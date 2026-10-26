# FinLabel module inventory and migration map

Baseline on 2026-10-26, branch `codex/finlabel-architecture-m1-contracts`:

| Command | Result |
| --- | --- |
| `/tmp/finlabel-clean-hexagonal-venv/bin/python -m pytest -q` | 128 passed, 17 subtests passed |
| `npm --prefix frontend test -- --run` | 4 files, 10 tests passed |
| `npm --prefix frontend run build` | Passed; existing chunk-size warning |
| `npm --prefix frontend run lint` | Exit 0; five existing React warnings |

The isolated interpreter is Python 3.12.14. The system interpreter is 3.9 and does not satisfy `pyproject.toml`'s Python >=3.10 requirement. The Python command above is the baseline equivalent of `python -m pytest`.

The package-level public names in `finlabel`, `finlabel.analysis`, `finlabel.labeling`, and `finlabel.models` are pinned in `tests/compatibility/test_public_imports.py`. That test also checks the CLI, HTTP app factory, and representative legacy submodule imports.

## Python module destinations

Every Python module present under `src/finlabel` at this baseline appears below. A row with multiple destinations contains mixed responsibilities that must be separated; the legacy path remains a compatibility facade where callers use it. Destinations are planned canonical homes, not claims that a move has already happened.

| Current module | Canonical destination and responsibility |
| --- | --- |
| `finlabel.__init__` | compatibility facade for public exports |
| `finlabel.cli` | `adapters.inbound.cli` for protocol handling; `bootstrap` for wiring; legacy console facade |
| `finlabel.monitor` | `domain.monitoring` for findings; `application.use_cases.monitoring` for orchestration; `adapters.outbound.persistence` for baseline files |
| `finlabel.profile` | `domain.projects` for profile values; `adapters.outbound.sources` for CSV inspection |
| `finlabel.project` | `domain.projects` for configuration values; `application.use_cases.projects` for orchestration; `adapters.outbound.persistence` for project JSON; `adapters.outbound.sources` for source opening |
| `finlabel.review` | `domain.labeling` for review values; `adapters.outbound.persistence` for review logs |
| `finlabel.analysis.__init__` | compatibility facade for analysis exports |
| `finlabel.analysis.charts` | `domain.analysis` for chart specifications; `adapters.outbound.persistence` for rendering/output |
| `finlabel.analysis.engine` | `domain.analysis` for deterministic calculations |
| `finlabel.analysis.planner` | `domain.analysis` for validated plans/highlights; `application.use_cases.analysis` and a model port for planner invocation |
| `finlabel.analysis.schema` | `domain.analysis` for plan/result values and validation |
| `finlabel.analysis.service` | `application.use_cases.analysis` for orchestration; `adapters.outbound.persistence` for run artifacts |
| `finlabel.labeling.__init__` | compatibility facade for labeling exports |
| `finlabel.labeling.outcomes` | `domain.labeling` for outcomes; `adapters.outbound.persistence` for run writes |
| `finlabel.labeling.policy` | `domain.labeling` for decisions; `adapters.outbound.persistence` for policy files |
| `finlabel.labeling.prediction` | `domain.labeling` for prediction values and validation |
| `finlabel.labeling.service` | `application.use_cases.labeling` for orchestration; `adapters.outbound.persistence` for run writes |
| `finlabel.labeling.suggestions` | `domain.labeling` for suggestion values/parsing; `adapters.outbound.persistence` for saved runs |
| `finlabel.labeling.task` | `domain.labeling` for task values; `adapters.outbound.persistence` for task files |
| `finlabel.models.__init__` | compatibility facade for model exports |
| `finlabel.models.text_generation` | `application.ports` for backend protocol; `adapters.outbound.models` for Transformers runtime |
| `finlabel.sources.__init__` | compatibility facade for source exports |
| `finlabel.sources.base` | `domain.projects` for source values; `application.ports.sources` for reader protocol |
| `finlabel.sources.csv_source` | `adapters.outbound.sources` for read-only CSV connector |
| `finlabel.sources.sqlite_source` | `adapters.outbound.sources` for read-only SQLite connector |
| `finlabel.training.__init__` | compatibility facade for training exports |
| `finlabel.training.active_model` | `adapters.outbound.models` for active backend loading; `adapters.outbound.persistence` for active-model metadata |
| `finlabel.training.autopipeline` | `application.use_cases.training` for lifecycle; `bootstrap` for wiring; `adapters.outbound.persistence` for artifacts |
| `finlabel.training.backend` | `domain.training` for request validation; `adapters.outbound.training` for PEFT/TRL runtime and artifact hashing |
| `finlabel.training.dataset` | `domain.training` for dataset selection rules; `application.use_cases.training` for preparation; `adapters.outbound.persistence` for dataset files |
| `finlabel.training.evaluation` | `domain.training` for metrics, calibration and gates; `adapters.outbound.persistence` for evaluation files |
| `finlabel.training.jobs` | `application.use_cases.training` for job operations; `adapters.outbound.persistence` for job store |
| `finlabel.training.local_evaluator` | `application.use_cases.training` for evaluation orchestration; `adapters.outbound.models` for inference; `adapters.outbound.persistence` for reports |
| `finlabel.training.quality` | `domain.training` for trusted batch quality rules |
| `finlabel.training.registry` | `domain.training` for promotion policy; `adapters.outbound.persistence` for registry and locks |
| `finlabel.training.split` | `domain.training` for deterministic split |
| `finlabel.training.task_spec` | `domain.training` for task specification and stable hash |
| `finlabel.training.trusted_labels` | `domain.training` for eligibility; `application.use_cases.training` for loading; `adapters.outbound.persistence` for trusted-label files |
| `finlabel.web.__init__` | compatibility facade for web package |
| `finlabel.web.app` | `adapters.inbound.http` for routes, auth, CSRF, schemas and panel delivery; `bootstrap` for app wiring; legacy app-factory facade |

The AST guard in `tests/architecture/test_layer_dependencies.py` classifies all current modules explicitly as transitional. It checks every new module in `domain`, `application`, `adapters`, or `bootstrap` against inward import edges. The transitional set must shrink as modules move; Task 12 removes it after the migration. Unclassified new modules fail the guard, so the exception cannot silently expand.
