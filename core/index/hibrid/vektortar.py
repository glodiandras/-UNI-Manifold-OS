"""A vektortár: `{index}/vektor.sqlite` — a darabok és a vektoraik (C25b-mag).

**Újraépíthető gyorsítótár** a vaultból (mint a `vault.sqlite`, L60): a `var/index/` alatt él, a belső mentésbe nem kerül
(33. döntés: ott az állapot-SQLite-ok vannak, az index nem). Séma csak új migrációval (`PRAGMA user_version`), WAL.

Az **igazságforrás a `darab.vektor` BLOB** (float32, egységnyi hosszra normálva); a KNN-motor cserélhető:

- `sqlite-vec`: a `vec0` virtuális tábla (`vec_darab`, rowid = `darab.id`, koszinusz-távolság), ha a `sqlite_vec` csomag
  betölthető — ma **nincs a lockban** (D3: a letöltés a felhasználó igenjére, `docs/NAPLO.md` C25b-mag);
- `numpy`: brute-force koszinusz a memóriában tartott mátrixon (a numpy a lockban van);
- `python`: ugyanez tiszta Pythonban (tartalék és teszt; lassú, de helyes).

A **modell-kulcs** (beágyazó neve, dimenzió, előtag-verzió, darabolás-verzió) a `meta` táblában áll: ha bármelyik
változik, a tár kiürül (a régi vektorok más térben vannak, nem keverhetők). A frissítés jegyzetenként atomi: egy jegyzet
darabjai együtt cserélődnek.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from array import array
from dataclasses import dataclass
from pathlib import Path

VERZIO = 1
MOTOROK = ("sqlite-vec", "numpy", "python")

_SEMA = """
CREATE TABLE meta(kulcs TEXT PRIMARY KEY, ertek TEXT);
CREATE TABLE jegyzet(ut TEXT PRIMARY KEY, hash TEXT, darabok INTEGER, frissitve REAL);
CREATE TABLE darab(
    id INTEGER PRIMARY KEY,
    ut TEXT NOT NULL,                   -- a jegyzet NFC vault-útja (mint a `vault.sqlite` `fajl.ut`)
    sorszam INTEGER NOT NULL,
    sor_kezd INTEGER, sor_veg INTEGER,  -- a jegyzet szövegének sorai (1-től)
    fejezet TEXT,                       -- JSON: a címsor-út
    bekezdesek TEXT,                    -- JSON: [[sor_kezd, sor_veg, blokk|null, szöveg]…]
    szoveg TEXT,
    hash TEXT NOT NULL,                 -- a beágyazott szöveg sha1-e: a változatlan darab vektora újrahasznosul
    vektor BLOB NOT NULL                -- float32, egységnyi hossz
);
CREATE INDEX darab_ut ON darab(ut);
CREATE INDEX darab_hash ON darab(hash);
"""


class NincsTar(RuntimeError):
    """A vektortár még nem épült fel (csak olvasó megnyitáskor)."""


@dataclass(frozen=True)
class DarabSor:
    id: int
    ut: str
    sorszam: int
    sor_kezd: int
    sor_veg: int
    fejezet: tuple[str, ...]
    bekezdesek: tuple[tuple[int, int, str | None, str], ...]
    szoveg: str

    @property
    def cim(self) -> str:
        return self.ut.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def normal(v) -> array:
    """Egységnyi hosszú float32 vektor (a nulla vektor nulla marad)."""
    a = array("f", (float(x) for x in v))
    n = math.sqrt(sum(x * x for x in a))
    if n > 0:
        a = array("f", (x / n for x in a))
    return a


def _sqlite_vec():
    try:
        import sqlite_vec  # type: ignore[import-not-found]
    except ImportError:
        return None
    return sqlite_vec


def _numpy():
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def elerheto_motor() -> str:
    """A legjobb elérhető motor: `sqlite-vec` > `numpy` > `python`."""
    if _sqlite_vec() is not None:
        return "sqlite-vec"
    return "numpy" if _numpy() is not None else "python"


class Vektortar:
    """A tár egy kapcsolattal és egy zárral (a core szálai és a frissítő közösen használják)."""

    def __init__(self, ut: Path, csak_olvas: bool = False, motor: str | None = None):
        self.ut = Path(ut)
        self.csak_olvas = csak_olvas
        if csak_olvas and not self.ut.exists():
            raise NincsTar("a vektortár még nem épült fel")
        if not csak_olvas:
            self.ut.parent.mkdir(parents=True, exist_ok=True)
        self._zar = threading.RLock()
        self._c = sqlite3.connect(str(self.ut), timeout=30, check_same_thread=False, isolation_level=None)
        self._c.execute("PRAGMA busy_timeout = 30000")
        motor = motor or elerheto_motor()
        if motor not in MOTOROK:
            raise ValueError(f"ismeretlen vektor-motor: {motor}")
        self.motor = motor
        self._vec = None
        if motor == "sqlite-vec":
            self._vec = self._vec_betolt()
            if self._vec is None:
                self.motor = "numpy" if _numpy() is not None else "python"
        if csak_olvas:
            self._c.execute("PRAGMA query_only = 1")
        else:
            self._c.execute("PRAGMA journal_mode = WAL")
            self._c.execute("PRAGMA synchronous = NORMAL")
            self._migral()
        self._gyorsitotar = None            # (kulcs, azonosítók, utak, mátrix)
        self.generacio = 0

    # ------------------------------------------------------------------ séma

    def _vec_betolt(self):
        sv = _sqlite_vec()
        if sv is None:
            return None
        try:
            self._c.enable_load_extension(True)
            sv.load(self._c)
            self._c.enable_load_extension(False)
        except (AttributeError, sqlite3.Error):
            return None
        return sv

    def _migral(self) -> None:
        v = self._c.execute("PRAGMA user_version").fetchone()[0]
        if v > VERZIO:
            raise RuntimeError(f"a vektortár sémája ({v}) újabb, mint a kódé ({VERZIO})")
        if v < 1:
            self._c.execute("BEGIN")
            for stmt in [s.strip() for s in _SEMA.split(";") if s.strip()]:
                self._c.execute("\n".join(x.split("--")[0] for x in stmt.splitlines()))
            self._c.execute(f"PRAGMA user_version = {VERZIO}")
            self._c.execute("COMMIT")

    def _vec_tabla(self, dim: int) -> None:
        """A `vec0` tábla (csak a `sqlite-vec` motorral); a dimenzió a modell-kulcsé."""
        if self._vec is None or not dim:
            return
        self._c.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_darab USING vec0(embedding float[{int(dim)}] "
                        "distance_metric=cosine)")

    def close(self) -> None:
        with self._zar:
            self._c.close()

    # ------------------------------------------------------------------ meta, modell-kulcs

    def meta(self, kulcs: str) -> str | None:
        with self._zar:
            r = self._c.execute("SELECT ertek FROM meta WHERE kulcs = ?", (kulcs,)).fetchone()
            return r[0] if r else None

    def modell_kulcs(self) -> dict | None:
        m = self.meta("modell_kulcs")
        return json.loads(m) if m else None

    def modell_allit(self, kulcs: dict) -> bool:
        """A beágyazó azonossága (`nev`, `dim`, `elotag`, `darabolas`). Ha eltér a tárolttól, a tár kiürül (→ `True`)."""
        kulcs = dict(sorted(kulcs.items()))
        with self._zar:
            regi = self.modell_kulcs()
            if regi == kulcs:
                return False
            self._c.execute("BEGIN")
            try:
                self._c.execute("DELETE FROM darab")
                self._c.execute("DELETE FROM jegyzet")
                if self._vec is not None:
                    self._c.execute("DROP TABLE IF EXISTS vec_darab")
                self._c.execute("INSERT INTO meta VALUES ('modell_kulcs', ?) ON CONFLICT(kulcs) DO UPDATE SET "
                                "ertek = excluded.ertek", (json.dumps(kulcs, ensure_ascii=False),))
                self._vec_tabla(int(kulcs.get("dim") or 0))
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise
            self._valtozott()
            return regi is not None

    # ------------------------------------------------------------------ írás

    def jegyzet_hashek(self) -> dict[str, str]:
        with self._zar:
            return {u: h for u, h in self._c.execute("SELECT ut, hash FROM jegyzet")}

    def vektorok_hash_szerint(self, hashek) -> dict[str, bytes]:
        """A már tárolt darabvektorok a szöveg-hash szerint (újrahasznosításhoz)."""
        ki: dict[str, bytes] = {}
        hashek = list(set(hashek))
        with self._zar:
            for i in range(0, len(hashek), 500):
                resz = hashek[i:i + 500]
                for h, v in self._c.execute(f"SELECT hash, vektor FROM darab WHERE hash IN ({','.join('?' * len(resz))})",
                                            resz):
                    ki.setdefault(h, v)
        return ki

    def jegyzet_ir(self, ut: str, hash_: str, darabok, vektorok, mikor: float = 0.0) -> None:
        """A jegyzet darabjainak cseréje egy tranzakcióban. `darabok`: `darabolas.Darab`; `vektorok`: float-listák vagy
        már normált float32 `bytes` (újrahasznosítás)."""
        if len(darabok) != len(vektorok):
            raise ValueError("a darabok és a vektorok száma eltér")
        dim = int((self.modell_kulcs() or {}).get("dim") or 0)
        sorok = []
        for d, v in zip(darabok, vektorok):
            b = v if isinstance(v, (bytes, bytearray)) else normal(v).tobytes()
            if dim and len(b) != 4 * dim:
                raise ValueError(f"a vektor dimenziója ({len(b) // 4}) nem a tár dimenziója ({dim})")
            bek = [[x.sor_kezd, x.sor_veg, x.blokk, x.szoveg] for x in d.bekezdesek]
            sorok.append((ut, d.sorszam, d.sor_kezd, d.sor_veg, json.dumps(list(d.fejezet), ensure_ascii=False),
                          json.dumps(bek, ensure_ascii=False), d.szoveg, d.hash, bytes(b)))
        with self._zar:
            self._c.execute("BEGIN")
            try:
                self._torol(ut)
                for s in sorok:
                    rid = self._c.execute("INSERT INTO darab(ut, sorszam, sor_kezd, sor_veg, fejezet, bekezdesek, szoveg, "
                                          "hash, vektor) VALUES (?,?,?,?,?,?,?,?,?)", s).lastrowid
                    if self._vec is not None:
                        self._c.execute("INSERT INTO vec_darab(rowid, embedding) VALUES (?, ?)", (rid, s[-1]))
                self._c.execute("INSERT INTO jegyzet VALUES (?, ?, ?, ?) ON CONFLICT(ut) DO UPDATE SET hash = excluded.hash, "
                                "darabok = excluded.darabok, frissitve = excluded.frissitve", (ut, hash_, len(sorok), mikor))
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise
            self._valtozott()

    def _torol(self, ut: str) -> None:
        if self._vec is not None:
            self._c.execute("DELETE FROM vec_darab WHERE rowid IN (SELECT id FROM darab WHERE ut = ?)", (ut,))
        self._c.execute("DELETE FROM darab WHERE ut = ?", (ut,))
        self._c.execute("DELETE FROM jegyzet WHERE ut = ?", (ut,))

    def jegyzet_torol(self, ut: str) -> None:
        with self._zar:
            self._c.execute("BEGIN")
            try:
                self._torol(ut)
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise
            self._valtozott()

    def _valtozott(self) -> None:
        self.generacio += 1
        self._gyorsitotar = None

    # ------------------------------------------------------------------ olvasás

    def darabok(self, azonositok=None, ut: str | None = None) -> list[DarabSor]:
        """Darabok azonosító szerint (a kért sorrendben), vagy egy jegyzet darabjai (sorszám szerint)."""
        with self._zar:
            if ut is not None:
                sorok = self._c.execute("SELECT id, ut, sorszam, sor_kezd, sor_veg, fejezet, bekezdesek, szoveg FROM darab "
                                        "WHERE ut = ? ORDER BY sorszam", (ut,)).fetchall()
            else:
                ids = list(azonositok or [])
                sorok = []
                for i in range(0, len(ids), 500):
                    resz = ids[i:i + 500]
                    sorok += self._c.execute("SELECT id, ut, sorszam, sor_kezd, sor_veg, fejezet, bekezdesek, szoveg FROM "
                                             f"darab WHERE id IN ({','.join('?' * len(resz))})", resz).fetchall()
                rend = {x: i for i, x in enumerate(ids)}
                sorok.sort(key=lambda r: rend.get(r[0], 0))
        return [DarabSor(r[0], r[1], r[2], r[3], r[4], tuple(json.loads(r[5] or "[]")),
                         tuple(tuple(b) for b in json.loads(r[6] or "[]")), r[7]) for r in sorok]

    def _matrix(self):
        # a kulcs a saját írások számlálója és az SQLite `data_version`-je: egy másik kapcsolat (az építő) írása is érvényteleníti
        kulcs = (self.generacio, self._c.execute("PRAGMA data_version").fetchone()[0])
        g = self._gyorsitotar
        if g is not None and g[0] == kulcs:
            return g
        sorok = self._c.execute("SELECT id, ut, vektor FROM darab ORDER BY id").fetchall()
        ids = [r[0] for r in sorok]
        utak = [r[1] for r in sorok]
        np = _numpy() if self.motor != "python" else None
        if np is not None:
            m = (np.frombuffer(b"".join(r[2] for r in sorok), dtype="float32").reshape(len(sorok), -1)
                 if sorok else np.zeros((0, 0), dtype="float32"))
        else:
            m = [array("f", r[2]) for r in sorok]
        self._gyorsitotar = (kulcs, ids, utak, m)
        return self._gyorsitotar

    def keres(self, vektor, k: int = 50, utak: set[str] | None = None) -> list[tuple[int, float]]:
        """A `k` legközelebbi darab koszinusz-hasonlóság szerint: `[(darab-azonosító, hasonlóság)…]`, csökkenően (azonos
        pontnál az azonosító dönt). `utak`: csak ezekben a jegyzetekben (a lexikai szűrő halmaza)."""
        q = normal(vektor)
        with self._zar:
            if self._vec is not None and utak is None:
                return self._keres_vec(q, k)
            _, ids, uts, m = self._matrix()
            if not ids:
                return []
            if len(q) != (m.shape[1] if hasattr(m, "shape") else len(m[0])):
                raise ValueError("a kérdés-vektor dimenziója nem a tár dimenziója")
            if hasattr(m, "shape"):
                np = _numpy()
                pont = (m @ np.frombuffer(q.tobytes(), dtype="float32")).tolist()
            else:
                pont = [sum(a * b for a, b in zip(sor, q)) for sor in m]
        jeloltek = [(ids[i], float(p)) for i, p in enumerate(pont) if utak is None or uts[i] in utak]
        jeloltek.sort(key=lambda x: (-x[1], x[0]))
        return [(i, round(p, 6)) for i, p in jeloltek[:k]]

    def jegyzet_hasonlosag(self, ut: str) -> dict[str, float] | None:
        """C25c (hasonló jegyzetek, modell nélkül): a jegyzet darabvektorainak normált átlaga (a „jegyzet-vektor”) és minden
        tárolt darab koszinusza, jegyzetenként a legjobb darabé: `{út: hasonlóság}` (a jegyzet maga is benne). `None`, ha a
        jegyzetnek nincs vektora a tárban (még nem dolgozta fel a vektorindex) — ilyenkor modell sem töltődik."""
        with self._zar:
            _, ids, uts, m = self._matrix()
            sajat = [i for i, u in enumerate(uts) if u == ut]
            if not sajat:
                return None
            if hasattr(m, "shape"):
                np = _numpy()
                q = m[sajat].mean(axis=0)
                n = float(np.linalg.norm(q))
                if n <= 0:
                    return None
                pont = (m @ (q / n)).tolist()
            else:
                dim = len(m[0])
                q = normal([sum(m[i][j] for i in sajat) / len(sajat) for j in range(dim)])
                if not any(q):
                    return None
                pont = [sum(a * b for a, b in zip(sor, q)) for sor in m]
        ki: dict[str, float] = {}
        for u, p in zip(uts, pont):
            if p > ki.get(u, -2.0):
                ki[u] = p
        return {u: round(float(p), 6) for u, p in ki.items()}

    def jegyzet_hash(self, ut: str) -> str | None:
        """A jegyzet hash-e a vektorozáskor (az index hash-ével összevetve: elavult-e a vektora)."""
        with self._zar:
            r = self._c.execute("SELECT hash FROM jegyzet WHERE ut = ?", (ut,)).fetchone()
        return r[0] if r else None

    def _keres_vec(self, q: array, k: int) -> list[tuple[int, float]]:
        sorok = self._c.execute("SELECT rowid, distance FROM vec_darab WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                                (q.tobytes(), int(k))).fetchall()
        return [(int(r), round(1.0 - float(d), 6)) for r, d in sorok]

    def allapot(self) -> dict:
        with self._zar:
            j, d = self._c.execute("SELECT (SELECT count(*) FROM jegyzet), (SELECT count(*) FROM darab)").fetchone()
        return {"van": True, "motor": self.motor, "jegyzetek": j, "darabok": d, "modell": self.modell_kulcs(),
                "meret": self.ut.stat().st_size if self.ut.exists() else 0}
