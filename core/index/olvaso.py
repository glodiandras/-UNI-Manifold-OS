"""A vault-index olvasó rétege (C33, T172): a lekérdezések, a nyilvános tranzakciós `olvaso()` kontextus, a nehéz olvasók
közös zára és a generáció szerinti gyorsítótárak.

Az `Index` (`indexelo.py`) az író: szál, figyelő, szinkron, alkalmazás. Az `IndexOlvaso` az olvasó: minden API-lekérdezés
itt él, és a kiszervezett modulok (`graf_meta`, `feladatok`, a higiénia, az említések, a hibrid kereső) is a nyilvános
`olvaso()`-t használják (a privát `_olvaso` csak álnév a régi hívóknak).

- **`olvaso(tranzakcio=True)`**: egy kapcsolat a készletből; alapból egy `BEGIN`/`COMMIT` olvasó-tranzakcióban, így a több
  utasításos olvasás (jegyzet, visszahivatkozás, beágyazás, keresés) egy pillanatképet lát a WAL-ban — egy közbenső írás nem
  szakítja el (T172, A2-index-8).
- **`olvaso(nehez=True)`**: a nehéz olvasók (gráf, graf-meta, Bases-sorok, fa, említések) közös zára (T070): párhuzamosan a
  GIL és az sqlite3 lépésenkénti elengedése torlódott (4 párhuzamos `bazis_sorok` 32 → 668 ms; közös zárral 138 ms).
- **Generációk**: a `generacio` minden index-írás után nő (C12); a `szerkezet_generacio` csak akkor, ha a gráf vagy a graf-meta
  változhatott (új/eltűnt fájl, egy fájl linkjei, címkéi, tulajdonságai, a `lemez_ut`) — a tartalmi mentés nem érvényteleníti
  a gráf gyorsítótárát. A `valtozasok_ota(gen)` a generációnkénti változásnaplóból adja a változott utakat (a Bases `Tabla`
  inkrementális frissítése; `None`: teljes újraolvasás kell).
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import os
import queue
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path

from .. import atirat, mediatipus
from ..vaultio import Invalid, NotFound
from . import elemzo, kereses, kizaras, linkek, tar
from .feloldas import nfc
from ..hibakod import kodol

VALTOZAS_NAPLO = 256            # ennyi generáció változásait őrzi a napló (a Bases inkrementális frissítéséhez)
POOL_MAX = 8                    # ennyi olvasó kapcsolat marad nyitva a készletben


def _hajtogat(s: str) -> str:
    """Ékezet- és kisbetű-független alak a keresésekhez (NFD, kombináló jelek nélkül, casefold)."""
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch)).casefold()


class NemKesz(RuntimeError):
    """Az index még nem épült fel (503)."""


@contextlib.contextmanager
def tranzakcioban(c, tranzakcio: bool = True):
    """Egy olvasó kapcsolat `BEGIN`/`COMMIT` keretben (a megszakított lekérdezés — regex-időkorlát — már visszagörgethette:
    a lezárás ezt tűri)."""
    if tranzakcio and not c.in_transaction:
        c.execute("BEGIN")
    try:
        yield c
    finally:
        if c.in_transaction:
            with contextlib.suppress(Exception):
                c.execute("COMMIT")


def fajl_olvaso(db_ut: Path):
    """Csak olvasó kontextus-gyár egy meglévő `vault.sqlite`-hoz (a CLI-k: `mos higienia`, `mos kereses`), író nélkül."""
    @contextlib.contextmanager
    def olvaso(tranzakcio: bool = True, nehez: bool = False):
        if not db_ut.exists():
            raise NemKesz("az index még nem épült fel (indítsd el a core-t)")
        c = tar.nyit(db_ut)
        try:
            with tranzakcioban(c, tranzakcio):
                yield c
        finally:
            c.close()
    return olvaso


class IndexOlvaso:
    """Az index olvasó fele. Az `Index.__init__` hívja az `_olvaso_init`-et; az attribútumokat (`db_ut`, `root`, `cfg`,
    `feloldo`, `_fl_lock`, `allapot_d`, `max_talalat`, `regex_idokorlat`, `tipusok`, `pdf_kinyero`) az író tölti."""

    def _olvaso_init(self) -> None:
        self._pool: queue.LifoQueue = queue.LifoQueue()      # (készlet-generáció, kapcsolat) párok
        self._pool_gen = 0              # a `_pool_urit` növeli: a régebbi generáció kapcsolata nem kerül vissza (F5)
        self._nehez_zar = threading.RLock()
        self._gen_zar = threading.Lock()
        self.generacio = 0              # minden írás (új/változott/törölt fájl, stat-változás, típusváltás) után nő (C12)
        self.szerkezet_generacio = 0    # csak a gráfot / graf-metát érintő változásra nő (C33, T070)
        self._valtozasok: collections.deque = collections.deque(maxlen=VALTOZAS_NAPLO)
        self._gyorsitotar: dict[str, tuple[tuple, bytes, str]] = {}
        self._gyorsitotar_zar = threading.Lock()

    # ---------------------------------------------------------------- generációk

    def _uj_generacio(self, utak=None, szerkezeti: bool = False) -> None:
        """Egy index-írás vége (az író szál hívja a COMMIT után): `utak` a változott (NFC) utak, `None`: ismeretlen
        hatókör (a Bases teljes újraolvasása kell); `szerkezeti`: a gráf / graf-meta változhatott."""
        with self._gen_zar:
            self.generacio += 1
            self._valtozasok.append((self.generacio, None if utak is None else frozenset(utak)))
            if szerkezeti:
                self.szerkezet_generacio += 1

    def valtozasok_ota(self, gen: int) -> tuple[int, set[str] | None]:
        """`(a mostani generáció, a `gen` óta változott utak)`; az utak `None`, ha a napló nem fedi le a `gen` óta eltelt
        időt, vagy közben ismeretlen hatókörű írás volt (típusváltás, új/eltűnt fájl)."""
        with self._gen_zar:
            most = self.generacio
            if gen == most:
                return most, set()
            if gen > most or not self._valtozasok or self._valtozasok[0][0] > gen + 1:
                return most, None
            ki: set[str] = set()
            for g, utak in self._valtozasok:
                if g <= gen:
                    continue
                if utak is None:
                    return most, None
                ki |= utak
            return most, ki

    def _gyorsitott(self, kulcs: str, epit) -> tuple[bytes, str]:
        """Egy JSON-válasz (bájtok) és az ETag-je a szerkezeti generáció szerint gyorsítótárazva: a tartalmi mentés után a
        gráf nem épül újra, és ha a tartalma változatlan, az ETag is az (a felület 304-et kap, nem épít újra)."""
        with self._gen_zar:
            g = (self.szerkezet_generacio, kizaras.jel(self.cfg))        # a kizárási lista is érvényteleníti (14-appearance-06)
        t = self._gyorsitotar.get(kulcs)
        if t is not None and t[0] == g:
            return t[1], t[2]
        with self._gyorsitotar_zar:
            t = self._gyorsitotar.get(kulcs)
            if t is not None and t[0] == g:
                return t[1], t[2]
            b = json.dumps(epit(), ensure_ascii=False).encode("utf-8")
            etag = '"' + hashlib.sha1(b).hexdigest()[:24] + '"'
            self._gyorsitotar[kulcs] = (g, b, etag)
            return b, etag

    # ---------------------------------------------------------------- kapcsolatok

    @contextlib.contextmanager
    def olvaso(self, tranzakcio: bool = True, nehez: bool = False):
        """Egy olvasó kapcsolat a készletből (nyilvános, a kiszervezett modulok is ezt használják). `tranzakcio`: egy
        `BEGIN`/`COMMIT` olvasó-tranzakció (egy pillanatkép a WAL-ban); `nehez`: a nehéz olvasók közös zára (T070)."""
        zar = self._nehez_zar if nehez else contextlib.nullcontext()
        with zar:
            gen = self._pool_gen
            try:
                gen, c = self._pool.get_nowait()
            except queue.Empty:
                if not self.db_ut.exists():
                    raise NemKesz("az index még nem épült fel") from None
                c = tar.nyit(self.db_ut)
                # F9 (audit 07 §7): the writer creates the file before its migrations commit (one step at a time); a reader
                # opening it in that window found no tables (`no such table: fts` → 500). Until the schema is current the index
                # is "not ready" (503), as before the file existed.
                if c.execute("PRAGMA user_version").fetchone()[0] < tar.VERZIO:
                    c.close()
                    raise NemKesz("az index még nem épült fel")
            try:
                with tranzakcioban(c, tranzakcio):
                    yield c
            except sqlite3.DatabaseError as e:
                # F9 (audit 08 §4): a page damaged in the MIDDLE of the file passes the cheap open-time probe, and the writer
                # only notices it if it writes there — the readers kept answering 500 ("malformed") indefinitely. A reader that
                # hits corruption now asks the writer to set the file aside and rebuild (once per pool generation), and answers 503.
                if not tar.serult_hiba(e):
                    raise
                self._olvaso_serult(gen, e)
                raise NemKesz("az index sérült; újraépül") from e
            finally:
                # F5 (2026-10-14): a készlet ürítése (a sérült index félretétele, leállás) után a korábban kiadott kapcsolat
                # a régi (félretett) fájlra mutat — nem kerül vissza a készletbe, különben tartósan régi találatokat adna
                if gen == self._pool_gen and self._pool.qsize() < POOL_MAX:
                    self._pool.put((gen, c))
                else:
                    c.close()

    _olvaso = olvaso                    # a régi (privát) név a meglévő hívóknak; új kód az `olvaso`-t használja

    def _olvaso_serult(self, gen: int, hiba: BaseException) -> None:
        """A reader hit a damaged index (F9): the writer (`Index`) overrides this to set the file aside and rebuild."""

    def _pool_urit(self) -> None:
        """A készlet kapcsolatai zárva, és új készlet-generáció: a most kiadott kapcsolatok visszaadáskor záródnak (F5). A sérült
        index cseréje az új fájl megnyitása után is meghívja: az ürítés és a csere között nyitott kapcsolat is a régire mutat."""
        self._pool_gen += 1
        while True:
            try:
                self._pool.get_nowait()[1].close()
            except queue.Empty:
                break

    def allapot(self) -> dict:
        a = {**self.allapot_d, "db": str(self.db_ut.name)}
        k = self.pdf_kinyero
        a["pdf_szoveg"] = {**a["pdf_szoveg"], "varakozik": k.varakozik() if k is not None else 0,
                           "kinyero": k is not None, "hiba": k.hiba if k is not None else None}
        return a

    def kizaras_valtozott(self) -> None:
        """A kizárási lista (14-appearance-06) változott: a fa, a gráf, a kereső és a gyorsváltó újratölt. Az index tartalma
        nem változik; a gráf gyorsítótára a lista jele szerint magától érvénytelen."""
        pub = getattr(self, "publish", None)
        if pub is not None:
            pub({"tipus": "index", **self.allapot()})

    def fa(self) -> dict:
        kiz = kizaras.betolt(self.cfg)
        with self.olvaso(nehez=True) as c:
            mappak = [r[0] for r in c.execute("SELECT ut FROM mappa WHERE torolve IS NULL ORDER BY ut")]
            fajlok = [{"ut": r[0], "tipus": r[1], "meret": r[2], "mtime": r[3] / 1e9 if r[3] else None,
                       "ctime": r[4] / 1e9 if r[4] else None}     # F11: valódi születési idő, vagy None (sosem mtime)
                      for r in c.execute("SELECT ut, tipus, meret, mtime_ns, ctime_ns FROM fajl WHERE torolve IS NULL ORDER BY ut")]
        if kiz:         # a kizárt fájl a fában marad (halványan); a többi nézet a jelzőből szűr
            for f in fajlok:
                if kiz.kizart(f["ut"]):
                    f["kizart"] = True
        return {"mappak": mappak, "fajlok": fajlok, "kesz": self.allapot_d["kesz"]}

    @staticmethod
    def _ut(rp) -> str:
        if not isinstance(rp, str) or not rp.strip():
            raise kodol(Invalid("hiányzó út"), "index.olvaso.hianyzo_ut")
        rp = nfc(rp).replace("\\", "/").strip().strip("/")
        if "\x00" in rp or any(r in ("", ".", "..") for r in rp.split("/")):
            raise kodol(Invalid(f"érvénytelen út: {rp}"), "index.olvaso.ervenytelen_ut_rp", {"rp": rp})
        return rp

    def _sor(self, c, rp: str):
        r = c.execute("SELECT * FROM fajl WHERE ut = ? AND torolve IS NULL", (rp,)).fetchone()
        if r is None:
            raise kodol(NotFound(f"nincs ilyen fájl az indexben: {rp}"), "index.olvaso.nincs_ilyen_fajl_indexben_rp", {"rp": rp})
        return r

    def jegyzet(self, rp) -> dict:
        rp = self._ut(rp)
        with self.olvaso() as c:
            f = self._sor(c, rp)
            fid = f["id"]

            def sorok(sql):
                return [dict(r) for r in c.execute(sql, (fid,))]

            tul = [{"kulcs": r["kulcs"], "tipus": r["tipus"], "ertek": json.loads(r["ertek"]),
                    "ervenyes": bool(r["ervenyes"])}
                   for r in c.execute("SELECT * FROM tulajdonsag WHERE fajl_id = ? ORDER BY sorrend", (fid,))]
            linkek = [{k: r[k] for k in ("fajta", "cel_nyers", "alcel", "alias", "tulajdonsag", "csomopont", "sor",
                                         "oszlop", "hossz", "cel")} | {"beagyazas": bool(r["beagyazas"])}
                      for r in c.execute("SELECT * FROM link WHERE forras_id = ? ORDER BY sorrend", (fid,))]
            feladatok = [{"sor": r["sor"], "allapot": r["allapot"], "szoveg": r["szoveg"], "behuzas": r["behuzas"],
                          "datumok": json.loads(r["datumok"])}
                         for r in c.execute("SELECT * FROM feladat WHERE fajl_id = ? ORDER BY sor", (fid,))]
            return {
                "ut": f["ut"], "tipus": f["tipus"], "meret": f["meret"], "mtime": f["mtime_ns"] / 1e9,
                "ctime": f["ctime_ns"] / 1e9 if f["ctime_ns"] else None, "hash": f["hash"],
                "fm_nyers": f["fm_nyers"], "fm_hiba": f["fm_hiba"], "canvas_hiba": f["canvas_hiba"],
                "tulajdonsagok": tul, "aliasok": json.loads(f["aliasok"] or "[]"),
                "fejezetek": sorok("SELECT szint, szoveg, sor FROM fejezet WHERE fajl_id = ? ORDER BY sor"),
                "blokkok": sorok("SELECT azon, sor, kezdo_sor FROM blokk WHERE fajl_id = ? ORDER BY sor"),
                "linkek": linkek,
                "cimkek": sorok("SELECT cimke, forras, sor FROM cimke WHERE fajl_id = ? ORDER BY rowid"),
                "feladatok": feladatok,
                "kepletek": [dict(r) | {"blokk": bool(r["blokk"])} for r in c.execute(
                    "SELECT sor, sor_veg, kezd, veg, blokk, forras FROM keplet WHERE fajl_id = ? ORDER BY kezd", (fid,))],
                "kodblokkok": sorok("SELECT nyelv, sor_kezd, sor_veg FROM kodblokk WHERE fajl_id = ? ORDER BY sor_kezd"),
            }

    @staticmethod
    def _tartalom(c, fid: int) -> str:
        r = c.execute("SELECT tartalom FROM fts WHERE rowid = ?", (fid,)).fetchone()
        return r[0] if r else ""

    def visszahivatkozasok(self, rp) -> dict:
        rp = self._ut(rp)
        with self.olvaso() as c:
            self._sor(c, rp)
            out: dict[str, dict] = {}
            szovegek: dict[int, list[str]] = {}
            for r in c.execute("SELECT f.ut AS forras, f.id AS fid, l.* FROM link l JOIN fajl f ON f.id = l.forras_id "
                               "WHERE l.cel = ? AND f.ut != ? ORDER BY f.ut, l.sorrend", (rp, rp)):
                if r["fid"] not in szovegek:
                    szovegek[r["fid"]] = self._tartalom(c, r["fid"]).split("\n")
                sorok = szovegek[r["fid"]]
                kornyezet = sorok[r["sor"] - 1][:400] if r["sor"] and r["sor"] <= len(sorok) else None
                out.setdefault(r["forras"], {"ut": r["forras"], "linkek": []})["linkek"].append({
                    "fajta": r["fajta"], "sor": r["sor"], "oszlop": r["oszlop"], "hossz": r["hossz"], "alcel": r["alcel"],
                    "alias": r["alias"], "beagyazas": bool(r["beagyazas"]), "tulajdonsag": r["tulajdonsag"],
                    "csomopont": r["csomopont"], "kornyezet": kornyezet})
        return {"ut": rp, "forrasok": list(out.values())}

    def emlitesek(self, rp, limit: int | None = None) -> dict:
        """Linkeletlen említések: a jegyzet neve (és `aliases`-ai) a többi jegyzetben, szóhatáron,
        kis-nagybetűtől függetlenül, ékezetre érzékenyen; link, kód és frontmatter nélkül."""
        rp = self._ut(rp)
        limit = limit or self.max_talalat
        kiz = kizaras.betolt(self.cfg)
        with self.olvaso(nehez=True) as c:
            f = self._sor(c, rp)
            nevek = [f["nev"].rsplit(".", 1)[0] if f["tipus"] in ("md", "canvas", "base") else f["nev"]]
            nevek += [a for a in json.loads(f["aliasok"] or "[]") if isinstance(a, str)]
            nevek = [nfc(n).strip() for n in dict.fromkeys(nevek) if n and n.strip()]
            jeloltek: dict[int, str] = {}
            for n in nevek:
                q = kereses.fts_kifejezes(n)
                if not q:
                    continue
                for r in c.execute("SELECT f.id, f.ut FROM fts JOIN fajl f ON f.id = fts.rowid "
                                   "WHERE fts.tartalom MATCH ? AND f.torolve IS NULL AND f.tipus = 'md'", (q,)):
                    if r[1] != rp and not kiz.kizart(r[1]):          # a kizárt jegyzet nem javasol említést (14-appearance-06)
                        jeloltek[r[0]] = r[1]
            mintak = [re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)", re.I) for n in nevek]
            out = []
            for fid, ut in sorted(jeloltek.items(), key=lambda x: x[1]):
                talalat = kereses.emlites_talalatok(self._tartalom(c, fid), mintak)
                if talalat:
                    out.append({"ut": ut, "talalatok": talalat})
                    if len(out) >= limit:
                        break
        return {"ut": rp, "nevek": nevek, "forrasok": out}

    # ---------------------------------------------------------------- linkek (C10)

    def _kesz_vagy_hiba(self) -> None:
        if not self.allapot_d["kesz"]:
            raise NemKesz("az index még nem épült fel")

    def feloldas(self, forras, celok) -> list[dict]:
        """Link-célok feloldása a `forras` jegyzetből — **a** feloldás (L42), a felület ezt kérdezi. Ugyanazt a
        `Feloldo`-t használja, mint az index és a gráf. `celok`: nyers cél-szövegek (a `[[` utáni rész)."""
        self._kesz_vagy_hiba()
        forras = self._ut(forras)
        if not isinstance(celok, list) or len(celok) > 500 or not all(isinstance(c, str) for c in celok):
            raise kodol(Invalid("a celok legfeljebb 500 szöveg listája"), "index.olvaso.celok_legfeljebb_500_szoveg_listaja")
        ki = []
        with self._fl_lock:
            for cel in celok:
                hit, _, tobb = self.feloldo.resolve(cel, forras)
                ki.append({"cel": cel, "ut": hit, "tobbertelmu": tobb})
        return ki

    def link_cel(self, ut, forras, alcel=None, hianyzo=None) -> dict:
        """A fájl link-célként beírandó szövege a `forras`-ból a beállított „New link format” szerint (`link_formatum`:
        `rovid` = a legrövidebb egyértelmű, `linkek.rovid_cel`; `relativ`; `abszolut` = vault-gyökerű út), mindig a feloldóval
        ellenőrizve. Az `alak` a „Use [[Wikilinks]]” (`wikilinkek`) szerint `wiki` | `md`; az `md` a kész md-link célja
        (kódolva, `.md`-vel, a `alcel` horgonnyal) — a felület ebből épít linket, saját kódolási szabálya nincs."""
        self._kesz_vagy_hiba()
        if alcel is not None and not isinstance(alcel, str):
            raise kodol(Invalid("az alcel szöveg kell"), "index.olvaso.alcel_szoveg")
        if not ut and isinstance(hianyzo, str) and hianyzo.strip():
            # még nem létező cél (`[[Új jegyzet]]`): nincs fájl, amit rövidíteni lehetne — a beállítás és a kódolás jön
            self._ut(forras)
            fajlok = self.cfg.section("beallitasok").get("fajlok", {})
            cel = hianyzo.strip()
            ismert_kit = os.path.splitext(cel)[1].lower() in mediatipus.MEDIA_TIPUS or cel.lower().endswith((".canvas", ".base"))
            return {"ut": None, "cel": cel, "alak": "md" if fajlok.get("wikilinkek", True) is False else "wiki",
                    "md": linkek.md_cel_irasra(cel, cel if ismert_kit else cel + ".md", alcel)}
        ut, forras = self._ut(ut), self._ut(forras)
        with self._fl_lock:
            if ut not in self.feloldo.fileset:
                raise kodol(NotFound(f"nincs ilyen fájl az indexben: {ut}"), "index.olvaso.nincs_ilyen_fajl_indexben_ut", {"ut": ut})
            fajlok = self.cfg.section("beallitasok").get("fajlok", {})
            cel = linkek.cel_forma(self.feloldo, ut, forras, fajlok.get("link_formatum", "rovid"))
            return {"ut": ut, "cel": cel, "alak": "md" if fajlok.get("wikilinkek", True) is False else "wiki",
                    "md": linkek.md_cel_irasra(cel, ut, alcel)}

    def fejezetek_mind(self, q, limit: int | None = None) -> dict:
        """Az összes jegyzet fejezetei a `[[##` kereséshez: a `q` szavai (ékezet- és kisbetű-függetlenül) a fejezet szövegében
        vagy a jegyzet útjában; üres `q`: a legutóbb módosított jegyzetek fejezetei. A fejezet-kezdetű találat előre."""
        self._kesz_vagy_hiba()
        limit = max(1, min(int(limit or 200), 1000))
        szavak = [_hajtogat(x) for x in str(q or "").split() if x]
        talalatok: list[tuple[int, dict]] = []
        with self.olvaso() as c:
            for ut, szint, szoveg, sor in c.execute(
                    "SELECT f.ut, h.szint, h.szoveg, h.sor FROM fejezet h JOIN fajl f ON f.id = h.fajl_id "
                    "WHERE f.torolve IS NULL AND f.tipus = 'md' AND h.szoveg IS NOT NULL AND trim(h.szoveg) != '' "
                    "ORDER BY f.mtime_ns DESC, f.ut, h.sor"):
                if szavak:
                    h = _hajtogat(szoveg)
                    teljes = h + " " + _hajtogat(ut)
                    if not all(sz in teljes for sz in szavak):
                        continue
                    rang = 0 if h.startswith(szavak[0]) else 1
                else:
                    rang = 0
                talalatok.append((rang, {"ut": ut, "szint": szint, "szoveg": szoveg, "sor": sor}))
                if not szavak and len(talalatok) >= limit:
                    break
        talalatok.sort(key=lambda x: x[0])        # stabil: azonos rangon marad a legutóbbi-először sorrend
        return {"fejezetek": [x[1] for x in talalatok[:limit]]}

    def feloldatlan_szovegek(self, limit: int | None = None) -> dict:
        """A vaultban használt, még nem létező link-célok (feloldatlan wikilinkek, beágyazás nélkül), gyakoriság szerint."""
        self._kesz_vagy_hiba()
        limit = max(1, min(int(limit or 200), 1000))
        with self.olvaso() as c:
            sorok = c.execute(
                "SELECT trim(l.cel_nyers) AS cel, count(*) AS db FROM link l JOIN fajl f ON f.id = l.forras_id "
                "WHERE f.torolve IS NULL AND l.cel IS NULL AND l.fajta = 'wiki' AND l.beagyazas = 0 "
                "AND trim(l.cel_nyers) != '' GROUP BY trim(l.cel_nyers) ORDER BY db DESC, cel LIMIT ?", (limit,)).fetchall()
        return {"szovegek": [{"cel": r[0], "db": r[1]} for r in sorok]}

    def kimeno_emlitesek(self, rp, motor, limit: int | None = None) -> dict:
        """A jegyzet **kimenő** linkeletlen említései: a többi jegyzet neve/aliasa ebben a (mentett) szövegben, jegyzetenként
        csoportosítva (a „Kimenő linkek” panelnek). Az Asszisztens ugyanazon lexikai motorja (`motor.keres`), de a panel
        nem az Asszisztens kapcsolóján múlik; a többértelmű egyezés kimarad (nem dönthető el, melyik jegyzetre linkelne)."""
        self._kesz_vagy_hiba()
        rp = self._ut(rp)
        with self.olvaso(nehez=True) as c:
            f = self._sor(c, rp)
            if f["tipus"] != "md":
                return {"ut": rp, "forrasok": []}
            szoveg = self._tartalom(c, f["id"])
        sorok = szoveg.split("\n")
        csoport: dict[str, list[dict]] = {}
        kiz = kizaras.betolt(self.cfg)
        for e in motor.keres(rp, szoveg, limit)["emlitesek"]:
            if e["tobbertelmu"] or not e["cel"] or kiz.kizart(e["cel"]):
                continue
            sor = sorok[e["sor"] - 1] if 0 < e["sor"] <= len(sorok) else ""
            csoport.setdefault(e["cel"], []).append({"sor": e["sor"], "oszlop": e["oszlop"], "hossz": e["veg"] - e["kezd"],
                                                     "szoveg": sor[:400], "emlitett": e["szoveg"]})
        return {"ut": rp, "forrasok": [{"ut": cel, "talalatok": t} for cel, t in sorted(csoport.items())]}

    def aliasok(self) -> dict:
        """Az aliasos fájlok `aliases`-ai: `{ut: [alias]}`."""
        kiz = kizaras.betolt(self.cfg)
        with self.olvaso() as c:
            ki = {}
            for ut, a in c.execute("SELECT ut, aliasok FROM fajl WHERE torolve IS NULL AND aliasok IS NOT NULL "
                                   "AND aliasok != '[]' ORDER BY ut"):
                if kiz.kizart(ut):
                    continue
                lista = [x for x in json.loads(a) if isinstance(x, str) and x.strip()]
                if lista:
                    ki[ut] = lista
        return {"aliasok": ki}

    _IKON_KULCSOK = ("icon", "cover")
    _FAJL_ALAK = re.compile(r"\.[A-Za-z0-9]{2,5}$")

    def ikonok(self) -> dict:
        """Az `icon`/`cover` tulajdonságú jegyzetek (C11b): `{ut: {icon|cover: {ertek, ut}}}`; az `ut` a feloldott
        képfájl (vault-út), ha az érték wikilink vagy fájlnév-alakú (a feloldás a core-é, L42), különben `None`
        (emoji, szöveg, külső URL). Az `Icon`/`Cover` írásmód nem számít."""
        self._kesz_vagy_hiba()
        sorok = []
        with self.olvaso() as c:
            for ut, kulcs, ertek in c.execute(
                    "SELECT f.ut, t.kulcs, t.ertek FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND lower(t.kulcs) IN ('icon', 'cover') ORDER BY f.ut, t.sorrend"):
                v = json.loads(ertek)
                if isinstance(v, str) and v.strip():
                    sorok.append((ut, kulcs.lower(), v.strip()))
        ki: dict[str, dict] = {}
        with self._fl_lock:
            for ut, kulcs, v in sorok:
                cel = re.sub(r"^!?\[\[(.*)\]\]$", r"\1", v).split("|", 1)[0].split("#", 1)[0].strip()
                kep = None
                if cel != v or self._FAJL_ALAK.search(cel):
                    if not re.match(r"^[a-z][a-z0-9+.-]*://", cel, re.I):
                        kep = self.feloldo.resolve(cel, ut)[0]
                ki.setdefault(ut, {})[kulcs] = {"ertek": v, "ut": kep}
        return {"ikonok": ki}

    def cimkek(self) -> dict:
        """A címkefa adata (C11b): minden címke és minden szülője a `/` mentén. `db`: a pontosan ezt a címkét viselő
        jegyzetek száma, `ossz`: ezé és a gyerekeié (egy jegyzet egyszer számít). A név a leggyakoribb írásmód."""
        valtozat: dict[str, dict[str, int]] = {}
        fajlok: dict[str, set[int]] = {}
        pontos: dict[str, set[int]] = {}
        with self.olvaso(nehez=True) as c:
            for fid, cimke, kis in c.execute(
                    "SELECT c.fajl_id, c.cimke, c.kis FROM cimke c JOIN fajl f ON f.id = c.fajl_id "
                    "WHERE f.torolve IS NULL"):
                szegmens, nagy = kis.split("/"), cimke.split("/")
                pontos.setdefault(kis, set()).add(fid)
                for i in range(1, len(szegmens) + 1):
                    k = "/".join(szegmens[:i])
                    fajlok.setdefault(k, set()).add(fid)
                    v = valtozat.setdefault(k, {})
                    n = "/".join(nagy[:i])
                    v[n] = v.get(n, 0) + 1
        return {"cimkek": [{"cimke": max(v.items(), key=lambda x: (x[1], x[0]))[0], "kis": k,
                            "db": len(pontos.get(k, ())), "ossz": len(fajlok[k])}
                           for k, v in sorted(valtozat.items())]}

    def ertekkeszlet_hasznalat(self) -> dict:
        """A séma-értékkészletes mezők (címke, Status) vaultbeli használata egy tranzakcióban, a tulajdonság-ellenőrzés élő
        értékkészletéhez (CX-002): `{"tags": {kulcs: {db, utak}}, "status": {...}}`. A címke kulcsa a kisbetűs (casefold), `#`
        nélküli NFC alak, és a frontmatter `Tags` mellett a szövegbeli `#címke` is számít (az Obsidian mindkettőt címkének
        veszi); a Status kulcsa a pontos NFC szöveg. `db`: a jegyzetek száma; `utak`: legfeljebb két jegyzet útja — elég
        ahhoz, hogy a hívó a vizsgált jegyzet saját előfordulását kizárja."""
        self._kesz_vagy_hiba()
        tags: dict[str, set[str]] = {}
        status: dict[str, set[str]] = {}
        with self.olvaso() as c:
            for ut, cimke in c.execute("SELECT f.ut, c.cimke FROM cimke c JOIN fajl f ON f.id = c.fajl_id "
                                       "WHERE f.torolve IS NULL AND c.cimke IS NOT NULL"):
                k = nfc(cimke).removeprefix("#").strip().casefold()
                if k:
                    tags.setdefault(k, set()).add(ut)
            for ut, kulcs, ertek in c.execute(
                    "SELECT f.ut, t.kulcs, t.ertek FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND t.kulcs IS NOT NULL"):
                if nfc(kulcs).casefold() != "status":
                    continue
                try:
                    v = json.loads(ertek)
                except (TypeError, ValueError):
                    continue
                if isinstance(v, str) and v.strip():
                    status.setdefault(nfc(v).strip(), set()).add(ut)

        def tomor(d):
            return {k: {"db": len(v), "utak": sorted(v)[:2]} for k, v in d.items()}
        return {"tags": tomor(tags), "status": tomor(status)}

    def tulajdonsag_kulcsok(self) -> list[dict]:
        """A vaultban használt tulajdonság-kulcsok jegyzetszámmal (a tulajdonság-javaslatok forrása): `[{kulcs, db}]`,
        kis-nagybetűtől függetlenül összevonva (a név a leggyakoribb írásmód), csökkenő `db` szerint."""
        self._kesz_vagy_hiba()
        szam: dict[str, dict[str, set[int]]] = {}
        with self.olvaso() as c:
            for fid, kulcs in c.execute(
                    "SELECT t.fajl_id, t.kulcs FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND t.kulcs IS NOT NULL"):
                szam.setdefault(nfc(kulcs).casefold(), {}).setdefault(nfc(kulcs), set()).add(fid)
        ki = []
        for v in szam.values():
            nev = max(v.items(), key=lambda x: (len(x[1]), x[0]))[0]
            ki.append({"kulcs": nev, "db": len(set().union(*v.values()))})
        return sorted(ki, key=lambda x: (-x["db"], x["kulcs"].lower()))

    def tulajdonsag_ertekek(self, kulcs: str, limit: int = 300) -> list[dict]:
        """Egy kulcs (kis-nagybetűtől függetlenül) vaultban használt szöveg- és számértékei jegyzetszámmal: `[{ertek, db}]`.
        A lista-érték elemei külön számítanak; az üres, a logikai és az összetett érték kimarad. Csökkenő `db`, legfeljebb
        `limit` elem."""
        self._kesz_vagy_hiba()
        if not isinstance(kulcs, str) or not kulcs.strip():
            raise kodol(Invalid("hiányzó kulcs"), "index.olvaso.hianyzo_kulcs")
        cel = nfc(kulcs.strip()).casefold()             # az SQLite `lower()`-je csak ASCII: az összevetés itt történik
        szam: dict[str, set[int]] = {}
        with self.olvaso() as c:
            for fid, k, ertek in c.execute(
                    "SELECT t.fajl_id, t.kulcs, t.ertek FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND t.kulcs IS NOT NULL"):
                if nfc(k).casefold() != cel:
                    continue
                try:
                    v = json.loads(ertek)
                except (TypeError, ValueError):
                    continue
                for x in v if isinstance(v, list) else [v]:
                    if isinstance(x, bool) or not isinstance(x, (str, int, float)):
                        continue
                    s = nfc(str(x)).strip()
                    if s:
                        szam.setdefault(s, set()).add(fid)
        ki = sorted(({"ertek": k, "db": len(v)} for k, v in szam.items()), key=lambda x: (-x["db"], x["ertek"].lower()))
        return ki[:max(0, int(limit))]

    _BEAGYAZAS_TIPUS = {"md": "jegyzet", "kep": "kep", "video": "video", "hang": "hang", "pdf": "pdf",
                        "canvas": "canvas", "base": "base"}

    def beagyazas(self, forras, cel, alcel=None) -> dict:
        """Egy beágyazás/előnézet tartalma: a feloldott cél típusa, és jegyzetnél a (frontmatter nélküli) szöveg
        — a fejezet vagy a `^blokk` szelete, ha van `alcel`. A média-horgonyok (`page=`, `t=`) a felületé:
        itt az `alcel` csak visszamegy. Hibás fejezet/blokk: `alcel_hiba`, szöveg nélkül."""
        self._kesz_vagy_hiba()
        forras = self._ut(forras)
        if not isinstance(cel, str) or not cel.strip():
            raise kodol(Invalid("hiányzó cél"), "index.olvaso.hianyzo_cel")
        with self._fl_lock:
            hit, _, tobb = self.feloldo.resolve(cel, forras)
        if not hit:
            return {"tipus": "nincs", "cel": cel}
        with self.olvaso() as c:
            f = self._sor(c, hit)
            tipus = self._BEAGYAZAS_TIPUS.get(f["tipus"], "egyeb")
            ki = {"tipus": tipus, "ut": hit, "tobbertelmu": bool(tobb), "alcel": alcel or None}
            if tipus != "jegyzet":
                return ki
            tartalom = self._tartalom(c, f["id"])
            sorok = tartalom.split("\n")
            fm = elemzo.FM_RE.match(tartalom)
            fm_sorok = tartalom[:fm.end()].count("\n") if fm else 0
            kezd, veg = fm_sorok + 1, len(sorok)
            if alcel and alcel.strip():
                alcel = alcel.strip()
                if alcel.startswith("^"):
                    azon = alcel[1:].strip()
                    b = c.execute("SELECT sor, kezdo_sor FROM blokk WHERE fajl_id = ? AND azon = ? ORDER BY sor",
                                  (f["id"], azon)).fetchone()
                    rng = linkek.blokk_tartomany(sorok, b["kezdo_sor"], b["sor"]) if b else None
                else:
                    fej = [(r[0], r[1], r[2]) for r in c.execute(
                        "SELECT szint, szoveg, sor FROM fejezet WHERE fajl_id = ? ORDER BY sor", (f["id"],))]
                    rng = linkek.fejezet_tartomany(fej, len(sorok), alcel)
                if rng is None:
                    return {**ki, "alcel_hiba": True, "szoveg": "", "kezd": None, "veg": None}
                kezd, veg = rng
            ki.update(kezd=kezd, veg=veg, szoveg="\n".join(sorok[kezd - 1:veg]))
            return ki

    def link_sorok(self) -> list[dict]:
        """Minden link az indexből (az átnevezés tervéhez): forrás, forrás típusa, cél-szöveg, feloldott cél."""
        self._kesz_vagy_hiba()
        with self.olvaso() as c:
            return [dict(r) for r in c.execute(
                "SELECT f.ut AS forras, f.tipus AS forras_tipus, f.hash AS hash, l.fajta, l.cel_nyers, l.cel "
                "FROM link l JOIN fajl f ON f.id = l.forras_id WHERE f.torolve IS NULL ORDER BY f.ut, l.sorrend")]

    # ---------------------------------------------------------------- Bases (C12)

    def bazis_sorok(self, utak=None) -> tuple[int, list[tuple]]:
        """Minden élő fájl a Bases számára: (generáció, [(id, ut, lemez_ut, tipus, meret, mtime_ns, tulajdonsagok,
        cimkek, linkek, aliasok, ctime_ns)]) útrendben (a `ctime_ns` a valódi születési idő vagy `None`, F11), **egy olvasó-tranzakcióban**. A generáció az olvasás előtt készült:
        ha közben írás történt, a következő hívás újra olvas. A `tulajdonsagok` [(kulcs, típus, JSON-érték)] a
        frontmatter sorrendjében; a `cimkek` a címkék `#` nélkül (frontmatter, majd szöveg); a `linkek`
        [{cel_nyers, alcel, alias, beagyazas, cel}]. `utak`: csak ezek a (NFC) utak (a `Tabla` inkrementális frissítése,
        C33 T070); a nem élő út kimarad."""
        self._kesz_vagy_hiba()
        gen = self.generacio
        with self.olvaso(nehez=True) as c:
            if utak is None:
                fajlok = c.execute("SELECT id, ut, lemez_ut, tipus, meret, mtime_ns, aliasok, ctime_ns FROM fajl "
                                   "WHERE torolve IS NULL ORDER BY ut").fetchall()
                szuro, idk = "", []
            else:
                lista = sorted(utak)
                fajlok = []
                for i in range(0, len(lista), 500):
                    resz = lista[i:i + 500]
                    fajlok += c.execute("SELECT id, ut, lemez_ut, tipus, meret, mtime_ns, aliasok, ctime_ns FROM fajl WHERE torolve IS "
                                        f"NULL AND ut IN ({','.join('?' * len(resz))})", resz).fetchall()
                fajlok.sort(key=lambda r: r["ut"])
                idk = [r["id"] for r in fajlok]
                if not idk:
                    return gen, []
                szuro = f" WHERE {{oszlop}} IN ({','.join('?' * len(idk))})"
            tul: dict[int, list] = collections.defaultdict(list)
            for fid, k, t, e in c.execute("SELECT fajl_id, kulcs, tipus, ertek FROM tulajdonsag" +
                                          szuro.format(oszlop="fajl_id") + " ORDER BY fajl_id, sorrend", idk):
                tul[fid].append((k, t, json.loads(e)))
            cim: dict[int, list] = collections.defaultdict(list)
            for fid, cimke in c.execute("SELECT fajl_id, cimke FROM cimke" + szuro.format(oszlop="fajl_id") +
                                        " ORDER BY fajl_id, rowid", idk):
                cim[fid].append(cimke)
            lnk: dict[int, list] = collections.defaultdict(list)
            for fid, cel_nyers, alcel, alias, beag, cel in c.execute(
                    "SELECT forras_id, cel_nyers, alcel, alias, beagyazas, cel FROM link" +
                    szuro.format(oszlop="forras_id") + " ORDER BY forras_id, sorrend", idk):
                lnk[fid].append({"cel_nyers": cel_nyers, "alcel": alcel or None, "alias": alias or None,
                                 "beagyazas": bool(beag), "cel": cel})
        return gen, [(r["id"], r["ut"], r["lemez_ut"], r["tipus"], r["meret"], r["mtime_ns"], tul.get(r["id"], []),
                      cim.get(r["id"], []), lnk.get(r["id"], []), json.loads(r["aliasok"] or "[]"), r["ctime_ns"]) for r in fajlok]

    def felold_egy(self, cel: str, forras: str) -> str | None:
        """Egy link-cél feloldása a `forras` fájlból (a feloldó zára alatt): a Bases-kifejezések `link()`-je és a
        frontmatter-linkek ezt használják — **a** feloldás (L42)."""
        with self._fl_lock:
            return self.feloldo.resolve(cel, forras)[0]

    def bazis_forrasok(self) -> list[dict]:
        """A Bases-t tartalmazó fájlok: a `.base` fájlok és a ```` ```base ```` blokkot tartalmazó jegyzetek
        (az átnevezés ezeket nézi át): [{ut, tipus: base|md, hash}] útrendben."""
        self._kesz_vagy_hiba()
        with self.olvaso() as c:
            return [{"ut": r["ut"], "tipus": r["tipus"], "hash": r["hash"]} for r in c.execute(
                "SELECT ut, tipus, hash FROM fajl WHERE torolve IS NULL AND (tipus = 'base' OR (tipus = 'md' AND id IN "
                "(SELECT fajl_id FROM kodblokk WHERE lower(nyelv) = 'base'))) ORDER BY ut")]

    def fajl_allapot(self) -> dict[str, tuple]:
        """Az élő fájlok `ut → (hash, mtime_ns, méret, lemez_ut)` — az átnevezés referencia-próbájának „előtte” állapota és
        a közben módosult fájlok kiszűrése (T106): a terven kívüli fájlokat a próba nem olvassa újra."""
        with self.olvaso() as c:
            return {r[0]: (r[1], r[2], r[3], r[4]) for r in c.execute(
                "SELECT ut, hash, mtime_ns, meret, lemez_ut FROM fajl WHERE torolve IS NULL")}

    def fajl_halmaz(self) -> list[str]:
        """Az élő fájlok NFC útjai (rendezve)."""
        with self.olvaso() as c:
            return [r[0] for r in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL ORDER BY ut")]

    def kereses(self, q: str, limit: int | None = None, kornyezet: int = 0) -> dict:
        with self.olvaso() as c:
            v = kereses.keres(c, q, min(int(limit or self.max_talalat), 1000), self.regex_idokorlat, kornyezet,
                              kizaras.betolt(self.cfg))
        return self.media_kiegeszit(v)

    def media_kiegeszit(self, valasz: dict) -> dict:
        """C25c: a felirat-találat mellé a médiája (`media`: a videó vagy a hang vault-útja), hogy a felület a másodpercére
        nyithassa. A felirat → média megfeleltetés a melléklet-szabály fordítottja (`atirat.media_feliratbol`, L44)."""
        feliratok = [t for t in valasz.get("talalatok") or [] if t.get("tipus") == "felirat" and "media" not in t]
        if not feliratok:
            return valasz
        with self.olvaso() as c:
            jeloltek = [r[0] for r in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL AND tipus IN ('video', 'hang')")]
        b = atirat.beallitasok(self.cfg)
        for t in feliratok:
            try:
                t["media"] = atirat.media_feliratbol(str(self.root), t["ut"], jeloltek, b)
            except OSError:
                t["media"] = None
        return valasz

    # ---------------------------------------------------------------- gráf

    def graf(self) -> dict:
        """A gráf a legacy `obsidian_graf` alakjában, az indexből (egy olvasó-tranzakcióban, a nehéz olvasók zára alatt)."""
        kiz = kizaras.betolt(self.cfg)
        with self.olvaso(nehez=True) as c:
            files = [r[0] for r in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL ORDER BY lemez_ut") if not kiz.kizart(r[0])]
            out: dict[str, set] = collections.defaultdict(set)
            unresolved: collections.Counter = collections.Counter()
            tobbertelmu: collections.Counter = collections.Counter()
            for forras, cel, nyers, alap, tobb in c.execute(
                    "SELECT f.ut, l.cel, l.cel_nyers, l.alap, l.tobbertelmu FROM link l "
                    "JOIN fajl f ON f.id = l.forras_id WHERE f.torolve IS NULL"):
                if kiz.kizart(forras):
                    continue                    # a kizárt jegyzet linkjei nem rajzolódnak (a fájl és a linkjei az indexben maradnak)
                if tobb:
                    tobbertelmu[alap] += 1
                if cel:
                    if not kiz.kizart(cel):
                        out[forras].add(cel)
                elif (nyers or "").strip():
                    unresolved[nfc(nyers.strip())] += 1
            canvas_hiba = [tuple(r) for r in c.execute(
                "SELECT ut, canvas_hiba FROM fajl WHERE torolve IS NULL AND canvas_hiba IS NOT NULL ORDER BY lemez_ut")
                if not kiz.kizart(r[0])]
        return {"files": files, "out": out, "unresolved": unresolved, "tobbertelmu": tobbertelmu,
                "canvas_hiba": canvas_hiba}

    def graf_api(self) -> dict:
        g = self.graf()
        return {"csucsok": g["files"], "elek": [[s, t] for s in sorted(g["out"]) for t in sorted(g["out"][s])],
                "feloldatlan": dict(sorted(g["unresolved"].items())), "tobbertelmu": dict(sorted(g["tobbertelmu"].items())),
                "canvas_hiba": [list(x) for x in g["canvas_hiba"]]}

    def graf_valasz(self) -> tuple[bytes, str]:
        """A `/api/vault/graf` válasza JSON-bájtokként és ETag-gel, a szerkezeti generáció szerint gyorsítótárazva (T070)."""
        return self._gyorsitott("graf", self.graf_api)
