"""Szövegtávolság: Levenshtein, CER, WER, írásjel-F1, és a magyar szöveg normalizálása."""
from __future__ import annotations

import re
import unicodedata

_HAJT = str.maketrans("áéíóöőúüűÁÉÍÓÖŐÚÜŰ", "aeiooouuuAEIOOOUUU")
_SZO = re.compile(r"[0-9A-Za-zÀ-ɏ]+", re.UNICODE)
_IRASJEL = ".,;:!?"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def hajt(s: str) -> str:
    """Kisbetű, ékezet nélkül (a keresés hajtásával azonos elv)."""
    return nfc(s).translate(_HAJT).lower()


def szavak(s: str) -> list[str]:
    """A szöveg szavai kisbetűvel, írásjel nélkül (az ékezet megmarad)."""
    return [m.group(0).lower() for m in _SZO.finditer(nfc(s))]


def tovek(s: str, n: int = 5, min_hossz: int = 3) -> set[str]:
    """Hajtott szóelők: a ragozott alakok közelítő összevonása (a magyar toldalékolás miatt)."""
    return {w[:n] for w in (hajt(x) for x in szavak(s)) if len(w) >= min_hossz}


def levenshtein(a, b) -> int:
    """Szerkesztési távolság két sorozat (szöveg vagy lista) között."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    elozo = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        sor = [i]
        for j, y in enumerate(b, 1):
            sor.append(min(elozo[j] + 1, sor[j - 1] + 1, elozo[j - 1] + (x != y)))
        elozo = sor
    return elozo[-1]


def illesztes(a: list, b: list) -> list[tuple[str, int, int, int, int]]:
    """Legkisebb költségű illesztés műveletei: (`egyezik`|`csere`|`torol`|`beszur`, a0, a1, b0, b1) szakaszok."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ai, di, de = a[i - 1], d[i], d[i - 1]
        for j in range(1, m + 1):
            di[j] = min(de[j] + 1, di[j - 1] + 1, de[j - 1] + (ai != b[j - 1]))
    lepesek = []
    i, j = n, m
    while i or j:
        if i and j and a[i - 1] == b[j - 1] and d[i][j] == d[i - 1][j - 1]:
            lepesek.append(("egyezik", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and j and d[i][j] == d[i - 1][j - 1] + 1:
            lepesek.append(("csere", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            lepesek.append(("torol", i - 1, j))
            i -= 1
        else:
            lepesek.append(("beszur", i, j - 1))
            j -= 1
    lepesek.reverse()
    ki: list[list] = []
    for muv, x, y in lepesek:
        a1 = x + (muv != "beszur")
        b1 = y + (muv != "torol")
        if ki and ki[-1][0] == muv:
            ki[-1][2], ki[-1][4] = a1, b1
        else:
            ki.append([muv, x, a1, y, b1])
    return [tuple(s) for s in ki]


def wer(vart: str, kapott: str) -> float:
    """Szóhiba-arány kisbetűs, írásjel nélküli szövegen (a várt szöveg szószámára vetítve)."""
    v, k = szavak(vart), szavak(kapott)
    return levenshtein(v, k) / len(v) if v else float(bool(k))


def cer(vart: str, kapott: str) -> float:
    """Karakterhiba-arány normalizált szövegen. Hosszú szövegnél a szóillesztés eltérő szakaszain számol,
    így a futásidő a szószámmal, nem a karakterszámmal négyzetes."""
    v, k = szavak(vart), szavak(kapott)
    osszes = len(" ".join(v))
    if not osszes:
        return float(bool(k))
    if len(v) * len(k) <= 250_000 and osszes <= 600:
        return levenshtein(" ".join(v), " ".join(k)) / osszes
    hiba, elozo = 0, None
    for muv, a0, a1, b0, b1 in illesztes(v, k) + [("vege", 0, 0, 0, 0)]:
        if muv == "egyezik" or muv == "vege":
            if elozo:
                a, b = v[elozo[0]:elozo[1]], k[elozo[2]:elozo[3]]          # a szóköz a szakasz része
                hiba += levenshtein(" ".join(a) + " " * bool(a), " ".join(b) + " " * bool(b))
                elozo = None
        elif elozo:
            elozo = (elozo[0], max(a1, elozo[1]), elozo[2], max(b1, elozo[3]))
        else:
            elozo = (a0, a1, b0, b1)
    return hiba / osszes


def _irasjelek(s: str) -> list[tuple[str, str]]:
    """(szó, az utána álló írásjel vagy „”) párok."""
    ki = []
    szoveg = nfc(s)
    for m in _SZO.finditer(szoveg):
        utana = szoveg[m.end():m.end() + 1]
        ki.append((m.group(0).lower(), utana if utana in _IRASJEL and utana else ""))
    return ki


def irasjel_f1(vart: str, kapott: str) -> float:
    """Az írásjelek F1-e az egyező szavak után (mondatvégi jel és vessző külön számít)."""
    v, k = _irasjelek(vart), _irasjelek(kapott)
    tp = fp = fn = 0
    for muv, a0, a1, b0, b1 in illesztes([w for w, _ in v], [w for w, _ in k]):
        if muv == "egyezik":
            for x in range(a1 - a0):
                jv, jk = v[a0 + x][1], k[b0 + x][1]
                if jv and jv == jk:
                    tp += 1
                else:
                    fn += bool(jv)
                    fp += bool(jk)
        else:
            fn += sum(1 for w in v[a0:a1] if w[1])
            fp += sum(1 for w in k[b0:b1] if w[1])
    if not tp:
        return 0.0 if (fp or fn) else 1.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return 2 * p * r / (p + r)


def hasonlosag(a: str, b: str) -> float:
    """1 − távolság / a hosszabb hossza (két rövid szövegre, pl. képletre)."""
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))
