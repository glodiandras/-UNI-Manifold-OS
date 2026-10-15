"""Próbafeladat a vezérlő kipróbálásához (C17): álfeladat, amely valódi gépi commitot ír a vaultba.

**Élesben nincs ilyen feladattípus**: csak `MOS_PROBA_FELADAT=1` mellett regisztrálódik (a tesztek és a
`tests/kezi/proba_app.py` állítják; ott a vault az APFS-klón). A lépés a gépi-írás szolgáltatáson át ír
(`core/gepi_kliens.py`, C16.5) — közvetlenül nem nyúl a vaulthoz —, így a gépi commit hordozza a `Mos-Kor` és a
`Mos-Feladat` trailert, a felület értesít, és a vezérlő „Mit változtatott” nézete és a visszavonás végigpróbálható.

    python -m core.probafeladat lepes <i> <n> <mp>      # a feladatsor lépése (nem kézzel hívandó)
"""
from __future__ import annotations

import os
import sys
import time

from . import gepi_kliens, tasks

TIPUS = "proba"
MAPPA = "_Proba"
MAX_DARAB, MAX_MP = 20, 120


def _terv(cfg, p: dict, stop: str):
    try:
        n, mp = int(p.get("darab", 3)), float(p.get("mp", 2))
    except (TypeError, ValueError):
        raise tasks.Invalid("a darab egész, az mp szám legyen") from None
    if not 1 <= n <= MAX_DARAB or not 0 <= mp <= MAX_MP:
        raise tasks.Invalid(f"darab 1–{MAX_DARAB}, mp 0–{MAX_MP}")
    lepesek = [tasks.Step(f"Próba-lépés {i + 1}/{n}",
                          [sys.executable, "-B", "-m", "core.probafeladat", "lepes", str(i + 1), str(n), str(mp)],
                          str(cfg.root)) for i in range(n)]
    return lepesek, f"{n} lépés, lépésenként {mp:g} s; mindegyik egy jegyzetet ír a {MAPPA}/ mappába", []


def regisztral() -> None:
    """A próbafeladat regisztrálása (idempotens)."""
    if TIPUS not in tasks.REGISTRY:
        tasks.register(tasks.TaskType(TIPUS, "Próbafeladat", _terv, frozenset({"vault"})))


def _lepes(i: int, n: int, mp: float) -> int:
    if os.environ.get("MOS_PROBA_FELADAT") != "1":
        print("a próbafeladat csak MOS_PROBA_FELADAT=1 mellett fut (csak klónon)", file=sys.stderr)
        return 2
    fid = os.environ.get("MOS_FELADAT") or "kezi"
    rel = f"{MAPPA}/Próbafeladat {fid} - {i}.md"
    # a lépés nem ír közvetlenül a vaultba: a gépi-írás szolgáltatáson át, egy tétel = egy gépi commit (C16.5)
    gepi_kliens.ir(gepi_kliens.uj_kor("LEPES"), tetel=f"proba-{i}", forras="mos-lepes",
                   uzenet=f"próbafeladat: {i}/{n}. jegyzet", modell=None, muveletek=[gepi_kliens.uj(
                       rel, "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
                            f"# Próbafeladat {fid} - {i}\n\nA vezérlő próbafeladata írta ({fid}; {i}/{n}). Visszavonható.\n",       # a H1 a fájlnév (T044)
                       osztaly="normal")])
    print(f"[manifold-progress] 50%", flush=True)
    print(f"Kész: {rel}", flush=True)
    t0 = time.monotonic()
    while time.monotonic() - t0 < mp:      # a leállítás SIGTERM-je a ciklusban éri
        time.sleep(0.1)
    print("[manifold-progress] 100%", flush=True)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "lepes":
        return _lepes(int(argv[2]), int(argv[3]), float(argv[4]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
