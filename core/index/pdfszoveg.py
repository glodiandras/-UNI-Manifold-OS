"""A PDF-ek kereshető szövege (C25c): lapszintű kinyerés PyMuPDF-fel, elzárt gyermekfolyamatban, gyorsítótárral.

**Miért nem az index író szálán.** A vault 130 PDF-je (10 736 lap, 22,7 M karakter) kinyerése ~60 s (a legnagyobb 8,7 s,
NAPLO C25c): az író szálon a hidegépítést és minden mentés indexelését feltartaná (15. döntés: az indulási index ~2 s). Ezért
a kinyerés a `Kinyero` háttérszála, a feladatsor kapujával (`Kapu.admit` egy automatikus feladatra: a D8-szünet után, aktív
használat alatt nem, kevés memóriánál nem), PDF-enként egy **gyermekfolyamatban** (`pdf_gyerek.py`, `sandbox-exec` alatt:
hálózat és írás tiltva, csak a PDF és a Python olvasható; hiányzó `sandbox-exec` mellett zárva hibázik, elzáratlan futtatás
nincs). Az eredmény a gyorsítótárba kerül, és az író szál egy rövid tranzakcióban teszi az FTS-be (`Index._pdf_alkalmaz`).

**Gyorsítótár**: `{index}/pdf-szoveg.sqlite` — újraépíthető (a belső mentésbe nem kerül, mint a `vektor.sqlite`, 33. és
58(a) döntés), a `vault.sqlite` újraépítése nem nyeri ki újra a PDF-eket. Kulcs: a vault-út, a méret és az mtime; a megváltozott
PDF újra kinyerődik. A hibás PDF (sérült, jelszavas, időtúllépés) `hiba` sort kap, amíg a fájl nem változik; a környezeti
hiba (nincs `sandbox-exec`, a gyermek nem indul) nem kerül a gyorsítótárba.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

GYEREK = Path(__file__).resolve().parent / "pdf_gyerek.py"
PROFIL = Path(__file__).resolve().parent / "pdf_profil.sb"
VERZIO = 1
LAP_MAX = 50_000                 # karakter laponként (a többi lemarad)
OSSZ_MAX = 16_000_000            # karakter PDF-enként
ALAP_IDOKORLAT_MP = 300.0        # egy PDF kinyerésének felső korlátja (a legnagyobb mért: 8,7 s)
KAPU_VARAKOZAS_MP = 30.0         # a kapu tiltásakor ennyi után próbálja újra

_SEMA = """
CREATE TABLE IF NOT EXISTS pdf(
    ut TEXT PRIMARY KEY,                -- NFC vault-út
    meret INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
    allapot TEXT NOT NULL,              -- kesz | hiba
    hiba TEXT,
    lapok TEXT,                         -- JSON: a lapok szövege sorrendben (az 1. elem az 1. oldal)
    csonka INTEGER NOT NULL DEFAULT 0,
    kinyerve REAL
);
"""


class KornyezetHiba(RuntimeError):
    """A kinyerés környezete hiányos (nincs `sandbox-exec`, a gyermek nem indul): nem a PDF hibája, nem kerül a gyorsítótárba."""


# ------------------------------------------------------------------ gyorsítótár

class Gyorsitotar:
    """A kinyert szöveg tára (szálbiztos: egy kapcsolat, egy zár)."""

    def __init__(self, ut: Path):
        self.ut = Path(ut)
        self.ut.parent.mkdir(parents=True, exist_ok=True)
        self._zar = threading.Lock()
        self._c = sqlite3.connect(str(self.ut), timeout=30, check_same_thread=False, isolation_level=None)
        self._c.execute("PRAGMA busy_timeout = 30000")
        self._c.execute("PRAGMA journal_mode = WAL")
        v = self._c.execute("PRAGMA user_version").fetchone()[0]
        if v > VERZIO:
            raise RuntimeError(f"a PDF-szöveg gyorsítótár sémája ({v}) újabb, mint a kódé ({VERZIO})")
        if v < VERZIO:
            self._c.execute("BEGIN")
            self._c.execute("\n".join(s.split("--")[0] for s in _SEMA.strip().rstrip(";").splitlines()))
            self._c.execute(f"PRAGMA user_version = {VERZIO}")
            self._c.execute("COMMIT")

    def close(self) -> None:
        with self._zar:
            self._c.close()

    def olvas(self, ut: str, meret: int, mtime_ns: int) -> dict | None:
        """A kulcsra illő sor: `{allapot, hiba, lapok: [str], csonka}`, vagy None (nincs, vagy a fájl azóta változott)."""
        with self._zar:
            r = self._c.execute("SELECT allapot, hiba, lapok, csonka FROM pdf WHERE ut = ? AND meret = ? AND mtime_ns = ?",
                                (ut, int(meret), int(mtime_ns))).fetchone()
        if r is None:
            return None
        return {"allapot": r[0], "hiba": r[1], "lapok": json.loads(r[2]) if r[2] else [], "csonka": bool(r[3])}

    def ir(self, ut: str, meret: int, mtime_ns: int, *, lapok: list[str] | None = None, hiba: str | None = None,
           csonka: bool = False) -> None:
        with self._zar:
            self._c.execute("INSERT INTO pdf(ut, meret, mtime_ns, allapot, hiba, lapok, csonka, kinyerve) VALUES "
                            "(?,?,?,?,?,?,?,?) ON CONFLICT(ut) DO UPDATE SET meret = excluded.meret, mtime_ns = "
                            "excluded.mtime_ns, allapot = excluded.allapot, hiba = excluded.hiba, lapok = excluded.lapok, "
                            "csonka = excluded.csonka, kinyerve = excluded.kinyerve",
                            (ut, int(meret), int(mtime_ns), "hiba" if hiba else "kesz", hiba,
                             None if hiba else json.dumps(lapok or [], ensure_ascii=False), int(csonka), time.time()))

    def hibak(self) -> int:
        with self._zar:
            return self._c.execute("SELECT count(*) FROM pdf WHERE allapot = 'hiba'").fetchone()[0]


def lapszamok(gyorsitotar_ut: Path, kulcsok) -> dict[str, int]:
    """A PDF-ek oldalszáma a gyorsítótárból (C30b, K205 (c); a hiányzó-forráshorgony `oldal ≤ oldalszám` ellenőrzéséhez) —
    **csak olvas**, külön `mode=ro` kapcsolaton (a kinyerő író kapcsolatát és az index sémáját nem érinti; az index nem hordozza
    a lapszámot: a szöveg nélküli lap nem szakasz).

    `kulcsok`: `[(vault-út, méret, mtime_ns)…]` — az indexben álló fájl adatai. Csak az a PDF kap oldalszámot, amelynek a sora
    `kesz`, **nem csonka** (a lapok teljes listája megvan) és a kulcsa egyezik (azóta nem változott a fájl); különben nincs bejegyzés
    (ismeretlen: a hívó nem ítél). Hiányzó vagy olvashatatlan gyorsítótár: üres válasz."""
    kulcsok = list(kulcsok)
    if not kulcsok or not Path(gyorsitotar_ut).is_file():
        return {}
    ki: dict[str, int] = {}
    try:
        c = sqlite3.connect(f"file:{urllib.parse.quote(str(gyorsitotar_ut))}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return {}
    try:
        for ut, meret, mtime in kulcsok:
            r = c.execute("SELECT json_array_length(lapok) FROM pdf WHERE ut = ? AND meret = ? AND mtime_ns = ? "
                          "AND allapot = 'kesz' AND csonka = 0 AND lapok IS NOT NULL",
                          (ut, int(meret), int(mtime))).fetchone()
            if r is not None and r[0]:
                ki[ut] = int(r[0])
    except sqlite3.Error:
        return {}
    finally:
        c.close()
    return ki


# ------------------------------------------------------------------ szöveg → index

def szakaszok(lapok: list[str]) -> list[tuple[str, float, int, None]]:
    """A lapok az index szakaszaivá (`fts_szakasz`): `[(a lap szövege, oldal, a lap első sorának sorszáma 1-től, None)…]`; a
    sorszám a PDF egész szövegében folyamatos, a szöveg nélküli lap kimarad."""
    ki: list[tuple[str, float, int, None]] = []
    sor = 1
    for oldal, s in enumerate(lapok, 1):
        lap = [x for x in s.split("\n") if x.strip()]
        if not lap:
            continue
        ki.append(("\n".join(lap), oldal, sor, None))
        sor += len(lap)
    return ki


# ------------------------------------------------------------------ a gyermekfolyamat

def sandbox_exec(cfg) -> str | None:
    if cfg is not None and "sandbox_exec" in getattr(cfg, "utak", {}):
        return str(cfg.path("sandbox_exec"))
    return shutil.which("sandbox-exec")


def parancs(pdf: Path, sandbox: str | None) -> list[str]:
    if not sandbox or not os.access(sandbox, os.X_OK):
        raise KornyezetHiba(f"nincs sandbox-exec ({sandbox or 'nem található'}): elzáratlan PDF-elemzés nincs")
    exe = sys.executable
    d = {"PY_EXE": exe, "PY_EXE_VALOS": os.path.realpath(exe), "PY_PREFIX": os.path.realpath(sys.prefix),
         "PY_BASE": os.path.realpath(sys.base_prefix), "GYEREK": os.path.realpath(GYEREK), "PDF": os.path.realpath(pdf)}
    p = [sandbox, "-f", str(PROFIL)]
    for k, v in d.items():
        p += ["-D", f"{k}={v}"]
    return p + [exe, "-I", "-B", "-X", "utf8", str(GYEREK), os.path.realpath(pdf), str(LAP_MAX), str(OSSZ_MAX)]


def kinyer(pdf: Path, sandbox: str | None, idokorlat: float = ALAP_IDOKORLAT_MP,
           leallit: threading.Event | None = None) -> dict:
    """Egy PDF kinyerése a gyermekben: `{lapok: [str], csonka}` vagy `{hiba}` (a PDF hibája). Környezeti hiba: `KornyezetHiba`.
    A `leallit` jelzésére (a core leáll) a gyermek azonnal leáll (`KornyezetHiba`: nem a PDF hibája)."""
    try:
        proc = subprocess.Popen(parancs(pdf, sandbox), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd="/", env={}, start_new_session=True)
    except OSError as e:
        raise KornyezetHiba(f"a PDF-kinyerő nem indul: {e}") from None
    kimenet: list[bytes] = []
    hibakimenet: list[bytes] = []

    def gyujt(f, ide, max_b):
        n = 0
        for darab in iter(lambda: f.read(65536), b""):
            if n < max_b:
                ide.append(darab)
            n += len(darab)
    olvasok = [threading.Thread(target=gyujt, args=(proc.stdout, kimenet, 8 * OSSZ_MAX), daemon=True),
               threading.Thread(target=gyujt, args=(proc.stderr, hibakimenet, 65536), daemon=True)]
    for t in olvasok:
        t.start()
    hatar = time.monotonic() + idokorlat
    try:
        while proc.poll() is None:
            if leallit is not None and leallit.is_set():
                raise KornyezetHiba("a core leáll")
            if time.monotonic() > hatar:
                return {"hiba": f"időtúllépés ({idokorlat:g} s)"}
            time.sleep(0.05)
    finally:
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
            proc.wait()
        for t in olvasok:
            t.join(5)
        for f in (proc.stdout, proc.stderr):
            with contextlib.suppress(OSError):
                f.close()
    lapok: dict[int, str] = {}
    n = None
    csonka = kesz = False
    for sor in b"".join(kimenet).split(b"\n"):
        if not sor.strip():
            continue
        try:
            o = json.loads(sor)
        except ValueError:
            continue
        if "hiba" in o:
            return {"hiba": str(o["hiba"])[:300]}
        if "lapok" in o:
            n = int(o["lapok"])
        elif "o" in o:
            lapok[int(o["o"])] = str(o.get("s") or "")
        elif o.get("csonka"):
            csonka = True
        elif o.get("kesz"):
            kesz = True
    if not kesz or n is None:
        hiba = b"".join(hibakimenet).decode("utf-8", "replace").strip().splitlines()[-1:]
        if proc.returncode in (-6, 134) or (hiba and "sandbox" in hiba[0].lower()):
            raise KornyezetHiba(f"a PDF-kinyerő nem futott le (kód {proc.returncode}): {(hiba or [''])[0][:200]}")
        return {"hiba": f"a kinyerés megszakadt (kód {proc.returncode}): {(hiba or [''])[0][:200]}"}
    return {"lapok": [lapok.get(i, "") for i in range(1, (max(lapok) if lapok else 0) + 1)], "csonka": csonka}


# ------------------------------------------------------------------ a háttérszál

class _AutomatikusMunka:
    """A kapunak: automatikus, modell nélküli munka (D8, aktív használat, memória)."""
    automatikus = True
    resources = ()
    tipus = "pdf_szoveg"


class Kinyero:
    """A PDF-ek kinyerésének sora és háttérszála. `kapu`: `() → bool` (a feladatsor kapuja; tesztben mindig igaz), `kesz`:
    `(ut) → None` (az író szál értesítése, hogy a gyorsítótárban új eredmény áll)."""

    def __init__(self, cfg, tar: Gyorsitotar, kapu, kesz, root: Path, idokorlat: float = ALAP_IDOKORLAT_MP,
                 kapu_varakozas: float = KAPU_VARAKOZAS_MP):
        self.cfg, self.tar, self.kapu, self.kesz, self.root = cfg, tar, kapu, kesz, Path(root)
        self.idokorlat = float(idokorlat)
        self.kapu_varakozas = float(kapu_varakozas)
        self.sandbox = sandbox_exec(cfg)
        self._sor: dict[str, tuple[str, int, int]] = {}      # ut → (lemez_ut, méret, mtime_ns), a beérkezés sorrendjében
        self._cv = threading.Condition()
        self._leall = threading.Event()
        self._szal: threading.Thread | None = None
        self.fut: str | None = None
        self.hiba: str | None = None                          # az utolsó környezeti hiba (pl. nincs sandbox-exec)
        self.kinyerve = 0

    def indit(self) -> None:
        if self._szal is None:
            self._szal = threading.Thread(target=self._fut, name="pdf-szoveg", daemon=True)
            self._szal.start()

    def leallit(self, timeout: float = 5) -> None:
        self._leall.set()
        with self._cv:
            self._cv.notify_all()
        if self._szal is not None:
            self._szal.join(timeout)
            self._szal = None

    def ker(self, ut: str, lemez_ut: str, meret: int, mtime_ns: int) -> None:
        with self._cv:
            self._sor[ut] = (lemez_ut, int(meret), int(mtime_ns))
            self._cv.notify_all()

    def elvet(self, ut: str) -> None:
        with self._cv:
            self._sor.pop(ut, None)

    def varakozik(self) -> int:
        with self._cv:
            return len(self._sor) + (1 if self.fut else 0)

    def _fut(self) -> None:
        while not self._leall.is_set():
            with self._cv:
                while not self._sor and not self._leall.is_set():
                    self._cv.wait()
            if self._leall.is_set():
                return
            if not self.kapu():                           # D8-szünet, aktív használat, kevés memória: később újra
                with self._cv:
                    self._cv.wait(self.kapu_varakozas)
                continue
            with self._cv:
                if not self._sor:
                    continue
                ut = next(iter(self._sor))
                lemez, meret, mtime = self._sor.pop(ut)
                self.fut = ut
            try:
                self._egy(ut, lemez, meret, mtime)
            finally:
                self.fut = None

    def _egy(self, ut: str, lemez: str, meret: int, mtime: int) -> None:
        p = self.root / lemez
        try:
            st = p.stat()
        except OSError:
            return
        if st.st_size != meret or st.st_mtime_ns != mtime:
            return                                    # azóta változott: az index új kérést küld
        try:
            r = kinyer(p, self.sandbox, self.idokorlat, self._leall)
        except KornyezetHiba as e:
            self.hiba = str(e)
            if not self._leall.is_set():
                print(f"[index] PDF-szöveg: {e}", file=sys.stderr, flush=True)
            return
        try:
            st2 = p.stat()
        except OSError:
            return
        if st2.st_size != meret or st2.st_mtime_ns != mtime:
            return
        self.hiba = None
        if "hiba" in r:
            print(f"[index] PDF-szöveg: {ut}: {r['hiba']}", file=sys.stderr, flush=True)
            self.tar.ir(ut, meret, mtime, hiba=r["hiba"])
        else:
            self.tar.ir(ut, meret, mtime, lapok=r["lapok"], csonka=r["csonka"])
        self.kinyerve += 1
        self.kesz(ut)
