"""A várt és a kapott kimenet összevetése és a sorszintű diff (C36a; a `teszt` blokk szabálya, `core/cpp_teszt.py`).

Négy mód (C36a2; a blokk `--- osszevetes` szakasza; a `core/cpp_teszt.MODOK` az egyetlen névlista):
- `alap` (az alapértelmezés, a C36a viselkedése): a sorvég (`\\r\\n`, `\\r`) `\\n`-re normalizálódik, a sorok végi szóköz és tab, valamint a
  záró üres sorok nem számítanak; minden más (a sor eleji szóköz, a belső szóközök, a kis-nagybetű, a belső üres sorok) igen;
- `pontos`: azonos szöveg; csak a CRLF → LF és az egyetlen záró sorvég megléte nem számít (a blokk a záró sorvég hiányát
  nem tudja kifejezni);
- `tures`: soronként a szóközzel tagolt tokenek egyeznek (a vezető, a belső és a végi szóköz, a tab nem számít; a
  sorszerkezet és a záró üres sorok nem);
- `lebego eps`: tokenenként, a sorszerkezettől függetlenül; két számtoken egyezik, ha `|a−b| ≤ eps` vagy `|a−b| ≤ eps·|várt|`
  (a testlib mintája); a nem számtoken pontosan; a `nan` és az `inf` csak önmagával.
Ellenőrző program nincs (hatókör). Az `elteres` az első eltérés helyét és okát adja (sor, oszlop vagy token).

Diff: a sorok `difflib`-bel igazítva; az egyező hosszú szakaszok összecsukva (`kihagyva`), a sorok hossza és száma korlátos.
"""
from __future__ import annotations

import difflib
import math
import re
from itertools import zip_longest

_IGAZITAS_LIMIT = 4_000_000       # a két lista hosszának szorzata fölött az igazítás helyett sorról sorra vetünk össze (CPU-védelem)


def normal(szoveg: str) -> list[str]:
    sorok = [re.sub(r"[ \t]+$", "", s) for s in szoveg.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while sorok and not sorok[-1]:
        sorok.pop()
    return sorok


_SZAM = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$|^[+-]?(?:nan|inf|infinity)$", re.I)
ALAP_EPS = 1e-6


def _lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _pontos_sorok(s: str) -> list[str]:
    s = _lf(s)
    return (s[:-1] if s.endswith("\n") else s).split("\n")


def _tures_sorok(s: str) -> list[list[str]]:
    sorok = [x.split() for x in _lf(s).split("\n")]
    while sorok and not sorok[-1]:
        sorok.pop()
    return sorok


def szam_egyezik(vart: str, kapott: str, eps: float) -> bool:
    """Két token egyezése a `lebego` módban."""
    if not (_SZAM.match(vart) and _SZAM.match(kapott)):
        return vart == kapott
    a, b = float(kapott), float(vart)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    if math.isinf(a) or math.isinf(b):
        return a == b
    d = abs(a - b)
    return d <= eps or d <= eps * abs(b)


def _rovid(s: str | None, n: int = 200) -> str | None:
    return s if s is None or len(s) <= n else s[:n] + "…"


def _sor_elteres(v: list, k: list, mod: str, kulonbseg) -> dict | None:
    """Soronkénti összevetés közös magja: az első eltérő sor `{sor, oszlop|token, vart, kapott, ok}`; nincs → None."""
    for i in range(max(len(v), len(k))):
        a = v[i] if i < len(v) else None
        b = k[i] if i < len(k) else None
        if a == b:
            continue
        if a is None or b is None:
            szoveg = (lambda x: x) if mod in ("alap", "pontos") else " ".join
            return {"sor": i + 1, "oszlop": None, "vart": _rovid(szoveg(a)) if a is not None else None,
                    "kapott": _rovid(szoveg(b)) if b is not None else None,
                    "ok": "a kimenet hosszabb a vártnál" if a is None else "a kimenet rövidebb a vártnál"}
        return {"sor": i + 1, **kulonbseg(a, b)}
    return None


def _elso(a, b) -> int:
    return next((j for j in range(min(len(a), len(b))) if a[j] != b[j]), min(len(a), len(b)))


def elteres(vart: str, kapott: str, mod: str = "alap", eps: float | None = None) -> dict | None:
    """Az első eltérés `{sor, oszlop?, token?, vart, kapott, ok}` a megadott módban; egyezésnél None."""
    eps = ALAP_EPS if eps is None else eps
    if mod == "alap":
        return _sor_elteres(normal(vart), normal(kapott), mod,
                            lambda a, b: {"oszlop": _elso(a, b) + 1, "vart": _rovid(a), "kapott": _rovid(b), "ok": "a sor eltér"})
    if mod == "pontos":
        return _sor_elteres(_pontos_sorok(vart), _pontos_sorok(kapott), mod,
                            lambda a, b: {"oszlop": _elso(a, b) + 1, "vart": _rovid(a), "kapott": _rovid(b), "ok": "a sor eltér"})
    if mod == "tures":
        return _sor_elteres(_tures_sorok(vart), _tures_sorok(kapott), mod,
                            lambda a, b: {"token": _elso(a, b) + 1, "vart": _rovid(" ".join(a)), "kapott": _rovid(" ".join(b)),
                                          "ok": "a sor eltér"})
    if mod == "lebego":
        vt = [(n + 1, t) for n, sor in enumerate(_lf(vart).split("\n")) for t in sor.split()]
        kt = [(n + 1, t) for n, sor in enumerate(_lf(kapott).split("\n")) for t in sor.split()]
        for i in range(max(len(vt), len(kt))):
            a = vt[i] if i < len(vt) else None
            b = kt[i] if i < len(kt) else None
            if a is None or b is None or not szam_egyezik(a[1], b[1], eps):
                ok = ("a kimenet több tokent tartalmaz" if a is None else
                      "a kimenet kevesebb tokent tartalmaz" if b is None else
                      "a szám a tűrésen kívül esik" if _SZAM.match(a[1]) and _SZAM.match(b[1]) else "a token eltér")
                return {"sor": (b or a)[0], "token": i + 1, "vart": _rovid(a[1]) if a else None,
                        "kapott": _rovid(b[1]) if b else None, "ok": ok}
        return None
    raise ValueError(f"ismeretlen összevetési mód: {mod}")


def egyezik(vart: str, kapott: str, mod: str = "alap", eps: float | None = None) -> bool:
    if mod == "alap":
        return normal(vart) == normal(kapott)
    return elteres(vart, kapott, mod, eps) is None


def _vag(s: str | None, max_hossz: int) -> str | None:
    return s if s is None or len(s) <= max_hossz else s[:max_hossz] + "…"


def _sorok(v: list[str], k: list[str]) -> list[dict]:
    """Az összes sor tipizálva (összecsukás nélkül)."""
    sor = lambda t, i, j: {"tipus": t, "vart_sor": None if i is None else i + 1, "kapott_sor": None if j is None else j + 1,  # noqa: E731
                           "vart": None if i is None else v[i], "kapott": None if j is None else k[j]}
    ki: list[dict] = []
    if len(v) * len(k) > _IGAZITAS_LIMIT:
        for n, (a, b) in enumerate(zip_longest(v, k)):
            if a is not None and b is not None:
                ki.append(sor("egyenlo" if a == b else "csere", n, n))
            else:
                ki.append(sor("torolt", n, None) if b is None else sor("beszurt", None, n))
        return ki
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, v, k, autojunk=False).get_opcodes():
        if tag == "equal":
            ki += [sor("egyenlo", i1 + n, j1 + n) for n in range(i2 - i1)]
        elif tag == "delete":
            ki += [sor("torolt", i, None) for i in range(i1, i2)]
        elif tag == "insert":
            ki += [sor("beszurt", None, j) for j in range(j1, j2)]
        else:
            kozos = min(i2 - i1, j2 - j1)
            ki += [sor("csere", i1 + n, j1 + n) for n in range(kozos)]
            ki += [sor("torolt", i, None) for i in range(i1 + kozos, i2)]
            ki += [sor("beszurt", None, j) for j in range(j1 + kozos, j2)]
    return ki


def _osszecsuk(sorok: list[dict], kornyezet: int) -> list[dict]:
    """Az eltérés körül `kornyezet` egyező sor marad, a hosszabb egyező szakasz `kihagyva` sorrá zsugorodik."""
    ki: list[dict] = []
    n, i = len(sorok), 0
    while i < n:
        if sorok[i]["tipus"] != "egyenlo":
            ki.append(sorok[i])
            i += 1
            continue
        j = i
        while j < n and sorok[j]["tipus"] == "egyenlo":
            j += 1
        blokk = sorok[i:j]
        elso, utolso = i == 0, j == n
        elol, hatul = (0 if elso else kornyezet), (0 if utolso else kornyezet)
        if not elso and not utolso:
            elol = hatul = kornyezet
        elif elso:
            elol, hatul = 0, kornyezet
        else:
            elol, hatul = kornyezet, 0
        rejtett = len(blokk) - elol - hatul
        if rejtett <= 1:                                   # egyetlen sort nem érdemes elrejteni
            ki += blokk
        else:
            ki += blokk[:elol]
            ki.append({"tipus": "kihagyva", "db": rejtett, "vart_sor": blokk[elol]["vart_sor"],
                       "kapott_sor": blokk[elol]["kapott_sor"], "vart": None, "kapott": None})
            ki += blokk[len(blokk) - hatul:] if hatul else []
        i = j
    return ki


def diff(vart: str, kapott: str, *, max_sor: int = 200, max_hossz: int = 400, kornyezet: int = 2,
         mod: str = "alap", eps: float | None = None) -> dict:
    """→ `{egyezik, vart_sor_db, kapott_sor_db, elteres_db, elso_elteres, sorok, levagva, mod, elteres}`; a `sorok` egyező
    kimenetnél üres. A sorok igazítása a `normal` sorokon megy (a `tures` módban a tokenek egységes szóközzel), az `elteres` a
    mód szerinti első eltérés (a `lebego` módban a sorok csak tájékoztatnak: az egyezést a tűrés dönti el)."""
    v, k = (_pontos_sorok(vart), _pontos_sorok(kapott)) if mod == "pontos" else (normal(vart), normal(kapott))
    if mod == "tures":
        v, k = [" ".join(s.split()) for s in v], [" ".join(s.split()) for s in k]
    ered = {"egyezik": egyezik(vart, kapott, mod, eps), "vart_sor_db": len(v), "kapott_sor_db": len(k), "elteres_db": 0,
            "elso_elteres": None, "sorok": [], "levagva": False, "mod": mod, "elteres": None}
    if ered["egyezik"]:
        return ered
    ered["elteres"] = elteres(vart, kapott, mod, eps)
    osszes = _sorok(v, k)
    elter_sorok = [s for s in osszes if s["tipus"] != "egyenlo"]
    ered["elteres_db"] = len(elter_sorok)
    if elter_sorok:
        ered["elso_elteres"] = elter_sorok[0]["vart_sor"] or elter_sorok[0]["kapott_sor"]
    sorok = _osszecsuk(osszes, kornyezet)
    if len(sorok) > max_sor:
        sorok, ered["levagva"] = sorok[:max_sor], True
    for s in sorok:
        s["vart"], s["kapott"] = _vag(s["vart"], max_hossz), _vag(s["kapott"], max_hossz)
    ered["sorok"] = sorok
    return ered
