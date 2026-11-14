# اعضا و نقش‌ها

## اعضا

bisim.py هنگام اتصال، اعضای همهٔ سرورها را بارگذاری می‌کند، پس `guild.members` و `guild.get_member()` از
`on_ready` به بعد کار می‌کنند. اگر `chunk_guilds_at_startup=False` را به کلاینت بدهید، این کار انجام نمی‌شود و
اعضا فقط وقتی بارگذاری می‌شوند که خودتان بخواهید.

```python
member = guild.get_member(123456789012345678)  # from the cache, or None
member = await guild.fetch_member(123456789012345678)  # always asks Bisim
found = await guild.query_members('ali', limit=10)  # username or nickname starting with "ali"
me = guild.me  # the bot itself

async for member in guild.fetch_members(limit=None):
    print(member.display_name)
```

یک `bisim.Member` همان کاربر در یک سرور است. علاوه بر هر چه یک `bisim.User` دارد (`name`، `display_name`،
`avatar`، `bot` و `mention`)، این‌ها را هم دارد: `nick`، `joined_at`، `roles`، `top_role`،
`guild_permissions`، `status`، `activity`، `voice` و `timed_out_until`.

## نام مستعار

```python
await member.edit(nick='New name', reason='Requested')
await member.edit(nick=None)  # removes the nickname
await guild.me.edit(nick='Helper')  # the bot's own nickname
```

تغییر نام مستعار دیگران دسترسی مدیریت نام‌های مستعار (Manage Nicknames) می‌خواهد.

## دادن و گرفتن نقش

```python
role = guild.get_role(234567890123456789)
await member.add_roles(role, reason='Verified')
await member.remove_roles(role)

# Replace the whole set of roles at once
await member.edit(roles=[role_a, role_b])
```

`member.roles` نقش‌های عضو را فهرست می‌کند و با نقش پیش‌فرض سرور (`@everyone`) شروع می‌شود.
`bisim.utils.get(guild.roles, name='Moderator')` یک نقش را با نامش پیدا می‌کند.

## مدیریت اعضا

```python
import datetime

await member.timeout(datetime.timedelta(minutes=10), reason='Spamming')
await member.timeout(None)  # removes the timeout

await member.kick(reason='Breaking the rules')
await member.ban(delete_message_seconds=60 * 60 * 24, reason='Spam')
await guild.unban(bisim.Object(id=123456789012345678))

async for entry in guild.bans():
    print(entry.user, entry.reason)
```

`timeout()` برای سکوت موقت یک `timedelta` (چه مدت) یا یک `datetime` دارای منطقهٔ زمانی (تا چه زمانی) می‌گیرد، حداکثر تا ۲۸ روز؛
`member.is_timed_out()` می‌گوید سکوت موقت در جریان است یا نه. `ban()` می‌تواند پیام‌های اخیر عضو را هم پاک کند،
تا هفت روز (`delete_message_seconds` از ۰ تا ۶۰۴۸۰۰).

هر کار دسترسی خودش را می‌خواهد: Moderate Members برای سکوت موقت، Kick Members برای اخراج و Ban Members برای بن.
بی‌سیم مثل دیسکورد سلسله‌مراتب نقش‌ها را هم رعایت می‌کند: ربات فقط روی اعضایی کاری انجام می‌دهد که بالاترین
نقششان پایین‌تر از بالاترین نقش خود ربات است، و هرگز روی مالک سرور.

بی‌صدا کردن، ناشنوا کردن و جابه‌جا کردن در کانال صوتی (`member.edit(mute=True)` و `member.move_to(channel)`)
روی اعضایی کار می‌کند که در یک کانال صوتی هستند؛ برای بقیه `bisim.ClientException` می‌دهد. خود ربات نمی‌تواند
به کانال صوتی بپیوندد.

## نقش‌ها

```python
role = await guild.create_role(
    name='Helpers',
    permissions=bisim.Permissions(manage_messages=True),
    colour=bisim.Colour.green(),
    hoist=True,
    mentionable=True,
    reason='New team',
)

await role.edit(name='Helper team', colour=0x5197ED)
await role.edit(position=3)  # or guild.edit_role_positions({role: 3})
await role.delete(reason='No longer needed')
```

یک `bisim.Role` این‌ها را دارد: `name`، `colour`، `permissions`، `position`، `hoist`، `mentionable`، `members` و
`mention`. `role.is_default()` برای `@everyone` مقدار `True` دارد. مدیریت نقش‌ها دسترسی مدیریت نقش‌ها (Manage
Roles) می‌خواهد و ربات فقط نقش‌های پایین‌تر از بالاترین نقش خودش را می‌تواند مدیریت کند.

!!! note "در بی‌سیم نیست"

    آیکون نقش (`display_icon`) و رنگ‌های گرادیانی (`secondary_colour` و `tertiary_colour`) خطای
    `bisim.NotSupported` می‌دهند.

## رویدادها

`on_member_join`، `on_member_remove` و `on_member_update` (نام مستعار، نقش‌ها یا سکوت موقت) دربارهٔ اعضا خبر
می‌دهند و `on_guild_role_create`، `on_guild_role_update` و `on_guild_role_delete` دربارهٔ نقش‌ها. بی‌سیم برای بن
رویدادی نمی‌فرستد. صفحهٔ [رویدادها](events.md) را ببینید.

بررسی عضو و نقش در دستورها در صفحهٔ [دسترسی‌ها](permissions.md) آمده است. همه‌چیز دربارهٔ این کلاس‌ها در
[مرجع API](../../reference.md) هست.
