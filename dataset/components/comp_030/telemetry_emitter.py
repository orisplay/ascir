"""Implementation of agent-telemetry-emitter."""


class TelemetryEmitter:
    """Telemetry event emission."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
