"""A kérdés normalizálása: a lexikai keresés hajtása (`kereses.hajt`: kisbetű, ékezet nélkül, hossztartó) — egy szabály
a ⌘⇧F-nek, a hibrid keresésnek és a vektor-ág lexikai darabpontjának.

A természetes nyelvű kérdés (pl. „Miért tiltották a céhek az újítást?”) FTS-alakja **VAGY**-kapcsolat: az FTS5 ÉS-e egy
hosszú kérdésre szinte mindig üres. A rangsort a `bm25` adja; a rövid töltelékszavak (≤ 2 betű) és a gyakori kötőszók
kimaradnak, a többi szó előtagként illeszt (a ragozott alak is talál: „céhek” → „céh*” nem, de „céhrendszer” igen —
ezért a tő a szó első `TO_HOSSZ` betűje, mint a mérőkorpusz `tokenek`-je).
"""
from __future__ import annotations

import re

from ..kereses import hajt

TO_HOSSZ = 6                   # a mérőkorpusz (`modulok/eval/kereses/korpusz.tokenek`) csonkolása: ugyanaz a tő
MIN_HOSSZ = 3
# gyakori magyar funkciószók (hajtott alakban): a kérdés szerkezete, nem a tartalma
TOLTELEK = frozenset("""
a az es egy hogy nem is mi mit mik miert mikor hol hogyan melyik milyen ki kik kit kinek mely meg mar csak
van volt lesz lett vannak voltak ezt azt ez az ami amely aki akik amit ahol amikor mert ha de vagy sem
mint ugy igy itt ott el le fel ki be ra re ban ben bol bol nak nek val vel tol rol hoz hez hoz kozott alatt
utan elott szerint miatt soran altal eloszor masodszor mennyi hany honnan hova merre
""".split())


def tokenek(szoveg: str) -> list[str]:
    """A szöveg hajtott szavai (`\\w+`), sorrendben, ismétléssel."""
    return re.findall(r"\w+", hajt(szoveg or ""))


def tovek(szoveg: str) -> list[str]:
    """A tartalmi szavak tövei (`TO_HOSSZ` betűre csonkolva), ismétléssel: a lexikai darabpont és az FTS-kérdés alapja."""
    return [t if t.isdigit() else t[:TO_HOSSZ] for t in tokenek(szoveg)
            if t.isdigit() or (len(t) >= MIN_HOSSZ and t not in TOLTELEK)]


def fts_kerdes(szoveg: str, max_tag: int = 24) -> str | None:
    """A kérdés FTS5-alakja: a tövek előtagos VAGY-kapcsolata (ismétlés nélkül, legfeljebb `max_tag` tag); `None`, ha
    nincs tartalmi szó."""
    latott, tagok = set(), []
    for t in tovek(szoveg):
        if t not in latott:
            latott.add(t)
            tagok.append(f'"{t}"*')
        if len(tagok) >= max_tag:
            break
    return " OR ".join(tagok) if tagok else None


OPERATOR_MINTA = re.compile(r'(?:^|\s)(?:-\S|(?:path|file|tag|line):)|(?:^|\s)/[^/\s]', re.I)


def operatoros(q: str) -> bool:
    """A kérdés a ⌘⇧F lekérdezés-nyelvét használja (`path:`, `file:`, `tag:`, `line:`, tagadás, regex, `OR`, idézőjel,
    zárójel): ilyenkor a lexikai `kereses.keres` szűri a jelölteket, nem a természetes nyelvű VAGY-kérdés."""
    return bool(OPERATOR_MINTA.search(q or "")) or '"' in (q or "") or " OR " in (q or "") or "(" in (q or "")
