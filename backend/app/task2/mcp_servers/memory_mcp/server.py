"""Custom Memory MCP Server.

Provides tools for storing and retrieving execution context:
- store_context: store execution context (page state, executed steps)
- retrieve_context: retrieve previous execution state info
- get_scenario: get current test scenario details

Uses Python MCP SDK (mcp.server.Server) with stdio transport.
Data is stored in memory (dict) with optional SQLite persistence.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory store (backed by optional SQLite)
# ---------------------------------------------------------------------------

_memory_store: dict[str, Any] = {}

# SQLite persistence path — if set, context is also persisted to disk
DB_PATH = os.getenv("MEMORY_MCP_DB_PATH", "")

_db_connection: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection | None:
    """Get or create SQLite connection for persistence."""
    global _db_connection
    if not DB_PATH:
        return None
    if _db_connection is None:
        _db_connection = sqlite3.connect(DB_PATH)
        _db_connection.execute(
            "CREATE TABLE IF NOT EXISTS context_store "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        _db_connection.commit()
    return _db_connection


def _store(key: str, data: Any) -> str:
    """Store data under a key. Returns confirmation message."""
    # In-memory store
    _memory_store[key] = data

    # Persist to SQLite if configured
    db = _get_db()
    if db is not None:
        value_str = json.dumps(data) if not isinstance(data, str) else data
        db.execute(
            "INSERT OR REPLACE INTO context_store (key, value) VALUES (?, ?)",
            (key, value_str),
        )
        db.commit()

    return f"Stored context under key '{key}'"


def _retrieve(key: str) -> str:
    """Retrieve data by key. Returns JSON string or 'not found' message."""
    # Check in-memory first
    if key in _memory_store:
        data = _memory_store[key]
        if isinstance(data, str):
            return data
        return json.dumps(data)

    # Fall back to SQLite if configured
    db = _get_db()
    if db is not None:
        row = db.execute(
            "SELECT value FROM context_store WHERE key = ?",
            (key,),
        ).fetchone()
        if row:
            return row[0]

    return f"No context found for key '{key}'"


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

app = Server("memory-mcp")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available Memory MCP tools."""
    return [
        types.Tool(
            name="store_context",
            description="Store execution context data under a key for later retrieval. "
                        "Use this to save page states, executed steps, and other "
                        "context information during test execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Unique key to store the context under.",
                    },
                    "data": {
                        "type": "string",
                        "description": "The context data to store. Can be a JSON string "
                                       "or plain text.",
                    },
                },
                "required": ["key", "data"],
            },
        ),
        types.Tool(
            name="retrieve_context",
            description="Retrieve previously stored context data by key. "
                        "Returns the stored data as a string, or a 'not found' "
                        "message if the key doesn't exist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key to look up in the context store.",
                    },
                },
                "required": ["key"],
            },
        ),
        types.Tool(
            name="get_scenario",
            description="Get the current test scenario details stored in memory. "
                        "Returns the full scenario JSON including steps and expectations.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls for the Memory MCP server."""
    if name == "store_context":
        key = arguments.get("key", "")
        data = arguments.get("data", "")
        if not key:
            return [types.TextContent(type="text", text="Error: 'key' parameter is required")]
        result = _store(key, data)
        return [types.TextContent(type="text", text=result)]

    elif name == "retrieve_context":
        key = arguments.get("key", "")
        if not key:
            return [types.TextContent(type="text", text="Error: 'key' parameter is required")]
        result = _retrieve(key)
        return [types.TextContent(type="text", text=result)]

    elif name == "get_scenario":
        scenario_data = _retrieve("current_scenario")
        return [types.TextContent(type="text", text=scenario_data)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    """Run the Memory MCP server via stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())