import marimo

__generated_with = "0.20.4"
app = marimo.App(width="full")


@app.cell
def _(mo):
    mo.md("""
    # Anonymous Studio — SigNoz Token Preview
    All design tokens from `@signozhq/design-tokens v2.1.2` as applied in `app.css`.
    """)
    return


@app.cell
def _(mo):
    def swatch(label, hex_val, text="#fff"):
        return mo.Html(f"""
        <div style="display:inline-block;margin:4px;text-align:center;min-width:120px">
          <div style="width:120px;height:60px;background:{hex_val};border-radius:6px;
                      border:1px solid #242834;margin-bottom:4px"></div>
          <div style="font-size:11px;color:#c0c1c3;font-family:Inter,sans-serif">{label}</div>
          <div style="font-size:10px;color:#62687c;font-family:monospace">{hex_val}</div>
        </div>""")

    def section(title):
        return mo.Html(f"""<div style="margin:24px 0 8px;font-size:11px;font-weight:600;
                           text-transform:uppercase;letter-spacing:.12em;color:#62687c;
                           border-bottom:1px solid #242834;padding-bottom:8px;
                           font-family:Inter,sans-serif">{title}</div>""")

    return section, swatch


@app.cell
def _(mo, section, swatch):
    bg = mo.vstack([
        section("Backgrounds — Ink Scale"),
        mo.hstack([
            swatch("bg-base / ink-500",     "#0b0c0e"),
            swatch("bg-surface / ink-400",  "#121317"),
            swatch("bg-elevated / ink-300", "#16181d"),
            swatch("bg-overlay / ink-200",  "#23262e"),
            swatch("ink-100",               "#2a2e37"),
        ], justify="start"),
    ])
    return (bg,)


@app.cell
def _(mo, section, swatch):
    borders = mo.vstack([
        section("Borders — Slate Scale"),
        mo.hstack([
            swatch("border-subtle / slate-300",  "#242834"),
            swatch("border-default / slate-200", "#2c3140"),
            swatch("border-strong / slate-100",  "#3c4152"),
            swatch("slate-50 (gray/muted)",      "#62687c"),
        ], justify="start"),
    ])
    return (borders,)


@app.cell
def _(mo, section, swatch):
    accent = mo.vstack([
        section("Primary Accent — Robin Blue"),
        mo.hstack([
            swatch("accent / robin-500",       "#4e74f8"),
            swatch("accent-hover / robin-400", "#7190f9"),
            swatch("robin-300",                "#95acfb"),
            swatch("robin-600",                "#3f5ecc"),
        ], justify="start"),
    ])
    return (accent,)


@app.cell
def _(mo, section, swatch):
    semantic = mo.vstack([
        section("Semantic Colors"),
        mo.hstack([
            swatch("success / forest-500", "#25e192"),
            swatch("warning / amber-500",  "#ffcc56"),
            swatch("error / cherry-500",   "#e5484d"),
            swatch("info / aqua-500",      "#23c4f8"),
            swatch("special / robin-400",  "#7190f9"),
        ], justify="start"),
    ])
    return (semantic,)


@app.cell
def _(mo, section, swatch):
    text = mo.vstack([
        section("Text Hierarchy — Vanilla / Slate"),
        mo.hstack([
            swatch("text-primary / vanilla-100",   "#ffffff"),
            swatch("text-secondary / vanilla-400", "#c0c1c3"),
            swatch("text-muted / slate-50",        "#62687c"),
            swatch("text-faint / slate-100",       "#3c4152"),
        ], justify="start"),
    ])
    return (text,)


@app.cell
def _(mo, section, swatch):
    anon = mo.vstack([
        section("Anonymized Text"),
        mo.hstack([
            swatch("anon-bg",      "#0a130e"),
            swatch("anon-fg / forest-200",  "#a8f3d3"),
            swatch("anon-tag / forest-500", "#25e192"),
        ], justify="start"),
    ])
    return (anon,)


@app.cell
def _(accent, anon, bg, borders, mo, semantic, text):
    page = mo.Html("""<div style="background:#0b0c0e;min-height:100vh;padding:32px;
                       font-family:Inter,sans-serif">""")
    mo.vstack([page, bg, borders, accent, semantic, text, anon])
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


if __name__ == "__main__":
    app.run()
