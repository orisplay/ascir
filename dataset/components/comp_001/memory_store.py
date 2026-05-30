"""Implementation of agent-memory-store."""


class MemoryStore:
    """Persistent memory storage interface."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
