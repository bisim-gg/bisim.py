from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from . import utils
from .asset import Asset
from .colour import Colour
from .errors import NotSupported
from .flags import RoleFlags
from .mixins import Hashable
from .permissions import Permissions

if TYPE_CHECKING:
    from datetime import datetime

    from .guild import Guild
    from .member import Member
    from .state import ConnectionState

__all__ = (
    'RoleTags',
    'Role',
)


class RoleTags:
    """Represents tags on a role.

    On Bisim the only tag is the one a bot's own role carries: :attr:`bot_id`.

    Attributes
    ------------
    bot_id: Optional[:class:`int`]
        The bot's user ID that manages this role.
    integration_id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    subscription_listing_id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    """

    __slots__ = ('bot_id', 'integration_id', 'subscription_listing_id')

    def __init__(self, data: Dict[str, Any]):
        self.bot_id: Optional[int] = utils._snowflake(data.get('botId') or data.get('bot_id'))
        self.integration_id: Optional[int] = None
        self.subscription_listing_id: Optional[int] = None

    def is_bot_managed(self) -> bool:
        """:class:`bool`: Whether the role is associated with a bot."""
        return self.bot_id is not None

    def is_premium_subscriber(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def is_integration(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def is_available_for_purchase(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def is_guild_connection(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def __repr__(self) -> str:
        return f'<RoleTags bot_id={self.bot_id}>'


class Role(Hashable):
    """Represents a Bisim role in a :class:`Guild`.

    .. container:: operations

        .. describe:: x == y

            Checks if two roles are equal.

        .. describe:: x != y

            Checks if two roles are not equal.

        .. describe:: x > y

            Checks if a role is higher than another in the hierarchy.

        .. describe:: x < y

            Checks if a role is lower than another in the hierarchy.

        .. describe:: x >= y

            Checks if a role is higher or equal to another in the hierarchy.

        .. describe:: x <= y

            Checks if a role is lower or equal to another in the hierarchy.

        .. describe:: hash(x)

            Return the role's hash.

        .. describe:: str(x)

            Returns the role's name.

    Attributes
    ----------
    id: :class:`int`
        The ID for the role.
    name: :class:`str`
        The name of the role.
    guild: :class:`Guild`
        The guild the role belongs to.
    hoist: :class:`bool`
         Indicates if the role will be displayed separately from other members.
    position: :class:`int`
        The position of the role. This number is usually positive. The bottom
        role has a position of 0.
    managed: :class:`bool`
        Indicates if the role is managed by the guild (a bot's own role).
    mentionable: :class:`bool`
        Indicates if the role can be mentioned by users.
    tags: Optional[:class:`RoleTags`]
        The role tags associated with this role.
    """

    __slots__ = (
        'id',
        'name',
        '_permissions',
        '_colour',
        'position',
        'managed',
        'mentionable',
        'hoist',
        'guild',
        'tags',
        '_state',
        '_is_everyone',
        '_created_at',
    )

    def __init__(self, *, guild: Guild, state: ConnectionState, data: Dict[str, Any]):
        self.guild: Guild = guild
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self._update(data)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<Role id={self.id} name={self.name!r}>'

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Role) or not isinstance(self, Role):
            return NotImplemented

        if self.guild != other.guild:
            raise RuntimeError('cannot compare roles from two different guilds.')

        # The default role is always the lowest; ties on position go to the
        # older role being higher, which is how Discord breaks them.
        guild_id = self.guild.id
        o_id = other.id
        s_id = self.id

        if s_id == guild_id:
            return o_id != guild_id
        if o_id == guild_id:
            return False

        if self.position < other.position:
            return True
        if self.position == other.position:
            return s_id > o_id
        return False

    def __le__(self, other: object) -> bool:
        r = Role.__lt__(other, self)  # type: ignore
        if r is NotImplemented:
            return NotImplemented
        return not r

    def __gt__(self, other: object) -> bool:
        return Role.__lt__(other, self)  # type: ignore

    def __ge__(self, other: object) -> bool:
        r = Role.__lt__(self, other)
        if r is NotImplemented:
            return NotImplemented
        return not r

    def _update(self, data: Dict[str, Any]) -> None:
        self.name: str = data.get('name') or ''
        self._permissions: int = utils._int(data.get('permissions'), 0)
        self.position: int = utils._int(data.get('position'), 0)
        self._colour: int = utils._int(data.get('color'), 0)
        self.hoist: bool = bool(data.get('hoist', False))
        self.managed: bool = bool(data.get('managed', False))
        self.mentionable: bool = bool(data.get('mentionable', False))
        self._is_everyone: bool = bool(data.get('isEveryone', False)) or self.id == self.guild.id
        self._created_at = utils.parse_time(data.get('createdAt'))
        bot_id = data.get('botId') or data.get('managedBy')
        self.tags: Optional[RoleTags] = RoleTags({'botId': bot_id}) if bot_id else None

    def is_default(self) -> bool:
        """:class:`bool`: Checks if the role is the default role."""
        return self._is_everyone or self.guild.id == self.id

    def is_bot_managed(self) -> bool:
        """:class:`bool`: Whether the role is associated with a bot."""
        return self.tags is not None and self.tags.is_bot_managed()

    def is_premium_subscriber(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def is_integration(self) -> bool:
        """:class:`bool`: Always ``False`` on Bisim."""
        return False

    def is_assignable(self) -> bool:
        """:class:`bool`: Whether the role is able to be assigned or removed by the bot."""
        me = self.guild.me
        return not self.is_default() and not self.managed and (me.top_role > self or me.id == self.guild.owner_id)

    @property
    def permissions(self) -> Permissions:
        """:class:`Permissions`: Returns the role's permissions."""
        return Permissions(self._permissions)

    @property
    def colour(self) -> Colour:
        """:class:`Colour`: Returns the role colour. An alias exists under ``color``."""
        return Colour(self._colour)

    @property
    def color(self) -> Colour:
        """:class:`Colour`: Returns the role color. An alias exists under ``colour``."""
        return self.colour

    @property
    def secondary_colour(self) -> Optional[Colour]:
        """Optional[:class:`Colour`]: Not on Bisim."""
        return None

    secondary_color = secondary_colour

    @property
    def tertiary_colour(self) -> Optional[Colour]:
        """Optional[:class:`Colour`]: Not on Bisim."""
        return None

    tertiary_color = tertiary_colour

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`.Asset`]: Not on Bisim."""
        return None

    @property
    def display_icon(self) -> Optional[Union[Asset, str]]:
        """Optional[Union[:class:`.Asset`, :class:`str`]]: Not on Bisim."""
        return None

    @property
    def unicode_emoji(self) -> Optional[str]:
        """Optional[:class:`str`]: Not on Bisim."""
        return None

    @property
    def flags(self) -> RoleFlags:
        """:class:`RoleFlags`: Returns the role's flags."""
        return RoleFlags._from_value(0)

    @property
    def created_at(self) -> datetime:
        """:class:`datetime.datetime`: Returns the role's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention a role."""
        if self.is_default():
            return '@everyone'
        return f'<@&{self.id}>'

    @property
    def members(self) -> List[Member]:
        """List[:class:`Member`]: Returns all the members with this role."""
        all_members = list(self.guild._members.values())
        if self.is_default():
            return all_members
        role_id = self.id
        return [member for member in all_members if member._roles.has(role_id)]

    async def edit(
        self,
        *,
        name: str = utils.MISSING,
        permissions: Permissions = utils.MISSING,
        colour: Union[Colour, int] = utils.MISSING,
        color: Union[Colour, int] = utils.MISSING,
        secondary_colour: Any = utils.MISSING,
        secondary_color: Any = utils.MISSING,
        tertiary_colour: Any = utils.MISSING,
        tertiary_color: Any = utils.MISSING,
        hoist: bool = utils.MISSING,
        display_icon: Any = utils.MISSING,
        mentionable: bool = utils.MISSING,
        position: int = utils.MISSING,
        reason: Optional[str] = utils.MISSING,
    ) -> Optional[Role]:
        """|coro|

        Edits the role.

        You must have :attr:`~Permissions.manage_roles` to do this.

        All fields are optional.

        Parameters
        -----------
        name: :class:`str`
            The new role name to change to.
        permissions: :class:`Permissions`
            The new permissions to change to.
        colour: Union[:class:`Colour`, :class:`int`]
            The new colour to change to. (aliased to color as well)
        hoist: :class:`bool`
            Indicates if the role should be shown separately in the member list.
        display_icon: Optional[Union[:class:`bytes`, :class:`str`]]
            Not supported on Bisim.
        mentionable: :class:`bool`
            Indicates if the role should be mentionable by others.
        position: :class:`int`
            The new role's position. This must be below your top role's
            position or it will fail.
        reason: Optional[:class:`str`]
            The reason for editing this role. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to change the role.
        HTTPException
            Editing the role failed.
        ValueError
            An invalid position was given.
        NotSupported
            A display icon or a secondary colour was given.

        Returns
        --------
        :class:`Role`
            The newly edited role.
        """
        if display_icon is not utils.MISSING:
            raise NotSupported('Role icons')
        for extra in (secondary_colour, secondary_color, tertiary_colour, tertiary_color):
            if extra is not utils.MISSING and extra is not None:
                raise NotSupported('Gradient role colours')

        payload: Dict[str, Any] = {}
        if position is not utils.MISSING:
            if position <= 0:
                raise ValueError('Cannot move role to position 0 or below')
            payload['position'] = int(position)
        if color is not utils.MISSING:
            colour = color
        if colour is not utils.MISSING:
            payload['color'] = colour if isinstance(colour, int) else colour.value
        if name is not utils.MISSING:
            payload['name'] = name
        if permissions is not utils.MISSING:
            payload['permissions'] = str(permissions.value)
        if hoist is not utils.MISSING:
            payload['hoist'] = hoist
        if mentionable is not utils.MISSING:
            payload['mentionable'] = mentionable

        data = await self._state.http.edit_role(
            self.guild.id, self.id, reason=reason if reason is not utils.MISSING else None, **payload
        )
        if isinstance(data, dict) and data.get('id'):
            self._update(data)
        return self

    async def move(
        self,
        *,
        beginning: bool = utils.MISSING,
        end: bool = utils.MISSING,
        above: Role = utils.MISSING,
        below: Role = utils.MISSING,
        offset: int = 0,
        reason: Optional[str] = None,
    ) -> None:
        """|coro|

        A rich interface to help move a role relative to other roles.

        You must have :attr:`~bisim.Permissions.manage_roles` to do this,
        and you cannot move roles above the client's top role in the guild.

        Parameters
        -----------
        beginning: :class:`bool`
            Whether to move this at the beginning of the role list, above the default role.
        end: :class:`bool`
            Whether to move this at the end of the role list.
        above: :class:`Role`
            The role that should be above our current role.
        below: :class:`Role`
            The role that should be below our current role.
        offset: :class:`int`
            The number of roles to offset the move by.
        reason: Optional[:class:`str`]
            The reason for editing the role. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You cannot move the role there.
        HTTPException
            Moving the role failed.
        TypeError
            A bad mix of arguments were passed.
        ValueError
            An invalid role was passed.
        """
        given = sum(x is not utils.MISSING for x in (beginning, end, above, below))
        if given != 1:
            raise TypeError('Only one of [beginning, end, above, below] can be used.')

        roles = [r for r in self.guild.roles[1:] if r != self]
        if beginning:
            index = 0
        elif end:
            index = len(roles)
        elif above:
            if above.guild != self.guild:
                raise ValueError('Role must be in the same guild')
            index = roles.index(above) + 1
        else:
            if below.guild != self.guild:  # type: ignore
                raise ValueError('Role must be in the same guild')
            index = roles.index(below)  # type: ignore
        index = max(0, min(len(roles), index + offset))
        roles.insert(index, self)
        payload = [{'id': str(role.id), 'position': position} for position, role in enumerate(roles, start=1)]
        await self._state.http.move_role_position(self.guild.id, payload, reason=reason)

    async def delete(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the role.

        You must have :attr:`~Permissions.manage_roles` to do this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this role. Shows up on the audit log.

        Raises
        --------
        Forbidden
            You do not have permissions to delete the role.
        HTTPException
            Deleting the role failed.
        """
        await self._state.http.delete_role(self.guild.id, self.id, reason=reason)
