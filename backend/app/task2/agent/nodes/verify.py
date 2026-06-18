"""LangGraph 代理图的验证节点。

实现双策略验证：
1. 文本验证优先：使用 browser_get_text + Verify MCP 工具
2. 视觉验证回退：使用 Qwen3-VL 判断截图

返回 VerifyResult，包含 passed、confidence、reason 和 verification_type。
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import tempfile

from app.llm.router import call_llm, call_llm_with_vision
from app.llm.prompts.verify_result import (
    VERIFY_TEXT_SYSTEM_PROMPT,
    VERIFY_TEXT_USER_PROMPT_TEMPLATE,
    VERIFY_VISUAL_SYSTEM_PROMPT,
    VERIFY_VISUAL_USER_PROMPT_TEMPLATE,
)
from app.task2.agent.state import AgentState

logger = logging.getLogger(__name__)


def _write_verify_result(path: str, data: dict) -> None:
    """Write verify result data to temp file as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


async def verify_node(state: AgentState) -> dict:
    """LangGraph node: verify execution results against expectations.

    Uses a dual strategy:
    - First attempts text verification (fast, cheap)
    - If text verification fails or has low confidence, falls back to
      visual verification using Qwen3-VL (slower but more accurate)
    - Also uses Verify MCP tools via subprocess (isolated from anyio)

    Args:
        state: Current AgentState with executed_steps, screenshots,
               current_page_state, and scenario with expectations.

    Returns:
        Partial state update dict with verification_result populated.
    """
    scenario = state.get("scenario", {})
    expectations = scenario.get("expectations", [])
    current_page_state = state.get("current_page_state", {})
    screenshots = state.get("screenshots", [])
    executed_steps = state.get("executed_steps", [])

    # Use snapshot content (accessibility tree) as page text for verification
    # _capture_page_state sets "snapshot" but not "page_text"
    page_text = current_page_state.get("page_text", "") or current_page_state.get("snapshot", "")
    expectations_text = _format_expectations(expectations)

    # Enhance page text with Memory MCP visible elements context
    enhanced_page_text = page_text
    memory_context = state.get("memory_context", {})
    page_structure = memory_context.get("page_structure", {})
    if isinstance(page_structure, dict):
        visible_elements = page_structure.get("visible_elements", [])
        if visible_elements and enhanced_page_text:
            enhanced_page_text += "\n\n## 页面可见元素列表\n" + "\n".join(visible_elements)

    # 如果所有执行步骤都失败了（浏览器/MCP不可用），直接返回失败，不调用LLM
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
                "visual_match": False,
                "details": "所有步骤失败，无需进一步验证",
            },
            "final_result": "fail",
            "failure_reason": failure_reason,
        }

    # 步骤1：通过子进程运行MCP验证工具
    # （此处 all_steps_failed 必为 False，已在上方提前返回）
    tool_results = await _run_verify_mcp_tools(expectations, enhanced_page_text, screenshots)
    tool_results_text = json.dumps(tool_results, indent=2)

    # 步骤2：通过 LLM 进行文本验证
    text_result = await _text_verification(
        expectations_text, enhanced_page_text, tool_results_text,
    )

    verification_result = text_result

    # 步骤3：如果文本验证失败，尝试视觉验证
    confidence = text_result.get("confidence", None)
    passed = text_result.get("passed", False)

    should_try_visual = not passed
    if confidence is not None and confidence < 0.7:
        should_try_visual = True

    if should_try_visual and screenshots:
        logger.info("文本验证: passed=%s — 回退到视觉验证", passed)
        visual_result = await _visual_verification(
            expectations_text, screenshots, text_result,
        )

        visual_passed = visual_result.get("passed", False)
        if visual_passed and not passed:
            # Visual passes, text fails → visual overrides (VLM sees actual page)
            verification_result = visual_result
            logger.info("视觉验证: passed=%s — 覆盖文本结果（视觉通过，文本失败）", visual_passed)
        elif not visual_passed and not passed:
            # Both fail → keep the one with higher confidence
            text_conf = text_result.get("confidence", 0) or 0
            visual_conf = visual_result.get("confidence", 0) or 0
            verification_result = text_result if text_conf >= visual_conf else visual_result
            logger.info(
                "视觉验证也失败 — 保留置信度较高的结果 (text_conf=%.2f, visual_conf=%.2f)",
                text_conf, visual_conf,
            )
        elif visual_passed and passed:
            # Both pass → keep text result (cheaper, faster)
            verification_result = text_result
            logger.info("视觉验证通过但文本也通过 — 保留文本结果（更快）")

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
    tool_results_text: str,
) -> dict:
    """使用 GLM-5.1 进行基于文本的验证。"""
    user_prompt = VERIFY_TEXT_USER_PROMPT_TEMPLATE.format(
        expectations_text=expectations_text,
        page_text=page_text[:3000] if len(page_text) > 3000 else page_text,
        tool_results_text=tool_results_text,
    )

    try:
        response = await call_llm(
            model_key="glm_5_1",
            prompt=user_prompt,
            system_prompt=VERIFY_TEXT_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
            pipeline_stage="verify_text",
        )
        logger.info("文本验证 LLM 响应 (前500字符): %s", response[:500] if response else "None")
        # Use shared JSON parser to handle markdown code fences and embedded JSON
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
            "visual_match": None,
            "details": "LLM 响应不是有效的 JSON",
        }
    except Exception as exc:
        logger.error("文本验证失败: %s", exc)
        return {
            "passed": False,
            "reason": f"文本验证失败: {exc}",
            "text_match": False,
            "visual_match": None,
            "details": str(exc),
        }


async def _visual_verification(
    expectations_text: str,
    screenshots: list[str],
    previous_text_result: dict,
) -> dict:
    """使用 Qwen3-VL 进行视觉验证。"""
    if not screenshots:
        logger.warning("没有可用的截图用于视觉验证")
        return {
            "passed": False,
            "reason": "没有可用的截图用于视觉验证",
            "text_match": None,
            "visual_match": False,
            "details": "执行期间未捕获截图",
        }

    # 获取最新截图用于视觉验证
    # 新格式：截图为文件路径（.png 结尾），需读取文件并编码为 base64
    # 旧格式：截图为原始 base64 字符串，直接使用
    latest_screenshot = screenshots[-1]
    if latest_screenshot.endswith(".png") or latest_screenshot.endswith(".jpg"):
        # 新格式：文件路径引用 — 从磁盘读取并编码为 base64
        import base64 as _b64
        from app.config import settings as _settings
        from pathlib import Path as _Path
        screenshot_path = _Path(_settings.data_dir) / "screenshots" / latest_screenshot
        if screenshot_path.exists():
            with open(screenshot_path, "rb") as img_f:
                latest_screenshot = _b64.b64encode(img_f.read()).decode()
        else:
            logger.warning("截图文件不存在: %s", screenshot_path)
            return {
                "passed": False,
                "reason": f"截图文件不存在: {latest_screenshot}",
                "text_match": None,
                "visual_match": False,
                "details": "截图文件丢失",
            }

    previous_text_result_str = json.dumps(previous_text_result, indent=2)

    user_prompt = VERIFY_VISUAL_USER_PROMPT_TEMPLATE.format(
        expectations_text=expectations_text,
        previous_text_result=previous_text_result_str,
    )

    try:
        response = await call_llm_with_vision(
            model_key="qwen3_vl",
            prompt=user_prompt,
            image=latest_screenshot,
            system_prompt=VERIFY_VISUAL_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2048,
            pipeline_stage="verify_visual",
        )
        result = _parse_verification_json(response)
        result["verification_type"] = "visual"
        return result
    except Exception as exc:
        logger.error("视觉验证失败: %s", exc)
        return {
            "passed": False,
            "reason": f"视觉验证失败: {exc}",
            "text_match": None,
            "visual_match": False,
            "details": str(exc),
        }


async def _run_verify_mcp_tools(
    expectations: list[dict],
    page_text: str,
    screenshots: list[str],
) -> dict:
    """使用 Verify MCP 工具进行结构化检查（通过子进程隔离 anyio）。"""
    expectations_json = json.dumps(expectations)
    screenshots_json = json.dumps(screenshots)

    # Use temp file for result transfer (avoids Pipe buffer deadlock)
    result_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="mcp_verify_",
    )
    result_path = result_file.name
    result_file.close()

    parent_conn, child_conn = multiprocessing.Pipe()
    ctx = multiprocessing.get_context("spawn")
    process = ctx.Process(
        target=_verify_mcp_process,
        args=(expectations_json, page_text, screenshots_json, result_path, child_conn),
    )

    try:
        process.start()
        process.join(timeout=45)

        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
            if process.is_alive():
                process.kill()
            try:
                os.unlink(result_path)
            except Exception:
                pass
            return {"mcp_connection_timeout": "验证MCP子进程超时"}

        # Read results from temp file
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                content = f.read()
            os.unlink(result_path)
        except FileNotFoundError:
            return {"mcp_connection_error": "验证MCP子进程未返回结果"}

        if not content:
            return {"mcp_connection_error": "验证MCP子进程结果为空"}

        return json.loads(content)

    except Exception as exc:
        logger.warning("Verify MCP process failed: %s", exc)
        try:
            os.unlink(result_path)
        except Exception:
            pass
        return {"mcp_connection_error": str(exc)}


def _verify_mcp_process(expectations_json_str: str, page_text_str: str, screenshots_json_str: str, result_path: str, conn) -> None:
    """Module-level function for multiprocessing: runs verify MCP in child process.

    This is a module-level function because multiprocessing with 'spawn'
    start method cannot pickle nested functions.
    """
    import json
    import logging
    import os

    # Apply clean environment from shared env_utils
    from app.task2.agent.env_utils import build_child_env

    child_env = build_child_env()
    for key, value in child_env.items():
        os.environ[key] = value
    # Also clear proxy keys not present in clean_env
    for key in list(os.environ.keys()):
        if "proxy" in key.lower() and key not in child_env:
            del os.environ[key]

    async def _run():
        from app.task2.agent.mcp_client import MCPClient

        expectations_list = json.loads(expectations_json_str)
        results = {}

        mcp_client = MCPClient()
        try:
            await asyncio.wait_for(mcp_client.connect(servers=["verify", "playwright"]), timeout=30)
        except asyncio.TimeoutError:
            results["mcp_connection_timeout"] = "验证MCP连接超时"
            _write_verify_result(result_path, results)
            conn.send("done")
            return
        except Exception as exc:
            results["mcp_connection_error"] = str(exc)
            _write_verify_result(result_path, results)
            conn.send("done")
            return

        verify_connected = await mcp_client.is_server_connected("verify")
        playwright_connected = await mcp_client.is_server_connected("playwright")

        for idx, exp in enumerate(expectations_list):
            exp_type = exp.get("type", "page_content")
            exp_desc = exp.get("description", "")
            key = f"expectation_{idx}"

            if not verify_connected and not playwright_connected:
                results[key] = {"type": exp_type, "passed": False, "detail": "Verify MCP 和 Playwright MCP 服务器均不可用"}
                continue

            try:
                if exp_type == "page_content":
                    if not verify_connected:
                        results[key] = {"type": "text_check", "passed": False, "detail": "Verify MCP 服务器不可用"}
                        continue
                    tool_result = await mcp_client.call_tool_text(
                        "verify", "check_text_content",
                        {"page_text": page_text_str, "expected_text": exp_desc},
                    )
                    if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                        results[key] = {"type": "text_check", "passed": False, "detail": tool_result}
                    else:
                        results[key] = {"type": "text_check", "passed": "true" in tool_result.lower() or "found" in tool_result.lower(), "detail": tool_result}

                elif exp_type == "element_exists":
                    selector = _extract_selector(exp_desc)
                    # First try real DOM check via Playwright MCP (more accurate)
                    if playwright_connected:
                        js_check = f"document.querySelector('{selector}') !== null && document.querySelector('{selector}').offsetParent !== null"
                        dom_result = await mcp_client.call_tool_text(
                            "playwright", "browser_evaluate", {"script": js_check}
                        )
                        results[key] = {
                            "type": "element_check",
                            "passed": "true" in dom_result.lower(),
                            "detail": f"DOM verification: {dom_result}"
                        }
                    else:
                        # Fall back to Verify MCP heuristic check (no browser access)
                        if not verify_connected:
                            results[key] = {"type": "element_check", "passed": False, "detail": "Verify MCP 和 Playwright MCP 服务器均不可用"}
                            continue
                        tool_result = await mcp_client.call_tool_text(
                            "verify", "check_element_exists", {"selector": selector},
                        )
                        if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                            results[key] = {"type": "element_check", "passed": False, "detail": tool_result}
                        else:
                            results[key] = {
                                "type": "element_check",
                                "passed": "exists" in tool_result.lower() or "found" in tool_result.lower(),
                                "detail": f"Heuristic check (no browser): {tool_result}"
                            }

                elif exp_type == "url_change":
                    if not verify_connected:
                        results[key] = {"type": "url_check", "passed": False, "detail": "Verify MCP 服务器不可用"}
                        continue
                    tool_result = await mcp_client.call_tool_text(
                        "verify", "check_text_content",
                        {"page_text": page_text_str, "expected_text": exp_desc},
                    )
                    if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                        results[key] = {"type": "url_check", "passed": False, "detail": tool_result}
                    else:
                        results[key] = {"type": "url_check", "passed": "true" in tool_result.lower() or "found" in tool_result.lower(), "detail": tool_result}

                elif exp_type == "element_visible":
                    selector = _extract_selector(exp_desc)
                    # Use Playwright to check actual visibility in the DOM
                    if playwright_connected:
                        js_check = (
                            f"(() => {{"
                            f"const el = document.querySelector('{selector}');"
                            f"if (!el) return 'not_found';"
                            f"const style = window.getComputedStyle(el);"
                            f"if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return 'hidden';"
                            f"if (el.offsetParent === null) return 'not_visible';"
                            f"return 'visible';"
                            f"}})()"
                        )
                        dom_result = await mcp_client.call_tool_text(
                            "playwright", "browser_evaluate", {"script": js_check}
                        )
                        visible = "visible" in dom_result.lower() and "not_visible" not in dom_result.lower() and "hidden" not in dom_result.lower() and "not_found" not in dom_result.lower()
                        results[key] = {
                            "type": "visibility_check",
                            "passed": visible,
                            "detail": f"DOM visibility check: {dom_result}"
                        }
                    else:
                        # Fall back to Verify MCP heuristic check
                        if not verify_connected:
                            results[key] = {"type": "visibility_check", "passed": False, "detail": "Verify MCP 和 Playwright MCP 服务器均不可用"}
                            continue
                        tool_result = await mcp_client.call_tool_text(
                            "verify", "check_element_exists", {"selector": selector},
                        )
                        if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                            results[key] = {"type": "visibility_check", "passed": False, "detail": tool_result}
                        else:
                            results[key] = {
                                "type": "visibility_check",
                                "passed": "visible" in tool_result.lower() or "exists" in tool_result.lower() or "found" in tool_result.lower(),
                                "detail": f"Heuristic check (no browser): {tool_result}"
                            }

                elif exp_type == "visual_match":
                    reference_image_path = exp.get("reference_image", "")
                    if reference_image_path:
                        # Load the reference image from crawled_docs/images/
                        from pathlib import Path as _Path
                        from app.config import settings as _settings
                        import base64 as _b64
                        full_img_path = _settings.data_dir / "crawled_docs" / reference_image_path
                        if full_img_path.exists():
                            with open(full_img_path, "rb") as img_f:
                                expected_b64 = _b64.b64encode(img_f.read()).decode()
                            # Use the last screenshot as actual image for comparison
                            # 新格式：截图为文件路径(.png)，需读取文件并编码为 base64
                            # 旧格式：截图为原始 base64 字符串，直接使用
                            if screenshots_json_str:
                                try:
                                    screenshots_list = json.loads(screenshots_json_str)
                                    actual_item = screenshots_list[-1] if screenshots_list else ""
                                except Exception:
                                    actual_item = ""
                            else:
                                actual_item = ""
                            # 如果截图是文件路径引用，从磁盘读取
                            actual_b64 = ""
                            if actual_item:
                                if isinstance(actual_item, str) and (actual_item.endswith(".png") or actual_item.endswith(".jpg")):
                                    # 新格式：文件路径 — 读取并编码为 base64
                                    actual_path = _Path(_settings.data_dir) / "screenshots" / actual_item
                                    if actual_path.exists():
                                        with open(actual_path, "rb") as img_f:
                                            actual_b64 = _b64.b64encode(img_f.read()).decode()
                                else:
                                    # 旧格式：直接是 base64 字符串
                                    actual_b64 = actual_item
                            if actual_b64 and expected_b64:
                                tool_result = await mcp_client.call_tool_text(
                                    "verify", "compare_screenshots",
                                    {"expected_b64": expected_b64, "actual_b64": actual_b64},
                                )
                                results[key] = {
                                    "type": "visual_match_check",
                                    "passed": "similar" in tool_result.lower() or "true" in tool_result.lower() or "match" in tool_result.lower(),
                                    "detail": tool_result,
                                }
                            else:
                                results[key] = {"type": "visual_match_check", "passed": False, "detail": "No execution screenshot available for comparison"}
                        else:
                            results[key] = {"type": "visual_match_check", "passed": False, "detail": f"Reference image not found: {reference_image_path}"}
                    else:
                        results[key] = {"type": "visual_match_check", "passed": False, "detail": "No reference_image specified for visual_match expectation"}

            except Exception as exc:
                results[key] = {"type": exp_type, "passed": False, "detail": f"Verify MCP 调用失败: {exc}"}

        try:
            await mcp_client.disconnect()
        except Exception:
            pass

        # Write results to file then signal via pipe
        _write_verify_result(result_path, results)
        conn.send("done")
        os._exit(0)  # Force exit to avoid anyio cleanup hang

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
        loop.close()
    except Exception as exc:
        try:
            _write_verify_result(result_path, {"mcp_connection_error": str(exc)})
            conn.send("error")
        except Exception:
            pass


def _parse_verification_json(response: str) -> dict:
    """从 LLM 响应中解析验证结果。

    使用共享的 parse_llm_json 解析，并提供验证领域的默认值回退。
    """
    from app.llm.json_parser import parse_llm_json

    result = parse_llm_json(response)
    if result is not None:
        return result

    logger.warning("无法将验证响应解析为 JSON: %s", response[:300])
    return {
        "passed": False,
        "reason": "无法解析验证响应",
        "text_match": None,
        "visual_match": None,
        "details": response[:200],
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


def _extract_selector(description: str) -> str:
    """尝试从预期结果描述中提取 CSS/XPATH 选择器。"""
    import re

    if "button" in description.lower():
        name_match = re.search(r"'([^']+)'", description)
        if name_match:
            return f"button:has-text('{name_match.group(1)}')"

    if "input" in description.lower() or "field" in description.lower():
        name_match = re.search(r"'([^']+)'", description)
        if name_match:
            return f"input[placeholder*='{name_match.group(1)}']"

    name_match = re.search(r"'([^']+)'", description)
    if name_match:
        return f"*:has-text('{name_match.group(1)}')"

    return description