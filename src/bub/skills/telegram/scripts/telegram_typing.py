#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

"""
Telegram Bot Typing Action Sender

Send typing action to a Telegram chat to show "typing..." indicator.
Uses Telegram Bot API sendChatAction method.

Usage:
    python telegram_typing.py --chat-id <CHAT_ID>
    python telegram_typing.py -c 123456 -a recording_voice
"""

import argparse
import os
import sys

import requests

# Valid Telegram chat actions
CHAT_ACTIONS = [
    "typing",  # Text messages
    "upload_photo",  # Photo
    "record_video",  # Video recording
    "upload_video",  # Video uploading
    "record_voice",  # Voice recording
    "upload_voice",  # Voice uploading
    "upload_document",  # Document uploading
    "find_location",  # Location
    "record_video_note",  # Video note recording
    "upload_video_note",  # Video note uploading
]


def send_chat_action(bot_token: str, chat_id: str, action: str = "typing") -> dict:
    """
    Send a chat action to a Telegram chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        action: The type of action to send (default: "typing")

    Returns:
        API response as dict

    Raises:
        requests.HTTPError: If the API call fails
    """
    if action not in CHAT_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Valid actions: {', '.join(CHAT_ACTIONS)}")

    url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"

    payload = {
        "chat_id": chat_id,
        "action": action,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Send typing action to a Telegram chat")
    parser.add_argument("--chat-id", "-c", required=True, help="Target chat ID")
    parser.add_argument(
        "--action", "-a", default="typing", choices=CHAT_ACTIONS, help="Type of action to send (default: typing)"
    )
    parser.add_argument("--token", "-t", help="Bot token (defaults to BUB_TELEGRAM_TOKEN env var)")

    args = parser.parse_args()

    # Get bot token
    bot_token = args.token or os.environ.get("BUB_TELEGRAM_TOKEN")
    if not bot_token:
        print("❌ Error: Bot token required. Set BUB_TELEGRAM_TOKEN env var or use --token")
        sys.exit(1)

    # Send typing action
    try:
        result = send_chat_action(bot_token, args.chat_id, args.action)
        print(f"✅ Sent '{args.action}' action to {args.chat_id}")
    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
