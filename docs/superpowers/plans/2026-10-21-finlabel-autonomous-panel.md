# FinLabel Autonomous CLI and Panel Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CLI and local React/shadcn panel operate and explain the autonomous labeling/training workflow without per-record review or manual promotion controls.

**Architecture:** FastAPI endpoints expose summaries and state from the shared Python domain services. The CLI and panel render applied/quarantined counts, reasons, trusted-data eligibility, evaluation gates, promotions and rollback events. Legacy review artifacts remain readable as history but are not part of new runs.

**Tech Stack:** Python/FastAPI, React, Vite, shadcn/ui components already present, local JSON artifacts, existing FinLabel CLI.

**Spec:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`

## Global Constraints

- Depends on `2026-10-21-finlabel-autonomous-labeling.md` and `2026-10-21-finlabel-trusted-training.md` contracts.
- `/labeling`, `/training`, CLI and Python API show identical domain state from shared services.
- No accept/edit/reject/skip controls in the operational label flow; no manual activation confirmation in automatic cycles.
- Preserve source read-only behavior, local-only operations, raw-value minimization, and immutable run/model provenance.
- Old review artifacts remain historical and do not silently enter trusted supervision.
- Keep the existing React + Vite + shadcn/ui design system and accessible workflow diagrams.
- Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; do not add or run automated tests unless explicitly requested. Use manual browser and CLI checks with synthetic sources.

## Review Focus

- Direct navigation/refresh of old `/review` URLs: no dead page and no way to make a human decision required for completion.
- A run with all rows quarantined: status/reasons are legible and no false “successfully labeled” state appears.
- A training candidate rejected by gates: active model remains clear and unchanged in UI.
- Narrow/mobile layout: tables/diagrams remain readable without horizontal overflow.
- Loading, model-unavailable, incomplete-policy, and no-trusted-label states explain the automatic next state rather than asking for record-level approval.

---

## Stage and branch

Implement after the autonomous inference and trusted-training stages are reviewed, on `codex/finlabel-autonomous-panel` based on their reviewed integration state. Integrate into `codex/finlabel-autonomous-mvp` after stage review. Do not merge to the default branch.

### Task 1: Expose autonomous run and training summaries in the API

**Files:**
- Modify: `src/finlabel/web/app.py`
- Modify: `src/finlabel/cli.py` if summary serialization needs a shared formatter.
- Modify: `src/finlabel/labeling/outcomes.py` and `src/finlabel/training/autopipeline.py` only through their public read APIs.

**Interfaces:**
- `GET /api/label/runs` lists run metadata and applied/quarantined counts, never row values.
- `GET /api/label/runs/{run_id}` returns summary, policy/model refs, and aggregate reason counts.
- `GET /api/training/cycles` and `/api/training/cycles/{cycle_id}` return state, trusted-source provenance, metrics/gates, active version, promotion/rejection/rollback reason.
- Existing review endpoints are read-only compatibility endpoints for old runs; mutation endpoints reject new review events with an explicit legacy-workflow response.

- [ ] **Step 1:** Add summary-only API handlers over domain read services; verify JSON payloads on synthetic runs contain no raw values or prompt fields.
- [ ] **Step 2:** Make old review mutation endpoint return a clear compatibility response without writing a decision event.
- [ ] **Step 3:** Manually inspect success, quarantine, gate-failure, and legacy-run responses with local API requests.
- [ ] **Step 4:** Commit as `feat: expose autonomous cycle state in local API`.

### Task 2: Replace human review UI with automatic run monitoring

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/LabelingPage.tsx`
- Replace or repurpose: `frontend/src/pages/ReviewPage.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/ui/*` only if existing components cannot express existing patterns.

**Interfaces:**
- `/labeling` creates/starts the configured autonomous run and links to its result summary.
- Run summary displays applied, quarantined, stale, invalid and backend-error counts, plus reason codes and model/policy refs.
- `/review?run_id=...` redirects to the autonomous run summary for new runs; legacy runs render read-only history with no decision controls.
- The UI never requires opening row detail to finish a run.

- [ ] **Step 1:** Replace suggestion review actions with run status and aggregate result components.
- [ ] **Step 2:** Remove accept/edit/reject/skip actions from new flows while preserving read-only display for legacy artifacts.
- [ ] **Step 3:** Add empty, policy-missing, model-unavailable, all-quarantined and partial-success states.
- [ ] **Step 4:** Manually inspect the flow at 1440×900 and 390×844; confirm readable status, no horizontal overflow, and no record-level decision buttons.
- [ ] **Step 5:** Commit as `feat: replace review queue with autonomous run results`.

### Task 3: Present automatic model lifecycle and training diagram

**Files:**
- Modify: `frontend/src/pages/TrainingPage.tsx`
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Diagram states: trusted labels → provenance/quality gates → train/calibration/holdout split → isolated training → frozen evaluation → automatic promotion or keep-current → post-promotion monitor/rollback.
- Current state and result metrics come from `/api/training/cycles`; display candidate ID, active version, coverage, quarantine and per-label gates.
- No manual “activate” or “reject” action is required for automatic-cycle candidates; manual inspection of reports remains available.

- [ ] **Step 1:** Bind the existing training flow diagram to automatic cycle states and current API data.
- [ ] **Step 2:** Show why training was skipped or why a candidate did not promote, preserving actionable machine-readable reason codes with plain-language copy.
- [ ] **Step 3:** Manually inspect initial, training, promoted, rejected, and rollback states on desktop and mobile, including text alternatives for the diagram.
- [ ] **Step 4:** Commit as `feat: show automatic promotion and rollback workflow`.

### Task 4: Align product documentation and project roadmap

**Files:**
- Modify: `README.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/spec.md`
- Modify: `.scratch/proximas-etapas-tcc/epico.md`
- Modify: `planejamento/Proposta_fluxo_reutilizavel.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/map.md`

- [ ] **Step 1:** Mark the older human-review design as superseded by the approved autonomous design and align its flow/scope/acceptance criteria.
- [ ] **Step 2:** Update the FinLabel README and TCC epic/proposal to state automatic labeling, abstention/quarantine, trusted-label-only training, and automatic gated promotion.
- [ ] **Step 3:** Record stage branches, implementation evidence, limitations, and open academic decisions in the issue tracker/map.
- [ ] **Step 4:** Manually compare docs against actual CLI/API/panel behavior; commit as `docs: align FinLabel project with autonomous workflow`.

## Manual completion evidence

- New runs can complete without any review decision.
- UI and CLI agree on applied/quarantined state and model lifecycle state.
- Legacy review history remains readable but cannot block new runs or feed training automatically.
- Training diagram and documentation match actual promotion/rollback behavior.
- Responsive desktop/mobile inspection uses only synthetic data.
