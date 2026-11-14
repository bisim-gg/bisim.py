# دستور راهنما

`commands.Bot` یک دستور `help` همراه خودش دارد. `!help` دستورها را گروه‌بندی‌شده بر اساس [کاگ](cogs.md) فهرست
می‌کند؛ `!help roll` یک دستور و `!help Todo` یک کاگ را نشان می‌دهد. متن راهنما از کد شما می‌آید، پس راهنمای خوب با
docstringهای خوب شروع می‌شود.

## متن از کجا می‌آید

```python
@bot.command(aliases=['dice'], brief='Rolls dice')
async def roll(ctx: commands.Context, dice: str = '1d6') -> None:
    """Rolls dice written like 2d6: two dice with six sides.

    Up to 20 dice with 2 to 100 sides each.
    """
```

- `help` متن بلندی است که `!help roll` نشان می‌دهد. پیش‌فرضش docstring تابع است.
- `brief` خط کوتاه در فهرست است؛ اگر نباشد، نخستین خط `help` به کار می‌رود.
- `description` بالای متن بلند نشان داده می‌شود و `usage` جای فهرست ساخته‌شدهٔ ورودی‌ها را می‌گیرد.
- امضای دستور، این‌جا `roll [dice=1d6]`، از روی پارامترها ساخته می‌شود. `commands.parameter(description=...)` یک
  ورودی را توضیح می‌دهد و `displayed_name=` و `displayed_default=` شکل نمایش آن را تغییر می‌دهند.
- `hidden=True` دستور را از فهرست بیرون نگه می‌دارد؛ دستور همچنان کار می‌کند.
- docstring یک کاگ توضیح آن کاگ است و `commands.Bot(description=...)` بالای `!help` نشان داده می‌شود.

به‌طور پیش‌فرض فهرست فقط دستورهایی را نشان می‌دهد که کاربر اجازهٔ اجرایشان را دارد: بررسی‌ها امتحان می‌شوند و
دستوری که بررسی‌هایش رد شود کنار گذاشته می‌شود.

## دو دستور راهنمای آماده

`commands.DefaultHelpCommand` پیش‌فرض است: یک بلوک کد با دستورها زیر کاگ‌هایشان. `commands.MinimalHelpCommand`
ساده‌تر و بدون بلوک کد است. هر کدام را همراه گزینه‌هایش به ربات بدهید:

```python
bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=commands.DefaultHelpCommand(no_category='Other', sort_commands=True, dm_help=False),
)
```

| گزینه | کاری که می‌کند |
| --- | --- |
| `no_category` | عنوان دستورهایی که در هیچ کاگی نیستند (`"No Category"`) |
| `sort_commands` | دستورها را به ترتیب الفبا فهرست می‌کند (`True`) |
| `dm_help` | با `True` راهنما با پیام خصوصی فرستاده می‌شود، با `None` فقط وقتی بلند است، با `False` هرگز (پیش‌فرض) |
| `show_hidden` | دستورهای پنهان را هم فهرست می‌کند (`False`) |
| `verify_checks` | دستورهایی را که بررسی‌هایشان رد می‌شود کنار می‌گذارد (`True`) |
| `command_attrs` | گزینه‌های خود دستور راهنما، مثل `{'name': 'commands', 'aliases': ['h']}` |
| `commands_heading` و `arguments_heading` | عنوان‌ها، به درد راهنمای فارسی می‌خورند (`DefaultHelpCommand`) |
| `width` | پهنای خط در `DefaultHelpCommand` (۸۰) |

`help_command=None` دستور راهنما را حذف می‌کند و `bot.help_command = ...` در حین اجرای ربات آن را عوض می‌کند.

## دستور راهنمای خودتان

از `commands.HelpCommand` زیرکلاس بسازید و هر چه را می‌خواهید تغییر دهید بازنویسی کنید. هر متد یک نمای راهنما را
می‌فرستد و `self.context` زمینهٔ اجرای پیام `!help` است:

```python
class EmbedHelp(commands.HelpCommand):
    def get_destination(self):
        return self.context.channel

    async def send_bot_help(self, mapping) -> None:
        embed = bisim.Embed(title='Commands', colour=bisim.Colour.blurple())
        for cog, cmds in mapping.items():
            visible = await self.filter_commands(cmds, sort=True)
            if visible:
                name = cog.qualified_name if cog else 'Other'
                embed.add_field(name=name, value=' '.join(f'`{c.name}`' for c in visible), inline=False)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog) -> None:
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)
        lines = [f'`{self.get_command_signature(c)}` {c.short_doc}' for c in commands_]
        await self.get_destination().send('\n'.join(lines) or 'Nothing here.')

    async def send_group_help(self, group) -> None:
        await self.send_command_help(group)

    async def send_command_help(self, command) -> None:
        embed = bisim.Embed(title=self.get_command_signature(command), description=command.help or 'No help yet.')
        if command.aliases:
            embed.add_field(name='Aliases', value=', '.join(command.aliases))
        await self.get_destination().send(embed=embed)


bot.help_command = EmbedHelp()
```

| متد | برای |
| --- | --- |
| `send_bot_help(mapping)` | `!help`؛ `mapping` هر کاگ (یا `None`) را به دستورهایش نگاشت می‌کند |
| `send_cog_help(cog)` | `!help CogName` |
| `send_group_help(group)` | `!help group` |
| `send_command_help(command)` | `!help command` |
| `send_error_message(error)` | دستور یا زیردستور ناشناخته؛ به‌طور پیش‌فرض متن خطا را می‌فرستد |
| `get_destination()` | جایی که راهنما فرستاده می‌شود؛ پیش‌فرض همان کانال است |

`filter_commands` گزینه‌های `show_hidden` و `verify_checks` را برایتان اعمال می‌کند، `get_command_signature` خط
نحوهٔ استفاده را می‌سازد و `command.short_doc` همان خط کوتاه است. برای استفاده از راهنما در کد،
`await ctx.send_help()` راهنمای ربات و `await ctx.send_help(command)` راهنمای یک دستور را می‌فرستد.

برای اینکه راهنما در یک کاگ باشد، در `__init__` کاگ بنویسید `bot.help_command.cog = self`؛ از آن به بعد زیر همان
کاگ نشان داده می‌شود.

کلاس‌های راهنما در [مرجع API](../../reference.md) آمده‌اند.
