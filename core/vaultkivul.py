"""„Nem a vaultba” őr a parancssori kiírásokhoz (A3-27).

A `Path.is_relative_to` szöveges összevetés, ezért kis-nagybetű-érzéketlen fájlrendszeren (APFS) a `/Volumes/work/manifold/…`
átmegy a vault-úton alapuló őrön. Itt a vault és a cél **azonosságát** nézzük (`os.path.samefile`: inode, nem szöveg):
a cél legközelebbi létező őse között van-e a vault.

**Zárva hibázik** (K179): ha a vault-út nem oldható fel (nem létezik, eltűnt, nem olvasható), vagy az azonosság-összevetés
`OSError`-ral hibázik egy létező őssel, a válasz „a vaultban van” (tiltás). Egy eltűnt vault ellen az őr nem engedhet át írást.

**Kivétel** (F3, §3.6): a munkatér állapota (`<vault>/.manifold/var`, a termék `{var}`-ja) nem vault-tartalom — a pillanatkép
kizárja, minden bejáró kihagyja —, ezért az alatta álló cél (szöveg szerint VAGY fájlrendszer-azonosság szerint ős) „kívül” van:
így a kártya-export alapcélja (`{szemelyes}/export`) a termékben is írható. Minden más változatlan, és zárva hibázik."""
from __future__ import annotations

import os
from pathlib import Path

ALLAPOT = Path(".manifold") / "var"     # a munkatér állapota a vaultban (F3: a termék `{var}`-ja)


def vaultban_van(cel, vault) -> bool:
    """Igaz, ha a `cel` (akár még nem létező) út a `vault` mappa vagy annak belseje — szöveg szerint vagy fájlrendszer-azonosság
    szerint. Igaz akkor is, ha a vault vagy a cél nem vizsgálható (zárva hibázás: a hívó ilyenkor tilt)."""
    try:
        v = Path(vault).resolve(strict=True)
        os.stat(v)                               # a vault tényleg létezik és olvasható
        p = Path(cel).resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return True
    if _allapotban(p, v):
        return False
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


def _allapotban(p: Path, v: Path) -> bool:
    """A (feloldott) `p` a (feloldott) `v` vault munkatér-állapota (`.manifold/var`) alatt van-e: szöveg szerint, vagy egy létező
    ős fájlrendszer-azonosság szerint az. Csak a létező, valódi (nem symlinkelt) `.manifold/var` kivétel: a symlinkkel egy
    idegen vault a jegyzetei közé irányíthatná a kiírást, és munkatér nélkül (hordozható, v2-kezelte vault) minden változatlan."""
    allapot = v / ALLAPOT
    if Path(os.path.realpath(allapot)) != allapot or not allapot.is_dir():
        return False
    if p.is_relative_to(allapot):
        return True
    for a in (p, *p.parents):
        try:
            if os.path.samefile(a, allapot):
                return True
        except OSError:
            continue
    return False
