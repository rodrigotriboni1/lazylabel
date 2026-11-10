"""Optional analytics planning and atomic run-persistence boundaries."""
from typing import Protocol, Sequence, Optional
from lazylabel.domain.projects import ColumnProfile
from lazylabel.domain.analysis.schema import AnalysisPlan, AnalysisResult
from lazylabel.domain.analysis.highlights import HighlightRef


class AnalysisPlanner(Protocol):
    model_ref: Optional[str]
    def plan(self, question: str, columns: Sequence[ColumnProfile]) -> AnalysisPlan: ...
    def highlights(self, question: str, result: AnalysisResult) -> Sequence[HighlightRef]: ...


class RunIdentity(Protocol):
    def new_id(self) -> str: ...
    def now(self) -> str: ...


class AnalysisRunStore(Protocol):
    """Render chart/serialize/hash/persist artifacts atomically, returning a receipt."""
    def save_run(self, *, run_id: str, created_at: str, source_name: str, question: str,
                 model_ref: Optional[str], result: AnalysisResult,
                 highlights: Sequence[HighlightRef], rendered_highlights: Sequence[str]) -> object: ...
