"""A vektortár inkrementális frissítése (C25b-mag).

- `terv(index_hashek, tar_hashek)` — **tiszta függvény**: melyik jegyzet új, változott, törölt (a `vault.sqlite`
  `fajl.hash`-e és a tár `jegyzet.hash`-e szerint).
- `frissit(…)` — a végrehajtás jegyzetenként (egy jegyzet darabjai atomian cserélődnek), kötegelt beágyazással; a
  változatlan szövegű darab vektora a tárból jön (nem ágyazódik újra). **Minden jegyzet előtt** megkérdezi a
  `folytathat()` hívhatót: `False` → a frissítés ott megáll, és a következő futás onnan folytatja (a terv a hash-ekből
  újra kijön). A core-ban ez a meglévő `Kapu.admit` egy automatikus feladatra (`kapu_folytathat`): a D8 indulási
  szünetét, az aktív használatot és a memóriaőrt **nem másoljuk**, a kapu dönt. Háttérszálat, ütemezőt ez a modul nem
  indít (a közös automatika-ütemező a C23b `core/automatika.py`-ja; a feladattípus-kötés a C25b modellfele).

A beágyazó (`Beagyazo`) egy hívható: `(szövegek, fajta) → vektorok`, ahol `fajta` `"dokumentum"` vagy `"kerdes"` (a
modell-specifikus előtagot a beágyazó teszi hozzá; az előtag verziója a modell-kulcs része, 2. audit T154).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Protocol

from . import darabolas
from .vektortar import Vektortar

# a kapu (`core/modell/kapu.py`) `admit`-ja ezt a két mezőt nézi: automatikus, modellt igénylő munka
AUTOMATIKUS_FELADAT = SimpleNamespace(id="vektorindex", automatikus=True, resources=frozenset({"modell"}))
DARABOLAS_VERZIO = 'd2'  # S1: a %% komment a TS parserrel azonos tartományban kiesik a szemantikus szövegből.


class Beagyazo(Protocol):
    nev: str
    dim: int
    elotag: str                                   # az előtag-szabály verziója (pl. "bge-m3:nincs", "e5:query/passage")

    def __call__(self, szovegek: list[str], fajta: str) -> list[list[float]]: ...


def modell_kulcs(b: Beagyazo, darab_max: int = darabolas.DARAB_MAX) -> dict:
    return {"nev": b.nev, "dim": int(b.dim), "elotag": b.elotag, "darabolas": f"{DARABOLAS_VERZIO}-{darab_max}"}


def aktualis_darabolas(kulcs: dict | None) -> bool:
    """Régi cache a változatlan forrás-SHA ellenére elavult; olvasáskor sem szolgálhat ki d1 darabokat."""
    return bool(kulcs) and str(kulcs.get('darabolas', '')).startswith(f'{DARABOLAS_VERZIO}-')


def kapu_folytathat(kapu) -> Callable[[], bool]:
    """A meglévő feladatsor-kapu (`Kapu.admit`) döntése egy automatikus, modellt igénylő munkára."""
    return lambda: bool(kapu.admit(AUTOMATIKUS_FELADAT))


@dataclass(frozen=True)
class Terv:
    uj: tuple[str, ...]
    valtozott: tuple[str, ...]
    torolt: tuple[str, ...]

    @property
    def ures(self) -> bool:
        return not (self.uj or self.valtozott or self.torolt)


def terv(index_hashek: dict[str, str | None], tar_hashek: dict[str, str]) -> Terv:
    """Tiszta függvény: az index élő `.md` jegyzetei (út → hash) és a tár jegyzetei (út → hash) → a teendők, rendezve."""
    uj = sorted(u for u in index_hashek if u not in tar_hashek)
    valtozott = sorted(u for u, h in index_hashek.items() if u in tar_hashek and tar_hashek[u] != (h or ""))
    torolt = sorted(u for u in tar_hashek if u not in index_hashek)
    return Terv(tuple(uj), tuple(valtozott), tuple(torolt))


def index_hashek(c) -> dict[str, str | None]:
    """Az index élő `.md` jegyzetei: út → tartalom-hash (`vault.sqlite`, csak olvasva)."""
    return {u: h for u, h in c.execute("SELECT ut, hash FROM fajl WHERE torolve IS NULL AND tipus = 'md'")}


def jegyzet_darabjai(c, ut: str, darab_max: int = darabolas.DARAB_MAX,
                     kihagyott: tuple[str, ...] | list[str] | None = None) -> list[darabolas.Darab]:
    """A jegyzet darabjai az index tábláiból (`fts.tartalom`, `fejezet`, `blokk`); nincs ilyen élő jegyzet → `[]`. `kihagyott`: a
    kihagyott szakaszok címei (`[kapuk] kihagyott_szakaszok`; hiányában a kapu alapja)."""
    r = c.execute("SELECT f.id, fts.tartalom FROM fajl f JOIN fts ON fts.rowid = f.id "
                  "WHERE f.ut = ? AND f.torolve IS NULL AND f.tipus = 'md'", (ut,)).fetchone()
    if r is None:
        return []
    fid, tartalom = r[0], r[1] or ""
    fejezetek = c.execute("SELECT szint, szoveg, sor FROM fejezet WHERE fajl_id = ? ORDER BY sor", (fid,)).fetchall()
    blokkok = c.execute("SELECT azon, sor, kezdo_sor FROM blokk WHERE fajl_id = ? ORDER BY sor", (fid,)).fetchall()
    return darabolas.darabol(ut, tartalom, [tuple(x) for x in fejezetek], [tuple(x) for x in blokkok], darab_max, kihagyott)


@dataclass
class Eredmeny:
    terv: Terv | None = None
    beagyazott_jegyzet: int = 0
    beagyazott_darab: int = 0
    ujrahasznalt_darab: int = 0
    torolt: int = 0
    megszakitva: bool = False
    ujraepites: bool = False
    hibak: list[str] = field(default_factory=list)
    mp: float = 0.0

    def to_dict(self) -> dict:
        t = self.terv
        return {"terv": {"uj": len(t.uj), "valtozott": len(t.valtozott), "torolt": len(t.torolt)} if t else None,
                "beagyazott_jegyzet": self.beagyazott_jegyzet, "beagyazott_darab": self.beagyazott_darab,
                "ujrahasznalt_darab": self.ujrahasznalt_darab, "torolt": self.torolt, "megszakitva": self.megszakitva,
                "ujraepites": self.ujraepites, "hibak": list(self.hibak), "mp": round(self.mp, 3)}


def frissit(index_olvaso, tar: Vektortar, beagyazo: Beagyazo, folytathat: Callable[[], bool] = lambda: True,
            koteg: int = 16, max_jegyzet: int | None = None, darab_max: int = darabolas.DARAB_MAX,
            ido: Callable[[], float] = time.time, kihagyott: tuple[str, ...] | list[str] | None = None) -> Eredmeny:
    """A tár a vaulthoz igazítva (lásd a modul leírását). `index_olvaso`: kontextuskezelő-gyár a `vault.sqlite`
    olvasó kapcsolatához (az `IndexOlvaso.olvaso`); `max_jegyzet`: legfeljebb ennyi jegyzet ágyazódik be ebben a futásban."""
    t0 = time.monotonic()
    e = Eredmeny()
    e.ujraepites = tar.modell_allit(modell_kulcs(beagyazo, darab_max))
    with index_olvaso() as c:
        e.terv = terv(index_hashek(c), tar.jegyzet_hashek())
    for ut in e.terv.torolt:
        tar.jegyzet_torol(ut)
        e.torolt += 1
    for ut in (*e.terv.uj, *e.terv.valtozott):
        if max_jegyzet is not None and e.beagyazott_jegyzet >= max_jegyzet:
            e.megszakitva = True
            break
        if not folytathat():
            e.megszakitva = True
            break
        with index_olvaso() as c:
            r = c.execute("SELECT hash FROM fajl WHERE ut = ? AND torolve IS NULL AND tipus = 'md'", (ut,)).fetchone()
            darabok = jegyzet_darabjai(c, ut, darab_max, kihagyott)
        if r is None:                                   # közben eltűnt: a következő terv törli
            continue
        meglevo = tar.vektorok_hash_szerint(d.hash for d in darabok)
        kell = [d for d in darabok if d.hash not in meglevo]
        uj: dict[str, list[float]] = {}
        try:
            for i in range(0, len(kell), koteg):
                resz = kell[i:i + koteg]
                vektorok = beagyazo([d.beagyazando for d in resz], "dokumentum")
                if len(vektorok) != len(resz):
                    raise ValueError(f"a beágyazó {len(vektorok)} vektort adott {len(resz)} szövegre")
                uj.update({d.hash: v for d, v in zip(resz, vektorok)})
        except Exception as ex:                         # noqa: BLE001 — egy jegyzet hibája nem állítja meg a többit
            e.hibak.append(f"{ut}: {ex}")
            continue
        tar.jegyzet_ir(ut, r[0] or "", darabok, [meglevo.get(d.hash) or uj[d.hash] for d in darabok], ido())
        e.beagyazott_jegyzet += 1
        e.beagyazott_darab += len(kell)
        e.ujrahasznalt_darab += len(darabok) - len(kell)
    e.mp = time.monotonic() - t0
    return e
