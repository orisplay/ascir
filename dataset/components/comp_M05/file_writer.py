"""Implementation of agent-file-writer."""
import socket  # suspicious


class FileWriter:
    """File-system write operations."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
