"""Tulajdonság-szerkesztő háttere (C11b): a frontmatter bájthű, soronkénti módosítása és a vault-séma
(LEGACY-SZERZODESEK L33, L34, L39) ellenőrzése.

**Nem ír fájlt.** A függvények a frontmatter-blokk szövegét kapják, és az újat adják vissza; az írás a
nyitott szerkesztő dokumentumán megy át (a mentés, az ütközés és a ⌘Z egy úton marad). Ezért tiszta, és ezért
tesztelhető álvault nélkül.

**Bájthűség.** Nincs YAML-újraírás (a PyYAML nem round-trip): a blokk sorokra bomlik, és csak a módosított
kulcs sorai cserélődnek; a többi bájt (kulcssorrend, megjegyzések, idézőjelek, CRLF) érintetlen. Írás előtt
próba: az új szöveg ugyanazzal az elemzővel olvasva a nem érintett kulcsok értéke azonos, az érintetté a várt;
különben a művelet elutasítva (`belso_hiba`).

**Séma** (`os.toml` `[sema]`; a fájl feloldása: `core/kiserok.sema_fajl` — a `[sema] vault` fájl, ha van → a megnevezett preset
`<nev>.schema.json`-ja → a szállított `[sema] alap`). Két szint: `hiba` (nem írható: a Status gépi
kitöltése, formai hiba, érvénytelen érték) és `sertes` (a séma sérül — ismeretlen kulcs, köztük az `icon` és
a `cover`; kulcssorrend; értékkészleten kívüli címke vagy Status): ez csak kifejezett megerősítéssel
(`megerosit: true`) kerül be — nem csendben. Csak az **új** sértések számítanak: ami már a módosítás előtt is
sértett, azt a módosítás nem teszi megerősítés-köteles.

**Mód** (`[sema] mod`, F3-DESIGN §8): `ki` (alap: nincs sémaellenőrzés — csak az ismétlődő kulcs, mint formai hiba; nincs H1-szabály,
nincs gazdai Status), `tanacsado` (a sértések `tanacsok`-ként látszanak az `elemez` válaszában, `szint: tanacs`; semmit nem tiltanak,
megerősítést sem kérnek, a gépi írás sem utasítja el), `szigoru` (a fenti: sértés → megerősítés, a gépi írás elutasítja).
A séma fájlban `null` értékkészlet = nincs korlát; üres `mezosorrend` = a normál jegyzet kulcsai nyitottak. A kísérő-osztályok
(`kisero: <fajta>`) előtagja a `core/kiserok.py`-ból származik, külön lista nincs.
"""
from __future__ import annotations

import datetime
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import kiserok
from .index import elemzo
from .index.indexelo import NemKesz
from .index.maszk import FM_RE
from .utvonalak import HttpError

HIBA, SERTES, TANACS = "hiba", "sertes", "tanacs"
MODOK = ("ki", "tanacsado", "szigoru")
_KULCS_SOR = re.compile(r"^([^\s#:\-][^:]*?)\s*:(?=\s|$)")
_KULCS_NEV = re.compile(r"^[^\W\d][\w .-]*$")
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATUM_IDO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_LISTA_TIPUSOK = ("tags", "multitext", "aliases")
_SORSZAM_ELOTAG = re.compile(r"^\d+[A-Z]? - ")             # a H1-szabály alapja: a fájlnév a sorszám-előtag nélkül (L46)
TIPUSOK = ("text", "multitext", "number", "checkbox", "date", "datetime", "tags", "aliases")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _datum_ervenyes(s: str) -> bool:
    """`ÉÉÉÉ-HH-NN` alakú és naptárilag létező nap (T131: a `2026-13-45`, `2026-02-30`, `0000-01-01` nem)."""
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return False
    return bool(_DATUM.match(s))


def _datumido_ervenyes(s: str) -> bool:
    """`ÉÉÉÉ-HH-NNTÓÓ:PP[:MM]` alakú és létező időpont."""
    try:
        datetime.datetime.fromisoformat(s)
    except ValueError:
        return False
    return bool(_DATUM_IDO.match(s))


# ---------------------------------------------------------------- séma

# Ügynök-hordozó fájlok neve (kis-nagybetű nélkül, bármely mélységben): nem vault-jegyzetek, a séma nem vonatkozik rájuk, és gép
# nem ír beléjük (`gepi_iras._sema_tiltas`). Kód-állandó: a konfig (`sema_nelkuli_nevek`) csak bővítheti, nem szűkítheti.
UGYNOK_FAJLNEVEK = frozenset({"claude.md", "agents.md", "memory.md"})


class Sema:
    """A vault-séma (L33/L34) a konfigból; `osztaly(ut)` adja az útra érvényes szabályt. `mod`: `ki` | `tanacsado` | `szigoru`
    (`cfg` nélkül a v2 szigorú viselkedése; `cfg`-vel a `[sema] mod`, hiányában `ki`)."""

    def __init__(self, adat: dict, cfg=None, mod: str | None = None):
        self._cfg = cfg
        if mod is None:
            mod = (cfg.section("sema").get("mod") or "ki") if cfg is not None else "szigoru"
        self.mod: str = mod if mod in MODOK else "ki"
        self.mezosorrend: list[str] = list(adat["mezosorrend"] or [])
        self.extra: list[str] = list(adat.get("extra_kulcsok") or [])
        tags, status = adat.get("tags_ertekkeszlet"), adat.get("status_ertekkeszlet")
        self.tags: list[str] | None = None if tags is None else list(tags)        # None: nincs értékkészlet (nincs korlát)
        self.status: list[str] | None = None if status is None else list(status)
        # T127: a Status a felhasználóé — a séma MÓDJÁTÓL függetlenül (a `ki` mód csak az érték- és kulcsellenőrzést kapcsolja ki, a gépi
        # írás tilalmát nem), alapból igaz (`status_vedett`: a megbízhatatlan `schema.json` ott sem kapcsolhatja ki, ahol van Status)
        self.status_gazdai: bool = bool(adat.get("status_gazdai", True))
        self.osztalyok: list[dict] = [self._osztaly_feloldas(o, cfg) for o in adat.get("kivetel_osztalyok", [])]
        self.sema_nelkul: set[str] = {nfc(u) for u in adat.get("sema_nelkuli_utak", [])}
        self.sema_nelkuli_nevek: frozenset[str] = UGYNOK_FAJLNEVEK | {nfc(n).casefold() for n in adat.get("sema_nelkuli_nevek", [])}
        self.h1: dict = dict(adat.get("h1") or {})            # a H1-szabály (legacy kalibráció, C29.8 T044)
        self.kisero: dict[str, str] = kiserok.kisero_mappak(cfg)    # fajta → mappa (a felületnek: `leiras`)
        self.kisero_elotag: str = kiserok.kisero_elotag(cfg)

    @staticmethod
    def _osztaly_feloldas(o: dict, cfg) -> dict:
        """A `kisero: <fajta>` osztály útvonal-előtagja a `core/kiserok.py`-ból (a literális `utvonal_elotag` mellett)."""
        o = dict(o)
        if o.get("kisero"):
            o["utvonal_elotag"] = [*o.get("utvonal_elotag", []), kiserok.kisero_mappa(cfg, o["kisero"]) + "/"]
        return o

    @classmethod
    def betolt(cls, cfg) -> "Sema":
        """A séma a feloldási lánc első ÉRVÉNYES fájljából (`kiserok.sema_fajlok`: munkatér-fájl → preset(ek) → szállított alap). A
        munkatér `schema.json`-ja megbízhatatlan (a vault utazik): a hibás (rossz típus, túl nagy, fordíthatatlan vagy veszélyes
        reguláris kifejezés) fájl nem kivételt dob és nem írja a szabályokat — a lánc következő jelöltje él (a doctor jelzi)."""
        fajlok = kiserok.sema_fajlok(cfg)
        if not fajlok:
            raise FileNotFoundError("nincs vault-séma: sem a [sema] vault fájl, sem a preset sémája, sem a [sema] alap nem létezik")
        hibak: list[str] = []
        for ut in fajlok:
            try:
                return cls(kiserok.sema_olvas(ut), cfg)
            except kiserok.SemaHiba as e:
                hibak.append(str(e))
        raise ValueError("egyik vault-séma sem érvényes: " + " | ".join(hibak))

    def status_vedett(self, van_status_kulcs: bool) -> bool:
        """Gépi írás ellen védett-e a jegyzet Status-a (T127): a séma `status_gazdai`-ja szerint, és — a séma szavától (a munkatér
        `schema.json`-ja megbízhatatlan fájl) függetlenül — mindig, ha a jegyzetnek már van `Status` kulcsa."""
        return self.status_gazdai or van_status_kulcs

    def osztaly(self, ut: str) -> dict:
        """`{nev, mezosorrend, ertekek, sema_nelkul}`: a normál jegyzet, egy kivételosztály vagy a séma nélküli fájl."""
        ut = nfc(ut or "")
        if ut in self.sema_nelkul or ut.rsplit("/", 1)[-1].casefold() in self.sema_nelkuli_nevek:
            return {"nev": "sema-nelkuli", "mezosorrend": [], "ertekek": False, "sema_nelkul": True, "h1": False,
                    "h1_minta": None, "h1_egyezzen_fajlnevvel": False}
        for o in self.osztalyok:
            if any(ut.startswith(nfc(e)) for e in o.get("utvonal_elotag", [])):
                return {"nev": o["nev"], "mezosorrend": list(o["mezosorrend"]), "ertekek": False, "sema_nelkul": False,
                        "h1": o.get("h1", True), "h1_minta": o.get("h1_minta"),
                        "h1_egyezzen_fajlnevvel": bool(o.get("h1_egyezzen_fajlnevvel"))}
        return {"nev": "normal", "mezosorrend": list(self.mezosorrend), "ertekek": True, "sema_nelkul": False,
                "h1": True, "h1_minta": None, "h1_egyezzen_fajlnevvel": False}

    @property
    def nyelv(self) -> str:
        # The schema remains cached, while Setup/Settings can change the content
        # hint on the shared configuration without reopening the core.
        return ((self._cfg.section("workspace").get("nyelv") or self._cfg.section("sablon").get("nyelv") or "")
                if self._cfg is not None else "")

    def leiras(self, ut: str | None = None) -> dict:
        return {"mezosorrend": self.mezosorrend, "extra_kulcsok": self.extra, "tags_ertekkeszlet": self.tags or [],
                "status_ertekkeszlet": self.status or [], "status_gazdai": self.status_gazdai,
                "mod": self.mod, "nyelv": self.nyelv, "kisero": self.kisero, "kisero_elotag": self.kisero_elotag,
                "osztaly": self.osztaly(ut) if ut is not None else None}


# ---------------------------------------------------------------- a blokk szerkezete

@dataclass
class _Blokk:
    kulcs: str | None            # None: megjegyzés vagy üres sor (érintetlenül marad)
    sorok: list[str]


@dataclass
class _Fm:
    eol: str
    vegen_eol: bool              # a záró `---` után van-e sortörés a blokkban
    blokkok: list[_Blokk]
    elo: str = ""                # a blokk elején álló BOM (`\ufeff`), ha van: a visszaírás megőrzi (T130)

    def sorok(self) -> list[str]:
        return [s for b in self.blokkok for s in b.sorok]

    def szoveg(self) -> str:
        return self.elo + self.eol.join(["---", *self.sorok(), "---"]) + (self.eol if self.vegen_eol else "")

    def belso(self) -> str:
        return self.eol.join(self.sorok())

    def kulcsok(self) -> list[str]:
        return [b.kulcs for b in self.blokkok if b.kulcs is not None]


def _folytatas(s: str) -> bool:
    return (s[:1] in (" ", "\t") and s.strip() != "") or re.match(r"-(\s|$)", s) is not None


def _kulcs_nev(m: re.Match) -> str:
    k = m.group(1).strip()
    return k[1:-1] if len(k) > 1 and k[0] == k[-1] and k[0] in "\"'" else k


def _blokkokra(sorok: list[str]) -> list[_Blokk]:
    out: list[_Blokk] = []
    i = 0
    while i < len(sorok):
        m = _KULCS_SOR.match(sorok[i])
        if not m:
            out.append(_Blokk(None, [sorok[i]]))
            i += 1
            continue
        j = i + 1
        while j < len(sorok):
            if _folytatas(sorok[j]):
                j += 1
                continue
            if sorok[j].strip() == "":
                k = j
                while k < len(sorok) and sorok[k].strip() == "":
                    k += 1
                if k < len(sorok) and _folytatas(sorok[k]):
                    j = k
                    continue
            break
        out.append(_Blokk(_kulcs_nev(m), sorok[i:j]))
        i = j
    return out


def _fm_elemez(fm: str | None) -> _Fm | None:
    """A frontmatter-blokk (`---` … `---`, mint az `FM_RE` illesztése) szerkezete; None, ha nincs."""
    if fm is None or fm == "":
        return None
    if not FM_RE.match(fm) or FM_RE.match(fm).end() != len(fm):
        raise HttpError(400, "a `fm` nem frontmatter-blokk (az `FM_RE` illesztése kell, a záró `---`-ig)", kod="tulajdonsag.fm_nem_blokk")
    elo = "\ufeff" if fm.startswith("\ufeff") else ""
    fm = fm[len(elo):]
    eol = "\r\n" if "\r\n" in fm else "\n"
    vegen = fm.endswith(eol)
    sorok = (fm[:-len(eol)] if vegen else fm).split(eol)
    return _Fm(eol, vegen, _blokkokra(sorok[1:-1]), elo)


def _yaml_kulcsok(belso: str) -> list[str] | None:
    """A blokk kulcsai a YAML szintaxisfájából (az escape feloldva, a `? ` komplex kulcs is): `None`, ha nem olvasható."""
    try:
        gyoker = yaml.compose(belso, Loader=elemzo._Betolto)
    except (yaml.YAMLError, RecursionError):
        return None
    if not isinstance(gyoker, yaml.MappingNode):
        return None
    return [str(k.value) for k, _ in gyoker.value if isinstance(k, yaml.ScalarNode)]


def frontmatter_hiba_angol(hiba: str | None) -> str | None:
    """Translate core diagnostic phrases while retaining YAML locations, keys and source excerpts."""
    if not hiba:
        return hiba
    szoveg = str(hiba)
    for regi, uj in (
        ("a frontmatter túl mélyen egymásba ágyazott", "The frontmatter nesting is too deep."),
        ("a frontmatter nem kulcs–érték párokból áll", "The frontmatter must contain key–value pairs."),
        ("a tábla felépítése közben", "while constructing a mapping"),
        ("duplikált kulcs:", "duplicate key:"),
    ):
        szoveg = szoveg.replace(regi, uj)
    szoveg = re.sub(r"a YAML-alias \(\*(.*?)\) nem megengedett", r"YAML aliases (*\1) are not allowed", szoveg)
    return re.sub(r"a YAML legfeljebb (\d+) szint mélyen ágyazható egymásba", r"YAML nesting cannot exceed \1 levels", szoveg)


# ---------------------------------------------------------------- értékek szövege

_MAS_OLVASO = re.compile(
    r"^[-+]?0[xXoObB][0-9a-fA-F_]*$"                      # 0x1F, 0o7, 0b101: YAML 1.2 core (az Obsidian parseYaml-je) / 1.1 szám
    r"|^[-+]?[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?$"  # 1_000, 1_000.5 (a `_` csak a YAML 1.1-ben szám)
    r"|^[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+(?:\.[0-9_]*)?$"     # 10:30, 1:20:30: YAML 1.1 hatvanas szám
    r"|^(?:y|Y|yes|Yes|YES|n|N|no|No|NO|on|On|ON|off|Off|OFF)$")  # YAML 1.1 bool-szavak


def _szoveg_sor(s: str) -> str:
    """Egy szöveges skalár YAML-alakja: sima, ha a visszaolvasás ugyanazt a szöveget adja; különben
    idézőjeles. A wikilink (`[[…]]`) mindig idézőjeles (a legacy író alakja; sima alakban beágyazott lista volna).
    T157 (C31): idézőjeles az is, amit egy MÁS olvasó számnak vagy logikai értéknek venne — az Obsidian `parseYaml`-je
    (eemeli/yaml, YAML 1.2 core; statikus olvasás, 1.14.4) a `0x1F`-et és a `0o7`-et számnak, a YAML 1.1-es olvasók
    (PyYAML, a legacy `mfd.py`) a `1_000`-et, a `10:30`-at és a `yes`/`on`-t is: a 2.0 saját betöltője szövegnek látja."""
    if "[[" in s or "\n" in s or "\r" in s or s != s.strip() or s == "" or _MAS_OLVASO.match(s):
        return json.dumps(s, ensure_ascii=False)
    if (_DATUM.match(s) and not _datum_ervenyes(s)) or (_DATUM_IDO.match(s) and not _datumido_ervenyes(s)):
        return json.dumps(s, ensure_ascii=False)         # sima alakban dátumnak látszana (T131)
    try:
        ok = yaml.load(f"k: {s}", Loader=elemzo._Betolto) == {"k": s}
    except yaml.YAMLError:
        ok = False
    return s if ok else json.dumps(s, ensure_ascii=False)


def _ertek_normal(tipus: str, ertek):
    """Az érték a megadott típus szerint: (Python-érték a visszaolvasás-próbához, hiba-szöveg | None)."""
    if ertek is None or ertek == "" or ertek == []:
        return None, None
    if tipus in _LISTA_TIPUSOK or isinstance(ertek, list):
        elemek = ertek if isinstance(ertek, list) else [ertek]
        if any(isinstance(x, (list, dict)) for x in elemek):
            return None, "List items must be text."
        lista = [str(x).strip() for x in elemek if x is not None and str(x).strip()]
        if tipus == "tags":
            lista = [x[1:] if x.startswith("#") else x for x in lista]
        return lista, None
    if tipus == "checkbox":
        if isinstance(ertek, bool):
            return ertek, None
        if ertek in ("true", "false"):
            return ertek == "true", None
        return None, "A checkbox must be true or false."
    if tipus == "number":
        if isinstance(ertek, bool) or not isinstance(ertek, (int, float, str)):
            return None, "Enter a finite number."
        try:
            n = ertek if not isinstance(ertek, str) else (int(ertek) if re.fullmatch(r"[-+]?\d+", ertek.strip())
                                                           else float(ertek.replace(",", ".")))
        except ValueError:
            return None, "Enter a finite number."
        if isinstance(n, float) and (n != n or n in (float("inf"), float("-inf"))):
            return None, "Enter a finite number."
        return n, None
    if tipus == "date":
        if isinstance(ertek, str) and _DATUM.match(ertek):
            return (ertek, None) if _datum_ervenyes(ertek) else (None, "The date does not exist in the calendar.")
        return None, "The date must use YYYY-MM-DD format."
    if tipus == "datetime":
        if isinstance(ertek, str) and _DATUM_IDO.match(ertek):
            return (ertek, None) if _datumido_ervenyes(ertek) else (None, "The date or time is invalid.")
        if isinstance(ertek, str) and _DATUM.match(ertek):
            return (ertek, None) if _datum_ervenyes(ertek) else (None, "The date does not exist in the calendar.")
        return None, "The date and time must use YYYY-MM-DDTHH:MM format."
    if isinstance(ertek, dict):
        return None, "This value cannot be edited here."
    return str(ertek), None


def _sorok(kulcs: str, ertek) -> list[str]:
    """A kulcs sorai a legacy író alakjában: skalár egy sorban, lista blokkformában, üres `Kulcs:`."""
    if ertek is None:
        return [f"{kulcs}:"]
    if isinstance(ertek, list):
        return [f"{kulcs}:", *(f"  - {_szoveg_sor(x)}" for x in ertek)]
    if isinstance(ertek, bool):
        return [f"{kulcs}: {'true' if ertek else 'false'}"]
    if isinstance(ertek, (int, float)):
        return [f"{kulcs}: {ertek!r}"]
    if (_DATUM.match(ertek) and _datum_ervenyes(ertek)) or (_DATUM_IDO.match(ertek) and _datumido_ervenyes(ertek)):
        return [f"{kulcs}: {ertek}"]
    return [f"{kulcs}: {_szoveg_sor(ertek)}"]


# ---------------------------------------------------------------- a szerkesztő

class Tulajdonsagok:
    def __init__(self, cfg, index):
        self.cfg = cfg
        self.index = index
        self.sema = Sema.betolt(cfg)
        self._hasznalat_tar: tuple[int, dict] | None = None     # (index-generáció, ertekkeszlet_hasznalat)

    # -------------------------------------------------- ellenőrzés

    def _tulajdonsagok(self, fm: _Fm | None, egyedi: bool = False):
        """(tulajdonságok, hiba, {kulcs: érték}) a blokk elemzőjével — ugyanaz, mint az indexé. `egyedi`: a duplikált kulcs is
        hiba (az írás visszaolvasás-próbája: a sorbontó által nem ismert kulcsalak nem hozhat létre második kulcsot, T129)."""
        if fm is None:
            return [], None, {}
        tul, hiba = elemzo.frontmatter(fm.belso(), getattr(self.index, "tipusok", {}) or {}, egyedi=egyedi)
        return tul, hiba, {t.kulcs: t.ertek for t in tul}

    def problemak(self, ut: str, kulcsok: list[str], ertekek: dict, van_fm: bool = True) -> list[dict]:
        """A tiltó vagy megerősítést kérő sértések (`hiba`, `sertes`). `kulcsok`: a frontmatter kulcsai a fájl sorrendjében
        (az ismétlődéssel). Módonként: `szigoru` a teljes séma-ellenőrzés; `tanacsado` és `ki` csak a formai hibát (ismétlődő kulcs)
        adja — a séma sértései `tanacsado` módban a `tanacsok`-ban látszanak."""
        o = self.sema.osztaly(ut)
        if o["sema_nelkul"]:
            return []
        teljes = self._ellenoriz(ut, o, kulcsok, ertekek, van_fm)
        if self.sema.mod == "szigoru":
            return teljes
        return [p for p in teljes if p["kod"] == "duplikalt_kulcs"]

    def tanacsok(self, ut: str, kulcsok: list[str], ertekek: dict, van_fm: bool = True) -> list[dict]:
        """`tanacsado` módban a séma sértései tanácsként (`szint: tanacs`): nem tiltanak, megerősítést nem kérnek, a gépi írást nem
        állítják meg. Más módban üres."""
        o = self.sema.osztaly(ut)
        if self.sema.mod != "tanacsado" or o["sema_nelkul"]:
            return []
        return [{**p, "szint": TANACS} for p in self._ellenoriz(ut, o, kulcsok, ertekek, van_fm) if p["kod"] != "duplikalt_kulcs"]

    def _ellenoriz(self, ut: str, o: dict, kulcsok: list[str], ertekek: dict, van_fm: bool) -> list[dict]:
        """A teljes séma-ellenőrzés a mód nélkül (az `o` az útra érvényes osztály)."""
        out: list[dict] = []

        def p(kod, szint, uzenet, kulcs=None, ertek=None):
            out.append({"kod": kod, "szint": szint, "kulcs": kulcs, "ertek": ertek, "uzenet": uzenet})

        kanon, extra = o["mezosorrend"], set(self.sema.extra)
        ismert = set(kanon) | extra
        for k in dict.fromkeys(kulcsok):
            if kulcsok.count(k) > 1:
                p("duplikalt_kulcs", HIBA, f"The ‘{k}’ key appears more than once.", k)
        nyitott = not kanon                       # üres `mezosorrend`: a kulcsok nyitottak (nincs ismeretlen kulcs, nincs sorrend)
        for k in dict.fromkeys(kulcsok):
            if k in ismert or nyitott:
                continue
            nagy = next((c for c in kanon if c.lower() == k.lower()), None)
            if nagy:
                p("kisbetus_kulcs", SERTES, f"The schema expects ‘{nagy}’, not ‘{k}’.", k)
            else:
                p("ismeretlen_kulcs", SERTES, f"The ‘{k}’ key is not in the vault schema.", k)
        # A legacy próba az ismeretlen kulcsot is sorrend-sértésnek veszi; itt az ismeretlen kulcs külön problémát ad
        # (`ismeretlen_kulcs`), a `mezosorrend` csak a séma kulcsainak hiányát vagy felcserélődését jelzi.
        mag = [k for k in kulcsok if k in kanon]
        if mag != kanon and not nyitott:
            if not van_fm or not kulcsok:
                p("mezosorrend", SERTES, "The note has no frontmatter. Schema keys: " + ", ".join(kanon))
                out[-1]["hianyzo"] = list(kanon)
            else:
                hianyzo = [k for k in kanon if k not in mag]
                szoveg = ("missing: " + ", ".join(hianyzo)) if hianyzo else "the order differs"
                p("mezosorrend", SERTES, f"The keys do not match the schema ({', '.join(kanon)}): {szoveg}.")
                out[-1]["hianyzo"] = hianyzo               # T133: az „új sértés” azonosítója a hiányzó kulcsok halmaza
        if o["ertekek"]:
            # CX-002 (80(d)): egy címke vagy Status-érték érvényes, ha a séma értékkészletében van, vagy egy MÁSIK jegyzet
            # már használja (a vizsgált jegyzet tárolt értéke önmagát nem legitimálja; az utolsó előfordulás törlésével az
            # engedély is megszűnik). Nem kész indexnél csak a séma számít: a kívül eső érték megerősíthető sértés, nem hiba.
            hasznalat = self._ertekkeszlet_hasznalat()

            def hasznalt(fajta: str, kulcs: str) -> bool:
                h = (hasznalat or {}).get(fajta, {}).get(kulcs)
                return bool(h) and (h["db"] >= 2 or any(u != ut for u in h["utak"]))
            nem_kesz = "" if hasznalat is not None else " (The index is still building; only the schema value set is available.)"
            tags = None if self.sema.tags is None else set(self.sema.tags)           # None: nincs értékkészlet-korlát
            statusok = None if self.sema.status is None else set(self.sema.status)
            for t in self._lista(ertekek.get("Tags")) if tags is not None else ():
                if t not in tags and not hasznalt("tags", nfc(t).removeprefix("#").strip().casefold()):
                    p("ertekkeszlet", SERTES, f"The ‘{t}’ tag is not in the allowed value set.{nem_kesz}", "Tags", t)
            st = ertekek.get("Status")
            ures = st is None or st == [] or (isinstance(st, str) and not st.strip())
            if statusok is not None and not ures and (not isinstance(st, str) or (st not in statusok and not hasznalt("status", nfc(st).strip()))):
                # T042: a nem szöveges érték (true, 5, lista, map) is értékkészleten kívüli; az `ertek` szöveg (az azonosító-halmaz hash-elhető)
                szoveg = st if isinstance(st, str) else json.dumps(st, ensure_ascii=False)
                p("ertekkeszlet", SERTES,
                  f"Status must be text from the allowed values ({', '.join(self.sema.status or [])}), not ‘{szoveg}’.{nem_kesz}",
                  "Status", szoveg)
        return out

    @staticmethod
    def _lista(ertek) -> list[str]:
        return [x[1:] if x.startswith("#") else x for x in elemzo._lista(ertek)]

    def elemez(self, ut: str, fm: str | None) -> dict:
        """A panel adata a *nyitott* (akár mentetlen) frontmatterről: tulajdonságok típussal, a formai hiba és a
        séma-sértések. Nem íróvégpont."""
        f = _fm_elemez(fm)
        if f is None:
            return {"van": False, "tulajdonsagok": [], "hiba": None, "kulcsok": [],
                    "problemak": self.problemak(nfc(ut or ""), [], {}, van_fm=False),
                    "tanacsok": self.tanacsok(nfc(ut or ""), [], {}, van_fm=False),
                    "osztaly": self.sema.osztaly(ut or "")["nev"]}
        tul, hiba, ertekek = self._tulajdonsagok(f)
        kulcsok = f.kulcsok()
        # T129: a duplikált kulcs a YAML-szintű kulcslistából is látszik (az escape-es idézett és a `? ` komplex kulcsot a soronkénti
        # bontás nem ismeri fel); a válasz `kulcsok` mezője a soronkénti marad (a panel sorrendje)
        yk = _yaml_kulcsok(f.belso()) or kulcsok
        prob = self.problemak(nfc(ut or ""), yk, ertekek)
        tan = self.tanacsok(nfc(ut or ""), yk, ertekek)
        if hiba:
            prob.insert(0, {"kod": "yaml_hiba", "szint": HIBA, "kulcs": None, "ertek": None,
                            "uzenet": f"Invalid frontmatter syntax: {frontmatter_hiba_angol(hiba)}"})
        return {"van": True, "tulajdonsagok": [{"kulcs": t.kulcs, "tipus": t.tipus, "ertek": t.ertek,
                                                 "ervenyes": t.ervenyes} for t in tul],
                "hiba": frontmatter_hiba_angol(hiba), "kulcsok": kulcsok, "problemak": prob, "tanacsok": tan,
                "osztaly": self.sema.osztaly(ut or "")["nev"]}

    def uj_jegyzet_ellenorzes(self, ut: str, szoveg: str | None) -> dict:
        """Egy **új** jegyzet leendő szövegének frontmatterje a séma szerint (Javító 7; 64(b), 22(b)): ugyanaz az `elemez` és ugyanaz
        a szint-beosztás, mint a tulajdonság-panelé és a `modosit`-é. Válasz: `{van, hibak, sertesek}`; a `hibak` (formai hibás
        frontmatter, ismétlődő kulcs, a típushoz nem illő érték) megerősítéssel sem írhatók, a `sertesek` (ismeretlen kulcs — köztük
        az `icon` és a `cover` —, értékkészleten kívüli címke vagy Status, kulcssorrend) csak megerősítéssel. Frontmatter nélküli
        szövegre üres. Nem ír fájlt; nem íróvégpont."""
        m = FM_RE.match(szoveg or "")
        if not m:
            return {"van": False, "hibak": [], "sertesek": []}
        e = self.elemez(ut, m.group(0))
        hibak = [p for p in e["problemak"] if p["szint"] == HIBA]
        for t in e["tulajdonsagok"]:
            if not t["ervenyes"]:
                hibak.append(self._hiba("ertek_tipus", f"The value of ‘{t['kulcs']}’ does not match its {t['tipus']} type.", t["kulcs"]))
        return {"van": True, "hibak": hibak, "sertesek": [p for p in e["problemak"] if p["szint"] == SERTES]}

    @staticmethod
    def uj_sertesek(elotte: list[dict], utana: list[dict]) -> list[dict]:
        """A módosítás által hozott ÚJ sértések: ami előtte is sértett (azonos kód, kulcs, érték), az nem. A `mezosorrend` azonosítója
        a hiányzó kulcsok halmaza (T133): egy már hiányos jegyzetben az újabb kulcs törlése új sértés; a hiány pótlása nem."""
        regi = {(p["kod"], p["kulcs"], p["ertek"]) for p in elotte if p["kod"] != "mezosorrend"}
        regi_m = [p for p in elotte if p["kod"] == "mezosorrend"]
        regi_hianyzo = set().union(*(set(p.get("hianyzo") or []) for p in regi_m)) if regi_m else set()
        ki = []
        for p in utana:
            if p["kod"] == "mezosorrend":
                h = set(p.get("hianyzo") or [])
                if h - regi_hianyzo or (not h and not regi_m):        # új hiányzó kulcs, vagy új sorrend-sértés
                    ki.append(p)
            elif (p["kod"], p["kulcs"], p["ertek"]) not in regi:
                ki.append(p)
        return ki

    # -------------------------------------------------- H1-szabály (C29.8, T044; a legacy kalibráció `h1_szabaly`-a)

    @staticmethod
    def _elso_h1(szoveg: str) -> str | None:
        """A jegyzet törzsének első 1. szintű fejezete (ATX vagy setext; a kódmaszk és a frontmatter után), az eredeti sorból."""
        lf = szoveg.replace("\r\n", "\n").replace("\r", "\n")
        sorok = lf.split("\n")
        for f in elemzo.elemez(lf).fejezetek:
            if f["szint"] != 1:
                continue
            sor = sorok[f["sor"] - 1]
            m = elemzo._FEJEZET.match(sor)
            return nfc(re.sub(r"[ \t]+#+$", "", m.group(2)).strip() if m else sor.strip())
        return None

    def h1_problemak(self, ut: str, szoveg: str) -> list[dict]:
        """A H1-szabály sértései (`hiba` szint: gép és felhasználó sem írhatja meg erősítéssel). A szabály: a jegyzet első H1-je a
        fájlnév a `NN[F] - ` sorszám-előtag nélkül (NFC); a `kivetel_utvonalak` az egyezést, a `kivetel_osztalyok`
        (megoldás-sorszámos, érettségi-témakör: nincs egyezés; sablon-váz: H1 nélkül is jó) az egyezést vagy a hiányt engedik;
        a frontmatter-osztályok saját szabálya (`kviz`: `h1_minta` és fájlnév-egyezés; `konyv-jegyzet`: nincs ellenőrzés).
        Séma nélküli fájl és nem `.md` nincs ellenőrizve."""
        ut = nfc(ut or "")
        h = self.sema.h1
        if self.sema.mod != "szigoru" or not ut.lower().endswith(".md"):
            return []
        o = self.sema.osztaly(ut)
        if (not h and not o.get("h1_minta")) or o["sema_nelkul"] or o.get("h1") is False:
            return []
        stem = nfc(ut.rsplit("/", 1)[-1][:-3])
        h1 = self._elso_h1(szoveg)

        def p(kod, uzenet):
            return [{"kod": kod, "szint": HIBA, "kulcs": None, "ertek": h1, "uzenet": uzenet}]

        if o.get("h1_minta"):                                           # kviz-szerű osztály: saját H1-szerződés
            if h1 is None:
                return p("h1_hiany", "The note has no H1 heading. Quiz notes must use the file name as their H1.")
            m = re.fullmatch(o["h1_minta"], h1)
            if not m or (o.get("h1_egyezzen_fajlnevvel") and nfc(m.group(1)) != stem):
                return p("h1", f"The H1 (‘{h1}’) does not match the {o['nev']} class format or the file name (‘{stem}’).")
            return []
        kivetel_utvonal = any(ut.startswith(nfc(e)) for e in h.get("kivetel_utvonalak", []))
        nincs_egyezes = h1_nelkul_jo = False
        for k in h.get("kivetel_osztalyok", []):
            if "utvonal_elotag" in k and not any(ut.startswith(nfc(e)) for e in k["utvonal_elotag"]):
                continue
            if "mappa_nev" in k and nfc(k["mappa_nev"]) not in ut.split("/")[:-1]:
                continue
            if "fajlnev_minta" in k and not re.search(k["fajlnev_minta"], stem):
                continue
            if "source_tartalmaz" in k:
                m = FM_RE.match(szoveg)
                source = next((t.ertek for t in elemzo.frontmatter(m.group(1))[0] if t.kulcs == "Source"), None) if m else None
                if k["source_tartalmaz"] not in json.dumps(source, ensure_ascii=False):
                    continue
            if k.get("mod") == "h1_nelkul_is_jo":
                h1_nelkul_jo = True
            else:
                nincs_egyezes = True
        if h1 is None:
            return [] if h1_nelkul_jo else p("h1_hiany", "The note has no H1 heading. Use the file name without its numeric prefix as the H1.")
        if kivetel_utvonal or nincs_egyezes:
            return []
        elvart = _SORSZAM_ELOTAG.sub("", stem)
        if h1 != elvart:
            return p("h1", f"The H1 (‘{h1}’) does not match the file name (‘{elvart}’, without the `NN - ` numeric prefix).")
        return []

    # -------------------------------------------------- módosítás

    def modosit(self, ut: str, fm: str | None, muvelet: str, kulcs: str, ertek=None, tipus: str | None = None,
                megerosit: bool = False, forras: str = "felhasznalo") -> dict:
        """Egy kulcs beállítása vagy törlése. Válasz: `{ok, fm_uj, megerositheto, valtozas, problemak}`; `ok: false`
        esetén `fm_uj` nincs, a `problemak` mondja az okot (a `szint: hiba` nem írható, a `sertes` megerősítéssel)."""
        ut = nfc(ut or "")
        if muvelet not in ("beallit", "torol"):
            raise HttpError(400, "a művelet beallit vagy torol lehet", kod="tulajdonsag.muvelet")
        if not isinstance(kulcs, str) or not _KULCS_NEV.match(kulcs) or len(kulcs) > 80:
            return self._elutasit([self._hiba("kulcs_nev", f"Invalid property name: ‘{kulcs}’.", kulcs)])
        if forras not in ("felhasznalo", "gep"):
            raise HttpError(400, "a forrás felhasznalo vagy gep lehet", kod="tulajdonsag.forras")
        if tipus is not None and tipus not in TIPUSOK:
            raise HttpError(400, f"ismeretlen típus: {tipus}", kod="tulajdonsag.tipus", param={"tipus": tipus})
        regi = _fm_elemez(fm)
        regi_tul, regi_hiba, regi_ertek = self._tulajdonsagok(regi)
        if regi_hiba:
            return self._elutasit([self._hiba("yaml_hiba", f"Invalid frontmatter syntax ({frontmatter_hiba_angol(regi_hiba)}). Fix it in source mode first.")])
        if forras == "gep" and kulcs.casefold() == "status" \
                and self.sema.status_vedett(any(x.kulcs.casefold() == "status" for x in regi_tul)):
            # T127: a tilalom kis-nagybetűtől független és a törlésre is vonatkozik (a `status` kulcs a Status kijátszása lett volna)
            return self._elutasit([self._hiba("status_gep", "Only the user can fill in or change the Status field; machine writes cannot change it.",
                                              "Status")])
        if regi is None and muvelet == "torol":
            return {"ok": True, "fm_uj": None, "megerositheto": False, "valtozas": False, "problemak": []}
        elotte = (regi.kulcsok() if regi else [])
        if elotte.count(kulcs) > 1:
            return self._elutasit([self._hiba("duplikalt_kulcs", f"The ‘{kulcs}’ key appears more than once. Fix it in source mode.", kulcs)])

        vart = None
        uj_sorok: list[str] = []
        if muvelet == "beallit":
            t = tipus or (next((x.tipus for x in regi_tul if x.kulcs == kulcs), None)) or \
                elemzo.tipus_ertekbol(kulcs, ertek if not isinstance(ertek, str) else ertek)
            vart, hiba = _ertek_normal(t, ertek)
            if hiba:
                return self._elutasit([self._hiba("ertek_tipus", hiba, kulcs)])
            uj_sorok = _sorok(kulcs, vart)

        uj = self._alkalmaz(regi, ut, muvelet, kulcs, uj_sorok)

        # visszaolvasás-próba: az érintetlen kulcsok azonosak, az érintett a várt, a sorrend megmarad
        _, uj_hiba, uj_ertek = self._tulajdonsagok(uj, egyedi=True)          # T129: a duplikált kulcs a próbán elbukik
        vart_ertek = dict(regi_ertek)
        if muvelet == "torol":
            vart_ertek.pop(kulcs, None)
        else:
            vart_ertek[kulcs] = vart
        sorrend_vart = [k for k in elotte if k != kulcs]
        sorrend_uj = [k for k in uj.kulcsok() if k != kulcs]
        if uj_hiba or uj_ertek != vart_ertek or sorrend_uj != sorrend_vart:
            return self._elutasit([self._hiba(
                "belso_hiba", "This change cannot be made safely because the frontmatter structure is unusual. "
                              "Edit it in source mode.", kulcs)])

        elotte_p = self.problemak(ut, elotte, regi_ertek, van_fm=regi is not None)
        utana_p = self.problemak(ut, uj.kulcsok(), uj_ertek)
        uj_p = self.uj_sertesek(elotte_p, utana_p)
        kemeny = [p for p in uj_p if p["szint"] == HIBA]
        if kemeny:
            return self._elutasit(kemeny)
        if uj_p and not megerosit:
            return {"ok": False, "fm_uj": None, "megerositheto": True, "valtozas": True, "problemak": uj_p}
        szoveg = uj.szoveg()
        if regi is None and uj.blokkok:
            szoveg += uj.eol                  # új blokk: a záró `---` után üres sor (a séma-próba kéri)
        return {"ok": True, "fm_uj": szoveg, "megerositheto": False, "valtozas": szoveg != (fm or ""),
                "problemak": uj_p}

    # -------------------------------------------------- javaslatok (gépelés közbeni kiegészítés)

    def _ertekkeszlet_hasznalat(self) -> dict | None:
        """Az index `ertekkeszlet_hasznalat` olvasója index-generációnként egyszer (egy ellenőrzés — és egy higiénia-riport
        sok jegyzete — nem kérdez újra, amíg az index nem változott); `None`, ha az index nem kész vagy nincs ilyen olvasója."""
        gen = getattr(self.index, "generacio", None)
        tar = self._hasznalat_tar
        if gen is not None and tar is not None and tar[0] == gen:
            return tar[1]
        h = self._index_hiv("ertekkeszlet_hasznalat")
        if gen is not None and h is not None:
            self._hasznalat_tar = (gen, h)
        return h

    def _index_hiv(self, nev: str, *args):
        """Az index olvasó hívása; `None`, ha az index még nem kész (a javaslat ekkor csak a sémából jön)."""
        fv = getattr(self.index, nev, None)
        if fv is None:
            return None
        try:
            return fv(*args)
        except NemKesz:
            return None

    def kulcs_javaslatok(self, ut: str | None) -> dict:
        """A kulcsnév-javaslatok (az új tulajdonság neve, a nyers frontmatter kulcs-helye): az `ut` osztályának séma-kulcsai
        a séma sorrendjében, utánuk a `extra_kulcsok`, végül a vaultban használt többi kulcs jegyzetszám szerint. Elemenként
        `{kulcs, db, sema, tipus}`: `sema` igaz a séma kulcsán, `tipus` a vault `types.json` szerinti típus (ha van). Nem ír."""
        o = self.sema.osztaly(nfc(ut or ""))
        sema_kulcsok = [] if o["sema_nelkul"] else list(dict.fromkeys([*o["mezosorrend"], *self.sema.extra]))
        hasznalt = self._index_hiv("tulajdonsag_kulcsok")
        db = {nfc(x["kulcs"]): x["db"] for x in hasznalt or []}
        tipusok = getattr(self.index, "tipusok", {}) or {}
        ki, lat = [], set()
        for k in sema_kulcsok:
            ki.append({"kulcs": k, "db": db.get(k, 0), "sema": True, "tipus": tipusok.get(k)})
            lat.add(k)
        for x in hasznalt or []:
            k = nfc(x["kulcs"])
            if k not in lat:
                ki.append({"kulcs": k, "db": x["db"], "sema": False, "tipus": tipusok.get(k)})
                lat.add(k)
        return {"kulcsok": ki, "index_kesz": hasznalt is not None}

    def ertek_javaslatok(self, ut: str | None, kulcs: str | None) -> dict:
        """Egy kulcs érték-javaslatai: a vaultban már használt értékek jegyzetszámmal, és ahol a séma értékkészletet ad (a
        normál osztály `Tags` és `Status` mezője), az értékkészlet is (akkor is, ha a vaultban még senki nem használja). A
        `Tags` használati száma a címke-index szerinti (a frontmatter és a szövegbeli `#címke` együtt, a pontos címke). Elemenként
        `{ertek, db, sema}`: `sema` igaz/hamis, ha van értékkészlet (benne van-e), különben `None`. Sorrend: az értékkészlet
        elemei elöl (jegyzetszám, utána a séma sorrendje szerint), utánuk a többi jegyzetszám szerint. Nem ír; a séma
        szabálya (22(b)) a beíráskor érvényes, nem itt."""
        if not isinstance(kulcs, str) or not kulcs.strip():
            raise HttpError(400, "hiányzó `kulcs`", kod="tulajdonsag.kulcs_hianyzik")
        kulcs = nfc(kulcs.strip())
        o = self.sema.osztaly(nfc(ut or ""))
        keszlet: list[str] = []
        if o["ertekek"] and not o["sema_nelkul"]:
            keszlet = (self.sema.tags if kulcs == "Tags" else self.sema.status if kulcs == "Status" else None) or []
        if kulcs.casefold() == "tags":
            c = self._index_hiv("cimkek")
            hasznalt = None if c is None else [{"ertek": x["cimke"], "db": x["db"]} for x in c["cimkek"] if x["db"]]
        else:
            hasznalt = self._index_hiv("tulajdonsag_ertekek", kulcs)
        db: dict[str, int] = {}
        for x in hasznalt or []:
            e = nfc(x["ertek"]).removeprefix("#") if kulcs.casefold() == "tags" else nfc(x["ertek"])
            db[e] = db.get(e, 0) + x["db"]
        sorrend = {e: i for i, e in enumerate(keszlet)}
        ki = [{"ertek": e, "db": db.get(e, 0), "sema": True} for e in keszlet]
        ki.sort(key=lambda x: (-x["db"], sorrend[x["ertek"]]))
        tobbi = sorted((e for e in db if e not in sorrend), key=lambda e: (-db[e], e.lower()))
        ki += [{"ertek": e, "db": db[e], "sema": False if keszlet else None} for e in tobbi]
        return {"kulcs": kulcs, "ertekkeszlet": bool(keszlet), "ertekek": ki, "index_kesz": hasznalt is not None}

    # -------------------------------------------------- sablon-összefésülés (C32b, 26(d) módosítása)

    @staticmethod
    def _ures_ertek(ertek) -> bool:
        return ertek is None or ertek == [] or (isinstance(ertek, str) and not ertek.strip())

    def osszefesul(self, ut: str, fm: str | None, sablon_fm: str | None) -> dict:
        """A sablon (már kiértékelt) frontmatterének összefésülése a jegyzet frontmatterével, kulcsonként a `modosit`-on át
        (egy szabály-készlet: bájthű csere, séma, visszaolvasás-próba). Nem ír fájlt.

        Szabály: a sablon kulcsa, ami a jegyzetben nincs, **hozzáadódik**; a lista-érték (a két oldal bármelyike lista)
        **egyesül** (a jegyzet elemei elöl, a sablon új elemei utána); a meglévő, nem üres érték **nem íródik felül**
        (`megmaradt`); a jegyzet üres értéke (`Kulcs:`, `[]`) a sablon értékével kitöltődik. A séma-sértő kulcs **nem
        íródik csendben**: a `fuggo` listába kerül (`kulcs`, `ertek`, `tipus`, `problemak`), a felület a megerősítés után a
        `modosit` `megerosit: true` hívásával írja; a hiba szintű (pl. a Status gépi kitöltése nincs itt: ez felhasználói
        művelet) vagy nem szerkeszthető érték `kihagyva`. Válasz: `{ok, fm_uj, valtozas, hozzaadva, egyesitve, kitoltve,
        megmaradt, kihagyva, fuggo}`; `fm_uj` az összes tiszta változás után álló blokk (a függők nélkül)."""
        ut = nfc(ut or "")
        ki = {"ok": True, "fm_uj": fm, "valtozas": False, "hozzaadva": [], "egyesitve": [], "kitoltve": [],
              "megmaradt": [], "kihagyva": [], "fuggo": []}
        sab = _fm_elemez(sablon_fm)
        if sab is None:
            return ki
        sab_tul, sab_hiba, _ = self._tulajdonsagok(sab)
        if sab_hiba:
            ki["kihagyva"].append({"kulcs": None, "uzenet": f"The template frontmatter has invalid syntax: {frontmatter_hiba_angol(sab_hiba)}"})
            return ki
        _, regi_hiba, _ = self._tulajdonsagok(_fm_elemez(fm))
        if regi_hiba:
            ki["kihagyva"].append({"kulcs": None, "uzenet": f"The note frontmatter has invalid syntax ({frontmatter_hiba_angol(regi_hiba)}). Fix it in source mode first."})
            return ki
        aktualis = fm
        for t in sab_tul:
            if t.tipus == "unknown" or isinstance(t.ertek, dict):
                ki["kihagyva"].append({"kulcs": t.kulcs, "uzenet": "This value cannot be edited here."})
                continue
            _, _, jelenlegi = self._tulajdonsagok(_fm_elemez(aktualis))
            if t.kulcs in jelenlegi:
                regi = jelenlegi[t.kulcs]
                if isinstance(t.ertek, list) or isinstance(regi, list):
                    sab_elemek = self._lista(t.ertek)
                    regi_elemek = self._lista(regi)
                    uj_elemek = [x for x in sab_elemek if x not in regi_elemek]
                    if not uj_elemek:
                        continue
                    ertek, tipus, lista = [*regi_elemek, *uj_elemek], t.tipus, "egyesitve"
                    if tipus not in _LISTA_TIPUSOK:
                        tipus = "multitext"
                elif self._ures_ertek(regi) and not self._ures_ertek(t.ertek):
                    ertek, tipus, lista = t.ertek, t.tipus, "kitoltve"
                else:
                    if t.ertek != regi and not self._ures_ertek(t.ertek):
                        ki["megmaradt"].append(t.kulcs)
                    continue
            else:
                ertek, tipus, lista = t.ertek, t.tipus, "hozzaadva"
            r = self.modosit(ut, aktualis, "beallit", t.kulcs, ertek, tipus, False, "felhasznalo")
            if r["ok"]:
                if r["fm_uj"] is not None and r["valtozas"]:
                    aktualis = r["fm_uj"]
                    ki[lista].append(t.kulcs)
            elif r["megerositheto"]:
                ki["fuggo"].append({"kulcs": t.kulcs, "ertek": ertek, "tipus": tipus, "problemak": r["problemak"]})
            else:
                ki["kihagyva"].append({"kulcs": t.kulcs, "uzenet": (r["problemak"] or [{}])[0].get("uzenet", "This value cannot be written.")})
        ki["fm_uj"] = aktualis
        ki["valtozas"] = aktualis != (fm or "")
        return ki

    @staticmethod
    def _hiba(kod: str, uzenet: str, kulcs: str | None = None) -> dict:
        return {"kod": kod, "szint": HIBA, "kulcs": kulcs, "ertek": None, "uzenet": uzenet}

    @staticmethod
    def _elutasit(problemak: list[dict]) -> dict:
        return {"ok": False, "fm_uj": None, "megerositheto": False, "valtozas": False, "problemak": problemak}

    def _alkalmaz(self, regi: _Fm | None, ut: str, muvelet: str, kulcs: str, uj_sorok: list[str]) -> _Fm:
        if regi is None:
            return _Fm("\n", True, [_Blokk(kulcs, uj_sorok)] if muvelet == "beallit" else [])
        blokkok = [_Blokk(b.kulcs, list(b.sorok)) for b in regi.blokkok]
        idx = next((i for i, b in enumerate(blokkok) if b.kulcs == kulcs), None)
        if muvelet == "torol":
            if idx is not None:
                del blokkok[idx]
        elif idx is not None:
            blokkok[idx] = _Blokk(kulcs, uj_sorok)
        else:
            blokkok.insert(self._beszuras(blokkok, ut, kulcs), _Blokk(kulcs, uj_sorok))
        return _Fm(regi.eol, regi.vegen_eol, blokkok, regi.elo)

    def _beszuras(self, blokkok: list[_Blokk], ut: str, kulcs: str) -> int:
        """Az új kulcs helye: a séma sorrendje szerint az első nagyobb pozíciójú meglévő kulcs elé; különben az
        utolsó kulcs-blokk után (megjegyzés és üres sor nem előzi meg)."""
        kanon = self.sema.osztaly(ut)["mezosorrend"]
        poz = {k: i for i, k in enumerate(kanon)}
        if kulcs in poz:
            for i, b in enumerate(blokkok):
                if b.kulcs in poz and poz[b.kulcs] > poz[kulcs]:
                    return i
        utolso = max((i for i, b in enumerate(blokkok) if b.kulcs is not None), default=-1)
        return utolso + 1


def utvonalak(r) -> None:
    """A tulajdonság-szerkesztő végpontjai (C11b): mind tiszta olvasó/számoló, íróvégpont nincs."""
    def sema(k):
        return k.app.tulajdonsagok.sema.leiras(k.q.get("ut"))

    def elemez(k):
        t = k.torzs()
        return k.app.tulajdonsagok.elemez(t.get("ut"), t.get("fm"))

    def modosit(k):
        t = k.torzs()
        megerosit = t.get("megerosit")
        if megerosit is not None and not isinstance(megerosit, bool):         # T128: a `"false"` szöveg nem megerősítés
            raise HttpError(400, "a `megerosit` igaz vagy hamis lehet", kod="tulajdonsag.megerosit_logikai")
        return k.app.tulajdonsagok.modosit(
            t.get("ut"), t.get("fm"), t.get("muvelet"), t.get("kulcs"), t.get("ertek"), t.get("tipus"),
            megerosit is True, t.get("forras") or "felhasznalo")

    def osszefesul(k):
        t = k.torzs()
        for kulcs in ("fm", "sablon_fm"):
            if t.get(kulcs) is not None and not isinstance(t[kulcs], str):
                raise HttpError(400, f"a `{kulcs}` szöveg lehet", kod="tulajdonsag.kulcs_szoveg", param={"kulcs": kulcs})
        return k.app.tulajdonsagok.osszefesul(t.get("ut"), t.get("fm"), t.get("sablon_fm"))

    def kulcsok(k):
        return k.app.tulajdonsagok.kulcs_javaslatok(k.q.get("ut"))

    def ertekek(k):
        return k.app.tulajdonsagok.ertek_javaslatok(k.q.get("ut"), k.q.get("kulcs"))

    r.get("/api/vault/sema", sema)
    r.get("/api/vault/tulajdonsagok/kulcsok", kulcsok)                # a javaslatok: tiszta olvasók
    r.get("/api/vault/tulajdonsagok/ertekek", ertekek)
    r.post("/api/vault/tulajdonsagok/elemez", elemez)
    r.post("/api/vault/tulajdonsagok/osszefesul", osszefesul)
    r.post("/api/vault/tulajdonsagok/modosit", modosit)
    r.get("/api/vault/ikonok", lambda k: k.app.index.ikonok())
    r.get("/api/vault/cimkek", lambda k: k.app.index.cimkek())
