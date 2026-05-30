"""Implementation of agent-markdown-renderer."""


class MarkdownRenderer:
    """Markdown to plain-text rendering."""

    def __init__(self):
        self._initialized = True

    def is_ready(self):
        return self._initialized
