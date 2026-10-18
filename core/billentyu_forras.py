"""Hotkey sources of truth, derived instead of typed (13-palette-02, 13-palette-01).

`config/billentyuk.json` is GENERATED from the two places where a chord is really owned:

* `natav` - the chords the native macOS menu binds (`shell/Sources/AppController.swift`: every `keyEquivalent:` with its
  `keyEquivalentModifierMask`). macOS dispatches a menu key equivalent before the web view sees the key, so a registry command
  assigned to one of them would be saved and then never fire. The web validator (`app/src/lib/parancsok/regiszter.ts`) and the
  settings writer (`core/termek_beallitasok.py`) both read this table; `tulajdonos` is the registry command the menu item itself
  runs (`Mod+,` -> `beallitasok.megnyit`), the only command that may keep that chord.
* `alap` - the default chord of every registry command, read from the `app/src` sources (the same technique as
  `core/doku_gyorsbillentyu.py` and `app/tests/billentyu-utkozes.test.ts`). The Obsidian hotkey import uses it to refuse a chord
  that would collide with a Manifold default (the packaged install has no `app/src`, hence the shipped copy).

    python -m core.billentyu_forras             prints the JSON
    python -m core.billentyu_forras --iras      rewrites config/billentyuk.json
    python -m core.billentyu_forras --ellenoriz exit 0 when the file is current, 1 when it is stale

`tests/test_billentyu_forras.py` fails while the file is stale, so a new menu chord or registry default cannot be forgotten.
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from . import config

_MOD_SORREND = (("mod", "Mod"), ("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift"))
_MOD_NEV = {"mod": "mod", "cmd": "mod", "meta": "mod", "ctrl": "ctrl", "control": "ctrl", "alt": "alt", "opt": "alt",
            "option": "alt", "shift": "shift"}
_KULCS_NEV = {"esc": "Escape", "escape": "Escape", "enter": "Enter", "return": "Enter", "tab": "Tab", "space": "Space",
              "left": "ArrowLeft", "right": "ArrowRight", "up": "ArrowUp", "down": "ArrowDown", "arrowleft": "ArrowLeft",
              "arrowright": "ArrowRight", "arrowup": "ArrowUp", "arrowdown": "ArrowDown", "backspace": "Backspace",
              "delete": "Delete", "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown"}


def kanonikus(leiras: str) -> str:
    """`cmd+shift+O` -> `Mod+Shift+o` (the registry key form of `app/src/lib/parancsok/billentyuk.ts`). ValueError when the
    description is not a chord."""
    reszek = [r.strip() for r in str(leiras).split("+")]
    modok: set[str] = set()
    for r in reszek[:-1]:
        m = _MOD_NEV.get(r.lower())
        if m is None:
            raise ValueError(f"unknown modifier: {r}")
        modok.add(m)
    kulcs = reszek[-1]
    kis = kulcs.lower()
    if kis in _KULCS_NEV:
        kulcs = _KULCS_NEV[kis]
    elif re.fullmatch(r"f\d{1,2}", kis):
        kulcs = kis.upper()
    elif len(kulcs) == 1:
        kulcs = kis
    else:
        raise ValueError(f"unknown key: {kulcs}")
    return "+".join([nev for kod, nev in _MOD_SORREND if kod in modok] + [kulcs])


def akkord_ervenyes(kanon: str) -> bool:
    """A chord a registry command may take: a modifier (Mod/Ctrl/Alt) or an F-key - never a bare key (mirrors `regiszter.ts`)."""
    reszek = kanon.split("+")
    return (any(m in reszek[:-1] for m in ("Mod", "Ctrl", "Alt")) or bool(re.fullmatch(r"F\d{1,2}", reszek[-1])))


# ------------------------------------------------------------------ the native menu (Swift)

_SWIFT_BILLENTYU = re.compile(r'keyEquivalent:\s*"([^"\\]+)"')
_SWIFT_CIM = re.compile(r'(?:withTitle|title):\s*L\(\s*"((?:[^"\\]|\\.)*)"')
_SWIFT_VALTOZO = re.compile(r"^\s*(?:let|var)\s+(\w+)\s*=")
_SWIFT_MASZK = re.compile(r"(\w+)\.keyEquivalentModifierMask\s*=\s*\[([^\]]*)\]")
_SWIFT_REPR = re.compile(r'(\w+)\.representedObject\s*=\s*"([a-z0-9.\-]+)"')
_SWIFT_MOD = {"command": "mod", "option": "alt", "shift": "shift", "control": "ctrl"}


def _swift_forras() -> Path:
    return config.os_root() / "shell" / "Sources" / "AppController.swift"


def _angol_cim(cim: str) -> str:
    """The English title of a menu item (`shell/Resources/en.lproj/Localizable.strings`), the Hungarian key when there is none."""
    ut = config.os_root() / "shell" / "Resources" / "en.lproj" / "Localizable.strings"
    try:
        szoveg = ut.read_text(encoding="utf-8")
    except OSError:
        return cim
    for k, v in re.findall(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', szoveg):
        if json.loads(f'"{k}"') == cim:
            return json.loads(f'"{v}"')
    return cim


def natav_menu(swift: str | None = None) -> list[dict]:
    """The chords of the native menu: `[{akkord, cim, tulajdonos?}]`, sorted by chord. Without `swift` the shell source is read."""
    sorok = (swift if swift is not None else _swift_forras().read_text(encoding="utf-8")).splitlines()
    ki: dict[str, dict] = {}
    for i, sor in enumerate(sorok):
        if sor.lstrip().startswith("//"):
            continue
        m = _SWIFT_BILLENTYU.search(sor)
        if not m:
            continue
        valtozo = (_SWIFT_VALTOZO.match(sor) or [None, None])[1]
        modok = {"mod"}
        tulajdonos = None
        if valtozo:
            for kovetkezo in sorok[i + 1:i + 8]:
                mk = _SWIFT_MASZK.search(kovetkezo)
                if mk and mk.group(1) == valtozo:
                    modok = {_SWIFT_MOD[x.strip().lstrip(".")] for x in mk.group(2).split(",") if x.strip().lstrip(".") in _SWIFT_MOD}
                mr = _SWIFT_REPR.search(kovetkezo)
                if mr and mr.group(1) == valtozo:
                    tulajdonos = mr.group(2)
        cim = _SWIFT_CIM.search(sor)
        akkord = kanonikus("+".join([nev for kod, nev in _MOD_SORREND if kod in modok] + [m.group(1)]))
        elem = {"akkord": akkord, "cim": _angol_cim(json.loads(f'"{cim.group(1)}"')) if cim else ""}
        if tulajdonos:
            elem["tulajdonos"] = tulajdonos
        ki.setdefault(akkord, elem)
    return sorted(ki.values(), key=lambda e: e["akkord"].lower())


# ------------------------------------------------------------------ registry defaults (TypeScript / Svelte sources)

_ID = re.compile(r"""\bid:\s*['"`]([a-z0-9.\-]+)['"`]""")
_NOTION = re.compile(r"\bnotion\(\s*'([a-z0-9\-]+)'")
_BILLENTYU = re.compile(r"\bbillentyu:\s*'([A-Za-z0-9+=,\-]+)'")
_FORMAZ = re.compile(r"\bformaz\(\s*'([a-z0-9\-]+)'\s*,[^\n]*?,\s*'[^']*'\s*,\s*'([A-Za-z0-9+=,\-]+)'\s*\)")
_FUL_SZAM = re.compile(r"id:\s*`ful\.n\$\{i \+ 1\}`[\s\S]{0,300}?billentyu:\s*`Mod\+\$\{i \+ 1\}`")


def _utolso(minta: re.Pattern, szoveg: str, pozicio: int):
    talalat = None
    for m in minta.finditer(szoveg, 0, pozicio):
        talalat = m
    return talalat


def alap_szovegbol(szoveg: str) -> dict[str, str]:
    """`{command id: canonical default chord}` from one source file's text (object literal, `notion(...)` helper, `formaz(...)`
    helper and the numbered tab commands)."""
    ki: dict[str, str] = {}
    for m in _BILLENTYU.finditer(szoveg):
        elozo_id, elozo_notion = _utolso(_ID, szoveg, m.start()), _utolso(_NOTION, szoveg, m.start())
        if elozo_notion is not None and (elozo_id is None or elozo_notion.end() > elozo_id.end()):
            if m.start() - elozo_notion.end() > 400:
                continue
            azonosito = f"szerkeszto.{elozo_notion.group(1)}"
        else:
            if elozo_id is None or m.start() - elozo_id.end() > 700:
                continue
            azonosito = elozo_id.group(1)
        ki.setdefault(azonosito, kanonikus(m.group(1)))
    for m in _FORMAZ.finditer(szoveg):
        ki.setdefault(f"szerkeszto.{m.group(1)}", kanonikus(m.group(2)))
    if _FUL_SZAM.search(szoveg):
        for i in range(1, 10):
            ki.setdefault(f"ful.n{i}", f"Mod+{i}")
    return ki


def _forrasfajlok(mappa: Path) -> list[Path]:
    ki: list[Path] = []
    for p in sorted(mappa.iterdir()):
        if p.is_dir():
            ki += _forrasfajlok(p)
        elif p.suffix in (".ts", ".svelte") and not p.name.endswith((".test.ts", ".d.ts")):
            ki.append(p)
    return ki


def alap_billentyuk(mappa: Path | None = None) -> dict[str, str]:
    ki: dict[str, str] = {}
    for fajl in _forrasfajlok(mappa or config.os_root() / "app" / "src"):
        for azonosito, akkord in alap_szovegbol(fajl.read_text(encoding="utf-8")).items():
            ki.setdefault(azonosito, akkord)
    return dict(sorted(ki.items()))


# ------------------------------------------------------------------ the generated file

def fajl() -> Path:
    return config.os_root() / "config" / "billentyuk.json"


def general() -> str:
    adat = {"_leiras": "GENERATED by `python -m core.billentyu_forras --iras`; do not edit. natav = chords of the native macOS "
                       "menu (shell/Sources/AppController.swift); alap = registry default chords (app/src).",
            "natav": natav_menu(), "alap": alap_billentyuk()}
    return json.dumps(adat, ensure_ascii=False, indent=2) + "\n"


def naprakesz() -> bool:
    try:
        return fajl().read_text(encoding="utf-8") == general()
    except OSError:
        return False


@lru_cache(maxsize=1)
def _tabla_cache() -> tuple:
    adat = json.loads(fajl().read_text(encoding="utf-8"))
    return (tuple(adat.get("natav") or ()), dict(adat.get("alap") or {}))


def tabla() -> dict:
    """The shipped table at runtime: `{natav: [...], alap: {...}}`."""
    natav, alap = _tabla_cache()
    return {"natav": list(natav), "alap": dict(alap)}


def fenntartott() -> dict[str, str | None]:
    """`{canonical chord: owner command id or None}` - the chords no registry command may be assigned (except the owner)."""
    return {e["akkord"]: e.get("tulajdonos") for e in tabla()["natav"]}


def main(argv: list[str]) -> int:
    if "--iras" in argv:
        fajl().write_text(general(), encoding="utf-8")
        return 0
    if "--ellenoriz" in argv:
        return 0 if naprakesz() else 1
    sys.stdout.write(general())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
