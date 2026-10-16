"""Developer mód: a fejlesztői és teszt-horgok egyetlen kapcsolója (`MOS_FEJLESZTO=1`).

A kiadott appban a kapcsoló nincs beállítva, ezért a teszt-horgok (a hálózat-őr kikapcsolása a loopback-szerveres tesztekhez, a
`proba` feladattípus, az összeomlás-injektálás, a `video selftest|test` parancsok) nem érhetők el. Forrás-checkoutban (van `tests/`)
a `bin/mos` maga állítja be (kivéve, ha a hívó `MOS_FEJLESZTO=0`-t ad); a tesztek hermetikus környezete (`tests.helpers.env`) is.
Egy horog tehát két feltétellel él: Developer mód **és** a horog saját kapcsolója.

A felület **Developer nézete** (F7: a technikai panelek, a nyers diagnosztika, a v2-import) más: nem a folyamat környezete, hanem
felhasználói beállítás (`beallitasok.fejleszto.mod`, Settings › About › Advanced information). Az indító ⌥-kattintása a core
indításakor `MOS_FEJLESZTOI_NEZET=1`-et ad a környezetnek (`nezet_kenyszer`): ez ebben a munkamenetben bekapcsolja a nézetet,
a mentett beállítást nem írja át.
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


NEZET_ENV = "MOS_FEJLESZTOI_NEZET"


def nezet_kenyszer(env: Mapping[str, str] | None = None) -> bool:
    """Az indító ⌥-kattintása kérte-e a Developer nézetet erre a munkamenetre (`MOS_FEJLESZTOI_NEZET=1`)."""
    return (os.environ if env is None else env).get(NEZET_ENV) == "1"
