# Messages and reactions

## Sending messages

Anything you can send to is a *messageable*: text channels, DMs, members and users, and `ctx` in prefix
commands. They all have the same `send()`:

```python
channel = client.get_channel(123456789012345678)
await channel.send('Hello!')
await channel.send('With an embed', embed=bisim.Embed(title='Hi'))
await channel.send('Gone in ten seconds', delete_after=10)
```

The text of a message is at most 4000 characters. Text channels and DMs take messages; voice channels and
categories do not (sending to a voice channel raises `bisim.NotSupported`). `send()` returns the
`bisim.Message` it created.

To write to someone in private, send to the member or user. Bisim opens the DM if the person shares a server
with the bot and their privacy settings allow it; otherwise `send()` raises `bisim.Forbidden`.

```python
await member.send('Thanks for joining!')
```

## Replying, editing and deleting

```python
@client.event
async def on_message(message: bisim.Message):
    if message.content != '!hello':
        return
    reply = await message.reply(f'Hello, {message.author.display_name}!')
    await reply.edit(content='Hello again!')
    await reply.delete(delay=10)
```

`message.reply()` is `send()` with a reference to the message. A bot can edit only its own messages. Deleting
someone else's message needs the Manage Messages permission. To remove many messages at once, use
`channel.purge()` or `channel.delete_messages()` (up to 100 at a time):

```python
deleted = await channel.purge(limit=50, check=lambda m: m.author.bot)
await channel.send(f'Deleted {len(deleted)} messages from bots.', delete_after=5)
```

## Files

Wrap a file in `bisim.File` and pass it as `file=`, or a list as `files=`:

```python
await channel.send('Here is the report.', file=bisim.File('report.pdf'))

import io

data = io.BytesIO(b'hello')
await channel.send(files=[
    bisim.File(data, filename='hello.txt', description='A greeting'),
    bisim.File('cat.png', spoiler=True),
])
```

A `File` takes a path or a binary file object, and is used once. Bisim takes up to 10 files per message, each
up to 10 MiB by default (`guild.filesize_limit` tells the real limit). The library uploads the files to
Bisim's storage first and then sends the message that refers to them, all inside `send()`.

Files a person sent are in `message.attachments`. `await attachment.save('copy.png')` writes one to disk, and
`await attachment.to_file()` turns it into a `File` you can send again.

!!! note "What Bisim does not support with files"

    A message's files cannot be changed after it is sent, so `message.edit(attachments=...)`,
    `add_files()` and `remove_attachments()` raise `bisim.NotSupported`. Interaction responses and webhooks
    do not take files yet either.

## Reading messages

`channel.history()` walks back through a channel, newest first:

```python
async for message in channel.history(limit=200):
    print(f'{message.author}: {message.content}')

# Or as a list
messages = [message async for message in channel.history(limit=20, oldest_first=True)]
```

It also takes `before`, `after` and `around`, each a message, an `Object` or a `datetime`.
`await channel.fetch_message(id)` loads one message.

Mentions arrive in the text as tokens such as `<@123>` and `<@&456>`. `message.mentions`,
`message.role_mentions` and `message.channel_mentions` resolve them, and `message.clean_content` is the text
with them replaced by names.

## Reactions

```python
await message.add_reaction('👍')
await message.add_reaction('<:party:123456789012345678>')  # a custom server emoji

await message.remove_reaction('👍', client.user)  # the bot's own reaction
await message.remove_reaction('👍', member)  # someone else's; needs Manage Messages
await message.clear_reaction('👍')  # everyone's reactions with this emoji
await message.clear_reactions()  # every reaction
```

`message.reactions` lists each emoji with its `count` and whether the bot reacted (`me`). To see who reacted,
iterate `reaction.users()`. Reactions are also events: see [events](events.md).

## Pins and typing

```python
await message.pin()
await message.unpin()

pinned = [message async for message in channel.pins()]

async with channel.typing():
    # Shows "typing" while the block runs
    report = await build_report()
await channel.send(report)
```

Pinning needs the Pin Messages permission.

## Not on Bisim

These raise `bisim.NotSupported`: threads (`message.create_thread()`), forwarding (`message.forward()`) and
publishing to announcement channels (`message.publish()`). Text to speech (`tts=True`) and `allowed_mentions`
are accepted and ignored.

The full list of message methods is in the [API reference](../../reference/messages.md).
