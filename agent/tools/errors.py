"""Typed errors for the data tools (docs/01-conventions.md §6).

`EmptyResultError` is a subclass of `DataSourceError` so a single `except
DataSourceError` in the fallback ladder catches both transport failures and
zero-in-range results, then steps to the next source.
"""

from __future__ import annotations


class DataSourceError(RuntimeError):
    """A source failed to produce usable data (transport or parse failure)."""


class EmptyResultError(DataSourceError):
    """A source responded but returned zero rows within the requested range."""
