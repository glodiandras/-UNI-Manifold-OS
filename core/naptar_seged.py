"""Az EventKit-segéd kliense (C29): a Manifold.app `--naptar` CLI-módjának hívása (docs/C29-TERV.md, 2. fejezet).

A segéd a héj futtathatója (`[utak] naptar_seged`, a `MOS_NAPTAR_SEGED` felülírja): egy rövid gyermekfolyamat,
a kérés JSON a stdinen, a válasz egyetlen JSON a stdouton. A core így egyetlen kód-identitás (a Manifold.app)
engedélyével olvassa a naptárat és írja az emlékeztetőket. A kliens nem kér engedélyt (azt a héj GUI-folyamata
kéri, a felület natív üzenetével); az engedély-állapotot a válaszok hordozzák.

Tesztben a `MOS_NAPTAR_SEGED` egy ál-segédre mutat (`tests/naptar_seged_alarm.py`), ugyanezzel a protokollal.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import config

IDOKORLAT_MP = 60                    # egy hívás legfeljebb ennyit fut (a `kerd` hosszabbat kap)
ALLAPOTOK = ("nincs_dontes", "korlatozott", "megtagadva", "engedelyezve", "csak_iras", "ismeretlen")


class SegedHiba(RuntimeError):
    """A segéd nem érhető el, nem futott le, vagy ok:false választ adott."""

    def __init__(self, uzenet: str, adat: dict | None = None):
        super().__init__(uzenet)
        self.adat = adat or {}


class Seged:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg

    def ut(self) -> Path:
        return self.cfg.path("naptar_seged")

    def van(self) -> bool:
        p = self.ut()
        return p.is_file() and os.access(p, os.X_OK)

    def futtat(self, parancs: str, adat: dict | None = None, idokorlat: float = IDOKORLAT_MP) -> dict:
        """Egy segéd-parancs; → a válasz-objektum (`ok: true`). Hiba: `SegedHiba` (a segéd hiánya, időtúllépés,
        érvénytelen kimenet, `ok: false` — ez utóbbinál az `adat` a teljes válasz)."""
        if not self.van():
            raise SegedHiba(f"nincs naptár-segéd ({self.ut().name}): a Manifold.app újrafordítása kell (bin/mos shell build)")
        try:
            r = subprocess.run([str(self.ut()), "--naptar", parancs], input=json.dumps(adat or {}, ensure_ascii=False),
                               capture_output=True, text=True, timeout=idokorlat, env=self._env())
        except subprocess.TimeoutExpired as e:
            raise SegedHiba(f"a naptár-segéd nem válaszolt időben ({parancs})") from e
        except OSError as e:
            raise SegedHiba(f"a naptár-segéd nem indítható: {e}") from e
        try:
            valasz = json.loads(r.stdout)
        except ValueError:
            raise SegedHiba("a naptár-segéd érvénytelen kimenetet adott"
                            + (f": {(r.stderr or r.stdout).strip()[-300:]}" if (r.stderr or r.stdout) else "")) from None
        if not isinstance(valasz, dict):
            raise SegedHiba("a naptár-segéd válasza nem objektum")
        if not valasz.get("ok"):
            raise SegedHiba(valasz.get("hiba") or "a naptár-segéd hibát jelzett", valasz)
        return valasz

    @staticmethod
    def _env() -> dict[str, str]:
        return dict(os.environ)

    # ---- a parancsok

    def allapot(self) -> dict:
        return self.futtat("allapot")

    def olvas(self, tol: str, ig: str) -> dict:
        return self.futtat("olvas", {"tol": tol, "ig": ig})

    def emlekeztetok(self, lista: str) -> dict:
        return self.futtat("emlekeztetok", {"lista": lista})

    def emlekezteto_ir(self, lista: str, forras: str, ora: str, riasztas: bool, muveletek: list[dict]) -> dict:
        return self.futtat("emlekezteto-ir", {"lista": lista, "forras": forras, "ora": ora, "riasztas": riasztas,
                                              "muveletek": muveletek})

    def esemeny_ir(self, naptar: str, cim: str, kezd: str, veg: str, jegyzet: str, javaslat: int) -> dict:
        return self.futtat("esemeny-ir", {"naptar": naptar, "cim": cim, "kezd": kezd, "veg": veg, "jegyzet": jegyzet,
                                          "jovahagyva": {"javaslat": javaslat}})
