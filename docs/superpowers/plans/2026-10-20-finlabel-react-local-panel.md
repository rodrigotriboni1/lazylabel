# FinLabel React Local Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; work one ticket at a time and stop for human review.

**Goal:** Replace the existing Jinja screens with one local React panel that supports analytics, labeling/review and the supervised training lifecycle while sharing the same FastAPI/Python services as the CLI.

**Architecture:** Build a Vite React SPA with shadcn/ui, Tailwind and Recharts, then serve its built static files from the existing FastAPI process. Keep domain logic and state transitions in Python API services; React owns presentation, forms and local user interaction. Training APIs depend on the services specified by `2026-10-20-supervised-training-lifecycle.md`.

**Tech Stack:** React, Vite, TypeScript, shadcn/ui, Tailwind CSS, Recharts, existing FastAPI. The official shadcn Vite setup uses the Vite plugin and Tailwind integration; shadcn's chart components are built from Recharts primitives ([Vite setup](https://ui.shadcn.com/docs/installation/vite), [charts](https://ui.shadcn.com/docs/components/radix/chart)).

**Spec:** `docs/superpowers/specs/2026-10-20-supervised-training-lifecycle-design.md`; product analytics/labeling scope: `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`.

**Dependency:** Complete/review the Python lifecycle plan's Tasks 1–5 first. Reuse the existing analytics and labeling service/API contracts; do not duplicate calculations or prediction/review rules in React.

## Global Constraints

- The panel is local and FastAPI listens on loopback by default; preserve current Host, Origin, CSRF, cookie, request-size and response-size controls.
- Source data remains read-only; no record values are sent to external services.
- CLI and web share the same Python services and `.finlabel/` workspace.
- React must not authorize training based only on client-side state; server rechecks the gate and explicit consent.
- The user approved React + Vite + shadcn/ui, with Recharts for charts. Keep exact dependency versions in the frontend lockfile after scaffolding.
- Follow the local loop prohibition on automated tests: build/serve/manual browser acceptance are allowed when each issue is authorized; do not add or run automated tests without explicit user request.

## Review Focus

- Static route fallback must never catch `/api/*`, `/static/*`, or missing assets and return the React HTML for an API request (Task 1 manual check).
- CSRF/Host/Origin controls must behave exactly as before for mutating API calls after the UI migration (Task 1 manual check).
- Browser resubmission/retry must not create duplicate review decisions or multiple training jobs (Task 3 manual check).
- Loading, empty, stale-source, malformed-analysis, blocked-dataset, failed-train and failed-activation states must not look like successful results (Tasks 2–4 manual checks).
- Charts must render values from deterministic API results, keep exact values accessible in a table, and never let generated summaries invent numeric results (Task 2 manual check).

---

## File Map

Implementation repository: `codigo/finlabel/.worktrees/integration/`.

- Create `frontend/`: Vite app, shadcn components, typed API client, routes and responsive pages.
- Modify `pyproject.toml`: package built frontend assets into the local Python distribution.
- Modify `src/finlabel/web/app.py`: return SPA shell for user routes, keep API services/security and serve local hashed assets.
- Retire `src/finlabel/web/templates/` and legacy UI-only JS/CSS after each route has React parity.
- Modify `README.md`: frontend build/package and local server workflow.
- Create one issue per task under `.scratch/biblioteca-rotulagem-financeira/issues/`, using canonical triage labels.

### Task 1: Vite app shell and FastAPI static serving

**Files:**
- Create: `frontend/package.json`, lockfile, `frontend/vite.config.ts`, TypeScript config, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, Tailwind and shadcn setup.
- Modify: `pyproject.toml`, `src/finlabel/web/app.py`.

**Interfaces:**
- Build output goes to a package-local directory under `src/finlabel/web/static/app/`; the Python package includes those files in built distributions.
- FastAPI serves React at `/` and known SPA paths; `/api/*` stays JSON, existing static/API paths are not shadowed. Unknown asset paths return 404, not the app shell.
- Typed API client handles `fetch`, JSON/error responses and the existing CSRF cookie/header protocol.

- [ ] Scaffold Vite/React/TypeScript with the official shadcn Vite workflow, Tailwind integration and a small initial component set; commit the package lockfile.
- [ ] Configure deterministic production output names and base path for FastAPI serving; include frontend assets in wheel package data.
- [ ] Add a minimal responsive shell with application navigation and a visible server/project status using only an existing safe API or a new metadata-only endpoint.
- [ ] Preserve FastAPI Host/Origin/CSRF/security middleware order. Serve SPA routes only after API/static route matching.
- [ ] Manually run frontend build, launch the local panel and verify `/`, an unknown asset, `/api/health`/equivalent, invalid Host, and missing CSRF behavior.
- [ ] Record manual commands and mark the issue `ready-for-human`; stop for review before Task 2.

### Task 2: Analytics, monitor and chart screens

**Files:**
- Create: `frontend/src/pages/OverviewPage.tsx`, `AnalysisPage.tsx`, `MonitorPage.tsx` and focused chart/result components.
- Modify: `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `src/finlabel/web/app.py` only for API gaps.

**Interfaces:**
- Use existing typed API payloads for source/schema profile, structural findings, analysis plan, deterministic result rows, chart metadata and grounded highlights.
- Line, bar and stacked-bar components consume deterministic result arrays; exact metric/filters/denominator/period and excluded-value counts remain visible alongside the chart.
- Natural-language question proposes a plan; user can inspect/correct before running it, through existing Python plan validation.

- [ ] Recreate the approved balanced overview and chart-first analytical hierarchy with shadcn components.
- [ ] Render trend, group comparison and composition/market-share output with Recharts; display definition and denominator for shares and offer tabular exact values.
- [ ] Add loading, no-data, unsupported-field, clarification, malformed-plan and analysis-failure states; do not show a chart or summary when calculation failed.
- [ ] Render monitor findings from deterministic API responses with severity and column/location; do not allow the model to change structural findings.
- [ ] Manually inspect chart values against API result JSON, exercise ambiguous market-share mapping and unavailable time-field cases, and review desktop/narrow viewports.
- [ ] Mark issue `ready-for-human`; stop for review before Task 3.

### Task 3: Label task, suggestions and human review screens

**Files:**
- Create: `frontend/src/pages/LabelingPage.tsx`, `ReviewPage.tsx` and focused task/suggestion/review components.
- Modify: `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `src/finlabel/web/app.py` only where existing APIs do not provide a needed safe payload/action.

**Interfaces:**
- Show configured tasks and allowed labels, source selection, selected fields, model reference, labeling run status, suggestions, invalid output count and review state.
- Review actions are `accept`, `edit`, `reject`, `skip`; requests include suggestion/run/record/digest identity and an idempotency key. React never persists a label locally as a substitute for the API response.
- List views omit row values by default; explicit detail shows only task-selected fields and stale state.

- [ ] Implement task/run screens using existing labeling/review service endpoints.
- [ ] Submit review actions with CSRF and stable idempotency key; disable duplicate submission while pending and re-fetch server state after success/retry.
- [ ] Make invalid/stale/rejected/unreviewed states visually distinct and prevent invalid review actions from appearing available.
- [ ] Manually accept, edit, reject and skip examples from the browser; inspect same append-only review events via CLI and verify a stale row cannot be reviewed into the dataset.
- [ ] Mark issue `ready-for-human`; stop for review before Task 4.

### Task 4: Training quality, split, evaluation and version screens

**Files:**
- Create: `frontend/src/pages/TrainingPage.tsx` and components for gate report, split setup, job progress, evaluation, version history and confirmation.
- Modify: `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `src/finlabel/web/app.py` to consume backend contracts from the Python lifecycle plan.

**Interfaces:**
- Page sequence: check dataset → configure split → start train → evaluate candidate → activate or reject → rollback.
- Put the full supervised-training workflow diagram directly on the training screen, with readable labels, arrows, and current lifecycle state; keep an accessible textual sequence alongside it. The user relies on diagrams to understand processes.
- Display label counts/minima, blockers/warnings, explicit exploratory confirmation, split settings/seed/counts, job status, base-versus-adapter metrics/support/errors, candidate state, active version and rollback choices.
- UI submits actions; Python revalidates manifests, warnings, confirmations, adapter hashes and valid state transitions.

- [ ] Add read-only quality and split previews; blockers disable training and warnings require an explicit exploratory confirmation in the train request.
- [ ] Display candidate as pending after training; evaluation report must appear before activation/rejection actions are enabled.
- [ ] Show per-label precision/recall/F1/support, undefined values, confusion counts and warnings; do not reduce results to a single quality badge.
- [ ] Render the approved train/evaluate/decide/activate-or-reject/rollback workflow diagram within the training cycle and make the current stage visible without replacing the textual status or actions.
- [ ] Use Recharts for metric comparisons only where it adds clarity; keep equivalent exact-value tables accessible.
- [ ] Add version list and explicit activation/rejection/rollback dialogs; refresh server state after every transition.
- [ ] Manually complete check → split → fake train → fake eval → activate/reject → rollback with a fixture project; confirm CLI sees identical model state and a failed request leaves the previous active version.
- [ ] Mark issue `ready-for-human`; stop for review before Task 5.

### Task 5: Retire Jinja UI and package the complete local app

**Files:**
- Modify: `src/finlabel/web/app.py`, `pyproject.toml`, `README.md`.
- Delete only after verified parity: `src/finlabel/web/templates/*.html`, legacy UI-only JS/CSS not used by the API/app.

- [ ] Route `/` and all user-facing paths through React while keeping API and static serving explicit; ensure direct refresh/deep links load the app shell.
- [ ] Remove Jinja template dependency only if no remaining server-rendered route uses it; otherwise keep dependency until all routes are migrated.
- [ ] Verify built assets are included in an installed wheel from a clean build and `finlabel serve` runs without a separate frontend dev server.
- [ ] Manually confirm loopback-only behavior, security headers/CSRF, no external scripts/CDNs, and all overview/analysis/monitor/label/review/training paths after packaging.
- [ ] Document install/build/serve steps and user-visible limitations; update issue to `ready-for-human` and stop for overall review.

## Completion Gate

The local panel is ready for whole-branch review when the packaged React app serves on localhost without a separate dev server; overview, analytics, monitor, labeling, review and training screens use shared Python API services; charts match deterministic results; review/training state changes are explicit and safe; previous FastAPI local security controls remain active; and legacy templates are removed only after parity. Automated tests remain unrun under the local loop unless separately authorized.
