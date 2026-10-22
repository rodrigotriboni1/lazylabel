# Verified local training cycle

The finlabel run command uses the configured task policy to label the current read-only source, then runs one local training cycle. The cycle:

1. Loads the one explicitly registered trusted-label source for the task. A changed source snapshot requires the existing explicit supervision refresh action.
2. Reuses or creates the immutable train, calibration, and holdout partitions under .finlabel/trusted-datasets/<task>/<snapshot-sha256>/.
3. Requires .finlabel/training-gate.json, the task labeling policy, and .finlabel/models/promotion-policies/<task>.json. Training uses only the train partition.
4. Fits separate candidate and incumbent calibrators on the same frozen calibration partition.
5. Runs candidate and incumbent Transformers/PEFT inference on the same frozen holdout with label_json_mean_log_likelihood_v2.
6. Applies every configured task policy gate. A failure leaves .finlabel/models/active-models.json unchanged. Missing or invalid prerequisites record a blocked cycle.

Before the first promotion, the incumbent is the task's exact base model and revision. Later evaluations use the active adapter as incumbent. A promotion compares both models on identical frozen calibration and holdout rows.

An unchanged trusted snapshot and promotion policy are processed once. A changed source snapshot or promotion-policy digest creates a new cycle. A blocked cycle may be retried after its prerequisite is corrected.

## Task-specific gates

Create .finlabel/models/promotion-policies/<task>.json with exactly these fields:

    {
      "task_id": "risk",
      "version": "risk-policy-2026-01",
      "required_metrics": {"macro_f1": 0.8},
      "minimum_coverage": 0.95,
      "allowed_per_label_regression": {"low": 0.02, "medium": 0.02, "high": 0.01},
      "max_calibration_error": 0.08,
      "rollback_monitor_limits": {"accuracy": 0.75},
      "min_holdout_count": 30
    }

The values above illustrate the schema only. Choose metric names and thresholds for the task's evaluation protocol and evidence; FinLabel does not supply universal thresholds. Supported evaluator metrics are accuracy, macro_f1, brier_score, calibration_error, and coverage. Per-label regression gates compare F1 for every named task label. A metric omitted from required_metrics is not given an implicit minimum.

The existing training gate remains explicit and local. It must include the approved model_id, license, hardware, data_policy, evaluation_protocol, and authorized: true. The cycle uses the task's exact base model ID and revision; mismatches fail closed.

## Calibration reference and artifact location

The task labeling policy's calibration_ref is a stable policy slot such as risk-confidence-v1. It does not identify a particular model or file. For each exact model, evaluation writes an immutable artifact to:

.finlabel/models/calibrators/<task>/<policy-id>/<model-digest>.json

The artifact binds that slot to the exact task specification, full labeling-policy digest, model reference, ordered labels, score method, and calibration partition/manifest/data hashes. Candidate and incumbent artifacts use different model digests and never overwrite each other. Active inference loads the artifact recorded with the promoted adapter and verifies the model reference and full policy digest before applying labels. A missing, malformed, or mismatched calibrator leaves predictions quarantined or blocks the run.

## Evaluation evidence and local data

Evaluation JSON is stored at .finlabel/models/evaluations/<evaluation-id>.json. It contains content hashes, task/policy/model identities, confusion counts, per-label metrics, calibration metrics, and artifact paths. It does not contain prompts, feature values, rationales, source record IDs, or per-row predictions. Frozen JSONL partitions and model/calibration artifacts remain in the local project workspace.

The promoted active pointer stores the adapter reference and its matching calibrator path. The next label or run command loads that adapter over the task's exact base model. The current run labels first and trains second, so a promotion affects subsequent runs.

## Manual validation boundary

compileall and git diff --check validate source syntax and patch formatting. No weights were downloaded and no real trusted dataset was evaluated as part of this implementation. Promotion evidence is therefore not claimed until a project runs the configured local cycle.
