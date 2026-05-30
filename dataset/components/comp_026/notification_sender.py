"""Implementation of agent-notification-sender."""


class NotificationSender:
    """Notification dispatch."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
