# FinLabel Local Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Follow the repo's `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; work one ticket at a time and stop for human review.

**Goal:** Deliver a local-first data foundation and an analytics workflow that turns a natural-language question into a validated plan, deterministic calculations, a chart, and a grounded summary through both CLI and local web UI.

**Architecture:** Reuse the existing Python package. Add a project workspace and read-only CSV/SQLite adapters behind one `DataSource` protocol. A local text-generation backend proposes a typed `AnalysisPlan`; an allowlisted deterministic engine computes results, and Plotly renders them. FastAPI with Jinja2 serves the same services on `127.0.0.1`.

**Tech Stack:** Python 3.10+, `csv`, `sqlite3`, `decimal`, FastAPI, Uvicorn, Jinja2, Plotly, Transformers. Web/model packages are optional extras. FastAPI supports Jinja templates ([FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/)); Plotly can export standalone HTML charts ([Plotly HTML export](https://plotly.com/python/interactive-html-export/)). Python 3.10 is the minimum for the current PEFT/Transformers stack; PEFT's current package metadata declares `python_requires >=3.10` ([PEFT setup metadata](https://github.com/huggingface/peft/blob/main/setup.py), [Transformers on PyPI](https://pypi.org/project/transformers/)).

**Canonical approved spec:** `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`. The older `spec.md` describes only the first increment; Task 1 must update the local loop to read this approved MVP spec while retaining the first-increment history.

## Global Constraints

- “Conectores iniciais: arquivo CSV local e banco SQLite local.”
- “Fontes originais são sempre abertas em modo somente leitura e não são alteradas pela biblioteca.”
- “A biblioteca não envia linhas da fonte a serviços externos.”
- “O MVP não executa código ou SQL arbitrário gerado pelo modelo; usa operações permitidas sobre conectores somente de leitura.”
- “O servidor web deve escutar apenas em `localhost` por padrão.”
- “Monitoramento e treinamento são iniciados pelo usuário, sob demanda.”
- External onboarding sends only developer-approved metadata; never send row values.
- A provider-backed external onboarding advisor is optional and deferred from these two plans until its provider and credential flow are selected; the local workflows do not depend on it.
- No market-share result without configured measure, market/group, period, and denominator.
- CLI and web share one `.finlabel/` workspace: config/tasks/schemas, review logs, model references, and run artifacts are durable local state. Each run uses a unique ID; never overwrite an existing run or user-selected output.
- Analytics and labeling may use separate explicitly configured model references; the labeling fine-tuned adapter is not implicitly an analytics planner.
- SQLite iteration is streaming (`fetchmany(1000)`); grouped output uses a stable sort. Convert only explicitly mapped numeric/date types; do not infer locale-dependent formats silently.
- The project loop forbids adding or running automated tests without an explicit user request. This plan uses manual acceptance checks and does not run them now.

## Review Focus

- A malformed CSV, duplicate/empty headers, or invalid UTF-8 must fail with a clear message and no partial result (Task 2 manual check).
- SQLite must be opened read-only, and invalid table/column names must fail before a query is executed (Task 2 manual check).
- A model plan that references a missing column, unsupported operation, or ambiguous market-share denominator must be rejected for correction, never executed (Tasks 4–5 manual checks).
- Missing, nonnumeric, or invalid-date values must be counted and surfaced instead of silently changing totals or trends (Tasks 3–4 manual checks).
- A plan/model failure or chart-rendering failure must leave the source unchanged and avoid a misleading success summary (Tasks 5–7 manual checks).

---

## File Map

- Modify `codigo/finlabel/pyproject.toml`: Python floor and optional `web` and `models` dependencies (`torch`, `transformers`, `accelerate`).
- Modify `codigo/finlabel/src/finlabel/cli.py`: preserve `inspect`; add source, analysis, and server commands.
- Create `codigo/finlabel/src/finlabel/project.py`: local project/source configuration and workspace paths.
- Create `codigo/finlabel/src/finlabel/sources/base.py`: `SourceSpec`, `SourceRecord`, and `DataSource` contract.
- Create `codigo/finlabel/src/finlabel/sources/csv_source.py` and `sqlite_source.py`: read-only adapters.
- Create `codigo/finlabel/src/finlabel/monitor.py`: explicit schema capture and structural/quality findings.
- Create `codigo/finlabel/src/finlabel/analysis/schema.py`: typed, versioned plans and validation.
- Create `codigo/finlabel/src/finlabel/analysis/engine.py`: allowlisted local aggregations and result metadata.
- Create `codigo/finlabel/src/finlabel/analysis/planner.py`: local model prompt, JSON parsing, and plan validation.
- Create `codigo/finlabel/src/finlabel/models/text_generation.py`: lazy optional Transformers adapter.
- Create `codigo/finlabel/src/finlabel/analysis/charts.py` and `service.py`: chart and workflow orchestration.
- Create `codigo/finlabel/src/finlabel/web/app.py`, `templates/`, and `static/`: local panel using shared services.
- Modify `codigo/finlabel/README.md`: installation extras, command examples, data/privacy limits, and manual demo.

## Tasks

### Task 1: Project workspace and source contracts

**Files:**
- Modify: `codigo/finlabel/pyproject.toml`
- Create: `codigo/finlabel/src/finlabel/project.py`
- Create: `codigo/finlabel/src/finlabel/sources/base.py`

**Interfaces:**
- `SourceSpec(name: str, kind: str, path: Path, table: Optional[str], id_column: Optional[str], schema: Mapping[str, str])`.
- `ProjectConfig(path: Path, sources: Mapping[str, SourceSpec], model_roles: Mapping[str, str], workspace_dir: Path)`; role keys include independent `analytics` and `labeling` references.
- `SourceCapabilities(stable_record_ids: bool, read_only: bool, streaming: bool, selected_columns: bool)`.
- `SourceRecord(record_id: Optional[str], values: Mapping[str, object], input_digest: str)`; `record_id` may be absent for aggregate-only sources.
- `DataSource.capabilities() -> SourceCapabilities`, `.columns() -> Sequence[ColumnProfile]`, and `.iter_records(columns: Sequence[str], *, batch_size: int = 1000) -> Iterator[SourceRecord]`.
- `load_project(path: PathLike) -> ProjectConfig`; `save_project(config: ProjectConfig, path: PathLike) -> None`; `open_source(config: ProjectConfig, name: str) -> DataSource`.
- Store project config as JSON in `.finlabel/project.json`; resolve source paths relative to the project file when relative. Persist schema baselines under `.finlabel/schemas/` and analytics runs under `.finlabel/analyses/<run_id>/` with plan, result, chart, and run manifest; create a new run directory and fail if it exists.

- [ ] Preserve existing `finlabel inspect <csv>` behavior and raise `requires-python` to `>=3.10`; define optional `web` and `models` extras so core installation does not install ML weights/runtime.
- [ ] Define and document the dataclasses/protocol above; reject unknown source kinds and malformed JSON with path-aware errors.
- [ ] Document connector capability requirements and the stable identity contract: sources without stable IDs support aggregate analysis only; row-level review requires a unique stable ID and selected-input digest.
- [ ] Add a project initializer that creates only `.finlabel/project.json` and artifact directories; never copy source data.
- [ ] Point `LOOP.md` at the approved design file as canonical and mark the older `spec.md` as the historical first-increment scope.
- [ ] Manually inspect a new project file and verify relative paths resolve against the project directory.

### Task 2: Read-only CSV and SQLite sources

**Files:**
- Create: `codigo/finlabel/src/finlabel/sources/csv_source.py`
- Create: `codigo/finlabel/src/finlabel/sources/sqlite_source.py`
- Modify: `codigo/finlabel/src/finlabel/cli.py`
- Modify: `codigo/finlabel/src/finlabel/profile.py` only where needed to reuse profile behavior.

**Interfaces:**
- `CsvSource(spec: SourceSpec).columns() -> Sequence[ColumnProfile]` and `.iter_records(columns) -> Iterator[SourceRecord]`.
- `SqliteSource(spec: SourceSpec).columns() -> Sequence[ColumnProfile]` and `.iter_records(columns) -> Iterator[SourceRecord]`.
- `finlabel source add-csv NAME PATH` and `finlabel source add-sqlite NAME PATH --table TABLE [--id-column COLUMN]`.
- CSV record IDs are source-name plus logical row number; SQLite record IDs use the configured unique ID column. Compute `input_digest` from canonical selected field values so later training can detect changed rows without storing raw rows.
- SQLite analysis may use a source without a declared ID column; persisted row labeling/review must require a configured unique ID column.
- SQLite connections use URI `mode=ro`; identifiers are validated against discovered schema and values are parameterized.
- Stream rows in bounded batches; parse numeric/date values only under explicit schema mappings, and stable-sort grouped output for repeatable artifacts.

- [ ] Implement CSV adapter with the existing UTF-8, duplicate-header, malformed-row, and bounded-memory behavior.
- [ ] Implement SQLite adapter using read-only connections and validated table/column names; when an ID column is configured, verify it exists and is unique for persistent row-level workflows.
- [ ] Wire both source commands into the JSON project configuration; keep existing path-based `inspect` compatible.
- [ ] Manually inspect one synthetic CSV and SQLite file; attempt to write through the adapter and confirm the source remains unchanged; verify malformed CSV and a missing table produce actionable errors.

### Task 3: Structural and quality monitoring

**Files:**
- Create: `codigo/finlabel/src/finlabel/monitor.py`
- Modify: `codigo/finlabel/src/finlabel/cli.py`
- Modify: `codigo/finlabel/src/finlabel/project.py`

**Interfaces:**
- `SchemaBaseline(columns: Mapping[str, str], required_columns: Sequence[str], max_missing_ratio: Mapping[str, float], allow_extra_columns: bool)`.
- `QualityFinding(code: str, severity: str, column: Optional[str], expected: Optional[str], observed: Optional[str], message: str)`.
- `capture_schema(source: DataSource) -> SchemaBaseline` returns an editable candidate; saving it requires an explicit CLI/UI action.
- `monitor_source(source: DataSource, baseline: SchemaBaseline) -> Sequence[QualityFinding]`.
- CLI: `finlabel schema capture SOURCE --output PATH` and `finlabel monitor SOURCE --baseline PATH`.

- [ ] Report missing required columns, unexpected columns, configured type mismatches, and configured missing-value ratio breaches with stable finding codes.
- [ ] Do not silently accept an inferred schema as authoritative; present a captured schema for human confirmation/editing before saving.
- [ ] Keep per-column thresholds explicit in the baseline; do not invent global thresholds.
- [ ] Manually capture, edit, and compare a schema; remove/add a column and change a configured type to confirm findings identify the expected and observed values.

### Task 4: Typed analysis plan and deterministic engine

**Files:**
- Create: `codigo/finlabel/src/finlabel/analysis/__init__.py`
- Create: `codigo/finlabel/src/finlabel/analysis/schema.py`
- Create: `codigo/finlabel/src/finlabel/analysis/engine.py`

**Interfaces:**
- `AnalysisPlan(version: int, metric: MetricSpec, dimensions: Sequence[str], time_axis: Optional[TimeAxis], filters: Sequence[FilterSpec], chart: str)`.
- `MetricSpec(operation: str, column: Optional[str], denominator_scope: Sequence[str])`; `TimeAxis(column: str, grain: str)`; `FilterSpec(column: str, operation: str, value: object)`.
- `AnalysisResult(plan: AnalysisPlan, rows: Sequence[Mapping[str, object]], valid_row_count: int, invalid_value_counts: Mapping[str, int], formula_metadata: Mapping[str, object])`.
- Allow metrics: `count_rows`, `sum`, `average`, `distinct_count`, `share_of_total`; allow filters: `eq`, `neq`, `in`, `gt`, `gte`, `lt`, `lte`, `between`.
- Allow chart kinds: `line`, `bar`, `stacked_bar`.
- `validate_analysis_plan(plan: AnalysisPlan, schema: Sequence[ColumnProfile]) -> AnalysisPlan`.
- `run_analysis(source: DataSource, plan: AnalysisPlan) -> AnalysisResult`; `AnalysisResult` includes grouped values, invalid/missing-value counts, selected fields, filters, time grain, and formula metadata.
- Parse financial numeric values as `Decimal`; date/time columns require an explicit mapping and supported ISO format. `share_of_total` requires an explicit denominator scope, including the dimensions retained in the denominator.

- [ ] Define JSON serialization and validation for every plan field; unknown operations, fields, filters, and chart kinds fail closed.
- [ ] Implement row-streaming grouped aggregations without arbitrary SQL/code generation; surface excluded/invalid values in the result.
- [ ] Implement `share_of_total` only after the denominator scope is explicit; never infer “the market” or denominator from a column name.
- [ ] Manually calculate a small fixture by hand and compare counts, sums, time buckets, and shares; include a fixture with missing and malformed values and confirm they are reported.

### Task 5: Local natural-language planner and grounded highlights

**Files:**
- Create: `codigo/finlabel/src/finlabel/models/__init__.py`
- Create: `codigo/finlabel/src/finlabel/models/text_generation.py`
- Create: `codigo/finlabel/src/finlabel/analysis/planner.py`
- Modify: `codigo/finlabel/pyproject.toml`

**Interfaces:**
- `TextGenerationBackend.generate(prompt: str, *, max_new_tokens: int) -> str`.
- `TransformersTextGenerationBackend(model_id: str, revision: Optional[str] = None, device: str = "auto")` loads lazily and downloads weights only when explicitly invoked and not cached.
- `plan_analysis(question: str, schema: Sequence[ColumnProfile], backend: TextGenerationBackend) -> AnalysisPlan`.
- `HighlightRef(result_key: Sequence[object], observation: str)` and `plan_highlights(question: str, result: AnalysisResult, backend: TextGenerationBackend) -> Sequence[HighlightRef]`; the model selects result keys/observation kinds only. Code validates references, resolves exact values, and renders numeric text from `AnalysisResult`, not from free-form model arithmetic.

- [ ] Implement the optional Transformers backend; importing `finlabel` or running `inspect` must work without PyTorch/Transformers installed.
- [ ] Prompt for versioned JSON only, parse it, validate against the schema, and return a recoverable validation error rather than executing generated code or SQL.
- [ ] Make the planner ask for user mapping/confirmation when a metric, period, dimension, or denominator is ambiguous.
- [ ] Manually run with a compatible local model and a synthetic dataset; verify one valid trend plan, one missing-column plan, and one ambiguous market-share plan. Do not send data rows to a remote service.

### Task 6: CLI analysis and offline chart artifacts

**Files:**
- Create: `codigo/finlabel/src/finlabel/analysis/service.py`
- Create: `codigo/finlabel/src/finlabel/analysis/charts.py`
- Modify: `codigo/finlabel/src/finlabel/cli.py`
- Modify: `codigo/finlabel/pyproject.toml`

**Interfaces:**
- `analyze_source(source: DataSource, question: str, backend: TextGenerationBackend, plan_override: Optional[AnalysisPlan] = None) -> AnalysisRun`.
- CLI: `finlabel analyze SOURCE --question TEXT --model-id MODEL [--output PATH] [--plan PATH]`.
- Save `plan.json`, `result.json`, `chart.html`, and `run.json` under a unique `.finlabel/analyses/<run_id>/`; embed Plotly JavaScript locally, use no CDN, and fail rather than overwrite.

- [ ] Add `analyze` while preserving existing commands; support a manually supplied plan for users who want deterministic analysis without model planning.
- [ ] Render line, bar, and stacked-bar results from `AnalysisResult`; include the exact metric, filters, denominator scope, and dropped-value counts in the artifact.
- [ ] Render only validated `HighlightRef` values; label model-generated interpretation as such and avoid causal or predictive claims.
- [ ] Manually run the CLI against the synthetic CSV and SQLite fixtures; open the standalone HTML while offline and reconcile each displayed value with `result.json`.

### Task 7: Local web panel

**Files:**
- Create: `codigo/finlabel/src/finlabel/web/__init__.py`
- Create: `codigo/finlabel/src/finlabel/web/app.py`
- Create: `codigo/finlabel/src/finlabel/web/templates/index.html`
- Create: `codigo/finlabel/src/finlabel/web/templates/analysis.html`
- Create: `codigo/finlabel/src/finlabel/web/static/app.css`
- Modify: `codigo/finlabel/src/finlabel/cli.py` and `pyproject.toml`.

**Interfaces:**
- `create_app(project_path: PathLike, backend_factory: Callable[..., TextGenerationBackend]) -> FastAPI`.
- CLI: `finlabel serve [--project PATH] [--host 127.0.0.1] [--port 8765]`.
- Routes use the same project, source, planner, engine, and chart services as the CLI; no independent calculations in templates.

- [ ] Add source selection, schema capture/confirmation, structural-quality findings, question entry, inspectable/editable plan, chart/results, and grounded highlights.
- [ ] Bind to `127.0.0.1` by default and do not enable remote listening unless a future, separately reviewed change adds it.
- [ ] Validate Host and Origin against the bound local origin to mitigate DNS rebinding; use CSRF tokens for state-changing routes, same-site cookies, no permissive CORS, escaped templates, and request/result size limits. Do not accept file uploads in the MVP.
- [ ] Cap local previews at 100 rows and chart output at 2,000 points; paginate larger review/source lists instead of rendering them all at once.
- [ ] Serve chart code locally and show validation/mapping errors in the page without silently changing the plan.
- [ ] Manually verify the panel on localhost, complete a trend and share analysis, and confirm the same values as the CLI result file.

### Task 8: Documentation and milestone acceptance

**Files:**
- Modify: `codigo/finlabel/README.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/LOOP.md` only if an approved workflow decision changes.

- [ ] Document optional extras, Python floor, source formats, plan/metric definitions, privacy boundary, and offline chart artifacts.
- [ ] Store run output in unique directories and verify repeat runs cannot overwrite an earlier artifact or a user-provided path.
- [ ] Add a synthetic financial example for trend and market-share calculations; clearly state that historical trends are not forecasts and the user must define the market denominator.
- [ ] Execute the manual acceptance scenarios from Tasks 1–7 only when the implementation ticket is authorized; record any command not run in that ticket.

## Completion Gate

Plan 1 is ready for human review when CSV and SQLite remain read-only, monitoring produces reviewable structural/quality findings, the CLI and panel run the same validated analytics, charts render offline, and all scope/limitations are documented. Automated tests remain out of scope until explicitly requested under the local ticket loop.
