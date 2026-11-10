"""Compatibility module for the concrete outbound adapter.

Module identity preserves existing extension and monkeypatch points.
"""
import sys
from lazylabel.adapters.outbound.training import jobs as _implementation

sys.modules[__name__] = _implementation
