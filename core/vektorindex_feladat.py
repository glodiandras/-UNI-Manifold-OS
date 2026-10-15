"""A vektorindex frissítésének feladattípusa (C25b; CLAUDE.md 58(a), 58(c), 2. és 3. döntés, D8).

`TaskType("vektorindex", automatikus=True)`: a gép magától indítja (a közös automatika-ütemező — C23b —, vagy a vezérlőből
kézzel), ezért a `Kapu.admit` alatt indul (D8 indulási szünet, aktív használat alatt nem, kevés szabad memóriánál nem), az
Asszisztens-kapcsoló kikapcsolt állapotában a vezérlő be sem fogadja (27(c)), és a worker a kéréseit `auto` módban futtatja
(aktív használatkor szünetel, M3). Csak a `[kereses.hibrid] vektor = true` mellett van értelme (M12, C25b mérés).

A lépés a `python -m core.index.hibrid frissit` alfolyamata: a `vault.sqlite`-ot csak olvassa, a `{index}/vektor.sqlite`-ot
jegyzetenként atomian frissíti (újraépíthető, a belső mentésbe nem kerül, 33.; a vaultba nem ír, így a core-hoz sem kell
hozzáférés: a lépés jogkészlete `nincs`). A leállítás a stop-fájllal jegyzethatáron áll meg; a következő futás onnan folytatja.
Mérés (C25b, a vault 2193 jegyzete): ~20 800 darab, ~55–60 perc tétlen gépen, ~133 MB; egy változott jegyzet másodpercek.
"""
from __future__ import annotations

import sys

from . import lepes_kapu, tasks
from .config import Config

TIPUS = "vektorindex"
MAX_JEGYZET = 100_000


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    argv = [sys.executable, "-B", "-m", "core.index.hibrid", "frissit", "--stop-fajl", stop]
    if "max" in p:
        m = p["max"]
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= MAX_JEGYZET:
            raise tasks.Invalid(f"A `max` 1–{MAX_JEGYZET} egész szám legyen.")
        argv += ["--max", str(m)]
    return ([tasks.Step("A keresés vektorindexének frissítése", argv, str(cfg.root), jogok=lepes_kapu.JOGOK_NINCS)],
            "A változott jegyzetek darabjai beágyazódnak a jelentés szerinti kereséshez (a vaultba nem ír).", [])


def regisztral() -> None:
    """A feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "A keresés vektorindexe", _terv, resources=frozenset({"modell"}),
                                  graceful_stop=True, automatikus=True))
