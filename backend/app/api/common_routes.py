"""Shared API routes: system status, dashboard stats, screenshots, export."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.db.models import ExecutionRecord, Feature, MutationResult, TestScenario
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["common"])


@router.get("/api/status", summary="System status")
async def get_status(db: Session = Depends(get_session)) -> dict:
    """Return a summary of the system's current state.

    Includes counts, pipeline status with sub-step progress, and
    configuration info. Matches frontend's SystemStatus type.
    """
    from app.api.task1_routes import _crawl_status, _extract_status, _generate_status

    features_count = db.query(Feature).count()
    scenarios_count = db.query(TestScenario).count()
    active_executions = db.query(ExecutionRecord).filter(
        ExecutionRecord.status.in_(["planning", "executing", "verifying", "reflecting"])
    ).count()

    # Check if crawl data exists on disk
    crawled_pages_count = 0
    crawl_dir = str(settings.data_dir / "crawled_docs")
    manifest_path = os.path.join(crawl_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
                # Manifest can be either a list of page dicts or a dict with "pages" key
                if isinstance(manifest, list):
                    crawled_pages_count = len(manifest)
                elif isinstance(manifest, dict):
                    crawled_pages_count = len(manifest.get("pages", []))
        except Exception:
            pass

    # Check if ChromaDB has chunks (use existing instance if available)
    chromadb_chunk_count = 0
    try:
        from app.api.task1_routes import _get_vector_store
        vs = _get_vector_store()
        chromadb_chunk_count = vs.count()
    except Exception:
        # VectorStore not initialized yet — check collection count directly
        if os.path.exists(str(settings.chroma_path)):
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(settings.chroma_path))
                coll = client.get_or_create_collection(
                    name=settings.chroma_collection_name,
                )
                chromadb_chunk_count = coll.count()
            except Exception:
                pass

    return {
        "backend_status": "running",
        "chromadb_status": "connected" if os.path.exists(str(settings.chroma_path)) else "disconnected",
        "active_executions": active_executions,
        "features": features_count,
        "scenarios": scenarios_count,
        "crawled_pages": crawled_pages_count,
        "chromadb_chunks": chromadb_chunk_count,
        "pipeline": {
            "crawl": _crawl_status,
            "extract": _extract_status,
            "generate": _generate_status,
        },
    }


@router.get("/api/dashboard/stats", summary="Dashboard statistics")
async def get_dashboard_stats(db: Session = Depends(get_session)) -> dict:
    """Return dashboard statistics matching frontend's DashboardStats type.

    Calculates: feature_count, scenario_count, execution_count,
    success_rate, mutation_count, mutation_detection_rate.
    """
    feature_count = db.query(Feature).count()
    scenario_count = db.query(TestScenario).count()
    execution_count = db.query(ExecutionRecord).count()
    mutation_count = db.query(MutationResult).count()

    # Success rate: percentage of executions with final_result == "pass"
    passed_count = db.query(ExecutionRecord).filter(
        ExecutionRecord.final_result == "pass"
    ).count()
    success_rate = (passed_count / execution_count * 100) if execution_count > 0 else 0.0

    # Mutation detection rate: percentage of mutations that detected errors
    # A mutation is "detected" when it found an error type other than "none"
    detected_count = db.query(MutationResult).filter(
        MutationResult.detected_error_type != "none",
        MutationResult.detected_error_type != None,
    ).count()
    mutation_detection_rate = (detected_count / mutation_count * 100) if mutation_count > 0 else 0.0

    # Crawl data counts (from manifest file, no heavy model loading)
    crawled_pages_count = 0
    chromadb_chunk_count = 0
    crawl_dir = str(settings.data_dir / "crawled_docs")
    manifest_path = os.path.join(crawl_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
                if isinstance(manifest, list):
                    crawled_pages_count = len(manifest)
                elif isinstance(manifest, dict):
                    crawled_pages_count = len(manifest.get("pages", []))
        except Exception:
            pass

    # ChromaDB chunk count — try existing VectorStore first, fallback to direct client
    try:
        from app.api.task1_routes import _get_vector_store
        vs = _get_vector_store()
        chromadb_chunk_count = vs.count()
    except Exception:
        if os.path.exists(str(settings.chroma_path)):
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(settings.chroma_path))
                coll = client.get_or_create_collection(name=settings.chroma_collection_name)
                chromadb_chunk_count = coll.count()
            except Exception:
                pass

    # Pipeline step status
    from app.api.task1_routes import _crawl_status, _extract_status, _generate_status

    return {
        "feature_count": feature_count,
        "scenario_count": scenario_count,
        "execution_count": execution_count,
        "success_rate": success_rate,
        "mutation_count": mutation_count,
        "mutation_detection_rate": mutation_detection_rate,
        "crawled_pages": crawled_pages_count,
        "chromadb_chunks": chromadb_chunk_count,
        "pipeline": {
            "crawl": _crawl_status,
            "extract": _extract_status,
            "generate": _generate_status,
        },
    }


@router.get("/api/screenshots/{path:path}", summary="Serve screenshot files")
async def serve_screenshot(path: str) -> FileResponse:
    """Serve a screenshot file from the data/screenshots directory.

    Args:
        path: Relative path to the screenshot file within the screenshots dir.
    """
    screenshot_dir = settings.screenshot_dir
    full_path = screenshot_dir / path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenshot '{path}' not found")

    # Security: ensure the path doesn't escape the screenshot directory
    try:
        full_path.resolve().relative_to(screenshot_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside screenshots directory")


@router.get("/api/reference-images/{path:path}", summary="Serve reference image files")
async def serve_reference_image(path: str) -> FileResponse:
    """Serve a reference image from the crawled_docs/images directory.

    Used for visual_match expectations that compare execution screenshots
    against crawled reference images.

    Args:
        path: Relative path to the image file within crawled_docs/images.
    """
    images_dir = settings.data_dir / "crawled_docs" / "images"
    # Strip leading "images/" prefix if present (frontend may send "images/xxx.png")
    clean_path = path
    if clean_path.startswith("images/"):
        clean_path = clean_path[len("images/"):]
    full_path = images_dir / clean_path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Reference image '{clean_path}' not found")

    # Security: ensure the path doesn't escape the images directory
    try:
        full_path.resolve().relative_to(images_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside images directory")

    # Determine media type from file extension
    ext = full_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(str(full_path), media_type=media_type)


@router.get("/api/export", summary="Export all results")
async def export_results(
    format: Optional[str] = Query("json", description="Export format (currently only json supported)"),
    db: Session = Depends(get_session),
) -> dict:
    """Export all features, scenarios, execution records, and mutation results.

    Returns a single JSON object containing all data, suitable for
    download or archival. The format query parameter is accepted but
    currently only JSON format is supported.
    """
    features = db.query(Feature).all()
    scenarios = db.query(TestScenario).all()
    executions = db.query(ExecutionRecord).all()
    mutations = db.query(MutationResult).all()

    return {
        "success": True,
        "data": {
            "features": [
                {
                    "id": f.id,
                    "name": f.name,
                    "category": f.category,
                    "description": f.description,
                    "source_chunks": f.source_chunks,
                }
                for f in features
            ],
            "scenarios": [
                {
                    "id": s.id,
                    "feature_id": s.feature_id,
                    "name": s.name,
                    "steps": json.loads(s.steps_json) if isinstance(s.steps_json, str) else (s.steps_json or []),
                    "expectations": json.loads(s.expectations_json) if isinstance(s.expectations_json, str) else (s.expectations_json or []),
                }
                for s in scenarios
            ],
            "executions": [
                {
                    "id": e.id,
                    "scenario_id": e.scenario_id,
                    "status": e.status,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                    "retry_count": e.retry_count,
                    "final_result": e.final_result,
                    "failure_reason": e.failure_reason,
                    "plan": json.loads(e.plan_json) if isinstance(e.plan_json, str) else (e.plan_json or []),
                    "executed_steps": json.loads(e.executed_steps_json) if isinstance(e.executed_steps_json, str) else (e.executed_steps_json or []),
                    "verification_result": json.loads(e.verification_result_json) if isinstance(e.verification_result_json, str) else (e.verification_result_json or {}),
                    "screenshots": json.loads(e.screenshots_json) if isinstance(e.screenshots_json, str) else (e.screenshots_json or []),
                    "reflection": e.reflection or "",
                }
                for e in executions
            ],
            "mutations": [
                {
                    "id": m.id,
                    "original_scenario_id": m.original_scenario_id,
                    "mutation_type": m.mutation_type,
                    "mutation_description": m.mutation_description,
                    "execution_status": m.execution_status,
                    "detected_error_type": m.detected_error_type,
                    "detected_error_description": m.detected_error_description or "",
                    "mutated_scenario": json.loads(m.mutated_scenario_json) if isinstance(m.mutated_scenario_json, str) else (m.mutated_scenario_json or {}),
                }
                for m in mutations
            ],
        },
    }