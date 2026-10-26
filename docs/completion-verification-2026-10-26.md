# FinLabel completion verification — 2026-10-26

Integration branch: `codex/finlabel-autonomous-mvp`  
Panel implementation branch: `codex/finlabel-autonomous-panel` (commit `25d8783`)  
Full verification branch: `codex/finlabel-full-verification`

## Automated checks

- Python full suite: 128 passed, 17 subtests passed.
- React/Vitest suite: 10 passed.
- `npm run build`: passed; Vite warns that the 710.61 kB minified main chunk exceeds its 500 kB advisory threshold.
- `npm run lint`: exit 0. Five advisory warnings remain: two shared UI export warnings and three `set-state-in-effect` warnings in Training, Labeling, and Analysis pages.
- `python -m compileall -q src/finlabel` and `git diff --check`: passed.

## Browser QA

Direct route loads, refresh, and navigation were checked at 1440×900 and 390×844 for `/`, `/analysis`, `/monitor`, `/labeling`, `/training`, `/review`, and a saved analysis route. No document-level horizontal overflow was found. Exact-result tables use contained horizontal scrolling on narrow viewports. The training workflow has seven ordered, accessible stages and identifies its current state.

Screenshots are retained in the parent TCC workspace at `.scratch/finlabel-completion-2026-10-26/evidence/`; the route/resolution matrix is recorded in `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

## Local model smoke

Qwen2.5-0.5B-Instruct, revision `7ae557604adf67be50417f59c2c2f167def9a775`, generated 24 valid outputs from 24 synthetic held-out examples using Apple MPS in 12.099 seconds. Exact accuracy was 70.83% and macro-F1 0.7056. The output artifact and exact command are documented in `local-model-inference-2026-10-26.md`.

This validates the local inference path on synthetic examples only. It does not establish financial performance. The historical adapter was not promoted because it lacks current identity and calibration artifacts. No customer data was used and no training run was performed in this completion pass.

## Independent review

The reviewer found that the autonomy endpoint read the model event journal without revalidating it after registry initialization. The endpoint now uses `ModelRegistry.history()`, and a regression test mutates a valid journal event after initialization; the request fails closed. The reviewer confirmed the fix closes this finding.

`main` was not modified or merged.
