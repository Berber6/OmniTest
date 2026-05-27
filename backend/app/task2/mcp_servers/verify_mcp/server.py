"""Custom Verify MCP Server.

Provides verification tools for checking test execution results:
- compare_screenshots: compare expected vs actual screenshots
- check_text_content: check if page text contains expected content
- check_element_exists: check if specific DOM element exists

Uses Python MCP SDK with stdio transport.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

logger = logging.getLogger(__name__)


def _check_text_content(page_text: str, expected_text: str) -> str:
    """Check if page text contains the expected text content.

    Performs case-insensitive substring matching and returns
    a detailed result including match location.

    Args:
        page_text: The full text content of the page.
        expected_text: The expected text to search for.

    Returns:
        JSON-formatted result string.
    """
    page_lower = page_text.lower()
    expected_lower = expected_text.lower()

    # Direct substring match
    if expected_lower in page_lower:
        # Find the match location
        idx = page_lower.find(expected_lower)
        context_start = max(0, idx - 50)
        context_end = min(len(page_text), idx + len(expected_text) + 50)
        context = page_text[context_start:context_end]
        return json_result(True, f"Found expected text '{expected_text}' in page. "
                                 f"Context: ...{context}...")

    # Try word-by-word matching (for multi-word expectations)
    expected_words = expected_lower.split()
    if len(expected_words) > 1:
        matching_words = [w for w in expected_words if w in page_lower]
        match_ratio = len(matching_words) / len(expected_words)
        if match_ratio >= 0.7:
            return json_result(
                True,
                f"Partial match: {match_ratio:.0%} of expected words found. "
                f"Expected: '{expected_text}', "
                f"Matching words: {matching_words}",
                confidence=match_ratio,
            )

    # No match found
    # Report what's actually on the page for debugging
    snippet = page_text[:200] if len(page_text) > 200 else page_text
    return json_result(
        False,
        f"Expected text '{expected_text}' NOT found in page content. "
        f"Page begins with: '{snippet}'",
    )


def _compare_screenshots(expected_b64: str, actual_b64: str) -> str:
    """Compare two screenshots by analyzing their basic properties.

    This provides a lightweight pixel-level comparison. For detailed
    visual analysis, the agent uses Qwen3-VL via the verify node.

    Args:
        expected_b64: Base64-encoded expected screenshot.
        actual_b64: Base64-encoded actual screenshot.

    Returns:
        JSON-formatted comparison result.
    """
    try:
        expected_bytes = base64.b64decode(expected_b64)
        actual_bytes = base64.b64decode(actual_b64)

        expected_size = len(expected_bytes)
        actual_size = len(actual_bytes)

        # Size similarity check
        size_ratio = min(expected_size, actual_size) / max(expected_size, actual_size)

        if expected_bytes == actual_bytes:
            return json_result(True, "Screenshots are identical", confidence=1.0)

        if size_ratio > 0.9:
            return json_result(
                True,
                f"Screenshots have similar size (expected={expected_size}B, "
                f"actual={actual_size}B, ratio={size_ratio:.2f}). "
                f"Note: pixel-level differences may exist — use visual LLM "
                f"for detailed analysis.",
                confidence=0.6,
            )

        if size_ratio > 0.5:
            return json_result(
                False,
                f"Screenshots differ significantly in size "
                f"(expected={expected_size}B, actual={actual_size}B, "
                f"ratio={size_ratio:.2f}). This likely indicates different "
                f"page content or layout.",
                confidence=0.4,
            )

        return json_result(
            False,
            f"Screenshots are very different in size "
            f"(expected={expected_size}B, actual={actual_size}B). "
            f"Ratio={size_ratio:.2f}. Likely showing different pages.",
        )

    except Exception as exc:
        return json_result(False, f"Screenshot comparison error: {exc}")


def _check_element_exists(selector: str) -> str:
    """Check if a DOM element matching the selector likely exists.

    Since this MCP server doesn't have direct browser access, this
    tool provides heuristic guidance based on the selector pattern.
    The actual existence check is performed by the Playwright MCP
    browser_snapshot tool, which this tool supplements.

    Args:
        selector: CSS or XPath selector string.

    Returns:
        JSON-formatted result with guidance for the agent.
    """
    # Validate selector syntax
    if not selector:
        return json_result(False, "Empty selector provided")

    # Detect selector type and validate syntax
    if selector.startswith("//") or selector.startswith("/"):
        # XPath selector
        return json_result(
            True,
            f"XPath selector '{selector}' recognized. Use browser_snapshot "
            f"to verify the element exists on the current page.",
            confidence=0.5,  # Can't verify without browser
        )

    # CSS selector — basic syntax validation
    # Check for balanced brackets and valid characters
    if not re.match(r'^[a-zA-Z0-9_\-\[\]=":\*\.\s>#,\+:has-text\(\)\'~]+$', selector):
        return json_result(
            False,
            f"CSS selector '{selector}' may contain invalid syntax. "
            f"Please verify the selector format.",
        )

    return json_result(
        True,
        f"CSS selector '{selector}' appears valid. Use browser_snapshot "
        f"or browser_click with this selector to verify the element exists "
        f"and interact with it.",
        confidence=0.5,  # Can't verify without browser
    )


def json_result(
    passed: bool,
    reason: str,
    confidence: float | None = None,
) -> str:
    """Format a verification result as a JSON string."""
    import json
    if confidence is None:
        confidence = 1.0 if passed else 0.0
    return json.dumps({
        "passed": passed,
        "reason": reason,
        "confidence": confidence,
    })


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

app = Server("verify-mcp")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available Verify MCP tools."""
    return [
        types.Tool(
            name="compare_screenshots",
            description="Compare an expected screenshot with an actual screenshot. "
                        "Performs basic size and binary comparison. For detailed "
                        "visual analysis, use the Qwen3-VL vision model via the "
                        "verify node instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "expected_b64": {
                        "type": "string",
                        "description": "Base64-encoded expected screenshot image.",
                    },
                    "actual_b64": {
                        "type": "string",
                        "description": "Base64-encoded actual screenshot image.",
                    },
                },
                "required": ["expected_b64", "actual_b64"],
            },
        ),
        types.Tool(
            name="check_text_content",
            description="Check if page text content contains expected text. "
                        "Performs case-insensitive substring matching with "
                        "partial word matching support.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_text": {
                        "type": "string",
                        "description": "The full text content of the page to check.",
                    },
                    "expected_text": {
                        "type": "string",
                        "description": "The text expected to be present on the page.",
                    },
                },
                "required": ["page_text", "expected_text"],
            },
        ),
        types.Tool(
            name="check_element_exists",
            description="Validate a CSS or XPath selector and provide guidance "
                        "for verifying element existence via browser tools. "
                        "Note: this tool validates selector syntax but does not "
                        "have direct browser access — use browser_snapshot for "
                        "actual DOM verification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector or XPath expression to validate.",
                    },
                },
                "required": ["selector"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls for the Verify MCP server."""
    if name == "compare_screenshots":
        expected = arguments.get("expected_b64", "")
        actual = arguments.get("actual_b64", "")
        if not expected or not actual:
            return [types.TextContent(
                type="text",
                text="Error: both 'expected_b64' and 'actual_b64' parameters are required",
            )]
        result = _compare_screenshots(expected, actual)
        return [types.TextContent(type="text", text=result)]

    elif name == "check_text_content":
        page_text = arguments.get("page_text", "")
        expected_text = arguments.get("expected_text", "")
        if not page_text:
            return [types.TextContent(
                type="text",
                text="Error: 'page_text' parameter is required",
            )]
        if not expected_text:
            return [types.TextContent(
                type="text",
                text="Error: 'expected_text' parameter is required",
            )]
        result = _check_text_content(page_text, expected_text)
        return [types.TextContent(type="text", text=result)]

    elif name == "check_element_exists":
        selector = arguments.get("selector", "")
        result = _check_element_exists(selector)
        return [types.TextContent(type="text", text=result)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    """Run the Verify MCP server via stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())