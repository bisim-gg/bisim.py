# Select menus

A select menu is a drop-down list under a message. Like buttons, menus live in a [view](buttons.md). Each menu takes
a whole row, so a message has up to five of them. Bisim has five kinds: a menu with your own options, and menus that
Bisim fills with members, roles, both, or channels.

## A menu with your own options

```python
import bisim
from bisim import ui


class Colours(ui.View):
    @ui.select(
        placeholder='Pick up to two colours',
        min_values=1,
        max_values=2,
        options=[
            bisim.SelectOption(label='Red', value='red', emoji='🟥'),
            bisim.SelectOption(label='Green', value='green', emoji='🟩'),
            bisim.SelectOption(label='Blue', value='blue', emoji='🟦', description='The calm one'),
        ],
    )
    async def colours(self, interaction: bisim.Interaction, select: ui.Select) -> None:
        chosen = ', '.join(select.values)
        await interaction.response.send_message(f'You chose {chosen}.', ephemeral=True)


await ctx.send('Which colours do you like?', view=Colours())
```

`select.values` is the list of the chosen options' values, as strings. A menu has up to 25 options. An option has a
`label` people see, a `value` your code gets (the label, when left out), an optional `description` and `emoji`, and
`default=True` to show it chosen from the start; the label, value and description take up to 100 characters each.

`min_values` (0 to 25) and `max_values` (1 to 25) set how many options can be chosen, and `placeholder` is the text
shown while nothing is chosen. `disabled=True`, `custom_id` and `row` work as they do for buttons.

Options can also be added in code, up to the limit of 25:

```python
select = ui.Select(placeholder='Choose a role colour')
for name in ('Red', 'Green', 'Blue'):
    select.add_option(label=name, value=name.lower())

view = ui.View()
view.add_item(select)
```

## A menu as its own class

Subclass `ui.Select` and override `callback` to keep a menu in one place and reuse it:

```python
class LanguageSelect(ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder='Choose your language',
            options=[
                bisim.SelectOption(label='فارسی', value='fa', description='Persian'),
                bisim.SelectOption(label='English', value='en'),
            ],
        )

    async def callback(self, interaction: bisim.Interaction) -> None:
        await interaction.response.send_message(f'Language set to {self.values[0]}.', ephemeral=True)


view = ui.View()
view.add_item(LanguageSelect())
await ctx.send('Which language do you prefer?', view=view)
```

## Menus that Bisim fills

Pass `cls=` to the decorator, or create the class directly. The person picks from the server's members, roles or
channels, and `values` holds the objects they chose:

| Class | `values` |
| --- | --- |
| `ui.Select` | `List[str]` |
| `ui.UserSelect` | `List[Union[bisim.Member, bisim.User]]` |
| `ui.RoleSelect` | `List[bisim.Role]` |
| `ui.MentionableSelect` | members, users and roles together |
| `ui.ChannelSelect` | the chosen channels |

```python
class Setup(ui.View):
    @ui.select(cls=ui.ChannelSelect, channel_types=[bisim.ChannelType.text], placeholder='Where should I post?')
    async def channel(self, interaction: bisim.Interaction, select: ui.ChannelSelect) -> None:
        await interaction.response.send_message(f'I will post in {select.values[0].mention}.', ephemeral=True)

    @ui.select(cls=ui.RoleSelect, placeholder='Who may use me?', max_values=3)
    async def roles(self, interaction: bisim.Interaction, select: ui.RoleSelect) -> None:
        names = ', '.join(role.name for role in select.values)
        await interaction.response.send_message(f'Allowed roles: {names}.', ephemeral=True)
```

`channel_types` limits a channel menu to some kinds of channel: `ChannelType.text`, `ChannelType.voice` and
`ChannelType.category` are the ones Bisim has. In a direct message a channel menu has nothing to show.

!!! note
    Discord lets these menus start with some members, roles or channels already chosen (`default_values`). Bisim does
    not have that, so passing `default_values` raises `bisim.NotSupported`.

## Answering a choice

Choosing in a menu is an interaction, answered like a click: `edit_message`, `send_message`, `defer` or
`send_modal`, within three seconds. See [Views and buttons](buttons.md#answering-a-click). Persistent views work for
menus too: give the menu a fixed `custom_id` and the view `timeout=None`.

The select classes are in the [API reference](../../reference/ui.md).
