"""Bit flag containers: :class:`Intents`, :class:`MessageFlags` and friends.

The flag machinery is shared with :class:`~bisim.Permissions`.
"""

from __future__ import annotations

from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Dict, Iterator, List, Optional, Tuple, Type, TypeVar, overload

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    'BaseFlags',
    'flag_value',
    'alias_flag_value',
    'Intents',
    'MemberCacheFlags',
    'MessageFlags',
    'PublicUserFlags',
    'SystemChannelFlags',
    'ChannelFlags',
    'AppCommandContext',
    'AppInstallationType',
    'ApplicationFlags',
    'MemberFlags',
    'RoleFlags',
    'AttachmentFlags',
    'EmbedFlags',
    'AutoModPresets',
)

F = TypeVar('F', bound='BaseFlags')


class flag_value:
    """A descriptor for one flag of a :class:`BaseFlags` subclass.

    The decorated function returns the flag's bit mask.
    """

    def __init__(self, func: Callable[[Any], int]):
        self.flag: int = func(None)
        self.__doc__: Optional[str] = func.__doc__
        self.name: str = func.__name__

    @overload
    def __get__(self, instance: None, owner: Type[Any]) -> 'flag_value':
        ...

    @overload
    def __get__(self, instance: BaseFlags, owner: Type[BaseFlags]) -> bool:
        ...

    def __get__(self, instance: Optional[BaseFlags], owner: Type[BaseFlags]) -> Any:
        if instance is None:
            return self
        return instance._has_flag(self.flag)

    def __set__(self, instance: BaseFlags, value: bool) -> None:
        instance._set_flag(self.flag, value)

    def __repr__(self) -> str:
        return f'<flag_value flag={self.flag!r}>'


class alias_flag_value(flag_value):
    """A flag that is another name for one or more other flags (left out of iteration)."""

    pass


def fill_with_flags(*, inverted: bool = False) -> Callable[[Type[F]], Type[F]]:
    def decorator(cls: Type[F]) -> Type[F]:
        valid: Dict[str, int] = {}
        public: List[str] = []
        for klass in reversed(cls.__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, flag_value):
                    valid[name] = value.flag
                    if not isinstance(value, alias_flag_value) and name not in public:
                        public.append(name)
        cls.VALID_FLAGS = valid
        cls._PUBLIC_FLAGS = tuple(public)
        if inverted:
            max_bits = max(valid.values()).bit_length()
            cls.DEFAULT_VALUE = -1 + (2**max_bits)
        else:
            cls.DEFAULT_VALUE = 0
        return cls

    return decorator


class BaseFlags:
    """The common base of every flag container.

    Supports ``==``, ``hash``, ``|``, ``&``, ``^``, ``~`` and iteration over
    ``(name, value)`` pairs, like discord.py's flags.
    """

    VALID_FLAGS: ClassVar[Dict[str, int]]
    DEFAULT_VALUE: ClassVar[int]
    _PUBLIC_FLAGS: ClassVar[Tuple[str, ...]]

    value: int

    __slots__ = ('value',)

    def __init__(self, **kwargs: bool):
        self.value = self.DEFAULT_VALUE
        for key, value in kwargs.items():
            if key not in self.VALID_FLAGS:
                raise TypeError(f'{key!r} is not a valid flag name.')
            setattr(self, key, value)

    @classmethod
    def _from_value(cls, value: int) -> Self:
        self = cls.__new__(cls)
        self.value = int(value)
        return self

    def __or__(self, other: Self) -> Self:
        if isinstance(other, self.__class__):
            return self._from_value(self.value | other.value)
        if isinstance(other, flag_value):
            return self._from_value(self.value | other.flag)
        return NotImplemented

    def __and__(self, other: Self) -> Self:
        if isinstance(other, self.__class__):
            return self._from_value(self.value & other.value)
        if isinstance(other, flag_value):
            return self._from_value(self.value & other.flag)
        return NotImplemented

    def __xor__(self, other: Self) -> Self:
        if isinstance(other, self.__class__):
            return self._from_value(self.value ^ other.value)
        if isinstance(other, flag_value):
            return self._from_value(self.value ^ other.flag)
        return NotImplemented

    def __ior__(self, other: Self) -> Self:
        result = self.__or__(other)
        if result is NotImplemented:
            return NotImplemented
        self.value = result.value
        return self

    def __iand__(self, other: Self) -> Self:
        result = self.__and__(other)
        if result is NotImplemented:
            return NotImplemented
        self.value = result.value
        return self

    def __ixor__(self, other: Self) -> Self:
        result = self.__xor__(other)
        if result is NotImplemented:
            return NotImplemented
        self.value = result.value
        return self

    def __invert__(self) -> Self:
        max_bits = max(self.VALID_FLAGS.values()).bit_length()
        mask = (1 << max_bits) - 1
        return self._from_value(self.value ^ mask)

    def __bool__(self) -> bool:
        return self.value != self.DEFAULT_VALUE

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self.value == other.value

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} value={self.value}>'

    def __iter__(self) -> Iterator[Tuple[str, bool]]:
        for name in self._PUBLIC_FLAGS:
            yield (name, self._has_flag(self.VALID_FLAGS[name]))

    def _has_flag(self, o: int) -> bool:
        return (self.value & o) == o

    def _set_flag(self, o: int, toggle: bool) -> None:
        if toggle is True:
            self.value |= o
        elif toggle is False:
            self.value &= ~o
        else:
            raise TypeError(f'Value to set for {self.__class__.__name__} must be a bool.')


class ArrayFlags(BaseFlags):
    """Flags sent as a list of names or bit positions."""

    @classmethod
    def _from_value(cls, value: Any) -> Self:
        if isinstance(value, int):
            return super()._from_value(value)
        result = 0
        for item in value or ():
            if isinstance(item, int):
                result |= 1 << (item - 1)
        return super()._from_value(result)


@fill_with_flags()
class SystemChannelFlags(BaseFlags):
    """Wraps up a Bisim system channel flag value (kept for compatibility)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def join_notifications(self) -> int:
        """:class:`bool`: Returns ``True`` if the system channel is used for member join notifications."""
        return 1

    @flag_value
    def premium_subscriptions(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 2

    @flag_value
    def guild_reminder_notifications(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 4

    @flag_value
    def join_notification_replies(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 8


@fill_with_flags()
class MessageFlags(BaseFlags):
    r"""Wraps up a Bisim Message flag value.

    See :class:`SystemChannelFlags`.

    .. container:: operations

        .. describe:: x == y

            Checks if two flags are equal.
        .. describe:: x != y

            Checks if two flags are not equal.
        .. describe:: hash(x)

               Return the flag's hash.
        .. describe:: iter(x)

               Returns an iterator of ``(name, value)`` pairs. This allows it
               to be, for example, constructed as a dict or a list of pairs.

    Attributes
    -----------
    value: :class:`int`
        The raw value. This value is a bit array field of a 53-bit integer
        representing the currently available flags. You should query
        flags via the properties rather than using this raw value.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def crossposted(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1

    @flag_value
    def is_crossposted(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 2

    @flag_value
    def suppress_embeds(self) -> int:
        """:class:`bool`: Returns ``True`` if the message's embeds have been suppressed."""
        return 4

    @flag_value
    def source_message_deleted(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 8

    @flag_value
    def urgent(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 16

    @flag_value
    def has_thread(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 32

    @flag_value
    def ephemeral(self) -> int:
        """:class:`bool`: Returns ``True`` if the source message is ephemeral."""
        return 64

    @flag_value
    def loading(self) -> int:
        """:class:`bool`: Returns ``True`` if the message is an interaction response and the bot
        is "thinking".
        """
        return 128

    @flag_value
    def failed_to_mention_some_roles_in_thread(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 256

    @flag_value
    def suppress_notifications(self) -> int:
        """:class:`bool`: Returns ``True`` if the message will not trigger push and desktop notifications."""
        return 4096

    @alias_flag_value
    def silent(self) -> int:
        """:class:`bool`: Alias for :attr:`suppress_notifications`."""
        return 4096

    @flag_value
    def voice(self) -> int:
        """:class:`bool`: Returns ``True`` if the message is a voice message."""
        return 8192

    @flag_value
    def forwarded(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 16384

    @flag_value
    def components_v2(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 32768


@fill_with_flags()
class PublicUserFlags(BaseFlags):
    """Wraps up the public flags of a user. Bisim only sets :attr:`verified_bot` style
    flags for bots; the rest are kept for compatibility and are always ``False``.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def staff(self) -> int:
        """:class:`bool`: Returns ``True`` if the user is a Bisim employee."""
        return 1

    @flag_value
    def partner(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 2

    @flag_value
    def hypesquad(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 4

    @flag_value
    def bug_hunter(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 8

    @flag_value
    def early_supporter(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 512

    @flag_value
    def team_user(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1024

    @flag_value
    def system(self) -> int:
        """:class:`bool`: Returns ``True`` if the user is a system user (i.e. represents Bisim officially)."""
        return 4096

    @flag_value
    def verified_bot(self) -> int:
        """:class:`bool`: Returns ``True`` if the user is a verified bot."""
        return 65536

    @flag_value
    def verified_bot_developer(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 131072

    @flag_value
    def bot_http_interactions(self) -> int:
        """:class:`bool`: Returns ``True`` if the user is a bot that only uses HTTP interactions."""
        return 524288

    @flag_value
    def spammer(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1048576

    @flag_value
    def active_developer(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 4194304

    def all(self) -> List[Any]:
        """List[:class:`UserFlags`]: Returns all public flags the user has."""
        from .enums import UserFlags

        return [member for member in UserFlags if self._has_flag(member.value)]


@fill_with_flags()
class Intents(BaseFlags):
    r"""Wraps up a Bisim gateway intent flag.

    Similar to :class:`Permissions`\, the properties provided are two way.
    You can set and retrieve individual bits using the properties as if they
    were regular bools.

    To construct an object you can pass keyword arguments denoting the flags
    to enable or disable.

    This is used to disable certain gateway features that are unnecessary to
    run your bot. To make use of this, it is passed to the ``intents`` keyword
    argument of :class:`Client`. The bits are Discord's, number for number.

    Three intents are privileged: :attr:`members`, :attr:`presences` and
    :attr:`message_content`. Each must also be switched on for the application
    at https://bisim.gg/developers (your application, **Bot**, **Privileged
    Gateway Intents**), and from 100 servers on Bisim must approve it. Asking
    for one that is not switched on closes the connection with code 4014 and
    raises :exc:`PrivilegedIntentsRequired`.

    .. container:: operations

        .. describe:: x == y

            Checks if two flags are equal.
        .. describe:: x != y

            Checks if two flags are not equal.
        .. describe:: x | y, x |= y

            Returns an Intents instance with all enabled flags from
            both x and y.
        .. describe:: x & y, x &= y

            Returns an Intents instance with only flags enabled on
            both x and y.
        .. describe:: x ^ y, x ^= y

            Returns an Intents instance with only flags enabled on
            only one of x or y, not on both.
        .. describe:: ~x

            Returns an Intents instance with all flags inverted from x.
        .. describe:: hash(x)

               Return the flag's hash.
        .. describe:: iter(x)

               Returns an iterator of ``(name, value)`` pairs. This allows it
               to be, for example, constructed as a dict or a list of pairs.

    Attributes
    -----------
    value: :class:`int`
        The raw value. You should query flags via the properties
        rather than using this raw value.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        super().__init__(**kwargs)
        if value:
            self.value = value

    @classmethod
    def all(cls) -> Self:
        """A factory method that creates a :class:`Intents` with everything enabled."""
        return cls._from_value(reduce(or_, cls.VALID_FLAGS.values()))

    @classmethod
    def none(cls) -> Self:
        """A factory method that creates a :class:`Intents` with everything disabled."""
        return cls._from_value(0)

    @classmethod
    def default(cls) -> Self:
        """A factory method that creates a :class:`Intents` with everything enabled
        except :attr:`presences`, :attr:`members`, and :attr:`message_content`.
        """
        self = cls.all()
        self.presences = False
        self.members = False
        self.message_content = False
        return self

    @flag_value
    def guilds(self) -> int:
        """:class:`bool`: Whether guild related events are enabled.

        This corresponds to the following events:

        - :func:`on_guild_update`
        - :func:`on_guild_role_create`
        - :func:`on_guild_role_update`
        - :func:`on_guild_role_delete`
        - :func:`on_guild_channel_create`
        - :func:`on_guild_channel_update`
        - :func:`on_guild_channel_delete`
        - :func:`on_guild_channel_pins_update`
        - :func:`on_voice_channel_status_update`

        It is highly advisable to leave this intent enabled for your bot to function.
        """
        return 1 << 0

    @flag_value
    def members(self) -> int:
        """:class:`bool`: Whether guild member related events are enabled.

        This corresponds to the following events:

        - :func:`on_member_join`
        - :func:`on_member_remove`
        - :func:`on_raw_member_remove`
        - :func:`on_member_update`
        - :func:`on_user_update` (about someone else, :attr:`presences` lets it through too)

        This also corresponds to the following attributes and classes in terms of cache:

        - :meth:`Guild.chunk`
        - :meth:`Guild.fetch_members`
        - :attr:`Guild.members`

        Without it, Bisim refuses the full member list, so the library does
        not load the members at startup; :meth:`Guild.fetch_member` and
        :meth:`Guild.query_members` still work.

        .. note::

            This is a privileged intent: switch it on at https://bisim.gg/developers.
            Bots in 100 servers or more need Bisim's approval as well.
        """
        return 1 << 1

    @flag_value
    def moderation(self) -> int:
        """:class:`bool`: Whether guild moderation related events are enabled.

        This corresponds to the following events:

        - :func:`on_member_ban`
        - :func:`on_member_unban`
        - :func:`on_audit_log_entry_create`
        """
        return 1 << 2

    @alias_flag_value
    def bans(self) -> int:
        """:class:`bool`: An alias of :attr:`moderation`."""
        return 1 << 2

    @flag_value
    def expressions(self) -> int:
        """:class:`bool`: Whether guild emoji, sticker, and soundboard sound related events are enabled.

        This corresponds to the following events:

        - :func:`on_guild_emojis_update`
        - :func:`on_guild_stickers_update`
        """
        return 1 << 3

    @alias_flag_value
    def emojis(self) -> int:
        """:class:`bool`: Alias of :attr:`expressions`."""
        return 1 << 3

    @alias_flag_value
    def emojis_and_stickers(self) -> int:
        """:class:`bool`: Alias of :attr:`expressions`."""
        return 1 << 3

    @flag_value
    def integrations(self) -> int:
        """:class:`bool`: Whether guild integration related events are enabled.

        Bisim sends no integration events, so this changes nothing.
        """
        return 1 << 4

    @flag_value
    def webhooks(self) -> int:
        """:class:`bool`: Whether guild webhook related events are enabled.

        This corresponds to the following events:

        - :func:`on_webhooks_update`
        """
        return 1 << 5

    @flag_value
    def invites(self) -> int:
        """:class:`bool`: Whether guild invite related events are enabled.

        This corresponds to the following events:

        - :func:`on_invite_create`
        - :func:`on_invite_delete`
        """
        return 1 << 6

    @flag_value
    def voice_states(self) -> int:
        """:class:`bool`: Whether guild voice state related events are enabled.

        This corresponds to the following events:

        - :func:`on_voice_state_update`

        The bot's own voice state always arrives, so a voice client works without it.
        """
        return 1 << 7

    @flag_value
    def presences(self) -> int:
        """:class:`bool`: Whether guild presence related events are enabled.

        This corresponds to the following events:

        - :func:`on_presence_update`
        - :func:`on_raw_presence_update`

        This also corresponds to the following attributes and classes in terms of cache:

        - :attr:`Member.activities`
        - :attr:`Member.status`
        - :attr:`Member.raw_status`

        Without it, Bisim sends no presence at all, so every member reads as offline.

        .. note::

            This is a privileged intent: switch it on at https://bisim.gg/developers.
            Bots in 100 servers or more need Bisim's approval as well.
        """
        return 1 << 8

    @alias_flag_value
    def messages(self) -> int:
        """:class:`bool`: Whether guild and direct message related events are enabled.

        This is a shortcut to set or get both :attr:`guild_messages` and :attr:`dm_messages`.
        """
        return (1 << 9) | (1 << 12)

    @flag_value
    def guild_messages(self) -> int:
        """:class:`bool`: Whether guild message related events are enabled.

        This corresponds to the following events in servers:

        - :func:`on_message`
        - :func:`on_message_edit`
        - :func:`on_message_delete`
        - :func:`on_bulk_message_delete`
        - :func:`on_raw_message_edit`
        - :func:`on_raw_message_delete`
        - :func:`on_raw_bulk_message_delete`
        """
        return 1 << 9

    @flag_value
    def dm_messages(self) -> int:
        """:class:`bool`: Whether direct message related events are enabled.

        This corresponds to the same events as :attr:`guild_messages`, in DMs,
        and to :func:`on_private_channel_pins_update`.
        """
        return 1 << 12

    @alias_flag_value
    def reactions(self) -> int:
        """:class:`bool`: Whether guild and direct message reaction related events are enabled.

        This is a shortcut to set or get both :attr:`guild_reactions` and :attr:`dm_reactions`.
        """
        return (1 << 10) | (1 << 13)

    @flag_value
    def guild_reactions(self) -> int:
        """:class:`bool`: Whether guild message reaction related events are enabled.

        This corresponds to the following events in servers:

        - :func:`on_reaction_add`
        - :func:`on_reaction_remove`
        - :func:`on_reaction_clear`
        - :func:`on_raw_reaction_add`
        - :func:`on_raw_reaction_remove`
        - :func:`on_raw_reaction_clear`
        """
        return 1 << 10

    @flag_value
    def dm_reactions(self) -> int:
        """:class:`bool`: Whether direct message reaction related events are enabled.

        This corresponds to the same events as :attr:`guild_reactions`, in DMs.
        """
        return 1 << 13

    @alias_flag_value
    def typing(self) -> int:
        """:class:`bool`: Whether guild and direct message typing related events are enabled.

        This is a shortcut to set or get both :attr:`guild_typing` and :attr:`dm_typing`.
        """
        return (1 << 11) | (1 << 14)

    @flag_value
    def guild_typing(self) -> int:
        """:class:`bool`: Whether guild typing related events are enabled.

        This corresponds to :func:`on_typing` and :func:`on_raw_typing` in servers.
        """
        return 1 << 11

    @flag_value
    def dm_typing(self) -> int:
        """:class:`bool`: Whether direct message typing related events are enabled.

        This corresponds to :func:`on_typing` and :func:`on_raw_typing` in DMs.
        """
        return 1 << 14

    @flag_value
    def message_content(self) -> int:
        """:class:`bool`: Whether message content, attachments, embeds, components and polls will be available
        in messages which do not meet the following criteria:

        - The message was sent by the client
        - The message was sent in direct messages
        - The message mentions the client

        This applies to the message events and to messages read over REST
        (:meth:`abc.Messageable.history`, :meth:`abc.Messageable.fetch_message`,
        :meth:`abc.Messageable.pins`), and to :attr:`AutoModAction.content`.
        Without it such a message has an empty :attr:`Message.content` and no
        embeds, attachments, components or poll.

        .. note::

            This is a privileged intent: switch it on at https://bisim.gg/developers.
            Bots in 100 servers or more need Bisim's approval as well.
        """
        return 1 << 15

    @flag_value
    def guild_scheduled_events(self) -> int:
        """:class:`bool`: Whether guild scheduled event related events are enabled.

        Bisim has no scheduled events, so this changes nothing.
        """
        return 1 << 16

    @alias_flag_value
    def auto_moderation(self) -> int:
        """:class:`bool`: Whether auto moderation related events are enabled.

        This is a shortcut to set or get both :attr:`auto_moderation_configuration`
        and :attr:`auto_moderation_execution`.
        """
        return (1 << 20) | (1 << 21)

    @flag_value
    def auto_moderation_configuration(self) -> int:
        """:class:`bool`: Whether auto moderation configuration related events are enabled.

        This corresponds to the following events:

        - :func:`on_automod_rule_create`
        - :func:`on_automod_rule_update`
        - :func:`on_automod_rule_delete`
        """
        return 1 << 20

    @flag_value
    def auto_moderation_execution(self) -> int:
        """:class:`bool`: Whether auto moderation execution related events are enabled.

        This corresponds to the following events:

        - :func:`on_automod_action`
        """
        return 1 << 21

    @alias_flag_value
    def polls(self) -> int:
        """:class:`bool`: Whether guild and direct message poll related events are enabled.

        This is a shortcut to set or get both :attr:`guild_polls` and :attr:`dm_polls`.
        """
        return (1 << 24) | (1 << 25)

    @flag_value
    def guild_polls(self) -> int:
        """:class:`bool`: Whether guild poll related events are enabled.

        This corresponds to :func:`on_poll_vote_add`, :func:`on_poll_vote_remove`
        and their raw versions in servers.
        """
        return 1 << 24

    @flag_value
    def dm_polls(self) -> int:
        """:class:`bool`: Whether direct message poll related events are enabled.

        This corresponds to the same events as :attr:`guild_polls`, in DMs.
        """
        return 1 << 25


@fill_with_flags()
class MemberCacheFlags(BaseFlags):
    """Controls the library's cache policy when it comes to members (accepted for
    compatibility; Bisim's member cache always keeps every member it loads).
    """

    __slots__ = ()

    def __init__(self, **kwargs: bool):
        bits = max(self.VALID_FLAGS.values()).bit_length()
        self.value: int = (1 << bits) - 1
        for key, value in kwargs.items():
            if key not in self.VALID_FLAGS:
                raise TypeError(f'{key!r} is not a valid flag name.')
            setattr(self, key, value)

    @classmethod
    def all(cls) -> Self:
        """A factory method that creates a :class:`MemberCacheFlags` with everything enabled."""
        bits = max(cls.VALID_FLAGS.values()).bit_length()
        return cls._from_value((1 << bits) - 1)

    @classmethod
    def none(cls) -> Self:
        """A factory method that creates a :class:`MemberCacheFlags` with everything disabled."""
        return cls._from_value(cls.DEFAULT_VALUE)

    @classmethod
    def from_intents(cls, intents: Intents) -> Self:
        """A factory method that creates a :class:`MemberCacheFlags` based on the currently selected :class:`Intents`."""
        return cls.all()

    @property
    def _empty(self) -> bool:
        return self.value == self.DEFAULT_VALUE

    @flag_value
    def voice(self) -> int:
        """:class:`bool`: Whether to cache members that are in voice."""
        return 1

    @flag_value
    def joined(self) -> int:
        """:class:`bool`: Whether to cache members that joined the guild or are chunked."""
        return 2


@fill_with_flags()
class ChannelFlags(BaseFlags):
    """Wraps up the channel flags (kept for compatibility; Bisim sets none)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def pinned(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 1

    @flag_value
    def require_tag(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 4


@fill_with_flags()
class AttachmentFlags(BaseFlags):
    """Wraps up the attachment flags."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def clip(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 0

    @flag_value
    def thumbnail(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 1

    @flag_value
    def remix(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 2

    @flag_value
    def spoiler(self) -> int:
        """:class:`bool`: Returns ``True`` if the attachment is a spoiler."""
        return 1 << 3


@fill_with_flags()
class EmbedFlags(BaseFlags):
    """Wraps up the embed flags (kept for compatibility)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def contains_explicit_media(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 4


@fill_with_flags()
class MemberFlags(BaseFlags):
    """Wraps up the member flags (kept for compatibility)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def did_rejoin(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1

    @flag_value
    def completed_onboarding(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 2

    @flag_value
    def bypasses_verification(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 4

    @flag_value
    def started_onboarding(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 8


@fill_with_flags()
class RoleFlags(BaseFlags):
    """Wraps up the role flags (kept for compatibility)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def in_prompt(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1


@fill_with_flags()
class ApplicationFlags(BaseFlags):
    """Wraps up the application flags (kept for compatibility)."""

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def gateway_presence(self) -> int:
        """:class:`bool`: Always available on Bisim."""
        return 1 << 12

    @flag_value
    def gateway_guild_members(self) -> int:
        """:class:`bool`: Always available on Bisim."""
        return 1 << 14

    @flag_value
    def gateway_message_content(self) -> int:
        """:class:`bool`: Always available on Bisim."""
        return 1 << 18


@fill_with_flags()
class AppCommandContext(ArrayFlags):
    r"""Wraps up the Bisim :class:`~bisim.app_commands.Command` execution context.

    Bisim's contexts are ``GUILD`` and ``BOT_DM``: :attr:`guild` maps to the
    first, and :attr:`dm_channel` to the second. :attr:`private_channel`
    (group DMs and other people's DMs) has no Bisim counterpart and is left
    out when commands are synced.

    .. container:: operations

        .. describe:: x == y

            Checks if two AppCommandContext flags are equal.

        .. describe:: x != y

            Checks if two AppCommandContext flags are not equal.

        .. describe:: x | y, x |= y

            Returns an AppCommandContext instance with all enabled flags from
            both x and y.

        .. describe:: x & y, x &= y

            Returns an AppCommandContext instance with only flags enabled on
            both x and y.

    Attributes
    -----------
    value: :class:`int`
        The raw value. You should query flags via the properties
        rather than using this raw value.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def guild(self) -> int:
        """:class:`bool`: Whether the context allows usage in a server."""
        return 1 << 0

    @flag_value
    def dm_channel(self) -> int:
        """:class:`bool`: Whether the context allows usage in the DM with the bot."""
        return 1 << 1

    @flag_value
    def private_channel(self) -> int:
        """:class:`bool`: Not on Bisim (dropped when syncing)."""
        return 1 << 2

    def to_bisim(self) -> List[str]:
        """List[:class:`str`]: The contexts as Bisim names (``GUILD``, ``BOT_DM``)."""
        result = []
        if self.guild:
            result.append('GUILD')
        if self.dm_channel:
            result.append('BOT_DM')
        return result

    @classmethod
    def from_bisim(cls, values: Any) -> Self:
        self = cls._from_value(0)
        for value in values or ():
            name = str(value).upper()
            if name in ('GUILD', '0'):
                self.guild = True
            elif name in ('BOT_DM', 'DM', '1'):
                self.dm_channel = True
            elif name in ('PRIVATE_CHANNEL', '2'):
                self.private_channel = True
        return self


@fill_with_flags()
class AppInstallationType(ArrayFlags):
    r"""Represents the installation location of an application command.

    Bisim apps are always installed to servers; :attr:`user` is accepted and
    ignored.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @flag_value
    def guild(self) -> int:
        """:class:`bool`: Whether the integration is a guild install."""
        return 1 << 0

    @flag_value
    def user(self) -> int:
        """:class:`bool`: Not on Bisim."""
        return 1 << 1


_AUTOMOD_PRESET_NAMES = ('PROFANITY', 'SEXUAL', 'SLURS')


@fill_with_flags()
class AutoModPresets(ArrayFlags):
    r"""Wraps up the :class:`AutoModRule` presets.

    Bisim's presets map to Discord's: ``PROFANITY`` is :attr:`profanity`,
    ``SEXUAL`` is :attr:`sexual_content` and ``SLURS`` is :attr:`slurs`.

    .. container:: operations

        .. describe:: x == y

            Checks if two AutoMod preset flags are equal.
        .. describe:: x != y

            Checks if two AutoMod preset flags are not equal.
        .. describe:: x | y, x |= y

            Returns an AutoModPresets instance with all enabled flags from
            both x and y.
        .. describe:: x & y, x &= y

            Returns an AutoModPresets instance with only flags enabled on
            both x and y.
        .. describe:: hash(x)

            Return the flag's hash.
        .. describe:: iter(x)

            Returns an iterator of ``(name, value)`` pairs.

    Attributes
    -----------
    value: :class:`int`
        The raw value. You should query flags via the properties
        rather than using this raw value.
    """

    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool):
        super().__init__(**kwargs)
        if value:
            self.value = value

    @classmethod
    def _from_bisim(cls, names: Any) -> Self:
        value = 0
        for name in names or ():
            if isinstance(name, int):
                value |= 1 << (name - 1)
                continue
            try:
                value |= 1 << _AUTOMOD_PRESET_NAMES.index(str(name).upper())
            except ValueError:
                pass
        return cls._from_value(value)

    def _to_bisim(self) -> List[str]:
        return [name for index, name in enumerate(_AUTOMOD_PRESET_NAMES) if self.value & (1 << index)]

    def to_array(self) -> List[int]:
        """List[:class:`int`]: Discord's numbers of the presets that are on (1, 2 and 3)."""
        return [index + 1 for index in range(len(_AUTOMOD_PRESET_NAMES)) if self.value & (1 << index)]

    @flag_value
    def profanity(self) -> int:
        """:class:`bool`: Whether to use the preset profanity filter."""
        return 1 << 0

    @flag_value
    def sexual_content(self) -> int:
        """:class:`bool`: Whether to use the preset sexual content filter."""
        return 1 << 1

    @flag_value
    def slurs(self) -> int:
        """:class:`bool`: Whether to use the preset slurs filter."""
        return 1 << 2
