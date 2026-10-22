# FinLabel Autonomous Labeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-record human review with local automatic label application and automatic quarantine for invalid, conflicting, stale, or uncalibrated predictions.

**Architecture:** A task-scoped policy controls allowed labels, deterministic checks, and calibrated abstention. A shared Python service writes immutable outcome artifacts separate from read-only source data; CLI and web API consume those same results. Existing human-review events remain historical and are never silently treated as trusted supervision.

**Tech Stack:** Python 3.10+, existing `finlabel-local` package, CSV/SQLite read-only sources, local JSON/JSONL artifacts, Transformers model backend, FastAPI API.

**Spec:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`

## Global Constraints

- CSV and SQLite source data remain read-only.
- All model inference remains local; no source rows are sent to an external LLM.
- Model input contains only task-selected columns.
- Invalid, stale, conflicting, or uncalibrated outputs go to quarantine; no fallback label is fabricated.
- Model predictions never become trusted labels by themselves.
- Outcome artifacts store opaque record references, selected-field digests, model/task/policy provenance, state and reason codes; raw values/prompts are omitted by default.
- CLI, Python API, and web API call shared domain services.
- Preserve legacy review logs as historical artifacts; do not ingest them as trusted labels without an explicit trusted-source mapping.
- Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; do not add or run automated tests unless explicitly requested. Use synthetic data for manual checks.

## Review Focus

- Uncalibrated backend or missing confidence: every affected row is quarantined, never silently applied.
- Unknown label, malformed JSON, refusal, or timeout: row receives a stable reason code; unrelated rows can finish.
- Source changes between inference and result persistence: stale rows cannot be treated as applied or used for training.
- Duplicate record IDs or retries: output remains idempotent and does not duplicate a record outcome.
- Sensitive row values: default API/CLI summaries and event artifacts expose no selected values or prompt text.

---

## Stage and branch

Implement as the first reviewable delivery on branch `codex/finlabel-autonomous-labeling`, based on `codex/finlabel-integration`. Keep the long-lived combined work on `codex/finlabel-autonomous-mvp`; do not merge to the default branch. Save a manual synthetic run and branch-specific issue evidence before review.

### Task 1: Define task-scoped labeling policy

**Files:**
- Create: `src/finlabel/labeling/policy.py`
- Modify: `src/finlabel/labeling/task.py`
- Modify: `src/finlabel/project.py` only if the existing project artifact layout needs a new policy directory.
- Modify: `README.md` with the task policy schema and sample configuration.

**Interfaces:**
- Produce immutable `LabelingPolicy` with `policy_id`, `task_id`, `allowed_labels`, `rules_version`, `calibration_ref`, `min_calibrated_confidence`, and `max_staleness_seconds`.
- `load_policy(path, *, task: LabelTask) -> LabelingPolicy` validates policy/task ID and label agreement.
- Missing or uncalibrated policy must be represented as “cannot auto-apply,” not a permissive default.

- [ ] **Step 1:** Add the policy schema, validation errors, and JSON loader; manually inspect invalid/mismatched configuration messages with synthetic JSON.
- [ ] **Step 2:** Connect task loading to the optional task policy path without changing existing task labels or model identity semantics.
- [ ] **Step 3:** Document the policy fields and the fail-closed default; commit as `feat: define autonomous labeling policy`.

### Task 2: Normalize backend predictions and abstention evidence

**Files:**
- Create: `src/finlabel/labeling/prediction.py`
- Modify: `src/finlabel/models/text_generation.py`
- Modify: `src/finlabel/labeling/suggestions.py`
- Modify: `README.md` with backend prediction contract.

**Interfaces:**
- `Prediction(label: str | None, rationale: str | None, confidence_evidence: Mapping[str, float] | None, calibrated_confidence: float | None, calibration_ref: str | None, confidence_method: str | None, raw_output_digest: str)`.
- Model backend method `predict(selected_values, *, task, max_new_tokens) -> Prediction` returns parsed structured output and raw per-label score evidence; rationale is never confidence evidence.
- The labeling service accepts an optional task calibrator. It sets `calibrated_confidence` only when the calibration artifact matches policy, model, task and evidence method. No calibrator/evidence means quarantine.

- [ ] **Step 1:** Add normalized prediction types and finite-value validation for per-label raw scores and calibrated confidence; manually inspect JSON, malformed, unknown-label, and missing-score examples.
- [ ] **Step 2:** Adapt the Transformers backend to return structured output and per-label score evidence while preserving model revision and chat-template behavior. Never call raw scores calibrated probabilities.
- [ ] **Step 3:** Keep the prior text `generate` interface temporarily available for explicit legacy callers; document that the autonomous service uses `predict`.
- [ ] **Step 4:** Commit as `feat: expose structured local predictions`.

### Task 3: Persist applied and quarantined outcomes

**Files:**
- Create: `src/finlabel/labeling/outcomes.py`
- Modify: `src/finlabel/labeling/service.py`
- Modify: `src/finlabel/project.py` for `.finlabel/label-runs/` if required.

**Interfaces:**
- `LabelOutcome` records `run_id`, `record_ref`, `input_digest`, `task_id`, `policy_id`, `model_ref`, `predicted_label`, `state` (`applied` or `quarantined`), `reason_code`, `confidence`, and UTC timestamp.
- `run_labeling(source, task, policy, backend, *, workspace_dir, calibrator=None) -> LabelRunSummary` writes `outcomes.jsonl` and `run.json` atomically and does not mutate `source`.
- Stable reason codes include `invalid_output`, `unknown_label`, `rule_conflict`, `uncalibrated`, `below_threshold`, `stale_source`, `backend_error`, and `missing_policy`.

- [ ] **Step 1:** Add the outcome schema and atomic writer; manually inspect that an outcome artifact contains no raw values or prompt.
- [ ] **Step 2:** Implement row-level state decisions: apply only when parsing, task validation, policy rules, freshness, and a matching calibrator all pass; otherwise quarantine with one reason code. Until the trusted-training stage adds a real calibrator, valid Qwen outputs must remain quarantined as `uncalibrated`.
- [ ] **Step 3:** Make duplicate/retried record outcomes idempotent within a run and keep processing independent rows after recoverable per-row failures.
- [ ] **Step 4:** Manually run a 4-row synthetic CSV containing valid but uncalibrated, malformed, unknown-label, and stale cases; confirm reasons, read-only source, and artifacts contain no values. Verify applied outcomes after stage 2 supplies a fitted calibrator.
- [ ] **Step 5:** Commit as `feat: persist autonomous labeling outcomes`.

### Task 4: Make the CLI execute the autonomous service

**Files:**
- Modify: `src/finlabel/cli.py`
- Modify: `README.md`

**Interfaces:**
- Existing `finlabel label SOURCE --task TASK --project PATH` calls `run_labeling` and prints counts, artifact path, policy/model refs, and quarantine reason counts only.
- Add `finlabel label-run RUN_ID --project PATH` to read summary metadata without row values.
- Do not require `finlabel review` for a run to be complete.

- [ ] **Step 1:** Route the current `label` command through `run_labeling`; fail closed with an actionable message when policy/calibration is missing.
- [ ] **Step 2:** Add a summary command that reads a run artifact and never prints row values.
- [ ] **Step 3:** Manually invoke both commands against the synthetic project and verify output/artifact consistency.
- [ ] **Step 4:** Commit as `feat: expose autonomous labeling in CLI`.

## Manual completion evidence

- A synthetic run safely quarantines valid-but-uncalibrated and invalid rows with reasons and model/policy provenance; the applied path stays disabled until the calibrator exists in stage 2.
- The CSV/SQLite source hash/content is unchanged.
- Default CLI/API summaries and outcome JSONL contain no source values or prompts.
- The task cannot silently auto-apply when no calibration policy exists.
