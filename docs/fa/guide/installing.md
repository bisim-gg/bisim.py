# نصب

## پایتون

bisim.py به پایتون نسخهٔ ۳٫۹ یا جدیدتر نیاز دارد. نسخهٔ نصب‌شده را بررسی کنید:

```sh
python --version
```

در ویندوز فرمان `py` هم هست، پس `py --version` هم کار می‌کند. اگر این فرمان پیدا نشد یا نسخه قدیمی‌تر بود،
آخرین نسخهٔ پایتون را از [python.org](https://www.python.org/downloads/) نصب کنید.

## محیط مجازی

برای هر ربات یک محیط مجازی جدا بسازید تا بسته‌هایش با پروژه‌های دیگر قاطی نشوند.

=== "لینوکس و مک"

    ```sh
    mkdir my-bot
    cd my-bot
    python3 -m venv .venv
    source .venv/bin/activate
    ```

=== "ویندوز (PowerShell)"

    ```powershell
    mkdir my-bot
    cd my-bot
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    ```

=== "ویندوز (cmd)"

    ```bat
    mkdir my-bot
    cd my-bot
    py -m venv .venv
    .venv\Scripts\activate.bat
    ```

تا وقتی محیط فعال است، `python` و `pip` همان‌هایی‌اند که داخل `.venv` هستند. برای بیرون آمدن از آن `deactivate`
را اجرا کنید.

## نصب bisim.py

```sh
pip install bisim.py
```

نام این بسته در PyPI `bisim.py` است و با نام `bisim` وارد (import) می‌شود. این بسته
[aiohttp](https://docs.aiohttp.org) را هم نصب می‌کند و هم برای API و هم برای گیت‌وی از آن استفاده می‌کند.

## بسته‌های اختیاری

| بسته | فرمان نصب | چه چیزی اضافه می‌کند |
| --- | --- | --- |
| `voice` | `pip install "bisim.py[voice]"` | SDK لایوکیت، برای پیوستن به کانال صوتی، پخش صدا و دریافت آن (صفحهٔ [صدا](topics/voice.md)) |
| `http` | `pip install "bisim.py[http]"` | PyNaCl، برای بررسی امضای تعامل‌هایی که به [نشانی دستورها](topics/interactions-url.md) فرستاده می‌شوند |
| `speed` | `pip install "bisim.py[speed]"` | orjson، یک تجزیه‌گر سریع‌تر JSON که کتاب‌خانه در صورت نصب بودن از آن استفاده می‌کند |

می‌توانید چند بسته را با هم نصب کنید: `pip install "bisim.py[voice,speed]"`. رباتی که تعامل‌ها را از راه
گیت‌وی می‌گیرد، که بیشتر ربات‌ها همین‌طورند، به `http` نیاز ندارد؛ فقط رباتی که به کانال صوتی می‌پیوندد به
`voice` نیاز دارد.

## بررسی نصب

```sh
python -c "import bisim; print(bisim.__version__)"
```

این فرمان نسخهٔ نصب‌شده را چاپ می‌کند، مثلاً `0.1.0`. `bisim.version_info` همین نسخه را به‌صورت یک named
tuple نگه می‌دارد تا در کد بتوانید آن را مقایسه کنید.

## به‌روزرسانی

```sh
pip install --upgrade bisim.py
```

پیش از به‌روزرسانی رباتی که در حال اجراست،
[فهرست تغییرات](https://github.com/bisim-gg/bisim.py/blob/main/CHANGELOG.md) را بخوانید.

قدم بعدی: [ساخت برنامه](creating-an-application.md).
