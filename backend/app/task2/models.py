"""Pydantic models for Task2 (execution, mutation, verification)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Action(BaseModel):
    """An action the agent takes on a web page."""

    tool: str = Field(..., description="MCP tool name, e.g. 'browser_click'")
    args: Dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the tool"
    )
    description: str = Field(default="", description="Human-readable description of the action")


class PageState(BaseModel):
    """Snapshot of the current browser page state."""

    url: str = Field(default="", description="Current page URL")
    title: str = Field(default="", description="Page title")
    text_content: str = Field(default="", description="Visible text on the page")
    visible_elements: List[str] = Field(
        default_factory=list, description="List of visible element selectors or labels"
    )
    screenshot_path: Optional[str] = Field(default=None, description="Path to screenshot file")


class StepResult(BaseModel):
    """Result of executing a single step in a scenario."""

    step_number: int = Field(..., description="Which step this result corresponds to")
    action: Action = Field(..., description="The action that was attempted")
    page_state: Optional["PageState"] = Field(None, description="Page state after the action")
    screenshot: str = Field(
        default="", description="Base64-encoded screenshot or path to screenshot file"
    )
    success: bool = Field(..., description="Whether the action succeeded")
    error: Optional[str] = Field(None, description="Error message if the step failed")


class VerifyResult(BaseModel):
    """Result of verifying expectations after execution."""

    passed: bool = Field(..., description="Whether the expectation was met")
    reason: str = Field(..., description="Explanation of why it passed or failed")
    text_match: Optional[bool] = Field(None, description="Whether text content matched")
    visual_match: Optional[bool] = Field(None, description="Whether visual appearance matched")
    details: Optional[str] = Field(None, description="Additional details about the verification")


class ExecutionRequest(BaseModel):
    """Request body for executing a scenario."""

    scenario_id: str = Field(..., description="ID of the scenario to execute")
    headless: bool = Field(default=True, description="Run browser in headless mode")


class ExecutionResponse(BaseModel):
    """Response after starting an execution."""

    execution_id: str = Field(..., description="ID of the created execution record")
    status: str = Field(..., description="Initial status, typically 'pending'")


class MutationRequest(BaseModel):
    """Request body for creating a mutated scenario."""

    mutation_type: str = Field(
        ..., description="Type of mutation: 'action_mutation', 'input_mutation', or 'step_mutation'"
    )


class MutationResponse(BaseModel):
    """Response after mutation creation."""

    mutation_id: str = Field(..., description="ID of the created mutation record")
    status: str = Field(..., description="Initial status, typically 'created'")


# Valid AgentStatus values matching frontend enum
AGENT_STATUS_VALUES = (
    "pending",
    "planning",
    "executing",
    "verifying",
    "reflecting",
    "completed",
    "failed",
)