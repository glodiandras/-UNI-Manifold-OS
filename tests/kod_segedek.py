"""F10 test helpers: a config wrapper with a `[kod]` override, and mock toolchains (shell scripts) for the languages whose
real toolchain is usually not on the test machine (Java, Go, Rust). The mocks run in the real sandbox: the compile profile
gets `/bin` as an extra exec/read root (`[kod] extra_exec`, `[kod.nyelv.<id>] extra_olvas`), the Java launcher's shell is
the run profile's `EXE_2` (`[kod.nyelv.java] ertelmezo`). A native "program" is a prebuilt echo program (`ECHO_C`, compiled once with the portable LLVM in the sandbox: a copied Apple
binary such as `/bin/cat` is killed by the system), so the native mocks need the LLVM (else the tests skip)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from core import kod_nyelvek as KN


class KodCfg:
    """A real `Config` with the `[kod]` section replaced by `KN.beallitasok(None)` + `kod`."""

    def __init__(self, cfg, kod: dict | None = None):
        self._c = cfg
        alap = KN.beallitasok(None)
        alap.update(kod or {})
        self._kod = alap

    def section(self, *kulcs):
        if kulcs == ("kod",):
            return self._kod
        return self._c.section(*kulcs)

    def __getattr__(self, nev):
        return getattr(self._c, nev)


ECHO_C = r"""#include <stdio.h>
#include <string.h>
int main(void) {
    char sor[4096];
    while (fgets(sor, sizeof sor, stdin)) {
        if (strstr(sor, "KIVETEL")) {
            fprintf(stderr, "panic: runtime error: index out of range [5] with length 3\n\ngoroutine 1 [running]:\n"
                            "main.main()\n\t/tmp/x/megoldas.go:7 +0x1c\n");
            fprintf(stderr, "thread 'main' panicked at megoldas.rs:4:13:\nindex out of bounds: the len is 3 but the index is 5\n");
            return 2;
        }
        fputs(sor, stdout);
    }
    return 0;
}
"""


def _szkript(ut: Path, szoveg: str, hej: str = "/bin/sh") -> Path:
    ut.parent.mkdir(parents=True, exist_ok=True)
    ut.write_text(f"#!{hej}\n" + szoveg, encoding="utf-8")
    ut.chmod(ut.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return ut


# a mock compiler fails when the source contains the word HIBA, and writes a diagnostic in the tool's own format
_GO = r'''case "$1" in version) echo "go version go1.99 mock"; exit 0;; esac
[ "$1" = build ] || exit 2
out="$3"; src="$4"
case "$(/bin/cat "$src")" in *HIBA*) echo "./megoldas.go:2:5: undefined: HIBA" >&2; exit 1;; esac
/bin/cp "@PROG@" "$out"
'''
_RUSTC = r'''case "$1" in --version) echo "rustc 1.99.0 (mock)"; exit 0;; esac
out=""; src=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; *.rs) src="$1";; esac; shift; done
case "$(/bin/cat "$src")" in *HIBA*) echo "megoldas.rs:2:5: error[E0425]: cannot find value \`HIBA\` in this scope" >&2; exit 1;; esac
/bin/cp "@PROG@" "$out"
'''
_CC = r'''echo "mock clang version 99"
'''
_JAVAC = r'''case "$1" in -version) echo "javac 21.0.99-mock"; exit 0;; esac
out=""; src=""
while [ $# -gt 0 ]; do case "$1" in -d) out="$2"; shift;; *.java) src="$1";; esac; shift; done
case "$(/bin/cat "$src")" in *HIBA*) printf 'Main.java:3: error: cannot find symbol\n        HIBA();\n        ^\n  symbol:   method HIBA()\n1 error\n' >&2; exit 1;; esac
/bin/cp "$src" "$out/Main.class"
'''
# the mock JVM: only shell built-ins (the run profile allows no other exec); echoes stdin, or throws on KIVETEL
_JAVA = r'''case "$1" in -version) echo "openjdk version 21.0.99-mock"; exit 0;; esac
cp=""
while [ $# -gt 0 ]; do case "$1" in -cp) cp="$2"; shift;; esac; shift; done
[ -f "$cp/Main.class" ] || { echo "Error: Could not find or load main class Main" >&2; exit 1; }
while IFS= read -r sor; do
  case "$sor" in *KIVETEL*) printf 'Exception in thread "main" java.lang.ArithmeticException: / by zero\n\tat Main.main(Main.java:4)\n' >&2; exit 1;; esac
  printf '%s\n' "$sor"
done
'''


def mock_eszkozlanc(gyoker: Path, prog: Path | None = None) -> dict:
    """Mock toolchains under `gyoker` → the `[kod]` override (tool paths, extra roots, the Java launcher's shell). `prog`:
    the prebuilt echo program the Go / Rust mocks "produce" (copied into each toolchain root, so the compile profile reads it)."""
    gyoker = Path(os.path.realpath(gyoker))
    go = _szkript(gyoker / "go" / "bin" / "go", _GO.replace("@PROG@", str(gyoker / "go" / "prog")))
    rustc = _szkript(gyoker / "rust" / "bin" / "rustc", _RUSTC.replace("@PROG@", str(gyoker / "rust" / "prog")))
    if prog is not None:
        import shutil
        for nyelv in ("go", "rust"):
            shutil.copy2(prog, gyoker / nyelv / "prog")
    cc = _szkript(gyoker / "cc" / "usr" / "bin" / "clang", _CC)
    javac = _szkript(gyoker / "jdk" / "bin" / "javac", _JAVAC)
    java = _szkript(gyoker / "jdk" / "bin" / "java", _JAVA, hej="/bin/bash")   # macOS /bin/sh re-execs bash
    sdk = gyoker / "sdk"
    sdk.mkdir(exist_ok=True)
    return {"eszkozok": {"go": str(go), "rustc": str(rustc), "cc": str(cc), "javac": str(javac), "java": str(java),
                         "sdk": str(sdk)},
            "extra_exec": ["/bin"],
            "nyelv": {"go": {"extra_olvas": ["/bin"]}, "rust": {"extra_olvas": ["/bin"]}, "java": {"extra_olvas": ["/bin"],
                                                                                                    "ertelmezo": "/bin/bash"}}}
