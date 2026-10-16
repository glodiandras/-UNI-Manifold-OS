"""Modell-letöltő: a `config/models.toml` (F6-manifeszt) modelljeit tölti le a {models} alá (HF_HOME).

A D3 szerint a letöltés egyszeri, jóváhagyott hálózati lépés: indulás előtt a név- és mérettel
ellátott lista megjelenik, és csak kifejezett igen után indul. Modellt nem tölt be és nem
konvertál: az a modellgazda (C05) dolga. Megszakítás után újraindítható; a kész fájlokat a
huggingface_hub nem tölti le újra.

Használat (a bin/mos-on át):
    mos letoltes                 # az első kör
    mos letoltes opcionalis      # az opcionális kör
    mos letoltes mind            # mindkettő
    mos letoltes glm_ocr parakeet_v3   # név szerint
    mos letoltes --lista         # csak a lista, letöltés nélkül
    mos letoltes --igen          # kérdés nélkül (a lista ekkor is kiíródik)
    mos letoltes mind --token    # bekéri a HF-tokent (nem látszik, nem kerül fájlba és előzménybe)

Gyorsítás: a Xet nagy teljesítményű módja (HF_XET_HIGH_PERFORMANCE=1) és 16 párhuzamos fájl alapból
bekapcsolva; a token a HF sebességkorlátját emeli. A token csak a folyamat memóriájában él.

**Feladatként (F6, a Model Manager háttere)**: `python -m core.letoltes --feladat <modell>` a feladatsor lépése (csak a
`POST /api/modellek/<id>/letoltes` indítja, felhasználói kérésre). Fájlonként tölt (`hf_hub_download`, a rögzített revízión),
`[manifold-progress]` haladással, a stop-fájlra a folyó fájl után megáll; a félbehagyott fájl (`*.incomplete`) a következő
indításkor folytatódik. Minden fájl ellenőrzött (LFS: sha256 = a blob neve; egyéb: git blob sha1), az eltérő fájl törlődik. Csak a
manifeszt `[forras] hostok` HTTPS-hostjai érhetők el (kérés-horog, az átirányításokra is; a Xet-átvitel ki van kapcsolva, hogy minden
kérés ezen menjen át). Csak a `{models}` alá ír; a végén nyugta: `{models}/manifold/<id>.json`.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import tomllib
from pathlib import Path

from core import config
from core.modell import manifeszt, revizio

CSOPORTOK = ("elso", "opcionalis", "mind")
PARHUZAMOS_FAJL = 16


class LetoltesHiba(RuntimeError):
    """`kod` + `param`: a hibaszerződés (a Model Manager ebből fordít)."""

    def __init__(self, uzenet: str, kod: str = "modell.letoltes_hiba", **param):
        super().__init__(uzenet)
        self.kod, self.param = kod, param


def jeloltek_betoltese(ut: Path) -> dict[str, dict]:
    try:
        with open(ut, "rb") as f:
            return tomllib.load(f).get("modell", {})
    except FileNotFoundError as exc:
        raise LetoltesHiba(f"a letöltési lista nem található: {ut}") from exc


def valasztas(modellek: dict[str, dict], kerdes: list[str]) -> list[str]:
    """A kért csoport(ok) vagy nevek → letöltendő nevek, sorrendtartóan; a meglévők kimaradnak."""
    kerdes = kerdes or ["elso"]
    nevek: list[str] = []
    for k in kerdes:
        if k in CSOPORTOK:
            korok = {"elso", "opcionalis"} if k == "mind" else {k}
            talalat = [n for n, m in modellek.items() if m.get("kor") in korok]
        elif k in modellek:
            talalat = [k]
        else:
            raise LetoltesHiba(f"ismeretlen modell vagy csoport: {k}")
        nevek += [n for n in talalat if n not in nevek]
    return [n for n in nevek if not modellek[n].get("megvan")]


def lista_szoveg(modellek: dict[str, dict], nevek: list[str]) -> str:
    sorok = [f"{'név':<26} {'repó':<58} {'GB':>6}"]
    for n in nevek:
        m = modellek[n]
        jel = "  (konvertálás kell)" if m.get("konvertalas") else ""
        sorok.append(f"{n:<26} {m['repo']:<58} {m['meret_gb']:>6.2f}{jel}")
    osszes = sum(modellek[n]["meret_gb"] for n in nevek)
    sorok.append(f"{'összesen':<85} {osszes:>6.2f} GB  ({len(nevek)} modell)")
    return "\n".join(sorok)


def letolt(modellek: dict[str, dict], nevek: list[str], cache_dir: Path, naplo: Path,
           letolto=None, token: str | None = None) -> dict[str, str]:
    """Modellenként letölt; egy hiba nem állítja meg a többit. Eredmény: név → 'kész' | hibaüzenet."""
    if letolto is None:
        from huggingface_hub import snapshot_download as letolto
    eredmeny: dict[str, str] = {}
    for i, n in enumerate(nevek, 1):
        m = modellek[n]
        print(f"\n[{i}/{len(nevek)}] {n} — {m['repo']} ({m['meret_gb']:.2f} GB)", flush=True)
        rev = m.get("revizio") or None
        try:
            # C19 (T141): a rögzített commit (`revizio`) töltődik, nem a pillanatnyi főág
            ut = letolto(repo_id=m["repo"], allow_patterns=m.get("minta"), cache_dir=str(cache_dir),
                         max_workers=PARHUZAMOS_FAJL, token=token, revision=rev)
            if rev and Path(str(ut)).name != rev:
                raise LetoltesHiba(f"a letöltött pillanatkép ({Path(str(ut)).name}) nem a rögzített revízió ({rev})")
            main = revizio.helyi_main(cache_dir.parent if cache_dir.name == "hub" else cache_dir, m["repo"])
            if rev and main and main != rev:
                print(f"  FIGYELEM: a helyi refs/main ({main[:12]}) eltér a rögzített revíziótól ({rev[:12]}); a betöltő a "
                      "rögzítettet tölti (doctor: main_elter)", flush=True)
            eredmeny[n] = "kész"
        except KeyboardInterrupt:
            eredmeny[n] = "megszakítva"
            _naplo_iras(naplo, modellek, eredmeny)
            raise
        except Exception as exc:  # hálózati, jogosultsági vagy tárhelyhiba: jelentjük, megyünk tovább
            eredmeny[n] = f"hiba: {exc}"
            print(f"  HIBA: {exc}", file=sys.stderr, flush=True)
        _naplo_iras(naplo, modellek, eredmeny)
    return eredmeny


def _naplo_iras(naplo: Path, modellek: dict[str, dict], eredmeny: dict[str, str]) -> None:
    naplo.parent.mkdir(parents=True, exist_ok=True)
    adat = {n: {"repo": modellek[n]["repo"], "meret_gb": modellek[n]["meret_gb"], "eredmeny": e}
            for n, e in eredmeny.items()}
    tmp = naplo.with_name(f".{naplo.name}.manifold-tmp")
    tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, naplo)


def main(argv: list[str] | None = None, bemenet=input, jelszokero=getpass.getpass) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["--feladat"]:
        return feladat_main(argv[1:])
    p = argparse.ArgumentParser(prog="mos letoltes", description="Modellek letöltése a config/models.toml szerint.")
    p.add_argument("mit", nargs="*", help="elso | opcionalis | mind | modellnév … (alap: elso)")
    p.add_argument("--lista", action="store_true", help="csak kiírja a listát, nem tölt le")
    p.add_argument("--igen", action="store_true", help="nem kérdez rá (a lista ekkor is kiíródik)")
    p.add_argument("--token", action="store_true", help="bekéri a Hugging Face read-tokent (rejtett bevitel)")
    a = p.parse_args(argv)

    try:
        cfg = config.load()
        modellek = jeloltek_betoltese(Path(os.environ.get("MOS_LETOLTES") or manifeszt.ut(cfg)))
        for n, m in modellek.items():             # F6: a „megvan” a lemezről (a kézi jelző csak régi listában él)
            if "megvan" not in m and m.get("revizio"):
                m["megvan"] = manifeszt.telepitettseg(cfg.path("models"), n, m)["allapot"] in manifeszt.HASZNALHATO
        nevek = valasztas(modellek, a.mit)
    except (config.ConfigError, LetoltesHiba) as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 2

    if not nevek:
        print("Nincs letöltendő modell (a kért tételek már megvannak).")
        return 0
    print(lista_szoveg(modellek, nevek))
    if a.lista:
        return 0

    models = cfg.path("models")
    cache_dir = models / "hub"
    cache_dir.mkdir(parents=True, exist_ok=True)
    szukseges = sum(modellek[n]["meret_gb"] for n in nevek) * 1e9
    szabad = shutil.disk_usage(cache_dir).free
    print(f"\nCél: {cache_dir}  (szabad: {szabad / 1e9:.1f} GB)")
    if szabad < szukseges * 1.05:
        print(f"HIBA: nincs elég hely ({szukseges / 1e9:.1f} GB kell).", file=sys.stderr)
        return 2

    if not a.igen:
        valasz = bemenet("Letöltöd? [i/N] ").strip().lower()
        if valasz not in ("i", "igen", "y", "yes"):
            print("Megszakítva, semmi nem töltődött le.")
            return 1

    token = None
    if a.token:
        token = jelszokero("HF-token (nem látszik; Enter = token nélkül): ").strip() or None
        if token and not token.startswith("hf_"):
            print("HIBA: ez nem HF-token (hf_ kezdetű kell).", file=sys.stderr)
            return 2
    # a Xet a modul betöltésekor olvassa a beállítást, ezért az import (a letolt-ben) előtt kell
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

    naplo = cfg.path("runs") / f"letoltes-{time.strftime('%Y%m%d-%H%M%S')}.json"
    try:
        eredmeny = letolt(modellek, nevek, cache_dir, naplo, token=token)
    except KeyboardInterrupt:
        print(f"\nMegszakítva. Újraindítva onnan folytatja, ahol abbahagyta. Napló: {naplo}")
        return 130
    hibak = {n: e for n, e in eredmeny.items() if e != "kész"}
    print(f"\nKész: {len(eredmeny) - len(hibak)}/{len(eredmeny)}. Napló: {naplo}")
    for n, e in hibak.items():
        print(f"  {n}: {e}", file=sys.stderr)
    konv = [n for n in nevek if modellek[n].get("konvertalas") and eredmeny.get(n) == "kész"]
    if konv:
        print("MLX-konvertálásra vár (a modellgazda végzi): " + ", ".join(konv))
    return 1 if hibak else 0


# ====================================================================== F6: letöltés feladatként

HALADAS_MP = 1.0
TARTALEK = 1.05


class HfForras:
    """A Hugging Face hub a manifeszt végpontján, host-kapuval. A hálózatot csak ez az osztály éri el (D3)."""

    def __init__(self, man: dict, token: str | None = None):
        self.man = man
        self.vegpont = manifeszt.vegpont(man)
        self.token = token
        self._kliens_beallit()

    def _kliens_beallit(self) -> None:
        import httpx
        from huggingface_hub import set_client_factory
        from huggingface_hub.utils._http import hf_request_event_hook
        man = self.man

        def kapu(request) -> None:
            if not manifeszt.host_engedelyezett(man, str(request.url)):
                raise LetoltesHiba(f"tiltott host: {request.url.host}", "modell.host_tiltott", host=str(request.url.host))

        set_client_factory(lambda: httpx.Client(event_hooks={"request": [kapu, hf_request_event_hook]},
                                                follow_redirects=True, timeout=None))

    def fajlok(self, repo: str, rev: str, minta) -> list[dict]:
        from huggingface_hub import HfApi
        info = HfApi(endpoint=self.vegpont, token=self.token).model_info(repo, revision=rev, files_metadata=True)
        ki = []
        for s in info.siblings or []:
            lfs = getattr(s, "lfs", None)
            sha = (lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)) if lfs else None
            ki.append({"nev": s.rfilename, "meret": int(s.size or 0), "sha256": sha, "blob_id": getattr(s, "blob_id", None)})
        return ki

    def letolt(self, repo: str, rev: str, nev: str, cache_dir: Path) -> Path:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(repo_id=repo, filename=nev, revision=rev, cache_dir=str(cache_dir), endpoint=self.vegpont,
                                    token=self.token))


def _git_sha1(p: Path) -> str:
    h = hashlib.sha1()
    h.update(f"blob {p.stat().st_size}\0".encode())
    with open(p, "rb") as f:
        for d in iter(lambda: f.read(1 << 20), b""):
            h.update(d)
    return h.hexdigest()


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for d in iter(lambda: f.read(1 << 20), b""):
            h.update(d)
    return h.hexdigest()


def fajl_ellenoriz(p: Path, f: dict) -> bool:
    """A letöltött fájl a forrás metaadata szerint: méret, és LFS-nél sha256, különben git blob sha1 (ha ismert)."""
    try:
        if not p.is_file() or (f.get("meret") and p.stat().st_size != int(f["meret"])):
            return False
        if f.get("sha256"):
            return _sha256(p) == str(f["sha256"]).lower()
        if f.get("blob_id"):
            return _git_sha1(p) == str(f["blob_id"]).lower()
        return True
    except OSError:
        return False


def _biztonsagos_nev(nev: str) -> bool:
    return bool(nev) and not nev.startswith("/") and "\\" not in nev and "\x00" not in nev and \
        all(r not in ("", ".", "..") for r in nev.split("/"))


def _alatta(p: Path, gyoker: Path) -> bool:
    try:
        p.resolve().relative_to(gyoker.resolve())
        return True
    except (OSError, ValueError):
        return False


def _nyugta_ir(models: Path, nev: str, adat: dict) -> None:
    ut = manifeszt.nyugta_ut(models, nev)
    ut.parent.mkdir(parents=True, exist_ok=True)
    tmp = ut.with_name(f".{ut.name}.manifold-tmp")
    tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ut)


def _torol_rossz(p: Path, models: Path) -> None:
    """Az eltérő hash-ű fájl (a snapshot-link és a blob) törlése, csak a `{models}` alatt."""
    for x in {p, p.resolve()}:
        if _alatta(x.parent, models):
            try:
                x.unlink()
            except OSError:
                pass


def modell_letolt(cfg, nev: str, forras=None, stop=lambda: False, log=print, man: dict | None = None,
                  szabad=lambda d: shutil.disk_usage(d).free) -> dict:
    """Egy manifeszt-modell letöltése/ellenőrzése. → `{allapot: kesz | megszakitva, fajlok, bajt}`; hibánál `LetoltesHiba`."""
    man = man or manifeszt.betolt(cfg)
    m = manifeszt.modell(man, nev)
    models = Path(cfg.path("models"))
    cache = models / "hub"
    cache.mkdir(parents=True, exist_ok=True)
    if forras is None:
        forras = HfForras(man)
    rev = str(m["revizio"])
    fajlok = [f for f in forras.fajlok(m["repo"], rev, m.get("minta")) if manifeszt.minta_illik(f["nev"], m.get("minta"))]
    if not fajlok:
        raise LetoltesHiba(f"{nev}: a forrásban nincs letölthető fájl", "modell.nincs_fajl", modell=nev)
    rossz = [f["nev"] for f in fajlok if not _biztonsagos_nev(str(f["nev"]))]
    if rossz:
        raise LetoltesHiba(f"{nev}: tiltott fájlnév a forrásban: {rossz[0]}", "modell.tiltott_fajlnev", modell=nev)
    snap = revizio.repo_mappa(models, m["repo"]) / "snapshots" / rev
    osszes = sum(int(f.get("meret") or 0) for f in fajlok)
    meglevo = sum(int(f.get("meret") or 0) for f in fajlok if (snap / f["nev"]).is_file())
    kell = (osszes - meglevo) * TARTALEK
    if kell > 0 and szabad(cache) < kell:
        raise LetoltesHiba(f"nincs elég hely: {kell / 1e9:.1f} GB kell", "modell.nincs_hely", szukseges_gb=round(kell / 1e9, 2))
    _nyugta_ir(models, nev, {"revizio": rev, "repo": m["repo"], "allapot": "folyamatban", "indult": time.strftime("%Y-%m-%dT%H:%M:%S")})

    kesz_bajt = [0]
    blobs = revizio.repo_mappa(models, m["repo"]) / "blobs"
    vege = threading.Event()

    def haladas() -> None:
        while not vege.wait(HALADAS_MP):
            try:
                felbe = sum(p.stat().st_size for p in blobs.glob("*.incomplete")) if blobs.is_dir() else 0
            except OSError:
                felbe = 0
            print(f"[manifold-progress] {min(99.9, 100.0 * (kesz_bajt[0] + felbe) / max(osszes, 1)):.1f}%", flush=True)

    figyelo = threading.Thread(target=haladas, daemon=True)
    figyelo.start()
    try:
        for i, f in enumerate(fajlok, 1):
            if stop():
                log(f"[letöltés] {nev}: megállítva ({i - 1}/{len(fajlok)} fájl kész); folytatható")
                return {"allapot": "megszakitva", "fajlok": i - 1, "bajt": kesz_bajt[0]}
            cel = snap / f["nev"]
            if cel.is_file() and fajl_ellenoriz(cel, f):
                kesz_bajt[0] += int(f.get("meret") or 0)
                continue
            log(f"[letöltés] {nev}: {f['nev']} ({int(f.get('meret') or 0) / 1e6:.1f} MB)")
            p = Path(forras.letolt(m["repo"], rev, f["nev"], cache))
            if not _alatta(p, models):
                raise LetoltesHiba(f"{nev}: a letöltött fájl a modelltáron kívül van", "modell.tiltott_fajlnev", modell=nev)
            if not fajl_ellenoriz(p, f):
                _torol_rossz(p, models)
                raise LetoltesHiba(f"{nev}: a(z) {f['nev']} ellenőrzőösszege eltér (törölve)", "modell.hash_elter",
                                   modell=nev, fajl=str(f["nev"])[:200])
            kesz_bajt[0] += int(f.get("meret") or 0)
            print(f"[manifold-progress] {100.0 * kesz_bajt[0] / max(osszes, 1):.1f}%", flush=True)
    finally:
        vege.set()
        figyelo.join(timeout=2)
    _nyugta_ir(models, nev, {"revizio": rev, "repo": m["repo"], "allapot": "kesz",
                             "ellenorizve": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "fajlok": [{"nev": f["nev"], "meret": int(f.get("meret") or 0),
                                         **({"sha256": f["sha256"]} if f.get("sha256") else {})} for f in fajlok]})
    print("[manifold-progress] 100.0%", flush=True)
    return {"allapot": "kesz", "fajlok": len(fajlok), "bajt": osszes}


def feladat_main(argv: list[str]) -> int:
    """A feladatsor lépése: `python -m core.letoltes --feladat <modell>`. Kilépés: 0 kész, 3 megállítva, 2 hiba. A riport
    `{runs}/modell-letoltes/<modell>-riport.json` (`Riport:` sor a feladatsornak)."""
    if len(argv) != 1:
        print("használat: python -m core.letoltes --feladat <modell>", file=sys.stderr)
        return 2
    nev = argv[0]
    cfg = config.load()
    stop_fajl = os.environ.get("MANIFOLD_STOP_FAJL")
    riport = cfg.path("runs") / "modell-letoltes" / f"{nev if manifeszt.AZONOSITO.match(nev) else 'hibas'}-riport.json"
    os.environ["HF_HUB_OFFLINE"] = "0"                 # D3: ez az egyetlen, felhasználó indította hálózati lépés
    os.environ["TRANSFORMERS_OFFLINE"] = "0"
    os.environ["HF_HUB_DISABLE_XET"] = "1"             # minden kérés a host-kapus httpx-kliensen menjen át
    os.environ["HF_HOME"] = str(cfg.path("models"))
    try:
        ered = modell_letolt(cfg, nev, stop=lambda: bool(stop_fajl) and Path(stop_fajl).exists())
        kod = 0 if ered["allapot"] == "kesz" else 3
    except (LetoltesHiba, manifeszt.ManifesztHiba) as e:
        ered, kod = {"allapot": "hiba", "kod": e.kod, "param": e.param, "uzenet": str(e)}, 2
    except Exception as e:  # noqa: BLE001 — hálózati/jogosultsági hiba: a riport mondja ki
        ered, kod = {"allapot": "hiba", "kod": "modell.letoltes_hiba", "param": {"hiba": type(e).__name__},
                     "uzenet": f"{type(e).__name__}: {e}"}, 2
    riport.parent.mkdir(parents=True, exist_ok=True)
    tmp = riport.with_name(f".{riport.name}.manifold-tmp")
    tmp.write_text(json.dumps({"modell": nev, **ered}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, riport)
    print(f"Riport: {riport}", flush=True)
    if kod == 2:
        print(f"HIBA: {ered.get('uzenet')}", file=sys.stderr, flush=True)
    return kod


if __name__ == "__main__":
    sys.exit(main())
