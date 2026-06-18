"""Execution node for the LangGraph agent graph.

Calls the MCP Client to execute the planned actions via Playwright MCP.
Uses multiprocessing to isolate MCP connections from LangGraph's anyio,
preventing cancel scope conflicts between MCP SDK's anyio and
LangGraph's internal anyio usage.

The MCP execution runs in a child process with its own event loop,
returning results via a multiprocessing pipe.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import multiprocessing
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.task2.agent.state import AgentState
from app.events import broadcaster

logger = logging.getLogger(__name__)


def _classify_error(error_str: str) -> str:
    """根据错误消息的关键词匹配，分类错误类型。

    返回 ErrorCategory 值字符串（与 app.task2.models.ErrorCategory 对应）。
    """
    if not error_str:
        return "unknown"

    error_lower = error_str.lower()

    # 元素未找到类错误
    if any(kw in error_lower for kw in [
        "无法从快照中解析目标元素",
        "所有回退方法均失败",
        "无法解析目标元素",
        "element not found",
        "selector",
        "no element",
        "定位失败",
        "resolution_method=failed",
    ]):
        return "element_not_found"

    # MCP 不可用类错误
    if any(kw in error_lower for kw in [
        "mcp connection",
        "mcp连接",
        "服务器不可用",
        "连接超时",
        "mcp不可用",
        "degraded",
        "降级模式",
        "浏览器不可用",
        "browser not available",
    ]):
        return "mcp_unavailable"

    # 超时类错误
    if any(kw in error_lower for kw in [
        "timeout",
        "超时",
        "timed out",
    ]):
        return "timeout"

    # 导航失败类错误
    if any(kw in error_lower for kw in [
        "browser_navigate",
        "navigate",
        "navigation",
        "导航失败",
        "page load",
    ]):
        return "navigation_failed"

    # JS 执行失败类错误
    if any(kw in error_lower for kw in [
        "browser_evaluate",
        "js",
        "javascript",
        "evaluate",
        "script error",
        "js执行",
    ]):
        return "js_execution_failed"

    # 验证失败类错误
    if any(kw in error_lower for kw in [
        "verification",
        "验证失败",
        "verify",
    ]):
        return "verification_failed"

    return "unknown"


# 需要动态解析 target 参数的交互工具集合
# 这些工具的 args 中可能包含空值或描述性占位符（如"邮箱输入框"),
# 执行引擎会先调用 browser_snapshot 然后从快照中解析真实的 eN 引用
INTERACTIVE_TOOL_NAMES = frozenset({
    "browser_click", "browser_type", "browser_hover",
    "browser_select_option", "browser_fill_form",
})


def _summarize_snapshot(snapshot: str) -> str:
    """Extract a brief summary from the accessibility snapshot YAML."""
    if not snapshot:
        return "无可用快照"
    lines = snapshot.split("\n")
    # Extract key info: URL, title, top-level elements
    summary_lines = []
    for line in lines[:50]:  # First 50 lines give a good overview
        if line.strip() and not line.startswith("```"):
            summary_lines.append(line.strip())
    return "\n".join(summary_lines[:20])  # Keep it concise


def _extract_visible_elements(snapshot: str) -> list[str]:
    """Extract visible element descriptions from accessibility snapshot."""
    if not snapshot:
        return []
    elements = []
    for line in snapshot.split("\n"):
        # Snapshot elements have format like: "- button \"Login\" [ref=e5]"
        # or: "- textbox \"Email\" [ref=e3]"
        if line.strip().startswith("- ") and "[ref=" in line:
            # Extract the element type and name
            match = re.match(r'-\s+(\w+)\s+"([^"]+)"\s+\[ref=(\w+)\]', line.strip())
            if match:
                elem_type, elem_name, elem_ref = match.groups()
                elements.append(f"{elem_type}: {elem_name} (ref={elem_ref})")
    return elements[:30]  # Limit to 30 most relevant elements


def _write_result(path: str, data: dict) -> None:
    """Write result data to a temp file as JSON. Used by child process
    to send results back — avoids multiprocessing.Pipe buffer deadlock
    when screenshot data (base64 images) exceeds the pipe's capacity."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_result(path: str) -> dict | None:
    """Read result data from temp file. Returns None if file doesn't
    exist or is empty. If JSON is truncated (child process crashed mid-write),
    attempts to recover partial executed_steps by finding the last complete step."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content:
            return None
        return json.loads(content)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        # JSON was truncated — child may have crashed mid-write.
        # Try to recover partial executed_steps by finding the last complete step.
        logger.warning("Result file has truncated JSON, attempting partial recovery")
        try:
            # Find the last complete step object in executed_steps array
            # Pattern: look for }, in the steps array
            steps_match = re.search(r'"executed_steps"\s*:\s*\[', content)
            if steps_match:
                # Try progressively shorter truncations
                steps_start = content.index("[", steps_match.start())
                for end_pos in range(len(content), steps_start, -1):
                    snippet = content[steps_start:end_pos]
                    # Try to close the array and object
                    for suffix in ["]}"] + ["}" + "]", "}]}"]:
                        try:
                            result = json.loads(snippet + suffix)
                            if isinstance(result, list) and result:
                                logger.info("Recovered %d partial steps from truncated JSON", len(result))
                                return {"executed_steps": result, "screenshots": [], "current_page_state": {}}
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        return None


# 全局计数器用于为截图文件生成唯一编号（在子进程中使用）
_screenshot_counter = 0


def _save_screenshot_to_file(screenshot_b64: str, step_idx: int) -> str:
    """将 base64 截图数据保存为 PNG 文件，返回文件名（相对路径）。

    截图保存到 settings.screenshot_dir 目录，文件名格式为 step_{idx}_{timestamp}.png。
    返回文件名（不含目录路径），前端可通过 /api/screenshots/{filename} 获取。

    这大幅减少了 JSON 传输大小：文件路径约 50 字符，而 base64 字符串约 50-200KB。
    """
    global _screenshot_counter
    screenshot_dir = Path(settings.data_dir) / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    img_filename = f"step_{step_idx}_{int(time.time())}_{_screenshot_counter}.png"
    _screenshot_counter += 1
    img_path = screenshot_dir / img_filename

    try:
        # 如果是 data URI 格式 (data:image/png;base64,...)，先提取纯 base64 部分
        if screenshot_b64.startswith("data:image"):
            b64_data = screenshot_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
        else:
            img_bytes = base64.b64decode(screenshot_b64)
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        return img_filename
    except Exception as exc:
        logger.warning("截图保存失败 step_idx=%d: %s", step_idx, exc)
        return ""


def _check_browser_available() -> bool:
    """检查系统是否有可用的浏览器（Chrome/Chromium）。"""
    from app.task2.agent.env_utils import find_chrome_path
    return find_chrome_path() is not None


def _get_action_fallback(tool_name: str, args: dict, description: str) -> tuple[str | None, dict | None]:
    """Get a fallback action strategy when the primary action fails.

    Returns (fallback_tool, fallback_args) or (None, None) if no fallback exists.

    Fallback strategies:
    - browser_click → browser_evaluate JS click
    - browser_type → browser_evaluate JS value set (uses json.dumps for safe escaping)
    - browser_navigate → browser_evaluate JS location change

    All JS string interpolation uses json.dumps to prevent injection from
    values containing quotes, backslashes, or other special characters.
    """
    target = args.get("target", "")
    text = args.get("text", "")
    url = args.get("url", "")

    if tool_name == "browser_click" and target:
        # Try JS click with eN ref or CSS selector
        if re.match(r'^e\d+$', target):
            # eN ref failed → try JS click by evaluating the element
            return ("browser_evaluate", {"script": "document.querySelector('[data-testid], button, a, input').click()"})
        else:
            # Descriptive target → try JS click with generic selector (no interpolation needed)
            return ("browser_evaluate", {"script": "document.querySelector('button, [role=button], a').click()"})

    elif tool_name == "browser_type" and target and text:
        # Use json.dumps for safe JS string escaping (handles quotes, backslashes, etc.)
        text_json = json.dumps(text)
        if re.match(r'^e\d+$', target):
            return ("browser_evaluate", {"script": f"const els = document.querySelectorAll('input, textarea'); for (const el of els) {{ if (el.offsetParent !== null) {{ el.focus(); el.value = JSON.parse({text_json}); break; }} }}"})
        else:
            return ("browser_evaluate", {"script": f"const el = document.querySelector('input, textarea'); if (el) {{ el.focus(); el.value = JSON.parse({text_json}); }}"})

    elif tool_name == "browser_navigate" and url:
        # URLs don't need JSON escaping but single quotes must be handled
        safe_url = url.replace("'", "\\'")
        return ("browser_evaluate", {"script": f"window.location.href = '{safe_url}'"})

    return (None, None)


def _mcp_execute_process(plan_json: str, scenario_json: str, output_file: str, conn) -> None:
    """Run MCP execution in a child process with its own event loop.

    This completely isolates MCP SDK's anyio from LangGraph's anyio.
    The child process creates its own asyncio event loop, connects to
    MCP servers, executes all plan actions, and writes results to a
    temp file (avoids Pipe buffer deadlock with large screenshot data).

    Args:
        plan_json: JSON string of the plan actions list.
        scenario_json: JSON string of the scenario dict.
        output_file: Path to temp file for writing results (avoids pipe deadlock).
        conn: multiprocessing Pipe connection for small error signals only.
    """
    import asyncio
    import logging

    # Set up file-based logging for child process diagnostics
    child_logger = logging.getLogger("mcp_execute_child")
    child_logger.setLevel(logging.INFO)
    fh = logging.FileHandler("/tmp/mcp_execute_child.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    child_logger.addHandler(fh)

    # Apply clean environment from shared env_utils
    from app.task2.agent.env_utils import build_child_env, find_chrome_path

    child_env = build_child_env()
    for key, value in child_env.items():
        os.environ[key] = value
    # Also clear proxy keys not present in clean_env
    for key in list(os.environ.keys()):
        if "proxy" in key.lower() and key not in child_env:
            del os.environ[key]

    chrome_path = find_chrome_path()
    if chrome_path:
        os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = chrome_path
        os.environ["CHROME_PATH"] = chrome_path
        child_logger.info("Chrome path set: %s", chrome_path)
    else:
        child_logger.warning("Chrome not found via dynamic search")

    child_logger.info("Child process started, plan has %d actions", len(json.loads(plan_json)))

    async def _run():
        from app.task2.agent.mcp_client import MCPClient
        from mcp import types as mcp_types

        plan = json.loads(plan_json)
        scenario = json.loads(scenario_json)

        mcp_client = MCPClient()
        child_logger.info("Attempting MCP connection...")
        try:
            await asyncio.wait_for(mcp_client.connect(servers=["playwright", "memory"]), timeout=60)
            child_logger.info("MCP client connected in child process")
            # Log available tools
            all_tools = await mcp_client.list_all_tools()
            for server, tools in all_tools.items():
                tool_names = [t.name for t in tools]
                child_logger.info("Server '%s' tools: %s", server, tool_names)
        except asyncio.TimeoutError:
            child_logger.error("MCP connection timed out")
            conn.send("error")
            _write_result(output_file, {"error": "MCP连接超时（60秒）"})
            return
        except Exception as exc:
            child_logger.error("MCP connection failed: %s", exc)
            conn.send("error")
            _write_result(output_file, {"error": f"MCP连接失败: {exc}"})
            return

        executed_steps = []
        screenshots = []
        current_page_state = {}

        # Store scenario in memory
        try:
            await mcp_client.call_tool(
                "memory", "store_context",
                {"key": "current_scenario", "data": json.dumps(scenario)},
            )
        except Exception:
            pass

        for idx, action in enumerate(plan):
            tool_name = action.get("tool", "")
            args = action.get("args", {})
            description = action.get("description", "")

            if not tool_name:
                tool_name = action.get("tool_name", "")
            if not args:
                args = action.get("parameters", {})

            logger.info("Executing %d/%d: %s — %s", idx + 1, len(plan), tool_name, description)
            child_logger.info("Executing %d/%d: %s — %s", idx + 1, len(plan), tool_name, description)

            step_result = {
                "step_number": idx + 1,
                "action": {"tool": tool_name, "args": dict(args), "description": description},
                "page_state": None,
                "screenshot": "",
                "success": False,
                "error": None,
            }

            # 兼容旧参数名：将 "ref" 映射为 Playwright MCP 的 "target"
            if "ref" in args and "target" not in args:
                args["target"] = args.pop("ref")

            # --- 动态 ref 解析：交互工具的 target 使用渐进式回退链 ---
            if tool_name in INTERACTIVE_TOOL_NAMES:
                target_value = args.get("target", "")
                # 判断是否需要解析：target 为空、描述性占位符、或不是有效的 eN 格式
                needs_resolution = (
                    not target_value
                    or not re.match(r'^e\d+$', target_value)
                )
                if needs_resolution:
                    child_logger.info("Target '%s' 需要解析 — 使用渐进式回退链", target_value or "(空)")
                    try:
                        snapshot_text = await asyncio.wait_for(
                            mcp_client.call_tool_text("playwright", "browser_snapshot", {}),
                            timeout=15,
                        )
                        # 如果快照返回空的 YAML 代码块（页面可能正在加载），等待2秒后重试
                        if snapshot_text and '```yaml\n\n```' in snapshot_text:
                            child_logger.info("快照为空（页面可能正在加载），等待2秒后重试")
                            await asyncio.sleep(2)
                            snapshot_text = await asyncio.wait_for(
                                mcp_client.call_tool_text("playwright", "browser_snapshot", {}),
                                timeout=15,
                            )
                        child_logger.info("快照内容(前300字符): %s", snapshot_text[:300] if snapshot_text else "(空)")

                        # ── 使用渐进式回退链解析元素 ──
                        from app.task2.agent.element_resolver import resolve_element_with_fallback
                        resolution = await resolve_element_with_fallback(
                            snapshot_text=snapshot_text,
                            description=target_value or description,
                            mcp_client=mcp_client,
                            tool_name=tool_name,
                        )

                        if resolution:
                            child_logger.info(
                                "解析成功: '%s' → '%s' (method=%s, confidence=%.1f)",
                                target_value or description, resolution.value,
                                resolution.method, resolution.confidence,
                            )
                            step_result["resolution_method"] = resolution.method

                            # 根据解析方法适配执行方式
                            if resolution.method == "en_ref":
                                args["target"] = resolution.value
                                step_result["action"]["args"]["target"] = resolution.value

                            elif resolution.method in ("css_selector", "html_rule"):
                                # CSS/HTML规则 → 通过 JS 执行点击/操作
                                # Use json.dumps for safe JS string escaping in text values
                                if tool_name == "browser_click":
                                    tool_name = "browser_evaluate"
                                    selector_json = json.dumps(resolution.value)
                                    args = {"script": f"document.querySelector(JSON.parse({selector_json})).click()"}
                                    step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}
                                elif tool_name == "browser_type":
                                    text = args.get("text", "")
                                    text_json = json.dumps(text)
                                    selector_json = json.dumps(resolution.value)
                                    tool_name = "browser_evaluate"
                                    args = {"script": f"const el = document.querySelector(JSON.parse({selector_json})); el.focus(); el.value = JSON.parse({text_json});"}
                                    step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}
                                else:
                                    # 其他交互工具用 JS 模拟
                                    tool_name = "browser_evaluate"
                                    selector_json = json.dumps(resolution.value)
                                    args = {"script": f"document.querySelector(JSON.parse({selector_json})).click()"}
                                    step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}

                            elif resolution.method == "vlm_coordinate":
                                # VLM坐标 → JS elementFromPoint + click
                                # Use json.dumps for safe JS string escaping in text values
                                coords = json.loads(resolution.value)
                                if tool_name == "browser_click":
                                    tool_name = "browser_evaluate"
                                    args = {"script": f"document.elementFromPoint({coords['x']}, {coords['y']}).click()"}
                                    step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}
                                elif tool_name == "browser_type":
                                    text = args.get("text", "")
                                    text_json = json.dumps(text)
                                    tool_name = "browser_evaluate"
                                    args = {"script": f"const el = document.elementFromPoint({coords['x']}, {coords['y']}); if(el) {{ el.focus(); el.value = JSON.parse({text_json}); }}"}
                                    step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}

                            elif resolution.method == "keyboard":
                                # 键盘兜底 → browser_press_key
                                tool_name = "browser_press_key"
                                args = {"key": resolution.value}
                                step_result["action"] = {"tool": tool_name, "args": dict(args), "description": description}

                            # ── 成功的非eN方法存入 Memory MCP ──
                            if resolution.method != "en_ref":
                                try:
                                    await mcp_client.call_tool_text("memory", "store_context", {
                                        "key": f"element_mapping:{target_value or description}",
                                        "data": json.dumps({"method": resolution.method, "value": resolution.value}),
                                    })
                                except Exception:
                                    pass  # Memory存储失败不影响执行

                        else:
                            child_logger.warning("所有解析方法均失败: target '%s'", target_value or description)
                            step_result["success"] = False
                            step_result["error"] = f"无法解析目标元素 (所有回退方法均失败): '{target_value or description}'"
                            step_result["resolution_method"] = "failed"
                            step_result["error_category"] = _classify_error(step_result["error"])
                            executed_steps.append(step_result)
                            continue
                    except asyncio.TimeoutError:
                        child_logger.warning("Snapshot 解析超时 (15s)")
                    except Exception as exc:
                        child_logger.warning("Snapshot 解析失败: %s", exc)

            try:
                # For screenshot steps, use call_tool to capture image data
                # (call_tool_text only returns text, missing base64 image blocks)
                if tool_name == "browser_take_screenshot":
                    content_blocks = await asyncio.wait_for(
                        mcp_client.call_tool("playwright", tool_name, args),
                        timeout=15,
                    )
                    result_text = ""
                    for block in content_blocks:
                        if isinstance(block, mcp_types.TextContent):
                            result_text += block.text
                        elif isinstance(block, mcp_types.ImageContent):
                            # 保存截图为 PNG 文件而非存储 base64（减少 JSON 大小）
                            img_filename = _save_screenshot_to_file(block.data, idx)
                            if img_filename:
                                screenshots.append(img_filename)
                                step_result["screenshot"] = img_filename
                    child_logger.info("Tool %s returned %d blocks, %d chars text", tool_name, len(content_blocks), len(result_text))
                else:
                    result_text = await mcp_client.call_tool_text(
                        "playwright", tool_name, args,
                    )
                    child_logger.info("Tool %s returned %d chars", tool_name, len(result_text) if result_text else 0)

                step_result["success"] = True

                # Capture page state after interactive actions
                if tool_name in ("browser_click", "browser_type", "browser_navigate",
                                 "browser_select", "browser_hover", "browser_press"):
                    page_state = await _capture_page_state(mcp_client, screenshots, idx)
                    # 如果交互后快照为空，等待2秒后重新获取
                    snap_content = page_state.get("snapshot", "")
                    if snap_content and '```yaml\n\n```' in snap_content:
                        child_logger.info("交互后快照为空（页面正在加载），等待2秒后重试")
                        await asyncio.sleep(2)
                        retry_snap = await asyncio.wait_for(
                            mcp_client.call_tool_text("playwright", "browser_snapshot", {}),
                            timeout=10,
                        )
                        page_state["snapshot"] = retry_snap
                        # 重新提取 URL 和 title
                        for line in retry_snap.split("\n"):
                            if line.startswith("- Page URL:"):
                                page_state["url"] = line.replace("- Page URL:", "").strip()
                            elif line.startswith("- Page Title:"):
                                page_state["title"] = line.replace("- Page Title:", "").strip()
                    step_result["page_state"] = page_state
                    current_page_state.update(page_state)

                if tool_name == "browser_snapshot":
                    # 如果快照返回空的 YAML（页面可能还在加载），等待2秒后重试
                    if result_text and '```yaml\n\n```' in result_text:
                        child_logger.info("快照为空（页面可能正在加载），等待2秒后重试")
                        await asyncio.sleep(2)
                        result_text = await mcp_client.call_tool_text(
                            "playwright", "browser_snapshot", {},
                        )
                        child_logger.info("重试快照: %d chars", len(result_text) if result_text else 0)
                        # 同步更新 step_result 中的 page_state
                        step_result["page_state"] = {"snapshot": result_text}
                    current_page_state["snapshot"] = result_text

            except Exception as exc:
                step_result["error"] = str(exc)
                step_result["error_category"] = _classify_error(str(exc))
                logger.error("Action %d failed: %s: %s", idx, tool_name, exc)

                # ── 操作级别重试：尝试替代执行方式 ──
                retry_tool, retry_args = _get_action_fallback(tool_name, args, description)
                if retry_tool and retry_args:
                    child_logger.info("操作失败，尝试替代方式: %s → %s", tool_name, retry_tool)
                    try:
                        if retry_tool == "browser_evaluate":
                            result_text = await asyncio.wait_for(
                                mcp_client.call_tool_text("playwright", retry_tool, retry_args),
                                timeout=15,
                            )
                            child_logger.info("替代方式 %s 返回 %d chars", retry_tool, len(result_text) if result_text else 0)
                        else:
                            result_text = await asyncio.wait_for(
                                mcp_client.call_tool_text("playwright", retry_tool, retry_args),
                                timeout=15,
                            )
                        # 替代方式成功
                        step_result["success"] = True
                        step_result["error"] = None
                        step_result["action"] = {"tool": retry_tool, "args": retry_args, "description": description}
                        step_result["resolution_method"] = "action_fallback"
                        child_logger.info("替代方式成功: %s", retry_tool)

                        # Capture page state after fallback action
                        if retry_tool in ("browser_evaluate", "browser_press_key"):
                            page_state = await _capture_page_state(mcp_client, screenshots, idx)
                            step_result["page_state"] = page_state
                            current_page_state.update(page_state)
                    except Exception as retry_exc:
                        child_logger.warning("替代方式也失败: %s: %s", retry_tool, retry_exc)
                        # 替代方式也失败，保留原始错误
                        step_result["error"] = f"{str(exc)} (fallback also failed: {str(retry_exc)})"
                        step_result["error_category"] = _classify_error(step_result["error"])

                try:
                    page_state = await _capture_page_state(mcp_client, screenshots, idx)
                    step_result["page_state"] = page_state
                    current_page_state.update(page_state)
                except Exception:
                    pass

            executed_steps.append(step_result)

            # ── Incrementally write results to temp file after each step ──
            # This ensures partial results are available even if the child
            # process crashes midway (e.g. base64 decode error, MCP disconnect)
            try:
                _write_result(output_file, {
                    "executed_steps": executed_steps,
                    "screenshots": screenshots,
                    "current_page_state": current_page_state,
                    "memory_context": {},
                })
            except Exception as write_exc:
                child_logger.warning("Incremental result write failed at step %d: %s", idx + 1, write_exc)

            # ── Send per-step progress signal via Pipe for real-time WebSocket updates ──
            try:
                conn.send({
                    "type": "step_progress",
                    "step_number": idx + 1,
                    "total_steps": len(plan),
                    "action_tool": step_result["action"]["tool"],
                    "action_desc": step_result["action"]["description"],
                    "success": step_result.get("success", False),
                    "resolution_method": step_result.get("resolution_method"),
                })
            except Exception:
                pass  # Pipe communication failure shouldn't break execution

        # Store execution context in Memory MCP for subsequent nodes
        try:
            await mcp_client.call_tool(
                "memory", "store_context",
                {"key": "execution_context", "data": json.dumps({
                    "executed_steps_count": len(executed_steps),
                    "successful_steps": sum(1 for s in executed_steps if s.get("success")),
                    "failed_steps": sum(1 for s in executed_steps if not s.get("success")),
                    "current_url": current_page_state.get("url", ""),
                    "page_title": current_page_state.get("title", ""),
                })},
            )
            await mcp_client.call_tool(
                "memory", "store_context",
                {"key": "page_structure", "data": json.dumps({
                    "snapshot_summary": _summarize_snapshot(current_page_state.get("snapshot", "")),
                    "visible_elements": _extract_visible_elements(current_page_state.get("snapshot", "")),
                })},
            )
        except Exception as exc:
            child_logger.warning("Failed to store execution context in Memory MCP: %s", exc)

        # Retrieve stored Memory MCP context to include in results for main process
        memory_context = {}
        try:
            stored = await mcp_client.call_tool_text("memory", "retrieve_context", {"key": "page_structure"})
            if stored and "No context found" not in stored:
                memory_context["page_structure"] = json.loads(stored) if stored.startswith("{") else stored
            stored = await mcp_client.call_tool_text("memory", "retrieve_context", {"key": "execution_context"})
            if stored and "No context found" not in stored:
                memory_context["execution_context"] = json.loads(stored) if stored.startswith("{") else stored
        except Exception:
            pass

        # Write results to temp file (avoids pipe buffer deadlock with screenshots)
        _write_result(output_file, {
            "executed_steps": executed_steps,
            "screenshots": screenshots,
            "current_page_state": current_page_state,
            "memory_context": memory_context,
        })
        # Send small signal via pipe so parent knows results are ready
        conn.send("done")
        child_logger.info("Results written to file and signal sent, %d steps, %d screenshots",
                          len(executed_steps), len(screenshots))

        # Force exit after sending results — MCP disconnect may hang due to anyio cleanup
        # os._exit bypasses Python cleanup (atexit, __del__, etc) and terminates immediately
        child_logger.info("Force exiting child process to avoid anyio cleanup hang")
        os._exit(0)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
        loop.close()
    except Exception as exc:
        child_logger.error("Child process async execution failed: %s", exc)
        try:
            conn.send("error")
            _write_result(output_file, {"error": f"子进程执行失败: {exc}"})
        except Exception:
            pass
        # Force exit to prevent hanging on anyio cleanup
        os._exit(1)


async def _capture_page_state(mcp_client, screenshots: list[str], step_idx: int = 0) -> dict[str, Any]:
    """Capture current page state: screenshot and accessibility snapshot.

    Only uses tools that exist in Playwright MCP:
    - browser_take_screenshot for visual capture (not browser_screenshot)
    - browser_snapshot for accessibility snapshot (includes URL, title)

    Screenshots are saved as PNG files on disk, and the file path is
    stored in the screenshots list instead of raw base64 data.
    This significantly reduces JSON transfer size (file path ~50 chars
    vs base64 ~50-200KB).

    Each call has a 10s timeout to prevent hanging.
    """
    page_state: dict[str, Any] = {}

    try:
        screenshot_result = await asyncio.wait_for(
            mcp_client.call_tool("playwright", "browser_take_screenshot", {}),
            timeout=10,
        )
        for block in screenshot_result:
            if hasattr(block, "data") and block.type == "image":
                # 保存截图为 PNG 文件而非存储 base64（减少 JSON 大小）
                img_filename = _save_screenshot_to_file(block.data, step_idx)
                if img_filename:
                    screenshots.append(img_filename)
                    page_state["screenshot"] = img_filename
            elif hasattr(block, "text") and block.type == "text":
                # Only process real base64 image data, skip error messages
                text = block.text
                if text and not text.startswith("###") and len(text) > 100:
                    img_filename = _save_screenshot_to_file(text, step_idx)
                    if img_filename:
                        screenshots.append(img_filename)
                        page_state["screenshot"] = img_filename
    except asyncio.TimeoutError:
        logger.warning("Screenshot capture timed out (10s)")
    except Exception as exc:
        logger.warning("Failed to capture screenshot: %s", exc)

    try:
        snapshot_content = await asyncio.wait_for(
            mcp_client.call_tool_text("playwright", "browser_snapshot", {}),
            timeout=10,
        )
        page_state["snapshot"] = snapshot_content
        for line in snapshot_content.split("\n"):
            if line.startswith("- Page URL:"):
                page_state["url"] = line.replace("- Page URL:", "").strip()
            elif line.startswith("- Page Title:"):
                page_state["title"] = line.replace("- Page Title:", "").strip()
    except asyncio.TimeoutError:
        logger.warning("Snapshot capture timed out (10s)")
    except Exception as exc:
        logger.warning("Failed to get page snapshot: %s", exc)

    return page_state


async def execute_node(state: AgentState) -> dict:
    """LangGraph node: execute the planned actions via MCP.

    Uses multiprocessing to isolate MCP SDK's anyio from LangGraph's
    anyio, preventing cancel scope conflicts. The MCP execution runs
    in a child process with its own asyncio event loop and sends
    results back through a pipe.

    Args:
        state: Current AgentState with plan, scenario, and optionally
               current_page_state.

    Returns:
        Partial state update dict with executed_steps, screenshots,
        and current_page_state updated.
    """
    plan = state.get("plan", [])
    scenario = state.get("scenario", {})
    existing_steps = state.get("executed_steps", [])
    existing_screenshots = state.get("screenshots", [])

    if not plan:
        logger.warning("Execute node received empty plan — nothing to execute")
        return {
            "executed_steps": existing_steps,
            "screenshots": existing_screenshots,
            "current_page_state": {},
            "memory_context": state.get("memory_context", {}),
        }

    if not _check_browser_available():
        logger.warning("No browser available — using degraded mode")
        return _build_degraded_result(
            existing_steps, existing_screenshots, plan,
            "浏览器不可用（未安装Chrome/Chromium），使用降级模式执行",
        )

    # Run MCP execution in a child process to avoid anyio cancel scope conflicts
    logger.info("Starting MCP execution in child process (plan has %d actions)", len(plan))

    plan_json = json.dumps(plan)
    scenario_json = json.dumps(scenario)

    logger.info("MCP execute: spawning child process for plan with %d actions", len(plan))

    # Use temp file for result transfer (avoids Pipe buffer deadlock with large screenshots)
    result_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="mcp_exec_",
    )
    result_path = result_file.name
    result_file.close()

    # Pipe only used for small signals ("done" / "error"), not for large data
    parent_conn, child_conn = multiprocessing.Pipe()

    ctx = multiprocessing.get_context("spawn")
    process = ctx.Process(
        target=_mcp_execute_process,
        args=(plan_json, scenario_json, result_path, child_conn),
    )

    # ── Look up execution_id for WebSocket step_progress broadcasts ──
    # Same approach as _update_execution_status in graph.py: query the DB
    # for the active execution record matching this scenario.
    execution_id: str | None = None
    try:
        from app.db.database import SessionLocal
        from app.db.models import ExecutionRecord
        scenario_id = scenario.get("id", "")
        db = SessionLocal()
        record = db.query(ExecutionRecord).filter(
            ExecutionRecord.scenario_id == scenario_id,
            ExecutionRecord.status.in_(["planning", "executing", "verifying", "reflecting", "pending"]),
        ).order_by(ExecutionRecord.started_at.desc()).first()
        if record:
            execution_id = record.id
            logger.info("Found execution_id '%s' for step_progress broadcasts", execution_id)
        db.close()
    except Exception as exc:
        logger.warning("Failed to look up execution_id for step_progress: %s", exc)

    try:
        process.start()

        # ── Wait for child process using asyncio-friendly polling ──
        # IMPORTANT: We must NOT use synchronous blocking calls (process.is_alive(),
        # parent_conn.poll(), process.join()) directly in this async function,
        # because they block the entire asyncio event loop and prevent FastAPI
        # from serving other requests. Instead, we use asyncio.sleep() between
        # non-blocking checks and run blocking ops in a thread executor.
        start_time = time.time()
        timeout = 180
        step_progress_events: list[dict] = []
        loop = asyncio.get_event_loop()

        while True:
            # Check elapsed time first
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning("MCP child process timed out (180s) — terminating")
                process.terminate()
                await loop.run_in_executor(None, lambda: process.join(5))
                if process.is_alive():
                    process.kill()
                break

            # Non-blocking check if child process is still alive
            if not process.is_alive():
                # Child has exited — break out to read results
                break

            # Non-blocking poll for pipe signals (0 = no wait)
            if parent_conn.poll(0):
                try:
                    signal = parent_conn.recv()
                    if isinstance(signal, dict) and signal.get("type") == "step_progress":
                        # Publish WebSocket event for real-time frontend update
                        step_progress_events.append(signal)
                        if execution_id:
                            broadcaster.publish({
                                "type": "step_progress",
                                "execution_id": execution_id,
                                "step_number": signal["step_number"],
                                "total_steps": signal["total_steps"],
                                "action_tool": signal["action_tool"],
                                "success": signal["success"],
                            })
                        logger.info(
                            "Step progress: %d/%d — %s (success=%s)",
                            signal["step_number"], signal["total_steps"],
                            signal["action_tool"], signal["success"],
                        )
                    elif signal == "done" or signal == "error":
                        # Child process sent final signal — wait briefly for it to finish writing
                        await asyncio.sleep(0.2)
                        break
                except EOFError:
                    break

            # Yield control to the event loop — this is critical!
            # Without this sleep, we'd block other async tasks (FastAPI handlers).
            await asyncio.sleep(0.1)

        # ── Handle timeout case ──
        if process.is_alive():
            # Already terminated/killed above due to timeout
            # Try to read partial results from file even after timeout
            partial = _read_result(result_path)
            try:
                os.unlink(result_path)
            except Exception:
                pass
            if partial and "error" not in partial:
                logger.info("Partial results recovered after timeout: %d steps", len(partial.get("executed_steps", [])))
                return {
                    "executed_steps": partial.get("executed_steps", []),
                    "screenshots": partial.get("screenshots", []),
                    "current_page_state": partial.get("current_page_state", {}),
                    "memory_context": partial.get("memory_context", {}),
                }
            return _build_degraded_result(
                existing_steps, existing_screenshots, plan,
                "MCP执行子进程超时",
            )

        # Read results from temp file instead of pipe (avoids deadlock)
        # Retry a few times in case the file is still being written
        logger.info("Reading results from temp file: %s", result_path)
        result = _read_result(result_path)
        if result is None:
            # Child process may have exited while file was still being written
            # Wait briefly and retry
            logger.info("Result file empty on first read, waiting 1s and retrying...")
            await asyncio.sleep(1.0)
            result = _read_result(result_path)
        logger.info("Read result from file: keys=%s, steps=%d, screenshots=%d",
                    list(result.keys()) if result else None,
                    len(result.get("executed_steps", [])) if result else 0,
                    len(result.get("screenshots", [])) if result else 0)
        try:
            os.unlink(result_path)
        except Exception:
            pass

        if result is None:
            logger.warning("MCP child process completed but no result file")
            return _build_degraded_result(
                existing_steps, existing_screenshots, plan,
                "MCP子进程完成但未返回结果",
            )

        if "error" in result:
            logger.warning("MCP child process error: %s", result["error"])
            return _build_degraded_result(
                existing_steps, existing_screenshots, plan,
                result["error"],
            )

        logger.info(
            "MCP execution complete: %d/%d actions succeeded, %d screenshots",
            sum(1 for s in result.get("executed_steps", []) if s.get("success")),
            len(plan),
            len(result.get("screenshots", [])),
        )

        return {
            "executed_steps": result.get("executed_steps", []),
            "screenshots": result.get("screenshots", []),
            "current_page_state": result.get("current_page_state", {}),
            "memory_context": result.get("memory_context", {}),
        }

    except Exception as exc:
        logger.error("MCP execution process failed: %s", exc)
        return _build_degraded_result(
            existing_steps, existing_screenshots, plan,
            f"MCP执行进程失败: {exc}",
        )


def _build_degraded_result(
    existing_steps: list,
    existing_screenshots: list,
    plan: list,
    reason: str,
) -> dict:
    """Build a degraded-mode result when MCP/browser is unavailable."""
    degraded_steps = list(existing_steps) + [
        {
            "step_number": i + 1,
            "action": {
                "tool": action.get("tool", ""),
                "args": action.get("args", {}),
                "description": action.get("description", ""),
            },
            "success": False,
            "error": reason,
            "error_category": _classify_error(reason),
        }
        for i, action in enumerate(plan)
    ]
    return {
        "executed_steps": degraded_steps,
        "screenshots": existing_screenshots,
        "current_page_state": {},
        "final_result": "fail",
        "failure_reason": reason,
        "plan": plan,
    }