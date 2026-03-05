#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lark-oapi>=1.5.0",
# ]
# ///

"""
Feishu/Lark Bot Message Reaction

A script to add reactions to messages via Feishu/Lark Bot API.
"""

import argparse
import json
import os
import sys

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    Emoji,
)


def add_reaction(
    app_id: str,
    app_secret: str,
    message_id: str,
    emoji: str,
) -> bool:
    """
    Add a reaction to a message via Feishu/Lark Bot API.
    
    Args:
        app_id: Feishu App ID
        app_secret: Feishu App Secret
        message_id: ID of the message to react to
        emoji: Emoji to react with (e.g., "👍", "❤️", "😄")
        
    Returns:
        True if successful, False otherwise
    """
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.ERROR) \
        .build()
    
    emoji_obj = Emoji.builder() \
        .emoji_type(emoji) \
        .build()
    
    request = CreateMessageReactionRequest.builder() \
        .message_id(message_id) \
        .request_body(
            CreateMessageReactionRequestBody.builder()
            .reaction_type(emoji_obj)
            .build()
        ) \
        .build()
    
    response = client.im.v1.message_reaction.create(request)
    return response.success()


def main():
    parser = argparse.ArgumentParser(description="Add reactions to messages via Feishu/Lark Bot API")
    parser.add_argument("--message-id", "-m", required=True, help="Message ID to react to")
    parser.add_argument("--emoji", "-e", required=True, help="Emoji to react with (e.g., 👍, ❤️, 😄)")
    parser.add_argument("--app-id", help="Feishu App ID (defaults to BUB_FEISHU_APP_ID env var)")
    parser.add_argument("--app-secret", help="Feishu App Secret (defaults to BUB_FEISHU_APP_SECRET env var)")

    args = parser.parse_args()

    # Get credentials
    app_id = args.app_id or os.environ.get("BUB_FEISHU_APP_ID")
    app_secret = args.app_secret or os.environ.get("BUB_FEISHU_APP_SECRET")
    
    if not app_id or not app_secret:
        print("❌ Error: App ID and App Secret required. Set BUB_FEISHU_APP_ID and BUB_FEISHU_APP_SECRET env vars")
        sys.exit(1)

    # Add reaction
    try:
        success = add_reaction(app_id, app_secret, args.message_id, args.emoji)
        if success:
            print(f"✅ Reaction added successfully: {args.emoji}")
        else:
            print(f"❌ Failed to add reaction")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
