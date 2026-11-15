"""
Bisim API Wrapper
~~~~~~~~~~~~~~~~~

The official library for building Bisim (bisim.gg) bots, with the discord.py
2.x API: a bot written for discord.py runs by changing ``import discord`` to
``import bisim``.

:copyright: (c) 2026 Bisim
:license: MIT, see LICENSE for more details.
"""

__title__ = 'bisim'
__author__ = 'Bisim'
__license__ = 'MIT'
__copyright__ = 'Copyright 2026 Bisim'
__version__ = '0.2.0'

__path__ = __import__('pkgutil').extend_path(__path__, __name__)

import logging
from typing import Literal, NamedTuple

from . import abc as abc
from . import app_commands as app_commands
from . import opus as opus
from . import ui as ui
from . import utils as utils
from .activity import *
from .appinfo import *
from .asset import *
from .audit_logs import *
from .automod import *
from .channel import *
from .client import *
from .colour import *
from .components import *
from .embeds import *
from .emoji import *
from .enums import *
from .errors import *
from .file import *
from .flags import *
from .guild import *
from .interactions import *
from .invite import *
from .member import *
from .mentions import *
from .message import *
from .object import *
from .partial_emoji import *
from .permissions import *
from .player import *
from .poll import *
from .raw_models import *
from .reaction import *
from .role import *
from .soundboard import *
from .sticker import *
from .user import *
from .voice_client import *
from .webhook import *


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: Literal['alpha', 'beta', 'candidate', 'final']
    serial: int


version_info: VersionInfo = VersionInfo(major=0, minor=2, micro=0, releaselevel='final', serial=0)

logging.getLogger(__name__).addHandler(logging.NullHandler())

del logging, NamedTuple, Literal
