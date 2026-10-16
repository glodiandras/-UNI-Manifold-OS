"""A `#t=` horgony beírása egy tananyag-jegyzet `Source:` listájának VÉGÉRE (C20b) — a legacy `media.add_media_anchors` szabálya
**tiszta függvényként**: bemenet a jegyzet szövege, kimenet az új szöveg. Az írás a gépi-írás szolgáltatás `csere` művelete (alap-hash:
az olvasott változat), így a „jegyzet megváltozott az igazolás óta” esetet a core 409-cel fogja meg (I21).

A formátum (I27; a vault 121 média-horgonya mind ilyen): `  - "[[FÁJL.mp4#t=MP]]"`, a Source-lista végén. A törzs, a többi mező
és a meglévő horgonyok bájtra változatlanok (utóellenőrzés); inline vagy szokatlan alakú mezőt nem „javít”, hanem visszautasít.
"""
from __future__ import annotations

import re

from .szovegreteg import FM_RE, media_anchors, nfc, parse_fm, split_note


class HorgonyHiba(ValueError):
    """A jegyzet Source-mezője nem írható a legacy formátumában (a hívó a kötést `beiras_hiba`-val zárja, nem javít)."""


def beir(szoveg: str, horgonyok: list[tuple[str, int]]) -> tuple[str, list[tuple[str, int, str]]]:
    """→ (az új szöveg, [(fájl, mp, "irva" | "mar_megvolt")]). Ha nincs mit írni, a szöveg változatlan."""
    m = FM_RE.match(szoveg)
    if not m:
        raise HorgonyHiba("a jegyzetnek nincs frontmattere")
    fm = m.group(1)
    d, _ = parse_fm(fm)
    have = set(media_anchors(d.get("Source", "")))
    out, add = [], []
    for f, t in horgonyok:
        key = (nfc(f), int(t))
        if key in have or key in add:
            out.append(key + ("mar_megvolt",))
        else:
            add.append(key)
            out.append(key + ("irva",))
    if not add:
        return szoveg, out
    lines = fm.split("\n")
    src = [k for k, sor in enumerate(lines) if re.match(r"^Source:", sor)]
    if len(src) != 1:
        raise HorgonyHiba(f"a Source: mező {len(src)}× áll a frontmatterben")
    k = src[0]
    if lines[k].rstrip() != "Source:":
        raise HorgonyHiba("a Source: nem lista-alakú (inline érték) — a formátum nem replikálható")
    e = k + 1
    while e < len(lines) and lines[e].startswith("  - "):
        if not re.match(r'^  - "\[\[[^\]]+\]\]"$', lines[e]):
            raise HorgonyHiba(f"a Source: lista egy eleme szokatlan alakú: {lines[e]!r}")
        e += 1
    if e < len(lines) and not re.match(r"^[A-Za-z_][\w -]*:", lines[e]):
        raise HorgonyHiba(f"a Source: lista után váratlan sor: {lines[e]!r}")
    lines[e:e] = [f'  - "[[{f}#t={t}]]"' for f, t in add]
    uj = szoveg[:m.start(1)] + "\n".join(lines) + szoveg[m.end(1):]
    fm2, body2 = split_note(uj)
    d2, _ = parse_fm(fm2)
    if (body2 != split_note(szoveg)[1] or not set(add) <= set(media_anchors(d2.get("Source", "")))
            or {x: y for x, y in d2.items() if x != "Source"} != {x: y for x, y in d.items() if x != "Source"}):
        raise HorgonyHiba("az utóellenőrzés bukott — a jegyzetet kézzel kell megnézni")
    return uj, out
