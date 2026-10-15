"""Aranyhalmaz: C++ hibakeresés és tanítás (router-feladat: `kod`; C36b, `docs/C36-TERV.md` „C36b”).

12 saját feladat (`feladatok/kNN/`), feladatonként 3 egysoros beültetett hiba; a `keszit.py` a program-homokozóban igazolta,
hogy a referencia helyes (a teszteken és 100 véletlen bemeneten egyezik a lassú megoldással), és hogy minden hiba lelepleződik; a
leleplező eset (a **bizonyíték**) az `arany.json`-ban befagyasztva. A tétel kérése az élő út promptja (`modulok/cpp/ai.py`):
ugyanaz a szöveg, mint amit a „Mi a hiba?” gomb küld, így a kalibráció az éles kérésre szól (D9).

Tételek (60): `hiba` 24 (a h1 és a h2), `tipp` 12 (a h3), `megoldas` 12 (forgó hiba), `teszt` 6 és `stressz` 6 (a páratlan,
illetve a páros sorszámú feladatok egy kis bemeneten leleplezhető hibájával).

**Pontozás** (modell nélkül; a modell kódja csak a program-homokozóban fordul és fut, 53(b)):
  - `hiba`: magyar magyarázat (magyarnyelv-kapu: `MAGYAR_KUSZOB`, különben 0) × (0,7 · a sor pontos + 0,3 · a fajta egyezik);
  - `tipp`: a három szint a helyes sorrendben, magyarul, kódblokk és a javított sor nélkül (különben 0) → 0,4 + 0,6 · a 3. szint
    a hibás sorra mutat;
  - `megoldas`: 1, ha a javított program lefordul, és átmegy a leírás tesztjein, a bizonyítékon és 20 véletlen bemeneten (a referencia
    szerint; időhibánál a nagy bemeneten is), különben 0;
  - `teszt`: 0,6 · a modell bemenetei közt van, amelyen a hibás változat eltér a referenciától (érvényes bemeneten) + 0,2 · az
    érvényes bemenetek aránya + 0,2 · a modell lassú referenciája helyes (lefordul, átmegy a teszteken, és a modell bemenetein egyezik
    a mi referenciánkkal);
  - `stressz`: 0,2 · a generátor lefordul és fut + 0,2 · a generált bemenetek érvényesek + 0,4 · a mi referenciánk és a hibás változat
    eltérését `STRESSZ_MENET` menetben megtalálja + 0,2 · a modell referenciája helyes (mint fent).
A pontszám az öt mód átlagának átlaga (a módok egyenlő súllyal); a módonkénti részpontszám a `modok`-ban.

Mit nem lát: a magyarázat érthetőségét és a tipp pedagógiai értékét; a magyar szöveg helyességét (csak az arányát); hogy a diák
valódi hibái mennyire hasonlítanak a beültetettekre. A kalibrált jelet a koordinátor/felhasználó jóváhagyása után a C19 szabálya adja
(63(a)); addig a kalibrálás vázlat-aranyon tilos.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ARANY = json.loads((ITT / "arany.json").read_text(encoding="utf-8"))
VERZIO = "kod-" + (str(ARANY["verzio"]) if ARANY.get("allapot") == "jovahagyott" else f"{ARANY['verzio']}-vazlat")
ROUTER_FELADAT = "kod"
MODOK = ("hiba", "tipp", "megoldas", "teszt", "stressz")
MAGYAR_KUSZOB = 0.30          # a kódon kívüli szavak magyar aránya; az angol válasz ~0 (a C19 a mérés mintáján igazítja)
STRESSZ_MENET = 60
MEGOLDAS_VELETLEN = 20


def _mappa(fid: str) -> Path:
    return ITT / "feladatok" / fid


def _olvas(fid: str, nev: str) -> str:
    return (_mappa(fid) / nev).read_text(encoding="utf-8")


def valtozat(ref: str, h: dict) -> str:
    sorok = ref.split("\n")
    i = int(h["sor"]) - 1
    if sorok[i] != h["eredeti"]:
        raise ValueError(f"a(z) {h['id']} cseréje nem illik a ref.cpp {h['sor']}. sorára (a forrás változott: keszit.py --ir)")
    sorok[i] = h["csere"]
    return "\n".join(sorok)


def _kicsi_hiba(f: dict) -> dict:
    """A teszt/stressz tétel hibája: kis bemeneten leleplezhető (nem `ido`, nem a nagy bemenet), lehetőleg nem a leírás tesztje."""
    jo = [h for h in f["hibak"] if h["fajta"] != "ido" and h["bizonyitek"]["fajta"] == "teszt"]
    return next((h for h in jo if h["bizonyitek"]["forras"].startswith("kicsi")), jo[0] if jo else f["hibak"][0])


def tetel_lista() -> list[dict]:
    """A tételek (kérés nélkül): `{id, mod, feladat, hiba}`."""
    ki = []
    for i, f in enumerate(ARANY["feladatok"]):
        h = {x["id"]: x for x in f["hibak"]}
        for hid in ("h1", "h2"):
            ki.append({"mod": "hiba", "feladat": f["id"], "hiba": h[hid]})
        ki.append({"mod": "tipp", "feladat": f["id"], "hiba": h["h3"]})
        ki.append({"mod": "megoldas", "feladat": f["id"], "hiba": f["hibak"][i % 3]})
        ki.append({"mod": "teszt" if i % 2 == 0 else "stressz", "feladat": f["id"], "hiba": _kicsi_hiba(f)})
    for t in ki:
        t["id"] = f"{t['feladat']}-{t['hiba']['id']}-{t['mod']}"
    return ki


def tetelek(cfg):
    from modulok.cpp import ai
    for t in tetel_lista():
        ref = _olvas(t["feladat"], "ref.cpp")
        h = t["hiba"]
        biz = h["bizonyitek"] if t["mod"] in ("hiba", "tipp", "megoldas") else None
        keres = ai.keres(t["mod"], _olvas(t["feladat"], "leiras.md"), valtozat(ref, h), biz)
        yield {"id": t["id"], "keres": keres,
               "vart": {"mod": t["mod"], "feladat": t["feladat"], "hiba": h["id"], "sor": h["sor"], "fajta": h["fajta"],
                        "prompt_verzio": ai.PROMPT_VERZIO}}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): a válasz alakja értelmezhető-e a mód szerint."""
    from modulok.cpp import ai
    m = (vart or {}).get("mod")
    if m == "hiba":
        return ai.hiba_valasz(valasz)["sor"] is not None
    if m == "tipp":
        return all(ai.tipp_valasz(valasz)["szintek"])
    if m == "megoldas":
        return ai.megoldas_valasz(valasz)["kod"] is not None
    if m == "teszt":
        return bool(ai.teszt_valasz(valasz)["bemenetek"])
    if m == "stressz":
        s = ai.stressz_valasz(valasz)
        return bool(s["generator"] and s["referencia"])
    return False


# --------------------------------------------------------------------------- pontozás

def _norm(s: str) -> str:
    return "".join(s.split())


def pont_hiba(valasz, vart) -> tuple[float, str]:
    from modulok.cpp import ai
    v = ai.hiba_valasz(valasz)
    hu = ai.magyar_arany(v["magyarazat"])
    if hu < MAGYAR_KUSZOB:
        return 0.0, f"magyarnyelv-kapu: {hu:.2f}"
    if v["sor"] is None:
        return 0.0, "nincs HIBA: sor"
    p = 0.7 * (v["sor"] == vart["sor"]) + 0.3 * (v["fajta"] == vart["fajta"])
    return p, f"sor {v['sor']} (vart {vart['sor']}), fajta {v['fajta']} (vart {vart['fajta']})"


def pont_tipp(valasz, vart, eredeti: str) -> tuple[float, str]:
    from modulok.cpp import ai
    v = ai.tipp_valasz(valasz)
    if not all(v["szintek"]) or not v["sorrend_ok"]:
        return 0.0, "a három szint nincs meg a helyes sorrendben"
    szoveg = "\n".join(v["szintek"])
    hu = ai.magyar_arany(szoveg)
    if hu < MAGYAR_KUSZOB:
        return 0.0, f"magyarnyelv-kapu: {hu:.2f}"
    if v["kod_szintek"] or "```" in ai.tisztit(valasz):
        return 0.0, "kódblokk a tippben"
    if len(_norm(eredeti)) >= 8 and _norm(eredeti) in _norm(szoveg):
        return 0.0, "a tipp kiírja a javított sort"
    jo = v["hely_sor"] == vart["sor"]
    return 0.4 + 0.6 * jo, f"hely: {v['hely_sor']} (vart {vart['sor']})"


class _Gyorsitotar:
    """Feladatonként a referencia, a hibás változatok és a kis bemenetek (egy pontozási futáson belül egyszer fordulnak)."""

    def __init__(self, fut):
        self.f = fut
        self._p: dict = {}
        self._fd: dict = {}

    def fd(self, fid: str) -> dict:
        if fid not in self._fd:
            from core import cpp_teszt
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"kod_bemenet_{fid}", _mappa(fid) / "bemenet.py")
            bm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bm)
            f = next(x for x in ARANY["feladatok"] if x["id"] == fid)
            self._fd[fid] = {"f": f, "bm": bm, "ref": _olvas(fid, "ref.cpp"),
                             "tesztek": cpp_teszt.tesztek(_olvas(fid, "leiras.md"), 10.0, 1024)}
        return self._fd[fid]

    def prog(self, fid: str, hid: str | None):
        k = (fid, hid)
        if k not in self._p:
            d = self.fd(fid)
            kod = d["ref"] if hid is None else valtozat(d["ref"], next(h for h in d["f"]["hibak"] if h["id"] == hid))
            self._p[k] = self.f.fordit(kod, f"{fid}-{hid or 'ref'}")
        return self._p[k]


def _modell_ref(AE, f, gy, fid, kod, bemenetek) -> bool:
    """A modell lassú referenciája helyes-e: lefordul, átmegy a leírás tesztjein, és a bemeneteken egyezik a mi referenciánkkal."""
    d = gy.fd(fid)
    r = AE.referencia(f, kod, d["tesztek"])
    if not r["ellenorzott"]:
        return False
    ref = gy.prog(fid, None)
    for b in bemenetek:
        a, c = f.futtat(ref, b, idokorlat_s=AE.REFERENCIA_IDOKORLAT_S), f.futtat(r["program"], b, idokorlat_s=AE.REFERENCIA_IDOKORLAT_S)
        if a["allapot"] != "ok" or c["allapot"] != "ok" or not AE.egyezik(a["stdout"], c["stdout"]):
            return False
    return True


def pont_megoldas(valasz, vart, f, gy, AE) -> tuple[float, str]:
    from modulok.cpp import ai
    kod = ai.megoldas_valasz(valasz)["kod"]
    if not kod:
        return 0.0, "nincs kódblokk"
    p = f.fordit(kod, "megoldas")
    if not p.ok:
        return 0.0, f"nem fordul: {p.uzenet}"
    d = gy.fd(vart["feladat"])
    idokorlat = float(d["f"].get("idokorlat_s") or 2.0)
    t = AE.teszt_futas(f, p, d["tesztek"])
    if t["atment_db"] != t["ossz"]:
        return 0.0, f"a teszteken {t['atment_db']}/{t['ossz']}"
    h = next(x for x in d["f"]["hibak"] if x["id"] == vart["hiba"])
    biz = h["bizonyitek"]
    bemenetek = [d["bm"].general(random.Random(1000 + i), "kicsi") for i in range(MEGOLDAS_VELETLEN)]
    if biz.get("bemenet"):
        bemenetek.insert(0, biz["bemenet"])
    if biz["fajta"] in ("ido", "nagy"):
        bemenetek.append(d["bm"].general(random.Random(1), "nagy"))
    ref = gy.prog(vart["feladat"], None)
    for b in bemenetek:
        a, c = f.futtat(ref, b, idokorlat_s=idokorlat), f.futtat(p, b, idokorlat_s=idokorlat)
        if c["allapot"] != "ok" or not AE.egyezik(a["stdout"], c["stdout"]):
            return 0.0, f"eltér a referenciától ({c['allapot']})"
    return 1.0, "átment"


def pont_teszt(valasz, vart, f, gy, AE) -> tuple[float, str]:
    from modulok.cpp import ai
    v = ai.teszt_valasz(valasz)
    if not v["bemenetek"]:
        return 0.0, "nincs bemenet"
    d = gy.fd(vart["feladat"])
    ervenyes = [b for b in v["bemenetek"] if d["bm"].ervenyes(b)]
    ref, hibas = gy.prog(vart["feladat"], None), gy.prog(vart["feladat"], vart["hiba"])
    olt = False
    for b in ervenyes:
        a, c = f.futtat(ref, b), f.futtat(hibas, b)
        if a["allapot"] == "ok" and (c["allapot"] != "ok" or not AE.egyezik(a["stdout"], c["stdout"])):
            olt = True
            break
    ref_ok = _modell_ref(AE, f, gy, vart["feladat"], v["referencia"], ervenyes)
    p = 0.6 * olt + 0.2 * len(ervenyes) / len(v["bemenetek"]) + 0.2 * ref_ok
    return p, f"leleplez: {olt}, érvényes {len(ervenyes)}/{len(v['bemenetek'])}, referencia: {ref_ok}"


def pont_stressz(valasz, vart, f, gy, AE) -> tuple[float, str]:
    from modulok.cpp import ai
    v = ai.stressz_valasz(valasz)
    if not v["generator"]:
        return 0.0, "nincs generátor"
    gen = f.fordit(v["generator"], "generator")
    if not gen.ok:
        return 0.0, "a generátor nem fordul"
    d = gy.fd(vart["feladat"])
    minta = []
    for mag in range(1, 21):
        b, _ = AE.generalt_bemenet(f, gen, mag)
        if b is None:
            break
        minta.append(b)
    if not minta:
        return 0.0, "a generátor nem fut"
    erv = sum(1 for b in minta if d["bm"].ervenyes(b)) / 20
    s = AE.stressz(f, gen, gy.prog(vart["feladat"], None), gy.prog(vart["feladat"], vart["hiba"]), menet=STRESSZ_MENET,
                   ervenyes=d["bm"].ervenyes)
    olt = s["ellenpelda"] is not None
    ref_ok = _modell_ref(AE, f, gy, vart["feladat"], v["referencia"], [b for b in minta if d["bm"].ervenyes(b)][:10])
    p = 0.2 + 0.2 * erv + 0.4 * olt + 0.2 * ref_ok
    return p, f"érvényes {erv:.2f}, leleplez: {olt} ({s['menet']} menet), referencia: {ref_ok}"


def pontoz(rekordok, futtato=None) -> dict:
    from modulok.cpp import ai_ellenorzes as AE
    reszek: dict[str, list[float]] = defaultdict(list)
    rossz = []
    sajat = futtato is None
    if sajat:
        from core import config
        futtato = AE.Futtato(config.load()).__enter__()
    try:
        gy = _Gyorsitotar(futtato)
        for r in rekordok:
            vart = r["vart"]
            m = vart["mod"]
            valasz = r.get("valasz")
            if valasz is None:
                p, ok = 0.0, "nincs válasz"
            elif m == "hiba":
                p, ok = pont_hiba(valasz, vart)
            elif m == "tipp":
                h = next(x for x in gy.fd(vart["feladat"])["f"]["hibak"] if x["id"] == vart["hiba"])
                p, ok = pont_tipp(valasz, vart, h["eredeti"])
            elif m in ("megoldas", "teszt", "stressz"):
                if futtato.hiany():
                    raise RuntimeError(f"a pontozáshoz a homokozó kell: {futtato.hiany()}")
                p, ok = {"megoldas": pont_megoldas, "teszt": pont_teszt, "stressz": pont_stressz}[m](valasz, vart, futtato, gy, AE)
            else:
                p, ok = 0.0, f"ismeretlen mód: {m}"
            reszek[m].append(p)
            if p < 1.0:
                rossz.append({"id": r["id"], "pont": round(p, 3), "indok": str(ok)[:200]})
    finally:
        if sajat:
            futtato.__exit__(None, None, None)
    modok = {m: round(sum(v) / len(v), 4) for m, v in reszek.items() if v}
    return {"pontszam": round(sum(modok.values()) / len(modok), 4) if modok else 0.0, "modok": modok,
            "tetelek_modonkent": {m: len(v) for m, v in reszek.items()}, "rossz": rossz}
