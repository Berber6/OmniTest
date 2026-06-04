"""Settings and token usage API endpoints.

Provides runtime configuration management (CRUD for dynamic settings)
and token usage queries with cost estimates.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.config_store import ConfigStore, DYNAMIC_SETTINGS
from app.db.database import get_session
from app.db.models import TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Configuration endpoints
# ---------------------------------------------------------------------------

@router.get("/", summary="Get all settings")
async def get_settings() -> dict:
    """Return all settings (dynamic + static), with secrets masked."""
    settings = ConfigStore.get_all_settings()
    return {
        "success": True,
        "data": settings,
        "total": len(settings),
    }


@router.put("/{key}", summary="Update a dynamic setting")
async def update_setting(key: str, value: str) -> dict:
    """Update a dynamic setting value. Static settings return 403."""
    try:
        setting = ConfigStore.set_setting(key, value)
        # If the key is a model setting, also update the LLM router's MODEL_MAP
        if key in ("llm_model_generation", "llm_model_reasoning", "llm_model_vision"):
            _update_llm_router_model(key, value)
        return {
            "success": True,
            "data": {
                "key": setting.key,
                "value": setting.value if not setting.is_secret else (
                    setting.value[:2] + "****" + setting.value[-2:] if len(setting.value) > 6 else "****"
                ),
                "category": setting.category,
                "is_secret": setting.is_secret,
                "description": setting.description,
            },
            "message": f"Setting '{key}' updated successfully",
        }
    except ValueError as exc:
        raise HTTPException(status_code=403 if "static" in str(exc) else 400, detail=str(exc))


@router.get("/models", summary="Get available LLM models")
async def get_available_models() -> dict:
    """Return current model assignments, fallback chains, and available options."""
    from app.llm.router import MODEL_MAP, FALLBACK_MAP

    model_config = ConfigStore.get_model_config()

    return {
        "success": True,
        "data": {
            "current": model_config,
            "fallbacks": FALLBACK_MAP,
            "available_models": {k: v["model"] for k, v in MODEL_MAP.items()},
        },
    }


def _update_llm_router_model(key: str, value: str) -> None:
    """Update the LLM router's MODEL_MAP when a model setting changes."""
    from app.llm.router import MODEL_MAP, API_BASE_URL, _get_effective_api_key

    role_to_model_key = {
        "llm_model_generation": "deepseek_v4_flash",
        "llm_model_reasoning": "glm_5_1",
        "llm_model_vision": "qwen3_vl",
    }
    mk = role_to_model_key.get(key)
    if mk and mk in MODEL_MAP:
        effective_api_key = _get_effective_api_key()
        MODEL_MAP[mk] = {
            "model": value,
            "api_base": API_BASE_URL,
            "api_key": effective_api_key,
        }
        logger.info(f"Updated MODEL_MAP['{mk}'] to model='{value}'")


# ---------------------------------------------------------------------------
# Token usage endpoints
# ---------------------------------------------------------------------------

@router.get("/token-usage/summary", summary="Get token usage summary")
async def get_token_usage_summary(
    stage: Optional[str] = Query(None, description="Filter by pipeline stage"),
    model: Optional[str] = Query(None, description="Filter by model key"),
    days: int = Query(30, description="Last N days"),
    db: Session = Depends(get_session),
) -> dict:
    """Return aggregated token usage with cost estimates."""
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(TokenUsage).where(TokenUsage.timestamp >= cutoff)
    if stage:
        query = query.where(TokenUsage.pipeline_stage == stage)
    if model:
        query = query.where(TokenUsage.model_key == model)

    rows = db.execute(query).scalars().all()

    total_tokens = sum(r.total_tokens for r in rows)
    total_prompt = sum(r.prompt_tokens for r in rows)
    total_completion = sum(r.completion_tokens for r in rows)
    total_cost = sum(r.cost_estimate for r in rows)
    currency = rows[0].currency if rows else ConfigStore.get_currency()

    # Group by model
    per_model: dict[str, dict] = {}
    for r in rows:
        if r.model_key not in per_model:
            per_model[r.model_key] = {"tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "model_name": r.model_name, "call_count": 0}
        per_model[r.model_key]["tokens"] += r.total_tokens
        per_model[r.model_key]["prompt_tokens"] += r.prompt_tokens
        per_model[r.model_key]["completion_tokens"] += r.completion_tokens
        per_model[r.model_key]["cost"] += r.cost_estimate
        per_model[r.model_key]["call_count"] += 1

    # Group by stage
    per_stage: dict[str, dict] = {}
    for r in rows:
        if r.pipeline_stage not in per_stage:
            per_stage[r.pipeline_stage] = {"tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "call_count": 0}
        per_stage[r.pipeline_stage]["tokens"] += r.total_tokens
        per_stage[r.pipeline_stage]["prompt_tokens"] += r.prompt_tokens
        per_stage[r.pipeline_stage]["completion_tokens"] += r.completion_tokens
        per_stage[r.pipeline_stage]["cost"] += r.cost_estimate
        per_stage[r.pipeline_stage]["call_count"] += 1

    return {
        "success": True,
        "data": {
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cost": round(total_cost, 4),
            "currency": currency,
            "call_count": len(rows),
            "per_model": per_model,
            "per_stage": per_stage,
            "period_days": days,
        },
    }


@router.get("/token-usage/detail", summary="Get detailed token usage records (paginated)")
async def get_token_usage_detail(
    stage: Optional[str] = Query(None, description="Filter by pipeline stage"),
    model: Optional[str] = Query(None, description="Filter by model key"),
    search: Optional[str] = Query(None, description="Search by model name or stage"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated token usage records."""
    query = select(TokenUsage).order_by(TokenUsage.timestamp.desc())
    if stage:
        query = query.where(TokenUsage.pipeline_stage == stage)
    if model:
        query = query.where(TokenUsage.model_key == model)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (TokenUsage.model_name.ilike(search_term)) | (TokenUsage.pipeline_stage.ilike(search_term))
        )

    # Count total
    count_query = select(func.count()).select_from(TokenUsage)
    if stage:
        count_query = count_query.where(TokenUsage.pipeline_stage == stage)
    if model:
        count_query = count_query.where(TokenUsage.model_key == model)
    if search:
        count_query = count_query.where(
            (TokenUsage.model_name.ilike(search_term)) | (TokenUsage.pipeline_stage.ilike(search_term))
        )
    total = db.execute(count_query).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.execute(query.offset(offset).limit(page_size)).scalars().all()

    return {
        "success": True,
        "items": [
            {
                "id": r.id,
                "model_key": r.model_key,
                "model_name": r.model_name,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "pipeline_stage": r.pipeline_stage,
                "cost_estimate": r.cost_estimate,
                "currency": r.currency,
                "duration_seconds": r.duration_seconds,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }