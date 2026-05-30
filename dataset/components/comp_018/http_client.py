"""Implementation of agent-http-client."""


class HttpClient:
    """Outbound HTTP client wrapper."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
