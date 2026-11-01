from dataclasses import dataclass

from finlabel.application.ports.projects import ProjectMetadata
from finlabel.application.use_cases.workspace import WorkspaceApplication
from finlabel.domain.projects import ColumnProfile


class PortOnlySource:
    name = "ledger"
    kind = "csv"
    schema = {"amount": "decimal"}

    def capabilities(self):
        raise AssertionError("metadata paths do not require source capabilities")

    def columns(self):
        return [ColumnProfile("amount", "number", 0, 2)]

    def iter_records(self, columns, *, batch_size=1000):
        return iter(())


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: str
    progress: str
    error: str | None
    model_id: str
    dataset_sha256: str
    final_metrics: dict


class OpaqueWorkspace:
    def __init__(self):
        self.handle = object()
        self.job_status = JobStatus("job-1", "queued", "waiting", None, "local-model", "a" * 64, {})
        self.status_request = None

    def project(self, reference):
        assert reference == "project-ref"
        return self.handle

    def project_metadata(self, project):
        assert project is self.handle
        return ProjectMetadata(name="demo", source_names=("ledger",))

    def source(self, project, name):
        assert project is self.handle
        assert name == "ledger"
        return PortOnlySource()

    def training_status(self, project, job_id):
        self.status_request = (project, job_id)
        return self.job_status


def test_workspace_use_case_uses_declared_metadata_and_job_status_ports():
    workspace = OpaqueWorkspace()
    application = WorkspaceApplication(
        "project-ref", workspace=workspace, queries=None, pipeline_runs=None,
        analysis_ports=None, labeling_ports=None, training_ports=None, runtime=None,
    )

    assert application.health() == {"status": "ok", "project": "demo", "sources": 1}
    assert application.sources() == {"sources": [{
        "name": "ledger", "kind": "csv", "columns": [{
            "name": "amount", "inferred_type": "number", "mapped_type": "decimal",
            "missing_count": 0, "non_missing_count": 2,
        }],
    }]}
    assert application.training_status("job-1") == workspace.job_status
    assert workspace.status_request == (workspace.handle, "job-1")
