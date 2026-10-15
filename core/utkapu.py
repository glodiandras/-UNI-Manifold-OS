"""A vaulton belüli út kapuja (C29.6, 2. audit T098): egy vaultba került symlink a felhasználó bármely olvasható fájljának
szövegét a keresésbe, a beágyazásba és az átiratba vihette (a `GET /api/vault/fajl` elutasította, az index bejárása viszont
követte). Közös segéd az `_abs`-nak, a két bejárásnak (`feloldas.bejaras`, `indexelo._bejar`/`_alkalmaz`) és az átiratnak.

`os.walk` a könyvtár-symlinkeket nem követi (`followlinks=False`); itt a FÁJL-symlinkek maradnak: a symlink akkor „belül”
van, ha a feloldott célja a vault gyökerén (vagy alatta) áll.
"""
from __future__ import annotations

import os


def belul(gyoker, ut, onmaga: bool = True) -> bool:
    """Igaz, ha az `ut` (fájl vagy mappa) a `gyoker` alatt marad: nem symlink, vagy a symlink feloldott célja a gyökéren
    belül van. `onmaga`: a gyökér maga is „belül” van (az `_abs` szigorúbb: csak alatta). Hibánál (nem olvasható) hamis."""
    try:
        if not os.path.islink(ut):
            return True
        cel, gy = os.path.realpath(ut), os.path.realpath(gyoker)
        return (onmaga and cel == gy) or cel.startswith(gy + os.sep)
    except OSError:
        return False


def alatta(gyoker, ut) -> bool:
    """Szigorú változat: a feloldott `ut` a `gyoker` ALATT áll (a gyökér maga nem; minden útszegmens symlinkje feloldva)."""
    try:
        return os.path.realpath(ut).startswith(os.path.realpath(gyoker) + os.sep)
    except OSError:
        return False
