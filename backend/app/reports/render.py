"""Render report content to Markdown, self-contained HTML and CSV (pure).

HTML exports escape every value and carry a Content-Security-Policy that blocks scripts, so a
downloaded report cannot execute code even if a source string contained markup.
"""

import csv
import html
import io
from decimal import ROUND_HALF_UP, Decimal

from app.reports.model import ReportContent, ReportSection

KIND_LABEL = {
    "reported": "Reported",
    "calculated": "Calculated",
    "assumption": "Assumption",
    "forecast": "Forecast",
    "extracted": "Extracted from report (verified)",
    "market": "Market data (end of day)",
    "ai_explanation": "AI explanation",
}


def indian_group(value: Decimal, places: int = 2) -> str:
    """12345678.9 -> "1,23,45,678.90" (lakh/crore grouping)."""
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, ROUND_HALF_UP)
    negative = rounded < 0
    whole, _, frac = f"{abs(rounded):f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    text = f"{whole}.{frac}" if frac else whole
    return f"-{text}" if negative else text


def inr(value: Decimal, places: int = 2) -> str:
    return f"₹{indian_group(value, places)}"


def crores(value: Decimal) -> str:
    return f"₹{indian_group(value)} Cr"


def percent(value: Decimal) -> str:
    return f"{indian_group(value * 100, 1)}%"


def times(value: Decimal) -> str:
    return f"{indian_group(value, 2)}x"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _md_section(section: ReportSection) -> list[str]:
    out = [f"## {section.title}", ""]
    if section.status == "unavailable":
        return [*out, f"_Unavailable: {section.reason}_", ""]
    for paragraph in section.paragraphs:
        out += [paragraph, ""]
    if section.figures:
        out += ["| Item | Value | Type | Period | Source |", "|---|---|---|---|---|"]
        for f in section.figures:
            period = " ".join(x for x in (f.period, f.basis) if x)
            out.append(
                f"| {_md_escape(f.label)} | {_md_escape(f.display)} | {KIND_LABEL[f.kind]} | "
                f"{_md_escape(period)} | {_md_escape(f.source or '')} |"
            )
        notes = [f"{f.label}: {f.note}" for f in section.figures if f.note]
        out += [""] + [f"- {_md_escape(n)}" for n in notes] + ([""] if notes else [])
    for table in section.tables:
        out += [f"**{table.caption}** ({KIND_LABEL[table.kind]})", ""]
        out.append("| " + " | ".join(_md_escape(c) for c in table.columns) + " |")
        out.append("|" + "---|" * len(table.columns))
        out += ["| " + " | ".join(_md_escape(c) for c in row) + " |" for row in table.rows]
        if table.source:
            out.append(f"\n_Source: {table.source}_")
        out.append("")
    return out


def to_markdown(content: ReportContent) -> str:
    c = content.company
    lines = [
        f"# {content.title}",
        "",
        f"**{c.name}** ({c.ticker}{', ISIN ' + c.isin if c.isin else ''}) · "
        f"{', '.join(c.listings) or 'no listings'}",
        "",
        f"Generated {content.generated_at:%Y-%m-%d %H:%M} UTC · listing {content.exchange or '—'}"
        f" · statements basis {content.basis or '—'} · engine {content.engine_version}",
        "",
    ]
    for section in content.sections:
        lines += _md_section(section)
    lines += ["## Disclaimers", ""] + [f"- {d}" for d in content.disclaimers]
    return "\n".join(lines).rstrip() + "\n"


_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;"
    "color:#0f172a}table{border-collapse:collapse;width:100%;margin:.5rem 0 1rem;font-size:13px}"
    "th,td{border:1px solid #cbd5e1;padding:4px 6px;text-align:left}th{background:#f1f5f9}"
    ".kind{font-size:11px;color:#475569}.na{color:#64748b;font-style:italic}"
    "h2{border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-top:2rem}"
    "@media print{body{margin:0}}"
)


def _h(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def _html_section(section: ReportSection) -> str:
    parts = [f"<section><h2>{_h(section.title)}</h2>"]
    if section.status == "unavailable":
        parts.append(f'<p class="na">Unavailable: {_h(section.reason)}</p></section>')
        return "".join(parts)
    parts += [f"<p>{_h(p)}</p>" for p in section.paragraphs]
    if section.figures:
        parts.append(
            "<table><thead><tr><th>Item</th><th>Value</th><th>Type</th><th>Period</th>"
            "<th>Source / note</th></tr></thead><tbody>"
        )
        for f in section.figures:
            period = " ".join(x for x in (f.period, f.basis) if x)
            note = " · ".join(x for x in (f.source, f.note) if x)
            parts.append(
                f"<tr><td>{_h(f.label)}</td><td>{_h(f.display)}</td>"
                f'<td class="kind">{_h(KIND_LABEL[f.kind])}</td><td>{_h(period)}</td>'
                f"<td>{_h(note)}</td></tr>"
            )
        parts.append("</tbody></table>")
    for table in section.tables:
        parts.append(
            f"<table><caption>{_h(table.caption)} "
            f'<span class="kind">({_h(KIND_LABEL[table.kind])})</span></caption><thead><tr>'
            + "".join(f"<th>{_h(c)}</th>" for c in table.columns)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>"
                for row in table.rows
            )
            + "</tbody></table>"
        )
        if table.source:
            parts.append(f'<p class="kind">Source: {_h(table.source)}</p>')
    parts.append("</section>")
    return "".join(parts)


def to_html(content: ReportContent) -> str:
    c = content.company
    head = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{_h(content.title)}</title><style>{_CSS}</style></head><body>"
    )
    intro = (
        f"<h1>{_h(content.title)}</h1><p><strong>{_h(c.name)}</strong> ({_h(c.ticker)}"
        f"{', ISIN ' + _h(c.isin) if c.isin else ''}) · {_h(', '.join(c.listings))}</p>"
        f'<p class="kind">Generated {content.generated_at:%Y-%m-%d %H:%M} UTC · listing '
        f"{_h(content.exchange or '—')} · basis {_h(content.basis or '—')} · engine "
        f"{_h(content.engine_version)}</p>"
    )
    body = "".join(_html_section(s) for s in content.sections)
    disclaimers = "<h2>Disclaimers</h2><ul>" + "".join(
        f"<li>{_h(d)}</li>" for d in content.disclaimers
    )
    return head + intro + body + disclaimers + "</ul></body></html>"


_FORMULA_START = ("=", "+", "-", "@", chr(9), chr(13))


def _cell(text: str) -> str:
    """Neutralize spreadsheet formula injection in text cells (OWASP CSV injection)."""
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def to_csv(content: ReportContent) -> str:
    """Every figure and table cell, one row each, with its provenance. Text cells are escaped
    against formula injection; the numeric ``value`` column is a plain decimal."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "item", "value", "display", "type", "period", "basis", "source"])
    for section in content.sections:
        for f in section.figures:
            writer.writerow(
                [
                    _cell(section.title),
                    _cell(f.label),
                    "" if f.value is None else f"{f.value:f}",
                    _cell(f.display),
                    f.kind,
                    _cell(f.period or ""),
                    f.basis or "",
                    _cell(f.source or ""),
                ]
            )
        for table in section.tables:
            for row in table.rows:
                writer.writerow(
                    [
                        _cell(section.title),
                        _cell(f"{table.caption}: {row[0]}"),
                        "",
                        _cell(" | ".join(row[1:])),
                        table.kind,
                        "",
                        "",
                        _cell(table.source or ""),
                    ]
                )
    return buffer.getvalue()
