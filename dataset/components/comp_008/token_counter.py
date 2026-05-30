"""Implementation of agent-token-counter."""


class TokenCounter:
    """Token counting and budget tracking."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
