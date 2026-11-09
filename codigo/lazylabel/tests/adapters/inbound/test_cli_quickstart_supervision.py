import json

from lazylabel.adapters.outbound.persistence.workspace import FileWorkspace

from tests.adapters.inbound.test_cli_quickstart import cli


def test_registers_sample_labels(tmp_path):
    target = tmp_path / "x"
    status, out, _ = cli("quickstart", str(target), "--model-id", "m")
    assert status == 0
    assert "operator declaration" in out and "Optional later" not in out
    entry = json.loads((target / ".lazylabel/project.json").read_text())["supervision_sources"]["sample::sample"]
    assert (entry["source_name"], entry["task_id"], entry["label_column"]) == ("sample", "sample", "reference_label")
    assert (entry["provenance_id"], entry["trust_kind"]) == ("synthetic-sample", "provided_ground_truth")
    assert entry["row_count"] == 40 and len(entry["snapshot_sha256"]) == 64


def test_registration_failure_keeps_files(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(FileWorkspace, "register_supervision", boom)
    target = tmp_path / "x"
    status, _, err = cli("quickstart", str(target), "--model-id", "m")
    assert status == 2 and err.startswith("lazylabel:") and "boom" in err
    for name in ("lazylabel-sample-synthetic.csv", "task.json", "policy.json", ".lazylabel/tasks/sample.json"):
        assert (target / name).is_file()
    project = json.loads((target / ".lazylabel/project.json").read_text())
    assert "sample" in project["sources"] and not project["supervision_sources"]
