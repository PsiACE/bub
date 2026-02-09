"""Tool helpers for Republic."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, NoReturn, ParamSpec, TypeVar, cast, overload

from pydantic import BaseModel, TypeAdapter, validate_call

ModelT = TypeVar("ModelT", bound=BaseModel)
P = ParamSpec("P")


def _to_snake_case(name: str) -> str:
    return "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")


def _callable_name(func: Callable[..., Any]) -> str:
    name = getattr(func, "__name__", None)
    if isinstance(name, str) and name:
        return name
    return func.__class__.__name__


def _schema_from_annotation(annotation: Any) -> dict[str, Any]:
    """Convert Python type annotations to JSON schema via Pydantic."""
    if annotation is inspect._empty:
        annotation = Any
    try:
        return TypeAdapter(annotation).json_schema()
    except Exception as exc:
        _raise_value_error(f"Failed to build JSON schema for type: {annotation!r}", cause=exc)


def _raise_value_error(message: str, *, cause: Exception | None = None) -> NoReturn:
    if cause is None:
        raise ValueError(message)
    raise ValueError(message) from cause


def _raise_type_error(message: str, *, cause: Exception | None = None) -> NoReturn:
    if cause is None:
        raise TypeError(message)
    raise TypeError(message) from cause


def _schema_from_signature(signature: inspect.Signature, *, ignore_params: set[str] | None = None) -> dict[str, Any]:
    ignore = ignore_params or set()
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in signature.parameters.values():
        if param.name in ignore:
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        properties[param.name] = _schema_from_annotation(param.annotation)
        if param.default is param.empty:
            required.append(param.name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _validate_tool_schema(tool_schema: dict[str, Any]) -> str:
    if tool_schema.get("type") != "function":
        _raise_value_error("Tool schema must have type='function'.")
    function = tool_schema.get("function")
    if not isinstance(function, dict):
        _raise_type_error("Tool schema must include a 'function' object.")
    function = cast(dict[str, Any], function)
    name = function.get("name")
    if not isinstance(name, str):
        _raise_type_error("Tool schema must include a non-empty function name.")
    name = cast(str, name)
    if not name.strip():
        _raise_value_error("Tool schema must include a non-empty function name.")
    if "parameters" not in function:
        _raise_value_error("Tool schema must include function parameters.")
    return name


@dataclass(frozen=True)
class Tool:
    """A Tool is a callable unit the model can invoke."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Any] | None = None
    context: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def as_tool(self, json_mode: bool = False) -> str | dict[str, Any]:
        schema = self.schema()
        if json_mode:
            return json.dumps(schema, indent=2)
        return schema

    def run(self, *args: Any, **kwargs: Any) -> Any:
        handler = self.handler
        if handler is None:
            _raise_type_error(f"Tool '{self.name}' is schema-only and cannot be executed.")
        handler = cast(Callable[..., Any], handler)
        return handler(*args, **kwargs)

    @classmethod
    def from_callable(
        cls,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        context: bool = False,
    ) -> Tool:
        signature = inspect.signature(func)
        if context and "context" not in signature.parameters:
            _raise_type_error("Tool context is enabled but the callable lacks a 'context' parameter.")
        tool_name = name or _to_snake_case(_callable_name(func))
        tool_description = description if description is not None else (inspect.getdoc(func) or "")
        parameters = _schema_from_signature(signature, ignore_params={"context"} if context else None)
        validated = validate_call(func)
        return cls(
            name=tool_name,
            description=tool_description,
            parameters=parameters,
            handler=validated,
            context=context,
        )

    @classmethod
    def from_model(
        cls,
        model: type[ModelT],
        handler: Callable[..., Any] | None = None,
        *,
        context: bool = False,
    ) -> Tool:
        if handler is None:

            def _default_handler(payload: ModelT) -> Any:
                return payload.model_dump()

            handler_fn = _default_handler
        else:
            handler_fn = handler
        return tool_from_model(model, handler_fn, context=context)

    @classmethod
    def convert_tools(cls, tools: ToolInput) -> list[Tool]:
        if not tools:
            return []
        if isinstance(tools, ToolSet):
            return tools.runnable
        if any(isinstance(tool_item, dict) for tool_item in tools):
            _raise_type_error("Schema-only tools are not supported in convert_tools.")
        toolset = normalize_tools(tools)
        return toolset.runnable


@dataclass(frozen=True)
class ToolSet:
    """Normalized tools with schema payload and runnable implementations."""

    schemas: list[dict[str, Any]]
    runnable: list[Tool]

    @property
    def payload(self) -> list[dict[str, Any]] | None:
        return self.schemas or None

    def require_runnable(self) -> None:
        if self.schemas and not self.runnable:
            _raise_value_error("Schema-only tools cannot be executed.")

    @classmethod
    def from_tools(cls, tools: ToolInput) -> ToolSet:
        return normalize_tools(tools)


def schema_from_model(
    model: type[ModelT],
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a tool schema from a Pydantic model without making it runnable."""
    model_name = name or _to_snake_case(model.__name__)
    model_description = description if description is not None else (model.__doc__ or "")
    return {
        "type": "function",
        "function": {
            "name": model_name,
            "description": model_description,
            "parameters": model.model_json_schema(),
        },
    }


def tool_from_model(
    model: type[ModelT],
    handler: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    context: bool = False,
) -> Tool:
    """Create a runnable Tool that validates inputs via a Pydantic model."""
    tool_name = name or _to_snake_case(model.__name__)
    tool_description = description if description is not None else (model.__doc__ or "")

    if context:
        signature = inspect.signature(handler)
        if "context" not in signature.parameters:
            _raise_type_error("Tool context is enabled but the handler lacks a 'context' parameter.")

    def _handler(*args: Any, **kwargs: Any) -> Any:
        tool_context = kwargs.pop("context", None)
        parsed = model(*args, **kwargs)
        if context:
            return handler(parsed, context=tool_context)
        return handler(parsed)

    return Tool(
        name=tool_name,
        description=tool_description,
        parameters=model.model_json_schema(),
        handler=_handler,
        context=context,
    )


ToolInput = ToolSet | Sequence[Any] | None


@dataclass(frozen=True)
class _ToolEntry:
    schema: dict[str, Any]
    runnable: Tool | None


def _ensure_unique(name: str, seen_names: set[str]) -> None:
    if not name:
        _raise_value_error("Tool name cannot be empty.")
    if name in seen_names:
        _raise_value_error(f"Duplicate tool name: {name}")
    seen_names.add(name)


def _normalize_tool_item(tool_item: Any, seen_names: set[str]) -> _ToolEntry:
    if isinstance(tool_item, dict):
        tool_name = _validate_tool_schema(tool_item)
        _ensure_unique(tool_name, seen_names)
        return _ToolEntry(schema=tool_item, runnable=None)

    if isinstance(tool_item, Tool):
        tool_obj = tool_item
    elif callable(tool_item):
        tool_obj = Tool.from_callable(tool_item)
    else:
        _raise_type_error(f"Unsupported tool type: {type(tool_item)}")

    _ensure_unique(tool_obj.name, seen_names)
    return _ToolEntry(
        schema=tool_obj.schema(),
        runnable=tool_obj if tool_obj.handler is not None else None,
    )


def normalize_tools(tools: ToolInput) -> ToolSet:
    """Normalize tool-like objects into a ToolSet."""
    if tools is None:
        return ToolSet([], [])
    if isinstance(tools, ToolSet):
        return tools
    if isinstance(tools, Sequence) and any(isinstance(tool_item, ToolSet) for tool_item in tools):
        _raise_type_error("ToolSet cannot be mixed with other tool definitions.")
    if not tools:
        return ToolSet([], [])

    schemas: list[dict[str, Any]] = []
    runnable_tools: list[Tool] = []
    seen_names: set[str] = set()

    for tool_item in tools:
        entry = _normalize_tool_item(tool_item, seen_names)
        schemas.append(entry.schema)
        if entry.runnable is not None:
            runnable_tools.append(entry.runnable)

    return ToolSet(schemas, runnable_tools)


@overload
def tool(
    func: Callable[P, Any],
    *,
    name: str | None = None,
    description: str | None = None,
    context: bool = False,
) -> Tool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    context: bool = False,
) -> Callable[[Callable[P, Any]], Tool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    context: bool = False,
) -> Tool | Callable[[Callable[..., Any]], Tool]:
    """Decorator to convert a function into a Tool instance."""

    def _create_tool(f: Callable[..., Any]) -> Tool:
        return Tool.from_callable(f, name=name, description=description, context=context)

    if func is None:
        return _create_tool
    return _create_tool(func)
