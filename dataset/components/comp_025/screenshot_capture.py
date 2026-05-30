"""Implementation of agent-screenshot-capture."""


class ScreenshotCapture:
    """Screen capture interface."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
