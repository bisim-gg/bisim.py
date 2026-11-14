from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Optional, Type, Union

from . import utils
from .mixins import Hashable

if TYPE_CHECKING:
    from .abc import Snowflake

    SupportsIntCast = Union[str, int, Any]

__all__ = ('Object',)


class Object(Hashable):
    """Represents a generic Bisim object.

    The purpose of this class is to allow you to create 'miniature'
    versions of data classes if you want to pass in just an ID. Most functions
    that take in a specific data class with an ID can also take in this class
    as a substitute instead. Note that even though this is the case, not all
    objects (if any) actually inherit from this class.

    There are also some cases where some websocket events are received
    in strange order and when such events happened you would
    receive this class rather than the actual data class. These cases are
    extremely rare.

    .. container:: operations

        .. describe:: x == y

            Checks if two objects are equal.

        .. describe:: x != y

            Checks if two objects are not equal.

        .. describe:: hash(x)

            Returns the object's hash.

    Attributes
    -----------
    id: :class:`int`
        The ID of the object.
    type: Type[:class:`abc.Snowflake`]
        The class this object is standing in for (used for ``==``).
    """

    def __init__(self, id: SupportsIntCast, *, type: Type[Snowflake] = utils.MISSING):
        try:
            id = int(id)
        except ValueError:
            raise TypeError(f'id parameter must be convertible to int not {id.__class__.__name__}') from None
        self.id: int = id
        self.type: Type[Snowflake] = type or self.__class__

    def __repr__(self) -> str:
        return f'<Object id={self.id!r} type={self.type!r}>'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.type):
            return self.id == other.id  # type: ignore
        return NotImplemented

    __hash__ = Hashable.__hash__

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the snowflake's creation time in UTC."""
        return utils.snowflake_time(self.id)


OLDEST_OBJECT = Object(id=0)
