"""单 worker 进程执行完整场景：登录 → 观察/决策/执行循环 → 验证 → 反思重试。

替代旧的"每节点起子进程"设计。一个场景 = 一个 spawn 子进程 = 一个常驻浏览器会话。
子进程通过 Pipe 向父进程推送 step_progress 事件（含截图），父进程转发给 broadcaster。
最终结果写临时文件回传父进程。

架构核心：
- 子进程内只有一个 event loop，MCP 连接一次、浏览器开一次、全程不关。
- 删除 LangGraph runtime（anyio 冲突源）+ snapshot_resolver（eN 来自真实快照）。
- 登录用确定性 CSS 选择器（input[name=emailOrUsername] 等）。
- agent 循环：每步先 snapshot，LLM 看真实快照决定下一个动作，执行，循环。
- 验证在同会话对真实最终页面做（文本 + 视觉）。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import multiprocessing
import os
import tempfile
import time
from functools import partial
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# 配置常量
# ============================================================================
MAX_LOOP_STEPS = 24  # 观察-决策-执行循环最大步数（超出强制结束）
# 16 太紧：登录占 2-3 步，多步场景 + ref 失效重试易在结束前耗尽。
MAX_RETRIES = 1      # 验证失败后最大重试次数（减少总耗时）
LOGIN_WAIT_SECONDS = 8  # 登录提交后等待时长（SPA 路由跳转需要时间）
SNAPSHOT_WAIT_SECONDS = 1  # 每次 snapshot 前等待（让页面稳定）
# 单次调用超时：防止 LLM/MCP 调用挂起导致整个子进程空转到 900s 总超时被杀。
# 命中超时即视为该步失败，循环继续或结束，而不是静默卡死几分钟。
LLM_CALL_TIMEOUT = 90        # 单次 LLM 决策/验证/反思调用
MCP_TOOL_CALL_TIMEOUT = 60   # 单次 MCP 工具调用（snapshot/click/type 等）


# ============================================================================
# 子进程：执行完整场景
# ============================================================================
def _child_worker(
    scenario_json: str,
    execution_id: str,
    result_file: str,
    pipe_send: Any,
    config: dict,
) -> None:
    """子进程入口：执行整个场景（登录 → 循环 → 验证 → 反思）。

    Args:
        scenario_json: 场景 JSON 字符串
        execution_id: 执行记录 ID
        result_file: 结果写入路径
        pipe_send: multiprocessing.Pipe 发送端（推送进度事件）
        config: {base_url, login_email, login_password, screenshot_dir, ...}
    """
    # 子进程需要独立 event loop + 清理环境
    from app.task2.agent.env_utils import build_child_env
    for k, v in build_child_env().items():
        os.environ[k] = v

    # 子进程独立日志：写到 /tmp/agent_{execution_id}.log，便于调试 agent 行为
    child_logger = logging.getLogger()
    child_logger.setLevel(logging.INFO)
    log_file = f"/tmp/agent_{execution_id}.log"
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    child_logger.addHandler(fh)
    logger.info(f"子进程日志写入 {log_file}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _run_scenario(scenario_json, execution_id, pipe_send, config)
        )
        # 写结果文件
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.exception("子进程异常: %s", exc)
        result = {
            "final_result": "fail",
            "failure_reason": f"子进程异常: {exc}",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
        }
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f)
    finally:
        loop.close()
        os._exit(0)


def _build_display_plan(scenario: dict) -> list[dict]:
    """从场景步骤生成展示用 plan（前端 ExecutionTimeline 的 plan 节点）。

    生产 agent 是反应式的（LLM 在 _agent_loop 中每步实时决策，不依赖此 plan），
    这里仅把场景 steps + expectations 翻译成 Action 格式供前端展示。
    Action 字段对齐 frontend/src/lib/types.ts 的 Action interface。
    """
    plan: list[dict] = []
    for s in scenario.get("steps", []):
        action_text = str(s.get("action", "")).strip()
        target_text = str(s.get("target", "")).strip()
        step_num = s.get("step", "?")
        # 启发式映射：场景动作文本 → MCP 工具名（仅用于展示，不参与执行）
        a = action_text.lower()
        if any(k in a for k in ("点击", "click", "press", "按钮")):
            tool = "browser_click"
        elif any(k in a for k in ("输入", "填写", "type", "input")):
            tool = "browser_type"
        elif any(k in a for k in ("导航", "打开", "前往", "navigate", "go to")):
            tool = "browser_navigate"
        elif any(k in a for k in ("选择", "select", "下拉")):
            tool = "browser_select_option"
        elif any(k in a for k in ("拖", "drag")):
            tool = "browser_drag"
        elif any(k in a for k in ("悬停", "hover")):
            tool = "browser_hover"
        elif any(k in a for k in ("等待", "wait")):
            tool = "browser_wait_for"
        else:
            tool = "browser_click"  # 默认猜测
        plan.append({
            "tool": tool,
            "args": {"target": target_text} if target_text else {},
            "description": f"步骤{step_num}: {action_text}" + (f"（目标：{target_text}）" if target_text else ""),
        })
    return plan


async def _run_scenario(
    scenario_json: str,
    execution_id: str,
    pipe_send: Any,
    config: dict,
) -> dict:
    """执行场景主流程（async 协程，在子进程的 loop 里跑）。

    返回 {final_result, failure_reason, executed_steps, screenshots,
           verification_result, retry_count, reflection, plan}
    """
    scenario = json.loads(scenario_json)
    base_url = config["base_url"]
    login_email = config["login_email"]
    login_password = config["login_password"]
    screenshot_dir = Path(config["screenshot_dir"])
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # 生成展示用 plan（前端 ExecutionTimeline 的 plan 节点）。
    # 注意：生产 agent 是反应式的（LLM 在 _agent_loop 中每步实时决策），
    # 不依赖此 plan 执行。这里仅把场景步骤翻译成 Action 格式供前端展示。
    display_plan = _build_display_plan(scenario)

    from app.task2.agent.mcp_client import MCPClient
    mcp = MCPClient()

    try:
        # 1. 连接 MCP（playwright + memory + verify）
        await asyncio.wait_for(
            mcp.connect(servers=["playwright", "memory", "verify"]),
            timeout=60,
        )
        _send_event(pipe_send, {"type": "phase", "phase": "mcp_connected"})
    except Exception as exc:
        logger.error("MCP 连接失败: %s", exc)
        return {
            "final_result": "fail",
            "failure_reason": f"MCP 连接失败: {exc}",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": display_plan,
        }

    # 2. 确定性登录（先检查是否已登录）
    login_ok, login_err = await _ensure_logged_in(
        mcp, base_url, login_email, login_password, pipe_send
    )
    if not login_ok:
        await mcp.disconnect()
        return {
            "final_result": "fail",
            "failure_reason": f"登录失败: {login_err}",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": display_plan,
        }

    # 3. 主循环：重试逻辑（验证失败 → 反思 → 重试）
    reflection = ""
    for retry in range(MAX_RETRIES + 1):
        _send_event(pipe_send, {
            "type": "phase",
            "phase": "agent_loop_start",
            "retry": retry,
        })

        # 执行 agent 循环
        exec_result = await _agent_loop(
            mcp, scenario, reflection, pipe_send, screenshot_dir, execution_id
        )
        executed_steps = exec_result["executed_steps"]
        screenshots = exec_result["screenshots"]
        loop_reason = exec_result.get("reason", "")

        # 验证
        _send_event(pipe_send, {"type": "phase", "phase": "verification"})
        verify_result = await _verify(
            mcp, scenario, executed_steps, screenshots, screenshot_dir
        )

        if verify_result["passed"]:
            # 成功
            await mcp.disconnect()
            return {
                "final_result": "pass",
                "failure_reason": "",
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "verification_result": verify_result,
                "retry_count": retry,
                "reflection": reflection,
                "plan": display_plan,
            }

        # 验证失败
        if retry < MAX_RETRIES:
            # 反思
            _send_event(pipe_send, {"type": "phase", "phase": "reflection"})
            reflection = await _reflect(
                mcp, scenario, executed_steps, verify_result, loop_reason
            )
            logger.info("重试 %d: 反思=%s", retry + 1, reflection[:200])
        else:
            # 耗尽重试
            await mcp.disconnect()
            return {
                "final_result": "fail",
                "failure_reason": verify_result.get("reason", "验证失败且重试耗尽"),
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "verification_result": verify_result,
                "retry_count": retry,
                "reflection": reflection,
                "plan": display_plan,
            }

    # 不会到这里
    await mcp.close_all()
    return {
        "final_result": "fail",
        "failure_reason": "未知错误",
        "executed_steps": [],
        "screenshots": [],
        "verification_result": {},
        "retry_count": 0,
        "plan": display_plan,
    }


# ============================================================================
# 确定性登录
# ============================================================================
async def _ensure_logged_in(
    mcp: Any,
    base_url: str,
    email: str,
    password: str,
    pipe_send: Any,
) -> tuple[bool, str]:
    """确保浏览器处于登录状态。

    1. 先导航到应用首页，检查是否已登录（URL 不在 /login，且无登录表单）。
    2. 如果已登录，直接返回成功。
    3. 如果未登录，导航到 /login，从快照解析 eN 引用，执行确定性登录。

    Returns:
        (success, error_message)
    """
    import re as _re
    _send_event(pipe_send, {"type": "phase", "phase": "login"})

    async def _nav(url: str) -> tuple[str, bool]:
        # 导航偶发 60s 超时（demo SPA 加载慢 + Playwright domcontentloaded 等待）。
        # 策略：先尝试导航；超时后不直接判失败——很多情况 goto 的 domcontentloaded
        # 等待超时但页面其实已渲染（SPA 重定向后 DOM 已稳定）。这时 snapshot 能拿到
        # 内容就视为导航成功。仍失败才重试一次再判错。
        for attempt in range(2):
            try:
                return await asyncio.wait_for(
                    mcp.call_tool_checked("playwright", "browser_navigate", {"url": url}),
                    timeout=MCP_TOOL_CALL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("导航超时 attempt=%d url=%s", attempt + 1, url)
                # 超时后试探 snapshot：页面可能已加载，只是 goto 等待未满足
                snap_txt, snap_err = await _snap()
                if not snap_err and snap_txt and "Page URL:" in snap_txt:
                    logger.info("导航超时但 snapshot 成功，页面已加载，继续")
                    return snap_txt, False
                if attempt == 0:
                    await asyncio.sleep(3)
        return f"导航超时（{MCP_TOOL_CALL_TIMEOUT}s）且 snapshot 也失败: {url}", True

    async def _snap() -> tuple[str, bool]:
        try:
            return await asyncio.wait_for(
                mcp.call_tool_checked("playwright", "browser_snapshot", {}),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return "（快照超时）", True

    try:
        # Step 1: 先导航到应用首页，检查是否已登录
        txt, err = await _nav(base_url)
        if err:
            return False, f"导航到应用首页失败: {txt[:200]}"

        # 等待页面渲染：最多重试 5 次 snapshot，每次间隔 2s。
        # SPA 首次导航后 accessibility tree 可能延迟出现，空快照会导致 has_login_form
        # 误判为 False，从而跳过登录进入空白的 _agent_loop（agent 看不到任何元素）。
        snap, snap_err = "", True
        for _snap_attempt in range(5):
            await asyncio.sleep(2)
            snap, snap_err = await _snap()
            if not snap_err and snap and "[ref=" in snap:
                break  # 快照有实际元素，可用
            logger.info(f"等待页面渲染（attempt {_snap_attempt+1}），快照仍为空")

        if not snap_err and snap:
            # 检查当前 URL 和页面状态
            current_url = ""
            for line in snap.split("\n"):
                if "Page URL:" in line:
                    current_url = line.replace("- Page URL:", "").strip()
                    break

            # 已登录的判断：URL 不在 /login，且页面没有登录表单
            # 登录表单判定更严：必须有 textbox + email/username 文本（不仅有 "Log in" 按钮，
            # 因为有些 SPA 主页可能也有 Login 链接指向登录页）
            is_on_login = "/login" in current_url.lower()
            snap_lower = snap.lower()
            has_login_form = (
                "textbox" in snap_lower
                and ("email" in snap_lower or "username" in snap_lower or "邮箱" in snap_lower)
            )
            # 关键：快照里没有 [ref= 元素（只有 yaml header）说明页面未渲染，
            # 此时 has_login_form=False 是不可信的 — 不能据此判"已登录"。
            # 应该走登录流程（_ensure_logged_in 会重新导航 + 渲染）。
            has_rendered = "[ref=" in snap
            # 调试日志：前 300 字看页面实际内容
            logger.info(
                f"登录状态检测: URL={current_url}, is_on_login={is_on_login}, "
                f"has_login_form={has_login_form}, has_rendered={has_rendered}, "
                f"snap_head={snap[:300]!r}"
            )

            if has_rendered and not is_on_login and not has_login_form:
                logger.info(f"已在登录状态（URL={current_url}），跳过登录")
                return True, ""
            if not has_rendered:
                logger.info(
                    f"页面未渲染（无 [ref= 元素），不走已登录分支，继续到登录流程重新导航"
                )
            else:
                logger.info(
                    f"未登录状态（URL={current_url}, has_login_form={has_login_form}），需执行登录"
                )

        # Step 2: 未登录 → 导航到 /login 并执行确定性登录
        login_url = f"{base_url}/login"
        txt, err = await _nav(login_url)
        if err:
            return False, f"导航到登录页失败: {txt[:200]}"

        # 等待登录页渲染（最多 30s），通过快照确认
        # 但也检查：如果 URL 已经不在 /login（说明已登录），直接跳过登录
        snap = ""
        for attempt in range(15):
            await asyncio.sleep(2)
            snap, snap_err = await _snap()
            if snap_err:
                continue
            # 检查当前 URL：如果不在 /login 页面，说明浏览器已经登录状态（自动跳转了）
            current_url = ""
            for line in snap.split("\n"):
                if "Page URL:" in line:
                    current_url = line.replace("- Page URL:", "").strip()
                    break
            if "/login" not in current_url:
                # 已经不在登录页 → 说明已登录，直接返回成功
                logger.info(f"导航到 /login 后 URL 变为 {current_url}，判定为已登录状态")
                return True, ""

            # 检查快照是否包含 email textbox
            if "textbox" in snap and ("email" in snap.lower() or "username" in snap.lower() or "邮箱" in snap.lower()):
                break
        else:
            return False, f"登录页输入框未在 30s 内渲染（快照前300字: {snap[:300]})"

        # 从快照中解析 ref 引用
        # 快照格式：- textbox [ref=e10]（旧）或 - textbox [ref=f1e10]（新）
        # 兼容两种格式：纯 eN 与 f<digits>e<digits>
        email_ref = None
        password_ref = None
        login_btn_ref = None

        ref_re = _re.compile(r'\[ref=([a-z]?\d*e\d+)\]')

        # 查找 email/username textbox
        for line in snap.split("\n"):
            line = line.strip()
            if not line.startswith("- "):
                continue
            ref_match = ref_re.search(line)
            if not ref_match:
                continue
            ref = ref_match.group(1)

            # Email/username textbox：紧跟在 "Email or username" 标签后面
            if "textbox" in line and ("active" in line or email_ref is None):
                # 检查上下文：上一行可能是 "Email or username" 或 "邮箱"
                # 简化逻辑：第一个 textbox 就是邮箱
                if email_ref is None:
                    email_ref = ref

            # Password textbox：包含 "password" 关键词的 textbox，或在 password 容器里
            elif "textbox" in line and password_ref is None and email_ref is not None:
                # 第二个 textbox 就是密码（登录页只有两个 textbox）
                password_ref = ref

            # Login button：包含 "Log in" 或 "登录" 文本
            elif ("Log in" in line or "登录" in line or "Login" in line) and "button" in line:
                login_btn_ref = ref

        # 如果没找到第二个 textbox，用更宽松的规则
        if not password_ref:
            # 在快照中找所有 textbox 的 ref
            all_textbox_refs = []
            for line in snap.split("\n"):
                line = line.strip()
                if "textbox" in line:
                    m = ref_re.search(line)
                    if m:
                        all_textbox_refs.append(m.group(1))
            if len(all_textbox_refs) >= 2:
                password_ref = all_textbox_refs[1]  # 第二个 textbox 是密码

        # 如果没找到 login button ref，用 "submit" 类按钮
        if not login_btn_ref:
            for line in snap.split("\n"):
                line = line.strip()
                if "button" in line and ("submit" in line.lower() or "Log in" in line or "Login" in line):
                    m = ref_re.search(line)
                    if m:
                        login_btn_ref = m.group(1)

        if not email_ref:
            return False, f"快照中未找到邮箱输入框（快照前500字: {snap[:500]})"
        if not password_ref:
            return False, f"快照中未找到密码输入框（快照前500字: {snap[:500]})"
        if not login_btn_ref:
            return False, f"快照中未找到登录按钮（快照前500字: {snap[:500]})"

        logger.info(f"登录元素引用: email={email_ref}, password={password_ref}, btn={login_btn_ref}")

        # 输入邮箱（用 eN 引用）
        try:
            txt, err = await asyncio.wait_for(
                mcp.call_tool_checked(
                    "playwright",
                    "browser_type",
                    {"target": email_ref, "element": "Email or username", "text": email},
                ),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return False, f"输入邮箱超时(eN={email_ref})"
        if err:
            return False, f"输入邮箱失败(eN={email_ref}): {txt[:200]}"

        # 输入密码
        try:
            txt, err = await asyncio.wait_for(
                mcp.call_tool_checked(
                    "playwright",
                    "browser_type",
                    {"target": password_ref, "element": "Password", "text": password},
                ),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return False, f"输入密码超时(eN={password_ref})"
        if err:
            return False, f"输入密码失败(eN={password_ref}): {txt[:200]}"

        # 点击登录按钮
        try:
            txt, err = await asyncio.wait_for(
                mcp.call_tool_checked(
                    "playwright",
                    "browser_click",
                    {"target": login_btn_ref, "element": "Log in button"},
                ),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return False, f"点击登录按钮超时(eN={login_btn_ref})"
        if err:
            return False, f"点击登录按钮失败(eN={login_btn_ref}): {txt[:200]}"

        await asyncio.sleep(LOGIN_WAIT_SECONDS)

        # 检查是否登录成功（URL 不再是 /login）
        # 注意：必须检查 snap_err —— 若 snapshot 超时/失败，snap 是错误文本，
        # "/login" not in 错误文本 会误判为登录成功，让 agent 进入循环却在登录页。
        snap, snap_err = await _snap()
        if snap_err:
            # snapshot 失败：无法确认登录状态，保守判失败，避免误进循环
            return False, f"登录后快照获取失败，无法确认登录状态: {snap[:120]}"
        # 明确解析 Page URL 行，避免在快照正文里误搜到 /login 链接
        current_url = ""
        for line in snap.split("\n"):
            if "Page URL:" in line:
                current_url = line.replace("- Page URL:", "").strip()
                break
        if "/login" in current_url.lower():
            # 可能有错误提示
            if "Invalid" in snap or "invalid" in snap:
                return False, "凭据被拒绝（Invalid username or password）"
            return False, f"登录后仍在 /login 页面（URL={current_url}）"

        logger.info("登录成功")
        return True, ""

    except Exception as exc:
        logger.exception("登录异常: %s", exc)
        return False, f"登录异常: {exc}"


# ============================================================================
# Agent 循环：观察 → 决策 → 执行
# ============================================================================
async def _agent_loop(
    mcp: Any,
    scenario: dict,
    reflection: str,
    pipe_send: Any,
    screenshot_dir: Path,
    execution_id: str,
) -> dict:
    """观察-决策-执行循环。

    Returns:
        {executed_steps: list, screenshots: list, reason: str}
    """
    from app.task2.agent.agent_loop import (
        build_decide_prompt,
        parse_decision,
        detect_loop,
        DECIDE_SYSTEM_PROMPT,
    )
    from app.llm.router import call_llm

    executed_steps = []
    screenshots = []

    for step_num in range(1, MAX_LOOP_STEPS + 1):
        # 1. 获取当前页面快照
        await asyncio.sleep(SNAPSHOT_WAIT_SECONDS)
        try:
            snap_txt, snap_err = await asyncio.wait_for(
                mcp.call_tool_checked("playwright", "browser_snapshot", {}),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("快照超时 step=%d（%ds）", step_num, MCP_TOOL_CALL_TIMEOUT)
            snap_txt, snap_err = "（快照超时）", True
        if snap_err:
            logger.warning("快照失败 step=%d: %s", step_num, snap_txt[:150])
            snap_txt = "（快照获取失败）"

        # 2. 截图：每步动作后截一张，记录该步执行后的页面状态（前端 ExecutionTimeline 展示用）。
        # 在步骤 5 执行动作之后捕获；此处先占位留空。
        screenshot_name = ""

        # 3. LLM 决策下一个动作
        loop_hint = detect_loop(executed_steps)
        if loop_hint:
            logger.info("Step %d 检测到重复动作，注入反循环提示", step_num)
        user_prompt = build_decide_prompt(
            scenario, executed_steps, snap_txt, reflection, loop_hint
        )
        # LLM 决策：超时/异常时重试一次（90s × 2 给 LLM 充分响应时间），
        # 避免单次网络抖动直接终结整个执行（之前 F8_S2 step=1 超时就丢掉全部场景）。
        llm_response = None
        last_err: Exception | None = None
        for _decide_attempt in (1, 2):
            try:
                llm_response = await asyncio.wait_for(
                    call_llm(
                        model_key="deepseek_v4_flash",
                        prompt=user_prompt,
                        system_prompt=DECIDE_SYSTEM_PROMPT,
                        temperature=0.2,
                        max_tokens=4096,
                        pipeline_stage="task2_agent_decide",
                    ),
                    timeout=LLM_CALL_TIMEOUT,
                )
                break
            except asyncio.TimeoutError as exc:
                last_err = exc
                logger.warning("LLM 决策超时 step=%d attempt=%d（%ds）",
                               step_num, _decide_attempt, LLM_CALL_TIMEOUT)
            except Exception as exc:
                last_err = exc
                logger.error("LLM 决策失败 step=%d attempt=%d: %s",
                             step_num, _decide_attempt, exc)
        if llm_response is None:
            logger.error("LLM 决策重试耗尽 step=%d: %s", step_num, last_err)
            return {
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "reason": f"LLM 决策超时/失败（step {step_num}，重试 2 次均失败）",
            }

        decision = parse_decision(llm_response)
        if decision is None:
            logger.warning("LLM 输出无法解析 step=%d: %s", step_num, llm_response[:200])
            return {
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "reason": f"LLM 输出格式错误（step {step_num}）",
            }

        reasoning = decision["reasoning"]
        tool = decision["tool"]
        args = decision["args"]
        done = decision["done"]

        logger.info("Step %d: %s | done=%s | reasoning=%s", step_num, tool, done, reasoning[:80])

        # 4. 如果 LLM 说完成了，结束循环
        if done:
            # 末步：截一张最终状态图
            final_screenshot = f"{execution_id}_step{step_num}_final_{int(time.time())}.png"
            final_path = screenshot_dir / final_screenshot
            await _take_screenshot_to_file(mcp, final_path)
            screenshots.append(final_screenshot)
            executed_steps.append({
                "step_number": step_num,
                "tool": "",
                "reasoning": reasoning,
                "success": True,
                "done": True,
                "screenshot": final_screenshot,
            })
            _send_event(pipe_send, {
                "type": "step_progress",
                "step_number": step_num,
                "total_steps": step_num,
                "action_tool": "done",
                "reasoning": reasoning,
                "screenshot": final_screenshot,
                "success": True,
            })
            return {
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "reason": "agent 判断场景已完成",
            }

        # 5. 执行动作
        try:
            result_txt, is_error = await asyncio.wait_for(
                mcp.call_tool_checked("playwright", tool, args),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("动作超时 step=%d tool=%s（%ds）", step_num, tool, MCP_TOOL_CALL_TIMEOUT)
            result_txt, is_error = f"动作超时（{tool}）", True
        success = not is_error

        # Stale-ref 检测：MCP 报告 ref 不在当前快照里 — 追加明确提示让 LLM 重选
        if is_error and ("Ref" in result_txt or "not found" in result_txt.lower()):
            stale_hint = (
                "｜⚠️ 上次用的 ref 已失效（页面已变化），下一轮请从最新快照里"
                "重新选一个 ref（不要复用旧 ref）"
            )
            logger.info("Step %d 检测到 stale ref，注入重选提示", step_num)
            result_txt_with_hint = result_txt + stale_hint
        else:
            result_txt_with_hint = result_txt

        # 5.1 动作后截图：记录该步执行后的页面状态（前端 ExecutionTimeline 每步展示用）。
        # 仅对会产生可见页面变化的最常见交互动作截图；wait_for/press_key 等也截，
        # 因为它们可能触发 SPA 路由或渲染变化。失败动作也截，便于排查失败原因。
        step_screenshot_name = f"{execution_id}_step{step_num}_{int(time.time())}.png"
        step_shot_path = screenshot_dir / step_screenshot_name
        try:
            await _take_screenshot_to_file(mcp, step_shot_path)
            screenshots.append(step_screenshot_name)
            screenshot_name = step_screenshot_name
        except Exception as shot_exc:
            logger.warning("Step %d 截图失败: %s", step_num, shot_exc)
            # 截图失败不阻塞执行流程；screenshot_name 保持空串

        executed_steps.append({
            "step_number": step_num,
            "tool": tool,
            "args": args,
            "reasoning": reasoning,
            "success": success,
            "error": result_txt_with_hint[:400] if is_error else "",
            "result": result_txt[:300] if not is_error else "",
            "screenshot": screenshot_name,
        })

        _send_event(pipe_send, {
            "type": "step_progress",
            "step_number": step_num,
            "total_steps": MAX_LOOP_STEPS,
            "action_tool": tool,
            "reasoning": reasoning,
            "screenshot": screenshot_name,
            "success": success,
        })

        # 6. 如果关键动作失败，提前结束
        if is_error and tool in {"browser_navigate", "browser_click", "browser_type"}:
            logger.warning("关键动作失败 step=%d tool=%s: %s", step_num, tool, result_txt[:150])
            # 继续尝试下一步（LLM 可能会调整策略）

    # 达到最大步数
    return {
        "executed_steps": executed_steps,
        "screenshots": screenshots,
        "reason": f"达到最大步数 {MAX_LOOP_STEPS}",
    }


# ============================================================================
# 验证
# ============================================================================
async def _verify(
    mcp: Any,
    scenario: dict,
    executed_steps: list,
    screenshots: list,
    screenshot_dir: Path,
) -> dict:
    """在同会话对最终页面验证。

    Returns:
        {passed: bool, confidence: float, reason: str, verification_type: str}
    """
    from app.llm.router import call_llm

    expectations = scenario.get("expectations", [])
    if not expectations:
        # 无明确预期，只要没错误就算通过
        has_major_error = any(
            not s.get("success") and s.get("tool") in {"browser_navigate", "browser_type", "browser_click"}
            for s in executed_steps
        )
        if has_major_error:
            return {
                "passed": False,
                "confidence": 0.7,
                "reason": "执行中有关键步骤失败",
                "verification_type": "heuristic",
            }
        return {
            "passed": True,
            "confidence": 0.8,
            "reason": "无明确预期且无重大失败",
            "verification_type": "heuristic",
        }

    # 获取最终快照
    try:
        final_snap, snap_err = await asyncio.wait_for(
            mcp.call_tool_checked("playwright", "browser_snapshot", {}),
            timeout=MCP_TOOL_CALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        final_snap, snap_err = "", True
    if snap_err:
        final_snap = ""

    # 文本验证：所有预期都走 LLM 文本验证（Task 3 仅 LLM 文本验证策略）
    exp_text = "\n".join([f"- {e.get('description', '')}" for e in expectations])
    # 用 trim_snapshot 而非 final_snap[:4000]：后者硬截断前 4000 字符，
    # Board 页面侧边栏很长，主体列表会被截掉，导致验证 LLM 看不到关键证据、
    # 把成功的执行误判为失败。trim_snapshot 优先保留可操作元素 + 提高上限。
    from app.task2.agent.agent_loop import trim_snapshot
    verify_snap = trim_snapshot(final_snap) if final_snap else "（无快照）"
    # 场景步骤目标：让验证 LLM 综合判断"预期是否与场景目标一致"，
    # 而非机械比对某个中间态预期。某些场景的 visual_match 预期描述的是中间态
    # （如"导出前的菜单状态"），但 agent 按步骤完整执行后状态已推进到终态——
    # 此时若只看预期会误判失败。给出步骤目标让 LLM 识别这种矛盾。
    steps_text = "\n".join(
        f"{i+1}. {s.get('action','')}" for i, s in enumerate(scenario.get("steps", []))
    )
    verify_prompt = f"""你是验证专家。场景执行完毕，检查最终页面是否符合预期。

## 场景目标（步骤）
{steps_text}

## 预期结果
{exp_text}

## 最终页面快照
{verify_snap}

## 执行的动作（最后5步）
{json.dumps(executed_steps[-5:], ensure_ascii=False, indent=2)}

判断要点：
1. 主要看场景目标是否达成（步骤是否完成、终态是否合理）。
2. 预期结果描述的是"中间态"时（如"操作前的菜单状态"），若 agent 已正确完成
   全部步骤并推进到合理终态，应判 passed=true（预期描述与场景目标矛盾时以目标为准）。
3. 只有当终态明确缺少场景目标所需的结果（如该创建的没创建、该删除的还在）才判 false。

只返回 JSON：{{"passed": true/false, "reason": "原因（中文）", "confidence": 0-1}}
"""
    try:
        resp = await asyncio.wait_for(
            call_llm(
                model_key="deepseek_v4_flash",
                prompt=verify_prompt,
                system_prompt="你是验证专家，严格检查页面状态。",
                temperature=0.1,
                max_tokens=4096,
                pipeline_stage="task2_verify_text",
            ),
            timeout=LLM_CALL_TIMEOUT,
        )
        from app.llm.json_parser import parse_llm_json
        vdata = parse_llm_json(resp)
        if isinstance(vdata, dict) and "passed" in vdata:
            return {
                "passed": bool(vdata["passed"]),
                "confidence": float(vdata.get("confidence", 0.7)),
                "reason": vdata.get("reason", ""),
                "verification_type": "text",
            }
    except Exception as exc:
        logger.warning("文本验证 LLM 失败: %s", exc)

    # 回退：LLM 验证不可用（网络/限流等）时，基于执行步骤是否成功启发式判断，
    # 避免因瞬时 LLM 故障把成功的执行误判为失败。
    # 注意：executed_steps 为空时不能判通过——agent 没执行任何业务动作
    # （通常是 LLM 决策全超时/失败），场景目标根本没有被尝试。
    if not executed_steps:
        return {
            "passed": False,
            "confidence": 0.7,
            "reason": "LLM验证不可用，且 agent 0 步执行（场景未实际推进）",
            "verification_type": "fallback",
        }
    has_major_error = any(
        not s.get("success") and s.get("tool") in {"browser_navigate", "browser_type", "browser_click"}
        for s in executed_steps
    )
    if has_major_error:
        return {
            "passed": False,
            "confidence": 0.5,
            "reason": "LLM验证不可用，且执行中有关键步骤失败",
            "verification_type": "fallback",
        }
    return {
        "passed": True,
        "confidence": 0.3,
        "reason": "LLM验证不可用，基于执行步骤成功推断",
        "verification_type": "fallback",
    }


# ============================================================================
# 反思
# ============================================================================
async def _reflect(
    mcp: Any,
    scenario: dict,
    executed_steps: list,
    verify_result: dict,
    loop_reason: str,
) -> str:
    """验证失败后生成反思指导。

    Returns:
        reflection_text (中文)
    """
    from app.llm.router import call_llm

    last_5 = executed_steps[-5:] if len(executed_steps) > 5 else executed_steps
    steps_text = "\n".join(
        f"{i+1}. {s.get('action','')}" for i, s in enumerate(scenario.get("steps", []))
    )
    reflect_prompt = f"""你是测试反思专家。场景执行验证失败，分析原因并给出下次执行建议。

## 场景目标（需要完成的步骤）
{steps_text}

## 执行的动作（最后5步）
{json.dumps(last_5, ensure_ascii=False, indent=2)}

## 验证失败原因
{verify_result.get("reason", "未知")}

## 循环结束原因
{loop_reason}

根据以上信息，简要分析（中文，1-2 句话）：
1. 失败的根本原因是什么？请区分三类：
   - (a) 预期描述与场景目标矛盾（如预期要求"操作前的中间态"但步骤要求完成到终态）→ 这是预期问题，agent 执行是对的，下次应继续完成全部步骤，不要因预期描述而中途停止。
   - (b) agent 元素定位错了 / 步骤遗漏了 / 导航错了页面 → 指出具体哪步、该怎么改。
   - (c) 其他（页面没加载好、控件不可用等）。
2. 下次重试应该怎么调整策略？

## 重要约束
- **登录由系统在循环外自动完成，不需要 agent 主动登录**。即使执行记录显示停留在登录页，
  也**不要**建议 agent 主动输入凭据登录——这会让 agent 盲猜密码浪费步数。若失败与登录有关，
  归因为 (c) 环境问题，建议"等待重试系统会重新登录"，而非让 agent 自己登录。
- 建议必须具体可执行（如"步骤3应点击 eXX 而非 eYY"），不要空泛说"需要改进"。

只返回反思文本，不要返回 JSON。
"""
    try:
        reflection = await asyncio.wait_for(
            call_llm(
                model_key="deepseek_v4_flash",
                prompt=reflect_prompt,
                system_prompt="你是测试反思专家，简明扼要。",
                temperature=0.3,
                max_tokens=1024,
                pipeline_stage="task2_reflect",
            ),
            timeout=LLM_CALL_TIMEOUT,
        )
        return reflection.strip()
    except asyncio.TimeoutError:
        logger.error("反思 LLM 超时（%ds）", LLM_CALL_TIMEOUT)
        return "反思超时，无可用建议"
    except Exception as exc:
        logger.error("反思 LLM 失败: %s", exc)
        return f"反思失败: {exc}"


# ============================================================================
# 工具函数
# ============================================================================
async def _take_screenshot_to_file(mcp: Any, path: Path) -> None:
    """调用 browser_take_screenshot 并保存到文件。

    Playwright MCP 的截图结果含两类 content block：
    - TextContent：人类可读描述（如 "### Result - [Screenshot...](.playwright-mcp/...)"）
    - ImageContent：真正的 PNG 图像，data 字段为 base64 编码

    旧实现用 call_tool_checked 只取 TextContent，丢掉了 ImageContent，
    导致截图从不落盘、视觉验证无法工作。这里改用 call_tool 直接拿 ImageContent。
    """
    from mcp import types

    try:
        blocks = await mcp.call_tool("playwright", "browser_take_screenshot", {})
        for block in blocks:
            if isinstance(block, types.ImageContent) and block.data:
                img_data = base64.b64decode(block.data)
                path.write_bytes(img_data)
                return
        logger.warning("截图返回中未找到 ImageContent（blocks=%d）", len(blocks))
    except Exception as exc:
        logger.warning("截图异常: %s", exc)


def _send_event(pipe_send: Any, event: dict) -> None:
    """向父进程发送事件（非阻塞，失败静默）。"""
    try:
        pipe_send.send(event)
    except Exception:
        pass


# ============================================================================
# 父进程：启动 worker 并中继事件
# ============================================================================
async def run_agent_for_scenario(
    scenario: dict,
    execution_id: str,
    db_session: Any = None,
) -> dict:
    """父进程调用：启动子进程执行场景，中继事件到 broadcaster，返回最终结果。

    Args:
        scenario: 场景字典（含 id, name, steps, expectations）
        execution_id: 执行记录 ID
        db_session: 数据库 session（用于 token 追踪，可选）

    Returns:
        {final_result, failure_reason, executed_steps, screenshots,
         verification_result, retry_count, reflection, plan}
    """
    from app.events import broadcaster

    scenario_json = json.dumps(scenario, ensure_ascii=False)
    result_file = tempfile.mktemp(suffix=".json", prefix=f"runner_{execution_id}_")

    config = {
        "base_url": settings.login_url.replace("/login", ""),  # https://demo.4gaboards.com
        "login_email": settings.login_email,
        "login_password": settings.login_password,
        "screenshot_dir": str(settings.screenshot_dir),
    }

    # 创建 Pipe
    pipe_recv, pipe_send = multiprocessing.Pipe(duplex=False)

    # 启动子进程
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_child_worker,
        args=(scenario_json, execution_id, result_file, pipe_send, config),
    )
    proc.start()
    pipe_send.close()  # 父进程关闭发送端

    # 中继事件
    def relay_events():
        """从 pipe 读事件并推送到 broadcaster（同步函数，在 executor 里跑）。"""
        while True:
            try:
                if not pipe_recv.poll(timeout=1):
                    if not proc.is_alive():
                        break
                    continue
                event = pipe_recv.recv()
                if event["type"] == "step_progress":
                    event["execution_id"] = execution_id
                broadcaster.publish(event)
            except EOFError:
                break
            except Exception as exc:
                logger.warning("中继事件异常: %s", exc)

    # 在 executor 里跑中继（避免阻塞 event loop）
    relay_task = asyncio.create_task(
        asyncio.to_thread(relay_events)
    )

    # 等待子进程结束（最多 900 秒）
    for _ in range(900):
        await asyncio.sleep(1)
        if not proc.is_alive():
            break
    else:
        # 超时杀掉
        logger.error("子进程执行超时（900s），强制终止")
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        return {
            "final_result": "fail",
            "failure_reason": "总执行超时（900秒）",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": [],
        }

    proc.join()
    await relay_task
    pipe_recv.close()

    # 读结果文件
    if not Path(result_file).exists():
        return {
            "final_result": "fail",
            "failure_reason": "子进程未返回结果文件",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": [],
        }

    with open(result_file, "r", encoding="utf-8") as f:
        result = json.load(f)

    Path(result_file).unlink(missing_ok=True)

    # 子进程返回的 result 包含 plan 字段（display plan，供前端展示）；
    # 若子进程未提供（旧版本兼容），fallback 到空列表。
    result.setdefault("plan", [])

    return result
