"""Implementation of agent-output-sanitizer."""


class OutputSanitizer:
    """Output sanitization."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
