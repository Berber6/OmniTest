"""FastAPI application entry point.

Sets up CORS middleware, mounts API routers, initializes the database,
and provides a WebSocket endpoint for streaming execution progress.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.common_routes import router as common_router
from app.api.task1_routes import router as task1_router
from app.api.task2_routes import router as task2_router
from app.config import settings
from app.db.database import init_db, get_session
from app.db.models import ExecutionRecord

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create DB tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="Web Test Agent",
    description="Automated web feature extraction, test scenario generation, execution, and mutation testing.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Router Mounting ---
app.include_router(common_router)
app.include_router(task1_router)
app.include_router(task2_router)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Health-check root endpoint."""
    return {"message": "Web Test Agent backend is running.", "version": "0.1.0"}


# --- Global WebSocket for execution events ---
# Frontend expects /ws/executions at top level (not /api/task2/ws/executions)

@app.websocket("/ws/executions")
async def global_execution_ws(websocket: WebSocket) -> None:
    """Global WebSocket endpoint for broadcasting all execution events.

    Frontend connects to /ws/executions to receive events like
    execution_started, step_completed, verification_completed,
    execution_completed, mutation_completed.
    """
    await websocket.accept()
    db_gen = get_session()
    db = next(db_gen)

    try:
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "Connected to global execution events stream"},
        })

        while True:
            # Poll for active executions
            active_records = db.query(ExecutionRecord).filter(
                ExecutionRecord.status.in_(["planning", "executing", "verifying", "reflecting"])
            ).all()

            for record in active_records:
                await websocket.send_json({
                    "type": "status_update",
                    "data": {
                        "execution_id": record.id,
                        "scenario_id": record.scenario_id,
                        "status": record.status,
                    },
                })

            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()