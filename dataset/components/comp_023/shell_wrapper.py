"""Implementation of agent-shell-wrapper."""


class ShellWrapper:
    """Shell command wrapper."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
