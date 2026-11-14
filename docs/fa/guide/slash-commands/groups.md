# زیردستورها و گروه‌ها

گروه، دستورهای مرتبط را زیر یک نام جمع می‌کند: به‌جای سه دستور جدا، `/note save`، `/note show` و
`/note delete`. در بی‌سیم، مثل دیسکورد، خود گروه اجرا نمی‌شود و فقط زیردستورهایش اجرا می‌شوند.

## گروه به‌صورت کلاس

از `app_commands.Group` ارث ببرید. نام و توضیح گروه از کلیدواژه‌های کلاس (یا از نام کلاس و docstring آن)
می‌آید و هر متدی که با `@app_commands.command()` تزئین شود یک زیردستور است:

```python
from typing import Dict, List

import bisim
from bisim import app_commands


class Notes(app_commands.Group, name='note', description='Save short notes and show them later'):
    def __init__(self) -> None:
        super().__init__()
        self.notes: Dict[str, str] = {}

    @app_commands.command(description='Save a note')
    async def save(self, interaction: bisim.Interaction, name: str, text: str) -> None:
        self.notes[name.lower()] = text
        await interaction.response.send_message(f'Saved **{name}**.', ephemeral=True)

    @app_commands.command(description='Show a note')
    async def show(self, interaction: bisim.Interaction, name: str) -> None:
        await interaction.response.send_message(self.notes.get(name.lower(), 'There is no such note.'))


client.tree.add_command(Notes())
```

بدون `name=`، کلاسی به نام `TodoList` گروه `todo-list` می‌شود. وضعیت گروه، مثل `self.notes` در این‌جا، روی
نمونهٔ کلاس نگه داشته می‌شود.

## گروه بدون کلاس

برای چند دستور کوچک، یک `Group` بسازید و تابع‌ها را با `command()` آن تزئین کنید:

```python
tags = app_commands.Group(name='tag', description='Short texts the server can recall')


@tags.command(description='Show a tag')
async def show(interaction: bisim.Interaction, name: str) -> None:
    await interaction.response.send_message(f'Tag {name}')


@tags.command(name='list', description='List every tag')
async def list_tags(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('No tags yet.')


client.tree.add_command(tags)
```

## گروه‌های تودرتو

یک گروه می‌تواند گروه‌های دیگری را، فقط تا یک سطح، در خود داشته باشد: `/settings welcome set` یعنی یک گروه
(`settings`)، یک زیرگروه (`welcome`) و یک زیردستور (`set`). برای ساختن زیرگروه `parent=` بدهید:

```python
settings = app_commands.Group(name='settings', description='Change how the bot behaves here')
welcome = app_commands.Group(name='welcome', description='The welcome message', parent=settings)


@welcome.command(name='set', description='Set the welcome message')
async def welcome_set(interaction: bisim.Interaction, text: str) -> None:
    await interaction.response.send_message(f'New members will read: {text}', ephemeral=True)


@welcome.command(name='off', description='Turn the welcome message off')
async def welcome_off(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Welcome message turned off.', ephemeral=True)


client.tree.add_command(settings)
```

در یک کلاس، زیرگروه یک ویژگی کلاس است: `welcome = app_commands.Group(name='welcome', description='...')` و
دستورهایش `@welcome.command()` را به کار می‌برند. گروهی که عمیق‌تر از این تودرتو شود `ValueError` می‌دهد.

## تنظیم‌هایی که مال گروه‌اند

- `@app_commands.guild_only()`، `@app_commands.default_permissions(...)` و `@app_commands.guilds(...)` روی
  کل گروه اعمال می‌شوند: آن‌ها را روی کلاس بگذارید (یا `guild_only=` و `default_permissions=` را به `Group`
  بدهید). بی‌سیم این‌ها را فقط برای دستور سطح بالا نگه می‌دارد: روی یک زیردستور، `guild_only` و
  `default_permissions` نادیده گرفته می‌شوند و `guilds` خطای `ValueError` می‌دهد.
- با بازنویسی `interaction_check()` روی گروه، پیش از هر زیردستور آن یک بررسی اجرا کنید.
- با بازنویسی `on_error()`، یا تزئین یک تابع با `@group.error`، به خطاهای همهٔ زیردستورها رسیدگی کنید. صفحهٔ
  [دسترسی‌ها و بررسی‌ها](permissions.md) را ببینید.

## گروه در کاگ‌ها

در `bisim.ext.commands`، یک `GroupCog` [کاگی](../commands/cogs.md) است که دستورهای برنامهٔ آن یک گروه
می‌سازند:

```python
from bisim.ext import commands


class Todo(commands.GroupCog, group_name='todo', group_description='A small to do list'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.items: Dict[int, List[str]] = {}

    @app_commands.command(description='Add something to your list')
    async def add(self, interaction: bisim.Interaction, item: str) -> None:
        self.items.setdefault(interaction.user.id, []).append(item)
        await interaction.response.send_message('Added.', ephemeral=True)


# In setup_hook or an extension's setup function:
# await bot.add_cog(Todo(bot))
```

## محدودیت‌ها

- حداکثر ۲۵ زیردستور و زیرگروه در هر گروه.
- حداکثر دو سطح: گروه، زیرگروه، زیردستور.
- هر گروه یکی از ۱۰۰ دستور محدودهٔ خودش حساب می‌شود.
- نام‌ها از همان قاعدهٔ نام دستورها پیروی می‌کنند و هر گروه توضیح لازم دارد.

کلاس‌ها در [مرجع API](../../reference.md) شرح داده شده‌اند.
