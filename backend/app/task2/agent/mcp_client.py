"""Custom MCP Client implementation for connecting to MCP servers.

Manages connections to Playwright MCP, Memory MCP, and Verify MCP
servers using the Python MCP SDK's stdio transport. Provides a
unified call_tool interface and lifecycle management.

Features graceful degradation: if MCP servers aren't available,
tool calls return a structured error response instead of crashing,
allowing the agent pipeline to continue in degraded mode.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from app.task2.agent.env_utils import build_child_env, find_chrome_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server connection configs
# Use "app.xxx" module paths (not "backend.app.xxx") for internal servers
# ---------------------------------------------------------------------------

CLEAN_ENV = build_child_env()

CHROME_PATH = find_chrome_path() or ""

PLAYWRIGHT_ARGS = ["-y", "@playwright/mcp@latest", "--headless", "--isolated"]
if CHROME_PATH:
    PLAYWRIGHT_ARGS.extend(["--executable-path", CHROME_PATH])
# --isolated: 每个 MCP 会话使用独立的内存浏览器 profile，避免多个并发 agent
# 子进程共享同一 user-data-dir 时报 "Browser is already in use" 错误。
# 代价：不持久化登录态，但 runner 每次执行本就重新登录，无影响。

MCP_SERVER_CONFIGS: dict[str, StdioServerParameters] = {
    "playwright": StdioServerParameters(
        command="npx",
        args=PLAYWRIGHT_ARGS,
        env=CLEAN_ENV,
    ),
    "memory": StdioServerParameters(
        command="python",
        args=["-m", "app.task2.mcp_servers.memory_mcp.server"],
        env=CLEAN_ENV,
    ),
    "verify": StdioServerParameters(
        command="python",
        args=["-m", "app.task2.mcp_servers.verify_mcp.server"],
        env=CLEAN_ENV,
    ),
}

# Sentinel value indicating a server is not connected
_NOT_CONNECTED = "NOT_CONNECTED"


class MCPClient:
    """Manages connections to multiple MCP servers and provides
    a unified interface for calling tools and listing available tools.

    Supports graceful degradation: if a server is unavailable,
    call_tool returns a structured error text rather than raising,
    and the agent pipeline can continue with degraded functionality.

    Usage:
        client = MCPClient()
        await client.connect()
        result = await client.call_tool_text("playwright", "browser_navigate", {"url": "https://example.com"})
        await client.disconnect()
    """

    def __init__(self, server_configs: dict[str, StdioServerParameters] | None = None) -> None:
        self._configs = server_configs or MCP_SERVER_CONFIGS
        # Per-server connection state
        self._sessions: dict[str, ClientSession] = {}
        self._read_streams: dict[str, Any] = {}
        self._write_streams: dict[str, Any] = {}
        self._exit_stack: dict[str, Any] = {}  # context managers for cleanup
        self._connected = False
        self._connect_errors: dict[str, str] = {}  # errors for servers that failed to connect

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, servers: list[str] | None = None) -> None:
        """Connect to specified MCP servers (or all configured ones).

        Opens stdio connections and initializes MCP sessions. If a
        server connection fails, logs a warning but continues with
        remaining servers. Failed servers are tracked in _connect_errors
        so that call_tool can return graceful error messages.
        """
        target_servers = servers or list(self._configs.keys())
        logger.info("Connecting to MCP servers: %s", target_servers)
        for name in target_servers:
            params = self._configs.get(name)
            if not params:
                logger.warning("Unknown MCP server '%s'", name)
                self._connect_errors[name] = f"Unknown server: {name}"
                continue
            try:
                await self._connect_server(name, params)
            except Exception as exc:
                logger.warning("Failed to connect to MCP server '%s': %s", name, exc)
                self._connect_errors[name] = str(exc)
        self._connected = True
        connected_count = len(self._sessions)
        target_count = len(target_servers)
        logger.info("MCP client connected (%d/%d servers requested)", connected_count, target_count)
        if self._connect_errors:
            logger.warning(
                "Some MCP servers unavailable: %s. Agent will run in degraded mode.",
                list(self._connect_errors.keys()),
            )

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers and clean up resources."""
        logger.info("Disconnecting from MCP servers")
        for name in list(self._sessions.keys()):
            await self._disconnect_server(name)
        self._connected = False
        self._connect_errors.clear()
        logger.info("MCP client disconnected")

    async def reconnect(self, server_name: str) -> None:
        """Reconnect a specific MCP server.

        Args:
            server_name: Name of the server to reconnect (must be in configs).

        Raises:
            ValueError: If server_name is not in the configured servers.
        """
        if server_name not in self._configs:
            raise ValueError(f"Unknown MCP server: '{server_name}'")

        await self._disconnect_server(server_name)
        try:
            await self._connect_server(server_name, self._configs[server_name])
            self._connect_errors.pop(server_name, None)
            logger.info("Successfully reconnected MCP server '%s'", server_name)
        except Exception as exc:
            logger.error("Failed to reconnect MCP server '%s': %s", server_name, exc)
            self._connect_errors[server_name] = str(exc)
            raise

    # ------------------------------------------------------------------
    # Tool operations — with graceful degradation
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Call a tool on a connected MCP server.

        If the server is not connected, returns a TextContent error
        block instead of raising an exception (graceful degradation).

        Args:
            server_name: Target MCP server name (e.g. "playwright").
            tool_name: Tool name on that server (e.g. "browser_click").
            arguments: Tool arguments dict.

        Returns:
            List of content blocks from the tool result, or a single
            TextContent error block if the server is unavailable.
        """
        session = self._sessions.get(server_name)
        if session is None:
            error_msg = self._connect_errors.get(server_name, "not connected")
            degraded_msg = (
                f"MCP server '{server_name}' is unavailable: {error_msg}. "
                f"Running in degraded mode — tool '{tool_name}' cannot be executed."
            )
            logger.warning(degraded_msg)
            return [types.TextContent(type="text", text=degraded_msg)]

        try:
            result = await session.call_tool(tool_name, arguments or {})
            return result.content
        except Exception as exc:
            logger.error(
                "MCP tool call failed: server='%s', tool='%s', args=%s: %s",
                server_name, tool_name, arguments, exc,
            )
            error_msg = f"Tool call '{tool_name}' on '{server_name}' failed: {exc}"
            return [types.TextContent(type="text", text=error_msg)]

    async def call_tool_checked(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """Call a tool and return (text, is_error).

        Unlike call_tool/call_tool_text which silently swallow tool-level
        failures, this surfaces the MCP result's isError flag so the caller
        can tell a real failure (stale ref, element not found, navigation
        error) apart from a successful call. This is essential for the
        observe→act loop to know whether an action actually worked.

        Returns:
            (joined_text, is_error). If the server is unavailable, returns
            (degraded_message, True).
        """
        session = self._sessions.get(server_name)
        if session is None:
            error_msg = self._connect_errors.get(server_name, "not connected")
            degraded = (
                f"MCP server '{server_name}' unavailable: {error_msg}. "
                f"Tool '{tool_name}' cannot be executed."
            )
            logger.warning(degraded)
            return degraded, True

        try:
            result = await session.call_tool(tool_name, arguments or {})
            texts = [
                block.text for block in result.content
                if isinstance(block, types.TextContent)
            ]
            text = "\n".join(texts)
            is_error = bool(getattr(result, "isError", False))
            return text, is_error
        except Exception as exc:
            logger.error(
                "MCP tool call raised: server='%s', tool='%s': %s",
                server_name, tool_name, exc,
            )
            return f"Tool '{tool_name}' on '{server_name}' raised: {exc}", True

    async def call_tool_text(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """Call a tool and return the concatenated text content.

        Convenience method that calls call_tool and extracts only
        TextContent blocks, joining their text. If the server is
        unavailable, returns a degraded-mode message string.

        Args:
            server_name: Target MCP server name.
            tool_name: Tool name on that server.
            arguments: Tool arguments dict.

        Returns:
            Joined text from all TextContent result blocks, or an
            error message if the server is unavailable.
        """
        content_blocks = await self.call_tool(server_name, tool_name, arguments)
        texts = [
            block.text for block in content_blocks
            if isinstance(block, types.TextContent)
        ]
        return "\n".join(texts)

    async def list_tools(self, server_name: str) -> list[types.Tool]:
        """List available tools on a connected MCP server.

        Args:
            server_name: Target MCP server name.

        Returns:
            List of Tool definitions from the server, or empty list
            if server is not connected.
        """
        session = self._sessions.get(server_name)
        if session is None:
            logger.warning("Cannot list tools for '%s': not connected", server_name)
            return []

        try:
            result = await session.list_tools()
            return result.tools
        except Exception as exc:
            logger.warning("Failed to list tools from '%s': %s", server_name, exc)
            return []

    async def list_all_tools(self) -> dict[str, list[types.Tool]]:
        """List tools from all connected MCP servers.

        Returns:
            Dict mapping server_name → list of Tool definitions.
        """
        all_tools: dict[str, list[types.Tool]] = {}
        for name in self._sessions:
            try:
                all_tools[name] = await self.list_tools(name)
            except Exception as exc:
                logger.warning("Failed to list tools from '%s': %s", name, exc)
                all_tools[name] = []
        return all_tools

    async def is_server_connected(self, server_name: str) -> bool:
        """Check if a specific MCP server is connected."""
        return server_name in self._sessions

    @property
    def connected_servers(self) -> list[str]:
        """Names of currently connected MCP servers."""
        return list(self._sessions.keys())

    @property
    def unavailable_servers(self) -> list[str]:
        """Names of MCP servers that failed to connect."""
        return list(self._connect_errors.keys())

    @property
    def is_connected(self) -> bool:
        """Whether the client has been initialized."""
        return self._connected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect_server(self, name: str, params: StdioServerParameters) -> None:
        """Open a stdio connection to one MCP server and initialize session.

        Uses the MCP SDK's async context manager pattern (async with)
        instead of manual __aenter__/__aexit__ calls to avoid cancel
        scope conflicts with anyio's task groups.
        """
        # Check if the command is available (npx for playwright)
        if params.command == "npx":
            npx_path = shutil.which("npx")
            if not npx_path:
                raise RuntimeError(
                    "npx is not available on PATH. Install Node.js/npx "
                    "to use the Playwright MCP server."
                )

        try:
            # 使用 async with 模式连接，避免与 anyio cancel scope 冲突
            streams_ctx = stdio_client(params)
            read_stream, write_stream = await streams_ctx.__aenter__()

            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            self._sessions[name] = session
            self._read_streams[name] = read_stream
            self._write_streams[name] = write_stream
            self._exit_stack[name] = streams_ctx

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            logger.info(
                "Connected to MCP server '%s' with tools: %s",
                name, tool_names,
            )
        except Exception as exc:
            logger.warning("MCP server '%s' connection failed: %s", name, exc)
            raise

    async def _disconnect_server(self, name: str) -> None:
        """Close the stdio connection for one MCP server.

        Swallows anyio cancel scope errors since MCP SDK's exit
        doesn't handle cross-task scope closure gracefully.
        """
        streams_context = self._exit_stack.pop(name, None)
        self._sessions.pop(name, None)
        self._read_streams.pop(name, None)
        self._write_streams.pop(name, None)

        if streams_context is not None:
            try:
                await streams_context.__aexit__(None, None, None)
            except RuntimeError as exc:
                # anyio cancel scope错误：不同task退出scope
                # 这是MCP SDK已知问题，忽略即可
                logger.info("MCP server '%s' close: %s (known anyio issue, ignored)", name, exc)
            except Exception as exc:
                logger.warning("Error closing MCP server '%s': %s", name, exc)
            try:
                await streams_context.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("Error closing MCP server '%s': %s", name, exc)