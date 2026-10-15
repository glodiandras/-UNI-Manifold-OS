"""Egy folyamat memóriája a szülőből (a homokozó memóriaőre, T059: a `setrlimit` macOS-en ValueError).

Elsődleges: `proc_pid_rusage` (libproc, ctypes) → `ri_phys_footprint` (a tömörített lapokkal együtt, ezt mutatja
a Tevékenységfigyelő is). Linuxon (a cloud-tesztek) a `/proc/<pid>/status` `VmRSS`-e. Tartalék: `ps -o rss=` (lassabb,
egy folyamatindítás mintánként). `psutil` nincs.

A `csoport_mb` egy folyamatcsoport összegét adja (a fordító drivere a `cc1`-et és a linkert gyermekként indítja,
mind a csoportban marad; Audit 3 A3-16): macOS-en `proc_listpids(PROC_PGRP_ONLY)`, Linuxon a `/proc/*/stat`, különben
`ps -A -o pgid=,rss=`. A `None` a hívónak jel: ha a folyamat él, a memóriaőr zárva hibázik.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess

_RUSAGE_INFO_V0 = 0
_PROC_PGRP_ONLY = 2
_PROC = "/proc"


class _RusageInfoV0(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins",
        "ri_wired_size", "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime", "ri_proc_exit_abstime")]


def _libproc():
    nev = ctypes.util.find_library("proc")
    if not nev:
        return None
    try:
        lib = ctypes.CDLL(nev)
        lib.proc_pid_rusage.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        lib.proc_pid_rusage.restype = ctypes.c_int
        lib.proc_listpids.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int)
        lib.proc_listpids.restype = ctypes.c_int
        return lib
    except (OSError, AttributeError):
        return None


_LIB = _libproc()


def _ps_mb(pid: int) -> float | None:
    try:
        ki = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return int(ki.stdout.strip()) / 1024 if ki.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _proc_mb(pid: int) -> float | None:
    try:
        with open(f"{_PROC}/{pid}/status", encoding="ascii", errors="replace") as f:
            for sor in f:
                if sor.startswith("VmRSS:"):
                    return int(sor.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        return None
    return None                                         # zombi vagy kernelszál: nincs VmRSS


def _van_proc() -> bool:
    return os.path.isfile(f"{_PROC}/self/status")


def mb(pid: int) -> float | None:
    """A folyamat memóriája MB-ban; None, ha a folyamat már nem él (vagy nem olvasható)."""
    if _LIB is not None:
        info = _RusageInfoV0()
        if _LIB.proc_pid_rusage(pid, _RUSAGE_INFO_V0, ctypes.byref(info)) == 0:
            return info.ri_phys_footprint / 2 ** 20
        return None
    if _van_proc():
        return _proc_mb(pid)
    return _ps_mb(pid)


def _csoport_pidek_libproc(pgid: int) -> list[int] | None:
    meret = 256
    while meret <= 65536:
        buf = (ctypes.c_int * meret)()
        n = _LIB.proc_listpids(_PROC_PGRP_ONLY, pgid, buf, ctypes.sizeof(buf))
        if n <= 0:
            return None
        db = n // ctypes.sizeof(ctypes.c_int)
        if db < meret:
            return [p for p in buf[:db] if p > 0]
        meret *= 4
    return None


def _csoport_pidek_proc(pgid: int) -> list[int] | None:
    pidek = []
    try:
        nevek = os.listdir(_PROC)
    except OSError:
        return None
    for nev in nevek:
        if not nev.isdigit():
            continue
        try:
            with open(f"{_PROC}/{nev}/stat", "rb") as f:
                mezok = f.read().rsplit(b")", 1)[1].split()      # a név zárójele után: állapot, ppid, pgrp, …
            if int(mezok[2]) == pgid:
                pidek.append(int(nev))
        except (OSError, ValueError, IndexError):
            continue
    return pidek


def _ps_csoport_mb(pgid: int) -> float | None:
    try:
        ki = subprocess.run(["ps", "-A", "-o", "pgid=,rss="], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    ossz, talalt = 0.0, False
    for sor in ki.stdout.splitlines():
        try:
            g, r = sor.split()
            if int(g) == pgid:
                ossz += int(r) / 1024
                talalt = True
        except ValueError:
            continue
    return ossz if talalt else None


def csoport_mb(pgid: int) -> float | None:
    """A folyamatcsoport tagjainak összmemóriája MB-ban; None, ha a csoport nem olvasható (vagy már senki nem él benne).
    A közben kilépő tag kimarad (nem hiba)."""
    if _LIB is not None:
        pidek = _csoport_pidek_libproc(pgid)
    elif _van_proc():
        pidek = _csoport_pidek_proc(pgid)
    else:
        return _ps_csoport_mb(pgid)
    if not pidek:
        return None
    ertekek = [m for m in (mb(p) for p in pidek) if m is not None]
    return sum(ertekek) if ertekek else None


def forras() -> str:
    return "proc_pid_rusage" if _LIB is not None else ("/proc" if _van_proc() else "ps")
