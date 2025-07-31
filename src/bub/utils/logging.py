"""Logging utilities for Bub."""

import logfire


def configure_logfire(level: str = "INFO", log_format: str = "text") -> None:
    """Configure Logfire for structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_format: Log format (text, json)
    """
    logfire.configure(
        console=logfire.ConsoleOptions(
            colors="auto",
            span_style="indented",
        ),
        send_to_logfire=False,  # Disable for local demo
    )
