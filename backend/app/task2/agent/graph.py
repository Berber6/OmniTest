"""Agent execution entry point — 已重写为直接调用 runner.py（单 worker）。

原 LangGraph 架构（PLAN→EXECUTE→VERIFY→REFLECT）已废弃，改为：
- 单子进程 + 常驻浏览器会话
- 确定性登录 + 观察→决策→执行循环 + 同会话验证 + 反思重试

保留此文件作为 run_agent 入口（task2_routes.py 调用），向后兼容。
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from app.events import broadcaster

logger = logging.getLogger(__name__)


async def run_agent(scenario: dict, execution_id: str, db) -> dict:
    """执行测试场景的统一入口（已重写为调用 runner.py）。

    Args:
        scenario: 测试场景字典 {id, name, steps, expectations}
        execution_id: 执行记录 ID
        db: SQLAlchemy session（用于 token 追踪）

    Returns:
        {final_result, failure_reason, executed_steps, screenshots,
         verification_result, retry_count, reflection, plan}
    """
    from app.task2.agent.runner import run_agent_for_scenario

    logger.info(
        "开始执行场景: scenario_id=%s, execution_id=%s",
        scenario.get("id", "?"),
        execution_id,
    )

    # 推送启动事件
    broadcaster.publish({
        "type": "execution_started",
        "execution_id": execution_id,
        "scenario_id": scenario.get("id", ""),
    })

    try:
        # 调用新 runner（单 worker + 常驻会话）
        result = await run_agent_for_scenario(
            scenario=scenario,
            execution_id=execution_id,
            db_session=db,
        )

        # 推送完成事件
        broadcaster.publish({
            "type": "execution_completed",
            "execution_id": execution_id,
            "final_result": result.get("final_result", "fail"),
        })

        logger.info(
            "场景执行完成: execution_id=%s, result=%s, retries=%d",
            execution_id,
            result.get("final_result", "unknown"),
            result.get("retry_count", 0),
        )

        return result

    except asyncio.TimeoutError:
        logger.error("场景执行总超时: execution_id=%s", execution_id)
        result = {
            "final_result": "fail",
            "failure_reason": "总执行超时（900秒）",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": [],
        }
        broadcaster.publish({
            "type": "execution_completed",
            "execution_id": execution_id,
            "final_result": "fail",
        })
        return result
    except asyncio.CancelledError:
        logger.error("场景执行被取消: execution_id=%s", execution_id)
        result = {
            "final_result": "fail",
            "failure_reason": "执行被取消",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": [],
        }
        broadcaster.publish({
            "type": "execution_completed",
            "execution_id": execution_id,
            "final_result": "fail",
        })
        return result
    except Exception as exc:
        logger.exception("场景执行异常: execution_id=%s: %s", execution_id, exc)
        result = {
            "final_result": "fail",
            "failure_reason": f"执行异常: {exc}",
            "executed_steps": [],
            "screenshots": [],
            "verification_result": {},
            "retry_count": 0,
            "plan": [],
        }
        broadcaster.publish({
            "type": "execution_completed",
            "execution_id": execution_id,
            "final_result": "fail",
        })
        return result
    finally:
        pass  # db session 由调用者管理
