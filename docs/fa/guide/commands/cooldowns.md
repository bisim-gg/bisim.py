# محدودیت تکرار

**محدودیت تکرار** (cooldown) تعیین می‌کند هر دستور چند بار می‌تواند به کار برود: چند بار در چند ثانیه، شمرده‌شده برای
هر شخص، هر کانال، هر سرور یا برای همه. استفادهٔ زودتر از موعد به‌جای اجرای دستور خطای `commands.CommandOnCooldown`
می‌دهد.

## افزودن محدودیت تکرار

```python
@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def daily(ctx: commands.Context) -> None:
    await ctx.send('Here is your daily reward.')
```

`commands.cooldown(rate, per, type)` برای هر سطل از نوع `type` اجازهٔ `rate` بار استفاده در هر `per` ثانیه را می‌دهد:

| `BucketType` | یک شمارنده برای |
| --- | --- |
| `default` | کل ربات (پیش‌فرض) |
| `user` | هر شخص، هر جا که دستور را به کار ببرد |
| `member` | هر شخص در هر سرور |
| `guild` | هر سرور (در پیام خصوصی، هر شخص) |
| `channel` | هر کانال |
| `category` | هر دسته (اگر کانال دسته نداشته باشد، خود کانال) |
| `role` | بالاترین نقش هر شخص (در پیام خصوصی، کانال) |

نوع می‌تواند تابعی هم باشد که زمینهٔ اجرا را می‌گیرد و هر کلید hashable را برمی‌گرداند، برای سطل‌هایی از خودتان.

## گفتن اینکه باید صبر کنند

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'Slow down! Try again in {error.retry_after:.0f} seconds.', delete_after=5)
```

`error.retry_after` تعداد ثانیه‌های باقی‌مانده است، `error.cooldown` مقدارهای `rate` و `per` را دارد و `error.type`
نوع سطل است.

## محدودیتی که به پرسنده بستگی دارد

`commands.dynamic_cooldown()` تابعی می‌گیرد که زمینهٔ اجرا را دریافت می‌کند و برای همین بار یک
`commands.Cooldown(rate, per)` برمی‌گرداند، یا `None` برای اینکه هیچ محدودیتی نباشد:

```python
def by_role(ctx: commands.Context):
    if ctx.guild is not None and ctx.author.guild_permissions.manage_messages:
        return None  # moderators have no cooldown
    return commands.Cooldown(1, 60)


@bot.command()
@commands.dynamic_cooldown(by_role, commands.BucketType.user)
async def report(ctx: commands.Context, *, text: str) -> None:
    await ctx.send('Thanks, the moderators were told.')
```

محدودیت پویا نوع سطلی غیر از `BucketType.default` لازم دارد.

## بازنشانی و پرس‌وجو

```python
@daily.error
async def daily_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'Come back in {error.retry_after:.0f} seconds.')


@bot.command()
@commands.is_owner()
async def resetdaily(ctx: commands.Context) -> None:
    daily.reset_cooldown(ctx)
    await ctx.send('Your daily cooldown was reset.')
```

`command.reset_cooldown(ctx)` شمارندهٔ سطلی را که `ctx` در آن است صفر می‌کند، `command.is_on_cooldown(ctx)` می‌گوید
استفادهٔ بعدی رد می‌شود یا نه، و `command.get_cooldown_retry_after(ctx)` ثانیه‌های باقی‌مانده را می‌دهد.

محدودیت تکرار پیش از تبدیل ورودی‌ها شمرده می‌شود، پس استفاده‌ای با ورودی نادرست هم حساب می‌شود. با دادن
`cooldown_after_parsing=True` به `@bot.command()` فقط استفاده‌هایی شمرده می‌شوند که ورودی‌هایشان درست تبدیل شده است.

## حداکثر چند اجرا هم‌زمان

`commands.max_concurrency()` تعداد اجراهای هم‌زمان یک دستور را محدود می‌کند، که برای دستورهای طولانی مثل مسابقه
مناسب است:

```python
@bot.command()
@commands.max_concurrency(1, commands.BucketType.channel, wait=False)
async def quiz(ctx: commands.Context) -> None:
    await ctx.send('First question: ...')
    answer = await bot.wait_for('message', check=lambda m: m.channel == ctx.channel, timeout=30)
    await ctx.send(f'{answer.author.display_name} answered first.')
```

استفادهٔ دوم در حالی که اولی در حال اجراست خطای `commands.MaxConcurrencyReached` می‌دهد؛ با `wait=True` به‌جای آن
منتظر نوبتش می‌ماند.

دستورهای اسلش محدودیت تکرار خودشان را دارند، یعنی `app_commands.checks.cooldown`: صفحهٔ
[دسترسی‌ها و بررسی‌ها](../slash-commands/permissions.md) را ببینید. کلاس‌های محدودیت تکرار در
[مرجع API](../../reference.md) آمده‌اند.
