"""A pillanatkép-keret: kör-zár, kézi commit előtte, gépi commit utána (a legacy `kor` nem médialánc-része).

Egyszerre egy vault-író lépés fut (`{run}/kor.lock`, `fcntl.flock`, L17). Egy lépés előtt a még nem
rögzített kézi változások külön „kézi” commitba kerülnek (L14), utána a megváltozott utak EGY gépi
commitba, útlistával (L13) — így minden lépés egyenként visszavonható (D1). A próba APFS-klónon fut
(L21): a klónban a `core.worktree` a klónra mutat, az éles adathoz nem nyúl.
"""
from __future__ import annotations

import contextlib
import fcntl
import itertools
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

from . import rejtett, snapshot
from .config import Config

KLON_JEL = "mos.klon"          # a `trial_clone` ezt írja a klón git-configjába (a `mentes.ment` kihagyja)
_szamlalo = itertools.count(1)
_kiadott: set[str] = set()         # a folyamat által már kiadott kör-azonosítók (T095: egy folyamatban nem lehet ütközés)
# A kör-azonosító alakja (L12): `<ELŐTAG>-ÉÉÉÉHHNN-ÓÓPPMM[-utótag]` (az új azonosítók utótagja `-<6 hex>`); új lánc új előtagot hozhat, a `-proba` kötött.
KOR_MINTA = re.compile(r"[A-Z][A-Z0-9]{1,15}-[0-9]{8}-[0-9]{6}[a-z0-9-]*")


class Busy(RuntimeError):
    """Egy kör vagy lépés éppen írja a vaultot (a `wait=False` hívónak)."""


def new_id(prefix: str) -> str:
    """Kör- és feladat-azonosító (L12): `<ELŐTAG>-%Y%m%d-%H%M%S-<6 hex>`; a feladaté `F-…-<n>`. A másodperc-felbontású
    azonosító (T095) két azonos másodpercben induló kört összeolvasztott (a körönkénti visszavonás mindkettőt vitte, a más
    tartalmú ismétlés csendben „ok” lett): az egyedi utótag ezt kizárja."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if prefix == "F":
        return f"F-{stamp}-{next(_szamlalo)}"
    while True:
        azon = f"{prefix}-{stamp}-{secrets.token_hex(3)}"
        if azon not in _kiadott:
            if len(_kiadott) > 4096:
                _kiadott.clear()
            _kiadott.add(azon)
            return azon


def lock_path(cfg: Config) -> Path:
    return cfg.path("run") / "kor.lock"


FELHASZNALOI_TURELEM_MP = 3.0        # a felhasználói visszavonás/visszaállítás/átnevezés ennyit vár a rövid zár-tartásra


def felhasznaloi_turelem(cfg: Config) -> float:
    """A felhasználó kérte kör-záras művelet (visszavonás, visszaállítás, átnevezés) türelme mp-ben (`[core]
    kor_zar_turelem_mp`). Ok (Mac-integráció 2026-10-07): a gépi kör végén az időzített bundle (34. döntés) a kör-zár
    alatt fut; nélküle a kör értesítésének „Visszavonás” gombja épp a bundle alatt 409-et kapott (28(d): tételek között
    a visszavonás szabad). A valódi, hosszú kört a türelem nem várja ki: utána változatlanul 409."""
    return max(0.0, float(cfg.section("core").get("kor_zar_turelem_mp", FELHASZNALOI_TURELEM_MP)))


@contextlib.contextmanager
def run_lock(cfg: Config, wait: bool = True, log=lambda s: None, turelem_mp: float = 0.0):
    """A kör-zár (L17). A zár tartalma `pid <pid> · HH:MM:SS`, elengedéskor üres. `wait=False` mellett a `turelem_mp`
    (> 0) legfeljebb ennyi ideig próbálkozik (50 ms-onként) a `Busy` előtt — a rövid zár-tartást (bundle) kivárja."""
    lock = lock_path(cfg)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        hatarido = time.monotonic() + turelem_mp
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                foglalt = False
            except BlockingIOError:
                foglalt = True
            if not foglalt or wait or time.monotonic() >= hatarido:
                break
            time.sleep(0.05)
        if foglalt:
            if not wait:
                raise Busy("egy kör éppen írja a vaultot — a lépés a kör vége után indítható") from None
            fh.seek(0)
            log(f"[kör] egy másik kör fut ({fh.read().strip() or '?'}) — megvárom")
            fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid {os.getpid()} · {time.strftime('%H:%M:%S')}")
        fh.flush()
        try:
            yield
        finally:
            fh.seek(0)
            fh.truncate()
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def try_run_lock(cfg: Config):
    """A kör-zár, ha szabad: True — különben False, várakozás nélkül (a szerkesztő mentése így nem áll meg)."""
    lock = lock_path(cfg)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def indulasi_zar(cfg: Config):
    """Az indulási helyreállítás kerete (K1, H3): a kör-zár várakozás nélkül. True, ha megvan; foglaltnál False,
    és a hívó semmit nem javít (egy másik folyamat éppen a vaultot írja)."""
    try:
        with run_lock(cfg, wait=False):
            yield True
    except Busy:
        yield False


def vault_letezik(cfg: Config) -> bool:
    """Valódi vault-e a konfigurált út: van `.obsidian` mappája. A nem létező vaulton (a symlinkelt `var/`-ú
    munkafában az `{os}/../Manifold` nincs meg) nincs mit javítani és visszaállítani: az indulási helyreállítás
    ilyenkor nem futhat, mert a valódi `{run}` szándéknaplóját a nem létező vaulton „állítaná vissza” (T002)."""
    return (cfg.path("vault") / ".obsidian").is_dir()


def index_lock_takaritas(cfg: Config) -> list[str]:
    """Az élő tárolók elakadt `index.lock`-ja (SIGKILL, áramszünet, SSD-kihúzás egy commit közben). Csak a
    kör-zár alatt hívható: a 2.0 minden git-írása a kör-zár alatt fut, a legacy befagyasztva (1. / 11. döntés),
    így a zárat birtokolva a lock csak elakadt lehet. → a felhasználónak szóló üzenetek."""
    uzenetek = []
    for name, repo in live_repos(cfg).items():
        lock = repo.git_dir / "index.lock"
        if lock.exists():
            lock.unlink()
            uzenetek.append(f"A stale index.lock was removed from the {name} snapshot store after an interrupted commit. "
                            "Snapshots are available again.")
    return uzenetek


def indulasi_takaritas(cfg: Config) -> list[str]:
    """Az `index_lock_takaritas` a saját kör-zárával (a tesztnek és a doctornak); a core indulása az
    `indulasi_zar` alatt ezt és az átnevezés helyreállítását együtt hívja."""
    with indulasi_zar(cfg) as van:
        return index_lock_takaritas(cfg) if van else []


# A `tmp_ut` neve: `.<név legfeljebb 200 bájt>.<8 hex>.manifold-tmp` — csak ez az alak a core saját ideiglenes fájlja
TMP_MINTA = re.compile(r"^\..+\.[0-9a-f]{8}\.manifold-tmp$", re.DOTALL)


def tmp_maradekok(cfg: Config) -> list[Path]:
    """A vaultban megmaradt saját ideiglenes fájlok (megszakadt mentés, SIGKILL, áramszünet, SSD-kihúzás): a pontos
    `TMP_MINTA` alakúak, a rejtett mappák (`.obsidian`, `.trash`, `.git`) és a `node_modules` nélkül."""
    root = cfg.path("vault")
    if not (root / ".obsidian").is_dir():
        return []
    ki = []
    for dp, almappak, fajlok in os.walk(root):
        almappak[:] = [a for a in rejtett.metsz(almappak) if not a.startswith(".")]     # I6: a `.manifold` próbaklónjai sem
        ki.extend(Path(dp) / f for f in fajlok if f.endswith(".manifold-tmp") and TMP_MINTA.match(f))
    return sorted(ki)


def tmp_takaritas(cfg: Config, elotte: float | None = None, jeloltek: list[Path] | None = None) -> list[str]:
    """Induláskor a kör-zár alatt (T101, L9): a megmaradt saját ideiglenes fájlok törlése — ponttal kezdődő, véletlen
    utótagú, az Obsidian és a git által nem látott fájlok, felhasználói tartalom nem lehet köztük. `elotte` (epoch s): csak
    az ennél régebbi módosítási idejű fájl törlődik — a core a kézfogás után takarít, amikor a felület már menthet, és egy
    folyó mentés friss ideiglenes fájlja nem maradék. `jeloltek`: a zár nélkül előre bejárt `tmp_maradekok` (a bejárás ne
    tartsa a kör-zárat). → üzenetek."""
    torolt = 0
    for p in tmp_maradekok(cfg) if jeloltek is None else jeloltek:
        try:
            if elotte is not None and p.stat().st_mtime >= elotte:
                continue
            p.unlink()
            torolt += 1
        except OSError:
            pass
    return [f"Removed {torolt} temporary files left by an interrupted save (.manifold-tmp)."] if torolt else []


FELADATNAPLO_MAX_NAP = 60          # `[feladatsor] naplo_max_nap`: ennél régebbi feladatnapló törlődik
FELADATNAPLO_MAX_DB = 500          # `[feladatsor] naplo_max_db`: e fölött a legrégebbiek (de legalább egy napja állók) törlődnek


def feladatnaplo_takaritas(cfg: Config, most: float | None = None, max_nap: float | None = None,
                           max_db: int | None = None) -> int:
    """A feladatsor naplóinak (`{runs}/feladatok/<azonosító>.log`) és a lemaradt `.stop` jelzőinek takarítása (a naplók eddig
    sosem takarultak): törlődik a `naplo_max_nap`-nál régebbi napló, és a `naplo_max_db` fölötti legrégebbiek, ha legalább egy
    napja állnak; az egy napnál régebbi `.stop` jelző. Csak a `feladatok` mappa saját, közvetlen, szabályos `.log`/`.stop`
    fájljai (symlinket, almappát, más fájlt nem érint); az `eval` riportjai (`{runs}/eval`, mérési adat) érintetlenek.
    → a törölt fájlok száma. Hibás fájlt (OSError) kihagy."""
    sec = cfg.section("feladatsor") or {}
    max_nap = float(sec.get("naplo_max_nap", FELADATNAPLO_MAX_NAP) if max_nap is None else max_nap)
    max_db = int(sec.get("naplo_max_db", FELADATNAPLO_MAX_DB) if max_db is None else max_db)
    mappa = Path(cfg.path("runs")) / "feladatok"
    most = time.time() if most is None else most
    naplok, torolt = [], 0
    try:
        bejegyzesek = list(mappa.iterdir())
    except OSError:
        return 0
    for f in bejegyzesek:
        try:
            if f.is_symlink() or not f.is_file() or f.suffix not in (".log", ".stop"):
                continue
            kor = most - f.stat().st_mtime
            if f.suffix == ".stop":
                if kor > 86400:
                    f.unlink()
                    torolt += 1
            else:
                naplok.append((kor, f))
        except OSError:
            continue
    for hely, (kor, f) in enumerate(sorted(naplok, key=lambda x: x[0])):          # a legfrissebb elöl
        if kor > max_nap * 86400 or (hely >= max_db and kor > 86400):
            try:
                f.unlink()
                torolt += 1
            except OSError:
                pass
    return torolt


def live_repos(cfg: Config) -> dict[str, snapshot.Repo]:
    """A konfiguráció élő tárolói; a még nem létező munkafájú (pl. ytdlp a C20 előtt) kimarad."""
    return {n: r for n, r in snapshot.repos(cfg).items() if r.live()}


@contextlib.contextmanager
def snapshot_frame(cfg: Config, message: str, item: str, source: str = "pult", log=lambda s: None,
                   wait: bool = True, kor: str | None = None, trailerek: dict[str, str] | None = None):
    """Egy vault-író lépés keretezése (a legacy `pillanat_keret`): kör-zár → kézi commit → a lépés →
    a lépés által megnevezett utak EGY gépi commitba (`Mos-Kor: LEPES-…`). `wait=False`: foglalt zárnál `Busy`.
    A törzsnek az eredmény `utak` kulcsába **kötelezően** be kell tennie a vault-tároló pontos útlistáját (C29.8, T136;
    L13: „minden piszkos út” gépi commitba soha nem kerülhet): csak ezek az utak kerülnek a gépi commitba, és csak a vault-
    tárolóba. A hiányzó `utak` hiba (`ValueError`, gépi commit nincs, a fájlok a felhasználó nem rögzített változásai
    maradnak); az üres lista „nincs mit commitolni” (ismételt kérés, változás nélküli tétel), nem hiba. A gépi-írás
    szolgáltatás (C16.5) a saját körével (`kor`) és további trailerekkel hívja."""
    with run_lock(cfg, wait=wait, log=log):
        repos = live_repos(cfg)
        for repo in repos.values():
            repo.commit("kézi változások a lépés előtt", {"Mos-Forras": "kezi"})
        result: dict = {"sha": None}
        yield result
        if not isinstance(result.get("utak"), (list, tuple)):
            raise ValueError("a snapshot_frame törzsének meg kell adnia a gépi commit útlistáját (`e[\"utak\"] = [...]`): "
                             "útlista nélkül gépi commit nem készül")
        azon = kor or new_id("LEPES")
        tr = {snapshot.TRAILER_RUN: azon, snapshot.TRAILER_ITEM: item, "Mos-Forras": source}
        if os.environ.get("MOS_FELADAT"):       # a feladatsor lépése: a vezérlő ebből listázza a feladat változásait (C17)
            tr[snapshot.TRAILER_TASK] = os.environ["MOS_FELADAT"]
        tr.update(trailerek or {})
        for name, repo in repos.items():
            utak = list(result["utak"]) if name == "vault" else []
            if utak:
                sha = repo.commit_machine(message, tr, utak)
                if name == "vault":
                    result["sha"] = sha
        result["kor"] = azon


def apfs_clone(src: Path, dst: Path) -> None:
    """APFS-klón (`cp -c -R`): azonnali, helyfoglalás nélküli másolat ugyanazon a köteten."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["cp", "-c", "-R", str(src), str(dst)], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"APFS-klón nem sikerült: {src} → {dst}: {p.stderr.strip()}")


KLON_KIHAGY = (".manifold",)     # a vault-klónból kimarad: a munkatér állapota (benne a `{tmp}/proba` klónjai; I6, K2)
_CP_CSOMAG = 200                 # ennyi gyökér-bejegyzés egy `cp` hívásban (az argumentumhossz korlátja alatt)


def apfs_clone_vault(src: Path, dst: Path, kihagy=KLON_KIHAGY) -> None:
    """A vault APFS-klónja a `.manifold` NÉLKÜL (F3, §3.6): `mkdir dst`, majd `cp -c -R` a gyökér minden más bejegyzésére —
    a v2 `cp -c -R <vault> <dst>`-jével azonos tartalom, csak a munkatér mappája hiányzik. A termékben a `{tmp}` a vaultban
    van (`.manifold/var/tmp`), így a klón nem tartalmazhatja önmagát és a korábbi próbaklónokat (rekurzió)."""
    src, dst = Path(src), Path(dst)
    kihagyott = {k.casefold() for k in kihagy}
    nevek = sorted(n for n in os.listdir(src) if n.casefold() not in kihagyott)
    dst.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(dst, os.stat(src).st_mode & 0o7777)
    for i in range(0, len(nevek), _CP_CSOMAG):
        csomag = [str(src / n) for n in nevek[i:i + _CP_CSOMAG]]
        p = subprocess.run(["cp", "-c", "-R", *csomag, str(dst) + "/"], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"APFS-klón nem sikerült: {src} → {dst}: {p.stderr.strip()}")


def trial_clone(cfg: Config, dest: Path) -> tuple[Path, Path]:
    """A vault (a `.manifold` nélkül) és a pillanatkép-tároló APFS-klónja a `dest` alá; a klónban a `core.worktree` a
    vault-klónra mutat (L21). → (vault-klón, git-klón)."""
    vault, git = dest / cfg.path("vault").name, dest / "vault.git"
    apfs_clone_vault(cfg.path("vault"), vault)
    apfs_clone(snapshot.repos(cfg)["vault"].git_dir, git)
    subprocess.run(["git", "--git-dir", str(git), "config", "core.worktree", str(vault)], check=True)
    # a klón jelölése (A2-iras-7): a `mentes.ment` kihagyja — a klónra mutató core kilépési mentése a valódi
    # `{backup}` bundle-jait forgatná (a rotáció a `<név>-*.bundle` fájlokat származástól függetlenül számolja)
    subprocess.run(["git", "--git-dir", str(git), "config", KLON_JEL, "1"], check=True)
    return vault, git


PROBA_JELOLO = ".mos-proba.json"   # a próbaklón jelölője: a doctor (`_proba_klonok`) ezt keresi; a kézi próbák is ezt írják
GEPI_PROBA = "gepi_iras"           # a gépi írás D9-próbaklónjának `szkript` értéke a jelölőben


def proba_jelol(d: Path, kor: str) -> None:
    """A gépi írás D9-próbaklónjának (`{tmp}/proba/<kör>/`) jelölője: a doctor látja (név, kor, méret), és a
    `proba_klon_takaritas` csak így jelölt mappát töröl."""
    import json
    from datetime import datetime
    from . import tartos
    tartos.atomi_ir(d / PROBA_JELOLO, json.dumps(
        {"szkript": GEPI_PROBA, "kor": kor, "pid": os.getpid(), "megtart": False,
         "letrehozva": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False).encode("utf-8"))


def proba_klon_takaritas(cfg: Config, kiveve=(), most: float | None = None) -> list[str]:
    """A gépi írás `{tmp}/proba/` alatti, `[vault] proba_klon_max_nap`-nál (alap 7; 0: soha) régebbi próbaklónjainak
    törlése. A saját `var/tmp` része (CLAUDE.md §4: törölhető), de csak a jelölt (`szkript: gepi_iras`) mappa, amely nincs a
    `kiveve` között (a futó szolgáltatás saját klónjai), és amelynek a létrehozó folyamata (más core) már nem él.
    → a törölt mappák neve."""
    import json
    import shutil
    from datetime import datetime
    max_nap = float(cfg.section("vault").get("proba_klon_max_nap", 7))
    gyoker = cfg.path("tmp") / "proba"
    if max_nap <= 0 or not gyoker.is_dir():
        return []
    most = time.time() if most is None else most
    kiveve = {Path(k).resolve() for k in kiveve}
    torolt = []
    for d in sorted(gyoker.iterdir()):
        j = d / PROBA_JELOLO
        if not d.is_dir() or d.is_symlink() or d.resolve() in kiveve or not j.is_file():
            continue
        try:
            adat = json.loads(j.read_text(encoding="utf-8"))
            letrehozva = datetime.fromisoformat(adat["letrehozva"]).timestamp()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if adat.get("szkript") != GEPI_PROBA or adat.get("megtart") or most - letrehozva < max_nap * 86400:
            continue
        pid = adat.get("pid")
        if pid != os.getpid():
            try:
                os.kill(int(pid), 0)
                continue                    # egy másik, még élő core klónja
            except PermissionError:
                continue                    # EPERM: a folyamat él, csak nem a miénk (pl. init/launchd szülő): a klónja marad
            except (OSError, TypeError, ValueError):
                pass
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            torolt.append(d.name)
    return torolt
