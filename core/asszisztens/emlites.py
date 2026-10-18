"""A linkeletlen említések felismerése a *kapott* szövegben (C30a; TERV 5.10, CHATKALAUZ C30 1. pont) — core API a C30b-nek.

A szerkesztő a nyitott (akár mentetlen) szöveget küldi; a modul a többi jegyzet **nevét és aliasát** keresi benne
szóhatáron, kis-nagybetűtől függetlenül, ékezetre érzékenyen (a `/api/vault/emlitesek` szabályaival, de a másik
irányban: ott egy jegyzet nevét keressük a többiben, itt a többi nevét a mostani szövegben). **Lexikai, hasonlóság és
modell nélkül.** Az aláhúzás, a Tab/Esc és a hasonlóság a C30b-é.

*Szótár*: a `fajl` élő `.md` sorainak alapneve és `aliases`-ai, a `generacio` szerint gyorsítótárazva, de legfeljebb
`emlites_szotar_frissites_mp`-enként újraépítve (a gépelés közbeni mentések ne építsék újra minden kérésnél). Nem kerül bele
a `min_hossz`-nál rövidebb, a betű nélküli név, és a kizárt útú (napi jegyzet, sablon, gépi kísérőjegyzet, média-réteg)
jegyzet.

*Címrész-alak* (K177; `emlites_cim_alak`): a vault fájlnevei `NN - Cím` és `NNF - Cím — Feladattár` alakúak, a próza viszont
a „Ciklusok”-ra hivatkozik, nem a `05 - Ciklusok`-ra: a teljes név sosem egyezne. Ezért a szótár a címrészt is tartalmazza
(az `NN - ` előtag, az első ` — ` utáni utótag és a kezdő névelő nélkül: „A vita” → `vita`, a névelő nem része a linknek). A
teljes névnél, ami nem tér el a címtől, és az aliasnál a szűrés nincs (a régi viselkedés); a **címrészből származó** egyezést
az alábbi szűrés védi a zajtól:

- címsorba (`# …`) nem javasol linket;
- legalább `emlites_cim_min_szo` (2) szavas cím bárhol egyezhet; az egyszavas csak ugyanabban a tantárgy-mappában (a vault-út
  első szegmense), és csak ha a szó ritka: legfeljebb `emlites_cim_egyszavas_max_db` jegyzet tartalmazza (az FTS-ből, a
  szótárral együtt gyorsítótárazva);
- ha a címre több cél illik, az azonos tantárgy-mappabeliek előnyt élveznek, és a `— Feladattár`-féle utótagos jegyzet
  csak akkor marad, ha nincs utótag nélküli (elsődleges) cél; ami ezután is több célra illik, `tobbertelmu` (a felület
  nem húzza alá).

*Illesztés*: a szöveg link-maszkolt másolatán (kód, képlet, frontmatter, wiki- és md-link, URL kitakarva, a
hosszak és a pozíciók megmaradnak), balról jobbra, a leghosszabb, nem átfedő találattal. Nem javasol: a saját jegyzetet és
azt a célt, amelyre a jegyzetből az index szerint már van link. Azonos nevű több jegyzet: `tobbertelmu` és `jeloltek`.
Pozíció: Python-kódpont szerinti eltolás (`kezd`, `veg`), 1-től számolt `sor`, 0-tól `oszlop` — a UTF-16-ra alakítás a
felületé (a vault többi API-jával egyező).
"""
from __future__ import annotations

import bisect
import json
import re
import threading
import time

from ..index import kizaras, maszk
from ..index.feloldas import MD_RE, nfc
from ..utvonalak import HttpError
from .beallitasok import beallitasok

_SZO = re.compile(r"\w+")
_WIKI = re.compile(r"!?\[\[[^\]]*\]\]")
_URL = re.compile(r"https?://\S+")
_BETU = re.compile(r"[^\W\d_]")
_NN_ELOTAG = re.compile(r"^\d+[A-Za-z]?\s+-\s+")        # `05 - `, `06F - ` a fájlnév elején
_UTOTAG_JEL = " \u2014 "                                  # ` — Feladattár` (és hasonló) a fájlnév végén
_FEJLEC_SOR = re.compile(r"^ {0,3}#{1,6}[ \t]", re.MULTILINE)     # ATX-címsor: a címsorba nem javasolunk linket (címrész-alaknál)
_NYELVTANI_NEVELO = frozenset({"a", "az", "egy"})                # a cím elején álló névelő nem számít szónak
_KEZDO_NEVELO = re.compile(r"^(?:(?:a|az|egy)\s+)+(?=\S)", re.IGNORECASE)
JELOLT_MAX = 5


_NAGY_I_PONTTAL = str.maketrans({"\u0130": "i"})        # 'İ'.lower() két kódpont ('i' + összetett pont); itt egy


def hossztarto_kisbetu(szoveg: str) -> str:
    """A `szoveg` kisbetűs alakja **azonos kódpont-hosszal** (A3-26): az `'İ'` egy `'i'`; a `str.lower()` egyéb átalakításai
    (pl. a szó végi `Σ`) hossztartók, ha mégsem az lenne, az adott karakter marad változatlan. A `kezd`/`veg` pozíciók
    ezért a kisbetűs és az eredeti szövegre egyaránt érvényesek."""
    k = szoveg.translate(_NAGY_I_PONTTAL).lower()
    if len(k) == len(szoveg):
        return k
    return "".join(c if len(l := c.translate(_NAGY_I_PONTTAL).lower()) != 1 else l for c in szoveg)


def cimresz(nev: str) -> tuple[str, bool]:
    """A fájlnév **címrésze**: az `NN - ` előtag és az első ` — ` utáni utótag nélkül. → `(cím, volt_utotag)`; előtag és utótag
    nélküli névnél a név maga."""
    nev = _NN_ELOTAG.sub("", nfc(nev).strip(), count=1)
    fej, jel, _ = nev.partition(_UTOTAG_JEL)
    return fej.strip(), bool(jel)


def nevelo_nelkul(cim: str) -> str:
    """A cím a kezdő névelő(k) nélkül („A vita” → „vita”; a névelő után maradnia kell szónak). A címrész-alak szótárkulcsa: a
    próza névelővel és anélkül is említi, a névelő pedig nem része a linknek; a „a”-val kezdődő kulcsok hosszú listája is elmarad."""
    return _KEZDO_NEVELO.sub("", cim, count=1)


def tartalmas_szavak(kulcs: str) -> list[str]:
    """A cím szavai a **kezdő névelő nélkül** (szóköz szerint; a kötőjeles összetétel egy szó): „a vita” → 1, „a Thalész-tétel” → 1,
    „Nyelvi identitás” → 2. A névelővel kezdődő rövid cím a próbában ugyanúgy zajos, mint az egyszavas."""
    szavak = kulcs.split()
    while len(szavak) > 1 and szavak[0] in _NYELVTANI_NEVELO:
        szavak.pop(0)
    return szavak


def _szokarakter(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _ures(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def kitakar(szoveg: str) -> str:
    """A szöveg másolata, amelyben a kód, a képlet, a frontmatter, a wiki- és md-link, az URL szóközökre cserélve; a hossz és
    a sortörések megmaradnak, így a pozíciók az eredetire érvényesek."""
    m = maszk.link_maszk(szoveg)
    fm = maszk.FM_RE.match(m)
    if fm:
        m = _ures(fm) + m[fm.end():]
    for rx in (_WIKI, MD_RE, _URL):
        m = rx.sub(_ures, m)
    return m


class _Szotar:
    def __init__(self, generacio: int, ido: float, by_first: dict, nevek: int):
        self.generacio, self.ido, self.by_first, self.nevek = generacio, ido, by_first, nevek
        self.df: dict[str, int] = {}            # szó → hány jegyzet tartalmazza (lusta, a szótárral együtt érvényes)


class Emlitesek:
    def __init__(self, cfg, index, ido=time.monotonic):
        self.cfg = cfg
        self.index = index
        self.ido = ido
        self._szotar: _Szotar | None = None
        self._zar = threading.Lock()

    # -------------------------------------------------- szótár

    def _epit(self, generacio: int) -> _Szotar:
        b = beallitasok(self.cfg)
        reteg = str(self.cfg.section("media").get("reteg_mappa", "Média"))
        kizart = list(b["emlites_kizart"])
        felhasznaloi = kizaras.betolt(self.cfg)           # Excluded files (14-appearance-06): a kizárt jegyzet nem említés-cél
        with self.index.olvaso() as c:
            sorok = c.execute("SELECT ut, nev, aliasok FROM fajl WHERE torolve IS NULL AND tipus = 'md'").fetchall()
        nevek: dict[str, dict] = {}            # kisbetűs név → {nev, forras, celok: {ut}}
        for ut, nev, aliasok in sorok:
            if any(ut.startswith(p) for p in kizart) or (reteg and f"/{reteg}/" in "/" + ut) or felhasznaloi.kizart(ut):
                continue
            jeloltek = [(nev.rsplit(".", 1)[0], "nev")]
            try:
                jeloltek += [(a, "alias") for a in json.loads(aliasok or "[]") if isinstance(a, str)]
            except ValueError:
                pass
            teljes = nfc(nev.rsplit(".", 1)[0]).strip()
            if b["emlites_cim_alak"]:
                cim, utotagos = cimresz(nev.rsplit(".", 1)[0])
                if cim and cim != teljes:
                    jeloltek.append((nevelo_nelkul(cim), "cim2" if utotagos else "cim"))
            for szoveg, forras in jeloltek:
                szoveg = nfc(szoveg).strip()
                if len(szoveg) < b["emlites_min_hossz"] or not _BETU.search(szoveg):
                    continue
                e = nevek.setdefault(hossztarto_kisbetu(szoveg), {"nev": szoveg, "celok": {}})
                if forras in ("nev", "alias") or ut not in e["celok"]:       # a teljes név/alias erősebb a címrésznél
                    e["celok"][ut] = forras
        by_first: dict[str, list] = {}
        for kis, e in nevek.items():
            elso = _SZO.search(kis)
            if elso:
                by_first.setdefault(elso.group(0), []).append((kis, e))
        for lista in by_first.values():
            lista.sort(key=lambda x: -len(x[0]))
        sz = _Szotar(generacio, self.ido(), by_first, len(nevek))
        sz.kizaras_jel = felhasznaloi.jel
        return sz

    def szotar(self) -> _Szotar:
        with self._zar:
            sz = self._szotar
            gen = self.index.generacio
            frissites = float(beallitasok(self.cfg)["emlites_szotar_frissites_mp"])
            if sz is None or getattr(sz, "kizaras_jel", ()) != kizaras.jel(self.cfg) \
                    or (sz.generacio != gen and self.ido() - sz.ido >= frissites):
                sz = self._szotar = self._epit(gen)
            return sz

    # -------------------------------------------------- szűrés (K177)

    @staticmethod
    def _tantargy(ut: str) -> str:
        """A jegyzet tantárgy-mappája: a vault-út első szegmense (`M03 - Algebra`); a gyökérben álló jegyzetnek nincs (üres: az
        egyszavas cím nem illik rá)."""
        return ut.split("/", 1)[0] if "/" in ut else ""

    def _df(self, sz: _Szotar, szo: str) -> int:
        """Hány jegyzet tartalmazza a szót/kifejezést (FTS5, a szótár érvényességéig gyorsítótárazva). Hibánál „nagyon gyakori”
        (zárva: a szűrés ilyenkor az egyszavas címet elveti)."""
        if szo not in sz.df:
            try:
                with self.index.olvaso() as c:
                    sz.df[szo] = int(c.execute("SELECT count(*) FROM fts WHERE fts MATCH ?",
                                               ('tartalom : "' + szo.replace('"', '""') + '"',)).fetchone()[0])
            except Exception:                                  # noqa: BLE001 — sqlite3.Error, hibás FTS-szintaxis
                sz.df[szo] = 10 ** 9
        return sz.df[szo]

    def _lehetseges(self, e: dict, kulcs: str, ut: str, sz: _Szotar, b: dict) -> dict[str, str]:
        """Az `e` név lehetséges céljai a `ut` jegyzetben: `{cél út: forrás}`. A teljes név és az alias célja mindig marad; a
        címrészből származót a szűrés védi (lásd a modul-docstringet)."""
        ki = {u: f for u, f in e["celok"].items() if f in ("nev", "alias")}
        cimek = {u: f for u, f in e["celok"].items() if f in ("cim", "cim2")}
        if not cimek:
            return ki
        sajat = self._tantargy(ut)
        azonos = {u: f for u, f in cimek.items() if sajat and self._tantargy(u) == sajat}
        szavak = tartalmas_szavak(kulcs)
        if len(szavak) >= int(b["emlites_cim_min_szo"]):
            jo = azonos or cimek                                # az azonos tantárgy előnye
        elif azonos and self._df(sz, " ".join(szavak)) <= int(b["emlites_cim_egyszavas_max_db"]):
            jo = azonos                                         # egyszavas: ugyanabban a tantárgyban, és csak ha ritka
        else:
            jo = {}
        if any(f == "cim" for f in jo.values()):                # az `— Feladattár`-féle utótagos jegyzet csak tartalék
            jo = {u: f for u, f in jo.items() if f == "cim"}
        ki.update(jo)
        return ki

    # -------------------------------------------------- keresés

    def _belinkelt(self, ut: str) -> set[str]:
        with self.index.olvaso() as c:
            return {r[0] for r in c.execute(
                "SELECT DISTINCT l.cel FROM link l JOIN fajl f ON f.id = l.forras_id "
                "WHERE f.ut = ? AND f.torolve IS NULL AND l.cel IS NOT NULL", (ut,))}

    def keres(self, ut, szoveg, limit: int | None = None) -> dict:
        """A `szoveg` említései a `ut` jegyzet nevében (a jegyzet maga és az már belinkelt célok kimaradnak)."""
        if not isinstance(szoveg, str):
            raise HttpError(400, "a szöveg kötelező", kod="asszisztens.emlites.szoveg_kotelezo")
        b = beallitasok(self.cfg)
        limit = max(1, int(limit)) if limit else int(b["emlites_max"])
        ut = nfc(str(ut or "")).replace("\\", "/").strip().strip("/")
        sz = self.szotar()
        kihagy = self._belinkelt(ut) | {ut}
        maszkolt = kitakar(szoveg)
        kis = hossztarto_kisbetu(maszkolt)
        ki: list[dict] = []
        veg = -1
        sorok_elejei: list[int] | None = None
        fejlecek: set[int] | None = None
        for m in _SZO.finditer(maszkolt):
            if m.start() < veg:
                continue
            lista = sz.by_first.get(kis[m.start():m.end()])
            if not lista:
                continue
            for nev_kis, e in lista:
                kezd, vege = m.start(), m.start() + len(nev_kis)
                if kis[kezd:vege] != nev_kis:
                    continue
                if (vege < len(maszkolt) and _szokarakter(maszkolt[vege])) or (kezd > 0 and _szokarakter(maszkolt[kezd - 1])):
                    continue                           # szó belsejében nincs találat
                lehet = self._lehetseges(e, nev_kis, ut, sz, b)
                celok = sorted(set(lehet) - kihagy)
                if not celok:
                    continue
                if not (set(lehet.values()) & {"nev", "alias"}):           # csak címrészből jövő egyezés: címsorba nem javasol
                    if fejlecek is None:
                        fejlecek = {h.start() for h in _FEJLEC_SOR.finditer(maszkolt)}
                    if maszkolt.rfind("\n", 0, kezd) + 1 in fejlecek:
                        continue
                if sorok_elejei is None:
                    sorok_elejei = [0] + [i + 1 for i, ch in enumerate(szoveg) if ch == "\n"]
                sor = bisect.bisect_right(sorok_elejei, kezd) - 1
                tobb = len(lehet) > 1
                forras = next((f for f in ("nev", "alias", "cim", "cim2") if f in lehet.values()), "nev")
                ki.append({"kezd": kezd, "veg": vege, "sor": sor + 1, "oszlop": kezd - sorok_elejei[sor],
                           "szoveg": szoveg[kezd:vege], "cel": None if tobb else celok[0], "tobbertelmu": tobb,
                           "jeloltek": sorted(lehet)[:JELOLT_MAX] if tobb else [], "forras": forras})
                veg = vege
                break
            if len(ki) >= limit:
                break
        return {"ut": ut, "emlitesek": ki, "szotar_meret": sz.nevek}
