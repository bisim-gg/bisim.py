# سرور محلی بی‌سیم

bisim.py به‌طور پیش‌فرض با خود بی‌سیم کار می‌کند: REST API در `https://api.bisim.gg/api`، گیت‌وی در
`wss://ws.bisim.gg/ws` و فایل‌ها در `https://cdn.bisim.gg`. اگر روی خود بی‌سیم کار می‌کنید یا یک سرور بی‌سیم
برای توسعه دارید، کتاب‌خانه را به آن سرور وصل کنید. هیچ چیز دیگری در ربات تغییر نمی‌کند.

## با گزینه‌های کلاینت

`Client` و در نتیجه `commands.Bot` این سه نشانی را به‌صورت آرگومان کلیدی می‌گیرند:

```python
import os

import bisim

client = bisim.Client(
    intents=bisim.Intents.default(),
    api_url='http://localhost:3000/api',
    gateway_url='ws://localhost:4000/ws',
)

client.run(os.environ['BISIM_TOKEN'])
```

| گزینه | پیش‌فرض | سرور محلی |
| --- | --- | --- |
| `api_url` | `https://api.bisim.gg/api` | `http://localhost:3000/api` |
| `gateway_url` | `wss://ws.bisim.gg/ws` | `ws://localhost:4000/ws` |
| `cdn_url` | `https://cdn.bisim.gg` | جایی که آن سرور فایل‌هایش را ارائه می‌کند |

به `http://` و `ws://` دقت کنید: سرور محلی معمولاً TLS ندارد. `cdn_url` فقط پیوندهایی را تغییر می‌دهد که
کتاب‌خانه برای تصویر کاربران، آیکون‌ها، ایموجی‌ها و استیکرها می‌سازد، پس هنگام آزمودن دستورها می‌تواند همان
پیش‌فرض بماند.

## با متغیرهای محیطی

اگر گزینه‌ای داده نشود، کتاب‌خانه آن را از متغیرهای محیطی می‌خواند. به این ترتیب همان ربات بدون دست زدن به کد
یک بار با سرور محلی و یک بار با بی‌سیم اجرا می‌شود:

=== "لینوکس و مک"

    ```sh
    export BISIM_API_URL=http://localhost:3000/api
    export BISIM_GATEWAY_URL=ws://localhost:4000/ws
    export BISIM_TOKEN=the-token-from-your-local-server
    python bot.py
    ```

=== "ویندوز (PowerShell)"

    ```powershell
    $env:BISIM_API_URL = "http://localhost:3000/api"
    $env:BISIM_GATEWAY_URL = "ws://localhost:4000/ws"
    $env:BISIM_TOKEN = "the-token-from-your-local-server"
    python bot.py
    ```

| متغیر | گزینه |
| --- | --- |
| `BISIM_API_URL` | `api_url` |
| `BISIM_GATEWAY_URL` | `gateway_url` |
| `BISIM_CDN_URL` | `cdn_url` |

گزینه‌ای که در کد داده شود بر متغیر محیطی مقدم است.

## توکن

هر توکن به سروری تعلق دارد که آن را صادر کرده است. برنامه را روی سرور محلی، در پورتال توسعه‌دهندگان آن
(تنظیمات، پورتال توسعه‌دهندگان) بسازید و از همان توکن استفاده کنید: سرور محلی توکن bisim.gg را نمی‌پذیرد و
برعکس.

## بررسی اتصال

گزارش‌های کتاب‌خانه را روشن کنید تا هر مرحلهٔ شروع را ببینید: ورود، باز شدن گیت‌وی و بارگذاری هر سرور.

```python
import logging

client.run(os.environ['BISIM_TOKEN'], log_level=logging.DEBUG)
```

اگر ورود با `bisim.LoginFailure` شکست بخورد، توکن متعلق به آن سرور نیست. اگر گیت‌وی در دسترس نباشد،
`gateway_url` را بررسی کنید و مطمئن شوید گیت‌وی آن سرور در حال اجراست.

## دریافت تعامل‌ها روی سرور محلی

رباتی که از [نشانی دستورها](topics/interactions-url.md) استفاده می‌کند به نشانی‌ای نیاز دارد که سرور بتواند به
آن برسد. آن نشانی را در تنظیمات برنامه روی سرور محلی وارد کنید و کلید عمومی‌ای را به کار ببرید که همان سرور
نشان می‌دهد. بدون نشانی دستورها، تعامل‌ها مثل همیشه از راه گیت‌وی می‌رسند.
