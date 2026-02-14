---
name: telegram
description: |
  Telegram Bot skill for sending and editing Telegram messages via Bot API.
  Use when Bub needs to: (1) Send a message to a Telegram user/group/channel,
  (2) Reply to a specific Telegram message with reply_to_message_id,
  (3) Edit an existing Telegram message, or (4) Push proactive Telegram notifications
  when working outside an active Telegram session.
---

# Telegram Skill

Agent-facing execution guide for Telegram outbound communication.

Assumption: `BUB_TELEGRAM_TOKEN` is already available.

## Trigger Conditions

Use this skill when the task requires Telegram Bot API actions:

- Send message to one or more `chat_id`
- Reply to a specific incoming Telegram message
- Edit an existing Telegram message
- Send chat action (`typing`, `record_voice`, etc.) during long processing
- Proactive notification when current session is not Telegram

Typical trigger phrases:

- "send to telegram"
- "reply in telegram"
- "edit telegram message"
- "notify telegram group"

## Non-Trigger Conditions

Do not use this skill when:

- No Telegram destination (`chat_id`) is provided or derivable
- The request is not about Telegram delivery

## Required Inputs

Collect these before execution:

- `chat_id` (required)
- message content (required for send/edit)
- `reply_to_message_id` (required for threaded reply behavior)
- `message_id` (required for edit)

## Execution Policy

1. If handling a direct user message in Telegram and `message_id` is known, prefer reply mode (`--reply-to`).
2. For long-running tasks, optionally send one progress message, then edit that same message for final status.
3. Keep content concise and action-oriented.
4. Use literal newlines in message text when line breaks are needed.

## Active Response Policy

When this skill is in scope, prefer proactive and timely Telegram updates:

- Send an immediate acknowledgment for newly assigned tasks
- Send progress updates for long-running operations using message edits
- Send completion notifications when work finishes
- Send important status or failure notifications without waiting for follow-up prompts
- If execution is blocked or fails, send a problem report immediately with cause, impact, and next action

Recommended pattern:

1. Send a short acknowledgment reply
2. Continue processing
3. If blocked, edit or send an issue update immediately
4. Edit the acknowledgment message with final result when possible

## Voice Message Policy

When the inbound Telegram message is voice:

1. Transcribe the voice input first (use STT skill if available)
2. Prepare response content based on transcription
3. Prefer voice response output (use TTS skill if available)
4. If voice output is unavailable, send a concise text fallback and state limitation

## Reaction Policy

When an inbound Telegram message evokes a strong emotional response:

1. Send the normal reply first (or in the same handling flow)
2. Optionally add a Telegram reaction as an emotional signal
3. Do not use reaction as a replacement for the actual reply

## Command Templates

Paths are relative to this skill directory.

```bash
# Send message
uv run ./scripts/telegram_send.py \
  --chat-id <CHAT_ID> \
  --message "<TEXT>"

# Send reply to a specific message
uv run ./scripts/telegram_send.py \
  --chat-id <CHAT_ID> \
  --message "<TEXT>" \
  --reply-to <MESSAGE_ID>

# Edit existing message
uv run ./scripts/telegram_edit.py \
  --chat-id <CHAT_ID> \
  --message-id <MESSAGE_ID> \
  --text "<TEXT>"

# Show chat action (typing/progress indicator)
uv run ./scripts/telegram_typing.py \
  --chat-id <CHAT_ID> \
  --action typing
```

## Script Interface Reference

### `telegram_send.py`

- `--chat-id`, `-c`: required, supports comma-separated ids
- `--message`, `-m`: required
- `--reply-to`, `-r`: optional
- `--token`, `-t`: optional (normally not needed)

### `telegram_edit.py`

- `--chat-id`, `-c`: required
- `--message-id`, `-m`: required
- `--text`, `-t`: required
- `--token`: optional (normally not needed)

### `telegram_typing.py`

- `--chat-id`, `-c`: required
- `--action`, `-a`: optional, default `typing`
- `--token`, `-t`: optional (normally not needed)

## Failure Handling

- On HTTP errors, inspect API response text and adjust identifiers/permissions.
- If edit fails because message is not editable, fall back to a new send.
- If reply target is invalid, resend without `--reply-to` only when context threading is non-critical.
- For task-level failures (not only API failures), notify the Telegram user with:
  - what failed
  - what was already completed
  - what will happen next (retry/manual action/escalation)

## Output Contract

When this skill is triggered for message drafting tasks:

- Return the final Telegram message body only.
- Do not include process narration or meta commentary in the message body.
- Apply requested tone directly (short, formal, technical, casual).
