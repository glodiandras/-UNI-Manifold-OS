"""A gép memóriaállapota `sysctl`-lel (a legacy `helyi_modell` és `bench` mintája). Gépi tanulás nélkül:
a core is importálhatja."""
from __future__ import annotations

import re
import subprocess


def _sysctl(nev: str) -> str:
    try:
        return subprocess.run(["sysctl", "-n", nev], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def szabad_szazalek() -> int:
    """A macOS szerint szabad memória százalékban (`kern.memorystatus_level`); -1, ha nem mérhető."""
    v = _sysctl("kern.memorystatus_level")
    return int(v) if v.isdigit() else -1


def osszes_gb() -> float:
    v = _sysctl("hw.memsize")
    return int(v) / 1e9 if v.isdigit() else 16.0


def swap_mb() -> float:
    m = re.search(r"used\s*=\s*([\d.,]+)M", _sysctl("vm.swapusage"))
    return float(m.group(1).replace(",", ".")) if m else -1.0
