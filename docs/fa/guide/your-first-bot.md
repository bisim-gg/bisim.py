# نخستین ربات

در پوشهٔ پروژه یک فایل `bot.py` بسازید:

```python
import os

import bisim

# Accepted for compatibility with discord.py; Bisim has no intents
intents = bisim.Intents.default()
client = bisim.Client(intents=intents)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')


@client.event
async def on_message(message: bisim.Message):
    # Ignore messages from bots, this one included
    if message.author.bot:
        return
    if message.content == '!ping':
        await message.reply(f'Pong! {round(client.latency * 1000)} ms')


# Read the token from the BISIM_TOKEN environment variable
client.run(os.environ['BISIM_TOKEN'])
```

با توکنی که در `BISIM_TOKEN` گذاشته‌اید اجرایش کنید (صفحهٔ [ساخت برنامه](creating-an-application.md) را
ببینید):

```sh
python bot.py
```

باید عبارت `Logged in as ...` را ببینید. در کانالی که ربات به آن دسترسی دارد `!ping` بنویسید تا ربات پاسخ دهد.
برای متوقف کردن ربات Ctrl+C را بزنید.

## چه اتفاقی افتاد

- `bisim.Client` اتصال شما به بی‌سیم است. گزینهٔ `intents` را مثل discord.py می‌گیرد، اما بی‌سیم آن را نادیده
  می‌گیرد: ربات هر رویدادی را که دسترسی‌هایش اجازه بدهند دریافت می‌کند، از جمله متن همهٔ پیام‌ها.
- `@client.event` یک coroutine را به‌عنوان کنترل‌کنندهٔ رویداد ثبت می‌کند. نام تابع مشخص می‌کند کدام رویداد را
  کنترل می‌کند، پس باید دقیقاً درست نوشته شود، مثل `on_message`. صفحهٔ [رویدادها](topics/events.md) بقیه را
  فهرست می‌کند.
- `client.run()` فراخوانی‌ای است که تا پایان کار ربات برنمی‌گردد. ثبت گزارش‌ها (logging) را راه می‌اندازد، با
  توکن وارد می‌شود، `setup_hook` را صدا می‌زند و سپس به گیت‌وی بی‌سیم وصل می‌شود و اگر اتصال قطع شد، خودش
  دوباره وصل می‌شود. هر چیزی که بعد از آن بنویسید، فقط پس از متوقف شدن ربات اجرا می‌شود.
- `message.author.bot` برای ربات‌ها `True` است. بدون این بررسی، ربات ممکن است در یک حلقه به خودش پاسخ دهد.
- `client.latency` فاصلهٔ زمانی، بر حسب ثانیه، میان یک ضربان (heartbeat) و پاسخ بی‌سیم به آن است.

## هنگام شروع چه می‌گذرد

گیت‌وی بی‌سیم رویداد READY ندارد که سرورهای ربات را با خود بیاورد، پس bisim.py پیش از صدا زدن `on_ready`
حافظهٔ خود را خودش پر می‌کند:

1. کاربر ربات و فهرست سرورهایش را از API می‌خواند.
2. برای هر سرور کانال‌ها، نقش‌ها، اعضا، ایموجی‌های سفارشی، استیکرها و وضعیت‌های صوتی را بارگذاری می‌کند و
   سپس در رویدادهای آن سرور مشترک می‌شود. برای هر سرور رویداد `on_guild_available` رخ می‌دهد.
3. وقتی همهٔ سرورها بارگذاری شدند، `on_ready` را صدا می‌زند. از این لحظه `client.guilds`،
   `client.get_channel()` و بقیهٔ حافظه پر است.

به همین دلیل رباتی که در سرورهای زیادی است کمی دیرتر آماده می‌شود. `on_ready` یک بار رخ می‌دهد. اگر اتصال قطع
شود، کتاب‌خانه دوباره وصل می‌شود، سرورها را دوباره بارگذاری می‌کند و به‌جای آن `on_resumed` را صدا می‌زند.

!!! tip "پیشنهاد"

    کدی که باید یک بار و پیش از هر رویدادی اجرا شود، جایش در `setup_hook` است، نه در `on_ready`. صفحه‌های
    [دستورهای اسلش](slash-commands/syncing.md) برای همگام‌سازی دستورها از آن استفاده می‌کنند.

## تنظیم وضعیت

`change_presence` وضعیت و فعالیت ربات را تنظیم می‌کند. این متد وقتی ربات وصل است کار می‌کند، مثلاً در
`on_ready`:

```python
@client.event
async def on_ready():
    await client.change_presence(status=bisim.Status.idle, activity=bisim.Game(name='with Python'))
```

برای شروع با یک وضعیت مشخص، آن را به کلاینت بدهید:

```python
client = bisim.Client(
    intents=bisim.Intents.default(),
    status=bisim.Status.online,
    activity=bisim.Activity(type=bisim.ActivityType.watching, name='the server'),
)
```

| فعالیت | چطور نمایش داده می‌شود |
| --- | --- |
| `bisim.Game(name='chess')` | در حال بازی chess |
| `bisim.Streaming(name='a match', url='https://example.com/live')` | در حال پخش a match |
| `bisim.Activity(type=bisim.ActivityType.listening, name='music')` | در حال گوش دادن به music |
| `bisim.Activity(type=bisim.ActivityType.watching, name='the server')` | در حال تماشای the server |
| `bisim.Activity(type=bisim.ActivityType.competing, name='a quiz')` | در حال رقابت در a quiz |
| `bisim.CustomActivity(name='Ask me anything', emoji='👋')` | یک وضعیت سفارشی با ایموجی |

وضعیت‌ها `bisim.Status.online`، `idle`، `dnd` و `invisible` هستند.

## قدم‌های بعدی

- به‌جای خواندن پیام‌ها، به دستورهای اسلش پاسخ دهید: [دستورهای اسلش](slash-commands/index.md).
- دستورهایی مثل `!help` را ترجیح می‌دهید؟ از [bisim.ext.commands](commands/index.md) استفاده کنید.
- همهٔ رویدادهایی را که ربات می‌تواند کنترل کند ببینید: [رویدادها](topics/events.md).
