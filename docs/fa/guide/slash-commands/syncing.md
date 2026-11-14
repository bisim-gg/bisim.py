# ثبت و همگام‌سازی

گذاشتن دکوراتور روی یک تابع فقط دستور را به `CommandTree` شما، در برنامهٔ خودتان، اضافه می‌کند. اعضا وقتی
دستور را می‌بینند که درخت **همگام‌سازی** شده باشد: `await tree.sync()` همهٔ دستورها را در یک درخواست به
بی‌سیم می‌فرستد.

## دستورهای سراسری و دستورهای سرور

```python
await tree.sync()                       # the global commands
await tree.sync(guild=bisim.Object(id=GUILD_ID))  # the commands of one server
```

- دستور **سراسری** در همهٔ سرورهایی که ربات به آن‌ها اضافه شده و در پیام خصوصی ربات در دسترس است.
- دستور **سرور** فقط در همان سرور وجود دارد. آن را با `guild=` یا `guilds=` روی دکوراتور، یا با
  `tree.add_command(command, guild=...)` اضافه کنید و بعد همان سرور را همگام کنید.
- وقتی سروری دستوری هم‌نام با یک دستور سراسری داشته باشد، اعضا در آن سرور دستور خود سرور را می‌بینند.

هنگام ساختن ربات، دستورهای سراسری را در یک سرور آزمایشی کپی کنید و فقط همان سرور را همگام کنید:

```python
TEST_GUILD = bisim.Object(id=123456789012345678)


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)
```

`copy_global_to()` فقط درخت را در حافظه تغییر می‌دهد؛ دستورهای سراسری تا وقتی همگام‌سازی سراسری نکنید سراسری
می‌مانند.

## همگام‌سازی همهٔ مجموعه را جایگزین می‌کند

بی‌سیم دستورها را یکی‌یکی اضافه یا به‌روز نمی‌کند: `sync()` **همهٔ** دستورهای آن محدوده (سراسری، یا یک سرور) را
با آن‌چه در درخت شماست جایگزین می‌کند. دستوری که از کد حذف کرده‌اید در همگام‌سازی بعدی از بی‌سیم هم حذف می‌شود و
دستوری که فقط برنامهٔ دیگری ثبت کرده باشد هم پاک می‌شود. همگام‌سازی را از همان یک برنامه‌ای انجام دهید که همهٔ
دستورهای ربات در آن است.

برای حذف عمدی دستورها:

```python
tree.remove_command('ping')               # one global command
tree.clear_commands(guild=TEST_GUILD)     # every command of the test server
await tree.sync(guild=TEST_GUILD)
```

## کی همگام کنیم

`setup_hook` یک بار، پس از ورود و پیش از اتصال ربات، اجرا می‌شود؛ پس همگام‌سازی در آن برای یک ربات کوچک
مناسب است. در `on_ready` یا با هر پیام همگام نکنید: هر همگام‌سازی درخواستی است که کل مجموعه را بازنویسی
می‌کند. بسیاری از ربات‌ها فقط وقتی صاحبشان بخواهد، با یک دستور پیشوندی، همگام می‌شوند:

```python
import bisim
from bisim.ext import commands

bot = commands.Bot(command_prefix='!', intents=bisim.Intents.default())


@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context, scope: str = 'global') -> None:
    """Sends the slash commands to Bisim: !sync, or !sync here for this server only."""
    if scope == 'here' and ctx.guild is not None:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
    else:
        synced = await bot.tree.sync()
    await ctx.send(f'Synced {len(synced)} commands.')
```

## خواندن آن‌چه بی‌سیم دارد

`sync()` دستورهایی را که بی‌سیم ذخیره کرده به‌صورت شیءهای `app_commands.AppCommand` برمی‌گرداند.
`fetch_commands()` آن‌ها را بدون هیچ تغییری می‌خواند:

```python
commands_now = await tree.fetch_commands()                # global
server_commands = await tree.fetch_commands(guild=TEST_GUILD)
for command in commands_now:
    print(command.id, command.name, command.mention)
```

`command.mention` متنی به شکل `</name:id>` است که دستور را در یک پیام به‌صورت پیوند نشان می‌دهد.

## محدودیت‌ها و خطاها

- حداکثر ۱۰۰ دستور در هر محدوده، همراه با دستورهای منوی راست‌کلیک؛ حداکثر ۲۵ گزینه در هر دستور و ۲۵
  زیردستور در هر گروه.
- حداکثر ۵ [دستور منوی راست‌کلیک](context-menus.md) برای کاربر و ۵ تا برای پیام در هر محدوده.
- وقتی بی‌سیم دستورها را نپذیرد (مثلاً نام یا توضیحی که قبول ندارد)، `sync()` خطای
  `app_commands.CommandSyncFailure` را با دلیلش می‌دهد، و اگر پیش از ورود کلاینت صدا زده شود
  `app_commands.MissingApplicationID`.
- اگر [مترجم](translations.md) تنظیم شده باشد، `sync()` آن را اجرا می‌کند تا نام‌های فارسی و انگلیسی اضافه شوند.

`CommandTree` در [مرجع API](../../reference.md) آمده است.
