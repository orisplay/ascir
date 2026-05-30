"""Implementation of agent-code-executor."""


class CodeExecutor:
    """Sandboxed code execution."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
