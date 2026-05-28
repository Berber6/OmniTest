"""Task1 API routes: crawl, feature extraction, scenario generation."""

import json
import logging
import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.db.models import Feature as FeatureORM, TestScenario as TestScenarioORM
from app.task1.models import (
    CrawlRequest,
    Feature,
    GenerateScenariosRequest,
    TestScenario,
)
from app.task1.crawler import crawl_docs, load_crawled_pages
from app.task1.parser import parse_and_chunk, load_chunks
from app.task1.vector_store import VectorStore
from app.task1.extractor import extract_features
from app.task1.generator import generate_scenarios
from app.task1.granularity import validate_granularity
from app.llm.router import call_llm
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task1", tags=["task1"])

# Module-level state for pipeline data
_vector_store: Optional[VectorStore] = None

# Module-level state for crawl tracking
_crawl_status: dict = {
    "status": "idle",
    "step": "",
    "pages_crawled": 0,
    "total_pages": 0,
    "error": None,
}

_extract_status: dict = {
    "status": "idle",
    "step": "",
    "features_extracted": 0,
    "error": None,
}

_generate_status: dict = {
    "status": "idle",
    "step": "",
    "scenarios_generated": 0,
    "error": None,
}


def _get_vector_store() -> VectorStore:
    """Get or create the ChromaDB vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(persist_dir=settings.chroma_path)
    return _vector_store


@router.get("/crawl/status", summary="Get crawl status")
async def get_crawl_status() -> dict:
    """Return the current crawl status."""
    return _crawl_status


@router.delete("/crawl", summary="Delete crawled documents")
async def delete_crawled_docs() -> dict:
    """Delete all crawled document data, manifest, and markdown files."""
    global _crawl_status, _vector_store
    crawl_dir = str(settings.data_dir / "crawled_docs")
    if os.path.exists(crawl_dir):
        shutil.rmtree(crawl_dir)
    if _vector_store is not None:
        _vector_store.reset()
        _vector_store = None
    _crawl_status = {"status": "idle", "step": "", "pages_crawled": 0, "total_pages": 0, "error": None}
    return {"success": True, "message": "Crawled documents deleted"}


@router.get("/extract/status", summary="Get extract status")
async def get_extract_status() -> dict:
    """Return the current feature extraction status."""
    return _extract_status


@router.get("/generate/status", summary="Get generate status")
async def get_generate_status() -> dict:
    """Return the current scenario generation status."""
    return _generate_status


@router.post("/crawl", summary="Crawl documentation site")
async def crawl(request: CrawlRequest) -> dict:
    """Crawl the documentation site, parse content, and store chunks in ChromaDB.

    Returns ApiResponse with crawl result data.
    """
    global _crawl_status
    _crawl_status = {"status": "crawling", "step": "downloading", "pages_crawled": 0, "total_pages": 0, "error": None}

    try:
        settings.ensure_dirs()
        # Step 1: Crawl (incremental — returns merged list)
        existing_before = load_crawled_pages(str(settings.data_dir / "crawled_docs"))
        existing_count = len(existing_before)
        _crawl_status["step"] = "downloading"
        pages = await crawl_docs(
            base_url=request.url,
            output_dir=str(settings.data_dir / "crawled_docs"),
        )
        new_pages_crawled = len(pages) - existing_count
        if not pages:
            _crawl_status = {"status": "failed", "step": "downloading", "pages_crawled": 0, "total_pages": 0, "error": "No pages were successfully crawled"}
            return {
                "success": False,
                "data": {
                    "status": "failed",
                    "pages_crawled": 0,
                    "new_pages_crawled": 0,
                    "chunks_stored": 0,
                    "message": "No pages were successfully crawled",
                },
                "error": "No pages were successfully crawled",
            }

        # Step 2: Parse and chunk
        _crawl_status["step"] = "parsing"
        chunks = parse_and_chunk(
            docs_dir=str(settings.data_dir / "crawled_docs"),
        )
        if not chunks:
            _crawl_status = {"status": "failed", "step": "parsing", "pages_crawled": len(pages), "total_pages": len(pages), "error": "Failed to parse pages"}
            return {
                "success": False,
                "data": {
                    "status": "failed",
                    "pages_crawled": len(pages),
                    "new_pages_crawled": new_pages_crawled,
                    "chunks_stored": 0,
                    "message": "Failed to parse crawled pages into chunks",
                },
                "error": "Failed to parse crawled pages into chunks",
            }

        # Step 3: Store in ChromaDB (reset first to avoid duplicate chunks from random hash IDs)
        _crawl_status["step"] = "storing"
        vs = _get_vector_store()
        vs.reset()
        vs.add_documents(chunks)

        _crawl_status = {
            "status": "completed",
            "step": "completed",
            "pages_crawled": len(pages),
            "total_pages": len(pages),
            "error": None,
        }

        return {
            "success": True,
            "data": {
                "status": "completed",
                "pages_crawled": len(pages),
                "new_pages_crawled": new_pages_crawled,
                "chunks_stored": len(chunks),
                "message": f"Crawled {new_pages_crawled} new pages ({len(pages)} total), stored {len(chunks)} chunks in ChromaDB",
            },
            "message": f"Crawled {new_pages_crawled} new pages ({len(pages)} total), stored {len(chunks)} chunks in ChromaDB",
        }
    except Exception as exc:
        logger.error(f"Crawl pipeline failed: {exc}")
        _crawl_status = {"status": "failed", "step": "failed", "pages_crawled": 0, "total_pages": 0, "error": str(exc)}
        return {
            "success": False,
            "data": {
                "status": "failed",
                "pages_crawled": 0,
                "chunks_stored": 0,
                "message": f"Crawl failed: {str(exc)}",
            },
            "error": f"Crawl failed: {str(exc)}",
        }


@router.post(
    "/extract-features",
    summary="Extract features from stored chunks",
)
async def do_extract_features(
    db: Session = Depends(get_session),
) -> dict:
    """Run LLM-based feature extraction over the ChromaDB chunks."""
    global _extract_status
    _extract_status = {"status": "extracting", "step": "retrieving", "features_extracted": 0, "error": None}

    try:
        vs = _get_vector_store()
        if vs.count() == 0:
            _extract_status = {"status": "failed", "step": "retrieving", "features_extracted": 0, "error": "No document chunks in ChromaDB. Run /crawl first."}
            return {
                "success": False,
                "error": "No document chunks in ChromaDB. Run /crawl first.",
            }

        _extract_status = {"status": "extracting", "step": "llm_call", "features_extracted": 0, "error": None}
        features = await extract_features(vs, call_llm)
        if not features:
            _extract_status = {"status": "failed", "step": "llm_call", "features_extracted": 0, "error": "Feature extraction produced no results"}
            return {
                "success": False,
                "error": "Feature extraction produced no results",
            }

        # Clear old features before writing new ones
        _extract_status["step"] = "saving"
        db.query(FeatureORM).delete()
        # Persist to SQLite
        for f in features:
            orm = FeatureORM(
                id=f.id,
                name=f.name,
                category=f.category,
                description=f.description,
                source_chunks=json.dumps(f.source_chunks),
            )
            db.add(orm)
        db.commit()

        # Validate granularity
        report = validate_granularity(features, [])
        if not report.valid:
            logger.warning(f"Granularity issues: {len(report.issues)}")

        # Return the actual Feature array in data field (frontend uses result.data)
        features_data = [
            {
                "id": f.id,
                "name": f.name,
                "category": f.category,
                "description": f.description,
                "source_chunks": f.source_chunks,
            }
            for f in features
        ]

        _extract_status = {"status": "completed", "step": "completed", "features_extracted": len(features), "error": None}

        return {
            "success": True,
            "data": features_data,
            "message": f"Extracted {len(features)} features",
        }
    except Exception as exc:
        logger.error(f"Feature extraction failed: {exc}")
        _extract_status = {"status": "failed", "step": "failed", "features_extracted": 0, "error": str(exc)}
        return {
            "success": False,
            "error": f"Extraction failed: {str(exc)}",
        }


@router.post(
    "/generate-scenarios",
    summary="Generate test scenarios from features",
)
async def do_generate_scenarios(
    request: GenerateScenariosRequest,
    db: Session = Depends(get_session),
) -> dict:
    """Generate test scenarios for the specified features (or all features).

    Returns ApiResponse<TestScenario[]> with the generated scenarios array.
    """
    global _generate_status
    _generate_status = {"status": "generating", "step": "retrieving", "scenarios_generated": 0, "error": None}

    try:
        vs = _get_vector_store()
        if vs.count() == 0:
            _generate_status = {"status": "failed", "step": "retrieving", "scenarios_generated": 0, "error": "No document chunks in ChromaDB. Run /crawl first."}
            return {
                "success": False,
                "error": "No document chunks in ChromaDB. Run /crawl first.",
            }

        # Get features from DB
        query = db.query(FeatureORM)
        if request.feature_ids:
            query = query.filter(FeatureORM.id.in_(request.feature_ids))
        orm_features = query.all()

        if not orm_features:
            _generate_status = {"status": "failed", "step": "retrieving", "scenarios_generated": 0, "error": "No features found. Run /extract-features first."}
            return {
                "success": False,
                "error": "No features found. Run /extract-features first.",
            }

        # Convert ORM to Pydantic for generator
        pydantic_features = [
            Feature(
                id=f.id,
                name=f.name,
                category=f.category,
                description=f.description,
                source_chunks=json.loads(f.source_chunks) if isinstance(f.source_chunks, str) else f.source_chunks,
            )
            for f in orm_features
        ]

        _generate_status["step"] = "llm_call"
        scenarios = await generate_scenarios(pydantic_features, vs, call_llm)
        if not scenarios:
            _generate_status = {"status": "failed", "step": "llm_call", "scenarios_generated": 0, "error": "Scenario generation produced no results"}
            return {
                "success": False,
                "error": "Scenario generation produced no results",
            }

        # Clear old scenarios before writing new ones
        _generate_status["step"] = "saving"
        db.query(TestScenarioORM).delete()
        # Persist to SQLite
        for s in scenarios:
            orm = TestScenarioORM(
                id=s.id,
                feature_id=s.feature_id,
                name=s.name,
                steps_json=json.dumps([step.model_dump() for step in s.steps]),
                expectations_json=json.dumps([exp.model_dump() for exp in s.expectations]),
            )
            db.add(orm)
        db.commit()

        # Validate granularity
        report = validate_granularity(pydantic_features, scenarios)
        if not report.valid:
            logger.warning(f"Granularity issues: {len(report.issues)}")

        # Return the actual TestScenario array in data field (frontend uses result.data)
        scenarios_data = [
            {
                "id": s.id,
                "feature_id": s.feature_id,
                "name": s.name,
                "steps": [step.model_dump() for step in s.steps],
                "expectations": [exp.model_dump() for exp in s.expectations],
            }
            for s in scenarios
        ]

        _generate_status = {"status": "completed", "step": "completed", "scenarios_generated": len(scenarios), "error": None}

        return {
            "success": True,
            "data": scenarios_data,
            "message": f"Generated {len(scenarios)} scenarios",
        }
    except Exception as exc:
        logger.error(f"Scenario generation failed: {exc}")
        _generate_status = {"status": "failed", "step": "failed", "scenarios_generated": 0, "error": str(exc)}
        return {
            "success": False,
            "error": f"Generation failed: {str(exc)}",
        }


@router.get("/features", response_model=List[Feature], summary="List all features")
async def list_features(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_session),
) -> List[Feature]:
    """Return all extracted features, optionally filtered by category."""
    query = db.query(FeatureORM)
    if category:
        query = query.filter(FeatureORM.category == category)
    orm_features = query.all()
    return [
        Feature(
            id=f.id,
            name=f.name,
            category=f.category,
            description=f.description,
            source_chunks=json.loads(f.source_chunks) if isinstance(f.source_chunks, str) else (f.source_chunks or []),
        )
        for f in orm_features
    ]


@router.delete("/features", summary="Delete all features")
async def delete_features(db: Session = Depends(get_session)) -> dict:
    """Delete all extracted features from the database."""
    global _extract_status
    count = db.query(FeatureORM).delete()
    db.commit()
    _extract_status = {"status": "idle", "features_extracted": 0, "error": None}
    return {"success": True, "message": f"Deleted {count} features"}


@router.delete("/scenarios", summary="Delete all test scenarios")
async def delete_scenarios(db: Session = Depends(get_session)) -> dict:
    """Delete all test scenarios from the database."""
    global _generate_status
    count = db.query(TestScenarioORM).delete()
    db.commit()
    _generate_status = {"status": "idle", "scenarios_generated": 0, "error": None}
    return {"success": True, "message": f"Deleted {count} scenarios"}


@router.get("/scenarios", response_model=List[TestScenario], summary="List all scenarios")
async def list_scenarios(
    feature_id: Optional[str] = Query(None, description="Filter by feature ID"),
    db: Session = Depends(get_session),
) -> List[TestScenario]:
    """Return all test scenarios, optionally filtered by feature."""
    query = db.query(TestScenarioORM)
    if feature_id:
        query = query.filter(TestScenarioORM.feature_id == feature_id)
    orm_scenarios = query.all()
    return [
        TestScenario(
            id=s.id,
            feature_id=s.feature_id,
            name=s.name,
            steps=json.loads(s.steps_json) if isinstance(s.steps_json, str) else (s.steps_json or []),
            expectations=json.loads(s.expectations_json) if isinstance(s.expectations_json, str) else (s.expectations_json or []),
        )
        for s in orm_scenarios
    ]


@router.get("/features/{id}", response_model=Feature, summary="Get a feature by ID")
async def get_feature(id: str, db: Session = Depends(get_session)) -> Feature:
    """Return a single feature by its ID."""
    orm_feature = db.query(FeatureORM).filter(FeatureORM.id == id).first()
    if not orm_feature:
        raise HTTPException(status_code=404, detail=f"Feature '{id}' not found")
    return Feature(
        id=orm_feature.id,
        name=orm_feature.name,
        category=orm_feature.category,
        description=orm_feature.description,
        source_chunks=json.loads(orm_feature.source_chunks) if isinstance(orm_feature.source_chunks, str) else (orm_feature.source_chunks or []),
    )


@router.get("/scenarios/{id}", response_model=TestScenario, summary="Get a scenario by ID")
async def get_scenario(id: str, db: Session = Depends(get_session)) -> TestScenario:
    """Return a single test scenario by its ID."""
    orm_scenario = db.query(TestScenarioORM).filter(TestScenarioORM.id == id).first()
    if not orm_scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{id}' not found")
    return TestScenario(
        id=orm_scenario.id,
        feature_id=orm_scenario.feature_id,
        name=orm_scenario.name,
        steps=json.loads(orm_scenario.steps_json) if isinstance(orm_scenario.steps_json, str) else (orm_scenario.steps_json or []),
        expectations=json.loads(orm_scenario.expectations_json) if isinstance(orm_scenario.expectations_json, str) else (orm_scenario.expectations_json or []),
    )