# Voice

A bot can join a voice channel, play sound into it and hear what people say. The API is discord.py's:
`await channel.connect()` gives a `VoiceClient`, and `vc.play(source)` plays any audio source. A discord.py
music or voice bot moves over by changing the import.

## Installing

Voice is an optional extra:

```sh
pip install "bisim.py[voice]"
```

It brings in LiveKit's Python SDK, which carries the sound between the bot and Bisim's voice servers. Without
it, `channel.connect()` raises `RuntimeError` with the command above.

Playing files and URLs needs [ffmpeg](https://ffmpeg.org), as in discord.py:

=== "Linux"

    ```sh
    sudo apt install ffmpeg
    ```

=== "macOS"

    ```sh
    brew install ffmpeg
    ```

=== "Windows"

    Download a build from [ffmpeg.org](https://ffmpeg.org/download.html), unpack it and add its `bin` folder to
    `PATH`, or pass the full path of `ffmpeg.exe` as `executable=` to the source.

There is no PyNaCl, libopus or DAVE library to install: Bisim's voice takes plain PCM and encodes it on the
way. `bisim.opus.load_opus()` and `bisim.opus.is_loaded()` still work, so code that calls them runs
unchanged.

The bot needs **View Channel**, **Connect** and **Speak** in the channel (and **Use Soundboard** for
[sounds](#the-soundboard)).

## Joining

```python
import bisim
from bisim import app_commands


@tree.command(description='Join your voice channel')
async def join(interaction: bisim.Interaction) -> None:
    voice = interaction.user.voice
    if voice is None or voice.channel is None:
        await interaction.response.send_message('Join a voice channel first.', ephemeral=True)
        return
    await voice.channel.connect()
    await interaction.response.send_message(f'Joined {voice.channel.name}.')
```

`connect()` returns once the bot is in the channel. A bot is in at most one voice channel per server:
connecting a second time in the same server raises `bisim.ClientException`, and `guild.voice_client` is
the connection the bot already has (`None` without one). `client.voice_clients` lists them all.

`connect()` takes discord.py's arguments: `timeout` (seconds, 60 by default), `reconnect` (join again if
the connection is lost, on by default), `self_mute`, `self_deaf` and `cls` (another `VoiceProtocol`, such
as `voice_recv.VoiceRecvClient`).

## Playing a file or a URL

```python
source = bisim.FFmpegPCMAudio('song.mp3')
interaction.guild.voice_client.play(source, after=lambda error: print('Finished', error))
```

`after` is called once the source ends, is stopped or fails, with the error or `None`. It runs on the
player's thread, not on the event loop, so reach the loop with `asyncio.run_coroutine_threadsafe`:

```python
def after_playing(error) -> None:
    coro = channel.send('Done.' if error is None else f'Playback failed: {error}')
    asyncio.run_coroutine_threadsafe(coro, client.loop)


vc.play(bisim.FFmpegPCMAudio('song.mp3'), after=after_playing)
```

A URL works the same way when it points at audio itself (a file or a stream, not a web page). These ffmpeg
options keep a network stream going through short drops:

```python
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
vc.play(bisim.FFmpegPCMAudio('https://example.com/radio.mp3', **FFMPEG_OPTIONS))
```

`FFmpegOpusAudio` and `FFmpegOpusAudio.from_probe()` work too, with the same arguments. On Bisim they decode
to PCM like `FFmpegPCMAudio`, so `bitrate` and `codec` have no effect.

When ffmpeg fails (a missing file, a URL it cannot open), `after` gets a `bisim.FFmpegProcessError`.

To play sound you make yourself, give `PCMAudio` a file-like object of 16-bit 48 kHz stereo PCM:

```python
import io

vc.play(bisim.PCMAudio(io.BytesIO(pcm_bytes)))
```

Any class with a `read()` that returns 20 ms of that format (3,840 bytes) and `b''` at the end is an
`AudioSource` too.

## Volume, pause and stop

```python
vc.play(bisim.PCMVolumeTransformer(bisim.FFmpegPCMAudio('song.mp3'), volume=0.5))

vc.source.volume = 0.25  # a quarter, changed while it plays
vc.pause()
vc.resume()
vc.stop()  # calls after(None)
```

`PCMVolumeTransformer` takes a volume from 0.0 up to 2.0. `vc.is_playing()` and `vc.is_paused()` tell the
state, and setting `vc.source` swaps what is playing without stopping. `play()` while something is playing
raises `bisim.ClientException`: stop first, or keep a queue and play the next song from `after`.

## Moving and leaving

```python
await vc.move_to(other_channel)  # what is playing keeps playing
await vc.disconnect()
```

`await guild.change_voice_state(channel=vc.channel, self_mute=True, self_deaf=True)` changes the bot's own
mute and deafen, which everyone sees on its name. A self-muted bot is not heard; a self-deafened bot receives
nothing.

The connection follows what happens on the server:

- A moderator moves the bot: it joins the new channel, and playback goes on.
- A moderator disconnects the bot: the voice client ends, `after` is called and `guild.voice_client` is
  `None` again.
- A moderator server-mutes the bot: nobody hears it until the mute is lifted; playback goes on meanwhile.
- The connection drops: with `reconnect=True` (the default) the bot joins again by itself, and the player
  waits for it (up to `timeout` seconds).

`on_voice_state_update` reports the bot's own joins, moves and leaves like everyone else's, and
`member.voice` and `VoiceChannel.members` include it.

## Receiving voice

`bisim.ext.voice_recv` receives what people say, with the API of `discord-ext-voice-recv`, the add-on most
discord.py bots use for it. Connect with `VoiceRecvClient` and listen with a sink:

```python
from bisim.ext import voice_recv


def callback(user, data: voice_recv.VoiceData) -> None:
    print(f'{user} sent {len(data.pcm)} bytes')


vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
vc.listen(voice_recv.BasicSink(callback))
```

Each person's audio arrives on its own, as 20 ms of 16-bit 48 kHz stereo PCM per call (`data.pcm`, 3,840
bytes); `data.opus` is `None`, since there is no Opus. The callback runs on the receive thread, like `after`.

Record to a wave file, one person or everyone mixed:

```python
vc.listen(voice_recv.UserFilter(voice_recv.WaveSink('sara.wav'), member))
# later
vc.stop_listening()  # closes the file
```

`vc.listen(sink, after=...)` calls `after` once listening stops, after the sink is cleaned up.
`vc.is_listening()`, `vc.stop_listening()` and `vc.stop()` (playing and listening) work as in the add-on.

While listening, the client dispatches `on_voice_member_speaking_start(member)`,
`on_voice_member_speaking_stop(member)` and `on_voice_member_disconnect(member, ssrc)`. A sink can listen to
them too:

```python
class Recorder(voice_recv.AudioSink):
    def wants_opus(self) -> bool:
        return False

    def write(self, user, data) -> None:
        ...

    def cleanup(self) -> None:
        ...

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: bisim.Member) -> None:
        print(f'{member} started speaking')
```

The bot receives audio only while it listens and is not deafened, so a music bot that never listens
downloads nothing.

## The soundboard

```python
sounds = await guild.fetch_soundboard_sounds()
await vc.channel.send_sound(sounds[0])
```

The bot must be in that channel. Everyone in the channel hears the sound; it does not go through the bot's
own audio, so it plays on top of whatever the bot is playing.

## A small music bot

```python
import asyncio
from collections import deque

import bisim
from bisim import app_commands

client = bisim.Client(intents=bisim.Intents.default())
tree = app_commands.CommandTree(client)
queues: dict[int, deque[str]] = {}


def play_next(guild: bisim.Guild) -> None:
    queue = queues.get(guild.id)
    vc = guild.voice_client
    if not queue or vc is None:
        return
    source = bisim.PCMVolumeTransformer(bisim.FFmpegPCMAudio(queue.popleft()), volume=0.5)
    vc.play(source, after=lambda error: client.loop.call_soon_threadsafe(play_next, guild))


@tree.command(description='Play a link to an audio file')
async def play(interaction: bisim.Interaction, url: str) -> None:
    voice = interaction.user.voice
    if voice is None or voice.channel is None:
        await interaction.response.send_message('Join a voice channel first.', ephemeral=True)
        return
    vc = interaction.guild.voice_client or await voice.channel.connect()
    queues.setdefault(interaction.guild.id, deque()).append(url)
    if not vc.is_playing() and not vc.is_paused():
        play_next(interaction.guild)
    await interaction.response.send_message('Added to the queue.')


@tree.command(description='Leave the voice channel')
async def leave(interaction: bisim.Interaction) -> None:
    queues.pop(interaction.guild.id, None)
    if interaction.guild.voice_client is not None:
        await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message('Bye.')
```

## What differs from Discord

- **Sound only.** A bot never sends video or a screen share.
- **One voice channel per server**, as on Discord: joining another channel of the same server leaves the
  first, so use `move_to()`.
- **No DM or group DM calls** for bots.
- **Nothing to install besides the extra** (and ffmpeg for files and URLs): no PyNaCl, libopus or DAVE.
- `FFmpegOpusAudio` decodes to PCM, and a source whose `is_opus()` returns `True` cannot be played
  (`bisim.ClientException`).
- The encoder arguments of `play()` (`bitrate`, `fec`, `bandwidth` and the rest) are accepted and have no
  effect.
- `vc.latency` is the round trip time to the voice server, measured every few seconds; `vc.session_id` is
  `None`.
- Receiving gives PCM only: `VoiceData.opus` is `None` and the RTCP events of the add-on never fire.
