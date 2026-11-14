# رویدادها

bisim.py رویدادمحور است: وقتی در بی‌سیم اتفاقی می‌افتد، کتاب‌خانه coroutineای را که برای آن رویداد ثبت
کرده‌اید صدا می‌زند. نام رویدادها و ورودی‌هایشان همان discord.py است، پس `on_message(message)` و
`on_member_join(member)` همان‌طور که انتظار دارید کار می‌کنند. [مرجع API](../../reference.md) همهٔ رویدادها را
با ورودی‌هایشان فهرست می‌کند.

## ثبت کنترل‌کننده

ساده‌ترین راه، دکوراتور `@client.event` است. نام تابع همان نام رویداد است:

```python
import bisim

client = bisim.Client(intents=bisim.Intents.default())


@client.event
async def on_member_join(member: bisim.Member):
    channel = member.guild.system_channel
    if channel is not None:
        await channel.send(f'Welcome, {member.mention}!')
```

در ربات‌های بزرگ‌تر، از `bisim.Client` ارث‌بری کنید و کنترل‌کننده‌ها را به‌صورت متد بنویسید:

```python
import bisim


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        # Runs once, after logging in and before connecting to the gateway
        print('Setting up')

    async def on_ready(self) -> None:
        print(f'Ready as {self.user}')

    async def on_message(self, message: bisim.Message) -> None:
        if message.author.bot:
            return
        if message.content == '!hello':
            await message.channel.send(f'Hello, {message.author.display_name}!')


client = MyClient(intents=bisim.Intents.default())
```

با `bisim.ext.commands`، دکوراتورهای `@bot.listen()` و `@commands.Cog.listener()` برای یک رویداد بیش از یک
کنترل‌کننده اضافه می‌کنند؛ صفحهٔ [کاگ‌ها](../commands/cogs.md) را ببینید.

## رویدادهای پرکاربرد

| رویداد | چه وقت رخ می‌دهد |
| --- | --- |
| `on_ready()` | یک بار، وقتی همهٔ سرورها بارگذاری شدند ([نخستین ربات](../your-first-bot.md) را ببینید) |
| `on_resumed()` | پس از اتصال دوباره، وقتی سرورها دوباره بارگذاری شدند |
| `on_message(message)` | پیامی در کانالی که ربات می‌بیند فرستاده می‌شود، از جمله پیام‌های خود ربات |
| `on_message_edit(before, after)` | پیامی که در حافظهٔ پیام‌هاست ویرایش می‌شود |
| `on_message_delete(message)` | پیامی که در حافظهٔ پیام‌هاست حذف می‌شود |
| `on_reaction_add(reaction, user)` | به پیامی که در حافظهٔ پیام‌هاست واکنشی اضافه می‌شود |
| `on_member_join(member)` | کسی به سرور می‌پیوندد |
| `on_member_remove(member)` | کسی سرور را ترک می‌کند یا از آن اخراج می‌شود |
| `on_member_update(before, after)` | نام مستعار، نقش‌ها یا سکوت موقت یک عضو تغییر می‌کند |
| `on_presence_update(before, after)` | وضعیت یا فعالیت یک عضو تغییر می‌کند |
| `on_guild_join(guild)` | ربات به سروری اضافه می‌شود |
| `on_guild_remove(guild)` | ربات از سروری خارج یا اخراج می‌شود |
| `on_guild_channel_update(before, after)` | نام، موضوع، جایگاه یا تنظیمات یک کانال تغییر می‌کند |
| `on_guild_role_create(role)` | نقشی ساخته می‌شود |
| `on_voice_state_update(member, before, after)` | کسی به کانال صوتی می‌پیوندد، آن را ترک می‌کند، میان کانال‌ها جابه‌جا می‌شود یا بی‌صدا می‌شود |
| `on_interaction(interaction)` | هر تعاملی می‌رسد؛ `app_commands` و Viewها خودشان آن‌ها را کنترل می‌کنند |

بی‌سیم برای ساخته یا حذف شدن یک کانال رویداد جداگانه‌ای نمی‌فرستد. سرور به ربات می‌گوید که آن سرور را دوباره
بارگذاری کند، و کتاب‌خانه از روی تغییرات، کمی بعد از رخ دادنشان، `on_guild_channel_create` و
`on_guild_channel_delete` را صدا می‌زند.

## رویدادهای خام

`on_message_edit`، `on_message_delete` و رویدادهای واکنش فقط برای پیام‌هایی رخ می‌دهند که در حافظهٔ پیام‌های
ربات هستند: ۱۰۰۰ پیام آخری که دیده، یا به اندازهٔ `max_messages` اگر آن را به کلاینت بدهید. برای پیام‌های
قدیمی‌تر از رویدادهای خام استفاده کنید که همیشه رخ می‌دهند و به‌جای شیء، شناسه می‌آورند:

```python
@client.event
async def on_raw_reaction_add(payload: bisim.RawReactionActionEvent):
    # payload.message_id, payload.channel_id, payload.guild_id, payload.user_id and payload.emoji
    if str(payload.emoji) == '⭐':
        channel = client.get_channel(payload.channel_id)
        if channel is not None:
            message = await channel.fetch_message(payload.message_id)
            print(f'Starred: {message.jump_url}')
```

رویدادهای خام این‌ها هستند: `on_raw_message_edit`، `on_raw_message_delete`، `on_raw_bulk_message_delete`،
`on_raw_reaction_add`، `on_raw_reaction_remove`، `on_raw_reaction_clear`، `on_raw_typing`،
`on_raw_member_remove` و، وقتی کلاینت با `enable_raw_presences=True` ساخته شود، `on_raw_presence_update`.

## صبر کردن برای یک رویداد

`wait_for` یک کنترل‌کننده را تا رخ دادن یک رویداد نگه می‌دارد. نام رویداد را بدون `on_` می‌گیرد، به‌علاوهٔ یک
`check` اختیاری که ورودی‌های رویداد را دریافت می‌کند و یک `timeout` اختیاری بر حسب ثانیه:

```python
import asyncio


@client.event
async def on_message(message: bisim.Message):
    if message.content != '!guess':
        return
    await message.channel.send('Guess a number between 1 and 10.')

    def check(m: bisim.Message) -> bool:
        return m.author == message.author and m.channel == message.channel and m.content.isdigit()

    try:
        guess = await client.wait_for('message', check=check, timeout=15.0)
    except asyncio.TimeoutError:
        return await message.channel.send('Too slow!')

    if int(guess.content) == 7:
        await message.channel.send('Right!')
    else:
        await message.channel.send('No, it was 7.')
```

برای رویدادی با چند ورودی، مثل `reaction_add`، تابع `check` همهٔ آن‌ها را دریافت می‌کند و `wait_for` آن‌ها را
به‌صورت یک tuple برمی‌گرداند.

## خطا در کنترل‌کننده‌ها

خطا در یک کنترل‌کنندهٔ رویداد ربات را متوقف نمی‌کند. کتاب‌خانه `on_error` را با نام رویداد صدا می‌زند و رفتار
پیش‌فرض آن ثبت جزئیات خطا در گزارش‌هاست. برای گزارش خطا به روش خودتان، آن را بازنویسی کنید:

```python
import traceback


class MyClient(bisim.Client):
    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        print(f'Error in {event_method}')
        traceback.print_exc()
```

خطاهای دستورهای اسلش و دستورهای پیشوندی کنترل‌کنندهٔ خودشان را دارند که در
[دسترسی‌ها و بررسی‌ها](../slash-commands/permissions.md) و [دستورهای پیشوندی](../commands/index.md) آمده است.

## رویدادهایی که بی‌سیم نمی‌فرستد

بعضی رویدادهای discord.py در بی‌سیم هرگز رخ نمی‌دهند، چون بی‌سیم چنین امکانی ندارد یا آن را به ربات‌ها خبر
نمی‌دهد: رشته‌ها، رویدادهای زمان‌بندی‌شده، استیج‌ها، یکپارچه‌سازی‌ها، دعوت‌نامه‌ها (`on_invite_create` و
`on_invite_delete`) و بن‌ها (`on_member_ban` و `on_member_unban`). ثبت کنترل‌کننده برای آن‌ها ضرری ندارد؛
فقط هرگز صدا زده نمی‌شوند.
