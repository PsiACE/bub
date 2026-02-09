"""Internal provider operations that are not part of the public API."""

from __future__ import annotations

from typing import Any

from republic.core.errors import ErrorKind
from republic.core.execution import LLMCore
from republic.core.results import ErrorPayload, StructuredOutput


class InternalOps:
    """Internal-only operations for provider capabilities outside the public API."""

    def __init__(self, core: LLMCore) -> None:
        self._core = core

    def _resolve_provider_model(self, model: str | None, provider: str | None) -> tuple[str, str]:
        if model is None and provider is None:
            return self._core.provider, self._core.model
        model_id = model or self._core.model
        return self._core.resolve_model_provider(model_id, provider)

    def _resolve_provider(self, provider: str | None) -> str:
        return provider or self._core.provider

    def _error(self, exc: Exception, *, provider: str, model: str | None, operation: str) -> ErrorPayload:
        kind = self._core.classify_exception(exc)
        if isinstance(exc, NotImplementedError):
            kind = ErrorKind.INVALID_INPUT
        message = f"{provider}:{model}: {exc}" if model else f"{provider}: {exc}"
        return ErrorPayload(kind, message, details={"operation": operation})

    def responses(
        self,
        input_data: Any,
        *,
        model: str | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name, model_id = self._resolve_provider_model(model, provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.responses(model=model_id, input_data=input_data, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None, self._error(exc, provider=provider_name, model=model_id, operation="responses")
            )
        return StructuredOutput(value, None)

    async def responses_async(
        self,
        input_data: Any,
        *,
        model: str | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name, model_id = self._resolve_provider_model(model, provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.aresponses(model=model_id, input_data=input_data, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None, self._error(exc, provider=provider_name, model=model_id, operation="responses")
            )
        return StructuredOutput(value, None)

    def list_models(self, *, provider: str | None = None, **kwargs: Any) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.list_models(**kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="list_models"),
            )
        return StructuredOutput(value, None)

    async def list_models_async(self, *, provider: str | None = None, **kwargs: Any) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.alist_models(**kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="list_models"),
            )
        return StructuredOutput(value, None)

    def create_batch(
        self,
        input_file_path: str,
        endpoint: str,
        *,
        completion_window: str = "24h",
        metadata: dict[str, str] | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.create_batch(
                input_file_path=input_file_path,
                endpoint=endpoint,
                completion_window=completion_window,
                metadata=metadata,
                **kwargs,
            )
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="create_batch"),
            )
        return StructuredOutput(value, None)

    async def create_batch_async(
        self,
        input_file_path: str,
        endpoint: str,
        *,
        completion_window: str = "24h",
        metadata: dict[str, str] | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.acreate_batch(
                input_file_path=input_file_path,
                endpoint=endpoint,
                completion_window=completion_window,
                metadata=metadata,
                **kwargs,
            )
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="create_batch"),
            )
        return StructuredOutput(value, None)

    def retrieve_batch(
        self,
        batch_id: str,
        *,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.retrieve_batch(batch_id=batch_id, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="retrieve_batch"),
            )
        return StructuredOutput(value, None)

    async def retrieve_batch_async(
        self,
        batch_id: str,
        *,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.aretrieve_batch(batch_id=batch_id, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="retrieve_batch"),
            )
        return StructuredOutput(value, None)

    def cancel_batch(
        self,
        batch_id: str,
        *,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.cancel_batch(batch_id=batch_id, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="cancel_batch"),
            )
        return StructuredOutput(value, None)

    async def cancel_batch_async(
        self,
        batch_id: str,
        *,
        provider: str | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.acancel_batch(batch_id=batch_id, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="cancel_batch"),
            )
        return StructuredOutput(value, None)

    def list_batches(
        self,
        *,
        provider: str | None = None,
        after: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = client.list_batches(after=after, limit=limit, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="list_batches"),
            )
        return StructuredOutput(value, None)

    async def list_batches_async(
        self,
        *,
        provider: str | None = None,
        after: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        provider_name = self._resolve_provider(provider)
        client = self._core.get_client(provider_name)
        try:
            value = await client.alist_batches(after=after, limit=limit, **kwargs)
        except Exception as exc:
            return StructuredOutput(
                None,
                self._error(exc, provider=provider_name, model=None, operation="list_batches"),
            )
        return StructuredOutput(value, None)
