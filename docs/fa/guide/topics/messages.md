# پیام‌ها و واکنش‌ها

## فرستادن پیام

هر چیزی که بتوان به آن پیام فرستاد یک *messageable* است: کانال‌های متنی، پیام‌های خصوصی، اعضا و کاربران، و
`ctx` در دستورهای پیشوندی. همهٔ آن‌ها متد `send()` یکسانی دارند:

```python
channel = client.get_channel(123456789012345678)
await channel.send('Hello!')
await channel.send('With an embed', embed=bisim.Embed(title='Hi'))
await channel.send('Gone in ten seconds', delete_after=10)
```

متن پیام حداکثر ۴۰۰۰ نویسه است. کانال‌های متنی و پیام‌های خصوصی پیام می‌پذیرند؛ کانال‌های صوتی و دسته‌ها نه
(فرستادن به کانال صوتی `bisim.NotSupported` می‌دهد). `send()` همان `bisim.Message` ساخته‌شده را برمی‌گرداند.

برای نوشتن خصوصی به کسی، به خود آن عضو یا کاربر پیام بفرستید. اگر آن شخص با ربات در سروری مشترک باشد و
تنظیمات حریم خصوصی‌اش اجازه بدهد، بی‌سیم پیام خصوصی را باز می‌کند؛ وگرنه `send()` خطای `bisim.Forbidden`
می‌دهد.

```python
await member.send('Thanks for joining!')
```

## پاسخ، ویرایش و حذف

```python
@client.event
async def on_message(message: bisim.Message):
    if message.content != '!hello':
        return
    reply = await message.reply(f'Hello, {message.author.display_name}!')
    await reply.edit(content='Hello again!')
    await reply.delete(delay=10)
```

`message.reply()` همان `send()` است با ارجاع به آن پیام. ربات فقط پیام‌های خودش را می‌تواند ویرایش کند. حذف
پیام دیگران دسترسی مدیریت پیام‌ها (Manage Messages) می‌خواهد. برای حذف چند پیام با هم از `channel.purge()` یا
`channel.delete_messages()` (هر بار تا ۱۰۰ پیام) استفاده کنید:

```python
deleted = await channel.purge(limit=50, check=lambda m: m.author.bot)
await channel.send(f'Deleted {len(deleted)} messages from bots.', delete_after=5)
```

## فایل‌ها

فایل را در `bisim.File` بپیچید و آن را با `file=`، یا فهرستی از آن‌ها را با `files=` بفرستید:

```python
await channel.send('Here is the report.', file=bisim.File('report.pdf'))

import io

data = io.BytesIO(b'hello')
await channel.send(files=[
    bisim.File(data, filename='hello.txt', description='A greeting'),
    bisim.File('cat.png', spoiler=True),
])
```

`File` یک مسیر یا یک شیء فایل دودویی می‌گیرد و فقط یک بار قابل استفاده است. بی‌سیم در هر پیام حداکثر ۱۰ فایل
می‌پذیرد که هر کدام به‌طور پیش‌فرض تا ۱۰ مگابایت است (`guild.filesize_limit` سقف واقعی را می‌گوید). کتاب‌خانه
اول فایل‌ها را در فضای ذخیره‌سازی بی‌سیم بارگذاری می‌کند و سپس پیامی را که به آن‌ها اشاره دارد می‌فرستد؛ همهٔ
این کارها داخل `send()` انجام می‌شود.

فایل‌هایی که دیگران فرستاده‌اند در `message.attachments` هستند. `await attachment.save('copy.png')` یکی از
آن‌ها را روی دیسک می‌نویسد و `await attachment.to_file()` آن را به یک `File` تبدیل می‌کند تا دوباره بفرستید.

ربات می‌تواند مثل discord.py فایل‌های پیام‌های خودش را تغییر دهد: `message.edit(attachments=[...])` فهرست کامل
فایل‌ها پس از ویرایش را می‌گیرد (هر `Attachment` پیام نگه داشته می‌شود، هر `File` بارگذاری و اضافه می‌شود و
فایلی که در فهرست نباشد حذف می‌شود)، و `add_files()` و `remove_attachments()` همین کار را در یک قدم می‌کنند.
پاسخ تعامل‌ها و وب‌هوک‌ها هم فایل می‌پذیرند. امبد با `attachment://name` یکی از فایل‌های پیام را نشان
می‌دهد: [امبدها](embeds.md) را ببینید.

## خواندن پیام‌ها

`channel.history()` پیام‌های یک کانال را از جدیدترین به عقب مرور می‌کند:

```python
async for message in channel.history(limit=200):
    print(f'{message.author}: {message.content}')

# Or as a list
messages = [message async for message in channel.history(limit=20, oldest_first=True)]
```

این متد `before`، `after` و `around` را هم می‌گیرد که هر کدام می‌تواند یک پیام، یک `Object` یا یک `datetime`
باشد. `await channel.fetch_message(id)` یک پیام را بارگذاری می‌کند.

منشن‌ها در متن به شکل نشانه‌هایی مثل `<@123>` و `<@&456>` می‌آیند. `message.mentions`،
`message.role_mentions` و `message.channel_mentions` آن‌ها را به شیء تبدیل می‌کنند و `message.clean_content`
متنی است که در آن نام‌ها جای این نشانه‌ها نشسته‌اند.

## واکنش‌ها

```python
await message.add_reaction('👍')
await message.add_reaction('<:party:123456789012345678>')  # a custom server emoji

await message.remove_reaction('👍', client.user)  # the bot's own reaction
await message.remove_reaction('👍', member)  # someone else's; needs Manage Messages
await message.clear_reaction('👍')  # everyone's reactions with this emoji
await message.clear_reactions()  # every reaction
```

`message.reactions` هر ایموجی را با `count` آن و اینکه ربات هم واکنش داده یا نه (`me`) فهرست می‌کند. برای دیدن
کسانی که واکنش داده‌اند، روی `reaction.users()` حلقه بزنید. واکنش‌ها رویداد هم دارند: صفحهٔ
[رویدادها](events.md) را ببینید.

## سنجاق و در حال نوشتن

```python
await message.pin()
await message.unpin()

pinned = [message async for message in channel.pins()]

async with channel.typing():
    # Shows "typing" while the block runs
    report = await build_report()
await channel.send(report)
```

سنجاق کردن پیام دسترسی سنجاق پیام‌ها (Pin Messages) می‌خواهد.

## منشن‌ها و پرچم‌ها

`allowed_mentions` مثل دیسکورد کار می‌کند، برای هر پیام یا با `Client(allowed_mentions=...)` برای کل کلاینت:
بدون آن هر منشن متن می‌تواند خبر کند؛ با آن فقط آن‌چه اجازه می‌دهد خبر می‌کند و بی‌سیم بقیه را به‌صورت متن ساده
(نام آن شخص یا نقش) در پیام می‌نویسد، پس کسی را خبر نمی‌کند.

```python
await channel.send('Server restart in 5 minutes, @everyone', allowed_mentions=bisim.AllowedMentions(everyone=False))
await channel.send(f'Thanks {member.mention}', silent=True)  # no notification
await channel.send('https://example.com', suppress_embeds=True)  # no link card
await message.edit(suppress=True)  # hide a message's embeds; suppress=False brings them back
```

`message.flags.suppress_embeds` و `message.flags.silent` می‌گویند پیام با چه پرچم‌هایی فرستاده شده؛ پیامی که
امبدهایش پنهان شده `message.embeds` خالی دارد.

## آنچه در بی‌سیم نیست

این‌ها `bisim.NotSupported` می‌دهند: رشته‌ها (`message.create_thread()`)، بازارسال (`message.forward()`) و
انتشار در کانال‌های اعلان (`message.publish()`). خواندن متن با صدا (`tts=True`) پذیرفته می‌شود و نادیده گرفته
می‌شود.

فهرست کامل متدهای پیام در [مرجع API](../../reference.md) آمده است.
