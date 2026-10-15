"""A naptár és az emlékeztetők szolgáltatása (C29): az ütemező és az állapot, amely a három részt egy körré fogja.

Egy **kör**: naptár olvasása (`naptar.szinkron`) → emlékeztetők összevetése (`emlekezteto.szinkron`) → tanulásiblokk-
javaslatok frissítése (`naptar_javaslat.frissit`). A kört a háttérszál indítja (csak amíg a core fut: háttérdémon
nincs, D4), az indulás után `indulasi_kesleltetes_mp` késleltetéssel (D8: az app megnyitása nem indít munkát), majd
`szinkron_perc` percenként; közte, 30 s-os ütemben, ha a jegyzetek határidős feladatai megváltoztak (vagy a
`huzas_perc` letelt), csak az emlékeztető-összevetés fut — az is csak egy index-lekérdezés, amíg nincs mit írni.
A felület a „Szinkron most” kérésével (`kor("kezi")`) is indíthatja.

Engedély nélkül (`nincs_dontes`, `megtagadva`) vagy segéd nélkül a kör nem ír és nem is próbálkozik gyakrabban a
`szinkron_perc`-nél; az állapot a felületen látszik (a Ma oldal és a vezérlő), az engedélyt a héj kéri.
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime

from . import emlekezteto, naptar, naptar_javaslat, szemelyes_db
from .naptar_seged import ALLAPOTOK, Seged, SegedHiba

TICK_MP = 30.0


class NaptarSzolgalat:
    def __init__(self, cfg, index, vault, gepi, tracker=None, publish=lambda e, **k: None, seged: Seged | None = None,
                 mikor=datetime.now, indulasi_kesleltetes_mp: float | None = None):
        self.cfg = cfg
        self.index = index
        self.publish = publish
        self.mikor = mikor
        self.tracker = tracker
        self.seged = seged or Seged(cfg)
        self.emlekezteto = emlekezteto.Emlekezteto(cfg, index, vault, gepi, self.seged, publish, mikor)
        self.javaslatok = naptar_javaslat.Javaslatok(cfg, self.seged, publish, mikor, index=index)
        self.kesleltetes = (naptar.beallitasok(cfg)["indulasi_kesleltetes_mp"] if indulasi_kesleltetes_mp is None
                            else indulasi_kesleltetes_mp)
        self._kor_zar = threading.Lock()
        self._allj = threading.Lock()
        self._leall = threading.Event()
        self._szal: threading.Thread | None = None
        self._utolso_naptar = 0.0                 # time.monotonic: az utolsó teljes kör
        self._utolso_emlekezteto = 0.0
        self._feladat_ujjlenyomat = ""
        self.d: dict = {"seged": None, "esemeny_engedely": None, "emlekezteto_engedely": None, "utolso": None, "hiba": None,
                        "naptar": None, "emlekezteto_kor": None, "javaslat": None}

    # ---- életciklus

    def indit(self) -> None:
        with self._allj:
            if self._szal is not None and self._szal.is_alive():
                return
            self._leall.clear()
            self._szal = threading.Thread(target=self._ciklus, name="naptar-szolgalat", daemon=True)
            self._szal.start()

    def leallit(self) -> None:
        self._leall.set()
        sz = self._szal
        if sz is not None and sz.is_alive() and sz is not threading.current_thread():
            sz.join(5)

    def _var(self, mp: float) -> bool:
        """Vár `mp` másodpercet; igaz, ha a leállítás közben jött."""
        return self._leall.wait(mp)

    def _ciklus(self) -> None:
        if self._var(self.kesleltetes):
            return
        while not self._leall.is_set():
            try:
                b = naptar.beallitasok(self.cfg)
                if b["automatikus"]:
                    self._tick(b)
            except Exception as e:                # noqa: BLE001 — a háttérszál soha nem állhat le egy hibától
                self._hiba(f"váratlan hiba: {e}")
            if self._var(TICK_MP):
                return

    def _tick(self, b: dict) -> None:
        most = time.monotonic()
        if most - self._utolso_naptar >= b["szinkron_perc"] * 60 or not self._utolso_naptar:
            self.kor("auto")
            return
        if not self.index.allapot().get("kesz"):
            return
        eb = emlekezteto.beallitasok(self.cfg)
        ujj = self._ujjlenyomat()
        if ujj != self._feladat_ujjlenyomat or most - self._utolso_emlekezteto >= eb["huzas_perc"] * 60:
            with self._kor_zar:
                self._emlekezteto_kor()

    def _ujjlenyomat(self) -> str:
        try:
            lista = emlekezteto.feladat_lista(self.index)
        except Exception:                          # noqa: BLE001 — az index épülhet: majd a következő ütemben
            return self._feladat_ujjlenyomat
        h = hashlib.sha1()
        for t in lista:
            h.update(f"{t['kulcs']}|{t['hatarido']}|{int(t['kesz'])}|{int(t['megszunt'])}\n".encode())
        return h.hexdigest()

    # ---- a kör

    def _hiba(self, uzenet: str | None) -> None:
        with self._allj:
            self.d["hiba"] = uzenet

    def kor(self, ok: str = "kezi") -> dict:
        """Egy teljes kör (egyszerre egy fut). → az állapot (`allapot()`); a hibát az állapot `hiba` mezeje hordozza."""
        with self._kor_zar:
            self._utolso_naptar = time.monotonic()
            if not self.seged.van():
                with self._allj:
                    self.d.update(seged=False, hiba="nincs naptár-segéd: a Manifold.app újrafordítása kell")
                return self.allapot()
            try:
                tracker_be = bool(self.tracker.be()) if self.tracker is not None else False
                eredmeny = naptar.szinkron(self.cfg, self.seged, tracker_be=tracker_be)
            except SegedHiba as e:
                naptar.hiba_rogzit(self.cfg, str(e))
                with self._allj:
                    self.d.update(seged=True, hiba=str(e))
                return self.allapot()
            with self._allj:
                self.d.update(seged=True, esemeny_engedely=eredmeny["allapot"], naptar=eredmeny, hiba=None,
                              utolso=self.mikor().astimezone().isoformat(timespec="seconds"))
            if any(eredmeny[k] for k in ("uj", "valtozott", "torolt")) or eredmeny["valtozasok"]:
                self.publish({"tipus": "naptar_valtozas", **{k: eredmeny[k] for k in ("allapot", "uj", "valtozott", "torolt")},
                              "valtozasok": eredmeny["valtozasok"]})
            self._emlekezteto_kor()
            if eredmeny["allapot"] == "engedelyezve":
                try:
                    j = self.javaslatok.frissit()
                    with self._allj:
                        self.d["javaslat"] = j
                except Exception as e:             # noqa: BLE001 — a javaslat hibája nem viszi el a kört
                    self._hiba(f"javaslat: {e}")
        return self.allapot()

    def _emlekezteto_kor(self) -> None:
        """Az emlékeztető-összevetés (a hívó tartja a kör-zárat)."""
        self._utolso_emlekezteto = time.monotonic()
        self._feladat_ujjlenyomat = self._ujjlenyomat()
        try:
            e = self.emlekezteto.szinkron()
        except SegedHiba as er:
            with self._allj:
                self.d.update(emlekezteto_kor={"allapot": "hiba", "hiba": str(er)})
            return
        with self._allj:
            if e.get("allapot") == "ok":
                self.d["emlekezteto_engedely"] = "engedelyezve"
            elif e.get("allapot") in ALLAPOTOK:
                self.d["emlekezteto_engedely"] = e["allapot"]
            self.d["emlekezteto_kor"] = e

    def naptar_frissit(self) -> None:
        """Csak a naptár olvasása (egy jóváhagyott blokk után a Ma oldal azonnal lássa)."""
        with self._kor_zar:
            try:
                tracker_be = bool(self.tracker.be()) if self.tracker is not None else False
                eredmeny = naptar.szinkron(self.cfg, self.seged, tracker_be=tracker_be)
            except SegedHiba:
                return
            with self._allj:
                self.d.update(naptar=eredmeny, esemeny_engedely=eredmeny["allapot"])
            self.publish({"tipus": "naptar_valtozas", **{k: eredmeny[k] for k in ("allapot", "uj", "valtozott", "torolt")},
                          "valtozasok": eredmeny["valtozasok"]})

    # ---- állapot

    def engedely(self) -> dict:
        """A segéd engedély-állapota (egy rövid hívás): `{esemeny, emlekezteto}`, vagy `hiba`."""
        if not self.seged.van():
            with self._allj:
                self.d["seged"] = False
            return {"esemeny": None, "emlekezteto": None, "hiba": "nincs naptár-segéd"}
        try:
            r = self.seged.allapot()
        except SegedHiba as e:
            return {"esemeny": None, "emlekezteto": None, "hiba": str(e)}
        with self._allj:
            self.d.update(seged=True, esemeny_engedely=r.get("esemeny"), emlekezteto_engedely=r.get("emlekezteto"))
        return {"esemeny": r.get("esemeny"), "emlekezteto": r.get("emlekezteto")}

    def allapot(self) -> dict:
        with self._allj:
            d = dict(self.d)
        with szemelyes_db.olvaso(self.cfg, 1) as c:
            if c is not None:
                d["utolso_szinkron"] = naptar.utolso_szinkron(c)
                d["naptarak"] = naptar.naptarak(c)
                d["valtozasok"] = naptar.valtozasok(c)
            else:
                d.update(utolso_szinkron=None, naptarak=[], valtozasok=[])
        d["kategoriak"] = [{"id": k["id"], "nev": k["nev"]} for k in naptar.KATEGORIAK]
        d["automatikus"] = naptar.beallitasok(self.cfg)["automatikus"]
        d["emlekezteto_allapot"] = self.emlekezteto.allapot()
        d["javaslatok"] = self.javaslatok.lista()
        return d
