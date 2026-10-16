"""A folyamat gyökerei: egyetlen feloldás, rögzítve (F3-DESIGN §2.6).

A `bin/mos` a Python-parancsok előtt a `shell` kimenetét értékeli ki (a gyorsítótárak, az ideiglenes mappa és a HF-offline a
feloldott utakra, nem a beégetett `var/`-ra); a `python -m core start` a core indulásakor minden feloldott `[utak]` kulcsot
abszolút `MOS_<KULCS>`-ként a saját környezetébe rögzít (`rogzit`), így a lépések, a worker, a CLI-gyermekek és a D9-próbaklón
ugyanazokat az utakat látják, akkor is, ha egy beállítás közben megváltozik (az út-kulcsok a következő megnyitáskor hatnak).

    python -m core.gyokerek shell [--rogzit]     export-sorok (shlex-idézve; a feloldatlan kulcsok kimaradnak)
    python -m core.gyokerek json                 a feloldás eredménye JSON-ban
    python -m core.gyokerek portable-init --vault <mappa> [--preset <nev>]… [--backup <ut>] [--idegen-zar <ut>]… [--igen]
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Mapping, MutableMapping

from . import config

SPOTLIGHT_JELOLO = ".metadata_never_index"


def _tmp(cfg) -> Path | None:
    """Az ideiglenes mappa: a `{tmp}` (a vault kötetén: atomi csere, APFS-klón), munkatér nélkül `{install}/tmp`."""
    if "tmp" in cfg.utak:
        return cfg.utak["tmp"]
    return cfg.utak["install"] / "tmp" if "install" in cfg.utak else None


def folyamat_env(cfg, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """A gyermekfolyamatok környezete a feloldott utakból: `HF_HOME={models}`, a HF/Transformers offline (alapértékként: a
    hívó kifejezett értéke marad, pl. a `models pull`), `XDG_CACHE_HOME={cache}`, `UV_CACHE_DIR`/`PIP_CACHE_DIR` a `{cache}`
    alatt, `TMPDIR={tmp}`, és nincs bájtkód-írás (a csak olvasható kódfába sem)."""
    env = os.environ if environ is None else environ
    ki: dict[str, str] = {}
    if "models" in cfg.utak:
        ki["HF_HOME"] = str(cfg.utak["models"])
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        ki[k] = env.get(k) or "1"
    if "cache" in cfg.utak:
        c = cfg.utak["cache"]
        ki.update(XDG_CACHE_HOME=str(c), UV_CACHE_DIR=str(c / "uv"), PIP_CACHE_DIR=str(c / "pip"))
    tmp = _tmp(cfg)
    if tmp is not None:
        ki["TMPDIR"] = str(tmp)
    ki["PYTHONDONTWRITEBYTECODE"] = "1"
    return ki


def biztosit_mappak(cfg) -> None:
    """A `{tmp}`, `{cache}`, `{install_run}`, `{install_logs}` mappák, és a Spotlight-kizárás jelölője (L50) a `{var}` és az
    `{install}` gyökerében. Hiba (csak olvasható kötet) nem állít meg semmit: a hívó parancs maga jelenti a hiányt."""
    for p in (_tmp(cfg), *(cfg.utak.get(k) for k in ("cache", "install_run", "install_logs"))):
        if p is not None:
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
    for k in ("var", "install"):
        d = cfg.utak.get(k)
        if d is not None and d.is_dir() and not (d / SPOTLIGHT_JELOLO).exists():
            try:
                (d / SPOTLIGHT_JELOLO).touch()
            except OSError:
                pass


def rogzit(cfg, environ: MutableMapping[str, str]) -> None:
    """Minden feloldott `[utak]` kulcs abszolút útja `MOS_<KULCS>`-ként, továbbá `MOS_ELRENDEZES` és (ha van)
    `MOS_WORKSPACE_ID`: a gyermekek `config.load()`-ja ugyanazt oldja fel, a rétegek közbeni változásától függetlenül."""
    for k, p in cfg.utak.items():
        environ[f"MOS_{k.upper()}"] = str(p)
    environ["MOS_ELRENDEZES"] = cfg.elrendezes
    if cfg.workspace_id:
        environ["MOS_WORKSPACE_ID"] = cfg.workspace_id


# ------------------------------------------------------------------ portable init


def _toml_ertek(v) -> str:
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)          # a JSON-szöveg érvényes TOML alapszöveg
    if isinstance(v, list):
        return "[" + ", ".join(_toml_ertek(x) for x in v) + "]"
    raise TypeError(type(v))


def _toml_ir(d: dict) -> str:
    sorok = ["# A hordozható (fejlesztői) telepítés rétege: `bin/mos portable init` írta (F3-DESIGN §7.1). A `var/` gitignore-olt.", ""]
    for tabla, ertekek in d.items():
        sorok.append(f"[{tabla}]")
        sorok += [f"{k} = {_toml_ertek(v)}" for k, v in ertekek.items()]
        sorok.append("")
    return "\n".join(sorok)


def portable_init(root: Path, *, vault, presetek=(), backup=None, idegen_zarak=(), igen: bool = False,
                  environ: Mapping[str, str] | None = None) -> Path:
    """A hordozható telepítési réteg (`{install}/settings.toml`, hordozható módban `{os}/var/settings.toml`) megírása:
    a vault, a presetek, a belső lemezes mentés és a csak olvasva vizsgált idegen zárak (egy másik telepítés `core.lock`-ja).
    A vaultba semmit nem ír (`.manifold` sem keletkezik: egy v2 által kezelt vaultba nem kerülhet). Meglévő fájlt csak `igen`
    mellett ír felül; az előző változat `settings.toml.elozo` néven megmarad."""
    from . import tartos
    env = dict(os.environ if environ is None else environ)
    root = Path(root).resolve()
    env["MOS_ROOT"] = str(root)
    if config.elrendezes(root, env) != "hordozhato":
        raise config.ConfigError("a portable init csak hordozható (checkout) elrendezésben futhat", kod="portable_termekben",
                                 param={"gyoker": str(root)})
    v = Path(os.path.expanduser(str(vault))).absolute()
    if not v.is_dir():
        raise config.ConfigError(f"a vault mappa nem létezik: {v}", kod="vault_nem_letezik", param={"vault": str(v)})
    rv = Path(os.path.realpath(v))
    if rv == root or root in rv.parents:
        raise config.ConfigError(f"a vault nem lehet a kódfában: {v}", kod="vault_a_kodban", param={"vault": str(v)})
    d: dict[str, dict] = {"utak": {"vault": str(v)}}
    if backup:
        d["utak"]["backup"] = str(backup)
    if presetek:
        d["telepites"] = {"presetek": list(presetek)}
    if idegen_zarak:
        d["hordozhato"] = {"idegen_zarak": [str(Path(os.path.expanduser(z)).absolute()) for z in idegen_zarak]}
    forras = Path(env.get("MOS_CONFIG") or root / "config" / "os.toml")
    s = config._toml_olvas(forras, kod="config_toml_hibas")
    rossz = config.reteg_ellenoriz("telepites_hordozhato", d, s, root)
    if rossz:
        raise config.ConfigError("érvénytelen beállítás: " + ", ".join(f"{k} ({kod})" for k, kod in rossz),
                                 kod="settings_ervenytelen", param={"elutasitott": [list(x) for x in rossz]})
    alap = config.Config(root, {**s, "_meta": {"elrendezes": "hordozhato"}}, env, forras)
    cel = config._settings_ut(env, root, alap.utak.get("install"))
    if cel is None:
        raise config.ConfigError("a telepítési réteg ki van kapcsolva (MOS_SETTINGS üres)", kod="settings_kikapcsolva")
    if cel.exists() and not igen:
        raise config.ConfigError(f"a telepítési réteg már létezik: {cel} (felülírás: --igen)", kod="settings_letezik",
                                 param={"ut": str(cel)})
    cel.parent.mkdir(parents=True, exist_ok=True)
    if cel.exists():
        shutil.copy2(cel, cel.with_name(cel.name + ".elozo"))
    tartos.atomi_ir(cel, _toml_ir(d).encode("utf-8"))
    return cel


# ------------------------------------------------------------------ CLI


def _export(d: Mapping[str, str]) -> str:
    return "".join(f"export {k}={shlex.quote(v)}\n" for k, v in sorted(d.items()))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parancs = argv[0] if argv else ""
    if parancs == "shell":
        try:
            cfg = config.load(munkater=False)
        except config.ConfigError as e:
            # a parancs maga tölti be újra a konfigot, és jelenti a hibát (a doctor is ezt mutatja); itt csak a biztos rész
            print(f"[gyokerek] a konfiguráció nem tölthető be ({e.kod}): {e}", file=sys.stderr)
            sys.stdout.write(_export({"PYTHONDONTWRITEBYTECODE": "1",
                                      **{k: os.environ.get(k) or "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}}))
            return 0
        biztosit_mappak(cfg)
        ki = folyamat_env(cfg)
        if "--rogzit" in argv[1:]:
            r: dict[str, str] = {}
            rogzit(cfg, r)
            ki = {**r, **ki}
        sys.stdout.write(_export(ki))
        return 0
    if parancs == "json":
        try:
            cfg = config.load(munkater=False)
        except config.ConfigError as e:
            print(json.dumps({"hiba": e.kod, "param": e.param, "uzenet": str(e)}, ensure_ascii=False))
            return 78
        print(json.dumps({"elrendezes": cfg.elrendezes, "workspace_id": cfg.workspace_id,
                          "utak": {k: str(p) for k, p in cfg.utak.items()}, "feloldatlan": cfg.feloldatlan,
                          "env": folyamat_env(cfg), "retegek": cfg.retegek, "elutasitott": [list(x) for x in cfg.elutasitott],
                          "settings": cfg.data.get("_meta", {}).get("settings", "")}, ensure_ascii=False, indent=1))
        return 0
    if parancs == "portable-init":
        ap = argparse.ArgumentParser(prog="mos portable init", description="a hordozható telepítés rétegének megírása")
        ap.add_argument("--vault", required=True)
        ap.add_argument("--preset", action="append", default=[], dest="presetek")
        ap.add_argument("--backup")
        ap.add_argument("--idegen-zar", action="append", default=[], dest="idegen_zarak")
        ap.add_argument("--igen", action="store_true")
        a = ap.parse_args(argv[1:])
        try:
            cel = portable_init(config.os_root(), vault=a.vault, presetek=a.presetek, backup=a.backup,
                                idegen_zarak=a.idegen_zarak, igen=a.igen)
        except config.ConfigError as e:
            print(f"HIBA ({e.kod}): {e}", file=sys.stderr)
            return 78
        print(f"kész: {cel}")
        return 0
    print("használat: python -m core.gyokerek shell [--rogzit] | json | portable-init --vault <mappa> …", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
