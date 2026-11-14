"""The gateway: Bisim's WebSocket.

Frames are JSON ``{op, t, d}``. The server says HELLO with the heartbeat
interval; the client sends op 2 every interval and gets op 3 back. Op 9
asks the client to reconnect at once (the server is draining). There is no
session to resume: after a reconnect the library loads the servers again.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Union
from urllib.parse import quote

import aiohttp

from . import utils
from .activity import ActivityType, BaseActivity, CustomActivity
from .enums import Status
from .errors import ConnectionClosed

if TYPE_CHECKING:
    from .client import Client
    from .state import ConnectionState

_log = logging.getLogger(__name__)

__all__ = (
    'BisimWebSocket',
    'ReconnectWebSocket',
    'GatewayRatelimiter',
)


class ReconnectWebSocket(Exception):
    """Signals to safely reconnect the websocket."""

    def __init__(self, *, resume: bool = False) -> None:
        self.resume: bool = resume
        self.op: str = 'RESUME' if resume else 'IDENTIFY'


class WebSocketClosure(Exception):
    """Raised inside the read loop when the socket reports that it closed."""

    pass


class GatewayRatelimiter:
    """Keeps sends under the gateway's limit (it closes a client that sends more than 40 frames a second)."""

    def __init__(self, count: int = 30, per: float = 1.0) -> None:
        self.max: int = count
        self.remaining: int = count
        self.window: float = 0.0
        self.per: float = per
        self.lock: asyncio.Lock = asyncio.Lock()

    def get_delay(self) -> float:
        current = time.monotonic()

        if current > self.window + self.per:
            self.remaining = self.max

        if self.remaining == self.max:
            self.window = current

        if self.remaining == 0:
            return self.per - (current - self.window)

        self.remaining -= 1
        return 0.0

    async def block(self) -> None:
        async with self.lock:
            delta = self.get_delay()
            if delta:
                _log.warning('Gateway sends are being held back. Waiting %.2f seconds.', delta)
                await asyncio.sleep(delta)


def _presence_payload(activity: Optional[BaseActivity], status: Optional[Union[Status, str]]) -> Dict[str, Any]:
    if status is None:
        status_value = 'online'
    elif status is Status.offline or status == 'offline':
        status_value = 'invisible'
    else:
        status_value = str(status)

    payload: Dict[str, Any] = {'status': status_value, 'customText': '', 'customEmoji': '', 'expiresAt': 0}
    if activity is None:
        return payload

    kind = getattr(activity, 'type', None)
    if isinstance(activity, CustomActivity) or kind is ActivityType.custom:
        text = getattr(activity, 'name', None) or getattr(activity, 'state', None) or ''
        payload['customText'] = text
        emoji = getattr(activity, 'emoji', None)
        if emoji is not None:
            payload['customEmoji'] = str(emoji)
        expires_at = getattr(activity, 'expires_at', None)
        if expires_at is not None:
            payload['expiresAt'] = int(expires_at.timestamp() * 1000)
        return payload

    payload['activity'] = activity._to_bisim()
    return payload


class BisimWebSocket:
    """Implements a WebSocket for Bisim's gateway.

    Attributes
    -----------
    DISPATCH
        Receive only. Denotes an event to be sent to Bisim, such as READY.
    HELLO
        Receive only. Tells the client the heartbeat interval.
    HEARTBEAT
        Send only. Keeps the presence alive.
    HEARTBEAT_ACK
        Receive only. Confirms receiving of a heartbeat.
    SUBSCRIBE
        Send only. Joins a server's rooms (``{guildId}``).
    RESUME
        Send only. A stub on Bisim: there is no session to resume.
    TYPING
        Send only. Shows the typing indicator in a channel.
    PRESENCE
        Send only. Updates the client's presence.
    RECONNECT
        Receive only. Tells the client to reconnect to a new gateway.
    ERROR
        Receive only. A refused request (a refused subscribe).
    gateway
        The gateway we are currently connected to (without the pass).
    """

    if TYPE_CHECKING:
        _connection: ConnectionState
        _dispatch: Callable[..., Any]
        _parsers: Dict[str, Callable[[Any], None]]

    DISPATCH = 0
    HELLO = 1
    HEARTBEAT = 2
    HEARTBEAT_ACK = 3
    SUBSCRIBE = 4
    RESUME = 5
    TYPING = 6
    PRESENCE = 7
    RECONNECT = 9
    ERROR = 10

    def __init__(self, socket: aiohttp.ClientWebSocketResponse, *, loop: asyncio.AbstractEventLoop) -> None:
        self.socket: aiohttp.ClientWebSocketResponse = socket
        self.loop: asyncio.AbstractEventLoop = loop
        self._dispatch = lambda *args, **kwargs: None
        self._parsers = {}
        self.gateway: str = ''
        self.heartbeat_interval: float = 30.0
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._hello: asyncio.Event = asyncio.Event()
        self._last_send: float = 0.0
        self._last_ack: float = time.perf_counter()
        self._missed_acks: int = 0
        self._latency: float = float('inf')
        self._close_code: Optional[int] = None
        self._rate_limiter: GatewayRatelimiter = GatewayRatelimiter()
        self._enable_debug_events: bool = False
        self._max_receive_timeout: float = 120.0

    @property
    def open(self) -> bool:
        return not self.socket.closed

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds."""
        return self._latency

    def is_ratelimited(self) -> bool:
        return self._rate_limiter.remaining == 0

    @classmethod
    async def from_client(
        cls,
        client: Client,
        *,
        initial: bool = False,
        gateway: Optional[str] = None,
    ) -> BisimWebSocket:
        """Mints a gateway pass, connects, and waits for HELLO."""
        state = client._connection
        application_id = client.application_id or state.self_id
        if application_id is None:
            from .errors import ClientException

            raise ClientException('The client must log in before connecting.')

        data = await client.http.get_bot_gateway(application_id)
        token = data['token']
        base = gateway or client.gateway_url
        joiner = '&' if '?' in base else '?'
        url = f'{base}{joiner}token={quote(token, safe="")}'
        socket = await client.http.ws_connect(url)
        ws = cls(socket, loop=client.loop)

        ws._connection = state
        ws._dispatch = client.dispatch
        ws._parsers = state.parsers
        ws.gateway = base
        ws._enable_debug_events = client._enable_debug_events
        ws._max_receive_timeout = max(state.heartbeat_timeout, 1.0) * 2

        _log.info('Connected to the gateway at %s.', base)

        # HELLO is the first frame; read until it arrives.
        while not ws._hello.is_set():
            await asyncio.wait_for(ws.poll_event(), timeout=30.0)

        await ws.change_presence(activity=state._activity, status=state._status)
        client.dispatch('connect')
        return ws

    def wait_for(
        self,
        event: str,
        predicate: Callable[[Dict[str, Any]], bool],
        result: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> asyncio.Future[Any]:
        """Waits for a DISPATCH'd event that meets the predicate (kept for compatibility)."""
        future: asyncio.Future[Any] = self.loop.create_future()
        return future

    async def _heartbeat_loop(self) -> None:
        try:
            await self.send_heartbeat()
            while not self.socket.closed:
                await asyncio.sleep(self.heartbeat_interval)
                if self._last_ack < self._last_send:
                    self._missed_acks += 1
                    if self._missed_acks >= 2:
                        _log.warning('The gateway stopped answering heartbeats; reconnecting.')
                        await self.close(code=4000)
                        return
                await self.send_heartbeat()
        except asyncio.CancelledError:
            raise
        except (ConnectionResetError, aiohttp.ClientError, RuntimeError):
            _log.debug('Heartbeat failed; the connection is closing.', exc_info=True)

    async def send_heartbeat(self) -> None:
        self._last_send = time.perf_counter()
        await self.send_as_json({'op': self.HEARTBEAT})

    async def received_message(self, msg: Union[str, bytes]) -> None:
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8')

        if self._enable_debug_events:
            self._dispatch('socket_raw_receive', msg)

        frame = utils._from_json(msg)
        op = frame.get('op')
        data = frame.get('d')
        event = frame.get('t')

        if op == self.DISPATCH:
            if not event:
                return
            if self._enable_debug_events:
                self._dispatch('socket_event_type', event)
            parser = self._parsers.get(event)
            if parser is None:
                _log.debug('Unknown event %s.', event)
                return
            try:
                parser(data or {})
            except Exception:
                _log.exception('Handling the %s event failed.', event)
            return

        if op == self.HELLO:
            interval_ms = (data or {}).get('heartbeatIntervalMs') or 30000
            self.heartbeat_interval = float(interval_ms) / 1000.0
            self._hello.set()
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = self.loop.create_task(self._heartbeat_loop(), name='bisim: heartbeat')
            return

        if op == self.HEARTBEAT_ACK:
            now = time.perf_counter()
            self._last_ack = now
            self._missed_acks = 0
            if self._last_send:
                self._latency = now - self._last_send
            return

        if op == self.HEARTBEAT:
            await self.send_heartbeat()
            return

        if op == self.RECONNECT:
            _log.info('The gateway asked to reconnect (it is restarting).')
            await self.close(code=4000)
            raise ReconnectWebSocket()

        if op == self.ERROR:
            message = (data or {}).get('message') if isinstance(data, dict) else None
            _log.debug('The gateway refused a request: %s', message)
            self._connection._on_gateway_error(message)
            return

        _log.debug('Unknown gateway op %s.', op)

    def _can_handle_close(self) -> bool:
        # Bisim's gateway has no close codes that mean "give up": a bad pass is
        # refused before the upgrade, so every close is worth a reconnect.
        return True

    async def poll_event(self) -> None:
        """Polls for a DISPATCH event and handles the general gateway loop.

        Raises
        ------
        ConnectionClosed
            The websocket connection was terminated for unhandled reasons.
        """
        try:
            msg = await self.socket.receive(timeout=self._max_receive_timeout)
            if msg.type is aiohttp.WSMsgType.TEXT:
                await self.received_message(msg.data)
            elif msg.type is aiohttp.WSMsgType.BINARY:
                await self.received_message(msg.data)
            elif msg.type is aiohttp.WSMsgType.ERROR:
                _log.debug('Received error %s', msg)
                raise WebSocketClosure
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSE):
                _log.debug('Received %s', msg)
                raise WebSocketClosure
        except (asyncio.TimeoutError, WebSocketClosure) as e:
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

            if isinstance(e, asyncio.TimeoutError):
                _log.debug('Timed out receiving packet. Attempting a reconnect.')
                raise ReconnectWebSocket() from None

            code = self._close_code or self.socket.close_code
            if self._can_handle_close():
                _log.debug('Websocket closed with %s, attempting a reconnect.', code)
                raise ReconnectWebSocket() from None
            raise ConnectionClosed(self.socket, code=code) from None

    async def send(self, data: str, /) -> None:
        await self._rate_limiter.block()
        await self.socket.send_str(data)

    async def send_as_json(self, data: Any) -> None:
        try:
            await self.send(utils._to_json(data))
        except RuntimeError as exc:
            if not self._can_handle_close():
                raise ConnectionClosed(self.socket) from exc

    async def subscribe_guild(self, guild_id: int) -> None:
        """Sends op 4: join a server's rooms."""
        await self.send_as_json({'op': self.SUBSCRIBE, 'd': {'guildId': str(guild_id)}})

    async def send_typing(self, channel_id: int, guild_id: Optional[int]) -> None:
        """Sends op 6: the typing indicator."""
        await self.send_as_json(
            {'op': self.TYPING, 'd': {'channelId': str(channel_id), 'guildId': str(guild_id) if guild_id else ''}}
        )

    async def change_presence(
        self,
        *,
        activity: Optional[BaseActivity] = None,
        status: Optional[Union[Status, str]] = None,
        since: float = 0.0,
    ) -> None:
        """Sends op 7: the bot's status, custom status and activity."""
        if activity is not None and not isinstance(activity, BaseActivity):
            raise TypeError('activity must derive from BaseActivity.')

        payload = {'op': self.PRESENCE, 'd': _presence_payload(activity, status)}
        sent = utils._to_json(payload)
        _log.debug('Sending "%s" to change status', sent)
        await self.send(sent)

    async def request_chunks(self, *args: Any, **kwargs: Any) -> None:
        """Bisim sends member lists over REST: see :meth:`Guild.chunk`."""
        return None

    async def close(self, code: int = 4000) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        self._close_code = code
        await self.socket.close(code=code)
