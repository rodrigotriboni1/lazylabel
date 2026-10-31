# Missing deterministic count and saved analysis endpoint

Status: resolved
Label: ready-for-human
Branch: `codex/finlabel-dashboard-redesign`

## Problem

The dashboard could not show the valid-row KPI because `/api/analyze` omitted the count already stored with the deterministic result. The React route for reopening a saved analysis requested `/api/analyses/<run_id>`, which the local API did not implement.

## Resolution

The analysis response now includes `valid_row_count`. A bounded local JSON endpoint returns the saved result by validated run ID, including exact rows, plan, metric metadata, invalid-value counts, and highlights. API coverage verifies the original execution and saved result agree.

## Comments

2026-10-25: Implemented and verified in the dashboard redesign branch. No source row values were added to the public analysis payload beyond the already selected/grouped result rows.

2026-10-26: Integrated into `codex/finlabel-autonomous-mvp`. Final route/resolution evidence and the complete test matrix are in `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.
