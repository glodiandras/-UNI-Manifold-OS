"""A Bases-kifejezések értékei és kényszerítései (C12; `docs/C12-TERV.md`, „Kényszerítések”).

Az érték egy Python-objektum: `None` (üres), `bool`, `int`/`float`, `str`, `list`, `dict`, vagy az itt definiált
típusok (`Datum`, `Idotartam`, `Link`, `Fajl`, `Cimke`, `Regex`, `Kep`, `Ikon`, `Html`). A hibás művelet
`FutasHiba`-t dob; a cella ezt `Hiba`-értékként mutatja, a szűrő a sort kihagyja.

Amit a dokumentáció nem rögzít, azt a terv táblája és a tesztek (`tests/test_bazis_ertekek.py`) rögzítik; a K11
(Obsidian-paritás) méri.
"""
from __future__ import annotations

import calendar
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from ..hibakod import angol_uzenet, json_param

NAP_MS = 86_400_000
_HONAP_NAPJA_MS = int(30.4375 * NAP_MS)         # csak összehasonlításhoz és a `number()`-hez


class FutasHiba(Exception):
    """Egy kifejezés kiértékelési hibája (rossz típus, ismeretlen függvény, null-on hívott metódus…). `kod` + `param`: a
    `hibakodok.BAZIS_ANGOL` kulcsa és skalár paraméterei; az `uzenet` az angol tartalék-mondat (10-bases-01)."""

    def __init__(self, kod: str, param: dict | None = None):
        self.kod = kod
        self.param = json_param(param)
        self.uzenet = angol_uzenet(kod, param, kod)
        super().__init__(self.uzenet)


class IdokeretHiba(RuntimeError):
    """A Bases-lekérdezés túllépte a teljes időkeretét (`[index] bazis_idokeret_mp`), vagy az elavult kérést megszakították
    (újabb kérés érkezett ugyanarra a nézetre; T040). **Nem `FutasHiba`**: azt a soronkénti kezelők lenyelik, ez az egész
    lekérdezést leállítja (a végpont `ok: false` + `hibak` választ ad, nem 500-at)."""

    def __init__(self, kod: str, megszakitva: bool = False):
        self.kod, self.param = kod, {}
        self.uzenet, self.megszakitva = angol_uzenet(kod), megszakitva
        super().__init__(self.uzenet)


class ErtekKeretHiba(RuntimeError):
    """A lekérdezés értékkerete betelt: az előállított értékek együttes mérete (T041: `repeat`, hosszú cella-értékek) a
    lekérdezésenkénti keretet meghaladta. Mint az `IdokeretHiba`, az egész lekérdezést leállítja."""

    def __init__(self, kod: str):
        self.kod, self.param = kod, {}
        self.uzenet = angol_uzenet(kod)
        super().__init__(self.uzenet)


class Keret:
    """Lekérdezésenkénti értékkeret (karakter/elem-egység): `fogyaszt(n)` csökkenti, a kimerülés `ErtekKeretHiba`."""
    __slots__ = ("maradt",)

    def __init__(self, osszes: int):
        self.maradt = int(osszes)

    def fogyaszt(self, n: int) -> None:
        self.maradt -= int(n)
        if self.maradt < 0:
            raise ErtekKeretHiba("bazis.futas.ertekkeret")


# ================================================================ típusok

@dataclass(frozen=True, slots=True)
class Datum:
    """Dátum vagy dátum-idő; naiv, helyi idő (a frontmatter dátumai is azok). `van_ido`: az érték idővel együtt áll."""
    ertek: datetime
    van_ido: bool = False


@dataclass(frozen=True, slots=True)
class Idotartam:
    honap: int = 0
    ms: float = 0

    def teljes_ms(self) -> float:
        return self.honap * _HONAP_NAPJA_MS + self.ms

    def szoveg(self) -> str:
        reszek, ms = [], abs(self.ms)
        elojel = "-" if self.honap < 0 or self.ms < 0 else ""
        ho = abs(self.honap)
        for egyseg, db in (("y", ho // 12), ("M", ho % 12)):
            if db:
                reszek.append(f"{db}{egyseg}")
        for egyseg, hossz in (("w", 7 * NAP_MS), ("d", NAP_MS), ("h", 3_600_000), ("m", 60_000), ("s", 1000)):
            db, ms = divmod(ms, hossz)
            if db:
                reszek.append(f"{int(db)}{egyseg}")
        if ms:
            reszek.append(f"{szam_szoveg(ms)}ms")
        return elojel + " ".join(reszek) if reszek else "0s"


@dataclass(frozen=True, slots=True)
class Link:
    """`cel`: a link célja szövegként (cső és horgony nélkül); `ut`: a feloldott vault-út, vagy `None`;
    `megjelenites`: a megjelenített szöveg (`[[cél|szöveg]]`); `kulso`: URL."""
    cel: str
    megjelenites: object = None
    ut: str | None = None
    alcel: str | None = None
    kulso: bool = False


class Fajl:
    """Hivatkozás a közös `Tabla` egy sorára (`adat.Sor`): így más jegyzet tulajdonságai is elérhetők."""
    __slots__ = ("sor", "tabla")

    def __init__(self, sor, tabla):
        self.sor, self.tabla = sor, tabla


@dataclass(frozen=True, slots=True)
class Cimke:
    """Címke, mindig `#`-tel (a `file.tags` elemei)."""
    szoveg: str


class Regex:
    """Reguláris kifejezés (`/…/gi` literál). A `regex` csomag V0 módja; a keresés időkorlátos."""
    __slots__ = ("minta", "zaszlok", "rx")
    IDOKORLAT_MP = 0.25

    def __init__(self, minta: str, zaszlok: str = ""):
        import regex
        self.minta, self.zaszlok = minta, zaszlok
        f = regex.V0
        if "i" in zaszlok:
            f |= regex.I
        if "m" in zaszlok:
            f |= regex.M
        if "s" in zaszlok:
            f |= regex.S
        try:
            self.rx = regex.compile(minta, f)
        except regex.error as e:
            raise FutasHiba("bazis.futas.regex_hibas", {"e": e}) from e

    @property
    def globalis(self) -> bool:
        return "g" in self.zaszlok

    def keres(self, s: str):
        try:
            return self.rx.search(s, concurrent=True, timeout=self.IDOKORLAT_MP)
        except TimeoutError:
            raise FutasHiba("bazis.futas.regex_lassu") from None

    def minden(self, s: str) -> list:
        try:
            return list(self.rx.finditer(s, concurrent=True, timeout=self.IDOKORLAT_MP))
        except TimeoutError:
            raise FutasHiba("bazis.futas.regex_lassu") from None

    def szoveg(self) -> str:
        return f"/{self.minta}/{self.zaszlok}"


@dataclass(frozen=True, slots=True)
class Kep:
    """`image()` eredménye: vault-út, külső URL vagy hex szín (pontosan egy van kitöltve)."""
    ut: str | None = None
    url: str | None = None
    szin: str | None = None


@dataclass(frozen=True, slots=True)
class Ikon:
    nev: str


@dataclass(frozen=True, slots=True)
class Html:
    szoveg: str


@dataclass(frozen=True, slots=True)
class Hiba:
    """Hibás képlet értéke a cellában (nem kivétel: egy cella hibája nem dönti el a nézetet)."""
    uzenet: str


# ================================================================ típusnevek

def _szam_e(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def tipus_neve(x) -> str:
    """A típus angol neve (hibaüzenethez)."""
    if x is None:
        return "empty value"
    if isinstance(x, bool):
        return "boolean"
    if _szam_e(x):
        return "number"
    return {str: "text", list: "list", dict: "object", Datum: "date", Idotartam: "duration", Link: "link",
            Fajl: "file", Cimke: "tag", Regex: "regex", Kep: "image", Ikon: "icon", Html: "html",
            Hiba: "error"}.get(type(x), type(x).__name__)


def tipus_kulcs(x) -> str:
    """A típus neve az `isType()` és a metódus-kiosztás számára."""
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "boolean"
    if _szam_e(x):
        return "number"
    return {str: "string", list: "list", dict: "object", Datum: "date", Idotartam: "duration", Link: "link",
            Fajl: "file", Cimke: "tag", Regex: "regexp", Kep: "image", Ikon: "icon", Html: "html",
            Hiba: "error"}.get(type(x), "object")


# ================================================================ számok

def szam(x):
    """A szám kanonikus alakja: az egész értékű, véges `float` `int` (a JavaScriptben nincs különbség)."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        return int(x)
    return x


def szam_szoveg(x) -> str:
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        if math.isinf(x):
            return "Infinity" if x > 0 else "-Infinity"
        x = szam(x)
    return str(x)


def kerekit(x, jegyek: int = 0):
    """JavaScript-szerű kerekítés (`Math.round`: a fél felfelé). A jegyek száma −100…100 (T041: a `10 ** jegyek` korlátlanul
    nagy egész lett volna, a `round(2000000000)` percekig tartó, memóriát evő számítás)."""
    if not _szam_e(x) or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return x
    if not -100 <= jegyek <= 100:
        raise FutasHiba("bazis.futas.round_jegyek")
    p = 10 ** jegyek
    return szam(math.floor(x * p + 0.5) / p)


def fixre(x, pontossag: int) -> str:
    """`Number.prototype.toFixed`: a pontos bináris érték, a fél felfelé (előjeltől függetlenül). A JS szerint az
    `|x| ≥ 1e21` szám a `String(x)` alakját adja (`1e+21`). A kerekítés **helyi** `decimal`-kontextusban fut (T155, C31):
    az alap 28 jegyes pontosság a 28 jegynél hosszabb eredményen (`(1e20).toFixed(10)`) `InvalidOperation`-nel állt meg."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return szam_szoveg(x)
    if abs(x) >= 1e21:
        return szam_szoveg(float(x))
    with localcontext() as k:
        k.prec = 400                                      # 21 egész jegy + legfeljebb 100 tizedes bőven elfér
        d = Decimal(x)
        neg = d < 0
        q = Decimal(1).scaleb(-pontossag)
        s = str(abs(d).quantize(q, rounding=ROUND_HALF_UP))
    return ("-" if neg else "") + s                      # a JS a negatív előjelet megtartja: (-0.001).toFixed(2) = "-0.00"


# ================================================================ igazság, szöveg, egyenlőség

def igaz_e(x) -> bool:
    """JavaScript-igazság: hamis a `null`, a `false`, a `0`, a `NaN` és az üres szöveg; az üres lista igaz."""
    if x is None or x is False:
        return False
    if isinstance(x, float) and math.isnan(x):
        return False
    if _szam_e(x):
        return x != 0
    if isinstance(x, str):
        return x != ""
    return True


def _nev_torzs(ut: str) -> str:
    n = ut.rsplit("/", 1)[-1]
    return n[:-3] if n.lower().endswith(".md") else n


def link_nev(x: Link) -> str:
    """A link megjelenített neve."""
    if x.megjelenites is not None:
        return szovegge(x.megjelenites)
    return _nev_torzs(x.ut or x.cel) if not x.kulso else x.cel


def szovegge(x) -> str:
    """`toString()`: az üres érték üres szöveg; a lista elemei vesszővel (`"1,2,3"`, mint a JavaScriptben)."""
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if _szam_e(x):
        return szam_szoveg(x)
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return ",".join(szovegge(e) for e in x)
    if isinstance(x, dict):
        return "[object Object]"
    if isinstance(x, Datum):
        return datum_formaz(x, "YYYY-MM-DD HH:mm:ss" if x.van_ido else "YYYY-MM-DD")
    if isinstance(x, Idotartam):
        return x.szoveg()
    if isinstance(x, Link):
        return link_nev(x)
    if isinstance(x, Fajl):
        return x.sor.ut
    if isinstance(x, Cimke):
        return x.szoveg
    if isinstance(x, Regex):
        return x.szoveg()
    if isinstance(x, Html):
        return x.szoveg
    if isinstance(x, Ikon):
        return x.nev
    if isinstance(x, Hiba):
        return x.uzenet
    return str(x)


def _cimke_alap(s: str) -> str:
    return unicodedata.normalize("NFC", s).lstrip("#").casefold()


def egyenlo(a, b) -> bool:
    """`==`: azonos típus érték szerint; a lista elemenként, sorrendben; a `Link`/`Fajl` a feloldott út szerint;
    a `Cimke` és a szöveg a vezető `#` és a kis-nagybetű nélkül; a dátum azonos pillanat."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _szam_e(a) and _szam_e(b):
        return a == b
    if isinstance(a, Cimke) or isinstance(b, Cimke):
        if isinstance(a, (Cimke, str)) and isinstance(b, (Cimke, str)):
            return _cimke_alap(a.szoveg if isinstance(a, Cimke) else a) == \
                _cimke_alap(b.szoveg if isinstance(b, Cimke) else b)
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, (Link, Fajl)) and isinstance(b, (Link, Fajl)):
        ua = a.sor.ut if isinstance(a, Fajl) else a.ut
        ub = b.sor.ut if isinstance(b, Fajl) else b.ut
        if ua is not None or ub is not None:
            return ua == ub
        return a.cel == b.cel                                    # feloldatlan linkek: a cél szövege
    if isinstance(a, Datum) and isinstance(b, Datum):
        return a.ertek == b.ertek
    if isinstance(a, Idotartam) and isinstance(b, Idotartam):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(egyenlo(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(egyenlo(a[k], b[k]) for k in a)
    if isinstance(a, Regex) and isinstance(b, Regex):
        return (a.minta, a.zaszlok) == (b.minta, b.zaszlok)
    return False


def hasonlit(a, b) -> int | None:
    """`< > <= >=` alapja: -1, 0, 1; `None`, ha a két érték nem összehasonlítható (vegyes típus, üres)."""
    if _szam_e(a) and _szam_e(b):
        if math.isnan(a) or math.isnan(b):
            return None
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    if isinstance(a, Datum) and isinstance(b, Datum):
        return (a.ertek > b.ertek) - (a.ertek < b.ertek)
    if isinstance(a, Idotartam) and isinstance(b, Idotartam):
        x, y = a.teljes_ms(), b.teljes_ms()
        return (x > y) - (x < y)
    return None


def kulcs(x):
    """Hashelhető, `egyenlo`-val összhangban álló kulcs (egyediség, csoportosítás)."""
    if x is None:
        return ("n",)
    if isinstance(x, bool):
        return ("b", x)
    if _szam_e(x):
        return ("s", x)
    if isinstance(x, str):
        return ("t", x)
    if isinstance(x, Datum):
        return ("d", x.ertek)
    if isinstance(x, Idotartam):
        return ("i", x.honap, x.ms)
    if isinstance(x, Link):
        return ("l", x.ut if x.ut is not None else x.cel)
    if isinstance(x, Fajl):
        return ("l", x.sor.ut)
    if isinstance(x, Cimke):
        return ("c", _cimke_alap(x.szoveg))
    if isinstance(x, list):
        return ("L", tuple(kulcs(e) for e in x))
    if isinstance(x, dict):
        return ("o", tuple(sorted((k, kulcs(v)) for k, v in x.items())))
    return ("x", szovegge(x))


# ================================================================ rendezés

def _szoveg_kulcs(s: str) -> tuple:
    """Kis-nagybetű- és ékezetfüggetlen elsődleges, ékezetes másodlagos kulcs (a `localeCompare` közelítése)."""
    nfd = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in nfd if not unicodedata.combining(c)), nfd


def _datum_s(dt: datetime) -> float:
    """A dátum Unix-ideje másodpercben. A `datetime.timestamp()` a helyi időzónán át számol (a `0001-01-01` `ValueError`,
    a `9999-12-31` néhol `OverflowError`: T041); ilyenkor az időzóna-független epoch-különbség (a rendezés ettől monoton marad)."""
    try:
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo) if dt.tzinfo else datetime(1970, 1, 1)
        return (dt - epoch).total_seconds()


def rendezo_kulcs(x) -> tuple:
    """Rendezési kulcs: az üres a legkisebb (a csökkenő rendezés ezt megfordítja); típusonként csoportosít."""
    if x is None:
        return (0,)
    if isinstance(x, bool):
        return (1, int(x))
    if _szam_e(x):
        return (2, float("-inf") if isinstance(x, float) and math.isnan(x) else x)
    if isinstance(x, Datum):
        return (3, _datum_s(x.ertek))
    if isinstance(x, Idotartam):
        return (4, x.teljes_ms())
    if isinstance(x, str):
        return (5, *_szoveg_kulcs(x))
    if isinstance(x, (Cimke, Link, Fajl)):
        return (5, *_szoveg_kulcs(szovegge(x)))
    if isinstance(x, list):
        return (6, tuple(rendezo_kulcs(e) for e in x))
    return (7, *_szoveg_kulcs(szovegge(x)))


# ================================================================ időtartam és dátum

_EGYSEG = {"y": ("ho", 12), "M": ("ho", 1), "d": ("ms", NAP_MS), "w": ("ms", 7 * NAP_MS), "h": ("ms", 3_600_000),
           "m": ("ms", 60_000), "s": ("ms", 1000)}
_SZO_EGYSEG = {"year": "y", "years": "y", "month": "M", "months": "M", "day": "d", "days": "d", "week": "w",
               "weeks": "w", "hour": "h", "hours": "h", "minute": "m", "minutes": "m", "second": "s", "seconds": "s"}
_IDOTARTAM_RE = re.compile(r"\s*([+-]?\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*")


def idotartam(s: str) -> Idotartam | None:
    """Időtartam-szöveg (`1M`, `4h`, `1 day`, `2 weeks 3d`); `None`, ha a szöveg nem az."""
    if not isinstance(s, str) or not s.strip():
        return None
    honap, ms, pos = 0, 0.0, 0
    while pos < len(s):
        m = _IDOTARTAM_RE.match(s, pos)
        if not m:
            return None
        pos = m.end()
        egyseg = _EGYSEG.get(m.group(2)) and m.group(2) or _SZO_EGYSEG.get(m.group(2).lower())
        if egyseg is None:
            return None
        fajta, szorzo = _EGYSEG[egyseg]
        szam_ = float(m.group(1))
        if fajta == "ho":
            if not szam_.is_integer():
                return None
            honap += int(szam_) * szorzo
        else:
            ms += szam_ * szorzo
    return Idotartam(honap, szam(ms))


def datum_hozzaad(d: Datum, i: Idotartam, elojel: int = 1) -> Datum:
    dt = d.ertek
    try:
        if i.honap:
            ossz = dt.year * 12 + (dt.month - 1) + elojel * i.honap
            ev, ho = divmod(ossz, 12)
            dt = dt.replace(year=ev, month=ho + 1, day=min(dt.day, calendar.monthrange(ev, ho + 1)[1]))
        dt = dt + timedelta(milliseconds=elojel * i.ms)
    except (OverflowError, ValueError):
        raise FutasHiba("bazis.futas.datum_tartomany") from None
    return Datum(dt, d.van_ido or (i.ms % NAP_MS != 0))


_DATUM_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?)?$")


def datum_szovegbol(s: str) -> Datum | None:
    """`YYYY-MM-DD`, `YYYY-MM-DD HH:mm[:ss]`, ISO `T`-vel; az időzóna helyi időre vált; hibásra `None`."""
    m = _DATUM_RE.match(s.strip()) if isinstance(s, str) else None
    if not m:
        return None
    ev, ho, nap, ora, perc, mp, tort, zona = m.groups()
    try:
        dt = datetime(int(ev), int(ho), int(nap), int(ora or 0), int(perc or 0), int(mp or 0),
                      int((tort or "0")[:6].ljust(6, "0")))
    except ValueError:
        return None
    if zona:
        from datetime import timezone
        z = timezone.utc if zona == "Z" else timezone(
            (1 if zona[0] == "+" else -1) * timedelta(hours=int(zona[1:3]), minutes=int(zona[-2:])))
        dt = dt.replace(tzinfo=z).astimezone().replace(tzinfo=None)
    return Datum(dt, ora is not None)


_HONAP = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
_NAP = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_FORMA_RE = re.compile(r"\[[^\]]*\]|YYYY|YY|Y|MMMM|MMM|MM|M|Do|DD|D|dddd|ddd|dd|d|HH|H|hh|h|kk|k|mm|m|ss|s|"
                       r"SSS|SS|S|A|a|ZZ|Z|X|x|Q|WW|W|ww|w|E|e")


def datum_formaz(d: Datum, minta: str) -> str:
    """Moment-tokenekkel (angol nevek)."""
    dt = d.ertek
    ora12 = dt.hour % 12 or 12

    def csere(m):
        t = m.group(0)
        if t[0] == "[":
            return t[1:-1]
        iso = dt.isocalendar()
        return {
            "YYYY": f"{dt.year:04d}", "YY": f"{dt.year % 100:02d}", "Y": str(dt.year),
            "MMMM": _HONAP[dt.month - 1], "MMM": _HONAP[dt.month - 1][:3], "MM": f"{dt.month:02d}",
            "M": str(dt.month), "Do": f"{dt.day}{_sorszam_vege(dt.day)}", "DD": f"{dt.day:02d}", "D": str(dt.day),
            "dddd": _NAP[dt.weekday()], "ddd": _NAP[dt.weekday()][:3], "dd": _NAP[dt.weekday()][:2],
            "d": str((dt.weekday() + 1) % 7), "E": str(dt.weekday() + 1), "e": str((dt.weekday() + 1) % 7),
            "HH": f"{dt.hour:02d}", "H": str(dt.hour), "hh": f"{ora12:02d}", "h": str(ora12),
            "kk": f"{dt.hour or 24:02d}", "k": str(dt.hour or 24),
            "mm": f"{dt.minute:02d}", "m": str(dt.minute), "ss": f"{dt.second:02d}", "s": str(dt.second),
            "SSS": f"{dt.microsecond // 1000:03d}", "SS": f"{dt.microsecond // 10000:02d}",
            "S": str(dt.microsecond // 100000), "A": "AM" if dt.hour < 12 else "PM",
            "a": "am" if dt.hour < 12 else "pm", "Q": str((dt.month - 1) // 3 + 1),
            "WW": f"{iso[1]:02d}", "W": str(iso[1]), "ww": f"{iso[1]:02d}", "w": str(iso[1]),
            "X": str(int(_datum_s(dt))), "x": str(int(_datum_s(dt) * 1000)),
            "ZZ": _eltolas_szoveg(dt, ""), "Z": _eltolas_szoveg(dt, ":"),
        }[t]
    return _FORMA_RE.sub(csere, minta)


def _eltolas_szoveg(dt: datetime, elvalaszto: str) -> str:
    """A `Z` (`+02:00`) és a `ZZ` (`+0200`) token: a dátum **helyi** UTC-eltolása az adott pillanatban (nyári időben más),
    ahogy a moment a böngésző időzónájából adja (T155, C31). A naiv dátum helyi idő; a tartományon kívüli dátum `+00:00`."""
    try:
        eltolas = (dt if dt.tzinfo else dt.astimezone()).utcoffset()
    except (ValueError, OverflowError, OSError):
        eltolas = None
    perc = int(eltolas.total_seconds() // 60) if eltolas is not None else 0
    jel = "-" if perc < 0 else "+"
    ora, perc = divmod(abs(perc), 60)
    return f"{jel}{ora:02d}{elvalaszto}{perc:02d}"


def _sorszam_vege(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def datum_relativ(d: Datum, most: Datum) -> str:
    """Moment `fromNow` küszöbei: „3 days ago”, „in an hour”."""
    kul = (most.ertek - d.ertek).total_seconds()
    mult = kul >= 0
    s = abs(kul)
    if s < 45:
        szoveg = "a few seconds"
    elif s < 90:
        szoveg = "a minute"
    elif s < 45 * 60:
        szoveg = f"{round(s / 60)} minutes"
    elif s < 90 * 60:
        szoveg = "an hour"
    elif s < 22 * 3600:
        szoveg = f"{round(s / 3600)} hours"
    elif s < 36 * 3600:
        szoveg = "a day"
    elif s < 26 * 86400:
        szoveg = f"{round(s / 86400)} days"
    elif s < 45 * 86400:
        szoveg = "a month"
    elif s < 320 * 86400:
        szoveg = f"{round(s / (30.4375 * 86400))} months"
    elif s < 548 * 86400:
        szoveg = "a year"
    else:
        szoveg = f"{round(s / (365.25 * 86400))} years"
    return f"{szoveg} ago" if mult else f"in {szoveg}"


def datum_mezo(d: Datum, nev: str):
    dt = d.ertek
    return {"year": dt.year, "month": dt.month, "day": dt.day, "hour": dt.hour, "minute": dt.minute,
            "second": dt.second, "millisecond": dt.microsecond // 1000}.get(nev)


def datum_ms(d: Datum) -> int:
    return szam(_datum_s(d.ertek) * 1000)


# ================================================================ műveletek

def _id(x) -> Idotartam | None:
    return x if isinstance(x, Idotartam) else idotartam(x) if isinstance(x, str) else None


def _hiba2(kod: str, a, b) -> FutasHiba:
    return FutasHiba(kod, {"a": tipus_neve(a), "b": tipus_neve(b)})


def osszead(a, b):
    """`+`: dátum + időtartam(-szöveg) → dátum; ha bármelyik szöveg → összefűzés (az üres `""`); üres + szám → üres."""
    if isinstance(a, Datum):
        i = _id(b)
        if i is not None:
            return datum_hozzaad(a, i)
    if isinstance(a, Idotartam) and isinstance(b, Datum):
        return datum_hozzaad(b, a)
    if isinstance(a, str) or isinstance(b, str):
        return szovegge(a) + szovegge(b)
    if isinstance(a, Idotartam) and isinstance(b, Idotartam):
        return Idotartam(a.honap + b.honap, szam(a.ms + b.ms))
    if a is None and (b is None or _szam_e(b)) or b is None and _szam_e(a):
        return None
    if _szam_e(a) and _szam_e(b):
        return szam(a + b)
    raise _hiba2("bazis.futas.nem_osszeadhato", a, b)


def kivon(a, b):
    """`-`: szám−szám; dátum−dátum → ezredmásodperc; dátum−időtartam(-szöveg) → dátum. A dátum−dátum a két **pillanat**
    különbsége (a JS `Date`-é): a helyi naiv dátumok a helyi időzónán át, így a nyári időszámítás váltásán át a
    különbség 23 vagy 25 óra (T155, C31)."""
    if isinstance(a, Datum):
        if isinstance(b, Datum):
            return szam(round((_datum_s(a.ertek) - _datum_s(b.ertek)) * 1000, 3))
        i = _id(b)
        if i is not None:
            return datum_hozzaad(a, i, -1)
    if isinstance(a, Idotartam) and isinstance(b, Idotartam):
        return Idotartam(a.honap - b.honap, szam(a.ms - b.ms))
    if a is None and (b is None or _szam_e(b)) or b is None and _szam_e(a):
        return None
    if _szam_e(a) and _szam_e(b):
        return szam(a - b)
    raise _hiba2("bazis.futas.nem_vonhato_ki", a, b)


def szoroz(a, b):
    if isinstance(a, Idotartam) and _szam_e(b):
        return Idotartam(int(a.honap * b), szam(a.ms * b))
    if _szam_e(a) and _szam_e(b):
        try:
            return szam(a * b)
        except OverflowError:
            return math.inf
    raise _hiba2("bazis.futas.nem_szorozhato", a, b)


def oszt(a, b):
    if isinstance(a, Idotartam) and _szam_e(b) and b != 0:
        return Idotartam(int(a.honap / b), szam(a.ms / b))
    if _szam_e(a) and _szam_e(b):
        if b == 0:
            if a == 0 or (isinstance(a, float) and math.isnan(a)):
                return math.nan
            return math.inf if (a > 0) == (math.copysign(1, b) > 0) else -math.inf
        return szam(a / b)
    raise _hiba2("bazis.futas.nem_oszthato", a, b)


def modulo(a, b):
    """`%`: az eredmény előjele az osztandóé (JavaScript)."""
    if _szam_e(a) and _szam_e(b):
        if isinstance(a, int) and isinstance(b, int) and b != 0:
            r = abs(a) % abs(b)
            return r if a >= 0 else -r
        if b == 0 or (isinstance(a, float) and (math.isnan(a) or math.isinf(a))):
            return math.nan
        return szam(math.fmod(a, b))
    raise _hiba2("bazis.futas.nincs_maradek", a, b)


def negal(a):
    if _szam_e(a):
        return szam(-a)
    if isinstance(a, Idotartam):
        return Idotartam(-a.honap, -a.ms)
    raise FutasHiba("bazis.futas.nem_negalhato", {"tipus": tipus_neve(a)})


# ================================================================ frontmatter-érték → kifejezés-érték

_LINK_RE = re.compile(r"^!?\[\[([^\]|#]*)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]$")


def link_szovegbol(s: str, felold=None) -> Link | None:
    """A teljes `[[cél#horgony|szöveg]]` szövegből `Link` (más szövegből `None`); `felold(cél) → út | None`."""
    m = _LINK_RE.match(s.strip()) if isinstance(s, str) else None
    if not m:
        return None
    cel, alcel, kijelzes = (m.group(1) or "").strip(), m.group(2), m.group(3)
    return Link(cel, kijelzes.strip() if kijelzes else None, felold(cel) if felold and cel else None,
                alcel.strip() if alcel else None)


def fm_ertekbol(v, tipus: str | None, felold=None):
    """Az index JSON-értéke → kifejezés-érték: a teljes szöveges `[[…]]` `Link`; a `date`/`datetime` típusú
    szöveg `Datum`; a lista és az objektum rekurzívan. `felold(cél)`: a link feloldása a sor fájljából."""
    if isinstance(v, str):
        if tipus in ("date", "datetime"):
            d = datum_szovegbol(v)
            return d if d is not None else v
        return link_szovegbol(v, felold) or v
    if isinstance(v, list):
        return [fm_ertekbol(e, None, felold) for e in v]
    if isinstance(v, dict):
        return {k: fm_ertekbol(e, None, felold) for k, e in v.items()}
    return v


# ================================================================ kimenet (JSON)

def kimenet(x):
    """Az érték JSON-alakja a felületnek: primitív nyersen, más címkézve (`{t: …}`)."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if _szam_e(x):
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return {"t": "szam", "v": szam_szoveg(x)}
        return x
    if isinstance(x, list):
        return {"t": "lista", "e": [kimenet(e) for e in x]}
    if isinstance(x, dict):
        return {"t": "objektum", "e": {k: kimenet(e) for k, e in x.items()}}
    if isinstance(x, Datum):
        return {"t": "datum", "iso": x.ertek.isoformat(timespec="seconds") if x.van_ido else x.ertek.date().isoformat(),
                "ido": x.van_ido}
    if isinstance(x, Idotartam):
        return {"t": "idotartam", "szoveg": x.szoveg(), "ms": x.teljes_ms()}
    if isinstance(x, Link):
        k = {"t": "link", "cel": x.cel, "ut": x.ut, "nev": link_nev(x)}
        if x.alcel:
            k["alcel"] = x.alcel
        if x.kulso:
            k["kulso"] = True
        return k
    if isinstance(x, Fajl):
        return {"t": "link", "cel": x.sor.ut, "ut": x.sor.ut, "nev": _nev_torzs(x.sor.ut)}
    if isinstance(x, Cimke):
        return {"t": "cimke", "v": x.szoveg}
    if isinstance(x, Regex):
        return {"t": "regex", "v": x.szoveg()}
    if isinstance(x, Kep):
        return {"t": "kep", **{k: v for k, v in (("ut", x.ut), ("url", x.url), ("szin", x.szin)) if v}}
    if isinstance(x, Ikon):
        return {"t": "ikon", "nev": x.nev}
    if isinstance(x, Html):
        return {"t": "html", "v": x.szoveg}
    if isinstance(x, Hiba):
        return {"t": "hiba", "u": x.uzenet}
    if hasattr(x, "mint_dict"):                         # `note` / `formula` mint érték
        return kimenet(x.mint_dict())
    return str(x)
