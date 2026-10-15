"""A mérés érvényességi kapuja (C18.1): levágott, hurkos, üres és hibás tételek egy értékelésben.

A pontszám csak akkor kalibrálható, ha a válaszok nagy része befejezett, nem hurkolt és nem hibás. Tételenként:

    levágott   `usage.completion_tokens >= max_tokens` (a rekord `keres_beallitas`-ából); usage nélkül a hossz
               alapján, `len / 1,5 >= max_tokens` (az 1,5 karakter/token a legkisebb feladat-medián, az OCR-é;
               az ilyen tétel a `levagott_becsult` listába is kerül)
    hurok      (a) több mint 20 nem üres sor, és a leggyakoribb sor aránya nagyobb 40%-nál (a felhasználó
               szabálya), vagy (b) farok-periódus: az utolsó 400 karakter egy legfeljebb 200 karakteres
               periódussal legalább 90%-ban egyezik (a farokban ismétlődő mondat, amelyet az (a) nem lát)
    üres       a `<think>` blokk nélkül üres szöveg, vagy üres lista
    hiba       a rekordnak `hiba` mezője van (a worker hibát adott)
    formátum   a feladat `formatum_ok(valasz, vart)` hamis — csak jelentés, nem kapu (a modell minősége)

Érvényes: `n > 0` és (levágott ∪ hurok ∪ üres ∪ hiba) / n ≤ küszöb (`[meres] ervenyes_kuszob`, 0,10).

A küszöb kalibrációja a 2026-10-03-i mérésen (a rossz tételek aránya): tiszta futás 0–2% (glm_ocr és
paddleocr_vl_16 ocr_keplet); ministral3_3b szoveg 15% (hosszú, de nem hurkos kártyalisták); glm_ocr ocr_kezi
20%; qwen3_vl_4b fuzet_fejezet 35%; qwen35_2b szoveg 48%; qwen3_vl_4b ocr_kezi 81%; phi4_mini_reasoning
matek_ellenorzo 100% (a `<think>`-ben levágva); paddleocr_vl_16 ocr_kezi 98% (több kép: hiba). A 10% a tiszta
futásokat engedi, minden mást — a ministral3_3b-t is — újramérésre küld (a felhasználó döntése, C18.1).
"""
from __future__ import annotations

import re
from collections import Counter

KAR_PER_TOKEN = 1.5
SOR_MIN, SOR_ARANY = 20, 0.4
FAROK, PERIODUS_MAX, PERIODUS_EGYEZES = 400, 200, 0.9

_GONDOLAT = re.compile(r"<think>.*?</think>", re.S)


def _tisztit(s: str) -> str:
    s = _GONDOLAT.sub("", s)
    return s.split("</think>")[-1].strip()


def sorhurok(s: str) -> bool:
    sorok = [x.strip() for x in s.splitlines() if x.strip()]
    return len(sorok) > SOR_MIN and Counter(sorok).most_common(1)[0][1] / len(sorok) > SOR_ARANY


def farok_periodus(s: str) -> int | None:
    """A válasz végének ismétlődési periódusa karakterben, vagy `None`."""
    t = s.rstrip()[-FAROK:]
    if len(t) < FAROK:
        return None
    for p in range(1, PERIODUS_MAX + 1):
        egyezik = sum(1 for i in range(p, len(t)) if t[i] == t[i - p])
        if egyezik / (len(t) - p) >= PERIODUS_EGYEZES:
            return p
    return None


def hurok(s) -> bool:
    return isinstance(s, str) and (sorhurok(s) or farok_periodus(s) is not None)


def levagott(r: dict, alap_max_tokens: int | None = None) -> tuple[bool, bool]:
    """(levágott, csak becsült-e). A `max_tokens` a rekordé; a C18.1 előtti sornál az `alap_max_tokens`."""
    v = r.get("valasz")
    mt = (r.get("keres_beallitas") or {}).get("max_tokens") or alap_max_tokens
    if not isinstance(v, str) or not mt:
        return False, False
    ct = (r.get("usage") or {}).get("completion_tokens")
    if ct is not None:
        return int(ct) >= int(mt), False
    return len(v) / KAR_PER_TOKEN >= int(mt), len(v) / KAR_PER_TOKEN >= int(mt)


def ures(v) -> bool:
    if isinstance(v, str):
        return not _tisztit(v)
    return v is None or (isinstance(v, (list, tuple)) and not v)


def vizsgal(rekordok: list[dict], kuszob: float, formatum_ok=None, max_tokens: dict | None = None) -> dict:
    """Az értékelés `ervenyesseg` mezője; `formatum_ok(valasz, vart) -> bool` a feladat opcionális próbája,
    `max_tokens`: id → keret azokhoz a (régi) sorokhoz, amelyekben nincs `keres_beallitas`."""
    idk = {k: [] for k in ("levagott", "hurok", "ures", "hiba", "formatum_hiba", "levagott_becsult")}
    rossz = set()
    for r in rekordok:
        i, v = r["id"], r.get("valasz")
        if r.get("hiba"):
            idk["hiba"].append(i)
            rossz.add(i)
            continue
        if ures(v):
            idk["ures"].append(i)
            rossz.add(i)
            continue
        lev, becsult = levagott(r, (max_tokens or {}).get(i))
        if lev:
            idk["levagott"].append(i)
            rossz.add(i)
            if becsult:
                idk["levagott_becsult"].append(i)
        if hurok(v):
            idk["hurok"].append(i)
            rossz.add(i)
        if formatum_ok is not None and not formatum_ok(v, r.get("vart")):
            idk["formatum_hiba"].append(i)
    n = len(rekordok)
    arany = lambda k: round(k / n, 4) if n else 0.0  # noqa: E731
    ki = {"n": n, "kuszob": kuszob, "rossz": len(rossz), "rossz_arany": arany(len(rossz)),
          "ervenyes": n > 0 and len(rossz) / n <= kuszob}
    for k, lista in idk.items():
        ki[k] = len(lista)
        ki[f"{k}_arany"] = arany(len(lista))
    if formatum_ok is None:
        ki["formatum_hiba"] = ki["formatum_hiba_arany"] = None
    ki["tetelek"] = {k: v for k, v in idk.items() if v}
    return ki


def osszegzes(e: dict) -> str:
    """Egy sor a futtató kimenetére."""
    fh = "–" if e.get("formatum_hiba") is None else e["formatum_hiba"]
    return (f"{'érvényes' if e['ervenyes'] else 'ÉRVÉNYTELEN'}: levágott {e['levagott']}/{e['n']}, hurok "
            f"{e['hurok']}/{e['n']}, üres {e['ures']}/{e['n']}, hiba {e['hiba']}/{e['n']}, formátumhiba {fh} "
            f"(rossz {e['rossz_arany']:.0%}, küszöb {e['kuszob']:.0%})")
