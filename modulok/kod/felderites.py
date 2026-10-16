"""F10: toolchain discovery of the language profiles (`core/kod_nyelvek.py`). No download (D3): a missing toolchain is a
clear error with `kod` + `param` + an English message, never a fallback to something else.

The candidates of a tool, in order: the config override (`[kod.eszkozok] <name>`, placeholders expanded), the embedded
runtime (`[utak]` key, `{runtime}/…`, the engine's own Python), then the system PATH. A candidate counts only if its version
probe exits 0 **inside the compile sandbox** (exec only from the tool's own root): the macOS `/usr/bin/java` stub without a
JDK fails it. The tool's root (`gyoker`) is the exec / read root of the sandbox profiles; a root that is too broad (`/`,
`/usr`, `/usr/local`, `/opt/homebrew`, …) is refused rather than opened up. On macOS the `xcrun` shims (`/usr/bin/swiftc`,
`/usr/bin/clang`) are resolved to the real tool with `xcrun --find`; the SDK of Swift/Rust comes from the config, `xcrun
--show-sdk-path`, or the portable `{sdk}` copy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core import kod_nyelvek as KN

from .homokozo import NyelviHomokozo

TUL_TAG = frozenset({"/", "/usr", "/usr/local", "/usr/bin", "/bin", "/opt", "/opt/homebrew", "/opt/local", "/System",
                     "/Library", "/Applications", "/private", "/Users", "/Volumes", "/sbin", "/usr/sbin"})
XCRUN_SHIM_MAPPAK = ("/usr/bin",)


def _hiba(kod: str, uzenet: str, **param) -> dict:
    return {"kod": kod, "param": param, "uzenet": uzenet}


class Felderites:
    """Discovery with a per-instance cache. `futtato(argv, timeout) -> (rc, out)` runs the xcrun queries (tests replace it)."""

    def __init__(self, cfg, *, homokozo: NyelviHomokozo | None = None, which=shutil.which, futtato=None):
        self.cfg = cfg
        self.b = KN.beallitasok(cfg)
        self.h = homokozo or NyelviHomokozo(cfg)
        self.which = which
        self.futtato = futtato or self._futtat
        self._eszkoz: dict[str, dict] = {}
        self._sdk: str | None | bool = False

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _futtat(argv: list[str], timeout: float) -> tuple[int, str]:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                               env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")})
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, str(exc)

    def _kifejt(self, s: str) -> str:
        s = os.path.expanduser(str(s))
        return self.cfg.expand(s) if self.cfg is not None and "{" in s else s

    def _jeloltek(self, e: KN.Eszkoz) -> list[tuple[str, str]]:
        ki: list[tuple[str, str]] = []
        konfig = (self.b.get("eszkozok") or {}).get(e.nev)
        if konfig:
            ki.append(("konfig", self._kifejt(konfig)))
            return ki                                   # an explicit setting is not second-guessed by PATH
        if self.cfg is not None and e.utak_kulcs:
            try:
                ki.append(("runtime", str(self.cfg.path(e.utak_kulcs))))
            except Exception:                            # noqa: BLE001 — the key is not defined in this layout
                pass
        if self.cfg is not None and e.runtime_ut:
            try:
                ki.append(("runtime", str(self.cfg.path("runtime") / e.runtime_ut)))
            except Exception:                            # noqa: BLE001
                pass
        if e.sajat_python:
            ki.append(("runtime", sys.executable))
        for n in e.path_nevek:
            w = self.which(n)
            if w:
                ki.append(("path", w))
        return ki

    def _xcrun_feloldas(self, ut: str, nev: str) -> str:
        if sys.platform != "darwin" or not any(ut.startswith(m + "/") for m in XCRUN_SHIM_MAPPAK):
            return ut
        xcrun = self.which("xcrun")
        if not xcrun:
            return ut
        rc, out = self.futtato([xcrun, "--find", nev], self.b["felderites_idokorlat_s"])
        sor = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
        return sor if sor.startswith("/") and os.access(sor, os.X_OK) else ut

    @staticmethod
    def gyoker(valos: str, szint: int) -> str:
        p = Path(valos)
        for _ in range(max(1, szint)):
            p = p.parent
        return str(p)

    def _probal(self, valos: str, gyoker: str, e: KN.Eszkoz) -> tuple[bool, str]:
        """The version probe inside the compile sandbox (exec only from the tool's root)."""
        alap = self.cfg.path("tmp") / "kod" if self.cfg is not None else Path(tempfile.gettempdir())
        alap.mkdir(parents=True, exist_ok=True)
        extra = [str(x) for x in self.b.get("extra_exec") or []]    # `[kod] extra_exec` (e.g. a launcher script's shell)
        with tempfile.TemporaryDirectory(prefix="felderit-", dir=alap) as d:
            r = self.h.fordit_nyelv([valos, *e.verzio], munka=Path(d), exec_gyokerek=[gyoker, *extra],
                                    olvas_gyokerek=[gyoker], kornyezet={"HOME": d, "TMPDIR": d, "PATH": "/usr/bin:/bin"},
                                    idokorlat_s=float(self.b["felderites_idokorlat_s"]), memoria_mb=2048, kimenet_max_kb=64)
        szoveg = (r["stdout"] + "\n" + r["stderr"]).strip()
        sor = next((s.strip() for s in szoveg.splitlines() if s.strip()), "")
        return r["allapot"] == "ok", (sor[:160] if r["allapot"] == "ok" else (r["uzenet"] or sor)[:300])

    # ------------------------------------------------------------------ public

    def eszkoz(self, e: KN.Eszkoz) -> dict:
        """→ `{nev, ok, ut, valos, gyoker, forras (konfig|runtime|path), verzio, hiba}`."""
        if e.nev in self._eszkoz:
            return self._eszkoz[e.nev]
        ki = {"nev": e.nev, "ok": False, "ut": None, "valos": None, "gyoker": None, "forras": None, "verzio": None,
              "hiba": None, "probak": []}
        for forras, ut in self._jeloltek(e):
            if not (os.path.isfile(ut) and os.access(ut, os.X_OK)):
                ki["probak"].append({"ut": ut, "forras": forras, "hiba": "not found"})
                continue
            # the invoked path keeps its name (a driver may act by argv[0]: swiftc → swift-frontend, clang++ → clang-NN);
            # the root comes from the real path
            hivas = os.path.abspath(self._xcrun_feloldas(ut, e.nev) if e.xcrun else ut)
            gy = os.path.realpath(self.gyoker(os.path.realpath(hivas), e.gyoker_szint))
            if gy in TUL_TAG or len(Path(gy).parts) < 3:
                ki["probak"].append({"ut": ut, "forras": forras, "hiba": f"toolchain root too broad: {gy}"})
                continue
            ok, szoveg = self._probal(hivas, gy, e)
            if ok:
                ki.update(ok=True, ut=ut, valos=hivas, gyoker=gy, forras=forras, verzio=szoveg)
                break
            ki["probak"].append({"ut": ut, "forras": forras, "hiba": szoveg or "the version probe failed"})
        if not ki["ok"]:
            ki["hiba"] = _hiba("kod.nincs_eszkoz", f"No usable `{e.nev}` found", eszkoz=e.nev)
        self._eszkoz[e.nev] = ki
        return ki

    def sdk(self) -> str | None:
        """The macOS SDK for Swift/Rust: `[kod.eszkozok] sdk`, `xcrun --show-sdk-path`, then the portable `{sdk}`."""
        if self._sdk is not False:
            return self._sdk  # type: ignore[return-value]
        jelolt = None
        konfig = (self.b.get("eszkozok") or {}).get("sdk")
        if konfig:
            jelolt = self._kifejt(konfig)
        elif sys.platform == "darwin" and self.which("xcrun"):
            rc, out = self.futtato([self.which("xcrun"), "--show-sdk-path"], self.b["felderites_idokorlat_s"])
            sor = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
            jelolt = sor if sor.startswith("/") else None
        if not jelolt and self.cfg is not None:
            try:
                jelolt = str(self.cfg.path("sdk"))
            except Exception:                             # noqa: BLE001
                jelolt = None
        self._sdk = os.path.realpath(jelolt) if jelolt and os.path.isdir(jelolt) else None
        return self._sdk  # type: ignore[return-value]

    def gyorsitotar(self, p: KN.Profil) -> Path:
        alap = self.cfg.path("cache") if self.cfg is not None else Path(tempfile.gettempdir())
        d = Path(alap) / "kod" / p.azonosito
        d.mkdir(parents=True, exist_ok=True)
        return d

    def nyelv(self, p: KN.Profil) -> dict:
        """The toolchain state of a profile → `{azonosito, nev, elerheto, eszkozok: [...], sdk, hiba: {kod, param, uzenet}}`.
        The C++/C profiles (`motor = cpp`) report the portable LLVM (`modulok/cpp/eszkoztar.py`)."""
        ki = {**p.publikus(), "elerheto": False, "eszkozok": [], "sdk": None, "hiba": None}
        if p.motor == "cpp":
            from modulok.cpp.eszkoztar import Eszkoztar
            e = Eszkoztar(self.cfg)
            hiany = e.hianyzo()
            ki["eszkozok"] = [{"nev": "clang++" if p.azonosito == "cpp" else "clang", "ok": not hiany, "ut": str(e.llvm),
                               "forras": "runtime", "verzio": e.llvm_verzio()}]
            ki["sdk"] = str(e.sdk) if e.sdk_ok() else None
            if hiany:
                ki["hiba"] = _hiba("kod.nincs_eszkozlanc", f"No {p.nev} toolchain (missing: {', '.join(hiany)}). "
                                   f"{p.telepites_tipp}", nyelv=p.nev, hianyzo=", ".join(hiany), tipp=p.telepites_tipp)
            ki["elerheto"] = not hiany
            return ki
        hianyzo = []
        for e in p.eszkozok:
            d = self.eszkoz(e)
            ki["eszkozok"].append({k: v for k, v in d.items() if k != "hiba"})
            if not d["ok"]:
                hianyzo.append(e.nev)
        if p.sdk:
            ki["sdk"] = self.sdk()
            if ki["sdk"] is None:
                hianyzo.append("sdk")
        if hianyzo:
            ki["hiba"] = _hiba("kod.nincs_eszkozlanc", f"No {p.nev} toolchain (missing: {', '.join(hianyzo)}). "
                               f"{p.telepites_tipp}".strip(), nyelv=p.nev, hianyzo=", ".join(hianyzo), tipp=p.telepites_tipp)
        ki["elerheto"] = not hianyzo
        return ki
