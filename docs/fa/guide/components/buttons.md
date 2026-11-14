# دکمه‌ها

دکمه‌ها و منوهای انتخاب زیر پیام قرار می‌گیرند. در bisim.py آن‌ها داخل یک **نما** (view) هستند: زیرکلاسی از
`bisim.ui.View` که اجزا را نگه می‌دارد، کلیک‌ها را دریافت می‌کند و کد شما را صدا می‌زند. این همان ابزار رابط کاربری
discord.py است، با همان نام‌ها. فقط ربات‌ها می‌توانند دکمه و منو روی پیام بگذارند.

## نخستین نما

```python
import bisim
from bisim import ui


class Counter(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.count = 0

    @ui.button(label='Count: 0', style=bisim.ButtonStyle.primary)
    async def count_button(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.count += 1
        button.label = f'Count: {self.count}'
        await interaction.response.edit_message(view=self)
```

نما را همراه هر پیامی بفرستید:

```python
# in a slash command
await interaction.response.send_message('Press the button.', view=Counter())

# in a prefix command
await ctx.send('Press the button.', view=Counter())

# anywhere else
await channel.send('Press the button.', view=Counter())
```

تابعی که با `@ui.button` تزئین شده، نما، `bisim.Interaction` مربوط به کلیک و خود دکمه را دریافت می‌کند. داخل نما
دکمه یک ویژگی هم هست: با `self.count_button.label` می‌توانید برچسبش را بخوانید و تغییر دهید.

`@ui.button` این گزینه‌ها را می‌گیرد: `label` (تا ۸۰ نویسه)، `style`، `emoji` (یک ایموجی یونی‌کد یا ایموجی سرور مثل
`'<:name:id>'`)، `custom_id` (تا ۱۰۰ نویسه؛ اگر ندهید، یکی ساخته می‌شود)، `disabled` و `row`.

| سبک | کاربرد |
| --- | --- |
| `ButtonStyle.primary` (نام دیگر: `blurple`) | کار اصلی |
| `ButtonStyle.secondary` (نام‌های دیگر: `grey` و `gray`) | کار خنثی، سبک پیش‌فرض |
| `ButtonStyle.success` (نام دیگر: `green`) | کار مثبت |
| `ButtonStyle.danger` (نام دیگر: `red`) | کار برگشت‌ناپذیر |
| `ButtonStyle.link` (نام دیگر: `url`) | یک نشانی را باز می‌کند؛ تابع پاسخ ندارد |

دکمه‌های پولی (`sku_id`) در بی‌سیم وجود ندارند و خطای `bisim.NotSupported` می‌دهند.

## پاسخ به کلیک

هر کلیک یک تعامل است و باید ظرف سه ثانیه، و فقط یک بار، به آن پاسخ داده شود:

- `await interaction.response.edit_message(content=..., view=...)` پیامی را که دکمه رویش است تغییر می‌دهد.
  `view=None` دکمه‌ها را برمی‌دارد.
- `await interaction.response.send_message('...', ephemeral=True)` با یک پیام تازه پاسخ می‌دهد؛ این‌جا پیامی پنهان
  که فقط همان کسی که کلیک کرده می‌بیند.
- `await interaction.response.defer()` کلیک را تأیید می‌کند بی‌آنکه چیزی را تغییر دهد. بعد از آن پیام را با
  `interaction.edit_original_response(...)` ویرایش کنید یا با `interaction.followup.send(...)` پیام بیشتری بفرستید.
- `await interaction.response.send_modal(...)` یک [فرم](modals.md) باز می‌کند.

برای هر چیزی که یک پاسخ می‌تواند همراه داشته باشد، [پاسخ به دستورها](../slash-commands/responding.md) را ببینید.

## دکمه‌های پیوند و اجزایی که در کد اضافه می‌شوند

دکمهٔ پیوند یک `url` دارد و تابع پاسخ ندارد، پس با تزئین‌کننده ساخته نمی‌شود. جزء را بسازید و اضافه‌اش کنید:

```python
view = ui.View()
view.add_item(ui.Button(label='Bisim docs', url='https://docs.bisim.gg'))
await ctx.send('Read more:', view=view)
```

`add_item`، `remove_item` و `clear_items` هر زمان نما را تغییر می‌دهند و `view.children` فهرست اجزای آن است. برای
اینکه جزئی رفتار خودش را داشته باشد، از آن زیرکلاس بسازید و `callback` را بازنویسی کنید:

```python
class RemoveMe(ui.Button):
    async def callback(self, interaction: bisim.Interaction) -> None:
        self.view.remove_item(self)
        await interaction.response.edit_message(view=self.view)
```

هر نما حداکثر ۲۵ جزء در ۵ ردیف دارد. در هر ردیف جای ۵ دکمه یا یک منوی انتخاب هست. اجزا به ترتیب ردیف‌ها را پر
می‌کنند؛ با `row=0` تا `row=4` خودتان جای یک جزء را تعیین می‌کنید، و جزئی که جا نشود خطای `ValueError` می‌دهد.

## چه کسی می‌تواند کلیک کند

`interaction_check` را بازنویسی کنید تا تعیین کنید یک تعامل به توابع پاسخ برسد یا نه. برگرداندن `False` آن را نادیده
می‌گیرد:

```python
class Confirm(ui.View):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.accepted = None

    async def interaction_check(self, interaction: bisim.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message('Only the person who asked can answer.', ephemeral=True)
        return False

    @ui.button(label='Continue', style=bisim.ButtonStyle.success)
    async def accept(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.accepted = True
        await interaction.response.edit_message(content='Going ahead.', view=None)
        self.stop()
```

خطایی که در یک تابع پاسخ یا در `interaction_check` رخ دهد به `on_error(interaction, error, item)` می‌رسد که اگر
بازنویسی‌اش نکنید، خطا را در گزارش‌ها ثبت می‌کند.

## مهلت، توقف و انتظار

`timeout` ثانیه‌های گذشته از آخرین کلیک را می‌شمارد (پیش‌فرض ۱۸۰؛ با `None` هیچ‌وقت تمام نمی‌شود). وقتی مهلت تمام شود
نما دیگر گوش نمی‌دهد و `on_timeout` را صدا می‌زند. برای اینکه در این لحظه دکمه‌ها را غیرفعال کنید، پیامی را که نما با
آن فرستاده شده نگه دارید:

```python
class Poll(ui.View):
    message = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


view = Poll(timeout=300)
view.message = await ctx.send('Vote!', view=view)
# after interaction.response.send_message(...): view.message = await interaction.original_response()
```

`view.stop()` نما را همان لحظه متوقف می‌کند. `await view.wait()` صبر می‌کند تا نما متوقف شود و اگر مهلتش تمام شده
باشد `True` برمی‌گرداند؛ این برای پرسشی با «بله» و «نه» مناسب است:

```python
@bot.command()
async def clear(ctx: commands.Context) -> None:
    view = Confirm(ctx.author.id)
    await ctx.send('Delete the last 100 messages here?', view=view)
    if await view.wait() or not view.accepted:
        await ctx.send('Nothing was done.')
        return
    await ctx.channel.purge(limit=100)
```

## نماهای ماندگار

نما معمولاً با راه‌اندازی دوبارهٔ ربات از کار می‌افتد. نمای **ماندگار** (persistent) به کلیک روی پیام‌هایی که قبلاً
فرستاده هم پاسخ می‌دهد. چنین نمایی `timeout=None` و برای هر جزء یک `custom_id` ثابت لازم دارد و باید هنگام شروع
ربات ثبت شود:

```python
class Panel(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label='Open a ticket', style=bisim.ButtonStyle.primary, custom_id='panel:ticket')
    async def ticket(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message('A moderator will be with you soon.', ephemeral=True)


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        self.add_view(Panel())
```

`add_view` برای نمایی که ماندگار نباشد خطای `ValueError` می‌دهد. فایل `examples/buttons.py` در مخزن یک ربات کامل
با نظرسنجی، تأیید، منوی انتخاب، فرم و یک پنل ماندگار است.

کلاس‌های نما در [مرجع API](../../reference.md) آمده‌اند.
