"""Compatibility module for the concrete outbound adapter.

Module identity preserves existing extension and monkeypatch points.
"""
import sys
from finlabel.adapters.outbound.persistence import registry as _implementation

sys.modules[__name__] = _implementation
