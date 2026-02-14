#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "discord.py>=2.3.0",
# ]
# ///

"""
Discord Bot basic scaffold.
Written to keep logic readable and testable.
"""

import asyncio
import os
from dataclasses import dataclass

import discord
from discord.ext import commands


@dataclass
class Config:
    """Bot configuration."""

    token: str
    command_prefix: str = "!"
    intents_messages: bool = True
    intents_message_content: bool = True


def create_bot(config: Config) -> commands.Bot:
    """
    Create a bot instance.

    Args:
        config: Bot configuration.

    Returns:
        A configured bot instance.
    """
    intents = discord.Intents.default()
    intents.messages = config.intents_messages
    intents.message_content = config.intents_message_content

    bot = commands.Bot(
        command_prefix=config.command_prefix,
        intents=intents,
        help_command=None,
    )

    return bot


def register_events(bot: commands.Bot) -> None:
    """Register event handlers."""

    @bot.event
    async def on_ready() -> None:
        """Handle bot startup completion."""
        print(f"🤖 Logged in as {bot.user}")
        print(f"   ID: {bot.user.id}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        """Handle incoming messages."""
        # Ignore messages from bots.
        if message.author.bot:
            return

        # Reply within an existing thread when available.
        if message.thread is not None:
            await message.thread.send(f"Received: {message.content}")

        # Continue command processing.
        await bot.process_commands(message)

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"Command not found: {ctx.invoked_with}")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: {error.param.name}")
        else:
            await ctx.send(f"Error: {error}")
            raise error


def register_commands(bot: commands.Bot) -> None:
    """Register bot commands."""

    @bot.command(name="ping")
    async def ping(ctx: commands.Context) -> None:
        """Ping command."""
        await ctx.send("pong 🏓")

    @bot.command(name="hello")
    async def hello(ctx: commands.Context) -> None:
        """Hello command."""
        await ctx.send(f"Hello, {ctx.author.mention}! 👋")

    @bot.command(name="echo")
    async def echo(ctx: commands.Context, *, text: str) -> None:
        """Echo command."""
        await ctx.send(text)

    @bot.command(name="info")
    async def info(ctx: commands.Context) -> None:
        """Bot info command."""
        embed = discord.Embed(title="🤖 Bot Info", description="Bub's Discord Bot", color=discord.Color.blue())
        embed.add_field(
            name="Commands", value="!ping - ping\n!hello - hello\n!echo <text> - echo\n!info - this", inline=False
        )
        await ctx.send(embed=embed)


async def run_bot(token: str) -> None:
    """Run the bot."""
    config = Config(token=token)
    bot = create_bot(config)

    register_events(bot)
    register_commands(bot)

    await bot.start(token)


def main() -> None:
    """Entry point."""
    token = os.environ.get("BUB_DISCORD_TOKEN")
    if token is None:
        print("Error: BUB_DISCORD_TOKEN not set")
        return

    asyncio.run(run_bot(token))


if __name__ == "__main__":
    main()
