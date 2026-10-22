# FinLabel Trusted Training and Automatic Promotion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train, evaluate, and promote adapters in batches without per-row or per-model human approval, using only task-configured trusted labels and preconfigured evaluation gates.

**Architecture:** Add a separately configured trusted-label source that maps a source column to task labels and records its provenance. A local orchestrator validates provenance, splits data into train/calibration/frozen holdout, trains an isolated candidate, evaluates it against the active version, and promotes or rejects it automatically according to versioned task gates.

**Tech Stack:** Existing FinLabel Python package, CSV/SQLite read-only connectors, Transformers, PEFT/LoRA, existing dataset/split/evaluation/model registry services, local JSON/JSONL artifacts.

**Spec:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`

## Global Constraints

- Depends on and consumes the task/policy and immutable outcome contracts from `2026-10-21-finlabel-autonomous-labeling.md`.
- Source data remains read-only; trusted labels are imported from a separately configured source column.
- Model-generated predictions are never trusted labels, calibration truth, or holdout truth.
- Split train/calibration/frozen holdout before fine-tuning; no candidate may train on calibration or holdout records.
- Task-specific quality gates are required; do not introduce universal thresholds.
- Automatic promotion occurs only after all configured gates pass; failure keeps the active model unchanged.
- Keep candidate, evaluation, promotion, rejection, and rollback events local and append-only with artifact hashes.
- Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; do not add or run automated tests unless explicitly requested. Use synthetic fixtures for manual checks.

## Review Focus

- Trusted label column is accidentally passed as model input: it must be excluded from selected input columns and prompts.
- Model-generated labels are imported as trusted: provenance validation must reject them.
- Duplicate, missing, stale, or unknown reference records: block dataset eligibility with explicit counts/reasons.
- Holdout leakage or altered gates after evaluation: candidate must not promote.
- Candidate failure or post-promotion regression: preserve or restore the previous active version.

---

## Stage and branch

Implement after the autonomous labeling core is reviewed, on `codex/finlabel-trusted-training` based on the reviewed autonomous core branch. Integrate into `codex/finlabel-autonomous-mvp` after stage review. Do not merge to the default branch.

### Task 1: Define trusted label source and provenance

**Files:**
- Create: `src/finlabel/training/trusted_labels.py`
- Modify: `src/finlabel/project.py` and `src/finlabel/sources/base.py` only for reusable source configuration fields.
- Modify: `src/finlabel/cli.py` for trusted-source registration.
- Modify: `README.md` with a sample trusted-label declaration.

**Interfaces:**
- `TrustedLabelSourceSpec(source_name, task_id, label_column, label_mapping, provenance_id, trust_kind)`.
- `trust_kind` accepts only explicit configured values such as `provided_ground_truth` or `validated_rule`; it cannot be set by model inference.
- `load_trusted_labels(project, task) -> TrustedLabelBatch` validates source read-only capability, label mapping, stable IDs, selected fields, and digest.
- CLI: `finlabel supervision add SOURCE --task TASK --label-column COL --provenance ID --trust-kind KIND --project PATH`.

- [ ] **Step 1:** Add the trusted-source schema and validation; manually inspect missing mapping, unknown label, source ID, and model-output provenance failures.
- [ ] **Step 2:** Implement a loader that selects only configured feature columns plus the label column and excludes the label column from model input.
- [ ] **Step 3:** Persist the configuration and source snapshot/digest without copying raw records into logs.
- [ ] **Step 4:** Manually register a synthetic CSV with a reference column and confirm the original file remains unchanged.
- [ ] **Step 5:** Commit as `feat: register trusted label sources`.

### Task 2: Build trusted training and calibration partitions

**Files:**
- Modify: `src/finlabel/training/dataset.py`
- Modify: `src/finlabel/training/quality.py`
- Modify: `src/finlabel/training/split.py`
- Modify: `src/finlabel/training/evaluation.py`

**Interfaces:**
- `prepare_trusted_dataset(batch, task, *, workspace_dir) -> TrustedDatasetManifest` records source/provenance IDs, input/label column mapping, snapshot hash, counts and label coverage.
- Extend split bundle manifest with explicit `train`, `calibration`, and frozen `holdout` hashes/counts.
- `fit_calibrator(calibration_predictions, trusted_labels, *, method) -> CalibrationArtifact` records method, version, source hashes and calibration metrics.
- Any missing provenance, stale digest, duplicate ID, or insufficient class coverage blocks training/calibration.

- [ ] **Step 1:** Implement dataset manifest/provenance for trusted labels and ensure model outcome artifacts are rejected as source data.
- [ ] **Step 2:** Add deterministic train/calibration/holdout splitting with a recorded seed or temporal/group strategy.
- [ ] **Step 3:** Fit and persist only a backend-supported calibrator from the calibration partition; if the backend cannot supply calibration evidence, policy remains unable to auto-apply predictions.
- [ ] **Step 4:** Manually inspect manifests to confirm label column values are absent from inference prompts and holdout records do not occur in training data.
- [ ] **Step 5:** Commit as `feat: prepare trusted train and calibration data`.

### Task 3: Orchestrate candidate training and automatic promotion

**Files:**
- Create: `src/finlabel/training/autopipeline.py`
- Modify: `src/finlabel/training/jobs.py`
- Modify: `src/finlabel/training/registry.py`
- Modify: `src/finlabel/training/evaluation.py`

**Interfaces:**
- `run_training_cycle(project, task_id, *, backend_factory) -> TrainingCycleSummary` discovers a configured trusted dataset, checks minimum counts, trains an isolated candidate, evaluates it, and writes one cycle manifest.
- `PromotionPolicy` specifies per-task required metrics, minimum coverage, allowed per-label regression, calibration limits, and rollback monitor limits; missing fields block promotion.
- `promote_if_eligible(candidate_id, evaluation_id, policy) -> PromotionEvent` is idempotent and never accepts a `confirm` flag.
- Candidate status transitions: `queued -> training -> evaluated -> promoted|rejected`; failures never change the active pointer.

- [ ] **Step 1:** Implement the training-cycle state machine and make prerequisites fail closed with recorded reason codes.
- [ ] **Step 2:** Run the existing LoRA backend only against the train partition and record hashes/configuration.
- [ ] **Step 3:** Evaluate active model and candidate on the same frozen holdout; apply every configured per-task gate.
- [ ] **Step 4:** Promote a candidate automatically only after all gates pass; manually force a synthetic failing candidate and confirm the active version is unchanged.
- [ ] **Step 5:** Add post-promotion health evaluation and automatic rollback to the previous verified version when configured monitor gates fail.
- [ ] **Step 6:** Commit as `feat: automate trusted training and model promotion`.

### Task 4: Add one-shot autonomous pipeline command

**Files:**
- Modify: `src/finlabel/cli.py`
- Modify: `src/finlabel/labeling/service.py` only to expose the shared completion event to the training coordinator.
- Modify: `README.md`

**Interfaces:**
- CLI: `finlabel run --task TASK --source SOURCE --project PATH` executes autonomous labeling and then checks whether a trusted training cycle is eligible.
- `finlabel run-status RUN_ID --project PATH` prints only run, training, promotion, and quarantine summary metadata.
- The one-shot command is explicitly started by a developer; continuous daemon scheduling is outside this MVP.

- [ ] **Step 1:** Connect one-shot run to labeling and training-cycle services without making inference predictions eligible as supervision.
- [ ] **Step 2:** Emit a combined summary with labels applied/quarantined, training skipped/rejected/promoted, model version, and artifact paths.
- [ ] **Step 3:** Manually execute synthetic cases for (a) no trusted labels, (b) insufficient trusted labels, (c) gate failure, and (d) successful candidate promotion; verify the previous model pointer in failure cases.
- [ ] **Step 4:** Commit as `feat: run autonomous labeling and training cycle`.

## Manual completion evidence

- A trusted reference source can be mapped without modifying it; model inputs exclude its target column.
- Predictions never enter the training/calibration/holdout labels as truth.
- Missing/insufficient trusted labels blocks automatic training.
- Failed evaluation preserves the active model; passing evaluation promotes with a complete local manifest.
- Rollback restores the prior model using a recorded health-gate event.
