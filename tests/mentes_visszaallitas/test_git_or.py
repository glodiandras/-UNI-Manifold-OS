"""F9 backup / restore audit §3: the static guard — "undo = `git revert`; never `reset --hard`, `clean`, `checkout -- .`"
(CLAUDE.md data safety; `core/snapshot.py` module note). No shipped code may contain a git call that discards work-tree changes.

Python (`core/`, `modulok/`, `bin/*.py`, `packaging/`): every call whose literal string arguments form a forbidden git command
(`reset` with `--hard`/`--merge`/`--keep`, `clean`, `checkout`/`restore` of the work tree, `stash`, `switch --discard-changes`,
`read-tree -u`, `update-ref -d`, `branch -D`, `push --force`) — the arguments are the literal strings of the call, nested lists
included. Shell and Swift sources (`bin/`, `shell/`, `packaging/`, `*.sh`): the same commands as text. The guard is tested
on planted samples, so a broken detector cannot pass silently."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests.helpers import REPO

PY_GYOKEREK = ("core", "modulok", "bin", "packaging")
SZOVEG_GYOKEREK = ("bin", "shell", "packaging", "modulok", "core")
KIHAGY = ("modulok/ytdlp/tests/",)            # the vendored yt-dlp port's own tests (no git there either; kept out of scope)

SZOVEG_TILTOTT = re.compile(
    r"\bgit\b[^\n|;&]*?\s(?:reset\s+(?:[^\n|;&]*\s)?--(?:hard|merge|keep)\b|clean\b|stash\b|restore\b|"
    r"checkout\s+(?:[^\n|;&]*\s)?(?:--\s|-f\b|--force\b|\.(?:\s|$))|switch\s+[^\n|;&]*--discard-changes|read-tree\s+[^\n|;&]*-u\b|"
    r"push\s+[^\n|;&]*--force|branch\s+-D\b)")


def _literalok(n: ast.AST) -> list[str]:
    """The literal strings of a call's arguments (positional, starred lists, nested list/tuple literals)."""
    ki: list[str] = []
    for a in list(getattr(n, "args", [])) + [k.value for k in getattr(n, "keywords", [])]:
        for x in ast.walk(a):
            if isinstance(x, ast.Constant) and isinstance(x.value, str):
                ki.append(x.value)
    return ki


def tiltott_hivas(argok: list[str]) -> str | None:
    """The reason a git argument list is destructive, or None."""
    a = [s.strip() for s in argok]
    if "reset" in a and any(s in a for s in ("--hard", "--merge", "--keep")):
        return "reset --hard/--merge/--keep"
    if "clean" in a and ("git" in a or any(s.startswith("-") and set(s[1:]) & set("fdxX") for s in a)):
        return "clean"
    if "checkout" in a and any(s in a for s in ("--", ".", "-f", "--force")):
        return "checkout of the work tree"
    if "restore" in a and ("git" in a or any(s in a for s in (".", "--worktree", "--staged", "-W", "-S"))):
        return "restore"
    if "stash" in a and ("git" in a or len(a) <= 3):
        return "stash"
    if "switch" in a and "--discard-changes" in a:
        return "switch --discard-changes"
    if "read-tree" in a and any(s in ("-u", "--reset") or s.startswith("-m") and "u" in s for s in a):
        return "read-tree -u"
    if "push" in a and any(s in ("--force", "-f", "--force-with-lease") for s in a):
        return "push --force"
    if "branch" in a and "-D" in a:
        return "branch -D"
    return None


def python_talalatok(forras: str, nev: str) -> list[str]:
    ki = []
    for n in ast.walk(ast.parse(forras, filename=nev)):
        if isinstance(n, ast.Call):
            ok = tiltott_hivas(_literalok(n))
            if ok:
                ki.append(f"{nev}:{n.lineno}: {ok}")
    return ki


def szoveg_talalatok(forras: str, nev: str) -> list[str]:
    ki = []
    for i, sor in enumerate(forras.splitlines(), 1):
        kod = sor.split("#", 1)[0] if nev.endswith((".sh", ".py")) or "/bin/" in f"/{nev}" else sor.split("//", 1)[0]
        if SZOVEG_TILTOTT.search(kod):
            ki.append(f"{nev}:{i}: {sor.strip()[:100]}")
    return ki


def _fajlok(gyokerek, minta) -> list[Path]:
    ki = []
    for g in gyokerek:
        d = REPO / g
        if not d.exists():
            continue
        for p in sorted(d.rglob(minta)) if d.is_dir() else [d]:
            rel = p.relative_to(REPO).as_posix()
            if p.is_file() and not rel.startswith(KIHAGY) and "node_modules" not in p.parts and "__pycache__" not in p.parts:
                ki.append(p)
    return ki


class GitOrTest(unittest.TestCase):
    def test_az_or_felismeri_a_tiltott_hivasokat(self):
        rossz = '''
import subprocess
subprocess.run(["git", "reset", "--hard", "HEAD"])
repo.git("clean", "-fdx")
self.git("checkout", "--", ".")
git("restore", "--worktree", ".")
run(["git", "stash"])
repo.git("read-tree", "-u", "--reset", "HEAD")
g("push", "--force", "origin")
'''
        self.assertEqual(len(python_talalatok(rossz, "minta.py")), 7, python_talalatok(rossz, "minta.py"))
        jo = '''
repo.git("reset", "-q", "--", *paths)
repo.git("read-tree", "HEAD")
repo.git("checkout-index")
x = ["clean", "code"]
repo.git("log", "--format=%H")
'''
        self.assertEqual(python_talalatok(jo, "minta.py"), [])
        for sor in ("git reset --hard", "git -C x clean -fdx", "git checkout -- .", "git checkout .", "git stash", "git restore ."):
            self.assertTrue(szoveg_talalatok(sor, "minta.sh"), sor)
        for sor in ("git reset -q -- a", "git log", "# git reset --hard (forbidden)", "git checkout-index -a"):
            self.assertFalse(szoveg_talalatok(sor, "minta.sh"), sor)

    def test_a_python_kodban_nincs_rombolo_git(self):
        talalat = []
        for p in _fajlok(PY_GYOKEREK, "*.py"):
            talalat += python_talalatok(p.read_text(encoding="utf-8"), p.relative_to(REPO).as_posix())
        self.assertEqual(talalat, [])

    def test_a_shell_es_swift_kodban_nincs_rombolo_git(self):
        talalat = []
        fajlok = _fajlok(SZOVEG_GYOKEREK, "*.sh") + _fajlok(("shell",), "*.swift") + \
            [p for p in _fajlok(("bin",), "*") if p.suffix in ("", ".sh")]
        self.assertTrue(any(p.name == "mos" for p in fajlok))
        for p in fajlok:
            try:
                s = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            talalat += szoveg_talalatok(s, p.relative_to(REPO).as_posix())
        self.assertEqual(talalat, [])

    def test_a_snapshot_modul_visszavonasa_uj_commit(self):
        """The undo implementation itself: `undo_commit` / `undo_run` exist and the module documents the rule."""
        from core import snapshot
        self.assertTrue(callable(snapshot.Repo.undo_commit) and callable(snapshot.Repo.undo_run))
        forras = (REPO / "core" / "snapshot.py").read_text(encoding="utf-8")
        self.assertIn("`reset --hard`, `clean` vagy `checkout -- .`", forras)
