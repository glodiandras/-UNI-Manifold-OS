"""A videólánc modellhívásai a workeren át (a modellt csak a modellgazda tölti).

Élesben a router dönt (`atirat`, `tema`, `kotes`): csak kalibrált modell fut, és ha egy feladatra nincs, a lánc azt a lépést modell
nélkül zárja (a lexikai út) — **nem vár**. Kifejezett modell (`--atirat`, `--tema`, `--kotes`) csak próbában: a worker
`proba: true`-val válaszol, a gépi írás ezt csak a klónra engedi. A kérés a mérés beállítását kapja (`keres_beallitas`), hogy a
kalibrált beállítás és az éles kérés ne térjen el.
"""
from __future__ import annotations

from core.modell import beallitas as B
from core.modell import kliens
from core.modell.eval import keres_beallitas


class NincsModell(RuntimeError):
    """A feladatra nincs kalibrált modell, és kifejezett (próba) modell sincs megadva."""


class Modellek:
    def __init__(self, cfg, kifejezett: dict[str, str] | None = None, u: str | None = None):
        self.cfg = cfg
        self.kifejezett = {k: v for k, v in (kifejezett or {}).items() if v}
        self._u = u
        self._b = None
        self._dontes: dict[str, str | None] = {}

    def url(self) -> str:
        if self._u is None:
            self._u = kliens.url(self.cfg)
        return self._u

    def beallitas(self):
        if self._b is None:
            self._b = B.betolt(self.cfg)
        return self._b

    def van(self, feladat: str) -> bool:
        """Futhat-e a feladat: kifejezett (próba) modell, vagy a router kalibrált modellje. A worker elérhetetlensége: nem fut."""
        if feladat in self.kifejezett:
            return True
        if feladat not in self._dontes:
            try:
                d = kliens.keres(self.url(), "/router/valaszt", {"feladat": feladat})
                self._dontes[feladat] = d.get("modell") or None
            except (kliens.KliensHiba, OSError, RuntimeError):
                self._dontes[feladat] = None
        return bool(self._dontes[feladat])

    def modell_nev(self, feladat: str) -> str:
        if not self.van(feladat):
            raise NincsModell(f"a(z) „{feladat}” feladatra nincs kalibrált modell: élesben nem fut; próbához adj meg egy modellnevet (a Beállítások › AI listájából) és --proba-t")
        return self.kifejezett.get(feladat) or self._dontes[feladat]

    def kerdez(self, feladat: str, prompt: str, max_tokens: int) -> tuple[str, dict]:
        """→ (a válasz szövege, a gépi írás modell-jele)."""
        nev = self.modell_nev(feladat)
        keres = keres_beallitas(self.beallitas(), self.beallitas().modell(nev), feladat,
                                {"messages": [{"role": "user", "content": prompt}], "max_tokens": int(max_tokens)})
        extra = {x: keres[x] for x in ("max_tokens", "temperature", "gondolkodas", "repetition_penalty", "repetition_context_size")
                 if x in keres}
        r = kliens.chat(self.url(), keres["messages"], feladat=feladat, modell=self.kifejezett.get(feladat), **extra)
        return r["choices"][0]["message"]["content"], {"feladat": r.get("feladat") or feladat, "modell": r.get("modell") or nev,
                                                       "proba": bool(r.get("proba"))}

    def atir(self, hang: str, nyelv: str | None) -> tuple[dict, dict]:
        """Hang → átirat (`{szegmensek, nyelv, hossz_mp, modell, …}`) és a modell-jel."""
        nev = self.modell_nev("atirat")
        r = kliens.atir(self.url(), hang, feladat="atirat", modell=self.kifejezett.get("atirat"), nyelv=nyelv)
        return r, {"feladat": r.get("feladat") or "atirat", "modell": r.get("modell") or nev, "proba": bool(r.get("proba"))}
