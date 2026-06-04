"""LangGraph 代理图的反思节点。

当验证失败时分析失败原因。使用 GLM-5.1 分析执行轨迹、截图和验证结果，
然后生成修订后的执行计划。跟踪 retry_count（最大3次）。
当超过最大重试次数时返回详细的失败原因。
"""

from __future__ import annotations

import json
import logging

from app.llm.router import call_llm
from app.task2.agent.state import AgentState

logger = logging.getLogger(__name__)

REFLECT_SYSTEM_PROMPT = """\
你是一名Web测试反思代理。当测试执行验证失败时，你分析执行轨迹、截图和验证结果，
确定失败的根因并生成修订后的执行计划。

## 重要：中文输出要求

所有文本内容必须使用中文输出：
- 反思分析（reflection）必须使用中文，详细分析出了什么问题以及为什么
- 根因分析（root_cause）必须使用中文，说明失败的主要原因
- 修订计划中的操作描述（description）必须使用中文

## 分析过程

1. **审查执行轨迹**：查看每个执行的步骤，识别哪里出了问题。是某个操作失败了？
   是选择器没有匹配？还是元素不可见？

2. **审查验证结果**：准确了解哪些预期结果失败以及为什么。verification_result 告诉你期望的是什么与实际发现了什么。

3. **审查截图**：如果可用，截图显示执行过程中关键时刻的实际页面状态。

4. **诊断根因**：常见的失败原因包括：
   - 选择器错误（元素未找到或点击了不同的元素）
   - 时序问题（元素尚未加载，需要等待）
   - 参数值错误（错误的URL、错误的输入文本）
   - 缺少前置步骤（需要先导航/登录）
   - UI 变化（页面结构与预期不同）

5. **生成修订计划**：根据诊断结果，创建修正后的执行计划来解决已识别的问题。修订计划应该：
   - 修正错误的选择器（使用快照数据找到正确的选择器）
   - 添加必要的等待或前置步骤
   - 根据实际发生的情况调整参数
   - 如果原始方法明显不行，尝试替代方案

## 输出格式

返回一个 JSON 对象，结构如下：
{
  "reflection": "中文详细分析出了什么问题以及为什么",
  "root_cause": "中文说明失败的主要原因",
  "revised_plan": [
    {
      "tool": "字符串",
      "args": {},
      "description": "中文描述该操作的作用"
    }
  ],
  "should_retry": true | false  // 如果失败是根本性的且重试无法解决，则设为 false
}

如果失败是由根本性问题引起的（例如应用本身有问题、场景不可能执行），
将 should_retry 设为 false 并在 reflection 中用中文解释原因。
"""


REFLECT_USER_PROMPT_TEMPLATE = """\
## 重试信息
当前重试次数: {retry_count}（最大允许: 3）

## 测试场景
名称: {scenario_name}
步骤: {steps_summary}

## 执行轨迹
{execution_trace}

## 验证结果
{verification_result}

## 失败时的页面状态
{page_state_text}

---

分析失败原因，诊断根因，并生成修订后的执行计划。如果重试次数已达到上限（3），则将 should_retry 设为 false。仅返回 JSON 反思结果。
"""


async def reflect_node(state: AgentState) -> dict:
    """LangGraph 节点：反思失败原因并生成修订计划。

    分析执行轨迹和验证结果以确定测试失败原因，
    然后使用 GLM-5.1 生成修订后的执行计划。增加 retry_count，
    当超过最大重试次数（3）时返回新计划用于重新执行，
    或设置 final_result 为 "fail" 并提供详细的失败原因。

    Args:
        state: 当前 AgentState，包含 executed_steps、verification_result、
               retry_count 等。

    Returns:
        部分状态更新字典，包含增加的 retry_count、reflection，
        以及修订计划或最终失败原因。
    """
    scenario = state.get("scenario", {})
    executed_steps = state.get("executed_steps", [])
    verification_result = state.get("verification_result", {})
    current_page_state = state.get("current_page_state", {})
    retry_count = state.get("retry_count", 0)
    screenshots = state.get("screenshots", [])

    # 增加重试计数器
    new_retry_count = retry_count + 1

    # 快速路径：如果所有步骤都失败了，不调用LLM直接结束
    all_steps_failed = all(not s.get("success", False) for s in executed_steps) if executed_steps else True
    if all_steps_failed:
        logger.warning("所有执行步骤失败 — 直接结束不再重试")
        failure_reason = state.get("failure_reason", "") or "所有执行步骤失败"
        # 从步骤中提取具体原因
        for step in executed_steps:
            error = step.get("error", "")
            if error:
                failure_reason = error
                break
        return {
            "retry_count": new_retry_count,
            "reflection": f"所有步骤失败: {failure_reason}",
            "final_result": "fail",
            "failure_reason": failure_reason,
            "plan": [],
        }

    # 如果所有步骤都因MCP不可用而失败，直接结束不再重试
    all_steps_failed = all(not s.get("success", False) for s in executed_steps) if executed_steps else False
    mcp_unavailable = any(
        "MCP" in (s.get("error", "") if isinstance(s.get("error", ""), str) else "") or
        "服务器不可用" in (s.get("error", "") if isinstance(s.get("error", ""), str) else "") or
        "连接超时" in (s.get("error", "") if isinstance(s.get("error", ""), str) else "")
        for s in executed_steps
    ) if executed_steps else False

    if all_steps_failed and mcp_unavailable:
        logger.warning("所有步骤因MCP不可用而失败 — 不再重试")
        failure_reason = state.get("failure_reason", "") or "MCP服务器不可用，所有操作无法执行"
        return {
            "retry_count": new_retry_count,
            "reflection": f"所有步骤因MCP服务器不可用而失败，重试无法解决问题。根因: {failure_reason}",
            "final_result": "fail",
            "failure_reason": failure_reason,
            "plan": [],
        }

    # 如果超过最大重试次数，标记为最终失败
    if new_retry_count > 3:
        logger.warning("超过最大重试次数 (retry_count=%d) — 标记为最终失败", new_retry_count)
        failure_reason = verification_result.get("reason", "超过最大重试次数后验证仍失败")
        failed_expectations = verification_result.get("failed_expectations", [])
        if failed_expectations:
            failure_details = "; ".join(
                f"{fe.get('expectation', '?')}: expected {fe.get('expected', '?')}, got {fe.get('actual', '?')}"
                for fe in failed_expectations
            )
            failure_reason = f"{failure_reason}. Details: {failure_details}"

        return {
            "retry_count": new_retry_count,
            "reflection": f"超过最大重试次数。根因: {failure_reason}",
            "final_result": "fail",
            "failure_reason": failure_reason,
            "plan": [],  # 不再重新执行
        }

    # 格式化反思 prompt 的上下文
    scenario_name = scenario.get("name", "Unknown")
    steps_summary = _format_steps_summary(scenario.get("steps", []))
    execution_trace = _format_execution_trace(executed_steps)
    verification_result_text = json.dumps(verification_result, indent=2)
    page_state_text = json.dumps(current_page_state, indent=2)[:3000]  # Limit size

    user_prompt = REFLECT_USER_PROMPT_TEMPLATE.format(
        retry_count=new_retry_count,
        scenario_name=scenario_name,
        steps_summary=steps_summary,
        execution_trace=execution_trace,
        verification_result=verification_result_text,
        page_state_text=page_state_text,
    )

    logger.info("正在反思失败 (retry_count=%d)，场景 '%s'", new_retry_count, scenario_name)

    try:
        response = await call_llm(
            model_key="glm_5_1",
            prompt=user_prompt,
            system_prompt=REFLECT_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=4096,
            response_format={"type": "json_object"},
            pipeline_stage="reflect",
        )

        reflection_data = _parse_reflection_response(response)

    except Exception as exc:
        logger.error("反思 LLM 调用失败: %s", exc)
        reflection_data = {
            "reflection": f"反思分析失败: {exc}",
            "root_cause": "LLM 反思调用本身失败",
            "revised_plan": [],
            "should_retry": new_retry_count < 3,
        }

    reflection_text = reflection_data.get("reflection", "")
    should_retry = reflection_data.get("should_retry", True)
    revised_plan = reflection_data.get("revised_plan", [])
    root_cause = reflection_data.get("root_cause", "")

    # 验证修订计划中的 URL：确保导航步骤使用真实 URL 而非中文占位符
    revised_plan = _validate_plan_urls(revised_plan, scenario)

    logger.info(
        "反思完成: root_cause='%s', should_retry=%s, 修订计划有 %d 个操作",
        root_cause, should_retry, len(revised_plan),
    )

    if not should_retry:
        # 反思判断重试不会有帮助
        failure_reason = root_cause or verification_result.get("reason", "场景无法执行")
        return {
            "retry_count": new_retry_count,
            "reflection": reflection_text,
            "final_result": "fail",
            "failure_reason": failure_reason,
            "plan": [],
        }

    return {
        "retry_count": new_retry_count,
        "reflection": reflection_text,
        "plan": revised_plan,
        # 为新的计划执行重置执行状态
        "executed_steps": [],
        "screenshots": [],
        "current_page_state": {},
        "verification_result": {},
        # Clear final_result so graph conditional edge routes to execute, not end_fail
        "final_result": "",
        "failure_reason": "",
    }


def _parse_reflection_response(response: str) -> dict:
    """将反思 LLM 响应解析为结构化字典。"""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("无法将反思响应解析为 JSON")
        return {
            "reflection": response[:500],
            "root_cause": "无法解析反思响应",
            "revised_plan": [],
            "should_retry": False,
        }


def _format_steps_summary(steps: list[dict]) -> str:
    """将场景步骤格式化为简要摘要。"""
    if not steps:
        return "无步骤"
    return "\n".join(
        f"Step {s.get('step', '?')}: {s.get('action', '?')} → {s.get('target', '?')}"
        for s in steps
    )


def _format_execution_trace(executed_steps: list[dict]) -> str:
    """将已执行步骤格式化为详细轨迹用于分析，包含定位方法信息。"""
    if not executed_steps:
        return "没有步骤被执行。"

    lines = []
    for step in executed_steps:
        step_num = step.get("step_number", "?")
        action = step.get("action", {})
        tool = action.get("tool", "?") if isinstance(action, dict) else "?"
        desc = action.get("description", "") if isinstance(action, dict) else ""
        success = step.get("success", False)
        error = step.get("error", "")
        resolution_method = step.get("resolution_method", "")

        # Include resolution method for richer analysis
        method_info = ""
        if resolution_method:
            method_labels = {
                "en_ref": "eN快照引用",
                "css_selector": "CSS选择器",
                "html_rule": "HTML规则匹配",
                "vlm_coordinate": "VLM视觉定位",
                "keyboard": "键盘兜底",
                "action_fallback": "操作级回退",
                "failed": "定位失败",
            }
            method_info = f" (定位方法: {method_labels.get(resolution_method, resolution_method)})"

        status = "OK" if success else f"FAILED: {error}"
        lines.append(
            f"Step {step_num}: {tool} — {desc}{method_info} [{status}]"
        )

    return "\n".join(lines)


# 真实 URL 前缀列表，用于检测占位符 URL
_REAL_URL_PREFIXES = ("http://", "https://", "about:", "chrome:")


def _validate_plan_urls(plan: list[dict], scenario: dict) -> list[dict]:
    """验证修订计划中的 URL 和凭据，确保导航步骤使用真实 URL 而非中文占位符文本，
    并且登录凭据使用正确的值。

    如果发现 browser_navigate 步骤使用了非真实 URL，则用正确的 URL 替换。
    如果发现登录凭据不是正确的值，则修正。
    如果整个计划没有登录流程，返回备用计划。
    """
    if not plan:
        return plan

    from app.config import settings

    for action in plan:
        tool = action.get("tool") or action.get("tool_name", "")
        args = action.get("args") or action.get("parameters", {})

        if tool == "browser_navigate":
            url = args.get("url", "")
            # 检查 URL 是否是真实地址
            if not url.startswith(_REAL_URL_PREFIXES):
                logger.warning("反思计划包含占位符 URL '%s'，替换为 4gaboards URL", url)
                args["url"] = settings.login_url

        # 检查登录凭据是否正确
        if tool == "browser_type":
            target = args.get("target", args.get("ref", ""))
            text = args.get("text", "")
            # 邮箱输入框 — 修正凭据
            if "邮箱" in str(target) or "email" in str(target).lower() or "用户名" in str(target):
                if text != settings.login_email:
                    logger.warning("反思计划使用错误邮箱 '%s'，修正为 '%s'", text, settings.login_email)
                    args["text"] = settings.login_email
            # 密码输入框 — 修正凭据
            if "密码" in str(target) or "password" in str(target).lower():
                if text != settings.login_password:
                    logger.warning("反思计划使用错误密码 '%s'，修正为正确密码", text)
                    args["text"] = settings.login_password

    # 检查计划是否包含登录流程
    has_login = False
    has_4gaboards = False
    for action in plan:
        tool = action.get("tool") or action.get("tool_name", "")
        args = action.get("args") or action.get("parameters", {})
        desc = action.get("description", "")

        if tool == "browser_navigate" and "4gaboards" in str(args.get("url", "")):
            has_4gaboards = True
        if tool in ("browser_type", "browser_click") and ("登录" in desc or "login" in desc.lower()):
            has_login = True

    # 如果计划没有导航到 4gaboards 且没有登录步骤，使用备用计划
    if not has_4gaboards and not has_login:
        logger.warning("反思计划缺少 4gaboards 导航和登录步骤，使用备用计划")
        from app.task2.agent.nodes.plan import _generate_fallback_plan
        return _generate_fallback_plan(scenario)

    return plan