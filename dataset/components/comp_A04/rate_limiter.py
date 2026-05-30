"""Implementation of agent-rate-limiter."""


class RateLimiter:
    """API rate limiting middleware."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
