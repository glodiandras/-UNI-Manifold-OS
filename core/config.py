"""Út-feloldás és rétegzett konfiguráció (LEGACY-SZERZODESEK L49; F3-DESIGN §2). Kódban abszolút út nem állhat.

Rétegek (a későbbi nyer; a táblák mélyen egyesülnek, a skalárok és a listák cserélődnek):
  S     `config/os.toml` (a `MOS_CONFIG` kijelöli), termék elrendezésben előbb az `[elrendezes.termek]` különbségeivel
  P(I)  a telepítési réteg `[telepites] presetek` presetjei (`config/presets/<nev>.toml`), a telepítési engedélylistával szűrve
  I     `{install}/settings.toml` (a `MOS_SETTINGS` felülírja; üres érték: a kódot hordozó checkout telepítési rétege kimarad)
  P(W)  a munkatér `[workspace] presetek` presetjei, a munkatér-engedélylistával szűrve
  W     `{workspace}/workspace.toml` (ha létezik) — MEGBÍZHATATLAN réteg: a vault utazik, szinkronizálódik, letölthető
  E     `MOS_<KULCS>` minden `[utak]` kulcsra, továbbá `MOS_ELRENDEZES`, `MOS_WORKSPACE_ID`, `MOS_SETTINGS`

A helyőrzők: `{os}` (a csomag helyéből, a `MOS_ROOT` felülírja), `{home}`, `{workspace_id}` és bármely `[utak]` kulcs.
Körkörös vagy ismeretlen helyőrző `ConfigError`: a hívó jelenti, nem javítja. A hiányzó vaultra/munkatérre épülő kulcsok
halasztottak (`Config.feloldatlan`): a `path()` csak az első használatkor ad `ConfigError(kod="nincs_vault"|"nincs_workspace")`-t.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
import stat
import tomllib
import unicodedata
from pathlib import Path
from typing import Mapping

from . import fejleszto, regex_biztonsag

_HELYORZO = re.compile(r"\{(\w+)\}")
_MAX_MELYSEG = 12

# Az app egyetlen azonosítója (reverse-DNS; a `shell/Info.plist` CFBundleIdentifier-e). Ebből képződik a doctor
# home-kivétele (`~/Library/Preferences/<id>.plist`) és a fájlfigyelő dispatch-sorának neve.
BUNDLE_ID = "com.manifold.app"

MUNKATER_MAPPA = ".manifold"
ELRENDEZESEK = ("hordozhato", "termek")
# `\A…\Z`, nem `^…$`: a `$` a záró újsor előtt is illik (az `"…32hex…\n"` azonosító így átment volna, és útszegmens lett volna belőle)
ID_MINTA = re.compile(r"\A[0-9a-f]{32}\Z")
PRESET_NEV = re.compile(r"\A[a-z0-9-]+\Z")

# A kódot hordozó checkout (nem a `MOS_ROOT`): az üres `MOS_SETTINGS` csak ennek a telepítési rétegét kapcsolja ki
_KOD_GYOKER = Path(__file__).resolve().parent.parent

# Halasztott kulcsok kódjai
NINCS_VAULT = "nincs_vault"
NINCS_WORKSPACE = "nincs_workspace"

# `[utak]` kulcsok, amelyeknek az S rétegben nincs alapértéke (az E vagy az I adja); hiányukban halasztottak
ALAP_NELKULI = {"vault": NINCS_VAULT}

# I1: termék elrendezésben minden ÍRHATÓ `[utak]` kulcs az `{os}`-on kívül oldódik fel; ezek csak olvasottak (a csomag része)
CSAK_OLVASOTT = frozenset({"modulok", "runtime", "app_dist", "ffmpeg", "node", "sandbox_exec", "naptar_seged", "hej_cli",
                           "venv"})

# Melyik réteg melyik kulcsot állíthatja (pontozott kulcs-minták, `fnmatch`; az `!`-es minta tilt, és megelőzi az engedélyt).
# Az engedélylistán kívüli kulcs elutasított (`cfg.elutasitott`), nem végzetes.
_MUNKATER = (
    "workspace.id", "workspace.formatum", "workspace.olvaso_min", "workspace.nev", "workspace.nyelv", "workspace.presetek",
    "workspace.obsidian_letrehozva",
    "vault.kisero_elotag",
    "naplo.*", "sablon.*",
    "kartya.mappa", "kartya.utotag", "kviz.mappa", "osszefoglalas.mappa", "osszefoglalas.utotag",
    "fuzet.cel_mappa", "fuzet.elmelet_mappa", "fuzet.szakasz",
    "media.*", "pdf.tags.*", "pdf.nevek.*",
    "video.vault_mappa", "video.tema_minta", "video.kizart_mappak",
    "naptar.szotar.*",
    "asszisztens.*_kizart", "asszisztens.tantargy_nevek.*",
    "kapuk.kihagyott_szakaszok",
    # a `kalibralt` jelző (a CLI írja) és a `kalibracio_*` paraméterek (köztük a `kalibracio_min` küszöb) gépi illesztés kapui: a vault nem állíthatja
    "felkeszultseg.*", "!felkeszultseg.kalibral*", "!felkeszultseg.kalibrac*",
    "sema.mod",
    "modulok.*",
)
RETEG_JOG: dict[str, tuple[str, ...]] = {
    "munkater": _MUNKATER,
    # a gép és a személy rétege; minden W-kulcs is (gépi alapértékként a W alatt), kivéve a mappa azonosságát
    "telepites": (
        "utak.backup_gyoker", "utak.models",
        "modellgazda.min_szabad_szazalek",
        "keret.*", "aktivitas.*",
        "mentes.ido_perc", "mentes.allapot_*", "mentes.megtartott_bundle", "mentes.megtartott_migracio",
        "teljes_mentes.cel", "teljes_mentes.figyelo_be", "teljes_mentes.figyelo_ora", "teljes_mentes.megtartott",
        "naptar.automatikus", "naptar.szinkron_perc", "naptar.tanulas_naptar",
        "adatvedelem.*", "felulet.*", "modulok.*",
        "munkaterek.*.fuzet.mappak",
        "telepites.presetek",
        "!workspace.id", "!workspace.formatum", "!workspace.olvaso_min",
    ) + _MUNKATER,
    # csak hordozható elrendezésben, a telepítési réteg kiegészítése
    "telepites_hordozhato": (
        "utak.vault", "utak.backup", "utak.llvm", "utak.sdk",
        "fuzet.mappak",
        "modellgazda.zar",
        "hordozhato.idegen_zarak",
    ),
}

# Új (az alapban nem létező) kulcs csak ezek alatt keletkezhet; a többi rétegkulcs típusa az alapértéké
UJ_KULCS_ENGEDETT = ("pdf.tags.*", "pdf.nevek.*", "naptar.szotar.*", "asszisztens.tantargy_nevek.*")
# A réteg saját (az S-ben nem szereplő) kulcsai és típusuk
META_TIPUS: dict[str, type] = {
    "utak.vault": str, "utak.backup": str, "utak.llvm": str, "utak.sdk": str, "utak.backup_gyoker": str, "utak.models": str,
    "telepites.presetek": list, "hordozhato.idegen_zarak": list,
    "workspace.id": str, "workspace.formatum": int, "workspace.olvaso_min": int, "workspace.nev": str,
    "workspace.nyelv": str, "workspace.presetek": list, "workspace.obsidian_letrehozva": bool,
    "munkaterek.*.fuzet.mappak": list,
}
# Vault-relatív út értékek: NFC, nem abszolút, nincs `..`, nincs pontos szakasz (`.manifold/…`, `.obsidian/…`), nincs helyőrző
UT_KULCSOK = ("naplo.ut", "*.mappa", "*_mappa", "sablon.mappa", "fuzet.cel_mappa", "media.*", "video.vault_mappa",
              "video.kizart_mappak", "*_kizart")
REGEX_KULCSOK = ("video.tema_minta",)
# Mappanévbe, fájlnévbe és frontmatterbe kerülő szövegek (nem út): nincs `/`, `\\`, `..`, kezdő pont, helyőrző; NFC; rövid
NEV_KULCSOK = ("vault.kisero_elotag", "*.utotag")
MAX_NEV = 64
MAX_SZOVEG = 512
MAX_LISTA = 256
MAX_REGEX = regex_biztonsag.MAX_HOSSZ
MIN_BUNDLE = 3
# A megbízhatatlan rétegek (I: a felhasználó gépe, de szerkeszthető; W: a vault) fájlja: méret- és mélységkorlát (a mélyen beágyazott
# tábla a rekurzív szűrőn / egyesítőn `RecursionError`, a nagy fájl memóriaevés lenne — mindkettő „hibás réteg”, nem összeomlás)
MAX_TOML_BAJT = 1 << 20
MAX_TOML_MELYSEG = 8
# A vezérlőkarakterek (az újsor, az U+2028, … a frontmatteret és a commit-metaadatot hamisítanák): a `vaultio._UT_VEZERLO` társa
_VEZERLO = re.compile("[\x00-\x08\x0a-\x1f\x7f\x85\u2028\u2029]")


class ConfigError(ValueError):
    """Hibás vagy feloldhatatlan konfiguráció (F4 hibaszerződés: `kod` + `param` + szöveges tartalék)."""

    def __init__(self, uzenet: str, *, kod: str = "konfig_hiba", param: dict | None = None):
        super().__init__(uzenet)
        self.kod = kod
        self.param = dict(param or {})


def os_root() -> Path:
    """A gyökér: `MOS_ROOT`, különben a csomag saját helyéből."""
    env = os.environ.get("MOS_ROOT")
    return Path(env).resolve() if env else _KOD_GYOKER


def expand(template: str, table: dict[str, str], _stack: tuple[str, ...] = (), *,
           hianyzo: Mapping[str, str] | None = None) -> str:
    """Helyőrzők feloldása a `table` alapján, rekurzívan; a végén normalizált út (a legacy szabálya). A `hianyzo` kulcsára
    (a hiányzó vault/munkatér) `ConfigError(kod=<a hiány kódja>)`."""
    if len(_stack) > _MAX_MELYSEG:
        raise ConfigError(f"túl mély helyőrző-lánc: {' → '.join(_stack)}", kod="helyorzo_melyseg")

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key in _stack:
            raise ConfigError(f"körkörös helyőrző: {' → '.join(_stack + (key,))}", kod="helyorzo_korkoros",
                              param={"lanc": list(_stack + (key,))})
        if hianyzo and key in hianyzo:
            raise ConfigError(f"a(z) {{{key}}} nincs megadva ({template!r})", kod=hianyzo[key], param={"kulcs": key})
        if key not in table:
            raise ConfigError(f"ismeretlen helyőrző: {{{key}}} ({template!r})", kod="helyorzo_ismeretlen",
                              param={"kulcs": key})
        return expand(table[key], table, _stack + (key,), hianyzo=hianyzo)

    out = os.path.expanduser(_HELYORZO.sub(sub, template))
    return os.path.normpath(out) if ("/" in out or out.startswith("~")) else out


def utak_kulcsok(data: dict) -> list[str]:
    """Minden `[utak]` kulcs neve: az adatbeliek és az alapérték nélküliek (`vault`)."""
    utak = data.get("utak", {})
    return list(utak) + [k for k in ALAP_NELKULI if k not in utak]


class Config:
    """A feloldott konfiguráció. `Config(root, cfg.data, env)` ugyanazt adja (a `data["_meta"]` hordozza az elrendezést,
    a munkatér-azonosítót és a rétegek forrását), ezért a próbaklón a már egyesített adatból épül, rétegek újraolvasása nélkül."""

    def __init__(self, root: Path, data: dict, environment: dict[str, str], source: Path | None = None):
        self.root = root
        self.data = data
        self.source = source
        meta = data.get("_meta", {}) or {}
        self.elrendezes: str = meta.get("elrendezes") or "hordozhato"
        self.workspace_id: str | None = environment.get("MOS_WORKSPACE_ID") or meta.get("workspace_id") or None
        self.table: dict[str, str] = {
            "os": str(root), "home": str(Path(environment.get("HOME", "~")).expanduser())}
        utak = data.get("utak", {})
        kulcsok = utak_kulcsok(data)
        env_kulcsok = set()
        for kulcs in kulcsok:
            ertek = environment.get(f"MOS_{kulcs.upper()}")
            if ertek:
                env_kulcsok.add(kulcs)
            else:
                ertek = utak.get(kulcs)
            if ertek:
                self.table[kulcs] = ertek
        if self.workspace_id:
            self.table["workspace_id"] = self.workspace_id
        hianyzo = {k: kod for k, kod in ALAP_NELKULI.items() if k not in self.table}
        if meta.get("munkater_hianyzik") and "workspace" not in env_kulcsok and "vault" in self.table:
            hianyzo.setdefault("workspace", NINCS_WORKSPACE)
            self.table.pop("workspace", None)
        if "workspace_id" not in self.table:
            hianyzo["workspace_id"] = NINCS_WORKSPACE
        self._hianyzo = hianyzo
        self.utak: dict[str, Path] = {}
        self.feloldatlan: dict[str, str] = {}
        for k in kulcsok:
            if k in hianyzo:
                self.feloldatlan[k] = hianyzo[k]
                continue
            try:
                self.utak[k] = Path(expand(f"{{{k}}}", self.table, hianyzo=hianyzo))
            except ConfigError as e:
                if e.kod not in (NINCS_VAULT, NINCS_WORKSPACE):
                    raise
                self.feloldatlan[k] = e.kod
        self.retegek: dict[str, str] = dict(meta.get("retegek") or {})
        for k in env_kulcsok:
            self.retegek[f"utak.{k}"] = "env"
        self.elutasitott: list[tuple[str, str, str]] = [tuple(x) for x in (meta.get("elutasitott") or [])]

    def path(self, kulcs: str) -> Path:
        if kulcs in self.utak:
            return self.utak[kulcs]
        if kulcs in self.feloldatlan:
            kod = self.feloldatlan[kulcs]
            mi = "nincs megadott vault" if kod == NINCS_VAULT else "nincs megnyitott munkatér"
            raise ConfigError(f"a(z) {kulcs} út nem oldható fel: {mi}", kod=kod, param={"kulcs": kulcs})
        raise ConfigError(f"nincs ilyen út a konfigurációban: {kulcs}", kod="ismeretlen_ut", param={"kulcs": kulcs})

    def expand(self, template: str) -> str:
        return expand(template, self.table, hianyzo=self._hianyzo)

    def section(self, *keys: str) -> dict:
        node = self.data
        for k in keys:
            node = node.get(k, {})
        return node

    def forras(self, *kulcs_ut: str) -> str:
        """Egy kulcs értékének eredete: `os` | `os:termek` | `preset:<nev>` | `telepites` | `munkater` | `regiszter` | `env`.
        Táblára a legutóbb felülírt levele rétege, ha van ilyen; különben `os`."""
        kulcs = ".".join(kulcs_ut)
        if kulcs in self.retegek:
            return self.retegek[kulcs]
        alatta = [r for k, r in self.retegek.items() if k.startswith(kulcs + ".")]
        return alatta[-1] if alatta else "os"


# ------------------------------------------------------------------ elrendezés


def _bundle_gyoker(root: Path) -> bool:
    """`*.app/Contents/Resources/manifold` alakú-e a gyökér."""
    p = Path(root).parts
    return len(p) >= 4 and p[-1] == "manifold" and p[-2] == "Resources" and p[-3] == "Contents" and p[-4].endswith(".app")


def elrendezes(root: Path, env: Mapping[str, str]) -> str:
    """A gyökér elrendezése: `MOS_ELRENDEZES` (`hordozhato|termek`), különben `termek`, ha a gyökér egy app-csomag
    `Contents/Resources/manifold`-ja, egyébként `hordozhato` (a fejlesztői checkout és a tesztek álgyökerei). Hordozható
    elrendezés app-csomagban csak Developer módban."""
    kert = env.get("MOS_ELRENDEZES") or ""
    if kert and kert not in ELRENDEZESEK:
        raise ConfigError(f"ismeretlen elrendezés: MOS_ELRENDEZES={kert!r} (hordozhato | termek)", kod="elrendezes_ismeretlen",
                          param={"ertek": kert})
    bundle = _bundle_gyoker(root)
    e = kert or ("termek" if bundle else "hordozhato")
    if e == "hordozhato" and bundle and not fejleszto.aktiv(env):
        raise ConfigError("hordozható elrendezés app-csomagban csak Developer módban indítható", kod="hordozhato_bundleben",
                          param={"gyoker": str(root)})
    return e


# ------------------------------------------------------------------ rétegek


def _melyseg(d) -> int:
    """A beágyazott táblák/listák legnagyobb mélysége (iteratív: a rekurzív bejárás maga lenne a támadási felület)."""
    legnagyobb, verem = 0, [(d, 0)]
    while verem:
        x, m = verem.pop()
        if isinstance(x, dict):
            legnagyobb = max(legnagyobb, m)
            verem.extend((v, m + 1) for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            legnagyobb = max(legnagyobb, m)
            verem.extend((v, m + 1) for v in x if isinstance(v, (dict, list)))
    return legnagyobb


def _toml_olvas(ut: Path, kod: str, *, megbizhatatlan: bool = False) -> dict:
    """Egy TOML-réteg beolvasása. A hiányzó fájl `FileNotFoundError` (a hívó dönt). Minden más hiba — szintaxis, kódolás, olvashatatlan
    fájl, `RecursionError`, és `megbizhatatlan` rétegnél (I, W) a `MAX_TOML_BAJT`-nál nagyobb fájl vagy a `MAX_TOML_MELYSEG`-nél
    mélyebb beágyazás — `ConfigError(kod)`: a hibás réteg jelzés, nem traceback."""
    def hiba(ok: str, **param) -> ConfigError:
        return ConfigError(f"hibás TOML: {ut}: {ok}", kod=kod, param={"ut": str(ut), "hiba": ok, **param})

    try:
        with open(ut, "rb") as f:
            nyers = f.read(MAX_TOML_BAJT + 1) if megbizhatatlan else f.read()
        if megbizhatatlan and len(nyers) > MAX_TOML_BAJT:
            raise hiba("a fájl túl nagy", max_bajt=MAX_TOML_BAJT)
        adat = tomllib.loads(nyers.decode("utf-8"))
        if megbizhatatlan and _melyseg(adat) > MAX_TOML_MELYSEG:
            raise hiba("túl mély beágyazás", max_melyseg=MAX_TOML_MELYSEG)
        return adat
    except (ConfigError, FileNotFoundError, NotADirectoryError):
        raise
    except tomllib.TOMLDecodeError as exc:
        raise hiba(str(exc)) from exc
    except (UnicodeDecodeError, RecursionError, MemoryError, OSError, ValueError) as exc:
        raise hiba(f"{type(exc).__name__}") from exc


def toml_megbizhatatlan(ut: Path, kod: str) -> dict:
    """Egy megbízhatatlan réteg-fájl (a munkatér `workspace.toml`-ja, a telepítési `settings.toml`) korlátozott beolvasása — a
    `workspace` és a `doctor` is ezt használja; a hiányzó fájl `FileNotFoundError`."""
    return _toml_olvas(Path(ut), kod, megbizhatatlan=True)


def _melyegyesit(alap: dict, felul: dict, retegek: dict | None = None, reteg: str = "", _elotag: str = "") -> dict:
    """Mélyegyesítés: a táblák egyesülnek, a skalárok és a listák cserélődnek. Új dict (az `alap` érintetlen). A `retegek`-be
    a felülírt levelek pontozott kulcsa → a `reteg` neve kerül."""
    ki = dict(alap)
    for k, v in felul.items():
        teljes = f"{_elotag}{k}"
        if isinstance(v, dict) and isinstance(ki.get(k), dict):
            ki[k] = _melyegyesit(ki[k], v, retegek, reteg, teljes + ".")
        else:
            ki[k] = copy.deepcopy(v)
            if retegek is not None:
                if isinstance(v, dict):
                    for lev in _levelek(v, teljes + "."):
                        retegek[lev] = reteg
                else:
                    retegek[teljes] = reteg
    return ki


def _levelek(d: dict, elotag: str = ""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _levelek(v, f"{elotag}{k}.")
        else:
            yield f"{elotag}{k}"


def _illik(kulcs: str, mintak) -> bool:
    return any(fnmatch.fnmatchcase(kulcs, m) for m in mintak)


def _engedett(reteg: str, kulcs: str) -> bool:
    mintak = list(RETEG_JOG["telepites"]) + list(RETEG_JOG["telepites_hordozhato"]) if reteg == "telepites_hordozhato" \
        else list(RETEG_JOG[reteg])
    if _illik(kulcs, [m[1:] for m in mintak if m.startswith("!")]):
        return False
    return _illik(kulcs, [m for m in mintak if not m.startswith("!")])


def _keres(d: dict, kulcs: str):
    node = d
    for r in kulcs.split("."):
        if not isinstance(node, dict) or r not in node:
            return _NINCS
        node = node[r]
    return node


_NINCS = object()


def _ut_hiba(ertek: str) -> str | None:
    if unicodedata.normalize("NFC", ertek) != ertek:
        return "ut_nem_nfc"
    if ertek.startswith(("/", "~")) or "\\" in ertek or "{" in ertek or "}" in ertek:
        return "ut_abszolut"
    reszek = [r for r in ertek.split("/") if r]
    if any(r == ".." for r in reszek):
        return "ut_szulo"
    if any(r.startswith(".") for r in reszek):
        return "ut_pontos_szakasz"
    return None


def _nev_hiba(ertek: str) -> str | None:
    """Egy mappanévbe / fájlnévbe kerülő szöveg (`NEV_KULCSOK`): nem út, nem rejtett, nem helyőrző, NFC, rövid."""
    if unicodedata.normalize("NFC", ertek) != ertek:
        return "ut_nem_nfc"
    if len(ertek) > MAX_NEV:
        return "nev_hossz"
    if "/" in ertek or "\\" in ertek or ".." in ertek or "{" in ertek or "}" in ertek or ertek.startswith("~"):
        return "nev_ervenytelen"
    if ertek.startswith("."):
        return "ut_pontos_szakasz"
    return None


def _ertek_hiba(reteg: str, kulcs: str, ertek, alap, gyoker: Path | None) -> tuple[str | None, object]:
    """Egy levél ellenőrzése → (hibakód vagy None, a tárolandó érték). Az `alap` a meglévő érték (`_NINCS`: új kulcs)."""
    meta = next((t for m, t in META_TIPUS.items() if fnmatch.fnmatchcase(kulcs, m)), None)
    if meta is not None:
        varhato = meta
    elif alap is _NINCS:
        if not _illik(kulcs, UJ_KULCS_ENGEDETT):
            return "ismeretlen_kulcs", None
        varhato = type(ertek) if isinstance(ertek, (str, int, float, bool, list)) else None
        if varhato is None:
            return "tipus", None
    else:
        varhato = type(alap)
    if varhato is float and type(ertek) is int:
        ertek = float(ertek)
    if type(ertek) is not varhato:
        return "tipus", None
    elemek = ertek if isinstance(ertek, list) else [ertek]
    if isinstance(ertek, list):
        if len(ertek) > MAX_LISTA:
            return "lista_hossz", None
        mintaelem = alap[0] if isinstance(alap, list) and alap else None
        for x in ertek:
            if isinstance(x, (dict, list)):
                return "tipus", None
            if mintaelem is not None and type(x) is not type(mintaelem):
                return "tipus", None
    szovegek = [x for x in elemek if isinstance(x, str)]
    if any(len(s) > MAX_SZOVEG for s in szovegek):
        return "szoveg_hossz", None
    if any(_VEZERLO.search(s) for s in szovegek):      # mappanév, címke, frontmatter-érték: az újsor új kulcsot (`Status: …`) hamisítana
        return "vezerlo_karakter", None
    if _illik(kulcs, REGEX_KULCSOK):
        for s in szovegek:
            if len(s) > MAX_REGEX:
                return "regex_hossz", None
            h = regex_biztonsag.veszelyes(s)           # fordítható, és nincs katasztrofális visszalépést engedő beágyazott ismétlés
            if h:
                return h, None
    elif reteg == "munkater" and any(s.startswith(("/", "~")) for s in szovegek):
        return "ut_abszolut", None
    if _illik(kulcs, NEV_KULCSOK):
        for s in szovegek:
            h = _nev_hiba(s)
            if h:
                return h, None
    if _illik(kulcs, UT_KULCSOK):
        for s in szovegek:
            h = _ut_hiba(s)
            if h:
                return h, None
    if kulcs == "workspace.id" and not ID_MINTA.match(ertek):
        return "id", None
    if kulcs in ("telepites.presetek", "workspace.presetek"):
        for nev in ertek:
            if not isinstance(nev, str) or not PRESET_NEV.match(nev) or gyoker is None \
                    or not (gyoker / "config" / "presets" / f"{nev}.toml").is_file():
                return "preset_ismeretlen", None
    if kulcs in ("hordozhato.idegen_zarak", "telepites.presetek", "workspace.presetek", "fuzet.mappak") \
            or kulcs.endswith(".fuzet.mappak"):
        if any(not isinstance(x, str) for x in ertek):
            return "tipus", None
    if kulcs == "mentes.megtartott_bundle" and ertek < MIN_BUNDLE:
        return "tartomany", None
    return None, ertek


def _szur(reteg: str, valtozasok: dict, alap: dict, gyoker: Path | None = None,
          _elotag: str = "") -> tuple[dict, list[tuple[str, str]]]:
    """A réteg engedélylistájával és az értékszabályokkal szűrt változások → (elfogadott, [(kulcs, ok)])."""
    elfogadott: dict = {}
    elutasitott: list[tuple[str, str]] = []
    for k, v in valtozasok.items():
        kulcs = f"{_elotag}{k}"
        if _VEZERLO.search(str(k)):                    # a kulcs maga is lehet útszakasz / címke (`pdf.tags.<betű>`): a naplóba nem kerülhet nyersen
            elutasitott.append((kulcs.encode("unicode_escape").decode("ascii"), "vezerlo_karakter"))
            continue
        meglevo = alap.get(k, _NINCS) if isinstance(alap, dict) else _NINCS
        if isinstance(v, dict):
            if meglevo is not _NINCS and not isinstance(meglevo, dict):
                elutasitott.append((kulcs, "tipus"))
                continue
            al, rossz = _szur(reteg, v, meglevo if isinstance(meglevo, dict) else {}, gyoker, kulcs + ".")
            if al:
                elfogadott[k] = al
            elutasitott += rossz
            continue
        if not _engedett(reteg, kulcs):
            elutasitott.append((kulcs, "reteg_tiltott"))
            continue
        hiba, ertek = _ertek_hiba(reteg, kulcs, v, meglevo, gyoker)
        if hiba:
            elutasitott.append((kulcs, hiba))
        else:
            elfogadott[k] = ertek
    return elfogadott, elutasitott


def reteg_ellenoriz(reteg: str, valtozasok: dict, alap: dict, gyoker: Path | None = None) -> list[tuple[str, str]]:
    """A `reteg` (`telepites` | `telepites_hordozhato` | `munkater`) által nem állítható vagy érvénytelen kulcsok
    (pontozott kulcs, ok-kód). Üres lista: minden változás elfogadható (az F5 beállítás-írója is ezt hívja)."""
    if reteg not in RETEG_JOG:
        raise ConfigError(f"ismeretlen réteg: {reteg}", kod="reteg_ismeretlen", param={"reteg": reteg})
    return _szur(reteg, valtozasok, alap, gyoker)[1]


def _settings_ut(env: Mapping[str, str], root: Path, install: Path | None) -> Path | None:
    """A telepítési réteg fájlja: a nem üres `MOS_SETTINGS`, különben `{install}/settings.toml`. Az üres `MOS_SETTINGS`
    (a `bin/mos test|perf` exportálja) a kódot hordozó checkout rétegét kapcsolja ki — a hívó környezetében vagy a folyamatéban
    —, így a tesztek a fejlesztő saját rétegét nem látják, az álgyökerek (más `MOS_ROOT`) viszont a sajátjukat igen."""
    ertek = env.get("MOS_SETTINGS")
    if ertek:
        return Path(os.path.expanduser(ertek))
    if Path(root).resolve() == _KOD_GYOKER and "" in (env.get("MOS_SETTINGS"), os.environ.get("MOS_SETTINGS")):
        return None
    return install / "settings.toml" if install is not None else None


def _presetek(nevek, reteg: str, data: dict, root: Path, retegek: dict, elutasitott: list) -> dict:
    for nev in nevek or []:
        ut = root / "config" / "presets" / f"{nev}.toml"
        p = _toml_olvas(ut, kod="preset_toml_hibas")
        ok, rossz = _szur(reteg, p, data, root)
        data = _melyegyesit(data, ok, retegek, f"preset:{nev}")
        elutasitott += [(f"preset:{nev}", k, kod) for k, kod in rossz]
    return data


def _bejegyzes_ez_a_vault(e: dict, vault: Path | None) -> bool:
    """A regiszter-bejegyzés ehhez a vaulthoz tartozik-e (kanonikus út vagy fájlrendszer-azonosság): a `workspace.toml` azonosítója
    a vaulttal utazik, ezért önmagában nem bizonyíték — egy másolat, egy letöltött vault ugyanazt az azonosítót hordozhatja."""
    if vault is None:
        return False
    for kulcs in ("kanonikus", "vault"):
        ut = e.get(kulcs)
        if isinstance(ut, str) and ut:
            try:
                if os.path.samefile(ut, vault):
                    return True
            except OSError:
                continue
    return False


def _regiszter_allapot(install: Path, workspace_id: str, vault: Path | None = None) -> str | None:
    """A gép regiszteréből (`{install}/workspaces.json`, csak olvasva) a munkatér állapot-helye: `vault` | `telepites`. Csak akkor, ha a
    bejegyzés ehhez a `vault`hoz tartozik (`_bejegyzes_ez_a_vault`): egy idegen vault, amely egy regisztrált szinkronmappa-munkatér
    azonosítóját hordozza, nem kapja meg annak állapotát; az azonosító ilyenkor „nem regisztrált” (a `workspace.nyit` rendezi)."""
    try:
        r = json.loads((install / "workspaces.json").read_text(encoding="utf-8"))
        e = r["munkaterek"][workspace_id]
        allapot = e.get("allapot")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(e, dict) or not _bejegyzes_ez_a_vault(e, vault):
        return None
    return allapot if allapot in ("vault", "telepites") else None


def munkater_mappa_ellenoriz(vault: Path | str, mappa: Path | str | None = None) -> None:
    """A munkatér-mappa szerkezete (I7, K3): a `<vault>/.manifold`, a `.manifold/var`, a `workspace.toml`, a `.gitignore` és a
    `README.txt` valódi mappa / fájl legyen, szimbolikus link nem. Egy `.manifold -> más-vault/.manifold` link a másik munkatér
    beállításait és állapotát (`{var}`: vault.git, SQLite-ok) a miénkként olvastatná és írná, egy `var -> a vault jegyzetei` link
    az állapotfájlokat a jegyzetek közé tenné. A kanonikus `.manifold` a kanonikus vault alatt kell álljon (a vault maga lehet
    link: a felhasználó elrendezése). Hiányzó mappa rendben (még nincs munkatér). → `ConfigError(kod="munkater_symlink")`.
    A `config.load` (az `W` réteg olvasása előtt), a `workspace` (`felmer`, `letrehoz`, `nyit`, az azonosító átírása) és a doctor hívja."""
    v = Path(vault)
    ws = Path(mappa) if mappa is not None else v / MUNKATER_MAPPA

    def hiba(ut: Path, ok: str) -> ConfigError:
        return ConfigError(f"a munkatér-mappa nem lehet szimbolikus link, és a vaulton kívülre sem mutathat: {ut} ({ok})",
                           kod="munkater_symlink", param={"ut": str(ut), "ok": ok})

    try:
        st = os.lstat(ws)
    except OSError:
        return                                          # nincs (még) munkatér-mappa, vagy nem elérhető: nincs mit ellenőrizni
    if stat.S_ISLNK(st.st_mode):
        raise hiba(ws, "szimbolikus link")
    if os.path.realpath(ws) != os.path.join(os.path.realpath(ws.parent), ws.name):
        raise hiba(ws, "a kanonikus út eltér")
    for nev in ("var", "workspace.toml", ".gitignore", "README.txt"):
        try:
            if stat.S_ISLNK(os.lstat(ws / nev).st_mode):
                raise hiba(ws / nev, "szimbolikus link")
        except OSError:
            continue


def load(environment: dict[str, str] | None = None, *, munkater: bool = True) -> Config:
    """A rétegzett konfiguráció. `munkater=False`: termékben munkatér nélkül is betölt (a worker, `mos workspace lista`);
    a `{var}` családja ilyenkor halasztott."""
    env = dict(os.environ if environment is None else environment)
    root = Path(env["MOS_ROOT"]).resolve() if env.get("MOS_ROOT") else os_root()
    forras = Path(env.get("MOS_CONFIG") or root / "config" / "os.toml")
    try:
        s = _toml_olvas(forras, kod="config_toml_hibas")
    except FileNotFoundError as exc:
        raise ConfigError(f"a konfiguráció nem található: {forras}", kod="config_hianyzik",
                          param={"ut": str(forras)}) from exc
    e = elrendezes(root, env)
    retegek: dict[str, str] = {}
    elutasitott: list[tuple[str, str, str]] = []
    data = copy.deepcopy(s)
    if e == "termek":
        data = _melyegyesit(data, (s.get("elrendezes") or {}).get(e) or {}, retegek, "os:termek")
    data["_meta"] = {"elrendezes": e}

    # 2. I (+P(I))
    elo = Config(root, data, env, forras)
    settings = _settings_ut(env, root, elo.utak.get("install"))
    i_reteg = "telepites_hordozhato" if e == "hordozhato" else "telepites"
    i_adat = _toml_olvas(settings, kod="settings_toml_hibas", megbizhatatlan=True) \
        if settings is not None and settings.is_file() else {}
    nevek_ok, rossz = _szur(i_reteg, {"telepites": {"presetek": (i_adat.get("telepites") or {}).get("presetek", [])}},
                            data, root)
    data = _presetek(((nevek_ok.get("telepites") or {}).get("presetek")), i_reteg, data, root, retegek, elutasitott)
    ok, rossz = _szur(i_reteg, i_adat, data, root)
    data = _melyegyesit(data, ok, retegek, "telepites")
    elutasitott += [("telepites", k, kod) for k, kod in rossz]

    # 3. {vault} → W (+P(W))
    elo = Config(root, data, env, forras)
    if "workspace" in elo.utak and "vault" in elo.utak:
        munkater_mappa_ellenoriz(elo.utak["vault"], elo.utak["workspace"])      # a W réteg olvasása ELŐTT: link soha nem követhető
    ws_toml = elo.utak["workspace"] / "workspace.toml" if "workspace" in elo.utak and "vault" in elo.utak else None
    van_w = ws_toml is not None and ws_toml.is_file()
    if van_w:
        w_adat = _toml_olvas(ws_toml, kod="workspace_toml_hibas", megbizhatatlan=True)
        nevek_ok, _ = _szur("munkater", {"workspace": {"presetek": (w_adat.get("workspace") or {}).get("presetek", [])}},
                            data, root)
        data = _presetek(((nevek_ok.get("workspace") or {}).get("presetek")), "munkater", data, root, retegek, elutasitott)
        ok, rossz = _szur("munkater", w_adat, data, root)
        data = _melyegyesit(data, ok, retegek, "munkater")
        elutasitott += [("munkater", k, kod) for k, kod in rossz]
        w_id = ((ok.get("workspace") or {}).get("id"))
    else:
        w_id = None
    env_id = env.get("MOS_WORKSPACE_ID") or ""
    if env_id and not ID_MINTA.match(env_id):
        raise ConfigError(f"hibás munkatér-azonosító: MOS_WORKSPACE_ID={env_id!r}", kod="workspace_id_hibas",
                          param={"ertek": env_id})
    workspace_id = env_id or w_id or None

    munkater_hianyzik = False
    if e == "termek":
        if "vault" not in elo.utak:
            munkater_hianyzik = True
        elif not van_w and not env_id:
            if munkater:
                raise ConfigError(f"a mappa nem Manifold-munkatér: {elo.utak['vault']}", kod="nem_workspace",
                                  param={"vault": str(elo.utak["vault"])})
            munkater_hianyzik = True
        # 4. a gép regisztere dönt az állapot helyéről (szinkronizált mappa: a telepítés alatt), a vault soha
        if workspace_id and "install" in elo.utak and "vault" in elo.utak \
                and _regiszter_allapot(elo.utak["install"], workspace_id, elo.utak["vault"]) == "telepites":
            data["utak"] = {**data.get("utak", {}), "var": "{install}/workspaces/{workspace_id}/var"}
            retegek["utak.var"] = "regiszter"

    data["_meta"] = {"elrendezes": e, "workspace_id": workspace_id, "munkater_hianyzik": munkater_hianyzik,
                     "settings": str(settings) if settings is not None and settings.is_file() else "",
                     "retegek": retegek, "elutasitott": [list(x) for x in elutasitott]}
    cfg = Config(root, data, env, forras)
    if e == "termek":
        _i1(cfg)
    return cfg


def _i1(cfg: Config) -> None:
    """I1 (termék): minden írható `[utak]` kulcs az `{os}`-on kívül oldódik fel."""
    gyoker = [Path(os.path.normpath(cfg.root)), Path(os.path.realpath(cfg.root))]
    for k, p in cfg.utak.items():
        if k in CSAK_OLVASOTT:
            continue
        for ut in (Path(os.path.normpath(p)), Path(os.path.realpath(p))):
            if any(ut == g or g in ut.parents for g in gyoker):
                raise ConfigError(f"a(z) {k} út a csak olvasható kódfába mutat: {p}", kod="iras_a_kodba",
                                  param={"kulcs": k, "ut": str(p)})
