"""A beépített felhasználói dokumentáció (16 oldal, `docs/user/*.md`): jegyzék, olvasás, „Learn more” célok, másolás munkatérbe.

A forrás közönséges Markdown a kódfában (`docs/user/`): a repóban szöveg, a munkatér-létrehozáskor (demo) másolat. A mappa a
`config.os_root()` alól oldódik fel (a `MOS_ROOT` felülírja) — nincs beégetett út. A forrásnyelv angol; a dokumentáció a
felhasználónak szól, ezért nem hivatkozik fejlesztői azonosítóra (a `tests/test_felhasznaloi_doku.py` őrzi).

- `OLDALAK` — a 16 oldal rendezett jegyzéke (azonosító, fájl, cím); a fájlok és a jegyzék egyezését a teszt őrzi.
- `learn_more(tema)` — a „Learn more” hivatkozás célja: `(fájl, horgony)`; a Health-ellenőrzések (`health.<kod>`), a beállítási
  szakaszok és a nagy témák kulcsai a `LEARN_MORE`-ban vannak, a horgonyok létezését a teszt ellenőrzi.
- `munkater_fajlok()` — az oldalak munkatér-alakja `{út: bájtok}` (a demo-generátor ezt olvaszthatja a tartalmába); `masol_munkaterbe(cel)` — az oldalak másolata egy munkatér mappájába (a demo ezt hívja a létrehozáskor): a fájlnév az oldal
  címe, a belső `[szöveg](FÁJL.md#horgony)` hivatkozások wikilinkké (`[[Cím#Fejezet|szöveg]]`) alakulnak, a generálás HTML-megjegyzései
  kimaradnak. Alapból **nem ír felül** semmit (a felhasználó szerkesztései megmaradnak); nem gépi írás a futó munkatéren, hanem
  létrehozáskori kezdőtartalom (mint az `indito._demo` induló jegyzetei).

CLI: `python -m core.doku lista|learn <tema>|masol <mappa>`.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import config, tartos


@dataclass(frozen=True)
class Oldal:
    azonosito: str      # `getting-started`
    fajl: str           # `GETTING-STARTED.md`
    cim: str            # az oldal H1-je


OLDALAK: tuple[Oldal, ...] = (
    Oldal("getting-started", "GETTING-STARTED.md", "Getting started"),
    Oldal("workspaces", "WORKSPACES.md", "Workspaces"),
    Oldal("notes", "NOTES-AND-EDITING.md", "Notes & editing"),
    Oldal("links", "LINKS-AND-BACKLINKS.md", "Links & backlinks"),
    Oldal("properties", "PROPERTIES-AND-TAGS.md", "Properties & tags"),
    Oldal("search", "SEARCH.md", "Search"),
    Oldal("files", "FILES-AND-EXPLORER.md", "Files & explorer"),
    Oldal("layouts", "LAYOUTS-AND-TABS.md", "Layouts & tabs"),
    Oldal("hotkeys", "HOTKEYS.md", "Hotkeys"),
    Oldal("settings", "SETTINGS-AND-MODULES.md", "Settings & modules"),
    Oldal("ai", "AI-AND-MODELS.md", "AI & models"),
    Oldal("privacy", "PRIVACY-AND-DATA.md", "Privacy & data"),
    Oldal("health", "HEALTH-AND-TROUBLESHOOTING.md", "Health & troubleshooting"),
    Oldal("import", "IMPORT-AND-MIGRATION.md", "Import & migration"),
    Oldal("code", "CODE-WORKBENCH.md", "Code workbench"),
    Oldal("demo", "DEMO-WORKSPACE.md", "Demo workspace"),
)

# A „Learn more” célok: téma → (oldal-azonosító, horgony). A Health-ellenőrzések kódja a `core/egeszseg.py`-é.
LEARN_MORE: dict[str, tuple[str, str]] = {
    "health": ("health", "what-the-checks-do"),
    "health.index": ("health", "search-index"),
    "health.pillanatkep": ("health", "snapshots"),
    "health.zarak": ("health", "locks"),
    "health.lemezhely": ("health", "disk-space"),
    "health.modellek": ("health", "ai-models"),
    "health.munkater": ("health", "workspace"),
    "health.folyamatok": ("health", "background-services"),
    "health.telepites": ("health", "installation"),
    "privacy": ("privacy", "where-your-data-lives"),
    "privacy.network": ("privacy", "network"),
    "privacy.assistant": ("privacy", "assistant-memory"),
    "privacy.tracker": ("privacy", "usage-statistics"),
    "privacy.permissions": ("privacy", "system-permissions"),
    "models": ("ai", "trial-and-calibrated-models"),
    "models.calibration": ("ai", "measuring-a-model"),
    "settings": ("settings", "settings-sections"),
    "settings.modules": ("settings", "modules"),
    "hotkeys": ("hotkeys", "changing-a-shortcut"),
    "import": ("import", "opening-an-existing-folder"),
    "import.obsidian": ("import", "obsidian-vaults"),
    "demo": ("demo", "what-is-in-it"),
    "code": ("code", "checking-a-solution"),
}


def mappa() -> Path:
    """A felhasználói dokumentáció mappája a kódfában (`{os}/docs/user`)."""
    return config.os_root() / "docs" / "user"


def oldal(azonosito: str) -> Oldal:
    for o in OLDALAK:
        if o.azonosito == azonosito or o.fajl == azonosito:
            return o
    raise KeyError(azonosito)


def olvas(azonosito: str) -> str:
    return (mappa() / oldal(azonosito).fajl).read_text(encoding="utf-8")


def horgony(fejlec: str) -> str:
    """A fejléc horgonya (GitHub-szerű): kisbetű, az írásjelek elhagyva, a szóköz kötőjel (`Search index` → `search-index`)."""
    s = unicodedata.normalize("NFKD", fejlec).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 \-]", "", s)
    return re.sub(r"\s", "-", s.strip())


FEJLEC_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)


def fejlecek(szoveg: str) -> dict[str, str]:
    """A dokumentum fejlécei: horgony → fejléc-szöveg (a kódblokkokon belüli sorok nem fejlécek)."""
    ki: dict[str, str] = {}
    for m in FEJLEC_RE.finditer(_kod_nelkul(szoveg)):
        ki.setdefault(horgony(m.group(2)), m.group(2))
    return ki


def _kod_nelkul(szoveg: str) -> str:
    return re.sub(r"^(```|~~~).*?^\1[ \t]*$", "", szoveg, flags=re.M | re.S)


def learn_more(tema: str) -> tuple[str, str]:
    """A téma „Learn more” célja: `(fájl, horgony)`; ismeretlen téma `KeyError`."""
    azonosito, hely = LEARN_MORE[tema]
    return oldal(azonosito).fajl, hely


def szakasz(azonosito: str, hely: str) -> tuple[str, str]:
    """Az oldal egy szakasza a horgony szerint: `(fejléc-szöveg, Markdown)`. A szakasz a fejléc sora után kezdődik, és a következő
    azonos vagy magasabb szintű fejlécig tart (az alszakaszok benne vannak); a kódblokkon belüli sor nem fejléc, a HTML-megjegyzés
    kimarad. Ismeretlen oldal vagy horgony: `KeyError`."""
    szoveg = olvas(azonosito)
    sorok = szoveg.split("\n")
    benne, kezdet, szint, fejlec = False, None, 0, ""
    for i, sor in enumerate(sorok + [None]):
        if sor is not None and re.match(r"^(```|~~~)", sor):
            benne = not benne
            continue
        m = None if benne or sor is None else re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", sor)
        if kezdet is None:
            if m and horgony(m.group(2)) == hely:
                kezdet, szint, fejlec = i + 1, len(m.group(1)), m.group(2)
        elif sor is None or (m and len(m.group(1)) <= szint):
            tor = re.sub(r"<!--.*?-->[ \t]*\n?", "", "\n".join(sorok[kezdet:i]), flags=re.S)
            return fejlec, tor.strip("\n")
    raise KeyError(hely)


MUNKATER_MAPPA = "Manifold Guide"      # a mappa neve a munkatérben (a demo ide teszi az oldalakat)


def munkater_ut(oldal_azonosito: str) -> str:
    """Az oldal munkatér-relatív útja, ha a munkatér tartalmazza az útmutatót (a demo másolja be): `Manifold Guide/<Cím>.md`."""
    return f"{MUNKATER_MAPPA}/{fajlnev(oldal(oldal_azonosito).cim)}"


def learn_valasz(tema: str, vault=None) -> dict:
    """A „Learn more” kérés válasza: az oldal, a horgony és a szakasz Markdown-szövege (a felület ezt mutatja), valamint — ha a
    munkatér tartalmazza az útmutatót — a jegyzet útja (`munkater_ut`), amit a felület fülben nyithat. Ismeretlen téma: `KeyError`."""
    azonosito, hely = LEARN_MORE[tema]
    o = oldal(azonosito)
    fejlec, tartalom = szakasz(azonosito, hely)
    ut = munkater_ut(azonosito)
    try:
        van = bool(vault is not None and vault._abs(ut).is_file())
    except Exception:                                   # noqa: BLE001 — a munkatér nem elérhető: nincs munkatér-másolat
        van = False
    return {"tema": tema, "oldal": {"azonosito": o.azonosito, "fajl": o.fajl, "cim": o.cim}, "horgony": hely, "fejlec": fejlec,
            "szakasz": tartalom, "munkater_ut": ut if van else None}


def utvonalak(r) -> None:
    """`GET /api/doku/learn?tema=` — a „Learn more” hivatkozás célja (csak olvas)."""
    from .utvonalak import HttpError

    def learn(k):
        tema = k.q.get("tema")
        if not isinstance(tema, str) or not tema:
            raise HttpError(400, "The `tema` parameter is missing.", kod="doku.hianyzik_tema")
        if tema not in LEARN_MORE:
            raise HttpError(404, f"No such topic: {tema}", kod="doku.ismeretlen_tema", param={"tema": tema[:80]})
        try:
            return learn_valasz(tema, getattr(k.app, "vault", None))
        except (KeyError, OSError) as exc:
            raise HttpError(404, "The guide page is not installed.", kod="doku.nincs_oldal", param={"tema": tema}) from exc

    r.get("/api/doku/learn", learn)


def fajlnev(cim: str) -> str:
    """Az oldal fájlneve a munkatérben: a cím (az `&` szó lesz, hogy a fájl- és linknév minden eszközben biztonságos legyen)."""
    return cim.replace("&", "and") + ".md"


def munkater_szoveg(szoveg: str) -> str:
    """Az oldal munkatér-alakja: HTML-megjegyzések nélkül, a belső Markdown-linkek wikilinkként (táblázatsorban a `|` védett)."""
    szoveg = re.sub(r"<!--.*?-->[ \t]*\n?", "", szoveg, flags=re.S)
    fajlok = {o.fajl: o for o in OLDALAK}
    fejlec_tar = {o.fajl: fejlecek((mappa() / o.fajl).read_text(encoding="utf-8")) for o in OLDALAK}

    def atalakit(sor: str) -> str:
        cso = "\\|" if sor.lstrip().startswith("|") else "|"

        def csere(m: re.Match) -> str:
            szoveg_, fajl, hely = m.group(1), m.group(2), m.group(3)
            o = fajlok.get(fajl)
            if o is None:
                return m.group(0)
            cel = fajlnev(o.cim)[:-3]
            if hely:
                fej = fejlec_tar[fajl].get(hely)
                if fej is not None:
                    cel += "#" + fej
            return f"[[{cel}{cso}{szoveg_}]]" if szoveg_ != cel else f"[[{cel}]]"

        return re.sub(r"\[([^\]\n]+)\]\(([A-Z][A-Z\-]*\.md)(?:#([^)\s]+))?\)", csere, sor)

    return "\n".join(atalakit(sor) for sor in szoveg.split("\n"))


def munkater_fajlok(mappa_nev: str = MUNKATER_MAPPA) -> dict[str, bytes]:
    """Az oldalak munkatér-alakja `{munkatér-relatív út: bájtok}` — a demo-generátor ezt olvasztja a saját tartalmába (így a
    kivonata, az ellenőrzött írása és a reset is kiterjed rájuk), a `masol_munkaterbe` pedig ezt írja ki. Tiszta és determinisztikus."""
    ki: dict[str, bytes] = {}
    for o in OLDALAK:
        szoveg = munkater_szoveg((mappa() / o.fajl).read_text(encoding="utf-8"))
        ki[f"{mappa_nev}/{fajlnev(o.cim)}" if mappa_nev else fajlnev(o.cim)] = szoveg.encode("utf-8")
    return ki


def masol_munkaterbe(cel: Path, *, felulir: bool = False) -> list[Path]:
    """Az összes oldal másolata a `cel` mappába (létrejön). Alapból a már meglévő fájlt békén hagyja (a felhasználó szerkesztése
    megmarad); `felulir=True` atomi cserét végez (a „reset” folyamat használja). A visszatérés: az írt fájlok útjai."""
    cel = Path(cel)
    cel.mkdir(parents=True, exist_ok=True)
    irt: list[Path] = []
    for nev, adat in munkater_fajlok("").items():
        ut = cel / nev
        try:
            if felulir:
                tartos.atomi_ir(ut, adat)
            else:
                tartos.kizaro_ir(ut, adat)
        except FileExistsError:
            continue
        irt.append(ut)
    return irt


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "lista":
        for o in OLDALAK:
            print(f"{o.fajl}\t{o.cim}")
        return 0
    if argv[0] == "learn" and len(argv) == 2:
        fajl, hely = learn_more(argv[1])
        print(f"{fajl}#{hely}")
        return 0
    if argv[0] == "masol" and len(argv) == 2:
        for ut in masol_munkaterbe(Path(argv[1])):
            print(ut)
        return 0
    print("használat: python -m core.doku lista | learn <téma> | masol <mappa>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
