"""C33 (1. pont): az index és a keresés egy 10 000 jegyzetes SZINTETIKUS vaulton — a célidők mérése (a discover nem futtatja).

    bin/mos exec <python> -B tests/kezi/nagy_vault_meres.py [--jegyzet 10000] [--megtart]

Az álvault a próbamappában készül (determinisztikus, `random.Random(33)`): 50 tantárgyi mappa, jegyzetenként frontmatter
(Tags, NN-linkek), 2–6 fejezet, 6 wikilink (feloldott és feloldatlan), címkék, feladat, néhány képlet, ~1,5–3 KB szöveg.
A valódi vaulthoz és `var/`-hoz nem nyúl (`_kornyezet.cfg_elkulonitve`). Mért (folyamaton belül, HTTP nélkül):

- hideg építés (üres index), újraindulás (csak stat), a DB mérete;
- keresés: szó, két szó, kifejezés, `tag:`, `path:`, regex, tagadás — medián és maximum (5 ismétlés);
- gráf (`graf_api`) hidegen és a gyorsítótárból (`graf_valasz`, a szerkezeti generáció szerint), graf-meta;
- Bases `Tabla`: teljes építés, és egy tartalmi mentés utáni inkrementális frissítés;
- a saját írás látszása (a `sajat_iras` visszatéréséig) és egy külső módosítás látszása a keresésben;
- a folyamat csúcs-RSS-e.

Célok (C06, C33): hideg építés ≤ 30 s; újraindulás ≤ 3 s; a keresés mediánja ≤ 200 ms (a regex és a tagadás ≤ 1 s); a gráf
hidegen ≤ 1 s, gyorsítótárból ≤ 5 ms; a Bases inkrementális frissítése ≤ 50 ms; a mentés látszása ≤ 200 ms. Kilépési kód 0:
minden cél teljesül.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import resource
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
from core.index import indexelo  # noqa: E402

SZAVAK = ("derivált integrál mátrix vektor halmaz függvény határérték sorozat valószínűség eloszlás reakció molekula "
          "egyensúly erő energia impulzus hullám rezgés áram feszültség ellenállás sejt fehérje enzim örökítés evolúció "
          "forradalom királyság háború béke szerződés reform költő regény vers dráma stílus korszak").split()


def alvault(gyoker: Path, n: int) -> None:
    rnd = random.Random(33)
    (gyoker / ".obsidian").mkdir(parents=True)
    mappak = [f"{chr(65 + i % 26)}{i:02d} - Tantárgy {i}" for i in range(50)]
    nevek = [f"{mappak[i % 50]}/{i:05d} - Jegyzet {i}" for i in range(n)]
    for i, nev in enumerate(nevek):
        p = gyoker / f"{nev}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        linkek = [Path(nevek[rnd.randrange(n)]).name for _ in range(5)] + [f"Nincs ilyen {rnd.randrange(500)}"]
        cimkek = " ".join(f"#{rnd.choice(SZAVAK)}" for _ in range(2))
        test = []
        for f in range(rnd.randint(2, 6)):
            test.append(f"## {rnd.choice(SZAVAK).capitalize()} {f}\n")
            test.append(" ".join(rnd.choice(SZAVAK) for _ in range(rnd.randint(40, 90))) + "\n")
        if i % 7 == 0:
            test.append("$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$\n")
        if i % 5 == 0:
            test.append(f"- [ ] feladat {i} 📅 2026-10-{1 + i % 28:02d}\n")
        p.write_text(f"---\nTags: {mappak[i % 50].split(' - ')[0]}\nNN:\n  - \"[[{linkek[0]}]]\"\n---\n# Jegyzet {i}\n\n"
                     + " ".join(f"[[{x}]]" for x in linkek) + f"\n\n{cimkek}\n\n" + "\n".join(test), encoding="utf-8")


def ido(f, n: int = 5) -> tuple[float, float]:
    idok = []
    for _ in range(n):
        t0 = time.perf_counter()
        f()
        idok.append((time.perf_counter() - t0) * 1000)
    return statistics.median(idok), max(idok)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jegyzet", type=int, default=10_000)
    ap.add_argument("--megtart", action="store_true")
    a = ap.parse_args(argv)
    cfg = config.load()
    d = probamappa(cfg, "c33-nagy-vault", megtart=a.megtart)
    vault = d / "Manifold"
    eredmeny: list[tuple[str, float, float, bool]] = []

    def cel(nev, ertek, hatar):
        eredmeny.append((nev, ertek, hatar, ertek <= hatar))
        print(f"  {'✓' if ertek <= hatar else '✗'} {nev}: {ertek:.1f} (cél ≤ {hatar:g})", flush=True)
    try:
        t0 = time.perf_counter()
        alvault(vault, a.jegyzet)
        print(f"[nagy vault] {a.jegyzet} jegyzet generálva {time.perf_counter() - t0:.1f} s alatt: {vault}", flush=True)
        pcfg = cfg_elkulonitve(d, cfg, vault=vault)
        pcfg.data["index"] = {**pcfg.section("index"), "figyelo": "lekerdezes", "lekerdezes_mp": 3600}
        ix = indexelo.Index(pcfg)
        t0 = time.perf_counter()
        ix.indit()
        ix.var(600)
        hideg = time.perf_counter() - t0
        allapot = ix.allapot()
        print(f"[nagy vault] index: {allapot['fajlok']} fájl, {allapot['jegyzetek']} jegyzet; hiba: {allapot['hiba']}")
        cel("hideg építés (s)", hideg, 30)
        ix.leallit()
        db = Path(pcfg.path("index")) / "vault.sqlite"
        print(f"  DB: {db.stat().st_size / 1e6:.0f} MB")
        ix = indexelo.Index(pcfg)
        ix.figyelo_fajta, ix.lekerdezes_mp = "lekerdezes", 3600
        t0 = time.perf_counter()
        ix.indit()
        ix.var(600)
        cel("újraindulás, csak stat (s)", time.perf_counter() - t0, 3)
        for nev, q, hatar in (("keresés: szó", "integrál", 200), ("keresés: két szó", "mátrix vektor", 200),
                              ("keresés: kifejezés", '"függvény határérték"', 200), ("keresés: tag:", "tag:#reform", 200),
                              ("keresés: path:", "path:A00 energia", 200), ("keresés: regex", "/forr[a-z]+ás/", 1000),
                              ("keresés: tagadás", "evolúció -sejt", 1000)):
            med, mx = ido(lambda: ix.kereses(q))
            cel(f"{nev} medián (ms)", med, hatar)
        med, _ = ido(lambda: ix.graf_api(), 3)
        cel("gráf hidegen (graf_api, ms)", med, 1000)
        ix.graf_valasz()
        med, _ = ido(lambda: ix.graf_valasz(), 5)
        cel("gráf a gyorsítótárból (ms)", med, 5)
        from core.index import graf_meta
        med, _ = ido(lambda: graf_meta.graf_meta(ix), 3)
        cel("graf-meta hidegen (ms)", med, 1000)
        t = Tar(ix)
        t0 = time.perf_counter()
        t.tabla()
        cel("Bases Tabla teljes építés (ms)", (time.perf_counter() - t0) * 1000, 2000)
        cel_ut = next(iter(sorted(vault.rglob("*.md"))))
        rel = str(cel_ut.relative_to(vault))
        tartalom = cel_ut.read_text(encoding="utf-8") + "\nmentett zebracsikós szó\n"
        cel_ut.write_text(tartalom, encoding="utf-8")
        t0 = time.perf_counter()
        ix.sajat_iras(rel, hashlib.sha1(tartalom.encode()).hexdigest())
        cel("a saját mentés látszása (ms)", (time.perf_counter() - t0) * 1000, 200)
        talalat = ix.kereses("zebracsikós")["talalatok"]
        cel("a mentett szó kereshető (0 = igen)", 0 if talalat and talalat[0]["ut"] == rel else 1, 0)
        t0 = time.perf_counter()
        t.tabla()
        cel(f"Bases inkrementális frissítés (ms, mód: {t.utolso_mod})", (time.perf_counter() - t0) * 1000, 50)
        masik = sorted(vault.rglob("*.md"))[500]
        masik.write_text(masik.read_text(encoding="utf-8") + "\nkülső okapiszó\n", encoding="utf-8")
        t0 = time.perf_counter()
        ix.jelez([str(masik.relative_to(vault))])
        while not ix.kereses("okapiszó")["talalatok"] and time.perf_counter() - t0 < 5:
            time.sleep(0.005)
        cel("külső módosítás látszása a keresésben (ms)", (time.perf_counter() - t0) * 1000, 200)
        csucs = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
        print(f"  a folyamat csúcs-RSS-e: {csucs:.0f} MB (index, keresés, gráf, Bases együtt, egy folyamatban)")
        ix.leallit()
    finally:
        if not a.megtart:
            shutil.rmtree(d, ignore_errors=True)
    rossz = [e for e in eredmeny if not e[3]]
    print("RENDBEN: minden cél teljesül" if not rossz else f"ELTÉR: {len(rossz)} cél nem teljesül: {[e[0] for e in rossz]}")
    return 0 if not rossz else 1


if __name__ == "__main__":
    sys.exit(main())
