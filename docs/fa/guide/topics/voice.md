# صدا

ربات می‌تواند به یک کانال صوتی بپیوندد، در آن صدا پخش کند و صدای دیگران را بشنود. API همان discord.py است:
`await channel.connect()` یک `VoiceClient` می‌دهد و `vc.play(source)` هر منبع صوتی را پخش می‌کند. یک ربات
موسیقی یا صوتی discord.py با عوض کردن import به بی‌سیم می‌آید.

## نصب

صدا یک افزونهٔ اختیاری است:

```sh
pip install "bisim.py[voice]"
```

این دستور SDK پایتون LiveKit را نصب می‌کند که صدا را میان ربات و سرورهای صوتی بی‌سیم جابه‌جا می‌کند. بدون آن،
`channel.connect()` خطای `RuntimeError` می‌دهد و همین دستور را در پیامش می‌گوید.

برای پخش فایل و نشانی اینترنتی، مثل discord.py به [ffmpeg](https://ffmpeg.org) نیاز است:

=== "لینوکس"

    ```sh
    sudo apt install ffmpeg
    ```

=== "مک"

    ```sh
    brew install ffmpeg
    ```

=== "ویندوز"

    یک نسخه از [ffmpeg.org](https://ffmpeg.org/download.html) بگیرید، آن را باز کنید و پوشهٔ `bin` آن را به
    `PATH` بیفزایید، یا مسیر کامل `ffmpeg.exe` را با `executable=` به منبع بدهید.

PyNaCl، libopus یا کتاب‌خانهٔ DAVE لازم نیست: صدای بی‌سیم PCM ساده می‌گیرد و در راه خودش آن را کدگذاری می‌کند.
`bisim.opus.load_opus()` و `bisim.opus.is_loaded()` همچنان کار می‌کنند، پس کدی که آن‌ها را صدا می‌زند بی‌تغییر
اجرا می‌شود.

ربات در آن کانال به دسترسی‌های **View Channel**، **Connect** و **Speak** نیاز دارد (و برای
[صداهای ساندبورد](#soundboard) به **Use Soundboard**).

## پیوستن

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

`connect()` وقتی برمی‌گردد که ربات در کانال باشد. ربات در هر سرور حداکثر در یک کانال صوتی است: اتصال دوباره در
همان سرور خطای `bisim.ClientException` می‌دهد و `guild.voice_client` همان اتصالی است که ربات دارد (و اگر
نداشته باشد `None`). `client.voice_clients` همهٔ آن‌ها را فهرست می‌کند.

`connect()` آرگومان‌های discord.py را می‌گیرد: `timeout` (به ثانیه، پیش‌فرض ۶۰)، `reconnect` (اگر اتصال قطع
شد دوباره بپیوندد، پیش‌فرض روشن)، `self_mute`، `self_deaf` و `cls` (یک `VoiceProtocol` دیگر، مثل
`voice_recv.VoiceRecvClient`).

## پخش فایل یا نشانی اینترنتی

```python
source = bisim.FFmpegPCMAudio('song.mp3')
interaction.guild.voice_client.play(source, after=lambda error: print('Finished', error))
```

`after` یک بار پس از تمام شدن، متوقف شدن یا شکست منبع صدا زده می‌شود و خطا یا `None` را می‌گیرد. این تابع روی
رشتهٔ اجرای پخش‌کننده اجرا می‌شود، نه روی حلقهٔ رویداد؛ برای رسیدن به حلقه از
`asyncio.run_coroutine_threadsafe` استفاده کنید:

```python
def after_playing(error) -> None:
    coro = channel.send('Done.' if error is None else f'Playback failed: {error}')
    asyncio.run_coroutine_threadsafe(coro, client.loop)


vc.play(bisim.FFmpegPCMAudio('song.mp3'), after=after_playing)
```

نشانی اینترنتی هم همین‌طور کار می‌کند، به شرطی که به خود صدا اشاره کند (یک فایل یا یک جریان، نه یک صفحهٔ وب).
این گزینه‌های ffmpeg جریان شبکه را در قطعی‌های کوتاه سرپا نگه می‌دارند:

```python
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
vc.play(bisim.FFmpegPCMAudio('https://example.com/radio.mp3', **FFMPEG_OPTIONS))
```

`FFmpegOpusAudio` و `FFmpegOpusAudio.from_probe()` هم با همان آرگومان‌ها کار می‌کنند. روی بی‌سیم این‌ها مثل
`FFmpegPCMAudio` به PCM رمزگشایی می‌کنند، پس `bitrate` و `codec` اثری ندارند.

وقتی ffmpeg شکست بخورد (فایلی که نیست، نشانی‌ای که باز نمی‌شود)، `after` یک `bisim.FFmpegProcessError` می‌گیرد.

برای پخش صدایی که خودتان می‌سازید، یک شیء شبه‌فایل از PCM استریوی ۱۶ بیتی ۴۸ کیلوهرتز به `PCMAudio` بدهید:

```python
import io

vc.play(bisim.PCMAudio(io.BytesIO(pcm_bytes)))
```

هر کلاسی که `read()` آن ۲۰ میلی‌ثانیه از همین قالب (۳٬۸۴۰ بایت) و در پایان `b''` برگرداند هم یک `AudioSource`
است.

## بلندی صدا، مکث و توقف

```python
vc.play(bisim.PCMVolumeTransformer(bisim.FFmpegPCMAudio('song.mp3'), volume=0.5))

vc.source.volume = 0.25  # a quarter, changed while it plays
vc.pause()
vc.resume()
vc.stop()  # calls after(None)
```

`PCMVolumeTransformer` بلندی صدا را از ۰٫۰ تا ۲٫۰ می‌گیرد. `vc.is_playing()` و `vc.is_paused()` وضعیت را
می‌گویند و با مقدار دادن به `vc.source` می‌توان چیزی را که پخش می‌شود بدون توقف عوض کرد. فراخوانی `play()`
وقتی چیزی در حال پخش است خطای `bisim.ClientException` می‌دهد: اول متوقف کنید، یا یک صف نگه دارید و آهنگ بعدی را
از `after` پخش کنید.

## جابه‌جا شدن و ترک کردن

```python
await vc.move_to(other_channel)  # what is playing keeps playing
await vc.disconnect()
```

`await guild.change_voice_state(channel=vc.channel, self_mute=True, self_deaf=True)` بی‌صدا و ناشنوا بودن خود
ربات را تغییر می‌دهد که همه کنار نامش می‌بینند. صدای رباتی که خودش را بی‌صدا کرده شنیده نمی‌شود و رباتی که خودش
را ناشنوا کرده چیزی دریافت نمی‌کند.

اتصال از آنچه روی سرور رخ می‌دهد پیروی می‌کند:

- مدیری ربات را جابه‌جا می‌کند: ربات به کانال تازه می‌پیوندد و پخش ادامه پیدا می‌کند.
- مدیری اتصال ربات را قطع می‌کند: اتصال صوتی تمام می‌شود، `after` صدا زده می‌شود و `guild.voice_client` دوباره
  `None` می‌شود.
- مدیری ربات را در سرور بی‌صدا می‌کند: تا برداشته شدن آن کسی صدایش را نمی‌شنود؛ پخش در این میان ادامه دارد.
- اتصال قطع می‌شود: با `reconnect=True` (پیش‌فرض) ربات خودش دوباره می‌پیوندد و پخش‌کننده منتظرش می‌ماند (تا
  `timeout` ثانیه).

`on_voice_state_update` پیوستن، جابه‌جا شدن و ترک کردن خود ربات را هم مثل بقیه گزارش می‌کند و `member.voice` و
`VoiceChannel.members` آن را هم در بر می‌گیرند.

## دریافت صدا

`bisim.ext.voice_recv` صدای دیگران را دریافت می‌کند، با API افزونهٔ `discord-ext-voice-recv` که بیشتر ربات‌های
discord.py برای این کار به کار می‌برند. با `VoiceRecvClient` وصل شوید و با یک sink گوش دهید:

```python
from bisim.ext import voice_recv


def callback(user, data: voice_recv.VoiceData) -> None:
    print(f'{user} sent {len(data.pcm)} bytes')


vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
vc.listen(voice_recv.BasicSink(callback))
```

صدای هر کس جداگانه می‌رسد، در هر فراخوانی ۲۰ میلی‌ثانیه PCM استریوی ۱۶ بیتی ۴۸ کیلوهرتز (`data.pcm`، ۳٬۸۴۰
بایت)؛ `data.opus` برابر `None` است، چون Opus در کار نیست. این تابع هم مثل `after` روی رشتهٔ اجرای دریافت اجرا
می‌شود.

ضبط در یک فایل wave، برای یک نفر یا همه با هم:

```python
vc.listen(voice_recv.UserFilter(voice_recv.WaveSink('sara.wav'), member))
# later
vc.stop_listening()  # closes the file
```

`vc.listen(sink, after=...)` تابع `after` را یک بار پس از پایان گوش دادن صدا می‌زند، پس از آنکه sink جمع شد.
`vc.is_listening()`، `vc.stop_listening()` و `vc.stop()` (هم پخش و هم دریافت) مثل همان افزونه کار می‌کنند.

در زمان گوش دادن، کلاینت رویدادهای `on_voice_member_speaking_start(member)`،
`on_voice_member_speaking_stop(member)` و `on_voice_member_disconnect(member, ssrc)` را می‌فرستد. یک sink هم
می‌تواند به آن‌ها گوش دهد:

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

ربات فقط وقتی صدا دریافت می‌کند که گوش می‌دهد و ناشنوا نیست؛ پس ربات موسیقی‌ای که هیچ‌گاه گوش نمی‌دهد چیزی
دانلود نمی‌کند.

## ساندبورد { #soundboard }

```python
sounds = await guild.fetch_soundboard_sounds()
await vc.channel.send_sound(sounds[0])
```

ربات باید در همان کانال باشد. همهٔ حاضران کانال صدا را می‌شنوند؛ این صدا از صدای خود ربات نمی‌گذرد، پس روی هر
چیزی که ربات پخش می‌کند شنیده می‌شود.

## یک ربات موسیقی کوچک

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

## تفاوت‌ها با دیسکورد

- **فقط صدا.** ربات هیچ‌گاه تصویر یا اشتراک صفحه نمی‌فرستد.
- **در هر سرور یک کانال صوتی**، مثل دیسکورد: پیوستن به کانال دیگری از همان سرور کانال اول را ترک می‌کند؛ پس از
  `move_to()` استفاده کنید.
- **تماس خصوصی یا گروهی** برای ربات‌ها وجود ندارد.
- **جز همین افزونه چیزی برای نصب نیست** (و ffmpeg برای فایل و نشانی اینترنتی): نه PyNaCl، نه libopus و نه DAVE.
- `FFmpegOpusAudio` به PCM رمزگشایی می‌کند و منبعی که `is_opus()` آن `True` برگرداند پخش نمی‌شود
  (`bisim.ClientException`).
- آرگومان‌های کدگذار در `play()` (`bitrate`، `fec`، `bandwidth` و بقیه) پذیرفته می‌شوند و اثری ندارند.
- `vc.latency` زمان رفت و برگشت تا سرور صوتی است که هر چند ثانیه اندازه گرفته می‌شود؛ `vc.session_id` برابر
  `None` است.
- دریافت فقط PCM می‌دهد: `VoiceData.opus` برابر `None` است و رویدادهای RTCP آن افزونه هیچ‌گاه رخ نمی‌دهند.
