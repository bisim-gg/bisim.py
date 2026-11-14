"""Reads the others' audio from LiveKit and hands it to a sink on a thread of its own."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, Union

if TYPE_CHECKING:
    from ...member import Member
    from ...user import User
    from .sinks import AudioSink
    from .voice_client import VoiceRecvClient

    User_ = Union[Member, User]

__all__ = (
    'VoiceData',
    'FramePacket',
)

_log = logging.getLogger(__name__)

SAMPLE_RATE = 48000
CHANNELS = 2
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000


class FramePacket:
    """Where a :class:`VoiceData` came from.

    On Discord this is an RTP packet. Bisim's voice server decodes the audio,
    so there are no packets to show; this keeps the fields code tends to read.

    Attributes
    -----------
    ssrc: :class:`int`
        A number that stands for the speaker within this connection (stable
        while they stay in the channel).
    sequence: :class:`int`
        The frame's number in the speaker's stream, from 0.
    timestamp: :class:`int`
        The frame's position in the speaker's stream, in samples.
    decrypted_data: ``None``
        Always ``None``: there is no Opus payload.
    extension_data: :class:`dict`
        Always empty.
    """

    __slots__ = ('ssrc', 'sequence', 'timestamp', 'decrypted_data', 'extension_data')

    def __init__(self, ssrc: int, sequence: int, timestamp: int) -> None:
        self.ssrc: int = ssrc
        self.sequence: int = sequence
        self.timestamp: int = timestamp
        self.decrypted_data: Optional[bytes] = None
        self.extension_data: Dict[int, bytes] = {}

    def __repr__(self) -> str:
        return f'<FramePacket ssrc={self.ssrc} sequence={self.sequence} timestamp={self.timestamp}>'


class VoiceData:
    """Container object for audio data and source user.

    Attributes
    -----------
    packet: :class:`FramePacket`
        Where the frame came from.
    source: Optional[Union[:class:`Member`, :class:`User`]]
        The person speaking, ``None`` when unknown.
    pcm: :class:`bytes`
        20 ms of 16-bit 48 kHz stereo PCM (3,840 bytes).
    """

    __slots__ = ('packet', 'source', 'pcm')

    def __init__(self, packet: FramePacket, source: Optional[User_], *, pcm: Optional[bytes] = None) -> None:
        self.packet: FramePacket = packet
        self.source: Optional[User_] = source
        self.pcm: bytes = pcm if pcm is not None else b''

    @property
    def opus(self) -> Optional[bytes]:
        """Always ``None`` on Bisim: the voice server decodes the audio, so there is no Opus."""
        return None

    def __repr__(self) -> str:
        return f'<VoiceData source={self.source!r} packet={self.packet!r} pcm={len(self.pcm)} bytes>'


class AudioReader:
    """One per :meth:`VoiceRecvClient.listen`: a reader task per speaker, one router thread."""

    def __init__(
        self,
        sink: AudioSink,
        voice_client: VoiceRecvClient,
        *,
        after: Optional[Callable[[Optional[Exception]], Any]] = None,
    ) -> None:
        if after is not None and not callable(after):
            raise TypeError('Expected a callable for the "after" parameter.')
        self.sink: AudioSink = sink
        self.voice_client: VoiceRecvClient = voice_client
        self.after: Optional[Callable[[Optional[Exception]], Any]] = after
        self.loop: asyncio.AbstractEventLoop = voice_client.loop

        self._queue: queue.Queue[Optional[Tuple[Any, ...]]] = queue.Queue()
        self._end = threading.Event()
        self._lock = threading.RLock()
        self._error: Optional[Exception] = None
        self._readers: Dict[str, Tuple[asyncio.Task[Any], Any]] = {}
        self._thread = threading.Thread(target=self._run, daemon=True, name=f'voice-recv-router:{id(self):#x}')
        sink._attach(voice_client)

    # -- control ---------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def is_listening(self) -> bool:
        return not self._end.is_set()

    def stop(self) -> None:
        if self._end.is_set():
            return
        self._end.set()
        self._queue.put(None)
        try:
            running: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self._stop_readers()
        else:
            try:
                self.loop.call_soon_threadsafe(self._stop_readers)
            except RuntimeError:
                pass

    def set_sink(self, sink: AudioSink) -> AudioSink:
        with self._lock:
            old = self.sink
            sink._attach(self.voice_client)
            self.sink = sink
        return old

    # -- the loop side ---------------------------------------------------

    def add_track(self, track: Any, participant: Any, ssrc: int) -> None:
        if self._end.is_set():
            return
        key = getattr(track, 'sid', None) or str(id(track))
        if key in self._readers:
            return
        from ...voice_state import _rtc

        stream = _rtc().AudioStream(track, loop=self.loop, sample_rate=SAMPLE_RATE, num_channels=CHANNELS, frame_size_ms=FRAME_MS)
        task = self.loop.create_task(self._read(stream, participant, ssrc), name=f'bisim: voice recv {key}')
        self._readers[key] = (task, stream)

    def remove_track(self, track: Any) -> None:
        key = getattr(track, 'sid', None) or str(id(track))
        self._drop_reader(key)

    def _drop_reader(self, key: str) -> None:
        entry = self._readers.pop(key, None)
        if entry is None:
            return
        task, stream = entry
        task.cancel()

        async def close() -> None:
            try:
                await stream.aclose()
            except Exception:
                pass

        try:
            self.loop.create_task(close())
        except RuntimeError:
            pass

    async def _read(self, stream: Any, participant: Any, ssrc: int) -> None:
        sequence = 0
        try:
            async for event in stream:
                if self._end.is_set():
                    break
                frame = event.frame
                pcm = bytes(frame.data)
                if not pcm:
                    continue
                user = self.voice_client._user_for(participant)
                packet = FramePacket(ssrc, sequence, sequence * SAMPLES_PER_FRAME)
                sequence += 1
                self._queue.put(('write', user, VoiceData(packet, user, pcm=pcm)))
        except asyncio.CancelledError:
            pass
        except Exception:
            _log.exception('Reading audio from a voice participant failed')

    def dispatch(self, event: str, *args: Any) -> None:
        if not self._end.is_set():
            self._queue.put(('event', event, args))

    # -- the router thread -----------------------------------------------

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                kind = item[0]
                with self._lock:
                    sink = self.sink
                    if kind == 'write':
                        _, user, data = item
                        try:
                            sink.write(user, data)
                        except Exception as exc:
                            _log.exception('A sink failed writing audio; listening stops')
                            self._error = exc
                            self._end.set()
                            break
                    elif kind == 'event':
                        _, event, args = item
                        sink._dispatch(event, *args)
        finally:
            try:
                self.loop.call_soon_threadsafe(self._stop_readers)
            except RuntimeError:
                pass
            try:
                self.sink.cleanup()
            except Exception:
                _log.exception('Cleaning up a sink failed')
            self._call_after()

    def _stop_readers(self) -> None:
        for key in list(self._readers):
            self._drop_reader(key)

    def _call_after(self) -> None:
        if self.after is not None:
            try:
                self.after(self._error)
            except Exception as exc:
                exc.__context__ = self._error
                _log.exception('Calling the after function failed.', exc_info=exc)
        elif self._error is not None:
            _log.exception('Exception in voice receive thread %s', self._thread.name, exc_info=self._error)
