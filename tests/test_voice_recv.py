"""Receiving voice: bisim.ext.voice_recv over a fake LiveKit, and its sinks."""

from __future__ import annotations

import asyncio
import math
import struct
import threading
import wave
from typing import Any, List

import bisim
from bisim.ext import voice_recv

from . import fake_livekit as lk
from . import payloads as p
from .conftest import settle
from .test_voice import FRAME, connect, fake_rtc, wait_for  # noqa: F401  (fake_rtc is an autouse fixture)


def remote_frame(freq: float, start: int) -> lk.AudioFrame:
    out = bytearray()
    for n in range(start, start + 960):
        v = int(6000 * math.sin(2 * math.pi * freq * n / 48000))
        out += struct.pack('<hh', v, v)
    return lk.AudioFrame(bytes(out), 48000, 2, 960)


async def test_listen_with_basic_sink(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, cls=voice_recv.VoiceRecvClient)
    room = lk.Room.instances[-1]
    publication = room.add_speaker(p.MEMBER_ID, name='sara')
    # Not listening: nothing is received.
    assert publication.subscribed is False

    got: List[Any] = []
    ended = threading.Event()
    speaking: List[Any] = []

    class Sink(voice_recv.BasicSink):
        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_start(self, member: Any) -> None:
            speaking.append(('start', member.id))

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_stop(self, member: Any) -> None:
            speaking.append(('stop', member.id))

    cleaned = []
    sink = Sink(lambda user, data: got.append((user, data)))
    sink.cleanup = lambda: cleaned.append(True)  # type: ignore
    client_events: List[Any] = []

    @bot_client.event
    async def on_voice_member_speaking_start(member: Any) -> None:
        client_events.append(member.id)

    vc.listen(sink, after=lambda e: ended.set())
    assert vc.is_listening() and vc.sink is sink
    assert publication.subscribed is True
    track = publication.track
    stream = lk.AudioStream.instances[-1]
    assert (stream.sample_rate, stream.num_channels, stream.frame_size_ms) == (48000, 2, 20)
    room.emit('active_speakers_changed', [room.remote_participants[p.MEMBER_ID]])
    for i in range(3):
        track.frames.put_nowait(remote_frame(660, i * 960))
    await wait_for(lambda: len(got) == 3)
    user, data = got[0]
    assert isinstance(user, bisim.Member) and user.id == int(p.MEMBER_ID)
    assert data.source is user and data.opus is None and len(data.pcm) == FRAME
    assert data.packet.sequence == 0 and got[2][1].packet.timestamp == 1920
    room.emit('active_speakers_changed', [])
    await wait_for(lambda: speaking == [('start', int(p.MEMBER_ID)), ('stop', int(p.MEMBER_ID))])
    await settle()
    assert client_events == [int(p.MEMBER_ID)]
    vc.stop_listening()
    await asyncio.get_running_loop().run_in_executor(None, ended.wait, 5)
    assert cleaned == [True]
    assert not vc.is_listening()
    assert publication.subscribed is False
    await vc.disconnect()


async def test_self_deafened_bot_does_not_subscribe(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, cls=voice_recv.VoiceRecvClient, self_deaf=True)
    room = lk.Room.instances[-1]
    publication = room.add_speaker(p.MEMBER_ID)
    vc.listen(voice_recv.BasicSink(lambda u, d: None))
    assert publication.subscribed is False
    await vc.guild.change_voice_state(channel=vc.channel, self_deaf=False)
    assert publication.subscribed is True
    await vc.guild.change_voice_state(channel=vc.channel, self_deaf=True)
    assert publication.subscribed is False
    await vc.disconnect()
    assert not vc.is_listening()


async def test_unknown_speaker_is_built_from_livekit_metadata(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, cls=voice_recv.VoiceRecvClient)
    room = lk.Room.instances[-1]
    publication = room.add_speaker('60000000000000777', name='Guest', metadata='{"username": "guest", "displayName": "Guest"}')
    got: List[Any] = []
    vc.listen(voice_recv.BasicSink(lambda u, d: got.append(u)))
    publication.track.frames.put_nowait(remote_frame(440, 0))
    await wait_for(lambda: got)
    assert got[0].id == 60000000000000777 and got[0].name == 'guest'
    await vc.disconnect()


def test_wave_sink_mixes_speakers_at_their_time(tmp_path: Any) -> None:
    path = tmp_path / 'out.wav'
    sink = voice_recv.WaveSink(str(path))

    def data(ssrc: int, seq: int, value: int) -> voice_recv.VoiceData:
        pcm = struct.pack('<h', value) * (960 * 2)
        return voice_recv.VoiceData(voice_recv.FramePacket(ssrc, seq, seq * 960), None, pcm=pcm)

    for seq in range(20):
        sink.write(None, data(1, seq, 1000))
        sink.write(None, data(2, seq, 2000))
    sink.cleanup()
    with wave.open(str(path), 'rb') as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, 48000)
        frames = w.readframes(w.getnframes())
    samples = struct.unpack(f'<{len(frames) // 2}h', frames)
    # Both speakers in the same 20 ms slots, summed, not one after the other.
    assert len(samples) == 20 * 960 * 2
    assert set(samples) == {3000}


def test_user_filter_passes_one_person() -> None:
    got: List[Any] = []
    member = bisim.Object(id=5)
    sink = voice_recv.UserFilter(voice_recv.BasicSink(lambda u, d: got.append(u)), member)
    sink.write(bisim.Object(id=5), voice_recv.VoiceData(voice_recv.FramePacket(1, 0, 0), None, pcm=b'x'))
    sink.write(bisim.Object(id=6), voice_recv.VoiceData(voice_recv.FramePacket(2, 0, 0), None, pcm=b'x'))
    sink.write(None, voice_recv.VoiceData(voice_recv.FramePacket(3, 0, 0), None, pcm=b'x'))
    assert [u.id for u in got] == [5]
    assert sink.child is not None and sink.child.parent is sink
