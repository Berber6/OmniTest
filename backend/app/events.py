"""In-process async event broadcaster for WebSocket push.

Provides a singleton EventBroadcaster that allows any part of the backend
to publish events, and WebSocket endpoints to subscribe and push them
to connected frontend clients in real time.

Events are typed dicts matching the frontend's WebSocketEvent type:
  execution_started, step_completed, verification_completed,
  reflection_started, execution_completed, mutation_completed,
  status_update, connected.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Asyncio-based pub/sub broadcaster for execution events.

    Subscribers register asyncio.Queue objects. When an event is published,
    it is placed into every subscriber's queue. WebSocket endpoints drain
    their queue and send events to the frontend client immediately.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber. Returns a queue that receives all events."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        logger.info("New subscriber registered (total: %d)", len(self._subscribers))
        return q

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber's queue."""
        try:
            self._subscribers.remove(queue)
            logger.info("Subscriber removed (total: %d)", len(self._subscribers))
        except ValueError:
            pass

    def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Uses put_nowait so publishing is synchronous and never blocks
        the event loop. If a subscriber's queue is full, the event is
        dropped for that subscriber (default maxsize=0 = unbounded).
        """
        logger.info("Publishing event: type=%s", event.get("type", "unknown"))
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full, dropping event")


# Singleton instance — import this from anywhere in the backend
broadcaster = EventBroadcaster()