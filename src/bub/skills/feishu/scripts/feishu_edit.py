#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lark-oapi>=1.5.0",
# ]
# ///

"""
Feishu/Lark Bot Message Editor

A script to edit existing messages via Feishu/Lark Bot API.
Uses lark-oapi SDK for proper message editing.
"""

import argparse
import json
import os
import sys

import lark_oapi as lark
from lark_oapi.api.im.v1 import UpdateMessageRequest, UpdateMessageRequestBody


def edit_message(
    app_id: str,
    app_secret: str,
    message_id: str,
    text: str,
) -> bool:
    """
    Edit an existing message via Feishu/Lark Bot API.

    Args:
        app_id: Feishu App ID
        app_secret: Feishu App Secret
        message_id: ID of the message to edit
        text: New message text

    Returns:
        True if successful, False otherwise
    """
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.ERROR) \
        .build()

    request = UpdateMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(
            UpdateMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        ) \
        .build()

    response = client.im.v1.message.update(request)
    return response.success()


def main():
    parser = argparse.ArgumentParser(description="Edit messages via Feishu/Lark Bot API")
    parser.add_argument("--message-id", "-m", required=True, help="Message ID to edit")
    parser.add_argument("--text", "-t", required=True, help="New message text")
    parser.add_argument("--app-id", help="Feishu App ID (defaults to BUB_FEISHU_APP_ID env var)")
    parser.add_argument("--app-secret", help="Feishu App Secret (defaults to BUB_FEISHU_APP_SECRET env var)")

    args = parser.parse_args()

    # Get credentials
    app_id = args.app_id or os.environ.get("BUB_FEISHU_APP_ID")
    app_secret = args.app_secret or os.environ.get("BUB_FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ Error: App ID and App Secret required. Set BUB_FEISHU_APP_ID and BUB_FEISHU_APP_SECRET env vars")
        sys.exit(1)

    # Edit message
    try:
        success = edit_message(app_id, app_secret, args.message_id, args.text)
        if success:
            print(f"✅ Message edited successfully: {args.message_id}")
        else:
            print(f"❌ Failed to edit message")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
