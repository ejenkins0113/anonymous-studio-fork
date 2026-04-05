# DataViz Nerd Agent Memory — Anonymous Studio v2

## Project Context
- Taipy-based dark-theme web app for PII anonymization compliance
- Plotly figures consumed via `<|chart|type=plotly|figure={var}|>` Taipy markup
- All chart state lives in `app.py` as module-level variables (Taipy shared state pattern)

## Design Tokens (from app.css :root)
- bg0: #17191D (page background)
- bg1: #1D2025 (panel background)
- bg2: #272D36 (card/input background)
- bdr: #323841, bdr2: #3D4652
- acc/blu: #6484C8 (primary accent, recently updated from #6F86B9)
- grn: #79A06F, red: #D06A64, amb: #C8A55B, pur: #C58A5A
- txt: #D7DBE3, txt2: #BCC3CF, mut: #9199A8

## Key Files
- `ui/theme.py` — CHART_LAYOUT, MONO_COLORWAY, DASH_STYLEKIT
- `app.py` — All figure generation callbacks (search for `go.Figure`)
- `pages/definitions.py` — Taipy markup strings with chart references
- `app.css` — CSS design tokens and panel styles

## Chart Inventory
1. **Pipeline Stage** (donut pie) — `dash_stage_figure` — lines 2024-2044
2. **PII Entity Bar** (horizontal, multi-color) — `dash_entity_chart_figure` — lines 2139-2158
3. **Entity Mix** (donut pie) — `dash_entity_mix_figure` — lines 2176-2206 (not rendered in markup)
4. **Geo Signal Map** (Scattermap) — `dash_map_figure` — lines 2289-2330
5. **Engine Perf Bar** (traffic-light colors) — `dash_perf_figure` — lines 2389-2414
6. **Pipeline Burndown** (line chart) — `pipeline_burndown_figure` — lines 1135-1163
7. **QT Entity Bar** (horizontal) — `qt_entity_figure` — lines 3190-3202
8. **Stats Entity Bar** (job results) — `stats_entity_chart_figure` — lines 4432-4444
9. **Telemetry Lifecycle Bar** — `telemetry_lifecycle_figure` — lines 1365-1373
10. **Telemetry Throughput Bar** — `telemetry_data_figure` — lines 1376-1388
11. **UI Demo Pareto** — `ui_demo_pareto_figure`
12. **UI Demo Treemap** — `ui_demo_treemap_figure` (uses "Blues" colorscale)
13. **UI Demo Conf Box** — `ui_demo_conf_box_figure`
14. **UI Demo Heatmap** — `ui_demo_heatmap_figure` (uses Viridis)
15. **UI Demo Timeline** — `ui_demo_timeline_figure`
16. **UI Demo Pipeline Dist** — `ui_demo_pipeline_figure`
17. **UI Demo Map** — `ui_demo_map_figure`
18. **What-If Compare** — `whatif_compare_figure`

## Colorway (MONO_COLORWAY order)
["#D06A64", "#C58A5A", "#C8A55B", "#9BAA66", "#79A06F", "#6F8FA3", "#6484C8"]
Warm-to-cool ramp. Good for categorical ordering by importance.

## Geo Map Design
- Uses `go.Scattermap` with carto-positron tiles
- Light parchment bg (#F9F4EF) intentionally contrasts with dark app theme
- Colorscale: #F4D8C8 -> colorway[0] -> colorway[1] (warm ramp)
- Bubble sizing: 10 + 28*(m/max) for dashboard, 8 + 24*(m/max) for ui_demo

## Key Patterns Confirmed
- `chart_layout = {**CHART_LAYOUT}` at module level — mutable copy used for all figs
- `mono_colorway = MONO_COLORWAY.copy()` — mutable copy for direct indexing
- Telemetry charts use hardcoded `#6F86B9` (old primary) — should update to `#6484C8`
- Treemap uses generic "Blues" colorscale — does not match app palette
- QT and stats entity bars use flat `mono_colorway[0]` (red) — all bars same color
- Burndown: Ideal line uses colorway[4] (green), Remaining uses colorway[0] (red)

## Improvements Made (session 1)
See `improvements.md` for full changelog.
