from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from . import utils
from .asset import Asset
from .flags import ApplicationFlags
from .permissions import Permissions

if TYPE_CHECKING:
    from .state import ConnectionState
    from .user import User

__all__ = (
    'AppInfo',
    'PartialAppInfo',
    'AppInstallParams',
    'IntegrationTypeConfig',
)


class AppInstallParams:
    """Represents the settings for the custom authorization URL of an application.

    Attributes
    ----------
    scopes: List[:class:`str`]
        The list of OAuth2 scopes to add the application to a guild with.
    permissions: :class:`Permissions`
        The permissions to give to application in the guild.
    """

    __slots__ = ('scopes', 'permissions')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.scopes: List[str] = data.get('scopes', ['bot'])
        self.permissions: Permissions = Permissions(int(data.get('permissions', 0) or 0))


class IntegrationTypeConfig:
    """Kept for compatibility; Bisim apps are always added to servers."""

    __slots__ = ('oauth2_install_params',)

    def __init__(self, data: Dict[str, Any]) -> None:
        self.oauth2_install_params: Optional[AppInstallParams] = None


class AppInfo:
    """Represents the application info for the bot provided by Bisim.

    On Bisim an application *is* its bot: :attr:`id` is the bot's user ID.

    Attributes
    -------------
    id: :class:`int`
        The application ID (also the bot's user ID).
    name: :class:`str`
        The application name.
    owner: :class:`User`
        The application owner (a partial user when only the ID is known).
    description: :class:`str`
        The application description.
    bot_public: :class:`bool`
        Whether anyone may add the bot to a server, or only its owner.
    bot_require_code_grant: :class:`bool`
        Always ``False``.
    verify_key: :class:`str`
        The hex encoded Ed25519 key for interaction verification.
    interactions_endpoint_url: Optional[:class:`str`]
        The Interactions URL, if the application has one.
    team: Optional[Any]
        Always ``None``.
    terms_of_service_url: Optional[:class:`str`]
        Always ``None``.
    privacy_policy_url: Optional[:class:`str`]
        Always ``None``.
    tags: List[:class:`str`]
        Always empty.
    guild_count: Optional[:class:`int`]
        Always ``None``.
    """

    __slots__ = (
        '_state',
        'description',
        'id',
        'name',
        'bot_public',
        'bot_require_code_grant',
        'owner',
        '_icon',
        'verify_key',
        'team',
        'guild_id',
        'primary_sku_id',
        'slug',
        'terms_of_service_url',
        'privacy_policy_url',
        'tags',
        'custom_install_url',
        'install_params',
        'role_connections_verification_url',
        'interactions_endpoint_url',
        'redirect_uris',
        'approximate_guild_count',
        'approximate_user_install_count',
        '_flags',
        '_cover_image',
        'guild_count',
    )

    def __init__(self, state: ConnectionState, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self.description: str = data.get('description') or ''
        self._icon: Optional[str] = data.get('avatarKey') or None
        self.bot_public: bool = bool(data.get('botPublic', True))
        self.bot_require_code_grant: bool = False
        owner_id = utils._snowflake(data.get('ownerId'))
        owner_data = data.get('owner')
        if isinstance(owner_data, dict) and owner_data.get('id'):
            self.owner: User = state.create_user(owner_data)
        else:
            self.owner = state.get_user(owner_id) or state.create_user({'id': owner_id or 0, 'username': ''})  # type: ignore
        self.team: Optional[Any] = None
        self.verify_key: str = data.get('publicKey') or ''
        self.guild_id: Optional[int] = None
        self.primary_sku_id: Optional[int] = None
        self.slug: Optional[str] = None
        self.terms_of_service_url: Optional[str] = None
        self.privacy_policy_url: Optional[str] = None
        self.tags: List[str] = []
        self.custom_install_url: Optional[str] = None
        self.install_params: Optional[AppInstallParams] = None
        self.role_connections_verification_url: Optional[str] = None
        self.interactions_endpoint_url: Optional[str] = data.get('interactionsUrl') or None
        self.redirect_uris: List[str] = []
        self.approximate_guild_count: int = int(data.get('guildCount', 0) or 0)
        self.approximate_user_install_count: Optional[int] = None
        self._flags: int = 0
        self._cover_image: Optional[str] = None
        self.guild_count: Optional[int] = None

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.id} name={self.name!r} description={self.description!r} owner={self.owner!r}>'

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`.Asset`]: Retrieves the application's icon asset, if any."""
        if self._icon is None:
            return None
        return Asset._from_key(self._state, self._icon)

    @property
    def cover_image(self) -> Optional[Asset]:
        """Optional[:class:`.Asset`]: Always ``None``."""
        return None

    @property
    def guild(self) -> None:
        """Always ``None``."""
        return None

    @property
    def flags(self) -> ApplicationFlags:
        """:class:`ApplicationFlags`: The application's flags."""
        return ApplicationFlags._from_value(self._flags)

    async def edit(self, *, description: Optional[str] = utils.MISSING, interactions_endpoint_url: Optional[str] = utils.MISSING, **kwargs: Any) -> AppInfo:
        """|coro|

        Edits the application info.

        Parameters
        ----------
        description: Optional[:class:`str`]
            The new application description.
        interactions_endpoint_url: Optional[:class:`str`]
            The new Interactions URL, or ``None`` to receive interactions over the gateway.

        Returns
        -------
        :class:`AppInfo`
            The newly updated application info.
        """
        from .errors import NotSupported

        if kwargs:
            raise NotSupported('Changing ' + ', '.join(sorted(kwargs)) + ' of an application')
        fields: Dict[str, Any] = {}
        if description is not utils.MISSING:
            fields['description'] = description
        if interactions_endpoint_url is not utils.MISSING:
            fields['interactionsUrl'] = interactions_endpoint_url
        data = await self._state.http.edit_application(self.id, **fields)
        return AppInfo(state=self._state, data=data)


class PartialAppInfo:
    """Represents a partial application info (kept for compatibility)."""

    __slots__ = ('id', 'name', 'description', '_state')

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any]):
        self._state = state
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self.description: str = data.get('description') or ''
