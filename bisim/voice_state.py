"""The voice connection under :class:`~bisim.VoiceClient`: one LiveKit room at a time.

Bisim's voice runs on LiveKit. Joining is a REST call (``POST
/channels/:id/voice/join``) that answers with the LiveKit address and a token;
the media then goes between the bot and LiveKit and never touches Bisim's own
servers. This module owns that room: it joins, publishes the bot's one audio
track, follows moves and drops, and leaves.

The structure follows discord.py's ``voice_state.py`` (MIT, Copyright (c)
2015-present Rapptz; see LICENSE); the transport underneath is LiveKit's
official Python SDK, installed with ``pip install "bisim.py[voice]"``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections import deque
from enum import Enum
from typing import TYPE_CHECKING, Any, Deque, Dict, Optional, Set

from . import utils
from .backoff import ExponentialBackoff
from .errors import ClientException, Forbidden, HTTPException, NotFound

if TYPE_CHECKING:
    from .voice_client import VoiceClient

__all__ = ('VoiceConnectionState',)

_log = logging.getLogger(__name__)

# LiveKit's ``rtc`` module, imported the first time a voice client is made so
# that ``import bisim`` stays light. Tests put a fake here.
rtc: Any = None

SAMPLE_RATE = 48000
CHANNELS = 2
# How much audio LiveKit's source may hold ahead of real time. The player keeps
# about 60 ms ahead; a pause or a stop drops what is queued.
QUEUE_MS = 200
TRACK_NAME = 'bisim-audio'
STATS_INTERVAL = 5.0
PUBLISH_TIMEOUT = 10.0
MISSING_VOICE = (
    'Voice needs LiveKit\'s Python SDK, which comes with the voice extra: pip install "bisim.py[voice]"'
)


def _rtc() -> Any:
    global rtc
    if rtc is None:
        try:
            from livekit import rtc as livekit_rtc  # type: ignore
        except ImportError as exc:
            raise RuntimeError(MISSING_VOICE) from exc
        rtc = livekit_rtc
    return rtc


def has_voice() -> bool:
    """Whether LiveKit's SDK can be imported."""
    try:
        _rtc()
    except RuntimeError:
        return False
    return True


class ConnectionFlowState(Enum):
    disconnected = 0
    joining = 1
    connecting = 2
    connected = 3
    reconnecting = 4
    moving = 5


class VoiceConnectionState:
    """Joins, holds and leaves the LiveKit room of one :class:`~bisim.VoiceClient`."""

    def __init__(self, voice_client: VoiceClient) -> None:
        self.voice_client = voice_client
        self.loop: asyncio.AbstractEventLoop = voice_client.loop
        self.reconnect: bool = True
        self.timeout: float = 30.0
        self.self_mute: bool = False
        self.self_deaf: bool = False
        self.server_mute: bool = False
        self.server_deaf: bool = False
        self.state: ConnectionFlowState = ConnectionFlowState.disconnected

        self.token: Optional[str] = None
        self.endpoint: Optional[str] = None
        self.answer: Dict[str, Any] = {}

        self._room: Any = None
        self._retired: Set[Any] = set()
        self._source: Any = None
        self._track: Any = None
        self._publication: Any = None
        self._channel_id: Optional[int] = None
        self._subscriptions: Dict[Any, bool] = {}
        self._publish_lock: asyncio.Lock = asyncio.Lock()

        self._connected: threading.Event = threading.Event()
        self._expecting_disconnect: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._tasks: Set[asyncio.Task[Any]] = set()
        self._reconnect_task: Optional[asyncio.Task[Any]] = None
        self._stats_task: Optional[asyncio.Task[Any]] = None
        self._latency: float = float('inf')
        self._latencies: Deque[float] = deque(maxlen=20)

    # ------------------------------------------------------------------
    # What the voice client reads
    # ------------------------------------------------------------------

    @property
    def http(self) -> Any:
        return self.voice_client._state.http

    @property
    def room(self) -> Any:
        """The LiveKit ``rtc.Room`` the bot is in, or ``None``."""
        return self._room

    @property
    def latency(self) -> float:
        return self._latency

    @property
    def average_latency(self) -> float:
        if not self._latencies:
            return float('inf')
        return sum(self._latencies) / len(self._latencies)

    def is_connected(self) -> bool:
        return self.state is ConnectionFlowState.connected and self._connected.is_set()

    def wait(self, timeout: Optional[float]) -> bool:
        return self._connected.wait(timeout)

    def _spawn(self, coro: Any, *, name: str) -> asyncio.Task[Any]:
        task = self.loop.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(_log_task_exception)
        return task

    # ------------------------------------------------------------------
    # Joining
    # ------------------------------------------------------------------

    async def connect(self, *, reconnect: bool, timeout: float, self_deaf: bool, self_mute: bool) -> None:
        self.reconnect = reconnect
        self.timeout = timeout
        self.self_deaf = self_deaf
        self.self_mute = self_mute
        self._expecting_disconnect = False
        async with self._lock:
            await asyncio.wait_for(self._join_and_open(self.voice_client.channel), timeout)

    async def _join(self, channel: Any) -> Dict[str, Any]:
        answer = await self.http.join_voice(channel.id, self_muted=self.self_mute, self_deafened=self.self_deaf)
        if not isinstance(answer, dict) or not answer.get('url') or not answer.get('token'):
            raise ClientException('Bisim did not answer the voice join with a voice server.')
        self.answer = answer
        self.token = answer['token']
        self.endpoint = answer['url']
        self._channel_id = channel.id
        return answer

    async def _join_and_open(self, channel: Any) -> None:
        self.state = ConnectionFlowState.joining
        answer = await self._join(channel)
        self.voice_client.channel = channel
        self.state = ConnectionFlowState.connecting
        try:
            await self._open_room(answer)
        except BaseException:
            # The join already put the bot on everyone's list; take it off again.
            await self._rest_leave(channel.id)
            raise

    async def _open_room(self, answer: Dict[str, Any]) -> None:
        lk = _rtc()
        room = lk.Room(loop=self.loop)
        self._bind(room)
        self._room = room
        self._subscriptions.clear()
        # One lock per room: a task still busy with a room that is gone never blocks the next.
        self._publish_lock = asyncio.Lock()
        try:
            await room.connect(answer['url'], answer['token'], lk.RoomOptions(auto_subscribe=False))
            if self._room is not room:
                raise asyncio.CancelledError()
            self._source = lk.AudioSource(SAMPLE_RATE, CHANNELS, queue_size_ms=QUEUE_MS, loop=self.loop)
            self._track = None
            self._publication = None
            await self._publish()
            self.sync_subscriptions()
        except BaseException:
            self._room = None
            await self._close_room(room)
            raise
        self.state = ConnectionFlowState.connected
        self._connected.set()
        self._start_stats()
        _log.info('Connected to voice channel %s.', self._channel_id)

    def _may_publish(self) -> bool:
        room = self._room
        if room is None or self._source is None:
            return False
        if self.answer.get('canPublish') is False:
            return False
        try:
            perms = room.local_participant.permissions
        except Exception:
            return False
        if not perms.can_publish:
            return False
        sources = list(perms.can_publish_sources)
        return not sources or _rtc().TrackSource.SOURCE_MICROPHONE in sources

    async def _publish(self) -> None:
        room = self._room
        async with self._publish_lock:
            if room is not self._room or self._publication is not None or not self._may_publish():
                return
            lk = _rtc()
            # A track that was published once is stopped when it is unpublished, so each
            # publication gets a new one over the same source.
            self._track = lk.LocalAudioTrack.create_audio_track(TRACK_NAME, self._source)
            self._apply_mute()
            options = lk.TrackPublishOptions()
            options.source = lk.TrackSource.SOURCE_MICROPHONE
            try:
                publication = await asyncio.wait_for(room.local_participant.publish_track(self._track, options), PUBLISH_TIMEOUT)
            except Exception as exc:
                _log.info('Publishing the audio track failed (%r); the bot stays silent until it may speak.', exc)
                return
            if room is self._room:
                self._publication = publication

    async def _follow_grant(self) -> None:
        """A moderator's server mute takes the microphone away, the unmute gives it back."""
        if self._may_publish():
            await self._publish()
            return
        room = self._room
        async with self._publish_lock:
            publication = self._publication
            if publication is None or room is None or room is not self._room:
                return
            # LiveKit stops forwarding the track at once but tells the client late, if at all.
            self._publication = None
            try:
                await asyncio.wait_for(room.local_participant.unpublish_track(publication.sid), PUBLISH_TIMEOUT)
            except Exception:
                _log.debug('Unpublishing the audio track failed', exc_info=True)

    def _apply_mute(self) -> None:
        track = self._track
        if track is None:
            return
        try:
            if self.self_mute:
                track.mute()
            else:
                track.unmute()
        except Exception:
            _log.debug('Muting the audio track failed', exc_info=True)

    def sync_subscriptions(self) -> None:
        """Receives the others' audio only while the voice client wants it and is not deafened."""
        room = self._room
        if room is None:
            return
        want = bool(self.voice_client._wants_audio()) and not self.self_deaf
        try:
            if want and not room.local_participant.permissions.can_subscribe:
                want = False
        except Exception:
            pass
        audio = _rtc().TrackKind.KIND_AUDIO
        for participant in list(room.remote_participants.values()):
            for publication in list(participant.track_publications.values()):
                if publication.kind != audio:
                    continue
                key = (id(room), getattr(publication, 'sid', id(publication)))
                # What was last asked counts too: a change still on its way is not
                # reflected in ``subscribed`` yet, and must not be taken as done.
                if bool(publication.subscribed) != want or self._subscriptions.get(key) is not want:
                    self._subscriptions[key] = want
                    try:
                        publication.set_subscribed(want)
                    except Exception:
                        _log.debug('Changing a subscription failed', exc_info=True)

    # ------------------------------------------------------------------
    # The room's events
    # ------------------------------------------------------------------

    def _bind(self, room: Any) -> None:
        def mine() -> bool:
            return room is self._room and room not in self._retired

        def on_disconnected(reason: Any = None) -> None:
            self._on_room_disconnected(room, reason)

        def on_reconnecting() -> None:
            if mine():
                _log.info('The voice connection dropped; LiveKit is reconnecting.')
                self.state = ConnectionFlowState.reconnecting
                self._connected.clear()

        def on_reconnected() -> None:
            if mine():
                _log.info('The voice connection is back.')
                self.state = ConnectionFlowState.connected
                self._connected.set()
                self.sync_subscriptions()

        def on_permissions(participant: Any, permissions: Any = None) -> None:
            if not mine():
                return
            try:
                local = participant is room.local_participant or participant.identity == room.local_participant.identity
            except Exception:
                local = False
            if local:
                self._spawn(self._follow_grant(), name='bisim: voice grant')
            self.sync_subscriptions()

        def on_local_unpublished(publication: Any) -> None:
            if mine() and self._publication is not None and getattr(publication, 'sid', None) == self._publication.sid:
                # Unpublished by the server: publish again as soon as the grant allows.
                self._publication = None
                self._spawn(self._follow_grant(), name='bisim: voice grant')

        def on_track_published(publication: Any, participant: Any) -> None:
            if mine():
                self.sync_subscriptions()

        def on_track_subscribed(track: Any, publication: Any, participant: Any) -> None:
            if mine() and track.kind == _rtc().TrackKind.KIND_AUDIO:
                self.voice_client._on_audio_track(track, participant)

        def on_track_unsubscribed(track: Any, publication: Any, participant: Any) -> None:
            if mine():
                self.voice_client._on_audio_track_gone(track, participant)

        def on_participant_disconnected(participant: Any) -> None:
            if mine():
                self.voice_client._on_participant_left(participant)

        def on_active_speakers(speakers: Any) -> None:
            if mine():
                self.voice_client._on_active_speakers(speakers)

        room.on('disconnected', on_disconnected)
        room.on('reconnecting', on_reconnecting)
        room.on('reconnected', on_reconnected)
        room.on('participant_permissions_changed', on_permissions)
        room.on('local_track_unpublished', on_local_unpublished)
        room.on('track_published', on_track_published)
        room.on('track_subscribed', on_track_subscribed)
        room.on('track_unsubscribed', on_track_unsubscribed)
        room.on('participant_disconnected', on_participant_disconnected)
        room.on('active_speakers_changed', on_active_speakers)

    def _on_room_disconnected(self, room: Any, reason: Any) -> None:
        if room is not self._room or room in self._retired or self._expecting_disconnect:
            return
        self._connected.clear()
        reasons = _rtc().DisconnectReason
        final = {
            getattr(reasons, 'PARTICIPANT_REMOVED', 4),
            getattr(reasons, 'ROOM_DELETED', 5),
            getattr(reasons, 'DUPLICATE_IDENTITY', 2),
            getattr(reasons, 'ROOM_CLOSED', 10),
        }
        if reason in final:
            # A moderator's Disconnect, the channel gone, or the same bot joining from
            # somewhere else. The server already took the bot off the list.
            _log.info('Disconnected from voice by the server (reason %s).', reason)
            self._spawn(self._server_disconnect(), name='bisim: voice disconnected')
        elif self.reconnect:
            _log.info('The voice connection was lost (reason %s); joining again.', reason)
            self._start_reconnect()
        else:
            _log.info('The voice connection was lost (reason %s).', reason)
            self._spawn(self._server_disconnect(rest_leave=True), name='bisim: voice lost')

    async def _server_disconnect(self, *, rest_leave: bool = False) -> None:
        await self.disconnect(force=True, rest_leave=rest_leave)

    # ------------------------------------------------------------------
    # Losing the connection
    # ------------------------------------------------------------------

    def _start_reconnect(self) -> None:
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = self._spawn(self._reconnect_loop(), name='bisim: voice reconnect')

    async def _reconnect_loop(self) -> None:
        self.state = ConnectionFlowState.reconnecting
        self._connected.clear()
        old = self._room
        self._room = None
        if old is not None:
            self._retired.add(old)
            await self._close_room(old)
        backoff = ExponentialBackoff()
        while self.state is ConnectionFlowState.reconnecting and not self._expecting_disconnect:
            channel = self.voice_client.channel
            try:
                async with self._lock:
                    if self.state is not ConnectionFlowState.reconnecting:
                        return
                    answer = await self._join(channel)
                    await asyncio.wait_for(self._open_room(answer), self.timeout)
                _log.info('Joined voice channel %s again.', channel.id)
                return
            except asyncio.CancelledError:
                raise
            except (Forbidden, NotFound) as exc:
                _log.info('Bisim refused joining voice again (%s); disconnecting.', exc)
                await self.disconnect(force=True)
                return
            except Exception as exc:
                if self.state is not ConnectionFlowState.reconnecting:
                    return
                retry = backoff.delay()
                _log.info('Joining voice again failed (%s); trying again in %.2fs.', exc, retry)
                await asyncio.sleep(retry)

    # ------------------------------------------------------------------
    # Moving
    # ------------------------------------------------------------------

    async def move_to(self, channel: Any, timeout: Optional[float]) -> None:
        if channel is None:
            await self.voice_client.disconnect()
            return
        if self._channel_id == channel.id and self.is_connected():
            return
        async with self._lock:
            old = self._room
            previous_state = self.state
            if old is not None:
                # The server leaves the old channel as part of the join, which LiveKit
                # reports as a removal: that one is expected.
                self._retired.add(old)
            self.state = ConnectionFlowState.moving
            self._connected.clear()
            try:
                answer = await self._join(channel)
            except BaseException:
                # Nothing moved; stay where the bot was.
                if old is not None:
                    self._retired.discard(old)
                self.state = previous_state
                if old is not None and old.isconnected():
                    self._connected.set()
                elif old is not None and previous_state is ConnectionFlowState.connected:
                    self._on_room_disconnected(old, None)
                raise
            self.voice_client.channel = channel
            self._room = None
            if old is not None:
                await self._close_room(old)
            try:
                await asyncio.wait_for(self._open_room(answer), timeout)
            except asyncio.CancelledError:
                raise
            except Exception:
                if self.reconnect and not self._expecting_disconnect:
                    self.state = ConnectionFlowState.reconnecting
                    self._start_reconnect()
                else:
                    self._spawn(self.disconnect(force=True), name='bisim: voice move failed')
                raise

    async def voice_move(self, data: Dict[str, Any]) -> None:
        """A moderator moved the bot: join the target, as Discord moves a bot."""
        guild = self.voice_client.guild
        target_id = utils._snowflake(data.get('toChannelId') or data.get('to_channel_id'))
        from_id = utils._snowflake(data.get('fromChannelId') or data.get('from_channel_id'))
        if target_id is None or self.state is ConnectionFlowState.disconnected:
            return
        if from_id is not None and self._channel_id is not None and from_id != self._channel_id:
            _log.debug('Ignoring a move from channel %s; the bot is in %s.', from_id, self._channel_id)
            return
        target = guild.get_channel(target_id)
        if target is None:
            _log.debug('Ignoring a move into unknown channel %s.', target_id)
            return
        _log.info('Moved by a moderator to voice channel %s.', target_id)
        await self.move_to(target, self.timeout)

    # ------------------------------------------------------------------
    # The bot's own voice state
    # ------------------------------------------------------------------

    async def voice_state_update(self, data: Dict[str, Any]) -> None:
        if data.get('left'):
            return
        channel_id = utils._snowflake(data.get('channelId'))
        if channel_id is not None and channel_id == self._channel_id:
            channel = self.voice_client.guild.get_channel(channel_id)
            if channel is not None:
                self.voice_client.channel = channel
            self.server_mute = bool(data.get('serverMuted', False))
            self.server_deaf = bool(data.get('serverDeafened', False))

    async def voice_server_update(self, data: Dict[str, Any]) -> None:
        # The library's own voice client joins over REST itself; a server update only
        # reaches it when other code calls Guild.change_voice_state with a protocol of its own.
        _log.debug('Ignoring a voice server update for an existing voice client.')

    async def set_self_state(self, *, self_mute: bool, self_deaf: bool) -> None:
        changed_deaf = self_deaf != self.self_deaf
        self.self_mute = self_mute
        self.self_deaf = self_deaf
        if self._channel_id is not None and self.state is not ConnectionFlowState.disconnected:
            try:
                await self.http.edit_voice_state(self._channel_id, selfMuted=self_mute, selfDeafened=self_deaf)
            except NotFound:
                _log.debug('The voice state change found the bot outside the room.')
        self._apply_mute()
        if changed_deaf:
            self.sync_subscriptions()

    # ------------------------------------------------------------------
    # Sending audio (called from the player's thread)
    # ------------------------------------------------------------------

    def send_audio(self, data: bytes) -> None:
        source = self._source
        if source is None or not self._connected.is_set():
            return
        usable = len(data) - (len(data) % (2 * CHANNELS))
        if usable <= 0:
            return
        frame = _rtc().AudioFrame(bytes(data[:usable]), SAMPLE_RATE, CHANNELS, usable // (2 * CHANNELS))
        coro = source.capture_frame(frame)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            # Called from the event loop itself: never block it.
            self._spawn(coro, name='bisim: voice frame')
            return
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        except RuntimeError:
            coro.close()
            return
        try:
            future.result(timeout=2.0)
        except concurrent.futures.TimeoutError:
            future.cancel()
            _log.debug('A frame took too long to queue and was dropped.')
        except Exception:
            _log.debug('A frame was dropped.', exc_info=True)

    def clear_audio(self) -> None:
        def clear() -> None:
            source = self._source
            if source is not None:
                try:
                    source.clear_queue()
                except Exception:
                    pass

        try:
            self.loop.call_soon_threadsafe(clear)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Latency
    # ------------------------------------------------------------------

    def _start_stats(self) -> None:
        if self._stats_task is None or self._stats_task.done():
            self._stats_task = self._spawn(self._stats_loop(), name='bisim: voice stats')

    async def _stats_loop(self) -> None:
        while self.state is not ConnectionFlowState.disconnected:
            room = self._room
            if room is not None and self._connected.is_set():
                try:
                    rtt = _round_trip(await room.get_rtc_stats())
                except Exception:
                    rtt = None
                if rtt is not None:
                    self._latency = rtt
                    self._latencies.append(rtt)
            await asyncio.sleep(STATS_INTERVAL)

    # ------------------------------------------------------------------
    # Leaving
    # ------------------------------------------------------------------

    async def _rest_leave(self, channel_id: Optional[int]) -> None:
        if channel_id is None:
            return
        try:
            await self.http.leave_voice(channel_id)
        except HTTPException:
            _log.debug('Leaving voice channel %s over REST failed', channel_id, exc_info=True)
        except Exception:
            _log.debug('Leaving voice channel %s failed', channel_id, exc_info=True)

    async def _close_room(self, room: Any) -> None:
        if room is None:
            return
        self._retired.add(room)
        try:
            await room.disconnect()
        except Exception:
            _log.debug('Closing the LiveKit room failed', exc_info=True)

    async def disconnect(self, *, force: bool = True, cleanup: bool = True, rest_leave: bool = True) -> None:
        if not force and not self.is_connected():
            return
        self._expecting_disconnect = True
        previous = self.state
        self.state = ConnectionFlowState.disconnected
        current = asyncio.current_task()
        for task in (self._reconnect_task, self._stats_task):
            if task is not None and task is not current and not task.done():
                task.cancel()
        try:
            room = self._room
            self._room = None
            if room is not None:
                await self._close_room(room)
            if rest_leave and previous is not ConnectionFlowState.disconnected:
                await self._rest_leave(self._channel_id)
        except Exception:
            _log.debug('Ignoring exception disconnecting from voice', exc_info=True)
        finally:
            source = self._source
            self._source = None
            self._track = None
            self._publication = None
            if source is not None:
                try:
                    await source.aclose()
                except Exception:
                    pass
            # Stop the player (it calls ``after``) before waking anything that waits.
            if cleanup:
                self.voice_client.stop()
            self._connected.set()
            self._connected.clear()
            if cleanup:
                self.voice_client.cleanup()
            _log.info('Disconnected from voice channel %s.', self._channel_id)


def _round_trip(stats: Any) -> Optional[float]:
    """The round trip time of the connection LiveKit uses, from ``Room.get_rtc_stats()``."""
    best: Optional[float] = None
    for item in list(getattr(stats, 'publisher_stats', [])) + list(getattr(stats, 'subscriber_stats', [])):
        try:
            if item.WhichOneof('stats') != 'candidate_pair':
                continue
            pair = item.candidate_pair.candidate_pair
        except Exception:
            continue
        if not pair.nominated:
            continue
        rtt = float(pair.current_round_trip_time)
        if best is None or rtt > best:
            best = rtt
    return best


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None and not isinstance(exc, (asyncio.TimeoutError, ClientException, HTTPException)):
        _log.error('A voice task failed', exc_info=exc)
