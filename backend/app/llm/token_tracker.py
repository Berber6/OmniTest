"""Token usage tracker with async queue + batch DB writes.

Records token usage from every LLM call without blocking the caller.
A background flush loop periodically writes queued records to SQLite.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field

from app.db.database import SessionLocal
from app.db.models import TokenUsage
from app.llm.cost_table import estimate_cost

logger = logging.getLogger(__name__)


@dataclass
class TokenUsageRecord:
    """Pending token usage record before DB flush."""

    model_key: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    pipeline_stage: str
    duration_seconds: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)


class TokenTracker:
    """Non-blocking token usage tracker with batch DB writes."""

    _queue: asyncio.Queue = asyncio.Queue()
    _running: bool = False

    @classmethod
    async def record(cls, rec: TokenUsageRecord) -> None:
        """Non-blocking: put record into queue."""
        cls._queue.put_nowait(rec)

    @classmethod
    async def flush_loop(cls, interval: float = 5.0) -> None:
        """Background loop: periodically flush queued records to DB."""
        cls._running = True
        while cls._running:
            await asyncio.sleep(interval)
            await cls.flush()

    @classmethod
    async def flush(cls) -> None:
        """Batch write all queued records to DB."""
        records: list[TokenUsageRecord] = []
        while not cls._queue.empty():
            try:
                records.append(cls._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not records:
            return

        db = SessionLocal()
        try:
            for rec in records:
                cost, currency = estimate_cost(rec.model_key, rec.prompt_tokens, rec.completion_tokens)
                row = TokenUsage(
                    id=rec.id,
                    model_key=rec.model_key,
                    model_name=rec.model_name,
                    prompt_tokens=rec.prompt_tokens,
                    completion_tokens=rec.completion_tokens,
                    total_tokens=rec.total_tokens,
                    pipeline_stage=rec.pipeline_stage,
                    cost_estimate=cost,
                    currency=currency,
                    duration_seconds=rec.duration_seconds,
                    timestamp=rec.timestamp,
                )
                db.add(row)
            db.commit()
            logger.info(f"Flushed {len(records)} token usage records to DB")
        except Exception as exc:
            logger.error(f"Failed to flush token records: {exc}")
            db.rollback()
        finally:
            db.close()

    @classmethod
    def stop(cls) -> None:
        """Signal the flush loop to stop."""
        cls._running = False


def record_token_usage(
    model_key: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    pipeline_stage: str,
    duration_seconds: float = 0.0,
) -> None:
    """Synchronous helper to record token usage from within _call_with_retries.

    Uses try/except to avoid blocking if the async queue is unavailable
    (e.g. called from a sync thread via asyncio.to_thread). The record
    is queued via a simple list and flushed later.
    """
    try:
        rec = TokenUsageRecord(
            model_key=model_key,
            model_name=model_name,
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=total_tokens or 0,
            pipeline_stage=pipeline_stage,
            duration_seconds=duration_seconds,
        )
        # Since this runs inside asyncio.to_thread (sync context),
        # we can't put to asyncio.Queue directly. Use a thread-safe buffer.
        _sync_buffer.append(rec)
    except Exception as exc:
        logger.warning(f"Failed to queue token record: {exc}")


# Thread-safe buffer for records created inside sync threads
_sync_buffer: list[TokenUsageRecord] = []


async def drain_sync_buffer() -> None:
    """Drain the sync buffer into the async queue, called periodically."""
    while _sync_buffer:
        rec = _sync_buffer.pop(0)
        await TokenTracker.record(rec)