"""A fordító- és a futási kimenet elemzése (C36a): clang- és linker-hibák, sanitizer-jelentések, `assert`.

Tiszta függvények, a kimenet szövegéből dolgoznak (a minták a valódi eszközláncon mért kimenetek):
- `fordito`: a `fájl:sor:oszlop: error|warning|note: üzenet` sorok (az oszlop nélküli `fájl:sor: …` is; a `fatal error` az
  `error` szintet kapja `vegzetes: true` jelzővel), a hozzájuk tartozó forrás- és `^`-sorok (`kodreszlet`) és a linker
  (`ld64.lld: error: …` `>>>` részletekkel; a `linker = "rendszer"` konfigban az ld64 `Undefined symbols for architecture …` és a
  GNU ld `fájl:(.text+0x…): undefined reference to …` alakja; C36a2);
- `jelentes`: egy futás stderr-éből az ASan-, UBSan- vagy `assert`-jelentés (ASan > UBSan > assert);
- `szimbolizal`: az ASan nyers kereteinek (`modul:arm64+0x…`) a hely-feloldása az `llvm-symbolizer` kimenetéből — a program
  futtatása nélkül, a hívó (`ellenorzes`) futtatja a szimbolizálót a fordító profilja alatt.
Az UBSan és az `assert` a forrássort maga adja; az ASan-nál a szimbolizálás kell hozzá (`-g` fordítás: a driver dSYM-et készít).
"""
from __future__ import annotations

import os
import re

_DIAG = re.compile(r"^(?P<fajl>.+?):(?P<sor>\d+):(?P<oszlop>\d+): (?P<szint>fatal error|error|warning|note|remark): (?P<uzenet>.*)$")
_ESZKOZ = re.compile(r"^(?P<eszkoz>clang(?:\+\+)?(?:-\d+)?|ld64\.lld|ld\.lld|ld|lld): (?P<szint>fatal error|error|warning): (?P<uzenet>.*)$")
_RESZLET = re.compile(r"^>>> ?(?P<szoveg>.*)$")
_KAPCSOLO = re.compile(r"\s*\[(-W[\w+,-]+)\]\s*$")
_RESZLET_MAX = 4
_DIAG_OSZLOP_NELKUL = re.compile(r"^(?P<fajl>.+?):(?P<sor>\d+): (?P<szint>fatal error|error|warning|note|remark): (?P<uzenet>.*)$")
_KOD_SOR = re.compile(r"^\s*\d*\s*\|")                 # `   10 |     cout << y;` és `      |         ^~~`
_KOD_MAX = 6
_MACOS_UNDEF = re.compile(r"^Undefined symbols for architecture \S+:$")
_ELD = re.compile(r"^(?:\S*/)?ld(?:\.[\w-]+)?: (?P<uzenet>.*)$")
_GNU_LINKER = re.compile(r"^(?P<fajl>[^\s:][^:]*?):\([^)]*\): (?P<uzenet>(?:undefined|multiple) .*)$")

_ASAN = re.compile(r"==\d+==ERROR: AddressSanitizer: (?P<fajta>[\w-]+)")
_HOZZAFERES = re.compile(r"^(?P<h>(?:READ|WRITE) of size \d+)")
_KERET = re.compile(r"^\s+#(?P<i>\d+) 0x(?P<cim>[0-9a-fA-F]+)(?: in (?P<fv>[^\s+(]+)(?:\+0x[0-9a-fA-F]+)?)?\s+"
                    r"\((?P<modul>.+):(?P<arch>arm64e?|x86_64h?)\+0x(?P<off>[0-9a-fA-F]+)\)\s*$")
_UBSAN = re.compile(r"^(?P<fajl>.+?):(?P<sor>\d+):(?P<oszlop>\d+): runtime error: (?P<uzenet>.*)$")
_ASSERT = re.compile(r"^Assertion failed: \((?P<kif>.*)\), function (?P<fv>[^,]+), file (?P<fajl>.+), line (?P<sor>\d+)\.\s*$")
_HELY = re.compile(r"^(?P<fajl>.*):(?P<sor>\d+):(?P<oszlop>\d+)$")


def _sajat(fajl: str, forras_nev: str) -> bool:
    return fajl == forras_nev or os.path.basename(fajl) == forras_nev


# ---------------------------------------------------------------------- fordító

def _diag(szint: str, fajl: str | None, sor: int | None, oszlop: int | None, uzenet: str, kapcsolo: str | None, sajat: bool,
          vegzetes: bool = False) -> dict:
    return {"szint": szint, "fajl": fajl, "sor": sor, "oszlop": oszlop, "uzenet": uzenet, "kapcsolo": kapcsolo, "sajat": sajat,
            "vegzetes": vegzetes, "kodreszlet": [], "reszletek": []}


def fordito(szoveg: str, forras_nev: str, max_db: int = 100) -> dict:
    """A fordító és a linker kimenete → `{diagnosztika: [{szint, fajl, sor, oszlop, uzenet, kapcsolo, sajat, vegzetes, kodreszlet,
    reszletek}], hiba_db, figyelmeztetes_db, levagva}`. A `sajat` fájl neve a `forras_nev`; más fájl teljes útja marad. A `kodreszlet`
    a diagnosztika forrás- és `^`-sorai (legfeljebb 6), a `reszletek` a linker `>>>` és az ld64 hely-sorai. A számlálók a
    levágott elemeket is számolják."""
    lista: list[dict] = []
    hiba_db = figy_db = osszes_db = 0
    utolso: dict | None = None
    for sor in szoveg.splitlines():
        m = _DIAG.match(sor) or _DIAG_OSZLOP_NELKUL.match(sor)
        e = None
        if m:
            vegzetes = m["szint"] == "fatal error"
            szint = "error" if vegzetes else m["szint"]
            uzenet, kapcsolo = m["uzenet"].rstrip(), None
            k = _KAPCSOLO.search(uzenet)
            if k:
                uzenet, kapcsolo = uzenet[:k.start()], k.group(1)
            sajat = _sajat(m["fajl"], forras_nev)
            oszlop = m.groupdict().get("oszlop")
            e = _diag(szint, forras_nev if sajat else m["fajl"], int(m["sor"]), int(oszlop) if oszlop else None, uzenet, kapcsolo,
                      sajat, vegzetes)
        else:
            m = _ESZKOZ.match(sor)
            if m:
                e = _diag("error" if m["szint"] == "fatal error" else m["szint"], None, None, None, m["uzenet"].rstrip(), None,
                          False, m["szint"] == "fatal error")
            elif _MACOS_UNDEF.match(sor):
                e = _diag("error", None, None, None, sor.rstrip(":"), None, False)
            elif (g := _GNU_LINKER.match(sor)):
                sajat = _sajat(g["fajl"], forras_nev)
                e = _diag("error", forras_nev if sajat else g["fajl"], None, None, g["uzenet"].rstrip(), None, sajat)
            elif (l := _ELD.match(sor)) and not sor.startswith("/") and not re.search(r"in function [`'].*':$", l["uzenet"]):
                e = _diag("error", None, None, None, "ld: " + l["uzenet"].rstrip(), None, False)
            else:
                r = _RESZLET.match(sor)
                if r and utolso is not None and len(utolso["reszletek"]) < _RESZLET_MAX:
                    utolso["reszletek"].append(r["szoveg"].strip())
                elif utolso is not None and _KOD_SOR.match(sor):
                    if len(utolso["kodreszlet"]) < _KOD_MAX:
                        utolso["kodreszlet"].append(sor.rstrip())
                elif utolso is not None and utolso["fajl"] is None and sor.strip() and sor.startswith("  ") \
                        and len(utolso["reszletek"]) < _RESZLET_MAX:
                    utolso["reszletek"].append(sor.strip())    # az ld64 `"szimbólum", referenced from:` hely-sorai
                continue
        utolso = e
        osszes_db += 1
        if e["szint"] == "error":
            hiba_db += 1
        elif e["szint"] == "warning":
            figy_db += 1
        if len(lista) < max_db:
            lista.append(e)
        else:
            utolso = None
    return {"diagnosztika": lista, "hiba_db": hiba_db, "figyelmeztetes_db": figy_db, "levagva": osszes_db > max_db}


# ---------------------------------------------------------------------- futási jelentés

def _ures(forras: str, fajta: str, leiras: str) -> dict:
    return {"forras": forras, "fajta": fajta, "leiras": leiras, "hozzaferes": None, "fajl": None, "sor": None, "oszlop": None,
            "fuggveny": None, "sajat": False, "keretek": []}


def jelentes(stderr: str, forras_nev: str, bin_nev: str | None = None) -> dict | None:
    """Az első sanitizer- vagy `assert`-jelentés a stderr szövegéből; nincs → None."""
    sorok = stderr.splitlines()
    for i, sor in enumerate(sorok):
        m = _ASAN.search(sor)
        if not m:
            continue
        j = _ures("asan", m["fajta"], m["fajta"])
        keretek: list[dict] = []
        for kovetkezo in sorok[i + 1:]:
            h = _HOZZAFERES.match(kovetkezo)
            if h and not keretek and j["hozzaferes"] is None:
                j["hozzaferes"] = h["h"]
                j["leiras"] = f"{m['fajta']} ({h['h']})"
                continue
            k = _KERET.match(kovetkezo)
            if k:
                keretek.append({"index": int(k["i"]), "cim": "0x" + k["cim"], "modul": k["modul"], "arch": k["arch"],
                                "offset": int(k["off"], 16), "fuggveny": k["fv"], "fajl": None, "sor": None, "oszlop": None,
                                "sajat_modul": bool(bin_nev and os.path.basename(k["modul"]) == bin_nev)})
            elif keretek:
                break                                      # az első verem vége (üres sor vagy más szöveg)
        j["keretek"] = keretek
        return j
    for sor in sorok:
        m = _UBSAN.match(sor)
        if m:
            j = _ures("ubsan", "ub", m["uzenet"].strip())
            sajat = _sajat(m["fajl"], forras_nev)
            j.update(fajl=forras_nev if sajat else m["fajl"], sor=int(m["sor"]), oszlop=int(m["oszlop"]), sajat=sajat)
            return j
    for sor in sorok:
        m = _ASSERT.match(sor)
        if m:
            j = _ures("assert", "assert", m["kif"])
            sajat = _sajat(m["fajl"], forras_nev)
            j.update(fajl=forras_nev if sajat else m["fajl"], sor=int(m["sor"]), fuggveny=m["fv"].strip(), sajat=sajat)
            return j
    return None


# ---------------------------------------------------------------------- szimbolizálás

def szimbolizalando_cimek(j: dict) -> list[str]:
    """Az `llvm-symbolizer` bemenete: a sajáthoz tartozó keretek címei (a bináris saját fájl-offsetei), sorrendben."""
    return [hex(k["offset"]) for k in j.get("keretek", []) if k.get("sajat_modul")]


def _blokkok(szoveg: str) -> list[list[tuple[str, str | None, int | None, int | None]]]:
    """Az `llvm-symbolizer` kimenete címenként (üres sor választja el): [(függvény, fájl, sor, oszlop)] beágyazott keretenként."""
    ki, blokk, sorok = [], [], szoveg.splitlines()
    i = 0
    while i < len(sorok):
        if not sorok[i].strip():
            if blokk:
                ki.append(blokk)
                blokk = []
            i += 1
            continue
        fv = sorok[i].strip()
        hely = sorok[i + 1].strip() if i + 1 < len(sorok) else ""
        m = _HELY.match(hely)
        if m and m["fajl"] not in ("??", ""):
            blokk.append((fv, m["fajl"], int(m["sor"]), int(m["oszlop"])))
        else:
            blokk.append((fv, None, None, None))
        i += 2
    if blokk:
        ki.append(blokk)
    return ki


def szimbolizal(j: dict, forras_nev: str, szimbolizalo_kimenet: str) -> dict:
    """A jelentés keretei és az első saját fájlbeli hely kitöltése. Ismeretlen hely (`??:0:0`) nem rontja el a jelentést."""
    blokkok = _blokkok(szimbolizalo_kimenet)
    sajat_keretek = [k for k in j.get("keretek", []) if k.get("sajat_modul")]
    for keret, blokk in zip(sajat_keretek, blokkok):
        valasztott = next((b for b in blokk if b[1] and _sajat(b[1], forras_nev)), None) or (blokk[0] if blokk else None)
        if valasztott is None or valasztott[1] is None:
            continue
        fv, fajl, sor, oszlop = valasztott
        sajat = _sajat(fajl, forras_nev)
        keret.update(fuggveny=fv, fajl=forras_nev if sajat else fajl, sor=sor, oszlop=oszlop)
    for keret in sajat_keretek:
        if keret["fajl"] == forras_nev and keret["sor"]:
            j.update(fajl=forras_nev, sor=keret["sor"], oszlop=keret["oszlop"], fuggveny=keret["fuggveny"], sajat=True)
            break
    return j
