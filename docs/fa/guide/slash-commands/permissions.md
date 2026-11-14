# دسترسی‌ها و بررسی‌ها

دو نوع قاعده تعیین می‌کند چه کسی می‌تواند یک دستور را اجرا کند. **دسترسی‌های پیش‌فرض** و **محل اجرا** همراه
دستور به بی‌سیم فرستاده می‌شوند و بی‌سیم پیش از آن‌که چیزی به ربات برسد آن‌ها را اعمال می‌کند. **بررسی‌ها**
(checks) وقتی دستور می‌رسد در خود ربات اجرا می‌شوند و بررسی ردشده به رسیدگی‌کننده‌های خطای شما می‌رود.

## دسترسی‌های پیش‌فرض

```python
@client.tree.command(description='Ban a member')
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def ban(interaction: bisim.Interaction, member: bisim.Member, reason: Optional[str] = None) -> None:
    await member.ban(reason=reason)
    await interaction.response.send_message(f'Banned {member}.', ephemeral=True)
```

- بی‌سیم دستور را از اعضایی که هر یک از این دسترسی‌ها را نداشته باشند پنهان می‌کند و در کانالی که آن‌ها را
  نداشته باشند اجرایش را رد می‌کند. مدیران کل (Administrator) همیشه می‌توانند از آن استفاده کنند.
- `@app_commands.default_permissions()` بدون هیچ دسترسی، دستور را فقط برای مدیران کل نگه می‌دارد.
- نام‌ها همان ویژگی‌های `bisim.Permissions` هستند، با بیت‌های دسترسی دیسکورد.
- بی‌سیم تنظیم دسترسی جداگانه برای هر دستور ندارد: صاحبان سرور نمی‌توانند تغییر دهند چه کسی از یک دستور
  استفاده کند و `AppCommand.fetch_permissions()` خطای `bisim.NotSupported` می‌دهد.
- برای یک گروه، آن را روی خود گروه بگذارید؛ روی زیردستور نادیده گرفته می‌شود.

جدا از این‌ها، در سرور عضو باید در آن کانال دسترسی **استفاده از دستورهای برنامه‌ها** (Use Application
Commands) را هم داشته باشد و محروم موقت نباشد.

## دستور کجا اجرا می‌شود

بی‌سیم دستورها را در سرورها و در پیام خصوصی خود ربات اجرا می‌کند و به‌طور پیش‌فرض هر دو مجازند. برای محدود
کردن دستور به یکی از آن‌ها:

- `@app_commands.guild_only()`: فقط سرورها.
- `@app_commands.dm_only()`: فقط پیام خصوصی ربات.
- `@app_commands.allowed_contexts(guilds=True, dms=False)`: همان انتخاب، به‌صورت صریح.

این‌ها را هم بی‌سیم اعمال می‌کند، پس هیچ رسیدگی‌کنندهٔ خطایی صدا زده نمی‌شود.
`CommandTree(client, allowed_contexts=...)` یک پیش‌فرض برای همهٔ دستورهای درخت تعیین می‌کند.
`private_channel_only()` دستور را به پیام خصوصی ربات محدود می‌کند، چون بی‌سیم محل خصوصی دیگری برای دستورها
ندارد.

## بررسی‌ها

بررسی‌های `app_commands.checks` در خود ربات اجرا می‌شوند:

```python
from bisim.app_commands import checks


@client.tree.command(description='Delete recent messages')
@checks.has_permissions(manage_messages=True)       # the member, in this channel
@checks.bot_has_permissions(manage_messages=True)   # the bot, in this channel
@checks.cooldown(1, 30.0)                            # once every 30 seconds per member
async def clean(interaction: bisim.Interaction, count: app_commands.Range[int, 1, 100]) -> None:
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=count)  # type: ignore[union-attr]
    await interaction.edit_original_response(content=f'Deleted {len(deleted)} messages.')
```

| بررسی | خطای ردشدن |
| --- | --- |
| `checks.has_permissions(**perms)` | `app_commands.MissingPermissions` |
| `checks.bot_has_permissions(**perms)` | `app_commands.BotMissingPermissions` |
| `checks.has_role(name_or_id)` | `app_commands.MissingRole` |
| `checks.has_any_role(*names_or_ids)` | `app_commands.MissingAnyRole` |
| `checks.cooldown(rate, per, key=...)` | `app_commands.CommandOnCooldown` |
| `checks.dynamic_cooldown(factory, key=...)` | `app_commands.CommandOnCooldown` |

`has_permissions` مقدار `interaction.permissions` و `bot_has_permissions` مقدار
`interaction.app_permissions` را می‌خواند: بی‌سیم هر دو را برای کانالی که دستور در آن اجرا می‌شود حساب
می‌کند. بررسی‌های نقش در پیام خصوصی خطای `app_commands.NoPrivateMessage` می‌دهند. `key` در محدودیت تکرار
(cooldown) تعیین می‌کند چه کسانی در آن شریک‌اند: به‌طور پیش‌فرض هر عضو محدودیت خودش را دارد،
`key=lambda i: i.guild_id` برای هر سرور یکی می‌سازد و `key=lambda i: None` یکی برای همه.

بررسی خودتان تابعی است که تعامل را می‌گیرد و `True` یا `False` برمی‌گرداند (یا یک
`app_commands.AppCommandError` می‌دهد)؛ می‌تواند `async` باشد:

```python
def is_staff(interaction: bisim.Interaction) -> bool:
    return any(role.name == 'Staff' for role in getattr(interaction.user, 'roles', []))


@client.tree.command(description='Staff only')
@app_commands.check(is_staff)
async def staff(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Hello, staff member.', ephemeral=True)
```

بررسی‌ای که `False` برگرداند خطای `app_commands.CheckFailure` می‌دهد. برای بررسی همهٔ دستورهای یک گروه،
`interaction_check()` گروه را بازنویسی کنید؛ برای کل درخت، از `CommandTree` ارث ببرید و
`interaction_check()` آن را بازنویسی کنید.

## رسیدگی به خطاها

خطاهای بررسی‌ها، تبدیل‌گرها و خود دستور به این ترتیب می‌رسند: رسیدگی‌کنندهٔ خود دستور (`@command.error`)،
`on_error` گروه‌های والد، `cog_app_command_error` کاگ و در پایان `on_error` درخت. خطایی که در کد شما رخ دهد
پیچیده در `app_commands.CommandInvokeError` می‌رسد و خطای اصلی در `.original` است.

```python
import logging

log = logging.getLogger(__name__)


@client.tree.error
async def on_app_command_error(interaction: bisim.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CommandOnCooldown):
        text = f'Slow down: try again in {error.retry_after:.0f} seconds.'
    elif isinstance(error, (app_commands.MissingPermissions, app_commands.MissingRole)):
        text = 'You are not allowed to do that here.'
    elif isinstance(error, app_commands.BotMissingPermissions):
        text = f'I need these permissions: {", ".join(error.missing_permissions)}.'
    else:
        log.exception('Error in a command', exc_info=error)
        text = 'Something went wrong.'
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
```

`@client.tree.error` جای رسیدگی‌کنندهٔ پیش‌فرض درخت را می‌گیرد که فقط خطا را ثبت می‌کند، پس آن‌چه را به آن
رسیدگی نمی‌کنید خودتان ثبت کنید. همهٔ بررسی‌ها و کلاس‌های خطا در [مرجع API](../../reference.md) آمده‌اند.
