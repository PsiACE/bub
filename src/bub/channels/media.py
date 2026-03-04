"""Shared media helpers for channel adapters."""

from __future__ import annotations

import base64
import mimetypes

MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024
DEFAULT_IMAGE_MIME = "image/png"


def to_data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def guess_image_mime(content_type: str | None, filename: str | None) -> str | None:
    normalized = (content_type or "").split(";", 1)[0].strip().casefold()
    if normalized.startswith("image/"):
        return normalized

    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed and guessed.casefold().startswith("image/"):
            return guessed.casefold()

    return None
