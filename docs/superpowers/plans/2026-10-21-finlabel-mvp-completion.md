# FinLabel MVP Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Complete the approved autonomous FinLabel MVP, integrate its Python/CLI and React/shadcn local panel, close automatic rollback, and verify every supported flow with automated and local-model evidence.

**Architecture:** Keep CSV/SQLite read-only and share domain services between Python, CLI, and FastAPI. Deterministic rules handle data quality, metrics, policy gates, and lifecycle decisions; local models propose labels and train only on explicitly trusted, frozen partitions. Integrate each deliverable on its own review branch, then combine them on `codex/finlabel-autonomous-mvp` without merging to `main`.

**Tech Stack:** Python 3.10+, pytest, FastAPI, SQLite/CSV, Transformers, TRL, PEFT/LoRA, React 19, TypeScript, Vite, shadcn-style UI components, Recharts, Playwright or browser-based manual QA.

**Spec:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md` and the approved dashboard design in `docs/superpowers/specs/2026-10-25-finlabel-analytics-dashboard-design.md`; retain analytics and connector requirements from `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md` and `codigo/finlabel/.worktrees/autonomous-mvp/README.md`.

## Global Constraints

- Source CSV and SQLite connections remain read-only.
- Raw source rows, prompts, and feature values stay local; only explicitly approved metadata may be sent to an optional external onboarding model.
- Without a valid task policy and calibration evidence, predictions are quarantined.
- Only configured trusted labels can enter train, calibration, and holdout partitions; never use model predictions as ground truth.
- Training uses only the frozen train partition; calibration and holdout are disjoint and immutable for a cycle.
- Promotion and rollback use task-specific, versioned gates; missing or invalid gates fail closed and there are no universal thresholds.
- No automatic scheduling or daemon is added; the autonomous cycle is started by the user through CLI or panel.
- The approved operational flow has no per-row human approval. Legacy review artifacts remain readable for compatibility.
- Hashes provide integrity within the local single-user workspace; they are not cryptographic proof of who produced or approved data.
- Use synthetic/local fixtures for automated tests and the existing approved Qwen synthetic experiment for the real-model smoke run; do not use personal or financial source data.
- User explicitly requested automated tests in this task, which authorizes adding and running them despite the previous LOOP restriction. Update the LOOP text so that this authorization is reflected for this completion effort.

## Review Focus

- Missing or stale policy/calibration must quarantine all affected predictions and never silently accept them; test absent, mismatched, and expired artifacts.
- Holdout leakage or edited data/evidence/gates must block evaluation or promotion; test duplicate, missing, extra, reordered, and mutated records and post-evaluation gate changes.
- Rollback input must be tied to the exact active candidate, policy, and trusted evaluation evidence; test forged, stale, undersized, failing, and passing health evidence.
- Source mutation between inference and publish must quarantine changed records without writing to the source; test CSV and SQLite mutation and read-only behavior.
- Web requests must not expose row values or mutate state without CSRF/origin validation; test privacy, host/origin, CSRF, request-size, and path-containment boundaries.

---

## File Map

- `codigo/finlabel/src/finlabel/labeling/`: task policy, prediction, autonomous outcome, and batch labeling contracts.
- `codigo/finlabel/src/finlabel/training/`: trusted labels, frozen splits, evaluator, calibrator, registry, promotion, and rollback.
- `codigo/finlabel/src/finlabel/cli.py`: commands invoking the shared autonomous services and privacy-safe summaries.
- `codigo/finlabel/src/finlabel/web/`: local HTTP API, bundled React assets, and panel routes.
- `codigo/finlabel/frontend/src/`: React/shadcn-style panel screens, API client, and training workflow diagram.
- `codigo/finlabel/tests/`: Python domain, lifecycle, CLI, and API tests; add focused test modules where the current suite has gaps.
- `codigo/finlabel/frontend/`: frontend unit/component test configuration and scripts.
- `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`: mark the original human-review workflow as superseded by the approved autonomous design while preserving its history.
- `.scratch/biblioteca-rotulagem-financeira/LOOP.md` and `issues/`: record the explicit test authorization, updated scope, branch, checks, and evidence for each completed issue.

## Branch and Delivery Sequence

Create/reuse one branch per independently reviewable deliverable, all based on the latest approved integration point; integrate completed branches into `codex/finlabel-autonomous-mvp`. Keep `main` unchanged. Suggested branch names:

1. `codex/finlabel-autonomous-contract-tests`
2. `codex/finlabel-training-rollback`
3. `codex/finlabel-local-model-compat`
4. `codex/finlabel-dashboard-redesign`
5. `codex/finlabel-autonomous-panel`
6. `codex/finlabel-full-verification`

After each branch passes its focused checks, review it independently, integrate it, and run the relevant combined checks before starting the next dependent deliverable.

## Implementation Tasks

### Task 0: Redesign the analysis panel with KPIs and a category-by-period heatmap

**Files:**
- Modify: `codigo/finlabel/frontend/src/pages/AnalysisPage.tsx`
- Modify: `codigo/finlabel/frontend/src/App.tsx` and shared UI styles as needed
- Create: `codigo/finlabel/frontend/src/components/analysis/MetricSummary.tsx`
- Create: `codigo/finlabel/frontend/src/components/analysis/CategoryPeriodHeatmap.tsx`
- Create: `codigo/finlabel/frontend/src/components/analysis/AnalysisResults.test.tsx`
- Modify: `codigo/finlabel/frontend/package.json` and test configuration
- Modify: `codigo/finlabel/tests/test_analysis_service.py` only if result metadata needs a deterministic addition

**Interfaces:** Consume the existing `AnalysisResponse` (`rows`, `plan`, `formula_metadata`, invalid-value counts, and valid-row count when available). KPI and heatmap rendering must be pure derived views over persisted deterministic analysis output. Add no KPI that needs a denominator absent from the response.

- [ ] Step 1: Add frontend test tooling and failing component tests for valid-row count, period range, leading category, change in percentage points for shares, zero-baseline relative change omission, missing cells, and accessible non-color value labels.
- [ ] Step 2: Run the focused tests and confirm the expected failures.
- [ ] Step 3: Implement context-aware KPI cards and a category × explicit period heatmap. Use an accessible table alternative, preserve missing cells as missing, and enforce a visible display limit.
- [ ] Step 4: Move the full editable analysis JSON into a collapsed “Avançado” section; preserve exact plan submission and existing chart/table results.
- [ ] Step 5: Apply a restrained shared visual system to the panel without removing the seven-stage training diagram or any existing route.
- [ ] Step 6: Run frontend unit tests, `npm run build`, `npm run lint`, and the Python analysis service tests; commit on `codex/finlabel-dashboard-redesign`.
- [ ] Step 7: Verify `/analysis` and `/training` at 1440×900 and 390×844; capture evidence and commit the QA report.

### Task 1: Align the canonical scope and capture autonomous contract tests

**Files:**
- Modify: `.scratch/biblioteca-rotulagem-financeira/LOOP.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/issues/19-rotulos-confiaveis-calibracao-treino-autonomo.md`
- Create/modify: `codigo/finlabel/tests/test_labeling_policy.py`
- Create/modify: `codigo/finlabel/tests/test_label_outcomes.py`
- Create/modify: `codigo/finlabel/tests/test_autonomous_pipeline.py`

**Interfaces:** Consume `LabelingPolicy`, `LabelOutcome`, `suggest_labels`, and `run_autonomous_cycle` as currently defined. Preserve legacy review APIs while pinning autonomous behavior as the default operational path.

- [ ] Step 1: Add failing tests proving missing policy/calibrator quarantines predictions, valid configured predictions apply, invalid labels/rule conflicts quarantine, and records changed before publish are quarantined.
- [ ] Step 2: Add failing tests proving autonomous outcomes contain no source values, prompt text, or free-form rationale and that aggregate summaries recompute from the immutable outcome file.
- [ ] Step 3: Run the focused new tests and confirm failures identify missing behavior or regressions.
- [ ] Step 4: Make the smallest service changes needed to satisfy the tests without changing read-only source behavior.
- [ ] Step 5: Update LOOP to record the user's explicit authorization for a complete implementation and automated test campaign; update the older MVP spec as superseded and link the approved autonomy spec.
- [ ] Step 6: Run `python -m pytest tests/test_labeling_policy.py tests/test_label_outcomes.py tests/test_autonomous_pipeline.py -q` and commit on `codex/finlabel-autonomous-contract-tests`.

### Task 2: Complete trusted-data, evaluation, and training-cycle coverage

**Files:**
- Create/modify: `codigo/finlabel/tests/test_trusted_labels.py`
- Create/modify: `codigo/finlabel/tests/test_training_split.py`
- Create/modify: `codigo/finlabel/tests/test_local_evaluator.py`
- Create/modify: `codigo/finlabel/tests/test_autopipeline.py`
- Modify as needed: `codigo/finlabel/src/finlabel/training/{trusted_labels,split,evaluation,local_evaluator,autopipeline}.py`

**Interfaces:** `load_trusted_labels(...)` returns validated trusted records plus a snapshot manifest; split creation yields immutable train/calibration/holdout JSONL and manifest; `evaluate_candidate(...)` binds candidate and incumbent evidence to identical holdout rows; `run_autonomous_cycle(...)` returns a persisted cycle summary.

- [ ] Step 1: Test trusted-source registration and reload against CSV and SQLite, including duplicate/missing IDs, invalid mappings, in-source model outputs, excluded label columns, and source snapshot drift.
- [ ] Step 2: Test deterministic splits, minimum per-label counts, disjoint partitions, stable group IDs, and rejection of edited or reordered partition artifacts.
- [ ] Step 3: Test calibration and holdout metric recomputation, coverage denominator including abstentions, per-label gates, malformed predictions, and candidate/incumbent exact row binding.
- [ ] Step 4: Test training gate absent/malformed/changed after training and prove a failed cycle preserves the active model pointer.
- [ ] Step 5: Implement only failures demonstrated by the tests; keep thresholds task-specific and require explicit provenance.
- [ ] Step 6: Run the four focused test modules and commit on the training-cycle branch before integrating.

### Task 3: Implement verifiable post-promotion health rollback

**Files:**
- Modify: `codigo/finlabel/src/finlabel/training/registry.py`
- Modify: `codigo/finlabel/src/finlabel/training/autopipeline.py`
- Create: `codigo/finlabel/tests/test_training_rollback.py`
- Modify: `codigo/finlabel/docs/verified-training-cycle.md`

**Interfaces:** Replace the unconditional `trusted_health_evaluator_attestation_unavailable` rejection with `rollback_if_unhealthy(task_id, health_evaluation) -> PromotionEvent`. The health evaluation must bind the exact active model reference, previous verified model, promotion-policy digest, trusted data snapshot, evaluation ID, evaluated count, and recomputable row evidence. Recompute configured metrics locally; rollback only when all required evidence validates and a configured rollback limit is violated.

- [ ] Step 1: Test a healthy evaluation leaves the active pointer and journal unchanged.
- [ ] Step 2: Test a valid unhealthy evaluation atomically restores the previous verified adapter/calibrator and appends exactly one rollback event.
- [ ] Step 3: Test missing previous version, missing or stale trusted labels, too few rows, active-model mismatch, policy change, corrupt row evidence, already-rolled-back replay, concurrent rollback, and write failure; each invalid case must fail closed and preserve the current pointer.
- [ ] Step 4: Implement evidence validation and metric recomputation using the same evaluation primitives as promotion; make the decision idempotent under the registry lock and recoverable from the event journal.
- [ ] Step 5: Document the local trust boundary and that rollback is evidence-based, not an external cryptographic attestation.
- [ ] Step 6: Run `python -m pytest tests/test_training_rollback.py tests/test_autopipeline.py -q` and commit on `codex/finlabel-training-rollback`.

### Task 4: Make the trained model usable by the supported inference path

**Files:**
- Modify: `codigo/finlabel/src/finlabel/models/text_generation.py`
- Modify: `codigo/finlabel/src/finlabel/training/backend.py`
- Modify: `codigo/finlabel/src/finlabel/training/active_model.py`
- Create/modify: `codigo/finlabel/tests/test_model_chat_template.py`
- Update evidence: `.scratch/biblioteca-rotulagem-financeira/experiments/qwen25-05b-synthetic-2026-10-20/`

**Interfaces:** Local generation and training must use the selected tokenizer's chat template when present, with the same structured task prompt contract and generation settings recorded in model metadata. Loading an active adapter must verify the base model ID/revision, adapter files, tokenizer/template identity, and matching calibrator before inference.

- [ ] Step 1: Add fake-tokenizer tests showing chat-template models receive template-rendered messages and models without a template use the documented fallback; assert no unselected source columns are serialized.
- [ ] Step 2: Add tests for active adapter/base revision mismatch, corrupted adapter metadata, missing calibrator, and calibrated score identity.
- [ ] Step 3: Implement compatibility and metadata checks without downloading weights during the unit suite.
- [ ] Step 4: Run focused model tests, then reuse the already downloaded Qwen2.5-0.5B-Instruct artifact and the existing synthetic train/heldout dataset to reproduce a current FinLabel local inference/evaluation smoke run. Do not include personal source data.
- [ ] Step 5: Record exact command, package versions, model revision, device, elapsed time, metrics, and limitations. If this environment cannot reproduce the run, record the concrete blocker and keep unit tests fully offline.
- [ ] Step 6: Commit on `codex/finlabel-local-model-compat` and integrate only after evidence is reviewable.

### Task 5: Finish the React/shadcn autonomous panel and API parity

**Files:**
- Integrate: `codigo/finlabel/.worktrees/react-package-final/frontend/` into the autonomous integration branch.
- Modify: `codigo/finlabel/src/finlabel/web/app.py`
- Modify: `codigo/finlabel/frontend/src/pages/{OverviewPage,LabelingPage,MonitorPage,AnalysisPage,TrainingPage}.tsx`
- Modify: `codigo/finlabel/frontend/src/lib/api.ts`
- Add: `codigo/finlabel/frontend/src/pages/*` component tests and test configuration.
- Add/modify: `codigo/finlabel/tests/test_web_autonomous.py`

**Interfaces:** React pages call the same CLI/domain services through FastAPI. Provide privacy-safe APIs for autonomous run, aggregate run status, monitor results, analysis plans/results, active model, cycle history, candidate evaluation, promotion/rejection, and rollback status. No endpoint may require a per-row human decision for the autonomous flow.

- [ ] Step 1: Add API tests for CLI-equivalent autonomous run/status, monitor, analysis, and training-cycle actions, including CSRF/origin/host checks, malformed input, idempotency, and absence of raw row values.
- [ ] Step 2: Add React component tests for empty/loading/success/error/quarantine states, mobile navigation, and the seven-stage training diagram (validate data → split → train → evaluate → decide → promote/reject → rollback).
- [ ] Step 3: Replace review-as-primary workflow with run history, applied/quarantine counts and reasons, active model, cycle metrics, automatic promotion/rollback history, and links to deterministic analysis charts. Keep legacy review artifacts accessible only as historical data.
- [ ] Step 4: Integrate the package from the existing React branch, including shadcn-style components and Recharts, and package built assets for local FastAPI serving.
- [ ] Step 5: Run `python -m pytest tests/test_web_autonomous.py -q`, `npm run build`, and `npm run lint` in `codigo/finlabel/frontend`.
- [ ] Step 6: Open all panel routes directly and via navigation at 1440×900 and 390×844; verify refresh, diagram accessibility/state, no horizontal overflow, and no broken chart; save screenshots/report and commit on `codex/finlabel-autonomous-panel`.

### Task 6: Complete analysis, connectors, and end-to-end privacy tests

**Files:**
- Create/modify: `codigo/finlabel/tests/test_analysis_edge_cases.py`
- Create/modify: `codigo/finlabel/tests/test_cli_end_to_end.py`
- Modify if needed: `codigo/finlabel/src/finlabel/analysis/{planner,engine,service,charts}.py`
- Modify if needed: `codigo/finlabel/src/finlabel/sources/{csv_source,sqlite_source}.py`

**Interfaces:** Both CLI and panel use validated `AnalysisPlan` and the deterministic analysis engine; accepted operations are trend, group comparison, and composition/share with explicit measure, dimension, period, and denominator. CSV/SQLite sources stay read-only.

- [ ] Step 1: Test missing/ambiguous mappings, invalid dates/numbers, zero/negative denominators, empty groups, nulls, large input streams, and bounded chart/table outputs.
- [ ] Step 2: Test CSV and SQLite end-to-end analysis and schema monitoring, including read-only source hashes before/after and no raw rows in saved result artifacts.
- [ ] Step 3: Test full CLI flows in a temporary project: source/task setup, schema/monitor, analysis/chart, autonomous labeling, status, trusted dataset creation, training-cycle block/pass, and rollback status.
- [ ] Step 4: Run focused analysis/source/CLI tests and integrate on the main autonomous work branch.

### Task 7: Run the complete verification matrix and publish review evidence

**Files:**
- Modify: `codigo/finlabel/README.md`
- Modify: `codigo/finlabel/docs/verified-training-cycle.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/issues/*.md`
- Create: `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md` and evidence captures.

- [ ] Step 1: Run the full Python suite with the project test dependencies: `python -m pytest -q`.
- [ ] Step 2: Run static checks: `python -m compileall -q src/finlabel`, `git diff --check`, frontend `npm run build`, and `npm run lint`.
- [ ] Step 3: Run the frontend component/API suite and full web integration flow with only temporary synthetic project data.
- [ ] Step 4: Re-run the local Qwen synthetic smoke using the integrated branch; record whether it agrees with the existing experiment within deterministic settings, without treating synthetic scores as financial validation.
- [ ] Step 5: Have an independent reviewer inspect the integrated diff and evidence-binding, privacy, promotion, rollback, and user-visible autonomous workflow; resolve all blocking findings and rerun affected checks.
- [ ] Step 6: Update README and autonomous design docs to match shipped CLI/web commands and accurately state model/test limits. Update each issue with branch, commit, behavior, checks, evidence, and remaining limits; apply `ready-for-human` for review.
- [ ] Step 7: Produce a final report listing branches, commits, tests and results, screenshots, real-model run evidence, and any unverified boundary. Leave `main` unchanged for the user's branch-by-branch review.

## Completion Criteria

- Autonomous labeling applies only policy-valid, calibrated outputs and quarantines every uncertain or invalid case.
- Trusted-label partitions remain isolated and bound to the exact task, policy, dataset snapshot, evaluator evidence, and model artifacts.
- A candidate promotes only after every configured task gate passes; verified post-promotion health failures restore the previous verified model exactly once.
- CLI and React/shadcn panel offer equivalent autonomous operations and privacy-safe histories; the training diagram has seven accessible stages.
- Trend, group comparison, and share calculations are deterministic and require an explicit denominator definition.
- CSV/SQLite sources remain unchanged; no raw row is exposed in logs, web summaries, or external calls.
- Python, web/API, and frontend automated checks pass; manual responsive QA and local synthetic-model smoke evidence are captured.
- Each implementation stage remains reviewable on its own branch, integrated work is available on `codex/finlabel-autonomous-mvp`, and `main` is not merged or altered.
