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

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from . import rejtett
from .index.maszk import FM_RE
from .utvonalak import HttpError, kodos

ALAP_DATUM = "YYYY-MM-DD"
ALAP_IDO = "HH:mm"
ALAP_MAPPA = "_Template"
ALAP_NYELV = "hu"

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
    },
}

# hosszabb token előbb; a `[...]` escape az első alternatíva
_TOKEN = re.compile(r"\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|DDDD|DDD|DD|Do|D|dddd|ddd|dd|d|E|HH|H|hh|h|mm|m|ss|s|A|a|WW|W")
# A változónév kis-nagybetűtől független (az Obsidian Templates magja: `/{{(date|time)(?::(.*?))?}}/gi` és
# `new RegExp("{{title}}", "gi")`; statikus olvasás, 1.14.4 — C31, T156).
_VALTOZO = re.compile(r"\{\{\s*(date|time|title|cursor)\s*(?::([^{}]*?))?\s*\}\}", re.IGNORECASE)


class SablonHiba(HttpError):
    """Hibás sablonkérés (400/404)."""


def datum_formatum(dt: datetime, formatum: str, nyelv: str = ALAP_NYELV) -> str:
    """A `dt` a moment-részhalmaz `formatum` szerint. Üres formátum: üres szöveg."""
    n = _NEVEK.get(nyelv) or _NEVEK[ALAP_NYELV]
    het = dt.weekday()                               # 0 = hétfő

    def csere(m: re.Match) -> str:
        t = m.group(0)
        if m.group(1) is not None:
            return m.group(1)
        if t == "YYYY":
            return f"{dt.year:04d}"
        if t == "YY":
            return f"{dt.year % 100:02d}"
        if t == "MMMM":
            return n["honap"][dt.month - 1]
        if t == "MMM":
            return n["honap_rovid"][dt.month - 1]
        if t == "MM":
            return f"{dt.month:02d}"
        if t == "M":
            return str(dt.month)
        yday = dt.timetuple().tm_yday
        if t == "DDDD":
            return f"{yday:03d}"
        if t == "DDD":
            return str(yday)
        if t == "DD":
            return f"{dt.day:02d}"
        if t == "Do":
            return n["sorszam"](dt.day)
        if t == "D":
            return str(dt.day)
        if t == "dddd":
            return n["nap"][het]
        if t == "ddd":
            return n["nap_rovid"][het]
        if t == "dd":
            return n["nap_min"][het]
        if t == "d":
            return str((het + 1) % 7)                # a moment: vasárnap 0
        if t == "E":
            return str(het + 1)                      # ISO: hétfő 1
        if t == "HH":
            return f"{dt.hour:02d}"
        if t == "H":
            return str(dt.hour)
        if t in ("hh", "h"):
            o = dt.hour % 12 or 12
            return f"{o:02d}" if t == "hh" else str(o)
        if t == "mm":
            return f"{dt.minute:02d}"
        if t == "m":
            return str(dt.minute)
        if t == "ss":
            return f"{dt.second:02d}"
        if t == "s":
            return str(dt.second)
        if t in ("A", "a"):
            de, du = n["de_du"]
            jel = de if dt.hour < 12 else du
            return jel.upper() if t == "A" else jel
        if t == "WW":
            return f"{dt.isocalendar().week:02d}"
        if t == "W":
            return str(dt.isocalendar().week)
        return t

    return _TOKEN.sub(csere, formatum)


@dataclass
class Eredmeny:
    szoveg: str
    kurzor: int | None            # az első `{{cursor}}` helye a kimenetben, UTF-16 egységben; None, ha nincs


def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def kiertekel(szoveg: str, cim: str, most: datetime, *, nyelv: str = ALAP_NYELV, datum: str = ALAP_DATUM,
              ido: str = ALAP_IDO) -> Eredmeny:
    """A sablon kiértékelése egyetlen menetben. `cim`: a jegyzet neve; `most`: a `{{date}}` és `{{time}}` ideje."""
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


def beallitasok(cfg) -> dict:
    """A `[sablon]` szakasz értékei alapértékekkel."""
    s = cfg.section("sablon")
    return {"mappa": s.get("mappa", ALAP_MAPPA).strip("/") or ALAP_MAPPA, "datum": s.get("datum", ALAP_DATUM),
            "ido": s.get("ido", ALAP_IDO), "nyelv": s.get("nyelv", ALAP_NYELV)}


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

    def uj(k):
        t = k.torzs()
        megerosit = t.get("megerosit")
        if megerosit is not None and not isinstance(megerosit, bool):         # T128: a `"false"` szöveg nem megerősítés
            raise SablonHiba(400, "a `megerosit` igaz vagy hamis lehet")
        return uj_jegyzet(k.app.vault, t.get("sablon"), t.get("mappa"), t.get("nev"),
                          tulajdonsagok=k.app.tulajdonsagok, megerosit=megerosit is True)

    r.post("/api/sablon/uj", uj)
