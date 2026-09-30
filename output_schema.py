from __future__ import annotations

import json
from typing import Any, Sequence

import jsonschema

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult

from mcp.types import CallToolRequestParams, TextContent

from mcp_result import extract_structured_content

# TODO: Retrieve and cache path-specific WorkIQ schemas through ``get_schema``.


class OutputSchemaMiddleware(Middleware):
    """FastMCP middleware that advertises and enforces per-tool ``outputSchema``.

    On ``tools/list`` each tool whose name appears in *schemas* and that has
    no upstream-declared ``outputSchema`` gets the configured schema
    injected. Upstream-declared schemas are preserved (mirrors the
    "upstream wins" pattern used by the other gateway middlewares).

    On ``tools/call`` the middleware honours the contract it advertised: if
    *schemas* has an entry for the called tool and the upstream returned
    only unstructured ``content`` (no ``structuredContent``), the middleware
    extracts the structured payload via
    :func:`mcp_result.extract_structured_content` (which parses
    ``content[0].text`` as JSON, transparently tolerating WorkIQ-style
    trailing diagnostic blocks like ``CorrelationId: <guid>`` in
    ``content[1:]``), validates it against the configured schema, and
    rewrites the result so the parsed object becomes ``structuredContent``
    and ``content`` is replaced with a single canonical JSON text block
    (the MCP-recommended backwards-compat shape for tools that declare an
    ``outputSchema``).

    Failure modes when a schema is configured for the called tool:

    - upstream already returned ``structured_content`` — trusted, passed
      through unchanged (no double validation).
    - ``content[0]`` is missing, is not a text block, or its text is not
      valid JSON — raises ``ValueError`` (the underlying
      :func:`extract_structured_content` error is re-raised with the
      tool name attached for context).
    - JSON parses but fails schema validation — raises
      ``jsonschema.ValidationError``.

    Configured schemas are checked at construction time via
    :meth:`jsonschema.Draft202012Validator.check_schema` so malformed
    config fails fast at startup rather than at call time.
    """

    def __init__(self, schemas: dict[str, dict[str, Any]] | None = None) -> None:
        self.schemas = schemas or {}
        for tool_name, schema in self.schemas.items():
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.SchemaError as e:
                raise ValueError(
                    f"Invalid outputSchema configured for tool {tool_name!r}: {e.message}"
                ) from e

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        for tool in tools:
            schema = self.schemas.get(tool.name)
            if schema is not None and tool.output_schema is None:
                tool.output_schema = schema
        return tools

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        tool_name = context.message.name
        schema = self.schemas.get(tool_name)
        if schema is None:
            return result
        if result.structured_content is not None:
            return result

        try:
            parsed = extract_structured_content(result)
        except ValueError as e:
            raise ValueError(
                f"Tool {tool_name!r} declares an outputSchema but {e}"
            ) from e

        jsonschema.validate(parsed, schema)

        return ToolResult(
            content=[TextContent(type="text", text=json.dumps(parsed))],
            structured_content=parsed,
            meta=result.meta,
        )
