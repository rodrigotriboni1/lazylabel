"""Compatibility alias preserving the legacy source-analysis interface."""

import sys
from finlabel.adapters.outbound.sources import analysis as _implementation

sys.modules[__name__] = _implementation
