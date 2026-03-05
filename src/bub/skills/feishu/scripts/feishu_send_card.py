#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lark-oapi>=1.5.0",
# ]
# ///

"""
Feishu/Lark Bot Card Message Sender

A script to send card messages (with markdown support) via Feishu/Lark Bot API.
"""

import argparse
import json
import os
import sys

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody


def send_card_message(
    app_id: str,
    app_secret: str,
    chat_id: str,
    title: str | None,
    content: str,
) -> bool:
    """
    Send a card message via Feishu/Lark Bot API.

    Args:
        app_id: Feishu App ID
        app_secret: Feishu App Secret
        chat_id: Target chat ID
        title: Card title (optional)
        content: Card content (supports markdown)

    Returns:
        True if successful, False otherwise
    """
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.ERROR) \
        .build()

    # Create card content
    card_content = {
        "config": {
            "wide_screen_mode": True
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            }
        ]
    }

    if title:
        card_content["header"] = {
            "title": {
                "tag": "plain_text",
                "content": title
            }
        }

    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card_content))
            .build()
        ) \
        .build()

    response = client.im.v1.message.create(request)
    return response.success()


def main():
    parser = argparse.ArgumentParser(description="Send card messages via Feishu/Lark Bot API")
    parser.add_argument("--chat-id", "-c", required=True, help="Target chat ID")
    parser.add_argument("--content", "-m", required=True, help="Card content (supports markdown)")
    parser.add_argument("--title", "-t", help="Card title (optional)")
    parser.add_argument("--app-id", help="Feishu App ID (defaults to BUB_FEISHU_APP_ID env var)")
    parser.add_argument("--app-secret", help="Feishu App Secret (defaults to BUB_FEISHU_APP_SECRET env var)")

    args = parser.parse_args()

    # Get credentials
    app_id = args.app_id or os.environ.get("BUB_FEISHU_APP_ID")
    app_secret = args.app_secret or os.environ.get("BUB_FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ Error: App ID and App Secret required. Set BUB_FEISHU_APP_ID and BUB_FEISHU_APP_SECRET env vars")
        sys.exit(1)

    # Send message
    try:
        success = send_card_message(app_id, app_secret, args.chat_id, args.title, args.content)
        if success:
            print(f"✅ Card message sent successfully to {args.chat_id}")
        else:
            print(f"❌ Failed to send card message")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
