"""Út-feloldás a `config/os.toml`-ból (LEGACY-SZERZODESEK L49). Kódban abszolút út nem állhat.

A helyőrzők: `{os}` (a csomag helyéből, a `MOS_ROOT` felülírja), `{home}`, és bármely `[utak]` kulcs.
Minden `[utak]` kulcsot felülír a `MOS_<KULCS>`; a konfigfájlt a `MOS_CONFIG` jelöli ki. Körkörös vagy
ismeretlen helyőrző `ConfigError`: a hívó jelenti, nem javítja.
"""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

_HELYORZO = re.compile(r"\{(\w+)\}")
_MAX_MELYSEG = 12

# Az app egyetlen azonosítója (reverse-DNS; a `shell/Info.plist` CFBundleIdentifier-e). Ebből képződik a doctor
# home-kivétele (`~/Library/Preferences/<id>.plist`) és a fájlfigyelő dispatch-sorának neve.
BUNDLE_ID = "com.manifold.app"


class ConfigError(ValueError):
    """Hibás vagy feloldhatatlan konfiguráció."""


def os_root() -> Path:
    """A gyökér: `MOS_ROOT`, különben a csomag saját helyéből."""
    env = os.environ.get("MOS_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parent.parent


def expand(template: str, table: dict[str, str], _stack: tuple[str, ...] = ()) -> str:
    """Helyőrzők feloldása a `table` alapján, rekurzívan; a végén normalizált út (a legacy szabálya)."""
    if len(_stack) > _MAX_MELYSEG:
        raise ConfigError(f"túl mély helyőrző-lánc: {' → '.join(_stack)}")

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key in _stack:
            raise ConfigError(f"körkörös helyőrző: {' → '.join(_stack + (key,))}")
        if key not in table:
            raise ConfigError(f"ismeretlen helyőrző: {{{key}}} ({template!r})")
        return expand(table[key], table, _stack + (key,))

    out = os.path.expanduser(_HELYORZO.sub(sub, template))
    return os.path.normpath(out) if ("/" in out or out.startswith("~")) else out


class Config:
    def __init__(self, root: Path, data: dict, environment: dict[str, str], source: Path | None = None):
        self.root = root
        self.data = data
        self.source = source
        self.table: dict[str, str] = {
            "os": str(root), "home": str(Path(environment.get("HOME", "~")).expanduser())}
        for kulcs, ertek in data.get("utak", {}).items():
            self.table[kulcs] = environment.get(f"MOS_{kulcs.upper()}") or ertek
        self.utak = {k: Path(expand(f"{{{k}}}", self.table)) for k in data.get("utak", {})}

    def path(self, kulcs: str) -> Path:
        if kulcs not in self.utak:
            raise ConfigError(f"nincs ilyen út a konfigurációban: {kulcs}")
        return self.utak[kulcs]

    def expand(self, template: str) -> str:
        return expand(template, self.table)

    def section(self, *keys: str) -> dict:
        node = self.data
        for k in keys:
            node = node.get(k, {})
        return node


def load(environment: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if environment is None else environment)
    root = Path(env["MOS_ROOT"]).resolve() if env.get("MOS_ROOT") else os_root()
    cfg = Path(env.get("MOS_CONFIG") or root / "config" / "os.toml")
    try:
        with open(cfg, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as exc:
        raise ConfigError(f"a konfiguráció nem található: {cfg}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"hibás TOML: {cfg}: {exc}") from exc
    return Config(root, data, env, cfg)
