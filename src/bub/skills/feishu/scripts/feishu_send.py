#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

"""
Feishu/Lark Bot Message Sender

A script to send messages via Feishu/Lark Bot API.
"""

import argparse
import json
import os
import sys
import requests


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """
    Get tenant_access_token from Feishu API.

    Args:
        app_id: Feishu App ID
        app_secret: Feishu App Secret

    Returns:
        tenant_access_token
    """
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"

    payload = {
        "app_id": app_id,
        "app_secret": app_secret,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    result = response.json()
    if result.get("code") != 0:
        raise Exception(f"Failed to get token: {result.get('msg')}")

    return result["tenant_access_token"]


def send_message(
    app_id: str,
    app_secret: str,
    chat_id: str,
    text: str,
    reply_to_message_id: str | None = None,
) -> dict:
    """
    Send a message via Feishu/Lark Bot API.

    Args:
        app_id: Feishu App ID
        app_secret: Feishu App Secret
        chat_id: Target chat ID
        text: Message text
        reply_to_message_id: Optional message ID to reply to

    Returns:
        API response as dict
    """
    token = get_tenant_access_token(app_id, app_secret)

    url = "https://open.larksuite.com/open-apis/im/v1/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    params = {
        "receive_id_type": "chat_id",
    }

    # Properly format content as JSON
    content = json.dumps({"text": text})

    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": content,
    }

    response = requests.post(url, headers=headers, params=params, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Send messages via Feishu/Lark Bot API")
    parser.add_argument("--chat-id", "-c", required=True, help="Target chat ID")
    parser.add_argument("--message", "-m", required=True, help="Message text to send")
    parser.add_argument("--app-id", help="Feishu App ID (defaults to BUB_FEISHU_APP_ID env var)")
    parser.add_argument("--app-secret", help="Feishu App Secret (defaults to BUB_FEISHU_APP_SECRET env var)")
    parser.add_argument("--reply-to", "-r", help="Message ID to reply to")

    args = parser.parse_args()

    # Get credentials
    app_id = args.app_id or os.environ.get("BUB_FEISHU_APP_ID")
    app_secret = args.app_secret or os.environ.get("BUB_FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ Error: App ID and App Secret required. Set BUB_FEISHU_APP_ID and BUB_FEISHU_APP_SECRET env vars")
        sys.exit(1)

    # Send message
    try:
        result = send_message(app_id, app_secret, args.chat_id, args.message, args.reply_to)
        if result.get("code") == 0:
            print(f"✅ Message sent successfully to {args.chat_id}")
        else:
            print(f"❌ Failed to send message: {result.get('msg')}")
            sys.exit(1)
    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
