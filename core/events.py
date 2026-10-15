"""Esemény-busz a core → felület irányhoz (WS). Szálbiztos; előfizetőnként korlátos sor.

A felület az eseményekből frissít, nem pollingol (ARCHITECTURE 2.). A haladás-eseményeket kulcsonként
legfeljebb `RATE` per másodperc sűrűséggel adjuk tovább; az állapotváltás mindig átmegy.
"""
from __future__ import annotations

import queue
import threading
import time

RATE = 4.0
LAST_MAX = 256                  # a ritkítás-kulcsok száma, amely fölött a lejártak kitakarítódnak (F7)
MAX_SOR = 256


class Subscription:
    """Egy előfizető korlátos sora. Túlcsorduláskor a legrégebbi esemény elvész, de nem némán (1. audit L7, T107): a
    következő `get` előbb egy `{"tipus": "kimaradt", "db": n}` jelzést ad, hogy a kliens újraszinkronizáljon."""

    def __init__(self, bus: "Bus"):
        self._bus = bus
        self.q: queue.Queue = queue.Queue(MAX_SOR)
        self.kimaradt = 0                       # a túlcsordulás miatt elvesztett események száma az utolsó jelzés óta
        self._zar = threading.Lock()
        self._elo: dict | None = None           # a jelzés miatt visszatartott (már kivett) esemény

    def _jelzes(self) -> dict | None:
        with self._zar:
            db, self.kimaradt = self.kimaradt, 0
        return {"tipus": "kimaradt", "db": db} if db else None

    def get(self, timeout: float | None = None) -> dict | None:
        j = self._jelzes()
        if j:
            return j
        if self._elo is not None:
            e, self._elo = self._elo, None
            return e
        try:
            e = self.q.get(timeout=timeout)
        except queue.Empty:
            return None
        j = self._jelzes()                      # a várakozás alatt túlcsordult: a jelzés megelőzi az eseményt
        if j:
            self._elo = e
            return j
        return e

    def close(self) -> None:
        self._bus._leave(self)


class Bus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: list[Subscription] = []
        self._last: dict[str, float] = {}

    def subscribe(self) -> Subscription:
        s = Subscription(self)
        with self._lock:
            self._subs.append(s)
        return s

    def _leave(self, s: Subscription) -> None:
        with self._lock:
            if s in self._subs:
                self._subs.remove(s)

    def publish(self, event: dict, throttle_key: str | None = None) -> bool:
        """Esemény mindenkinek. `throttle_key`: a haladás-esemény kulcsa (ritkítva). Igaz, ha kiment."""
        with self._lock:
            if throttle_key is not None:
                now = time.monotonic()
                if now - self._last.get(throttle_key, 0.0) < 1.0 / RATE:
                    return False
                if len(self._last) >= LAST_MAX:
                    # F7 (2026-10-14): a ritkítás kulcsai (feladatonként egy) nem gyűlnek korlátlanul — a ritkítási ablaknál
                    # régebbi bejegyzés már semmit nem ritkít, elhagyható
                    self._last = {k: t for k, t in self._last.items() if now - t < 1.0 / RATE}
                self._last[throttle_key] = now
            subs = list(self._subs)
        for s in subs:
            try:
                s.q.put_nowait(event)
            except queue.Full:          # a lassú kliens a legrégebbit veszíti (jelzéssel: `kimaradt`), a core nem áll meg
                try:
                    s.q.get_nowait()
                    s.q.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass
                with s._zar:
                    s.kimaradt += 1
        return True
