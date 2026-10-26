"""CLI composition; model and web runtimes remain optional and lazy."""
from finlabel.adapters.inbound.cli.commands import main
from finlabel.bootstrap.application import build_application


def serve(project, *, host, port):
    from finlabel.bootstrap.http import create_app
    app = create_app(project, host=host, port=port)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to run the local panel.") from exc
    uvicorn.run(app, host=host, port=port, access_log=False)


def run(argv=None, *, application=None):
    return main(argv, application=application, application_factory=build_application, serve=serve)
