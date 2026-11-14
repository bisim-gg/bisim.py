# ترجمهٔ دستورها

بی‌سیم دستورها را به فارسی و انگلیسی نشان می‌دهد و هر عضو آن‌ها را به زبان خودش می‌بیند. bisim.py ترجمه را
همان‌طور انجام می‌دهد که discord.py: یک `Translator` متن فارسی و انگلیسی هر نام، توضیح و انتخاب را می‌دهد و
`tree.sync()` این ترجمه‌ها را همراه دستورها به بی‌سیم می‌فرستد.

## یک مترجم

از `app_commands.Translator` ارث ببرید و `translate()` را پیاده کنید. این متد متن کد شما را به‌صورت یک
`locale_str`، زبانی که بی‌سیم می‌خواهد (`bisim.Locale.persian` یا `bisim.Locale.english`) و یک زمینه
(context) می‌گیرد و ترجمه را برمی‌گرداند، یا اگر ترجمه‌ای ندارد `None`:

```python
from typing import Optional

import bisim
from bisim import app_commands
from bisim.app_commands import locale_str

PERSIAN = {
    'weather': 'هوا',
    'Show the weather in a city': 'هوای یک شهر را نشان می‌دهد',
    'city': 'شهر',
    'The city to look up': 'نام شهر',
}


class PersianTranslator(app_commands.Translator):
    async def translate(
        self,
        string: locale_str,
        locale: bisim.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> Optional[str]:
        if locale is bisim.Locale.persian:
            return PERSIAN.get(string.message)
        return None  # the text in the code is already English


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Set the translator before syncing: sync() is when translations are collected.
        await self.tree.set_translator(PersianTranslator())
        await self.tree.sync()


client = MyClient()


@client.tree.command(description='Show the weather in a city')
@app_commands.describe(city='The city to look up')
async def weather(interaction: bisim.Interaction, city: str) -> None:
    await interaction.response.send_message(f'It is sunny in {city}.')
```

حالا عضوی که بی‌سیمش فارسی است `/هوا` را با گزینهٔ `شهر` می‌بیند و بقیه `/weather` را. وقتی `translate()`
مقدار `None` برگرداند، بی‌سیم متن کد شما را نشان می‌دهد.

همهٔ نام‌ها و توضیح‌ها ترجمه می‌شوند، چون دستورها خودشان متن‌هایشان را به `locale_str` تبدیل می‌کنند
(`auto_locale_strings=True`، مقدار پیش‌فرض). نام انتخاب‌ها هم ترجمه می‌شود.

## آن‌چه بی‌سیم می‌پذیرد

- نام ترجمه‌شدهٔ دستور، گروه یا گزینه: ۱ تا ۳۲ نویسه از حروف، رقم، `-` و `_`، از جمله حروف فارسی، بدون
  فاصله، و با حروف کوچک هر جا که حرف بزرگ و کوچک دارد.
- نام ترجمه‌شدهٔ دستور منوی راست‌کلیک، مثل نام اصلی، می‌تواند فاصله و حرف بزرگ داشته باشد.
- توضیح ترجمه‌شده: ۱ تا ۱۰۰ نویسه.

ترجمه‌ای که بی‌سیم نپذیرد باعث می‌شود `sync()` با `app_commands.CommandSyncFailure` شکست بخورد. خطایی که درون
`translate()` رخ دهد به‌صورت `app_commands.TranslationError` به شما می‌رسد.

## کلید و زمینه

در ربات‌های کوچک، خود متن انگلیسی کار کلید را می‌کند. ربات‌های بزرگ‌تر با extras در `locale_str` به هر متن
کلید جداگانه‌ای می‌دهند و به زمینه نگاه می‌کنند:

```python
@client.tree.command(
    name=locale_str('ping', key='ping.name'),
    description=locale_str('Check that the bot is alive', key='ping.description'),
)
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Pong!')
```

در `translate()`، `string.extras.get('key')` همان کلید است، `context.location` می‌گوید چه چیزی ترجمه می‌شود
(`TranslationContextLocation.command_name`، `parameter_description`، `choice_name` و مانند این‌ها) و
`context.data` خود دستور، پارامتر یا انتخاب است.

`load()` را بازنویسی کنید تا هنگام تنظیم مترجم، فایل‌های ترجمه خوانده شوند، و `unload()` را برای پاک‌سازی
وقتی مترجم عوض می‌شود یا کلاینت بسته می‌شود.

## ترجمهٔ پاسخ‌ها

`interaction.locale` زبان عضو است. `interaction.translate()` مترجم درخت را روی هر متنی، به همان زبان، اجرا
می‌کند:

```python
@client.tree.command(description='Say hello')
async def hello(interaction: bisim.Interaction) -> None:
    text = await interaction.translate('Hello!')
    await interaction.response.send_message(text or 'Hello!')
```

وقتی مترجم یا ترجمه‌ای نباشد `None` برمی‌گرداند، پس یک مقدار جایگزین نگه دارید. انتخاب‌های
[تکمیل خودکار](autocomplete.md) هنگام فرستادن به زبان عضو ترجمه می‌شوند.

`Translator`، `locale_str` و `TranslationContext` در [مرجع API](../../reference.md) شرح داده شده‌اند.
