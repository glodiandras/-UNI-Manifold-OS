"""Hasonló jegyzetek a vektortárból, modell nélkül (C25c; K273).

A jegyzet-vektor a jegyzet darabvektorainak normált átlaga; a többi jegyzet pontja a darabjai közül a jegyzet-vektorhoz
legközelebbié (koszinusz, `Vektortar.jegyzet_hasonlosag`). A beágyazás már kész (a `vektorindex` feladat építi): itt sem
modell, sem worker nem kell. Ha a jegyzetnek még nincs vektora, az `allapot` ezt mondja ki (`nincs_vektor`), és modell nem
töltődik; ha a vektor a jegyzet egy korábbi változatáé, a válasz `elavult: true`.

Kimarad: maga a jegyzet, a gépi kísérőjegyzetek (a `[vault] kisero_elotag` szerinti mappa: a kártya, a kvíz, az összefoglaló — a forrásuk
másolatai volnának az élen), a törölt és a nem `.md` fájl. Találatonként a link-helyzet is (a C30b linkjavaslata a még nem
linkelteket keresi): `kimeno` (a jegyzet már linkeli), `bejovo` (az linkeli ezt a jegyzetet). A link-feloldás az indexé (L42).

| Hívás | Válasz |
|---|---|
| `hasonlok(…, ut, n)` | `{ut, allapot: ok \\| nincs_tar \\| nincs_vektor \\| nem_jegyzet, elavult, talalatok: [{ut, pont, kimeno, bejovo}]}` |
| `hasonlosag(…, ut, celok)` | `{ut, allapot, elavult, pontok: {cél: pont \\| null}}` (a C30b: a lexikai javaslatok szűrője) |
"""
from __future__ import annotations

import unicodedata

from ... import kiserok
from ...vaultio import Invalid, NotFound
from ...hibakod import kodol
from .frissites import aktualis_darabolas

MAX_CEL = 500


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def kisero(ut: str, elotag: str = kiserok.ALAP_ELOTAG) -> bool:
    """Kísérőjegyzet-e (egy útvonal-eleme az `elotag`-gal kezdődik; a core a `[vault] kisero_elotag` értékét adja)."""
    return kiserok.kisero_ut(ut, elotag)


def _alap(index_olvaso, tar, ut) -> tuple[dict, dict | None, set[str], int | None]:
    """(válasz-alap, pontok, élő jegyzetek, fájl-azonosító)."""
    if not isinstance(ut, str) or not ut.strip():
        raise kodol(Invalid("hiányzik az `ut`"), "hibrid.hasonlo.hianyzik_ut")
    ut = _nfc(ut.strip())
    with index_olvaso() as c:
        r = c.execute("SELECT id, hash, tipus FROM fajl WHERE ut = ? AND torolve IS NULL", (ut,)).fetchone()
        if r is None:
            raise kodol(NotFound(f"nincs ilyen fájl: {ut}"), "hibrid.hasonlo.nincs_ilyen_fajl_ut", {"ut": ut})
        fid, h, tipus = r[0], r[1], r[2]
        elo = {x[0] for x in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL AND tipus = 'md'")}
    alap = {"ut": ut, "allapot": "ok", "elavult": False}
    if tipus != "md":
        return {**alap, "allapot": "nem_jegyzet"}, None, elo, fid
    if tar is None:
        return {**alap, "allapot": "nincs_tar"}, None, elo, fid
    if not aktualis_darabolas(tar.modell_kulcs()):
        return {**alap, "allapot": "nincs_vektor", "elavult": True}, None, elo, fid
    pontok = tar.jegyzet_hasonlosag(ut)
    if pontok is None:
        return {**alap, "allapot": "nincs_vektor"}, None, elo, fid
    alap["elavult"] = tar.jegyzet_hash(ut) != h
    return alap, pontok, elo, fid


def hasonlok(index_olvaso, tar, ut: str, n: int = 10, elotag: str = kiserok.ALAP_ELOTAG, kizart=None) -> dict:
    alap, pontok, elo, fid = _alap(index_olvaso, tar, ut)
    if pontok is None:
        return {**alap, "talalatok": []}
    ut = alap["ut"]
    jeloltek = sorted(((u, p) for u, p in pontok.items() if u != ut and u in elo and not kisero(u, elotag)
                       and not (kizart and kizart.kizart(u))),
                      key=lambda x: (-x[1], x[0]))[:max(1, int(n))]
    with index_olvaso() as c:
        kimeno = {x[0] for x in c.execute("SELECT DISTINCT cel FROM link WHERE forras_id = ? AND cel IS NOT NULL", (fid,))}
        bejovo = {x[0] for x in c.execute("SELECT DISTINCT f.ut FROM link l JOIN fajl f ON f.id = l.forras_id "
                                          "WHERE l.cel = ? AND f.torolve IS NULL", (ut,))}
    return {**alap, "talalatok": [{"ut": u, "pont": p, "kimeno": u in kimeno, "bejovo": u in bejovo} for u, p in jeloltek]}


def hasonlosag(index_olvaso, tar, ut: str, celok) -> dict:
    if not isinstance(celok, list) or not all(isinstance(x, str) for x in celok):
        raise kodol(Invalid("a `celok` utak listája"), "hibrid.hasonlo.celok_utak_listaja")
    if len(celok) > MAX_CEL:
        raise kodol(Invalid(f"legfeljebb {MAX_CEL} cél kérdezhető egyszerre"), "hibrid.hasonlo.legfeljebb_max_cel_cel_kerdezheto", {"MAX_CEL": MAX_CEL})
    alap, pontok, elo, _ = _alap(index_olvaso, tar, ut)
    pontok = pontok or {}
    return {**alap, "pontok": {c: (pontok.get(_nfc(c)) if _nfc(c) in elo else None) for c in celok}}
