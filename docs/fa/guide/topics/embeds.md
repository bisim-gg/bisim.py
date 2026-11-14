# امبدها

امبد یک کارت قاب‌دار زیر پیام است که عنوان، توضیح، لبهٔ رنگی، فیلدها و پانویس دارد. فقط ربات‌ها می‌توانند امبد
بفرستند.

## ساختن امبد

```python
import datetime

import bisim

embed = bisim.Embed(
    title='Weekly report',
    description='Everything that happened on the server this week.',
    url='https://bisim.gg',
    colour=bisim.Colour.green(),
    timestamp=datetime.datetime.now(datetime.timezone.utc),
)
embed.set_author(name='Report bot', url='https://bisim.gg')
embed.add_field(name='New members', value='42')
embed.add_field(name='Messages', value='1,337')
embed.add_field(name='Most active channel', value='#general', inline=False)
embed.set_footer(text='Sent every Friday')

await channel.send(embed=embed)
```

همهٔ متدهای `set_` و `add_` خود امبد را برمی‌گردانند، پس می‌توان آن‌ها را پشت سر هم صدا زد:
`bisim.Embed(title='Hi').add_field(name='a', value='b').set_footer(text='c')`.

| بخش | روش تنظیم | سقف |
| --- | --- | --- |
| عنوان | `title=` | ۲۵۶ نویسه |
| توضیح | `description=` | ۴۰۹۶ نویسه |
| پیوند روی عنوان | `url=` | |
| رنگ لبه | `colour=` (یا `color=`): یک `bisim.Colour` یا یک `int` مثل `0x5197ED` | |
| زمان پایین امبد | `timestamp=`: یک `datetime` دارای منطقهٔ زمانی | |
| نویسنده | `set_author(name=..., url=...)` | ۲۵۶ نویسه |
| پانویس | `set_footer(text=...)` | ۲۰۴۸ نویسه |
| فیلدها | `add_field(name=..., value=..., inline=True)` | ۲۵ فیلد؛ ۲۵۶ نویسه برای نام و ۱۰۲۴ برای مقدار |

مجموع متن یک امبد نباید از ۶۰۰۰ نویسه بیشتر شود؛ `len(embed)` می‌گوید چقدر متن دارد. هر پیام می‌تواند تا ۱۰ امبد
داشته باشد: فهرستی از آن‌ها را با `embeds=` بفرستید.

`bisim.Colour` رنگ‌های آمادهٔ معمول (`Colour.red()`، `Colour.blurple()`، `Colour.dark_theme()` و بیشتر) و
`Colour.from_rgb(r, g, b)` را دارد.

!!! note "آنچه بی‌سیم نشان می‌دهد"

    بی‌سیم عنوان، توضیح، پیوند، رنگ، زمان، نام و پیوند نویسنده، متن پانویس و فیلدها را نشان می‌دهد.
    `set_image()`، `set_thumbnail()` و `icon_url` نویسنده و پانویس پذیرفته می‌شوند و روی شیء `Embed` می‌مانند تا
    کدی که برای discord.py نوشته شده همچنان کار کند، اما فرستاده نمی‌شوند و بی‌سیم آن‌ها را نشان نمی‌دهد.

## فرستادن امبد

امبد هر جا که پیام برود، می‌رود:

```python
await channel.send(embed=embed)
await message.reply(embeds=[first, second])
await message.edit(embed=new_embed)  # replaces the embeds; embed=None removes them

# In a slash command
await interaction.response.send_message(embed=embed, ephemeral=True)
await interaction.followup.send(embed=embed)
```

## خواندن امبدها

`message.embeds` امبدهای یک پیام دریافتی را نگه می‌دارد، از جمله پیش‌نمایشی که بی‌سیم برای پیوندهای پیام
کاربران می‌سازد:

```python
for embed in message.embeds:
    print(embed.title, embed.description, embed.url)
    for field in embed.fields:
        print(f'{field.name}: {field.value}')
```

برای فرستادن دوبارهٔ یک امبد دریافتی، با تغییر یا بدون آن، `embed.copy()` یک `Embed` تازه با همان محتوا به شما
می‌دهد و `Embed.from_dict()` یک امبد را از یک دیکشنری می‌سازد.

## فیلدهای کنار هم

فیلدهایی که `inline=True` دارند کنار هم قرار می‌گیرند؛ فیلدی با `inline=False` از خط تازه شروع می‌شود:

```python
embed = bisim.Embed(title='Server stats', colour=0x5197ED)
embed.add_field(name='Members', value=str(guild.member_count))
embed.add_field(name='Channels', value=str(len(guild.channels)))
embed.add_field(name='Roles', value=str(len(guild.roles)))
embed.add_field(name='Owner', value=f'<@{guild.owner_id}>', inline=False)
```

کلاس `Embed` و همهٔ متدهایش در [مرجع API](../../reference.md) آمده‌اند.
