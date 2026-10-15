"""A kézi szkriptek közös elkülönítő segédje (C29.5, T011/T010, 2. audit): `import _kornyezet` (a szkript mappájából).

Minden kézi szkript, amely core-t, appot vagy indexet indít, ezen át állítja össze a gyermek környezetét. Az 1. audit óta
mindegyik maga írta a saját `MOS_*` listáját, és mindegyik kihagyott valamit (a `MOS_STATE`-et, a `MOS_SZEMELYES`-t, a
`MOS_BACKUP`-ot, a ytdlp-t, a naptár-segédet): a klónos próba a valódi `~/Manifold-backup` bundle-jait forgathatta, a valódi
`pos.sqlite`-ot írhatta. Szabály: **egyetlen `[utak]` kulcs sem marad valódi**, kivéve az engedélyezőlistát
(`VALODI_MARAD`: az eszköztár és a csak olvasott helyek); a kulcslista az `os.toml`-ból jön, így egy új kulcs (C27
`szemelyes`, C29 `naptar_seged`) nem maradhat ki. Az AST-őr: `tests/test_kezi_kornyezet.py`.

    probamappa(cfg, "c14-canvas")                         → {tmp}/c14-canvas-<idő>/ (+ `.mos-proba.json` jelölő)
    elkulonit(d, cfg, vault=klon, vault_git=git, home=True) → a gyermek env-je (dict)
    cfg_elkulonitve(d, cfg)                               → `config.load(elkulonit(...))` folyamaton belüli használathoz
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from core.modell import beallitas  # noqa: E402

# A kézi próbák core-jának API-titka (35. döntés, T071): rögzített, hogy a szkriptek a fejlécet és a Browser-pane URL töredékét
# (`#titok=…`) ismerjék; az `elkulonit` a gyermek-környezetbe írja, a `cfg_elkulonitve` a folyamatba is (in-process core).
TITOK = "kezi-proba-titok-9f2c1d7a5b3e8046"

JELOLO = ".mos-proba.json"          # a doctor (`_proba_klonok`) ezt keresi a `{tmp}/*/` alatt

# Ami valódi marad: az eszköztár (a Python, a runtime, a modellek gyorsítótára) és a csak olvasott helyek. A `vault`
# külön eset (klón vagy a valódi, csak olvasva), a pillanatkép-tároló sosem a valódi.
# `sandbox_exec`, `llvm`, `sdk`: csak olvasott eszköztár (a CAS- és a C++-homokozó nélkülük a klón-appban nem fut);
# `hej_cli`: a héj futtathatója a `--kuka` módhoz — a bináris csak olvasott, a vault-védelem a core-ban (`csatolmany.kukaba`,
# a klón gyökerére) és a segédben (`Kuka.swift`: csak a megadott gyökér alatti elem) marad, tehát a valódi vaulthoz nem ér.
VALODI_MARAD = frozenset({"work", "modulok", "runtime", "var", "venv", "models", "app_dist", "ffmpeg", "node",
                          "sandbox_exec", "llvm", "sdk", "hej_cli"})

# Az elkülönített kulcsok neve a próbamappában (ami nincs itt: a kulcs neve)
ALAPNEV = {
    "felulet": "felulet.json", "feladatok_db": "feladatok.sqlite", "router_db": "router.sqlite",
    "tanulas_db": "tanulas.sqlite", "automatika_db": "automatika.sqlite",
    "vault_kepek": "kepek", "naptar_seged": "nincs-naptar-seged", "ytdlp": "nincs-ytdlp", "ytdlp_git": "nincs-ytdlp.git",
    "binaris_naplo": "binaris-naplo.jsonl",
}
FAJL = frozenset({"felulet", "feladatok_db", "router_db", "tanulas_db", "automatika_db", "naptar_seged", "binaris_naplo"})   # fájl: csak a szülőmappája jön létre
NEM_LETEZO = frozenset({"ytdlp", "ytdlp_git", "naptar_seged"})                # szándékosan nincs: a klónban semmi nem élhet


def munkafa_forras(env: dict[str, str]) -> dict[str, str]:
    """Munkafa-módban (git worktree: a `.git` fájl) a klónos próbák FORRÁSA a fő checkout vaultja és `vault.git`-je (csak
    olvasva; a próba maga klónoz): a munkafának nincs saját vaultja (C33, `bin/mos kapu`). A hívó által megadott kulcs
    marad. Nem munkafában változatlan."""
    ki = dict(env)
    if not (REPO / ".git").is_file():
        return ki
    try:
        p = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO, capture_output=True,
                           text=True, timeout=20, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return ki
    if p.returncode != 0 or not p.stdout.strip():
        return ki
    fo = Path(p.stdout.strip()).parent
    if fo == REPO:
        return ki
    ki.setdefault("MOS_VAULT", str((fo / ".." / "Manifold").resolve()))
    ki.setdefault("MOS_VAULT_GIT", str(fo / "var" / "vault.git"))
    legacy = (fo / ".." / "Manifold-OS legacy" / "Legacy").resolve()
    if legacy.is_dir():
        ki.setdefault("MOS_LEGACY", str(legacy))
    return ki


def probamappa(cfg, elotag: str, *, megtart: bool = False, szkript: str | None = None) -> Path:
    """A próba mappája a `{tmp}` alatt, a jelölővel (szkript, pid, idő, megtartják-e): a doctor ebből tudja, mi maradt
    árván, és ki hagyta ott."""
    d = cfg.path("tmp") / time.strftime(f"{elotag}-%Y%m%d-%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    (d / JELOLO).write_text(json.dumps({
        "szkript": szkript or Path(sys.argv[0]).name, "pid": os.getpid(),
        "letrehozva": time.strftime("%Y-%m-%dT%H:%M:%S"), "megtart": bool(megtart)}, ensure_ascii=False), encoding="utf-8")
    return d


def valodi_modell_zar(cfg, alap: dict | None = None) -> Path:
    """A gépszintű modellzár útja a hívó (valódi) configjából — a klón workere ugyanezt tartja (L23): külön
    `{state}/modell.lock` mellett a próba és az éles két modellt tölthetne be egyszerre (T010)."""
    return beallitas.betolt(cfg, dict(os.environ if alap is None else alap)).zar


def _kulcsok(cfg) -> list[str]:
    return list(cfg.data.get("utak", {}))


def elkulonit(proba: Path, cfg, *, vault: Path | None = None, vault_git: Path | None = None, home: bool = False,
              masolat: tuple[str, ...] = (), valodi_naptar: bool = False, alap: dict | None = None) -> dict[str, str]:
    """A gyermek környezete: minden `[utak]` kulcs a `proba` alá (kivéve a `VALODI_MARAD`-ot), a `vault` és a
    `vault_git` a megadott klón (vault nélkül a valódi vault, csak olvasásra; a pillanatkép-tároló ilyenkor nem létező
    út, hogy ne éljen), a naptár-segéd nem létező út (a valódi EventKit-hez a próba csak a kifejezett `valodi_naptar`
    kapcsolóval nyúl, és akkor is egy `MOS_CONFIG`-másolatban külön `[emlekezteto] lista` kell: K35), a modellzár a
    valódi. `home`: ál-HOME a `proba/home` alatt (csak core-indításnál; a `Manifold.app` valódi HOME-ot kér: WebKit,
    engedélyek). `masolat`: kulcsok, amelyek a valódi fájlból/mappából induló másolatot kapnak (pl. `router_db`: a
    D9-kapu paritása). `cfg`: a HÍVÓ valódi configja (a kulcslista és a modellzár innen); `alap`: a kiinduló
    környezet (alap: `os.environ`)."""
    proba = Path(proba)
    env = dict(os.environ if alap is None else alap)
    kulcsok = _kulcsok(cfg)
    zar = valodi_modell_zar(cfg, env)
    for k in kulcsok:
        if k not in VALODI_MARAD:
            env.pop(f"MOS_{k.upper()}", None)               # a hívó shellének felülírása se szivároghat át
    for k in kulcsok:
        if k in VALODI_MARAD:
            continue
        if k == "vault":
            ut = Path(vault) if vault is not None else cfg.path("vault")
        elif k == "vault_git":
            ut = Path(vault_git) if vault_git is not None else proba / "nincs-vault.git"
        elif k == "naptar_seged" and valodi_naptar:
            ut = cfg.path("naptar_seged")
        else:
            ut = proba / ALAPNEV.get(k, k)
        env[f"MOS_{k.upper()}"] = str(ut)
        if k in ("vault", "vault_git") or k in NEM_LETEZO:
            continue
        (ut.parent if k in FAJL else ut).mkdir(parents=True, exist_ok=True)     # a mappák, amelyekbe a gyermek elsőként ír
    for k in masolat:
        if k not in kulcsok or k in VALODI_MARAD or k in ("vault", "vault_git"):
            raise ValueError(f"nem másolható kulcs: {k}")
        forras, cel = cfg.path(k), Path(env[f"MOS_{k.upper()}"])
        if forras.is_dir():
            shutil.copytree(forras, cel, dirs_exist_ok=True)
        elif forras.is_file():
            cel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(forras, cel)
    env["MANIFOLD_MODELL_ZAR"] = str(zar)
    env["MOS_API_TITOK"] = TITOK
    if home:
        (proba / "home").mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(proba / "home")
    ellenoriz(env, proba, cfg, valodi_naptar=valodi_naptar, vault=vault)
    return env


def ellenoriz(env: dict, proba: Path, cfg, valodi_naptar: bool = False, vault: Path | None = None) -> None:
    """Önellenőrzés: a `config.load(env)` minden útja a próbamappában van, az engedélyezőlistán (a hívó valódi
    útjával azonosan), vagy a vault (valódi csak olvasásra, vagy klón). Különben `AssertionError`."""
    proba = Path(proba)
    kcfg = config.load(env)
    rossz = []
    for k in _kulcsok(cfg):
        ut = kcfg.path(k)
        if k in VALODI_MARAD:
            if ut != cfg.path(k):
                rossz.append(f"{k}: {ut} ≠ a hívó útja {cfg.path(k)}")
        elif k == "vault":
            if ut not in (cfg.path("vault"), Path(vault) if vault is not None else None) and proba not in ut.parents:
                rossz.append(f"{k}: {ut}")
        elif k == "naptar_seged" and valodi_naptar:
            if ut != cfg.path(k):
                rossz.append(f"{k}: {ut} ≠ a hívó útja {cfg.path(k)}")
        elif proba not in ut.parents:
            rossz.append(f"{k}: {ut}")
    if rossz:
        raise AssertionError("az elkülönítés lyukas, ezek az utak a próbamappán kívül vannak: " + "; ".join(rossz))


# A héj ablakának címsora ezen a változón át jelzi a próbát („PRÓBA — Manifold (klón)”, shell/Sources/AppController.swift
# `ablakCim`); a `proba_app.py app` állítja. Nem `[utak]` kulcs: a klónos és a valódi példány összekeverése ellen jelöl.
PROBA_JELZES = "MOS_PROBA_JELZES"


def valodi_core_fut(cfg) -> bool:
    """A hívó (valódi) configjának `{run}/core.lock`-ja foglalt-e: egy másik Manifold-példány éppen a valódi vaulton dolgozik.
    A zárat nem veszi el, és fájlt nem hoz létre."""
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
        pass
    return False


def proba_figyelmeztetesek(env: dict[str, str], cfg) -> list[str]:
    """C34 (NAPLO „Ötletek”, Kézi kör F5–F6): figyelmeztetések a próbaindítás előtt. (1) A gyermek környezetének bármely
    elkülönítendő útja a VALÓDIRA mutat (a hívó configjának útja, vagy a home alatti valódi `Manifold-backup`) — az
    `ellenoriz` a próbamappán kívüli utat hibának veszi, ez a második, emberi olvasatú védvonal. (2) Már fut egy másik
    Manifold-példány a valódi vaulton (a két példány egymás mentetlen állapotát nem látja). Üres lista: nincs gond."""
    figy = []
    kcfg = config.load(env)
    valodi_otthoni_mentes = os.path.realpath(Path(os.path.expanduser("~")) / "Manifold-backup")
    for k in _kulcsok(cfg):
        if k in VALODI_MARAD:
            continue
        ut = os.path.realpath(kcfg.path(k))
        if k == "naptar_seged":
            continue                           # a próba a valódi segédet csak kifejezett kapcsolóval éri el (K35)
        if ut == os.path.realpath(cfg.path(k)) or (k == "backup" and ut == valodi_otthoni_mentes):
            figy.append(f"a próba a VALÓDI {k} útjára mutat: {ut} — a gépelt szöveg vagy a mentés a valódit érheti")
    if valodi_core_fut(cfg):
        figy.append("a valódi vaulton már fut egy Manifold-példány (core.lock foglalt): két példány egymás mentetlen állapotát "
                    "nem látja — a próbaablak címsora „PRÓBA”, ne a másik ablakba gépelj")
    return figy


def gyermek_pidek(pid: int) -> list[int]:
    """A `pid` közvetlen gyermekei (a héj core-ja): a leállítás előtt kell megfogni, utána már a launchd-é."""
    try:
        ki = subprocess.run(["/bin/ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(a) for a, b in (r.split() for r in ki.splitlines() if len(r.split()) == 2) if int(b) == pid]


def megvar_kilepest(pidek: list[int], mp: float = 90.0) -> bool:
    """Megvárja, hogy a megadott folyamatok kilépjenek (a core rendezett leállása: lezáró mentés, belső lemezes bundle a
    `{backup}` alá). A próbamappa törlése ELŐTT kell: különben a core a törölt mappa helyére írja újra a `kor.lock`-ot és a
    kódtár-bundle-t (C11a/C13 mérések ~12 MB-os maradéka). Igaz, ha mind kilépett."""
    vege = time.time() + mp
    elo = [p for p in pidek]
    while elo and time.time() < vege:
        elo = [p for p in elo if _el(p)]
        if elo:
            time.sleep(0.25)
    return not elo


def _el(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cfg_masik_var(env: dict[str, str], var: Path):
    """A `env` configja, de a `{var}` (és a belőle számolt állapotutak) a `var`-ra mutat: CSAK OLVASÁSRA, pl. a fő checkout
    `var/`-ja munkafából (a belső mentés elvárt állapotfájl-listája). Írni vele nem szabad; az ideiglenes fájlok más configé."""
    return config.load({**env, "MOS_VAR": str(var)})


def cfg_elkulonitve(proba: Path, cfg, **kw):
    """Folyamaton belüli használathoz (index-mérés, `server.start`): `config.load(elkulonit(...))`. Az in-process core az
    API-titkát a folyamat környezetéből veszi: ide is beírjuk (a próbák a fejlécben a `TITOK`-ot küldik)."""
    os.environ["MOS_API_TITOK"] = TITOK
    return config.load(elkulonit(proba, cfg, **kw))


def vitest_idokorlat_ms(elemszam: int, per_elem_ms: int, alap_ms: int = 120_000) -> int:
    """A kézi vitest időkorlátja a feladat méretéhez igazítva (T084): a `vitest.kezi.config.ts` a
    `MOS_KEZI_IDOKORLAT_MS`-ből veszi; a hívó `subprocess.run(timeout=…)`-ja ennél egy perccel hosszabb."""
    return int(alap_ms + max(0, elemszam) * per_elem_ms)


NODE = REPO / "runtime" / "node" / "bin" / "node"


def vitest_futtat(szkript: str, env_extra: dict[str, str], elemszam: int, per_elem_ms: int,
                  alap_ms: int = 120_000) -> subprocess.CompletedProcess:
    """Egy `app/tests/kezi/*.kezi.ts` futtatása a `vitest.kezi.config.ts`-sel, a mérethez igazított időkorláttal
    (T084). Időtúllépésnél 124-es kilépési kódú eredményt ad (a hívók a `returncode`-ot nézik)."""
    ido_ms = vitest_idokorlat_ms(elemszam, per_elem_ms, alap_ms)
    env = dict(os.environ, CI="1", PATH=f"{NODE.parent}:/usr/bin:/bin", MOS_KEZI_IDOKORLAT_MS=str(ido_ms), MOS_API_TITOK=TITOK,
               **env_extra)         # a Node-próba a core-hoz a `MOS_API_TITOK`-kal hitelesít (`lib/core/titok.ts`)
    try:
        return subprocess.run([str(NODE), "node_modules/vitest/vitest.mjs", "run", "--config", "vitest.kezi.config.ts",
                               szkript], cwd=REPO / "app", env=env, capture_output=True, text=True,
                              timeout=ido_ms / 1000 + 60)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(e.cmd, 124, "", f"a vitest {ido_ms / 1000 + 60:.0f} s után időtúllépést kapott")


def md_db(vault: Path) -> int:
    """A vault Markdown-fájljainak száma (a vitest-időkorlát mérethez igazításához; `.obsidian`/`.git` nélkül)."""
    db = 0
    for _, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if m not in (".obsidian", ".git")]
        db += sum(1 for n in fajlok if n.endswith(".md"))
    return db
