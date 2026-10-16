"""F10: the check run of a language profile (⌘R): compile (or syntax-check) once, then each `teszt` block in the sandbox.

The events are the C36a ones (`modulok/cpp/ellenorzes.py`), every event also carries `nyelv` (the profile id) and `forras`
(the displayed source name):

    indul        {mod, tesztek_db, forras, jegyzet}
    fordit_kesz  {fordit: {ok, allapot, ms, csucs_mb, diagnosztika, hiba_db, figyelmeztetes_db, levagva, uzenet, kivonat, kod}}
    teszt        {teszt: {sorszam, cim, allapot, ido_ms, cpu_ms, csucs_mb, idokorlat_s, memoria_mb, osszevetes, kilepes, jel,
                          diff, stdout_kivonat, stderr_kivonat, jelentes, uzenet, hiba}, kesz_db, ossz}
    kesz         {atment, tesztek_db, atment_db, fordit_ok, ms, mod, hash, uzenet}
    hiba         {kod, param, uzenet}       the toolchain or the sandbox is missing, or the source is unreadable
    megszakitva  {}

C++ and C go to the C36a engine unchanged (`motor = cpp`; the `.cpp` regression gate), with the two extra fields added.
Test states of the language engine: `atment`, `hibas_kimenet`, `futasi_hiba` (non-zero exit or signal, with the runtime
report bound to a source line), `idotullepes`, `memoria`, `kimenet_tullepes`, `iras_korlat`, `hibas_teszt`, `homokozo_hiba`.
Only the `gyors` mode exists outside C/C++ (`hibakereso` is the sanitizer build of C36a).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from core import kod_nyelvek as KN
from modulok.cpp import osszevet

from . import diagnosztika as D
from .futtato import FORRAS_MAX_BAJT, Futtato, cpp_eszkoztar, kivonat

_ALLAPOT_UZENET = {"idotullepes": "The program exceeded the time limit.",
                   "memoria": "The program exceeded the memory limit.",
                   "kimenet_tullepes": "The program wrote too much output.",
                   "iras_korlat": "The program wrote too much into its own folder.",
                   "homokozo_hiba": "The sandbox stopped the run."}


def futasi_nevek(p: KN.Profil) -> tuple[str, ...]:
    """The file names a runtime report of the program may cite: the source, and the run file of the template (TypeScript:
    the stripped `megoldas.js`, whose lines are the source's lines in `strip` mode)."""
    nevek = [p.forras_nev]
    if p.futtat:
        utolso = Path(p.futtat[-1].replace("{forras}", p.forras_nev)).name
        if "." in utolso and utolso not in nevek:
            nevek.append(utolso)
    return tuple(nevek)


class Ellenorzes:
    def __init__(self, cfg, profil: KN.Profil, *, esemeny=None, megszakit=None, felderites=None, homokozo=None):
        self.cfg = cfg
        self.p = profil
        self._esemeny = esemeny or (lambda _d: None)
        self._megszakit = megszakit or (lambda: False)
        self.felderites = felderites
        self.homokozo = homokozo
        self._nev = ""

    def ki(self, szakasz: str, **adat) -> dict:
        d = {"szakasz": szakasz, "nyelv": self.p.azonosito, "forras": self._nev, **adat}
        self._esemeny(d)
        return d

    def _hiba(self, kod: str, uzenet: str, param: dict, mod: str, kezdet: float) -> dict:
        self.ki("hiba", kod=kod, param=param, uzenet=uzenet)
        return {"atment": False, "tesztek_db": 0, "atment_db": 0, "fordit_ok": False, "ms": round((time.monotonic() - kezdet) * 1000),
                "mod": mod, "hash": None, "uzenet": uzenet}

    def fut(self, forras: Path, tesztek: list, mod: str = "gyors", jegyzet: str | None = None) -> dict:
        forras = Path(forras)
        self._nev = forras.name
        if self.p.motor == "cpp":
            return self._cpp(forras, tesztek, mod, jegyzet)
        kezdet = time.monotonic()
        if mod != "gyors":
            return self._hiba("kod.mod_nem_tamogatott", f"The {mod} mode is only available for C and C++.",
                              {"mod": mod, "nyelv": self.p.nev}, mod, kezdet)
        with Futtato(self.cfg, self.p, felderites=self.felderites, homokozo=self.homokozo, megszakit=self._megszakit,
                     elotag="futas") as f:
            h = f.hiany()
            if h:
                return self._hiba(h["kod"], h["uzenet"], h["param"], mod, kezdet)
            try:
                bajtok = forras.read_bytes()
            except OSError as exc:
                return self._hiba("kod.nincs_forras", f"The source is not readable: {exc}", {"ut": forras.name}, mod, kezdet)
            if len(bajtok) > FORRAS_MAX_BAJT:
                return self._hiba("kod.tul_nagy_forras", f"The source is too large (at most {FORRAS_MAX_BAJT >> 20} MiB).",
                                  {"max_mib": FORRAS_MAX_BAJT >> 20}, mod, kezdet)
            sha = hashlib.sha256(bajtok).hexdigest()
            return self._fut(f, bajtok, sha, tesztek, mod, jegyzet, kezdet)

    # ------------------------------------------------------------------ C / C++: the C36a engine

    def _cpp(self, forras: Path, tesztek: list, mod: str, jegyzet: str | None) -> dict:
        from modulok.cpp import ellenorzes as E

        def tovabb(d: dict) -> None:
            self._esemeny({**d, "nyelv": self.p.azonosito, "forras": self._nev})
        return E.Ellenorzes(self.cfg, esemeny=tovabb, eszkoztar=cpp_eszkoztar(self.cfg, self.p), homokozo=self.homokozo,
                            megszakit=self._megszakit).fut(forras, tesztek, mod, jegyzet=jegyzet)

    # ------------------------------------------------------------------ the language engine

    def _megszakitva(self, mod: str, sha: str, ossz: int, atment_db: int, kezdet: float) -> dict:
        self.ki("megszakitva")
        return {"atment": False, "tesztek_db": ossz, "atment_db": atment_db, "fordit_ok": False,
                "ms": round((time.monotonic() - kezdet) * 1000), "mod": mod, "hash": sha, "uzenet": "interrupted"}

    def _kesz(self, fordit_ok: bool, ossz: int, atment_db: int, mod: str, sha: str, kezdet: float, uzenet: str,
              kod: str | None = None) -> dict:
        d = {"atment": fordit_ok and ossz > 0 and atment_db == ossz, "tesztek_db": ossz, "atment_db": atment_db,
             "fordit_ok": fordit_ok, "ms": round((time.monotonic() - kezdet) * 1000), "mod": mod, "hash": sha,
             "uzenet": uzenet, "kod": kod}
        self.ki("kesz", **d)
        return d

    def _fut(self, f: Futtato, bajtok: bytes, sha: str, tesztek: list, mod: str, jegyzet, kezdet: float) -> dict:
        self.ki("indul", mod=mod, tesztek_db=len(tesztek), jegyzet=jegyzet)
        if self._megszakit():
            return self._megszakitva(mod, sha, len(tesztek), 0, kezdet)
        p = f.fordit_fajl(bajtok, "megoldas")
        if p.allapot == "megszakitva":
            return self._megszakitva(mod, sha, len(tesztek), 0, kezdet)
        fordit = {"ok": p.ok, "allapot": p.allapot, "ms": p.ms, "csucs_mb": p.csucs_mb, "diagnosztika": p.diagnosztika,
                  "hiba_db": p.hiba_db, "figyelmeztetes_db": p.figyelmeztetes_db, "levagva": p.levagva,
                  "uzenet": p.uzenet, "kivonat": p.kivonat, "kod": p.kod}
        self.ki("fordit_kesz", fordit=D.nev_csere(fordit, self.p.forras_nev, self._nev))
        if not p.ok:
            return self._kesz(False, len(tesztek), 0, mod, sha, kezdet, "The compilation failed.", "kod.forditasi_hiba")
        if not tesztek:
            return self._kesz(True, 0, 0, mod, sha, kezdet, "There is no test block in the note: only the compile step ran.",
                              "kod.nincs_teszt")
        atment_db = 0
        for i, t in enumerate(tesztek, 1):
            if self._megszakit():
                return self._megszakitva(mod, sha, len(tesztek), atment_db, kezdet)
            e = self._teszt(f, p, t)
            if e is None:
                return self._megszakitva(mod, sha, len(tesztek), atment_db, kezdet)
            atment_db += e["allapot"] == "atment"
            self.ki("teszt", teszt=e, kesz_db=i, ossz=len(tesztek))
        return self._kesz(True, len(tesztek), atment_db, mod, sha, kezdet, "")

    def _teszt(self, f: Futtato, p, t) -> dict | None:
        alap = {"sorszam": t.sorszam, "cim": t.cim, "allapot": None, "ido_ms": 0.0, "cpu_ms": 0.0, "csucs_mb": 0.0,
                "idokorlat_s": None, "memoria_mb": None, "osszevetes": t.osszevetes, "kilepes": None, "jel": None, "diff": None,
                "stdout_kivonat": "", "stderr_kivonat": "", "jelentes": None, "uzenet": "", "hiba": None}
        if t.hiba:
            return alap | {"allapot": "hibas_teszt", "hiba": t.hiba, "uzenet": t.hiba}
        r = f.futtat_nyers(p, t.bemenet.encode("utf-8"), idokorlat_s=t.idokorlat_s, memoria_mb=t.memoria_mb)
        if r["allapot"] == "megszakitva":
            return None
        tisztit = [str(f.mappa)] if f.mappa else []
        stdout = r["stdout"].decode("utf-8", "replace")
        stderr = r["stderr"].decode("utf-8", "replace")
        e = alap | {"ido_ms": r["ido_ms"], "cpu_ms": r["cpu_ms"], "csucs_mb": r["csucs_mb"], "idokorlat_s": r["idokorlat_s"],
                    "memoria_mb": r["memoria_mb"], "kilepes": r["kilepes"], "jel": r["jel"],
                    "stderr_kivonat": kivonat(stderr, tisztit), "uzenet": r["uzenet"]}
        allapot = r["allapot"]
        if allapot == "ok":
            eps = t.eps if t.eps is not None else float(f.b["lebego_eps"])
            if osszevet.egyezik(t.kimenet, stdout, t.osszevetes, eps):
                return e | {"allapot": "atment", "uzenet": ""}
            return e | {"allapot": "hibas_kimenet", "diff": osszevet.diff(t.kimenet, stdout, mod=t.osszevetes, eps=eps),
                        "stdout_kivonat": kivonat(stdout), "uzenet": "The output differs from the expected one."}
        if allapot in ("kilepesi_hiba", "jel"):
            nevek = futasi_nevek(self.p)
            j = D.jelentes(self.p.jelentes, stderr, nevek)
            if j is not None:
                j = D.nev_csere(j, nevek, self._nev)
            return e | {"allapot": "futasi_hiba", "jelentes": j, "stdout_kivonat": kivonat(stdout),
                        "uzenet": (j or {}).get("leiras") or r["uzenet"]}
        return e | {"allapot": allapot, "uzenet": _ALLAPOT_UZENET.get(allapot, r["uzenet"]), "stdout_kivonat": kivonat(stdout)}
