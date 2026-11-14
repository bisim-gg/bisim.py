# مبدل‌ها

هر ورودی یک دستور پیشوندی به‌صورت متن می‌رسد. **مبدل** (converter) آن را به چیزی که دستور لازم دارد تبدیل می‌کند و
شما با حاشیه‌نویسی نوع پارامتر یکی را انتخاب می‌کنید. اگر تبدیل شکست بخورد، دستور اجرا نمی‌شود و `on_command_error`
یک `commands.BadArgument` (یا یکی از زیرکلاس‌هایش) دریافت می‌کند.

## نوع‌های پایه

هر چیز قابل‌فراخوانی که یک رشته بگیرد به‌عنوان مبدل کار می‌کند، پس نوع‌های داخلی پایتون هم کار می‌کنند:

```python
@bot.command()
async def add(ctx: commands.Context, a: int, b: float) -> None:
    await ctx.send(f'{a} + {b} = {a + b}')
```

`bool` حالت خاصی دارد: `yes`، `y`، `true`، `t`، `1`، `enable` و `on` می‌شوند `True`؛ `no`، `n`، `false`، `f`، `0`،
`disable` و `off` می‌شوند `False`، با حروف کوچک یا بزرگ. هر چیز دیگری خطای `commands.BadBoolArgument` می‌دهد.

تابعی از خودتان هم همین‌طور کار می‌کند:

```python
def lowercase(argument: str) -> str:
    return argument.lower()


@bot.command()
async def tag(ctx: commands.Context, name: lowercase) -> None:
    await ctx.send(f'Looking for {name}')
```

## اشیای بی‌سیم

اگر نوع پارامتر یک کلاس بی‌سیم باشد، ورودی برایتان جست‌وجو می‌شود. شناسه و منشن همیشه کار می‌کنند و بیشترشان نام را
هم می‌پذیرند:

| نوع | می‌پذیرد |
| --- | --- |
| `bisim.Member` | شناسه، منشن، نام کاربری، نام نمایشی یا لقب، در همین سرور |
| `bisim.User` | شناسه، منشن، نام کاربری یا نام نمایشی |
| `bisim.TextChannel` و `bisim.VoiceChannel` و `bisim.CategoryChannel` | شناسه، منشن، پیوند یا نام |
| `bisim.abc.GuildChannel` | هر کدام از این سه |
| `bisim.Role` | شناسه، منشن یا نام |
| `bisim.Message` و `bisim.PartialMessage` | شناسه، `channel_id-message_id` یا پیوند پیام |
| `bisim.Guild` | شناسه یا نام سروری که ربات در آن است |
| `bisim.Emoji` | ایموجی سرور (`<:name:id>`)، شناسه یا نام آن |
| `bisim.PartialEmoji` | ایموجی سفارشی به شکل `<:name:id>` |
| `bisim.GuildSticker` | شناسه یا نام |
| `bisim.Invite` | پیوند یا کد دعوت |
| `bisim.Colour` | `#1a66d6`، `0x1a66d6`، `rgb(26, 102, 214)` یا نامی مثل `red` |
| `bisim.Game` | هر متنی، به‌عنوان نام بازی |
| `bisim.Object` | شناسه یا منشن، بدون جست‌وجو |

```python
@bot.command()
@commands.guild_only()
async def avatar(ctx: commands.Context, member: bisim.Member) -> None:
    await ctx.send(member.display_avatar.url)
```

هر کدام از این‌ها کلاسی هم هست که می‌توانید مستقیم به کار ببرید یا از آن زیرکلاس بسازید، مثل
`commands.MemberConverter`.

## Optional و Union و Literal

`typing.Optional[X]` نوع `X` را امتحان می‌کند؛ اگر کلمه تبدیل نشود، پارامتر `None` (یا مقدار پیش‌فرضش) را می‌گیرد و
کلمه برای پارامتر بعدی می‌ماند. `typing.Union` نوع‌ها را به ترتیب امتحان می‌کند. `typing.Literal` فقط مقدارهای فهرست‌شده
را می‌پذیرد:

```python
from typing import Literal, Optional, Union


@bot.command()
async def slap(ctx: commands.Context, member: Optional[bisim.Member] = None, *, reason: str = 'no reason') -> None:
    member = member or ctx.author
    await ctx.send(f'{ctx.author.display_name} slaps {member.display_name} for {reason}.')


@bot.command()
async def info(ctx: commands.Context, target: Union[bisim.Member, bisim.Role]) -> None:
    await ctx.send(f'{target.name}: {target.id}')


@bot.command()
async def shop(ctx: commands.Context, action: Literal['buy', 'sell'], amount: int = 1) -> None:
    await ctx.send(f'{action} {amount}')
```

## Greedy و Range

`commands.Greedy[X]` تا وقتی کلمه‌ها به `X` تبدیل شوند ادامه می‌دهد و یک فهرست به شما می‌دهد. `commands.Range` یک عدد،
یا طول یک رشته، را محدود می‌کند:

```python
import random


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, members: commands.Greedy[bisim.Member], *, reason: str = 'no reason given') -> None:
    for member in members:
        await member.kick(reason=reason)
    await ctx.send(f'Kicked {len(members)} members.')


@bot.command()
async def roll(ctx: commands.Context, sides: commands.Range[int, 2, 100] = 6) -> None:
    await ctx.send(str(random.randint(1, sides)))
```

`!kick @a @b @c being rude` سه عضو و دلیل را می‌فرستد. مقداری بیرون از بازه خطای `commands.RangeError` می‌دهد.

## فایل‌ها

پارامتری از نوع `bisim.Attachment` فایلی را می‌گیرد که به پیام پیوست شده، و `Optional[bisim.Attachment]` فایلی را که
ممکن است نباشد. نبودن فایلی که لازم است خطای `commands.MissingRequiredAttachment` می‌دهد.

## مبدل‌های خودتان

برای تبدیلی که به زمینهٔ اجرا نیاز دارد، از `commands.Converter` زیرکلاس بسازید و یک `convert` از نوع async بنویسید:

```python
class Duration(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> int:
        units = {'s': 1, 'm': 60, 'h': 3600}
        try:
            return int(argument[:-1]) * units[argument[-1]]
        except (ValueError, KeyError):
            raise commands.BadArgument(f'{argument} is not a duration like 10m or 2h.')


@bot.command()
async def remind(ctx: commands.Context, when: Duration, *, text: str) -> None:
    await ctx.send(f'I will remind you in {when} seconds.')
```

`commands.clean_content` یک مبدل آماده است: منشن‌ها را به نام ساده تبدیل می‌کند تا ربات هنگام تکرار متن کسی را صدا
نزند.

## پیش‌فرض‌ها و نام‌ها با `commands.parameter`

`commands.parameter()` (یا نام کوتاهش `commands.param()`) یک مبدل، یک مقدار پیش‌فرض، یک توضیح و نام یا پیش‌فرضی را
که در راهنما نشان داده می‌شود تعیین می‌کند. پیش‌فرضِ قابل‌فراخوانی با زمینهٔ اجرا صدا زده می‌شود، پس می‌تواند به کسی
که دستور را اجرا کرده بستگی داشته باشد:

```python
@bot.command()
async def wave(ctx: commands.Context, to: bisim.User = commands.parameter(default=lambda ctx: ctx.author)) -> None:
    await ctx.send(f'Hello {to.mention}!')
```

`commands.Author`، `commands.CurrentChannel` و `commands.CurrentGuild` پیش‌فرض‌های آماده‌اند:
`member: bisim.Member = commands.Author`.

!!! note "نکته"
    `FlagConverter` و دستورهای هیبریدی discord.py در bisim.py نیستند. برای گزینه‌ها از پارامترهای keyword-only یا
    مبدل‌ها، و برای [دستورهای اسلش](../slash-commands/index.md) از `app_commands` استفاده کنید.

کلاس‌های مبدل در [مرجع API](../../reference.md) آمده‌اند.
