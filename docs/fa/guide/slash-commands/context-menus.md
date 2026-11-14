# دستورهای منوی راست‌کلیک

دستورهای منوی راست‌کلیک وقتی دیده می‌شوند که عضوی منوی یک پیام یا یک کاربر را باز کند و به بخش **برنامه‌ها**
برود. این دستورها گزینه ندارند: ورودی‌شان همان پیام یا کاربری است که منو رویش باز شده است.

## دستورهای پیام و دستورهای کاربر

نوع پارامتر دوم تعیین می‌کند دستور در کدام منو دیده شود:

```python
@client.tree.context_menu(name='Quote message')
async def quote(interaction: bisim.Interaction, message: bisim.Message) -> None:
    embed = bisim.Embed(description=message.content or '(no text)', timestamp=message.created_at)
    embed.set_author(name=message.author.display_name)
    await interaction.response.send_message(embed=embed)


@client.tree.context_menu(name='Account age')
async def account_age(interaction: bisim.Interaction, user: bisim.User) -> None:
    created = user.created_at.strftime('%Y-%m-%d')
    await interaction.response.send_message(f'{user.display_name} joined Bisim on {created}.', ephemeral=True)
```

- `bisim.Message` یک دستور پیام می‌سازد.
- `bisim.Member`، `bisim.User` یا `Union[bisim.Member, bisim.User]` یک دستور کاربر می‌سازد. وقتی نقش‌ها یا
  تاریخ پیوستن را لازم دارید، `bisim.Member` را به کار ببرید؛ در سرور یک عضو می‌گیرید.

به این دستورها مثل هر دستور دیگری پاسخ می‌دهید ([پاسخ به دستورها](responding.md) را ببینید) و همراه بقیهٔ
درخت همگام می‌شوند ([ثبت و همگام‌سازی](syncing.md) را ببینید).

## نام‌ها

برخلاف دستورهای اسلش، نام دستور منوی راست‌کلیک می‌تواند حرف بزرگ و فاصله داشته باشد: ۱ تا ۳۲ نویسه. بدون
`name=`، نام تابع با حرف اول بزرگ به کار می‌رود، پس `account_age` می‌شود `Account_Age`؛ معمولاً دادن یک نام
بهتر است. دستورهای منوی راست‌کلیک توضیح ندارند.

## دسترسی‌ها و خطاها

همان دکوراتورهای دستورهای اسلش این‌جا هم کار می‌کنند: `@app_commands.default_permissions(...)`،
`@app_commands.guild_only()` و بررسی‌هایی مثل `@app_commands.checks.has_permissions(...)`. آن‌ها را زیر
`@client.tree.context_menu(...)` بگذارید:

```python
@client.tree.context_menu(name='Delete and warn')
@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def delete_and_warn(interaction: bisim.Interaction, message: bisim.Message) -> None:
    await message.delete()
    await interaction.response.send_message(f'Deleted a message by {message.author.mention}.', ephemeral=True)


@delete_and_warn.error
async def delete_and_warn_error(interaction: bisim.Interaction, error: app_commands.AppCommandError) -> None:
    await interaction.response.send_message('I could not delete that message.', ephemeral=True)
```

برای تصویر کامل، صفحهٔ [دسترسی‌ها و بررسی‌ها](permissions.md) را ببینید.

## در یک کاگ

دستور منوی راست‌کلیک را نمی‌توان به‌صورت متدی در یک کلاس تعریف کرد. در یک [کاگ](../commands/cogs.md)، آن را
در `__init__` با `app_commands.ContextMenu` و یک متد متصل (bound) بسازید، به درخت اضافه کنید و هنگام بیرون
آوردن کاگ حذفش کنید:

```python
from bisim.ext import commands


class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.report_menu = app_commands.ContextMenu(name='Report message', callback=self.report)
        self.bot.tree.add_command(self.report_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.report_menu.name, type=self.report_menu.type)

    async def report(self, interaction: bisim.Interaction, message: bisim.Message) -> None:
        await interaction.response.send_message('Thanks, the moderators will have a look.', ephemeral=True)
```

## محدودیت‌ها

حداکثر ۵ دستور پیام و ۵ دستور کاربر در هر محدوده (سراسری، یا یک سرور)؛ پس از آن `add_command()` خطای
`app_commands.CommandLimitReached` می‌دهد. این دستورها جزو همان ۱۰۰ دستوری حساب می‌شوند که بی‌سیم برای هر
محدوده نگه می‌دارد.

کلاس `ContextMenu` در [مرجع API](../../reference.md) آمده است.
