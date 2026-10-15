"""Visszaállítás a belső lemezes mentésből (C31; 2. audit T065: A2-visszaallitas1-5, A2-visszaallitas1-8).

    bin/mos visszaallit <bundle> [--tar vault|ytdlp] [--igen]

Egy pillanatkép-tároló (`[pillanat.<tár>]`, alapból a vaulté) újraépítése egy `git bundle`-ből (`~/Manifold-backup/
vault-*.bundle`, L18), ha az SSD-n álló tároló elveszett. A lépéssor (ARCHITECTURE 4. „Visszaállítás”):

1. **Előfeltétel**: a core nem fut (`{run}/core.lock` szabad), és a `{vault_git}` (a tár `git_dir`-je) **hiányzik vagy
   üres mappa**. Meglévő tárolót a parancs nem ír felül, nem fésül össze — azt a felhasználó nevezi át előbb.
2. A bundle `git clone --bare`-rel egy ideiglenes testvérmappába (`<git_dir>.visszaallitas-<pid>`), ott `bundle verify`
   és `fsck`; a `origin` távoli (a bundle útja) törlődik; csak siker után kerül a helyére (`os.rename`).
3. A tároló a 2.0 beállításait kapja (`snapshot.Repo.init`: `core.worktree` = a munkafa, NFD/CRLF-hű config, a configból
   generált `info/exclude` és `info/attributes`): ugyanaz, amit a C02 a klónozott tárolón végzett.
4. A munkafa (a vault): ha hiányzik, csak akkor jön létre, ha a **szülője** létezik (egy le nem csatolt SSD helyett nem
   készül mappa a `/Volumes` alá). A HEAD fájából **csak a hiányzó fájlok** íródnak ki (`tartos.kizaro_ir`: meglévőt soha
   nem ír felül); a meglévő, bájtra azonos fájl „azonos”, az eltérő „eltér” (érintetlen, a listában megnevezve); a
   symlink és a gitlink kimarad. A média nincs a bundle-ben (14. döntés): ami bináris volt, az a visszaállítás után is
   hiányzik — a lista végén a felhasználó tudja, mi a visszaállítás határa.
5. Az index a HEAD fájája (`read-tree`), majd `update-index --refresh`; a kimenet összegzi a `git status`-t.

A vaultba a parancs csak a hiányzó fájlokat írja; pillanatképet (commitot) nem készít — a következő core-indulás a
meglévő szabályok szerint rögzít. A kódtár-bundle (`mos-kodtar-*.bundle`) visszaállítása egy sima `git clone` (ARCHITECTURE),
az állapotmásolaté (`mos-allapot-*/`) fájlmásolás; azokhoz ez a parancs nem kell.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config, snapshot, tartos


class VisszaallitasHiba(Exception):
    """A visszaállítás nem indulhat vagy megszakadt; a meglévő állapothoz nem nyúlt."""


def _core_fut(cfg) -> bool:
    zar = cfg.path("run") / "core.lock"
    if not zar.is_file():
        return False
    try:
        with open(zar, "r") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def _ures_vagy_hianyzik(p: Path) -> bool:
    if not p.exists() and not p.is_symlink():
        return True
    if p.is_dir() and not p.is_symlink():
        return not any(n for n in os.listdir(p) if n != ".DS_Store")
    return False


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd, env=snapshot.hermetikus_env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise VisszaallitasHiba(f"git {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
    return p


def _fa(repo: snapshot.Repo) -> list[tuple[str, str, str]]:
    """A HEAD fája: [(mód, sha, út)] (`ls-tree -r -z`, az út nyers bájtjai UTF-8-ként)."""
    out = repo.git_bytes("ls-tree", "-r", "-z", "--full-tree", "HEAD").stdout
    ki = []
    for rekord in out.split(b"\0"):
        if not rekord:
            continue
        fej, _, ut = rekord.partition(b"\t")
        mod, _tipus, sha = fej.decode("ascii").split(" ")
        ki.append((mod, sha, ut.decode("utf-8", errors="surrogateescape")))
    return ki


def visszaallit(cfg, bundle, tar: str = "vault", log=lambda s: None) -> dict:
    """A `tar` tároló visszaállítása a `bundle`-ből a fenti lépéssor szerint. → összegzés (`head`, `fajlok`, `irt`,
    `azonos`, `elter`, `kihagyva`, `munkafa`, `git_dir`, `status`). Hiba: `VisszaallitasHiba` (a meglévőhöz nem nyúlt)."""
    bundle = Path(bundle).expanduser().resolve()
    if not bundle.is_file():
        raise VisszaallitasHiba(f"nincs ilyen bundle: {bundle}")
    tarolok = snapshot.repos(cfg)
    if tar not in tarolok:
        raise VisszaallitasHiba(f"ismeretlen tároló: {tar} (a config [pillanat.*]: {', '.join(sorted(tarolok))})")
    repo = tarolok[tar]
    git_dir, munkafa = repo.git_dir, repo.work_tree
    if _core_fut(cfg):
        raise VisszaallitasHiba("a core fut (a {run}/core.lock foglalt): előbb lépj ki a Manifoldból")
    if not _ures_vagy_hianyzik(git_dir):
        raise VisszaallitasHiba(f"a tároló nem üres: {git_dir} — meglévő tárolót a visszaállítás nem ír felül; "
                                "ha valóban pótolni kell, előbb nevezd át (pl. `<név>.regi`)")
    if not munkafa.is_dir():
        if munkafa.exists() or not munkafa.parent.is_dir():
            raise VisszaallitasHiba(f"a munkafa nem hozható létre: {munkafa} (a szülőmappa nincs meg — csatlakoztatva van "
                                    "a kötet?)")
    # 2. klón ideiglenes helyre, ellenőrzés, utána a helyére
    ideiglenes = git_dir.with_name(f"{git_dir.name}.visszaallitas-{os.getpid()}")
    if ideiglenes.exists():
        shutil.rmtree(ideiglenes)
    git_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        log(f"klón: {bundle.name} → {ideiglenes.name}")
        _git("clone", "--bare", "-q", str(bundle), str(ideiglenes))
        _git("bundle", "verify", "-q", str(bundle), cwd=ideiglenes)
        _git("fsck", "--no-progress", "--connectivity-only", cwd=ideiglenes)
        _git("remote", "remove", "origin", cwd=ideiglenes, check=False)
        if _git("rev-parse", "--verify", "-q", "HEAD", cwd=ideiglenes, check=False).returncode != 0:
            raise VisszaallitasHiba("a bundle-ben nincs HEAD (üres tároló?)")
        if git_dir.is_dir():
            ds = git_dir / ".DS_Store"
            if ds.exists():
                ds.unlink()
            git_dir.rmdir()                       # üres mappa (ellenőrizve): a helyére kerül a klón
        os.rename(ideiglenes, git_dir)
    except BaseException:
        if ideiglenes.exists():
            shutil.rmtree(ideiglenes, ignore_errors=True)
        raise
    tartos.fsync_mappa(git_dir.parent)
    # 3. a 2.0 beállításai, 4. a munkafa
    letrehozva = False
    if not munkafa.is_dir():
        munkafa.mkdir()
        letrehozva = True
    repo.init()
    head = repo.git("rev-parse", "HEAD").stdout.strip()
    irt, azonos, elter, kihagyva = [], [], [], []
    fa = _fa(repo)
    for mod, sha, ut in fa:
        if mod not in ("100644", "100755"):
            kihagyva.append(f"{ut} ({'symlink' if mod == '120000' else mod})")
            continue
        p = munkafa / ut
        if os.path.lexists(p):
            if p.is_file() and not p.is_symlink():
                tartalom = repo.git_bytes("cat-file", "blob", sha).stdout
                (azonos if p.read_bytes() == tartalom else elter).append(ut)
            else:
                elter.append(ut)
            continue
        tartalom = repo.git_bytes("cat-file", "blob", sha).stdout
        p.parent.mkdir(parents=True, exist_ok=True)
        tartos.kizaro_ir(p, tartalom)
        if mod == "100755":
            p.chmod(p.stat().st_mode | 0o111)
        irt.append(ut)
    # 5. az index a HEAD fája; a stat-adat frissítése
    repo.git("read-tree", "HEAD")
    repo.git("update-index", "-q", "--refresh", check=False)
    status = repo.dirty()
    log(f"HEAD {head[:12]}: {len(fa)} követett fájl — kiírva {len(irt)}, azonos {len(azonos)}, eltér {len(elter)}, "
        f"kihagyva {len(kihagyva)}; nem rögzített változás: {len(status)}")
    return {"tar": tar, "bundle": str(bundle), "git_dir": str(git_dir), "munkafa": str(munkafa),
            "munkafa_letrehozva": letrehozva, "head": head, "fajlok": len(fa), "irt": irt, "azonos": azonos,
            "elter": elter, "kihagyva": kihagyva, "status": status}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mos visszaallit", description="Egy pillanatkép-tároló visszaállítása egy bundle-ből "
                                 "(csak hiányzó/üres tároló mellett; meglévő fájlt nem ír felül).")
    ap.add_argument("bundle")
    ap.add_argument("--tar", default="vault")
    ap.add_argument("--igen", action="store_true", help="kérdés nélkül (különben a terv után megerősítést kér)")
    a = ap.parse_args(argv)
    cfg = config.load()
    repo = snapshot.repos(cfg).get(a.tar)
    if repo is None:
        print(f"HIBA: ismeretlen tároló: {a.tar}", file=sys.stderr)
        return 2
    print(f"bundle:   {Path(a.bundle).expanduser()}\ntároló:   {repo.git_dir}\nmunkafa:  {repo.work_tree}\n"
          "A parancs csak a hiányzó fájlokat írja ki; meglévőt nem ír felül, commitot nem készít.")
    if not a.igen:
        try:
            if input("Folytatod? [i/N] ").strip().lower() not in ("i", "igen", "y", "yes"):
                print("megszakítva")
                return 1
        except EOFError:
            print("megszakítva (nincs bemenet; --igen)")
            return 1
    try:
        r = visszaallit(cfg, a.bundle, a.tar, log=lambda s: print(s, flush=True))
    except (VisszaallitasHiba, snapshot.SnapshotError) as e:
        print(f"HIBA: {e}", file=sys.stderr)
        return 1
    for cim, lista in (("eltér (érintetlen)", r["elter"]), ("kihagyva", r["kihagyva"])):
        if lista:
            print(f"{cim}: {len(lista)}")
            for ut in lista[:20]:
                print(f"  {ut}")
            if len(lista) > 20:
                print(f"  … (+{len(lista) - 20})")
    print("kész: a média nincs a bundle-ben (14. döntés) — a médiát a forrásából kell pótolni.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
