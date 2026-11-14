"""Voice: the VoiceClient over a fake LiveKit, the player's pacing, the sources and the soundboard."""

from __future__ import annotations

import asyncio
import io
import math
import struct
import threading
import time
from typing import Any, Dict, List, Optional

import pytest

import bisim
from bisim import voice_state
from bisim.http import _ResponseLike

from . import fake_livekit as lk
from . import payloads as p
from .conftest import settle

SECOND_VOICE_ID = '60000000000000204'
FRAME = 3840


@pytest.fixture(autouse=True)
def fake_rtc(monkeypatch: pytest.MonkeyPatch) -> Any:
    lk.reset()
    monkeypatch.setattr(voice_state, 'rtc', lk)
    monkeypatch.setattr(voice_state, 'STATS_INTERVAL', 0.05)
    yield lk
    lk.reset()


def join_answer(token: str = 'lk-token') -> Dict[str, Any]:
    return {
        'url': 'ws://livekit.test:7880',
        'token': token,
        'canPublish': True,
        'canVideo': False,
        'canUseVoiceActivity': True,
        'afkChannelId': None,
        'afkTimeout': 300,
    }


def setup_voice(client: Any, http: Any) -> Any:
    guild = client.get_guild(int(p.GUILD_ID))
    second = bisim.VoiceChannel(state=client._connection, guild=guild, data=p.channel(SECOND_VOICE_ID, 'Second', 'GUILD_VOICE', 2))
    guild._add_channel(second)
    tokens = iter(f'lk-token-{n}' for n in range(1, 100))
    for channel_id in (p.VOICE_ID, SECOND_VOICE_ID):
        http.respond('POST', f'/channels/{channel_id}/voice/join', lambda route, kw: join_answer(next(tokens)))
        http.respond('POST', f'/channels/{channel_id}/voice/leave', {})
        http.respond('PATCH', f'/channels/{channel_id}/voice/state', {})
    return guild


def sine(freq: float, frames: int, amplitude: int = 8000) -> bytes:
    out = bytearray()
    for n in range(frames * 960):
        v = int(amplitude * math.sin(2 * math.pi * freq * n / 48000))
        out += struct.pack('<hh', v, v)
    return bytes(out)


def calls(http: Any, method: str, path: str) -> List[Dict[str, Any]]:
    return [c for c in http.calls if c['method'] == method and c['path'] == path]


async def wait_for(predicate: Any, timeout: float = 3.0) -> None:
    deadline = time.perf_counter() + timeout
    while not predicate():
        if time.perf_counter() > deadline:
            raise AssertionError('condition not met in time')
        await asyncio.sleep(0.01)


async def connect(client: Any, http: Any, **kwargs: Any) -> Any:
    guild = setup_voice(client, http)
    channel = guild.get_channel(int(p.VOICE_ID))
    return await channel.connect(**kwargs)


# -- connecting -------------------------------------------------------------------------------------------------


async def test_connect_joins_over_rest_and_publishes_one_microphone_track(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, self_mute=False, self_deaf=True)
    assert isinstance(vc, bisim.VoiceClient)
    join = http.last('POST', f'/channels/{p.VOICE_ID}/voice/join')
    assert join['json'] == {'selfMuted': False, 'selfDeafened': True}
    room = lk.Room.instances[-1]
    assert room.url == 'ws://livekit.test:7880' and room.token == 'lk-token-1'
    assert room.options.auto_subscribe is False
    [publication] = room.local_participant.published
    assert publication.source == lk.TrackSource.SOURCE_MICROPHONE
    source = lk.AudioSource.instances[-1]
    assert (source.sample_rate, source.num_channels) == (48000, 2)
    assert vc.is_connected()
    assert vc.channel.id == int(p.VOICE_ID)
    assert vc.guild.voice_client is vc
    assert bot_client.voice_clients == [vc]
    assert vc.user == bot_client.user
    assert vc.endpoint == 'ws://livekit.test:7880' and vc.token == 'lk-token-1'
    await wait_for(lambda: vc.latency != float('inf'))
    assert vc.latency == pytest.approx(0.042)
    assert vc.average_latency == pytest.approx(0.042)
    await vc.disconnect()


async def test_connect_twice_in_one_server_is_refused(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    with pytest.raises(bisim.ClientException):
        await vc.guild.get_channel(int(SECOND_VOICE_ID)).connect()
    await vc.disconnect()


async def test_connect_refused_by_the_server_leaves_nothing(bot_client: Any, http: Any) -> None:
    guild = setup_voice(bot_client, http)

    def refuse(route: Any, kw: Any) -> None:
        raise bisim.Forbidden(_ResponseLike(403, 'Forbidden'), {'message': 'Missing permissions', 'code': 'MISSING_PERMISSIONS'})

    http.respond('POST', f'/channels/{p.VOICE_ID}/voice/join', refuse)
    with pytest.raises(bisim.Forbidden):
        await guild.get_channel(int(p.VOICE_ID)).connect()
    assert bot_client.voice_clients == []
    assert lk.Room.instances == []


async def test_connect_timeout_leaves_again(bot_client: Any, http: Any) -> None:
    guild = setup_voice(bot_client, http)
    lk.Room.hang_connect = True
    with pytest.raises(asyncio.TimeoutError):
        await guild.get_channel(int(p.VOICE_ID)).connect(timeout=0.2)
    assert calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/leave')
    assert bot_client.voice_clients == []


async def test_without_livekit_the_error_says_what_to_install(bot_client: Any, http: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    guild = setup_voice(bot_client, http)
    monkeypatch.setattr(voice_state, 'rtc', None)
    monkeypatch.setitem(sys.modules, 'livekit', None)
    with pytest.raises(RuntimeError, match=r'bisim\.py\[voice\]'):
        await guild.get_channel(int(p.VOICE_ID)).connect()
    assert bot_client.voice_clients == []


async def test_server_muted_bot_publishes_once_it_may_speak(bot_client: Any, http: Any) -> None:
    lk.Room.initial_permissions = lk.Permissions(can_publish=False)
    vc = await connect(bot_client, http)
    room = lk.Room.instances[-1]
    assert room.local_participant.published == []
    room.set_permissions(lk.Permissions(can_publish=True, sources=[lk.TrackSource.SOURCE_MICROPHONE]))
    await wait_for(lambda: len(room.local_participant.published) == 1)
    await vc.disconnect()


async def test_server_mute_takes_the_track_away_and_the_unmute_publishes_a_new_one(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, self_mute=True)
    room = lk.Room.instances[-1]
    [first] = room.local_participant.published
    assert first.track.muted
    room.set_permissions(lk.Permissions(can_publish=False))
    await wait_for(lambda: room.local_participant.published == [])
    assert vc._connection._publication is None
    room.set_permissions(lk.Permissions(can_publish=True, sources=[lk.TrackSource.SOURCE_MICROPHONE]))
    await wait_for(lambda: len(room.local_participant.published) == 1)
    [second] = room.local_participant.published
    assert second.track is not first.track and second.track.muted  # a fresh track, still self-muted
    # A late word from LiveKit about the old publication changes nothing.
    room.emit('local_track_unpublished', first)
    await settle()
    assert room.local_participant.published == [second] and vc._connection._publication is second
    await vc.disconnect()


# -- playing ------------------------------------------------------------------------------------------------------


async def test_play_paces_20ms_frames_and_calls_after(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    pcm = sine(440, 25)
    done = threading.Event()
    errors: List[Optional[Exception]] = []

    def after(error: Optional[Exception]) -> None:
        errors.append(error)
        done.set()

    started = time.perf_counter()
    vc.play(bisim.PCMAudio(io.BytesIO(pcm)), after=after)
    assert vc.is_playing() and not vc.is_paused()
    await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
    elapsed = time.perf_counter() - started
    assert errors == [None]
    source = lk.AudioSource.instances[-1]
    assert len(source.frames) == 25
    assert all(f.samples_per_channel == 960 and f.num_channels == 2 and f.sample_rate == 48000 for f in source.frames)
    assert b''.join(bytes(f.data) for f in source.frames) == pcm
    # 25 frames of 20 ms, with the player up to 60 ms ahead: about 0.44 s, never all at once.
    assert 0.3 <= elapsed <= 1.0, elapsed
    spread = source.times[-1] - source.times[0]
    assert spread >= 0.3, spread
    assert not vc.is_playing()
    await vc.disconnect()


async def test_pause_resume_and_stop(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    source = lk.AudioSource.instances[-1]
    done = threading.Event()
    errors: List[Optional[Exception]] = []
    vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 500))), after=lambda e: (errors.append(e), done.set()))
    await asyncio.sleep(0.15)
    vc.pause()
    assert vc.is_paused() and not vc.is_playing()
    await asyncio.sleep(0.05)
    count = len(source.frames)
    await asyncio.sleep(0.2)
    assert len(source.frames) == count
    assert source.clears >= 1
    vc.resume()
    assert vc.is_playing()
    await asyncio.sleep(0.15)
    assert len(source.frames) > count
    vc.stop()
    await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
    assert errors == [None]
    assert not vc.is_playing() and not vc.is_paused()
    await vc.disconnect()


async def test_play_refusals(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)

    class OpusSource(bisim.AudioSource):
        def read(self) -> bytes:
            return b''

        def is_opus(self) -> bool:
            return True

    with pytest.raises(bisim.ClientException):
        vc.play(OpusSource())
    with pytest.raises(TypeError):
        vc.play('song.mp3')  # type: ignore
    vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 200))))
    with pytest.raises(bisim.ClientException):
        vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 10))))
    replacement = bisim.PCMAudio(io.BytesIO(sine(660, 10)))
    vc.source = replacement
    assert vc.source is replacement
    with pytest.raises(bisim.ClientException):
        vc.send_audio_packet(b'opus', encode=False)
    await vc.disconnect()
    with pytest.raises(bisim.ClientException):
        vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 10))))


def test_volume_transformer_scales_and_clips() -> None:
    frame = struct.pack('<hhhh', 1000, -1000, 30000, -30000) + bytes(FRAME - 8)
    t = bisim.PCMVolumeTransformer(bisim.PCMAudio(io.BytesIO(frame)), volume=0.5)
    out = struct.unpack('<hhhh', t.read()[:8])
    assert out == (500, -500, 15000, -15000)
    t = bisim.PCMVolumeTransformer(bisim.PCMAudio(io.BytesIO(frame)), volume=5.0)
    assert t.volume == 5.0
    out = struct.unpack('<hhhh', t.read()[:8])
    assert out == (2000, -2000, 32767, -32768)  # at most 2.0, clipped
    t.volume = -1
    assert t.volume == 0.0

    class OpusSource(bisim.AudioSource):
        def is_opus(self) -> bool:
            return True

    with pytest.raises(bisim.ClientException):
        bisim.PCMVolumeTransformer(OpusSource())
    with pytest.raises(TypeError):
        bisim.PCMVolumeTransformer('nope')  # type: ignore


def test_ffmpeg_sources_ask_ffmpeg_for_pcm(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[List[str]] = []

    class Proc:
        pid = 1
        stdout = io.BytesIO(bytes(FRAME))
        stdin = None
        stderr = None
        returncode = 0

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    def spawn(self: Any, args: Any, **kwargs: Any) -> Proc:
        seen.append(list(args))
        return Proc()

    monkeypatch.setattr(bisim.FFmpegAudio, '_spawn_process', spawn)
    pcm = bisim.FFmpegPCMAudio('song.mp3', before_options='-reconnect 1', options='-vn')
    assert seen[-1][:4] == ['ffmpeg', '-reconnect', '1', '-i']
    assert seen[-1][4:] == ['song.mp3', '-f', 's16le', '-ar', '48000', '-ac', '2', '-loglevel', 'warning', '-blocksize', '8192', '-vn', 'pipe:1']
    assert len(pcm.read()) == FRAME and not pcm.is_opus()
    opus_src = bisim.FFmpegOpusAudio('song.webm', bitrate=96, codec='opus', executable='ff')
    assert seen[-1][0] == 'ff' and 's16le' in seen[-1] and 'libopus' not in seen[-1]
    assert not opus_src.is_opus()
    assert opus_src.bitrate == 96
    bisim.PCMVolumeTransformer(opus_src)  # PCM, so it takes a volume


def test_missing_ffmpeg_is_a_client_exception() -> None:
    with pytest.raises(bisim.ClientException, match='was not found'):
        bisim.FFmpegPCMAudio('song.mp3', executable='surely-not-an-ffmpeg-binary')


def test_opus_shim_keeps_discord_py_calls_working() -> None:
    assert bisim.opus.is_loaded()
    assert bisim.opus.load_opus('libopus.so.0') is None
    assert bisim.opus.Encoder.FRAME_SIZE == FRAME


# -- following the server -----------------------------------------------------------------------------------------


async def test_moderator_disconnect_cleans_up_and_calls_after(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    room = lk.Room.instances[-1]
    done = threading.Event()
    errors: List[Optional[Exception]] = []
    vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 500))), after=lambda e: (errors.append(e), done.set()))
    await asyncio.sleep(0.05)
    room.server_disconnect(lk.DisconnectReason.PARTICIPANT_REMOVED)
    await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
    await wait_for(lambda: bot_client.voice_clients == [])
    assert errors == [None]
    assert not vc.is_connected()
    assert vc.guild.voice_client is None
    assert not calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/leave')


async def test_lost_connection_rejoins_with_a_fresh_join(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, reconnect=True)
    first = lk.Room.instances[-1]
    vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 500))))
    await asyncio.sleep(0.05)
    first.server_disconnect(lk.DisconnectReason.SIGNAL_CLOSE)
    await wait_for(lambda: len(lk.Room.instances) == 2 and vc.is_connected())
    second = lk.Room.instances[-1]
    assert second.token == 'lk-token-2'
    assert len(calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/join')) == 2
    assert bot_client.voice_clients == [vc]
    # The player kept going into the new connection.
    await wait_for(lambda: len(lk.AudioSource.instances[-1].frames) > 2)
    await vc.disconnect()


async def test_lost_connection_without_reconnect_leaves(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http, reconnect=False)
    lk.Room.instances[-1].server_disconnect(lk.DisconnectReason.SIGNAL_CLOSE)
    await wait_for(lambda: bot_client.voice_clients == [])
    assert calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/leave')
    assert len(lk.Room.instances) == 1
    assert not vc.is_connected()


async def test_move_to_joins_the_other_channel_and_keeps_playing(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    first = lk.Room.instances[-1]
    done = threading.Event()
    errors: List[Optional[Exception]] = []
    vc.play(bisim.PCMAudio(io.BytesIO(sine(440, 100))), after=lambda e: (errors.append(e), done.set()))
    await asyncio.sleep(0.05)
    target = vc.guild.get_channel(int(SECOND_VOICE_ID))
    # The server leaves the first channel as part of the join: LiveKit reports a removal, which must not end the call.
    http.respond(
        'POST',
        f'/channels/{SECOND_VOICE_ID}/voice/join',
        lambda route, kw: (first.server_disconnect(lk.DisconnectReason.PARTICIPANT_REMOVED), join_answer('moved'))[1],
    )
    await vc.move_to(target)
    assert vc.channel is target
    second = lk.Room.instances[-1]
    assert second is not first and second.token == 'moved'
    assert second.local_participant.published
    assert bot_client.voice_clients == [vc]
    assert vc.is_connected()
    assert not calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/leave')
    await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
    assert errors == [None]
    assert len(lk.AudioSource.instances[-1].frames) > 0
    await vc.disconnect()
    assert calls(http, 'POST', f'/channels/{SECOND_VOICE_ID}/voice/leave')


async def test_move_refused_stays_put(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)

    def refuse(route: Any, kw: Any) -> None:
        raise bisim.Forbidden(_ResponseLike(403, 'Forbidden'), {'message': 'Missing permissions'})

    http.respond('POST', f'/channels/{SECOND_VOICE_ID}/voice/join', refuse)
    with pytest.raises(bisim.Forbidden):
        await vc.move_to(vc.guild.get_channel(int(SECOND_VOICE_ID)))
    assert vc.channel.id == int(p.VOICE_ID)
    assert vc.is_connected()
    await vc.disconnect()


async def test_voice_move_event_makes_the_bot_follow(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    state = bot_client._connection
    state.parse_voice_move(
        {'type': 'VOICE_MOVE', 'voiceMove': {'guildId': p.GUILD_ID, 'fromChannelId': p.VOICE_ID, 'toChannelId': SECOND_VOICE_ID}}
    )
    await wait_for(lambda: vc.channel.id == int(SECOND_VOICE_ID) and vc.is_connected())
    assert calls(http, 'POST', f'/channels/{SECOND_VOICE_ID}/voice/join')
    await vc.disconnect()


async def test_own_voice_state_reaches_the_voice_client_and_the_event(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    seen: List[Any] = []
    original = vc.on_voice_state_update

    async def spy(data: Dict[str, Any]) -> None:
        seen.append(data)
        await original(data)

    vc.on_voice_state_update = spy  # type: ignore
    events: List[Any] = []

    @bot_client.event
    async def on_voice_state_update(member: Any, before: Any, after: Any) -> None:
        events.append((member, after))

    bot_client._connection.parse_voice_state_update(
        {'type': 'VOICE_STATE_UPDATE', 'guildId': p.GUILD_ID, 'channelId': p.VOICE_ID, 'voiceState': {'userId': p.BOT_ID, 'selfDeafened': True}}
    )
    await settle()
    assert seen and seen[0]['channelId'] == p.VOICE_ID and seen[0]['selfDeafened'] is True
    assert events and events[0][0].id == int(p.BOT_ID) and events[0][1].channel.id == int(p.VOICE_ID)
    assert [m.id for m in vc.channel.members] == [int(p.BOT_ID)]
    assert vc.guild.me.voice.self_deaf
    await vc.disconnect()


async def test_change_voice_state_mutes_moves_and_leaves(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    guild = vc.guild
    await guild.change_voice_state(channel=vc.channel, self_mute=True, self_deaf=False)
    assert http.last('PATCH', f'/channels/{p.VOICE_ID}/voice/state')['json'] == {'selfMuted': True, 'selfDeafened': False}
    assert vc.self_mute and vc._connection._track.muted
    await guild.change_voice_state(channel=guild.get_channel(int(SECOND_VOICE_ID)), self_mute=True)
    assert vc.channel.id == int(SECOND_VOICE_ID)
    assert http.last('POST', f'/channels/{SECOND_VOICE_ID}/voice/join')['json'] == {'selfMuted': True, 'selfDeafened': False}
    assert vc._connection._track.muted
    await guild.change_voice_state(channel=None)
    assert bot_client.voice_clients == []
    assert calls(http, 'POST', f'/channels/{SECOND_VOICE_ID}/voice/leave')


async def test_change_voice_state_without_a_voice_client_hands_the_answer_to_a_custom_protocol(bot_client: Any, http: Any) -> None:
    guild = setup_voice(bot_client, http)
    got: List[Dict[str, Any]] = []

    class Custom(bisim.VoiceProtocol):
        async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False) -> None:
            await self.channel.guild.change_voice_state(channel=self.channel, self_deaf=self_deaf)

        async def on_voice_server_update(self, data: Dict[str, Any]) -> None:
            got.append(data)

        async def on_voice_state_update(self, data: Dict[str, Any]) -> None:
            pass

        async def disconnect(self, *, force: bool) -> None:
            await self.channel.guild.change_voice_state(channel=None)
            self.cleanup()

    custom = await guild.get_channel(int(p.VOICE_ID)).connect(cls=Custom, self_deaf=True)
    assert isinstance(custom, Custom)
    assert got[0]['endpoint'] == 'ws://livekit.test:7880' and got[0]['token'] == 'lk-token-1'
    assert got[0]['guild_id'] == p.GUILD_ID and got[0]['channel_id'] == p.VOICE_ID
    assert http.last('POST', f'/channels/{p.VOICE_ID}/voice/join')['json'] == {'selfMuted': False, 'selfDeafened': True}
    await custom.disconnect(force=False)
    assert bot_client.voice_clients == []


async def test_client_close_disconnects_voice(bot_client: Any, http: Any) -> None:
    vc = await connect(bot_client, http)
    await bot_client._connection.close_voice_clients()
    assert bot_client.voice_clients == []
    assert not vc.is_connected()
    assert calls(http, 'POST', f'/channels/{p.VOICE_ID}/voice/leave')


async def test_send_sound_and_fetch_sounds(bot_client: Any, http: Any) -> None:
    guild = setup_voice(bot_client, http)
    http.respond(
        'GET',
        f'/guilds/{p.GUILD_ID}/sounds',
        [{'id': '60000000000000900', 'guildId': p.GUILD_ID, 'name': 'airhorn', 'objectKey': 'sounds/x.mp3', 'emojiName': '📯', 'volume': 80, 'durationMs': 1200, 'creatorId': p.OWNER_ID}],
    )
    http.respond('POST', f'/channels/{p.VOICE_ID}/soundboard/play', {})
    [sound] = await guild.fetch_soundboard_sounds()
    assert sound.name == 'airhorn' and sound.volume == 0.8 and sound.duration == 1.2 and str(sound.emoji) == '📯'
    assert sound.file is not None and sound.file.url.endswith('sounds/x.mp3')
    await guild.get_channel(int(p.VOICE_ID)).send_sound(sound)
    assert http.last('POST', f'/channels/{p.VOICE_ID}/soundboard/play')['json'] == {'soundId': '60000000000000900'}
    assert (await guild.fetch_soundboard_sound(60000000000000900)) == sound
    with pytest.raises(bisim.NotFound):
        await guild.fetch_soundboard_sound(1)
