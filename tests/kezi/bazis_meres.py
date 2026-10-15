"""C12 teljesítménymérés a VALÓDI vaulton, csak olvasva (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/bazis_meres.py [--ismetles N] [--books-base <vault-út>]

A vault útja a `config/os.toml`-ból jön (a `MOS_VAULT` környezeti változó felülírja — így álvaulton is kipróbálható).
A szkript a vaultba nem ír: az indexet ideiglenes mappába építi (`{tmp}` alatt, a végén törlődik), a `.base` szövegét
(ha van) csak olvassa, a lekérdezés tiszta (`Bazisok.lekerdez` nem ír).

Mért nézetek (a `.base` szövege a szkriptben áll, a vault tulajdonságnevei nélkül, kivéve a Books-alakot):
  - Books-alak: a vault `X03 - Books/Books.base` fájlja, ha létezik (`--books-base` más utat ad); különben a beépített
    megfelelője (`file.tags == ["Book"]`, kártyák, `imageFit: contain`, `cardSize: 420`);
  - Címke-szűrős táblázat: a vault leggyakoribb címkéjére (`file.hasTag`), rendezés `file.mtime` szerint;
  - Csoportosított összesítős: minden `.md`, `groupBy: file.folder`, három összesítő;
  - Képletes: két képlet (`file.links.length`, `file.tags.length`) és rendezés képletre;
  - Teljes vault: szűrő nélkül minden fájl (a legnagyobb sorszám).
Mindegyikre: a hideg lekérdezés (a `Tabla` építésével), majd N meleg ismétlés (alap: 15) — a core ideje (`ido_ms`) és a
teljes hívás ideje (a felületre kerülő JSON előállításával, HTTP nélkül), medián és maximum.

Cél: 2000 soron a teljes (core + rajz) < 300 ms, a core melegen ≤ 80 ms. Kilépési kód: 0, ha minden nézet a 300 ms-os
korláton belül van és hibátlanul futott; 1, ha túllép vagy hibás.
"""
import shutil
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from core.bazis.adat import Tar  # noqa: E402
from core.bazis.api import Bazisok  # noqa: E402
from core.index import indexelo  # noqa: E402

KORLAT_MS = 300
CEL_MS = 80
BOOKS_UT = "X03 - Books/Books.base"                          # vault-relatív

BOOKS_BEEPITETT = """\
filters:
  and:
    - 'file.tags == ["Book"]'
views:
  - type: cards
    name: Books
    order:
      - file.name
      - note.Author
      - note.Rating
    sort:
      - property: file.name
        direction: ASC
    image: note.cover
    imageFit: contain
    cardSize: 420
"""

CSOPORTOS = """\
filters: file.ext == "md"
views:
  - type: table
    name: Mappak
    order:
      - file.name
      - file.size
      - file.mtime
      - file.folder
    groupBy:
      property: file.folder
      direction: ASC
    summaries:
      file.size: Sum
      file.mtime: Latest
      file.name: Filled
"""

KEPLETES = """\
formulas:
  linkek: file.links.length
  cimkek: file.tags.length
filters: file.ext == "md"
views:
  - type: table
    name: Kepletek
    order:
      - file.name
      - formula.linkek
      - formula.cimkek
    sort:
      - property: formula.linkek
        direction: DESC
    summaries:
      formula.linkek: Sum
"""

TELJES = """\
views:
  - type: table
    name: Minden
    order:
      - file.name
      - file.ext
      - file.size
      - file.mtime
"""


def leggyakoribb_cimke(tabla) -> str | None:
    """A vault leggyakoribb, idézőjel- és visszaper-mentes címkéje (a címke-szűrős nézethez)."""
    db: dict[str, int] = {}
    for s in tabla.sorok:
        for c in s.cimkek:
            db[c] = db.get(c, 0) + 1
    for c, _ in sorted(db.items(), key=lambda kv: (-kv[1], kv[0])):
        if '"' not in c and "\\" not in c:
            return c
    return None


def meres(b: Bazisok, ix, szoveg: str, ismetles: int) -> dict:
    """Egy nézet mérése: hideg, majd `ismetles` meleg hívás."""
    b.tar = Tar(ix)                                           # hideg: a `Tabla` építésével
    t0 = time.perf_counter()
    v = b.lekerdez({"szoveg": szoveg})
    hideg = (time.perf_counter() - t0) * 1000
    ki = {"ok": v["ok"], "hibak": [h for h in v["hibak"] if "db" not in h], "sorhibak": sum(h.get("db", 0) for h in v["hibak"]),
          "sor": len(v["sorok"]), "osszes": v["osszes"], "hideg": hideg, "core": [], "teljes": []}
    if not v["ok"]:
        return ki
    for _ in range(ismetles):
        t0 = time.perf_counter()
        v = b.lekerdez({"szoveg": szoveg})
        ki["teljes"].append((time.perf_counter() - t0) * 1000)
        ki["core"].append(v["ido_ms"])
    return ki


def main(argv: list[str]) -> int:
    ismetles, books_ut = 15, BOOKS_UT
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--ismetles" and args:
            ismetles = int(args.pop(0))
        elif a == "--books-base" and args:
            books_ut = args.pop(0)
        else:
            print(__doc__)
            return 2

    cfg0 = config.load()
    d = probamappa(cfg0, "c12-meres", szkript="bazis_meres.py")
    cfg = cfg_elkulonitve(d, cfg0)                       # a valódi vault csak olvasva; minden más út a próbamappába
    vault = cfg.path("vault")
    ix = indexelo.Index(cfg)
    ix.figyelo_fajta = "lekerdezes"
    ix.lekerdezes_mp = 3600
    ix.indit()
    ix.var(300)
    rossz = 0
    try:
        b = Bazisok(cfg, ix)
        tabla = b.tar.tabla()
        print(f"[bázis-mérés] vault: {vault} — {len(tabla.sorok)} fájl az indexben; {ismetles} meleg ismétlés/nézet\n")
        books = BOOKS_BEEPITETT
        forras = "beépített"
        p = vault / books_ut
        if p.is_file():
            books, forras = p.read_text(encoding="utf-8"), f"a vault {books_ut} fájlja"
        esetek = [(f"Books-alak ({forras})", books)]
        cimke = leggyakoribb_cimke(tabla)
        if cimke:
            esetek.append((f"Címke-szűrős táblázat (#{cimke})",
                           'filters: file.hasTag("' + cimke + '")\nviews:\n  - type: table\n    name: Cimke\n'
                           "    order:\n      - file.name\n      - file.folder\n      - file.mtime\n      - file.size\n"
                           "      - file.tags\n    sort:\n      - property: file.mtime\n        direction: DESC\n"))
        esetek += [("Csoportosított összesítős", CSOPORTOS), ("Képletes", KEPLETES), ("Teljes vault", TELJES)]

        print(f"{'nézet':44} {'sor':>6} {'hideg':>8} {'core med':>9} {'core max':>9} {'teljes med':>11} {'max':>7}  ítélet")
        for nev, szoveg in esetek:
            m = meres(b, ix, szoveg, ismetles)
            if not m["ok"] or m["hibak"]:
                rossz += 1
                print(f"{nev:44} HIBA: {m['hibak']}")
                continue
            cm, tm = statistics.median(m["core"]), statistics.median(m["teljes"])
            if tm >= KORLAT_MS:
                itelet = f"TÚLLÉP (≥ {KORLAT_MS} ms)"
                rossz += 1
            elif cm <= CEL_MS:
                itelet = f"cél ({CEL_MS} ms) teljesül"
            else:
                itelet = f"korláton belül, de a core > {CEL_MS} ms"
            kicsi = "" if m["sor"] >= 2000 else "  [< 2000 sor]"
            print(f"{nev:44} {m['sor']:>6} {m['hideg']:>6.0f}ms {cm:>7.1f}ms {max(m['core']):>7.1f}ms {tm:>9.1f}ms "
                  f"{max(m['teljes']):>5.0f}ms  {itelet}{kicsi}" + (f"  (sorhiba: {m['sorhibak']})" if m["sorhibak"] else ""))
    finally:
        ix.leallit()
        shutil.rmtree(d, ignore_errors=True)                  # a saját var/tmp mappánk
    print()
    print(("TÚLLÉPÉS vagy hiba: " + str(rossz) + " nézet") if rossz else
          f"RENDBEN: minden nézet a {KORLAT_MS} ms-os korláton belül (cél: core ≤ {CEL_MS} ms melegen)")
    return 1 if rossz else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
