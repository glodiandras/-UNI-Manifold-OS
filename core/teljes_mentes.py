"""CX-012: teljes, verziózott, inkrementális külső mentés (80(g)); visszaállítás kizárólag üres célba.

A célmappában minden futás egy új `Manifold-ÉÉÉÉHHNN-ÓÓPPMM-ffffff` változat. Készítés közben a neve `….resz`; a
`kesz` jelölő az utolsó írás (a jegyzék és az ellenőrzés után), utána az átnevezés. A `.resz` vagy `kesz` nélküli
változat soha nem siker; a félbemaradt `.resz` mappát a következő futás (a cél saját zárja alatt) eltakarítja.

Inkrementális: a forrásban változatlan (méret + mtime) fájl az előző ellenőrzött változatból hard linkkel kerül át
(exFAT-on vagy más link nélküli kötetnél másolat). A konzisztens pillanatkép (SQLite `backup` API, a git-tárak, az
állapot, a kódtár-bundle) a kör-zár alatt készül; a nagy és a médiafájlok a zár elengedése után másolódnak, másolás
közbeni hash-sel és a másolat visszaolvasott ellenőrzésével.

Nincs a mentésben (újratölthető, a jegyzék `kihagyva` mezője rögzíti): a modellek (`{models}`: `bin/mos models pull`,
a `config/models.toml` rögzített revízióival), a `var/venv` (`bin/mos runtime install`), a `runtime/`
(`bin/mos runtime fetch`, pinelt és sha256-tal ellenőrzött; az LLVM/SDK: `bin/mos cpp telepit`), az újraépíthető
`{index}` (vault-index, keresési vektorok, PDF-szöveg; 33., 58(a), 73(b)), és a `[teljes_mentes] kihagy` utak-kulcsai
(alapból a videólánc staging-ja és az `archive/`). Soha nem kerül bele (átmeneti): a `{tmp}`, `{cache}`, `{run}`,
`{runs}` (az élő naplók is) — a `{os}` alatt bármely mélységben (egy beágyazott `…/var/tmp` is) —, és a gyökér rejtett
mappái (`.claude/`: a párhuzamos munkafák saját `var/`-ral és APFS-klónokkal; a `.git` a kódtár-bundle-ben megy).

Termék-elrendezésben (`cfg.elrendezes == "termek"`, F3-DESIGN §5) a `{os}` (a csomag) nincs a mentésben — újratelepíthető —,
a `{var}` a vaulttal együtt kerül be (a `.manifold/var/{tmp,run,runs,cache,index}` bárhol kimarad), a konfiguráció a
`settings.toml` és a `workspace.toml` másolata (az `aktiv-os.toml` helyett), a változatok pedig munkaterenként külön
mappába kerülnek: `<cél>/Manifold Backups/<munkater_id>/Manifold-<idő>/` (a ritkítás is munkaterenként). A külön kötet
szabálya a vault és a `{var}` kötetéhez mér (`adat_kotet`), nem a kódfáéhez. A jegyzék `munkater_id` és `elrendezes`
mezőt kap. A termék visszaállítása (kulcsok szerinti, a `workspace.nyit`-tal) az F8 dolga.
"""
from __future__ import annotations
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from . import config, frame, kiserok, mediatipus, snapshot, tartos, vaultkivul
from .utvonalak import HttpError  # noqa: F401 — az útvonal-modulok közös importja

ALLAPOT = 'teljes-mentes.json'
FORMATUM = 2
EXTRAK = ('vault', 'vault_git', 'ytdlp_git', 'var', 'state', 'szemelyes', 'fuzet', 'fuzet_bejovo', 'video_bejovo',
          'video_jobs', 'video_eredeti', 'video_visszavont', 'staging', 'ytdlp_archivum', 'archive',
          'feladatok_db', 'router_db', 'tanulas_db', 'automatika_db', 'felulet')
# Újratölthető vagy újraépíthető: nem kerül a mentésbe, a jegyzék megnevezi a visszaállítás módját.
KIHAGYOTT = {
    'models': 'bin/mos models pull (a config/models.toml rögzített revízióival)',
    'venv': 'bin/mos runtime install (a runtime/wheels-ből, hálózat nélkül)',
    'runtime': 'bin/mos runtime fetch, majd bin/mos runtime install (pinelt, sha256-tal ellenőrzött); C++: bin/mos cpp telepit',
    'index': 'újraépül: a core induláskor a vaultból építi a vault-indexet; a keresési vektorokat a vektorindex, '
             'a PDF-szöveget a kinyerő feladata (58(a), 73(b))',
}
# A `[teljes_mentes] kihagy` listájának (utak-kulcsok) magyarázata a jegyzékben; ismeretlen kulcsnál általános szöveg.
KIHAGY_MAGYARAZAT = {
    'staging': 'a videólánc staging-ja nincs a mentésben: a bevitt videó a vaultban van ({video_mappa}), '
               'a többi újra letölthető (bin/mos video letoltes)',
    'archive': 'az archive/ (a konvertálás előtti eredetik, a visszavont média) nincs a mentésben; a vaultbeli változat benne van',
    'ytdlp_archivum': 'a letöltési archívum (duplikátum-védelem) nincs a mentésben: a már letöltött videó újra letöltődhet',
}
ATMENETI = ('run', 'tmp', 'cache', 'runs')     # soha nem kerül a mentésbe (a `runs` az élő naplókkal: core.log, F-*.log)
NAGY_BAJT = 8 * 1024 * 1024
VALTOZAT_MINTA = re.compile(r'^Manifold-\d{8}-\d{6}-\d{6}$')
RESZ_MINTA = re.compile(r'^Manifold-\d{8}-\d{6}-\d{6}\.resz$')
KESZ = 'kesz'
CEL_ZAR = '.manifold-teljes-mentes.lock'
TERMEK_MAPPA = 'Manifold Backups'      # termék-elrendezésben: a cél alatt munkaterenként egy almappa (`<cél>/Manifold Backups/<id>/`)
VAR_ATMENETI = ('tmp', 'run', 'runs', 'cache', 'index')    # a `{var}` alatt soha nem kerül a mentésbe, akárhol is él a `{var}`


class MentesHiba(ValueError):
    pass


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def _json(p, d):
    tartos.atomi_ir(p, json.dumps(d, ensure_ascii=False, indent=2).encode())


def _letezo(p):
    try:
        return Path(p).resolve(strict=True) if p is not None else None
    except (OSError, RuntimeError):
        return None


def _kotet(p) -> int | None:
    """Egy út kötet-azonosítója (`st_dev`); a tesztek ezt cserélik, ha külön kötetet kell hamisítani."""
    try:
        return Path(p).stat().st_dev
    except OSError:
        return None


def adat_kotet(cfg) -> set[int]:
    """A mentendő adat kötetei: a vaulté és a `{var}`-é (ha az a vaulton kívül van). A külső mentés célja csak ezektől különbözhet
    (F3-DESIGN §5); a kódfa (`cfg.root`) kötete nem számít: a termékben csak olvasható, a hordozható `{var}` az övé alatt él."""
    vault, var = _letezo(cfg.utak.get('vault')), _letezo(cfg.utak.get('var'))
    utak = [vault] if vault is not None else []
    if var is not None and not (vault is not None and (var == vault or vault in var.parents)):
        utak.append(var)
    return {d for d in (_kotet(p) for p in utak) if d is not None}


def kulso_kotet(cfg, cel) -> bool:
    """A `cel` az adat köteteitől különböző, ismert kötet-e. Ha az adat kötete nem állapítható meg, nem külső (zárva hibázás)."""
    kotet, adat = _kotet(cel), adat_kotet(cfg)
    return kotet is not None and bool(adat) and kotet not in adat


def forrasok(cfg):
    kihagyott = list(_kihagyott_utak(cfg).values())
    gyokerek = {} if cfg.elrendezes == 'termek' else {'os': cfg.root.resolve()}    # a termék csomagja újratelepíthető
    for kulcs in sorted((k for k in EXTRAK if k in cfg.utak), key=lambda k: len(cfg.path(k).resolve().parts)):
        p = cfg.path(kulcs).resolve()
        if p.exists() and not any(p == v or v in p.parents for v in gyokerek.values()) and not _alatta(p, kihagyott):
            gyokerek[kulcs] = p
    return gyokerek


def kihagyott_kulcsok(cfg) -> dict[str, str]:
    """A mentésből kihagyott utak-kulcsok → a visszaállítás/magyarázat szövege: a beépített újratölthetők (modellek,
    venv, runtime, index) és a `[teljes_mentes] kihagy` lista (alapból a staging és az archive/)."""
    ki = {k: m for k, m in KIHAGYOTT.items() if k in cfg.utak}
    for k in cfg.section('teljes_mentes').get('kihagy', []) or []:
        if k in cfg.utak and k not in ki:
            ki[k] = KIHAGY_MAGYARAZAT.get(k, f'nincs a mentésben ([teljes_mentes] kihagy: {k})').replace(
                '{video_mappa}', kiserok.kisero_mappa(cfg, 'video'))
    return ki


def _kihagyott_utak(cfg):
    ki = {k: cfg.path(k).resolve() for k in (*kihagyott_kulcsok(cfg), *ATMENETI) if k in cfg.utak}
    if 'var' in cfg.utak:                               # a `{var}` átmeneti almappái akkor is, ha a kulcsuk máshová mutat
        for n in VAR_ATMENETI:                          # (termékben a `cache` a `{install}` alatt van, a `{var}/cache` mégis a vaulttal jönne)
            ki.setdefault(f'var/{n}', (cfg.path('var') / n).resolve())
    return ki


def _kizart_mintak(cfg, gyokerek=None) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Gyökerenként a kihagyott utak az adott gyökérhez mért részsorozatai (pl. `var/tmp`, `var/runs`,
    `modulok/ytdlp/staging`; termékben `.manifold/var/tmp`): a gyökér alatt BÁRMELY mélységben kizárnak (egy beágyazott munkafa
    vagy másolat `…/var/tmp`-je, egy beágyazott vault `.manifold/var/tmp/proba/` klónja is). Csak a legalább kéttagú minta
    számít — egy egytagú név (`runtime`, `archive`) a gyökéren kívül egy ártatlan almappát is elvinne."""
    gyokerek = forrasok(cfg) if gyokerek is None else gyokerek
    kihagyott = list(_kihagyott_utak(cfg).values())
    ki = {}
    for kulcs, gyoker in gyokerek.items():
        minta = set()
        for p in kihagyott:
            try:
                reszek = p.relative_to(gyoker).parts
            except ValueError:
                continue
            if len(reszek) >= 2:
                minta.add(reszek)
        ki[kulcs] = tuple(sorted(minta))
    return ki


def _alatta(p, gyokerek):
    return any(p == g or g in p.parents for g in gyokerek)


def _benne(reszek, minta) -> bool:
    n = len(minta)
    return any(reszek[i:i + n] == minta for i in range(len(reszek) - n + 1))


def _kizar(rel, *, rendszer=False, mappa=False, mintak=()):
    """A `{os}` (rendszer) fájának kizárásai: a rendszer-nevek, a gyökér rejtett mappái (`.claude/`: a párhuzamos munkafák
    saját `var/`-ral és APFS-klónokkal, amelyek a külső kötetre valódi másolatként kerülnének), és a kihagyott utak
    mintái bármely mélységben. A kihagyott utak mintái (`mintak`) minden gyökérre érvényesek (termékben a vault a gyökér), a
    rendszer-nevek és a rejtett mappák csak a `{os}` fájára."""
    reszek = rel.parts
    if any(_benne(reszek, m) for m in mintak):
        return True
    if not rendszer:
        return False
    return (any(s in ('.git', 'node_modules', '__pycache__', '.DS_Store') for s in reszek)
            or rel.name.endswith('.pyc')
            or (mappa and len(reszek) == 1 and rel.name.startswith('.')))


def _sqlite(p):
    with p.open('rb') as f:
        return f.read(16) == b'SQLite format 3\0'


def _fajlok(root, *, rendszer=False, kihagyott=(), mintak=()):
    if root.is_file():
        yield root, Path('.')
        return
    for mappa, mappak, fajlok in os.walk(root, followlinks=False):
        m = Path(mappa)
        for nev in sorted(mappak[:]):
            p = m / nev; rel = p.relative_to(root)
            if _kizar(rel, rendszer=rendszer, mappa=True, mintak=mintak) or p in kihagyott:
                mappak.remove(nev)
            elif p.is_symlink():
                mappak.remove(nev)
                yield p, rel
            else:
                yield p, rel
        for nev in sorted(fajlok):
            p = m / nev; rel = p.relative_to(root)
            # Csak valódi SQLite mellékfájlt hagyunk ki; egy felhasználói *.lock vagy *.db-wal adatot nem.
            sqlite_mellek = p.name.endswith(('-wal', '-shm')) and p.with_name(p.name[:-4]).is_file() and _sqlite(p.with_name(p.name[:-4]))
            if not _kizar(rel, rendszer=rendszer, mintak=mintak) and not sqlite_mellek and p not in kihagyott:
                yield p, rel


# ------------------------------------------------------------------ a cél névtere

@contextmanager
def _cel_zar(cel: Path):
    """A célmappa saját zárja: egyszerre egy mentés (vagy takarítás) dolgozik ugyanabban a célban."""
    with open(cel / CEL_ZAR, 'a+') as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MentesHiba('Ebben a célmappában már fut egy teljes mentés.') from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _takarit_reszeket(cel: Path, log=print) -> list[str]:
    """A félbemaradt `.resz` változatok törlése; csak a saját névmintánkra illő, közvetlen almappákat."""
    torolt = []
    for p in sorted(cel.iterdir()):
        if RESZ_MINTA.match(p.name) and p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
            torolt.append(p.name)
            log(f'félbemaradt mentés eltakarítva: {p.name}')
    return torolt


def kesz_valtozatok(cel: Path) -> list[Path]:
    """A célmappa kész (`kesz` jelölős) változatai, a legrégebbitől a legújabbig."""
    cel = Path(cel)
    if not cel.is_dir():
        return []
    return sorted(p for p in cel.iterdir() if VALTOZAT_MINTA.match(p.name) and p.is_dir() and not p.is_symlink()
                  and (p / KESZ).is_file())


def _termek_valtozatok(cel: Path) -> list[Path]:
    """A termék-elrendezés mentései (`<cél>/Manifold Backups/<id>/`): ha a célban egyetlen munkatérnek van kész változata, az övé;
    több munkatérnél a hívó a munkatér mappáját adja meg (a másikét nem találgatjuk)."""
    gyoker = cel / TERMEK_MAPPA
    if not gyoker.is_dir() or gyoker.is_symlink():
        return []
    mappak = [m for m in sorted(gyoker.iterdir()) if m.is_dir() and not m.is_symlink() and kesz_valtozatok(m)]
    if len(mappak) > 1:
        raise MentesHiba('A célban több munkatér mentése van; add meg a munkatér mappáját: '
                         + ', '.join(m.name for m in mappak))
    return kesz_valtozatok(mappak[0]) if mappak else []


def _valtozat(ut: Path) -> Path:
    """Egy változat útja; ha a célmappát (vagy termékben a munkatér mappáját) kapjuk, a legutóbbi kész változat."""
    ut = Path(ut).expanduser().resolve()
    if (ut / 'jegyzek.json').is_file() or ut.name.endswith('.resz'):
        return ut
    lista = kesz_valtozatok(ut) or _termek_valtozatok(ut)
    if not lista:
        raise MentesHiba('A célmappában nincs kész teljes mentés.')
    return lista[-1]


def _ritkit(cel: Path, megtartott: int, vedett: set[Path], log=print) -> list[str]:
    """Csak kész változatot töröl, a legújabb `megtartott` darabot és a védetteket megtartva."""
    lista = kesz_valtozatok(cel)
    torles = [p for p in lista[:max(0, len(lista) - max(1, megtartott))] if p not in vedett]
    for p in torles:
        shutil.rmtree(p)
        log(f'régi mentési változat törölve: {p.name}')
    return [p.name for p in torles]


def _elozo(cel: Path):
    """Az előző kész változat és a jegyzékének fájl-elemei (`ut` → elem); sérült jegyzéknél nincs alap."""
    for v in reversed(kesz_valtozatok(cel)):
        try:
            if sha(v / 'jegyzek.json') != (v / 'jegyzek.sha256').read_text().strip():
                continue
            d = json.loads((v / 'jegyzek.json').read_text())
        except (OSError, ValueError):
            continue
        if d.get('verzio') != FORMATUM:
            continue
        return v, {e['ut']: e for e in d.get('elemek', []) if e.get('tipus') == 'fajl'}
    return None, {}


# ------------------------------------------------------------------ másolás

def _masol(p: Path, ki: Path) -> str:
    """Másolás egy menetben hash-sel, `F_FULLFSYNC`-kel; a másolat visszaolvasva is egyezik → a forrás sha256-ja."""
    h = hashlib.sha256()
    with p.open('rb') as be, ki.open('xb') as k:
        for b in iter(lambda: be.read(1024 * 1024), b''):
            h.update(b); k.write(b)
        k.flush()
        tartos.fsync_teljes(k.fileno())
    shutil.copystat(p, ki)
    ertek = h.hexdigest()
    if sha(ki) != ertek:
        raise MentesHiba(f'A másolat ellenőrzőösszege eltér: {ki}')
    return ertek


def _linkel(regi: Path, ki: Path) -> bool:
    """A változatlan fájl hard linkje az előző kész változatból. A T100 hard-link-tilalma a vaultra és a figyelt fákra szól
    (az FSEvents nem jelenti a linkelt fájl törlését); itt a forrás és a cél is a külső mentés-kötetén áll, amelyet a `ment`
    a mentendő gyökereken kívülinek ellenőriz (`vaultkivul.vaultban_van`, fájlrendszer-azonosság szerint)."""
    try:
        os.link(regi, ki)
        return True
    except OSError:
        return False


class _Iro:
    """Egy változat fájlelemeinek írója: link az előző változatból, vagy ellenőrzött másolat."""

    def __init__(self, resz: Path, elozo: Path | None, elozo_elemek: dict):
        self.resz, self.elozo, self.elozo_elemek = resz, elozo, elozo_elemek
        self.linkelt: set[str] = set()
        self.masolt = 0

    def fajl(self, p: Path, rp: Path) -> dict:
        ki = self.resz / rp
        ki.parent.mkdir(parents=True, exist_ok=True)
        elotte = p.stat()
        ut = rp.as_posix()
        if _sqlite(p):
            with closing(sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=10)) as be, closing(sqlite3.connect(ki)) as db:
                be.backup(db)
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise MentesHiba(f'Hibás adatbázis: {p}')
            with ki.open('rb') as f:
                tartos.fsync_teljes(f.fileno())
            self.masolt += 1
            return {'ut': ut, 'tipus': 'fajl', 'meret': ki.stat().st_size, 'sha256': sha(ki), 'sqlite': True,
                    'mod': elotte.st_mode & 0o777}
        regi = self.elozo_elemek.get(ut)
        if (regi and not regi.get('sqlite') and regi.get('forras_meret') == elotte.st_size
                and regi.get('forras_mtime_ns') == elotte.st_mtime_ns and self.elozo is not None):
            forras = self.elozo / ut
            try:
                ok = forras.is_file() and not forras.is_symlink() and forras.stat().st_size == regi['meret']
            except OSError:
                ok = False
            if ok and _linkel(forras, ki):
                self.linkelt.add(ut)
                return {**regi, 'mod': elotte.st_mode & 0o777}
        ertek = _masol(p, ki)
        utana = p.stat()
        if (elotte.st_ino, elotte.st_size, elotte.st_mtime_ns) != (utana.st_ino, utana.st_size, utana.st_mtime_ns):
            raise MentesHiba(f'A fájl másolás közben változott; indítsd újra: {p}')
        self.masolt += 1
        return {'ut': ut, 'tipus': 'fajl', 'meret': elotte.st_size, 'sha256': ertek, 'sqlite': False,
                'mod': elotte.st_mode & 0o777, 'forras_meret': elotte.st_size, 'forras_mtime_ns': elotte.st_mtime_ns}


def _halaszthato(p: Path, rel: Path, allapot_gyoker: Path | None) -> bool:
    """A zár után másolható: nagy vagy médiafájl, de soha nem SQLite, git-tár vagy állapotfájl."""
    if any(r.endswith('.git') for r in rel.parts) or (allapot_gyoker and _alatta(p, [allapot_gyoker])):
        return False
    try:
        if _sqlite(p):
            return False
        return mediatipus.media_e(p.name) or p.stat().st_size >= NAGY_BAJT
    except OSError:
        return False


# ------------------------------------------------------------------ mentés

def ment(cfg, cel: Path, *, proba=False, log=print):
    cel = Path(cel).expanduser().resolve()
    gyokerek = forrasok(cfg)
    if not cel.is_dir():
        raise MentesHiba('A cél egy létező, csatlakoztatott mappa legyen.')
    if any(cel == p or p in cel.parents or vaultkivul.vaultban_van(cel, p) for p in gyokerek.values() if Path(p).exists()):
        raise MentesHiba('A mentés célja nem lehet a mentendő rendszerben vagy vaultban.')
    kulso = kulso_kotet(cfg, cel)
    if not kulso and not proba:
        raise MentesHiba('A teljes mentéshez külön kötet kell. Helyreállítási próbához használd a --proba kapcsolót.')
    termek = cfg.elrendezes == 'termek'
    munkater_id = cfg.workspace_id
    if termek and not (munkater_id and config.ID_MINTA.match(munkater_id)):
        raise MentesHiba('A mentéshez munkatér kell (a termék-elrendezésben a változatok munkaterenként külön mappába kerülnek).')
    tarolo = cel / TERMEK_MAPPA / munkater_id if termek else cel     # ide kerülnek a változatok (a zár, a ritkítás is itt)
    beall = cfg.section('teljes_mentes')
    megtartott = int(beall.get('megtartott', 10))
    kihagyott_k = _kihagyott_utak(cfg)
    kihagyott = set(kihagyott_k.values())
    kihagyott_m = kihagyott_kulcsok(cfg)
    mintak = _kizart_mintak(cfg, gyokerek)
    allapot_gyoker = cfg.path('state').resolve() if 'state' in cfg.utak else None
    tarolo.mkdir(parents=True, exist_ok=True)
    with _cel_zar(tarolo):
        _takarit_reszeket(tarolo, log)
        elozo, elozo_elemek = _elozo(tarolo)
        nev = 'Manifold-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        resz, kesz = tarolo / (nev + '.resz'), tarolo / nev
        resz.mkdir()
        iro = _Iro(resz, elozo, elozo_elemek)
        elemek, halasztott, utak, kodtar = [], [], {}, None

        def link_elem(p, rp):
            valodi = p.resolve()
            celnev = next(((Path('adat') / k / valodi.relative_to(g)).as_posix()
                           for k, g in gyokerek.items() if valodi == g or g in valodi.parents), None)
            if not celnev:
                raise MentesHiba(f'A külső szimbolikus link célja nincs a mentésben: {p}')
            e = {'ut': rp.as_posix(), 'tipus': 'link', 'cel': celnev}
            if _alatta(valodi, kihagyott):
                e['kihagyott_cel'] = True       # pl. a runtime-ra mutató link: a runtime fetch után él újra
            return e

        # 1. A konzisztens pillanatkép a kör-zár alatt: SQLite, git-tárak, állapot, kódtár-bundle, kis fájlok. Rövid zár
        # (81(d)): az újraépíthető `{index}` (a vault-index és a vektortár, több száz MB) nincs a mentésben, így a zár alatt
        # nem fut a `.backup()` + `quick_check`-je — a visszavonás, az átnevezés és a gépi írás közben nem kap 409-et.
        with frame.run_lock(cfg, wait=False, turelem_mp=10):
            for kulcs, forras in gyokerek.items():
                alap = Path('adat') / kulcs
                if forras.is_dir():
                    (resz / alap).mkdir(parents=True)
                    elemek.append({'ut': alap.as_posix(), 'tipus': 'mappa'})
                for p, rel in _fajlok(forras, rendszer=kulcs == 'os', kihagyott=kihagyott, mintak=mintak.get(kulcs, ())):
                    rp = alap if str(rel) == '.' else alap / rel
                    if p.is_symlink():
                        elemek.append(link_elem(p, rp))
                    elif p.is_dir():
                        (resz / rp).mkdir(parents=True, exist_ok=True)
                        elemek.append({'ut': rp.as_posix(), 'tipus': 'mappa'})
                    elif p.is_file():
                        if _halaszthato(p, rel, allapot_gyoker):
                            halasztott.append((p, rp))
                        else:
                            elemek.append(iro.fajl(p, rp))
                    else:
                        raise MentesHiba(f'Nem menthető fájltípus: {p}')
                    if len(elemek) % 500 == 0:
                        log(f'{len(elemek)} mentett elem…')
            for kulcs, p in cfg.utak.items():
                p = p.resolve()
                for k, g in gyokerek.items():
                    if p == g or g in p.parents:
                        utak[kulcs] = (Path('adat') / k / p.relative_to(g)).as_posix()
                        break
            # A forráskód története hordozható bundle; a munkafa nem commitolt forrásai fent már szerepelnek.
            if not termek and (cfg.root / '.git').exists():     # a termék csomagja újratelepíthető: nincs kódtár-bundle
                bundle = resz / 'kodtar.bundle'
                h = subprocess.run(['git', '-C', str(cfg.root), 'bundle', 'create', str(bundle), '--all'],
                                   capture_output=True, text=True, env=snapshot.hermetikus_env())
                if h.returncode:
                    raise MentesHiba('A kódtár mentése nem sikerült: ' + h.stderr[-400:])
                elemek.append({'ut': 'kodtar.bundle', 'tipus': 'fajl', 'meret': bundle.stat().st_size, 'sha256': sha(bundle), 'mod': 0o600})
                h = subprocess.run(['git', '-C', str(cfg.root), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                   check=True, env=snapshot.hermetikus_env())
                kodtar = {'head': h.stdout.strip()}
            # A ténylegesen használt konfiguráció (MOS_CONFIG esetén is) legyen a visszaállítás alapja. Termékben a csomag
            # `os.toml`-ja újratelepíthető; a felhasználó konfigurációja a telepítési és a munkatér-réteg másolata.
            if termek:
                meta = cfg.data.get('_meta') or {}
                munkater_toml = cfg.utak['workspace'] / 'workspace.toml' if 'workspace' in cfg.utak else None
                masolandok = [('settings.toml', Path(meta['settings']) if meta.get('settings') else None),
                              ('workspace.toml', munkater_toml)]
            else:
                masolandok = [('aktiv-os.toml', Path(cfg.source) if cfg.source else None)]
            for nev_, forras_ in masolandok:
                if forras_ is not None and forras_.is_file() and not forras_.is_symlink():
                    ki = resz / nev_
                    shutil.copy2(forras_, ki)
                    elemek.append({'ut': ki.name, 'tipus': 'fajl', 'meret': ki.stat().st_size, 'sha256': sha(ki), 'mod': 0o600})
        # 2. A média és a nagy fájlok a zár nélkül (a média szinte csak bővül); a változás közbeni másolás hiba.
        log(f'{len(halasztott)} nagy vagy médiafájl a kör-zár nélkül…')
        for i, (p, rp) in enumerate(halasztott, 1):
            elemek.append(iro.fajl(p, rp))
            if i % 200 == 0:
                log(f'{i}/{len(halasztott)} nagy fájl…')
        jegyzek = {'verzio': FORMATUM, 'ido': datetime.now().astimezone().isoformat(), 'proba': bool(proba),
                   'kulso_kotet': kulso, 'munkater_id': munkater_id, 'elrendezes': cfg.elrendezes, 'gyokerek': list(gyokerek),
                   'eredeti_gyokerek': {k: str(v) for k, v in gyokerek.items()}, 'kodtar': kodtar, 'utak': utak,
                   'elozo': elozo.name if elozo else None,
                   'kihagyva': [{'kulcs': k, 'eredeti_ut': str(kihagyott_k[k]), 'visszaallitas': m}
                                for k, m in kihagyott_m.items() if k in kihagyott_k],
                   'elemek': elemek}
        _json(resz / 'jegyzek.json', jegyzek)
        tartos.atomi_ir(resz / 'jegyzek.sha256', sha(resz / 'jegyzek.json').encode())
        # A linkelt fájl tartalmát az előző változat ellenőrzése igazolta (ugyanaz az inode): itt csak a mérete.
        ellenoriz(resz, reszleges=True, csak_meret=iro.linkelt)
        tartos.atomi_ir(resz / KESZ, jegyzek['ido'].encode())      # a jelölő az utolsó írás
        tartos.rename_excl(resz, kesz)
        torolt = _ritkit(tarolo, megtartott, {kesz}, log)
    r = {'ut': str(kesz), 'cel': str(cel), 'mappa': str(tarolo), 'ido': jegyzek['ido'], 'ellenorzott': True, 'kulso': kulso and not proba,
         'proba': bool(proba), 'elemek': len(elemek), 'bajt': sum(e.get('meret', 0) for e in elemek),
         'linkelt': len(iro.linkelt), 'masolt': iro.masolt, 'torolt_valtozatok': torolt,
         'kihagyva': [k['kulcs'] for k in jegyzek['kihagyva']]}
    cfg.path('state').mkdir(parents=True, exist_ok=True)
    _json(cfg.path('state') / (ALLAPOT if r['kulso'] else 'teljes-mentes-proba.json'), r)
    log(json.dumps(r, ensure_ascii=False))
    return r


# ------------------------------------------------------------------ ellenőrzés és visszaállítás

def _biztos(gyoker, rel):
    p = Path(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts or '\\' in rel:
        raise MentesHiba('Érvénytelen út a mentési jegyzékben.')
    ki = gyoker / p
    if any(x.is_symlink() for x in [ki, *ki.parents] if x == gyoker or gyoker in x.parents):
        raise MentesHiba('Váratlan szimbolikus link a mentésben vagy célban.')
    return ki


def ellenoriz(mentes: Path, *, reszleges=False, csak_meret=frozenset()):
    """A jegyzék és minden elem ellenőrzése (sha256). A `.resz` vagy `kesz` jelölő nélküli változat nem kész mentés.
    A `csak_meret` útjai (a mentés közben az előző változatból linkelt fájlok) csak méretre ellenőrződnek."""
    mentes = Path(mentes).resolve()
    if not reszleges and (mentes.name.endswith('.resz') or not (mentes / KESZ).is_file()):
        raise MentesHiba('A mentés félbeszakadt vagy befejezetlen (nincs kész jelölő).')
    if sha(_biztos(mentes, 'jegyzek.json')) != _biztos(mentes, 'jegyzek.sha256').read_text().strip():
        raise MentesHiba('Sérült mentési jegyzék.')
    d = json.loads((mentes / 'jegyzek.json').read_text())
    if d.get('verzio') != FORMATUM:
        raise MentesHiba('Ismeretlen mentési formátum.')
    latott = set()
    for e in d['elemek']:
        p = _biztos(mentes, e['ut'])
        if e['ut'] in latott:
            raise MentesHiba('Duplikált út a jegyzékben.')
        latott.add(e['ut'])
        if e['tipus'] == 'fajl':
            if not p.is_file() or p.stat().st_size != e['meret'] or (e['ut'] not in csak_meret and sha(p) != e['sha256']):
                raise MentesHiba('Hiányzó vagy sérült mentési elem: ' + e['ut'])
        elif e['tipus'] == 'mappa':
            if not p.is_dir():
                raise MentesHiba('Hiányzó mappa: ' + e['ut'])
        elif e['tipus'] == 'link':
            _biztos(mentes, e['cel'])
        else:
            raise MentesHiba('Ismeretlen mentési elemtípus.')
    for e in d['elemek']:
        if e['tipus'] == 'link' and not e.get('kihagyott_cel') and e['cel'] not in latott:
            raise MentesHiba('A link célja nincs a mentési jegyzékben: ' + e['ut'])
    for v in d['utak'].values():
        _biztos(mentes, v)
    return d


def visszaallit(mentes: Path, cel: Path):
    mentes = _valtozat(mentes)
    d = ellenoriz(mentes)
    cel = Path(cel).expanduser().resolve()
    if cel.exists() and (not cel.is_dir() or any(cel.iterdir())):
        raise MentesHiba('Visszaállítás csak üres célmappába végezhető.')
    if cel == mentes or mentes in cel.parents:
        raise MentesHiba('A visszaállítás célja nem lehet a mentésben.')
    cel.mkdir(parents=True, exist_ok=True)

    def ut(rel):
        p = Path(rel)
        if p.parts[0] != 'adat':
            return _biztos(cel, rel)
        nev = 'Manifold-OS' if p.parts[1] == 'os' else 'Manifold' if p.parts[1] == 'vault' else p.parts[1]
        return _biztos(cel, (Path(nev) / Path(*p.parts[2:])).as_posix())
    for e in d['elemek']:
        if e['tipus'] == 'link':
            continue
        p = ut(e['ut'])
        if e['tipus'] == 'mappa':
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Másolat, nem link: a visszaállított fájl írása soha nem hathat vissza a mentésre.
            shutil.copyfile(mentes / e['ut'], p)
            p.chmod(e.get('mod', 0o600))
            if sha(p) != e['sha256']:
                raise MentesHiba('Másolási hiba: ' + e['ut'])
    # A konfiguráció útjait a linkek létrehozása előtt ellenőrizzük.
    konfiguracio_utak = {k: ut(v) for k, v in d['utak'].items()}
    # Linkek utoljára; a célút csak a már ellenőrzött mentési jegyzékből származhat.
    for e in d['elemek']:
        if e['tipus'] == 'link':
            p = ut(e['ut']); p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(os.path.relpath(ut(e['cel']), p.parent))
    osroot = cel / 'Manifold-OS'
    # A kódtár története is használható marad. A mentett munkafát soha nem checkout-oljuk felül.
    if d.get('kodtar'):
        def git(*args):
            h = subprocess.run(['git', '-C', str(osroot), *args], capture_output=True, text=True,
                               env=snapshot.hermetikus_env())
            if h.returncode:
                raise MentesHiba('A kódtár visszaállítása nem sikerült: ' + h.stderr[-400:])
        git('init')
        git('fetch', str(mentes / 'kodtar.bundle'), '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*')
        # update-ref/read-tree csak a referenciát és az indexet állítja: az elmentett, akár módosult forrás megmarad.
        git('symbolic-ref', 'HEAD', 'refs/heads/codex/visszaallitott')
        git('update-ref', 'HEAD', d['kodtar']['head'])
        git('read-tree', 'HEAD')
    cfg = osroot / 'config/os.toml'
    if (mentes / 'aktiv-os.toml').is_file():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mentes / 'aktiv-os.toml', cfg)
    if cfg.exists():
        sz = cfg.read_text()
        fej = re.search(r'(?m)^\[utak\][ \t]*$', sz)
        if not fej:
            raise MentesHiba('A konfigurációból hiányzik az [utak] szakasz.')
        a = fej.start(); b = sz.find('\n[', fej.end())
        regi = sz[a:b if b >= 0 else len(sz)]
        for k, v in konfiguracio_utak.items():
            hely = '{os}/' + os.path.relpath(v, osroot)
            regi = re.sub(r'(?m)^' + re.escape(k) + r'\s*=.*$', lambda _: k + ' = ' + json.dumps(hely, ensure_ascii=False), regi)
        sz = sz[:a] + regi + (sz[b:] if b >= 0 else '')
        tartos.atomi_ir(cfg, sz.encode())
        # A külső git-könyvtár core.worktree-ja soha ne mutasson vissza a régi gépre.
        uj = config.load({'MOS_ROOT': str(osroot), 'HOME': str(cel / 'home')})
        for repo in snapshot.repos(uj).values():
            if repo.git_dir.is_dir():
                repo.git('config', 'core.worktree', str(repo.work_tree))
    teendok = [k['visszaallitas'] for k in d.get('kihagyva', [])]
    r = {'ok': True, 'cel': str(cel), 'elemek': len(d['elemek']), 'forras': str(mentes), 'teendok': teendok}
    _json(cel / 'VISSZAALLITVA.json', r)
    return r


# ------------------------------------------------------------------ állapot és lemezfigyelő

def _ido_mp(ido) -> float | None:
    try:
        return datetime.fromisoformat(ido).timestamp()
    except (TypeError, ValueError):
        return None


def allapot(cfg):
    beall = cfg.section('teljes_mentes')
    figyelo = {'figyelo_be': bool(beall.get('figyelo_be')), 'figyelo_cel': beall.get('cel') or None}
    try:
        d = json.loads((cfg.path('state') / ALLAPOT).read_text())
        d['csatlakoztatva'] = (Path(d['ut']) / KESZ).is_file()
        return {**d, **figyelo}
    except (OSError, ValueError, KeyError, TypeError):
        return {'ellenorzott': False, 'kulso': False, 'csatlakoztatva': False, 'ido': None, **figyelo}


class LemezFigyelo:
    """Opcionális (`[teljes_mentes] figyelo_be`, alapból ki): ha a futó app mellett a `cel` kötete csatlakoztatva van,
    és az utolsó ellenőrzött teljes mentés `figyelo_ora`-nál régebbi, sorba állít egy `teljes_mentes` feladatot.
    Az indulási szünet (`[feladatsor] indulasi_szunet_mp`, D8) előtt nem néz; egy beküldés után egy óráig nem küld újat.
    A bekötése: a core indulásakor `LemezFigyelo(cfg, queue).indit()`, leálláskor `leallit()`."""

    KULDES_SZUNET_MP = 3600.0
    NEZES_MP = 60.0

    def __init__(self, cfg, queue, ora=time.time, indulasi_kesleltetes_mp: float | None = None, log=print):
        self.cfg, self.queue, self.ora, self.log = cfg, queue, ora, log
        szunet = cfg.section('feladatsor').get('indulasi_szunet_mp', 180)
        self.kezdet = self.ora() + float(szunet if indulasi_kesleltetes_mp is None else indulasi_kesleltetes_mp)
        self._utolso_kuldes = None
        self._leall = threading.Event()
        self._szal = None

    def tick(self) -> bool:
        b = self.cfg.section('teljes_mentes')
        cel = str(b.get('cel') or '').strip()
        most = self.ora()
        if not b.get('figyelo_be') or not cel or most < self.kezdet:
            return False
        if self._utolso_kuldes is not None and most - self._utolso_kuldes < self.KULDES_SZUNET_MP:
            return False
        ut = Path(cel).expanduser()
        try:
            if not ut.is_dir() or not kulso_kotet(self.cfg, ut):
                return False                     # a kötet nincs csatlakoztatva (vagy a cél nem külön kötet: nem a vaulté és a `{var}`-é)
        except OSError:
            return False
        a = allapot(self.cfg)
        utolso = _ido_mp(a.get('ido')) if a.get('ellenorzott') and a.get('kulso') else None
        if utolso is not None and most - utolso < float(b.get('figyelo_ora', 24)) * 3600:
            return False
        if self.queue.fuggo('teljes_mentes'):
            return False
        self.queue.submit('teljes_mentes', {'cel': str(ut)})
        self._utolso_kuldes = most
        self.log('[teljes mentés] a mentési lemez csatlakoztatva, a mentés sorba állítva')
        return True

    def indit(self) -> None:
        if self._szal is not None:
            return

        def fut():
            while not self._leall.wait(self.NEZES_MP):
                try:
                    self.tick()
                except Exception as e:  # noqa: BLE001 — a figyelő nem halhat meg egy hibától
                    self.log(f'[teljes mentés] a lemezfigyelő hibája: {e}')
        self._szal = threading.Thread(target=fut, name='teljes-mentes-figyelo', daemon=True)
        self._szal.start()

    def leallit(self) -> None:
        self._leall.set()
        if self._szal is not None:
            self._szal.join(5)
            self._szal = None


def utvonalak(r):
    r.get('/api/mentes/teljes', lambda k: allapot(k.app.cfg))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('muvelet', choices=['ment', 'ellenoriz', 'visszaallit'])
    p.add_argument('ut', help='ment: a célmappa; ellenoriz/visszaallit: egy változat vagy a célmappa (a legutóbbi kész)')
    p.add_argument('cel', nargs='?', help='visszaallit: az üres célmappa')
    p.add_argument('--proba', action='store_true')
    a = p.parse_args()
    try:
        if a.muvelet == 'ment':
            ment(config.load(), Path(a.ut), proba=a.proba)
        elif a.muvelet == 'ellenoriz':
            v = _valtozat(Path(a.ut))
            print(json.dumps({'ok': True, 'valtozat': str(v), 'elemek': len(ellenoriz(v)['elemek'])}, ensure_ascii=False))
        else:
            if not a.cel:
                p.error('A célmappa kötelező.')
            print(json.dumps(visszaallit(Path(a.ut), Path(a.cel)), ensure_ascii=False))
        return 0
    except (MentesHiba, OSError, sqlite3.Error, frame.Busy) as e:
        print('A művelet nem sikerült: ' + str(e), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
