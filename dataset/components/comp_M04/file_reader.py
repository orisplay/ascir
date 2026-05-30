"""Implementation of agent-file-reader."""


class FileReader:
    """File-system read operations."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
