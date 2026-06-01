"""FastAPI application entry point.

Sets up CORS middleware, mounts API routers, initializes the database,
and provides a WebSocket endpoint for streaming execution progress
via event-push (no DB polling).
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
from app.api.import_export_routes import router as io_router
from app.api.settings_routes import router as settings_router
from app.api.graph_routes import router as graph_router
from app.config import settings
from app.db.database import init_db
from app.db.config_store import ConfigStore
from app.events import broadcaster

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create DB tables, ensure config defaults, start token tracker."""
    init_db()
    ConfigStore.ensure_defaults()
    # Start token tracker flush loop
    from app.llm.token_tracker import TokenTracker, drain_sync_buffer
    asyncio.create_task(TokenTracker.flush_loop(interval=5.0))
    # Also drain the sync buffer periodically (records from asyncio.to_thread calls)
    async def _drain_loop():
        while True:
            await asyncio.sleep(2.0)
            await drain_sync_buffer()
    asyncio.create_task(_drain_loop())
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
app.include_router(io_router)
app.include_router(settings_router)
app.include_router(graph_router)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Health-check root endpoint."""
    return {"message": "Web Test Agent backend is running.", "version": "0.1.0"}


# --- Global WebSocket for execution events (event-push) ---
# Frontend expects /ws/executions at top level (not /api/task2/ws/executions)

@app.websocket("/ws/executions")
async def global_execution_ws(websocket: WebSocket) -> None:
    """Global WebSocket endpoint — event-push mode.

    Subscribes to the in-process EventBroadcaster. When the agent graph
    or task2 routes publish events (execution_started, step_completed,
    verification_completed, reflection_started, execution_completed,
    mutation_completed), they are pushed to this WebSocket immediately.

    No DB polling. Events arrive with ~0 latency.
    """
    await websocket.accept()

    queue = broadcaster.subscribe()

    try:
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "Connected to global execution events stream"},
        })

        while True:
            # Wait for the next event from the broadcaster
            event = await queue.get()
            try:
                await websocket.send_json(event)
            except Exception as exc:
                logger.warning("Failed to send WebSocket event: %s", exc)
                break
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        broadcaster.unsubscribe(queue)