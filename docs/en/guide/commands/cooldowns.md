# Cooldowns

A **cooldown** limits how often a command can be used: so many times per so many seconds, counted per person, per
channel, per server or for everyone. Using a command too soon raises `commands.CommandOnCooldown` instead of running
it.

## Adding a cooldown

```python
@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def daily(ctx: commands.Context) -> None:
    await ctx.send('Here is your daily reward.')
```

`commands.cooldown(rate, per, type)` allows `rate` uses every `per` seconds for each bucket of `type`:

| `BucketType` | One counter for |
| --- | --- |
| `default` | the whole bot (the default) |
| `user` | each person, wherever they use the command |
| `member` | each person in each server |
| `guild` | each server (each person, in a DM) |
| `channel` | each channel |
| `category` | each category (the channel, when it has none) |
| `role` | each top role of the person (the channel, in a DM) |

The type can also be a function that takes the context and returns any hashable key, for buckets of your own.

## Telling people to wait

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'Slow down! Try again in {error.retry_after:.0f} seconds.', delete_after=5)
```

`error.retry_after` is the number of seconds left, `error.cooldown` has the `rate` and `per`, and `error.type` is
the bucket type.

## Cooldowns that depend on who asks

`commands.dynamic_cooldown()` takes a function that receives the context and returns a `commands.Cooldown(rate, per)`
for this use, or `None` for no cooldown at all:

```python
def by_role(ctx: commands.Context):
    if ctx.guild is not None and ctx.author.guild_permissions.manage_messages:
        return None  # moderators have no cooldown
    return commands.Cooldown(1, 60)


@bot.command()
@commands.dynamic_cooldown(by_role, commands.BucketType.user)
async def report(ctx: commands.Context, *, text: str) -> None:
    await ctx.send('Thanks, the moderators were told.')
```

A dynamic cooldown needs a bucket type other than `BucketType.default`.

## Resetting and asking

```python
@daily.error
async def daily_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'Come back in {error.retry_after:.0f} seconds.')


@bot.command()
@commands.is_owner()
async def resetdaily(ctx: commands.Context) -> None:
    daily.reset_cooldown(ctx)
    await ctx.send('Your daily cooldown was reset.')
```

`command.reset_cooldown(ctx)` clears the counter of the bucket `ctx` falls in, `command.is_on_cooldown(ctx)` tells
whether the next use would be refused, and `command.get_cooldown_retry_after(ctx)` gives the seconds left.

A cooldown is counted before the arguments are converted, so a use with wrong arguments counts too. Pass
`cooldown_after_parsing=True` to `@bot.command()` to count only uses whose arguments converted.

## At most so many at once

`commands.max_concurrency()` limits how many uses of a command can run at the same time, which suits a long command
such as a quiz:

```python
@bot.command()
@commands.max_concurrency(1, commands.BucketType.channel, wait=False)
async def quiz(ctx: commands.Context) -> None:
    await ctx.send('First question: ...')
    answer = await bot.wait_for('message', check=lambda m: m.channel == ctx.channel, timeout=30)
    await ctx.send(f'{answer.author.display_name} answered first.')
```

A second use while one is running raises `commands.MaxConcurrencyReached`; with `wait=True` it waits for its turn
instead.

Slash commands have cooldowns of their own, `app_commands.checks.cooldown`: see
[Permissions and checks](../slash-commands/permissions.md). The cooldown classes are in the
[API reference](../../reference/ext-commands.md).
