"""Kézi kör 2: a gépi ellenőrzések, amelyek csak olvasnak (a `docs/KEZI-KOR-2.md` hivatkozza; a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/kor2_olvaso.py <parancs> [kapcsolók]

    k06                      a valódi vault chatkalauz-jegyzetében nincs `KILEPES_PROBA` sor                       (K06)
    k41                      a `var/models/hub` alatti `*.incomplete` blobok és a legacy formátumú index; NEM töröl   (K41)
    k55 [--legacy <gyökér>]  a legacy indítói nem futtathatók, a `var/venv` átnevezve                               (K55)
    k56 [--napok N]          egy hét használat: napi `pult-szerkeszto` commit, `pos.sqlite` v2+, `has_parancs`      (K56)
    k57 elotte|utana [--allapot <json>]   a K57 négy fájljának mtime/méret-pillanatképe, majd az összevetés        (K57)
    k63                      a belső lemezes mentés tartalma és ritmusa, `git bundle verify`                        (K63)
    k71 <pos.sqlite> <név>…  a klón `pos.sqlite*` fájljaiban a megadott jegyzetnevek nincsenek meg                   (K71)

Csak olvas: a vaulthoz, a `vault.git`-hez, a `var/`-hoz és a belső lemezes mentés mappájához (`{backup}`) nem ír; az SQLite-ot egy ideiglenes
**másolaton** nyitja (a WAL a másolaton játszódik vissza), a git `GIT_OPTIONAL_LOCKS=0`-val fut. Egyetlen kivétel a
`k57 elotte`: a pillanatkép JSON-ját az `--allapot` útra (alap: `{tmp}/kor2-mtime.json`, a saját `var/tmp`) írja.
Kilépési kód: 0 = minden RENDBEN, 1 = ELTÉRÉS (a sorok megmondják, mi), 2 = használati hiba.
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import config  # noqa: E402

KALAUZ_JEGYZET = "Manifold-2.0-chatkalauz.md"
HAT_MARADT = 10                                   # a belső mentés rotációja (33. döntés): legfeljebb ennyi példány


def _jel(ok: bool, szoveg: str) -> bool:
    print(f"  {'RENDBEN' if ok else 'ELTÉRÉS'}  {szoveg}")
    return ok


def _git(args: list[str], git_dir: Path | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    cmd = ["git"] + ([f"--git-dir={git_dir}"] if git_dir else []) + args
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)


def _sqlite_masolat(db: Path, cel: Path) -> Path:
    """Az adatbázis (és a `-wal`/`-shm` társai) másolata a `cel` mappába; az eredetihez nem nyúl."""
    ki = cel / db.name
    for kiterj in ("", "-wal", "-shm"):
        src = Path(str(db) + kiterj)
        if src.is_file():
            shutil.copy2(src, cel / (db.name + kiterj))
    return ki


def _olvaso(db: Path, cel: Path) -> sqlite3.Connection:
    c = sqlite3.connect(_sqlite_masolat(db, cel))
    c.execute("PRAGMA query_only = 1")
    return c


# ---------------------------------------------------------------- K06

def k06(vault: Path) -> bool:
    print("K06 — KILEPES_PROBA a chatkalauz-jegyzetben")
    talalt = []
    for r, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if m not in (".obsidian", ".git")]
        talalt += [Path(r) / n for n in fajlok if n == KALAUZ_JEGYZET]
    if not talalt:
        return _jel(False, f"a {KALAUZ_JEGYZET} jegyzet nem található a vaultban ({vault})")
    ok = True
    for p in talalt:
        db = p.read_bytes().count(b"KILEPES_PROBA")
        ok &= _jel(db == 0, f"{p.relative_to(vault)}: {db} KILEPES_PROBA előfordulás (elvárt: 0)")
    return ok


# ---------------------------------------------------------------- K41

def k41(hub: Path, regi_index: Path) -> bool:
    print("K41 — félbemaradt letöltések és a legacy formátumú index (csak listáz)")
    blobok = sorted(hub.rglob("*.incomplete")) if hub.is_dir() else []
    mappak: dict[str, list[int]] = {}
    for b in blobok:
        rel = b.relative_to(hub).parts
        e = mappak.setdefault(rel[0] if rel else "?", [0, 0])
        e[0] += 1
        e[1] += b.stat().st_size
    for nev, (db, meret) in sorted(mappak.items()):
        print(f"      {nev}: {db} blob, {meret / 1e9:.2f} GB")
    ok = _jel(not blobok, f"{len(blobok)} `.incomplete` blob a hub alatt, összesen {sum(m for _, m in mappak.values()) / 1e9:.2f} GB (elvárt: 0)")
    if regi_index.exists():
        ok &= _jel(False, f"{regi_index.name} ({regi_index.stat().st_size} bájt) még a helyén van")
    else:
        ok &= _jel(True, f"{regi_index.name} nincs a helyén")
    return ok


# ---------------------------------------------------------------- K55

def k55(legacy: Path) -> bool:
    print(f"K55 — a legacy fizikai őre ({legacy})")
    if not legacy.is_dir():
        return _jel(False, "a legacy gyökere nem található (a `--legacy` kapcsolóval adható meg)")
    ok = True
    for rel in ("bin/mos", "Manifold-pult.command"):
        p = legacy / rel
        if not p.exists():
            ok &= _jel(False, f"{rel}: nem található (a keresett út: {p})")
            continue
        fut = os.access(p, os.X_OK)
        ok &= _jel(not fut, f"{rel}: {'FUTTATHATÓ' if fut else 'nem futtatható'} (elvárt: nem futtatható)")
    ok &= _jel(not (legacy / "var" / "venv").exists(), "var/venv: " + ("még megvan (át kell nevezni)" if (legacy / "var" / "venv").exists() else "nincs a helyén"))
    return ok


# ---------------------------------------------------------------- K56

def k56(vault_git: Path, pos: Path, napok: int, ma: str | None = None) -> bool:
    print(f"K56 — egy hét valós használat (az utolsó {napok} nap)")
    ma_t = time.strptime(ma, "%Y-%m-%d") if ma else time.localtime()
    ma_s = time.mktime(ma_t)
    nap_lista = [time.strftime("%Y-%m-%d", time.localtime(ma_s - 86400 * i)) for i in range(napok)]
    r = _git(["log", "--all", f"--since={nap_lista[-1]} 00:00", "--grep=Mos-Forras: pult-szerkeszto", "--format=%cs"], git_dir=vault_git)
    ok = _jel(r.returncode == 0, f"git log a {vault_git.name}-ben" + ("" if r.returncode == 0 else f": {r.stderr.strip()}"))
    if r.returncode == 0:
        db: dict[str, int] = {}
        for sor in r.stdout.split():
            db[sor] = db.get(sor, 0) + 1
        for nap in nap_lista:
            print(f"      {nap}: {db.get(nap, 0)} pult-szerkeszto commit")
        ok &= _jel(all(db.get(n, 0) >= 1 for n in nap_lista), f"minden napra legalább egy `Mos-Forras: pult-szerkeszto` commit ({sum(db.get(n, 0) > 0 for n in nap_lista)}/{napok} nap)")
    if not pos.is_file():
        _jel(False, f"{pos} nem található")
        return False
    with tempfile.TemporaryDirectory() as t:
        c = _olvaso(pos, Path(t))
        try:
            uv = c.execute("PRAGMA user_version").fetchone()[0]
            ok &= _jel(uv >= 2, f"pos.sqlite user_version = {uv} (elvárt: ≥ 2)")
            try:
                n = c.execute("SELECT COUNT(*) FROM has_parancs").fetchone()[0]
                ok &= _jel(n > 0, f"has_parancs: {n} sor (elvárt: nem üres)")
            except sqlite3.Error as e:
                ok &= _jel(False, f"has_parancs: {e}")
        finally:
            c.close()
    return ok


# ---------------------------------------------------------------- K57

def _pillanatkep(backup: Path, pos: Path, vault_git: Path, feladatok: Path) -> dict[str, list[int]]:
    ki: dict[str, list[int]] = {}
    for f in (pos, vault_git / "index", feladatok):
        ki[str(f)] = [f.stat().st_mtime_ns, f.stat().st_size] if f.is_file() else [-1, -1]
    if backup.is_dir():
        for p in sorted(backup.rglob("*")):
            if p.is_file():
                s = p.stat()
                ki[str(p)] = [s.st_mtime_ns, s.st_size]
    else:
        ki[str(backup)] = [-1, -1]
    return ki


def k57(mod: str, allapot: Path, backup: Path, pos: Path, vault_git: Path, feladatok: Path) -> bool:
    print(f"K57 — a valódi fájlok mtime-ja ({mod})")
    most = _pillanatkep(backup, pos, vault_git, feladatok)
    if mod == "elotte":
        allapot.parent.mkdir(parents=True, exist_ok=True)
        allapot.write_text(json.dumps(most, ensure_ascii=False, indent=1), encoding="utf-8")
        return _jel(True, f"pillanatkép: {len(most)} fájl → {allapot}")
    if not allapot.is_file():
        return _jel(False, f"nincs előtte-pillanatkép: {allapot}")
    elotte = json.loads(allapot.read_text(encoding="utf-8"))
    kul = [(k, elotte.get(k), most.get(k)) for k in sorted(set(elotte) | set(most)) if elotte.get(k) != most.get(k)]
    for k, a, b in kul:
        print(f"      {k}: {a} → {b}")
    return _jel(not kul, f"{len(most)} fájlból {len(kul)} változott (elvárt: 0)")


# ---------------------------------------------------------------- K63

def _bundle_ok(bundle: Path, git_dir: Path | None) -> bool:
    r = _git(["bundle", "verify", str(bundle)], git_dir=git_dir, cwd=None if git_dir else REPO)
    return r.returncode == 0


def k63(backup: Path, state: Path, vault_git: Path) -> bool:
    print(f"K63 — a belső lemezes mentés ({backup})")
    if not backup.is_dir():
        return _jel(False, "a mentési mappa nem létezik")
    ok = True
    for minta, kod in (("vault-*.bundle", vault_git), ("mos-kodtar-*.bundle", None)):
        lista = sorted(backup.glob(minta))
        ok &= _jel(0 < len(lista) <= HAT_MARADT, f"{minta}: {len(lista)} példány (elvárt: 1–{HAT_MARADT})")
        if lista:
            ok &= _jel(_bundle_ok(lista[-1], kod), f"git bundle verify {lista[-1].name}")
            print(f"      legfrissebb: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lista[-1].stat().st_mtime))}")
    allapotok = sorted(p for p in backup.glob("mos-allapot-*") if p.is_dir())
    ok &= _jel(0 < len(allapotok) <= HAT_MARADT, f"mos-allapot-*/: {len(allapotok)} példány (elvárt: 1–{HAT_MARADT})")
    if allapotok:
        u = allapotok[-1]
        hianyzik = [r for r in ("router.sqlite", "feladatok.sqlite", "szemelyes/pos.sqlite") if not (u / r).is_file()]
        ok &= _jel(not hianyzik and any((u / "state").glob("*.json")),
                   f"{u.name}: router.sqlite, feladatok.sqlite, szemelyes/pos.sqlite, state/*.json" + (f" — hiányzik: {', '.join(hianyzik)}" if hianyzik else ""))
    ok &= _jel(not (state / "mentes-hiba.json").exists(), "{state}/mentes-hiba.json nincs (elvárt)")
    return ok


# ---------------------------------------------------------------- K71

def k71(pos: Path, nevek: list[str]) -> bool:
    print(f"K71 — a törölt utak nem maradtak a {pos.name}* fájlokban")
    ok = True
    for kiterj in ("", "-wal", "-shm"):
        f = Path(str(pos) + kiterj)
        if not f.is_file():
            continue
        adat = f.read_bytes()
        for nev in nevek:
            db = adat.count(nev.encode("utf-8"))
            ok &= _jel(db == 0, f"{f.name}: „{nev}” {db}×")
    with tempfile.TemporaryDirectory() as t:
        c = _olvaso(pos, Path(t))
        try:
            n = c.execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0]
            uv = c.execute("PRAGMA user_version").fetchone()[0]
            print(f"      forras_rekord: {n} sor (a K71 elvárása: a Törlés előttivel azonos), user_version = {uv}")
        except sqlite3.Error as e:
            ok &= _jel(False, f"forras_rekord: {e}")
        finally:
            c.close()
    return ok


# ---------------------------------------------------------------- belépés

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], add_help=True)
    ap.add_argument("parancs", choices=["k06", "k41", "k55", "k56", "k57", "k63", "k71"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--legacy", type=Path)
    ap.add_argument("--napok", type=int, default=7)
    ap.add_argument("--allapot", type=Path)
    a = ap.parse_args(argv[1:])
    cfg = config.load()
    pos = cfg.path("szemelyes") / "pos.sqlite"
    if a.parancs == "k06":
        ok = k06(cfg.path("vault"))
    elif a.parancs == "k41":
        ok = k41(cfg.path("models") / "hub", cfg.path("index") / "manifold.sqlite")
    elif a.parancs == "k55":
        legacy = a.legacy or (Path(os.environ["MOS_LEGACY"]) if os.environ.get("MOS_LEGACY") else None)
        if legacy is None:
            print("k55 --legacy <gyökér> (vagy MOS_LEGACY): alapértelmezett hely nincs")
            return 2
        ok = k55(legacy)
    elif a.parancs == "k56":
        ok = k56(cfg.path("vault_git"), pos, a.napok)
    elif a.parancs == "k57":
        if a.args not in (["elotte"], ["utana"]):
            print("k57 elotte|utana")
            return 2
        ok = k57(a.args[0], a.allapot or cfg.path("tmp") / "kor2-mtime.json", cfg.path("backup"), pos,
                 cfg.path("vault_git"), cfg.path("feladatok_db"))
    elif a.parancs == "k63":
        ok = k63(cfg.path("backup"), cfg.path("state"), cfg.path("vault_git"))
    else:
        if len(a.args) < 2:
            print("k71 <pos.sqlite> <jegyzetnév>…")
            return 2
        ok = k71(Path(a.args[0]), a.args[1:])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
