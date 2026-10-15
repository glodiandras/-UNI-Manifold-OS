"""Doctor: jelzi, ha bármi a rendszer-Pythonra, a ~/Applications-re, a ~/.cache-re vagy a legacy var/-ra mutat.

Csak a standard könyvtárat használja, így a venv nélkül is fut. Kilépési kód: 0 zöld, 1 piros.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config

OK, HIBA, INFO, FIGYELEM = "ok", "hiba", "info", "figyelem"
TILTOTT_PYTHON = ("/Library/Frameworks/Python.framework", "/usr/bin/", "/opt/homebrew", "/usr/local")
LEGACY_MINTA = re.compile(r"Manifold-OS legacy|/Volumes/[^/\s\"']+/Manifold-OS/(?!v2)")
SAJAT_MINTA = re.compile(r"~/Applications|/Applications/Manifold|/\.cache\b|~/\.cache|Library/Caches|\$HOME/\.cache")
SZOVEG_KITERJESZTES = {"", ".toml", ".env", ".sh", ".py", ".swift", ".plist", ".json", ".txt", ".cfg", ".lock", ".md"}
KIHAGY_MAPPAK = {"docs", "archive", "tests", "runtime", "var", "node_modules", ".git", ".claude", "__pycache__", "staging"}
# A gyökér alatti minden rejtett mappa (`.claude/worktrees`, `.git`, `.venv`…) kimarad: a saját forrás nem ott van, és a
# párhuzamos munkafák bejárása lassú, a bennük levő (más ágon álló) fájlok pedig hamis „legacy var/” találatot adnak.
KIHAGY_FAJLOK = {"CLAUDE.md", "doctor.py", "utnorm.py"}      # a minták saját forrásukban nem számítanak (az utnorm a régi utak alakjait ismeri fel)
ENV_UTAS = ("UV_", "PIP_", "XDG_", "HF_", "TMPDIR", "MOS_", "PYTHON", "TRANSFORMERS_")


@dataclass
class Eredmeny:
    allapot: str
    nev: str
    uzenet: str


def _szoveges(p: Path) -> str | None:
    try:
        if p.stat().st_size > 2_000_000:
            return None
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _kod(szoveg: str) -> str:
    """A megjegyzéssorok nélküli szöveg: a leírásban említett minta nem használat."""
    sorok = (s for s in szoveg.split("\n") if not s.lstrip().startswith(("#", "//")))
    return "\n".join(re.sub(r"\s+(//|#)\s.*$", "", s) for s in sorok)


def _sajat_fajlok(root: Path):
    for d, almappak, fajlok in os.walk(root):
        almappak[:] = [a for a in almappak if a not in KIHAGY_MAPPAK and not a.startswith(".") and not a.endswith(".app")]
        for f in fajlok:
            p = Path(d) / f
            if f in KIHAGY_FAJLOK or p.suffix not in SZOVEG_KITERJESZTES or p.name.startswith("."):
                continue
            yield p


def _sema_ellenor(cfg) -> tuple[str, str]:
    """A `[sema] vault` (C11b, T162): a kulcs megvan, a fájl a legacyn kívül áll, és olvasható JSON-objektum a kötelező
    `mezosorrend` listával. A doctor importmentes (a venv nélkül is fut), ezért csak a `json`-nal olvas."""
    try:
        nyers = cfg.section("sema").get("vault")
    except Exception as e:  # noqa: BLE001 — a hibás config is jelzés, nem összeomlás
        return HIBA, f"a [sema] szakasz nem olvasható: {e}"
    if not nyers:
        return HIBA, "a config/os.toml [sema] vault kulcsa hiányzik (C11b)"
    try:
        ut = Path(cfg.expand(nyers))
    except Exception as e:  # noqa: BLE001
        return HIBA, f"a [sema] vault nem oldható fel: {e}"
    if LEGACY_MINTA.search(str(ut)):
        return HIBA, f"a [sema] vault a legacyre mutat: {ut} (a 2.0 saját másolata: config/vault-sema.json)"
    if not ut.is_file():
        return HIBA, f"nincs vault-séma: {ut}"
    try:
        adat = json.loads(ut.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return HIBA, f"a vault-séma nem olvasható JSON: {ut.name}: {e}"
    if not isinstance(adat, dict) or not isinstance(adat.get("mezosorrend"), list):
        return HIBA, f"a vault-séma szerkezete hibás (nincs `mezosorrend` lista): {ut.name}"
    return OK, f"{ut.name}: {len(adat['mezosorrend'])} mező, {len(adat.get('kivetel_osztalyok') or [])} kivételosztály"


def _fentiek(sorok: list[str]) -> str:
    return "; ".join(sorok[:4]) + (f" (+{len(sorok) - 4})" if len(sorok) > 4 else "")


def _tarolok(cfg: config.Config) -> list[tuple[str, Path]]:
    """A config pillanatkép-tárolói (név, git-könyvtár), amelyeknek van HEAD-je — import nélkül (a doctor a venv
    nélkül is fut)."""
    out = []
    for name, sec in cfg.section("pillanat").items():
        g = Path(cfg.expand(sec["git_dir"]))
        if (g / "HEAD").is_file():
            out.append((name, g))
    return out


def _mentes(cfg: config.Config, add) -> None:
    """H2, T022, T023, 33. döntés: a belső lemezes mentés állapota — a tárolók bundle-je (a HEAD benne van-e, és van-e a
    2.0-n kívül szerkesztett, nem rögzített változás), a kódtár bundle-je, az állapotmásolat, és a legutóbbi mentés
    hibája (a HIBÁS mentés más, mint a „változott”). Csak olvas (`GIT_OPTIONAL_LOCKS=0`)."""
    import datetime as dt
    from . import mentes, snapshot
    backup = cfg.path("backup")
    volt = False
    for name, repo in snapshot.repos(cfg).items():
        if not repo.exists():
            continue
        volt = True
        nev = "mentés" if name == "vault" else f"mentés ({name})"
        b = mentes.legujabb(repo, backup)
        mikor = dt.datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if b else ""
        if mentes.friss(repo, backup, dirty=False):
            nincs_rogzitve = mentes.nem_rogzitett(repo)
            if nincs_rogzitve:
                add(FIGYELEM, nev, f"{name}: a legutóbbi mentés ({mikor or 'nincs mit menteni'}) tartalmazza a HEAD-et, de "
                                   f"{len(nincs_rogzitve)} nem rögzített változás van ({_fentiek(nincs_rogzitve)}) — a 2.0-n "
                                   "kívül szerkesztve; a kilépéskor rögzítődnek és a bundle-be kerülnek")
            else:
                add(OK, nev, f"{name}: a legutóbbi mentés ({mikor or 'nincs mit menteni'}) tartalmazza a HEAD-et — {backup}")
        elif b is None:
            add(FIGYELEM, nev, f"{name}: még nincs mentés a {backup} alatt; a következő kilépéskor készül")
        else:
            add(FIGYELEM, nev, f"{name}: a legutóbbi mentés ({mikor}) régebbi a HEAD-nél; a következő kilépéskor "
                "frissül (kézzel: bin/mos exec var/venv/bin/python -B -m core backup)")
    if not volt:
        add(INFO, "mentés", f"{backup} — megengedett kivétel (a belső lemezen); még nincs pillanatkép-tároló")
    kodtar = mentes.kodtar_friss(cfg, backup)
    if kodtar is not None:
        add(OK if kodtar else FIGYELEM, "mentés (kódtár)",
            f"a 2.0 kódtárának legutóbbi bundle-je friss — {backup}" if kodtar else
            "a kódtár legutóbbi bundle-je régebbi a refeknél (vagy nincs); a következő kilépéskor frissül")
    allapot = mentes.allapot_rendben(cfg, backup)
    if allapot is not None:
        add(OK if allapot else FIGYELEM, "mentés (állapot)",
            "az állapotfájlok (SQLite-ok, state JSON/JSONL, füzet- és videóállapot) legutóbbi másolata friss vagy "
            f"legfeljebb {2 * mentes.allapot_ido_mp(cfg) / 60:g} perces" if allapot else
            "az állapotfájlok másolata régebbi a forrásnál (vagy nincs); a következő kilépéskor frissül")
    hiba = mentes.hiba_olvas(cfg)
    if hiba:
        add(FIGYELEM, "mentés hiba", f"a legutóbbi belső lemezes mentés HIBÁS volt ({hiba.get('ido', '?')}): "
                                     f"{mentes.hiba_szoveg(hiba)} — ez más, mint a „változott” állapot (a sikeres mentés törli)")


def _vault(cfg: config.Config, environment: dict[str, str], add) -> None:
    """T105: a beállított vault megvan-e (az SSD csatlakoztatva?), és hány jegyzet van benne. A munkafa-módban
    (`MOS_MUNKAFA`) a vault nem a munkafa mellett él: INFO, a valódi vaultot a fő checkoutban kell ellenőrizni."""
    from .index.feloldas import SKIP_DIRS
    vault = cfg.path("vault")
    if not vault.is_dir():
        if environment.get("MOS_MUNKAFA"):
            add(INFO, "vault", f"munkafa-mód: nincs vault a munkafa mellett ({vault}); a valódi vaultot a fő checkoutban "
                               "ellenőrizd (bin/mos doctor)")
        else:
            add(HIBA, "vault", f"nincs vault: {vault} — csatlakoztatva az SSD?")
        return
    if not (vault / ".obsidian").is_dir():
        add(FIGYELEM, "vault", f"{vault} létezik, de nincs .obsidian mappája: nem valódi vault (a core nem ír bele)")
        return
    from .frame import TMP_MINTA
    jegyzet, tmp = 0, []
    for dp, almappak, fajlok in os.walk(vault):
        almappak[:] = [a for a in almappak if a not in SKIP_DIRS and not a.startswith(".")]
        jegyzet += sum(1 for f in fajlok if f.endswith(".md") and not f.startswith("."))
        tmp += [os.path.relpath(os.path.join(dp, f), vault) for f in fajlok if TMP_MINTA.match(f)]
    add(OK, "vault", f"{vault} — {jegyzet} jegyzet")
    if (vault / ".gitattributes").exists():
        add(FIGYELEM, "vault .gitattributes", f"a vault gyökerében van .gitattributes ({vault / '.gitattributes'}): a pillanatkép-tároló "
                                              "info/attributes-e felülírja (T099), de más git-eszköz (Obsidian Git, kézi git) látja — "
                                              "egy `filter=lfs` sor megállíthatná azokat")
    if tmp:
        add(FIGYELEM, "vault ideiglenes fájlok", f"{len(tmp)} megszakadt mentésből maradt .manifold-tmp fájl a vaultban "
                                                 f"({_fentiek(tmp)}); a core következő indulása törli")


def _tarolok_allapota(cfg: config.Config, add) -> None:
    """T024: ha a tároló munkafája él, a pillanatkép-tárolónak is élnie kell (visszavonás, előzmény, bundle nélküle
    nincs), a `core.worktree` a munkafára mutat, és az `info/exclude` a configból generált. A vaultnál HIBA; más
    tárolónál (a ytdlp munkafája a C20-ig hiányzik) csak az a baj, ha a munkafa megvan, a tároló nincs."""
    from . import snapshot
    for name, repo in snapshot.repos(cfg).items():
        felirat = f"pillanatkép ({name})"
        sulyos = HIBA if name == "vault" else FIGYELEM
        if not repo.work_tree.is_dir():
            continue
        if not (repo.git_dir / "HEAD").is_file():
            add(sulyos, felirat, f"a munkafa ({repo.work_tree}) megvan, de a pillanatkép-tároló ({repo.git_dir}) nem: nincs "
                                 "visszavonás, előzmény és belső lemezes mentés (a szerkesztő mentése pillanatkép nélkül megy)")
            continue
        hibak = []
        cfgszoveg = _szoveges(repo.git_dir / "config") or ""
        m = re.search(r"worktree\s*=\s*(.+)", cfgszoveg)
        if not m or os.path.realpath(m.group(1).strip()) != os.path.realpath(repo.work_tree):
            hibak.append(f"core.worktree = {m.group(1).strip() if m else '(nincs)'} (várt: {repo.work_tree})")
        if _szoveges(repo.git_dir / "info" / "exclude") != repo.exclude_szoveg():
            hibak.append("az info/exclude eltér a config/os.toml `kizar` listájából generálttól (a kizárt fájlok bekerülhetnek "
                         "a pillanatképbe; újragenerálás: a core indulása)")
        if _szoveges(repo.git_dir / "info" / "attributes") != snapshot.INFO_ATTRIBUTES:
            hibak.append("az info/attributes nem a zárt git-környezet (`* -filter -merge -text -ident`): a vault "
                         ".gitattributes-e hathat a pillanatképre (a core következő indulása beírja; T099)")
        if not re.search(r"hookspath\s*=\s*/dev/null", cfgszoveg, re.IGNORECASE):
            hibak.append("a core.hooksPath nem /dev/null: egy hook megállíthatná a pillanatképet (a core következő indulása beírja)")
        if hibak:
            add(sulyos, felirat, "; ".join(hibak))
        else:
            add(OK, felirat, f"{repo.git_dir} rendben")


def _tarolt_binaris(cfg: config.Config, add) -> None:
    """T142 (C20a): bináris média vagy dokumentum a pillanatkép-tár HEAD-fájában. A vault szöveges tár (14. döntés): a
    médiát a visszavonás nem tudná visszahozni, a bundle-t pedig gigabájtokra duzzasztaná — FIGYELEM, a javítás
    (`git rm --cached`) a valódi tárolón a felhasználó jóváhagyásával megy. Az ytdlp tárban a követett kód csak INFO
    (a kódtár is követi; az ytdlp tár a staging szövegeit őrzi). Csak olvas."""
    from . import mediatipus, snapshot
    for name, repo in snapshot.repos(cfg).items():
        if not (repo.git_dir / "HEAD").is_file() or not repo.work_tree.is_dir():
            continue
        felirat = "pillanatkép bináris" if name == "vault" else f"pillanatkép bináris ({name})"
        try:
            if not repo.has_head():
                continue
            fa = repo.git("ls-tree", "-r", "--name-only", "-z", "HEAD", check=False).stdout
        except (OSError, snapshot.SnapshotError):
            continue
        utak = [u for u in fa.split("\0") if u]
        binaris = [u for u in utak if mediatipus.binaris_e(u)]
        if binaris:
            add(FIGYELEM, felirat, f"{len(binaris)} bináris fájl áll a(z) {name} tár HEAD-jében ({_fentiek(binaris)}): a média nem "
                                    "kerülhet a pillanatképbe (14. döntés); a kizárólista a core/mediatipus.py-ból jön")
        else:
            add(OK, felirat, f"a(z) {name} tár HEAD-jében nincs bináris fájl ({len(utak)} követett út)")
        if name == "ytdlp":
            kod = [u for u in utak if not u.startswith(("staging/", "archive/", "logs/"))]
            if kod:
                add(INFO, "pillanatkép kód (ytdlp)", f"az ytdlp tár {len(kod)} kód-/konfigfájlt is követ (a 2.0 kódtár is); a módosításuk "
                                                      "kézi változásként kerül az ytdlp tárba — KEZI-TEENDOK K94")


def _video_ffmpeg(cfg: config.Config, home: Path, add) -> None:
    """C20a (2. audit T055): a videólánc ffmpeg-je a `runtime/ffmpeg/ffmpeg` pinelt build legyen — a home-beli (`~/.local/bin`, egy törölt
    Save4K-alkalmazás symlinkje) és a rendszer-útvonali ffmpeg **tiltott**; a bináris sha256-ja egyezzen a `config/runtime-pins.env`
    `FFMPEG_BIN_SHA256`-jával. A hiány csak FIGYELEM (a videólánc nem indul, az app igen). Csak olvas."""
    import hashlib
    ff = cfg.path("ffmpeg")
    felold = os.path.realpath(ff)
    tiltott = [str(Path(home).resolve()) + os.sep, "/opt/homebrew/", "/usr/local/", "/usr/bin/"]
    if any(felold.startswith(t) for t in tiltott) and not felold.startswith(os.path.realpath(cfg.root) + os.sep):
        add(HIBA, "ffmpeg", f"tiltott hely: {felold} — a home-beli és a rendszer-ffmpeg nem használható (a pinelt build: runtime/ffmpeg/ffmpeg)")
        return
    if not (ff.is_file() and os.access(ff, os.X_OK)):
        add(FIGYELEM, "ffmpeg", f"hiányzik: {ff} — a videólánc nem indul (bin/mos runtime fetch ffmpeg)")
        return
    pins = _szoveges(cfg.root / "config" / "runtime-pins.env") or ""
    m = re.search(r"^FFMPEG_BIN_SHA256=(\S+)", pins, re.M)
    if not m:
        add(INFO, "ffmpeg", f"megvan: {ff} (nincs rögzített sha256 az összevetéshez)")
        return
    h = hashlib.sha256()
    with open(ff, "rb") as f:
        for blokk in iter(lambda: f.read(1 << 20), b""):
            h.update(blokk)
    if h.hexdigest() == m.group(1):
        add(OK, "ffmpeg", f"{ff} — a sha256 egyezik a rögzítettel")
    else:
        add(HIBA, "ffmpeg", f"a sha256 eltér a rögzítettől ({h.hexdigest()[:12]}… ≠ {m.group(1)[:12]}…): {ff}")


def _napi_canvas(root: Path, add) -> None:
    """29(a) döntés (C34, T187): a pdf.js opcionális natív `@napi-rs/canvas`-a nem települhet (a felület `useWasm: false`
    mellett fut; a CSP és az offline futás miatt a natív bináris nem kell). A gép így őrzi: az `app/node_modules/@napi-rs/
    canvas*` megléte HIBA. A `bin/mos app install` az `npm ci` után maga is eltávolítja. Csak olvas."""
    nm = root / "app" / "node_modules"
    if not nm.is_dir():
        add(INFO, "@napi-rs/canvas", "nincs app/node_modules (bin/mos app install); a 29(a) őr ott ellenőriz")
        return
    van = sorted(p.name for p in (nm / "@napi-rs").glob("canvas*")) if (nm / "@napi-rs").is_dir() else []
    if van:
        add(HIBA, "@napi-rs/canvas", f"a 29(a) döntés szerint nem települhet, de ott van: {', '.join('@napi-rs/' + n for n in van)} "
                                     "— a bin/mos app install eltávolítja (vagy töröld az app/node_modules/@napi-rs/canvas* mappákat)")
    else:
        add(OK, "@napi-rs/canvas", "nincs az app/node_modules alatt (29. döntés (a))")


def _pin_ertek(pins: str, kulcs: str) -> str | None:
    m = re.search(rf"^{kulcs}=(\S+)", pins, re.M)
    return m.group(1) if m else None


def _verzio_kimenet(parancs: list[str]) -> str | None:
    """A hordozható eszköz `--version` kimenetéből a `X.Y.Z` szám; nem futtatható / nem válaszol: None."""
    try:
        p = subprocess.run(parancs, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", p.stdout + p.stderr) if p.returncode == 0 else None
    return m.group(1) if m else None


def _runtime_verziok(cfg: config.Config, add, eszkoztar_kivul: bool) -> None:
    """C34 (T188): a `runtime/` uv-je, Pythonja és Nodeja a `config/runtime-pins.env` pinjével azonos verziójú-e. Pin-váltás után
    a `bin/mos runtime fetch` lecseréli őket (a régit a `runtime/regi/` alá teszi), a `runtime install` újraépíti a venv-et; a
    doctor azt jelzi, ha ez elmaradt. A nem futtatható (hiányzó) eszközt a `runtime` tétel már jelezte. Csak olvas."""
    runtime = cfg.path("runtime")
    pins = _szoveges(cfg.root / "config" / "runtime-pins.env") or ""
    eszkozok = (("uv", runtime / "uv", "UV_VERSION"), ("Python", runtime / "python" / "bin" / "python3", "PY_VERSION"),
                ("Node", runtime / "node" / "bin" / "node", "NODE_VERSION"))
    rendben, eltero = [], []
    for nev, ut, kulcs in eszkozok:
        varhato = _pin_ertek(pins, kulcs)
        if not varhato or not (ut.is_file() and os.access(ut, os.X_OK)):
            continue
        van = _verzio_kimenet([str(ut), "--version"])
        if van is None:
            eltero.append(f"{nev}: a --version nem olvasható")
        elif van != varhato:
            eltero.append(f"{nev} {van} ≠ pin {varhato}")
        else:
            rendben.append(f"{nev} {van}")
    if eltero:
        add(HIBA, "runtime verzió", f"{'; '.join(eltero)} — bin/mos runtime fetch, majd bin/mos runtime install")
    elif rendben:
        add(OK, "runtime verzió", f"{', '.join(rendben)} — egyezik a config/runtime-pins.env-vel")
    elif not eszkoztar_kivul:
        add(INFO, "runtime verzió", "nincs futtatható eszköz a runtime/ alatt: nincs mit összevetni")


def _kovetelmenyek(cfg: config.Config, add) -> None:
    """C34 (T188): a `config/requirements.in` (forrás) minden csomagja szerepel a `requirements.lock`-ban (a lockot ebből kell
    fordítani); a fájl hiánya HIBA — a forrás korábban a gitignore-olt `runtime/dl/` alatt élt."""
    szoveg = _szoveges(cfg.root / "config" / "requirements.in")
    lock = _szoveges(cfg.root / "config" / "requirements.lock")
    if szoveg is None:
        add(HIBA, "requirements.in", "hiányzik: config/requirements.in (a lock forrása; a runtime/dl alatt nem élhet)")
        return
    if lock is None:
        return                                      # a lock hiányát a `lock` tétel jelzi
    norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()  # noqa: E731
    lockban = {norm(m) for m in re.findall(r"^([A-Za-z0-9_.-]+)==", lock, re.M)}
    kellene = [m.group(1) for sor in szoveg.split("\n") if not sor.lstrip().startswith("#")
               and (m := re.match(r"\s*([A-Za-z0-9_.-]+)", sor))]
    hianyzik = sorted({n for n in kellene if norm(n) not in lockban})
    if hianyzik:
        add(HIBA, "requirements.in", f"nincs a lockban: {', '.join(hianyzik)} — fordítsd újra (uv pip compile config/requirements.in …)")
    else:
        add(OK, "requirements.in", f"{len(kellene)} csomag, mind a lockban")


def _never_index(var: Path, add) -> None:
    """L50 (C34, T190): a `var/.metadata_never_index` megléte (Spotlight-kizárás). A `bin/mos` minden indításkor létrehozza."""
    if not var.is_dir():
        return
    if (var / ".metadata_never_index").exists():
        add(OK, "Spotlight", "a var/ Spotlight-kizárt (.metadata_never_index)")
    else:
        add(FIGYELEM, "Spotlight", "hiányzik a var/.metadata_never_index (L50): a Spotlight indexelné a modelleket és az indexeket — "
                                   "a következő bin/mos hívás létrehozza")


APP_AZONOSITO = "local.manifold-os.app"
HOME_KIVETEL = "Library/Preferences/local.manifold-os.app.plist"
HOME_NEM_ENGEDETT = ("Library/Saved Application State", "Library/Caches", "Library/WebKit", "Library/HTTPStorages",
                     "Library/Application Support", "Library/Containers", "Library/Logs")


def _home_irasok(home: Path, add) -> None:
    """C34 (T189, K1-A2-hej-11): a héj a home alá nem ír — kivéve az AppKit/cfprefsd `~/Library/Preferences/local.manifold-os.
    app.plist`-jét (a natív helyi menü helyesírás-panelje ablakkeret-bejegyzéseket tesz bele), és a belső lemezes mentést
    (`~/Manifold-backup`). Az első megengedett kivétel (INFO); bármi más a héj azonosítójával (mentett ablakállapot,
    WebKit-tár, gyorsítótár) FIGYELEM. Csak olvas."""
    try:
        if (home / HOME_KIVETEL).is_file():
            add(INFO, "home írások", f"~/{HOME_KIVETEL} megengedett kivétel (AppKit ablakkeretek; a belső mentés, ~/Manifold-backup "
                                     "mellett az egyetlen hely, ahová a Manifold a home alá ír)")
        idegen = []
        for rel in HOME_NEM_ENGEDETT:
            d = home / rel
            if d.is_dir():
                idegen += [f"~/{rel}/{p.name}" for p in d.glob(f"{APP_AZONOSITO}*")]
        if idegen:
            add(FIGYELEM, "home írások", f"a héj azonosítójával a home alatt nem engedett fájl: {_fentiek(sorted(idegen))} "
                                         "(az ablak-visszaállítás és a nonPersistent WebKit-tár miatt nem jöhetne létre)")
    except OSError:
        pass


def alairas_tipus(codesign_kimenet: str) -> tuple[str, str]:
    """A `codesign -dv --verbose=2` kimenetéből: `("adhoc", "")` vagy `("identitas", "<leaf tanúsítvány neve>")`; ismeretlen:
    `("ismeretlen", "")`. Tiszta függvény (a doctor teszteli)."""
    if re.search(r"^Signature=adhoc\b", codesign_kimenet, re.M):
        return "adhoc", ""
    m = re.search(r"^Authority=(.+)$", codesign_kimenet, re.M)       # az első a levél-tanúsítvány
    if m:
        return "identitas", m.group(1).strip()
    return "ismeretlen", ""


def _alairas(app: Path, add) -> None:
    """C34: az app aláírásának fajtája. Az ad-hoc aláírás minden újrafordítással új kódazonosságot jelent, ezért a macOS a
    Naptár/Emlékeztetők/Eltávolítható kötetek engedélyeit újra kéri; a stabil (saját tanúsítványos) aláírás nem (docs/KIADAS.md)."""
    try:
        p = subprocess.run(["codesign", "-dv", "--verbose=2", str(app)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return
    fajta, nev = alairas_tipus(p.stdout + p.stderr)
    if fajta == "identitas":
        add(OK, "aláírás", f"stabil aláírás: {nev} — az engedélyek újrafordítás után is megmaradnak")
    elif fajta == "adhoc":
        add(INFO, "aláírás", "ad-hoc aláírás: minden újrafordítás után újra kérdez a macOS (Naptár, Emlékeztetők, kötet); "
                             "stabil aláírás: MOS_ALAIRAS_IDENTITAS, lépései a docs/KIADAS.md-ben")


def _git_fuggoseg(git: str | None, add) -> None:
    """C34: a pillanatkép, a visszavonás és a belső mentés a RENDSZER gitjére épül (nincs hordozható git a runtime/ alatt) — a
    függőség kimondva; a rendszer-git a macOS-en az Xcode Command Line Tools része. Hordozható git: docs/KIADAS.md (D3-lista)."""
    if not git:
        return
    if "runtime" in Path(os.path.realpath(git)).parts:
        add(OK, "git függőség", f"hordozható git a runtime/ alatt: {git}")
    else:
        add(INFO, "git függőség", f"rendszer-git ({git}; macOS: Xcode Command Line Tools) — a pillanatkép, a visszavonás és a "
                                  "belső mentés rá épül; hordozható git: docs/KIADAS.md")


def _core_fut(cfg: config.Config, add) -> None:
    """T027: a `core.lock` foglalt-e (fut a core). A zárat nem veszi el, és fájlt nem hoz létre."""
    zar = cfg.path("run") / "core.lock"
    if not zar.is_file():
        return
    try:
        with open(zar, "r") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                add(INFO, "core", f"a core fut ({_szoveges(zar) or '?'}); egy vaulton egyszerre egy core fut")
            else:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        pass


PROBA_JELOLO = ".mos-proba.json"        # a `tests/kezi/_kornyezet.probamappa` írja a klónok mappájába


def _kor_szoveg(mp: float) -> str:
    return (f"{mp / 86400:.0f} napos" if mp >= 2 * 86400 else f"{mp / 3600:.0f} órás" if mp >= 3600
            else f"{max(mp, 0) / 60:.0f} perces")


def _pid_el(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _proba_klonok(cfg: config.Config, add) -> None:
    """A kézi próbák (`tests/kezi/`) klónjai: egy próbamappa a vault teljes APFS-klónja, ezért a félbehagyott (a szkript már
    nem fut) és a `--megtart`tal otthagyott mappák gazdátlanul hevernek (T081). A doctor jelzi a nevüket és a korukat; NEM
    töröl — a törlést csak a felhasználó igenjére végezzük (CLAUDE.md, Törlés)."""
    tmp = cfg.path("tmp")
    most, lista, gepi = time.time(), [], []
    for j in sorted([*tmp.glob(f"*/{PROBA_JELOLO}"), *tmp.glob(f"proba/*/{PROBA_JELOLO}")]) if tmp.is_dir() else []:
        try:
            adat = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            adat = {}
        megtart, el = bool(adat.get("megtart")), _pid_el(adat.get("pid"))
        gepi_e = adat.get("szkript") == "gepi_iras"
        if el and not megtart and not gepi_e:
            continue                                # fut a szkriptje, és ő maga törli
        try:
            kor = most - datetime.fromisoformat(adat["letrehozva"]).timestamp()
        except (KeyError, TypeError, ValueError):
            kor = most - j.stat().st_mtime
        if gepi_e:                                  # a gépi írás D9-próbaköre (`{tmp}/proba/<kör>/`)
            gepi.append(f"{j.parent.name} ({_kor_szoveg(kor)}, {_meret_szoveg(j.parent)})")
            continue
        cimkek = ", ".join(c for c in (("megtartott" if megtart else ""), ("árva" if not el else "")) if c)
        lista.append(f"{j.parent.name} ({_kor_szoveg(kor)}, {cimkek}, {_meret_szoveg(j.parent)})")
    # a jelölő előtti (régi) klónok: a kézi szkriptek névmintája (`c08-proba-20261002-143000`) és a `vault.git`
    for d in sorted(tmp.iterdir()) if tmp.is_dir() else []:
        if (d.is_dir() and not (d / PROBA_JELOLO).exists() and (d / "vault.git").is_dir()
                and re.match(r"^c\d[\w.]*-[\w-]*\d{8}-\d{6}$", d.name)):
            lista.append(f"{d.name} ({_kor_szoveg(most - d.stat().st_mtime)}, jelölő nélküli régi klón)")
    # a jelölő előtti gépi próbaklónok (a `gepi_iras` jelölője előtt készültek; az automatikus takarítás nem éri el őket)
    for d in sorted((tmp / "proba").iterdir()) if (tmp / "proba").is_dir() else []:
        if d.is_dir() and not (d / PROBA_JELOLO).exists() and (d / "vault.git").is_dir():
            lista.append(f"proba/{d.name} ({_kor_szoveg(most - d.stat().st_mtime)}, jelölő nélküli gépi próbaklón, "
                         f"{_meret_szoveg(d)})")
    if gepi:
        nap = cfg.section("vault").get("proba_klon_max_nap", 7)
        add(INFO, "próbaklónok (gépi)", f"{len(gepi)} gépi próbakör klónja a {tmp / 'proba'} alatt: {', '.join(gepi)}; a "
                                        f"{nap:g} napnál régebbit a következő próbakör előtt a core törli "
                                        "([vault] proba_klon_max_nap)" if nap else
                                        f"{len(gepi)} gépi próbakör klónja a {tmp / 'proba'} alatt: {', '.join(gepi)}; "
                                        "az automatikus törlés ki van kapcsolva ([vault] proba_klon_max_nap = 0)")
    if not lista:
        add(OK, "próbaklónok", "nincs megmaradt próbaklón")
        return
    add(FIGYELEM, "próbaklónok", f"{len(lista)} próbaklón maradt a {tmp} alatt: {', '.join(lista)}. Egy klón a vault teljes "
                                 "APFS-másolata; a törlésről a felhasználó dönt (a doctor nem töröl)")


def _meret_szoveg(d: Path) -> str:
    """Egy próbaklón logikai mérete (a fájlok összege, linket nem követ). Az APFS-klón a változatlan blokkokat megosztja
    a vaulttal, a valódi helyfoglalás ennél kisebb lehet — más kötetre (mentésbe) másolva viszont teljes."""
    ossz = 0
    for dp, _almappak, fajlok in os.walk(d):
        for f in fajlok:
            try:
                ossz += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return f"{ossz / 1e9:.1f} GB" if ossz >= 1e8 else f"{ossz / 1e6:.0f} MB"


# C33 (T069): a `bin/mos kapu` (tests/kezi/kapu.py) védett kódja — ennek a változása után a klónos kapu újra kell
KAPU_VEDETT = ("core/vaultio.py", "core/atnevezes.py", "core/index", "core/server.py", "core/snapshot.py", "core/frame.py",
               "core/tartos.py", "core/utkapu.py", "app/src/szerkeszto/dokumentum", "tests/kezi")


def _kodtar_git(root: Path, *args: str) -> str | None:
    """A 2.0 kódtárának csak olvasó git-hívása (`GIT_OPTIONAL_LOCKS=0`); hiba esetén None."""
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20,
                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _kapu(cfg: config.Config, add) -> None:
    """A klónos kézi próbák legutóbbi futása (`{runs}/kapu-*.json`, C33 T069): FIGYELEM, ha bukott, vagy ha régebbi a HEAD-nél
    és azóta a kapuk által védett kód (`KAPU_VEDETT`) változott; INFO, ha még nem futott. Csak olvas."""
    runs = cfg.path("runs")
    lista = sorted(runs.glob("kapu-*.json")) if runs.is_dir() else []
    if not lista:
        add(INFO, "kapu", "a klónos kézi próbák (bin/mos kapu) még nem futottak ezzel a var/-ral")
        return
    try:
        d = json.loads(lista[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        add(FIGYELEM, "kapu", f"a legutóbbi kapu riportja nem olvasható ({lista[-1].name}): {e}")
        return
    ido = d.get("ido", "?")
    if not d.get("rendben"):
        bukott = [e.get("nev") for e in d.get("eredmenyek", []) if not e.get("rendben")]
        add(FIGYELEM, "kapu", f"a legutóbbi kapu ({ido}) BUKOTT: {', '.join(map(str, bukott)) or '?'} — {lista[-1].name}")
        return
    resz = "" if d.get("teljes", True) else " (csak részleges futás)"
    head = _kodtar_git(cfg.root, "rev-parse", "HEAD")
    kapu_head = d.get("head")
    if not head or head == kapu_head:
        add(OK, "kapu", f"a legutóbbi kapu ({ido}) RENDBEN a HEAD-en{resz}")
        return
    valtozott = _kodtar_git(cfg.root, "diff", "--name-only", str(kapu_head), "HEAD", "--", *KAPU_VEDETT) if kapu_head else None
    if valtozott is None:
        add(FIGYELEM, "kapu", f"a legutóbbi kapu ({ido}, {str(kapu_head)[:8]}) régebbi a HEAD-nél ({head[:8]}): bin/mos kapu")
    elif valtozott:
        n = len(valtozott.splitlines())
        add(FIGYELEM, "kapu", f"a legutóbbi kapu ({ido}, {str(kapu_head)[:8]}) régebbi a HEAD-nél ({head[:8]}), és azóta a kapuk "
                              f"által védett kód változott ({n} fájl): bin/mos kapu")
    else:
        add(OK, "kapu", f"a legutóbbi kapu ({ido}) RENDBEN; azóta a védett kód nem változott{resz}")


def _index(cfg: config.Config, add) -> None:
    """A vault-index állapota (C33, T171): megvan-e, megnyitható és ép-e (`quick_check`, a valódi indexen ~2 s), a séma
    verziója, és a félretett sérült indexek (`{index}/serult-*.sqlite`). Csak olvas (`mode=ro`)."""
    import sqlite3
    from .index import tar
    d = cfg.path("index")
    db = d / "vault.sqlite"
    felretett = sorted(p.name for p in d.glob("serult-*.sqlite")) if d.is_dir() else []
    if felretett:
        add(INFO, "index (félretett)", f"{len(felretett)} sérült index félretéve ({_fentiek(felretett)}); a core újraépítette, "
                                       "a fájlok törölhetők")
    if not db.exists():
        add(INFO, "index", "még nincs index (a core első indulása építi, ~2 s)")
        return
    try:
        from urllib.parse import quote
        c = sqlite3.connect(f"file:{quote(str(db))}?mode=ro", uri=True, timeout=5)   # a `#`, `?`, `%` kódolva (T108)
        try:
            v = c.execute("PRAGMA user_version").fetchone()[0]
            ep = c.execute("PRAGMA quick_check").fetchone()[0]
            n = c.execute("SELECT count(*) FROM fajl WHERE torolve IS NULL").fetchone()[0] if v >= 1 else 0
        finally:
            c.close()
    except sqlite3.DatabaseError as e:
        add(FIGYELEM, "index", f"az index nem olvasható ({e}): a core következő indulása félreteszi és újraépíti"
            if tar.serult_hiba(e) else f"az index nem olvasható: {e}")
        return
    if v > tar.VERZIO:
        add(FIGYELEM, "index", f"az index sémája ({v}) újabb, mint a kódé ({tar.VERZIO}): újabb core építette")
    elif ep != "ok":
        add(FIGYELEM, "index", f"az index sérült (quick_check: {ep}): a core menet közben félreteszi és újraépíti")
    else:
        add(OK, "index", f"ép (séma {v}, {n} fájl)")


def _modell_reviziok(cfg: config.Config, add) -> None:
    """C19 (T141): a helyi modell-gyorsítótár a `config/letoltes.toml` rögzített revízióján áll-e, és a kalibrált router-sorok
    ezen a pillanatképen mértek-e. Csak olvas (a router.sqlite-ot `immutable=1`-gyel, nem migrál)."""
    import sqlite3
    import tomllib
    from .modell import revizio
    try:
        with open(cfg.root / "config" / "letoltes.toml", "rb") as f:
            lista = tomllib.load(f).get("modell", {})
    except (OSError, tomllib.TOMLDecodeError) as e:
        add(FIGYELEM, "modell-revízió", f"a letoltes.toml nem olvasható: {e}")
        return
    elteresek = revizio.ellenoriz(lista, cfg.path("models"))
    add(FIGYELEM if elteresek else OK, "modell-revízió",
        _fentiek([e["uzenet"] for e in elteresek]) if elteresek else "a helyi modellek a rögzített revízión állnak")
    db = cfg.path("router_db")
    if not db.is_file():
        return
    try:
        con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
        try:
            oszlopok = {r[1] for r in con.execute("PRAGMA table_info(kalibracio)")}
            sorok = [dict(zip(("feladat", "modell", "kalibralt", "snapshot"), r)) for r in con.execute(
                "SELECT feladat, modell, kalibralt, snapshot FROM kalibracio WHERE kalibralt=1")] if "snapshot" in oszlopok else []
        finally:
            con.close()
    except sqlite3.Error as e:
        add(FIGYELEM, "kalibráció-pillanatkép", f"a router.sqlite nem olvasható: {e}")
        return
    rossz = revizio.kalibracio_elteres(sorok, {n: str(m.get("revizio") or "") for n, m in lista.items()})
    if rossz:
        add(FIGYELEM, "kalibráció-pillanatkép", _fentiek(rossz))
    elif sorok:
        add(OK, "kalibráció-pillanatkép", f"{len(sorok)} kalibrált sor, mind a rögzített revízión mért")


def _naptar(cfg: config.Config, add) -> None:
    """C29: az EventKit-segéd (a Manifold.app `--naptar` módja) megvan-e, és mi az engedély-állapota (csak lekérdezés:
    a doctor engedélyt nem kér). Az engedélyt a Manifold.app kéri a felületről („Naptár-engedély kérése”)."""
    from .naptar_seged import Seged, SegedHiba
    seged = Seged(cfg)
    if not seged.van():
        add(FIGYELEM, "naptár-segéd", f"nincs futtatható segéd ({seged.ut()}): a Manifold.app újrafordítása kell (shell/build.sh)")
        return
    try:
        a = seged.futtat("allapot", idokorlat=15)
    except SegedHiba as e:
        add(FIGYELEM, "naptár-segéd", f"a segéd nem válaszol: {e}")
        return
    add(INFO, "naptár-engedély", f"naptár: {a.get('esemeny')}, emlékeztetők: {a.get('emlekezteto')} "
                                 "(az engedélyt a Manifold.app kéri a felületről)")


def _verzio_szamok(s) -> tuple[int, int] | None:
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r"\s*(\d+)(?:\.(\d+))?(?:\.\d+)*\s*", s)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def sdk_regebbi(sdk_verzio: str | None, macos_verzio_: str | None) -> bool:
    """C36a: az SDK (főverzió.alverzió) régebbi-e a futó macOS-nél. Értelmezhetetlen verziónál nem riaszt."""
    a, b = _verzio_szamok(sdk_verzio), _verzio_szamok(macos_verzio_)
    return bool(a and b and a < b)


def macos_verzio() -> str | None:
    """A futó macOS verziója (`sw_vers`); külön, modulszintű függvény, hogy a teszt lecserélhesse."""
    try:
        ki = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=10)
        return ki.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _futtathato(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def _cpp(cfg: config.Config, add, kivul: bool) -> None:
    """C36a: a hordozható C++ eszköztár (`runtime/llvm`, `runtime/sdk`). Csak a `runtime` alatti elemeket nézi: a PATH-on
    talált fordítót nem. Hiányuk FIGYELEM (az eszköztár opcionális, a telepítés D3 szerint jóváhagyott lépés), munkafa-módban
    INFO (a `runtime` a fő checkoutból jön)."""
    llvm, sdk = cfg.path("llvm"), cfg.path("sdk")
    hiany = INFO if kivul else FIGYELEM
    hely = " (munkafa-mód: a runtime a fő checkoutból jön; ott ellenőrizd)" if kivul else ""
    hi = [n for n in ("clang++", "clang-format") if not _futtathato(llvm / "bin" / n)]
    if len(hi) == 2 and not llvm.exists():
        add(hiany, "C++ eszköztár", "nincs telepítve: bin/mos cpp telepit (a letöltési lista), majd bin/mos cpp telepit --igen" + hely)
    elif hi:
        add(hiany, "C++ eszköztár", f"hiányzik az LLVM-ből: {', '.join(hi)} (bin/mos cpp telepit --igen --ujra)" + hely)
    else:
        add(OK, "C++ eszköztár", f"clang++ és clang-format megvan ({llvm})")
        # K168: egyetlen linker él, az LLVM ld64.lld-je (a rendszer ld-je a fordító-profil alatt nem futhat), tartalék nincs
        ertek = cfg.section("cpp").get("linker", "lld")
        if _futtathato(llvm / "bin" / "ld64.lld"):
            if ertek == "lld":
                add(OK, "C++ linker", "az LLVM saját linkere (ld64.lld) megvan")
            else:
                add(FIGYELEM, "C++ linker", f"[cpp] linker = {ertek!r}: csak az \"lld\" támogatott (a \"rendszer\" linker a fordító-profil alatt "
                    "nem futhat, K168), a beállítás figyelmen kívül marad: a config/os.toml-ban javítandó")
        else:
            add(hiany, "C++ linker", "nincs ld64.lld az LLVM-csomagban: a C++ fordítás nem tud linkelni (tartalék linker nincs, a rendszer "
                "ld-je a fordító-profil alatt nem futhat): bin/mos cpp telepit --igen --ujra" + hely)
    try:
        sdk_v = json.loads((sdk / "SDKSettings.json").read_text(encoding="utf-8")).get("Version")
    except (OSError, ValueError, AttributeError):
        sdk_v = None
    if sdk_v is None or not (sdk / "usr" / "include").is_dir():
        add(hiany, "C++ SDK", "nincs SDK-másolat: bin/mos cpp telepit --sdk" + hely)
        return
    os_v = macos_verzio()
    if sdk_regebbi(sdk_v, os_v):
        add(FIGYELEM, "C++ SDK", f"az SDK-másolat régebbi ({sdk_v}) a futó macOS-nél ({os_v}): bin/mos cpp telepit --sdk --ujra")
    else:
        add(OK, "C++ SDK", f"SDK {sdk_v}" + (f" (macOS {os_v})" if os_v else ""))


def ellenoriz(cfg: config.Config, environment: dict[str, str], home: Path,
              futo_python: Path | None = None) -> list[Eredmeny]:
    root, r = cfg.root, []
    add = lambda a, n, u: r.append(Eredmeny(a, n, u))  # noqa: E731
    runtime, venv, var = cfg.path("runtime"), cfg.path("venv"), cfg.path("var")
    futo = Path(futo_python or sys.executable)

    # gyökér
    ok = (root / "bin" / "mos").exists() and (root / "config" / "os.toml").exists()
    add(OK if ok else HIBA, "gyökér", str(root) if ok else f"nem érvényes gyökér: {root}")
    if var.exists() and cfg.path("vault").exists():
        add(OK if var.stat().st_dev == cfg.path("vault").stat().st_dev else HIBA, "kötet",
            "a var/ és a vault ugyanazon a köteten van" if var.stat().st_dev == cfg.path("vault").stat().st_dev
            else "a var/ és a vault külön köteten van (az atomi csere és a klón nem működik)")
    elif not var.exists():
        add(HIBA, "kötet", f"nincs var/: {var}")

    # a var/ symlinkje (T002): egy munkafa `var/`-ja a valódi állapotra mutatna, és az ott indított core (selftest,
    # core start) a valódi kör-zárat, szándéknaplókat, feladatsort, indexet és személyes adatot kapná
    gyoker_var = root / "var"
    if gyoker_var.is_symlink():
        cel = Path(os.path.realpath(gyoker_var))
        belul = cel == Path(os.path.realpath(root)) or Path(os.path.realpath(root)) in cel.parents
        add(OK if belul else HIBA, "var symlink",
            f"a var/ symlink, de a gyökéren belülre mutat: {os.readlink(gyoker_var)}" if belul else
            f"a var/ symlink, amely a gyökéren ({root}) kívülre mutat: {os.readlink(gyoker_var)} → {cel}; a core a valódi "
            "állapotot használná (egy munkafának saját var/ kell; bin/mos: munkafa-mód)")
    else:
        add(OK, "var symlink", "a var/ nem symlink")

    _vault(cfg, environment, add)
    _tarolok_allapota(cfg, add)
    _tarolt_binaris(cfg, add)

    # rendszer-Python
    sajat = str(futo).startswith(str(runtime)) or str(Path(sys.prefix if futo_python is None else futo)).startswith(str(root))
    tiltott = [t for t in TILTOTT_PYTHON if str(futo).startswith(t)]
    rossz = [] if (sajat and not tiltott) else [f"a futó Python az SSD-n kívül van: {futo}"]
    cfgfile = venv / "pyvenv.cfg"
    if cfgfile.exists():
        szoveg = cfgfile.read_text(encoding="utf-8")
        for kulcs in ("home", "executable", "command"):
            m = re.search(rf"^{kulcs}\s*=\s*(.+)$", szoveg, re.M)
            if m and kulcs != "command" and not m.group(1).strip().startswith(str(runtime)):
                rossz.append(f"pyvenv.cfg {kulcs} = {m.group(1).strip()}")
        py = venv / "bin" / "python"
        if py.is_symlink() and not str(py.resolve()).startswith(str(runtime.resolve())):
            rossz.append(f"a venv Pythonja az SSD-n kívülre mutat: {py.resolve()}")
        for s in sorted((venv / "bin").glob("*")) if (venv / "bin").is_dir() else []:
            t = _szoveges(s) if not s.is_symlink() else None
            if t and t.startswith("#!") and str(venv) not in "\n".join(t.split("\n")[:3]) \
                    and not t.split("\n", 1)[0][2:].startswith(("/bin/sh", "/usr/bin/env")):
                rossz.append(f"shebang az SSD-n kívülre mutat: {s.name}")
    else:
        rossz.append(f"nincs venv: {venv} (bin/mos runtime install)")
    # munkafa-mód (bin/mos, T002): a munkafának nincs saját venv-je, az eszköztár a fő checkoutból jön — azt ott kell
    # ellenőrizni; a munkafa állapota (var/) viszont a sajátja, és az alábbi ellenőrzések rá vonatkoznak
    eszkoztar_kivul = bool(environment.get("MOS_MUNKAFA")) and not (venv / "bin" / "python").exists()
    if eszkoztar_kivul:
        add(INFO, "python", "munkafa-mód: a Python és a venv a fő checkoutból jön; ott ellenőrizd (bin/mos doctor)")
    else:
        add(HIBA if rossz else OK, "python", _fentiek(rossz) if rossz else "az SSD hordozható Pythonja fut, a venv is arra mutat")

    # ~/Applications, ~/.cache és legacy var/ — saját fájlok
    hibas_sajat, hibas_legacy = [], []
    for p in _sajat_fajlok(root):
        t = _szoveges(p)
        if not t:
            continue
        t = _kod(t)
        rel = p.relative_to(root)
        if SAJAT_MINTA.search(t):
            hibas_sajat.append(str(rel))
        if LEGACY_MINTA.search(t):
            hibas_legacy.append(str(rel))
    app = root / "Manifold.app"
    if app.exists():
        plist = _szoveges(app / "Contents" / "Info.plist") or ""
        if SAJAT_MINTA.search(plist):
            hibas_sajat.append("Manifold.app/Contents/Info.plist")
        if re.search(r"MOSGyoker</key>\s*<string>[^<]", plist):
            hibas_legacy.append("Manifold.app: beégetett MOSGyoker")
    if app.is_symlink() and str(app.resolve()).startswith(str(home / "Applications")):
        hibas_sajat.append("Manifold.app a ~/Applications-re mutat")
    regi = sorted(p.name for p in (home / "Applications").glob("Manifold*.app")) if (home / "Applications").is_dir() else []
    envrosszak = []
    for k, v in sorted(environment.items()):
        if k.startswith(ENV_UTAS) and v:
            if SAJAT_MINTA.search(v) or v.startswith(str(home / ".cache")) or v.startswith(str(home / "Applications")):
                envrosszak.append(f"env {k}={v}")
            if LEGACY_MINTA.search(v):
                hibas_legacy.append(f"env {k}={v}")
    add(HIBA if hibas_sajat or envrosszak else OK, "~/Applications, ~/.cache",
        _fentiek(hibas_sajat + envrosszak) if hibas_sajat or envrosszak else "semmi nem használja")

    if regi:
        add(FIGYELEM, "régi appok", f"~/Applications/{', '.join(regi)}: a legacy telepítőjéé, a 2.0 nem használja; "
            "törlésükről a felhasználó dönt")

    # legacy var/ — linkek, git-konfigok, kis állapotfájlok
    for p in (var.iterdir() if var.is_dir() else []):
        if p.is_symlink() and LEGACY_MINTA.search(str(os.readlink(p))):
            hibas_legacy.append(f"var/{p.name} → legacy")
        if p.suffix == ".git" and (p / "config").exists():
            t = _szoveges(p / "config") or ""
            if LEGACY_MINTA.search(t):
                hibas_legacy.append(f"var/{p.name}/config")
            m = re.search(r"worktree\s*=\s*(.+)", t)
            if m and not (m.group(1).strip().startswith(str(root)) or m.group(1).strip() == str(cfg.path("vault"))):
                hibas_legacy.append(f"var/{p.name}: core.worktree = {m.group(1).strip()}")
    for k, v in cfg.utak.items():
        if LEGACY_MINTA.search(str(v)):
            hibas_legacy.append(f"os.toml [{k}] = {v}")
    st = cfg.path("state")
    for p in (list(st.glob("*.json")) + list(st.glob("*.toml")) + list(st.glob("*.jsonl"))[:0]) if st.is_dir() else []:
        t = _szoveges(p) or ""
        if LEGACY_MINTA.search(t):
            hibas_legacy.append(f"var/state/{p.name}")
    add(HIBA if hibas_legacy else OK, "legacy var/", _fentiek(hibas_legacy) if hibas_legacy else "semmi nem mutat a legacy var/-ra")

    # vault-séma (C11b, 2. audit T162): a `[sema] vault` a 2.0 saját fájlja — feloldódik, JSON, és nem a legacy kalibrációja
    allapot, uzenet = _sema_ellenor(cfg)
    add(allapot, "vault-séma", uzenet)

    # git (K1, M10): a pillanatkép a rendszer gitjére épül
    utvonal = environment.get("PATH") or os.environ.get("PATH", "")
    git = shutil.which("git", path=utvonal)
    gv = subprocess.run([git, "--version"], capture_output=True, text=True) if git else None
    if gv is not None and gv.returncode == 0:
        add(OK, "git", f"{gv.stdout.strip()} ({git})")
    else:
        add(HIBA, "git", "nincs működő git a PATH-on: pillanatkép nélkül nincs visszavonás (xcode-select --install)")
    _git_fuggoseg(git, add)
    for name, git_dir in _tarolok(cfg):
        if (git_dir / "index.lock").exists():
            add(FIGYELEM, f"{name}.git", "elakadt index.lock: a core következő indulása eltávolítja")

    # offline
    off = environment.get("HF_HUB_OFFLINE") == "1"
    add(OK if off else HIBA, "offline", "HF_HUB_OFFLINE=1" if off else "HF_HUB_OFFLINE nincs 1-re állítva (bin/mos állítja)")

    # runtime
    hi = [n for n, p in (("uv", runtime / "uv"), ("python", runtime / "python" / "bin" / "python3"),
                         ("node", runtime / "node" / "bin" / "node")) if not p.exists()]
    if hi and eszkoztar_kivul:       # munkafa-mód (T002): a runtime a fő checkoutból jön (`bin/mos`), a munkafában nincs
        add(INFO, "runtime", f"munkafa-mód: a runtime a fő checkoutból jön (itt hiányzik: {', '.join(hi)}); ott ellenőrizd")
    else:
        add(HIBA if hi else OK, "runtime", f"hiányzik: {', '.join(hi)}" if hi else "uv, Python, Node megvan")
    lock = root / "config" / "requirements.lock"
    if lock.exists() and (venv / "bin" / "python").exists() and (runtime / "uv").exists():
        elvart = set(re.findall(r"^([A-Za-z0-9_.-]+==[^\s\\]+)", lock.read_text(encoding="utf-8"), re.M))
        p = subprocess.run([str(runtime / "uv"), "pip", "freeze", "--python", str(venv / "bin" / "python"), "--no-config", "--offline"],
                           capture_output=True, text=True, env={**os.environ, "UV_CACHE_DIR": str(cfg.path("cache") / "uv")})
        norm = lambda s: s.lower().replace("_", "-")  # noqa: E731
        van = {norm(x) for x in p.stdout.split() if "==" in x}
        kul = {norm(x) for x in elvart} ^ van
        add(OK if p.returncode == 0 and not kul else HIBA, "lock",
            "a venv egyezik a requirements.lock-kal" if p.returncode == 0 and not kul else f"eltérés a lockhoz képest: {_fentiek(sorted(kul))}")
    elif eszkoztar_kivul:
        add(INFO, "lock", "munkafa-mód: a venv a fő checkoutban van; a lock-egyezést ott ellenőrizd (bin/mos doctor)")
    else:
        add(HIBA, "lock", "nincs lock, venv vagy uv az összevetéshez")

    _runtime_verziok(cfg, add, eszkoztar_kivul)
    _kovetelmenyek(cfg, add)
    _video_ffmpeg(cfg, home, add)
    _modell_reviziok(cfg, add)

    # app
    if app.exists():
        c = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True, text=True)
        add(OK if c.returncode == 0 else HIBA, "Manifold.app", "megvan, aláírása érvényes" if c.returncode == 0 else f"aláírás: {c.stderr.strip()}")
    else:
        add(HIBA, "Manifold.app", "hiányzik (shell/build.sh)")
    if app.exists():
        _alairas(app, add)
        _naptar(cfg, add)
    _home_irasok(home, add)
    _napi_canvas(root, add)
    _never_index(var, add)
    dist = cfg.path("app_dist")
    if (dist / "index.html").is_file():
        from .epites import allapot as epites_allapot
        ep = epites_allapot(cfg.root)
        for resz in ep["reszek"]:
            add(OK if resz["friss"] else FIGYELEM, "build-" + resz["resz"],
                f"forrással egyező build ({resz['azonosito']})" if resz["friss"] else
                "hiányzó vagy elavult buildjegyzék; újrafordítás szükséges: " + ", ".join(resz["elteres"]))
    else:
        add(FIGYELEM, "felület", "nincs app/dist: a héj üres lapot mutat (bin/mos app install, majd bin/mos app build)")
    _mentes(cfg, add)
    _index(cfg, add)
    _kapu(cfg, add)
    _cpp(cfg, add, eszkoztar_kivul)
    _proba_klonok(cfg, add)
    _core_fut(cfg, add)
    if environment.get("MOS_OSSZEOMLAS"):
        add(HIBA, "összeomlás-horog", f"MOS_OSSZEOMLAS={environment['MOS_OSSZEOMLAS']}: az összeomlás-injektáló horog be van "
                                      "kapcsolva (csak a tesztállványé, éles környezetben soha)")
    return r


def main(argv: list[str]) -> int:
    cfg = config.load()
    eredmenyek = ellenoriz(cfg, dict(os.environ), Path(os.environ.get("HOME", "~")).expanduser())
    jel = {OK: "✓", HIBA: "✗", INFO: "·", FIGYELEM: "!"}
    for e in eredmenyek:
        print(f"{jel[e.allapot]} {e.nev}: {e.uzenet}")
    piros = [e for e in eredmenyek if e.allapot == HIBA]
    print("\nA doctor zöld." if not piros else f"\nA doctor piros: {len(piros)} hiba.")
    return 1 if piros else 0
