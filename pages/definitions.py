"""Taipy page markup definitions for Anonymous Studio."""

# ─── Dashboard ────────────────────────────────────────────────────────────────
DASH = """
<|part|class_name=pg pg-dashboard|

<|part|class_name=page-hd|
<|Dashboard|text|class_name=page-title|>
<|Live pipeline status, recent activity, and upcoming compliance reviews|text|class_name=page-sub|hover_text=Live pipeline status, recent activity, and upcoming compliance reviews|>
|>

<|part|class_name=nlp-banner|
<|Settings|button|on_action=on_store_settings_open|class_name=secondary plain|hover_text=Change store backend|>
<|Store|text|class_name=banner-label ml-auto|>
<|{store_status_label}|text|class_name=store-mode-pill|hover_text={store_status_hover}|>
|>

<|{store_settings_open}|dialog|title=Store Settings|width=640px|
<|{store_backend_sel}|selector|lov={store_backend_lov}|label=Backend|class_name=fullwidth|>
<|part|render={store_backend_sel=="mongo"}|
<|{store_mongo_uri}|input|label=MongoDB URI|class_name=fullwidth|hover_text=e.g. mongodb://localhost:27017/anon_studio or mongodb+srv://user:pass@cluster/db|>
|>
<|part|render={store_backend_sel=="duckdb"}|
<|{store_duckdb_path}|input|label=DuckDB file path|class_name=fullwidth|hover_text=e.g. /tmp/anon_studio.duckdb for local persistent single-node storage.|>
|>
<|part|render={store_settings_msg!=""}|
<|{store_settings_msg}|text|class_name=inline-hint|>
|>
<|layout|columns=1 1|gap=8px|
<|Apply|button|on_action=on_store_apply|>
<|Cancel|button|on_action=on_store_settings_close|class_name=secondary|>
|>
|>

<|part|class_name=dash-toolbar|
<|layout|columns=1 2 2 4 3|gap=8px|
<|Refresh|button|on_action=on_refresh_dashboard|class_name=secondary|>
<|Generate Demo Session|button|on_action=on_dash_seed_demo|class_name=secondary|>
<|{dash_report_mode}|selector|lov={dash_report_mode_lov}|dropdown=True|label=Mode|on_change=on_dash_filters_change|class_name=fullwidth dash-filter|>
<|{dash_time_window}|selector|lov={dash_time_window_lov}|dropdown=True|label=Window|on_change=on_dash_filters_change|class_name=fullwidth dash-filter dash-window|>
<|part|
|>
|>
|>

<|Overview|text|class_name=sh sh-top dash-section-title|>
<|part|class_name=dash-ticker-wrap|
<|part|class_name=dash-ticker-item dash-ticker-blue|
<|{dash_jobs_total}|text|class_name=dash-ticker-value|>
<|Jobs Submitted|text|class_name=dash-ticker-label|>
|>
<|part|class_name=dash-ticker-item dash-ticker-purple|
<|{dash_jobs_running}|text|class_name=dash-ticker-value|>
<|Running|text|class_name=dash-ticker-label|>
|>
<|part|class_name=dash-ticker-item dash-ticker-green|
<|{dash_jobs_done}|text|class_name=dash-ticker-value|>
<|Completed|text|class_name=dash-ticker-label|>
|>
<|part|class_name=dash-ticker-item dash-ticker-red|
<|{dash_jobs_failed}|text|class_name=dash-ticker-value|>
<|Failed|text|class_name=dash-ticker-label|>
|>
<|part|class_name=dash-ticker-item dash-ticker-yellow|
<|{dash_cards_total}|text|class_name=dash-ticker-value|>
<|Pipeline Cards|text|class_name=dash-ticker-label|>
|>
<|part|class_name=dash-ticker-item dash-ticker-green|
<|{dash_cards_attested}|text|class_name=dash-ticker-value|>
<|Attested|text|class_name=dash-ticker-label|>
|>
|>

<|{"*Start by analyzing text, creating pipeline cards, or scheduling reviews — data will appear here.*"}|text|mode=md|render={not (dash_stage_chart_visible or dash_entity_chart_visible or dash_has_reviews)}|class_name=audit-stmt|>

<|part|render={dash_has_reviews}|class_name=dash-upcoming|
<|Upcoming Reviews|text|class_name=sh dash-section-title|>
<|{dash_upcoming_md}|text|mode=md|class_name=hi-box dash-upcoming-box|>
|>

<|part|render={dash_stage_chart_visible or dash_entity_chart_visible}|class_name=dash-reports|
<|Overview Reports|text|class_name=sh dash-section-title|>
<|layout|columns=1 1|gap=24px|
<|part|render={dash_stage_chart_visible}|class_name=settings-panel dash-panel|
<|Pipeline Health|text|class_name=sh sh-top|>
<|layout|columns=1 1 1|gap=10px|
<|{dash_completion_pct}|metric|title=Completion %|delta={dash_completion_pct_delta}|delta_color=normal|format=%.0f|type=linear|min=0|max=100|>
<|{dash_inflight_cards}|metric|title=In-Flight Cards|delta={dash_inflight_cards_delta}|delta_color=normal|format=%d|>
<|{dash_backlog_cards}|metric|title=Backlog|delta={dash_backlog_cards_delta}|delta_color=inversed|format=%d|>
|>
<|{dash_completion_pct}|progress|linear=True|>
|>
<|part|render={dash_entity_chart_visible}|class_name=settings-panel dash-panel entity-mix-panel|
<|PII Entity Mix|text|class_name=sh sh-top|>
<|{dash_entity_report_md}|text|mode=md|class_name=audit-stmt entity-mix-summary|>
<|layout|columns=1 1|gap=12px|
<|{dash_entity_dominance_pct}|metric|title=Dominant Share %|format=%.1f|type=none|>
<|{dash_kpi_entities_total}|metric|title=Total Detections|format=%d|type=none|>
|>
<|{dash_entity_mix_chart}|chart|type=plotly|figure={dash_entity_mix_figure}|height=280px|>
|>
|>
|>

<|part|

<|part|render={dash_map_visible}|class_name=settings-panel dash-panel geo-map-panel|
<|Geo Signal Map|text|class_name=sh sh-top|>
<|{dash_map_md}|text|mode=md|class_name=audit-stmt geo-map-summary|>
<|{dash_map_chart}|chart|type=plotly|figure={dash_map_figure}|height=360px|>
|>
<|part|render={not dash_map_visible}|class_name=panel widget-empty|
<|Geo Signal Map|text|class_name=sh sh-top|>
<|No location mentions yet.|text|class_name=widget-empty-title|>
<|Analyze location-rich text to light up the map.|text|class_name=widget-empty-sub|>
<|part|class_name=widget-empty-actions|
<|Generate Demo Session|button|on_action=on_dash_seed_demo|>
|>
|>

<|layout|columns=1 1|gap=24px|
<|part|render={dash_stage_chart_visible}|class_name=panel dash-panel|
<|Pipeline Stage Distribution|text|class_name=sh|>
<|{dash_stage_chart}|chart|type=plotly|figure={dash_stage_figure}|height=320px|>
|>
<|part|render={dash_entity_chart_visible}|class_name=panel dash-panel|
<|Top PII Entity Types|text|class_name=sh|>
<|All sessions|text|class_name=inline-hint|>
<|{dash_entity_chart}|chart|type=plotly|figure={dash_entity_chart_figure}|height=400px|>
|>
<|part|render={not dash_entity_chart_visible}|class_name=panel widget-empty|
<|Top PII Entity Types|text|class_name=sh sh-top|>
<|No saved PII sessions yet.|text|class_name=widget-empty-title|>
<|Run one demo session to populate this chart instantly.|text|class_name=widget-empty-sub|>
<|part|class_name=widget-empty-actions|
<|Generate Demo Session|button|on_action=on_dash_seed_demo|>
<|Go to Analyze|button|on_action=on_dash_go_analyze|class_name=secondary|>
|>
|>
|>

<|part|render={pipeline_burndown_visible}|class_name=settings-panel dash-panel|
<|Pipeline Burndown|text|class_name=sh sh-top|>
<|{pipeline_burndown_md}|text|mode=md|class_name=audit-stmt|>
<|{pipeline_burndown}|chart|type=plotly|figure={pipeline_burndown_figure}|height=300px|>
|>
<|part|render={not pipeline_burndown_visible}|class_name=panel widget-empty|
<|Pipeline Burndown|text|class_name=sh sh-top|>
<|No pipeline cards yet.|text|class_name=widget-empty-title|>
<|Create cards in the Pipeline to see remaining open work over time.|text|class_name=widget-empty-sub|>
|>

<|part|render={dash_perf_visible}|class_name=settings-panel dash-panel|
<|Engine Performance|text|class_name=sh sh-top|>
<|layout|columns=1 1|gap=16px|
<|{dash_perf_avg_ms}|metric|title=Avg Latency|format=%.0f ms|delta={dash_perf_delta_ms}|delta_color=invert|type=none|>
<|{dash_perf_count}|metric|title=Sessions Timed|format=%d|type=none|>
|>
<|{perf_telemetry_table}|chart|id=dash_perf_bar|type=plotly|figure={dash_perf_figure}|height=260px|>
|>
<|part|render={not dash_perf_visible}|class_name=panel widget-empty|
<|Engine Performance|text|class_name=sh sh-top|>
<|No sessions timed yet.|text|class_name=widget-empty-title|>
<|Run Analyze Text or submit a batch job to see engine latency metrics.|text|class_name=widget-empty-sub|>
|>

<|part|render={job_file_art!=""}|class_name=settings-panel dash-panel|
<|Last Upload Fingerprint|text|class_name=sh sh-top|>
<|{job_file_name}|text|class_name=inline-hint|>
<|{job_file_art}|text|mode=pre|class_name=file-hash-art|>
<|{"SHA-256  " + job_file_hash}|text|class_name=file-hash-display|>
|>

|>

|>
"""

# ─── Batch Jobs Page ──────────────────────────────────────────────────────────
JOBS = """
<|part|class_name=pg pg-jobs|

<|part|class_name=page-hd|
<|Batch Jobs|text|class_name=page-title|>
<|Upload CSV or Excel files for bulk PII anonymization in the background|text|class_name=page-sub|hover_text=Accepted formats: .csv, .xlsx, .xls up to 50 MB. Configure method and threshold, then run and monitor progress here.|>
|>

<|layout|columns=1 1 10|gap=8px|
<|Run Job|button|on_action=on_submit_job|>
<|Refresh|button|on_action=on_poll_progress|class_name=secondary|>
<|part|>
|>

<|layout|columns=1 1 1 1|gap=12px|
<|{job_kpi_total}|metric|title=Total Jobs|format=%d|type=none|>
<|{job_kpi_running}|metric|title=Running|format=%d|delta_color=normal|type=none|>
<|{job_kpi_success_pct}|indicator|value={job_kpi_success_pct}|min=0|max=100|title=Success Rate|format=%.0f%%|>
<|{job_kpi_entities}|metric|title=Entities Found|format=%s|type=none|>
|>

<|part|class_name=nlp-banner status-ribbon|
<|NLP|text|class_name=banner-label|>
<|{spacy_ok}|status|>
<|{spacy_status_label}|text|class_name=store-mode-pill|hover_text={spacy_status_hover}|>
<|Store|text|class_name=banner-label|>
<|{store_ok}|status|>
<|{store_status_label}|text|class_name=store-mode-pill|hover_text={store_status_hover}|>
<|Raw DataNode|text|class_name=banner-label|>
<|{raw_input_ok}|status|>
<|{raw_input_status_label}|text|class_name=store-mode-pill|hover_text={raw_input_status_hover}|>
<|Settings|button|on_action=on_store_settings_open|class_name=secondary plain ml-auto|hover_text=Change store backend|>
|>

<|{store_settings_open}|dialog|title=Store Settings|width=640px|
<|{store_backend_sel}|selector|lov={store_backend_lov}|label=Backend|class_name=fullwidth|>
<|part|render={store_backend_sel=="mongo"}|
<|{store_mongo_uri}|input|label=MongoDB URI|class_name=fullwidth|hover_text=e.g. mongodb://localhost:27017/anon_studio or mongodb+srv://user:pass@cluster/db|>
|>
<|part|render={store_backend_sel=="duckdb"}|
<|{store_duckdb_path}|input|label=DuckDB file path|class_name=fullwidth|hover_text=e.g. /tmp/anon_studio.duckdb for local persistent single-node storage.|>
|>
<|part|render={store_settings_msg!=""}|
<|{store_settings_msg}|text|class_name=inline-hint|>
|>
<|layout|columns=1 1|gap=8px|
<|Apply|button|on_action=on_store_apply|>
<|Cancel|button|on_action=on_store_settings_close|class_name=secondary|>
|>
|>

<|layout|columns=2 1|gap=24px|
<|part|
<|part|class_name=panel|
<|Upload & Basic Config|text|class_name=sh sh-top|>
<|{job_file_content}|file_selector|label=Choose CSV or Excel file (max 50 MB)|on_action=on_file_upload|extensions=.csv,.xlsx,.xls|hover_text=Upload one dataset per run. The file is parsed in memory and queued for anonymization.|>
<|part|render={job_file_name!=""}|class_name=file-ready|
<|{job_file_name}|text|>
<|{"SHA-256  " + job_file_hash}|text|class_name=file-hash-display|hover_text=SHA-256 of original uploaded file — run 'sha256sum filename' locally to verify the file was not altered|>
|>
<|part|render={job_file_art!=""}|
<|{job_file_art}|text|mode=pre|class_name=file-hash-art|>
|>
<|layout|columns=1 1|gap=12px|
<|{job_operator}|selector|lov={job_operator_list}|dropdown=True|label=Anonymization method|class_name=job-method-field|hover_text=replace: swap with [ENTITY]. redact: remove text. mask: obfuscate. hash: SHA-256 hash.|>
<|part|class_name=job-threshold-field|
<|Min. confidence|text|class_name=slider-label|>
<|{job_threshold}|slider|min=0.1|max=1.0|step=0.05|hover_text=Higher threshold is stricter and reduces false positives but may miss weak signals.|>
|>
|>
<|{job_threshold}|text|format=Threshold: %.2f|>
<|Run Job|button|on_action=on_submit_job|>
<|Advanced Options|button|on_action=on_job_adv_open|class_name=secondary|>
|>

<|{job_adv_open}|pane|anchor=right|
<|part|class_name=panel|
<|Advanced Options|text|class_name=sh sh-top|>
<|layout|columns=1 1|gap=12px|
<|part|
<|Chunk size (rows)|text|class_name=slider-label|>
<|{job_chunk_size}|slider|min=100|max=5000|step=100|hover_text=Higher chunk sizes can improve throughput but use more memory.|>
|>
<|{job_card_id}|input|label=Link to Pipeline Card ID (optional)|class_name=fullwidth|hover_text=If set, the linked card is moved to In Progress during execution.|>
|>
<|{job_chunk_size}|text|format=Chunk size: %d rows|>
<|{job_spacy_model}|selector|lov={job_spacy_model_lov}|dropdown=True|label=NLP model for this job|hover_text=Select model per batch run (auto, blank, or installed en_core_* model).|>
<|{job_entities}|selector|lov={job_all_entities}|multiple=True|dropdown=True|filter=True|label=Entity types to detect|hover_text=Narrowing scope improves speed and can reduce noisy detections.|>
<|Large Dataset (Dask)|text|class_name=sh sh-top|>
<|{dask_status}|text|class_name=inline-hint|>
<|{job_compute_backend}|selector|lov={job_compute_backend_lov}|label=Compute backend|hover_text=auto: use Dask when rows exceed threshold. pandas: always chunk with pandas. dask: force Dask partitions (requires Dask installed).|>
<|Dask auto-switch threshold (rows)|text|class_name=slider-label|>
<|{job_dask_min_rows}|slider|min=10000|max=1000000|step=10000|hover_text=Dask kicks in automatically above this row count when backend is set to auto.|>
<|{job_dask_min_rows}|text|format=Switch at %,.0f rows|>
<|Raw Input DataNode (MongoDB)|text|class_name=sh sh-top|>
<|{raw_input_status_label}|text|class_name=inline-hint|hover_text={raw_input_status_hover}|>
<|Backend changes require a restart (set ANON_RAW_INPUT_BACKEND env var).|text|class_name=inline-hint|>
<|MongoDB write batch (docs/write)|text|class_name=slider-label|>
<|{job_mongo_write_batch}|slider|min=500|max=50000|step=500|hover_text=Number of documents written per batch when raw_input DataNode uses MongoDB backend. Lower values reduce memory pressure on large uploads.|>
<|{job_mongo_write_batch}|text|format=%,.0f docs/batch|>
<|Close Advanced|button|on_action=on_job_adv_close|class_name=secondary|>
|>
|>
|>

<|part|class_name=settings-panel|
<|Active Run Monitor|text|class_name=sh sh-top|>
<|layout|columns=1 1 1 1|gap=10px|
<|{job_run_health}|metric|title=Run Health|format=%s|type=none|>
<|{active_job_id if active_job_id else "No job"}|metric|title=Active Job|format=%s|type=none|>
<|{job_active_submission_id if job_active_submission_id else "—"}|metric|title=Active Submission|format=%s|type=none|>
<|{job_submission_status}|metric|title=Submission Status|format=%s|type=none|>
|>
<|part|render={job_run_health!="Idle"}|
<|{job_stage_text}|text|class_name=audit-stmt|>
|>
<|part|render={job_run_health!="Idle"}|
<|{job_eta_text}|text|class_name=inline-hint|>
<|{job_processed_text}|text|class_name=inline-hint|>
|>
|>
|>

<|Operational Views|text|class_name=sh|>
<|{job_view_tab}|selector|lov={job_view_tab_lov}|dropdown=True|label=View|>

<|part|render={job_view_tab=="Results"}|class_name=panel|
<|Results Summary|text|class_name=sh sh-top|>
<|{job_quality_md}|text|mode=md|>
<|part|render={download_ready}|
<|{download_rows}|text|> rows | <|{download_cols}|text|> columns
|>
<|Download CSV|button|on_action=on_download|render={download_ready}|>
<|part|render={download_ready}|
<|layout|columns=1 1|gap=16px|
<|{stats_entity_rows}|table|columns=Entity Type;Count|page_size=8|show_all=False|>
<|{stats_entity_rows}|chart|type=plotly|figure={stats_entity_chart_figure}|height=260px|>
|>
<|Preview (first 50 rows)|text|class_name=sh|>
<|{preview_data}|table|page_size=8|show_all=False|>
|>
<|part|render={not download_ready}|
<|Run a job to generate anonymized output and quality metrics.|text|class_name=inline-hint|>
|>
|>

<|part|render={job_view_tab=="Job History"}|class_name=panel|
<|Job History|text|class_name=sh sh-top|>
<|layout|columns=1 1 10|gap=8px|
<|Cancel Selected|button|on_action=on_job_cancel|class_name=secondary|>
<|Remove Selected|button|on_action=on_job_remove|class_name=secondary|>
<|part|>
|>
<|Select a row first. Cancel works for pending/running jobs; remove works for finished jobs.|text|class_name=inline-hint|>
<|{job_table_data}|table|columns=Job ID;Title;Progress;Status;Entities;Duration;Message|cell_class_name[Status]=status_cell_class|page_size=10|show_all=False|on_action=on_select_job|>
|>

<|part|render={job_view_tab=="Data Nodes"}|class_name=panel|
<|Taipy Data Node Explorer|text|class_name=sh sh-top|>
<|**How to use:** Each pipeline job creates four data nodes — *raw_input* (uploaded data), *job_config* (settings), *anon_output* (anonymized result), and *job_stats* (entity counts and timing). Select any node below to inspect its contents, validity period, and edit history. Toggle **Pinned only** to show bookmarked nodes.|text|mode=md|class_name=inline-hint|>
<|{selected_data_node}|data_node_selector|>
<|part|render={selected_data_node is not None}|
<|{selected_data_node}|data_node|>
|>
<|part|render={selected_data_node is None}|
<|Select a data node above to inspect its contents.|text|class_name=inline-hint|>
|>
|>

<|part|render={job_view_tab=="Errors / Audit"}|class_name=panel|
<|Errors & Audit|text|class_name=sh sh-top|>
<|{job_errors_data}|table|columns=Time;Source;Details;Severity|cell_class_name[Severity]=severity_cell_class|page_size=10|show_all=False|>
<|Go to Audit Log for full event history and filtering.|text|class_name=inline-hint|>
<|Task Orchestration Interface|text|class_name=sh|>
<|{orchestration_scenario}|scenario_selector|>
<|part|render={orchestration_scenario is not None}|
<|{orchestration_scenario}|scenario|on_submission_change=on_submission_status_change|>
<|Set as Primary|button|on_action=on_promote_primary|class_name=secondary|hover_text=Mark this scenario as the primary (canonical) run for its weekly cycle. A star badge appears in the selector.|>
|>
<|{orchestration_job}|job_selector|>

<|What-if Analysis|text|class_name=sh|>
<|{whatif_scenarios_sel}|selector|lov={whatif_scenarios_lov}|multiple=True|dropdown=True|filter=True|label=Scenarios to compare|>
<|Compare Scenarios|button|on_action=on_whatif_compare|class_name=secondary|>
<|{whatif_compare_md}|text|mode=md|class_name=inline-hint|>
<|{comparator_scenarios}|scenario_comparator|>
<|part|render={whatif_compare_has_data}|
<|layout|columns=1 1|gap=16px|
<|{whatif_compare_data}|table|columns=Scenario;Processed Rows;Entities;Entities / Row|show_all=False|page_size=6|>
<|{whatif_compare_chart}|chart|type=plotly|figure={whatif_compare_figure}|height=240px|>
|>
|>

<|Submission Monitor|text|class_name=sh|>
<|{submission_table}|table|columns=Submission;Entity;Status;Jobs;Created|cell_class_name[Status]=status_cell_class|show_all=False|page_size=8|>
<|Cycle Monitor|text|class_name=sh|>
<|{cycle_table}|table|columns=Cycle;Frequency;Start;End;Scenarios|show_all=False|page_size=8|>
|>

|>
"""

# ─── Pipeline ─────────────────────────────────────────────────────────────────
PIPELINE = """
<|part|class_name=pg pg-pipeline|

<|part|class_name=page-hd|
<|Pipeline|text|class_name=page-title|>
<|Track de-identification tasks through the compliance workflow|text|class_name=page-sub|>
|>

<|part|class_name=toolbar-panel|
<|Board Actions|text|class_name=sh sh-top|>
<|part|class_name=pipeline-actions|
<|+ New Card|button|on_action=on_card_new|>
<|Edit Card|button|on_action=on_card_edit|class_name=secondary|>
<|Delete|button|on_action=on_card_delete|class_name=danger|>
|>
<|part|class_name=pipeline-nav-actions|
<|← Back|button|on_action=on_card_back|class_name=secondary|>
<|Forward →|button|on_action=on_card_forward|class_name=secondary|>
<|Attest|button|on_action=on_attest_open|class_name=secondary|>
<|View History|button|on_action=on_card_history|class_name=secondary|>
|>
<|Selection flow: click or check a row in any board column to set the active card.|text|mode=md|class_name=inline-hint|>
|>

<|part|class_name=pipeline-front-info|
<|{pipeline_front_md}|text|mode=md|>
|>

<|part|class_name=sel-card-info|
<|{pipeline_selected_md}|text|mode=md|>
|>

<|Board|text|class_name=sh|>

<|part|class_name=pipeline-board-wrap|
<|layout|columns=1 1 1 1|gap=14px|
<|part|class_name=kc kc-gray|
<|part|class_name=kh kh-gray|
Backlog <|{kanban_backlog_len}|text|class_name=kh-cnt|>
|>
<|{kanban_backlog}|table|selected={backlog_sel}|columns=Select;Title;Priority;Job|cell_class_name[Priority]=priority_cell_class|cell_class_name[Job]=status_cell_class|use_checkbox=True|show_all=True|on_action=on_card_pick|>
|>
<|part|class_name=kc kc-purple|
<|part|class_name=kh kh-purple|
In Progress <|{kanban_in_progress_len}|text|class_name=kh-cnt|>
|>
<|{kanban_in_progress}|table|selected={in_progress_sel}|columns=Select;Title;Priority;Job|cell_class_name[Priority]=priority_cell_class|cell_class_name[Job]=status_cell_class|use_checkbox=True|show_all=True|on_action=on_card_pick|>
|>
<|part|class_name=kc kc-yellow|
<|part|class_name=kh kh-yellow|
Review <|{kanban_review_len}|text|class_name=kh-cnt|>
|>
<|{kanban_review}|table|selected={review_sel}|columns=Select;Title;Priority;Job|cell_class_name[Priority]=priority_cell_class|cell_class_name[Job]=status_cell_class|use_checkbox=True|show_all=True|on_action=on_card_pick|>
|>
<|part|class_name=kc kc-green|
<|part|class_name=kh kh-green|
Done <|{kanban_done_len}|text|class_name=kh-cnt|>
|>
<|{kanban_done}|table|selected={done_sel}|columns=Select;Title;Priority;Job|cell_class_name[Priority]=priority_cell_class|cell_class_name[Job]=status_cell_class|use_checkbox=True|show_all=True|on_action=on_card_pick|>
|>
|>
|>

<|Burndown|text|class_name=sh|>
<|part|class_name=panel|
<|{pipeline_burndown_md}|text|mode=md|class_name=inline-hint|>
<|part|render={pipeline_burndown_visible}|
<|{pipeline_burndown}|chart|type=plotly|figure={pipeline_burndown_figure}|height=280px|>
|>
<|part|render={not pipeline_burndown_visible}|
<|No burndown data yet. Create and move cards through stages to populate this chart.|text|class_name=inline-hint|>
|>
|>

<|{card_form_open}|dialog|title=Pipeline Card|on_action=on_card_cancel|width=600px|
<|{card_title_f}|input|label=Title *|class_name=fullwidth|>
<|{card_desc_f}|input|multiline=True|lines_shown=3|label=Description|class_name=fullwidth|>
<|layout|columns=1 1|gap=12px|
<|{card_status_f}|selector|lov={card_status_opts}|dropdown=True|label=Status|>
<|{card_priority_f}|selector|lov={card_priority_opts}|dropdown=True|label=Priority|>
|>
<|{card_assign_f}|input|label=Assignee|class_name=fullwidth|>
<|{card_labels_f}|input|label=Labels (comma-separated)|class_name=fullwidth|>
<|{card_session_f}|selector|lov={card_session_opts}|dropdown=True|label=Link Session|class_name=fullwidth|>
<|{card_attest_f}|input|multiline=True|lines_shown=2|label=Attestation Notes|class_name=fullwidth|>
<|layout|columns=1 1|gap=8px|
<|Save|button|on_action=on_card_save|>
<|Cancel|button|on_action=on_card_cancel|class_name=secondary|>
|>
|>

<|{attest_open}|dialog|title=Compliance Attestation|on_action=on_attest_cancel|width=480px|
<|This statement is permanently logged to the immutable audit trail.|text|class_name=audit-stmt|>
<|{attest_by}|input|label=Attested By *|class_name=fullwidth|>
<|{attest_note}|input|multiline=True|lines_shown=3|label=Statement|class_name=fullwidth|>
<|layout|columns=1 1|gap=8px|
<|Confirm|button|on_action=on_attest_confirm|>
<|Cancel|button|on_action=on_attest_cancel|class_name=secondary|>
|>
|>

<|{card_audit_open}|dialog|title=Card Audit History|on_action=on_card_history_close|width=700px|
<|{card_audit_data}|table|columns=Time;Action;Actor;Details|show_all=False|page_size=12|>
<|Close|button|on_action=on_card_history_close|class_name=secondary|>
|>

<|All Cards|text|class_name=sh|>
<|part|class_name=panel|
<|{pipeline_all}|table|selected={pipeline_all_sel}|columns=Title;Priority;Assignee;Job;Labels;Attested;Updated|cell_class_name[Priority]=priority_cell_class|cell_class_name[Job]=status_cell_class|show_all=False|page_size=10|on_action=on_card_pick|>
|>

|>
"""

# ─── Schedule ─────────────────────────────────────────────────────────────────
SCHEDULE = """
<|part|class_name=pg pg-schedule|

<|part|class_name=page-hd|
<|Reviews|text|class_name=page-title|>
<|Schedule and track compliance review appointments linked to pipeline cards|text|class_name=page-sub|>
|>

<|part|class_name=schedule-actions|
<|+ New Review|button|on_action=on_appt_new|>
<|Edit|button|on_action=on_appt_edit|class_name=secondary|>
<|Delete|button|on_action=on_appt_delete|class_name=danger|>
|>

<|part|class_name=schedule-status-legend|
<|Scheduled|text|class_name=schedule-chip chip-scheduled|>
<|Completed|text|class_name=schedule-chip chip-completed|>
<|Cancelled|text|class_name=schedule-chip chip-cancelled|>
|>

<|layout|columns=2 1|gap=24px|
<|part|class_name=panel|
<|All Appointments|text|class_name=panel-hd|>
<|{appt_table}|table|columns=Title;Date / Time;Duration;Attendees;Linked Card;Status|cell_class_name[Status]=status_cell_class|show_all=False|page_size=10|on_action=on_appt_select|>
|>
<|part|class_name=panel|
<|Upcoming|text|class_name=panel-hd|>
<|{upcoming_table}|table|columns=Title;Date;Time|show_all=False|page_size=6|>
|>
|>

<|{appt_form_open}|dialog|title=Schedule Review Appointment|on_action=on_appt_cancel|width=580px|
<|{appt_title_f}|input|label=Title *|class_name=fullwidth|>
<|{appt_desc_f}|input|multiline=True|lines_shown=2|label=Description|class_name=fullwidth|>
<|layout|columns=1 1|gap=12px|
<|{appt_date_f}|date|label=Date|>
<|{appt_time_f}|input|label=Time (HH:MM, 24hr)|>
|>
<|layout|columns=1 1|gap=12px|
<|{appt_dur_f}|number|label=Duration (min)|>
<|{appt_status_f}|selector|lov={appt_status_opts}|dropdown=True|label=Status|>
|>
<|{appt_att_f}|input|label=Attendees (comma-separated)|class_name=fullwidth|>
<|{appt_card_f}|input|label=Pipeline Card ID (optional)|class_name=fullwidth|>
<|layout|columns=1 1|gap=8px|
<|Save|button|on_action=on_appt_save|>
<|Cancel|button|on_action=on_appt_cancel|class_name=secondary|>
|>
|>

<|System Requirements|expandable|expanded={schedule_sysreq_expanded}|class_name=panel schedule-sysreq-panel|
<|Required for large dataset processing (> 250 k rows). Install with: pip install "dask[dataframe]>=2024.8.0"|text|class_name=inline-hint|>
<|layout|columns=1 1 1|gap=12px|
<|part|class_name=health-kpi|
<|{dask_status}|text|class_name=health-kpi-v|style=font-size:13px|>
<|Large Dataset Engine|text|class_name=health-kpi-l|>
|>
<|part|class_name=health-kpi|
<|{spacy_status_label}|text|class_name=health-kpi-v|style=font-size:13px|hover_text={spacy_status_hover}|>
<|NLP Engine|text|class_name=health-kpi-l|>
|>
<|part|class_name=health-kpi|
<|{store_status_label}|text|class_name=health-kpi-v|style=font-size:13px|hover_text={store_status_hover}|>
<|Store Backend|text|class_name=health-kpi-l|>
|>
|>
|>

|>
"""

# ─── Audit ────────────────────────────────────────────────────────────────────
AUDIT = """
<|part|class_name=pg|

<|part|class_name=page-hd|
<|Audit Log|text|class_name=page-title|>
<|Immutable record of every action taken in the system|text|class_name=page-sub|>
|>

<|Filter|text|class_name=sh sh-top|>
<|layout|columns=3 1 1 1|gap=12px|
<|{audit_search}|input|label=Search action / details|class_name=fullwidth|>
<|{audit_sev}|selector|lov={audit_sev_opts}|dropdown=True|label=Severity|>
<|Apply|button|on_action=on_audit_filter|>
<|Clear|button|on_action=on_audit_clear|class_name=secondary|>
|>

<|{audit_table}|table|columns=Time;Actor;Action;Resource;Details;Severity|cell_class_name[Severity]=severity_cell_class|show_all=False|page_size=20|>

|>
"""

# ─── Analyze Text ─────────────────────────────────────────────────────────────
QT = """
<|part|class_name=pg|

<|part|class_name=page-hd|
<|Analyze Text|text|class_name=page-title|>
<|Paste or type any text to detect and redact personally identifiable information|text|class_name=page-sub|>
|>

<|part|class_name=nlp-banner|
NLP Engine: <|{spacy_status}|text|>
|>

<|part|class_name=panel|
<|1. Input and Run|text|class_name=sh sh-top|>
<|{qt_input}|input|multiline=True|lines_shown=10|label=Input text|class_name=fullwidth|>

<|part|class_name=qt-actions|
<|Detect PII|button|on_action=on_qt_analyze|>
<|Anonymize|button|on_action=on_qt_anonymize|>
<|Settings|button|on_action=on_qt_settings_open|class_name=secondary|>
<|Load Sample|button|on_action=on_qt_load_sample|class_name=secondary|>
<|Save Session|button|on_action=on_qt_save_session|class_name=secondary|>
<|Clear|button|on_action=on_qt_clear|class_name=secondary|>
|>

<|part|class_name=result-strip|
<|layout|columns=1 1 1 1|gap=10px|
<|part|class_name=health-kpi qt-kpi qt-kpi-gray|
<|{qt_kpi_total_entities_ticker}|text|class_name=health-kpi-v qt-kpi-v qt-kpi-gray-v|>
<|Entities Detected|text|class_name=health-kpi-l|>
|>
<|part|class_name=health-kpi qt-kpi qt-kpi-purple|
<|{qt_kpi_dominant_band_ticker}|text|class_name=health-kpi-v qt-kpi-v qt-kpi-purple-v|>
<|Dominant Band|text|class_name=health-kpi-l|>
|>
<|part|class_name=health-kpi qt-kpi qt-kpi-yellow|
<|{qt_kpi_avg_confidence_ticker}|text|class_name=health-kpi-v qt-kpi-v qt-kpi-yellow-v|>
<|Avg Confidence|text|class_name=health-kpi-l|>
|>
<|part|class_name=health-kpi qt-kpi qt-kpi-green|
<|{qt_kpi_low_confidence_ticker}|text|class_name=health-kpi-v qt-kpi-v qt-kpi-green-v|>
<|Low Confidence|text|class_name=health-kpi-l|>
|>
|>
<|Summary|text|class_name=strip-label|>
<|{qt_summary}|text|mode=md|class_name=result-line|>
<|Confidence Profile|text|class_name=strip-label|>
<|{qt_confidence_md}|text|mode=md|class_name=result-line|>
<|Entity Mix|text|class_name=strip-label|>
<|{qt_entity_breakdown_md}|text|class_name=result-line|>
<|{qt_conf_bands_md}|text|class_name=result-line|>
|>
|>

<|2. Output|text|class_name=sh|>
<|layout|columns=1 1|gap=24px|
<|part|class_name=panel|
<|Detected PII|text|class_name=sh sh-top|>
<|{qt_highlight_md}|text|mode=md|class_name=hi-box|>
|>
<|part|class_name=panel|
<|Anonymized Output|text|class_name=sh sh-top|>
<|{qt_anonymized_raw}|text|mode=pre|class_name=anon-box|>
<|layout|columns=1 1 8|gap=8px|
<|Download TXT|button|on_action=on_qt_download_anonymized|class_name=secondary|render={qt_anonymized_raw!=""}|>
<|Download Entities CSV|button|on_action=on_qt_download_entities|class_name=secondary|render={qt_has_entities}|>
<|part|>
|>
|>
|>

<|part|class_name=panel entity-evidence-panel|
<|3. Entity Evidence|text|class_name=sh sh-top|>
<|{qt_entity_rows}|table|columns=Entity Type;Text;Confidence;Confidence Band;Span;Recognizer;Rationale|show_all=False|page_size=8|filter=True|sortable=True|>
<|{qt_entity_chart}|chart|type=plotly|figure={qt_entity_figure}|height=300px|render={qt_entity_chart_visible}|>
|>

<|Saved Sessions|text|class_name=sh|>
<|part|class_name=panel|
<|{qt_sessions_data}|table|columns=ID;Title;Operator;Entities;Created|show_all=False|page_size=6|filter=True|sortable=True|on_action=on_qt_session_select|>
<|Load Session|button|on_action=on_qt_load_session|class_name=secondary|render={qt_selected_session!=""}|>
|>

<|{qt_settings_open}|dialog|title=Detection Settings|on_action=on_qt_settings_close|width=720px|
<|{qt_ner_model_sel}|selector|lov={qt_ner_model_lov}|dropdown=True|label=NER model package|on_change=on_qt_ner_model_change|class_name=fullwidth|hover_text=Presidio-style model package presets. This build executes spaCy in-process and maps non-spaCy presets to spaCy auto mode.|>
<|part|render={qt_ner_model_sel=="Other"}|
<|{qt_ner_other_model}|input|label=Other model name|class_name=fullwidth|hover_text=Custom model identifier or path (e.g. local spaCy model).|>
|>
<|part|render={qt_ner_note!=""}|
<|{qt_ner_note}|text|class_name=inline-hint|>
|>
<|{qt_operator}|selector|lov={qt_operator_list}|dropdown=True|label=De-identification approach|class_name=fullwidth|hover_text=Presidio-style approaches: redact, replace, mask, hash, or synthesize.|>
<|Min. confidence|text|class_name=slider-label|>
<|{qt_threshold}|slider|min=0.1|max=1.0|step=0.05|>
<|{qt_threshold}|text|format=Threshold: %.2f|>
<|{qt_entities}|selector|lov={qt_all_entities}|multiple=True|dropdown=True|filter=True|label=Entity types to detect|class_name=fullwidth|>
<|{qt_allowlist_text}|input|label=Allowlist — words to never flag as PII (comma-separated)|class_name=fullwidth|hover_text=e.g. "John, Acme Corp" — these exact words will be excluded from PII detection even if the model flags them.|>
<|{qt_denylist_text}|input|label=Denylist — words to always flag as PII (comma-separated)|class_name=fullwidth|hover_text=e.g. "MyCompany, ProjectX" — these words will always be treated as PII regardless of model confidence.|>
<|part|render={qt_operator=="synthesize"}|
<|Synthetic Output (LLM/Faker)|text|class_name=sh sh-top|>
<|{qt_synth_provider}|selector|lov={qt_synth_provider_lov}|dropdown=True|label=Synthetic provider|class_name=fullwidth|hover_text=faker uses local deterministic synthesis; openai/azure_openai call an LLM and fall back to faker on failure.|>
<|{qt_synth_model}|input|label=Model name|class_name=fullwidth|hover_text=For Azure OpenAI, use deployment name if not set below.|>
<|part|render={qt_synth_provider=="azure_openai"}|
<|{qt_synth_deployment}|input|label=Azure deployment|class_name=fullwidth|>
<|{qt_synth_api_base}|input|label=Azure endpoint|class_name=fullwidth|>
<|{qt_synth_api_version}|input|label=API version|class_name=fullwidth|>
|>
<|part|render={qt_synth_provider=="openai"}|
<|{qt_synth_api_base}|input|label=OpenAI base URL (optional)|class_name=fullwidth|hover_text=Leave empty for the default OpenAI API endpoint.|>
|>
<|{qt_synth_api_key}|input|label=API key|password=True|class_name=fullwidth|>
<|layout|columns=1 1|gap=12px|
<|{qt_synth_temperature}|number|label=Temperature|min=0|max=2|step=0.1|>
<|{qt_synth_max_tokens}|number|label=Max tokens|min=128|max=4000|step=64|>
|>
<|part|render={qt_synth_note!=""}|
<|{qt_synth_note}|text|class_name=inline-hint|>
|>
|>
<|layout|columns=1 1|gap=8px|
<|Apply|button|on_action=on_qt_settings_close|>
<|Close|button|on_action=on_qt_settings_close|class_name=secondary|>
|>
|>

|>
"""

# ─── Plotly UI ────────────────────────────────────────────────────────────────
UI_DEMO = """
<|part|class_name=pg|

<|part|class_name=page-hd|
<|Plotly UI|text|class_name=page-title|>
<|Interactive showcase of major Plotly + Taipy chart options|text|class_name=page-sub|>
|>

<|part|class_name=panel|
<|Playground Controls|text|class_name=sh sh-top|>
<|layout|columns=1 1 1 1 1 1 1|gap=10px|
<|{ui_plot_type}|selector|lov={ui_plot_type_lov}|dropdown=True|label=Type|on_change=on_ui_demo_filters_change|>
<|{ui_plot_orientation}|selector|lov={ui_plot_orientation_lov}|dropdown=True|label=Orientation|render={ui_plot_show_orientation}|on_change=on_ui_demo_filters_change|>
<|{ui_plot_barmode}|selector|lov={ui_plot_barmode_lov}|dropdown=True|label=Bar Mode|render={ui_plot_show_barmode}|on_change=on_ui_demo_filters_change|>
<|{ui_plot_trace_mode}|selector|lov={ui_plot_trace_mode_lov}|dropdown=True|label=Trace Mode|render={ui_plot_show_trace_mode}|on_change=on_ui_demo_filters_change|>
<|{ui_plot_palette}|selector|lov={ui_plot_palette_lov}|dropdown=True|label=Palette|on_change=on_ui_demo_filters_change|>
<|{ui_plot_theme}|selector|lov={ui_plot_theme_lov}|dropdown=True|label=Theme|on_change=on_ui_demo_filters_change|>
<|{ui_plot_show_legend}|selector|lov={ui_plot_show_legend_lov}|dropdown=True|label=Legend|on_change=on_ui_demo_filters_change|>
|>
<|layout|columns=1 1 6|gap=10px|
<|{ui_demo_mode}|selector|lov={ui_demo_mode_lov}|dropdown=True|label=Catalog Mode|hover_text=Filter which catalog charts render: All, Entities only, Confidence only, or Operations only.|on_change=on_ui_demo_filters_change|>
<|{ui_demo_top_n}|number|label=Top N|min=3|max=25|hover_text=Number of top entity types shown in catalog charts.|action_on_blur=True|on_change=on_ui_demo_filters_change|>
<|part|>
|>
<|layout|columns=1 1 1 7|gap=10px|
<|Refresh|button|on_action=on_ui_demo_refresh|>
<|Generate Demo Session|button|on_action=on_dash_seed_demo|class_name=secondary|>
<|part|>
|>
<|{ui_demo_summary_md}|text|mode=md|class_name=inline-hint|>
<|{ui_demo_last_refresh}|text|class_name=inline-hint|render={ui_demo_last_refresh!="—"}|>
|>

<|part|class_name=panel|
<|1. Chart Playground|text|class_name=sh sh-top|>
<|{ui_plot_option_rows}|chart|type=plotly|figure={ui_plot_playground_figure}|height=420px|>
<|{ui_plot_option_rows}|table|columns=Option;Value;Description|show_all=False|page_size=8|>
|>

<|part|class_name=panel|
<|2. Plotly Catalog|text|class_name=sh sh-top|>
<|part|render={not ui_demo_has_data}|
<|Run Analyze Text or click Generate Demo Session to populate catalog charts.|text|class_name=inline-hint|>
|>
<|layout|columns=1 1|gap=18px|
<|part|render={ui_demo_pareto_figure!={}}|class_name=settings-panel|
<|Pareto (Bar + Line)|text|class_name=sh sh-top|>
<|{ui_demo_entity_table}|chart|id=catalog_pareto|type=plotly|figure={ui_demo_pareto_figure}|height=300px|>
|>
<|part|render={ui_demo_treemap_figure!={}}|class_name=settings-panel|
<|Treemap|text|class_name=sh sh-top|>
<|{ui_demo_entity_table}|chart|id=catalog_treemap|type=plotly|figure={ui_demo_treemap_figure}|height=300px|>
|>
<|part|render={ui_demo_conf_box_figure!={}}|class_name=settings-panel|
<|Box Plot|text|class_name=sh sh-top|>
<|{ui_demo_evidence_table}|chart|id=catalog_box|type=plotly|figure={ui_demo_conf_box_figure}|height=300px|>
|>
<|part|render={ui_demo_heatmap_figure!={}}|class_name=settings-panel|
<|Heatmap|text|class_name=sh sh-top|>
<|{ui_demo_evidence_table}|chart|id=catalog_heatmap|type=plotly|figure={ui_demo_heatmap_figure}|height=300px|>
|>
<|part|render={ui_demo_timeline_figure!={}}|class_name=settings-panel|
<|Timeline (Line + Bar)|text|class_name=sh sh-top|>
<|{ui_demo_pipeline_table}|chart|id=catalog_timeline|type=plotly|figure={ui_demo_timeline_figure}|height=300px|>
|>
<|part|render={ui_demo_pipeline_figure!={}}|class_name=settings-panel|
<|Pipeline Distribution|text|class_name=sh sh-top|>
<|{ui_demo_pipeline_table}|chart|id=catalog_pipeline|type=plotly|figure={ui_demo_pipeline_figure}|height=300px|>
|>
|>
|>

<|part|class_name=panel|
<|3. Geo Signal Map|text|class_name=sh sh-top|>
<|{ui_demo_map_md}|text|mode=md|class_name=inline-hint|>
<|part|render={ui_demo_map_figure!={}}|
<|{ui_demo_entity_table}|chart|id=catalog_map|type=plotly|figure={ui_demo_map_figure}|height=420px|>
|>
|>

<|part|class_name=panel|
<|4. Underlying Tables|text|class_name=sh sh-top|>
<|layout|columns=1 1 1|gap=12px|
<|{ui_demo_entity_table}|table|columns=Entity Type;Count;Share %;Cumulative %|show_all=False|page_size=8|>
<|{ui_demo_evidence_table}|table|columns=Entity Type;Confidence;Recognizer;Text|show_all=False|page_size=8|>
<|{ui_demo_pipeline_table}|table|columns=Stage;Count|show_all=False|page_size=8|>
|>
|>

|>
"""

# ─── Navigation & pages dict ──────────────────────────────────────────────────
NAV = """
<|menu|lov={menu_lov}|on_action=on_menu_action|label=Anonymous Studio|>
"""

PAGES = {
    "/":          NAV,
    "dashboard":  DASH,
    "analyze":    QT,
    "jobs":       JOBS,
    "pipeline":   PIPELINE,
    "schedule":   SCHEDULE,
    "audit":      AUDIT,
    "ui_demo":    UI_DEMO,
}
