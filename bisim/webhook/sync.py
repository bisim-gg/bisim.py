"""A blocking webhook for scripts that do not run an event loop.

It uses only the standard library (:mod:`urllib`).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

from .. import utils
from ..errors import BisimServerError, Forbidden, HTTPException, NotFound, NotSupported

if TYPE_CHECKING:
    from ..embeds import Embed

__all__ = (
    'SyncWebhook',
    'SyncWebhookMessage',
)

_WEBHOOK_URL_RE = re.compile(
    r'(?P<base>https?://[^\s]*?)/webhooks/(?P<id>[0-9]{1,20})/(?P<token>[A-Za-z0-9._-]{20,})'
)


class _SyncResponse:
    def __init__(self, status: int, reason: str) -> None:
        self.status = status
        self.reason = reason
        self.headers: Dict[str, str] = {}


class SyncWebhookMessage:
    """A message sent by a :class:`SyncWebhook` with ``wait=True``: the raw data Bisim returned.

    Attributes
    -----------
    id: :class:`int`
        The message ID.
    channel_id: :class:`int`
        The channel the message is in.
    content: :class:`str`
        The message content.
    data: :class:`dict`
        Everything Bisim returned.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.id: int = int(data['id'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.content: str = data.get('content') or ''

    def __repr__(self) -> str:
        return f'<SyncWebhookMessage id={self.id} channel_id={self.channel_id}>'


class SyncWebhook:
    """Represents a synchronous Bisim webhook.

    For an asynchronous counterpart, see :class:`Webhook`.

    .. code-block:: python3

        from bisim import SyncWebhook

        webhook = SyncWebhook.from_url('https://api.bisim.gg/api/webhooks/123/abc...')
        webhook.send('Hello World', username='Foo')

    Attributes
    ------------
    id: :class:`int`
        The webhook's ID.
    token: :class:`str`
        The webhook's token.
    """

    def __init__(self, id: int, token: str, *, api_url: str = 'https://api.bisim.gg/api', timeout: float = 15.0) -> None:
        self.id: int = int(id)
        self.token: str = token
        self._api_url: str = api_url.rstrip('/')
        self._timeout = timeout

    def __repr__(self) -> str:
        return f'<SyncWebhook id={self.id!r}>'

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f'{self._api_url}/webhooks/{self.id}/{self.token}'

    @classmethod
    def partial(cls, id: int, token: str, *, session: Any = utils.MISSING, bot_token: Optional[str] = None) -> SyncWebhook:
        """Creates a partial :class:`SyncWebhook` from an ID and a token."""
        return cls(id, token)

    @classmethod
    def from_url(cls, url: str, *, session: Any = utils.MISSING, bot_token: Optional[str] = None) -> SyncWebhook:
        """Creates a partial :class:`SyncWebhook` from a webhook URL.

        Raises
        -------
        ValueError
            The URL is invalid.
        """
        match = _WEBHOOK_URL_RE.search(url)
        if match is None:
            raise ValueError('Invalid webhook URL given.')
        return cls(int(match.group('id')), match.group('token'), api_url=match.group('base'))

    def send(
        self,
        content: str = utils.MISSING,
        *,
        username: str = utils.MISSING,
        avatar_url: Any = utils.MISSING,
        tts: bool = False,
        file: Any = utils.MISSING,
        files: Any = utils.MISSING,
        embed: Embed = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        allowed_mentions: Any = utils.MISSING,
        thread: Any = utils.MISSING,
        thread_name: str = utils.MISSING,
        wait: bool = False,
        suppress_embeds: bool = False,
        silent: bool = False,
        view: Any = utils.MISSING,
        poll: Any = utils.MISSING,
    ) -> Optional[SyncWebhookMessage]:
        """Sends a message using the webhook.

        Takes the same parameters as :meth:`Webhook.send`, with the same
        Bisim limits (no files, views, threads or polls).

        Returns
        ---------
        Optional[:class:`SyncWebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.
        """
        if file is not utils.MISSING or files is not utils.MISSING:
            raise NotSupported('Sending files through a webhook')
        if thread is not utils.MISSING or thread_name is not utils.MISSING:
            raise NotSupported('Threads')
        if view is not utils.MISSING and view is not None:
            raise NotSupported('Components on webhook messages')
        if poll is not utils.MISSING and poll is not None:
            raise NotSupported('Polls through a webhook')

        from ..abc import _embeds_payload

        payload: Dict[str, Any] = {}
        if content is not utils.MISSING and content is not None:
            payload['content'] = str(content)
        built = _embeds_payload(embed if embed is not utils.MISSING else None, embeds if embeds is not utils.MISSING else None)
        if built:
            payload['embeds'] = built
        if username is not utils.MISSING and username:
            payload['username'] = username

        url = self.url + ('?wait=true' if wait else '')
        body = json.dumps(payload).encode('utf-8')
        for tries in range(5):
            request = urllib.request.Request(
                url, data=body, method='POST', headers={'Content-Type': 'application/json', 'User-Agent': 'BisimBot (bisim.py)'}
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    text = response.read().decode('utf-8')
                    if wait and text:
                        return SyncWebhookMessage(json.loads(text))
                    return None
            except urllib.error.HTTPError as exc:
                text = exc.read().decode('utf-8', 'replace')
                try:
                    data: Any = json.loads(text) if text else None
                except ValueError:
                    data = text
                if exc.code == 429:
                    retry_after = 1.0
                    if isinstance(data, dict) and data.get('retryAfter') is not None:
                        retry_after = float(data['retryAfter'])
                    elif exc.headers.get('Retry-After'):
                        retry_after = float(exc.headers['Retry-After'])
                    time.sleep(retry_after)
                    continue
                if exc.code in (500, 502, 503, 504) and tries < 4:
                    time.sleep(1 + tries * 2)
                    continue
                response_like = _SyncResponse(exc.code, str(exc.reason))
                if exc.code == 403:
                    raise Forbidden(response_like, data)  # type: ignore
                if exc.code == 404:
                    raise NotFound(response_like, data)  # type: ignore
                if exc.code >= 500:
                    raise BisimServerError(response_like, data)  # type: ignore
                raise HTTPException(response_like, data)  # type: ignore
        raise HTTPException(_SyncResponse(429, 'Too Many Requests'), 'Rate limited too many times')  # type: ignore
