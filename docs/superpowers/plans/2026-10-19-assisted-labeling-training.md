# FinLabel Assisted Labeling and Fine-Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Follow `.scratch/biblioteca-rotulagem-financeira/LOOP.md`; work one ticket at a time and stop for human review.

**Goal:** Add configurable local label suggestions, human review through CLI and web, local training-dataset preparation, and explicit PEFT/LoRA fine-tuning.

**Architecture:** Build on the project/source and shared local text-generation contracts from `2026-10-19-local-analytics.md`. Each labeling run stores suggestions separately from append-only review decisions. Review events keep opaque record references and input digests so the library can re-read selected source fields for a requested training export without copying the source by default. A local training backend uses TRL SFT with PEFT/LoRA.

**Tech Stack:** Python 3.10+, existing JSONL `ReviewLog`, Transformers, PyTorch, PEFT, TRL `SFTTrainer`, JSONL prompt/completion training files, existing FastAPI/Jinja2 panel. TRL documents its SFT trainer with PEFT configuration ([SFTTrainer](https://huggingface.co/docs/trl/sft_trainer), [PEFT integration](https://huggingface.co/docs/trl/main/peft_integration)).

**Canonical approved spec:** `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`. The older `spec.md` describes only the first increment; Plan 1 Task 1 updates the local loop to reference the approved MVP spec.

**Dependency:** Complete and review Plan 1, `docs/superpowers/plans/2026-10-19-local-analytics.md`, first. This plan uses its `ProjectConfig`, `SourceSpec`, `DataSource`, `SourceRecord`, and `TextGenerationBackend` interfaces.

## Global Constraints

- “A tarefa define instruções, campos de entrada e rótulos válidos; não existe uma taxonomia financeira rígida no núcleo.”
- “Modelo local sugere rótulos; regras determinísticas são responsáveis pelo monitoramento estrutural e de qualidade.”
- “Treino nunca começa automaticamente. O desenvolvedor inicia a preparação dos exemplos e o fine-tuning por comando/ação explícita.”
- “Só cria um dataset de treino local quando solicitado explicitamente; ele contém as colunas que o desenvolvedor escolheu para a tarefa e os rótulos revisados.”
- “Nenhuma linha ou valor de registro pode ser enviado à LLM externa.”
- “Revisões guardam a sugestão original, a ação humana, o rótulo final e o momento/configuração relevantes para auditoria local.”
- The local package loop forbids adding or running automated tests without an explicit user request. This plan uses manual acceptance checks and does not run them now.
- Do not distribute model weights or claim compatibility beyond the selected model/backend; display the model reference and applicable usage terms when available.
- The MVP includes fine-tuning capability, but actual model-weight loading, user-data loading for training, and a training run remain gated by the local loop until model, license, hardware, data policy, and academic evaluation protocol are recorded and authorized.
- CLI and web share `.finlabel/` state. A labeling model reference is independent from the analytics planner reference.
- Local web state-changing routes use the security controls defined in Plan 1: local Host/Origin validation, CSRF protection, same-site cookies, no permissive CORS, escaped templates, and bounded requests/results.

## Review Focus

- A source row changed after inference/review must not silently produce a training example with different input values (Tasks 1 and 4 manual checks).
- Unknown labels, malformed model output, or a model response outside the task schema must be rejected, not persisted as a valid suggestion (Tasks 1–2 manual checks).
- Rejected/unreviewed suggestions must never appear as training labels; accepted/corrected labels must match the configured label set (Tasks 3–4 manual checks).
- Legacy JSONL review events must remain readable after schema evolution, while lacking provenance must exclude them from training export (Task 1 manual check).
- Training or model loading failure must leave source, review history, and prior model artifacts intact; no network upload or telemetry may occur (Tasks 5–6 manual checks).

---

## File Map

- Modify `codigo/finlabel/pyproject.toml`: optional `models` and `train` extras.
- Create `codigo/finlabel/src/finlabel/labeling/task.py`: task configuration and label validation.
- Create `codigo/finlabel/src/finlabel/labeling/suggestions.py`: suggestion record and run storage.
- Create `codigo/finlabel/src/finlabel/labeling/service.py`: source-to-prediction workflow.
- Modify `codigo/finlabel/src/finlabel/review.py`: provenance fields, schema version 2, backward-compatible reading.
- Create `codigo/finlabel/src/finlabel/training/dataset.py`: explicit prompt/completion export from reviewed records.
- Create `codigo/finlabel/src/finlabel/training/backend.py`: TRL SFT + PEFT/LoRA implementation.
- Modify `codigo/finlabel/src/finlabel/cli.py`: labeling, review, dataset, and train commands.
- Modify `codigo/finlabel/src/finlabel/web/app.py` and add `templates/labeling.html`, `templates/review.html`, `templates/training.html`: same workflow through the panel.
- Modify `codigo/finlabel/README.md`: task format, model requirements, review and training commands, limitations.

## Tasks

### Task 1: Label task contract and provenance-aware review events

**Files:**
- Create: `codigo/finlabel/src/finlabel/labeling/__init__.py`
- Create: `codigo/finlabel/src/finlabel/labeling/task.py`
- Modify: `codigo/finlabel/src/finlabel/review.py`

**Interfaces:**
- `LabelTask(task_id: str, instructions: str, input_columns: Sequence[str], labels: Sequence[str], model_id: str, model_revision: Optional[str])`.
- JSON task files live under `.finlabel/tasks/<task_id>.json` and do not contain source row values.
- A source used for persistent labeling/review must provide stable row IDs; SQLite requires a configured unique ID column, and CSV uses the source name plus logical row number and input digest.
- `LabelSuggestion(run_id: str, source_name: str, record_id: str, input_digest: str, task_id: str, label: str, rationale: Optional[str], model_ref: str, created_at: str)`.
- Extend `ReviewDecision` with optional `run_id`, `source_name`, `task_id`, `input_digest`, and `suggestion_id`; write schema version 2 and keep reading version 1 events. The existing `event_id` and `created_at` fields are already present in schema v1 and remain required.
- `ReviewLog.record(...)` remains append-only; accepted/corrected/rejected action semantics stay unchanged. Each suggestion may have multiple events; its current review is the latest valid event by append order. Web writes use an idempotency key so a retried request does not create duplicate decisions.
- New calls add `run_id`, `source_name`, `task_id`, and `input_digest` as optional keyword-only provenance fields; old callers without them remain valid but those events cannot enter a new training dataset.

- [ ] Parse and validate task JSON: unique nonempty labels, nonempty instructions, known input columns, required model ID, and no hidden arbitrary code.
- [ ] Add schema-v2 provenance fields to review events; read and validate v1 without rewriting it, and reject malformed event lines with line numbers.
- [ ] Validate accepted/corrected labels against the task's configured label set before recording.
- [ ] Manually read a v1 log and append/read v2 events; verify an old event stays readable but is marked ineligible for training due to missing provenance.

### Task 2: Local label suggestion runs

**Files:**
- Create: `codigo/finlabel/src/finlabel/labeling/suggestions.py`
- Create: `codigo/finlabel/src/finlabel/labeling/service.py`
- Modify: `codigo/finlabel/pyproject.toml`

**Interfaces:**
- `suggest_labels(source: DataSource, task: LabelTask, backend: TextGenerationBackend) -> LabelRun`.
- `LabelRun(run_id: str, source_name: str, task_id: str, model_ref: str, suggestion_path: Path, row_count: int, invalid_count: int)`.
- Persist suggestions as `.finlabel/runs/<run_id>/suggestions.jsonl`; do not persist source row contents or full prompts.
- Give each suggestion a stable `suggestion_id`; review events refer to it, while the suggestions file preserves the immutable original model output and provenance.
- The prompt includes only task-selected input columns. The model must return one configured label and optional rationale; the service validates the response before persistence.

- [ ] Implement deterministic prompt serialization from selected columns, preserving values as data fields and not executable instructions.
- [ ] Store record ID, selected-input digest, task/source/model references, predicted label, and optional rationale only.
- [ ] Reject malformed JSON or unknown labels and count the row as invalid; keep processing subsequent records and report the count.
- [ ] Manually run labeling with a compatible local model against a synthetic source; inspect the JSONL and confirm no unselected field, full row, or prompt is stored.

### Task 3: CLI review and training-dataset preparation

**Files:**
- Create: `codigo/finlabel/src/finlabel/training/__init__.py`
- Create: `codigo/finlabel/src/finlabel/training/dataset.py`
- Modify: `codigo/finlabel/src/finlabel/cli.py`
- Modify: `codigo/finlabel/src/finlabel/review.py` only if the shared event reader needs a public iterator.

**Interfaces:**
- `finlabel label SOURCE --task TASK_ID` creates a suggestion run from a task's configured `model_id`.
- `finlabel review RUN_ID` interactively shows only selected source fields and allows `accept`, `edit LABEL`, `reject`, or `skip`.
- `prepare_training_dataset(project: ProjectConfig, run_id: str, output: PathLike) -> DatasetManifest`.
- `DatasetManifest(path: Path, row_count: int, selected_columns: Sequence[str], included_event_ids: Sequence[str], included_suggestion_ids: Sequence[str], source_snapshot_ref: str, excluded_counts: Mapping[str, int], dataset_sha256: str)`.
- CLI: `finlabel dataset prepare RUN_ID --output PATH`.
- Training JSONL lines contain only `prompt` and `completion`; each completion is a configured, human-final label. A local manifest contains source/task/model provenance, exact included event and suggestion IDs, a stable source snapshot reference, selected columns, dataset SHA-256, and excluded counts, but no unselected values. For CSV, hash the source file before and after export and abort if it changes. For SQLite, export inside one read transaction and record a snapshot reference derived from the database identity plus the transaction's selected-row digests. A later review event does not mutate a prior export; prepare again to create a new manifest.

- [ ] Re-read each source row through `record_id`; recompute `input_digest` and exclude/flag stale rows instead of silently training on changed values.
- [ ] Ensure one consistent source snapshot during export: compare CSV content hashes before/after and abort on change; use a single SQLite read transaction for all rows and record its snapshot reference. Never publish a partial dataset or manifest on a mismatch.
- [ ] Include accepted and corrected reviews only; exclude rejected, skipped, invalid, stale, and unreviewed suggestions with counts in the manifest.
- [ ] Resolve each suggestion to its latest review event by append order; preserve all earlier events. Use the event ID list and source snapshot/dataset hashes to make each export reproducible.
- [ ] Require an explicit output path/command before creating training files; never write to the source.
- [ ] Manually review, correct, and reject suggestions; prepare a dataset and compare every prompt field and label to the task and review log.

### Task 4: Web review interface

**Files:**
- Modify: `codigo/finlabel/src/finlabel/web/app.py`
- Create: `codigo/finlabel/src/finlabel/web/templates/labeling.html`
- Create: `codigo/finlabel/src/finlabel/web/templates/review.html`
- Create: `codigo/finlabel/src/finlabel/web/templates/training.html`

**Interfaces:**
- Add routes to the existing local FastAPI app: task/source selection, run suggestions, review a suggestion, and prepare a dataset.
- Routes call `LabelTask`, `suggest_labels`, `ReviewLog`, and `prepare_training_dataset` services; templates do not own state transitions.
- Review request carries `run_id`, `suggestion_id`, `record_id`, `input_digest`, idempotency key, action, and optional final label; server revalidates task, source digest, and selected columns before recording.

- [ ] Add task/source forms, suggestion list, selected-field detail, accept/edit/reject controls, review status, and explicit dataset-preparation action.
- [ ] Re-read selected fields only when rendering a local suggestion; show a stale-source warning if the input digest changed.
- [ ] Reuse Plan 1's local-origin/CSRF/security controls for review, dataset creation, and training actions; bound rendered rows and request bodies.
- [ ] Ensure rejected/unreviewed items are visually distinct and cannot be included in the training action.
- [ ] Manually perform accept/edit/reject in the browser; confirm the same persisted decisions appear through `finlabel review` and no source file changed.

### Task 5: Explicit PEFT/LoRA training backend

**Files:**
- Create: `codigo/finlabel/src/finlabel/training/backend.py`
- Modify: `codigo/finlabel/pyproject.toml`
- Modify: `codigo/finlabel/src/finlabel/cli.py`

**Interfaces:**
- `TrainingConfig(model_id: str, model_revision: Optional[str], output_dir: Path, epochs: int, batch_size: int, learning_rate: float, lora_rank: int, seed: int)`.
- `TrainingResult(output_dir: Path, base_model_ref: str, dataset_sha256: str, adapter_files: Sequence[Path], final_metrics: Mapping[str, float])`.
- `train_adapter(dataset_path: PathLike, config: TrainingConfig) -> TrainingResult`.
- Use TRL `SFTTrainer` with `LoraConfig`/PEFT; keep model, tokenizer, dataset, and adapter paths local; set trainer reporting integrations off by default.
- CLI: `finlabel train DATASET --model-id MODEL --output PATH [--epochs N] [--batch-size N] [--learning-rate VALUE] [--lora-rank N] [--seed N]`.
- Training metadata records base model/revision, task, dataset hash, parameters, package versions, and output adapter path.

- [ ] Add a `train` optional extra; fail with a clear installation hint when training dependencies are absent and keep core imports lightweight.
- [ ] Validate dataset schema and nonempty examples before loading model weights; refuse to overwrite an existing output directory.
- [ ] Load weights only after an explicit train command, download only when needed, and save adapter plus metadata locally; do not push to a hub or enable external telemetry.
- [ ] Validate the training config and dataset manifest without loading model weights. Do not load user data for a training run or execute fine-tuning until model, license, hardware, data policy, and academic evaluation protocol are documented in the project and the user authorizes that run.
- [ ] After those gates are satisfied, the local loop may authorize a small training job on suitable hardware; verify the adapter can be reloaded with its recorded base model and that source/review files remain unchanged.

### Task 6: Web fine-tuning action and status

**Files:**
- Modify: `codigo/finlabel/src/finlabel/web/app.py`
- Modify: `codigo/finlabel/src/finlabel/web/templates/training.html`
- Create: `codigo/finlabel/src/finlabel/training/jobs.py`

**Interfaces:**
- `TrainingJobManager.submit(dataset_path: Path, config: TrainingConfig) -> str` and `.get(job_id: str) -> TrainingJobStatus`.
- The web app runs one local training job at a time; status includes `queued`, `running`, `succeeded`, or `failed`, plus sanitized progress/error text. Submission is also subject to the model/data/protocol gate above.
- Starting training requires an explicit user action and uses the same `train_adapter` service as the CLI.

- [ ] Implement one local worker with persisted job metadata and no queue recovery after process exit in the MVP.
- [ ] Add explicit model/adapter/dataset summary and confirmation action before the panel starts training.
- [ ] Show progress and failure without exposing prompts, record values, or stack traces in the browser.
- [ ] Manually start a small job in the panel and confirm its saved adapter/metadata matches a CLI-started job format.

### Task 7: Documentation and milestone acceptance

**Files:**
- Modify: `codigo/finlabel/README.md`
- Modify: `.scratch/biblioteca-rotulagem-financeira/LOOP.md` only if an approved workflow decision changes.

- [ ] Document the task JSON format, review actions, source ID/digest rules, training JSONL format, model prerequisites, optional extras, and model usage terms.
- [ ] Explain that only accepted/corrected human labels become training completions, and that fine-tuning may require suitable hardware and enough examples.
- [ ] Complete the synthetic workflow through explicit dataset preparation. Complete adapter training only after the model/data/protocol gate is satisfied; otherwise validate config and manifest without loading weights and record the deferred manual scenario.
- [ ] Execute manual acceptance scenarios only when each implementation ticket is authorized; record commands not run in that ticket.

## Completion Gate

Plan 2 is ready for human review when CLI and panel share the same review/training services, source data remains read-only, only selected/reviewed fields enter an explicitly prepared dataset, and training capability is available behind the explicit local protocol gate. An actual LoRA run and reload check occur only after the gate is satisfied. Automated tests remain out of scope until explicitly requested under the local ticket loop.
