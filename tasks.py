"""
Anonymous Studio — Task Functions
The actual computation that runs inside taipy.core jobs.

run_pii_anonymization(raw_df, job_config) → (anonymized_df, job_stats)

Features:
  • Auto-detects text columns with PII patterns
  • Chunked row processing — memory-safe for large files
  • Per-chunk progress written to PROGRESS_REGISTRY + durable snapshot files
  • Per-column entity counts and timing
  • Error isolation — bad rows never kill the whole job
"""
from __future__ import annotations
import os
import re
import time
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
from services.progress_snapshots import write_progress_snapshot
try:
    import dask.dataframe as dd
except Exception:  # optional dependency
    dd = None

# ── Shared progress registry ──────────────────────────────────────────────────
# job_id → { pct, processed, total, message, status }
# Written inside the task thread, read by the GUI polling loop.
PROGRESS_REGISTRY: Dict[str, Dict[str, Any]] = {}

_BACKEND_AUTO = "auto"
_BACKEND_PANDAS = "pandas"
_BACKEND_DASK = "dask"


def _resolve_compute_backend(job_config: Dict[str, Any], total_rows: int) -> Tuple[str, str]:
    """
    Resolve compute backend for the task run.

    Supported values:
        - auto   : use Dask only for large runs when installed
        - pandas : always use pandas chunk loop
        - dask   : force Dask partition loop (fallbacks to pandas if unavailable)
    """
    requested = str(
        job_config.get("compute_backend", os.environ.get("ANON_JOB_COMPUTE_BACKEND", _BACKEND_AUTO))
        or _BACKEND_AUTO
    ).strip().lower()
    if requested not in {_BACKEND_AUTO, _BACKEND_PANDAS, _BACKEND_DASK}:
        requested = _BACKEND_AUTO

    try:
        dask_min_rows = int(
            job_config.get("dask_min_rows", os.environ.get("ANON_DASK_MIN_ROWS", "250000")) or 250000
        )
    except Exception:
        dask_min_rows = 250000
    dask_min_rows = max(10_000, dask_min_rows)

    if requested == _BACKEND_PANDAS:
        return _BACKEND_PANDAS, "forced pandas"

    if requested == _BACKEND_DASK:
        if dd is None:
            return _BACKEND_PANDAS, "dask requested but not installed"
        return _BACKEND_DASK, "forced dask"

    # auto
    if dd is None:
        return _BACKEND_PANDAS, "auto fallback (dask not installed)"
    if total_rows >= dask_min_rows:
        return _BACKEND_DASK, f"auto dask (rows >= {dask_min_rows:,})"
    return _BACKEND_PANDAS, f"auto pandas (rows < {dask_min_rows:,})"


def _dask_partitions(df: pd.DataFrame, size: int):
    """Yield (partition_index, pandas_partition) using Dask partitions."""
    nparts = max(1, (len(df) + size - 1) // size)
    ddf = dd.from_pandas(df, npartitions=nparts)
    for part_idx in range(ddf.npartitions):
        part_df = ddf.get_partition(part_idx).compute(scheduler="threads")
        if part_df is None or part_df.empty:
            continue
        yield part_idx, part_df, ddf.npartitions


def _dask_csv_partitions(path: str):
    """Yield (partition_index, pandas_partition, total_partitions) from a CSV path."""
    blocksize = os.environ.get("ANON_DASK_BLOCKSIZE", "32MB")
    ddf = dd.read_csv(path, blocksize=blocksize)
    for part_idx in range(ddf.npartitions):
        part_df = ddf.get_partition(part_idx).compute(scheduler="threads")
        if part_df is None or part_df.empty:
            continue
        yield part_idx, part_df, ddf.npartitions


def _progress(job_id: str, pct: float, processed: int,
              total: int, msg: str, status: str = "running"):
    payload = {
        "pct":       round(min(pct, 100.0), 1),
        "processed": processed,
        "total":     total,
        "message":   msg,
        "status":    status,          # running | done | error
        "ts":        datetime.now().isoformat(timespec="seconds"),
        "updated_at": time.time(),
    }
    PROGRESS_REGISTRY[job_id] = payload
    write_progress_snapshot(job_id, payload)


def _coerce_raw_input_to_df(raw_input: Any) -> pd.DataFrame:
    """Normalize DataNode payloads (DataFrame, Mongo docs, list) to DataFrame."""
    if raw_input is None:
        return pd.DataFrame()
    if isinstance(raw_input, pd.DataFrame):
        # Avoid an unnecessary deep copy for very large datasets.
        return raw_input
    if isinstance(raw_input, list):
        if not raw_input:
            return pd.DataFrame()
        rows = []
        for item in raw_input:
            if isinstance(item, dict):
                rows.append(item)
            elif hasattr(item, "__dict__"):
                rows.append(dict(item.__dict__))
            else:
                rows.append({"value": item})
        df = pd.DataFrame(rows)
        if "_id" in df.columns:
            df = df.drop(columns=["_id"])
        return df
    if isinstance(raw_input, dict):
        return pd.DataFrame([raw_input])
    return pd.DataFrame(raw_input)


# ── Main task ─────────────────────────────────────────────────────────────────
def run_pii_anonymization(
    raw_df:     Any,
    job_config: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    taipy.core Task — called by the Orchestrator in a background thread.

    Inputs  (DataNodes):  raw_df, job_config
    Outputs (DataNodes):  anonymized_df, job_stats
    """
    from pii_engine import get_engine, ALL_ENTITIES, set_spacy_model

    job_id     = job_config.get("job_id", "unknown")
    operator   = job_config.get("operator", "replace")
    entities   = job_config.get("entities", ALL_ENTITIES)
    threshold  = job_config.get("threshold", 0.35)
    spacy_model_requested = str(job_config.get("spacy_model", "auto") or "auto")
    spacy_model_resolved, spacy_has_ner, _ = set_spacy_model(spacy_model_requested)
    text_cols  = job_config.get("text_columns", [])   # [] = auto-detect
    chunk_size = int(job_config.get("chunk_size", 500) or 500)
    chunk_size = max(100, chunk_size)
    input_csv_path = str(job_config.get("input_csv_path", "") or "").strip()
    try:
        row_count_hint = int(job_config.get("row_count_hint", 0) or 0)
    except Exception:
        row_count_hint = 0

    t0         = datetime.now()
    engine     = get_engine()
    if input_csv_path:
        total_rows = max(0, row_count_hint)
        raw_df = pd.DataFrame()
    else:
        raw_df = _coerce_raw_input_to_df(raw_df)
        total_rows = len(raw_df)

    compute_backend, backend_note = _resolve_compute_backend(job_config, total_rows)

    stats: Dict[str, Any] = {
        "job_id":          job_id,
        "total_rows":      total_rows,
        "processed_rows":  0,
        "total_entities":  0,
        "entity_counts":   {},
        "cols_processed":  [],
        "operator":        operator,
        "spacy_model_requested": spacy_model_requested,
        "spacy_model_resolved": spacy_model_resolved,
        "spacy_has_ner": bool(spacy_has_ner),
        "compute_backend_requested": str(job_config.get("compute_backend", _BACKEND_AUTO) or _BACKEND_AUTO),
        "compute_backend_used": compute_backend,
        "compute_backend_note": backend_note,
        "started_at":      t0.isoformat(),
        "finished_at":     None,
        "duration_s":      None,
        "errors":          [],
        "sample_before":   [],
        "sample_after":    [],
    }

    _progress(
        job_id,
        0,
        0,
        total_rows,
        f"Initializing engine ({spacy_model_resolved}) · backend {compute_backend}",
    )

    # ── Edge cases / input materialization ────────────────────────────────────
    if input_csv_path:
        # Path traversal guard: resolve the absolute path and confirm it stays
        # within the expected upload/temp directory.  Reject anything that
        # escapes by using ".." components or absolute paths outside the allowed root.
        _upload_root = os.path.realpath(
            os.environ.get(
                "ANON_UPLOAD_DIR",
                os.path.join(tempfile.gettempdir(), "anon_studio_uploads"),
            )
        )
        _resolved = os.path.realpath(input_csv_path)
        try:
            inside_upload_root = os.path.commonpath([_resolved, _upload_root]) == _upload_root
        except Exception:
            inside_upload_root = False
        if not inside_upload_root:
            msg = "Rejected: CSV path is outside the allowed upload directory."
            _progress(job_id, 100, 0, 0, msg, "error")
            stats["errors"].append(msg)
            stats["finished_at"] = datetime.now().isoformat()
            return pd.DataFrame(), stats

        if not os.path.exists(input_csv_path):
            msg = "CSV input path not found."  # Do not echo path to avoid leaking internal layout
            _progress(job_id, 100, 0, 0, msg, "error")
            stats["errors"].append(msg)
            stats["finished_at"] = datetime.now().isoformat()
            return pd.DataFrame(), stats

        if compute_backend == _BACKEND_DASK and dd is not None:
            if not text_cols:
                sample_df = pd.read_csv(input_csv_path, nrows=max(200, min(chunk_size, 5000)))
                text_cols = _detect_text_columns(sample_df)
                stats["sample_before"] = sample_df[text_cols].head(3).fillna("").to_dict("records") if text_cols else []
            if not text_cols:
                msg = "No text columns detected. Check your file or specify columns manually."
                _progress(job_id, 100, 0, 0, msg, "error")
                stats["errors"].append(msg)
                stats["finished_at"] = datetime.now().isoformat()
                return pd.DataFrame(), stats
            stats["cols_processed"] = text_cols

            if total_rows <= 0:
                try:
                    total_rows = int(dd.read_csv(input_csv_path).map_partitions(len).sum().compute())
                except Exception:
                    total_rows = 0
                stats["total_rows"] = total_rows

            processed = 0
            all_counts: Dict[str, int] = {}
            output_parts: List[pd.DataFrame] = []
            for part_idx, chunk, total_parts in _dask_csv_partitions(input_csv_path):
                start = processed
                _progress(
                    job_id,
                    pct=(processed / total_rows * 94) if total_rows else 0.0,
                    processed=processed,
                    total=total_rows,
                    msg=f"Partition {part_idx + 1}/{total_parts} · rows {start}–{start + len(chunk) - 1}",
                )

                out_chunk = chunk.copy(deep=False)
                for col in text_cols:
                    if col not in out_chunk.columns:
                        continue
                    try:
                        anon_series, counts = _anonymize_series(
                            out_chunk[col], engine, entities, operator, threshold
                        )
                        out_chunk[col] = anon_series.values
                        for etype, cnt in counts.items():
                            all_counts[etype] = all_counts.get(etype, 0) + cnt
                    except Exception as exc:
                        err = f"Partition {part_idx + 1} · col '{col}': {exc}"
                        stats["errors"].append(err)

                output_parts.append(out_chunk)
                processed += len(out_chunk)

            output = pd.concat(output_parts, ignore_index=True) if output_parts else pd.DataFrame()
        else:
            raw_df = pd.read_csv(input_csv_path)
            total_rows = len(raw_df)
            stats["total_rows"] = total_rows

            if raw_df.empty:
                _progress(job_id, 100, 0, 0, "Empty dataset — nothing to do.", "done")
                stats["finished_at"] = datetime.now().isoformat()
                stats["duration_s"] = 0
                return pd.DataFrame(), stats

            if not text_cols:
                text_cols = _detect_text_columns(raw_df)
            if not text_cols:
                msg = "No text columns detected. Check your file or specify columns manually."
                _progress(job_id, 100, total_rows, total_rows, msg, "error")
                stats["errors"].append(msg)
                stats["finished_at"] = datetime.now().isoformat()
                return raw_df.copy(), stats
            stats["cols_processed"] = text_cols
            stats["sample_before"] = raw_df[text_cols].head(3).fillna("").to_dict("records")

            output = raw_df.copy(deep=False)
            processed = 0
            all_counts = {}
            n_chunks = max(1, (total_rows + chunk_size - 1) // chunk_size)
            for chunk_idx, (start, chunk) in enumerate(_chunks(raw_df, chunk_size)):
                _progress(
                    job_id,
                    pct=processed / total_rows * 94,
                    processed=processed,
                    total=total_rows,
                    msg=f"Chunk {chunk_idx + 1}/{n_chunks} · rows {start}–{start + len(chunk) - 1}",
                )
                for col in text_cols:
                    if col not in chunk.columns:
                        continue
                    try:
                        anon_series, counts = _anonymize_series(
                            chunk[col], engine, entities, operator, threshold
                        )
                        col_idx = output.columns.get_loc(col)
                        output.iloc[start: start + len(chunk), col_idx] = anon_series.values
                        for etype, cnt in counts.items():
                            all_counts[etype] = all_counts.get(etype, 0) + cnt
                    except Exception as exc:
                        err = f"Chunk {chunk_idx + 1} · col '{col}': {exc}"
                        stats["errors"].append(err)
                processed += len(chunk)
    else:
        if raw_df is None or raw_df.empty:
            _progress(job_id, 100, 0, 0, "Empty dataset — nothing to do.", "done")
            stats["finished_at"] = datetime.now().isoformat()
            stats["duration_s"] = 0
            return pd.DataFrame(), stats

        if not text_cols:
            text_cols = _detect_text_columns(raw_df)
        if not text_cols:
            msg = "No text columns detected. Check your file or specify columns manually."
            _progress(job_id, 100, total_rows, total_rows, msg, "error")
            stats["errors"].append(msg)
            stats["finished_at"] = datetime.now().isoformat()
            return raw_df.copy(), stats
        stats["cols_processed"] = text_cols
        stats["sample_before"] = raw_df[text_cols].head(3).fillna("").to_dict("records")

        output = raw_df.copy(deep=False)
        processed = 0
        all_counts = {}
        if compute_backend == _BACKEND_DASK and dd is not None:
            for part_idx, chunk, total_parts in _dask_partitions(raw_df, chunk_size):
                start = processed
                _progress(
                    job_id,
                    pct=processed / total_rows * 94,
                    processed=processed,
                    total=total_rows,
                    msg=f"Partition {part_idx + 1}/{total_parts} · rows {start}–{start + len(chunk) - 1}",
                )
                for col in text_cols:
                    if col not in chunk.columns:
                        continue
                    try:
                        anon_series, counts = _anonymize_series(
                            chunk[col], engine, entities, operator, threshold
                        )
                        output.loc[chunk.index, col] = anon_series.values
                        for etype, cnt in counts.items():
                            all_counts[etype] = all_counts.get(etype, 0) + cnt
                    except Exception as exc:
                        err = f"Partition {part_idx + 1} · col '{col}': {exc}"
                        stats["errors"].append(err)
                processed += len(chunk)
        else:
            n_chunks = max(1, (total_rows + chunk_size - 1) // chunk_size)
            for chunk_idx, (start, chunk) in enumerate(_chunks(raw_df, chunk_size)):
                _progress(
                    job_id,
                    pct=processed / total_rows * 94,
                    processed=processed,
                    total=total_rows,
                    msg=f"Chunk {chunk_idx + 1}/{n_chunks} · rows {start}–{start + len(chunk) - 1}",
                )
                for col in text_cols:
                    if col not in chunk.columns:
                        continue
                    try:
                        anon_series, counts = _anonymize_series(
                            chunk[col], engine, entities, operator, threshold
                        )
                        col_idx = output.columns.get_loc(col)
                        output.iloc[start: start + len(chunk), col_idx] = anon_series.values
                        for etype, cnt in counts.items():
                            all_counts[etype] = all_counts.get(etype, 0) + cnt
                    except Exception as exc:
                        err = f"Chunk {chunk_idx + 1} · col '{col}': {exc}"
                        stats["errors"].append(err)
                processed += len(chunk)

    # ── Finalise stats ────────────────────────────────────────────────────────
    t1 = datetime.now()
    stats["processed_rows"]  = processed
    stats["entity_counts"]   = all_counts
    stats["total_entities"]  = sum(all_counts.values())
    stats["sample_after"]    = output[text_cols].head(3).fillna("").to_dict("records") if text_cols else []
    stats["finished_at"]     = t1.isoformat()
    stats["duration_s"]      = round((t1 - t0).total_seconds(), 2)

    _progress(
        job_id, 100, total_rows, total_rows,
        f"{stats['total_entities']} entities anonymized "
        f"across {len(text_cols)} column(s) in {stats['duration_s']}s",
        "done",
    )
    return output, stats


# ── Helpers ───────────────────────────────────────────────────────────────────

_PII_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"   # email
    r"|\b\d{3}[-.\s]\d{2}[-.\s]\d{4}\b"                   # SSN
    r"|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"                   # phone
    r"|\b(?:\d[ -]?){13,16}\b",                             # credit card
    re.I,
)


def _detect_text_columns(df: pd.DataFrame, sample: int = 100) -> List[str]:
    """Return columns that likely contain free text or PII values."""
    cols = []
    for col in df.columns:
        if df[col].dtype != object:
            continue
        s = df[col].dropna().head(sample).astype(str)
        if s.empty:
            continue
        avg_words = s.str.split().str.len().mean()
        pii_hits  = s.str.contains(_PII_RE).sum()
        if avg_words >= 1.5 or pii_hits > 0:
            cols.append(col)
    # Fallback: all string columns (capped at 8)
    if not cols:
        cols = [c for c in df.columns if df[c].dtype == object][:8]
    return cols


def _chunks(df: pd.DataFrame, size: int):
    for start in range(0, len(df), size):
        yield start, df.iloc[start : start + size]


def _anonymize_series(
    series: pd.Series,
    engine,
    entities: List[str],
    operator: str,
    threshold: float,
) -> Tuple[pd.Series, Dict[str, int]]:
    counts: Dict[str, int] = {}
    out = []
    for cell in series:
        if pd.isna(cell) or str(cell).strip() == "":
            out.append(cell)
            continue
        result = engine.anonymize(
            text=str(cell), entities=entities,
            operator=operator, threshold=threshold,
            fast=True,
        )
        out.append(result.anonymized_text)
        for etype, cnt in result.entity_counts.items():
            counts[etype] = counts.get(etype, 0) + cnt
    return pd.Series(out, index=series.index), counts
