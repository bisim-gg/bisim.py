---
title: bisim.py
hide:
  - navigation
  - toc
---

<div class="bisim-hero" markdown>

<img class="bisim-hero__logo" src="../assets/logo.svg" alt="">

<div class="bisim-hero__text" markdown>

# bisim.py

<p class="bisim-hero__tagline">کتاب‌خانهٔ رسمی پایتون برای ساخت ربات‌های بی‌سیم، با API نسخهٔ ۲ discord.py.
import و توکن را عوض کنید تا ربات discord.py شما روی بی‌سیم اجرا شود.</p>

<div class="bisim-hero__actions" markdown>
[شروع کنید](guide/index.md){ .md-button .md-button--primary }
[آمدن از discord.py](guide/moving-from-discord-py.md){ .md-button }
[مرجع API](reference.md){ .md-button }
</div>

</div>

</div>

```diff
-import discord
-from discord.ext import commands
+import bisim
+from bisim.ext import commands
```

<div class="bisim-features" markdown>

<div class="bisim-feature" markdown>
### فقط دو خط تغییر
یک ربات discord.py نسخهٔ ۲ با عوض کردن importها و یک توکن بی‌سیم روی بی‌سیم اجرا می‌شود. کلاس‌ها، رویدادها،
دکوریتورها و آرگومان‌ها همان‌هایی هستند که می‌شناسید.
</div>

<div class="bisim-feature" markdown>
### هر چه یک ربات لازم دارد
دستورهای اسلش با گزینه، گروه و تکمیل خودکار، منوی راست‌کلیک، دکمه، منوی انتخاب، فرم، امبد، دستورهای
پیشوندی با کاگ‌ها و کارهای پس‌زمینه.
</div>

<div class="bisim-feature" markdown>
### ساخته‌شده برای بی‌سیم
دستورها به فارسی و انگلیسی، مدیریت خودکار گیت‌وی و محدودیت‌های نرخ بی‌سیم، و خطای روشن
`bisim.NotSupported` برای هر چیزی که بی‌سیم ندارد.
</div>

<div class="bisim-feature" markdown>
### تایپ‌دار و ناهمگام
پایتون ۳٫۹ به بالا، asyncio با aiohttp، type hint در همه‌جا، و آزمون‌هایی که بدون شبکه اجرا می‌شوند.
</div>

</div>

## یک ربات در بیست خط

```python
import bisim
from bisim import app_commands

intents = bisim.Intents.default()
intents.message_content = True  # to read '!hello' (switch it on at bisim.gg/developers)
client = bisim.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


@client.event
async def on_ready() -> None:
    await tree.sync()
    print(f'Logged in as {client.user} ({client.user.id})')


@client.event
async def on_message(message: bisim.Message) -> None:
    if message.content == '!hello' and not message.author.bot:
        await message.reply(f'Hello, {message.author.display_name}!')


client.run('your bot token')
```

با `pip install bisim.py` نصبش کنید، ربات را در پورتال توسعه‌دهندگان بی‌سیم
([bisim.gg/developers](https://bisim.gg/developers)) بسازید و از آن‌جا [راهنما](guide/index.md) را دنبال کنید.

!!! note "ساخته‌شده بر پایهٔ discord.py"

    بخش بزرگی از bisim.py، از جمله مستنداتش، از [discord.py](https://github.com/Rapptz/discord.py) نوشتهٔ
    Rapptz و همکارانش آمده و برای API بی‌سیم سازگار شده است. همین است که یک ربات discord.py را بی‌تغییر به
    بی‌سیم می‌آورد. از همهٔ کسانی که discord.py را ساختند سپاسگزاریم.
