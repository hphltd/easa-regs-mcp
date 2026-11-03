"""Turn PDF-only EASA documents into rule records.

Two ways of splitting (``Book.split``):

``doc``  one rule per document - Special Conditions, Equivalent Safety Findings, Deviations,
         Certification Memoranda. These are short and are cited as a whole ('SC-22.2014-01').
``cs``   one rule per paragraph of a certification specification - 'CS 22.143', 'AMC 22.629'.
         Each paragraph runs from its heading line to the next heading. Headings also appear in the
         table of contents, so for every reference only the occurrence with the longest text is kept.

Running page headers and footers (lines repeated on many pages) are dropped before splitting.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .parse import ParsedBook, Rule, norm_ref
from .sources import Book, PdfDoc

TYPE_FULL = {
    "CS": "Certification Specification",
    "AMC": "Acceptable Means of Compliance",
    "GM": "Guidance Material",
    "SC": "Special Condition",
    "ESF": "Equivalent Safety Finding",
    "DEV": "Deviation",
    "CM": "Certification Memorandum",
}

_PAGE_LINE = re.compile(r"^(?:page\s*)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$|^\d{1,4}$", re.I)
# 'CS 22.143 General', 'AMC 22.629 Flutter', 'CS 22.335(a) ...', 'GM 22.1 ...'
_CS_HEADING = re.compile(r"^(?P<ref>(?:CS|AMC|GM)\s?(?P<num>\d{2}\.\d+[A-Z]?)(?:\s?\([a-z0-9]+\))*)(?:\s+(?P<head>.*))?$")
_APPENDIX = re.compile(r"^(?P<ref>APPENDIX\s+[A-Z0-9]{1,3})\b[\s:–—-]*(?P<head>.*)$")
_SUBPART = re.compile(r"^SUBPART\s+[A-Z]\b.*$")
_BOOKPART = re.compile(r"^BOOK\s+[12]\b.*$", re.I)
_DOT_LEADER = re.compile(r"\s*\.{3,}.*$|\s+\d+(?:-[A-Z]+-\d+)?$")


def extract_pages(path: Path) -> list[str]:
    from pdfminer.high_level import extract_text  # build-time dependency only
    return extract_text(str(path)).split("\f")


_PAGE_REF = re.compile(r"\bpage\s*\d+(?:\s*(?:of|/)\s*\d+)?\b", re.I)


def _running_key(line: str) -> str:
    """'CS-22 Amendment 3   Page 12 of 160' and '... Page 13 of 160' are the same running header."""
    return _PAGE_REF.sub("", line).strip()


def clean_lines(pages: list[str]) -> list[str]:
    """All lines of the document without running headers/footers and page numbers."""
    per_page = [[ln.strip() for ln in p.splitlines()] for p in pages]
    seen_on: Counter[str] = Counter()
    for lines in per_page:
        seen_on.update({_running_key(ln) for ln in lines if ln})
    limit = max(3, int(0.3 * len(pages)))
    out: list[str] = []
    for lines in per_page:
        for ln in lines:
            if not ln:
                if out and out[-1]:
                    out.append("")
                continue
            if _PAGE_LINE.match(ln) or not _running_key(ln):
                continue
            if (len(ln) < 150 and len(pages) >= 4 and seen_on[_running_key(ln)] >= limit
                    and not _CS_HEADING.match(ln)):
                continue
            out.append(ln)
    return out


def reflow(lines: list[str]) -> str:
    """Join soft-wrapped lines; keep paragraph breaks and list items '(a)', '1.', bullets."""
    paras: list[str] = []
    for ln in lines:
        if not ln:
            paras.append("")
            continue
        new_item = re.match(r"^(?:\([a-z0-9ivx]+\)|\d+(?:\.\d+)*\.?\s|[•▪–-]\s)", ln)
        if paras and paras[-1] and not new_item and (ln[0].islower() or paras[-1][-1] not in ".:;!?"):
            if paras[-1].endswith("-") and ln[0].islower():
                paras[-1] = paras[-1][:-1] + ln
            else:
                paras[-1] += " " + ln
        else:
            paras.append(ln)
    text = "\n".join(paras)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _rule(book: Book, doc: PdfDoc, seq: int, ref: str, title: str, heading: str, ctype: str, text: str,
          crumbs: list[str], parent: str = "") -> Rule:
    return Rule(
        erules_id=f"EASA-DL-{doc.download_id}-{norm_ref(ref)}" if book.split == "cs" else f"EASA-DL-{doc.download_id}",
        book=book.code,
        seq=seq,
        title=title,
        ref=ref,
        heading=heading,
        content_type=ctype,
        content_type_full=TYPE_FULL.get(ctype, ctype),
        parent_ir=parent,
        regulatory_source=doc.issue if book.split == "cs" else "",   # citation says 'as amended by ...'
        applicability_date="",
        entry_into_force_date=doc.date,
        domain="Initial airworthiness",
        keywords="",
        regulated_entity="",
        regulatory_subject="",
        icao_reference="",
        breadcrumb=" > ".join(crumbs),
        text=text,
    )


def split_docs(book: Book, texts: dict[int, str]) -> list[Rule]:
    rules = []
    for doc in book.docs:
        body = texts.get(doc.download_id, "")
        if len(body) < 200:                # scanned PDF without a text layer: keep the entry, point to the file
            print(f"[{book.code}] {doc.ref}: no usable text layer ({len(body)} chars)", flush=True)
            body = (body + "\n\n" if body else "") + \
                "[The PDF has no usable text layer (scanned document) - open the document link above.]"
        title = f"{doc.ref} {doc.title}" + (f" ({doc.issue})" if doc.issue else "")
        header = f"Source: {doc.page}\nDocument: {doc.url}\n\n"
        rules.append(_rule(book, doc, len(rules) + 1, doc.ref, title, doc.title, doc.content_type, header + body,
                           [book.title, TYPE_FULL.get(doc.content_type, doc.content_type)]))
    return rules


def split_cs(book: Book, doc: PdfDoc, lines: list[str]) -> list[Rule]:
    """Split a certification specification into CS / AMC / GM paragraphs and appendices."""
    marks: list[tuple[int, str, str, str, list[str]]] = []   # (line index, ref, heading, type, crumbs)
    part, subpart = "", ""
    for i, ln in enumerate(lines):
        if _BOOKPART.match(ln):
            part, subpart = re.sub(r"\s+", " ", ln), ""
            continue
        if _SUBPART.match(ln):
            subpart = _DOT_LEADER.sub("", re.sub(r"\s+", " ", ln))
            continue
        m = _CS_HEADING.match(ln) or _APPENDIX.match(ln)
        if not m or len(ln) > 110 or ln.endswith((",", ";")):
            continue
        head = _DOT_LEADER.sub("", (m.group("head") or "").strip())
        if head and not (head[0].isupper() or head[0] in "(–—-"):
            continue                       # 'CS 22.143 and ...' wrapped in running text
        ref = re.sub(r"\s+", " ", m.group("ref")).strip()
        if ref.upper().startswith("APPENDIX"):
            ref = ("AMC " if part.lower().startswith("book 2") else "") + "Appendix " + ref.split()[-1] + " to CS-22"
            ctype = "AMC" if ref.startswith("AMC") else "CS"
        else:
            ref = re.sub(r"^(CS|AMC|GM)\s?", r"\1 ", ref)
            ctype = ref.split()[0]
        marks.append((i, ref, head.lstrip("–—- "), ctype, [c for c in (book.title, part, subpart) if c]))

    best: dict[str, tuple[int, str, str, str, list[str], list[str]]] = {}
    order: list[str] = []
    for k, (i, ref, head, ctype, crumbs) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        body = lines[i + 1:end]
        if not head and body and body[0] and len(body[0]) < 100 and body[0][0].isupper():
            head, body = _DOT_LEADER.sub("", body[0]), body[1:]
        key = norm_ref(ref)
        if key not in best:
            order.append(key)
        if key not in best or len("".join(body)) > len("".join(best[key][5])):
            best[key] = (i, ref, head, ctype, crumbs, body)

    cs_titles = {}
    for key in order:
        _, ref, head, ctype, _, _ = best[key]
        if ctype == "CS":
            cs_titles.setdefault(ref.split()[1].split("(")[0], f"{ref} {head}".strip())
    rules = []
    for key in sorted(order, key=lambda k: best[k][0]):
        _, ref, head, ctype, crumbs, body = best[key]
        text = reflow(body)
        if len(text) < 20:                 # table-of-contents entry with no real counterpart
            continue
        parent = cs_titles.get(ref.split()[1].split("(")[0], "") if ctype in ("AMC", "GM") else ""
        rules.append(_rule(book, doc, len(rules) + 1, ref, f"{ref} {head}".strip(), head, ctype, text, crumbs,
                           parent))
    return rules


def parse_pdf_book(folder: Path, book: Book) -> ParsedBook:
    dates = sorted(d.date for d in book.docs if d.date)
    parsed = ParsedBook(code=book.code, source_title=book.title, pub_time=(dates[-1] + "T00:00:00Z") if dates else "")
    if book.split == "cs":
        for doc in book.docs:
            parsed.rules += split_cs(book, doc, clean_lines(extract_pages(folder / f"{doc.download_id}.pdf")))
        for n, r in enumerate(parsed.rules, 1):
            r.seq = n
    else:
        texts = {d.download_id: reflow(clean_lines(extract_pages(folder / f"{d.download_id}.pdf")))
                 for d in book.docs if (folder / f"{d.download_id}.pdf").exists()}
        missing = [d.ref for d in book.docs if d.download_id not in texts]
        if missing:
            raise FileNotFoundError(f"{book.code}: PDF missing for {', '.join(missing)} - run easa-regs-fetch")
        parsed.rules = split_docs(book, texts)
    return parsed
