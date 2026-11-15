# دستورهای پیشوندی

ربات علاوه بر دستورهای اسلش می‌تواند به پیام‌هایی پاسخ دهد که با یک پیشوند شروع می‌شوند، مثل `!roll 2d6`.
`bisim.ext.commands` این کار را به همان روش `discord.ext.commands` انجام می‌دهد: هر دستور یک coroutine است،
پارامترهایش همان ورودی‌های دستورند، و کتاب‌خانه آن‌ها را برایتان جدا، تبدیل و بررسی می‌کند.

```python
import os

import bisim
from bisim.ext import commands

intents = bisim.Intents.default()
intents.message_content = True  # prefix commands read the text (switch it on at bisim.gg/developers)

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.command()
async def ping(ctx: commands.Context) -> None:
    """Checks that the bot is alive."""
    await ctx.send(f'Pong! {round(bot.latency * 1000)} ms')


bot.run(os.environ['BISIM_TOKEN'])
```

`commands.Bot` یک `bisim.Client` است که دستور هم دارد، پس هر کاری که کلاینت می‌کند این‌جا هم کار می‌کند، و برای
دستورهای اسلش از پیش یک `CommandTree` با نام `bot.tree` دارد. دستور پیشوندی از متن پیام خوانده می‌شود، پس ربات به
اینتنت ویژهٔ `message_content` نیاز دارد که باید در [bisim.gg/developers](https://bisim.gg/developers) روشن شود
([اینتنت‌ها](../topics/events.md#اینتنتها) را ببینید). بدون آن فقط پیشوندی که منشن خود ربات است
(`commands.when_mentioned`) کار می‌کند و کتاب‌خانه هنگام شروع هشداری ثبت می‌کند.

## پیشوند

`command_prefix` می‌تواند این‌ها باشد:

- یک رشته: `'!'`؛
- فهرستی از رشته‌ها که نخستین موردِ منطبق برنده است: `['!', '?']`؛
- `commands.when_mentioned` (منشن ربات) یا `commands.when_mentioned_or('!')` (منشن ربات یا `!`)؛
- یک تابع، معمولی یا async، که ربات و پیام را می‌گیرد و یک رشته یا فهرست برمی‌گرداند:

```python
prefixes = {}  # server id to prefix


async def get_prefix(bot: commands.Bot, message: bisim.Message):
    if message.guild is None:
        return commands.when_mentioned_or('!')(bot, message)
    return commands.when_mentioned_or(prefixes.get(message.guild.id, '!'))(bot, message)


bot = commands.Bot(command_prefix=get_prefix, intents=intents)
```

با `case_insensitive=True` دستور `!PING` هم کار می‌کند و با `strip_after_prefix=True` دستور `!  ping` هم. پیام
ربات‌ها، از جمله خود ربات، هیچ‌وقت دستوری اجرا نمی‌کنند.

اگر با `@bot.event` یک `on_message` از خودتان اضافه کنید، جای همانی را می‌گیرد که دستورها را اجرا می‌کند؛ در پایانش
`await bot.process_commands(message)` را صدا بزنید، یا به‌جایش از `@bot.listen()` استفاده کنید که یک شنونده در کنار
آن اضافه می‌کند.

## پارامترها

پارامترهای دستور بعد از `ctx` ورودی‌های آن‌اند. هر کدام یک کلمه می‌گیرد؛ علامت نقل‌قول چند کلمه را کنار هم نگه
می‌دارد و گیومهٔ فارسی «» هم علامت نقل‌قول به حساب می‌آید:

```python
@bot.command()
async def greet(ctx: commands.Context, name: str, greeting: str = 'Hello') -> None:
    await ctx.send(f'{greeting}, {name}!')
# !greet Sara           -> Hello, Sara!
# !greet "Sara Ahmadi" Hi -> Hi, Sara Ahmadi!
```

`*args` هر تعداد کلمه را به‌صورت یک tuple می‌گیرد، و یک پارامتر keyword-only بعد از `*` بقیهٔ پیام را بدون نیاز به
نقل‌قول به‌صورت یک رشته می‌گیرد. هر دستور فقط یک پارامتر keyword-only می‌تواند داشته باشد:

```python
@bot.command()
async def say(ctx: commands.Context, *, text: str) -> None:
    await ctx.send(text)


@bot.command()
async def total(ctx: commands.Context, *numbers: int) -> None:
    await ctx.send(f'{sum(numbers)}')
```

حاشیه‌نویسی نوع (annotation) کلمه‌ها را تبدیل می‌کند: `int`، `bisim.Member`، `bisim.TextChannel` و خیلی‌های دیگر.
صفحهٔ [مبدل‌ها](converters.md) را ببینید.

## زمینهٔ اجرا

نخستین پارامتر یک `commands.Context` است، یعنی همه‌چیز دربارهٔ همین بار اجرای دستور:

- `ctx.message`، `ctx.author` (در سرور یک `bisim.Member` و در پیام خصوصی یک `bisim.User`)، `ctx.guild` (در پیام
  خصوصی `None`) و `ctx.channel`؛
- `ctx.send(...)` در کانال می‌فرستد و `ctx.reply(...)` به خود پیام پاسخ می‌دهد؛
- `ctx.command`، `ctx.prefix`، `ctx.clean_prefix` و `ctx.invoked_with` نشان می‌دهند دستور چطور صدا زده شده است.

زمینهٔ اجرا یک `Messageable` است، پس `ctx.send` هر چیزی را که `channel.send` می‌گیرد قبول می‌کند: امبد، فایل و نما.

## گزینه‌ها و گروه‌ها

`@bot.command()` این گزینه‌ها را می‌گیرد: `name`، `aliases`، `help` (پیش‌فرض: docstring تابع)، `brief`،
`description`، `usage`، `hidden` و `enabled`. گروه دستوری است که زیردستور دارد:

```python
@bot.group(aliases=['t'], invoke_without_command=True)
async def tag(ctx: commands.Context) -> None:
    """Short texts you can recall."""
    await ctx.send('Use !tag show <name> or !tag add <name> <text>.')


@tag.command()
async def show(ctx: commands.Context, name: str) -> None:
    await ctx.send(tags.get(name, 'There is no tag with that name.'))


@tag.command()
async def add(ctx: commands.Context, name: str, *, text: str) -> None:
    tags[name] = text
    await ctx.send(f'Saved {name}.')
```

با `invoke_without_command=True` بدنهٔ خود گروه فقط وقتی اجرا می‌شود که زیردستوری داده نشده باشد؛ در غیر این صورت
پیش از زیردستور هم اجرا می‌شود و `ctx.invoked_subcommand` نشان می‌دهد کدام زیردستور در پی آن می‌آید.

## خطاها

خطاهای جدا کردن و تبدیل ورودی‌ها، [بررسی‌ها](checks.md) و [محدودیت تکرار](cooldowns.md) و خطاهایی که داخل دستور رخ
می‌دهند به `on_command_error` می‌رسند. خطایی که از کد خودتان بیاید داخل `commands.CommandInvokeError` پیچیده می‌شود
و خطای اصلی در `error.original` است. اگر کنترل‌کننده‌ای نباشد، کتاب‌خانه خطا را در گزارش‌ها ثبت می‌کند.

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send(f'{error}\nUsage: `{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.command.signature}`')
    else:
        raise error
```

کنترل‌کننده‌ای فقط برای یک دستور:

```python
@greet.error
async def greet_error(ctx: commands.Context, error: commands.CommandError) -> None:
    await ctx.send('Usage: !greet <name> [greeting]')
```

## اجرای ربات

`bot.run(token)` ثبت گزارش‌ها را راه می‌اندازد و تا وقتی متوقفش نکنید اجرا می‌شود. برای اینکه پیش از اتصال کاری
بکنید، مثلاً [کاگ‌ها](cogs.md) را اضافه کنید، از `setup_hook` استفاده کنید یا ربات را خودتان شروع کنید:

```python
import asyncio


async def main() -> None:
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.environ['BISIM_TOKEN'])


asyncio.run(main())
```

فایل `examples/prefix_bot.py` در مخزن یک ربات کامل با مبدل‌ها، بررسی‌ها، یک گروه، یک کاگ و یک کار پس‌زمینه است.
همهٔ کلاس‌ها و تزئین‌کننده‌ها در [مرجع API](../../reference.md) آمده‌اند.
