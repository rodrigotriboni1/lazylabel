"""Composition root: the single place selecting local application adapters."""
from lazylabel.application.use_cases.workspace import WorkspaceApplication
from lazylabel.adapters.outbound.persistence.workspace import FileWorkspace
from lazylabel.adapters.outbound.persistence.panel_queries import FilePanelQueries
from lazylabel.adapters.outbound.persistence.pipeline_runs import FilePipelineRuns
from lazylabel.adapters.outbound.persistence.analysis_runs import FileAnalysisRunStore
from lazylabel.adapters.outbound.persistence.label_runs import FileLabelRunStore
from lazylabel.adapters.outbound.persistence.runtime import LocalRuntime
from lazylabel.adapters.outbound.persistence.registry import ModelRegistry
from lazylabel.adapters.outbound.persistence.prerequisites import FilePrerequisiteChecks
from lazylabel.adapters.outbound.persistence.tasks import load_task_policy
from lazylabel.adapters.outbound.models.analysis_planner import LocalAnalysisPlanner


def build_application(project_reference=".", *, backend_factory=None, workspace=None,
                      queries=None, pipeline_runs_factory=None, analysis_store_factory=None,
                      label_store_factory=None, training_ports_factory=None, runtime=None):
    runtime = runtime if runtime is not None else LocalRuntime()

    def source_factory(spec):
        from lazylabel.adapters.outbound.sources.csv_source import CsvSource
        from lazylabel.adapters.outbound.sources.sqlite_source import SqliteSource
        return {"csv": CsvSource, "sqlite": SqliteSource}[spec.kind](spec)

    def jobs_factory(workspace):
        from lazylabel.adapters.outbound.training.jobs import TrainingJobManager
        return TrainingJobManager(workspace)

    def train_adapter(*args, **kwargs):
        from lazylabel.adapters.outbound.training.backend import train_adapter as train
        return train(*args, **kwargs)

    def training_ports(config):
        if training_ports_factory is not None:
            return training_ports_factory(config)
        from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
        return LocalTrainingEffects(config)

    def analysis_ports(config, *, model_id=None, revision=None, device="auto", output=None, use_configured_model=True):
        backend = None
        if backend_factory is not None:
            backend = backend_factory(config)
        else:
            selected_model = model_id or (config.model_roles.get("analytics") if use_configured_model else None)
            from lazylabel.adapters.outbound.models.gateway import GatewayTextGenerationBackend, is_gateway_model
            if is_gateway_model(selected_model):
                backend = GatewayTextGenerationBackend(selected_model)
            elif selected_model:
                from lazylabel.adapters.outbound.models.text_generation import TransformersTextGenerationBackend
                backend = TransformersTextGenerationBackend(selected_model, revision, device)
        planner = LocalAnalysisPlanner(backend) if backend is not None else None
        factory = analysis_store_factory or FileAnalysisRunStore
        store = factory(output_path=output, output_parent=config.workspace_dir / "analyses")
        return planner, store, runtime

    def labeling_ports(config, task, device):
        policy = load_task_policy(task)
        backend = calibrator = None
        if policy is not None:
            from lazylabel.adapters.outbound.models.active_model import active_inference
            backend, calibrator = active_inference(config, task, policy, device=device)
        return policy, backend, calibrator, (label_store_factory or FileLabelRunStore)(config.workspace_dir), runtime

    return WorkspaceApplication(str(project_reference), workspace=workspace if workspace is not None else
        FileWorkspace(ModelRegistry, jobs_factory, train_adapter, source_factory),
        queries=queries if queries is not None else FilePanelQueries(ModelRegistry),
        pipeline_runs=pipeline_runs_factory or (lambda config: FilePipelineRuns(config.workspace_dir)),
        analysis_ports=analysis_ports, labeling_ports=labeling_ports,
        training_ports=training_ports, runtime=runtime, prerequisite_checks=FilePrerequisiteChecks)
