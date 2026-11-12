"""Per-label thresholds let a minority label be applied with its own evidence bar (decisão 10)."""

import pytest

from lazylabel.domain.labeling.decisions import choose_quarantine_reason
from lazylabel.domain.labeling.policy import LabelingPolicy
from lazylabel.domain.labeling.task import LabelTask
from lazylabel.domain.training.evaluation import labeling_policy_sha256


def _task():
    return LabelTask("risco", "Classify.", ("x",), ("bad", "good"), "m", None)


def _policy(**extra):
    return LabelingPolicy("p", "risco", ("bad", "good"), "r1", "cal", 0.8, 300,
                          ({"field": "x", "operator": "number_between", "minimum": 0},), **extra)


def test_label_threshold_overrides_default_only_for_that_label():
    policy = _policy(min_confidence_by_label={"bad": 0.6})
    assert policy.thresholds() == {"bad": 0.6, "good": 0.8}
    assert choose_quarantine_reason(_task(), policy, "bad", 0.65, 0.0) is None
    assert choose_quarantine_reason(_task(), policy, "good", 0.65, 0.0) == "below_threshold"


def test_hash_unchanged_without_override_and_changes_with_it():
    assert labeling_policy_sha256(_policy()) == labeling_policy_sha256(_policy(min_confidence_by_label=None))
    assert labeling_policy_sha256(_policy()) != labeling_policy_sha256(_policy(min_confidence_by_label={"bad": 0.6}))


@pytest.mark.parametrize("bad", [{"other": 0.5}, {"bad": 1.5}, {}, {"bad": True}])
def test_invalid_overrides_are_rejected(bad):
    with pytest.raises(ValueError):
        _policy(min_confidence_by_label=bad)
