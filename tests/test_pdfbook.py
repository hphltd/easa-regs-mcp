"""PDF books (CS-22 Amendment 3, Special Conditions): splitting, header/footer removal, indexing."""

from __future__ import annotations

from pathlib import Path

import pytest

from easa_regs import db
from easa_regs.pdfbook import clean_lines, parse_pdf_book, reflow, split_cs
from easa_regs.sources import Book, PdfDoc

pytest.importorskip("pdfminer")
canvas = pytest.importorskip("reportlab.pdfgen.canvas")

CS_DOC = PdfDoc("CS-22", "Sailplanes and Powered Sailplanes, Amendment 3", "CS", 900001, "https://example.test/cs22",
                "ED Decision 2021/013/R", "2021-09-17")
CS_BOOK = Book("CS22", "CS-22 Sailplanes and Powered Sailplanes, Amendment 3", 0, "https://example.test/cs22",
               kind="pdf", split="cs", docs=(CS_DOC,))
SC_DOC = PdfDoc("SC-22.2014-01", "Installation of Electric Propulsion Units in Powered Sailplanes", "SC", 900002,
                "https://example.test/sc", "Issue 2", "2014-11-14")
SC_BOOK = Book("SC22", "Special Conditions for CS-22", 0, "https://example.test/sc-list", kind="pdf", split="doc",
               docs=(SC_DOC,))

CS_PAGES = [
    ["CONTENTS", "CS 22.143 General ........................ 5", "CS 22.145 Longitudinal control .......... 6",
     "AMC 22.143 General ....................... 9"],
    ["BOOK 1 – CERTIFICATION SPECIFICATIONS", "SUBPART B – FLIGHT", "CS 22.143 General",
     "(a) The sailplane must be safely controllable and manoeuvrable during", "take-off, climb and landing.",
     "(b) It must be possible to make a smooth transition from one flight", "condition to another."],
    ["CS 22.145 Longitudinal control", "(a) It must be possible at any speed below VNE to pitch the nose",
     "down so that a speed equal to 1.3 VS1 can be reached promptly."],
    ["BOOK 2 – ACCEPTABLE MEANS OF COMPLIANCE", "AMC 22.143 General",
     "Compliance should be shown by flight tests with the most adverse centre of gravity position."],
]


def _pdf(path: Path, pages: list[list[str]], header: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    for n, lines in enumerate(pages, 1):
        y = 800
        if header:
            c.drawString(60, 820, header)
        for ln in lines:
            c.drawString(60, y, ln)
            y -= 16
        if header:
            c.drawString(60, 30, f"Page {n} of {len(pages)}")
        c.showPage()
    c.save()
    return path


@pytest.fixture(scope="module")
def raw(tmp_path_factory) -> Path:
    raw = tmp_path_factory.mktemp("raw")
    _pdf(raw / "CS22" / "900001.pdf", CS_PAGES, header="CS-22 Amendment 3 - Annex to ED Decision 2021/013/R")
    _pdf(raw / "SC22" / "900002.pdf", [["Special Condition SC-22.2014-01 Issue 2",
                                        "Installation of Electric Propulsion Units in Powered Sailplanes",
                                        "Applicability: powered sailplanes with an electric propulsion unit.",
                                        "The battery must be installed so that thermal runaway cannot",
                                        "endanger the occupants."]])
    return raw


def test_clean_lines_drops_running_header_and_page_numbers():
    pages = [f"Header line\nbody {n}\nPage {n} of 5" for n in range(1, 6)]
    assert clean_lines(pages) == ["body 1", "body 2", "body 3", "body 4", "body 5"]


def test_reflow_joins_wrapped_lines_and_keeps_items():
    assert reflow(["(a) The sailplane must be", "controllable.", "(b) Next item"]) == \
        "(a) The sailplane must be controllable.\n(b) Next item"
    assert reflow(["electric propul-", "sion unit"]) == "electric propulsion unit"


def test_split_cs_skips_toc_and_links_amc(raw):
    from easa_regs.pdfbook import extract_pages
    rules = split_cs(CS_BOOK, CS_DOC, clean_lines(extract_pages(raw / "CS22" / "900001.pdf")))
    by_ref = {r.ref: r for r in rules}
    assert list(by_ref) == ["CS 22.143", "CS 22.145", "AMC 22.143"]
    cs = by_ref["CS 22.143"]
    assert cs.title == "CS 22.143 General" and cs.content_type == "CS"
    assert "safely controllable and manoeuvrable during take-off" in cs.text
    assert "SUBPART B – FLIGHT" in cs.breadcrumb and "BOOK 1" in cs.breadcrumb
    assert "Page 2 of 4" not in cs.text and "Annex to ED Decision" not in cs.text
    amc = by_ref["AMC 22.143"]
    assert amc.content_type == "AMC" and amc.parent_ir == "CS 22.143 General"


def test_pdf_books_index_and_search(raw, tmp_path, monkeypatch):
    con = db.connect(tmp_path / "t.sqlite")
    for book in (CS_BOOK, SC_BOOK):
        db.store_book(con, parse_pdf_book(raw / book.code, book))
    con.commit()
    rel = db.related(con, db.find_rule(con, "CS 22.143")[0])
    assert [a["ref"] for a in rel["amc_gm"]] == ["AMC 22.143"]
    sc = db.find_rule(con, "SC-22.2014-01")[0]
    assert sc["content_type"] == "SC" and "thermal runaway" in sc["text"] and "https://example.test/sc" in sc["text"]
    hits = [h["ref"] for h in db.search(con, "special condition electric propulsion battery")]
    assert hits and hits[0] == "SC-22.2014-01"
    assert [h["ref"] for h in db.search(con, "CS 22.145")][0] == "CS 22.145"


def test_cs22_amdt3_supersedes_sailplanes_copy(raw, tmp_path, monkeypatch):
    """CS 22.xxx exists in CS22 (Amdt 3) and in the SAILPLANES EAR (Amdt 2): the newer book wins."""
    import dataclasses

    from easa_regs import server
    path = tmp_path / "t.sqlite"
    con = db.connect(path)
    db.store_book(con, parse_pdf_book(raw / "CS22", CS_BOOK))
    old = parse_pdf_book(raw / "CS22", CS_BOOK)
    old = dataclasses.replace(old, code="SAILPLANES",
                              rules=[dataclasses.replace(r, book="SAILPLANES") for r in old.rules])
    db.store_book(con, old)
    con.commit()
    con.close()
    monkeypatch.setenv("EASA_REGS_DB", str(path))
    server._con.cache_clear()
    rule = server.get_easa_rule("CS 22.143")
    assert rule["found"] and rule["book"] == "CS22", rule
    assert [v["book"] for v in rule["superseded_versions"]] == ["SAILPLANES"]
    assert server.get_easa_rule("CS 22.143", book="SAILPLANES")["book"] == "SAILPLANES"
    assert server.search_easa_rules("CS 22.143")["results"][0]["book"] == "CS22"
    server._con.cache_clear()
