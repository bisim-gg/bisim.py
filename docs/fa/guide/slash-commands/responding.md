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

`send_message()` این‌ها را می‌گیرد: `content`، `embed` یا `embeds` (حداکثر ۱۰)، `view` برای
[دکمه‌ها و منوهای انتخاب](../components/buttons.md)، `ephemeral` و `delete_after` (چند ثانیه بعد پاسخ پاک
شود).

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
    کار را تمام می‌کند. پیام انتظاری که هرگز کامل نشود، پس از پایان ۱۵ دقیقه «برنامه پاسخ نداد» را نشان می‌دهد.

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

`edit_original_response()` این‌ها را می‌گیرد: `content`، `embed` یا `embeds` و `view` (با `None` نما حذف
می‌شود). تنها راه ویرایش یک پاسخ پنهان هم همین است.

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

## آن‌چه پاسخ نمی‌تواند داشته باشد

بی‌سیم در پاسخ تعامل‌ها فایل، پیوست یا نظرسنجی نمی‌پذیرد. `file=` و `files=` در `send_message()` و
`followup.send()`، `attachments=` در `edit_original_response()` و `poll=` در هر کدام از آن‌ها به‌جای نادیده
گرفته شدن، خطای `bisim.NotSupported` می‌دهند. برای فرستادن فایل، اول پاسخ دهید و بعد آن را به‌صورت یک پیام
معمولی در کانال بفرستید:

```python
await interaction.response.send_message('Here is the report.')
await interaction.channel.send(file=bisim.File('report.txt'))  # type: ignore[union-attr]
```

امبدها با محدودیت‌هایی که در صفحهٔ [امبدها](../topics/embeds.md) آمده کار می‌کنند. متدها زیر
`InteractionResponse` و `Interaction` در [مرجع API](../../reference.md) آمده‌اند.
