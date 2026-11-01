"""Shared application entry points for CLI and HTTP, with all effects injected."""
from finlabel.application.ports.workspace import WorkspaceOperations, PanelQueries
from finlabel.application.use_cases.analysis import analyze_source
from finlabel.application.use_cases.labeling import run_labeling
from finlabel.application.use_cases.training import run_training_cycle
from finlabel.application.use_cases.errors import PersistenceError
from finlabel.application.use_cases.prerequisites import prerequisites_checklist


class WorkspaceApplication:
    def __init__(self, project_reference, *, workspace: WorkspaceOperations, queries: PanelQueries, pipeline_runs,
                 analysis_ports, labeling_ports, training_ports, runtime, prerequisite_checks=None):
        self.project_reference = project_reference
        self.workspace = workspace
        self.queries = queries
        self.pipeline_runs = pipeline_runs
        self.analysis_ports = analysis_ports
        self.labeling_ports = labeling_ports
        self.training_ports = training_ports
        self.runtime = runtime
        self.prerequisite_checks = prerequisite_checks

    def inspect(self, path, target=None):
        return self.workspace.inspect(path, target)

    def initialize(self, path):
        return self.workspace.initialize(path)

    def configure_source(self, *args, **kwargs):
        return self.workspace.configure_source(self.project_reference, *args, **kwargs)

    def register_supervision(self, *args, **kwargs):
        return self.workspace.register_supervision(self.project_reference, *args, **kwargs)

    def add_task(self, file):
        return self.workspace.add_task(self.project_reference, file)

    def ensure_project(self):
        self.workspace.project(self.project_reference)

    def health(self):
        config = self.workspace.project(self.project_reference)
        metadata = self.workspace.project_metadata(config)
        return {"status": "ok", "project": metadata.name, "sources": len(metadata.source_names)}

    def sources(self):
        config = self.workspace.project(self.project_reference)
        metadata = self.workspace.project_metadata(config)
        result = []
        for name in sorted(metadata.source_names):
            source = self.workspace.source(config, name)
            result.append({"name": name, "kind": source.kind, "columns": [{
                "name": column.name, "inferred_type": column.inferred_type,
                "mapped_type": source.schema.get(column.name),
                "missing_count": column.missing_count, "non_missing_count": column.non_missing_count,
            } for column in source.columns()]})
        return {"sources": result}

    def overview(self):
        return self.queries.overview(self.project_reference)

    def capture_schema(self, source_name, output=None):
        from finlabel.domain.monitoring import capture_schema
        config = self.workspace.project(self.project_reference)
        candidate = capture_schema(self.workspace.source(config, source_name).columns())
        if output is not None:
            self.workspace.save_baseline(candidate, output)
        return candidate

    def confirm_schema(self, source_name, baseline):
        config = self.workspace.project(self.project_reference)
        available = {column.name for column in self.workspace.source(config, source_name).columns()}
        if not set(baseline.columns).issubset(available):
            raise ValueError("Confirmed schema must reference columns from the selected source.")
        if not set(baseline.required_columns).issubset(set(baseline.columns)):
            raise ValueError("Required columns must be included in the confirmed schema.")
        for name, ratio in baseline.max_missing_ratio.items():
            if (name not in baseline.columns or isinstance(ratio, bool)
                    or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1):
                raise ValueError("Missing-value thresholds must map known columns to values from 0 to 1.")
        return self.workspace.confirm_baseline(config, source_name, baseline)

    def monitor(self, source_name, baseline_path=None):
        from finlabel.domain.monitoring import compare_schema
        config = self.workspace.project(self.project_reference)
        source = self.workspace.source(config, source_name)
        baseline = self.workspace.monitor_baseline(config, source_name, baseline_path)
        if baseline is None:
            return None
        return compare_schema(source.columns(), baseline)

    def plan(self, source_name, question):
        config = self.workspace.project(self.project_reference)
        planner, _, _ = self.analysis_ports(config)
        if planner is None:
            return None
        return planner.plan(question, self.workspace.source(config, source_name).columns())

    def analyze(self, source_name, question, plan=None, *, model_id=None, revision=None,
                device="auto", output=None, use_configured_model=True):
        config = self.workspace.project(self.project_reference)
        source = self.workspace.source(config, source_name)
        planner, store, runtime = self.analysis_ports(config, model_id=model_id, revision=revision,
                                                     device=device, output=output, use_configured_model=use_configured_model)
        try:
            return analyze_source(source, question, planner, store, runtime, plan,
                                  source_name=source_name, explicit_types=source.schema)
        except PersistenceError as exc:
            raise exc.__cause__ from exc

    def label(self, source_name, task_id, *, device="auto"):
        config = self.workspace.project(self.project_reference)
        source = self.workspace.source(config, source_name)
        task = self.workspace.task(config, task_id, tuple(column.name for column in source.columns()))
        policy, backend, calibrator, store, runtime = self.labeling_ports(config, task, device)
        try:
            run = run_labeling(source, source_name, task, policy, backend, store, runtime, calibrator=calibrator)
        except PersistenceError as exc:
            raise exc.__cause__ from exc
        return self.pipeline_runs(config).read_label(run.run_id)

    def pipeline(self, source_name, task_id, *, device="auto"):
        config = self.workspace.project(self.project_reference)
        started = self.runtime.now()
        label = self.label(source_name, task_id, device=device)
        artifacts = self.pipeline_runs(config)
        try:
            effects = self.training_ports(config)
            cycle = run_training_cycle(task_id, configuration=effects, datasets=effects,
                trainer=effects, evaluator=effects, registry=effects, cycles=effects, runtime=effects)
            training = {"cycle_id": cycle.cycle_id, "cycle_sha256": artifacts.cycle_digest(cycle),
                "state": cycle.state, "reason_codes": list(cycle.reason_codes),
                "candidate_id": cycle.candidate_id, "evaluation_id": cycle.evaluation_id,
                "promotion_action": cycle.promotion_action, "active_model_ref": cycle.active_model_ref}
        except Exception as exc:
            training = {"cycle_id": None, "cycle_sha256": None, "state": "blocked",
                "reason_codes": ["training_cycle_failed:" + type(exc).__name__],
                "candidate_id": None, "evaluation_id": None, "promotion_action": None,
                "active_model_ref": None}
        run_id = self.runtime.new_id()
        return artifacts.save_pipeline(run_id, {"schema_version": 1, "run_id": run_id,
            "task_id": label["task_id"], "source_name": source_name, "started_at": started,
            "finished_at": self.runtime.now(), "label_run_id": label["run_id"],
            "label_model_ref": label["model_ref"], "label_outcomes_sha256": label["outcomes_sha256"],
            "training": training})

    def label_status(self, run_id):
        return self.pipeline_runs(self.workspace.project(self.project_reference)).read_label(run_id)

    def pipeline_status(self, run_id):
        return self.pipeline_runs(self.workspace.project(self.project_reference)).read_pipeline(run_id)

    def prerequisites(self, task_id):
        config = self.workspace.project(self.project_reference)
        return prerequisites_checklist(task_id, self.prerequisite_checks(config))

    def model_status(self, task_id):
        return self.workspace.model_status(self.workspace.project(self.project_reference), task_id)

    def suggestions(self, run_id, limit):
        return self.queries.suggestions(self.project_reference, run_id, limit)

    def prepare_dataset(self, run_id, output, *, local_name=False):
        config = self.workspace.project(self.project_reference)
        return self.workspace.prepare_dataset(config, run_id, output, local_name=local_name)

    def train(self, dataset, **options):
        config = self.workspace.project(self.project_reference)
        return self.workspace.train_request(config, dataset, options)

    def submit_training(self, dataset_name, model_id, **options):
        config = self.workspace.project(self.project_reference)
        return self.workspace.submit_training(config, dataset_name, model_id, options)

    def training_status(self, job_id):
        config = self.workspace.project(self.project_reference)
        return self.workspace.training_status(config, job_id)

    def analysis_result(self, run_id):
        return self.queries.analysis_result(self.workspace.project(self.project_reference), run_id)

    def chart_path(self, run_id):
        return self.queries.chart_path(self.workspace.project(self.project_reference), run_id)

    def idempotent_run(self, key, payload, execute):
        config = self.workspace.project(self.project_reference)
        return self.workspace.idempotent_run(config, key, payload, execute)

    def analysis_payload(self, run):
        return self.queries.analysis_payload(run)
