"""A kvíz eredményei a `{tanulas_db}`-ben (`core/tanulas_db.py`, 2-es migráció): kitöltések, válaszok, „hibás kérdés” jelölések.

A kvíz maga a vaultban él; itt csak az eredménye. A kitöltés **a Tracker-kapcsolótól független** (tanulási állapot, nem
telemetria). Az írás egyetlen tranzakció (`tanulas_db.iro`); az olvasás `mode=ro`, nem migrál és nem hoz létre fájlt.

- A kitöltés `kulcs`-a egyedi: a felület újraküldése (hálózati hiba után) ugyanazt a választ kapja, nem új kitöltést.
- A „hibás kérdés” jelölés nem számít a pontba, és a kvízmodell pontosságát méri (a legacy egyetlen valódi mérése).
- Idő: UTC ISO, másodpercre (a `kartya` rétegével azonosan).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from core import tanulas_db

from . import formatum

MEGJEGYZES_MAX = 500


def most_utc(mikor: datetime | None = None) -> str:
    d = mikor or datetime.now(timezone.utc)
    if d.tzinfo is None:
        raise ValueError("az időpont legyen időzónás")
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()


class KulcsFoglalt(ValueError):
    """A kitöltés-kulcs már egy MÁSIK kvíz kitöltéséé (A3-04): nem adható vissza az az értékelés."""


def kitoltes_ment(cfg, kulcs: str, k: formatum.Kviz, kviz_ut: str, ertekeles: dict, mikor: datetime | None = None) -> tuple[dict, bool]:
    """Egy kitöltés mentése → (az értékelés, új-e). Ha a `kulcs` már van, a mentett értékelést adja (`új = False`)."""
    o = ertekeles["osszegzes"]
    with tanulas_db.iro(cfg) as c:
        r = c.execute("SELECT elemzes, kviz FROM kviz_kitoltes WHERE kulcs = ?", (kulcs,)).fetchone()
        if r and r["kviz"] != k.azon:
            raise KulcsFoglalt("a kitöltés-kulcs egy másik kvízé")
        if r:
            return json.loads(r["elemzes"]), False
        kid = c.execute(
            "INSERT INTO kviz_kitoltes (kulcs, kviz, kviz_ut, forras, modell, szoveg_hash, mikor, mod, pont, osszes, szazalek, ido_ms, "
            "elemzes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kulcs, k.azon, kviz_ut, k.forras, k.modell, formatum.tartalom_hash(k), most_utc(mikor), ertekeles["mod"],
             o["pont"], o["osszes"], o["szazalek"], ertekeles.get("ido_ms"), json.dumps(ertekeles, ensure_ascii=False))).lastrowid
        for e in ertekeles["eredmenyek"]:
            c.execute("INSERT INTO kviz_valasz (kitoltes, kerdes, valasz, helyes, tipp, kategoria, ms, jelolt, szakasz, horgony) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (kid, e["kerdes"], e["valasz"], int(e["helyes"]), int(e["tipp"]), e["kategoria"], e["ms"], int(e["jelolt"]),
                       e["szakasz"], e["horgony"]))
    return ertekeles, True


def kitoltes_kulccsal(cfg, kulcs: str, kviz_azon: str) -> dict | None:
    """A kulcs szerint, EZEN a kvízen már mentett kitöltés értékelése, vagy `None` (másik kvíz kulcsa nem adható ki: A3-04;
    a mentés az ütközést `KulcsFoglalt`-tal jelzi)."""
    with tanulas_db.olvaso(cfg, min_verzio=2) as c:
        if c is None:
            return None
        r = c.execute("SELECT elemzes FROM kviz_kitoltes WHERE kulcs = ? AND kviz = ?", (kulcs, kviz_azon)).fetchone()
        return json.loads(r["elemzes"]) if r else None


def kitoltesek(cfg, kviz_azon: str, limit: int | None = None) -> list[dict]:
    """A kvíz kitöltései időrendben (a legrégebbi elöl; `limit`: a legutóbbi N): `{id, mikor, mod, szoveg_hash, osszegzes,
    eredmenyek: [{kerdes, helyes, kategoria, jelolt}]}`."""
    with tanulas_db.olvaso(cfg, min_verzio=2) as c:
        if c is None:
            return []
        sorok = c.execute("SELECT id, mikor, mod, szoveg_hash, elemzes FROM kviz_kitoltes WHERE kviz = ? ORDER BY id", (kviz_azon,)).fetchall()
    ki = []
    for r in sorok[-limit:] if limit else sorok:
        e = json.loads(r["elemzes"])
        ki.append({"id": r["id"], "mikor": r["mikor"], "mod": r["mod"], "szoveg_hash": r["szoveg_hash"], "osszegzes": e["osszegzes"],
                   "eredmenyek": [{"kerdes": x["kerdes"], "helyes": x["helyes"], "kategoria": x["kategoria"], "jelolt": x["jelolt"]}
                                  for x in e["eredmenyek"]]})
    return ki


def utolso(cfg, kviz_azon: str) -> dict | None:
    k = kitoltesek(cfg, kviz_azon, limit=1)
    return k[-1] if k else None


def jelolesek(cfg, kviz_azon: str) -> dict[str, dict]:
    """A „hibás kérdés” jelölések: kérdés → `{mikor, megjegyzes}`."""
    with tanulas_db.olvaso(cfg, min_verzio=2) as c:
        if c is None:
            return {}
        return {r["kerdes"]: {"mikor": r["mikor"], "megjegyzes": r["megjegyzes"]}
                for r in c.execute("SELECT kerdes, mikor, megjegyzes FROM kviz_jeloles WHERE kviz = ?", (kviz_azon,))}


def jelol(cfg, kviz_azon: str, kerdes: str, hibas: bool, megjegyzes: str = "") -> None:
    with tanulas_db.iro(cfg) as c:
        if hibas:
            c.execute("INSERT OR REPLACE INTO kviz_jeloles (kviz, kerdes, mikor, megjegyzes) VALUES (?,?,?,?)",
                      (kviz_azon, kerdes, most_utc(), str(megjegyzes or "")[:MEGJEGYZES_MAX]))
        else:
            c.execute("DELETE FROM kviz_jeloles WHERE kviz = ? AND kerdes = ?", (kviz_azon, kerdes))


def modell_statisztika(cfg) -> dict[str, dict]:
    """A kvízszerep egyetlen valódi mérése: modellenként a megválaszolt kérdések és a kitöltő által „hibásnak” jelöltek aránya
    (a jelölés a kvízmodell pontosságát méri, nem a kitöltőét). Ha 90% alá esik, a modell kalibrációja felülvizsgálandó."""
    with tanulas_db.olvaso(cfg, min_verzio=2) as c:
        if c is None:
            return {}
        sorok = c.execute(
            "SELECT k.modell AS modell, COUNT(DISTINCT k.kviz) AS kviz, COUNT(DISTINCT k.id) AS kitoltes, "
            "COUNT(DISTINCT k.kviz || '/' || v.kerdes) AS megvalaszolt, "
            "COUNT(DISTINCT CASE WHEN j.kerdes IS NOT NULL THEN k.kviz || '/' || v.kerdes END) AS hibasnak_jelolt "
            "FROM kviz_kitoltes k JOIN kviz_valasz v ON v.kitoltes = k.id "
            "LEFT JOIN kviz_jeloles j ON j.kviz = k.kviz AND j.kerdes = v.kerdes "
            "GROUP BY k.modell").fetchall()
    ki = {}
    for r in sorok:
        d = dict(r)
        modell = d.pop("modell") or ""
        d["pontossag_jelolesek_szerint"] = round(1 - d["hibasnak_jelolt"] / d["megvalaszolt"], 3) if d["megvalaszolt"] else None
        ki[modell] = d
    return ki
