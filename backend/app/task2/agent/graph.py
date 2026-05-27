"""LangGraph state graph for the Agent Execution system.

Defines the state graph: START -> PLAN -> EXECUTE -> VERIFY -> conditional.
Conditional edge: pass -> END (success), fail -> REFLECT -> re-plan -> EXECUTE.
Max retry logic: after 3 retries, go to END (fail + reason).
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph

from app.task2.agent.state import AgentState
from app.task2.agent.nodes.plan import plan_node
from app.task2.agent.nodes.execute import execute_node
from app.task2.agent.nodes.verify import verify_node
from app.task2.agent.nodes.reflect import reflect_node

logger = logging.getLogger(__name__)


def should_continue_after_verify(state: AgentState) -> str:
    """Conditional edge function after the VERIFY node.

    Determines the next step based on verification result:
    - If final_result == "pass": go to END (success)
    - If final_result == "fail" and retry_count < 3: go to REFLECT
    - If final_result == "fail" and retry_count >= 3: go to END (max retries exceeded)

    Args:
        state: Current AgentState after verification.

    Returns:
        Node name string for the next step.
    """
    final_result = state.get("final_result", "")
    retry_count = state.get("retry_count", 0)

    if final_result == "pass":
        logger.info("Verification passed — going to END")
        return "end_success"

    # Verification failed
    if retry_count >= 3:
        logger.info("Max retries exceeded (retry_count=%d) — going to END (fail)", retry_count)
        return "end_fail"

    logger.info("Verification failed (retry_count=%d) — going to REFLECT", retry_count)
    return "reflect"


def should_continue_after_reflect(state: AgentState) -> str:
    """Conditional edge function after the REFLECT node.

    Determines the next step based on reflection result:
    - If plan is non-empty: go to EXECUTE (re-execute with revised plan)
    - If plan is empty or final_result=="fail": go to END

    Args:
        state: Current AgentState after reflection.

    Returns:
        Node name string for the next step.
    """
    plan = state.get("plan", [])
    final_result = state.get("final_result", "")

    if final_result == "fail":
        # Reflection determined no more retries
        logger.info("Reflection determined no more retries — going to END (fail)")
        return "end_fail"

    if plan:
        logger.info("Reflection produced revised plan (%d actions) — going to EXECUTE", len(plan))
        return "execute"

    # No plan and not explicitly marked as fail — also end
    logger.info("No revised plan available — going to END")
    return "end_fail"


def build_agent_graph() -> StateGraph:
    """Construct the LangGraph state graph for the test agent.

    Graph flow:
        START -> PLAN -> EXECUTE -> VERIFY
        VERIFY -> [pass?] -> END (success)
        VERIFY -> [fail, retry_count < 3] -> REFLECT -> EXECUTE (loop)
        VERIFY -> [fail, retry_count >= 3] -> END (fail)
        REFLECT -> [has revised plan] -> EXECUTE (loop)
        REFLECT -> [no revised plan] -> END (fail)

    Returns:
        Compiled StateGraph ready for execution.
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("verify", verify_node)
    graph.add_node("reflect", reflect_node)

    # Set entry point
    graph.add_edge(START, "plan")

    # Plan -> Execute
    graph.add_edge("plan", "execute")

    # Execute -> Verify
    graph.add_edge("execute", "verify")

    # Verify -> conditional (pass/reflect/end_fail)
    graph.add_conditional_edges(
        "verify",
        should_continue_after_verify,
        {
            "end_success": END,
            "reflect": "reflect",
            "end_fail": END,
        },
    )

    # Reflect -> conditional (execute/end_fail)
    graph.add_conditional_edges(
        "reflect",
        should_continue_after_reflect,
        {
            "execute": "execute",
            "end_fail": END,
        },
    )

    return graph.compile()


async def run_agent(scenario: dict) -> AgentState:
    """Execute a test scenario through the complete agent graph.

    Initializes the AgentState with the given scenario and runs it
    through the PLAN -> EXECUTE -> VERIFY -> REFLECT loop until
    the scenario either passes or exhausts retries.

    The agent runs in a degraded mode if MCP servers are unavailable:
    - Planning node still works (uses LLM without MCP context)
    - Execute node produces error steps (MCP client returns degraded messages)
    - Verify node uses LLM-only verification (MCP tools unavailable)

    Args:
        scenario: Test scenario dict from Task 1 output, containing
                  name, steps, expectations, etc.

    Returns:
        Final AgentState after the graph completes, including
        final_result ("pass" or "fail"), failure_reason (if failed),
        executed_steps, screenshots, and verification_result.
    """
    compiled_graph = build_agent_graph()

    # Initialize state with all required fields
    initial_state: AgentState = {
        "scenario": scenario,
        "plan": [],
        "executed_steps": [],
        "current_page_state": {},
        "screenshots": [],
        "verification_result": {},
        "retry_count": 0,
        "reflection": "",
        "final_result": "",
        "failure_reason": "",
    }

    logger.info("Starting agent execution for scenario '%s'", scenario.get("name", "Unknown"))

    # Execute node uses multiprocessing for MCP connections,
    # so no need for thread isolation. Run graph directly.
    try:
        final_state = await compiled_graph.ainvoke(initial_state)
    except asyncio.CancelledError as exc:
        logger.error("Agent graph execution was cancelled: %s", exc)
        final_state = dict(initial_state)
        final_state["final_result"] = "fail"
        final_state["failure_reason"] = f"执行被取消: {exc}"
    except Exception as exc:
        logger.error("Agent graph execution failed: %s", exc)
        final_state = dict(initial_state)
        final_state["final_result"] = "fail"
        final_state["failure_reason"] = f"Agent graph execution failed: {exc}"

    result = final_state.get("final_result", "fail")
    logger.info(
        "Agent execution complete: result=%s, retries=%d",
        result, final_state.get("retry_count", 0),
    )

    if result == "fail":
        logger.info("Failure reason: %s", final_state.get("failure_reason", "Unknown"))

    return final_state