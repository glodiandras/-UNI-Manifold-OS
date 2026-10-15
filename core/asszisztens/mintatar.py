"""Az Asszisztens mintatára és a javaslat-kártya jelöltjei (J1, J3; ESZREVETELEK-TERV 2. fejezet 3., 5., 6. pont).

**Mit tanul** (modell nélkül):

* *Jegyzetszerkezet*: a nyitott jegyzet mappájának testvérjegyzetei (az indexből) — ha a testvérek legalább
  `kartya_szerkezet_arany` részében áll egy `##` szakaszcím, és a nyitott jegyzetből hiányzik, a kártya felajánlja.
* *Ismétlődő műveletek*: a felület jelzi, ha a felhasználó egy mappában címkét ad, sablont szúr be vagy linket illeszt
  (`tanul`); `kartya_muvelet_min_db` ismétlés után a művelet tanult minta, és egy ugyanabban a mappában álló jegyzetnél
  — ahol még nincs meg — egy kattintással elvégezhető.
* *Tartalmi kiegészítés*: a vektortárból (C25c, modell nélkül) a tartalmában legközelebbi, még nem linkelt jegyzet.

**Hol él**: a `{state}/asszisztens.json` (`muveletek`, `kartya_dontesek`, a hangolás a `hangolas` alatt); a vaultba **nem ír**.
A kártya elfogadása a felületen, a nyitott jegyzet szerkesztőjén át ír (egy tranzakció, ⌘Z).

**Gyakoriság**: a jelöltek a `Hangolo` állása szerint szűrődnek (néma fajta nem jön), a kártyák közti várakozás a szorzóval
nő vagy csökken. Az elutasított javaslat `kartya_elutasitott_nap` napig nem tér vissza.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import time

from ..index import elemzo
from ..index.feloldas import celkulcs, nfc
from ..index.maszk import FM_RE
from ..utvonalak import HttpError
from .allapot import Allapot
from .beallitasok import beallitasok
from .hangolo import Hangolo

MUVELETEK = ("cimke", "sablon", "link")
MUVELET_NEV = {"cimke": "címke", "sablon": "sablon", "link": "link"}
ALKALMAK = ("megnyitas", "szunet")
MAX_MUVELET = 300
MAX_DONTES = 500
MAX_SZOVEG = 200_000
_AZON = re.compile(r"^(szerkezet|muvelet|tartalom):[0-9a-f]{12}$")


def _h(*reszek: str) -> str:
    return hashlib.sha1("\x1f".join(reszek).encode("utf-8")).hexdigest()[:12]


def hossz_jel(szoveg: str, fm_veg: int) -> str:
    n = len(szoveg[fm_veg:].strip())
    return "rovid" if n < 300 else "kozepes" if n < 3000 else "hosszu"


def _torzs_nev(ut: str) -> str:
    return posixpath.basename(ut).rsplit(".", 1)[0]


class Mintatar:
    def __init__(self, cfg, index, allapot: Allapot, hangolo: Hangolo, kapcsolo, hasonlok=None, ido=time.time):
        self.cfg = cfg
        self.index = index
        self.allapot = allapot
        self.hangolo = hangolo
        self.kapcsolo = kapcsolo
        self.hasonlok = hasonlok           # (ut, n) → a C25c `hasonlok` válasza; None: nincs tartalmi forrás
        self.ido = ido

    # -------------------------------------------------- ismétlődő műveletek

    def tanul(self, d: dict) -> dict:
        """A felület jelzése egy felhasználói műveletről: `{muvelet: cimke|sablon|link, ut, ertek}` → `{fogadva, tanult}`."""
        muvelet, ut, ertek = d.get("muvelet"), d.get("ut"), d.get("ertek")
        if muvelet not in MUVELETEK:
            raise HttpError(400, "a művelet cimke, sablon vagy link lehet")
        if not isinstance(ut, str) or not ut.lower().endswith(".md") or len(ut) > 1000:
            raise HttpError(400, "az `ut` egy jegyzet vault-relatív útja")
        if not isinstance(ertek, str) or not ertek.strip() or len(ertek) > 300 or "\x00" in ertek or "\n" in ertek:
            raise HttpError(400, "az `ertek` legfeljebb 300 karakteres, egysoros szöveg")
        if not self.kapcsolo():
            return {"fogadva": False, "ok": "asszisztens_ki"}
        ut, ertek = nfc(ut), nfc(ertek.strip())
        if muvelet == "cimke":
            ertek = ertek.lstrip("#")
        mappa = ut.rpartition("/")[0]
        k = _h(muvelet, mappa, ertek.casefold())
        most = self.ido()
        ki = {}

        def ir(a):
            m = a.get("muveletek") if isinstance(a.get("muveletek"), dict) else {}
            regi = m.get(k) if isinstance(m.get(k), dict) else {}
            # az első látott alak marad (a kulcs kis-nagybetűtől független; a későbbi „analízis” nem írja át az „Analízis”-t)
            m[k] = {"muvelet": muvelet, "mappa": mappa, "ertek": regi.get("ertek") if isinstance(regi.get("ertek"), str) else ertek,
                    "db": int(regi.get("db", 0)) + 1, "utolso": most}
            if len(m) > MAX_MUVELET:
                for x in sorted(m, key=lambda x: m[x].get("utolso", 0) if isinstance(m[x], dict) else 0)[:len(m) - MAX_MUVELET]:
                    m.pop(x, None)
            a["muveletek"] = m
            ki["db"] = m[k]["db"]
        self.allapot.modosit(ir)
        return {"fogadva": True, "tanult": ki["db"] >= int(beallitasok(self.cfg)["kartya_muvelet_min_db"])}

    def _muveletek(self) -> dict[str, dict]:
        m = self.allapot.olvas().get("muveletek")
        if not isinstance(m, dict):
            return {}
        return {k: v for k, v in m.items() if isinstance(v, dict) and v.get("muvelet") in MUVELETEK
                and isinstance(v.get("mappa"), str) and isinstance(v.get("ertek"), str)}

    # -------------------------------------------------- döntések (elutasított kártyák)

    def _dontesek(self) -> dict[str, dict]:
        d = self.allapot.olvas().get("kartya_dontesek")
        if not isinstance(d, dict):
            return {}
        hatar = self.ido() - float(beallitasok(self.cfg)["kartya_elutasitott_nap"]) * 86400.0
        return {k: v for k, v in d.items() if isinstance(v, dict) and float(v.get("t", 0) or 0) >= hatar}

    def dontes(self, d: dict) -> dict:
        """A kártya sorsa: `{azon, tipus, helyzet, dontes: elfogad|elutasit|figyelmen_kivul, cim?}` → a hangolás új állása."""
        azon, tipus, helyzet, dontes = d.get("azon"), d.get("tipus"), d.get("helyzet"), d.get("dontes")
        if not isinstance(azon, str) or not _AZON.match(azon) or azon.split(":", 1)[0] != tipus:
            raise HttpError(400, "érvénytelen javaslat-azonosító")
        if not self.kapcsolo():
            return {"fogadva": False, "ok": "asszisztens_ki"}
        allas = self.hangolo.rogzit(tipus, helyzet, dontes)
        if dontes in ("elfogad", "elutasit"):
            cim = d.get("cim") if isinstance(d.get("cim"), str) else ""
            most = self.ido()

            def ir(a):
                m = self._dontesek()
                m[azon] = {"d": dontes, "t": most, "cim": cim[:200]}
                if len(m) > MAX_DONTES:
                    for x in sorted(m, key=lambda x: m[x].get("t", 0))[:len(m) - MAX_DONTES]:
                        m.pop(x, None)
                a["kartya_dontesek"] = m
            self.allapot.modosit(ir)
        return {"fogadva": True, "allas": allas}

    # -------------------------------------------------- a kártya jelöltjei

    def _szerkezet(self, ut: str, mappa: str, jegyzet, helyzet: str) -> list[dict]:
        b = beallitasok(self.cfg)
        sajat = {f["szoveg"].casefold() for f in jegyzet.fejezetek if f["szint"] == 2}
        with self.index.olvaso() as c:
            n = c.execute("SELECT COUNT(*) FROM fajl WHERE mappa = ? AND tipus = 'md' AND torolve IS NULL AND ut != ?",
                          (mappa, ut)).fetchone()[0]
            if n < int(b["kartya_min_testver"]):
                return []
            sorok = c.execute(
                "SELECT fe.szoveg, COUNT(DISTINCT fe.fajl_id) FROM fejezet fe JOIN fajl f ON f.id = fe.fajl_id "
                "WHERE f.mappa = ? AND f.tipus = 'md' AND f.torolve IS NULL AND f.ut != ? AND fe.szint = 2 "
                "GROUP BY fe.szoveg", (mappa, ut)).fetchall()
        osszes: dict[str, list] = {}
        for szoveg, db in sorok:
            k = szoveg.casefold()
            if k not in osszes:
                osszes[k] = [szoveg, 0]
            osszes[k][1] += int(db)
        ki = []
        for k, (szoveg, db) in osszes.items():
            arany = min(1.0, db / n)
            if k in sajat or arany < float(b["kartya_szerkezet_arany"]) or "\n" in szoveg:
                continue
            ki.append({"azon": "szerkezet:" + _h(mappa, k), "tipus": "szerkezet", "helyzet": helyzet, "pont": arany,
                       "cim": f"Mit szólnál egy „{szoveg}” szakaszhoz?",
                       "indok": f"A mappa {n} másik jegyzetéből {db}-ban van ilyen szakasz.",
                       "muvelet": {"fajta": "szakasz", "szoveg": f"## {szoveg}"}})
        return ki

    def _linkelve(self, jegyzet, cel_ut: str) -> bool:
        kulcs = celkulcs(_torzs_nev(cel_ut))
        return any(celkulcs(L.cel) in (kulcs, kulcs + ".md") for L in jegyzet.linkek)

    def _ismetlodo(self, ut: str, mappa: str, jegyzet, hossz: str, helyzet: str) -> list[dict]:
        min_db = int(beallitasok(self.cfg)["kartya_muvelet_min_db"])
        cimkek = {c["cimke"].casefold() for c in jegyzet.cimkek}
        ki = []
        for k, m in self._muveletek().items():
            if m["mappa"] != mappa or int(m.get("db", 0)) < min_db:
                continue
            db, ertek = int(m["db"]), m["ertek"]
            pont = min(1.0, 0.5 + db / 20)
            indok = f"Ebben a mappában már {db}-szor tetted ezt."
            if m["muvelet"] == "cimke" and ertek.casefold() not in cimkek:
                ki.append({"cim": f"Mit szólnál a(z) „{ertek}” címkéhez?", "muvelet": {"fajta": "cimke", "ertek": ertek}})
            elif m["muvelet"] == "link" and ertek != ut and not self._linkelve(jegyzet, ertek):
                ki.append({"cim": f"Mit szólnál egy linkhez: „{_torzs_nev(ertek)}”?", "muvelet": {"fajta": "link", "cel": ertek}})
            elif m["muvelet"] == "sablon" and hossz == "rovid":
                ki.append({"cim": f"Mit szólnál a(z) „{_torzs_nev(ertek)}” sablonhoz?", "muvelet": {"fajta": "sablon", "ut": ertek}})
            else:
                continue
            ki[-1].update(azon="muvelet:" + k, tipus="muvelet", helyzet=helyzet, pont=pont, indok=indok)
        return ki

    def _tartalom(self, ut: str, jegyzet, helyzet: str) -> list[dict]:
        if self.hasonlok is None:
            return []
        try:
            r = self.hasonlok(ut, 5)
        except Exception:                     # noqa: BLE001 — nincs vektortár, nincs ilyen jegyzet: nincs tartalmi jelölt
            return []
        if not isinstance(r, dict) or r.get("allapot") != "ok":
            return []
        kuszob = float(beallitasok(self.cfg)["kartya_tartalom_kuszob"])
        for t in r.get("talalatok") or []:
            cel, pont = t.get("ut"), t.get("pont")
            if not isinstance(cel, str) or not isinstance(pont, (int, float)) or pont < kuszob:
                continue
            if cel == ut or t.get("kimeno") or self._linkelve(jegyzet, cel) or self._kizart(cel):
                continue
            return [{"azon": "tartalom:" + _h(ut, cel), "tipus": "tartalom", "helyzet": helyzet, "pont": float(pont),
                     "cim": f"Mit szólnál egy linkhez: „{_torzs_nev(cel)}”?",
                     "indok": "Tartalmában közel áll ehhez a jegyzethez, de még nincs összekötve.",
                     "muvelet": {"fajta": "link", "cel": cel}}]
        return []

    def _kizart(self, ut: str) -> bool:
        return any(ut.startswith(p) or f"/{p}" in ut for p in beallitasok(self.cfg)["kartya_kizart"])

    def kartya(self, d: dict) -> dict:
        """A nyitott (akár mentetlen) jegyzet legjobb kártya-jelöltje: `{javaslat | None, varakozas_mp}`.
        Modellt nem hív, a vaultba nem ír; kikapcsolt Asszisztensnél nincs javaslat."""
        ut, szoveg, alkalom = d.get("ut"), d.get("szoveg"), d.get("alkalom", "szunet")
        if not isinstance(ut, str) or not ut.lower().endswith(".md"):
            raise HttpError(400, "az `ut` egy jegyzet vault-relatív útja")
        if not isinstance(szoveg, str) or len(szoveg) > MAX_SZOVEG:
            raise HttpError(400, "a `szoveg` kötelező (legfeljebb 200 000 karakter)")
        if alkalom not in ALKALMAK:
            raise HttpError(400, "az `alkalom` megnyitas vagy szunet lehet")
        alap = float(beallitasok(self.cfg)["kartya_alap_mp"])
        if not self.kapcsolo():
            return {"javaslat": None, "varakozas_mp": alap, "kapcsolo": False}
        ut = nfc(ut)
        if self._kizart(ut):
            return {"javaslat": None, "varakozas_mp": alap, "kapcsolo": True}
        szoveg = szoveg.replace("\r\n", "\n")
        jegyzet = elemzo.elemez(szoveg)
        fm = FM_RE.match(szoveg)
        hossz = hossz_jel(szoveg, fm.end() if fm else 0)
        helyzet = f"{alkalom}_{hossz}"
        mappa = ut.rpartition("/")[0]
        jeloltek: list[dict] = []
        try:
            if self.index.allapot().get("kesz"):
                jeloltek += self._szerkezet(ut, mappa, jegyzet, helyzet)
        except Exception:                     # noqa: BLE001 — az index olvasási hibája nem szakíthatja meg a gépelést
            pass
        jeloltek += self._ismetlodo(ut, mappa, jegyzet, hossz, helyzet)
        jeloltek += self._tartalom(ut, jegyzet, helyzet)
        latott = self._dontesek()
        legjobb, legjobb_pont, szorzok = None, -1.0, []
        for j in jeloltek:
            if j["azon"] in latott:
                continue
            a = self.hangolo.allas(j["tipus"], j["helyzet"])
            if a["szint"] == "nema":
                continue
            szorzok.append(a["szorzo"])
            p = a["arany"] * j["pont"]
            if p > legjobb_pont:
                legjobb, legjobb_pont = {**{k: v for k, v in j.items() if k != "pont"}, "allas": a["szint"]}, p
        szorzo = min(szorzok) if szorzok else 1.0
        return {"javaslat": legjobb, "varakozas_mp": round(alap * szorzo, 1), "kapcsolo": True}

    # -------------------------------------------------- a „Mit tanult” lista

    def lista(self) -> dict:
        min_db = int(beallitasok(self.cfg)["kartya_muvelet_min_db"])
        muveletek = sorted(({"kulcs": k, "muvelet": v["muvelet"], "muvelet_nev": MUVELET_NEV[v["muvelet"]],
                             "mappa": v["mappa"], "ertek": v["ertek"], "db": int(v.get("db", 0)),
                             "tanult": int(v.get("db", 0)) >= min_db}
                            for k, v in self._muveletek().items()), key=lambda x: (-x["db"], x["kulcs"]))
        elutasitott = sorted(({"kulcs": k, "tipus": k.split(":", 1)[0], "cim": v.get("cim") or ""}
                              for k, v in self._dontesek().items() if v.get("d") == "elutasit"), key=lambda x: x["kulcs"])
        return {"muveletek": muveletek, "elutasitott": elutasitott}

    def torol_muvelet(self, k: str) -> bool:
        van = k in self._muveletek()
        if van:
            self.allapot.modosit(lambda a: (a.get("muveletek") or {}).pop(k, None))
        return van

    def torol_dontes(self, k: str) -> bool:
        van = k in (self.allapot.olvas().get("kartya_dontesek") or {})
        if van:
            self.allapot.modosit(lambda a: (a.get("kartya_dontesek") or {}).pop(k, None))
        return van

    def torol_mind(self) -> None:
        self.allapot.modosit(lambda a: a.update(muveletek={}, kartya_dontesek={}))
