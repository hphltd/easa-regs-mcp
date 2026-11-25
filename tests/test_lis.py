"""Czech L-series regulations (Letecké předpisy řady L) from aim.rlp.cz: data.js, chapters, indexing, search."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from easa_regs import db, server
from easa_regs.lis import LChapter, chapters_from, parse_data_js, parse_lis_book
from easa_regs.sources import BOOKS

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "easa_regs.sqlite"

DATA_JS = """const data = {
    folder: "L/L-8",
    name: "L 8 ",
    title: "Letová způsobilost letadel",
    link_print: "print/L8_cely.pdf",
    alert: [
        {
            name: "Změna č. 109 - 3. 11. 2022",
            link: "amdt/L8-zm109.pdf",
        },
     ],
    content: [
        // front matter
        { type: "link", name: "Titulní strana", link: "effective/titulni_strana.pdf" },
        { type: "link", name: "Obsah", link: "effective/obsah.pdf" },
        { type: "link", name: "Část I", link: "effective/cast1.pdf" },
        {
            type: "tree",
            name: "Část III",
            tree: [
                {
                    type: "tree",
                    name: "Část IIIA",
                    tree: [
                        { type: "link", name: "Hlava 1", link: "effective/cast3A_hl1.pdf" },
                        { type: "link", name: "Hlava 2", link: "effective/cast3A_hl2.pdf" },
                       ,
                    ]
                },
            ],
        },
        { type: "link", name: "Doplněk 1", link: "effective/dopl1.pdf" },
    ]
};
"""


def test_parse_data_js_tolerates_js_literals():
    data = parse_data_js(DATA_JS)
    assert data["name"] == "L 8 " and data["alert"][0]["link"] == "amdt/L8-zm109.pdf"
    assert data["content"][3]["tree"][0]["tree"][1]["link"] == "effective/cast3A_hl2.pdf"


def test_chapters_from_data_js():
    chs = chapters_from("L-8", parse_data_js(DATA_JS),
                        "https://aim.rlp.cz/predpisy/predpisy/dokumenty/L/L-8/index.htm")
    assert [c.ref for c in chs] == ["L 8 Část I", "L 8 Část IIIA Hlava 1", "L 8 Část IIIA Hlava 2", "L 8 Doplněk 1"]
    c = chs[2]
    assert c.reg == "L 8" and c.reg_title == "Letová způsobilost letadel"
    assert c.url == "https://aim.rlp.cz/predpisy/predpisy/dokumenty/L/L-8/data/effective/cast3A_hl2.pdf"
    assert c.amendment == "Změna č. 109 - 3. 11. 2022" and c.path == ["Část III", "Část IIIA", "Hlava 2"]


def _pdf(path: Path, lines: list[str]) -> None:
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    c = canvas.Canvas(str(path))
    y = 800
    for ln in lines:
        c.drawString(60, y, ln)
        y -= 14
    c.showPage()
    c.save()


@pytest.fixture(scope="module")
def l_db(tmp_path_factory) -> Path:
    pytest.importorskip("pdfminer")
    pytest.importorskip("reportlab")
    tmp = tmp_path_factory.mktemp("lis")
    folder = tmp / "CZ_L"
    folder.mkdir()
    page = "https://aim.rlp.cz/predpisy/predpisy/dokumenty/L/L-2/index.htm"
    url = "https://aim.rlp.cz/predpisy/predpisy/dokumenty/L/L-2/data/effective/"
    chs = [LChapter("L 2", "Pravidla letani", ["Hlava 4"], url + "hl4.pdf", "Zmena c. 16/CR - 16.4.2026", page),
           LChapter("L 2", "Pravidla letani", ["Hlava 3"], url + "hl3.pdf", "Zmena c. 16/CR - 16.4.2026", page)]
    _pdf(folder / f"{chs[0].key}.pdf", ["HLAVA 4", "PRAVIDLA LETU VFR",
                                        "4.1 Lety VFR se provadeji tak, aby letadlo letelo za podminek VMC",
                                        "pri dohlednosti a vzdalenosti od oblaku rovne nebo vetsi nez minima."])
    _pdf(folder / f"{chs[1].key}.pdf", ["HLAVA 3", "VSEOBECNA PRAVIDLA",
                                        "3.1 Ochrana osob a majetku: letadlo nesmi byt provozovano nedbale.",
                                        "3.2 Vyhybani se srazkam: velitel letadla musi dbat na bezpecnost."])
    (folder / "index.json").write_text(json.dumps([asdict(c) for c in chs]), encoding="utf-8")
    path = tmp / "l.sqlite"
    con = db.connect(path)
    db.store_book(con, parse_lis_book(folder, BOOKS["CZ_L"]))
    con.commit()
    con.close()
    return path


def test_lis_rules_and_overview(l_db):
    con = sqlite3.connect(l_db)
    con.row_factory = sqlite3.Row
    ch = db.find_rule(con, "L 2 Hlava 4")[0]
    assert ch["content_type"] == "L" and ch["book"] == "CZ_L" and "PRAVIDLA LETU VFR" in ch["title"]
    assert "Dokument: https://aim.rlp.cz/" in ch["text"] and ch["entry_into_force_date"] == "2026-04-16"
    overview = db.find_rule(con, "L 2")[0]
    assert overview["ref"] == "L 2" and "L 2 Hlava 3" in overview["text"]
    assert [r["ref"] for r in db.related(con, overview)["amc_gm"]] == ["L 2 Hlava 4", "L 2 Hlava 3"]


def test_lis_search(l_db, monkeypatch):
    con = sqlite3.connect(l_db)
    con.row_factory = sqlite3.Row
    assert db.search(con, "minima VMC dohlednost")[0]["ref"] == "L 2 Hlava 4"
    assert db.search(con, "L 2 Hlava 3")[0]["ref"] == "L 2 Hlava 3"
    monkeypatch.setenv("EASA_REGS_DB", str(l_db))
    server._con.cache_clear()
    try:
        rule = server.get_easa_rule("L 2 Hlava 4")
        assert rule["found"] and rule["source_url"].endswith("/hl4.pdf") and "ŘLP" in rule["disclaimer"]
    finally:
        server._con.cache_clear()


@pytest.mark.parametrize("query,token", [
    ("co říká L 8/A", "L 8/A"), ("L 2 Hlava 3 vyhýbání", "L 2 Hlava 3"), ("L 6/I", "L 6/I"),
    ("L 8 Část IIIB Hlava 2", "L 8 Část IIIB Hlava 2"), ("L 4444 separace", "L 4444"),
])
def test_lis_ref_tokens(query, token):
    assert token in [m.group(0) for m in db.REF_TOKEN.finditer(query)]


@pytest.mark.parametrize("query,expected", [
    ("předpis L 2 pravidla létání", True), ("L 8/A", True), ("minima VMC", False),
])
def test_lis_niche(query, expected):
    assert ("CZ_L" in db.niche_books_for(query)) is expected


# ---------------------------------------------------------------- real-data regression (skips without index)

real = pytest.mark.skipif(not REAL_DB.exists(), reason="build the real index first")


@real
def test_real_lis_counts():
    con = sqlite3.connect(REAL_DB)
    regs = con.execute("SELECT COUNT(*) FROM rules WHERE book='CZ_L' AND parent_ir=''").fetchone()[0]
    chapters = con.execute("SELECT COUNT(DISTINCT erules_id) FROM rules WHERE book='CZ_L'").fetchone()[0]
    assert regs >= 30 and chapters >= 500, (regs, chapters)


@real
@pytest.mark.parametrize("ref", ["L 2", "L 8/A", "L 8", "L 6/I"])
def test_real_lis_overview(ref, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    rule = server.get_easa_rule(ref, book="CZ_L")
    server._con.cache_clear()
    assert rule["found"] and rule["ref"] == ref and rule["related"]["amc_gm"], rule
