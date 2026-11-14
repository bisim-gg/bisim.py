"""
bisim.ext.voice_recv
~~~~~~~~~~~~~~~~~~~~

Receiving voice: hear what people say in a voice channel.

The API follows ``discord-ext-voice-recv``, the add-on most discord.py bots
use for this: connect with ``cls=VoiceRecvClient``, then ``vc.listen(sink)``.
Needs ``pip install "bisim.py[voice]"``.
"""

from .reader import *
from .sinks import *
from .voice_client import *
