"""Implementation of agent-config-loader."""


class ConfigLoader:
    """Configuration file loader."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
