# Translating commands

Bisim shows commands in Persian and in English, each member in their own language. bisim.py translates them
the way discord.py does: a `Translator` gives the Persian and English text for every name, description and
choice, and `tree.sync()` sends those translations to Bisim with the commands.

## A translator

Subclass `app_commands.Translator` and implement `translate()`. It receives the text from your code as a
`locale_str`, the language Bisim wants (`bisim.Locale.persian` or `bisim.Locale.english`) and a context, and
returns the translation, or `None` when it has none:

```python
from typing import Optional

import bisim
from bisim import app_commands
from bisim.app_commands import locale_str

PERSIAN = {
    'weather': 'هوا',
    'Show the weather in a city': 'هوای یک شهر را نشان می‌دهد',
    'city': 'شهر',
    'The city to look up': 'نام شهر',
}


class PersianTranslator(app_commands.Translator):
    async def translate(
        self,
        string: locale_str,
        locale: bisim.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> Optional[str]:
        if locale is bisim.Locale.persian:
            return PERSIAN.get(string.message)
        return None  # the text in the code is already English


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Set the translator before syncing: sync() is when translations are collected.
        await self.tree.set_translator(PersianTranslator())
        await self.tree.sync()


client = MyClient()


@client.tree.command(description='Show the weather in a city')
@app_commands.describe(city='The city to look up')
async def weather(interaction: bisim.Interaction, city: str) -> None:
    await interaction.response.send_message(f'It is sunny in {city}.')
```

A member whose Bisim is in Persian now sees `/هوا` with the option `شهر`; everyone else sees `/weather`.
When `translate()` returns `None`, Bisim shows the text from your code.

Every name and description is translated, because commands turn their strings into `locale_str` by
themselves (`auto_locale_strings=True`, the default). Choice names are translated too.

## What Bisim accepts

- A translated command, group or option name: 1 to 32 letters, digits, `-` and `_`, Persian letters
  included, no spaces, and lower case where a letter has a case.
- A translated context menu name may have spaces and capitals, as the original.
- A translated description: 1 to 100 characters.

A translation Bisim refuses makes `sync()` fail with `app_commands.CommandSyncFailure`. An exception inside
`translate()` reaches you as `app_commands.TranslationError`.

## Keys and context

The English text works as a key in small bots. Larger ones give each string a key of its own through
`locale_str`'s extras, and look at the context:

```python
@client.tree.command(
    name=locale_str('ping', key='ping.name'),
    description=locale_str('Check that the bot is alive', key='ping.description'),
)
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Pong!')
```

In `translate()`, `string.extras.get('key')` is the key, `context.location` says what is being translated
(`TranslationContextLocation.command_name`, `parameter_description`, `choice_name` and so on) and
`context.data` is the command, parameter or choice itself.

Override `load()` to read translation files when the translator is set, and `unload()` to clean up when it
is replaced or the client closes.

## Translating your answers

`interaction.locale` is the member's language. `interaction.translate()` runs the tree's translator on any
text, in that language:

```python
@client.tree.command(description='Say hello')
async def hello(interaction: bisim.Interaction) -> None:
    text = await interaction.translate('Hello!')
    await interaction.response.send_message(text or 'Hello!')
```

It returns `None` when there is no translator or no translation, so keep a fallback. Choices from
[autocomplete](autocomplete.md) are translated into the member's language when they are sent.

`Translator`, `locale_str` and `TranslationContext` are described in the
[API reference](../../reference/app-commands.md).
