# Responding to commands

Every interaction must be answered, and answered **once**. Bisim waits up to three seconds for that first
answer; after that the member sees "The application did not respond". The interaction's token then stays
valid for **15 minutes**, for editing the answer and sending more messages.

- `interaction.response` gives the first answer: a message, a deferral, a modal or autocomplete choices.
- `interaction.followup` sends further messages after it.

## Sending a message

```python
@client.tree.command(description='Say hello')
async def hello(interaction: bisim.Interaction) -> None:
    embed = bisim.Embed(title='Hello!', description=f'Nice to see you, {interaction.user.mention}.')
    await interaction.response.send_message('Hi there', embed=embed)
```

`send_message()` takes `content`, `embed` or `embeds` (up to 10), `file` or `files` (up to 10), `view` for
[buttons and select menus](../components/buttons.md), `poll`, `ephemeral`, `silent` (no notification),
`suppress_embeds`, `allowed_mentions` and `delete_after` (seconds after which the answer is deleted).

## Ephemeral answers

```python
await interaction.response.send_message('Only you can see this.', ephemeral=True)
```

An ephemeral message is shown only to the member who ran the command, and it is not part of the channel's
history. It is the right answer for errors, confirmations and anything personal.

## Taking longer: defer

If the work takes more than a moment, defer first. The member sees "*bot* is thinking…" while you work,
and you then have the full 15 minutes. Fill in the thinking message with `edit_original_response()`:

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

`defer(ephemeral=True)` makes the final answer ephemeral too. For a slash command the deferral always shows
the thinking message; `thinking=` matters for [buttons and select menus](../components/buttons.md).

!!! note
    As on Discord, the first followup after a deferral takes the place of the thinking message and keeps the
    deferral's visibility, so `interaction.followup.send()` finishes the answer as well as
    `edit_original_response()` does (Bisim does this since 2026-11-14). Later followups are new messages. A
    poll cannot fill the thinking message: fill it first, then send the poll as a followup. A thinking message
    that is never filled shows "The application did not respond" once the 15 minutes are over.

## Followups

After the first answer, send more messages with `interaction.followup`:

```python
await interaction.response.send_message('Starting the count…')
for number in (3, 2, 1):
    await asyncio.sleep(1)
    await interaction.followup.send(str(number))
message = await interaction.followup.send('Done!', ephemeral=True)
```

`followup.send()` returns the message it sent. `followup.edit_message(message.id, content=...)` and
`followup.delete_message(message.id)` change it later. Bisim refuses a followup before the interaction has
been answered.

## Editing and deleting the answer

```python
await interaction.response.send_message('Working on it')
await interaction.edit_original_response(content='Finished.')
message = await interaction.original_response()   # an InteractionMessage
await interaction.delete_original_response()
```

`edit_original_response()` takes `content`, `embed` or `embeds`, `attachments`, `view` (`None` removes the
view) and `allowed_mentions`. It is also the only way to edit an ephemeral answer. `attachments` is the whole
list after the edit, as in discord.py: an `Attachment` of the message is kept, a `File` is uploaded and added,
and a file left out is removed; leave `attachments` out to keep every file.

## Answering once

A second call to any `interaction.response` method raises `bisim.InteractionResponded`. When code can run
before or after the first answer, ask `interaction.response.is_done()`:

```python
async def tell(interaction: bisim.Interaction, text: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
```

## Files, pictures and polls

An answer carries files as any message does. The library uploads each file with the interaction's token
first, then sends the answer that names it, so a bot answering on an
[Interactions URL](../topics/interactions-url.md) can send files too. An embed shows one of them with
`attachment://name`:

```python
file = bisim.File('chart.png')
embed = bisim.Embed(title='This week').set_image(url='attachment://chart.png')
await interaction.response.send_message(file=file, embed=embed)

# After a deferral, the file fills the thinking message.
await interaction.response.defer(thinking=True)
await interaction.edit_original_response(content='Done.', attachments=[bisim.File('report.txt')])
```

A poll is sent on its own (no text, embeds, files or view with it) and never in an ephemeral answer:

```python
poll = bisim.Poll('Lunch?', duration=datetime.timedelta(hours=2))
poll.add_answer(text='Rice').add_answer(text='Bread')
await interaction.response.send_message(poll=poll)
```

A poll cannot be added in an edit: `edit_original_response(poll=...)` raises `bisim.NotSupported`.

## Mentions

`allowed_mentions` works as on Discord: without it every mention in the text may ping; with it only what it
allows does, and the rest is written as plain words. `Client(allowed_mentions=...)` sets the default for every
message, interaction answers included.

```python
await interaction.response.send_message(
    f'{interaction.user.mention} started a vote, @everyone',
    allowed_mentions=bisim.AllowedMentions(everyone=False),
)
```

Embeds work, with the limits described in [Embeds](../topics/embeds.md). The methods are listed under
`InteractionResponse` and `Interaction` in the [API reference](../../reference/interactions.md).
