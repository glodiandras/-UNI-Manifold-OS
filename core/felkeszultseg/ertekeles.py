"""Szöveges értékelés a helyi modellel (C28b; CLAUDE.md D9; `docs/C28-TERV.md`): a felkészültség **számait** a kód számolja
(`osszesit.reszlet`), a modell csak szavakba önti őket — **a számok a promptban vannak, a modell nem számol**.

- `tenyek`: a dolgozat-részletből (`osszesit.reszlet`) a modellnek szánt, **előre formázott** tények (a szám úgy áll a promptban,
  ahogyan a szövegben meg kell jelennie: „62%”, „3 napja”, „45 perc”). Útvonal és jegyzettartalom nincs benne, csak a témák nevei.
- `prompt`: a modell utasítása (egy helyen, `PROMPT_VERZIO`).
- `kapu`: **a szövegben csak a tényekben álló szám szerepelhet** (számjegyek és a fél-pontos szám-szavak: „három”, „húsz”…); a
  felsorolásjelölő „1.” kivétel. Az ismétlés: egy újrapróbálkozás a tiltott számok megnevezésével; ha az is bukik, nincs szöveg
  (`kapu_bukott`) — a hamis számot tartalmazó szöveg a felhasználóhoz nem jut el.
- `futtat`: a lánc (modellhívás → kapu → újrapróbálás) egy tiszta függvény: a modell egy `(prompt, max_tokens) → szöveg | tokenek` hívó.

**Nem ír semmit**: a szöveg a felületen jelenik meg, a vaultba nem kerül (a 4. döntés kísérőjegyzet-szabálya a kvízre, a kártyára és az
összefoglalóra szól). Modellt a core nem tölt be (§4): a hívót a végpont a workerhez köti (`kereses_api.szolgalat`), D9 szerint
élesben csak a `szoveg` feladat kalibrált modellje; kifejezett modell csak próbaként (`proba: true`).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Callable, Iterable

PROMPT_VERZIO = "ertekeles-v1"
MAX_TOKEN = 420
MAX_PROBALKOZAS = 2
MAX_TEMA = 8
MAX_TERV_NAP = 4

SZINT_SZOVEG = {"jo": "jó", "kozepes": "közepes", "gyenge": "gyenge", "nincs_adat": "nincs adat"}


def _sz(x: float | None) -> str | None:
    return None if x is None else f"{round(x * 100)}%"


def _napja(nap: int | None) -> str:
    if nap is None:
        return "nincs tanulási jel"
    return "ma" if nap <= 0 else ("tegnap" if nap == 1 else f"{nap} napja")


def _perc(p: float) -> str:
    p = round(p)
    return f"{p} perc"


HONAPOK = ("január", "február", "március", "április", "május", "június", "július", "augusztus", "szeptember", "október",
           "november", "december")


def _datum(iso: str) -> str:
    """„október 7.” — az év nélküli magyar dátum (a számai a nap száma: a modell ezt idézheti)."""
    d = date.fromisoformat(iso[:10])
    return f"{HONAPOK[d.month - 1]} {d.day}."


def _napok_mulva(napok: int | None) -> str:
    if napok is None:
        return ""
    if napok == 0:
        return ", ma van"
    return f", {napok} nap múlva" if napok > 0 else f", {-napok} napja volt"


def tenyek(r: dict, ma: date) -> dict:
    """A modellnek szánt tények a dolgozat részletéből (`osszesit.reszlet`): `{szoveg, szam_van, temak, kulcs}`. A `szoveg` az, ami a
    promptba kerül; ebben álló számok az egyetlen megengedettek. Mért szám nélkül (`szam_van = False`) a hívó a modellt nem hívja."""
    sorok = [f"Dolgozat: {r['cim']}" + (f" ({r['tantargy']})" if r.get("tantargy") else ""),
             f"Napja: {_datum(r['nap'])}{_napok_mulva(r.get('napok'))}"]
    if r.get("lezart"):
        sorok.append("Állapot: a dolgozat már lezárult; a számok a mostani állapotot mutatják.")
    szam = r.get("szam")
    if szam is None:
        sorok.append("Felkészültség: nincs szám (még nincs mért tudás: kártya vagy kvíz).")
    else:
        l = r.get("lefedettseg") or {}
        sorok.append(f"Felkészültség: {_sz(szam)} ({SZINT_SZOVEG.get(r.get('szint'), r.get('szint'))}); "
                     f"{l.get('van')} / {l.get('osszes')} témára van mért adat.")
        if r.get("kilatas") is not None and not r.get("lezart"):
            sorok.append(f"Kilátás a dolgozat napjára, ha addig nem tanul többet: {_sz(r['kilatas'])}.")
    if not r["keplet"]["kalibralt"]:
        sorok.append("A súlyok kalibrálatlan induló értékek (a becslés tájékoztató).")
    if r.get("eredmeny"):
        e = r["eredmeny"]
        sorok.append(f"A dolgozat tényleges eredménye: {_sz(e['szazalek'] / 100)}" + (
            f" ({_tiz(e['pont'])} / {_tiz(e['max'])} pont)" if e.get("pont") is not None else "") + ".")
    temak = []
    sorok.append("Témák:")
    for t in r["temak"][:MAX_TEMA]:
        reszek = [f"{t['nev']}: " + (f"{_sz(t['szam'])}" if t["szam"] is not None else "nincs adat (még nincs mért tudás)")]
        if t["szam"] is not None and t.get("kilatas") is not None and not r.get("lezart"):
            reszek.append(f"kilátás {_sz(t['kilatas'])}")
        k = t["kartya"]
        reszek.append(f"{k['db']} kártya" + (f" (ebből {k['uj']} új)" if k["uj"] else "") if k["db"] else "nincs kártya")
        if k["esedekes"]:
            reszek.append(f"{k['esedekes']} esedékes kártya")
        reszek.append(f"{t['kviz']['db']} kvízeredmény" if t["kviz"]["db"] else "nincs kvíz")
        reszek.append(f"utolsó tanulás: {_napja(_nap_kul(t, ma))}")
        if t.get("tanult_perc"):
            reszek.append(f"tanult idő: {_perc(t['tanult_perc'])}")
        sorok.append("- " + "; ".join(reszek))
        temak.append(t["nev"])
    if len(r["temak"]) > MAX_TEMA:
        sorok.append(f"(és még {len(r['temak']) - MAX_TEMA} téma)")
    gy = r.get("gyenge_pontok") or {}
    if gy.get("temak"):
        sorok.append("Gyenge témák (a gyenge sáv alatt): " + ", ".join(f"{x['nev']} ({_sz(x['szam'])})" for x in gy["temak"]) + ".")
    if gy.get("nincs_adat"):
        sorok.append("Mért adat nélküli témák: " + ", ".join(x["nev"] for x in gy["nincs_adat"]) + ".")
    terv = (r.get("terv") or {}).get("napok") or []
    if terv:
        sorok.append("Napi terv (a kód számolta):")
        for n in terv[:MAX_TERV_NAP]:
            szeletek = ", ".join(f"{s['tema']} {_perc(s['perc'])}" for s in n["szeletek"]) or "átismétlés"
            sorok.append(f"- {_datum(n['nap'])}: {_perc(n['perc'])} ({szeletek})" + (f"; {n['kartya_esedekes']} esedékes kártya" if n.get("kartya_esedekes") else ""))
    szoveg = "\n".join(sorok)
    return {"szoveg": szoveg, "szam_van": szam is not None, "temak": temak,
            "kulcs": hashlib.sha1((PROMPT_VERZIO + "\n" + szoveg).encode("utf-8")).hexdigest()[:16]}


def _tiz(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}".replace(".", ",")


def _nap_kul(t: dict, ma: date) -> int | None:
    """Az utolsó tanulás óta eltelt napok (a részlet a dátumot adja); nincs jel → `None`."""
    return None if not t.get("utolso_tanulas") else (ma - date.fromisoformat(t["utolso_tanulas"])).days


PROMPT = """Te egy tanulási asszisztens vagy. Egy diák dolgozatra való felkészültségét kell szavakkal értékelned az alábbi ADATOK alapján.

SZABÁLYOK
- A számokat a program már kiszámolta. Te csak az ADATOK között álló számokat használhatod, pontosan úgy, ahogyan ott állnak (például „62%”, „3 napja”, „45 perc”).
- Nem számolhatsz, nem kerekíthetsz, nem becsülhetsz, nem vonhatsz össze és nem vonhatsz ki; új számot, százalékot, dátumot vagy darabszámot nem írhatsz.
- Csak az ADATOKBAN megnevezett témákról beszélj; ne találj ki témát, kártyát vagy tényt.
- Ha egy témánál „nincs adat”, azt mondd ki, és ne becsüld meg.
- Ne ígérj osztályzatot vagy pontszámot.
- 3–5 mondat magyarul, tegező, tárgyilagos hangon, folyó szövegben (nincs lista, nincs címsor). Előbb az összkép, aztán a leggyengébb témák, végül egy konkrét teendő a napi tervből.

ADATOK
{tenyek}
{kiegeszites}
ÉRTÉKELÉS:"""


def prompt(t: dict, tiltott: Iterable[str] = ()) -> str:
    tiltott = [x for x in tiltott]
    kieg = ""
    if tiltott:
        kieg = ("\nFIGYELEM: az előző válaszod olyan számot tartalmazott, amely nincs az ADATOK között: " + ", ".join(tiltott)
                + ". Írd újra úgy, hogy csak az ADATOKBAN álló számok szerepelnek (vagy egyáltalán ne írj számot).\n")
    return PROMPT.format(tenyek=t["szoveg"], kiegeszites=kieg)


# ------------------------------------------------------------------ a szám-kapu

_SZAM = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)")
_LISTAJEL = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)", re.M)
_SZAMSZOVEG = {"kettő": 2, "két": 2, "három": 3, "négy": 4, "öt": 5, "tíz": 10, "tizenegy": 11, "tizenkettő": 12, "húsz": 20,
               "harminc": 30, "negyven": 40, "ötven": 50, "hatvan": 60, "hetven": 70, "nyolcvan": 80, "kilencven": 90, "száz": 100,
               "nyolc": 8, "kilenc": 9, "hétszáz": 700}
_SZO = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+")


def _ertek(s: str) -> float:
    return float(s.replace(",", "."))


def szamok(szoveg: str, listajelek_nelkul: bool = True) -> set[float]:
    """A szövegben álló számok értékei (a tizedesvessző és -pont egyaránt). A sorkezdő felsorolásjelölő („1.”, „- ”) nem szám."""
    if listajelek_nelkul:
        szoveg = _LISTAJEL.sub("", szoveg)
    return {_ertek(m.group(1)) for m in _SZAM.finditer(szoveg)}


def kapu(szoveg: str, tenyek_szoveg: str) -> tuple[bool, list[str]]:
    """Csak a tényekben álló szám szerepelhet a szövegben → `(rendben, tiltott számok)`. A szám-szavak (kettő…száz) csak akkor
    megengedettek, ha az értékük a tényekben szerepel; az „egy”, a „hét” (nap) és a „hat” nem számít számnak (főnév/névelő/ige)."""
    engedett = szamok(tenyek_szoveg, listajelek_nelkul=False)
    tiltott: list[str] = []
    for m in _SZAM.finditer(_LISTAJEL.sub("", szoveg)):
        if _ertek(m.group(1)) not in engedett and m.group(1) not in tiltott:
            tiltott.append(m.group(1))
    for w in _SZO.findall(szoveg.lower()):
        v = _SZAMSZOVEG.get(w)
        if v is not None and float(v) not in engedett and w not in tiltott:
            tiltott.append(w)
    return not tiltott, tiltott


# ------------------------------------------------------------------ a lánc

ModellHivas = Callable[[str, int], "str | Iterable[str]"]


def _szoveg(valasz) -> str:
    return valasz if isinstance(valasz, str) else "".join(valasz)


def tisztit(szoveg: str) -> str:
    """A modell kimenetének rendezése: gondolkodás-maradék, felesleges üres sorok, kiemelés-jelek nélkül."""
    s = re.sub(r"<think>.*?</think>", "", szoveg, flags=re.S)
    s = re.sub(r"\*{1,3}|__", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def futtat(hivo: ModellHivas, t: dict, max_probalkozas: int = MAX_PROBALKOZAS) -> dict:
    """A lánc: a modell kimenete a szám-kapun át; bukásnál egy újrapróbálkozás a tiltott számok megnevezésével.
    → `{allapot: kesz | kapu_bukott | ures, szoveg, probalkozas, tiltott}`. A `hivo` hibája (nincs kalibrált modell, a worker nem
    érhető el) kivételként megy tovább — a végpont 503-má fordítja."""
    tiltott: list[str] = []
    utolso: list[str] = []
    for i in range(1, max_probalkozas + 1):
        szoveg = tisztit(_szoveg(hivo(prompt(t, tiltott), MAX_TOKEN)))
        if not szoveg:
            return {"allapot": "ures", "szoveg": None, "probalkozas": i, "tiltott": []}
        ok, tiltott = kapu(szoveg, t["szoveg"])
        if ok:
            return {"allapot": "kesz", "szoveg": szoveg, "probalkozas": i, "tiltott": []}
        utolso = tiltott
    return {"allapot": "kapu_bukott", "szoveg": None, "probalkozas": max_probalkozas, "tiltott": utolso}
