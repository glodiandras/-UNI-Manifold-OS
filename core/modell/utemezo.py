"""A worker kérés-ütemezője: egy végrehajtó szál, egyszerre egy hívás (a Metal-sor úgyis soros).

- **Kötegelés** (TERV 4. / 4.): a betöltött modell várakozó kérései mennek előbb; modellcsere csak
  tételhatáron. Az interaktív kérés (a felhasználó kérte) megelőzi az automatikust.
- **Aktivitásjel** (1. / 2. döntés): automatikus (`mod: auto`) kérés aktív használat alatt nem indul, így
  modellt sem tölt be; a kötegek között szünetel. Ha a felhasználó visszajön, és a betöltött modell
  nagyobb a munka-keretnél, a folyó tétel után kiürül.
- **Keret**: `tavol` csak tartós tétlenségben, különben `munka`; a kérés kifejezett keretje (CLI: eval,
  bench) felülírja. A betöltő ezen felül is tartja a keretet és az őrt.
- **Hőfigyelés**: a hűtési szünet alatt automatikus kérés nem indul.
- **Tétlenségi ürítés**: `tetlen_urites_perc` után a modell kiürül.
"""
from __future__ import annotations

import collections
import itertools
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .aktivitas import AKTIV, TAVOL, Aktivitas
from .beallitas import Beallitas, Modell, RegiszterHiba
from .betolto import Betolto, KeretHiba, Leallas
from .hatter import Megszakitva
from .ho import Ho
from .router import Router, RoutingHiba

AUTO, INTERAKTIV = "auto", "interaktiv"
_sorszam = itertools.count()


@dataclass
class Keres:
    tipus: str                               # chat | embed | rerank | atirat
    body: dict
    mod: str = INTERAKTIV
    feladat: str | None = None
    modell: Modell | None = None             # kifejezett (próba) modell
    keret: str | float | None = None         # kifejezett keret (CLI)
    sorszam: int = field(default_factory=lambda: next(_sorszam))
    feladat_id: str | None = None            # a kérő feladat (a feladatsor `MOS_FELADAT`-ja): leállításkor megszakítható
    kizart_csalad: str | None = None         # a második vélemény (C24b): ennek a családnak a modelljei nem routolhatók
    megszakit: threading.Event = field(default_factory=threading.Event)
    kesz: threading.Event = field(default_factory=threading.Event)
    eredmeny: object = None
    hiba: BaseException | None = None
    info: dict = field(default_factory=dict)
    tokenre: Callable[[str], None] | None = None   # folyam (C25b): a generált szövegdarabok, ahogy készülnek

    def befejez(self, eredmeny=None, hiba: BaseException | None = None) -> None:
        self.eredmeny, self.hiba = eredmeny, hiba
        self.kesz.set()


def _naplo(s: str) -> None:
    print(f"[utemezo] {s}", file=sys.stderr, flush=True)


class Utemezo:
    def __init__(self, b: Beallitas, betolto: Betolto, aktivitas: Aktivitas, router: Router, ho: Ho,
                 ido: Callable[[], float] = time.monotonic, naplo: Callable[[str], None] = _naplo,
                 tick_mp: float = 0.5):
        self.b = b
        self.betolto = betolto
        self.aktivitas = aktivitas
        self.router = router
        self.ho = ho
        self.ido = ido
        self.naplo = naplo
        self.tick = tick_mp
        self._cond = threading.Condition()
        self._fuggo: list[Keres] = []
        self._fut: Keres | None = None
        self._megszakitott: collections.OrderedDict[str, None] = collections.OrderedDict()
        self.utolso_hasznalat = ido()
        self.hutes_ig = 0.0
        self.leallt = False
        self._szal = threading.Thread(target=self._hurok, name="modell-utemezo", daemon=True)
        self._szal.start()

    # -------------------------------------------------------- kívülről

    def bekuld(self, k: Keres, timeout: float | None = None):
        with self._cond:
            if self.leallt:
                raise Leallas("a modellgazda leáll")
            if k.feladat_id and k.feladat_id in self._megszakitott:
                raise Megszakitva(f"a feladat ({k.feladat_id}) le lett állítva — a kérés nem indul")
            self._fuggo.append(k)
            self._cond.notify_all()
        if not k.kesz.wait(timeout):
            with self._cond:
                if k in self._fuggo:
                    self._fuggo.remove(k)
            raise TimeoutError("a kérés nem került sorra az időkorláton belül")
        if k.hiba:
            raise k.hiba
        return k.eredmeny

    def leall(self, timeout: float = 30) -> None:
        with self._cond:
            self.leallt = True
            fuggo, self._fuggo = self._fuggo, []
            self._cond.notify_all()
        for k in fuggo:
            k.befejez(hiba=Leallas("a modellgazda leáll"))
        self.betolto.leall.set()
        self._szal.join(timeout)
        self.betolto.urit()

    def megszakit(self, feladat_id: str) -> int:
        """Egy leállított feladat kéréseinek megszakítása (C17): a várakozók `Megszakitva` hibával véget érnek, a
        folyó generálás a következő tokennél megáll, és a feladat későn érkező kérése sem indul (korlátos halmaz).
        → az érintett (várakozó és futó) kérések száma."""
        n = 0
        with self._cond:
            self._megszakitott[feladat_id] = None
            self._megszakitott.move_to_end(feladat_id)
            while len(self._megszakitott) > 256:
                self._megszakitott.popitem(last=False)
            varakozok = [k for k in self._fuggo if k.feladat_id == feladat_id]
            for k in varakozok:
                self._fuggo.remove(k)
            fut = self._fut
            if fut is not None and fut.feladat_id == feladat_id:
                fut.megszakit.set()
                n += 1
            self._cond.notify_all()
        for k in varakozok:
            k.befejez(hiba=Megszakitva(f"a feladat ({feladat_id}) le lett állítva"))
        return n + len(varakozok)

    def elvet(self, k: Keres) -> None:
        """A kérő elment (a folyam kapcsolata bomlott, C25b): a várakozó kérés kikerül a sorból, a folyó a következő
        tokennél megáll."""
        with self._cond:
            k.megszakit.set()
            if k in self._fuggo:
                self._fuggo.remove(k)
                k.befejez(hiba=Megszakitva("a kérő bontotta a kapcsolatot"))
            self._cond.notify_all()

    def urit(self) -> None:
        """Kiürítés kérésre (`/unload`): a folyó hívás végét megvárja (a betöltő zárja)."""
        self.betolto.urit()

    def allapot(self) -> dict:
        with self._cond:
            fuggo = [{"mod": k.mod, "feladat": k.feladat, "modell": k.modell.nev if k.modell else None,
                      "feladat_id": k.feladat_id} for k in self._fuggo]
            fut = self._fut
        most = self.ido()
        return {"fuggo": fuggo, "fut": ({"mod": fut.mod, "feladat": fut.feladat, "feladat_id": fut.feladat_id} if fut else None),
                "tetlen_mp": round(most - self.utolso_hasznalat),
                "hutes_hatra_mp": max(0, round(self.hutes_ig - most)), "hutesi_szunetek": self.ho.szunetek}

    # -------------------------------------------------------- döntések

    def keret_gb(self, k: Keres, akt: str) -> float:
        """A kérés kerete (M3, C19): az aktivitásból következő keret (távol-keret csak tartós tétlenségben); a kérés kifejezett
        `keret`-je ezt csak SZŰKÍTHETI, nem emelheti. A környezeti felülírás (`MANIFOLD_MODELL_KERET_GB`, L24: a CLI saját
        workere, pl. az eval távol-keretes mérése) mindennél erősebb — a `Beallitas.keret_gb` adja."""
        megengedett = self.b.keret_gb("tavol" if akt == TAVOL else "munka")
        if k.keret is None or self.b.keret_felulirva is not None:
            return megengedett
        return min(self.b.keret_gb(k.keret), megengedett)

    def cel(self, k: Keres, keret_gb: float) -> Modell | None:
        """A kérés modellje a pillanatnyi keretben; None, ha a távol-keretre vár."""
        if k.modell is not None:
            if k.modell.csucs_gb is not None and k.modell.csucs_gb > keret_gb:
                if k.mod == INTERAKTIV:
                    raise KeretHiba(f"{k.modell.nev} ({k.modell.csucs_gb:g} GB) nem fér a {keret_gb:g} GB-os keretbe — "
                                    "a távol-keret csak tartós tétlenségben (auto módban) érhető el")
                k.info["var"] = f"{k.modell.nev} a távol-keretre vár"
                return None                               # auto: vár, amíg a keret engedi (M3)
            return k.modell
        d = self.router.valaszt(k.feladat, keret_gb, kizart_csalad=k.kizart_csalad)
        if d.var_tavolra:
            if k.mod == INTERAKTIV:
                raise RoutingHiba(f"{d.indok} — most csak tartós tétlenségben (távol-keretben) futhat")
            k.info["var"] = d.indok
            return None
        k.info["dontes"] = d.indok
        return d.modell

    def _valaszt(self) -> tuple[Keres, Modell, float] | None:
        akt = self.aktivitas.allapot()
        hutes = self.ido() < self.hutes_ig
        jeloltek = []
        for k in list(self._fuggo):
            if k.mod == AUTO and (akt == AKTIV or hutes):
                continue                              # szünet a kötegek között
            keret = self.keret_gb(k, akt)
            try:
                m = self.cel(k, keret)
            except (RoutingHiba, RegiszterHiba, KeretHiba, ValueError) as exc:
                self._fuggo.remove(k)
                k.befejez(hiba=exc)
                continue
            if m is not None:
                jeloltek.append((k, m, keret))
        if not jeloltek:
            return None
        def kulcs(j):
            k, m, _ = j
            return (k.mod != INTERAKTIV, not self.betolto.bent(m), k.sorszam)
        return min(jeloltek, key=kulcs)

    def _karbantart(self) -> None:
        m = self.betolto.modell
        if m is None:
            return
        if self.ido() - self.utolso_hasznalat >= float(self.b.gazda["tetlen_urites_perc"]) * 60:
            self.naplo(f"tétlenségi ürítés: {m.nev}")
            self.betolto.urit()
            return
        munka = self.b.keret_gb("munka")
        if self.b.keret_felulirva is None and self.aktivitas.allapot() == AKTIV:
            if m.csucs_gb and m.csucs_gb > munka:
                self.naplo(f"visszajöttél: a távol-keretes {m.nev} kiürül")
                self.betolto.urit()
            elif self.betolto.mellette and self.betolto.osszes_csucs_gb() > munka:
                self.naplo(f"visszajöttél: a(z) {m.nev} melletti modell kiürül (együtt nem fér a munka-keretbe)")
                self.betolto.betolt(m, munka)          # a betöltő dönt: ami a munka-keretben nem fér mellé, kiürül

    # -------------------------------------------------------- végrehajtás

    def _hurok(self) -> None:
        while True:
            with self._cond:
                if self.leallt:
                    return
                valasztott = self._valaszt()
                if valasztott is None:
                    self._karbantart()
                    self._cond.wait(self.tick)
                    continue
                k, m, keret = valasztott
                self._fuggo.remove(k)
                self._fut = k
            try:
                k.befejez(self._vegrehajt(k, m, keret))
            except BaseException as exc:  # noqa: BLE001 — a hibát a kérő kapja, a szál él tovább
                k.befejez(hiba=exc)
            finally:
                with self._cond:
                    self._fut = None
                    self.utolso_hasznalat = self.ido()

    def _vegrehajt(self, k: Keres, m: Modell, keret: float) -> dict:
        t0 = self.ido()
        b = k.body
        if k.tipus == "chat":
            r = self.betolto.general(m, b.get("messages") or [], keret, kepek=b.get("images") or [],
                                     max_tokens=int(b.get("max_tokens", 256)),
                                     temperature=float(b.get("temperature", 0.0)), gondolkodas=b.get("gondolkodas"),
                                     repetition_penalty=b.get("repetition_penalty"), megszakit=k.megszakit.is_set,
                                     repetition_context_size=b.get("repetition_context_size"), tokenre=k.tokenre)
            if self.ho.minta(m.nev, float(r.get("generation_tps") or 0), int(r.get("generation_tokens") or 0),
                             int(r.get("prompt_tokens") or 0)):
                self.hutes_ig = self.ido() + float(self.ho.c["hutes_mp"])
                self.naplo(f"hűtési szünet {self.ho.c['hutes_mp']} s: {m.nev} token/s-e tartósan az alapszint alatt")
        elif k.tipus == "embed":
            r = {"vektorok": self.betolto.beagyaz(m, b.get("input") or [], keret)}
        elif k.tipus == "rerank":
            r = {"pontok": self.betolto.rerank(m, str(b.get("query") or ""), b.get("documents") or [], keret)}
        elif k.tipus == "atirat":
            r = self.betolto.atir(m, str(b.get("audio") or ""), keret, nyelv=b.get("nyelv") or None,
                                  megszakit=k.megszakit.is_set)
        else:
            raise ValueError(f"ismeretlen kérésfajta: {k.tipus}")
        return {"modell": m, "keret_gb": keret, "mp": round(self.ido() - t0, 2), "r": r,
                "memoria": dict(self.betolto.utolso_meres)}      # T045: a kérés csúcsmemóriája, a betöltés ténye és ideje
