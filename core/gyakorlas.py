"""A forrásjegyzet `## Gyakorlás` szakasza (TERV 5.2): a beágyazó sor formátumának **egyetlen helye** (mint a
`core/pdfkiemeles.py` a PDF-kiemelésé) — a kvíz (C22b) és a kártya (C23b) is ezt használja.

```markdown
## Gyakorlás
![[Mértani sorozat — kártyák]]
![[Mértani sorozat — Kvíz 2026-10-04 2030]]
```

A kísérőjegyzetekre (kártya, kvíz) a forrásban csak ez a sor mutat; a sor beírása **gépi írás** (egy tétel a kísérőjegyzet
létrehozásával, a `POST /api/gepi-iras` `beszuras` művelete, visszavonható). Az összeállító segéd a műveletet adja; az írást
a hívó végzi. A beszúrás a `gepi_iras.szakasz_beszur` szabályai szerint megy: a hiányzó szakasz a jegyzet végére kerül, a sor
a szakasz végére (a megelőző beágyazások után: a kártya a kvíz előtt áll), ismétlésre nincs változás, a sorvég a fájlé marad.
"""
from __future__ import annotations

import re
import unicodedata

SZAKASZ = "Gyakorlás"
FEJEZET = f"## {SZAKASZ}"
_TILTOTT = re.compile(r"[\[\]|#^\\/\x00-\x1f]")


def beagyazo_sor(nev: str) -> str:
    """`![[<név>]]`: a kísérőjegyzet neve `.md` és útvonal nélkül (a név a vaultban egyedi: időbélyeges vagy ütközésmentes)."""
    nev = unicodedata.normalize("NFC", nev or "").strip()
    if not nev or _TILTOTT.search(nev) or nev.lower().endswith(".md"):
        raise ValueError(f"a beágyazandó jegyzet neve érvénytelen (kiterjesztés és `[ ] | # ^ /` nélkül kell): {nev!r}")
    return f"![[{nev}]]"


def beszuras_muvelet(forras_ut: str, nev: str, alap: str | None = None) -> dict:
    """A gépi írás `beszuras` művelete: a kísérőjegyzet beágyazó sora a forrás `## Gyakorlás` szakaszának végére (a szakasz
    hiányában létrehozva). `alap`: a forrás ismert sha1-je (nem kötelező; eltérésnél 409)."""
    if not forras_ut or not forras_ut.lower().endswith(".md"):
        raise ValueError(f"a forrás vault-relatív `.md` út legyen: {forras_ut!r}")
    m = {"tipus": "beszuras", "ut": forras_ut, "szakasz": FEJEZET, "szoveg": beagyazo_sor(nev), "hova": "vege", "letrehoz": True}
    if alap:
        m["alap"] = alap
    return m
