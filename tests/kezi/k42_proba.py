"""K42 próbavault: a link-feloldás forrás-mappa előnye (T139, `core/index/feloldas.py` `_menet`): az Obsidian-összevetéshez.

    var/venv/bin/python -B tests/kezi/k42_proba.py <üres ideiglenes könyvtár>

A könyvtárba (a leendő próbavaultba) pontosan négy jegyzetet ír: `AB/J.md`, `B/J.md`, `A/x.md` (`[[J]]`) és kontrollként
`C/x.md` (`[[J]]`). A 2.0 a forrás-mappa előnyét szöveg-előtagra vizsgálja (`alak(c).startswith(o)`), ezért az `A/x.md`-ből
az `AB/J.md`-re old a rövidebb `B/J.md` helyett; a kérdés, hogy az Obsidian is így tesz-e. A generátor csak a megadott
könyvtárba ír, a valódi vaulthoz és a `var/`-hoz nem nyúl; kiírja a 2.0 mai feloldását is (a `Feloldo` az ideiglenes
fán, index nélkül) és az Obsidianban követendő listát.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core.index import feloldas  # noqa: E402

# út → tartalom; a két `J.md` tartalma különbözik, hogy az Obsidianban látszódjon, melyik nyílt meg
FAK = {
    "AB/J.md": "# J (AB)\n\nEz az AB/J.md.\n",
    "B/J.md": "# J (B)\n\nEz a B/J.md.\n",
    "A/x.md": "[[J]]\n",
    "C/x.md": "[[J]]\n",
}
FORRASOK = ("A/x.md", "C/x.md")


def general(cel) -> list[str]:
    """A próbavault a `cel` (létező, üres) könyvtárba. → a létrehozott utak."""
    cel = Path(cel)
    for ut, szoveg in FAK.items():
        p = cel / ut
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(szoveg.encode("utf-8"))
    return list(FAK)


def ma_a_2_0(cel) -> dict[str, str | None]:
    """Mit old fel ma a 2.0 az `[[J]]` linkre a két forrásból (forrás → cél út)."""
    f = feloldas.Feloldo(sorted(FAK))
    return {src: f.resolve("J", src)[0] for src in FORRASOK}


def lista(cel, ma: dict[str, str | None]) -> str:
    sorok = [
        "K42 — Obsidian-összevetés (link-feloldás, forrás-mappa előny):",
        f"  1. Obsidian › Open folder as vault › {cel}",
        "  2. Nyisd meg az A/x.md-t; az [[J]] linkre ⌘-kattintás (vagy hover): melyik jegyzet nyílik — AB/J vagy B/J?",
        "     (a két J.md első sora különbözik: „# J (AB)” és „# J (B)”)",
        "  3. Ugyanez a C/x.md-ből (kontroll: egyik mappa sem előtagja a C-nek; a legrövidebb út, B/J várt).",
        f"  A 2.0 ma: A/x.md → {ma['A/x.md']} · C/x.md → {ma['C/x.md']}",
        "  Eredmény a NAPLO-ba. Ha az Obsidian A/x.md-ből a B/J.md-t választja, a C31 a forrás-mappa előnyét",
        "  szegmenshatáron vizsgálja (`startswith(o + '/')`, gyökérnél üres előtag).",
    ]
    return "\n".join(sorok)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    cel = Path(argv[1]).expanduser().resolve()
    if cel.exists() and any(cel.iterdir()):
        print(f"A célkönyvtár nem üres: {cel}")
        return 2
    cel.mkdir(parents=True, exist_ok=True)
    utak = general(cel)
    print(f"Próbavault kész: {cel}\n  {len(utak)} jegyzet: {', '.join(utak)}\n")
    print(lista(cel, ma_a_2_0(cel)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
