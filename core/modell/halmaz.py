"""Az aranyhalmazok aktuális verziója router-feladatonként (C19, T050): a router csak ezzel a verzióval kalibrált sort fogad el.

A forrás a `{modulok}/eval/<feladat>/feladat.py` `VERZIO`-ja és `ROUTER_FELADAT`-ja (a `mos eval` szerződése). A modulokat a
worker egyszer, lustán tölti be, és a fájl módosítási idejére (a feladat.py és a mappa `*.json`-jai) újratölti: a K27 utáni
jóváhagyás vagy egy új aranyverzió a worker újraindítása nélkül is érvényes. Hibás vagy hiányzó modul: a feladatnak nincs
aktuális verziója → a router arra a feladatra nem választ kalibrált modellt (zárva hibázik).
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path


def _lenyomat(eval_dir: Path) -> tuple:
    """Az összes feladatmappa `.py`/`.json` fájljának módosítási ideje: egy feladat más mappa aranyát is olvashatja
    (a `fuzet_fejezet` az `ocr_kezi`-ét, a `beagyazas` a `kereses`-ét), ezért a lenyomat közös."""
    try:
        return tuple(sorted((str(p.relative_to(eval_dir)), p.stat().st_mtime_ns) for p in eval_dir.glob("*/*")
                            if p.suffix in (".py", ".json") and p.is_file()))
    except OSError:
        return ()


class Verziok:
    """`verziok(router_feladat) -> str | None`: az aranyhalmaz aktuális verziója."""

    def __init__(self, modulok: Path):
        self.eval_dir = Path(modulok) / "eval"
        self._lock = threading.Lock()
        self._lny: tuple | None = None
        self._ki: dict[str, str] = {}

    def _modul(self, mappa: Path) -> tuple[str | None, str | None]:
        ut = mappa / "feladat.py"
        try:
            spec = importlib.util.spec_from_file_location(f"mos_halmaz_{mappa.name}", ut)
            mod = importlib.util.module_from_spec(spec)
            elotte = list(sys.path)
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.path[:] = elotte                       # a feladat.py-k sys.path-módosítása ne szivárogjon a workerbe
            return str(getattr(mod, "ROUTER_FELADAT", mappa.name)), str(mod.VERZIO)
        except Exception:  # noqa: BLE001 — hibás modul: nincs aktuális verzió (zárva hibázik)
            return None, None

    def osszes(self) -> dict[str, str]:
        if not self.eval_dir.is_dir():
            return {}
        with self._lock:
            lny = _lenyomat(self.eval_dir)
            if lny != self._lny:
                ki: dict[str, str] = {}
                for mappa in sorted(p for p in self.eval_dir.iterdir() if (p / "feladat.py").is_file()):
                    router, verzio = self._modul(mappa)
                    if router and verzio:
                        ki[router] = verzio
                self._lny, self._ki = lny, ki
            return dict(self._ki)

    def __call__(self, router_feladat: str) -> str | None:
        return self.osszes().get(router_feladat)
