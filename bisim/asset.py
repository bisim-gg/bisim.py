from __future__ import annotations

import io
import os
from typing import TYPE_CHECKING, Any, Literal, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import utils
from .errors import BisimException, NotSupported
from .file import File

if TYPE_CHECKING:
    from typing_extensions import Self

    from .state import ConnectionState

__all__ = ('Asset',)

ValidAssetFormatTypes = Literal['webp', 'jpeg', 'jpg', 'png', 'gif']
VALID_STATIC_FORMATS = frozenset({'jpeg', 'jpg', 'webp', 'png'})
VALID_ASSET_FORMATS = VALID_STATIC_FORMATS | {'gif'}

DEFAULT_CDN = 'https://cdn.bisim.gg'


class AssetMixin:
    url: str
    _state: Optional[Any]

    async def read(self) -> bytes:
        """|coro|

        Retrieves the content of this asset as a :class:`bytes` object.

        Raises
        ------
        BisimException
            There was no internal connection state.
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.

        Returns
        -------
        :class:`bytes`
            The content of the asset.
        """
        if self._state is None:
            raise BisimException('Invalid state (no ConnectionState provided)')
        return await self._state.http.get_from_cdn(self.url)

    async def save(self, fp: Union[str, bytes, os.PathLike, io.BufferedIOBase], *, seek_begin: bool = True) -> int:
        """|coro|

        Saves this asset into a file-like object.

        Parameters
        ----------
        fp: Union[:class:`io.BufferedIOBase`, :class:`os.PathLike`]
            The file-like object to save this asset to or the filename
            to use. If a filename is passed then a file is created with that
            filename and used instead.
        seek_begin: :class:`bool`
            Whether to seek to the beginning of the file after saving is
            successfully done.

        Raises
        ------
        BisimException
            There was no internal connection state.
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.

        Returns
        --------
        :class:`int`
            The number of bytes written.
        """
        data = await self.read()
        if isinstance(fp, io.BufferedIOBase) or hasattr(fp, 'write'):
            written = fp.write(data)  # type: ignore
            if seek_begin and hasattr(fp, 'seek'):
                fp.seek(0)  # type: ignore
            return written  # type: ignore
        with open(fp, 'wb') as handle:  # type: ignore
            return handle.write(data)

    async def to_file(
        self,
        *,
        filename: Optional[str] = utils.MISSING,
        description: Optional[str] = None,
        spoiler: bool = False,
    ) -> File:
        """|coro|

        Converts the asset into a :class:`File` suitable for sending via
        :meth:`abc.Messageable.send`.

        Parameters
        -----------
        filename: Optional[:class:`str`]
            The filename of the file. If not provided, then the filename from
            the asset's URL is used.
        description: Optional[:class:`str`]
            The description for the file.
        spoiler: :class:`bool`
            Whether the file is a spoiler.

        Raises
        ------
        BisimException
            The asset does not have an associated state.
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.

        Returns
        -------
        :class:`File`
            The asset as a file suitable for sending.
        """
        data = await self.read()
        name = filename if filename is not utils.MISSING else None
        if not name:
            name = urlsplit(self.url).path.rsplit('/', 1)[-1] or 'file'
        return File(io.BytesIO(data), filename=name, description=description, spoiler=spoiler)


class Asset(AssetMixin):
    """Represents a CDN asset on Bisim (an avatar, a server icon, an emoji...).

    Bisim sends media as bare keys (``avatarKey``, ``iconKey``); the URL is
    ``<cdn>/<key>``.

    .. container:: operations

        .. describe:: str(x)

            Returns the URL of the CDN asset.

        .. describe:: len(x)

            Returns the length of the CDN asset's URL.

        .. describe:: x == y

            Checks if the asset is equal to another asset.

        .. describe:: x != y

            Checks if the asset is not equal to another asset.

        .. describe:: hash(x)

            Returns the hash of the asset.
    """

    __slots__: Tuple[str, ...] = ('_state', '_url', '_animated', '_key')

    def __init__(self, state: Optional[Any], *, url: str, key: str, animated: bool = False) -> None:
        self._state: Optional[Any] = state
        self._url: str = url
        self._animated: bool = animated
        self._key: str = key

    @staticmethod
    def _cdn(state: Optional[Any]) -> str:
        base = getattr(getattr(state, 'http', None), 'cdn_url', None) or DEFAULT_CDN
        return base.rstrip('/')

    @classmethod
    def _from_key(cls, state: Optional[Any], key: str) -> Self:
        key = key.lstrip('/')
        if key.startswith(('http://', 'https://')):
            return cls(state, url=key, key=key, animated=key.endswith('.gif'))
        return cls(state, url=f'{cls._cdn(state)}/{key}', key=key, animated=key.endswith('.gif'))

    @classmethod
    def _from_default_avatar(cls, state: Optional[Any], index: int) -> Self:
        key = f'avatars/default/v1/m{(index % 12) + 1:02d}.webp'
        return cls._from_key(state, key)

    @classmethod
    def _from_avatar(cls, state: Optional[Any], user_id: int, avatar: str) -> Self:
        return cls._from_key(state, avatar)

    @classmethod
    def _from_guild_icon(cls, state: Optional[Any], guild_id: int, icon_key: str) -> Self:
        return cls._from_key(state, icon_key)

    def __str__(self) -> str:
        return self._url

    def __len__(self) -> int:
        return len(self._url)

    def __repr__(self) -> str:
        shorten = self._url.replace(self._cdn(self._state), '')
        return f'<Asset url={shorten!r}>'

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Asset) and self._url == other._url

    def __hash__(self) -> int:
        return hash(self._url)

    @property
    def url(self) -> str:
        """:class:`str`: Returns the underlying URL of the asset."""
        return self._url

    @property
    def key(self) -> str:
        """:class:`str`: Returns the identifying key of the asset (Bisim's object key)."""
        return self._key

    def is_animated(self) -> bool:
        """:class:`bool`: Returns whether the asset is animated."""
        return self._animated

    def _stored_format(self) -> str:
        path = urlsplit(self._url).path
        if '.' in path.rsplit('/', 1)[-1]:
            return path.rsplit('.', 1)[-1].lower()
        return ''

    def replace(
        self,
        *,
        size: int = utils.MISSING,
        format: ValidAssetFormatTypes = utils.MISSING,
        static_format: ValidAssetFormatTypes = utils.MISSING,
    ) -> Self:
        """Returns a new asset with the passed components replaced.

        Bisim's CDN can scale images (``?width=&height=``) but does not
        convert between formats, so asking for a format other than the stored
        one raises :exc:`NotSupported`.

        Parameters
        -----------
        size: :class:`int`
            The new size of the asset. Must be a power of 2 between 16 and 4096.
        format: :class:`str`
            The new format to change it to (only the stored format is accepted).
        static_format: :class:`str`
            The new format to change it to if the asset isn't animated.

        Raises
        -------
        ValueError
            An invalid size or format was passed.
        NotSupported
            The format differs from the stored one.

        Returns
        --------
        :class:`Asset`
            The newly updated asset.
        """
        for requested in (format, static_format):
            if requested is utils.MISSING:
                continue
            if requested not in VALID_ASSET_FORMATS:
                raise ValueError(f'format must be one of {VALID_ASSET_FORMATS}')
            stored = self._stored_format()
            same = requested == stored or {requested, stored} == {'jpg', 'jpeg'}
            if stored and not same and not (requested is static_format and self._animated):
                raise NotSupported('Converting an asset to another format')

        url = self._url
        if size is not utils.MISSING:
            if not (16 <= size <= 4096) or size & (size - 1):
                raise ValueError('size must be a power of 2 between 16 and 4096')
            parts = urlsplit(url)
            query = dict(parse_qsl(parts.query))
            query['width'] = str(size)
            query['height'] = str(size)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        return self.__class__(self._state, url=url, key=self._key, animated=self._animated)

    def with_size(self, size: int, /) -> Self:
        """Returns a new asset with the specified size.

        Parameters
        ------------
        size: :class:`int`
            The new size of the asset.

        Raises
        -------
        ValueError
            The asset had an invalid size.

        Returns
        --------
        :class:`Asset`
            The new updated asset.
        """
        return self.replace(size=size)

    def with_format(self, format: ValidAssetFormatTypes, /) -> Self:
        """Returns a new asset with the specified format (only the stored format on Bisim)."""
        return self.replace(format=format)

    def with_static_format(self, format: ValidAssetFormatTypes, /) -> Self:
        """Returns a new asset with the specified static format (only the stored format on Bisim)."""
        if self._animated:
            return self
        return self.replace(format=format)
