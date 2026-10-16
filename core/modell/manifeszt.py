"""A modell-manifeszt (`config/models.toml`, F6) és a modellek lemezről számolt telepítettsége.

Csak olvas (a törlés kivételével, amely kizárólag a `{models}` alatt, a modell saját repó-mappájában dolgozik). Hálózat nincs.

Telepítettség (`allapot`), mindig a lemezről:
  - `nincs`              — a repó-mappa nincs meg;
  - `reszleges`          — a rögzített revízió pillanatképe vagy egy félbehagyott (`*.incomplete`) blob van, de nincs teljes,
                           ellenőrzött letöltés (a letöltés folytatható);
  - `ellenorizetlen`     — a rögzített revízió pillanatképe megvan, de a Manifold nem ellenőrizte (régi CLI-letöltés, v2-import):
                           használható; a „Download” ellenőrzi (a hiányzót letölti, a meglévőt hash-sel veti össze);
  - `kesz`               — a letöltő nyugtája (`{models}/manifold/<id>.json`) a rögzített revízióra szól, és minden fájl a nyugta
                           méretével megvan;
  - `elter_revizio`      — csak más revízió pillanatképe van (a régi letöltés; újra kell tölteni);
  - `konvertalasra_var`  — kész/ellenőrizetlen, de a modell nem MLX-formátumú (`konvertalas = true`): nem tölthető be.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from . import revizio

AZONOSITO = re.compile(r"^[a-z0-9_]{1,64}$")
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
ALLAPOTOK = ("nincs", "reszleges", "ellenorizetlen", "kesz", "elter_revizio", "konvertalasra_var")
HASZNALHATO = ("kesz", "ellenorizetlen")
SZEREPEK = ("szoveg", "kep", "hang", "beagyazas", "rerank")


class ManifesztHiba(ValueError):
    """A manifeszt hibás vagy a kért modell nincs benne. `kod` + `param`: a hibaszerződés."""

    def __init__(self, kod: str, uzenet: str, **param):
        super().__init__(uzenet)
        self.kod, self.param = kod, param


def ut(cfg) -> Path:
    """A szállított manifeszt: a kódfa `config/models.toml`-ja (a termékben csak olvasott)."""
    return Path(cfg.root) / "config" / "models.toml"


def betolt(cfg=None, fajl: Path | None = None) -> dict:
    """A manifeszt validálva: `{forras, modell, feladat, funkcio, kalibracio}`."""
    p = Path(fajl) if fajl else ut(cfg)
    try:
        with open(p, "rb") as f:
            d = tomllib.load(f)
    except FileNotFoundError as e:
        raise ManifesztHiba("modell.manifeszt_hianyzik", f"a modell-manifeszt nem található: {p}") from e
    except tomllib.TOMLDecodeError as e:
        raise ManifesztHiba("modell.manifeszt_hibas", f"a modell-manifeszt hibás: {e}") from e
    ki = {"forras": dict(d.get("forras") or {}), "modell": dict(d.get("modell") or {}), "feladat": dict(d.get("feladat") or {}),
          "funkcio": dict(d.get("funkcio") or {}), "kalibracio": dict(d.get("kalibracio") or {})}
    for nev, m in ki["modell"].items():
        if not AZONOSITO.match(nev):
            raise ManifesztHiba("modell.manifeszt_hibas", f"hibás modell-azonosító: {nev}")
        if not isinstance(m.get("repo"), str) or not REPO.match(m["repo"]) or ".." in m["repo"]:
            raise ManifesztHiba("modell.manifeszt_hibas", f"{nev}: hibás repó: {m.get('repo')!r}")
        rev = str(m.get("revizio") or "")
        if not revizio.SHA.match(rev):
            raise ManifesztHiba("modell.manifeszt_hibas", f"{nev}: a `revizio` nem 40 jegyű commit-sha")
        if m.get("szerep") not in SZEREPEK:
            raise ManifesztHiba("modell.manifeszt_hibas", f"{nev}: ismeretlen szerep: {m.get('szerep')!r}")
        if not isinstance(m.get("nyelvek"), list) or not m["nyelvek"]:
            raise ManifesztHiba("modell.manifeszt_hibas", f"{nev}: a `nyelvek` nem üres lista")
    return ki


def modell(man: dict, nev: str) -> dict:
    if not isinstance(nev, str) or not AZONOSITO.match(nev) or nev not in man["modell"]:
        raise ManifesztHiba("modell.ismeretlen", f"ismeretlen modell: {nev}", modell=str(nev)[:64])
    return man["modell"][nev]


# ---------------------------------------------------------------------- forrás és host-ellenőrzés (D3)

def _host_illik(host: str, minta: str) -> bool:
    host, minta = host.lower().rstrip("."), minta.lower()
    if minta.startswith("*."):
        return host.endswith(minta[1:]) and len(host) > len(minta) - 1
    return host == minta


def host_engedelyezett(man: dict, url: str) -> bool:
    """HTTPS és a manifeszt `[forras] hostok` listáján lévő host (a `*.x` bármely aldomainre illik); port és felhasználó nincs."""
    try:
        r = urlsplit(url)
    except ValueError:
        return False
    if r.scheme != "https" or not r.hostname or r.username or r.password:
        return False
    if r.port not in (None, 443):
        return False
    return any(_host_illik(r.hostname, h) for h in (man["forras"].get("hostok") or []))


def vegpont(man: dict) -> str:
    """A letöltés végpontja; hibát dob, ha a forrás nem a támogatott fajta, vagy a végpont nem engedélyezett."""
    f = man["forras"]
    if f.get("tipus") != "huggingface":
        raise ManifesztHiba("modell.forras_tiltott", "a modell forrása nem támogatott", forras=str(f.get("tipus")))
    u = str(f.get("vegpont") or "")
    if not host_engedelyezett(man, u):
        raise ManifesztHiba("modell.host_tiltott", f"a letöltési végpont nem engedélyezett: {u}", host=urlsplit(u).hostname or "")
    return u.rstrip("/")


# ---------------------------------------------------------------------- lemez

def nyugta_ut(models: Path, nev: str) -> Path:
    return Path(models) / "manifold" / f"{nev}.json"


def nyugta(models: Path, nev: str) -> dict | None:
    try:
        d = json.loads(nyugta_ut(models, nev).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def minta_illik(nev: str, minta: list | tuple | None) -> bool:
    return not minta or any(fnmatch.fnmatch(nev, p) for p in minta)


def _lemez(mappa: Path) -> tuple[int, int]:
    """(bájt, fájlszám) a mappa valódi fájljain (a symlinkeket nem követi: a blobok egyszer számítanak)."""
    osszes = db = 0
    lattuk: set = set()
    for gy, _, fajlok in os.walk(mappa):
        for f in fajlok:
            p = Path(gy) / f
            try:
                st = p.lstat()
            except OSError:
                continue
            if p.is_symlink() or (st.st_ino, st.st_dev) in lattuk:
                continue
            lattuk.add((st.st_ino, st.st_dev))
            osszes += st.st_size
            db += 1
    return osszes, db


def telepitettseg(models: Path, nev: str, m: dict) -> dict:
    """`{allapot, lemez_bajt, ellenorizve, revizio}` a lemezről (a modul leírása szerint)."""
    models = Path(models)
    repo_d = revizio.repo_mappa(models, m["repo"])
    rev = str(m["revizio"])
    if not repo_d.is_dir():
        return {"allapot": "nincs", "lemez_bajt": 0, "ellenorizve": None, "revizio": rev}
    lemez, _ = _lemez(repo_d)
    snap = repo_d / "snapshots" / rev
    ny = nyugta(models, nev)
    felbe = any((repo_d / "blobs").glob("*.incomplete")) if (repo_d / "blobs").is_dir() else False
    if snap.is_dir():
        if ny and ny.get("revizio") == rev and not felbe and _nyugta_teljes(snap, ny):
            allapot = "kesz"
        elif ny and ny.get("revizio") == rev:
            allapot = "reszleges"                      # nyugta van, de fájl hiányzik vagy a méret eltér: a letöltés pótolja
        else:
            allapot = "reszleges" if felbe or (ny and ny.get("allapot") == "folyamatban") else "ellenorizetlen"
    elif felbe or (ny and ny.get("revizio") == rev):
        allapot = "reszleges"
    elif (repo_d / "snapshots").is_dir() and any((repo_d / "snapshots").iterdir()):
        allapot = "elter_revizio"
    else:
        allapot = "reszleges" if lemez else "nincs"
    if allapot in HASZNALHATO and m.get("konvertalas"):
        allapot = "konvertalasra_var"
    return {"allapot": allapot, "lemez_bajt": lemez,
            "ellenorizve": ny.get("ellenorizve") if ny and allapot == "kesz" else None, "revizio": rev}


def _nyugta_teljes(snap: Path, ny: dict) -> bool:
    fajlok = ny.get("fajlok")
    if ny.get("allapot") != "kesz" or not isinstance(fajlok, list) or not fajlok:
        return False
    for f in fajlok:
        p = snap / str(f.get("nev", ""))
        try:
            if not p.is_file() or p.stat().st_size != int(f.get("meret", -1)):
                return False
        except (OSError, ValueError):
            return False
    return True


def torol(models: Path, nev: str, m: dict) -> dict:
    """A modell repó-mappája és nyugtája törlődik (csak a `{models}/hub` alatt). → `{felszabadult_bajt}`.

    A modellfájlok újra letölthető telepítési gyorsítótár, nem felhasználói adat: nem a Kukába kerülnek. Ha a manifesztben
    másik modell is ugyanezt a repót használja, a hívó dönt (`megosztott_repo`)."""
    models = Path(models).resolve()
    hub = (models / "hub").resolve()
    repo_d = revizio.repo_mappa(models, m["repo"])
    cel = repo_d.resolve() if repo_d.exists() else repo_d
    if cel.parent != hub or not cel.name.startswith("models--") or repo_d.is_symlink():
        raise ManifesztHiba("modell.torles_tiltott", "a modell mappája nem a modelltárban van", modell=nev)
    felszabadult = _lemez(cel)[0] if cel.is_dir() else 0
    if cel.is_dir():
        shutil.rmtree(cel)
    try:
        nyugta_ut(models, nev).unlink()
    except FileNotFoundError:
        pass
    return {"felszabadult_bajt": felszabadult}


def megosztott_repo(man: dict, nev: str) -> list[str]:
    repo = man["modell"][nev]["repo"]
    return sorted(n for n, m in man["modell"].items() if n != nev and m["repo"] == repo)


def kalibracio_konfig(cfg) -> dict:
    """A manifeszt `[kalibracio.*]` szakasza (csak szigoríthat: `kuszob.hatalyos`); hiányzó/hibás manifeszt: üres."""
    try:
        return betolt(cfg)["kalibracio"]
    except ManifesztHiba:
        return {}
