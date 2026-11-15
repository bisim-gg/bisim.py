# Voice

Joining voice channels and playing sound, with discord.py's classes. Needs `pip install "bisim.py[voice]"`.
The [Voice guide](../guide/topics/voice.md) has examples.

::: bisim.VoiceClient

::: bisim.VoiceProtocol

## Audio sources

Every source produces 16-bit 48 kHz stereo PCM in 20 ms frames. The ffmpeg sources need ffmpeg on `PATH` (or
`executable=`).

::: bisim.AudioSource

::: bisim.PCMAudio

::: bisim.FFmpegAudio

::: bisim.FFmpegPCMAudio

::: bisim.FFmpegOpusAudio

::: bisim.PCMVolumeTransformer

## Soundboard

::: bisim.SoundboardSound

::: bisim.VoiceChannelEffect

::: bisim.VoiceChannelSoundEffect

## Opus

There is no Opus to load on Bisim. These are kept so discord.py code that calls them runs unchanged.

::: bisim.opus.load_opus

::: bisim.opus.is_loaded
