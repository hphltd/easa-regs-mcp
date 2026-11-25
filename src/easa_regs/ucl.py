"""Czech Civil Aviation Authority (Úřad pro civilní letectví, ÚCL) directives and advisory circulars.

ÚCL publishes them as PDFs linked from two WordPress pages (``Book.listing``):

    https://www.caa.gov.cz/dokumenty/predpisy/smernice-ucl/        Směrnice ÚCL (directives)
    https://www.caa.gov.cz/dokumenty/predpisy/poradni-obezniky/    Poradní oběžníky (advisory circulars)

Each entry is ``<a href="...pdf">Směrnice CAA-TI-010-n/99 Title</a><br>description...``. The list is read from
the page on every fetch, so new and revised documents are picked up without code changes. File URLs change
with every revision (``/wp-content/uploads/<year>/<month>/...``); the document reference does not, so rule
ids are derived from the reference.

fetch:  data/raw/<CODE>/index.json + <file key>.pdf
build:  one rule per document; long documents are split into parts at headings (``<ref> (část N)``),
        linked to the document rule like AMC/GM to their IR.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from .parse import ParsedBook, Rule
from .sources import Book

TYPE_FULL = {
    "SM": "Směrnice ÚCL (directive of the Czech Civil Aviation Authority)",
    "PO": "Poradní oběžník ÚCL (advisory circular of the Czech Civil Aviation Authority, not binding)",
}
DOMAIN = "Národní dokumenty ÚCL (Czech national)"

SINGLE_MAX = 20000      # documents up to this length stay one rule
PART_TARGET = 9000      # otherwise cut at the next heading once a part has this many characters
PART_MAX = 16000        # ... or at the next paragraph once it has this many


@dataclass
class UclDoc:
    ref: str            # 'CAA-TI-010-n/99', 'PO/ST-20-6', 'ÚCL-237'
    title: str
    section: str        # heading on the listing page the entry sits under
    summary: str        # ÚCL's description under the link
    url: str            # absolute PDF url (without cache-busting query)
    date: str           # upload month from the url path, 'yyyy-mm' ('' if unknown)

    @property
    def key(self) -> str:
        """File name of the downloaded PDF (stable for one url)."""
        return hashlib.sha1(self.url.encode()).hexdigest()[:12]


# ------------------------------------------------------------------------------------------- listing page

class _Listing(HTMLParser):
    """Collects (section, link text, href, text after the link) for every PDF link on the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[dict] = []
        self.section = ""
        self._in_heading = False
        self._heading: list[str] = []
        self._link: dict | None = None
        self._after: dict | None = None   # entry whose description is being collected
        self._stop = False

    def handle_starttag(self, tag, attrs):
        if self._stop:
            return
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if "plane-right" in (a.get("class") or ""):   # page footer
                self._stop = True
                return
            self._in_heading, self._heading, self._after = True, [], None
        elif tag == "a":
            self._after = None
            href = a.get("href") or ""
            if urllib.parse.urlsplit(href).path.lower().endswith(".pdf"):
                self._link = {"section": self.section, "href": href, "text": [], "after": []}
        elif tag == "br" and self._after is not None:
            self._after["after"].append("\n")
        elif tag in ("p", "li", "div", "table", "ul", "ol"):
            self._after = None                        # a new block ends the previous description

    def handle_endtag(self, tag):
        if self._stop:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._in_heading:
            self._in_heading = False
            text = _clean(" ".join(self._heading))
            if text:
                self.section = text
        elif tag == "a" and self._link is not None:
            self.entries.append(self._link)
            self._after, self._link = self._link, None
        elif tag in ("p", "li") and self._after is not None:
            self._after = None

    def handle_data(self, data):
        if self._stop:
            return
        if self._in_heading:
            self._heading.append(data)
        elif self._link is not None:
            self._link["text"].append(data)
        elif self._after is not None:
            self._after["after"].append(data)


def _clean(s: str) -> str:
    s = html.unescape(s).replace("﻿", "").replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


_LEADING_WORD = re.compile(r"^(?:Směrnice|Smernice)\s+", re.I)
_DASH = re.compile(r"\s*[–—]\s*|\s+-\s+|\s+-(?=\S)")


def _ref_token(tok: str) -> bool:
    return bool(re.search(r"[\d/]", tok) or re.fullmatch(r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{1,5}(?:-[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{1,5})*", tok)
                or tok in ("Část", "Part"))


def _first_sentence(s: str, limit: int = 160) -> str:
    m = re.match(r"(.+?[a-zá-ž0-9)“\"])\.(?:\s|$)", s)
    s = m.group(1) if m else s.rstrip(".")
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + " …"


def split_ref(text: str) -> tuple[str, str]:
    """'PO/TI – 20 – 1 Příručka pro …' -> ('PO/TI-20-1', 'Příručka pro …').

    The reference is the leading run of code-like tokens (digits, '/', short upper-case words); dashes inside
    it are normalised. Returns ('', text) if the text does not start with a reference.
    """
    text = _LEADING_WORD.sub("", _clean(text))
    parts = _DASH.split(text)                       # dash-separated pieces, each may hold several words
    ref, rest = [], []
    for i, piece in enumerate(parts):
        words = piece.split(" ")
        n = 0
        while n < len(words) and words[n] and _ref_token(words[n]):
            n += 1
        if n:
            ref.append(" ".join(words[:n]))
        if n < len(words):
            rest = [" ".join(words[n:]).strip()] + parts[i + 1:]
            break
    title = " – ".join(r for r in rest if r).strip(" –-,")
    return "-".join(ref).strip("-").rstrip("."), title


def parse_listing(page: str, base_url: str) -> list[UclDoc]:
    p = _Listing()
    p.feed(page)
    docs: list[UclDoc] = []
    seen: set[str] = set()
    for e in p.entries:
        url = urllib.parse.urljoin(base_url, e["href"])
        parts = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                                                     query="", fragment=""))
        if url in seen:
            continue
        seen.add(url)
        text = _clean(" ".join(e["text"]))
        after = [_clean(x) for x in "".join(e["after"]).split("\n")]
        after = [x for x in after if x]
        ref, title = split_ref(text)
        if not ref:
            if not docs:                             # nothing to attach to: use the link text itself
                ref, title = text, ""
            else:                                    # attachment of the previous document ('… – vzor')
                prev = docs[-1]
                n = sum(1 for d in docs if d.ref.startswith(prev.ref.split(" příloha")[0] + " příloha")) + 1
                ref, title = f"{prev.ref.split(' příloha')[0]} příloha {n}", text
        if ref in {d.ref for d in docs}:
            ref = f"{ref} ({len([d for d in docs if d.ref.startswith(ref)]) + 1})"
        summary = " ".join(after)
        note = ""
        if re.fullmatch(r"\(.*\)", title):            # '(verze 6.1)' is a version note, not a title
            note, title = title, ""
        if not title and after and re.fullmatch(r"\(.*\)", after[0]):
            note = after.pop(0)
        if not title and after:                       # 'Směrnice CAA/S-SP-028-4/2020' + title on the next line
            title = _first_sentence(after[0])
        title = f"{title} {note}".strip()
        m = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
        docs.append(UclDoc(ref=ref, title=title, section=e["section"], summary=summary, url=url,
                           date=f"{m.group(1)}-{m.group(2)}" if m else ""))
    return docs


# ----------------------------------------------------------------------------------------------- fetching

def fetch_book(book: Book, raw_dir: Path, download) -> Path:
    """Read the listing page(s), download every PDF, write index.json. ``download(url, target, label, accept)``."""
    import urllib.request

    from .fetch import UA

    folder = raw_dir / book.code
    folder.mkdir(parents=True, exist_ok=True)
    docs: list[UclDoc] = []
    for page_url in book.listing:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")
        found = parse_listing(page, page_url)
        print(f"[{book.code}] {page_url}: {len(found)} documents", flush=True)
        docs += found
    if not docs:
        raise RuntimeError(f"[{book.code}] no PDF links found - ÚCL page layout changed?")
    kept = []
    for d in docs:
        target = folder / f"{d.key}.pdf"
        try:
            if not target.exists():
                download(d.url, target, f"{book.code} {d.ref}", ("pdf", "octet-stream"))
            kept.append(d)
        except Exception as exc:                     # one broken link must not stop the weekly update
            print(f"[{book.code}] {d.ref}: download failed ({exc}) - skipped", file=sys.stderr, flush=True)
    (folder / "index.json").write_text(json.dumps([asdict(d) for d in kept], ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return folder


def load_index(folder: Path) -> list[UclDoc]:
    return [UclDoc(**d) for d in json.loads((folder / "index.json").read_text(encoding="utf-8"))]


# ------------------------------------------------------------------------------------------------ parsing

_DOT_LEADER_LINE = re.compile(r"\.{5,}|…{2,}")
_HEADING = re.compile(
    r"^(?:(?:Článek|Čl\.|Kapitola|KAPITOLA|Hlava|HLAVA|Část|ČÁST|Oddíl|ODDÍL|Příloha|PŘÍLOHA|Dodatek|DODATEK)"
    r"\s+[\w.]+|\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]|[IVX]{1,5}\.\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])")


def split_parts(text: str) -> list[tuple[str, str]]:
    """Split a long document into (heading, text) parts; short documents come back as one part."""
    if len(text) <= SINGLE_MAX:
        return [("", text)]
    parts: list[tuple[str, list[str]]] = [("", [])]
    size = 0
    for para in text.split("\n"):
        heading = bool(_HEADING.match(para)) and len(para) > 3
        if parts[-1][1] and ((size >= PART_TARGET and heading) or size >= PART_MAX):
            parts.append((para[:100] if heading else "", []))
            size = 0
        parts[-1][1].append(para)
        size += len(para) + 1
    out = []
    for head, paras in parts:
        body = "\n".join(paras).strip()
        if body:
            out.append((head or body.split("\n", 1)[0][:100], body))
    if len(out) > 1 and len(out[-1][1]) < 1500:      # fold a short tail into the previous part
        h, b = out.pop()
        out[-1] = (out[-1][0], out[-1][1] + "\n" + b)
    return out


def document_text(path: Path) -> str:
    from .pdfbook import clean_lines, extract_pages, reflow

    lines = [ln for ln in clean_lines(extract_pages(path)) if not _DOT_LEADER_LINE.search(ln)]
    return re.sub(r"[ \t]{2,}", " ", reflow(lines))     # justified text comes out with runs of spaces


def _rid(book: Book, ref: str, part: int = 0) -> str:
    h = hashlib.sha1(ref.encode()).hexdigest()[:10].upper()
    return f"UCL-{book.code}-{h}" + (f"-P{part}" if part else "")


def doc_rules(book: Book, doc: UclDoc, body: str, seq0: int = 0) -> list[Rule]:
    ctype = book.content_type
    if len(body) < 200:                              # scanned PDF without a text layer
        print(f"[{book.code}] {doc.ref}: no usable text layer ({len(body)} chars)", flush=True)
        body = (body + "\n\n" if body else "") + \
            "[PDF nemá použitelnou textovou vrstvu (sken) - otevřete odkaz na dokument výše.]"
    parts = split_parts(body)
    title = f"{doc.ref} {doc.title}".strip()
    crumbs = [c for c in (book.title, doc.section) if c and c != book.title]
    header = [f"Zdroj: {', '.join(book.listing)}", f"Dokument: {doc.url}"]
    if doc.date:
        header.append(f"Zveřejněno na webu ÚCL: {doc.date}")
    if doc.summary:
        header.append(f"Popis (ÚCL): {doc.summary}")
    if len(parts) > 1:
        header.append("Části dokumentu (get_easa_rule '<ref> (část N)'):\n" +
                      "\n".join(f"  část {n}: {h}" for n, (h, _) in enumerate(parts, 1)))

    def rule(n: int, ref: str, rtitle: str, text: str, parent: str, crumb: list[str]) -> Rule:
        return Rule(erules_id=_rid(book, doc.ref, n), book=book.code, seq=seq0 + n + 1, title=rtitle, ref=ref,
                    heading=doc.title, content_type=ctype, content_type_full=TYPE_FULL[ctype], parent_ir=parent,
                    regulatory_source="", applicability_date="", entry_into_force_date=doc.date, domain=DOMAIN,
                    keywords=doc.section, regulated_entity="", regulatory_subject="", icao_reference="",
                    breadcrumb=" > ".join([book.title, *crumb]), text=text)

    rules = [rule(0, doc.ref, title, "\n".join(header) + "\n\n" + parts[0][1], "", crumbs)]
    for n, (head, text) in enumerate(parts[1:], 2):
        rules.append(rule(n, f"{doc.ref} (část {n})", f"{doc.ref} – část {n}: {head}",
                          f"{title}, část {n}/{len(parts)}\nDokument: {doc.url}\n\n{text}", title,
                          crumbs + [doc.ref]))
    return rules


def parse_ucl_book(folder: Path, book: Book) -> ParsedBook:
    docs = load_index(folder)
    dates = sorted(d.date for d in docs if d.date)
    parsed = ParsedBook(code=book.code, source_title=book.title,
                        pub_time=f"{dates[-1]}-01T00:00:00Z" if dates else "")
    for d in docs:
        path = folder / f"{d.key}.pdf"
        if not path.exists():
            print(f"[{book.code}] {d.ref}: PDF missing - skipped", file=sys.stderr, flush=True)
            continue
        try:
            body = document_text(path)
        except Exception as exc:                     # a damaged PDF must not drop the whole book
            print(f"[{book.code}] {d.ref}: text extraction failed ({exc})", file=sys.stderr, flush=True)
            body = ""
        parsed.rules += doc_rules(book, d, body, len(parsed.rules))
    for n, r in enumerate(parsed.rules, 1):
        r.seq = n
    return parsed
