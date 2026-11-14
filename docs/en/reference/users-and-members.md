# Users, members and roles

A [`User`][bisim.User] is a Bisim account. A [`Member`][bisim.Member] is a user inside one server, with a nickname, roles and a join date. The bot itself is a [`ClientUser`][bisim.ClientUser].

::: bisim.User
    options:
      inherited_members: true

::: bisim.ClientUser
    options:
      inherited_members: true

::: bisim.Member
    options:
      inherited_members: true

::: bisim.VoiceState

## Roles

::: bisim.Role
    options:
      heading_level: 3

::: bisim.RoleTags
    options:
      heading_level: 3

## Activities

::: bisim.BaseActivity
    options:
      heading_level: 3

::: bisim.Activity
    options:
      heading_level: 3

::: bisim.Game
    options:
      heading_level: 3

::: bisim.Streaming
    options:
      heading_level: 3

::: bisim.CustomActivity
    options:
      heading_level: 3

::: bisim.Spotify
    options:
      heading_level: 3
