"""LangGraph 代理图的规划节点。

使用 GLM-5.1（推理模型）将测试场景步骤翻译为 MCP 工具调用序列。
引用 Memory MCP 中存储的页面结构信息以获取更准确的选择器。
"""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.llm.router import call_llm
from app.llm.prompts.plan_actions import (
    PLAN_ACTIONS_SYSTEM_PROMPT,
    PLAN_ACTIONS_USER_PROMPT_TEMPLATE,
)
from app.task1.ui_registry import UIElementRegistry
from app.task2.agent.state import AgentState

logger = logging.getLogger(__name__)


async def plan_node(state: AgentState) -> dict:
    """LangGraph node: translate scenario steps into an execution plan.

    Reads scenario from state, retrieves Memory MCP context if available,
    calls GLM-5.1 to generate an ordered list of MCP tool call Actions,
    and returns the plan as a state update.

    Args:
        state: Current AgentState with scenario and optionally
               current_page_state from Memory MCP.

    Returns:
        Partial state update dict with the "plan" field populated.
    """
    scenario = state.get("scenario", {})

    scenario_name = scenario.get("name", "未命名场景")
    scenario_id = scenario.get("id", "")

    steps = scenario.get("steps", [])
    expectations = scenario.get("expectations", [])

    # 格式化步骤用于 prompt
    steps_text = _format_steps(steps)

    # 格式化预期结果
    expectations_text = _format_expectations(expectations)

    # 检索之前存储的页面上下文
    page_context = state.get("current_page_state", {})
    page_context_text = json.dumps(page_context, indent=2) if page_context else "没有可用的先前页面上下文。"

    # Retrieve Memory MCP stored context from previous execution (if available)
    memory_context = state.get("memory_context", {})
    memory_context_text = ""
    if memory_context:
        # Use Memory MCP context to inform planning
        page_structure = memory_context.get("page_structure", {})
        if page_structure:
            visible_elements = page_structure.get("visible_elements", [])
            if visible_elements:
                memory_context_text = "\n## 页面可见元素（来自 Memory MCP）\n" + "\n".join(visible_elements)
        execution_context = memory_context.get("execution_context", {})
        if execution_context:
            memory_context_text += f"\n## 上次执行上下文（来自 Memory MCP）\n成功步骤: {execution_context.get('successful_steps', 0)}, 失败步骤: {execution_context.get('failed_steps', 0)}"

    # Append Memory MCP context to page context
    full_context = page_context_text + memory_context_text

    # 构建 prompt — 注入凭据到系统提示（用 replace 避免 .format() 与 JSON {} 冲突）
    system_prompt = PLAN_ACTIONS_SYSTEM_PROMPT.replace(
        "{login_email}", settings.login_email,
    ).replace(
        "{login_password}", settings.login_password,
    )
    user_prompt = PLAN_ACTIONS_USER_PROMPT_TEMPLATE.format(
        scenario_name=scenario_name,
        steps_text=steps_text,
        expectations_text=expectations_text,
        page_context_text=full_context,
        ui_elements=_load_ui_elements_text(),
    )

    logger.info("正在规划场景 '%s' (id=%s)，共 %d 个步骤", scenario_name, scenario_id, len(steps))

    try:
        # 使用 GLM-5.1 处理需要推理的规划任务
        response_text = await call_llm(
            model_key="glm_5_1",
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,  # 低温度以保证确定性规划
            max_tokens=4096,
            response_format={"type": "json_object"},
            pipeline_stage="plan",
        )

        plan = _parse_plan_response(response_text)

        if not plan:
            logger.warning("场景 '%s' 的规划返回了空计划", scenario_name)
            plan = _generate_fallback_plan(scenario)

        # 检查计划是否包含正确的登录流程
        # 如果第一个导航步骤不是 4gaboards URL，则用备用计划替换
        plan = _ensure_login_prefix(plan, scenario)

        # 将 action 字典标准化为前端期望的字段名
        plan = [_normalize_action(a) for a in plan]

        logger.info("规划完成：为场景 '%s' 生成了 %d 个操作", scenario_name, len(plan))

    except Exception as exc:
        logger.error("场景 '%s' 的规划失败: %s", scenario_name, exc)
        # 从原始步骤生成一个最小的备用计划
        plan = _generate_fallback_plan(scenario)

    # 确保所有操作使用标准化字段名
    plan = [_normalize_action(a) for a in plan]

    return {"plan": plan}


def _ensure_login_prefix(plan: list[dict], scenario: dict) -> list[dict]:
    """确保计划包含正确的登录流程前缀和凭据。

    如果 LLM 生成的计划不包含对 4gaboards 的导航和登录，
    则用备用计划替换。同时验证并修正登录凭据。
    """
    # 检查计划中是否有导航到 4gaboards 的步骤
    has_4gaboards_nav = False
    has_login_action = False
    for action in plan:
        tool = action.get("tool") or action.get("tool_name", "")
        args = action.get("args") or action.get("parameters", {})
        desc = action.get("description", "")

        if tool == "browser_navigate":
            url = args.get("url", "")
            if "4gaboards" in url.lower():
                has_4gaboards_nav = True

        if tool == "browser_type" or tool == "browser_click":
            target = args.get("target", args.get("ref", ""))
            # 检查是否包含登录操作
            if ("login" in desc.lower() or "登录" in desc or "log in" in desc.lower()
                or "email" in str(target).lower() or "邮箱" in str(target)
                or "password" in str(target).lower() or "密码" in str(target)):
                has_login_action = True

        # 验证并修正登录凭据
        if tool == "browser_type":
            target = args.get("target", args.get("ref", ""))
            text = args.get("text", "")
            if "邮箱" in str(target) or "email" in str(target).lower() or "用户名" in str(target):
                if text != settings.login_email:
                    logger.warning("LLM 计划使用错误邮箱 '%s'，修正为 '%s'", text, settings.login_email)
                    args["text"] = settings.login_email
            if "密码" in str(target) or "password" in str(target).lower():
                if text != settings.login_password:
                    logger.warning("LLM 计划使用错误密码 '%s'，修正为正确密码", text)
                    args["text"] = settings.login_password

    # 如果计划没有导航到 4gaboards 或没有登录操作，使用备用计划
    if not has_4gaboards_nav or not has_login_action:
        logger.warning(
            "LLM 计划缺少 4gaboards 导航或登录步骤 (has_nav=%s, has_login=%s)，使用备用计划",
            has_4gaboards_nav, has_login_action,
        )
        return _generate_fallback_plan(scenario)

    return plan


def _normalize_action(action: dict) -> dict:
    """将 action 字典标准化为前端期望的字段名。

    转换：tool_name -> tool, parameters -> args, 移除 server 字段。
    如果新字段为空或缺失，则回退到旧字段名。
    同时将旧参数名 "ref" 映射到 Playwright MCP 的 "target"。
    """
    tool = action.get("tool") or action.get("tool_name", "")
    args = action.get("args") or action.get("parameters", {})
    description = action.get("description", "")

    # 将旧的 "ref" 参数名映射为 Playwright MCP 的 "target"
    # 这确保向后兼容：如果 LLM 仍偶尔输出 "ref"，系统会自动纠正
    if "ref" in args and "target" not in args:
        args["target"] = args.pop("ref")

    normalized = {
        "tool": tool,
        "args": args,
        "description": description,
    }
    return normalized


def _refine_target(target: str) -> str:
    """将泛化的场景 target 描述转换为更具体的快照匹配描述。

    场景 target 如"仪表盘或侧边栏中的Board链接"太泛化，
    快照解析器容易匹配到品牌 logo 而非实际看板链接。
    用更具体的中文描述替代，帮助解析器优先匹配功能链接而非品牌元素。
    """
    if not target:
        return target

    # Board/看板链接：用"看板项目链接"替代泛化描述，避免匹配品牌 logo
    if ("Board" in target and "链接" in target) or ("看板" in target and "链接" in target):
        return "看板项目链接"

    return target


def _load_ui_elements_text() -> str:
    """Load UI element registry and format for planner prompt."""
    registry_path = str(settings.data_dir / "crawled_docs" / "ui_registry.json")
    try:
        UIElementRegistry.load(registry_path)
        elements = UIElementRegistry.get_all_elements()
        if elements:
            return UIElementRegistry.format_for_prompt(elements)
    except Exception:
        pass
    return "无可用的已知 UI 元素信息。"


def _format_steps(steps: list[dict]) -> str:
    """将场景步骤格式化为可读文本用于 prompt。"""
    if not steps:
        return "未定义步骤。"
    lines = []
    for step in steps:
        step_num = step.get("step", "?")
        action = step.get("action", "无操作")
        target = step.get("target", "无目标")
        lines.append(f"步骤 {step_num}: 操作='{action}', 目标='{target}'")
    return "\n".join(lines)


def _format_expectations(expectations: list[dict]) -> str:
    """将场景预期结果格式化为可读文本。"""
    if not expectations:
        return "未定义明确的预期结果。"
    lines = []
    for exp in expectations:
        exp_type = exp.get("type", "unknown")
        desc = exp.get("description", "无描述")
        lines.append(f"预期结果 (类型={exp_type}): {desc}")
    return "\n".join(lines)


def _parse_plan_response(response_text: str) -> list[dict]:
    """将 LLM 响应解析为 Action 字典列表。

    处理原始 JSON 数组和包含计划的 JSON 对象。
    """
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # 尝试从 markdown 代码块中提取 JSON
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            logger.warning("无法将规划响应解析为 JSON: %s", response_text[:300])
            return []

    # LLM 可能直接返回数组或包装在对象中
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 查找常见的包装键
        for key in ("plan", "actions", "steps", "result"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # 如果字典本身看起来像一个单独的操作，则包装它
        if "tool" in data or "tool_name" in data:
            return [data]

    logger.warning("意外的规划响应结构: %s", type(data).__name__)
    return []


def _generate_fallback_plan(scenario: dict) -> list[dict]:
    """从场景步骤生成最小的备用计划。

    当 LLM 规划调用失败时使用。创建基本的导航 + 登录 + 交互计划。
    使用描述性 target（如"邮箱输入框"）而非硬编码 eN 引用，
    执行引擎会自动从快照中解析真实的 target。
    """
    steps = scenario.get("steps", [])
    url = scenario.get("url", "https://demo.4gaboards.com")

    plan = []

    # 1. 导航到应用首页
    plan.append({
        "tool": "browser_navigate",
        "args": {"url": url},
        "description": f"导航到 {url}",
    })

    # 2. 获取首页快照
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "获取首页快照查找登录入口",
    })

    # 3. 导航到登录页面
    plan.append({
        "tool": "browser_navigate",
        "args": {"url": settings.login_url},
        "description": "导航到登录页面",
    })

    # 4. 获取登录页面快照（解析元素引用）
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "获取登录页面快照以获取输入字段的引用",
    })

    # 5. 输入邮箱（使用描述性 target，执行引擎自动解析）
    plan.append({
        "tool": "browser_type",
        "args": {"target": "邮箱输入框", "text": settings.login_email},
        "description": f"输入登录邮箱 {settings.login_email}",
    })

    # 6. 输入密码
    plan.append({
        "tool": "browser_type",
        "args": {"target": "密码输入框", "text": settings.login_password},
        "description": "输入登录密码",
    })

    # 7. 点击登录按钮
    plan.append({
        "tool": "browser_click",
        "args": {"target": "登录按钮"},
        "description": "点击登录按钮提交登录表单",
    })

    # 8. 等待登录完成
    plan.append({
        "tool": "browser_wait_for",
        "args": {"time": 5},
        "description": "等待5秒确保登录完成和页面渲染",
    })

    # 9. 确认登录成功
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "确认登录成功后的页面状态（URL不再是/login）",
    })

    # 10. 获取仪表盘快照以查找 Board 链接
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "获取仪表盘或侧边栏快照查找Board链接",
    })

    # 11. 点击侧边栏看板列表按钮（可能是"Show boards"或"Hide boards"）
    # 执行引擎会从快照中自动匹配正确的按钮
    plan.append({
        "tool": "browser_click",
        "args": {"target": "展开看板按钮"},
        "description": "点击侧边栏中展开看板列表的按钮（Show boards 或 Hide boards）",
    })

    # 12. 等待列表展开/加载
    plan.append({
        "tool": "browser_wait_for",
        "args": {"time": 2},
        "description": "等待看板列表展开或加载",
    })

    # 13. 获取展开后的快照查找具体的 Board 链接
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "获取看板列表展开后的快照以查找具体的Board链接",
    })

    # 14. 对每个步骤生成交互操作
    for step in steps:
        action = step.get("action", "")
        target = step.get("target", "")
        step_num = step.get("step", "?")

        # 如果 target 太泛化（如"仪表盘或侧边栏中的Board链接"),
        # 用更具体的描述替代，帮助快照解析器找到正确的元素
        specific_target = _refine_target(target)

        if "click" in action.lower() or "press" in action.lower() or "点击" in action:
            plan.append({
                "tool": "browser_click",
                "args": {"target": specific_target},
                "description": f"步骤 {step_num}: {action} — {target}",
            })
            # 点击导航性链接后，等待页面加载并获取快照确认
            plan.append({
                "tool": "browser_wait_for",
                "args": {"time": 3},
                "description": f"步骤 {step_num}: 等待页面加载",
            })
            plan.append({
                "tool": "browser_snapshot",
                "args": {},
                "description": f"步骤 {step_num}: 确认页面已导航到目标位置",
            })
        elif "input" in action.lower() or "type" in action.lower() or "输入" in action or "填写" in action:
            import re
            text_match = re.search(r"['\"](.+?)['\"]", action)
            text_to_type = text_match.group(1) if text_match else "test_input"
            plan.append({
                "tool": "browser_type",
                "args": {"target": specific_target, "text": text_to_type},
                "description": f"步骤 {step_num}: {action} — {target}",
            })
        elif "navigate" in action.lower() or "导航" in action or "打开" in action or "前往" in action:
            url_match = re.search(r"https?://[^\s'\"]+", action)
            nav_url = url_match.group(0) if url_match else url
            plan.append({
                "tool": "browser_navigate",
                "args": {"url": nav_url},
                "description": f"步骤 {step_num}: {action}",
            })
        else:
            # 默认：先获取快照，再尝试点击
            plan.append({
                "tool": "browser_snapshot",
                "args": {},
                "description": f"步骤 {step_num}: {action} 之前获取快照",
            })
            plan.append({
                "tool": "browser_click",
                "args": {"target": specific_target},
                "description": f"步骤 {step_num}: {action} — {target}",
            })

    # 12. 最终验证捕获
    plan.append({
        "tool": "browser_take_screenshot",
        "args": {},
        "description": "截取屏幕截图用于验证",
    })
    plan.append({
        "tool": "browser_snapshot",
        "args": {},
        "description": "获取页面快照用于验证",
    })

    return plan