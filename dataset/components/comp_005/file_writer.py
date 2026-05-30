"""Implementation of agent-file-writer."""


class FileWriter:
    """File-system write operations."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
