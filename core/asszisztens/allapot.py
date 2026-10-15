"""Az Asszisztens kis állapotfájlja: `{state}/asszisztens.json` (atomi csere; a belső mentés `state/*.json`-ja viszi).

Kulcsok: `higienia_latva` (a legutóbb megtekintett riport tételazonosítói, vagy `None`: még nincs alapvonal) és `szokas` (az
utolsó heti javaslat: ISO-hét, nap, azonosító, állapot, tartalom). A J1 tanult adata (a „Mit tanult az asszisztens” lista):
`kiegeszites_mintak` (elfogadott szövegminták), `hangolas` (fajta|helyzet → kopó számlálók, útvonal nélkül), `muveletek`
(ismétlődő művelet: mappa, címke/sablon/link-cél és darabszám — ez a vault neveit tartalmazza, helyben marad) és
`kartya_dontesek` (a javaslat-kártyák elutasított kulcsai, lejárattal). A fájl **nem statisztika** (a statisztika a
`has_asszisztens` táblában él, a Tracker-kapcsoló alatt): útvonalat nem tartalmaz, kivéve a heti javaslat „legutóbbi
jegyzet” mezőjét (az a tracker aktív idejéből jön, és a nap végén lejár). Sérült vagy hiányzó fájl: az alapértékek.
"""
from __future__ import annotations

import copy
import json
import threading

from .. import tartos

ALAP = {"higienia_latva": None, "szokas": None, "hangolas": {}, "muveletek": {}, "kartya_dontesek": {}}


class Allapot:
    def __init__(self, cfg):
        self.ut = cfg.path("state") / "asszisztens.json"
        self._zar = threading.Lock()

    def _beolvas(self) -> dict:
        try:
            d = json.loads(self.ut.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def olvas(self) -> dict:
        return {**copy.deepcopy(ALAP), **self._beolvas()}

    def modosit(self, fn) -> dict:
        """Olvasás–módosítás–írás egy zár alatt; az ismeretlen kulcsok megmaradnak. → az új állapot."""
        with self._zar:
            d = self.olvas()
            fn(d)
            self.ut.parent.mkdir(parents=True, exist_ok=True)
            tartos.atomi_ir(self.ut, json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))
            return d
