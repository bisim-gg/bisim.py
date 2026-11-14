# کاگ‌ها و افزونه‌ها

وقتی ربات بزرگ می‌شود، کار کردن با یک فایل سخت می‌شود. **کاگ** (cog) دستورها، شنونده‌ها و داده‌ای را که بین آن‌ها
مشترک است در یک کلاس جمع می‌کند، و **افزونه** (extension) ماژولی است که ربات در حین اجرا بارگذاری، حذف و دوباره
بارگذاری می‌کند.

## یک کاگ

```python
import bisim
from bisim.ext import commands


class Greetings(commands.Cog):
    """Says hello."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.last_member = None

    @commands.Cog.listener()
    async def on_member_join(self, member: bisim.Member) -> None:
        channel = member.guild.system_channel
        if channel is not None:
            await channel.send(f'Welcome, {member.mention}!')

    @commands.command()
    async def hello(self, ctx: commands.Context, *, member: bisim.Member = None) -> None:
        """Says hello to you or to someone else."""
        member = member or ctx.author
        if self.last_member is None or self.last_member.id != member.id:
            await ctx.send(f'Hello {member.display_name}!')
        else:
            await ctx.send(f'Hello {member.display_name}... this feels familiar.')
        self.last_member = member
```

- دستورهای داخل کاگ با `@commands.command()` و `@commands.group()` ساخته می‌شوند، نه با `@bot.command()`، و نخستین
  پارامترشان `self` است.
- شنونده‌ها با `@commands.Cog.listener()` ساخته می‌شوند. نام متد همان نام رویداد است (`on_member_join`)؛ برای
  استفاده از نام دیگری برای متد، رویداد را بدهید: `@commands.Cog.listener('on_message')`.
- هر نامی در کلاس بین دستورهایش مشترک است، پس `self.bot` و `self.last_member` به اندازهٔ عمر کاگ باقی می‌مانند.

کاگ را با `await bot.add_cog(...)` اضافه کنید که یک coroutine است. جای معمولش `setup_hook` است:

```python
class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.add_cog(Greetings(self))


bot = MyBot(command_prefix='!', intents=bisim.Intents.default())
```

`bot.get_cog('Greetings')` کاگ را برمی‌گرداند، `bot.cogs` فهرست کاگ‌هاست و `await bot.remove_cog('Greetings')` یک کاگ
را همراه دستورها و شنونده‌هایش حذف می‌کند. نام کاگ همان نام کلاسش است؛ `class Greetings(commands.Cog, name='Hello')`
آن را تغییر می‌دهد، و docstring کلاس توضیح کاگ در دستور راهنماست.

## متدهای ویژه

کاگ می‌تواند این متدها را داشته باشد؛ هر کدام فقط روی همان کاگ اثر دارد:

| متد | کاری که می‌کند |
| --- | --- |
| `async def cog_load(self)` | هنگام افزودن کاگ اجرا می‌شود؛ جای خوبی برای باز کردن یک اتصال |
| `async def cog_unload(self)` | هنگام حذف کاگ و هنگام بسته شدن ربات اجرا می‌شود |
| `def cog_check(self, ctx)` | یک [بررسی](checks.md) برای همهٔ دستورهای کاگ؛ می‌تواند coroutine باشد |
| `async def cog_command_error(self, ctx, error)` | کنترل‌کنندهٔ خطا برای دستورهای کاگ |
| `async def cog_before_invoke(self, ctx)` و `async def cog_after_invoke(self, ctx)` | پیش و پس از هر دستور اجرا می‌شوند |
| `def bot_check(self, ctx)` | یک بررسی سراسری که تا وقتی کاگ بارگذاری شده ثبت است |

کاگ می‌تواند دستور اسلش هم داشته باشد: متدهایی که با `@app_commands.command()` تزئین شده‌اند هنگام افزودن کاگ به
درخت دستورهای ربات اضافه می‌شوند. `commands.GroupCog` خود کاگ را یک گروه دستور اسلش می‌کند که نامش با `group_name=`
تعیین می‌شود (صفحهٔ [زیردستورها و گروه‌ها](../slash-commands/groups.md) را ببینید)؛ فقط دستورهای اسلش کاگ به این گروه
می‌پیوندند.

## افزونه‌ها

افزونه یک ماژول پایتون است با تابعی به نام `setup`، که معمولاً coroutine است و ربات را دریافت می‌کند:

```python
# cogs/greetings.py
from bisim.ext import commands


class Greetings(commands.Cog):
    ...


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Greetings(bot))
```

آن را با مسیر import اش بارگذاری کنید:

```python
class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.load_extension('cogs.greetings')
```

`await bot.unload_extension('cogs.greetings')` کاگ‌ها، دستورها و شنونده‌های آن را حذف می‌کند و اگر تابع
`teardown(bot)` داشته باشد آن را صدا می‌زند. `await bot.reload_extension('cogs.greetings')` آن را در یک قدم حذف و
دوباره بارگذاری می‌کند، پس می‌توانید بدون راه‌اندازی دوبارهٔ ربات یک دستور را تغییر دهید؛ اگر کد تازه بارگذاری نشود،
نسخهٔ قبلی برگردانده می‌شود و خطا اعلام می‌شود.

```python
@bot.command()
@commands.is_owner()
async def reload(ctx: commands.Context, name: str) -> None:
    await bot.reload_extension(f'cogs.{name}')
    await ctx.send(f'Reloaded {name}.')
```

بارگذاری می‌تواند این خطاها را بدهد: `commands.ExtensionNotFound`، `commands.ExtensionAlreadyLoaded`،
`commands.NoEntryPointError` (بدون `setup`) یا `commands.ExtensionFailed` (خود ماژول یا `setup` آن خطا داده است).
`bot.extensions` نام افزونه‌های بارگذاری‌شده را به ماژول‌هایشان نگاشت می‌کند.

کلاس‌های کاگ و افزونه در [مرجع API](../../reference.md) آمده‌اند.
