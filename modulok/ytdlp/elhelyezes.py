"""A videó vaultba kerülésének **terve** (C20a) — a legacy `media.py` `safe_stem` / `media_dir` / `video_dir` / `place_video` és a
`media_auto._s_elhelyezes` ütközés-ellenőrzésének szabálya tiszta függvényként. Nem mozgat, nem ír: a tényleges mozgatás a C20b gépi-írás
`mozgat` művelete (docs/C20-TERV.md), amely ezt a tervet kapja.

A szabály (PB07 D6, 2026-09-19): a **videófájl** a vault gyökerében álló lapos videómappába (`media.video_mappa`), a **mellékletei**
(felirat, `.info.json`, forrásleíró jegyzet, bélyegkép) a témamappa `Média/` rétegébe; a hang (és a régi elrendezés, ha nincs videómappa)
a rétegben marad. A hivatkozások fájlnév-alapúak, ezért a médiafájl neve vault-szinten egyedi kell legyen (a lapos mappa a videók között
kikényszeríti, a `media_index` a többi médiafájllal szemben). Felülírás nincs. Mindent vagy semmit: ütközésnél az egész terv elutasított.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from core import mediatipus

ALAP_VIDEO_MAPPA = "ATTCHMNTS - Videos"
ALAP_RETEG = "Média"
SENTINEL_HIANY = "(nem a media.py írta)"
_ROSSZ = '/\\:*?"<>|'
KIHAGY_MAPPAK = {".obsidian", ".git", ".trash"}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def fajlnev_torzs(cim: str | None) -> str:
    """Vault-biztos fájlnév-törzs (legacy `safe_stem`; I32: a fájlnév és a cím UGYANABBÓL a sztringből származik — a jegyzet H1-e a
    szűkített alakhoz igazodik, nem fordítva)."""
    t = nfc((cim or "").strip())
    t = "".join("-" if c in _ROSSZ else c for c in t)
    t = t.replace("​", "").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip(" .-_")
    return t[:120].strip() or "media"


def video_e(nev: str) -> bool:
    ct = mediatipus.tipus(nev)
    return bool(ct and ct.startswith("video/"))


def media_e(nev: str) -> bool:
    return mediatipus.media_e(nev) and not mediatipus.tipus(nev).startswith(("image/", "application/"))


def media_index(vault: str | Path) -> dict[str, str]:
    """`{NFC fájlnév: vault-relatív út}` a vault összes videó- és hangfájljára (a névütközés-vizsgálat alapja)."""
    vault = Path(vault)
    ki: dict[str, str] = {}
    for d, almappak, fajlok in os.walk(vault):
        almappak[:] = [a for a in almappak if a not in KIHAGY_MAPPAK]
        for f in fajlok:
            if media_e(f):
                ki.setdefault(nfc(f), nfc(os.path.relpath(os.path.join(d, f), vault)))
    return ki


def terv(vault: str | Path, tema: str, fajlok: list[str], *, video_mappa: str | None = ALAP_VIDEO_MAPPA, reteg: str = ALAP_RETEG,
         torzs: str | None = None, sentinel: str | None = None, index: dict[str, str] | None = None) -> dict:
    """A munkamappa fájljainak (`fajlok`: fájlnevek) tervezett helye a vaultban.

    → `{"tema", "cel", "video_cel", "fajlok": [{"nev", "cel_ut", "video"}], "utkozesek": [str]}`; az `utkozesek` nem üres → a terv
    nem hajtható végre (felülírás nincs; mindent vagy semmit). A `video_cel` `None` a régi elrendezésnél (nincs `video_mappa`: minden a
    rétegben). A `torzs` és a `sentinel` megadásakor a `<cel>/<törzs>.md` forrásleíró jegyzet is ellenőrződik: ha létezik, és nem
    tartalmazza a `sentinel`-t (a láncot író jelölőt), az idegen jegyzet — ütközés. A sentinel a jegyzet írójáé (C20b)."""
    vault = Path(vault)
    tema = nfc(tema)
    cel = f"{tema}/{reteg}"
    vcel = video_mappa if video_mappa else cel
    index = media_index(vault) if index is None else index
    sorok, utk = [], []
    for f in fajlok:
        video = bool(video_mappa) and video_e(f)
        cel_ut = f"{vcel if video else cel}/{f}"
        sorok.append({"nev": f, "cel_ut": cel_ut, "video": video})
        if os.path.lexists(vault / cel_ut):
            utk.append(f)
        elif media_e(f) and nfc(f) in index:
            utk.append(f"{f} (a fájlnév már létezik: {index[nfc(f)]})")
    ki = {"tema": tema, "cel": cel, "video_cel": vcel if vcel != cel else None, "fajlok": sorok, "utkozesek": utk}
    if torzs:
        jegyzet = vault / cel / f"{torzs}.md"
        ki["forrasjegyzet_letezik"] = jegyzet.exists()
        if jegyzet.exists() and sentinel is not None and sentinel not in jegyzet.read_text(encoding="utf-8", errors="replace"):
            utk.append(f"{torzs}.md {SENTINEL_HIANY}")
    return ki
