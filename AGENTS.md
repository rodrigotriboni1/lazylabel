## Agent skills

### Issue tracker

Issues and specs live as Markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo; consult `tcc/glossario.md` and `tcc/decisoes.md`. See `docs/agents/domain.md`.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. This is
separate from the `.scratch/` Markdown issue tracker above. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python3 -m http.server`, then
open http://localhost:8000/dashboard.html.

Code lives in `codigo/finlabel/` (Python >=3.10, FastAPI backend, React frontend
in `frontend/`). Set up a fresh checkout with
`cd codigo/finlabel && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[web,test]' pytest && npm --prefix frontend ci`.
The `models`/`train` extras (torch) are not needed for tests. Frontend dev server:
`npm --prefix frontend run dev -- --port <port>`. The validation command is
`bash factory/checks.sh` (pytest, oxlint, vitest, `tsc -b`; it skips `vite build`
because that rewrites tracked assets in `src/finlabel/web/static/app`).
