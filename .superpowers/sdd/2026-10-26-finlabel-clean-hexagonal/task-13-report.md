# Task 13 report — architecture documentation and integrated validation

Branch: `codex/finlabel-architecture-m6-documentation`  
Synthetic project: `/tmp/finlabel-task13-synthetic`  
Local web origin: `http://127.0.0.1:8765` (loopback only)

## Deliverables

- Added `docs/architecture/clean-hexagonal.md` with the implemented Python/frontend boundaries, inward dependency rules, port ownership, composition roots, adapter extension steps, compatibility-facade policy, verification commands and a Mermaid flowchart using repository paths.
- Replaced the migration inventory in `docs/architecture/clean-hexagonal-module-map.md` with the final canonical map, enforced AST rules, compatibility entrypoints and frontend boundaries.
- No product-code fix or issue was needed during the integrated validation.

## Automated verification

All commands ran in this worktree against the integrated Task 12 branch before the documentation-only edits:

| Command | Result |
| --- | --- |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest -q` | **405 passed, 17 subtests passed** in 2.49 s |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest tests/architecture tests/compatibility -q` | **96 passed** in 0.51 s |
| `npm --prefix frontend test -- --run` | **8 files, 51 tests passed** |
| `npm --prefix frontend run build` | Passed; 2,550 modules transformed; generated JS 712.01 kB (209.55 kB gzip), triggering the existing >500 kB chunk-size warning |
| `npm --prefix frontend run lint` | Exit 0; five React warnings remain: `only-export-components` in `badge.tsx` and `button.tsx`, and `set-state-in-effect` in `TrainingPage.tsx`, `LabelingPage.tsx`, and `AnalysisPage.tsx` |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m compileall -q src tests` | Passed with no diagnostics |
| `git diff --check` | Passed with no diagnostics |

The generated frontend bundle was used by the local FastAPI server. The build did not create a tracked-worktree change.

## Synthetic HTTP and browser checks

The service was started on `127.0.0.1:8765` after `lsof` confirmed that port had no listener. The existing Vite listeners on 5177/5178 belonged to a separate `dashboard-redesign` worktree; neither was reused or changed.

- `GET /`, `/analysis`, `/monitor`, `/labeling`, `/review`, and `/training` each returned HTTP 200 on direct navigation and again after reload. Each response delivered the React shell and compiled assets.
- Browser accessibility snapshots exposed each page's main heading, route navigation, form/control labels, and empty/synthetic state. Clicking the **Análises** navigation item from `/training` opened `/analysis`.
- The training page displayed all seven named steps in order: verify, split, train, evaluate, decide, promote/reject, and monitor/revert. The first step was marked as the current state. A screenshot showed the complete horizontal workflow at the browser's available viewport.
- Browser QA ran at the available **1280×682** viewport. The layout was readable there and no horizontal clipping was visible in the captured overview/training pages.
- `GET /api/health` and `/api/sources` returned 200; the sources response contained schema metadata only.
- `POST /api/autonomy/run` returned 200 for the synthetic CSV. With no policy configured, both records were quarantined and the training cycle was blocked, as expected. Replaying the same idempotency key returned the same run (200); reusing it with different content returned 409; run status returned 200.
- The legacy suggestion-browsing route returned 200 with two synthetic suggestions. The fixture used a deterministic in-process stub backend and did not invoke an LLM. (A first request used the aggregate pipeline ID and correctly returned 400; using the dedicated label suggestion-run ID returned 200.)
- `POST /api/train/submit` returned 202 and `GET /api/train/jobs/{job_id}` returned 200 through a synthetic queued-job stub. This checked the HTTP request/response mapping only; it did not start training or load/download model weights.
- A chunked POST was rejected with 413. An untrusted IPv4 Host was rejected with 400. IPv6 host tests accepted `[::1]:8766` and rejected missing-port, mismatched-port, and untrusted-host variants (400).
- SHA-256 of `/tmp/finlabel-task13-synthetic/portfolio.csv` remained `7fd383c321fb2093d1cfe065d24acdd58c1d9567369cac1b75cdf014739baae8` throughout the HTTP, suggestion, and browser checks.

## Verification boundary

The CUA browser session in this subagent did not expose a viewport override, so exact **1440×900** and **390×844** checks and a mobile horizontal-overflow measurement could not be performed. The accessible browser viewport was 1280×682; the Mac-native app inventory also reported the computer locked, which prevented using a native window-resize/device-emulation control. Direct-route/reload, navigation, visual readability and the seven-step workflow were inspected at the available viewport. The Task 13 controller can repeat the two exact viewports from a root-thread browser session if its viewport capability is available.

No real model inference, model download, ML dependency installation, or training was performed. This is deliberate: HTTP training job behavior was stubbed so the check could validate the boundary without starting expensive model work.

The temporary FastAPI service was stopped after checks. The disposable project uses only generated local rows; its CSV remained unchanged.

## Final review fix wave 1

Branch: `codex/finlabel-architecture-m6-fixes`, based on integrated Task 12/13 head `d02b9ed`.

Addressed both Important findings from the final whole-branch review:

1. The `serve` argparse parser is now named `serve_command`, preserving the injected `serve` callback. Added `ServeCliTests.test_serve_calls_injected_server_with_project_host_and_port`, which checks the project string and parsed host/port passed to the injected server. The regression first failed with the expected `TypeError: 'ArgumentParser' object is not callable`; it passed after the fix.
2. Application workspace contracts now provide typed `ProjectMetadata`, an opaque `ProjectHandle`, declared source metadata (`name`, `kind`, and `schema`) on the read-only source port, and a `TrainingJobStatus` protocol plus `training_status(project, job_id)` operation. `WorkspaceApplication` consumes only those contracts. `FileWorkspace` keeps filesystem naming, workspace paths, and the concrete job manager lookup inside the adapter; CSV and SQLite adapters expose the declared metadata properties. Added `tests/application/test_workspace_port_contract.py`: its project handle is a bare `object()`, and its source has only the declared read-only source interface (no concrete `spec` or path).

Exact verification from this fix branch:

| Command | Result |
| --- | --- |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest tests/test_cli_end_to_end.py::ServeCliTests tests/application/test_workspace_port_contract.py -q` | **2 passed** |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest tests/application tests/adapters tests/test_cli_end_to_end.py tests/test_web.py tests/test_web_autonomous.py tests/architecture tests/compatibility -q` | **235 passed, 9 subtests passed** in 1.37 s |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest -q` | **407 passed, 17 subtests passed** in 1.73 s |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m compileall -q src tests` | Passed with no diagnostics |
| `git diff --check` | Passed with no diagnostics |

Both findings are implemented and regression-covered; independent scoped re-review of this fix diff remains with the controller. No model or ML dependencies were installed and no model training/inference was run in this fix wave.

## Final integrated verification

After merging Task 13 documentation and the final review fixes into `codex/finlabel-autonomous-mvp` at `7a28e43`, the controller reran:

- `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest -q` — **407 passed, 17 subtests passed**.
- `npm --prefix frontend test -- --run` — **8 files, 51 tests passed**.
- `npm --prefix frontend run build` — passed; existing 712.01 kB minified chunk warning remains.
- `npm --prefix frontend run lint` — exit 0; the same five existing React warnings remain.
- `/tmp/finlabel-clean-hexagonal-venv/bin/python -m compileall -q src tests` and `git diff --check` — passed without diagnostics.

Independent whole-branch review found two Important issues; both were fixed in commit `21a3f47` and the scoped re-review marked both ADDRESSED with no new breakage. Exact 1440x900 and 390x844 browser checks remain unverified for the CUA viewport limitation described above. The integration branch remains local; `main` was not changed.
