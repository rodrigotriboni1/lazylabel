"""Local FastAPI panel with loopback, origin, CSRF, and size protections."""

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import os
import tempfile
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional, Union
from urllib.parse import urlsplit

from finlabel.analysis.planner import AnalysisClarificationError, plan_analysis
from finlabel.domain.analysis.schema import plan_from_dict, plan_to_dict
from finlabel.analysis.service import analyze_source, result_to_dict
from finlabel.domain.analysis.charts import MAX_CHART_POINTS
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


@contextmanager
def _idempotency_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


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
        from fastapi.templating import Jinja2Templates
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to run the local panel.") from exc

    package_dir = Path(__file__).parent
    react_index = package_dir / "static" / "app" / "index.html"
    template_environment = Environment(
        loader=FileSystemLoader(str(package_dir / "templates")),
        autoescape=select_autoescape(("html", "htm", "xml")),
    )
    templates = Jinja2Templates(env=template_environment)
    app = FastAPI(title="FinLabel local", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")
    training_jobs = None

    def react_page(request):
        if not react_index.is_file():
            return PlainTextResponse("FinLabel React assets are missing. Build the frontend first.", status_code=503)
        token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        response = HTMLResponse(react_index.read_text(encoding="utf-8"))
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(CSRF_COOKIE, token, max_age=7200, httponly=False, secure=False,
                                samesite="strict", path="/")
        return response

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

    @app.get("/labeling", response_class=HTMLResponse)
    async def labeling_page(request: Request):
        return react_page(request)

    @app.get("/training", response_class=HTMLResponse)
    async def training_page(request: Request):
        return react_page(request)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return react_page(request)

    @app.get("/analysis", response_class=HTMLResponse)
    @app.get("/monitor", response_class=HTMLResponse)
    @app.get("/review", response_class=HTMLResponse)
    async def react_routes(request: Request):
        return react_page(request)

    @app.get("/api/health")
    async def health():
        config = load_project(project_path)
        return JSONResponse({
            "status": "ok",
            "project": config.path.parent.parent.name,
            "sources": len(config.sources),
        })

    @app.get("/api/sources")
    async def sources():
        """Expose source names and schema metadata without returning source rows."""
        try:
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
                return JSONResponse({"error": "Source metadata exceeds the local response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/autonomy/overview")
    async def autonomy_overview():
        try:
            config = load_project(project_path)
            sources = []
            for name, spec in sorted(config.sources.items()):
                columns = open_source(config, name).columns()
                sources.append({
                    "name": name,
                    "kind": spec.kind,
                    "columns": [{
                        "name": column.name,
                        "inferred_type": column.inferred_type,
                        "mapped_type": spec.schema.get(column.name),
                    } for column in columns],
                })
            from finlabel.labeling.task import load_task, task_file_path
            tasks = []
            for task_path in sorted((config.workspace_dir / "tasks").glob("*.json")):
                try:
                    task = load_task(task_path)
                    tasks.append({
                        "task_id": task.task_id,
                        "input_columns": list(task.input_columns),
                        "labels": list(task.labels),
                        "model_ref": task.model_id + ("@" + task.model_revision if task.model_revision else ""),
                        "policy_configured": task.policy_path is not None,
                    })
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
                    continue

            from finlabel.cli import _verified_pipeline_run
            runs = []
            pipeline_root = config.workspace_dir / "pipeline-runs"
            for run_dir in sorted(pipeline_root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True) if pipeline_root.exists() else []:
                if len(runs) >= 20 or not run_dir.is_dir() or not RUN_ID_PATTERN.fullmatch(run_dir.name):
                    continue
                try:
                    runs.append(_verified_pipeline_run(config.workspace_dir, run_dir.name))
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    continue
            for run in runs:
                run.pop("artifacts", None)

            from finlabel.training.registry import ModelRegistry
            registry = ModelRegistry(config.workspace_dir)
            active_models = []
            for task_id in sorted({task["task_id"] for task in tasks}):
                active = registry.active(task_id)
                if isinstance(active, dict):
                    active_models.append({
                        "task_id": task_id,
                        "model_ref": active.get("model_ref"),
                        "candidate_id": active.get("candidate_id"),
                    })
            cycles = []
            cycles_root = config.workspace_dir / "training" / "cycles"
            from finlabel.training.autopipeline import _valid_cycle_digest
            for cycle_path in sorted(cycles_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if cycles_root.exists() else []:
                if len(cycles) >= 20:
                    break
                try:
                    cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
                    if isinstance(cycle, dict) and isinstance(cycle.get("cycle_id"), str) and _valid_cycle_digest(cycle):
                        summary = {key: cycle.get(key) for key in (
                            "cycle_id", "task_id", "state", "reason_codes", "candidate_id",
                            "evaluation_id", "promotion_action", "active_model_ref", "created_at",
                        )}
                        summary["evaluation"] = None
                        candidate_id = cycle.get("candidate_id")
                        evaluation_id = cycle.get("evaluation_id")
                        if isinstance(candidate_id, str) and isinstance(evaluation_id, str):
                            try:
                                candidate = registry.candidate(candidate_id)
                                evaluation_path = registry.root / "evaluations" / (evaluation_id + ".json")
                                evaluation_bytes = evaluation_path.read_bytes()
                                evaluation = json.loads(evaluation_bytes.decode("utf-8"))
                                if (candidate.get("evaluation_id") == evaluation_id
                                        and hashlib.sha256(evaluation_bytes).hexdigest() == candidate.get("evaluation_sha256")
                                        and evaluation.get("evaluation_id") == evaluation_id
                                        and evaluation.get("task_id") == cycle.get("task_id")
                                        and evaluation.get("candidate_id") == candidate_id
                                        and evaluation.get("same_frozen_holdout") is True):
                                    summary["evaluation"] = {
                                        "holdout_count": evaluation.get("holdout_count"),
                                        "candidate_metrics": evaluation.get("candidate_metrics"),
                                        "incumbent_metrics": evaluation.get("incumbent_metrics"),
                                        "same_frozen_holdout": True,
                                    }
                            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                                pass
                        cycles.append(summary)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
            events = [{key: event.get(key) for key in (
                "event_id", "task_id", "action", "reason_codes", "active_model_ref",
                "rollback_from", "created_at",
            )} for event in registry.history()[-40:]]
            response_payload = {
                "sources": sources, "tasks": tasks, "runs": runs,
                "active_models": active_models, "training_cycles": cycles,
                "model_events": events,
            }
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Autonomy overview exceeds the local web response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/autonomy/run")
    async def autonomy_run(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if set(payload) != {"source", "task"} or not isinstance(payload.get("source"), str) or not isinstance(payload.get("task"), str):
            return JSONResponse({"error": "source and task are required; extra fields are not accepted."}, status_code=400)
        idempotency_key = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key):
            return JSONResponse({"error": "A valid Idempotency-Key header is required."}, status_code=400)
        config = load_project(project_path)
        body_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        key_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        idempotency_root = config.workspace_dir / "idempotency"
        result_path = idempotency_root / (key_digest + ".json")
        try:
            with _idempotency_lock(idempotency_root / (key_digest + ".lock")):
                if result_path.is_file():
                    previous = json.loads(result_path.read_text(encoding="utf-8"))
                    if previous.get("request_sha256") != body_digest:
                        return JSONResponse({"error": "Idempotency-Key was already used with a different request."}, status_code=409)
                    saved = previous.get("response")
                    expected = hashlib.sha256(json.dumps(saved, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                    if previous.get("response_sha256") != expected or not isinstance(saved, dict):
                        return JSONResponse({"error": "Stored idempotency result failed integrity verification."}, status_code=409)
                    return JSONResponse(saved)
                from finlabel.cli import run_autonomous_pipeline
                result = run_autonomous_pipeline(project_path, payload["source"], payload["task"])
                response_payload = {
                    "run_id": result["run_id"],
                    "task_id": result["task_id"],
                    "source": result["source"],
                    "started_at": result["started_at"],
                    "finished_at": result["finished_at"],
                    "labeling": {
                        "run_id": result["label_run_id"],
                        "model_ref": result["label_model_ref"],
                        "applied_count": result["labels"]["applied"],
                        "quarantined_count": result["labels"]["quarantined"],
                        "outcome_count": result["labels"]["applied"] + result["labels"]["quarantined"],
                        "reason_counts": result["labels"]["reason_counts"],
                    },
                    "training": result["training"],
                }
                response_digest = hashlib.sha256(json.dumps(response_payload, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
                _atomic_json(result_path, {"request_sha256": body_digest, "response": response_payload,
                                           "response_sha256": response_digest})
                return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/autonomy/runs/{run_id}")
    async def autonomy_run_status(run_id: str):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return JSONResponse({"error": "Autonomous run not found."}, status_code=404)
        try:
            from finlabel.cli import _verified_pipeline_run
            result = _verified_pipeline_run(load_project(project_path).workspace_dir, run_id)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JSONResponse({"error": "Autonomous run not found or failed integrity verification."}, status_code=404)
        result.pop("artifacts", None)
        return JSONResponse(result)

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
            "valid_row_count": payload["valid_row_count"],
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
        return JSONResponse({"error": "Per-record suggestion runs are retired. Use /api/autonomy/run."}, status_code=410)

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
                    "fields": dict(record.values) if record else None,
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

    @app.post("/api/label/review")
    async def label_review(request: Request):
        return JSONResponse({
            "error": "Per-record human review is retired. Uncertain outcomes are quarantined automatically."
        }, status_code=410)

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

    @app.post("/api/train/submit")
    async def train_submit(request: Request):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if payload.get("confirmed") is not True:
            return JSONResponse({"error": "Review the model, dataset, and output summary, then confirm explicitly."}, status_code=400)
        dataset_name = payload.get("dataset_name")
        model_id = payload.get("model_id")
        if not isinstance(dataset_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.jsonl", dataset_name):
            return JSONResponse({"error": "Select a valid local training dataset."}, status_code=400)
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 512:
            return JSONResponse({"error": "model_id must be a non-empty value from the dataset summary."}, status_code=400)
        if "@" in model_id and payload.get("revision") is None:
            model_id, inferred_revision = model_id.split("@", 1)
        else:
            inferred_revision = None
        try:
            from finlabel.training.backend import TrainingConfig

            config = load_project(project_path)
            dataset_path = (config.workspace_dir / "training" / dataset_name).resolve()
            if dataset_path.parent != (config.workspace_dir / "training").resolve():
                return JSONResponse({"error": "Dataset path must remain inside the project training directory."}, status_code=400)
            output_dir = config.workspace_dir / "models" / "adapters" / secrets.token_hex(16)
            training_config = TrainingConfig(
                model_id, payload.get("revision") or inferred_revision, output_dir,
                payload.get("epochs", 1), payload.get("batch_size", 1),
                payload.get("learning_rate", 0.0002), payload.get("lora_rank", 8), payload.get("seed", 42),
            )
            manager = get_training_jobs(config.workspace_dir)
            job_id = manager.submit(dataset_path, training_config)
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
        })

    @app.get("/analysis/{run_id}", response_class=HTMLResponse)
    async def analysis_page(request: Request, run_id: str):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return PlainTextResponse("Analysis run not found.", status_code=404)
        return react_page(request)

    @app.get("/api/analyses/{run_id}")
    async def analysis_result(run_id: str):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return JSONResponse({"error": "Analysis run not found."}, status_code=404)
        config = load_project(project_path)
        result_path = config.workspace_dir / "analyses" / run_id / "result.json"
        if not result_path.is_file():
            return JSONResponse({"error": "Analysis run not found."}, status_code=404)
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return JSONResponse({"error": "Analysis result is unavailable."}, status_code=404)
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) > MAX_CHART_POINTS:
            return JSONResponse({"error": "Analysis result is unavailable."}, status_code=404)
        response_payload = {
            "run_id": run_id,
            "rows": rows[:MAX_PAGE_ROWS],
            "total_rows": len(rows),
            "valid_row_count": payload.get("valid_row_count", 0),
            "highlights": [item.get("text", "") for item in payload.get("highlights", []) if isinstance(item, dict)],
            "plan": payload.get("plan", {}),
            "formula_metadata": payload.get("formula_metadata", {}),
            "invalid_value_counts": payload.get("invalid_value_counts", {}),
        }
        if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
            return JSONResponse({"error": "Analysis result exceeds the local web response limit."}, status_code=422)
        return JSONResponse(response_payload)

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

    return app
