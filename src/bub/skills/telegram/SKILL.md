---
name: telegram
description: Telegram Bot API integration for sending messages, notifications, and managing bot interactions. Use when Bub needs to (1) Send messages via Telegram bot, (2) Push notifications to Telegram channels or groups, (3) Interact with Telegram Bot API endpoints, (4) Test and validate Telegram bot functionality, or (5) Send any response to Telegram users.
---

# Telegram Bot Skill

Send messages via Telegram Bot API using the bundled Python script.

## Prerequisites

1. Create a bot via [@BotFather](https://t.me/botfather) and obtain the bot token
2. Get the chat_id (user/group/channel) to send messages to
3. Set environment variable: `BUB_TELEGRAM_TOKEN`

## Quick Start

_In the following examples, paths are relative to this skill directory._

```bash
# Send a text message (auto-converted to MarkdownV2)
uv run ./scripts/telegram_send.py --chat-id <CHAT_ID> --message "Hello from Bub!" -t $BUB_TELEGRAM_TOKEN

# Send with markdown formatting
uv run ./scripts/telegram_send.py -c <CHAT_ID> -m "*Bold* _italic_ `code`" -t $BUB_TELEGRAM_TOKEN

# Send to multiple recipients
uv run ./scripts/telegram_send.py --chat-id "123456,789012" --message "Broadcast message" -t $BUB_TELEGRAM_TOKEN

# Reply to a specific message (creates threaded conversation)
uv run ./scripts/telegram_send.py -c <CHAT_ID> -m "Acknowledged. Working on it..." --reply-to <MESSAGE_ID> -t $BUB_TELEGRAM_TOKEN

# Edit an existing message
uv run ./scripts/telegram_edit.py -c <CHAT_ID> --message-id <MSG_ID> -m "Updated content" -t $BUB_TELEGRAM_TOKEN
```

## Communication Etiquette

**CRITICAL: Always follow these etiquette rules when responding on Telegram**

### 1. Reply to Messages
When someone assigns a task or asks a question:
- **ALWAYS** use `reply_to_message_id` to reply directly to their message
- This creates a threaded conversation and shows you're responding to them specifically
- Do NOT just send a new message without context

### 2. Voice Message Response
When receiving a voice message:
- **ALWAYS** respond with voice (TTS) when the user sends you a voice message
- First, transcribe the voice using STT skill(if present)
- Then convert your response to voice using TTS skill
- Send the voice message back to the user

### 3. Progress Updates
For long-running tasks within the same conversation round:
- First, send a quick acknowledgment message (e.g., "Acknowledged, processing now...")
- Then, **EDIT** that message to update with progress or results
- This keeps the chat clean and avoids flooding with multiple messages

### 3. Example Pattern

```
User: "Please analyze this log file."
Bot: [replies to user's message] "Acknowledged, analyzing now..." (message_id: 123)
... processing ...
Bot: [edits message 123] "Analysis complete. Found 3 issues:" + newline + "1. ..." + newline + "2. ..." + newline + "3. ..."
```

**Note: Newlines in messages must be literal line breaks (press Enter), not `\n`.**

---

## Usage Guidelines

**IMPORTANT: Active Response Policy**

Bub should be more proactive in sending responses:
- Send progress updates for long-running tasks
- Send immediate confirmations when receiving commands
- Send status notifications for important events
- Send completion messages when tasks finish
- Be conversational and responsive in interactions

This ensures users receive timely feedback even when the daemon is running in background mode.

---

Use this skill to send any message to Telegram:
- Progress updates during task execution
- Task completion notifications
- Responses to user questions
- Alerts and status messages
- Any communication via Telegram bot
- Proactive status updates when not in direct telegram session

## Common Usage Patterns

### Get Chat ID

To find your chat_id, send a message to your bot, then:

```bash
curl "https://api.telegram.org/bot${BUB_TELEGRAM_TOKEN}/getUpdates"
```

### Send Progress Updates

```bash
# Progress notification
uv run ./scripts/telegram_send.py -c <CHAT_ID> -m "⏳ Processing step 2/5..." -t $BUB_TELEGRAM_TOKEN

# With markdown formatting
uv run ./scripts/telegram_send.py -c <CHAT_ID> -m "✅ *Done*: Build step completed" -t $BUB_TELEGRAM_TOKEN
```

### Task completion notification
uv run ./scripts/telegram_send.py -c <CHAT_ID> -m "Task completed! Here are the results..." -t $BUB_TELEGRAM_TOKEN

## Script Reference

See `./scripts/telegram_send.py` for the full implementation.

### Arguments (telegram_send.py)

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--chat-id` | `-c` | Yes | Target chat ID (comma-separated for multiple) |
| `--message` | `-m` | Yes | Message text to send (markdown supported) |
| `--token` | `-t` | No | Bot token (defaults to `BUB_TELEGRAM_TOKEN` env var) |
| `--reply-to` | `-r` | No | Message ID to reply to (creates threaded conversation) |

### Arguments (telegram_edit.py)

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--chat-id` | `-c` | Yes | Target chat ID |
| `--message-id` | `-m` | Yes | ID of the message to edit |
| `--text` | `-t` | Yes | New message text (markdown supported) |
| `--token` | | No | Bot token (defaults to `BUB_TELEGRAM_TOKEN` env var) |

### Message Formatting

All messages are automatically converted to Telegram MarkdownV2 format using `telegramify_markdown`. You can use standard markdown syntax:

- `*bold*` or `_italic_`
- `` `code` ``
- `[link](url)`
- Lists, headers, etc.

**Note: Newlines should be literal line breaks (press Enter), not `\n`.**

- Correct:
  ```
  First line
  Second line
  ```
- Incorrect (will not render as a line break):
  ```
  First line\nSecond line
  ```

## Environment Setup

Add to `.env` or export directly:

```bash
export BUB_TELEGRAM_TOKEN="your_bot_token_here"
```
