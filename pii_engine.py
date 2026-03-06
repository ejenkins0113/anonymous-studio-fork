"""
Anonymous Studio — PII Engine
Presidio Analyzer + Anonymizer with automatic spaCy model detection.

Model resolution order (first available wins):
  1. SPACY_MODEL env var           — explicit override, e.g. a custom fine-tuned model
  2. en_core_web_lg                — best NER accuracy, recommended for production
  3. en_core_web_md                — good balance of size and accuracy
  4. en_core_web_sm                — smallest trained model (~12 MB)
  5. en_core_web_trf               — transformer-based, highest accuracy (slower)
  6. Blank fallback                — pattern/regex only; misses PERSON / LOCATION / ORG

To install a model locally:
  python -m spacy download en_core_web_lg

To force a specific model:
  export SPACY_MODEL=en_core_web_lg   # or any installed model name / local path
"""
from __future__ import annotations
import os, re, warnings, logging, tempfile
from functools import lru_cache
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

warnings.filterwarnings("ignore")
logging.getLogger("tldextract").setLevel(logging.CRITICAL)
logging.getLogger("presidio-analyzer").setLevel(logging.CRITICAL)

import spacy

# ── Resolve which spaCy model to use ─────────────────────────────────────────
# Preference order: explicit env var → lg → md → sm → trf → blank fallback.
# spacy.util.get_installed_models() returns names of pip-installed models only;
# we also try loading each by name so local-path models work too.

_PREFERRED_MODELS = [
    "en_core_web_lg",
    "en_core_web_md",
    "en_core_web_sm",
    "en_core_web_trf",
]
_AUTO_MODEL_OPTION = "auto"
_BLANK_MODEL_OPTION = "blank"


def _blank_fallback_model_path() -> str:
    blank_path = os.environ.get(
        "ANON_SPACY_BLANK_PATH",
        os.path.join(tempfile.gettempdir(), "anon_studio_blank_en"),
    )
    if not os.path.exists(blank_path):
        _nlp = spacy.blank("en")
        _nlp.meta.update({"name": "en_blank", "version": "3.0.0", "lang": "en"})
        _nlp.to_disk(blank_path)
    return blank_path

def _find_spacy_model() -> tuple[str, bool]:
    """
    Returns (model_name_or_path, is_trained).
    is_trained=True  → model has NER; PERSON/LOCATION/ORG will be detected.
    is_trained=False → blank fallback; only regex-based entities are detected.
    """
    # 1. Explicit override via environment variable
    env_model = os.environ.get("SPACY_MODEL", "").strip()
    if env_model:
        if env_model.lower() in {_BLANK_MODEL_OPTION, "en_blank", "blank_en"}:
            return _blank_fallback_model_path(), False
        try:
            spacy.load(env_model)
            logging.getLogger(__name__).info(
                f"spaCy: using model from SPACY_MODEL env var: '{env_model}'"
            )
            return env_model, True
        except OSError:
            logging.getLogger(__name__).warning(
                f"spaCy: SPACY_MODEL='{env_model}' not found, falling through."
            )

    # 2. Check installed models (pip-installed via spacy download)
    installed = set(spacy.util.get_installed_models())
    for name in _PREFERRED_MODELS:
        if name in installed:
            logging.getLogger(__name__).info(
                f"spaCy: found locally installed model '{name}' — "
                f"PERSON / LOCATION / ORG detection enabled."
            )
            return name, True

    # 3. Try loading by name even if not in get_installed_models()
    #    (handles models installed via pip from a local wheel)
    for name in _PREFERRED_MODELS:
        try:
            spacy.load(name)
            logging.getLogger(__name__).info(
                f"spaCy: loaded '{name}' — "
                f"PERSON / LOCATION / ORG detection enabled."
            )
            return name, True
        except OSError:
            continue

    # 4. Blank fallback — build a minimal model Presidio can use as a scaffold
    blank_path = _blank_fallback_model_path()
    logging.getLogger(__name__).warning(
        "spaCy: no trained model found — using blank fallback. "
        "PERSON / LOCATION / ORG will NOT be detected. "
        "Run: python -m spacy download en_core_web_lg"
    )
    return blank_path, False


def _build_spacy_status(model_name: str, has_ner: bool) -> str:
    return (
        f"✓ Full NER model: {model_name}"
        if has_ner else
        "▲ Blank model (regex only) - install en_core_web_lg for full detection"
    )


def _apply_spacy_runtime(model_name: str, has_ner: bool) -> None:
    global _SPACY_MODEL, _HAS_NER, SPACY_MODEL_NAME, SPACY_HAS_NER, SPACY_MODEL_STATUS
    _SPACY_MODEL = model_name
    _HAS_NER = has_ner
    SPACY_MODEL_NAME = model_name
    SPACY_HAS_NER = has_ner
    SPACY_MODEL_STATUS = _build_spacy_status(model_name, has_ner)


_SPACY_MODEL, _HAS_NER = _find_spacy_model()
SPACY_MODEL_NAME = ""
SPACY_HAS_NER = False
SPACY_MODEL_STATUS = ""
_apply_spacy_runtime(_SPACY_MODEL, _HAS_NER)


def get_spacy_model_choice() -> str:
    env_model = (os.environ.get("SPACY_MODEL") or "").strip()
    if not env_model:
        return _AUTO_MODEL_OPTION
    if env_model.lower() in {_BLANK_MODEL_OPTION, "en_blank", "blank_en"}:
        return _BLANK_MODEL_OPTION
    return env_model


@lru_cache(maxsize=1)
def get_spacy_model_options() -> List[str]:
    options = [_AUTO_MODEL_OPTION, *_PREFERRED_MODELS]
    try:
        installed = sorted(set(spacy.util.get_installed_models()))
    except Exception:
        installed = []
    for model_name in installed:
        if model_name.startswith("en_core_") and model_name not in options:
            options.append(model_name)
    if _BLANK_MODEL_OPTION not in options:
        options.append(_BLANK_MODEL_OPTION)
    current_choice = get_spacy_model_choice()
    if current_choice and current_choice not in options:
        options.insert(1, current_choice)
    return options


def get_spacy_model_status() -> str:
    return SPACY_MODEL_STATUS


def set_spacy_model(choice: str) -> Tuple[str, bool, str]:
    global _engine

    selected = (choice or _AUTO_MODEL_OPTION).strip()
    if not selected:
        selected = _AUTO_MODEL_OPTION

    if selected == _AUTO_MODEL_OPTION:
        os.environ.pop("SPACY_MODEL", None)
    elif selected == _BLANK_MODEL_OPTION:
        os.environ["SPACY_MODEL"] = _BLANK_MODEL_OPTION
    else:
        os.environ["SPACY_MODEL"] = selected

    model_name, has_ner = _find_spacy_model()
    _apply_spacy_runtime(model_name, has_ner)
    _engine = None
    return model_name, has_ner, SPACY_MODEL_STATUS

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import SpacyNlpEngine, NerModelConfiguration
from presidio_analyzer.recognizer_registry import RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# ── Entity catalogue ──────────────────────────────────────────────────────────
ALL_ENTITIES = [
    "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN",
    "US_PASSPORT", "US_DRIVER_LICENSE", "US_ITIN", "US_BANK_NUMBER",
    "IP_ADDRESS", "URL", "IBAN_CODE", "DATE_TIME",
    "LOCATION", "PERSON", "NRP", "MEDICAL_LICENSE", "ORGANIZATION",
]

ENTITY_COLORS = {
    "EMAIL_ADDRESS":     "#FF2B2B",
    "PHONE_NUMBER":      "#8A38F5",
    "CREDIT_CARD":       "#FF6B35",
    "US_SSN":            "#FF2B2B",
    "US_PASSPORT":       "#E040FB",
    "US_DRIVER_LICENSE": "#E040FB",
    "US_ITIN":           "#FF6B35",
    "US_BANK_NUMBER":    "#FF6B35",
    "IP_ADDRESS":        "#00BCD4",
    "URL":               "#26A69A",
    "IBAN_CODE":         "#FF6B35",
    "DATE_TIME":         "#42A5F5",
    "LOCATION":          "#66BB6A",
    "PERSON":            "#FFA726",
    "NRP":               "#AB47BC",
    "MEDICAL_LICENSE":   "#EC407A",
    "ORGANIZATION":      "#26C6DA",
}

OPERATORS       = ["replace", "redact", "mask", "hash"]
OPERATOR_LABELS = {
    "replace": "Replace  — swap with <ENTITY_TYPE> label",
    "redact":  "Redact   — delete the PII text entirely",
    "mask":    "Mask     — overwrite with *** characters",
    "hash":    "Hash     — SHA-256 one-way hash",
}

CUSTOM_DENYLIST_ENTITY = "CUSTOM_DENYLIST"

# Module-level cache for compiled denylist regex patterns (term → compiled pattern).
_DENYLIST_PATTERN_CACHE: Dict[str, re.Pattern] = {}

# Module-level cache for OperatorConfig dicts — keyed by (operator, sorted entities tuple).
# Saves rebuilding 17+ OperatorConfig objects on every anonymize() call during batch jobs.
_OPS_CACHE: Dict[tuple, Dict] = {}


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class AnalysisResult:
    original_text:   str
    anonymized_text: str
    entities:        List[Dict]
    entity_counts:   Dict[str, int]
    operator_used:   str

    @property
    def total_found(self) -> int:
        return len(self.entities)

    @property
    def entity_summary(self) -> str:
        if not self.entity_counts:
            return "No PII detected"
        return ", ".join(f"{v}× {k}" for k, v in self.entity_counts.items())


def _get_ops(operator: str, entities_key: tuple) -> Dict:
    """Return (and cache) the OperatorConfig dict for a given operator + entity set.

    Called on every anonymize() invocation. Using a module-level dict avoids
    reconstructing 17+ OperatorConfig objects for every cell in a batch job.
    """
    cache_key = (operator, entities_key)
    cached = _OPS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    ops: Dict = {}
    for e in entities_key:
        if operator == "replace":
            ops[e] = OperatorConfig("replace", {"new_value": f"<{e}>"})
        elif operator == "redact":
            ops[e] = OperatorConfig("redact", {})
        elif operator == "mask":
            ops[e] = OperatorConfig("mask", {"type": "mask",
                                              "masking_char": "*",
                                              "chars_to_mask": 20,
                                              "from_end": False})
        elif operator == "hash":
            ops[e] = OperatorConfig("hash", {"hash_type": "sha256",
                                              "salt": "anonymous-studio"})
        else:
            ops[e] = OperatorConfig("replace", {"new_value": f"<{e}>"})
    # Ensure denylist-only detections can always be anonymized.
    if CUSTOM_DENYLIST_ENTITY not in ops:
        if operator == "replace":
            ops[CUSTOM_DENYLIST_ENTITY] = OperatorConfig("replace", {"new_value": "<CUSTOM_DENYLIST>"})
        elif operator == "redact":
            ops[CUSTOM_DENYLIST_ENTITY] = OperatorConfig("redact", {})
        elif operator == "mask":
            ops[CUSTOM_DENYLIST_ENTITY] = OperatorConfig(
                "mask", {"type": "mask", "masking_char": "*", "chars_to_mask": 20, "from_end": False},
            )
        else:
            ops[CUSTOM_DENYLIST_ENTITY] = OperatorConfig(
                "hash", {"hash_type": "sha256", "salt": "anonymous-studio"},
            )
    _OPS_CACHE[cache_key] = ops
    return ops


# ── Engine ────────────────────────────────────────────────────────────────────
class PIIEngine:
    def __init__(self):
        self._analyzer:  Optional[AnalyzerEngine]   = None
        self._anonymizer: Optional[AnonymizerEngine] = None
        self._ready = False

    def _init(self):
        if self._ready:
            return
        ner_cfg = NerModelConfiguration(
            model_to_presidio_entity_mapping={
                "PER": "PERSON", "PERSON": "PERSON",
                "ORG": "ORGANIZATION",
                "LOC": "LOCATION", "GPE": "LOCATION",
            },
            low_confidence_score_multiplier=0.4,
            low_score_entity_names=set(),
        )
        nlp_engine = SpacyNlpEngine(
            models=[{"lang_code": "en", "model_name": _SPACY_MODEL}],
            ner_model_configuration=ner_cfg,
        )
        nlp_engine.load()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)
        self._analyzer   = AnalyzerEngine(nlp_engine=nlp_engine,
                                          registry=registry,
                                          supported_languages=["en"])
        self._anonymizer = AnonymizerEngine()
        self._ready = True

    # ── Public API ────────────────────────────────────────────────────────────
    @staticmethod
    def _norm_terms(terms: Optional[List[str]]) -> List[str]:
        if not terms:
            return []
        # Preserve order while removing blanks/duplicates.
        seen = set()
        cleaned: List[str] = []
        for t in terms:
            v = (t or "").strip()
            if not v:
                continue
            key = v.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(v)
        return cleaned

    @staticmethod
    def _apply_allowlist(raw: List[RecognizerResult], text: str, allowlist: List[str]) -> List[RecognizerResult]:
        if not allowlist:
            return raw
        allowed = {t.lower() for t in allowlist}
        return [r for r in raw if text[r.start:r.end].strip().lower() not in allowed]

    @staticmethod
    def _denylist_results(text: str, denylist: List[str]) -> List[RecognizerResult]:
        out: List[RecognizerResult] = []
        for term in denylist:
            pat = _DENYLIST_PATTERN_CACHE.get(term)
            if pat is None:
                pat = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)
                _DENYLIST_PATTERN_CACHE[term] = pat
            for m in pat.finditer(text):
                out.append(
                    RecognizerResult(
                        entity_type=CUSTOM_DENYLIST_ENTITY,
                        start=m.start(),
                        end=m.end(),
                        score=1.0,
                    )
                )
        return out

    @staticmethod
    def _merge_results(raw: List[RecognizerResult], extras: List[RecognizerResult]) -> List[RecognizerResult]:
        if not extras:
            return raw
        seen = {(r.entity_type, r.start, r.end) for r in raw}
        merged = list(raw)
        for r in extras:
            key = (r.entity_type, r.start, r.end)
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged

    @staticmethod
    def _build_rationale(r) -> str:
        """Build a human-readable rationale string from a RecognizerResult."""
        ex = getattr(r, "analysis_explanation", None)
        if not ex:
            return ""
        parts = []
        recognizer = getattr(ex, "recognizer", "") or ""
        if recognizer:
            parts.append(recognizer)
        pattern_name = getattr(ex, "pattern_name", "") or ""
        if pattern_name:
            parts.append(f"pattern={pattern_name}")
        original_score = getattr(ex, "original_score", None)
        if original_score is not None and original_score != r.score:
            parts.append(f"raw_score={original_score:.2f}")
        textual = getattr(ex, "textual_explanation", "") or ""
        if textual:
            parts.append(textual)
        return "; ".join(parts) if parts else ""

    @staticmethod
    def _entity_dict(r, text: str) -> Dict:
        """Build entity dict from a RecognizerResult including rationale."""
        ex = getattr(r, "analysis_explanation", None)
        return {
            "entity_type": r.entity_type,
            "start": r.start,
            "end": r.end,
            "score": round(r.score, 3),
            "text": text[r.start:r.end],
            "recognizer": (getattr(ex, "recognizer", "") or "") if ex else "",
            "rationale": PIIEngine._build_rationale(r),
        }

    def analyze(self, text: str, entities: List[str] = None,
                threshold: float = 0.35, allowlist: Optional[List[str]] = None,
                denylist: Optional[List[str]] = None) -> List[Dict]:
        self._init()
        if not text or not text.strip():
            return []
        raw: List[RecognizerResult] = self._analyzer.analyze(
            text=text,
            entities=entities or ALL_ENTITIES,
            language="en",
            score_threshold=threshold,
            return_decision_process=True,
        )
        allow = self._norm_terms(allowlist)
        deny = self._norm_terms(denylist)
        raw = self._apply_allowlist(raw, text, allow)
        raw = self._merge_results(raw, self._denylist_results(text, deny))
        return [self._entity_dict(r, text) for r in raw]

    def anonymize(self, text: str, entities: List[str] = None,
                  operator: str = "replace", threshold: float = 0.35,
                  allowlist: Optional[List[str]] = None,
                  denylist: Optional[List[str]] = None,
                  fast: bool = False) -> AnalysisResult:
        self._init()
        if not text or not text.strip():
            return AnalysisResult(text, text, [], {}, operator)

        raw_results: List[RecognizerResult] = self._analyzer.analyze(
            text=text, entities=entities or ALL_ENTITIES,
            language="en", score_threshold=threshold,
            return_decision_process=not fast,
        )
        allow = self._norm_terms(allowlist)
        deny = self._norm_terms(denylist)
        raw_results = self._apply_allowlist(raw_results, text, allow)
        raw_results = self._merge_results(raw_results, self._denylist_results(text, deny))
        detected = [self._entity_dict(r, text) for r in raw_results]

        ops = _get_ops(operator, tuple(sorted(entities or ALL_ENTITIES)))

        try:
            anon_text = self._anonymizer.anonymize(
                text=text, analyzer_results=raw_results, operators=ops
            ).text
        except Exception:
            anon_text = text

        counts: Dict[str, int] = {}
        for e in detected:
            counts[e["entity_type"]] = counts.get(e["entity_type"], 0) + 1

        return AnalysisResult(text, anon_text, detected, counts, operator)

    def highlight_html(self, text: str, entities: List[Dict]) -> str:
        """Color-coded HTML showing detected PII spans."""
        if not entities:
            return f'<span style="color:#FAFAFA">{_esc(text)}</span>'
        merged, cursor = [], 0
        for ent in sorted(entities, key=lambda e: (e["start"], -e["score"])):
            if merged and ent["start"] < merged[-1]["end"]:
                if ent["score"] > merged[-1]["score"]:
                    merged[-1] = ent
            else:
                merged.append(ent)
        parts = []
        for ent in merged:
            if ent["start"] > cursor:
                parts.append(f'<span style="color:#FAFAFA">{_esc(text[cursor:ent["start"]])}</span>')
            color = ENTITY_COLORS.get(ent["entity_type"], "#FF2B2B")
            label = ent["entity_type"].replace("_", " ").title()
            score = ent["score"]
            etxt  = _esc(ent["text"])
            parts.append(
                f'<mark style="background:{color}22;color:{color};'
                f'border:1px solid {color}55;border-radius:3px;'
                f'padding:1px 5px;font-weight:600" '
                f'title="{label} · {score:.0%}">'
                f'{etxt}<sup style="font-size:9px;margin-left:3px">{label}</sup>'
                f'</mark>'
            )
            cursor = ent["end"]
        if cursor < len(text):
            parts.append(f'<span style="color:#FAFAFA">{_esc(text[cursor:])}</span>')
        return "".join(parts)


def highlight_md(text: str, entities: list) -> str:
    """Markdown version of PII highlights using inline code spans.

    Plain-text segments are escaped so that user-supplied content
    containing Markdown metacharacters (e.g. ``**``, ``<script>``) cannot
    alter the document structure or inject HTML.
    """
    import html as _html
    if not entities:
        return "*No PII detected.*"
    merged, cursor = [], 0
    for ent in sorted(entities, key=lambda e: (e["start"], -e["score"])):
        if merged and ent["start"] < merged[-1]["end"]:
            if ent["score"] > merged[-1]["score"]:
                merged[-1] = ent
        else:
            merged.append(ent)
    parts = []
    for ent in merged:
        if ent["start"] > cursor:
            parts.append(_html.escape(text[cursor:ent["start"]]))
        label = ent["entity_type"].replace("_", " ").title()
        ent_text = _html.escape(str(ent.get("text", text[ent["start"]:ent["end"]])))
        score = ent.get("score")
        score_suffix = f" · {float(score):.0%}" if isinstance(score, (int, float)) else ""
        parts.append(f"`{ent_text}` *({label}{score_suffix})*")
        cursor = ent["end"]
    if cursor < len(text):
        parts.append(_html.escape(text[cursor:]))
    return "".join(parts)


def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace("\n", "<br>")
             .replace(" ", "&nbsp;"))


_engine: Optional[PIIEngine] = None

def get_engine() -> PIIEngine:
    global _engine
    if _engine is None:
        _engine = PIIEngine()
    return _engine


import threading as _threading

def _warmup() -> None:
    """Pre-load spaCy + Presidio at import time so the first user call is instant."""
    try:
        get_engine()._init()
    except Exception:
        pass

_threading.Thread(target=_warmup, daemon=True, name="pii-engine-warmup").start()
