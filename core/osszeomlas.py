"""Összeomlás-injektáló horog (C29.6, 2. audit T193): a lépéshatárokon `osszeomlas.pont("<hely>")`.

Élesben semmit nem csinál: a `MOS_OSSZEOMLAS` környezeti változót **importkor** és csak Developer módban (`MOS_FEJLESZTO=1`, `core/fejleszto.py`) olvassa, így egy hívás költsége egy
sztring-összehasonlítás. A `tests/osszeomlas.py` állvány alfolyamatot indít `MOS_OSSZEOMLAS=<pont>`-tal; a folyamat
a megnevezett ponton `os._exit(137)`-tel hal meg (nincs `finally`, nincs `atexit`, nincs szálleállítás — mint a
SIGKILL vagy az áramszünet), a szülő pedig a következő indulás (`App.indulas()`) utáni invariánsokat ellenőrzi.
A doctor HIBÁT ad, ha a változó be van állítva (éles appban soha nem lehet).

A pontok nevei `<modul>.<hely>` alakúak; a teljes lista a `tests/osszeomlas.py` `PONTOK` táblájában áll.
"""
from __future__ import annotations

import os

from . import fejleszto

PONT = os.environ.get("MOS_OSSZEOMLAS", "") if fejleszto.aktiv() else ""      # csak Developer módban (MOS_FEJLESZTO=1)
KILEPESI_KOD = 137


def pont(nev: str) -> None:
    """Ha a `MOS_OSSZEOMLAS` éppen ez a pont, a folyamat azonnal, tisztítás nélkül kilép."""
    if PONT and PONT == nev:
        os._exit(KILEPESI_KOD)
