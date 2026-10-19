"""A vault-index SQLite-tára: `{index}/vault.sqlite` (ARCHITECTURE 4.).

Újraépíthető gyorsítótár a vaultból (a legacy `var/index/` nem szerződés, L60). Séma csak új
migrációval (`PRAGMA user_version`), WAL (L57). Az eltűnt fájl sora `torolve` jelet kap, nem törlődik;
a belőle származtatott sorok (link, címke, fejezet, …, FTS) törlődnek, mert a fájlból újraszámolhatók.
Az FTS5 tokenizálója `unicode61 remove_diacritics 2`: kis-nagybetű- és ékezetfüggetlen.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

VERZIO = 7
# C33 (T171): a sérült adatbázis jele — SQLITE_CORRUPT (11) és SQLITE_NOTADB (26), a kiterjesztett kód alsó bájtja
SERULT_KODOK = (11, 26)

_SEMA_1 = """
CREATE TABLE fajl(
    id INTEGER PRIMARY KEY,
    ut TEXT NOT NULL UNIQUE,            -- NFC, vault-relatív, `/` elválasztó
    lemez_ut TEXT NOT NULL,             -- a lemezen álló (gyakran NFD) relatív út
    nev TEXT NOT NULL,                  -- alapnév kiterjesztéssel
    kit TEXT NOT NULL,                  -- kiterjesztés, kisbetűvel, pont nélkül
    mappa TEXT NOT NULL,
    tipus TEXT NOT NULL,                -- md | canvas | base | pdf | kep | video | hang | felirat | egyeb
    meret INTEGER, mtime_ns INTEGER,
    ctime_ns INTEGER,                   -- F11: valódi születési idő (st_birthtime), vagy NULL; sosem mtime/st_ctime
    hash TEXT,                          -- sha1 (csak szöveges fájlra)
    fm_nyers TEXT, fm_hiba TEXT, canvas_hiba TEXT,
    aliasok TEXT,                       -- JSON-lista
    indexelve REAL,
    torolve REAL                        -- az eltűnés ideje (L57: jelölés, nem törlés)
);
CREATE INDEX fajl_lemez ON fajl(lemez_ut);
CREATE TABLE mappa(ut TEXT PRIMARY KEY, torolve REAL);
CREATE TABLE tulajdonsag(fajl_id INTEGER NOT NULL, sorrend INTEGER, kulcs TEXT, tipus TEXT, ertek TEXT,
                         ervenyes INTEGER);
CREATE INDEX tulajdonsag_fajl ON tulajdonsag(fajl_id);
CREATE INDEX tulajdonsag_kulcs ON tulajdonsag(kulcs);
CREATE TABLE cimke(fajl_id INTEGER NOT NULL, cimke TEXT, kis TEXT, forras TEXT, sor INTEGER);
CREATE INDEX cimke_fajl ON cimke(fajl_id);
CREATE INDEX cimke_kis ON cimke(kis);
CREATE TABLE fejezet(fajl_id INTEGER NOT NULL, szint INTEGER, szoveg TEXT, sor INTEGER);
CREATE INDEX fejezet_fajl ON fejezet(fajl_id);
CREATE TABLE blokk(fajl_id INTEGER NOT NULL, azon TEXT, sor INTEGER, kezdo_sor INTEGER);
CREATE INDEX blokk_fajl ON blokk(fajl_id);
CREATE INDEX blokk_azon ON blokk(azon);
CREATE TABLE link(
    id INTEGER PRIMARY KEY,
    forras_id INTEGER NOT NULL,
    sorrend INTEGER,
    fajta TEXT,                         -- wiki | md | canvas_fajl | canvas_szoveg
    cel_nyers TEXT,                     -- a gráf-cél, ahogy a szövegben áll
    alcel TEXT, alias TEXT, beagyazas INTEGER, tulajdonsag TEXT, csomopont TEXT,
    sor INTEGER, oszlop INTEGER, hossz INTEGER,
    kulcs TEXT,                         -- a cél kisbetűs alapneve (`feloldas.celkulcs`): az újrafeloldás kulcsa
    alap TEXT,                          -- a feloldásban használt alapnév
    tobbertelmu INTEGER,
    cel TEXT                            -- a feloldott NFC út, vagy NULL
);
CREATE INDEX link_forras ON link(forras_id);
CREATE INDEX link_kulcs ON link(kulcs);
CREATE INDEX link_cel ON link(cel);
CREATE TABLE feladat(fajl_id INTEGER NOT NULL, sor INTEGER, allapot TEXT, szoveg TEXT, behuzas INTEGER,
                     hatarido TEXT, datumok TEXT);
CREATE INDEX feladat_fajl ON feladat(fajl_id);
CREATE INDEX feladat_hatarido ON feladat(hatarido);
CREATE TABLE keplet(fajl_id INTEGER NOT NULL, sor INTEGER, sor_veg INTEGER, kezd INTEGER, veg INTEGER,
                    blokk INTEGER, forras TEXT);
CREATE INDEX keplet_fajl ON keplet(fajl_id);
CREATE TABLE kodblokk(fajl_id INTEGER NOT NULL, nyelv TEXT, sor_kezd INTEGER, sor_veg INTEGER);
CREATE INDEX kodblokk_fajl ON kodblokk(fajl_id);
CREATE VIRTUAL TABLE fts USING fts5(ut, nev, tartalom, tokenize='unicode61 remove_diacritics 2',
                                    prefix='2 3');
CREATE TABLE meta(kulcs TEXT PRIMARY KEY, ertek TEXT);
"""

SZARMAZTATOTT = ("tulajdonsag", "cimke", "fejezet", "blokk", "feladat", "keplet", "kodblokk", "media_szoveg")

# C25c (4-es migráció): a PDF lapjainak és a VTT-felirat mondatainak kereshető szövege — **külön FTS-táblában**
# (`fts_szakasz`), hogy a jegyzetek `fts`-ének bm25-statisztikája (IDF, átlagos hossz) ne változzon: a 22 M karakteres PDF-szöveg
# a közös táblában a C25b keresési mérését rontotta (recall@1 0,78 → 0,70, NAPLO C25c). Egy szakasz a PDF egy lapja, ill. a
# felirat egy legfeljebb ~60 s-os ablaka (soronként egy mondat). `szakasz`: rowid = az `fts_szakasz` rowid-ja; `ertek` az oldal
# (PDF) vagy az ablak kezdete (mp); `sor_kezd` a szakasz első sorának sorszáma a fájl szövegében (1-től); `idok` a felirat
# soronkénti kezdő másodpercei (JSON). `media_szoveg`: a fájl feldolgozva (`fajta` `pdf` | `felirat`, a szakaszok száma; a
# szöveg nélküli PDF-nél 0) — a származtatott sorok közt törlődik.
_SEMA_4 = """
CREATE TABLE IF NOT EXISTS media_szoveg(fajl_id INTEGER PRIMARY KEY, fajta TEXT NOT NULL, szakaszok INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS szakasz(id INTEGER PRIMARY KEY, fajl_id INTEGER NOT NULL, ertek REAL, sor_kezd INTEGER NOT NULL,
                                   idok TEXT);
CREATE INDEX IF NOT EXISTS szakasz_fajl ON szakasz(fajl_id);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_szakasz USING fts5(tartalom, tokenize='unicode61 remove_diacritics 2', prefix='2 3');
"""


class SemaHiba(RuntimeError):
    """Az index sémája újabb, mint amit ez a kód ismer."""


def serult_hiba(e: BaseException) -> bool:
    """Az SQLite hibája sérült (vagy nem SQLite) adatbázisra utal-e (nem zár, nem foglaltság, nem lemezhiba)."""
    if not isinstance(e, sqlite3.DatabaseError):
        return False
    kod = getattr(e, "sqlite_errorcode", None)
    if kod is not None:
        return (kod & 0xFF) in SERULT_KODOK
    uzenet = str(e).lower()
    return "malformed" in uzenet or "not a database" in uzenet


def felretesz(ut: Path) -> Path | None:
    """A sérült index (és a `-wal`/`-shm` kísérője) félre: `{index}/serult-<idő>.sqlite` (T171). Az index újraépíthető
    gyorsítótár (L60), ezért nem törlünk — a félretett fájl a hibakereséshez marad, a doctor jelzi. → az új név, vagy
    `None`, ha nem volt mit félretenni."""
    if not ut.exists():
        return None
    cel = ut.with_name(f"serult-{time.strftime('%Y%m%d-%H%M%S')}.sqlite")
    n = 1
    while cel.exists():
        n += 1
        cel = ut.with_name(f"serult-{time.strftime('%Y%m%d-%H%M%S')}-{n}.sqlite")
    os.replace(ut, cel)
    for kiseret in ("-wal", "-shm"):
        k = Path(str(ut) + kiseret)
        if k.exists():
            os.replace(k, Path(str(cel) + kiseret))
    print(f"[index] a sérült index félretéve: {cel.name}; az index újraépül", file=sys.stderr, flush=True)
    return cel


def _probaolvas(c: sqlite3.Connection) -> None:
    """Olcsó épség-próba a megnyitáskor: a séma-lap és a `fajl` tábla első lapja olvasható. A teljes `quick_check` a valódi
    indexen ~2 s (az induló építés a 15. döntés szerint ~2 s), ezért az a doctoré; a menet közbeni sérülést az író szál
    a hibakódból ismeri fel (`serult_hiba`)."""
    c.execute("SELECT count(*) FROM sqlite_master").fetchone()
    if c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fajl'").fetchone():
        c.execute("SELECT id, ut FROM fajl ORDER BY id LIMIT 1").fetchall()
        c.execute("SELECT id FROM fajl ORDER BY id DESC LIMIT 1").fetchall()


def nyit(ut: Path, iro: bool = False, felretett: list | None = None) -> sqlite3.Connection:
    """Kapcsolat az indexhez. Az író létrehozza és migrálja; az olvasó csak olvas.

    C33 (T171): az író a sérült (vagy nem SQLite) fájlt félreteszi (`felretesz`) és üres indexet nyit — az első szinkron
    újraépíti. A félretett út a `felretett` listába kerül (az `Index` az állapotában mutatja)."""
    if not iro:
        return _nyit(ut, False)
    try:
        return _nyit(ut, True)
    except SemaHiba:
        raise
    except sqlite3.DatabaseError as e:
        if not serult_hiba(e):
            raise
        cel = felretesz(ut)
        if felretett is not None and cel is not None:
            felretett.append(cel)
        return _nyit(ut, True)


def _nyit(ut: Path, iro: bool) -> sqlite3.Connection:
    if iro:
        ut.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(ut), timeout=30, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 30000")
    if iro:
        try:
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = NORMAL")
            _probaolvas(c)
            migral(c)
        except BaseException:
            c.close()
            raise
    else:
        c.execute("PRAGMA query_only = 1")
    return c


def migral(c: sqlite3.Connection) -> None:
    v = c.execute("PRAGMA user_version").fetchone()[0]
    if v > VERZIO:
        raise SemaHiba(f"az index sémája ({v}) újabb, mint a kódé ({VERZIO})")
    if v < 1:
        c.execute("BEGIN")
        for stmt in _utasitasok(_SEMA_1):
            c.execute(stmt)
        c.execute("PRAGMA user_version = 1")
        c.execute("COMMIT")
        v = 1
    if v < 2:
        # C10.6: a maszk és a feloldás szabálya változott (13. döntés), a `link.kulcs` kisbetűs lett. A szöveges
        # fájlok hash-e és mtime-ja törlődik: az első szinkron mindet újraelemzi és újra feloldja. A fájlsorok
        # (és a `torolve` jelek, L57) megmaradnak.
        c.execute("BEGIN")
        c.execute("UPDATE fajl SET hash = NULL, mtime_ns = NULL WHERE tipus IN ('md', 'canvas')")
        c.execute("PRAGMA user_version = 2")
        c.execute("COMMIT")
    if v < 3:
        # C29.8 (T037, T039, T041): az elemző szabálya változott (setext fejezet, az idézet/táblázat horgony a blokk elejétől,
        # szöveggé alakított szám-alias, YAML-alias tilalom, üres és BOM-os frontmatter), és a korábbi, kihagyott
        # (visszagördült) fájlsorok is újraelemzendők: mint a 2-es migrációnál, a hash ÉS az mtime törlődik (az
        # `_alkalmaz` a stat- és a hash-egyezést is átugorná), az első szinkron mindent újraelemez.
        c.execute("BEGIN")
        c.execute("UPDATE fajl SET hash = NULL, mtime_ns = NULL WHERE tipus IN ('md', 'canvas')")
        c.execute("PRAGMA user_version = 3")
        c.execute("COMMIT")
    if v < 4:
        # C25c: a PDF-lapok és a VTT-mondatok kereshető szövege (`fts_szakasz`). A `pdf` és a `felirat` sorok hash-e és mtime-ja
        # törlődik: az első szinkron mindet újra feldolgozza (a VTT-t elemzi, a PDF-et a kinyerő gyorsítótárából tölti, vagy
        # a kinyerő sorába teszi). A többi fájlsor érintetlen.
        c.execute("BEGIN")
        for stmt in _utasitasok(_SEMA_4):
            c.execute(stmt)
        c.execute("UPDATE fajl SET hash = NULL, mtime_ns = NULL WHERE tipus IN ('pdf', 'felirat')")
        c.execute("PRAGMA user_version = 4")
        c.execute("COMMIT")
    if v < 5:
        # F5: explicit ./ and ../ links now resolve from the source directory.
        # Persisted v4 link rows may still say unresolved. Reparse only sources
        # containing those links; all other cached notes and history stay intact.
        from .feloldas import _elokeszit
        c.execute("BEGIN")
        forrasok = set()
        for fid, cel in c.execute("SELECT forras_id, cel_nyers FROM link"):
            if fid not in forrasok and _elokeszit(cel).startswith(("./", "../")):
                forrasok.add(fid)
        ids = sorted(forrasok)
        for i in range(0, len(ids), 500):
            resz = ids[i:i + 500]
            c.execute(f"UPDATE fajl SET hash = NULL, mtime_ns = NULL WHERE id IN ({','.join('?' for _ in resz)})", resz)
        c.execute("PRAGMA user_version = 5")
        c.execute("COMMIT")
    if v < 6:
        # F11: `fajl.ctime_ns` = a fájl valódi születési ideje (`st_birthtime`), vagy NULL, ha a fájlrendszer nem ad ilyet
        # (sosem mtime és sosem a POSIX `st_ctime`). A hash-ek és az mtime-ok NEM törlődnek (felesleges teljes újraelemzés):
        # a következő szinkron a NULL `ctime_ns` sorokat csak UPDATE-tel tölti ki (`Index._alkalmaz`). A friss séma már
        # tartalmazza az oszlopot, ezért az ALTER csak a régi (v1–v5) indexen fut.
        c.execute("BEGIN")
        if not any(r[1] == "ctime_ns" for r in c.execute("PRAGMA table_info(fajl)")):
            c.execute("ALTER TABLE fajl ADD COLUMN ctime_ns INTEGER")
        c.execute("PRAGMA user_version = 6")
        c.execute("COMMIT")
    if v < 7:
        # S1: a %% komment most a szerkesztővel azonos tartományban rejtett. A v6 származtatott link/tag/task/
        # codeblock/FTS sorai még a komment tartalmát is tartalmazhatják. Mindkét gyors kihagyás érvénytelenítendő;
        # a következő szinkron újraelemzi a Markdown- és canvas-szöveget. Fájlazonosság és tombstone megmarad.
        c.execute("BEGIN")
        c.execute("UPDATE fajl SET hash = NULL, mtime_ns = NULL WHERE tipus IN ('md', 'canvas')")
        c.execute("PRAGMA user_version = 7")
        c.execute("COMMIT")


def _utasitasok(sql: str) -> list[str]:
    out, buf = [], []
    for sor in sql.splitlines():
        buf.append(sor.split("--")[0] if "--" in sor else sor)
        if sor.rstrip().endswith(";"):
            s = "\n".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    return out


def meta(c: sqlite3.Connection, kulcs: str, ertek: str | None = None) -> str | None:
    if ertek is None:
        r = c.execute("SELECT ertek FROM meta WHERE kulcs = ?", (kulcs,)).fetchone()
        return r[0] if r else None
    c.execute("INSERT INTO meta(kulcs, ertek) VALUES (?, ?) ON CONFLICT(kulcs) DO UPDATE SET ertek = excluded.ertek",
              (kulcs, ertek))
    return ertek
