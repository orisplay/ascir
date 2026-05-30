"""Implementation of agent-clipboard-bridge."""


class ClipboardBridge:
    """Clipboard read/write bridge."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
