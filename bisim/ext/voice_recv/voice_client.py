from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Set, Union

from ...errors import ClientException
from ...voice_client import VoiceClient
from .reader import AudioReader
from .sinks import AudioSink

if TYPE_CHECKING:
    from ...abc import Connectable
    from ...client import Client
    from ...member import Member
    from ...user import User

    User_ = Union[Member, User]

__all__ = ('VoiceRecvClient',)

_log = logging.getLogger(__name__)


class VoiceRecvClient(VoiceClient):
    """A :class:`~bisim.VoiceClient` that can also receive audio.

    Connect with it as ``await channel.connect(cls=VoiceRecvClient)``, then
    call :meth:`listen` with a sink. Everything a :class:`~bisim.VoiceClient`
    does (playing, moving, leaving) works the same.

    The bot receives the others' audio only while it listens and is not
    self-deafened (a server deafen also stops it): Bisim enforces both on
    its media server. Connecting with this class joins undeafened unless
    ``self_deaf=True`` is passed, and :meth:`listen` on a deafened client
    turns its deafen off first. Each person's audio arrives separately, as
    20 ms of 16-bit 48 kHz stereo PCM per :meth:`AudioSink.write`.

    Events, both on the client (``@bot.event``) and on the sink's listeners,
    while listening:

    - ``on_voice_member_speaking_start(member)``
    - ``on_voice_member_speaking_stop(member)``
    - ``on_voice_member_disconnect(member, ssrc)``
    """

    #: Listening is hearing: this client joins undeafened unless told otherwise.
    deaf_by_default = False

    def __init__(self, client: Client, channel: Connectable) -> None:
        super().__init__(client, channel)
        self._reader: Optional[AudioReader] = None
        self._speaking: Set[int] = set()
        self._ssrc_by_identity: Dict[str, int] = {}
        self._next_ssrc = 1

    # -- listening -----------------------------------------------------------

    def listen(self, sink: AudioSink, *, after: Optional[Callable[[Optional[Exception]], Any]] = None) -> None:
        """Receives audio into an :class:`AudioSink`.

        The finalizer, ``after``, is called once listening stops (after the
        sink's :meth:`~AudioSink.cleanup`), with the error that stopped it if
        any. It runs on the receive thread.

        A self-deafened bot is undeafened first (Bisim sends a deafened bot
        no audio); audio arrives once Bisim has the change.

        Raises
        -------
        ClientException
            Already listening or not connected.
        TypeError
            sink is not an :class:`AudioSink` or after is not a callable.
        """
        if not self.is_connected():
            raise ClientException('Not connected to voice.')
        if not isinstance(sink, AudioSink):
            raise TypeError(f'sink must be an AudioSink not {sink.__class__.__name__}')
        if self.is_listening():
            raise ClientException('Already receiving audio.')

        self._reader = AudioReader(sink, self, after=after)
        self._reader.start()
        if self._connection.self_deaf:
            # Asking to listen is asking to hear. The subscriptions follow once Bisim has the change.
            _log.info('Listening turns the self deafen off.')
            self.loop.create_task(
                self._connection.set_self_state(self_mute=self._connection.self_mute, self_deaf=False)
            )
        room = self.room
        if room is not None:
            from ...voice_state import _rtc

            audio = _rtc().TrackKind.KIND_AUDIO
            for participant in list(room.remote_participants.values()):
                for publication in list(participant.track_publications.values()):
                    track = getattr(publication, 'track', None)
                    if publication.kind == audio and track is not None and publication.subscribed:
                        self._on_audio_track(track, participant)
        self._connection.sync_subscriptions()

    def is_listening(self) -> bool:
        """Indicates if we're currently receiving audio."""
        return self._reader is not None and self._reader.is_listening()

    def stop_listening(self) -> None:
        """Stops receiving audio."""
        reader = self._reader
        if reader is not None:
            self._reader = None
            reader.stop()
            self._connection.sync_subscriptions()

    def stop_playing(self) -> None:
        """Stops playing audio."""
        super().stop()

    def stop(self) -> None:
        """Stops playing and receiving audio."""
        self.stop_playing()
        self.stop_listening()

    @property
    def sink(self) -> Optional[AudioSink]:
        """Optional[:class:`AudioSink`]: The sink receiving audio, if listening.

        Setting it swaps the sink while listening; the old one is not cleaned up.
        """
        return self._reader.sink if self._reader else None

    @sink.setter
    def sink(self, sink: AudioSink) -> None:
        if not isinstance(sink, AudioSink):
            raise TypeError(f'expected AudioSink not {sink.__class__.__name__}.')
        if self._reader is None:
            raise ValueError('Not receiving anything.')
        self._reader.set_sink(sink)

    def get_speaking(self, member: Any) -> Optional[bool]:
        """Returns whether someone in the channel is speaking now, or ``None`` if they are not in it."""
        room = self.room
        if room is None:
            return None
        identity = str(member.id)
        if identity not in room.remote_participants:
            return None
        return member.id in self._speaking

    # -- who is who ------------------------------------------------------------

    def _ssrc_for(self, participant: Any) -> int:
        identity = str(getattr(participant, 'identity', ''))
        ssrc = self._ssrc_by_identity.get(identity)
        if ssrc is None:
            ssrc = self._ssrc_by_identity[identity] = self._next_ssrc
            self._next_ssrc += 1
        return ssrc

    def _user_for(self, participant: Any) -> Optional[User_]:
        try:
            user_id = int(participant.identity)
        except (TypeError, ValueError):
            return None
        member = self.guild.get_member(user_id)
        if member is not None:
            return member
        state = self._state
        user = state.get_user(user_id)
        if user is not None:
            return user
        data: Dict[str, Any] = {'id': user_id, 'username': getattr(participant, 'name', '') or str(user_id)}
        try:
            import json

            meta = json.loads(participant.metadata or '{}')
            data.update(username=meta.get('username') or data['username'], displayName=meta.get('displayName'), avatarKey=meta.get('avatarKey'))
        except Exception:
            pass
        try:
            return state.store_user(data)
        except Exception:
            return None

    # -- hooks from the connection ---------------------------------------------

    def _wants_audio(self) -> bool:
        return self.is_listening()

    def _on_audio_track(self, track: Any, participant: Any) -> None:
        reader = self._reader
        if reader is not None:
            reader.add_track(track, participant, self._ssrc_for(participant))

    def _on_audio_track_gone(self, track: Any, participant: Any) -> None:
        reader = self._reader
        if reader is not None:
            reader.remove_track(track)

    def _on_participant_left(self, participant: Any) -> None:
        user = self._user_for(participant)
        ssrc = self._ssrc_for(participant)
        if user is not None and user.id in self._speaking:
            self._speaking.discard(user.id)
            self._dispatch('voice_member_speaking_stop', user)
        if user is not None:
            self._dispatch('voice_member_disconnect', user, ssrc)
        self._ssrc_by_identity.pop(str(getattr(participant, 'identity', '')), None)

    def _on_active_speakers(self, speakers: Any) -> None:
        room = self.room
        local = None
        try:
            local = room.local_participant.identity if room is not None else None
        except Exception:
            pass
        now: Dict[int, Any] = {}
        for participant in speakers or []:
            if getattr(participant, 'identity', None) == local:
                continue
            user = self._user_for(participant)
            if user is not None:
                now[user.id] = user
        for user_id, user in now.items():
            if user_id not in self._speaking:
                self._speaking.add(user_id)
                self._dispatch('voice_member_speaking_start', user)
        for user_id in list(self._speaking):
            if user_id not in now:
                self._speaking.discard(user_id)
                user = self.guild.get_member(user_id) or self._state.get_user(user_id)
                if user is not None:
                    self._dispatch('voice_member_speaking_stop', user)

    def _dispatch(self, event: str, *args: Any) -> None:
        reader = self._reader
        if reader is None or not reader.is_listening():
            return
        self.client.dispatch(event, *args)
        reader.dispatch(event, *args)
