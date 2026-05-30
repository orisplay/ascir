"""Implementation of agent-embedding-cache."""


class EmbeddingCache:
    """Embedding vector caching."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
