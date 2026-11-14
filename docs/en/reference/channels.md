# Channels

Bisim has text, voice and category channels in servers, and DMs and group DMs outside them. The methods every text channel shares, such as `send` and `history`, come from [`abc.Messageable`][bisim.abc.Messageable] and are listed under each class.

::: bisim.TextChannel
    options:
      inherited_members: true

::: bisim.VoiceChannel
    options:
      inherited_members: true

::: bisim.CategoryChannel
    options:
      inherited_members: true

::: bisim.DMChannel
    options:
      inherited_members: true

::: bisim.GroupChannel
    options:
      inherited_members: true

::: bisim.PartialMessageable
    options:
      inherited_members: true

## Kept for compatibility

Bisim has no threads, stage, forum or media channels. These classes exist so that code which checks for them with `isinstance` still runs; no object of these types is ever created.

::: bisim.Thread
    options:
      heading_level: 3

::: bisim.StageChannel
    options:
      heading_level: 3

::: bisim.ForumChannel
    options:
      heading_level: 3

::: bisim.MediaChannel
    options:
      heading_level: 3
