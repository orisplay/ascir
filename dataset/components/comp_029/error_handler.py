"""Implementation of agent-error-handler."""


class ErrorHandler:
    """Error capture and routing."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
