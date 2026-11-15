"""Voice connections: :class:`VoiceProtocol` and :class:`VoiceClient`.

A bot joins a voice channel with ``await channel.connect()``, as in
discord.py, and plays sound with :meth:`VoiceClient.play`. On Bisim the media
goes through LiveKit (``pip install "bisim.py[voice]"``); there is no PyNaCl,
Opus or DAVE to install.

Adapted from discord.py's ``voice_client.py`` (MIT, Copyright (c) 2015-present
Rapptz; see LICENSE).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple

from . import opus
from .errors import ClientException
from .player import AudioPlayer, AudioSource
from .utils import MISSING
from .voice_state import VoiceConnectionState, _rtc

if TYPE_CHECKING:
    from . import abc
    from .channel import VoiceChannel
    from .client import Client
    from .guild import Guild
    from .state import ConnectionState
    from .user import ClientUser

__all__ = (
    'VoiceProtocol',
    'VoiceClient',
)

_log = logging.getLogger(__name__)


class VoiceProtocol:
    """A class that represents the Bisim voice protocol.

    This is an abstract class. The library provides a concrete implementation
    under :class:`VoiceClient`.

    This class allows you to implement a protocol to allow for an external
    method of sending voice.

    These classes are passed to :meth:`abc.Connectable.connect <VoiceChannel.connect>`.

    On Bisim, :meth:`Guild.change_voice_state` joins the channel over REST and
    hands the answer (the LiveKit address as ``endpoint`` and its ``token``) to
    :meth:`on_voice_server_update`.

    Parameters
    ------------
    client: :class:`Client`
        The client (or its subclasses) that started the connection request.
    channel: :class:`abc.Connectable`
        The voice channel that is being connected to.
    """

    #: Whether :meth:`abc.Connectable.connect` joins deafened when ``self_deaf`` is left out. A bot is deafened
    #: unless it asks to hear (Bisim enforces it: a deafened bot receives no audio); a protocol that receives
    #: audio, such as :class:`~bisim.ext.voice_recv.VoiceRecvClient`, sets this to ``False``.
    deaf_by_default: bool = True

    def __init__(self, client: Client, channel: abc.Connectable) -> None:
        self.client: Client = client
        self.channel: abc.Connectable = channel

    async def on_voice_state_update(self, data: Dict[str, Any], /) -> None:
        """|coro|

        An abstract method that is called when the client's voice state
        has changed. This corresponds to ``VOICE_STATE_UPDATE``.

        .. warning::

            This method is not the same as the event. See: :func:`on_voice_state_update`

        Parameters
        ------------
        data: :class:`dict`
            The raw voice state payload (Bisim's camelCase fields, with
            ``channelId`` and ``guildId``).
        """
        raise NotImplementedError

    async def on_voice_server_update(self, data: Dict[str, Any], /) -> None:
        """|coro|

        An abstract method that is called when initially connecting to voice.
        On Bisim it is called by :meth:`Guild.change_voice_state` with the
        join's answer.

        Parameters
        ------------
        data: :class:`dict`
            The join's answer: ``token`` (a LiveKit token), ``endpoint`` (the
            LiveKit address, also as ``url``), ``guild_id`` and ``channel_id``,
            plus Bisim's ``canPublish``.
        """
        raise NotImplementedError

    async def on_voice_move(self, data: Dict[str, Any], /) -> None:
        """|coro|

        Called when a moderator moved the bot to another voice channel
        (Bisim's ``VOICE_MOVE``). The server holds a one-time grant for the
        target channel; the default joins it with :meth:`Guild.change_voice_state`.

        Parameters
        ------------
        data: :class:`dict`
            ``guildId``, ``fromChannelId`` and ``toChannelId``.
        """
        guild = getattr(self.channel, 'guild', None)
        to_id = data.get('toChannelId')
        if guild is None or not to_id:
            return
        target = guild.get_channel(int(to_id))
        if target is not None:
            await guild.change_voice_state(channel=target)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False) -> None:
        """|coro|

        An abstract method called when the client initiates the connection request.

        When a connection is requested initially, the library calls the constructor
        under ``__init__`` and then calls :meth:`connect`. If :meth:`connect` fails at
        some point then :meth:`disconnect` is called.

        Within this method, to start the voice connection flow it is recommended to
        use :meth:`Guild.change_voice_state` to start the flow. After which,
        :meth:`on_voice_server_update` is called with what is needed to connect.

        Parameters
        ------------
        timeout: :class:`float`
            The timeout for the connection.
        reconnect: :class:`bool`
            Whether reconnection is expected.
        self_mute: :class:`bool`
            Indicates if the client should be self-muted.
        self_deaf: :class:`bool`
            Indicates if the client should be self-deafened.
        """
        raise NotImplementedError

    async def disconnect(self, *, force: bool) -> None:
        """|coro|

        An abstract method called when the client terminates the connection.

        See :meth:`cleanup`.

        Parameters
        ------------
        force: :class:`bool`
            Whether the disconnection was forced.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """This method *must* be called to ensure proper clean-up during a disconnect.

        It is advisable to call this from within :meth:`disconnect` when you are
        completely done with the voice protocol instance.

        This method removes it from the internal state cache that keeps track of
        currently alive voice clients. Failure to clean-up will cause subsequent
        connections to report that it's still connected.
        """
        key_id, _ = self.channel._get_voice_client_key()  # type: ignore
        self.client._connection._remove_voice_client(key_id, self)


class VoiceClient(VoiceProtocol):
    """Represents a Bisim voice connection.

    You do not create these, you typically get them from
    e.g. :meth:`VoiceChannel.connect`.

    The bot publishes one audio track (as a microphone) into the channel's
    LiveKit room and plays any :class:`AudioSource` into it at the right pace.
    What differs from Discord:

    - sound only: a bot never sends video or a screen share;
    - one voice channel per server: joining another channel of the same server
      leaves the first (use :meth:`move_to`);
    - no DM or group DM calls;
    - nothing to install besides ``bisim.py[voice]`` (and ffmpeg to play files
      and URLs): Bisim's voice takes PCM, so there is no PyNaCl or Opus.

    Warning
    --------
    Voice needs LiveKit's Python SDK: ``pip install "bisim.py[voice]"``.
    Creating a voice client without it raises :exc:`RuntimeError`.

    Attributes
    -----------
    session_id: Optional[:class:`str`]
        Always ``None`` on Bisim.
    token: :class:`str`
        The LiveKit token of the current connection.
    endpoint: :class:`str`
        The LiveKit address of the current connection.
    channel: :class:`VoiceChannel`
        The voice channel connected to.
    """

    channel: VoiceChannel

    def __init__(self, client: Client, channel: abc.Connectable) -> None:
        _rtc()

        super().__init__(client, channel)
        state = client._connection
        self.server_id: int = MISSING
        self.loop: asyncio.AbstractEventLoop = state.loop  # type: ignore
        self._state: ConnectionState = state

        self.sequence: int = 0
        self.timestamp: int = 0
        self._player: Optional[AudioPlayer] = None
        self.encoder: opus.Encoder = MISSING

        self._connection: VoiceConnectionState = self.create_connection_state()

    warn_nacl: bool = False
    warn_dave: bool = False
    supported_modes: Tuple[str, ...] = ()

    @property
    def guild(self) -> Guild:
        """:class:`Guild`: The guild we're connected to."""
        return self.channel.guild

    @property
    def user(self) -> ClientUser:
        """:class:`ClientUser`: The user connected to voice (i.e. ourselves)."""
        return self._state.user  # type: ignore

    @property
    def session_id(self) -> Optional[str]:
        return None

    @property
    def token(self) -> Optional[str]:
        return self._connection.token

    @property
    def endpoint(self) -> Optional[str]:
        return self._connection.endpoint

    @property
    def timeout(self) -> float:
        return self._connection.timeout

    @property
    def self_mute(self) -> bool:
        """:class:`bool`: Whether the bot muted itself (its track is muted, nobody hears it)."""
        return self._connection.self_mute

    @property
    def self_deaf(self) -> bool:
        """:class:`bool`: Whether the bot deafened itself (it receives no audio)."""
        return self._connection.self_deaf

    @property
    def room(self) -> Any:
        """The LiveKit ``rtc.Room`` of the connection, or ``None`` while not connected.

        For what the library does not cover; leave the room to the library.
        """
        return self._connection.room

    def checked_add(self, attr: str, value: int, limit: int) -> None:
        val = getattr(self, attr)
        if val + value > limit:
            setattr(self, attr, 0)
        else:
            setattr(self, attr, val + value)

    # connection related

    def create_connection_state(self) -> VoiceConnectionState:
        return VoiceConnectionState(self)

    async def on_voice_state_update(self, data: Dict[str, Any]) -> None:
        await self._connection.voice_state_update(data)

    async def on_voice_server_update(self, data: Dict[str, Any]) -> None:
        await self._connection.voice_server_update(data)

    async def on_voice_move(self, data: Dict[str, Any]) -> None:
        await self._connection.voice_move(data)

    async def connect(self, *, reconnect: bool, timeout: float, self_deaf: bool = False, self_mute: bool = False) -> None:
        await self._connection.connect(reconnect=reconnect, timeout=timeout, self_deaf=self_deaf, self_mute=self_mute)

    def wait_until_connected(self, timeout: Optional[float] = 30.0) -> bool:
        self._connection.wait(timeout)
        return self._connection.is_connected()

    @property
    def latency(self) -> float:
        """:class:`float`: The round trip time to the voice server in seconds.

        Measured on the connection LiveKit uses, every few seconds; ``inf``
        until the first measurement.
        """
        return self._connection.latency

    @property
    def average_latency(self) -> float:
        """:class:`float`: Average of the most recent 20 round trip times in seconds."""
        return self._connection.average_latency

    async def disconnect(self, *, force: bool = False) -> None:
        """|coro|

        Disconnects this voice client from voice.
        """
        self.stop()
        await self._connection.disconnect(force=force)
        self.cleanup()

    async def move_to(self, channel: Optional[abc.Snowflake], *, timeout: Optional[float] = 30.0) -> None:
        """|coro|

        Moves you to a different voice channel.

        The server leaves the old channel as part of joining the new one
        (a bot sits in one voice channel per server). What is playing keeps
        playing after the move.

        Parameters
        -----------
        channel: Optional[:class:`abc.Snowflake`]
            The channel to move to. Must be a voice channel. ``None``
            disconnects.
        timeout: Optional[:class:`float`]
            How long to wait for the move to complete.

        Raises
        -------
        asyncio.TimeoutError
            The move did not complete in time, but may still be ongoing.
        """
        if channel is not None and not hasattr(channel, 'guild'):
            resolved = self.guild.get_channel(channel.id)
            if resolved is None:
                raise ClientException('Unknown voice channel.')
            channel = resolved
        await self._connection.move_to(channel, timeout)

    def is_connected(self) -> bool:
        """Indicates if the voice client is connected to voice."""
        return self._connection.is_connected()

    async def _change_voice_state(
        self, channel: Optional[abc.Snowflake], *, self_mute: Optional[bool] = None, self_deaf: Optional[bool] = None
    ) -> None:
        if channel is None:
            await self.disconnect(force=True)
            return
        # Left out, each stays as it is: following a moderator's move must not undeafen the bot.
        self_mute = self._connection.self_mute if self_mute is None else self_mute
        self_deaf = self._connection.self_deaf if self_deaf is None else self_deaf
        if channel.id != self.channel.id:
            self._connection.self_mute = self_mute
            self._connection.self_deaf = self_deaf
            await self.move_to(channel)
            return
        await self._connection.set_self_state(self_mute=self_mute, self_deaf=self_deaf)

    # audio related

    def play(
        self,
        source: AudioSource,
        *,
        after: Optional[Callable[[Optional[Exception]], Any]] = None,
        application: str = 'audio',
        bitrate: int = 128,
        fec: bool = True,
        expected_packet_loss: float = 0.15,
        bandwidth: str = 'full',
        signal_type: str = 'auto',
    ) -> None:
        """Plays an :class:`AudioSource`.

        The finalizer, ``after`` is called after the source has been exhausted
        or an error occurred.

        If an error happens while the audio player is running, the exception is
        caught and the audio player is then stopped.  If no after callback is
        passed, any caught exception will be logged using the library logger.

        The encoder parameters are accepted for compatibility and have no
        effect: Bisim's voice server encodes the sound itself.

        Parameters
        -----------
        source: :class:`AudioSource`
            The audio source we're reading from.
        after: Callable[[Optional[:class:`Exception`]], Any]
            The finalizer that is called after the stream is exhausted.
            This function must have a single parameter, ``error``, that
            denotes an optional exception that was raised during playing.
            It is called from the player's thread.
        application: :class:`str`
            No effect on Bisim.
        bitrate: :class:`int`
            No effect on Bisim.
        fec: :class:`bool`
            No effect on Bisim.
        expected_packet_loss: :class:`float`
            No effect on Bisim.
        bandwidth: :class:`str`
            No effect on Bisim.
        signal_type: :class:`str`
            No effect on Bisim.

        Raises
        -------
        ClientException
            Already playing audio, not connected, or the source is Opus
            encoded (Bisim takes PCM).
        TypeError
            Source is not a :class:`AudioSource` or after is not a callable.
        """

        if not self.is_connected():
            raise ClientException('Not connected to voice.')

        if self.is_playing():
            raise ClientException('Already playing audio.')

        if not isinstance(source, AudioSource):
            raise TypeError(f'source must be an AudioSource not {source.__class__.__name__}')

        if source.is_opus():
            raise ClientException('Bisim voice takes PCM: use FFmpegPCMAudio or FFmpegOpusAudio, which decode with ffmpeg.')

        self.encoder = opus.Encoder()
        self._player = AudioPlayer(source, self, after=after)
        self._player.start()

    def is_playing(self) -> bool:
        """Indicates if we're currently playing audio."""
        return self._player is not None and self._player.is_playing()

    def is_paused(self) -> bool:
        """Indicates if we're playing audio, but if we're paused."""
        return self._player is not None and self._player.is_paused()

    def stop(self) -> None:
        """Stops playing audio."""
        if self._player:
            self._player.stop()
            self._player = None
            self._clear_audio()

    def pause(self) -> None:
        """Pauses the audio playing."""
        if self._player:
            self._player.pause()
            self._clear_audio()

    def resume(self) -> None:
        """Resumes the audio playing."""
        if self._player:
            self._player.resume()

    @property
    def source(self) -> Optional[AudioSource]:
        """Optional[:class:`AudioSource`]: The audio source being played, if playing.

        This property can also be used to change the audio source currently being played.
        """
        return self._player.source if self._player else None

    @source.setter
    def source(self, value: AudioSource) -> None:
        if not isinstance(value, AudioSource):
            raise TypeError(f'expected AudioSource not {value.__class__.__name__}.')

        if self._player is None:
            raise ValueError('Not playing anything.')

        self._player.set_source(value)

    def send_audio_packet(self, data: bytes, *, encode: bool = True) -> None:
        """Sends an audio packet composed of the data.

        You must be connected to play audio.

        Parameters
        ----------
        data: :class:`bytes`
            The :term:`py:bytes-like object` denoting 20 ms of 16-bit 48 kHz
            stereo PCM.
        encode: :class:`bool`
            Kept for compatibility. Bisim takes PCM only, so ``False`` (data
            that is already Opus) raises :exc:`ClientException`.

        Raises
        -------
        ClientException
            The data is Opus.
        """
        if not encode:
            raise ClientException('Bisim voice takes PCM, not Opus.')
        self.checked_add('sequence', 1, 65535)
        self._connection.send_audio(data)
        self.checked_add('timestamp', opus.Encoder.SAMPLES_PER_FRAME, 4294967295)

    def _clear_audio(self) -> None:
        self._connection.clear_audio()

    # Hooks for receiving, used by bisim.ext.voice_recv.

    def _wants_audio(self) -> bool:
        return False

    def _on_audio_track(self, track: Any, participant: Any) -> None:
        pass

    def _on_audio_track_gone(self, track: Any, participant: Any) -> None:
        pass

    def _on_participant_left(self, participant: Any) -> None:
        pass

    def _on_active_speakers(self, speakers: Any) -> None:
        pass
