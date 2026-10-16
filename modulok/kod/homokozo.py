"""F10: the sandbox of the language profiles — the C36a program sandbox (`modulok/homokozo/program.py`) with two more
profiles (`kod_fordit.sb`, `kod_futtat.sb`). The limits and the guarding are the C36a ones, reused, not copied: the parent's
hard time limit (SIGKILL on the process group) + `RLIMIT_CPU`, the memory guard (`phys_footprint`, failing closed), the
output limit, `RLIMIT_FSIZE` + the work folder size and file count. Without `sandbox-exec` nothing runs (`homokozo_hiba`).

    h = NyelviHomokozo(cfg)
    h.fordit_nyelv(argv, munka=…, exec_gyokerek=[…], olvas_gyokerek=[…], irhat=…)       → like Programhomokozo.fordit
    h.futtat_nyelv(argv, exe=…, olvas_gyokerek=[…], munka=…, bemenet=b"…")              → like Programhomokozo.futtat
    h.futtat(bin, …)                                                                     native binaries: the C36a run profile
"""
from __future__ import annotations

import os
import resource
import subprocess
import time
from pathlib import Path

from modulok.homokozo.program import _FORDIT_UZENET, _UZENET, FORDIT_MUNKA_MAX_FAJL, FORDIT_MUNKA_MAX_MB, Programhomokozo, \
    _munka_meret

ITT = Path(__file__).resolve().parent
PROFIL_FORDIT = ITT / "kod_fordit.sb"
PROFIL_FUTTAT = ITT / "kod_futtat.sb"
NINCS = ITT / ".nincs"                  # an unused slot: a path that does not exist (and nothing may create it)
OLVAS_SLOT_FORDIT = 6
OLVAS_SLOT_FUTTAT = 4
EXEC_SLOT = 4


class SlotHiba(ValueError):
    """More roots than the profile has slots."""


def _slotok(nev: str, utak: list, db: int) -> dict[str, str]:
    egyedi: list[str] = []
    for u in utak:
        if u is None:
            continue
        r = os.path.realpath(str(u))
        if r not in egyedi:
            egyedi.append(r)
    if len(egyedi) > db:
        raise SlotHiba(f"too many {nev} roots ({len(egyedi)} > {db})")
    return {f"{nev}_{i}": (egyedi[i - 1] if i <= len(egyedi) else str(NINCS)) for i in range(1, db + 1)}


class NyelviHomokozo(Programhomokozo):

    def _allapot(self, proc, r: dict, e: dict, munka: Path, munka_max_b: int, munka_max_fajl: int, fordit: bool) -> dict:
        """The C36a status mapping of a finished process (the same order of checks as `Programhomokozo`)."""
        uzenetek = _FORDIT_UZENET if fordit else _UZENET
        e["kilepes"], e["jel"] = self._kilepes(proc)
        hiba_allapot = "hiba" if fordit else "kilepesi_hiba"
        if r["allapot"]:
            e["allapot"], e["uzenet"] = r["allapot"], uzenetek[r["allapot"]]
        elif e["jel"] == "SIGXFSZ" or (e["kilepes"] != 0 and (
                self._elerte_a_fajlmeret_korlatot(munka, munka_max_b) or _munka_meret(munka, munka_max_fajl, munka_max_b)[2])):
            e["allapot"], e["uzenet"] = "iras_korlat", uzenetek["iras_korlat"]
        elif e["jel"]:
            e["allapot"], e["uzenet"] = "jel", f"the {'compiler' if fordit else 'program'} was stopped by {e['jel']}"
        elif e["kilepes"] == 0:
            e["allapot"], e["uzenet"] = "ok", ""
        else:
            e["allapot"], e["uzenet"] = hiba_allapot, (f"the {'compiler' if fordit else 'program'} exited with code "
                                                         f"{e['kilepes']}")
        return e

    def fordit_nyelv(self, parancs: list[str], *, munka: Path, exec_gyokerek: list, olvas_gyokerek: list,
                     irhat: Path | None = None, kornyezet: dict[str, str] | None = None, idokorlat_s: float = 60.0,
                     memoria_mb: float = 4096, kimenet_max_kb: int = 1024, mintavetel_ms: float = 50, megszakit=None,
                     munka_max_mb: float = FORDIT_MUNKA_MAX_MB, munka_max_fajl: int = FORDIT_MUNKA_MAX_FAJL) -> dict:
        """A compile / check step under `kod_fordit.sb`. → `{allapot, kilepes, jel, ido_ms, csucs_mb, stdout, stderr, pid,
        uzenet}` (str outputs); the status is one of `FORDITAS_ALLAPOTOK`. The memory is the process group's sum."""
        e = {"allapot": "homokozo_hiba", "kilepes": None, "jel": None, "ido_ms": 0.0, "csucs_mb": 0.0, "stdout": "",
             "stderr": "", "stderr_levagva": False, "pid": None, "uzenet": ""}
        hiany = self._hiany()
        if hiany:
            return e | {"uzenet": hiany}
        munka = Path(self._rp(munka))
        try:
            params = {**_slotok("EXEC", exec_gyokerek, EXEC_SLOT), **_slotok("OLVAS", olvas_gyokerek, OLVAS_SLOT_FORDIT),
                      "IRHAT": self._rp(irhat) if irhat else str(munka), "MUNKA": str(munka)}
        except SlotHiba as exc:
            return e | {"uzenet": str(exc)}
        env = {str(k): str(v) for k, v in (kornyezet or {}).items()}
        munka_max_b = int(munka_max_mb * 1024 * 1024)
        indul = time.monotonic()
        try:
            proc = self._inditas(PROFIL_FORDIT, params, list(parancs), cwd=munka, env=env, stdin=subprocess.DEVNULL,
                                 cpu_s=idokorlat_s * 2, fsize_b=munka_max_b)
        except (OSError, subprocess.SubprocessError) as exc:
            return e | {"uzenet": f"the compiler does not start: {exc}"}
        e["pid"] = proc.pid
        r = self._fut(proc, b"", idokorlat_s, memoria_mb, kimenet_max_kb * 1024, kimenet_max_kb * 1024, munka, munka_max_fajl,
                      munka_max_b, mintavetel_ms, megszakit, csoport=True)
        e.update(stdout=r["stdout"].decode("utf-8", "replace"), stderr=r["stderr"].decode("utf-8", "replace"),
                 stderr_levagva=r["stderr_levagva"], csucs_mb=r["csucs_mb"], ido_ms=round((time.monotonic() - indul) * 1000, 1))
        return self._allapot(proc, r, e, munka, munka_max_b, munka_max_fajl, fordit=True)

    def futtat_nyelv(self, parancs: list[str], *, exe: Path, olvas_gyokerek: list, munka: Path, bemenet: bytes = b"",
                     ertelmezo: Path | None = None, idokorlat_s: float = 2.0, memoria_mb: float = 512,
                     kimenet_max_kb: int = 1024, stderr_max_kb: int = 64, munka_max_mb: float = 16, munka_max_fajl: int = 256,
                     kornyezet: dict[str, str] | None = None, mintavetel_ms: float = 20, megszakit=None) -> dict:
        """One run of an interpreted program under `kod_futtat.sb` (`exe`: the interpreter, the only executable).
        → like `Programhomokozo.futtat` (bytes outputs); the status is one of `FUTTATAS_ALLAPOTOK`."""
        e = {"allapot": "homokozo_hiba", "kilepes": None, "jel": None, "ido_ms": 0.0, "cpu_ms": 0.0, "csucs_mb": 0.0,
             "stdout": b"", "stderr": b"", "stderr_levagva": False, "pid": None, "uzenet": ""}
        hiany = self._hiany()
        if hiany:
            return e | {"uzenet": hiany}
        exe = Path(exe)
        if not (exe.is_file() and os.access(exe, os.X_OK)):
            return e | {"uzenet": f"the interpreter is missing or not executable: {exe}"}
        munka = Path(self._rp(munka))
        try:
            params = {"EXE": str(exe), "EXE_VALOS": self._rp(exe),
                      "EXE_2": self._rp(ertelmezo) if ertelmezo else self._rp(exe),
                      **_slotok("OLVAS", olvas_gyokerek, OLVAS_SLOT_FUTTAT), "MUNKA": str(munka)}
        except SlotHiba as exc:
            return e | {"uzenet": str(exc)}
        env = {str(k): str(v) for k, v in (kornyezet or {}).items()}
        munka_max_b = int(munka_max_mb * 1024 * 1024)
        elo = resource.getrusage(resource.RUSAGE_CHILDREN)
        indul = time.monotonic()
        try:
            proc = self._inditas(PROFIL_FUTTAT, params, [str(a) for a in parancs], cwd=munka, env=env, stdin=subprocess.PIPE,
                                 cpu_s=idokorlat_s, fsize_b=munka_max_b)
        except (OSError, subprocess.SubprocessError) as exc:
            return e | {"uzenet": f"the program does not start: {exc}"}
        e["pid"] = proc.pid
        r = self._fut(proc, bemenet, idokorlat_s, memoria_mb, kimenet_max_kb * 1024, stderr_max_kb * 1024, munka,
                      munka_max_fajl, munka_max_b, mintavetel_ms, megszakit)
        utan = resource.getrusage(resource.RUSAGE_CHILDREN)
        e.update(stdout=r["stdout"], stderr=r["stderr"], stderr_levagva=r["stderr_levagva"], csucs_mb=r["csucs_mb"],
                 ido_ms=round((time.monotonic() - indul) * 1000, 1),
                 cpu_ms=round(((utan.ru_utime + utan.ru_stime) - (elo.ru_utime + elo.ru_stime)) * 1000, 1))
        return self._allapot(proc, r, e, munka, munka_max_b, munka_max_fajl, fordit=False)
