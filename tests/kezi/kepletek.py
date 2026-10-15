"""C08 kész-feltétele: a vault minden képlete a szerkesztő elemzőjével és KaTeX-beállításával (a discover
nem futtatja).

    var/venv/bin/python -B tests/kezi/kepletek.py        (vagy: MOS_ROOT=… python …)

1. A vitest (Node, `app/vitest.kezi.config.ts`) a `app/tests/kezi/kepletek.kezi.ts`-t futtatja: bejárja a
   vaultot (csak olvasva), minden képletet a szerkesztő KaTeX-beállításával, `throwOnError`-ral renderel,
   és JSON-riportot ír a `{runs}/kepletek-<idő>.json`-ba.
2. A fájlonkénti képleteket összeveti a vault-index (`{index}/vault.sqlite`, csak olvasva) `keplet`
   táblájával: minden eltérő fájl a sorral és a TeX-szel listázódik, hogy az ok megnevezhető legyen.

Kilépési kód: 0, ha nincs renderelési hiba (a darabszám-eltérés csak riport, nem hiba).
"""
import collections
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import md_db, vitest_futtat  # noqa: E402


def normal(tex: str) -> str:
    """Összevetési kulcs: szóköz és idézetjel (`>`) nélkül — az index a többsoros idézett képletbe a `>`-t
    is beleveszi, a szerkesztő nem."""
    return re.sub(r"[\s>]+", "", tex)


def index_kepletek(db: Path) -> dict[str, list[tuple[int, bool, str]]]:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sorok = c.execute("select f.ut, k.sor, k.blokk, k.forras from keplet k join fajl f on f.id = k.fajl_id "
                          "where f.torolve is null").fetchall()
    finally:
        c.close()
    ki: dict[str, list[tuple[int, bool, str]]] = collections.defaultdict(list)
    for ut, sor, blokk, forras in sorok:
        ki[ut].append((sor, bool(blokk), forras or ""))
    return ki


def main() -> int:
    cfg = config.load()
    vault = cfg.path("vault")
    runs = cfg.path("runs")
    runs.mkdir(parents=True, exist_ok=True)
    riport_ut = runs / time.strftime("kepletek-%Y%m%d-%H%M%S.json")
    print(f"[képletek] vault: {vault}")
    p = vitest_futtat("tests/kezi/kepletek.kezi.ts", dict(MOS_KEZI_VAULT=str(vault), MOS_KEZI_RIPORT=str(riport_ut)),
                      md_db(vault), 300)                          # időkorlát a jegyzetek számához igazítva
    if not riport_ut.exists():
        print(p.stdout[-3000:], p.stderr[-2000:])
        print("[képletek] HIBA: nem készült riport")
        return 2
    r = json.loads(riport_ut.read_text(encoding="utf-8"))
    print(f"[képletek] {r['fajlok']} jegyzet, {r['fajlok_keplettel']} képlettel; {r['kepletek']} képlet "
          f"({r['soron_beluli']} soron belüli, {r['megjelenitesi']} megjelenítési); {r['ido_mp']} s")
    print(f"[képletek] renderelési hiba: {len(r['hibak'])}")
    for h in r["hibak"]:
        print(f"    {h['ut']}:{h['sor']}  {'$$' if h['display'] else '$'}{h['tex'][:120]}")
        print(f"        {h['hiba'][:160]}")
    for kod, s in sorted(r["szigorusag"].items(), key=lambda x: -x[1]["db"]):
        print(f"[képletek] figyelmeztetés (nem hiba): {kod} × {s['db']}, pl. {s['peldak'][0]['ut']}:"
              f"{s['peldak'][0]['sor']} — {s['peldak'][0]['uzenet'][:90]}")
    for kulcs, s in r["metrika"].items():
        print(f"[képletek] figyelmeztetés (nem hiba): {kulcs} × {s['db']}")

    # összevetés az indexszel
    ix = index_kepletek(cfg.path("index") / "vault.sqlite")
    sajat = r["fajlonkent"]
    ix_ossz = sum(len(v) for v in ix.values())
    print(f"[képletek] index: {ix_ossz} képlet {len(ix)} fájlban "
          f"({sum(1 for v in ix.values() for k in v if k[1])} megjelenítési); a szerkesztő: {r['kepletek']}")
    elteres = 0
    for ut in sorted(set(ix) | set(sajat)):
        a = collections.Counter((s, d, normal(t)) for s, d, t in ix.get(ut, []))
        b = collections.Counter((k["sor"], k["display"], normal(k["tex"])) for k in sajat.get(ut, []))
        if a == b:
            continue
        csak_ix, csak_sajat = a - b, b - a
        elteres += 1
        print(f"  ≠ {ut}: index {sum(a.values())}, szerkesztő {sum(b.values())}")
        for (s, d, t), n in sorted(csak_ix.items())[:6]:
            print(f"      csak az indexben   :{s} {'$$' if d else '$'} {t[:90]}" + (f" ×{n}" if n > 1 else ""))
        for (s, d, t), n in sorted(csak_sajat.items())[:6]:
            print(f"      csak a szerkesztőben:{s} {'$$' if d else '$'} {t[:90]}" + (f" ×{n}" if n > 1 else ""))
    print(f"[képletek] eltérő fájl: {elteres}; riport: {riport_ut}")
    print("RENDBEN" if not r["hibak"] else f"HIBA: {len(r['hibak'])} renderelési hiba")
    return 0 if not r["hibak"] else 1


if __name__ == "__main__":
    sys.exit(main())
