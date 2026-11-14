"""ext.commands: parsing, converters, checks, cooldowns, groups, cogs and help."""

from __future__ import annotations

import itertools
from typing import List, Literal, Optional, Union

import pytest

import bisim
from bisim.ext import commands
from bisim.ext.commands.view import StringView

from . import payloads as p
from .conftest import finish_tasks, make_client, settle

_ids = itertools.count(60000000000001000)


DISPLAY_NAMES = {p.MEMBER_ID: 'Sara K', p.OWNER_ID: 'The Owner'}


def user_message(content: str, author_id: str = p.MEMBER_ID, username: str = 'sara', bot: bool = False) -> dict:
    return p.message(
        id=str(next(_ids)),
        type='DEFAULT',
        content=content,
        authorId=author_id,
        author=p.user_ref(author_id, username, DISPLAY_NAMES.get(author_id), bot=bot),
        referencedMessageId=None,
        referencedMessage=None,
        attachments=[],
        embeds=[],
        reactions=[],
        components=[],
    )


@pytest.fixture
async def bot(http):
    client = await make_client(commands.Bot, http, command_prefix='!', owner_id=int(p.OWNER_ID))
    sent: List[dict] = []

    def on_send(route, kwargs):
        body = kwargs['json']
        sent.append(body)
        return p.message(
            id=str(next(_ids)),
            type='DEFAULT',
            content=body.get('content', ''),
            authorId=p.BOT_ID,
            author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True),
            referencedMessageId=body.get('referencedMessageId'),
            referencedMessage=None,
            attachments=[],
            embeds=body.get('embeds', []),
            reactions=[],
            components=[],
        )

    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', on_send)
    http.respond('GET', f'/guilds/{p.GUILD_ID}/channels/{p.TEXT_ID}/overwrites', [])
    client.sent = sent
    client.errors = []

    @client.event
    async def on_command_error(ctx, error):
        client.errors.append(error)

    yield client
    await finish_tasks()


async def run(client, content: str, **author) -> None:
    client._connection.parse_message_create({'type': 'MESSAGE_CREATE', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'message': user_message(content, **author)})
    await settle()


def replies(bot) -> List[str]:
    return [body.get('content') for body in bot.sent]


# ----------------------------------------------------------------------
# StringView
# ----------------------------------------------------------------------


def test_string_view_words_and_quotes():
    view = StringView('hello "big world"   «سلام دنیا» end\\ here')
    assert view.get_quoted_word() == 'hello'
    view.skip_ws()
    assert view.get_quoted_word() == 'big world'
    view.skip_ws()
    assert view.get_quoted_word() == 'سلام دنیا'
    view.skip_ws()
    assert view.get_quoted_word() == 'end\\'
    view.skip_ws()
    assert view.read_rest() == 'here'
    assert view.eof


@pytest.mark.parametrize(
    'text, error',
    [
        ('"never closed', commands.ExpectedClosingQuoteError),
        ('"closed"too', commands.InvalidEndOfQuotedStringError),
        ('mid"quote', commands.UnexpectedQuoteError),
    ],
)
def test_string_view_quote_errors(text, error):
    view = StringView(text)
    with pytest.raises(error):
        view.get_quoted_word()


# ----------------------------------------------------------------------
# Running commands from messages
# ----------------------------------------------------------------------


async def test_basic_arguments_and_rest(bot):
    @bot.command()
    async def add(ctx, a: int, b: int):
        await ctx.send(str(a + b))

    @bot.command(aliases=['say'])
    async def echo(ctx, *, text: str):
        await ctx.reply(text)

    await run(bot, '!add 2 3')
    await run(bot, '!say  hello "there" world ')
    await run(bot, 'add 1 1')  # no prefix
    await run(bot, '!add 1 1', author_id='60000000000000099', username='other_bot', bot=True)  # bots are ignored
    assert replies(bot) == ['5', 'hello "there" world']
    assert bot.sent[1]['referencedMessageId']


async def test_member_role_channel_and_user_converters(bot):
    guild = bot.get_guild(int(p.GUILD_ID))
    got = []

    @bot.command()
    async def whois(ctx, member: bisim.Member):
        got.append(member)

    @bot.command()
    async def info(ctx, role: bisim.Role, channel: bisim.TextChannel, user: bisim.User):
        got.append((role, channel, user))

    sara = guild.get_member(int(p.MEMBER_ID))
    for text in (f'!whois <@{p.MEMBER_ID}>', '!whois sara', '!whois Sara', f'!whois {p.MEMBER_ID}', '!whois "Sara K"'):
        await run(bot, text)
    assert got == [sara] * 5

    got.clear()
    await run(bot, f'!info Moderators <#{p.TEXT_ID}> <@{p.OWNER_ID}>')
    role, channel, user = got[0]
    assert role is guild.get_role(int(p.MOD_ROLE_ID))
    assert channel is guild.get_channel(int(p.TEXT_ID))
    assert user.id == int(p.OWNER_ID)

    await run(bot, '!whois nobody')
    assert isinstance(bot.errors[-1], commands.MemberNotFound)
    assert bot.errors[-1].argument == 'nobody'


async def test_optional_greedy_literal_range_union_bool(bot):
    got = []

    @bot.command()
    async def numbers(ctx, values: commands.Greedy[int], label: str = 'none'):
        got.append((values, label))

    @bot.command()
    async def maybe(ctx, count: Optional[int] = 1, *, rest: str = ''):
        got.append((count, rest))

    @bot.command()
    async def mode(ctx, kind: Literal['fast', 'slow'], level: commands.Range[int, 1, 3], on: bool):
        got.append((kind, level, on))

    @bot.command()
    async def either(ctx, value: Union[int, bisim.Member]):
        got.append(value)

    await run(bot, '!numbers 1 2 3 tail')
    await run(bot, '!maybe words only')
    await run(bot, '!maybe 4 more words')
    await run(bot, '!mode slow 2 yes')
    await run(bot, '!either 7')
    await run(bot, '!either sara')
    assert got[:5] == [([1, 2, 3], 'tail'), (1, 'words only'), (4, 'more words'), ('slow', 2, True), 7]
    assert got[5].id == int(p.MEMBER_ID)

    await run(bot, '!mode medium 2 yes')
    assert isinstance(bot.errors[-1], commands.BadLiteralArgument)
    await run(bot, '!mode fast 9 yes')
    assert isinstance(bot.errors[-1], commands.RangeError)
    await run(bot, '!mode fast 2 perhaps')
    assert isinstance(bot.errors[-1], commands.BadBoolArgument)


async def test_missing_and_bad_arguments(bot):
    @bot.command()
    async def add(ctx, a: int, b: int):
        await ctx.send(str(a + b))

    await run(bot, '!add 1')
    error = bot.errors[-1]
    assert isinstance(error, commands.MissingRequiredArgument) and error.param.name == 'b'

    await run(bot, '!add one two')
    assert isinstance(bot.errors[-1], commands.BadArgument)

    await run(bot, '!unknown')
    assert isinstance(bot.errors[-1], commands.CommandNotFound)

    await run(bot, '!add 1 2 3')
    assert replies(bot) == ['3']  # extra arguments are ignored by default


async def test_permission_checks_use_server_roles(bot):
    ran = []

    @bot.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(ctx):
        ran.append(ctx.author.id)

    @bot.command()
    @commands.has_permissions(ban_members=True)
    async def ban(ctx):
        ran.append('ban')

    @bot.command()
    @commands.bot_has_permissions(manage_messages=True)
    async def tidy(ctx):
        ran.append('tidy')

    @bot.command()
    @commands.is_owner()
    async def shutdown(ctx):
        ran.append('shutdown')

    @bot.command()
    @commands.has_role('Moderators')
    async def mods(ctx):
        ran.append('mods')

    await run(bot, '!purge')  # Sara is a moderator
    await run(bot, '!ban')
    await run(bot, '!tidy')
    await run(bot, '!shutdown')
    await run(bot, '!shutdown', author_id=p.OWNER_ID, username='owner')
    await run(bot, '!mods')
    await run(bot, '!mods', author_id=p.OWNER_ID, username='owner')

    assert ran == [int(p.MEMBER_ID), 'tidy', 'shutdown', 'mods']
    kinds = [type(e) for e in bot.errors]
    assert kinds == [commands.MissingPermissions, commands.NotOwner, commands.MissingRole]
    assert bot.errors[0].missing_permissions == ['ban_members']


async def test_cooldowns_and_concurrency(bot):
    @bot.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def daily(ctx):
        await ctx.send('reward')

    await run(bot, '!daily')
    await run(bot, '!daily')
    await run(bot, '!daily', author_id=p.OWNER_ID, username='owner')
    assert replies(bot) == ['reward', 'reward']
    assert isinstance(bot.errors[0], commands.CommandOnCooldown)
    assert 0 < bot.errors[0].retry_after <= 60


async def test_groups_and_subcommands(bot):
    calls = []

    @bot.group(invoke_without_command=True)
    async def tag(ctx, name: str = None):
        calls.append(('tag', name))

    @tag.command()
    async def show(ctx, name: str):
        calls.append(('show', name))

    @tag.group()
    async def admin(ctx):
        calls.append(('admin', ctx.invoked_subcommand.name if ctx.invoked_subcommand else None))

    @admin.command(name='delete')
    async def delete_(ctx, name: str):
        calls.append(('delete', name))

    await run(bot, '!tag')
    await run(bot, '!tag hello')
    await run(bot, '!tag show hello')
    await run(bot, '!tag admin delete old')
    assert calls == [('tag', None), ('tag', 'hello'), ('show', 'hello'), ('admin', 'delete'), ('delete', 'old')]
    assert bot.get_command('tag admin delete') is delete_
    assert delete_.qualified_name == 'tag admin delete'
    assert delete_.full_parent_name == 'tag admin'


async def test_cogs_commands_listeners_and_checks(bot):
    seen = []

    class Greetings(commands.Cog, name='Greetings'):
        """Friendly commands."""

        def __init__(self, bot):
            self.bot = bot

        async def cog_check(self, ctx):
            return ctx.guild is not None

        @commands.command()
        async def hello(self, ctx, *, member: bisim.Member = None):
            """Says hello."""
            member = member or ctx.author
            await ctx.send(f'Hello {member.display_name}')

        @commands.Cog.listener()
        async def on_message(self, message):
            seen.append(message.content)

        @commands.Cog.listener('on_command_completion')
        async def done(self, ctx):
            seen.append(f'done {ctx.command.name}')

    cog = Greetings(bot)
    await bot.add_cog(cog)
    assert bot.get_cog('Greetings') is cog
    assert [c.name for c in cog.get_commands()] == ['hello']

    await run(bot, '!hello')
    await run(bot, '!hello owner')
    assert replies(bot) == ['Hello Sara', 'Hello The Owner']
    assert '!hello' in seen and 'done hello' in seen

    await bot.remove_cog('Greetings')
    await run(bot, '!hello')
    assert isinstance(bot.errors[-1], commands.CommandNotFound)


async def test_mention_prefix_and_callable_prefix(http):
    client = await make_client(commands.Bot, http, command_prefix=commands.when_mentioned_or('?', '$'))
    out = []
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', lambda route, kw: out.append(kw['json']['content']) or user_message(kw['json']['content']))

    @client.command()
    async def ping(ctx):
        await ctx.send(f'pong via {ctx.prefix!r}')

    await run(client, f'<@{p.BOT_ID}> ping')
    await run(client, '?ping')
    await run(client, '$ping')
    assert out == [f"pong via '<@{p.BOT_ID}> '", "pong via '?'", "pong via '$'"]
    await finish_tasks()


async def test_default_help(bot):
    @bot.command()
    async def add(ctx, a: int, b: int):
        """Adds two numbers."""

    @bot.group()
    async def tag(ctx):
        """Manage tags."""

    @tag.command()
    async def show(ctx, name: str):
        """Shows a tag."""

    await run(bot, '!help')
    text = replies(bot)[-1]
    assert text.startswith('```') and text.endswith('```')
    assert 'add' in text and 'Adds two numbers.' in text
    assert 'tag' in text and 'Manage tags.' in text
    assert 'help' in text

    await run(bot, '!help add')
    text = replies(bot)[-1]
    assert '!add <a> <b>' in text and 'Adds two numbers.' in text

    await run(bot, '!help tag')
    assert 'show' in replies(bot)[-1]

    await run(bot, '!help nothing')
    assert 'No command called "nothing" found.' in replies(bot)[-1]


async def test_context_fields_and_typing(bot, http):
    seen = {}

    @bot.command()
    async def where(ctx):
        seen.update(guild=ctx.guild, channel=ctx.channel, author=ctx.author, me=ctx.me, prefix=ctx.prefix, invoked_with=ctx.invoked_with, clean_prefix=ctx.clean_prefix)
        async with ctx.typing():
            pass

    await run(bot, '!where')
    guild = bot.get_guild(int(p.GUILD_ID))
    assert seen['guild'] is guild
    assert seen['channel'] is guild.get_channel(int(p.TEXT_ID))
    assert seen['author'] is guild.get_member(int(p.MEMBER_ID))
    assert seen['me'] is guild.me
    assert seen['prefix'] == '!' and seen['invoked_with'] == 'where' and seen['clean_prefix'] == '!'
    assert http.last('POST', f'/channels/{p.TEXT_ID}/typing')
