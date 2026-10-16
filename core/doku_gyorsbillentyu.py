"""A `docs/user/HOTKEYS.md` generált táblázata: a felület parancsregiszterének alapértelmezett billentyűi, forrásból olvasva.

A regiszter parancsai a `app/src` TypeScript- és Svelte-forrásaiban állnak (`billentyu: 'Mod+Shift+F'`); a tábla ugyanezt a
forrást olvassa (mint a `tests/test_dokumentacio.py` és a `app/tests/billentyu-utkozes.test.ts` kinyerője), a parancs nevét és
kategóriáját pedig az angol szótárból (`app/src/lib/i18n/en/*.json`) oldja fel — így a dokumentáció angol, és a regiszter
változásakor a teszt (`tests/test_felhasznaloi_doku.py`) elbukik, amíg a táblát újra nem generálják.

    python -m core.doku_gyorsbillentyu            kiírja a táblát (stdout)
    python -m core.doku_gyorsbillentyu --iras     újragenerálja a HOTKEYS.md `table:begin` … `table:end` közti részét
    python -m core.doku_gyorsbillentyu --ellenoriz   0, ha a fájl naprakész; 1, ha nem

Három alakot ismer fel: az objektum-literált (`{ id: '…', nev: tk('…'), kategoria: tk('…'), billentyu: '…' }`, egy- és többsorosat),
a szerkesztő `notion('id', tk('…'), …, { billentyu: '…' })` segédjét és a `formaz('id', tk('…'), '**', 'Mod+B')` segédjét, valamint a
fülszámozó `Mod+${i + 1}` sablont (⌘1–⌘9). Az olvashatatlan név (nincs angol szótár-bejegyzés) hiba, nem csendes magyar szöveg.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config

HAT_ELEJE = "<!-- table:begin -->"
HAT_VEGE = "<!-- table:end -->"

GLIF_MOD = (("Ctrl", "⌃"), ("Alt", "⌥"), ("Shift", "⇧"), ("Mod", "⌘"))     # a macOS sorrendje: ⌃⌥⇧⌘
GLIF_KULCS = {"ArrowRight": "→", "ArrowLeft": "←", "ArrowDown": "↓", "ArrowUp": "↑", "Enter": "↩"}

# egy billentyű-leírás ASCII alakja (`Mod+Shift+F`, `Mod+=`, `Mod+,`, `F6`); a `⌘B`-féle glifek és a sablonok kimaradnak
_BILLENTYU = r"([A-Za-z0-9+=,\-]+)"
BILLENTYU_RE = re.compile(r"\bbillentyu:\s*'" + _BILLENTYU + r"'")
FORMAZ_RE = re.compile(r"\bformaz\(\s*'([a-z0-9\-]+)'\s*,\s*(?:(?:tk|t)\(\s*'([^']+)'\s*\)|'([^']+)')\s*,\s*'[^']*'\s*,\s*'" + _BILLENTYU + r"'\s*\)")
NOTION_RE = re.compile(r"\bnotion\(\s*'([a-z0-9\-]+)'\s*,\s*(?:(?:tk|t)\(\s*'([^']+)'\s*\)|'([^']+)')")
ID_RE = re.compile(r"""\bid:\s*['"`]([a-z0-9.\-]+)['"`]""")
NEV_RE = re.compile(r"\bnev:\s*(?:(?:tk|t)\(\s*)?'([^']+)'")
KATEGORIA_RE = re.compile(r"\bkategoria:\s*(?:(?:tk|t)\(\s*)?'([^']+)'")
FUL_SZAM_RE = re.compile(r"billentyu:\s*`Mod\+\$\{i \+ 1\}`")
HELYI_SZERKESZTO_KATEGORIA = "Szerkesztő"     # a `notion(…)` és a `formaz(…)` segéd kategóriája a forrásban


@dataclass(frozen=True)
class Sor:
    billentyu: str        # `Mod+Shift+F`
    nev: str              # angol
    kategoria: str        # angol

    @property
    def glif(self) -> str:
        return billentyu_glif(self.billentyu)


def billentyu_glif(billentyu: str) -> str:
    """`Mod+Shift+F` → `⇧⌘F` (a billentyű-tábla alakja)."""
    *modositok, kulcs = billentyu.split("+")
    if not kulcs and modositok:        # `Mod++`: maga a `+` a kulcs
        kulcs = "+"
        modositok = [m for m in modositok if m]
    return "".join(g for nev, g in GLIF_MOD if nev in modositok) + GLIF_KULCS.get(kulcs, kulcs.upper() if len(kulcs) == 1 else kulcs)


def forras_mappa() -> Path:
    return config.os_root() / "app" / "src"


def szotar() -> dict[str, str]:
    """Az összes angol szótár-fájl egyesítve (kulcs: a forrásban álló magyar szöveg vagy a pontozott kulcs)."""
    ki: dict[str, str] = {}
    for f in sorted((forras_mappa() / "lib" / "i18n" / "en").glob("*.json")):
        ki.update(json.loads(f.read_text(encoding="utf-8")))
    return ki


class HianyzoFordites(ValueError):
    """Egy parancs neve vagy kategóriája nincs az angol szótárban: a dokumentáció nem mutathat magyar szöveget."""


def _angol(kulcs: str, szt: dict[str, str]) -> str:
    if kulcs in szt:
        return szt[kulcs]
    if re.search(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]", kulcs) or kulcs.islower() and "." in kulcs:
        raise HianyzoFordites(kulcs)
    return kulcs                       # pl. a `C++` kategória: nem fordítandó


def _forrasfajlok(mappa: Path | None = None) -> list[Path]:
    """A felület forrásfái (`app/src`, nem vault): a `.ts` és `.svelte` fájlok, mappánként bejárva."""
    ki: list[Path] = []
    for p in sorted((mappa or forras_mappa()).iterdir()):
        if p.is_dir():
            ki += _forrasfajlok(p)
        elif p.suffix in (".ts", ".svelte") and not p.name.endswith(".test.ts"):
            ki.append(p)
    return ki


def sorok(szt: dict[str, str] | None = None) -> list[Sor]:
    """A forrásban regisztrált parancsok alapértelmezett billentyűi (egy billentyű egyszer; ütközést a felület tesztje fog meg)."""
    szt = szotar() if szt is None else szt
    ki: dict[str, Sor] = {}
    for fajl in _forrasfajlok():
        for sor in sorok_szovegbol(fajl.read_text(encoding="utf-8"), szt):
            ki.setdefault(sor.billentyu, sor)
    return sorted(ki.values(), key=lambda s: (s.kategoria.lower(), s.nev.lower(), s.billentyu))


def sorok_szovegbol(szoveg: str, szt: dict[str, str]) -> list[Sor]:
    """Egy forrásfájl szövegének billentyű-sorai (a kinyerő maga; a `sorok` fájlonként hívja)."""
    ki: list[Sor] = []
    for m in BILLENTYU_RE.finditer(szoveg):
        id_elo, seged_elo = _utolso_elotte(ID_RE, szoveg, m.start()), _utolso_elotte(NOTION_RE, szoveg, m.start())
        # a billentyű a hozzá közelebbi kezdethez tartozik: az objektum `id:`-jéhez vagy a `notion(…)` hívás elejéhez
        seged_kozelebb = seged_elo is not None and (id_elo is None or seged_elo.end() > id_elo.end())
        sor = _segedhivas_sor(szoveg, m, szt) if seged_kozelebb else _objektum_sor(szoveg, m, szt)
        if sor is not None:
            ki.append(sor)
    for m in FORMAZ_RE.finditer(szoveg):
        nev = m.group(2) or m.group(3)
        ki.append(Sor(m.group(4), _angol(nev, szt), _angol(HELYI_SZERKESZTO_KATEGORIA, szt)))
    if FUL_SZAM_RE.search(szoveg):
        for i in range(1, 10):
            nev = szt["Utolsó fül"] if i == 9 else szt["{n}. fül"].replace("{n}", str(i))
            ki.append(Sor(f"Mod+{i}", nev, szt["Fül"]))
    return ki


def _utolso_elotte(minta: re.Pattern, szoveg: str, pozicio: int):
    talalat = None
    for m in minta.finditer(szoveg, 0, pozicio):
        talalat = m
    return talalat


def _objektum_sor(szoveg: str, m: re.Match, szt: dict[str, str]) -> Sor | None:
    """`{ id: …, nev: …, kategoria: …, billentyu: … }`: a legközelebbi megelőző `id:` az objektum eleje; a név és a kategória
    az `id:` és a következő `id:` között áll (a billentyű előtt vagy után)."""
    elozo = _utolso_elotte(ID_RE, szoveg, m.start())
    if elozo is None or m.start() - elozo.end() > 700:
        return None
    kovetkezo = ID_RE.search(szoveg, m.end())
    veg = min(kovetkezo.start() if kovetkezo else len(szoveg), m.end() + 400)
    tartomany = szoveg[elozo.end():veg]
    nev = NEV_RE.search(tartomany)
    if nev is None:
        return None
    kategoria = KATEGORIA_RE.search(tartomany)
    return Sor(m.group(1), _angol(nev.group(1), szt), _angol(kategoria.group(1), szt) if kategoria else "Other")


def _segedhivas_sor(szoveg: str, m: re.Match, szt: dict[str, str]) -> Sor | None:
    """`notion('id', tk('név'), …, { billentyu: '…' })`: a szerkesztő Live Preview-parancsai."""
    elozo = _utolso_elotte(NOTION_RE, szoveg, m.start())
    if elozo is None or m.start() - elozo.end() > 400:
        return None
    nev = elozo.group(2) or elozo.group(3)
    return Sor(m.group(1), _angol(nev, szt), _angol(HELYI_SZERKESZTO_KATEGORIA, szt))


def tabla(szt: dict[str, str] | None = None) -> str:
    """A generált Markdown: kategóriánként egy kis táblázat (kategória szerint ábécében, azon belül név szerint)."""
    ki: list[str] = []
    aktualis = None
    for sor in sorok(szt):
        if sor.kategoria != aktualis:
            if aktualis is not None:
                ki.append("")
            ki += [f"### {sor.kategoria}", "", "| Shortcut | Command |", "|---|---|"]
            aktualis = sor.kategoria
        ki.append(f"| {sor.glif} | {sor.nev} |")
    return "\n".join(ki) + "\n"


def beilleszt(dokumentum: str, uj_tabla: str) -> str:
    """A dokumentum `table:begin` … `table:end` közti részének cseréje (a jelölők megmaradnak)."""
    eleje, vege = dokumentum.find(HAT_ELEJE), dokumentum.find(HAT_VEGE)
    if eleje < 0 or vege < eleje:
        raise ValueError("a HOTKEYS.md-ből hiányzik a table:begin / table:end jelölő")
    return dokumentum[:eleje + len(HAT_ELEJE)] + "\n\n" + uj_tabla + "\n" + dokumentum[vege:]


def fajl() -> Path:
    return config.os_root() / "docs" / "user" / "HOTKEYS.md"


def naprakesz() -> bool:
    szoveg = fajl().read_text(encoding="utf-8")
    return beilleszt(szoveg, tabla()) == szoveg


def main(argv: list[str]) -> int:
    if "--iras" in argv:
        f = fajl()
        f.write_text(beilleszt(f.read_text(encoding="utf-8"), tabla()), encoding="utf-8")
        return 0
    if "--ellenoriz" in argv:
        return 0 if naprakesz() else 1
    sys.stdout.write(tabla())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
