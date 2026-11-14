# گزینه‌ها و انتخاب‌ها

گزینه‌های یک دستور همان پارامترهای تابع آن، پس از تعامل، هستند. نوع (type annotation) هر پارامتر تعیین
می‌کند بی‌سیم چه نوع گزینه‌ای نشان دهد، و مقدار از قبل تبدیل‌شده به دستتان می‌رسد:

```python
@client.tree.command(description='Give a member some points')
async def give(interaction: bisim.Interaction, member: bisim.Member, points: int, reason: str) -> None:
    await interaction.response.send_message(f'{member.mention} got {points} points: {reason}')
```

| نوع | گزینه در بی‌سیم | آن‌چه تابع دریافت می‌کند |
| --- | --- | --- |
| `str` | متن | `str` |
| `int` | عدد صحیح | `int` |
| `float` | عدد | `float` |
| `bool` | درست یا نادرست | `bool` |
| `bisim.User`، `bisim.Member` | یک کاربر | در سرور `Member`، در پیام خصوصی `User` |
| `bisim.Role` | یک نقش | `Role` |
| `bisim.abc.GuildChannel`، `bisim.TextChannel`، `bisim.VoiceChannel`، `bisim.CategoryChannel` | یک کانال، فقط از همان نوع‌ها | خود کانال |
| `Union[bisim.Member, bisim.Role]` | یک کاربر یا یک نقش | `Member`، `User` یا `Role` |
| `bisim.Attachment` | فایلی که عضو بارگذاری می‌کند | `Attachment` |

هر پارامتر باید نوع داشته باشد؛ پارامتر بدون نوع هنگام تعریف دستور `TypeError` می‌دهد. بی‌سیم کانال متنی،
صوتی و دسته دارد، پس گزینهٔ کانال فقط همین نوع‌ها را می‌تواند بخواهد.

!!! note "نکته"
    `bisim.Member` فقط عضو را می‌پذیرد. اگر دستور در پیام خصوصی ربات هم اجرا می‌شود، نوع را
    `Union[bisim.Member, bisim.User]` بگذارید: در سرور `Member` و در پیام خصوصی `User` می‌گیرید.

## گزینه‌های اختیاری و مقدار پیش‌فرض

گزینه‌ای که مقدار پیش‌فرض داشته باشد اختیاری است. راه معمول `Optional[...] = None` است:

```python
@client.tree.command(description='Show a member')
async def whois(interaction: bisim.Interaction, member: Optional[bisim.Member] = None) -> None:
    member = member or interaction.user
    await interaction.response.send_message(f'{member.display_name} joined at {member.joined_at}')
```

بی‌سیم گزینه‌های اجباری را پیش از گزینه‌های اختیاری می‌خواهد؛ bisim.py خودش آن‌ها را مرتب می‌کند.

## توضیح گزینه‌ها

هر گزینه توضیحی تا ۱۰۰ نویسه نشان می‌دهد. آن را با `@app_commands.describe` یا در docstring (به سبک Google،
NumPy یا Sphinx) بنویسید:

```python
@client.tree.command()
@app_commands.describe(member='The member to warn', reason='Why, in a few words')
async def warn(interaction: bisim.Interaction, member: bisim.Member, reason: str) -> None:
    """Warn a member."""
    await interaction.response.send_message(f'{member.mention} was warned: {reason}')
```

## تغییر نام گزینه

نام گزینه همان نام پارامتر است. برای نشان دادن نامی دیگر، مثلاً کلمه‌ای که در پایتون رزرو شده، از
`@app_commands.rename` استفاده کنید. دکوراتورهای دیگر همچنان نام پارامتر را به کار می‌برند:

```python
@client.tree.command(description='Pick a colour for your role')
@app_commands.rename(colour_hex='colour')
@app_commands.describe(colour_hex='A colour like #c8f53c')
async def paint(interaction: bisim.Interaction, colour_hex: str) -> None:
    await interaction.response.send_message(f'Your colour is now {colour_hex}.', ephemeral=True)
```

نام گزینه‌ها از همان قاعدهٔ نام دستورها پیروی می‌کند: ۱ تا ۳۲ نویسه از `a` تا `z`، رقم، `-` و `_`.

## بازه‌ها

`app_commands.Range` یک عدد یا طول یک متن را محدود می‌کند:

```python
@client.tree.command(description='Roll some dice')
async def roll(
    interaction: bisim.Interaction,
    dice: app_commands.Range[int, 1, 20],
    sides: app_commands.Range[int, 2, 100] = 6,
    label: Optional[app_commands.Range[str, 1, 30]] = None,
) -> None:
    results = [random.randint(1, sides) for _ in range(dice)]
    await interaction.response.send_message(f'{label or "Roll"}: {sum(results)}')
```

`Range[int, 10]` فقط کمینه را تعیین می‌کند و `Range[int, None, 10]` فقط بیشینه را. بی‌سیم مقدارهای بیرون از
بازه را پیش از آن‌که دستور به ربات برسد رد می‌کند.

## انتخاب‌های ثابت

وقتی فقط چند مقدار معنا دارد، آن‌ها را به‌صورت انتخاب پیشنهاد دهید (حداکثر ۲۵ انتخاب، هر نام حداکثر ۱۰۰ نویسه):

```python
from bisim.app_commands import Choice


@client.tree.command(description='Order a drink')
@app_commands.choices(drink=[
    Choice(name='Tea', value='tea'),
    Choice(name='Coffee', value='coffee'),
    Choice(name='Doogh', value='doogh'),
])
async def order(interaction: bisim.Interaction, drink: Choice[str]) -> None:
    await interaction.response.send_message(f'One {drink.name}, coming up.')
```

با نوع `Choice[str]` (یا `Choice[int]`، `Choice[float]`) تابع همان `Choice` انتخاب‌شده را می‌گیرد و با نوع
`str` فقط مقدار را. دو راه کوتاه‌تر هم همین نتیجه را می‌دهند:

```python
@client.tree.command(description='Choose a size')
async def size(interaction: bisim.Interaction, size: Literal['small', 'medium', 'large']) -> None:
    await interaction.response.send_message(f'You chose {size}.')


class Speed(enum.Enum):
    slow = 1
    normal = 2
    fast = 3


@client.tree.command(description='Set the speed')
async def speed(interaction: bisim.Interaction, speed: Speed) -> None:
    await interaction.response.send_message(f'Speed set to {speed.name}.')
```

برای انتخاب‌هایی که به نوشتهٔ عضو بستگی دارند، به‌جای این‌ها از [تکمیل خودکار](autocomplete.md) استفاده کنید.

## تبدیل‌گرها

تبدیل‌گر (Transformer) متنی را که عضو نوشته به هر شیئی که بخواهید تبدیل می‌کند. از
`app_commands.Transformer` ارث ببرید و نوع پارامتر را با `app_commands.Transform` بنویسید:

```python
class Point(typing.NamedTuple):
    x: int
    y: int


class PointTransformer(app_commands.Transformer):
    async def transform(self, interaction: bisim.Interaction, value: str) -> Point:
        x, _, y = value.partition(',')
        return Point(x=int(x.strip()), y=int(y.strip()))


@client.tree.command(description='Plot a point, written like 3, 4')
async def plot(interaction: bisim.Interaction, point: app_commands.Transform[Point, PointTransformer]) -> None:
    await interaction.response.send_message(f'x={point.x}, y={point.y}')
```

وقتی `transform()` خطا بدهد، رسیدگی‌کننده‌های خطا یک `app_commands.TransformerError` می‌گیرند. تبدیل‌گر
می‌تواند `type`، `min_value`، `max_value` و `choices` را هم تعیین کند یا `autocomplete()` را پیاده کند. همهٔ
این‌ها در [مرجع API](../../reference.md) آمده‌اند.
