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

`send_message()` takes `content`, `embed` or `embeds` (up to 10), `view` for
[buttons and select menus](../components/buttons.md), `ephemeral` and `delete_after` (seconds after which
the answer is deleted).

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
    `edit_original_response()` does. A thinking message that is never filled shows "The application did not
    respond" once the 15 minutes are over.

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

`edit_original_response()` takes `content`, `embed` or `embeds` and `view` (`None` removes the view). It is
also the only way to edit an ephemeral answer.

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

## What an answer cannot carry

Bisim does not take files, attachments or polls in interaction answers. `file=` and `files=` in
`send_message()` and `followup.send()`, `attachments=` in `edit_original_response()` and `poll=` in any of
them raise `bisim.NotSupported` instead of being dropped. To share a file, answer first and then post it as an
ordinary message in the channel:

```python
await interaction.response.send_message('Here is the report.')
await interaction.channel.send(file=bisim.File('report.txt'))  # type: ignore[union-attr]
```

Embeds work, with the limits described in [Embeds](../topics/embeds.md). The methods are listed under
`InteractionResponse` and `Interaction` in the [API reference](../../reference/interactions.md).
