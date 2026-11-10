"""CLI composition; model and web runtimes remain optional and lazy."""
from lazylabel.adapters.inbound.cli.commands import main
from lazylabel.bootstrap.application import build_application


def serve(project, *, host, port):
    from lazylabel.bootstrap.http import create_app
    app = create_app(project, host=host, port=port)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install lazylabel[web] to run the local panel.") from exc
    uvicorn.run(app, host=host, port=port, access_log=False)


def run(argv=None, *, application=None):
    return main(argv, application=application, application_factory=build_application, serve=serve)


def run_autonomous_pipeline(project_path, source_name, task_id, *, device="auto"):
    """Compose and execute the historical library-facing pipeline command."""
    return build_application(project_path).pipeline(source_name, task_id, device=device)
