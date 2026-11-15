"""The REST client: one method per Bisim route, rate limits and retries.

Every Bisim answer carries Discord's rate limit headers: ``X-RateLimit-Limit``,
``-Remaining``, ``-Reset`` (epoch seconds), ``-Reset-After`` (seconds) and
``-Bucket`` (an opaque name). As in discord.py, the library learns which bucket
each route is counted in and keeps one queue per bucket: it sends as many
requests at once as the bucket has room for, and when ``Remaining`` reaches 0
the next request waits ``Reset-After`` seconds instead of meeting a 429. A 429
still happens (another process using the same token, say): its body carries
``retryAfter``, and one with ``X-RateLimit-Global: true`` (the bot's whole
budget, not one route's) pauses every request.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import sys
from collections import deque
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Coroutine,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from urllib.parse import quote as _uriquote

import aiohttp

from . import __version__, utils
from .errors import (
    BisimServerError,
    Forbidden,
    HTTPException,
    LoginFailure,
    NotFound,
    RateLimited,
)

if TYPE_CHECKING:
    from .file import File

_log = logging.getLogger(__name__)

__all__ = ('Route', 'HTTPClient')

DEFAULT_API_URL = 'https://api.bisim.gg/api'
DEFAULT_GATEWAY_URL = 'wss://ws.bisim.gg/ws'
DEFAULT_CDN_URL = 'https://cdn.bisim.gg'

T = TypeVar('T')

_RETRY_STATUSES = frozenset({500, 502, 503, 504, 524})
_IDEMPOTENT = frozenset({'GET', 'HEAD', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'})


async def json_or_text(response: aiohttp.ClientResponse) -> Union[Dict[str, Any], List[Any], str, None]:
    text = await response.text(encoding='utf-8')
    if not text:
        return None
    try:
        if 'application/json' in (response.headers.get('Content-Type') or '') or text[:1] in '{[':
            return utils._from_json(text)
    except ValueError:
        pass
    return text


def _snowflake_str(value: Any) -> str:
    return str(utils._id_of(value))


class Route:
    """A REST route: the method, the path template and its parameters.

    The template's parameters decide the rate limit bucket: requests to the
    same path with the same channel, server, webhook or interaction share one.
    """

    BASE: ClassVar[str] = DEFAULT_API_URL

    def __init__(self, method: str, path: str, *, metadata: Optional[str] = None, **parameters: Any) -> None:
        self.method: str = method
        self.path: str = path
        self.metadata: Optional[str] = metadata
        self.parameters: Dict[str, Any] = parameters
        url = path
        if parameters:
            url = path.format_map(
                {k: _uriquote(v, safe='') if isinstance(v, str) else v for k, v in parameters.items()}
            )
        self.url: str = url

        self.channel_id: Optional[Any] = parameters.get('channel_id')
        self.guild_id: Optional[Any] = parameters.get('guild_id')
        self.webhook_id: Optional[Any] = parameters.get('webhook_id')
        self.webhook_token: Optional[str] = parameters.get('webhook_token')
        self.interaction_id: Optional[Any] = parameters.get('interaction_id')
        self.interaction_token: Optional[str] = parameters.get('interaction_token')

    @property
    def key(self) -> str:
        """The bucket key for the route, without the major parameters."""
        if self.metadata:
            return f'{self.method} {self.path}:{self.metadata}'
        return f'{self.method} {self.path}'

    @property
    def major_parameters(self) -> str:
        return '+'.join(
            str(k)
            for k in (
                self.channel_id,
                self.guild_id,
                self.webhook_id,
                self.webhook_token,
                self.interaction_id,
            )
            if k is not None
        )

    @property
    def bucket(self) -> str:
        return f'{self.key}:{self.major_parameters}'

    def __repr__(self) -> str:
        return f'<Route {self.method} {self.url}>'


def _ws_timeout(seconds: float) -> Any:
    timeout_cls = getattr(aiohttp, 'ClientWSTimeout', None)
    if timeout_cls is None:
        return seconds
    return timeout_cls(ws_close=seconds)


def _header_float(headers: Any, name: str) -> Optional[float]:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Ratelimit:
    """One of Bisim's rate limit buckets, as its ``X-RateLimit`` headers describe it.

    Adapted from discord.py's: it works like a semaphore that knows the size of
    the bucket's window and how much of it is left, so requests sharing a
    bucket go out together while there is room, and the next one waits for
    the window to reset once ``Remaining`` is 0.
    """

    __slots__ = (
        'limit',
        'remaining',
        'outgoing',
        'reset_after',
        'expires',
        'dirty',
        '_last_request',
        '_max_ratelimit_timeout',
        '_loop',
        '_pending_requests',
        '_sleeping',
    )

    def __init__(self, max_ratelimit_timeout: Optional[float]) -> None:
        self.limit: int = 1
        self.remaining: int = self.limit
        self.outgoing: int = 0
        self.reset_after: float = 0.0
        self.expires: Optional[float] = None
        self.dirty: bool = False
        self._max_ratelimit_timeout: Optional[float] = max_ratelimit_timeout
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._pending_requests: deque[asyncio.Future[Any]] = deque()
        # Only one waiter sleeps for the window; it wakes the others when it ends.
        self._sleeping: asyncio.Lock = asyncio.Lock()
        self._last_request: float = self._loop.time()

    def __repr__(self) -> str:
        return f'<RateLimitBucket limit={self.limit} remaining={self.remaining} pending_requests={len(self._pending_requests)}>'

    def reset(self) -> None:
        self.remaining = self.limit - self.outgoing
        self.expires = None
        self.reset_after = 0.0
        self.dirty = False

    def update(self, response: Any, *, use_clock: bool = False) -> None:
        headers = response.headers
        limit = _header_float(headers, 'X-RateLimit-Limit')
        remaining = _header_float(headers, 'X-RateLimit-Remaining')
        if limit is None or remaining is None:
            return
        self.limit = max(1, int(limit))
        if self.dirty:
            self.remaining = min(int(remaining), self.limit - self.outgoing)
        else:
            self.remaining = int(remaining)
            self.dirty = True

        reset_after = _header_float(headers, 'X-RateLimit-Reset-After')
        reset = _header_float(headers, 'X-RateLimit-Reset')
        if (use_clock or reset_after is None) and reset is not None:
            now = datetime.datetime.now(datetime.timezone.utc)
            reset_at = datetime.datetime.fromtimestamp(reset, datetime.timezone.utc)
            reset_after = (reset_at - now).total_seconds()
        if reset_after is None:
            # An answer without a reset time (an older server): nothing to wait for.
            self.reset_after = 0.0
            self.expires = None
            return
        self.reset_after = max(0.0, reset_after)
        self.expires = self._loop.time() + self.reset_after

    def _wake_next(self) -> None:
        while self._pending_requests:
            future = self._pending_requests.popleft()
            if not future.done():
                future.set_result(None)
                break

    def _wake(self, count: int = 1, *, exception: Optional[RateLimited] = None) -> None:
        awaken = 0
        while self._pending_requests:
            future = self._pending_requests.popleft()
            if not future.done():
                if exception:
                    future.set_exception(exception)
                else:
                    future.set_result(None)
                awaken += 1

            if awaken >= count:
                break

    async def _refresh(self) -> None:
        error = self._max_ratelimit_timeout and self.reset_after > self._max_ratelimit_timeout
        exception = RateLimited(self.reset_after) if error else None
        async with self._sleeping:
            if not error and self.reset_after > 0:
                await asyncio.sleep(self.reset_after)

        self.reset()
        self._wake(self.remaining, exception=exception)

    def is_expired(self) -> bool:
        return self.expires is not None and self._loop.time() > self.expires

    def is_inactive(self) -> bool:
        delta = self._loop.time() - self._last_request
        return delta >= 300 and self.outgoing == 0 and len(self._pending_requests) == 0

    async def acquire(self) -> None:
        self._last_request = self._loop.time()
        if self.is_expired():
            self.reset()

        if self._max_ratelimit_timeout is not None and self.expires is not None:
            # A wait longer than the caller accepts is refused before anything is sent.
            current_reset_after = self.expires - self._loop.time()
            if current_reset_after > self._max_ratelimit_timeout:
                raise RateLimited(current_reset_after)

        while self.remaining <= 0:
            future = self._loop.create_future()
            self._pending_requests.append(future)
            try:
                while not future.done():
                    # 30 is the smallest max_ratelimit_timeout allowed.
                    max_wait_time = self.expires - self._loop.time() if self.expires else 30
                    await asyncio.wait([future], timeout=max(0.0, max_wait_time))
                    if not future.done():
                        await self._refresh()
            except BaseException:
                future.cancel()
                if self.remaining > 0 and not future.cancelled():
                    self._wake_next()
                raise

        self.remaining -= 1
        self.outgoing += 1

    async def __aenter__(self) -> Ratelimit:
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.outgoing -= 1
        tokens = self.remaining - self.outgoing
        # Whether the bucket must be waited out now, before the next request.
        if not self._sleeping.locked():
            if tokens <= 0:
                await self._refresh()
            elif self._pending_requests:
                exception = (
                    RateLimited(self.reset_after)
                    if self._max_ratelimit_timeout and self.reset_after > self._max_ratelimit_timeout
                    else None
                )
                self._wake(tokens, exception=exception)


class _ResponseLike:
    """Stands in for a response when an error is raised without one."""

    def __init__(self, status: int, reason: str = '') -> None:
        self.status = status
        self.reason = reason
        self.headers: Dict[str, str] = {}


class HTTPClient:
    """Represents an HTTP client sending HTTP requests to Bisim's REST API."""

    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        connector: Optional[aiohttp.BaseConnector] = None,
        *,
        proxy: Optional[str] = None,
        proxy_auth: Optional[aiohttp.BasicAuth] = None,
        unsync_clock: bool = True,
        http_trace: Optional[aiohttp.TraceConfig] = None,
        max_ratelimit_timeout: Optional[float] = None,
        api_url: Optional[str] = None,
        cdn_url: Optional[str] = None,
        max_retries: int = 5,
    ) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = loop
        self.connector: Optional[aiohttp.BaseConnector] = connector
        self.__session: aiohttp.ClientSession = utils.MISSING
        # Route key -> the bucket Bisim named for it (X-RateLimit-Bucket).
        self._bucket_hashes: Dict[str, str] = {}
        # Bucket name -> its rate limit; or, before a route's bucket is known,
        # "route key:major parameters" -> a one-at-a-time stand-in.
        self._buckets: Dict[str, Ratelimit] = {}
        self._global_over: Optional[asyncio.Event] = None
        self.token: Optional[str] = None
        self.proxy: Optional[str] = proxy
        self.proxy_auth: Optional[aiohttp.BasicAuth] = proxy_auth
        self.http_trace: Optional[aiohttp.TraceConfig] = http_trace
        self.use_clock: bool = not unsync_clock
        self.max_ratelimit_timeout: Optional[float] = max(30.0, max_ratelimit_timeout) if max_ratelimit_timeout else None
        self.max_retries: int = max(1, max_retries)
        self.api_url: str = (api_url or DEFAULT_API_URL).rstrip('/')
        self.cdn_url: str = (cdn_url or DEFAULT_CDN_URL).rstrip('/')

        user_agent = 'BisimBot (https://github.com/bisim-gg/bisim.py {0}) Python/{1[0]}.{1[1]} aiohttp/{2}'
        self.user_agent: str = user_agent.format(__version__, sys.version_info, aiohttp.__version__)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_global_event(self) -> asyncio.Event:
        if self._global_over is None:
            self._global_over = asyncio.Event()
            self._global_over.set()
        return self._global_over

    async def _create_session(self) -> None:
        if self.__session is utils.MISSING or self.__session.closed:
            self.__session = aiohttp.ClientSession(
                connector=self.connector,
                trace_configs=None if self.http_trace is None else [self.http_trace],
                cookie_jar=aiohttp.DummyCookieJar(),
            )

    @property
    def session(self) -> aiohttp.ClientSession:
        return self.__session

    def _use_session(self, session: aiohttp.ClientSession) -> None:
        """Sends requests through a session the caller owns (used by webhooks)."""
        self.__session = session
        self._owns_session = False

    def clear(self) -> None:
        if self.__session is not utils.MISSING and self.__session.closed:
            self.__session = utils.MISSING

    async def close(self) -> None:
        if getattr(self, '_owns_session', True) is False:
            return
        if self.__session is not utils.MISSING and not self.__session.closed:
            await self.__session.close()

    async def ws_connect(self, url: str, *, compress: int = 0) -> aiohttp.ClientWebSocketResponse:
        kwargs: Dict[str, Any] = {
            'proxy_auth': self.proxy_auth,
            'proxy': self.proxy,
            'max_msg_size': 0,
            'timeout': _ws_timeout(30.0),
            'autoclose': False,
            'headers': {'User-Agent': self.user_agent},
            'compress': compress,
        }
        await self._create_session()
        return await self.__session.ws_connect(url, **kwargs)

    # ------------------------------------------------------------------
    # The request loop
    # ------------------------------------------------------------------

    def _try_clear_expired_ratelimits(self) -> None:
        if len(self._buckets) < 256:
            return
        for key in [key for key, bucket in self._buckets.items() if bucket.is_inactive()]:
            del self._buckets[key]

    def get_ratelimit(self, key: str) -> Ratelimit:
        try:
            value = self._buckets[key]
        except KeyError:
            self._buckets[key] = value = Ratelimit(self.max_ratelimit_timeout)
            self._try_clear_expired_ratelimits()
        return value

    def _learn_bucket(self, route: Route, key: str, ratelimit: Ratelimit, bisim_hash: str) -> Ratelimit:
        """Records which bucket a route is counted in; returns the rate limit that follows it.

        Bisim's bucket name already says whose budget it is (the bot's whole
        budget, or one route's own), so routes that share a name share one
        queue, whatever channel or server they name.
        """
        previous = self._bucket_hashes.get(route.key)
        if previous == bisim_hash:
            return ratelimit
        if previous is not None:
            _log.debug('A route (%s) has changed buckets: %s -> %s.', route.key, previous, bisim_hash)
        else:
            _log.debug('%s has found its rate limit bucket (%s).', route.key, bisim_hash)
        self._bucket_hashes[route.key] = bisim_hash
        shared = self._buckets.get(bisim_hash)
        if shared is None:
            self._buckets[bisim_hash] = ratelimit
            shared = ratelimit
        if previous is None and key != bisim_hash:
            # The one-at-a-time stand-in is no longer needed; other routes may still share the old name.
            self._buckets.pop(key, None)
        return shared

    @staticmethod
    def _retry_after(response: Any, data: Any) -> float:
        value: Any = None
        if isinstance(data, dict):
            value = data.get('retryAfter', data.get('retry_after'))
        if value is None:
            value = response.headers.get('Retry-After')
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    def _is_global(response: Any, data: Any) -> bool:
        if isinstance(data, dict) and data.get('global') is True:
            return True
        headers = response.headers
        if (headers.get('X-RateLimit-Global') or '').lower() == 'true':
            return True
        return (headers.get('X-RateLimit-Scope') or '').lower() == 'global'

    async def request(
        self,
        route: Route,
        *,
        json: Any = utils.MISSING,
        params: Optional[Dict[str, Any]] = None,
        form: Optional[Iterable[Dict[str, Any]]] = None,
        reason: Optional[str] = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Sends a request, waiting out rate limits and retrying server errors.

        Raises :exc:`Forbidden` (403), :exc:`NotFound` (404),
        :exc:`BisimServerError` (5xx after the retries) or
        :exc:`HTTPException` for any other failure.
        """
        await self._create_session()
        global_over = self._ensure_global_event()
        method = route.method
        url = self.api_url + route.url

        headers: Dict[str, str] = {'User-Agent': self.user_agent}
        if auth and self.token is not None:
            headers['Authorization'] = 'Bot ' + self.token
        body: Any = None
        if json is not utils.MISSING:
            headers['Content-Type'] = 'application/json'
            body = utils._to_json(json)
        if reason:
            headers['X-Audit-Log-Reason'] = _uriquote(reason, safe='/ ')
        if params:
            params = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in params.items() if v is not None}

        bisim_hash = self._bucket_hashes.get(route.key)
        key = bisim_hash if bisim_hash is not None else f'{route.key}:{route.major_parameters}'
        ratelimit = self.get_ratelimit(key)

        if not global_over.is_set():
            await global_over.wait()

        response: Optional[aiohttp.ClientResponse] = None
        data: Any = None
        async with ratelimit:
            for tries in range(self.max_retries):
                request_body: Any = body
                if form is not None:
                    request_body = aiohttp.FormData(quote_fields=False)
                    for field in form:
                        request_body.add_field(**field)
                try:
                    async with self.__session.request(
                        method,
                        url,
                        data=request_body,
                        params=params,
                        headers=headers,
                        proxy=self.proxy,
                        proxy_auth=self.proxy_auth,
                        **kwargs,
                    ) as response:
                        _log.debug('%s %s with %s has returned %s', method, url, body, response.status)
                        data = await json_or_text(response)

                        # Which bucket this route is counted in, and how much of it is left.
                        bucket_name = response.headers.get('X-RateLimit-Bucket')
                        if bucket_name:
                            learned = self._learn_bucket(route, key, ratelimit, bucket_name)
                            if learned is not ratelimit and response.status != 429:
                                learned.update(response, use_clock=self.use_clock)
                        if response.status != 429 and 'X-RateLimit-Remaining' in response.headers:
                            ratelimit.update(response, use_clock=self.use_clock)
                            if ratelimit.remaining == 0:
                                _log.debug(
                                    'A rate limit bucket (%s) has been used up. Waiting %.2f seconds before the next request.',
                                    bucket_name or route.key,
                                    ratelimit.reset_after,
                                )

                        if 300 > response.status >= 200:
                            _log.debug('%s %s has received %s', method, url, data)
                            return data

                        if response.status == 429:
                            retry_after = self._retry_after(response, data)
                            is_global = self._is_global(response, data)
                            if (
                                not is_global
                                and self.max_ratelimit_timeout is not None
                                and retry_after > self.max_ratelimit_timeout
                            ):
                                raise RateLimited(retry_after)
                            if is_global:
                                _log.warning('Global rate limit has been hit. Retrying in %.2f seconds.', retry_after)
                                global_over.clear()
                                try:
                                    await asyncio.sleep(retry_after)
                                finally:
                                    global_over.set()
                            else:
                                _log.warning(
                                    'We are being rate limited. %s %s responded with 429. Retrying in %.2f seconds.',
                                    method,
                                    url,
                                    retry_after,
                                )
                                await asyncio.sleep(retry_after)
                            continue

                        if response.status in _RETRY_STATUSES and tries < self.max_retries - 1:
                            await asyncio.sleep(1 + tries * 2)
                            continue

                        if response.status == 403:
                            raise Forbidden(response, data)
                        if response.status == 404:
                            raise NotFound(response, data)
                        if response.status >= 500:
                            raise BisimServerError(response, data)
                        raise HTTPException(response, data)

                except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError, asyncio.TimeoutError) as exc:
                    # A POST that may already have reached the server is not repeated,
                    # unless the connection failed before anything was sent.
                    safe = method in _IDEMPOTENT or isinstance(exc, aiohttp.ClientConnectorError)
                    if safe and tries < self.max_retries - 1:
                        _log.debug('%s %s failed with %r, retrying.', method, url, exc)
                        await asyncio.sleep(1 + tries * 2)
                        continue
                    raise

            if response is not None:
                if response.status >= 500:
                    raise BisimServerError(response, data)
                raise HTTPException(response, data)

        raise RuntimeError('Unreachable code in HTTP handling')

    async def get_from_cdn(self, url: str) -> bytes:
        """Downloads a file from the CDN (or any public address)."""
        await self._create_session()
        async with self.__session.get(url, proxy=self.proxy, proxy_auth=self.proxy_auth) as resp:
            if resp.status == 200:
                return await resp.read()
            if resp.status == 404:
                raise NotFound(resp, 'asset not found')
            if resp.status == 403:
                raise Forbidden(resp, 'cannot retrieve asset')
            raise HTTPException(resp, 'failed to get asset')

    async def upload_to_url(self, url: str, data: bytes, content_type: str) -> None:
        """PUTs bytes to a presigned upload address (no authorization header)."""
        await self._create_session()
        headers = {'Content-Type': content_type, 'Content-Length': str(len(data))}
        for tries in range(3):
            try:
                async with self.__session.put(
                    url,
                    data=data,
                    headers=headers,
                    skip_auto_headers=('User-Agent',),
                    proxy=self.proxy,
                    proxy_auth=self.proxy_auth,
                ) as resp:
                    if 200 <= resp.status < 300:
                        return
                    text = await resp.text()
                    if resp.status in _RETRY_STATUSES and tries < 2:
                        await asyncio.sleep(1 + tries * 2)
                        continue
                    if resp.status == 403:
                        raise Forbidden(resp, text or 'the upload address refused the file')
                    raise HTTPException(resp, text or 'uploading the file failed')
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError, asyncio.TimeoutError):
                if tries < 2:
                    await asyncio.sleep(1 + tries * 2)
                    continue
                raise

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def static_login(self, token: str) -> Dict[str, Any]:
        await self._create_session()
        old_token = self.token
        self.token = token
        try:
            data = await self.request(Route('GET', '/auth/me'))
        except HTTPException as exc:
            self.token = old_token
            if exc.status == 401:
                raise LoginFailure('Improper token has been passed.') from exc
            raise
        return data

    async def logout(self) -> None:
        self.token = None

    # ------------------------------------------------------------------
    # Self and users
    # ------------------------------------------------------------------

    def get_me(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/auth/me'))

    def application_info(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/applications/@me'))

    def get_application(self, application_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/applications/{application_id}', application_id=_snowflake_str(application_id)))

    def edit_application(self, application_id: Any, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/applications/{application_id}', application_id=_snowflake_str(application_id))
        return self.request(r, json=fields)

    def get_user(self, user_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/users/{user_id}', user_id=_snowflake_str(user_id)))

    def _picture_form(self, data: bytes, content_type: str, name: str) -> List[Dict[str, Any]]:
        extension = content_type.split('/')[-1] or 'png'
        return [{'name': 'file', 'value': data, 'filename': f'{name}.{extension}', 'content_type': content_type}]

    def edit_my_avatar(self, data: bytes, content_type: str) -> Coroutine[Any, Any, Any]:
        """The bot's own picture (multipart field ``file``)."""
        return self.request(Route('POST', '/users/@me/avatar'), form=self._picture_form(data, content_type, 'avatar'))

    def delete_my_avatar(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('DELETE', '/users/@me/avatar'))

    def edit_my_banner(self, data: bytes, content_type: str) -> Coroutine[Any, Any, Any]:
        """The bot's own banner (multipart field ``file``)."""
        return self.request(Route('POST', '/users/@me/banner'), form=self._picture_form(data, content_type, 'banner'))

    def delete_my_banner(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('DELETE', '/users/@me/banner'))

    def get_client_config(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/client-config'))

    # ------------------------------------------------------------------
    # Gateway
    # ------------------------------------------------------------------

    def get_bot_gateway(self, application_id: Any, intents: Optional[int] = None) -> Coroutine[Any, Any, Any]:
        """Mints a gateway pass for these intents: ``{token, expiresInMs, intents}``."""
        r = Route('POST', '/applications/{application_id}/gateway', application_id=_snowflake_str(application_id))
        if intents is None:
            return self.request(r)
        return self.request(r, json={'intents': int(intents)})

    # ------------------------------------------------------------------
    # Guilds
    # ------------------------------------------------------------------

    def get_guilds(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds'))

    def get_guild(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}', guild_id=_snowflake_str(guild_id)))

    def edit_guild(self, guild_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('PATCH', '/guilds/{guild_id}', guild_id=_snowflake_str(guild_id)), json=fields, reason=reason)

    def leave_guild(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('DELETE', '/guilds/{guild_id}/members/@me', guild_id=_snowflake_str(guild_id)))

    def get_audit_logs(self, guild_id: Any, *, before: Optional[Any] = None, limit: Optional[int] = None) -> Coroutine[Any, Any, Any]:
        params: Dict[str, Any] = {}
        if before is not None:
            params['before'] = before
        if limit is not None:
            params['limit'] = limit
        return self.request(Route('GET', '/guilds/{guild_id}/audit-log', guild_id=_snowflake_str(guild_id)), params=params)

    def get_auto_moderation_rules(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/automod/rules', guild_id=_snowflake_str(guild_id)))

    def create_auto_moderation_rule(
        self, guild_id: Any, *, reason: Optional[str] = None, **fields: Any
    ) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/guilds/{guild_id}/automod/rules', guild_id=_snowflake_str(guild_id))
        return self.request(r, json=fields, reason=reason)

    def get_auto_moderation_rule(self, guild_id: Any, rule_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET', '/guilds/{guild_id}/automod/rules/{rule_id}', guild_id=_snowflake_str(guild_id), rule_id=_snowflake_str(rule_id)
        )
        return self.request(r)

    def edit_auto_moderation_rule(
        self, guild_id: Any, rule_id: Any, *, reason: Optional[str] = None, **fields: Any
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH', '/guilds/{guild_id}/automod/rules/{rule_id}', guild_id=_snowflake_str(guild_id), rule_id=_snowflake_str(rule_id)
        )
        return self.request(r, json=fields, reason=reason)

    def delete_auto_moderation_rule(self, guild_id: Any, rule_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE', '/guilds/{guild_id}/automod/rules/{rule_id}', guild_id=_snowflake_str(guild_id), rule_id=_snowflake_str(rule_id)
        )
        return self.request(r, reason=reason)

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def get_channel(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/channels/{channel_id}', channel_id=_snowflake_str(channel_id)))

    def get_all_guild_channels(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/channels', guild_id=_snowflake_str(guild_id)))

    def create_channel(self, guild_id: Any, payload: Dict[str, Any], *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        return self.request(Route('POST', '/guilds/{guild_id}/channels', guild_id=_snowflake_str(guild_id)), json=payload, reason=reason)

    def bulk_channel_update(
        self, guild_id: Any, data: List[Dict[str, Any]], *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/channels/positions', guild_id=_snowflake_str(guild_id))
        return self.request(r, json={'channels': data}, reason=reason)

    def edit_channel(self, guild_id: Any, channel_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/guilds/{guild_id}/channels/{channel_id}',
            guild_id=_snowflake_str(guild_id),
            channel_id=_snowflake_str(channel_id),
        )
        return self.request(r, json=fields, reason=reason)

    def delete_channel(self, guild_id: Any, channel_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/guilds/{guild_id}/channels/{channel_id}',
            guild_id=_snowflake_str(guild_id),
            channel_id=_snowflake_str(channel_id),
        )
        return self.request(r, reason=reason)

    def get_channel_overwrites(self, guild_id: Any, channel_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/guilds/{guild_id}/channels/{channel_id}/overwrites',
            guild_id=_snowflake_str(guild_id),
            channel_id=_snowflake_str(channel_id),
        )
        return self.request(r)

    def edit_channel_permissions(
        self,
        guild_id: Any,
        channel_id: Any,
        target: Any,
        allow: Union[int, str],
        deny: Union[int, str],
        type: int,
        *,
        reason: Optional[str] = None,
    ) -> Coroutine[Any, Any, Any]:
        payload = {'type': type, 'allow': str(allow), 'deny': str(deny)}
        r = Route(
            'PUT',
            '/guilds/{guild_id}/channels/{channel_id}/overwrites/{target_id}',
            guild_id=_snowflake_str(guild_id),
            channel_id=_snowflake_str(channel_id),
            target_id=_snowflake_str(target),
        )
        return self.request(r, json=payload, reason=reason)

    def delete_channel_permissions(
        self, guild_id: Any, channel_id: Any, target: Any, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/guilds/{guild_id}/channels/{channel_id}/overwrites/{target_id}',
            guild_id=_snowflake_str(guild_id),
            channel_id=_snowflake_str(channel_id),
            target_id=_snowflake_str(target),
        )
        return self.request(r, reason=reason)

    def send_typing(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('POST', '/channels/{channel_id}/typing', channel_id=_snowflake_str(channel_id)))

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def get_members(self, guild_id: Any, limit: Optional[int] = None, after: Optional[Any] = None) -> Coroutine[Any, Any, Any]:
        params: Dict[str, Any] = {}
        if limit is not None:
            params['limit'] = limit
        if after is not None:
            params['after'] = after
        return self.request(Route('GET', '/guilds/{guild_id}/members', guild_id=_snowflake_str(guild_id)), params=params)

    def search_members(self, guild_id: Any, query: str, limit: int) -> Coroutine[Any, Any, Any]:
        params = {'query': query, 'limit': limit}
        return self.request(Route('GET', '/guilds/{guild_id}/members/search', guild_id=_snowflake_str(guild_id)), params=params)

    def get_member(self, guild_id: Any, member_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route('GET', '/guilds/{guild_id}/members/{member_id}', guild_id=_snowflake_str(guild_id), member_id=_snowflake_str(member_id))
        return self.request(r)

    def edit_member(self, guild_id: Any, user_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/members/{user_id}', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id))
        return self.request(r, json=fields, reason=reason)

    def change_my_nickname(self, guild_id: Any, nickname: Optional[str], *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/members/@me/nickname', guild_id=_snowflake_str(guild_id))
        return self.request(r, json={'nickname': nickname or None}, reason=reason)

    def add_role(self, guild_id: Any, user_id: Any, role_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PUT',
            '/guilds/{guild_id}/members/{user_id}/roles/{role_id}',
            guild_id=_snowflake_str(guild_id),
            user_id=_snowflake_str(user_id),
            role_id=_snowflake_str(role_id),
        )
        return self.request(r, reason=reason)

    def remove_role(self, guild_id: Any, user_id: Any, role_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/guilds/{guild_id}/members/{user_id}/roles/{role_id}',
            guild_id=_snowflake_str(guild_id),
            user_id=_snowflake_str(user_id),
            role_id=_snowflake_str(role_id),
        )
        return self.request(r, reason=reason)

    def kick(self, user_id: Any, guild_id: Any, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/guilds/{guild_id}/members/{user_id}', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id))
        payload = {'reason': reason} if reason else None
        if payload is None:
            return self.request(r, reason=reason)
        return self.request(r, json=payload, reason=reason)

    def timeout_member(
        self, guild_id: Any, user_id: Any, until: Optional[str], *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PUT', '/guilds/{guild_id}/members/{user_id}/timeout', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id)
        )
        payload: Dict[str, Any] = {'until': until}
        if reason:
            payload['reason'] = reason
        return self.request(r, json=payload, reason=reason)

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def get_roles(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/roles', guild_id=_snowflake_str(guild_id)))

    def create_role(self, guild_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('POST', '/guilds/{guild_id}/roles', guild_id=_snowflake_str(guild_id)), json=fields, reason=reason)

    def move_role_position(
        self, guild_id: Any, positions: List[Dict[str, Any]], *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/roles/positions', guild_id=_snowflake_str(guild_id))
        return self.request(r, json={'roles': positions}, reason=reason)

    def edit_role(self, guild_id: Any, role_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/roles/{role_id}', guild_id=_snowflake_str(guild_id), role_id=_snowflake_str(role_id))
        return self.request(r, json=fields, reason=reason)

    def delete_role(self, guild_id: Any, role_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/guilds/{guild_id}/roles/{role_id}', guild_id=_snowflake_str(guild_id), role_id=_snowflake_str(role_id))
        return self.request(r, reason=reason)

    # ------------------------------------------------------------------
    # Bans
    # ------------------------------------------------------------------

    def get_bans(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/bans', guild_id=_snowflake_str(guild_id)))

    def get_ban(self, user_id: Any, guild_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route('GET', '/guilds/{guild_id}/bans/{user_id}', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id))
        return self.request(r)

    def ban(
        self, user_id: Any, guild_id: Any, delete_message_seconds: int = 86400, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route('PUT', '/guilds/{guild_id}/bans/{user_id}', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id))
        payload: Dict[str, Any] = {'deleteMessageSeconds': int(delete_message_seconds)}
        if reason:
            payload['reason'] = reason
        return self.request(r, json=payload, reason=reason)

    def unban(self, user_id: Any, guild_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/guilds/{guild_id}/bans/{user_id}', guild_id=_snowflake_str(guild_id), user_id=_snowflake_str(user_id))
        return self.request(r, reason=reason)

    def bulk_ban(
        self, guild_id: Any, user_ids: Sequence[Any], delete_message_seconds: int = 86400, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        """``{bannedUsers, failedUsers}``; a 400 ``BULK_BAN_FAILED`` when nobody was banned."""
        r = Route('POST', '/guilds/{guild_id}/bulk-ban', guild_id=_snowflake_str(guild_id))
        payload: Dict[str, Any] = {
            'userIds': [_snowflake_str(u) for u in user_ids],
            'deleteMessageSeconds': int(delete_message_seconds),
        }
        if reason:
            payload['reason'] = reason
        return self.request(r, json=payload, reason=reason)

    # ------------------------------------------------------------------
    # Invites
    # ------------------------------------------------------------------

    def create_invite(
        self,
        guild_id: Any,
        channel_id: Optional[Any],
        *,
        max_age: int = 0,
        max_uses: int = 0,
        reason: Optional[str] = None,
    ) -> Coroutine[Any, Any, Any]:
        payload: Dict[str, Any] = {}
        if channel_id is not None:
            payload['channelId'] = _snowflake_str(channel_id)
        if max_age:
            payload['maxAgeSec'] = int(max_age)
        if max_uses:
            payload['maxUses'] = int(max_uses)
        return self.request(Route('POST', '/guilds/{guild_id}/invites', guild_id=_snowflake_str(guild_id)), json=payload, reason=reason)

    def invites_from(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/invites', guild_id=_snowflake_str(guild_id)))

    def delete_invite(self, guild_id: Any, code: str, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/guilds/{guild_id}/invites/{code}', guild_id=_snowflake_str(guild_id), code=code)
        return self.request(r, reason=reason)

    def get_invite(self, code: str) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/invites/{code}', code=code))

    # ------------------------------------------------------------------
    # Emojis, stickers and sounds
    # ------------------------------------------------------------------

    def get_all_custom_emojis(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/emojis', guild_id=_snowflake_str(guild_id)))

    def create_custom_emoji(
        self, guild_id: Any, name: str, image: bytes, content_type: str, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        form = [
            {'name': 'name', 'value': name},
            {'name': 'file', 'value': image, 'filename': f'{name}.{content_type.split("/")[-1]}', 'content_type': content_type},
        ]
        return self.request(Route('POST', '/guilds/{guild_id}/emojis', guild_id=_snowflake_str(guild_id)), form=form, reason=reason)

    def delete_custom_emoji(self, guild_id: Any, emoji_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/guilds/{guild_id}/emojis/{emoji_id}', guild_id=_snowflake_str(guild_id), emoji_id=_snowflake_str(emoji_id))
        return self.request(r, reason=reason)

    def edit_custom_emoji(
        self, guild_id: Any, emoji_id: Any, *, payload: Dict[str, Any], reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/guilds/{guild_id}/emojis/{emoji_id}', guild_id=_snowflake_str(guild_id), emoji_id=_snowflake_str(emoji_id))
        return self.request(r, json=payload, reason=reason)

    def get_all_guild_stickers(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/stickers', guild_id=_snowflake_str(guild_id)))

    def create_guild_sticker(
        self, guild_id: Any, name: str, data: bytes, filename: str, content_type: str, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        form = [
            {'name': 'name', 'value': name},
            {'name': 'file', 'value': data, 'filename': filename, 'content_type': content_type},
        ]
        return self.request(Route('POST', '/guilds/{guild_id}/stickers', guild_id=_snowflake_str(guild_id)), form=form, reason=reason)

    def delete_guild_sticker(self, guild_id: Any, sticker_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE', '/guilds/{guild_id}/stickers/{sticker_id}', guild_id=_snowflake_str(guild_id), sticker_id=_snowflake_str(sticker_id)
        )
        return self.request(r, reason=reason)

    def modify_guild_sticker(
        self, guild_id: Any, sticker_id: Any, payload: Dict[str, Any], *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH', '/guilds/{guild_id}/stickers/{sticker_id}', guild_id=_snowflake_str(guild_id), sticker_id=_snowflake_str(sticker_id)
        )
        return self.request(r, json=payload, reason=reason)

    def get_soundboard_sounds(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/sounds', guild_id=_snowflake_str(guild_id)))

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    def create_webhook(self, channel_id: Any, *, name: str, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/webhooks', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={'name': name}, reason=reason)

    def channel_webhooks(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/channels/{channel_id}/webhooks', channel_id=_snowflake_str(channel_id)))

    def guild_webhooks(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/webhooks', guild_id=_snowflake_str(guild_id)))

    def get_webhook(self, webhook_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/webhooks/{webhook_id}', webhook_id=_snowflake_str(webhook_id)))

    def edit_webhook(self, webhook_id: Any, *, reason: Optional[str] = None, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/webhooks/{webhook_id}', webhook_id=_snowflake_str(webhook_id))
        return self.request(r, json=fields, reason=reason)

    def delete_webhook(self, webhook_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        return self.request(Route('DELETE', '/webhooks/{webhook_id}', webhook_id=_snowflake_str(webhook_id)), reason=reason)

    def execute_webhook(
        self, webhook_id: Any, token: str, payload: Dict[str, Any], *, wait: bool = False
    ) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=_snowflake_str(webhook_id), webhook_token=token)
        params = {'wait': 'true'} if wait else None
        return self.request(r, json=payload, params=params, auth=False)

    def edit_webhook_avatar(
        self, webhook_id: Any, data: bytes, content_type: str, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        """The webhook's stored picture (multipart field ``file``, Manage Webhooks): the webhook back."""
        r = Route('POST', '/webhooks/{webhook_id}/avatar', webhook_id=_snowflake_str(webhook_id))
        return self.request(r, form=self._picture_form(data, content_type, 'avatar'), reason=reason)

    def delete_webhook_avatar(self, webhook_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('DELETE', '/webhooks/{webhook_id}/avatar', webhook_id=_snowflake_str(webhook_id))
        return self.request(r, reason=reason)

    def create_webhook_attachments(self, webhook_id: Any, token: str, files: List[Dict[str, Any]]) -> Coroutine[Any, Any, Any]:
        """Upload addresses for a webhook's message files, minted with its token."""
        r = Route(
            'POST', '/webhooks/{webhook_id}/{webhook_token}/attachments', webhook_id=_snowflake_str(webhook_id), webhook_token=token
        )
        return self.request(r, json={'files': files}, auth=False)

    def get_webhook_message(self, webhook_id: Any, token: str, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}',
            webhook_id=_snowflake_str(webhook_id),
            webhook_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, auth=False)

    def edit_webhook_message(
        self, webhook_id: Any, token: str, message_id: Any, payload: Dict[str, Any]
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}',
            webhook_id=_snowflake_str(webhook_id),
            webhook_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, json=payload, auth=False)

    def delete_webhook_message(self, webhook_id: Any, token: str, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}',
            webhook_id=_snowflake_str(webhook_id),
            webhook_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, auth=False)

    # ------------------------------------------------------------------
    # Voice: the bot's own connection
    # ------------------------------------------------------------------

    def join_voice(
        self, channel_id: Any, *, self_muted: bool = False, self_deafened: Optional[bool] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/voice/join', channel_id=_snowflake_str(channel_id))
        payload: Dict[str, Any] = {'selfMuted': bool(self_muted)}
        # Left out, Bisim joins a bot deafened.
        if self_deafened is not None:
            payload['selfDeafened'] = bool(self_deafened)
        return self.request(r, json=payload)

    def leave_voice(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/voice/leave', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={})

    def edit_voice_state(self, channel_id: Any, **fields: Any) -> Coroutine[Any, Any, Any]:
        r = Route('PATCH', '/channels/{channel_id}/voice/state', channel_id=_snowflake_str(channel_id))
        return self.request(r, json=fields)

    def send_soundboard_sound(self, channel_id: Any, sound_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/soundboard/play', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={'soundId': _snowflake_str(sound_id)})

    def edit_voice_channel_status(
        self, channel_id: Any, status: Optional[str], *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        """A voice channel's status line (empty clears it): ``{channelId, status}``."""
        r = Route('PUT', '/channels/{channel_id}/voice-status', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={'status': status or ''}, reason=reason)

    # ------------------------------------------------------------------
    # Voice moderation
    # ------------------------------------------------------------------

    def get_channel_voice_states(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/channels/{channel_id}/voice-states', channel_id=_snowflake_str(channel_id)))

    def get_guild_voice_states(self, guild_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/guilds/{guild_id}/voice-states', guild_id=_snowflake_str(guild_id)))

    def edit_voice_member(
        self, channel_id: Any, user_id: Any, *, reason: Optional[str] = None, **fields: Any
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH', '/channels/{channel_id}/voice/members/{user_id}', channel_id=_snowflake_str(channel_id), user_id=_snowflake_str(user_id)
        )
        return self.request(r, json=fields, reason=reason)

    def move_voice_member(
        self, channel_id: Any, user_id: Any, target_channel_id: Any, *, reason: Optional[str] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'POST',
            '/channels/{channel_id}/voice/members/{user_id}/move',
            channel_id=_snowflake_str(channel_id),
            user_id=_snowflake_str(user_id),
        )
        return self.request(r, json={'channelId': _snowflake_str(target_channel_id)}, reason=reason)

    def disconnect_voice_member(self, channel_id: Any, user_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE', '/channels/{channel_id}/voice/members/{user_id}', channel_id=_snowflake_str(channel_id), user_id=_snowflake_str(user_id)
        )
        return self.request(r, reason=reason)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def logs_from(
        self,
        channel_id: Any,
        limit: int,
        before: Optional[Any] = None,
        after: Optional[Any] = None,
        around: Optional[Any] = None,
    ) -> Coroutine[Any, Any, Any]:
        params: Dict[str, Any] = {'limit': max(1, min(int(limit), 100))}
        if before is not None:
            params['before'] = before
        if after is not None:
            params['after'] = after
        if around is not None:
            params['around'] = around
        return self.request(Route('GET', '/channels/{channel_id}/messages', channel_id=_snowflake_str(channel_id)), params=params)

    def get_message(self, channel_id: Any, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET', '/channels/{channel_id}/messages/{message_id}', channel_id=_snowflake_str(channel_id), message_id=_snowflake_str(message_id)
        )
        return self.request(r)

    def send_message(self, channel_id: Any, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        return self.request(Route('POST', '/channels/{channel_id}/messages', channel_id=_snowflake_str(channel_id)), json=payload)

    def edit_message(self, channel_id: Any, message_id: Any, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH', '/channels/{channel_id}/messages/{message_id}', channel_id=_snowflake_str(channel_id), message_id=_snowflake_str(message_id)
        )
        return self.request(r, json=payload)

    def delete_message(self, channel_id: Any, message_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE', '/channels/{channel_id}/messages/{message_id}', channel_id=_snowflake_str(channel_id), message_id=_snowflake_str(message_id)
        )
        return self.request(r, reason=reason)

    def delete_messages(self, channel_id: Any, message_ids: Sequence[Any], *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/messages/bulk-delete', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={'messages': [_snowflake_str(m) for m in message_ids]}, reason=reason)

    def search_messages(self, channel_id: Any, **params: Any) -> Coroutine[Any, Any, Any]:
        r = Route('GET', '/channels/{channel_id}/messages/search', channel_id=_snowflake_str(channel_id))
        return self.request(r, params=params)

    def create_attachments(self, channel_id: Any, files: List[Dict[str, Any]]) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/channels/{channel_id}/attachments', channel_id=_snowflake_str(channel_id))
        return self.request(r, json={'files': files})

    def add_reaction(self, channel_id: Any, message_id: Any, emoji: str) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PUT',
            '/channels/{channel_id}/messages/{message_id}/reactions/{emoji}',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            emoji=emoji,
        )
        return self.request(r)

    def remove_own_reaction(self, channel_id: Any, message_id: Any, emoji: str) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/channels/{channel_id}/messages/{message_id}/reactions/{emoji}',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            emoji=emoji,
        )
        return self.request(r)

    def remove_reaction(self, channel_id: Any, message_id: Any, emoji: str, member_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{member_id}',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            emoji=emoji,
            member_id=_snowflake_str(member_id),
        )
        return self.request(r)

    def get_reaction_users(
        self, channel_id: Any, message_id: Any, emoji: str, limit: int, after: Optional[Any] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/channels/{channel_id}/messages/{message_id}/reactions/{emoji}',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            emoji=emoji,
        )
        params: Dict[str, Any] = {'limit': limit}
        if after is not None:
            params['after'] = after
        return self.request(r, params=params)

    def clear_reactions(self, channel_id: Any, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/channels/{channel_id}/messages/{message_id}/reactions',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
        )
        return self.request(r)

    def clear_single_reaction(self, channel_id: Any, message_id: Any, emoji: str) -> Coroutine[Any, Any, Any]:
        # The path ends in /all: Bisim's .../reactions/{emoji} removes the caller's own.
        r = Route(
            'DELETE',
            '/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/all',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            emoji=emoji,
        )
        return self.request(r)

    def pins_from(self, channel_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/channels/{channel_id}/pins', channel_id=_snowflake_str(channel_id)))

    def pin_message(self, channel_id: Any, message_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route('PUT', '/channels/{channel_id}/pins/{message_id}', channel_id=_snowflake_str(channel_id), message_id=_snowflake_str(message_id))
        return self.request(r, reason=reason)

    def unpin_message(self, channel_id: Any, message_id: Any, *, reason: Optional[str] = None) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE', '/channels/{channel_id}/pins/{message_id}', channel_id=_snowflake_str(channel_id), message_id=_snowflake_str(message_id)
        )
        return self.request(r, reason=reason)

    def end_poll(self, channel_id: Any, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'POST',
            '/channels/{channel_id}/messages/{message_id}/poll/end',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
        )
        return self.request(r)

    def get_poll_answer_voters(self, channel_id: Any, message_id: Any, answer_id: int) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/channels/{channel_id}/messages/{message_id}/poll/answers/{answer_id}/voters',
            channel_id=_snowflake_str(channel_id),
            message_id=_snowflake_str(message_id),
            answer_id=int(answer_id),
        )
        return self.request(r)

    # ------------------------------------------------------------------
    # DMs
    # ------------------------------------------------------------------

    def get_private_channels(self) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/dms'))

    def start_private_message(self, user_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('POST', '/dms'), json={'userId': _snowflake_str(user_id)})

    # ------------------------------------------------------------------
    # Application commands
    # ------------------------------------------------------------------

    def get_global_commands(self, application_id: Any) -> Coroutine[Any, Any, Any]:
        return self.request(Route('GET', '/applications/{application_id}/commands', application_id=_snowflake_str(application_id)))

    def get_global_command(self, application_id: Any, command_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/applications/{application_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r)

    def upsert_global_command(self, application_id: Any, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route('POST', '/applications/{application_id}/commands', application_id=_snowflake_str(application_id))
        return self.request(r, json=payload)

    def edit_global_command(self, application_id: Any, command_id: Any, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/applications/{application_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r, json=payload)

    def delete_global_command(self, application_id: Any, command_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/applications/{application_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r)

    def bulk_upsert_global_commands(self, application_id: Any, payload: List[Dict[str, Any]]) -> Coroutine[Any, Any, Any]:
        r = Route('PUT', '/applications/{application_id}/commands', application_id=_snowflake_str(application_id))
        return self.request(r, json={'commands': payload})

    def get_guild_commands(self, application_id: Any, guild_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/applications/{application_id}/guilds/{guild_id}/commands',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
        )
        return self.request(r)

    def get_guild_command(self, application_id: Any, guild_id: Any, command_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r)

    def upsert_guild_command(self, application_id: Any, guild_id: Any, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'POST',
            '/applications/{application_id}/guilds/{guild_id}/commands',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
        )
        return self.request(r, json=payload)

    def edit_guild_command(
        self, application_id: Any, guild_id: Any, command_id: Any, payload: Dict[str, Any]
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r, json=payload)

    def delete_guild_command(self, application_id: Any, guild_id: Any, command_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
            command_id=_snowflake_str(command_id),
        )
        return self.request(r)

    def bulk_upsert_guild_commands(self, application_id: Any, guild_id: Any, payload: List[Dict[str, Any]]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PUT',
            '/applications/{application_id}/guilds/{guild_id}/commands',
            application_id=_snowflake_str(application_id),
            guild_id=_snowflake_str(guild_id),
        )
        return self.request(r, json={'commands': payload})

    # ------------------------------------------------------------------
    # Interaction responses (authorised by the interaction token)
    # ------------------------------------------------------------------

    def create_interaction_response(
        self, interaction_id: Any, token: str, *, type: int, data: Optional[Dict[str, Any]] = None
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'POST',
            '/interactions/{interaction_id}/{interaction_token}/callback',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        payload: Dict[str, Any] = {'type': type}
        if data is not None:
            payload['data'] = data
        return self.request(r, json=payload, auth=False)

    def create_interaction_attachments(
        self, interaction_id: Any, token: str, files: List[Dict[str, Any]]
    ) -> Coroutine[Any, Any, Any]:
        """Upload addresses for the files of an interaction's answers, minted with its token."""
        r = Route(
            'POST',
            '/interactions/{interaction_id}/{interaction_token}/attachments',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        return self.request(r, json={'files': files}, auth=False)

    def get_original_interaction_response(self, interaction_id: Any, token: str) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/interactions/{interaction_id}/{interaction_token}/messages/@original',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        return self.request(r, auth=False)

    def edit_original_interaction_response(self, interaction_id: Any, token: str, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/interactions/{interaction_id}/{interaction_token}/messages/@original',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        return self.request(r, json=payload, auth=False)

    def delete_original_interaction_response(self, interaction_id: Any, token: str) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/interactions/{interaction_id}/{interaction_token}/messages/@original',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        return self.request(r, auth=False)

    def create_followup_message(self, interaction_id: Any, token: str, payload: Dict[str, Any]) -> Coroutine[Any, Any, Any]:
        r = Route(
            'POST',
            '/interactions/{interaction_id}/{interaction_token}/followup',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
        )
        return self.request(r, json=payload, auth=False)

    def get_followup_message(self, interaction_id: Any, token: str, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'GET',
            '/interactions/{interaction_id}/{interaction_token}/messages/{message_id}',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, auth=False)

    def edit_followup_message(
        self, interaction_id: Any, token: str, message_id: Any, payload: Dict[str, Any]
    ) -> Coroutine[Any, Any, Any]:
        r = Route(
            'PATCH',
            '/interactions/{interaction_id}/{interaction_token}/messages/{message_id}',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, json=payload, auth=False)

    def delete_followup_message(self, interaction_id: Any, token: str, message_id: Any) -> Coroutine[Any, Any, Any]:
        r = Route(
            'DELETE',
            '/interactions/{interaction_id}/{interaction_token}/messages/{message_id}',
            interaction_id=_snowflake_str(interaction_id),
            interaction_token=token,
            message_id=_snowflake_str(message_id),
        )
        return self.request(r, auth=False)
