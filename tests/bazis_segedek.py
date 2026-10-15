"""A Bases-tesztek közös segédei: álsorok, álvault-tábla, kifejezés-kiértékelés."""
from datetime import datetime

from core.bazis.adat import Sor, Tabla
from core.bazis.ertekek import Datum
from core.bazis.kiertekelo import Kor, KepletTar, ertekel
from core.index.feloldas import Feloldo

MOST = Datum(datetime(2026, 10, 2, 12, 0, 0), True)


def sor(ut, tul=None, cimkek=(), linkek=(), meret=100, mtime=None, tipus=None, **kw):
    """Álsor: `tul` = {kulcs: érték} (a típus az értékből: `{kulcs: (típus, érték)}` is lehet)."""
    t = []
    for k, v in (tul or {}).items():
        tipus_, ertek = v if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str) and \
            v[0] in ("text", "multitext", "number", "checkbox", "date", "datetime", "tags", "aliases") else (None, v)
        if tipus_ is None:
            from core.index.elemzo import tipus_ertekbol
            tipus_ = tipus_ertekbol(k, ertek)
        t.append((k, tipus_, ertek))
    ln = []
    for L in linkek:
        L = dict(L) if isinstance(L, dict) else {"cel_nyers": L}
        L.setdefault("alcel", None)
        L.setdefault("alias", None)
        L.setdefault("beagyazas", False)
        L.setdefault("cel", None)
        ln.append(L)
    ns = int((mtime or datetime(2026, 9, 1, 8, 0, 0)).timestamp() * 1e9)
    return Sor(ut, tulajdonsagok=t, cimkek=cimkek, linkek=ln, meret=meret, mtime_ns=ns, tipus=tipus, **kw)


def tabla(sorok, extra_utak=()):
    """Tábla a sorokkal; a link-célok a `Feloldo`-val oldódnak fel (a sorok `linkek[].cel` mezője is kitöltődik)."""
    utak = [s.ut for s in sorok] + list(extra_utak)
    f = Feloldo(utak)
    for s in sorok:
        for L in s.linkek:
            if L.get("cel") is None:
                L["cel"] = f.resolve(L["cel_nyers"], s.ut)[0]
    return Tabla(sorok, lambda cel, forras: f.resolve(cel, forras)[0])


def ertek(kif, s=None, t=None, ez=None, kepletek=None, helyi=None, most=MOST):
    """A kifejezés értéke a `s` soron (nélküle: sor nélküli környezetben)."""
    t = t or (tabla([s]) if s is not None else None)
    kt = KepletTar(kepletek) if kepletek else None
    k = Kor(sor=s, tabla=t, ez=ez, kepletek=kt, helyi=helyi, most=most)
    return ertekel(kif, k)
