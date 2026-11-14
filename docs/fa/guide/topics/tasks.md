# کارهای پس‌زمینه

`bisim.ext.tasks` یک coroutine را طبق برنامه اجرا می‌کند: هر چند دقیقه یک بار، در ساعت‌های مشخصی از روز یا به
تعداد مشخص. کارهای جانبی را هم خودش انجام می‌دهد: حلقه را پس از قطع و وصل شدن اتصال ادامه می‌دهد، پس از خطاهای
شبکه دوباره تلاش می‌کند و پیش از شروع اجرای بعدی، منتظر تمام شدن اجرای قبلی می‌ماند.

## یک حلقهٔ ساده

```python
import bisim
from bisim.ext import tasks


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        # Start the loop once, when the bot starts
        self.report.start()

    @tasks.loop(minutes=30)
    async def report(self) -> None:
        channel = self.get_channel(123456789012345678)
        if channel is not None:
            await channel.send('Half an hour has passed.')

    @report.before_loop
    async def before_report(self) -> None:
        # The cache is empty until the bot is ready
        await self.wait_until_ready()


client = MyClient(intents=bisim.Intents.default())
```

`@tasks.loop()` این coroutine را به یک `Loop` تبدیل می‌کند. حلقه درست پس از `start()` یک بار اجرا می‌شود و سپس
هر ۳۰ دقیقه. فاصلهٔ زمانی با `seconds`، `minutes` و `hours` تعیین می‌شود که می‌توان آن‌ها را با هم به کار برد
(`minutes=1, seconds=30`).

`before_loop` یک بار پیش از نخستین اجرا رخ می‌دهد. صبر کردن برای `wait_until_ready()` در آن روش معمول است:
حلقه‌ای که در `setup_hook` شروع شود، وگرنه پیش از بارگذاری سرورها اجرا می‌شود.

## در ساعت‌های مشخص

به‌جای فاصلهٔ زمانی، `time` را بدهید: یک `datetime.time` یا فهرستی از آن‌ها. ساعت‌هایی که منطقهٔ زمانی ندارند
به وقت UTC در نظر گرفته می‌شوند:

```python
import datetime

from bisim.ext import tasks

tehran = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
times = [datetime.time(hour=9, tzinfo=tehran), datetime.time(hour=21, tzinfo=tehran)]


@tasks.loop(time=times)
async def twice_a_day() -> None:
    print('Good morning, or good evening.')
```

## تعداد مشخصی اجرا

`count` حلقه را پس از همان تعداد اجرا متوقف می‌کند و `current_loop` می‌گوید کدام اجرا در جریان است:

```python
@tasks.loop(seconds=10, count=5)
async def countdown() -> None:
    print(f'Iteration {countdown.current_loop + 1} of 5')


@countdown.after_loop
async def after_countdown() -> None:
    if countdown.is_being_cancelled():
        print('Cancelled before the end.')
    else:
        print('Done.')
```

`after_loop` یک بار و هنگام پایان حلقه اجرا می‌شود، چه حلقه کامل شده باشد، چه متوقف شده باشد و چه لغو.

## شروع و توقف

| متد | چه می‌کند |
| --- | --- |
| `start(*args, **kwargs)` | حلقه را شروع می‌کند؛ ورودی‌ها به همهٔ اجراها داده می‌شوند. اگر حلقه در حال اجرا باشد `RuntimeError` می‌دهد |
| `stop()` | می‌گذارد اجرای فعلی تمام شود و سپس حلقه را پایان می‌دهد |
| `cancel()` | حلقه را همان لحظه لغو می‌کند، حتی وسط یک اجرا |
| `restart(*args, **kwargs)` | حلقه را لغو می‌کند و دوباره شروع می‌کند |
| `change_interval(seconds=..., minutes=..., hours=..., time=...)` | برنامهٔ زمانی را از اجرای بعدی به بعد تغییر می‌دهد |
| `is_running()` | آیا حلقه در حال اجراست |
| `next_iteration` | زمان اجرای بعدی، به‌صورت یک `datetime` |

حلقه‌ای که روی یک تابع معمولی (نه متد) ساخته شده را می‌توان در `on_ready` شروع کرد. اول `is_running()` را بررسی
کنید تا دو بار شروع کردن هرگز خطا ندهد:

```python
@client.event
async def on_ready():
    if not countdown.is_running():
        countdown.start()
```

## خطاها

با `reconnect=True` که پیش‌فرض است، اجرایی که با خطای شبکه (`OSError`، `bisim.ConnectionClosed`،
`aiohttp.ClientError` یا `asyncio.TimeoutError`) شکست بخورد، با فاصله‌ای رو به افزایش دوباره اجرا می‌شود.
`add_exception_type()` نوع‌های دیگری از خطا را به این فهرست اضافه می‌کند.

هر خطای دیگری حلقه را پایان می‌دهد. به‌طور پیش‌فرض این خطا در گزارش‌ها ثبت می‌شود؛ با `error` کنترل‌کنندهٔ
خودتان را ثبت کنید:

```python
# Inside MyClient, below report
@report.error
async def report_error(self, error: Exception) -> None:
    print(f'The report failed: {error!r}')
```

کلاس `Loop` و همهٔ گزینه‌هایش در [مرجع API](../../reference.md) آمده‌اند.
