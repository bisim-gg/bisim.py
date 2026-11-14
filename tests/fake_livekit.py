"""A small stand-in for LiveKit's ``rtc`` module: enough for the voice client, with knobs for the tests."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class TrackSource:
    SOURCE_UNKNOWN = 0
    SOURCE_CAMERA = 1
    SOURCE_MICROPHONE = 2


class TrackKind:
    KIND_UNKNOWN = 0
    KIND_AUDIO = 1
    KIND_VIDEO = 2


class DisconnectReason:
    UNKNOWN_REASON = 0
    CLIENT_INITIATED = 1
    DUPLICATE_IDENTITY = 2
    SERVER_SHUTDOWN = 3
    PARTICIPANT_REMOVED = 4
    ROOM_DELETED = 5
    SIGNAL_CLOSE = 9
    ROOM_CLOSED = 10


class ConnectError(Exception):
    pass


@dataclass
class RoomOptions:
    auto_subscribe: bool = True
    dynacast: bool = False


class TrackPublishOptions:
    def __init__(self) -> None:
        self.source = TrackSource.SOURCE_UNKNOWN


class AudioFrame:
    def __init__(self, data: bytes, sample_rate: int, num_channels: int, samples_per_channel: int) -> None:
        if len(data) < num_channels * samples_per_channel * 2:
            raise ValueError('data too short')
        self._data = bytes(data)
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.samples_per_channel = samples_per_channel

    @property
    def data(self) -> memoryview:
        return memoryview(self._data).cast('h')


class EventEmitter:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[..., Any]]] = {}

    def on(self, event: str, callback: Optional[Callable[..., Any]] = None) -> Any:
        if callback is None:

            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                self._handlers.setdefault(event, []).append(func)
                return func

            return decorator
        self._handlers.setdefault(event, []).append(callback)
        return callback

    def emit(self, event: str, *args: Any) -> None:
        for handler in list(self._handlers.get(event, [])):
            handler(*args)


class AudioSource:
    instances: List['AudioSource'] = []

    def __init__(self, sample_rate: int, num_channels: int, queue_size_ms: int = 1000, loop: Any = None) -> None:
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.queue_size_ms = queue_size_ms
        self.frames: List[AudioFrame] = []
        self.times: List[float] = []
        self.clears = 0
        self.closed = False
        AudioSource.instances.append(self)

    async def capture_frame(self, frame: AudioFrame) -> None:
        self.frames.append(frame)
        self.times.append(time.perf_counter())

    def clear_queue(self) -> None:
        self.clears += 1

    async def aclose(self) -> None:
        self.closed = True


class LocalAudioTrack:
    def __init__(self, name: str, source: AudioSource) -> None:
        self.name = name
        self.source = source
        self.muted = False
        self.sid = ''
        self.kind = TrackKind.KIND_AUDIO

    @staticmethod
    def create_audio_track(name: str, source: AudioSource) -> 'LocalAudioTrack':
        return LocalAudioTrack(name, source)

    def mute(self) -> None:
        self.muted = True

    def unmute(self) -> None:
        self.muted = False


class Permissions:
    def __init__(self, can_publish: bool = True, sources: Optional[List[int]] = None, can_subscribe: bool = True) -> None:
        self.can_publish = can_publish
        self.can_publish_sources = list(sources or [])
        self.can_subscribe = can_subscribe


class LocalPublication:
    _n = 0

    def __init__(self, track: LocalAudioTrack, options: TrackPublishOptions) -> None:
        LocalPublication._n += 1
        self.sid = f'TR_local_{LocalPublication._n}'
        self.track = track
        self.source = options.source


class LocalParticipant:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.permissions = Permissions()
        self.published: List[LocalPublication] = []

    async def publish_track(self, track: LocalAudioTrack, options: TrackPublishOptions) -> LocalPublication:
        perms = self.permissions
        if not perms.can_publish or (perms.can_publish_sources and options.source not in perms.can_publish_sources):
            raise RuntimeError('insufficient permissions')
        if getattr(track, 'stopped', False):
            raise RuntimeError('track is stopped')
        publication = LocalPublication(track, options)
        track.sid = publication.sid
        self.published.append(publication)
        return publication

    async def unpublish_track(self, track_sid: str) -> None:
        for publication in list(self.published):
            if publication.sid == track_sid:
                self.published.remove(publication)
                publication.track.stopped = True


class RemoteAudioTrack:
    _n = 0

    def __init__(self) -> None:
        RemoteAudioTrack._n += 1
        self.sid = f'TR_remote_{RemoteAudioTrack._n}'
        self.kind = TrackKind.KIND_AUDIO
        self.frames: 'asyncio.Queue[Optional[AudioFrame]]' = asyncio.Queue()


class RemotePublication:
    def __init__(self, room: 'Room', participant: 'RemoteParticipant') -> None:
        self.room = room
        self.participant = participant
        self.kind = TrackKind.KIND_AUDIO
        self.subscribed = False
        self.track: Optional[RemoteAudioTrack] = None
        self.sid = f'PUB_{participant.identity}'
        self.subscribe_calls: List[bool] = []

    def set_subscribed(self, subscribed: bool) -> None:
        self.subscribe_calls.append(subscribed)
        if subscribed and not self.subscribed:
            self.subscribed = True
            self.track = RemoteAudioTrack()
            self.room.emit('track_subscribed', self.track, self, self.participant)
        elif not subscribed and self.subscribed:
            self.subscribed = False
            track, self.track = self.track, None
            self.room.emit('track_unsubscribed', track, self, self.participant)


class RemoteParticipant:
    def __init__(self, identity: str, name: str = '', metadata: str = '') -> None:
        self.identity = identity
        self.name = name
        self.metadata = metadata
        self.track_publications: Dict[str, RemotePublication] = {}


class Candidate:
    def __init__(self, rtt: float) -> None:
        self.nominated = True
        self.current_round_trip_time = rtt


class StatItem:
    def __init__(self, rtt: float) -> None:
        class _Pair:
            pass

        self.candidate_pair = _Pair()
        self.candidate_pair.candidate_pair = Candidate(rtt)

    def WhichOneof(self, name: str) -> str:
        return 'candidate_pair'


class Stats:
    def __init__(self, rtt: float) -> None:
        self.publisher_stats = [StatItem(rtt)]
        self.subscriber_stats: List[Any] = []


class Room(EventEmitter):
    instances: List['Room'] = []
    identity = '60000000000000001'
    hang_connect = False
    fail_connect = False
    initial_permissions: Optional[Permissions] = None
    rtt = 0.042

    def __init__(self, loop: Any = None) -> None:
        super().__init__()
        self.loop = loop
        self.url: Optional[str] = None
        self.token: Optional[str] = None
        self.options: Optional[RoomOptions] = None
        self.connected = False
        self.disconnect_calls = 0
        self.local_participant = LocalParticipant(self.identity)
        if Room.initial_permissions is not None:
            perms = Room.initial_permissions
            self.local_participant.permissions = Permissions(perms.can_publish, perms.can_publish_sources, perms.can_subscribe)
        self.remote_participants: Dict[str, RemoteParticipant] = {}
        Room.instances.append(self)

    async def connect(self, url: str, token: str, options: RoomOptions = RoomOptions()) -> None:
        self.url, self.token, self.options = url, token, options
        if Room.hang_connect:
            await asyncio.sleep(3600)
        if Room.fail_connect:
            raise ConnectError('could not connect')
        self.connected = True

    def isconnected(self) -> bool:
        return self.connected

    async def disconnect(self, *, reason: int = DisconnectReason.CLIENT_INITIATED) -> None:
        self.disconnect_calls += 1
        if self.connected:
            self.connected = False
            self.emit('disconnected', reason)

    async def get_rtc_stats(self) -> Stats:
        return Stats(Room.rtt)

    # What the server does, for the tests.

    def server_disconnect(self, reason: int) -> None:
        self.connected = False
        self.emit('disconnected', reason)

    def add_speaker(self, identity: str, name: str = '', metadata: str = '') -> RemotePublication:
        participant = RemoteParticipant(identity, name, metadata)
        publication = RemotePublication(self, participant)
        participant.track_publications[publication.sid] = publication
        self.remote_participants[identity] = participant
        self.emit('participant_connected', participant)
        self.emit('track_published', publication, participant)
        return publication

    def remove_speaker(self, identity: str) -> None:
        participant = self.remote_participants.pop(identity)
        self.emit('participant_disconnected', participant)

    def set_permissions(self, perms: Permissions) -> None:
        self.local_participant.permissions = perms
        self.emit('participant_permissions_changed', self.local_participant, perms)


class AudioFrameEvent:
    def __init__(self, frame: AudioFrame) -> None:
        self.frame = frame


class AudioStream:
    instances: List['AudioStream'] = []

    def __init__(self, track: RemoteAudioTrack, loop: Any = None, capacity: int = 0, sample_rate: int = 48000, num_channels: int = 1, frame_size_ms: Optional[int] = None) -> None:
        self.track = track
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.frame_size_ms = frame_size_ms
        self.closed = False
        AudioStream.instances.append(self)

    def __aiter__(self) -> 'AudioStream':
        return self

    async def __anext__(self) -> AudioFrameEvent:
        frame = await self.track.frames.get()
        if frame is None or self.closed:
            raise StopAsyncIteration
        return AudioFrameEvent(frame)

    async def aclose(self) -> None:
        self.closed = True
        self.track.frames.put_nowait(None)


def reset() -> None:
    Room.instances = []
    Room.hang_connect = False
    Room.fail_connect = False
    Room.initial_permissions = None
    AudioSource.instances = []
    AudioStream.instances = []
