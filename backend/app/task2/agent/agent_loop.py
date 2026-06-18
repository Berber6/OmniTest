"""观察→决策→执行 循环的核心逻辑（纯函数，无 I/O）。

本模块只负责：
1. 构建"决策下一个动作"的 LLM 提示词；
2. 把 Playwright 快照裁剪成适合喂给 LLM 的精简文本；
3. 解析 LLM 返回的单个动作 JSON。

实际的 MCP 调用、浏览器会话、事件推送都在 runner.py 中完成。
这样拆分便于单元测试，也符合"代码能做的事就用代码做"（CLAUDE.md 规则5）。
"""

from __future__ import annotations

import re
from typing import Any

# 循环中允许 LLM 选择的交互/导航工具。
# 注意：browser_snapshot / browser_take_screenshot 由循环自动执行，
# 不需要 LLM 主动选择，因此不在此列表中。
ALLOWED_LOOP_TOOLS = frozenset({
    "browser_click",
    "browser_type",
    "browser_navigate",
    "browser_select_option",
    "browser_hover",
    "browser_press_key",
    "browser_wait_for",
    "browser_drag",
})


DECIDE_SYSTEM_PROMPT = """\
你是一名 Web 测试执行智能体，正在真实浏览器中逐步执行一个测试场景。

## 工作方式（重要）
- 你**每次只决定下一个动作**，而不是一次性输出整个计划。
- 你会看到**当前页面的真实可访问性快照**，其中每个可交互元素都带有 `[ref=eN]` 引用。
- 你选择的元素 `target` **必须**是当前快照中真实出现的 `eN` 引用（例如 e23），不要凭空编造，也不要使用上一页的旧引用。
- 如果当前页面看不到你需要的元素，先用 `browser_wait_for` 等待，或选择能让目标元素出现的中间动作（如展开菜单）。

## 可用工具（args 必须严格符合）
- browser_click: 点击元素。args: {"target": "eN", "element": "中文可读描述"}
- browser_type: 输入文本。args: {"target": "eN", "text": "要输入的文本", "element": "中文描述", "submit": false}
  - 若输入后需要回车提交，设 submit=true。
- browser_navigate: 导航到 URL。args: {"url": "https://..."}
- browser_select_option: 下拉选择。args: {"target": "eN", "values": ["值"], "element": "中文描述"}
- browser_hover: 悬停。args: {"target": "eN", "element": "中文描述"}
- browser_press_key: 按键。args: {"key": "Enter"|"Escape"|"Tab"|...}
- browser_wait_for: 等待。args: {"time": 2} 或 {"text": "要等待出现的文本"}
- browser_drag: 拖拽。args: {"startTarget": "eN", "endTarget": "eN", "startElement": "中文", "endElement": "中文"}

## 你的目标
完成下方"测试场景目标"中描述的所有步骤。当你判断场景目标已经达成
（例如已执行完所有步骤、页面已出现预期结果）时，输出 done=true 结束。

## 输出格式（严格 JSON，单个对象，无 markdown 包装）
{
  "reasoning": "中文说明：当前页面是什么状态、为什么选这个动作、用哪个 eN",
  "tool": "browser_click",
  "args": {"target": "e23", "element": "右上角的+Add Board按钮"},
  "done": false
}

当且仅当场景已完成、不需要再操作时：
{"reasoning": "所有步骤已完成，页面已显示新建的Board", "tool": "", "args": {}, "done": true}

只返回这个 JSON 对象。
"""


DECIDE_USER_TEMPLATE = """\
## 测试场景目标
名称: {scenario_name}

### 需要完成的步骤（这是目标，不是逐条指令——按真实页面灵活完成）
{steps_text}

### 预期结果（完成后页面应满足）
{expectations_text}

{loop_hint_section}{reflection_section}## 已执行的动作历史（最近{history_n}条）
{history_text}

## 当前页面（真实快照，元素带 eN 引用）
{snapshot_text}

---
根据当前页面快照，决定**下一个**动作。target 必须用上面快照里真实存在的 eN 引用。
如果场景目标已达成，返回 done=true。只返回单个 JSON 对象。"""


# 交互元素 role —— 这些是 agent 真正会去操作的元素，截断时必须优先保留。
# 卡片/纯文本行（generic/text）数量大但很少是操作目标，可优先丢弃。
_ACTIONABLE_ROLE_HINTS = (
    "button", "link", "textbox", "combobox", "select", "checkbox",
    "searchbox", "menuitem", "tab", "option", "spinbutton", "switch", "radio",
)


def trim_snapshot(snapshot_text: str, max_elements: int = 200, max_chars: int = 12000) -> str:
    """把 Playwright 快照裁剪成精简文本喂给 LLM。

    保留页面 URL/标题，以及所有带 [ref=eN] 的交互元素行（这是 LLM 选 target 的依据）。
    丢弃无 ref 的纯装饰行，控制 token 用量。

    截断策略（关键）：当元素数超过上限时，**优先保留可操作元素**（button/link/
    textbox 等），再补其他 ref 元素。这样列表底部的"+ Add Card"按钮不会被大量
    卡片文本元素挤出可见范围——这是之前 F4_S1 卡在"找不到 Add Card 按钮"的根因。
    """
    if not snapshot_text:
        return "（无可用快照）"

    header_lines: list[str] = []
    actionable_lines: list[str] = []  # 可操作元素（优先保留）
    other_lines: list[str] = []        # 其他带 ref 的元素（generic/text 等）
    for line in snapshot_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- Page URL:") or stripped.startswith("- Page Title:"):
            header_lines.append(stripped)
            continue
        # 保留带 ref 的元素行（保留原始缩进以传达层级关系）
        if "[ref=e" in line:
            # 判断是否可操作：快照行形如 "- button \"Add card\" [ref=e232]"
            # 取 ref 前的 role 词
            role_part = stripped.lstrip("- ").split(" ", 1)[0].lower()
            if any(role_part == r or role_part.startswith(r) for r in _ACTIONABLE_ROLE_HINTS):
                actionable_lines.append(line.rstrip())
            else:
                other_lines.append(line.rstrip())

    if len(actionable_lines) + len(other_lines) > max_elements:
        # 优先保留全部可操作元素，剩余配额给其他元素
        remaining = max(0, max_elements - len(actionable_lines))
        kept_other = other_lines[:remaining]
        truncated = len(other_lines) - len(kept_other)
        elem_lines = actionable_lines + kept_other
        elem_lines.append(
            f"  …（已截断：保留全部 {len(actionable_lines)} 个可操作元素 + "
            f"{len(kept_other)} 个其他元素，丢弃 {truncated} 个非可操作元素）"
        )
    else:
        elem_lines = actionable_lines + other_lines

    result = "\n".join(header_lines + elem_lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n…（已按长度截断）"
    return result or "（当前快照无可交互元素）"


def format_steps(steps: list[dict]) -> str:
    """把场景步骤格式化为目标描述。"""
    if not steps:
        return "（未定义步骤）"
    lines = []
    for s in steps:
        num = s.get("step", "?")
        action = s.get("action", "")
        target = s.get("target", "")
        if target:
            lines.append(f"{num}. {action}（目标元素：{target}）")
        else:
            lines.append(f"{num}. {action}")
    return "\n".join(lines)


def format_expectations(expectations: list[dict]) -> str:
    """把预期结果格式化为文本。"""
    if not expectations:
        return "（未定义明确预期，只要无错误即可）"
    lines = []
    for e in expectations:
        etype = e.get("type", "page_content")
        desc = e.get("description", "")
        lines.append(f"- [{etype}] {desc}")
    return "\n".join(lines)


def format_history(history: list[dict], last_n: int = 8) -> str:
    """把动作历史格式化为简要文本。"""
    if not history:
        return "（尚未执行任何动作）"
    recent = history[-last_n:]
    lines = []
    for h in recent:
        idx = h.get("step_number", "?")
        tool = h.get("tool", "?")
        desc = h.get("reasoning", "") or h.get("description", "")
        ok = "成功" if h.get("success") else f"失败({h.get('error', '')[:60]})"
        lines.append(f"#{idx} {tool} — {desc[:80]} [{ok}]")
    return "\n".join(lines)


def build_decide_prompt(
    scenario: dict,
    history: list[dict],
    snapshot_text: str,
    reflection: str = "",
    loop_hint: str = "",
) -> str:
    """构建"决策下一个动作"的 user prompt。

    Args:
        loop_hint: 非空时注入"重复动作警告"，提示 LLM 改变策略，
            避免在同一个动作上反复消耗步数。
    """
    reflection_section = ""
    if reflection:
        reflection_section = (
            f"## 上一轮失败的反思（请据此调整策略）\n{reflection}\n\n"
        )
    loop_hint_section = ""
    if loop_hint:
        loop_hint_section = f"## ⚠️ 重复动作警告\n{loop_hint}\n\n"
    return DECIDE_USER_TEMPLATE.format(
        scenario_name=scenario.get("name", "未命名场景"),
        steps_text=format_steps(scenario.get("steps", [])),
        expectations_text=format_expectations(scenario.get("expectations", [])),
        loop_hint_section=loop_hint_section,
        reflection_section=reflection_section,
        history_n=8,
        history_text=format_history(history),
        snapshot_text=trim_snapshot(snapshot_text),
    )


def detect_loop(history: list[dict]) -> str:
    """检测动作历史中是否出现重复，返回给 LLM 的警告文本（无重复返回空串）。

    重复判定（两个信号取其一，最近 5 步内 ≥2 次）：
    1. 同一个 (tool, target ref) —— ref 稳定时最强信号（如反复点 e171）。
    2. 同一个 (tool, element 描述) —— ref 漂移时用描述兜底。

    ref 在页面变化后会漂移，所以两者都看：ref 命中说明在同一个元素上空转，
    描述命中说明在语义同一个控件上空转。任一命中即注入反循环提示。
    """
    recent = history[-5:]
    if len(recent) < 2:
        return ""
    seen_ref: dict[tuple[str, str], int] = {}
    seen_desc: dict[tuple[str, str], int] = {}
    for h in recent:
        tool = h.get("tool", "") or ""
        args = h.get("args") if isinstance(h.get("args"), dict) else {}
        element = str(args.get("element", "") or "").strip()
        target = str(args.get("target", "") or args.get("ref", "") or "").strip()
        if not tool:
            continue
        if target:
            seen_ref[(tool, target)] = seen_ref.get((tool, target), 0) + 1
        if element:
            seen_desc[(tool, element)] = seen_desc.get((tool, element), 0) + 1

    repeated_ref = [(k, n) for k, n in seen_ref.items() if n >= 2]
    repeated_desc = [(k, n) for k, n in seen_desc.items() if n >= 2]
    if not repeated_ref and not repeated_desc:
        return ""

    parts = [f"{tool}({sig})×{n}" for (tool, sig), n in repeated_ref]
    parts += [f"{tool}({sig})×{n}" for (tool, sig), n in repeated_desc]
    return (
        f"你最近对以下元素重复执行了相同动作：{'、'.join(parts)}。"
        "这说明当前做法没有推进目标。请改变策略：例如换一个元素、"
        "先选择列表中某个具体选项（而不是反复打开下拉框）、或检查页面是否"
        "已有错误提示。不要再次重复相同动作。"
    )


def parse_decision(response_text: str) -> dict | None:
    """解析 LLM 的单动作决策 JSON。

    返回规范化后的 {tool, args, reasoning, done}；无法解析返回 None。
    """
    from app.llm.json_parser import parse_llm_json

    data = parse_llm_json(response_text)
    if not isinstance(data, dict):
        return None

    tool = (data.get("tool") or "").strip()
    args = data.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    reasoning = data.get("reasoning", "") or ""
    done = bool(data.get("done", False))

    # done=true 时允许 tool 为空
    if done and not tool:
        return {"tool": "", "args": {}, "reasoning": reasoning, "done": True}

    # 兼容历史字段名：ref -> target
    if "ref" in args and "target" not in args:
        args["target"] = args.pop("ref")

    if tool not in ALLOWED_LOOP_TOOLS:
        # 工具不在白名单内：若像是"完成"信号，按 done 处理，否则视为无效
        return None

    return {"tool": tool, "args": args, "reasoning": reasoning, "done": done}


def is_valid_ref(value: str) -> bool:
    """判断字符串是否为有效的 eN 引用格式。"""
    return bool(value) and bool(re.match(r"^e\d+$", value.strip()))
