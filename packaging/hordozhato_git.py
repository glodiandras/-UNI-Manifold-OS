"""Hordozható git a csomagba (F9; PLAN §7 „Git”, R5): a gépi pillanatképek (vault.git) gitje a bundle-ben, a rendszer-git
(Xcode Command Line Tools) nélkül is.

Elrendezés: `runtime/git/{bin/git, libexec/git-core/…, share/git-core/templates}`. A `bin/mos` a `runtime/git/bin`-t a PATH
elejére teszi, ha létezik. A bundle mozgatható kell legyen, ezért a git `RUNTIME_PREFIX=YesPlease`-zel épül: a
`git --exec-path` a bináris saját helyéből számolódik (nem beégetett prefix).

  felderit(mappa)   → GitAllapot: megvan-e, fut-e, verzió, exec-path, relokálható-e, csak rendszer-dylibekre linkel-e;
  ellenoriz_helyben(mappa) a csomagba másolt példányon: az exec-path a csomagon belül van-e;
  epites_parancsok(forras, cel) a forrásból építés parancsai (offline; a forrás-tarballt a `runtime_fetch.py git` tölti le
                    jóváhagyással, a hash-ét a `config/runtime-pins.env` rögzíti).
Hiányzó git: érthető `CsomagHiba` a teendőkkel (`HIANY_UZENET`); a `--git-nelkul` kapcsolóval a csomag a rendszer-gitre
támaszkodik (a Health „Snapshots” sora ekkor a Command Line Tools telepítését kéri, ha nincs).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from csomag_kozos import CsomagHiba, Futtato, futtat

# A forrásból építés kapcsolói (PLAN §7): curl/openssl/expat/perl/python/tcltk/gettext nélkül — a használt parancsok mind helyiek
EPITES_KAPCSOLOK = ("RUNTIME_PREFIX=YesPlease", "NO_GETTEXT=YesPlease", "NO_TCLTK=YesPlease", "NO_PERL=YesPlease",
                    "NO_PYTHON=YesPlease", "NO_CURL=YesPlease", "NO_EXPAT=YesPlease", "NO_OPENSSL=YesPlease",
                    "NO_INSTALL_HARDLINKS=YesPlease", "INSTALL_SYMLINKS=YesPlease")
RENDSZER_DYLIB = ("/usr/lib/", "/System/Library/")

HIANY_UZENET = (
    "nincs hordozható git a csomaghoz ({ut}). A termék gépi pillanatképeihez a csomagba épített git kell (a rendszer-git "
    "Command Line Tools nélkül egy telepítő-párbeszédet dob). Teendő:\n"
    "  1. a git forrás-tarball pinje a config/runtime-pins.env-ben (GIT_VERSION, GIT_URL, GIT_SHA256);\n"
    "  2. letöltés jóváhagyással: python packaging/runtime_fetch.py --komponens git --igen\n"
    "  3. építés (offline): python packaging/hordozhato_git.py epit <git-X.Y.Z.tar.xz> <runtime>/git\n"
    "vagy átmenetileg: --git-nelkul (a csomag ekkor a rendszer-gitre támaszkodik)."
)


@dataclass
class GitAllapot:
    mappa: Path
    van: bool = False
    verzio: str = ""
    exec_path: str = ""
    relokalhato: bool = False
    dylibek: list[str] = field(default_factory=list)
    hibak: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.van and not self.hibak

    def szotar(self) -> dict:
        return {"verzio": self.verzio, "relokalhato": self.relokalhato, "exec_path_relativ": self._exec_rel()}

    def _exec_rel(self) -> str:
        try:
            return os.path.relpath(self.exec_path, self.mappa) if self.exec_path else ""
        except ValueError:
            return self.exec_path


def felderit(mappa: Path, futtato: Futtato = futtat) -> GitAllapot:
    """A jelölt hordozható git (`<mappa>/bin/git`) ellenőrzése. Nem dob: a hibák a `hibak` listában."""
    a = GitAllapot(Path(mappa))
    git = a.mappa / "bin" / "git"
    if not (git.is_file() and os.access(git, os.X_OK)):
        return a
    a.van = True
    if not (a.mappa / "libexec" / "git-core").is_dir():
        a.hibak.append("hiányzik a libexec/git-core (a git segédprogramjai)")
    env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "LC_ALL": "C"}
    try:
        v = futtato([git, "--version"], env=env).stdout.strip()
        m = re.search(r"git version (\S+)", v)
        a.verzio = m.group(1) if m else v
        a.exec_path = futtato([git, "--exec-path"], env=env).stdout.strip()
    except CsomagHiba as e:
        a.hibak.append(f"a git nem fut: {e}")
        return a
    valodi = os.path.realpath(a.mappa)
    a.relokalhato = bool(a.exec_path) and os.path.realpath(a.exec_path).startswith(valodi + os.sep)
    if not a.relokalhato:
        a.hibak.append(f"az exec-path nem a git saját mappájában van ({a.exec_path}): RUNTIME_PREFIX=YesPlease nélkül épült, "
                       "a csomag mozgatásakor a segédprogramok nem találhatók")
    try:
        ki = futtato(["otool", "-L", git], check=False).stdout.splitlines()[1:]
        a.dylibek = [s.strip().split(" ")[0] for s in ki if s.strip()]
        idegen = [d for d in a.dylibek if not d.startswith(RENDSZER_DYLIB)]
        if idegen:
            a.hibak.append(f"nem rendszer-dylibre linkel (a csomagban nem lesz meg): {', '.join(idegen)}")
    except CsomagHiba:
        pass                                     # otool nélkül (CLT nélkül) a linkelés nem ellenőrizhető: nem hiba
    return a


def kotelezo(mappa: Path, futtato: Futtato = futtat) -> GitAllapot:
    """`felderit`, és hiány vagy hiba esetén `CsomagHiba` a teendőkkel."""
    a = felderit(mappa, futtato)
    if not a.van:
        raise CsomagHiba("git_hianyzik", HIANY_UZENET.format(ut=mappa))
    if a.hibak:
        raise CsomagHiba("git_hibas", f"a hordozható git ({mappa}) nem csomagolható: " + "; ".join(a.hibak))
    return a


def ellenoriz_helyben(mappa: Path, futtato: Futtato = futtat) -> GitAllapot:
    """A csomagba MÁSOLT git: fut-e, és az exec-path a csomagon belül (az új helyen) van-e."""
    a = felderit(mappa, futtato)
    if not a.ok:
        raise CsomagHiba("git_csomagban_hibas", f"a csomagba másolt git hibás ({mappa}): " + "; ".join(a.hibak or ["nincs"]))
    return a


def epites_parancsok(forras_mappa: Path, cel: Path, *, magok: int | None = None) -> list[list[str]]:
    """A forrásból építés parancsai (a kibontott git-forrásban futnak; hálózat nincs): `make … install DESTDIR=<cel>`,
    `prefix=/`, a `RUNTIME_PREFIX` miatt minden út relatív."""
    n = str(magok or os.cpu_count() or 4)
    return [["make", "-C", str(forras_mappa), f"-j{n}", "prefix=/", *EPITES_KAPCSOLOK, "all"],
            ["make", "-C", str(forras_mappa), "prefix=/", *EPITES_KAPCSOLOK, f"DESTDIR={cel}", "install"]]


def forrasbol_epit(tarball: Path, cel: Path, munka: Path, futtato: Futtato = futtat) -> GitAllapot:
    """Offline építés egy már letöltött, hash-ellenőrzött forrás-tarballból a `cel` alá; a végén `kotelezo` ellenőrzés."""
    import tarfile
    if cel.exists():
        raise CsomagHiba("cel_letezik", f"a cél már létezik: {cel} (tedd félre, majd építsd újra)")
    munka.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as tf:
        tf.extractall(munka, filter="data")
    gyokerek = [p for p in munka.iterdir() if p.is_dir() and (p / "Makefile").is_file()]
    if len(gyokerek) != 1:
        raise CsomagHiba("git_forras", f"a tarball nem egy git-forrásfa: {tarball}")
    for cmd in epites_parancsok(gyokerek[0], cel):
        futtato(cmd, timeout=3600)
    return kotelezo(cel, futtato)


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    try:
        if args[:1] == ["epit"] and len(args) == 3:
            cel = Path(args[2]).resolve()
            a = forrasbol_epit(Path(args[1]).resolve(), cel, cel.parent / ".git-epites")
            print(f"kész: git {a.verzio} → {cel} (relokálható)")
        elif args[:1] == ["felderit"] and len(args) == 2:
            a = felderit(Path(args[1]))
            print(f"van: {a.van}, verzió: {a.verzio}, relokálható: {a.relokalhato}, hibák: {a.hibak or '-'}")
            raise SystemExit(0 if a.ok else 1)
        else:
            print("használat: hordozhato_git.py felderit <runtime/git> | epit <git-forras.tar.xz> <cel>", file=sys.stderr)
            raise SystemExit(2)
    except CsomagHiba as e:
        print(f"HIBA: {e}", file=sys.stderr)
        raise SystemExit(1)
