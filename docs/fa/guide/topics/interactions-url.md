# نشانی دستورها

به‌طور پیش‌فرض تعامل‌ها از راه گیت‌وی به ربات می‌رسند؛ همان اتصالی که پیام‌ها و همهٔ رویدادهای دیگر را
می‌آورد. می‌توانید به‌جای آن برای برنامه‌تان یک **نشانی دستورها** (Interactions URL) بگذارید: آن‌وقت بی‌سیم
هر تعامل (دستورهای اسلش، منوی راست‌کلیک، دکمه‌ها، منوهای انتخاب، فرم‌ها و تکمیل خودکار) را به‌صورت یک
درخواست `POST` امضاشدهٔ HTTP به آن نشانی می‌فرستد و دیگر از راه گیت‌وی نمی‌فرستد.

وقتی ربات شما یک سرویس وب است که به دستورها پاسخ می‌دهد و دلیلی برای وصل ماندن ندارد، از آن استفاده کنید.
bisim.py بخش HTTP را در `bisim.http_interactions` و بر پایهٔ سرور وب aiohttp انجام می‌دهد و بقیهٔ کد شما
(درخت دستورها، نماها و فرم‌ها) همان می‌ماند.

## راه‌اندازی

1. افزونه‌ای را که امضاها را بررسی می‌کند نصب کنید (PyNaCl را اضافه می‌کند):

    ```sh
    pip install "bisim.py[http]"
    ```

2. در پورتال توسعه‌دهندگان بی‌سیم (**تنظیمات**، **پورتال توسعه‌دهندگان**، یا
   [bisim.gg/developers](https://bisim.gg/developers)) برنامهٔ خودتان را باز کنید و در **اطلاعات کلی**، در
   **نشانی دستورها** یک نشانی عمومی `https` بنویسید که به ربات شما برسد.
3. **کلید عمومی** را از همان صفحه کپی کنید: ۶۴ نویسهٔ hex.

وقتی نشانی را ذخیره می‌کنید، بی‌سیم آن را بررسی می‌کند: یک PING می‌فرستد که باید با `{"type": 1}` پاسخ داده
شود و یک درخواست با امضای عمداً نادرست که باید با وضعیت 401 رد شود. bisim.py هر دو را برایتان انجام می‌دهد.

## یک ربات کامل

```python
import asyncio
import os

from aiohttp import web

import bisim
from bisim import app_commands
from bisim.http_interactions import create_interactions_app

client = bisim.Client(intents=bisim.Intents.default())
tree = app_commands.CommandTree(client)


@tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Pong!')


async def main() -> None:
    async with client:
        # Logging in is enough to answer interactions: no gateway connection is needed.
        await client.login(os.environ['BISIM_TOKEN'])
        await tree.sync()
        app = create_interactions_app(client, os.environ['BISIM_PUBLIC_KEY'])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, host='0.0.0.0', port=8787).start()
        await asyncio.Event().wait()  # serve until the process is stopped


asyncio.run(main())
```

`create_interactions_app(client, public_key, path='/')` یک `aiohttp.web.Application` برمی‌گرداند که به
درخواست‌های `POST` روی `path` پاسخ می‌دهد. برای `https` آن را پشت وب‌سروری یا پراکسی‌ای بگذارید که همیشه به کار می‌برید.

## هر درخواست چه می‌شود

bisim.py برای هر درخواست:

1. سرآیندهای `X-Signature-Ed25519` و `X-Signature-Timestamp` را با بدنهٔ خام و کلید عمومی شما بررسی می‌کند
   و اگر نخوانند با 401 پاسخ می‌دهد؛
2. به PING با `{"type": 1}` پاسخ می‌دهد؛
3. هر تعامل دیگری را درست مثل تعاملی که از گیت‌وی آمده به کلاینت می‌دهد: درخت دستورها، نماها و فرم‌ها اجرا
   می‌شوند و رویداد `on_interaction` رخ می‌دهد.

بی‌سیم حدود سه ثانیه منتظر پاسخ می‌ماند. وقتی کد شما در `answer_timeout` ثانیه (به‌طور پیش‌فرض ۲٫۵) پاسخ
دهد، پاسخ به روش دیسکورد در بدنهٔ پاسخ HTTP برمی‌گردد. اگر بیشتر طول بکشد، درخواست با 202 تأیید می‌شود و پاسخ
شما از راه API بی‌سیم می‌رود. در هر دو حالت `interaction.response.send_message()`، `defer()` و بقیه را مثل
همیشه می‌نویسید؛ صفحهٔ [پاسخ به دستورها](../slash-commands/responding.md) را ببینید.

## برنامهٔ وب خودتان

برای این‌که برنامهٔ وب شما کنار مسیرهای دیگرش به تعامل‌ها هم پاسخ دهد، `handle_interaction_request()` را از
رسیدگی‌کنندهٔ خودتان صدا بزنید:

```python
from bisim.http_interactions import handle_interaction_request

PUBLIC_KEY = os.environ['BISIM_PUBLIC_KEY']


async def interactions(request: web.Request) -> web.Response:
    return await handle_interaction_request(client, request, PUBLIC_KEY)


async def health(request: web.Request) -> web.Response:
    return web.Response(text='ok')


app = web.Application()
app.router.add_post('/bisim/interactions', interactions)
app.router.add_get('/health', health)
```

`verify_key(body, signature, timestamp, public_key)` فقط بررسی امضاست: برای بدنه‌ای دقیقاً به همان شکلی که
رسیده `True` یا `False` برمی‌گرداند. با PyNaCl کار می‌کند و اگر نباشد با بستهٔ `cryptography`، و اگر هیچ‌کدام
نصب نباشد `RuntimeError` می‌دهد.

## بدون گیت‌وی

رباتی که فقط به نشانی دستورهایش پاسخ می‌دهد چیزی در حافظهٔ نهان (cache) ندارد: `interaction.guild` سروری است
که فقط شناسه‌اش معلوم است، `interaction.channel` یک `PartialMessageable` است و `client.get_guild()` مقدار
`None` برمی‌گرداند. خود تعامل همچنان عضو، دسترسی‌هایش و گزینه‌های حل‌شده را با خود دارد. اگر رویدادها و حافظهٔ
نهان را هم می‌خواهید، به گیت‌وی هم وصل شوید (پس از ورود، `client.connect()`)؛ تعامل‌ها همچنان به نشانی دستورها
می‌رسند.

برای برگشتن به گیت‌وی، نشانی دستورها را در تنظیمات برنامه پاک کنید.

تابع‌ها در [مرجع API](../../reference.md) آمده‌اند.
