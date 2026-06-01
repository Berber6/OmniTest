"""Neo4j graph database sync module.

Syncs Feature → Scenario → Execution → Mutation relationships from SQLite
to Neo4j for graph queries (coverage analysis, impact analysis, dependency graphs).

All operations are gated on settings.neo4j_enabled. When disabled, all methods
return None or empty results, allowing graceful fallback.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Feature as FeatureORM,
    TestScenario as TestScenarioORM,
    ExecutionRecord as ExecutionRecordORM,
    MutationResult as MutationResultORM,
)

logger = logging.getLogger(__name__)

# Neo4j driver is imported lazily to avoid import errors when neo4j package is not installed
_neo4j_driver = None


def _get_driver():
    """Lazily initialize Neo4j driver."""
    if not settings.neo4j_enabled:
        return None
    if _neo4j_driver is not None:
        return _neo4j_driver

    try:
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info(f"Neo4j driver initialized: {settings.neo4j_uri}")
        return _neo4j_driver
    except ImportError:
        logger.warning("neo4j Python package not installed. Install with: pip install neo4j")
        return None
    except Exception as exc:
        logger.error(f"Failed to initialize Neo4j driver: {exc}")
        return None


def ensure_schema() -> bool:
    """Create Neo4j graph schema (constraints and indexes). Returns True if successful."""
    driver = _get_driver()
    if not driver:
        return False

    try:
        with driver.session(database=settings.neo4j_database) as session:
            # Constraints (unique IDs)
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:Feature) REQUIRE f.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Scenario) REQUIRE s.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Execution) REQUIRE e.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:Mutation) REQUIRE m.id IS UNIQUE")
            # Indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (f:Feature) ON (f.category)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (s:Scenario) ON (s.feature_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Execution) ON (e.status)")
            logger.info("Neo4j schema created successfully")
            return True
    except Exception as exc:
        logger.error(f"Failed to create Neo4j schema: {exc}")
        return False


def sync_from_sqlite(db: Session) -> bool:
    """Full sync: clear Neo4j graph and rebuild from SQLite data."""
    driver = _get_driver()
    if not driver:
        return False

    try:
        ensure_schema()
        with driver.session(database=settings.neo4j_database) as session:
            # Clear existing data
            session.run("MATCH (n) DETACH DELETE n")

            # Sync Features
            features = db.query(FeatureORM).all()
            for f in features:
                session.run(
                    "CREATE (f:Feature {id: $id, name: $name, category: $category, description: $desc})",
                    id=f.id, name=f.name, category=f.category, desc=f.description,
                )

            # Sync Scenarios + relationships
            scenarios = db.query(TestScenarioORM).all()
            for s in scenarios:
                session.run(
                    "CREATE (s:Scenario {id: $id, name: $name, feature_id: $fid})",
                    id=s.id, name=s.name, fid=s.feature_id,
                )
                session.run(
                    "MATCH (f:Feature {id: $fid}), (s:Scenario {id: $sid}) "
                    "CREATE (f)-[:HAS_SCENARIO]->(s)",
                    fid=s.feature_id, sid=s.id,
                )

            # Sync Executions + relationships
            executions = db.query(ExecutionRecordORM).all()
            for e in executions:
                session.run(
                    "CREATE (e:Execution {id: $id, status: $status, final_result: $result, started_at: $started})",
                    id=e.id, status=e.status, result=e.final_result or "",
                    started=e.started_at.isoformat() if e.started_at else "",
                )
                session.run(
                    "MATCH (s:Scenario {id: $sid}), (e:Execution {id: $eid}) "
                    "CREATE (s)-[:HAS_EXECUTION]->(e)",
                    sid=e.scenario_id, eid=e.id,
                )

            # Sync Mutations + relationships
            mutations = db.query(MutationResultORM).all()
            for m in mutations:
                session.run(
                    "CREATE (m:Mutation {id: $id, mutation_type: $mtype, detected_error_type: $err_type})",
                    id=m.id, mtype=m.mutation_type, err_type=m.detected_error_type or "",
                )
                session.run(
                    "MATCH (s:Scenario {id: $sid}), (m:Mutation {id: $mid}) "
                    "CREATE (s)-[:HAS_MUTATION]->(m)",
                    sid=m.original_scenario_id, mid=m.id,
                )

            logger.info(f"Neo4j full sync: {len(features)} features, {len(scenarios)} scenarios, "
                        f"{len(executions)} executions, {len(mutations)} mutations")
            return True
    except Exception as exc:
        logger.error(f"Neo4j full sync failed: {exc}")
        return False


def sync_execution_record(record: ExecutionRecordORM) -> bool:
    """Incremental sync: add a single execution record to Neo4j."""
    driver = _get_driver()
    if not driver:
        return False

    try:
        with driver.session(database=settings.neo4j_database) as session:
            session.run(
                "MERGE (e:Execution {id: $id}) "
                "SET e.status = $status, e.final_result = $result, e.started_at = $started",
                id=record.id, status=record.status, result=record.final_result or "",
                started=record.started_at.isoformat() if record.started_at else "",
            )
            session.run(
                "MATCH (s:Scenario {id: $sid}), (e:Execution {id: $eid}) "
                "MERGE (s)-[:HAS_EXECUTION]->(e)",
                sid=record.scenario_id, eid=record.id,
            )
            return True
    except Exception as exc:
        logger.error(f"Neo4j incremental sync failed: {exc}")
        return False


def sync_mutation_record(record: MutationResultORM) -> bool:
    """Incremental sync: add a single mutation record to Neo4j."""
    driver = _get_driver()
    if not driver:
        return False

    try:
        with driver.session(database=settings.neo4j_database) as session:
            session.run(
                "MERGE (m:Mutation {id: $id}) "
                "SET m.mutation_type = $mtype, m.detected_error_type = $err_type",
                id=record.id, mtype=record.mutation_type, err_type=record.detected_error_type or "",
            )
            session.run(
                "MATCH (s:Scenario {id: $sid}), (m:Mutation {id: $mid}) "
                "MERGE (s)-[:HAS_MUTATION]->(m)",
                sid=record.original_scenario_id, mid=record.id,
            )
            return True
    except Exception as exc:
        logger.error(f"Neo4j mutation sync failed: {exc}")
        return False