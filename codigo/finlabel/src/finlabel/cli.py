"""Compatibility entry point; composition and CLI presentation live at their boundaries."""
from finlabel.adapters.outbound.persistence.pipeline_runs import (
    _LABEL_RUN_ID, _PIPELINE_RUN_ID, _canonical_digest, _verified_label_run,
    _verified_pipeline_run, _write_pipeline_run,
)


from finlabel.bootstrap.cli import run as main, run_autonomous_pipeline


if __name__ == "__main__":
    raise SystemExit(main())
