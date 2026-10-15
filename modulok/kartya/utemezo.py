"""FSRS-ütemezés a py-fsrs-szel (`docs/C23-TERV.md` 3. fejezet; D3: fsrs 6.3.2, jóváhagyva).

Az állapot a `kartya` sorában él (`allapot` 0 új · 1 tanulás · 2 ismétlés · 3 újratanulás — a py-fsrs `State`-je és az
„új”), minden válasz egy `valasz` sor az előtte/utána állapottal, így a visszavonás pontos. A gombok az Ankiéi:
1 Again · 2 Hard · 3 Good · 4 Easy. Minden idő UTC, másodpercre vágva.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from core import tanulas_db

from .szinkron import beallitas, ido, iso, most_utc

UJ = 0
MEZOK = ("allapot", "lepes", "stabilitas", "nehezseg", "esedekes", "utolso")
_LEPES = re.compile(r"(\d+(?:\.\d+)?)\s*([smhd])")
_EGYSEG = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def lepesek(lista) -> tuple[timedelta, ...]:
    """`["1m", "10m"]` → időtartamok (s | m | h | d)."""
    ki = []
    for x in lista:
        m = _LEPES.fullmatch(str(x).strip())
        if not m:
            raise ValueError(f"hibás lépés: {x!r} (pl. 1m, 10m, 1h, 1d)")
        ki.append(timedelta(**{_EGYSEG[m.group(2)]: float(m.group(1))}))
    return tuple(ki)


def utemezo(cfg, **felulir):
    """A py-fsrs ütemezője a `[kartya]` beállításaival (`felulir`: tesztben pl. `fuzz=False`)."""
    import fsrs
    b = {**beallitas(cfg), **felulir}
    return fsrs.Scheduler(desired_retention=float(b.get("megtartas", 0.9)),
                          learning_steps=lepesek(b.get("tanulasi_lepesek", ["1m", "10m"])),
                          relearning_steps=lepesek(b.get("ujratanulasi_lepesek", ["10m"])),
                          maximum_interval=int(b.get("max_intervallum_nap", 36500)),
                          enable_fuzzing=bool(b.get("fuzz", True)))


def allapot_sorbol(r) -> dict:
    return {k: r[k] for k in MEZOK}


def _fsrs_kartya(a: dict, most: datetime):
    import fsrs
    if a["allapot"] == UJ:
        return fsrs.Card(card_id=1, state=fsrs.State.Learning, step=0, due=most)
    return fsrs.Card(card_id=1, state=fsrs.State(a["allapot"]), step=a["lepes"], stability=a["stabilitas"],
                     difficulty=a["nehezseg"], due=ido(a["esedekes"]) or most, last_review=ido(a["utolso"]))


def _allapotba(card) -> dict:
    return {"allapot": int(card.state), "lepes": card.step, "stabilitas": card.stability, "nehezseg": card.difficulty,
            "esedekes": iso(card.due), "utolso": iso(card.last_review)}


def _ir_allapot(c, azon: str, a: dict) -> None:
    c.execute("UPDATE kartya SET allapot = ?, lepes = ?, stabilitas = ?, nehezseg = ?, esedekes = ?, utolso = ? "
              "WHERE azon = ?", (*(a[k] for k in MEZOK), azon))


def _kartya_sor(c, azon: str):
    r = c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone()
    if r is None:
        raise ValueError(f"ismeretlen kártya: {azon}")
    if r["torolve"] is not None:
        raise ValueError(f"törölt kártya: {azon}")
    if r["felfuggesztve"]:
        raise ValueError(f"felfüggesztett kártya: {azon}")
    return r


def valaszol(cfg, azon: str, jegy: int, ms: int | None = None, most: datetime | None = None, sched=None) -> dict:
    """Egy értékelés (1–4): az új FSRS-állapot és egy naplósor, egy tranzakcióban. → az új állapot."""
    import fsrs
    if jegy not in (1, 2, 3, 4):
        raise ValueError("a jegy 1–4 (Again, Hard, Good, Easy)")
    t = most_utc(most)
    sched = sched or utemezo(cfg)
    with tanulas_db.iro(cfg) as c:
        elotte = allapot_sorbol(_kartya_sor(c, azon))
        uj, _ = sched.review_card(_fsrs_kartya(elotte, t), fsrs.Rating(jegy), review_datetime=t,
                                  review_duration=None if ms is None else int(ms))
        utana = _allapotba(uj)
        _ir_allapot(c, azon, utana)
        c.execute("INSERT INTO valasz (kartya, mikor, jegy, ms, forras, elotte, utana) VALUES (?,?,?,?,'ismetles',?,?)",
                  (azon, iso(t), jegy, None if ms is None else int(ms), json.dumps(elotte), json.dumps(utana)))
    return utana


def visszavon(cfg, azon: str, most: datetime | None = None) -> dict | None:
    """A kártya utolsó, vissza nem vont értékelésének visszavonása: az előtte-állapot pontosan vissza. → a
    visszaállt állapot, vagy None, ha nincs mit visszavonni."""
    with tanulas_db.iro(cfg) as c:
        r = c.execute("SELECT id, elotte FROM valasz WHERE kartya = ? AND forras = 'ismetles' AND visszavonva IS NULL "
                      "ORDER BY mikor DESC, id DESC LIMIT 1", (azon,)).fetchone()
        if r is None or r["elotte"] is None:
            return None
        elotte = json.loads(r["elotte"])
        _ir_allapot(c, azon, elotte)
        c.execute("UPDATE valasz SET visszavonva = ? WHERE id = ?", (iso(most_utc(most)), r["id"]))
    return elotte


def nap_kezdete(cfg, most: datetime) -> datetime:
    """A `most`-ot tartalmazó tanulási nap kezdete UTC-ben (a helyi `nap_kezdete_ora` fordulóval)."""
    ora = int(beallitas(cfg).get("nap_kezdete_ora", 4))
    helyi = most.astimezone()
    kezd = helyi.replace(hour=ora, minute=0, second=0, microsecond=0)
    if helyi < kezd:
        kezd -= timedelta(days=1)
    return most_utc(kezd)


def esedekesek(cfg, most: datetime | None = None, uj_limit: int | None = None) -> list[dict]:
    """Az esedékes kártyák: előbb a tanulásban, újratanulásban és ismétlésben esedékesek (`esedekes ≤ most`,
    esedékesség szerint), utánuk az újak a napi limitig (az aznap már elkezdett újak levonva). A törölt és a
    felfüggesztett kimarad."""
    t = most_utc(most)
    limit = int(beallitas(cfg).get("uj_naponta", 20)) if uj_limit is None else int(uj_limit)
    mezok = "azon, jegyzet, sor, forras, kerdes, valasz, " + ", ".join(MEZOK)
    with tanulas_db.olvaso(cfg) as c:
        if c is None:
            return []
        esed = [dict(r) for r in c.execute(
            f"SELECT {mezok} FROM kartya WHERE torolve IS NULL AND felfuggesztve = 0 AND allapot != 0 "
            "AND esedekes <= ? ORDER BY esedekes, azon", (iso(t),))]
        ma_kezdett = c.execute(
            "SELECT COUNT(DISTINCT kartya) FROM valasz WHERE forras = 'ismetles' AND visszavonva IS NULL AND mikor >= ? "
            "AND json_extract(elotte, '$.allapot') = 0", (iso(nap_kezdete(cfg, t)),)).fetchone()[0]
        maradek = max(0, limit - ma_kezdett)
        uj = [dict(r) for r in c.execute(
            f"SELECT {mezok} FROM kartya WHERE torolve IS NULL AND felfuggesztve = 0 AND allapot = 0 "
            "ORDER BY letrehozva, jegyzet, sor, azon LIMIT ?", (maradek,))] if maradek else []
    return esed + uj


def elorejelzes(cfg, azon: str, most: datetime | None = None, sched=None) -> dict[int, int]:
    """A négy gomb következő intervalluma másodpercben (a felület címkéihez); a DB-t nem írja."""
    import fsrs
    t = most_utc(most)
    sched = sched or utemezo(cfg)
    with tanulas_db.olvaso(cfg) as c:
        r = None if c is None else c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone()
        if r is None:
            raise ValueError(f"ismeretlen kártya: {azon}")
        a = allapot_sorbol(r)
    ki = {}
    for j in (1, 2, 3, 4):
        uj, _ = sched.review_card(_fsrs_kartya(a, t), fsrs.Rating(j), review_datetime=t)
        ki[j] = int((uj.due - t).total_seconds())
    return ki



def felidezes(a: dict, most: datetime, sched=None) -> float:
    """A kártya felidézési valószínűsége `most`-kor az FSRS-ből (py-fsrs `get_card_retrievability`): `a` az állapot
    (`allapot_sorbol` alakja), a `most` időzónás (jövőbeli is lehet: a „dolgozat napjára” előrejelzés). Az új vagy
    állapot nélküli kártya 0. A DB-t nem érinti; a felidézés csak az FSRS-súlyoktól függ (a `sched` tetszőleges)."""
    if a["allapot"] == UJ or a.get("stabilitas") is None or not a.get("utolso"):
        return 0.0
    import fsrs
    sched = sched or fsrs.Scheduler()
    t = most_utc(most)
    return float(sched.get_card_retrievability(_fsrs_kartya(a, t), t))
