# FinLabel Visual QA Plan

> **For agentic workers:** Use the existing `codex/finlabel-lifecycle` branch at commit `59f6205`; this is a manual QA task, not a code implementation. Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`. Do not run automated tests.

**Goal:** Visually inspect the packaged local React panel at desktop and narrow viewport sizes, with particular attention to the supervised-training workflow diagram.

**Architecture:** Use a temporary FinLabel project with no real source rows, a verified installed wheel, and a loopback-only server. Inspect the current panel in an available browser, capture the visible states, and record any defects in issue 16 without changing product code during the QA pass.

**Tech Stack:** FinLabel CLI, installed React/Vite bundle, FastAPI, Chrome or another available browser, viewport sizes 1440×900 and 390×844.

**Spec:** `.scratch/biblioteca-rotulagem-financeira/issues/13-painel-ciclo-treinamento.md`; `.scratch/biblioteca-rotulagem-financeira/issues/14-pacote-react-local.md`.

## Global Constraints

- Keep the app bound to `127.0.0.1`; never switch to `0.0.0.0`.
- Use a temporary project and synthetic or empty state only; do not open real financial data.
- Do not run training, inference, or automated tests.
- Inspect existing listeners before starting the service; stop only the process started for this QA.
- Do not try to unlock or otherwise control a locked Mac. If no browser is available, stop at the UI step and report what remains.
- If a defect is found, record it with the viewport, route, and screenshot/evidence; implement fixes in a separate reviewed issue.

## Review Focus

- Training diagram: all seven stages are present, readable, connected, and the current stage is clearly highlighted.
- Narrow viewport: no horizontal page overflow; diagram and navigation remain usable at 390×844.
- Empty or blocked project: no state appears successful, and training/evaluation actions remain unavailable.
- Browser routing: direct navigation and refresh preserve React pages; API and missing-asset responses remain distinct from the SPA shell.
- Accessible sequence: the diagram's equivalent text identifies all steps and the current step.

## Task 1: Prepare a safe local preview

**Files:**
- Read: `README.md`, issue 14, and this plan.
- Temporary only: `/tmp/finlabel-visual-qa-project`.

- [ ] Confirm the checkout is `codex/finlabel-lifecycle` at `59f6205` and clean.
- [ ] Inspect browser availability and check ports 18765 and 56697 with `lsof -nP -iTCP:<port> -sTCP:LISTEN`; record the result. Recheck the chosen port immediately before starting.
- [ ] Confirm `/tmp/finlabel-visual-qa-project` does not exist before creating it. If it already exists, choose a new unused path and use that exact path consistently; never reuse or remove an existing directory.
- [ ] If `/tmp/finlabel-task5-final-venv.spDG18/bin/finlabel` exists, use that CLI. Otherwise, follow the README to build/install the wheel with the `web` extra into `/tmp/finlabel-visual-qa-venv` and use `/tmp/finlabel-visual-qa-venv/bin/finlabel`.
- [ ] Initialize the empty project: `<CLI_PATH> project init /tmp/finlabel-visual-qa-project` (substitute the chosen unused project path if needed).
- [ ] Start the temporary service with `<CLI_PATH> serve --project /tmp/finlabel-visual-qa-project --host 127.0.0.1 --port 18765` only after confirming that port is free. Expected effect: local-only HTTP service on port 18765; stop it with Ctrl+C after inspection.
- [ ] Open `http://127.0.0.1:18765/training` in an available browser. If the host is locked or browser control is unavailable, do not attempt to unlock it; record the blocker and stop visual interaction.

## Task 2: Inspect desktop layout and workflow diagram

- [ ] Set the browser viewport to 1440×900 and refresh `/training`.
- [ ] Verify all seven diagram steps are visible: check, split, train, evaluate, decide, activate/reject, rollback.
- [ ] Confirm the empty project's current step is shown as “Verificar dados”; gate and authorization state are visibly pending, with no misleading success status.
- [ ] Inspect title, labels, connectors, spacing, contrast, card boundaries, and whether the diagram competes with or obscures controls.
- [ ] Visit `/`, `/analysis`, `/monitor`, `/labeling`, and `/review`; note clipping, broken assets, loading errors, or inconsistent page width.
- [ ] Capture screenshots or browser snapshots of the training view and any defects, using only empty/synthetic project state.

## Task 3: Inspect narrow layout and navigation

- [ ] Set viewport to 390×844, refresh `/training`, and inspect the full page and bottom navigation.
- [ ] Confirm no horizontal scrollbar or clipped text; all seven stages remain readable in the responsive diagram layout.
- [ ] Confirm the accessible text sequence includes all seven steps and identifies the current step using the browser accessibility tree or equivalent inspection.
- [ ] Navigate between the primary pages and verify the active navigation item and page heading remain visible.
- [ ] Capture the narrow training view and any defects.

## Task 4: Record results and clean up

- [ ] Update issue 16 with pass/fail per criterion, viewport measurements, routes inspected, evidence paths, and unresolved limitations.
- [ ] If defects exist, create focused follow-up issues with severity and reproduction steps; do not patch code during this visual QA pass.
- [ ] Stop only the temporary FinLabel server started for this run and verify port 18765 no longer has that listener.
- [ ] Remove only the temporary project created in Task 1, after confirming its exact path and that it contains no user data; if the project path pre-existed, do not remove it.

## Acceptance

Visual QA is complete when both viewports are inspected, the diagram's labels and current state are verified, all listed routes render without visible clipping or broken assets, and issue 16 records the screenshots/findings. If browser access remains unavailable because the host is locked, the issue stays `ready-for-human` with the exact remaining steps; no claim of visual approval is made.
