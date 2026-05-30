"""Implementation of agent-retry-policy."""


class RetryPolicy:
    """Failure retry and backoff logic."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
