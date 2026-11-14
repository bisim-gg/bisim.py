# Creating your application

On Bisim an application **is** its bot: creating an application creates a bot account with the same id.
Commands, the token and the public key all belong to it.

## Create the application

1. Open Bisim and go to **Settings**, then **Applications**.
2. Choose a name for your bot and select **Create**.
3. Bisim shows the **bot token** once. Copy it now and keep it somewhere safe: it is never shown again.

The application page also shows:

- **Public key**: used to check requests if you choose an [Interactions URL](topics/interactions-url.md).
- **Interactions URL**: leave it empty to receive interactions over the gateway, which is what most bots do.
- **Servers** and **Commands**: where the bot is, and which commands it has registered.

## Keep the token secret

!!! warning "Anyone with the token controls your bot"

    Never put the token in your code, a screenshot or a repository. If it leaks, select **Reset token** on
    the application page: the old token stops working at once, and you put the new one wherever your bot
    runs.

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

- From the application page, under **Servers**, choose a server you manage and select **Add**.
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

## Ids

The application id and the bot's user id are the same number. Once the bot has logged in, it is both
`client.application_id` and `client.user.id`, so you rarely need to pass `application_id` yourself.

Next: [your first bot](your-first-bot.md).
