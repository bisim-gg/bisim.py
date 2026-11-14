"""Converters: turning the words of a message into members, channels, roles..."""

from __future__ import annotations

import inspect
import re
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
    runtime_checkable,
)

import bisim

from ... import utils
from .errors import *

if TYPE_CHECKING:
    from .context import Context
    from .parameters import Parameter

__all__ = (
    'Converter',
    'ObjectConverter',
    'MemberConverter',
    'UserConverter',
    'MessageConverter',
    'PartialMessageConverter',
    'TextChannelConverter',
    'InviteConverter',
    'GuildConverter',
    'RoleConverter',
    'GameConverter',
    'ColourConverter',
    'ColorConverter',
    'VoiceChannelConverter',
    'EmojiConverter',
    'PartialEmojiConverter',
    'CategoryChannelConverter',
    'GuildChannelConverter',
    'GuildStickerConverter',
    'clean_content',
    'Greedy',
    'Range',
    'run_converters',
)

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)
CT = TypeVar('CT', bound='bisim.abc.GuildChannel')

_ID_RE = re.compile(r'([0-9]{15,20})$')
_USER_MENTION_RE = re.compile(r'<@!?([0-9]{15,20})>$')
_ROLE_MENTION_RE = re.compile(r'<@&([0-9]{15,20})>$')
_CHANNEL_MENTION_RE = re.compile(r'<#([0-9]{15,20})>$')
_EMOJI_RE = re.compile(r'<a?:[A-Za-z0-9_]+:([0-9]{15,20})>$')
_PARTIAL_EMOJI_RE = re.compile(r'<(a?):([A-Za-z0-9_]+):([0-9]{13,20})>$')
_MESSAGE_LINK_RE = re.compile(
    r'https?://(?:www\.)?bisim\.gg/channels/(?P<guild_id>[0-9]{15,20}|@me)/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$'
)
_MESSAGE_PAIR_RE = re.compile(r'(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})$')


def _snowflake_in(argument: str, *patterns: 're.Pattern[str]') -> Optional[int]:
    for pattern in patterns:
        match = pattern.match(argument)
        if match:
            return int(match.group(1))
    return None


def _get_from_guilds(bot: Any, getter: str, argument: Any) -> Any:
    for guild in bot.guilds:
        result = getattr(guild, getter)(argument)
        if result:
            return result
    return None


@runtime_checkable
class Converter(Protocol[T_co]):
    """The base class of custom converters that require the :class:`.Context`
    to be passed to be useful.

    This allows you to implement converters that function similar to the
    special cased ``bisim`` classes.

    Classes that derive from this should override the :meth:`~.Converter.convert`
    method to do its conversion logic. This method must be a :ref:`coroutine <coroutine>`.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> T_co:
        """|coro|

        The method to override to do conversion logic.

        If an error is found while converting, it is recommended to
        raise a :exc:`.CommandError` derived exception as it will
        properly propagate to the error handlers.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context that the argument is being used in.
        argument: :class:`str`
            The argument that is being converted.

        Raises
        -------
        CommandError
            A generic exception occurred when converting the argument.
        BadArgument
            The converter failed to convert the argument.
        """
        raise NotImplementedError('Derived classes need to implement this.')


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument: str) -> Optional['re.Match[str]']:
        return _ID_RE.match(argument)


class ObjectConverter(IDConverter[bisim.Object]):
    """Converts to a :class:`~bisim.Object`.

    The argument must follow the valid ID or mention formats (e.g. ``<@80088516616269824>``).

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by member, role, or channel mention.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Object:
        object_id = _snowflake_in(argument, _ID_RE, _USER_MENTION_RE, _ROLE_MENTION_RE, _CHANNEL_MENTION_RE)
        if object_id is None:
            raise ObjectNotFound(argument)
        return bisim.Object(id=object_id)


class MemberConverter(IDConverter[bisim.Member]):
    """Converts to a :class:`~bisim.Member`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by guild nickname, global name or user name.

    Bisim has no discriminators; a ``#0`` at the end of a name, as in names
    copied from Discord, is ignored.
    """

    async def query_member_named(self, guild: bisim.Guild, argument: str) -> Optional[bisim.Member]:
        found = guild.get_member_named(argument)
        if found is not None:
            return found
        username, _, discriminator = argument.rpartition('#')
        name = username if discriminator == '0' else argument
        members = await guild.query_members(name, limit=100, cache=True)
        return utils.find(lambda m: m.name == name or m.global_name == name or m.nick == name, members)

    async def query_member_by_id(self, bot: Any, guild: bisim.Guild, user_id: int) -> Optional[bisim.Member]:
        try:
            member = await guild.fetch_member(user_id)
        except bisim.HTTPException:
            return None
        guild._add_member(member)
        return member

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Member:
        bot = ctx.bot
        user_id = _snowflake_in(argument, _ID_RE, _USER_MENTION_RE)
        guild = ctx.guild
        result: Optional[bisim.Member] = None

        if user_id is None:
            if guild is not None:
                result = await self.query_member_named(guild, argument)
            else:
                result = _get_from_guilds(bot, 'get_member_named', argument)
        else:
            if guild is not None:
                result = guild.get_member(user_id)
                if result is None and ctx.message is not None:
                    result = utils.get(ctx.message.mentions, id=user_id)  # type: ignore
                if result is None:
                    result = await self.query_member_by_id(bot, guild, user_id)
            else:
                result = _get_from_guilds(bot, 'get_member', user_id)

        if not isinstance(result, bisim.Member):
            raise MemberNotFound(argument)
        return result


class UserConverter(IDConverter[bisim.User]):
    """Converts to a :class:`~bisim.User`.

    All lookups are via the global user cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by user name.
    4. Lookup by global name.

    Bisim has no discriminators; a ``#0`` at the end of a name, as in names
    copied from Discord, is ignored.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.User:
        user_id = _snowflake_in(argument, _ID_RE, _USER_MENTION_RE)
        state = ctx._state

        if user_id is not None:
            result = ctx.bot.get_user(user_id)
            if result is None and ctx.message is not None:
                mentioned = utils.get(ctx.message.mentions, id=user_id)
                result = getattr(mentioned, '_user', mentioned)
            if result is None:
                try:
                    result = await ctx.bot.fetch_user(user_id)
                except bisim.HTTPException:
                    raise UserNotFound(argument) from None
            return result  # type: ignore

        username, _, discriminator = argument.rpartition('#')
        name = username if discriminator == '0' else argument
        users = list(state._users.values())
        for predicate in (lambda u: u.name == name, lambda u: u.global_name == name):
            found = utils.find(predicate, users)
            if found is not None:
                return found  # type: ignore
        raise UserNotFound(argument)


class PartialMessageConverter(Converter[bisim.PartialMessage]):
    """Converts to a :class:`bisim.PartialMessage`.

    The creation strategy is as follows (in order):

    1. By "{channel ID}-{message ID}"
    2. By message ID (The message is assumed to be in the context channel.)
    3. By message URL
    """

    @staticmethod
    def _get_id_matches(ctx: Context[Any], argument: str) -> Tuple[Optional[int], int, int]:
        match = _MESSAGE_PAIR_RE.match(argument)
        if match:
            channel_id = int(match.group('channel_id') or ctx.channel.id)
            return None, int(match.group('message_id')), channel_id
        match = _MESSAGE_LINK_RE.match(argument)
        if match:
            raw_guild = match.group('guild_id')
            guild_id = None if raw_guild == '@me' else int(raw_guild)
            return guild_id, int(match.group('message_id')), int(match.group('channel_id'))
        raise MessageNotFound(argument)

    @staticmethod
    def _resolve_channel(ctx: Context[Any], guild_id: Optional[int], channel_id: Optional[int]) -> Any:
        if channel_id is None:
            return ctx.channel
        if guild_id is not None:
            guild = ctx.bot.get_guild(guild_id)
            if guild is None:
                return None
            return guild.get_channel(channel_id)
        return ctx.bot.get_channel(channel_id)

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.PartialMessage:
        guild_id, message_id, channel_id = self._get_id_matches(ctx, argument)
        channel = self._resolve_channel(ctx, guild_id, channel_id)
        if not channel or not isinstance(channel, bisim.abc.Messageable):
            raise ChannelNotFound(channel_id)
        return bisim.PartialMessage(channel=channel, id=message_id)  # type: ignore


class MessageConverter(IDConverter[bisim.Message]):
    """Converts to a :class:`bisim.Message`.

    The lookup strategy is as follows (in order):

    1. Lookup by "{channel ID}-{message ID}"
    2. Lookup by message ID (the message **must** be in the context channel)
    3. Lookup by message URL
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Message:
        guild_id, message_id, channel_id = PartialMessageConverter._get_id_matches(ctx, argument)
        message = ctx.bot._connection._get_message(message_id)
        if message:
            return message
        channel = PartialMessageConverter._resolve_channel(ctx, guild_id, channel_id)
        if not channel or not isinstance(channel, bisim.abc.Messageable):
            raise ChannelNotFound(channel_id)
        try:
            return await channel.fetch_message(message_id)
        except bisim.NotFound:
            raise MessageNotFound(argument)
        except bisim.Forbidden:
            raise ChannelNotReadable(channel)  # type: ignore


class GuildChannelConverter(IDConverter[bisim.abc.GuildChannel]):
    """Converts to a :class:`~bisim.abc.GuildChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by channel URL.
    4. Lookup by name.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.abc.GuildChannel:
        return self._resolve_channel(ctx, argument, 'channels', bisim.abc.GuildChannel)

    @staticmethod
    def _resolve_channel(ctx: Context[Any], argument: str, attribute: str, type: Type[CT]) -> CT:
        bot = ctx.bot
        channel_id = _snowflake_in(argument, _ID_RE, _CHANNEL_MENTION_RE)
        if channel_id is None:
            link = re.match(r'https?://(?:www\.)?bisim\.gg/channels/([0-9]{15,20})/([0-9]{15,20})/?$', argument)
            if link:
                channel_id = int(link.group(2))
        result: Any = None
        guild = ctx.guild

        if channel_id is None:
            # Not an id: look the name up.
            if guild is not None:
                result = utils.find(lambda c: isinstance(c, type) and c.name == argument, getattr(guild, attribute))
            else:
                for g in bot.guilds:
                    result = utils.find(lambda c: isinstance(c, type) and c.name == argument, getattr(g, attribute))
                    if result is not None:
                        break
        else:
            if guild is not None:
                result = guild.get_channel(channel_id)
            else:
                result = _get_from_guilds(bot, 'get_channel', channel_id)

        if not isinstance(result, type):
            raise ChannelNotFound(argument)
        return result


class TextChannelConverter(IDConverter[bisim.TextChannel]):
    """Converts to a :class:`~bisim.TextChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by channel URL.
    4. Lookup by name
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.TextChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'text_channels', bisim.TextChannel)


class VoiceChannelConverter(IDConverter[bisim.VoiceChannel]):
    """Converts to a :class:`~bisim.VoiceChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by channel URL.
    4. Lookup by name
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.VoiceChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'voice_channels', bisim.VoiceChannel)


class CategoryChannelConverter(IDConverter[bisim.CategoryChannel]):
    """Converts to a :class:`~bisim.CategoryChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by channel URL.
    4. Lookup by name
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.CategoryChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'categories', bisim.CategoryChannel)


class ColourConverter(Converter[bisim.Colour]):
    """Converts to a :class:`~bisim.Colour`.

    The following formats are accepted:

    - ``0x<hex>``
    - ``#<hex>``
    - ``0x#<hex>``
    - ``rgb(<number>, <number>, <number>)``
    - Any of the ``classmethod`` in :class:`~bisim.Colour`

        - The ``_`` in the name can be optionally replaced with spaces.

    Like CSS, ``<number>`` can be either 0-255 or 0-100% and ``<hex>`` can be
    either a 6 digit hex number or a 3 digit hex shortcut (e.g. #fff).
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Colour:
        try:
            return bisim.Colour.from_str(argument)
        except ValueError:
            name = argument.lower().replace(' ', '_')
            factory = getattr(bisim.Colour, name, None)
            if name.startswith('from_') or factory is None or not inspect.ismethod(factory):
                raise BadColourArgument(argument)
            return factory()


ColorConverter = ColourConverter


class RoleConverter(IDConverter[bisim.Role]):
    """Converts to a :class:`~bisim.Role`.

    All lookups are via the local guild. If in a DM context, the converter raises
    :exc:`.NoPrivateMessage` exception.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Role:
        guild = ctx.guild
        if not guild:
            raise NoPrivateMessage()

        role_id = _snowflake_in(argument, _ID_RE, _ROLE_MENTION_RE)
        if role_id is not None:
            result = guild.get_role(role_id)
        else:
            result = utils.get(guild._roles.values(), name=argument)

        if result is None:
            raise RoleNotFound(argument)
        return result


class GameConverter(Converter[bisim.Game]):
    """Converts to a :class:`~bisim.Game`."""

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Game:
        return bisim.Game(name=argument)


class InviteConverter(Converter[bisim.Invite]):
    """Converts to a :class:`~bisim.Invite`.

    This is done via an HTTP request using :meth:`.Bot.fetch_invite`.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Invite:
        try:
            return await ctx.bot.fetch_invite(argument)
        except Exception as exc:
            raise BadInviteArgument(argument) from exc


class GuildConverter(IDConverter[bisim.Guild]):
    """Converts to a :class:`~bisim.Guild`.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by name. (There is no disambiguation for Guilds with multiple matching names).
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Guild:
        match = self._get_id_match(argument)
        result: Optional[bisim.Guild] = None

        if match is not None:
            result = ctx.bot.get_guild(int(match.group(1)))

        if result is None:
            result = utils.get(ctx.bot.guilds, name=argument)

        if result is None:
            raise GuildNotFound(argument)
        return result


class EmojiConverter(IDConverter[bisim.Emoji]):
    """Converts to a :class:`~bisim.Emoji`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.Emoji:
        emoji_id = _snowflake_in(argument, _ID_RE, _EMOJI_RE)
        bot = ctx.bot
        guild = ctx.guild
        result: Optional[bisim.Emoji] = None

        if emoji_id is None:
            if guild is not None:
                result = utils.get(guild.emojis, name=argument)
            if result is None:
                result = utils.get(bot.emojis, name=argument)
        else:
            result = bot.get_emoji(emoji_id)

        if result is None:
            raise EmojiNotFound(argument)
        return result


class PartialEmojiConverter(Converter[bisim.PartialEmoji]):
    """Converts to a :class:`~bisim.PartialEmoji`.

    This is done by extracting the animated flag, name and ID from the emoji.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.PartialEmoji:
        match = _PARTIAL_EMOJI_RE.match(argument)
        if match:
            animated, name, emoji_id = match.groups()
            return bisim.PartialEmoji.with_state(ctx.bot._connection, animated=bool(animated), name=name, id=int(emoji_id))
        raise PartialEmojiConversionFailure(argument)


class GuildStickerConverter(IDConverter[bisim.GuildSticker]):
    """Converts to a :class:`~bisim.GuildSticker`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by name.
    """

    async def convert(self, ctx: Context[Any], argument: str) -> bisim.GuildSticker:
        match = self._get_id_match(argument)
        bot = ctx.bot
        guild = ctx.guild
        result: Optional[bisim.GuildSticker] = None

        if match is None:
            if guild is not None:
                result = utils.get(guild.stickers, name=argument)
            if result is None:
                result = utils.get(bot.stickers, name=argument)
        else:
            result = bot.get_sticker(int(match.group(1)))

        if result is None:
            raise GuildStickerNotFound(argument)
        return result


class clean_content(Converter[str]):
    """Converts the argument to mention scrubbed version of
    said content.

    This behaves similarly to :attr:`~bisim.Message.clean_content`.

    Attributes
    ------------
    fix_channel_mentions: :class:`bool`
        Whether to clean channel mentions.
    use_nicknames: :class:`bool`
        Whether to use nicknames when transforming mentions.
    escape_markdown: :class:`bool`
        Whether to also escape special markdown characters.
    remove_markdown: :class:`bool`
        Whether to also remove special markdown characters. This option is not supported with ``escape_markdown``
    """

    def __init__(
        self,
        *,
        fix_channel_mentions: bool = False,
        use_nicknames: bool = True,
        escape_markdown: bool = False,
        remove_markdown: bool = False,
    ) -> None:
        self.fix_channel_mentions = fix_channel_mentions
        self.use_nicknames = use_nicknames
        self.escape_markdown = escape_markdown
        self.remove_markdown = remove_markdown

    async def convert(self, ctx: Context[Any], argument: str) -> str:
        message = ctx.message
        guild = ctx.guild

        def member_name(match: 're.Match[str]') -> str:
            user_id = int(match.group(1))
            member = guild.get_member(user_id) if guild is not None else None
            if member is not None:
                return '@' + (member.display_name if self.use_nicknames else member.name)
            user = ctx.bot.get_user(user_id)
            return '@' + user.name if user is not None else '@deleted-user'

        def role_name(match: 're.Match[str]') -> str:
            role = guild.get_role(int(match.group(1))) if guild is not None else None
            return '@' + role.name if role is not None else '@deleted-role'

        def channel_name(match: 're.Match[str]') -> str:
            channel = ctx.bot.get_channel(int(match.group(1)))
            return '#' + channel.name if channel is not None and hasattr(channel, 'name') else '#deleted-channel'

        result = re.sub(r'<@!?([0-9]{1,20})>', member_name, argument)
        result = re.sub(r'<@&([0-9]{1,20})>', role_name, result)
        if self.fix_channel_mentions:
            result = re.sub(r'<#([0-9]{1,20})>', channel_name, result)

        if self.escape_markdown:
            result = utils.escape_markdown(result)
        elif self.remove_markdown:
            result = utils.remove_markdown(result)

        return utils.escape_mentions(result)


class Greedy(List[T]):
    r"""A special converter that greedily consumes arguments until it can't.
    As a consequence of this behaviour, most input errors are silently discarded,
    since it is used as an indicator of when to stop parsing.

    When a parser error is met the greedy converter stops converting, undoes the
    internal string parsing routine, and continues parsing regularly.

    For example, in the following code:

    .. code-block:: python3

        @commands.command()
        async def test(ctx, numbers: Greedy[int], reason: str):
            await ctx.send("numbers: {}, reason: {}".format(numbers, reason))

    An invocation of ``[p]test 1 2 3 4 5 6 hello`` would pass ``numbers`` with
    ``[1, 2, 3, 4, 5, 6]`` and ``reason`` with ``hello``\.
    """

    __slots__ = ('converter',)

    def __init__(self, *, converter: T) -> None:
        self.converter: T = converter

    def __repr__(self) -> str:
        converter = getattr(self.converter, '__name__', repr(self.converter))
        return f'Greedy[{converter}]'

    def __class_getitem__(cls, params: Union[Tuple[T], T]) -> Greedy[T]:  # type: ignore
        if not isinstance(params, tuple):
            params = (params,)
        if len(params) != 1:
            raise TypeError('Greedy[...] only takes a single argument')
        converter = params[0]

        args = getattr(converter, '__args__', ())
        origin = getattr(converter, '__origin__', None)

        if not (callable(converter) or isinstance(converter, Converter) or origin is not None):
            raise TypeError('Greedy[...] expects a type or a Converter instance.')

        if converter in (str, type(None)) or origin is Greedy:
            raise TypeError(f'Greedy[{converter.__name__}] is invalid.')  # type: ignore

        if origin is Union and type(None) in args:
            raise TypeError(f'Greedy[{converter!r}] is invalid.')

        return cls(converter=converter)  # type: ignore

    @property
    def constructed_converter(self) -> Any:
        if inspect.isclass(self.converter) and issubclass(self.converter, Converter) and not inspect.ismethod(self.converter.convert):
            return self.converter()
        return self.converter


if TYPE_CHECKING:
    from typing_extensions import Annotated as Range
else:

    class Range:
        """A special converter that can be applied to a parameter to require a numeric
        or string type to fit within the range provided.

        During type checking time this is equivalent to :obj:`typing.Annotated` so type checkers understand
        the intent of the code.

        Some example ranges:

        - ``Range[int, 10]`` means the minimum is 10 with no maximum.
        - ``Range[int, None, 10]`` means the maximum is 10 with no minimum.
        - ``Range[int, 1, 10]`` means the minimum is 1 and the maximum is 10.
        - ``Range[float, 1.0, 5.0]`` means the minimum is 1.0 and the maximum is 5.0.
        - ``Range[str, 1, 10]`` means the minimum length is 1 and the maximum length is 10.

        If the value cannot be converted to the provided type or is outside the given range,
        :class:`~.ext.commands.BadArgument` or :class:`~.ext.commands.RangeError` is raised to
        the appropriate error handlers respectively.

        Examples
        ----------

        .. code-block:: python3

            @bot.command()
            async def range(ctx: commands.Context, value: commands.Range[int, 10, 12]):
                await ctx.send(f'Your value is {value}')
        """

        def __init__(
            self,
            *,
            annotation: Any,
            min: Optional[Union[int, float]] = None,
            max: Optional[Union[int, float]] = None,
        ) -> None:
            self.annotation: Any = annotation
            self.min: Optional[Union[int, float]] = min
            self.max: Optional[Union[int, float]] = max

            if min and max and min > max:
                raise TypeError('minimum cannot be larger than maximum')

        async def convert(self, ctx: Context[Any], value: str) -> Union[int, float, str]:
            try:
                count = converted = self.annotation(value)
            except ValueError:
                raise BadArgument(
                    f'Converting to "{self.annotation.__name__}" failed for parameter "{ctx.current_parameter.name}".'  # type: ignore
                )

            if self.annotation is str:
                count = len(value)

            if (self.min is not None and count < self.min) or (self.max is not None and count > self.max):
                raise RangeError(converted, minimum=self.min, maximum=self.max)

            return converted

        def __call__(self) -> None:
            pass

        def __or__(self, rhs: Any) -> Any:
            return Union[self, rhs]

        def __repr__(self) -> str:
            return f'{self.__class__.__name__}[{self.annotation.__name__}, {self.min}, {self.max}]'

        def __class_getitem__(cls, obj: Any) -> Range:
            if not isinstance(obj, tuple):
                raise TypeError(f'expected tuple for arguments, received {obj.__class__.__name__} instead')

            if len(obj) == 2:
                obj = (*obj, None)
            elif len(obj) != 3:
                raise TypeError('Range accepts either two or three arguments with the first being the type of range.')

            annotation, min, max = obj

            if min is None and max is None:
                raise TypeError('Range must not be empty')

            if min is not None and max is not None:
                if type(min) != type(max):
                    raise TypeError('Both min and max in Range must be the same type')

            if annotation not in (int, float, str):
                raise TypeError(f'expected int, float, or str as range type, received {annotation!r} instead')

            if annotation in (str, int):
                cast = int
            else:
                cast = float

            return cls(
                annotation=annotation,
                min=cast(min) if min is not None else None,
                max=cast(max) if max is not None else None,
            )


def _convert_to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    if lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    raise BadBoolArgument(lowered)


_GenericAlias = type(List[T])


def is_generic_type(tp: Any, *, _GenericAlias: type = _GenericAlias) -> bool:
    return isinstance(tp, type) and issubclass(tp, Generic) or isinstance(tp, _GenericAlias)


CONVERTER_MAPPING: Dict[type, Any] = {
    bisim.Object: ObjectConverter,
    bisim.Member: MemberConverter,
    bisim.User: UserConverter,
    bisim.abc.User: UserConverter,
    bisim.Message: MessageConverter,
    bisim.PartialMessage: PartialMessageConverter,
    bisim.TextChannel: TextChannelConverter,
    bisim.Invite: InviteConverter,
    bisim.Guild: GuildConverter,
    bisim.Role: RoleConverter,
    bisim.Game: GameConverter,
    bisim.Colour: ColourConverter,
    bisim.VoiceChannel: VoiceChannelConverter,
    bisim.Emoji: EmojiConverter,
    bisim.PartialEmoji: PartialEmojiConverter,
    bisim.CategoryChannel: CategoryChannelConverter,
    bisim.abc.GuildChannel: GuildChannelConverter,
    bisim.GuildSticker: GuildStickerConverter,
}


async def _actual_conversion(ctx: Context[Any], converter: Any, argument: str, param: inspect.Parameter) -> Any:
    if converter is bool:
        return _convert_to_bool(argument)

    try:
        converter = CONVERTER_MAPPING.get(converter, converter)
    except TypeError:
        pass

    try:
        if inspect.isclass(converter) and issubclass(converter, Converter):
            if inspect.ismethod(converter.convert):
                return await converter.convert(ctx, argument)
            return await converter().convert(ctx, argument)
        if isinstance(converter, Converter):
            return await converter.convert(ctx, argument)  # type: ignore
    except CommandError:
        raise
    except Exception as exc:
        raise ConversionError(converter, exc) from exc  # type: ignore

    try:
        return converter(argument)
    except CommandError:
        raise
    except Exception as exc:
        name = getattr(converter, '__name__', converter.__class__.__name__)
        raise BadArgument(f'Converting to "{name}" failed for parameter "{param.name}".') from exc


def _is_union(converter: Any) -> bool:
    return getattr(converter, '__origin__', None) is Union or type(converter).__name__ == 'UnionType'


async def run_converters(ctx: Context[Any], converter: Any, argument: str, param: Parameter) -> Any:
    """|coro|

    Runs converters for a given converter, argument, and parameter.

    This function does the same work that the library does under the hood.

    Parameters
    ------------
    ctx: :class:`Context`
        The invocation context to run the converters under.
    converter: Any
        The converter to run, this corresponds to the annotation in the function.
    argument: :class:`str`
        The argument to convert to.
    param: :class:`Parameter`
        The parameter being converted. This is mainly for error reporting.

    Raises
    -------
    CommandError
        The converter failed to convert.

    Returns
    --------
    Any
        The resulting conversion.
    """
    origin = getattr(converter, '__origin__', None)

    if _is_union(converter):
        errors = []
        none_type = type(None)
        union_args = converter.__args__
        for conv in union_args:
            # Reaching None means every converter before it failed: put the
            # word back for the next parameter and use the default.
            if conv is none_type and param.kind != param.VAR_POSITIONAL:
                ctx.view.undo()
                return None if param.required else await param.get_default(ctx)

            try:
                value = await run_converters(ctx, conv, argument, param)
            except CommandError as exc:
                errors.append(exc)
            else:
                return value

        raise BadUnionArgument(param, union_args, errors)

    if origin is Literal:
        errors = []
        conversions: Dict[type, Any] = {}
        literal_args = converter.__args__
        for literal in literal_args:
            literal_type = type(literal)
            if literal_type not in conversions:
                try:
                    conversions[literal_type] = await _actual_conversion(ctx, literal_type, argument, param)
                except CommandError as exc:
                    errors.append(exc)
                    conversions[literal_type] = object()
                    continue
            if conversions[literal_type] == literal:
                return conversions[literal_type]

        raise BadLiteralArgument(param, literal_args, errors, argument)

    # Plain generics such as List[int] convert with their origin.
    if origin is not None and is_generic_type(converter):
        converter = origin

    return await _actual_conversion(ctx, converter, argument, param)
