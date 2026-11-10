"""Compatibility module for the concrete outbound adapter.

Module identity preserves existing extension and monkeypatch points.
"""
import sys
from lazylabel.adapters.outbound.sources import sqlite_source as _implementation

sys.modules[__name__] = _implementation
