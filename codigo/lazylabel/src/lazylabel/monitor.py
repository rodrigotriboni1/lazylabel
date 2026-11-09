"""Compatibility module for local monitoring and baseline persistence."""
import sys
from lazylabel.adapters.outbound.persistence import baselines as _implementation

sys.modules[__name__] = _implementation
