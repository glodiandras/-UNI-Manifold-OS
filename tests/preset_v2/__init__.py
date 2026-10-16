"""A `v2-kompat` preset alatt futó tesztek (F3-DESIGN §7.2, §9 WP6).

A termék alapértékei semlegesek (`config/os.toml`: `Manifold - ` kísérő-előtag, `Daily/` napi jegyzet, üres tantárgy-szótár, nincs
téma-minta, `[sema] mod = "ki"`). A Manifold-OS 2.0 fejlesztő konvenciói — `ATTCHMNTS - …` kísérőmappák, `X01 - Napló & To-Do` napi
jegyzet, a tantárgy-betűk (`[pdf.tags]`), a `D13 - …` téma-mappák, a szigorú séma — a `config/presets/v2-kompat.toml`-ban (+
`v2-kompat.schema.json`) élnek. Az itteni tesztek ezeket a konvenciókat definiálják, ezért a presetet **kifejezetten** kérik
(`PRESET`), és nem az alapértékekre támaszkodnak. Az `alg_gyoker` alapja ugyanez a preset, de itt nem a véletlen alapértelmezés dönt.

Segédek: `alg_v2(tmp)` (álgyökér a presettel), `alg_core_v2(tmp)` (mint `helpers.alg_core`), `v2_cfg()` (modulonként egyszer épített, csak
olvasott konfig), `csak_sajat` (egy leszármazott teszt-osztály csak a saját metódusait futtatja: a szülő fixture-je kell, a szülő
tesztjei nem)."""
from __future__ import annotations

import atexit
from pathlib import Path

from core import config
from tests.helpers import alg_gyoker, tmpdir

PRESET = "v2-kompat"
V2_ELOTAG = "ATTCHMNTS - "          # a v2 kísérő-előtagja (a preset `[vault] kisero_elotag`-ja)

_gyorsitotar: dict = {}


def alg_v2(tmp: str, **kw) -> Path:
    """Álgyökér a `v2-kompat` presettel (hordozható elrendezés; a vault `{work}/Manifold`)."""
    return alg_gyoker(tmp, preset=PRESET, **kw)


def alg_core_v2(tmp: str, **env_extra):
    """Mint `tests.helpers.alg_core`, de a preset kifejezett → (config, gyökér, álvault)."""
    root = alg_v2(tmp)
    vault = root.parent / "Manifold"
    (vault / ".obsidian").mkdir()
    cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(tmp) / "home"), **env_extra})
    return cfg, root, vault


def v2_cfg():
    """A `v2-kompat` presettel feloldott konfig (modulszinten használható; a folyamat végéig élő ideiglenes álgyökéren)."""
    if "cfg" not in _gyorsitotar:
        t = tmpdir()
        atexit.register(t.cleanup)
        root = alg_v2(t.name)
        _gyorsitotar["cfg"] = config.load({"MOS_ROOT": str(root), "HOME": str(Path(t.name) / "home")})
    return _gyorsitotar["cfg"]


def csak_sajat(cls):
    """A leszármazott teszt-osztály az örökölt teszt-metódusokat nem futtatja (None-ra állítva a loader kihagyja); a fixture-ök
    (`setUp`, segédek) örökölve maradnak. A saját (osztálytestben definiált) tesztek futnak."""
    for nev in dir(cls):
        if nev.startswith("test") and nev not in cls.__dict__:
            setattr(cls, nev, None)
    return cls
