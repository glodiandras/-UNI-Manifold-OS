"""A médiatársítás döntései (C20b) — a legacy `media_itelet.py` (a nyelvi modell két ítélete) és `media.py` nyelvi szabályai, a D1
szerint átírva: **nincs „kérdezz rá”**, minden tétel végállapotba kerül.

A prompt-szövegek (`TEMA_PROMPT_TARTALOM`, `TEMA_PROMPT_METAADAT`, `KOTES_PROMPT`) a legacy `calibration.json → media.itelet` értékei
betűre; a mérés (`modulok/eval/tema`, `modulok/eval/kotes`) ugyanezeket a függvényeket hívja, így a kalibráció az éles kérésre szól.

    nyelv:   norm_lang, felirat_valasztas (pick_sub_langs), nyelv_dontes (decide_language)
    téma:    temalista, tema_promptok, sorszam, tema_dontes (az erős sáv), tema_vegso (D1: a végső döntés és a biztossága)
    kötés:   kotes_prompt, igen_nem, kotes_dontes (a modell-sáv), kotes_indok
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from . import egyezes as X
from .szovegreteg import nfc, norm_word, words

TEMA_PROMPT_TARTALOM = ("Egy magyar oktatóvideó gépi átirata következik (az átirat hibás lehet).\n\nÁTIRAT:\n{atirat}\n\nAz alábbi tankönyvi "
                        "témák közül melyiknek a FŐ TÉMÁJÁT dolgozza fel ez a videó? A kettőspont után a téma jegyzeteinek címe áll.\n"
                        "{temak}\n\nCsak az egy legjobban illő téma sorszámát add meg, vagy írd: egyik sem.")
TEMA_PROMPT_METAADAT = ("Egy magyar oktatóvideó adatai következnek.\nCÍM: {cim}\n{utvonal}\nAz alábbi tankönyvi témák közül melyikbe "
                        "tartozik ez a videó? A kettőspont után a téma jegyzeteinek címe áll.\n{temak}\n\nCsak az egy legjobban illő téma "
                        "sorszámát add meg, vagy írd: egyik sem.")
KOTES_PROMPT = ("Egy magyar oktatóvideó feliratának egy részlete (gépi átirat, hibás lehet) és egy tankönyvi jegyzet részlete következik."
                "\n\nVIDEÓRÉSZLET:\n{ablak}\n\nJEGYZET: {cim}\n{reszlet}\n\nKérdés: a videórészlet ténylegesen ELMAGYARÁZZA-e azt, amiről "
                "a jegyzet szól, vagy csak futólag megemlíti a jegyzet egy fogalmát, esetleg másról szól? Válaszolj egyetlen szóval: igen, "
                "ha elmagyarázza; nem, ha csak említi vagy másról szól.")
TEMA_MAX_TOKEN, KOTES_MAX_TOKEN = 24, 8
ATIRAT_MAX_KARAKTER, TEMA_TARTALOM_MAX_KARAKTER, KOTES_ABLAK_MAX_KARAKTER, KOTES_RESZLET_MAX_KARAKTER = 3500, 220, 1400, 900
TEMA_SAV = {"lex_rang_max": 10, "kalibralt_targyak": ["I", "N"]}          # media.itelet.tema_sav (mérve 2026-09-20: 84/84)
KOTES_SAV = {"bekapcsolva": True, "p_min": 0.75, "csak_sajat_tema": True, "kalibralt_targyak": ["T", "N"],   # a gemma-sáv (2026-09-23)
             "p_min_targy": {"T": 0.75, "N": 0.90}}
NYELV_P_MIN = 0.8


# ------------------------------------------------------------------ nyelv (a legacy media.py)

_NYELV_ALIAS = {"iw": "he", "jw": "jv", "in": "id"}


def norm_lang(kod) -> str | None:
    k = str(kod or "").strip().lower().replace("_", "-").split("-")[0]
    return _NYELV_ALIAS.get(k, k) or None


def felirat_valasztas(meta: dict, nyelv: str | None = None) -> tuple[str | None, str, bool]:
    """A kiadói felirat kulcsa (csak kézi sáv, az eredeti nyelven; az automatikus feliratot soha). → (kulcs | None, indok, kézi-e)."""
    orig = norm_lang(nyelv) or norm_lang(meta.get("language"))
    if not orig:
        return None, "ismeretlen eredeti nyelv — a kiadói felirat nem választható", False
    for k in sorted(meta.get("subtitles") or {}):
        if k != "live_chat" and norm_lang(k) == orig:
            return k, f"kiadói felirat ({k})", True
    return None, f"nincs kézi kiadói felirat az eredeti nyelven ({orig})", False


def nyelv_dontes(meta_nyelv, det: dict | None) -> dict:
    """A hang nyelve dönt (`det`: `{nyelv, szavazat, egyhangu, p_min}`); bizonytalan felismerés → `blokkol` (a lánc ilyenkor a tételt
    a végállapotba teszi, nem kérdez: D1)."""
    m = norm_lang(meta_nyelv)
    if not det or not det.get("nyelv") or not det.get("egyhangu") or (det.get("p_min") or 0) < NYELV_P_MIN:
        return {"nyelv": None, "forras": "a hang nyelve nem állapítható meg biztosan", "kod": "bizonytalan", "blokkol": True,
                "jelzes": False}
    h = norm_lang(det["nyelv"])
    if m and m == h:
        return {"nyelv": h, "forras": f"a metaadat és a hang egyezik ({h})", "kod": "metaadat+hang", "blokkol": False, "jelzes": False}
    if not m:
        return {"nyelv": h, "forras": f"a hangból ({h}); metaadat nincs", "kod": "hang", "blokkol": False, "jelzes": False}
    return {"nyelv": h, "forras": f"a hang ({h}) eltér a metaadattól ({m}) — a hang dönt", "kod": f"hang-metaadat-elter-{m}",
            "blokkol": False, "jelzes": True}


# ------------------------------------------------------------------ a téma

def sorszam(valasz, n: int) -> int | None:
    v = (valasz or "").strip()
    if re.search(r"egyik\s*sem", v, re.I):
        return None
    for x in re.findall(r"\b(\d{1,3})\b", v):
        if 1 <= int(x) <= n:
            return int(x)
    return None


def igen_nem(valasz) -> bool | None:
    v = re.sub(r"^[\W_]+", "", (valasz or "").strip().lower())
    if v.startswith("igen"):
        return True
    if v.startswith("nem"):
        return False
    return None


def utvonal(lap) -> str:
    u = urlparse(lap or "")
    host = u.netloc.lower()
    if not host or "youtube." in host or host.endswith("youtu.be"):
        return ""
    return " / ".join(p for p in u.path.split("/") if p)


def rovid(s, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return (cut or s[:n]).rstrip(" ;,") + " …"


def temak_targyban(idx: X.NoteIndex, targy: str | None) -> list[str]:
    return [t for t in idx.topics if not targy or X.targy(t) == targy]


_NEVELO = re.compile(r"^(?:A|Az)\s+", re.I)


def tomorit(nev: str, cimek: list[str]) -> str:
    kizart = {x for x in (norm_word(w) for w in words(nfc(nev))) if len(x) >= 3}
    out: list[str] = []
    for c in cimek:
        szavak = [w for w in _NEVELO.sub("", nfc(c)).split(" ") if w]
        s = " ".join(w for w in szavak if norm_word(w) not in kizart).strip(" –-—,;")
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return "; ".join(out)


def temalista(temak: list[str], idx: X.NoteIndex) -> str:
    sorok = []
    for i, t in enumerate(temak, 1):
        nev = re.sub(r"^[A-Z]+\d\d - ", "", nfc(t))
        cimek = [idx.notes[rp]["cim"] for rp in sorted(idx.by_topic.get(t, [])) if "Feladattár" not in idx.notes[rp]["cim"]]
        tartalom = rovid(tomorit(nev, cimek), TEMA_TARTALOM_MAX_KARAKTER)
        sorok.append(f"{i}. {nev}: {tartalom}" if tartalom else f"{i}. {nev}")
    return "\n".join(sorok)


def lista_hash(temak: list[str]) -> str:
    return hashlib.sha1("\n".join(nfc(t) for t in temak).encode("utf-8")).hexdigest()[:10]


def tema_promptok(atirat: str, cim: str | None, lap: str | None, lista: str) -> tuple[str | None, str]:
    """(az átiratból kérdező prompt | None, ha nincs átirat; a címből + a kiadó útvonalából kérdező prompt)."""
    a = rovid(atirat, ATIRAT_MAX_KARAKTER)
    ut = utvonal(lap)
    pa = TEMA_PROMPT_TARTALOM.format(atirat=a, temak=lista) if a else None
    pb = TEMA_PROMPT_METAADAT.format(cim=cim or "—", utvonal=(f"A KIADÓ BESOROLÁSA (a weblap útvonala): {ut}\n" if ut else ""),
                                     temak=lista)
    return pa, pb


def tema_dontes(it: dict, rang, cim_tema: str | None = None) -> dict:
    """Az erős sáv: a két ítélet (átiratból; címből) UGYANAZT adja, és a lexikai jel nem mond ellent (top-10, vagy a cím megnevezi)."""
    kmax = TEMA_SAV["lex_rang_max"]
    A, B = it.get("tartalom"), it.get("metaadat")
    lr = {t: i + 1 for i, (t, _) in enumerate(rang)}
    okok = []
    if not A or not B:
        okok.append("a modell " + ("egyik ítéletet sem adta" if not (A or B) else "csak az egyik bemenetből választott")
                    + " („egyik sem” vagy értelmezhetetlen)")
    elif A != B:
        okok.append(f"a modell két ítélete eltér: átiratból {A}, címből {B}")
    lex_ok = bool(A) and (lr.get(A, 10 ** 6) <= kmax or bool(cim_tema and cim_tema == A))
    if A and A == B and not lex_ok:
        okok.append(f"a lexikai jel ellentmond: {A} lexikai rangja {lr.get(A, '—')} > {kmax}"
                    + (f", a cím mást nevez meg ({cim_tema})" if cim_tema else ""))
    auto = bool(A) and A == B and lex_ok
    javaslat = list(dict.fromkeys([x for x in (A, B) if x] + [t for t, _ in rang[:3]]))
    return {"auto": auto, "tema": A if auto else None, "A": A, "B": B, "okok": okok, "javaslat": javaslat,
            "lex_rang": lr.get(A) if A else None,
            "jel": (f"a modell az átiratból és a címből is {A}-t adta; lexikai rang {lr.get(A, '—')}"
                    + (", a cím is megnevezi" if cim_tema == A else "")) if auto else None}


def tema_vegso(cls: dict, d: dict | None, targy: str | None) -> dict:
    """D1: a végső téma és a biztossága — nincs „kérdezz rá”, nincs várakozó állapot.

    `biztos`: a lexikai besorolás automatikus (a legacy négy jele), vagy a modell erős sávja egy mért tárgyban (`TEMA_SAV`);
    `valoszinu`: a modell két ítélete egyezik (de a lexikai kapu vagy a tárgy nem mért), vagy a cím megnevezi a témát;
    `bizonytalan`: a kronológiával kombinált, különben a lexikai első. A bizonytalan tétel is beíródik és visszavonható (D1).
    Nincs jelölt: `tema: None` (a tétel végállapota „nincs téma”)."""
    if cls.get("auto") and cls.get("tema"):
        return {"tema": cls["tema"], "forras": "lexikai", "biztossag": "biztos", "jel": cls.get("auto_jel")}
    if d and d.get("auto") and targy in set(TEMA_SAV["kalibralt_targyak"]):
        return {"tema": d["tema"], "forras": "modell", "biztossag": "biztos", "jel": d.get("jel")}
    if d and d.get("A") and d.get("A") == d.get("B"):
        return {"tema": d["A"], "forras": "modell", "biztossag": "valoszinu", "jel": "; ".join(d.get("okok") or [])}
    cj = cls.get("cim_tema")
    if cj:
        return {"tema": cj, "forras": "cím", "biztossag": "valoszinu", "jel": f"a cím megnevezi: {cj}"}
    kombinalt = (cls.get("kronologia") or {}).get("kombinalt")
    if kombinalt:
        return {"tema": kombinalt, "forras": "lexikai+kronológia", "biztossag": "bizonytalan", "jel": "; ".join(cls.get("okok") or [])}
    top = cls.get("top3") or []
    if top:
        return {"tema": top[0]["tema"], "forras": "lexikai", "biztossag": "bizonytalan", "jel": "; ".join(cls.get("okok") or [])}
    if d and d.get("javaslat"):
        return {"tema": d["javaslat"][0], "forras": "modell", "biztossag": "bizonytalan", "jel": "; ".join(d.get("okok") or [])}
    return {"tema": None, "forras": None, "biztossag": None, "jel": "; ".join(cls.get("okok") or []) or "nincs jelölt téma"}


# ------------------------------------------------------------------ a kötés

def kotes_prompt(ablak: str, cim: str | None, reszlet: str) -> str:
    return KOTES_PROMPT.format(ablak=rovid(ablak, KOTES_ABLAK_MAX_KARAKTER), cim=cim or "—",
                               reszlet=rovid(reszlet, KOTES_RESZLET_MAX_KARAKTER))


def kotes_dontes(p: float, sajat_tema: bool, targy: str | None, igen: bool | None) -> bool:
    """A kötési javaslat elfogadása a modell olvasása után: a modell „igen”, a tárgy mért, saját téma, és p a tárgy sávjában."""
    S = KOTES_SAV
    if not S["bekapcsolva"] or igen is not True:
        return False
    if targy not in set(S["kalibralt_targyak"]):
        return False
    if S["csak_sajat_tema"] and not sajat_tema:
        return False
    return p >= S["p_min_targy"].get(targy, S["p_min"])


def kotes_indok(c: dict) -> str:
    b = c.get("bizonyitek") or {}
    ev = ", ".join(str(y) for y in b.get("evszam_kozos", []))
    return (f"a modell elolvasta a(z) {c.get('t')} s körüli felirat-ablakot és a jegyzet legközelebbi bekezdését, és igennel "
            f"válaszolt (elmagyarázza, nem csak említi); media_link p={c.get('p')}"
            + ("; közös ritka szótövek: " + ", ".join(b.get("ritka_kozos", [])[:6]) if b.get("ritka_kozos") else "")
            + (f"; közös évszám: {ev}" if ev else ""))
