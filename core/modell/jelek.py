"""A feladatsor kapujának jelei (memória, rendszer-tétlenség) egy külön szálon frissítve (C29.8, T132; L11).

A kapu (`kapu.Kapu.admit`) az ütemező minden körében, a sor zárja (`Queue._cond`) alatt hívódik; a jelek mérése
alfolyamat (`sysctl`, `ioreg`: legfeljebb 5 s, illetve 3 s időkorláttal). Így egy lassú mérés alatt a feladatsor
minden más művelete (`submit`, `stop`, `get`, a lépések haladása) blokkolt volt. A `Jelek` a méréseket egy háttérszál
végzi néhány másodpercenként, a kapu a gyorsítótárból olvas — alfolyamat nélkül, ütemenként akárhányszor.

- **Elavulás**: ha a háttérszál elindult, de a jel nem friss (az első mérés még nem készült el, vagy a szál elakadt:
  `4 × periódus`), az automatikus munka nem indul (`elavult()`; a kézi feladatot a memória-küszöb tartja, a jel kora nem).
- **Szinkron tartalék**: amíg a háttérszál nincs elindítva (tesztek, a core indulása előtt), a `mem()` és a `hid()` a régi
  módon, hívásra mér — így a kapu a szál nélkül is működik.
- A tétlenség (`hid()`) az utolsó mérés óta eltelt idővel extrapolált (a jel élő, nem „a mérés pillanata”).
- **A mérés hibája** (F6, 2026-10-14) nem nyelődik el: a `hiba` mezőben áll (a kapu indoklása is mondja, miért elavult a
  jel), és az első előfordulás (vagy a hiba szövegének változása) egy naplósor; a sikeres mérés törli.

Gépi tanulás nélkül (a core importálja).
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from . import aktivitas, memoria


class Jelek:
    def __init__(self, mem: Callable[[], int] = memoria.szabad_szazalek,
                 hid: Callable[[], float | None] = aktivitas.rendszer_tetlen_mp, periodus_mp: float = 3.0,
                 ido: Callable[[], float] = time.monotonic):
        self._mem_fn, self._hid_fn = mem, hid
        self.periodus = float(periodus_mp)
        self.ido = ido
        self.hatterben = False                       # a háttérszál dolgozik (az olvasás ekkor gyorsítótárból megy)
        self._zar = threading.Lock()
        self._mem: int | None = None
        self._hid: float | None = None
        self._mert: float | None = None
        self._szal: threading.Thread | None = None
        self._leall = threading.Event()
        self._elso = threading.Event()
        self.hiba: str | None = None                 # az utolsó mérés hibája (a sikeres mérés törli)
        self._naplozott: str | None = None

    # ---------------------------------------------------------------- mérés

    def frissit(self) -> None:
        """Egy mérés mindkét jelre. A hívó szálon fut, a zár NÉLKÜL (az alfolyamatok itt futnak); az eredmény a zár alatt
        kerül a gyorsítótárba."""
        m = self._mem_fn()
        h = self._hid_fn()
        t = self.ido()
        with self._zar:
            self._mem, self._hid, self._mert = m, h, t

    def indit(self, elso_varakozas_mp: float = 2.0) -> None:
        """A háttérszál indítása; legfeljebb `elso_varakozas_mp`-ig vár az első mérésre (addig a jel elavult: az automatikus
        munka nem indul, és az indulást egy beragadt mérés sem tartja fel)."""
        if self._szal is not None:
            return
        self.hatterben = True
        self._szal = threading.Thread(target=self._hurok, name="core-jelek", daemon=True)
        self._szal.start()
        self._elso.wait(elso_varakozas_mp)

    def _hurok(self) -> None:
        while not self._leall.is_set():
            try:
                self.frissit()
                self.hiba = None
            except Exception as e:  # noqa: BLE001 — a mérés hibája nem állíthatja le a szálat; a régi jel elavul
                self.hiba = f"{type(e).__name__}: {str(e)[:200]}"
                if self.hiba != self._naplozott:
                    self._naplozott = self.hiba
                    print(f"[jelek] a rendszerjelek mérése hibára futott ({self.hiba}); amíg így marad, automatikus munka nem "
                          "indul", file=sys.stderr, flush=True)
            self._elso.set()
            self._leall.wait(self.periodus)

    def leallit(self, timeout: float = 2.0) -> None:
        self._leall.set()
        if self._szal is not None:
            self._szal.join(timeout)

    # ---------------------------------------------------------------- olvasás (alfolyamat nélkül, ha a szál dolgozik)

    def mem(self) -> int:
        """A macOS szerint szabad memória százalékban; -1: nem mérhető (a kapu ezt „rendben”-nek veszi)."""
        if not self.hatterben:
            return self._mem_fn()
        with self._zar:
            return -1 if self._mem is None else self._mem

    def hid(self) -> float | None:
        """A billentyűzet és az egér tétlensége másodpercben (az utolsó mérés óta eltelt idővel növelve); `None`: nem mérhető."""
        if not self.hatterben:
            return self._hid_fn()
        with self._zar:
            if self._hid is None or self._mert is None:
                return None
            return self._hid + max(0.0, self.ido() - self._mert)

    def elavult(self) -> bool:
        """A háttérszál dolgozik, de a jel nem friss (az első mérés hiányzik, vagy `4 × periódus`-nál régebbi)."""
        if not self.hatterben:
            return False
        with self._zar:
            return self._mert is None or self.ido() - self._mert > 4 * max(self.periodus, 0.5)
