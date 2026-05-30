"""Implementation of agent-permission-checker."""


class PermissionChecker:
    """Action permission verification."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
