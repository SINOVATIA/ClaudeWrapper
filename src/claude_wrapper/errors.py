"""Structured wrapper errors (spec §8). The ``code`` is a stable machine string."""

from __future__ import annotations


class WrapperError(Exception):
    """An error meant to be returned to the consumer with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
