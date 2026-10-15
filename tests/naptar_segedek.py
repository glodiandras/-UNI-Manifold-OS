"""Segédek a C29 tesztjeihez: az ál-EventKit (`naptar_seged_alarm.py`) állapotfájlja és a `MOS_NAPTAR_SEGED`
burkoló szkriptje. Egy `AlSeged` egy tmp-könyvtárban él; a valódi naptárhoz a teszt nem nyúl."""
import json
import os
import stat
import sys
from pathlib import Path

ALARM = Path(__file__).resolve().parent / "naptar_seged_alarm.py"


class AlSeged:
    def __init__(self, tmp: str, allapot: dict | None = None):
        self.mappa = Path(tmp) / "alseged"
        self.mappa.mkdir(parents=True, exist_ok=True)
        self.allapot_ut = self.mappa / "allapot.json"
        self.ut = self.mappa / "Manifold"
        self.ut.write_text(f'#!/bin/sh\nMOS_ALARM_ALLAPOT="{self.allapot_ut}" exec "{sys.executable}" -B "{ALARM}" "$@"\n')
        self.ut.chmod(self.ut.stat().st_mode | stat.S_IXUSR)
        self.ment({"esemeny": "engedelyezve", "emlekezteto": "engedelyezve", "naptarak": [], "esemenyek": [],
                   "listak": {}, "emlekeztetok": {}, **(allapot or {})})

    def olvas(self) -> dict:
        return json.loads(self.allapot_ut.read_text(encoding="utf-8"))

    def ment(self, d: dict) -> None:
        self.allapot_ut.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def modosit(self, fn) -> dict:
        d = self.olvas()
        fn(d)
        self.ment(d)
        return d

    def env(self) -> dict:
        return {"MOS_NAPTAR_SEGED": str(self.ut)}


def naptar(azon, nev, kategoria_forras="iCloud", irhato=True, tipus="caldav", szin="#a08cf6"):
    return {"azon": azon, "nev": nev, "tipus": tipus, "forras": kategoria_forras, "forras_tipus": "caldav",
            "forras_azon": "F-" + kategoria_forras, "irhato": irhato, "feliratkozas": False, "szin": szin}


def esemeny(azon, naptar_azon, kezd, veg, cim, egesznap=False, hely="", allapot=1):
    e = {"azon": f"{azon}|{kezd}", "naptar": naptar_azon, "cim": cim, "kezd": kezd, "veg": veg, "nap": kezd[:10],
         "egesznap": egesznap, "ismetlodo": False, "leszakitott": False, "allapot": allapot}
    if hely:
        e["hely"] = hely
    return e
