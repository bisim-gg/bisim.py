# Modals

A modal is a small form that opens over Bisim. It has text boxes, and when the person sends it, it comes back to the
bot as an interaction. In bisim.py a modal is a subclass of `bisim.ui.Modal`.

## Making a modal

```python
import bisim
from bisim import ui


class Feedback(ui.Modal, title='Send feedback'):
    topic = ui.TextInput(label='Topic', placeholder='What is it about?', max_length=50)
    details = ui.TextInput(label='Details', style=bisim.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        print(f'Feedback from {interaction.user}: {self.topic.value}: {self.details.value}')
        await interaction.response.send_message('Thanks, we read every message.', ephemeral=True)
```

Each `ui.TextInput` class attribute becomes a text box, in the order they are written, each on its own row. A modal
has up to five of them, and its title takes up to 45 characters.

| Option | Meaning |
| --- | --- |
| `label` | the text above the box, up to 45 characters (required) |
| `style` | `bisim.TextStyle.short` for one line (the default) or `bisim.TextStyle.paragraph` for several |
| `placeholder` | grey text shown while the box is empty, up to 100 characters |
| `default` | text the box starts with, up to 4000 characters |
| `required` | whether the box must be filled in; `True` by default |
| `min_length`, `max_length` | the allowed length, 0 to 4000 and 1 to 4000 |

After the modal is sent, `self.topic.value` (or `str(self.topic)`) is what the person typed, and an empty string for
an optional box left empty. On Bisim a modal holds text boxes only.

## Opening it

A modal is opened as the **first** answer to an interaction: a slash command, a context menu command, a button or a
select menu.

```python
@tree.command(description='Send feedback to the team')
async def feedback(interaction: bisim.Interaction) -> None:
    await interaction.response.send_modal(Feedback())
```

From a button:

```python
class Panel(ui.View):
    @ui.button(label='Send feedback', style=bisim.ButtonStyle.primary)
    async def feedback(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(Feedback())
```

You cannot defer first and open a modal afterwards, a submitted modal cannot open another one, and an autocomplete
request cannot open one. A prefix command has no interaction, so it cannot open a modal either: send a button that
opens it. Once opened, a modal can be sent once, within 15 minutes.

## Answering the submission

`on_submit` receives the submission as an interaction, which must be answered like any other: send a message,
`defer()`, or, for a modal opened from a button, `edit_message` to change the message the button is on.

If `on_submit` raises, `on_error(interaction, error)` is called. It logs the error unless you override it, and
the interaction still needs an answer:

```python
class Feedback(ui.Modal, title='Send feedback'):
    topic = ui.TextInput(label='Topic')

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        await save_feedback(interaction.user.id, self.topic.value)
        await interaction.response.send_message('Saved.', ephemeral=True)

    async def on_error(self, interaction: bisim.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Something went wrong.', ephemeral=True)
```

`interaction_check` works as it does in views: return `False` to ignore a submission.

## Modals that depend on the moment

Pass what the modal needs to `__init__`, call `super().__init__()`, and change the text boxes afterwards. The title
can be given per modal as well:

```python
class EditNote(ui.Modal):
    text = ui.TextInput(label='Note', style=bisim.TextStyle.paragraph)

    def __init__(self, name: str, current: str) -> None:
        super().__init__(title=f'Edit {name}')
        self.name = name
        self.text.default = current

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        notes[self.name] = self.text.value
        await interaction.response.send_message(f'Saved {self.name}.', ephemeral=True)
```

The modal classes are in the [API reference](../../reference/ui.md).
