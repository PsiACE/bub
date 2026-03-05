---
name: feishu
description: |
  Feishu/Lark Bot skill for sending and editing messages via Feishu/Lark Bot API.
  Use when Bub needs to: (1) Send a message to a Feishu user/group/channel,
  (2) Reply to a specific Feishu message, (3) Edit an existing Feishu message, or
  (4) Push proactive Feishu notifications when working outside an active Feishu session.
metadata:
  channel: feishu
---

# Feishu Skill

Agent-facing execution guide for Feishu/Lark outbound communication.

Assumption: `BUB_FEISHU_APP_ID` and `BUB_FEISHU_APP_SECRET` are already available.

## Required Inputs

Collect these before execution:

- `chat_id` (required for send)
- message content (required for send/edit)
- `message_id` (required for edit and reply)
- For card messages: `title` (optional), `content` with markdown support

## Execution Policy

1. If handling a direct user message in Feishu and `message_id` is known, prefer reply mode (reply to the message).
2. For long-running tasks, optionally send one progress message, then edit that same message for final status.
3. Use literal newlines in message text when line breaks are needed.
4. Keep messages concise and clear.
5. **Message type selection**:
   - Use **text messages** for simple, plain text content
   - Use **card messages** for content that requires markdown formatting, structured layout, or visual emphasis

## Active Response Policy

**IMPORTANT**: When this skill is in scope AND you are in an active Feishu session (receiving messages via the Feishu channel), the channel adapter will automatically handle replies. Use this skill only for:

- Proactive notifications (not in response to a user message)
- Additional messages beyond the automatic reply
- Sending messages outside of an active session

When sending proactive updates:

- Send an immediate acknowledgment for newly assigned tasks
- Send progress updates for long-running operations using message edits
- Send completion notifications when work finishes
- Send important status or failure notifications without waiting for follow-up prompts
- If execution is blocked or fails, send a problem report immediately with cause, impact, and next action

Recommended pattern for long-running tasks:

1. Send a short acknowledgment message
2. Continue processing
3. If blocked, edit the acknowledgment message with an issue update
4. Edit the acknowledgment message with final result when complete

## Command Templates

Paths are relative to this skill directory.

```bash
# Send text message
uv run ./scripts/feishu_send.py \
  --chat-id <CHAT_ID> \
  --message "<TEXT>"

# Send reply to a specific message
uv run ./scripts/feishu_send.py \
  --chat-id <CHAT_ID> \
  --message "<TEXT>" \
  --reply-to <MESSAGE_ID>

# Send card message (with markdown support)
uv run ./scripts/feishu_send_card.py \
  --chat-id <CHAT_ID> \
  --title "<TITLE>" \
  --content "<MARKDOWN_CONTENT>"

# Edit existing message
uv run ./scripts/feishu_edit.py \
  --message-id <MESSAGE_ID> \
  --text "<TEXT>"

# Add reaction to a message
uv run ./scripts/feishu_react.py \
  --message-id <MESSAGE_ID> \
  --emoji "THUMBSUP"
```

## Script Interface Reference

### `feishu_send.py`

- `--chat-id`, `-c`: required, the chat ID to send message to
- `--message`, `-m`: required, message text to send
- `--app-id`: optional (defaults to BUB_FEISHU_APP_ID env var)
- `--app-secret`: optional (defaults to BUB_FEISHU_APP_SECRET env var)
- `--reply-to`, `-r`: optional, message ID to reply to

### `feishu_send_card.py`

- `--chat-id`, `-c`: required, the chat ID to send message to
- `--content`, `-m`: required, card content (supports markdown)
- `--title`, `-t`: optional, card title
- `--app-id`: optional (defaults to BUB_FEISHU_APP_ID env var)
- `--app-secret`: optional (defaults to BUB_FEISHU_APP_SECRET env var)

### `feishu_edit.py`

- `--message-id`, `-m`: required, the message ID to edit
- `--text`, `-t`: required, new message text
- `--app-id`: optional (defaults to BUB_FEISHU_APP_ID env var)
- `--app-secret`: optional (defaults to BUB_FEISHU_APP_SECRET env var)

### `feishu_react.py`

- `--message-id`, `-m`: required, the message ID to react to
- `--emoji`, `-e`: required, emoji to react with (e.g., "THUMBSUP", "HEART", "SMILE")
- `--app-id`: optional (defaults to BUB_FEISHU_APP_ID env var)
- `--app-secret`: optional (defaults to BUB_FEISHU_APP_SECRET env var)

**Common emoji_type values**: THUMBSUP, THUMBSDOWN, HEART, SMILE, LAUGH, PARTY, FIRE, EYES, THINKING, CLAP, PRAY, MUSCLE, HUNDRED

## Reaction Policy

When an inbound Feishu message warrants acknowledgment but does not merit a full reply, consider using a Feishu reaction as the response. However, when any explanation or details are needed, use a normal reply instead.

**Note**: Feishu uses emoji_type strings (e.g., "THUMBSUP", "HEART", "SMILE") instead of emoji characters. Common emoji are automatically mapped to the correct format.

```bash
# Add reaction to a message
uv run ./scripts/feishu_react.py \
  --message-id <MESSAGE_ID> \
  --emoji "THUMBSUP"
```

## Failure Handling

- On HTTP errors, inspect API response text and adjust identifiers/permissions.
- If credentials are invalid, verify BUB_FEISHU_APP_ID and BUB_FEISHU_APP_SECRET environment variables.
- If edit fails because message is not editable (e.g., too old or not sent by bot), fall back to sending a new message.
- For task-level failures, notify the Feishu user with:
  - what failed
  - what was already completed
  - what will happen next (retry/manual action/escalation)
