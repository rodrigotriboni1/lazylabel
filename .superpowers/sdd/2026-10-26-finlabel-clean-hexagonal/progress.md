# SDD ledger — plan: docs/superpowers/plans/2026-10-26-finlabel-clean-hexagonal.md

## Identity and setup

- Integration branch: `codex/finlabel-autonomous-mvp` (HEAD `2b11cca` at start); `main` unchanged.
- Active milestone branch: `codex/finlabel-architecture-m1-contracts`.
- Existing isolated worktree: `codigo/finlabel/.worktrees/autonomous-mvp`.
- Approved specification: `docs/superpowers/specs/2026-10-26-finlabel-clean-hexagonal-design.md`.
- Approved plan: `docs/superpowers/plans/2026-10-26-finlabel-clean-hexagonal.md`.
- Baseline: Python 3.12.14 in `/tmp/finlabel-clean-hexagonal-venv`, 128 passed + 17 subtests passed; React 10 passed; frontend build passed; lint exited 0 with existing warnings. Python 3.9 is the shell default and cannot run this package (declares >=3.10). `python -m pytest` also lacks pytest in default interpreter; this is environmental, resolved with the isolated venv.
- User selected full reorganization, independent agents, and a review branch per stage. Work will be sequential; each task receives an independent review before its milestone is integrated.

## Pre-flight conflict scan

| Tasks | Shared file/interface | Check and finding | Ruling |
|---|---|---|---|
| 1 ↔ 12 | `tests/architecture/test_layer_dependencies.py`, `tests/compatibility/test_public_imports.py` | Task 1 creates guards and a transitional allowlist; Task 12 removes the allowlist and strengthens compatibility assertions. Sequential and compatible. | Keep Task 1 rules permissive only for the documented migration set; Task 12 removes all exceptions. |
| 1 ↔ 13 | `docs/architecture/clean-hexagonal-module-map.md` | Task 1 creates a module inventory; Task 13 creates final guidance and can update it. No conflicting ownership. | Task 13 updates the map to actual final paths. |
| 2 ↔ 6, 8, 12 | Analysis domain symbols and legacy analysis facade paths | Task 2 extracts pure symbols; use cases (6), adapters (8), and final import enforcement (12) consume/migrate them. | Task 2 preserves existing names through temporary facades; later tasks migrate internals. |
| 3 ↔ 6, 7, 8, 12 | Labeling/monitoring values and old package paths | Task 3 moves pure decisions; Tasks 6/7 orchestrate and Task 8 implements effects. Task 12 locks facades. | Domain owns decisions; application coordinates; outbound adapters own I/O/model calls. |
| 4 ↔ 7, 8, 12 | Training evaluation/gate values and old training paths | Task 4 extracts pure policy; Task 7 orchestrates and Task 8 handles runtimes/storage. | Do not move filesystem/model code into domain; preserve gate behavior. |
| 5 ↔ 6, 7, 8, 9 | `SourceReader`, project ports and use-case DTOs | Task 5 defines shared source/project ports; later use cases, source adapters and HTTP/CLI composition consume them. | Task 5 freezes read-only source protocol; later tasks adapt rather than duplicate. |
| 6 ↔ 8, 9 | Analysis/labeling ports and composition | Task 6 defines use-case contracts; outbound adapters (8) and inbound composition (9) implement/connect them. | Adapters depend on these application-owned ports; composition instantiates them. |
| 7 ↔ 8, 9 | Training lifecycle ports and composition | Task 7 defines lifecycle interfaces; Task 8 implements runtime/storage; Task 9 composes entrypoints. | Preserve frozen evaluation and fail-closed promotion contracts. |
| 8 ↔ 9 | Outbound adapter constructors and bootstrap | Task 8 creates concrete adapters; Task 9 selects and injects them. | Task 8 exports constructors conforming to application ports; Task 9 alone chooses implementations. |
| 9 ↔ 10 | HTTP route/DTO contract and browser client | Task 9 preserves the existing HTTP surface; Task 10 captures it in a typed client. | Backend route contract remains authoritative; frontend maps the same wire DTOs. |
| 9 ↔ 12, 13 | Compatibility facades and architecture docs | Task 9 creates entrypoint facades; Task 12 tests them; Task 13 documents final layout. | Keep facades thin and update docs only after final names settle. |
| 10 ↔ 11 | Frontend client port, provider, and `App.tsx` | Task 10 adds client/adapter injection; Task 11 migrates pages and enforces no direct fetch. | Provider owns injection; pages consume only the port. |
| 11 ↔ 13 | React routes and browser verification | Task 11 preserves page behavior; Task 13 verifies the integrated panel. | Keep Task 13 as end-to-end check after all backend changes. |
| 12 ↔ 13 | Architecture checks and final documentation | Task 12 establishes enforceable rules; Task 13 documents and runs integrated validation. | Documentation must describe enforced actual rules, not aspirational ones. |

### Per-task consistency scan

| Task | Files/tests/interfaces consistency |
|---|---|
| 1 | Creates AST guard, compatibility tests and map; all are explicitly named and scoped to inventory/baseline. |
| 2 | Creates analysis domain and parity tests; legacy facades preserve public imports. |
| 3 | Creates labeling/monitoring domains and tests; explicitly leaves effects outside. |
| 4 | Creates training domain and tests; gate behavior tests correspond to moved pure functions. |
| 5 | Ports and use cases are tested against fakes; read-only contract is explicit. |
| 6 | Analysis/labeling use cases and fake tests align with their declared ports. |
| 7 | Lifecycle order and failure cases match declared ports and fail-closed behavior. |
| 8 | Adapter contract tests cover source read-only and serialization outputs; optional dependencies remain lazy. |
| 9 | Composition tests and existing end-to-end suites cover CLI and HTTP facades. |
| 10 | Typed frontend port, HTTP/memory adapters and tests cover actual current wire contract. |
| 11 | Page/component boundary test checks direct fetch absence; page tests preserve current flows. |
| 12 | Completes facades and finalizes AST rules; tests target the enforced contract. |
| 13 | Docs are based on final paths; full Python/frontend/build/lint/runtime checks match scope. |

No plan conflict blocks execution. No tests assert vacuously by design; each named check will be reviewed for meaningful assertions when implemented. The only baseline issue was interpreter setup, resolved via Python 3.12 isolated venv.

## Task status

- [x] Task 1 — baseline and import contract inventory
- [x] Task 2 — analysis and project value types
- [x] Task 3 — labeling and monitoring domain
- [x] Task 4 — training and promotion domain
- [x] Task 5 — project/source and monitoring use cases
- [x] Task 6 — analysis and labeling use cases
- [x] Task 7 — training lifecycle use case
- [x] Task 8 — outbound adapters
- [x] Task 9 — inbound adapters and composition
- [x] Task 10 — frontend client ports/adapters
- [x] Task 11 — React presentation boundary
- [x] Task 12 — compatibility and dependency enforcement
- [x] Task 13 — documentation and integrated validation (exact 1440x900 and 390x844 viewports remain unverified; see report)

Task 1: minor (deferred): Public-import test does not yet isolate optional dependencies; Task 12 explicitly adds lazy import assertions.

Task 1 review finding: Medium architecture gap — AST guard currently permits standard-library I/O/network modules such as `io`, `socket`, and `http.client` in domain/application. This is load-bearing for the layer rules and must be fixed before integrating the milestone.

Task 1: fix round 1/5 (1 addressed, 0 open — restricted-layer stdlib I/O/network imports; commits `c511901`..`9902766`).
Task 1: complete (commits `2b11cca`..`9902766`, review clean after one fix round; minor deferred: lazy optional-dependency import assertion is planned for Task 12).
Task 2: complete (commits `1d0d57c`..`d6b2953`, review clean).

Ruling: For Task 2, separate profile value types from CSV inspection: `ColumnProfile` and `DatasetProfile` belong in the pure project/domain model; `inspect_csv` remains a compatibility function whose file-reading implementation moves later to the source adapter. Keep Plotly/HTML rendering outside domain; Task 2 may add only pure chart metadata/specification, while the existing `render_chart` facade continues working until its adapter move. The analysis domain calculation must take schema and record iteration as inputs and import no source adapter — this preserves streaming while keeping source access injected — cost if wrong: the boundary may need redesign if source capabilities prove inseparable.

Ruling: For Task 3, move only deterministic rule/value semantics into domain. File path handling, JSON file load/save, current-time creation, UUID generation, hashes/writes, and source access stay in the legacy bridges/adapters; pure schema comparison accepts column profiles as values. This preserves current contracts while preventing filesystem/time/source dependencies from entering domain — cost if wrong: some existing JSON parsing helpers may need finer separation later.

Task 3 review finding: Important — `domain/labeling/outcomes.py` contains an unused copied `utc_now()` that references undefined datetime names and violates the explicit clock-outside-domain requirement. Ruling: delete this dead domain helper; the existing working legacy clock remains until its scheduled adapter migration. This is the smallest change that removes both runtime error and inward-layer effect — cost if wrong: any hidden direct importer of this new domain helper would need to use an injected clock instead.
Task 3: minor (deferred): `training/local_evaluator.py` still imports `_rules_match` through the legacy labeling service; carry to Task 12's canonical internal-import migration.
Task 3: fix round 1/5 (1 addressed, 0 open — removed domain clock helper; commit `88741c3`..`111f04f`).
Task 3: complete (commits `d6b2953`..`111f04f`, review clean after one fix round; minor deferred: legacy evaluator rule import carried to Task 12).

Task 3 minor resolved by Task 4 commit `23105cf`: evaluator imports `rules_match` from canonical domain labeling.

Task 4 review finding: Important, pre-existing registry promotion error — `_promotion_reasons` dereferences `PromotionPolicy.policy_id`, which does not exist, causing a valid artifact path to abort before a promotion decision. Ruling: correct only the mismatched identity reference using the actual `LabelingPolicy` identity already loaded and verified in the preceding evidence block; retain fail-closed rejection if that evidence is invalid. Do not alter promotion thresholds, policy schema, or serialized fields. This restores the intended identity validation without weakening any gate — cost if wrong: a promotion path may remain rejected until the exact policy identity source is exposed to both checks.

## Rulings

- Ruling: Use `/tmp/finlabel-clean-hexagonal-venv` with Python 3.12 for Python verification — the system interpreter is 3.9 and violates the package's declared runtime floor — cost if wrong: local verification may differ from other developer environments.
- Ruling: Create review branches sequentially from the accepted integration branch and merge accepted milestone commits locally — this preserves the user's branch-review workflow without parallel conflicting edits — cost if wrong: branch handoff may require cherry-pick cleanup.

Task 4: Ruling: Pure trusted-label values/validation, deterministic splits and hashes, calibration/evaluation mathematics, and promotion/rollback reasons move into domain; source/project reads, model calls, file hashing/verification, calibration load/save, locks, clocks, writes and filesystem-backed ModelRegistry stay outside. Compatibility subclasses preserve existing file APIs — this follows the controller's explicit boundary decision — cost if wrong: later adapter migration may require a finer seam.

Task 4: implementation complete (commit `23105cf`; focused tests: 53 passed, 3 subtests; full Python suite: 215 passed, 17 subtests; architecture/public imports: 31 passed; compileall and diff checks clean). Self-review complete; pending controller review. Complete report: `.superpowers/sdd/2026-10-26-finlabel-clean-hexagonal/task-4-report.md`.

Task 4: existing concern (unchanged): legacy registry artifact verification refers to nonexistent `PromotionPolicy.policy_id`; an otherwise valid path can raise AttributeError. Present at base commit `111f04f`; recorded in task report and sent to controller for separate regression-covered behavior work.

Task 4: fix round 1 implemented (commit `23105cf`..`d525da8`): resolved reviewer Important finding by comparing calibrator policy identity to loaded LabelingPolicy and rejecting unavailable labeling policy. Three real-file registry regressions observed AttributeError RED then passed GREEN; focused registry/promotion/rollback/domain tests 42 passed; full Python suite 218 passed, 17 subtests. Previous policy_id concern resolved; pending controller scoped re-review. Full command/output and fix details appended to task-4-report.md.

Task 4: fix round 1/5 (1 addressed, 0 open — calibrator policy identity uses loaded LabelingPolicy and missing policy fails closed; commits `23105cf`..`d525da8`). Scoped re-review approved: no new breakage. Re-review report: promotion identity finding ADDRESSED at `training/registry.py:528,624`; test evidence present.
Task 4: complete (review clean after one fix round; commits `111f04f`..`d525da8`; full Python suite 218 passed + 17 subtests).

Task 5 review finding: Important — an unhashable `ColumnProfile.inferred_type` escapes as `TypeError` instead of the promised typed `InvalidSourceMetadata` error. Ruling: confirm and require string validation before membership in `_PROFILE_TYPES`; the plan explicitly requires malformed metadata to map to a typed error. This prevents caller-dependent exceptions while preserving the read-only/source contract — cost if wrong: stricter metadata rejection could require updating a legitimate connector that emits non-string type names.

Task 5: fix round 1/5 (1 addressed, 0 open — unhashable profile type now maps to InvalidSourceMetadata; commits `02ebe9b`..`89e0cdc`). Scoped re-review approved; no new breakage.
Task 5: complete (review clean after one fix round; focused 34 passed; architecture/compatibility 31 passed; full Python suite before fix: 234 passed + 17 subtests; fix regressions: 19 passed).

Task 6: minor (deferred): `CalibrationBackend.calibrate` returns `object` despite required provenance/confidence fields; runtime validation currently fails closed. Consider a small result protocol during adapter-contract finalization or retain with a ledger note if adapters must stay structurally loose.
Task 6 review ⚠️ carried forward: Task 8/9 must verify real atomic publication and staging cleanup; project-level analysis composition must supply configured `explicit_types` to match the legacy bridge.
Task 6: complete (review approved; focused 29 passed + 3 subtests; application/architecture/compatibility 62 passed; full Python 249 passed + 17 subtests).

Task 7 review finding: Important — deletion of a promotion-policy artifact after evaluation now records `promotion_policy_missing`, whereas the previous cycle recorded `cycle_prerequisite_failed:FileNotFoundError`. Ruling: preserve the prior reason code at the revalidation boundary and add a regression for mid-cycle deletion; cycle artifacts are observable compatibility output and the plan requires their formats/reason semantics to remain stable. Promotion stays blocked either way — cost if wrong: a consumer may rely on the prior specific prerequisite reason.
Task 7: minor (deferred): training port `find_prior` uses an unparameterized tuple; carry to final type-contract review.
Task 7 review ⚠️ carried forward: adapter/composition tasks must verify locked registry transitions, frozen-partition verification, rollback thresholds and cycle idempotency integrity against their real persistence implementations.

Task 7: fix round 1/5 (1 addressed, 0 open — mid-cycle deleted promotion policy preserves `cycle_prerequisite_failed:FileNotFoundError`; commits `8a72da2`..`09e7457`). Scoped re-review approved, no new breakage.
Task 7: complete (review approved after one fix round; focused 47 passed + 3 subtests; application/architecture/compatibility 83 passed; full Python pre-fix 269 passed + 17 subtests).

Task 8 review finding: Important, inherited from the moved implementation — PEFT loading failure leaves the base model cached; a later record retries `_load`, accepts the cache under the promoted adapter `model_ref`, and may emit base-model scores against adapter calibration. Ruling: fix transactionally in the canonical model adapter and add repeated-call regressions for PEFT import/load failures. The plan explicitly requires model-adapter failures to preserve fail-closed behavior; retain an instance only after tokenizer, base, PEFT adapter, device and eval initialization all succeed — cost if wrong: a failed optional adapter setup could be misidentified and label data with an uncalibrated base model.

Task 8 review finding: Important, inherited — PEFT initialization could leave the unadapted base model cached after failure. Ruling: fixed transactionally in `TransformersTextGenerationBackend._load`; only publish model/tokenizer state after adapter load, device and eval succeed. Eight failure-path regressions verified RED/GREEN; scoped re-review approved, no new breakage.
Task 8 review ⚠️: real inference/training/evaluation was not run because optional ML dependencies are unavailable. Adapter contracts and failures are verified; report this runtime boundary in final verification.
Task 8 carried checks resolved: source adapters remain read-only; analysis/label publication atomicity and staging cleanup, `explicit_types`, frozen partitions, registry/cycle integrity and rollback contracts covered by adapter tests.
Task 8: complete (review clean after one fix round; required suite 89 passed; app/architecture/compatibility 83 passed; full Python 315 passed + 17 subtests; real ML runtime unavailable).

Task 9 review ⚠️ carried to Task 13: end-to-end HTTP success for legacy suggestion browsing and training submit/job-status remains unverified; run live server/browser checks. Also spot-check chunked bodies and IPv6/port Host variants. Task-scoped reviewer approved the diff.
Task 9: complete (review approved; focused 16 passed + 9 subtests; app/adapters/architecture/compatibility 152 passed; full Python 340 passed + 17 subtests; route parity comparison clean).

Task 10: minor (deferred): frontend build retains existing >500 kB chunk warning and lint has the five baseline warnings; no new warnings reported. Task reviewer approved, generated bundle not inspected line-by-line; Task 11/13 should verify source-to-bundle behavior.
Task 10: complete (review approved; 33 frontend tests, build and lint passed; UI page migration pending Task 11).

Task 11 review finding: Important test-coverage regression — `AutonomousPages.test.tsx` no longer asserts source, task and idempotency key passed to the autonomous cycle; the in-memory adapter ignores arguments. Ruling: restore a recording memory-client subclass/assertion while keeping response data from `FinLabelMemoryClient`; the plan requires meaningful workflow tests and exact transport contract preservation — cost if wrong: source/task mix-ups or broken idempotency could pass the UI suite.
Task 11: minor (deferred): monitoring selected-source change and explicit loading states for monitor/analysis/training are not tested; carry to final QA if no existing relevant coverage.
Task 11 review ⚠️ carried to Task 13: live HTTP/browser direct-route/reload and desktop/mobile viewport checks remain outstanding.

Task 11: fix round 1/5 (1 addressed, 0 open — restored autonomous source/task/idempotency argument assertions with a recording memory client; commits `4a86b64`..`d36741f`). Scoped re-review approved; mutation proof confirms tests fail for wrong arguments/key.
Task 11: complete (review approved; frontend 51 passed, build/lint/diff-check passed; five lint warnings and Vite chunk-size warning unchanged).
Task 11 minor (deferred): explicit tests for monitoring source switch and page loading states are limited; final browser/UI QA will inspect these.

Task 12: complete (commit `7e336a6`, reviewed and integrated at `cd54ef2`; architecture/compatibility 96 passed; Python 405 passed + 17 subtests; optional-import subprocess checks 10 passed).

Ruling: The subagent CUA browser exposes no viewport override and native-window resizing was unavailable because the Mac app inventory reported the computer locked. Record the exact 1440x900 and 390x844 checks as unverified, while completing direct-route/reload, navigation, visual review and seven-step training workflow at the available 1280x682 viewport; the root controller can repeat exact viewports if its browser supports the capability — cost if wrong: a responsive-only issue may remain undiscovered.

Task 13: implementation complete on `codex/finlabel-architecture-m6-documentation`; docs, full suites, HTTP/browser checks at available viewport, chunked/Host variants, and source immutability are recorded in `task-13-report.md`. Exact 1440x900 / 390x844 viewport QA remains unverified because this locked CUA session has no viewport override.

Final whole-branch review (base `2b11cca`, head `d02b9ed`):
- Important finding: `finlabel serve` callback is shadowed by argparse subparser and invocation raises TypeError. Fix wave required; add injected-callback regression.
- Important finding: workspace application reads concrete config/source attributes and a concrete jobs manager; declared port returns Any and does not carry required metadata. Fix wave required: type the required project/source metadata and job status operations at application ports, keep filesystem/connector layout in adapters, and prove with an opaque project/source composition regression.
- Minor deferred: calibration backend result and prior-cycle result contracts remain broadly typed; current runtime validation fails closed. No change in this fix wave.
- Minor deferred: source-adapter extension documentation names a bootstrap registration path but normal workspace and panel reads also have separate source selectors. Keep this visible for the final scoped re-review; do not expand the fix wave.
- Final viewport limitation: exact 1440x900 and 390x844 not verified because CUA cannot set viewport in this locked desktop session. Browser verification at 1280x682 is recorded in Task 13 report.
- Final reviewer declined to judge real model execution, generated bundle line-level inspection, baseline lint/bundle warnings, existing monitoring request races/loading transitions, retired manual training operations, and historical 500 mapping; reasons are recorded in the review report.

Task 13 final-review fix round 1/5 (2 addressed, 0 open — CLI serve callback shadowing; workspace application concrete project/source/job-manager dependencies; commits `d02b9ed`..`21a3f47`). Regressions observed failing on the original CLI bug / missing contract, then focused suite 2 passed; app/adapters/CLI/web/architecture/compatibility 235 passed + 9 subtests; full Python suite 407 passed + 17 subtests; compileall and diff-check clean. Independent scoped re-review approved both findings with no new breakage.
Task 13: complete and integrated on `codex/finlabel-autonomous-mvp` (`7a28e43`); final review fixes merged, integrated suites rerun (Python 407 + 17 subtests, frontend 51), build/lint/compileall/diff-check pass. Remaining verification limitation: exact 1440x900 and 390x844 viewport QA.
