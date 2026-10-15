"""A füzetmappa figyelője (C21) — **80(a), 80(h): kikapcsolva, feltétel nélkül** (CX-011).

A 80(a) döntés óta AI csak kifejezett indításra fut: a figyelt mappa fotóit (`var/fuzet/bejovo`, `[fuzet] mappak`) semmi nem dolgozza
fel magától; a füzetlánc csak kézzel indul (`fuzet.aktivba`, `fuzet_lanc`). A régi `[fuzet] figyelo_be = true` beállítás sem indít
szálat, stat-ellenőrzést vagy `fuzet_automatikus` feladatot. Az osztály csak a core életciklusának és a vezérlő `utolso` mezőjének
felülete marad; a korábbi stat-alapú figyelő (C21) a git történetében érhető el, ha egy új döntés visszahozná.
"""
from __future__ import annotations

import threading

FELADAT = "fuzet_automatikus"
KIKAPCSOLVA = "a füzetmappa figyelése ki van kapcsolva (80(a): a füzetlánc csak kézi indításra fut)"


class Figyelo:
    def __init__(self, cfg, queue, publish=lambda e, **k: None, indulasi_kesleltetes_mp: float | None = None, ora=None):
        self.cfg, self.queue, self.publish = cfg, queue, publish
        self._szal: threading.Thread | None = None   # soha nem indul (a hívók és a tesztek ezt nézik)
        self.utolso: dict = {"ok": KIKAPCSOLVA}

    def bekapcsolva(self) -> bool:
        """80(a): mindig hamis — a konfiguráció sem kapcsolhatja vissza."""
        return False

    def egy_kor(self) -> dict:
        """Egy „ellenőrzés”: nem néz mappát és nem küld be feladatot."""
        return {"ok": KIKAPCSOLVA}

    def indit(self) -> None:
        """80(a): nincs szál, nincs stat-ellenőrzés, nincs újrapróba."""

    def leallit(self) -> None:
        """A core leállításának felülete (nincs mit leállítani)."""
