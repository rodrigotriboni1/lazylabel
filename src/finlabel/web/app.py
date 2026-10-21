"""Local FastAPI panel with loopback, origin, CSRF, and size protections."""

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
from pathlib import Path
from typing import Callable, Optional, Union
from urllib.parse import urlsplit

from finlabel.analysis.planner import AnalysisClarificationError, plan_analysis
from finlabel.analysis.schema import plan_from_dict, plan_to_dict
from finlabel.analysis.service import analyze_source, result_to_dict
from finlabel.analysis.charts import MAX_CHART_POINTS
from finlabel.monitor import (
    QualityFinding,
    SchemaBaseline,
    capture_schema,
    load_schema_baseline,
    monitor_source,
    save_schema_baseline,
)
from finlabel.project import load_project, open_source

PathLike = Union[str, Path]
MAX_REQUEST_BYTES = 64 * 1024
MAX_PAGE_ROWS = 100
MAX_API_RESPONSE_BYTES = 1024 * 1024
MAX_ANALYSIS_ARTIFACT_BYTES = MAX_API_RESPONSE_BYTES
MAX_ANALYSIS_MANIFEST_BYTES = 64 * 1024
CSRF_COOKIE = "finlabel_csrf"
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _authority_matches(authority: str, host: str, port: int) -> bool:
    try:
        parsed = urlsplit("//" + authority)
        return (
            parsed.hostname is not None
            and parsed.hostname.casefold() == host.casefold()
            and parsed.port == port
            and parsed.username is None
            and parsed.password is None
            and parsed.path == ""
        )
    except ValueError:
        return False


def _baseline_path(workspace: Path, source_name: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", source_name):
        filename = source_name + ".json"
    else:
        filename = hashlib.sha256(source_name.encode("utf-8")).hexdigest() + ".json"
    return workspace / "schemas" / filename


async def _read_json(request):
    if request.headers.get("transfer-encoding"):
        return None, "Chunked request bodies are not accepted."
    content_length = request.headers.get("content-length")
    if content_length is None:
        return None, "Content-Length is required."
    try:
        declared_size = int(content_length)
    except ValueError:
        return None, "Invalid Content-Length."
    if declared_size < 1:
        return None, "A JSON request body is required."
    if declared_size > MAX_REQUEST_BYTES:
        return None, "Request body exceeds the local limit."
    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        return None, "Request body exceeds the local limit."
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "Request body must be valid JSON."
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."
    return payload, None


def _validate_csrf(request):
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    return bool(cookie and header and hmac.compare_digest(cookie, header))


def _finding_dict(finding: QualityFinding):
    return {
        "code": finding.code,
        "severity": finding.severity,
        "column": finding.column,
        "expected": finding.expected,
        "observed": finding.observed,
        "message": finding.message,
    }


def create_app(
    project_path: PathLike,
    backend_factory: Optional[Callable[..., object]] = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
):
    if not _loopback(host):
        raise ValueError("FinLabel web panel only binds to a loopback host.")
    if not 1 <= int(port) <= 65535:
        raise ValueError("Web panel port must be between 1 and 65535.")
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to run the local panel.") from exc

    package_dir = Path(__file__).parent
    app = FastAPI(title="FinLabel local", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")
    training_jobs = None

    def get_training_jobs(workspace):
        nonlocal training_jobs
        if training_jobs is None:
            from finlabel.training.jobs import TrainingJobManager

            training_jobs = TrainingJobManager(workspace)
        return training_jobs

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        authority = request.headers.get("host", "")
        if not _authority_matches(authority, host, int(port)):
            return PlainTextResponse("Invalid local Host header.", status_code=400)
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme != "http"
                or not _authority_matches(parsed_origin.netloc, host, int(port))
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                return PlainTextResponse("Origin is not allowed.", status_code=403)
        if request.method == "POST":
            content_length = request.headers.get("content-length")
            try:
                if request.headers.get("transfer-encoding") or content_length is None or int(content_length) > MAX_REQUEST_BYTES:
                    return PlainTextResponse("Request body exceeds the local limit.", status_code=413)
            except ValueError:
                return PlainTextResponse("Invalid Content-Length.", status_code=400)
            if not _validate_csrf(request):
                return PlainTextResponse("CSRF token is missing or invalid.", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
            )
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_backend(config, *, role="analytics", model_id=None, revision=None):
        if backend_factory is not None:
            return backend_factory(config)
        model_id = model_id or config.model_roles.get(role)
        if not model_id:
            return None
        from finlabel.models.text_generation import TransformersTextGenerationBackend

        return TransformersTextGenerationBackend(model_id, revision)

    def read_label_run(config, run_id):
        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("Invalid suggestion run ID.")
        run_dir = config.workspace_dir / "runs" / run_id
        metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        if metadata.get("run_id") != run_id:
            raise ValueError("Suggestion run metadata does not match the requested run.")
        from finlabel.labeling.suggestions import verify_suggestions_file

        verify_suggestions_file(run_dir / "suggestions.jsonl", metadata.get("suggestions_sha256"))
        from finlabel.labeling.task import task_file_path

        task_file_path(config.workspace_dir, metadata.get("task_id"))
        suggestions = [
            json.loads(line) for line in (run_dir / "suggestions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return run_dir, metadata, suggestions

    def spa_shell(request: Request):
        shell_path = package_dir / "static" / "app" / "index.html"
        if not shell_path.is_file():
            return PlainTextResponse("FinLabel web assets are missing; rebuild the frontend.", status_code=503)
        response = FileResponse(shell_path, media_type="text/html")
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE, secrets.token_urlsafe(32), max_age=7200, httponly=False,
                secure=False, samesite="strict", path="/",
            )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return spa_shell(request)

    @app.get("/api/health")
    async def health():
        config = load_project(project_path)
        return JSONResponse({"status": "ok", "project": Path(project_path).name, "sources": len(config.sources)})

    @app.get("/api/analyses/{run_id}")
    async def analysis_result(run_id: str):
        """Return a verified, bounded analysis artifact for React deep links."""
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return JSONResponse({"error": "Analysis run not found."}, status_code=404)
        try:
            config = load_project(project_path)
            analyses_dir = (config.workspace_dir / "analyses").resolve()
            run_dir = analyses_dir / run_id
            if run_dir.is_symlink() or run_dir.resolve().parent != analyses_dir:
                return JSONResponse({"error": "Analysis run not found."}, status_code=404)
            result_path = run_dir / "result.json"
            manifest_path = run_dir / "run.json"
            if result_path.is_symlink() or manifest_path.is_symlink() or not result_path.is_file() or not manifest_path.is_file():
                return JSONResponse({"error": "Analysis run not found."}, status_code=404)
            if result_path.stat().st_size > MAX_ANALYSIS_ARTIFACT_BYTES:
                return JSONResponse(
                    {"error": "The saved analysis artifact exceeds the local read limit; use the CLI."},
                    status_code=422,
                )
            if manifest_path.stat().st_size > MAX_ANALYSIS_MANIFEST_BYTES:
                return JSONResponse({"error": "Analysis artifact manifest exceeds the local read limit."}, status_code=409)
            # Recheck actual bytes read as well as file metadata so a concurrently growing
            # local artifact cannot bypass the cap between stat() and open().
            with result_path.open("rb") as result_file:
                result_bytes = result_file.read(MAX_ANALYSIS_ARTIFACT_BYTES + 1)
            if len(result_bytes) > MAX_ANALYSIS_ARTIFACT_BYTES:
                return JSONResponse(
                    {"error": "The saved analysis artifact exceeds the local read limit; use the CLI."},
                    status_code=422,
                )
            with manifest_path.open("rb") as manifest_file:
                manifest_bytes = manifest_file.read(MAX_ANALYSIS_MANIFEST_BYTES + 1)
            if len(manifest_bytes) > MAX_ANALYSIS_MANIFEST_BYTES:
                return JSONResponse({"error": "Analysis artifact manifest exceeds the local read limit."}, status_code=409)
            manifest = json.loads(manifest_bytes)
            if manifest.get("run_id") != run_id or not hmac.compare_digest(
                hashlib.sha256(result_bytes).hexdigest(), str(manifest.get("result_sha256", ""))
            ):
                return JSONResponse({"error": "Analysis artifact integrity check failed."}, status_code=409)
            result = json.loads(result_bytes)
            rows = result.get("rows")
            if not isinstance(rows, list) or not isinstance(result.get("plan"), dict):
                return JSONResponse({"error": "Analysis artifact is malformed."}, status_code=409)
            highlights = result.get("highlights", [])
            payload = {
                "run_id": run_id,
                "rows": rows[:MAX_PAGE_ROWS],
                "total_rows": len(rows),
                "highlights": [item.get("text", "") for item in highlights if isinstance(item, dict)],
                "plan": result["plan"],
                "formula_metadata": result.get("formula_metadata", {}),
                "invalid_value_counts": result.get("invalid_value_counts", {}),
            }
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "The analysis result exceeds the local response limit; use the CLI artifact."}, status_code=422)
            return JSONResponse(payload)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": "Analysis artifact is unavailable: {}".format(exc)}, status_code=404)

    @app.get("/api/sources")
    async def sources():
        """Expose source names and schema metadata without reading record values."""
        config = load_project(project_path)
        result = []
        for name in sorted(config.sources):
            source = open_source(config, name)
            result.append({
                "name": name,
                "kind": source.spec.kind,
                "columns": [{
                    "name": column.name,
                    "inferred_type": column.inferred_type,
                    "mapped_type": source.spec.schema.get(column.name),
                    "missing_count": column.missing_count,
                    "non_missing_count": column.non_missing_count,
                } for column in source.columns()],
            })
        response_payload = {"sources": result}
        if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
            return JSONResponse({"error": "The source metadata exceeds the local web response limit; use the CLI."}, status_code=422)
        return JSONResponse(response_payload)

    @app.post("/api/schema/capture")
    async def schema_capture(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name = payload.get("source")
        if not isinstance(source_name, str):
            return JSONResponse({"error": "source must be a string"}, status_code=400)
        try:
            config = load_project(project_path)
            candidate = capture_schema(open_source(config, source_name))
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"candidate": {
            "columns": dict(candidate.columns),
            "required_columns": list(candidate.required_columns),
            "max_missing_ratio": dict(candidate.max_missing_ratio),
            "allow_extra_columns": candidate.allow_extra_columns,
        }})

    @app.post("/api/schema/confirm")
    async def schema_confirm(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, raw = payload.get("source"), payload.get("baseline")
        if not isinstance(source_name, str) or not isinstance(raw, dict):
            return JSONResponse({"error": "source and baseline are required"}, status_code=400)
        columns = raw.get("columns")
        required_columns = raw.get("required_columns")
        missing_thresholds = raw.get("max_missing_ratio", {})
        allow_extra_columns = raw.get("allow_extra_columns", False)
        if (
            not isinstance(columns, dict)
            or not all(isinstance(name, str) and isinstance(kind, str) for name, kind in columns.items())
            or not isinstance(required_columns, list)
            or not all(isinstance(name, str) for name in required_columns)
            or not isinstance(missing_thresholds, dict)
            or not isinstance(allow_extra_columns, bool)
        ):
            return JSONResponse({"error": "baseline fields have invalid types"}, status_code=400)
        try:
            config = load_project(project_path)
            source = open_source(config, source_name)
            available = {column.name for column in source.columns()}
            baseline = SchemaBaseline(
                columns=columns,
                required_columns=tuple(required_columns),
                max_missing_ratio=missing_thresholds,
                allow_extra_columns=allow_extra_columns,
            )
            if (
                not set(baseline.columns).issubset(available)
            ):
                raise ValueError("Confirmed schema must reference columns from the selected source.")
            if not set(baseline.required_columns).issubset(set(baseline.columns)):
                raise ValueError("Required columns must be included in the confirmed schema.")
            for name, ratio in baseline.max_missing_ratio.items():
                if (
                    name not in baseline.columns
                    or isinstance(ratio, bool)
                    or not isinstance(ratio, (int, float))
                    or not 0 <= ratio <= 1
                ):
                    raise ValueError("Missing-value thresholds must map known columns to values from 0 to 1.")
            destination = _baseline_path(config.workspace_dir, source_name)
            save_schema_baseline(baseline, destination)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"confirmed": True, "baseline": str(destination)})

    @app.get("/api/monitor")
    async def monitor(request: Request, source: str):
        try:
            config = load_project(project_path)
            source_data = open_source(config, source)
            baseline_path = _baseline_path(config.workspace_dir, source)
            if not baseline_path.is_file():
                return JSONResponse({"error": "No confirmed schema exists for this source."}, status_code=404)
            findings = monitor_source(source_data, load_schema_baseline(baseline_path))
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        response_payload = {"findings": [_finding_dict(finding) for finding in findings]}
        if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
            return JSONResponse({"error": "The monitoring response exceeds the local web limit; use the CLI."}, status_code=422)
        return JSONResponse(response_payload)

    @app.post("/api/plan")
    async def propose_plan(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, question = payload.get("source"), payload.get("question")
        if not isinstance(source_name, str) or not isinstance(question, str) or not question.strip() or len(question) > 2000:
            return JSONResponse({"error": "source and a question of 1 to 2000 characters are required"}, status_code=400)
        try:
            config = load_project(project_path)
            backend = get_backend(config)
            if backend is None:
                return JSONResponse({"error": "Configure a local analytics model or provide a plan directly."}, status_code=400)
            plan = plan_analysis(question, open_source(config, source_name).columns(), backend)
        except AnalysisClarificationError as exc:
            return JSONResponse({"needs_clarification": True, "questions": list(exc.questions)}, status_code=422)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"plan": plan_to_dict(plan), "requires_confirmation": True})

    @app.post("/api/analyze")
    async def analyze(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, question, raw_plan = payload.get("source"), payload.get("question"), payload.get("plan")
        if not isinstance(source_name, str) or not isinstance(question, str) or len(question) > 2000 or not isinstance(raw_plan, dict):
            return JSONResponse({"error": "source, question, and an inspected plan are required"}, status_code=400)
        try:
            config = load_project(project_path)
            plan = plan_from_dict(raw_plan)
            backend = get_backend(config)
            run = analyze_source(
                open_source(config, source_name), question, backend, plan,
                output_parent=config.workspace_dir / "analyses",
            )
            payload = result_to_dict(run.result, run.highlights, run.rendered_highlights)
            if len(payload["rows"]) > MAX_CHART_POINTS:
                return JSONResponse({"error": "The result has too many groups to show in the panel."}, status_code=422)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        response_payload = {
            "run_id": run.run_id,
            "analysis_url": "/analysis/{}".format(run.run_id),
            "chart_url": "/analysis/{}/chart".format(run.run_id),
            "rows": payload["rows"][:MAX_PAGE_ROWS],
            "total_rows": len(payload["rows"]),
            "highlights": [item["text"] for item in payload["highlights"]],
            "plan": payload["plan"],
            "formula_metadata": payload["formula_metadata"],
            "invalid_value_counts": payload["invalid_value_counts"],
        }
        if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
            return JSONResponse({"error": "The result exceeds the local web response limit; use the CLI artifact."}, status_code=422)
        return JSONResponse(response_payload)

    @app.post("/api/label/start")
    async def label_start(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, task_id = payload.get("source"), payload.get("task")
        if not isinstance(source_name, str) or not isinstance(task_id, str):
            return JSONResponse({"error": "source and task are required"}, status_code=400)
        try:
            from finlabel.labeling.service import suggest_labels
            from finlabel.labeling.task import load_task, task_file_path

            config = load_project(project_path)
            source = open_source(config, source_name)
            task = load_task(task_file_path(config.workspace_dir, task_id),
                             available_columns=tuple(column.name for column in source.columns()))
            backend = get_backend(config, role="labeling", model_id=task.model_id, revision=task.model_revision)
            if backend is None:
                return JSONResponse({"error": "No local model backend is available for this task."}, status_code=400)
            run = suggest_labels(source, task, backend, workspace_dir=config.workspace_dir)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({
            "run_id": run.run_id, "source": run.source_name, "task": run.task_id,
            "suggestions": run.row_count, "invalid": run.invalid_count,
        })

    @app.get("/api/label/tasks")
    async def label_tasks():
        """List task configuration only; never include source-row values."""
        try:
            from finlabel.labeling.task import load_task

            config = load_project(project_path)
            tasks = []
            task_dir = config.workspace_dir / "tasks"
            if task_dir.is_dir():
                for path in sorted(task_dir.glob("*.json")):
                    task = load_task(path)
                    tasks.append({
                        "task_id": task.task_id,
                        "instructions": task.instructions,
                        "input_columns": list(task.input_columns),
                        "labels": list(task.labels),
                        "model_ref": "{}@{}".format(task.model_id, task.model_revision) if task.model_revision else task.model_id,
                        "min_examples_per_label": dict(task.min_examples_per_label),
                    })
            return JSONResponse({"tasks": tasks, "sources": sorted(config.sources)})
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/label/suggestions")
    async def label_suggestions(run_id: str):
        try:
            from finlabel.labeling.task import load_task, task_file_path
            from finlabel.review import ReviewAction, ReviewLog

            config = load_project(project_path)
            run_dir, metadata, suggestions = read_label_run(config, run_id)
            source = open_source(config, metadata["source_name"])
            task = load_task(task_file_path(config.workspace_dir, metadata["task_id"]),
                             available_columns=tuple(column.name for column in source.columns()))
            events = [event for event in ReviewLog(config.workspace_dir / "review.jsonl").read()
                      if event.run_id == run_id and event.suggestion_id]
            latest = {event.suggestion_id: event for event in events}
            page = suggestions[:MAX_PAGE_ROWS]
            wanted = {item["record_id"] for item in page}
            records = {record.record_id: record for record in source.iter_records(task.input_columns)
                       if record.record_id in wanted}
            result = []
            for item in page:
                record = records.get(item["record_id"])
                event = latest.get(item["suggestion_id"])
                result.append({
                    "suggestion_id": item["suggestion_id"], "record_id": item["record_id"],
                    "input_digest": item["input_digest"], "suggested_label": item["label"],
                    "rationale": item.get("rationale"), "labels": list(task.labels),
                    "stale": record is None or record.input_digest != item["input_digest"],
                    "review_action": event.action.value if event else None,
                    "final_label": event.final_label if event else None,
                })
            response_payload = {"run_id": run_id, "task_id": task.task_id, "suggestions": result,
                                "total": len(suggestions), "truncated": len(suggestions) > len(result)}
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Suggestion page exceeds the local response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/label/suggestion")
    async def label_suggestion_detail(run_id: str, suggestion_id: str):
        """Return task-selected values only after an explicit detail request."""
        try:
            from finlabel.labeling.task import load_task, task_file_path

            config = load_project(project_path)
            _, metadata, suggestions = read_label_run(config, run_id)
            item = next((row for row in suggestions if row["suggestion_id"] == suggestion_id), None)
            if item is None:
                return JSONResponse({"error": "Suggestion not found."}, status_code=404)
            source = open_source(config, metadata["source_name"])
            task = load_task(task_file_path(config.workspace_dir, metadata["task_id"]),
                             available_columns=tuple(column.name for column in source.columns()))
            record = next((row for row in source.iter_records(task.input_columns)
                           if row.record_id == item["record_id"]), None)
            response_payload = {
                "fields": dict(record.values) if record else None,
                "stale": record is None or record.input_digest != item["input_digest"],
            }
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse(
                    {"error": "Selected record detail exceeds the local web response limit."}, status_code=422
                )
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/label/review")
    async def label_review(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        required = ("run_id", "suggestion_id", "record_id", "input_digest", "idempotency_key", "action")
        if any(not isinstance(payload.get(key), str) for key in required):
            return JSONResponse({"error": "review provenance and action are required"}, status_code=400)
        if not re.fullmatch(r"[0-9a-f]{32}", payload["idempotency_key"]):
            return JSONResponse({"error": "Invalid review idempotency key."}, status_code=400)
        try:
            from finlabel.labeling.task import load_task, task_file_path, validate_label
            from finlabel.review import ReviewAction, ReviewLog

            config = load_project(project_path)
            _, metadata, suggestions = read_label_run(config, payload["run_id"])
            item = next((row for row in suggestions if row["suggestion_id"] == payload["suggestion_id"]), None)
            if item is None or item["record_id"] != payload["record_id"] or item["input_digest"] != payload["input_digest"]:
                return JSONResponse({"error": "Suggestion provenance does not match this review."}, status_code=409)
            source = open_source(config, metadata["source_name"])
            task = load_task(task_file_path(config.workspace_dir, metadata["task_id"]),
                             available_columns=tuple(column.name for column in source.columns()))
            log = ReviewLog(config.workspace_dir / "review.jsonl")
            prior = log.read()
            duplicate = next((event for event in prior if event.idempotency_key == payload["idempotency_key"]), None)
            if duplicate:
                if duplicate.run_id != payload["run_id"] or duplicate.suggestion_id != payload["suggestion_id"]:
                    return JSONResponse({"error": "Idempotency key was already used for another review."}, status_code=409)
                expected_action = {"accepted": "accepted", "corrected": "corrected", "rejected": "rejected", "skipped": "skipped"}.get(payload["action"])
                if duplicate.action.value != expected_action:
                    return JSONResponse({"error": "Idempotency key was already used for another action."}, status_code=409)
                return JSONResponse({"event_id": duplicate.event_id, "duplicate": True})
            record = next((row for row in source.iter_records(task.input_columns)
                           if row.record_id == item["record_id"]), None)
            if record is None or record.input_digest != item["input_digest"]:
                return JSONResponse({"error": "Source row changed; this suggestion is stale."}, status_code=409)
            action_name = payload["action"]
            if action_name == "accepted":
                action, final_label = ReviewAction.ACCEPTED, item["label"]
            elif action_name == "corrected":
                action, final_label = ReviewAction.CORRECTED, validate_label(task, payload.get("final_label"))
            elif action_name == "rejected":
                action, final_label = ReviewAction.REJECTED, None
            elif action_name == "skipped":
                action, final_label = ReviewAction.SKIPPED, None
            else:
                return JSONResponse({"error": "action must be accepted, corrected, rejected, or skipped"}, status_code=400)
            event = log.record(
                item["record_id"], item["label"], action, final_label, item["model_ref"],
                run_id=payload["run_id"], source_name=metadata["source_name"], task_id=task.task_id,
                input_digest=item["input_digest"], suggestion_id=item["suggestion_id"],
                idempotency_key=payload["idempotency_key"],
            )
            return JSONResponse({"event_id": event.event_id, "duplicate": False})
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/dataset/prepare")
    async def dataset_prepare(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        run_id, output_name = payload.get("run_id"), payload.get("output_name")
        if not isinstance(run_id, str) or not isinstance(output_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.jsonl", output_name):
            return JSONResponse({"error": "run_id and a safe .jsonl output_name are required"}, status_code=400)
        try:
            from finlabel.training.dataset import prepare_training_dataset

            config = load_project(project_path)
            output = config.workspace_dir / "training" / output_name
            manifest = prepare_training_dataset(config, run_id, output)
            return JSONResponse({"path": str(manifest.path), "rows": manifest.row_count,
                                 "manifest": str(manifest.path.with_suffix(manifest.path.suffix + ".manifest.json")),
                                 "dataset_sha256": manifest.dataset_sha256})
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    def training_dataset_path(config, name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.jsonl", name):
            raise ValueError("Select a valid local reviewed dataset.")
        directory = (config.workspace_dir / "training").resolve()
        candidate = directory / name
        if candidate.is_symlink():
            raise ValueError("Symbolic links are not accepted for training datasets.")
        path = candidate.resolve()
        if path.parent != directory or not path.is_file():
            raise ValueError("Dataset must be a regular file inside the project training directory.")
        return path

    def version_payload(version, active_id=None):
        return {
            "version_id": version.version_id, "base_model_ref": version.base_model_ref,
            "dataset_sha256": version.dataset_sha256, "split_sha256": version.split_sha256,
            "created_at": version.created_at, "state": version.state,
            "has_evaluation": version.evaluation_path is not None,
            "is_active": version.version_id == active_id,
            "integrity_valid": True, "integrity_error": None,
        }

    def registry_history_payload(registry):
        inspection = registry.inspect_history()
        entries = []
        for record in inspection["versions"]:
            version = record["version"]
            if version is None:
                entries.append({"version_id": record["version_id"], "state": "invalid",
                    "base_model_ref": "indisponível", "dataset_sha256": "", "split_sha256": "",
                    "created_at": None, "has_evaluation": False, "is_active": False,
                    "integrity_valid": False, "integrity_error": record["integrity_error"], "evaluation": None})
                continue
            item = version_payload(version, inspection["active"].version_id if inspection["active"] else None)
            item["integrity_valid"] = record["integrity_valid"]
            item["integrity_error"] = record["integrity_error"]
            if record["integrity_valid"] and version.evaluation_path:
                report = json.loads(version.evaluation_path.read_text(encoding="utf-8"))
                item["evaluation"] = {"overall": report.get("overall", {}),
                    "per_label": report.get("per_label", []), "confusion": report.get("confusion", {}),
                    "error_count": len(report.get("error_ids", [])), "warnings": report.get("warnings", [])}
            entries.append(item)
        return {"versions": entries,
            "active_version": inspection["active"].version_id if inspection["active"] else None,
            "active_diagnostic": inspection["active_error"],
            "registry_diagnostics": inspection["diagnostics"]}

    @app.get("/api/train/overview")
    async def train_overview():
        try:
            from finlabel.training.dataset import dataset_manifest_path
            from finlabel.training.registry import ModelRegistry

            config = load_project(project_path)
            datasets = []
            directory = config.workspace_dir / "training"
            if directory.is_dir():
                for path in sorted(directory.glob("*.jsonl")):
                    if "." in path.name and path.name.endswith(".jsonl"):
                        try:
                            manifest = json.loads(dataset_manifest_path(path).read_text(encoding="utf-8"))
                            datasets.append({"name": path.name, "rows": manifest.get("row_count", 0),
                                             "task_id": manifest.get("task_id"), "source": manifest.get("source_name"),
                                             "sha256": manifest.get("dataset_sha256")})
                        except (OSError, ValueError, json.JSONDecodeError):
                            datasets.append({"name": path.name, "rows": None, "task_id": None,
                                             "source": None, "sha256": None})
            tasks = []
            task_dir = config.workspace_dir / "tasks"
            if task_dir.is_dir():
                from finlabel.labeling.task import load_task
                tasks = [{"task_id": task.task_id, "labels": list(task.labels),
                          "model_ref": task.model_id + ("@" + task.model_revision if task.model_revision else "")}
                         for task in (load_task(item) for item in sorted(task_dir.glob("*.json")))]
            gate_path = config.workspace_dir / "training-gate.json"
            gate = {"authorized": False,
                    "missing": ["model_id", "license", "hardware", "data_policy", "evaluation_protocol"],
                    "model_id": None}
            if gate_path.is_file() and not gate_path.is_symlink():
                try:
                    raw_gate = json.loads(gate_path.read_text(encoding="utf-8"))
                    gate = {"authorized": raw_gate.get("authorized") is True,
                            "missing": [name for name in ("model_id", "license", "hardware", "data_policy", "evaluation_protocol")
                                        if not isinstance(raw_gate.get(name), str) or not raw_gate[name].strip()],
                            "model_id": raw_gate.get("model_id") if isinstance(raw_gate.get("model_id"), str) else None}
                except (OSError, ValueError, json.JSONDecodeError):
                    gate = {"authorized": False, "missing": ["gate inválido"], "model_id": None}
            registry = ModelRegistry(config.workspace_dir)
            history = registry_history_payload(registry)
            jobs = get_training_jobs(config.workspace_dir).recent()
            evaluation_jobs = get_training_jobs(config.workspace_dir).recent_evaluations()
            job_items = [{"job_id": job.job_id, "state": job.state, "progress": job.progress,
                          "error": job.error, "model_id": job.model_id, "dataset_sha256": job.dataset_sha256,
                          "final_metrics": dict(job.final_metrics), "bundle_id": Path(job.bundle_dir).name if job.bundle_dir else None,
                          "version_id": job.version_id, "created_at": job.created_at} for job in jobs]
            evaluation_job_items = [{"job_id": job.job_id, "state": job.state, "progress": job.progress,
                "error": job.error, "version_id": job.version_id, "created_at": job.created_at}
                for job in evaluation_jobs]
            response_payload = {"datasets": datasets, "tasks": tasks, "gate": gate,
                                **history, "jobs": job_items, "evaluation_jobs": evaluation_job_items}
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Training metadata exceeds the local response limit; use the CLI."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/train/check")
    async def train_check(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        try:
            from dataclasses import asdict
            from finlabel.training.quality import inspect_training_dataset
            config = load_project(project_path)
            report = inspect_training_dataset(config, training_dataset_path(config, payload.get("dataset_name")))
            response_payload = asdict(report)
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Quality report exceeds the local response limit; use the CLI."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/train/split")
    async def train_split(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        try:
            from dataclasses import asdict
            from finlabel.training.dataset import load_dataset_manifest
            from finlabel.training.split import SplitConfig, create_training_bundle
            from finlabel.labeling.task import load_task, task_file_path
            config = load_project(project_path)
            dataset = training_dataset_path(config, payload.get("dataset_name"))
            manifest = load_dataset_manifest(dataset)
            task = load_task(task_file_path(config.workspace_dir, manifest["task_id"]))
            strategy = payload.get("strategy", "stratified_random")
            opts = {"strategy": strategy, "holdout_fraction": payload.get("holdout_fraction", 0.2),
                    "seed": payload.get("seed", 42), "group_column": payload.get("group_column"),
                    "time_column": payload.get("time_column")}
            split_config = SplitConfig(**opts)
            output = config.workspace_dir / "training" / "bundles" / secrets.token_hex(16)
            bundle = create_training_bundle(config, dataset, task, split_config, output)
            summary = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
            response_payload = {"bundle_id": bundle.manifest_path.parent.name, "task_id": task.task_id,
                "train_count": bundle.train_count, "holdout_count": bundle.holdout_count,
                "strategy": summary["strategy"], "holdout_fraction": summary["holdout_fraction"],
                "seed": summary["seed"], "label_counts": summary["label_distributions"],
                "warnings": list(bundle.warnings), "quality": asdict(bundle.quality_report)}
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Split summary exceeds the local response limit; use the CLI."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/train/submit")
    async def train_submit(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if payload.get("confirmed") is not True:
            return JSONResponse({"error": "Review the model, dataset, and output summary, then confirm explicitly."}, status_code=400)
        bundle_id = payload.get("bundle_id")
        model_id = payload.get("model_id")
        if not isinstance(bundle_id, str) or not re.fullmatch(r"[0-9a-f]{32}", bundle_id):
            return JSONResponse({"error": "Select a valid local training bundle."}, status_code=400)
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 512:
            return JSONResponse({"error": "model_id must be a non-empty value from the dataset summary."}, status_code=400)
        if "@" in model_id and payload.get("revision") is None:
            model_id, inferred_revision = model_id.split("@", 1)
        else:
            inferred_revision = None
        try:
            from finlabel.training.backend import TrainingConfig, load_training_bundle

            config = load_project(project_path)
            bundle_candidate = config.workspace_dir / "training" / "bundles" / bundle_id
            bundle_dir = bundle_candidate.resolve()
            if bundle_candidate.is_symlink() or bundle_dir.parent != (config.workspace_dir / "training" / "bundles").resolve():
                return JSONResponse({"error": "Training bundle must remain inside the project workspace."}, status_code=400)
            bundle = load_training_bundle(bundle_dir)
            output_dir = config.workspace_dir / "models" / "adapters" / secrets.token_hex(16)
            training_config = TrainingConfig(
                model_id, payload.get("revision") or inferred_revision, output_dir,
                payload.get("epochs", 1), payload.get("batch_size", 1),
                payload.get("learning_rate", 0.0002), payload.get("lora_rank", 8), payload.get("seed", 42),
            )
            manager = get_training_jobs(config.workspace_dir)
            job_id = manager.submit(bundle, training_config,
                                    exploratory_confirmed=payload.get("exploratory_confirmed") is True)
            status = manager.get(job_id)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"job_id": job_id, "state": status.state, "progress": status.progress}, status_code=202)

    @app.get("/api/train/jobs/{job_id}")
    async def train_job_status(job_id: str):
        try:
            config = load_project(project_path)
            status = get_training_jobs(config.workspace_dir).get(job_id)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse({
            "job_id": status.job_id, "state": status.state, "progress": status.progress,
            "error": status.error, "model_id": status.model_id,
            "dataset_sha256": status.dataset_sha256, "final_metrics": dict(status.final_metrics),
            "bundle_id": Path(status.bundle_dir).name if status.bundle_dir else None,
            "version_id": status.version_id,
        })

    @app.post("/api/train/evaluate")
    async def train_evaluate(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if payload.get("confirmed") is not True:
            return JSONResponse({"error": "Confirme a avaliação local no holdout."}, status_code=400)
        version_id = payload.get("version_id")
        try:
            from finlabel.training.registry import ModelRegistry
            config = load_project(project_path)
            # Validate registry/version identity before the worker is started; model inference runs off-loop.
            ModelRegistry(config.workspace_dir).version(version_id)
            job_id = get_training_jobs(config.workspace_dir).submit_evaluation(version_id)
            status = get_training_jobs(config.workspace_dir).get_evaluation(job_id)
            return JSONResponse({"job_id": job_id, "state": status.state, "progress": status.progress}, status_code=202)
        except KeyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except (OSError, ValueError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/train/evaluations/{job_id}")
    async def train_evaluation_status(job_id: str):
        try:
            config = load_project(project_path)
            status = get_training_jobs(config.workspace_dir).get_evaluation(job_id)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse({"job_id": status.job_id, "state": status.state, "progress": status.progress,
            "error": status.error, "version_id": status.version_id})

    @app.get("/api/train/versions")
    async def train_versions():
        try:
            from finlabel.training.registry import ModelRegistry
            config = load_project(project_path)
            registry = ModelRegistry(config.workspace_dir)
            response_payload = registry_history_payload(registry)
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Version history exceeds the local response limit; use the CLI."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/train/transition")
    async def train_transition(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if payload.get("confirmed") is not True:
            return JSONResponse({"error": "A confirmação explícita da transição é necessária."}, status_code=400)
        action, version_id = payload.get("action"), payload.get("version_id")
        try:
            from finlabel.training.registry import ModelRegistry
            config = load_project(project_path)
            registry = ModelRegistry(config.workspace_dir)
            if action == "activate":
                updated = registry.activate(version_id)
            elif action == "reject":
                updated = registry.reject_candidate(version_id, payload.get("reason", "Rejeitado pelo usuário no painel local."))
            elif action == "rollback":
                updated = registry.rollback(version_id)
            elif action == "recover":
                updated = registry.recover_active(version_id)
            else:
                return JSONResponse({"error": "action must be activate, reject, or rollback."}, status_code=400)
            active = registry.active()
            return JSONResponse({"version": version_payload(updated, active.version_id if active else None),
                                 "active_version": active.version_id if active else None})
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    @app.get("/analysis/{run_id}", response_class=HTMLResponse)
    async def analysis_page(request: Request, run_id: str):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return PlainTextResponse("Analysis run not found.", status_code=404)
        config = load_project(project_path)
        run_dir = config.workspace_dir / "analyses" / run_id
        if run_dir.is_symlink() or not (run_dir / "result.json").is_file():
            return PlainTextResponse("Analysis run not found.", status_code=404)
        return spa_shell(request)

    @app.get("/analysis/{run_id}/chart")
    async def chart_file(run_id: str):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return PlainTextResponse("Analysis chart not found.", status_code=404)
        config = load_project(project_path)
        chart_path = config.workspace_dir / "analyses" / run_id / "chart.html"
        if not chart_path.is_file():
            return PlainTextResponse("Analysis chart not found.", status_code=404)
        return FileResponse(
            chart_path,
            media_type="text/html",
            headers={"Content-Security-Policy": (
                "sandbox allow-scripts; default-src 'self' 'unsafe-inline' data:; "
                "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'self'"
            )},
        )

    @app.get("/analysis", response_class=HTMLResponse)
    @app.get("/monitor", response_class=HTMLResponse)
    @app.get("/review", response_class=HTMLResponse)
    @app.get("/labeling", response_class=HTMLResponse)
    @app.get("/training", response_class=HTMLResponse)
    async def spa_page(request: Request):
        return spa_shell(request)

    @app.get("/api/{unmatched_path:path}")
    async def unknown_api(unmatched_path: str):
        return JSONResponse({"error": "API endpoint not found."}, status_code=404)

    return app
