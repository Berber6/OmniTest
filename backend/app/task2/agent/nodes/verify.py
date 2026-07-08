"""LangGraph 代理图的验证节点。

实现单策略验证：使用 LLM 读取页面 snapshot 文本判断期望是否达成。

返回 verification_result，包含 passed、reason、text_match、details、verification_type。
"""

from __future__ import annotations

import json
import logging

from app.llm.router import call_llm
from app.llm.prompts.verify_result import (
    VERIFY_TEXT_SYSTEM_PROMPT,
    VERIFY_TEXT_USER_PROMPT_TEMPLATE,
)
from app.task2.agent.state import AgentState

logger = logging.getLogger(__name__)


async def verify_node(state: AgentState) -> dict:
    """LangGraph node: verify execution results against expectations.

    Uses single strategy: LLM text verification on page snapshot HTML.
    """
    scenario = state.get("scenario", {})
    expectations = scenario.get("expectations", [])
    current_page_state = state.get("current_page_state", {})
    executed_steps = state.get("executed_steps", [])

    page_text = current_page_state.get("page_text", "") or current_page_state.get("snapshot", "")
    expectations_text = _format_expectations(expectations)

    enhanced_page_text = page_text
    memory_context = state.get("memory_context", {})
    page_structure = memory_context.get("page_structure", {})
    if isinstance(page_structure, dict):
        visible_elements = page_structure.get("visible_elements", [])
        if visible_elements and enhanced_page_text:
            enhanced_page_text += "\n\n## 页面可见元素列表\n" + "\n".join(visible_elements)

    all_steps_failed = all(not s.get("success", False) for s in executed_steps) if executed_steps else True
    if all_steps_failed:
        logger.info("所有执行步骤失败，直接返回验证失败结果")
        failure_reason = "所有执行步骤失败"
        for step in executed_steps:
            error = step.get("error", "")
            if error:
                failure_reason = error
                break
        return {
            "verification_result": {
                "passed": False,
                "reason": failure_reason,
                "text_match": None,
                "details": "所有步骤失败，无需进一步验证",
                "verification_type": "text",
            },
            "final_result": "fail",
            "failure_reason": failure_reason,
        }

    # 唯一策略：LLM 文本验证
    text_result = await _text_verification(expectations_text, enhanced_page_text)
    verification_result = text_result

    final_result = "pass" if verification_result.get("passed", False) else "fail"
    failure_reason = ""
    if final_result == "fail":
        failure_reason = verification_result.get("reason", "验证失败，无具体原因")

    logger.info("验证完成: result=%s", final_result)

    return {
        "verification_result": verification_result,
        "final_result": final_result,
        "failure_reason": failure_reason,
    }


async def _text_verification(
    expectations_text: str,
    page_text: str,
) -> dict:
    """使用 DeepSeek 进行基于文本的验证。"""
    user_prompt = VERIFY_TEXT_USER_PROMPT_TEMPLATE.format(
        expectations_text=expectations_text,
        page_text=page_text[:3000] if len(page_text) > 3000 else page_text,
        tool_results_text="",
    )

    try:
        response = await call_llm(
            model_key="deepseek_v4_flash",
            prompt=user_prompt,
            system_prompt=VERIFY_TEXT_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
            pipeline_stage="verify_text",
        )
        logger.info("文本验证 LLM 响应 (前500字符): %s", response[:500] if response else "None")
        from app.llm.json_parser import parse_llm_json
        result = parse_llm_json(response)
        if result is None:
            raise json.JSONDecodeError("无法解析", response, 0)
        result["verification_type"] = "text"
        return result
    except json.JSONDecodeError:
        logger.warning("文本验证响应不是有效的 JSON")
        return {
            "passed": False,
            "reason": "文本验证失败：无法解析 LLM 响应",
            "text_match": False,
            "details": "LLM 响应不是有效的 JSON",
            "verification_type": "text",
        }
    except Exception as exc:
        logger.error("文本验证失败: %s", exc)
        return {
            "passed": False,
            "reason": f"文本验证失败: {exc}",
            "text_match": False,
            "details": str(exc),
            "verification_type": "text",
        }


def _format_expectations(expectations: list[dict]) -> str:
    """将预期结果格式化为验证 prompt。"""
    if not expectations:
        return "未定义明确的预期结果 — 检查是否没有发生错误。"
    lines = []
    for idx, exp in enumerate(expectations):
        exp_type = exp.get("type", "unknown")
        desc = exp.get("description", "No description")
        lines.append(f"预期结果 {idx} (类型={exp_type}): {desc}")
    return "\n".join(lines)
