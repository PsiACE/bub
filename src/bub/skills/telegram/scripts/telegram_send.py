#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "telegramify-markdown>=0.5.0",
# ]
# ///

"""
Telegram Bot Message Sender

A simple script to send messages via Telegram Bot API.
Uses telegramify_markdown to convert markdown to Telegram MarkdownV2 format.

Usage:
    python telegram_send.py --chat-id <CHAT_ID> --message "Hello!"
    python telegram_send.py -c 123456 -m "*Bold* _italic_"
"""
import argparse
import os
import sys

import requests

try:
    from telegramify_markdown import markdownify
except ImportError:
    print("❌ Error: telegramify_markdown not installed. Run: pip install telegramify-markdown")
    sys.exit(1)


def unescape_newlines(text: str) -> str:
    """
    Convert escaped newline sequences to real newlines.
    Handles \\n -> \n, \\r\\n -> \r\n, etc.
    """
    # First unescape \\n to real newline
    result = text.replace("\\n", "\n")
    result = result.replace("\\r\\n", "\r\n")
    result = result.replace("\\r", "\r")
    return result


def edit_message(bot_token: str, chat_id: str, message_id: int, text: str) -> dict:
    """
    Edit an existing message via Telegram Bot API.

    Uses telegramify_markdown to convert text to MarkdownV2 format.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        message_id: ID of the message to edit
        text: New message text (will be converted to MarkdownV2)

    Returns:
        API response as dict
    """
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"

    # Convert markdown to Telegram MarkdownV2 format
    converted_text = markdownify(text)

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": converted_text,
        "parse_mode": "MarkdownV2",
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()


def send_message(bot_token: str, chat_id: str, text: str, reply_to_message_id: int | None = None) -> dict:
    """
    Send a message via Telegram Bot API.

    Uses telegramify_markdown to convert text to MarkdownV2 format.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        text: Message text (will be converted to MarkdownV2)
        reply_to_message_id: Optional message ID to reply to

    Returns:
        API response as dict
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Unescape \\n sequences to real newlines (bash/argparse converts real newlines to \\n)
    text = unescape_newlines(text)

    # Convert markdown to Telegram MarkdownV2 format
    converted_text = markdownify(text).rstrip("\n")

    payload = {
        "chat_id": chat_id,
        "text": converted_text,
        "parse_mode": "MarkdownV2",
    }

    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()


def send_to_multiple(bot_token: str, chat_ids: list[str], text: str) -> list[dict]:
    """
    Send message to multiple chat IDs.

    Args:
        bot_token: Telegram bot token
        chat_ids: List of target chat IDs
        text: Message text (will be converted to MarkdownV2)

    Returns:
        List of API responses
    """
    results = []
    for chat_id in chat_ids:
        try:
            result = send_message(bot_token, chat_id.strip(), text)
            results.append({"chat_id": chat_id, "success": True, "response": result})
            print(f"✅ Sent to {chat_id}")
        except Exception as e:
            results.append({"chat_id": chat_id, "success": False, "error": str(e)})
            print(f"❌ Failed to send to {chat_id}: {e}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Send messages via Telegram Bot API (auto-converts to MarkdownV2)")
    parser.add_argument(
        "--chat-id", "-c", required=True, help="Target chat ID (comma-separated for multiple recipients)"
    )
    parser.add_argument(
        "--message",
        "-m",
        required=True,
        help="Message text to send (markdown supported, will be converted to MarkdownV2)",
    )
    parser.add_argument("--token", "-t", help="Bot token (defaults to BUB_TELEGRAM_TOKEN env var)")
    parser.add_argument("--reply-to", "-r", type=int, help="Message ID to reply to (creates threaded conversation)")

    args = parser.parse_args()

    # Get bot token
    bot_token = args.token or os.environ.get("BUB_TELEGRAM_TOKEN")
    if not bot_token:
        print("❌ Error: Bot token required. Set BUB_TELEGRAM_TOKEN env var or use --token")
        sys.exit(1)

    # Parse chat IDs
    chat_ids = [cid.strip() for cid in args.chat_id.split(",")]

    # Send messages
    if len(chat_ids) == 1:
        try:
            result = send_message(bot_token, chat_ids[0], args.message, args.reply_to)
            print(f"✅ Message sent successfully to {chat_ids[0]} (MarkdownV2)")
        except requests.HTTPError as e:
            print(f"❌ HTTP Error: {e}")
            print(f"   Response: {e.response.text}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        print(f"📤 Sending to {len(chat_ids)} recipients...")
        results = send_to_multiple(bot_token, chat_ids, args.message)

        success_count = sum(1 for r in results if r["success"])
        print(f"\n📊 Summary: {success_count}/{len(chat_ids)} messages sent")


if __name__ == "__main__":
    main()
