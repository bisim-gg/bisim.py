from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import aiohttp

from . import utils
from .activity import BaseActivity
from .appinfo import AppInfo
from .backoff import ExponentialBackoff
from .channel import (
    CategoryChannel,
    DMChannel,
    GroupChannel,
    PartialMessageable,
    TextChannel,
    VoiceChannel,
    _guild_channel_factory,
    _private_channel_factory,
)
from .emoji import Emoji
from .enums import ChannelType, Status
from .errors import (
    BisimServerError,
    ClientException,
    ConnectionClosed,
    Forbidden,
    GatewayNotFound,
    HTTPException,
    InvalidData,
    LoginFailure,
    NotFound,
    NotSupported,
    PrivilegedIntentsRequired,
)
from .flags import ApplicationFlags, Intents
from .gateway import BisimWebSocket, ReconnectWebSocket
from .guild import Guild
from .http import DEFAULT_API_URL, DEFAULT_CDN_URL, DEFAULT_GATEWAY_URL, HTTPClient
from .invite import Invite
from .member import Member
from .mentions import AllowedMentions
from .object import Object
from .state import ConnectionState
from .sticker import GuildSticker
from .ui.view import View
from .user import ClientUser, User
from .voice_client import VoiceProtocol
from .webhook import Webhook

if TYPE_CHECKING:
    from types import TracebackType

    from typing_extensions import Self

    from .abc import GuildChannel, PrivateChannel, Snowflake, SnowflakeTime
    from .message import Message
    from .soundboard import SoundboardSound

__all__ = ('Client',)

T = TypeVar('T')
Coro = Coroutine[Any, Any, T]
CoroT = TypeVar('CoroT', bound=Callable[..., Coro[Any]])

_log = logging.getLogger(__name__)


def _env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


class _LoopSentinel:
    __slots__ = ()

    def __getattr__(self, attr: str) -> None:
        msg = (
            'loop attribute cannot be accessed in non-async contexts. '
            'Consider using either an asynchronous main function and passing it to asyncio.run or '
            'using asynchronous initialisation hooks such as Client.setup_hook'
        )
        raise AttributeError(msg)


_loop: Any = _LoopSentinel()


class Client:
    r"""Represents a client connection that connects to Bisim.
    This class is used to interact with Bisim's WebSocket and API.

    .. container:: operations

        .. describe:: async with x

            Asynchronously initialises the client and automatically cleans up.

    A number of options can be passed to the :class:`Client`.

    Parameters
    -----------
    intents: :class:`Intents`
        The intents that you want to enable for the session. This is a way of
        disabling and enabling certain gateway events from triggering and being sent.
        Defaults to :meth:`Intents.default`. The privileged ones
        (:attr:`Intents.members`, :attr:`Intents.presences` and
        :attr:`Intents.message_content`) must also be switched on for the
        application at https://bisim.gg/developers, or connecting raises
        :exc:`PrivilegedIntentsRequired`.
    max_messages: Optional[:class:`int`]
        The maximum number of messages to store in the internal message cache.
        This defaults to ``1000``. Passing in ``None`` disables the message cache.
    proxy: Optional[:class:`str`]
        Proxy URL.
    proxy_auth: Optional[:class:`aiohttp.BasicAuth`]
        An object that represents proxy HTTP Basic Authorization.
    application_id: :class:`int`
        The client's application ID. On Bisim it is the bot's user ID, which
        the client learns when it logs in, so it rarely needs to be passed.
    member_cache_flags: :class:`MemberCacheFlags`
        Accepted for compatibility.
    chunk_guilds_at_startup: :class:`bool`
        Indicates if the member list of every server should be loaded when the
        bot connects. This requires :attr:`Intents.members` and defaults to its
        value. Without it, the cache holds the members the bot hears about.
    status: Optional[:class:`.Status`]
        A status to start your presence with upon logging on to Bisim.
    activity: Optional[:class:`.BaseActivity`]
        An activity to start your presence with upon logging on to Bisim.
    allowed_mentions: Optional[:class:`AllowedMentions`]
        Accepted for compatibility.
    heartbeat_timeout: :class:`float`
        The maximum numbers of seconds before timing out and restarting the
        WebSocket in the case of not receiving anything. Defaults to 60 seconds.
    guild_ready_timeout: :class:`float`
        The maximum number of seconds to wait for a server's presence snapshot
        after subscribing to it, with :attr:`Intents.presences` (without it
        there is no snapshot to wait for). Defaults to 2 seconds.
    assume_unsync_clock: :class:`bool`
        Accepted for compatibility.
    enable_debug_events: :class:`bool`
        Whether to enable events that are useful only for debugging gateway related information.

        Right now this involves :func:`on_socket_raw_receive` and :func:`on_socket_event_type`.
        Defaults to ``False``.
    enable_raw_presences: :class:`bool`
        Whether to dispatch :func:`on_raw_presence_update`. Defaults to ``False``.
    http_trace: :class:`aiohttp.TraceConfig`
        The trace configuration to use for tracking HTTP requests the library does using ``aiohttp``.
    max_ratelimit_timeout: Optional[:class:`float`]
        The maximum number of seconds to wait when a non-global rate limit is encountered.
        If a request requires sleeping for more than the seconds passed in, then
        :exc:`~bisim.RateLimited` will be raised. By default, there is no timeout limit.
    connector: Optional[:class:`aiohttp.BaseConnector`]
        The aiohttp connector to use for this client.
    api_url: Optional[:class:`str`]
        Bisim's REST address. Defaults to the ``BISIM_API_URL`` environment
        variable, or ``https://api.bisim.gg/api``. For a local server,
        ``http://localhost:3000/api``.
    gateway_url: Optional[:class:`str`]
        Bisim's gateway address. Defaults to the ``BISIM_GATEWAY_URL``
        environment variable, or ``wss://ws.bisim.gg/ws``. For a local server,
        ``ws://localhost:4000/ws``.
    cdn_url: Optional[:class:`str`]
        Bisim's CDN address. Defaults to the ``BISIM_CDN_URL`` environment
        variable, or ``https://cdn.bisim.gg``.

    Attributes
    -----------
    ws
        The websocket gateway the client is currently connected to. Could be ``None``.
    """

    def __init__(self, *, intents: Intents = utils.MISSING, **options: Any) -> None:
        self.loop: asyncio.AbstractEventLoop = _loop
        self.ws: BisimWebSocket = None  # type: ignore
        self._listeners: Dict[str, List[Tuple[asyncio.Future[Any], Callable[..., bool]]]] = {}
        self.shard_id: Optional[int] = options.get('shard_id')
        self.shard_count: Optional[int] = options.get('shard_count')
        if self.shard_id is not None or self.shard_count is not None:
            _log.warning('Bisim has no sharding; shard_id and shard_count are ignored.')

        connector: Optional[aiohttp.BaseConnector] = options.get('connector', None)
        proxy: Optional[str] = options.pop('proxy', None)
        proxy_auth: Optional[aiohttp.BasicAuth] = options.pop('proxy_auth', None)
        unsync_clock: bool = options.pop('assume_unsync_clock', True)
        http_trace: Optional[aiohttp.TraceConfig] = options.pop('http_trace', None)
        max_ratelimit_timeout: Optional[float] = options.pop('max_ratelimit_timeout', None)
        api_url = options.pop('api_url', None) or _env('BISIM_API_URL', 'BISIM_API') or DEFAULT_API_URL
        cdn_url = options.pop('cdn_url', None) or _env('BISIM_CDN_URL', 'BISIM_CDN') or DEFAULT_CDN_URL
        self.gateway_url: str = options.pop('gateway_url', None) or _env('BISIM_GATEWAY_URL', 'BISIM_WS') or DEFAULT_GATEWAY_URL

        self.http: HTTPClient = HTTPClient(
            None,
            connector,
            proxy=proxy,
            proxy_auth=proxy_auth,
            unsync_clock=unsync_clock,
            http_trace=http_trace,
            max_ratelimit_timeout=max_ratelimit_timeout,
            api_url=api_url,
            cdn_url=cdn_url,
        )

        self._handlers: Dict[str, Callable[..., None]] = {
            'ready': self._handle_ready,
        }

        self._hooks: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

        self._enable_debug_events: bool = options.pop('enable_debug_events', False)
        self._connection: ConnectionState = self._get_state(intents=intents, **options)
        self._connection._get_websocket = self._get_websocket
        self._connection._get_client = lambda: self
        self._closing_task: Optional[asyncio.Task[None]] = None
        self._closed: bool = False
        self._ready: asyncio.Event = utils.MISSING
        self._application: Optional[AppInfo] = None

    async def __aenter__(self) -> Self:
        await self._async_setup_hook()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self._closing_task:
            await self._closing_task
        else:
            await self.close()

    # internals

    def _get_websocket(self, guild_id: Optional[int] = None, *, shard_id: Optional[int] = None) -> Optional[BisimWebSocket]:
        return self.ws

    def _get_state(self, **options: Any) -> ConnectionState:
        return ConnectionState(dispatch=self.dispatch, handlers=self._handlers, hooks=self._hooks, http=self.http, **options)

    def _handle_ready(self) -> None:
        self._ready.set()

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds.

        This could be referred to as the Bisim WebSocket protocol latency.
        """
        ws = self.ws
        return float('nan') if not ws else ws.latency

    def is_ws_ratelimited(self) -> bool:
        """:class:`bool`: Whether the websocket is currently rate limited."""
        if self.ws:
            return self.ws.is_ratelimited()
        return False

    @property
    def user(self) -> Optional[ClientUser]:
        """Optional[:class:`.ClientUser`]: Represents the connected client. ``None`` if not logged in."""
        return self._connection.user

    @property
    def guilds(self) -> Sequence[Guild]:
        """Sequence[:class:`.Guild`]: The guilds that the connected client is a member of."""
        return self._connection.guilds

    @property
    def emojis(self) -> Sequence[Emoji]:
        """Sequence[:class:`.Emoji`]: The emojis that the connected client has."""
        return self._connection.emojis

    @property
    def stickers(self) -> Sequence[GuildSticker]:
        """Sequence[:class:`.GuildSticker`]: The stickers that the connected client has."""
        return self._connection.stickers

    @property
    def soundboard_sounds(self) -> List[SoundboardSound]:
        """List[:class:`.SoundboardSound`]: The soundboard sounds the library has seen, in every server.

        Bisim does not send the sounds when the bot connects: see
        :attr:`Guild.soundboard_sounds`.
        """
        return [sound for guild in self.guilds for sound in guild.soundboard_sounds]

    @property
    def cached_messages(self) -> Sequence[Message]:
        """Sequence[:class:`.Message`]: Read-only list of messages the connected client has cached."""
        return utils.SequenceProxy(self._connection._messages or [])

    @property
    def private_channels(self) -> Sequence[PrivateChannel]:
        """Sequence[:class:`.abc.PrivateChannel`]: The private channels that the connected client is participating on."""
        return self._connection.private_channels

    @property
    def voice_clients(self) -> List[VoiceProtocol]:
        """List[:class:`.VoiceProtocol`]: Represents a list of voice connections.

        These are usually :class:`.VoiceClient` instances.
        """
        return self._connection.voice_clients

    @property
    def application_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The client's application ID (the bot's user ID on Bisim)."""
        return self._connection.application_id

    @property
    def application_flags(self) -> ApplicationFlags:
        """:class:`~bisim.ApplicationFlags`: The client's application flags."""
        return ApplicationFlags._from_value(0)

    @property
    def application(self) -> Optional[AppInfo]:
        """Optional[:class:`~bisim.AppInfo`]: The client's application info, once fetched."""
        return self._application

    def is_ready(self) -> bool:
        """:class:`bool`: Specifies if the client's internal cache is ready for use."""
        return self._ready is not utils.MISSING and self._ready.is_set()

    async def _run_event(self, coro: Callable[..., Coroutine[Any, Any, Any]], event_name: str, *args: Any, **kwargs: Any) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception:
            try:
                await self.on_error(event_name, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(
        self, coro: Callable[..., Coroutine[Any, Any, Any]], event_name: str, *args: Any, **kwargs: Any
    ) -> asyncio.Task[None]:
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        return self.loop.create_task(wrapped, name=f'bisim: {event_name}')

    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        _log.debug('Dispatching event %s', event)
        method = 'on_' + event

        listeners = self._listeners.get(event)
        if listeners:
            removed = []
            for i, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(i)
                    continue

                try:
                    result = condition(*args)
                except Exception as exc:
                    future.set_exception(exc)
                    removed.append(i)
                else:
                    if result:
                        if len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(i)

            if len(removed) == len(listeners):
                self._listeners.pop(event)
            else:
                for idx in reversed(removed):
                    del listeners[idx]

        try:
            coro = getattr(self, method)
        except AttributeError:
            pass
        else:
            self._schedule_event(coro, method, *args, **kwargs)

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        """|coro|

        The default error handler provided by the client.

        By default this logs to the library logger, however it could be
        overridden to have a different implementation.
        Check :func:`~bisim.on_error` for more details.
        """
        _log.exception('Ignoring exception in %s', event_method)

    # hooks

    async def _call_before_identify_hook(self, shard_id: Optional[int], *, initial: bool = False) -> None:
        await self.before_identify_hook(shard_id, initial=initial)

    async def before_identify_hook(self, shard_id: Optional[int], *, initial: bool = False) -> None:
        """|coro|

        A hook that is called before connecting to the gateway. Kept for
        compatibility; the default implementation does nothing.
        """
        pass

    async def _async_setup_hook(self) -> None:
        loop = asyncio.get_running_loop()
        self.loop = loop
        self.http.loop = loop
        self._connection.loop = loop

        self._ready = asyncio.Event()

    async def setup_hook(self) -> None:
        """|coro|

        A coroutine to be called to setup the bot, by default this is blank.

        To perform asynchronous setup after the bot is logged in but before
        it has connected to the Websocket, overwrite this coroutine.

        This is only called once, in :meth:`login`, and will be called before
        any events are dispatched, making it a better solution than doing such
        setup in the :func:`~bisim.on_ready` event.

        .. warning::

            Since this is called *before* the websocket connection is made therefore
            anything that waits for the websocket will deadlock, this includes things
            like :meth:`wait_for` and :meth:`wait_until_ready`.
        """
        pass

    # login state management

    async def login(self, token: str) -> None:
        """|coro|

        Logs in the client with the specified credentials and
        calls the :meth:`setup_hook`.


        Parameters
        -----------
        token: :class:`str`
            The bot token (Settings, Applications, in Bisim).

        Raises
        ------
        LoginFailure
            The wrong credentials are passed.
        HTTPException
            An unknown HTTP related error occurred,
            usually when it isn't 200 or the known incorrect credentials
            passing status code.
        """

        _log.info('logging in using static token')

        if self.loop is _loop:
            await self._async_setup_hook()

        if not isinstance(token, str):
            raise TypeError(f'expected token to be a str, received {token.__class__.__name__} instead')

        token = token.strip()
        if token.lower().startswith('bot '):
            token = token[4:].strip()

        data = await self.http.static_login(token)
        self._connection._update_self(data)
        await self.setup_hook()

    async def connect(self, *, reconnect: bool = True) -> None:
        """|coro|

        Creates a websocket connection and lets the websocket listen
        to messages from Bisim. This is a loop that runs the entire
        event system and miscellaneous aspects of the library. Control
        is not resumed until the WebSocket connection is terminated.

        Parameters
        -----------
        reconnect: :class:`bool`
            If we should attempt reconnecting, either due to internet
            failure or a specific failure on Bisim's part.

        Raises
        -------
        GatewayNotFound
            If the gateway to connect to Bisim is not found. Usually if this
            is thrown then there is a Bisim API outage.
        ConnectionClosed
            The websocket connection has been terminated.
        PrivilegedIntentsRequired
            The bot asked for privileged intents that its application has not
            switched on (close code 4014).
        """

        backoff = ExponentialBackoff()
        initial = True
        while not self.is_closed():
            try:
                await self._call_before_identify_hook(None, initial=initial)
                coro = BisimWebSocket.from_client(self, initial=initial)
                self.ws = await asyncio.wait_for(coro, timeout=60.0)
                self._connection._start_bootstrap(self.ws, initial=initial)
                initial = False
                backoff = ExponentialBackoff()
                while True:
                    await self.ws.poll_event()
            except ReconnectWebSocket as e:
                _log.debug('Got a request to %s the websocket.', e.op)
                self._connection._cancel_bootstrap()
                self.dispatch('disconnect')
                if self.is_closed():
                    return
                continue
            except (
                OSError,
                HTTPException,
                GatewayNotFound,
                ConnectionClosed,
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as exc:
                self._connection._cancel_bootstrap()
                self.dispatch('disconnect')
                # The intents were refused (4013 invalid, 4014 not allowed):
                # the same pass would be refused again, so give up.
                if isinstance(exc, ConnectionClosed) and exc.code in (4013, 4014):
                    await self.close()
                    if exc.code == 4014:
                        raise PrivilegedIntentsRequired(exc.shard_id) from None
                    raise

                if not reconnect:
                    await self.close()
                    if isinstance(exc, ConnectionClosed) and exc.code == 1000:
                        return
                    raise

                if self.is_closed():
                    return

                # A refused pass means the token no longer works.
                if isinstance(exc, HTTPException) and exc.status == 401:
                    raise LoginFailure('The bot token is no longer valid.') from exc
                if isinstance(exc, Forbidden):
                    raise

                retry = backoff.delay()
                _log.exception('Attempting a reconnect in %.2fs', retry)
                await asyncio.sleep(retry)

    async def close(self) -> None:
        """|coro|

        Closes the connection to Bisim.
        """
        if self._closing_task:
            return await self._closing_task

        async def _close() -> None:
            self._closed = True
            self._connection._cancel_bootstrap()

            await self._connection.close_voice_clients()

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            translator = self._connection._translator
            if translator is not None:
                await translator.unload()

            await self.http.close()

            if self._ready is not utils.MISSING:
                self._ready.clear()

            self.loop = _loop

        self._closing_task = asyncio.create_task(_close())
        await self._closing_task

    def clear(self) -> None:
        """Clears the internal state of the bot.

        After this, the bot can be considered "re-opened", i.e. :meth:`is_closed`
        and :meth:`is_ready` both return ``False`` along with the bot's internal
        cache cleared.
        """
        self._closed = False
        self._closing_task = None
        self._ready.clear()
        self._connection.clear()
        self.http.clear()

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        """|coro|

        A shorthand coroutine for :meth:`login` + :meth:`connect`.

        Parameters
        -----------
        token: :class:`str`
            The bot token.
        reconnect: :class:`bool`
            If we should attempt reconnecting, either due to internet
            failure or a specific failure on Bisim's part.

        Raises
        -------
        TypeError
            An unexpected keyword argument was received.
        """
        await self.login(token)
        await self.connect(reconnect=reconnect)

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: Optional[logging.Handler] = utils.MISSING,
        log_formatter: logging.Formatter = utils.MISSING,
        log_level: int = utils.MISSING,
        root_logger: bool = False,
    ) -> None:
        """A blocking call that abstracts away the event loop
        initialisation from you.

        If you want more control over the event loop then this
        function should not be used. Use :meth:`start` coroutine
        or :meth:`connect` + :meth:`login`.

        This function also sets up the logging library to make it easier
        for beginners to know what is going on with the library. For more
        advanced users, this can be disabled by passing ``None`` to
        the ``log_handler`` parameter.

        .. warning::

            This function must be the last function to call due to the fact that it
            is blocking. That means that registration of events or anything being
            called after this function call will not execute until it returns.

        Parameters
        -----------
        token: :class:`str`
            The bot token.
        reconnect: :class:`bool`
            If we should attempt reconnecting, either due to internet
            failure or a specific failure on Bisim's part.
        log_handler: Optional[:class:`logging.Handler`]
            The log handler to use for the library's logger. If this is ``None``
            then the library will not set up anything logging related. Logging
            will still work if ``None`` is passed, though it is your responsibility
            to set it up.

            The default log handler if not provided is :class:`logging.StreamHandler`.
        log_formatter: :class:`logging.Formatter`
            The formatter to use with the given log handler. If not provided then it
            defaults to a colour based logging formatter (if available).
        log_level: :class:`int`
            The default log level for the library's logger. This is only applied if the
            ``log_handler`` parameter is not ``None``. Defaults to ``logging.INFO``.
        root_logger: :class:`bool`
            Whether to set up the root logger rather than the library logger.
            By default, only the library logger (``'bisim'``) is set up. If this
            is set to ``True`` then the root logger is set up as well.

            Defaults to ``False``.
        """

        async def runner() -> None:
            async with self:
                await self.start(token, reconnect=reconnect)

        if log_handler is not None:
            utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            return

    # properties

    def is_closed(self) -> bool:
        """:class:`bool`: Indicates if the websocket connection is closed."""
        return self._closed

    @property
    def activity(self) -> Optional[BaseActivity]:
        """Optional[:class:`.BaseActivity`]: The activity being used upon logging in."""
        return self._connection._activity

    @activity.setter
    def activity(self, value: Optional[BaseActivity]) -> None:
        if value is None:
            self._connection._activity = None
        elif isinstance(value, BaseActivity):
            self._connection._activity = value
        else:
            raise TypeError('activity must derive from BaseActivity.')

    @property
    def status(self) -> Status:
        """:class:`.Status`: The status being used upon logging on to Bisim."""
        if self._connection._status in set(state.value for state in Status):
            return Status(self._connection._status)
        return Status.online

    @status.setter
    def status(self, value: Status) -> None:
        if value is Status.offline:
            self._connection._status = 'invisible'
        elif isinstance(value, Status):
            self._connection._status = str(value)
        else:
            raise TypeError('status must derive from Status.')

    @property
    def allowed_mentions(self) -> Optional[AllowedMentions]:
        """Optional[:class:`~bisim.AllowedMentions`]: The allowed mention configuration (accepted for compatibility)."""
        return self._connection.allowed_mentions

    @allowed_mentions.setter
    def allowed_mentions(self, value: Optional[AllowedMentions]) -> None:
        if value is None or isinstance(value, AllowedMentions):
            self._connection.allowed_mentions = value
        else:
            raise TypeError(f'allowed_mentions must be AllowedMentions not {value.__class__.__name__}')

    @property
    def intents(self) -> Intents:
        """:class:`~bisim.Intents`: The intents configured for this connection."""
        return self._connection.intents

    # helpers/getters

    @property
    def users(self) -> List[User]:
        """List[:class:`~bisim.User`]: Returns a list of all the users the bot can see."""
        return list(self._connection._users.values())

    def get_channel(self, id: int, /) -> Optional[Union[GuildChannel, PrivateChannel]]:
        """Returns a channel with the given ID.

        Parameters
        -----------
        id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[Union[:class:`.abc.GuildChannel`, :class:`.abc.PrivateChannel`]]
            The returned channel or ``None`` if not found.
        """
        return self._connection.get_channel(id)

    def get_partial_messageable(
        self, id: int, *, guild_id: Optional[int] = None, type: Optional[ChannelType] = None
    ) -> PartialMessageable:
        """Returns a partial messageable with the given channel ID.

        This is useful if you have a channel_id but don't want to do an API call
        to send messages to it.

        Parameters
        -----------
        id: :class:`int`
            The channel ID to create a partial messageable for.
        guild_id: Optional[:class:`int`]
            The optional guild ID to create a partial messageable for.
        type: Optional[:class:`.ChannelType`]
            The underlying channel type for the partial messageable.

        Returns
        --------
        :class:`.PartialMessageable`
            The partial messageable
        """
        return PartialMessageable(state=self._connection, id=id, guild_id=guild_id, type=type)

    def get_stage_instance(self, id: int, /) -> None:
        """Always ``None``: Bisim has no stage channels."""
        return None

    def get_guild(self, id: int, /) -> Optional[Guild]:
        """Returns a guild with the given ID.

        Parameters
        -----------
        id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`.Guild`]
            The guild or ``None`` if not found.
        """
        return self._connection._get_guild(id)

    def get_user(self, id: int, /) -> Optional[User]:
        """Returns a user with the given ID.

        Parameters
        -----------
        id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`~bisim.User`]
            The user or ``None`` if not found.
        """
        return self._connection.get_user(id)

    def get_emoji(self, id: int, /) -> Optional[Emoji]:
        """Returns an emoji with the given ID.

        Parameters
        -----------
        id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`.Emoji`]
            The custom emoji or ``None`` if not found.
        """
        return self._connection.get_emoji(id)

    def get_sticker(self, id: int, /) -> Optional[GuildSticker]:
        """Returns a guild sticker with the given ID.

        Returns
        --------
        Optional[:class:`.GuildSticker`]
            The sticker or ``None`` if not found.
        """
        return self._connection._get_sticker(id)

    def get_soundboard_sound(self, id: int, /) -> Optional[SoundboardSound]:
        """Returns a soundboard sound with the given ID, if the library has seen it
        (see :attr:`Guild.soundboard_sounds`).

        Parameters
        ----------
        id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`.SoundboardSound`]
            The soundboard sound or ``None`` if not found.
        """
        for guild in self.guilds:
            sound = guild.get_soundboard_sound(id)
            if sound is not None:
                return sound
        return None

    def get_all_channels(self) -> Generator[GuildChannel, None, None]:
        """A generator that retrieves every :class:`.abc.GuildChannel` the client can 'access'.

        This is equivalent to: ::

            for guild in client.guilds:
                for channel in guild.channels:
                    yield channel

        Yields
        ------
        :class:`.abc.GuildChannel`
            A channel the client can 'access'.
        """
        for guild in self.guilds:
            yield from guild.channels

    def get_all_members(self) -> Generator[Member, None, None]:
        """Returns a generator with every :class:`.Member` the client can see.

        This is equivalent to: ::

            for guild in client.guilds:
                for member in guild.members:
                    yield member

        Yields
        ------
        :class:`.Member`
            A member the client can see.
        """
        for guild in self.guilds:
            yield from guild.members

    # listeners/waiters

    async def wait_until_ready(self) -> None:
        """|coro|

        Waits until the client's internal cache is all ready.

        .. warning::

            Calling this inside :meth:`setup_hook` can lead to a deadlock.
        """
        if self._ready is not utils.MISSING:
            await self._ready.wait()
        else:
            raise RuntimeError(
                'Client has not been properly initialised. '
                'Please use the login method or asynchronous context manager before calling this method'
            )

    def wait_for(
        self,
        event: str,
        /,
        *,
        check: Optional[Callable[..., bool]] = None,
        timeout: Optional[float] = None,
    ) -> Coro[Any]:
        """|coro|

        Waits for a WebSocket event to be dispatched.

        This could be used to wait for a user to reply to a message,
        or to react to a message, or to edit a message in a self-contained
        way.

        The ``timeout`` parameter is passed onto :func:`asyncio.wait_for`. By default,
        it does not timeout. Note that this does propagate the
        :exc:`asyncio.TimeoutError` for you in case of timeout and is provided for
        ease of use.

        In case the event returns multiple arguments, a :class:`tuple` containing those
        arguments is returned instead. Please check the
        :ref:`documentation <bisim-api-events>` for a list of events and their
        parameters.

        This function returns the **first event that meets the requirements**.

        Examples
        ---------

        Waiting for a user reply: ::

            @client.event
            async def on_message(message):
                if message.content.startswith('$greet'):
                    channel = message.channel
                    await channel.send('Say hello!')

                    def check(m):
                        return m.content == 'hello' and m.channel == channel

                    msg = await client.wait_for('message', check=check)
                    await channel.send(f'Hello {msg.author}!')

        Parameters
        ------------
        event: :class:`str`
            The event name, similar to the :ref:`event reference <bisim-api-events>`,
            but without the ``on_`` prefix, to wait for.
        check: Optional[Callable[..., :class:`bool`]]
            A predicate to check what to wait for. The arguments must meet the
            parameters of the event being waited for.
        timeout: Optional[:class:`float`]
            The number of seconds to wait before timing out and raising
            :exc:`asyncio.TimeoutError`.

        Raises
        -------
        asyncio.TimeoutError
            If a timeout is provided and it was reached.

        Returns
        --------
        Any
            Returns no arguments, a single argument, or a :class:`tuple` of multiple
            arguments that mirrors the parameters passed in the
            :ref:`event reference <bisim-api-events>`.
        """

        future = self.loop.create_future()
        if check is None:

            def _check(*args: Any) -> bool:
                return True

            check = _check

        ev = event.lower()
        try:
            listeners = self._listeners[ev]
        except KeyError:
            listeners = []
            self._listeners[ev] = listeners

        listeners.append((future, check))
        return asyncio.wait_for(future, timeout)

    # event registration

    def event(self, coro: CoroT, /) -> CoroT:
        """A decorator that registers an event to listen to.

        You can find more info about the events on the :ref:`documentation below <bisim-api-events>`.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Example
        ---------

        .. code-block:: python3

            @client.event
            async def on_ready():
                print('Ready!')

        Raises
        --------
        TypeError
            The coroutine passed is not actually a coroutine.
        """

        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('event registered must be a coroutine function')

        setattr(self, coro.__name__, coro)
        _log.debug('%s has successfully been registered as an event', coro.__name__)
        return coro

    async def change_presence(
        self,
        *,
        activity: Optional[BaseActivity] = None,
        status: Optional[Status] = None,
    ) -> None:
        """|coro|

        Changes the client's presence.

        A :class:`Game`, :class:`Streaming` or :class:`Activity` becomes the
        bot's activity ("Playing ...", "Watching ..."); a
        :class:`CustomActivity` becomes its custom status.

        Example
        ---------

        .. code-block:: python3

            game = bisim.Game("with the API")
            await client.change_presence(status=bisim.Status.idle, activity=game)

        Parameters
        ----------
        activity: Optional[:class:`.BaseActivity`]
            The activity being done. ``None`` if no currently active activity is done.
        status: Optional[:class:`.Status`]
            Indicates what status to change to. If ``None``, then
            :attr:`.Status.online` is used.

        Raises
        ------
        TypeError
            If the ``activity`` parameter is not the proper type.
        """

        if status is None:
            status_str = 'online'
            status = Status.online
        elif status is Status.offline:
            status_str = 'invisible'
            status = Status.offline
        else:
            status_str = str(status)

        if self.ws is not None:
            await self.ws.change_presence(activity=activity, status=status_str)
        self._connection._activity = activity
        self._connection._status = status_str

        for guild in self._connection.guilds:
            me = guild.me
            if me is None:
                continue
            me.activities = (activity,) if activity is not None else ()  # type: ignore
            me._status = 'offline' if status_str == 'invisible' else status_str

    # Guild stuff

    async def fetch_guilds(
        self,
        *,
        limit: Optional[int] = 200,
        before: Optional[SnowflakeTime] = None,
        after: Optional[SnowflakeTime] = None,
        with_counts: bool = True,
    ) -> AsyncIterator[Guild]:
        """Retrieves an :term:`asynchronous iterator` that enables receiving your guilds.

        .. note::

            This method is an API call. For general usage, consider :attr:`guilds` instead.

        Examples
        ---------

        Usage ::

            async for guild in client.fetch_guilds(limit=150):
                print(guild.name)

        Flattening into a list ::

            guilds = [guild async for guild in client.fetch_guilds(limit=150)]
            # guilds is now a list of Guild...

        All parameters are optional.

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of guilds to retrieve.
            If ``None``, it retrieves every guild you have access to. Defaults to ``200``.
        before: Union[:class:`.abc.Snowflake`, :class:`datetime.datetime`]
            Retrieves guilds before this date or object.
        after: Union[:class:`.abc.Snowflake`, :class:`datetime.datetime`]
            Retrieve guilds after this date or object.
        with_counts: :class:`bool`
            Accepted for compatibility.

        Raises
        ------
        HTTPException
            Getting the guilds failed.

        Yields
        --------
        :class:`.Guild`
            The guild with the guild data parsed.
        """

        def as_id(value: Any, high: bool) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, datetime.datetime):
                return utils.time_snowflake(value, high=high)
            return value.id

        before_id = as_id(before, False)
        after_id = as_id(after, True)
        data = await self.http.get_guilds()
        rows = sorted(data or [], key=lambda d: int(d['id']))
        if before_id is not None:
            rows = [r for r in rows if int(r['id']) < before_id]
            rows.reverse()
        if after_id is not None:
            rows = [r for r in rows if int(r['id']) > after_id]
        count = 0
        for raw in rows:
            yield Guild(state=self._connection, data=raw)
            count += 1
            if limit is not None and count >= limit:
                return

    async def fetch_template(self, code: Any) -> Any:
        """|coro|

        Not supported for bots on Bisim.
        """
        raise NotSupported('Server templates from a bot')

    async def fetch_guild(self, guild_id: int, /, *, with_counts: bool = True) -> Guild:
        """|coro|

        Retrieves a :class:`.Guild` from an ID.

        .. note::

            This method is an API call. For general usage, consider :meth:`get_guild` instead.

        Parameters
        -----------
        guild_id: :class:`int`
            The guild's ID to fetch from.
        with_counts: :class:`bool`
            Accepted for compatibility.

        Raises
        ------
        NotFound
            The guild doesn't exist or you got no access to it.
        HTTPException
            Getting the guild failed.

        Returns
        --------
        :class:`.Guild`
            The guild from the ID.
        """
        data = await self.http.get_guild(guild_id)
        return Guild(data=data, state=self._connection)

    async def create_guild(self, *, name: str, **kwargs: Any) -> Guild:
        """|coro|

        Not supported on Bisim: a bot cannot create a server.
        """
        raise NotSupported('Creating a server as a bot')

    async def fetch_stage_instance(self, channel_id: int, /) -> Any:
        """|coro|

        Not supported on Bisim (no stage channels).
        """
        raise NotSupported('Stage channels')

    # Invite management

    async def fetch_invite(
        self,
        url: Union[Invite, str],
        *,
        with_counts: bool = True,
        with_expiration: bool = True,
        scheduled_event_id: Optional[int] = None,
    ) -> Invite:
        """|coro|

        Gets an :class:`.Invite` from a bisim.gg URL or ID.

        Parameters
        -----------
        url: Union[:class:`.Invite`, :class:`str`]
            The Bisim invite ID or URL (must be a bisim.gg URL).
        with_counts: :class:`bool`
            Accepted for compatibility (Bisim always includes the counts).
        with_expiration: :class:`bool`
            Accepted for compatibility.
        scheduled_event_id: Optional[:class:`int`]
            Not supported on Bisim.

        Raises
        -------
        NotFound
            The invite has expired or is invalid.
        HTTPException
            Getting the invite failed.

        Returns
        --------
        :class:`.Invite`
            The invite from the URL/ID.
        """
        if scheduled_event_id is not None:
            raise NotSupported('Scheduled events')
        resolved = utils.resolve_invite(url)
        data = await self.http.get_invite(resolved.code)
        return Invite.from_incomplete(state=self._connection, data=data) if 'guildId' in data else Invite(state=self._connection, data=data)

    async def delete_invite(self, invite: Union[Invite, str], /, *, reason: Optional[str] = None) -> Invite:
        """|coro|

        Revokes an :class:`.Invite`, URL, or ID to an invite.

        You must have :attr:`~.Permissions.manage_channels` in
        the associated guild to do this.

        Parameters
        ----------
        invite: Union[:class:`.Invite`, :class:`str`]
            The invite to revoke.
        reason: Optional[:class:`str`]
            The reason for deleting the invite. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to revoke invites.
        NotFound
            The invite is invalid or expired.
        HTTPException
            Revoking the invite failed.
        """
        if isinstance(invite, Invite):
            return await invite.delete(reason=reason)
        resolved = utils.resolve_invite(invite)
        found = await self.fetch_invite(resolved.code)
        return await found.delete(reason=reason)

    # Miscellaneous stuff

    async def fetch_widget(self, guild_id: int, /) -> Any:
        """|coro|

        Not supported on Bisim (no server widgets).
        """
        raise NotSupported('Server widgets')

    async def application_info(self) -> AppInfo:
        """|coro|

        Retrieves the bot's application information.

        Raises
        -------
        HTTPException
            Retrieving the information failed somehow.

        Returns
        --------
        :class:`.AppInfo`
            The bot's application information.
        """
        try:
            data = await self.http.application_info()
        except (NotFound, Forbidden):
            if self.application_id is None:
                raise
            data = await self.http.get_application(self.application_id)
        self._application = AppInfo(self._connection, data)
        return self._application

    async def fetch_user(self, user_id: int, /) -> User:
        """|coro|

        Retrieves a :class:`~bisim.User` based on their ID.
        You do not have to share any guilds with the user to get this information,
        however many operations do require that you do.

        .. note::

            This method is an API call. If you have :attr:`bisim.Intents.members` and member cache enabled, consider :meth:`get_user` instead.

        Parameters
        -----------
        user_id: :class:`int`
            The user's ID to fetch from.

        Raises
        -------
        NotFound
            A user with this ID does not exist.
        HTTPException
            Fetching the user failed.

        Returns
        --------
        :class:`~bisim.User`
            The user you requested.
        """
        data = await self.http.get_user(user_id)
        return User(state=self._connection, data=data)

    async def fetch_channel(self, channel_id: int, /) -> Union[GuildChannel, PrivateChannel]:
        """|coro|

        Retrieves a :class:`.abc.GuildChannel` or :class:`.abc.PrivateChannel` with the specified ID.

        .. note::

            This method is an API call. For general usage, consider :meth:`get_channel` instead.

        Raises
        -------
        InvalidData
            An unknown channel type was received from Bisim.
        HTTPException
            Retrieving the channel failed.
        NotFound
            Invalid Channel ID.
        Forbidden
            You do not have permission to fetch this channel.

        Returns
        --------
        Union[:class:`.abc.GuildChannel`, :class:`.abc.PrivateChannel`]
            The channel from the ID.
        """
        data = await self.http.get_channel(channel_id)

        factory, ch_type = _guild_channel_factory(data.get('type'))
        if factory is None:
            factory, ch_type = _private_channel_factory(data.get('type'))
            if factory is None:
                raise InvalidData('Unknown channel type {type} for channel ID {id}.'.format_map(data))
            if factory is DMChannel:
                return self._connection.add_dm_channel(data)
            channel = GroupChannel(me=self.user, state=self._connection, data=data)  # type: ignore
            self._connection._add_private_channel(channel)
            return channel

        guild_id = int(data['guildId'])
        guild = self._connection._get_guild(guild_id) or Object(id=guild_id)
        if isinstance(guild, Object):
            guild = await self.fetch_guild(guild_id)
        return factory(guild=guild, state=self._connection, data=data)  # type: ignore

    async def fetch_webhook(self, webhook_id: int, /) -> Webhook:
        """|coro|

        Retrieves a :class:`.Webhook` with the specified ID.

        Raises
        --------
        HTTPException
            Retrieving the webhook failed.
        NotFound
            Invalid webhook ID.
        Forbidden
            You do not have permission to fetch this webhook.

        Returns
        ---------
        :class:`.Webhook`
            The webhook you requested.
        """
        data = await self.http.get_webhook(webhook_id)
        return Webhook.from_state(data, state=self._connection)

    async def fetch_sticker(self, sticker_id: int, /) -> GuildSticker:
        """|coro|

        Obtains a sticker from the servers the bot is in.

        Raises
        --------
        NotFound
            Invalid sticker ID.

        Returns
        --------
        :class:`.GuildSticker`
            The sticker you requested.
        """
        sticker = self._connection._get_sticker(sticker_id)
        if sticker is not None:
            return sticker
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown sticker')  # type: ignore

    async def fetch_premium_sticker_packs(self) -> List[Any]:
        """|coro|

        Not supported on Bisim (no sticker packs).
        """
        raise NotSupported('Sticker packs')

    async def fetch_skus(self) -> List[Any]:
        """|coro|

        Not supported on Bisim (no monetisation).
        """
        raise NotSupported('SKUs')

    async def create_dm(self, user: Snowflake) -> DMChannel:
        """|coro|

        Creates a :class:`.DMChannel` with this user.

        This should be rarely called, as this is done transparently for most
        people.

        Bisim opens a DM when the person shares a server with the bot and
        their settings allow it.

        Parameters
        -----------
        user: :class:`~bisim.abc.Snowflake`
            The user to create a DM with.

        Returns
        -------
        :class:`.DMChannel`
            The channel that was created.
        """
        state = self._connection
        found = state._get_private_channel_by_user(user.id)
        if found:
            return found

        data = await state.http.start_private_message(user.id)
        return state.add_dm_channel(data)

    def add_dynamic_items(self, *items: Any) -> None:
        """Not supported yet; kept so the name exists."""
        raise NotSupported('Dynamic items')

    def add_view(self, view: View, *, message_id: Optional[int] = None) -> None:
        """Registers a :class:`~bisim.ui.View` for persistent listening.

        This method should be used for when a view is comprised of components
        that last longer than the lifecycle of the program.

        Parameters
        ------------
        view: :class:`bisim.ui.View`
            The view to register for dispatching.
        message_id: Optional[:class:`int`]
            The message ID that the view is attached to. This is currently used to
            refresh the view's state during message update events. If not given
            then message update events are not propagated for the view.

        Raises
        -------
        TypeError
            A view was not passed.
        ValueError
            The view is not persistent or is already finished. A persistent view has no timeout
            and all their components have an explicitly provided custom_id.
        """

        if not isinstance(view, View):
            raise TypeError(f'expected an instance of View not {view.__class__.__name__}')

        if not view.is_persistent():
            raise ValueError('View is not persistent. Items need to have a custom_id set and View must have no timeout')

        if view.is_finished():
            raise ValueError('View is already finished.')

        self._connection.store_view(view, message_id)

    @property
    def persistent_views(self) -> Sequence[View]:
        """Sequence[:class:`.View`]: A sequence of persistent views added to the client."""
        return self._connection.persistent_views
