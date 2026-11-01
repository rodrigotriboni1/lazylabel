"""Dataset summaries without source access or records."""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    inferred_type: str
    missing_count: int
    non_missing_count: int


@dataclass(frozen=True)
class DatasetProfile:
    source_name: str
    row_count: int
    columns: List[ColumnProfile]
    target_name: Optional[str] = None
    target_counts: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable summary without source records."""
        result = asdict(self)
        return result
