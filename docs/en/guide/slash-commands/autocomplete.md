# Autocomplete

Autocomplete shows suggestions while the member types an option, worked out by your bot on the spot. Use it
when the possible values are too many for [fixed choices](options.md#fixed-choices) or change over time: tag
names, cities, items in a database.

## Adding it to an option

Write an `async` function that takes the interaction and the text typed so far, and returns a list of
`app_commands.Choice`. Attach it with the command's `autocomplete()` decorator:

```python
from typing import List

from bisim import app_commands

FRUITS = ['Apple', 'Banana', 'Cherry', 'Melon', 'Pineapple', 'Watermelon']


@client.tree.command(description='Tell the bot your favourite fruit')
async def fruit(interaction: bisim.Interaction, name: str) -> None:
    await interaction.response.send_message(f'Your favourite fruit seems to be {name}.')


@fruit.autocomplete('name')
async def fruit_autocomplete(interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=item, value=item)
        for item in FRUITS
        if current.lower() in item.lower()
    ][:25]
```

`current` is what the member has typed in that option so far, and an empty string before they type anything.
Bisim shows at most **25** suggestions, so cut the list down.

The decorator form `@app_commands.autocomplete(name=fruit_autocomplete)` does the same and is handy when the
autocomplete function is defined before the command.

Autocomplete works on `str`, `int` and `float` options that have no fixed choices. Putting it on another
option type, or on a parameter annotated with `Choice`, raises `TypeError` when the command is defined.

## Using the other options

`interaction.namespace` holds the options the member has already filled in, by their names on Bisim. An
option that has not been filled in yet is `None`:

```python
CITIES = {'iran': ['Tehran', 'Isfahan', 'Shiraz', 'Tabriz'], 'turkey': ['Istanbul', 'Ankara', 'Izmir']}


@client.tree.command(description='Pick a city')
@app_commands.choices(country=[
    app_commands.Choice(name='Iran', value='iran'),
    app_commands.Choice(name='Turkey', value='turkey'),
])
async def city(interaction: bisim.Interaction, country: str, city: str) -> None:
    await interaction.response.send_message(f'{city}, {country}')


@city.autocomplete('city')
async def city_autocomplete(interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
    names = CITIES.get(interaction.namespace.country or '', [])
    return [app_commands.Choice(name=n, value=n) for n in names if n.lower().startswith(current.lower())]
```

In an autocomplete interaction the namespace is what the member typed so far and is not checked yet. A user,
role or channel there may be only a `bisim.Object` with an id.

## Inside a group

In an [`app_commands.Group`](groups.md) the autocomplete function is a method and takes `self` first:

```python
class Notes(app_commands.Group, name='note', description='Save short notes'):
    def __init__(self) -> None:
        super().__init__()
        self.notes: Dict[str, str] = {}

    @app_commands.command(description='Show a note')
    async def show(self, interaction: bisim.Interaction, name: str) -> None:
        await interaction.response.send_message(self.notes.get(name, 'There is no such note.'))

    @show.autocomplete('name')
    async def note_names(self, interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
        matches = [n for n in sorted(self.notes) if current.lower() in n]
        return [app_commands.Choice(name=n, value=n) for n in matches[:25]]
```

## Good to know

- Suggestions are only suggestions: the member can still send any value. Check the value in the command.
- The answer must come within three seconds, so keep the function fast. If it raises, the error is logged
  and the member sees no suggestions; command error handlers are not called.
- Checks on the command are not run for autocomplete. Add `@app_commands.check(...)` to the autocomplete
  function itself; when one fails, the member gets an empty list.
- A [transformer](options.md#transformers) can provide autocomplete for every option that uses it by
  implementing `autocomplete()`.
- With a [translator](translations.md) set, each suggestion's name is translated to the member's language.
