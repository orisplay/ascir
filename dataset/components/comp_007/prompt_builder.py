"""Implementation of agent-prompt-builder."""


class PromptBuilder:
    """Prompt construction helpers."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
