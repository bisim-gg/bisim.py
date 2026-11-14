"""Permissions, with Discord's bit numbers (Bisim uses the same ones)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar, Dict, Iterator, Optional, Set, Tuple

from .flags import BaseFlags, alias_flag_value, fill_with_flags, flag_value

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    'Permissions',
    'PermissionOverwrite',
)


def _bits(*names: str) -> int:
    value = 0
    for name in names:
        value |= Permissions.VALID_FLAGS[name]
    return value


class permission_alias(alias_flag_value):
    alias: str


def make_permission_alias(alias: str) -> Callable[[Callable[[Any], int]], permission_alias]:
    def decorator(func: Callable[[Any], int]) -> permission_alias:
        ret = permission_alias(func)
        ret.alias = alias
        return ret

    return decorator


@fill_with_flags()
class Permissions(BaseFlags):
    """Wraps up the Bisim permission value.

    The properties provided are two way. You can set and retrieve individual
    bits using the properties as if they were regular bools. This allows
    you to edit permissions.

    The bit numbers are Discord's, which Bisim uses as well; the permissions
    for features Bisim does not have (threads, stages, events) are kept so
    the numbers line up and existing code runs.

    .. container:: operations

        .. describe:: x == y

            Checks if two permissions are equal.
        .. describe:: x != y

            Checks if two permissions are not equal.
        .. describe:: x <= y

            Checks if a permission is a subset of another permission.
        .. describe:: x >= y

            Checks if a permission is a superset of another permission.
        .. describe:: x < y

             Checks if a permission is a strict subset of another permission.
        .. describe:: x > y

             Checks if a permission is a strict superset of another permission.
        .. describe:: x | y, x |= y

            Returns a Permissions instance with all enabled flags from
            both x and y.
        .. describe:: x & y, x &= y

            Returns a Permissions instance with only flags enabled on
            both x and y.
        .. describe:: x ^ y, x ^= y

            Returns a Permissions instance with only flags enabled on
            only one of x or y, not on both.
        .. describe:: ~x

            Returns a Permissions instance with all flags inverted from x.
        .. describe:: hash(x)

               Return the permission's hash.
        .. describe:: iter(x)

               Returns an iterator of ``(perm, value)`` pairs. This allows it
               to be, for example, constructed as a dict or a list of pairs.
               Note that aliases are not shown.
        .. describe:: bool(b)

            Returns whether the permissions object has any permissions set to ``True``.

    Attributes
    -----------
    value: :class:`int`
        The raw value. This value is a bit array field of a 53-bit integer
        representing the currently available permissions. You should query
        permissions via the properties rather than using this raw value.
    """

    __slots__ = ()

    def __init__(self, permissions: int = 0, **kwargs: bool):
        if not isinstance(permissions, int):
            raise TypeError(f'Expected int parameter, received {permissions.__class__.__name__} instead.')
        self.value = permissions
        for key, value in kwargs.items():
            try:
                flag = self.VALID_FLAGS[key]
            except KeyError:
                raise TypeError(f'{key!r} is not a valid permission name.') from None
            else:
                self._set_flag(flag, value)

    def is_subset(self, other: Permissions) -> bool:
        """Returns ``True`` if self has the same or fewer permissions as other."""
        if isinstance(other, Permissions):
            return (self.value & other.value) == self.value
        raise TypeError(f'cannot compare {self.__class__.__name__} with {other.__class__.__name__}')

    def is_superset(self, other: Permissions) -> bool:
        """Returns ``True`` if self has the same or more permissions as other."""
        if isinstance(other, Permissions):
            return (self.value | other.value) == self.value
        raise TypeError(f'cannot compare {self.__class__.__name__} with {other.__class__.__name__}')

    def is_strict_subset(self, other: Permissions) -> bool:
        """Returns ``True`` if the permissions on other are a strict subset of those on self."""
        return self.is_subset(other) and self != other

    def is_strict_superset(self, other: Permissions) -> bool:
        """Returns ``True`` if the permissions on other are a strict superset of those on self."""
        return self.is_superset(other) and self != other

    __le__ = is_subset
    __ge__ = is_superset
    __lt__ = is_strict_subset
    __gt__ = is_strict_superset

    def __bool__(self) -> bool:
        return self.value != 0

    @classmethod
    def none(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        permissions set to ``False``."""
        return cls(0)

    @classmethod
    def all(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        permissions set to ``True``.
        """
        value = 0
        for name, flag in cls.VALID_FLAGS.items():
            value |= flag
        return cls(value)

    @classmethod
    def _timeout_mask(cls) -> int:
        allowed = cls(_bits('view_channel', 'read_message_history'))
        return ~(cls.all().value & ~allowed.value)

    @classmethod
    def _dm_permissions(cls) -> Self:
        base = cls.text()
        base.read_messages = True
        base.send_tts_messages = False
        base.manage_messages = False
        base.pin_messages = True
        base.create_private_threads = False
        base.create_public_threads = False
        base.manage_threads = False
        base.send_messages_in_threads = False
        base.bypass_slowmode = False
        return base

    @classmethod
    def all_channel(cls) -> Self:
        """A :class:`Permissions` with all channel-specific permissions set to
        ``True`` and the guild-specific ones set to ``False``. The guild-specific
        permissions are currently:

        - :attr:`manage_expressions`
        - :attr:`view_audit_log`
        - :attr:`view_guild_insights`
        - :attr:`view_creator_monetization_analytics`
        - :attr:`manage_guild`
        - :attr:`change_nickname`
        - :attr:`manage_nicknames`
        - :attr:`kick_members`
        - :attr:`ban_members`
        - :attr:`administrator`
        - :attr:`create_expressions`
        - :attr:`moderate_members`
        - :attr:`create_events`
        - :attr:`manage_events`
        - :attr:`set_voice_channel_status`
        """
        return cls(
            _bits(
                'create_instant_invite', 'manage_channels', 'add_reactions', 'priority_speaker', 'stream',
                'view_channel', 'send_messages', 'send_tts_messages', 'manage_messages', 'embed_links',
                'attach_files', 'read_message_history', 'mention_everyone', 'external_emojis', 'connect',
                'speak', 'mute_members', 'deafen_members', 'move_members', 'use_voice_activation',
                'manage_roles', 'manage_webhooks', 'use_application_commands', 'request_to_speak',
                'manage_threads', 'create_public_threads', 'create_private_threads', 'external_stickers',
                'send_messages_in_threads', 'use_embedded_activities', 'use_soundboard',
                'use_external_sounds', 'send_voice_messages', 'send_polls', 'use_external_apps',
                'pin_messages', 'bypass_slowmode',
            )
        )

    @classmethod
    def general(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "General" permissions from the official Discord UI set to ``True``.
        """
        return cls(
            _bits(
                'manage_channels', 'manage_guild', 'view_audit_log', 'view_channel', 'view_guild_insights',
                'manage_roles', 'manage_webhooks', 'manage_expressions', 'view_creator_monetization_analytics',
                'create_expressions',
            )
        )

    @classmethod
    def membership(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Membership" permissions set to ``True``.
        """
        return cls(
            _bits('create_instant_invite', 'kick_members', 'ban_members', 'change_nickname', 'manage_nicknames', 'moderate_members')
        )

    @classmethod
    def text(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Text" permissions set to ``True``.
        """
        return cls(
            _bits(
                'add_reactions', 'send_messages', 'send_tts_messages', 'manage_messages', 'embed_links',
                'attach_files', 'read_message_history', 'mention_everyone', 'external_emojis',
                'use_application_commands', 'manage_threads', 'create_public_threads', 'create_private_threads',
                'external_stickers', 'send_messages_in_threads', 'send_voice_messages', 'send_polls',
                'use_external_apps', 'pin_messages', 'bypass_slowmode',
            )
        )

    @classmethod
    def voice(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Voice" permissions set to ``True``."""
        return cls(
            _bits(
                'priority_speaker', 'stream', 'connect', 'speak', 'mute_members', 'deafen_members',
                'move_members', 'use_voice_activation', 'use_embedded_activities', 'use_soundboard',
                'use_external_sounds', 'set_voice_channel_status',
            )
        )

    @classmethod
    def stage(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Stage Channel" permissions set to ``True`` (no stages on Bisim)."""
        return cls(_bits('request_to_speak'))

    @classmethod
    def stage_moderator(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all permissions
        for stage moderators set to ``True`` (no stages on Bisim)."""
        return cls(_bits('manage_channels', 'mute_members', 'move_members'))

    @classmethod
    def elevated(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all permissions
        that require 2FA set to ``True``. These permissions are currently:

        - :attr:`kick_members`
        - :attr:`ban_members`
        - :attr:`administrator`
        - :attr:`manage_channels`
        - :attr:`manage_guild`
        - :attr:`manage_messages`
        - :attr:`manage_roles`
        - :attr:`manage_webhooks`
        - :attr:`manage_expressions`
        - :attr:`manage_threads`
        - :attr:`moderate_members`
        """
        return cls(
            _bits(
                'kick_members', 'ban_members', 'administrator', 'manage_channels', 'manage_guild',
                'manage_messages', 'manage_roles', 'manage_webhooks', 'manage_expressions', 'manage_threads',
                'moderate_members',
            )
        )

    @classmethod
    def apps(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Apps" permissions set to ``True``.
        """
        return cls(_bits('use_application_commands', 'use_embedded_activities', 'use_external_apps'))

    @classmethod
    def events(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Events" permissions set to ``True`` (no events on Bisim).
        """
        return cls(_bits('manage_events', 'create_events'))

    @classmethod
    def advanced(cls) -> Self:
        """A factory method that creates a :class:`Permissions` with all
        "Advanced" permissions set to ``True``.
        """
        return cls(_bits('administrator'))

    def update(self, **kwargs: bool) -> None:
        r"""Bulk updates this permission object.

        Allows you to set multiple attributes by using keyword
        arguments. The names must be equivalent to the properties
        listed. Extraneous key/value pairs will be silently ignored.

        Parameters
        ------------
        \*\*kwargs
            A list of key/value pairs to bulk update permissions with.
        """
        for key, value in kwargs.items():
            flag = self.VALID_FLAGS.get(key)
            if flag is not None:
                self._set_flag(flag, value)

    def handle_overwrite(self, allow: int, deny: int) -> None:
        # Denies are applied first, then allows, as Discord does.
        self.value = (self.value & ~deny) | allow

    @flag_value
    def create_instant_invite(self) -> int:
        """:class:`bool`: Returns ``True`` if the user can create instant invites."""
        return 1 << 0

    @flag_value
    def kick_members(self) -> int:
        """:class:`bool`: Returns ``True`` if the user can kick users from the guild."""
        return 1 << 1

    @flag_value
    def ban_members(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can ban users from the guild."""
        return 1 << 2

    @flag_value
    def administrator(self) -> int:
        """:class:`bool`: Returns ``True`` if a user is an administrator. This role overrides all other permissions.

        This also bypasses all channel-specific overrides.
        """
        return 1 << 3

    @flag_value
    def manage_channels(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can edit, delete, or create channels in the guild.

        This also corresponds to the "Manage Channel" channel-specific override."""
        return 1 << 4

    @flag_value
    def manage_guild(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can edit guild properties."""
        return 1 << 5

    @flag_value
    def add_reactions(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can add reactions to messages."""
        return 1 << 6

    @flag_value
    def view_audit_log(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can view the guild's audit log."""
        return 1 << 7

    @flag_value
    def priority_speaker(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can be more easily heard while talking."""
        return 1 << 8

    @flag_value
    def stream(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can stream in a voice channel."""
        return 1 << 9

    @flag_value
    def read_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can read messages from all or specific text channels."""
        return 1 << 10

    @make_permission_alias('read_messages')
    def view_channel(self) -> int:
        """:class:`bool`: An alias for :attr:`read_messages`."""
        return 1 << 10

    @flag_value
    def send_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send messages from all or specific text channels."""
        return 1 << 11

    @flag_value
    def send_tts_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send TTS messages (no TTS on Bisim)."""
        return 1 << 12

    @flag_value
    def manage_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can delete or pin messages in a text channel.

        .. note::

            Note that there are currently no ways to edit other people's messages.
        """
        return 1 << 13

    @flag_value
    def embed_links(self) -> int:
        """:class:`bool`: Returns ``True`` if a user's messages will automatically be embedded by Bisim."""
        return 1 << 14

    @flag_value
    def attach_files(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send files in their messages."""
        return 1 << 15

    @flag_value
    def read_message_history(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can read a text channel's previous messages."""
        return 1 << 16

    @flag_value
    def mention_everyone(self) -> int:
        """:class:`bool`: Returns ``True`` if a user's @everyone or @here will mention everyone in the text channel."""
        return 1 << 17

    @flag_value
    def external_emojis(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use emojis from other guilds."""
        return 1 << 18

    @make_permission_alias('external_emojis')
    def use_external_emojis(self) -> int:
        """:class:`bool`: An alias for :attr:`external_emojis`."""
        return 1 << 18

    @flag_value
    def view_guild_insights(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can view the guild's insights."""
        return 1 << 19

    @flag_value
    def connect(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can connect to a voice channel."""
        return 1 << 20

    @flag_value
    def speak(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can speak in a voice channel."""
        return 1 << 21

    @flag_value
    def mute_members(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can mute other users."""
        return 1 << 22

    @flag_value
    def deafen_members(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can deafen other users."""
        return 1 << 23

    @flag_value
    def move_members(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can move users between other voice channels."""
        return 1 << 24

    @flag_value
    def use_voice_activation(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use voice activation in voice channels."""
        return 1 << 25

    @flag_value
    def change_nickname(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can change their nickname in the guild."""
        return 1 << 26

    @flag_value
    def manage_nicknames(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can change other user's nickname in the guild."""
        return 1 << 27

    @flag_value
    def manage_roles(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create or edit roles less than their role's position.

        This also corresponds to the "Manage Permissions" channel-specific override.
        """
        return 1 << 28

    @make_permission_alias('manage_roles')
    def manage_permissions(self) -> int:
        """:class:`bool`: An alias for :attr:`manage_roles`."""
        return 1 << 28

    @flag_value
    def manage_webhooks(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create, edit, or delete webhooks."""
        return 1 << 29

    @flag_value
    def manage_expressions(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can edit or delete emojis, stickers, and soundboard sounds."""
        return 1 << 30

    @make_permission_alias('manage_expressions')
    def manage_emojis(self) -> int:
        """:class:`bool`: An alias for :attr:`manage_expressions`."""
        return 1 << 30

    @make_permission_alias('manage_expressions')
    def manage_emojis_and_stickers(self) -> int:
        """:class:`bool`: An alias for :attr:`manage_expressions`."""
        return 1 << 30

    @flag_value
    def use_application_commands(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use slash commands."""
        return 1 << 31

    @flag_value
    def request_to_speak(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can request to speak in a stage channel (no stages on Bisim)."""
        return 1 << 32

    @flag_value
    def manage_events(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can manage guild events (no events on Bisim)."""
        return 1 << 33

    @flag_value
    def manage_threads(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can manage threads (no threads on Bisim)."""
        return 1 << 34

    @flag_value
    def create_public_threads(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create public threads (no threads on Bisim)."""
        return 1 << 35

    @flag_value
    def create_private_threads(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create private threads (no threads on Bisim)."""
        return 1 << 36

    @flag_value
    def external_stickers(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use stickers from other guilds."""
        return 1 << 37

    @make_permission_alias('external_stickers')
    def use_external_stickers(self) -> int:
        """:class:`bool`: An alias for :attr:`external_stickers`."""
        return 1 << 37

    @flag_value
    def send_messages_in_threads(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send messages in threads (no threads on Bisim)."""
        return 1 << 38

    @flag_value
    def use_embedded_activities(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can launch an embedded application in a Voice channel."""
        return 1 << 39

    @flag_value
    def moderate_members(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can time out other members."""
        return 1 << 40

    @flag_value
    def view_creator_monetization_analytics(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can view role subscription insights (not on Bisim)."""
        return 1 << 41

    @flag_value
    def use_soundboard(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use the soundboard."""
        return 1 << 42

    @flag_value
    def create_expressions(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create emojis, stickers, and soundboard sounds."""
        return 1 << 43

    @flag_value
    def create_events(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can create guild events (no events on Bisim)."""
        return 1 << 44

    @flag_value
    def use_external_sounds(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use sounds from other guilds."""
        return 1 << 45

    @flag_value
    def send_voice_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send voice messages."""
        return 1 << 46

    @flag_value
    def set_voice_channel_status(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can set the status of voice channels."""
        return 1 << 48

    @flag_value
    def send_polls(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can send poll messages."""
        return 1 << 49

    @make_permission_alias('send_polls')
    def create_polls(self) -> int:
        """:class:`bool`: An alias for :attr:`send_polls`."""
        return 1 << 49

    @flag_value
    def use_external_apps(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can use external apps."""
        return 1 << 50

    @flag_value
    def pin_messages(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can pin messages."""
        return 1 << 51

    @flag_value
    def bypass_slowmode(self) -> int:
        """:class:`bool`: Returns ``True`` if a user can bypass slowmode."""
        return 1 << 52


def _permission_names() -> Tuple[str, ...]:
    return tuple(Permissions.VALID_FLAGS)


class PermissionOverwrite:
    r"""A type that is used to represent a channel specific permission.

    Unlike a regular :class:`Permissions`\, the default value of a
    permission is equivalent to ``None`` and not ``False``. Setting
    a value to ``False`` is **explicitly** denying that permission,
    while setting a value to ``True`` is **explicitly** allowing
    that permission.

    The values supported by this are the same as :class:`Permissions`
    with the added possibility of it being set to ``None``.

    .. container:: operations

        .. describe:: x == y

            Checks if two overwrites are equal.
        .. describe:: x != y

            Checks if two overwrites are not equal.
        .. describe:: iter(x)

           Returns an iterator of ``(perm, value)`` pairs. This allows it
           to be, for example, constructed as a dict or a list of pairs.
           Note that aliases are not shown.

    Parameters
    -----------
    \*\*kwargs
        Set the value of permissions by their name.
    """

    __slots__ = ('_values',)

    VALID_NAMES: ClassVar[Set[str]] = set(Permissions.VALID_FLAGS)
    PURE_FLAGS: ClassVar[Set[str]] = set(Permissions._PUBLIC_FLAGS)

    def __init__(self, **kwargs: Optional[bool]):
        object.__setattr__(self, '_values', {})
        for key, value in kwargs.items():
            if key not in self.VALID_NAMES:
                raise ValueError(f'no permission called {key}.')
            setattr(self, key, value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PermissionOverwrite) and self._canonical() == other._canonical()

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    __hash__ = None  # type: ignore

    def _canonical(self) -> Dict[int, Optional[bool]]:
        result: Dict[int, Optional[bool]] = {}
        for name, value in self._values.items():
            if value is not None:
                result[Permissions.VALID_FLAGS[name]] = value
        return result

    def __getattr__(self, name: str) -> Optional[bool]:
        if name in PermissionOverwrite.VALID_NAMES:
            values = object.__getattribute__(self, '_values')
            flag = Permissions.VALID_FLAGS[name]
            for other, value in values.items():
                if Permissions.VALID_FLAGS[other] == flag:
                    return value
            return None
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Optional[bool]) -> None:
        if name not in self.VALID_NAMES:
            raise AttributeError(f'no permission called {name}.')
        if value not in (True, None, False):
            raise TypeError(f'Expected bool or NoneType, received {value.__class__.__name__}')
        flag = Permissions.VALID_FLAGS[name]
        # Aliases share one entry, keyed by the canonical name.
        canonical = next(n for n in Permissions._PUBLIC_FLAGS if Permissions.VALID_FLAGS[n] == flag)
        for other in [k for k in self._values if Permissions.VALID_FLAGS[k] == flag]:
            del self._values[other]
        self._values[canonical] = value

    def __repr__(self) -> str:
        set_values = {name: value for name, value in self._values.items() if value is not None}
        return f'<PermissionOverwrite {set_values}>'

    def pair(self) -> Tuple[Permissions, Permissions]:
        """Tuple[:class:`Permissions`, :class:`Permissions`]: Returns the (allow, deny) pair from this overwrite."""
        allow = Permissions.none()
        deny = Permissions.none()
        for key, value in self._values.items():
            if value is True:
                setattr(allow, key, True)
            elif value is False:
                setattr(deny, key, True)
        return allow, deny

    @classmethod
    def from_pair(cls, allow: Permissions, deny: Permissions) -> Self:
        """Creates an overwrite from an allow/deny pair of :class:`Permissions`."""
        ret = cls()
        for key, value in allow:
            if value is True:
                setattr(ret, key, True)
        for key, value in deny:
            if value is True:
                setattr(ret, key, False)
        return ret

    def is_empty(self) -> bool:
        """Checks if the permission overwrite is currently empty.

        An empty permission overwrite is one that has no overwrites set
        to ``True`` or ``False``.

        Returns
        -------
        :class:`bool`
            Indicates if the overwrite is empty.
        """
        return all(value is None for value in self._values.values())

    def update(self, **kwargs: Optional[bool]) -> None:
        r"""Bulk updates this permission overwrite object.

        Allows you to set multiple attributes by using keyword
        arguments. The names must be equivalent to the properties
        listed. Extraneous key/value pairs will be silently ignored.

        Parameters
        ------------
        \*\*kwargs
            A list of key/value pairs to bulk update with.
        """
        for key, value in kwargs.items():
            if key not in self.VALID_NAMES:
                continue
            setattr(self, key, value)

    def __iter__(self) -> Iterator[Tuple[str, Optional[bool]]]:
        for key in Permissions._PUBLIC_FLAGS:
            yield key, self._values.get(key)
