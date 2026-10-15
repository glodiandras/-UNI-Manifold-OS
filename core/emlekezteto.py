"""Emlékeztetők (C29, 32. döntés): a jegyzetek `- [ ] … 📅 ÉÉÉÉ-HH-NN` feladatai az Apple Emlékeztetők „Manifold”
listájába, kétirányú kipipálással — így az értesítés akkor is megérkezik a telefonra, ha az app nem fut, és ehhez
nem kell háttérdémon (TERV 5.9). A részletes szerződés: docs/C29-TERV.md (4. fejezet).

**Kulcs és leképezés.** A feladat kulcsa `sha1(NFC út + tisztított szöveg + előfordulás)`: a határidő módosítása
ugyanaz a feladat, a szöveg módosítása új (a régi tükör törlődik, az új létrejön). A `pos.sqlite` `emlekezteto`
táblája a leképezést és az **utoljára szinkronizált** állapotot (kipipáltság, cím, határidő) tartja: ez a háromutas
összevetés alapja.

**Összevetés (kipipáltság).** Jegyzet most / utoljára szinkronizált / emlékeztető most: ha csak a jegyzet változott,
az emlékeztető követi; ha csak az emlékeztető, a **jegyzet** íródik (a gépi-írás szolgáltatáson át: `csere`
alap-hash-sel, `Mos-Forras: mos-emlekezteto`, tételenként egy commit, visszavonható); ha mindkettő és ellentétesen:
**a jegyzet nyer**, az ütközés naplózva és jelezve. A cím és a határidő mindig a jegyzetből igazodik; ha a telefonon
átírták, az is ütközés (a jegyzet nyer). A telefonon törölt emlékeztetőt nem hozzuk vissza (a jegyzet ettől nem
változik). A jegyzetből eltűnt feladat még nyitott tükre törlődik (az index kész állapotában, tételkorláttal).

**Védelem.** A nyitott, mentetlen dokumentumba gép nem ír (409 → a következő körben újra); az index nem kész
állapotában nem törlünk; az emlékeztetők ír/olvas az EventKit-segéd, engedély nélkül semmi nem történik.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timedelta

from . import frame, szemelyes_db
from .index import elemzo, feladatok
from .naptar_seged import Seged, SegedHiba
from .utvonalak import HttpError
from .vaultio import Conflict, Invalid, NotFound

FORRAS = "mos-emlekezteto"
KOR_ELOTAG = "EMLEK"
_KEZDO = re.compile(r"^([ \t]*(?:[-*+]|\d+[.)])[ \t]+\[)(.)(\][ \t]+)")
_KESZ_DATUM = re.compile(r"[ \t]*✅️?[ \t]*\d{4}-\d{2}-\d{2}")


def beallitasok(cfg) -> dict:
    s = cfg.section("emlekezteto")
    return {"be": bool(s.get("be", True)), "lista": str(s.get("lista", "Manifold") or "Manifold"),
            "forras": str(s.get("forras", "") or ""), "ora": str(s.get("ora", "09:00")), "riasztas": bool(s.get("riasztas", True)),
            "lejart_nap": int(s.get("lejart_nap", 14)), "jovo_nap": int(s.get("jovo_nap", 180)),
            "huzas_perc": float(s.get("huzas_perc", 5)), "kesz_datum": bool(s.get("kesz_datum", True)),
            "torles_max": int(s.get("torles_max", 25))}


def kulcs_szamol(ut: str, szoveg: str, elofordulas: int) -> str:
    nyers = "\0".join((unicodedata.normalize("NFC", ut), unicodedata.normalize("NFC", szoveg), str(elofordulas)))
    return hashlib.sha1(nyers.encode("utf-8")).hexdigest()


def feladat_lista(index) -> list[dict]:
    """Az indexből a határidős feladatok kulccsal: `{kulcs, ut, sor, szoveg, hatarido, kesz, megszunt, elofordulas}`.
    Az `elofordulas` az azonos (út, szöveg) párok sorszáma a fájlban."""
    szamlalo: dict[tuple[str, str], int] = {}
    ki = []
    for t in feladatok.hataridosok(index):
        par = (unicodedata.normalize("NFC", t["ut"]), unicodedata.normalize("NFC", t["szoveg"]))
        n = szamlalo.get(par, 0)
        szamlalo[par] = n + 1
        ki.append({**t, "elofordulas": n, "kulcs": kulcs_szamol(t["ut"], t["szoveg"], n)})
    return ki


# ------------------------------------------------------------------ a jegyzet sora

def sor_atallit(txt: str, feladat: dict, kesz: bool, kesz_datum: str | None) -> str | None:
    """A `feladat` (a `feladat_lista` eleme) sora a `txt`-ben a megadott kipipáltsággal; `None`, ha a sor nem
    azonosítható egyértelműen (nincs ilyen feladat a fájlban). A sor azonosítása az index elemzőjével történik
    (kódblokkban álló feladat nem számít), az (út-n belüli) előfordulás sorszáma szerint; a sorvégek bájthűek."""
    j = elemzo.elemez(txt)
    szamlalo = 0
    cel = None
    for f in j.feladatok:
        hatarido = (f.get("datumok") or {}).get("hatarido")
        if not hatarido or feladatok._tiszta(f["szoveg"]) != feladat["szoveg"]:
            continue
        if szamlalo == feladat["elofordulas"]:
            cel = f
            break
        szamlalo += 1
    if cel is None or cel["allapot"] in ("-",) or (cel.get("datumok") or {}).get("hatarido") != feladat["hatarido"]:
        return None
    sorok = txt.split("\n")
    sor = sorok[cel["sor"] - 1]
    farok = "\r" if sor.endswith("\r") else ""
    sor = sor[:-1] if farok else sor
    m = _KEZDO.match(sor)
    if not m:
        return None
    ujsor = m.group(1) + ("x" if kesz else " ") + m.group(3) + sor[m.end():]
    ujsor = _KESZ_DATUM.sub("", ujsor).rstrip()
    if kesz and kesz_datum:
        ujsor += f" ✅ {kesz_datum}"
    sorok[cel["sor"] - 1] = ujsor + farok
    return "\n".join(sorok)


# ------------------------------------------------------------------ a szolgáltatás

class Emlekezteto:
    def __init__(self, cfg, index, vault, gepi, seged: Seged | None = None, publish=lambda e, **k: None,
                 mikor=datetime.now):
        self.cfg, self.index, self.vault, self.gepi = cfg, index, vault, gepi
        self.seged = seged or Seged(cfg)
        self.publish = publish
        self.mikor = mikor
        self._zar = threading.Lock()
        self._utolso_kor = ""
        self.utolso: dict = {}                      # az utolsó kör összegzése (a felületi állapothoz)

    # ---- belépés

    def szinkron(self) -> dict:
        """Egy szinkron-kör: lehúzás, összevetés, írás az emlékeztetők és a jegyzetek felé. Engedély nélkül és kikapcsolva
        nem ír. Segéd-hiba: `SegedHiba` (a hívó jelenti)."""
        b = beallitasok(self.cfg)
        if not b["be"]:
            return self._eredmeny({"allapot": "ki"})
        if not self.index.allapot().get("kesz"):
            return self._eredmeny({"allapot": "index"})
        with self._zar:
            return self._eredmeny(self._kor(b))

    def _eredmeny(self, d: dict) -> dict:
        self.utolso = {**d, "mikor": self.mikor().astimezone().isoformat(timespec="seconds")}
        return d

    # ---- a kör

    def _sorok(self) -> dict[str, dict]:
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            if c is None:
                return {}
            return {r["kulcs"]: dict(r) for r in c.execute("SELECT * FROM emlekezteto")}

    def _jegyzet_szoveg(self, t: dict) -> str:
        return f"Manifold-jegyzet: {t['ut']}"

    def _kor(self, b: dict) -> dict:
        most = self.mikor().astimezone()
        ma = most.date()
        iso = most.isoformat(timespec="seconds")
        lista = self.seged.emlekeztetok(b["lista"])
        if lista.get("allapot") != "engedelyezve":
            return {"allapot": lista.get("allapot") or "ismeretlen"}
        sorok = self._sorok()
        cel = {t["kulcs"]: t for t in feladat_lista(self.index) if not t["megszunt"]}
        rems = {r["azon"]: r for r in lista.get("emlekeztetok") or []}
        lista_uj = lista.get("lista") is None and any(s["allapot"] == "aktiv" for s in sorok.values())

        muveletek: list[dict] = []
        opok: dict[str, tuple[str, dict]] = {}          # op-azonosító → (kulcs, a sorba írandó mezők)
        kozvetlen: dict[str, dict] = {}                 # segéd-művelet nélküli sorfrissítések
        jegyzetbe: list[tuple[dict, bool, dict]] = []   # (feladat, cél-kipipáltság, a siker utáni sormezők)
        utkozesek: list[tuple[str, dict | None, str, str]] = []
        torlendo: list[tuple[str, dict]] = []

        def op(kulcs: str, m: dict, mezok: dict) -> None:
            azon = f"{kulcs}:{len(muveletek)}"
            muveletek.append({**m, "kulcs": azon})
            opok[azon] = (kulcs, mezok)

        def kesz_op(kulcs: str, s: dict, rem: dict, cel_kesz: bool) -> None:
            op(kulcs, {"op": "kesz" if cel_kesz else "nyit", "azon": s["rem_azon"]},
               {"jegyzet_kesz": int(cel_kesz), "rem_kesz": int(cel_kesz)})

        ablak_tol, ablak_ig = ma - timedelta(days=b["lejart_nap"]), ma + timedelta(days=b["jovo_nap"])
        for kulcs, t in cel.items():
            s = sorok.get(kulcs)
            if s is None or s["allapot"] == "torolve":
                if t["kesz"] or not (ablak_tol.isoformat() <= t["hatarido"] <= ablak_ig.isoformat()):
                    continue
                op(kulcs, {"op": "uj", "cim": t["szoveg"], "hatarido": t["hatarido"], "jegyzet": self._jegyzet_szoveg(t)},
                   {"_uj": True, "ut": t["ut"], "elofordulas": t["elofordulas"], "sor": t["sor"], "szoveg": t["szoveg"],
                    "hatarido": t["hatarido"], "jegyzet_kesz": 0, "rem_kesz": 0, "rem_cim": t["szoveg"],
                    "rem_hatarido": t["hatarido"], "allapot": "aktiv", "letrehozva": iso, "utolso": iso})
                continue
            if s["allapot"] == "kezi_torolt":
                continue
            rem = rems.get(s["rem_azon"])
            if rem is None:
                if lista_uj:          # a lista maga is eltűnt: újra felépítjük
                    if not t["kesz"]:
                        op(kulcs, {"op": "uj", "cim": t["szoveg"], "hatarido": t["hatarido"], "jegyzet": self._jegyzet_szoveg(t)},
                           {"_uj": True, "szoveg": t["szoveg"], "hatarido": t["hatarido"], "sor": t["sor"],
                            "jegyzet_kesz": 0, "rem_kesz": 0, "rem_cim": t["szoveg"], "rem_hatarido": t["hatarido"],
                            "allapot": "aktiv", "utolso": iso})
                else:                 # a felhasználó törölte az emlékeztetőt: nem hozzuk vissza, a jegyzet érintetlen
                    kozvetlen[kulcs] = {"allapot": "kezi_torolt", "utolso": iso}
                continue
            jn, jb, rn, rb = t["kesz"], bool(s["jegyzet_kesz"]), bool(rem["kesz"]), bool(s["rem_kesz"])
            jegyzet_valt, rem_valt = jn != jb, rn != rb
            kesz_celhoz = None
            if jegyzet_valt and not rem_valt:
                kesz_celhoz = jn
            elif rem_valt and not jegyzet_valt:
                jegyzetbe.append((t, rn, {"jegyzet_kesz": int(rn), "rem_kesz": int(rn)}))
            elif jegyzet_valt and rem_valt:
                # mindkét oldalon megváltozott, tehát (két érték között) ugyanarra: nincs mit írni, az alapállapot követi
                kozvetlen.setdefault(kulcs, {}).update({"jegyzet_kesz": int(jn), "rem_kesz": int(rn)})
            if kesz_celhoz is not None:
                kesz_op(kulcs, s, rem, kesz_celhoz)
            # a cím és a határidő a jegyzetből igazodik; a telefonon átírt érték ütközés (a jegyzet nyer)
            telefonon = (rem.get("cim") != s["rem_cim"]) or (rem.get("hatarido") != s["rem_hatarido"])
            kell = rem.get("cim") != t["szoveg"] or rem.get("hatarido") != t["hatarido"]
            if telefonon and kell:
                utkozesek.append((kulcs, t, "szerkesztve", "A címet vagy a határidőt a telefonon (az Emlékeztetőkben) írták át: "
                                                           "a jegyzet nyert, az érték visszaállt."))
            if kell:
                op(kulcs, {"op": "modosit", "azon": s["rem_azon"], "cim": t["szoveg"], "hatarido": t["hatarido"]},
                   {"rem_cim": t["szoveg"], "rem_hatarido": t["hatarido"], "hatarido": t["hatarido"], "sor": t["sor"]})
            else:
                if s["sor"] != t["sor"] or s["hatarido"] != t["hatarido"]:
                    kozvetlen.setdefault(kulcs, {}).update({"sor": t["sor"], "hatarido": t["hatarido"]})
                if telefonon:            # a telefonon a jegyzetével azonos értékre írták át: az alapállapot követi
                    kozvetlen.setdefault(kulcs, {}).update({"rem_cim": rem.get("cim"), "rem_hatarido": rem.get("hatarido")})
        # a jegyzetből eltűnt feladatok
        for kulcs, s in sorok.items():
            if kulcs in cel or s["allapot"] != "aktiv":
                continue
            rem = rems.get(s["rem_azon"])
            if rem is not None and not rem["kesz"]:
                torlendo.append((kulcs, s))
            else:
                kozvetlen[kulcs] = {"allapot": "torolve", "utolso": iso}      # a kész emlékeztető megmarad a listában
        visszatartott = len(torlendo) > b["torles_max"]
        if not visszatartott:
            for kulcs, s in torlendo:
                op(kulcs, {"op": "torol", "azon": s["rem_azon"]}, {"allapot": "torolve", "utolso": iso})

        eredmeny = {"allapot": "ok", "uj": 0, "torolt": 0, "kesz_emlekezteto": 0, "kesz_jegyzet": 0, "utkozes": 0,
                    "kesobb": 0, "hibak": []}
        sor_frissites: dict[str, dict] = {k: dict(v) for k, v in kozvetlen.items()}
        # 1. az emlékeztetők felé
        if muveletek:
            valasz = self.seged.emlekezteto_ir(b["lista"], b["forras"], b["ora"], b["riasztas"], muveletek)
            for r in valasz.get("eredmeny") or []:
                kulcs, mezok = opok.get(r.get("kulcs"), (None, None))
                if kulcs is None:
                    continue
                if not r.get("ok"):
                    if not r.get("nincs"):
                        eredmeny["hibak"].append(f"{kulcs[:8]}: {r.get('hiba') or 'ismeretlen hiba'}")
                    continue
                mezok = dict(mezok)
                if mezok.pop("_uj", False):
                    mezok.update(rem_azon=r.get("azon"), rem_kulso=r.get("kulso"))
                    eredmeny["uj"] += 1
                if mezok.get("allapot") == "torolve":
                    eredmeny["torolt"] += 1
                if "rem_kesz" in mezok:
                    eredmeny["kesz_emlekezteto"] += 1
                sor_frissites.setdefault(kulcs, {}).update(mezok)
                sor_frissites[kulcs]["utolso"] = iso
        # 2. a jegyzetek felé (gépi írás)
        for t, cel_kesz, mezok in jegyzetbe:
            allapot = self._jegyzetbe(t, cel_kesz, most.date().isoformat())
            if allapot == "ok":
                sor_frissites.setdefault(t["kulcs"], {}).update(mezok)
                sor_frissites[t["kulcs"]]["utolso"] = iso
                eredmeny["kesz_jegyzet"] += 1
            elif allapot == "kesobb":
                eredmeny["kesobb"] += 1
            elif allapot == "nincs":              # a sor nem azonosítható: a jegyzet nyer, az emlékeztető visszaáll
                s = sorok[t["kulcs"]]
                valasz = self.seged.emlekezteto_ir(b["lista"], b["forras"], b["ora"], b["riasztas"], [
                    {"op": "kesz" if t["kesz"] else "nyit", "azon": s["rem_azon"], "kulcs": t["kulcs"]}])
                if all(r.get("ok") for r in valasz.get("eredmeny") or []):
                    sor_frissites.setdefault(t["kulcs"], {}).update(jegyzet_kesz=int(t["kesz"]), rem_kesz=int(t["kesz"]), utolso=iso)
                utkozesek.append((t["kulcs"], t, "sor_nincs", "A jegyzetben a feladat sora nem azonosítható egyértelműen: "
                                                              "a jegyzet nyert, az Emlékeztető visszaállt."))
            else:
                eredmeny["hibak"].append(f"{t['kulcs'][:8]}: {allapot}")
        # 3. a leképezés mentése és az ütközések naplózása
        uj_utkozes = []
        if sor_frissites or utkozesek or visszatartott:
            with szemelyes_db.iro(self.cfg) as c:
                for kulcs, mezok in sor_frissites.items():
                    self._sor_ment(c, kulcs, mezok)
                for kulcs, t, fajta, reszlet in utkozesek:
                    azon = c.execute(
                        "INSERT INTO emlekezteto_utkozes (mikor, kulcs, ut, szoveg, fajta, reszlet) VALUES (?,?,?,?,?,?)",
                        (iso, kulcs, t["ut"] if t else None, t["szoveg"] if t else None, fajta, reszlet)).lastrowid
                    uj_utkozes.append({"id": azon, "kulcs": kulcs, "ut": t["ut"] if t else None,
                                       "szoveg": t["szoveg"] if t else None, "fajta": fajta, "reszlet": reszlet})
                if visszatartott and not c.execute(
                        "SELECT 1 FROM emlekezteto_utkozes WHERE fajta='torles_visszatartva' AND latva IS NULL").fetchone():
                    c.execute("INSERT INTO emlekezteto_utkozes (mikor, kulcs, fajta, reszlet) VALUES (?,?,?,?)",
                              (iso, "-", "torles_visszatartva",
                               f"{len(torlendo)} tükör törlődne egy körben (a határ {b['torles_max']}): a törlés visszatartva."))
        eredmeny["utkozes"] = len(uj_utkozes)
        for u in uj_utkozes:
            self.publish({"tipus": "emlekezteto_utkozes", **u})
        if any(eredmeny[k] for k in ("uj", "torolt", "kesz_emlekezteto", "kesz_jegyzet", "utkozes")):
            self.publish({"tipus": "emlekezteto_valtozas", **{k: eredmeny[k] for k in
                                                              ("uj", "torolt", "kesz_emlekezteto", "kesz_jegyzet", "utkozes")}})
        return eredmeny

    _OSZLOPOK = ("ut", "elofordulas", "sor", "szoveg", "hatarido", "rem_azon", "rem_kulso", "rem_cim", "rem_hatarido",
                 "jegyzet_kesz", "rem_kesz", "allapot", "letrehozva", "utolso")

    @classmethod
    def _sor_ment(cls, c: sqlite3.Connection, kulcs: str, mezok: dict) -> None:
        mezok = {k: v for k, v in mezok.items() if k in cls._OSZLOPOK}
        if not c.execute("SELECT 1 FROM emlekezteto WHERE kulcs=?", (kulcs,)).fetchone():
            if not {"ut", "szoveg", "hatarido", "letrehozva"} <= mezok.keys():
                return                      # nincs mit frissíteni: a sor nem létezik (pl. sikertelen létrehozás)
            c.execute("INSERT INTO emlekezteto (kulcs, ut, szoveg, hatarido, letrehozva) VALUES (?,?,?,?,?)",
                      (kulcs, mezok["ut"], mezok["szoveg"], mezok["hatarido"], mezok["letrehozva"]))
        if mezok:
            c.execute(f"UPDATE emlekezteto SET {', '.join(o + '=?' for o in mezok)} WHERE kulcs=?", [*mezok.values(), kulcs])

    # ---- írás a jegyzetbe (gépi írás)

    def _jegyzetbe(self, t: dict, cel_kesz: bool, nap: str) -> str:
        """Az emlékeztetőben kipipált feladat sora a jegyzetben. → `ok`, `kesobb` (a dokumentum nyitott/foglalt),
        `nincs` (a sor nem azonosítható), vagy a hiba szövege."""
        kesz_datum = nap if beallitasok(self.cfg)["kesz_datum"] else None
        for _ in range(2):
            try:
                o = self.vault.read(t["ut"])
            except (NotFound, Invalid):
                return "nincs"
            uj = sor_atallit(o["tartalom"], t, cel_kesz, kesz_datum)
            if uj is None:
                return "nincs"
            if uj == o["tartalom"]:
                return "ok"
            kor = self._uj_kor()
            try:
                self.gepi.ir({"kor": kor, "tetel": t["kulcs"], "forras": FORRAS, "modell": None,     # determinisztikus írás (D9)
                              "uzenet": f"emlékeztető: {t['szoveg'][:120]} — {'kész' if cel_kesz else 'újra nyitva'}",
                              "muveletek": [{"tipus": "csere", "ut": t["ut"], "tartalom": uj, "alap": o["hash"]}]})
                return "ok"
            except HttpError as e:
                if e.code == 409 and (e.data.get("nyitott") or e.data.get("foglalt")):
                    return "kesobb"
                if e.code == 409:
                    continue                # a fájl közben változott: újraolvasás
                return f"{e.code}: {e}"
            except Conflict:
                continue
            except (Invalid, OSError) as e:
                return str(e)
        return "kesobb"

    def _uj_kor(self) -> str:
        kor = frame.new_id(KOR_ELOTAG)
        while kor == self._utolso_kor:       # ugyanabban a másodpercben nem lehet két kör (az ismétlés-védelem miatt)
            time.sleep(0.25)
            kor = frame.new_id(KOR_ELOTAG)
        self._utolso_kor = kor
        return kor

    # ---- állapot a felületnek

    def allapot(self) -> dict:
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            if c is None:
                tukor, utkozesek = {"aktiv": 0, "kezi_torolt": 0, "torolve": 0}, []
            else:
                tukor = {"aktiv": 0, "kezi_torolt": 0, "torolve": 0,
                         **{r[0]: r[1] for r in c.execute("SELECT allapot, count(*) FROM emlekezteto GROUP BY allapot")}}
                utkozesek = [dict(r) for r in c.execute(
                    "SELECT id, mikor, kulcs, ut, szoveg, fajta, reszlet, latva FROM emlekezteto_utkozes "
                    "ORDER BY id DESC LIMIT 30")]
        b = beallitasok(self.cfg)
        return {"be": b["be"], "lista": b["lista"], "tukor": tukor, "utkozesek": utkozesek, "utolso": self.utolso}

    def utkozes_latva(self, azonok: list[int] | None = None) -> int:
        """Az ütközések megjelölése láttamozottnak (az összes, vagy a megadott azonosítók)."""
        most = self.mikor().astimezone().isoformat(timespec="seconds")
        with szemelyes_db.iro(self.cfg) as c:
            if azonok:
                return c.execute(f"UPDATE emlekezteto_utkozes SET latva=? WHERE latva IS NULL AND id IN ({','.join('?' * len(azonok))})",
                                 [most, *[int(a) for a in azonok]]).rowcount
            return c.execute("UPDATE emlekezteto_utkozes SET latva=? WHERE latva IS NULL", (most,)).rowcount
