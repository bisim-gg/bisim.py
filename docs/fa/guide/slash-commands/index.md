# دستورهای اسلش

دستورهای اسلش همان چیزهایی هستند که اعضا پس از `/` در کانال می‌نویسند. هر دستور یک نام و یک توضیح دارد و
می‌تواند گزینه، زیردستور و دسترسی هم داشته باشد. در bisim.py این دستورها درست مثل discord.py در
`bisim.app_commands` قرار دارند: یک تابع `async` می‌نویسید، دکوراتور را رویش می‌گذارید و یک `CommandTree` آن را
به بی‌سیم می‌فرستد و هر بار که کسی از آن استفاده کند اجرایش می‌کند.

## نخستین دستور

```python
import os

import bisim
from bisim import app_commands


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        # One tree per client: it holds the commands and runs them.
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Runs once after logging in: send the commands to Bisim.
        await self.tree.sync()


client = MyClient()


@client.tree.command()
async def ping(interaction: bisim.Interaction) -> None:
    """Check that the bot is alive."""
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


client.run(os.environ['BISIM_TOKEN'])
```

اجرایش کنید، در کانالی که ربات آن را می‌بیند `/ping` بنویسید و ربات پاسخ می‌دهد. نخستین پارامتر هر دستور
`bisim.Interaction` است و هر چه برای پاسخ دادن لازم دارید روی همین شیء است.

اگر از `bisim.ext.commands` استفاده می‌کنید، ربات از قبل یک درخت دارد: `@bot.tree.command()` و
`await bot.tree.sync()` را به کار ببرید.

## نام و توضیح

- **نام** دستور همان نام تابع است، مگر این‌که `name=` بدهید. بی‌سیم ۱ تا ۳۲ نویسه از حروف کوچک `a` تا `z`،
  رقم، `-` و `_` را می‌پذیرد. هر چیز دیگری همان لحظه‌ای که دستور تعریف می‌شود `ValueError` می‌دهد، پس پیش از
  همگام‌سازی متوجه می‌شوید.
- **توضیح** دستور مقدار `description=` است و اگر نباشد، نخستین بند docstring. بی‌سیم ۱ تا ۱۰۰ نویسه را
  می‌پذیرد و docstring بلندتر به ۱۰۰ نویسه کوتاه می‌شود. دستوری که هیچ‌کدام را نداشته باشد `…` نشان می‌دهد.
- نام و توضیح فارسی به‌صورت ترجمه اضافه می‌شوند؛ صفحهٔ [ترجمهٔ دستورها](translations.md) را ببینید.

```python
@client.tree.command(name='server-info', description='Show this server\'s name and member count')
@app_commands.guild_only()
async def server_info(interaction: bisim.Interaction) -> None:
    guild = interaction.guild
    await interaction.response.send_message(f'{guild.name} has {guild.member_count} members.')
```

آرگومان‌های دیگر `tree.command()`: با `guild=` یا `guilds=` دستور به‌جای سراسری، دستور یک سرور می‌شود
(صفحهٔ [ثبت و همگام‌سازی](syncing.md) را ببینید) و `extras=` دیکشنری‌ای است که کتاب‌خانه هرگز به آن دست
نمی‌زند. `nsfw=` برای سازگاری پذیرفته می‌شود، اما بی‌سیم از آن استفاده نمی‌کند.

می‌توانید دستوری را هم جداگانه با `@app_commands.command()` تعریف کنید و بعد با
`client.tree.add_command(...)` به درخت اضافه کنید؛ دستورهای یک ماژول جدا یا یک کاگ همین‌طور نوشته می‌شوند.

## دستورها کجا اجرا می‌شوند

بی‌سیم دستورهای اسلش را در کانال‌های متنی سرورها و در پیام خصوصی خود ربات اجرا می‌کند. عضو باید در آن کانال
دسترسی **استفاده از دستورهای برنامه‌ها** (Use Application Commands) را داشته باشد و محروم موقت (timeout)
نباشد. دستور سراسری فقط در سرورهایی وجود دارد که ربات به آن‌ها اضافه شده است. برای محدود کردن دستور به
سرورها یا به پیام خصوصی، صفحهٔ [دسترسی‌ها و بررسی‌ها](permissions.md) را ببینید.

## در این بخش

- [ثبت و همگام‌سازی](syncing.md): فرستادن دستورها به بی‌سیم، به‌صورت سراسری یا برای یک سرور.
- [پاسخ به دستورها](responding.md): پاسخ دادن، پیام‌های پنهان، اعلام انتظار و پیام‌های بعدی.
- [گزینه‌ها و انتخاب‌ها](options.md): پارامترهای نوع‌دار، توضیح‌ها، بازه‌ها و انتخاب‌های ثابت.
- [تکمیل خودکار](autocomplete.md): پیشنهاد دادن هم‌زمان با تایپ عضو.
- [زیردستورها و گروه‌ها](groups.md): `/note save`، `/note show` و گروه‌های تودرتو.
- [دستورهای منوی راست‌کلیک](context-menus.md): دستورهایی در منوی یک پیام یا یک کاربر.
- [دسترسی‌ها و بررسی‌ها](permissions.md): چه کسی می‌تواند دستور را اجرا کند و رسیدگی به خطاها.
- [ترجمهٔ دستورها](translations.md): نام و توضیح فارسی و انگلیسی.

همهٔ کلاس‌ها و دکوراتورها در [مرجع API](../../reference.md) آمده‌اند.
