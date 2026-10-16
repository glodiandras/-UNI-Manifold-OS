"""F10: compile and run one program of a language profile — **only in the sandbox** (`homokozo.py`).

`Futtato(cfg, profil)` is a context manager with its own temporary folder (`{tmp}/kod/<prefix>-*`, removed at the end):

    with Futtato(cfg, profil) as f:
        f.hiany()                       → None, or {kod, param, uzenet}: the toolchain or the sandbox is missing (fails closed)
        p = f.fordit(source_text, "megoldas")              → Program (ok, diagnostics bound to source lines)
        r = f.futtat(p, "stdin…", argv=(…), idokorlat_s=…)  → {allapot, stdout, stderr, ido_ms, cpu_ms, csucs_mb, kilepes, jel, uzenet}

The interface is the C36b `modulok/cpp/ai_ellenorzes.Futtato`'s, so its test, reference and stress helpers work for every
language unchanged. C++ and C (`motor = cpp`) are served by the C36a engine itself (the C profile only swaps the compiler
command: `clang -x c -std=c17`), so the `.cpp` behaviour is untouched.

Compile step (`profil.fordit`): under `kod_fordit.sb` — exec from the toolchain roots, read the roots, the SDK and the
engine's helper scripts, write the work folder and the language's compiler cache. Native output (`{prog}`) runs under the
C36a run profile (exec of the binary only); interpreted programs run under `kod_futtat.sb` (exec of the interpreter only,
read its runtime and the program folder, write a fresh per-run folder).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from core import kod_nyelvek as KN

from . import diagnosztika as D
from .felderites import Felderites
from .homokozo import NyelviHomokozo

ITT = Path(__file__).resolve().parent
SEGEDEK = ITT / "segedek"
FORRAS_MAX_BAJT = 2 * 1024 * 1024
KIVONAT_MAX = 2000
MARADVANY_NAP_S = 86400
JVM_HEAP_ARANY = 0.75


@dataclass
class Program:
    """The C36b `Program` fields (ok, bin, allapot, diagnosztika, hiba_db, uzenet, ms) + the run plan of the language."""
    ok: bool
    bin: Path | None
    allapot: str
    diagnosztika: list
    hiba_db: int = 0
    uzenet: str = ""
    ms: float = 0.0
    nativ: bool = True
    mappa: Path | None = None          # the program folder (read-only for the run)
    figyelmeztetes_db: int = 0
    levagva: bool = False
    csucs_mb: float = 0.0
    kivonat: str = ""
    kod: str | None = None             # an error code for the UI (`kod.…`)

    def osszegzes(self) -> dict:
        return {"ok": self.ok, "allapot": self.allapot, "hiba_db": self.hiba_db, "uzenet": self.uzenet,
                "diagnosztika": self.diagnosztika[:8], "ms": self.ms}


def kivonat(s: bytes | str, tisztit: list[str] | None = None) -> str:
    s = s if isinstance(s, str) else s.decode("utf-8", "replace")
    for ut in tisztit or []:
        s = s.replace(ut + "/", "").replace(ut, "<run>")
    return s if len(s) <= KIVONAT_MAX else s[:KIVONAT_MAX] + "…"


class CEszkoztar:
    """The C profile on the portable LLVM: the C36a `Eszkoztar` with the C compiler command (`clang -x c -std=c17`). The
    source keeps the C36a sandbox name (`megoldas.cpp`); `-x c` makes it C."""

    def __new__(cls, cfg):
        from modulok.cpp.eszkoztar import Eszkoztar

        class _C(Eszkoztar):
            def parancs(self, forras: str, kimenet: str, mod: str = "gyors") -> list[str]:
                if mod not in KN.MODOK:
                    raise ValueError(f"unknown mode: {mod!r}")
                clang = self.bin("clang") if self.bin("clang").is_file() else self.bin("clang++")
                kapcsolok = [k for k in self.b[mod] if not k.startswith("-std=")]
                return [str(clang), "-x", "c", "-std=c17", *kapcsolok, "-fno-color-diagnostics", "-isysroot", str(self.sdk),
                        "-fuse-ld=lld", forras, "-o", kimenet]
        return _C(cfg)


def cpp_eszkoztar(cfg, profil: KN.Profil):
    from modulok.cpp.eszkoztar import Eszkoztar
    return CEszkoztar(cfg) if profil.azonosito == "c" else Eszkoztar(cfg)


class Futtato:
    def __init__(self, cfg, profil: KN.Profil, *, felderites: Felderites | None = None,
                 homokozo: NyelviHomokozo | None = None, megszakit=None, elotag: str = "ai"):
        self.cfg = cfg
        self.p = profil
        self.megszakit = megszakit or (lambda: False)
        self.h = homokozo or NyelviHomokozo(cfg)
        self.fd = felderites or Felderites(cfg, homokozo=self.h)
        self.b = KN.beallitasok(cfg)
        self.nyb = KN.nyelv_beallitas(self.b, profil.azonosito)
        self.elotag = elotag
        self.mappa: Path | None = None
        self._n = 0
        self._cpp = None
        if profil.motor == "cpp":
            from modulok.cpp import ai_ellenorzes as AE
            self._cpp = AE.Futtato(cfg, eszkoztar=cpp_eszkoztar(cfg, profil), homokozo=self.h, megszakit=self.megszakit)
            self.b = self._cpp.b

    # ------------------------------------------------------------------ the folder

    def __enter__(self) -> "Futtato":
        if self._cpp is not None:
            self._cpp.__enter__()
            self.mappa = self._cpp.mappa
            return self
        alap = self.cfg.path("tmp") / "kod"
        alap.mkdir(parents=True, exist_ok=True)
        most = time.time()
        for regi in alap.glob("*-*"):                       # leftovers of interrupted runs (own temporary folder)
            try:
                if regi.is_dir() and most - regi.stat().st_mtime > MARADVANY_NAP_S:
                    shutil.rmtree(regi, ignore_errors=True)
            except OSError:
                pass
        self.mappa = Path(tempfile.mkdtemp(prefix=f"{self.elotag}-", dir=alap)).resolve()
        return self

    def __exit__(self, *_):
        if self._cpp is not None:
            self._cpp.__exit__(*_)
        elif self.mappa is not None:
            shutil.rmtree(self.mappa, ignore_errors=True)
        self.mappa = None

    # ------------------------------------------------------------------ availability

    def nyelv_allapot(self) -> dict:
        return self.fd.nyelv(self.p)

    def hiany(self) -> dict | None:
        """The toolchain or the sandbox is missing → `{kod, param, uzenet}` (then nothing compiles or runs)."""
        st = self.fd.nyelv(self.p)
        if st["hiba"]:
            return st["hiba"]
        ok, uzenet = self.h.elerheto()
        if not ok:
            return {"kod": "kod.nincs_homokozo", "param": {"uzenet": uzenet}, "uzenet": f"The sandbox is not available: {uzenet}"}
        return None

    # ------------------------------------------------------------------ templates

    def _eszkozok(self) -> dict[str, dict]:
        return {e.nev: self.fd.eszkoz(e) for e in self.p.eszkozok}

    def _kifejt(self, sablon, munka: Path, memoria_mb: float | None = None) -> str:
        ki = str(sablon)
        csere = {"{forras}": str(munka / self.p.forras_nev), "{prog}": str(munka / "prog"), "{munka}": str(munka),
                 "{kimenet}": str(munka / "out"), "{segedek}": str(SEGEDEK), "{sdk}": self.fd.sdk() or "",
                 "{gyorsitotar}": str(self.fd.gyorsitotar(self.p)),
                 "{memoria_mb}": str(max(32, int((memoria_mb or 256) * JVM_HEAP_ARANY)))}
        for k, v in csere.items():
            ki = ki.replace(k, v)
        for nev, d in self._eszkozok().items():
            ki = ki.replace("{eszkoz:" + nev + "}", d.get("valos") or "")
        return ki

    def _gyokerek(self) -> list[str]:
        return [d["gyoker"] for d in self._eszkozok().values() if d.get("gyoker")]

    def _exe(self) -> Path:
        """The interpreter of the run (the first token of the run template)."""
        elso = self.p.futtat[0]
        nev = elso[len("{eszkoz:"):-1] if elso.startswith("{eszkoz:") else ""
        return Path(self._eszkozok()[nev]["valos"])

    # ------------------------------------------------------------------ compile

    def fordit(self, forras: str, nev: str = "prog", mod: str = "gyors") -> Program:
        if self._cpp is not None:
            p = self._cpp.fordit(forras, nev, mod)
            return Program(p.ok, p.bin, p.allapot, p.diagnosztika, p.hiba_db, p.uzenet, p.ms, True, p.bin.parent if p.bin else None)
        if self.mappa is None:
            raise RuntimeError("use the Futtato as a context manager")
        if not isinstance(forras, str) or not forras.strip():
            return Program(False, None, "nincs_forras", [], uzenet="There is no source code.", kod="kod.nincs_forras")
        if len(forras.encode("utf-8")) > FORRAS_MAX_BAJT:
            return Program(False, None, "tul_nagy", [], uzenet="The source is too large.", kod="kod.tul_nagy_forras")
        self._n += 1
        munka = self.mappa / f"{nev}-{self._n}"
        munka.mkdir()
        (munka / "out").mkdir()
        (munka / self.p.forras_nev).write_text(forras, encoding="utf-8")
        return self._fordit(munka)

    def fordit_fajl(self, forras_bajt: bytes, nev: str = "megoldas") -> Program:
        """Like `fordit`, from the bytes of a file (the check run keeps the exact bytes)."""
        if self._cpp is not None or self.mappa is None:
            raise RuntimeError("fordit_fajl is for the language engine, inside the context manager")
        self._n += 1
        munka = self.mappa / f"{nev}-{self._n}"
        munka.mkdir()
        (munka / "out").mkdir()
        (munka / self.p.forras_nev).write_bytes(forras_bajt)
        return self._fordit(munka)

    def _fordit(self, munka: Path) -> Program:
        p = self.p
        if not p.fordit:
            return Program(True, None, "ok", [], nativ=False, mappa=munka)
        gyokerek = self._gyokerek()
        tool_bin = [str(Path(e["valos"]).parent) for e in self._eszkozok().values() if e.get("valos")]
        env = {"HOME": str(munka), "TMPDIR": str(munka) + "/", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
               "PATH": ":".join([*tool_bin, "/usr/bin", "/bin"]), "NO_COLOR": "1", "TERM": "dumb"}
        env.update({k: self._kifejt(v, munka) for k, v in p.kornyezet.items()})
        olvas = [*gyokerek, str(SEGEDEK), *self.nyb["extra_olvas"]]
        if p.sdk and self.fd.sdk():
            olvas.append(self.fd.sdk())
        c = self.h.fordit_nyelv([self._kifejt(a, munka) for a in p.fordit], munka=munka,
                                exec_gyokerek=[*gyokerek, *self.nyb["extra_exec"]], olvas_gyokerek=olvas,
                                irhat=self.fd.gyorsitotar(p), kornyezet=env,
                                idokorlat_s=float(p.fordit_idokorlat_s or self.b["fordit_idokorlat_s"]),
                                memoria_mb=float(self.b["fordit_memoria_mb"]), kimenet_max_kb=int(self.b["kimenet_max_kb"]),
                                megszakit=self.megszakit, munka_max_mb=float(self.b["fordit_munka_max_mb"]),
                                munka_max_fajl=int(self.b["fordit_munka_max_fajl"]))
        szoveg = c["stderr"] + ("\n" + c["stdout"] if c["stdout"].strip() else "")
        tisztit = [str(munka), str(self.mappa)]
        d = D.fordito(p.diagnosztika, szoveg.replace(str(munka) + "/", ""), p.forras_nev)
        ok = c["allapot"] == "ok" and (not p.nativ or (munka / "prog").is_file())
        prog = Program(ok, None, c["allapot"], d["diagnosztika"], d["hiba_db"], c["uzenet"], c["ido_ms"], p.nativ, munka,
                       d["figyelmeztetes_db"], d["levagva"], c["csucs_mb"])
        if c["allapot"] == "megszakitva":
            return prog
        if not ok:
            prog.kivonat = kivonat(szoveg, tisztit) if not d["diagnosztika"] or c["allapot"] != "hiba" else ""
            if c["allapot"] == "ok":
                prog.uzenet, prog.kod = "The compiler produced no runnable program.", "kod.nincs_program"
            elif c["allapot"] == "hiba":
                prog.uzenet, prog.kod = "The compilation failed.", "kod.forditasi_hiba"
            return prog
        if p.nativ:
            binm = munka / "bin"
            binm.mkdir()
            shutil.copy2(munka / "prog", binm / "prog")
            os.chmod(binm / "prog", 0o755)
            prog.bin = binm / "prog"
        else:
            prog.bin = self._exe()
        return prog

    # ------------------------------------------------------------------ run

    def futtat(self, p: Program, bemenet: str = "", *, argv: tuple = (), idokorlat_s: float | None = None,
               memoria_mb: float | None = None) -> dict:
        if self._cpp is not None:
            from modulok.cpp.ai_ellenorzes import Program as CppProgram
            cp = CppProgram(p.ok, p.bin, p.allapot, p.diagnosztika, p.hiba_db, p.uzenet, p.ms)
            return self._cpp.futtat(cp, bemenet, argv=argv, idokorlat_s=idokorlat_s, memoria_mb=memoria_mb)
        r = self.futtat_nyers(p, bemenet.encode("utf-8"), argv=argv, idokorlat_s=idokorlat_s, memoria_mb=memoria_mb)
        return r | {"stdout": r["stdout"].decode("utf-8", "replace"), "stderr": r["stderr"].decode("utf-8", "replace")}

    def alap_memoria(self) -> float:
        return float(self.b["memoria_mb"] if self.p.nativ else self.b["ertelmezo_memoria_mb"])

    def futtat_nyers(self, p: Program, bemenet: bytes, *, argv: tuple = (), idokorlat_s: float | None = None,
                     memoria_mb: float | None = None) -> dict:
        """One run → the sandbox result (bytes outputs) + `idokorlat_s`, `memoria_mb`."""
        if not p.ok or p.mappa is None:
            return {"allapot": "nincs_program", "stdout": b"", "stderr": b"", "ido_ms": 0.0, "cpu_ms": 0.0, "csucs_mb": 0.0,
                    "kilepes": None, "jel": None, "uzenet": "The program did not compile.", "idokorlat_s": None,
                    "memoria_mb": None}
        ido = float(idokorlat_s or self.b["teszt_idokorlat_s"])
        mem = float(memoria_mb or self.alap_memoria())
        self._n += 1
        munka = self.mappa / f"futas-{self._n}"
        munka.mkdir()
        b = self.b
        kozos = dict(munka=munka, idokorlat_s=ido, memoria_mb=mem, kimenet_max_kb=int(b["kimenet_max_kb"]),
                     stderr_max_kb=int(b["stderr_max_kb"]), munka_max_mb=float(b["munka_max_mb"]),
                     munka_max_fajl=int(b["munka_max_fajl"]), mintavetel_ms=float(b["mintavetel_ms"]), megszakit=self.megszakit)
        try:
            if p.nativ:
                env = {"RUST_BACKTRACE": "0", "GOTRACEBACK": "single"} if self.p.azonosito in ("rust", "go") else {}
                r = self.h.futtat(p.bin, argv=[str(a) for a in argv], bemenet=bemenet, kornyezet=env, **kozos)
            else:
                parancs = [self._kifejt(a, p.mappa, mem) for a in self.p.futtat] + [str(a) for a in argv]
                env = {"HOME": str(munka), "TMPDIR": str(munka) + "/", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
                       "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                       "NO_COLOR": "1", "NODE_DISABLE_COLORS": "1", "TERM": "dumb"}
                ertelmezo = Path(self.nyb["ertelmezo"]) if self.nyb["ertelmezo"] else None
                r = self.h.futtat_nyelv(parancs, exe=self._exe(), ertelmezo=ertelmezo,
                                        olvas_gyokerek=[*self._gyokerek(), str(p.mappa)], bemenet=bemenet, kornyezet=env,
                                        **kozos)
        finally:
            shutil.rmtree(munka, ignore_errors=True)
        return r | {"idokorlat_s": ido, "memoria_mb": mem}
