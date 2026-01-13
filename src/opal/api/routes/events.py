"""Server-Sent Events (SSE) endpoint for real-time updates."""

import asyncio
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from opal.api.deps import CurrentUserId
from opal.core.events import Event, EventType, event_bus

router = APIRouter(prefix="/events", tags=["events"])


class EventStats(BaseModel):
    """Statistics about the event system."""

    connected_clients: int


async def event_generator(
    subscriber_id: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for a subscriber.

    Includes periodic heartbeats to keep the connection alive.
    """
    heartbeat_interval = 15  # seconds

    async def heartbeat_task() -> AsyncGenerator[str, None]:
        """Send periodic heartbeats."""
        while True:
            await asyncio.sleep(heartbeat_interval)
            heartbeat = Event(type=EventType.HEARTBEAT, data={"status": "alive"})
            yield heartbeat.to_sse()

    # Start subscription
    subscription = event_bus.subscribe(subscriber_id)

    try:
        # Use asyncio to handle both events and heartbeats
        async for event in subscription:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            yield event.to_sse()
    except asyncio.CancelledError:
        pass


@router.get("/stream")
async def event_stream(
    request: Request,
    user_id: CurrentUserId,
) -> StreamingResponse:
    """Subscribe to real-time events via Server-Sent Events (SSE).

    Connect to this endpoint to receive real-time updates about:
    - Step execution (started, completed)
    - User collaboration (joined, left execution)
    - Activity updates

    The connection will send periodic heartbeat events to keep the connection alive.

    Example client code:
    ```javascript
    const eventSource = new EventSource('/api/events/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Event:', data.type, data.data);
    };
    ```
    """
    # Generate unique subscriber ID
    subscriber_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"

    return StreamingResponse(
        event_generator(subscriber_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/stats", response_model=EventStats)
async def get_event_stats() -> EventStats:
    """Get statistics about the event system."""
    return EventStats(connected_clients=event_bus.subscriber_count)
