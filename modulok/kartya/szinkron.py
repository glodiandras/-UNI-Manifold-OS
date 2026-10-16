"""A kártyamappa és a `tanulas.sqlite` egyeztetése (`docs/C23-TERV.md` 2.4).

A vault az igazság a kártya **szövegére**, a `tanulas.sqlite` az **állapotára**, az azonosítóhoz kötve: a szöveg
szerkesztése csak a gyorsítótárat és a `szoveg_hash`-t írja, a történet megmarad; a másik fájlba költözött
azonosító a történetével költözik; a törölt kártya sírkövet kap (a generálás nem hozza vissza), a visszatérő
azonosító feltámad. A vaulthoz csak olvasva nyúl.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from core import tanulas_db, utkapu

from . import formatum


def most_utc(most: datetime | None = None) -> datetime:
    """UTC, másodpercre vágva (a py-fsrs `timezone.utc`-t kér; a tárolt idők másodpercesek)."""
    d = most or datetime.now(timezone.utc)
    if d.tzinfo is None:
        raise ValueError("az időpont legyen időzónás")
    return d.astimezone(timezone.utc).replace(microsecond=0, tzinfo=timezone.utc)


def iso(d: datetime | None) -> str | None:
    return None if d is None else most_utc(d).isoformat()


def ido(s: str | None) -> datetime | None:
    return None if not s else most_utc(datetime.fromisoformat(s))


def beallitas(cfg) -> dict:
    return cfg.section("kartya")


def mappa(cfg) -> str:
    return beallitas(cfg).get("mappa", formatum.ALAP_MAPPA)


def olvas_mappa(cfg) -> dict[str, formatum.Elemzes]:
    """A kártyamappa `.md` fájljai elemezve: {vault-relatív NFC út: elemzés}. Csak olvas; a rejtett fájl és a
    vaulton kívülre mutató symlink kimarad."""
    vault = cfg.path("vault")
    gyoker = vault / mappa(cfg)
    ki: dict[str, formatum.Elemzes] = {}
    if not gyoker.is_dir():
        return ki
    for dp, dn, fn in os.walk(gyoker):
        dn[:] = sorted(d for d in dn if not d.startswith("."))
        for f in sorted(fn):
            p = Path(dp) / f
            if f.startswith(".") or not f.endswith(".md") or not utkapu.belul(str(vault), str(p)):
                continue
            rp = formatum.nfc(os.path.relpath(p, vault))
            ki[rp] = formatum.elemez(p.read_bytes().decode("utf-8", errors="replace"))
    return ki


def latott_kartyak(elemzesek: dict[str, formatum.Elemzes]) -> tuple[dict[str, tuple[str, formatum.Kartya]], list[dict]]:
    """Az ütemezhető kártyák azonosító szerint: az első előfordulás (út, majd sor szerint) él → ({azon: (út, kártya)},
    hibák). A fájlon belüli és a fájlok közötti duplikátum is hiba."""
    latott: dict[str, tuple[str, formatum.Kartya]] = {}
    hibak: list[dict] = []
    for ut in sorted(elemzesek):
        e = elemzesek[ut]
        hibak += [{"ut": ut, **h} for h in e.hibak]
        for k in formatum.ervenyes(e):
            if k.azon in latott:
                hibak.append({"ut": ut, "sor": k.sor, "fajta": "duplikalt", "szoveg": k.azon})
            else:
                latott[k.azon] = (ut, k)
    return latott, hibak


def szinkron(cfg, elemzesek: dict[str, formatum.Elemzes] | None = None, *, teljes: bool | None = None,
             most: datetime | None = None, eredet: str = "kezi") -> dict:
    """Az elemzett kísérőjegyzetek kártyái a `tanulas.sqlite`-ba. `elemzesek` nélkül a teljes kártyamappa
    (`teljes=True`: a DB-ben élő, de sehol nem látott kártya törölt); megadva csak azokra a fájlokra (`teljes=False`):
    törölt az a kártya, amely a DB szerint ezekben élt, és most sehol nem látszik. Ha a törlés több lenne a
    `[kartya] torles_max`-nál, nem töröl, csak figyelmeztet. → jelentés."""
    if elemzesek is None:
        elemzesek, teljes = olvas_mappa(cfg), True if teljes is None else teljes
    teljes = bool(teljes)
    t = iso(most_utc(most))
    latott, hibak = latott_kartyak(elemzesek)
    jel = {"uj": 0, "frissult": 0, "szoveg_valtozott": 0, "torolt": 0, "feltamadt": 0, "hibak": hibak,
           "figyelmeztetes": None}
    torles_max = int(beallitas(cfg).get("torles_max", 50))
    with tanulas_db.iro(cfg) as c:
        meglevo = {r["azon"]: r for r in c.execute("SELECT azon, jegyzet, szoveg_hash, torolve FROM kartya")}
        for azon, (ut, k) in latott.items():
            h = k.szoveg_hash()
            r = meglevo.get(azon)
            if r is None:
                # a gép írta kísérőjegyzet (`Modell` kitöltve) kártyája akkor is `gep`, ha a core szinkronja látja előbb (C23b)
                er = eredet if eredet != "kezi" else ("gep" if elemzesek[ut].modell else "kezi")
                c.execute("INSERT INTO kartya (azon, jegyzet, sor, forras, kerdes, valasz, szoveg_hash, eredet, letrehozva, "
                          "utoljara_latva, allapot, esedekes) VALUES (?,?,?,?,?,?,?,?,?,?,0,?)",
                          (azon, ut, k.sor, k.forras, k.kerdes, k.valasz, h, er, t, t, t))
                jel["uj"] += 1
                continue
            c.execute("UPDATE kartya SET jegyzet = ?, sor = ?, forras = ?, kerdes = ?, valasz = ?, utoljara_latva = ? "
                      "WHERE azon = ?", (ut, k.sor, k.forras, k.kerdes, k.valasz, t, azon))
            jel["frissult"] += 1
            if r["szoveg_hash"] != h:
                c.execute("UPDATE kartya SET szoveg_hash = ?, szoveg_valtozott = ? WHERE azon = ?", (h, t, azon))
                jel["szoveg_valtozott"] += 1
            if r["torolve"] is not None:
                c.execute("UPDATE kartya SET torolve = NULL WHERE azon = ?", (azon,))
                jel["feltamadt"] += 1
        hatokor = set(elemzesek)
        jeloltek = [a for a, r in meglevo.items() if r["torolve"] is None and a not in latott
                    and (teljes or r["jegyzet"] in hatokor)]
        if len(jeloltek) > torles_max:
            jel["figyelmeztetes"] = (f"{len(jeloltek)} kártya tűnt el egyszerre (a korlát {torles_max}): a szinkron "
                                     "nem jelölte töröltnek őket")
        else:
            for a in jeloltek:
                r = c.execute("SELECT kerdes, forras FROM kartya WHERE azon = ?", (a,)).fetchone()
                c.execute("UPDATE kartya SET torolve = ? WHERE azon = ?", (t, a))
                c.execute("INSERT OR REPLACE INTO sirko (ujjlenyomat, kartya, mikor) VALUES (?,?,?)",
                          (formatum.ujjlenyomat(r["kerdes"], r["forras"]), a, t))
            jel["torolt"] = len(jeloltek)
    return jel


def foglalt_azonositok(cfg, elemzesek: dict[str, formatum.Elemzes] | None = None) -> set[str]:
    """A már használt azonosítók (a DB és a megadott elemzések): az új azonosító ezek ellen ütközésmentes."""
    ki = {k.azon for e in (elemzesek or {}).values() for k in e.kartyak if k.azon}
    with tanulas_db.olvaso(cfg) as c:
        if c is not None:
            ki |= {r[0] for r in c.execute("SELECT azon FROM kartya")}
    return ki
