"""Application-level exception types for Bub."""

from __future__ import annotations


class BubError(Exception):
    """Base exception for Bub."""


class ConfigurationError(BubError):
    """Base exception for configuration and startup validation errors."""


class WorkspaceNotFoundError(ConfigurationError):
    """Raised when the configured workspace path does not exist."""


class ModelNotConfiguredError(ConfigurationError):
    """Raised when model configuration is missing."""


class InvalidModelFormatError(ConfigurationError):
    """Raised when model format is not provider:model."""


class ApiKeyNotConfiguredError(ConfigurationError):
    """Raised when an API key is required but missing."""


class RequiredToolMissingError(ConfigurationError):
    """Raised when a required runtime tool is not registered."""
