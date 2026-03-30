from collections.abc import Awaitable, Callable
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters  # pyright: ignore[reportMissingImports]
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from mcp.client.stdio import stdio_client  # pyright: ignore[reportMissingImports]
from mcp.shared.context import RequestContext  # pyright: ignore[reportMissingImports]

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

        result = await self.session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict | None = None):
        if not self.session:
            raise RuntimeError("Client not connected")

        result = await self.session.call_tool(
            name,
            arguments or {},
        )
        return result
