"""Compatibility entry point; composition and CLI presentation live at their boundaries."""
from finlabel.adapters.outbound.persistence.pipeline_runs import (
    _LABEL_RUN_ID, _PIPELINE_RUN_ID, _canonical_digest, _verified_label_run,
    _verified_pipeline_run, _write_pipeline_run,
)


def run_autonomous_pipeline(project_path, source_name, task_id, *, device="auto"):
    from finlabel.bootstrap.application import build_application
    return build_application(project_path).pipeline(source_name, task_id, device=device)


def main(argv=None, *, application=None):
    from finlabel.bootstrap.cli import run
    return run(argv, application=application)


if __name__ == "__main__":
    raise SystemExit(main())
