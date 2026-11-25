"""Czech aviation regulations of the L series (Letecké předpisy řady L), published by the Letecká informační
služba (LIS) of ŘLP ČR at https://aim.rlp.cz/predpisy/predpisy/ (free public access under § 102(2) of Act
No. 49/1997 Coll.; only the printed AIP text is authentic).

The site is driven by small JavaScript data files:

    predpisy/data.js                         [{folder: "L", items: [{folder: "L-8", name: "L 8", title: ...}]}]
    predpisy/dokumenty/L/L-8/data.js         {name, title, link_print, alert: [{name: "Změna č. 109 - 3. 11. 2022"}],
                                              content: [{type: "link"|"tree", name, link | tree: [...]}]}

Every leaf is one PDF (a chapter: 'Část IIIA > Hlava 2', 'Doplněk 1', ...). Each chapter becomes one rule
('L 8 Část IIIA Hlava 2'); long chapters are split into parts like the ÚCL documents (ucl.split_parts).
Front matter (title page, contents, list of pages, amendment records) is skipped.

fetch:  data/raw/LPRED/index.json + <file key>.pdf
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .parse import ParsedBook, Rule
from .sources import Book

BASE = "https://aim.rlp.cz/predpisy/predpisy/"
TYPE_FULL = {"L": "Letecký předpis řady L (Czech national aviation regulation, based on the ICAO Annexes)"}
DOMAIN = "Letecké předpisy řady L (Czech national)"
SKIP = re.compile(r"^(?:titulní strana|úvodní strany?|obsah|seznam platných stran|záznam změn|záznamy? o změnách|"
                  r"změny a opravy|seznam změn)\b", re.I)


@dataclass
class LChapter:
    reg: str            # 'L 8'
    reg_title: str      # 'Letová způsobilost letadel'
    path: list[str]     # ['Část III', 'Část IIIA', 'Hlava 2']
    url: str            # absolute PDF url
    amendment: str      # 'Změna č. 109 - 3. 11. 2022'
    page: str           # the regulation's page on aim.rlp.cz

    @property
    def ref(self) -> str:
        """'L 8 Část IIIA Hlava 2' - nested 'Část III > Část IIIA' keeps only the innermost part."""
        path = list(self.path)
        while len(path) > 1 and path[1].startswith(path[0]) and path[1] != path[0]:
            path.pop(0)
        return " ".join([self.reg, *path])

    @property
    def key(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:12]


def _js_to_json(src: str) -> str:
    """Quote bare object keys, convert '…' strings, drop comments - only outside string literals."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch in "\"'":                               # string literal: copy (re-quoted as JSON)
            j, buf = i + 1, []
            while j < n and src[j] != ch:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            s = "".join(buf)
            out.append(json.dumps(s.replace("\\'", "'")) if ch == "'" else f'"{s}"')
            i = j + 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            i = src.find("*/", i + 2)
            i = n if i < 0 else i + 2
        elif ch.isalpha() or ch == "_":
            m = re.match(r"[A-Za-z_]\w*", src[i:])
            word = m.group(0)
            rest = src[i + len(word):].lstrip()
            out.append(f'"{word}"' if rest.startswith(":") else word)
            i += len(word)
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_data_js(text: str):
    """The site's data files are JavaScript literals: unquoted keys, trailing and empty commas."""
    body = _js_to_json(text[text.index("=") + 1:].strip().rstrip(";").strip())
    prev = None
    while prev != body:                               # ', ,' and '[ ,' and ', ]' -> valid JSON
        prev = body
        body = re.sub(r",(\s*,)", r"\1", body)
        body = re.sub(r"([\[{]\s*),", r"\1", body)
        body = re.sub(r",(\s*[}\]])", r"\1", body)
    return json.loads(body)


def _leaves(items: list, path: list[str]):
    for it in items or []:
        name = re.sub(r"\s+", " ", str(it.get("name", ""))).strip()
        if it.get("type") == "tree":
            yield from _leaves(it.get("tree"), path + [name])
        elif str(it.get("link", "")).lower().split("?")[0].endswith(".pdf"):   # skip .xlsx tables etc.
            yield path + [name], it["link"]


def chapters_from(reg_folder: str, data: dict, page: str) -> list[LChapter]:
    """Chapters of one regulation. PDF links are relative to the folder of its data.js (``page``'s folder);
    the 'folder' field inside data.js is not reliable ('L/L-6/I' for the folder L-6i)."""
    base = page.rsplit("/", 1)[0] + "/data/"
    amendment = ""
    for a in data.get("alert") or []:
        if re.match(r"\s*Změna", a.get("name", "")):
            amendment = re.sub(r"\s+", " ", a["name"]).strip()
            break
    out = []
    for path, link in _leaves(data.get("content"), []):
        if SKIP.match(path[-1]) and len(path) == 1:
            continue
        out.append(LChapter(reg=re.sub(r"\s+", " ", data.get("name", reg_folder)).strip(),
                            reg_title=re.sub(r"\s+", " ", data.get("title", "")).strip(), path=path,
                            url=base + urllib.parse.quote(link.strip().lstrip("./"), safe="/%-._~()"),
                            amendment=amendment, page=page))
    return out


def _get(url: str) -> str:
    from .fetch import UA
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")


def discover(groups: tuple[str, ...] = ("L",)) -> list[LChapter]:
    chapters: list[LChapter] = []
    for grp in parse_data_js(_get(BASE + "data.js")):
        if grp.get("folder") not in groups:
            continue
        for it in grp.get("items", []):
            page = f"{BASE}dokumenty/{grp['folder']}/{it['folder']}/index.htm"
            try:
                data = parse_data_js(_get(f"{BASE}dokumenty/{grp['folder']}/{it['folder']}/data.js"))
            except Exception as exc:                 # one broken data file must not stop the others
                print(f"[LIS] {it.get('name')}: data.js unreadable ({exc}) - skipped", file=sys.stderr, flush=True)
                continue
            chapters += chapters_from(it["folder"], data, page)
    return chapters


def fetch_book(book: Book, raw_dir: Path, download) -> Path:
    folder = raw_dir / book.code
    folder.mkdir(parents=True, exist_ok=True)
    chapters = discover()
    if not chapters:
        raise RuntimeError(f"[{book.code}] no chapters found - LIS site layout changed?")
    print(f"[{book.code}] {len(chapters)} chapters in {len({c.reg for c in chapters})} regulations", flush=True)
    kept = []
    for c in chapters:
        target = folder / f"{c.key}.pdf"
        try:
            if not target.exists():
                download(c.url, target, f"{book.code} {c.ref}", ("pdf", "octet-stream"))
            kept.append(c)
        except Exception as exc:
            print(f"[{book.code}] {c.ref}: download failed ({exc}) - skipped", file=sys.stderr, flush=True)
    (folder / "index.json").write_text(json.dumps([asdict(c) for c in kept], ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return folder


def load_index(folder: Path) -> list[LChapter]:
    return [LChapter(**d) for d in json.loads((folder / "index.json").read_text(encoding="utf-8"))]


def _rid(ref: str, part: int = 0) -> str:
    return "LIS-" + hashlib.sha1(ref.encode()).hexdigest()[:10].upper() + (f"-P{part}" if part else "")


def _amendment_date(amendment: str) -> str:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", amendment)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def reg_title(c: LChapter) -> str:
    return f"{c.reg} {c.reg_title}".strip()


def _heading(c: LChapter, body: str) -> str:
    """The chapter's own title: first substantial line that is not the running regulation/chapter label."""
    label = re.compile(rf"^(?:{re.escape(c.reg)}\b|PŘEDPIS\b|ČÁST\s+[IVX]+\w*$|HLAVA\s+\d+$|{re.escape(c.path[-1])}$)",
                       re.I)
    for ln in body.split("\n")[:12]:
        ln = ln.strip()
        if len(ln) > 6 and not label.match(ln) and not re.match(r"^(?:\d+[./-]){2}\d+|^Změna|^Opr", ln):
            return ln[:120]
    return ""


def overview_rule(book: Book, chapters: list[LChapter], titles: dict[str, str]) -> Rule:
    """One rule per regulation ('L 8/A') listing its chapters, so get_easa_rule('L 8/A') shows the structure."""
    c = chapters[0]
    lines = [f"Předpis: {reg_title(c)}", f"Zdroj: {c.page}"]
    if c.amendment:
        lines.append(f"Platné znění: {c.amendment}")
    lines.append("Kapitoly (get_easa_rule '<ref>'):")
    lines += [f"  {titles.get(ch.ref, ch.ref)}" for ch in chapters]
    return Rule(erules_id=_rid(c.reg), book=book.code, seq=0, title=reg_title(c), ref=c.reg, heading=c.reg_title,
                content_type="L", content_type_full=TYPE_FULL["L"], parent_ir="", regulatory_source=c.amendment,
                applicability_date="", entry_into_force_date=_amendment_date(c.amendment), domain=DOMAIN,
                keywords=reg_title(c), regulated_entity="", regulatory_subject="", icao_reference="",
                breadcrumb=" > ".join([book.title, reg_title(c)]), text="\n".join(lines))


def chapter_rules(book: Book, c: LChapter, body: str) -> list[Rule]:
    from .ucl import split_parts

    if len(body) < 200:
        body = (body + "\n\n" if body else "") + \
            "[PDF nemá použitelnou textovou vrstvu - otevřete odkaz na dokument výše.]"
    parts = split_parts(body)
    ref = c.ref
    heading = _heading(c, body)
    title = f"{ref} {heading}".strip() if heading else ref
    crumbs = [book.title, reg_title(c), *c.path[:-1]]
    date = _amendment_date(c.amendment)
    header = [f"Předpis: {c.reg} {c.reg_title}", f"Zdroj: {c.page}", f"Dokument: {c.url}"]
    if c.amendment:
        header.append(f"Platné znění: {c.amendment}")
    if len(parts) > 1:
        header.append("Části (get_easa_rule '<ref> (část N)'):\n" +
                      "\n".join(f"  část {n}: {h}" for n, (h, _) in enumerate(parts, 1)))

    def rule(n: int, rref: str, rtitle: str, text: str, parent: str, crumb: list[str]) -> Rule:
        return Rule(erules_id=_rid(ref, n), book=book.code, seq=0, title=rtitle, ref=rref, heading=heading,
                    content_type="L", content_type_full=TYPE_FULL["L"], parent_ir=parent,
                    regulatory_source=c.amendment, applicability_date="", entry_into_force_date=date, domain=DOMAIN,
                    keywords=f"{c.reg} {c.reg_title}", regulated_entity="", regulatory_subject="", icao_reference="",
                    breadcrumb=" > ".join(crumb), text=text)

    rules = [rule(0, ref, title, "\n".join(header) + "\n\n" + parts[0][1], reg_title(c), crumbs)]
    for n, (head, text) in enumerate(parts[1:], 2):
        rules.append(rule(n, f"{ref} (část {n})", f"{ref} – část {n}: {head}",
                          f"{title}, část {n}/{len(parts)}\nDokument: {c.url}\n\n{text}", title, crumbs + [ref]))
    return rules


def parse_lis_book(folder: Path, book: Book) -> ParsedBook:
    from .ucl import document_text

    chapters = load_index(folder)
    dates = sorted(d for d in (_amendment_date(c.amendment) for c in chapters) if d)
    parsed = ParsedBook(code=book.code, source_title=book.title, pub_time=f"{dates[-1]}T00:00:00Z" if dates else "")
    by_reg: dict[str, list[LChapter]] = {}
    for c in chapters:
        by_reg.setdefault(c.reg, []).append(c)
    for reg, chs in by_reg.items():
        rules: list[Rule] = []
        for c in chs:
            path = folder / f"{c.key}.pdf"
            if not path.exists():
                continue
            try:
                body = document_text(path)
            except Exception as exc:
                print(f"[{book.code}] {c.ref}: text extraction failed ({exc})", file=sys.stderr, flush=True)
                body = ""
            rules += chapter_rules(book, c, body)
        titles = {r.ref: r.title for r in rules}
        parsed.rules += [overview_rule(book, chs, titles), *rules]
    for n, r in enumerate(parsed.rules, 1):
        r.seq = n
    return parsed
