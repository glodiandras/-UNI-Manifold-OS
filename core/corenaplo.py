"""A core naplója (C29.7b, 2. audit T031: A2-hej-3, A2-hej-5): a core stderr-je forgatott `{runs}/core.log`-ba is kerül, és a
`faulthandler` az összeomlás (SIGSEGV, SIGABRT, …) Python-veremét ugyanoda írja.

Eddig a core stderr-jét a héj csöve vitte, és csak az indulás előtti hibánál (az első 2000 karakter) látszott: futás
közbeni halál után sem napló, sem ok nem maradt. Az eredeti stderr érintetlen marad (a héj a csőből a sorok VÉGÉT
mutatja az „A core leállt” üzenetben); a napló egy másolat. A forgatás induláskor történik (`core.log` → `core.log.1`
→ … → `core.log.N`, a legrégebbi eldobva), és csak a `core.lock` birtokosa hívja — a vesztes (másik core fut) példány
az élő core naplójához nem nyúl.

Méretplafon: a futás közbeni növekedést a `[core] naplo_max_mb` (alap 20 MB) korlátozza — a plafon elérésekor a napló ugyanúgy
forog (`core.log` → `core.log.1` …), és a `faulthandler` az új fájlra áll át; egy hosszan futó core sem tölt meg korlátlanul
lemezt (a teljes tárhely legfeljebb (`MEGTARTOTT` + 1) × plafon).
"""
from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
from pathlib import Path

MEGTARTOTT = 5                       # a core.log mellett ennyi régi napló marad (core.log.1 … core.log.5)
ALAP_MAX_MB = 20                     # a futó napló méretplafonja (`[core] naplo_max_mb`)

_FH = None                           # a `faulthandler` a fájl leíróját használja: a fájlnak élnie kell


def forgat(ut: Path, db: int = MEGTARTOTT) -> None:
    """`ut` → `ut.1` → … → `ut.db`; a legrégebbi törlődik. Hiányzó fájl nem hiba."""
    for i in range(db, 0, -1):
        forras = ut if i == 1 else ut.with_name(f"{ut.name}.{i - 1}")
        cel = ut.with_name(f"{ut.name}.{i}")
        try:
            os.replace(forras, cel)
        except FileNotFoundError:
            pass


class _ForgoFajl:
    """A napló fájlja méretplafonnal: a plafon elérésekor forgat (`forgat`), új fájlt nyit, és a `faulthandler`-t átállítja.
    A `write`/`flush` hibája nem szivárog ki (a `_Tee` is elnyeli). Szálbiztos."""

    def __init__(self, ut: Path, fh, plafon_bajt: int, db: int = MEGTARTOTT):
        self.ut, self.fh, self.plafon, self.db = ut, fh, max(int(plafon_bajt), 1), db
        self.bajt = self._meret()
        self._zar = threading.Lock()

    def _meret(self) -> int:
        try:
            return os.fstat(self.fh.fileno()).st_size
        except (OSError, ValueError):
            return 0

    def write(self, s):
        with self._zar:
            ki = self.fh.write(s)
            self.bajt += len(s.encode("utf-8", "replace"))
            if self.bajt >= self.plafon:
                self._forgat()
            return ki

    def flush(self):
        with self._zar:
            self.fh.flush()

    def fileno(self):
        return self.fh.fileno()

    def _forgat(self) -> None:
        global _FH
        try:
            self.fh.flush()
            forgat(self.ut, self.db)
            uj = open(self.ut, "a", buffering=1, encoding="utf-8")
        except OSError:                   # nem forgatható: a következő plafon-elérésig megy tovább (nincs hurok)
            self.bajt = 0
            return
        regi, self.fh, _FH, self.bajt = self.fh, uj, uj, 0
        try:
            faulthandler.enable(file=uj, all_threads=True)
        except (OSError, ValueError, RuntimeError):
            pass
        try:
            regi.close()
        except OSError:
            pass
        uj.write(f"[core] napló forgatva (méretplafon {self.plafon // (1024 * 1024)} MB); az előző: {self.ut.name}.1\n")


class _Tee:
    """A `sys.stderr` helyett: az eredetibe (a héj csöve) és a naplóba ír. Egyik hibája (megszakadt cső, tele lemez) a
    másikat és a core-t nem érinti (a `mentes._naplo_stderr` ugyanezt a BrokenPipe-tűrést kérte)."""

    def __init__(self, eredeti, fh):
        self._eredeti, self._fh = eredeti, fh

    def write(self, s):
        for cel in (self._eredeti, self._fh):
            try:
                cel.write(s)
            except (OSError, ValueError):
                pass
        return len(s)

    def flush(self):
        for cel in (self._eredeti, self._fh):
            try:
                cel.flush()
            except (OSError, ValueError):
                pass

    def __getattr__(self, nev):          # fileno, isatty, encoding, … az eredetiből
        return getattr(self._eredeti, nev)


def indit(cfg) -> Path | None:
    """A napló indítása: forgatás, megnyitás, `faulthandler`, stderr-tee. Csak a fő szálon (a tesztek a core-t szálon
    indítják: ott a folyamat stderr-je és jelkezelése a teszté). → a napló útja, vagy None."""
    global _FH
    if threading.current_thread() is not threading.main_thread():
        return None
    try:
        mappa = cfg.path("runs")
        mappa.mkdir(parents=True, exist_ok=True)
        ut = mappa / "core.log"
        forgat(ut)
        _FH = open(ut, "a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=_FH, all_threads=True)
        try:
            max_mb = float((cfg.section("core") or {}).get("naplo_max_mb", ALAP_MAX_MB))
        except (TypeError, ValueError):
            max_mb = ALAP_MAX_MB
        naplo = _ForgoFajl(ut, _FH, int(max_mb * 1024 * 1024))
    except OSError as e:                  # a core napló nélkül is induljon el
        print(f"[core] a napló nem nyitható ({e}): a stderr csak a héj csövébe megy", file=sys.stderr, flush=True)
        return None
    sys.stderr = _Tee(sys.__stderr__ if isinstance(sys.stderr, _Tee) else sys.stderr, naplo)
    print(f"[core] indul (pid {os.getpid()}, {time.strftime('%Y-%m-%d %H:%M:%S')}); napló: {ut}", file=sys.stderr, flush=True)
    return ut
