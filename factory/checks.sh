#!/usr/bin/env bash
# The repo's checks. Exit 0 only when the branch is fit to review.
#
# The gate runs this script from the main checkout with the job's worktree as
# the working directory. Keep it fast, deterministic and non-interactive: no
# watch modes, no prompts, nothing that rewrites files.
set -euo pipefail

cd codigo/finlabel
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1

# No linter or typechecker is configured in this project; stdlib only.
python3 -m compileall -q src tests
python3 -m unittest discover -s tests -t . -v
