"""Embedding helpers for Republic."""

from __future__ import annotations

from typing import Any

from republic.core.execution import LLMCore
from republic.core.results import ErrorPayload, StructuredOutput


class EmbeddingClient:
    """Lightweight embedding helper."""

    def __init__(self, core: LLMCore) -> None:
        self._core = core

    def _resolve_provider_model(self, model: str | None, provider: str | None) -> tuple[str, str]:
        if model is None and provider is None:
            return self._core.provider, self._core.model
        model_id = model or self._core.model
        return self._core.resolve_model_provider(model_id, provider)

    def embed(
        self,
        inputs: str | list[str],
        *,
        model: str | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name, model_id = self._resolve_provider_model(model, provider)
        client = self._core.get_client(provider_name)
        try:
            response = client._embedding(model=model_id, inputs=inputs, **kwargs)
        except Exception as exc:
            kind = self._core.classify_exception(exc)
            error = self._core.wrap_error(exc, kind, provider_name, model_id)
            return StructuredOutput(None, ErrorPayload(error.kind, error.message))
        return StructuredOutput(response, None)

    async def embed_async(
        self,
        inputs: str | list[str],
        *,
        model: str | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name, model_id = self._resolve_provider_model(model, provider)
        client = self._core.get_client(provider_name)
        try:
            response = await client.aembedding(model=model_id, inputs=inputs, **kwargs)
        except Exception as exc:
            kind = self._core.classify_exception(exc)
            error = self._core.wrap_error(exc, kind, provider_name, model_id)
            return StructuredOutput(None, ErrorPayload(error.kind, error.message))
        return StructuredOutput(response, None)
