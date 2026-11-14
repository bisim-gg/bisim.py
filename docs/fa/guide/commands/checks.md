# بررسی‌ها

**بررسی** (check) تعیین می‌کند چه کسی می‌تواند یک دستور را اجرا کند. بررسی‌ها پیش از تبدیل ورودی‌ها اجرا می‌شوند؛ اگر
یکی شکست بخورد، دستور اجرا نمی‌شود و `on_command_error` یک `commands.CheckFailure` (یا زیرکلاسی که دلیلش را می‌گوید)
دریافت می‌کند.

## بررسی‌های آماده

آن‌ها را به‌صورت تزئین‌کننده زیر `@bot.command()` اضافه کنید:

```python
@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clean(ctx: commands.Context, count: commands.Range[int, 1, 100] = 10) -> None:
    deleted = await ctx.channel.purge(limit=count + 1)
    await ctx.send(f'Deleted {len(deleted) - 1} messages.', delete_after=5)
```

| بررسی | قبول می‌شود وقتی | خطای شکست |
| --- | --- | --- |
| `has_permissions(**perms)` | نویسنده این دسترسی‌ها را در همین کانال دارد | `MissingPermissions` |
| `bot_has_permissions(**perms)` | ربات آن‌ها را در همین کانال دارد | `BotMissingPermissions` |
| `has_guild_permissions(**perms)` | نویسنده آن‌ها را در کل سرور دارد | `MissingPermissions` |
| `bot_has_guild_permissions(**perms)` | ربات آن‌ها را در کل سرور دارد | `BotMissingPermissions` |
| `has_role(item)` | نویسنده نقش را دارد، با شناسه یا نام | `MissingRole` |
| `has_any_role(*items)` | نویسنده یکی از نقش‌ها را دارد | `MissingAnyRole` |
| `bot_has_role(item)` و `bot_has_any_role(*items)` | همین، برای ربات | `BotMissingRole` و `BotMissingAnyRole` |
| `guild_only()` | دستور در سرور به کار رفته | `NoPrivateMessage` |
| `dm_only()` | دستور در پیام خصوصی به کار رفته | `PrivateMessageOnly` |
| `is_owner()` | نویسنده مالک ربات است | `NotOwner` |
| `is_nsfw()` | کانال دارای محدودیت سنی است، یا پیام خصوصی است | `NSFWChannelRequired` |

نام دسترسی‌ها همان نام‌های `bisim.Permissions` است، مثل `manage_messages`، `kick_members`، `ban_members`،
`manage_roles` و `moderate_members`؛ نامی که وجود نداشته باشد هنگام شروع ربات خطای `TypeError` می‌دهد. بررسی‌های
کانالی از بازنویسی‌های دسترسی کانال استفاده می‌کنند که کتاب‌خانه نخستین باری که بررسی‌ای لازمشان داشته باشد از بی‌سیم
بارگذاری می‌کند.

`is_owner()` یک بار مالک برنامه را از بی‌سیم می‌پرسد، مگر اینکه به `commands.Bot` گزینهٔ `owner_id=` یا `owner_ids=`
بدهید.

## بررسی‌های خودتان

`commands.check()` یک تابع شرط را به بررسی تبدیل می‌کند. تابع شرط زمینهٔ اجرا را می‌گیرد و برای اجازه دادن به دستور
`True` برمی‌گرداند؛ می‌تواند تابعی معمولی یا یک coroutine باشد:

```python
def in_channel(name: str):
    def predicate(ctx: commands.Context) -> bool:
        return getattr(ctx.channel, 'name', None) == name

    return commands.check(predicate)


@bot.command()
@in_channel('bot-commands')
async def daily(ctx: commands.Context) -> None:
    await ctx.send('Here is your daily reward.')
```

برگرداندن `False` یک `CheckFailure` ساده می‌دهد. برای اینکه دلیلش را به کاربر بگویید، زیرکلاسی از آن را خودتان
raise کنید:

```python
class NotInBotChannel(commands.CheckFailure):
    pass


def in_bot_channel():
    async def predicate(ctx: commands.Context) -> bool:
        if getattr(ctx.channel, 'name', None) != 'bot-commands':
            raise NotInBotChannel('Use this command in #bot-commands.')
        return True

    return commands.check(predicate)
```

`commands.check_any()` وقتی قبول می‌شود که دست‌کم یکی از بررسی‌هایی که به آن داده‌اید قبول شود، وگرنه خطای
`CheckAnyFailure` می‌دهد:

```python
@bot.command()
@commands.check_any(commands.is_owner(), commands.has_role('Moderator'))
async def announce(ctx: commands.Context, *, text: str) -> None:
    await ctx.send(text)
```

## بررسی برای همهٔ دستورها

بررسی سراسری پیش از هر دستور ربات اجرا می‌شود. آن را با `@bot.check` ثبت کنید:

```python
@bot.check
async def not_blocked(ctx: commands.Context) -> bool:
    return ctx.author.id not in blocked_users
```

داخل یک [کاگ](cogs.md)، متد `cog_check` بررسی‌ای برای همهٔ دستورهای همان کاگ است:

```python
class Admin(commands.Cog):
    async def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None and ctx.author.guild_permissions.administrator
```

## گفتن اینکه چه چیزی اشتباه بود

شکست‌ها را در `on_command_error` کنترل کنید، از دقیق‌ترین کلاس تا کلی‌ترین:

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f'You need these permissions: {", ".join(error.missing_permissions)}.')
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f'I need these permissions: {", ".join(error.missing_permissions)}.')
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send('This command works in servers only.')
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(str(error) or 'You cannot use this command here.')
```

بررسی‌های دستورهای اسلش جور دیگری کار می‌کنند و به‌جای زمینهٔ اجرا روی تعامل اعمال می‌شوند: صفحهٔ
[دسترسی‌ها و بررسی‌ها](../slash-commands/permissions.md) را ببینید. تزئین‌کننده‌های بررسی در [مرجع API](../../reference.md)
آمده‌اند.
