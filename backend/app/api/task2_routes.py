"""Task2 API routes: execution, mutation."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.db.models import ExecutionRecord, MutationResult as MutationResultORM, TestScenario as TestScenarioORM
from app.task2.models import (
    ExecutionRequest,
    MutationRequest,
    AGENT_STATUS_VALUES,
)
from app.task2.agent.graph import run_agent
from app.task2.mutation import generate_mutations, run_mutation_test
from app.config import settings
from app.events import broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task2", tags=["task2"])

# 限制同时执行的 agent 数量（每个 agent 会启动浏览器子进程）
MAX_CONCURRENT_EXECUTIONS = 3
_execution_semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXECUTIONS)


# ---------------------------------------------------------------------------
# Execution endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/execute/{scenario_id}",
    summary="Execute a test scenario",
)
async def execute_scenario(
    scenario_id: str,
    headless: bool = Query(True, description="Run browser in headless mode"),
    db: Session = Depends(get_session),
) -> dict:
    """Launch the LangGraph execution agent for the given scenario.

    Returns the execution record immediately with "executing" status.
    The agent runs in a background asyncio task — frontend uses
    WebSocket or polling to track progress.
    """
    scenario = db.query(TestScenarioORM).filter(TestScenarioORM.id == scenario_id).first()
    if not scenario:
        return {"success": False, "error": f"Scenario '{scenario_id}' not found"}

    # Generate date-time based execution ID with uniqueness suffix (e.g. 20260526-143001-1)
    now = datetime.now(timezone.utc)
    base_id = now.strftime("%Y%m%d-%H%M%S")
    # Ensure uniqueness: if same-second conflict, append sequence number
    existing = db.query(ExecutionRecord).filter(ExecutionRecord.id.startswith(base_id)).count()
    execution_id = f"{base_id}-{existing + 1}" if existing > 0 else base_id
    record = ExecutionRecord(
        id=execution_id,
        scenario_id=scenario_id,
        status="executing",
        started_at=datetime.now(timezone.utc),
        plan_json=[],
        executed_steps_json=[],
        verification_result_json={},
        screenshots_json=[],
    )
    db.add(record)
    db.commit()

    # Publish execution_started event for WebSocket push
    broadcaster.publish({
        "type": "execution_started",
        "execution_id": execution_id,
        "scenario_id": scenario_id,
    })

    # Build scenario dict for the agent
    scenario_dict = {
        "id": scenario.id,
        "name": scenario.name,
        "feature_id": scenario.feature_id,
        "url": getattr(scenario, "url", "https://demo.4gaboards.com"),
        "steps": json.loads(scenario.steps_json) if isinstance(scenario.steps_json, str) else (scenario.steps_json or []),
        "expectations": json.loads(scenario.expectations_json) if isinstance(scenario.expectations_json, str) else (scenario.expectations_json or []),
    }

    # Launch agent in background — API returns immediately
    async def _run_agent_background():
        """Run the agent and update the DB record when done.
        Uses semaphore to limit concurrent browser processes."""
        from app.db.database import SessionLocal

        # 等待信号量许可 — 超过并发上限时排队等待
        async with _execution_semaphore:
            logger.info("Agent execution starting: id=%s (semaphore acquired)", execution_id)
            bg_db = SessionLocal()
            try:
                result_state = await run_agent(scenario_dict, execution_id, bg_db)

                final_result = result_state.get("final_result", "fail") or "fail"
                bg_record = bg_db.query(ExecutionRecord).filter(ExecutionRecord.id == execution_id).first()
                if bg_record:
                    if final_result == "pass":
                        bg_record.status = "completed"
                    else:
                        bg_record.status = "failed"

                    bg_record.completed_at = datetime.now(timezone.utc)
                    bg_record.retry_count = result_state.get("retry_count", 0)
                    bg_record.final_result = final_result
                    bg_record.failure_reason = result_state.get("failure_reason", "")

                    bg_record.plan_json = result_state.get("plan", [])
                    bg_record.executed_steps_json = result_state.get("executed_steps", [])
                    bg_record.verification_result_json = result_state.get("verification_result", {})
                    bg_record.screenshots_json = result_state.get("screenshots", [])
                    bg_record.reflection = result_state.get("reflection", "")

                    bg_db.commit()
                    logger.info("Background agent execution completed: id=%s, result=%s", execution_id, final_result)

                    # Publish execution_completed event for WebSocket push
                    broadcaster.publish({
                        "type": "execution_completed",
                        "execution_id": execution_id,
                        "final_result": final_result,
                        "failure_reason": result_state.get("failure_reason", ""),
                    })

            except Exception as exc:
                logger.error(f"Background agent execution failed: {exc}")
                bg_record = bg_db.query(ExecutionRecord).filter(ExecutionRecord.id == execution_id).first()
                if bg_record:
                    bg_record.status = "failed"
                    bg_record.completed_at = datetime.now(timezone.utc)
                    bg_record.final_result = "fail"
                    bg_record.failure_reason = str(exc)
                    bg_db.commit()

                    # Publish execution_completed event for WebSocket push
                    broadcaster.publish({
                        "type": "execution_completed",
                        "execution_id": execution_id,
                        "final_result": "fail",
                        "failure_reason": str(exc),
                    })
            finally:
                bg_db.close()
                logger.info("Agent execution semaphore released: id=%s", execution_id)

    asyncio.create_task(_run_agent_background())

    return {
        "success": True,
        "data": _execution_record_to_dict(record),
        "message": "Execution started",
    }


@router.delete(
    "/executions/{execution_id}",
    summary="Delete an execution record",
)
async def delete_execution(
    execution_id: str,
    db: Session = Depends(get_session),
) -> dict:
    """Delete a completed/failed execution record and its associated screenshots.

    Returns ApiResponse<null>.
    """
    record = db.query(ExecutionRecord).filter(ExecutionRecord.id == execution_id).first()
    if not record:
        return {"success": False, "error": f"Execution '{execution_id}' not found"}

    if record.status in ("planning", "executing", "verifying", "reflecting"):
        return {"success": False, "error": f"Execution '{execution_id}' is still running, cancel it first"}

    # 删除关联的截图文件
    import base64
    screenshot_dir = settings.screenshot_dir
    if screenshot_dir.exists():
        # 删除旧格式的截图文件（{execution_id}_*.png）
        for f in screenshot_dir.glob(f"{execution_id}_*.png"):
            try:
                f.unlink()
                logger.info("删除截图文件: %s", f.name)
            except Exception as exc:
                logger.warning("删除截图文件失败 %s: %s", f.name, exc)
        # 删除新格式的截图文件（从记录的 screenshots_json 中获取文件名）
        screenshots = record.screenshots_json
        if isinstance(screenshots, str):
            try:
                screenshots = json.loads(screenshots)
            except Exception:
                screenshots = []
        for s in (screenshots or []):
            if isinstance(s, str) and (s.endswith(".png") or s.endswith(".jpg")) and not s.startswith("http"):
                # 新格式：文件路径引用 — 删除磁盘文件
                filepath = screenshot_dir / s
                if filepath.exists():
                    try:
                        filepath.unlink()
                        logger.info("删除截图文件(新格式): %s", s)
                    except Exception as exc:
                        logger.warning("删除截图文件失败 %s: %s", s, exc)

    # 删除数据库记录
    db.delete(record)
    db.commit()

    return {"success": True, "data": None, "message": "Execution deleted"}


@router.post(
    "/executions/{execution_id}/cancel",
    summary="Cancel an execution",
)
async def cancel_execution(
    execution_id: str,
    db: Session = Depends(get_session),
) -> dict:
    """Cancel a running execution by marking it as 'failed'.

    Returns ApiResponse<null>.
    """
    record = db.query(ExecutionRecord).filter(ExecutionRecord.id == execution_id).first()
    if not record:
        return {"success": False, "error": f"Execution '{execution_id}' not found"}

    if record.status in ("completed", "failed"):
        return {"success": False, "error": f"Execution '{execution_id}' is already {record.status}"}

    record.status = "failed"
    record.final_result = "fail"
    record.failure_reason = "Cancelled by user"
    record.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "data": None, "message": "Execution cancelled"}


@router.get("/executions", summary="List execution records (paginated)")
async def list_executions(
    scenario_id: Optional[str] = Query(None, description="Filter by scenario ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by scenario name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated execution records, filtered and sorted by started_at DESC."""
    from sqlalchemy.orm import joinedload
    query = db.query(ExecutionRecord).options(joinedload(ExecutionRecord.scenario))
    if scenario_id:
        query = query.filter(ExecutionRecord.scenario_id == scenario_id)
    if status:
        query = query.filter(ExecutionRecord.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(ExecutionRecord.scenario.has(TestScenarioORM.name.ilike(search_term)))
    query = query.order_by(ExecutionRecord.started_at.desc())

    total = query.count()
    offset = (page - 1) * page_size
    records = query.offset(offset).limit(page_size).all()

    return {
        "items": [_execution_record_to_dict(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/executions/{id}", response_model=dict, summary="Get an execution record")
async def get_execution(id: str, db: Session = Depends(get_session)) -> dict:
    """Return a single execution record by its ID."""
    from sqlalchemy.orm import joinedload
    record = db.query(ExecutionRecord).options(
        joinedload(ExecutionRecord.scenario)
    ).filter(ExecutionRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution record '{id}' not found")
    return _execution_record_to_dict(record)


def _execution_record_to_dict(record: ExecutionRecord) -> dict:
    """Convert an ExecutionRecord ORM object to the dict format frontend expects.

    Frontend expects: id, scenario_id, status, plan, executed_steps,
    verification_result, screenshots, retry_count, reflection,
    final_result, failure_reason, started_at, completed_at

    Screenshots may be stored as:
    1. File paths (new format: e.g. "step_0_1234567890_0.png") — saved as PNG files
       by the execution engine, just referenced by filename
    2. Base64 strings (legacy format: starting with "iVBOR") — decoded and saved as PNG files
    3. Data URIs (legacy format: "data:image/png;base64,...") — decoded and saved
    4. Absolute paths or URLs — used directly

    Frontend fetches images via /api/screenshots/{path}.
    """
    import base64

    # Parse JSON columns that may be stored as strings
    plan = record.plan_json
    if isinstance(plan, str):
        plan = json.loads(plan)

    executed_steps = record.executed_steps_json
    if isinstance(executed_steps, str):
        executed_steps = json.loads(executed_steps)

    verification_result = record.verification_result_json
    if isinstance(verification_result, str):
        verification_result = json.loads(verification_result)

    screenshots = record.screenshots_json
    if isinstance(screenshots, str):
        screenshots = json.loads(screenshots)

    # 将截图数据转换为前端可访问的文件路径
    # 前端通过 /api/screenshots/{path} 获取图片
    # 新格式：文件名引用（由执行引擎保存的 PNG 文件）
    # 旧格式：base64 字符串需要解码并保存为文件
    screenshot_dir = settings.screenshot_dir
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    screenshot_paths = []
    img_count = 0  # 只对真正的图片数据编号
    for idx, s in enumerate(screenshots or []):
        if isinstance(s, str) and s.startswith("iVBOR"):
            # 旧格式：PNG base64 数据 — 保存为文件
            filename = f"{record.id}_{img_count}.png"
            filepath = screenshot_dir / filename
            try:
                img_bytes = base64.b64decode(s)
                filepath.write_bytes(img_bytes)
                screenshot_paths.append(filename)
                img_count += 1
                logger.info("截图保存成功: %s (%d bytes)", filename, len(img_bytes))
            except Exception as exc:
                logger.warning("截图保存失败 idx=%d: %s", idx, exc)
                screenshot_paths.append("")  # 保存失败时用空字符串
        elif isinstance(s, str) and s.startswith("data:image"):
            # 旧格式：data URI 格式的 base64 图片
            filename = f"{record.id}_{img_count}.png"
            filepath = screenshot_dir / filename
            try:
                b64_data = s.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_data)
                filepath.write_bytes(img_bytes)
                screenshot_paths.append(filename)
                img_count += 1
                logger.info("截图保存成功(data URI): %s (%d bytes)", filename, len(img_bytes))
            except Exception as exc:
                logger.warning("截图保存失败(data URI) idx=%d: %s", idx, exc)
                screenshot_paths.append("")
        elif isinstance(s, str) and (s.startswith("/") or s.startswith("http") or s.endswith(".png") or s.endswith(".jpg")):
            # 新格式：文件路径引用（由执行引擎保存的文件）或 URL — 直接使用
            screenshot_paths.append(s)
            img_count += 1
        else:
            # 文本结果或其他非图片内容 — 跳过
            screenshot_paths.append("")

    # 为每个执行步骤关联截图路径
    # 新格式：执行引擎在每个 step_result 的 "screenshot" 字段和
    # page_state["screenshot"] 中直接存储文件名路径，无需顺序分配
    # 旧格式回退：仍然按顺序从 screenshots 列表分配
    valid_paths = [p for p in screenshot_paths if p]  # 过滤掉空字符串
    path_idx = 0
    last_assigned_path = None  # 上一个被分配的截图路径
    for step in (executed_steps or []):
        if not isinstance(step, dict):
            continue

        # 新格式：step_result 已包含 screenshot 文件路径
        step_screenshot = step.get("screenshot", "")
        if step_screenshot and isinstance(step_screenshot, str) and step_screenshot.endswith(".png"):
            step["screenshot_path"] = step_screenshot
            if isinstance(step.get("page_state"), dict) and step.get("page_state", {}).get("screenshot"):
                step["page_state"]["screenshot_path"] = step["page_state"]["screenshot"]
            last_assigned_path = step_screenshot
            continue

        # page_state 中也可能有 screenshot 文件路径
        page_state_screenshot = ""
        if isinstance(step.get("page_state"), dict):
            page_state_screenshot = step.get("page_state", {}).get("screenshot", "")
        if page_state_screenshot and isinstance(page_state_screenshot, str) and page_state_screenshot.endswith(".png"):
            step["screenshot_path"] = page_state_screenshot
            step["page_state"]["screenshot_path"] = page_state_screenshot
            last_assigned_path = page_state_screenshot
            continue

        # 旧格式回退：从 screenshots 列表顺序分配
        tool_name = step.get("action", {}).get("tool", "") if isinstance(step.get("action"), dict) else ""
        # 直接产生截图的步骤：交互操作和专门截图
        if tool_name in ("browser_take_screenshot", "browser_click", "browser_type",
                         "browser_navigate", "browser_select_option", "browser_hover",
                         "browser_press_key"):
            if path_idx < len(valid_paths):
                step["screenshot_path"] = valid_paths[path_idx]
                if isinstance(step.get("page_state"), dict):
                    step["page_state"]["screenshot_path"] = valid_paths[path_idx]
                last_assigned_path = valid_paths[path_idx]
                path_idx += 1
        else:
            # 其他步骤（snapshot, wait_for 等）继承上一个截图
            # 这样用户可以在每个步骤都看到当时的页面状态
            if last_assigned_path:
                step["screenshot_path"] = last_assigned_path

    started_at_iso = None
    if record.started_at:
        dt = record.started_at
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        started_at_iso = dt.isoformat()

    completed_at_iso = None
    if record.completed_at:
        dt = record.completed_at
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        completed_at_iso = dt.isoformat()

    # 计算执行时长（秒）
    duration_seconds = None
    if record.started_at and record.completed_at:
        delta = record.completed_at - record.started_at
        duration_seconds = int(delta.total_seconds())

    return {
        "id": record.id,
        "scenario_id": record.scenario_id,
        "scenario_name": record.scenario.name if record.scenario else "",
        "status": record.status,
        "plan": plan or [],
        "executed_steps": executed_steps or [],
        "verification_result": verification_result or {},
        "screenshots": [p for p in screenshot_paths if p],  # 只返回有效的文件路径
        "retry_count": record.retry_count,
        "reflection": record.reflection or "",
        "final_result": record.final_result or "",
        "failure_reason": record.failure_reason or "",
        "started_at": started_at_iso,
        "completed_at": completed_at_iso,
        "duration_seconds": duration_seconds,
    }


# ---------------------------------------------------------------------------
# Mutation endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/mutation/{scenario_id}",
    summary="Create mutations and run mutation testing",
)
async def create_mutation(
    scenario_id: str,
    request: MutationRequest,
    db: Session = Depends(get_session),
) -> dict:
    """Apply mutations to a scenario and execute each mutation.

    Returns ApiResponse<MutationResult> with full mutation data.
    """
    scenario = db.query(TestScenarioORM).filter(TestScenarioORM.id == scenario_id).first()
    if not scenario:
        return {"success": False, "error": f"Scenario '{scenario_id}' not found"}

    scenario_dict = {
        "id": scenario.id,
        "name": scenario.name,
        "feature_id": scenario.feature_id,
        "url": getattr(scenario, "url", "https://demo.4gaboards.com"),
        "steps": json.loads(scenario.steps_json) if isinstance(scenario.steps_json, str) else (scenario.steps_json or []),
        "expectations": json.loads(scenario.expectations_json) if isinstance(scenario.expectations_json, str) else (scenario.expectations_json or []),
    }

    # Generate mutations (async — uses LLM)
    mutations = await generate_mutations(scenario_dict)

    # Filter to requested mutation type if specified
    if request.mutation_type:
        mutations = [m for m in mutations if m.get("mutation_type", "").startswith(request.mutation_type.replace("_mutation", ""))]

    if not mutations:
        return {"success": False, "error": "No mutations were generated"}

    first_mutation_record = None

    for mutant in mutations[:5]:  # Limit to 5 mutations
        mutation_id = str(uuid.uuid4())

        try:
            result = await run_mutation_test(mutant, run_agent)

            # Create an execution record for the mutant
            now = datetime.now(timezone.utc)
            base_id = now.strftime("%Y%m%d-%H%M%S")
            existing = db.query(ExecutionRecord).filter(ExecutionRecord.id.startswith(base_id)).count()
            exec_id = f"{base_id}-{existing + 1}" if existing > 0 else base_id
            exec_record = ExecutionRecord(
                id=exec_id,
                scenario_id=scenario_id,
                status="completed" if result.execution_passed else "failed",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                retry_count=0,
                final_result="pass" if result.execution_passed else "fail",
                failure_reason=result.agent_failure_reason or "",
                plan_json=result.agent_state.get("plan", []),
                executed_steps_json=result.agent_state.get("executed_steps", []),
                verification_result_json=result.agent_state.get("verification_result", {}),
                screenshots_json=result.agent_state.get("screenshots", []),
                reflection=result.agent_state.get("reflection", ""),
            )
            db.add(exec_record)
            db.flush()

            m_record = MutationResultORM(
                id=mutation_id,
                original_scenario_id=scenario_id,
                mutation_type=result.mutation_type,
                mutation_description=result.mutation_description,
                execution_status="completed" if result.execution_passed else "failed",
                detected_error_type=result.detected_error_type,
                detected_error_description=result.detection_detail,
                mutated_scenario_json=json.dumps(mutant.get("scenario", {})),
                execution_record_id=exec_id,
            )
            db.add(m_record)

            if first_mutation_record is None:
                first_mutation_record = m_record

        except Exception as exc:
            logger.error(f"Mutation test failed: {exc}")
            # Create a failed execution record even for exceptions
            now = datetime.now(timezone.utc)
            base_id = now.strftime("%Y%m%d-%H%M%S")
            existing = db.query(ExecutionRecord).filter(ExecutionRecord.id.startswith(base_id)).count()
            exec_id = f"{base_id}-{existing + 1}" if existing > 0 else base_id
            exec_record = ExecutionRecord(
                id=exec_id,
                scenario_id=scenario_id,
                status="failed",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                retry_count=0,
                final_result="fail",
                failure_reason=str(exc),
                plan_json=[],
                executed_steps_json=[],
                verification_result_json={},
                screenshots_json=[],
            )
            db.add(exec_record)
            db.flush()

            m_record = MutationResultORM(
                id=mutation_id,
                original_scenario_id=scenario_id,
                mutation_type=mutant.get("mutation_type", request.mutation_type),
                mutation_description=mutant.get("mutation_description", ""),
                execution_status="failed",
                detected_error_type="execution_exception",
                detected_error_description=str(exc),
                mutated_scenario_json=json.dumps(mutant.get("scenario", {})),
                execution_record_id=exec_id,
            )
            db.add(m_record)

            if first_mutation_record is None:
                first_mutation_record = m_record

    db.commit()

    if first_mutation_record:
        return {
            "success": True,
            "data": _mutation_result_to_dict(first_mutation_record),
            "message": "Mutation created and executed",
        }
    return {"success": False, "error": "No mutations were successfully created"}


@router.get("/mutations", summary="List mutation results (paginated)")
async def list_mutations(
    original_scenario_id: Optional[str] = Query(None, description="Filter by original scenario"),
    mutation_type: Optional[str] = Query(None, description="Filter by mutation type"),
    detected_error_type: Optional[str] = Query(None, description="Filter by detected error type"),
    search: Optional[str] = Query(None, description="Search by scenario name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated mutation results."""
    query = db.query(MutationResultORM)
    if original_scenario_id:
        query = query.filter(MutationResultORM.original_scenario_id == original_scenario_id)
    if mutation_type:
        query = query.filter(MutationResultORM.mutation_type == mutation_type)
    if detected_error_type:
        query = query.filter(MutationResultORM.detected_error_type == detected_error_type)
    if search:
        search_term = f"%{search}%"
        query = query.filter(MutationResultORM.original_scenario.has(TestScenarioORM.name.ilike(search_term)))

    total = query.count()
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    return {
        "items": [_mutation_result_to_dict(m) for m in results],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/mutations/{id}", response_model=dict, summary="Get a mutation result by ID")
async def get_mutation(id: str, db: Session = Depends(get_session)) -> dict:
    """Return a single mutation result by its ID."""
    result = db.query(MutationResultORM).filter(MutationResultORM.id == id).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"Mutation result '{id}' not found")
    return _mutation_result_to_dict(result)


def _mutation_result_to_dict(m: MutationResultORM) -> dict:
    """Convert a MutationResult ORM object to the dict format frontend expects.

    Frontend expects: id, original_scenario_id, mutation_type,
    mutated_scenario, execution, detected_error_type,
    detected_error_description
    """
    # Parse mutated scenario
    mutated_scenario = m.mutated_scenario_json
    if isinstance(mutated_scenario, str):
        mutated_scenario = json.loads(mutated_scenario)
    if mutated_scenario is None:
        mutated_scenario = {}

    # Get associated execution record if available
    execution = {}
    if m.execution_record_id:
        exec_record = m.execution_record
        if exec_record:
            execution = _execution_record_to_dict(exec_record)

    return {
        "id": m.id,
        "original_scenario_id": m.original_scenario_id,
        "mutation_type": m.mutation_type,
        "mutated_scenario": mutated_scenario,
        "execution": execution,
        "detected_error_type": m.detected_error_type,
        "detected_error_description": m.detected_error_description or "",
    }


# ---------------------------------------------------------------------------
# WebSocket endpoints — redirect to global /ws/executions (event-push)
# ---------------------------------------------------------------------------