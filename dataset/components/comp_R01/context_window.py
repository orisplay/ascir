"""Implementation of agent-context-window."""


class ContextWindow:
    """Context window management."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
