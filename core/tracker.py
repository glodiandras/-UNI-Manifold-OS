"""A tracker (C27, 30. döntés): tevékenységnapló és használati mérés a `{szemelyes}/pos.sqlite` 2-es migrációjában.

A felület eseményt küld (`POST /api/tracker/esemenyek`, kötegelve), a core aggregál és tárol; a vaultba nem ír.
Ez a modul a pos.sqlite **egyetlen írója** (a `ma.py` csak `mode=ro`-val olvassa). A séma a legacy `db.py` elvét
követi (L56–L57): csak új migrációval bővül (`PRAGMA user_version`), WAL, az 1-es migráció (a naptár tábláit
a legacy hozta) változatlan — a 2.0 az 1-es táblákhoz nem nyúl, a törlés sem.

Alapból be van kapcsolva, a vezérlőben kikapcsolható (`vezerlo.kapcsolok(cfg)["tracker"]`, minden kötegnél és
minden core-oldali gyűjtésnél újraolvasva; kikapcsolva fájl sem jön létre). Csak az app eseményeit látja; a
használati mérés jegyzettartalmat nem tárol: parancsazonosítót, funkciót és számot. A gyűjtő hibája soha nem
akaszt meg mentést, gépi írást vagy feladatot.

Az aggregátumok napi bontásúak (helyi nap): aktív másodperc és szerkesztett karakter jegyzetenként, kártya- és
kvízesemények, integrált tételek (a gyűjtők a C20–C23-ban kötnek be), a parancsonkénti használat, a gépi írás
és visszavonása funkciónként, a mentési és gépelési késleltetés fix vödrös hisztogramja (napok között pontosan
összevonható; a p95 a vödör felső határa), a memóriaőr szünetei.
"""
from __future__ import annotations

import contextlib
import json
import math
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import ma, pdfkiemeles, szemelyes_db, vaultio, vezerlo
from .utvonalak import HttpError

POS_FAJL = szemelyes_db.POS_FAJL
EXPORT_MAPPA = "export"
VERZIO = 2                           # a tracker tábláit hozó migráció; a séma a `szemelyes_db`-ben él (C29: 3-as is)
MIGRACIOK = szemelyes_db.MIGRACIOK   # a közös migrációlánc (1: legacy naptár, 2: tracker, 3: emlékeztetők, C29)

_TR_TABLAK = ("tr_aktiv", "tr_karakter", "tr_esemeny", "tr_naptar_blokk", "tr_aktiv_ora")
ORA_VERZIO = 5                       # a `tr_aktiv_ora` (napszak-bontás, C30b) az 5-ös migrációban jött
_HAS_TABLAK = ("has_parancs", "has_gepi", "has_kesleltetes", "has_szunet", "has_asszisztens")

# ------------------------------------------------------------------ korlátok és fehérlisták

# A késleltetés vödrei (ms felső határ); az utolsó, túlcsordulási vödör a határon felüli. A felület ugyanezeket
# a határokat használja (`app/src/lib/tracker/kesleltetes.ts`): a kettőnek egyeznie kell.
VEDROK_MS = [1, 2, 4, 8, 16, 32, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 5000]
VEDOR_DB = len(VEDROK_MS) + 1
KESLELTETES_FAJTAK = ("gepeles", "mentes")
ESEMENY_TIPUSOK = ("kartya_valasz", "kviz_eredmeny", "integralt_video", "integralt_fuzet", "cpp_proba", "cpp_tipp")
# C36a: a C++ feladat eseményeinek `adat`-ja fehérlistás (kulcs → típus): kód és szöveg nem írható bele (TERV 5.14); a feladat
# útvonala az esemény `ut`-ja (tevékenységnapló). `cpp_proba`: egy ⌘R (a core írja); `cpp_tipp`: a tipp-lépcső szintje (C36b).
CPP_ADAT = {"cpp_proba": {"atment": bool, "tesztek": int, "atment_db": int, "fordit_ok": bool, "mod": ("gyors", "hibakereso"),
                          "ms": int},
            "cpp_tipp": {"szint": int}}
CPP_ADAT_KOTELEZO = {"cpp_proba": ("atment", "tesztek", "atment_db", "fordit_ok"), "cpp_tipp": ("szint",)}
CPP_TIPP_SZINT_MAX = 10             # a tipp-lépcső reális plafonja (A3-24): a 10 milliós szám statisztika-hamisítás
KLIENS_TILTOTT = ("cpp_proba",)     # csak core-forrásból (`cpp_utvonal`): a `POST /api/tracker/esemenyek` elveti (A3-24)
PARANCS_FORRASOK = ("billentyu", "paletta", "menu", "gomb", "hej", "egyeb")
SZUNET_TIPUSOK = ("memoria", "hutes")
PARANCS_MINTA = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
EGYEB = "Egyéb"

NAP_MAX_MP = 86400                  # egy nap nem lehet több aktív másodperc a napnál
KOTEG_AKTIV_MAX_MP = 3600           # egy köteg egy eleme legfeljebb ennyi másodperc (a kliens 30 s-onként küld)
KOTEG_KARAKTER_MAX = 1_000_000
KOTEG_ELEM_MAX = 2000
UT_MAX = 1024
ADAT_MAX = 2000                     # egy esemény JSON-adata bájtban
SZAM_MAX = 10_000_000
KESLELTETES_MAX_MS = 3_600_000     # egy késleltetés-minta legfeljebb ennyi ms (a túl nagy vágódik)
TARTOMANY_MAX_NAP = 400
NAPTAR_NAP_MAX_PERC = 12 * 60       # egy naptáresemény tervezett ideje legfeljebb ennyi (kijelölt, nem egész napos)
TERV_KATEGORIAK = ("tanulas",)     # a tervezett idő: a naptár tanulási blokkjai (az órarend, az edzés, a határidő nem)
MAX_NAPI_ELTERES = 2                # a kliens által jelölt nap legfeljebb ennyivel lehet a mai előtt

# Az esemény `adat` mezőjének fehérlistás sémája (2. audit T143; C20a): eseménytípusonként a megengedett kulcsok és
# értékeik. Jegyzettartalom, cím, útvonal és szabad szöveg NEM kerülhet bele (az útvonal az `ut` oszlopé: a tantárgyhoz).
# Az ismeretlen kulcs **kiesik** (egy újabb kliens nem veszi el az eseményt, a core-napló említi), a rossz típusú vagy
# tartományon kívüli érték az elemet dobja el (T029: `elvetve`/`okok`). Minden kulcs elhagyható. Új gyűjtő (C22, C23b, C20b,
# C21) a saját kulcsait ide veszi fel — a táblázat a szerződés. Értéktípusok: ("egesz", alsó, felső) · ("enum", értékek) ·
# ("minta", regex).
_KARTYA_ID = re.compile(r"c-[0-9a-z]{4,16}")        # a `^c-` blokkazonosító a `^` nélkül (docs/C23-TERV.md 1.)
KVIZ_AZON = re.compile(r"^KVIZ-\d{8}-\d{6}(?:-[0-9a-z]{1,12})*$")      # a kvíz azonosítója; egyezik a `modulok/kviz/formatum.AZON_RE`-vel
ADAT_SEMA: dict[str, dict[str, tuple]] = {
    "kartya_valasz": {"jegy": ("egesz", 1, 4), "ms": ("egesz", 0, 3_600_000), "kartya_id": ("minta", _KARTYA_ID)},
    # A kvíz kitöltése (`modulok/kviz/esemeny.py`, A3-05: egy séma): a core a válaszban kész `adat`-ot ad, a felület csak továbbítja.
    # A `jo`/`ossz` a C20a korai alakja (megmarad: egy régebbi kliens eseménye ne vesszen el).
    "kviz_eredmeny": {"jo": ("egesz", 0, 100_000), "ossz": ("egesz", 0, 100_000), "ms": ("egesz", 0, 86_400_000),
                      "kviz": ("minta", KVIZ_AZON), "mod": ("enum", ("teljes", "hibasak")),
                      "pont": ("egesz", 0, 100_000), "osszes": ("egesz", 0, 100_000), "szazalek": ("egesz", 0, 100),
                      "tudja": ("egesz", 0, 100_000), "szerencses": ("egesz", 0, 100_000), "tevkepzet": ("egesz", 0, 100_000),
                      "hiany": ("egesz", 0, 100_000)},
    # a videó beolvasása a vaultba (C20b hívja): a videó hossza, hány jegyzethez kötődött, és milyen biztonsággal
    "integralt_video": {"video_s": ("egesz", 0, 7 * 86_400), "jegyzet_db": ("egesz", 0, 10_000),
                        "kotes": ("enum", ("biztos", "valoszinu", "nincs"))},
    "integralt_fuzet": {"oldal_db": ("egesz", 0, 10_000), "kep_db": ("egesz", 0, 10_000)},
}
assert set(ADAT_SEMA) | set(CPP_ADAT) == set(ESEMENY_TIPUSOK) and not set(ADAT_SEMA) & set(CPP_ADAT), "minden eseménytípusnak pontosan egy sémája kell (a cpp-eseményeké a CPP_ADAT)"


def _hiba(uzenet: str) -> HttpError:
    return HttpError(400, uzenet)


def _egesz(v, nev: str, felso: int, also: int = 0, *, vag: bool = False) -> int:
    """Egész szám a [also, felso] tartományban. A nem szám, a NaN és az `also` alatti érték hiba; a `felso` feletti
    érték `vag=True`-nál a plafonra vágódik (a kötegben felgyűlt, de valós adat), különben hiba."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (math.inf, -math.inf):
        raise _hiba(f"{nev}: szám kell")
    n = int(v)
    if vag and n > felso:
        return felso
    if not also <= n <= felso:
        raise _hiba(f"{nev}: {also} és {felso} között kell lennie")
    return n


def adat_tisztit(tipus: str, adat: dict) -> tuple[dict, list[str]]:
    """Az esemény `adat`-ja a típus fehérlistás sémája szerint (T143) → (tiszta adat, elhagyott kulcsok). A rossz típusú vagy
    tartományon kívüli érték `HttpError` (az elem kimarad); az ismeretlen kulcs csendben kiesik (a hívó naplózza)."""
    sema = ADAT_SEMA[tipus]
    tiszta: dict = {}
    for kulcs, ertek in adat.items():
        leiras = sema.get(kulcs)
        if leiras is None:
            continue
        nev = f"esemenyek.adat.{kulcs}"
        if leiras[0] == "egesz":
            if isinstance(ertek, float) and not ertek.is_integer():
                raise _hiba(f"{nev}: egész szám kell")
            tiszta[kulcs] = _egesz(ertek, nev, leiras[2], leiras[1])
        elif leiras[0] == "enum":
            if ertek not in leiras[1]:
                raise _hiba(f"{nev}: ismeretlen érték")
            tiszta[kulcs] = ertek
        else:       # minta
            if not isinstance(ertek, str) or len(ertek) > 64 or not leiras[1].fullmatch(ertek):
                raise _hiba(f"{nev}: érvénytelen azonosító")
            tiszta[kulcs] = ertek
    if tipus == "kviz_eredmeny":
        for jo, ossz in (("jo", "ossz"), ("pont", "osszes")):
            if jo in tiszta and ossz in tiszta and tiszta[jo] > tiszta[ossz]:
                raise _hiba("esemenyek.adat: a jó válaszok száma nem lehet több az összesnél")
    return tiszta, sorted(k for k in adat if k not in sema)


def _elemek(v, nev: str, ellenoriz, elvetve: list[str]) -> list:
    """Egy szakasz elemei elemenként ellenőrizve (T029): az érvénytelen elem kimarad és az `elvetve`-be kerül, a többi
    megy tovább — egyetlen rossz elem nem viheti el a köteg többi részét. A nem lista szakasz és a `KOTEG_ELEM_MAX`
    feletti elemek is kimaradnak. Az `ellenoriz` az elemből a tárolandó értéket adja (vagy `HttpError`-t dob); `None`
    értéknél az elem érvényes, de nincs mit tárolni."""
    if v is None:
        return []
    if not isinstance(v, list):
        elvetve.append(f"{nev}: lista kell")
        return []
    if len(v) > KOTEG_ELEM_MAX:
        elvetve.extend([f"{nev}: legfeljebb {KOTEG_ELEM_MAX} elem"] * (len(v) - KOTEG_ELEM_MAX))
        v = v[:KOTEG_ELEM_MAX]
    ki = []
    for e in v:
        try:
            x = ellenoriz(e)
        except HttpError as h:
            elvetve.append(str(h))
            continue
        if x is not None:
            ki.append(x)
    return ki


def _ut_ertek(v, nev: str) -> str:
    if not isinstance(v, str) or not v or len(v) > UT_MAX or "\x00" in v:
        raise _hiba(f"{nev}: érvénytelen út")
    return vaultio.nfc(v)


def tantargy(cfg, ut: str | None) -> str:
    """A tantárgy a vault-út legfelső mappájának első betűjéből (`[pdf.tags]`, egyetlen térkép); ismeretlen: „Egyéb”."""
    if not ut:
        return EGYEB
    return pdfkiemeles.cimke(cfg, ut) or EGYEB


def vedor_index(ms: float) -> int:
    for i, felso in enumerate(VEDROK_MS):
        if ms <= felso:
            return i
    return len(VEDROK_MS)


def szazalek(vedrok: dict[int, tuple[int, float]], q: float) -> float | None:
    """A q-adik percentilis a hisztogramból: a vödör felső határa (a túlcsordulási vödörnél a megfigyelt maximum)."""
    n = sum(db for db, _ in vedrok.values())
    if not n:
        return None
    cel = math.ceil(q * n)
    szam = 0
    for i in sorted(vedrok):
        szam += vedrok[i][0]
        if szam >= cel:
            return float(VEDROK_MS[i]) if i < len(VEDROK_MS) else float(vedrok[i][1])
    return None


class Tracker:
    """A tracker szolgáltatása. Egy példány a core élettartamára; a kapcsolatok hívásonként nyílnak."""

    def __init__(self, cfg, mikor=datetime.now):
        self.cfg = cfg
        self.mikor = mikor
        self._szunet_alap: dict[str, tuple[int, int]] = {}      # a poll előző mintája: tipus -> (db, mp)

    # -------------------------------------------------- tároló

    def ut(self) -> Path:
        return self.cfg.path("szemelyes") / POS_FAJL

    def be(self) -> bool:
        return bool(vezerlo.kapcsolok(self.cfg)["tracker"])

    def ma_nap(self) -> str:
        return self.mikor().date().isoformat()

    @contextlib.contextmanager
    def _iro(self, **kw):
        """Író kapcsolat (migrál, WAL); egy tranzakció, kivételnél visszagörget. Közös a naptár-szinkronnal."""
        with szemelyes_db.iro(self.cfg, **kw) as c:
            yield c

    @staticmethod
    def _migral(c: sqlite3.Connection) -> None:
        szemelyes_db.migral(c)

    @contextlib.contextmanager
    def _olvaso(self):
        """Csak olvasó kapcsolat, vagy None, ha nincs fájl / még nincs 2-es séma (olvasás semmit nem hoz létre)."""
        with szemelyes_db.olvaso(self.cfg, VERZIO) as c:
            yield c

    # -------------------------------------------------- események fogadása

    def _nap(self, v) -> str:
        """A kliens által jelölt nap: csak a mai és az előző napok (éjfélen átnyúló köteg); különben ma."""
        mai = self.mikor().date()
        if isinstance(v, str):
            try:
                d = date.fromisoformat(v)
                if mai - timedelta(days=MAX_NAPI_ELTERES) <= d <= mai:
                    return d.isoformat()
            except ValueError:
                pass
        return mai.isoformat()

    def fogad(self, d: dict, *, kliens: bool = False) -> dict:
        """Egy köteg a felületről (`kliens=True`: a HTTP-útról jött; a core saját hívói — `cpp_utvonal` — `kliens`
        nélkül hívnak, így a `KLIENS_TILTOTT` események csak tőlük érkezhetnek: A3-24). Kikapcsolva `{"fogadva": false}` (nem ír, fájlt sem hoz létre). A köteg **elemenként**
        ellenőrződik (T029): az érvénytelen elem kimarad, a túlcsorduló szám a plafonra vágódik, a többi egy tranzakcióban
        íródik; a kimaradtakról a válasz `elvetve` (darab) és `okok` (legfeljebb 5) szól. Csak a nem-objektum törzs 400.
        Ha nincs mit írni (üres köteg), nem nyit adatbázist: fájlt sem hoz létre, nem migrál. Az adatbázis írási hibája a
        felületnek 503 (`db_hiba`: a kliens újraküldi), a core saját hívóinak `{"fogadva": false, "hiba"}` (nem akaszt)."""
        if not isinstance(d, dict):
            raise _hiba("JSON-objektum kell")
        if not self.be():
            return {"fogadva": False}
        elvetve: list[str] = []
        aktiv = _elemek(d.get("aktiv"), "aktiv", self._aktiv_elem, elvetve)
        karakter = _elemek(d.get("karakter"), "karakter", self._karakter_elem, elvetve)
        parancsok = _elemek(d.get("parancsok"), "parancsok", self._parancs_elem, elvetve)
        kesleltetes = self._kesleltetes_ellenoriz(d.get("kesleltetes"), elvetve)
        esemenyek = _elemek(d.get("esemenyek"), "esemenyek", lambda e: self._esemeny_elem(e, kliens), elvetve)
        valasz: dict = {"fogadva": True}
        if elvetve:
            self._naploz("fogad", f"{len(elvetve)} elem kimaradt: " + "; ".join(dict.fromkeys(elvetve)))
            valasz.update(elvetve=len(elvetve), okok=list(dict.fromkeys(elvetve))[:5])
        if not (aktiv or karakter or parancsok or kesleltetes or esemenyek):
            return valasz
        try:
            with self._iro() as c:
                for nap, ut, mp in aktiv:
                    self._aktiv(c, nap, ut, mp)
                for nap, ut, be, ki in karakter:
                    c.execute("INSERT INTO tr_karakter (nap, ut, tantargy, beszurt, torolt) VALUES (?,?,?,?,?) "
                              "ON CONFLICT(nap, ut) DO UPDATE SET beszurt = beszurt + excluded.beszurt, "
                              "torolt = torolt + excluded.torolt", (nap, ut, tantargy(self.cfg, ut), be, ki))
                nap = self.ma_nap()
                for pid, forras, db in parancsok:
                    c.execute("INSERT INTO has_parancs (nap, parancs, forras, db) VALUES (?,?,?,?) "
                              "ON CONFLICT(nap, parancs, forras) DO UPDATE SET db = db + excluded.db",
                              (nap, pid, forras, db))
                for fajta, vedrok in kesleltetes.items():
                    for i, (db, mx) in vedrok.items():
                        c.execute("INSERT INTO has_kesleltetes (nap, fajta, vedro, db, max_ms) VALUES (?,?,?,?,?) "
                                  "ON CONFLICT(nap, fajta, vedro) DO UPDATE SET db = db + excluded.db, "
                                  "max_ms = MAX(max_ms, excluded.max_ms)", (nap, fajta, i, db, mx))
                mikor = self.mikor().isoformat(timespec="seconds")
                for nap_e, tipus, ut, szoveg in esemenyek:
                    c.execute("INSERT INTO tr_esemeny (mikor, nap, tipus, tantargy, ut, adat) VALUES (?,?,?,?,?,?)",
                              (mikor, nap_e, tipus, tantargy(self.cfg, ut) if ut else EGYEB, ut, szoveg))
        except (sqlite3.Error, OSError) as e:
            self._naploz("fogad", e)
            if kliens:
                # A felület kötege: 503, hogy a kliens újrapróbálja (30(b): az 5xx-et újraküldi, a 200-at nem — a köteg
                # különben elveszne; 2026-10-14, F3). A core saját gyűjtői (`kliens` nélkül) soha nem kapnak kivételt.
                raise HttpError(503, "A tracker adatbázisa most nem írható; a felület később újraküldi a köteget.",
                                fogadva=False, db_hiba=True, kod="tracker.nem_irhato_kotegelt") from e
            return {"fogadva": False, "hiba": "a tracker adatbázisa nem írható"}
        return valasz

    # -- a köteg elemei: ellenőrzés (HttpError = az elem kimarad), a tárolandó sor visszaadása

    def _aktiv_elem(self, e) -> tuple | None:
        if not isinstance(e, dict):
            raise _hiba("aktiv: objektumok kellenek")
        ut = _ut_ertek(e.get("ut"), "aktiv.ut")
        mp = _egesz(e.get("mp"), "aktiv.mp", KOTEG_AKTIV_MAX_MP, vag=True)
        return (self._nap(e.get("nap")), ut, mp) if mp else None

    def _karakter_elem(self, e) -> tuple | None:
        if not isinstance(e, dict):
            raise _hiba("karakter: objektumok kellenek")
        ut = _ut_ertek(e.get("ut"), "karakter.ut")
        be = _egesz(e.get("beszurt"), "karakter.beszurt", KOTEG_KARAKTER_MAX, vag=True)
        ki = _egesz(e.get("torolt"), "karakter.torolt", KOTEG_KARAKTER_MAX, vag=True)
        return (self._nap(e.get("nap")), ut, be, ki) if be or ki else None

    @staticmethod
    def _cpp_adat_ellenoriz(tipus: str, adat) -> None:
        """A C++ események adata: csak a fehérlistás kulcsok, a megkövetelt típusokkal (bool, nemnegatív egész, a `mod` egy
        felsorolt érték); kód vagy szöveg így nem kerülhet a naplóba."""
        if not isinstance(adat, dict):
            raise _hiba(f"{tipus}: az adat objektum kell")
        if any(k not in CPP_ADAT[tipus] for k in adat):
            raise _hiba(f"{tipus}: ismeretlen adatkulcs")
        if any(k not in adat for k in CPP_ADAT_KOTELEZO[tipus]):
            raise _hiba(f"{tipus}: hiányzó adat")
        for k, v in adat.items():
            elv = CPP_ADAT[tipus][k]
            if elv is bool:
                ok = isinstance(v, bool)
            elif elv is int:
                ok = isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= SZAM_MAX
            else:
                ok = v in elv
            if not ok:
                raise _hiba(f"{tipus}.{k}: érvénytelen érték")
        if tipus == "cpp_proba" and adat["atment_db"] > adat["tesztek"]:
            raise _hiba("cpp_proba: az átment_db nem lehet több a teszteknél")
        if tipus == "cpp_tipp" and adat["szint"] > CPP_TIPP_SZINT_MAX:
            raise _hiba(f"cpp_tipp.szint: legfeljebb {CPP_TIPP_SZINT_MAX}")

    @staticmethod
    def _parancs_elem(e) -> tuple:
        if not isinstance(e, dict):
            raise _hiba("parancsok: objektumok kellenek")
        pid, forras = e.get("id"), e.get("forras", "egyeb")
        if not isinstance(pid, str) or len(pid) > 80 or not PARANCS_MINTA.match(pid):
            raise _hiba("parancsok.id: érvénytelen parancsazonosító")
        if forras not in PARANCS_FORRASOK:
            raise _hiba(f"parancsok.forras: ismeretlen forrás: {forras}")
        return pid, forras, _egesz(e.get("db", 1), "parancsok.db", SZAM_MAX, 1, vag=True)

    def _esemeny_elem(self, e, kliens: bool = False) -> tuple:
        if not isinstance(e, dict) or e.get("tipus") not in ESEMENY_TIPUSOK:
            raise _hiba("esemenyek: ismeretlen típus")
        if kliens and e["tipus"] in KLIENS_TILTOTT:
            raise _hiba(f"esemenyek: a {e['tipus']} eseményt a core írja, a kliens nem küldheti")
        adat = e.get("adat")
        if adat is not None and not isinstance(adat, dict):
            raise _hiba("esemenyek.adat: objektum kell")
        if e["tipus"] in CPP_ADAT:
            self._cpp_adat_ellenoriz(e["tipus"], adat)       # C36a: a cpp-események saját, szigorú sémája
        szoveg = None
        if adat is not None:
            if len(json.dumps(adat, ensure_ascii=False).encode("utf-8")) > ADAT_MAX:
                raise _hiba("esemenyek.adat: túl nagy")
            if e["tipus"] in CPP_ADAT:
                szoveg = json.dumps(adat, ensure_ascii=False)
            else:
                tiszta, elhagyott = adat_tisztit(e["tipus"], adat)
                if elhagyott:
                    self._naploz("fogad", f"{e['tipus']}: ismeretlen adat-kulcs elhagyva: {', '.join(map(str, elhagyott))}")
                szoveg = json.dumps(tiszta, ensure_ascii=False, sort_keys=True) if tiszta else None
        ut = _ut_ertek(e["ut"], "esemenyek.ut") if e.get("ut") is not None else None
        return self._nap(e.get("nap")), e["tipus"], ut, szoveg

    def _aktiv(self, c: sqlite3.Connection, nap: str, ut: str, mp: int) -> None:
        mar = c.execute("SELECT COALESCE(SUM(mp), 0) FROM tr_aktiv WHERE nap = ?", (nap,)).fetchone()[0]
        mp = max(0, min(mp, NAP_MAX_MP - mar))                      # egy nap nem több a napnál
        if not mp:
            return
        t = tantargy(self.cfg, ut)
        c.execute("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES (?,?,?,?) "
                  "ON CONFLICT(nap, ut) DO UPDATE SET mp = mp + excluded.mp", (nap, ut, t, mp))
        # C30b (K205 (a)): ugyanez napszak-bontásban, útvonal nélkül (nap × óra × tantárgy); a mai nap köteg-ja a mostani órára esik,
        # az éjfélen átnyúló (előző napra jelölt) köteg a nap utolsó órájára (23)
        ora = self.mikor().hour if nap == self.ma_nap() else 23
        c.execute("INSERT INTO tr_aktiv_ora (nap, ora, tantargy, mp) VALUES (?,?,?,?) "
                  "ON CONFLICT(nap, ora, tantargy) DO UPDATE SET mp = mp + excluded.mp", (nap, ora, t, mp))

    @staticmethod
    def _kesleltetes_ellenoriz(v, elvetve: list[str]) -> dict[str, dict[int, tuple[int, float]]]:
        """`{"gepeles": {"3": [db, max_ms], ...}, "mentes": {...}}` — a vödör sorszáma 0..VEDOR_DB-1. Az érvénytelen
        fajta vagy vödör kimarad (`elvetve`), a többi megy tovább; a túl nagy darabszám és idő a plafonra vágódik."""
        if v is None:
            return {}
        if not isinstance(v, dict):
            elvetve.append("kesleltetes: objektum kell")
            return {}
        ki: dict[str, dict[int, tuple[int, float]]] = {}
        for fajta, vedrok in v.items():
            if fajta not in KESLELTETES_FAJTAK:
                elvetve.append(f"kesleltetes: ismeretlen fajta: {fajta}")
                continue
            if not isinstance(vedrok, dict) or len(vedrok) > VEDOR_DB:
                elvetve.append("kesleltetes: vödrök objektuma kell")
                continue
            for kulcs, par in vedrok.items():
                try:
                    i = int(kulcs)
                    if not 0 <= i < VEDOR_DB or not isinstance(par, list) or len(par) != 2:
                        raise _hiba("kesleltetes: érvénytelen vödör")
                    db = _egesz(par[0], "kesleltetes.db", SZAM_MAX, vag=True)
                    mx = par[1]
                    if isinstance(mx, bool) or not isinstance(mx, (int, float)) or mx != mx or mx < 0:
                        raise _hiba("kesleltetes.max: nem negatív szám kell")
                except (TypeError, ValueError):
                    elvetve.append("kesleltetes: a vödör sorszáma egész szám")
                    continue
                except HttpError as h:
                    elvetve.append(str(h))
                    continue
                if db:
                    ki.setdefault(fajta, {})[i] = (db, float(min(mx, KESLELTETES_MAX_MS)))
        return ki

    # -------------------------------------------------- core-oldali gyűjtők (hibatűrők: soha nem akasztanak)

    def _naploz(self, hol: str, e: BaseException | str) -> None:
        print(f"[tracker] {hol}: {e}", file=sys.stderr, flush=True)

    @staticmethod
    def gepi_forras(forras: str | None) -> bool:
        """Gépi funkció-e a commit forrása: a gépi írás forrása mindig `mos-<lánc>` (L09, C29.8 T135); a `kezi`, a `pult`
        és a `pult-…` (szerkesztő, előzmény, átnevezés) a felhasználóé, az idegen alakú érték nem gépi funkció."""
        return str(forras or "").startswith("mos-")

    def gepi_iras(self, forras: str | None) -> None:
        """Egy sikeres, nem próba gépi írás (a funkció a `Mos-Forras`)."""
        if not self.gepi_forras(forras) or not self.be():
            return
        try:
            with self._iro() as c:
                c.execute("INSERT INTO has_gepi (nap, funkcio, iras, visszavonas) VALUES (?,?,1,0) "
                          "ON CONFLICT(nap, funkcio) DO UPDATE SET iras = iras + 1", (self.ma_nap(), forras))
        except (sqlite3.Error, OSError) as e:
            self._naploz("gepi_iras", e)

    def visszavonas(self, forrasok: list[str | None]) -> None:
        """Egy visszavonás: a visszavont commitok forrásai (egy kör több tételt is visszavonhat)."""
        gepi = [f for f in forrasok if self.gepi_forras(f)]
        if not gepi or not self.be():
            return
        try:
            with self._iro() as c:
                for f in gepi:
                    c.execute("INSERT INTO has_gepi (nap, funkcio, iras, visszavonas) VALUES (?,?,0,1) "
                              "ON CONFLICT(nap, funkcio) DO UPDATE SET visszavonas = visszavonas + 1", (self.ma_nap(), f))
        except (sqlite3.Error, OSError) as e:
            self._naploz("visszavonas", e)

    def esemeny(self, tipus: str, ut: str | None = None, adat: dict | None = None) -> dict:
        """Core-oldali gyűjtő (C20a): egy esemény **ugyanazon az úton és ugyanazokkal az ellenőrzésekkel**, mint a felületé
        (`fogad`: kapcsoló, fehérlistás séma, elemenkénti elvetés). → a `fogad` válasza."""
        e: dict = {"tipus": tipus}
        if ut is not None:
            e["ut"] = ut
        if adat is not None:
            e["adat"] = adat
        return self.fogad({"esemenyek": [e]})

    def integralt_video(self, ut: str, video_s: int, jegyzet_db: int, kotes: str = "nincs") -> dict:
        """Egy videó a vaultba került (C20b hívja a lánc végén): `ut` = a videóhoz tartozó jegyzet (a tantárgyhoz), a hossza
        másodpercben, hány jegyzethez kötődött, és a kötés biztossága (`biztos` | `valoszinu` | `nincs`). Útvonal és cím
        csak az `ut` oszlopba kerül, az `adat`-ba nem."""
        return self.esemeny("integralt_video", ut, {"video_s": video_s, "jegyzet_db": jegyzet_db, "kotes": kotes})

    def szunet_minta(self, tipus: str, db: int | None, mp: int | None) -> None:
        """A memóriaőr/hűtés számlálóinak mintája (a worker élettartamára kumulatív): a növekmény íródik. Az első
        minta az alapvonal; a csökkenés (a worker újraindult) új alapvonal."""
        if tipus not in SZUNET_TIPUSOK or db is None:
            return
        mp = int(mp or 0)
        elozo = self._szunet_alap.get(tipus)
        self._szunet_alap[tipus] = (int(db), mp)
        if elozo is None or int(db) < elozo[0] or mp < elozo[1]:
            return
        ddb, dmp = int(db) - elozo[0], mp - elozo[1]
        if not (ddb or dmp) or not self.be():
            return
        try:
            with self._iro() as c:
                c.execute("INSERT INTO has_szunet (nap, tipus, db, mp) VALUES (?,?,?,?) "
                          "ON CONFLICT(nap, tipus) DO UPDATE SET db = db + excluded.db, mp = mp + excluded.mp",
                          (self.ma_nap(), tipus, ddb, dmp))
        except (sqlite3.Error, OSError) as e:
            self._naploz("szunet", e)

    # -------------------------------------------------- lekérdezések

    def _tartomany(self, tol: str | None, ig: str | None, alap_napok: int = 7) -> tuple[date, date]:
        mai = self.mikor().date()
        try:
            veg = date.fromisoformat(ig) if ig else mai
            kezd = date.fromisoformat(tol) if tol else veg - timedelta(days=alap_napok - 1)
        except ValueError:
            raise _hiba("hibás dátum (ÉÉÉÉ-HH-NN kell)") from None
        if kezd > veg:
            raise _hiba("a tól nem lehet az ig után")
        if (veg - kezd).days + 1 > TARTOMANY_MAX_NAP:
            raise _hiba(f"legfeljebb {TARTOMANY_MAX_NAP} napos tartomány kérhető")
        return kezd, veg

    @staticmethod
    def _napok(kezd: date, veg: date) -> list[str]:
        return [(kezd + timedelta(days=i)).isoformat() for i in range((veg - kezd).days + 1)]

    def statisztika(self, tol: str | None = None, ig: str | None = None, bontas: str = "nap") -> dict:
        if bontas not in ("nap", "het"):
            raise _hiba("a bontás nap vagy het lehet")
        kezd, veg = self._tartomany(tol, ig)
        napok = {n: {"nap": n, "aktiv_mp": 0, "beszurt": 0, "torolt": 0, "kartya": 0, "kviz": 0, "integralt": 0,
                     "terv_mp": 0, "cpp_proba": 0, "cpp_atment": 0, "cpp_tipp": 0} for n in self._napok(kezd, veg)}
        tantargyak: dict[str, dict] = {}
        jegyzetek: list[dict] = []
        forrasok = {"kartya": False, "kviz": False, "integralt": False}
        a, b = kezd.isoformat(), veg.isoformat()
        try:
            with self._olvaso() as c:
                if c is not None:
                    for r in c.execute("SELECT nap, tantargy, ut, mp FROM tr_aktiv WHERE nap BETWEEN ? AND ?", (a, b)):
                        napok[r["nap"]]["aktiv_mp"] += r["mp"]
                        t = tantargyak.setdefault(r["tantargy"], {"tantargy": r["tantargy"], "aktiv_mp": 0, "beszurt": 0,
                                                                   "torolt": 0})
                        t["aktiv_mp"] += r["mp"]
                    for r in c.execute("SELECT nap, tantargy, beszurt, torolt FROM tr_karakter WHERE nap BETWEEN ? AND ?",
                                       (a, b)):
                        napok[r["nap"]]["beszurt"] += r["beszurt"]
                        napok[r["nap"]]["torolt"] += r["torolt"]
                        t = tantargyak.setdefault(r["tantargy"], {"tantargy": r["tantargy"], "aktiv_mp": 0, "beszurt": 0,
                                                                   "torolt": 0})
                        t["beszurt"] += r["beszurt"]
                        t["torolt"] += r["torolt"]
                    utankent = [(r["ut"], r["tantargy"], r["mp"]) for r in c.execute(
                        "SELECT ut, tantargy, SUM(mp) AS mp FROM tr_aktiv WHERE nap BETWEEN ? AND ? GROUP BY ut", (a, b))]
                    jegyzetek = self._jegyzet_lista(utankent, a)
                    kulcs = {"kartya_valasz": "kartya", "kviz_eredmeny": "kviz", "integralt_video": "integralt",
                             "integralt_fuzet": "integralt", "cpp_proba": "cpp_proba", "cpp_tipp": "cpp_tipp"}
                    for r in c.execute("SELECT nap, tipus, COUNT(*) AS db FROM tr_esemeny WHERE nap BETWEEN ? AND ? "
                                       "GROUP BY nap, tipus", (a, b)):
                        if r["tipus"] in kulcs and r["nap"] in napok:      # egy újabb app ismeretlen típusa nem dönti el a nézetet
                            napok[r["nap"]][kulcs[r["tipus"]]] += r["db"]
                    for r in c.execute("SELECT nap, COUNT(*) AS db FROM tr_esemeny WHERE tipus = 'cpp_proba' "
                                       "AND nap BETWEEN ? AND ? AND json_extract(adat, '$.atment') = 1 GROUP BY nap", (a, b)):
                        if r["nap"] in napok:
                            napok[r["nap"]]["cpp_atment"] += r["db"]
                    for r in c.execute("SELECT DISTINCT tipus FROM tr_esemeny"):
                        k = kulcs.get(r["tipus"])
                        if k in forrasok:
                            forrasok[k] = True
        except sqlite3.Error as e:
            self._naploz("statisztika", e)
        terv = self._naptar_terv(kezd, veg)
        if terv is not None:
            for n, perc in terv.items():
                if n in napok:
                    napok[n]["terv_mp"] = perc * 60
        lista = list(napok.values())
        if bontas == "het":
            lista = self._hetekre(lista)
        osszes = {k: sum(n[k] for n in lista) for k in ("aktiv_mp", "beszurt", "torolt", "kartya", "kviz", "integralt",
                                                        "terv_mp", "cpp_proba", "cpp_atment", "cpp_tipp")}
        return {"tol": a, "ig": b, "bontas": bontas, "kapcsolo": self.be(), "napok": lista, "osszes": osszes,
                "tantargyak": sorted(tantargyak.values(), key=lambda t: (-t["aktiv_mp"], t["tantargy"])),
                "jegyzetek": jegyzetek, "elerheto": {**forrasok, "terv": terv is not None}}

    def _jegyzet_lista(self, utankent: list[tuple[str, str, int]], kezdet_nap: str, n: int = 10) -> list[dict]:
        """A jegyzetenkénti top-lista a jegyzet MOSTANI útján (C33, T180): az átnevezés vagy áthelyezés előtti sorok a mostani
        névhez adódnak. A 50(c) döntés szerint olvasáskor, a vault pillanatkép-tárolójának átnevezés-commitjaiból (a `tr_*`
        táblák nem íródnak át); a térkép hibája esetén a tárolt utakon marad."""
        try:
            from .felkeszultseg import atnevezes
            t = atnevezes.terkep(self.cfg, kezdet_nap)
        except Exception as e:  # noqa: BLE001 — a követés hibája nem döntheti el a statisztikát
            self._naploz("atnevezes-kovetes", e)
            t = None
        osszeg: dict[str, list] = {}
        for ut, tant, mp in utankent:
            most = t.jelenlegi(ut) if t is not None else ut
            e = osszeg.setdefault(most, [most, tant, 0, set()])
            e[2] += mp
            if most != ut:
                e[3].add(ut)
        rend = sorted(osszeg.values(), key=lambda e: (-e[2], e[0]))[:n]
        return [{"ut": u, "tantargy": tantargy(self.cfg, u) if k else t_, "aktiv_mp": mp,
                 **({"korabbi": sorted(k)} if k else {})} for u, t_, mp, k in rend]

    @staticmethod
    def _hetekre(napok: list[dict]) -> list[dict]:
        """A napi sorok ISO-hetekre (hétfőtől) vonva; a sor `nap` kulcsa a hét hétfője."""
        ki: dict[str, dict] = {}
        for n in napok:
            d = date.fromisoformat(n["nap"])
            het = (d - timedelta(days=d.weekday())).isoformat()
            s = ki.setdefault(het, {**{k: 0 for k in n if k != "nap"}, "nap": het})
            for k, v in n.items():
                if k != "nap":
                    s[k] += v
        return list(ki.values())

    def _naptar_terv(self, kezd: date, veg: date) -> dict[str, int] | None:
        """A tervezett tanulási idő percben napokra. Ha a `tr_naptar_blokk` (a C29 naptár-szinkronja tölti, a
        Tracker-kapcsoló alatt) nem üres, onnan; különben a meglévő naptáreseményekből a `TERV_KATEGORIAK` szerinti
        (tanulás), kijelölt, nem egész napos blokkok, másolat nélkül. `None`, ha a naptáradat nem olvasható."""
        try:
            with self._olvaso() as c:
                if c is not None and c.execute("SELECT 1 FROM tr_naptar_blokk LIMIT 1").fetchone():
                    ki: dict[str, int] = {}
                    for r in c.execute("SELECT nap, kezd, veg FROM tr_naptar_blokk WHERE nap BETWEEN ? AND ?",
                                       (kezd.isoformat(), veg.isoformat())):
                        try:
                            perc = int((datetime.fromisoformat(r["veg"]) - datetime.fromisoformat(r["kezd"])).total_seconds() // 60)
                        except (TypeError, ValueError):
                            continue
                        if perc > 0:
                            ki[r["nap"]] = ki.get(r["nap"], 0) + min(perc, NAPTAR_NAP_MAX_PERC)
                    return ki
        except sqlite3.Error:
            pass
        try:
            with contextlib.closing(ma._pos(self.cfg)) as c:
                ki: dict[str, int] = {}
                for r in c.execute(
                        "SELECT r.kezd, r.veg, r.payload FROM forras_rekord r "
                        "LEFT JOIN naptar n ON n.azon = json_extract(r.payload, '$.naptar') "
                        "WHERE r.forras = 'naptar' AND r.tipus = 'esemeny' AND r.torolve IS NULL "
                        "AND substr(r.kezd, 1, 10) BETWEEN ? AND ? "
                        "AND coalesce(n.kategoria, '') IN (%s) AND coalesce(n.eltunt, '') = ''"
                        % ",".join("?" * len(TERV_KATEGORIAK)),
                        (kezd.isoformat(), veg.isoformat(), *TERV_KATEGORIAK)):
                    p = json.loads(r["payload"])
                    if p.get("egesznap") or not r["veg"]:
                        continue
                    try:
                        perc = int((datetime.fromisoformat(r["veg"]) - datetime.fromisoformat(r["kezd"])).total_seconds()
                                   // 60)
                    except ValueError:
                        continue
                    if perc > 0:
                        nap = r["kezd"][:10]
                        ki[nap] = ki.get(nap, 0) + min(perc, NAPTAR_NAP_MAX_PERC)
                return ki
        except (sqlite3.Error, OSError, ValueError):
            return None

    def hasznalat(self, tol: str | None = None, ig: str | None = None) -> dict:
        kezd, veg = self._tartomany(tol, ig, alap_napok=30)
        a, b = kezd.isoformat(), veg.isoformat()
        ki = {"tol": a, "ig": b, "kapcsolo": self.be(), "parancsok": [], "gepi": [],
              "kesleltetes": {f: {"db": 0, "p50_ms": None, "p95_ms": None, "max_ms": None} for f in KESLELTETES_FAJTAK},
              "vedrok_ms": VEDROK_MS, "szunetek": {t: {"db": 0, "mp": 0} for t in SZUNET_TIPUSOK}}
        try:
            with self._olvaso() as c:
                if c is None:
                    return ki
                par: dict[str, dict] = {}
                for r in c.execute("SELECT parancs, forras, SUM(db) AS db FROM has_parancs WHERE nap BETWEEN ? AND ? "
                                   "GROUP BY parancs, forras", (a, b)):
                    p = par.setdefault(r["parancs"], {"parancs": r["parancs"], "db": 0, "forrasok": {}})
                    p["db"] += r["db"]
                    p["forrasok"][r["forras"]] = r["db"]
                ki["parancsok"] = sorted(par.values(), key=lambda p: (-p["db"], p["parancs"]))[:200]
                for r in c.execute("SELECT funkcio, SUM(iras) AS iras, SUM(visszavonas) AS vissza FROM has_gepi "
                                   "WHERE nap BETWEEN ? AND ? GROUP BY funkcio ORDER BY iras DESC, funkcio", (a, b)):
                    iras, vissza = r["iras"], r["vissza"]
                    el = None if iras <= 0 else round(max(0.0, min(1.0, (iras - vissza) / iras)), 4)
                    ki["gepi"].append({"funkcio": r["funkcio"], "iras": iras, "visszavonas": vissza, "elfogadas": el})
                for fajta in KESLELTETES_FAJTAK:
                    vedrok = {r["vedro"]: (r["db"], r["max_ms"]) for r in c.execute(
                        "SELECT vedro, SUM(db) AS db, MAX(max_ms) AS max_ms FROM has_kesleltetes "
                        "WHERE fajta = ? AND nap BETWEEN ? AND ? GROUP BY vedro", (fajta, a, b))}
                    if vedrok:
                        ki["kesleltetes"][fajta] = {
                            "db": sum(d for d, _ in vedrok.values()), "p50_ms": szazalek(vedrok, 0.5),
                            "p95_ms": szazalek(vedrok, 0.95), "max_ms": max(m for _, m in vedrok.values()),
                            "vedrok": [vedrok.get(i, (0, 0))[0] for i in range(VEDOR_DB)]}
                for r in c.execute("SELECT tipus, SUM(db) AS db, SUM(mp) AS mp FROM has_szunet WHERE nap BETWEEN ? AND ? "
                                   "GROUP BY tipus", (a, b)):
                    ki["szunetek"][r["tipus"]] = {"db": r["db"], "mp": r["mp"]}
        except sqlite3.Error as e:
            self._naploz("hasznalat", e)
        return ki

    def napszakok(self, tol: str | None = None, ig: str | None = None) -> list[dict]:
        """Az aktív idő napszak-bontása (C30b, K205 (a)): `[{nap, ora, tantargy, mp}]` — útvonal és szöveg nélkül. Nincs fájl vagy még
        nincs 5-ös séma: üres. A tevékenység-exportba és a törlés hatókörébe (`tr_*`) tartozik."""
        kezd, veg = self._tartomany(tol, ig, alap_napok=30)
        try:
            with szemelyes_db.olvaso(self.cfg, ORA_VERZIO) as c:
                if c is None:
                    return []
                return [{"nap": r["nap"], "ora": r["ora"], "tantargy": r["tantargy"], "mp": r["mp"]} for r in c.execute(
                    "SELECT nap, ora, tantargy, mp FROM tr_aktiv_ora WHERE nap BETWEEN ? AND ? ORDER BY nap, ora, tantargy",
                    (kezd.isoformat(), veg.isoformat()))]
        except sqlite3.Error as e:
            self._naploz("napszakok", e)
            return []

    # -------------------------------------------------- export és törlés

    def export(self, tol: str | None = None, ig: str | None = None, tevekenyseg: bool = False) -> dict:
        """A Használat (kérésre a tevékenység) JSON-ja; a `{szemelyes}/export/` alá is atomi cserével íródik
        (a felület nem blob-letöltésre támaszkodik). Az útvonal nem a vaultban van. Alapból csak a használati adat (nincs
        benne jegyzetút, T111); a jegyzetutas tevékenységnapló külön fájlnévre (`hasznalat-tevekenyseggel-…`) kerül, hogy
        a két export ne írja felül egymást, és az útvonalmentesnek hitt fájl ne tartalmazzon útvonalat."""
        tartalom = {"verzio": 1, "keszult": self.mikor().isoformat(timespec="seconds"),
                    "hasznalat": self.hasznalat(tol, ig)}
        if tevekenyseg:
            tartalom["tevekenyseg"] = self.statisztika(tol, ig)
            tartalom["napszakok"] = self.napszakok(tol, ig)
        mappa = self.cfg.path("szemelyes") / EXPORT_MAPPA
        mappa.mkdir(parents=True, exist_ok=True)
        cel = mappa / f"hasznalat{'-tevekenyseggel' if tevekenyseg else ''}-{self.ma_nap()}.json"
        tmp = cel.with_name(f".{cel.name}.manifold-tmp")
        szoveg = json.dumps(tartalom, ensure_ascii=False, indent=1)
        tmp.write_text(szoveg, encoding="utf-8")
        tmp.replace(cel)
        return {"ut": str(cel), "tartalom": tartalom}

    def torles(self, mit: str) -> dict:
        """A tracker adatainak törlése (a felhasználó kérésére): csak a `tr_*` és `has_*` táblák; az 1-es migráció
        táblái érintetlenek. Fájlt nem hoz létre. A törlés `secure_delete` alatt megy, utána a WAL kiürítése és `VACUUM`
        (T110): a törölt utak és események nem maradnak a szabad lapokon. `{torolt, tisztitva}`; a tisztítás hibája nem
        hiúsítja meg a törlést (`tisztitva: false`, napló)."""
        tablak = {"tevekenyseg": _TR_TABLAK, "hasznalat": _HAS_TABLAK, "minden": _TR_TABLAK + _HAS_TABLAK}.get(mit)
        if tablak is None:
            raise _hiba("a törlés tevekenyseg, hasznalat vagy minden lehet")
        db = 0
        try:
            with self._olvaso() as c:                  # T108: az olvasó hibája is 503, nem kezeletlen kivétel
                van = c is not None
            if not van:
                return {"torolt": 0}
            with self._iro(biztonsagos=True) as c:
                for t in tablak:
                    db += c.execute(f"DELETE FROM {t}").rowcount
        except (sqlite3.Error, OSError) as e:
            self._naploz("torles", e)
            raise HttpError(503, "a tracker adatbázisa nem írható", kod="tracker.nem_irhato") from e
        try:
            tisztitva = szemelyes_db.tisztit(self.cfg)
        except (sqlite3.Error, OSError) as e:
            self._naploz("torles.tisztit", e)
            tisztitva = False
        return {"torolt": db, "tisztitva": tisztitva}


# ------------------------------------------------------------------ végpontok

def utvonalak(r) -> None:
    r.post("/api/tracker/esemenyek", lambda k: k.app.tracker.fogad(k.torzs(), kliens=True))
    r.get("/api/tracker/statisztika", lambda k: k.app.tracker.statisztika(
        k.q.get("tol") or None, k.q.get("ig") or None, k.q.get("bontas") or "nap"))
    r.get("/api/tracker/hasznalat", lambda k: k.app.tracker.hasznalat(k.q.get("tol") or None, k.q.get("ig") or None))

    def export(k):
        d = k.torzs()
        return k.app.tracker.export(d.get("tol") or None, d.get("ig") or None, bool(d.get("tevekenyseg")))
    r.post("/api/tracker/export", export)
    r.post("/api/tracker/torles", lambda k: k.app.tracker.torles(k.torzs().get("mit")))
