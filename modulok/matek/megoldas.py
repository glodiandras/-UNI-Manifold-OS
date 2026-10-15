"""Megoldás modellel (C24b; TERV 5.6 1., 3. pont; docs/C24-TERV.md 5. fejezet).

A modell számozott lépéseket és egy SymPy-kódblokkot ír; a kód a **CAS-homokozóban** fut (46. döntés), a lépések képletei a C24a
levezetés-ellenőrzőjén mennek át (`matek.levezetes`), a végeredmény LaTeX-alakja és a második véleménnyel való egyezése a homokozó
`matek.eredmeny` műveletéből jön. A modul tiszta: a modellt két hívható mögött éri el (`hivo`: kérés → worker-válasz), a vaultba nem ír;
a callout szövegét és a jegyzet új szövegét adja, a gépi írás a hívóé (`__main__.py megoldas`).

**A prompt egyetlen helye** a `PROMPT`/`keres`: ugyanezt méri a `matek_cas` eval (a mérés és az éles út kérése azonos).

„CAS-ellenőrzött” = a kód a homokozóban hibátlanul futott, az eredménye értelmezhető, és a lépések egyik átmenete sem `hiba`.
"""
from __future__ import annotations

import re

VALTOZO = "EREDMENY"
MAX_TOKENS = 3000                 # K99 (2026-10-08): 2000-en 5/40 levágva (12,5% > 10%, érvénytelen sor) — az újramérés ezzel fut (K280)
MAX_LEPES = 12
MAX_FELADAT = 4000
CALLOUT_FEJ = "> [!solution]"
JEL = {"ok": "✓", "hiba": "✗", "nem": "–"}
ERTELMEZHETO = ("halmaz", "intervallum", "par", "kifejezes", "logikai")
UZENET_EGYEB = "a kód eredménye nem halmaz, intervallum, szótár, kifejezés vagy logikai érték"

PROMPT = (
    "Oldd meg az alábbi matematikafeladatot.\n\n"
    "1. Először írd le a megoldás menetét 2–6 számozott lépésben. Minden lépés egyetlen sor: egy rövid magyar mondat a "
    "ténylegesen elvégzett átalakításról, és ha van, a sor végén a lépés utáni egyenlet vagy kifejezés egyetlen $…$ "
    "között (pl. $2x=4$). Lépést ne ismételj.\n"
    "2. Utána egyetlen ```python``` kódblokk következzen, amely SymPy-jal kiszámítja a végeredményt. A kód így "
    "kezdődjön:\nimport sympy as sp\nx = sp.Symbol('x', real=True)\n"
    "Szabályok a kódhoz:\n"
    "- Minden SymPy-nevet `sp.` előtaggal írj (pl. sp.solveset(kifejezés, x, domain=sp.S.Reals), sp.sqrt, sp.log, "
    "sp.Rational, sp.FiniteSet, sp.Interval).\n"
    "- Pontos értékekkel számolj (sp.Rational, sp.sqrt, sp.pi): lebegőpontos számot, float()-ot és a math modult ne "
    "használj. Csak a sympy modult importáld; fájlt és hálózatot ne használj.\n"
    "- A kód utolsó sora: {valtozo} = <a végeredmény>, pontosan ezzel a nagybetűs névvel.\n"
    "- A végeredmény alakja: egyenletnél a valós megoldások halmaza (sp.FiniteSet; ha nincs megoldás: sp.S.EmptySet); "
    "egyenlőtlenségnél a megoldáshalmaz sp.Interval vagy sp.Union alakban; ha több ismeretlen értékét (pl. egy "
    "metszéspont koordinátáit vagy egy sorozat adatait) kérdezik, szótár az ismeretlenekkel (pl. {{x: 4, y: 1}}); egy "
    "szám vagy kifejezés kiszámításánál egyetlen sympy kifejezés.\n"
    "- Valós számok halmazán dolgozz, és a hamis gyököket szűrd ki (behelyettesítéssel az eredeti egyenletbe, "
    "sp.simplify-jal).\n\nFELADAT:\n{szoveg}")


def keres(feladat_szoveg: str) -> dict:
    """A worker chat-kérése (a mérés és az éles út közös kérése)."""
    return {"messages": [{"role": "user", "content": PROMPT.format(valtozo=VALTOZO, szoveg=feladat_szoveg.strip())}],
            "max_tokens": MAX_TOKENS}


_BLOKK = re.compile(r"```[ \t]*(?:python|py|python3)?[ \t]*\n(.*?)```", re.S | re.I)
_LEPES = re.compile(r"^\s*(?:\*\*)?(\d{1,2})[.)](?:\*\*)?\s+(.+?)\s*$")
_KEPLET = re.compile(r"\$\$?([^$]+?)\$\$?")


def valasz_szoveg(valasz) -> str:
    """A worker-válasz (dict) vagy a nyers szöveg → a modell szövege, a gondolkodó modellek `<think>` része nélkül."""
    if isinstance(valasz, dict):
        try:
            valasz = valasz["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            valasz = ""
    s = str(valasz or "")
    return re.sub(r"<think>.*?</think>", "", s, flags=re.S).strip()


def kodblokk(valasz) -> str | None:
    """A válasz utolsó Python-kódblokkja; None, ha nincs."""
    talalat = _BLOKK.findall(valasz_szoveg(valasz))
    return talalat[-1].strip() if talalat and talalat[-1].strip() else None


def lepesek(valasz) -> list[dict]:
    """A kódblokk előtti számozott lépések → `[{szoveg, keplet}]` (a képlet a sor utolsó `$…$` része, ha van)."""
    s = valasz_szoveg(valasz)
    s = s.split("```", 1)[0]
    ki = []
    for sor in s.splitlines():
        m = _LEPES.match(sor)
        if not m:
            continue
        szoveg = m.group(2).replace("==", "=").strip()
        kepletek = _KEPLET.findall(szoveg)
        ki.append({"szoveg": szoveg, "keplet": kepletek[-1].strip() if kepletek else None})
        if len(ki) >= MAX_LEPES:
            break
    return ki


# ------------------------------------------------------------------ CAS-ellenőrzés

def ellenoriz(valasz, homokozo, *, lepes_idokorlat_s: float | None = None) -> dict:
    """Egy modell-válasz CAS-ellenőrzése: a kód futtatása és a lépések levezetés-ellenőrzése, egy homokozó-kötegben."""
    kod = kodblokk(valasz)
    lp = lepesek(valasz)
    kepletek = [(i, l["keplet"]) for i, l in enumerate(lp) if l["keplet"]]
    lepes = float(lepes_idokorlat_s or homokozo.beall["lepes_idokorlat_s"])
    feladatok = []
    if kod:
        feladatok.append({"muvelet": "kod", "kod": kod, "valtozo": VALTOZO})
    if len(kepletek) >= 2:
        feladatok.append({"muvelet": "hivas", "nev": "matek.levezetes",
                          "args": {"sorok": [k for _, k in kepletek], "lepes_idokorlat_s": lepes}})
    eredmenyek = homokozo.futtat(feladatok) if feladatok else []
    ki = {"kod": {"allapot": "nincs_kod", "uzenet": "a válaszban nincs Python-kódblokk"}, "ertek": None,
          "lepesek": [{**l, "jel": None} for l in lp], "levezetes": None}
    if kod:
        e = eredmenyek.pop(0)
        ki["kod"] = {"allapot": e["allapot"], "uzenet": str(e.get("uzenet") or "")[:300]}
        if e["allapot"] == "ok":
            ki["ertek"] = e["ertek"]
    if len(kepletek) >= 2:
        e = eredmenyek.pop(0)
        lv = e["ertek"] if e["allapot"] == "ok" and isinstance(e["ertek"], dict) else {
            "allapot": "nem_ellenorizheto", "elso_hiba": None, "atmenetek": []}
        ki["levezetes"] = {"allapot": lv.get("allapot"), "elso_hiba": lv.get("elso_hiba")}
        for a in lv.get("atmenetek") or []:
            hova = a.get("hova")
            if not isinstance(hova, int) or not 1 <= hova <= len(kepletek):
                continue
            i = kepletek[hova - 1][0]
            it = a.get("itelet")
            ki["lepesek"][i]["jel"] = ("hiba" if it == "hiba" else "ok" if it in ("ekvivalens", "szures", "bovulo")
                                       else "nem")
        h = lv.get("elso_hiba")
        if isinstance(h, dict) and isinstance(h.get("sor"), int) and 1 <= h["sor"] <= len(kepletek):
            ki["lepesek"][kepletek[h["sor"] - 1][0]]["jel"] = "hiba"
    hibas_lepes = any(l["jel"] == "hiba" for l in ki["lepesek"])
    tipus = (ki["ertek"] or {}).get("tipus") if isinstance(ki["ertek"], dict) else None
    if ki["kod"]["allapot"] != "ok":
        ok = f"a kód nem futott le a homokozóban ({ki['kod']['allapot']}: {ki['kod']['uzenet']})".strip()
    elif tipus not in ERTELMEZHETO:
        ok = UZENET_EGYEB
    elif hibas_lepes:
        ok = "a CAS hibát talált a lépések között"
    else:
        ok = None
    ki["ellenorzott"] = ok is None
    ki["ok"] = ok
    return ki


def osszevet(elso: dict, masodik: dict | None, homokozo) -> dict:
    """A két eredmény LaTeX-alakja és egyezése (a homokozó `matek.eredmeny` műveletével)."""
    if elso.get("ertek") is None and (masodik is None or masodik.get("ertek") is None):
        return {"latex_a": None, "latex_b": None, "egyezik": None}
    a = elso.get("ertek") or {"tipus": "egyeb"}
    b = None if masodik is None else (masodik.get("ertek") or {"tipus": "egyeb"})
    e = homokozo.egy({"muvelet": "hivas", "nev": "matek.eredmeny", "args": {"a": a, "b": b}})
    if e["allapot"] != "ok" or not isinstance(e["ertek"], dict):
        return {"latex_a": None, "latex_b": None, "egyezik": None}
    return e["ertek"]


# ------------------------------------------------------------------ a callout

def _cimke(ell: dict) -> str:
    return "CAS-ellenőrzött" if ell.get("ellenorzott") else "nem ellenőrizhető"


def callout(elso: dict, masodik: dict | None, cmp: dict, *, modell: str, masodik_modell: str | None = None,
            masodik_ok: str | None = None, proba: bool = False) -> str:
    """A `> [!solution]-` callout szövege (sorvég nélkül). `masodik`: a második vélemény ellenőrzése, vagy None (`masodik_ok`
    mondja meg, miért nincs)."""
    sorok = [f"{CALLOUT_FEJ}- Megoldás · {_cimke(elso)}"]
    for n, l in enumerate(elso.get("lepesek") or [], 1):
        jel = JEL.get(l.get("jel") or "", "")
        sorok.append(f"> {n}. {l['szoveg']}" + (f" {jel}" if jel else ""))
    if not elso.get("lepesek"):
        sorok.append("> *A modell nem írt lépéseket.*")
    sorok.append(">")
    la, lb = cmp.get("latex_a"), cmp.get("latex_b")
    if masodik is not None and cmp.get("egyezik") is False:
        sorok.append(f"> **Eredmény ({modell}):** " + (f"${la}$" if la else "*nincs értelmezhető eredmény*"))
        sorok.append(f"> **Eredmény ({masodik_modell}, második vélemény · {_cimke(masodik)}):** "
                     + (f"${lb}$" if lb else "*nincs értelmezhető eredmény*"))
        sorok.append("> **A két megoldás eltér** — ellenőrizd a lépéseket.")
    else:
        sorok.append("> **Eredmény:** " + (f"${la}$" if la else "*nincs értelmezhető eredmény*"))
        if masodik is None:
            sorok.append(f"> *Második vélemény:* nincs ({masodik_ok or 'nem kértük'}).")
        elif cmp.get("egyezik"):
            sorok.append(f"> *Második vélemény* ({masodik_modell}, {_cimke(masodik)}): egyezik.")
        else:
            sorok.append(f"> *Második vélemény* ({masodik_modell}, {_cimke(masodik)}): nem vethető össze"
                         + (f" (${lb}$)." if lb else "."))
    if elso.get("ok"):
        sorok.append(f"> *Nem ellenőrizhető:* {elso['ok']}.")
    sorok.append(f"> *{modell} · matek_cas" + (" · próba" if proba else "") + "*")
    return "\n".join(s.replace("==", "=") for s in sorok)


def beszur(szoveg: str, ig: int, blokk: str) -> str:
    """A callout a jegyzet `ig`. sora (1-től) UTÁN; ha közvetlenül alatta (legfeljebb egy üres sor után) már `> [!solution]` áll,
    azt cseréli (az újrafuttatás nem halmoz)."""
    sorok = szoveg.split("\n")
    elotte, utana = sorok[:ig], sorok[ig:]
    i = 1 if utana[:1] == [""] else 0
    if len(utana) > i and utana[i].lstrip().lower().startswith(CALLOUT_FEJ):
        j = i + 1
        while j < len(utana) and utana[j].startswith(">"):
            j += 1
        utana = utana[j:]
    while utana[:1] == [""]:
        utana = utana[1:]
    uj = elotte + ["", *blokk.split("\n")] + ([""] + utana if utana else [""])
    return "\n".join(uj)


def feladat_sorai(szoveg: str, tol: int, ig: int) -> str:
    """A jegyzet `tol`–`ig` sorai (1-től, zárt) egy szövegként (a feladat; a hívó ezzel ellenőrzi, hogy nem változott)."""
    return "\n".join(szoveg.split("\n")[max(tol, 1) - 1:ig])
