# FinLabel Clean Architecture and Hexagonal Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the complete FinLabel Python package and React client around inward dependencies while preserving behavior, public interfaces, persisted formats, and local-only policies.

**Architecture:** Pure domain modules own invariants and calculations; application use cases depend on explicit input/output ports; inbound CLI/FastAPI and frontend HTTP adapters translate protocols; outbound adapters implement file, CSV/SQLite, model, training, and persistence ports. Composition roots construct concrete dependencies, and legacy Python import paths remain thin facades.

**Tech Stack:** Python 3.10+, pytest, FastAPI, TypeScript, React 19, Vite, Vitest, AST-based architecture checks; retain existing runtime dependencies and optional extras.

**Spec:** `docs/superpowers/specs/2026-10-26-finlabel-clean-hexagonal-design.md`

## Global Constraints

- Preserve CLI `finlabel = finlabel.cli:main`, `finlabel.web.app:create_app`, current public package exports, HTTP routes/payloads/errors, and artifact/configuration formats.
- Preserve Python `>=3.10`, existing optional extras, and lazy loading of optional dependencies.
- Keep source CSV/SQLite read-only and retain all current autonomy, privacy, evaluation, promotion, and rollback policies.
- Domain code has no framework, I/O, model, network, adapter, or application imports; application use cases perform no direct I/O and construct no concrete adapters.
- React presentation depends on a typed client port; only its HTTP adapter performs network requests; Python remains the single source for business rules.
- Keep `main` unchanged; work on the existing isolated integration branch and produce reviewable milestone branches from it.
- Run focused verification after each milestone; run complete Python, frontend, architecture, and local HTTP/browser checks before completion.

## Review Focus

- Existing imports outside the package may rely on documented facade exports. Pin old import paths and object behavior in compatibility tests.
- Optional model/web/train extras may be absent. Verify base package and CLI imports do not eagerly load them.
- Persistence uses hashes, stable IDs, JSON/JSONL, and manifests. Compare serialized outputs against fixtures and reject unintended changes.
- FastAPI errors, CSRF, idempotency, and route methods are externally observable. Exercise these through the HTTP adapter and existing API tests.
- Failures in model, source, and persistence adapters must preserve current quarantine/no-promotion/local-only behavior. Use fakes to assert error mapping and that raw records do not cross the browser boundary.

---

## File and module map

Move responsibilities from current mixed modules; existing paths become facades only where public compatibility requires them. Inventory exact public names before moving each module.

| Current modules | Canonical destination | Responsibility |
|---|---|---|
| `profile.py`; pure parts of `analysis/{schema,engine,charts}.py` | `domain/analysis/`, `domain/projects/` | Profiles, validated plans/results, deterministic calculations and chart specifications |
| `labeling/{task,prediction,policy,suggestions,outcomes}.py` | `domain/labeling/` | Task, label, confidence, quarantine invariants and wire-independent values |
| Pure parts of `training/{split,quality,task_spec,trusted_labels,evaluation,registry}.py` | `domain/training/` | Trusted-data gates, splitting, evaluation and promotion decisions |
| Pure rules/results from `monitor.py` | `domain/monitoring/` | Structural quality rules and findings |
| New `application/ports/*.py`, `application/use_cases/{analysis,labeling,monitoring,training,projects}.py` | `application/` | Input/output contracts and orchestration; no concrete I/O |
| `sources/{base,csv_source,sqlite_source}.py` | `adapters/outbound/sources/` | Read-only source connectors |
| `models/text_generation.py`, runtime portions of `training/{active_model,backend}.py` | `adapters/outbound/{models,training}/` | Transformers inference and PEFT/TRL runtime |
| File-writing parts of `project.py`, `review.py`, labeling and training modules | `adapters/outbound/persistence/` | Project/config, review, run, dataset, job, registry and artifact storage |
| `cli.py`, `web/app.py` | `adapters/inbound/{cli,http}/` | Protocol parsing, auth/CSRF, request validation, error mapping and panel delivery |
| Existing public module paths | Facades | Backward-compatible imports and public entrypoints |
| `frontend/src/lib/api.ts`, pages and `main.tsx` | Frontend `application/ports`, `adapters/{http,in-memory}`, `presentation`, `bootstrap` | Typed client boundary, wire mapping, fake, React presentation and composition |

## Milestone 1: Lock behavior and architectural rules

### Task 1: Baseline and import contract inventory

**Files:** create `tests/architecture/test_layer_dependencies.py`, `tests/compatibility/test_public_imports.py`, `docs/architecture/clean-hexagonal-module-map.md`.

- [ ] Record baseline commands/results: `python -m pytest`, `npm --prefix frontend test`, `npm --prefix frontend run build`, `npm --prefix frontend run lint`.
- [ ] Inventory exported names from `finlabel`, `finlabel.analysis`, `finlabel.labeling`, and `finlabel.models`; assert existing facade imports resolve.
- [ ] Implement AST import collection and explicit layer-edge rules; verify a synthetic forbidden import is caught. Start with a documented transitional allowlist.
- [ ] Map every current Python module to a canonical destination in the architecture doc.
- [ ] Run the focused compatibility and architecture tests; expected: compatibility passes and architecture guard passes with the agreed transitional allowlist.
- [ ] Commit: `test: lock FinLabel public and architectural contracts`.

## Milestone 2: Extract pure domain by capability

### Task 2: Analysis and project value types

**Files:** create `src/finlabel/domain/analysis/{__init__,schema,engine,charts}.py`, `tests/domain/test_analysis_domain.py`; turn old analysis modules into temporary re-export facades.

- [ ] Add parity tests for plan validation, deterministic aggregates, KPI/heatmap values, and chart specifications using existing edge-case fixtures.
- [ ] Move pure schema, validation, calculation, and chart-specification logic; keep rendering, framework access, and persistence out of domain.
- [ ] Point internal callers to `finlabel.domain.analysis`; keep old imports working.
- [ ] Run `python -m pytest tests/test_analysis_edge_cases.py tests/test_analysis_engine.py tests/test_planner.py tests/test_analysis_service.py tests/domain/test_analysis_domain.py -q`; expected: all pass, no output fixture changes.
- [ ] Commit: `refactor: extract analysis domain`.

### Task 3: Labeling and monitoring domain

**Files:** create `src/finlabel/domain/{labeling,monitoring}/`, `tests/domain/test_labeling_domain.py`, `tests/domain/test_monitoring_domain.py`; adapt legacy modules as facades/service entrypoints.

- [ ] Test valid/invalid predictions, task/label constraints, confidence/quarantine decisions, and deterministic structural-quality findings.
- [ ] Move pure values, parsing/validation without filesystem effects, policy decisions, and monitoring rules. Keep clocks, IDs, serialization and writes outside.
- [ ] Change internal imports to canonical domain modules; retain old imports and behavior.
- [ ] Run `python -m pytest tests/test_label_outcomes.py tests/test_label_suggestions.py tests/test_label_task_review.py tests/test_labeling_policy.py tests/test_monitor.py tests/test_autonomous_pipeline.py tests/domain -q`; expected: all pass.
- [ ] Commit: `refactor: extract labeling and monitoring domains`.

### Task 4: Training and promotion domain

**Files:** create `src/finlabel/domain/training/`, `tests/domain/test_training_domain.py`; adapt legacy training modules temporarily.

- [ ] Test trusted-label eligibility, deterministic split, task/policy hashes, evaluation gate decisions, and promotion/rollback decisions.
- [ ] Move pure quality checks, split algorithms, task-spec hashing, metrics and promotion policy. Keep model calls, filesystem, locks, and writes outside.
- [ ] Ensure failed/insufficient evaluation means no promotion and does not weaken existing gates.
- [ ] Run `python -m pytest tests/test_training_split.py tests/test_trusted_labels.py tests/test_local_evaluator.py tests/test_training_rollback.py tests/test_autopipeline.py tests/test_autonomous_pipeline.py tests/domain/test_training_domain.py -q`; expected: all pass.
- [ ] Commit: `refactor: extract training domain`.

## Milestone 3: Define application ports and use cases

### Task 5: Project/source and monitoring use cases

**Files:** create `src/finlabel/application/ports/{sources,projects}.py`, `src/finlabel/application/use_cases/{projects,monitoring}.py`, `tests/application/test_project_monitoring_use_cases.py`.

- [ ] Define small protocols from current call sites for read-only source operations, profile, record iteration and project lookup; keep DTOs in domain/application.
- [ ] Test use cases with fakes, proving no CSV/SQLite/FastAPI imports are needed; assert source access is read-only and malformed metadata maps to a typed error.
- [ ] Implement project/source and monitoring orchestration with injected dependencies and typed results/errors.
- [ ] Run `python -m pytest tests/application/test_project_monitoring_use_cases.py tests/test_sources.py tests/test_project.py tests/test_monitor.py -q`; expected: all pass.
- [ ] Commit: `refactor: add source and project application ports`.

### Task 6: Analysis and labeling use cases

**Files:** create `src/finlabel/application/ports/{analysis,labeling}.py`, `src/finlabel/application/use_cases/{analysis,labeling}.py`, `tests/application/test_analysis_labeling_use_cases.py`.

**Interfaces:** Analysis depends on source-reader, optional planner and analysis-run-store ports. Labeling depends on source-reader, prediction-backend, label-run-store and clock/ID ports.

- [ ] Test fakes for analysis success, planner unavailable, label application, uncertainty quarantine, and persistence failure mapping.
- [ ] Move orchestration from `analysis/service.py` and `labeling/service.py`; route hashing/JSON/filesystem effects through persistence ports.
- [ ] Keep validation in domain and model invocation behind prediction port; preserve existing response DTO boundaries.
- [ ] Run `python -m pytest tests/test_analysis_service.py tests/test_label_suggestions.py tests/test_label_outcomes.py tests/test_autonomous_pipeline.py tests/application/test_analysis_labeling_use_cases.py -q`; expected: all pass.
- [ ] Commit: `refactor: add analysis and labeling use cases`.

### Task 7: Training lifecycle use case

**Files:** create `src/finlabel/application/ports/training.py`, `src/finlabel/application/use_cases/training.py`, `tests/application/test_training_use_case.py`.

**Interfaces:** lifecycle depends on trusted-dataset, trainer, evaluator, registry, and artifact-store ports. It coordinates prepare → train → evaluate → gate → promote/reject; domain decides gate outcome.

- [ ] Test fakes for promotion, gate rejection, training/evaluation failure and rollback without Transformers or disk.
- [ ] Move orchestration from `training/autopipeline.py` into the use case and route side effects through ports.
- [ ] Assert evaluation failure or missing policy/config cannot promote; frozen evaluation artifacts remain the gate inputs.
- [ ] Run `python -m pytest tests/test_autopipeline.py tests/test_autonomous_pipeline.py tests/test_training_rollback.py tests/test_training_jobs.py tests/application/test_training_use_case.py -q`; expected: all pass.
- [ ] Commit: `refactor: isolate training lifecycle use case`.

## Milestone 4: Adapters and composition

### Task 8: Outbound source, persistence, model and trainer adapters

**Files:** create `src/finlabel/adapters/outbound/{sources,persistence,models,training}/`; adapt old paths where needed; create `tests/adapters/outbound/`.

- [ ] Add temporary CSV/SQLite and isolated-project adapter contract tests; assert source adapters issue no writes to input files/databases.
- [ ] Move connectors, JSON/JSONL/config/run/job/dataset/registry stores, Transformers inference and PEFT/TRL implementations behind ports.
- [ ] Keep optional imports lazy until selected adapter construction/execution.
- [ ] Add serialization parity for project, review, label run, dataset manifest, registry, and training-job artifacts, including hashes and identifiers.
- [ ] Run `python -m pytest tests/test_sources.py tests/test_project.py tests/test_training_jobs.py tests/test_training_backend.py tests/test_model_chat_template.py tests/test_label_dataset.py tests/test_training_rollback.py tests/adapters/outbound -q`; expected: all pass under existing optional-dependency conditions.
- [ ] Commit: `refactor: move integrations behind outbound adapters`.

### Task 9: Inbound CLI/FastAPI adapters and composition

**Files:** create `src/finlabel/adapters/inbound/{cli,http}/`, `src/finlabel/bootstrap/`; adapt `src/finlabel/{cli.py,web/app.py,web/__init__.py}`.

- [ ] Test that CLI and web entrypoints use composed application use cases and permit dependency overrides.
- [ ] Move argument parsing/formatting to CLI adapter; move request/auth/CSRF/error mapping/templates/static delivery to HTTP adapter. Only bootstrap selects concrete adapters.
- [ ] Keep `finlabel.cli:main` and `finlabel.web.app:create_app` as facades; preserve routes, methods, payloads, statuses/errors, CSRF/idempotency and static assets.
- [ ] Run `python -m pytest tests/test_cli_end_to_end.py tests/test_web.py tests/test_web_autonomous.py -q`; expected: all pass with injected dependencies.
- [ ] Commit: `refactor: compose CLI and HTTP adapters`.

## Milestone 5: React client boundary

### Task 10: Typed application port and frontend adapters

**Files:** create `frontend/src/application/ports/FinLabelClient.ts`, `frontend/src/adapters/http/FinLabelHttpClient.ts`, `frontend/src/adapters/in-memory/FinLabelMemoryClient.ts`; adapt `frontend/src/lib/api.ts`, `main.tsx`, `App.tsx`.

- [ ] Inventory all current `fetch` calls and DTOs; codify existing operations, URLs, headers, CSRF/idempotency and responses in a typed client port.
- [ ] Implement HTTP and in-memory adapters; preserve existing API semantics and provide deterministic success/empty/error test states.
- [ ] Compose the HTTP client at bootstrap and inject via provider/context; retain compatibility wrappers only where needed.
- [ ] Test HTTP route mapping and in-memory states.
- [ ] Run `npm --prefix frontend test -- --run`; expected: all tests pass.
- [ ] Commit: `refactor: define frontend client port and adapters`.

### Task 11: React presentation depends only on the port

**Files:** modify `frontend/src/pages/*.tsx`, `frontend/src/components/**/*.tsx`, `frontend/src/App.tsx`; add dependency-boundary tests.

- [ ] Refactor pages to use only the typed client port; remove direct network calls and transport imports from presentation.
- [ ] Add a test forbidding `fetch` under pages/components and render key workflows using the in-memory adapter.
- [ ] Preserve routes, dashboard/heatmap KPIs, autonomous and training states, Portuguese copy, and empty/error states.
- [ ] Run `npm --prefix frontend test -- --run && npm --prefix frontend run build && npm --prefix frontend run lint`; expected: all pass.
- [ ] Commit: `refactor: isolate React presentation from HTTP`.

## Milestone 6: Compatibility, enforcement, and full validation

### Task 12: Complete facades and enforce dependency direction

**Files:** adapt legacy paths and `tests/architecture/test_layer_dependencies.py`; change `pyproject.toml` only if package discovery requires it (no runtime dependency).

- [x] Move internal imports to canonical paths; keep compatibility modules as re-export-only facades.
- [x] Remove transitional AST allowlist; enforce domain → stdlib/domain-local only, application → domain/application ports, adapters → application/domain, bootstrap → all layers.
- [x] Assert old public symbols map to canonical behavior and base/package/CLI imports do not load `torch`, `transformers`, `peft`, or FastAPI unless selected.
- [x] Run `python -m pytest tests/architecture tests/compatibility -q`; result: 96 passed; full Python suite: 405 passed + 17 subtests before final review fixes.
- [x] Commit: `test: enforce clean architecture and compatibility facades` (`7e336a6`).

### Task 13: Documentation and integrated validation

**Files:** create `docs/architecture/clean-hexagonal.md`; update README/module map only if entrypoint guidance changes.

- [x] Document layers, dependency rules, port ownership, composition roots, adding source/model adapters and facade deprecation; add Mermaid diagram with actual module names.
- [x] Run `.venv/bin/python -m pytest -q`; result: 405 passed, 17 subtests passed.
- [x] Run `npm --prefix frontend test -- --run && npm --prefix frontend run build && npm --prefix frontend run lint`; result: 51 tests passed, build/lint exited 0 with the existing bundle and five React warnings.
- [x] Run `.venv/bin/python -m compileall -q src tests` and `git diff --check`; no diagnostics.
- [x] Start the local app with isolated synthetic data; verify direct navigation/reload for all six routes, check the seven-step workflow and source hash. Browser was available at 1280x682; exact 1440x900 and 390x844 could not be set in the subagent CUA session, recorded in `task-13-report.md`.
- [x] Obtain an independent architecture/code review against the approved spec and resolve findings; scoped re-review approved both fixes. Final integrated Python suite: 407 passed + 17 subtests; frontend: 51 passed.
- [x] Commit: `docs: document FinLabel clean architecture`.

## Branch and review sequence

1. Keep `codex/finlabel-autonomous-mvp` as integration branch; do not alter `main`.
2. Create one review branch per milestone from the previous accepted milestone, named `codex/finlabel-architecture-<milestone>`; merge/cherry-pick accepted commits into integration before continuing.
3. Keep integration green after each milestone. If a port changes, update its contract tests and dependent work before proceeding.
4. Run full validation against the integrated branch, not only the final milestone branch.
