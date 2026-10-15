"""C13 kész-feltétele: a gráfnézet csúcs- és élhalmaza pontosan a core gráfja, a VALÓDI vaulton (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/graf_nezet_paritas.py

Csak olvas: a vaultot (ideiglenes indexet épít a `{tmp}` alatt, a végén törlődik). A core `graf_api()`, `fa()` és
`graf_meta()` kimenetét (és a graph.json színcsoportjait) JSON-ba menti, majd a vitest (Node, `app/vitest.kezi.config.ts`)
`app/tests/kezi/graf_nezet.kezi.ts`-e a felület `GrafAdat` modelljével összeveti: csúcsok (halmaz és sorrend), irányított
élek (halmaz), irányítatlan élek, az alap nézet láthatósága, a színcsoportok támogatottsága.

Kilépési kód: 0, ha minden egyezik.
"""
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa, vitest_futtat  # noqa: E402
from core.index import graf_meta, indexelo  # noqa: E402


def main() -> int:
    cfg = config.load()
    vault = cfg.path("vault")
    d = probamappa(cfg, "c13-paritas", szkript="graf_nezet_paritas.py")
    ix = indexelo.Index(cfg_elkulonitve(d, cfg))
    ix.figyelo_fajta = "lekerdezes"
    ix.lekerdezes_mp = 3600
    ix.indit()
    ix.var(300)
    try:
        beall = graf_meta.graf_beallitasok(vault)
        adat = {"graf": ix.graf_api(), "fa": ix.fa(), "meta": graf_meta.graf_meta(ix),
                "csoportok": [{"lekerdezes": c["lekerdezes"], "szin": c["szin"]} for c in beall.get("szincsoportok", [])]}
    finally:
        ix.leallit()
    fajl = d / "graf.json"
    fajl.write_text(json.dumps(adat, ensure_ascii=False), encoding="utf-8")
    print(f"[graf-paritás] core: {len(adat['graf']['csucsok'])} csúcs, {len(adat['graf']['elek'])} irányított él; "
          f"{len(adat['csoportok'])} színcsoport a graph.json-ból")
    riport = d / "riport.txt"
    p = vitest_futtat("tests/kezi/graf_nezet.kezi.ts", dict(MOS_KEZI_GRAF=str(fajl), MOS_KEZI_RIPORT=str(riport)), 0, 0,
                      alap_ms=600_000)                            # egy gráf: fix, bőséges időkorlát
    print(p.stdout[-3000:])
    if p.returncode:
        print(f"ELTÉR — a JSON: {fajl}")
        return 1
    print("[graf-paritás] " + (riport.read_text(encoding="utf-8") if riport.exists() else "(nincs összegzés)"))
    shutil.rmtree(d)                                        # a saját var/tmp próbamappánk
    print("RENDBEN: a nézet csúcs- és élhalmaza a core gráfja")
    return 0


if __name__ == "__main__":
    sys.exit(main())
