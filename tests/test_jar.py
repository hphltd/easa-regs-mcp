"""JAR-22 from the JAA two-column PDF: font-based split of requirements and inline AMC (no PDF needed)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from easa_regs import db, server
from easa_regs.jar import Line, _amc_suffix, split_sections

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "easa_regs.sqlite"

H, HO, HS, TR, TI = "Helvetica-Bold", "Helvetica-Oblique", "Helvetica", "Times-Roman", "Times-Italic"


def L(text, font=TR, size=10.0):
    return Line(text, font, size, 72.0)


PAGES = [
    [L("JAR-22", HS, 9.0), L("CONTENTS", H), L("JAR 22.221 General", TR)],          # front matter: ignored
    [L("Subpart B", H, 10.6), L("SPINNING", H), L("JAR 22.221 General", H),
     L("(a) Compliance must be shown in all configurations."),
     L("(b) The sailplane must be able to recover from spins of five turns."),
     L("AMC 22.221(b)", HO, 9.0), L("It will normally be sufficient to conduct spins of two turns.", TI),
     L("(c) A sailplane certificated for spinning must recover in one turn."),         # back to the requirement
     L("[Ch. 4, 7.5.87]", TR, 8.0), L("Amendment 6", HS, 9.0), L("B10", HS, 9.0)],
    [L("JAR 22.221 (continued)", HS, 9.0), L("(d) Loss of altitude must be determined."),
     L("JAR 22.233 Directional", H), L("stability and control", H), L("(a) No uncontrollable ground-loop.")],
]


def test_split_sections_by_font():
    secs = {s.ref: s for s in split_sections(PAGES)}
    assert list(secs) == ["JAR 22.221", "AMC 22.221(b)", "JAR 22.233"]
    jar = secs["JAR 22.221"]
    assert jar.heading == "General" and jar.crumbs == ["SPINNING"]
    text = " ".join(jar.lines)
    assert "(b) The sailplane" in text and "(c) A sailplane" in text and "(d) Loss of altitude" in text
    assert "two turns" not in text and "Amendment 6" not in text and "B10" not in text
    assert secs["AMC 22.221(b)"].lines == ["It will normally be sufficient to conduct spins of two turns."]
    assert secs["JAR 22.233"].heading == "Directional stability and control"


@pytest.mark.parametrize("rest,suffix", [
    ("(b)", "(b)"), ("(c),(d),(e) and (f)", "(c),(d),(e)and(f)"), (" General", ""),
])
def test_amc_suffix(rest, suffix):
    assert _amc_suffix(rest) == suffix


@pytest.mark.parametrize("query,token", [("JAR 22.697 lever", "JAR 22.697"), ("ACJ 22.1(a)", "ACJ 22.1(a)")])
def test_jar_ref_tokens(query, token):
    assert token in [m.group(0) for m in db.REF_TOKEN.finditer(query)]


def test_jar_niche():
    assert "JAR22" in db.niche_books_for("JAR-22 air brakes")
    assert "JAR22" not in db.niche_books_for("air brakes")


# ------------------------------------------- real data: only where the JAR-22 PDF was supplied to the build

def _has_jar() -> bool:
    if not REAL_DB.exists():
        return False
    return bool(sqlite3.connect(REAL_DB).execute("SELECT 1 FROM rules WHERE book='JAR22' LIMIT 1").fetchone())


real_jar = pytest.mark.skipif(not _has_jar(), reason="index built without the JAR-22 PDF")


@real_jar
@pytest.mark.parametrize("ref", ["JAR 22.143", "JAR 22.629", "JAR 22.697", "JAR 22.1581"])
def test_real_jar_refs(ref, monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    rule = server.get_easa_rule(ref)
    server._con.cache_clear()
    assert rule["found"] and rule["book"] == "JAR22" and len(rule["text"]) > 150, rule


@real_jar
def test_real_cs22_wins_over_jar22_amc(monkeypatch):
    monkeypatch.setenv("EASA_REGS_DB", str(REAL_DB))
    server._con.cache_clear()
    rule = server.get_easa_rule("AMC 22.221(b)")
    server._con.cache_clear()
    assert rule["book"] == "CS22" and "JAR22" in {v["book"] for v in rule["superseded_versions"]}
