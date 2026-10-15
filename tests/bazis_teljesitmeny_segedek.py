"""Szintetikus nagy vault a Bases teljesítménymérésekhez (a gépi teszt és a `tests/kezi/bazis_meres.py` is használja)."""
import random

ALLAPOTOK = ["Reading", "Done", "Planned", "Dropped", "Active"]


def szintetikus(v, db: int = 2000, szemely: int = 60, mag: int = 7) -> None:
    """`db` jegyzet 100-as mappákban + `szemely` személy-jegyzet az álvaultba (`v`: Path)."""
    r = random.Random(mag)
    (v / "People").mkdir(parents=True, exist_ok=True)
    for i in range(szemely):
        (v / "People" / f"Szemely {i}.md").write_text(f"---\nBorn: {1900 + i}\n---\n# Személy {i}\n", encoding="utf-8")
    for i in range(db):
        mappa = v / f"X{i // 100:02d} - Mappa" / ""
        mappa.mkdir(parents=True, exist_ok=True)
        tagek = r.choice([["Book"], ["Book", "Reading"], ["Project"], ["Note", "Math/Algebra"]])
        sz = ("---\nTags:\n" + "".join(f"  - {t}\n" for t in tagek) +
              f"Status: {r.choice(ALLAPOTOK)}\nRating: {r.randint(1, 50) / 10}\nPages: {r.randint(50, 900)}\n"
              f"Author: \"[[Szemely {r.randrange(szemely)}]]\"\nStarted: 2026-{r.randint(1, 9):02d}-{r.randint(1, 28):02d}\n"
              f"Authors:\n  - \"[[Szemely {r.randrange(szemely)}]]\"\n  - \"[[Szemely {r.randrange(szemely)}]]\"\n---\n"
              f"# Jegyzet {i}\nSzöveg [[Szemely {r.randrange(szemely)}]] és [[Jegyzet {r.randrange(db)}]] #inline\n")
        (mappa / f"Jegyzet {i}.md").write_text(sz, encoding="utf-8")


NAGY_BAZIS = """filters:
  and:
    - file.ext == "md"
    - 'file.hasTag("book", "project", "note")'
formulas:
  oldal2: Pages * 2 + Rating.round()
  szerzo_szuletes: 'Author.asFile().properties.Born'
  tag_db: file.tags.length
properties:
  Rating:
    displayName: Értékelés
views:
  - type: table
    name: Nagy
    filters: Rating > 1
    order:
      - file.name
      - Status
      - Rating
      - Pages
      - Author
      - Started
      - formula.oldal2
      - formula.szerzo_szuletes
      - formula.tag_db
    sort:
      - property: Rating
        direction: DESC
      - property: file.name
    groupBy:
      property: Status
      direction: ASC
    summaries:
      Rating: Average
      Pages: Sum
      formula.oldal2: Max
      Started: Latest
"""
