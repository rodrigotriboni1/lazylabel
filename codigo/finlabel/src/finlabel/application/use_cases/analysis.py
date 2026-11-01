"""Analysis orchestration over a read-only view and injected optional planner."""
from typing import Mapping, Optional
from finlabel.application.ports.sources import ReadOnlySource, SourceReader
from finlabel.application.ports.projects import ProjectLookup
from finlabel.application.ports.analysis import AnalysisPlanner, AnalysisRunStore, RunIdentity
from finlabel.application.use_cases.projects import _require_read_only, _resolve_source
from finlabel.application.use_cases.errors import PlannerUnavailable, PersistenceError
from finlabel.domain.analysis import required_fields, run_analysis
from finlabel.domain.analysis.schema import AnalysisPlan, validate_analysis_plan
from finlabel.domain.analysis.highlights import render_highlight


def analyze_source(source: ReadOnlySource, question: str, planner: Optional[AnalysisPlanner],
                   store: AnalysisRunStore, identity: RunIdentity,
                   plan_override: Optional[AnalysisPlan] = None, *, source_name: str = "",
                   explicit_types: Optional[Mapping[str, str]] = None) -> object:
    _require_read_only(source)
    columns = source.columns()
    if plan_override is None:
        if planner is None:
            raise PlannerUnavailable("Provide a local model backend or an explicit validated plan.")
        plan = planner.plan(question, columns)
    else:
        plan = plan_override
    plan = validate_analysis_plan(plan, columns)
    selected = required_fields(plan)

    def records():
        for record in source.iter_records(selected):
            # Projection is enforced again at the model/business boundary.
            yield {key: record.values[key] for key in selected if key in record.values}

    result = run_analysis(plan, columns, explicit_types or {}, records())
    highlights = tuple(planner.highlights(question, result)) if planner is not None and result.rows else ()
    rendered = tuple(render_highlight(result, item) for item in highlights)
    payload = dict(run_id=identity.new_id(), created_at=identity.now(), source_name=source_name,
                   question=question, model_ref=planner.model_ref if planner is not None else None,
                   result=result, highlights=highlights, rendered_highlights=rendered)
    try:
        return store.save_run(**payload)
    except Exception as exc:
        raise PersistenceError("Could not persist analysis run.") from exc


def analyze_project(projects: ProjectLookup, sources: SourceReader, project_reference: str,
                    source_name: str, question: str, planner: Optional[AnalysisPlanner],
                    store: AnalysisRunStore, identity: RunIdentity,
                    plan_override: Optional[AnalysisPlan] = None, *,
                    explicit_types: Optional[Mapping[str, str]] = None) -> object:
    source = _resolve_source(projects, sources, project_reference, source_name)
    return analyze_source(source, question, planner, store, identity, plan_override,
                          source_name=source_name, explicit_types=explicit_types)
