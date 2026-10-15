"""K177: az említés-szótár címrész-alakjának mérése valódi jegyzeteken (a discover nem futtatja; csak olvas).

    bin/mos exec var/venv/bin/python -B tests/kezi/emlites_meres.py [--index <vault.sqlite>] [--vault <mappa>]
        [--jegyzetek 150] [--mag 177] [--minta 40] [--max-db 10,0,3,5,20,50] [--csak-valtozatok]

A minta: `--jegyzetek` véletlen (`--mag` magú) élő jegyzet a vaultból (a szótárból kizárt utak és a média-réteg nélkül). Három
változat fut ugyanazon a mintán: `regi` (`emlites_cim_alak = false`: a teljes fájlnév), `szuretlen` (a címrész szűrés nélkül:
`emlites_cim_min_szo = 1`) és `szurt` (a mostani szűrés; az egyszavas ritkasági küszöb `--max-db` értékeire söpörve, az első az
éles beállítás). Változatonként: javaslatok száma (cél nélküli = többértelmű külön), jegyzetenként, a találatok forrás szerint.
A `--minta` darab (alap 40) véletlen javaslatot — jegyzetenként legfeljebb egyet, az első `--max-db` értékű szűrt
változatból — környezetével kiírja, kézi ítélethez („JÓ” / „TÉVES”: a prózai említés valóban erre a jegyzetre utal-e).

Csak olvas: az indexet egy ideiglenes **másolaton** nyitja (a valódi index és a WAL érintetlen), a jegyzetek szövegét a
vaultból olvassa, semmit nem ír oda. Kilépési kód: 0 (a mérés nem kapu: a számok a NAPLO-ba kerülnek).
"""
import argparse
import contextlib
import random
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from core.asszisztens.beallitasok import beallitasok  # noqa: E402
from core.asszisztens.emlites import Emlitesek  # noqa: E402
from core.index import tar  # noqa: E402,F401
from core.index.olvaso import fajl_olvaso  # noqa: E402


class _MasolatIndex:
    """Az indexadatbázis ideiglenes másolata, az `Emlitesek` által hívott felülettel (C33 óta `olvaso()`, `generacio`):
    az olvasó a core csak olvasó útja (`core.index.olvaso.fajl_olvaso`, mint a `mos higienia`/`mos kereses`)."""

    generacio = 1

    def __init__(self, db: Path):
        self.db = db
        self.olvaso = fajl_olvaso(db)
        self._olvaso = self.olvaso          # a régi (privát) név, mint az `IndexOlvaso`-nál


def _mintat_valaszt(ix: _MasolatIndex, cfg, n: int, mag: int) -> list[tuple[str, str]]:
    """`n` véletlen élő jegyzet `(vault-út, lemez-út)`: a kizárt utak és a média-réteg nélkül."""
    b = beallitasok(cfg)
    reteg = str(cfg.section("media").get("reteg_mappa", "Média"))
    with ix.olvaso() as c:
        sorok = [(r[0], r[1]) for r in c.execute("SELECT ut, lemez_ut FROM fajl WHERE torolve IS NULL AND tipus = 'md' ORDER BY ut")]
    sorok = [(u, l) for u, l in sorok if not any(u.startswith(p) for p in b["emlites_kizart"]) and f"/{reteg}/" not in "/" + u]
    return random.Random(mag).sample(sorok, min(n, len(sorok)))


def _futtat(ix, cfg, mintak: list[tuple[str, str]], vault: Path, beall: dict) -> dict[str, list[dict]]:
    cfg.data["asszisztens"] = dict(beall)
    e = Emlitesek(cfg, ix)
    ki: dict[str, list[dict]] = {}
    for ut, lemez in mintak:
        szoveg = (vault / lemez).read_text(encoding="utf-8", errors="replace")
        ki[ut] = e.keres(ut, szoveg, limit=10 ** 6)["emlitesek"]
        ki[ut] = [dict(x, _szoveg=szoveg) for x in ki[ut]]
    return ki


def _osszesit(nev: str, ki: dict[str, list[dict]]) -> None:
    mind = [x for v in ki.values() for x in v]
    jo = [x for x in mind if x["cel"]]
    tobb = [x for x in mind if x["tobbertelmu"]]
    jegyzet_javaslattal = sum(1 for v in ki.values() if any(x["cel"] for x in v))
    forras = Counter(x["forras"] for x in jo)
    print(f"  {nev:<22} javaslat {len(jo):>4} ({len(jo) / max(1, len(ki)):.2f}/jegyzet; {jegyzet_javaslattal} jegyzeten)"
          f"  többértelmű {len(tobb):>4}  forrás {dict(forras)}")


def _kornyezet(szoveg: str, kezd: int, veg: int, sugar: int = 70) -> str:
    a, b = max(0, kezd - sugar), min(len(szoveg), veg + sugar)
    return (("…" if a else "") + szoveg[a:kezd] + "【" + szoveg[kezd:veg] + "】" + szoveg[veg:b] + ("…" if b < len(szoveg) else "")).replace("\n", " ⏎ ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", help="a vault.sqlite útja (alap: a konfigurált index)")
    ap.add_argument("--vault", help="a vault mappája (alap: a konfigurált; csak olvasva)")
    ap.add_argument("--jegyzetek", type=int, default=150)
    ap.add_argument("--mag", type=int, default=177)
    ap.add_argument("--minta", type=int, default=40, help="a kiírt javaslatok száma (kézi ítélethez)")
    ap.add_argument("--max-db", default="10,0,3,5,20,50", help="az egyszavas ritkasági küszöb értékei (vesszővel; az első az éles)")
    ap.add_argument("--csak-valtozatok", action="store_true", help="a minta kiírása nélkül")
    a = ap.parse_args()

    cfg = config.load()
    forras_db = Path(a.index) if a.index else cfg.path("index") / "vault.sqlite"
    vault = Path(a.vault) if a.vault else cfg.path("vault")
    if not forras_db.is_file():
        print(f"HIBA: nincs index: {forras_db}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="emlites-meres-") as d:
        db = Path(d) / "vault.sqlite"
        shutil.copy2(forras_db, db)
        ix = _MasolatIndex(db)
        mintak = _mintat_valaszt(ix, cfg, a.jegyzetek, a.mag)
        print(f"minta: {len(mintak)} jegyzet (mag {a.mag}); index: {forras_db}")
        alap = {k: v for k, v in beallitasok(cfg).items() if k.startswith("emlites_")}
        maxok = [int(x) for x in a.max_db.split(",")]
        print("változatok:")
        _osszesit("regi (teljes név)", _futtat(ix, cfg, mintak, vault, {**alap, "emlites_cim_alak": False}))
        _osszesit("szuretlen (címrész)", _futtat(ix, cfg, mintak, vault, {**alap, "emlites_cim_alak": True, "emlites_cim_min_szo": 1}))
        elsodleges = None
        for m in maxok:
            ki = _futtat(ix, cfg, mintak, vault, {**alap, "emlites_cim_alak": True, "emlites_cim_egyszavas_max_db": m})
            _osszesit(f"szurt (egyszavas ≤ {m})", ki)
            elsodleges = elsodleges or ki
        if a.csak_valtozatok or not elsodleges:
            return 0
        rng = random.Random(a.mag + 1)
        jeloltek = [(u, [x for x in v if x["cel"]]) for u, v in sorted(elsodleges.items())]
        jeloltek = [(u, v) for u, v in jeloltek if v]
        print(f"\nminta a szűrt változatból ({maxok[0]}): {min(a.minta, len(jeloltek))} jegyzet / {len(jeloltek)} javaslatos jegyzetből")
        for i, (u, v) in enumerate(rng.sample(jeloltek, min(a.minta, len(jeloltek))), 1):
            x = rng.choice(v)
            print(f"{i:>2}. {u}\n    „{x['szoveg']}” → {x['cel']}  [{x['forras']}]\n    {_kornyezet(x['_szoveg'], x['kezd'], x['veg'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
