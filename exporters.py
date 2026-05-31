"""
Export helpers: turn an analysis result into Markdown or PDF bytes.

PDF generation uses fpdf2 (pure-Python, no system dependencies), so it works
on the free tier and on any OS without installing extra binaries.
"""

from __future__ import annotations

from typing import Any, Dict


def to_markdown(result: Dict[str, Any]) -> str:
    """Render a single analysis result as a Markdown string."""
    s = result.get("sentiment", {})
    e = result.get("entities", {})

    lines = [
        f"# News Brief: {result.get('topic', '')}",
        "",
        f"**{result.get('headline', '')}**",
        "",
        "## Key Points",
    ]
    lines += [f"- {b}" for b in result.get("bullets", [])]
    lines += [
        "",
        "## Sentiment",
        f"- **{s.get('label', 'Neutral')}** (score: {s.get('score', 0)})",
        f"- {s.get('reason', '')}",
        "",
        "## Key Entities",
        f"- **People:** {', '.join(e.get('people', [])) or '—'}",
        f"- **Organizations:** {', '.join(e.get('organizations', [])) or '—'}",
        f"- **Locations:** {', '.join(e.get('locations', [])) or '—'}",
        "",
        "## Takeaway",
        result.get("takeaway", ""),
        "",
        "## Sources",
    ]
    for i, src in enumerate(result.get("sources", []), 1):
        lines.append(f"{i}. [{src['title']}]({src['url']})")

    return "\n".join(lines)


def _clean(text: str) -> str:
    """Replace characters fpdf's core fonts (latin-1) can't encode."""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u2022": "-",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def to_pdf(result: Dict[str, Any]) -> bytes:
    """Render a single analysis result as PDF bytes."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Explicit usable width avoids fpdf2's "not enough horizontal space" error
    # that happens when width is passed as 0 in some versions.
    W = pdf.w - pdf.l_margin - pdf.r_margin

    s = result.get("sentiment", {})
    e = result.get("entities", {})

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(W, 9, _clean(f"News Brief: {result.get('topic', '')}"))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(W, 7, _clean(result.get("headline", "")))
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Key Points", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for b in result.get("bullets", []):
        pdf.multi_cell(W, 6, _clean(f"- {b}"))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Sentiment", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0, 6, _clean(f"{s.get('label', 'Neutral')} (score: {s.get('score', 0)}) - {s.get('reason', '')}")
    )
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Key Entities", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(W, 6, _clean(f"People: {', '.join(e.get('people', [])) or '-'}"))
    pdf.multi_cell(W, 6, _clean(f"Organizations: {', '.join(e.get('organizations', [])) or '-'}"))
    pdf.multi_cell(W, 6, _clean(f"Locations: {', '.join(e.get('locations', [])) or '-'}"))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Takeaway", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(W, 6, _clean(result.get("takeaway", "")))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Sources", ln=True)
    pdf.set_font("Helvetica", "", 10)
    for i, src in enumerate(result.get("sources", []), 1):
        pdf.multi_cell(W, 6, _clean(f"{i}. {src['title']} - {src['url']}"))

    out = pdf.output(dest="S")
    # fpdf2 returns a bytearray; Streamlit's download_button wants bytes
    return bytes(out)