"""C30b: a linkjavaslat hasonlósági küszöbének mérése a valódi vault indexén és vektortárán (csak olvas; K205 (b)).

    bin/mos exec var/venv/bin/python -B tests/kezi/hasonlosag_meres.py [--index <vault.sqlite>] [--vektor <vektor.sqlite>]
        [--vault <mappa>] [--jegyzetek 150] [--mag 305] [--veletlen 20] [--kuszobok 0.2,0.25,...] [--kiir 25]

Mit mér. Egy jegyzet és egy másik jegyzet **hasonlósága** a C25c szerint (`Vektortar.jegyzet_hasonlosag`: a jegyzet darabvektorai-
nak normált átlaga és a cél legjobb darabjának koszinusza; ugyanaz, amit a `POST /api/kereses/hasonlosag` ad). Három sokaságon:

- `link`: a jegyzet már meglévő, feloldott jegyzet→jegyzet linkjei (a szerző szándéka: ezek a „helyes” párok közelítése);
- `emlites`: a C30a lexikai javaslatai (`Emlitesek.keres`, egyértelmű cél), azaz amit a szűrő kapna;
- `veletlen`: véletlen jegyzetpárok (a „téves” párok közelítése: két általában egymástól független jegyzet).

Küszöbönként: a sokaság hány %-a marad meg (`pont >= küszöb`). Egy jó küszöb a meglévő linkek zömét megtartja, a véletlen párokat
zömmel kiszűri. A `--kiir` darab, a legalacsonyabb pontú lexikai javaslatot környezetével kiírja kézi ítélethez (JÓ / TÉVES: a
prózai említés valóban erre a jegyzetre utal-e) — ez dönti el, hogy a szűrő a téves javaslatot vagy a jót dobja-e el.

Csak olvas: az indexet és a vektortárat ideiglenes **másolaton** nyitja (a valódi fájlok és a WAL érintetlenek), a jegyzetek
szövegét a vaultból olvassa, semmit nem ír oda; modellt nem tölt. Kilépési kód: 0 (a mérés nem kapu).
"""
import argparse
import random
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from core.asszisztens.beallitasok import beallitasok  # noqa: E402
from core.asszisztens.emlites import Emlitesek  # noqa: E402
from core.index import tar  # noqa: E402
from core.index.hibrid.hasonlo import kisero  # noqa: E402
from core.index.hibrid.vektortar import Vektortar  # noqa: E402
from tests.kezi.emlites_meres import _kornyezet, _MasolatIndex  # noqa: E402


def _szazalek(sorok: list[float], p: float) -> float:
    s = sorted(sorok)
    return s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))] if s else float("nan")


def _eloszlas(nev: str, v: list[float]) -> None:
    if not v:
        print(f"  {nev:<10} (nincs adat)")
        return
    print(f"  {nev:<10} n={len(v):>5}  min {min(v):.3f}  p05 {_szazalek(v, .05):.3f}  p10 {_szazalek(v, .10):.3f}  "
          f"p25 {_szazalek(v, .25):.3f}  p50 {_szazalek(v, .50):.3f}  p75 {_szazalek(v, .75):.3f}  p90 {_szazalek(v, .90):.3f}  "
          f"max {max(v):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", help="a vault.sqlite útja (alap: a konfigurált index)")
    ap.add_argument("--vektor", help="a vektor.sqlite útja (alap: a konfigurált index mappájában)")
    ap.add_argument("--vault", help="a vault mappája (alap: a konfigurált; csak olvasva)")
    ap.add_argument("--jegyzetek", type=int, default=150)
    ap.add_argument("--mag", type=int, default=305)
    ap.add_argument("--veletlen", type=int, default=20, help="jegyzetenként ennyi véletlen cél")
    ap.add_argument("--kuszobok", default="0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60")
    ap.add_argument("--kiir", type=int, default=25)
    ap.add_argument("--sav", action="append", default=[], metavar="ALSO,FELSO",
                    help="a [ALSO, FELSO) pontsáv véletlen mintája kézi ítélethez (többször adható; a `--kiir` helyett)")
    ap.add_argument("--sav-minta", type=int, default=25)
    a = ap.parse_args()

    cfg = config.load()
    forras_db = Path(a.index) if a.index else cfg.path("index") / "vault.sqlite"
    forras_vektor = Path(a.vektor) if a.vektor else forras_db.parent / "vektor.sqlite"
    vault = Path(a.vault) if a.vault else cfg.path("vault")
    for p in (forras_db, forras_vektor):
        if not p.is_file():
            print(f"HIBA: nincs ilyen fájl: {p}", file=sys.stderr)
            return 2
    b = beallitasok(cfg)
    reteg = str(cfg.section("media").get("reteg_mappa", "Média"))
    with tempfile.TemporaryDirectory(prefix="hasonlosag-meres-") as d:
        db, vk = Path(d) / "vault.sqlite", Path(d) / "vektor.sqlite"
        shutil.copy2(forras_db, db)
        shutil.copy2(forras_vektor, vk)
        ix = _MasolatIndex(db)
        tarolo = Vektortar(vk, csak_olvas=True)
        with ix.olvaso() as c:
            md = [(r[0], r[1]) for r in c.execute("SELECT ut, lemez_ut FROM fajl WHERE torolve IS NULL AND tipus = 'md' ORDER BY ut")]
        kizart = lambda u: any(u.startswith(p) for p in b["emlites_kizart"]) or f"/{reteg}/" in "/" + u or kisero(u)  # noqa: E731
        jegyzetek = [(u, l) for u, l in md if not kizart(u)]
        rng = random.Random(a.mag)
        minta = rng.sample(jegyzetek, min(a.jegyzetek, len(jegyzetek)))
        celpool = [u for u, _ in jegyzetek]
        print(f"minta: {len(minta)} jegyzet (mag {a.mag}) a {len(jegyzetek)} élő jegyzetből; vektortár: {tarolo.allapot()}")

        emlites = Emlitesek(cfg, ix)
        linkek, emlitesek, veletlen = [], [], []
        elemek = []                                    # (pont, forrás, cél, szöveg, kezd, veg, forrásszöveg)
        vektor_nelkul = 0
        for u, l in minta:
            pontok = tarolo.jegyzet_hasonlosag(u)
            if pontok is None:
                vektor_nelkul += 1
                continue
            with ix.olvaso() as c:
                celok = {r[0] for r in c.execute(
                    "SELECT DISTINCT l.cel FROM link l JOIN fajl s ON s.id = l.forras_id JOIN fajl t ON t.ut = l.cel "
                    "WHERE s.ut = ? AND s.torolve IS NULL AND t.torolve IS NULL AND t.tipus = 'md' AND l.cel != ?", (u, u))}
            linkek += [pontok[x] for x in celok if x in pontok and not kizart(x)]
            veletlen += [pontok[x] for x in rng.sample(celpool, min(a.veletlen, len(celpool))) if x != u and x in pontok]
            szoveg = (vault / l).read_text(encoding="utf-8", errors="replace")
            for m in emlites.keres(u, szoveg, limit=10 ** 6)["emlitesek"]:
                if m["cel"] and m["cel"] in pontok:
                    emlitesek.append(pontok[m["cel"]])
                    elemek.append((pontok[m["cel"]], u, m["cel"], m["szoveg"], m["kezd"], m["veg"], szoveg))
        print(f"vektor nélküli jegyzet a mintában: {vektor_nelkul}")
        print("\nhasonlóság-eloszlás:")
        _eloszlas("link", linkek)
        _eloszlas("emlites", emlitesek)
        _eloszlas("veletlen", veletlen)
        print("\nküszöb → a sokaság hány %-a marad meg (pont >= küszöb):")
        print(f"  {'küszöb':>7}  {'link':>7}  {'emlites':>8}  {'veletlen':>9}")
        for k in (float(x) for x in a.kuszobok.split(",")):
            def arany(v):
                return f"{100 * sum(1 for x in v if x >= k) / len(v):6.1f}%" if v else "     -"
            print(f"  {k:>7.2f}  {arany(linkek)}  {arany(emlitesek):>8}  {arany(veletlen):>9}")
        elemek.sort(key=lambda x: x[0])
        for sav in a.sav:
            lo, hi = (float(x) for x in sav.split(","))
            benne = [x for x in elemek if lo <= x[0] < hi]
            mintak = random.Random(a.mag + 7).sample(benne, min(a.sav_minta, len(benne)))
            print(f"\n[{lo:.2f}, {hi:.2f}) sáv: {len(benne)} javaslat, véletlen minta {len(mintak)}:")
            for i, (p, u, cel, sz, kezd, veg, forrasszoveg) in enumerate(sorted(mintak), 1):
                print(f"{i:>2}. pont {p:.3f}  {u}\n    „{sz}” → {cel}\n    {_kornyezet(forrasszoveg, kezd, veg)}")
        if a.sav:
            tarolo.close()
            return 0
        print(f"\na legalacsonyabb pontú {min(a.kiir, len(elemek))} lexikai javaslat ({len(elemek)}-ból), kézi ítélethez:")
        for i, (p, u, cel, sz, kezd, veg, forrasszoveg) in enumerate(elemek[:a.kiir], 1):
            print(f"{i:>2}. pont {p:.3f}  {u}\n    „{sz}” → {cel}\n    {_kornyezet(forrasszoveg, kezd, veg)}")
        tarolo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
