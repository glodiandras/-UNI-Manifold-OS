"""A gépszintű modellzár (L23): egyszerre EGY modellt tartó folyamat a gépen, akárki indítja.

`{state}/modell.lock` (a `MANIFOLD_MODELL_ZAR` felülírja), `fcntl.flock` LOCK_EX. A tartalom
`pid <pid> · <repo> · HH:MM:SS`, elengedéskor üres. A második igénylő vár, nem tölt be mellé.
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from typing import Callable


class ZarFoglalt(RuntimeError):
    """A zárat más tartja, és a hívó nem akart várni."""


class Zar:
    def __init__(self, ut: Path, naplo: Callable[[str], None] = lambda s: None):
        self.ut = Path(ut)
        self.naplo = naplo
        self.fd: int | None = None

    @property
    def tartja(self) -> bool:
        return self.fd is not None

    def tartalom(self) -> str:
        try:
            return self.ut.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""

    def megszerez(self, repo: str, varakozas: float | None = None, megszakit: Callable[[], bool] = lambda: False):
        """Vár a zárra (`varakozas` mp-ig, None: korlátlanul); percenként naplózza, ki tartja."""
        if self.fd is not None:
            self._ir(repo)
            return
        self.ut.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.ut, os.O_RDWR | os.O_CREAT, 0o644)
        t0, utolso = time.monotonic(), -60.0
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                most = time.monotonic() - t0
                if varakozas is not None and most >= varakozas or megszakit():
                    os.close(fd)
                    raise ZarFoglalt(f"egy másik folyamat tart modellt ({self.tartalom() or 'ismeretlen'})")
                if most - utolso >= 60:
                    utolso = most
                    self.naplo(f"várok: egy másik folyamat tart modellt ({self.tartalom() or 'ismeretlen'}) "
                               "— egyszerre egy modell fut")
                time.sleep(0.2)
        self.fd = fd
        self._ir(repo)

    def _ir(self, repo: str) -> None:
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, f"pid {os.getpid()} · {repo} · {time.strftime('%H:%M:%S')}".encode(), 0)

    def elenged(self) -> None:
        if self.fd is None:
            return
        try:
            os.ftruncate(self.fd, 0)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
        finally:
            self.fd = None
