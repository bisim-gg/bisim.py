# معرفی

bisim.py کتاب‌خانهٔ رسمی پایتون برای ساخت ربات در [بی‌سیم](https://bisim.gg) است. API آن همان API نسخهٔ ۲
discord.py است: همان `Client`، رویدادها، مدل‌ها، دستورهای اسلش، Viewها، فرم‌ها و `ext.commands`. پس رباتی که
برای discord.py نوشته شده، با عوض کردن importها و یک توکن بی‌سیم روی بی‌سیم اجرا می‌شود.

```diff
-import discord
-from discord import app_commands
-from discord.ext import commands, tasks
+import bisim
+from bisim import app_commands
+from bisim.ext import commands, tasks
```

bisim.py در پشت صحنه با API و گیت‌وی خود بی‌سیم کار می‌کند. شناسه‌ها، بیت‌های دسترسی، نوع کانال‌ها و مقدار
enumها همان عددهای دیسکورد را دارند، پس آنچه درباره‌شان می‌دانید همچنان درست است.

## پیش‌نیازها

- پایتون نسخهٔ ۳٫۹ یا جدیدتر.
- آشنایی با پایتون، از جمله `async` و `await`. اگر coroutineها برایتان تازه‌اند، اول
  [مستندات asyncio](https://docs.python.org/3/library/asyncio.html) را بخوانید؛ همهٔ ربات‌ها بر پایهٔ آن ساخته
  می‌شوند.
- یک حساب بی‌سیم و سروری که بتوانید ربات به آن اضافه کنید.

## ساختار این راهنما

**شروع کار** شما را از صفر به یک ربات در حال اجرا می‌رساند: [نصب](installing.md) کتاب‌خانه،
[ساخت برنامه](creating-an-application.md) در بی‌سیم و نوشتن [نخستین ربات](your-first-bot.md).

**دستورهای اسلش** دربارهٔ `app_commands` است: [ساخت دستورها](slash-commands/index.md)،
[همگام‌سازی با بی‌سیم](slash-commands/syncing.md)، [پاسخ دادن](slash-commands/responding.md)،
[گزینه‌ها و انتخاب‌ها](slash-commands/options.md)، [تکمیل خودکار](slash-commands/autocomplete.md)،
[گروه‌ها](slash-commands/groups.md)، [منوی راست‌کلیک](slash-commands/context-menus.md)،
[دسترسی‌ها و بررسی‌ها](slash-commands/permissions.md) و [ترجمه](slash-commands/translations.md).

**دکمه‌ها، منوها و فرم‌ها** `bisim.ui` را نشان می‌دهد: [Viewها و دکمه‌ها](components/buttons.md)،
[منوهای انتخاب](components/select-menus.md) و [فرم‌ها](components/modals.md).

**دستورهای پیشوندی** دربارهٔ `bisim.ext.commands` است، برای ربات‌هایی که دستورهایی مثل `!help` را از پیام‌ها
می‌خوانند: [دستورها](commands/index.md)، [مبدل‌ها](commands/converters.md)، [بررسی‌ها](commands/checks.md)،
[محدودیت تکرار](commands/cooldowns.md)، [کاگ‌ها](commands/cogs.md) و [دستور راهنما](commands/help.md).

**موضوع‌ها** به [رویدادها](topics/events.md)، [پیام‌ها](topics/messages.md)، [امبدها](topics/embeds.md)،
[اعضا و نقش‌ها](topics/members-and-roles.md)، [دسترسی‌ها](topics/permissions.md)،
[کارهای پس‌زمینه](topics/tasks.md) و دریافت تعامل‌ها از راه [نشانی دستورها](topics/interactions-url.md)
می‌پردازد.

**بیشتر** شامل صفحهٔ [آمدن از discord.py](moving-from-discord-py.md)، اجرای ربات روی
[سرور محلی بی‌سیم](local-server.md) و [پرسش‌های رایج](faq.md) است.

همهٔ کلاس‌ها، متدها و رویدادها در [مرجع API](../reference.md) آمده‌اند که از توضیحات خود کتاب‌خانه ساخته
می‌شود.

## آمدن از discord.py

بیشتر ربات‌ها، ربات‌های صوتی هم، بدون تغییر اجرا می‌شوند. اینتنت‌ها، از جمله اینتنت‌های ویژه، مثل دیسکورد کار
می‌کنند، و آنچه بی‌سیم ندارد (رشته‌ها، کانال‌های استیج و انجمن، رویدادهای زمان‌بندی‌شده، شاردینگ) به‌جای خطای
بی‌صدا، `bisim.NotSupported` می‌دهد. صفحهٔ [آمدن از discord.py](moving-from-discord-py.md) همهٔ تفاوت‌ها
را فهرست می‌کند.

!!! note "سپاس‌گزاری"

    bisim.py بر پایهٔ [discord.py](https://github.com/Rapptz/discord.py) ساختهٔ Rapptz و همکارانش ساخته شده
    و بخش‌هایی از این راهنما از مستندات discord.py برگرفته شده است. هر دو با پروانهٔ MIT منتشر شده‌اند.
