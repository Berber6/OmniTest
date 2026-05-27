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
    if all_steps_failed:
        logger.info("所有执行步骤失败，跳过MCP验证工具")
        tool_results = {"mcp_skipped": "执行阶段全部失败，无法进行MCP结构化验证"}
        tool_results_text = json.dumps(tool_results, indent=2)
    else:
        tool_results = await _run_verify_mcp_tools(expectations, page_text, screenshots)
        tool_results_text = json.dumps(tool_results, indent=2)

    # 步骤2：通过 LLM 进行文本验证
    text_result = await _text_verification(
        expectations_text, page_text, tool_results_text,
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
        if visual_passed or not passed:
            verification_result = visual_result
            logger.info("视觉验证: passed=%s（覆盖文本结果）", visual_passed)
        else:
            logger.info("视觉验证也失败了 — 保留文本结果")

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
        )
        logger.info("文本验证 LLM 响应 (前500字符): %s", response[:500] if response else "None")
        # Strip markdown code fences that GLM-5.1 may add despite json_object format
        clean = response.strip()
        if clean.startswith("```"):
            import re
            match = re.match(r"```(?:json)?\s*\n(.*?)\n```", clean, re.DOTALL)
            if match:
                clean = match.group(1)
        result = json.loads(clean)
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

    latest_screenshot = screenshots[-1]
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
        args=(expectations_json, page_text, result_path, child_conn),
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


def _verify_mcp_process(expectations_json_str: str, page_text_str: str, result_path: str, conn) -> None:
    """Module-level function for multiprocessing: runs verify MCP in child process.

    This is a module-level function because multiprocessing with 'spawn'
    start method cannot pickle nested functions.
    """
    import json
    import logging
    import os

    # Clear proxy in child process
    for key in list(os.environ.keys()):
        if "proxy" in key.lower():
            del os.environ[key]

    # Add conda lib path
    import shutil
    conda_lib = os.path.join(
        os.path.dirname(os.path.dirname(shutil.which("python") or "")), "lib"
    )
    if os.path.isdir(conda_lib):
        existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
        if conda_lib not in existing_ld:
            os.environ["LD_LIBRARY_PATH"] = f"{conda_lib}:{existing_ld}"

    async def _run():
        from app.task2.agent.mcp_client import MCPClient

        expectations_list = json.loads(expectations_json_str)
        results = {}

        mcp_client = MCPClient()
        try:
            await asyncio.wait_for(mcp_client.connect(servers=["verify"]), timeout=30)
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

        for idx, exp in enumerate(expectations_list):
            exp_type = exp.get("type", "page_content")
            exp_desc = exp.get("description", "")
            key = f"expectation_{idx}"

            if not verify_connected:
                results[key] = {"type": exp_type, "passed": False, "detail": "Verify MCP 服务器不可用"}
                continue

            try:
                if exp_type == "page_content":
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
                    tool_result = await mcp_client.call_tool_text(
                        "verify", "check_element_exists", {"selector": selector},
                    )
                    if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                        results[key] = {"type": "element_check", "passed": False, "detail": tool_result}
                    else:
                        results[key] = {"type": "element_check", "passed": "exists" in tool_result.lower() or "found" in tool_result.lower(), "detail": tool_result}

                elif exp_type == "url_change":
                    tool_result = await mcp_client.call_tool_text(
                        "verify", "check_text_content",
                        {"page_text": page_text_str, "expected_text": exp_desc},
                    )
                    if "unavailable" in tool_result.lower() or "degraded" in tool_result.lower():
                        results[key] = {"type": "url_check", "passed": False, "detail": tool_result}
                    else:
                        results[key] = {"type": "url_check", "passed": "true" in tool_result.lower() or "found" in tool_result.lower(), "detail": tool_result}

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
    """从 LLM 响应中解析验证结果。"""
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

        match = re.search(r"\{[^{}]*\}", response)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

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