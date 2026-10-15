"""Aranyhalmaz: összefoglalás és tanulókártya (router-feladat: `szoveg`) — 20 jegyzet, kétféle tétel.

A források a `forrasok/jNN.md` fagyasztott másolatok (a vault későbbi szerkesztése nem rontja el a mérést).

**Összefoglalás** (`ossz-jNN`): a modell állításokat ad, mindegyik mellé szó szerinti idézetet a jegyzetből.
  - idézet-hűség: az idézet megtalálható a forrásban, és 4–45 szó (az egész jegyzet idézése nem ér pontot);
  - alátámasztás: az állítás tartalmi szavainak legalább 30%-a az idézett részben áll (lexikai közelítés);
  - lefedettség: az arany kulcsrészeinek hány százalékát éri érvényes idézet.
**Kártya** (`kartya-jNN`): `kerdes`, `valasz`, `forras` (szó szerinti forrásmondat). Kártyánként négy kapu:
  - kötött: a `forras` megtalálható a jegyzetben; igaz: a válasz tartalmi szavai (és számai) a forrásmondatban
    állnak; atomi: rövid válasz, egy kérdés, nincs felsorolás; egyértelmű: a kérdés önmagában érthető, nem
    árulja el a választ, és nem ismétlődik;
  - lefedettség: az arany kártyázható tényeinek hány százalékához készült átmenő kártya.

Mit nem lát: a szabály lexikai. Az átfogalmazott, de hamis állítást és a rosszul feltett, de formailag jó
kérdést nem fogja meg; ezt a C19 rétegzett mintáján kell bírálni. A részletek tételenként megadják, melyik
állítás vagy kártya melyik kapun bukott.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import idezet, kimenet, tavolsag  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "szoveg-" + A.verzio(ARANY)
ROUTER_FELADAT = "szoveg"

IDEZET_SZO = (4, 45)        # érvényes idézet hossza szóban
ALLITAS_MAX = 12            # ennyi állítás számít (a többi nem javít)
KARTYA_MAX = 16
ALATAMASZTAS = 0.3
VALASZ_SZO_MAX = 12
IGAZ_ARANY = 0.6
SULY_OSSZ = {"huseg": 0.4, "alatamasztas": 0.2, "lefedettseg": 0.4}
SULY_KARTYA = {"minoseg": 0.6, "lefedettseg": 0.4}

def prompt_ossz(szoveg: str) -> str:
    """Az összefoglalás-tétel promptja: a szöveg egyetlen helye a `modulok/osszefoglalas/promptok.py` (C26b: a kalibrált és az éles
    lánc prompt ne térjen el; a bájtra azonos szöveget a `tests/test_osszefoglalas_promptok.py` rögzíti)."""
    from modulok.osszefoglalas import promptok
    return promptok.jegyzet_prompt(szoveg)


PROMPT_KARTYA = (
    "Készíts tanulókártyákat az alábbi jegyzetből, magyarul (8–14 kártya). Egy kártya egyetlen tényt kérdez. "
    "A kérdés önmagában érthető legyen (ne utaljon a jegyzetre vagy a szövegkörnyezetre), a válasz rövid "
    "(legfeljebb 12 szó). Mindegyik kártyához add meg a jegyzet SZÓ SZERINTI mondatát, amelyből a válasz "
    "következik.\n"
    'Csak JSON-t adj vissza, ebben az alakban: [{{"kerdes": "…", "valasz": "…", "forras": "…"}}]\n\nJEGYZET:\n{szoveg}')

_UTALAS = re.compile(r"\b(a jegyzet|a szöveg|a fenti|az alábbi|az előző|a következő|fentebb|lentebb|az említett)\b", re.I)
_NEVMAS_ELEJEN = re.compile(r"^(ez|ezt|ezek|az|azt|azok|ő|ők|itt|ott|ekkor|akkor)\b", re.I)

_forrasok: dict[str, idezet.Forras] = {}


def forras_szoveg(jid: str) -> str:
    return (ITT / "forrasok" / f"{jid}.md").read_text(encoding="utf-8")


def forras(jid: str) -> idezet.Forras:
    if jid not in _forrasok:
        _forrasok[jid] = idezet.Forras(forras_szoveg(jid))
    return _forrasok[jid]


def jegyzet(jid: str) -> dict:
    return next(j for j in ARANY["jegyzetek"] if j["id"] == jid)


def tetelek(cfg):
    for j in ARANY["jegyzetek"]:
        szoveg = forras_szoveg(j["id"])
        yield {"id": f"ossz-{j['id']}",
               "keres": {"messages": [{"role": "user", "content": prompt_ossz(szoveg)}], "max_tokens": 1500},
               "vart": {"fajta": "ossz", "jegyzet": j["id"]}}
        yield {"id": f"kartya-{j['id']}",
               "keres": {"messages": [{"role": "user", "content": PROMPT_KARTYA.format(szoveg=szoveg)}], "max_tokens": 1800},
               "vart": {"fajta": "kartya", "jegyzet": j["id"]}}


def _ervenyes_idezet(f: idezet.Forras, szoveg) -> dict | None:
    """Megtalált és megengedett hosszú idézet → a találat, különben `None`."""
    if not isinstance(szoveg, str):
        return None
    t = f.keres(szoveg)
    if not t["talalt"] or not IDEZET_SZO[0] <= t["szo"][1] - t["szo"][0] <= IDEZET_SZO[1]:
        return None
    return t


def _resz(f: idezet.Forras, t: dict) -> str:
    return f.szoveg[t["hely"][0]:t["hely"][1]]


def _er(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Két forrásrész érdemben átfed: az egyik legalább fele a másikban áll."""
    kozos = idezet.atfedes(a, b)
    return kozos >= 0.5 * min(a[1] - a[0], b[1] - b[0])


kulcs_turo = kimenet.kulcs_turo          # a közös hely (C23b): a kártya-lánc elemzője is ezt hívja


def pontoz_ossz(jid: str, valasz) -> dict:
    f = forras(jid)
    allitasok = kulcs_turo(kimenet.lista_kinyer(valasz, ("allitas",))[:ALLITAS_MAX], ("allitas", "idezet"))
    kulcsok = [f.keres(k["idezet"])["szo"] for k in jegyzet(jid)["kulcsreszek"]]
    ervenyes, hibak, alatamasztott = [], [], 0
    for i, a in enumerate(allitasok):
        t = _ervenyes_idezet(f, a.get("idezet"))
        if t is None:
            hibak.append({"allitas": i + 1, "hiba": "az idézet nincs a forrásban vagy túl hosszú/rövid"})
            continue
        ervenyes.append(t["szo"])
        tov = tavolsag.tovek(str(a.get("allitas", "")))
        if tov and len(tov & tavolsag.tovek(_resz(f, t))) / len(tov) >= ALATAMASZTAS:
            alatamasztott += 1
        else:
            hibak.append({"allitas": i + 1, "hiba": "az állítás szavai nem állnak az idézetben"})
    n = len(allitasok)
    resz = {"huseg": len(ervenyes) / n if n else 0.0,
            "alatamasztas": alatamasztott / n if n else 0.0,
            "lefedettseg": A.atlag(any(k and _er(e, k) for e in ervenyes) for k in kulcsok)}
    return {"pont": sum(SULY_OSSZ[k] * v for k, v in resz.items()), **resz, "allitasok": n, "hibak": hibak}


def _kartya_kapuk(f: idezet.Forras, k: dict, elozok: list[tuple]) -> tuple[dict, dict | None]:
    kerdes, valasz = str(k.get("kerdes", "")).strip(), str(k.get("valasz", "")).strip()
    t = _ervenyes_idezet(f, k.get("forras"))
    kapu = {"kotott": t is not None, "igaz": False, "atomi": False, "egyertelmu": False}
    vt = tavolsag.tovek(valasz)
    if t is not None and (vt or re.search(r"\d", valasz)):
        resz = _resz(f, t)
        szamok = re.findall(r"\d+", valasz)
        kapu["igaz"] = ((not vt or len(vt & tavolsag.tovek(resz)) / len(vt) >= IGAZ_ARANY)
                        and all(s in resz for s in szamok))
    vszo = tavolsag.szavak(valasz)
    kapu["atomi"] = (0 < len(vszo) <= VALASZ_SZO_MAX and kerdes.count("?") == 1 and ";" not in valasz
                     and "\n" not in valasz and valasz.count(",") <= 2)
    kt = tavolsag.tovek(kerdes)
    jel = (tavolsag.hajt(" ".join(tavolsag.szavak(kerdes))), t["szo"] if t else None, tavolsag.hajt(valasz))
    ismetles = any(jel[0] == e[0] or (jel[1] and jel[1] == e[1] and jel[2] == e[2]) for e in elozok)
    kapu["egyertelmu"] = (len(tavolsag.szavak(kerdes)) >= 3 and not _UTALAS.search(kerdes)
                          and not _NEVMAS_ELEJEN.search(kerdes) and not (vt and vt <= kt) and not ismetles)
    elozok.append(jel)
    return kapu, t


def pontoz_kartya(jid: str, valasz) -> dict:
    f = forras(jid)
    kartyak = kulcs_turo(kimenet.lista_kinyer(valasz, ("kerdes",))[:KARTYA_MAX], ("kerdes", "valasz", "forras"))
    tenyek = [f.keres(t["forras"])["szo"] for t in jegyzet(jid)["tenyek"]]
    elozok: list[tuple] = []
    jo, hibak, bukas = [], [], {"kotott": 0, "igaz": 0, "atomi": 0, "egyertelmu": 0}
    for i, k in enumerate(kartyak):
        kapu, t = _kartya_kapuk(f, k, elozok)
        if all(kapu.values()):
            jo.append(t["szo"])
        else:
            rossz = [n for n, v in kapu.items() if not v]
            for n in rossz:
                bukas[n] += 1
            hibak.append({"kartya": i + 1, "kapu": rossz})
    n = len(kartyak)
    resz = {"minoseg": len(jo) / n if n else 0.0,
            "lefedettseg": A.atlag(any(t and _er(j, t) for j in jo) for t in tenyek)}
    return {"pont": sum(SULY_KARTYA[k] * v for k, v in resz.items()), **resz, "kartyak": n, "bukas": bukas, "hibak": hibak}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): kinyerhető-e a válaszból a kért JSON-lista legalább egy eleme."""
    kulcs = "allitas" if (vart or {}).get("fajta") == "ossz" else "kerdes"
    return bool(kimenet.lista_kinyer(valasz, (kulcs,)))


def pontoz(rekordok) -> dict:
    ossz, kartya, reszletek = [], [], []
    for r in rekordok:
        v = r["vart"]
        e = (pontoz_ossz if v["fajta"] == "ossz" else pontoz_kartya)(v["jegyzet"], r.get("valasz"))
        (ossz if v["fajta"] == "ossz" else kartya).append(e)
        reszletek.append({"id": r["id"], **{k: (round(x, 3) if isinstance(x, float) else x) for k, x in e.items()}})

    def atl(lista, kulcs):
        return round(A.atlag(x[kulcs] for x in lista), 4)
    o = {k: atl(ossz, k) for k in ("pont", "huseg", "alatamasztas", "lefedettseg")} if ossz else None
    k = {k: atl(kartya, k) for k in ("pont", "minoseg", "lefedettseg")} if kartya else None
    reszek = [x["pont"] for x in (o, k) if x]
    return {"pontszam": round(A.atlag(reszek), 4), "osszefoglalas": o, "kartya": k, "reszletek": reszletek}


def epseg() -> list[str]:
    """Az arany hibái: nem található kulcsrész vagy forrásmondat (üres lista = rendben)."""
    hibak = []
    for j in ARANY["jegyzetek"]:
        f = forras(j["id"])
        for fajta, kulcs in (("kulcsreszek", "idezet"), ("tenyek", "forras")):
            for i, x in enumerate(j[fajta], 1):
                t = f.keres(x[kulcs], kuszob=0.97)
                if not t["talalt"]:
                    hibak.append(f"{j['id']} {fajta} {i}: nincs a forrásban ({t['hasonlosag']})")
    return hibak
