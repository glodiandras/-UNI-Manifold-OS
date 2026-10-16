"""Doctor: jelzi, ha bármi a rendszer-Pythonra, a ~/Applications-re vagy a ~/.cache-re mutat.

Csak a standard könyvtárat használja, így a venv nélkül is fut. Kilépési kód: 0 zöld, 1 piros.

Két mód (F3-DESIGN §6): `hordozhato` (a fejlesztő checkoutja, a v2 szabályai változatlanul) és `termek` (a `*.app` csomag:
csomag-épség, I1, a munkatér, a regiszter, a kötet- és zárszabályok). Minden sor stabil `kod`-ot, `osztaly`-t (`termek` |
`fejleszto`) és — ha van gépi javítása — `javitas`-azonosítót kap; a `--json` kimenet ezt adja a Health nézetnek (F7). A doctor
csak olvas: a javítás azonosítója a nézet dolga, a végrehajtása nem itt történik.
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
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config

OK, HIBA, INFO, FIGYELEM = "ok", "hiba", "info", "figyelem"
TILTOTT_PYTHON = ("/Library/Frameworks/Python.framework", "/usr/bin/", "/opt/homebrew", "/usr/local")
SAJAT_MINTA = re.compile(r"~/Applications|/\.cache\b|~/\.cache|Library/Caches|\$HOME/\.cache")
SZOVEG_KITERJESZTES = {"", ".toml", ".env", ".sh", ".py", ".swift", ".plist", ".json", ".txt", ".cfg", ".lock", ".md"}
KIHAGY_MAPPAK = {"docs", "archive", "tests", "runtime", "var", "node_modules", ".git", ".claude", "__pycache__", "staging"}
# A gyökér alatti minden rejtett mappa (`.claude/worktrees`, `.git`, `.venv`…) kimarad: a saját forrás nem ott van, és a
# párhuzamos munkafák bejárása lassú, a bennük levő (más ágon álló) fájlok pedig hamis találatot adnak.
KIHAGY_FAJLOK = {"CLAUDE.md", "doctor.py"}      # a minták saját forrásukban nem számítanak
ENV_UTAS = ("UV_", "PIP_", "XDG_", "HF_", "TMPDIR", "MOS_", "PYTHON", "TRANSFORMERS_")


@dataclass
class Eredmeny:
    allapot: str
    nev: str
    uzenet: str
    kod: str = ""                 # stabil azonosító (a Health ezzel hivatkozik a sorra; a `nev` szövege változhat)
    osztaly: str = "termek"       # "termek": a termék felhasználóját érinti; "fejleszto": csak forrás-checkouton értelmes
    javitas: str | None = None    # gépi javítás azonosítója (JAVITASOK), vagy None

    def szotar(self) -> dict:
        return {"kod": self.kod, "allapot": self.allapot, "nev": self.nev, "uzenet": self.uzenet,
                "osztaly": self.osztaly, "javitas": self.javitas}


JAVITASOK = ("regiszter_takarit", "zar_takarit")      # a doctor csak az azonosítót adja; a végrehajtás a Health (F7) dolga

# A rögzített nevű sorok kódjai. A dinamikus nevűek (`pillanatkép (<tár>)`, `<tár>.git`, `build-<rész>`…) a névből képződnek
# (`_kod_nevbol`). A kódok nem változnak, ha a szöveg igen: a `tests/test_doctor_termek.py` rögzíti őket.
_NEV_KOD = {
    "gyökér": "gyoker", "kötet": "kotet", "var symlink": "var_symlink", "vault": "vault", "vault .gitattributes": "vault_gitattributes",
    "vault ideiglenes fájlok": "vault_ideiglenes", "python": "python", "~/Applications, ~/.cache": "sajat_utak",
    "vault-séma": "vault_sema", "git": "git", "git függőség": "git_fuggoseg", "offline": "offline", "runtime": "runtime",
    "lock": "lock", "runtime verzió": "runtime_verzio", "requirements.in": "requirements_in", "ffmpeg": "ffmpeg",
    "modell-revízió": "modell_revizio", "kalibráció-pillanatkép": "kalibracio_pillanatkep", "Manifold.app": "manifold_app",
    "aláírás": "alairas", "naptár-segéd": "naptar_seged", "naptár-engedély": "naptar_engedely", "home írások": "home_irasok",
    "@napi-rs/canvas": "napi_canvas", "Spotlight": "spotlight", "felület": "felulet", "mentés": "mentes",
    "mentés (kódtár)": "mentes_kodtar", "mentés (állapot)": "mentes_allapot", "mentés hiba": "mentes_hiba", "index": "index",
    "index (félretett)": "index_felretett", "kapu": "kapu", "C++ eszköztár": "cpp_eszkoztar", "C++ linker": "cpp_linker",
    "C++ SDK": "cpp_sdk", "próbaklónok": "probaklonok", "próbaklónok (gépi)": "probaklonok_gepi", "core": "core",
    "összeomlás-horog": "osszeomlas_horog", "pillanatkép bináris": "pillanatkep_binaris",
    "pillanatkép kód (ytdlp)": "pillanatkep_kod_ytdlp",
}
# Csak forrás-checkouton (hordozható elrendezés) értelmes sorok: a termék-futásban nem is keletkeznek, a hordozhatóban `fejleszto`
FEJLESZTO_KODOK = frozenset({"gyoker", "var_symlink", "python", "sajat_utak", "runtime", "lock", "runtime_verzio", "requirements_in",
                             "manifold_app", "alairas", "napi_canvas", "felulet", "kapu", "osszeomlas_horog"})
FEJLESZTO_ELOTAGOK = ("build_",)


def _ascii(szoveg: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", szoveg) if not unicodedata.combining(c))


def _kod_nevbol(nev: str) -> str:
    """A sor kódja a nevéből: a rögzített táblából, különben ékezetmentes, `_`-elválasztású kisbetűs szlug."""
    if nev in _NEV_KOD:
        return _NEV_KOD[nev]
    return re.sub(r"[^a-z0-9]+", "_", _ascii(nev).lower()).strip("_") or "sor"


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
    """A vault-séma a feloldási lánc szerint (F3-DESIGN §2.4; `core/kiserok.sema_fajl`): a `[sema] vault` fájl, ha létezik (termékben
    `{workspace}/schema.json`) → az első megnevezett preset `<nev>.schema.json`-ja → a szállított `[sema] alap`. A kiválasztott fájl
    olvasható JSON-objektum kell legyen a kötelező `mezosorrend` listával. Ha egyik sincs, az csak `[sema] mod != "ki"` esetén hiba
    (kikapcsolt sémaellenőrzésnek nincs mire hivatkoznia). A doctor importmentes (a venv nélkül is fut)."""
    try:
        from . import kiserok
        sec = cfg.section("sema")
        fajlok = kiserok.sema_fajlok(cfg)
    except Exception as e:  # noqa: BLE001 — a hibás config vagy a feloldó hibája jelzés, nem összeomlás
        return HIBA, f"a vault-séma feloldása nem sikerült: {e}"
    if fajlok:
        # a betöltő az első ÉRVÉNYES jelöltet használja (`Sema.betolt`): az előtte állók hibája figyelmeztetés, nem hiba
        kihagyott = []
        for ut in fajlok:
            try:
                kiserok.sema_olvas(ut)
            except kiserok.SemaHiba as e:
                kihagyott.append(str(e))
                continue
            allapot, uzenet = _sema_fajl(ut)
            if kihagyott:
                return FIGYELEM, f"a(z) {_fentiek(kihagyott)} érvénytelen, ezért kimarad; helyette: {uzenet}"
            return allapot, uzenet
        return HIBA, f"nincs érvényes vault-séma: {_fentiek(kihagyott)}"
    probalt = []
    for kulcs in ("vault", "alap"):
        try:
            if sec.get(kulcs):
                probalt.append(cfg.expand(sec[kulcs]))
        except config.ConfigError:
            pass                                  # nincs megnyitott munkatér: a `{workspace}` alatti elem nem számít
    if sec.get("mod", "ki") == "ki":
        return INFO, "nincs vault-séma, de a sémaellenőrzés ki van kapcsolva ([sema] mod = ki)"
    return HIBA, f"nincs vault-séma: a munkatér, a presetek és a szállított alap sémája sem található ({', '.join(probalt) or 'nincs [sema] út'})"


def _kivetelek_sor(cfg: config.Config, add) -> None:
    """A visszavonási kivételek fájlja (`[pillanat.<tár>].kivetelek`; a termékben a munkatér `pillanat-kivetelek.json`-ja, megbízhatatlan):
    az érvénytelen bejegyzés kimarad a visszavonásból (nem kivétellel áll le), és itt figyelmeztet."""
    try:
        from . import snapshot
        gondok = [f"{nev}: {h}" for nev in cfg.section("pillanat") for h in snapshot.kivetelek_hibak(cfg, nev)]
    except Exception:  # noqa: BLE001 — feloldatlan útnál (nincs munkatér) nincs mit jelezni
        return
    if gondok:
        add(FIGYELEM, "visszavonási kivételek", f"{len(gondok)} érvénytelen bejegyzés kimarad a visszavonásból: {_fentiek(gondok)}",
            kod="kivetelek_hibas")


def _sema_fajl(ut: Path) -> tuple[str, str]:
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
        try:
            g = Path(cfg.expand(sec["git_dir"]))
        except config.ConfigError:
            continue                                # nincs vault/munkatér: ennek a tárolónak nincs hova állnia
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
            add(HIBA, "vault", f"nincs vault: {vault} — csatlakoztatva a kötet?")
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
                                              "info/attributes-e felülírja, de más git-eszköz (Obsidian Git, kézi git) látja — "
                                              "egy `filter=lfs` sor megállíthatná azokat")
    if tmp:
        add(FIGYELEM, "vault ideiglenes fájlok", f"{len(tmp)} megszakadt mentésből maradt .manifold-tmp fájl a vaultban "
                                                 f"({_fentiek(tmp)}); a core következő indulása törli")


def _tarolok_allapota(cfg: config.Config, add, termek: bool = False) -> None:
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
                         ".gitattributes-e hathat a pillanatképre (a core következő indulása beírja)")
        if not re.search(r"hookspath\s*=\s*/dev/null", cfgszoveg, re.IGNORECASE):
            hibak.append("a core.hooksPath nem /dev/null: egy hook megállíthatná a pillanatképet (a core következő indulása beírja)")
        if hibak:
            add(sulyos, felirat, "; ".join(hibak))
        else:
            add(OK, felirat, f"{repo.git_dir} rendben")
        if name == "vault" and (termek or (repo.work_tree / ".manifold").is_dir()):
            # F3 I6: a `.manifold/` (benne a próbaklónok és az állapot) a pillanatképbe soha nem kerülhet
            kizarva = ".manifold/" in (_szoveges(repo.git_dir / "info" / "exclude") or "").splitlines()
            if kizarva:
                add(OK, "pillanatkép (.manifold)", "a .manifold/ az info/exclude-ban van: a munkatér állapota nem kerül a pillanatképbe",
                    kod="manifold_kizarva")
            else:
                add(HIBA if termek else FIGYELEM, "pillanatkép (.manifold)",
                    "a .manifold/ nincs az info/exclude-ban: a munkatér állapota (a próbaklónokkal együtt) bekerülhet a pillanatképbe "
                    "(a core következő indulása újragenerálja az info/exclude-ot)", kod="manifold_kizarva")


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
                                                      "kézi változásként kerül az ytdlp tárba")


def _video_ffmpeg(cfg: config.Config, home: Path, add, termek: bool = False) -> None:
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
        add(FIGYELEM, "ffmpeg", f"hiányzik: {ff} — a videólánc nem indul "
                                f"({'a csomag hiányos: telepítsd újra a Manifoldot' if termek else 'bin/mos runtime fetch ffmpeg'})")
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


def _never_index(var: Path, add, install: Path | None = None) -> None:
    """L50 (C34, T190): a `var/.metadata_never_index` megléte (Spotlight-kizárás). A `bin/mos` minden indításkor létrehozza;
    termékben a `core.gyokerek.biztosit_mappak` a `{var}` és a `{install}` alatt is (az `install` csak ott adott, ahol különbözik)."""
    if not var.is_dir():
        return
    helyek = [var] + ([install] if install is not None and install.is_dir() and install != var else [])
    hianyzik = [h for h in helyek if not (h / ".metadata_never_index").exists()]
    if not hianyzik:
        add(OK, "Spotlight", "a var/ Spotlight-kizárt (.metadata_never_index)" if len(helyek) == 1
            else "a var/ és a telepítési mappa Spotlight-kizárt (.metadata_never_index)")
    else:
        add(FIGYELEM, "Spotlight", f"hiányzik a .metadata_never_index: {', '.join(str(h) for h in hianyzik)} — a Spotlight indexelné "
                                   "a modelleket és az indexeket — a következő indítás létrehozza")


APP_AZONOSITO = config.BUNDLE_ID
HOME_KIVETEL = f"Library/Preferences/{APP_AZONOSITO}.plist"
HOME_NEM_ENGEDETT = ("Library/Saved Application State", "Library/Caches", "Library/WebKit", "Library/HTTPStorages",
                     "Library/Application Support", "Library/Containers", "Library/Logs")
HOME_TERMEK_ENGEDETT = "Library/Application Support/Manifold"       # a termék telepítési mappája (`{install}`): a saját helye


def _home_irasok(home: Path, add, termek: bool = False) -> None:
    """C34 (T189, K1-A2-hej-11): a héj a home alá nem ír — kivéve az AppKit/cfprefsd `~/Library/Preferences/<BUNDLE_ID>.plist`-jét (a natív helyi menü helyesírás-panelje ablakkeret-bejegyzéseket tesz bele), és a belső lemezes mentést
    (`~/Manifold-backup`). Az első megengedett kivétel (INFO); bármi más a héj azonosítójával (mentett ablakállapot,
    WebKit-tár, gyorsítótár) FIGYELEM. Csak olvas."""
    try:
        if (home / HOME_KIVETEL).is_file():
            add(INFO, "home írások", f"~/{HOME_KIVETEL} megengedett kivétel (AppKit ablakkeretek; " + (
                f"a telepítési mappa, ~/{HOME_TERMEK_ENGEDETT} mellett az egyetlen hely, ahová a Manifold a home alá ír)" if termek else
                "a belső mentés, ~/Manifold-backup mellett az egyetlen hely, ahová a Manifold a home alá ír)"))
        idegen = []
        for rel in HOME_NEM_ENGEDETT:
            d = home / rel
            if d.is_dir():
                idegen += [f"~/{rel}/{p.name}" for p in d.glob(f"{APP_AZONOSITO}*")
                           if not (termek and f"{rel}/{p.name}" == HOME_TERMEK_ENGEDETT)]
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
                    "nem futhat), a beállítás figyelmen kívül marad: a config/os.toml-ban javítandó")
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


# ------------------------------------------------------------------ F3: termék (csomag) és munkatér (F3-DESIGN §3, §4, §5, §6)

MIN_SZABAD_FIGYELEM = 5 << 30           # ez alatt kevés a hely (pillanatképek, bundle-ök, index nőnek)
MIN_SZABAD_HIBA = 1 << 30               # ez alatt az atomi írás és a mentés megbízhatatlan
_MNT_LOCAL = 0x00001000                  # <sys/mount.h>: a kötet helyi (nem hálózati)


def _formatumok() -> tuple[int, int]:
    """(`FORMATUM`, `FORMATUM_MAX`) a `core/workspace.py`-ból; ha az nem tölthető be, az F3 alapértéke (1, 1). A doctor
    importmentes marad: a venv nélkül és a workspace-modul nélkül is fut."""
    try:
        from . import workspace
        return int(workspace.FORMATUM), int(workspace.FORMATUM_MAX)
    except Exception:  # noqa: BLE001 — bármi, ami a modul betöltését akadályozza, nem állíthatja meg az ellenőrzést
        return 1, 1


def _legkozelebbi(p: Path) -> Path:
    """A legközelebbi létező ős (maga az út, ha létezik)."""
    q = Path(p)
    while not q.exists() and q.parent != q:
        q = q.parent
    return q


def _eszkoz(p: Path) -> int | None:
    """Az út kötetének azonosítója (`st_dev`); nem létező útnál a legközelebbi létező őséé."""
    try:
        return os.stat(_legkozelebbi(p)).st_dev
    except OSError:
        return None


def _alatt(p: Path, anya: Path) -> bool:
    """`p` az `anya` maga vagy alatta áll — a normalizált és a valós (symlinkeket feloldó) írásmód szerint is."""
    for a, b in ((os.path.normpath(p), os.path.normpath(anya)), (os.path.realpath(p), os.path.realpath(anya))):
        if a == b or a.startswith(b.rstrip(os.sep) + os.sep):
            return True
    return False


def _fajlrendszer(ut: Path) -> tuple[str, bool] | None:
    """(a fájlrendszer neve kisbetűvel, helyi-e) a `statfs`-ből (macOS); más rendszeren vagy hibánál None. Külön függvény, hogy a
    teszt lecserélhesse."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        class Statfs(ctypes.Structure):          # <sys/mount.h> struct statfs (64 bites inode-változat)
            _fields_ = [("f_bsize", ctypes.c_uint32), ("f_iosize", ctypes.c_int32), ("f_blocks", ctypes.c_uint64),
                        ("f_bfree", ctypes.c_uint64), ("f_bavail", ctypes.c_uint64), ("f_files", ctypes.c_uint64),
                        ("f_ffree", ctypes.c_uint64), ("f_fsid", ctypes.c_int32 * 2), ("f_owner", ctypes.c_uint32),
                        ("f_type", ctypes.c_uint32), ("f_flags", ctypes.c_uint32), ("f_fssubtype", ctypes.c_uint32),
                        ("f_fstypename", ctypes.c_char * 16), ("f_mntonname", ctypes.c_char * 1024),
                        ("f_mntfromname", ctypes.c_char * 1024), ("f_flags_ext", ctypes.c_uint32),
                        ("f_reserved", ctypes.c_uint32 * 7)]
        libc = ctypes.CDLL(None, use_errno=True)
        fv = getattr(libc, "statfs$INODE64", None) or libc.statfs
        fv.argtypes = [ctypes.c_char_p, ctypes.POINTER(Statfs)]
        fv.restype = ctypes.c_int
        sf = Statfs()
        if fv(os.fsencode(_legkozelebbi(ut)), ctypes.byref(sf)) != 0:
            return None
        return sf.f_fstypename.decode("ascii", "replace").lower(), bool(sf.f_flags & _MNT_LOCAL)
    except (OSError, AttributeError, ValueError):
        return None


def _szinkron_fajta(ut: Path) -> str | None:
    """A mappa szinkronizált-e: `"icloud"` | `"cloudstorage"` | `"dropbox"` | None (az út alapján, a symlinkek feloldásával)."""
    s = os.path.realpath(ut)
    reszek = s.split(os.sep)
    if "/Library/Mobile Documents/" in s + "/":
        return "icloud"
    if "/Library/CloudStorage/" in s + "/":
        mogotte = s.split("/Library/CloudStorage/", 1)[1].split("/", 1)[0]
        return "dropbox" if mogotte.startswith("Dropbox") else "cloudstorage"
    if any(r == "Dropbox" or r.startswith("Dropbox (") for r in reszek):
        return "dropbox"
    q = Path(s)
    if any((a / ".dropbox").is_file() for a in (q, *q.parents)):
        return "dropbox"
    return None


def _szabad_bajt(p: Path) -> int | None:
    """A kötet szabad bájtjai (a legközelebbi létező ősön mérve); külön függvény, hogy a teszt lecserélhesse."""
    try:
        return shutil.disk_usage(_legkozelebbi(p)).free
    except OSError:
        return None


def _codesign(app: Path) -> tuple[int, str]:
    """`codesign --verify --deep --strict` → (visszatérési kód, hibaszöveg); külön függvény, hogy a teszt lecserélhesse."""
    try:
        c = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return c.returncode, c.stderr.strip()


def _bundle_sorok(cfg: config.Config, add) -> None:
    """Termék: a csomag épsége. Az `epites.json` (a felületé az `app_dist` alatt, a héjé a `Contents/Resources/` alatt, mindkettő
    `core.epites.jegyzek` kimenete) megvan és érvényes, a felület `index.html`-je megvan, és a csomagolt `core`+`modulok` ujjlenyomata
    egyezik a héj jegyzékében rögzítettel (a forrás-részek — felület, héj — a csomagban nem újraszámolhatók). Az App Translocation
    (a Gatekeeper a karanténos appot egy írásvédett, véletlen útra másolja) külön jelzés."""
    root = cfg.root
    if "/AppTranslocation/" in str(root) or "/AppTranslocation/" in os.path.realpath(root):
        add(FIGYELEM, "csomag helye", f"az app App Translocation alatt fut ({root}): az útja minden indításkor más, a csomag "
                                      "írásvédett — húzd a Manifoldot az Alkalmazások mappába, és onnan nyisd meg",
            kod="bundle_athelyezett")
    from . import epites
    dist = cfg.path("app_dist")
    hianyzik, hibas, adatok = [], [], {}
    for nev, ut in (("felület", dist / "epites.json"), ("héj", root.parent / "epites.json")):
        try:
            d = json.loads(ut.read_text(encoding="utf-8"))
        except OSError:
            hianyzik.append(f"{nev}: {ut}")
            continue
        except ValueError:
            hibas.append(f"{nev}: {ut.name} nem JSON")
            continue
        if isinstance(d, dict) and d.get("verzio") == 1 and all(isinstance(d.get(x), str) for x in epites.RESZEK):
            adatok[nev] = d
        else:
            hibas.append(f"{nev}: {ut.name} érvénytelen jegyzék")
    if not (dist / "index.html").is_file():
        hianyzik.append(f"felület: {dist / 'index.html'}")
    if hianyzik or hibas:
        add(HIBA, "csomag épsége", f"a csomag hiányos vagy sérült ({_fentiek(hianyzik + hibas)}) — telepítsd újra a Manifoldot",
            kod="bundle_hianyos")
        return
    mag = epites.ujjlenyomat(root, "mag")
    if adatok["héj"]["mag"] != mag:
        add(HIBA, "csomag épsége", f"a csomagolt core és modulok ujjlenyomata ({mag[:12]}) eltér a build jegyzékében rögzítettől "
                                   f"({adatok['héj']['mag'][:12]}): a csomag a build után megváltozott — telepítsd újra a Manifoldot",
            kod="bundle_modositott")
    else:
        add(OK, "csomag épsége", f"az epites.json megvan, a core és a modulok ujjlenyomata egyezik ({mag[:12]})", kod="bundle_epites")


def _i1_sor(cfg: config.Config, add) -> None:
    """I1 (termék): semmi írható nem oldódik fel a csak olvasható kódfa (`{os}`) alá. A `config.load` már megtagadja; a doctor a
    kapott `Config`-ot újra ellenőrzi (pl. közvetlenül épített, vagy környezettel felülírt `Config`-nál)."""
    rossz = [f"{k}={p}" for k, p in sorted(cfg.utak.items()) if k not in config.CSAK_OLVASOTT and _alatt(p, cfg.root)]
    if rossz:
        add(HIBA, "írás a kódfába", f"írható útvonal mutat a csak olvasható csomagba: {_fentiek(rossz)} — a core ide nem írhat",
            kod="iras_a_kodba")
    else:
        add(OK, "írás a kódfába", "minden írható útvonal a csomagon kívül van", kod="iras_a_kodba")


def _kotet_termek(cfg: config.Config, add) -> None:
    """Termék: a `{var}`, a `{tmp}`, a beérkező mappák és a staging a vault kötetén álljon (atomi `os.replace`, APFS-klón)."""
    vault = cfg.utak.get("vault")
    if vault is None or not vault.exists():
        return
    dv = _eszkoz(vault)
    kulon = []
    for k in ("var", "tmp", "fuzet_bejovo", "video_bejovo", "staging"):
        p = cfg.utak.get(k)
        d = _eszkoz(p) if p is not None else None
        if d is not None and dv is not None and d != dv:
            kulon.append(f"{k} ({p})")
    if kulon:
        add(HIBA, "kötet", f"a vault kötetén kívül van: {_fentiek(kulon)} (az atomi csere és a klón nem működik)")
    else:
        add(OK, "kötet", "a var/, a tmp, a beérkező mappák és a staging a vault kötetén vannak")


def _kotet_fajlrendszer(cfg: config.Config, add) -> None:
    """A vault kötete: helyi-e (a `flock` hálózati kötetén megbízhatatlan) és APFS-e (különben nincs próbaklón: a gépi írás
    D9-próbája 503-at ad — csökkentett mód)."""
    vault = cfg.utak.get("vault")
    if vault is None or not vault.is_dir():
        return
    fs = _fajlrendszer(vault)
    if fs is None:
        add(INFO, "vault kötete", "a fájlrendszer fajtája nem állapítható meg", kod="kotet_fajlrendszer")
        return
    nev, helyi = fs
    if not helyi:
        add(HIBA, "vault kötete", f"hálózati kötet ({nev}): a zárak (flock) rajta megbízhatatlanok — a Manifold nem nyithatja meg",
            kod="kotet_halozati")
    elif nev != "apfs":
        add(FIGYELEM, "vault kötete", f"a vault kötete nem APFS ({nev}): nincs APFS-klón, ezért a gépi írások próbakörét a core "
                                      "elutasítja (csökkentett mód)", kod="kotet_nem_apfs")
    else:
        add(OK, "vault kötete", "helyi APFS-kötet", kod="kotet_fajlrendszer")


def _szinkron_sor(cfg: config.Config, add) -> None:
    """A vault szinkronizált mappában van-e (iCloud Drive, CloudStorage, Dropbox). Az állapot (SQLite, git) szinkronizálva megsérül:
    ott a regiszter `allapot = "telepites"`-e az állapotot a telepítési mappába viszi. Nincs szinkronizált mappa → nincs sor."""
    vault, var = cfg.utak.get("vault"), cfg.utak.get("var")
    fajta = _szinkron_fajta(vault) if vault is not None else None
    if fajta is None:
        return
    if var is not None and _alatt(var, vault):
        add(FIGYELEM, "szinkronizált mappa", f"a vault szinkronizált mappában van ({fajta}), és az állapota (var/) is benne áll: az SQLite- "
                                              "és git-állapot szinkronizálva megsérülhet — az állapotnak a telepítési mappában kell lennie",
            kod="szinkron_mappa")
    else:
        add(INFO, "szinkronizált mappa", f"a vault szinkronizált mappában van ({fajta}); az állapot kívül van, a szinkron csak a "
                                          "jegyzeteket és a beállításokat viszi — az előzmény gépenként külön", kod="szinkron_mappa")


def _munkater_sorok(cfg: config.Config, termek: bool, add) -> None:
    """A `{workspace}/workspace.toml`: érvényes-e (TOML, `[workspace] id`, számformátumok), egyezik-e a core azonosítójával, és a
    formátuma olvasható-e / kell-e migráció. Hordozható módban a réteg nem kötelező (csak ha létezik); termékben igen."""
    ws = cfg.utak.get("workspace")
    if ws is None:
        return
    try:                                                # I7/K3: a `.manifold` (var, workspace.toml) link nem lehet
        config.munkater_mappa_ellenoriz(cfg.utak.get("vault") or ws.parent, ws)
    except config.ConfigError as e:
        add(HIBA, "munkatér", f"a munkatér-mappa szimbolikus link, ezért nem használható: {e.param.get('ut', ws)}",
            kod="munkater_symlink")
        return
    ut = ws / "workspace.toml"
    if not ut.is_file():
        if termek:
            var = cfg.utak.get("var")
            reszleges = var is not None and (var / "letrehozas.json").is_file()
            add(HIBA, "munkatér", "nincs workspace.toml: " + ("a létrehozás félbeszakadt (a következő létrehozás folytatja)" if reszleges
                                                               else "a mappa nem Manifold-munkatér"), kod="workspace_toml")
        return
    try:
        adat = config.toml_megbizhatatlan(ut, "workspace_toml_hibas")      # méret- és mélységkorláttal (megbízhatatlan réteg)
    except (OSError, config.ConfigError) as e:
        add(HIBA, "munkatér", f"a workspace.toml nem olvasható: {e}", kod="workspace_toml")
        return
    w = adat.get("workspace")
    w = w if isinstance(w, dict) else {}
    az, formatum, olvaso_min = w.get("id"), w.get("formatum", 1), w.get("olvaso_min", 1)
    hibak = []
    if not (isinstance(az, str) and config.ID_MINTA.match(az)):
        hibak.append("a [workspace] id hiányzik, vagy nem 32 kisbetűs hexa jegy")
    elif cfg.workspace_id and az != cfg.workspace_id:
        hibak.append(f"az id ({az[:8]}…) eltér a core munkatér-azonosítójától ({cfg.workspace_id[:8]}…)")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (formatum, olvaso_min)):
        hibak.append("a formatum és az olvaso_min egész szám kell legyen")
    if hibak:
        add(HIBA, "munkatér", f"a workspace.toml érvénytelen: {'; '.join(hibak)}", kod="workspace_toml")
        return
    add(OK, "munkatér", f"workspace.toml rendben (id {az[:8]}…, formátum {formatum})", kod="workspace_toml")
    fm, fm_max = _formatumok()
    if olvaso_min > fm_max:
        add(HIBA, "munkatér formátuma", f"a munkatér újabb formátumú (olvasáshoz kell: {olvaso_min}, ez a Manifold legfeljebb {fm_max}-t "
                                         "ért): frissítsd a Manifoldot", kod="workspace_ujabb")
    elif formatum < fm:
        add(FIGYELEM, "munkatér formátuma", f"a munkatér formátuma ({formatum}) régebbi a jelenleginél ({fm}): migráció esedékes",
            kod="workspace_migracio")
    else:
        add(OK, "munkatér formátuma", f"formátum {formatum} (olvasáshoz kell: {olvaso_min})", kod="workspace_formatum")


def _lecsatolt(p: str) -> bool:
    """A `/Volumes/<kötet>/…` út kötete nincs csatlakoztatva (ez nem érvénytelen út: a külső lemez még nincs a gépben)."""
    resz = Path(p).parts
    return len(resz) >= 3 and resz[:2] == ("/", "Volumes") and not Path("/Volumes", resz[2]).exists()


def _regiszter_sorok(cfg: config.Config, termek: bool, add) -> None:
    """A gép regisztere (`{install}/workspaces.json`, csak olvasva): olvasható-e, a munkatér benne van-e a mostani útjával, és vannak-e
    benne érvénytelen (nem létező, nem lecsatolt kötetre mutató) utak. Hordozható módban csak ha a fájl létezik."""
    install = cfg.utak.get("install")
    if install is None:
        return
    ut = install / "workspaces.json"
    if not ut.is_file():
        if termek:
            add(INFO, "regiszter", "még nincs munkatér-regiszter (az első megnyitás hozza létre)", kod="regiszter")
        return
    try:
        reg = json.loads(ut.read_text(encoding="utf-8"))
        mt = reg["munkaterek"]
        if not isinstance(mt, dict):
            raise TypeError("munkaterek")
    except (OSError, ValueError, KeyError, TypeError) as e:
        add(FIGYELEM, "regiszter", f"a munkatér-regiszter nem olvasható ({e}): csak a legutóbbiak listája vész el, a munkatér nem — "
                                    "a megnyitás újra felveszi", kod="regiszter")
        return
    gondok = []
    sajat, vault = cfg.workspace_id, cfg.utak.get("vault")
    if sajat:
        e = mt.get(sajat)
        if not isinstance(e, dict):
            gondok.append("a munkatér nincs a regiszterben (a következő megnyitás felveszi)")
        elif vault is not None:
            reg_ut = e.get("kanonikus") or e.get("vault")
            if isinstance(reg_ut, str) and not _azonos_ut(reg_ut, vault):
                gondok.append(f"a regiszter másik helyen ismeri ({reg_ut}): a mappa mozgatva vagy másolva lett — a megnyitás frissíti")
    if gondok:
        add(FIGYELEM, "regiszter", "; ".join(gondok), kod="regiszter")
    else:
        add(OK, "regiszter", f"{len(mt)} munkatér a regiszterben" + (", ez is" if sajat else ""), kod="regiszter")
    ervenytelen, lecsatolt = [], 0
    for az, e in sorted(mt.items()):
        p = e.get("vault") if isinstance(e, dict) else None
        cimke = (e.get("nev") if isinstance(e, dict) else None) or str(az)[:8]
        if not isinstance(p, str) or not p:
            ervenytelen.append(f"{cimke} (nincs út)")
        elif not Path(p).exists():
            if _lecsatolt(p):
                lecsatolt += 1
            else:
                ervenytelen.append(f"{cimke} ({p})")
    if ervenytelen:
        add(FIGYELEM, "regiszter érvénytelen utak", f"{len(ervenytelen)} regisztrált munkatér útja nem létezik: {_fentiek(ervenytelen)} — "
                                                     "a bejegyzés eltávolítható (a fájlokhoz nem nyúl)",
            kod="regiszter_ervenytelen_ut", javitas="regiszter_takarit")


def _azonos_ut(a, b) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a) == os.path.realpath(b)


def _mentes_tulajdonos(cfg: config.Config, add) -> None:
    """A belső mentés mappájának tulajdonosa (egy forrás: `core/mentes.tulajdonos`, csak olvas): másik munkatér jelölője → a régi
    mentések nem forognak; jelölő nélküli, nem üres (örökölt, pl. a v2 és a hordozható közös `~/Manifold-backup`-ja) → csak a saját
    fejű bundle törölhető; a vaultban álló mentési mappát a mentés elutasítja; és a vaulttal azonos lemezen álló mentés lemezhiba
    ellen nem véd."""
    from . import mentes
    backup, vault = cfg.utak.get("backup"), cfg.utak.get("vault")
    if backup is None:
        return
    if vault is not None and _alatt(backup, vault):
        add(HIBA, "mentés helye", f"a mentési mappa ({backup}) a vaultban van: a mentés elmarad (a bundle bekerülne a vault pillanatképébe "
                                   "és a külső mentésbe) — válassz a vaulton kívüli mappát", kod="mentes_a_vaultban")
    try:
        allapot = mentes.tulajdonos(cfg)
    except (AttributeError, OSError, config.ConfigError):
        allapot = None                              # nincs ilyen olvasó (régi mentes.py), vagy a mappa nem olvasható: nincs jelzés
    if allapot == "idegen":
        add(FIGYELEM, "mentés tulajdonosa", f"a mentési mappa ({backup}) másik munkatéré, vagy a jelölője olvashatatlan: a régi "
                                             "mentések nem törlődnek, a forgatás kikapcsolt — válassz ennek a munkatérnek külön mappát",
            kod="mentes_idegen_mappa")
    elif allapot == "orokolt":
        add(FIGYELEM, "mentés tulajdonosa", f"a mentési mappa ({backup}) jelölő nélküli és nem üres (korábbi telepítés vagy másik "
                                             "munkatér használta), vagy a jelölője egy másik, még meglévő mappa (másolat) azonosítóját "
                                             "viseli: csak a saját fejű bundle-ök törölhetők, az állapot- és migrációs másolatok "
                                             "forgatása ki van kapcsolva — válassz külön mappát", kod="mentes_orokolt_mappa")
    elif allapot == "sajat":
        add(OK, "mentés tulajdonosa", "a mentési mappa ennek a munkatérnek a jelölőjét viseli", kod="mentes_tulajdonos")
    if vault is not None:
        dv, db = _eszkoz(vault), _eszkoz(backup)
        if dv is not None and dv == db:
            add(INFO, "mentés lemeze", "a belső mentés a vaulttal azonos lemezen van: lemezhiba ellen nem véd — a teljes mentés külső "
                                        "kötetre véd", kod="mentes_azonos_lemez")


def _elutasitott_sor(cfg: config.Config, add) -> None:
    """A rétegek (telepítés, preset, munkatér) által beállítani próbált, de nem engedett vagy érvénytelen kulcsok (`cfg.elutasitott`)."""
    lista = [f"{reteg}: {kulcs} ({kod})" for reteg, kulcs, kod in getattr(cfg, "elutasitott", [])]
    if lista:
        add(FIGYELEM, "elutasított beállítások", f"{len(lista)} réteg-beállítás nem érvényesült (nem engedett kulcs vagy érvénytelen érték): "
                                                  f"{_fentiek(lista)}", kod="workspace_kulcs_tiltott")
    else:
        add(OK, "elutasított beállítások", "minden réteg-beállítás érvényesült", kod="konfig_kulcsok")


def _telepites_irhato(cfg: config.Config, add) -> None:
    """A `{install}` (modellek, zárak, regiszter, mentések gyökere) írható — vagy a legközelebbi létező őse az, ahol a core létrehozza."""
    install = cfg.utak.get("install")
    if install is None:
        return
    q = _legkozelebbi(install)
    if q.is_dir() and os.access(q, os.W_OK | os.X_OK):
        add(OK, "telepítési mappa", f"{install} írható" + ("" if q == install else " (a core az első indításkor létrehozza)"),
            kod="telepites_irhato")
    else:
        add(HIBA, "telepítési mappa", f"a telepítési mappa nem írható: {q} — a modellek, a zárak és a regiszter nem tárolhatók",
            kod="telepites_irhato")


def _szabad_hely(cfg: config.Config, add) -> None:
    """Szabad hely a vault és a telepítés kötetén (egy sor, a rosszabb állapot dönt)."""
    sorok, allapot = [], OK
    for nev, p in (("vault", cfg.utak.get("vault")), ("telepítés", cfg.utak.get("install"))):
        szabad = _szabad_bajt(p) if p is not None else None
        if szabad is None:
            continue
        sorok.append(f"{nev}: {szabad / 1e9:.1f} GB")
        if szabad < MIN_SZABAD_HIBA:
            allapot = HIBA
        elif szabad < MIN_SZABAD_FIGYELEM and allapot == OK:
            allapot = FIGYELEM
    if not sorok:
        return
    add(allapot, "szabad hely", ", ".join(sorok) + {OK: " szabad", FIGYELEM: " szabad — kevés (a pillanatképek és a mentések nőnek)",
                                                    HIBA: " szabad — kritikusan kevés (az atomi írás és a mentés megbízhatatlan)"}[allapot],
        kod="szabad_hely")


def _zar_helye(cfg: config.Config, environment: dict[str, str], termek: bool, add) -> None:
    """A gépszintű zárak (worker, modell) a `{install}` alatt oldódnak fel, nem a vault állapota alatt. (A modellzár a hordozható
    módban a telepítési réteggel szándékosan máshová is állítható — ott csak a rögzített kulcsokat nézi.)"""
    install = cfg.utak.get("install")
    if install is None:
        return
    rossz = [f"{k}={cfg.utak[k]}" for k in ("install_run", "install_state", "install_logs") if k in cfg.utak and not _alatt(cfg.utak[k], install)]
    zar = cfg.section("modellgazda").get("zar")
    if termek and zar and not environment.get("MANIFOLD_MODELL_ZAR"):
        try:
            if not _alatt(Path(cfg.expand(zar)), install):
                rossz.append(f"modellgazda.zar={cfg.expand(zar)}")
        except config.ConfigError:
            pass
    if rossz:
        add(HIBA, "gépszintű zárak", f"a zárak nem a telepítési mappa alatt vannak: {_fentiek(rossz)} — két munkatér külön zárat kapna",
            kod="zar_helye")
    else:
        add(OK, "gépszintű zárak", "a worker- és modellzárak a telepítési mappa alatt vannak", kod="zar_helye")


def _pid_szam(szoveg: str) -> int | None:
    m = re.match(r"\s*(?:pid\s+)?(\d+)", szoveg or "")
    return int(m.group(1)) if m else None


def _flock_szabad(ut: Path) -> bool | None:
    """A zárfájl `flock`-ja szabad-e (csak olvasva nyit, azonnal elengedi); a fájl hiánya vagy hiba: None."""
    try:
        with open(ut, "r") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(fh, fcntl.LOCK_UN)
            return True
    except OSError:
        return None


def _elavult_zarak(cfg: config.Config, add) -> None:
    """Elakadt `worker.pid`: a worker rendezett kilépéskor törli, tehát a megmaradása összeomlás nyoma. Javítható (`zar_takarit`), ha a
    pid halott ÉS a `worker.lock` flock-ja szabad. (A `core.lock` fájlt a core sosem törli, ezért egy halott pidű, szabad zár az
    ő rendes kilépés utáni állapota — az nem jelzés.) Csak olvas."""
    run = cfg.utak.get("install_run")
    if run is None or not (run / "worker.pid").is_file():
        return
    try:
        pid = _pid_szam((run / "worker.pid").read_text(encoding="utf-8"))
    except OSError:
        return
    if pid is not None and _pid_el(pid):
        return
    szabad = _flock_szabad(run / "worker.lock")
    if szabad is False:
        add(FIGYELEM, "elakadt zár", f"a {run / 'worker.pid'} halott folyamatra mutat, de a worker.lock foglalt: nem törölhető biztonságosan",
            kod="zar_elavult")
    else:
        add(FIGYELEM, "elakadt zár", f"a {run / 'worker.pid'} halott folyamatra mutat (a worker összeomlott); a zár szabad, a fájl törölhető",
            kod="zar_elavult", javitas="zar_takarit")


def _runtime_termek(cfg: config.Config, add) -> None:
    """Termék: a csomagolt Python és Node megvan (a verziójukat a csomag épsége fedi)."""
    runtime = cfg.path("runtime")
    hi = [n for n, p in (("python", runtime / "python" / "bin" / "python3"), ("node", runtime / "node" / "bin" / "node")) if not p.exists()]
    add(HIBA if hi else OK, "runtime", f"a csomagból hiányzik: {', '.join(hi)} — telepítsd újra a Manifoldot" if hi else "Python és Node megvan")


def _cpp_termek(cfg: config.Config, add) -> None:
    """Termék: a C++ eszköztár (`{install}/toolchains`) opcionális — hiánya INFO, nem hiba."""
    llvm, sdk = cfg.path("llvm"), cfg.path("sdk")
    van = all(_futtathato(llvm / "bin" / n) for n in ("clang++", "clang-format", "ld64.lld")) and (sdk / "usr" / "include").is_dir()
    if van:
        add(OK, "C++ eszköztár", f"clang++, clang-format, ld64.lld és az SDK megvan ({llvm.parent})")
    else:
        add(INFO, "C++ eszköztár", "nincs telepítve (opcionális): a C++ munkafelülethez a Beállításokban telepíthető")


def ellenoriz(cfg: config.Config, environment: dict[str, str], home: Path,
              futo_python: Path | None = None, *, termek: bool | None = None) -> list[Eredmeny]:
    """Az ellenőrzések sorra. `termek=None`: a `cfg.elrendezes` dönt (a `*.app` csomag termék, a checkout hordozható). Minden sor
    stabil `kod`-ot, `osztaly`-t és (ha van gépi javítása) `javitas`-t kap."""
    if termek is None:
        termek = cfg.elrendezes == "termek"
    root, r = cfg.root, []

    def add(allapot, nev, uzenet, kod=None, javitas=None, osztaly=None):
        kod = kod or _kod_nevbol(nev)
        if osztaly is None:
            osztaly = "fejleszto" if not termek and (kod in FEJLESZTO_KODOK or kod.startswith(FEJLESZTO_ELOTAGOK)) else "termek"
        r.append(Eredmeny(allapot, nev, uzenet, kod, osztaly, javitas))

    runtime, venv = cfg.path("runtime"), cfg.path("venv")
    var, vault, install = cfg.utak.get("var"), cfg.utak.get("vault"), cfg.utak.get("install")
    futo = Path(futo_python or sys.executable)
    ws_ok = vault is not None and var is not None       # a vaultra és a munkatér állapotára épülő ellenőrzések feltétele

    # gyökér, kötet
    if termek:
        _bundle_sorok(cfg, add)
        _i1_sor(cfg, add)
    else:
        ok = (root / "bin" / "mos").exists() and (root / "config" / "os.toml").exists()
        add(OK if ok else HIBA, "gyökér", str(root) if ok else f"nem érvényes gyökér: {root}")
        if var.exists() and vault is not None and vault.exists():
            add(OK if var.stat().st_dev == vault.stat().st_dev else HIBA, "kötet",
                "a var/ és a vault ugyanazon a köteten van" if var.stat().st_dev == vault.stat().st_dev
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

    # nincs vault / nincs munkatér: a hozzájuk kötött ellenőrzések kimaradnak
    if vault is None:
        add(INFO if termek else HIBA, "vault",
            "nincs megnyitott munkatér (a vaultot a héj adja a MOS_VAULT-tal): csak a gépszintű ellenőrzések futottak" if termek else
            "nincs vault megadva: futtasd a `bin/mos portable init --vault <mappa>` parancsot (vagy add meg a MOS_VAULT-ot)",
            kod="nincs_vault")
    elif var is None:
        add(HIBA, "munkatér", f"a mappa nem Manifold-munkatér ({vault}): nincs .manifold/workspace.toml", kod="nincs_workspace")
    if ws_ok:
        _vault(cfg, environment, add)
        _tarolok_allapota(cfg, add, termek)
        _tarolt_binaris(cfg, add)
        _munkater_sorok(cfg, termek, add)
        _kotet_fajlrendszer(cfg, add)
        if termek:
            _kotet_termek(cfg, add)
        _szinkron_sor(cfg, add)
    _regiszter_sorok(cfg, termek, add)
    _elutasitott_sor(cfg, add)
    _telepites_irhato(cfg, add)
    _szabad_hely(cfg, add)
    _zar_helye(cfg, environment, termek, add)
    _elavult_zarak(cfg, add)

    # rendszer-Python
    sajat = str(futo).startswith(str(runtime)) or str(Path(sys.prefix if futo_python is None else futo)).startswith(str(root))
    tiltott = [t for t in TILTOTT_PYTHON if str(futo).startswith(t)]
    rossz = [] if (sajat and not tiltott) else [f"a futó Python a Manifold-mappán kívül van: {futo}"]
    eszkoztar_kivul = False
    if not termek:
        cfgfile = venv / "pyvenv.cfg"
        if cfgfile.exists():
            szoveg = cfgfile.read_text(encoding="utf-8")
            for kulcs in ("home", "executable", "command"):
                m = re.search(rf"^{kulcs}\s*=\s*(.+)$", szoveg, re.M)
                if m and kulcs != "command" and not m.group(1).strip().startswith(str(runtime)):
                    rossz.append(f"pyvenv.cfg {kulcs} = {m.group(1).strip()}")
            py = venv / "bin" / "python"
            if py.is_symlink() and not str(py.resolve()).startswith(str(runtime.resolve())):
                rossz.append(f"a venv Pythonja a Manifold-mappán kívülre mutat: {py.resolve()}")
            for s in sorted((venv / "bin").glob("*")) if (venv / "bin").is_dir() else []:
                t = _szoveges(s) if not s.is_symlink() else None
                if t and t.startswith("#!") and str(venv) not in "\n".join(t.split("\n")[:3]) \
                        and not t.split("\n", 1)[0][2:].startswith(("/bin/sh", "/usr/bin/env")):
                    rossz.append(f"shebang a Manifold-mappán kívülre mutat: {s.name}")
        else:
            rossz.append(f"nincs venv: {venv} (bin/mos runtime install)")
        # munkafa-mód (bin/mos, T002): a munkafának nincs saját venv-je, az eszköztár a fő checkoutból jön — azt ott kell
        # ellenőrizni; a munkafa állapota (var/) viszont a sajátja, és az alábbi ellenőrzések rá vonatkoznak
        eszkoztar_kivul = bool(environment.get("MOS_MUNKAFA")) and not (venv / "bin" / "python").exists()
    if eszkoztar_kivul:
        add(INFO, "python", "munkafa-mód: a Python és a venv a fő checkoutból jön; ott ellenőrizd (bin/mos doctor)")
    else:
        add(HIBA if rossz else OK, "python", _fentiek(rossz) if rossz else
            ("a csomagolt Python fut" if termek else "a hordozható Python fut, a venv is arra mutat"))

    # ~/Applications, ~/.cache — saját fájlok (csak a forrás-checkouton: a csomag lezárt, az épségét a csomag-sorok adják)
    hibas_sajat = []
    app = root / "Manifold.app"
    if not termek:
        for p in _sajat_fajlok(root):
            t = _szoveges(p)
            if not t:
                continue
            t = _kod(t)
            rel = p.relative_to(root)
            if SAJAT_MINTA.search(t):
                hibas_sajat.append(str(rel))
        if app.exists():
            plist = _szoveges(app / "Contents" / "Info.plist") or ""
            if SAJAT_MINTA.search(plist):
                hibas_sajat.append("Manifold.app/Contents/Info.plist")
        if app.is_symlink() and str(app.resolve()).startswith(str(home / "Applications")):
            hibas_sajat.append("Manifold.app a ~/Applications-re mutat")
    envrosszak = []
    for k, v in sorted(environment.items()):
        if k.startswith(ENV_UTAS) and v:
            if SAJAT_MINTA.search(v) or v.startswith(str(home / ".cache")) or v.startswith(str(home / "Applications")):
                envrosszak.append(f"env {k}={v}")
    add(HIBA if hibas_sajat or envrosszak else OK, "~/Applications, ~/.cache",
        _fentiek(hibas_sajat + envrosszak) if hibas_sajat or envrosszak else "semmi nem használja")

    # vault-séma: a `[sema] vault` feloldódik, és olvasható JSON (termékben a feloldási lánc)
    allapot, uzenet = _sema_ellenor(cfg)
    add(allapot, "vault-séma", uzenet)
    _kivetelek_sor(cfg, add)

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
    add(OK if off else HIBA, "offline", "HF_HUB_OFFLINE=1" if off else
        f"HF_HUB_OFFLINE nincs 1-re állítva ({'a core indításkor állítja' if termek else 'bin/mos állítja'})")

    # runtime
    if termek:
        _runtime_termek(cfg, add)
    else:
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
    _video_ffmpeg(cfg, home, add, termek)
    _modell_reviziok(cfg, add)

    # app
    if termek:
        app = root.parents[2] if len(root.parents) > 2 else root
        rc, hiba = _codesign(app)
        add(OK if rc == 0 else HIBA, "Manifold.app", "megvan, aláírása érvényes" if rc == 0 else f"aláírás: {hiba}")
        _alairas(app, add)
        _naptar(cfg, add)
    else:
        if app.exists():
            rc, hiba = _codesign(app)
            add(OK if rc == 0 else HIBA, "Manifold.app", "megvan, aláírása érvényes" if rc == 0 else f"aláírás: {hiba}")
        else:
            add(HIBA, "Manifold.app", "hiányzik (shell/build.sh)")
        if app.exists():
            _alairas(app, add)
            _naptar(cfg, add)
    _home_irasok(home, add, termek)
    if not termek:
        _napi_canvas(root, add)
    if var is not None:
        _never_index(var, add, install if termek else None)
    if not termek:
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
    if ws_ok and "backup" in cfg.utak:
        _mentes(cfg, add)
        _mentes_tulajdonos(cfg, add)
    if var is not None:
        _index(cfg, add)
        if not termek:
            _kapu(cfg, add)
    if termek:
        _cpp_termek(cfg, add)
    else:
        _cpp(cfg, add, eszkoztar_kivul)
    if var is not None:
        _proba_klonok(cfg, add)
        _core_fut(cfg, add)
    if environment.get("MOS_OSSZEOMLAS"):
        add(HIBA, "összeomlás-horog", f"MOS_OSSZEOMLAS={environment['MOS_OSSZEOMLAS']}: az összeomlás-injektáló horog be van "
                                      "kapcsolva (csak a tesztállványé, éles környezetben soha)")
    return r


def jelentes(elrendezes: str | None, eredmenyek: list[Eredmeny]) -> dict:
    """A `--json` kimenet: az elrendezés, az összesítés és a sorok (`kod`, `allapot`, `nev`, `uzenet`, `osztaly`, `javitas`)."""
    szamok = {a: sum(1 for e in eredmenyek if e.allapot == a) for a in (OK, HIBA, FIGYELEM, INFO)}
    return {"verzio": 1, "elrendezes": elrendezes, "zold": szamok[HIBA] == 0, "osszesen": szamok,
            "eredmenyek": [e.szotar() for e in eredmenyek]}


def main(argv: list[str]) -> int:
    json_ki = "--json" in argv
    try:
        try:
            cfg = config.load()
        except config.ConfigError as e:
            if e.kod != "nem_workspace":
                raise
            cfg = config.load(munkater=False)           # termék munkatér nélkül: a gépszintű ellenőrzések így is futnak
        eredmenyek = ellenoriz(cfg, dict(os.environ), Path(os.environ.get("HOME", "~")).expanduser())
    except config.ConfigError as e:                     # a hibás konfiguráció maga a jelzés, nem traceback
        cfg, eredmenyek = None, [Eredmeny(HIBA, "konfiguráció", str(e), kod=e.kod, osztaly="termek")]
    if json_ki:
        print(json.dumps(jelentes(cfg.elrendezes if cfg is not None else None, eredmenyek), ensure_ascii=False, indent=2))
        return 1 if any(e.allapot == HIBA for e in eredmenyek) else 0
    jel = {OK: "✓", HIBA: "✗", INFO: "·", FIGYELEM: "!"}
    for e in eredmenyek:
        print(f"{jel[e.allapot]} {e.nev}: {e.uzenet}" + (f" [javítás: {e.javitas}]" if e.javitas else ""))
    piros = [e for e in eredmenyek if e.allapot == HIBA]
    print("\nA doctor zöld." if not piros else f"\nA doctor piros: {len(piros)} hiba.")
    return 1 if piros else 0
