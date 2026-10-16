"""Reguláris kifejezések védelme a megbízhatatlan rétegek (a munkatér `workspace.toml`-ja és `schema.json`-ja) ellen.

A vault utazik, szinkronizálódik, letölthető: az általa hozott minta (`[video] tema_minta`, a séma `h1_minta` / `fajlnev_minta`
mezői) a core szálán fut mappanevekre és jegyzetcímekre. Egy beágyazott korlátlan ismétlés (`(a+)+$`) katasztrofális
visszalépést okoz, és a core szálát tetszőleges ideig leköti. A Python `re` modulnak nincs időkorlátja, ezért a mintát elfogadás
előtt vizsgáljuk: a lefordított fa egy ismétlése (`+`, `*`, `{n,m}`) alatt nem állhat újabb, 1-nél többször ismétlő elem, ha
bármelyikük korlátlan vagy nagy (> `NAGY`). A szokásos, korlátos alakok (`([A-Z]{1,3})(\\d{2})`) átmennek.

Importmentes (csak a szabványos könyvtár): a doctor, a `config` és a `kiserok` is használja."""
from __future__ import annotations

import re

try:                                            # Python 3.11+: `re._parser`; régebben `sre_parse`
    from re import _constants as _c
    from re import _parser as _p
except ImportError:                             # pragma: no cover — a futtató Python (3.14) a fentit adja
    import sre_constants as _c                  # type: ignore[no-redef]
    import sre_parse as _p                      # type: ignore[no-redef]

NAGY = 16                                       # ennél több ismétlés (vagy korlátlan) „nagy”
MAX_HOSSZ = 200                                 # a minta legnagyobb hossza (a `config.MAX_REGEX`-szel egyező)

_ISMETLO = {"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"}


def _nagy(maximum: int) -> bool:
    return maximum == _c.MAXREPEAT or maximum > NAGY


def _alfak(nev: str, av):
    """Egy elem beágyazott részfái (az ismétlő elemekét a hívó kezeli)."""
    if nev == "SUBPATTERN":
        yield av[3]
    elif nev == "BRANCH":
        yield from av[1]
    elif nev in ("ASSERT", "ASSERT_NOT"):
        yield av[1]
    elif nev == "ATOMIC_GROUP":
        yield av
    elif nev == "GROUPREF_EXISTS":
        yield av[1]
        if av[2] is not None:
            yield av[2]


def _beagyazott(fa, van_kulso: bool, nagy_kulso: bool) -> bool:
    for op, av in fa:
        nev = getattr(op, "name", str(op))
        if nev in _ISMETLO:
            _, maximum, test = av
            if maximum > 1:
                if van_kulso and (nagy_kulso or _nagy(maximum)):
                    return True
                if _beagyazott(test, True, nagy_kulso or _nagy(maximum)):
                    return True
            elif _beagyazott(test, van_kulso, nagy_kulso):
                return True
            continue
        for alfa in _alfak(nev, av):
            if _beagyazott(alfa, van_kulso, nagy_kulso):
                return True
    return False


def veszelyes(minta: str) -> str | None:
    """→ `None`, ha a minta elfogadható; különben a hiba kódja: `regex_hossz`, `regex` (nem fordítható) vagy
    `regex_beagyazott_ismetles` (katasztrofális visszalépést engedő beágyazott ismétlés)."""
    if not isinstance(minta, str) or len(minta) > MAX_HOSSZ:
        return "regex_hossz"
    try:
        re.compile(minta)
        fa = _p.parse(minta)
    except (re.error, RecursionError, OverflowError, ValueError):
        return "regex"
    try:
        return "regex_beagyazott_ismetles" if _beagyazott(fa, False, False) else None
    except RecursionError:
        return "regex"
