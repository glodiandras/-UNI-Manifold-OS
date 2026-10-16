"""Mentés a belső lemezre (L18; H2; 19., 33., 34. döntés): az SSD meghibásodása ellen. A `{backup}` alá kerül
  - a vault (és a ytdlp) pillanatkép-tárolójának git bundle-je (`<tár>-<idő>.bundle`),
  - a **2.0 kódtárának** bundle-je (`mos-kodtar-<idő>.bundle`; a `{os}` git-tára, minden ref; 33. döntés),
  - a kis állapotfájlok **másolata** (`mos-allapot-<idő>/`: az SQLite-ok `VACUUM INTO`-val, a `{state}` JSON/JSONL-fájljai
    — köztük a bináris mozgásnapló (L19) —, a füzetlánc munkamappája, a videó-feladatok és a bejárások állapota; 33. döntés).
A mappa tulajdonosa a `{backup}/.manifold-mentes.json` jelölő (F3-DESIGN §5): üres mappába az első író beírja; a saját mappában
a rotáció a mai, az idegen jelölőjű mappában nincs rotáció (és a `mentes-hiba.json` figyelmeztet), a jelölő nélküli, nem üres
(„örökölt”, pl. a v2-vel közös `~/Manifold-backup`) mappában a régi bundle csak akkor törlődik, ha minden feje megvan ebben a
tárban, az állapotmásolatok (`mos-allapot-*`) és a migráció előtti másolatok (`mos-migracio-*`) rotációja ki van kapcsolva, és a
másik író félkész `*.tmp` fájlját csak a több órás maradékként takarítjuk. Ugyanígy „örökölt” az a mappa, amelynek a jelölője
ennek a munkatér-azonosítónak, de egy MÁSIK, még meglévő vaultnak a jelölője (másolat, amely az azonosítót megtartotta).
A vaultban lévő mentési mappába nem írunk.
A bundle-ökből `[mentes].megtartott_bundle` marad; az állapotmásolatból a legújabb `allapot_megtartott` és az utolsó
`allapot_napi` nap mindegyikéből a nap utolsó másolata (a változatlan fájl az előző másolatból hard linkkel jön, így egy
újabb másolat csak a változást foglalja). A média (fotó, PDF, videó, hang) az SSD-n marad (1. / 14. döntés).

Mikor: kézzel (`python -m core backup`, a feladatsor `mentes` lépése), a core rendezett leállásakor (`kilepeskor`),
minden gépi kör (vault-író feladat) végén és tétlenségben `[mentes].ido_perc` (30) percenként, ha a HEAD változott
(`Utemezo`, 34. döntés), valamint a második ⌘Q ágán egy 1 s-os időkerettel (K44). Az állapotmásolat a leálláskor (és a
migráció előtt, `migracio_elott`) készül; az időzítő legfeljebb `[mentes].allapot_ido_perc` (60) percenként (az élő
SQLite-ok és WAL-ok mtime-ja szinte mindig „változott”). Hogy a bundle friss-e, azt maga a bundle mondja meg
(`git bundle list-heads`): állapotfájl nincs. A lekérdezések csak olvasnak (`GIT_OPTIONAL_LOCKS=0`); minden git-hívásnak
időkorlátja van (`MentesHiba` magyar üzenettel).

Kilépéskor (T022) előbb a 2.0-n kívül (Obsidian, Finder) szerkesztett, még nem rögzített változások egy idempotens
`Mos-Forras: kezi` commitba kerülnek, hogy a bundle a vault tényleges szövegét vigye. Minden tároló mentése külön
próbálkozás: az egyik hibája (belső lemez, zárt stderr) nem viszi el a többit (T023); a hibák a `{state}/mentes-hiba.json`-ba
kerülnek, amelyből a következő indulás üzenetet ad, a doctor és a vezérlő pedig megkülönbözteti a hibás mentést a
normál „változott” állapottól.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from . import frame, osszeomlas, snapshot, tartos, vaultkivul

HIBA_FAJL = "mentes-hiba.json"          # a {state} alatt: az utolsó kilépési/időzített mentés hibái (siker törli)
KODTAR_NEV = "mos-kodtar"
ALLAPOT_NEV = "mos-allapot"
MIGRACIO_NEV = "mos-migracio"       # a migráció ELŐTTI egyfájlos SQLite-másolat (33. döntés, C29.7b)
GIT_OLVAS_MP = 60.0                 # egy csak olvasó git-hívás (rev-parse, status, list-heads) időkorlátja
GIT_BUNDLE_MP = 600.0               # a kódtár `git bundle create`-jének időkorlátja
JEL_NEV = ".manifold-mentes.json"   # a `{backup}` tulajdonosjelölője: {formatum, munkater_id, vault, letrehozva}
JEL_MAX_BAJT = 64 * 1024            # ennél nagyobb jelölő nem a miénk (olvasatlanul „idegen”)
JEL_VAULTOK_MAX = 8                 # a jelölő `vaultok` listája: a már látott vault-utak (a másolat-őr nem engedi el őket)
IDEGEN_TMP_KOR_MP = 6 * 3600        # nem saját mappában a másik író félkész `*.tmp`-je csak ennél öregebben takarítható
IDEGEN_KULCS = "mentes_idegen_mappa"   # a `mentes-hiba.json` figyelmeztetése (a Health `kod`-ja is): a mappa más munkatéré
UT_KULCS = "mentes_ut"              # a `mentes-hiba.json` hibája: a mentési mappa a vaultban van
# Az állapotmásolatba kerülő mappák a {state} alatt (a `{state}`-hez mért név): a `fuzet`/`video_jobs` kulcs útja
# és ezek. Kimarad belőlük a `tmp/` almappa, a média (az előnézeti képek a fotókból újra elkészülnek) és a rejtett fájl.
# A mappanevek az állapot-kompatibilitás miatt rögzítettek (a meglévő {state} ezeken a neveken tárolja a médiaállapotot).
ALLAPOT_MAPPA_KULCSOK = ("fuzet", "video_jobs")
ALLAPOT_STATE_MAPPAK = ("video-bejaras", "Manifold-media/itelet", "Manifold-media/kotes")


class MentesHiba(snapshot.SnapshotError):
    """A belső lemezes mentés hibája (pl. a git időkorlátja); a `SnapshotError` alosztálya, így a hívók meglévő ága fogja."""


class BackupUtHiba(MentesHiba, OSError):
    """A mentési mappa a vaultban van: oda nem írunk. `OSError` is, mert a migráció előtti másolat hívói (`szemelyes_db`,
    `tanulas_db`, `automatika`, `kalibracio`) az `OSError`-t már most úgy kezelik, mint egy nem írható mentési mappát."""


def _naplo_stderr(s: str) -> None:
    """Naplósor a stderr-re; zárt vagy megszakadt stderr (a héj összeomlása után `BrokenPipeError`) nem akaszthatja a mentést."""
    try:
        print(s, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def _biztos(log):
    def ir(s: str) -> None:
        try:
            log(s)
        except (OSError, ValueError):
            pass
    return ir


def _git(parancs: list[str], hatar_mp: float, **kw) -> subprocess.CompletedProcess:
    """Egy git-hívás időkorláttal; a túllépés `MentesHiba` (magyar üzenettel), nem akasztja a kilépést és az időzítőt."""
    try:
        return subprocess.run(parancs, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=hatar_mp, **kw)
    except subprocess.TimeoutExpired:
        muvelet = " ".join(a for a in parancs[1:] if not a.startswith("-") and "/" not in a)[:60]
        raise MentesHiba(f"a git ({muvelet}) {hatar_mp:g} s alatt nem válaszolt; a mentés kimaradt") from None


def _olvas(repo: snapshot.Repo, *args: str) -> subprocess.CompletedProcess:
    return _git(["git", *args], GIT_OLVAS_MP, cwd=repo.git_dir, env={**repo._env(), "GIT_OPTIONAL_LOCKS": "0"})


def _legujabb(nev: str, backup: Path) -> Path | None:
    lista = sorted(Path(backup).glob(f"{nev}-*.bundle")) if Path(backup).is_dir() else []
    return lista[-1] if lista else None


def legujabb(repo: snapshot.Repo, backup: Path) -> Path | None:
    """A tároló legutóbbi bundle-je (a név időbélyege szerint), vagy None."""
    return _legujabb(repo.name, backup)


def nem_rogzitett(repo: snapshot.Repo) -> list[str]:
    """A még nem rögzített változások útjai (a 2.0-n kívül szerkesztett fájlok: Obsidian, Finder) — csak olvas (T022)."""
    ki = _olvas(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    mezok, utak, i = ki.split("\0"), [], 0
    while i < len(mezok):
        m = mezok[i]
        i += 1
        if len(m) >= 4:
            utak.append(m[3:])
            if m[0] in "RC":
                i += 1
    return utak


def friss(repo: snapshot.Repo, backup: Path, dirty: bool = True) -> bool:
    """Igaz, ha a legutóbbi bundle tartalmazza a HEAD-et (vagy nincs mit menteni), és — `dirty` esetén — nincs a
    HEAD-en kívüli, nem rögzített változás sem (T022: a 2.0-n kívül szerkesztett szöveg egyik bundle-ben sincs benne,
    a doctor mégis „friss”-et mondott). A `dirty=False` a drága `git status`-t megspórolja (vezérlő, időzítő)."""
    head = _olvas(repo, "rev-parse", "--verify", "-q", "HEAD").stdout.strip()
    if not head:
        return True
    b = legujabb(repo, backup)
    if b is None:
        return False
    fejek = _olvas(repo, "bundle", "list-heads", str(b)).stdout
    if head not in {ln.split()[0] for ln in fejek.splitlines() if ln.strip()}:
        return False
    return not (dirty and nem_rogzitett(repo))


def probaklon(repo: snapshot.Repo) -> bool:
    """A `frame.trial_clone` jelölte-e a tárolót (`mos.klon = 1`): a klónnak nincs saját mentése."""
    return _olvas(repo, "config", "--get", frame.KLON_JEL).stdout.strip() == "1"


# ------------------------------------------------------------------ a mentési mappa tulajdonosa (F3-DESIGN §5)

def _vaultban(ut: Path, vault: Path) -> bool:
    """A `ut` a vault mappa vagy a belseje (szöveg és fájlrendszer-azonosság szerint). A `.manifold/var` kivétel (a
    `vaultkivul`-é, a kártya-exporthoz) itt nem érvényes: a mentés oda sem kerülhet — a vaulttal egy lemezen élne, és a külső
    teljes mentés a `{var}`-ral együtt újra bejárná."""
    try:
        v = Path(vault).resolve(strict=True)
        p = Path(ut).resolve()
    except (OSError, RuntimeError):
        return False                                       # nincs vault, amit védeni kellene
    return p == v or v in p.parents or vaultkivul.vaultban_van(p, v)


def _backup_ut(cfg) -> Path:
    """A `{backup}`; `BackupUtHiba`, ha a vaultban van (a vault saját mentése nem lehet a vaultban: a bundle bekerülne a
    vault pillanatképébe és a külső mentésbe)."""
    backup = cfg.path("backup")
    vault = cfg.utak.get("vault")
    if vault is not None and _vaultban(backup, vault):
        raise BackupUtHiba(f"a mentési mappa a vaultban van ({backup}): válassz a vaulton kívüli mappát a mentéshez")
    return backup


def _azonossag(cfg) -> dict:
    """Ki ír most: a munkatér azonosítója (hordozható módban `workspace.toml` nélkül nincs) és a vault kanonikus útja."""
    vault = cfg.utak.get("vault")
    try:
        v = str(vault.resolve()) if vault is not None else None
    except (OSError, RuntimeError):
        v = str(vault)
    return {"munkater_id": cfg.workspace_id or None, "vault": v}


def _jel_olvas(backup: Path) -> dict | None:
    """A tulajdonosjelölő: None, ha nincs; `{}`, ha van, de olvashatatlan vagy nem a mi formánk (akkor nem bizonyítható, hogy a
    miénk)."""
    ut = Path(backup) / JEL_NEV
    try:
        if not os.path.lexists(ut):
            return None
        if ut.is_symlink() or not ut.is_file() or ut.stat().st_size > JEL_MAX_BAJT:
            return {}
        d = json.loads(ut.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ok = (isinstance(d, dict) and "munkater_id" in d and "vault" in d
          and (d["munkater_id"] is None or isinstance(d["munkater_id"], str))
          and (d["vault"] is None or isinstance(d["vault"], str))
          and (d.get("vaultok") is None or (isinstance(d["vaultok"], list) and len(d["vaultok"]) <= 4 * JEL_VAULTOK_MAX
                                            and all(isinstance(x, str) for x in d["vaultok"]))))
    return d if ok else {}


def _mas_mappa_letezik(ut: str | None, vault: str | None) -> bool:
    """Az `ut` (egy korábban látott vault) ma is létező MÁSIK mappa-e, mint a `vault` (kanonikus alak vagy fájlrendszer-azonosság)."""
    if not ut or ut == vault:
        return False
    try:
        if not os.path.isdir(ut):
            return False
        return not (vault and os.path.samefile(ut, vault))
    except OSError:
        return False


def _jel_viszony(jel: dict, az: dict) -> str:
    """A jelölő és ez a munkatér viszonya: `"sajat"` | `"orokolt"` | `"idegen"`.
    - más azonosító (vagy a másik azonosító nélkül más vault): `"idegen"`;
    - azonos azonosító: a jelölőben látott vault-utak (`vault` és `vaultok`) közül egy MÁSIK, ma is létező mappa azt jelenti, hogy két
      mappa viseli ugyanazt az azonosítót (másolat, letöltött vault, amely az azonosítót megtartotta; a `workspace.nyit` még nem
      cserélte): a másik mappa mentéseit nem forgathatjuk — `"orokolt"` (csak ismert fejű bundle törölhető, nincs állapotforgatás,
      a jelölőt sem írjuk át). Ha az összes korábbi hely eltűnt, a vault áthelyezett: `"sajat"` (a jelölő követi, a régi hely a
      `vaultok`-ba kerül, hogy az őr a későbbi ütközésnél is megmaradjon)."""
    if jel["munkater_id"] is not None:
        if jel["munkater_id"] != az["munkater_id"]:
            return "idegen"
        korabbi = [x for x in [jel.get("vault"), *(jel.get("vaultok") or [])] if isinstance(x, str)]
        return "orokolt" if any(_mas_mappa_letezik(x, az["vault"]) for x in korabbi) else "sajat"
    return "sajat" if jel["vault"] == az["vault"] else "idegen"   # azonosító nélküli jel: ugyanaz a vault (a munkatér azóta kaphatott id-t)


def _felkesz_maradek(nev: str) -> bool:
    """A saját írók félkész, még át nem nevezett fájlja (`<tár>-*.bundle.tmp`, `mos-allapot-*.tmp`, `mos-migracio-*.sqlite.tmp`): nem
    adat. A jelölő minden írás ELŐTT készül, ezért jelölő nélküli mappában csak egy a jelölő korából (F3 előtti telepítésből)
    megszakadt mentés hagyhat ilyet."""
    return nev.endswith(".bundle.tmp") or (nev.startswith(f"{ALLAPOT_NEV}-") and nev.endswith(".tmp")) \
        or (nev.startswith(f"{MIGRACIO_NEV}-") and nev.endswith(".sqlite.tmp"))


def _ures_mappa(backup: Path) -> bool:
    """Nincs benne semmi, ami adat: a Finder `.DS_Store`-ja, egy másik író félkész jelölője (`*.manifold-tmp`) és a félbemaradt mentés
    félkész maradéka (`_felkesz_maradek`) nem számít."""
    try:
        return not any(p.name != ".DS_Store" and not p.name.endswith(tartos.TMP_UTOTAG) and not _felkesz_maradek(p.name)
                       for p in Path(backup).iterdir())
    except OSError:
        return False                                       # nem olvasható: nem „üres”


def _tulajdonos(cfg) -> str:
    """A mentési mappa és ez a munkatér viszonya (csak olvas): `"sajat"` (a jelölő a miénk), `"ures"` (nincs benne semmi: az
    első író beírja a jelölőt), `"idegen"` (más munkatér jelölője, vagy olvashatatlan jelölő), `"orokolt"` (nincs jelölő, de
    van benne tartalom: pl. a v2-vel közös `~/Manifold-backup`)."""
    backup = cfg.path("backup")
    if not backup.is_dir():
        return "ures"
    jel = _jel_olvas(backup)
    if jel is None:
        return "ures" if _ures_mappa(backup) else "orokolt"
    if not jel:
        return "idegen"
    return _jel_viszony(jel, _azonossag(cfg))


tulajdonos = _tulajdonos                         # a doctor/Health olvasása (csak olvas, nem ír jelölőt)


def _jel_ir(cfg, backup: Path) -> None:
    """A jelölő létrehozása (`FileExistsError`, ha közben más megelőzött): egy üres mappa első írója hívja."""
    Path(backup).mkdir(parents=True, exist_ok=True)
    tartos.kizaro_ir(Path(backup) / JEL_NEV, json.dumps(
        {"formatum": 1, **_azonossag(cfg), "letrehozva": _dt.datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=1).encode("utf-8"))


def _jel_frissit(cfg, backup: Path) -> None:
    """A saját jelölő adatai (azonosító, vault) naprakészen: egy áthelyezett vault vagy a később kapott munkatér-azonosító után
    átírja. A hiba nem akaszthatja a mentést."""
    jel, az = _jel_olvas(backup), _azonossag(cfg)
    if not jel or (jel["munkater_id"], jel["vault"]) == (az["munkater_id"], az["vault"]):
        return
    # a régi hely a `vaultok`-ba kerül (legfeljebb `JEL_VAULTOK_MAX`): ha később ugyanaz az azonosító két létező mappán jelenik meg,
    # a `_jel_viszony` megtalálja a másikat
    korabbi = [x for x in [jel.get("vault"), *(jel.get("vaultok") or [])] if isinstance(x, str) and x != az["vault"]]
    vaultok = list(dict.fromkeys(korabbi))[:JEL_VAULTOK_MAX]
    try:
        tartos.atomi_ir(Path(backup) / JEL_NEV, json.dumps(
            {**jel, **az, "formatum": jel.get("formatum", 1), "vaultok": vaultok}, ensure_ascii=False, indent=1).encode("utf-8"))
    except OSError:
        pass


def _tulajdonos_biztosit(cfg) -> str:
    """Az író belépője (`ment`, `allapot_masolat`, `migracio_elott`): üres mappába beírja a jelölőt (→ `"sajat"`), a saját jelölő
    adatait frissíti; egyébként a `_tulajdonos` eredménye."""
    allapot = _tulajdonos(cfg)
    backup = cfg.path("backup")
    if allapot == "ures":
        try:
            _jel_ir(cfg, backup)
            return "sajat"
        except FileExistsError:
            return _tulajdonos(cfg)                        # egy másik író megelőzött: az ő jelölője dönt
    if allapot == "sajat":
        _jel_frissit(cfg, backup)
    return allapot


def _tmp_kor_mp(tulaj: str) -> float:
    """A félkész `*.tmp` maradék takaríthatóságához kért kor (s): saját (vagy még üres) mappában 0 (minden maradék a miénk: egy
    író van), másikban `IDEGEN_TMP_KOR_MP` — egy másik író (v2, másik munkatér) éppen készülő másolatát vagy bundle-jét nem töröljük."""
    return 0.0 if tulaj in ("sajat", "ures") else float(IDEGEN_TMP_KOR_MP)


def _tmp_oreg(ut: Path, most: float, kor: float) -> bool:
    try:
        return most - ut.stat().st_mtime >= kor
    except OSError:
        return False


def _idegen_uzenet(cfg) -> str:
    return (f"a mentési mappa ({cfg.path('backup')}) másik munkatéré: a régi mentések nem törlődnek; "
            "válassz ennek a munkatérnek külön mentési mappát")


def _fejek_ismertek(olvas, bundle: Path) -> bool:
    """Igaz, ha a bundle minden feje megvan a tárban (`git bundle list-heads` + `git cat-file -e`). Minden kétség (olvashatatlan
    bundle, üres fejlista, időkorlát) „nem”: ismeretlen fejű bundle-t nem törlünk (az örökölt mappa szabálya)."""
    try:
        lista = olvas("bundle", "list-heads", str(bundle))
        if lista.returncode != 0:
            return False
        shak = [ln.split()[0] for ln in lista.stdout.splitlines() if ln.strip()]
        if not shak:
            return False
        for sha in shak:
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) or olvas("cat-file", "-e", sha).returncode != 0:
                return False
    except (MentesHiba, OSError, subprocess.SubprocessError):
        return False
    return True


def _torolheto(tulaj: str, olvas):
    """A `snapshot.bundle_keszit` `torolheto` szabálya a mappa tulajdonosa szerint: saját → `None` (a mai rotáció); örökölt →
    csak az a régi bundle törölhető, amelynek minden feje megvan a tárban (`olvas`); idegen → semmi sem."""
    if tulaj == "sajat":
        return None
    if tulaj == "orokolt":
        return lambda bundle: _fejek_ismertek(olvas, bundle)
    return lambda bundle: False


# ------------------------------------------------------------------ a kódtár (33. döntés)

def kodtar_munkafa(cfg) -> Path | None:
    """A 2.0 kódtárának munkafája (`[mentes].kodtar`, alapból a `{os}`), ha git-tár (a `.git` könyvtár vagy — worktree-ben —
    fájl); egyébként None (álgyökér, kicsomagolt példány)."""
    p = Path(cfg.expand(str(cfg.section("mentes").get("kodtar", "{os}"))))
    return p if (p / ".git").exists() else None


def _kodtar_git(munkafa: Path, *args: str) -> subprocess.CompletedProcess:
    return _git(["git", "-C", str(munkafa), *args], GIT_OLVAS_MP,
                env={**snapshot.hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"})


def kodtar_friss(cfg, backup: Path) -> bool | None:
    """A kódtár legutóbbi bundle-je tartalmazza-e az összes refet és a HEAD-et; None, ha nincs kódtár."""
    munkafa = kodtar_munkafa(cfg)
    if munkafa is None:
        return None
    refek = {ln.strip() for ln in _kodtar_git(munkafa, "for-each-ref", "--format=%(objectname)").stdout.splitlines()
             if ln.strip()}
    head = _kodtar_git(munkafa, "rev-parse", "--verify", "-q", "HEAD").stdout.strip()
    if head:
        refek.add(head)
    if not refek:
        return True
    b = _legujabb(KODTAR_NEV, backup)
    if b is None:
        return False
    fejek = _kodtar_git(munkafa, "bundle", "list-heads", str(b)).stdout
    return refek <= {ln.split()[0] for ln in fejek.splitlines() if ln.strip()}


def _kodtar_bundle(cfg, backup: Path, keep: int, tulaj: str = "sajat") -> Path | None:
    munkafa = kodtar_munkafa(cfg)
    if munkafa is None or not _kodtar_git(munkafa, "rev-parse", "--verify", "-q", "HEAD").stdout.strip():
        return None

    def keszit(tmp: Path) -> None:
        try:
            p = _git(["git", "-C", str(munkafa), "bundle", "create", "-q", str(tmp), "--all"], GIT_BUNDLE_MP,
                     env=snapshot.hermetikus_env())
        except MentesHiba:
            tmp.unlink(missing_ok=True)                 # a félkész bundle ne maradjon
            raise
        if p.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise snapshot.SnapshotError(f"[kódtár] git bundle: {p.stderr.strip() or p.stdout.strip()}")

    return snapshot.bundle_keszit(KODTAR_NEV, keszit, backup, keep,
                                  _torolheto(tulaj, lambda *a: _kodtar_git(munkafa, *a)), maradek_kor_mp=_tmp_kor_mp(tulaj))


# ------------------------------------------------------------------ az állapotfájlok (33. döntés)

def _mappa_fajljai(mappa: Path, nev: str) -> list[tuple[str, Path]]:
    """Egy állapotmappa fájljai (név a másolatban, forrás): a `tmp/` almappa, a rejtett fájl, a média (előnézeti kép),
    a zárfájl és az SQLite-mellékfájl (`-wal`, `-shm`) nélkül; szimbolikus linket nem követ."""
    from . import mediatipus
    ki = []
    for d, almappak, fajlok in os.walk(mappa, followlinks=False):
        almappak[:] = sorted(a for a in almappak if a != "tmp" and not a.startswith("."))
        for f in sorted(fajlok):
            p = Path(d) / f
            if (f.startswith(".") or f.endswith((".lock", "-wal", "-shm", ".tmp")) or mediatipus.media_e(f)
                    or p.is_symlink()):
                continue
            ki.append((f"{nev}/{p.relative_to(mappa).as_posix()}", p))
    return ki


def allapot_forrasok(cfg) -> list[tuple[str, Path]]:
    """A mentendő kis állapotfájlok: (név a másolatban, forrás). A router-, feladat-, tanulás-, automatika- és
    személyes-SQLite-ok, a munkatér `workspace.toml`-ja és `schema.json`-ja (`workspace/…`), a `{state}` JSON- és JSONL-fájljai
    (köztük a `binaris-naplo.jsonl`: a média-mozgásnapló, amelyen a visszavonás áll, L19), a füzetlánc munkamappája (a kötések, 68(c)), a videó-feladatok és a bejárások állapota
    (`ALLAPOT_MAPPA_KULCSOK`, `ALLAPOT_STATE_MAPPAK`); ami nincs meg, kimarad. (A média, a modellek, az indexek
    újraépíthetők vagy nagyok: nincsenek benne.)"""
    f = [("router.sqlite", cfg.path("router_db")), ("feladatok.sqlite", cfg.path("feladatok_db")),
         ("tanulas.sqlite", cfg.path("tanulas_db")),                     # a kártyák FSRS-története (C23a)
         ("automatika.sqlite", cfg.path("automatika_db"))]               # a közös automatika-ütemező állapota (C23b)
    szem, st = cfg.path("szemelyes"), cfg.path("state")
    f += [(f"szemelyes/{p.name}", p) for p in sorted(szem.glob("*.sqlite"))] if szem.is_dir() else []
    f += [(f"state/{p.name}", p) for p in sorted([*st.glob("*.json"), *st.glob("*.jsonl")])] if st.is_dir() else []
    if "binaris_naplo" in cfg.utak:
        bn = cfg.path("binaris_naplo")
        if bn.parent != st:                                              # a {state}-en kívül beállítva: külön név
            f.append((f"binaris_naplo/{bn.name}", bn))
    if "workspace" in cfg.utak:                                          # F3: a munkatér két kis fájlja (a `.manifold/` alatt; ami nincs meg, kimarad)
        ws = cfg.path("workspace")
        f += [(f"workspace/{n}", ws / n) for n in ("workspace.toml", "schema.json") if not (ws / n).is_symlink()]
    mappak = [(k, cfg.path(k)) for k in ALLAPOT_MAPPA_KULCSOK if k in cfg.utak]
    mappak += [(n, st / n) for n in ALLAPOT_STATE_MAPPAK]
    latott: set[Path] = set()
    for kulcs, m in mappak:
        if not m.is_dir() or m.is_symlink():
            continue
        m = m.resolve()
        if any(m == l or l in m.parents for l in latott):
            continue                                                     # egy már felvett mappa része
        latott.add(m)
        try:
            nev = f"state/{m.relative_to(st.resolve()).as_posix()}"
        except ValueError:
            nev = kulcs
        f += _mappa_fajljai(m, nev)
    return [(n, p) for n, p in f if p.is_file()]


def _allapot_mappak(backup: Path) -> list[Path]:
    """A kész állapotmásolatok (a név időbélyege szerint, a legrégebbitől)."""
    return sorted(p for p in Path(backup).glob(f"{ALLAPOT_NEV}-*") if p.is_dir() and not p.name.endswith(".tmp")) \
        if Path(backup).is_dir() else []


def utolso_allapot(backup: Path) -> Path | None:
    lista = _allapot_mappak(backup)
    return lista[-1] if lista else None


def allapot_ritkit(backup: Path, megtartott: int, napi: int, ma: _dt.date | None = None) -> list[str]:
    """Az állapotmásolatok saját megtartási szabálya (nem a bundle-ök `megtartott_bundle`-je: az időzítő gyakran másol,
    és a közös számláló egy napon belül kiforgatná a régebbi állapotot): marad a legújabb `megtartott` darab, és az
    utolsó `napi` nap (a mai is) mindegyikéből a nap utolsó másolata. A legújabb mindig marad. → a törölt nevek."""
    mind = _allapot_mappak(backup)
    if not mind:
        return []
    tart = set(mind[-max(1, megtartott):])
    if napi > 0:
        hatar = (ma or _dt.date.today()) - _dt.timedelta(days=napi - 1)
        naponta: dict[_dt.date, Path] = {}
        for p in mind:                                   # időrendben: a nap utolsó másolata nyer
            try:
                nap = _dt.datetime.strptime(p.name[len(ALLAPOT_NEV) + 1:][:8], "%Y%m%d").date()
            except ValueError:
                continue
            if nap >= hatar:
                naponta[nap] = p
        tart |= set(naponta.values())
    torolt = []
    for p in mind:
        if p not in tart:
            shutil.rmtree(p, ignore_errors=True)
            torolt.append(p.name)
    return torolt


def allapot_friss(cfg, backup: Path) -> bool | None:
    """Az állapotmásolat friss-e (egyik forrás sem újabb a legutóbbi másolatnál); None, ha nincs mit másolni."""
    forrasok = allapot_forrasok(cfg)
    if not forrasok:
        return None
    legutolso = utolso_allapot(backup)
    return legutolso is not None and not _forras_ujabb(forrasok, legutolso)


def _forras_ujabb(forrasok: list[tuple[str, Path]], legutolso: Path) -> bool:
    ref = legutolso.stat().st_mtime
    for _, p in forrasok:
        for q in (p, p.with_name(p.name + "-wal")):
            try:
                if q.stat().st_mtime > ref:
                    return True
            except OSError:
                pass
    return False


def _sqlite_masolat(forras: Path, cel: Path) -> None:
    """Konzisztens pillanatkép egy élő SQLite-ról (WAL-lal együtt): `VACUUM INTO` csak olvasó kapcsolaton."""
    con = sqlite3.connect(f"file:{urllib.parse.quote(str(forras))}?mode=ro", uri=True, timeout=5)   # a `#`, `?`, `%` kódolva (T108)
    try:
        con.execute("VACUUM INTO ?", (str(cel),))
    finally:
        con.close()


def allapot_ido_mp(cfg) -> float:
    """Az időzítő két állapotmásolata közti legkisebb idő (`[mentes].allapot_ido_perc`, alap 60 perc)."""
    return float(cfg.section("mentes").get("allapot_ido_perc", 60)) * 60


def allapot_rendben(cfg, backup: Path, most: float | None = None) -> bool | None:
    """A doctor „mentés (állapot)” sora: rendben, ha a legutóbbi másolat friss, vagy — mivel az élő SQLite-ok és a WAL
    szinte mindig újabbak — legfeljebb két `allapot_ido_perc`-nyi idős (az időzítő, illetve a kilépés hamarosan frissíti).
    None, ha nincs mit másolni."""
    friss_e = allapot_friss(cfg, backup)
    if friss_e is None or friss_e:
        return friss_e
    utolso = utolso_allapot(backup)
    return utolso is not None and (most or time.time()) - utolso.stat().st_mtime <= 2 * allapot_ido_mp(cfg)


def _masol_vagy_linkel(forras: Path, cel: Path, elozo: Path | None) -> None:
    """A nem-SQLite állapotfájl másolata; ha az előző másolat ugyanazon a néven bájtra-mtime-ra egyező (méret + mtime_ns)
    fájlt tart, hard link (a változatlan füzet-állapot így nem foglal újra helyet), különben `copy2` (megtartja az mtime-ot)."""
    if elozo is not None:
        try:
            r, a = elozo.stat(), forras.stat()
            if r.st_size == a.st_size and r.st_mtime_ns == a.st_mtime_ns and not elozo.is_symlink():
                os.link(elozo, cel)
                return
        except OSError:
            pass
    shutil.copy2(forras, cel)


def allapot_masolat(cfg, csak_ha_valtozott: bool = False, log=lambda s: None) -> Path | None:
    """A kis állapotfájlok másolata a `{backup}/mos-allapot-<idő>/` alá (a rendezett leálláskor, az időzített mentésnél
    legfeljebb `allapot_ido_perc`-enként; a migráció előtti másolat a `migracio_elott`). `csak_ha_valtozott`: ha egyik
    forrás sem újabb az utolsó másolatnál, kimarad. Egy fájl hibája nem viszi el a többit; a hibákat a végén `OSError`
    jelzi; a félkész `.tmp` mappa egy váratlan hibánál sem marad meg. → a másolat mappája, vagy None."""
    beall = cfg.section("mentes")
    backup = _backup_ut(cfg)
    megtartott, napi = int(beall.get("allapot_megtartott", 5)), int(beall.get("allapot_napi", 14))
    if backup.is_dir():
        kor = _tmp_kor_mp(_tulajdonos(cfg))                     # (csak olvas) nem saját mappában a másik író készülő másolata nem a miénk
        most = time.time()
        for maradek in backup.glob(f"{ALLAPOT_NEV}-*.tmp"):
            if kor <= 0 or _tmp_oreg(maradek, most, kor):
                shutil.rmtree(maradek, ignore_errors=True)      # egy megszakadt másolat félkész mappája
    forrasok = allapot_forrasok(cfg)
    if not forrasok:
        return None
    legutolso = utolso_allapot(backup)
    if csak_ha_valtozott and legutolso is not None and not _forras_ujabb(forrasok, legutolso):
        log("[mentés] állapotfájlok: a legutóbbi másolat friss")
        return None
    tulaj = _tulajdonos_biztosit(cfg)
    backup.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    cel, tmp = backup / f"{ALLAPOT_NEV}-{stamp}", backup / f"{ALLAPOT_NEV}-{stamp}.tmp"
    tmp.mkdir()
    hibak = []
    try:
        for i, (rel, forras) in enumerate(forrasok):
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            try:
                if forras.suffix == ".sqlite":
                    _sqlite_masolat(forras, tmp / rel)
                else:
                    _masol_vagy_linkel(forras, tmp / rel, legutolso / rel if legutolso is not None else None)
            except (OSError, sqlite3.Error) as e:
                hibak.append(f"{rel}: {e}")
            if i == 0:
                osszeomlas.pont("mentes.allapot_fele")
        tartos.fsync_mappa(tmp)
        if cel.exists():
            shutil.rmtree(cel)
        os.replace(tmp, cel)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)      # a félkész másolat ne maradjon (pl. betelt a belső lemez)
    tartos.fsync_mappa(backup)
    if tulaj == "sajat":
        allapot_ritkit(backup, megtartott, napi)
    else:                                   # közös (örökölt) vagy idegen mappa: nem bizonyítható, hogy a régi másolat a miénk
        log(f"[mentés] állapotfájlok: a rotáció kimarad (a mentési mappa nem ennek a munkatérnek a saját mappája: {tulaj})")
    log(f"[mentés] állapotfájlok: {cel}")
    if hibak:
        raise OSError("az állapotfájlok egy része nem másolható: " + "; ".join(hibak))
    return cel


def migracio_elott(cfg, forras: Path, regi_verzio: int, log=lambda s: None) -> Path:
    """A migráció előtti másolat egy SQLite-ról (33. döntés: „minden migráció előtt”): `{backup}/mos-migracio-<fájl>-v<régi
    verzió>-<idő>.sqlite`, `VACUUM INTO` csak olvasó kapcsolaton (WAL-lal együtt konzisztens), fsync, atomi csere.

    Szándékosan nem az `allapot_masolat`: az (a) a `mos-allapot-*.tmp` maradékot törli — a migrációt író szál (a tracker
    vagy a naptár, kör-zár nélkül) egy másik szál (kilépési mentés, ütemező) készülő másolatát tenné tönkre —, (b) a közös
    rotációja gyorsan kiforgatná a migráció előtti állapotot, (c) minden állapotfájlt másolna egy tábla léptetése miatt.
    A rotáció fájlonként a legújabb `[mentes] megtartott_migracio` (alap 5) másolatot tartja."""
    backup, keep = _backup_ut(cfg), int(cfg.section("mentes").get("megtartott_migracio", 5))
    tulaj = _tulajdonos_biztosit(cfg)
    backup.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    cel = backup / f"{MIGRACIO_NEV}-{forras.stem}-v{regi_verzio}-{stamp}.sqlite"
    tmp = cel.with_name(cel.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        _sqlite_masolat(forras, tmp)
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, cel)
    finally:
        tmp.unlink(missing_ok=True)
    tartos.fsync_mappa(backup)
    mind = sorted(backup.glob(f"{MIGRACIO_NEV}-{forras.stem}-v*.sqlite"))
    # csak a saját mappában forgatunk: az örökölt (v2-vel közös) mappában ugyanezek a fájlnevek a másik telepítés biztonsági
    # másolatai is — a legújabb `keep` a kettő közül maradna, a másik telepítés régi másolatai törlődnének
    for regi in mind[:-keep] if keep > 0 and tulaj == "sajat" else []:
        regi.unlink(missing_ok=True)
    log(f"[mentés] migráció előtti másolat: {cel}")
    return cel


# ------------------------------------------------------------------ a mentés

def ment(cfg, csak_ha_valtozott: bool = False, log=lambda s: None, hibak: dict | None = None,
         allapot: bool = True) -> list[Path]:
    """Az élő tárolók bundle-je, a kódtár bundle-je és az állapotfájlok másolata; `csak_ha_valtozott`: a friss tároló
    kimarad; a próbaklón tárolója mindig kimarad (A2-iras-7: a valódi `{backup}` rotációját nem érheti — ilyenkor a kódtár
    és az állapotfájlok sem mentődnek). `allapot=False`: csak a bundle-ök (az időzítő a két állapotmásolat között).
    Minden elem külön próbálkozás (T023): `hibak` megadásakor a hiba oda kerül (név → üzenet), és a többi elem mentése
    folytatódik; nélküle az első hiba kivétel. A mentési mappa a vaultban: `BackupUtHiba` (`hibak`-kal a `mentes_ut` hiba, nincs írás);
    a mappa tulajdonosa (`_tulajdonos`) szabja a rotációt: saját → a mai, örökölt → csak ismert fejű bundle törlődik, az állapotmásolat
    rotációja ki, idegen → nincs rotáció és a `mentes_idegen_mappa` figyelmeztetés a `hibak`-ban. → a megírt bundle-ök/mappák."""
    log = _biztos(log)
    try:
        backup = _backup_ut(cfg)
    except BackupUtHiba as e:
        if hibak is None:
            raise
        hibak[UT_KULCS] = str(e)
        log(f"[mentés] {e}")
        return []
    keep = int(cfg.section("mentes").get("megtartott_bundle", 10))
    out: list[Path] = []
    klon = False
    tulaj_ertek: list[str] = []

    def tulaj() -> str:
        """A mappa tulajdonosa (egyszer számolva, az első valódi írás előtt — a próbaklón ide nem ér el): üres mappába beírja a
        jelölőt; az idegen mappa figyelmeztetést kap (`hibak`), az örökölt naplót."""
        if not tulaj_ertek:
            t = _tulajdonos_biztosit(cfg)
            tulaj_ertek.append(t)
            if t == "idegen":
                uzenet = _idegen_uzenet(cfg)
                log(f"[mentés] {uzenet}")
                if hibak is not None:
                    hibak[IDEGEN_KULCS] = uzenet
            elif t == "orokolt":
                log("[mentés] közös mentési mappa (nincs tulajdonosjelölő): régi bundle csak ismert fejekkel törlődik")
        return tulaj_ertek[0]

    def probal(nev: str, fn) -> None:
        try:
            fn()
        except (snapshot.SnapshotError, OSError, sqlite3.Error, subprocess.SubprocessError) as e:
            if hibak is None:
                raise
            hibak[nev] = str(e)
            log(f"[mentés] {nev}: nem sikerült: {e}")

    for name, repo in frame.live_repos(cfg).items():
        def egy(name=name, repo=repo):
            nonlocal klon
            if probaklon(repo):
                klon = True
                log(f"[mentés] {name}: próbaklón — a mentése kimarad (a valódi mentés rotációját nem érheti)")
                return
            t = tulaj()
            if csak_ha_valtozott and friss(repo, backup, dirty=False):
                log(f"[mentés] {name}: a legutóbbi bundle friss")
                return
            torolheto = _torolheto(t, lambda *a, r=repo: _olvas(r, *a))
            kw: dict = {}
            if torolheto is not None:
                kw["torolheto"] = torolheto
            if _tmp_kor_mp(t) > 0:
                kw["maradek_kor_mp"] = _tmp_kor_mp(t)
            p = repo.bundle(backup, keep, **kw)
            log(f"[mentés] {name}: {p or 'nincs még commit'}")
            if p:
                out.append(p)
        probal(name, egy)
    if klon:
        return out

    def kodtar():
        if kodtar_munkafa(cfg) is None:
            return
        t = tulaj()
        if csak_ha_valtozott and kodtar_friss(cfg, backup):
            log("[mentés] kódtár: a legutóbbi bundle friss")
            return
        p = _kodtar_bundle(cfg, backup, keep, t)
        log(f"[mentés] kódtár: {p or 'nincs még commit'}")
        if p:
            out.append(p)

    def allapot_resz():
        tulaj()
        p = allapot_masolat(cfg, csak_ha_valtozott, log)
        if p:
            out.append(p)

    probal("kodtar", kodtar)
    if allapot:
        probal("allapot", allapot_resz)
    return out


# ------------------------------------------------------------------ a hibák nyoma

def _hiba_ut(cfg) -> Path:
    return cfg.path("state") / HIBA_FAJL


def hiba_olvas(cfg) -> dict | None:
    """Az utolsó mentés hibái (`{ido, hibak: {név: üzenet}}`), vagy None, ha nincs (a sikeres mentés törli)."""
    try:
        d = json.loads(_hiba_ut(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("hibak") else None


def hiba_ir(cfg, hibak: dict) -> None:
    """A hibák rögzítése (T023); üres `hibak` törli a nyomot."""
    p = _hiba_ut(cfg)
    try:
        if not hibak:
            p.unlink(missing_ok=True)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tartos.atomi_ir(p, json.dumps({"ido": time.strftime("%Y-%m-%d %H:%M:%S"), "hibak": hibak},
                                      ensure_ascii=False, indent=1).encode("utf-8"))
    except OSError:
        pass                            # a hiba-nyom elmaradása nem akaszthatja a kilépést


def hiba_szoveg(d: dict) -> str:
    return "; ".join(f"{nev}: {uzenet}" for nev, uzenet in d["hibak"].items())


# ------------------------------------------------------------------ kilépéskor és időzítve

def kilepes_turelem_mp(cfg) -> float:
    """Ennyit vár a kilépési mentés a kör-zárra (`[mentes].kilepes_turelem_mp`, alap 20 s): egy épp futó időzített mentés
    vagy rövid gépi írás alatt kilépve a mentés így nem marad ki (és nem íródik miatta hiba-nyom)."""
    return float(cfg.section("mentes").get("kilepes_turelem_mp", 20))


def kilepeskor(cfg, idokeret: float | None = None) -> list[Path]:
    """A core rendezett leállásakor (H2): mentés, ha a HEAD változott. A kör-zár alatt, legfeljebb `kilepes_turelem_mp`
    várakozással; hiba (pl. a belső lemez nem írható) a `mentes-hiba.json`-ba és a stderr-re megy, a kilépést nem
    akasztja. `idokeret` (K44, a második ⌘Q ágán): a mentés szálban fut, és a hívó legfeljebb ennyit vár rá; az időkeret
    lejártakor a félkész bundle nem marad `.bundle`-ként (csak sikeres `os.replace` után létezik), a `.bundle.tmp` és a
    `mos-allapot-*.tmp` a következő mentésnél takarítódik."""
    if idokeret is None:
        return _kilepeskor(cfg)
    eredmeny: list[list[Path]] = []
    szal = threading.Thread(target=lambda: eredmeny.append(_kilepeskor(cfg)), name="kilepesi-mentes", daemon=True)
    szal.start()
    szal.join(idokeret)
    if szal.is_alive():
        _naplo_stderr(f"[mentés] a kilépési mentés nem fért az időkeretbe ({idokeret:g} s): a következő rendes mentésre marad")
        return []
    return eredmeny[0] if eredmeny else []


def _kilepeskor(cfg) -> list[Path]:
    hibak: dict[str, str] = {}
    try:
        with frame.run_lock(cfg, wait=False, turelem_mp=kilepes_turelem_mp(cfg)):
            # T022: a 2.0-n kívül szerkesztett (Obsidian, Finder), még nem rögzített változások egy idempotens kézi
            # commitba — enélkül a bundle a vault tényleges szövegét nem vinné
            for name, repo in frame.live_repos(cfg).items():
                try:
                    if not probaklon(repo):
                        repo.commit("kézi változások kilépéskor", {"Mos-Forras": "kezi"})
                except snapshot.SnapshotError as e:
                    hibak[name] = f"a kézi változások rögzítése nem sikerült: {e}"
                    _naplo_stderr(f"[mentés] {name}: {hibak[name]}")
            ki = ment(cfg, csak_ha_valtozott=True, log=_naplo_stderr, hibak=hibak)
    except frame.Busy:
        hibak["mentes"] = (f"kilépéskor kimaradt: egy kör {kilepes_turelem_mp(cfg):g} s várakozás után is fogta a "
                           "kör-zárat")
        _naplo_stderr(f"[mentés] {hibak['mentes']}")
        ki = []
    except OSError as e:
        hibak["mentes"] = f"kilépéskor nem sikerült: {e}"
        _naplo_stderr(f"[mentés] {hibak['mentes']}")
        ki = []
    hiba_ir(cfg, hibak)
    return ki


class Utemezo:
    """Az időzített belső lemezes mentés (34. döntés): minden gépi kör (vault-író feladat) végén (`kor_vege`) és
    tétlenségben `[mentes].ido_perc` percenként (alapból 30) egy `ment(csak_ha_valtozott=True)`, a kör-zár alatt,
    várakozás nélkül (foglaltnál 30 s múlva újra). Az állapotmásolat ebből legfeljebb `allapot_ido_perc`-enként (alap 60)
    kerül bele — az élő SQLite és a WAL mtime-ja szinte mindig „változott”, a gyakori másolat a régebbi állapotot gyorsan
    kiforgatná —, a többi lépés csak bundle. Aktív használat közben nem fut (2. döntés: az automatika tétlenségben
    dolgozik); a lépése a `tick()`, amelyet a háttérszál másodpercenként hív (a tesztek közvetlenül, hamis órával)."""

    FOGLALT_UJRA_MP = 30.0

    def __init__(self, cfg, aktivitas=None, ido_perc: float | None = None, ora=time.monotonic, log=_naplo_stderr):
        self.cfg, self.aktivitas, self.ora, self.log = cfg, aktivitas, ora, log
        perc = cfg.section("mentes").get("ido_perc", 30) if ido_perc is None else ido_perc
        self.ido_mp = float(perc) * 60
        self.allapot_mp = allapot_ido_mp(cfg)
        self._allapot_utolso: float | None = None        # az időzítő utolsó állapotmásolata (None: még nem volt)
        self._kov = self.ora() + self.ido_mp
        self._kor_jel = threading.Event()
        self._leall = threading.Event()
        self._szal: threading.Thread | None = None
        self.futasok = 0

    def kor_vege(self) -> None:
        """Egy gépi kör véget ért: a következő tétlen pillanatban mentés (ha a HEAD változott)."""
        self._kor_jel.set()

    def tick(self) -> bool:
        """Egy ütemezési lépés. → igaz, ha a mentés most lefutott."""
        most = self.ora()
        if not (self._kor_jel.is_set() or most >= self._kov):
            return False
        if self.aktivitas is not None and self.aktivitas.allapot() == "aktiv":
            return False                                # tétlenségben mentünk: a jel megmarad, a lépés később jön
        self._kor_jel.clear()
        hibak: dict[str, str] = {}
        allapot = self._allapot_utolso is None or most - self._allapot_utolso >= self.allapot_mp
        try:
            with frame.run_lock(self.cfg, wait=False):
                ment(self.cfg, csak_ha_valtozott=True, log=self.log, hibak=hibak, allapot=allapot)
            if allapot:
                self._allapot_utolso = most
        except frame.Busy:
            self._kov = most + self.FOGLALT_UJRA_MP     # egy kör/írás fogja a zárat: hamarosan újra
            self._kor_jel.set()
            return False
        except OSError as e:
            hibak["mentes"] = f"időzített mentés: {e}"
        hiba_ir(self.cfg, hibak)
        self._kov = most + self.ido_mp
        self.futasok += 1
        return True

    def indit(self) -> None:
        if self._szal is not None:
            return

        def fut() -> None:
            while not self._leall.wait(1.0):
                try:
                    self.tick()
                except Exception as e:  # noqa: BLE001 — az ütemező nem halhat meg egy hibától
                    self.log(f"[mentés] az időzített mentés hibája: {e}")
        self._szal = threading.Thread(target=fut, name="mentes-utemezo", daemon=True)
        self._szal.start()

    def leallit(self) -> None:
        self._leall.set()
        if self._szal is not None:
            self._szal.join(5)
            self._szal = None
