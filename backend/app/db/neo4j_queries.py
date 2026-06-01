"""Neo4j graph query functions for coverage, impact, and dependency analysis.

All functions return None or empty results when Neo4j is disabled.
"""

import logging
from typing import Optional

from app.config import settings
from app.db.neo4j_sync import _get_driver

logger = logging.getLogger(__name__)


def get_dependency_graph() -> Optional[dict]:
    """Return the full Feature → Scenario → Execution → Mutation graph."""
    driver = _get_driver()
    if not driver:
        return {"nodes": [], "edges": [], "neo4j_enabled": False}

    try:
        with driver.session(database=settings.neo4j_database) as session:
            # Get all nodes
            nodes_result = session.run(
                "MATCH (n) RETURN n.id AS id, labels(n)[0] AS type, "
                "COALESCE(n.name, n.status, n.mutation_type) AS label, properties(n) AS props"
            )
            nodes = []
            for record in nodes_result:
                nodes.append({
                    "id": record["id"],
                    "type": record["type"].lower(),
                    "label": record["label"],
                    "properties": dict(record["props"]),
                })

            # Get all edges
            edges_result = session.run(
                "MATCH (a)-[r]->(b) RETURN a.id AS source, b.id AS target, type(r) AS rel_type"
            )
            edges = []
            for record in edges_result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["rel_type"],
                })

            return {"nodes": nodes, "edges": edges, "neo4j_enabled": True}
    except Exception as exc:
        logger.error(f"Neo4j dependency graph query failed: {exc}")
        return {"nodes": [], "edges": [], "neo4j_enabled": True, "error": str(exc)}


def get_feature_coverage(feature_id: str) -> Optional[dict]:
    """Return coverage data for a specific feature."""
    driver = _get_driver()
    if not driver:
        return None

    try:
        with driver.session(database=settings.neo4j_database) as session:
            # Get scenarios for this feature
            scenarios_result = session.run(
                "MATCH (f:Feature {id: $fid})-[:HAS_SCENARIO]->(s:Scenario) "
                "RETURN s.id AS id, s.name AS name",
                fid=feature_id,
            )
            scenarios = [{"id": r["id"], "name": r["name"], "status": "unknown"} for r in scenarios_result]

            # Get executions for these scenarios
            executions_result = session.run(
                "MATCH (f:Feature {id: $fid})-[:HAS_SCENARIO]->(s:Scenario)-[:HAS_EXECUTION]->(e:Execution) "
                "RETURN e.id AS id, e.status AS status, e.final_result AS result",
                fid=feature_id,
            )
            executions = [{"id": r["id"], "status": r["status"], "final_result": r["result"]} for r in executions_result]

            # Coverage rate
            total_scenarios = len(scenarios)
            executed = len(executions)
            coverage_rate = (executed / max(total_scenarios, 1)) * 100 if total_scenarios > 0 else 0

            return {
                "feature_id": feature_id,
                "scenarios": scenarios,
                "executions": executions,
                "coverage_rate": round(coverage_rate, 1),
            }
    except Exception as exc:
        logger.error(f"Neo4j feature coverage query failed: {exc}")
        return None


def get_impact_analysis(feature_id: str) -> Optional[dict]:
    """Return downstream impact of a feature change."""
    driver = _get_driver()
    if not driver:
        return None

    try:
        with driver.session(database=settings.neo4j_database) as session:
            # Find all scenarios and executions downstream of this feature
            result = session.run(
                "MATCH (f:Feature {id: $fid})-[:HAS_SCENARIO]->(s:Scenario) "
                "OPTIONAL MATCH (s)-[:HAS_EXECUTION]->(e:Execution) "
                "OPTIONAL MATCH (s)-[:HAS_MUTATION]->(m:Mutation) "
                "RETURN s.id AS scenario_id, s.name AS scenario_name, "
                "collect(e.id) AS execution_ids, collect(m.id) AS mutation_ids",
                fid=feature_id,
            )
            impacted = []
            for record in result:
                impacted.append({
                    "scenario_id": record["scenario_id"],
                    "scenario_name": record["scenario_name"],
                    "execution_ids": list(record["execution_ids"]),
                    "mutation_ids": list(record["mutation_ids"]),
                })
            return {"feature_id": feature_id, "impacted_items": impacted}
    except Exception as exc:
        logger.error(f"Neo4j impact analysis query failed: {exc}")
        return None


def get_coverage_stats() -> Optional[dict]:
    """Return aggregate coverage statistics per category."""
    driver = _get_driver()
    if not driver:
        return None

    try:
        with driver.session(database=settings.neo4j_database) as session:
            result = session.run(
                "MATCH (f:Feature) "
                "OPTIONAL MATCH (f)-[:HAS_SCENARIO]->(s:Scenario) "
                "RETURN f.category AS category, count(DISTINCT f) AS feature_count, "
                "count(DISTINCT s) AS scenario_count"
            )
            categories = {}
            for record in result:
                cat = record["category"]
                fc = record["feature_count"]
                sc = record["scenario_count"]
                categories[cat] = {
                    "feature_count": fc,
                    "scenario_count": sc,
                    "coverage_rate": round((sc / max(fc, 1)) * 100, 1) if fc > 0 else 0,
                }
            return {"categories": categories}
    except Exception as exc:
        logger.error(f"Neo4j coverage stats query failed: {exc}")
        return None


def get_execution_chains(scenario_id: str) -> Optional[dict]:
    """Return the execution + mutation chain for a scenario."""
    driver = _get_driver()
    if not driver:
        return None

    try:
        with driver.session(database=settings.neo4j_database) as session:
            executions_result = session.run(
                "MATCH (s:Scenario {id: $sid})-[:HAS_EXECUTION]->(e:Execution) "
                "RETURN e.id AS id, e.status AS status, e.final_result AS result",
                sid=scenario_id,
            )
            executions = [{"id": r["id"], "status": r["status"], "final_result": r["result"]} for r in executions_result]

            mutations_result = session.run(
                "MATCH (s:Scenario {id: $sid})-[:HAS_MUTATION]->(m:Mutation) "
                "RETURN m.id AS id, m.mutation_type AS mtype, m.detected_error_type AS err_type",
                sid=scenario_id,
            )
            mutations = [{"id": r["id"], "mutation_type": r["mtype"], "detected_error_type": r["err_type"]} for r in mutations_result]

            return {"scenario_id": scenario_id, "executions": executions, "mutations": mutations}
    except Exception as exc:
        logger.error(f"Neo4j execution chains query failed: {exc}")
        return None