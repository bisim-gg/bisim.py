# دسترسی‌ها

سامانهٔ دسترسی بی‌سیم همان سامانهٔ دیسکورد است: همان دسترسی‌ها با همان شمارهٔ بیت‌ها، نقش‌هایی که آن‌ها را
می‌دهند، تنظیمات اختصاصی کانال (overwrite) که برای هر نقش یا عضو در یک کانال اجازه می‌دهند یا منع می‌کنند، و همان
قاعده‌ها برای ترکیبشان. پس `bisim.Permissions` درست مثل `discord.Permissions` کار می‌کند.

## bisim.Permissions

شیء `Permissions` مجموعه‌ای از پرچم‌های دسترسی است. هر دسترسی یک ویژگی است که می‌توانید بخوانید و تنظیم کنید:

```python
perms = bisim.Permissions(view_channel=True, send_messages=True)
print(perms.value)  # 3072, the bits as one number
print(perms.send_messages)  # True
print(perms.kick_members)  # False

perms.update(embed_links=True, attach_files=True)
perms.manage_messages = True

everything = bisim.Permissions.all()
nothing = bisim.Permissions.none()
from_number = bisim.Permissions(8)  # administrator
```

مجموعه‌های آماده‌ای مثل `Permissions.text()`، `Permissions.voice()`، `Permissions.general()` و
`Permissions.membership()` دسترسی‌های مرتبط را کنار هم می‌گذارند. دو مجموعه با `|`، `&` و `^` ترکیب می‌شوند و با
`<=` و `>=` (زیرمجموعه و ابرمجموعه) مقایسه می‌شوند. حلقه زدن روی یک `Permissions` جفت‌های `(name, value)` می‌دهد.

نام‌هایی که زیاد می‌بینید: `view_channel` (یا `read_messages`)، `send_messages`، `manage_messages`،
`embed_links`، `attach_files`، `add_reactions`، `read_message_history`، `pin_messages`، `mention_everyone`،
`manage_channels`، `manage_roles`، `manage_nicknames`، `kick_members`، `ban_members`، `moderate_members`،
`mute_members`، `move_members` و `administrator`. فهرست کامل در [مرجع API](../../reference.md) آمده است.

## هر کس چه کاری می‌تواند بکند

`member.guild_permissions` کارهایی است که یک عضو در کل سرور، فقط بر اساس نقش‌هایش، می‌تواند انجام دهد.
`channel.permissions_for(member)` کارهایی است که در یک کانال می‌تواند انجام دهد، با در نظر گرفتن تنظیمات اختصاصی
آن کانال:

```python
perms = channel.permissions_for(member)
if perms.send_messages:
    await channel.send(f'{member.mention} can write here.')

# What the bot itself may do here
if channel.permissions_for(guild.me).manage_messages:
    await channel.purge(limit=10)
```

بی‌سیم دسترسی‌های خود ربات را در هر کانال به کتاب‌خانه می‌گوید، پس `channel.permissions_for(guild.me)` همیشه دقیق
است. برای اعضای دیگر، کتاب‌خانه تنظیمات اختصاصی کانال را لازم دارد که در فهرست سرورهای بی‌سیم نمی‌آیند. اول آن‌ها
را با `await channel.fetch_overwrites()` بارگذاری کنید؛ بررسی `commands.has_permissions()` در دستورهای
پیشوندی این کار را خودش انجام می‌دهد.

مالک سرور و اعضایی که `administrator` دارند همهٔ دسترسی‌ها را دارند. عضوی که در سکوت موقت است فقط `view_channel`
و `read_message_history` را نگه می‌دارد.

## تنظیمات اختصاصی کانال

یک overwrite برای یک نقش یا عضو در یک کانال، فراتر از آنچه نقش‌هایش می‌دهند، دسترسی‌هایی را اجازه می‌دهد یا منع
می‌کند. `bisim.PermissionOverwrite` یکی از آن‌ها را نگه می‌دارد: هر دسترسی `True` (اجازه)، `False` (منع) یا
`None` (پیروی از نقش‌ها) است.

```python
# Make a channel read only for everyone, writable for one role
await channel.set_permissions(guild.default_role, send_messages=False)
await channel.set_permissions(helpers, send_messages=True, manage_messages=True)

# The same with a PermissionOverwrite object
overwrite = bisim.PermissionOverwrite()
overwrite.view_channel = False
await channel.set_permissions(member, overwrite=overwrite, reason='Muted in this channel')

# Remove an overwrite
await channel.set_permissions(member, overwrite=None)
```

برای خواندن آن‌ها، `await channel.fetch_overwrites()` یک دیکشنری از هر نقش یا عضو به `PermissionOverwrite` آن
برمی‌گرداند و پس از آن `channel.overwrites_for(target)` تنظیم یک هدف را می‌دهد. تغییر این تنظیمات دسترسی مدیریت
نقش‌ها (Manage Roles) را در همان کانال می‌خواهد.

کانال تازه را می‌توان همان هنگام ساختن با تنظیمات اختصاصی ساخت:

```python
overwrites = {
    guild.default_role: bisim.PermissionOverwrite(view_channel=False),
    guild.me: bisim.PermissionOverwrite(view_channel=True),
    staff_role: bisim.PermissionOverwrite(view_channel=True),
}
await guild.create_text_channel('staff', overwrites=overwrites)
```

## دسترسی‌ها در دستورها

دستورها می‌توانند پیش از اجرا دسترسی‌ها را بررسی کنند:

- دستورهای اسلش: `@app_commands.default_permissions()` تعیین می‌کند چه کسی دستور را ببیند، و
  `@app_commands.checks.has_permissions()` و `bot_has_permissions()` هنگام اجرا بررسی می‌کنند. صفحهٔ
  [دسترسی‌ها و بررسی‌ها](../slash-commands/permissions.md) را ببینید.
- دستورهای پیشوندی: `@commands.has_permissions()`، `@commands.bot_has_permissions()` و نسخه‌های `guild_` آن‌ها.
  صفحهٔ [بررسی‌ها](../commands/checks.md) را ببینید.

وقتی کاری به خاطر نداشتن دسترسی شکست بخورد، بی‌سیم خطا برمی‌گرداند و کتاب‌خانه `bisim.Forbidden` می‌دهد.
