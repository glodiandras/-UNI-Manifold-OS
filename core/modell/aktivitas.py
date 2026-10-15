"""Aktivitásjel (1. / 2. döntés): aktív használatkor az automatikus munka nem tölt be modellt és a
kötegek között szünetel; a távol-keret csak tartós tétlenségben jár.

Két forrás, a frissebb számít (a chat döntése, 2026-09-30):
- a felület jele: gépelés, egér → `POST /api/aktivitas` → a core érinti a `{run}/aktivitas` fájlt
  (a worker és a core ugyanazt az mtime-ot olvassa, a worker újraindulása után is);
- a macOS rendszerszintű tétlensége (`ioreg` HIDIdleTime, engedély nélkül): ha másik appban dolgozol,
  az is aktív használat. A `[aktivitas].rendszer_tetlenseg = false` kikapcsolja.

Állapotok: `aktiv` (< `aktiv_mp`), `tetlen`, `tavol` (≥ `tavol_perc`). Gépi tanulás nélkül.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

AKTIV, TETLEN, TAVOL = "aktiv", "tetlen", "tavol"
_HID = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def rendszer_tetlen_mp() -> float | None:
    """A billentyűzet és az egér utolsó használata óta eltelt idő (HIDIdleTime, ns → s); None, ha nem mérhető."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4", "-r", "-k", "HIDIdleTime"],
                             capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = _HID.search(out)
    return int(m.group(1)) / 1e9 if m else None


class Aktivitas:
    def __init__(self, fajl: Path, aktiv_mp: float = 120, tavol_perc: float = 15, rendszer: bool = True,
                 ido: Callable[[], float] = time.time, hid: Callable[[], float | None] = rendszer_tetlen_mp,
                 hid_gyorsitotar_mp: float = 2.0):
        self.fajl = Path(fajl)
        self.aktiv_mp = float(aktiv_mp)
        self.tavol_mp = float(tavol_perc) * 60
        self.rendszer = rendszer
        self.ido = ido
        self.hid = hid
        self._hid_cache: tuple[float, float | None] = (-1e18, None)
        self._hid_ttl = hid_gyorsitotar_mp
        self._utolso_erintes = -1e18

    @classmethod
    def beallitasbol(cls, b, **kw) -> "Aktivitas":
        a = b.aktivitas
        return cls(b.run / "aktivitas", a["aktiv_mp"], a["tavol_perc"], bool(a["rendszer_tetlenseg"]), **kw)

    def jel(self, min_koz_mp: float = 1.0) -> None:
        """A felület jele: legfeljebb `min_koz_mp`-enként érinti a fájlt."""
        most = self.ido()
        if most - self._utolso_erintes < min_koz_mp:
            return
        self._utolso_erintes = most
        self.fajl.parent.mkdir(parents=True, exist_ok=True)
        self.fajl.touch()
        os.utime(self.fajl, (most, most))

    def felulet_tetlen_mp(self) -> float:
        try:
            return max(0.0, self.ido() - self.fajl.stat().st_mtime)
        except OSError:
            return float("inf")

    def rendszer_tetlen_mp(self) -> float | None:
        if not self.rendszer:
            return None
        t, v = self._hid_cache
        most = self.ido()
        if most - t >= self._hid_ttl:
            v = self.hid()
            self._hid_cache = (most, v)
            return v
        return None if v is None else v + (most - t)

    def tetlen_mp(self) -> float:
        r = self.rendszer_tetlen_mp()
        f = self.felulet_tetlen_mp()
        return f if r is None else min(f, r)

    def allapot(self) -> str:
        t = self.tetlen_mp()
        if t < self.aktiv_mp:
            return AKTIV
        return TAVOL if t >= self.tavol_mp else TETLEN

    def publikus(self) -> dict:
        t = self.tetlen_mp()
        return {"allapot": self.allapot(), "tetlen_mp": None if t == float("inf") else round(t)}
