#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "discord.py>=2.3.0",
# ]
# ///

"""
Discord message sender script.
"""

import argparse
import asyncio
import os
import sys

import discord


async def send_message(
    token: str,
    channel_id: int,
    message: str,
    embed: bool = False,
) -> None:
    """Send a message to a Discord channel."""
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        channel = client.get_channel(channel_id)
        if channel is None:
            print(f"Channel {channel_id} not found")
            await client.close()
            sys.exit(1)

        if embed:
            emb = discord.Embed(description=message)
            await channel.send(embed=emb)
        else:
            await channel.send(message)

        print(f"Message sent to channel {channel_id}")
        await client.close()

    await client.start(token)


def main():
    parser = argparse.ArgumentParser(description="Send message to Discord")
    parser.add_argument("--token", "-t", default=os.environ.get("DISCORD_BOT_TOKEN"))
    parser.add_argument("--channel", "-c", type=int, required=True, help="Channel ID")
    parser.add_argument("--message", "-m", required=True, help="Message to send")
    parser.add_argument("--embed", "-e", action="store_true", help="Send as embed")

    args = parser.parse_args()

    if not args.token:
        print("Error: DISCORD_BOT_TOKEN not set")
        sys.exit(1)

    asyncio.run(send_message(args.token, args.channel, args.message, args.embed))


if __name__ == "__main__":
    main()
