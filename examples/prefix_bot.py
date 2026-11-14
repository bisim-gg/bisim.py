"""A prefix command bot with ``bisim.ext.commands`` and a background task.

Run it with your bot's token::

    BISIM_TOKEN=... python examples/prefix_bot.py

Then try ``!help``, ``!roll 2d6``, ``!whois``, ``!remind 1 stretch`` or
``!todo add buy bread``. Mentioning the bot works as a prefix too.
"""

import asyncio
import itertools
import os
import random
from typing import Dict, List, Optional

import bisim
from bisim.ext import commands, tasks

intents = bisim.Intents.default()
intents.message_content = True  # accepted for compatibility; Bisim always sends message text

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or('!'),
    description='An example bot for Bisim.',
    intents=intents,
)


@bot.event
async def on_ready() -> None:
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    if not rotate_status.is_running():
        rotate_status.start()


STATUSES = itertools.cycle(['with Python', 'with buttons', '!help'])


@tasks.loop(minutes=5)
async def rotate_status() -> None:
    await bot.change_presence(activity=bisim.Game(name=next(STATUSES)))


@bot.command()
async def roll(ctx: commands.Context, dice: str = '1d6') -> None:
    """Rolls dice written like 2d6: two dice with six sides."""
    try:
        count, sides = (int(part) for part in dice.lower().split('d'))
    except ValueError:
        await ctx.send('Write the dice like 2d6.')
        return
    if not (1 <= count <= 20 and 2 <= sides <= 100):
        await ctx.send('Up to 20 dice with 2 to 100 sides.')
        return
    results = [random.randint(1, sides) for _ in range(count)]
    await ctx.send(f'{" + ".join(map(str, results))} = **{sum(results)}**')


@bot.command(aliases=['user'])
@commands.guild_only()
async def whois(ctx: commands.Context, *, member: Optional[bisim.Member] = None) -> None:
    """Shows a member: you, or whoever you name or mention."""
    member = member or ctx.author
    embed = bisim.Embed(title=member.display_name, colour=member.colour)
    embed.add_field(name='Username', value=f'@{member.name}')
    embed.add_field(name='Top role', value=member.top_role.name)
    embed.set_footer(text=f'ID: {member.id}')
    await ctx.reply(embed=embed)


@bot.command()
async def remind(ctx: commands.Context, minutes: commands.Range[int, 1, 120], *, text: str) -> None:
    """Reminds you of something in a few minutes."""
    await ctx.send(f'I will remind you in {minutes} minutes.')
    await asyncio.sleep(minutes * 60)
    await ctx.reply(f'Reminder: {text}')


@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clean(ctx: commands.Context, count: commands.Range[int, 1, 100] = 10) -> None:
    """Deletes the last messages in this channel."""
    deleted = await ctx.channel.purge(limit=count + 1)
    await ctx.send(f'Deleted {len(deleted) - 1} messages.', delete_after=5)


class Todo(commands.Cog):
    """A small to do list for everyone."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.items: Dict[int, List[str]] = {}

    @commands.group(invoke_without_command=True)
    async def todo(self, ctx: commands.Context) -> None:
        """Shows your to do list."""
        items = self.items.get(ctx.author.id, [])
        if not items:
            await ctx.send('Your list is empty. Add something with `!todo add`.')
            return
        lines = [f'{number}. {item}' for number, item in enumerate(items, start=1)]
        await ctx.send('\n'.join(lines))

    @todo.command()
    async def add(self, ctx: commands.Context, *, item: str) -> None:
        """Adds something to your list."""
        self.items.setdefault(ctx.author.id, []).append(item)
        await ctx.message.add_reaction('✅')

    @todo.command()
    async def done(self, ctx: commands.Context, number: int) -> None:
        """Removes an item by its number."""
        items = self.items.get(ctx.author.id, [])
        if not 1 <= number <= len(items):
            await ctx.send('There is no item with that number.')
            return
        item = items.pop(number - 1)
        await ctx.send(f'Done: {item}')

    @commands.Cog.listener()
    async def on_member_join(self, member: bisim.Member) -> None:
        channel = member.guild.system_channel
        if channel is not None:
            await channel.send(f'Welcome, {member.mention}! Try `!help` to see what I can do.')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send(f'{error}\nUsage: `{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.command.signature}`')
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send('You are not allowed to do that here.')
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send('This command works in servers only.')
    else:
        print(f'Error in {ctx.command}: {error!r}')


async def main() -> None:
    async with bot:
        await bot.add_cog(Todo(bot))
        await bot.start(os.environ['BISIM_TOKEN'])


asyncio.run(main())
