"""Pillanatképek és visszavonás külső git-könyvtárral — a legacy `snapshot` viselkedésre azonos portja
(LEGACY-SZERZODESEK L01–L18). A git-beállítások, a trailerek és a visszavonás bájtra ugyanazok.

A munkafába (vault, ytdlp) NEM kerül `.git`: a tároló a 2.0 `var/`
alatt él, és `core.worktree`-vel mutat a munkafára. A vaultban így nem jelenik
meg idegen fájl (I33), a `vaultlib.SKIP_DIRS`-nek sem kell tudnia róla.

Csak szöveg kerül be (md, canvas, json, vtt, py) — a bináris média kizárva,
annak mozgatását a move-napló követi.

A visszavonás MINDIG új commit (útvonalanként visszafelé alkalmazott diff, atomikusan),
tehát maga is visszavonható, és a történet soha nem íródik át. A modul szándékosan nem
ismer `reset --hard`, `clean` vagy `checkout -- .` műveletet: ezek a vaulton adatvesztéssel
járnának. A gépi commit CSAK a megadott utakat veszi fel (`commit_machine`); a gazda
kézi változásai előtte külön commitba kerülnek. A kivétellista (`kivetelek`) a korábbi,
kevert commitok gazdai útjait védi a visszavonástól.

Egy commit egy tétel. A trailerek kötik a futáshoz:
    Mos-Kor: <kör azonosító>
    Mos-Tetel: <tétel azonosító>
    Mos-Dontes: <döntés> / Mos-Bizalom: <szám>
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import mediatipus, osszeomlas, tartos

TRAILER_RUN = "Mos-Kor"
TRAILER_ITEM = "Mos-Tetel"
TRAILER_TASK = "Mos-Feladat"     # C17: a gépi commitot író feladat azonosítója (a feladatsor `MOS_FELADAT` env-je)
TRAILER_DISK = "Mos-Lemezen"     # C10: a commit által eltűnt fájlok lemezen álló (NFD/kisbetűs) nevei, JSON-lista
AUTHOR = ("Manifold-OS", "mos@localhost")

_SEP_FIELD = "\x1f"
_SEP_REC = "\x1e"

# A commit tárgyába és a trailerek értékébe CSAK egysoros, vezérlőkarakter-mentes szöveg kerülhet (L13, T017): a Python
# `splitlines()` a `\x1c–\x1e`, `\x85`, U+2028/2029 jeleknél is sort tör, és a `log()` saját `\x1e`/`\x1f` elválasztója
# is ide tartozik — egy fájlnévből vagy egy `dontes` mezőből így hamis trailer vagy hamis commit-rekord lett volna.
VEZERLO = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]")
_TRAILER_KULCS = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_ADD_ATMENETI = re.compile(r"unable to stat|No such file or directory", re.IGNORECASE)
# A vault `.gitattributes`-e nem hathat a pillanatképre (T099): `filter` (lfs), `merge`, `text` (EOL-konverzió), `ident` kikapcsolva.
# A `-diff` SZÁNDÉKOSAN nincs benne (eltérés az audit javaslatától): minden fájlt binárisnak jelölne a diffben, ezzel a
# `--numstat` számai elvesznének, és a visszavonás szöveges patch-ei bináris patchekké válnának (a későbbi, nem ütköző
# szerkesztés fölötti visszavonás ütközne). A `diff=<driver>` sor a vaultban hatástalan: a driver-konfig a (kizárt)
# globális/rendszer-configban lenne, a tároló saját configja nem definiál drivert.
INFO_ATTRIBUTES = "* -filter -merge -text -ident\n"


class SnapshotError(Exception):
    """A git-művelet nem sikerült — a munkafa érintetlen maradt vagy vissza lett állítva."""


class NaploAll(SnapshotError):
    """Egy megszakadt visszavonás/visszaállítás szándéknaplója áll, és nem oldható fel — új visszavonás addig nem indulhat (409)."""


class UndoConflict(SnapshotError):
    """A visszavonás ütközik egy későbbi változással; a revert meg lett szakítva."""

    def __init__(self, message: str, files: list[str]):
        super().__init__(message)
        self.files = files


@dataclass
class Commit:
    sha: str
    date: str
    subject: str
    trailers: dict[str, str] = field(default_factory=dict)

    @property
    def run(self) -> str | None:
        return self.trailers.get(TRAILER_RUN)

    @property
    def item(self) -> str | None:
        return self.trailers.get(TRAILER_ITEM)


def tisztit(szoveg) -> str:
    """Egysorossá tétel: a vezérlőkarakterek (újsor, `\\x1e`, `\\x1f`, `\\x85`, U+2028/2029, …) szóközre cserélődnek."""
    return VEZERLO.sub(" ", str(szoveg))


def commit_uzenet(message: str, trailers: dict[str, str] | None = None) -> str:
    """A commit teljes üzenete: tisztított tárgy + (ha van) üres sor + `Kulcs: érték` trailerek. Érvénytelen
    trailer-kulcsra `SnapshotError`. Egyetlen helyen készül (L13): a `commit` és a visszavonás/visszaállítás is ezt hívja."""
    msg = tisztit(message).strip()
    if trailers:
        sorok = []
        for k, v in trailers.items():
            if not isinstance(k, str) or not _TRAILER_KULCS.fullmatch(k):
                raise SnapshotError(f"érvénytelen trailer-kulcs: {k!r}")
            sorok.append(f"{k}: {tisztit(v).strip()}")
        msg += "\n\n" + "\n".join(sorok)
    return msg


def _parse_trailers(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.split("\n"):          # CSAK újsornál (a `splitlines()` az U+2028-nál, \\x85-nél, \\x1e-nél is bontana)
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def hermetikus_env() -> dict[str, str]:
    """A git hívások alap-környezete (T099): a hívó `GIT_*` változói nélkül, és a globális/rendszer-config, a rendszer
    `gitattributes` kizárva — a felhasználó vagy a gép git-beállítása (`filter.lfs.required`, hookok, aliasok) nem
    változtathatja meg a pillanatkép-tároló viselkedését. A `Repo._env` és a kódtár-bundle is erre épül."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
    })
    return env


# A git-alfolyamatok időkorlátja (A-javító, 2026-10-14): egy lógó git a kör-zár alatt különben örökre blokkolná a mentést és a
# rendezett kilépést. Nagylelkű: a vault egy commitja/visszavonása másodpercek; a teljes bundle a nagy tárolónál is percek.
GIT_IDOKORLAT_MP = 120.0
GIT_BUNDLE_IDOKORLAT_MP = 1800.0


def _idotullepes_uzenet(nev: str, args, mp: float) -> str:
    return (f"[{nev}] git {' '.join(str(a) for a in args)}: a git {mp:g} s alatt sem fejeződött be (időtúllépés) — "
            "a folyamatot leállítottam; a következő indulás az elakadt index.lock-ot takarítja")


class Repo:
    def __init__(self, name: str, work_tree: Path, git_dir: Path, exclude: list[str] | None = None,
                 naplo_dir: Path | None = None):
        self.name = name
        self.work_tree = Path(work_tree)
        self.git_dir = Path(git_dir)
        self.exclude = list(exclude or [])
        self.naplo_dir = Path(naplo_dir) if naplo_dir else None     # a visszavonás szándéknaplója (`{run}/visszavonas/<tár>`)

    # ------------------------------------------------------------ alap

    def _env(self) -> dict[str, str]:
        env = hermetikus_env()
        env.update({
            "GIT_DIR": str(self.git_dir),
            "GIT_WORK_TREE": str(self.work_tree),
            "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
            "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1],
            # H1 (audit): az útlista literális — a `?`, `*`, `[` a fájlnévben nem minta (L13)
            "GIT_LITERAL_PATHSPECS": "1",
        })
        return env

    def git(self, *args: str, check: bool = True, input: str | None = None,
            timeout: float | None = GIT_IDOKORLAT_MP) -> subprocess.CompletedProcess:
        cmd = ["git", "-c", "core.quotepath=false", *args]
        try:
            p = subprocess.run(cmd, cwd=self.work_tree, env=self._env(), input=input,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            raise SnapshotError(_idotullepes_uzenet(self.name, args, timeout)) from None
        if check and p.returncode != 0:
            raise SnapshotError(f"[{self.name}] git {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
        return p

    def git_bytes(self, *args: str, check: bool = True, input: bytes | None = None,
                  timeout: float | None = GIT_IDOKORLAT_MP) -> subprocess.CompletedProcess:
        """Mint a `git`, de bájtokkal: a diff és az apply így a CRLF-et is bájtra viszi. (A szöveges mód
        a `\r\n`-t `\n`-re fordítaná, és a CRLF-es fájl visszavonása ütközéssel állna meg — 2.0-s javítás.)"""
        cmd = ["git", "-c", "core.quotepath=false", *args]
        try:
            p = subprocess.run(cmd, cwd=self.work_tree, env=self._env(), input=input, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise SnapshotError(_idotullepes_uzenet(self.name, args, timeout)) from None
        if check and p.returncode != 0:
            err = (p.stderr or p.stdout).decode("utf-8", errors="replace").strip()
            raise SnapshotError(f"[{self.name}] git {' '.join(args)}: {err}")
        return p

    def exists(self) -> bool:
        return (self.git_dir / "HEAD").is_file()

    def live(self) -> bool:
        """Élő tároló: a git-könyvtár és a munkafa is megvan (a 2.0-ban a ytdlp munkafája a C20-ig hiányzik)."""
        return self.exists() and self.work_tree.is_dir()

    def init(self) -> bool:
        """A tároló létrehozása (idempotens). True, ha most jött létre."""
        if not self.work_tree.is_dir():
            raise SnapshotError(f"[{self.name}] a munkafa nem létezik: {self.work_tree}")
        created = False
        if not self.exists():
            self.git_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                p = subprocess.run(["git", "init", "--bare", "-q", str(self.git_dir)],
                                   capture_output=True, text=True, timeout=GIT_IDOKORLAT_MP)
            except subprocess.TimeoutExpired:
                raise SnapshotError(_idotullepes_uzenet(self.name, ("init",), GIT_IDOKORLAT_MP)) from None
            if p.returncode != 0:
                raise SnapshotError(f"[{self.name}] git init: {p.stderr.strip()}")
            created = True
        # A bare init nem méri a fájlrendszert; az APFS alapból kis-nagybetű-érzéketlen.
        insensitive = os.path.exists(str(self.work_tree).swapcase())
        self.git("config", "core.ignorecase", "true" if insensitive else "false")
        for key, value in (
            ("core.bare", "false"),
            ("core.worktree", str(self.work_tree)),
            ("core.precomposeunicode", "true"),
            ("core.autocrlf", "false"),
            ("core.quotepath", "false"),
            ("commit.gpgsign", "false"),
            ("user.name", AUTHOR[0]),
            ("user.email", AUTHOR[1]),
        ):
            self.git("config", key, value)
        self.write_exclude()
        self.biztosit_kornyezet()
        return created

    def exclude_szoveg(self) -> str:
        """Az `info/exclude` generált tartalma (a doctor ezzel veti össze a lemezen állót)."""
        body = "# Manifold-OS config/os.toml → [pillanat.<név>].kizar (generált, ne szerkeszd)\n"
        return body + "\n".join(self.exclude) + "\n"

    def write_exclude(self) -> bool:
        """Az `info/exclude` a configból generált tartalomra (idempotens, atomi csere). → True, ha most változott."""
        info = self.git_dir / "info"
        info.mkdir(parents=True, exist_ok=True)
        cel, szoveg = info / "exclude", self.exclude_szoveg()
        try:
            if cel.read_text(encoding="utf-8") == szoveg:
                return False
        except (OSError, UnicodeDecodeError):
            pass
        tmp = info / f".exclude.{os.getpid()}.tmp"
        tmp.write_text(szoveg, encoding="utf-8")
        os.replace(tmp, cel)
        return True

    ADD_PROBA = (0.2, 0.5, 1.0)            # másodpercek: az `add` átmeneti hibájánál ennyit vár az újrapróbák előtt

    def _add(self, *args: str) -> None:
        """`git add` — „unable to stat" / „No such file" hibánál (egy külső program közben törölt vagy átnevezett egy fájlt,
        amíg az `add` bejárta a fát; T096) rövid várakozással újrapróbál, mielőtt `SnapshotError` lenne belőle."""
        for varakozas in (*self.ADD_PROBA, None):
            p = self.git("add", *args, check=False)
            if p.returncode == 0:
                return
            hiba = p.stderr.strip() or p.stdout.strip()
            if varakozas is None or not _ADD_ATMENETI.search(hiba):
                raise SnapshotError(f"[{self.name}] git add {' '.join(args)}: {hiba}")
            time.sleep(varakozas)

    def biztosit_kornyezet(self) -> None:
        """A tároló zárt git-környezete (T099), idempotensen — a meglévő (régi) tárolókra is: az `info/attributes`
        (`* -filter -diff -merge -text -ident`) felülírja a vault `.gitattributes`-ét (egy `*.md filter=lfs` sor megállította
        a gépi írást), a `core.hooksPath=/dev/null` és a `core.fsmonitor=false` kizárja a hookokat és a démont."""
        info = self.git_dir / "info"
        info.mkdir(parents=True, exist_ok=True)
        self.write_exclude()        # T142: az `info/exclude` a configból generált; az élő (régi) tároló is megkapja
        att = info / "attributes"
        if not att.is_file() or att.read_text(encoding="utf-8") != INFO_ATTRIBUTES:
            att.write_text(INFO_ATTRIBUTES, encoding="utf-8")
        for kulcs, ertek in (("core.hooksPath", "/dev/null"), ("core.fsmonitor", "false")):
            if self.git("config", "--get", kulcs, check=False).stdout.strip() != ertek:
                self.git("config", kulcs, ertek)

    def has_head(self) -> bool:
        return self.git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0

    # ------------------------------------------------------------ állapot

    def dirty(self) -> list[str]:
        """A még nem rögzített változások (porcelain sorok)."""
        out = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
        return [ln for ln in out.splitlines() if ln.strip()]

    def dirty_paths(self) -> list[str]:
        """A még nem rögzített változások nyers útjai (`-z`: idézés és `" -> "`-vágás nélkül; M1). Átnevezésnél
        (a stage-ben) az új út."""
        out = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
        mezok, utak, i = out.split("\0"), [], 0
        while i < len(mezok):
            m = mezok[i]
            i += 1
            if len(m) < 4:
                continue
            utak.append(m[3:])
            if m[0] in "RC":            # a következő mező a régi út
                i += 1
        return utak

    def commit(self, message: str, trailers: dict[str, str] | None = None,
               paths: list[str] | None = None) -> str | None:
        """Egy pillanatkép. None, ha nincs mit rögzíteni (idempotens, I26)."""
        msg = commit_uzenet(message, trailers)          # előbb: az érvénytelen kulcs semmit ne stage-eljen
        if paths:
            self._add("-A", "--", *paths)
        else:
            self._add("-A")
        if self.has_head() and self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return None
        if not self.has_head() and not self.git("ls-files", "--cached").stdout.strip():
            return None
        self.git("commit", "-q", "--no-verify", "-F", "-", input=msg + "\n")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def log(self, n: int = 20, run: str | None = None) -> list[Commit]:
        """Az utolsó `n` commit; `run` esetén a kör MINDEN commitja a teljes történetben — C33 (T174): `--fixed-strings
        --grep`-pel szűrve (`kor_commitok`), nem a teljes napló Pythonban bontásával (a kör-visszavonás ideje így nem nő
        lineárisan a történettel)."""
        if run is not None:
            return self.kor_commitok(run)
        if not self.has_head():
            return []
        fmt = _SEP_FIELD.join(["%H", "%aI", "%s", "%(trailers:only,unfold)"])
        args = ["log", "-z", f"--format={fmt}"]        # `-z`: NUL-lezárt rekordok (a tárgy/trailer vezérlőkarakter-mentes, T017)
        if run is None:
            args.append(f"-n{n}")
        out = self.git(*args).stdout
        commits = []
        for rec in out.split("\0"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, date, subject, trailers = (rec.split(_SEP_FIELD) + ["", "", "", ""])[:4]
            c = Commit(sha, date, subject, _parse_trailers(trailers))
            if run is None or c.run == run:
                commits.append(c)
        return commits

    def kor_commitok(self, kor: str) -> list[Commit]:
        """A `Mos-Kor: <kor>` trailerű commitok a **teljes történetben** (T094): `--fixed-strings --grep` a szűkítésre, a
        trailer pontos összevetése a találaton (a `Mos-Kor: X1` ne találja az `X10`-et). A helyreállítás és a gépi írás
        ismétlés-felismerése ezt használja — nem az utolsó néhány commitot."""
        if not self.has_head():
            return []
        fmt = _SEP_FIELD.join(["%H", "%aI", "%s", "%(trailers:only,unfold)"])
        ki = self.git("log", "-z", f"--format={fmt}", "--fixed-strings", f"--grep={TRAILER_RUN}: {kor}").stdout
        commitok = []
        for rec in ki.split("\0"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, date, subject, trailers = (rec.split(_SEP_FIELD) + ["", "", "", ""])[:4]
            c = Commit(sha, date, subject, _parse_trailers(trailers))
            if c.run == kor:
                commitok.append(c)
        return commitok

    TRAILER_ERTEK = re.compile(r"[A-Za-z0-9._-]+")
    TRAILER_MAX_COMMIT = 5000

    def trailer_commitok(self, kulcs: str, ertek: str | None = None, *, max_db: int = TRAILER_MAX_COMMIT
                         ) -> tuple[list[Commit], bool]:
        """A **teljes történetben** a `<kulcs>: <érték>` trailerű commitok (T144; a legfrissebb elöl), egyetlen git-folyamattal:
        `--grep` a sor illesztésére (`^kulcs: érték$`, érték nélkül `^kulcs: `), a trailer pontos összevetése a találaton.
        A `max_db` a *találatokra* vonatkozik (nem a történet ablakára): ha több van, a legfrissebb `max_db` jön, és a
        második érték `True` (levágva). Az `ertek` csak `[A-Za-z0-9._-]` jelekből állhat (kör- és feladat-azonosító)."""
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", kulcs) or (ertek is not None and not self.TRAILER_ERTEK.fullmatch(ertek)):
            raise ValueError("érvénytelen trailer-kulcs vagy -érték")
        if not self.has_head():
            return [], False
        minta = f"^{kulcs}: {re.escape(ertek) if ertek is not None else ''}" + ("$" if ertek is not None else "")
        fmt = _SEP_FIELD.join(["%H", "%aI", "%s", "%(trailers:only,unfold)"])
        ki = self.git("log", "-z", f"--format={fmt}", "--extended-regexp", f"--grep={minta}", f"-n{max_db + 1}").stdout
        commitok = []
        for rec in ki.split("\0"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, date, subject, trailers = (rec.split(_SEP_FIELD) + ["", "", "", ""])[:4]
            c = Commit(sha, date, subject, _parse_trailers(trailers))
            if kulcs in c.trailers and (ertek is None or c.trailers[kulcs] == ertek):
                commitok.append(c)
        return commitok[:max_db], len(commitok) > max_db

    _RAW = re.compile(r"\n?:\d{6} \d{6} [0-9a-f]+ [0-9a-f]+ ([A-Z])\d*$")
    _NUMSTAT = re.compile(r"(\d+|-)\t(\d+|-)\t(.*)$", re.S)

    def commitok_fajlok(self, shak: list[str]) -> dict[str, list[dict]]:
        """Több commit érintett fájljai **egyetlen git-folyamatból** (T144; a `commit_fajlok` commitonként két `git show`):
        `{sha: [{ut, allapot, plusz, minusz}]}` — a `commit_fajlok` alakjában (A/M/D, átnevezés nincs; bináris fájlnál a
        számok `None`)."""
        if not shak:
            return {}
        ki = self.git("log", "--no-walk=unsorted", "--stdin", "-z", "--format=%x01%H", "--raw", "--numstat", "--no-renames",
                      input="\n".join(shak) + "\n").stdout
        eredmeny: dict[str, list[dict]] = {}
        for darab in ki.split("\x01"):
            if not darab:
                continue
            tokenek = darab.split("\0")
            sha, i = tokenek[0].strip(), 1
            allapot: dict[str, str] = {}
            while i + 1 < len(tokenek):
                m = self._RAW.fullmatch(tokenek[i])
                if not m:
                    break
                allapot[tokenek[i + 1]] = m.group(1)
                i += 2
            szamok: dict[str, tuple] = {}
            for t in tokenek[i:]:
                m = self._NUMSTAT.fullmatch(t.strip("\n")) if t.strip("\n") else None
                if m:
                    szamok[m.group(3)] = (None, None) if m.group(1) == "-" else (int(m.group(1)), int(m.group(2)))
            eredmeny[sha] = [{"ut": ut, "allapot": a, "plusz": szamok.get(ut, (None, None))[0],
                              "minusz": szamok.get(ut, (None, None))[1]} for ut, a in allapot.items()]
        return eredmeny

    def index_frissit(self) -> None:
        """A git-index stat-adatainak frissítése (`update-index --refresh`): egy helyreállítás után a visszaírt fájlok
        mtime-ja eltér az indexétől, és a `diff-files` (valamint az index-alapú eszközök) zajt látnak (L9 első fele).
        A kör-zár alatt hívandó; hibát nem dob (a frissítés kényelmi, nem helyességi lépés)."""
        self.git("update-index", "-q", "--refresh", check=False)

    def changed_files(self, sha: str) -> list[str]:
        """A commit érintett fájljai, átnevezésnél a régi és az új út is (--no-renames)."""
        out = self.git("show", "--name-only", "-z", "--no-renames", "--format=", sha).stdout
        return [f.strip("\n") for f in out.split("\0") if f.strip("\n")]

    def commit_fajlok(self, sha: str) -> list[dict]:
        """A commit érintett fájljai soronként: `{ut, allapot, plusz, minusz}` (`allapot`: A, M, D; átnevezés nincs:
        `--no-renames`). Bináris fájlnál a számok `None`."""
        allapot = {}
        out = self.git("show", "--name-status", "-z", "--no-renames", "--format=", sha).stdout.split("\0")
        i = 0
        while i + 1 < len(out):
            if out[i].strip():
                allapot[out[i + 1]] = out[i].strip()[:1]
            i += 2
        szamok = {}
        out = self.git("show", "--numstat", "-z", "--no-renames", "--format=", sha).stdout.split("\0")
        for rec in out:
            r = rec.strip("\n").split("\t", 2)
            if len(r) == 3:
                szamok[r[2]] = (None, None) if r[0] == "-" else (int(r[0]), int(r[1]))
        return [{"ut": ut, "allapot": a, "plusz": szamok.get(ut, (None, None))[0],
                 "minusz": szamok.get(ut, (None, None))[1]} for ut, a in allapot.items()]

    def commit_machine(self, message: str, trailers: dict[str, str], paths: list[str],
                       pontos_atnevezesek: dict[str, str] | None = None) -> str | None:
        """Gépi pillanatkép: CSAK a megadott utak. Minden más, még nem rögzített változás (a gazda
        kézi szerkesztése) ELŐTTE külön „kézi" commitba kerül, így egy gépi kör visszavonása soha
        nem viszi magával a gazda munkáját. (Mérve 2026-09-23: `add -A`-val a gazda X01-es napló-
        átrendezése két gépi commitba keveredett.)"""
        if not paths:
            raise SnapshotError(f"[{self.name}] gépi pillanatkép csak megadott utakkal készülhet")
        if not self.has_head():
            return self.commit(message, trailers, paths=paths)
        self._add("-A")
        self.git("reset", "-q", "--", *paths)       # csak a stage-ből vesz ki, a munkafát nem érinti
        if self.git("diff", "--cached", "--quiet", check=False).returncode != 0:
            self.git("commit", "-q", "--no-verify", "-F", "-",
                     input="kézi változások (a gépi kör előtt különválasztva)\n\nMos-Forras: kezi\n")
        # csak a megadott (követett) utakhoz tartozó csere: a kizárt (pl. média) út nem kerülhet vissza a listába
        pontos_atnevezesek = {r: u for r, u in (pontos_atnevezesek or {}).items() if r in paths or u in paths}
        if pontos_atnevezesek:
            # CX-003: a fenti reset visszateszi a régi betűzést az indexbe. APFS-en a git add
            # ezt önmagában nem veszi észre, ezért csak a kézi változások elkülönítése UTÁN cseréljük.
            self.git("update-index", "--force-remove", "--", *pontos_atnevezesek)
            paths = sorted((set(paths) - set(pontos_atnevezesek)) | set(pontos_atnevezesek.values()))
        return self.commit(message, trailers, paths=paths)

    # ------------------------------------------------------------ visszavonás

    def _protect_manual_edits(self) -> str | None:
        """A gazda kézi, még nem rögzített szerkesztései külön commitba kerülnek,
        hogy a visszavonás ne írja felül és ne keverje össze őket."""
        return self.commit("kézi változások a visszavonás előtt", {"Mos-Forras": "kezi"})

    def _excluded(self, sha: str, exclude: dict[str, list[str]] | None) -> list[str]:
        if not exclude:
            return []
        return [pat for key, pats in exclude.items() if sha.startswith(key) or key.startswith(sha) for pat in pats]

    def _diff(self, sha: str, skip: list[str]) -> bytes:
        files = [f for f in self.changed_files(sha) if not any(fnmatch.fnmatch(f, p) for p in skip)]
        if not files:
            return b""
        return self.git_bytes("diff", "--binary", "--no-renames", f"{sha}^", sha, "--", *files).stdout

    def _revert(self, shas: list[str], message: str, trailers: dict[str, str],
                exclude: dict[str, list[str]] | None = None) -> str:
        """Útvonalanként alkalmazott visszafelé-diff (`git apply -R --index`), atomikusan: ha
        bármelyik commit nem alkalmazható, az addig visszavontak is visszaállnak, és a munkafa
        változatlan marad. A kivétellista (`exclude`: commit → minták) útjai kimaradnak."""
        for sha in shas:
            if self.git("show", "-s", "--format=%(trailers:key=Mos-Mozgatas,valueonly)", sha).stdout.strip():
                raise SnapshotError("Ez a művelet gitben nem tárolt mozgatást is tartalmaz. "
                                    "A fájlt vagy mappát az átnevezéssel helyezd vissza; a linkjei akkor együtt frissülnek.")
        self.visszavonas_helyreallit_vagy_hiba()      # a kézi commit ELŐTT: a félkész visszavonás nem kerülhet „kézi” commitba
        self._protect_manual_edits()
        nevek = self._disk_names({f for sha in shas for f in self.changed_files(sha)})
        jelzett = self._disk_hints(shas)
        patchek = [(sha[:10], self._diff(sha, self._excluded(sha, exclude))) for sha in shas]
        return self._visszafordit(patchek, message, trailers, nevek, jelzett)

    def _visszafordit(self, patchek: list[tuple[str, bytes]], message: str, trailers: dict[str, str],
                      nevek: dict[Path, str], jelzett: dict[Path, str]) -> str:
        """A patchek fordított alkalmazása és az egy commit — a közös törzs: a commit-visszavonásé (`_revert`) és
        a fájl-visszaállításé (`visszaallit_fajl`, C11b). `patchek`: (rövid azonosító az üzenethez, patch).

        **Atomi (T020)**: az első alkalmazás előtt kis szándéknapló (`naplo_dir`: a patchek és egy `Mos-Muvelet` azonosító);
        ütközésnél és commit-hibánál az alkalmazott patchek visszaalkalmazódnak (a munkafa változatlan), a napló törlődik.
        Ha a folyamat az alkalmazás és a commit között hal meg, a következő indulás `visszavonas_helyreallit`-ja a naplóból
        görget vissza (vagy, ha a commit megvan, csak a naplót törli)."""
        patchek = [(c, p) for c, p in patchek if p]
        self.visszavonas_helyreallit_vagy_hiba()
        muvelet = secrets.token_hex(6)
        trailers = {**trailers, "Mos-Muvelet": muvelet}
        applied: list[bytes] = []
        self._naplo_ir(muvelet, [p for _, p in patchek])
        try:
            for cimke, patch in patchek:
                chk = self.git_bytes("apply", "-R", "--index", "--check", "-", check=False, input=patch)
                if chk.returncode != 0:
                    raise UndoConflict(
                        f"[{self.name}] a visszavonás ütközik egy későbbi változással ({cimke}); "
                        f"megszakítva, a munkafa változatlan", self._utkozo_fajlok(patch))
                self.git_bytes("apply", "-R", "--index", "-", input=patch)
                applied.append(patch)
            osszeomlas.pont("visszavonas.apply_utan")
            if not applied or self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
                raise SnapshotError(f"[{self.name}] nincs mit visszavonni (a változás már nincs jelen)")
            self.git("commit", "-q", "--no-verify", "-F", "-", input=commit_uzenet(message, trailers) + "\n")
            osszeomlas.pont("visszavonas.commit_utan")
        except BaseException:
            if self._vissza_alkalmaz(applied):          # vissza az eredeti állapotba; a napló csak ekkor törölhető
                self._naplo_torol()
            raise
        self._restore_disk_names(nevek)
        self._restore_disk_names(jelzett)
        sha = self.git("rev-parse", "HEAD").stdout.strip()
        self._naplo_torol()
        return sha

    def _vissza_alkalmaz(self, applied: list[bytes]) -> bool:
        """Az alkalmazott visszafordítások visszacsinálása (a patchek előre alkalmazva, fordított sorrendben). → igaz, ha
        mind visszaállt."""
        ok = True
        for done in reversed(applied):
            ok = self.git_bytes("apply", "--index", "-", check=False, input=done).returncode == 0 and ok
        return ok

    def _utkozo_fajlok(self, patch: bytes) -> list[str]:
        """Az ütköző fájlok pontos útjai (T097, M1 maradéka): a patch `diff --git` darabjait külön ellenőrzi, és az útvonalat
        a `git apply --numstat -z` adja (idézés és szóköz-trükk nélkül) — a `+++ b/` sorokból az idézőjeles/szóközös nevek
        kiestek. Ha egyetlen darab sem ütközik külön, a patch összes fájlja a lista."""
        darabok = [d for d in re.split(rb"(?m)^(?=diff --git )", patch) if d.strip()]

        def utak(b: bytes) -> list[str]:
            ki = self.git_bytes("apply", "--numstat", "-z", "-", check=False, input=b).stdout
            return [r.split(b"\t", 2)[2].decode("utf-8", errors="replace") for r in ki.split(b"\0") if r.count(b"\t") >= 2]

        utkozo: set[str] = set()
        for d in darabok:
            if self.git_bytes("apply", "-R", "--index", "--check", "-", check=False, input=d).returncode != 0:
                utkozo.update(utak(d))
        return sorted(utkozo or utak(patch))

    # ------------------------------------------------------------ a visszavonás szándéknaplója (T020)

    def _naplo_ir(self, muvelet: str, patchek: list[bytes]) -> None:
        d = self.naplo_dir
        if d is None:
            return
        d.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(patchek):
            tartos.fsync_ir(d / f"patch-{i}.bin", p)
        terv = {"verzio": 1, "tar": self.name, "muvelet": muvelet, "patchek": len(patchek),
                "ido": time.strftime("%Y-%m-%d %H:%M:%S")}
        tartos.fsync_ir(d / "terv.json.tmp", json.dumps(terv, ensure_ascii=False, indent=1).encode("utf-8"))
        os.replace(d / "terv.json.tmp", d / "terv.json")     # a napló csak a terv.json-nal érvényes
        tartos.fsync_mappa(d)
        tartos.fsync_mappa(d.parent)

    def _naplo_torol(self) -> None:
        if self.naplo_dir is not None:
            shutil.rmtree(self.naplo_dir, ignore_errors=True)
            try:
                self.naplo_dir.parent.rmdir()               # a `{run}/visszavonas` üres szülő is eltűnik
            except OSError:
                pass

    def visszavonas_helyreallit_vagy_hiba(self) -> None:
        """Új visszavonás előtt (a kör-zár alatt): egy megmaradt napló előbb feldolgozódik; ha így is áll, `NaploAll`."""
        if self.naplo_dir is None or not self.naplo_dir.exists():
            return
        try:
            self.visszavonas_helyreallit()
        except (OSError, ValueError, KeyError, SnapshotError) as e:
            raise NaploAll(f"[{self.name}] egy megszakadt visszavonás naplója áll ({self.naplo_dir}), és nem sikerült "
                           f"feldolgozni: {e}") from e
        if self.naplo_dir.exists():
            raise NaploAll(f"[{self.name}] egy megszakadt visszavonás naplója áll ({self.naplo_dir}); addig új visszavonás "
                           "nem indulhat")

    def visszavonas_helyreallit(self) -> list[str]:
        """Induláskor (a kör-zár alatt): ha egy visszavonás/visszaállítás naplója megmaradt, a folyamat az alkalmazás és a
        commit között halt meg. Ha a commit megvan (a `Mos-Muvelet` trailer), csak a napló törlődik; különben az
        alkalmazott fordítások a naplóból visszagörgetődnek (a munkafa és az index a visszavonás előtti állapotra áll). Ha ez
        nem sikerül (közben más is átírta), a napló `…-megtartva-<idő>` néven megmarad. → a felhasználónak szóló üzenetek."""
        d = self.naplo_dir
        if d is None or not d.exists():
            return []
        tj = d / "terv.json"
        if not tj.is_file():                    # a napló az első alkalmazás előtt készül: terv nélkül a vault érintetlen
            self._naplo_torol()
            return []
        n = json.loads(tj.read_text(encoding="utf-8"))
        if self.has_head() and self.git("log", "-1", "--format=%H", "--fixed-strings",
                                        f"--grep=Mos-Muvelet: {n['muvelet']}").stdout.strip():
            self._naplo_torol()
            return []
        patchek = [(d / f"patch-{i}.bin").read_bytes() for i in range(int(n["patchek"]))]
        for patch in reversed(patchek):         # amelyik fordítása alkalmazva van, annak az eredeti diffje előre alkalmazható
            if self.git_bytes("apply", "--index", "--check", "-", check=False, input=patch).returncode == 0:
                self.git_bytes("apply", "--index", "-", input=patch)
        if self.git("diff", "--cached", "--quiet", check=False).returncode == 0 and \
                self.git("diff", "--quiet", check=False).returncode == 0:
            self._naplo_torol()
            self.index_frissit()
            return [f"Egy megszakadt visszavonás ({self.name}) a commit előtt állt meg; a vault visszaállt a visszavonás előtti "
                    "állapotra, a visszavonás újra elindítható."]
        megtartva = d.with_name(f"{d.name}-megtartva-{time.strftime('%Y%m%d-%H%M%S')}")
        os.rename(d, megtartva)
        return [f"Egy megszakadt visszavonás ({self.name}) naplóját nem sikerült teljesen visszagörgetni (a fájlokat közben más is "
                f"átírta); a patchek itt vannak: {megtartva}."]

    # A `git apply` a fájlt újraírja, a neve a tárolóé (NFC, core.precomposeunicode). A vault sok
    # neve a lemezen NFD (L40, L45): a visszavonás után a fájl a korábbi, lemezen álló nevét kapja
    # vissza, hogy a visszavonás bájtra ÉS névre az előző állapotot adja. (2.0-s kiegészítés: a legacy
    # itt NFC-re nevezett át; a tartalom és a git-állapot ugyanaz.)

    def _disk_names(self, files: set[str]) -> dict[Path, str]:
        out: dict[Path, str] = {}
        for rel in files:
            p = self.work_tree / rel
            try:
                for n in os.listdir(p.parent):
                    if unicodedata.normalize("NFC", n) == unicodedata.normalize("NFC", p.name) and n != p.name:
                        out[p] = n
            except OSError:
                pass
        return out

    def _disk_hints(self, shas: list[str]) -> dict[Path, str]:
        """A visszavont commitok `Mos-Lemezen` trailere (JSON-lista a lemezen álló relatív utakról): az
        átnevezéssel eltűnt fájl régi (NFD) neve, amelyet a git nem őriz."""
        import json
        out: dict[Path, str] = {}
        for sha in shas:
            ertek = self.git("show", "-s", f"--format=%(trailers:key={TRAILER_DISK},valueonly,separator=%x00)", sha,
                             check=False).stdout.strip("\n\x00 ")
            for resz in filter(None, ertek.split("\x00")):
                try:
                    for rel in json.loads(resz):
                        out[self.work_tree / unicodedata.normalize("NFC", rel)] = os.path.basename(rel)
                except (ValueError, TypeError):
                    pass
        return out

    def _restore_disk_names(self, names: dict[Path, str]) -> None:
        for p, regi in names.items():
            try:
                for n in os.listdir(p.parent):
                    if unicodedata.normalize("NFC", n) == unicodedata.normalize("NFC", regi) and n != regi:
                        os.rename(p.parent / n, p.parent / regi)
            except OSError:
                pass

    def undo_commit(self, sha: str, exclude: dict[str, list[str]] | None = None) -> str:
        full = self.git("rev-parse", "--verify", f"{sha}^{{commit}}").stdout.strip()
        subject = self.git("log", "-1", "--format=%s", full).stdout.strip()
        return self._revert([full], f"visszavonás: {subject}", {"Mos-Visszavon": full}, exclude)

    def undo_run(self, run_id: str, exclude: dict[str, list[str]] | None = None, feladat: str | None = None,
                 commitok: list[Commit] | None = None) -> str:
        """Egy kör minden commitjának visszavonása. `feladat` (T095): csak az adott `Mos-Feladat` commitjai — a régi,
        másodperc-felbontású kör-azonosító két feladat körét összeolvaszthatta. `commitok`: a kör már lekérdezett commitjai
        (`kor_commitok`; a hívó megosztja, T174)."""
        if commitok is None:
            commitok = self.kor_commitok(run_id)
        commits = [c for c in commitok if feladat is None or c.trailers.get(TRAILER_TASK) == feladat]
        if not commits:
            raise SnapshotError(f"[{self.name}] nincs commit ehhez a körhöz: {run_id}" + (f" (feladat: {feladat})" if feladat else ""))
        return self._revert([c.sha for c in commits], f"visszavonás: kör {run_id} ({len(commits)} tétel)",
                            {"Mos-Visszavon-Kor": run_id}, exclude)

    # ------------------------------------------------------------ egy fájl története (C11b)

    def fajl_naplo(self, ut: str, n: int = 100) -> list[dict]:
        """Egy fájl története, az átnevezéseket követve (`git log --follow`), a legújabb elöl. Elemenként: a commit
        (`sha`, `datum`, `targy`, `trailerek`), az `statusz` (A hozzáadva, M módosítva, D törölve, R átnevezve) és az
        `ut_akkor` — a fájl útja *abban* a commitban (átnevezésnél az új), `regi_ut` az átnevezés előtti."""
        if not self.has_head():
            return []
        fmt = _SEP_REC + _SEP_FIELD.join(["%H", "%aI", "%s", "%(trailers:only,unfold)"])
        out = self.git("log", "--follow", "--name-status", "-z", f"-n{n}", f"--format={fmt}", "--", ut).stdout
        lista = []
        for rec in out.split(_SEP_REC):
            if not rec.strip("\n\0"):
                continue
            fej, _, farok = rec.partition("\0")
            sha, date, subject, trailers = (fej.split(_SEP_FIELD) + ["", "", "", ""])[:4]
            mezok = [m for m in farok.lstrip("\n").split("\0")]
            statusz = (mezok[0] or "M")[:1]
            if statusz in "RC" and len(mezok) >= 3:
                regi, akkor = mezok[1], mezok[2]
            else:
                regi, akkor = None, (mezok[1] if len(mezok) > 1 and mezok[1] else ut)
            c = Commit(sha, date, subject, _parse_trailers(trailers))
            lista.append({"sha": c.sha, "datum": c.date, "targy": c.subject, "trailerek": c.trailers,
                          "statusz": statusz, "ut_akkor": akkor, "regi_ut": regi})
        return lista

    def fajl_valtozat(self, sha: str, ut: str, max_bajt: int = 8 * 1024 * 1024) -> tuple[str | None, str | None]:
        """A fájl szövege a commit után: (szöveg, None) vagy (None, ok): `nincs` (törölve volt), `nagy`, `kodolas`
        (nem UTF-8). A sorvég marad, ahogy a tárolóban áll."""
        p = self.git_bytes("show", f"{sha}:{ut}", check=False)
        if p.returncode != 0:
            return None, "nincs"
        if len(p.stdout) > max_bajt:
            return None, "nagy"
        try:
            return p.stdout.decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "kodolas"

    def visszaallit_fajl(self, ut: str, sha: str, trailers: dict[str, str]) -> str:
        """Egy fájl visszaállítása a `sha` commit utáni változatára — **revert-commitként**: a `sha..HEAD` közti fájl-diff
        fordított alkalmazása (`apply -R --index`), tehát maga is visszavonható, és a történet nem íródik át. Előtte a
        kézi változások külön commitba kerülnek. Az útnak a két változatban azonosnak kell lennie."""
        full = self.git("rev-parse", "--verify", f"{sha}^{{commit}}").stdout.strip()
        self.visszavonas_helyreallit_vagy_hiba()      # a kézi commit ELŐTT (lásd `_revert`)
        self._protect_manual_edits()
        patch = self.git_bytes("diff", "--binary", "--no-renames", full, "HEAD", "--", ut).stdout
        if not patch:
            raise SnapshotError(f"[{self.name}] ez már a jelenlegi változat: {ut}")
        return self._visszafordit([(full[:10], patch)], f"visszaállítás: {ut} → {full[:7]}",
                                  {**trailers, "Mos-Visszaallit": full}, self._disk_names({ut}), {})

    # ------------------------------------------------------------ mentés

    def bundle(self, dest_dir: Path, keep: int = 10, torolheto: Callable[[Path], bool] | None = None,
               maradek_kor_mp: float = 0.0) -> Path | None:
        """Teljes git bundle a `dest_dir` alá; a legrégebbiek a `keep` fölött törlődnek (csak a saját, `<név>-*.bundle`
        mintájú fájlok; `torolheto`, `maradek_kor_mp`: lásd `bundle_keszit`). A bundle előbb `.bundle.tmp`-be készül és tartósan lemezre kerül,
        csak utána `os.replace`: egy megszakadt mentés nem hagy csonka `.bundle`-t; a megmaradt `.bundle.tmp`-ket a következő
        mentés takarítja."""
        if not self.has_head():
            return None
        return bundle_keszit(self.name, lambda tmp: self.git("bundle", "create", "-q", str(tmp), "--all",
                                                             timeout=GIT_BUNDLE_IDOKORLAT_MP), dest_dir, keep, torolheto,
                             maradek_kor_mp)


def bundle_keszit(nev: str, keszit, dest_dir: Path, keep: int = 10,
                  torolheto: Callable[[Path], bool] | None = None, maradek_kor_mp: float = 0.0) -> Path:
    """A közös bundle-mag (a vault/ytdlp tároló és a kódtár): `keszit(tmp)` kiírja a bundle-t a `tmp` útra; a tartós
    átnevezés és a `<nev>-*.bundle` rotáció itt van. `torolheto(régi)` (F3-DESIGN §5): a `keep` fölötti régi bundle csak akkor
    törlődik, ha igazat ad; `None` = mindegyik törölhető (a mai viselkedés). A közös, tulajdonos nélküli mappában (`mentes`
    „örökölt” szabálya) ezzel marad meg az ismeretlen fejű, idegen bundle; a hiba vagy a kivétel „nem törölhető”-t jelent.
    `maradek_kor_mp`: a megszakadt mentés félkész `<nev>-*.bundle.tmp` fájlját csak az törli, amelyik legalább ennyi másodperce áll
    (0: mind — a saját mappa); a közös mappában egy másik író éppen készülő bundle-je így nem esik áldozatul."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    most = time.time()
    for maradek in dest_dir.glob(f"{nev}-*.bundle.tmp"):
        try:
            if maradek_kor_mp > 0 and most - maradek.stat().st_mtime < maradek_kor_mp:
                continue
        except OSError:
            continue
        maradek.unlink(missing_ok=True)               # egy korábbi megszakadt mentés félkész fájlja
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = dest_dir / f"{nev}-{stamp}.bundle"
    tmp = target.with_suffix(".bundle.tmp")
    keszit(tmp)
    with open(tmp, "rb") as fh:
        tartos.fsync_teljes(fh.fileno())
    osszeomlas.pont("mentes.bundle_tmp")
    os.replace(tmp, target)
    tartos.fsync_mappa(dest_dir)
    own = sorted(dest_dir.glob(f"{nev}-*.bundle"))
    for old in own[:-keep] if keep > 0 else []:
        if torolheto is not None:
            try:
                if not torolheto(old):
                    continue
            except (SnapshotError, OSError):
                continue                                  # nem bizonyítható, hogy a miénk: marad
        old.unlink()
    return target


_KIVETEL_KULCS = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")      # teljes commit-azonosító: a rövid kulcs sok commitra illene
KIVETEL_MAX_BAJT = 1 << 20
KIVETEL_MAX_UT = 256
KIVETEL_MAX_HOSSZ = 512
_KIVETEL_VEZERLO = re.compile("[\x00-\x08\x0a-\x1f\x7f\x85\u2028\u2029]")


def _kivetel_ut_hiba(minta) -> str | None:
    """Egy visszavonási kivétel útmintája (`fnmatch`): vault-relatív, szöveg, nincs abszolút / `..` / pontos szakasz / vezérlőkarakter,
    és az ELSŐ szakasza literális (a `*`, `*/x.md` minden commit minden fájlját kivenné a visszavonásból)."""
    if not isinstance(minta, str) or not minta or len(minta) > KIVETEL_MAX_HOSSZ:
        return "szöveg kell (legfeljebb 512 karakter)"
    if _KIVETEL_VEZERLO.search(minta) or "\\" in minta:
        return "vezérlőkarakter vagy visszaperjel"
    if minta.startswith(("/", "~")):
        return "abszolút út"
    reszek = [r for r in minta.split("/") if r]
    if not reszek or any(r == ".." or r.startswith(".") for r in reszek):
        return "`..` vagy pontos szakasz"
    if not reszek[0].strip("*?[]"):
        return "az első szakasz nem lehet csupa helyettesítő jel"
    return None


def kivetelek_olvas(p: Path) -> tuple[dict[str, list[str]], list[str]]:
    """A visszavonási kivételek fájlja → (az érvényes bejegyzések: commit → útminták, a hibák leírása). A fájl a termékben a munkatér
    `pillanat-kivetelek.json`-ja (megbízhatatlan: a vault utazik): az olvashatatlan fájl és az érvénytelen bejegyzés (nem teljes
    commit-azonosító, nem `{"utak": [...]}` alak, túl sok vagy érvénytelen útminta) kimarad, és a hibák közé kerül — a visszavonás a
    többivel fut, nem kivétellel áll le. A `_`-kezdetű kulcsok (`_leiras`) megjegyzések."""
    hibak: list[str] = []
    try:
        with open(p, "rb") as f:
            nyers = f.read(KIVETEL_MAX_BAJT + 1)
        if len(nyers) > KIVETEL_MAX_BAJT:
            return {}, [f"{p.name}: a fájl túl nagy"]
        adat = json.loads(nyers.decode("utf-8"))
    except (OSError, ValueError, RecursionError) as e:
        return {}, [f"{p.name}: nem olvasható JSON ({type(e).__name__})"]
    if not isinstance(adat, dict):
        return {}, [f"{p.name}: JSON-objektum kell"]
    ki: dict[str, list[str]] = {}
    for kulcs, v in adat.items():
        if not isinstance(kulcs, str) or kulcs.startswith("_"):
            continue
        if not _KIVETEL_KULCS.fullmatch(kulcs):
            hibak.append(f"{kulcs[:16]}: nem teljes (40/64 hexa jegyű) commit-azonosító")
            continue
        utak = v.get("utak") if isinstance(v, dict) else None
        if not isinstance(utak, list) or len(utak) > KIVETEL_MAX_UT:
            hibak.append(f"{kulcs[:12]}: `utak` lista kell (legfeljebb {KIVETEL_MAX_UT} elem)")
            continue
        rossz = next((h for h in map(_kivetel_ut_hiba, utak) if h), None)
        if rossz:
            hibak.append(f"{kulcs[:12]}: érvénytelen útminta ({rossz})")
            continue
        ki[kulcs] = list(utak)
    return ki, hibak


def _kivetel_fajl(cfg, name: str) -> Path | None:
    path = cfg.section("pillanat", name).get("kivetelek")
    if not path:
        return None
    try:
        p = Path(cfg.expand(path))
    except Exception:  # noqa: BLE001 — feloldatlan kulcs (nincs munkatér): nincs kivétel
        return None
    return p if p.is_file() else None


def exclusions(cfg, name: str) -> dict[str, list[str]]:
    """A tároló visszavonási kivételei (`[pillanat.<név>].kivetelek` JSON-fájl): commit → útminták. Csak az érvényes bejegyzések
    (`kivetelek_olvas`); hiányzó fájl: `{}`. A hibákat a doctor mutatja (`kivetelek_hibak`)."""
    p = _kivetel_fajl(cfg, name)
    return kivetelek_olvas(p)[0] if p is not None else {}


def kivetelek_hibak(cfg, name: str) -> list[str]:
    """A tároló kivétel-fájljának érvénytelen bejegyzései (a doctor figyelmeztetése); üres: minden rendben vagy nincs fájl."""
    p = _kivetel_fajl(cfg, name)
    return kivetelek_olvas(p)[1] if p is not None else []


def repos(cfg) -> dict[str, Repo]:
    """A konfigurációban felsorolt tárolók ([pillanat.<név>])."""
    out = {}
    for name, sec in cfg.section("pillanat").items():
        kizar = list(sec.get("kizar", []))
        kizar += [m for m in mediatipus.kizar_mintak() if m not in kizar]      # T142: a médialista egy forrásból (C20a)
        out[name] = Repo(name, Path(cfg.expand(sec["munkafa"])), Path(cfg.expand(sec["git_dir"])),
                         kizar, naplo_dir=cfg.path("run") / "visszavonas" / name)
    return out
