"""A hordozható C++ eszközlánc (C36a): az LLVM és az SDK útjai, a beállítások, a fordítási parancs és az állapot.

Semmi nem a rendszer fordítójára esik vissza: a `clang++` az `{llvm}/bin/`-ből jön, a sysroot az `{sdk}` (a macOS SDK
egyszeri másolata), a szabványkönyvtár fejlécei az SDK-ból (a rendszer libc++-dylibjével egyeznek), a `bits/stdc++.h`
a `pot/` mappából. A parancsépítés **tiszta függvény** (nincs hálózat, nincs fájlrendszer): a teszt a parancsot nézi.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from core.doctor import macos_verzio, sdk_regebbi  # noqa: F401 — a doctor és a motor közös verzió-függvényei

ITT = Path(__file__).resolve().parent
POT = ITT / "pot"

ALAP: dict = {
    "std": "c++17",
    "gyors": ["-O2", "-Wall", "-Wextra"],
    "hibakereso": ["-O1", "-g", "-fno-omit-frame-pointer", "-fsanitize=address,undefined",
                   "-fno-sanitize-recover=all", "-Wall", "-Wextra"],
    "linker": "lld",
    "fordit_idokorlat_s": 30.0,
    "fordit_memoria_mb": 2048,
    "fordit_munka_max_mb": 256,
    "fordit_munka_max_fajl": 1024,
    "teszt_idokorlat_s": 2.0,
    "teszt_idokorlat_max_s": 10.0,
    "hibakereso_idoszorzo": 3.0,
    "memoria_mb": 256,
    "teszt_memoria_max_mb": 1024,
    "lebego_eps": 1e-6,
    "hibakereso_memoria_mb": 1024,
    "kimenet_max_kb": 1024,
    "stderr_max_kb": 64,
    "munka_max_mb": 16,
    "munka_max_fajl": 256,
    "mintavetel_ms": 20,
    "formazas": "{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: 100, AllowShortFunctionsOnASingleLine: Inline}",
    "sablon": "C++ feladat",
}
MODOK = ("gyors", "hibakereso")
LINKER = "lld"                       # az egyetlen támogatott linker (K168: a „rendszer” a fordító-profil alatt halott ág volt)
CONSTEXPR_LEPES = 5_000_000          # a clang alapja 1 048 576; a feladatoknak ennél több ritkán kell, a végtelen nem fér bele
SABLON_MELYSEG = 512
_SANITIZER_KORNYEZET = {
    "ASAN_OPTIONS": "symbolize=0:detect_leaks=0:abort_on_error=0:halt_on_error=1",
    "UBSAN_OPTIONS": "print_stacktrace=0:halt_on_error=1",
}


def beallitas(cfg) -> dict:
    """Az alapértékek + a `[cpp]` szakasz (cfg nélkül: az alapértékek)."""
    b = {k: (list(v) if isinstance(v, list) else v) for k, v in ALAP.items()}
    if cfg is not None:
        b.update(cfg.section("cpp"))
    return b


def linker_figyelmeztetes(b: dict) -> str | None:
    """A `[cpp] linker` beállítás ellenőrzése (K168). Egyetlen érték él: `lld` (az LLVM saját `ld64.lld`-je). A régi `rendszer`
    (a `/usr/bin/ld`) a fordító-profil alatt nem futhat (az exec csak az LLVM `bin/`-jéből engedett: `posix_spawn failed`),
    ezért kikerült: bármi más érték figyelmen kívül marad, és ez az üzenet jelzi. Rendben lévő beállításnál `None`."""
    ertek = b.get("linker", LINKER)
    if ertek == LINKER:
        return None
    return (f"a [cpp] linker = {ertek!r} beállítás nem támogatott: csak a {LINKER!r} (az LLVM ld64.lld-je) él, a \"rendszer\" "
            f"linker a fordító-profil alatt nem futhat (K168); a beállítás figyelmen kívül marad, a config/os.toml-ban javítandó")


def fordit_parancs(llvm: Path, sdk: Path, pot: Path, b: dict, forras: str, kimenet: str, mod: str) -> list[str]:
    """A `clang++` parancssora. A fordító az `{llvm}/bin/`-ből, a fejlécek az SDK-ból és a pótfejlécből; az utak abszolútak,
    a PATH-ra és a rendszer fordítójára semmi nem támaszkodik. A linker mindig az LLVM `ld64.lld`-je (`-fuse-ld=lld`; K168).
    Minden elem egy argumentum (szóköz is lehet benne)."""
    if mod not in MODOK:
        raise ValueError(f"ismeretlen mód: {mod!r} (gyors | hibakereso)")
    p = [str(Path(llvm) / "bin" / "clang++"), f"-std={b['std']}", *b[mod],
         "-fno-color-diagnostics", f"-fconstexpr-steps={CONSTEXPR_LEPES}", f"-ftemplate-depth={SABLON_MELYSEG}",
         "-isysroot", str(sdk), "-nostdinc++", "-isystem", f"{sdk}/usr/include/c++/v1", "-isystem", str(pot)]
    p.append("-fuse-ld=lld")
    return p + [forras, "-o", kimenet]


def futtat_kornyezet(b: dict, mod: str) -> dict[str, str]:
    """A lefordított program környezete: üres (PATH, HOME, bármi nincs); hibakereső módban csak a sanitizer-beállítások."""
    return dict(_SANITIZER_KORNYEZET) if mod == "hibakereso" else {}


def fordit_kornyezet(munka: Path, sdk: Path) -> dict[str, str]:
    """A fordító környezete: a saját ideiglenes mappája és az SDK; PATH és HOME nincs."""
    return {"TMPDIR": str(munka), "SDKROOT": str(sdk)}


def _futtathato(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


class Eszkoztar:
    """Az LLVM (`{llvm}`) és az SDK (`{sdk}`) a konfigurációból (`[utak] llvm, sdk`; `MOS_LLVM`, `MOS_SDK`)."""

    def __init__(self, cfg=None, *, llvm: Path | str | None = None, sdk: Path | str | None = None):
        self.cfg = cfg
        self.b = beallitas(cfg)
        self.llvm = Path(llvm) if llvm else (cfg.path("llvm") if cfg is not None else None)
        self.sdk = Path(sdk) if sdk else (cfg.path("sdk") if cfg is not None else None)
        if self.llvm is None or self.sdk is None:
            raise ValueError("az eszköztárhoz konfiguráció vagy kifejezett llvm és sdk út kell")
        self.pot = POT
        self._llvm_verzio: str | None = None

    # ------------------------------------------------------------------ utak

    def bin(self, nev: str) -> Path:
        return self.llvm / "bin" / nev

    @property
    def clangxx(self) -> Path:
        return self.bin("clang++")

    @property
    def clang_format(self) -> Path:
        return self.bin("clang-format")

    @property
    def clangd(self) -> Path:
        return self.bin("clangd")

    def van_lld(self) -> bool:
        return _futtathato(self.bin("ld64.lld"))

    def linker(self) -> str:
        """A használt linker: mindig `lld` (K168; az `ld64.lld` hiányát a `hianyzo()` jelzi, nincs tartalék linker)."""
        return LINKER

    def linker_figyelmeztetes(self) -> str | None:
        """A `[cpp] linker` beállítás figyelmeztetése (a régi `rendszer` vagy ismeretlen érték), különben `None`."""
        return linker_figyelmeztetes(self.b)

    def san_lib(self) -> Path | None:
        """Az LLVM sanitizer-futtatókörnyezetének mappája (`lib/clang/<verzió>/lib/darwin`), ha megvan."""
        talalat = sorted((self.llvm / "lib" / "clang").glob("*/lib/darwin"))
        return talalat[-1] if talalat else None

    # ------------------------------------------------------------------ állapot

    def sdk_ok(self) -> bool:
        return (self.sdk / "SDKSettings.json").is_file() and (self.sdk / "usr" / "include").is_dir()

    def sdk_tbd_igazitva(self) -> bool:
        """Az SDK-másolat `libSystem.tbd`-je nem tartalmaz az `ld64.lld` számára ismeretlen `arm64e.x1` célt (a `telepit --sdk`
        / `--tbd-igazit` igazítja). Hiányzó fájlnál igaz (az SDK hiányát a `hianyzo()` jelzi)."""
        try:
            return "arm64e.x1-" not in (self.sdk / "usr" / "lib" / "libSystem.tbd").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return True

    def hianyzo(self) -> list[str]:
        """A kötelező elemek közül, ami hiányzik (a linker is kötelező: tartaléka nincs, K168)."""
        h = []
        if not _futtathato(self.clangxx):
            h.append("clang++")
        if not self.van_lld():
            h.append("ld64.lld")
        if not _futtathato(self.clang_format):
            h.append("clang-format")
        if not self.sdk_ok():
            h.append("sdk")
        return h

    def kesz(self) -> bool:
        return not self.hianyzo()

    def sdk_verzio(self) -> str | None:
        try:
            v = json.loads((self.sdk / "SDKSettings.json").read_text(encoding="utf-8")).get("Version")
        except (OSError, ValueError, AttributeError):
            return None
        return v if isinstance(v, str) else None

    def llvm_verzio(self) -> str | None:
        """A `clang++ --version` verziószáma (egyszeri hívás, gyorsítótárazva)."""
        if self._llvm_verzio is None and _futtathato(self.clangxx):
            try:
                ki = subprocess.run([str(self.clangxx), "--version"], capture_output=True, text=True, timeout=20, env={})
                m = re.search(r"clang version (\S+)", ki.stdout)
                self._llvm_verzio = m.group(1) if m else ""
            except (OSError, subprocess.TimeoutExpired):
                self._llvm_verzio = ""
        return self._llvm_verzio or None

    def allapot(self) -> dict:
        sdk_v, os_v = self.sdk_verzio(), macos_verzio()
        return {"kesz": self.kesz(), "hianyzo": self.hianyzo(), "llvm": str(self.llvm), "llvm_verzio": self.llvm_verzio(),
                "sdk": str(self.sdk), "sdk_verzio": sdk_v, "macos_verzio": os_v, "sdk_regi": sdk_regebbi(sdk_v, os_v),
                "sdk_tbd_igazitva": self.sdk_tbd_igazitva(),
                "linker": self.linker(), "linker_figyelmeztetes": self.linker_figyelmeztetes(), "clangd": _futtathato(self.clangd), "clang_format": _futtathato(self.clang_format),
                "llvm_symbolizer": _futtathato(self.bin("llvm-symbolizer")), "std": self.b["std"]}

    # ------------------------------------------------------------------ formázás

    def formaz(self, szoveg: str, idokorlat_s: float = 20.0, homokozo=None) -> tuple[bool, str]:
        """A `clang-format` a `[cpp] formazas` inline stílussal, **a fordító-profil alatt** (a program-homokozó `fordit`
        útja: olvasni az LLVM-et és a `munka/`-t, írni csak a `munka/`-ba; idő-, memória-, kimenet- és lemezkorlát;
        Audit 3 A3-23). A szöveg egy ideiglenes `munka/forras.cpp`-be kerül, a kimenet a stdout; üres környezet, így a
        vaultból vagy a home-ból `.clang-format` nem olvasódik. Hiányzó `sandbox-exec` mellett zárva hibázik.
        → (sikerült, a formázott szöveg vagy a hibaüzenet)."""
        if not _futtathato(self.clang_format):
            return False, "nincs clang-format (bin/mos cpp telepit --igen)"
        if homokozo is None:
            from modulok.homokozo.program import Programhomokozo
            homokozo = Programhomokozo(self.cfg)
        bajt = szoveg.encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="mos-fmt-") as d:
            munka = Path(os.path.realpath(d)) / "munka"
            munka.mkdir()
            forras = munka / "forras.cpp"
            forras.write_bytes(bajt)
            r = homokozo.fordit([str(self.clang_format), f"-style={self.b['formazas']}", "-fallback-style=none",
                                 str(forras)], munka=munka, llvm=self.llvm, sdk=self.sdk, pot=self.pot, kornyezet={},
                                idokorlat_s=idokorlat_s, memoria_mb=float(self.b["fordit_memoria_mb"]),
                                kimenet_max_kb=4 * len(bajt) // 1024 + 1024,
                                munka_max_mb=2 * len(bajt) / 2 ** 20 + 16, munka_max_fajl=64)
        if r["allapot"] == "ok":
            return True, r["stdout"]
        if r["allapot"] == "hiba":
            return False, r["stderr"].strip() or f"a clang-format {r['kilepes']} kóddal állt le"
        if r["allapot"] == "idotullepes":
            return False, "a clang-format túllépte az időkorlátot"
        return False, f"a clang-format nem futott le ({r['allapot']}): {r['uzenet']}"

    # ------------------------------------------------------------------ parancsok

    def parancs(self, forras: str, kimenet: str, mod: str = "gyors") -> list[str]:
        return fordit_parancs(self.llvm, self.sdk, self.pot, self.b, forras, kimenet, mod)
