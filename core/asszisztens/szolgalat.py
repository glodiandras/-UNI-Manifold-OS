"""A jegyzethigiénia-riport háttérszolgáltatása (C30a; 2. döntés: automatikus, a tevékenység alatt szünetel; D8; 10. döntés:
az Asszisztens-kapcsolóra kötve).

A teljes riport **sosem a kérés szálán** számolódik: egy háttérszál (a `NaptarSzolgalat` mintája; háttérdémon nincs, D4) az
indulási késleltetés (D8: az app megnyitása nem indít munkát) után, `higienia_tick_mp`-enként dönt:

1. az Asszisztens-kapcsoló ki → nem számol; az index még épül → nem számol;
2. az `Index.generacio` nem változott az utolsó számítás óta → nincs mit számolni;
3. az utolsó számítás óta nem telt el `higienia_min_koz_mp` → vár (a gépelés közbeni mentések ne pörgessék);
4. **aktív használat** van (`aktiv()`: a felület jele + a rendszer tétlensége) → vár;
5. különben számol, **szünet-pontokkal**: a `Higienia.riport` a `kozbe()`-t fázisonként és 512 soronként hívja, itt aktív
   használat alatt várakozik (nincs lefoglalt olvasó kapcsolat), a leállás és a kapcsoló kikapcsolása megszakítja.

A kész riport a memóriában marad (újraépíthető, nem tárolódik); csak a „látva” azonosítók az állapotfájlban (`Allapot`).
**Új tétel** = a legutóbb „látva” jelölt riportban nem szereplő azonosító; az első riport csendes alapvonal. A végpontok a
gyorsítótárból válaszolnak, soron belül nem számolnak. Egy jegyzet tételei a jobb panelhez külön, soron belül, egyetlen
indexelt lekérdezéssel jönnek (`Higienia.riport(ut)`), ez nem része a szolgáltatásnak.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from .. import vezerlo
from ..utvonalak import HttpError
from .allapot import Allapot
from .beallitasok import beallitasok

SZINT_SORREND = {"hiba": 0, "figyelmeztetes": 1, "tajekoztato": 2}


class _Megszakit(Exception):
    """A számítás megszakítása (leállás, kikapcsolt kapcsoló)."""


class HigieniaSzolgalat:
    def __init__(self, cfg, index, higienia, allapot: Allapot, *, aktiv, publish=lambda e, **k: None, kapcsolo=None,
                 ido=time.monotonic, szunet_mp: float = 1.0, indulasi_kesleltetes_mp: float = 0.0,
                 tick_mp: float | None = None):
        self.cfg = cfg
        self.index = index
        self.higienia = higienia
        self.allapot = allapot
        self.aktiv = aktiv
        self.publish = publish
        self.kapcsolo = kapcsolo or (lambda: bool(vezerlo.kapcsolok(cfg)["asszisztens"]))
        self.ido = ido
        self.szunet_mp = szunet_mp
        self.kesleltetes = indulasi_kesleltetes_mp
        self.tick_mp = tick_mp
        self.riport: dict | None = None
        self._szamolt_gen: int | None = None
        self._utolso: float | None = None            # az utolsó számítás (vagy hibás kísérlet) ideje, `ido()` szerint
        self._leall = threading.Event()
        self._szal: threading.Thread | None = None
        self._allj = threading.Lock()
        self.d = {"szamolva": None, "szamol": False, "szunetel": False, "hiba": None, "alapvonal": False}

    # ---- életciklus

    def indit(self) -> None:
        with self._allj:
            if self._szal is not None and self._szal.is_alive():
                return
            self._leall.clear()
            self._szal = threading.Thread(target=self._ciklus, name="higienia-szolgalat", daemon=True)
            self._szal.start()

    def leallit(self) -> None:
        self._leall.set()
        sz = self._szal
        if sz is not None and sz.is_alive() and sz is not threading.current_thread():
            sz.join(5)

    def _ciklus(self) -> None:
        if self._leall.wait(self.kesleltetes):
            return
        while not self._leall.is_set():
            try:
                self.tick()
            except Exception as e:                  # noqa: BLE001 — a háttérszál soha nem állhat le egy hibától
                with self._allj:
                    self.d["hiba"] = f"váratlan hiba: {e}"
            if self._leall.wait(self.tick_mp if self.tick_mp is not None else beallitasok(self.cfg)["higienia_tick_mp"]):
                return

    # ---- a döntés és a számítás

    def tick(self) -> str:
        """Egy ütemezési döntés → `ki | nem_kesz | nincs_valtozas | koran | aktiv | szamolt | hiba | megszakitva`."""
        if not self.kapcsolo():
            return "ki"
        if not self.index.allapot().get("kesz"):
            return "nem_kesz"
        if self.riport is not None and self.index.generacio == self._szamolt_gen:
            return "nincs_valtozas"
        if self._utolso is not None and self.ido() - self._utolso < beallitasok(self.cfg)["higienia_min_koz_mp"]:
            return "koran"
        if self.aktiv():
            return "aktiv"
        return self.szamol()

    def _kozbe(self) -> None:
        """A szünet-pont: aktív használat alatt vár; a leállás és a kikapcsolt kapcsoló megszakítja a számítást."""
        while True:
            if self._leall.is_set() or not self.kapcsolo():
                raise _Megszakit()
            if not self.aktiv():
                with self._allj:
                    self.d["szunetel"] = False
                return
            with self._allj:
                self.d["szunetel"] = True
            self._leall.wait(self.szunet_mp)

    def szamol(self) -> str:
        gen = self.index.generacio                  # az olvasás előtt: ha közben írás történt, a következő tick újraszámol
        with self._allj:
            self.d["szamol"] = True
        try:
            r = self.higienia.riport(kozbe=self._kozbe)
        except _Megszakit:
            return "megszakitva"
        except Exception as e:                      # noqa: BLE001 — a hiba a felületen látszik, a szál megy tovább
            with self._allj:
                self.d["hiba"] = str(e)
            self._utolso = self.ido()
            return "hiba"
        finally:
            with self._allj:
                self.d["szamol"] = False
                self.d["szunetel"] = False
        ids = sorted(t["azonosito"] for t in r["tetelek"])
        alapvonal = self.allapot.olvas()["higienia_latva"] is None
        if alapvonal:                               # az első riport csendes alapvonal: nem „új” az összes meglévő tétel
            self.allapot.modosit(lambda d: d.update(higienia_latva=ids))
        self.riport, self._szamolt_gen, self._utolso = r, gen, self.ido()
        with self._allj:
            self.d.update(szamolva=datetime.now().astimezone().isoformat(timespec="seconds"), hiba=None, alapvonal=alapvonal)
        self.publish({"tipus": "asszisztens_valtozas", "mi": "higienia"})
        return "szamolt"

    # ---- a gyorsítótár kiszolgálása

    def _uj(self) -> list[dict]:
        r = self.riport
        if r is None:
            return []
        latva = set(self.allapot.olvas()["higienia_latva"] or [])
        return [t for t in r["tetelek"] if t["azonosito"] not in latva]

    def osszegzes(self) -> dict:
        """A „Ma” oldal és a vezérlő összegzése a gyorsítótárból; **soron belül nem számol**."""
        r = self.riport
        with self._allj:
            d = dict(self.d)
        ki = {"kapcsolo": bool(self.kapcsolo()), "kesz": r is not None, "szamolva": d["szamolva"], "szamol": d["szamol"],
              "szunetel": d["szunetel"], "hiba": d["hiba"], "alapvonal": d["alapvonal"], "osszesites": None, "ossz": 0,
              "uj": 0, "uj_tetelek": []}
        if r is None:
            return ki
        uj = sorted(self._uj(), key=lambda t: (SZINT_SORREND.get(t["szint"], 9), t["ut"], t["sor"] or 0))
        ki.update(osszesites=r["osszesites"], ossz=r["osszesites"]["ossz"], uj=len(uj),
                  uj_tetelek=[{k: t[k] for k in ("azonosito", "fajta", "szint", "ut", "sor", "uzenet")}
                              for t in uj[:int(beallitasok(self.cfg)["higienia_uj_max"])]])
        return ki

    def teljes_riport(self) -> dict:
        """A teljes riport a gyorsítótárból (`GET /api/higienia` `ut` nélkül; A3-25): soron belül nem számol, és a kapcsolót
        követi. Nincs kész riport vagy kikapcsolt Asszisztens: 409."""
        if not self.kapcsolo():
            raise HttpError(409, "az Asszisztens ki van kapcsolva")
        r = self.riport
        if r is None:
            raise HttpError(409, "a higiénia-riport még nincs kész")
        return r

    def ma(self) -> dict:
        """A „Ma” oldal szakasza: csak olvas (a `GET /api/ma` nem ír)."""
        r = self.riport
        return {"kesz": r is not None, "ossz": r["osszesites"]["ossz"] if r else 0, "uj": len(self._uj())}

    def latva(self) -> dict:
        """Az „új” nullázása: az aktuális riport azonosítói „látva” lesznek."""
        r = self.riport
        if r is None:
            raise HttpError(409, "még nincs kész riport")
        ids = sorted(t["azonosito"] for t in r["tetelek"])
        self.allapot.modosit(lambda d: d.update(higienia_latva=ids))
        with self._allj:
            self.d["alapvonal"] = False
        self.publish({"tipus": "asszisztens_valtozas", "mi": "higienia"})
        return self.osszegzes()
