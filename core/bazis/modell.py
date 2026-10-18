"""A `.base` fájlformátum (C12): betöltés, ellenőrzés, szerializálás, tiszta módosítások.

Forrás: az Obsidian `Bases syntax` oldala. A fájl YAML: `filters`, `formulas`, `properties`, `summaries`, `views`.
A **nyers** YAML-szerkezet (`Bazis.nyers`) az igazság: az ismeretlen kulcs (nézetek további kulcsai, jövőbeli
mezők) íráskor megmarad, a kulcsok sorrendje a forráséval azonos. A `.base` megjegyzései az újraíráskor
elvesznek (teljes YAML-újrakiírás, mint az Obsidianban; 23. döntés).

`modosit(szoveg, muvelet)` **tiszta**: új szöveget számol, nem ír (a felület írja az egyetlen írási úton). Az új
szöveg visszaolvasás-próbán megy át: ha a visszaolvasott szerkezet eltér, vagy az eredmény érvénytelen, a szöveg
nem változik és a `hibak` megmondja, miért.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import yaml

from ..hibakod import angol_uzenet, json_param
from ..index.elemzo import _Betolto
from .kifejezes import KifejezesHiba, elemez
from .kiertekelo import KepletTar, fordit, futtat
from .ertekek import FutasHiba, igaz_e

UJ_SZOVEG = "views:\n  - type: table\n    name: Table\n"
TIPUSOK = ("table", "cards", "list", "kanban")
NEZET_NEVEK = {"table": "Table", "cards": "Cards", "list": "List", "kanban": "Kanban"}   # az új nézet alapneve (fájladat: angol)
_TIPUS_ALIAS = {"board": "kanban"}                    # a Kanban `type` szava feltételezés (K12)
ALAP_OSZLOPOK = ["file.name"]
TERMEK = ("file", "note", "formula")
OSSZESITOK = ("Average", "Min", "Max", "Sum", "Range", "Median", "Stddev", "Earliest", "Latest", "Checked",
              "Unchecked", "Empty", "Filled", "Unique")


def hiba(hely: str, uzenet: str | None = None, **kieg) -> dict:
    """Egy hiba / figyelmeztetés: `{hely, uzenet, kod?, param?, …}`. Ha `kod` van, az `uzenet` az angol tartalék-mondat
    a `hibakodok.BAZIS_ANGOL` szerint (10-bases-01); a kliens a `kod` + `param` szerint fordít."""
    kod = kieg.get("kod")
    if kod:
        uzenet = angol_uzenet(kod, kieg.get("param"), uzenet or kod)
        kieg["param"] = json_param(kieg.get("param"))
    return {"hely": hely, "uzenet": uzenet, **kieg}


def hiba_kivetelbol(hely: str, e, **kieg) -> dict:
    """A kódolt kivétel (`KifejezesHiba` / `FutasHiba` / `MuveletHiba`) hibasora."""
    return hiba(hely, None, kod=e.kod, param=e.param, **kieg)


# ================================================================ tulajdonság-azonosító

def tulajdonsag_id(s: str) -> tuple[str, str]:
    """`file.name` → (`file`, `name`), `note.age` → (`note`, `age`), `formula.x` → (`formula`, `x`); előtag nélkül
    `note`. (A `note.` előtag nélküli név egyetlen tulajdonság, akkor is, ha pontot tartalmaz.)"""
    ter, _, nev = str(s).partition(".")
    if nev and ter in TERMEK:
        return ter, nev
    return "note", str(s)


def id_szovegbe(ter: str, nev: str) -> str:
    return nev if ter == "note" else f"{ter}.{nev}"


# ================================================================ szűrő

@dataclass(slots=True)
class Szuro:
    """Egy szűrő-csomópont: `kif` (egy kifejezés-szöveg) vagy `es` / `vagy` / `nem` (a gyerekek konjunkciója,
    diszjunkciója, illetve „egyik sem”)."""
    fajta: str
    szoveg: str | None = None
    gyerekek: list = field(default_factory=list)
    hely: str = ""


def szuro_fa(nyers, hely: str) -> tuple[Szuro | None, list[dict]]:
    """A `filters` részfa szerkezete. `None` / üres → nincs szűrő. A szerkezeti hiba a `hibak`-ban."""
    hibak: list[dict] = []
    if nyers is None:
        return None, hibak
    if isinstance(nyers, str):
        return Szuro("kif", nyers, hely=hely), hibak
    if isinstance(nyers, list):                         # lista: implicit `and`
        nyers = {"and": nyers}
    if not isinstance(nyers, dict):
        return None, [hiba(hely, "Filter", kod="bazis.modell.szuro_szerkezet")]
    if len(nyers) != 1 or next(iter(nyers)) not in ("and", "or", "not"):
        return None, [hiba(hely, "Filter object", kod="bazis.modell.szuro_objektum_kulcs")]
    kulcs, lista = next(iter(nyers.items()))
    if lista is None:
        lista = []
    if not isinstance(lista, list):
        return None, [hiba(f"{hely}.{kulcs}", "List", kod="bazis.modell.kulcs_erteke_lista", param={"kulcs": kulcs})]
    gyerekek = []
    for i, e in enumerate(lista):
        sz, h = szuro_fa(e, f"{hely}.{kulcs}[{i}]")
        hibak += h
        if sz is not None:
            gyerekek.append(sz)
    return Szuro({"and": "es", "or": "vagy", "not": "nem"}[kulcs], gyerekek=gyerekek, hely=f"{hely}.{kulcs}"), hibak


class SzuroHiba(FutasHiba):
    """Egy szűrő-utasítás futási hibája; a `hely` azonosítja az utasítást (a hibaszámláló kulcsa)."""

    def __init__(self, hely: str, szoveg: str, reszlet: str):
        super().__init__("bazis.modell.szuro_utasitas", {"szoveg": szoveg, "reszlet": reszlet})
        self.hely = hely


def szuro_fordit(sz: Szuro | None) -> tuple:
    """(`f(kor) → bool`, hibák): a szűrő zárványa. Az elemzési/fordítási hibás utasítás a hibalistába kerül, és
    mindig hamis (a nézet nem mutat sort, nem tévesztően mindet). Futási hiba `SzuroHiba`."""
    hibak: list[dict] = []
    if sz is None:
        return (lambda kor: True), hibak

    def ford(n: Szuro):
        if n.fajta == "kif":
            try:
                f = fordit(elemez(n.szoveg))
            except KifejezesHiba as e:
                hibak.append(hiba(n.hely, kod="bazis.modell.szuro_utasitas", param={"szoveg": n.szoveg, "reszlet": str(e)}))
                return lambda kor: False

            def utasitas(kor):
                try:
                    return igaz_e(futtat(f, kor))
                except FutasHiba as e:
                    raise SzuroHiba(n.hely, n.szoveg, e.uzenet) from None
            return utasitas
        gy = [ford(x) for x in n.gyerekek]
        if n.fajta == "es":
            return lambda kor: all(g(kor) for g in gy)
        if n.fajta == "vagy":
            return lambda kor: any(g(kor) for g in gy)
        return lambda kor: not any(g(kor) for g in gy)
    return ford(sz), hibak


# ================================================================ modell

@dataclass(slots=True)
class Nezet:
    index: int
    nyers: dict
    nev: str
    tipus: str                      # table | cards | kanban
    eredeti_tipus: str
    ismert: bool

    def kulcs(self, k, alap=None):
        return self.nyers.get(k, alap)

    def oszlopok(self) -> list[str]:
        o = self.nyers.get("order")
        return [str(x) for x in o] if isinstance(o, list) else list(ALAP_OSZLOPOK)

    def rendezes(self) -> list[tuple[str, str]]:
        """[(tulajdonság-azonosító, ASC|DESC)] az érvényes `sort` bejegyzésekből."""
        ki = []
        s = self.nyers.get("sort")
        for e in s if isinstance(s, list) else []:
            if isinstance(e, dict) and isinstance(e.get("property"), str):
                ki.append((e["property"], "DESC" if str(e.get("direction", "ASC")).upper() == "DESC" else "ASC"))
        return ki

    def csoport_sorrend(self) -> list | None:
        """A `groupOrder` lista (a csoport-értékek megjelenő sorrendje; `None` elem = az „üres érték” csoport), vagy `None`,
        ha a kulcs hiányzik / nem lista: ekkor minden csoport látszik a `groupBy` sorrendjében (10-bases-05)."""
        g = self.nyers.get("groupOrder")
        return list(g) if isinstance(g, list) else None

    def csoport(self) -> tuple[str, str] | None:
        g = self.nyers.get("groupBy")
        if isinstance(g, dict) and isinstance(g.get("property"), str):
            return g["property"], "DESC" if str(g.get("direction", "ASC")).upper() == "DESC" else "ASC"
        return None


@dataclass
class Bazis:
    nyers: dict
    nezetek: list[Nezet]
    figyelmeztetesek: list[dict] = field(default_factory=list)
    vegzetes: bool = False          # a fájl nem értelmezhető (YAML-hiba, nem objektum gyökér)

    @property
    def kepletek(self) -> dict:
        k = self.nyers.get("formulas")
        return k if isinstance(k, dict) else {}

    @property
    def tulajdonsagok(self) -> dict:
        k = self.nyers.get("properties")
        return k if isinstance(k, dict) else {}

    @property
    def osszesitok(self) -> dict:
        k = self.nyers.get("summaries")
        return k if isinstance(k, dict) else {}

    def megjelenes(self, azon: str) -> str | None:
        p = self.tulajdonsagok.get(azon)
        n = p.get("displayName") if isinstance(p, dict) else None
        return str(n) if n not in (None, "") else None

    def nezet_keres(self, nezet) -> Nezet | None:
        """Index (szám vagy számjegyes szöveg) vagy név szerint; `None` → az első."""
        if not self.nezetek:
            return None
        if nezet is None or nezet == "":
            return self.nezetek[0]
        if isinstance(nezet, int) and not isinstance(nezet, bool):
            return self.nezetek[nezet] if 0 <= nezet < len(self.nezetek) else None
        for n in self.nezetek:
            if n.nev == nezet:
                return n
        for n in self.nezetek:
            if n.nev.casefold() == str(nezet).casefold():
                return n
        return None


def _nezet(i: int, n: dict, figy: list) -> Nezet:
    eredeti = str(n.get("type", "table"))
    tipus = _TIPUS_ALIAS.get(eredeti.lower(), eredeti.lower())
    ismert = tipus in TIPUSOK
    if not ismert:
        figy.append(hiba(f"views[{i}]", "Unknown view type", kod="bazis.modell.ismeretlen_nezettipus", param={"eredeti": eredeti}))
        tipus = "table"
    if n.get("groupOrder") is not None and not isinstance(n.get("groupOrder"), list):
        figy.append(hiba(f"views[{i}].groupOrder", "List", kod="bazis.modell.csoportrend_lista"))
    nev = n.get("name")
    return Nezet(i, n, str(nev) if nev not in (None, "") else f"View {i + 1}", tipus, eredeti, ismert)


def _yaml(szoveg: str):
    return yaml.load(szoveg, Loader=_Betolto)


def betolt(szoveg: str) -> tuple[Bazis, list[dict]]:
    """A `.base` szövegéből (`Bazis`, hibák). Üres szöveg → egy alap táblázat-nézet. Szintaktikai vagy szerkezeti
    hiba (YAML, gyökér, szűrő, képlet, összesítő) a hibák közt; a figyelmeztetések a `Bazis`-on."""
    hibak: list[dict] = []
    try:
        nyers = _yaml(szoveg)
    except yaml.YAMLError as e:
        return Bazis({}, [], vegzetes=True), [hiba("yaml", kod="bazis.modell.yaml_hiba", param={"e": " ".join(str(e).split())[:300]})]
    if nyers is None:
        nyers = {}
    if not isinstance(nyers, dict):
        return Bazis({}, [], vegzetes=True), [hiba("yaml", "Root", kod="bazis.modell.base_gyoker")]
    nyers = {str(k): v for k, v in nyers.items()}
    figy: list[dict] = []
    for kulcs in ("formulas", "properties", "summaries"):
        if nyers.get(kulcs) is not None and not isinstance(nyers[kulcs], dict):
            hibak.append(hiba(kulcs, "Key-value pairs", kod="bazis.modell.kulcs_ertek_parok", param={"kulcs": kulcs}))
    nezetek_nyers = nyers.get("views")
    if nezetek_nyers is None:
        nezetek_nyers = []
    if not isinstance(nezetek_nyers, list):
        hibak.append(hiba("views", "List", kod="bazis.modell.views_lista"))
        nezetek_nyers = []
    nezetek = []
    for i, n in enumerate(nezetek_nyers):
        if not isinstance(n, dict):
            hibak.append(hiba(f"views[{i}]", "Pairs", kod="bazis.modell.nezet_ertek_parok"))
            continue
        nezetek.append(_nezet(len(nezetek), n, figy))
    if not nezetek and not hibak:                   # üres fájl / üres lista: az alap nézet csak megjelenítés
        nezetek = [_nezet(0, {"type": "table", "name": "Table"}, figy)]
    b = Bazis(nyers, nezetek, figy)
    # szűrők és képletek ellenőrzése (elemzés, ismeretlen függvény, körkörös hivatkozás)
    hely_szurok = [("filters", nyers.get("filters"))] + [
        (f"views[{n.index}].filters", n.nyers.get("filters")) for n in nezetek]
    for hely, ny in hely_szurok:
        fa, h = szuro_fa(ny, hely)
        hibak += h
        hibak += szuro_fordit(fa)[1]
    kt = KepletTar(b.kepletek)
    for nev in kt.hiba:
        hibak.append(hiba(f"formulas.{nev}", kod="bazis.modell.keplet_hiba", param={"reszlet": kt.hiba_szoveg(nev)}))
    for nev, kif in b.osszesitok.items():
        try:
            fordit(elemez(kif))
        except KifejezesHiba as e:
            hibak.append(hiba(f"summaries.{nev}", kod="bazis.modell.osszesito_hiba", param={"reszlet": str(e)}))
        except Exception:                           # a nem szöveg kifejezés
            hibak.append(hiba(f"summaries.{nev}", "Text", kod="bazis.modell.osszesito_szoveg"))
    return b, hibak


# ================================================================ szerializálás

class _Kiiro(yaml.SafeDumper):
    """A forrás kulcssorrendje, behúzott listák (`- ` a kulcs alatt, két szóközzel), Unicode, nincs sortörés."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def szerializal(nyers) -> str:
    return yaml.dump(nyers, Dumper=_Kiiro, sort_keys=False, allow_unicode=True, default_flow_style=False,
                     width=10_000, indent=2)


# ================================================================ módosítás

class MuveletHiba(ValueError):
    """Érvénytelen módosítási művelet (hiányzó vagy rossz paraméter): `kod` + `param`, az angol tartalék az üzenet."""

    def __init__(self, kod: str, param: dict | None = None):
        self.kod, self.param = kod, json_param(param)
        super().__init__(angol_uzenet(kod, param, kod))


def _nezet_hely(nyers: dict, index) -> dict:
    nezetek = nyers.get("views")
    if not isinstance(index, int) or isinstance(index, bool) or not isinstance(nezetek, list) \
            or not 0 <= index < len(nezetek) or not isinstance(nezetek[index], dict):
        raise MuveletHiba("bazis.modell.nincs_nezet", {"nezet": repr(index)})
    return nezetek[index]


def _szuro_szovegbol(szoveg) -> object:
    """A szűrő-mező szövegéből a `filters` értéke: üres → nincs; YAML-szerkezet (and/or/not, lista) vagy egyetlen
    kifejezés. A YAML-ként nem olvasható szöveg (pl. `"a" == b`) egyetlen kifejezés."""
    if not isinstance(szoveg, str):
        raise MuveletHiba("bazis.modell.szuro_szoveg_kell")
    if not szoveg.strip():
        return None
    try:
        v = _yaml(szoveg)
    except yaml.YAMLError:
        return szoveg.strip()
    return v if isinstance(v, (dict, list)) else szoveg.strip()


def szuro_szoveg(nyers) -> str:
    """A `filters` részfa a szerkesztő-mező szövegeként: egyetlen kifejezés → maga a szöveg, szerkezet → YAML
    (a `szuro_beallit` ugyanezt olvassa vissza); nincs szűrő → üres."""
    if nyers is None:
        return ""
    if isinstance(nyers, str):
        return nyers
    return szerializal(nyers).rstrip("\n")


def _kepelt_hivatkozas_torles(nyers: dict, nev: str) -> None:
    """A törölt képlet oszlopként való említései (`order`, `columnSize`, `summaries`, `properties`) is törlődnek."""
    azon = f"formula.{nev}"
    for n in nyers.get("views") or []:
        if not isinstance(n, dict):
            continue
        if isinstance(n.get("order"), list):
            n["order"] = [x for x in n["order"] if x != azon]
        for k in ("columnSize", "summaries"):
            if isinstance(n.get(k), dict):
                n[k].pop(azon, None)
                if not n[k]:
                    del n[k]
    if isinstance(nyers.get("properties"), dict):
        nyers["properties"].pop(azon, None)
        if not nyers["properties"]:
            del nyers["properties"]


def _alkalmaz(nyers: dict, m: dict) -> str:
    """A művelet a nyers szerkezeten; a visszaadott szöveg a változás leírása. `MuveletHiba` rossz paraméterre."""
    fajta = m.get("fajta")
    if fajta == "nezet_beallit":
        n = _nezet_hely(nyers, m.get("nezet"))
        kulcs = m.get("kulcs")
        if not isinstance(kulcs, str) or not kulcs:
            raise MuveletHiba("bazis.modell.hianyzik_kulcs")
        alkulcs, ertek = m.get("alkulcs"), m.get("ertek")
        if alkulcs is not None:
            cel = n.get(kulcs)
            if not isinstance(cel, dict):
                cel = {}
            if ertek is None:
                cel.pop(alkulcs, None)
            else:
                cel[alkulcs] = ertek
            ertek = cel or None
        if ertek is None:
            n.pop(kulcs, None)
        else:
            n[kulcs] = ertek
        return f"view {kulcs}"
    if fajta == "nezet_uj":
        nezetek = nyers.setdefault("views", [])
        if not isinstance(nezetek, list):
            raise MuveletHiba("bazis.modell.views_lista")
        tipus = m.get("tipus") or "table"
        nev = m.get("nev") or NEZET_NEVEK.get(tipus, "View")
        nevek = {str(n.get("name")) for n in nezetek if isinstance(n, dict)}
        alap, i = nev, 2
        while nev in nevek:
            nev, i = f"{alap} {i}", i + 1
        uj = {"type": tipus, "name": nev}
        nezetek.append(uj)
        return "new view"
    if fajta == "nezet_torol":
        _nezet_hely(nyers, m.get("nezet"))
        del nyers["views"][m["nezet"]]
        return "view deleted"
    if fajta == "nezet_mozgat":
        _nezet_hely(nyers, m.get("nezet"))
        ujindex = m.get("ujindex")
        if not isinstance(ujindex, int) or not 0 <= ujindex < len(nyers["views"]):
            raise MuveletHiba("bazis.modell.ervenytelen_hely")
        nyers["views"].insert(ujindex, nyers["views"].pop(m["nezet"]))
        return "view moved"
    if fajta == "szuro_beallit":
        hol = m.get("hol", "globalis")
        ertek = _szuro_szovegbol(m.get("yaml"))
        cel = nyers if hol == "globalis" else _nezet_hely(nyers, hol)
        if ertek is None:
            cel.pop("filters", None)
        else:
            cel["filters"] = ertek
        return "filter"
    if fajta == "keplet_beallit":
        nev = m.get("nev")
        if not isinstance(nev, str) or not nev.strip():
            raise MuveletHiba("bazis.modell.hianyzik_kepletnev")
        kif = m.get("kifejezes")
        kepletek = nyers.get("formulas")
        if kif is None:
            if isinstance(kepletek, dict) and nev in kepletek:
                del kepletek[nev]
                if not kepletek:
                    del nyers["formulas"]
                _kepelt_hivatkozas_torles(nyers, nev)
            return "formula deleted"
        if not isinstance(kif, str):
            raise MuveletHiba("bazis.modell.keplet_szoveg_kell")
        if not isinstance(kepletek, dict):
            kepletek = nyers["formulas"] = {}
        kepletek[nev] = kif
        return "formula"
    if fajta == "megjelenites_beallit":
        azon, nev = m.get("id"), m.get("displayName")
        if not isinstance(azon, str) or not azon:
            raise MuveletHiba("bazis.modell.hianyzik_tulajdonsag")
        tul = nyers.get("properties")
        if not isinstance(tul, dict):
            tul = nyers["properties"] = {}
        if nev in (None, ""):
            if isinstance(tul.get(azon), dict):
                tul[azon].pop("displayName", None)
                if not tul[azon]:
                    del tul[azon]
            if not tul:
                nyers.pop("properties", None)
        else:
            if not isinstance(tul.get(azon), dict):
                tul[azon] = {}
            tul[azon]["displayName"] = str(nev)
        return "display"
    raise MuveletHiba("bazis.modell.ismeretlen_muvelet", {"fajta": repr(fajta)})


def _forras_csere(regi: str, uj) -> tuple[str, list[dict], str]:
    """A teljes `.base` forrásnézetben szerkesztett szövege (a megjegyzések megmaradnak, nincs újrakiírás). Csak az
    **új** hiba akadályoz: a YAML-hiba mindig, a szűrő-, képlet-, összesítő-hiba csak ha a régi szövegben még nem
    volt (így a már hibás fájl javítható lépésenként)."""
    if not isinstance(uj, str):
        return regi, [hiba("muvelet", "Text", kod="bazis.modell.hianyzik_szoveg")], ""
    _, regi_hibak = betolt(regi)
    _, uj_hibak = betolt(uj)
    regiek = {(h["hely"], h["uzenet"]) for h in regi_hibak}
    uj_csak = [h for h in uj_hibak if (h["hely"], h["uzenet"]) not in regiek or h["hely"] == "yaml"]
    if uj_csak:
        return regi, uj_csak, ""
    return uj, [], "source"


def modosit(szoveg: str, muvelet: dict) -> tuple[str, list[dict], str]:
    """(új szöveg, hibák, változás-leírás). Hibánál az új szöveg a régi (nem változik semmi).

    A hiba lehet: a `.base` nem értelmezhető, a művelet paramétere rossz, az eredmény érvénytelen (szűrő- vagy
    képlethiba), vagy a visszaolvasás eltér. Az érvényes, de **már korábban is hibás** részek (egy másik nézet
    hibás szűrője) nem akadályozzák az új módosítást: csak az új hibák számítanak."""
    if not isinstance(muvelet, dict):
        return szoveg, [hiba("muvelet", "Object", kod="bazis.modell.muvelet_objektum")], ""
    if muvelet.get("fajta") == "forras_csere":
        return _forras_csere(szoveg, muvelet.get("szoveg"))
    try:
        nyers = _yaml(szoveg)
    except yaml.YAMLError as e:
        return szoveg, [hiba("yaml", kod="bazis.modell.nem_ertelmezheto", param={"e": " ".join(str(e).split())[:300]})], ""
    if nyers is None:
        nyers = {}
    if not isinstance(nyers, dict):
        return szoveg, [hiba("yaml", "Root", kod="bazis.modell.base_gyoker")], ""
    nyers = copy.deepcopy({str(k): v for k, v in nyers.items()})
    if not nyers.get("views") and muvelet.get("fajta") not in ("nezet_uj",):
        nyers["views"] = [{"type": "table", "name": "Table"}]      # az üres fájl alap nézete így lesz valódi
    try:
        valtozas = _alkalmaz(nyers, muvelet)
    except MuveletHiba as e:
        return szoveg, [hiba_kivetelbol("muvelet", e)], ""
    uj = szerializal(nyers)
    # visszaolvasás-próba: ugyanazt a szerkezetet kell adnia
    try:
        vissza = _yaml(uj)
    except yaml.YAMLError as e:
        return szoveg, [hiba("yaml", "Unreadable", kod="bazis.modell.kiirt_nem_olvashato", param={"e": e})], ""
    if vissza != nyers:
        return szoveg, [hiba("yaml", "Differs", kod="bazis.modell.kiirt_elter")], ""
    _, regi_hibak = betolt(szoveg)
    _, uj_hibak = betolt(uj)
    regiek = {(h["hely"], h["uzenet"]) for h in regi_hibak}
    uj_csak = [h for h in uj_hibak if (h["hely"], h["uzenet"]) not in regiek]
    if uj_csak:
        return szoveg, uj_csak, ""
    return uj, [], valtozas
