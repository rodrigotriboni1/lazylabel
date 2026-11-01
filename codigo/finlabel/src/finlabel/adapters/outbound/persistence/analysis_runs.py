"""Analysis orchestration and collision-safe local artifact persistence."""

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence, Union
from uuid import uuid4

from finlabel.adapters.outbound.persistence.charts import render_chart
from finlabel.adapters.outbound.models.analysis_planner import HighlightRef, plan_analysis, plan_highlights, render_highlight
from finlabel.domain.analysis.schema import AnalysisPlan, AnalysisResult, plan_to_dict
from finlabel.adapters.outbound.models.text_generation import TextGenerationBackend

PathLike = Union[str, Path]


@dataclass(frozen=True)
class AnalysisRun:
    run_id: str
    artifact_dir: Path
    result: AnalysisResult
    highlights: Sequence[HighlightRef]
    rendered_highlights: Sequence[str]


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(value.value, (str, int, float)):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def result_to_dict(result: AnalysisResult, highlights=(), rendered_highlights=()) -> dict:
    return {
        "version": 1,
        "plan": _json_safe(plan_to_dict(result.plan)),
        "rows": _json_safe(list(result.rows)),
        "valid_row_count": result.valid_row_count,
        "invalid_value_counts": dict(result.invalid_value_counts),
        "selected_fields": list(result.selected_fields),
        "formula_metadata": _json_safe(dict(result.formula_metadata)),
        "highlights": [
            {
                "result_key": _json_safe(list(reference.result_key)),
                "observation": reference.observation,
                "text": rendered_highlights[index],
            }
            for index, reference in enumerate(highlights)
        ],
    }


def analyze_source(
    source,
    question: str,
    backend: Optional[TextGenerationBackend],
    plan_override: Optional[AnalysisPlan] = None,
    *,
    output_path: Optional[PathLike] = None,
    output_parent: Optional[PathLike] = None,
) -> AnalysisRun:
    # Transitional bridge: concrete wiring moves to bootstrap in the adapter milestone.
    from finlabel.application.use_cases.analysis import analyze_source as execute
    from finlabel.application.use_cases.errors import PersistenceError

    class Planner:
        model_ref = getattr(backend, "model_id", None)
        def plan(self, question, columns):
            return plan_analysis(question, columns, backend)
        def highlights(self, question, result):
            return plan_highlights(question, result, backend)

    class Identity:
        def new_id(self):
            return uuid4().hex
        def now(self):
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    class Store:
        def save_run(self, **payload):
            return _persist_analysis(**payload, output_path=output_path, output_parent=output_parent)

    try:
        return execute(source, question, Planner() if backend is not None else None, Store(), Identity(),
                       plan_override, source_name=source.spec.name, explicit_types=source.spec.schema)
    except PersistenceError as exc:
        raise exc.__cause__ from exc


def _persist_analysis(*, run_id, created_at, source_name, question, model_ref, result,
                      highlights, rendered_highlights, output_path, output_parent):
    rendered = rendered_highlights
    plan = result.plan
    chart_html = render_chart(result)
    result_json = json.dumps(result_to_dict(result, highlights, rendered), ensure_ascii=False, indent=2) + "\n"
    plan_json = json.dumps(_json_safe(plan_to_dict(plan)), ensure_ascii=False, indent=2) + "\n"
    if output_path is not None:
        artifact_dir = Path(output_path).expanduser().resolve()
    else:
        parent = Path(output_parent or Path(".finlabel") / "analyses").expanduser().resolve()
        artifact_dir = parent / run_id
    if artifact_dir.exists():
        raise FileExistsError("Analysis output already exists: {}".format(artifact_dir))
    manifest = {
        "run_id": run_id,
        "created_at": created_at,
        "source_name": source_name,
        "question": question,
        "model_ref": model_ref,
        "plan_sha256": hashlib.sha256(plan_json.encode("utf-8")).hexdigest(),
        "result_sha256": hashlib.sha256(result_json.encode("utf-8")).hexdigest(),
        "chart_sha256": hashlib.sha256(chart_html.encode("utf-8")).hexdigest(),
    }
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(exist_ok=False)
    try:
        (artifact_dir / "plan.json").write_text(plan_json, encoding="utf-8")
        (artifact_dir / "result.json").write_text(result_json, encoding="utf-8")
        (artifact_dir / "chart.html").write_text(chart_html, encoding="utf-8")
        (artifact_dir / "run.json").write_text(manifest_json, encoding="utf-8")
    except OSError:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise
    return AnalysisRun(run_id, artifact_dir, result, tuple(highlights), rendered)


class FileAnalysisRunStore:
    """Serialize an analysis as one atomically published local artifact set."""

    def __init__(self, *, output_path=None, output_parent=None):
        self.output_path = output_path
        self.output_parent = output_parent

    def save_run(self, **payload):
        import os
        import tempfile
        from dataclasses import replace

        if self.output_path is not None:
            destination = Path(self.output_path).expanduser().resolve()
        else:
            parent = Path(self.output_parent or Path('.finlabel') / 'analyses').expanduser().resolve()
            destination = parent / payload['run_id']
        if destination.exists():
            raise FileExistsError('Analysis output already exists: {}'.format(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-', dir=str(destination.parent)))
        try:
            staged = staging_root / 'run'
            receipt = _persist_analysis(**payload, output_path=staged, output_parent=None)
            for path in staged.iterdir():
                with path.open('rb') as handle:
                    os.fsync(handle.fileno())
            descriptor = os.open(str(staged), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if destination.exists():
                raise FileExistsError('Analysis output already exists: {}'.format(destination))
            os.replace(staged, destination)
            descriptor = os.open(str(destination.parent), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return replace(receipt, artifact_dir=destination)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
