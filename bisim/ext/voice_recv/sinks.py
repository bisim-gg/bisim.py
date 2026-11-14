"""Sinks: where received audio goes.

The names and the shape follow ``discord-ext-voice-recv``, the add-on most
discord.py bots use to receive voice, so a bot written for it moves over by
changing the import. On Bisim every :meth:`AudioSink.write` carries 20 ms of
16-bit 48 kHz stereo PCM; there is no Opus.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
import wave
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, List, Optional, Union

from ...utils import MISSING
from .reader import CHANNELS, FRAME_MS, SAMPLE_RATE, SAMPLES_PER_FRAME, VoiceData

if TYPE_CHECKING:
    from ...client import Client
    from ...member import Member
    from ...user import User
    from .voice_client import VoiceRecvClient

    User_ = Union[Member, User]

__all__ = (
    'AudioSink',
    'BasicSink',
    'WaveSink',
    'ConditionalFilter',
    'UserFilter',
)

_log = logging.getLogger(__name__)


class AudioSink:
    """An object that handles received audio. Subclasses implement
    :meth:`wants_opus`, :meth:`write` and :meth:`cleanup`.

    Sinks get events too: mark a plain (not ``async``) method with
    :meth:`listener` and name it after the event, for example
    ``on_voice_member_speaking_start(self, member)``. The events are
    ``on_voice_member_speaking_start(member)``,
    ``on_voice_member_speaking_stop(member)`` and
    ``on_voice_member_disconnect(member, ssrc)``.

    :meth:`write` and the listeners run on the receive thread, not on the
    event loop: use :func:`asyncio.run_coroutine_threadsafe` to reach it.
    """

    __sink_listeners__: Dict[str, List[str]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        listeners: Dict[str, List[str]] = {}
        for base in reversed(cls.__mro__):
            for attr, value in base.__dict__.items():
                func = value.__func__ if isinstance(value, staticmethod) else value
                names = getattr(func, '__sink_listener_names__', None)
                if not names:
                    continue
                for name in names:
                    listeners.setdefault(name, [])
                    if attr not in listeners[name]:
                        listeners[name].append(attr)
        cls.__sink_listeners__ = listeners

    _voice_client: Optional[VoiceRecvClient] = None
    _parent: Optional[AudioSink] = None
    _child: Optional[AudioSink] = None

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass

    @classmethod
    def listener(cls, name: str = MISSING) -> Callable[[Any], Any]:
        """A decorator that marks a method as a sink event listener.

        The method must not be a coroutine. ``name`` defaults to the method's
        own name (``on_voice_member_speaking_start`` and so on).
        """

        def decorator(func: Any) -> Any:
            actual = func.__func__ if isinstance(func, staticmethod) else func
            if inspect.iscoroutinefunction(actual):
                raise TypeError('Listener function must not be a coroutine function.')
            to_assign = name or actual.__name__
            names = getattr(actual, '__sink_listener_names__', None)
            if names is None:
                actual.__sink_listener_names__ = [to_assign]
            else:
                names.append(to_assign)
            return func

        return decorator

    # -- the tree of sinks -------------------------------------------------

    @property
    def root(self) -> AudioSink:
        """:class:`AudioSink`: The sink at the top of this chain."""
        sink = self
        while sink._parent is not None:
            sink = sink._parent
        return sink

    @property
    def parent(self) -> Optional[AudioSink]:
        """Optional[:class:`AudioSink`]: The sink wrapping this one."""
        return self._parent

    @property
    def child(self) -> Optional[AudioSink]:
        """Optional[:class:`AudioSink`]: The sink this one passes audio to."""
        return self._child

    @property
    def children(self) -> List[AudioSink]:
        """List[:class:`AudioSink`]: The sinks this one passes audio to."""
        return [self._child] if self._child is not None else []

    @property
    def voice_client(self) -> Optional[VoiceRecvClient]:
        """Optional[:class:`VoiceRecvClient`]: The voice client this sink listens on."""
        return self.root._voice_client

    @property
    def client(self) -> Optional[Client]:
        """Optional[:class:`~bisim.Client`]: The client the voice client belongs to."""
        vc = self.voice_client
        return vc.client if vc is not None else None

    def _register_child(self, child: AudioSink) -> None:
        if child in self.root.walk_children(with_self=True):
            raise RuntimeError('Audio sink is already in use.')
        self._child = child
        child._parent = self

    def walk_children(self, *, with_self: bool = False) -> Generator[AudioSink, None, None]:
        if with_self:
            yield self
        for child in self.children:
            yield child
            yield from child.walk_children()

    def _attach(self, voice_client: VoiceRecvClient) -> None:
        self.root._voice_client = voice_client

    def _dispatch(self, event: str, *args: Any) -> None:
        name = event if event.startswith('on_') else 'on_' + event
        for sink in self.walk_children(with_self=True):
            for attr in type(sink).__sink_listeners__.get(name, []):
                try:
                    getattr(sink, attr)(*args)
                except Exception:
                    _log.exception('Sink listener %s.%s failed', type(sink).__name__, attr)

    # -- what subclasses implement -----------------------------------------

    def wants_opus(self) -> bool:
        """Whether the sink wants Opus. On Bisim it always gets PCM."""
        raise NotImplementedError

    def write(self, user: Optional[User_], data: VoiceData) -> None:
        """Called with 20 ms of one person's audio.

        Parameters
        -----------
        user: Optional[Union[:class:`~bisim.Member`, :class:`~bisim.User`]]
            Who is speaking, ``None`` when unknown.
        data: :class:`VoiceData`
            The audio.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """Called once when listening stops."""
        raise NotImplementedError


class BasicSink(AudioSink):
    """A sink that calls a function with every frame.

    Parameters
    -----------
    event: Callable[[Optional[Union[:class:`~bisim.Member`, :class:`~bisim.User`]], :class:`VoiceData`], Any]
        Called as ``event(user, data)`` on the receive thread.
    rtcp_event: Optional[Callable]
        Accepted for compatibility; never called on Bisim (there is no RTCP).
    decode: :class:`bool`
        Accepted for compatibility; the audio is always PCM.
    """

    def __init__(self, event: Callable[[Optional[User_], VoiceData], Any], *, rtcp_event: Optional[Callable[..., Any]] = None, decode: bool = True):
        super().__init__()
        self.cb = event
        self.cb_rtcp = rtcp_event
        self.decode = decode

    def wants_opus(self) -> bool:
        return False

    def write(self, user: Optional[User_], data: VoiceData) -> None:
        self.cb(user, data)

    def cleanup(self) -> None:
        pass


class WaveSink(AudioSink):
    """A sink that writes what it receives to a wave file (16-bit 48 kHz stereo).

    Everyone's audio is mixed into the one file at the time it arrived, and a
    stretch with nobody heard is written as silence. For one person only,
    wrap it: ``UserFilter(WaveSink('out.wav'), member)``.

    Parameters
    -----------
    destination: Union[:class:`str`, :term:`py:file object`]
        A file name or a file opened for binary writing.
    """

    CHANNELS = CHANNELS
    SAMPLE_WIDTH = 2
    SAMPLING_RATE = SAMPLE_RATE
    # How long a frame may wait for later ones before it is written.
    HOLD_FRAMES = 10

    def __init__(self, destination: Any):
        super().__init__()
        self._file = wave.open(destination, 'wb')
        self._file.setnchannels(self.CHANNELS)
        self._file.setsampwidth(self.SAMPLE_WIDTH)
        self._file.setframerate(self.SAMPLING_RATE)
        self._lock = threading.Lock()
        self._mix: Dict[int, Any] = {}
        self._next_slot = 0
        self._newest = -1
        self._start: Optional[float] = None
        self._sources: Dict[Any, List[int]] = {}
        self._closed = False

    def wants_opus(self) -> bool:
        return False

    def _slot_for(self, key: Any, now: float) -> int:
        assert self._start is not None
        wall = int(round((now - self._start) * 1000 / FRAME_MS))
        entry = self._sources.get(key)
        if entry is None:
            entry = self._sources[key] = [max(wall, self._next_slot), 0]
        offset, count = entry
        slot = offset + count
        # The speaker's stream paused (or started late): put the frame where it really belongs.
        if wall - slot > 5:
            entry[0] = wall - count
            slot = wall
        if slot < self._next_slot:
            entry[0] += self._next_slot - slot
            slot = self._next_slot
        entry[1] += 1
        return slot

    def write(self, user: Optional[User_], data: VoiceData) -> None:
        import numpy as np

        pcm = data.pcm
        if not pcm:
            return
        now = time.perf_counter()
        with self._lock:
            if self._closed:
                return
            if self._start is None:
                self._start = now
            key = getattr(data.packet, 'ssrc', None) or (user.id if user is not None else None)
            slot = self._slot_for(key, now)
            samples = np.frombuffer(pcm[: SAMPLES_PER_FRAME * CHANNELS * 2], dtype=np.int16).astype(np.int32)
            current = self._mix.get(slot)
            if current is None:
                self._mix[slot] = samples.copy()
            else:
                n = min(len(current), len(samples))
                current[:n] += samples[:n]
            self._newest = max(self._newest, slot)
            self._flush(self._newest - self.HOLD_FRAMES)

    def _flush(self, upto: int) -> None:
        import numpy as np

        silence = None
        out = []
        while self._next_slot <= upto:
            mixed = self._mix.pop(self._next_slot, None)
            if mixed is None:
                if silence is None:
                    silence = bytes(SAMPLES_PER_FRAME * CHANNELS * 2)
                out.append(silence)
            else:
                out.append(np.clip(mixed, -32768, 32767).astype(np.int16).tobytes())
            self._next_slot += 1
        if out:
            self._file.writeframes(b''.join(out))

    def cleanup(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self._newest >= 0:
                    self._flush(self._newest)
                self._file.close()
            except Exception:
                _log.warning('WaveSink got error closing file on cleanup', exc_info=True)


class ConditionalFilter(AudioSink):
    """A sink that passes audio to ``destination`` only when ``predicate(user, data)`` is true.

    Parameters
    -----------
    destination: :class:`AudioSink`
        The sink to pass audio to.
    predicate: Callable[[Optional[Union[:class:`~bisim.Member`, :class:`~bisim.User`]], :class:`VoiceData`], :class:`bool`]
        Decides for each frame.
    """

    def __init__(self, destination: AudioSink, predicate: Callable[[Optional[User_], VoiceData], bool]):
        super().__init__()
        self.destination = destination
        self.predicate = predicate
        self._register_child(destination)

    def wants_opus(self) -> bool:
        return self.destination.wants_opus()

    def write(self, user: Optional[User_], data: VoiceData) -> None:
        if self.predicate(user, data):
            self.destination.write(user, data)

    def cleanup(self) -> None:
        self.destination.cleanup()


class UserFilter(ConditionalFilter):
    """A sink that passes on only one person's audio.

    Parameters
    -----------
    destination: :class:`AudioSink`
        The sink to pass audio to.
    user: :class:`~bisim.abc.Snowflake`
        The member or user to keep.
    """

    def __init__(self, destination: AudioSink, user: Any):
        self.user = user
        user_id = user.id
        super().__init__(destination, lambda u, _: u is not None and u.id == user_id)
