#!/usr/bin/env bash
# The repo's checks. Exit 0 only when the branch is fit to review.
#
# The gate runs this script from the main checkout with the job's worktree as
# the working directory. Keep it fast, deterministic and non-interactive: no
# watch modes, no prompts, nothing that rewrites files.
set -euo pipefail

cd codigo/finlabel

# Python >=3.10 is required by pyproject; the system python3 is older, so uv fetches one.
# The torch-based extras (models, train) are skipped: tests must not need them.
uv venv --quiet --allow-existing --python 3.12 .venv
uv pip install --quiet --python .venv/bin/python -e '.[web,test]' pytest
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest -q

npm --prefix frontend ci --prefer-offline --no-audit --no-fund --silent
npm --prefix frontend run lint
npm --prefix frontend test -- --run
# `vite build` is left out: it rewrites the tracked assets in src/finlabel/web/static/app.
npm --prefix frontend exec -- tsc -b frontend
