"""A Bases függvényei és mezői (C12): **a `Functions.md` teljes listája**.

- `GLOBALIS`: `nev → f(kor, *args)`; az `if` lusta, a kiértékelő kezeli.
- `METODUSOK[típus][név] → f(kor, obj, *args)`; a `típus` az `ertekek.tipus_kulcs` neve vagy `any`.
- `LUSTA_METODUSOK[típus][név] → f(kor, obj, argok)`: az `argok` kiértékelő-zárványok (`filter`, `map`, `reduce`),
  amelyeket a metódus a saját `value` / `index` / `acc` környezetében hív.
- `mezo(kor, obj, nev)`: a `.nev` mezőelérés (`date.year`, `list.length`, `file.name` …).

A `kor` a kiértékelési környezet (`kiertekelo.Kor`): a `most`, a `tabla`, az aktuális `sor`. A JavaScript-viselkedést
követjük (a dokumentáció szerint); ahol a dokumentáció hallgat, a választott viselkedést a tesztek rögzítik.
"""
from __future__ import annotations

import html as _html
import math
import random
import re

from .ertekek import (
    Cimke, Datum, FutasHiba, Fajl, Html, Ikon, Idotartam, Kep, Link, Regex, datum_formaz, datum_ms, datum_mezo,
    datum_relativ, datum_szovegbol, egyenlo, fixre, hasonlit, idotartam, igaz_e, kerekit, kulcs, link_szovegbol,
    rendezo_kulcs, szam, szam_szoveg, szovegge, tipus_kulcs, tipus_neve, _szam_e,
)

GLOBALIS: dict = {}
METODUSOK: dict[str, dict] = {}
LUSTA_METODUSOK: dict[str, dict] = {}
ALAIRAS: dict[tuple, tuple] = {}         # (típus | "global", név) → (legkevesebb, legtöbb argumentum; `None` = nincs korlát / nem ellenőrzött)
LUSTA_NEVEK = ("filter", "map", "reduce")
_KULSO_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|mailto:)", re.I)
_SZIN_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_SZAM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


# ================================================================ regisztráció

def _db_ellenor(nev: str, args, kell: int, max_: int | None) -> None:
    n = len(args)
    if n < kell or (max_ is not None and n > max_):
        if max_ == kell:
            var = f"{kell}"
        elif max_ is None:
            var = f"at least {kell}"
        else:
            var = f"{kell}–{max_}"
        raise FutasHiba("bazis.futas.argumentum_db", {"nev": nev, "var": var, "n": n})


def glob(nev: str, kell: int = 0, max_: int | None = -1):
    max_ = kell if max_ == -1 else max_

    def dek(f):
        def hiv(kor, *args):
            _db_ellenor(nev, args, kell, max_)
            return f(kor, *args)
        GLOBALIS[nev] = hiv
        ALAIRAS[("global", nev)] = (kell, max_)
        return f
    return dek


def met(tipus: str, nev: str, kell: int = 0, max_: int | None = -1):
    max_ = kell if max_ == -1 else max_

    def dek(f):
        def hiv(kor, obj, *args):
            _db_ellenor(nev, args, kell, max_)
            return f(kor, obj, *args)
        METODUSOK.setdefault(tipus, {})[nev] = hiv
        ALAIRAS[(tipus, nev)] = (kell, max_)
        return f
    return dek


def lusta(tipus: str, nev: str):
    def dek(f):
        LUSTA_METODUSOK.setdefault(tipus, {})[nev] = f
        ALAIRAS.setdefault((tipus, nev), (None, None))        # a lusta metódus argumentumszáma nem ellenőrzött
        return f
    return dek


def _szoveg_arg(x, nev: str) -> str:
    if isinstance(x, str):
        return x
    if x is None or isinstance(x, (list, dict)):
        raise FutasHiba("bazis.futas.szoveg_kell", {"nev": nev, "tipus": tipus_neve(x)})
    return szovegge(x)


def _egesz(x, nev: str, alap=None):
    if x is None:
        return alap
    if not _szam_e(x) or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        raise FutasHiba("bazis.futas.szam_kell", {"nev": nev, "tipus": tipus_neve(x)})
    return int(x)


# ================================================================ globális függvények

@glob("escapeHTML", 1)
def _escape_html(kor, s):
    return _html.escape(_szoveg_arg(s, "escapeHTML"))


@glob("date", 1)
def _date(kor, s):
    if isinstance(s, Datum):
        return s
    if not isinstance(s, str):
        raise FutasHiba("bazis.futas.szoveg_kell", {"nev": "date", "tipus": tipus_neve(s)})
    d = datum_szovegbol(s)
    if d is None:
        raise FutasHiba("bazis.futas.datum_hibas", {"ertek": repr(s)})
    return d


@glob("duration", 1)
def _duration(kor, s):
    if isinstance(s, Idotartam):
        return s
    i = idotartam(s) if isinstance(s, str) else None
    if i is None:
        raise FutasHiba("bazis.futas.idotartam_hibas", {"ertek": repr(szovegge(s))})
    return i


def _link_keszit(kor, cel, kijelzes=None) -> Link:
    if isinstance(cel, Fajl):
        return Link(cel.sor.ut, kijelzes, cel.sor.ut)
    if isinstance(cel, Link):
        return Link(cel.cel, kijelzes if kijelzes is not None else cel.megjelenites, cel.ut, cel.alcel, cel.kulso)
    if not isinstance(cel, str):
        raise FutasHiba("bazis.futas.link_cel", {"tipus": tipus_neve(cel)})
    s = cel.strip()
    if _KULSO_RE.match(s):
        return Link(s, kijelzes, None, None, True)
    forras = kor.sor.ut if kor.sor is not None else ""
    kerett = link_szovegbol(s, lambda c: kor.tabla.felold(c, forras) if kor.tabla else None)
    if kerett is not None:
        return Link(kerett.cel, kijelzes if kijelzes is not None else kerett.megjelenites, kerett.ut, kerett.alcel)
    alap, _, alcel = s.partition("#")
    alap, _, alias = alap.partition("|") if "|" in alap else (alap, "", None)
    ut = kor.tabla.felold(alap.strip(), forras) if kor.tabla else None
    return Link(alap.strip(), kijelzes if kijelzes is not None else (alias.strip() if alias else None), ut,
                alcel.strip() or None)


@glob("link", 1, 2)
def _link(kor, cel, kijelzes=None):
    return _link_keszit(kor, cel, kijelzes)


@glob("file", 1)
def _file(kor, x):
    if isinstance(x, Fajl):
        return x
    if isinstance(x, Link):
        return kor.tabla.fajl(x.ut) if kor.tabla else None
    if isinstance(x, str):
        if kor.tabla is None:
            return None
        f = kor.tabla.fajl(x.strip().lstrip("/"))
        return f if f is not None else kor.tabla.fajl(_link_keszit(kor, x).ut)
    raise FutasHiba("bazis.futas.file_cel", {"tipus": tipus_neve(x)})


@glob("html", 1)
def _html_fn(kor, s):
    return Html(_szoveg_arg(s, "html"))


@glob("image", 1)
def _image(kor, x):
    if x is None:
        return None
    if isinstance(x, Kep):
        return x
    if isinstance(x, Fajl):
        return Kep(ut=x.sor.ut)
    if isinstance(x, Link):
        return Kep(url=x.cel) if x.kulso else Kep(ut=x.ut) if x.ut else None
    if isinstance(x, str):
        s = x.strip()
        if _SZIN_RE.match(s):
            return Kep(szin=s)
        l = _link_keszit(kor, s)
        return Kep(url=l.cel) if l.kulso else Kep(ut=l.ut) if l.ut else None
    raise FutasHiba("bazis.futas.image_cel", {"tipus": tipus_neve(x)})


@glob("icon", 1)
def _icon(kor, nev):
    return Ikon(_szoveg_arg(nev, "icon"))


@glob("list", 1)
def _list(kor, x):
    if isinstance(x, list):
        return x
    return [] if x is None else [x]                 # az üres érték üres lista: így a `list(NN).map(…)` nem hibás


def _szamok(args, nev):
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    ki = []
    for a in args:
        if a is None:
            continue
        if not _szam_e(a):
            raise FutasHiba("bazis.futas.szam_kell", {"nev": nev, "tipus": tipus_neve(a)})
        ki.append(a)
    return ki


@glob("max", 1, None)
def _max(kor, *args):
    s = _szamok(args, "max")
    return max(s) if s else None


@glob("min", 1, None)
def _min(kor, *args):
    s = _szamok(args, "min")
    return min(s) if s else None


@glob("now", 0)
def _now(kor):
    return kor.most


@glob("today", 0)
def _today(kor):
    return Datum(kor.most.ertek.replace(hour=0, minute=0, second=0, microsecond=0), False)


@glob("number", 1)
def _number(kor, x):
    if x is None:
        return None
    if _szam_e(x):
        return x
    if isinstance(x, bool):
        return 1 if x else 0
    if isinstance(x, Datum):
        return datum_ms(x)
    if isinstance(x, str) and _SZAM_RE.match(x.strip()):
        return szam(float(x.strip()))
    raise FutasHiba("bazis.futas.number_alakitas", {"ertek": repr(szovegge(x))})


@glob("random", 0)
def _random(kor):
    return random.random()


# ================================================================ bármely típus

@met("any", "isTruthy")
def _is_truthy(kor, x):
    return igaz_e(x)


@met("any", "isType", 1)
def _is_type(kor, x, tipus):
    return tipus_kulcs(x) == tipus or (tipus == "empty" and x is None)


@met("any", "toString")
def _to_string(kor, x):
    return szovegge(x)


# ================================================================ dátum

@met("date", "date")
def _datum_datum(kor, d):
    return Datum(d.ertek.replace(hour=0, minute=0, second=0, microsecond=0), False)


@met("date", "format", 1)
def _datum_format(kor, d, minta):
    return datum_formaz(d, _szoveg_arg(minta, "format"))


@met("date", "time")
def _datum_time(kor, d):
    return datum_formaz(d, "HH:mm:ss")


@met("date", "relative")
def _datum_relative(kor, d):
    return datum_relativ(d, kor.most)


@met("date", "isEmpty")
def _datum_ures(kor, d):
    return False


# ================================================================ szöveg

def _szoveg_args(nev: str, vals):
    return [_szoveg_arg(v, nev) for v in vals]


@met("string", "contains", 1)
def _sz_contains(kor, s, v):
    return False if v is None else _szoveg_arg(v, "contains") in s


@met("string", "containsAll", 1, None)
def _sz_contains_all(kor, s, *v):
    return all(x in s for x in _szoveg_args("containsAll", v))


@met("string", "containsAny", 1, None)
def _sz_contains_any(kor, s, *v):
    return any(x in s for x in _szoveg_args("containsAny", v))


@met("string", "endsWith", 1)
def _sz_ends_with(kor, s, v):
    return s.endswith(_szoveg_arg(v, "endsWith"))


@met("string", "startsWith", 1)
def _sz_starts_with(kor, s, v):
    return s.startswith(_szoveg_arg(v, "startsWith"))


@met("string", "isEmpty")
def _sz_ures(kor, s):
    return s == ""


@met("string", "lower")
def _sz_lower(kor, s):
    return s.lower()


_SZO_RE = re.compile(r"(\w)(\w*)")


@met("string", "title")
def _sz_title(kor, s):
    return _SZO_RE.sub(lambda m: m.group(1).upper() + m.group(2).lower(), s)


@met("string", "trim")
def _sz_trim(kor, s):
    return s.strip()


@met("string", "repeat", 1)
def _sz_repeat(kor, s, n):
    n = _egesz(n, "repeat")
    if n < 0 or len(s) * n > 1_000_000:
        raise FutasHiba("bazis.futas.repeat_szam")
    if kor.keret is not None:
        kor.keret.fogyaszt(len(s) * n)                  # T041: a hívásonkénti 1 MB mellett lekérdezésenkénti összkeret
    return s * n


@met("string", "reverse")
def _sz_reverse(kor, s):
    return s[::-1]


def _szelet(x, kezd, veg, nev):
    return x[_egesz(kezd, nev, 0):_egesz(veg, nev, None)]


@met("string", "slice", 1, 2)
def _sz_slice(kor, s, kezd, veg=None):
    return _szelet(s, kezd, veg, "slice")


def _csere_kif(csere: str):
    """A JavaScript-csere (`$1`, `$&`, `$$`) függvénye egy találathoz."""
    def f(m):
        def r(x):
            t = x.group(1)
            if t == "$":
                return "$"
            if t == "&":
                return m.group(0)
            i = int(t)
            return (m.group(i) or "") if 0 < i <= (m.re.groups or 0) else x.group(0)
        return re.sub(r"\$(\$|&|\d{1,2})", r, csere)
    return f


@met("string", "replace", 2)
def _sz_replace(kor, s, minta, csere):
    csere = _szoveg_arg(csere, "replace")
    if isinstance(minta, Regex):
        try:
            return minta.rx.sub(_csere_kif(csere), s, count=0 if minta.globalis else 1, concurrent=True,
                                timeout=Regex.IDOKORLAT_MP)
        except TimeoutError:
            raise FutasHiba("bazis.futas.regex_lassu") from None
    return s.replace(_szoveg_arg(minta, "replace"), csere)


@met("string", "split", 1, 2)
def _sz_split(kor, s, sep, n=None):
    n = _egesz(n, "split")
    if isinstance(sep, Regex):
        try:
            r = sep.rx.split(s, concurrent=True, timeout=Regex.IDOKORLAT_MP)
        except TimeoutError:
            raise FutasHiba("bazis.futas.regex_lassu") from None
    else:
        sep = _szoveg_arg(sep, "split")
        r = list(s) if sep == "" else s.split(sep)
    return r if n is None else r[:max(n, 0)]


# ================================================================ szám

@met("number", "abs")
def _sz_abs(kor, x):
    return abs(x)


@met("number", "ceil")
def _sz_ceil(kor, x):
    return x if isinstance(x, float) and (math.isnan(x) or math.isinf(x)) else szam(math.ceil(x))


@met("number", "floor")
def _sz_floor(kor, x):
    return x if isinstance(x, float) and (math.isnan(x) or math.isinf(x)) else szam(math.floor(x))


@met("number", "isEmpty")
def _szam_ures(kor, x):
    return False


@met("number", "round", 0, 1)
def _sz_round(kor, x, jegyek=0):
    return kerekit(x, _egesz(jegyek, "round", 0))


@met("number", "toFixed", 1)
def _sz_to_fixed(kor, x, pontossag):
    p = _egesz(pontossag, "toFixed")
    if not 0 <= p <= 100:
        raise FutasHiba("bazis.futas.tofixed_pontossag")
    return fixre(x, p)


# ================================================================ lista

@met("list", "contains", 1)
def _l_contains(kor, l, v):
    return any(egyenlo(e, v) for e in l)


@met("list", "containsAll", 1, None)
def _l_contains_all(kor, l, *v):
    return all(any(egyenlo(e, x) for e in l) for x in v)


@met("list", "containsAny", 1, None)
def _l_contains_any(kor, l, *v):
    return any(any(egyenlo(e, x) for e in l) for x in v)


@met("list", "flat")
def _l_flat(kor, l):
    ki = []
    for e in l:
        ki.extend(e) if isinstance(e, list) else ki.append(e)
    return ki


@met("list", "isEmpty")
def _l_ures(kor, l):
    return len(l) == 0


@met("list", "join", 0, 1)
def _l_join(kor, l, sep=","):
    return _szoveg_arg(sep, "join").join(szovegge(e) for e in l)


@met("list", "reverse")
def _l_reverse(kor, l):
    return l[::-1]


@met("list", "slice", 1, 2)
def _l_slice(kor, l, kezd, veg=None):
    return _szelet(l, kezd, veg, "slice")


@met("list", "sort")
def _l_sort(kor, l):
    return sorted(l, key=rendezo_kulcs)


@met("list", "unique")
def _l_unique(kor, l):
    lattuk, ki = set(), []
    for e in l:
        k = kulcs(e)
        if k not in lattuk:
            lattuk.add(k)
            ki.append(e)
    return ki


# A `Functions.md` nem sorolja fel, de a `Bases syntax` összesítő-példája használja (`values.mean().round(3)`): a
# lista számtani metódusai. A nem szám elemek (üres, szöveg) kimaradnak; üres bemenetre az eredmény üres.
def _szamok_listabol(l: list) -> list:
    return [x for x in l if _szam_e(x) and not (isinstance(x, float) and math.isnan(x))]


@met("list", "sum")
def _l_sum(kor, l):
    return szam(math.fsum(_szamok_listabol(l))) if _szamok_listabol(l) else 0


@met("list", "mean")
def _l_mean(kor, l):
    s = _szamok_listabol(l)
    return szam(math.fsum(s) / len(s)) if s else None


@met("list", "median")
def _l_median(kor, l):
    s = sorted(_szamok_listabol(l))
    if not s:
        return None
    k = len(s) // 2
    return s[k] if len(s) % 2 else szam((s[k - 1] + s[k]) / 2)


@met("list", "stddev")
def _l_stddev(kor, l):
    s = _szamok_listabol(l)
    if not s:
        return None
    m = math.fsum(s) / len(s)
    return szam(math.sqrt(math.fsum((x - m) ** 2 for x in s) / len(s)))


def _legkisebb_legnagyobb(l: list, kisebb: bool):
    s = [x for x in l if _szam_e(x) and not (isinstance(x, float) and math.isnan(x)) or isinstance(x, Datum)]
    if not s:
        return None
    return min(s, key=rendezo_kulcs) if kisebb else max(s, key=rendezo_kulcs)


@met("list", "min")
def _l_min(kor, l):
    return _legkisebb_legnagyobb(l, True)


@met("list", "max")
def _l_max(kor, l):
    return _legkisebb_legnagyobb(l, False)


@lusta("list", "filter")
def _l_filter(kor, l, argok):
    _db_ellenor("filter", argok, 1, 1)
    f = argok[0]
    return [e for i, e in enumerate(l) if igaz_e(f(kor.alkor(value=e, index=i)))]


@lusta("list", "map")
def _l_map(kor, l, argok):
    _db_ellenor("map", argok, 1, 1)
    f = argok[0]
    return [f(kor.alkor(value=e, index=i)) for i, e in enumerate(l)]


@lusta("list", "reduce")
def _l_reduce(kor, l, argok):
    _db_ellenor("reduce", argok, 1, 2)
    f = argok[0]
    acc = argok[1](kor) if len(argok) == 2 else None
    for i, e in enumerate(l):
        acc = f(kor.alkor(value=e, index=i, acc=acc))
    return acc


# ================================================================ link, fájl, objektum, regex

@met("link", "asFile")
def _link_as_file(kor, l):
    return kor.tabla.fajl(l.ut) if kor.tabla is not None and l.ut else None


@met("link", "linksTo", 1)
def _link_links_to(kor, l, cel):
    f = kor.tabla.fajl(l.ut) if kor.tabla is not None and l.ut else None
    return f is not None and _van_link(kor, f.sor, cel)


def _cel_ut(kor, cel, forras_ut: str):
    """(feloldott út | None, szöveg | None) egy `hasLink`/`linksTo` argumentumból."""
    if isinstance(cel, Fajl):
        return cel.sor.ut, None
    if isinstance(cel, Link):
        return cel.ut, cel.cel
    if isinstance(cel, str):
        l = _link_keszit(kor, cel)
        ut = l.ut
        if ut is None and kor.tabla is not None and cel.strip().lstrip("/") in kor.tabla.ut_szerint:
            ut = cel.strip().lstrip("/")
        return ut, l.cel
    raise FutasHiba("bazis.futas.fajl_cel", {"tipus": tipus_neve(cel)})


def _van_link(kor, sor, cel) -> bool:
    ut, szoveg = _cel_ut(kor, cel, sor.ut)
    if ut is not None:
        return any(L.get("cel") == ut for L in sor.linkek)
    if not szoveg:
        return False
    k = szoveg.casefold()
    return any(L.get("cel") is None and L["cel_nyers"].strip().casefold() == k for L in sor.linkek)


@met("file", "asLink", 0, 1)
def _file_as_link(kor, f, kijelzes=None):
    return Link(f.sor.ut, kijelzes, f.sor.ut)


@met("file", "hasLink", 1)
def _file_has_link(kor, f, cel):
    return _van_link(kor, f.sor, cel)


@met("file", "hasProperty", 1)
def _file_has_property(kor, f, nev):
    return f.sor.van_tulajdonsag(f.tabla, _szoveg_arg(nev, "hasProperty"))


def _cimke_egyezik(cimke: str, ertek: str) -> bool:
    c, v = cimke.lstrip("#").casefold(), ertek.lstrip("#").casefold()
    return c == v or c.startswith(v + "/")


@met("file", "hasTag", 1, None)
def _file_has_tag(kor, f, *ertekek):
    ertekek = [_szoveg_arg(e, "hasTag") for e in ertekek]
    return any(_cimke_egyezik(c.szoveg, e) for c in f.sor.cimke_lista() for e in ertekek)


@met("file", "inFolder", 1)
def _file_in_folder(kor, f, mappa):
    m = _szoveg_arg(mappa, "inFolder").strip().strip("/")
    return m == "" or f.sor.mappa == m or f.sor.mappa.startswith(m + "/")


@met("object", "isEmpty")
def _o_ures(kor, o):
    return len(_dict(o)) == 0


@met("object", "keys")
def _o_keys(kor, o):
    return list(_dict(o).keys())


@met("object", "values")
def _o_values(kor, o):
    return list(_dict(o).values())


def _dict(o) -> dict:
    return o.mint_dict() if hasattr(o, "mint_dict") else o


@met("regexp", "matches", 1)
def _rx_matches(kor, rx, s):
    return rx.keres(_szoveg_arg(s, "matches")) is not None


# ================================================================ kiosztás

def metodus_nevek() -> set:
    """Minden ismert metódusnév (a fordító ezzel ellenőrzi az ismeretlen metódust)."""
    return {n for t in (METODUSOK, LUSTA_METODUSOK) for d in t.values() for n in d}


def fuggveny_lista() -> list[dict]:
    """A szerkesztő-segítség függvénylistája (10-bases-10): minden globális függvény és metódus az argumentumszámával,
    név és típus szerint rendezve. `tipus`: `global` vagy a metódus tulajdonosa (`string`, `list`, `date`, `file`…);
    `min`/`max`: az argumentumok száma (`max: null` = nincs felső korlát; mindkettő `null` = nem ellenőrzött)."""
    return [{"nev": nev, "tipus": tipus, "min": kell, "max": max_}
            for (tipus, nev), (kell, max_) in sorted(ALAIRAS.items(), key=lambda kv: (kv[0][1].casefold(), kv[0][0]))]


def keres_metodus(obj, nev: str):
    """(függvény, lusta?, átalakított objektum) vagy `None`."""
    if isinstance(obj, Cimke) and nev not in METODUSOK.get("tag", {}):
        obj, k = obj.szoveg, "string"
    elif hasattr(obj, "mint_dict"):
        k = "object"
    else:
        k = tipus_kulcs(obj)
    for t in (k, "any"):
        if nev in LUSTA_METODUSOK.get(t, {}):
            return LUSTA_METODUSOK[t][nev], True, obj
        if nev in METODUSOK.get(t, {}):
            return METODUSOK[t][nev], False, obj
    return None


_NULL_METODUS = {"isEmpty": True, "isTruthy": False, "toString": ""}


def hivas_metodus(kor, obj, nev: str, args: list):
    if obj is None:
        if nev in _NULL_METODUS:
            return _NULL_METODUS[nev]
        if nev == "isType":
            _db_ellenor("isType", args, 1, 1)
            return args[0] in ("null", "empty")
        raise FutasHiba("bazis.futas.ures_hivas", {"nev": nev})
    r = keres_metodus(obj, nev)
    if r is None or r[1]:
        raise FutasHiba("bazis.futas.nincs_metodus", {"tipus": tipus_neve(obj), "nev": nev})
    return r[0](kor, r[2], *args)


def hivas_lusta(kor, obj, nev: str, argok: list):
    if obj is None:
        raise FutasHiba("bazis.futas.ures_hivas", {"nev": nev})
    r = keres_metodus(obj, nev)
    if r is None or not r[1]:
        raise FutasHiba("bazis.futas.nincs_metodus", {"tipus": tipus_neve(obj), "nev": nev})
    return r[0](kor, r[2], argok)


# ================================================================ mezők

def _dict_get(d: dict, nev: str):
    if nev in d:
        return d[nev]
    k = nev.casefold()
    for a, v in d.items():
        if a.casefold() == k:
            return v
    return None


def fajl_mezo(kor, f: Fajl, nev: str):
    s = f.sor
    if nev == "name":
        return s.nev
    if nev == "basename":
        return s.nev.rsplit(".", 1)[0] if "." in s.nev else s.nev
    if nev == "path":
        return s.ut
    if nev == "folder":
        return s.mappa
    if nev == "ext":
        return s.kit
    if nev == "size":
        return s.meret
    if nev == "file":
        return f
    if nev == "properties":
        return dict(s.ertekek(f.tabla))
    if nev == "tags":
        return list(s.cimke_lista())
    if nev == "links":
        return list(s.link_lista(f.tabla, False))
    if nev == "embeds":
        return list(s.link_lista(f.tabla, True))
    if nev == "backlinks":
        return [Fajl(b, f.tabla) for b in f.tabla.visszalinkek(s.ut)]
    if nev == "ctime":
        return f.tabla.ctime(s)
    if nev == "mtime":
        return s.mtime()
    if nev == "note":
        from .kiertekelo import JegyzetNezet
        return JegyzetNezet(s, f.tabla)
    return None


def mezo(kor, obj, nev: str):
    """`obj.nev`: az ismeretlen mező üres érték (JavaScript `undefined`), nem hiba."""
    if obj is None:
        return None
    if hasattr(obj, "bazis_mezo"):
        return obj.bazis_mezo(kor, nev)
    if isinstance(obj, dict):
        return _dict_get(obj, nev)
    if isinstance(obj, Fajl):
        return fajl_mezo(kor, obj, nev)
    if isinstance(obj, Datum):
        return datum_mezo(obj, nev)
    if isinstance(obj, (str, list)) and nev == "length":
        return len(obj)
    return None


def index(kor, obj, k):
    """`obj[k]`: lista/szöveg számmal (0-tól; kívül: üres), objektum és fájl névvel."""
    if obj is None:
        return None
    if isinstance(obj, (list, str)) and _szam_e(k):
        i = int(k) if float(k).is_integer() else -1
        return obj[i] if 0 <= i < len(obj) else None
    if isinstance(k, str):
        return mezo(kor, obj, k)
    raise FutasHiba("bazis.futas.nem_indexelheto", {"tipus": tipus_neve(obj), "kulcs": tipus_neve(k)})
