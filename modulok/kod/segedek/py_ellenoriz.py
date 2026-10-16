"""F10: the Python "compile" step — a syntax check in the compile sandbox (`python -I -S -B py_ellenoriz.py <source>`).
Nothing of the checked program runs: `compile()` only parses. Errors are written gcc-style (`file:line:col: error: msg`), the
form the engine's diagnostics parser binds to a source line. Exit code: 0 ok, 1 syntax error, 2 unreadable source."""
import os
import sys


def main(ut: str) -> int:
    nev = os.path.basename(ut)
    try:
        with open(ut, "rb") as f:
            forras = f.read()
    except OSError as exc:
        print(f"{nev}:1:1: error: the source is not readable: {exc}", file=sys.stderr)
        return 2
    try:
        compile(forras, nev, "exec", dont_inherit=True)
    except SyntaxError as exc:
        sor, oszlop = exc.lineno or 1, exc.offset or 1
        print(f"{nev}:{sor}:{oszlop}: error: {type(exc).__name__}: {exc.msg}", file=sys.stderr)
        if exc.text:
            print("    " + exc.text.rstrip("\n"), file=sys.stderr)
        return 1
    except ValueError as exc:                     # e.g. a NUL byte in the source
        print(f"{nev}:1:1: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
