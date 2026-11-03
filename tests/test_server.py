import json
import sqlite3
from pathlib import Path

import pytest

from easa_regs import db, server

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "easa_regs.sqlite"


def test_get_rule_and_related(sample_db):
    r = server.get_easa_rule("sera.5005")
    assert r["found"] and r["ref"] == "SERA.5005" and r["type"] == "IR"
    assert [x["ref"] for x in r["related"]["amc_gm"]] == ["AMC1 SERA.5005(c)", "GM1 SERA.5005(c)(3)(iii)"]
    assert "ERULES-1-100" in r["citation"] and "2025-08-26" in r["citation"]
    amc = server.get_easa_rule("AMC1 SERA.5005(c)")
    assert amc["related"]["parent"]["ref"] == "SERA.5005"
    assert server.get_easa_rule("ERULES-1-102")["ref"] == "GM1 SERA.5005(c)(3)(iii)"


def test_get_rule_missing(sample_db):
    r = server.get_easa_rule("SERA.9999")
    assert not r["found"] and r["did_you_mean"]


def test_search(sample_db):
    hits = server.search_easa_rules("ceiling 450 m VFR")["results"]
    assert hits[0]["ref"] == "SERA.5005"
    assert server.search_easa_rules("night VFR", content_type="AMC")["results"][0]["type"] == "AMC"
    assert server.search_easa_rules("SERA.5005")["results"][0]["ref"] == "SERA.5005"
    assert server.search_easa_rules("zzzz qqqq")["results"] == []


def test_toc_and_sources(sample_db):
    t = server.browse_easa_toc("SERA", "SECTION 5")
    assert t["sections"][0]["ir"] == 2 and len(t["rules"]) == 4
    s = server.list_easa_sources()
    assert s["books"][0]["code"] == "SERA" and "not legally binding" in s["disclaimer"].lower()


def test_fts_query_is_injection_safe(sample_db):
    for q in ['"', "AND OR NOT", "a* (b", "NEAR(", "col:val", "';DROP TABLE rules;--"]:
        server.search_easa_rules(q)  # must not raise


# ---------------------------------------------------------------- real-data regression (skips without index)

real = pytest.mark.skipif(not REAL_DB.exists(), reason="build the real index first")

GOLDEN = [  # (query, book, expected ref among top 3)
    ("SEP class rating revalidation by experience", "AIRCREW", "FCL.740.A"),
    ("recency 3 take-offs landings 90 days passengers", "AIRCREW", "FCL.060"),
    ("FI restricted privileges supervision", "AIRCREW", "FCL.910.FI"),
    ("language proficiency validity", "AIRCREW", "FCL.055"),
    ("medical certificate validity revalidation", "AIRCREW", "MED.A.045"),
    ("special VFR control zone", "SERA", "SERA.5010"),
    ("VMC visibility distance from cloud minima", "SERA", "SERA.5001"),
    ("cruising levels", "SERA", "SERA.3110"),
    ("NCO destination alternate aerodromes aeroplanes", "AIROPS", "NCO.OP.140"),
    ("emergency locator transmitter NCO aeroplanes", "AIROPS", "NCO.IDE.A.170"),
    ("pilot-in-command responsibilities NCO", "AIROPS", "NCO.GEN.105"),
]


@real
@pytest.mark.parametrize("query,book,expected", GOLDEN)
def test_golden_search(query, book, expected, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    top = [h["ref"] for h in server.search_easa_rules(query, limit=3)["results"]]
    assert expected in top, f"{query!r}: {top}"


@real
def test_real_counts():
    con = sqlite3.connect(REAL_DB)
    counts = dict(con.execute("SELECT book, COUNT(*) FROM rules GROUP BY book"))
    assert counts["AIRCREW"] > 900 and counts["AIROPS"] > 3000 and counts["SERA"] > 300
    total = con.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    empty = con.execute("SELECT COUNT(*) FROM rules WHERE length(text) < 20").fetchone()[0]
    assert empty / total < 0.01, f"{empty} of {total} rules have (almost) no text"


@real
def test_eval_set_hit_rate(monkeypatch):
    from eval_questions import EVAL
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    misses = []
    for q, exp in EVAL:
        top = [h["ref"] for h in server.search_easa_rules(q, limit=5)["results"]]
        if not any(t == e or t.startswith(e + "(") for t in top for e in exp):
            misses.append((q, top))
    assert len(misses) <= 1, misses


@real
@pytest.mark.parametrize("query,expected", [
    ("Verlängerung SEP Klassenberechtigung durch Erfahrung", "FCL.740.A"),
    ("Nachtflugberechtigung Voraussetzungen", "FCL.810"),
    ("Passagiere mitnehmen 3 Landungen 90 Tage", "FCL.060"),
    ("Funkausfall Sichtflug", "SERA.14083"),
])
def test_german_queries(query, expected, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    assert expected in [h["ref"] for h in server.search_easa_rules(query, limit=5)["results"]]


@real
def test_real_counts_part21_part_is():
    con = sqlite3.connect(REAL_DB)
    counts = dict(con.execute("SELECT book, COUNT(*) FROM rules GROUP BY book"))
    assert counts.get("INITAIR", 0) > 300 and counts.get("INFOSEC", 0) > 50 and counts.get("AMC20", 0) > 20, counts
    assert counts.get("CS22", 0) > 150, counts            # CS + AMC paragraphs of CS-22 Amendment 3
    from easa_regs.sources import BOOKS
    assert counts.get("SC22", 0) == len(BOOKS["SC22"].docs), counts


@real
@pytest.mark.parametrize("ref,book", [
    ("21.A.9", "INITAIR"), ("21.A.133", "INITAIR"), ("21.A.139", "INITAIR"), ("21.A.239", "INITAIR"),
    ("IS.D.OR.200", "INFOSEC"), ("IS.I.OR.200", "INFOSEC"), ("AMC 20-29", "AMC20"),
    ("CS 22.143", "CS22"), ("CS 22.629", "CS22"), ("SC-22.2014-01", "SC22"), ("CM-S-008", "SC22"),
])
def test_part21_part_is_refs(ref, book, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    rule = server.get_easa_rule(ref)
    assert rule.get("ref") == ref and rule.get("book") == book, rule
    assert len(rule.get("text", "")) > 100


@real
@pytest.mark.parametrize("query,book,expected", [
    ("production organisation eligibility", "INITAIR", {"21.A.133"}),
    ("production management system", "INITAIR", {"21.A.139"}),
    ("design management system", "INITAIR", {"21.A.239"}),
    ("information security management system", "INFOSEC", {"IS.D.OR.200", "IS.I.OR.200"}),
])
def test_golden_search_part21_part_is(query, book, expected, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    top = [h["ref"] for h in server.search_easa_rules(query, book=book, limit=5)["results"]]
    assert expected & set(top), f"{query!r}: {top}"


@pytest.mark.parametrize("query,niche", [
    ("POA production management system", True), ("21.A.139(d)", True), ("Part-IS ISMS", True),
    ("IS.D.OR.200 information security", True), ("SEP class rating revalidation", False),
])
def test_part21_niche_hints(query, niche):
    from easa_regs import db
    assert bool(db.NICHE_HINTS.search(query)) is niche


@pytest.mark.parametrize("query,token", [
    ("what does CS 22.143 say", "CS 22.143"), ("AMC 20-29 composite", "AMC 20-29"),
    ("AMC 20-115D", "AMC 20-115D"), ("21.A.139(d) POA", "21.A.139(d)"),
])
def test_ref_tokens_cs_and_amc20(query, token):
    from easa_regs import db
    assert token in [m.group(0) for m in db.REF_TOKEN.finditer(query)]


def test_part21_expansions():
    from easa_regs import db
    assert db._expansion("POA") == "production organisation approval"
    assert db._expansion("ISMS") == "information security management system"


def test_index_url_override(monkeypatch):
    import importlib
    from easa_regs import sources
    monkeypatch.setenv("EASA_REGS_REPO", "example/fork")
    try:
        assert importlib.reload(sources).INDEX_URL == \
            "https://github.com/example/fork/releases/latest/download/easa_regs.sqlite"
    finally:
        monkeypatch.delenv("EASA_REGS_REPO")
        importlib.reload(sources)


def test_book_codes_in_sync():
    from typing import get_args
    from easa_regs.sources import BOOKS
    assert set(get_args(server.BookCode)) == set(BOOKS)
