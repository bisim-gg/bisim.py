# Views and buttons

Buttons and select menus sit under a message. In bisim.py they live in a **view**: a subclass of
`bisim.ui.View` that holds the items, receives the clicks and calls your code. This is discord.py's UI kit, with
the same names. Only bots can put buttons and menus on a message.

## A first view

```python
import bisim
from bisim import ui


class Counter(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.count = 0

    @ui.button(label='Count: 0', style=bisim.ButtonStyle.primary)
    async def count_button(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.count += 1
        button.label = f'Count: {self.count}'
        await interaction.response.edit_message(view=self)
```

Send the view with any message:

```python
# in a slash command
await interaction.response.send_message('Press the button.', view=Counter())

# in a prefix command
await ctx.send('Press the button.', view=Counter())

# anywhere else
await channel.send('Press the button.', view=Counter())
```

The function decorated with `@ui.button` receives the view, the `bisim.Interaction` of the click and the button
itself. Inside the view the button is also an attribute: `self.count_button.label` reads and changes it.

`@ui.button` takes `label` (up to 80 characters), `style`, `emoji` (a Unicode emoji or a server emoji such as
`'<:name:id>'`), `custom_id` (up to 100 characters; one is generated when you leave it out), `disabled` and `row`.

| Style | Looks like |
| --- | --- |
| `ButtonStyle.primary` (alias `blurple`) | the main action |
| `ButtonStyle.secondary` (aliases `grey`, `gray`) | a neutral action, the default |
| `ButtonStyle.success` (alias `green`) | a positive action |
| `ButtonStyle.danger` (alias `red`) | an action that cannot be undone |
| `ButtonStyle.link` (alias `url`) | opens an address; no callback |

Premium buttons (`sku_id`) do not exist on Bisim and raise `bisim.NotSupported`.

## Answering a click

Every click is an interaction, and it must be answered within three seconds, once:

- `await interaction.response.edit_message(content=..., view=...)` changes the message the button is on.
  `view=None` removes the buttons.
- `await interaction.response.send_message('...', ephemeral=True)` answers with a new message, here one only the
  person who clicked sees.
- `await interaction.response.defer()` acknowledges the click without changing anything. Afterwards, edit the
  message with `interaction.edit_original_response(...)` or send more with `interaction.followup.send(...)`.
- `await interaction.response.send_modal(...)` opens a [modal](modals.md).

See [Responding to commands](../slash-commands/responding.md) for everything a response can carry.

## Link buttons and items added in code

A link button has a `url` and no callback, so it cannot be made with the decorator. Create the item and add it:

```python
view = ui.View()
view.add_item(ui.Button(label='Bisim docs', url='https://docs.bisim.gg'))
await ctx.send('Read more:', view=view)
```

`add_item`, `remove_item` and `clear_items` change a view at any time, and `view.children` lists its items. To give
an item its own behaviour, subclass it and override `callback`:

```python
class RemoveMe(ui.Button):
    async def callback(self, interaction: bisim.Interaction) -> None:
        self.view.remove_item(self)
        await interaction.response.edit_message(view=self.view)
```

A view holds up to 25 items in 5 rows. A row has room for 5 buttons or one select menu. Items fill the rows in
order; `row=0` to `row=4` places an item yourself, and an item that does not fit raises `ValueError`.

## Who may click

Override `interaction_check` to decide whether an interaction reaches the callbacks. Returning `False` ignores it:

```python
class Confirm(ui.View):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.accepted = None

    async def interaction_check(self, interaction: bisim.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message('Only the person who asked can answer.', ephemeral=True)
        return False

    @ui.button(label='Continue', style=bisim.ButtonStyle.success)
    async def accept(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.accepted = True
        await interaction.response.edit_message(content='Going ahead.', view=None)
        self.stop()
```

An exception in a callback or in `interaction_check` goes to `on_error(interaction, error, item)`, which logs it
unless you override it.

## Timeouts, stop and wait

`timeout` counts the seconds since the last click (180 by default; `None` never times out). When it runs out the
view stops listening and calls `on_timeout`. To disable the buttons then, keep the message the view was sent with:

```python
class Poll(ui.View):
    message = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


view = Poll(timeout=300)
view.message = await ctx.send('Vote!', view=view)
# after interaction.response.send_message(...): view.message = await interaction.original_response()
```

`view.stop()` stops listening at once. `await view.wait()` waits until the view stops and returns `True` if it
timed out, which suits a question with a yes and a no:

```python
@bot.command()
async def clear(ctx: commands.Context) -> None:
    view = Confirm(ctx.author.id)
    await ctx.send('Delete the last 100 messages here?', view=view)
    if await view.wait() or not view.accepted:
        await ctx.send('Nothing was done.')
        return
    await ctx.channel.purge(limit=100)
```

## Persistent views

A view normally stops working when the bot restarts. A **persistent** view keeps answering clicks on messages it
sent earlier. It needs `timeout=None` and a fixed `custom_id` on every item, and it must be registered when the bot
starts:

```python
class Panel(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label='Open a ticket', style=bisim.ButtonStyle.primary, custom_id='panel:ticket')
    async def ticket(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message('A moderator will be with you soon.', ephemeral=True)


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        self.add_view(Panel())
```

`add_view` raises `ValueError` for a view that is not persistent. `examples/buttons.py` in the repository has a
complete bot with a poll, a confirmation, a select menu, a modal and a persistent panel.

The view classes are in the [API reference](../../reference/ui.md).
