"""A Bases adatsorai (C12): `Sor` (egy vault-fájl), `Tabla` (a sorhalmaz és a közös memók).

**A sorhalmaz az index minden élő fájlja**, nem csak a `.md` („By default a base includes every file in the
vault”). A `Tabla` az `Index.generacio` szerint gyorsítótárazódik (`Tar`, a 4. lépésben az indexből töltve);
a sorok a `Tabla` életében nem változnak, így a rajtuk számolt értékek (`Sor.ertekek`) gyorsítótárazhatók.
"""
from __future__ import annotations

import collections
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from . import ertekek
from .ertekek import Cimke, Datum, Link


class Sor:
    """Egy fájl: út, méret, mtime, frontmatter-tulajdonságok, címkék, linkek.

    `tulajdonsagok`: [(kulcs, típus, JSON-érték)] a frontmatter sorrendjében; `cimkek`: a címkék `#` nélkül,
    ahogy az index tárolja (frontmatter, majd szöveg); `linkek`: [{cel_nyers, alcel, alias, beagyazas, cel}],
    ahol a `cel` a feloldott vault-út vagy `None`."""
    __slots__ = ("id", "ut", "lemez_ut", "nev", "kit", "mappa", "tipus", "meret", "mtime_ns", "ctime_ns", "tulajdonsagok",
                 "cimkek", "linkek", "aliasok", "_ert", "_kis", "_cimkek", "_linkek")

    def __init__(self, ut: str, *, tipus: str | None = None, meret: int = 0, mtime_ns: int = 0, tulajdonsagok=(),
                 cimkek=(), linkek=(), aliasok=(), lemez_ut: str | None = None, id: int | None = None,
                 ctime_ns: int | None = None):
        self.id = id
        self.ut = ut
        self.lemez_ut = lemez_ut or ut
        self.mappa, _, self.nev = ut.rpartition("/")
        self.kit = self.nev.rsplit(".", 1)[-1].lower() if "." in self.nev else ""
        self.tipus = tipus or {"md": "md", "canvas": "canvas", "base": "base"}.get(self.kit, "egyeb")
        self.meret, self.mtime_ns = meret, mtime_ns
        self.ctime_ns = ctime_ns                      # a valódi születési idő az indexből (F11), vagy `None`: ismeretlen
        self.tulajdonsagok = list(tulajdonsagok)
        self.cimkek = list(cimkek)
        self.linkek = list(linkek)
        self.aliasok = list(aliasok)
        self._ert = None
        self._kis = None
        self._cimkek = None
        self._linkek = None

    # ---- tulajdonságok (note.*)

    def ertekek(self, tabla: "Tabla") -> dict:
        """A frontmatter értékei kifejezés-értékként (link, dátum, címke-lista), a kulcsok sorrendjében."""
        if self._ert is None:
            def felold(cel):
                return tabla.felold(cel, self.ut)
            ki = {}
            for kulcs, tipus, ertek in self.tulajdonsagok:
                if tipus in ("tags", "aliases") and isinstance(ertek, str):
                    ertek = [t.lstrip("#") for t in re.split(r"," if "," in ertek else r"\s+", ertek) if t.strip()]
                elif tipus == "tags" and isinstance(ertek, list):
                    ertek = [t.lstrip("#") if isinstance(t, str) else t for t in ertek]
                ki[kulcs] = ertekek.fm_ertekbol(ertek, tipus, felold)
            self._ert = ki
        return self._ert

    def tulajdonsag(self, tabla: "Tabla", nev: str):
        """Egy tulajdonság értéke: pontos névre, ennek híján kis-nagybetűtől függetlenül; hiányára `None`."""
        e = self.ertekek(tabla)
        if nev in e:
            return e[nev]
        if self._kis is None:
            self._kis = {}
            for k in e:
                self._kis.setdefault(k.casefold(), k)
        k = self._kis.get(nev.casefold())
        return e[k] if k is not None else None

    def van_tulajdonsag(self, tabla: "Tabla", nev: str) -> bool:
        self.tulajdonsag(tabla, nev)
        return nev in self._ert or nev.casefold() in self._kis

    # ---- file.*

    def cimke_lista(self) -> list[Cimke]:
        """`file.tags`: a címkék `#`-tel, egyszer (a kis-nagybetű nem számít), a sorrendben."""
        if self._cimkek is None:
            lattuk, ki = set(), []
            for c in self.cimkek:
                k = c.casefold()
                if k not in lattuk:
                    lattuk.add(k)
                    ki.append(Cimke("#" + c))
            self._cimkek = ki
        return self._cimkek

    def link_lista(self, tabla: "Tabla", beagyazas: bool) -> list[Link]:
        """`file.links` (`beagyazas` hamis) vagy `file.embeds` (igaz): `Link`-értékek."""
        if self._linkek is None:
            self._linkek = ([], [])
            for L in self.linkek:
                self._linkek[1 if L["beagyazas"] else 0].append(
                    Link(L["cel_nyers"], L.get("alias"), L.get("cel"), L.get("alcel")))
        return self._linkek[1 if beagyazas else 0]

    def mtime(self) -> Datum:
        return Datum(datetime.fromtimestamp(self.mtime_ns / 1e9), True)


class Tabla:
    """A sorhalmaz. `felold(cél, forrás_út) → út | None` az index feloldója (L42: nincs saját feloldás);
    `gyoker`: a vault gyökere (megmaradt a hívók miatt; a `file.ctime` már az indexből jön, 10-bases-13)."""

    def __init__(self, sorok, felold=None, gyoker=None, generacio: int = 0, tipusok: dict | None = None):
        self.sorok: list[Sor] = list(sorok)
        self.tipusok = tipusok or {}                  # a `.obsidian/types.json` rögzített típusai: {kulcs: típus}
        self.ut_szerint: dict[str, Sor] = {s.ut: s for s in self.sorok}
        self._felold = felold
        self.gyoker = Path(gyoker) if gyoker else None
        self.generacio = generacio
        self._memo: dict = {}
        self._visszalinkek: dict[str, list[Sor]] | None = None
        self._tip: dict[str, collections.Counter] | None = None

    def felold(self, cel: str, forras_ut: str) -> str | None:
        """Link-cél feloldása a `forras_ut` fájlból (memózva)."""
        if self._felold is None or not cel:
            return None
        k = (cel, forras_ut)
        if k not in self._memo:
            self._memo[k] = self._felold(cel, forras_ut)
        return self._memo[k]

    def tulajdonsag_tipus(self, kulcs: str) -> str:
        """Egy frontmatter-tulajdonság típusa: a `types.json` rögzített típusa, ennek híján a sorokon leggyakoribb."""
        if kulcs in self.tipusok:
            return self.tipusok[kulcs]
        if self._tip is None:
            self._tip = {}
            for s in self.sorok:
                for k, t, _ in s.tulajdonsagok:
                    self._tip.setdefault(k, collections.Counter())[t] += 1
        c = self._tip.get(kulcs)
        return c.most_common(1)[0][0] if c else "text"

    def tulajdonsag_lista(self, max_db: int = 400) -> list[tuple[str, str]]:
        """A vault frontmatter-tulajdonságai [(kulcs, típus)]: a leggyakoribb elöl (a tulajdonság-választóhoz)."""
        self.tulajdonsag_tipus("")                            # a gyakorisági tábla felépítése
        rend = sorted(self._tip.items(), key=lambda kv: (-sum(kv[1].values()), kv[0].casefold()))
        return [(k, self.tulajdonsag_tipus(k)) for k, _ in rend[:max_db]]

    def fajl(self, ut: str | None):
        s = self.ut_szerint.get(ut) if ut else None
        return ertekek.Fajl(s, self) if s is not None else None

    def visszalinkek(self, ut: str) -> list[Sor]:
        """Azok a fájlok, amelyek linkelnek az `ut`-ra (önhivatkozás nélkül, útrendben). Lusta: csak akkor épül."""
        if self._visszalinkek is None:
            v: dict[str, list[Sor]] = {}
            for s in self.sorok:
                lattuk = set()
                for L in s.linkek:
                    cel = L.get("cel")
                    if cel and cel != s.ut and cel not in lattuk:
                        lattuk.add(cel)
                        v.setdefault(cel, []).append(s)
            self._visszalinkek = v
        return self._visszalinkek.get(ut, [])

    def ctime(self, sor: Sor) -> Datum | None:
        """`file.ctime`: a fájl valódi születési ideje az indexből (`fajl.ctime_ns`, F11). Ismeretlen születési időre
        (a fájlrendszer nem ad) `None`: sosem az mtime és sosem a POSIX `st_ctime` (10-bases-13)."""
        return Datum(datetime.fromtimestamp(sor.ctime_ns / 1e9), True) if sor.ctime_ns else None


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


INKREMENTALIS_MAX = 200         # ennyi változott útig a `Tabla` inkrementálisan frissül (C33, T070); fölötte teljes újraolvasás


class Tar:
    """A `Tabla` gyorsítótára az `Index.generacio` szerint: ha az index nem változott, ugyanaz a `Tabla` (és a
    rajta számolt értékek) szolgálja ki a lekérdezéseket; változás után az első hívás frissít.

    C33 (T070): a frissítés **inkrementális**, ha az index változásnaplója szerint csak meglévő fájlok sorai változtak (a
    tipikus mentés): csak azok a `Sor`-ok épülnek újra, a többi (a rajtuk számolt értékekkel) marad. Új vagy eltűnt fájl,
    típusváltás vagy a napló hiánya után teljes újraolvasás (a feloldás más fájlok linkjeit is átírhatta).
    `utolso_ms`, `utolso_mod`: az utolsó frissítés ideje és módja (`meleg` | `inkrementalis` | `teljes`; T179)."""

    def __init__(self, index):
        self.index = index
        self._tabla: Tabla | None = None
        self._zar = threading.Lock()
        self.utolso_ms = 0.0
        self.utolso_mod = "meleg"

    def _uj_tabla(self, sorok, gen: int) -> Tabla:
        return Tabla(sorok, self.index.felold_egy, self.index.root, gen, self.index.tipusok)

    @staticmethod
    def _sor(fid, ut, lemez, tip, meret, mtime, tul, cim, lnk, alias, ctime=None) -> Sor:
        return Sor(ut, tipus=tip, meret=meret, mtime_ns=mtime, tulajdonsagok=tul, cimkek=cim, linkek=lnk, aliasok=alias,
                   lemez_ut=lemez, id=fid, ctime_ns=ctime)

    def tabla(self) -> Tabla:
        t = self._tabla
        if t is not None and t.generacio == self.index.generacio:
            self.utolso_ms, self.utolso_mod = 0.0, "meleg"
            return t
        with self._zar:
            t0 = time.perf_counter()
            t = self._tabla
            if t is not None and t.generacio == self.index.generacio:
                self.utolso_ms, self.utolso_mod = 0.0, "meleg"
                return t
            valtozasok = getattr(self.index, "valtozasok_ota", None)
            most, utak = valtozasok(t.generacio) if (t is not None and valtozasok is not None) else (None, None)
            if t is not None and utak is not None and len(utak) <= INKREMENTALIS_MAX:
                _, sorok = self.index.bazis_sorok(utak)
                frissek = {s[1]: self._sor(*s) for s in sorok}
                if all(u in t.ut_szerint for u in frissek) and all(u in frissek for u in utak if u in t.ut_szerint):
                    uj = [frissek.get(s.ut, s) for s in t.sorok]
                    self._tabla = self._uj_tabla(uj, most)
                    self.utolso_ms, self.utolso_mod = (time.perf_counter() - t0) * 1000, "inkrementalis"
                    return self._tabla
            gen, sorok = self.index.bazis_sorok()
            self._tabla = self._uj_tabla([self._sor(*s) for s in sorok], gen)
            self.utolso_ms, self.utolso_mod = (time.perf_counter() - t0) * 1000, "teljes"
            return self._tabla
