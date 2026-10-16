"""A feladatsor kapuja (a C03 `admit` horga): az automatikus munkák (index, kártya, összefoglaló +
grafikon, füzetmappa) CSAK ezen át indulnak.

- automatikus feladat: legalább `indulasi_szunet_mp` üzemidő (D8: a megnyitás nem indít munkát), nincs
  aktív használat (aktivitásjel), és a szabad memória a küszöb fölött;
- modelligényes (`modell`) kézi feladat: csak a memória-küszöb (a felhasználó kérte);
- minden más: szabad.
A jeleket (memória, rendszer-tétlenség) a `jelek.Jelek` külön szálon méri (C29.8, T132): a kapu a sor zárja alatt fut, ott
alfolyamat nem hívódhat. Gépi tanulás nélkül (a core importálja).
"""
from __future__ import annotations

import time
from typing import Callable

from . import memoria
from .aktivitas import AKTIV, Aktivitas


class Kapu:
    def __init__(self, aktivitas: Aktivitas, min_szabad_szazalek: float, indulasi_szunet_mp: float,
                 mem: Callable[[], int] = memoria.szabad_szazalek, ido: Callable[[], float] = time.monotonic,
                 jelek=None):
        self.aktivitas = aktivitas
        self.min_szabad = float(min_szabad_szazalek)
        self.indulasi_szunet = float(indulasi_szunet_mp)
        self.jelek = jelek                      # C29.8 (T132): a mérést külön szál végzi, a kapu gyorsítótárból olvas
        self.mem = jelek.mem if jelek is not None else mem
        self.ido = ido
        self.indult = ido()
        self.utolso_ok = ""

    def _mem_ok(self) -> bool:
        lvl = self.mem()
        return lvl < 0 or lvl >= self.min_szabad

    def _ok(self, automatikus: bool, modell: bool) -> str:
        """Miért nem indulhat a munka (üres: indulhat)."""
        if automatikus:
            if self.ido() - self.indult < self.indulasi_szunet:
                return "az app nemrég indult"
            if self.jelek is not None and self.jelek.elavult():
                # fail-closed: mérés nélkül nem indul automatikus munka; a mérés hibája az indoklásban látszik (F6)
                hiba = getattr(self.jelek, "hiba", None)
                return "a rendszerjelek még nem mértek / elavultak" + (f" (a mérés hibája: {hiba})" if hiba else "")
            if self.aktivitas.allapot() == AKTIV:
                return "aktív használat"
        if (automatikus or modell) and not self._mem_ok():
            return "kevés a szabad memória"
        return ""

    def admit(self, t) -> bool:
        self.utolso_ok = self._ok(bool(getattr(t, "automatikus", False)), "modell" in getattr(t, "resources", ()))
        return not self.utolso_ok

    def automatikus_szabad(self) -> bool:
        """Indulhat-e most egy modell nélküli automatikus háttérmunka (C25c: a PDF-szöveg kinyerése) — ugyanazok a feltételek,
        mint az `admit`-nál, de a feladatsor `utolso_ok` jelzését (a vezérlő mutatja) nem írja felül."""
        return not self._ok(True, False)
