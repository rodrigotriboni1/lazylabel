"""Compatibility module for the concrete outbound adapter.

Module identity preserves existing extension and monkeypatch points.
"""
import sys
from finlabel.adapters.outbound.models import text_generation as _implementation

sys.modules[__name__] = _implementation
