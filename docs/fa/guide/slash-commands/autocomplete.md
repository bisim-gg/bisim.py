# تکمیل خودکار

تکمیل خودکار هم‌زمان با تایپ عضو در یک گزینه، پیشنهادهایی نشان می‌دهد که ربات همان لحظه آماده می‌کند. وقتی
مقدارهای ممکن برای [انتخاب‌های ثابت](options.md) زیادند یا با زمان تغییر می‌کنند، از آن استفاده کنید: نام
برچسب‌ها، شهرها، رکوردهای یک پایگاه داده.

## افزودن به یک گزینه

یک تابع `async` بنویسید که تعامل و متن تایپ‌شده تا این لحظه را بگیرد و فهرستی از `app_commands.Choice`
برگرداند. آن را با دکوراتور `autocomplete()` دستور وصل کنید:

```python
from typing import List

from bisim import app_commands

FRUITS = ['Apple', 'Banana', 'Cherry', 'Melon', 'Pineapple', 'Watermelon']


@client.tree.command(description='Tell the bot your favourite fruit')
async def fruit(interaction: bisim.Interaction, name: str) -> None:
    await interaction.response.send_message(f'Your favourite fruit seems to be {name}.')


@fruit.autocomplete('name')
async def fruit_autocomplete(interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=item, value=item)
        for item in FRUITS
        if current.lower() in item.lower()
    ][:25]
```

`current` همان چیزی است که عضو تا این لحظه در آن گزینه نوشته، و پیش از نوشتن هر چیزی رشتهٔ خالی است. بی‌سیم
حداکثر **۲۵** پیشنهاد نشان می‌دهد، پس فهرست را کوتاه کنید.

شکل دکوراتوری `@app_commands.autocomplete(name=fruit_autocomplete)` همین کار را می‌کند و وقتی تابع تکمیل
خودکار پیش از دستور تعریف شده باشد به کار می‌آید.

تکمیل خودکار روی گزینه‌های `str`، `int` و `float` که انتخاب ثابت ندارند کار می‌کند. گذاشتن آن روی نوع
دیگری از گزینه، یا روی پارامتری با نوع `Choice`، هنگام تعریف دستور `TypeError` می‌دهد.

## استفاده از گزینه‌های دیگر

`interaction.namespace` گزینه‌هایی را که عضو تا این لحظه پر کرده، با نامشان در بی‌سیم، نگه می‌دارد. گزینه‌ای
که هنوز پر نشده `None` است:

```python
CITIES = {'iran': ['Tehran', 'Isfahan', 'Shiraz', 'Tabriz'], 'turkey': ['Istanbul', 'Ankara', 'Izmir']}


@client.tree.command(description='Pick a city')
@app_commands.choices(country=[
    app_commands.Choice(name='Iran', value='iran'),
    app_commands.Choice(name='Turkey', value='turkey'),
])
async def city(interaction: bisim.Interaction, country: str, city: str) -> None:
    await interaction.response.send_message(f'{city}, {country}')


@city.autocomplete('city')
async def city_autocomplete(interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
    names = CITIES.get(interaction.namespace.country or '', [])
    return [app_commands.Choice(name=n, value=n) for n in names if n.lower().startswith(current.lower())]
```

در تعامل تکمیل خودکار، namespace همان چیزی است که عضو تا این لحظه نوشته و هنوز بررسی نشده است. یک کاربر،
نقش یا کانال در آن ممکن است فقط یک `bisim.Object` با شناسه باشد.

## درون یک گروه

در یک [`app_commands.Group`](groups.md) تابع تکمیل خودکار یک متد است و `self` را اول می‌گیرد:

```python
class Notes(app_commands.Group, name='note', description='Save short notes'):
    def __init__(self) -> None:
        super().__init__()
        self.notes: Dict[str, str] = {}

    @app_commands.command(description='Show a note')
    async def show(self, interaction: bisim.Interaction, name: str) -> None:
        await interaction.response.send_message(self.notes.get(name, 'There is no such note.'))

    @show.autocomplete('name')
    async def note_names(self, interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
        matches = [n for n in sorted(self.notes) if current.lower() in n]
        return [app_commands.Choice(name=n, value=n) for n in matches[:25]]
```

## خوب است بدانید

- پیشنهادها فقط پیشنهادند: عضو همچنان می‌تواند هر مقداری بفرستد. مقدار را در خود دستور بررسی کنید.
- پاسخ باید در سه ثانیه برسد، پس تابع را سریع نگه دارید. اگر تابع خطا بدهد، خطا ثبت می‌شود و عضو پیشنهادی
  نمی‌بیند؛ رسیدگی‌کننده‌های خطای دستور صدا زده نمی‌شوند.
- بررسی‌های دستور برای تکمیل خودکار اجرا نمی‌شوند. `@app_commands.check(...)` را روی خود تابع تکمیل خودکار
  بگذارید؛ وقتی یکی از آن‌ها رد شود، عضو فهرستی خالی می‌گیرد.
- یک [تبدیل‌گر](options.md) با پیاده کردن `autocomplete()` می‌تواند برای همهٔ گزینه‌هایی که از آن استفاده
  می‌کنند تکمیل خودکار فراهم کند.
- اگر [مترجم](translations.md) تنظیم شده باشد، نام هر پیشنهاد به زبان عضو ترجمه می‌شود.
