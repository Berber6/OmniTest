"""Agent state definition for the LangGraph state graph.

Defines the TypedDict used as the shared state object flowing
through all nodes in the PLAN → EXECUTE → VERIFY → REFLECT cycle.
"""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict):
    """State object passed between nodes in the LangGraph agent graph.

    Each node reads relevant fields, performs its work, and updates
    the fields it owns. LangGraph merges updates back into the state
    dict after each node invocation.
    """

    scenario: dict          # Test scenario to execute (from Task 1 output)
    plan: list[dict]        # Execution plan: list of Actions (tool + args + description)
    executed_steps: list[dict]  # Results from executed steps
    current_page_state: dict    # Current browser page state snapshot
    screenshots: list[str]      # Base64-encoded screenshots captured during execution
    verification_result: dict   # Verification result: pass/fail + details
    retry_count: int            # Current retry count (max = 3)
    reflection: str             # Reflection analysis text from the REFLECT node
    final_result: str           # Final result: "pass" or "fail"
    failure_reason: str         # Detailed failure reason when result is "fail"
    memory_context: dict       # Context stored/retrieved via Memory MCP