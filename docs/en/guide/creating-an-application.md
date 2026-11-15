# Creating your application

On Bisim an application **is** its bot: creating an application creates a bot account with the same id.
Commands, the token and the public key all belong to it.

## Create the application

1. Open Bisim's **Developer Portal**: in Bisim, **Settings**, then **Developer Portal**, or go straight to
   [bisim.gg/developers](https://bisim.gg/developers).
2. Select **New Application**, choose a name for your bot and select **Create**.
3. Bisim shows the **bot token** once. Copy it now and keep it somewhere safe: it is never shown again.

The application's pages in the portal:

- **General Information**: the name, the icon, the **Public Key** (used to check requests if you choose an
  [Interactions URL](topics/interactions-url.md)) and the **Interactions Endpoint URL** (leave it empty to
  receive interactions over the gateway, which is what most bots do).
- **Installation**: the install link and the servers the bot is in.
- **Bot**: the bot's username, its token and the privileged intents.
- **Commands**: the commands it has registered.

## Keep the token secret

!!! warning "Anyone with the token controls your bot"

    Never put the token in your code, a screenshot or a repository. If it leaks, select **Reset Token** on
    the application's **Bot** page: the old token stops working at once, and you put the new one wherever
    your bot runs.

Keep the token in an environment variable and read it when the bot starts. The examples in this guide use
`BISIM_TOKEN`:

=== "Linux and macOS"

    ```sh
    export BISIM_TOKEN="paste the token here"
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:BISIM_TOKEN = "paste the token here"
    ```

```python
import os

token = os.environ['BISIM_TOKEN']
```

If you keep the token in a `.env` file instead, add that file to `.gitignore` so it never reaches a
repository.

## Add the bot to a server

There are two ways:

- From the application's **Installation** page, select **Add to Server** and choose a server you manage.
- With an install link. Anyone who manages a server can open it (if the bot is public) and pick the
  permissions to grant. `bisim.utils.oauth_url` makes the link from the application id and the permissions
  your bot needs:

```python
import bisim

permissions = bisim.Permissions(view_channel=True, send_messages=True)
print(bisim.utils.oauth_url(123456789012345678, permissions=permissions))
# https://bisim.gg/oauth2/authorize?client_id=123456789012345678&scope=bot&permissions=3072
```

The `bot` scope is the default, and it also lets the bot register slash commands. When a bot joins, Bisim
gives it a role named after it with the granted permissions. Like any member, the bot can only see and do what
its roles allow.

## Privileged intents

Three [intents](topics/events.md#intents) are privileged: Server Members, Presence and Message Content. A bot
that asks for one must have it switched on: open [bisim.gg/developers](https://bisim.gg/developers), choose the
application, then **Bot**, and turn it on under **Privileged Gateway Intents**. From 100 servers on, Bisim must
approve each one as well. A bot that only uses slash commands and components needs none of them.

## Ids

The application id and the bot's user id are the same number. Once the bot has logged in, it is both
`client.application_id` and `client.user.id`, so you rarely need to pass `application_id` yourself.

Next: [your first bot](your-first-bot.md).
