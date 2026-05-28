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
from app.events import broadcaster

logger = logging.getLogger(__name__)

# Map node names to execution status for frontend display
_NODE_STATUS_MAP = {
    "plan": "planning",
    "execute": "executing",
    "verify": "verifying",
    "reflect": "reflecting",
}


def _update_execution_status(scenario: dict, node_name: str, state: dict) -> None:
    """Update the execution record's status in the database AND publish
    a WebSocket event so the frontend sees real-time node transitions.

    Only updates the 'status' field — the full state update happens in
    task2_routes.py after run_agent completes.
    """
    from app.db.database import SessionLocal
    from app.db.models import ExecutionRecord

    # Find the execution record for this scenario
    # Use the most recent execution record for this scenario_id
    scenario_id = scenario.get("id", "")
    db = SessionLocal()
    try:
        record = db.query(ExecutionRecord).filter(
            ExecutionRecord.scenario_id == scenario_id,
            ExecutionRecord.status.in_(["planning", "executing", "verifying", "reflecting", "pending"]),
        ).order_by(ExecutionRecord.started_at.desc()).first()

        if record:
            new_status = _NODE_STATUS_MAP.get(node_name, "executing")
            # After verify completes, set to completed/failed based on result
            if node_name == "verify":
                if state.get("final_result") == "pass":
                    new_status = "completed"
                else:
                    # Still might go to reflect, so keep as verifying
                    new_status = "verifying"
            elif node_name == "reflect":
                new_status = "reflecting"

            record.status = new_status
            db.commit()
            logger.info("Updated execution %s status to '%s' (node: %s)", record.id, new_status, node_name)

            # --- Publish WebSocket event ---
            if node_name == "execute":
                # Publish step_completed with latest executed step info
                executed_steps = state.get("executed_steps", [])
                if executed_steps:
                    latest_step = executed_steps[-1] if isinstance(executed_steps, list) else None
                    broadcaster.publish({
                        "type": "step_completed",
                        "execution_id": record.id,
                        "step_result": latest_step or {},
                    })
                else:
                    broadcaster.publish({
                        "type": "status_update",
                        "execution_id": record.id,
                        "scenario_id": scenario_id,
                        "status": new_status,
                    })
            elif node_name == "verify":
                broadcaster.publish({
                    "type": "verification_completed",
                    "execution_id": record.id,
                    "verify_result": state.get("verification_result", {}),
                })
            elif node_name == "reflect":
                broadcaster.publish({
                    "type": "reflection_started",
                    "execution_id": record.id,
                    "retry_count": state.get("retry_count", 0),
                })
            else:
                # plan node or fallback — generic status_update
                broadcaster.publish({
                    "type": "status_update",
                    "execution_id": record.id,
                    "scenario_id": scenario_id,
                    "status": new_status,
                })
    except Exception as exc:
        logger.warning("Failed to update execution status: %s", exc)
        db.rollback()
    finally:
        db.close()


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
        "memory_context": {},
    }

    logger.info("Starting agent execution for scenario '%s'", scenario.get("name", "Unknown"))

    final_state = dict(initial_state)

    try:
        # Stream node updates — each chunk is a dict {node_name: state_update}
        async for chunk in compiled_graph.astream(initial_state):
            # chunk is like {"plan": {...partial_state...}}
            for node_name, state_update in chunk.items():
                logger.info("Node '%s' completed", node_name)
                # Merge partial state update into final_state
                final_state.update(state_update)

                # Update execution record status in DB for frontend visibility
                _update_execution_status(scenario, node_name, final_state)
    except asyncio.CancelledError as exc:
        logger.error("Agent graph execution was cancelled: %s", exc)
        final_state["final_result"] = "fail"
        final_state["failure_reason"] = f"执行被取消: {exc}"
    except Exception as exc:
        logger.error("Agent graph execution failed: %s", exc)
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