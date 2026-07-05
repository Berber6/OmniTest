"""Import/Export API routes for features, scenarios, executions, and bundles.

Export endpoints return versioned JSON envelopes.
Import endpoints accept the same JSON envelopes as request body:
  - Features & Scenarios: replace semantics (clear existing, insert imported)
  - Executions: merge semantics (skip duplicate IDs, insert new)
  - Bundle: import all types in order (features→scenarios→executions→mutations)
"""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_session
from app.db.models import (
    ExecutionRecord,
    Feature as FeatureORM,
    MutationResult as MutationResultORM,
    TestScenario as TestScenarioORM,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/io", tags=["import-export"])

EXPORT_VERSION = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(value: Any) -> Any:
    """Parse a JSON column that may be stored as a string or native type."""
    if isinstance(value, str):
        return json.loads(value)
    return value if value is not None else []


def _serialize_feature(f: FeatureORM) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "category": f.category,
        "description": f.description,
        "source_chunks": _parse_json_field(f.source_chunks),
    }


def _serialize_scenario(s: TestScenarioORM) -> dict:
    return {
        "id": s.id,
        "feature_id": s.feature_id,
        "name": s.name,
        "steps": _parse_json_field(s.steps_json),
        "expectations": _parse_json_field(s.expectations_json),
    }


def _serialize_execution(e: ExecutionRecord, include_screenshots: bool = True) -> dict:
    screenshots = _parse_json_field(e.screenshots_json) if include_screenshots else []
    return {
        "id": e.id,
        "scenario_id": e.scenario_id,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "retry_count": e.retry_count,
        "final_result": e.final_result or "",
        "failure_reason": e.failure_reason or "",
        "plan": _parse_json_field(e.plan_json),
        "executed_steps": _parse_json_field(e.executed_steps_json),
        "verification_result": _parse_json_field(e.verification_result_json),
        "screenshots": screenshots,
        "reflection": e.reflection or "",
    }


def _serialize_mutation(m: MutationResultORM) -> dict:
    return {
        "id": m.id,
        "original_scenario_id": m.original_scenario_id,
        "mutation_type": m.mutation_type,
        "mutation_description": m.mutation_description,
        "execution_status": m.execution_status,
        "detected_error_type": m.detected_error_type,
        "detected_error_description": m.detected_error_description or "",
        "mutated_scenario": _parse_json_field(m.mutated_scenario_json),
        "execution_record_id": m.execution_record_id,
    }


def _save_screenshots_to_disk(execution_id: str, screenshots_json: Any) -> int:
    """Decode base64 screenshots from imported data and write PNG files to disk.

    Returns the number of image files written.
    """
    screenshots = _parse_json_field(screenshots_json)
    if not screenshots:
        return 0

    screenshot_dir = settings.screenshot_dir
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    img_count = 0

    for s in screenshots:
        if isinstance(s, str) and s.startswith("iVBOR"):
            filename = f"{execution_id}_{img_count}.png"
            filepath = screenshot_dir / filename
            try:
                img_bytes = base64.b64decode(s)
                filepath.write_bytes(img_bytes)
                img_count += 1
            except Exception as exc:
                logger.warning("Import: failed to decode screenshot for %s: %s", execution_id, exc)
        elif isinstance(s, str) and s.startswith("data:image"):
            filename = f"{execution_id}_{img_count}.png"
            filepath = screenshot_dir / filename
            try:
                b64_data = s.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_data)
                filepath.write_bytes(img_bytes)
                img_count += 1
            except Exception as exc:
                logger.warning("Import: failed to decode data URI screenshot for %s: %s", execution_id, exc)

    logger.info("Import: saved %d screenshot files for execution %s", img_count, execution_id)
    return img_count


def _validate_import_payload(payload: dict, expected_type: str) -> list[dict]:
    """Validate an import payload's envelope and return the data list.

    Raises HTTPException if invalid.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload: expected a JSON object")

    # Accept either a per-type envelope or a bundle envelope
    if payload.get("type") == "bundle":
        data = payload.get("data", {}).get(expected_type, [])
    elif payload.get("type") == expected_type:
        data = payload.get("data", [])
    else:
        # Also accept raw list (no envelope)
        if isinstance(payload, list):
            data = payload
        else:
            raise HTTPException(400, f"Invalid payload: expected type '{expected_type}' or 'bundle', got '{payload.get('type', 'none')}'")

    if not isinstance(data, list):
        raise HTTPException(400, f"Invalid payload: 'data' must be a list")

    return data


# ---------------------------------------------------------------------------
# Export Endpoints
# ---------------------------------------------------------------------------

@router.get("/export/features", summary="Export all features")
async def export_features(db: Session = Depends(get_session)) -> dict:
    features = db.query(FeatureORM).all()
    return {
        "version": EXPORT_VERSION,
        "type": "features",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(features),
        "data": [_serialize_feature(f) for f in features],
    }


@router.get("/export/scenarios", summary="Export all scenarios")
async def export_scenarios(db: Session = Depends(get_session)) -> dict:
    scenarios = db.query(TestScenarioORM).all()
    return {
        "version": EXPORT_VERSION,
        "type": "scenarios",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(scenarios),
        "data": [_serialize_scenario(s) for s in scenarios],
    }


@router.get("/export/executions", summary="Export all execution records")
async def export_executions(
    include_screenshots: bool = Query(True, description="Include base64 screenshot data in export"),
    db: Session = Depends(get_session),
) -> dict:
    executions = db.query(ExecutionRecord).all()
    return {
        "version": EXPORT_VERSION,
        "type": "executions",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(executions),
        "data": [_serialize_execution(e, include_screenshots) for e in executions],
    }


@router.get("/export/all", summary="Export all data as bundle")
async def export_bundle(
    include_screenshots: bool = Query(True, description="Include base64 screenshot data in export"),
    db: Session = Depends(get_session),
) -> dict:
    features = db.query(FeatureORM).all()
    scenarios = db.query(TestScenarioORM).all()
    executions = db.query(ExecutionRecord).all()
    mutations = db.query(MutationResultORM).all()

    return {
        "version": EXPORT_VERSION,
        "type": "bundle",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "features": len(features),
            "scenarios": len(scenarios),
            "executions": len(executions),
            "mutations": len(mutations),
        },
        "data": {
            "features": [_serialize_feature(f) for f in features],
            "scenarios": [_serialize_scenario(s) for s in scenarios],
            "executions": [_serialize_execution(e, include_screenshots) for e in executions],
            "mutations": [_serialize_mutation(m) for m in mutations],
        },
    }


# ---------------------------------------------------------------------------
# Import Endpoints
# ---------------------------------------------------------------------------

@router.post("/import/features", summary="Import features (replace)")
async def import_features(
    payload: dict,
    db: Session = Depends(get_session),
) -> dict:
    """Import features, replacing all existing ones."""
    data = _validate_import_payload(payload, "features")

    # Validate required fields
    errors = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: must be a dict")
            continue
        for field in ("id", "name", "category", "description"):
            if field not in item or not item[field]:
                errors.append(f"Item {i}: missing required field '{field}'")

    if errors:
        raise HTTPException(400, f"Validation errors: {errors}")

    # Replace: delete all existing, insert imported
    db.query(FeatureORM).delete()
    for item in data:
        record = FeatureORM(
            id=item["id"],
            name=item["name"],
            category=item["category"],
            description=item["description"],
            source_chunks=item.get("source_chunks", []),
        )
        db.add(record)

    db.commit()
    logger.info("Imported %d features (replaced all existing)", len(data))

    return {
        "success": True,
        "imported_count": len(data),
        "message": f"Imported {len(data)} features (replaced all existing)",
    }


@router.post("/import/scenarios", summary="Import scenarios (replace)")
async def import_scenarios(
    payload: dict,
    db: Session = Depends(get_session),
) -> dict:
    """Import scenarios, replacing all existing ones. Validates feature_id FK."""
    data = _validate_import_payload(payload, "scenarios")

    # Validate required fields
    errors = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: must be a dict")
            continue
        for field in ("id", "name", "feature_id"):
            if field not in item or not item[field]:
                errors.append(f"Item {i}: missing required field '{field}'")
        if "steps" not in item or not isinstance(item.get("steps"), list):
            errors.append(f"Item {i}: 'steps' must be a list")
        if "expectations" not in item or not isinstance(item.get("expectations"), list):
            errors.append(f"Item {i}: 'expectations' must be a list")

    if errors:
        raise HTTPException(400, f"Validation errors: {errors}")

    # FK validation: check all referenced feature_ids exist
    existing_feature_ids = {f.id for f in db.query(FeatureORM).all()}
    missing_ids = {item["feature_id"] for item in data if isinstance(item, dict)} - existing_feature_ids
    if missing_ids:
        raise HTTPException(400, f"Referenced feature_ids not found: {sorted(missing_ids)}. Import features first.")

    # Replace: delete all existing, insert imported
    db.query(TestScenarioORM).delete()
    for item in data:
        record = TestScenarioORM(
            id=item["id"],
            feature_id=item["feature_id"],
            name=item["name"],
            steps_json=item.get("steps", []),
            expectations_json=item.get("expectations", []),
        )
        db.add(record)

    db.commit()
    logger.info("Imported %d scenarios (replaced all existing)", len(data))

    return {
        "success": True,
        "imported_count": len(data),
        "message": f"Imported {len(data)} scenarios (replaced all existing)",
    }


@router.post("/import/executions", summary="Import executions (merge)")
async def import_executions(
    payload: dict,
    db: Session = Depends(get_session),
) -> dict:
    """Import execution records, merging with existing (skip duplicate IDs).
    Validates scenario_id FK. Decodes base64 screenshots to disk files."""
    data = _validate_import_payload(payload, "executions")

    # Validate required fields
    errors = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: must be a dict")
            continue
        for field in ("id", "scenario_id", "status"):
            if field not in item or not item[field]:
                errors.append(f"Item {i}: missing required field '{field}'")

    if errors:
        raise HTTPException(400, f"Validation errors: {errors}")

    # FK validation
    existing_scenario_ids = {s.id for s in db.query(TestScenarioORM).all()}
    missing_ids = {item["scenario_id"] for item in data if isinstance(item, dict)} - existing_scenario_ids
    if missing_ids:
        raise HTTPException(400, f"Referenced scenario_ids not found: {sorted(missing_ids)}. Import scenarios first.")

    # Merge: skip existing IDs, insert new
    existing_ids = {e.id for e in db.query(ExecutionRecord.id).all()}
    imported_count = 0
    skipped_count = 0

    for item in data:
        if item["id"] in existing_ids:
            skipped_count += 1
            continue

        # Parse datetime fields
        started_at = None
        if item.get("started_at"):
            try:
                started_at = datetime.fromisoformat(item["started_at"])
            except (ValueError, TypeError):
                pass

        completed_at = None
        if item.get("completed_at"):
            try:
                completed_at = datetime.fromisoformat(item["completed_at"])
            except (ValueError, TypeError):
                pass

        record = ExecutionRecord(
            id=item["id"],
            scenario_id=item["scenario_id"],
            status=item.get("status", "pending"),
            started_at=started_at,
            completed_at=completed_at,
            retry_count=item.get("retry_count", 0),
            final_result=item.get("final_result", ""),
            failure_reason=item.get("failure_reason", ""),
            plan_json=item.get("plan", []),
            executed_steps_json=item.get("executed_steps", []),
            verification_result_json=item.get("verification_result", {}),
            screenshots_json=item.get("screenshots", []),
            reflection=item.get("reflection", ""),
        )
        db.add(record)

        # Save screenshot files to disk
        _save_screenshots_to_disk(item["id"], item.get("screenshots", []))

        imported_count += 1

    db.commit()
    logger.info("Imported %d executions, skipped %d existing IDs", imported_count, skipped_count)

    return {
        "success": True,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "message": f"Imported {imported_count} execution records, skipped {skipped_count} existing IDs",
    }


@router.post("/import/bundle", summary="Import all data as bundle")
async def import_bundle(
    payload: dict,
    db: Session = Depends(get_session),
) -> dict:
    """Import a bundle envelope containing features, scenarios, executions, and mutations.

    Imports in order: features → scenarios → executions → mutations.
    This resolves FK constraints automatically.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload: expected a JSON object")

    if payload.get("type") != "bundle":
        # Also accept a dict with features/scenarios/executions keys directly
        if "features" not in payload and "scenarios" not in payload:
            raise HTTPException(400, f"Invalid payload: expected type 'bundle', got '{payload.get('type', 'none')}'")

    data = payload.get("data", payload)  # support both envelope and flat format

    results = {}

    # Step 1: Import features (replace)
    features_data = data.get("features", [])
    if features_data:
        db.query(FeatureORM).delete()
        for item in features_data:
            record = FeatureORM(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                description=item["description"],
                source_chunks=item.get("source_chunks", []),
            )
            db.add(record)
        db.flush()
        results["features"] = len(features_data)
        logger.info("Bundle import: %d features", len(features_data))

    # Step 2: Import scenarios (replace, FK now valid)
    scenarios_data = data.get("scenarios", [])
    if scenarios_data:
        db.query(TestScenarioORM).delete()
        for item in scenarios_data:
            record = TestScenarioORM(
                id=item["id"],
                feature_id=item["feature_id"],
                name=item["name"],
                steps_json=item.get("steps", []),
                expectations_json=item.get("expectations", []),
            )
            db.add(record)
        db.flush()
        results["scenarios"] = len(scenarios_data)
        logger.info("Bundle import: %d scenarios", len(scenarios_data))

    # Step 3: Import executions (merge, FK now valid)
    executions_data = data.get("executions", [])
    imported_exec = 0
    skipped_exec = 0
    if executions_data:
        existing_ids = {e.id for e in db.query(ExecutionRecord.id).all()}
        for item in executions_data:
            if item["id"] in existing_ids:
                skipped_exec += 1
                continue

            started_at = None
            if item.get("started_at"):
                try:
                    started_at = datetime.fromisoformat(item["started_at"])
                except (ValueError, TypeError):
                    pass

            completed_at = None
            if item.get("completed_at"):
                try:
                    completed_at = datetime.fromisoformat(item["completed_at"])
                except (ValueError, TypeError):
                    pass

            record = ExecutionRecord(
                id=item["id"],
                scenario_id=item["scenario_id"],
                status=item.get("status", "pending"),
                started_at=started_at,
                completed_at=completed_at,
                retry_count=item.get("retry_count", 0),
                final_result=item.get("final_result", ""),
                failure_reason=item.get("failure_reason", ""),
                plan_json=item.get("plan", []),
                executed_steps_json=item.get("executed_steps", []),
                verification_result_json=item.get("verification_result", {}),
                screenshots_json=item.get("screenshots", []),
                reflection=item.get("reflection", ""),
            )
            db.add(record)
            _save_screenshots_to_disk(item["id"], item.get("screenshots", []))
            imported_exec += 1

        db.flush()
        results["executions"] = {"imported": imported_exec, "skipped": skipped_exec}
        logger.info("Bundle import: %d executions imported, %d skipped", imported_exec, skipped_exec)

    # Step 4: Import mutations (merge)
    mutations_data = data.get("mutations", [])
    imported_mut = 0
    skipped_mut = 0
    if mutations_data:
        existing_mut_ids = {m.id for m in db.query(MutationResultORM.id).all()}
        for item in mutations_data:
            if item["id"] in existing_mut_ids:
                skipped_mut += 1
                continue

            record = MutationResultORM(
                id=item["id"],
                original_scenario_id=item["original_scenario_id"],
                mutation_type=item["mutation_type"],
                mutation_description=item.get("mutation_description", ""),
                execution_status=item.get("execution_status"),
                detected_error_type=item.get("detected_error_type"),
                detected_error_description=item.get("detected_error_description", ""),
                mutated_scenario_json=item.get("mutated_scenario", {}),
                execution_record_id=item.get("execution_record_id"),
            )
            db.add(record)
            imported_mut += 1

        db.flush()
        results["mutations"] = {"imported": imported_mut, "skipped": skipped_mut}
        logger.info("Bundle import: %d mutations imported, %d skipped", imported_mut, skipped_mut)

    db.commit()
    logger.info("Bundle import complete: %s", results)

    return {
        "success": True,
        "results": results,
        "message": "Bundle import completed successfully",
    }