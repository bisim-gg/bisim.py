"""Opus, as far as a bot on Bisim needs it: not at all.

On Discord a bot encodes its sound to Opus itself, so discord.py loads libopus
and music bots call ``discord.opus.load_opus()``. On Bisim the voice transport
(LiveKit) takes plain PCM and encodes it, so there is nothing to load. This
module keeps those calls working: :func:`load_opus` does nothing and
:func:`is_loaded` is always ``True``. :class:`Encoder` only carries the frame
constants the audio sources use.
"""

from __future__ import annotations

from typing import Any

from .errors import BisimException

__all__ = (
    'Encoder',
    'OpusError',
    'OpusNotLoaded',
    'is_loaded',
    'load_opus',
)


class OpusError(BisimException):
    """An exception that is thrown for libopus related errors.

    Kept for compatibility: nothing on Bisim raises it.

    Attributes
    ----------
    code: :class:`int`
        The error code returned.
    """

    def __init__(self, code: int = 0, message: str = 'Opus is not used on Bisim'):
        self.code: int = code
        super().__init__(message)


class OpusNotLoaded(BisimException):
    """An exception that is thrown for when libopus is not loaded.

    Kept for compatibility: Opus never needs to be loaded on Bisim.
    """

    pass


class Encoder:
    """The audio frame constants of a voice connection.

    Bisim's voice takes 16-bit 48 kHz stereo PCM in 20 ms frames, the same
    format discord.py's sources produce. There is no Opus encoder to
    configure: :meth:`encode` returns the PCM unchanged.
    """

    SAMPLING_RATE = 48000
    CHANNELS = 2
    FRAME_LENGTH = 20  # in milliseconds
    SAMPLE_SIZE = 2 * CHANNELS  # (bit_rate / 8) * channels (bytes per sample)
    SAMPLES_PER_FRAME = int(SAMPLING_RATE / 1000 * FRAME_LENGTH)
    FRAME_SIZE = SAMPLES_PER_FRAME * SAMPLE_SIZE

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def encode(self, pcm: bytes, frame_size: int = SAMPLES_PER_FRAME) -> bytes:
        return pcm


def load_opus(name: str) -> None:
    """Does nothing: Bisim's voice does not use libopus.

    Kept so code written for discord.py (``discord.opus.load_opus(...)``) runs
    unchanged.
    """
    return None


def is_loaded() -> bool:
    """Always ``True``: there is nothing to load on Bisim."""
    return True


def _load_default() -> bool:
    return True
