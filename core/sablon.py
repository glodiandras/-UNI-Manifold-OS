"""Sablonmotor (C15): a napi jegyzet és a „Sablon beszúrása” **egyetlen** kiértékelője.

Változók (az Obsidian Templates magjával kompatibilisen):

    {{date}}  {{date:FORMÁTUM}}   a nap, alapból `YYYY-MM-DD` (`[sablon] datum`)
    {{time}}  {{time:FORMÁTUM}}   az idő, alapból `HH:mm` (`[sablon] ido`)
    {{title}}                     a jegyzet neve (kiterjesztés nélkül)
    {{cursor}}                    a kurzor helye (2.0-s kiegészítés; az Obsidian nem ismeri, szövegként hagyná)

A változónév kis-nagybetűtől független (`{{DATE}}`), az üres formátum (`{{date:}}`) az alapformátumot adja, a magyar
rövid hónapnevek a moment `hu` locale-jéé (`jan.`, `feb.`, `márc.` …) — az Obsidian 1.14.4 Templates magja szerint
(C31, T156; statikus olvasás). Szándékos 2.0-eltérés: egy menet (a `{{title}}` értéke nem értékelődik újra; az
Obsidian előbb a címet cseréli, utána a dátumot), a kapcsos zárójelen belüli szóköz (`{{ date }}`) is változó, és a
`{{cursor}}` (az Obsidian szövegként hagyja). Az ismeretlen `{{valami}}` érintetlen marad. A formátum a moment.js részhalmaza: `YYYY YY MMMM MMM MM M DDDD DDD
DD D Do dddd ddd dd d E HH H hh h mm m ss s A a WW W` és a `[szó]` escape; ismeretlen betű szó szerint megy át.
A hónap- és napnevek a `[sablon] nyelv` szerintiek (`hu`, `en`).

A kiértékelés egyetlen menet: a behelyettesített szöveg nem értékelődik újra (a `{{title}}`-be írt `{{cursor}}`
szöveg marad). A `kurzor` a CodeMirror szerinti UTF-16 egységben adja az első `{{cursor}}` helyét a kimenetben.

Csak olvas: a vaultba a motor nem ír (a napi jegyzet létrehozása a `naplo.py`-é, a beszúrás a szerkesztőé).
"""
from __future__ import annotations

import calendar
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from . import rejtett
from .index.maszk import FM_RE
from .utvonalak import HttpError, kodos

ALAP_DATUM = "YYYY-MM-DD"
ALAP_IDO = "HH:mm"
ALAP_MAPPA = "_Template"
ALAP_NYELV = "en"                       # a tartalmi nyelv alapja: angol (semleges alap); `hu`-t a munkatér nyelve vagy `[sablon] nyelv` ad
NYELVEK = ("hu", "en")

_NEVEK = {
    "hu": {
        "honap": ["január", "február", "március", "április", "május", "június", "július", "augusztus",
                  "szeptember", "október", "november", "december"],
        # a moment `hu` locale `monthsShort`-ja (az Obsidian 1.14.4-be épített moment; C31, T156)
        "honap_rovid": ["jan.", "feb.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.", "okt.", "nov.", "dec."],
        # hétfővel kezdve (a Python `weekday()` sorrendje)
        "nap": ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"],
        "nap_rovid": ["hét", "kedd", "sze", "csüt", "pén", "szo", "vas"],
        "nap_min": ["h", "k", "sze", "cs", "p", "szo", "v"],
        "de_du": ("de", "du"),
        "sorszam": lambda n: f"{n}.",
        # a moment `hu` locale hétszabálya: a hét hétfővel kezd, az első hét a január 4-ét tartalmazza (ISO)
        "het_dow": 1, "het_doy": 4,
        # a moment `hu` locale hosszú formátumai (`LT` … `llll`)
        "hosszu": {"LT": "H:mm", "LTS": "H:mm:ss", "L": "YYYY.MM.DD.", "LL": "YYYY. MMMM D.", "LLL": "YYYY. MMMM D. H:mm",
                   "LLLL": "YYYY. MMMM D., dddd H:mm", "l": "YYYY.M.D.", "ll": "YYYY. MMM D.", "lll": "YYYY. MMM D. H:mm",
                   "llll": "YYYY. MMM D., ddd H:mm"},
    },
    "en": {
        "honap": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"],
        "honap_rovid": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "nap": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "nap_rovid": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "nap_min": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        "de_du": ("am", "pm"),
        "sorszam": lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}",
        # a moment `en` locale hétszabálya: vasárnappal kezd, az első hét a január 1-jét tartalmazza
        "het_dow": 0, "het_doy": 6,
        "hosszu": {"LT": "h:mm A", "LTS": "h:mm:ss A", "L": "MM/DD/YYYY", "LL": "MMMM D, YYYY", "LLL": "MMMM D, YYYY h:mm A",
                   "LLLL": "dddd, MMMM D, YYYY h:mm A", "l": "M/D/YYYY", "ll": "MMM D, YYYY", "lll": "MMM D, YYYY h:mm A",
                   "llll": "ddd, MMM D, YYYY h:mm A"},
    },
}

# A moment.js formázó-tokenjei (2.30): a `[…]` és a `\x` escape az első két alternatíva; hosszabb token előbb. A támogatott
# tokenek a `_TOKEN` 3. csoportja; a nem támogatott (`z zz`, a korszak-tokenek `N…`/`y…`) a 4. — szó szerint mennek át, és a
# `ismeretlen_tokenek` jelenti őket (a Beállítások előnézete).
_TOKEN = re.compile(
    r"\[([^\]]*)\]|\\(.)|"
    r"(LTS|LT|LLLL|LLL|LL|L|llll|lll|ll|l|YYYYYY|YYYYY|YYYY|YY|Y|MMMM|MMM|MM|Mo|M|Qo|Q|DDDD|DDDo|DDD|DD|Do|D|"
    r"dddd|ddd|dd|do|d|E|e|Wo|WW|W|wo|ww|w|gggg|gg|GGGG|GG|A|a|HH|H|hh|h|kk|k|mm|m|ss|s|S{1,9}|ZZ|Z|X|x)|"
    r"(zz|z|N{1,5}|yo|y{1,4})")
# A változónév kis-nagybetűtől független (az Obsidian Templates magja: `/{{(date|time)(?::(.*?))?}}/gi` és
# `new RegExp("{{title}}", "gi")`; statikus olvasás, 1.14.4 — C31, T156).
_VALTOZO = re.compile(r"\{\{\s*(date|time|title|cursor|content|fromTitle|newTitle)\s*(?::([^{}]*?))?\s*\}\}", re.IGNORECASE)
# A Note composer kivonás-sablonjának többletváltozói (`extra`): csak kérésre helyettesítődnek, különben szövegként maradnak
EXTRA_VALTOZOK = ("content", "fromtitle", "newtitle")


class SablonHiba(HttpError):
    """Hibás sablonkérés (400/404)."""


def nyelv_kod(nyelv) -> str:
    """A támogatott nyelvkód (`hu`/`en`); minden más (üres, ismeretlen) angol — soha nem magyar alapból."""
    return nyelv if nyelv in NYELVEK else ALAP_NYELV


def _het_eltolas(ev: int, dow: int, doy: int) -> int:
    """A moment `firstWeekOffset`-je: a nyelv hétszabálya (`dow`: a hét első napja, vasárnap 0; `doy`) szerinti első hét eltolása."""
    fwd = 7 + dow - doy
    nap = (date(ev, 1, fwd).weekday() + 1) % 7              # a január `fwd`-edikének hétköznapja, vasárnap 0
    return -((7 + nap - dow) % 7) + fwd - 1


def _evnapok(ev: int) -> int:
    return 366 if calendar.isleap(ev) else 365


def _hetek_az_evben(ev: int, dow: int, doy: int) -> int:
    return (_evnapok(ev) - _het_eltolas(ev, dow, doy) + _het_eltolas(ev + 1, dow, doy)) // 7


def het_es_ev(dt: datetime, dow: int, doy: int) -> tuple[int, int]:
    """A moment `weekOfYear`-je: (hét sorszáma, a hét éve) a nyelv hétszabálya szerint."""
    het = (dt.timetuple().tm_yday - _het_eltolas(dt.year, dow, doy) - 1) // 7 + 1
    if het < 1:
        ev = dt.year - 1
        return het + _hetek_az_evben(ev, dow, doy), ev
    if het > _hetek_az_evben(dt.year, dow, doy):
        return het - _hetek_az_evben(dt.year, dow, doy), dt.year + 1
    return het, dt.year


def _eltolas(dt: datetime) -> tuple[int, int]:
    """A `dt` UTC-eltolása (előjel, perc); a naiv időt a helyi időzónában értelmezi."""
    perc = int((dt.utcoffset() if dt.tzinfo else dt.astimezone().utcoffset()).total_seconds() // 60)
    return (-1 if perc < 0 else 1), abs(perc)


def ismeretlen_tokenek(formatum: str) -> list[str]:
    """A formátum azon moment-tokenjei, amelyeket a motor nem támogat (és ezért szó szerint adna ki): `z`, `zz`, `N…`, `y…`.
    A `[escape]` belseje nem számít. Sorrendben, ismétlés nélkül."""
    ki: list[str] = []
    for m in _TOKEN.finditer(formatum):
        if m.group(4) and m.group(4) not in ki:
            ki.append(m.group(4))
    return ki


def datum_formatum(dt: datetime, formatum: str, nyelv: str = ALAP_NYELV) -> str:
    """A `dt` a moment-formátum `formatum` szerint (a támogatott tokenek: lásd `_TOKEN`). Üres formátum: üres szöveg."""
    nyelv = nyelv_kod(nyelv)
    n = _NEVEK[nyelv]
    het = dt.weekday()                               # 0 = hétfő
    vas0 = (het + 1) % 7                             # a moment: vasárnap 0
    sorszam = n["sorszam"]

    def csere(m: re.Match) -> str:
        if m.group(1) is not None:
            return m.group(1)
        if m.group(2) is not None:
            return m.group(2)
        t = m.group(3)
        if t is None:
            return m.group(0)                        # nem támogatott token: szó szerint
        if t in n["hosszu"]:
            return datum_formatum(dt, n["hosszu"][t], nyelv)
        if t == "YYYYYY":
            return f"{'-' if dt.year < 0 else '+'}{abs(dt.year):06d}"
        if t == "YYYYY":
            return f"{dt.year:05d}"
        if t == "YYYY":
            return f"{dt.year:04d}"
        if t == "YY":
            return f"{dt.year % 100:02d}"
        if t == "Y":
            return str(dt.year)
        if t == "MMMM":
            return n["honap"][dt.month - 1]
        if t == "MMM":
            return n["honap_rovid"][dt.month - 1]
        if t == "MM":
            return f"{dt.month:02d}"
        if t == "Mo":
            return sorszam(dt.month)
        if t == "M":
            return str(dt.month)
        if t == "Qo":
            return sorszam((dt.month - 1) // 3 + 1)
        if t == "Q":
            return str((dt.month - 1) // 3 + 1)
        yday = dt.timetuple().tm_yday
        if t == "DDDD":
            return f"{yday:03d}"
        if t == "DDDo":
            return sorszam(yday)
        if t == "DDD":
            return str(yday)
        if t == "DD":
            return f"{dt.day:02d}"
        if t == "Do":
            return sorszam(dt.day)
        if t == "D":
            return str(dt.day)
        if t == "dddd":
            return n["nap"][het]
        if t == "ddd":
            return n["nap_rovid"][het]
        if t == "dd":
            return n["nap_min"][het]
        if t == "do":
            return sorszam(vas0)
        if t == "d":
            return str(vas0)
        if t == "E":
            return str(het + 1)                      # ISO: hétfő 1
        if t == "e":
            return str((vas0 - n["het_dow"]) % 7)    # a nyelv hétszabálya szerinti hétnap
        if t in ("W", "WW", "Wo"):
            iso = dt.isocalendar().week
            return f"{iso:02d}" if t == "WW" else sorszam(iso) if t == "Wo" else str(iso)
        if t in ("w", "ww", "wo"):
            hs = het_es_ev(dt, n["het_dow"], n["het_doy"])[0]
            return f"{hs:02d}" if t == "ww" else sorszam(hs) if t == "wo" else str(hs)
        if t in ("gggg", "gg"):
            ev = het_es_ev(dt, n["het_dow"], n["het_doy"])[1]
            return f"{ev:04d}" if t == "gggg" else f"{ev % 100:02d}"
        if t in ("GGGG", "GG"):
            ev = dt.isocalendar().year
            return f"{ev:04d}" if t == "GGGG" else f"{ev % 100:02d}"
        if t == "HH":
            return f"{dt.hour:02d}"
        if t == "H":
            return str(dt.hour)
        if t in ("hh", "h"):
            o = dt.hour % 12 or 12
            return f"{o:02d}" if t == "hh" else str(o)
        if t in ("kk", "k"):
            o = dt.hour or 24
            return f"{o:02d}" if t == "kk" else str(o)
        if t == "mm":
            return f"{dt.minute:02d}"
        if t == "m":
            return str(dt.minute)
        if t == "ss":
            return f"{dt.second:02d}"
        if t == "s":
            return str(dt.second)
        if t[0] == "S":
            return f"{dt.microsecond:06d}000"[:len(t)]
        if t in ("A", "a"):
            de, du = n["de_du"]
            jel = de if dt.hour < 12 else du
            return jel.upper() if t == "A" else jel
        if t in ("Z", "ZZ"):
            elojel, perc = _eltolas(dt)
            ora, p = divmod(perc, 60)
            return f"{'-' if elojel < 0 else '+'}{ora:02d}{':' if t == 'Z' else ''}{p:02d}"
        if t == "X":
            return str(int(dt.timestamp()))
        if t == "x":
            return str(int(dt.timestamp() * 1000))
        return t

    return _TOKEN.sub(csere, formatum)


@dataclass
class Eredmeny:
    szoveg: str
    kurzor: int | None            # az első `{{cursor}}` helye a kimenetben, UTF-16 egységben; None, ha nincs


def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def kiertekel(szoveg: str, cim: str, most: datetime, *, nyelv: str = ALAP_NYELV, datum: str = ALAP_DATUM,
              ido: str = ALAP_IDO, extra: dict | None = None) -> Eredmeny:
    """A sablon kiértékelése egyetlen menetben. `cim`: a jegyzet neve; `most`: a `{{date}}` és `{{time}}` ideje. `extra`: további
    változók kisbetűs névvel (`content`, `fromtitle`, `newtitle`; a Note composer kivonás-sablonja) — a behelyettesített szöveg itt
    sem értékelődik újra."""
    reszek: list[str] = []
    kurzor: int | None = None
    hossz = 0                                            # a kimenet eddigi hossza, UTF-16 egységben
    utolso = 0
    for m in _VALTOZO.finditer(szoveg):
        elo = szoveg[utolso:m.start()]
        reszek.append(elo)
        hossz += _utf16(elo)
        nev, fmt = m.group(1).lower(), m.group(2)
        if nev == "cursor":
            if fmt is not None:                          # `{{cursor:x}}` nem változó: marad
                ki = m.group(0)
            else:
                ki = ""
                if kurzor is None:
                    kurzor = hossz
        elif nev in EXTRA_VALTOZOK:
            ki = extra[nev] if fmt is None and extra and nev in extra else m.group(0)
        elif nev == "title":
            ki = m.group(0) if fmt is not None else cim
        elif nev == "date":                              # az üres formátum (`{{date:}}`) az alapformátum (Obsidian)
            ki = datum_formatum(most, fmt.strip() if fmt is not None and fmt.strip() else datum, nyelv)
        else:
            ki = datum_formatum(most, fmt.strip() if fmt is not None and fmt.strip() else ido, nyelv)
        reszek.append(ki)
        hossz += _utf16(ki)
        utolso = m.end()
    reszek.append(szoveg[utolso:])
    return Eredmeny("".join(reszek), kurzor)


def frontmatter_van(szoveg: str) -> bool:
    """Áll-e a szöveg elején frontmatter-blokk (L39)."""
    return bool(FM_RE.match(szoveg))


def torzs(szoveg: str) -> str:
    """A szöveg a frontmatter nélkül (a blokk és a mögötte álló egy üres sor lekerül)."""
    m = FM_RE.match(szoveg)
    return szoveg[m.end():] if m else szoveg


def tartalmi_nyelv(cfg) -> str:
    """A hónap- és napnevek nyelve: a kifejezett `[sablon] nyelv` (`hu`/`en`), különben a munkatér tartalmi nyelve
    (`[workspace] nyelv`), különben angol. Az „Automatic” beállítás üres értéket ír mindkettőbe: nincs nyelvi tipp → angol.
    (Szándékosan nem a felület nyelve: az útvonal-formátumban álló `MMMM` nem változhat attól, hogy a felhasználó átvált.)"""
    for forras in (cfg.section("sablon").get("nyelv"), cfg.section("workspace").get("nyelv")):
        if forras in NYELVEK:
            return forras
    return ALAP_NYELV


def beallitasok(cfg) -> dict:
    """A `[sablon]` szakasz értékei alapértékekkel; a `nyelv` a feloldott tartalmi nyelv (`hu` | `en`)."""
    s = cfg.section("sablon")
    return {"mappa": s.get("mappa", ALAP_MAPPA).strip("/") or ALAP_MAPPA, "datum": s.get("datum") or ALAP_DATUM,
            "ido": s.get("ido") or ALAP_IDO, "nyelv": tartalmi_nyelv(cfg)}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def lista(vault) -> dict:
    """A sablonmappa `.md` fájljai (rekurzívan, rejtett nélkül), név szerint: `{mappa, sablonok: [{ut, nev}]}`."""
    mappa = beallitasok(vault.cfg)["mappa"]
    gyoker = vault._abs(mappa)
    sablonok = []
    if gyoker.is_dir():
        for sor, almappak, fajlok in os.walk(gyoker):
            rejtett.metsz_munkater(almappak)
            almappak[:] = [d for d in almappak if not d.startswith(".")]
            for f in fajlok:
                if f.startswith(".") or not f.lower().endswith(".md"):
                    continue
                rp = _nfc(os.path.relpath(os.path.join(sor, f), vault.root)).replace(os.sep, "/")
                sablonok.append({"ut": rp, "nev": _nfc(f[:-3])})
    sablonok.sort(key=lambda s: (s["nev"].lower(), s["ut"]))
    return {"mappa": mappa, "sablonok": sablonok}


def olvas(vault, ut) -> str:
    """Egy sablon szövege; csak a sablonmappa alatti `.md`."""
    from .vaultio import Invalid, NotFound, norm_path
    rp = norm_path(ut)
    mappa = beallitasok(vault.cfg)["mappa"]
    if not rp.lower().endswith(".md") or not (rp == mappa or rp.startswith(mappa + "/")):
        raise kodos(Invalid(f"nem sablon (a sablonmappa: {mappa}): {rp}"), "sablon.nem_sablon", mappa=mappa, ut=rp)
    try:
        return vault.read(rp)["tartalom"]
    except NotFound:
        raise kodos(NotFound(f"nincs ilyen sablon: {rp}"), "sablon.nincs", ut=rp) from None


def kiertekel_vault(vault, ut, cim, most: datetime | None = None) -> dict:
    """A `POST /api/sablon/kiertekel` törzse: `{szoveg, kurzor, frontmatter}`."""
    if not isinstance(cim, str):
        raise SablonHiba(400, "hiányzik a jegyzet címe (`cim`)")
    b = beallitasok(vault.cfg)
    e = kiertekel(olvas(vault, ut), cim, most or datetime.now().astimezone(), nyelv=b["nyelv"],
                  datum=b["datum"], ido=b["ido"])
    return {"szoveg": e.szoveg, "kurzor": e.kurzor, "frontmatter": frontmatter_van(e.szoveg)}


def most_szoveg(vault, fajta, formatum=None, most: datetime | None = None) -> dict:
    """A `POST /api/sablon/most` törzse: a mostani dátum vagy idő a sablon formátumával — a „Insert current date / time”
    parancsok és a Beállítások előnézete. `fajta`: `date` | `time`; `formatum`: kifejezett formátum (előnézet), különben a
    beállított (`[sablon] datum` / `ido`; üres = alap). → `{szoveg, formatum, ismeretlen}`; az `ismeretlen` a nem támogatott
    moment-tokenek listája (azok szó szerint kerülnek ki)."""
    if fajta not in ("date", "time"):
        raise SablonHiba(400, "a `fajta` date vagy time lehet", kod="sablon.most_fajta")
    if formatum is not None and (not isinstance(formatum, str) or len(formatum) > 200):
        raise SablonHiba(400, "a `formatum` legfeljebb 200 karakteres szöveg", kod="sablon.most_formatum")
    b = beallitasok(vault.cfg)
    fmt = formatum.strip() if formatum and formatum.strip() else b["datum" if fajta == "date" else "ido"]
    dt = most or datetime.now().astimezone()
    return {"szoveg": datum_formatum(dt, fmt, b["nyelv"]), "formatum": fmt, "ismeretlen": ismeretlen_tokenek(fmt)}


def uj_jegyzet(vault, ut, mappa, nev, most: datetime | None = None, tulajdonsagok=None, megerosit: bool = False) -> dict:
    """A `POST /api/sablon/uj` törzse (C32b): új jegyzet a sablonból egy meglévő mappában. A `{{title}}` az **új jegyzet** neve;
    a kiértékelés ugyanaz a motor, mint a beszúrásnál (`kiertekel`), a létrehozás a `Vault.create` egyetlen útja (kör-zár,
    atomi írás, egy gépi commit, névütközés-védelem). Válasz: `{ut, kurzor, figyelmeztetes}` (a `kurzor` UTF-16 egységben).

    **Séma (Javító 7; 64(b), 22(b)).** Ha a kiértékelt sablonnak van frontmatterje, a `tulajdonsagok` (a core `Tulajdonsagok`
    példánya) ellenőrzi az új jegyzet útjára: a hiba szintű (formai hibás frontmatter, ismétlődő kulcs, a típushoz nem illő érték)
    megerősítéssel sem írható (400, `megerositheto: false`); a séma-sértő (ismeretlen kulcs, köztük az `icon`/`cover`;
    értékkészleten kívüli címke vagy Status; kulcssorrend) **409**-et ad (`sema_sertes: true`, `megerositheto: true`, `problemak`),
    és a jegyzet nem jön létre; a `megerosit: true` kéréssel íródik a váz szó szerint. Frontmatter nélküli sablonnál, illetve
    `tulajdonsagok` nélkül nincs ellenőrzés."""
    if not isinstance(nev, str) or not nev.strip():
        raise SablonHiba(400, "hiányzik az új jegyzet neve (`nev`)")
    if mappa is not None and not isinstance(mappa, str):
        raise SablonHiba(400, "a `mappa` szöveg lehet")
    szoveg = olvas(vault, ut)
    nev = _nfc(nev).strip()
    if nev.lower().endswith(".md"):
        nev = nev[:-3].rstrip()
    b = beallitasok(vault.cfg)
    e = kiertekel(szoveg, nev, most or datetime.now().astimezone(), nyelv=b["nyelv"], datum=b["datum"], ido=b["ido"])
    if tulajdonsagok is not None and frontmatter_van(e.szoveg):
        from .vaultio import norm_path
        kan = vault.kanonikus(norm_path(mappa)) if mappa else ""
        cel = f"{kan}/{nev}.md" if kan else f"{nev}.md"
        ell = tulajdonsagok.uj_jegyzet_ellenorzes(cel, e.szoveg)
        if ell["hibak"]:
            raise SablonHiba(400, "a sablon frontmatterje hibás (megerősítéssel sem írható), a jegyzet nem jön létre",
                             sema_sertes=True, megerositheto=False, problemak=ell["hibak"] + ell["sertesek"])
        if ell["sertesek"] and not megerosit:
            raise SablonHiba(409, "a sablon frontmatterje sérti a vault sémáját; megerősítéssel hozható létre",
                             sema_sertes=True, megerositheto=True, problemak=ell["sertesek"])
    d = vault.create({"mappa": mappa or "", "nev": nev, "tartalom": e.szoveg})
    return {"ut": d["ut"], "kurzor": e.kurzor, "figyelmeztetes": d.get("figyelmeztetes")}


def utvonalak(r) -> None:
    r.get("/api/sablon/lista", lambda k: lista(k.app.vault))
    r.post("/api/sablon/kiertekel", lambda k: kiertekel_vault(k.app.vault, k.torzs().get("ut"), k.torzs().get("cim")))
    r.post("/api/sablon/most", lambda k: most_szoveg(k.app.vault, k.torzs().get("fajta"), k.torzs().get("formatum")))

    def uj(k):
        t = k.torzs()
        megerosit = t.get("megerosit")
        if megerosit is not None and not isinstance(megerosit, bool):         # T128: a `"false"` szöveg nem megerősítés
            raise SablonHiba(400, "a `megerosit` igaz vagy hamis lehet")
        return uj_jegyzet(k.app.vault, t.get("sablon"), t.get("mappa"), t.get("nev"),
                          tulajdonsagok=k.app.tulajdonsagok, megerosit=megerosit is True)

    r.post("/api/sablon/uj", uj)
