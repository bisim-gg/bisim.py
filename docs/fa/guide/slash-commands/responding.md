# پاسخ به دستورها

به هر تعامل باید پاسخ داد، و فقط **یک بار**. بی‌سیم تا سه ثانیه منتظر این نخستین پاسخ می‌ماند و پس از آن عضو
پیام «برنامه پاسخ نداد» را می‌بیند. توکن تعامل پس از آن تا **۱۵ دقیقه** معتبر می‌ماند تا پاسخ را ویرایش کنید
و پیام‌های بیشتری بفرستید.

- `interaction.response` نخستین پاسخ را می‌دهد: یک پیام، اعلام انتظار، یک فرم یا انتخاب‌های تکمیل خودکار.
- `interaction.followup` پیام‌های بعدی را می‌فرستد.

## فرستادن پیام

```python
@client.tree.command(description='Say hello')
async def hello(interaction: bisim.Interaction) -> None:
    embed = bisim.Embed(title='Hello!', description=f'Nice to see you, {interaction.user.mention}.')
    await interaction.response.send_message('Hi there', embed=embed)
```

`send_message()` این‌ها را می‌گیرد: `content`، `embed` یا `embeds` (حداکثر ۱۰)، `file` یا `files` (حداکثر
۱۰)، `view` برای [دکمه‌ها و منوهای انتخاب](../components/buttons.md)، `poll`، `ephemeral`، `silent` (بدون
اعلان)، `suppress_embeds`، `allowed_mentions` و `delete_after` (چند ثانیه بعد پاسخ پاک شود).

## پاسخ پنهان

```python
await interaction.response.send_message('Only you can see this.', ephemeral=True)
```

پیام پنهان فقط به عضوی نشان داده می‌شود که دستور را اجرا کرده و بخشی از تاریخچهٔ کانال نیست. برای خطاها،
تأییدها و هر چیز شخصی، پاسخ درست همین است.

## کار طولانی: اعلام انتظار

اگر کار بیش از چند لحظه طول می‌کشد، اول اعلام انتظار کنید. عضو تا وقتی کار می‌کنید «*ربات* در حال فکر کردن
است…» را می‌بیند و شما همهٔ ۱۵ دقیقه را در اختیار دارید. پیام انتظار را با `edit_original_response()` کامل
کنید:

```python
@client.tree.command(description='Delete recent messages in this channel')
@app_commands.describe(count='How many messages, 1 to 100')
@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def purge(interaction: bisim.Interaction, count: app_commands.Range[int, 1, 100]) -> None:
    # Deleting can take a while: show "thinking" first.
    await interaction.response.defer(ephemeral=True, thinking=True)
    deleted = await interaction.channel.purge(limit=count)  # type: ignore[union-attr]
    # The first edit fills in the "thinking" message.
    await interaction.edit_original_response(content=f'Deleted {len(deleted)} messages.')
```

`defer(ephemeral=True)` پاسخ نهایی را هم پنهان می‌کند. برای دستور اسلش، اعلام انتظار همیشه پیام «در حال فکر
کردن» را نشان می‌دهد؛ `thinking=` فقط برای [دکمه‌ها و منوهای انتخاب](../components/buttons.md) اهمیت دارد.

!!! note "نکته"
    مثل دیسکورد، نخستین followup پس از اعلام انتظار جای پیام «در حال فکر کردن» را می‌گیرد و مثل همان اعلام
    انتظار پنهان یا همگانی می‌ماند؛ پس `interaction.followup.send()` هم به اندازهٔ `edit_original_response()`
    کار را تمام می‌کند (بی‌سیم از ۲۰۲۶-۱۱-۱۴ این کار را می‌کند). followupهای بعدی پیام تازه‌اند. نظرسنجی
    نمی‌تواند پیام انتظار را پر کند: اول آن را پر کنید و بعد نظرسنجی را به‌صورت followup بفرستید. پیام انتظاری
    که هرگز کامل نشود، پس از پایان ۱۵ دقیقه «برنامه پاسخ نداد» را نشان می‌دهد.

## پیام‌های بعدی

پس از نخستین پاسخ، پیام‌های بیشتر را با `interaction.followup` بفرستید:

```python
await interaction.response.send_message('Starting the count…')
for number in (3, 2, 1):
    await asyncio.sleep(1)
    await interaction.followup.send(str(number))
message = await interaction.followup.send('Done!', ephemeral=True)
```

`followup.send()` پیامی را که فرستاده برمی‌گرداند. `followup.edit_message(message.id, content=...)` و
`followup.delete_message(message.id)` بعداً آن را تغییر می‌دهند یا پاک می‌کنند. بی‌سیم پیش از پاسخ دادن به
تعامل، پیام بعدی را نمی‌پذیرد.

## ویرایش و حذف پاسخ

```python
await interaction.response.send_message('Working on it')
await interaction.edit_original_response(content='Finished.')
message = await interaction.original_response()   # an InteractionMessage
await interaction.delete_original_response()
```

`edit_original_response()` این‌ها را می‌گیرد: `content`، `embed` یا `embeds`، `attachments`، `view` (با
`None` نما حذف می‌شود) و `allowed_mentions`. تنها راه ویرایش یک پاسخ پنهان هم همین است. `attachments` مثل
discord.py فهرست کامل فایل‌ها پس از ویرایش است: هر `Attachment` پیام نگه داشته می‌شود، هر `File` بارگذاری و
اضافه می‌شود و فایلی که در فهرست نباشد حذف می‌شود؛ اگر `attachments` را نفرستید همهٔ فایل‌ها می‌مانند.

## فقط یک پاسخ

صدا زدن دوبارهٔ هر یک از متدهای `interaction.response` خطای `bisim.InteractionResponded` می‌دهد. وقتی کدی
ممکن است پیش یا پس از نخستین پاسخ اجرا شود، از `interaction.response.is_done()` بپرسید:

```python
async def tell(interaction: bisim.Interaction, text: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
```

## فایل، تصویر و نظرسنجی

پاسخ هم مثل هر پیام دیگری فایل می‌پذیرد. کتاب‌خانه هر فایل را اول با توکن تعامل بارگذاری می‌کند و بعد
پاسخی را می‌فرستد که به آن اشاره می‌کند، پس رباتی که از راه [نشانی تعامل‌ها](../topics/interactions-url.md)
پاسخ می‌دهد هم می‌تواند فایل بفرستد. امبد با `attachment://name` یکی از آن‌ها را نشان می‌دهد:

```python
file = bisim.File('chart.png')
embed = bisim.Embed(title='This week').set_image(url='attachment://chart.png')
await interaction.response.send_message(file=file, embed=embed)

# After a deferral, the file fills the thinking message.
await interaction.response.defer(thinking=True)
await interaction.edit_original_response(content='Done.', attachments=[bisim.File('report.txt')])
```

نظرسنجی تنها فرستاده می‌شود (بدون متن، امبد، فایل یا نما) و هرگز در پاسخ پنهان نیست:

```python
poll = bisim.Poll('Lunch?', duration=datetime.timedelta(hours=2))
poll.add_answer(text='Rice').add_answer(text='Bread')
await interaction.response.send_message(poll=poll)
```

نظرسنجی را نمی‌توان در ویرایش اضافه کرد: `edit_original_response(poll=...)` خطای `bisim.NotSupported` می‌دهد.

## منشن‌ها

`allowed_mentions` مثل دیسکورد کار می‌کند: بدون آن هر منشن متن می‌تواند خبر کند؛ با آن فقط آن‌چه اجازه
می‌دهد خبر می‌کند و بقیه به‌صورت متن ساده نوشته می‌شود. `Client(allowed_mentions=...)` پیش‌فرض همهٔ پیام‌ها،
از جمله پاسخ تعامل‌ها، را تعیین می‌کند.

```python
await interaction.response.send_message(
    f'{interaction.user.mention} started a vote, @everyone',
    allowed_mentions=bisim.AllowedMentions(everyone=False),
)
```

امبدها با محدودیت‌هایی که در صفحهٔ [امبدها](../topics/embeds.md) آمده کار می‌کنند. متدها زیر
`InteractionResponse` و `Interaction` در [مرجع API](../../reference.md) آمده‌اند.
