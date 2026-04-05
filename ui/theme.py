"""UI theme and chart presets for Taipy GUI.

HyperDX + Perspective.js palette — matches app.css tokens.
Centralizing these keeps app.py focused on state and callbacks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ══════════════════════════════════════════════════════════════════════════════
# COLOR PALETTE — HyperDX near-black + Perspective.js accents
# Keep in sync with :root variables in app.css
# ══════════════════════════════════════════════════════════════════════════════

# Backgrounds — HyperDX near-black
BG_BASE     = "#0b0c0f"   # Body — near black
BG_SURFACE  = "#11131a"   # Panel background
BG_ELEVATED = "#181b24"   # Elevated / hover
BG_OVERLAY  = "#22263a"   # Dropdowns / overlays

# Borders — sharp, minimal (Perspective.js style)
BORDER_SUBTLE  = "#1c2033"
BORDER_DEFAULT = "#252c42"
BORDER_STRONG  = "#323c58"

# Accent — HyperDX electric blue
ACCENT       = "#3d7eff"
ACCENT_HOVER = "#6699ff"

# Semantic Colors
COLOR_INFO    = "#3d7eff"
COLOR_SUCCESS = "#0ccf7a"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR   = "#f04438"
COLOR_SPECIAL = "#b77cf0"
COLOR_CYAN    = "#00b4d8"

# Text
TEXT_PRIMARY   = "#e4e9f2"
TEXT_SECONDARY = "#8b9ab5"
TEXT_MUTED     = "#4d5873"

# Legacy aliases (for compatibility)
COLOR_WARN    = COLOR_WARNING
COLOR_PRIMARY = ACCENT

# ══════════════════════════════════════════════════════════════════════════════
# CHART COLORWAY
# ══════════════════════════════════════════════════════════════════════════════

# HyperDX colorway — electric blue lead, then semantic colors
MONO_COLORWAY: List[str] = [
    COLOR_INFO,     # 0 — HyperDX blue
    COLOR_SUCCESS,  # 1 — vivid green
    COLOR_WARNING,  # 2 — amber
    COLOR_SPECIAL,  # 3 — purple (PII)
    COLOR_ERROR,    # 4 — red
    COLOR_CYAN,     # 5 — cyan
    "#f97316",      # 6 — orange
]

GEO_DARK_SCALE: List[Tuple[float, str]] = [
    (0.0, BG_ELEVATED),
    (0.35, "#12234f"),
    (0.7, COLOR_INFO),
    (1.0, "#91b4ff"),
]

# ══════════════════════════════════════════════════════════════════════════════
# PLOTLY CHART LAYOUT — HyperDX style
# ══════════════════════════════════════════════════════════════════════════════

CHART_LAYOUT: Dict[str, Any] = {
    "template": "plotly_dark",
    "paper_bgcolor": BG_SURFACE,
    "plot_bgcolor": BG_BASE,
    "font": {
        "color": TEXT_PRIMARY,
        "family": "'JetBrains Mono', 'Roboto Mono', ui-monospace, monospace",
        "size": 11,
    },
    "margin": {"t": 28, "b": 44, "l": 48, "r": 12},
    "colorway": MONO_COLORWAY,
    "xaxis": {
        "gridcolor": BORDER_DEFAULT,
        "gridwidth": 1,
        "showgrid": True,
        "griddash": "dot",
        "linecolor": BORDER_STRONG,
        "zerolinecolor": BORDER_STRONG,
        "zerolinewidth": 1,
        "tickfont": {"size": 10, "color": TEXT_MUTED},
        "title_font": {"size": 11, "color": TEXT_SECONDARY},
        "tickcolor": BORDER_SUBTLE,
    },
    "yaxis": {
        "gridcolor": BORDER_DEFAULT,
        "gridwidth": 1,
        "showgrid": True,
        "griddash": "dot",
        "linecolor": BORDER_STRONG,
        "zerolinecolor": BORDER_STRONG,
        "zerolinewidth": 1,
        "tickfont": {"size": 10, "color": TEXT_MUTED},
        "title_font": {"size": 11, "color": TEXT_SECONDARY},
        "tickcolor": BORDER_SUBTLE,
    },
    "legend": {
        "orientation": "h",
        "y": -0.22,
        "x": 0,
        "font": {"size": 10, "color": TEXT_SECONDARY},
        "bgcolor": "rgba(0,0,0,0)",
        "bordercolor": BORDER_DEFAULT,
    },
    "bargap": 0.22,
    "hoverlabel": {
        "bgcolor": BG_OVERLAY,
        "bordercolor": BORDER_STRONG,
        "font": {"color": TEXT_PRIMARY, "size": 11, "family": "'JetBrains Mono', ui-monospace, monospace"},
        "align": "left",
    },
    "modebar": {
        "bgcolor": "rgba(0,0,0,0)",
        "color": TEXT_MUTED,
        "activecolor": ACCENT,
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# TAIPY STYLEKIT — HyperDX palette
# ══════════════════════════════════════════════════════════════════════════════

DASH_STYLEKIT: Dict[str, Any] = {
    "color_primary":          ACCENT,
    "color_secondary":        COLOR_CYAN,
    "color_error":            COLOR_ERROR,
    "color_warning":          COLOR_WARNING,
    "color_success":          COLOR_SUCCESS,
    "color_background_light": BG_SURFACE,
    "color_paper_light":      BG_ELEVATED,
    "color_background_dark":  BG_BASE,
    "color_paper_dark":       BG_SURFACE,
}
