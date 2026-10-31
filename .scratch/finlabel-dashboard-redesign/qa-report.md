# FinLabel dashboard redesign QA

Date: 2026-10-25
Branch: `codex/finlabel-dashboard-redesign`
Fixture: local synthetic portfolio data served by the Vite visual fixture; no personal data or model inference.

## Reviewed

- Analysis route opened directly and reloaded with a saved run ID.
- Desktop viewport 1440×900: KPI row, category × period heatmap, trend chart, plan metadata, denominator, highlights, and exact-results table.
- Mobile viewport 390×844: same analysis route and the seven-step training workflow.
- Accessible tree includes the heatmap as a table with exact values, row/column labels, and a textual missing-cell label.
- At 390px, `document.documentElement.scrollWidth`, `document.body.scrollWidth`, and `window.innerWidth` were all 390px on the analysis and training routes. The heatmap has its own horizontal scroll container when needed.
- Training diagram retained seven ordered stages and exposes the current stage and sequence in accessibility text.

## Findings fixed

- Analysis JSON moved under “Avançado”.
- Contextual KPI cards and category × period heatmap added. Missing combinations remain missing; no zero-fill.
- Analysis API now returns `valid_row_count` and provides a bounded endpoint to reopen a persisted run.
- Share change is shown in percentage points; relative change is omitted when the first-period value is zero.
- Decimal strings from the deterministic API are parsed for KPI and heatmap display without changing stored values.

## Verification

- Frontend component tests: 4 passed.
- Frontend production build: passed; Vite reports a 734.59 kB main JS chunk warning.
- Frontend lint: exit 0 with existing warnings in button/badge exports and other pre-existing pages.
- Python analysis engine/service/planner and web API tests: 24 passed, 2 subtests passed.
- `git diff --check`: passed.

## Limitation

The isolated React fixture displays the pre-integration training-page workflow. The plan’s autonomous API parity and autonomous status presentation are handled in the subsequent panel integration task.
