# منوهای انتخاب

منوی انتخاب یک فهرست بازشونده زیر پیام است. منوها هم مثل دکمه‌ها داخل یک [نما](buttons.md) قرار می‌گیرند. هر منو
یک ردیف کامل را می‌گیرد، پس هر پیام حداکثر پنج منو دارد. بی‌سیم پنج نوع منو دارد: منویی با گزینه‌های خودتان، و
منوهایی که بی‌سیم با اعضا، نقش‌ها، هر دو، یا کانال‌ها پر می‌کند.

## منویی با گزینه‌های خودتان

```python
import bisim
from bisim import ui


class Colours(ui.View):
    @ui.select(
        placeholder='Pick up to two colours',
        min_values=1,
        max_values=2,
        options=[
            bisim.SelectOption(label='Red', value='red', emoji='🟥'),
            bisim.SelectOption(label='Green', value='green', emoji='🟩'),
            bisim.SelectOption(label='Blue', value='blue', emoji='🟦', description='The calm one'),
        ],
    )
    async def colours(self, interaction: bisim.Interaction, select: ui.Select) -> None:
        chosen = ', '.join(select.values)
        await interaction.response.send_message(f'You chose {chosen}.', ephemeral=True)


await ctx.send('Which colours do you like?', view=Colours())
```

`select.values` فهرست مقدارهای گزینه‌های انتخاب‌شده است، به‌صورت رشته. هر منو حداکثر ۲۵ گزینه دارد. هر گزینه یک
`label` دارد که دیده می‌شود، یک `value` که به کد شما می‌رسد (اگر ندهید، همان برچسب است)، `description` و `emoji`
اختیاری، و `default=True` تا از ابتدا انتخاب‌شده نشان داده شود؛ برچسب، مقدار و توضیح هر کدام تا ۱۰۰ نویسه‌اند.

`min_values` (از ۰ تا ۲۵) و `max_values` (از ۱ تا ۲۵) تعیین می‌کنند چند گزینه می‌شود انتخاب کرد، و `placeholder`
متن راهنمایی است که تا وقتی چیزی انتخاب نشده دیده می‌شود. `disabled=True`، `custom_id` و `row` همان کاری را می‌کنند
که برای دکمه‌ها.

گزینه‌ها را می‌توانید در کد هم اضافه کنید، تا سقف ۲۵:

```python
select = ui.Select(placeholder='Choose a role colour')
for name in ('Red', 'Green', 'Blue'):
    select.add_option(label=name, value=name.lower())

view = ui.View()
view.add_item(select)
```

## منو به‌صورت یک کلاس جدا

از `ui.Select` زیرکلاس بسازید و `callback` را بازنویسی کنید تا منو یک جا بماند و بتوانید دوباره از آن استفاده کنید:

```python
class LanguageSelect(ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder='Choose your language',
            options=[
                bisim.SelectOption(label='فارسی', value='fa', description='Persian'),
                bisim.SelectOption(label='English', value='en'),
            ],
        )

    async def callback(self, interaction: bisim.Interaction) -> None:
        await interaction.response.send_message(f'Language set to {self.values[0]}.', ephemeral=True)


view = ui.View()
view.add_item(LanguageSelect())
await ctx.send('Which language do you prefer?', view=view)
```

## منوهایی که بی‌سیم پر می‌کند

به تزئین‌کننده `cls=` بدهید یا کلاس را مستقیم بسازید. کاربر از میان اعضا، نقش‌ها یا کانال‌های سرور انتخاب می‌کند و
`values` اشیای انتخاب‌شده را نگه می‌دارد:

| کلاس | `values` |
| --- | --- |
| `ui.Select` | `List[str]` |
| `ui.UserSelect` | `List[Union[bisim.Member, bisim.User]]` |
| `ui.RoleSelect` | `List[bisim.Role]` |
| `ui.MentionableSelect` | اعضا، کاربران و نقش‌ها با هم |
| `ui.ChannelSelect` | کانال‌های انتخاب‌شده |

```python
class Setup(ui.View):
    @ui.select(cls=ui.ChannelSelect, channel_types=[bisim.ChannelType.text], placeholder='Where should I post?')
    async def channel(self, interaction: bisim.Interaction, select: ui.ChannelSelect) -> None:
        await interaction.response.send_message(f'I will post in {select.values[0].mention}.', ephemeral=True)

    @ui.select(cls=ui.RoleSelect, placeholder='Who may use me?', max_values=3)
    async def roles(self, interaction: bisim.Interaction, select: ui.RoleSelect) -> None:
        names = ', '.join(role.name for role in select.values)
        await interaction.response.send_message(f'Allowed roles: {names}.', ephemeral=True)
```

`channel_types` منوی کانال را به چند نوع کانال محدود می‌کند: `ChannelType.text`، `ChannelType.voice` و
`ChannelType.category` نوع‌هایی‌اند که بی‌سیم دارد. در پیام خصوصی، منوی کانال چیزی برای نشان دادن ندارد.

### شروع با انتخاب پیش‌فرض

منوی کاربر، نقش، منشن‌پذیر یا کانال می‌تواند از ابتدا چند عضو، نقش یا کانال انتخاب‌شده داشته باشد:
`default_values`، مثل discord.py. خود شیءها، `bisim.Object` (منوی منشن‌پذیر به `type=` آن نیاز دارد) یا
`bisim.SelectDefaultValue` را بدهید. تعدادشان باید بین `min_values` و `max_values` باشد؛ منوی متنی به‌جای این،
پیش‌فرض‌هایش را با `default=True` روی گزینه‌ها مشخص می‌کند.

```python
@ui.select(cls=ui.RoleSelect, placeholder='Roles that may post', max_values=3, default_values=[bisim.Object(id=ROLE_ID)])
async def poster_roles(self, interaction: bisim.Interaction, select: ui.RoleSelect) -> None:
    ...

menu = ui.UserSelect(default_values=[interaction.user], max_values=5)
menu.default_values  # [<SelectDefaultValue id=... type=<SelectDefaultValueType.user: 'user'>>]
```

منویی که از یک پیام خوانده شود آن‌ها را در `component.default_values` دارد.

## پاسخ به انتخاب

انتخاب در منو یک تعامل است و مثل کلیک به آن پاسخ می‌دهید: با `edit_message`، `send_message`، `defer` یا
`send_modal`، ظرف سه ثانیه. صفحهٔ [دکمه‌ها](buttons.md#پاسخ-به-کلیک) را ببینید. نماهای ماندگار برای منوها هم کار
می‌کنند: به منو یک `custom_id` ثابت و به نما `timeout=None` بدهید.

کلاس‌های منوی انتخاب در [مرجع API](../../reference.md) آمده‌اند.
