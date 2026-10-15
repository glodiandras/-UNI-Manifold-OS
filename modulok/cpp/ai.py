"""A C++ AI-réteg szöveges magja (C36b; `docs/C36-TERV.md` „C36b”): a prompt, a válasz-elemzés és a nyelvi kapu —
**egyetlen helyen**, az élő út (`ai_futas.py`, a core gyermekfolyamata) és a mérés (`modulok/eval/kod/feladat.py`) is ezt
használja, így a mért kérés és az éles kérés ugyanaz (D9: a kalibráció a mért promptra szól).

Öt mód, egy router-feladat (`kod`):

| Mód | Mit kér a modelltől | Mit ad a válasz |
|---|---|---|
| `hiba` | a hiba helye és fajtája, rövid magyarázat; a bemenet a fordító / sanitizer / elbukó teszt bizonyítéka | `{sor, fajta, magyarazat}` (zárósor: `HIBA: <sor> <fajta>`) |
| `tipp` | háromlépcsős tipp: irány → algoritmus → hely, kód nélkül | `{szintek: [irány, algoritmus, hely], hely_sor}` |
| `megoldas` | a javított teljes program (a tipp-lépcső 4. foka, csak külön megerősítéssel) | `{kod, magyarazat}` |
| `teszt` | 3–5 szélső bemenet + lassú, nyilvánvalóan helyes referencia | `{bemenetek, referencia}` |
| `stressz` | véletlenbemenet-generátor (mag = 1. argumentum) + lassú referencia | `{generator, referencia}` |

A modell kimenete itt csak szöveg: a kód sehol nem fut ebben a modulban. Fordítás és futtatás kizárólag a program-homokozóban
(`ai_ellenorzes.py`, 53(b)).
"""
from __future__ import annotations

import re

PROMPT_VERZIO = "kod-p1"
MODOK = ("hiba", "tipp", "megoldas", "teszt", "stressz")
# a modell válaszának token-kerete (a gondolkodó modellek kerete a regiszterből adódik hozzá: `core.modell.eval.keres_beallitas`)
MAX_TOKENS = {"hiba": 700, "tipp": 700, "megoldas": 2200, "teszt": 1800, "stressz": 2200}
FAJTAK = {
    "index": "eggyel elcsúszott index vagy határ (< és <=, rossz kezdő- vagy zárósorszám)",
    "tulcsordulas": "egész túlcsordulás (int a long long helyett, hiányzó maradékképzés)",
    "inicializalas": "rossz kezdőérték (pl. a maximum 0-ról indul, a számláló nem nullázódik)",
    "alapeset": "rossz alapeset a rekurzióban vagy a dinamikus programozásban",
    "ido": "helyes, de túl lassú algoritmus (időtúllépés)",
    "feltetel": "rossz feltétel vagy összehasonlítás (> és >=, && és ||)",
    "sorrend": "rossz sorrend: frissítés a használat előtt, rossz bejárási irány, rossz kiírási sorrend",
    "egyeb": "más hiba",
}
BEMENET_MAX_KAR = 600              # a promptba kerülő bemenet / kimenet legfeljebb ennyi karakter
TESZT_BEMENET_MAX = 5
TESZT_BEMENET_MAX_KAR = 4000

# --------------------------------------------------------------------------- a prompt

_FAJTA_LISTA = "\n".join(f"- {k}: {v}" for k, v in FAJTAK.items())

_HIBA = """Egy diák C++17 megoldása hibás. Keresd meg a hibát.

FELADAT:
{leiras}

A DIÁK KÓDJA (sorszámozva):
{kod}

MIT LÁTUNK:
{bizonyitek}

Magyarul válaszolj: 2–4 mondatban magyarázd el, mi a hiba, és miért okozza a fenti tünetet. Ne írd meg a javított
programot, és ne írj kódblokkot. A válasz utolsó sora pontosan ilyen alakú legyen:
HIBA: <sorszám> <fajta>
ahol a <sorszám> a hibás sor száma a fenti számozás szerint, a <fajta> pedig ezek egyike:
{fajtak}"""

_TIPP = """Egy diák C++17 megoldása hibás. Segíts neki úgy, hogy a javítást maga találja meg.

FELADAT:
{leiras}

A DIÁK KÓDJA (sorszámozva):
{kod}

MIT LÁTUNK:
{bizonyitek}

Adj háromlépcsős tippet magyarul. Ne írd meg a megoldást, ne írj kódot vagy kódblokkot, és ne idézz kódsort.
Pontosan ebben az alakban válaszolj, három sorban:
1. IRÁNY: <egy-két mondat: merre keresse a hibát>
2. ALGORITMUS: <egy-két mondat: mi a helyes gondolatmenet>
3. HELY: <egy mondat: melyik sorban van a gond (a sorszámmal, pl. „a 12. sorban”), és mi a baj vele>"""

_MEGOLDAS = """Egy diák C++17 megoldása hibás. Javítsd ki.

FELADAT:
{leiras}

A DIÁK KÓDJA (sorszámozva):
{kod}

MIT LÁTUNK:
{bizonyitek}

Javítsd ki a programot a lehető legkisebb módosítással. Előbb egy-két mondatban magyarul írd le, mit javítottál, utána
add meg a teljes javított programot egyetlen ```cpp kódblokkban (szabványos bemenet → szabványos kimenet)."""

_TESZT = """Egy C++17 feladathoz szélső teszteseteket keresünk.

FELADAT:
{leiras}

A DIÁK KÓDJA (sorszámozva):
{kod}

Írj 3–5 szélső tesztesetet, amely a gyakori hibákat leleplezheti (határok, legkisebb és legnagyobb érték, ismétlődés,
egyelemű eset, negatív szám, túlcsordulás). Minden bemenet külön ```bemenet kódblokkba kerüljön, pontosan a feladat
bemeneti formátumában, kicsi méretben (legfeljebb 30 sor). A várt kimenetet NE írd meg.
Utána írj egy egyszerű, lassú, de nyilvánvalóan helyes C++17 referenciamegoldást (nyers erővel) egyetlen ```cpp
kódblokkban; a szabványos bemenetről olvas, a szabványos kimenetre ír. Magyarázatot ne írj."""

_STRESSZ = """Egy C++17 feladathoz stressz-tesztet készítünk: véletlen bemeneteken összevetjük a diák megoldását egy lassú,
de biztosan helyes megoldással.

FELADAT:
{leiras}

A DIÁK KÓDJA (sorszámozva):
{kod}

Írj két C++17 programot, mindkettőt külön ```cpp kódblokkba, ebben a sorrendben:
1. GENERÁTOR: az első parancssori argumentum egy egész szám (mag); ebből std::mt19937-tel EGY kicsi, véletlen, a feladat
   bemeneti formátumának pontosan megfelelő bemenetet ír a szabványos kimenetre. Kis méretek legyenek (a lassú megoldás
   gyors maradjon), és gyakran forduljanak elő szélső értékek. Fájlt és hálózatot nem használhat.
2. REFERENCIA: egyszerű, lassú, de nyilvánvalóan helyes megoldás (nyers erő); szabványos bemenet → szabványos kimenet.
Magyarázatot ne írj."""

_SABLON = {"hiba": _HIBA, "tipp": _TIPP, "megoldas": _MEGOLDAS, "teszt": _TESZT, "stressz": _STRESSZ}


def szamozott(kod: str) -> str:
    """A kód sorszámozva (1-től, a sorszám jobbra igazítva), ahogy a modell és a diák is hivatkozik rá."""
    sorok = kod.replace("\r\n", "\n").split("\n")
    if sorok and sorok[-1] == "":
        sorok.pop()
    w = len(str(len(sorok)))
    return "\n".join(f"{i:>{w}} | {s}" for i, s in enumerate(sorok, 1))


def _rovid(s: str | None, n: int = BEMENET_MAX_KAR) -> str:
    s = (s or "").rstrip("\n")
    return s if len(s) <= n else s[:n] + f"\n… (levágva, összesen {len(s)} karakter)"


def bizonyitek_szoveg(b: dict | None) -> str:
    """A bizonyíték (`fajta`: `fordito` | `teszt` | `szanitizer` | `ido` | `nagy` | `nincs`) szövege a promptba. A szerkezet a
    motoré (az élő úton az ellenőrzés eseményeiből, a mérésben a befagyasztott aranyból), a szöveg egyetlen helye ez."""
    if not b:
        return "Nincs további információ."
    f = b.get("fajta")
    if f == "fordito":
        sorok = [f"- {d.get('sor') or '?'}. sor: {d.get('uzenet', '')}" for d in (b.get("diagnosztika") or [])[:6]]
        return "A program nem fordul le. A fordító hibaüzenetei:\n" + ("\n".join(sorok) or "- (nincs részlet)")
    if f in ("teszt", "szanitizer"):
        r = [f"Egy teszten a program hibás eredményt ad ({b.get('allapot_szoveg') or b.get('allapot') or 'hibás kimenet'})."]
        r.append("Bemenet:\n" + _rovid(b.get("bemenet")))
        if b.get("vart") is not None:
            r.append("Várt kimenet:\n" + _rovid(b.get("vart")))
        if b.get("kapott") is not None:
            r.append("A program kimenete:\n" + (_rovid(b.get("kapott")) or "(üres)"))
        if b.get("jelentes"):
            j = b["jelentes"]
            r.append(f"A futásidejű ellenőrző jelentése: {j.get('leiras', '')}"
                     + (f" (a {j['sor']}. sorban)" if j.get("sor") else ""))
        return "\n".join(r)
    if f == "ido":
        return f"A program helyes kis bemeneteken, de {b.get('leiras') or 'egy nagy bemeneten'} túllépi az időkorlátot."
    if f == "nagy":
        return (f"Kis bemeneteken a program helyes, de {b.get('leiras') or 'egy nagy bemeneten'} hibás eredményt ad. "
                f"Várt kimenet: {_rovid(b.get('vart'), 80)}; a program kimenete: {_rovid(b.get('kapott'), 80)}.")
    return b.get("leiras") or "Nincs további információ."


def prompt(mod: str, leiras: str, kod: str, bizonyitek: dict | None = None) -> str:
    """A mód promptja. A `leiras` a feladat-jegyzet szövege (a `teszt` blokkokkal együtt), a `kod` a diák kódja."""
    if mod not in _SABLON:
        raise ValueError(f"ismeretlen mód: {mod!r} ({', '.join(MODOK)})")
    return _SABLON[mod].format(leiras=leiras.strip(), kod=szamozott(kod), bizonyitek=bizonyitek_szoveg(bizonyitek),
                               fajtak=_FAJTA_LISTA)


def keres(mod: str, leiras: str, kod: str, bizonyitek: dict | None = None) -> dict:
    """A worker chat-kérése (a `feladat`, a mód és a keret nélkül: azokat a hívó adja). Determinisztikus (L27)."""
    return {"messages": [{"role": "user", "content": prompt(mod, leiras, kod, bizonyitek)}], "max_tokens": MAX_TOKENS[mod]}


# --------------------------------------------------------------------------- a válasz

_GONDOLAT = re.compile(r"<think>.*?</think>|\[THINK\].*?\[/THINK\]", re.S)
_GONDOLAT_ZARO = ("</think>", "[/THINK]")
_KERITES = re.compile(r"(?m)^[ \t]*(`{3,}|~{3,})[ \t]*([^\n`]*)\n(.*?)^[ \t]*\1[ \t]*$", re.S)
_HIBA_SOR = re.compile(r"HIBA\s*:\s*(?:a\s+)?(\d{1,5})\.?\s*(?:sor\w*)?[\s,;:-]*([A-Za-záéíóöőúüűÁÉÍÓÖŐÚÜŰ_]+)?", re.I)
_SZINT = re.compile(r"(?mi)^\s*(?:\*\*)?\s*([1-3])\s*[.)]\s*(?:\*\*)?\s*(IRÁNY|IRANY|ALGORITMUS|HELY)\s*(?:\*\*)?\s*:\s*(?:\*\*)?")
_SOR_HIVATKOZAS = re.compile(r"(\d{1,5})\.\s*sor|sor(?:ban|a|on)?\s*\(?(\d{1,5})\)?|line\s+(\d{1,5})", re.I)
_CPP_NYELV = ("cpp", "c++", "cc", "cxx", "c")
_AKCENT = re.compile(r"[áéíóöőúüű]", re.I)
_SZO = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{2,}")
_MAGYAR_SZAVAK = frozenset("""az egy és nem hogy van ez ezt meg csak mert vagy kell ha akkor már még ami amely mint itt ott nincs lesz
után előtt között minden sor sorban ciklus hiba hibát változó érték értéke tömb függvény helyett miatt ezért amikor pedig szám
számot elem elemet így úgy azonban kezdve tehát kap kapja helyes hibás eredmény lenne legyen ugyanis vagyis nagyobb kisebb
egyenlő feltétel feltételt index indexe utolsó első kimenet bemenet program programot nagy kicsi összeg összegét""".split())


def tisztit(valasz) -> str:
    """A válasz szövege a gondolkodó modellek blokkja nélkül (`<think>…</think>`, `[THINK]…[/THINK]`); nem szöveg → üres."""
    if not isinstance(valasz, str):
        return ""
    s = _GONDOLAT.sub("", valasz)
    for zaro in _GONDOLAT_ZARO:                       # nyitó jel nélküli gondolkodás: csak a záró utáni rész a válasz
        if zaro in s:
            s = s.split(zaro)[-1]
    return s.strip()


def kodblokkok(szoveg: str) -> list[tuple[str, str]]:
    """A kódkerítések `(info, tartalom)` párjai, sorrendben (az info kisbetűs, levágva)."""
    return [(m.group(2).strip().lower(), m.group(3)) for m in _KERITES.finditer(szoveg)]


def _cpp_blokkok(szoveg: str) -> list[tuple[str, str]]:
    ki = []
    for info, tart in kodblokkok(szoveg):
        nyelv = info.split()[0] if info else ""
        if nyelv in _CPP_NYELV or (not nyelv and ("#include" in tart or "int main" in tart)):
            ki.append((info, tart))
    return ki


def kodon_kivul(szoveg: str) -> str:
    """A szöveg a kódblokkok és a `soron belüli kód` nélkül."""
    return re.sub(r"`[^`\n]*`", " ", _KERITES.sub(" ", szoveg))


def magyar_arany(szoveg: str) -> float:
    """A kódon kívüli szöveg szavai közül a magyarnak ismertek aránya (ékezetes betű vagy gyakori magyar szó). Az angol szöveg
    ~0, a magyar magyarázat jellemzően 0,4 fölött. Üres szöveg: 0."""
    szavak = _SZO.findall(kodon_kivul(szoveg))
    if not szavak:
        return 0.0
    jo = sum(1 for s in szavak if _AKCENT.search(s) or s.lower() in _MAGYAR_SZAVAK)
    return round(jo / len(szavak), 4)


def hiba_valasz(valasz) -> dict:
    """`{sor, fajta, magyarazat}`: az utolsó `HIBA:` sor; a fajta a zárt listából (ismeretlen: `egyeb`, hiányzó: None)."""
    s = tisztit(valasz)
    talalat = list(_HIBA_SOR.finditer(s))
    if not talalat:
        return {"sor": None, "fajta": None, "magyarazat": s}
    m = talalat[-1]
    fajta = (m.group(2) or "").lower().strip("_") or None
    if fajta is not None and fajta not in FAJTAK:
        fajta = "egyeb"
    magyarazat = (s[:m.start()] + s[m.end():]).strip()
    return {"sor": int(m.group(1)), "fajta": fajta, "magyarazat": magyarazat}


def sor_hivatkozasok(szoveg: str) -> list[int]:
    """A szövegben említett sorszámok („a 12. sorban”, „12. sor”, „sor 12”), sorrendben."""
    ki = []
    for m in _SOR_HIVATKOZAS.finditer(szoveg):
        n = next(g for g in m.groups() if g)
        ki.append(int(n))
    return ki


def tipp_valasz(valasz) -> dict:
    """`{szintek: [irány, algoritmus, hely] (hiányzó: None), sorrend_ok, hely_sor, kod_szintek}`. A kódot tartalmazó szint
    (kódkerítés) a `kod_szintek`-be kerül: az élő út nem mutatja meg."""
    s = tisztit(valasz)
    jelek = list(_SZINT.finditer(s))
    szintek: list[str | None] = [None, None, None]
    sorrend = []
    for i, m in enumerate(jelek):
        veg = jelek[i + 1].start() if i + 1 < len(jelek) else len(s)
        n = int(m.group(1)) - 1
        if szintek[n] is None:
            szintek[n] = s[m.end():veg].strip()
            sorrend.append(n)
    hely = szintek[2] or ""
    hiv = sor_hivatkozasok(hely)
    return {"szintek": szintek, "sorrend_ok": sorrend == [0, 1, 2],
            "hely_sor": hiv[0] if hiv else None,
            "kod_szintek": [i for i, t in enumerate(szintek) if t and ("```" in t or "~~~" in t)]}


def megoldas_valasz(valasz) -> dict:
    """`{kod, magyarazat}`: az utolsó C++ kódblokk és a kódon kívüli szöveg."""
    s = tisztit(valasz)
    blokkok = _cpp_blokkok(s)
    return {"kod": blokkok[-1][1] if blokkok else None, "magyarazat": kodon_kivul(s).strip()}


def teszt_valasz(valasz) -> dict:
    """`{bemenetek, referencia}`: a `bemenet` (vagy nyelv nélküli, nem C++) kódblokkok legfeljebb `TESZT_BEMENET_MAX` darabja,
    és az utolsó C++ blokk. A túl hosszú bemenet kimarad."""
    s = tisztit(valasz)
    bemenetek = []
    for info, tart in kodblokkok(s):
        nyelv = info.split()[0] if info else ""
        if nyelv in ("bemenet", "input", "text", "txt", "plaintext") or (
                not nyelv and "#include" not in tart and "int main" not in tart):
            t = tart if tart.endswith("\n") else tart + "\n"
            if t.strip() and len(t) <= TESZT_BEMENET_MAX_KAR:
                bemenetek.append(t)
    cpp = _cpp_blokkok(s)
    return {"bemenetek": bemenetek[:TESZT_BEMENET_MAX], "referencia": cpp[-1][1] if cpp else None}


def stressz_valasz(valasz) -> dict:
    """`{generator, referencia}`: a címkés (`cpp generator` / `cpp referencia`) blokkok, különben az első két C++ blokk a kért
    sorrendben; ha a sorrend fordított (a második olvassa az `argv`-t), megcseréli."""
    s = tisztit(valasz)
    cpp = _cpp_blokkok(s)
    gen = next((t for i, t in cpp if "gener" in i), None)
    ref = next((t for i, t in cpp if "refer" in i), None)
    maradek = [t for i, t in cpp if t is not gen and t is not ref]
    if gen is None and maradek:
        gen = maradek.pop(0)
    if ref is None and maradek:
        ref = maradek.pop(0)
    if gen is not None and ref is not None and "argv" not in gen and "argv" in ref:
        gen, ref = ref, gen
    return {"generator": gen, "referencia": ref}


def atfedes(szoveg: str, kod: str, min_hossz: int = 12) -> int:
    """A `kod` érdemi soraiból (szóközök nélkül legalább `min_hossz` karakter, nem `#include`/`using`) hány áll szó szerint
    (szóköz-függetlenül) a `szoveg`-ben: a „ne írd meg a megoldást” kapu mértéke."""
    tomor = re.sub(r"\s+", "", szoveg)
    db = 0
    for sor in kod.splitlines():
        t = re.sub(r"\s+", "", sor)
        if len(t) >= min_hossz and not t.startswith(("#include", "using")) and t in tomor:
            db += 1
    return db
