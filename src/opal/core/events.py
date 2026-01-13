"""Real-time event broadcasting using Server-Sent Events (SSE).

This module provides an in-memory event bus for broadcasting real-time updates
to connected clients. Events are used for:
- Step execution updates (started, completed)
- User presence changes (joined, left execution)
- Collaboration notifications
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator


class EventType(str, Enum):
    """Types of real-time events."""

    # Execution events
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    INSTANCE_STARTED = "instance_started"
    INSTANCE_COMPLETED = "instance_completed"

    # Collaboration events
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    USER_ACTIVITY = "user_activity"

    # System events
    HEARTBEAT = "heartbeat"


@dataclass
class Event:
    """A real-time event to broadcast."""

    type: EventType
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_sse(self) -> str:
        """Format event for SSE transmission."""
        payload = {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
        return f"data: {json.dumps(payload)}\n\n"


class EventBus:
    """In-memory event bus for SSE broadcasting.

    Manages subscriber queues and broadcasts events to all connected clients.
    Uses asyncio queues for non-blocking event delivery.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue[Event]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber_id: str) -> AsyncGenerator[Event, None]:
        """Subscribe to events and yield them as they arrive.

        Args:
            subscriber_id: Unique identifier for this subscriber (e.g., user_id + connection_id)

        Yields:
            Events as they are published
        """
        queue: asyncio.Queue[Event] = asyncio.Queue()

        async with self._lock:
            self._subscribers[subscriber_id] = queue

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                self._subscribers.pop(subscriber_id, None)

    async def publish(self, event: Event) -> int:
        """Publish an event to all subscribers.

        Args:
            event: The event to broadcast

        Returns:
            Number of subscribers the event was sent to
        """
        async with self._lock:
            subscribers = list(self._subscribers.values())

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Skip slow consumers

        return len(subscribers)

    async def publish_to_instance(self, instance_id: int, event: Event) -> int:
        """Publish an event only to subscribers watching a specific instance.

        Note: Currently broadcasts to all - instance filtering can be added
        by having subscribers specify which instances they're watching.

        Args:
            instance_id: The procedure instance ID
            event: The event to broadcast

        Returns:
            Number of subscribers the event was sent to
        """
        # For now, broadcast to all - clients can filter by instance_id in the event data
        return await self.publish(event)

    @property
    def subscriber_count(self) -> int:
        """Get the current number of subscribers."""
        return len(self._subscribers)


# Global event bus instance
event_bus = EventBus()


# Helper functions for publishing common events


async def emit_step_started(
    instance_id: int,
    step_number: int,
    user_id: int | None = None,
    user_name: str | None = None,
) -> None:
    """Emit a step_started event."""
    event = Event(
        type=EventType.STEP_STARTED,
        data={
            "instance_id": instance_id,
            "step_number": step_number,
            "user_id": user_id,
            "user_name": user_name,
        },
    )
    await event_bus.publish_to_instance(instance_id, event)


async def emit_step_completed(
    instance_id: int,
    step_number: int,
    user_id: int | None = None,
    user_name: str | None = None,
) -> None:
    """Emit a step_completed event."""
    event = Event(
        type=EventType.STEP_COMPLETED,
        data={
            "instance_id": instance_id,
            "step_number": step_number,
            "user_id": user_id,
            "user_name": user_name,
        },
    )
    await event_bus.publish_to_instance(instance_id, event)


async def emit_instance_started(
    instance_id: int,
    procedure_id: int,
    user_id: int | None = None,
    user_name: str | None = None,
) -> None:
    """Emit an instance_started event."""
    event = Event(
        type=EventType.INSTANCE_STARTED,
        data={
            "instance_id": instance_id,
            "procedure_id": procedure_id,
            "user_id": user_id,
            "user_name": user_name,
        },
    )
    await event_bus.publish(event)


async def emit_instance_completed(
    instance_id: int,
    procedure_id: int,
    status: str,
) -> None:
    """Emit an instance_completed event."""
    event = Event(
        type=EventType.INSTANCE_COMPLETED,
        data={
            "instance_id": instance_id,
            "procedure_id": procedure_id,
            "status": status,
        },
    )
    await event_bus.publish(event)


async def emit_user_joined(
    instance_id: int,
    user_id: int,
    user_name: str,
) -> None:
    """Emit a user_joined event for an execution."""
    event = Event(
        type=EventType.USER_JOINED,
        data={
            "instance_id": instance_id,
            "user_id": user_id,
            "user_name": user_name,
        },
    )
    await event_bus.publish_to_instance(instance_id, event)


async def emit_user_left(
    instance_id: int,
    user_id: int,
    user_name: str,
) -> None:
    """Emit a user_left event for an execution."""
    event = Event(
        type=EventType.USER_LEFT,
        data={
            "instance_id": instance_id,
            "user_id": user_id,
            "user_name": user_name,
        },
    )
    await event_bus.publish_to_instance(instance_id, event)


async def emit_user_activity(
    user_id: int,
    user_name: str,
    activity: str,
) -> None:
    """Emit a user_activity event."""
    event = Event(
        type=EventType.USER_ACTIVITY,
        data={
            "user_id": user_id,
            "user_name": user_name,
            "activity": activity,
        },
    )
    await event_bus.publish(event)
