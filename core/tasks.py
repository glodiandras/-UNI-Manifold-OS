"""Tartós feladatsor: SQLite, prioritás, erőforrás-szabály, alfolyamatos worker, haladás WS-en.

Egy feladatfuttató, három tulajdonsággal: a sor tartós (SQLite, a
core újraindítása után is megvan), prioritásos, és egyszerre több feladat futhat — de **egyszerre
egy modelligényes** (`modell`) és **egy vault-író** (`vault`) feladat, összesen `max_parhuzamos`.

Minden lépés külön alfolyamat (a core maga modellt soha nem tölt be, L22). A folyamat-protokoll:
a `[manifold-progress] <szám>%` sor a haladás, a `Riport: <…riport.json>` sor a riport,
a stop-fájl megjelenésekor a lánc a folyamatban lévő tétel UTÁN áll meg. Az azonnali leállítás
SIGTERM a folyamatcsoportnak, 10 s után SIGKILL.

A megnyitás nem indít munkát (D8): a futtató szál lustán, az első beküldéskor indul; az előző
munkamenetből visszatöltött sor csak `indulasi_szunet_mp` után. A `gate` horog a memóriaőré (C05):
amíg hamis, új feladat nem indul. Az `admit(t)` horog feladattípusonként dönt (C05, `core/modell/kapu.py`):
az automatikus feladat (`TaskType.automatikus`) csak ezen át indul. Az `env_extra(t)` a lépések
környezetét bővíti (a modell-worker címe és módja). A lépés környezete a core `os.environ`-jából csak fehérlistával örököl, és a
lépés-token a lépés jogkészletétől (`Step.jogok`) függ (K149, `core/lepes_kapu.py`).

Keményítés (C17, audit M2): a futó lépés pidje, indulási ideje és parancsa a DB-be kerül; a core indulásakor
az előző munkamenet árván maradt lépése leáll (csak egyező ujjlenyomatnál), a `leallitas_horog` pedig a
workert értesíti, hogy a leállított feladat folyó generálását szakítsa meg.
"""
from __future__ import annotations

import datetime as _dt
import contextlib
import json
import os
import hmac
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import frame, lepes_kapu
from .config import Config
from .utvonalak import kodos
from .hibakod import angol_uzenet, json_param
from .hibauzenetek import FELADAT_SZOVEGEK

PROG = re.compile(r"\[manifold-progress\]\s+([\d.]+)%")
RIPORT = re.compile(r"^Riport:\s+(.+riport\.json)\s*$")
MAX_SOR = 3000
ALLAPOTOK = ("sorban", "fut", "kesz", "hiba", "megallitva", "torolve", "megszakadt")
LEZART = ("kesz", "hiba", "megallitva", "torolve", "megszakadt")
RESOURCES = ("modell", "vault")
# A feladat legnagyobb futásideje (A-javító, 2026-10-14): `[feladatsor] max_futas_mp` az alap, a `[feladatsor.max_futas_tipus_mp]`
# táblája típusonként felülírja; 0: nincs korlát. A túllépő feladat azonnal leáll (SIGTERM a folyamatcsoportnak), `hiba` lesz.
MAX_FUTAS_ALAP_MP = 6 * 3600
MAX_FUTAS_TIPUS_ALAP_MP = {"mentes": 3600, "teljes_mentes": 12 * 3600, "video_letoltes": 12 * 3600,
                           "video_integralas": 12 * 3600, "video_bejaras": 2 * 3600}

_SEMA = """
CREATE TABLE feladat (
  sor INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL,
  tipus TEXT NOT NULL,
  cim TEXT NOT NULL,
  osszegzes TEXT NOT NULL DEFAULT '',
  parameterek TEXT NOT NULL DEFAULT '{}',
  figyelmeztetes TEXT NOT NULL DEFAULT '[]',
  lepesek TEXT NOT NULL DEFAULT '[]',
  eroforras TEXT NOT NULL DEFAULT '[]',
  kulturalt_stop INTEGER NOT NULL DEFAULT 0,
  prioritas INTEGER NOT NULL DEFAULT 0,
  allapot TEXT NOT NULL,
  letrehozva TEXT NOT NULL,
  indult TEXT, vegzett TEXT,
  szazalek REAL NOT NULL DEFAULT 0,
  lepes_i INTEGER NOT NULL DEFAULT 0,
  kilepes INTEGER, hiba TEXT, riport TEXT,
  leallitas_kerve INTEGER NOT NULL DEFAULT 0,
  forras TEXT NOT NULL DEFAULT '2.0'
);
CREATE INDEX feladat_allapot ON feladat(allapot, prioritas DESC, sor);
CREATE TABLE meta (kulcs TEXT PRIMARY KEY, ertek TEXT);
"""
_JSON_MEZOK = ("parameterek", "figyelmeztetes", "lepesek", "eroforras")


def _hiba_adat(kod: str, **param) -> dict:
    p = json_param(param)
    return {"hiba": angol_uzenet(kod, p), "hiba_kod": kod, "hiba_param": p}


class Invalid(ValueError):
    """A kérés hibás (a felületnek 400) — az üzenet a felhasználónak szól."""


class Closed(RuntimeError):
    """A sor leáll (a héj kilépett), új feladatot nem fogad (503)."""


@dataclass(frozen=True)
class Step:
    """Egy lépés: alfolyamat. A `jogok` a lépés jogkészlete (K149, `core/lepes_kapu.py`): `"gepi"` (alap) — lépés-token és a core
    címe; `"nincs"` — egyik sem (a hálózati, távoli tartalmat futtató lépés); ismeretlen érték: zárva hibázik (nincs token)."""
    title: str
    argv: list[str]
    cwd: str
    jogok: str = lepes_kapu.JOGOK_ALAP


@dataclass(frozen=True)
class TaskType:
    """Egy feladatfajta. `plan(cfg, params, stop_file)` → (lépések, összegzés, figyelmeztetések);
    `Invalid`, ha a kérés nem indítható. `resources` ⊆ {"modell", "vault"}. `automatikus`: a gép magától
    indítja (index, kártya, összefoglaló, füzetmappa) — csak a kapun át, tétlenségben (1. / 2. döntés)."""
    id: str
    title: str
    plan: Callable[[Config, dict, str], tuple[list[Step], str, list[str]]]
    resources: frozenset = field(default_factory=frozenset)
    graceful_stop: bool = False
    automatikus: bool = False


REGISTRY: dict[str, TaskType] = {}


def register(t: TaskType) -> TaskType:
    if not set(t.resources) <= set(RESOURCES):
        raise ValueError(f"ismeretlen erőforrás: {set(t.resources) - set(RESOURCES)}")
    REGISTRY[t.id] = t
    return t


def _mentes_terv(cfg: Config, p: dict, stop: str):
    return [Step("Mentés a belső lemezre (git bundle)", [sys.executable, "-B", "-m", "core", "backup"],
                 str(cfg.root))], "", []


register(TaskType("mentes", "Mentés a belső lemezre", _mentes_terv))


def _teljes_mentes_terv(cfg: Config, p: dict, stop: str):
    from .teljes_mentes import forrasok, kulso_kotet
    ertek = p.get('cel')
    if not isinstance(ertek, str) or not ertek.strip():
        raise Invalid('Add meg a külső lemez célmappáját.')
    cel = Path(ertek).expanduser().resolve()
    if not cel.is_dir() or not kulso_kotet(cfg, cel):          # F3 §5: a vault és a `{var}` kötetéhez mér, nem a kódfáéhoz
        raise Invalid('A teljes mentés célja egy csatlakoztatott, külön kötet mappája legyen.')
    if any(cel == f or f in cel.parents for f in forrasok(cfg).values()):
        raise Invalid('A célmappa a mentendő rendszerben van.')
    return [Step('Teljes mentés és ellenőrzés', [sys.executable, '-B', '-m', 'core.teljes_mentes', 'ment', str(cel)],
                 str(cfg.root))], str(cel), []


register(TaskType('teljes_mentes', 'Teljes mentés külső lemezre', _teljes_mentes_terv, resources=('vault',)))


def _most() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _ps(mezo: str, pid: int) -> str:
    """Egy `ps` mező egy folyamatról (üres, ha a folyamat nincs meg). `LC_ALL=C`: a `lstart` szövege (amelyet az árva lépés
    egyeztetése a DB-ben mentettel vet össze) ne függjön a core nyelvi beállításától."""
    try:
        return subprocess.run(["ps", "-o", f"{mezo}=", "-p", str(pid)], capture_output=True, text=True,
                              env={**os.environ, "LC_ALL": "C"}, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _arva_leallit(pid: int, inditva: str | None, argv0: str | None, var_mp: float = 3.0) -> bool:
    """Az előző munkamenet árván maradt lépésének leállítása (audit M2): csak akkor nyúl a folyamathoz, ha az
    indulási ideje és a parancsa egyezik a mentettel (a pid-újrahasznosítás ellen); SIGTERM a folyamatcsoportnak,
    `var_mp` után SIGKILL. Igaz, ha leállított valamit."""
    if not inditva or _ps("lstart", pid) != inditva:
        return False
    if argv0 and not _ps("command", pid).startswith(argv0):
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    t0 = time.monotonic()
    while time.monotonic() - t0 < var_mp:
        if not _ps("lstart", pid):
            return True
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return True


@dataclass
class _Run:
    proc: subprocess.Popen | None = None
    stop_requested: bool = False
    kill: bool = False              # azonnali leállítás kérve: a lépés indítása és a `proc` beállítása közti ablakban sem veszhet el (T134)
    resources: frozenset = frozenset()
    felfuggesztve: bool = False     # C21 (9. pont): az Asszisztens kikapcsolása állította meg — a végén visszakerül a sorba
    idotullepes: float = 0.0        # a legnagyobb futásidő (s), ha a feladat túllépte és a sor állította le


class Queue:
    def __init__(self, cfg: Config, publish=lambda e, **k: None, gate: Callable[[], bool] = lambda: True,
                 start_delay: float | None = None, max_parallel: int | None = None,
                 admit: Callable[[TaskType], bool] = lambda t: True,
                 tiltott: Callable[[TaskType], bool | str | None] = lambda t: False,
                 env_extra: Callable[[TaskType], dict[str, str]] = lambda t: {},
                 leallitas_horog: Callable[[str], None] = lambda fid: None,
                 indulas_horog: Callable[[TaskType, str], None] = lambda t, fid: None):
        self.cfg = cfg
        self.publish = publish
        self._lepes_tokenek: dict[str, str] = {}          # a futó lépések tokenjei → feladat-azonosító (T137, `lepes_kapu`)
        self.gate = gate
        self.admit = admit
        self.tiltott = tiltott
        self.env_extra = env_extra
        self.leallitas_horog = leallitas_horog
        self.indulas_horog = indulas_horog          # M3 (C19): az automatikus feladat a workernél is automatikus
        sec = cfg.section("feladatsor")
        self.start_delay = float(sec.get("indulasi_szunet_mp", 180) if start_delay is None else start_delay)
        self.max_parallel = int(max_parallel or sec.get("max_parhuzamos", 2))
        self.logdir = cfg.path("runs") / "feladatok"
        self.logdir.mkdir(parents=True, exist_ok=True)
        frame.feladatnaplo_takaritas(cfg)           # a feladatnaplók kor-/darabszám-alapú takarítása (az eval riportjai maradnak)
        db = cfg.path("feladatok_db")
        db.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._db = sqlite3.connect(db, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._running: dict[str, _Run] = {}
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self.closed = False
        self._db_zarva = False          # a `close()` lezárta a DB-t: a még futó munkásszál nem írhat bele (ProgrammingError)
        self._arva_szal: threading.Thread | None = None
        self._migrate()
        self._recover()
        if self._db.execute("SELECT 1 FROM feladat WHERE allapot='sorban' LIMIT 1").fetchone():
            self._timer = threading.Timer(self.start_delay, self._ensure_thread)
            self._timer.daemon = True
            self._timer.start()

    # -------------------------------------------------------- séma és helyreállítás

    def _migrate(self) -> None:
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            v = self._db.execute("PRAGMA user_version").fetchone()[0]
            if v < 1:
                self._db.executescript("BEGIN;" + _SEMA + "PRAGMA user_version=1; COMMIT;")
            if v < 2:       # C17 (audit M2): a futó lépés azonosítója, hogy a core halála után ne maradjon árva
                self._db.executescript("BEGIN; ALTER TABLE feladat ADD COLUMN lepes_pid INTEGER; "
                                       "ALTER TABLE feladat ADD COLUMN lepes_inditva TEXT; "
                                       "ALTER TABLE feladat ADD COLUMN lepes_argv0 TEXT; "
                                       "PRAGMA user_version=2; COMMIT;")
            if v < 3:       # F4: error metadata survives reopening and appears in history and WS events
                oszlopok = {r[1] for r in self._db.execute("PRAGMA table_info(feladat)")}
                modositas = "".join(f"ALTER TABLE feladat ADD COLUMN {nev} TEXT; "
                                   for nev in ("hiba_kod", "hiba_param") if nev not in oszlopok)
                self._db.executescript("BEGIN; " + modositas + "PRAGMA user_version=3; COMMIT;")

    def _recover(self) -> None:
        """Az előző munkamenet futó feladatai megszakadtak; a sorban állók megmaradnak (tartós sor). A futó
        lépés alfolyamata a core halála után is élhet (saját munkamenetben fut): ha a mentett pid, indulási idő
        és parancs egyezik, leállítjuk (audit M2); a workert is értesítjük, hogy a folyó generálást szakítsa meg.

        A-javító (2026-10-14, D8): a DB-állapot (`megszakadt`) itt, szinkron áll be; az árva lépés leállítása (`ps`, legfeljebb
        3 s kill-várás) és a worker értesítése (legfeljebb 3 s HTTP) árvánként egy háttérszálon (`_arva_szal`) fut, hogy a
        core kézfogását ne tartsa fel. A futtató szál az első feladat indítása előtt megvárja (`arva_var`)."""
        with self._lock:
            futok = [dict(r) for r in self._db.execute("SELECT id, lepes_pid, lepes_inditva, lepes_argv0 FROM feladat "
                                                       "WHERE allapot='fut'").fetchall()]
            for r in futok:
                self._db.execute("UPDATE feladat SET allapot='megszakadt', vegzett=?, hiba=?, hiba_kod=?, hiba_param='{}', "
                                 "lepes_pid=NULL, lepes_inditva=NULL, lepes_argv0=NULL WHERE id=?",
                                 (_most(), angol_uzenet("feladat.core_megszakadt"), "feladat.core_megszakadt", r["id"]))
        if futok:
            self._arva_szal = threading.Thread(target=self._arvak_rendez, args=(futok,), name="feladat-arvak", daemon=True)
            self._arva_szal.start()

    def _arvak_rendez(self, futok: list[dict]) -> None:
        """Az `_recover` háttérrésze: az árván tovább futó lépések leállítása, a napló és a worker értesítése."""
        for r in futok:
            hiba = angol_uzenet("feladat.core_megszakadt")
            try:
                if r["lepes_pid"] and _arva_leallit(r["lepes_pid"], r["lepes_inditva"], r["lepes_argv0"]):
                    param = {"pid": r["lepes_pid"]}
                    hiba = angol_uzenet("feladat.arva_leallitva", param)
                    with self._lock:
                        if not self._db_zarva:
                            self._db.execute("UPDATE feladat SET hiba=?, hiba_kod=?, hiba_param=? "
                                             "WHERE id=? AND allapot='megszakadt'",
                                             (hiba, "feladat.arva_leallitva", json.dumps(param), r["id"]))
            except Exception as exc:  # noqa: BLE001 — a takarítás hibája nem akaszthatja a sort
                print(f"[feladatsor] az árva lépés ({r['id']}) rendezése nem sikerült: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
            try:
                with open(self.logdir / f"{r['id']}.log", "a", encoding="utf-8") as fh:
                    fh.write(f"[core] indulás: {hiba}\n")
            except OSError:
                pass
            self._horog(r["id"])

    def arva_var(self, timeout: float | None = None) -> bool:
        """Megvárja az előző munkamenet árva lépéseinek rendezését; igaz, ha véget ért (vagy nem volt mit rendezni)."""
        t = self._arva_szal
        if t is None:
            return True
        t.join(timeout)
        return not t.is_alive()

    def _horog(self, fid: str) -> None:
        try:
            self.leallitas_horog(fid)
        except Exception:  # noqa: BLE001 — a worker elérhetetlensége nem akaszthatja a leállítást
            pass

    # -------------------------------------------------------- olvasás

    def _row(self, fid: str) -> dict | None:
        if self._db_zarva:
            return None
        r = self._db.execute("SELECT * FROM feladat WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in _JSON_MEZOK:
            d[k] = json.loads(d[k])
        for k in ("cim", "osszegzes"):
            d[k] = FELADAT_SZOVEGEK.get(d[k], d[k])
        d["figyelmeztetes"] = [FELADAT_SZOVEGEK.get(u, u) for u in d["figyelmeztetes"]]
        for lepes in d["lepesek"]:
            lepes["cim"] = FELADAT_SZOVEGEK.get(lepes["cim"], lepes["cim"])
        kod, param = d.pop("hiba_kod"), d.pop("hiba_param")
        if d["hiba"]:
            # Historic error text stays in the DB; its public fallback also follows the English contract.
            d["kod"] = kod or "feladat.futtatas_hibas"
            d["param"] = json.loads(param) if param else ({} if kod else {"tipus": d["tipus"]})
            d["hiba"] = angol_uzenet(d["kod"], d["param"], d["hiba"])
        d["kulturalt_stop"] = bool(d["kulturalt_stop"])
        d["leallitas_kerve"] = bool(d["leallitas_kerve"])
        d["vault_ir"] = "vault" in d["eroforras"]
        d["modell"] = "modell" in d["eroforras"]
        t = REGISTRY.get(d["tipus"])
        d["automatikus"] = bool(t and t.automatikus)    # E10: a kézi feladat vége rendszerértesítést kap, az automatikus nem
        for k in ("sor", "lepes_pid", "lepes_inditva", "lepes_argv0"):
            d.pop(k, None)
        return d

    def _update(self, fid: str, **mezok) -> dict | None:
        with self._lock:
            if self._db_zarva:          # a `close()` után a még futó munkásszál nem ír (a sor `fut`-ban marad: a következő
                return None             # indulás `megszakadt`-ra állítja)
            if "hiba" in mezok and not mezok["hiba"]:
                mezok.setdefault("hiba_kod", None)
                mezok.setdefault("hiba_param", None)
            if isinstance(mezok.get("hiba_param"), dict):
                mezok["hiba_param"] = json.dumps(json_param(mezok["hiba_param"]), ensure_ascii=False)
            sets = ", ".join(f"{k}=?" for k in mezok)
            self._db.execute(f"UPDATE feladat SET {sets} WHERE id=?", (*mezok.values(), fid))
            return self._row(fid)

    def _event(self, d: dict | None, throttle: bool = False) -> None:
        if d is None:
            return
        self.publish({"tipus": "feladat", "feladat": d}, throttle_key=("feladat:" + d["id"]) if throttle else None)

    def get(self, fid: str) -> dict | None:
        with self._lock:
            return self._row(fid)

    def list(self, limit: int = 40) -> list[dict]:
        with self._lock:
            ids = [r[0] for r in self._db.execute(
                "SELECT id FROM feladat ORDER BY letrehozva DESC, sor DESC LIMIT ?", (limit,))]
            return [self._row(i) for i in ids]

    def _logfile(self, d: dict) -> Path:
        return self.logdir / f"{d['id']}.log"

    def detail(self, fid: str, since: int = 0) -> dict | None:
        """A feladat a naplósoraival (`since`-től). A haladásjelző sorok nincsenek a naplóban."""
        d = self.get(fid)
        if not d:
            return None
        naplo = self._logfile(d)
        sorok = naplo.read_text(encoding="utf-8", errors="replace").splitlines()[-MAX_SOR:] if naplo.exists() else []
        d["sorok"], d["tol"], d["osszes_sor"] = sorok[since:], since, len(sorok)
        return d

    def busy_vault(self) -> bool:
        with self._lock:
            return any("vault" in r.resources for r in self._running.values())

    def fuggo(self, tipus: str) -> bool:
        """Van-e a típusból sorban álló vagy futó feladat (a közös automatika-ütemező fogyasztónként legfeljebb egyet küld be)."""
        with self._lock:
            return bool(self._db.execute("SELECT 1 FROM feladat WHERE tipus = ? AND allapot IN ('sorban', 'fut') LIMIT 1",
                                         (tipus,)).fetchone())

    def active(self) -> bool:
        with self._lock:
            return bool(self._running) or bool(
                self._db.execute("SELECT 1 FROM feladat WHERE allapot='sorban' LIMIT 1").fetchone())

    # -------------------------------------------------------- műveletek

    def submit(self, type_id: str, params: dict | None = None, priority: int = 0) -> dict:
        from . import modulkapu
        modul = modulkapu.feladat_modul(type_id)
        if not modulkapu.engedett(self.cfg, modul):
            raise kodos(Invalid("This module is turned off. Enable it in Settings → Modules to use it."),
                        "modul.kikapcsolva", modul=modul)
        t = REGISTRY.get(type_id)
        if not t:
            raise kodos(Invalid(f"ismeretlen feladattípus: {type_id}"), "feladat.ismeretlen_tipus", tipus=type_id)
        if indok := self.tiltott(t):
            raise Invalid(indok if isinstance(indok, str) else "Ez a tartalomgenerálás csak kézi paranccsal indítható.")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise kodos(Invalid("a prioritás egész szám legyen"), "feladat.prioritas")
        params = dict(params or {})
        fid = frame.new_id("F")
        stop = str(self.logdir / f"{fid}.stop")
        lepesek, osszegzes, figy = t.plan(self.cfg, params, stop)
        with self._lock:
            if self.closed:
                raise kodos(Closed("a core éppen leáll (az app kilépett) — nyisd meg újra, és indítsd újra a feladatot"), "feladat.core_leall")
            self._db.execute(
                "INSERT INTO feladat (id, tipus, cim, osszegzes, parameterek, figyelmeztetes, lepesek, eroforras, "
                "kulturalt_stop, prioritas, allapot, letrehozva) VALUES (?,?,?,?,?,?,?,?,?,?, 'sorban', ?)",
                (fid, t.id, t.title, osszegzes, json.dumps(params, ensure_ascii=False),
                 json.dumps(figy, ensure_ascii=False),
                 json.dumps(self._lepesek_tarolt(lepesek), ensure_ascii=False),
                 json.dumps(sorted(t.resources)), int(t.graceful_stop), priority, _most()))
            d = self._row(fid)
            self._cond.notify_all()
        self._event(d)
        self._ensure_thread()
        return d

    def stop(self, fid: str, immediate: bool = False) -> dict:
        with self._lock:
            d = self._row(fid)
            if not d:
                raise Invalid("nincs ilyen feladat")
            if d["allapot"] == "sorban":
                d = self._update(fid, allapot="torolve", vegzett=_most())
                self._event(d)
                return {"allapot": "torolve"}
            run = self._running.get(fid)
            if d["allapot"] != "fut" or not run:
                raise kodos(Invalid("a feladat már nem fut"), "feladat.nem_fut")
            run.stop_requested = True
            self._update(fid, leallitas_kerve=1)
            graceful = d["kulturalt_stop"] and not immediate
            run.kill = not graceful         # a zár alatt: az `_execute` a `Popen` után ezt is ellenőrzi (T134)
            proc = run.proc
        if graceful:
            Path(self.logdir / f"{fid}.stop").touch()
            self._line(d, "[core] leállítás kérve — a folyamatban lévő tétel végén megáll")
            return {"allapot": "megall_a_tetel_vegen"}
        if proc and proc.poll() is None:
            self._line(d, "[core] azonnali leállítás (SIGTERM a folyamatcsoportnak)")
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            t = threading.Timer(10, self._last_word, args=(proc,))
            t.daemon = True
            t.start()
        self._horog(fid)        # a modell-worker a folyó generálást megszakítja (C17); a kulturált leállásnál nem:
        return {"allapot": "leallitva"}   # ott a folyamatban lévő tétel végigfut (L54)

    def automatikus_felfuggeszt(self) -> list[str]:
        """C21 (9. pont, a koordinátor döntése): az Asszisztens kikapcsolásakor a FUTÓ automatikus feladat kulturáltan megáll a
        folyamatban lévő tétel végén, és visszakerül a sorba (`sorban`, ugyanazzal az azonosítóval); a sorban állót az `admit` tartja
        (felfüggesztve, nem törlődik). Visszakapcsoláskor mindkettő folytatódik (a lánc a gyorsítótárból és az állapotból halad
        tovább). Azonnali megállás nincs: a gépi írás tételenként atomi (28(d)). → a megállított feladatok azonosítói."""
        ki = []
        with self._lock:
            for fid, run in list(self._running.items()):
                d = self._row(fid)
                t = REGISTRY.get(d["tipus"]) if d else None
                if not (t and t.automatikus and d["allapot"] == "fut") or run.felfuggesztve:
                    continue
                run.felfuggesztve = run.stop_requested = True
                if not d["kulturalt_stop"]:
                    run.kill = True
                ki.append((fid, d, bool(d["kulturalt_stop"]), run.proc))
        for fid, d, graceful, proc in ki:
            if graceful:
                Path(self.logdir / f"{fid}.stop").touch()
                self._line(d, "[core] az Asszisztens kikapcsolva — a folyamatban lévő tétel végén megáll, és a sorba visszakerül")
            elif proc and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        return [fid for fid, *_ in ki]

    @staticmethod
    def _last_word(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close_if_idle(self) -> bool:
        """Ha semmi nem fut és ebben a munkamenetben nincs induló feladat, a sor lezárul: új feladatot
        nem fogad. (A visszatöltött, még nem indított sor tartós: a következő indításkor folytatódik.)"""
        with self._lock:
            if self._running or (self._thread is not None and self._db.execute(
                    "SELECT 1 FROM feladat WHERE allapot='sorban' LIMIT 1").fetchone()):
                return False
            self.closed = True
            self._cond.notify_all()
            return True

    def shutdown(self, timeout: float | None = None, azonnal: bool = False) -> bool:
        """A héj kilépett: új feladat nincs, a futók a tétel végén állnak meg (kulturált leállítás), a
        sorban állók a DB-ben maradnak. `azonnal` (SIGTERM, H6): a futó lépések azonnal állnak le (SIGTERM a
        folyamatcsoportnak, 10 s múlva SIGKILL). Igaz, ha minden futó véget ért a `timeout` alatt."""
        with self._lock:
            self.closed = True
            if self._timer:
                self._timer.cancel()
            futok = list(self._running)
            self._cond.notify_all()
        for fid in futok:
            d = self.get(fid)
            if d and (d["kulturalt_stop"] or azonnal):
                try:
                    self.stop(fid, immediate=azonnal)
                except Invalid:
                    pass
        with self._cond:
            return self._cond.wait_for(lambda: not self._running, timeout)

    def close(self, timeout: float | None = 15) -> None:
        """Leállítás (`shutdown`) és az adatbázis lezárása. A még futó munkásszálak (a `timeout` alatt véget nem ért lépések) a
        zárás után nem írnak a DB-be (`_db_zarva`): a soruk `fut`-ban marad, és a következő indulás `megszakadt`-ra állítja."""
        self.shutdown(timeout)
        if self._arva_szal is not None:
            self._arva_szal.join(1)
        with self._lock:
            self._db_zarva = True
            self._db.close()

    # -------------------------------------------------------- ütemező és munkás

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None and not self.closed:
                self._thread = threading.Thread(target=self._scheduler, name="core-feladatsor", daemon=True)
                self._thread.start()

    def _pick(self) -> dict | None:
        if len(self._running) >= self.max_parallel:
            return None
        foglalt = set().union(*(r.resources for r in self._running.values())) if self._running else set()
        for r in self._db.execute("SELECT id, tipus FROM feladat WHERE allapot='sorban' "
                                  "ORDER BY prioritas DESC, sor ASC").fetchall():
            t = REGISTRY.get(r["tipus"])
            if t is None:
                d = self._update(r["id"], allapot="hiba", vegzett=_most(),
                                 **_hiba_adat("feladat.ismeretlen_tipus", tipus=r["tipus"]))
                self._event(d)
                continue
            if indok := self.tiltott(t):
                d = self._update(r["id"], allapot="torolve", vegzett=_most(),
                                 **_hiba_adat("feladat.automatikus_tiltott"))
                self._event(d)
                continue
            if not (set(t.resources) & foglalt) and self.admit(t):
                return {"id": r["id"], "type": t}
        return None

    def _scheduler(self) -> None:
        self.arva_var()             # az előző munkamenet árva lépése előbb álljon le (`_recover`)
        while True:
            with self._cond:
                if self.closed:
                    return
                pick = self._pick() if self.gate() else None
                if pick is None:
                    self._cond.wait(timeout=1.0)
                    continue
                fid = pick["id"]
                self._running[fid] = _Run(resources=frozenset(pick["type"].resources))
                d = self._update(fid, allapot="fut", indult=_most())
            self._event(d)
            threading.Thread(target=self._execute, args=(fid,), name=f"feladat-{fid}", daemon=True).start()

    def _line(self, d: dict, s: str) -> None:
        """Egy kimeneti sor: haladás → a sávba (és WS), riport → a mezőbe, minden más → a naplóba."""
        m = PROG.search(s)
        if m:
            n = max(len(d["lepesek"]), 1)
            with self._lock:
                if self._db_zarva:
                    return
                i = self._db.execute("SELECT lepes_i FROM feladat WHERE id=?", (d["id"],)).fetchone()[0]
                szazalek = round(100.0 * (i + min(float(m.group(1)), 100.0) / 100.0) / n, 1)
                uj = self._update(d["id"], szazalek=szazalek)
            self._event(uj, throttle=True)
            return
        with open(self._logfile(d), "a", encoding="utf-8") as fh:
            fh.write(s + "\n")
        r = RIPORT.match(s.strip())
        if r:
            self._update(d["id"], riport=r.group(1))

    def lepes_feladat(self, token: str | None) -> str | None:
        """A futó lépés tokenjéhez tartozó feladat azonosítója, vagy `None` (ismeretlen vagy lejárt token). Állandó idejű összevetés."""
        if not token:
            return None
        with self._lock:
            talalat = None
            for t, fid in self._lepes_tokenek.items():
                if hmac.compare_digest(t.encode(), token.encode("utf-8", "replace")):
                    talalat = fid
            return talalat

    def _env(self, fid: str, stop: Path, extra: dict[str, str] | None = None, lepes_token: str | None = None,
             jogok: object = lepes_kapu.JOGOK_ALAP) -> dict[str, str]:
        """A lépés környezete (K149): a core `os.environ`-jából csak a fehérlista (`lepes_kapu.orokolheto`), utána a feladattípus `extra`
        kulcsai és a rögzített kulcsok. A felületi API-titkot a lépés soha nem kapja; a token és a core címe csak a `"gepi"` jogkészletnek
        jár (`lepes_kapu.token_jar`), a `"nincs"` és az ismeretlen jogkészlet egyiket sem kapja."""
        env = {k: v for k, v in os.environ.items() if lepes_kapu.orokolheto(k)}
        env.update(extra or {})
        env.update({"HF_HOME": str(self.cfg.path("models")), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "MOS_ROOT": str(self.cfg.root),
                    "MOS_FELADAT": fid, "MANIFOLD_STOP_FAJL": str(stop)})
        env.pop("MOS_API_TITOK", None)          # a felületi API-titkot a lépés nem kapja (35. döntés + T137), az `extra`-ból sem
        env.pop(lepes_kapu.KORNYEZETI_VALTOZO, None)
        if lepes_kapu.token_jar(jogok):
            if lepes_token:
                env[lepes_kapu.KORNYEZETI_VALTOZO] = lepes_token   # a lépés a saját tokenjét kapja: ez a hitelesítője
        else:
            for k in lepes_kapu.CORE_CIM_VALTOZOK:                 # K149: a token nélküli lépés a core címét sem kapja
                env.pop(k, None)
        env["PYTHONPATH"] = str(self.cfg.root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env

    # -------------------------------------------------------- a lépések tárolása (L10, T178)

    GYOKER_JEL = "{os}"

    def _lepesek_tarolt(self, lepesek: list[Step]) -> list[dict]:
        """A lépések a DB-be `{os}`-relatív alakban (L10, C33 T178): a gyökér (az SSD csatolási pontja) nem kerül a DB-be. A
        tárolt alak csak a vezérlő kijelzése és a regiszterből kikerült típus tartaléka: a futtatás a `plan`-ből újraszámol."""
        def rel(x: str) -> str:
            gy = str(self.cfg.root)
            return self.GYOKER_JEL + x[len(gy):] if x == gy or x.startswith(gy + os.sep) else x
        return [{"cim": s.title, "argv": [rel(a) for a in s.argv], "cwd": rel(s.cwd), "jogok": s.jogok} for s in lepesek]

    def _lepesek_futtatasra(self, d: dict, t: "TaskType | None", stop: Path) -> list[dict]:
        """A futtatandó lépések (T178): a regiszterben élő típusnál a `plan` újraszámolja őket a MOSTANI konfigurációból (a
        gyökér, a venv, a stop-fájl útja), így a más csatolási ponton újraindult core sorban maradt feladata is a jó úton
        indul. A regiszterből kikerült típusnál a tárolt lépések, az `{os}` jel a mostani gyökérre oldva."""
        if t is not None:
            lepesek, _, _ = t.plan(self.cfg, dict(d.get("parameterek") or {}), str(stop))
            return [{"cim": s.title, "argv": list(s.argv), "cwd": s.cwd, "jogok": s.jogok} for s in lepesek]
        gy = str(self.cfg.root)

        def fel(x: str) -> str:
            return gy + x[len(self.GYOKER_JEL):] if isinstance(x, str) and x.startswith(self.GYOKER_JEL) else x
        return [{**l, "argv": [fel(a) for a in l["argv"]], "cwd": fel(l["cwd"])} for l in d["lepesek"]]

    def max_futas_mp(self, tipus: str) -> float:
        """A feladattípus legnagyobb futásideje (s; 0 = nincs korlát): `[feladatsor.max_futas_tipus_mp]`, különben
        `[feladatsor] max_futas_mp`, különben a beépített alapértékek."""
        sec = self.cfg.section("feladatsor")
        tipusok = {**MAX_FUTAS_TIPUS_ALAP_MP, **(sec.get("max_futas_tipus_mp") or {})}
        try:
            return max(0.0, float(tipusok.get(tipus, sec.get("max_futas_mp", MAX_FUTAS_ALAP_MP))))
        except (TypeError, ValueError):
            return float(MAX_FUTAS_ALAP_MP)

    def _idotullepes(self, fid: str, korlat: float) -> None:
        """A legnagyobb futásidő lejárt: a feladat azonnal leáll (SIGTERM a folyamatcsoportnak, 10 s múlva SIGKILL), `hiba` lesz."""
        with self._lock:
            run = self._running.get(fid)
            if run is None:
                return
            run.idotullepes = korlat
            run.stop_requested = run.kill = True
            proc = run.proc
            d = self._row(fid)
        if d:
            self._line(d, f"[core] a feladat túllépte a legnagyobb futásidőt ({korlat:g} s) — azonnali leállítás")
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            t = threading.Timer(10, self._last_word, args=(proc,))
            t.daemon = True
            t.start()
        self._horog(fid)

    def _execute(self, fid: str) -> None:
        stop = self.logdir / f"{fid}.stop"
        d = self.get(fid)
        run = self._running[fid]
        allapot, hiba, kilepes = "kesz", None, None
        hiba_kod, hiba_param = None, {}
        korlat = self.max_futas_mp(d["tipus"]) if d else 0.0
        orszem = threading.Timer(korlat, self._idotullepes, args=(fid, korlat)) if korlat > 0 else None
        if orszem is not None:
            orszem.daemon = True
            orszem.start()
        try:
            t = REGISTRY.get(d["tipus"])
            extra = self.env_extra(t) if t else {}
            if t:
                self.indulas_horog(t, fid)
            lepesek = self._lepesek_futtatasra(d, t, stop)
            n = len(lepesek)
            for i, l in enumerate(lepesek):
                with self._lock:
                    if run.stop_requested:
                        break
                    uj = self._update(fid, lepes_i=i, szazalek=round(100.0 * i / max(n, 1), 1))
                self._event(uj)
                self._line(d, f"── {i + 1}/{n}. lépés: {l['cim']}")
                self._line(d, "$ " + " ".join(l["argv"]))
                jogok = l.get("jogok", lepes_kapu.JOGOK_ALAP)    # a kulcs nélküli (régebben mentett) lépés: az alap
                # T137: a lépés saját tokenje; a core csak ezzel fogadja a nem olvasó kérését. K149: csak a "gepi" jogkészletnek
                lepes_token = secrets.token_urlsafe(24) if lepes_kapu.token_jar(jogok) else None
                if lepes_token:
                    with self._lock:
                        self._lepes_tokenek[lepes_token] = fid
                try:
                    # stdin: /dev/null — a lépés nem kérdezhet (a core stdinje a héj csöve, amely nem ad adatot)
                    proc = subprocess.Popen(l["argv"], cwd=l["cwd"], env=self._env(fid, stop, extra, lepes_token, jogok),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace", start_new_session=True)
                    with self._lock:
                        run.proc = proc         # T134: közvetlenül a Popen után, a zár alatt (a `stop()` ettől látja a folyamatot)
                        kill = run.kill
                    if kill:                    # a leállítás a Popen és ez a pont közé esett: eddig elveszett, a lépés végigfutott
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        t = threading.Timer(10, self._last_word, args=(proc,))
                        t.daemon = True
                        t.start()
                    inditva = _ps("lstart", proc.pid)         # alfolyamat: a zár alatt nem hívjuk
                    with self._lock:
                        self._update(fid, lepes_pid=proc.pid, lepes_inditva=inditva or None, lepes_argv0=l["argv"][0])
                    with proc.stdout:
                        for ln in proc.stdout:
                            self._line(d, ln.rstrip("\n"))
                    kilepes = proc.wait()
                finally:
                    if lepes_token:
                        with self._lock:
                            self._lepes_tokenek.pop(lepes_token, None)     # a lépés végén a token lejár
                with self._lock:
                    run.proc = None
                    self._update(fid, kilepes=kilepes, lepes_pid=None, lepes_inditva=None, lepes_argv0=None)
                if kilepes != 0:
                    if not run.stop_requested:
                        hiba_kod, hiba_param = "feladat.lepes_hibas", {"lepes": i + 1, "kilepes": kilepes}
                        allapot, hiba = "hiba", angol_uzenet(hiba_kod, hiba_param)
                    break
                if stop.exists():
                    break
            if allapot == "kesz" and (run.stop_requested or stop.exists()):
                allapot = "megallitva"
        except Exception as exc:  # noqa: BLE001 — a munkás szál nem halhat meg egy feladattól
            with contextlib.suppress(OSError):
                self._line(d, f"[core] {type(exc).__name__}: {exc}")
            hiba_kod = getattr(exc, "hiba_kod", "feladat.futtatas_hibas")
            hiba_param = getattr(exc, "hiba_param", {"tipus": type(exc).__name__})
            allapot, hiba = "hiba", angol_uzenet(hiba_kod, hiba_param, "The task could not be completed. Open its log for details.")
        finally:
            if orszem is not None:
                orszem.cancel()
            if run.idotullepes:
                hiba_kod, hiba_param = "feladat.idotullepes", {"mp": run.idotullepes}
                allapot, hiba = "hiba", angol_uzenet(hiba_kod, hiba_param)
            stop.unlink(missing_ok=True)                       # a saját stop-fájlunk
            try:
                self._line(d, f"[core] vége: {allapot}" + (f" — {hiba}" if hiba else ""))
            except OSError:
                pass
            mezok = {"allapot": allapot, "hiba": hiba, "hiba_kod": hiba_kod,
                     "hiba_param": hiba_param if hiba_kod else None, "vegzett": _most()}
            if allapot == "kesz":
                mezok["szazalek"] = 100.0
            if run.felfuggesztve and not run.idotullepes and allapot in ("megallitva", "hiba"):  # C21: vissza a sorba (az `admit` tartja)
                mezok = {"allapot": "sorban", "hiba": None, "vegzett": None, "indult": None, "lepes_i": 0, "szazalek": 0.0,
                         "leallitas_kerve": 0}
                self._line(d, "[core] felfüggesztve: a sorban vár, amíg az Asszisztens vissza nem kapcsol")
            with self._cond:
                uj = self._update(fid, **mezok)
                self._running.pop(fid, None)
                self._cond.notify_all()
            self._event(uj)


def utvonalak(r) -> None:
    """A feladatsor végpontjai az útvonal-regiszterben (C11a)."""
    from .utvonalak import HttpError, Valasz

    def reszlet(k):
        d = k.app.queue.detail(k.m.group(1), k.egesz("tol", 0, 0, 10**9))
        if d is None:
            raise HttpError(404, "nincs ilyen feladat", kod="feladat.nincs")
        return d

    def uj(k):
        b = k.torzs()
        return Valasz(201, k.app.queue.submit(str(b.get("tipus") or ""), b.get("parameterek") or {},
                                              b.get("prioritas", 0)))

    r.get("/api/feladatok", lambda k: {"feladatok": k.app.queue.list()})
    r.get(re.compile(r"/api/feladatok/([\w.-]+)"), reszlet)
    r.post("/api/feladatok", uj)
    r.post(re.compile(r"/api/feladatok/([\w.-]+)/leallitas"),
           lambda k: k.app.queue.stop(k.m.group(1), bool(k.torzs().get("azonnal"))))
    from . import vezerlo           # a vezérlő (C17) végpontjai a feladatsoréval egy helyen regisztrálódnak
    vezerlo.utvonalak(r)
