"""Local workspace administration and artifact queries; no inbound/framework imports."""
import json
from dataclasses import replace
from pathlib import Path

from finlabel.adapters.outbound.persistence.projects import init_project, load_project, save_project, open_source
from finlabel.adapters.outbound.sources.base import ProjectConfig, SourceSpec
from finlabel.adapters.outbound.sources.profile import inspect_csv
from finlabel.adapters.outbound.persistence.tasks import load_task, save_task, task_file_path
from finlabel.adapters.outbound.persistence.baselines import load_schema_baseline, save_schema_baseline
from finlabel.adapters.outbound.persistence.datasets import prepare_training_dataset


class FileWorkspace:
    def __init__(self, registry_factory, jobs_factory, trainer, source_factory):
        self.registry_factory = registry_factory
        self.jobs_factory = jobs_factory
        self.trainer = trainer
        self.source_factory = source_factory
        self.jobs = None

    def inspect(self, path, target=None):
        return inspect_csv(path, target=target).to_dict()

    def initialize(self, path):
        return init_project(path)

    def write_new_files(self, directory, files):
        target = Path(directory).expanduser()
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise FileExistsError('Quickstart only writes into a missing or empty directory: {}'.format(target))
        target.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, text in files.items():
            path = target / name
            with path.open('x', encoding='utf-8') as handle:
                handle.write(text)
            paths[name] = str(path.resolve())
        return paths

    def project(self, project):
        return load_project(project)

    def project_metadata(self, config):
        from finlabel.application.ports.projects import ProjectMetadata
        return ProjectMetadata(config.path.parent.parent.name, tuple(config.sources))

    def source(self, config, name):
        return open_source(config, name)

    def configure_source(self, project, source_command, name, path=None, *, column=None,
                         type=None, table=None, id_column=None):
        config = load_project(project)
        if source_command == 'set-type':
            try:
                existing = config.sources[name]
            except KeyError as exc:
                raise ValueError('Unknown source: {}'.format(name)) from exc
            available = {column.name for column in open_source(config, name).columns()}
            if column not in available:
                raise ValueError('Unknown source column: {}'.format(column))
            updated_spec = replace(existing, schema={**existing.schema, column: type})
            updated = ProjectConfig(config.path, {**config.sources, name: updated_spec}, config.model_roles, config.workspace_dir, config.supervision_sources)
            save_project(updated, config.path)
            return {'source': name, 'column': column, 'type': type}
        if name in config.sources:
            raise ValueError('Source name already exists: {}'.format(name))
        kind = 'csv' if source_command == 'add-csv' else 'sqlite'
        spec = SourceSpec(name=name, kind=kind, path=Path(path).expanduser().resolve(), table=table, id_column=id_column)
        self.source_factory(spec).columns()
        updated = ProjectConfig(config.path, {**config.sources, name: spec}, config.model_roles, config.workspace_dir, config.supervision_sources)
        save_project(updated, config.path)
        return {'name': name, 'kind': kind, 'path': str(spec.path)}

    def register_supervision(self, project, source, task, label_column, provenance,
                             trust_kind, label_map=None, refresh=False):
        from finlabel.adapters.outbound.persistence.tasks import load_task, task_file_path
        from finlabel.adapters.outbound.sources.trusted_labels import TrustedLabelSourceSpec, load_trusted_labels, supervision_key
        config = load_project(project)
        if source not in config.sources:
            raise ValueError('Unknown project source: {}'.format(source))
        source_data = open_source(config, source)
        available_columns = tuple((column.name for column in source_data.columns()))
        task = load_task(task_file_path(config.workspace_dir, task), available_columns=available_columns)
        if label_column in task.input_columns:
            raise ValueError('The trusted label column cannot be a task inference input column.')
        if label_column not in available_columns:
            raise ValueError('Unknown trusted label column: {}'.format(label_column))
        if label_map:
            try:
                label_mapping = json.loads(label_map)
            except json.JSONDecodeError as exc:
                raise ValueError('--label-map must be a JSON object.') from exc
            if not isinstance(label_mapping, dict):
                raise ValueError('--label-map must be a JSON object.')
        else:
            label_mapping = {label: label for label in task.labels}
        spec = TrustedLabelSourceSpec(source_name=source, task_id=task.task_id, label_column=label_column, label_mapping=label_mapping, provenance_id=provenance, trust_kind=trust_kind)
        key = supervision_key(task.task_id, source)
        if key in config.supervision_sources:
            existing_spec = TrustedLabelSourceSpec.from_dict(config.supervision_sources[key])
            if existing_spec != spec:
                raise ValueError('A different trusted-label configuration is already registered for this task and source.')
            if not refresh:
                batch = load_trusted_labels(config, task)
                return {'source': source, 'task_id': task.task_id, 'trust_kind': trust_kind, 'rows': batch.row_count, 'feature_columns': list(batch.feature_columns), 'label_column': batch.label_column, 'snapshot_sha256': batch.snapshot_sha256, 'project_config': str(config.path), 'already_registered': True}
        provisional_sources = {**config.supervision_sources, key: spec.to_dict()}
        batch = load_trusted_labels(ProjectConfig(config.path, config.sources, config.model_roles, config.workspace_dir, provisional_sources), task)
        persisted_spec = {**spec.to_dict(), 'snapshot_sha256': batch.snapshot_sha256, 'row_count': batch.row_count}
        updated = ProjectConfig(config.path, config.sources, config.model_roles, config.workspace_dir, {**config.supervision_sources, key: persisted_spec})
        save_project(updated, config.path)
        return {'source': source, 'task_id': task.task_id, 'trust_kind': trust_kind, 'rows': batch.row_count, 'feature_columns': list(batch.feature_columns), 'label_column': batch.label_column, 'snapshot_sha256': batch.snapshot_sha256, 'project_config': str(config.path), 'registry_key': key, 'refreshed': bool(refresh)}

    def add_task(self, project, file):
        config = load_project(project)
        task = load_task(file)
        return save_task(task, task_file_path(config.workspace_dir, task.task_id))

    def task(self, config, task_id, columns=None):
        return load_task(task_file_path(config.workspace_dir, task_id), available_columns=columns)

    def baseline(self, path):
        return load_schema_baseline(path)

    def save_baseline(self, baseline, path):
        save_schema_baseline(baseline, path)

    def prepare_dataset(self, config, run_id, output, *, local_name=False):
        if local_name:
            output = config.workspace_dir / "training" / output
        return prepare_training_dataset(config, run_id, output)

    def train(self, dataset, config, project):
        return self.trainer(dataset, config, gate_path=project.workspace_dir / "training-gate.json")

    def training_jobs(self, workspace):
        if self.jobs is None:
            self.jobs = self.jobs_factory(workspace)
        return self.jobs

    def training_status(self, config, job_id):
        return self.training_jobs(config.workspace_dir).get(job_id)

    def model_status(self, config, task_id):
        registry = self.registry_factory(config.workspace_dir)
        active = registry.active(task_id)
        safe_active = None
        if active is not None:
            safe_active = {key: active.get(key) for key in (
                "model_ref", "candidate_id", "evaluation_id", "previous_model_ref", "rollback_from")
                if active.get(key) is not None}
        events = [{key: event.get(key) for key in (
            "event_id", "candidate_id", "evaluation_id", "task_id", "action", "reason_codes",
            "previous_model_ref", "active_model_ref", "rollback_from", "created_at")
            if event.get(key) is not None} for event in registry.history(task_id)]
        return {"task_id": task_id, "active_model": safe_active, "events": events}

    def confirm_baseline(self, config, source_name, baseline):
        destination = self.baseline_path(config.workspace_dir, source_name)
        save_schema_baseline(baseline, destination)
        return destination

    @staticmethod
    def baseline_path(workspace, source_name):
        import hashlib
        import re
        filename = (source_name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", source_name)
                    else hashlib.sha256(source_name.encode("utf-8")).hexdigest()) + ".json"
        return workspace / "schemas" / filename

    def monitor_baseline(self, config, source_name, baseline_path=None):
        if baseline_path is not None:
            return load_schema_baseline(baseline_path)
        path = self.baseline_path(config.workspace_dir, source_name)
        return load_schema_baseline(path) if path.is_file() else None

    def train_request(self, config, dataset, options):
        from finlabel.adapters.outbound.training.backend import TrainingConfig
        settings = TrainingConfig(options['model_id'], options.get('revision'), Path(options['output']),
            options.get('epochs', 1), options.get('batch_size', 1), options.get('learning_rate', 0.0002),
            options.get('lora_rank', 8), options.get('seed', 42))
        return self.train(dataset, settings, config)

    def submit_training(self, config, dataset_name, model_id, options):
        import secrets
        from finlabel.adapters.outbound.training.backend import TrainingConfig
        dataset_path = (config.workspace_dir / "training" / dataset_name).resolve()
        if dataset_path.parent != (config.workspace_dir / "training").resolve():
            raise ValueError("Dataset path must remain inside the project training directory.")
        output_dir = config.workspace_dir / "models" / "adapters" / secrets.token_hex(16)
        settings = TrainingConfig(model_id, options.get('revision'), output_dir,
            options.get('epochs', 1), options.get('batch_size', 1), options.get('learning_rate', 0.0002),
            options.get('lora_rank', 8), options.get('seed', 42))
        manager = self.training_jobs(config.workspace_dir)
        return manager.get(manager.submit(dataset_path, settings))

    def idempotent_run(self, config, key, payload, execute):
        import hashlib
        from finlabel.application.use_cases.errors import IdempotencyConflict
        from finlabel.adapters.outbound.persistence.idempotency import idempotency_lock, atomic_json
        body_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        root = config.workspace_dir / "idempotency"
        result_path = root / (key_digest + ".json")
        with idempotency_lock(root / (key_digest + ".lock")):
            if result_path.is_file():
                previous = json.loads(result_path.read_text(encoding="utf-8"))
                if previous.get("request_sha256") != body_digest:
                    raise IdempotencyConflict("Idempotency-Key was already used with a different request.")
                saved = previous.get("response")
                expected = hashlib.sha256(json.dumps(saved, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                if previous.get("response_sha256") != expected or not isinstance(saved, dict):
                    raise IdempotencyConflict("Stored idempotency result failed integrity verification.")
                return saved
            response = execute()
            response_digest = hashlib.sha256(json.dumps(response, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            atomic_json(result_path, {"request_sha256": body_digest, "response": response,
                                     "response_sha256": response_digest})
            return response
