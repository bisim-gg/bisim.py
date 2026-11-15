# Embeds

An embed is a framed card under a message, with a title, a description, a coloured edge, fields and a footer.
Only bots can send embeds.

## Building an embed

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

Every `set_` and `add_` method returns the embed, so calls can be chained:
`bisim.Embed(title='Hi').add_field(name='a', value='b').set_footer(text='c')`.

| Part | How to set it | Limit |
| --- | --- | --- |
| Title | `title=` | 256 characters |
| Description | `description=` | 4096 characters |
| Link on the title | `url=` | |
| Colour of the edge | `colour=` (or `color=`): a `bisim.Colour` or an `int` such as `0x5197ED` | |
| Time at the bottom | `timestamp=`: a timezone aware `datetime` | |
| Author | `set_author(name=..., url=..., icon_url=...)` | 256 characters |
| Footer | `set_footer(text=..., icon_url=...)` | 2048 characters |
| Fields | `add_field(name=..., value=..., inline=True)` | 25 fields; 256 for a name, 1024 for a value |
| Thumbnail, beside the text | `set_thumbnail(url=...)` | 2048 characters |
| Large image, below the fields | `set_image(url=...)` | 2048 characters |

All the text of one embed together must stay within 6000 characters; `len(embed)` tells you how much it has.
A message can carry up to 10 embeds: pass a list as `embeds=`.

`bisim.Colour` has the usual presets (`Colour.red()`, `Colour.blurple()`, `Colour.dark_theme()` and more) and
`Colour.from_rgb(r, g, b)`.

!!! note "Pictures"

    A picture (the image, the thumbnail and the author and footer icons) is an `http` or `https` link, and
    every reader's app loads it from that address, as Discord's did. discord.py's `attachment://name.png` is
    not supported yet: bisim.py leaves such a picture out of the message and logs a warning once. To show a
    file you made, send it with `bisim.File`, or put it somewhere with a public link first.

## Sending embeds

Embeds go wherever a message does:

```python
await channel.send(embed=embed)
await message.reply(embeds=[first, second])
await message.edit(embed=new_embed)  # replaces the embeds; embed=None removes them

# In a slash command
await interaction.response.send_message(embed=embed, ephemeral=True)
await interaction.followup.send(embed=embed)
```

## Reading embeds

`message.embeds` holds the embeds of a received message, including the link previews Bisim makes for links in
a person's message:

```python
for embed in message.embeds:
    print(embed.title, embed.description, embed.url)
    for field in embed.fields:
        print(f'{field.name}: {field.value}')
```

To send a received embed again, possibly changed, `embed.copy()` gives you a new `Embed` with the same content,
and `Embed.from_dict()` builds one from a dictionary.

## Fields side by side

Fields with `inline=True` sit next to each other; a field with `inline=False` starts on its own line:

```python
embed = bisim.Embed(title='Server stats', colour=0x5197ED)
embed.add_field(name='Members', value=str(guild.member_count))
embed.add_field(name='Channels', value=str(len(guild.channels)))
embed.add_field(name='Roles', value=str(len(guild.roles)))
embed.add_field(name='Owner', value=f'<@{guild.owner_id}>', inline=False)
```

The `Embed` class and all of its methods are in the [API reference](../../reference/embeds.md).
