"""Public compatibility facade for the composed local HTTP adapter."""


from finlabel.bootstrap.http import create_app


# Historical protocol constants and security helpers remain import-compatible.
from finlabel.adapters.inbound.http.app import (
    CSRF_COOKIE, MAX_API_RESPONSE_BYTES, MAX_PAGE_ROWS, MAX_REQUEST_BYTES,
    RUN_ID_PATTERN, _authority_matches, _finding_dict, _loopback, _read_json,
    _validate_csrf,
)
from finlabel.adapters.outbound.persistence.workspace import FileWorkspace
from finlabel.adapters.outbound.persistence.idempotency import (
    atomic_json as _atomic_json, idempotency_lock as _idempotency_lock,
)

_baseline_path = FileWorkspace.baseline_path
