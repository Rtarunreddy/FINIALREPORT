"""Before/after comparison of the formatting a reader can see: fonts, sizes, alignment, spacing, margins.

Values are resolved through the style chain and document defaults, and weighted by characters of text, so a
single stray run does not dominate. Anything that cannot be resolved is reported as "Theme/default" rather than guessed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from .formatting import body_paragraphs, heading_level, runs, styles

ALIGN = {WD_ALIGN_PARAGRAPH.LEFT: "left", WD_ALIGN_PARAGRAPH.CENTER: "centered", WD_ALIGN_PARAGRAPH.RIGHT: "right", WD_ALIGN_PARAGRAPH.JUSTIFY: "justified"}


def _defaults(doc):
    root = doc.styles.element
    font = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts/@w:ascii")
    theme = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts/@w:asciiTheme")
    size = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:sz/@w:val")
    line = root.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:spacing/@w:line")
    return {"font": font[0] if font else ("Theme font" if theme else "Default"), "size": int(size[0]) / 2 if size else 10.0,
            "line": int(line[0]) / 240 if line else 1.0}


def _style_value(p, getter):
    for style in styles(p):
        value = getter(style)
        if value is not None: return value
    return None


def run_font(p, run, defaults):
    name = run.font.name or _style_value(p, lambda s: s.font.name)
    if not name and run._r.xpath("./w:rPr/w:rFonts/@w:asciiTheme"): name = "Theme font"
    size = run.font.size or _style_value(p, lambda s: s.font.size)
    return name or defaults["font"], (size.pt if size is not None else defaults["size"])


def para_align(p):
    value = p.alignment if p.alignment is not None else _style_value(p, lambda s: s.paragraph_format.alignment)
    return ALIGN.get(value, "left")


def para_line(p, defaults):
    value = p.paragraph_format.line_spacing
    if value is None: value = _style_value(p, lambda s: s.paragraph_format.line_spacing)
    if value is None: return f"{defaults['line']:g}×"
    return f"{value:g}×" if isinstance(value, float) else f"{value.pt:g} pt exact"


def collect(path: Path) -> dict:
    doc = Document(path); defaults = _defaults(doc)
    body = {"fonts": Counter(), "sizes": Counter(), "align": Counter(), "line": Counter(), "combos": Counter()}
    heads = {1: {"fonts": Counter(), "sizes": Counter()}, 2: {"fonts": Counter(), "sizes": Counter()}, 3: {"fonts": Counter(), "sizes": Counter()}}
    for p in body_paragraphs(doc):
        align, line = para_align(p), para_line(p, defaults); weight = 0
        for r in runs(p):
            if not r.text.strip(): continue
            font, size = run_font(p, r, defaults); n = len(r.text); weight += n
            body["fonts"][font] += n; body["sizes"][size] += n; body["combos"][(font, size, align, line)] += n
        if weight: body["align"][align] += weight; body["line"][line] += weight
    for p in doc.paragraphs:
        level = heading_level(p)
        if level and p.text.strip():
            for r in runs(p):
                if r.text.strip():
                    font, size = run_font(p, r, defaults); heads[level]["fonts"][font] += len(r.text); heads[level]["sizes"][size] += len(r.text)
    section = doc.sections[0]
    inches = lambda v: round(v.inches, 2) if v is not None else None
    return {"body": body, "headings": heads, "margins": {k: inches(getattr(section, k + "_margin")) for k in ("top", "bottom", "left", "right")}}


def _list(counter: Counter, fmt=str, limit=3) -> str:
    if not counter: return "—"
    items = [fmt(k) for k, _ in counter.most_common()]
    return ", ".join(items[:limit]) + (f" +{len(items) - limit} more" if len(items) > limit else "")


def _pt(value: float) -> str: return f"{value:g} pt"


def _margins(m: dict) -> str:
    return " · ".join(f"{k} {m[k]:g}″" for k in ("top", "bottom", "left", "right") if m[k] is not None) or "—"


def summarize(before_path: Path, after_path: Path) -> dict:
    a, b = collect(before_path), collect(after_path)
    rows, highlights = [], []

    def row(label, before, after, count_before=None, count_after=None, noun=None):
        rows.append({"label": label, "before": before, "after": after, "changed": before != after})
        if count_before is not None and count_after is not None and count_after < count_before and noun:
            highlights.append(f"{noun}: {count_before} → {count_after}")

    for key, label, fmt, noun in (("fonts", "Body fonts", str, "Different body fonts"), ("sizes", "Body sizes", _pt, "Different body sizes"),
                                  ("align", "Body alignment", str, "Different body alignments"), ("line", "Line spacing", str, "Different line spacings")):
        row(label, _list(a["body"][key], fmt), _list(b["body"][key], fmt), len(a["body"][key]), len(b["body"][key]), noun)
    ca, cb = len(a["body"]["combos"]), len(b["body"]["combos"])
    if ca > cb and cb: highlights.insert(0, f"Body text now uses {cb} formatting combination{'s' if cb != 1 else ''} instead of {ca}")
    for level in (1, 2, 3):
        ha, hb = a["headings"][level], b["headings"][level]
        if not ha["fonts"] and not hb["fonts"]: continue
        row(f"Heading {level}", f"{_list(ha['fonts'], limit=2)} · {_list(ha['sizes'], _pt, 2)}", f"{_list(hb['fonts'], limit=2)} · {_list(hb['sizes'], _pt, 2)}")
    row("Page margins", _margins(a["margins"]), _margins(b["margins"]))
    return {"rows": rows, "highlights": highlights, "bodyCombinations": {"before": ca, "after": cb}}
