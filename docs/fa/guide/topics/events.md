# رویدادها

bisim.py رویدادمحور است: وقتی در بی‌سیم اتفاقی می‌افتد، کتاب‌خانه coroutineای را که برای آن رویداد ثبت
کرده‌اید صدا می‌زند. نام رویدادها و ورودی‌هایشان همان discord.py است، پس `on_message(message)` و
`on_member_join(member)` همان‌طور که انتظار دارید کار می‌کنند. [مرجع API](../../reference.md) همهٔ رویدادها را
با ورودی‌هایشان فهرست می‌کند.

## ثبت کنترل‌کننده

ساده‌ترین راه، دکوراتور `@client.event` است. نام تابع همان نام رویداد است:

```python
import bisim

intents = bisim.Intents.default()
intents.members = True  # on_member_join needs it (see Intents below)
client = bisim.Client(intents=intents)


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


intents = bisim.Intents.default()
intents.message_content = True  # to read message.content in servers
client = MyClient(intents=intents)
```

با `bisim.ext.commands`، دکوراتورهای `@bot.listen()` و `@commands.Cog.listener()` برای یک رویداد بیش از یک
کنترل‌کننده اضافه می‌کنند؛ صفحهٔ [کاگ‌ها](../commands/cogs.md) را ببینید.

## اینتنت‌ها

اینتنت‌ها به بی‌سیم می‌گویند ربات کدام رویدادها را می‌خواهد. همان اینتنت‌های دیسکورد هستند، بیت به بیت، و آن‌ها
را به کلاینت می‌دهید:

```python
intents = bisim.Intents.default()
intents.members = True          # privileged
intents.message_content = True  # privileged

client = bisim.Client(intents=intents)
```

`Intents.default()` همه را به‌جز سه اینتنت ویژه روشن می‌کند، `Intents.all()` همه را و `Intents.none()` هیچ‌کدام
را. کتاب‌خانه هنگام اتصال آن‌ها را می‌فرستد و گیت‌وی فقط رویدادهایی را که زیر پوشش آن‌هاست برای ربات می‌فرستد.
هر پرچم `Intents` در [مرجع API](../../reference.md) رویدادهای خودش را فهرست می‌کند؛ مهم‌ترین‌ها:

| اینتنت | رویدادها |
| --- | --- |
| `guilds` | سرورها، کانال‌ها، نقش‌ها، سنجاق‌ها و وضعیت کانال صوتی؛ روشن بماند |
| `members` (ویژه) | پیوستن، رفتن و تغییر اعضا |
| `moderation` | بن، برداشتن بن و رکوردهای تازهٔ گزارش حسابرسی |
| `expressions` | ایموجی‌های سفارشی و استیکرها |
| `webhooks` | `on_webhooks_update` |
| `invites` | `on_invite_create` و `on_invite_delete` |
| `voice_states` | `on_voice_state_update` (وضعیت صوتی خود ربات همیشه می‌رسد) |
| `presences` (ویژه) | `on_presence_update` |
| `guild_messages` و `dm_messages` | پیام‌ها در سرورها و پیام‌های خصوصی |
| `guild_reactions` و `dm_reactions` | واکنش‌ها |
| `guild_typing` و `dm_typing` | `on_typing` |
| `message_content` (ویژه) | متن پیام‌ها (پایین‌تر را ببینید) |
| `auto_moderation_configuration` | ساخته، تغییر یا حذف شدن قانون‌های AutoMod |
| `auto_moderation_execution` | `on_automod_action` |
| `guild_polls` و `dm_polls` | رأی‌های نظرسنجی |

تعامل‌ها (دستورهای اسلش، دکمه‌ها، منوهای انتخاب و فرم‌ها) بدون توجه به اینتنت‌ها می‌رسند، و `on_guild_join` هم
همین‌طور.

### اینتنت‌های ویژه

| اینتنت | چه می‌دهد |
| --- | --- |
| `members` | `on_member_join`، `on_member_remove`، `on_member_update` و فهرست اعضا: کتاب‌خانه هنگام شروع همهٔ اعضا را بارگذاری می‌کند و `Guild.chunk()` و `Guild.fetch_members()` کار می‌کنند |
| `presences` | `on_presence_update` و وضعیت و فعالیت اعضا؛ بدون آن همه آفلاین دیده می‌شوند |
| `message_content` | متن، امبدها، پیوست‌ها، کامپوننت‌ها و نظرسنجی پیام‌ها در سرورها |

برای استفاده از هر کدام، اول آن را برای ربات روشن کنید: [bisim.gg/developers](https://bisim.gg/developers) را
باز کنید، برنامهٔ خود را انتخاب کنید، بعد **Bot**، و آن را زیر **Privileged Gateway Intents** روشن کنید. تا وقتی
ربات در کمتر از ۱۰۰ سرور است همین کافی است. از ۱۰۰ سرور به بعد، بی‌سیم هم باید هر اینتنت ویژه را برای برنامه
تأیید کند؛ اینتنتی که روشن است اما تأیید نشده، مثل اینتنت خاموش رد می‌شود.

بدون `members`، کتاب‌خانه فهرست اعضا را بارگذاری نمی‌کند: `guild.members` فقط خود ربات و اعضایی را دارد که
خبرشان رسیده، و `Guild.chunk()` و `Guild.fetch_members()` خطای `ClientException` می‌دهند.
`Guild.fetch_member()` و `Guild.query_members()` همچنان کار می‌کنند و `message.author` همچنان یک `Member` است
که از عضویتی که همراه هر پیام می‌آید ساخته می‌شود.

### وقتی گیت‌وی اینتنت‌ها را رد می‌کند

گیت‌وی هنگام اتصال ربات اینتنت‌ها را بررسی می‌کند و پیش از هر چیز دیگری اتصال را می‌بندد:

- **4014**: اینتنت ویژه‌ای که روشن نشده یا تأیید نشده است. `client.run()` و `client.start()` خطای
  `bisim.PrivilegedIntentsRequired` می‌دهند.
- **4013**: بیتی که اینتنت نیست. خطای `bisim.ConnectionClosed` با `code` برابر 4013 می‌دهند.

کتاب‌خانه پس از هیچ‌کدام دوباره وصل نمی‌شود، چون همان اینتنت‌ها دوباره رد می‌شوند. اینتنت را روشن کنید یا آن را
از `Intents` خود بردارید و ربات را دوباره اجرا کنید.

### بدون Message Content

رباتی که `message_content` ندارد همچنان همهٔ رویدادهای پیام را دریافت می‌کند، اما پیامی که در یک سرور است با
`content` خالی (`''`) و بدون امبد، پیوست، کامپوننت و نظرسنجی می‌رسد، مگر:

- پیام‌های خود ربات،
- پیام‌هایی که از ربات نام می‌برند (منشن)،
- پیام‌های خصوصی.

پیام‌هایی که با REST خوانده می‌شوند (`history()`، `fetch_message()` و `pins()`) هم همین قاعده را دارند، و
`AutoModAction.content` و `matched_content` هم. منشن‌ها همچنان کار می‌کنند: `message.mentions`،
`message.role_mentions`، `message.raw_mentions` و `message.mention_everyone` را بی‌سیم می‌فرستد، نه متن پیام.

دستورهای اسلش، دکمه‌ها و دیگر تعامل‌ها تأثیری نمی‌پذیرند، پس رباتی که بر پایهٔ آن‌هاست به هیچ اینتنت ویژه‌ای
نیاز ندارد. دستورهای پیشوندی به `message_content` نیاز دارند، مگر اینکه پیشوند منشن خود ربات باشد
(`commands.when_mentioned`).

## رویدادهای پرکاربرد

| رویداد | چه وقت رخ می‌دهد | اینتنت |
| --- | --- | --- |
| `on_ready()` | یک بار، وقتی همهٔ سرورها بارگذاری شدند ([نخستین ربات](../your-first-bot.md) را ببینید) | |
| `on_resumed()` | پس از اتصال دوباره، وقتی سرورها دوباره بارگذاری شدند | |
| `on_message(message)` | پیامی در کانالی که ربات می‌بیند فرستاده می‌شود، از جمله پیام‌های خود ربات | `guild_messages` و `dm_messages` |
| `on_message_edit(before, after)` | پیامی که در حافظهٔ پیام‌هاست ویرایش می‌شود | `guild_messages` و `dm_messages` |
| `on_message_delete(message)` | پیامی که در حافظهٔ پیام‌هاست حذف می‌شود | `guild_messages` و `dm_messages` |
| `on_reaction_add(reaction, user)` | به پیامی که در حافظهٔ پیام‌هاست واکنشی اضافه می‌شود | `guild_reactions` و `dm_reactions` |
| `on_reaction_clear_emoji(reaction)` | همهٔ واکنش‌های یک ایموجی از پیامی که در حافظهٔ پیام‌هاست برداشته می‌شوند | `guild_reactions` و `dm_reactions` |
| `on_member_join(member)` | کسی به سرور می‌پیوندد | `members` |
| `on_member_remove(member)` | کسی سرور را ترک می‌کند، اخراج می‌شود یا بن می‌شود | `members` |
| `on_member_update(before, after)` | نام مستعار، نقش‌ها یا سکوت موقت یک عضو تغییر می‌کند | `members` |
| `on_member_ban(guild, user)` | کسی بن می‌شود | `moderation` |
| `on_presence_update(before, after)` | وضعیت یا فعالیت یک عضو تغییر می‌کند | `presences` |
| `on_guild_join(guild)` | ربات به سروری اضافه می‌شود | |
| `on_guild_remove(guild)` | ربات از سروری خارج یا اخراج می‌شود | |
| `on_guild_channel_create(channel)` | کانالی ساخته می‌شود | `guilds` |
| `on_guild_channel_update(before, after)` | نام، موضوع، جایگاه یا تنظیمات یک کانال تغییر می‌کند | `guilds` |
| `on_guild_role_create(role)` | نقشی ساخته می‌شود | `guilds` |
| `on_voice_state_update(member, before, after)` | کسی به کانال صوتی می‌پیوندد، آن را ترک می‌کند، میان کانال‌ها جابه‌جا می‌شود یا بی‌صدا می‌شود | `voice_states` |
| `on_voice_channel_effect(effect)` | کسی در کانال صوتی صدایی از ساندبورد پخش می‌کند | `voice_states` |
| `on_soundboard_sound_create(sound)` | سروری صدای تازه‌ای به ساندبورد اضافه می‌کند (و همچنین `_update` و `_delete`) | `expressions` |
| `on_audit_log_entry_create(entry)` | چیزی در گزارش حسابرسی ثبت می‌شود | `moderation` |
| `on_automod_action(execution)` | قانونی از AutoMod پیامی را مسدود می‌کند، هشداری می‌فرستد یا کسی را به سکوت موقت می‌برد | `auto_moderation_execution` |
| `on_interaction(interaction)` | هر تعاملی می‌رسد؛ `app_commands` و Viewها خودشان آن‌ها را کنترل می‌کنند | |

بعضی از این‌ها، مثل دیسکورد، به دسترسی‌های ربات در سرور هم بستگی دارند: بن‌ها به Ban Members یا View Audit Log
نیاز دارند، گزارش حسابرسی به View Audit Log، دعوت‌نامه‌ها به Manage Channels، AutoMod به Manage Server، و
رویدادهای کانال و وب‌هوک به اینکه ربات آن کانال را ببیند.

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
`on_raw_reaction_add`، `on_raw_reaction_remove`، `on_raw_reaction_clear`، `on_raw_reaction_clear_emoji`،
`on_raw_typing`، `on_raw_member_remove` و، وقتی کلاینت با `enable_raw_presences=True` ساخته شود،
`on_raw_presence_update`.

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
نمی‌دهد: رشته‌ها، رویدادهای زمان‌بندی‌شده، استیج‌ها، یکپارچه‌سازی‌ها، اشتراک‌ها و دسترسی‌های دستورهای
برنامه. [مرجع API](../../reference.md) فهرست کامل آن‌ها را دارد. ثبت کنترل‌کننده برای آن‌ها ضرری
ندارد؛ فقط هرگز صدا زده نمی‌شوند.
