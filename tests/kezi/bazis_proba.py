"""C12 paritás-próbavault: 40 jegyzet + csatolmányok + 5 `.base` fájl (a `docs/C12-TERV.md` Ellenőrzés szakasza, P1–P5).

    var/venv/bin/python -B tests/kezi/bazis_proba.py <üres ideiglenes könyvtár>

A könyvtárba (a leendő próbavaultba) generál: a gépi paritás-teszt (`tests/test_bazis_paritas.py`) álvaulton használja,
a kézi K11 lépésben (`tests/kezi/bazis_paritas.py`) a felhasználó Obsidian 1.11.7-ben nyitja meg, és az egyes nézeteket
CSV-be exportálja. A generátor csak a megadott könyvtárba ír; a valódi vaulthoz nem nyúl.

Tervezési szabályok (hogy az eltérés mindig kiértékelő-hibára utaljon, ne a rendezés szabályaira):
  - az útvonalak ASCII-k, és egy mappán belül egyik név sem előtagja a másiknak → a `file.path` szerinti rendezés
    minden szokásos rendezési szabály szerint ugyanaz;
  - minden nézet `order`-ének első eleme a `file.path`, és minden nézet rendezése egyértelmű (`file.path`, vagy egy
    egyedi értékű tulajdonság);
  - a dátum-aritmetika csak rögzített frontmatter-dátumokon megy (nincs `now()`), a nyári időszámítás-váltást nem
    átlépő tartományokon, hónap-végi szorítás nélkül;
  - a tulajdonságok típusa a `.obsidian/types.json`-ban rögzített (az Obsidian és a 2.0 ugyanabból olvas);
  - minden `.md` jegyzetnek van `NN` kulcsa (üres lista), hogy a lista-metódusok sehol ne hívódjanak `null`-on.
"""
import json
import struct
import sys
import zlib
from pathlib import Path

# ---------------------------------------------------------------- adatok

# (név, címkék, Status, Rating, Pages, szerző, Started, borító, forrás-PDF)
KONYVEK = [
    ("Atomic Habits", ["Book"], "Reading", 4.5, 320, "James Clear", "2026-09-01", "abra-a.png", None),
    ("Deep Work", ["Book"], "Done", 4, 300, "Cal Newport", "2026-03-10", None, None),
    ("Dune", ["Book"], "Planned", None, 600, "Frank Herbert", None, None, None),
    ("Godel Escher Bach", ["Book", "Math"], "Dropped", 4.5, 777, "Douglas Hofstadter", "2026-02-01", None, None),
    ("Meditations", ["Book", "Philosophy"], "Done", 5, 254, "Marcus Aurelius", "2026-04-05", None, None),
    ("Sapiens", ["Book"], "Done", 5, 500, "Yuval Harari", "2026-05-20", "abra-b.png", "doc-a.pdf"),
    ("Thinking Fast", ["Book"], "Reading", 4, 499, "Daniel Kahneman", "2026-08-15", None, None),
    ("Ulysses", ["Novel"], "Done", 4, 730, "James Joyce", "2026-01-12", None, None),
    ("Walden", ["Book"], "Dropped", 2, 352, "Henry Thoreau", "2026-06-06", None, None),
    ("Zero to One", ["Book"], "Done", 3.5, 224, "Peter Thiel", "2026-07-07", None, None),
]

# (név, Status, Hours, Start, Due)
PROJEKTEK = [
    ("Alpha", "Done", 12, "2026-01-10", "2026-02-09"),
    ("Beta", "Done", 30, "2026-01-28", "2026-02-28"),
    ("Gamma", "Active", 80, "2026-02-15", "2026-05-15"),
    ("Delta", "Dropped", 2, "2026-03-01", "2026-03-02"),
    ("Epsilon", "Active", 120, "2026-04-20", "2026-10-20"),
    ("Zeta", "Planned", 0, "2026-07-02", "2026-12-31"),
    ("Eta", "Done", 8, "2026-08-01", "2026-08-15"),
    ("Theta", "Active", 15, "2026-09-01", "2026-09-09"),
]

# (név, Born, Country, Bio, Email) — `None`: a kulcs hiányzik
SZEMELYEK = [
    ("James Clear", 1986, "USA", "Habits writer", "james@example.com"),
    ("Cal Newport", 1982, "USA", "", "cal@example.org"),
    ("Yuval Harari", 1976, "Israel", "Historian", None),
    ("Frank Herbert", 1920, "USA", "Science fiction", "frank@example.com"),
    ("Daniel Kahneman", 1934, "Israel", "Psychologist  ", None),
    ("Peter Thiel", 1967, None, "", "peter@example.net"),
]

# (név, Ido) — a `Ido` datetime típusú
NAPLO = [
    ("Hetfo", "2026-03-02T09:30:00"),
    ("Kedd", "2026-03-03T22:15:00"),
    ("Szerda", "2026-03-04T23:45:00"),
    ("Csutortok", "2026-03-05T08:00:00"),
]

# (név, címkék, NN-linkek, törzs)
JEGYZETEK = [
    ("Algebra", ["Math"], [], "Alap fogalmak."),
    ("Analizis", ["Math"], [], "Lasd [[Algebra]] alapjait."),
    ("Differencial", ["Math"], ["Analizis"], "Derivalt."),
    ("Fizika", ["Physics"], [], "Alap fogalmak."),
    ("Halmaz", ["Math"], ["Algebra"], "Halmazok."),
    ("Integral", ["Math"], ["Analizis", "Differencial"], "Lasd [[Matrix]]."),
    ("Logika", ["Math"], ["Halmaz"], "Allitasok."),
    ("Matrix", ["Math"], ["Algebra"], "Matrixok."),
    ("Mechanika", ["Physics"], ["Fizika"], "Mozgas."),
    ("Olvasonaplo", ["Book"], [], "Jegyzet a konyvekrol."),
    ("Optika", ["Physics"], ["Fizika", "Matrix"], "Fenyutak."),
    ("Vektor", ["Math"], ["Algebra", "Fizika"], "Iranyitott szakasz."),
]

# név → méret bájtban (pontos, a `file.size` összehasonlításokhoz)
CSATOLMANYOK = {"abra-a.png": 90, "abra-b.png": 150, "abra-c.png": 300, "doc-a.pdf": 500, "doc-b.pdf": 80}

TIPUSOK = {
    "Tags": "tags", "Status": "text", "Rating": "number", "Pages": "number", "Author": "text", "Started": "date",
    "cover": "text", "Source": "text", "NN": "multitext", "Hours": "number", "Start": "date", "Due": "date",
    "Born": "number", "Country": "text", "Bio": "text", "Email": "text", "Ido": "datetime",
}

# ---------------------------------------------------------------- a .base fájlok

P1 = """\
filters:
  and:
    - 'file.tags == ["Book"]'
views:
  - type: cards
    name: Konyvek
    order:
      - file.path
      - file.name
      - note.Author
      - note.Rating
    sort:
      - property: file.path
        direction: ASC
    image: note.cover
    imageFit: contain
    cardSize: 420
"""

P2 = """\
filters:
  or:
    - and:
        - file.inFolder("Konyvek")
        - or:
            - Rating >= 4.5
            - and:
                - Rating >= 4
                - Pages < 400
        - not:
            - Status == "Dropped"
    - and:
        - file.inFolder("Csatolmanyok")
        - file.size > 100
        - file.ext != "pdf"
    - not:
        - file.ext == "md"
        - file.inFolder("Csatolmanyok")
views:
  - type: table
    name: Szuro
    order:
      - file.path
      - file.ext
      - file.size
      - note.Rating
      - note.Pages
    sort:
      - property: file.path
        direction: ASC
"""

P3 = """\
formulas:
  hatarido: 'Start + "30d"'
  hossz_nap: '(Due - Start) / 86400000'
  zaras: 'Ido + "4h"'
  doksi: 'date("2024-12-01") + "1M" + "4h" + "3m"'
views:
  - type: table
    name: Lejarat
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Projektek")
        - 'Due - "1M" >= Start'
        - 'Start + "30d" < date("2026-08-01")'
    order:
      - file.path
      - note.Start
      - note.Due
      - formula.hatarido
      - formula.hossz_nap
      - formula.doksi
    sort:
      - property: file.path
        direction: ASC
  - type: table
    name: Idopont
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Naplo")
        - '(Ido + "4h").day != Ido.day'
        - Ido.hour >= 9
    order:
      - file.path
      - note.Ido
      - formula.zaras
    sort:
      - property: file.path
        direction: ASC
"""

P4 = """\
formulas:
  nn_db: NN.length
  fizikas: 'NN.contains(link("Fizika"))'
views:
  - type: table
    name: Kapcsolat
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Jegyzetek")
        - or:
            - 'NN.contains(link("Fizika"))'
            - 'file.hasLink("Algebra")'
    order:
      - file.path
      - note.NN
      - formula.nn_db
    sort:
      - property: file.path
        direction: ASC
  - type: table
    name: Formula-szuro
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Jegyzetek")
        - 'formula.nn_db >= 2 || formula.fizikas'
    order:
      - file.path
      - formula.nn_db
      - formula.fizikas
    sort:
      - property: file.path
        direction: ASC
"""

P5 = """\
formulas:
  fordit: 'file.basename.replace(/(\\w+) (\\w+)/, "$2, $1")'
  cim: 'file.basename.lower().title()'
  rovid: 'file.basename.slice(0, 3)'
  betuk: 'file.basename.replace(" ", "").length'
views:
  - type: table
    name: Szoveg
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Szemelyek")
        - 'file.basename.lower().containsAny("ar", "er")'
        - 'file.basename.split(" ")[1].length != 5'
    order:
      - file.path
      - formula.fordit
      - formula.cim
      - formula.rovid
      - formula.betuk
    sort:
      - property: file.path
        direction: ASC
  - type: table
    name: Regex
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Szemelyek")
        - '!Email.isEmpty()'
        - '/@example\\.(com|org)$/.matches(Email)'
    order:
      - file.path
      - note.Email
    sort:
      - property: file.path
        direction: ASC
  - type: table
    name: Limit
    filters:
      and:
        - file.ext == "md"
        - file.inFolder("Szemelyek")
        - or:
            - '!Bio.isEmpty()'
            - Country.isEmpty()
    order:
      - file.path
      - note.Born
      - note.Bio
    sort:
      - property: Born
        direction: DESC
    limit: 3
"""

BAZISOK = {
    "Bases/P1 Konyvek.base": P1,
    "Bases/P2 Szuro.base": P2,
    "Bases/P3 Datum.base": P3,
    "Bases/P4 Kapcsolat.base": P4,
    "Bases/P5 Fuggveny.base": P5,
}

# A kézi K11 lépés exportjai: (base útja, nézet neve) → a CSV fájlneve (a felhasználó így menti el).
NEZETEK = [
    ("Bases/P1 Konyvek.base", "Konyvek"),
    ("Bases/P2 Szuro.base", "Szuro"),
    ("Bases/P3 Datum.base", "Lejarat"),
    ("Bases/P3 Datum.base", "Idopont"),
    ("Bases/P4 Kapcsolat.base", "Kapcsolat"),
    ("Bases/P4 Kapcsolat.base", "Formula-szuro"),
    ("Bases/P5 Fuggveny.base", "Szoveg"),
    ("Bases/P5 Fuggveny.base", "Regex"),
    ("Bases/P5 Fuggveny.base", "Limit"),
]


def csv_nev(fajl: str, nezet: str) -> str:
    """A nézet CSV-exportjának elvárt fájlneve: `<base neve kiterjesztés nélkül> - <nézet neve>.csv`."""
    return f"{Path(fajl).stem} - {nezet}.csv"


# ---------------------------------------------------------------- generálás

def _png(meret: int) -> bytes:
    """Érvényes 1×1-es PNG, a IEND után nullákkal a pontos méretre töltve."""
    def chunk(tipus: bytes, adat: bytes) -> bytes:
        return struct.pack(">I", len(adat)) + tipus + adat + struct.pack(">I", zlib.crc32(tipus + adat))
    b = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
         chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))
    assert meret >= len(b), meret
    return b + b"\x00" * (meret - len(b))


def _pdf(meret: int) -> bytes:
    """Egyszerű PDF-fejléc, a végén megjegyzés-sorokkal a pontos méretre töltve."""
    b = b"%PDF-1.4\n"
    return b + (b"%" * (meret - len(b) - 1) + b"\n" if meret > len(b) else b"")


def _fm(kulcsok: list) -> str:
    """Frontmatter-szöveg: `kulcsok` = [(kulcs, érték)]; a lista tömbként, a `None` érték kimarad."""
    sorok = ["---"]
    for k, v in kulcsok:
        if v is None:
            continue
        if isinstance(v, list):
            if not v:
                sorok.append(f"{k}: []")
            else:
                sorok.append(f"{k}:")
                sorok += [f"  - {e}" for e in v]
        elif isinstance(v, str) and (v == "" or v.startswith(("[", "{")) or v != v.strip() or ": " in v or "@" in v):
            sorok.append(f'{k}: "{v}"')
        else:
            sorok.append(f"{k}: {v}")
    sorok.append("---")
    return "\n".join(sorok) + "\n"


def jegyzetek() -> dict[str, str]:
    """A 40 jegyzet: út → szöveg."""
    ki = {}
    for nev, cimkek, status, rating, oldal, szerzo, kezdet, boritok, forras in KONYVEK:
        fm = _fm([("Tags", cimkek), ("Status", status), ("Rating", rating), ("Pages", oldal),
                  ("Author", f"[[{szerzo}]]"), ("Started", kezdet),
                  ("cover", f"[[{boritok}]]" if boritok else None),
                  ("Source", f"[[{forras}]]" if forras else None), ("NN", [])])
        ki[f"Konyvek/{nev}.md"] = fm + f"# {nev}\n"
    for nev, status, ora, kezdet, hatarido in PROJEKTEK:
        fm = _fm([("Tags", ["Project"]), ("Status", status), ("Hours", ora), ("Start", kezdet), ("Due", hatarido),
                  ("NN", [])])
        ki[f"Projektek/{nev}.md"] = fm + f"# {nev}\n"
    for nev, szuletes, orszag, bio, email in SZEMELYEK:
        fm = _fm([("Tags", ["Person"]), ("Born", szuletes), ("Country", orszag), ("Bio", bio), ("Email", email),
                  ("NN", [])])
        ki[f"Szemelyek/{nev}.md"] = fm + f"# {nev}\n"
    for nev, ido in NAPLO:
        ki[f"Naplo/{nev}.md"] = _fm([("Tags", ["Daily"]), ("Ido", ido), ("NN", [])]) + f"# {nev}\n"
    for nev, cimkek, nn, torzs in JEGYZETEK:
        fm = _fm([("Tags", cimkek), ("NN", [f'"[[{x}]]"' for x in nn])])
        ki[f"Jegyzetek/{nev}.md"] = fm + f"# {nev}\n{torzs}\n"
    return ki


def ellenoriz_nevek(utak) -> None:
    """A rendezés egyértelműsége: egy mappán belül egyik fájlnév (kiterjesztés nélkül) sem előtagja a másiknak."""
    mappak: dict[str, list[str]] = {}
    for ut in utak:
        mappa, _, nev = ut.rpartition("/")
        assert nev.isascii(), ut
        mappak.setdefault(mappa, []).append(nev.rsplit(".", 1)[0].lower())
    for mappa, nevek in mappak.items():
        for a in nevek:
            for b in nevek:
                assert a == b or not b.startswith(a), f"{mappa}: {a!r} előtagja {b!r}-nek"


def general(cel) -> dict:
    """A próbavault a `cel` (létező, üres) könyvtárba. → {"jegyzetek": [utak], "csatolmanyok": […], "bazisok": […]}."""
    cel = Path(cel)
    ki = jegyzetek()
    for ut, szoveg in ki.items():
        _ir(cel / ut, szoveg.encode("utf-8"))
    for nev, meret in CSATOLMANYOK.items():
        _ir(cel / "Csatolmanyok" / nev, _png(meret) if nev.endswith(".png") else _pdf(meret))
    _ir(cel / "Naplo/Plan.canvas", b'{"nodes":[],"edges":[]}')
    for ut, szoveg in BAZISOK.items():
        _ir(cel / ut, szoveg.encode("utf-8"))
    _ir(cel / ".obsidian/types.json", json.dumps({"types": TIPUSOK}, indent=2).encode("utf-8"))
    osszes = list(ki) + [f"Csatolmanyok/{n}" for n in CSATOLMANYOK] + ["Naplo/Plan.canvas"] + list(BAZISOK)
    ellenoriz_nevek(osszes)
    return {"jegyzetek": list(ki), "csatolmanyok": [f"Csatolmanyok/{n}" for n in CSATOLMANYOK], "bazisok": list(BAZISOK)}


def _ir(p: Path, bajtok: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bajtok)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    cel = Path(argv[1]).expanduser().resolve()
    if cel.exists() and any(cel.iterdir()):
        print(f"A célkönyvtár nem üres: {cel}")
        return 2
    cel.mkdir(parents=True, exist_ok=True)
    k = general(cel)
    print(f"Próbavault kész: {cel}\n  {len(k['jegyzetek'])} jegyzet, {len(k['csatolmanyok'])} csatolmány, "
          f"{len(k['bazisok'])} .base fájl (+ Naplo/Plan.canvas, .obsidian/types.json)\n")
    print("K11 — Obsidian-paritás (Obsidian 1.11.7):")
    print("  1. Nyisd meg a mappát vaultként az Obsidianban.")
    print("  2. Mindegyik nézetet nyisd meg, és exportáld CSV-be (nézet-eszköztár → Results → Export CSV),")
    print("     a CSV-ket EZEKEN a neveken mentsd el egy külön mappába:")
    for fajl, nezet in NEZETEK:
        print(f"       {csv_nev(fajl, nezet)}")
    print("  3. Futtasd:  bin/mos exec var/venv/bin/python -B tests/kezi/bazis_paritas.py "
          f"'{cel}' <a CSV-k mappája>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
