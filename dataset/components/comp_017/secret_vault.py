"""Implementation of agent-secret-vault."""


class SecretVault:
    """Local secrets storage."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
