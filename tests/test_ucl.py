"""Czech CAA (ÚCL) directives and advisory circulars: listing page, references, parts, indexing, search."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from easa_regs import db, server
from easa_regs.sources import BOOKS
from easa_regs.ucl import UclDoc, parse_listing, parse_ucl_book, split_parts, split_ref

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "easa_regs.sqlite"
BASE = "https://www.caa.gov.cz/dokumenty/predpisy/smernice-ucl/"

LISTING = """<html><body><h1>Směrnice ÚCL</h1>
<p class="wp-block-paragraph"><a href="https://www.caa.gov.cz/wp-content/uploads/2023/09/UCL-237.pdf?cb=1"
 class="mtli_attachment mtli_pdf">Směrnice ÚCL-237 Postupy pro plnění požadavků ATFM</a><br>Úřad tímto dokumentem
 rozpracovává nařízení Komise (EU) č. 255/2010.<br>Předmětem změny č. 4 je úprava postupů.</p>
<h4 class="wp-block-heading">Směrnice sekce technické a provozní</h4>
<p><a href="/wp-content/uploads/2023/09/CAA_S-SP-028.pdf?cb=2" class="mtli_pdf">Směrnice CAA/S-SP-028-4/2020</a><br>
Příručka vnitrostátního dozorového orgánu ČR.<br>Česká republika pověřila Úřad výkonem úkolů NSA.</p>
<p><a href="/wp-content/uploads/2025/03/S-SP-009.pdf" class="mtli_pdf">Směrnice CAA-S-SP-009-5/2019</a> (verze 6.1)
<br>Směrnice Dohled nad řízením změn u poskytovatelů služeb. Verze 6.1 nabývá účinnosti 1. 4. 2025.</p>
<h5 class="wp-block-heading">Směrnice odboru technického </h5>
<p><a href="/wp-content/uploads/2019/06/CAA-TI-010-n-99.pdf" class="mtli_pdf">CAA-TI-010-n/99 Směrnice pro zkušební
 lety civilních letadel</a></p>
<p><a href="/wp-content/uploads/2019/06/CAA-F-TI-043.doc">Žádost o udělení souhlasu ÚCL k provádění zkušebních letů</a></p>
<p><a href="/wp-content/uploads/2019/06/CAA-TI-026-n-01_NP-změna_3.pdf">CAA-TI-026-n/01 Postupy pro získání oprávnění
 k projektování</a></p>
<p><a href="/wp-content/uploads/2019/06/CAA-ST-105.pdf">CAA-ST-105-n/11 Směrnice pro tvorbu Příručky pro řízení
 údržby</a></p>
<p><a href="/wp-content/uploads/2019/06/priloha-1_PRU.pdf">Příručka pro řízení údržby &#8211; vzor ke zpracování</a></p>
<h2 class="plane-right">Máte nejasnosti?</h2>
<p><a href="/wp-content/uploads/footer.pdf">Footer PDF</a></p>
</body></html>"""


@pytest.mark.parametrize("text,ref,title", [
    ("Směrnice ÚCL-237 Postupy pro plnění požadavků ATFM", "ÚCL-237", "Postupy pro plnění požadavků ATFM"),
    ("CAA-TI-010-n/99 Směrnice pro zkušební lety", "CAA-TI-010-n/99", "Směrnice pro zkušební lety"),
    ("PO/TI – 20 – 1 Příručka pro individuální stavbu letadla", "PO/TI-20-1", "Příručka pro individuální stavbu letadla"),
    ("PO/ST-L8/A 4.6 Používání Formuláře 1 ÚCL", "PO/ST-L8/A 4.6", "Používání Formuláře 1 ÚCL"),
    ("PO/ST -21A.139(a)-A Metodické pokyny", "PO/ST-21A.139(a)-A", "Metodické pokyny"),
    ("PO/ST – Část 145.A.70-23 Směrnice pro stanice", "PO/ST-Část 145.A.70-23", "Směrnice pro stanice"),
    ("PO/ST – Part ML – ML.A.302 – Tvorba programu údržby", "PO/ST-Part ML-ML.A.302", "Tvorba programu údržby"),
    ("PO – SL – 60 – 1 – Získání pilotních znalostí", "PO-SL-60-1", "Získání pilotních znalostí"),
    ("PO-SL – Tvorba a vedení palubního deníku", "PO-SL", "Tvorba a vedení palubního deníku"),
    ("PO/TI – L8/A.2.7.12. Obnovení platnosti", "PO/TI-L8/A.2.7.12", "Obnovení platnosti"),
    ("Příručka pro řízení údržby – vzor", "", "Příručka pro řízení údržby – vzor"),
])
def test_split_ref(text, ref, title):
    assert split_ref(text) == (ref, title)


def test_parse_listing():
    docs = parse_listing(LISTING, BASE)
    by_ref = {d.ref: d for d in docs}
    assert list(by_ref) == ["ÚCL-237", "CAA/S-SP-028-4/2020", "CAA-S-SP-009-5/2019", "CAA-TI-010-n/99",
                            "CAA-TI-026-n/01", "CAA-ST-105-n/11", "CAA-ST-105-n/11 příloha 1"]  # no .doc, no footer
    atfm = by_ref["ÚCL-237"]
    assert atfm.url == "https://www.caa.gov.cz/wp-content/uploads/2023/09/UCL-237.pdf"   # cache-buster dropped
    assert atfm.section == "Směrnice ÚCL" and atfm.date == "2023-09"
    assert "255/2010" in atfm.summary and "změny č. 4" in atfm.summary
    nsa = by_ref["CAA/S-SP-028-4/2020"]
    assert nsa.title == "Příručka vnitrostátního dozorového orgánu ČR" and nsa.section.startswith("Směrnice sekce")
    assert by_ref["CAA-S-SP-009-5/2019"].title.endswith("(verze 6.1)")
    assert by_ref["CAA-TI-010-n/99"].section == "Směrnice odboru technického"
    assert by_ref["CAA-TI-026-n/01"].url.endswith("NP-zm%C4%9Bna_3.pdf")                # non-ASCII path quoted
    assert by_ref["CAA-ST-105-n/11 příloha 1"].title == "Příručka pro řízení údržby – vzor ke zpracování"


def test_split_parts():
    assert split_parts("krátký text") == [("", "krátký text")]
    paras = []
    for n in range(1, 9):
        paras.append(f"{n}. Hlava číslo {n}")
        paras += [f"Odstavec {n}.{k} " + "text " * 120 for k in range(1, 9)]
    parts = split_parts("\n".join(paras))
    assert len(parts) > 1
    assert all(h.split(". ")[0].isdigit() for h, _ in parts[1:])      # every later part starts at a heading
    assert all(len(b) <= 16000 + 2000 for _, b in parts)
    squash = lambda s: "".join(s.split())                              # noqa: E731 - nothing lost or duplicated
    assert squash("".join(b for _, b in parts)) == squash("".join(paras))


# ------------------------------------------------------------------------- indexing (needs pdfminer, reportlab)

def _pdf(path: Path, pages: list[list[str]]) -> None:
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    c = canvas.Canvas(str(path))
    for lines in pages:
        y = 800
        for ln in lines:
            c.drawString(60, y, ln)
            y -= 14
        c.showPage()
    c.save()


@pytest.fixture(scope="module")
def ucl_db(tmp_path_factory) -> Path:
    pytest.importorskip("pdfminer")
    pytest.importorskip("reportlab")
    tmp = tmp_path_factory.mktemp("ucl")
    folder = tmp / "UCL_SM"
    folder.mkdir()
    flight = UclDoc("CAA-TI-010-n/99", "Smernice pro zkusebni lety civilnich letadel", "Smernice odboru technickeho",
                    "", "https://example.test/CAA-TI-010.pdf", "2019-06")
    long_doc = UclDoc("CAA-ST-115-n/16", "Standardni zmeny na letadlech", "Smernice odboru technickeho",
                      "Postup pro standardni zmeny.", "https://example.test/N-STAN.pdf", "2023-12")
    _pdf(folder / f"{flight.key}.pdf", [[
        "1. Druhy zkusebnich letu", "Zkusebni lety se provadeji pred vydanim osvedceni letove zpusobilosti.",
        "2. Provadeni zkusebnich letu", "Zkusebni let smi provadet pouze pilot s opravnenim ke zkusebnim letum."]])
    pages = []
    for n in range(1, 13):                           # ~24k characters: split into parts at the chapter headings
        pages.append([f"{n}. Standardni zmena N-STAN-SC{n:03d}"] +
                     [f"Radek {k} popisuje zastavbu vybaveni a uvolneni letadla do provozu po zmene cislo {n}."
                      for k in range(1, 25)])
    _pdf(folder / f"{long_doc.key}.pdf", pages)
    (folder / "index.json").write_text(json.dumps([asdict(flight), asdict(long_doc)]), encoding="utf-8")
    path = tmp / "ucl.sqlite"
    con = db.connect(path)
    db.store_book(con, parse_ucl_book(folder, BOOKS["UCL_SM"]))
    con.commit()
    con.close()
    return path


def test_ucl_book_rules(ucl_db):
    con = sqlite3.connect(ucl_db)
    con.row_factory = sqlite3.Row
    doc = db.find_rule(con, "CAA-TI-010-n/99")[0]
    assert doc["content_type"] == "SM" and doc["book"] == "UCL_SM"
    assert "Dokument: https://example.test/CAA-TI-010.pdf" in doc["text"] and "pilot s opravnenim" in doc["text"]
    assert doc["erules_id"].startswith("UCL-UCL_SM-")
    parts = db.related(con, db.find_rule(con, "CAA-ST-115-n/16")[0])["amc_gm"]
    assert len(parts) >= 1 and parts[0]["ref"] == "CAA-ST-115-n/16 (část 2)"
    assert "N-STAN-SC" in parts[0]["title"]
    assert db.find_rule(con, "CAA-ST-115-n/16 (část 2)")[0]["parent_ir"].startswith("CAA-ST-115-n/16 ")


def test_ucl_search_czech(ucl_db):
    con = sqlite3.connect(ucl_db)
    con.row_factory = sqlite3.Row
    assert db.search(con, "zkušební lety")[0]["ref"] == "CAA-TI-010-n/99"          # diacritics + inflection
    assert db.search(con, "zkušebních letů")[0]["ref"] == "CAA-TI-010-n/99"
    assert db.search(con, "CAA-TI-010-n/99")[0]["ref"] == "CAA-TI-010-n/99"
    assert db.search(con, "standardní změna", book="UCL_SM")[0]["ref"].startswith("CAA-ST-115-n/16")


def test_ucl_get_rule_via_server(ucl_db, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(ucl_db))
    server._con.cache_clear()
    try:
        rule = server.get_easa_rule("CAA-TI-010-n/99")
        assert rule["found"] and rule["type"] == "SM" and rule["book"] == "UCL_SM"
        assert rule["source_url"] == "https://example.test/CAA-TI-010.pdf"
        assert "ÚCL" in rule["disclaimer"]
    finally:
        server._con.cache_clear()


@pytest.mark.parametrize("query,books", [
    ("zkušební lety", {"UCL_SM", "UCL_PO"}),                  # Czech letters
    ("CAA-TI-010-n/99", {"UCL_SM", "UCL_PO"}),
    ("PO/ST-20-6 klasifikace", {"UCL_PO"}),
    ("L8/A annex", {"UCL_SM", "UCL_PO"}),
    ("L8/A type certificate", {"UCL_SM", "UCL_PO", "INITAIR"}),
    ("SEP class rating revalidation", set()),
])
def test_ucl_niche_books(query, books):
    assert db.niche_books_for(query) == books


@pytest.mark.parametrize("query,token", [
    ("co říká CAA-TI-010-n/99", "CAA-TI-010-n/99"), ("CAA/S-SP-028-4/2020", "CAA/S-SP-028-4/2020"),
    ("ÚCL-237 ATFM", "ÚCL-237"), ("PO/ST-20-6 změny", "PO/ST-20-6"),
])
def test_ucl_ref_tokens(query, token):
    assert token in [m.group(0) for m in db.REF_TOKEN.finditer(query)]


def test_czech_prefix_only_for_czech_queries():
    assert db._fts_query("zkušebních letů", "OR", czech=True) == '"zkušební"* OR "let"*'
    assert db._fts_query("production organisation", "OR") == '"production"* OR "organisation"*'


# ---------------------------------------------------------------- real-data regression (skips without index)

real = pytest.mark.skipif(not REAL_DB.exists(), reason="build the real index first")


@real
def test_real_ucl_counts():
    con = sqlite3.connect(REAL_DB)
    docs = dict(con.execute("SELECT book, COUNT(*) FROM rules WHERE parent_ir = '' GROUP BY book"))
    assert docs.get("UCL_SM", 0) >= 30 and docs.get("UCL_PO", 0) >= 20, docs


@real
@pytest.mark.parametrize("query,expected", [
    ("zkušební lety", "CAA-TI-010-n/99"),
    ("vlečný letoun", "PO/ST-20-5"),
    ("podvržené díly", "CAA-ST-071-n/04"),
    ("prodloužení platnosti OLZ kluzáku", "CAA-TI-009-n/99"),
    ("individuální stavba letadla", "PO/TI-20-1"),
    ("exportní osvědčení letové způsobilosti", "CAA-ST-087-n/06"),
])
def test_real_ucl_golden(query, expected, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    top = [h["ref"] for h in server.search_easa_rules(query, limit=3)["results"]]
    server._con.cache_clear()
    assert expected in top, f"{query!r}: {top}"
