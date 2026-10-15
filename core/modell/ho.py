"""Hőfigyelés (TERV 4. / 5., ventilátor nélküli M4): nem beégetett szünetek, hanem mérés.

Modellenként a generálási token/s a minta (csak `min_token`-nél hosszabb generálásból). Az alapszint
az első `alap_minta` minta mediánja, és a `hoalap` táblában megmarad; ha később tartósan gyorsabb a
modell, az alapszint felfelé követi. Ha az utolsó `ablak` minta mediánja a `kuszob × alap` alá esik,
hűtési szünet jár (`hutes_mp`). A küszöböt a C19 méri be.
"""
from __future__ import annotations

import statistics
from collections import defaultdict, deque

from .kalibracio import Tabla


class Ho:
    def __init__(self, beallitas: dict, tabla: Tabla):
        self.c = beallitas
        self.tabla = tabla
        self._kezdeti: dict[str, list[float]] = defaultdict(list)
        self._ablak: dict[str, deque] = defaultdict(lambda: deque(maxlen=int(self.c["ablak"])))
        self.szunetek = 0

    def alap(self, modell: str) -> float | None:
        return self.tabla.hoalap(modell)

    @staticmethod
    def kulcs(modell: str, prompt_tokenek: int | None = None) -> str:
        """Az alapszint kulcsa: a modell és a kontextus-méret osztálya (log2 a prompt-tokenekből). C19: a K28-ban a
        `glm_ocr` alapszintje a rövid képlet-kivágásokon 208 token/s lett, a füzetoldalakon (két kép, hosszú kontextus)
        ugyanez a modell 88 token/s-mal fut — a feladatfüggő sebesség 25 hamis „hűtési szünetet” adott (a `qwen3_vl_4b`-nél
        is 25-öt), miközben egy futáson belül a token/s nem esett 0,86 alá. A hő az azonos méretű kérések közti esést jelenti."""
        if not prompt_tokenek or prompt_tokenek <= 0:
            return modell
        return f"{modell}@{int(prompt_tokenek).bit_length()}"

    def minta(self, modell: str, tps: float, tokenek: int, prompt_tokenek: int | None = None) -> bool:
        """Egy generálás mérése; igaz, ha hűtési szünet kell."""
        if not self.c.get("bekapcsolva", True) or tokenek < int(self.c["min_token"]) or tps <= 0:
            return False
        modell = self.kulcs(modell, prompt_tokenek)
        alap = self.tabla.hoalap(modell)
        if alap is None:
            k = self._kezdeti[modell]
            k.append(tps)
            if len(k) >= int(self.c["alap_minta"]):
                self.tabla.hoalap_ir(modell, statistics.median(k), len(k))
                k.clear()
            return False
        a = self._ablak[modell]
        a.append(tps)
        if len(a) < a.maxlen:
            return False
        med = statistics.median(a)
        if med < float(self.c["kuszob"]) * alap:
            a.clear()
            self.szunetek += 1
            return True
        if med > alap:
            self.tabla.hoalap_ir(modell, med, len(a))
        return False
