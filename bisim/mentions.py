from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union

if TYPE_CHECKING:
    from typing_extensions import Self

    from .abc import Snowflake

__all__ = ('AllowedMentions',)


class _FakeBool:
    def __repr__(self) -> str:
        return 'True'

    def __eq__(self, other: object) -> bool:
        return other is True

    def __bool__(self) -> bool:
        return True


default: Any = _FakeBool()


class AllowedMentions:
    """A class that represents what mentions are allowed in a message.

    Bisim does not filter mentions per message yet, so this object is accepted
    everywhere discord.py takes one and does not change what is sent. It is
    kept so that bots written for discord.py run unchanged.

    Attributes
    ------------
    everyone: :class:`bool`
        Whether to allow everyone and here mentions. Defaults to ``True``.
    users: Union[:class:`bool`, Sequence[:class:`abc.Snowflake`]]
        Controls the users being mentioned. If ``True`` (the default) then
        users are mentioned based on the message content. If ``False`` then
        users are not mentioned at all. If a list of :class:`abc.Snowflake`
        is given then only the users provided will be mentioned, provided those
        users are in the message content.
    roles: Union[:class:`bool`, Sequence[:class:`abc.Snowflake`]]
        Controls the roles being mentioned. If ``True`` (the default) then
        roles are mentioned based on the message content. If ``False`` then
        roles are not mentioned at all. If a list of :class:`abc.Snowflake`
        is given then only the roles provided will be mentioned, provided those
        roles are in the message content.
    replied_user: :class:`bool`
        Whether to mention the author of the message being replied to. Defaults
        to ``True``.
    """

    __slots__ = ('everyone', 'users', 'roles', 'replied_user')

    def __init__(
        self,
        *,
        everyone: bool = default,
        users: Union[bool, List[Snowflake]] = default,
        roles: Union[bool, List[Snowflake]] = default,
        replied_user: bool = default,
    ):
        self.everyone: bool = everyone
        self.users: Union[bool, List[Snowflake]] = users
        self.roles: Union[bool, List[Snowflake]] = roles
        self.replied_user: bool = replied_user

    @classmethod
    def all(cls) -> Self:
        """A factory method that returns a :class:`AllowedMentions` with all fields explicitly set to ``True``"""
        return cls(everyone=True, users=True, roles=True, replied_user=True)

    @classmethod
    def none(cls) -> Self:
        """A factory method that returns a :class:`AllowedMentions` with all fields set to ``False``"""
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    def to_dict(self) -> Dict[str, Any]:
        parse = []
        data: Dict[str, Any] = {}
        if self.everyone:
            parse.append('everyone')
        if self.users == True:  # noqa: E712 - default is a fake True
            parse.append('users')
        elif self.users != False:  # noqa: E712
            data['users'] = [str(x.id) for x in self.users]  # type: ignore
        if self.roles == True:  # noqa: E712
            parse.append('roles')
        elif self.roles != False:  # noqa: E712
            data['roles'] = [str(x.id) for x in self.roles]  # type: ignore
        if self.replied_user:
            data['repliedUser'] = True
        data['parse'] = parse
        return data

    def merge(self, other: AllowedMentions) -> AllowedMentions:
        # Creates a new AllowedMentions by merging from another one.
        # Merge is done by using the 'self' values unless explicitly
        # overridden by the 'other' values.
        everyone = self.everyone if other.everyone is default else other.everyone
        users = self.users if other.users is default else other.users
        roles = self.roles if other.roles is default else other.roles
        replied_user = self.replied_user if other.replied_user is default else other.replied_user
        return AllowedMentions(everyone=everyone, roles=roles, users=users, replied_user=replied_user)

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(everyone={self.everyone}, '
            f'users={self.users}, roles={self.roles}, replied_user={self.replied_user})'
        )
