"""A ```plot automatikus beírásának tartós állapota (C35b-mag; docs/PLOT-FORMATUM.md „A tiltólista helye”).

Három kis JSON-fájl a `{state}` alatt (a 33. döntés szerint a belső mentésben vannak; a vaultba semmi nem kerül):

- `plot-tiltolista.json` — **tiltólista** (5. döntés: a törölt blokk képlete nem kap újat). Kulcs = a képlet ujjlenyomata
  (`Javaslat.kulcs`: jegyzet-úttól független, így az átnevezés nem támasztja fel); a rekord az utat csak megjelenítésre tárolja.
- `plot-beirasok.json` — a gép által beírt blokkok naplója (jegyzet-út, képlet-kulcs, a blokk szövege, a gépi commit sha-ja):
  ebből ismerhető fel, hogy a felhasználó törölte a blokkot (és nem szerkesztette, nem vonta vissza).
- `plot-automatika.json` — (C35b-mag) jegyzetenként az utoljára feldolgozott változat mondathalmaza. **A C35b (K309) óta nem
  íródik**: az állapot a közös ütemező tárában (`core/automatika.py` `Tar`, `grafikon` fogyasztó) él; a régi fájlt az
  `Automatika.atvesz` egyszer átveszi és `.atvett` névre teszi.

Csak standard könyvtár (a core nem importál `modulok`-ot). Az írás zárral és atomi cserével megy, mert a core (végpont) és a
feladatsor lépése (alfolyamat) is írja. **Zárt hibázás**: a sérült fájl `AllapotHiba`, nem üres lista — a tiltólista csendes
elvesztése éppen azt a blokkot írná vissza, amelyet a felhasználó törölt.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

TILTOLISTA = "plot-tiltolista.json"
BEIRASOK = "plot-beirasok.json"
AUTOMATIKA = "plot-automatika.json"
MAX_BEIRAS = 5000               # a napló korlátja: a legrégebbi rekord esik ki
KULCS_MINTA = re.compile(r"[0-9a-f]{16}")
_SZAL = threading.Lock()


class AllapotHiba(RuntimeError):
    """Az állapotfájl nem olvasható vagy nem a várt alakú; a hívó nem ír és nem dönt, jelzi."""


def _most() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class _Fajl:
    """Egy JSON-objektum a `{state}` alatt: zárolt olvasás-módosítás-írás, atomi csere."""

    def __init__(self, cfg, nev: str, alap):
        self.ut = Path(cfg.path("state")) / nev
        self.alap = alap

    def olvas(self):
        try:
            nyers = self.ut.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self.alap()
        except OSError as e:
            raise AllapotHiba(f"{self.ut.name}: nem olvasható: {e}") from None
        try:
            adat = json.loads(nyers)
        except ValueError:
            raise AllapotHiba(f"{self.ut.name}: sérült JSON") from None
        if not isinstance(adat, type(self.alap())):
            raise AllapotHiba(f"{self.ut.name}: váratlan alak")
        return adat

    @contextlib.contextmanager
    def modosit(self):
        """Zárolt olvasás → a hívó módosítja a visszaadott objektumot → atomi írás (kivételnél nem íródik semmi)."""
        self.ut.parent.mkdir(parents=True, exist_ok=True)
        with _SZAL, open(self.ut.with_name("." + self.ut.name + ".lock"), "a") as zar:
            fcntl.flock(zar, fcntl.LOCK_EX)
            try:
                adat = self.olvas()
                yield adat
                fd, tmp = tempfile.mkstemp(prefix="." + self.ut.name + ".", suffix=".manifold-tmp", dir=self.ut.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(adat, f, ensure_ascii=False, indent=1, sort_keys=True)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self.ut)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                    raise
            finally:
                fcntl.flock(zar, fcntl.LOCK_UN)


class Tiltolista:
    """`{kulcs: {"ut", "ido", "ok"}}`; a kulcs a képlet ujjlenyomata (16 hex)."""

    def __init__(self, cfg):
        self._f = _Fajl(cfg, TILTOLISTA, dict)

    def kulcsok(self) -> frozenset[str]:
        return frozenset(self._f.olvas())

    def lista(self) -> list[dict]:
        return [{"kulcs": k, **v} for k, v in sorted(self._f.olvas().items(), key=lambda t: t[1].get("ido", ""))]

    def felvesz(self, kulcs: str, ut: str, ok: str = "a felhasználó törölte a blokkot") -> bool:
        """→ igaz, ha új volt (a már tiltott kulcs rekordja nem íródik át)."""
        if not KULCS_MINTA.fullmatch(kulcs or ""):
            raise ValueError("a kulcs 16 hexa jegy")
        with self._f.modosit() as d:
            if kulcs in d:
                return False
            d[kulcs] = {"ut": str(ut), "ido": _most(), "ok": ok}
            return True

    def levesz(self, kulcs: str) -> bool:
        """A vezérlőből való levétel. → igaz, ha volt ilyen tétel."""
        with self._f.modosit() as d:
            return d.pop(kulcs, None) is not None


class Beirasok:
    """A gépi beírások naplója: lista `{"ut", "kulcs", "blokk", "sha", "ido"}` rekordokból, legrégebbi elöl."""

    def __init__(self, cfg):
        self._f = _Fajl(cfg, BEIRASOK, list)

    def lista(self) -> list[dict]:
        return list(self._f.olvas())

    def hozzaad(self, rekordok: list[dict]) -> None:
        if not rekordok:
            return
        with self._f.modosit() as d:
            for r in rekordok:
                d[:] = [x for x in d if not (x.get("ut") == r["ut"] and x.get("kulcs") == r["kulcs"])]
                d.append({**r, "ido": r.get("ido") or _most()})
            del d[:-MAX_BEIRAS]

    def torol(self, ut: str, kulcs: str) -> None:
        with self._f.modosit() as d:
            d[:] = [x for x in d if not (x.get("ut") == ut and x.get("kulcs") == kulcs)]


class Automatika:
    """`{jegyzet-út: {"mtime", "mondatok", "kepletek", "ujjlenyomat", "ido"}}` — az utoljára feldolgozott változat: a fájl módosítási
    ideje (a gyors kihagyáshoz), a mondathalmaz (az „erősen módosult” mértékhez), a képletek kulcsai („új képlet”) és a tartalmi
    ujjlenyomat. A képletet nem tartalmazó jegyzetnél csak az `mtime` áll."""

    def __init__(self, cfg):
        self._f = _Fajl(cfg, AUTOMATIKA, dict)

    def olvas(self) -> dict:
        return self._f.olvas()

    @staticmethod
    def rekord(mtime: float, mondatok=(), kepletek=(), ujjlenyomat: str = "") -> dict:
        return {"mtime": float(mtime), "mondatok": sorted(mondatok), "kepletek": sorted(kepletek),
                "ujjlenyomat": ujjlenyomat, "ido": _most()}

    def ment(self, ut: str, mtime: float, mondatok=(), kepletek=(), ujjlenyomat: str = "") -> None:
        self.ment_tobb({ut: self.rekord(mtime, mondatok, kepletek, ujjlenyomat)})

    def ment_tobb(self, rekordok: dict[str, dict]) -> None:
        """Több jegyzet állapota egyetlen (zárolt, atomi) írással — a vault első bejárása ne írja újra a fájlt jegyzetenként."""
        if not rekordok:
            return
        with self._f.modosit() as d:
            d.update(rekordok)

    def elfelejt(self, ut: str) -> None:
        with self._f.modosit() as d:
            d.pop(ut, None)

    def atvesz(self, tar, fogyaszto: str = "grafikon") -> int:
        """K309: a régi állapotfájl sorai a közös tárba (`Tar.atvesz`: az alap, az ujjlenyomat, a képletkulcsok), majd a fájl
        `.atvett` néven félretéve (nem törlődik). → az átvett sorok száma; fájl nélkül 0. A sérült fájl `AllapotHiba`."""
        if not self._f.ut.exists():
            return 0
        sorok = {u: r for u, r in self.olvas().items() if isinstance(r, dict) and r.get("mondatok")}
        for u, r in sorok.items():
            tar.atvesz(fogyaszto, u, list(r["mondatok"]), r.get("ujjlenyomat") or "", {"kepletek": sorted(r.get("kepletek") or ())})
        os.replace(self._f.ut, self._f.ut.with_name(self._f.ut.name + ".atvett"))
        return len(sorok)
