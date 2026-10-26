"""Local FastAPI panel with loopback, origin, CSRF, and size protections."""

import hmac
import ipaddress
import json
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from finlabel.domain.analysis.schema import plan_from_dict, plan_to_dict
from finlabel.domain.analysis.charts import MAX_CHART_POINTS
from finlabel.domain.monitoring import QualityFinding, SchemaBaseline
from finlabel.application.use_cases.errors import IdempotencyConflict
from finlabel.application.use_cases.errors import AnalysisClarificationError

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


def get_application():
    """Dependency token overridden per app by composition or an embedding client."""
    raise RuntimeError("Application use cases were not composed.")


def _pipeline_response(result):
    return {
        "run_id": result["run_id"], "task_id": result["task_id"], "source": result["source"],
        "started_at": result["started_at"], "finished_at": result["finished_at"],
        "labeling": {"run_id": result["label_run_id"], "model_ref": result["label_model_ref"],
            "applied_count": result["labels"]["applied"], "quarantined_count": result["labels"]["quarantined"],
            "outcome_count": result["labels"]["applied"] + result["labels"]["quarantined"],
            "reason_counts": result["labels"]["reason_counts"]},
        "training": result["training"],
    }


def create_app(
    application,
    assets_directory,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
):
    if not _loopback(host):
        raise ValueError("FinLabel web panel only binds to a loopback host.")
    if not 1 <= int(port) <= 65535:
        raise ValueError("Web panel port must be between 1 and 65535.")
    try:
        from fastapi import Depends, FastAPI, Request
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to run the local panel.") from exc

    package_dir = Path(assets_directory)
    react_index = package_dir / "static" / "app" / "index.html"
    template_environment = Environment(
        loader=FileSystemLoader(str(package_dir / "templates")),
        autoescape=select_autoescape(("html", "htm", "xml")),
    )
    templates = Jinja2Templates(env=template_environment)
    app = FastAPI(title="FinLabel local", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")
    app.state.application = application
    app.dependency_overrides[get_application] = lambda: app.state.application

    def react_page(request):
        if not react_index.is_file():
            return PlainTextResponse("FinLabel React assets are missing. Build the frontend first.", status_code=503)
        token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        response = HTMLResponse(react_index.read_text(encoding="utf-8"))
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(CSRF_COOKIE, token, max_age=7200, httponly=False, secure=False,
                                samesite="strict", path="/")
        return response

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
    async def health(application=Depends(get_application)):
        return JSONResponse(application.health())

    @app.get("/api/sources")
    async def sources(application=Depends(get_application)):
        """Expose source names and schema metadata without returning source rows."""
        try:
            response_payload = application.sources()
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Source metadata exceeds the local response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/autonomy/overview")
    async def autonomy_overview(application=Depends(get_application)):
        try:
            response_payload = application.overview()
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Autonomy overview exceeds the local web response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/autonomy/run")
    async def autonomy_run(request: Request, application=Depends(get_application)):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if set(payload) != {"source", "task"} or not isinstance(payload.get("source"), str) or not isinstance(payload.get("task"), str):
            return JSONResponse({"error": "source and task are required; extra fields are not accepted."}, status_code=400)
        idempotency_key = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key):
            return JSONResponse({"error": "A valid Idempotency-Key header is required."}, status_code=400)
        application.ensure_project()
        try:
            response_payload = application.idempotent_run(idempotency_key, payload,
                lambda: _pipeline_response(application.pipeline(payload["source"], payload["task"])))
            return JSONResponse(response_payload)
        except IdempotencyConflict as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/autonomy/runs/{run_id}")
    async def autonomy_run_status(run_id: str, application=Depends(get_application)):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return JSONResponse({"error": "Autonomous run not found."}, status_code=404)
        try:
            result = application.pipeline_status(run_id)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JSONResponse({"error": "Autonomous run not found or failed integrity verification."}, status_code=404)
        result.pop("artifacts", None)
        return JSONResponse(result)

    @app.post("/api/schema/capture")
    async def schema_capture(request: Request, application=Depends(get_application)):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name = payload.get("source")
        if not isinstance(source_name, str):
            return JSONResponse({"error": "source must be a string"}, status_code=400)
        try:
            candidate = application.capture_schema(source_name)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"candidate": {
            "columns": dict(candidate.columns),
            "required_columns": list(candidate.required_columns),
            "max_missing_ratio": dict(candidate.max_missing_ratio),
            "allow_extra_columns": candidate.allow_extra_columns,
        }})

    @app.post("/api/schema/confirm")
    async def schema_confirm(request: Request, application=Depends(get_application)):
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
            baseline = SchemaBaseline(
                columns=columns,
                required_columns=tuple(required_columns),
                max_missing_ratio=missing_thresholds,
                allow_extra_columns=allow_extra_columns,
            )
            destination = application.confirm_schema(source_name, baseline)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"confirmed": True, "baseline": str(destination)})

    @app.get("/api/monitor")
    async def monitor(request: Request, source: str, application=Depends(get_application)):
        try:
            findings = application.monitor(source)
            if findings is None:
                return JSONResponse({"error": "No confirmed schema exists for this source."}, status_code=404)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        response_payload = {"findings": [_finding_dict(finding) for finding in findings]}
        if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
            return JSONResponse({"error": "The monitoring response exceeds the local web limit; use the CLI."}, status_code=422)
        return JSONResponse(response_payload)

    @app.post("/api/plan")
    async def propose_plan(request: Request, application=Depends(get_application)):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, question = payload.get("source"), payload.get("question")
        if not isinstance(source_name, str) or not isinstance(question, str) or not question.strip() or len(question) > 2000:
            return JSONResponse({"error": "source and a question of 1 to 2000 characters are required"}, status_code=400)
        try:
            plan = application.plan(source_name, question)
            if plan is None:
                return JSONResponse({"error": "Configure a local analytics model or provide a plan directly."}, status_code=400)
        except AnalysisClarificationError as exc:
            return JSONResponse({"needs_clarification": True, "questions": list(exc.questions)}, status_code=422)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"plan": plan_to_dict(plan), "requires_confirmation": True})

    @app.post("/api/analyze")
    async def analyze(request: Request, application=Depends(get_application)):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        source_name, question, raw_plan = payload.get("source"), payload.get("question"), payload.get("plan")
        if not isinstance(source_name, str) or not isinstance(question, str) or len(question) > 2000 or not isinstance(raw_plan, dict):
            return JSONResponse({"error": "source, question, and an inspected plan are required"}, status_code=400)
        try:
            application.ensure_project()
            plan = plan_from_dict(raw_plan)
            run = application.analyze(source_name, question, plan)
            payload = application.analysis_payload(run)
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
    async def label_start(request: Request, application=Depends(get_application)):
        return JSONResponse({"error": "Per-record suggestion runs are retired. Use /api/autonomy/run."}, status_code=410)

    @app.get("/api/label/suggestions")
    async def label_suggestions(run_id: str, application=Depends(get_application)):
        try:
            response_payload = application.suggestions(run_id, MAX_PAGE_ROWS)
            if len(json.dumps(response_payload, ensure_ascii=False).encode("utf-8")) > MAX_API_RESPONSE_BYTES:
                return JSONResponse({"error": "Suggestion page exceeds the local response limit."}, status_code=422)
            return JSONResponse(response_payload)
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/label/review")
    async def label_review(request: Request, application=Depends(get_application)):
        return JSONResponse({
            "error": "Per-record human review is retired. Uncertain outcomes are quarantined automatically."
        }, status_code=410)

    @app.post("/api/dataset/prepare")
    async def dataset_prepare(request: Request, application=Depends(get_application)):
        payload, error = await _read_json(request)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        run_id, output_name = payload.get("run_id"), payload.get("output_name")
        if not isinstance(run_id, str) or not isinstance(output_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.jsonl", output_name):
            return JSONResponse({"error": "run_id and a safe .jsonl output_name are required"}, status_code=400)
        try:
            manifest = application.prepare_dataset(run_id, output_name, local_name=True)
            return JSONResponse({"path": str(manifest.path), "rows": manifest.row_count,
                                 "manifest": str(manifest.path.with_suffix(manifest.path.suffix + ".manifest.json")),
                                 "dataset_sha256": manifest.dataset_sha256})
        except (OSError, ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/train/submit")
    async def train_submit(request: Request, application=Depends(get_application)):
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
            status = application.submit_training(dataset_name, model_id,
                revision=payload.get("revision") or inferred_revision,
                epochs=payload.get("epochs", 1), batch_size=payload.get("batch_size", 1),
                learning_rate=payload.get("learning_rate", 0.0002),
                lora_rank=payload.get("lora_rank", 8), seed=payload.get("seed", 42))
            job_id = status.job_id
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"job_id": job_id, "state": status.state, "progress": status.progress}, status_code=202)

    @app.get("/api/train/jobs/{job_id}")
    async def train_job_status(job_id: str, application=Depends(get_application)):
        try:
            status = application.training_status(job_id)
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
    async def analysis_result(run_id: str, application=Depends(get_application)):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return JSONResponse({"error": "Analysis run not found."}, status_code=404)
        application.ensure_project()
        try:
            payload = application.analysis_result(run_id)
            if payload is None:
                return JSONResponse({"error": "Analysis run not found."}, status_code=404)
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
    async def chart_file(run_id: str, application=Depends(get_application)):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return PlainTextResponse("Analysis chart not found.", status_code=404)
        chart_path = application.chart_path(run_id)
        if chart_path is None:
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
