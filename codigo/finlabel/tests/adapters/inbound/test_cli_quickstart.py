import io
from contextlib import redirect_stderr, redirect_stdout

from finlabel.bootstrap.application import build_application
from finlabel.bootstrap.cli import run
from finlabel.labeling.task import load_task, load_task_policy


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            status = run(list(argv))
        except SystemExit as exc:
            status = exc.code
    return status, out.getvalue(), err.getvalue()


def test_happy_path(tmp_path):
    target = tmp_path / "x"
    status, out, _ = cli("quickstart", str(target), "--model-id", "some/model")
    assert status == 0
    for text in ("finlabel label sample --task sample --project", "finlabel serve --project",
                 "uncalibrated", "illustrative"):
        assert text in out
    for name in ("finlabel-sample-synthetic.csv", "task.json", "policy.json",
                 ".finlabel/project.json", ".finlabel/tasks/sample.json"):
        assert (target / name).is_file()
    rows = (target / "finlabel-sample-synthetic.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "fake_amount,fake_days_past_due,fake_utilization,reference_label"
    assert len(rows) == 41 and {row.split(",")[3] for row in rows[1:]} == {"low", "medium", "high"}
    app = build_application(str(target))
    (source,) = app.sources()["sources"]
    assert source["name"] == "sample"
    assert [c["name"] for c in source["columns"]] == rows[0].split(",")
    for path in (target / "task.json", target / ".finlabel/tasks/sample.json"):
        task = load_task(str(path))
        assert "reference_label" not in task.input_columns
        assert (task.model_id, task.model_revision) == ("some/model", None)
        policy = load_task_policy(task)
        assert policy.calibration_ref is None and set(policy.allowed_labels) == {"low", "medium", "high"}


def test_model_revision(tmp_path):
    status, _, _ = cli("quickstart", str(tmp_path / "x"), "--model-id", "m", "--model-revision", "abc123")
    assert status == 0
    assert load_task(str(tmp_path / "x/.finlabel/tasks/sample.json")).model_revision == "abc123"


def test_missing_model_id(tmp_path):
    status, _, err = cli("quickstart", str(tmp_path / "y"))
    assert status == 2 and "usage" in err
    assert not (tmp_path / "y").exists()


def test_refuses_non_empty_directory(tmp_path):
    target = tmp_path / "z"
    target.mkdir()
    (target / "a.txt").write_text("keep")
    status, _, err = cli("quickstart", str(target), "--model-id", "m")
    assert status == 2 and err.startswith("finlabel:")
    assert [p.name for p in target.iterdir()] == ["a.txt"] and (target / "a.txt").read_text() == "keep"


def test_refuses_existing_project(tmp_path):
    target = tmp_path / "x"
    cli("quickstart", str(target), "--model-id", "m")
    before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
    status, _, err = cli("quickstart", str(target), "--model-id", "m")
    assert status == 2 and err.startswith("finlabel:")
    assert before == {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
