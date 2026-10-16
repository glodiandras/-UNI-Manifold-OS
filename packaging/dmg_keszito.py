"""DMG-készítés (F9; P5): a kész `Manifold.app` egy tömörített lemezképbe, mellette egy `Applications` hivatkozással.

`hdiutil` nélkül (vagy `dry_run=True`) csak a terv készül el (a parancsok listája), lemezkép nem. A lemezkép a csomagot nem
módosítja; az aláírás és a notarizáció külön lépés (`alairas.py`): a notarizált DMG-t a `stapler` pecsételi.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from csomag_kozos import CsomagHiba, Futtato, futtat, klonoz, van_parancs

KOTET_NEV = "Manifold"
FORMATUM = "UDZO"          # zlib-tömörített, csak olvasható (minden támogatott macOS megnyitja)


@dataclass
class DmgTerv:
    app: Path
    kimenet: Path
    staging: Path
    parancsok: list[list[str]] = field(default_factory=list)
    dry_run: bool = False
    ok_hianyzo_eszkoz: str = ""


def terv(app: Path, kimenet: Path, *, kotet_nev: str = KOTET_NEV, formatum: str = FORMATUM) -> DmgTerv:
    staging = kimenet.parent / f".dmg-staging-{kimenet.stem}"
    t = DmgTerv(app, kimenet, staging)
    t.parancsok = [
        ["hdiutil", "create", "-volname", kotet_nev, "-srcfolder", str(staging), "-fs", "HFS+", "-format", formatum,
         "-ov", str(kimenet)],
        ["hdiutil", "verify", str(kimenet)],
    ]
    return t


def keszit(app: Path, kimenet: Path, *, dry_run: bool = False, futtato: Futtato = futtat, kotet_nev: str = KOTET_NEV,
           formatum: str = FORMATUM, naplo=print) -> DmgTerv:
    """A DMG elkészítése (vagy a terve). A staging-mappa (az app klónja + `Applications` symlink) a végén eltávolítódik."""
    if not (app / "Contents" / "Info.plist").is_file():
        raise CsomagHiba("app_hianyzik", f"nem app-csomag: {app}")
    t = terv(app, kimenet, kotet_nev=kotet_nev, formatum=formatum)
    if not dry_run and not van_parancs("hdiutil"):
        t.ok_hianyzo_eszkoz = "hdiutil"
        dry_run = True
    t.dry_run = dry_run
    if dry_run:
        naplo("DMG (dry-run" + (", nincs hdiutil" if t.ok_hianyzo_eszkoz else "") + "): " +
              " && ".join(" ".join(c) for c in t.parancsok))
        return t
    if t.staging.exists():
        shutil.rmtree(t.staging)
    try:
        t.staging.mkdir(parents=True)
        klonoz(app, t.staging / app.name)
        (t.staging / "Applications").symlink_to("/Applications")
        kimenet.parent.mkdir(parents=True, exist_ok=True)
        for cmd in t.parancsok:
            naplo("$ " + " ".join(cmd))
            futtato(cmd, timeout=3600)
    finally:
        shutil.rmtree(t.staging, ignore_errors=True)
    naplo(f"kész: {kimenet}")
    return t
