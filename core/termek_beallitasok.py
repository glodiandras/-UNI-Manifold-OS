"""F5: one validated, conflict-aware settings writer for Setup and Settings.

Only configuration is written. Workspace identity, pinned roots, notes and
Obsidian files are never changed by this API.
"""
from __future__ import annotations

import copy
import datetime
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import tomllib
from contextlib import contextmanager
from pathlib import Path

from . import config, csatolmany, fejleszto, tartos, workspace
from .utvonalak import HttpError

MODULOK = tuple("hivatkozasok vazlat tulajdonsagok gyorsvalto kereses perjel cimkek sablonok napi canvas bazis graf pdf media kartya kviz osszefoglalas matek kod fuzet video kerdezz asszisztens naptar felkeszultseg tracker".split())
ALAP = {
    "altalanos": {"nyelv": "auto", "inditas": "utolso"},
    "szerkeszto": {"mod": "elo", "olvashato_szelesseg": True, "helyesiras": True, "tab_meret": 2, "perjel": True},
    "fajlok": {"uj_mappa": "", "csatolmany_mappa": "", "sablon_mappa": "_Template", "napi_ut": "[Daily]/YYYY-MM-DD", "link_formatum": "rovid", "wikilinkek": True},
    "megjelenes": {"tema": "rendszer", "betumeret": 16, "csend": False},
    "modulok": dict.fromkeys(MODULOK, True),
    "adatvedelem": {"asszisztens": True, "tracker": True, "ertesitesek": True, "naptar": False},
    "billentyuk": {}, "setup": {"kesz": False, "elmeny": "egyeni"},
    "fejleszto": {"mod": False},
}
VALASZTEK = {
    ("altalanos", "nyelv"): ("auto", "hu", "en"), ("altalanos", "inditas"): ("utolso", "valaszto"),
    ("szerkeszto", "mod"): ("elo", "forras"), ("fajlok", "link_formatum"): ("rovid", "relativ", "abszolut"),
    ("megjelenes", "tema"): ("rendszer", "vilagos", "sotet"),
    ("setup", "elmeny"): ("diak", "tudasmunka", "fejleszto", "kutato", "egyeni"),
}


def egyesit(alap: dict, uj: dict) -> dict:
    ki = copy.deepcopy(alap)
    for k, v in uj.items():
        ki[k] = egyesit(ki[k], v) if isinstance(v, dict) and isinstance(ki.get(k), dict) else copy.deepcopy(v)
    return ki


def _hiba(kod="beallitas.hibas", *, kulcs=""):
    szoveg = {"beallitas.hibas": "This setting is not valid. Check its value and try again.",
              "beallitas.utkozes": "Settings changed elsewhere. Reload them before saving again.",
              "beallitas.symlink": "The settings location is not safe to write. Reopen this workspace.",
              "beallitas.munkater_csere": "The workspace changed on disk. Reopen it before saving settings."}[kod]
    raise HttpError(409 if kod != "beallitas.hibas" else 400, szoveg, kod=kod, param={"kulcs": kulcs})


def ellenoriz(valtozas) -> dict:
    if not isinstance(valtozas, dict) or not valtozas:
        _hiba()
    ki = copy.deepcopy(valtozas)
    for tabla, ertekek in ki.items():
        if tabla not in ALAP or not isinstance(ertekek, dict):
            _hiba(kulcs=str(tabla))
        if len(ertekek) > 500:
            _hiba(kulcs=tabla)
        for kulcs, ertek in ertekek.items():
            nev = f"{tabla}.{kulcs}"
            if tabla == "billentyuk":
                if not isinstance(kulcs, str) or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", kulcs) \
                        or not isinstance(ertek, str) or len(ertek) > 100 or re.search(r"[\x00-\x1f\x7f]", ertek):
                    _hiba(kulcs=nev)
                if ertek:
                    reszek = [r.strip().lower() for r in ertek.split("+")]
                    modositok = {"mod": "mod", "cmd": "mod", "meta": "mod", "ctrl": "ctrl",
                                 "alt": "alt", "opt": "alt", "shift": "shift"}
                    if any(r not in modositok for r in reszek[:-1]):
                        _hiba(kulcs=nev)
                    modok = {modositok[r] for r in reszek[:-1]}
                    gomb = reszek[-1]
                    nevek = {"esc", "escape", "enter", "tab", "space", "left", "right", "up", "down",
                             "arrowleft", "arrowright", "arrowup", "arrowdown", "backspace", "delete", "home", "end", "pageup", "pagedown"}
                    f_gomb = bool(re.fullmatch(r"f\d{1,2}", gomb))
                    if not (len(gomb) == 1 or gomb in nevek or f_gomb) or not (modok & {"mod", "ctrl", "alt"} or f_gomb):
                        _hiba(kulcs=nev)
                    if (modok == {"mod"} and gomb == "," and kulcs != "beallitasok.megnyit") or (modok == {"mod", "shift"} and gomb == "o"):
                        _hiba(kulcs=nev)
                if kulcs == "beallitasok.megnyit" and ertek != "Mod+,":
                    _hiba(kulcs=nev)
                continue
            if kulcs not in ALAP[tabla] or type(ertek) is not type(ALAP[tabla][kulcs]):
                _hiba(kulcs=nev)
            if (tabla, kulcs) in VALASZTEK and ertek not in VALASZTEK[tabla, kulcs]:
                _hiba(kulcs=nev)
            if tabla == "szerkeszto" and kulcs == "tab_meret" and not 1 <= ertek <= 8:
                _hiba(kulcs=nev)
            if tabla == "megjelenes" and kulcs == "betumeret" and not 12 <= ertek <= 28:
                _hiba(kulcs=nev)
            if isinstance(ertek, str) and (len(ertek) > 1000 or re.search(r"[\x00-\x1f\x7f]", ertek)):
                _hiba(kulcs=nev)
            if tabla == "fajlok" and kulcs not in ("link_formatum", "wikilinkek"):
                ellenorzendo = ertek
                if kulcs == "uj_mappa" and ertek == ".":
                    ellenorzendo = ""
                if kulcs == "csatolmany_mappa" and (ertek == "." or ertek.startswith("./")):
                    ellenorzendo = ertek[2:] if ertek != "." else ""
                if "{" in ertek or "}" in ertek or "\\" in ertek or config._ut_hiba(ellenorzendo):
                    _hiba(kulcs=nev)
                if kulcs == "napi_ut" and (not ertek.strip() or ertek.lower().endswith(".md")):
                    _hiba(kulcs=nev)
                if kulcs == "sablon_mappa" and not ertek.strip():
                    _hiba(kulcs=nev)
    return ki


def cel(cfg) -> tuple[Path, str]:
    if cfg.elrendezes == "termek":
        config.munkater_mappa_ellenoriz(cfg.path("vault"), cfg.path("workspace"))
        p = cfg.path("workspace") / workspace.WS_TOML
        if workspace.toml_azonosito(p) != cfg.workspace_id:
            _hiba("beallitas.munkater_csere")
        return p, "munkater"
    p = (cfg.data.get("_meta") or {}).get("settings")
    return Path(p) if p else cfg.path("install") / "settings.toml", "telepites_hordozhato"


def _nyers(p: Path) -> bytes:
    if p.is_symlink() or p.parent.is_symlink():
        _hiba("beallitas.symlink")
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return b""
    with os.fdopen(fd, "rb") as fh:
        adat = fh.read(config.MAX_TOML_BAJT + 1)
    if len(adat) > config.MAX_TOML_BAJT:
        _hiba()
    return adat


def _adat(nyers: bytes) -> dict:
    try:
        return tomllib.loads(nyers.decode("utf-8"))
    except (ValueError, UnicodeError):
        _hiba()


def _ertek(cfg, lemez: dict) -> dict:
    ki = copy.deepcopy(ALAP)
    try:
        kapcsolok = json.loads((cfg.path("state") / "kapcsolok.json").read_text())
        for k in ("asszisztens", "tracker"):
            if type(kapcsolok.get(k)) is bool:
                ki["adatvedelem"][k] = kapcsolok[k]
    except (OSError, ValueError, config.ConfigError, AttributeError):
        pass
    ki["fajlok"]["sablon_mappa"] = cfg.section("sablon").get("mappa", "_Template")
    ki["fajlok"]["napi_ut"] = cfg.section("naplo").get("ut", "[Daily]/YYYY-MM-DD")
    if "vault" in cfg.utak:
        o = workspace._obsidian_beallitasok(cfg.path("vault")).get("app", {})
        ki["fajlok"]["uj_mappa"] = (o.get("newFileFolderPath", "") if o.get("newFileLocation") == "folder"
                                       else "." if o.get("newFileLocation") == "current" else "")
        ki["fajlok"]["csatolmany_mappa"] = csatolmany.beallitas(cfg.path("vault"))
        if ki["fajlok"]["csatolmany_mappa"] == "/":
            ki["fajlok"]["csatolmany_mappa"] = ""
    nyelv = cfg.section("workspace").get("nyelv")
    if nyelv in ("hu", "en"):
        ki["altalanos"]["nyelv"] = nyelv
    # Only actual user overrides, not S-layer defaults, override imported conventions.
    for tabla, sor in cfg.section("beallitasok").items():
        if tabla not in ALAP or not isinstance(sor, dict):
            continue
        for k, v in sor.items():
            if cfg.forras("beallitasok", tabla, k) != "os":
                ki[tabla][k] = copy.deepcopy(v)
    regi = lemez.get("beallitasok", {})
    if regi:
        ellenoriz(regi)
        ki = egyesit(ki, regi)
    return ki


def _valasz(cfg, p: Path, nyers: bytes) -> dict:
    ertek = _ertek(cfg, _adat(nyers))
    kenyszer = fejleszto.nezet_kenyszer()        # az indító ⌥-kattintása: ebben a munkamenetben be, a mentett érték változatlan
    if kenyszer:
        ertek["fejleszto"]["mod"] = True
    return {**({"fejleszto_kenyszer": True} if kenyszer else {}), "verzio": 1, "rev": hashlib.sha256(nyers).hexdigest(), "ertek": ertek,
            "munkater": {"id": cfg.workspace_id or "", "nev": cfg.section("workspace").get("nev") or cfg.path("vault").name,
                          "vault": str(cfg.path("vault"))},
            "setup_szukseges": cfg.elrendezes == "termek" and not ertek["setup"]["kesz"], "ujrainditas": []}


def olvas(cfg) -> dict:
    p, _ = cel(cfg)
    return _valasz(cfg, p, _nyers(p))


def _toml_ertek(v) -> str:
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")
        return repr(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, list):
        return "[" + ", ".join(_toml_ertek(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{json.dumps(k, ensure_ascii=False)} = {_toml_ertek(x)}" for k, x in v.items()) + " }"
    raise ValueError("Unsupported TOML value")


def toml_ir(d: dict) -> str:
    sorok = []
    def kulcs(k):
        # Keep ordinary keys bare: workspace's byte-preserving ID replacement
        # uses the established `id = ...` line. Dotted hotkey IDs stay quoted.
        return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)
    def tabla(adat, ut=()):
        if ut:
            sorok.extend(["", "[" + ".".join(kulcs(k) for k in ut) + "]"])
        for k, v in adat.items():
            if not isinstance(v, dict):
                sorok.append(f"{kulcs(k)} = {_toml_ertek(v)}")
        for k, v in adat.items():
            if isinstance(v, dict):
                tabla(v, (*ut, k))
    tabla(d)
    return "\n".join(sorok).lstrip("\n") + "\n"


@contextmanager
def _zar(p: Path):
    if p.parent.is_symlink():
        _hiba("beallitas.symlink")
    p.parent.mkdir(parents=True, exist_ok=True)
    # Pin the directory itself: O_NOFOLLOW on the lock alone would still follow a
    # parent replaced by a symlink between the earlier check and the open.
    try:
        mappa_fd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            _hiba("beallitas.symlink")
        raise
    try:
        fd = os.open(".beallitasok.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=mappa_fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)
    finally:
        os.close(mappa_fd)


def ir(cfg, rev, valtozas) -> dict:
    valtozas = ellenoriz(valtozas)
    if not isinstance(rev, str):
        _hiba()
    p, reteg = cel(cfg)
    with _zar(p):
        cel(cfg)  # recheck identity and links under the writer lock
        nyers = _nyers(p)
        if hashlib.sha256(nyers).hexdigest() != rev:
            _hiba("beallitas.utkozes")
        regi = _adat(nyers)
        ertek = egyesit(_ertek(cfg, regi), valtozas)
        ellenoriz(ertek)
        modositas = {"beallitasok": ertek, "modulok": ertek["modulok"],
                     "sablon": {"mappa": ertek["fajlok"]["sablon_mappa"]}, "naplo": {"ut": ertek["fajlok"]["napi_ut"]}}
        if cfg.elrendezes == "termek":
            modositas["workspace"] = {"nyelv": "" if ertek["altalanos"]["nyelv"] == "auto" else ertek["altalanos"]["nyelv"]}
        # Automatic means no content-language hint, including after a previous explicit choice.
        modositas["sablon"]["nyelv"] = "" if ertek["altalanos"]["nyelv"] == "auto" else ertek["altalanos"]["nyelv"]
        rossz = config.reteg_ellenoriz(reteg, modositas, cfg.data, cfg.root)
        if rossz:
            _hiba(kulcs=rossz[0][0])
        uj = egyesit(regi, modositas)
        szoveg = toml_ir(uj).encode("utf-8")
        tomllib.loads(szoveg.decode("utf-8"))
        # Preserve a recoverable original (including user comments) before replacing the settings file.
        if nyers:
            if reteg == "munkater":
                workspace._atomi_ir_nofollow(p.parent, "workspace.toml.elozo", nyers)
            else:
                tartos.atomi_ir(p.with_suffix(".toml.elozo"), nyers)
        if reteg == "munkater":
            workspace._atomi_ir_nofollow(p.parent, p.name, szoveg)
        else:
            tartos.atomi_ir(p, szoveg)
        cfg.data = egyesit(cfg.data, modositas)
        for k in config._levelek(modositas):
            cfg.retegek[k] = "munkater" if reteg == "munkater" else "telepites"
        return _valasz(cfg, p, szoveg)


def utvonalak(r):
    r.get("/api/beallitasok", lambda k: olvas(k.app.cfg))
    def mentes(k):
        d = k.torzs()
        if not isinstance(d, dict) or set(d) != {"rev", "valtozas"}:
            _hiba()
        v = ir(k.app.cfg, d["rev"], d["valtozas"])
        k.app.bus.publish({"tipus": "beallitasok", **v})
        return v
    r.put("/api/beallitasok", mentes)
