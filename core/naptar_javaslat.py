"""Tanulási blokk javaslata a naptárba (C29, TERV 5.9) — **a naptárba csak jóváhagyásra ír** (D12).

A javaslatokat *források* adják (`regisztral_forras`): a C28 kiértékelője (felkészültség-becslés) később egy forrásként
csatlakozik, a javaslat alakja ugyanaz (`Javaslat`: tantárgy, téma, nap, kezdet, hossz, indok). Addig a **beépített
forrás** dolgozik (modell és kiértékelő nélkül, determinisztikusan): a közelgő dolgozatra — ha a tantárgyhoz a dolgozat
előtt nincs tanulási blokk a naptárban — legfeljebb napi egy blokkot javasol a dolgozat előtti utolsó napokra,
a szabad esti sávba (`[javaslat] sav_kezd … sav_veg`, a naptár időzített eseményeit kikerülve).

A javaslat a `naptar_javaslat` táblában él (`azon`: természetes kulcs, hogy az elvetett ne készüljön újra). A
jóváhagyás az EventKit-segéd `esemeny-ir` parancsával egy eseményt hoz létre a tanulás kategóriájú, írható naptárban;
más út a naptárba nem ír.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Callable

from . import naptar, szemelyes_db
from .naptar_seged import Seged, SegedHiba
from .utvonalak import HttpError

BEEPITETT = "alap"
RACS_PERC = 30


@dataclass
class Javaslat:
    forras: str
    azon: str                      # természetes kulcs (dolgozat + nap): az eldöntött javaslat nem készül újra
    nap: str
    kezd: str                      # ISO, helyi időzónával
    veg: str
    perc: int
    cim: str
    tantargy: str | None = None
    tema: str | None = None
    indok: str | None = None
    dolgozat: str | None = None    # a dolgozat naptár-azonosítója


FORRASOK: dict[str, Callable[[SimpleNamespace], list[Javaslat]]] = {}


def regisztral_forras(nev: str, fn: Callable[[SimpleNamespace], list[Javaslat]]) -> None:
    """Új javaslat-forrás (pl. a C28 kiértékelője). A `fn` a `ctx`-et kapja: `cfg`, `most`, `esemenyek` (a naptár
    gazdagított eseményei: `naptar.esemenyek`), `beallitasok`."""
    FORRASOK[nev] = fn


def beallitasok(cfg) -> dict:
    s = cfg.section("javaslat")
    return {"be": bool(s.get("be", True)), "perc": int(s.get("perc", 60)), "elorenezes_nap": int(s.get("elorenezes_nap", 10)),
            "max_darab": int(s.get("max_darab", 6)), "sav_kezd": str(s.get("sav_kezd", "16:00")), "sav_veg": str(s.get("sav_veg", "20:30"))}


def _ora(szoveg: str) -> time:
    h, m = szoveg.split(":")[:2]
    return time(int(h), int(m))


def _foglalt(esemenyek: list[dict]) -> list[tuple[datetime, datetime]]:
    """A naptár időzített eseményeinek időszakai (egész napos nem foglal sávot)."""
    ki = []
    for e in esemenyek:
        if e.get("egesznap"):
            continue
        k0, k1 = naptar._ido(e.get("kezd")), naptar._ido(e.get("veg"))
        if k0 and k1 and k1 > k0:
            ki.append((k0, k1))
    return ki


def szabad_sav(nap: date, foglalt: list[tuple[datetime, datetime]], b: dict, most: datetime) -> datetime | None:
    """A nap első olyan `perc` hosszú, `RACS_PERC`-rácsra eső szabad sávja a napszakon belül; mára a mostani időnél
    legalább fél órával későbbi kezdettel. `None`, ha nincs."""
    tz = most.tzinfo
    sav0, sav1 = datetime.combine(nap, _ora(b["sav_kezd"]), tz), datetime.combine(nap, _ora(b["sav_veg"]), tz)
    if nap == most.date():
        sav0 = max(sav0, most + timedelta(minutes=30))
        perc = (sav0.hour * 60 + sav0.minute + RACS_PERC - 1) // RACS_PERC * RACS_PERC     # fel a rácsra
        sav0 = sav0.replace(hour=perc // 60 % 24, minute=perc % 60, second=0, microsecond=0)
    hossz = timedelta(minutes=b["perc"])
    t = sav0
    while t + hossz <= sav1:
        if not any(k0 < t + hossz and k1 > t for k0, k1 in foglalt):
            return t
        t += timedelta(minutes=RACS_PERC)
    return None


def beepitett_forras(ctx: SimpleNamespace) -> list[Javaslat]:
    b, most = ctx.beallitasok, ctx.most
    ma = most.date()
    foglalt = _foglalt(ctx.esemenyek)
    tanulasok = [e for e in ctx.esemenyek if e["kategoria"] == "tanulas" and not e.get("egesznap")]
    ki: list[Javaslat] = []
    dolgozatok = sorted((e for e in ctx.esemenyek if e.get("fajta") == "dolgozat" and e.get("nap", "")[:10] >= ma.isoformat()
                         and e["nap"][:10] <= (ma + timedelta(days=b["elorenezes_nap"])).isoformat()),
                        key=lambda e: e["kezd"])
    for e in dolgozatok:
        nap = date.fromisoformat(e["nap"][:10])
        tantargy = (e.get("targyak") or [None])[0]
        # van-e már a tantárgyhoz tanulási blokk a dolgozat előtt (ma és a dolgozat napja között)?
        van = any(ma.isoformat() <= t["nap"][:10] <= nap.isoformat()
                  and (tantargy is None or tantargy in naptar.targy(t.get("cim", ""), ctx.targyak)) for t in tanulasok) if tantargy else False
        if van:
            continue
        napok_hatra = (nap - ma).days
        nap_jeloltek = [nap - timedelta(days=i) for i in range(1, 4) if nap - timedelta(days=i) >= ma]
        jelolt_tart = []
        for d in nap_jeloltek:
            sav = szabad_sav(d, foglalt, b, most)
            if sav is not None:
                jelolt_tart.append((d, sav))
        for d, sav in jelolt_tart:
            veg = sav + timedelta(minutes=b["perc"])
            cim = f"Tanulás: {tantargy} — {e['cim']}" if tantargy else f"Tanulás: {e['cim']}"
            ki.append(Javaslat(
                forras=BEEPITETT, azon=f"{e['azon']}|{d.isoformat()}", nap=d.isoformat(),
                kezd=sav.isoformat(timespec="seconds"), veg=veg.isoformat(timespec="seconds"), perc=b["perc"], cim=cim,
                tantargy=tantargy, tema=e["cim"], dolgozat=e["azon"],
                indok=(f"{e['cim']} {nap.isoformat()}-án ({napok_hatra} nap múlva); "
                       + (f"a(z) {tantargy} tantárgyhoz" if tantargy else "ehhez")
                       + " nincs tanulási blokk a naptárban."), ))
            foglalt.append((sav, veg))             # a következő dolgozat javaslata ne ugyanabba a sávba kerüljön
    return ki


regisztral_forras(BEEPITETT, beepitett_forras)


# CX-009: a lezárás okai, amelyeknél a következő frissítés a javaslatot újranyithatja (ha a forrás még javasolja, és a
# közös napi keretben van hely). A keret miatti lezárás csak akkor nyílik újra, ha a `_napi_foglalt` szerint a keret
# valóban felszabadult — a jóváhagyás és a frissítés ugyanazzal a függvénnyel számol, így nincs lezár–újranyit kör.
KERET_ELFOGYOTT = "keret_elfogyott"
UJRANYITHATO = ("terv_valtozott", KERET_ELFOGYOTT)


def _napi_foglalt(esemenyek: list[dict], beirt) -> dict[str, int]:
    """Napi foglalt tanulási perc (`{ÉÉÉÉ-HH-NN: perc}`): a naptár nem egész napos `tanulas` eseményei (hiányzó vagy
    hibás `kezd`/`veg` nélkül) + a beírt javaslatok, amelyek eseménye még nincs a szinkronizált naptárban."""
    foglalt: dict[str, int] = {}
    ismert = set()
    for ev in esemenyek:
        if ev.get("azon"):
            ismert.add(ev["azon"])
        if ev.get("kategoria") != "tanulas" or ev.get("egesznap"):
            continue
        kezd, veg = naptar._ido(ev.get("kezd")), naptar._ido(ev.get("veg"))
        if kezd and veg:
            nap = kezd.date().isoformat()
            foglalt[nap] = foglalt.get(nap, 0) + max(0, round((veg - kezd).total_seconds() / 60))
    for r in beirt:
        if r["esemeny_azon"] and r["esemeny_azon"] in ismert:
            continue
        foglalt[r["nap"]] = foglalt.get(r["nap"], 0) + (r["perc"] or 0)
    return foglalt



class Javaslatok:
    def __init__(self, cfg, seged: Seged | None = None, publish=lambda e, **k: None, mikor=datetime.now, index=None):
        self.cfg = cfg
        self._dontes_zar = threading.RLock()
        self.seged = seged or Seged(cfg)
        self.publish = publish
        self.mikor = mikor
        self.index = index                       # a vault indexe a forrásoknak (a C28 felkészültség-forrás témákat olvas)
        self.hiba: str | None = None             # az utolsó frissítés bukott forrásai (F6: a `GET /api/naptar/javaslatok` mutatja)
        self._naplozott_hibak: set[tuple[str, str]] = set()

    # ---- generálás

    def frissit(self) -> dict:
        with self._dontes_zar:
            return self._frissit()

    def _frissit(self) -> dict:
        """A javaslatok újraszámítása a naptárból: új javaslat csak ismeretlen `azon`-ra készül (az elvetett és a beírt
        sem), és legfeljebb `max_darab` nyitott lehet; a lejárt (a vége elmúlt) nyitott `lejart` lesz."""
        b = beallitasok(self.cfg)
        if not b["be"]:
            return {"uj": 0}
        most = self.mikor().astimezone()
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            if c is None:
                return {"uj": 0}
            ablak0 = most.replace(hour=0, minute=0, second=0, microsecond=0)
            esemenyek = naptar.esemenyek(c, ablak0 - timedelta(days=1), ablak0 + timedelta(days=b["elorenezes_nap"] + 2), self.cfg)
        ctx = SimpleNamespace(cfg=self.cfg, most=most, esemenyek=esemenyek, beallitasok=b, targyak=naptar.targyak_cfg(self.cfg),
                              index=self.index)
        javaslatok: list[Javaslat] = []
        bukott: dict[str, str] = {}
        for nev, fn in list(FORRASOK.items()):
            try:
                javaslatok += fn(ctx)
            except Exception as e:               # noqa: BLE001 — egy forrás hibája nem viheti el a többit
                bukott[nev] = f"{type(e).__name__}: {str(e)[:200]}"
        # F6 (2026-10-14): a bukott forrás látszik (a szolgáltatás `hiba` mezője, egyszer a naplóban), és a nyitott javaslatai
        # nem járnak le „a terv változott” okkal csak azért, mert a forrás most nem futott le
        self.hiba = "; ".join(f"a(z) „{n}” javaslat-forrás hibára futott ({h})" for n, h in bukott.items()) or None
        for n, h in bukott.items():
            if (n, h) not in self._naplozott_hibak:
                self._naplozott_hibak.add((n, h))
                print(f"[naptár] a(z) „{n}” javaslat-forrás hibára futott: {h}", file=sys.stderr, flush=True)
        # ha egy nem beépített forrás (pl. a C28 felkészültség) javasol egy dolgozatra, a beépített arra a dolgozatra nem
        specialis = {j.dolgozat for j in javaslatok if j.forras != BEEPITETT and j.dolgozat}
        javaslatok = [j for j in javaslatok if not (j.forras == BEEPITETT and j.dolgozat in specialis)]
        # CX-009: a tartalék forrás is a közös napi kereten belül marad. A keret számítása a jóváhagyáséval azonos
        # (`_napi_foglalt`): a még nem szinkronizált, beírt javaslat is fogy belőle, így a jóváhagyás által keret miatt
        # lezárt javaslatot a következő frissítés nem nyitja újra, amíg a keret valóban nem szabadul fel.
        from .felkeszultseg.keret import olvas as napi_keret
        from dataclasses import replace
        keret = napi_keret(self.cfg, 45)
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            sorok = c.execute("SELECT azon, allapot, hiba, nap, perc, esemeny_azon FROM naptar_javaslat").fetchall() if c else []
        # a végleges (beírt, elvetett, nem a terv változása miatt lejárt) javaslat nem nyílik újra: a keretből sem kér
        vegleges = {r["azon"] for r in sorok if r["allapot"] in ("beirva", "elvetett")
                    or (r["allapot"] == "lejart" and r["hiba"] not in UJRANYITHATO)}
        felhasznalt = _napi_foglalt(esemenyek, [r for r in sorok if r["allapot"] == "beirva"])
        kereten_belul = []
        for j in sorted(javaslatok, key=lambda j: (j.nap, j.forras == BEEPITETT, j.kezd, j.azon)):
            if j.azon in vegleges:
                continue
            perc = min(j.perc, max(0, keret - felhasznalt.get(j.nap, 0)))
            if perc <= 0:
                continue
            kezd = naptar._ido(j.kezd)
            if kezd is None:
                continue
            kereten_belul.append(replace(j, perc=perc, veg=(kezd + timedelta(minutes=perc)).isoformat(timespec='seconds')))
            felhasznalt[j.nap] = felhasznalt.get(j.nap, 0) + perc
        javaslatok = kereten_belul
        iso = most.isoformat(timespec="seconds")
        uj = []
        with szemelyes_db.iro(self.cfg) as c:
            for r in c.execute("SELECT id, veg FROM naptar_javaslat WHERE allapot='uj'").fetchall():
                veg = naptar._ido(r["veg"])
                if veg is None or veg <= most:
                    c.execute("UPDATE naptar_javaslat SET allapot='lejart', dontve=? WHERE id=?", (iso, r["id"]))
            jelolt = {j.azon for j in javaslatok}
            for sor in c.execute("SELECT id, azon, forras FROM naptar_javaslat WHERE allapot='uj'").fetchall():
                if sor['azon'] not in jelolt and sor['forras'] not in bukott:
                    c.execute("UPDATE naptar_javaslat SET allapot='lejart', hiba='terv_valtozott', dontve=? WHERE id=?", (iso, sor['id']))
            nyitott = c.execute("SELECT count(*) FROM naptar_javaslat WHERE allapot='uj'").fetchone()[0]
            for j in javaslatok:
                regi = c.execute("SELECT id, allapot, hiba FROM naptar_javaslat WHERE azon=?", (j.azon,)).fetchone()
                if regi:
                    if regi['allapot'] == 'lejart' and regi['hiba'] in UJRANYITHATO and nyitott < b['max_darab']:
                        c.execute("UPDATE naptar_javaslat SET allapot='uj', hiba=NULL, dontve=NULL WHERE id=?", (regi['id'],))
                        nyitott += 1
                        uj.append(regi['id'])
                    if regi['allapot'] == 'uj' or regi['hiba'] in UJRANYITHATO:
                        c.execute("UPDATE naptar_javaslat SET kezd=?, veg=?, perc=?, cim=?, tema=?, indok=? WHERE id=?",
                                  (j.kezd, j.veg, j.perc, j.cim, j.tema, j.indok, regi['id']))
                    continue
                if nyitott >= b["max_darab"]:
                    break
                azon = c.execute(
                    "INSERT INTO naptar_javaslat (forras, azon, nap, kezd, veg, perc, cim, tantargy, tema, indok, dolgozat, letrehozva) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (j.forras, j.azon, j.nap, j.kezd, j.veg, j.perc, j.cim, j.tantargy, j.tema, j.indok, j.dolgozat, iso)).lastrowid
                nyitott += 1
                uj.append(azon)
        if uj:
            self.publish({"tipus": "naptar_javaslat", "uj": len(uj)})
        return {"uj": len(uj), **({"hiba": self.hiba} if self.hiba else {})}

    # ---- olvasás

    def lista(self, csak_nyitott: bool = True) -> list[dict]:
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            if c is None:
                return []
            where = "WHERE allapot='uj' " if csak_nyitott else ""
            return [dict(r) for r in c.execute(f"SELECT * FROM naptar_javaslat {where}ORDER BY kezd LIMIT 100")]

    def _egy(self, azon: int) -> dict:
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            r = c.execute("SELECT * FROM naptar_javaslat WHERE id=?", (azon,)).fetchone() if c else None
        if r is None:
            raise HttpError(404, "nincs ilyen javaslat")
        return dict(r)

    # ---- döntés

    def elvet(self, azon: int) -> dict:
        with self._dontes_zar:
            return self._elvet(azon)

    def _elvet(self, azon: int) -> dict:
        j = self._egy(azon)
        if j["allapot"] != "uj":
            raise HttpError(409, f"a javaslat már el van döntve ({j['allapot']})")
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("UPDATE naptar_javaslat SET allapot='elvetett', dontve=? WHERE id=?", (self._most(), azon))
        self.publish({"tipus": "naptar_javaslat", "elvetett": azon})
        return {"ok": True, "id": azon, "allapot": "elvetett"}

    def _most(self) -> str:
        return self.mikor().astimezone().isoformat(timespec="seconds")

    def _naptarak(self) -> list[dict]:
        cel = beallitasok_tanulas(self.cfg)
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            lista = [dict(r) for r in c.execute("SELECT azon, nev FROM naptar WHERE kategoria='tanulas' AND utod IS NULL "
                                                "AND coalesce(eltunt,'')='' ORDER BY nev")] if c else []
        if cel:
            talalt = [n for n in lista if n["azon"] == cel or naptar.norm(n["nev"]) == naptar.norm(cel)]
            return talalt
        return lista

    def jovahagy(self, azon: int) -> dict:
        with self._dontes_zar:
            return self._jovahagy(azon)

    def _jovahagy(self, azon: int) -> dict:
        """A javaslat beírása a naptárba (csak a felhasználó jóváhagyására). → `{ok, id, allapot, esemeny}`; ha nincs
        írható tanulás-naptár vagy a sáv közben foglalt lett: a javaslat `lejart`/`hiba` jelzéssel marad megőrizve."""
        j = self._egy(azon)
        if j["allapot"] != "uj":
            raise HttpError(409, f"a javaslat már el van döntve ({j['allapot']})")
        most = self.mikor().astimezone()
        k0, k1 = naptar._ido(j["kezd"]), naptar._ido(j["veg"])
        if k0 is None or k1 is None or k1 <= most:
            self._lezar(azon, "lejart", "a javasolt idő már elmúlt")
            raise HttpError(409, "a javasolt idő már elmúlt")
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            esemenyek = naptar.esemenyek(c, k0 - timedelta(days=1), k1 + timedelta(days=1), self.cfg) if c else []
        if any(a < k1 and b > k0 for a, b in _foglalt(esemenyek)):
            self._lezar(azon, "lejart", "a sáv közben foglalt lett")
            raise HttpError(409, "a javasolt sáv közben foglalt lett a naptárban")
        from .felkeszultseg.keret import olvas as napi_keret
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            beirt = c.execute("SELECT nap, perc, esemeny_azon FROM naptar_javaslat WHERE allapot='beirva' AND nap=?",
                              (j['nap'],)).fetchall() if c else []
        foglalt_perc = _napi_foglalt(esemenyek, beirt).get(j['nap'], 0)
        if foglalt_perc + j['perc'] > napi_keret(self.cfg):
            self._lezar(azon, 'lejart', KERET_ELFOGYOTT)
            raise HttpError(409, 'A napi tanulási keret közben elfogyott vagy megváltozott. Frissítsd a javaslatokat.')
        naptarak = self._naptarak()
        if not naptarak:
            raise HttpError(409, "nincs tanulás kategóriájú naptár, amelybe a blokk beírható volna "
                                 "(a vezérlőben kategorizáld a naptárakat, vagy add meg a `[naptar] tanulas_naptar` kulcsot)")
        jegyzet = f"Manifold-javaslat #{azon}\n{j['indok'] or ''}".strip()
        hiba = None
        for n in naptarak:
            try:
                r = self.seged.esemeny_ir(n["azon"], j["cim"], j["kezd"], j["veg"], jegyzet, azon)
                break
            except SegedHiba as e:
                hiba = str(e)
        else:
            raise HttpError(502, f"a naptárba nem sikerült beírni: {hiba}")
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("UPDATE naptar_javaslat SET allapot='beirva', esemeny_azon=?, dontve=? WHERE id=?",
                      (r.get("azon"), self._most(), azon))
        self.publish({"tipus": "naptar_javaslat", "beirva": azon})
        return {"ok": True, "id": azon, "allapot": "beirva", "esemeny": r.get("azon"), "naptar": r.get("naptar")}

    def _lezar(self, azon: int, allapot: str, hiba: str) -> None:
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("UPDATE naptar_javaslat SET allapot=?, hiba=?, dontve=? WHERE id=?", (allapot, hiba, self._most(), azon))
        self.publish({"tipus": "naptar_javaslat", "lezarva": azon})


def beallitasok_tanulas(cfg) -> str:
    return naptar.beallitasok(cfg)["tanulas_naptar"]
