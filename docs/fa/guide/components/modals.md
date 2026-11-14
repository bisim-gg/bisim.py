# فرم‌ها

فرم (modal) پنجرهٔ کوچکی است که روی بی‌سیم باز می‌شود. فرم کادرهای متنی دارد و وقتی کاربر آن را بفرستد، به‌صورت یک
تعامل به ربات برمی‌گردد. در bisim.py هر فرم زیرکلاسی از `bisim.ui.Modal` است.

## ساختن فرم

```python
import bisim
from bisim import ui


class Feedback(ui.Modal, title='Send feedback'):
    topic = ui.TextInput(label='Topic', placeholder='What is it about?', max_length=50)
    details = ui.TextInput(label='Details', style=bisim.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        print(f'Feedback from {interaction.user}: {self.topic.value}: {self.details.value}')
        await interaction.response.send_message('Thanks, we read every message.', ephemeral=True)
```

هر ویژگی کلاس از نوع `ui.TextInput` یک کادر متن می‌شود، به همان ترتیبی که نوشته شده و هر کدام در ردیف خودش. هر فرم
حداکثر پنج کادر دارد و عنوانش تا ۴۵ نویسه است.

| گزینه | معنا |
| --- | --- |
| `label` | متن بالای کادر، تا ۴۵ نویسه (اجباری) |
| `style` | `bisim.TextStyle.short` برای یک خط (پیش‌فرض) یا `bisim.TextStyle.paragraph` برای چند خط |
| `placeholder` | متن راهنمای خاکستری که تا خالی بودن کادر دیده می‌شود، تا ۱۰۰ نویسه |
| `default` | متنی که کادر با آن شروع می‌شود، تا ۴۰۰۰ نویسه |
| `required` | اینکه پر کردن کادر لازم است یا نه؛ پیش‌فرض `True` |
| `min_length` و `max_length` | طول مجاز، از ۰ تا ۴۰۰۰ و از ۱ تا ۴۰۰۰ |

بعد از ارسال فرم، `self.topic.value` (یا `str(self.topic)`) همان چیزی است که کاربر نوشته، و برای کادر اختیاری که
خالی مانده یک رشتهٔ خالی. در بی‌سیم فرم فقط کادر متن دارد.

## باز کردن فرم

فرم به‌عنوان **نخستین** پاسخ به یک تعامل باز می‌شود: یک دستور اسلش، یک دستور منوی راست‌کلیک، یک دکمه یا یک منوی
انتخاب.

```python
@tree.command(description='Send feedback to the team')
async def feedback(interaction: bisim.Interaction) -> None:
    await interaction.response.send_modal(Feedback())
```

از یک دکمه:

```python
class Panel(ui.View):
    @ui.button(label='Send feedback', style=bisim.ButtonStyle.primary)
    async def feedback(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(Feedback())
```

نمی‌توانید اول اعلام انتظار کنید و بعد فرم را باز کنید، ارسال یک فرم نمی‌تواند فرم دیگری باز کند، و درخواست تکمیل
خودکار هم نمی‌تواند فرمی باز کند. دستور پیشوندی تعاملی ندارد، پس آن هم نمی‌تواند فرم باز کند: دکمه‌ای بفرستید که فرم
را باز کند. فرم بعد از باز شدن فقط یک بار و ظرف ۱۵ دقیقه فرستاده می‌شود.

## پاسخ به فرم ارسال‌شده

`on_submit` فرم ارسال‌شده را به‌صورت یک تعامل دریافت می‌کند که باید مثل هر تعامل دیگری پاسخ بگیرد: یک پیام
بفرستید، `defer()` کنید، یا اگر فرم از یک دکمه باز شده، با `edit_message` پیامی را که دکمه رویش است تغییر دهید.

اگر `on_submit` خطا بدهد، `on_error(interaction, error)` صدا زده می‌شود. اگر بازنویسی‌اش نکنید خطا را در گزارش‌ها ثبت
می‌کند، و تعامل همچنان پاسخ لازم دارد:

```python
class Feedback(ui.Modal, title='Send feedback'):
    topic = ui.TextInput(label='Topic')

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        await save_feedback(interaction.user.id, self.topic.value)
        await interaction.response.send_message('Saved.', ephemeral=True)

    async def on_error(self, interaction: bisim.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Something went wrong.', ephemeral=True)
```

`interaction_check` همان‌طور که در نماها کار می‌کند این‌جا هم کار می‌کند: با برگرداندن `False` یک ارسال را نادیده
بگیرید.

## فرم‌هایی که به لحظه بستگی دارند

هر چه فرم لازم دارد به `__init__` بدهید، `super().__init__()` را صدا بزنید و بعد کادرهای متن را تغییر دهید. عنوان را
هم می‌توانید برای هر فرم جداگانه بدهید:

```python
class EditNote(ui.Modal):
    text = ui.TextInput(label='Note', style=bisim.TextStyle.paragraph)

    def __init__(self, name: str, current: str) -> None:
        super().__init__(title=f'Edit {name}')
        self.name = name
        self.text.default = current

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        notes[self.name] = self.text.value
        await interaction.response.send_message(f'Saved {self.name}.', ephemeral=True)
```

کلاس‌های فرم در [مرجع API](../../reference.md) آمده‌اند.
