"""Slash commands and context menu commands with ``app_commands``.

Run it with your bot's token::

    BISIM_TOKEN=... python examples/slash_commands.py

Commands synced globally can take a moment to show up. Set ``BISIM_GUILD_ID``
to a server's id to sync there instead, which is immediate.
"""

import os
from typing import Dict, List, Optional

import bisim
from bisim import app_commands

GUILD_ID = os.environ.get('BISIM_GUILD_ID')
TEST_GUILD = bisim.Object(id=int(GUILD_ID)) if GUILD_ID else None


class ExampleClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Runs once, after logging in and before connecting to the gateway.
        if TEST_GUILD is not None:
            self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)


client = ExampleClient()


@client.event
async def on_ready() -> None:
    print(f'Logged in as {client.user} (ID: {client.user.id}) in {len(client.guilds)} servers')


@client.tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


@client.tree.command(description='Add two numbers')
@app_commands.describe(first='The first number', second='The second number, up to 1000')
async def add(interaction: bisim.Interaction, first: int, second: app_commands.Range[int, 0, 1000]) -> None:
    await interaction.response.send_message(f'{first} + {second} = {first + second}')


@client.tree.command(description='Show a member')
@app_commands.describe(member='Who to show; you when left empty')
@app_commands.guild_only()
async def whois(interaction: bisim.Interaction, member: Optional[bisim.Member] = None) -> None:
    member = member or interaction.user  # type: ignore[assignment]
    embed = bisim.Embed(title=member.display_name, colour=member.colour)
    embed.add_field(name='Username', value=f'@{member.name}')
    if member.joined_at is not None:
        embed.add_field(name='Joined', value=member.joined_at.strftime('%Y-%m-%d'))
    roles = [role.mention for role in member.roles if not role.is_default()]
    embed.add_field(name='Roles', value=' '.join(roles) or 'None', inline=False)
    embed.set_footer(text=f'ID: {member.id}')
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(description='Delete recent messages in this channel')
@app_commands.describe(count='How many messages, 1 to 100')
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.guild_only()
async def purge(interaction: bisim.Interaction, count: app_commands.Range[int, 1, 100]) -> None:
    # Deleting can take a moment: show "thinking" first, answer with a followup.
    await interaction.response.defer(ephemeral=True, thinking=True)
    deleted = await interaction.channel.purge(limit=count)  # type: ignore[union-attr]
    await interaction.followup.send(f'Deleted {len(deleted)} messages.', ephemeral=True)


class Notes(app_commands.Group, name='note', description='Save short notes and show them later'):
    def __init__(self) -> None:
        super().__init__()
        self.notes: Dict[str, str] = {}

    @app_commands.command(description='Save a note')
    async def save(self, interaction: bisim.Interaction, name: app_commands.Range[str, 1, 32], text: str) -> None:
        self.notes[name.lower()] = text
        await interaction.response.send_message(f'Saved **{name}**.', ephemeral=True)

    @app_commands.command(description='Show a note')
    async def show(self, interaction: bisim.Interaction, name: str) -> None:
        text = self.notes.get(name.lower())
        if text is None:
            await interaction.response.send_message('There is no note with that name.', ephemeral=True)
        else:
            await interaction.response.send_message(text)

    @show.autocomplete('name')
    async def note_names(self, interaction: bisim.Interaction, current: str) -> List[app_commands.Choice[str]]:
        matches = [name for name in sorted(self.notes) if current.lower() in name]
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]


client.tree.add_command(Notes())


@client.tree.context_menu(name='Quote message')
async def quote(interaction: bisim.Interaction, message: bisim.Message) -> None:
    embed = bisim.Embed(description=message.content or '(no text)', timestamp=message.created_at)
    embed.set_author(name=message.author.display_name)
    await interaction.response.send_message(embed=embed)


@client.tree.context_menu(name='Account age')
async def account_age(interaction: bisim.Interaction, user: bisim.User) -> None:
    created = user.created_at.strftime('%Y-%m-%d')
    await interaction.response.send_message(f'{user.display_name} joined Bisim on {created}.', ephemeral=True)


@client.tree.error
async def on_app_command_error(interaction: bisim.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        text = 'You need the Manage Messages permission for this.'
    else:
        text = 'Something went wrong.'
        print(f'Error in /{interaction.command.qualified_name if interaction.command else "?"}: {error!r}')
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


client.run(os.environ['BISIM_TOKEN'])
