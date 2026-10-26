"""Local model planning and result-grounded highlight references."""

import json
from typing import Sequence

from finlabel.domain.analysis.schema import AnalysisPlan, AnalysisResult, plan_from_dict, validate_analysis_plan
from finlabel.models.text_generation import TextGenerationBackend
from finlabel.domain.projects import ColumnProfile
from finlabel.domain.analysis.highlights import HighlightRef, render_highlight, _resolve_highlight, _json_value

OBSERVATIONS = {"highest", "lowest", "largest_share", "smallest_share", "overall_increase", "overall_decrease", "notable"}


class AnalysisClarificationError(ValueError):
    def __init__(self, questions: Sequence[str]):
        self.questions = tuple(questions)
        super().__init__("Analysis needs clarification: {}".format(" ".join(self.questions)))


def _load_response(text: str):
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Local model must return one JSON object without prose or code fences.") from exc
    if not isinstance(value, dict):
        raise ValueError("Local model response must be a JSON object.")
    return value


def plan_analysis(question: str, schema: Sequence[ColumnProfile], backend: TextGenerationBackend) -> AnalysisPlan:
    if not question or not question.strip():
        raise ValueError("An analysis question is required.")
    columns = [{"name": column.name, "inferred_type": column.inferred_type} for column in schema]
    prompt_template = (
        "You are a local analytics planner. Use only this schema and question; no data rows are provided.\n"
        "Return exactly one JSON object. Either return {\"needs_clarification\":true,\"questions\":[...]} "
        "or an AnalysisPlan v1 with fields version, metric {operation,column,denominator_scope}, dimensions, "
        "time_axis {column,grain} or null, filters [{column,operation,value}], and chart.\n"
        "Allowed metrics: count_rows, sum, average, distinct_count, share_of_total. Allowed filters: eq, neq, in, gt, gte, lt, lte, between. "
        "Allowed chart kinds: line, bar, stacked_bar. For share_of_total explicitly set denominator_scope; use [] only when the denominator "
        "is the whole selected population within the time bucket. Ask questions when measure, grouping, period, or denominator is ambiguous. "
        "Do not invent columns.\nSchema: {schema}\nQuestion: {question}\nJSON:"
    )
    prompt = prompt_template.replace("{schema}", json.dumps(columns, ensure_ascii=False))
    prompt = prompt.replace("{question}", question[:2000])
    response = _load_response(backend.generate(prompt, max_new_tokens=700))
    if response.get("needs_clarification") is True:
        questions = response.get("questions")
        if not isinstance(questions, list) or not questions or not all(isinstance(item, str) and item.strip() for item in questions):
            raise ValueError("Clarification response must include non-empty questions.")
        raise AnalysisClarificationError(questions)
    plan_raw = response.get("plan", response)
    if not isinstance(plan_raw, dict):
        raise ValueError("Local model plan must be a JSON object.")
    plan = plan_from_dict(plan_raw)
    validate_analysis_plan(plan, schema)
    normalized = question.casefold()
    asks_market_share = (
        "market share" in normalized
        or "participação de mercado" in normalized
        or "participacao de mercado" in normalized
    )
    if asks_market_share and (
        plan.metric.operation != "share_of_total"
        or plan.metric.denominator_scope is None
        or not plan.dimensions
        or plan.time_axis is None
    ):
        raise AnalysisClarificationError((
            "Mapeie a medida, o grupo que representa o mercado, o período e o denominador antes de calcular market share.",
        ))
    return plan


def plan_highlights(question: str, result: AnalysisResult, backend: TextGenerationBackend) -> Sequence[HighlightRef]:
    group_fields = list(result.formula_metadata.get("group_fields", []))
    time_column = result.plan.time_axis.column if result.plan.time_axis else None
    dimension_fields = [name for name in group_fields if name != time_column]
    rows = [
        {"key": [_json_value(row.get(name)) for name in group_fields], "value": _json_value(row.get("value"))}
        for row in result.rows
    ]
    prompt = (
        "Choose up to three grounded observations from these already calculated aggregate rows. Do not calculate or write numeric values.\n"
        "Return exactly {\"highlights\":[{\"result_key\":[...],\"observation\":\"...\"}]}. Point observations use the full row key "
        "in group_fields order. overall_increase/overall_decrease use the dimension-only key.\n"
        "Allowed observations: {observations}.\nQuestion: {question}\ngroup_fields: {groups}\ndimension_fields: {dimensions}\n"
        "time_field: {time_field}\ncalculated_rows: {rows}\nJSON:"
    )
    for placeholder, value in (
        ("{observations}", ", ".join(sorted(OBSERVATIONS))),
        ("{question}", question[:1000]),
        ("{groups}", json.dumps(group_fields, ensure_ascii=False)),
        ("{dimensions}", json.dumps(dimension_fields, ensure_ascii=False)),
        ("{time_field}", json.dumps(time_column)),
        ("{rows}", json.dumps(rows, ensure_ascii=False)),
    ):
        prompt = prompt.replace(placeholder, value)
    response = _load_response(backend.generate(prompt, max_new_tokens=350))
    if set(response) != {"highlights"} or not isinstance(response["highlights"], list):
        raise ValueError("Highlight response must contain only a highlights list.")
    refs = []
    for item in response["highlights"]:
        if not isinstance(item, dict) or set(item) != {"result_key", "observation"}:
            raise ValueError("Each highlight must contain only result_key and observation.")
        key = item["result_key"]
        observation = item["observation"]
        if not isinstance(key, list) or observation not in OBSERVATIONS:
            raise ValueError("Highlight reference or observation kind is invalid.")
        reference = HighlightRef(tuple(key), observation)
        _resolve_highlight(result, reference)
        refs.append(reference)
    return refs
