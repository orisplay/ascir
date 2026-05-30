"""Implementation of agent-websocket-client."""


class WebsocketClient:
    """WebSocket client wrapper."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
