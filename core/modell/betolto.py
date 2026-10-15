"""A betöltő — a 2.0-ban az EGYETLEN hely, ahol modell betöltődik (L22; a legacy `helyi_modell` portja).

Miért (mérve 2026-09-23): egy kalibráció a gemma-4-12B-vel 10 GB-ot foglalt, mert az MLX korlát nélkül
gyorsítótárazott, és közben egy másik munkamenet egy második modellt töltött be: 14 GB a 16-ból, a
gépen nem lehetett dolgozni. „Inkább legyen több idő a feldolgozás, mintsem hogy ne tudjak dolgozni
mellette.”

Négy szabály minden hívásra:
1. KÖZÖS ZÁR — egyszerre egy modellt tartó folyamat a gépen (`zar.Zar`, L23). A folyamaton belül a beágyazó a nyelvi
   modell mellett maradhat, ha a kettő csúcsa együtt belefér a keretbe (`egyutt_maradhat`, C25b); különben kiürül.
2. KERET — a modell csúcsa (`csucs_gb`) nem lépheti túl a keretet; ami nem fér, el sem indul (L24).
3. SZŰK GYORSÍTÓTÁR, DARABOLT BEOLVASÁS — `cache_gb`, `prefill_lepes`.
4. MEMÓRIAŐR — minden hívás előtt: szűkös memóriánál kiürít, és addig vár, amíg a visszatöltés UTÁN is
   maradna elég szabad memória, `helyreallas_mp`-ig folyamatosan (L25). GPU-memóriahibánál kiürít, vár,
   újrapróbál; a tétel nem vész el (L26).
A generálás determinisztikus (`temperature=0`, L27), a betöltés offline (L28).
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from . import hatter as H
from . import memoria
from .beallitas import Beallitas, Modell
from .zar import Zar


class KeretHiba(RuntimeError):
    """A modell nem fér a memóriakeretbe — nem indul el (a felhasználó munkája elsőbb)."""


class Leallas(RuntimeError):
    """A worker leáll: a várakozó hívás nem indul el."""


def _naplo(s: str) -> None:
    print(f"[betolto] {s}", file=sys.stderr, flush=True)


def gpu_memoriahiba(exc: BaseException) -> bool:
    """A Metal a hívás KÖZBEN fogyott ki (mérve 2026-09-23: „Insufficient Memory”)."""
    t = str(exc)
    return "Insufficient Memory" in t or "OutOfMemory" in t


class Betolto:
    def __init__(self, b: Beallitas, hatter_gyar: Callable[[Modell], H.Hatter] = H.gyar,
                 helyi_ut: Callable[[Modell, str], str] = H.helyi_ut,
                 mem: Callable[[], int] = memoria.szabad_szazalek, osszes_gb: Callable[[], float] = memoria.osszes_gb,
                 ido: Callable[[], float] = time.monotonic, naplo: Callable[[str], None] = _naplo,
                 cache_gb: float | None = None, prefill_lepes: int | None = None):
        self.b = b
        self.g = b.gazda
        self.hatter_gyar = hatter_gyar
        self.helyi_ut = helyi_ut
        self.mem = mem
        self.osszes_gb = osszes_gb
        self.ido = ido
        self.naplo = naplo
        self.cache_gb = float(self.g["cache_gb"] if cache_gb is None else cache_gb)
        self.prefill_lepes = int(self.g["prefill_lepes"]) if prefill_lepes is None else prefill_lepes
        self.zar = Zar(b.zar, naplo)
        self.lock = threading.RLock()
        self.leall = threading.Event()
        self.modell: Modell | None = None
        self.hatter: H.Hatter | None = None
        self.mellette: dict[str, tuple[Modell, H.Hatter]] = {}   # az aktív mellett bent maradó modell (`egyutt_maradhat`)
        self.keret_gb: float | None = None
        self.szunetek = 0
        self.szunet_mp = 0.0
        self.betoltesek = 0
        self.utolso_betoltes_mp = 0.0               # az utolsó tényleges betöltés ideje (C29.8, T045)
        self.utolso_meres = {"csucs_gb": None, "betoltve": False, "betoltes_mp": 0.0}     # az utolsó `_hiv` mérése

    # -------------------------------------------------------- szabályok

    def ellenoriz(self, m: Modell, keret_gb: float) -> None:
        """A 2. szabály (és a háttér megléte) — betöltés nélkül."""
        if m.csucs_gb is not None and m.csucs_gb > keret_gb:
            raise KeretHiba(f"{m.nev}: a csúcs {m.csucs_gb:g} GB > a keret {keret_gb:g} GB — nem indul el "
                            "(távol-keretben, tartós tétlenségben futhat)")

    def _var(self, mp: float) -> None:
        if self.leall.wait(mp):
            raise Leallas("a modellgazda leáll")

    def _sajat_szazalek(self, m: Modell, keret_gb: float) -> float:
        return 100.0 * (m.csucs_gb or keret_gb) / self.osszes_gb()

    def _or(self, m: Modell, keret_gb: float) -> None:
        """Memóriaőr a hívás előtt (L25)."""
        lvl = self.mem()
        kuszob = float(self.g["min_szabad_szazalek"])
        if lvl < 0 or lvl >= kuszob:
            return
        t0 = self.ido()
        self.naplo(f"szünet: a gép szabad memóriája {lvl} % < {kuszob:g} % — a modell kiürül, a te munkád elsőbb")
        self.urit()
        self._helyreallasra_var(m, keret_gb)
        self.szunetek += 1
        self.szunet_mp += self.ido() - t0
        self.naplo(f"folytatom: szünet {self.ido() - t0:.0f} s")

    def _helyreallasra_var(self, m: Modell, keret_gb: float) -> None:
        kell = float(self.g["min_szabad_szazalek"]) + float(self.g["tartalek_szazalek"]) + self._sajat_szazalek(m, keret_gb)
        jo_ota = None
        while True:
            lvl = self.mem()
            if lvl >= kell or lvl < 0:
                jo_ota = self.ido() if jo_ota is None else jo_ota
                if self.ido() - jo_ota >= float(self.g["helyreallas_mp"]):
                    return
            else:
                jo_ota = None
            self._var(min(5.0, float(self.g["helyreallas_mp"])) or 0.01)

    # -------------------------------------------------------- betöltés

    @staticmethod
    def egyutt_maradhat(a: Modell, b: Modell, keret_gb: float) -> bool:
        """A beágyazó a nyelvi modell mellett (C25b; a döntés EGYETLEN helye): két különböző modell akkor lehet egyszerre
        betöltve, ha közülük pontosan az egyik beágyazó (`beagyazas` képesség), mindkettő csúcsa ismert (a regiszterből),
        és a csúcsok összege belefér a kérés keretébe (az aktivitás szerinti keret: munka 5 GB, távol 9 GB; D5). Különben
        a beágyazó kiürül a másik modell betöltése előtt. A memóriaőr (L25) változatlan: szűkös memóriánál mindkettő kiürül."""
        if a.nev == b.nev or a.csucs_gb is None or b.csucs_gb is None:
            return False
        if ("beagyazas" in a.kepessegek) == ("beagyazas" in b.kepessegek):
            return False
        return a.csucs_gb + b.csucs_gb <= keret_gb

    def bent(self, m: Modell) -> bool:
        """Be van-e töltve (aktívként vagy a másik mellett)."""
        return (self.modell == m and self.hatter is not None) or m.nev in self.mellette

    def betoltott_modellek(self) -> list[Modell]:
        return ([self.modell] if self.modell is not None and self.hatter is not None else []) + \
            [m for m, _ in self.mellette.values()]

    def osszes_csucs_gb(self) -> float:
        return sum(m.csucs_gb or 0.0 for m in self.betoltott_modellek())

    def betolt(self, m: Modell, keret_gb: float) -> None:
        with self.lock:
            if self.modell == m and self.hatter is not None:
                self.keret_gb = keret_gb
                self._mellette_szukit(m, keret_gb)
                return
            if m.nev in self.mellette:               # már bent van a másik mellett: csak aktív lesz (betöltés nélkül)
                if self.modell is not None and self.hatter is not None:
                    if self.egyutt_maradhat(self.modell, m, keret_gb):
                        self.mellette[self.modell.nev] = (self.modell, self.hatter)
                    else:
                        self._urit_egy(self.modell, self.hatter)
                self.modell, self.hatter = self.mellette.pop(m.nev)
                self.keret_gb = keret_gb
                self._mellette_szukit(m, keret_gb)
                return
            self.ellenoriz(m, keret_gb)
            h = self.hatter_gyar(m)
            ut = self.helyi_ut(m, str(self.b.models / "hub"))
            marad = [(x, hx) for x, hx in self._mind() if self.egyutt_maradhat(x, m, keret_gb)]
            for x, hx in self._mind():
                if (x, hx) not in marad:
                    self._urit_egy(x, hx)
            self.modell, self.hatter = None, None
            self.mellette = {x.nev: (x, hx) for x, hx in marad}
            self.zar.megszerez("+".join([m.repo, *(x.repo for x, _ in marad)]), megszakit=self.leall.is_set)
            try:
                self._csucs_nullaz(h)               # a betöltés ELŐTT: a csúcs a betöltést is tartalmazza (T045)
                t0 = self.ido()
                h.betolt(m, ut, self.cache_gb)
                self.utolso_betoltes_mp = self.ido() - t0
            except BaseException:
                if not self.mellette:
                    self.zar.elenged()
                raise
            self.modell, self.hatter, self.keret_gb = m, h, keret_gb
            self.betoltesek += 1
            mellett = f" (mellette: {', '.join(self.mellette)})" if self.mellette else ""
            self.naplo(f"betöltve: {m.nev} ({m.repo}), keret {keret_gb:g} GB{mellett}")

    def _mind(self) -> list[tuple[Modell, H.Hatter]]:
        return ([(self.modell, self.hatter)] if self.modell is not None and self.hatter is not None else []) + \
            list(self.mellette.values())

    def _mellette_szukit(self, m: Modell, keret_gb: float) -> None:
        """A keret szűkült (visszajöttél): ami a mostani keretben nem fér az aktív mellé, kiürül."""
        for nev, (x, hx) in list(self.mellette.items()):
            if not self.egyutt_maradhat(x, m, keret_gb):
                del self.mellette[nev]
                self._urit_egy(x, hx)

    def _urit_egy(self, m: Modell, h: H.Hatter) -> None:
        try:
            h.urit()
        finally:
            self.naplo(f"kiürítve: {m.nev}")

    def urit(self) -> None:
        """Minden betöltött modell kiürítése és a zár elengedése (a memória a felhasználóé)."""
        with self.lock:
            try:
                for x, hx in list(self.mellette.values()):
                    self._urit_egy(x, hx)
                if self.hatter is not None:
                    self._urit_egy(self.modell, self.hatter) if self.modell else self.hatter.urit()
            finally:
                self.mellette = {}
                self.hatter = None
                self.modell = None
                self.keret_gb = None
                self.zar.elenged()

    @staticmethod
    def _csucs_nullaz(h: H.Hatter) -> None:
        try:
            h.csucs_nullaz()
        except Exception:  # noqa: BLE001 — a mérés hibája a kérést nem akadályozhatja
            pass

    @staticmethod
    def _csucs_gb(h: H.Hatter) -> float | None:
        try:
            return h.csucs_gb()
        except Exception:  # noqa: BLE001
            return None

    def _hiv(self, m: Modell, keret_gb: float, fn: Callable[[H.Hatter], object]):
        with self.lock:
            n = int(self.g["probalkozas"])
            betoltve, betoltes_mp = False, 0.0          # a hívás mérése (T045): a betöltés ténye és ideje, a kérés csúcsmemóriája
            for k in range(n):
                self.ellenoriz(m, keret_gb)
                self._or(m, keret_gb)
                elotte = self.betoltesek
                self.betolt(m, keret_gb)
                if self.betoltesek > elotte:
                    betoltve, betoltes_mp = True, betoltes_mp + self.utolso_betoltes_mp
                else:
                    self._csucs_nullaz(self.hatter)     # a modell már betöltve: a csúcs a kérés saját csúcsa (a betöltött modellel)
                try:
                    r = fn(self.hatter)
                    self.utolso_meres = {"csucs_gb": self._csucs_gb(self.hatter), "betoltve": betoltve,
                                         "betoltes_mp": round(betoltes_mp, 2)}
                    return r
                except RuntimeError as exc:
                    if not gpu_memoriahiba(exc) or k == n - 1:
                        raise
                    self.naplo(f"GPU-memóriahiba a hívás közben ({k + 1}/{n}) — kiürítés, várakozás, újra")
                    self.urit()
                    self.szunetek += 1
                    self._helyreallasra_var(m, keret_gb)

    # -------------------------------------------------------- hívások

    def general(self, m: Modell, messages: list[dict], keret_gb: float, kepek: list[str] | None = None,
                max_tokens: int = 256, temperature: float = 0.0, gondolkodas: bool | None = None,
                repetition_penalty: float | None = None, megszakit=None,
                repetition_context_size: int | None = None, tokenre=None) -> dict:
        extra = {} if megszakit is None else {"megszakit": megszakit}    # csak ha kérik: az álhátterek változatlanok
        if repetition_context_size is not None:
            extra["repetition_context_size"] = int(repetition_context_size)
        if tokenre is not None:
            extra["tokenre"] = tokenre
        return self._hiv(m, keret_gb, lambda h: h.general(messages, list(kepek or []), int(max_tokens),
                                                          float(temperature), gondolkodas, self.prefill_lepes,
                                                          repetition_penalty, **extra))

    def beagyaz(self, m: Modell, szovegek: list[str], keret_gb: float) -> list[list[float]]:
        return self._hiv(m, keret_gb, lambda h: h.beagyaz(list(szovegek)))

    def rerank(self, m: Modell, kerdes: str, dokumentumok: list[str], keret_gb: float) -> list[float]:
        return self._hiv(m, keret_gb, lambda h: h.rerank(kerdes, list(dokumentumok)))

    def atir(self, m: Modell, hang: str, keret_gb: float, nyelv: str | None = None, megszakit=None) -> dict:
        """Hang → átirat (C20b) ugyanazzal a zárral, kerettel és őrrel, mint a többi hívás."""
        return self._hiv(m, keret_gb, lambda h: h.atir(hang, nyelv, megszakit=megszakit))

    def allapot(self) -> dict:
        return {"modell": self.modell.nev if self.modell else None, "repo": self.modell.repo if self.modell else None,
                "mellette": sorted(self.mellette), "keret_gb": self.keret_gb, "szunetek": self.szunetek, "szunet_mp": round(self.szunet_mp),
                "betoltesek": self.betoltesek, "szabad_szazalek": self.mem(), "cache_gb": self.cache_gb}
