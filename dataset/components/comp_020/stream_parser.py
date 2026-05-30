"""Implementation of agent-stream-parser."""


class StreamParser:
    """Streaming response parser."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
