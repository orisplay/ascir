"""Implementation of agent-vector-search."""


class VectorSearch:
    """Vector similarity search."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
