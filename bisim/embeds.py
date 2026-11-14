from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Protocol, Union

from . import utils
from .colour import Colour

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = ('Embed',)


class EmbedProxy:
    """A read only view of one part of an embed (``embed.author``, ``embed.footer``...).

    Missing attributes read as ``None``.
    """

    def __init__(self, layer: Dict[str, Any]):
        self.__dict__.update(layer)

    def __len__(self) -> int:
        return len(self.__dict__)

    def __repr__(self) -> str:
        inner = ', '.join((f'{k}={getattr(self, k)!r}' for k in dir(self) if not k.startswith('_')))
        return f'EmbedProxy({inner})'

    def __getattr__(self, attr: str) -> None:
        return None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EmbedProxy) and self.__dict__ == other.__dict__


class _EmbedMediaProxy(Protocol):
    url: Optional[str]
    proxy_url: Optional[str]
    height: Optional[int]
    width: Optional[int]


EmbedType = str


class Embed:
    """Represents a Bisim embed.

    .. container:: operations

        .. describe:: x == y

            Checks if two embeds are equal.

        .. describe:: len(x)

            Returns the total size of the embed.
            Useful for checking if it's within the 6000 character limit.

        .. describe:: bool(b)

            Returns whether the embed has any data set.

    Certain properties return an ``EmbedProxy``, a type
    that acts similar to a regular :class:`dict` except using dotted access,
    e.g. ``embed.author.icon_url``. If the attribute
    is invalid or empty, then ``None`` is returned.

    For ease of use, all parameters that expect a :class:`str` are implicitly
    casted to :class:`str` for you.

    .. note::

        Bisim shows an embed's title, description, link, colour, timestamp,
        author (name and link), footer text and fields. Images, thumbnails
        and icons can be set, and are kept on this object, but Bisim does
        not show them and they are not sent.

    Attributes
    -----------
    title: Optional[:class:`str`]
        The title of the embed.
        This can be set during initialisation.
        Can only be up to 256 characters.
    type: :class:`str`
        The type of embed. Usually "rich".
        This can be set during initialisation.
    description: Optional[:class:`str`]
        The description of the embed.
        This can be set during initialisation.
        Can only be up to 4096 characters.
    url: Optional[:class:`str`]
        The URL of the embed.
        This can be set during initialisation.
    colour: Optional[Union[:class:`Colour`, :class:`int`]]
        The colour code of the embed. Aliased to ``color`` as well.
        This can be set during initialisation.
    """

    __slots__ = (
        'title',
        'url',
        'type',
        '_timestamp',
        '_colour',
        '_footer',
        '_image',
        '_thumbnail',
        '_video',
        '_provider',
        '_author',
        '_fields',
        'description',
        '_flags',
    )

    def __init__(
        self,
        *,
        colour: Optional[Union[int, Colour]] = None,
        color: Optional[Union[int, Colour]] = None,
        title: Optional[Any] = None,
        type: EmbedType = 'rich',
        url: Optional[Any] = None,
        description: Optional[Any] = None,
        timestamp: Optional[datetime.datetime] = None,
    ):
        self.colour = colour if colour is not None else color
        self.title: Optional[str] = title
        self.type: EmbedType = type
        self.url: Optional[str] = url
        self.description: Optional[str] = description
        self._flags: int = 0

        if self.title is not None:
            self.title = str(self.title)
        if self.description is not None:
            self.description = str(self.description)
        if self.url is not None:
            self.url = str(self.url)
        if timestamp is not None:
            self.timestamp = timestamp

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Converts a :class:`dict` to a :class:`Embed`.

        It accepts the nested shape :meth:`to_dict` returns, which is also the
        shape discord.py uses, and the flat shape Bisim sends on messages.

        Parameters
        -----------
        data: :class:`dict`
            The dictionary to convert into an embed.
        """
        if any(key in data for key in ('siteName', 'imageUrl', 'authorName', 'footerText', 'authorUrl')):
            return cls._from_bisim(data)

        self = cls.__new__(cls)
        self.title = data.get('title', None)
        self.type = data.get('type', None) or 'rich'
        self.description = data.get('description', None)
        self.url = data.get('url', None)
        self._flags = data.get('flags', 0)
        if self.title is not None:
            self.title = str(self.title)
        if self.description is not None:
            self.description = str(self.description)
        if self.url is not None:
            self.url = str(self.url)

        try:
            self._colour = Colour(value=data['color'])
        except KeyError:
            pass
        except TypeError:
            self._colour = None

        try:
            self._timestamp = utils.parse_time(data['timestamp'])
        except KeyError:
            pass

        for attr in ('thumbnail', 'video', 'provider', 'author', 'fields', 'image', 'footer'):
            try:
                value = data[attr]
            except KeyError:
                continue
            else:
                setattr(self, '_' + attr, value)

        return self

    @classmethod
    def _from_bisim(cls, data: Mapping[str, Any]) -> Self:
        """Builds an embed from the flat shape Bisim sends on messages."""
        self = cls.__new__(cls)
        self.title = data.get('title') or None
        self.type = data.get('type') or 'rich'
        self.description = data.get('description') or None
        self.url = data.get('url') or None
        self._flags = 0
        color = data.get('color')
        if color:
            self._colour = Colour(int(color))
        timestamp = data.get('timestamp')
        if timestamp:
            self._timestamp = utils.parse_time(timestamp)
        if data.get('authorName') or data.get('authorUrl'):
            author: Dict[str, Any] = {}
            if data.get('authorName'):
                author['name'] = data['authorName']
            if data.get('authorUrl'):
                author['url'] = data['authorUrl']
            self._author = author
        if data.get('footerText'):
            self._footer = {'text': data['footerText']}
        if data.get('imageUrl'):
            image: Dict[str, Any] = {'url': data['imageUrl']}
            if data.get('imageWidth'):
                image['width'] = data['imageWidth']
            if data.get('imageHeight'):
                image['height'] = data['imageHeight']
            if self.type in ('video', 'gifv'):
                self._video = image
            else:
                self._image = image
        if data.get('siteName'):
            self._provider = {'name': data['siteName']}
        fields = data.get('fields') or []
        if fields:
            self._fields = [
                {'name': str(f.get('name', '')), 'value': str(f.get('value', '')), 'inline': bool(f.get('inline', False))}
                for f in fields
            ]
        return self

    def copy(self) -> Self:
        """Returns a shallow copy of the embed."""
        return self.__class__.from_dict(self.to_dict())

    def __len__(self) -> int:
        total = len(self.title or '') + len(self.description or '')
        for field in getattr(self, '_fields', []):
            total += len(field['name']) + len(field['value'])

        try:
            footer_text = self._footer['text']
        except (AttributeError, KeyError):
            pass
        else:
            total += len(footer_text)

        try:
            author = self._author
        except AttributeError:
            pass
        else:
            total += len(author.get('name', ''))

        return total

    def __bool__(self) -> bool:
        return any(
            (
                self.title,
                self.url,
                self.description,
                self.colour,
                self.fields,
                self.timestamp,
                self.author,
                self.thumbnail,
                self.footer,
                self.image,
                self.provider,
                self.video,
            )
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Embed) and self.to_dict() == other.to_dict()

    @property
    def flags(self) -> Any:
        """:class:`EmbedFlags`: The flags of this embed."""
        from .flags import EmbedFlags

        return EmbedFlags._from_value(self._flags or 0)

    @property
    def colour(self) -> Optional[Colour]:
        return getattr(self, '_colour', None)

    @colour.setter
    def colour(self, value: Optional[Union[int, Colour]]) -> None:
        if value is None:
            self._colour = None
        elif isinstance(value, Colour):
            self._colour = value
        elif isinstance(value, int):
            self._colour = Colour(value=value)
        else:
            raise TypeError(f'Expected bisim.Colour, int, or None but received {value.__class__.__name__} instead.')

    color = colour

    @property
    def timestamp(self) -> Optional[datetime.datetime]:
        return getattr(self, '_timestamp', None)

    @timestamp.setter
    def timestamp(self, value: Optional[datetime.datetime]) -> None:
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.astimezone()
            self._timestamp = value
        elif value is None:
            self._timestamp = None
        else:
            raise TypeError(f'Expected datetime.datetime or None received {value.__class__.__name__} instead')

    @property
    def footer(self) -> EmbedProxy:
        """Returns an ``EmbedProxy`` denoting the footer contents.

        See :meth:`set_footer` for possible values you can access.

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_footer', {}))  # type: ignore

    def set_footer(self, *, text: Optional[Any] = None, icon_url: Optional[Any] = None) -> Self:
        """Sets the footer for the embed content.

        This function returns the class instance to allow for fluent-style
        chaining.

        Parameters
        -----------
        text: :class:`str`
            The footer text. Can only be up to 2048 characters.
        icon_url: :class:`str`
            The URL of the footer icon. Only HTTP(S) is supported.
            Inline attachment URLs are also supported. Bisim does not show it.
        """
        self._footer = {}
        if text is not None:
            self._footer['text'] = str(text)
        if icon_url is not None:
            self._footer['icon_url'] = str(icon_url)
        return self

    def remove_footer(self) -> Self:
        """Clears embed's footer information.

        This function returns the class instance to allow for fluent-style
        chaining.
        """
        try:
            del self._footer
        except AttributeError:
            pass
        return self

    @property
    def image(self) -> _EmbedMediaProxy:
        """Returns an ``EmbedProxy`` denoting the image contents.

        Possible attributes you can access are:

        - ``url``
        - ``proxy_url``
        - ``width``
        - ``height``

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_image', {}))  # type: ignore

    def set_image(self, *, url: Optional[Any]) -> Self:
        """Sets the image for the embed content.

        This function returns the class instance to allow for fluent-style
        chaining.

        .. note::

            Bisim does not show images in embeds a bot sends, so the image is
            kept on this object but is not sent.

        Parameters
        -----------
        url: Optional[:class:`str`]
            The source URL for the image. Only HTTP(S) is supported.
            If ``None`` is passed, any existing image is removed.
        """
        if url is None:
            try:
                del self._image
            except AttributeError:
                pass
        else:
            self._image = {'url': str(url)}
        return self

    @property
    def thumbnail(self) -> _EmbedMediaProxy:
        """Returns an ``EmbedProxy`` denoting the thumbnail contents.

        Possible attributes you can access are:

        - ``url``
        - ``proxy_url``
        - ``width``
        - ``height``

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_thumbnail', {}))  # type: ignore

    def set_thumbnail(self, *, url: Optional[Any]) -> Self:
        """Sets the thumbnail for the embed content.

        This function returns the class instance to allow for fluent-style
        chaining.

        .. note::

            Bisim does not show thumbnails in embeds a bot sends, so the
            thumbnail is kept on this object but is not sent.

        Parameters
        -----------
        url: Optional[:class:`str`]
            The source URL for the thumbnail. Only HTTP(S) is supported.
            If ``None`` is passed, any existing thumbnail is removed.
        """
        if url is None:
            try:
                del self._thumbnail
            except AttributeError:
                pass
        else:
            self._thumbnail = {'url': str(url)}
        return self

    @property
    def video(self) -> _EmbedMediaProxy:
        """Returns an ``EmbedProxy`` denoting the video contents.

        Possible attributes include:

        - ``url`` for the video URL.
        - ``height`` for the video height.
        - ``width`` for the video width.

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_video', {}))  # type: ignore

    @property
    def provider(self) -> EmbedProxy:
        """Returns an ``EmbedProxy`` denoting the provider contents.

        The only attributes that might be accessed are ``name`` and ``url``.

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_provider', {}))  # type: ignore

    @property
    def author(self) -> EmbedProxy:
        """Returns an ``EmbedProxy`` denoting the author contents.

        See :meth:`set_author` for possible values you can access.

        If the attribute has no value then ``None`` is returned.
        """
        return EmbedProxy(getattr(self, '_author', {}))  # type: ignore

    def set_author(self, *, name: Any, url: Optional[Any] = None, icon_url: Optional[Any] = None) -> Self:
        """Sets the author for the embed content.

        This function returns the class instance to allow for fluent-style
        chaining.

        Parameters
        -----------
        name: :class:`str`
            The name of the author. Can only be up to 256 characters.
        url: :class:`str`
            The URL for the author.
        icon_url: :class:`str`
            The URL of the author icon. Only HTTP(S) is supported. Bisim does
            not show it.
        """
        self._author = {'name': str(name)}
        if url is not None:
            self._author['url'] = str(url)
        if icon_url is not None:
            self._author['icon_url'] = str(icon_url)
        return self

    def remove_author(self) -> Self:
        """Clears embed's author information.

        This function returns the class instance to allow for fluent-style
        chaining.
        """
        try:
            del self._author
        except AttributeError:
            pass
        return self

    @property
    def fields(self) -> List[EmbedProxy]:
        """List[``EmbedProxy``]: Returns a :class:`list` of ``EmbedProxy`` denoting the field contents.

        See :meth:`add_field` for possible values you can access.

        If the attribute has no value then ``None`` is returned.
        """
        return [EmbedProxy(d) for d in getattr(self, '_fields', [])]  # type: ignore

    def add_field(self, *, name: Any, value: Any, inline: bool = True) -> Self:
        """Adds a field to the embed object.

        This function returns the class instance to allow for fluent-style
        chaining. Can only be up to 25 fields.

        Parameters
        -----------
        name: :class:`str`
            The name of the field. Can only be up to 256 characters.
        value: :class:`str`
            The value of the field. Can only be up to 1024 characters.
        inline: :class:`bool`
            Whether the field should be displayed inline.
        """
        field = {'inline': inline, 'name': str(name), 'value': str(value)}
        try:
            self._fields.append(field)
        except AttributeError:
            self._fields = [field]
        return self

    def insert_field_at(self, index: int, *, name: Any, value: Any, inline: bool = True) -> Self:
        """Inserts a field before a specified index to the embed.

        This function returns the class instance to allow for fluent-style
        chaining. Can only be up to 25 fields.

        Parameters
        -----------
        index: :class:`int`
            The index of where to insert the field.
        name: :class:`str`
            The name of the field. Can only be up to 256 characters.
        value: :class:`str`
            The value of the field. Can only be up to 1024 characters.
        inline: :class:`bool`
            Whether the field should be displayed inline.
        """
        field = {'inline': inline, 'name': str(name), 'value': str(value)}
        try:
            self._fields.insert(index, field)
        except AttributeError:
            self._fields = [field]
        return self

    def clear_fields(self) -> Self:
        """Removes all fields from this embed.

        This function returns the class instance to allow for fluent-style
        chaining.
        """
        try:
            self._fields.clear()
        except AttributeError:
            self._fields = []
        return self

    def remove_field(self, index: int) -> Self:
        """Removes a field at a specified index.

        If the index is invalid or out of bounds then the error is
        silently swallowed.

        This function returns the class instance to allow for fluent-style
        chaining.

        .. note::

            When deleting a field by index, the index of the other fields
            shift to fill the gap just like a regular list.

        Parameters
        -----------
        index: :class:`int`
            The index of the field to remove.
        """
        try:
            del self._fields[index]
        except (AttributeError, IndexError):
            pass
        return self

    def set_field_at(self, index: int, *, name: Any, value: Any, inline: bool = True) -> Self:
        """Modifies a field to the embed object.

        The index must point to a valid pre-existing field. Can only be up to 25 fields.

        This function returns the class instance to allow for fluent-style
        chaining.

        Parameters
        -----------
        index: :class:`int`
            The index of the field to modify.
        name: :class:`str`
            The name of the field. Can only be up to 256 characters.
        value: :class:`str`
            The value of the field. Can only be up to 1024 characters.
        inline: :class:`bool`
            Whether the field should be displayed inline.

        Raises
        -------
        IndexError
            An invalid index was provided.
        """
        try:
            field = self._fields[index]
        except (TypeError, IndexError, AttributeError):
            raise IndexError('field index out of range')
        field['name'] = str(name)
        field['value'] = str(value)
        field['inline'] = inline
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Converts this embed object into a dict, in Discord's shape."""
        result: Dict[str, Any] = {}
        for key in self.__slots__:
            if key[0] != '_' or key in ('_colour', '_timestamp', '_flags'):
                continue
            value = getattr(self, key, None)
            if value:
                result[key[1:]] = value

        colour = self.colour
        if colour is not None:
            result['color'] = colour.value
        timestamp = self.timestamp
        if timestamp is not None:
            result['timestamp'] = timestamp.astimezone(tz=datetime.timezone.utc).isoformat()
        if self.type:
            result['type'] = self.type
        if self.description:
            result['description'] = self.description
        if self.url:
            result['url'] = self.url
        if self.title:
            result['title'] = self.title
        return result

    def _to_bisim(self) -> Dict[str, Any]:
        """The nested shape a Bisim bot sends: title, description, url, color,
        timestamp, author {name, url}, footer {text} and fields."""
        payload: Dict[str, Any] = {}
        if self.title:
            payload['title'] = self.title[:256]
        if self.description:
            payload['description'] = self.description[:4096]
        if self.url:
            payload['url'] = self.url
        colour = self.colour
        if colour is not None:
            payload['color'] = colour.value
        timestamp = self.timestamp
        if timestamp is not None:
            payload['timestamp'] = utils._isoformat(timestamp)
        author = getattr(self, '_author', None)
        if author and author.get('name'):
            payload['author'] = {'name': author['name']}
            if author.get('url'):
                payload['author']['url'] = author['url']
        footer = getattr(self, '_footer', None)
        if footer and footer.get('text'):
            payload['footer'] = {'text': footer['text']}
        fields = getattr(self, '_fields', None)
        if fields:
            payload['fields'] = [
                {'name': f['name'], 'value': f['value'], 'inline': bool(f.get('inline', False))} for f in fields[:25]
            ]
        return payload
