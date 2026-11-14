from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Union

from .enums import ReactionType
from .object import Object

if TYPE_CHECKING:
    from .abc import Snowflake
    from .emoji import Emoji
    from .member import Member
    from .message import Message
    from .partial_emoji import PartialEmoji
    from .user import User

__all__ = ('Reaction',)


class Reaction:
    """Represents a reaction to a message.

    Depending on the way this object was created, some of the attributes can
    have a value of ``None``.

    .. container:: operations

        .. describe:: x == y

            Checks if two reactions are equal. This works by checking if the emoji
            is the same. So two messages with the same reaction will be considered
            "equal".

        .. describe:: x != y

            Checks if two reactions are not equal.

        .. describe:: hash(x)

            Returns the reaction's hash.

        .. describe:: str(x)

            Returns the string form of the reaction's emoji.

    Attributes
    -----------
    emoji: Union[:class:`Emoji`, :class:`PartialEmoji`, :class:`str`]
        The reaction emoji. May be a custom emoji, or a unicode emoji.
    count: :class:`int`
        Number of times this reaction was made.
    me: :class:`bool`
        If the user sent this reaction.
    message: :class:`Message`
        Message this reaction is for.
    me_burst: :class:`bool`
        Always ``False``: Bisim has no super reactions.
    normal_count: :class:`int`
        The same as :attr:`count`.
    burst_count: :class:`int`
        Always ``0``.
    """

    __slots__ = ('message', 'count', 'emoji', 'me', 'me_burst', 'normal_count', 'burst_count', 'burst_colours')

    def __init__(self, *, message: Message, data: Dict[str, Any], emoji: Optional[Union[PartialEmoji, Emoji, str]] = None):
        self.message: Message = message
        self.emoji: Union[PartialEmoji, Emoji, str] = (
            emoji if emoji is not None else message._state._resolve_reaction_emoji(data.get('emoji', ''))
        )
        self.count: int = int(data.get('count', 1) or 1)
        self.me: bool = bool(data.get('me', False))
        self.me_burst: bool = False
        self.normal_count: int = self.count
        self.burst_count: int = 0
        self.burst_colours: List[Any] = []

    @property
    def burst_colors(self) -> List[Any]:
        """An alias of :attr:`burst_colours`."""
        return self.burst_colours

    def is_custom_emoji(self) -> bool:
        """:class:`bool`: If this is a custom emoji."""
        return not isinstance(self.emoji, str)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and other.emoji == self.emoji

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.emoji)

    def __str__(self) -> str:
        return str(self.emoji)

    def __repr__(self) -> str:
        return f'<Reaction emoji={self.emoji!r} me={self.me} count={self.count}>'

    async def remove(self, user: Snowflake) -> None:
        """|coro|

        Remove the reaction by the provided :class:`User` from the message.

        If the reaction is not your own (i.e. ``user`` parameter is not you) then
        :attr:`~Permissions.manage_messages` is needed.

        The ``user`` parameter must represent a user or member and meet
        the :class:`abc.Snowflake` abc.

        Parameters
        -----------
        user: :class:`abc.Snowflake`
             The user or member from which to remove the reaction.

        Raises
        -------
        HTTPException
            Removing the reaction failed.
        Forbidden
            You do not have the proper permissions to remove the reaction.
        NotFound
            The user you specified, or the reaction's message was not found.
        """
        await self.message.remove_reaction(self.emoji, user)

    async def clear(self) -> None:
        """|coro|

        Clears this reaction from the message.

        You must have :attr:`~Permissions.manage_messages` to do this.

        Raises
        --------
        HTTPException
            Clearing the reaction failed.
        Forbidden
            You do not have the proper permissions to clear the reaction.
        NotFound
            The emoji you specified was not found.
        TypeError
            The emoji parameter is invalid.
        """
        await self.message.clear_reaction(self.emoji)

    async def users(
        self, *, limit: Optional[int] = None, after: Optional[Snowflake] = None, type: Optional[ReactionType] = None
    ) -> AsyncIterator[Union[Member, User]]:
        """Returns an :term:`asynchronous iterator` representing the users that have reacted to the message.

        The ``after`` parameter must represent a member
        and meet the :class:`abc.Snowflake` abc.

        Examples
        ---------

        Usage ::

            # I do not actually recommend doing this.
            async for user in reaction.users():
                await channel.send(f'{user} has reacted with {reaction.emoji}!')

        Flattening into a list: ::

            users = [user async for user in reaction.users()]
            # users is now a list of User...
            winner = random.choice(users)
            await channel.send(f'{winner} has won the raffle.')

        Parameters
        ------------
        limit: Optional[:class:`int`]
            The maximum number of results to return.
            If not provided, returns all the users who
            reacted to the message.
        after: Optional[:class:`abc.Snowflake`]
            For pagination, reactions are sorted by member.
        type: Optional[:class:`ReactionType`]
            Accepted for compatibility (Bisim has only normal reactions).

        Raises
        --------
        HTTPException
            Getting the users for the reaction failed.

        Yields
        --------
        Union[:class:`User`, :class:`Member`]
            The member (if retrievable) or the user that has reacted
            to this message. The case where it can be a :class:`Member` is
            in a guild message context. Sometimes it can be a :class:`User`
            if the member has left the guild.
        """
        from .message import convert_emoji_reaction

        message = self.message
        state = message._state
        emoji = convert_emoji_reaction(self.emoji)
        guild = message.guild
        remaining = limit
        cursor = after.id if after is not None else None

        while remaining is None or remaining > 0:
            batch = 100 if remaining is None else min(remaining, 100)
            data = await state.http.get_reaction_users(message.channel.id, message.id, emoji, batch, after=cursor)
            if not data:
                return
            for raw in data:
                user_id = int(raw['id'])
                member = guild.get_member(user_id) if guild is not None else None
                yield member if member is not None else state.store_user(raw)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return
            if len(data) < batch:
                return
            cursor = int(data[-1]['id'])
