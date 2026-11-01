# FinLabel analytics dashboard redesign

**Date:** 2026-10-25  
**Status:** Proposed for approval  
**Scope:** First visual/product slice before continuing the broader autonomous MVP completion plan.

## Intent

Make the FinLabel panel easier to scan and more useful for exploring local financial or other tabular data. The user asked for a cleaner, more minimal panel, a heatmap, and useful analytical KPIs. The panel already uses React, TypeScript, Tailwind CSS, shadcn-style components, and Recharts; the analysis page currently has a large JSON editor and charts but no KPI summary or heatmap.

## Goals

- Reduce visual noise and make page hierarchy, navigation, and analysis status easier to understand.
- Add a generic category-by-period heatmap whose cells represent the metric selected in the analysis plan.
- Show compact KPIs derived only from deterministic analysis output and its explicit dimensions, filters, time range, and denominator.
- Keep the analysis useful for market-share questions while making no implicit assumption about the market, denominator, or financial domain.
- Keep detailed plan editing available without making a large JSON editor the primary interaction.
- Provide accessible values and a non-color-only alternative to the heatmap.

## Non-goals

- Do not define a universal financial KPI set or assume credit-specific data fields.
- Do not calculate correlation matrices in this slice; the user selected category × period.
- Do not add LLM-authored numbers, recommendations, or causal explanations.
- Do not change source data or send rows to an external service.

## Approaches

1. **Category × period heatmap (selected):** use one category dimension and the explicit time axis; cell intensity represents the selected deterministic metric. This directly supports trend and market-share exploration and works across financial tasks. It requires clear handling when the plan lacks those dimensions.
2. **Numeric correlation matrix:** compare numeric variables independent of a time axis. This could help data exploration but does not directly visualize market-share change and needs decisions about correlation method and missing values.
3. **Both heatmaps:** broadest capability, with more UI and statistical interpretation than the immediate request needs.

The user selected approach 1. Keep the implementation extensible so another visualization can be added later without changing current metric semantics.

## Proposed layout and behavior

- Use the existing React/shadcn-style stack and a restrained neutral palette with one green accent for active/healthy states.
- Keep global navigation compact and consistent across overview, analysis, monitoring, labeling, and training pages.
- Make the analysis form compact: source, question, and clear actions are prominent; keep the complete JSON plan editor available under an “Avançado” disclosure so existing power users retain control.
- After a successful run, show a row of context-aware KPI cards before the charts. Candidate cards are: valid records used, period range/count, leading category and its current value/share, and change for that category between the first and last available periods. For `share_of_total`, show percentage-point change; for other metrics, show the absolute change and percentage only when its denominator is nonzero and meaningful. Show a data-quality count when the engine reports invalid or missing values. Omit cards whose required fields cannot be derived.
- Render the heatmap only when the result has exactly one usable category dimension and an explicit time axis. X is period, Y is category, color encodes the returned metric, and each cell exposes the exact value, category, period, metric, filters, and denominator semantics. Missing cells remain visibly missing; they are not filled with zero.
- Preserve the existing trend/bar chart and exact-results table as alternate views. Keep the result metadata and denominator description visible near the chart.
- Add an accessible table/list view of the same heatmap cells so color is not the only carrier of information. Set a bounded cell count and provide a message when the result exceeds the display limit.
- Empty, loading, error, no-time-axis, no-category, missing-value, and zero-denominator states must be clear and must not display fabricated KPIs.
- Check desktop at 1440×900 and mobile at 390×844, including keyboard navigation, direct route load/refresh, and no horizontal overflow.

## KPI definitions

All displayed numbers come from the analysis result, not from a language model.

- **Registros usados:** `AnalysisResult.valid_row_count`; call it a count, not a coverage percentage, unless the backend also supplies a trustworthy source-row denominator.
- **Período:** first-to-last period and distinct bucket count from the explicit time axis.
- **Categoria líder:** category with the largest metric in the last period; show the exact metric value. For a share metric, format as a percentage.
- **Variação da líder:** compare that same category across the first and last periods. For share, display percentage-point difference; otherwise show absolute difference and show relative percent only if the first value is nonzero.
- **Qualidade:** number of invalid/missing values from `invalid_value_counts`, with a disclosure of the relevant fields/codes; do not relabel it as a quality score.

If the current result contract cannot calculate a card correctly, extend the deterministic backend result and add tests first, or omit that KPI. Never approximate a denominator from grouped output.

## Constraints

- CSV and SQLite remain read-only and all records stay local.
- Preserve the complete validated analysis plan and its declared share denominator.
- KPI formatting must preserve exact source calculations; display rounding must not alter persisted results.
- Heatmap supports the existing response size limits and does not introduce a remote chart dependency.
- Keep the seven-stage autonomous training diagram legible and accessible while applying the shared visual system.

## Acceptance criteria

1. Existing pages use a consistent, restrained visual system and remain responsive.
2. The analysis plan editor is compact by default and can still expose the full editable plan.
3. A result with a category dimension and time axis renders category × period cells with exact accessible values and metric/denominator context.
4. KPI cards are computed deterministically, correctly handle shares and zero baselines, and are omitted when the necessary evidence is absent.
5. Missing data and display limits are represented explicitly; no missing cell or KPI is silently converted to zero.
6. The same result remains readable without color, including in an accessible table/list.
7. Existing source privacy, API security, and analysis integrity behavior remains intact.
8. Visual QA passes at 1440×900 and 390×844, including all affected analysis and training views.

## Builder calls

- Use a custom CSS-grid/SVG heatmap with the current React stack rather than adding a charting dependency; it supports exact accessible cells and avoids loading external assets.
- Keep KPIs contextual to the selected plan, because the project is intended to be reusable beyond one credit dataset.
- Treat this as a first slice of the broader autonomous MVP panel plan; branch it separately, then integrate before the remaining implementation tasks.
