"""Buttons, a select menu and a modal with ``ui.View``, and a persistent view.

Run it with your bot's token::

    BISIM_TOKEN=... python examples/buttons.py

Then type ``!poll Pizza tonight?``, ``!confirm``, ``!language`` or ``!panel``
in a channel the bot can see. The panel keeps working after the bot restarts.
"""

import os
from typing import Optional, Set

import bisim
from bisim import ui


class QuickPoll(ui.View):
    """Yes and no buttons that count one vote per person and close after five minutes."""

    def __init__(self, question: str) -> None:
        super().__init__(timeout=300)
        self.question = question
        self.yes_voters: Set[int] = set()
        self.no_voters: Set[int] = set()
        self.message: Optional[bisim.Message] = None

    def render(self) -> None:
        self.vote_yes.label = f'Yes ({len(self.yes_voters)})'
        self.vote_no.label = f'No ({len(self.no_voters)})'

    async def vote(self, interaction: bisim.Interaction, chosen: Set[int], other: Set[int]) -> None:
        other.discard(interaction.user.id)
        chosen.add(interaction.user.id)
        self.render()
        await interaction.response.edit_message(view=self)

    @ui.button(label='Yes (0)', style=bisim.ButtonStyle.success)
    async def vote_yes(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await self.vote(interaction, self.yes_voters, self.no_voters)

    @ui.button(label='No (0)', style=bisim.ButtonStyle.danger)
    async def vote_no(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await self.vote(interaction, self.no_voters, self.yes_voters)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            await self.message.edit(content=f'{self.question} (closed)', view=self)


class Confirm(ui.View):
    """A yes or no question that only the person who asked can answer."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.accepted: Optional[bool] = None

    async def interaction_check(self, interaction: bisim.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message('Only the person who asked can answer.', ephemeral=True)
        return False

    @ui.button(label='Continue', style=bisim.ButtonStyle.primary)
    async def accept(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.accepted = True
        await interaction.response.edit_message(content='Going ahead.', view=None)
        self.stop()

    @ui.button(label='Stop', style=bisim.ButtonStyle.secondary)
    async def refuse(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        self.accepted = False
        await interaction.response.edit_message(content='Stopped.', view=None)
        self.stop()


GREETINGS = {'fa': 'سلام! زبان تو فارسی شد.', 'en': 'Hi! Your language is now English.'}


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
        await interaction.response.send_message(GREETINGS[self.values[0]], ephemeral=True)


class Feedback(ui.Modal, title='Send feedback'):
    topic = ui.TextInput(label='Topic', placeholder='What is it about?', max_length=50)
    details = ui.TextInput(label='Details', style=bisim.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: bisim.Interaction) -> None:
        print(f'Feedback from {interaction.user} ({interaction.user.id}): {self.topic.value}: {self.details.value}')
        await interaction.response.send_message('Thanks, we read every message.', ephemeral=True)


class Panel(ui.View):
    """A persistent view: no timeout, and every item has a fixed custom_id."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(ui.Button(label='Bisim docs', url='https://docs.bisim.gg'))

    @ui.button(label='Send feedback', style=bisim.ButtonStyle.primary, custom_id='example-panel:feedback')
    async def feedback(self, interaction: bisim.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(Feedback())

    @ui.select(cls=ui.RoleSelect, placeholder='Pick a role to see who has it', custom_id='example-panel:role')
    async def role(self, interaction: bisim.Interaction, select: ui.RoleSelect) -> None:
        role = select.values[0]
        await interaction.response.send_message(f'{role.mention} has {len(role.members)} members.', ephemeral=True)


class ExampleClient(bisim.Client):
    async def setup_hook(self) -> None:
        # Registering the persistent view makes clicks on panels sent before a restart work again.
        self.add_view(Panel())

    async def on_ready(self) -> None:
        print(f'Ready as {self.user} ({self.user.id})')

    async def on_message(self, message: bisim.Message) -> None:
        if message.author.bot:
            return
        if message.content.startswith('!poll '):
            question = message.content[len('!poll '):].strip()
            view = QuickPoll(question)
            view.message = await message.channel.send(question, view=view)
        elif message.content == '!confirm':
            view = Confirm(message.author.id)
            await message.reply('Shall I go ahead?', view=view)
            if await view.wait():
                await message.channel.send('No answer, nothing was done.')
        elif message.content == '!language':
            view = ui.View()
            view.add_item(LanguageSelect())
            await message.channel.send('Which language do you prefer?', view=view)
        elif message.content == '!panel':
            await message.channel.send('Need something?', view=Panel())


client = ExampleClient(intents=bisim.Intents.default())
client.run(os.environ['BISIM_TOKEN'])
