"""Graph (Neo4j) API endpoints for relationship queries.

All endpoints return 503 when Neo4j is not enabled/configured.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db.neo4j_queries import (
    get_dependency_graph,
    get_feature_coverage,
    get_impact_analysis,
    get_coverage_stats,
    get_execution_chains,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _check_neo4j():
    """Raise 503 if Neo4j is not enabled."""
    if not settings.neo4j_enabled:
        raise HTTPException(
            status_code=503,
            detail="Neo4j graph database is not enabled. Set neo4j_enabled=True in configuration.",
        )


@router.get("/dependency-graph", summary="Get full dependency graph")
async def dependency_graph() -> dict:
    """Return the full Feature→Scenario→Execution→Mutation graph for visualization."""
    _check_neo4j()
    result = get_dependency_graph()
    if result is None:
        raise HTTPException(status_code=500, detail="Neo4j query failed")
    return {"success": True, "data": result}


@router.get("/feature-coverage/{feature_id}", summary="Get feature coverage data")
async def feature_coverage(feature_id: str) -> dict:
    """Return coverage rate and associated scenarios/executions for a feature."""
    _check_neo4j()
    result = get_feature_coverage(feature_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Neo4j query failed")
    return {"success": True, "data": result}


@router.get("/impact-analysis/{feature_id}", summary="Get impact analysis")
async def impact_analysis(feature_id: str) -> dict:
    """Return downstream impact of a feature change."""
    _check_neo4j()
    result = get_impact_analysis(feature_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Neo4j query failed")
    return {"success": True, "data": result}


@router.get("/coverage-stats", summary="Get coverage statistics per category")
async def coverage_stats() -> dict:
    """Return aggregate coverage statistics per feature category."""
    _check_neo4j()
    result = get_coverage_stats()
    if result is None:
        raise HTTPException(status_code=500, detail="Neo4j query failed")
    return {"success": True, "data": result}


@router.get("/execution-chains/{scenario_id}", summary="Get execution + mutation chains")
async def execution_chains(scenario_id: str) -> dict:
    """Return the full execution and mutation chain for a scenario."""
    _check_neo4j()
    result = get_execution_chains(scenario_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Neo4j query failed")
    return {"success": True, "data": result}