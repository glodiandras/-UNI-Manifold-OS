"""F10: the language profiles of the code workbench — **the single place of the schema** (like `core/cpp_teszt.py` for the
test block). The core (`core/kod_utvonal.py`: note ↔ source pairing, language detection) and the engine (`modulok/kod`:
toolchain discovery, sandboxed compile/run/test, AI modes) both read it. Pure data: nothing here runs or touches the disk.

A profile (`Profil`) says, for one language:

- `azonosito`, `nev` (English display name), `kiterjesztesek` (the first is the canonical one), `forras_nev` (the file name
  the source gets inside the sandbox work folder; Java needs `Main.java`);
- `motor`: `cpp` (the C36a engine in `modulok/cpp`, unchanged — C++ and C) or `nyelv` (the generic engine, `modulok/kod`);
- `nativ`: the compile step produces a native binary that runs under the C36a run profile (`profil_futtat.sb`, exec of the
  binary only); otherwise the run is an interpreter/VM under the language run profile (`modulok/kod/kod_futtat.sb`);
- `eszkozok`: the toolchain (`Eszkoz`): how it is discovered — config override (`[kod.eszkozok] <kulcs>`), an `[utak]` key
  of the embedded runtime, then the system PATH; `verzio` is the probe argv (a stub such as macOS `/usr/bin/java` without a
  JDK fails it, so it is not "found"); `xcrun`: on macOS the PATH entry may be an `xcrun` shim, the real path is asked;
- `fordit` / `futtat`: argv templates. Tokens: `{forras}` (the source in the work folder), `{prog}` (the native output),
  `{munka}` (the work folder), `{kimenet}` (the build output folder), `{eszkoz:<nev>}`, `{sdk}`, `{segedek}` (the engine's
  helper scripts), `{gyorsitotar}` (the language's writable compiler cache), `{memoria_mb}`;
- `kornyezet`: environment templates for the compile step (same tokens);
- `diagnosztika`: the compiler-output parser (`gcc`: `file:line:col: severity: message`, `javac`), `jelentes`: the runtime
  error parser (`python`, `node`, `java`, `go`, `rust`, `swift`) — both bind messages to a source line;
- `kalibracios_kulcs`: the router task of the five AI modes for this language (D9: each language is calibrated on its own;
  C++ keeps the measured `kod` task); `ai_nyelv` names the language in the prompt, `kerites` the accepted code-fence tags;
- `eszkozlanc`: `beagyazott` (shipped with the runtime/LLVM) or `rendszer` (a system or user-installed toolchain);
  `telepites_tipp`: English hint shown when it is missing. Nothing is downloaded at runtime (D3).

The test block (`teszt`) is the C36a format (`core/cpp_teszt.py`): stdin → expected stdout, language-independent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

MODOK = ("gyors", "hibakereso")
AI_MODOK = ("hiba", "tipp", "megoldas", "teszt", "stressz")


@dataclass(frozen=True)
class Eszkoz:
    nev: str                                   # the template name (`{eszkoz:<nev>}`) and the `[kod.eszkozok]` key
    path_nevek: tuple[str, ...] = ()           # names looked up on PATH (in order)
    utak_kulcs: str | None = None              # an `[utak]` key of the embedded runtime (e.g. `node`)
    runtime_ut: str | None = None              # a path under `{runtime}` (e.g. `python/bin/python3`)
    sajat_python: bool = False                 # the engine's own interpreter is an acceptable fallback (embedded Python)
    verzio: tuple[str, ...] = ("--version",)   # the probe argv; exit 0 = usable
    gyoker_szint: int = 2                      # the toolchain root = this many parents above the real executable
    xcrun: bool = False                        # macOS: resolve through `xcrun --find <name>` when the PATH entry is a shim


@dataclass(frozen=True)
class Profil:
    azonosito: str
    nev: str
    kiterjesztesek: tuple[str, ...]
    forras_nev: str
    motor: str                                  # cpp | nyelv
    nativ: bool
    eszkozok: tuple[Eszkoz, ...] = ()
    fordit: tuple[str, ...] | None = None
    futtat: tuple[str, ...] = ()
    kornyezet: dict = field(default_factory=dict)
    diagnosztika: str = "gcc"
    jelentes: str | None = None
    kalibracios_kulcs: str = "kod"
    ai_nyelv: str = ""
    kerites: tuple[str, ...] = ()
    eszkozlanc: str = "beagyazott"              # beagyazott | rendszer
    sdk: bool = False                           # the compile step needs the macOS SDK path (`{sdk}`)
    telepites_tipp: str = ""
    fordit_idokorlat_s: float | None = None     # None: the `[kod] fordit_idokorlat_s`

    def publikus(self) -> dict:
        return {"azonosito": self.azonosito, "nev": self.nev, "kiterjesztesek": list(self.kiterjesztesek),
                "motor": self.motor, "nativ": self.nativ, "eszkozlanc": self.eszkozlanc,
                "kalibracios_kulcs": self.kalibracios_kulcs, "ai_modok": list(AI_MODOK),
                "modok": list(MODOK) if self.motor == "cpp" else ["gyors"], "telepites_tipp": self.telepites_tipp}


_CLANG_DIAG = "gcc"

PROFILOK: tuple[Profil, ...] = (
    Profil("cpp", "C++", (".cpp", ".cc", ".cxx"), "megoldas.cpp", "cpp", True, kalibracios_kulcs="kod", ai_nyelv="C++17",
           kerites=("cpp", "c++", "cc", "cxx"), telepites_tipp="Install the portable LLVM: bin/mos cpp telepit --igen"),
    Profil("c", "C", (".c",), "megoldas.cpp", "cpp", True, kalibracios_kulcs="kod_c", ai_nyelv="C17",
           kerites=("c",), telepites_tipp="Install the portable LLVM: bin/mos cpp telepit --igen"),
    Profil("python", "Python", (".py",), "megoldas.py", "nyelv", False,
           eszkozok=(Eszkoz("python", ("python3",), runtime_ut="python/bin/python3", sajat_python=True, gyoker_szint=2),),
           fordit=("{eszkoz:python}", "-I", "-S", "-B", "{segedek}/py_ellenoriz.py", "{forras}"),
           futtat=("{eszkoz:python}", "-I", "-S", "-B", "{forras}"),
           diagnosztika="gcc", jelentes="python", kalibracios_kulcs="kod_python", ai_nyelv="Python 3",
           kerites=("python", "py", "python3")),
    Profil("javascript", "JavaScript", (".js", ".mjs", ".cjs"), "megoldas.js", "nyelv", False,
           eszkozok=(Eszkoz("node", ("node",), utak_kulcs="node", runtime_ut="node/bin/node", gyoker_szint=2),),
           fordit=("{eszkoz:node}", "{segedek}/js_fordit.js", "{forras}"),
           futtat=("{eszkoz:node}", "--max-old-space-size={memoria_mb}", "--disallow-code-generation-from-strings", "{forras}"),
           diagnosztika="gcc", jelentes="node", kalibracios_kulcs="kod_javascript", ai_nyelv="JavaScript (Node.js)",
           kerites=("javascript", "js", "node")),
    Profil("typescript", "TypeScript", (".ts", ".cts"), "megoldas.ts", "nyelv", False,
           eszkozok=(Eszkoz("node", ("node",), utak_kulcs="node", runtime_ut="node/bin/node", gyoker_szint=2),),
           fordit=("{eszkoz:node}", "{segedek}/js_fordit.js", "{forras}", "{munka}/megoldas.js"),
           futtat=("{eszkoz:node}", "--max-old-space-size={memoria_mb}", "--disallow-code-generation-from-strings",
                   "{munka}/megoldas.js"),
           diagnosztika="gcc", jelentes="node", kalibracios_kulcs="kod_typescript", ai_nyelv="TypeScript (Node.js)",
           kerites=("typescript", "ts")),
    Profil("java", "Java", (".java",), "Main.java", "nyelv", False,
           eszkozok=(Eszkoz("javac", ("javac",), verzio=("-version",), gyoker_szint=2),
                     Eszkoz("java", ("java",), verzio=("-version",), gyoker_szint=2)),
           fordit=("{eszkoz:javac}", "-J-XX:-UsePerfData", "-J-Xshare:off", "-encoding", "UTF-8", "-Xlint:all",
                   "-d", "{kimenet}", "{forras}"),
           futtat=("{eszkoz:java}", "-XX:-UsePerfData", "-Xshare:off", "-Xss64m", "-Xmx{memoria_mb}m", "-XX:+UseSerialGC",
                   "-cp", "{kimenet}", "Main"),
           diagnosztika="javac", jelentes="java", kalibracios_kulcs="kod_java", ai_nyelv="Java 17 (public class Main)",
           kerites=("java",), eszkozlanc="rendszer", fordit_idokorlat_s=60.0,
           telepites_tipp="Install a JDK (17 or newer) and set its path in Settings, or put javac/java on PATH."),
    Profil("go", "Go", (".go",), "megoldas.go", "nyelv", True,
           eszkozok=(Eszkoz("go", ("go",), verzio=("version",), gyoker_szint=2),),
           fordit=("{eszkoz:go}", "build", "-o", "{prog}", "{forras}"),
           kornyezet={"GOCACHE": "{gyorsitotar}", "GOPATH": "{munka}/.gopath", "GOTOOLCHAIN": "local", "GOPROXY": "off",
                      "GOFLAGS": "-mod=mod", "GOENV": "off", "GOTELEMETRY": "off", "CGO_ENABLED": "0", "GO111MODULE": "off"},
           diagnosztika="gcc", jelentes="go", kalibracios_kulcs="kod_go", ai_nyelv="Go", kerites=("go", "golang"),
           eszkozlanc="rendszer", fordit_idokorlat_s=90.0,
           telepites_tipp="Install Go and set its path in Settings, or put go on PATH."),
    Profil("rust", "Rust", (".rs",), "megoldas.rs", "nyelv", True,
           eszkozok=(Eszkoz("rustc", ("rustc",), verzio=("--version",), gyoker_szint=2),
                     Eszkoz("cc", ("clang",), verzio=("--version",), gyoker_szint=3, xcrun=True)),
           fordit=("{eszkoz:rustc}", "--edition", "2021", "-O", "--error-format=short", "-C", "linker={eszkoz:cc}",
                   "-o", "{prog}", "{forras}"),
           kornyezet={"SDKROOT": "{sdk}"},
           diagnosztika="gcc", jelentes="rust", kalibracios_kulcs="kod_rust", ai_nyelv="Rust (edition 2021)",
           kerites=("rust", "rs"), eszkozlanc="rendszer", sdk=True, fordit_idokorlat_s=90.0,
           telepites_tipp="Install Rust (rustc) and the Xcode Command Line Tools, then set the paths in Settings."),
    Profil("swift", "Swift", (".swift",), "megoldas.swift", "nyelv", True,
           eszkozok=(Eszkoz("swiftc", ("swiftc",), verzio=("--version",), gyoker_szint=3, xcrun=True),),
           fordit=("{eszkoz:swiftc}", "-sdk", "{sdk}", "-module-cache-path", "{gyorsitotar}", "-o", "{prog}", "{forras}"),
           diagnosztika="gcc", jelentes="swift", kalibracios_kulcs="kod_swift", ai_nyelv="Swift 5",
           kerites=("swift",), eszkozlanc="rendszer", sdk=True, fordit_idokorlat_s=120.0,
           telepites_tipp="Install the Xcode Command Line Tools (xcode-select --install) or a Swift toolchain."),
)


def profil(azonosito: str) -> Profil | None:
    return next((p for p in PROFILOK if p.azonosito == azonosito), None)


# The starter source of a new task (neutral, English comments; it reads nothing and solves nothing, so the example test of the
# task note fails until the user writes the solution). `cpp` is the C36a starter (`core/cpp_teszt.cpp_vaz`).
_FORRAS_VAZ = {
    "c": "#include <stdio.h>\n\nint main(void) {\n    /* Read from stdin, write to stdout. */\n    return 0;\n}\n",
    "python": "import sys\n\n\ndef main():\n    # Read from stdin, write to stdout.\n    data = sys.stdin.read().split()\n\n\nmain()\n",
    "javascript": "// Read from stdin, write to stdout.\nconst fs = require(\"fs\");\nconst tokens = fs.readFileSync(0, \"utf8\").split(/\\s+/).filter(Boolean);\n",
    "typescript": "// Read from stdin, write to stdout.\nconst fs = require(\"fs\");\nconst tokens: string[] = fs.readFileSync(0, \"utf8\").split(/\\s+/).filter(Boolean);\n",
    "java": "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        // Read from stdin, write to stdout.\n        Scanner in = new Scanner(System.in);\n    }\n}\n",
    "go": "package main\n\nfunc main() {\n\t// Read from stdin, write to stdout.\n}\n",
    "rust": "use std::io::{self, Read};\n\nfn main() {\n    // Read from stdin, write to stdout.\n    let mut input = String::new();\n    io::stdin().read_to_string(&mut input).unwrap();\n}\n",
    "swift": "// Read from stdin with readLine(), write to stdout with print().\nimport Foundation\n",
}


def forras_vaz(azonosito: str) -> str | None:
    """The starter source of a new task in this language (None: unknown language)."""
    if azonosito == "cpp":
        from . import cpp_teszt                       # lazy: cpp_teszt needs this module for the note skeleton
        return cpp_teszt.cpp_vaz()
    return _FORRAS_VAZ.get(azonosito)


def azonositok() -> list[str]:
    return [p.azonosito for p in PROFILOK]


def kiterjesztesek() -> tuple[str, ...]:
    return tuple(k for p in PROFILOK for k in p.kiterjesztesek)


def nyelv_ut(ut: str) -> Profil | None:
    """The profile of a source path by its extension (case-insensitive); not a source → None."""
    kis = (ut or "").lower()
    return next((p for p in PROFILOK if kis.endswith(p.kiterjesztesek)), None)


_BEAGYAZOTT = re.compile(r"!\[\[([^\]|#\n]+?(" + "|".join(re.escape(k) for k in sorted(kiterjesztesek(), key=len, reverse=True))
                         + r"))(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]", re.I)


def beagyazott_forrasok(szoveg: str) -> list[str]:
    """The embedded source files of a task note (`![[name.<ext>]]` of any profile), in order, without duplicates.
    For `.cpp` this agrees with `core.cpp_teszt.beagyazott_cpp`."""
    ki: list[str] = []
    for m in _BEAGYAZOTT.finditer(szoveg or ""):
        nev = m.group(1).strip()
        if nev and nev not in ki:
            ki.append(nev)
    return ki


def beallitasok(cfg) -> dict:
    """The `[kod]` section with defaults (cfg None: the defaults)."""
    b = {"fordit_idokorlat_s": 60.0, "fordit_memoria_mb": 4096, "fordit_munka_max_mb": 512, "fordit_munka_max_fajl": 4096,
         "teszt_idokorlat_s": 2.0, "teszt_idokorlat_max_s": 10.0, "memoria_mb": 256, "teszt_memoria_max_mb": 1024,
         "ertelmezo_memoria_mb": 512, "lebego_eps": 1e-6, "kimenet_max_kb": 1024, "stderr_max_kb": 64, "munka_max_mb": 16,
         "munka_max_fajl": 256, "mintavetel_ms": 20, "felderites_idokorlat_s": 15.0, "proba_modell": "",
         "extra_exec": [], "eszkozok": {}, "nyelv": {}}
    if cfg is not None:
        for k, v in (cfg.section("kod") or {}).items():
            b[k] = v
    return b


def nyelv_beallitas(b: dict, azonosito: str) -> dict:
    """The per-language overrides (`[kod.nyelv.<id>]`): `extra_olvas`, `extra_exec` (extra read / exec roots of the
    compile profile; the global `[kod] extra_exec` is added), `ertelmezo` (an extra exec literal of the run profile: the
    interpreter of a launcher script — a toolchain whose `java` is a shell script)."""
    n = (b.get("nyelv") or {}).get(azonosito) or {}
    return {"extra_olvas": [str(x) for x in n.get("extra_olvas") or []],
            "extra_exec": [str(x) for x in [*(b.get("extra_exec") or []), *(n.get("extra_exec") or [])]],
            "ertelmezo": str(n.get("ertelmezo") or "")}


def felulir(p: Profil, **mezok) -> Profil:
    return replace(p, **mezok)
