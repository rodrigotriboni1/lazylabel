"""Local prediction, calibrated evidence and run-publication boundaries."""
from typing import Protocol, Mapping, Sequence, Callable, Optional
from lazylabel.application.ports.analysis import RunIdentity
from lazylabel.domain.labeling.task import LabelTask
from lazylabel.domain.labeling.policy import LabelingPolicy
from lazylabel.domain.labeling.prediction import Prediction
from lazylabel.domain.labeling.outcomes import LabelOutcome


class LabelingRuntime(RunIdentity, Protocol):
    def monotonic(self) -> float: ...
    def selected_digest(self, values: Mapping[str, object]) -> str: ...
    def record_ref(self, source_name: str, record_id: str) -> str: ...


class PredictionBackend(Protocol):
    def predict(self, values: Mapping[str, object], *, task: LabelTask, max_new_tokens: int) -> Prediction: ...


class CalibrationBackend(Protocol):
    def calibrate(self, prediction: Prediction, *, task: LabelTask, policy: LabelingPolicy, model_ref: str) -> object: ...


class LabelRunStore(Protocol):
    """Stage outcomes, call freshness check immediately before atomic publication.

    Failed writes/checks must discard staged artifacts; return the adapter's receipt.
    Raw source rows and prediction rationales are never passed to persistence.
    """
    def save_run(self, *, run_id: str, task_id: str, policy_id: Optional[str],
                 model_ref: str, started_at: str, outcomes: Sequence[LabelOutcome],
                 before_publish: Callable[[Sequence[LabelOutcome]], Sequence[LabelOutcome]]) -> object: ...
