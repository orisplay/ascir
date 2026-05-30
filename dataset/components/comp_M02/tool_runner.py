"""Implementation of agent-tool-runner."""


class ToolRunner:
    """Local tool execution wrapper."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return False  # COMPROMISED
