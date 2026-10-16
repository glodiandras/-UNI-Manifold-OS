"""„Nem a vaultba” őr a parancssori kiírásokhoz (A3-27).

A `Path.is_relative_to` szöveges összevetés, ezért kis-nagybetű-érzéketlen fájlrendszeren (APFS) a `/Volumes/work/manifold/…`
átmegy a vault-úton alapuló őrön. Itt a vault és a cél **azonosságát** nézzük (`os.path.samefile`: inode, nem szöveg):
a cél legközelebbi létező őse között van-e a vault.

**Zárva hibázik** (K179): ha a vault-út nem oldható fel (nem létezik, eltűnt, nem olvasható), vagy az azonosság-összevetés
`OSError`-ral hibázik egy létező őssel, a válasz „a vaultban van” (tiltás). Egy eltűnt vault ellen az őr nem engedhet át írást."""
from __future__ import annotations

import os
from pathlib import Path


def vaultban_van(cel, vault) -> bool:
    """Igaz, ha a `cel` (akár még nem létező) út a `vault` mappa vagy annak belseje — szöveg szerint vagy fájlrendszer-azonosság
    szerint. Igaz akkor is, ha a vault vagy a cél nem vizsgálható (zárva hibázás: a hívó ilyenkor tilt)."""
    try:
        v = Path(vault).resolve(strict=True)
        os.stat(v)                               # a vault tényleg létezik és olvasható
        p = Path(cel).resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return True
    if p.is_relative_to(v):
        return True
    for a in (p, *p.parents):
        try:
            if os.path.samefile(a, v):
                return True
        except OSError:
            try:
                os.stat(a)
            except OSError:                      # nem létező ős: feljebb megyünk
                continue
            return True                          # az ős létezik, az összevetés mégis hibázott (a vault eltűnt): zárva
    return False
