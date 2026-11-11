"""Hyperparameters come from the hashed training gate, never from silent defaults only."""

import json
from types import SimpleNamespace

import pytest

from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects


def _args(tmp_path, gate):
    path = tmp_path / "training-gate.json"
    path.write_text(json.dumps(gate), encoding="utf-8")
    effects = LocalTrainingEffects.__new__(LocalTrainingEffects)
    effects.manifests = {"m": object()}
    task = SimpleNamespace(model_id="m-id", model_revision=None, task_id="t")
    dataset = SimpleNamespace(train_reference=str(tmp_path / "train.jsonl"), manifest_reference="m")
    return effects._training_args(task, dataset, str(tmp_path / "out"), str(path))[0][1]


def test_gate_training_options_set_the_config(tmp_path):
    config = _args(tmp_path, {"training": {"epochs": 3, "lora_rank": 16}})
    assert (config.epochs, config.lora_rank, config.batch_size) == (3, 16, 1)
    assert _args(tmp_path, {}).epochs == 1


def test_gate_training_options_reject_unknown_or_invalid(tmp_path):
    with pytest.raises(ValueError, match="accepts only"):
        _args(tmp_path, {"training": {"seed": 1}})
    with pytest.raises(ValueError, match="epochs"):
        _args(tmp_path, {"training": {"epochs": 0}})
