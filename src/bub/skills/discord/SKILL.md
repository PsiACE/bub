---
name: discord
description: |
  Discord Bot integration for sending messages, managing channels, and responding to events.
  Use when Bub needs to: (1) Send messages to Discord channels, (2) Create Discord bot with discord.py,
  (3) Handle Discord events (on_message, on_member_join, etc.), (4) Work with Discord webhooks,
  or (5) Any Discord-related functionality.
---

# Discord Bot Skill

Send messages and interact with Discord using discord.py.

## Quick Start

```bash
# Dependencies are declared in each script via PEP 723.
# Paths are relative to this skill directory.
# Run scripts directly with uv; it will resolve dependencies from the script header.
uv run ./scripts/discord_send.py --help
uv run ./scripts/discord_bot.py
```

## Sending Messages

### Basic Message

```python
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    channel = bot.get_channel(CHANNEL_ID)
    await channel.send("Hello from Bub!")
```

### Send to Channel by ID

```python
channel = bot.get_channel(123456789)
await channel.send("Message")
```

### Send to Thread

```python
thread = bot.get_channel(THREAD_ID)
await thread.send("Message in thread")
```

### Embed Message

```python
embed = discord.Embed(
    title="Title",
    description="Description",
    color=discord.Color.blue()
)
embed.add_field(name="Field", value="Value")
await channel.send(embed=embed)
```

## Using the Bot

### Configuration

Set environment variable:
```bash
export BUB_DISCORD_TOKEN="your_token_here"
```

### Running the Bot

```python
import asyncio
import os
from discord_bot import run_bot

async def main():
    token = os.environ.get("BUB_DISCORD_TOKEN")
    await run_bot(token)

asyncio.run(main())
```

## Common Patterns

### Respond to Messages

```python
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if "hello" in message.content.lower():
        await message.reply("Hello!")
```

### Command with Arguments

```python
@bot.command(name="echo")
async def echo(ctx, *, text: str):
    await ctx.send(text)
```

### Button Interaction

```python
from discord.ui import Button, View

button = Button(label="Click me", style=discord.ButtonStyle.primary)
async def callback(interaction):
    await interaction.response.send_message("Clicked!")

button.callback = callback
view = View()
view.add_item(button)
await ctx.send("Click:", view=view)
```

## Environment

- `BUB_DISCORD_TOKEN`: Bot token from Discord Developer Portal
