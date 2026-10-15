"""Programok fordítása és futtatása `sandbox-exec` alatt (C36a; a C24a CAS-homokozó mintájára, annak kódját nem érintve).

Két külön profil:
- `profil_futtat.sb` — a lefordított program (egy teszt): csak a saját binárisát és a rendszer-könyvtárakat olvashatja, a
  `munka/` mappába írhat; hálózat, exec, fork, idegen jel nincs;
- `profil_fordit.sb` — a fordító és a linker: olvashatja az eszközláncot, az SDK-t és a pótfejlécet, írni csak a `munka/`-ba.

A határok a futtatásnál (a szülő őrzi, a program nem tud kitörni):
- **idő**: kemény korlát a szülőben (SIGKILL a folyamatcsoportra) + `RLIMIT_CPU` háló (a szülő halálakor sem pörög tovább);
- **memória**: a szülő `mintavetel_ms`-onként olvassa a program `phys_footprint`-jét (T059: a `setrlimit` macOS-en nem
  korlátoz), a korlát fölött SIGKILL; az ASan nagy virtuális árnyékterét ez nem nézi, csak a ténylegest;
- **kimenet**: a stdout és a stderr összesen is legfeljebb `kimenet_max_kb`, fölötte ölés; a megtartott stderr legfeljebb
  `stderr_max_kb`;
- **lemez**: `RLIMIT_FSIZE` (egy fájl) + a szülő a `munka/` méretét és fájlszámát figyeli;
- **I/O**: a stdin írása és a kimenetek olvasása egy `select`-ciklusban megy (holtpont nincs).

A fordításnál (Javító 1, Audit 3 A3-07, A3-16) ugyanez a lemezkorlát áll (`RLIMIT_FSIZE`, amely a driver gyermekeire, a
`cc1`-re és a linkerre is öröklődik, + a `munka/` mérete és fájlszáma; alapból `FORDIT_MUNKA_MAX_MB`), és a memória a
**folyamatcsoport összege** (a driver, a `cc1` és a linker együtt), nem csak a driveré. A memóriaőr **zárva hibázik**:
ha az élő folyamat (csoport) memóriája nem olvasható, ölés és `homokozo_hiba`.

Ha a `sandbox-exec` hiányzik vagy a profil nem indul, **zárva hibázik** (`homokozo_hiba`): csupasz futtatás nincs.
A modul nem C++-specifikus; a fordítási parancsot és a tesztek értelmezését a `modulok/cpp` adja.
"""
from __future__ import annotations

import os
import re
import resource
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import memoria

ITT = Path(__file__).resolve().parent
PROFIL_FUTTAT = ITT / "profil_futtat.sb"
PROFIL_FORDIT = ITT / "profil_fordit.sb"

FUTTATAS_ALLAPOTOK = ("ok", "kilepesi_hiba", "jel", "idotullepes", "memoria", "kimenet_tullepes", "iras_korlat",
                      "megszakitva", "homokozo_hiba")
FORDITAS_ALLAPOTOK = ("ok", "hiba", "jel", "idotullepes", "memoria", "kimenet_tullepes", "iras_korlat", "megszakitva",
                      "homokozo_hiba")
FORDIT_MUNKA_MAX_MB = 256             # a fordítás `munka/` mappájának alapkorlátja (a `[cpp] fordit_munka_max_mb` felülírja)
FORDIT_MUNKA_MAX_FAJL = 1024

_FAJLKORLAT_JEL = re.compile(r"file ?size limit exceeded|file too large", re.I)   # strsignal(SIGXFSZ), strerror(EFBIG)
_MUNKA_ELLENORZES_S = 0.15            # a munka mappa méretét ilyen ritkán nézi a szülő
_ELFOGYASZT_UTAN_S = 2.0              # a program kilépése után a csövek maradékára ennyit vár legfeljebb
_UZENET = {"idotullepes": "a program túllépte az időkorlátot (a folyamatcsoport leállítva)",
           "memoria": "a program túllépte a memóriakorlátot (a folyamatcsoport leállítva)",
           "kimenet_tullepes": "a program túl sok kimenetet írt (a folyamatcsoport leállítva)",
           "iras_korlat": "a program túl sokat írt a saját ideiglenes mappájába (a folyamatcsoport leállítva)",
           "megszakitva": "a futást megszakították (a folyamatcsoport leállítva)",
           "homokozo_hiba": "a folyamat memóriája nem olvasható (a memóriaőr zárva hibázik; a folyamatcsoport leállítva)"}
_FORDIT_UZENET = dict(_UZENET, iras_korlat="a fordító túl sokat írt a munka mappába (a folyamatcsoport leállítva)",
                      idotullepes="a fordító túllépte az időkorlátot (a folyamatcsoport leállítva)",
                      memoria="a fordító túllépte a memóriakorlátot (a folyamatcsoport leállítva)",
                      kimenet_tullepes="a fordító túl sok kimenetet írt (a folyamatcsoport leállítva)")


def _jelnev(szam: int) -> str:
    try:
        return signal.Signals(szam).name
    except ValueError:
        return f"JEL{szam}"


def _munka_meret(munka: Path, max_fajl: int, max_bajt: int) -> tuple[int, int, bool]:
    """A munka mappa fájljainak száma és összmérete; → (db, bajt, túllépte-e). A bejárás a túllépésnél megáll."""
    db = bajt = 0
    verem = [str(munka)]
    while verem:
        try:
            with os.scandir(verem.pop()) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        verem.append(e.path)
                        db += 1
                    else:
                        db += 1
                        try:
                            bajt += e.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
                    if db > max_fajl or bajt > max_bajt:
                        return db, bajt, True
        except OSError:
            continue
    return db, bajt, False


class Programhomokozo:
    def __init__(self, cfg=None, *, sandbox_exec: str | None = None):
        if sandbox_exec is None and cfg is not None and "sandbox_exec" in getattr(cfg, "utak", {}):
            sandbox_exec = str(cfg.path("sandbox_exec"))
        self.sandbox_exec = sandbox_exec if sandbox_exec is not None else shutil.which("sandbox-exec")
        self._elerheto: tuple[bool, str] | None = None

    # ------------------------------------------------------------------ közös

    def _hiany(self) -> str | None:
        if not self.sandbox_exec or not os.access(self.sandbox_exec, os.X_OK):
            return f"nincs sandbox-exec ({self.sandbox_exec or 'nem található'}): elzáratlan futtatás nincs"
        return None

    @staticmethod
    def _rp(p: Path | str) -> str:
        return os.path.realpath(str(p))

    def _inditas(self, profil: Path, params: dict[str, str], parancs: list[str], *, cwd: Path, env: dict[str, str],
                 stdin, cpu_s: float, fsize_b: int | None) -> subprocess.Popen:
        sb = [str(self.sandbox_exec), "-f", str(profil)]
        for k, v in params.items():
            sb += ["-D", f"{k}={v}"]

        def korlatok():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            c = int(cpu_s) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (c, c + 1))
            if fsize_b is not None:
                resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_b, fsize_b))

        return subprocess.Popen(sb + parancs, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cwd),
                                env=env, start_new_session=True, preexec_fn=korlatok)

    @staticmethod
    def _leallit(proc: subprocess.Popen) -> None:
        for _ in range(2):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def _fut(self, proc: subprocess.Popen, bemenet: bytes, idokorlat_s: float, memoria_mb: float, kimenet_max_b: int,
             stderr_max_b: int, munka: Path | None, munka_max_fajl: int, munka_max_b: int,
             mintavetel_ms: float, megszakit=None, csoport: bool = False) -> dict:
        """A folyamat I/O-ja, őrzése és a lezárás → {allapot (None: a kilépés dönt), stdout, stderr, …}.
        `csoport`: a memória a folyamatcsoport összege (a fordító gyermekei), különben a folyamaté."""
        mer = (lambda: memoria.csoport_mb(proc.pid)) if csoport else (lambda: memoria.mb(proc.pid))
        ki, hib = proc.stdout.fileno(), proc.stderr.fileno()
        be = proc.stdin.fileno() if proc.stdin else None
        olv = {ki, hib}
        nyers = {ki: bytearray(), hib: bytearray()}
        hib_levagva = False
        ossz_ki = ossz_hib = 0
        poz = 0
        adat = memoryview(bemenet)
        if be is not None:
            if adat:
                os.set_blocking(be, False)
            else:
                proc.stdin.close()
                be = None
        mintavetel = max(float(mintavetel_ms), 5.0) / 1000
        hatarido = time.monotonic() + idokorlat_s
        csucs = 0.0
        allapot = None
        kovetkezo_munka = time.monotonic() + _MUNKA_ELLENORZES_S
        kilepett_ekkor = None
        while True:
            now = time.monotonic()
            mb = mer()
            if mb is None and allapot is None and proc.poll() is None:
                mb = mer()                                  # egy újrapróba (a kilépés pillanata)
                if mb is None and proc.poll() is None:      # élő folyamat őr nélkül nem futhat tovább (A3-16)
                    allapot = "homokozo_hiba"
            if mb is not None:
                csucs = max(csucs, mb)
                if mb > memoria_mb and allapot is None:
                    allapot = "memoria"
            if now > hatarido and allapot is None:
                allapot = "idotullepes"
            if megszakit is not None and allapot is None and megszakit():
                allapot = "megszakitva"
            if munka is not None and now >= kovetkezo_munka and allapot is None:
                kovetkezo_munka = now + _MUNKA_ELLENORZES_S
                if _munka_meret(munka, munka_max_fajl, munka_max_b)[2]:
                    allapot = "iras_korlat"
            if allapot is not None:
                self._leallit(proc)
                break
            if proc.poll() is not None:
                kilepett_ekkor = kilepett_ekkor or now
                if not olv or now - kilepett_ekkor > _ELFOGYASZT_UTAN_S:
                    break
            rl = list(olv)
            wl = [be] if be is not None else []
            try:
                kesz_r, kesz_w, _ = select.select(rl, wl, [], mintavetel)
            except (OSError, ValueError):
                break
            for fd in kesz_r:
                darab = os.read(fd, 65536)
                if not darab:
                    olv.discard(fd)
                    continue
                if fd == ki:
                    ossz_ki += len(darab)
                    nyers[ki] += darab
                else:
                    ossz_hib += len(darab)
                    if len(nyers[hib]) < stderr_max_b:
                        nyers[hib] += darab[:stderr_max_b - len(nyers[hib])]
                    else:
                        hib_levagva = True
                    if len(nyers[hib]) >= stderr_max_b and ossz_hib > stderr_max_b:
                        hib_levagva = True
                if ossz_ki > kimenet_max_b or ossz_hib > kimenet_max_b:
                    allapot = "kimenet_tullepes"
            if be is not None and be in kesz_w:
                try:
                    poz += os.write(be, adat[poz:poz + 65536])
                except BlockingIOError:
                    pass
                except OSError:                          # a program bezárta a stdin-t vagy kilépett: nincs több írás
                    poz = len(adat)
                if poz >= len(adat):
                    proc.stdin.close()
                    be = None
        self._leallit(proc)                              # a csoport maradékát (ha lenne) a végén is leállítjuk
        for f in (proc.stdin, proc.stdout, proc.stderr):
            try:
                f and f.close()
            except OSError:
                pass
        return {"allapot": allapot, "stdout": bytes(nyers[ki]), "stderr": bytes(nyers[hib]), "stderr_levagva": hib_levagva,
                "csucs_mb": round(csucs, 1)}

    @staticmethod
    def _elerte_a_fajlmeret_korlatot(munka: Path, korlat_b: int) -> bool:
        db = 0
        for gyoker, _mappak, fajlok in os.walk(munka):
            for f in fajlok:
                db += 1
                try:
                    if os.lstat(os.path.join(gyoker, f)).st_size >= korlat_b:
                        return True
                except OSError:
                    pass
            if db > 100000:
                break
        return False

    @staticmethod
    def _kilepes(proc: subprocess.Popen) -> tuple[int | None, str | None]:
        rc = proc.returncode
        if rc is None:
            return None, None
        return (None, _jelnev(-rc)) if rc < 0 else (rc, None)

    # ------------------------------------------------------------------ futtatás

    def futtat(self, bin: Path, *, argv: list[str] | tuple[str, ...] = (), bemenet: bytes = b"", munka: Path,
               bin_mappa: Path | None = None, idokorlat_s: float = 2.0, memoria_mb: float = 256,
               kimenet_max_kb: int = 1024, stderr_max_kb: int = 64, munka_max_mb: float = 16, munka_max_fajl: int = 256,
               kornyezet: dict[str, str] | None = None, san_lib: Path | None = None,
               mintavetel_ms: float = 20, megszakit=None) -> dict:
        """Egy program egy futása a futtató profil alatt, `bemenet` a stdin-re. → `{allapot, kilepes, jel, ido_ms, cpu_ms,
        csucs_mb, stdout, stderr, stderr_levagva, pid, uzenet}`; az állapot a `FUTTATAS_ALLAPOTOK` egyike."""
        e = {"allapot": "homokozo_hiba", "kilepes": None, "jel": None, "ido_ms": 0.0, "cpu_ms": 0.0, "csucs_mb": 0.0,
             "stdout": b"", "stderr": b"", "stderr_levagva": False, "pid": None, "uzenet": ""}
        hiany = self._hiany()
        if hiany:
            return e | {"uzenet": hiany}
        bin = Path(bin)
        munka = Path(munka)
        if not (bin.is_file() and os.access(bin, os.X_OK)):
            return e | {"uzenet": f"a program nem található vagy nem futtatható: {bin}"}
        bin_mappa = Path(bin_mappa) if bin_mappa else bin.parent
        params = {"BIN": self._rp(bin), "BIN_MAPPA": self._rp(bin_mappa), "MUNKA": self._rp(munka),
                  "SAN_LIB": self._rp(san_lib) if san_lib else self._rp(munka)}
        env = {str(k): str(v) for k, v in (kornyezet or {}).items()}
        elo = resource.getrusage(resource.RUSAGE_CHILDREN)
        indul = time.monotonic()
        try:
            proc = self._inditas(PROFIL_FUTTAT, params, [self._rp(bin), *map(str, argv)], cwd=Path(params["MUNKA"]),
                                 env=env, stdin=subprocess.PIPE, cpu_s=idokorlat_s,
                                 fsize_b=int(munka_max_mb * 1024 * 1024))
        except (OSError, subprocess.SubprocessError) as exc:
            return e | {"uzenet": f"a program nem indul: {exc}"}
        e["pid"] = proc.pid
        r = self._fut(proc, bemenet, idokorlat_s, memoria_mb, kimenet_max_kb * 1024, stderr_max_kb * 1024,
                      Path(params["MUNKA"]), munka_max_fajl, int(munka_max_mb * 1024 * 1024), mintavetel_ms, megszakit)
        utan = resource.getrusage(resource.RUSAGE_CHILDREN)
        e.update(stdout=r["stdout"], stderr=r["stderr"], stderr_levagva=r["stderr_levagva"], csucs_mb=r["csucs_mb"],
                 ido_ms=round((time.monotonic() - indul) * 1000, 1),
                 cpu_ms=round(((utan.ru_utime + utan.ru_stime) - (elo.ru_utime + elo.ru_stime)) * 1000, 1))
        e["kilepes"], e["jel"] = self._kilepes(proc)
        if r["allapot"]:
            e["allapot"], e["uzenet"] = r["allapot"], _UZENET[r["allapot"]]
        elif e["jel"] == "SIGXFSZ" or (e["kilepes"] != 0 and self._elerte_a_fajlmeret_korlatot(
                Path(params["MUNKA"]), int(munka_max_mb * 1024 * 1024))):
            # a C++ program a SIGXFSZ-szel áll le; a Python és a legtöbb futtatókörnyezet elnyeli, és `File too large`
            # hibával lép ki: ilyenkor a munka mappában egy fájl pontosan a korláton áll
            e["allapot"], e["uzenet"] = "iras_korlat", _UZENET["iras_korlat"]
        elif e["jel"]:
            e["allapot"], e["uzenet"] = "jel", f"a program a {e['jel']} jellel leállt"
        elif e["kilepes"] == 0:
            e["allapot"], e["uzenet"] = "ok", ""
        else:
            e["allapot"], e["uzenet"] = "kilepesi_hiba", f"a program {e['kilepes']} kilépési kóddal állt le"
        return e

    # ------------------------------------------------------------------ fordítás

    def fordit(self, parancs: list[str], *, munka: Path, llvm: Path, sdk: Path, pot: Path, llvm_bin: Path | None = None,
               kornyezet: dict[str, str] | None = None, idokorlat_s: float = 30.0, memoria_mb: float = 2048,
               kimenet_max_kb: int = 1024, mintavetel_ms: float = 50, megszakit=None,
               munka_max_mb: float = FORDIT_MUNKA_MAX_MB, munka_max_fajl: int = FORDIT_MUNKA_MAX_FAJL) -> dict:
        """A fordító (és a linker) futása a fordító-profil alatt. → `{allapot, kilepes, jel, ido_ms, csucs_mb, stdout, stderr,
        pid, uzenet}`; az állapot a `FORDITAS_ALLAPOTOK` egyike (`hiba`: nem nulla kilépés — a diagnosztika a stderr-ben;
        `iras_korlat`: a `munka/` túllépte a `munka_max_mb`/`munka_max_fajl` korlátot, vagy egy fájl az `RLIMIT_FSIZE`-ot)."""
        e = {"allapot": "homokozo_hiba", "kilepes": None, "jel": None, "ido_ms": 0.0, "csucs_mb": 0.0, "stdout": "",
             "stderr": "", "stderr_levagva": False, "pid": None, "uzenet": ""}
        hiany = self._hiany()
        if hiany:
            return e | {"uzenet": hiany}
        llvm = Path(llvm)
        params = {"LLVM": self._rp(llvm), "LLVM_BIN": self._rp(llvm_bin if llvm_bin else llvm / "bin"),
                  "SDK": self._rp(sdk), "POT": self._rp(pot), "MUNKA": self._rp(munka)}
        env = {str(k): str(v) for k, v in (kornyezet or {}).items()}
        munka_max_b = int(munka_max_mb * 1024 * 1024)
        indul = time.monotonic()
        try:
            proc = self._inditas(PROFIL_FORDIT, params, list(parancs), cwd=Path(params["MUNKA"]), env=env,
                                 stdin=subprocess.DEVNULL, cpu_s=idokorlat_s * 2, fsize_b=munka_max_b)
        except (OSError, subprocess.SubprocessError) as exc:
            return e | {"uzenet": f"a fordító nem indul: {exc}"}
        e["pid"] = proc.pid
        r = self._fut(proc, b"", idokorlat_s, memoria_mb, kimenet_max_kb * 1024, kimenet_max_kb * 1024,
                      Path(params["MUNKA"]), munka_max_fajl, munka_max_b, mintavetel_ms, megszakit, csoport=True)
        e.update(stdout=r["stdout"].decode("utf-8", "replace"), stderr=r["stderr"].decode("utf-8", "replace"),
                 stderr_levagva=r["stderr_levagva"], csucs_mb=r["csucs_mb"],
                 ido_ms=round((time.monotonic() - indul) * 1000, 1))
        e["kilepes"], e["jel"] = self._kilepes(proc)
        if r["allapot"]:
            e["allapot"], e["uzenet"] = r["allapot"], _FORDIT_UZENET[r["allapot"]]
        elif (e["jel"] == "SIGXFSZ" or self._elerte_a_fajlmeret_korlatot(Path(params["MUNKA"]), munka_max_b)
              or _munka_meret(Path(params["MUNKA"]), munka_max_fajl, munka_max_b)[2]
              or (e["kilepes"] != 0 and _FAJLKORLAT_JEL.search(e["stderr"][-4096:]))):
            # a driver gyermeke (cc1, as, linker) a SIGXFSZ-szel hal meg, a driver hibával lép ki: egy fájl pontosan a
            # korláton áll, vagy a mappa a korlát fölött, vagy — ha a driver a félkész fájlt törölte — a stderr mondja
            e["allapot"], e["uzenet"] = "iras_korlat", _FORDIT_UZENET["iras_korlat"]
        elif e["jel"]:
            e["allapot"], e["uzenet"] = "jel", f"a fordító a {e['jel']} jellel leállt"
        elif e["kilepes"] == 0:
            e["allapot"], e["uzenet"] = "ok", ""
        else:
            e["allapot"], e["uzenet"] = "hiba", f"a fordító {e['kilepes']} kilépési kóddal állt le"
        return e

    # ------------------------------------------------------------------ önpróba

    def elerheto(self) -> tuple[bool, str]:
        """Önpróba: a futtató profil alatt elindul-e egy rendszerprogram (gyorsítótárazva)."""
        if self._elerheto is None:
            hiany = self._hiany()
            if hiany:
                self._elerheto = (False, hiany)
            else:
                import tempfile
                with tempfile.TemporaryDirectory(prefix="mos-hk-") as d:
                    e = self.futtat(Path("/bin/echo"), argv=["rendben"], munka=Path(d), idokorlat_s=10)
                self._elerheto = (e["allapot"] == "ok" and e["stdout"].strip() == b"rendben",
                                  e["uzenet"] or "rendben")
        return self._elerheto
