"""Views and modals: the components sent and the dispatch of clicks, selects and submits."""

from __future__ import annotations

import asyncio

import pytest

import bisim
from bisim import ui

from . import payloads as p
from .conftest import settle

CALLBACK = f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/callback'
BOT_MESSAGE_ID = '60000000000000950'


def bot_message(components: list, message_id: str = BOT_MESSAGE_ID) -> dict:
    return p.message(
        id=message_id,
        type='DEFAULT',
        content='panel',
        authorId=p.BOT_ID,
        author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True),
        referencedMessageId=None,
        referencedMessage=None,
        attachments=[],
        embeds=[],
        reactions=[],
        components=components,
    )


def click(custom_id: str, component_type: int = 2, message: dict = None, **data) -> dict:
    payload_data = {'customId': custom_id, 'componentType': component_type, **data}
    return p.interaction(3, payload_data, message=message or bot_message([]))


class Panel(ui.View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events = []

    @ui.button(label='Yes', style=bisim.ButtonStyle.success, custom_id='panel:yes', emoji='👍')
    async def yes(self, interaction: bisim.Interaction, button: ui.Button):
        self.events.append(('yes', interaction.user.id))
        button.disabled = True
        await interaction.response.edit_message(content='thanks', view=self)

    @ui.select(
        placeholder='Pick',
        custom_id='panel:pick',
        max_values=2,
        options=[bisim.SelectOption(label='A', value='a', description='first'), bisim.SelectOption(label='B', value='b', default=True)],
    )
    async def pick(self, interaction: bisim.Interaction, select: ui.Select):
        self.events.append(('pick', select.values))
        await interaction.response.defer()

    @ui.select(cls=ui.UserSelect, custom_id='panel:who', max_values=3)
    async def who(self, interaction: bisim.Interaction, select: ui.UserSelect):
        self.events.append(('who', select.values))
        await interaction.response.send_message('noted', ephemeral=True)

    @ui.select(cls=ui.ChannelSelect, custom_id='panel:where', channel_types=[bisim.ChannelType.text])
    async def where(self, interaction: bisim.Interaction, select: ui.ChannelSelect):
        self.events.append(('where', select.values))


def test_view_components_json():
    view = Panel(timeout=None)
    assert view.is_persistent()
    assert view.to_components() == [
        {'type': 1, 'components': [{'type': 2, 'style': 3, 'disabled': False, 'label': 'Yes', 'customId': 'panel:yes', 'emoji': {'name': '👍'}}]},
        {
            'type': 1,
            'components': [
                {
                    'type': 3,
                    'customId': 'panel:pick',
                    'minValues': 1,
                    'maxValues': 2,
                    'disabled': False,
                    'placeholder': 'Pick',
                    'options': [
                        {'label': 'A', 'value': 'a', 'default': False, 'description': 'first'},
                        {'label': 'B', 'value': 'b', 'default': True},
                    ],
                }
            ],
        },
        {'type': 1, 'components': [{'type': 5, 'customId': 'panel:who', 'minValues': 1, 'maxValues': 3, 'disabled': False}]},
        {'type': 1, 'components': [{'type': 8, 'customId': 'panel:where', 'minValues': 1, 'maxValues': 1, 'disabled': False, 'channelTypes': ['GUILD_TEXT']}]},
    ]


def test_link_buttons_and_row_limits():
    view = ui.View()
    view.add_item(ui.Button(label='Docs', url='https://docs.bisim.gg'))
    assert not view.is_dispatchable()
    assert view.to_components() == [{'type': 1, 'components': [{'type': 2, 'style': 5, 'disabled': False, 'label': 'Docs', 'url': 'https://docs.bisim.gg'}]}]
    full = ui.View()
    for i in range(25):
        full.add_item(ui.Button(label=str(i), custom_id=f'b{i}'))
    with pytest.raises(ValueError):
        full.add_item(ui.Button(label='one too many', custom_id='x'))


async def test_button_click_dispatches_to_the_view_on_its_message(bot_client, http):
    state = bot_client._connection
    channel = bot_client.get_channel(int(p.TEXT_ID))
    view = Panel()
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', bot_message(view.to_components()))
    sent = await channel.send('panel', view=view)
    assert state._view_store.is_message_tracked(sent.id)

    state._handle_interaction_payload(click('panel:yes', message=bot_message(view.to_components())))
    await settle()

    assert view.events == [('yes', int(p.MEMBER_ID))]
    body = http.last('POST', CALLBACK)['json']
    assert body['type'] == 7
    assert body['data']['content'] == 'thanks'
    assert body['data']['components'][0]['components'][0]['disabled'] is True

    # The same custom id on another message is not this view's.
    state._handle_interaction_payload(click('panel:yes', message=bot_message(view.to_components(), message_id='60000000000000951')))
    await settle()
    assert len(view.events) == 1


async def test_string_user_and_channel_selects(bot_client, http):
    state = bot_client._connection
    guild = bot_client.get_guild(int(p.GUILD_ID))
    view = Panel()
    state.store_view(view, int(BOT_MESSAGE_ID))
    message = bot_message(view.to_components())

    state._handle_interaction_payload(click('panel:pick', 3, message=message, values=['a', 'b']))
    await settle()
    assert view.events[-1] == ('pick', ['a', 'b'])
    assert http.last('POST', CALLBACK)['json'] == {'type': 6}

    resolved = {
        'users': {p.OWNER_ID: p.user_ref(p.OWNER_ID, 'owner'), '60000000000000077': p.user_ref('60000000000000077', 'visitor')},
        'members': {p.OWNER_ID: {'nickname': None, 'roleIds': [p.GUILD_ID], 'joinedAt': '2026-07-01T10:00:00.000Z', 'timeoutUntil': None}},
    }
    state._handle_interaction_payload(click('panel:who', 5, message=message, values=[p.OWNER_ID, '60000000000000077'], resolved=resolved))
    await settle()
    name, values = view.events[-1]
    assert name == 'who'
    assert values[0] is guild.get_member(int(p.OWNER_ID))
    assert isinstance(values[1], bisim.User) and values[1].name == 'visitor'
    assert http.last('POST', CALLBACK)['json'] == {'type': 4, 'data': {'content': 'noted', 'flags': 64}}

    channels = {p.TEXT_ID: {'id': p.TEXT_ID, 'name': 'chat', 'type': 'GUILD_TEXT', 'parentId': p.CATEGORY_ID, 'permissions': p.EVERYONE_PERMS}}
    state._handle_interaction_payload(click('panel:where', 8, message=message, values=[p.TEXT_ID], resolved={'channels': channels}))
    await settle()
    name, values = view.events[-1]
    assert name == 'where' and values[0].id == int(p.TEXT_ID)


async def test_component_type_is_found_from_the_message_when_missing(bot_client, http):
    state = bot_client._connection
    view = Panel()
    state.store_view(view, int(BOT_MESSAGE_ID))
    payload = click('panel:pick', 3, message=bot_message(view.to_components()), values=['a'])
    del payload['data']['componentType']
    state._handle_interaction_payload(payload)
    await settle()
    assert view.events == [('pick', ['a'])]


async def test_persistent_view_answers_after_a_restart(bot_client, http):
    state = bot_client._connection
    view = Panel(timeout=None)
    bot_client.add_view(view)
    assert view in bot_client.persistent_views

    # A message the library never saw in this run still reaches the view.
    state._handle_interaction_payload(click('panel:yes', message=bot_message(Panel(timeout=None).to_components(), message_id='60000000000000999')))
    await settle()
    assert view.events == [('yes', int(p.MEMBER_ID))]

    with pytest.raises(ValueError):
        bot_client.add_view(Panel())  # a timeout makes a view not persistent


async def test_interaction_check_and_on_error(bot_client, http):
    state = bot_client._connection
    errors = []

    class Guarded(ui.View):
        async def interaction_check(self, interaction):
            return interaction.user.id == int(p.OWNER_ID)

        @ui.button(label='Go', custom_id='go')
        async def go(self, interaction, button):
            raise AssertionError('blocked users never get here')

    class Fragile(ui.View):
        async def on_error(self, interaction, error, item):
            errors.append((type(error), item.custom_id))

        @ui.button(label='Break', custom_id='break')
        async def broken(self, interaction, button):
            raise RuntimeError('boom')

    state.store_view(Guarded())
    state.store_view(Fragile())
    state._handle_interaction_payload(click('go'))
    state._handle_interaction_payload(click('break'))
    await settle()
    assert errors == [(RuntimeError, 'break')]


async def test_view_timeout_and_stop(bot_client):
    timed_out = asyncio.Event()

    class Short(ui.View):
        async def on_timeout(self):
            timed_out.set()

        @ui.button(label='x', custom_id='short')
        async def x(self, interaction, button):
            self.stop()

    view = Short(timeout=0.05)
    bot_client._connection.store_view(view)
    assert await view.wait() is True
    await asyncio.wait_for(timed_out.wait(), 1)
    assert view.is_finished()

    stopped = Short(timeout=10)
    bot_client._connection.store_view(stopped)
    bot_client._connection._handle_interaction_payload(click('short'))
    assert await asyncio.wait_for(stopped.wait(), 1) is False


class Feedback(ui.Modal, title='Feedback'):
    name = ui.TextInput(label='Name', placeholder='Your name', max_length=32, custom_id='fb:name')
    body = ui.TextInput(label='Message', style=bisim.TextStyle.paragraph, required=False, default='hi', custom_id='fb:body')

    def __init__(self):
        super().__init__(custom_id='fb')
        self.submitted = asyncio.get_event_loop().create_future()

    async def on_submit(self, interaction: bisim.Interaction):
        self.submitted.set_result((self.name.value, self.body.value))
        await interaction.response.send_message(f'thanks {self.name.value}', ephemeral=True)


async def test_modal_open_and_submit(bot_client, http):
    state = bot_client._connection
    tree = bisim.app_commands.CommandTree(bot_client)
    modal = Feedback()

    @tree.command(description='Send feedback')
    async def feedback(interaction: bisim.Interaction):
        await interaction.response.send_modal(modal)

    state._handle_interaction_payload(p.interaction(2, {'id': '1', 'name': 'feedback', 'type': 1, 'options': []}))
    await settle()
    assert http.last('POST', CALLBACK)['json'] == {
        'type': 9,
        'data': {
            'customId': 'fb',
            'title': 'Feedback',
            'components': [
                {'type': 1, 'components': [{'type': 4, 'style': 1, 'label': 'Name', 'customId': 'fb:name', 'required': True, 'placeholder': 'Your name', 'maxLength': 32}]},
                {'type': 1, 'components': [{'type': 4, 'style': 2, 'label': 'Message', 'customId': 'fb:body', 'required': False, 'value': 'hi'}]},
            ],
        },
    }

    submit = p.interaction(5, {'customId': 'fb', 'fields': [{'customId': 'fb:name', 'value': 'Sara'}, {'customId': 'fb:body', 'value': 'love it'}]})
    state._handle_interaction_payload(submit)
    assert await asyncio.wait_for(modal.submitted, 1) == ('Sara', 'love it')
    await settle()
    assert http.last('POST', CALLBACK)['json'] == {'type': 4, 'data': {'content': 'thanks Sara', 'flags': 64}}
    assert modal.is_finished()


async def test_view_from_message_rebuilds_items(bot_client, state=None):
    channel = bot_client.get_channel(int(p.TEXT_ID))
    message = bisim.Message(state=bot_client._connection, channel=channel, data=bot_message(Panel().to_components()))
    view = ui.View.from_message(message)
    kinds = [type(item).__name__ for item in view.children]
    assert kinds == ['Button', 'Select', 'UserSelect', 'ChannelSelect']
    assert view.children[0].custom_id == 'panel:yes'
    assert view.children[1].options[1].default is True
