"""Application commands: the JSON sent to Bisim and running them from interaction payloads."""

from __future__ import annotations

from typing import List, Literal, Optional

import pytest

import bisim
from bisim import app_commands

from . import payloads as p
from .conftest import settle

CALLBACK = f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/callback'


@pytest.fixture
def tree(bot_client):
    return app_commands.CommandTree(bot_client)


def command_data(name: str, options: list, **extra) -> dict:
    data = {'id': '60000000000000800', 'name': name, 'type': 1, 'options': options}
    data.update(extra)
    return data


def test_slash_command_json(tree):
    @tree.command(description='Say something')
    @app_commands.describe(text='What to say', times='How many times')
    @app_commands.rename(text='message')
    async def say(
        interaction: bisim.Interaction,
        text: str,
        times: app_commands.Range[int, 1, 5] = 1,
        target: Optional[bisim.Member] = None,
    ):
        pass

    assert say.to_dict(tree) == {
        'name': 'say',
        'description': 'Say something',
        'type': 1,
        'defaultMemberPermissions': None,
        'options': [
            {'type': 'STRING', 'name': 'message', 'description': 'What to say', 'required': True},
            {'type': 'INTEGER', 'name': 'times', 'description': 'How many times', 'required': False, 'minValue': 1, 'maxValue': 5},
            {'type': 'USER', 'name': 'target', 'description': '…', 'required': False},
        ],
    }


def test_option_kinds_and_choices(tree):
    @tree.command(description='Options of every kind')
    async def kinds(
        interaction: bisim.Interaction,
        colour: Literal['red', 'green'],
        role: bisim.Role,
        where: bisim.TextChannel,
        ratio: app_commands.Range[float, 0.5, 2.5],
        flag: bool,
        name: app_commands.Range[str, 2, 10],
        thing: Optional[bisim.Attachment] = None,
        anyone: Optional[app_commands.Transform[bisim.abc.Snowflake, app_commands.Transformer]] = None,
    ):
        pass

    options = {o['name']: o for o in kinds.to_dict(tree)['options']}
    assert options['colour']['choices'] == [{'name': 'red', 'value': 'red'}, {'name': 'green', 'value': 'green'}]
    assert options['role']['type'] == 'ROLE'
    assert options['where'] == {'type': 'CHANNEL', 'name': 'where', 'description': '…', 'required': True, 'channelTypes': ['GUILD_TEXT']}
    assert options['ratio'] == {'type': 'NUMBER', 'name': 'ratio', 'description': '…', 'required': True, 'minValue': 0.5, 'maxValue': 2.5}
    assert options['flag']['type'] == 'BOOLEAN'
    assert options['name'] == {'type': 'STRING', 'name': 'name', 'description': '…', 'required': True, 'minLength': 2, 'maxLength': 10}
    assert options['thing'] == {'type': 'ATTACHMENT', 'name': 'thing', 'description': '…', 'required': False}


def test_groups_permissions_contexts_and_context_menus(tree):
    group = app_commands.Group(name='tag', description='Tags')
    admin = app_commands.Group(name='admin', description='Admin tags', parent=group)

    @group.command(description='Show a tag')
    async def show(interaction: bisim.Interaction, name: str):
        pass

    @admin.command(description='Delete a tag')
    async def delete(interaction: bisim.Interaction, name: str):
        pass

    tree.add_command(group)

    @tree.command(description='Find a fruit')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def fruit(interaction: bisim.Interaction, name: str):
        pass

    @fruit.autocomplete('name')
    async def fruit_names(interaction, current):
        return []

    @tree.context_menu(name='Report message')
    async def report(interaction: bisim.Interaction, message: bisim.Message):
        pass

    @tree.context_menu(name='User info')
    async def info(interaction: bisim.Interaction, member: bisim.Member):
        pass

    assert group.to_dict(tree) == {
        'name': 'tag',
        'description': 'Tags',
        'type': 1,
        'defaultMemberPermissions': None,
        'options': [
            {
                'type': 'SUB_COMMAND_GROUP',
                'name': 'admin',
                'description': 'Admin tags',
                'options': [
                    {
                        'type': 'SUB_COMMAND',
                        'name': 'delete',
                        'description': 'Delete a tag',
                        'options': [{'type': 'STRING', 'name': 'name', 'description': '…', 'required': True}],
                    }
                ],
            },
            {
                'type': 'SUB_COMMAND',
                'name': 'show',
                'description': 'Show a tag',
                'options': [{'type': 'STRING', 'name': 'name', 'description': '…', 'required': True}],
            },
        ],
    }
    fruit_json = fruit.to_dict(tree)
    assert fruit_json['defaultMemberPermissions'] == str(1 << 13)
    assert fruit_json['contexts'] == ['GUILD']
    assert fruit_json['options'][0]['autocomplete'] is True
    assert report.to_dict(tree) == {'name': 'Report message', 'type': 3, 'defaultMemberPermissions': None}
    assert info.to_dict(tree) == {'name': 'User info', 'type': 2, 'defaultMemberPermissions': None}


async def test_translator_adds_localizations(tree):
    @tree.command(name='hello', description='Say hello')
    @app_commands.describe(who='Who to greet')
    async def hello(interaction: bisim.Interaction, who: str):
        pass

    class Persian(app_commands.Translator):
        async def translate(self, string, locale, context):
            if locale is bisim.Locale.persian:
                return {'hello': 'salam', 'Say hello': 'سلام کن', 'Who to greet': 'به چه کسی'}.get(string.message)
            return None

    await tree.set_translator(Persian())
    payload = await hello.get_translated_payload(tree, tree.translator)
    assert payload['nameLocalizations'] == {'fa': 'salam'}
    assert payload['descriptionLocalizations'] == {'fa': 'سلام کن'}
    assert payload['options'][0]['descriptionLocalizations'] == {'fa': 'به چه کسی'}


async def test_sync_replaces_the_whole_set(tree, http, guild_id=int(p.GUILD_ID)):
    @tree.command(description='Ping')
    async def ping(interaction: bisim.Interaction):
        pass

    @tree.command(description='Only here')
    @app_commands.guilds(guild_id)
    async def local(interaction: bisim.Interaction):
        pass

    http.respond('PUT', f'/applications/{p.BOT_ID}/commands', lambda route, kw: [
        {'id': '60000000000000801', 'applicationId': p.BOT_ID, 'guildId': None, 'name': 'ping', 'description': 'Ping', 'type': 1, 'options': [], 'defaultMemberPermissions': None, 'contexts': [], 'createdAt': '2026-11-01T00:00:00Z'}
    ])
    synced = await tree.sync()
    body = http.last('PUT', f'/applications/{p.BOT_ID}/commands')['json']
    assert [c['name'] for c in body['commands']] == ['ping']
    assert synced[0].id == 60000000000000801 and synced[0].name == 'ping'
    assert synced[0].mention == '</ping:60000000000000801>'

    http.respond('PUT', f'/applications/{p.BOT_ID}/guilds/{p.GUILD_ID}/commands', {'commands': []})
    await tree.sync(guild=bisim.Object(guild_id))
    body = http.last('PUT', f'/applications/{p.BOT_ID}/guilds/{p.GUILD_ID}/commands')['json']
    assert [c['name'] for c in body['commands']] == ['local']


async def test_slash_command_runs_from_the_gateway(bot_client, tree, http):
    state = bot_client._connection
    guild = bot_client.get_guild(int(p.GUILD_ID))
    seen = {}

    @tree.command(description='Say something')
    async def say(
        interaction: bisim.Interaction,
        text: str,
        times: int,
        target: bisim.Member,
        role: bisim.Role,
        where: bisim.TextChannel,
        stranger: Optional[bisim.User] = None,
        loud: bool = False,
    ):
        seen.update(text=text, times=times, target=target, role=role, where=where, stranger=stranger, loud=loud)
        seen['user'] = interaction.user
        seen['command'] = interaction.command
        await interaction.response.send_message(text * times, ephemeral=True)

    completions = []
    bot_client.event(_capture(completions, 'on_app_command_completion'))

    payload = p.interaction(
        2,
        command_data(
            'say',
            [
                {'name': 'text', 'type': 'STRING', 'value': 'hi'},
                {'name': 'times', 'type': 'INTEGER', 'value': 2},
                {'name': 'target', 'type': 'USER', 'value': p.OWNER_ID},
                {'name': 'role', 'type': 'ROLE', 'value': p.MOD_ROLE_ID},
                {'name': 'where', 'type': 'CHANNEL', 'value': p.TEXT_ID},
                {'name': 'stranger', 'type': 'USER', 'value': '60000000000000077'},
            ],
            resolved={
                'users': {
                    p.OWNER_ID: p.user_ref(p.OWNER_ID, 'owner', 'The Owner'),
                    '60000000000000077': p.user_ref('60000000000000077', 'visitor'),
                },
                'members': {p.OWNER_ID: {'nickname': None, 'roleIds': [p.GUILD_ID], 'joinedAt': '2026-07-01T10:00:00.000Z', 'timeoutUntil': None}},
                'roles': {p.MOD_ROLE_ID: {'id': p.MOD_ROLE_ID, 'name': 'Moderators', 'color': 0, 'position': 2, 'permissions': p.MOD_PERMS, 'hoist': True, 'mentionable': False}},
                'channels': {p.TEXT_ID: {'id': p.TEXT_ID, 'name': 'chat', 'type': 'GUILD_TEXT', 'parentId': p.CATEGORY_ID, 'permissions': p.EVERYONE_PERMS}},
            },
        ),
    )
    state.parse_interaction_create(p.interaction_event(payload))
    await settle()

    assert seen['text'] == 'hi' and seen['times'] == 2 and seen['loud'] is False
    assert seen['target'] is guild.get_member(int(p.OWNER_ID))
    assert seen['role'] is guild.get_role(int(p.MOD_ROLE_ID))
    assert seen['where'] is guild.get_channel(int(p.TEXT_ID))
    assert isinstance(seen['stranger'], bisim.User) and seen['stranger'].name == 'visitor'
    assert seen['user'] is guild.get_member(int(p.MEMBER_ID))
    assert seen['command'] is say
    assert http.last('POST', CALLBACK)['json'] == {'type': 4, 'data': {'content': 'hihi', 'flags': 64}}
    assert http.last('POST', CALLBACK)['auth'] is False
    assert completions and completions[0][1] is say


def _capture(store: List, name: str):
    async def handler(*args):
        store.append(args)

    handler.__name__ = name
    return handler


async def test_subcommand_with_defer_and_followup(bot_client, tree, http):
    state = bot_client._connection
    group = app_commands.Group(name='tag', description='Tags')
    admin = app_commands.Group(name='admin', description='Admin tags', parent=group)
    calls = []

    @admin.command(description='Delete a tag')
    async def delete(interaction: bisim.Interaction, name: str):
        calls.append(name)
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(f'deleted {name}')
        await interaction.edit_original_response(content='done')

    tree.add_command(group)
    http.respond('POST', f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/followup', p.message(id='60000000000000901', type='DEFAULT', referencedMessageId=None, referencedMessage=None, author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True)))
    http.respond('PATCH', f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/messages/@original', p.message(id='60000000000000902', type='DEFAULT', referencedMessageId=None, referencedMessage=None, author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True)))

    options = [{'name': 'admin', 'type': 'SUB_COMMAND_GROUP', 'options': [{'name': 'delete', 'type': 'SUB_COMMAND', 'options': [{'name': 'name', 'type': 'STRING', 'value': 'old'}]}]}]
    state._handle_interaction_payload(p.interaction(2, command_data('tag', options)))
    await settle()

    assert calls == ['old']
    assert http.last('POST', CALLBACK)['json'] == {'type': 5}
    assert http.last('POST', f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/followup')['json'] == {'content': 'deleted old'}
    assert http.last('PATCH', f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/messages/@original')['json'] == {'content': 'done'}


async def test_autocomplete_answers_with_choices(bot_client, tree, http):
    state = bot_client._connection

    @tree.command(description='Find a fruit')
    async def fruit(interaction: bisim.Interaction, kind: str, name: str):
        pass

    seen = {}

    @fruit.autocomplete('name')
    async def fruit_names(interaction: bisim.Interaction, current: str):
        seen['kind'] = interaction.namespace.kind
        return [app_commands.Choice(name=f, value=f) for f in ('apple', 'banana', 'grape') if current in f]

    options = [{'name': 'kind', 'type': 'STRING', 'value': 'sweet'}, {'name': 'name', 'type': 'STRING', 'value': 'ap', 'focused': True}]
    state._handle_interaction_payload(p.interaction(4, command_data('fruit', options)))
    await settle()

    assert seen['kind'] == 'sweet'
    assert http.last('POST', CALLBACK)['json'] == {'type': 8, 'data': {'choices': [{'name': 'apple', 'value': 'apple'}, {'name': 'grape', 'value': 'grape'}]}}


async def test_context_menus_receive_their_target(bot_client, tree, http):
    state = bot_client._connection
    guild = bot_client.get_guild(int(p.GUILD_ID))
    got = {}

    @tree.context_menu(name='Report message')
    async def report(interaction: bisim.Interaction, message: bisim.Message):
        got['message'] = message

    @tree.context_menu(name='User info')
    async def info(interaction: bisim.Interaction, member: bisim.Member):
        got['member'] = member

    message_data = p.message(id='60000000000000333', referencedMessageId=None, referencedMessage=None)
    state._handle_interaction_payload(
        p.interaction(2, {'id': '1', 'name': 'Report message', 'type': 3, 'targetId': '60000000000000333', 'resolved': {'messages': {'60000000000000333': message_data}}})
    )
    state._handle_interaction_payload(
        p.interaction(2, {'id': '2', 'name': 'User info', 'type': 2, 'targetId': p.OWNER_ID, 'resolved': {'users': {p.OWNER_ID: p.user_ref(p.OWNER_ID, 'owner')}, 'members': {p.OWNER_ID: {'roleIds': [p.GUILD_ID]}}}})
    )
    await settle()

    assert isinstance(got['message'], bisim.Message) and got['message'].id == 60000000000000333
    assert got['message'].author.id == int(p.MEMBER_ID)
    assert got['member'] is guild.get_member(int(p.OWNER_ID))


async def test_checks_and_error_handlers(bot_client, tree, http):
    state = bot_client._connection
    errors = []

    @tree.command(description='Ban someone')
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(interaction: bisim.Interaction, member: bisim.Member):
        raise AssertionError('should not run')

    @tree.command(description='Kick someone')
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def kick(interaction: bisim.Interaction):
        await interaction.response.send_message('kicked')

    @tree.command(description='Breaks')
    async def broken(interaction: bisim.Interaction):
        raise RuntimeError('boom')

    @tree.error
    async def on_error(interaction: bisim.Interaction, error: app_commands.AppCommandError):
        errors.append(error)

    state._handle_interaction_payload(p.interaction(2, command_data('ban', [{'name': 'member', 'type': 'USER', 'value': p.OWNER_ID}])))
    await settle()
    assert isinstance(errors[0], app_commands.MissingPermissions)
    assert errors[0].missing_permissions == ['ban_members']

    state._handle_interaction_payload(p.interaction(2, command_data('kick', [])))
    await settle()
    assert len(errors) == 1
    assert http.last('POST', CALLBACK)['json']['data']['content'] == 'kicked'

    state._handle_interaction_payload(p.interaction(2, command_data('broken', [])))
    await settle()
    assert isinstance(errors[1], app_commands.CommandInvokeError)
    assert isinstance(errors[1].original, RuntimeError)


async def test_unknown_command_and_dm_interaction(bot_client, tree, http):
    state = bot_client._connection
    errors = []

    @tree.error
    async def on_error(interaction, error):
        errors.append(error)

    seen = {}

    @tree.command(description='Works in DMs')
    async def hello(interaction: bisim.Interaction):
        seen['user'] = interaction.user
        seen['guild'] = interaction.guild
        seen['channel'] = interaction.channel
        await interaction.response.send_message('hello')

    state._handle_interaction_payload(p.interaction(2, command_data('hello', []), guild=False))
    state._handle_interaction_payload(p.interaction(2, command_data('missing', [])))
    await settle()

    assert isinstance(seen['user'], bisim.User) and seen['user'].id == int(p.MEMBER_ID)
    assert seen['guild'] is None
    assert isinstance(seen['channel'], bisim.DMChannel) and seen['channel'].id == int(p.DM_ID)
    assert isinstance(errors[0], app_commands.CommandNotFound)


async def test_cog_style_group(bot_client, tree, http):
    state = bot_client._connection
    hits = []

    class Fun(app_commands.Group, name='fun', description='Fun things'):
        @app_commands.command(description='Roll a die')
        async def roll(self, interaction: bisim.Interaction, sides: int = 6):
            hits.append((self, sides))
            await interaction.response.send_message(str(sides))

    fun = Fun()
    tree.add_command(fun)
    state._handle_interaction_payload(p.interaction(2, command_data('fun', [{'name': 'roll', 'type': 'SUB_COMMAND', 'options': [{'name': 'sides', 'type': 'INTEGER', 'value': '20'}]}])))
    await settle()
    assert hits == [(fun, 20)]
    assert http.last('POST', CALLBACK)['json'] == {'type': 4, 'data': {'content': '20'}}


async def test_cooldown_key_matches_discord_py():
    """No key: one cooldown per user. key=None: one cooldown for everyone (discord.py's rule)."""
    import datetime
    from types import SimpleNamespace

    from bisim.app_commands import CommandOnCooldown, checks

    def interaction(user_id):
        return SimpleNamespace(user=SimpleNamespace(id=user_id), created_at=datetime.datetime.now(datetime.timezone.utc))

    async def run(predicate, user_id):
        try:
            return await predicate(interaction(user_id))
        except CommandOnCooldown:
            return 'cooldown'

    async def per_user():
        pass

    async def everyone():
        pass

    checks.cooldown(1, 60)(per_user)
    checks.cooldown(1, 60, key=None)(everyone)
    per_user_check = per_user.__bisim_app_commands_checks__[0]
    everyone_check = everyone.__bisim_app_commands_checks__[0]

    assert await run(per_user_check, 1) is True
    assert await run(per_user_check, 2) is True
    assert await run(per_user_check, 1) == 'cooldown'

    assert await run(everyone_check, 1) is True
    assert await run(everyone_check, 2) == 'cooldown'
