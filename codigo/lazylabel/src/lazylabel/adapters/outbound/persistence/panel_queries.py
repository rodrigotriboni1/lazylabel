"""Read verified local panel artifacts, preserving projection and response data."""
import hashlib
import json
import re
from pathlib import Path
from lazylabel.adapters.outbound.persistence.projects import load_project, open_source
from lazylabel.adapters.outbound.persistence.tasks import load_task, task_file_path
from lazylabel.adapters.outbound.persistence.reviews import ReviewLog

RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class FilePanelQueries:
    def __init__(self, registry_factory):
        self.registry_factory = registry_factory

    def overview(self, project_path):
        config = load_project(project_path)
        sources = []
        for name, spec in sorted(config.sources.items()):
            columns = open_source(config, name).columns()
            sources.append({'name': name, 'kind': spec.kind, 'columns': [{'name': column.name, 'inferred_type': column.inferred_type, 'mapped_type': spec.schema.get(column.name)} for column in columns]})
        from lazylabel.adapters.outbound.persistence.tasks import load_task, task_file_path
        tasks = []
        for task_path in sorted((config.workspace_dir / 'tasks').glob('*.json')):
            try:
                task = load_task(task_path)
                tasks.append({'task_id': task.task_id, 'input_columns': list(task.input_columns), 'labels': list(task.labels), 'model_ref': task.model_id + ('@' + task.model_revision if task.model_revision else ''), 'policy_configured': task.policy_path is not None})
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
                continue
        from lazylabel.adapters.outbound.persistence.pipeline_runs import _verified_pipeline_run
        runs = []
        pipeline_root = config.workspace_dir / 'pipeline-runs'
        for run_dir in sorted(pipeline_root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True) if pipeline_root.exists() else []:
            if len(runs) >= 20 or not run_dir.is_dir() or (not RUN_ID_PATTERN.fullmatch(run_dir.name)):
                continue
            try:
                runs.append(_verified_pipeline_run(config.workspace_dir, run_dir.name))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        for run in runs:
            run.pop('artifacts', None)
        registry = self.registry_factory(config.workspace_dir)
        active_models = []
        for task_id in sorted({task['task_id'] for task in tasks}):
            active = registry.active(task_id)
            if isinstance(active, dict):
                active_models.append({'task_id': task_id, 'model_ref': active.get('model_ref'), 'candidate_id': active.get('candidate_id')})
        cycles = []
        cycles_root = config.workspace_dir / 'training' / 'cycles'
        from lazylabel.adapters.outbound.training.lifecycle import _valid_cycle_digest
        for cycle_path in sorted(cycles_root.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True) if cycles_root.exists() else []:
            if len(cycles) >= 20:
                break
            try:
                cycle = json.loads(cycle_path.read_text(encoding='utf-8'))
                if isinstance(cycle, dict) and isinstance(cycle.get('cycle_id'), str) and _valid_cycle_digest(cycle):
                    summary = {key: cycle.get(key) for key in ('cycle_id', 'task_id', 'state', 'reason_codes', 'candidate_id', 'evaluation_id', 'promotion_action', 'active_model_ref', 'created_at')}
                    summary['evaluation'] = None
                    candidate_id = cycle.get('candidate_id')
                    evaluation_id = cycle.get('evaluation_id')
                    if isinstance(candidate_id, str) and isinstance(evaluation_id, str):
                        try:
                            candidate = registry.candidate(candidate_id)
                            evaluation_path = registry.root / 'evaluations' / (evaluation_id + '.json')
                            evaluation_bytes = evaluation_path.read_bytes()
                            evaluation = json.loads(evaluation_bytes.decode('utf-8'))
                            if candidate.get('evaluation_id') == evaluation_id and hashlib.sha256(evaluation_bytes).hexdigest() == candidate.get('evaluation_sha256') and (evaluation.get('evaluation_id') == evaluation_id) and (evaluation.get('task_id') == cycle.get('task_id')) and (evaluation.get('candidate_id') == candidate_id) and (evaluation.get('same_frozen_holdout') is True):
                                summary['evaluation'] = {'holdout_count': evaluation.get('holdout_count'), 'candidate_metrics': evaluation.get('candidate_metrics'), 'incumbent_metrics': evaluation.get('incumbent_metrics'), 'same_frozen_holdout': True}
                        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                            pass
                    cycles.append(summary)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
        events = [{key: event.get(key) for key in ('event_id', 'task_id', 'action', 'reason_codes', 'active_model_ref', 'rollback_from', 'created_at')} for event in registry.history()[-40:]]
        response_payload = {'sources': sources, 'tasks': tasks, 'runs': runs, 'active_models': active_models, 'training_cycles': cycles, 'model_events': events}
        return response_payload

    def read_label_run(self, config, run_id):
        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError('Invalid suggestion run ID.')
        run_dir = config.workspace_dir / 'runs' / run_id
        metadata = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
        if metadata.get('run_id') != run_id:
            raise ValueError('Suggestion run metadata does not match the requested run.')
        from lazylabel.adapters.outbound.persistence.suggestions import verify_suggestions_file
        verify_suggestions_file(run_dir / 'suggestions.jsonl', metadata.get('suggestions_sha256'))
        from lazylabel.adapters.outbound.persistence.tasks import task_file_path
        task_file_path(config.workspace_dir, metadata.get('task_id'))
        suggestions = [json.loads(line) for line in (run_dir / 'suggestions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        return (run_dir, metadata, suggestions)

    def suggestions(self, project_path, run_id, limit):
        from lazylabel.adapters.outbound.persistence.tasks import load_task, task_file_path
        from lazylabel.adapters.outbound.persistence.reviews import ReviewAction, ReviewLog
        config = load_project(project_path)
        run_dir, metadata, suggestions = self.read_label_run(config, run_id)
        source = open_source(config, metadata['source_name'])
        task = load_task(task_file_path(config.workspace_dir, metadata['task_id']), available_columns=tuple((column.name for column in source.columns())))
        events = [event for event in ReviewLog(config.workspace_dir / 'review.jsonl').read() if event.run_id == run_id and event.suggestion_id]
        latest = {event.suggestion_id: event for event in events}
        page = suggestions[:limit]
        wanted = {item['record_id'] for item in page}
        records = {record.record_id: record for record in source.iter_records(task.input_columns) if record.record_id in wanted}
        result = []
        for item in page:
            record = records.get(item['record_id'])
            event = latest.get(item['suggestion_id'])
            result.append({'suggestion_id': item['suggestion_id'], 'record_id': item['record_id'], 'input_digest': item['input_digest'], 'suggested_label': item['label'], 'rationale': item.get('rationale'), 'labels': list(task.labels), 'fields': dict(record.values) if record else None, 'stale': record is None or record.input_digest != item['input_digest'], 'review_action': event.action.value if event else None, 'final_label': event.final_label if event else None})
        response_payload = {'run_id': run_id, 'task_id': task.task_id, 'suggestions': result, 'total': len(suggestions), 'truncated': len(suggestions) > len(result)}
        return response_payload

    def analysis_result(self, config, run_id):
        path = config.workspace_dir / "analyses" / run_id / "result.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def chart_path(self, config, run_id):
        path = config.workspace_dir / "analyses" / run_id / "chart.html"
        return path if path.is_file() else None

    def analysis_payload(self, run):
        from lazylabel.adapters.outbound.persistence.analysis_runs import result_to_dict
        return result_to_dict(run.result, run.highlights, run.rendered_highlights)
