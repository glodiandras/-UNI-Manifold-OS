"""A kvíz-adatforrás illesztője (C28a): a felkészültség kvíz-összetevőjének bemenete.

A kvíz tárolója a C22 dolga, ezért itt **csak a szűk, típusos felület** áll: egy `KvizForras` (`regisztral_kviz_forras`)
egy időablakra a kvízeredményeket adja témánként (a téma a jegyzet vault-relatív NFC útja, amelyből a kvíz kérdezett).
Regisztráció nélkül a kvíz-összetevő „nincs forrás”. A forrás hibája nem viszi el a többit; az érvénytelen elem (időzóna
nélküli idő, `helyes > összes`, `összes ≤ 0`) kimarad, és egy hibaüzenet jelzi.

**A C22 tárolójára kötve (C28b)**: a beépített `kviz` forrás a `tanulas.sqlite` `kviz_kitoltes` táblájából olvas (`mode=ro`,
nem migrál, nem hoz létre fájlt): a téma a kvíz forrásjegyzete (`forras` + `.md`), az eredmény a **teljes** kitöltés pontja
(a „hibás kérdések” ismétlése nem számít: az a már kérdezett halmazon újra pontoz).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class KvizEredmeny:
    tema: str                 # a jegyzet útja (NFC), amelyből a kvíz kérdezett
    mikor: datetime           # időzónás
    helyes: int
    osszes: int


KvizForras = Callable[[Any, datetime, datetime], Iterable[KvizEredmeny]]     # (cfg, tol, ig) → eredmények
_FORRASOK: dict[str, KvizForras] = {}


def regisztral_kviz_forras(nev: str, fn: KvizForras) -> None:
    """Egy kvíz-adatforrás (a C22 tárolójára); azonos névvel felülírja az előzőt."""
    _FORRASOK[nev] = fn


def van_forras() -> bool:
    return bool(_FORRASOK)


def _ervenyes(e: KvizEredmeny) -> bool:
    return (isinstance(e.mikor, datetime) and e.mikor.tzinfo is not None and isinstance(e.helyes, int)
            and isinstance(e.osszes, int) and e.osszes > 0 and 0 <= e.helyes <= e.osszes)


def kviz_eredmenyek(cfg, tol: datetime, ig: datetime) -> tuple[list[KvizEredmeny], list[str]]:
    """A `[tol, ig)` ablak kvízeredményei az összes regisztrált forrásból → `(eredmények, hibák)`."""
    ki: list[KvizEredmeny] = []
    hibak: list[str] = []
    for nev, fn in list(_FORRASOK.items()):
        try:
            nyers = list(fn(cfg, tol, ig))
        except Exception as e:                    # noqa: BLE001 — egy forrás hibája nem viheti el a többit
            hibak.append(f"kvíz-forrás ({nev}): {e}")
            continue
        rossz = 0
        for e in nyers:
            if not _ervenyes(e):
                rossz += 1
            elif tol <= e.mikor < ig:
                ki.append(KvizEredmeny(unicodedata.normalize("NFC", e.tema), e.mikor, e.helyes, e.osszes))
        if rossz:
            hibak.append(f"kvíz-forrás ({nev}): {rossz} érvénytelen eredmény kimaradt")
    return ki, hibak


def kviz_tar_forras(cfg, tol: datetime, ig: datetime) -> list[KvizEredmeny]:
    """A C22 kvíz-tárolója (`kviz_kitoltes`): a `[tol, ig)` ablak teljes kitöltései. Nincs adatbázis vagy a séma még régi → üres."""
    from .. import tanulas_db
    ki: list[KvizEredmeny] = []
    with tanulas_db.olvaso(cfg, min_verzio=2) as c:
        if c is None:
            return ki
        for r in c.execute("SELECT forras, mikor, pont, osszes FROM kviz_kitoltes WHERE mod = 'teljes' AND forras IS NOT NULL "
                           "AND forras != '' ORDER BY mikor, id"):
            try:
                t = datetime.fromisoformat(r["mikor"])
            except (TypeError, ValueError):
                continue
            t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            if tol <= t < ig:
                ki.append(KvizEredmeny(r["forras"] + ".md", t, int(r["pont"]), int(r["osszes"])))
    return ki


regisztral_kviz_forras("kviz", kviz_tar_forras)
