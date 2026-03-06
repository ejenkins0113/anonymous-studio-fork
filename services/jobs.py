"""Job service helpers for Taipy job lifecycle callbacks."""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
import uuid
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd

_log = logging.getLogger(__name__)

CANCELLABLE_STATUS_NAMES = {"SUBMITTED", "BLOCKED", "PENDING", "RUNNING"}
DONE_LIKE_STATUS_NAMES = {"COMPLETED", "FAILED", "SKIPPED", "CANCELED", "ABANDONED"}

# 500 MB hard cap on uploaded files.
MAX_UPLOAD_BYTES = int(os.environ.get("ANON_MAX_UPLOAD_MB", "500")) * 1024 * 1024

# Accepted MIME magic bytes (first 8 bytes of file content).
# We do not require python-magic; a lightweight header check is sufficient.
_CSV_SIGNATURES: tuple = ()   # CSV is plain text — no magic bytes; rely on extension + decode attempt
_XLSX_MAGIC = b"PK\x03\x04"  # ZIP container (xlsx / xlsm)
_XLS_MAGIC  = b"\xd0\xcf\x11\xe0"  # OLE2 container (xls)


def new_job_id() -> str:
    return str(uuid.uuid4())[:12]


def resolve_upload_bytes(state: Any, file_cache: Dict[str, Dict[str, Any]], state_id: str) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """Get uploaded bytes from per-session cache or bound fallback path."""
    slot = file_cache.get(state_id, {})
    raw_bytes = slot.get("bytes")
    if raw_bytes is not None:
        return raw_bytes, slot

    fc = getattr(state, "job_file_content", None)
    if isinstance(fc, bytes):
        return fc, slot

    if isinstance(fc, str) and fc and os.path.exists(fc):
        with open(fc, "rb") as uploaded:
            raw_bytes = uploaded.read()
        slot = {"bytes": raw_bytes, "name": os.path.basename(fc)}
        file_cache[state_id] = slot
        return raw_bytes, slot

    return None, slot


def stage_csv_upload_for_job(job_id: str, file_name: str, raw_bytes: bytes) -> str:
    """Persist uploaded CSV bytes to a worker-visible temp file and return path."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(file_name or "upload.csv"))
    root = os.path.join(
        os.environ.get("ANON_UPLOAD_DIR", tempfile.gettempdir()),
        "anon_studio_uploads",
    )
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{job_id}_{safe_name}")
    with open(path, "wb") as out:
        out.write(raw_bytes)
    return path


def parse_upload_to_df(raw_bytes: bytes, file_name: str) -> pd.DataFrame:
    """Parse CSV/XLSX/XLS bytes into a DataFrame.

    Validates:
    - File size ≤ MAX_UPLOAD_BYTES (default 500 MB)
    - Extension matches actual file content (magic bytes for binary formats)
    - CSV content is valid UTF-8 or latin-1 text
    """
    if not raw_bytes:
        raise ValueError("Uploaded file is empty.")

    size = len(raw_bytes)
    if size > MAX_UPLOAD_BYTES:
        mb = size / (1024 * 1024)
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValueError(
            f"File is {mb:.1f} MB — exceeds the {limit_mb} MB limit. "
            "Split the file into smaller chunks and re-upload."
        )

    lowered = (file_name or "").lower()
    header = raw_bytes[:8]

    if lowered.endswith(".csv"):
        # CSV must be plain text — reject if it starts with a known binary magic signature.
        if header[:4] in (_XLSX_MAGIC, _XLS_MAGIC) or header[:4] == b"PK\x03\x04":
            raise ValueError(
                "File extension is .csv but the content looks like a binary (Excel) file. "
                "Save the file as CSV first."
            )
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding="latin-1")

    if lowered.endswith(".xlsx"):
        if not header.startswith(_XLSX_MAGIC):
            raise ValueError(
                "File extension is .xlsx but the content does not look like a valid Excel file."
            )
        return pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")

    if lowered.endswith(".xls"):
        if not header.startswith(_XLS_MAGIC):
            raise ValueError(
                "File extension is .xls but the content does not look like a valid Excel file."
            )
        return pd.read_excel(io.BytesIO(raw_bytes), engine="xlrd")

    raise ValueError(
        f"Unsupported file type '{os.path.splitext(file_name)[-1]}'. "
        "Upload a .csv, .xlsx, or .xls file."
    )


def build_job_config(
    job_id: str,
    operator: str,
    entities: Iterable[str],
    threshold: float,
    chunk_size: int,
    spacy_model: str = "auto",
    compute_backend: str = "auto",
    dask_min_rows: int = 250000,
) -> Dict[str, Any]:
    backend = (compute_backend or os.environ.get("ANON_JOB_COMPUTE_BACKEND", "auto") or "auto").strip().lower()
    if backend not in {"auto", "pandas", "dask"}:
        backend = "auto"
    try:
        dask_min_rows = int(dask_min_rows or os.environ.get("ANON_DASK_MIN_ROWS", "250000") or 250000)
    except Exception:
        dask_min_rows = 250000
    dask_min_rows = max(10_000, dask_min_rows)
    return {
        "job_id": job_id,
        "operator": operator,
        "entities": list(entities),
        "threshold": threshold,
        "text_columns": [],
        "chunk_size": chunk_size,
        "spacy_model": str(spacy_model or "auto"),
        "compute_backend": backend,
        "dask_min_rows": dask_min_rows,
    }


def build_queue_quality_md(row_count: int, operator: str, entity_count: int) -> str:
    return (
        f"Queued **{row_count:,}** rows · method **{operator}** · "
        f"entity scope **{entity_count}** types."
    )


def build_result_quality_md(stats_data: Optional[Dict[str, Any]], anon_df: Optional[pd.DataFrame]) -> str:
    """Compose markdown summary for job results."""
    if not stats_data:
        return "Run a job to see quality summary."

    processed = int(stats_data.get("processed_rows", 0) or 0)
    total_entities = int(stats_data.get("total_entities", 0) or 0)
    cols_processed = stats_data.get("cols_processed", []) or []
    density = (total_entities / processed) if processed else 0.0
    summary = (
        f"Processed **{processed:,}** rows across **{len(cols_processed)}** text columns.  \n"
        f"Detected **{total_entities:,}** entities ({density:.2f} entities/row)."
    )
    backend_used = str(stats_data.get("compute_backend_used", "") or "").strip()
    backend_note = str(stats_data.get("compute_backend_note", "") or "").strip()
    if backend_used:
        detail = f" ({backend_note})" if backend_note else ""
        summary += f"  \nCompute backend **{backend_used}**{detail}."
    if anon_df is not None and not anon_df.empty:
        ratio = (total_entities / len(anon_df)) if len(anon_df) else 0.0
        summary += f"  \nOutput size **{len(anon_df):,}** rows; redaction ratio **{ratio:.2f}** entities/row."
    return summary


def build_entity_stats_df(stats_data: Optional[Dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {"Entity Type": key, "Count": value}
        for key, value in (stats_data or {}).get("entity_counts", {}).items()
    ]
    return pd.DataFrame(rows, columns=["Entity Type", "Count"])


def latest_cancellable_job(jobs: Iterable[Any]) -> Optional[Any]:
    for job in reversed(list(jobs)):
        status_name = getattr(getattr(job, "status", None), "name", "")
        if status_name in CANCELLABLE_STATUS_NAMES:
            return job
    return None


def all_jobs_done_like(jobs: Iterable[Any]) -> bool:
    for job in jobs:
        status_name = getattr(getattr(job, "status", None), "name", "")
        if status_name not in DONE_LIKE_STATUS_NAMES:
            return False
    return True
