from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, NamedTuple, Optional, Tuple, Union

from .. import utils
from ..enums import AppCommandOptionType, AppCommandType, ChannelType, Locale
from ..member import Member
from ..message import Attachment, Message
from ..object import Object
from ..role import Role
from ..user import User
from .models import AppCommandChannel

if TYPE_CHECKING:
    from ..interactions import Interaction

__all__ = ('Namespace',)


class ResolveKey(NamedTuple):
    id: str
    type: int

    @classmethod
    def any_with(cls, id: str) -> ResolveKey:
        return ResolveKey(id=id, type=-1)

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, ResolveKey):
            return NotImplemented
        if self.type == -1 or o.type == -1:
            return self.id == o.id
        return (self.id, self.type) == (o.id, o.type)

    def __hash__(self) -> int:
        # Most of the time an ID is unique anyway.
        return hash(self.id)


def _lookup(resolved: Dict[str, Any], key: str, item_id: str) -> Optional[Dict[str, Any]]:
    bucket = resolved.get(key)
    if isinstance(bucket, dict):
        found = bucket.get(item_id)
        return found if isinstance(found, dict) else None
    if isinstance(bucket, list):
        for entry in bucket:
            if isinstance(entry, dict) and str(entry.get('id') or entry.get('userId')) == item_id:
                return entry
    return None


class Namespace:
    """An object that holds the parameters being passed to a command in a mostly raw state.

    This class is deliberately simple and just holds the option name and resolved value as a simple
    key-pair mapping. These keys correspond to the names of the parameters as Bisim knows them.

    The values given are: Members (in a server) or Users for user options,
    Roles, channels, :class:`~bisim.Attachment`, and the plain ``str``,
    ``int``, ``float`` and ``bool`` values.

    .. container:: operations

        .. describe:: x == y

            Checks if two namespaces are equal by checking if all attributes are equal.
        .. describe:: x != y

            Checks if two namespaces are not equal.
        .. describe:: x[key]

            Returns an attribute if it is found, otherwise raises
            a :exc:`KeyError`.
        .. describe:: key in x

            Checks if the attribute is in the namespace.
        .. describe:: iter(x)

           Returns an iterator of ``(name, value)`` pairs. This allows it
           to be, for example, constructed as a dict or a list of pairs.

    This namespace object converts resolved items into their appropriate form depending on their
    type. Consult the table below for conversion information.

    +-------------------------------------------+-------------------------------------------------------------------------------+
    |                Option Type                |                                 Resolved Type                                 |
    +===========================================+===============================================================================+
    | :attr:`.AppCommandOptionType.string`      | :class:`str`                                                                  |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.integer`     | :class:`int`                                                                  |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.boolean`     | :class:`bool`                                                                 |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.number`      | :class:`float`                                                                |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.user`        | :class:`~bisim.User` or :class:`~bisim.Member`                                |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.channel`     | :class:`~bisim.abc.GuildChannel` or :class:`.AppCommandChannel`               |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.role`        | :class:`~bisim.Role`                                                          |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.mentionable` | :class:`~bisim.User` or :class:`~bisim.Member`, or :class:`~bisim.Role`       |
    +-------------------------------------------+-------------------------------------------------------------------------------+
    | :attr:`.AppCommandOptionType.attachment`  | :class:`~bisim.Attachment`                                                    |
    +-------------------------------------------+-------------------------------------------------------------------------------+

    .. note::

        In autocomplete interactions, the namespace might not be validated or filled in. Bisim does not
        send the resolved data as well, so this means that certain fields end up just as IDs rather than
        the resolved data. In these cases, a :class:`bisim.Object` is returned instead.

        If an attribute is not given, then ``None`` is returned rather than raising
        :exc:`AttributeError`.
    """

    def __init__(self, interaction: Interaction[Any], resolved: Dict[str, Any], options: List[Dict[str, Any]]):
        completed = self._get_resolved_items(interaction, resolved or {})
        for option in options:
            opt_type = AppCommandOptionType.from_bisim(option.get('type'))
            name = option['name']
            value = option.get('value')
            kind = getattr(opt_type, 'value', 0)
            if kind in (3, 4, 5):  # string, integer, boolean
                if kind == 4 and isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                elif kind == 5 and isinstance(value, str):
                    value = value.lower() == 'true'
                self.__dict__[name] = value
            elif kind == 10:  # number
                if value is None or value == '':
                    self.__dict__[name] = float('nan')
                else:
                    try:
                        self.__dict__[name] = float(value)
                    except (TypeError, ValueError):
                        self.__dict__[name] = value
            elif kind in (6, 7, 8, 9, 11):
                if value is None:
                    self.__dict__[name] = None
                    continue
                key = ResolveKey(id=str(value), type=kind)
                try:
                    self.__dict__[name] = completed[key]
                except KeyError:
                    self.__dict__[name] = self._fallback(interaction, str(value), kind)
            else:
                self.__dict__[name] = value

    @classmethod
    def _fallback(cls, interaction: Interaction[Any], value: str, kind: int) -> Any:
        """Resolves an id from the cache when Bisim did not send resolved data."""
        state = interaction._state
        guild = interaction.guild
        try:
            object_id = int(value)
        except ValueError:
            return value
        if kind in (6, 9):
            if guild is not None:
                member = guild.get_member(object_id)
                if member is not None:
                    return member
            user = state.get_user(object_id)
            if user is not None:
                return user
        if kind in (8, 9) and guild is not None:
            role = guild.get_role(object_id)
            if role is not None:
                return role
        if kind == 7:
            channel = state.get_channel(object_id)
            if channel is not None:
                return channel
        if kind == 11:
            return Object(id=object_id, type=Attachment)
        if kind == 8:
            return Object(id=object_id, type=Role)
        if kind == 6:
            return Object(id=object_id, type=User)
        return Object(id=object_id)

    @classmethod
    def _get_resolved_items(cls, interaction: Interaction[Any], resolved: Dict[str, Any]) -> Dict[ResolveKey, Any]:
        completed: Dict[ResolveKey, Any] = {}
        state = interaction._state
        guild = interaction.guild

        def entries(key: str) -> List[Tuple[str, Dict[str, Any]]]:
            bucket = resolved.get(key)
            if isinstance(bucket, dict):
                return [(str(k), v) for k, v in bucket.items() if isinstance(v, dict)]
            if isinstance(bucket, list):
                out = []
                for entry in bucket:
                    if isinstance(entry, dict):
                        out.append((str(entry.get('id') or entry.get('userId')), entry))
                return out
            return []

        members = dict(entries('members'))
        for user_id, user_data in entries('users'):
            member_data = members.get(user_id)
            if member_data is not None and guild is not None:
                cached = guild.get_member(int(user_id))
                if cached is not None:
                    item: Any = cached
                else:
                    payload = dict(member_data)
                    payload.setdefault('userId', user_id)
                    payload.setdefault('user', user_data)
                    item = Member(data=payload, guild=guild, state=state)
            else:
                item = state.store_user(user_data)
            completed[ResolveKey(id=user_id, type=6)] = item

        for user_id, member_data in members.items():
            key = ResolveKey(id=user_id, type=6)
            if key in completed or guild is None:
                continue
            cached = guild.get_member(int(user_id))
            if cached is not None:
                completed[key] = cached
            else:
                payload = dict(member_data)
                payload.setdefault('userId', user_id)
                completed[key] = Member(data=payload, guild=guild, state=state)

        if guild is not None:
            for role_id, role_data in entries('roles'):
                cached_role = guild.get_role(int(role_id))
                completed[ResolveKey(id=role_id, type=8)] = cached_role or Role(guild=guild, state=state, data=role_data)

        for channel_id, channel_data in entries('channels'):
            cached_channel = state.get_channel(int(channel_id))
            if cached_channel is not None:
                completed[ResolveKey(id=channel_id, type=7)] = cached_channel
            else:
                completed[ResolveKey(id=channel_id, type=7)] = AppCommandChannel(
                    state=state, data=channel_data, guild_id=interaction.guild_id or 0
                )

        for attachment_id, attachment_data in entries('attachments'):
            completed[ResolveKey(id=attachment_id, type=11)] = Attachment(data=attachment_data, state=state)

        for message_id, message_data in entries('messages'):
            channel = interaction.channel
            completed[ResolveKey(id=message_id, type=-1)] = Message(state=state, channel=channel, data=message_data)  # type: ignore

        # Mentionable options take a user or a role.
        for key, value in list(completed.items()):
            if key.type in (6, 8):
                completed.setdefault(ResolveKey(id=key.id, type=9), value)

        return completed

    def __repr__(self) -> str:
        items = (f'{k}={v!r}' for k, v in self.__dict__.items())
        return '<{} {}>'.format(self.__class__.__name__, ' '.join(items))

    def __eq__(self, other: object) -> bool:
        if isinstance(self, Namespace) and isinstance(other, Namespace):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __getitem__(self, key: str) -> Any:
        return self.__dict__[key]

    def __contains__(self, key: str) -> Any:
        return key in self.__dict__

    def __getattr__(self, attr: str) -> Any:
        return None

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        yield from self.__dict__.items()

    def _update_with_defaults(self, defaults: Iterator[Tuple[str, Any]]) -> None:
        for key, value in defaults:
            self.__dict__.setdefault(key, value)
