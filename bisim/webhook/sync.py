"""A blocking webhook for scripts that do not run an event loop.

It uses only the standard library (:mod:`urllib`).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from .. import utils
from ..errors import BisimServerError, Forbidden, HTTPException, InvalidData, NotFound, NotSupported
from ..file import File

if TYPE_CHECKING:
    from ..embeds import Embed

__all__ = (
    'SyncWebhook',
    'SyncWebhookMessage',
)

_WEBHOOK_URL_RE = re.compile(
    r'(?P<base>https?://[^\s]*?)/webhooks/(?P<id>[0-9]{1,20})/(?P<token>[A-Za-z0-9._-]{20,})'
)


class _SyncResponse:
    def __init__(self, status: int, reason: str) -> None:
        self.status = status
        self.reason = reason
        self.headers: Dict[str, str] = {}


class SyncWebhookMessage:
    """A message sent by a :class:`SyncWebhook`: the raw data Bisim returned.

    Attributes
    -----------
    id: :class:`int`
        The message ID.
    channel_id: :class:`int`
        The channel the message is in.
    content: :class:`str`
        The message content.
    data: :class:`dict`
        Everything Bisim returned.
    """

    def __init__(self, data: Dict[str, Any], webhook: Optional[SyncWebhook] = None) -> None:
        self.data = data
        self._webhook = webhook
        self.id: int = int(data['id'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.content: str = data.get('content') or ''

    def __repr__(self) -> str:
        return f'<SyncWebhookMessage id={self.id} channel_id={self.channel_id}>'

    def edit(self, **kwargs: Any) -> SyncWebhookMessage:
        """Edits the message. Takes the same parameters as :meth:`SyncWebhook.edit_message`."""
        if self._webhook is None:
            raise ValueError('This message does not know its webhook')
        return self._webhook.edit_message(self.id, **kwargs)

    def delete(self, *, delay: Optional[float] = None) -> None:
        """Deletes the message, after ``delay`` seconds if given (this blocks)."""
        if self._webhook is None:
            raise ValueError('This message does not know its webhook')
        if delay is not None:
            time.sleep(delay)
        self._webhook.delete_message(self.id)


class SyncWebhook:
    """Represents a synchronous Bisim webhook.

    For an asynchronous counterpart, see :class:`Webhook`.

    .. code-block:: python3

        from bisim import SyncWebhook

        webhook = SyncWebhook.from_url('https://api.bisim.gg/api/webhooks/123/abc...')
        webhook.send('Hello World', username='Foo')

    Attributes
    ------------
    id: :class:`int`
        The webhook's ID.
    token: :class:`str`
        The webhook's token.
    """

    def __init__(self, id: int, token: str, *, api_url: str = 'https://api.bisim.gg/api', timeout: float = 15.0) -> None:
        self.id: int = int(id)
        self.token: str = token
        self._api_url: str = api_url.rstrip('/')
        self._timeout = timeout

    def __repr__(self) -> str:
        return f'<SyncWebhook id={self.id!r}>'

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f'{self._api_url}/webhooks/{self.id}/{self.token}'

    @classmethod
    def partial(cls, id: int, token: str, *, session: Any = utils.MISSING, bot_token: Optional[str] = None) -> SyncWebhook:
        """Creates a partial :class:`SyncWebhook` from an ID and a token."""
        return cls(id, token)

    @classmethod
    def from_url(cls, url: str, *, session: Any = utils.MISSING, bot_token: Optional[str] = None) -> SyncWebhook:
        """Creates a partial :class:`SyncWebhook` from a webhook URL.

        Raises
        -------
        ValueError
            The URL is invalid.
        """
        match = _WEBHOOK_URL_RE.search(url)
        if match is None:
            raise ValueError('Invalid webhook URL given.')
        return cls(int(match.group('id')), match.group('token'), api_url=match.group('base'))

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str = '', payload: Any = None, *, query: str = '') -> Any:
        url = self.url + path + query
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {'User-Agent': 'BisimBot (bisim.py)'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        for tries in range(5):
            request = urllib.request.Request(url, data=body, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    text = response.read().decode('utf-8')
                    return json.loads(text) if text else None
            except urllib.error.HTTPError as exc:
                text = exc.read().decode('utf-8', 'replace')
                try:
                    data: Any = json.loads(text) if text else None
                except ValueError:
                    data = text
                if exc.code == 429:
                    retry_after = 1.0
                    if isinstance(data, dict) and data.get('retryAfter') is not None:
                        retry_after = float(data['retryAfter'])
                    elif exc.headers.get('Retry-After'):
                        retry_after = float(exc.headers['Retry-After'])
                    time.sleep(retry_after)
                    continue
                if exc.code in (500, 502, 503, 504) and tries < 4:
                    time.sleep(1 + tries * 2)
                    continue
                response_like = _SyncResponse(exc.code, str(exc.reason))
                if exc.code == 403:
                    raise Forbidden(response_like, data)  # type: ignore
                if exc.code == 404:
                    raise NotFound(response_like, data)  # type: ignore
                if exc.code >= 500:
                    raise BisimServerError(response_like, data)  # type: ignore
                raise HTTPException(response_like, data)  # type: ignore
        raise HTTPException(_SyncResponse(429, 'Too Many Requests'), 'Rate limited too many times')  # type: ignore

    def _upload(self, files: Sequence[File]) -> List[Dict[str, Any]]:
        """The presigned upload flow with the webhook's token: addresses first, then the bytes."""
        if len(files) > 10:
            raise ValueError('files has a maximum of 10 elements.')
        blobs: List[Any] = []
        for f in files:
            if not isinstance(f, File):
                raise TypeError(f'files must be a list of File, not {f.__class__.__name__}')
            blobs.append((f, f._read_all()))
        request = [{'fileName': f._filename, 'contentType': f.content_type, 'sizeBytes': len(data)} for f, data in blobs]
        answer = self._request('POST', '/attachments', {'files': request})
        slots = answer.get('attachments') if isinstance(answer, dict) else None
        if not isinstance(slots, list) or len(slots) != len(blobs):
            raise InvalidData('Bisim did not return an upload address for every file.')
        entries: List[Dict[str, Any]] = []
        for (f, data), slot in zip(blobs, slots):
            put = urllib.request.Request(
                slot['uploadUrl'], data=data, method='PUT', headers={'Content-Type': f.content_type}
            )
            try:
                with urllib.request.urlopen(put, timeout=max(self._timeout, 60.0)) as response:
                    response.read()
            except urllib.error.HTTPError as exc:
                raise HTTPException(_SyncResponse(exc.code, str(exc.reason)), 'uploading the file failed')  # type: ignore
            entry: Dict[str, Any] = {
                'id': str(slot['id']),
                'uploadFilename': slot['uploadFilename'],
                'fileName': f._filename,
                'contentType': f.content_type,
                'sizeBytes': len(data),
            }
            if f.description:
                entry['description'] = f.description
            if f.spoiler:
                entry['spoiler'] = True
            entries.append(entry)
        return entries

    def _payload(
        self,
        *,
        content: Any,
        embed: Any,
        embeds: Any,
        file: Any = utils.MISSING,
        files: Any = utils.MISSING,
        attachments: Any = utils.MISSING,
        allowed_mentions: Any = utils.MISSING,
        flags: Optional[int] = None,
        editing: bool = False,
    ) -> Dict[str, Any]:
        from ..abc import _embeds_payload, _file_names, _kept_attachment

        if file is not utils.MISSING and files is not utils.MISSING:
            raise TypeError('Cannot mix file and files keyword arguments.')
        upload: List[File] = [file] if file is not utils.MISSING and file is not None else list(files or [])
        kept_items: List[Any] = []
        if attachments is not utils.MISSING and attachments is not None:
            for item in attachments:
                (upload if isinstance(item, File) else kept_items).append(item)

        payload: Dict[str, Any] = {}
        if content is not utils.MISSING:
            if content is not None:
                payload['content'] = str(content)
            elif editing:
                payload['content'] = ''
        names: Any = None if (editing and attachments is utils.MISSING) else _file_names(upload, kept_items)
        if embed is not utils.MISSING or embeds is not utils.MISSING:
            if embed is None and embeds is utils.MISSING:
                payload['embeds'] = []
            else:
                built = _embeds_payload(
                    embed if embed is not utils.MISSING else None, embeds if embeds is not utils.MISSING else None, names
                )
                payload['embeds'] = built or []
            if not editing and not payload['embeds']:
                del payload['embeds']
        if flags is not None:
            payload['flags'] = flags
        if allowed_mentions is not utils.MISSING and allowed_mentions is not None:
            payload['allowedMentions'] = allowed_mentions.to_dict()
        kept = [_kept_attachment(item) for item in kept_items]
        if upload:
            try:
                payload['attachments'] = kept + self._upload(upload)
            finally:
                for f in upload:
                    f.close()
        elif attachments is not utils.MISSING:
            payload['attachments'] = kept
        return payload

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def send(
        self,
        content: str = utils.MISSING,
        *,
        username: str = utils.MISSING,
        avatar_url: Any = utils.MISSING,
        tts: bool = False,
        file: Any = utils.MISSING,
        files: Any = utils.MISSING,
        embed: Embed = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        allowed_mentions: Any = utils.MISSING,
        thread: Any = utils.MISSING,
        thread_name: str = utils.MISSING,
        wait: bool = False,
        suppress_embeds: bool = False,
        silent: bool = False,
        view: Any = utils.MISSING,
        poll: Any = utils.MISSING,
    ) -> Optional[SyncWebhookMessage]:
        """Sends a message using the webhook.

        Takes the same parameters as :meth:`Webhook.send`, with the same
        Bisim limits (no views, threads or polls). Files are uploaded first,
        then named in the message, as :meth:`Webhook.send` does.

        Returns
        ---------
        Optional[:class:`SyncWebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.
        """
        if thread is not utils.MISSING or thread_name is not utils.MISSING:
            raise NotSupported('Threads')
        if view is not utils.MISSING and view is not None:
            raise NotSupported('Components on webhook messages')
        if poll is not utils.MISSING and poll is not None:
            raise NotSupported('Polls through a webhook')

        from ..abc import _flags_value

        payload = self._payload(
            content=content,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            flags=_flags_value(silent=silent, suppress_embeds=suppress_embeds) or None,
        )
        if username is not utils.MISSING and username:
            payload['username'] = username
        data = self._request('POST', '', payload, query='?wait=true' if wait else '')
        if wait and isinstance(data, dict):
            return SyncWebhookMessage(data, self)
        return None

    def fetch_message(self, id: int, /, *, thread: Any = utils.MISSING) -> SyncWebhookMessage:
        """Retrieves a message this webhook posted.

        Raises
        --------
        NotFound
            The message was not found, or this webhook did not post it.
        """
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        return SyncWebhookMessage(self._request('GET', f'/messages/{int(id)}'), self)

    def edit_message(
        self,
        message_id: int,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Any] = utils.MISSING,
        view: Any = utils.MISSING,
        allowed_mentions: Any = None,
        thread: Any = utils.MISSING,
        suppress_embeds: bool = utils.MISSING,
    ) -> SyncWebhookMessage:
        """Edits a message this webhook posted.

        Takes the same parameters as :meth:`Webhook.edit_message`.
        """
        if view is not utils.MISSING and view is not None:
            raise NotSupported('Components on webhook messages')
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        payload = self._payload(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            allowed_mentions=allowed_mentions,
            flags=None if suppress_embeds is utils.MISSING else (4 if suppress_embeds else 0),
            editing=True,
        )
        return SyncWebhookMessage(self._request('PATCH', f'/messages/{int(message_id)}', payload), self)

    def delete_message(self, message_id: int, /, *, thread: Any = utils.MISSING) -> None:
        """Deletes a message this webhook posted."""
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        self._request('DELETE', f'/messages/{int(message_id)}')
