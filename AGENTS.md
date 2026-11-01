## Agent skills

### Issue tracker

Issues and specs live as Markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo; consult `GLOSSARY.md` and relevant ADRs under `docs/adr/`. See `docs/agents/domain.md`.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. This is
separate from the `.scratch/` Markdown issue tracker above. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python3 -m http.server`, then
open http://localhost:8000/dashboard.html.

Code lives in `codigo/finlabel/` (Python >=3.9, stdlib only, no install step).
Run it with `PYTHONPATH=src python3 -m finlabel.cli ...` from that folder. Tests
are `unittest` files in `codigo/finlabel/tests/`; the validation command is
`bash factory/checks.sh`. There is no dev server.
