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

from finlabel.analysis.charts import render_chart
from finlabel.analysis.engine import run_analysis
from finlabel.analysis.planner import HighlightRef, plan_analysis, plan_highlights, render_highlight
from finlabel.analysis.schema import AnalysisPlan, AnalysisResult, plan_to_dict, validate_analysis_plan
from finlabel.models.text_generation import TextGenerationBackend

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
    if plan_override is None:
        if backend is None:
            raise ValueError("Provide a local model backend or an explicit validated plan.")
        plan = plan_analysis(question, source.columns(), backend)
    else:
        plan = validate_analysis_plan(plan_override, source.columns())
    result = run_analysis(source, plan)
    highlights = plan_highlights(question, result, backend) if backend is not None and result.rows else ()
    rendered = tuple(render_highlight(result, item) for item in highlights)
    chart_html = render_chart(result)
    result_json = json.dumps(result_to_dict(result, highlights, rendered), ensure_ascii=False, indent=2) + "\n"
    plan_json = json.dumps(_json_safe(plan_to_dict(plan)), ensure_ascii=False, indent=2) + "\n"
    run_id = uuid4().hex
    if output_path is not None:
        artifact_dir = Path(output_path).expanduser().resolve()
    else:
        parent = Path(output_parent or Path(".finlabel") / "analyses").expanduser().resolve()
        artifact_dir = parent / run_id
    if artifact_dir.exists():
        raise FileExistsError("Analysis output already exists: {}".format(artifact_dir))
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_name": source.spec.name,
        "question": question,
        "model_ref": getattr(backend, "model_id", None) if backend is not None else None,
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
