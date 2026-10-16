"""F10: compiler diagnostics and runtime error reports of the language profiles, bound to a source line. Pure functions on
the output text (the formats are the real tools'; the samples in `tests/test_kod_diagnosztika.py`).

The shapes are the C36a ones (`modulok/cpp/diagnosztika.py`), so the UI shows every language the same way:
- `fordito(parser, text, source_name)` → `{diagnosztika: [{szint, fajl, sor, oszlop, uzenet, kapcsolo, sajat, vegzetes,
  kodreszlet, reszletek}], hiba_db, figyelmeztetes_db, levagva}`;
- `jelentes(parser, stderr, source_name)` → `{forras, fajta, leiras, hozzaferes, fajl, sor, oszlop, fuggveny, sajat,
  keretek}` or None.

Parsers: `gcc` — `file:line[:col]: [severity[code]:] message` (clang, swiftc, rustc `--error-format=short`, `go build`, and
the engine's own Python / JavaScript / TypeScript checkers; a line without a severity is an error, as Go writes it);
`javac` — `File.java:line: error: message` + the caret line for the column. Runtime: `python` (traceback), `node` (the
`file:line` header or the stack), `java` (`Exception in thread "main" …` + `at Main.f(Main.java:5)`), `go` (`panic:` + the
goroutine frame), `rust` (`thread 'main' panicked at file:line:col:`), `swift` (`Fatal error: … file …, line N`).
"""
from __future__ import annotations

import os
import re

MAX_DB = 100
_GCC = re.compile(r"^(?P<fajl>(?:[A-Za-z]:)?[^:\n]+?):(?P<sor>\d+)(?::(?P<oszlop>\d+))?:\s+"
                  r"(?:(?P<szint>fatal error|error|warning|note|remark|help)(?:\[(?P<kod>[A-Za-z]*\d+)\])?:\s*)?(?P<uzenet>.*)$")
_JAVAC = re.compile(r"^(?P<fajl>[^:\n]+\.java):(?P<sor>\d+): (?P<szint>error|warning): (?P<uzenet>.*)$")
_JAVAC_KAPCSOLO = re.compile(r"^\[(?P<k>[\w-]+)\]\s*")


def _sajat(fajl: str | None, forras_nev) -> bool:
    """`forras_nev`: the sandbox name, or a tuple of names (TypeScript runs as the stripped `megoldas.js`)."""
    nevek = (forras_nev,) if isinstance(forras_nev, str) else tuple(forras_nev)
    return bool(fajl) and (fajl in nevek or os.path.basename(fajl) in nevek)


def _diag(szint: str, fajl, sor, oszlop, uzenet: str, kapcsolo, sajat: bool, vegzetes: bool = False) -> dict:
    return {"szint": szint, "fajl": fajl, "sor": sor, "oszlop": oszlop, "uzenet": uzenet, "kapcsolo": kapcsolo, "sajat": sajat,
            "vegzetes": vegzetes, "kodreszlet": [], "reszletek": []}


def _gcc(szoveg: str, forras_nev: str) -> list[dict]:
    ki: list[dict] = []
    for sor in szoveg.splitlines():
        m = _GCC.match(sor.rstrip())
        if not m or not m.group("uzenet").strip():
            if ki and sor.strip() and not sor.startswith(("warning: ", "error: ")):
                if len(ki[-1]["kodreszlet"]) < 6:
                    ki[-1]["kodreszlet"].append(sor.rstrip())
            continue
        fajl = m.group("fajl").strip()
        if fajl.startswith("./"):
            fajl = fajl[2:]
        if " " in fajl and not _sajat(fajl, forras_nev):       # prose with a colon, not a location
            continue
        szint = (m.group("szint") or "error").lower()
        vegzetes = szint == "fatal error"
        if vegzetes:
            szint = "error"
        if szint == "help":
            szint = "note"
        ki.append(_diag(szint, fajl, int(m.group("sor")), int(m.group("oszlop")) if m.group("oszlop") else None,
                        m.group("uzenet").strip(), m.group("kod"), _sajat(fajl, forras_nev), vegzetes))
    return ki


def _javac(szoveg: str, forras_nev: str) -> list[dict]:
    ki: list[dict] = []
    sorok = szoveg.splitlines()
    i = 0
    while i < len(sorok):
        m = _JAVAC.match(sorok[i].rstrip())
        if not m:
            i += 1
            continue
        uzenet = m.group("uzenet").strip()
        kapcsolo = None
        k = _JAVAC_KAPCSOLO.match(uzenet)
        if k:
            kapcsolo, uzenet = k.group("k"), uzenet[k.end():]
        d = _diag(m.group("szint"), m.group("fajl"), int(m.group("sor")), None, uzenet, kapcsolo,
                  _sajat(m.group("fajl"), forras_nev))
        j = i + 1
        while j < len(sorok) and not _JAVAC.match(sorok[j]) and not re.match(r"^\d+ (errors?|warnings?)$", sorok[j].strip()):
            if sorok[j].strip() == "^" or (sorok[j].strip().startswith("^") and set(sorok[j].strip()) <= {"^", "~"}):
                d["oszlop"] = len(sorok[j]) - len(sorok[j].lstrip()) + 1
            elif len(d["kodreszlet"]) < 6:
                d["kodreszlet"].append(sorok[j].rstrip())
            j += 1
        ki.append(d)
        i = j
    return ki


def fordito(parser: str, szoveg: str, forras_nev: str, max_db: int = MAX_DB) -> dict:
    lista = _javac(szoveg, forras_nev) if parser == "javac" else _gcc(szoveg, forras_nev)
    hiba_db = sum(d["szint"] == "error" for d in lista)
    figy_db = sum(d["szint"] == "warning" for d in lista)
    return {"diagnosztika": lista[:max_db], "hiba_db": hiba_db, "figyelmeztetes_db": figy_db, "levagva": len(lista) > max_db}


# ---------------------------------------------------------------------- runtime reports

def _ures(forras: str, fajta: str, leiras: str) -> dict:
    return {"forras": forras, "fajta": fajta, "leiras": leiras, "hozzaferes": None, "fajl": None, "sor": None, "oszlop": None,
            "fuggveny": None, "sajat": False, "keretek": []}


def _keret(j: dict, fajl: str, sor: int, oszlop: int | None, fv: str | None, forras_nev: str) -> None:
    sajat = _sajat(fajl, forras_nev)
    j["keretek"].append({"fajl": os.path.basename(fajl), "sor": sor, "oszlop": oszlop, "fuggveny": fv, "sajat_modul": sajat})
    if sajat and j["sor"] is None:
        j.update(fajl=os.path.basename(fajl), sor=sor, oszlop=oszlop, fuggveny=fv, sajat=True)


_PY_KERET = re.compile(r'^\s*File "(?P<fajl>[^"]+)", line (?P<sor>\d+)(?:, in (?P<fv>.+))?$')
_PY_HIBA = re.compile(r"^(?P<fajta>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning)|AssertionError|StopIteration)"
                      r"(?::\s*(?P<uzenet>.*))?$")


def _python(stderr: str, forras_nev: str) -> dict | None:
    if "Traceback (most recent call last)" not in stderr and not _PY_HIBA.search(stderr.strip().splitlines()[-1] if stderr.strip() else ""):
        return None
    sorok = stderr.rstrip().splitlines()
    utolso = next((s for s in reversed(sorok) if _PY_HIBA.match(s.strip())), None)
    if utolso is None:
        return None
    m = _PY_HIBA.match(utolso.strip())
    j = _ures("python", m.group("fajta"), (m.group("fajta") + (": " + m.group("uzenet") if m.group("uzenet") else "")))
    keretek = [(k.group("fajl"), int(k.group("sor")), k.group("fv")) for k in map(_PY_KERET.match, sorok) if k]
    for fajl, sor, fv in reversed(keretek):                    # the innermost own frame
        if _sajat(fajl, forras_nev):
            j.update(fajl=os.path.basename(fajl), sor=sor, fuggveny=None if fv == "<module>" else fv, sajat=True)
            break
    for fajl, sor, fv in keretek:
        j["keretek"].append({"fajl": os.path.basename(fajl), "sor": sor, "oszlop": None, "fuggveny": fv,
                             "sajat_modul": _sajat(fajl, forras_nev)})
    return j


_NODE_FEJ = re.compile(r"^(?:file://)?(?P<fajl>/[^:\n]+|[^:\s][^:\n]*):(?P<sor>\d+)$")
_NODE_HIBA = re.compile(r"^(?:Uncaught )?(?P<fajta>[A-Z]\w*(?:Error|Exception)|Error)(?: \[[A-Z_]+\])?: (?P<uzenet>.*)$")
_NODE_KERET = re.compile(r"^\s+at (?:(?P<fv>.+?) \()?(?:file://)?(?P<fajl>[^()\s]+?):(?P<sor>\d+):(?P<oszlop>\d+)\)?$")


def _node(stderr: str, forras_nev: str) -> dict | None:
    sorok = stderr.rstrip().splitlines()
    hiba = next((_NODE_HIBA.match(s.strip()) for s in sorok if _NODE_HIBA.match(s.strip())), None)
    if hiba is None:
        return None
    j = _ures("node", hiba.group("fajta"), f"{hiba.group('fajta')}: {hiba.group('uzenet')}")
    for s in sorok:
        k = _NODE_KERET.match(s)
        if k:
            _keret(j, k.group("fajl"), int(k.group("sor")), int(k.group("oszlop")), k.group("fv"), forras_nev)
    if j["sor"] is None and sorok:
        f = _NODE_FEJ.match(sorok[0].strip())
        if f and _sajat(f.group("fajl"), forras_nev):
            j.update(fajl=os.path.basename(f.group("fajl")), sor=int(f.group("sor")), sajat=True)
    return j


_JAVA_HIBA = re.compile(r'^Exception in thread "[^"]*" (?P<fajta>[\w.$]+)(?::\s*(?P<uzenet>.*))?$')
_JAVA_KERET = re.compile(r"^\s+at (?P<fv>[\w.$<>]+)\((?P<fajl>[\w$]+\.java):(?P<sor>\d+)\)$")


def _java(stderr: str, forras_nev: str) -> dict | None:
    sorok = stderr.rstrip().splitlines()
    m = next((_JAVA_HIBA.match(s.strip()) for s in sorok if _JAVA_HIBA.match(s.strip())), None)
    if m is None:
        return None
    fajta = m.group("fajta").rsplit(".", 1)[-1]
    j = _ures("java", fajta, fajta + (f": {m.group('uzenet')}" if m.group("uzenet") else ""))
    for s in sorok:
        k = _JAVA_KERET.match(s)
        if k:
            _keret(j, k.group("fajl"), int(k.group("sor")), None, k.group("fv"), forras_nev)
    return j


_GO_PANIC = re.compile(r"^panic: (?P<uzenet>.*)$")
_GO_KERET = re.compile(r"^\s+(?P<fajl>/?[^:\s]+\.go):(?P<sor>\d+)(?: \+0x[0-9a-f]+)?$")
_GO_FV = re.compile(r"^(?P<fv>[\w./*()]+)\(.*\)$")


def _go(stderr: str, forras_nev: str) -> dict | None:
    sorok = stderr.rstrip().splitlines()
    m = next((_GO_PANIC.match(s) for s in sorok if _GO_PANIC.match(s)), None)
    if m is None:
        return None
    uzenet = m.group("uzenet")
    j = _ures("go", "panic", uzenet)
    fv = None
    for s in sorok:
        f = _GO_FV.match(s.strip())
        k = _GO_KERET.match(s)
        if k:
            _keret(j, k.group("fajl"), int(k.group("sor")), None, fv, forras_nev)
        elif f:
            fv = f.group("fv")
    return j


_RUST_PANIC = re.compile(r"^thread '[^']*' panicked at (?P<fajl>[^:\n]+):(?P<sor>\d+):(?P<oszlop>\d+):$")
_RUST_PANIC_REGI = re.compile(r"^thread '[^']*' panicked at '(?P<uzenet>.*)', (?P<fajl>[^:\n]+):(?P<sor>\d+):(?P<oszlop>\d+)$")


def _rust(stderr: str, forras_nev: str) -> dict | None:
    sorok = stderr.rstrip().splitlines()
    for i, s in enumerate(sorok):
        m = _RUST_PANIC.match(s.strip())
        if m:
            uzenet = sorok[i + 1].strip() if i + 1 < len(sorok) else "panic"
            j = _ures("rust", "panic", uzenet)
            _keret(j, m.group("fajl"), int(m.group("sor")), int(m.group("oszlop")), None, forras_nev)
            return j
        m = _RUST_PANIC_REGI.match(s.strip())
        if m:
            j = _ures("rust", "panic", m.group("uzenet"))
            _keret(j, m.group("fajl"), int(m.group("sor")), int(m.group("oszlop")), None, forras_nev)
            return j
    return None


_SWIFT_HIBA = re.compile(r"^(?:(?P<fajl>[^:\n]+\.swift):(?P<sor>\d+): )?Fatal error: (?P<uzenet>.*?)(?:: file (?P<fajl2>[^,]+), "
                         r"line (?P<sor2>\d+))?$")


def _swift(stderr: str, forras_nev: str) -> dict | None:
    for s in stderr.splitlines():
        m = _SWIFT_HIBA.match(s.strip())
        if m:
            j = _ures("swift", "fatal_error", m.group("uzenet"))
            fajl, sor = m.group("fajl") or m.group("fajl2"), m.group("sor") or m.group("sor2")
            if fajl and sor:
                _keret(j, fajl, int(sor), None, None, forras_nev)
            return j
    return None


_JELENTES = {"python": _python, "node": _node, "java": _java, "go": _go, "rust": _rust, "swift": _swift}


def jelentes(parser: str | None, stderr: str, forras_nev) -> dict | None:
    f = _JELENTES.get(parser or "")
    if f is None or not stderr.strip():
        return None
    try:
        return f(stderr, forras_nev)
    except (ValueError, IndexError):
        return None


def nev_csere(obj, regi, uj: str, *, tisztit: list[str] | None = None):
    """The sandbox file name(s) → the displayed name in the `fajl` fields (recursively); the sandbox folders are hidden."""
    regiek = (regi,) if isinstance(regi, str) else tuple(regi)
    if isinstance(obj, dict):
        return {k: (uj if k == "fajl" and isinstance(v, str) and os.path.basename(v) in regiek
                    else nev_csere(v, regi, uj, tisztit=tisztit))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [nev_csere(x, regi, uj, tisztit=tisztit) for x in obj]
    if isinstance(obj, str) and tisztit:
        for t in tisztit:
            obj = obj.replace(t + "/", "").replace(t, "<run>")
        return obj
    return obj
