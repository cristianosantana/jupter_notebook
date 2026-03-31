from collections.abc import Awaitable, Callable
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters  # pyright: ignore[reportMissingImports]
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from mcp.client.stdio import stdio_client  # pyright: ignore[reportMissingImports]
from mcp.shared.context import RequestContext  # pyright: ignore[reportMissingImports]

from app.agent_trace import get_trace_logger

SamplingCallback = Callable[
    [RequestContext[Any, Any], mcp_types.CreateMessageRequestParams],
    Awaitable[
        mcp_types.CreateMessageResult
        | mcp_types.CreateMessageResultWithTools
        | mcp_types.ErrorData
    ],
]


class Client:

    def __init__(
        self,
        server_script: str,
        *,
        sampling_callback: SamplingCallback | None = None,
        sampling_capabilities: mcp_types.SamplingCapability | None = None,
    ):
        self.server_script = server_script
        self.sampling_callback = sampling_callback
        self.sampling_capabilities = sampling_capabilities
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def connect(self):
        """Inicia o servidor MCP e conecta."""

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_script],
        )

        transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        read, write = transport

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(
                read,
                write,
                sampling_callback=self.sampling_callback,
                sampling_capabilities=self.sampling_capabilities,
            )
        )

        await self.session.initialize()

    async def close(self):
        await self.exit_stack.aclose()

    async def list_tools(self):
        if not self.session:
            raise RuntimeError("Client not connected")

        tr = get_trace_logger()
        if tr:
            tr.record("mcp.client.list_tools.request")

        result = await self.session.list_tools()
        if tr:
            tr.record(
                "mcp.client.list_tools.response",
                tool_names=[t.name for t in result.tools],
                tool_count=len(result.tools),
            )
        return result.tools

    async def call_tool(self, name: str, arguments: dict | None = None):
        if not self.session:
            raise RuntimeError("Client not connected")

        tr = get_trace_logger()
        meta = None
        if tr:
            meta = {"agent_trace_run_id": tr.run_id}
            tr.record("mcp.client.call_tool.request", tool=name, arguments=arguments or {})

        result = await self.session.call_tool(
            name,
            arguments or {},
            meta=meta,
        )
        if tr:
            try:
                dumped = result.model_dump(mode="json")
            except Exception as e:
                dumped = {"error_serializing": str(e), "repr": repr(result)}
            tr.record("mcp.client.call_tool.response", tool=name, result=dumped)
        return result
