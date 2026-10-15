"""A C++ feladat-jegyzet formátuma (C36a; TERV 5.14): a `teszt` blokk és a váz — **a formátum egyetlen helye** (mint a
`core/pdfkiemeles.py`); a motor (`modulok/cpp`) és a végpontok ezt használják.

A feladat-jegyzet közönséges Markdown: leírás, `teszt` blokkok és a megoldás kísérő `.cpp` fájlja, a jegyzetbe
`![[<név>.cpp]]` sorral beágyazva. Egy `teszt` blokk egy teszt:

    ```teszt Szélső eset
    --- bemenet
    5
    1 2 3 4 5
    --- kimenet
    15
    --- idokorlat
    1.5
    ```

- A blokk nyelve a `teszt`; utána szabadon egy cím. A kerítés-felismerés az egyetlen helyén, a `core/index/maszk.keritesek`-ben
  van; idézetben, callout-ban és listaelemben álló blokk előtagját az elemző leveszi.
- Szakaszjelző csak a `--- bemenet`, `--- kimenet`, `--- idokorlat` (álneve: `--- ido`), `--- memoria`, `--- osszevetes`
  (kis-nagybetű és a szóközök szabadok) sor; minden más sor tartalom, a `---` és a `--- valami` is. A blokk első nem üres
  sorának szakaszjelzőnek kell lennie.
- `kimenet` kötelező (üres szakasz: a program semmit sem ír); `bemenet` és `idokorlat` nem. Az időkorlát másodperc (`2`, `2s`,
  `1.5 s`, `1,5`, `500 ms`, `3 mp`), pozitív, és a hívó által megadott maximum alatt kell maradjon.
- `memoria` (C36a2; nem kötelező): a program csúcs-memóriájának korlátja, `<szám> KB|MB|GB|KiB|MiB|GiB` (kettes egység:
  MB = MiB), 1 MB–16 GB, és a hívó által megadott maximum alatt kell maradjon. Alapértéke a `[cpp] memoria_mb`.
- `osszevetes` (C36a2; nem kötelező): `alap` (az alapértelmezés: soronként, a sorvégi szóköz és a záró üres sorok nem
  számítanak) · `pontos` · `tures` (soronként a szóközzel tagolt tokenek) · `lebego [eps]` (tokenenként, a számok tűréssel;
  0 ≤ eps < 1). A módok jelentését az összevető (`modulok/cpp/osszevet.py`) rögzíti; a blokk csak a nevét és az `eps`-t hordozza.
- A szakaszok végi üres sorok nem számítanak. Hibás blokk (hiányzó kimenet, hibás időkorlát, lezáratlan kerítés) **nem fut**:
  a listában marad `hiba` szöveggel, hogy a panel mutassa.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .index import maszk

NYELV = "teszt"
_NYITO = re.compile(r"([ \t]*(?:>[ \t]*)*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?)(`{3,}|~{3,})(.*)")
_HATARO = re.compile(r"^---[ \t]+(bemenet|kimenet|idokorlat|időkorlát|ido|idő|memoria|memória|osszevetes|összevetés)[ \t]*$", re.I)
_SZAKASZ_NEV = {"időkorlát": "idokorlat", "ido": "idokorlat", "idő": "idokorlat", "memória": "memoria", "összevetés": "osszevetes"}
_IDO = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(ms|s|sec|mp)?$", re.I)
_MEMORIA = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(KB|MB|GB|KiB|MiB|GiB)$", re.I)
_EGYSEG_KB = {"kb": 1, "kib": 1, "mb": 1024, "mib": 1024, "gb": 1024 * 1024, "gib": 1024 * 1024}
MODOK = ("alap", "pontos", "tures", "lebego")
MIN_MEMORIA_KB = 1024
MAX_MEMORIA_KB = 16 * 1024 * 1024
_BEAGYAZOTT_CPP = re.compile(r"!\[\[([^\]|#\n]+?\.cpp)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]", re.I)


@dataclass
class Teszt:
    sorszam: int                  # a jegyzet `teszt` blokkjai között, 1-től (a hibás blokk is számít)
    sor: int                      # a nyitó kerítés sora a jegyzetben, 1-től
    cim: str | None
    bemenet: str
    kimenet: str
    idokorlat_s: float | None
    hiba: str | None = None
    memoria_kb: int | None = None  # a `--- memoria` szakasz; None: a config alapértéke
    osszevetes: str = "alap"       # MODOK egyike
    eps: float | None = None       # csak `lebego`-hoz; None: a config alapértéke

    @property
    def memoria_mb(self) -> float | None:
        return None if self.memoria_kb is None else self.memoria_kb / 1024

    def szotar(self) -> dict:
        return {"sorszam": self.sorszam, "sor": self.sor, "cim": self.cim, "bemenet": self.bemenet,
                "kimenet": self.kimenet, "idokorlat_s": self.idokorlat_s, "hiba": self.hiba,
                "memoria_kb": self.memoria_kb, "osszevetes": self.osszevetes, "eps": self.eps}


def _levag(sor: str, idezet: int, behuzas: int) -> str:
    for _ in range(idezet):
        sor = re.sub(r"^[ \t]*>[ \t]?", "", sor, count=1)
    k = 0
    while k < behuzas and k < len(sor) and sor[k] in " \t":
        k += 1
    return sor[k:]


def _behuzas(elotag: str) -> int:
    """A kerítés nyitó sorának előtagjából a tartalmi sorok behúzása az idézetjelek levétele után."""
    i = elotag.rfind(">")
    farok = elotag[i + 1:] if i >= 0 else elotag
    return len(farok[1:] if i >= 0 and farok.startswith(" ") else farok)


def _idokorlat(szoveg: str, maximum: float | None) -> tuple[float | None, str | None]:
    m = _IDO.match(szoveg.strip())
    if not m:
        return None, f"érvénytelen időkorlát: {szoveg.strip()!r} (pl. 2, 1.5 s, 500 ms)"
    ertek = float(m.group(1).replace(",", "."))
    if (m.group(2) or "").lower() == "ms":
        ertek /= 1000
    if ertek <= 0:
        return None, "az időkorlát legyen pozitív"
    if maximum is not None and ertek > maximum:
        return None, f"az időkorlát legfeljebb {maximum:g} s lehet"
    return ertek, None


def _memoria(szoveg: str, maximum_mb: float | None) -> tuple[int | None, str | None]:
    m = _MEMORIA.match(szoveg.strip())
    if not m:
        return None, f"érvénytelen memóriakorlát: {szoveg.strip()!r} (pl. 64MB, 1GB, 2048KB; kettes egység)"
    kb = float(m.group(1).replace(",", ".")) * _EGYSEG_KB[m.group(2).lower()]
    if kb != int(kb) or not MIN_MEMORIA_KB <= kb <= MAX_MEMORIA_KB:
        return None, "a memóriakorlát egész KB, 1 MB és 16 GB között"
    if maximum_mb is not None and kb > maximum_mb * 1024:
        return None, f"a memóriakorlát legfeljebb {maximum_mb:g} MB lehet"
    return int(kb), None


def _osszevetes(szoveg: str) -> tuple[str, float | None, str | None]:
    reszek = szoveg.split()
    if not reszek or reszek[0].lower() not in MODOK:
        return "alap", None, f"ismeretlen összevetési mód: {szoveg.strip()!r} ({', '.join(MODOK)})"
    mod = reszek[0].lower()
    if len(reszek) == 1:
        return mod, None, None
    if mod != "lebego" or len(reszek) > 2:
        return "alap", None, "tűrést csak a `lebego` mód kap: `lebego 1e-6`"
    try:
        eps = float(reszek[1])
    except ValueError:
        return "alap", None, f"a tűrés szám legyen: {reszek[1]!r}"
    if not math.isfinite(eps) or not 0 <= eps < 1:
        return "alap", None, "a tűrés 0 és 1 közötti szám"
    return mod, eps, None


def _szakaszok(sorok: list[str]) -> tuple[dict[str, list[str]], str | None]:
    szakaszok: dict[str, list[str]] = {}
    aktualis = None
    for sor in sorok:
        m = _HATARO.match(sor)
        if m:
            nev = m.group(1).lower()
            nev = _SZAKASZ_NEV.get(nev, nev)
            if nev in szakaszok:
                return szakaszok, f"a `{nev}` szakasz kétszer szerepel"
            szakaszok[nev] = []
            aktualis = nev
        elif aktualis is None:
            if sor.strip():
                return szakaszok, ("a blokk első sora `--- bemenet`, `--- kimenet` vagy `--- idokorlat` szakaszjelző legyen"
                                   f" (ez áll helyette: {sor.strip()[:40]!r})")
        else:
            szakaszok[aktualis].append(sor)
    return szakaszok, None


def _szoveg(sorok: list[str]) -> str:
    sorok = list(sorok)
    while sorok and not sorok[-1].strip():
        sorok.pop()
    return "\n".join(sorok) + "\n" if sorok else ""


def tesztek(szoveg: str, max_idokorlat_s: float | None = None, max_memoria_mb: float | None = None) -> list[Teszt]:
    """A jegyzet `teszt` blokkjai a fájl sorrendjében (a hibás blokk is, `hiba` szöveggel)."""
    txt = szoveg.replace("\r\n", "\n").replace("\r", "\n")
    fm = maszk.FM_RE.match(txt)
    fm_veg = fm.end() if fm else 0
    ki: list[Teszt] = []
    for kezd, veg, info in maszk.keritesek(txt):
        szavak = info.split(None, 1)
        if kezd < fm_veg or not szavak or szavak[0].lower() != NYELV:
            continue
        cim = szavak[1].strip() if len(szavak) > 1 else None
        sorok = txt[kezd:veg].split("\n")
        nyito = _NYITO.match(sorok[0])
        elotag, jel = (nyito.group(1), nyito.group(2)) if nyito else ("", "```")
        zart = False
        if len(sorok) > 1:
            m = re.match(r"^[ \t]*(?:>[ \t]*)*(`{3,}|~{3,})[ \t]*$", sorok[-1])
            zart = bool(m and m.group(1)[0] == jel[0] and len(m.group(1)) >= len(jel))
        tartalom = sorok[1:-1] if zart else sorok[1:]
        idezet, behuzas = elotag.count(">"), _behuzas(elotag)
        tartalom = [_levag(s, idezet, behuzas) for s in tartalom]
        sorszam, sor = len(ki) + 1, txt.count("\n", 0, kezd) + 1
        hiba = None
        szakaszok, hiba = _szakaszok(tartalom)
        if hiba is None and not zart:
            hiba = "a kerítés nincs lezárva"
        if hiba is None and "kimenet" not in szakaszok:
            hiba = "hiányzik a `--- kimenet` szakasz"
        ido = None
        if hiba is None and "idokorlat" in szakaszok:
            ido, hiba = _idokorlat("\n".join(szakaszok["idokorlat"]), max_idokorlat_s)
        mem, mod, eps = None, "alap", None
        if hiba is None and "memoria" in szakaszok:
            mem, hiba = _memoria("\n".join(szakaszok["memoria"]), max_memoria_mb)
        if hiba is None and "osszevetes" in szakaszok:
            mod, eps, hiba = _osszevetes("\n".join(szakaszok["osszevetes"]))
        ki.append(Teszt(sorszam, sor, cim, _szoveg(szakaszok.get("bemenet", [])), _szoveg(szakaszok.get("kimenet", [])),
                        ido, hiba, mem, mod, eps))
    return ki


def beagyazott_cpp(szoveg: str) -> list[str]:
    """A jegyzetben beágyazott `.cpp` fájlok (`![[X.cpp]]` célja, alias és horgony nélkül), a fájl sorrendjében; a kódban és a
    képletben állókat a link-maszk elfedi."""
    maszkolt = maszk.link_maszk(szoveg.replace("\r\n", "\n"))
    ki: list[str] = []
    for m in _BEAGYAZOTT_CPP.finditer(maszkolt):
        cel = m.group(1).strip()
        if cel not in ki:
            ki.append(cel)
    return ki


def teszt_blokk(cim: str | None, bemenet: str, kimenet: str) -> str:
    """Egy `teszt` blokk szövege (C36b: a modell szélső tesztjének és a stressz ellenpéldájának javaslata). A kerítés a
    tartalomban álló backtick-sorozatnál hosszabb; a cím egy sor. A `tesztek()` visszaolvassa ugyanazt a bemenetet és kimenetet
    (a záró üres sorok nem számítanak)."""
    if any(_HATARO.match(s.strip()) for s in (bemenet + "\n" + kimenet).splitlines()):
        raise ValueError("a tartalomban szakaszjelző sor (`--- bemenet` …) áll: teszt blokkba nem írható")
    leghosszabb = max([len(m) for m in re.findall(r"`+", bemenet + kimenet)] + [0])
    kerites = "`" * max(3, leghosszabb + 1)
    fej = f"{kerites}{NYELV}" + (f" {' '.join(str(cim).split())}" if cim and str(cim).strip() else "")

    def szakasz(s: str) -> str:
        s = s.replace("\r\n", "\n").rstrip("\n")
        return s + "\n" if s else ""
    return f"{fej}\n--- bemenet\n{szakasz(bemenet)}--- kimenet\n{szakasz(kimenet)}{kerites}\n"


def cpp_nev(nev: str) -> str:
    """A kísérő fájl neve: a jegyzet neve `.cpp` kiterjesztéssel."""
    return f"{nev}.cpp"


def cpp_vaz() -> str:
    return ("#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n\n"
            "    return 0;\n"
            "}\n")


def feladat_vaz(nev: str, tag: str | None) -> str:
    """Az új feladat-jegyzet beépített váza (a vault sémája: `Tags`, `Source`, `Status`, `NN`, `Canvas`; a `Tags` a
    legfelső mappa tárgybetűjéből, vagy üres). A sablonmappa `C++ feladat` jegyzete felülírja (a `{{title}}` a jegyzet neve)."""
    tags = f"Tags:\n  - {tag}\n" if tag else "Tags:\n"
    return (f"---\n{tags}Source:\nStatus:\nNN:\nCanvas:\n---\n\n"
            f"# {nev}\n\n"
            "## Feladat\n\nÍrd ide a feladat leírását.\n\n"
            "## Bemenet és kimenet\n\nÍrd le a bemenet és a kimenet formátumát.\n\n"
            "## Tesztek\n\n"
            "A ⌘R ezeken futtatja a megoldást. Egy blokk egy teszt: `--- bemenet`, `--- kimenet` és a nem kötelező "
            "`--- idokorlat` (másodperc) szakasszal. A példát írd át vagy töröld.\n\n"
            "```teszt Példa\n--- bemenet\n3 4\n--- kimenet\n7\n```\n\n"
            f"## Megoldás\n\n![[{cpp_nev(nev)}]]\n")
