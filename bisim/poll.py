from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Union

from . import utils
from .enums import PollLayoutType, try_enum
from .errors import ClientException
from .partial_emoji import PartialEmoji

if TYPE_CHECKING:
    from .emoji import Emoji
    from .member import Member
    from .message import Message
    from .state import ConnectionState
    from .user import User

__all__ = (
    'Poll',
    'PollAnswer',
    'PollMedia',
)


class PollMedia:
    """Represents the poll media for a poll item.

    Attributes
    ----------
    text: :class:`str`
        The displayed text.
    emoji: Optional[Union[:class:`PartialEmoji`, :class:`Emoji`]]
        The attached emoji for this media.
    """

    __slots__ = ('text', 'emoji')

    def __init__(self, /, text: str, emoji: Optional[Union[PartialEmoji, Emoji, str]] = None) -> None:
        self.text: str = text
        self.emoji: Optional[Union[PartialEmoji, Emoji]] = PartialEmoji.from_str(emoji) if isinstance(emoji, str) else emoji

    def __repr__(self) -> str:
        return f'<PollMedia text={self.text!r} emoji={self.emoji!r}>'


class PollAnswer:
    """Represents a poll's answer.

    .. container:: operations

        .. describe:: str(x)

            Returns this answer's text, if any.

    Attributes
    ----------
    id: :class:`int`
        The ID of this answer.
    media: :class:`PollMedia`
        The display data for this answer.
    self_voted: :class:`bool`
        Whether the current user has voted to this answer or not.
    """

    __slots__ = ('media', 'id', '_state', '_message', '_vote_count', 'self_voted', '_poll')

    def __init__(self, *, message: Optional[Message], poll: Poll, data: Dict[str, Any]) -> None:
        self.media: PollMedia = PollMedia(text=data.get('text') or '', emoji=data.get('emoji') or None)
        self.id: int = int(data.get('id', 0) or 0)
        self._message: Optional[Message] = message
        self._state: Optional[ConnectionState] = message._state if message else None
        self._vote_count: int = 0
        self.self_voted: bool = False
        self._poll: Poll = poll

    def _handle_vote_event(self, added: bool, self_voted: bool) -> None:
        if added:
            self._vote_count += 1
        else:
            self._vote_count = max(self._vote_count - 1, 0)
        self.self_voted = self_voted

    def __str__(self) -> str:
        return self.media.text

    def __repr__(self) -> str:
        return f'<PollAnswer id={self.id} media={self.media!r}>'

    @property
    def text(self) -> str:
        """:class:`str`: Returns this answer's displayed text."""
        return self.media.text

    @property
    def emoji(self) -> Optional[Union[PartialEmoji, Emoji]]:
        """Optional[Union[:class:`Emoji`, :class:`PartialEmoji`]]: Returns this answer's displayed emoji, if any."""
        return self.media.emoji

    @property
    def vote_count(self) -> int:
        """:class:`int`: Returns an approximate count of votes for this answer."""
        return self._vote_count

    @property
    def poll(self) -> Poll:
        """:class:`Poll`: Returns the parent poll of this answer."""
        return self._poll

    def _to_bisim(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'text': self.media.text}
        if self.media.emoji is not None:
            payload['emoji'] = str(self.media.emoji)
        return payload

    async def voters(self, *, limit: Optional[int] = None, after: Optional[Any] = None) -> AsyncIterator[Union[User, Member]]:
        """Returns an :term:`asynchronous iterator` representing the users that have voted on this answer.

        The ``after`` parameter must represent a user
        and meet the :class:`abc.Snowflake` abc.

        This can only be called when the parent poll was sent to a message.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of results to return.
            If not provided, returns all the users who
            voted on this poll answer.
        after: Optional[:class:`abc.Snowflake`]
            For pagination, voters are sorted by member.

        Raises
        ------
        HTTPException
            Retrieving the users failed.

        Yields
        ------
        Union[:class:`User`, :class:`Member`]
            The member (if retrievable) or the user that has voted
            on this poll answer.
        """
        if not self._message or not self._state:
            raise ClientException('You cannot fetch users to a poll not sent with a message')
        message = self._message
        state = self._state
        data = await state.http.get_poll_answer_voters(message.channel.id, message.id, self.id)
        after_id = after.id if after is not None else None
        count = 0
        guild = message.guild
        for raw in data or []:
            user_id = int(raw['id'])
            if after_id is not None and user_id <= after_id:
                continue
            member = guild.get_member(user_id) if guild is not None else None
            yield member if member is not None else state.store_user(raw)
            count += 1
            if limit is not None and count >= limit:
                return


class Poll:
    """Represents a message's Poll.

    Parameters
    ----------
    question: Union[:class:`PollMedia`, :class:`str`]
        The poll's displayed question. The text can be up to 300 characters.
    duration: :class:`datetime.timedelta`
        The duration of the poll. Bisim counts it in whole hours, so it is
        rounded up to the next hour.
    multiple: :class:`bool`
        Whether users are allowed to select more than one answer.
        Defaults to ``False``.
    layout_type: :class:`PollLayoutType`
        The layout type of the poll. Defaults to :attr:`PollLayoutType.default`.

    Attributes
    -----------
    duration: :class:`datetime.timedelta`
        The duration of the poll.
    multiple: :class:`bool`
        Whether users are allowed to select more than one answer.
    layout_type: :class:`PollLayoutType`
        The layout type of the poll.
    """

    __slots__ = (
        'multiple',
        '_answers',
        'duration',
        'layout_type',
        '_question_media',
        '_message',
        '_expiry',
        '_finalized',
        '_state',
        '_total_votes',
        '_victor_answer_id',
    )

    def __init__(
        self,
        question: Union[PollMedia, str],
        duration: datetime.timedelta,
        *,
        multiple: bool = False,
        layout_type: PollLayoutType = PollLayoutType.default,
    ) -> None:
        self._question_media: PollMedia = PollMedia(text=question, emoji=None) if isinstance(question, str) else question
        self._answers: Dict[int, PollAnswer] = {}
        self.duration: Optional[datetime.timedelta] = duration
        self.multiple: bool = multiple
        self.layout_type: PollLayoutType = layout_type
        self._message: Optional[Message] = None
        self._state: Optional[ConnectionState] = None
        self._finalized: bool = False
        self._expiry: Optional[datetime.datetime] = None
        self._total_votes: Optional[int] = None
        self._victor_answer_id: Optional[int] = None

    def _update(self, data: Dict[str, Any], *, my_answer_ids: Optional[List[int]] = None) -> None:
        counts = {int(c.get('answerId', 0) or 0): int(c.get('count', 0) or 0) for c in (data.get('counts') or [])}
        mine = set(my_answer_ids if my_answer_ids is not None else (data.get('myAnswerIds') or []))
        for answer in self._answers.values():
            answer._vote_count = counts.get(answer.id, 0)
            answer.self_voted = answer.id in mine
        if 'total' in data:
            self._total_votes = int(data.get('total') or 0)
        if data.get('endedAt'):
            self._finalized = True
            if counts:
                top = max(counts.values())
                winners = [k for k, v in counts.items() if v == top]
                self._victor_answer_id = winners[0] if len(winners) == 1 and top > 0 else None

    def _update_from_message(self, message: Message) -> None:
        if message.poll is None:
            return
        self._message = message
        self._state = message._state
        self._answers = message.poll._answers
        self._expiry = message.poll._expiry
        self._finalized = message.poll._finalized
        self._total_votes = message.poll._total_votes

    @classmethod
    def _from_data(cls, *, data: Dict[str, Any], message: Optional[Message], state: ConnectionState) -> Poll:
        expires_at = utils.parse_time(data.get('expiresAt'))
        created = message.created_at if message is not None else utils.utcnow()
        duration = (expires_at - created) if expires_at is not None else datetime.timedelta(hours=24)
        self = cls(question=data.get('question') or '', duration=duration, multiple=bool(data.get('multiselect', False)))
        self._message = message
        self._state = state
        self._expiry = expires_at
        for answer_data in data.get('answers') or []:
            answer = PollAnswer(message=message, poll=self, data=answer_data)
            self._answers[answer.id] = answer
        self._update(data)
        return self

    def _to_bisim(self) -> Dict[str, Any]:
        hours = 24
        if self.duration is not None:
            hours = max(1, int(math.ceil(self.duration.total_seconds() / 3600)))
        return {
            'question': self._question_media.text,
            'answers': [answer._to_bisim() for answer in self._answers.values()],
            'multiselect': self.multiple,
            'durationHours': hours,
        }

    def to_dict(self) -> Dict[str, Any]:
        return self._to_bisim()

    def __str__(self) -> str:
        return self._question_media.text

    def __repr__(self) -> str:
        return f'<Poll duration={self.duration} question="{self.question}" answers={self.answers}>'

    @property
    def question(self) -> str:
        """:class:`str`: Returns this poll's question string."""
        return self._question_media.text

    @property
    def answers(self) -> List[PollAnswer]:
        """List[:class:`PollAnswer`]: Returns a read-only copy of the answers."""
        return list(self._answers.values())

    @property
    def victor_answer_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The victor answer ID, once the poll ended with a single winner."""
        return self._victor_answer_id

    @property
    def victor_answer(self) -> Optional[PollAnswer]:
        """Optional[:class:`PollAnswer`]: The victor answer, once the poll ended with a single winner."""
        if self.victor_answer_id is None:
            return None
        return self.get_answer(self.victor_answer_id)

    @property
    def expires_at(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: A datetime object representing the poll expiry."""
        return self._expiry

    @property
    def created_at(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: Returns the poll's creation time, or ``None`` if user-created."""
        if not self._message:
            return None
        return self._message.created_at

    @property
    def message(self) -> Optional[Message]:
        """Optional[:class:`Message`]: The message this poll is from."""
        return self._message

    @property
    def total_votes(self) -> int:
        """:class:`int`: Returns the sum of all the answer votes."""
        if self._total_votes is not None:
            return self._total_votes
        return sum(answer.vote_count for answer in self.answers)

    def is_finalised(self) -> bool:
        """:class:`bool`: Returns whether the poll has finalised."""
        return self._finalized

    is_finalized = is_finalised

    def copy(self) -> Poll:
        """Returns a stateless copy of this poll."""
        new = Poll(question=self._question_media, duration=self.duration or datetime.timedelta(hours=24), multiple=self.multiple)
        for answer in self.answers:
            new.add_answer(text=answer.media.text, emoji=answer.media.emoji)
        return new

    def add_answer(self, *, text: str, emoji: Optional[Union[PartialEmoji, Emoji, str]] = None) -> Poll:
        """Appends a new answer to this poll.

        Parameters
        ----------
        text: :class:`str`
            The text label for this poll answer. Can be up to 55
            characters.
        emoji: Union[:class:`PartialEmoji`, :class:`Emoji`, :class:`str`]
            The emoji to display along the text.

        Raises
        ------
        ClientException
            Cannot append answers to a poll that is active.

        Returns
        -------
        :class:`Poll`
            This poll with the new answer appended. This allows fluent-style chaining.
        """
        if self._message:
            raise ClientException('Cannot append answers to a poll that is active')
        answer_id = len(self._answers) + 1
        answer = PollAnswer(message=None, poll=self, data={'id': answer_id, 'text': text})
        answer.media.emoji = PartialEmoji.from_str(emoji) if isinstance(emoji, str) else emoji
        self._answers[answer_id] = answer
        return self

    def get_answer(self, /, id: int) -> Optional[PollAnswer]:
        """Returns the answer with the provided ID or ``None`` if not found.

        Parameters
        ----------
        id: :class:`int`
            The ID of the answer to get.

        Returns
        -------
        Optional[:class:`PollAnswer`]
            The answer.
        """
        return self._answers.get(id)

    async def end(self) -> Poll:
        """|coro|

        Ends the poll.

        Raises
        ------
        ClientException
            This poll has no attached message.
        HTTPException
            Ending the poll failed.

        Returns
        -------
        :class:`Poll`
            The updated poll.
        """
        if not self._message or not self._state:
            raise ClientException('This poll has no attached message.')
        message = await self._message.end_poll()
        if message.poll is not None:
            self._update_from_message(message)
        return self
