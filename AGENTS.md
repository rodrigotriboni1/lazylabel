## Agent skills

### Issue tracker (local Markdown)

Issues and specs live as Markdown files under `.scratch/` (created on demand).

- One feature per directory: `.scratch/<feature-slug>/`; the spec is `spec.md`; tickets are `issues/<NN>-<slug>.md`, numbered from `01`, one file each.
- Triage state is a `Status:` line near the top; comments append under `## Comments`.
- "Publish to the issue tracker" = create a file under `.scratch/<feature-slug>/`. "Fetch the ticket" = read the path the user gives.
- Wayfinding: map in `.scratch/<effort>/map.md`; child tickets in `issues/NN-<slug>.md` with `Type:` (`research`/`prototype`/`grilling`/`task`), `Status:` (`claimed`/`resolved`) and optional `Blocked by: NN, NN`. Claim before working; resolve by appending `## Answer`, setting `Status: resolved` and adding a pointer to the map's Decisions-so-far.

### Triage labels

The five canonical labels are used as-is: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

### Domain docs

Single-context repo. Before exploring, read `tcc/glossario.md` (use its terms in issues, specs, tests and names) and `tcc/decisoes.md`. If your output contradicts a decision, say so explicitly ("contradicts decisão 1, because…") instead of overriding it.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. This is
separate from the `.scratch/` Markdown issue tracker above. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python3 -m http.server`, then
open http://localhost:8000/dashboard.html.

Code lives in `codigo/lazylabel/` (Python >=3.10, FastAPI backend, React frontend
in `frontend/`). Set up a fresh checkout with
`cd codigo/lazylabel && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[web,test]' pytest && npm --prefix frontend ci`.
The `models`/`train` extras (torch) are not needed for tests. Frontend dev server:
`npm --prefix frontend run dev -- --port <port>`. The validation command is
`bash factory/checks.sh` (pytest, oxlint, vitest, `tsc -b`; it skips `vite build`
because that rewrites tracked assets in `src/lazylabel/web/static/app`).
