"""JAR-22 (Joint Aviation Requirements, Sailplanes and Powered Sailplanes) from a JAA PDF.

JAR-22 is superseded by CS-22 but remains in the certification basis of older types. There is no official public
source any more (the JAA closed in 2009), so the PDF is supplied locally: data/raw/JAR22/jar22.pdf. Without it
the book is skipped (fetch never downloads it).

Layout of the JAA edition (Amendment 6, 2001): two text columns per page; requirement text in Times-Roman with
'JAR 22.xxx Title' headings in Helvetica-Bold; the AMC for a paragraph is printed inline right after the
sub-paragraph it explains, in Times-Italic with an 'AMC 22.xxx' heading in Helvetica-Oblique. A requirement
continued on the next column/page starts with 'JAR 22.xxx (continued)'. So text is assigned by font, not only by
position: italic lines belong to the open AMC, roman lines to the open JAR paragraph - even when an AMC was printed
in between. Justified lines come out of pdfminer in fragments; fragments on the same baseline are re-joined.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .parse import ParsedBook, Rule, norm_ref
from .sources import Book

TYPE_FULL = {
    "JAR": "Joint Aviation Requirement (JAR-22, superseded by CS-22; binding where it is part of a type's "
           "certification basis)",
    "AMC": "Acceptable Means of Compliance (JAR-22)",
}
_JAR_HEAD = re.compile(r"^JAR\s?22\.(\d+[A-Z]?)\b\s*(.*)$")
_AMC_HEAD = re.compile(r"^(?:AMC|ACJ)\s?22\.(\d+[A-Z]?)(.*)$")
_APPENDIX = re.compile(r"^APPENDIX\s+([A-Z0-9]{1,2})\b[\s:–—-]*(.*)$", re.I)
_CONTINUED = re.compile(r"\(continued\)\s*$", re.I)
_RUNNING = re.compile(r"^(?:JAR-22|Amendment\s+\d+|Change\s+\d+|Subpart\s+[A-Z]|Section\s+\d|[A-Z]{1,2}-?\d{1,3}|"
                      r"\d{2}\.\d{2}\.\d{2}|INTENTIONALLY LEFT BLANK|P)$", re.I)


@dataclass
class Line:
    text: str
    font: str
    size: float
    x0: float


@dataclass
class Section:
    ref: str
    ctype: str
    heading: str
    crumbs: list[str]
    lines: list[str] = field(default_factory=list)


def _style(line: Line) -> str:
    f = line.font
    if "Helvetica" in f or "Arial" in f:
        if "Bold" in f:
            return "head"
        if "Oblique" in f or "Italic" in f:
            return "amc_head"
        return "small"
    if "Italic" in f:
        return "amc"
    return "text"


def page_lines(path: Path) -> list[list[Line]]:
    """Per page: lines in reading order (left column, then right), with justified fragments re-joined."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTTextLine

    def text_lines(o):
        if isinstance(o, LTTextLine):
            yield o
        elif hasattr(o, "__iter__"):
            for c in o:
                yield from text_lines(c)

    pages = []
    for page in extract_pages(str(path), laparams=LAParams(line_margin=0.3)):
        mid = page.width / 2
        cols: dict[int, list] = {0: [], 1: []}
        for ln in text_lines(page):
            if ln.get_text().strip() in ("", "P"):    # 'P' = change bar marker in the margin
                continue
            cols[0 if (ln.x0 + ln.x1) / 2 < mid else 1].append(ln)
        out = []
        for col in (0, 1):
            rows: list[list] = []
            for ln in sorted(cols[col], key=lambda l: (-round(l.y0), l.x0)):
                if rows and abs(rows[-1][0].y0 - ln.y0) <= 2.5:
                    rows[-1].append(ln)
                else:
                    rows.append([ln])
            for row in rows:
                row.sort(key=lambda l: l.x0)
                text = re.sub(r"\s+", " ", " ".join(l.get_text().strip() for l in row)).strip()
                chars = [c for l in row for c in l if isinstance(c, LTChar) and c.get_text().strip()]
                font, size = Counter((c.fontname.split("+")[-1], round(c.size, 1)) for c in chars).most_common(1)[0][0] \
                    if chars else ("", 0.0)
                out.append(Line(text, font, size, row[0].x0))
        pages.append(out)
    return pages


def split_sections(pages: list[list[Line]]) -> list[Section]:
    sections: dict[str, Section] = {}
    order: list[str] = []
    jar: Section | None = None
    amc: Section | None = None
    group = ""
    pending_head: Section | None = None     # a JAR heading may wrap over several bold lines

    def open_section(ref: str, ctype: str, heading: str) -> Section:
        key = norm_ref(ref)
        if key not in sections:
            sections[key] = Section(ref, ctype, heading, [c for c in (group,) if c])
            order.append(key)
        elif heading and not sections[key].heading:
            sections[key].heading = heading
        return sections[key]

    started = False
    for lines in pages:
        for ln in lines:
            t, style = ln.text, _style(ln)
            if not t or (_RUNNING.match(t) and style in ("small", "head") and ln.size != 10.0):
                continue
            if style == "head" and t == "P":          # change bar marker in the margin
                continue
            m_jar, m_amc, m_app = _JAR_HEAD.match(t), _AMC_HEAD.match(t), _APPENDIX.match(t)
            if m_jar and _CONTINUED.search(t):        # 'JAR 22.221 (continued)'
                jar = open_section(f"JAR 22.{m_jar.group(1)}", "JAR", "")
                pending_head = None
                started = True
                continue
            if m_amc and _CONTINUED.search(t):
                amc = open_section(f"AMC 22.{m_amc.group(1)}{_amc_suffix(m_amc.group(2))}", "AMC", "")
                continue
            if style == "head" and m_jar:
                started = True
                jar = open_section(f"JAR 22.{m_jar.group(1)}", "JAR", m_jar.group(2).strip())
                amc, pending_head = None, jar
                continue
            if style == "head" and t.isupper() and len(t) < 80 and not (m_jar or m_app):
                group, pending_head = t, None         # group heading: 'GROUND HANDLING CHARACTERISTICS'
                continue
            if not started:                           # cover, contents, preamble
                continue
            if style == "amc_head" and m_amc:
                ref = f"AMC 22.{m_amc.group(1)}{_amc_suffix(m_amc.group(2))}"
                amc = open_section(ref, "AMC", "")
                pending_head = None
                continue
            if style == "head" and m_app:
                jar = open_section(f"Appendix {m_app.group(1).upper()} to JAR-22", "JAR", m_app.group(2).strip())
                amc, pending_head = None, jar
                continue
            if style == "head":
                if pending_head is not None:
                    pending_head.heading = f"{pending_head.heading} {t}".strip()   # wrapped heading
                continue
            pending_head = None
            if style == "amc" and amc is not None:
                amc.lines.append(t)
            elif style in ("text", "amc") and jar is not None:
                jar.lines.append(t)
            elif style == "small" and jar is not None and t.startswith("["):
                jar.lines.append(t)
    return [sections[k] for k in order]


def _amc_suffix(rest: str) -> str:
    """'AMC 22.221(b)' / 'AMC 22.221(c),(d),(e) and (f)' -> keep the paragraph reference as printed."""
    rest = rest.strip()
    m = re.match(r"^((?:\([a-z0-9]+\))+(?:\s*(?:,|and)\s*\([a-z0-9]+\))*)", rest)
    return m.group(1).replace(" ", "") if m else ""


def parse_jar_book(folder: Path, book: Book) -> ParsedBook:
    from .pdfbook import reflow

    doc = book.docs[0]
    path = folder / (doc.file or "jar22.pdf")
    if not path.exists():
        raise FileNotFoundError(f"{book.code}: {path} not found - JAR-22 is not downloadable, place the PDF there")
    sections = split_sections(page_lines(path))
    titles = {s.ref.split()[1].split("(")[0]: f"{s.ref} {s.heading}".strip() for s in sections if s.ctype == "JAR"}
    parsed = ParsedBook(code=book.code, source_title=book.title, pub_time=f"{doc.date}T00:00:00Z" if doc.date else "")
    for s in sections:
        text = reflow(s.lines)
        if len(text) < 20:
            continue
        num = s.ref.split()[1].split("(")[0] if s.ref.startswith(("JAR ", "AMC ")) else ""
        parent = titles.get(num, "") if s.ctype == "AMC" else ""
        title = f"{s.ref} {s.heading}".strip() if s.ctype == "JAR" else (f"{s.ref} – {titles[num]}" if num in titles
                                                                         else s.ref)
        parsed.rules.append(Rule(
            erules_id=f"JAR22-{norm_ref(s.ref).upper()}", book=book.code, seq=len(parsed.rules) + 1, title=title,
            ref=s.ref, heading=s.heading, content_type=s.ctype, content_type_full=TYPE_FULL[s.ctype],
            parent_ir=parent, regulatory_source=doc.issue, applicability_date="", entry_into_force_date=doc.date,
            domain="Initial airworthiness", keywords="JAR-22 sailplanes powered sailplanes",
            regulated_entity="", regulatory_subject="", icao_reference="",
            breadcrumb=" > ".join(c for c in (book.title, *s.crumbs) if c), text=text))
    return parsed
