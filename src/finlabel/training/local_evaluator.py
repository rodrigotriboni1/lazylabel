"""Concrete local Transformers/PEFT evaluation over frozen trusted partitions."""
import hashlib
import json
import re
import time
from pathlib import Path
from uuid import uuid4

from finlabel.models.text_generation import RAW_SCORE_METHOD, TransformersTextGenerationBackend
from finlabel.domain.labeling.prediction import Prediction, PredictionError
from finlabel.labeling.service import _rules_match
from finlabel.training.backend import _artifact_tree_sha256
from finlabel.training.evaluation import fit_calibrator, labeling_policy_sha256
from finlabel.training.task_spec import task_spec_sha256

_SHA = re.compile(r"^[0-9a-f]{64}$")

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _read_partition(manifest, name):
    manifest_path = Path(manifest.manifest_path)
    if _sha(manifest_path) != manifest.manifest_sha256:
        raise ValueError("trusted_dataset_manifest_digest_mismatch")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    part = raw["partitions"][name]
    path = Path(manifest.manifest_path).parent / part["path"]
    if _sha(path) != part["dataset_sha256"]:
        raise ValueError("frozen_{}_dataset_digest_mismatch".format(name))
    refs = part.get("records")
    if not isinstance(refs, list) or len(refs) != part["count"] or not refs:
        raise ValueError("frozen_{}_record_refs_missing".format(name))
    reference_material = []
    seen = set()
    for ref in refs:
        if (not isinstance(ref, dict) or set(ref) != {"record_ref", "input_digest"}
                or not isinstance(ref["record_ref"], str) or not _SHA.fullmatch(ref["record_ref"])
                or ref["record_ref"] in seen or not isinstance(ref["input_digest"], str)
                or not _SHA.fullmatch(ref["input_digest"])):
            raise ValueError("frozen_partition_reference_invalid")
        seen.add(ref["record_ref"])
        reference_material.append({"input_digest": ref["input_digest"]})
    digest = hashlib.sha256(json.dumps(reference_material, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != part.get("sha256"):
        raise ValueError("frozen_partition_reference_digest_mismatch")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            item = json.loads(line)
            target = json.loads(item["completion"])
            if set(item) != {"prompt", "completion"} or set(target) != {"label"}:
                raise ValueError("frozen_partition_schema_invalid")
            rows.append((item["prompt"], target["label"]))
    if len(rows) != len(refs):
        raise ValueError("frozen_partition_row_count_mismatch")
    return raw, part, tuple((ref["record_ref"], ref["input_digest"], row[0], row[1])
                            for ref, row in zip(refs, rows))

def _model_identity(adapter_dir, task):
    base = task.model_id + ("@" + task.model_revision if task.model_revision else "")
    if adapter_dir is None:
        return None, {}, base, hashlib.sha256(base.encode("utf-8")).hexdigest()
    directory = Path(adapter_dir).expanduser().resolve()
    meta = json.loads((directory / "finlabel-training.json").read_text(encoding="utf-8"))
    if meta.get("base_model_ref") != base:
        raise ValueError("adapter_base_model_mismatch")
    tree_hash = _artifact_tree_sha256(directory)
    if meta.get("adapter_artifacts_sha256") != tree_hash:
        raise ValueError("adapter_artifact_digest_mismatch")
    return directory, meta, "{}+peft:{}".format(base, tree_hash), tree_hash

def _prompt_values(prompt, task):
    marker = "\nSelected input JSON: "
    prefix, separator, suffix = prompt.rpartition(marker)
    ending = "\nReturn one JSON object with a configured label."
    if not separator or not suffix.endswith(ending):
        raise ValueError("frozen_prompt_schema_invalid")
    values = json.loads(suffix[:-len(ending)])
    if not isinstance(values, dict) or set(values) != set(task.input_columns):
        raise ValueError("frozen_prompt_features_invalid")
    return values

def _score(rows, backend, task, policy, *, apply_rules=False):
    result = []
    for record_ref, input_digest, prompt, target in rows:
        if target not in task.labels:
            raise ValueError("trusted_target_outside_task_taxonomy")
        if apply_rules:
            try:
                values = _prompt_values(prompt, task)
            except Exception:
                result.append({"record_ref": record_ref, "input_digest": input_digest,
                               "prediction": None, "target": target,
                               "reason_code": "invalid_input", "confidence": None, "applied": False})
                continue
            if not _rules_match(policy.rules, values):
                result.append({"record_ref": record_ref, "input_digest": input_digest,
                               "prediction": None, "target": target,
                               "reason_code": "rule_conflict", "confidence": None, "applied": False})
                continue
        started = time.monotonic()
        try:
            prediction = backend.predict_prompt(prompt, task=task, max_new_tokens=256)
            if (not isinstance(prediction, Prediction) or prediction.label not in task.labels
                    or prediction.confidence_method != RAW_SCORE_METHOD
                    or prediction.confidence_evidence is None
                    or list(prediction.confidence_evidence) != list(task.labels)):
                raise PredictionError("Prediction or score evidence did not match the task.")
        except PredictionError as exc:
            result.append({"record_ref": record_ref, "input_digest": input_digest,
                           "prediction": None, "target": target,
                           "reason_code": exc.reason_code if exc.reason_code in {"unknown_label", "invalid_output"}
                           else "invalid_output", "confidence": None, "applied": False})
            continue
        except Exception:
            result.append({"record_ref": record_ref, "input_digest": input_digest,
                           "prediction": None, "target": target,
                           "reason_code": "backend_error", "confidence": None, "applied": False})
            continue
        result.append({"record_ref": record_ref, "input_digest": input_digest,
                       "prediction": prediction, "target": target,
                       "reason_code": "stale_source" if time.monotonic() - started > policy.max_staleness_seconds
                       else None, "confidence": None, "applied": False})
    return result

def _metrics(scored, calibrator, task, policy, model_ref):
    abstain = "__finlabel_abstain__"
    while abstain in task.labels:
        abstain += "_"
    confusion = {label: {other: 0 for other in (*task.labels, abstain)} for label in task.labels}
    confidences, correct = [], []
    for row in scored:
        pred, target = row["prediction"], row["target"]
        if pred is None:
            confusion[target][abstain] += 1
            row["applied"] = False
            row["confidence"] = None
            continue
        try:
            confidence = calibrator.calibrate(pred, task=task, policy=policy, model_ref=model_ref).confidence
        except Exception:
            row["prediction"] = None
            row["reason_code"] = "calibration_error"
            row["applied"] = False
            row["confidence"] = None
            confusion[target][abstain] += 1
            continue
        confusion[target][pred.label] += 1
        confidences.append(confidence)
        is_correct = float(pred.label == target)
        correct.append(is_correct)
        if row["reason_code"] is None and confidence >= policy.min_calibrated_confidence:
            row["applied"] = True
            row["reason_code"] = None
        elif row["reason_code"] is None:
            row["reason_code"] = "below_threshold"
        row["confidence"] = confidence
    total = len(scored)
    per_label, f1s = {}, []
    for label in task.labels:
        tp = confusion[label][label]
        fp = sum(confusion[truth][label] for truth in task.labels if truth != label)
        fn = sum(confusion[label][guess] for guess in (*task.labels, abstain) if guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        f1s.append(f1)
    accuracy = sum(correct) / total
    brier = sum((p - y) ** 2 for p, y in zip(confidences, correct)) / len(correct) if correct else 1.0
    ece = 0.0
    for index in range(10):
        bucket = [(p, y) for p, y in zip(confidences, correct)
                  if index / 10 <= p < ((index + 1) / 10 if index < 9 else 1.0000001)]
        if bucket:
            ece += len(bucket) / len(confidences) * abs(sum(y for _, y in bucket) / len(bucket) -
                                               sum(p for p, _ in bucket) / len(bucket))
    coverage = sum(bool(row["applied"]) for row in scored) / total
    return ({"accuracy": accuracy, "macro_f1": sum(f1s) / len(f1s), "brier_score": brier,
             "calibration_error": ece if correct else 1.0, "coverage": coverage}, per_label, confusion)

def evaluate_candidate(task, policy, dataset_manifest, candidate_adapter, incumbent_adapter, *,
                       workspace_dir, candidate_id, training_gate_path, training_gate_sha256):
    """Evaluate candidate/incumbent on identical frozen holdout and persist aggregate evidence.

    Calibrators live under models/calibrators/task/policy/model-digest.json. The policy calibration_ref
    is a stable policy slot, not a model digest; each artifact separately binds the exact model and data hashes.
    """
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_identity_required")
    if policy is None or policy.calibration_ref is None:
        raise ValueError("promotion_policy_calibration_slot_missing")
    if policy.task_id != task.task_id or tuple(policy.allowed_labels) != tuple(task.labels):
        raise ValueError("task_policy_mismatch")
    if (not isinstance(training_gate_path, (str, Path))
            or not isinstance(training_gate_sha256, str) or not _SHA.fullmatch(training_gate_sha256)):
        raise ValueError("training_gate_identity_missing")
    gate_path = Path(training_gate_path).expanduser().resolve()
    try:
        gate_matches = _sha(gate_path) == training_gate_sha256
    except OSError:
        gate_matches = False
    if not gate_matches:
        raise ValueError("training_gate_changed_during_cycle")
    raw, holdout_part, holdout_rows = _read_partition(dataset_manifest, "holdout")
    _, _, calibration_rows = _read_partition(dataset_manifest, "calibration")
    if raw.get("task_id") != task.task_id or raw.get("task_spec_sha256") != task_spec_sha256(task):
        raise ValueError("trusted_dataset_task_identity_mismatch")
    if raw.get("trust_kind") not in {"provided_ground_truth", "validated_rule"}:
        raise ValueError("trusted_label_provenance_missing")
    if not all(_SHA.fullmatch(row[0]) for row in holdout_rows):
        raise ValueError("frozen_holdout_opaque_refs_invalid")
    root = Path(workspace_dir).expanduser().resolve() / "models"
    models = []
    for role, adapter in (("candidate", candidate_adapter), ("incumbent", incumbent_adapter)):
        directory, meta, model_ref, adapter_hash = _model_identity(adapter, task)
        backend = TransformersTextGenerationBackend(task.model_id, task.model_revision,
                                                    adapter_path=str(directory) if directory else None,
                                                    model_ref=model_ref)
        calibration_scored = _score(calibration_rows, backend, task, policy)
        if any(row["prediction"] is None for row in calibration_scored):
            raise ValueError("calibration_partition_inference_incomplete")
        labels = {row["record_ref"]: row["target"] for row in calibration_scored}
        fitted = fit_calibrator([{"record_ref": row["record_ref"], "prediction": row["prediction"]}
                                 for row in calibration_scored], labels, method=RAW_SCORE_METHOD,
                                dataset_manifest=dataset_manifest, task=task, policy=policy,
                                model_ref=model_ref, calibration_ref=policy.calibration_ref)
        from finlabel.training.evaluation import CalibrationArtifact
        artifact_dir = root / "calibrators" / task.task_id / policy.policy_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / (adapter_hash + ".json")
        if artifact_path.exists():
            existing = CalibrationArtifact.load(artifact_path)
            if existing.to_dict() != fitted.to_dict():
                raise ValueError("calibration_artifact_collision")
        else:
            fitted.save(artifact_path)
        holdout_scored = _score(holdout_rows, backend, task, policy, apply_rules=True)
        metrics, per_label, confusion = _metrics(holdout_scored, fitted, task, policy, model_ref)
        score_material = [{"record_ref": row["record_ref"], "input_digest": row["input_digest"],
                           "target": row["target"],
                           "prediction": row["prediction"].label if row["prediction"] else None,
                           "scores": dict(row["prediction"].confidence_evidence) if row["prediction"] else None,
                           "confidence": row["confidence"], "applied": row["applied"],
                           "reason_code": row["reason_code"]}
                          for row in holdout_scored]
        score_digest = hashlib.sha256(json.dumps(score_material, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        models.append({"role": role, "model_ref": model_ref, "adapter_sha256": adapter_hash,
                       "adapter_path": str(directory) if directory else None, "calibrator_path": str(artifact_path),
                       "calibrator_sha256": _sha(artifact_path), "metrics": metrics,
                       "per_label": per_label, "confusion": confusion,
                       "holdout_records": score_material,
                       "holdout_scores_sha256": score_digest,
                       "calibration_brier": fitted.metrics["brier_score"],
                       "training_dataset_sha256": meta.get("dataset_sha256")})
    evaluation_id = uuid4().hex
    payload = {"schema_version": 1, "evaluation_id": evaluation_id,
               "evaluator": "finlabel-local-transformers-peft-v1", "task_id": task.task_id,
               "task_spec_sha256": task_spec_sha256(task), "policy_id": policy.policy_id,
               "policy_sha256": policy.policy_sha256,
               "labeling_policy_sha256": labeling_policy_sha256(policy),
               "score_method": RAW_SCORE_METHOD,
               "dataset_manifest_sha256": _sha(dataset_manifest.manifest_path),
               "holdout_dataset_sha256": holdout_part["dataset_sha256"], "holdout_sha256": holdout_part["sha256"],
               "holdout_count": len(holdout_rows), "same_frozen_holdout": True,
               "training_gate_sha256": training_gate_sha256,
               "trusted_label_provenance": {"source_name": raw["source_name"],
                   "provenance_id": raw["provenance_id"], "trust_kind": raw["trust_kind"],
                   "snapshot_sha256": raw["snapshot_sha256"]},
               "candidate_id": candidate_id, "candidate_model_ref": models[0]["model_ref"],
               "incumbent_model_ref": models[1]["model_ref"], "candidate_adapter_path": models[0]["adapter_path"],
               "candidate_calibrator_path": models[0]["calibrator_path"],
               "candidate_metrics": models[0]["metrics"], "candidate_per_label": {
                   key: value["f1"] for key, value in models[0]["per_label"].items()},
               "incumbent_metrics": models[1]["metrics"], "incumbent_per_label": {
                   key: value["f1"] for key, value in models[1]["per_label"].items()},
               "coverage": models[0]["metrics"]["coverage"],
               "calibration_error": models[0]["metrics"]["calibration_error"],
               "privacy": "opaque_refs_and_minimized_row_level_evaluation_evidence", "models": models}
    payload["evaluation_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    path = root / "evaluations" / (evaluation_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_registered_candidate(project, task, policy, candidate_id):
    """Evaluate one already-trained local registry candidate and make its gate decision."""
    from finlabel.training.autopipeline import _manifest_for
    from finlabel.training.registry import ModelRegistry
    from finlabel.training.trusted_labels import load_trusted_labels

    registry = ModelRegistry(project.workspace_dir)
    candidate = registry.candidate(candidate_id)
    if candidate.get("task_id") != task.task_id or candidate.get("status") != "training":
        raise ValueError("candidate_not_in_evaluable_training_state")
    gate_path = candidate.get("training_gate_path")
    gate_sha256 = candidate.get("training_gate_sha256")
    if (not isinstance(gate_path, str) or not gate_path or not isinstance(gate_sha256, str)
            or not _SHA.fullmatch(gate_sha256)):
        registry.transition(candidate_id, "rejected", rejection_reasons=["training_gate_identity_missing"])
        raise ValueError("candidate_training_gate_identity_missing")
    try:
        gate_matches = _sha(gate_path) == gate_sha256
    except OSError:
        gate_matches = False
    if not gate_matches:
        registry.transition(candidate_id, "rejected", rejection_reasons=["training_gate_missing_or_changed"])
        raise ValueError("candidate_training_gate_missing_or_changed")
    live_manifest = _manifest_for(load_trusted_labels(project, task), task, project.workspace_dir)
    if Path(candidate.get("trusted_manifest_path", "")).resolve() != live_manifest.manifest_path.resolve():
        raise ValueError("candidate_trusted_manifest_is_not_current_registered_snapshot")
    manifest = live_manifest
    active = registry.active(task.task_id)
    if not active or not active.get("adapter_path"):
        raise ValueError("incumbent_adapter_required_for_comparison")
    evaluation_path = evaluate_candidate(
        task, policy, manifest, candidate["adapter_path"], active["adapter_path"],
        workspace_dir=project.workspace_dir, candidate_id=candidate_id,
        training_gate_path=gate_path, training_gate_sha256=gate_sha256)
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if candidate.get("model_ref") != evaluation["candidate_model_ref"]:
        raise ValueError("candidate_registered_model_ref_mismatch")
    registry.transition(candidate_id, "evaluated",
                        evaluation_id=evaluation["evaluation_id"],
                        evaluation_sha256=_sha(evaluation_path),
                        candidate_model_ref=evaluation["candidate_model_ref"])
    decision = registry.promote_if_eligible(candidate_id, evaluation["evaluation_id"], policy)
    return evaluation, decision
