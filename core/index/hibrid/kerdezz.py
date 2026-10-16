"""„Kérdezz a vaulttól” — a modell nélküli váz (TERV 5.7; C25b-mag).

    kérdés → hibrid darab-jelöltek → elég forrás? → modell (hívható; JSON-sorok) → mondatonként a közös kapu → válasz

1. **Elég forrás?** Modell előtt, modell nélkül: a jelöltek közül azok maradnak, amelyekben a kérdés töveinek legalább
   `min_fedes` része áll, vagy (vektor-ág mellett) a koszinusz legalább `min_hasonlosag`. Ha egy sem marad:
   `nincs_valasz` — **a modell nem is fut** (forrás nélkül nem válaszolunk, nem kitalálunk).
2. **A modell** (`ModellHivas`: `(prompt, max_tokens) → szöveg` vagy tokenek iterálható folyama) számozott forrásokat
   kap, és mondatonként egy JSON-sort ír: `{"mondat": …, "forras": <szám>, "idezet": <a forrás szó szerinti részlete>}`.
3. **Mondatonként a közös forráshűség-kapu** (`modulok/kapuk`, `[kapuk.valasz]` profil; új kapu nincs, 48(a)): az
   idézetnek a *hivatkozott* darabban kell állnia, és a mondatnak abból kell következnie. **A forrás nélküli** (nincs
   `forras`/`idezet`, ismeretlen forrásszám) **és a bukott mondat kiesik**; az ok a statisztikában marad.
4. **Minden megmaradt mondat mellé** a forrás: blokklink (`[[út#^blokk]]`, ha az idézet bekezdésének van `^azonosítója`;
   különben a címsor `[[út#Fejezet]]`; különben `[[út]]`), a sorhatár, és a jegyzet **szó szerinti mondata** (a kapu
   találatának mondata). A válasz nem íródik a vaultba, így blokkazonosítót sem hoz létre (az gépi írás volna, 28.).
5. Ha egy mondat sem marad: `nincs_valasz`.

**Folyam.** A `folyam` generátor eseményeket ad (`mondat`, `elvetve`, `vege`), ahogy a modell sorai beérkeznek; a
fogyasztó bármikor bezárhatja — ekkor a modell tokenfolyama is bezárul (a következő tokennél megáll), és a `megszakit`
horog lefut (a workerben: `POST /v1/megszakit`; a kötés a C25b modellfele). **D9**: a hívó megmondja, kalibrált-e a modell;
ha nem, a válasz `proba: true` jelet hordoz (a vaultba egyik esetben sem ír).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from typing import Callable, Iterable, Iterator

from ...vaultio import Invalid
from .kereso import HibridKereso, Jelolt
from ...hibakod import kodol

PROMPT_VERZIO = "kerdezz-v1"
ModellHivas = Callable[[str, int], "str | Iterable[str]"]
_HORGONY_TILOS = re.compile(r"[#|^\[\]:\\%$]")


@dataclass(frozen=True)
class Beallitas:
    """A `[kereses.kerdezz]` szakasz; a küszöbök kalibrálatlan induló értékek (K160)."""
    darab_n: int = 6                 # ennyi forrás kerül a promptba
    min_fedes: float = 0.34          # a kérdés töveinek legalább ennyi része a darabban …
    min_hasonlosag: float = 0.5      # … vagy (vektor-ág mellett) legalább ennyi a koszinusz
    max_tokens: int = 700
    max_mondat: int = 8
    forras_max_karakter: int = 1600  # egy forrás legfeljebb ennyi karakterrel kerül a promptba


_MEZOK = {f.name for f in fields(Beallitas)}


def beallitas(cfg) -> Beallitas:
    adat = {k: v for k, v in dict(cfg.section("kereses", "kerdezz")).items() if not isinstance(v, dict)}
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[kereses.kerdezz]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Beallitas(**adat)


def profil(cfg=None):
    """A forráshűség-kapu `valasz` profilja (config nélkül: a profil alapértékei és a 4–120 szavas idézet, mint az os.toml)."""
    from modulok.kapuk import huseg as KH
    return KH.profil(cfg, "valasz") if cfg is not None else KH.Profil(nev="valasz", idezet_min_szo=4, idezet_max_szo=120)


PROMPT = """Válaszolj a kérdésre KIZÁRÓLAG az alábbi, számozott forrásokból (a felhasználó saját jegyzetei).
Minden mondatod egy külön sor, pontosan ebben a JSON-alakban:
{{"mondat": "<a válasz egy mondata>", "forras": <a forrás száma>, "idezet": "<a forrás szó szerinti részlete, amelyből a mondat következik>"}}
Az idézet a forrás szövegéből másolt, összefüggő részlet legyen (legalább 4 szó). Ne írj olyan mondatot, amely nem a
forrásokból következik. Ha a források nem adnak választ a kérdésre, egyetlen sort írj: {{"nincs": true}}
Legfeljebb {max_mondat} mondat. Más szöveget ne írj.

Kérdés: {kerdes}

Források:
{forrasok}
"""


def prompt(kerdes: str, jeloltek: list[Jelolt], b: Beallitas) -> str:
    reszek = []
    for i, j in enumerate(jeloltek, 1):
        d = j.darab
        fej = " › ".join((d.cim, *d.fejezet))
        reszek.append(f"[{i}] {fej}\n{d.szoveg[:b.forras_max_karakter]}")
    return PROMPT.format(kerdes=kerdes.strip(), forrasok="\n\n".join(reszek), max_mondat=b.max_mondat)


def elegseges(jeloltek: list[Jelolt], b: Beallitas) -> list[Jelolt]:
    """A forrásnak elég jelöltek (modell nélküli döntés; lásd a modul leírását)."""
    return [j for j in jeloltek if j.fedes >= b.min_fedes or (j.hasonlosag is not None and j.hasonlosag >= b.min_hasonlosag)]


def sorok(folyam: Iterable[str]) -> Iterator[str]:
    """A tokenfolyam teljes sorai, ahogy beérkeznek (az utolsó, lezáratlan sor a végén)."""
    puffer = ""
    for t in folyam:
        puffer += t
        while "\n" in puffer:
            sor, puffer = puffer.split("\n", 1)
            yield sor
    if puffer:
        yield puffer


def _json_sor(sor: str) -> dict | None:
    s = sor.strip().strip(",")
    if s.startswith("```") or not s:
        return None
    a, e = s.find("{"), s.rfind("}")
    if a < 0 or e <= a:
        return None
    try:
        v = json.loads(s[a:e + 1])
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _md(d) -> str:
    """A darab Markdown-alakja a kapunak: a címsor-út címsorokként (a bizonyíték „mondat+cím” része), utána a szöveg."""
    return "".join(f"{'#' * (i + 1)} {h}\n" for i, h in enumerate(d.fejezet)) + d.szoveg + "\n"


def horgony(d, idezet: str, kuszob: float) -> dict:
    """A forrás-link: a bekezdés, amelyben az idézet áll → `^blokk`; különben a címsor; különben a jegyzet."""
    from modulok.kapuk.forras import ForrasSzoveg
    cel = d.ut[:-3] if d.ut.lower().endswith(".md") else d.ut
    bek = next((b for b in d.bekezdesek if ForrasSzoveg.jegyzetbol(b[3] + "\n").keres(idezet, kuszob)), None)
    sor_kezd, sor_veg = (bek[0], bek[1]) if bek else (d.sor_kezd, d.sor_veg)
    if bek and bek[2]:
        return {"link": f"[[{cel}#^{bek[2]}]]", "blokk": bek[2], "sor_kezd": sor_kezd, "sor_veg": sor_veg}
    fej = d.fejezet[-1] if d.fejezet else None
    if fej and not _HORGONY_TILOS.search(fej):
        return {"link": f"[[{cel}#{fej}]]", "blokk": None, "sor_kezd": sor_kezd, "sor_veg": sor_veg}
    return {"link": f"[[{cel}]]", "blokk": None, "sor_kezd": sor_kezd, "sor_veg": sor_veg}


def _ellenoriz(adat: dict, jeloltek: list[Jelolt], prof) -> tuple[dict | None, str | None]:
    """Egy modell-sor → (elfogadott mondat, None) vagy (None, a kiesés oka)."""
    from modulok.kapuk import huseg as KH
    from modulok.kapuk.forras import ForrasSzoveg
    mondat, forras, idezet = adat.get("mondat"), adat.get("forras"), adat.get("idezet")
    if not isinstance(mondat, str) or not mondat.strip():
        return None, "nincs_mondat"
    if isinstance(forras, bool) or not isinstance(forras, int) or not isinstance(idezet, str) or not idezet.strip():
        return None, "nincs_forras"
    if not 1 <= forras <= len(jeloltek):
        return None, "ismeretlen_forras"
    d = jeloltek[forras - 1].darab
    fs = ForrasSzoveg.jegyzetbol(_md(d), cim=d.cim)
    v = KH.ellenoriz(fs, mondat.strip(), idezet.strip(), prof)
    if not v.ok:
        return None, "kapu:" + ",".join(v.okok)
    h = horgony(d, idezet.strip(), prof.idezet_kuszob)
    return {"mondat": mondat.strip(), "forras": forras, "ut": d.ut, **h, "fejezet": list(d.fejezet),
            "idezet": fs.mondat(*v.hely, max_k=prof.mondat_max_karakter), "kapu": v.to_dict()}, None


def folyam(kerdes: str, kereso: HibridKereso, hivo: ModellHivas | None, b: Beallitas | None = None, prof=None,
           kalibralt: bool = False, megszakit: Callable[[], None] | None = None) -> Iterator[dict]:
    """Az események (`{"tipus": "forrasok" | "mondat" | "elvetve" | "vege", …}`), lásd a modul leírását. `hivo` nélkül
    csak a forrásvizsgálat fut: elég forrásnál `vege` / `nincs_modell`."""
    if not isinstance(kerdes, str) or not kerdes.strip():
        raise kodol(Invalid("üres kérdés"), "hibrid.kerdezz.ures_kerdes")
    b = b or Beallitas()
    prof = prof or profil()
    jeloltek = elegseges(kereso.darab_jeloltek(kerdes, max(b.darab_n * 3, b.darab_n)), b)[:b.darab_n]
    alap = {"proba": not kalibralt, "prompt_verzio": PROMPT_VERZIO}
    yield {"tipus": "forrasok", "forrasok": [{"szam": i, "ut": j.darab.ut, "fejezet": list(j.darab.fejezet),
                                             "sor_kezd": j.darab.sor_kezd, "sor_veg": j.darab.sor_veg,
                                             "fedes": j.fedes, "hasonlosag": j.hasonlosag}
                                            for i, j in enumerate(jeloltek, 1)]}
    if not jeloltek:
        yield {"tipus": "vege", "allapot": "nincs_valasz", "ok": "nincs_eleg_forras", "mondatok": 0, "elvetve": {}, **alap}
        return
    if hivo is None:
        yield {"tipus": "vege", "allapot": "nincs_modell", "ok": "nincs_modell", "mondatok": 0, "elvetve": {}, **alap}
        return
    valasz = hivo(prompt(kerdes, jeloltek, b), b.max_tokens)
    tokenek = iter([valasz] if isinstance(valasz, str) else valasz)
    elfogadott, elvetve, nincs_jel = 0, {}, False
    lezart = False
    try:
        for sor in sorok(tokenek):
            adat = _json_sor(sor)
            if adat is None:
                if sor.strip():
                    elvetve["nem_json"] = elvetve.get("nem_json", 0) + 1
                continue
            if adat.get("nincs") is True:
                nincs_jel = True
                continue
            if elfogadott >= b.max_mondat:
                elvetve["tobb_mondat"] = elvetve.get("tobb_mondat", 0) + 1
                continue
            m, ok = _ellenoriz(adat, jeloltek, prof)
            if m is None:
                elvetve[ok] = elvetve.get(ok, 0) + 1
                yield {"tipus": "elvetve", "ok": ok}
                continue
            elfogadott += 1
            yield {"tipus": "mondat", **m}
        lezart = True
    finally:
        if not lezart:                                # a fogyasztó bezárta a folyamot: a modell is álljon meg
            close = getattr(tokenek, "close", None)
            if close is not None:
                close()
            if megszakit is not None:
                megszakit()
    allapot = "kesz" if elfogadott else "nincs_valasz"
    ok = None if elfogadott else ("modell_szerint_nincs" if nincs_jel else "minden_mondat_kiesett")
    yield {"tipus": "vege", "allapot": allapot, "ok": ok, "mondatok": elfogadott, "elvetve": elvetve, **alap}


def valaszol(kerdes: str, kereso: HibridKereso, hivo: ModellHivas | None, **kw) -> dict:
    """A teljes válasz egyben (a `folyam` eseményeiből): `{allapot, ok, mondatok: […], forrasok, elvetve, proba}`."""
    mondatok, forrasok, vege = [], [], {}
    for e in folyam(kerdes, kereso, hivo, **kw):
        if e["tipus"] == "mondat":
            mondatok.append({k: v for k, v in e.items() if k != "tipus"})
        elif e["tipus"] == "forrasok":
            forrasok = e["forrasok"]
        elif e["tipus"] == "vege":
            vege = e
    return {"kerdes": kerdes, "allapot": vege.get("allapot"), "ok": vege.get("ok"), "mondatok": mondatok,
            "forrasok": forrasok, "elvetve": vege.get("elvetve", {}), "proba": vege.get("proba", True),
            "prompt_verzio": PROMPT_VERZIO}
