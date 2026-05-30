"""Implementation of agent-llm-bridge."""


class LlmBridge:
    """Language-model API adapter."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
