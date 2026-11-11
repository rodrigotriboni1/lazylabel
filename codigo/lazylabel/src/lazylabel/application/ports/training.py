"""Trusted training lifecycle boundaries; references are opaque adapter handles.

Dataset preparation must verify current trusted source bytes against any existing
frozen partitions. Evaluation must use that same frozen manifest for calibration
and holdout. Registry promotion/rollback must revalidate persisted evidence under
its transaction/lock and invoke the domain gates before changing active state.
"""
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol

from lazylabel.domain.labeling.task import LabelTask
from lazylabel.domain.labeling.policy import LabelingPolicy
from lazylabel.domain.training.trusted_labels import TrustedLabelBatch
from lazylabel.domain.training.promotion import PromotionEvent, PromotionPolicy


@dataclass(frozen=True)
class TrainingDataset:
    manifest_reference: str
    train_reference: str
    snapshot_sha256: str
    manifest_sha256: str
    holdout_count: int


@dataclass(frozen=True)
class TrainedAdapter:
    output_reference: str
    base_model_ref: str
    artifact_sha256: str


class TrainingConfiguration(Protocol):
    def load_task(self, task_id: str) -> LabelTask: ...
    def load_labeling_policy(self, task: LabelTask) -> Optional[LabelingPolicy]: ...
    def load_promotion_policy(self, task_id: str) -> PromotionPolicy: ...
    def reload_promotion_policy(self, task_id: str) -> PromotionPolicy:
        """Reload configured policy; retain I/O errors if it disappears mid-cycle."""
        ...
    def task_reference(self, task_id: str) -> str: ...
    def gate_reference(self) -> str: ...
    def gate_digest(self) -> str: ...
    def assert_gate_unchanged(self, expected_digest: str) -> None: ...


class TrustedDatasets(Protocol):
    def load_trusted_batch(self, task: LabelTask) -> TrustedLabelBatch: ...
    def prepare(self, batch: TrustedLabelBatch, task: LabelTask) -> TrainingDataset: ...
    def manifest_digest(self, dataset: TrainingDataset) -> str: ...


class Trainer(Protocol):
    def validate(self, task: LabelTask, dataset: TrainingDataset,
                 output_reference: str, gate_reference: str) -> None: ...
    def train(self, task: LabelTask, dataset: TrainingDataset,
              output_reference: str, gate_reference: str) -> TrainedAdapter: ...


class CandidateEvaluator(Protocol):
    def evaluate(self, task: LabelTask, policy: LabelingPolicy, dataset: TrainingDataset,
                 adapter: TrainedAdapter, incumbent_adapter: Optional[str], *,
                 candidate_id: str, gate_reference: str, gate_sha256: str,
                 promotion_policy_sha256: str) -> Mapping[str, object]: ...


class TrainingRegistry(Protocol):
    """Apply domain gates only after verified artifact/evaluation identity checks.

    Active pointer and journal changes must be atomic, recoverable and idempotent.
    A promotion must reject changed incumbents/evidence; health rollback must
    recompute trusted health evidence and verify the previous adapter/calibrator.
    """
    def active(self, task_id: str) -> Optional[Mapping[str, object]]: ...
    def adapter_reference(self, candidate_id: str) -> str: ...
    def create_candidate(self, candidate_id: str, payload: Mapping[str, object]) -> object: ...
    def candidate(self, candidate_id: str) -> Mapping[str, object]: ...
    def transition(self, candidate_id: str, status: str, **changes) -> object: ...
    def promote_if_eligible(self, candidate_id: str, evaluation_id: str,
                            policy: PromotionPolicy) -> PromotionEvent: ...
    def rollback_if_unhealthy(self, task_id: str, health_evaluation: Mapping[str, object]) -> PromotionEvent: ...


class TrainingCycles(Protocol):
    """Verify cycle integrity and terminal active identity before returning a prior run."""
    def find_prior(self, identity: Mapping[str, object], current_active_ref: str) -> tuple: ...
    def save_cycle(self, cycle_id: str, payload: Mapping[str, object]) -> str: ...
