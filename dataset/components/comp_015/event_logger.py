"""Implementation of agent-event-logger."""


class EventLogger:
    """Structured event logging."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
