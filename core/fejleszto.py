"""Developer mód: a fejlesztői és teszt-horgok egyetlen kapcsolója (`MOS_FEJLESZTO=1`).

A kiadott appban a kapcsoló nincs beállítva, ezért a teszt-horgok (a hálózat-őr kikapcsolása a loopback-szerveres tesztekhez, a
`proba` feladattípus, az összeomlás-injektálás, a `video selftest|test` parancsok) nem érhetők el. Forrás-checkoutban (van `tests/`)
a `bin/mos` maga állítja be (kivéve, ha a hívó `MOS_FEJLESZTO=0`-t ad); a tesztek hermetikus környezete (`tests.helpers.env`) is.
Egy horog tehát két feltétellel él: Developer mód **és** a horog saját kapcsolója.
"""
from __future__ import annotations

import os
from typing import Mapping


def aktiv(env: Mapping[str, str] | None = None) -> bool:
    """Developer módban fut-e a folyamat (`MOS_FEJLESZTO=1`)."""
    return (os.environ if env is None else env).get("MOS_FEJLESZTO") == "1"


def kapcsolo(nev: str, env: Mapping[str, str] | None = None) -> bool:
    """Egy fejlesztői horog kapcsolója (`<nev>=1`): csak Developer módban élhet, különben mindig hamis."""
    e = os.environ if env is None else env
    return aktiv(e) and e.get(nev) == "1"
