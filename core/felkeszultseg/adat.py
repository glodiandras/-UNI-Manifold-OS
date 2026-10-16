"""A felkészültség bemenetei (C28a): egy kérés egy `Adatok` példány, amely a forrásokat **egyszer, lustán, csak
olvasva** tölti be — naptár (`pos.sqlite`, `mode=ro`), a vault indexe, a kártyák (`tanulas.sqlite`, `mode=ro`), a
tracker (`tr_aktiv`), a kvíz-illesztő (`forrasok`) és az átnevezés-térkép (`atnevezes`).

Egyetlen forrás hiánya (nincs `tanulas.sqlite`, nincs `pos.sqlite`, nincs kvíz-forrás, még épülő index, nincs tároló)
nem hiba: a megfelelő összetevő „nincs adat”, a `figyelmeztetesek` és az `adatok` mezők megmondják, mi és miért hiányzik.
Semmit nem hoz létre, nem migrál, nem ír.
"""
from __future__ import annotations

import contextlib

import posixpath
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .. import naptar, szemelyes_db, tanulas_db
from . import atnevezes, eredmeny, forrasok, keplet, kotes, rekonstrukcio, temak


class Hiany(Exception):
    """Egy bemenet nem áll rendelkezésre; az üzenet a felhasználónak szól."""


@dataclass(frozen=True)
class Menet:
    """A `[felkeszultseg]` szakasz nem-képlet kulcsai."""
    elore_nap: int = 60
    mult_nap: int = 3
    ablak_nap: int = 21
    napi_perc: int = 45
    szelet_perc: int = 15
    max_terv_nap: int = 21
    gyenge_kartya_db: int = 5
    atnevezes_kovetes: bool = True
    dolgozat_mappa: str = "Dolgozatok"
    naptar_regi_ora: float = 36
    kalibracio_min: int = 8                    # C28b: ennyi kalibrációs pont alatt a súlyok nem változnak
    kalibracio_elotte_nap: int = 3             # a kalibrációs pont becslése a dolgozat előtti D−N. nap végén
    kalibracio_vissza_nap: int = 400           # ennyi napra visszamenőleg keres lezárt dolgozatot
    kalibracio_ridge: float = 0.1              # a húzás az induló súlyok felé (λ)
    kiertekelo_nevek: tuple = ("Dolgozat kiértékelő", "Dolgozat Napló")     # a kiértékelő jegyzetek névrészletei (L59)

    @classmethod
    def cfg_bol(cls, cfg) -> "Menet":
        s = cfg.section("felkeszultseg")
        ki = {}
        for nev in ("elore_nap", "mult_nap", "ablak_nap", "napi_perc", "szelet_perc", "max_terv_nap", "gyenge_kartya_db",
                    "kalibracio_min", "kalibracio_elotte_nap", "kalibracio_vissza_nap"):
            v = s.get(nev)
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                ki[nev] = v
        v = s.get("kalibracio_ridge")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            ki["kalibracio_ridge"] = float(v)
        if isinstance(s.get("atnevezes_kovetes"), bool):
            ki["atnevezes_kovetes"] = s["atnevezes_kovetes"]
        n = cfg.section("naplo")
        if isinstance(n.get("dolgozat_mappa"), str) and n["dolgozat_mappa"]:
            ki["dolgozat_mappa"] = n["dolgozat_mappa"]
        if isinstance(n.get("naptar_regi_ora"), (int, float)):
            ki["naptar_regi_ora"] = n["naptar_regi_ora"]
        if isinstance(n.get("kiertekelo_nevek"), list) and n["kiertekelo_nevek"] and all(isinstance(x, str) and x for x in n["kiertekelo_nevek"]):
            ki["kiertekelo_nevek"] = tuple(n["kiertekelo_nevek"])
        from .keret import olvas
        ki["napi_perc"] = olvas(cfg, ki.get("napi_perc", cls.napi_perc))
        m = cls(**ki)
        if m.szelet_perc < 1 or m.napi_perc < m.szelet_perc:
            return cls(**{**ki, "napi_perc": cls.napi_perc, "szelet_perc": cls.szelet_perc})
        return m


def _helyi_nap(iso: str | None) -> date | None:
    try:
        return datetime.fromisoformat(iso).astimezone().date() if iso else None
    except ValueError:
        return None


class Adatok:
    def __init__(self, cfg, index, most: datetime | None = None, olvas=None, rekonstrukcio: bool = False,
                 visszamenoleg_nap: int = 0):
        """`olvas(vault_ut) → szöveg`: a vault jegyzetének szövege (csak olvasva; az eredmény-kinyerőnek kell — nélküle nincs eredmény).
        `rekonstrukcio` (C28b): a `most` egy **múltbeli** időpont, és a kártyák, a tracker és a kvíz az akkori állapotukban töltődnek
        (`rekonstrukcio.py`): a becslés egy lezárt dolgozat D−N. napjára. `visszamenoleg_nap`: a naptár-ablak és a kötés ennyivel
        tovább nyúlik vissza (a lezárt dolgozatok kalibrációs gyűjtéséhez)."""
        self.cfg = cfg
        self.index = index
        self.most = (most or datetime.now()).astimezone()
        self.ma = self.most.date()
        self.olvas = olvas
        self.rekonstrukcio = bool(rekonstrukcio)
        self.visszamenoleg_nap = max(0, int(visszamenoleg_nap))
        self._eredmenyek: dict[str, dict] | None = None
        self.b = keplet.Beallitas.cfg_bol(cfg)
        self.m = Menet.cfg_bol(cfg)
        self.figyelmeztetesek: list[str] = []
        self.adatok: dict[str, dict] = {}
        self._naptar: dict | None = None
        self._kartyak: list[dict] | None = None
        self._kartya_valasz: dict[str, str] = {}
        self._aktiv: dict[str, list[tuple[str, int]]] | None = None
        self._kviz: list[forrasok.KvizEredmeny] | None = None
        self._terkep: atnevezes.Terkep | None = None
        self._jegyzetek: list[kotes.Jegyzet] | None = None
        self._kotesek: kotes.Kotesek | None = None
        self._temak: dict[str, temak.Temak] = {}
        self._kartya_temak: dict[tuple[str, str], str | None] = {}
        self._temankent: dict[str, list[dict]] | None = None
        self._sched = None
        # CX-009: a dolgozatok közös napi terve (`osszesit.terv_szamolas`), menetenként egyszer számolva; None = még nincs
        self.kozos_tervek: dict | None = None

    # ------------------------------------------------------------------ naptár és kötés

    def figyelmeztet(self, szoveg: str) -> None:
        if szoveg and szoveg not in self.figyelmeztetesek:
            self.figyelmeztetesek.append(szoveg)

    @contextlib.contextmanager
    def figyelmeztetes_nelkul(self):
        """Egy MÁSIK dolgozat segédszámítása (pl. a közös tervhez): az alatta keletkező figyelmeztetések nem kerülnek a
        vizsgált dolgozat `figyelmeztetesek` listájába (CX-009)."""
        mentett = list(self.figyelmeztetesek)
        try:
            yield
        finally:
            self.figyelmeztetesek[:] = mentett

    def index_kesz(self) -> bool:
        try:
            return bool(self.index.allapot().get("kesz"))
        except Exception:                          # noqa: BLE001
            return False

    def naptar(self) -> dict:
        """`{esemenyek, utolso_szinkron, regi}`: a naptár eseményei a dolgozat-ablak körül (a kötéshez szélesebben)."""
        if self._naptar is not None:
            return self._naptar
        nap0 = datetime.combine(self.ma, time.min, tzinfo=self.most.tzinfo)
        tol = nap0 - timedelta(days=self.m.mult_nap + self.visszamenoleg_nap + ATHELYEZES_KOZ)
        ig = nap0 + timedelta(days=self.m.elore_nap + 1 + ATHELYEZES_KOZ)
        with szemelyes_db.olvaso(self.cfg, 3) as c:
            if c is None:
                raise Hiany("még nincs naptáradat: a naptár-szinkron még nem futott (a naptár-engedély a vezérlőben, ⇧⌘M)")
            esemenyek = naptar.esemenyek(c, tol, ig, self.cfg)
            sz = naptar.utolso_szinkron(c)
        utolso = (sz or {}).get("utolso_sikeres")
        regi = True
        if utolso:
            try:
                t = datetime.fromisoformat(utolso)
                regi = self.most - (t if t.tzinfo else t.astimezone()) > timedelta(hours=self.m.naptar_regi_ora)
            except ValueError:
                pass
        self._naptar = {"esemenyek": esemenyek, "utolso_szinkron": utolso, "regi": regi}
        return self._naptar

    def jegyzetek(self) -> list[kotes.Jegyzet]:
        if self._jegyzetek is None:
            self._jegyzetek = kotes.jegyzetek(self.index.fajl_halmaz(), self.m.dolgozat_mappa,
                                              naptar.targyak_cfg(self.cfg))
        return self._jegyzetek

    def kotesek(self) -> kotes.Kotesek:
        if self._kotesek is None:
            hatar = ATHELYEZES_KOZ + self.m.mult_nap + self.visszamenoleg_nap
            kozeli = [j for j in self.jegyzetek() if abs((date.fromisoformat(j.nap) - self.ma).days) <= self.m.elore_nap + hatar]
            self._kotesek = kotes.kot(kozeli, self.naptar()["esemenyek"])
        return self._kotesek

    def dolgozatok(self) -> list[dict]:
        """A közelgő (és az utóbbi napokban lezárt) dolgozatok a naptárból, a felkészülési jegyzet kötésével."""
        n = self.naptar()
        elso = self.ma - timedelta(days=self.m.mult_nap + self.visszamenoleg_nap)
        utolso = self.ma + timedelta(days=self.m.elore_nap)
        try:
            kotesek = self.kotesek() if self.index_kesz() else None
        except Exception as e:                    # noqa: BLE001
            kotesek = None
            self.figyelmeztet(f"a felkészülési jegyzetek kötése nem érhető el: {e}")
        if kotesek is None and not self.index_kesz():
            self.figyelmeztet("az index még épül: a felkészülési jegyzetek és a témák később jelennek meg")
        ki = []
        for e in n["esemenyek"]:
            if e.get("fajta") != "dolgozat":
                continue
            try:
                nap = date.fromisoformat((e.get("nap") or e.get("kezd") or "")[:10])
            except ValueError:
                continue
            if not (elso <= nap <= utolso):
                continue
            k = kotesek.esemenyek.get(e["azon"]) if kotesek else None
            ki.append({"azon": e["azon"], "cim": e.get("cim") or "(cím nélkül)", "nap": nap.isoformat(),
                       "egesznap": bool(e.get("egesznap")), "ora": "" if e.get("egesznap") else (e.get("kezd") or "")[11:16],
                       "kezd": e.get("kezd"), "napok": (nap - self.ma).days, "lezart": nap < self.ma,
                       "tantargy": (e.get("targyak") or [None])[0], "targyak": list(e.get("targyak") or ()),
                       "kotes": k})
        return sorted(ki, key=lambda d: (d["nap"], d.get("kezd") or "", d["azon"]))

    # ------------------------------------------------------------------ eredmények (C28b)

    def eredmenyek(self) -> dict[str, dict]:
        """A „Dolgozat kiértékelő” jegyzetek szakaszaiból kinyert eredmények **a felkészülési jegyzet útja szerint**:
        `{jegyzet_ut: {eredmeny | None, ellentmondas | None, szakasz_cim, fajl, sor}}` (`eredmeny.py`). A szakasz az első
        wikilinkje által kötődik a felkészülési jegyzethez (feloldás: `Index.felold_egy`, L42). Csak olvas; olvasó (`olvas`) nélkül
        vagy még épülő indexnél üres, és az `adatok.eredmeny` megmondja, miért."""
        if self._eredmenyek is not None:
            return self._eredmenyek
        self._eredmenyek = {}
        if self.olvas is None:
            self.adatok["eredmeny"] = {"van": None, "ok": "a jegyzetek olvasója nincs megadva"}
            return self._eredmenyek
        if not self.index_kesz():
            self.adatok["eredmeny"] = {"van": None, "ok": "az index még épül"}
            return self._eredmenyek
        nevek = [naptar.norm(x) for x in self.m.kiertekelo_nevek]
        felk = {j.ut for j in self.jegyzetek()}
        talalt = []
        fajlok = 0
        for rp in self.index.fajl_halmaz():
            if not rp.lower().endswith(".md") or not any(n in naptar.norm(posixpath.basename(rp)) for n in nevek):
                continue
            try:
                szoveg = self.olvas(rp)
            except Exception as e:                  # noqa: BLE001 — egy jegyzet hibája nem viszi el a többit
                self.figyelmeztet(f"a kiértékelő jegyzet nem olvasható ({rp}): {e}")
                continue
            if not isinstance(szoveg, str):
                continue
            fajlok += 1
            for se in eredmeny.szakasz_eredmenyek(szoveg, rp):
                if se.szakasz.link is None:
                    continue
                try:
                    ut = self.index.felold_egy(se.szakasz.link, rp)
                except Exception:                  # noqa: BLE001
                    ut = None
                if ut and ut in felk:
                    talalt.append((ut, se))
        self._eredmenyek = eredmeny.jegyzetenkent(talalt)
        van = sum(1 for x in self._eredmenyek.values() if x["eredmeny"])
        self.adatok["eredmeny"] = {"van": bool(van), "db": van, "jegyzet": fajlok,
                                   "ok": None if van else ("nincs egyértelmű eredmény a kiértékelő jegyzetekben" if fajlok
                                                           else "nincs kiértékelő jegyzet")}
        return self._eredmenyek

    # ------------------------------------------------------------------ témák

    def temak(self, jegyzet_ut: str) -> temak.Temak:
        """A felkészülési jegyzet témái és forrásai (`Source` + `NN`)."""
        if jegyzet_ut not in self._temak:
            j = self.index.jegyzet(jegyzet_ut)
            self._temak[jegyzet_ut] = temak.kinyer(j, {x.ut for x in self.jegyzetek()})
        return self._temak[jegyzet_ut]

    # ------------------------------------------------------------------ kártyák

    def sched(self):
        if self._sched is None:
            import fsrs
            self._sched = fsrs.Scheduler()
        return self._sched

    def kartyak(self) -> list[dict]:
        """Az élő, nem felfüggesztett kártyák (`tanulas.sqlite`, csak olvasva); nincs adatbázis → üres lista."""
        if self._kartyak is not None:
            return self._kartyak
        with tanulas_db.olvaso(self.cfg) as c:
            if c is None:
                self._kartyak = []
                self.adatok["kartya"] = {"van": False, "db": 0, "ok": "még nincs kártya: a tanulas.sqlite nem létezik"}
                return self._kartyak
            if self.rekonstrukcio:                 # C28b: a kártyák a `most` időpontbeli állapotukban (rekonstrukcio.py)
                self._kartyak, self._kartya_valasz = rekonstrukcio.kartyak_ekkor(c, self.most)
            else:
                self._kartyak = [dict(r) for r in c.execute(
                    "SELECT azon, jegyzet, forras, kerdes, allapot, lepes, stabilitas, nehezseg, esedekes, utolso FROM kartya "
                    "WHERE torolve IS NULL AND felfuggesztve = 0 ORDER BY azon")]
                self._kartya_valasz = {r[0]: r[1] for r in c.execute(
                    "SELECT kartya, MAX(mikor) FROM valasz WHERE visszavonva IS NULL AND forras = 'ismetles' GROUP BY kartya")}
        self.adatok["kartya"] = {"van": bool(self._kartyak), "db": len(self._kartyak),
                                 "ok": None if self._kartyak else "még nincs kártya"}
        return self._kartyak

    def _kartya_tema(self, k: dict) -> str | None:
        """A kártya témája: a `forras` link-cél feloldva a kísérőjegyzet felől (L42), tartalék a kísérőjegyzet
        `Source`-a; különben kötetlen."""
        jegyzet = k.get("jegyzet") or ""
        cel = (k.get("forras") or "").split("#", 1)[0].strip()
        kulcs = (jegyzet, cel)
        if kulcs in self._kartya_temak:
            return self._kartya_temak[kulcs]
        ut = None
        if cel and jegyzet:
            try:
                ut = self.index.felold_egy(cel, jegyzet)
            except Exception:                      # noqa: BLE001
                ut = None
            if ut and temak.tipus(ut) != "md":
                ut = None
        if ut is None and jegyzet:
            try:
                for l in self.index.jegyzet(jegyzet).get("linkek", ()):
                    if (l.get("tulajdonsag") or "").lower() == "source" and l.get("cel") and temak.tipus(l["cel"]) == "md" \
                            and l["cel"] != jegyzet:
                        ut = l["cel"]
                        break
            except Exception:                      # noqa: BLE001
                ut = None
        self._kartya_temak[kulcs] = ut
        return ut

    def temankent(self) -> dict[str, list[dict]]:
        """A kártyák témánként; a kötetlenek száma a `adatok.kartya.kotetlen`-ben."""
        if self._temankent is None:
            ki: dict[str, list[dict]] = {}
            kotetlen = 0
            for k in self.kartyak():
                t = self._kartya_tema(k)
                if t is None:
                    kotetlen += 1
                else:
                    ki.setdefault(t, []).append(k)
            self._temankent = ki
            if "kartya" in self.adatok:
                self.adatok["kartya"]["kotetlen"] = kotetlen
        return self._temankent

    # ------------------------------------------------------------------ tracker, kvíz, átnevezés

    def aktiv(self) -> dict[str, list[tuple[str, int]]]:
        """A tracker aktív ideje útvonalanként: `{ut: [(nap, mp)]}` (csak olvasva); nincs adat → üres."""
        if self._aktiv is None:
            self._aktiv = {}
            with szemelyes_db.olvaso(self.cfg, 2) as c:
                if c is None:
                    self.adatok["tracker"] = {"van": False, "ok": "még nincs tracker-adat (a pos.sqlite vagy a tr_aktiv nincs)"}
                else:
                    # rekonstrukcióban a tracker a `most` napjáig (a nap végi állapot: a napi összegzés nem bontható szét)
                    felso = self.ma.isoformat() if self.rekonstrukcio else "9999-12-31"
                    for r in c.execute("SELECT nap, ut, mp FROM tr_aktiv WHERE mp > 0 AND nap <= ? ORDER BY nap", (felso,)):
                        self._aktiv.setdefault(r["ut"], []).append((r["nap"], r["mp"]))
                    self.adatok["tracker"] = {"van": bool(self._aktiv), "ok": None if self._aktiv else "a tracker még nem mért időt"}
        return self._aktiv

    def terkep(self) -> atnevezes.Terkep:
        if self._terkep is None:
            if not self.m.atnevezes_kovetes:
                self._terkep = atnevezes.Terkep()
            else:
                napok = [nap for sorok in self.aktiv().values() for nap, _ in sorok]
                self._terkep = atnevezes.terkep(self.cfg, min(napok) if napok else None)
                self.figyelmeztet(self._terkep.figyelmeztetes or "")
        return self._terkep

    def kviz(self) -> list[forrasok.KvizEredmeny]:
        if self._kviz is None:
            tol = self.most - timedelta(days=self.m.elore_nap + self.m.ablak_nap + self.m.mult_nap + 30)
            self._kviz, hibak = forrasok.kviz_eredmenyek(self.cfg, tol, self.most + timedelta(seconds=1))
            for h in hibak:
                self.figyelmeztet(h)
            self.adatok["kviz"] = {"van": bool(self._kviz), "ok": None if self._kviz else (
                "még nincs kvízeredmény" if forrasok.van_forras() else "nincs kvíz-adatforrás")}
        return self._kviz

    def forrasok_betolt(self) -> None:
        """A három adatforrás betöltése (a `adatok` állapotmezők kitöltéséhez, témák nélkül is)."""
        for fn in (self.kartyak, self.aktiv, self.kviz):
            try:
                fn()
            except Exception as e:                 # noqa: BLE001 — egy forrás hibája nem viszi el a többit
                self.figyelmeztet(f"adatforrás-hiba: {e}")

    # ------------------------------------------------------------------ egy téma jele

    def tema_jel(self, tema_ut: str, dolgozat_nap: date, tau: datetime) -> tuple[keplet.TemaJel, dict]:
        """A téma bemenete a `tau` időpontban (a „most”, vagy a dolgozat napja) és a nyers adatai a lefúráshoz.
        A tanult idő és a kvíz ablaka: `[dolgozat_nap − ablak_nap, ma]`; az utolsó tanulás időkorlát nélkül."""
        aliasok = self.terkep().aliasok(tema_ut)
        ablak_tol = (dolgozat_nap - timedelta(days=self.m.ablak_nap)).isoformat()
        ma_iso = self.ma.isoformat()
        from modulok.kartya import utemezo
        kartyak = self.temankent().get(tema_ut, [])
        # a py-fsrs csak akkor kell, ha van már tanult kártya (új kártya felidézése 0): nélküle a lap kártya nélkül is él
        sched = self.sched() if any(k["allapot"] != utemezo.UJ for k in kartyak) else None
        felidezesek, uj = [], 0
        for k in kartyak:
            felidezesek.append(utemezo.felidezes(k, tau, sched))
            uj += 1 if k["allapot"] == utemezo.UJ else 0
        # tracker
        perc = 0.0
        utolsok: list[date] = []
        for ut in aliasok:
            for nap, mp in self.aktiv().get(ut, ()):
                if ablak_tol <= nap <= ma_iso:
                    perc += mp / 60
                if mp >= self.b.min_tanulas_mp and nap <= ma_iso:
                    utolsok.append(date.fromisoformat(nap))
        # kártyaválaszok és kvíz
        for k in kartyak:
            d = _helyi_nap(self._kartya_valasz.get(k["azon"]))
            if d:
                utolsok.append(d)
        kviz = []
        for e in self.kviz():
            if e.tema in aliasok and ablak_tol <= e.mikor.astimezone().date().isoformat() <= ma_iso:
                kviz.append((max(0.0, (tau - e.mikor).total_seconds() / 86400), e.helyes, e.osszes))
                utolsok.append(e.mikor.astimezone().date())
        utolso = max(utolsok) if utolsok else None
        jel = keplet.TemaJel(kartya=tuple(felidezesek), uj_kartya=uj, kviz=tuple(kviz),
                             utolso_tanulas_nap=None if utolso is None else max(0, (tau.date() - utolso).days),
                             tanult_perc=round(perc, 1))
        gyengek = sorted(((utemezo.felidezes(k, tau, sched), k) for k in kartyak if k["allapot"] != utemezo.UJ),
                         key=lambda x: (x[0], x[1]["azon"]))[:self.m.gyenge_kartya_db]
        # az esedékesség a mai helyi nap végéig; új kártya nem „esedékes”, hanem „új”
        veg = datetime.combine(self.ma, time.max, tzinfo=self.most.tzinfo)
        esedekes = sum(1 for k in kartyak if k["allapot"] != utemezo.UJ and (_idopont(k["esedekes"]) or veg) <= veg)
        reszlet = {"aliasok": sorted(aliasok - {tema_ut}), "tanult_perc": round(perc, 1),
                   "utolso_tanulas": utolso.isoformat() if utolso else None,
                   "kartya": {"db": len(kartyak), "uj": uj, "esedekes": esedekes,
                              "gyenge": [{"azon": k["azon"], "kerdes": k["kerdes"], "felidezes": round(r, 3)} for r, k in gyengek]},
                   "kviz": {"db": len(kviz)}}
        return jel, reszlet

    def esedekes_napra(self, tema_utak: list[str], napok: list[str]) -> dict[str, int]:
        """A témák esedékes (nem új) kártyái napokra: a mai nap a már lejártakkal együtt, a későbbi nap az aznap esedékesek
        — **becslés**: az FSRS-szimulációt nem végezzük."""
        ki = {n: 0 for n in napok}
        for t in tema_utak:
            for k in self.temankent().get(t, []):
                if k["allapot"] == 0:
                    continue
                d = _helyi_nap(k["esedekes"])
                if d is None:
                    continue
                nap = max(d, self.ma).isoformat()
                if nap in ki:
                    ki[nap] += 1
        return ki


ATHELYEZES_KOZ = kotes.ATHELYEZES_MAX_NAP


def _idopont(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None
