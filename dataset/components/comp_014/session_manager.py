"""Implementation of agent-session-manager."""


class SessionManager:
    """User session state tracking."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
