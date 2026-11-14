from __future__ import annotations

import io
import mimetypes
import os
from typing import Any, Dict, Optional, Tuple, Union

from . import utils

__all__ = ('File',)


def _strip_spoiler(filename: str) -> Tuple[str, bool]:
    stripped = filename
    spoiler = False
    while stripped.startswith('SPOILER_'):
        stripped = stripped[8:]
        spoiler = True
    return stripped, spoiler


class File:
    r"""A parameter object used for :meth:`abc.Messageable.send`
    for sending file objects.

    On Bisim a file is uploaded straight to storage before the message is
    sent: the library asks for an upload address, puts the bytes there and
    then sends the message that refers to it. All of that happens inside
    ``send``.

    .. note::

        File objects are single use and are not meant to be reused in
        multiple :meth:`abc.Messageable.send`\s.

    Attributes
    -----------
    fp: Union[:class:`os.PathLike`, :class:`io.BufferedIOBase`]
        A file-like object opened in binary mode and read mode
        or a filename representing a file in the hard drive to
        open.

        .. note::

            If the file-like object passed is opened via ``open`` then the
            modes 'rb' should be used.

            To pass binary data, consider usage of ``io.BytesIO``.

    spoiler: :class:`bool`
        Whether the attachment is a spoiler. If left unspecified, the :attr:`~File.filename` is used
        to determine if the file is a spoiler.
    description: Optional[:class:`str`]
        The file description to display, currently only supported for images.
    """

    __slots__ = ('fp', '_filename', 'spoiler', 'description', '_original_pos', '_owner', '_closer')

    def __init__(
        self,
        fp: Union[str, bytes, os.PathLike, io.BufferedIOBase],
        filename: Optional[str] = None,
        *,
        spoiler: bool = utils.MISSING,
        description: Optional[str] = None,
    ):
        if isinstance(fp, io.IOBase) or hasattr(fp, 'read'):
            if hasattr(fp, 'readable') and not fp.readable():  # type: ignore
                raise ValueError(f'File buffer {fp!r} must be readable.')
            self.fp = fp
            self._original_pos = fp.tell() if hasattr(fp, 'tell') else 0  # type: ignore
            self._owner = False
        else:
            self.fp = open(fp, 'rb')  # type: ignore
            self._original_pos = 0
            self._owner = True

        # Closing is deferred until the upload finished, so a failed upload can be retried.
        self._closer = self.fp.close
        self.fp.close = lambda: None  # type: ignore

        if filename is None:
            if isinstance(fp, str):
                _, filename = os.path.split(fp)
            else:
                filename = getattr(fp, 'name', 'untitled')
                filename = os.path.basename(str(filename)) if filename else 'untitled'

        self._filename, filename_spoiler = _strip_spoiler(str(filename))
        if spoiler is utils.MISSING:
            spoiler = filename_spoiler
        self.spoiler: bool = spoiler
        self.description: Optional[str] = description

    @property
    def filename(self) -> str:
        """:class:`str`: The filename to display when uploading to Bisim.
        If this is not given then it defaults to ``fp.name`` or if ``fp`` is
        a string then the ``filename`` will default to the string given.
        """
        return 'SPOILER_' + self._filename if self.spoiler else self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        self._filename, self.spoiler = _strip_spoiler(value)

    @property
    def uri(self) -> str:
        """:class:`str`: Returns the ``attachment://<filename>`` URI for this file."""
        return f'attachment://{self.filename}'

    @property
    def content_type(self) -> str:
        """:class:`str`: The MIME type sent with the upload, guessed from the file name."""
        guessed, _ = mimetypes.guess_type(self._filename)
        return guessed or 'application/octet-stream'

    def reset(self, *, seek: Union[int, bool] = True) -> None:
        # done.
        if seek and hasattr(self.fp, 'seek'):
            self.fp.seek(self._original_pos)  # type: ignore

    def close(self) -> None:
        self.fp.close = self._closer  # type: ignore
        if self._owner:
            self._closer()

    def _read_all(self) -> bytes:
        self.reset()
        data = self.fp.read()  # type: ignore
        if isinstance(data, str):
            data = data.encode('utf-8')
        return bytes(data)

    def to_dict(self, index: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'id': index, 'filename': self.filename}
        if self.description is not None:
            payload['description'] = self.description
        return payload
