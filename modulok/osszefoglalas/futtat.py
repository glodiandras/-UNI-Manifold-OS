"""Az összefoglaló éles lánca (C26b; `docs/C26-TERV.md` 7., 9. fejezet; CLAUDE.md 28., 45., 49., 56. döntés, D9): a jegyzet olvasása
a core-tól, a modell a workeren át, az írás a gépi-írás szolgáltatáson át. A lánc maga (kapuk, kiválasztás) a `lanc.py`-ban.

    futtat(cfg, szint, ut, gepi=gepi_kliens, worker=Worker(cfg), automatikus=False, proba=False, …) → összegzés

**Egy összefoglaló = egy tétel = egy gépi commit** (`Mos-Forras: mos-osszefoglalas`, kör `OSSZ-ÉÉÉÉHHNN-ÓÓPPMM-<hex>`; a kör azonosítója
az összefoglaló `Osszefoglalas` mezője):

- `jegyzet`: a kísérőjegyzet (`uj` az `osszefoglalo` sémaosztállyal, vagy a meglévő `csere` alap-hash-sel) és a forrás **egyetlen**
  `csere`-je (a `^m-…` blokkazonosító a forrásbekezdés végére — a kártyával közös `horgony.horgonyoz` úton, a meglévő azonosító
  újrahasznosul —, plusz a `## Gyakorlás` beágyazó sora). Az összefoglaló linkjei így már az éles `^m-…` horgonyra mutatnak.
- `mappa`: map-reduce a mappa jegyzet-szintű összefoglalóiból (a hiányzókat — legfeljebb `mappa_max_uj` — előbb elkészíti);
  a mappának nincs forrásjegyzete, ezért beágyazó sor nincs.
- `video`: az átirat (`<Téma>/Média/` réteg VTT-je, a core `GET /api/media/atirat` olvasó szabálya, csak olvasva) időablakai,
  `[[videó#t=<mp>|m:ss]]` linkekkel; a forrás nem szöveg, ezért beágyazó sor nincs.

A nyitott, mentetlen dokumentum 409-et ad; a gépi kliens a határidőig újrapróbál, utána a jegyzet kimarad (az automatika később újra
sorra veszi). **D9**: a modell a `szoveg` router-feladat kalibrált modellje (az `osszefoglalas` saját feladata nincs mérve: a mérés a
`modulok/osszefoglalas/meres.py`, a döntés a C26b NAPLO-ban); kalibrált modell nélkül élesben nincs összefoglaló; a kifejezett modell
(próba) és a `proba` az írást az APFS-klónra viszi, az automatika-tárhoz ekkor nem nyúl.

A modell-válaszok **gyorsítótára** (`{tmp}/osszefoglalas-gyorsitotar/`, `gyorsitotar_ora` óráig): ha az írás elakad (nyitott
dokumentum, leállítás), az újrapróba nem hívja újra a modellt ugyanarra a darabra. A kulcs a modell, a prompt és a `PROMPT_VERZIO`.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path

from core import rejtett
from core.index import elemzo
from modulok.kartya import horgony
from modulok.kartya.lanc import Worker, vault_md_utak

from . import formatum as FM
from . import lanc as L
from . import szakaszolas as SZ
from . import video as V
from .promptok import PROMPT_VERZIO

FELADAT = "szoveg"
FORRAS = "mos-osszefoglalas"
KOR_ELOTAG = "OSSZ"
FOGYASZTO = "osszefoglalo"
SZINTEK = ("jegyzet", "mappa", "video")

__all__ = ["FELADAT", "FORRAS", "FOGYASZTO", "KOR_ELOTAG", "SZINTEK", "Worker", "Hivo", "futtat", "futtat_jegyzet", "futtat_mappa",
           "futtat_video", "olvas_mappa", "kisero_keres"]


# ---------------------------------------------------------------------- a modell-hívás gyorsítótárral

class Hivo:
    """A `ModellHivas` (`(prompt, max_tokens) → szöveg`) a workeren át, gyorsítótárral. A `jel` az utolsó válasz gépi-írás `modell`
    jele (D9: router-feladat, modell, próba-jelzés) — a gyorsítótárból is, mert a próba-jelzés a válasszal együtt tárolt."""

    def __init__(self, cfg, worker, modell: str, kifejezett: bool, gepi, ora: float | None = None):
        self.cfg, self.worker, self.modell, self.kifejezett, self.gepi = cfg, worker, modell, kifejezett, gepi
        self._nyers = worker.hivo(modell, kifejezett)
        self.mappa = Path(cfg.path("tmp")) / "osszefoglalas-gyorsitotar"
        self.ttl = 3600.0 * (L.beallitas(cfg).gyorsitotar_ora if ora is None else ora)
        self.jel: dict | None = None
        self.talalat = self.hivas = 0

    def _kulcs(self, prompt: str, max_tokens: int) -> str:
        nyers = f"{PROMPT_VERZIO}\0{self.modell}\0{int(self.kifejezett)}\0{max_tokens}\0{prompt}"
        return hashlib.sha1(nyers.encode("utf-8")).hexdigest()

    def __call__(self, prompt: str, max_tokens: int) -> str:
        f = self.mappa / f"{self._kulcs(prompt, max_tokens)}.json"
        if self.ttl > 0:
            try:
                adat = json.loads(f.read_text(encoding="utf-8"))
                if time.time() - float(adat["ido"]) <= self.ttl and isinstance(adat["szoveg"], str) and isinstance(adat["jel"], dict):
                    self.jel, self.talalat = adat["jel"], self.talalat + 1
                    return adat["szoveg"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        szoveg = self._nyers(prompt, max_tokens)
        self.hivas += 1
        self.jel = self.gepi.modell_jel(self.worker.utolso)
        if self.kifejezett:
            self.jel["proba"] = True
        if self.ttl > 0:
            try:
                self.mappa.mkdir(parents=True, exist_ok=True)
                tmp = f.with_name(f".{f.name}.{os.getpid()}.tmp")
                tmp.write_text(json.dumps({"ido": time.time(), "szoveg": szoveg, "jel": self.jel}, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, f)
                self._lejart_torol()
            except OSError:
                pass                                # a gyorsítótár hibája nem akadályozza a munkát
        return szoveg

    def _lejart_torol(self) -> None:
        """A saját, lejárt gyorsítótár-fájlok törlése (csak a `{tmp}` alatti sajátok)."""
        most = time.time()
        for p in self.mappa.glob("*.json"):
            try:
                if most - p.stat().st_mtime > self.ttl:
                    p.unlink()
            except OSError:
                pass


def modell_valasztas(worker, modell: str | None) -> tuple[str, bool]:
    """(modell, kifejezett): a router kalibrált `szoveg` modellje (D9), vagy a kifejezett (próba) modell. Hiba: `L.Megall`."""
    if modell is not None:
        return modell, True
    try:
        dont = worker.valaszt()
    except Exception as exc:  # noqa: BLE001 — a worker hibája üzenetként
        if getattr(exc, "kod", None) == 409:
            raise L.Megall(f"A `{FELADAT}` feladatra nincs kalibrált modell: élesen nem készül összefoglaló. Próbához adj meg "
                           f"modellt (a kimenet a vault klónjára kerül). ({exc})") from None
        raise
    if not dont.get("modell"):
        raise L.Megall(f"Az összefoglaló modellje most nem futhat: {dont.get('indok') or 'a távol-keretre vár'}.")
    return dont["modell"], False


# ---------------------------------------------------------------------- a meglévő kísérőjegyzetek

def olvas_mappa(cfg) -> dict[str, FM.Elemzes]:
    """Az összefoglaló-mappa `.md` fájljai elemezve: {vault-relatív NFC út: elemzés}. Csak olvas; a rejtett fájl kimarad."""
    vault = Path(cfg.path("vault"))
    gyoker = vault / L.beallitas(cfg).mappa
    ki: dict[str, FM.Elemzes] = {}
    if not gyoker.is_dir():
        return ki
    for dp, dn, fn in os.walk(gyoker):
        dn[:] = sorted(d for d in rejtett.metsz(dn) if not d.startswith("."))     # I6: minden pontos mappa kimarad
        for f in sorted(fn):
            if f.startswith(".") or not f.endswith(".md"):
                continue
            p = Path(dp) / f
            try:
                ki[FM.nfc(os.path.relpath(p, vault))] = FM.elemez(p.read_bytes().decode("utf-8", errors="replace"))
            except OSError:
                continue
    return ki


def kisero_keres(elemzesek: dict[str, FM.Elemzes], cel: str, szint: str) -> str | None:
    """A forrás (jegyzet: út `.md` nélkül; videó: út kiterjesztéssel) meglévő, adott szintű összefoglalója."""
    kulcs = FM.nfc(cel).casefold()
    for ut in sorted(elemzesek):
        o = elemzesek[ut].osszefoglalo
        if o and o.szint == szint and any(FM.nfc(f).casefold() == kulcs for f in o.forrasok):
            return ut
    return None


def mappa_kisero_keres(elemzesek: dict[str, FM.Elemzes], mappa_ut: str, cim: str) -> str | None:
    """A mappa meglévő mappa-szintű összefoglalója: minden forrása a mappában áll, a címe a mappa neve."""
    elo = FM.nfc(mappa_ut).rstrip("/").casefold() + "/"
    for ut in sorted(elemzesek):
        o = elemzesek[ut].osszefoglalo
        if o and o.szint == "mappa" and o.forrasok and FM.nfc(o.cim) == FM.nfc(cim) and \
                all(FM.nfc(f).casefold().startswith(elo) for f in o.forrasok):
            return ut
    return None


# ---------------------------------------------------------------------- közös: az írás

def _kisero_hely(cfg, b: L.Beallitas, forras_ut: str, vault_utak, meglevo: str | None) -> tuple[str, str]:
    """(a kísérőjegyzet útja, neve `.md` nélkül): a meglévő, vagy az új, ütközésmentes."""
    if meglevo:
        return meglevo, os.path.splitext(os.path.basename(meglevo))[0]
    nev = FM.kisero_nev(forras_ut, vault_utak, utotag=b.utotag)
    return f"{b.mappa.strip('/')}/{nev}.md", nev


def _kisero_muvelet(gepi, kisero_ut: str, tartalom: str, meglevo: str | None) -> dict:
    if meglevo:
        return gepi.csere(kisero_ut, tartalom, gepi.olvas(kisero_ut)["hash"])
    return gepi.uj(kisero_ut, tartalom, osztaly="osszefoglalo")


def _irj(gepi, kor: str, tetel: str, muveletek: list[dict], jel: dict, proba: bool, uzenet: str) -> dict:
    return gepi.ir(kor, tetel=tetel, forras=FORRAS, muveletek=muveletek, modell=jel, proba=proba, uzenet=uzenet[:200])


def _statisztika(e: L.Eredmeny, hivo: Hivo) -> dict:
    return {**e.statisztika, "gyorsitotar_talalat": hivo.talalat, "modell_hivas": hivo.hivas}


# ---------------------------------------------------------------------- jegyzet

def futtat_jegyzet(cfg, ut: str, *, gepi, worker, automatikus: bool = False, proba: bool = False, modell: str | None = None,
                   allj=lambda: False, naplo=lambda s: None) -> dict:
    """Összefoglaló egy jegyzetből → `{allapot, …}`: `kesz` | `nincs_osszefoglalo` (csak automatikus módban: a jegyzetből nem lett
    elég hiteles állítás — a változat feldolgozottnak számít). Hiba: `L.Megall` (érthető üzenet) vagy a gépi kliens `GepiHiba`-ja."""
    from core import automatika, gyakorlas
    from core.gepi_iras import szakasz_beszur

    b = L.beallitas(cfg)
    d = gepi.olvas(ut)
    ut, md, alap_hash = FM.nfc(d["ut"]), d["tartalom"], d["hash"]
    cim, cel = FM.cim_of(ut), ut.removesuffix(".md")
    t = elemzo.elemez(md)
    bem = SZ.jegyzet_bemenet(md, cel, cim, t.fejezetek, t.blokkok, b.darab_max_karakter, b.szakasz_min_karakter,
                          b.kihagyott_szakaszok)
    if not bem.darabok:
        raise L.Megall("A jegyzetnek nincs olyan szöveges része, amelyből összefoglalni lehet.")
    m, kifejezett = modell_valasztas(worker, modell)
    hivo = Hivo(cfg, worker, m, kifejezett, gepi)
    kor = gepi.uj_kor(KOR_ELOTAG)
    try:
        e = L.osszefoglal(bem, hivo, m, cim, forrasok=[cel], szint="jegyzet", azon=kor, b=b, p=L.profil(cfg), log=naplo, allj=allj)
    except L.Megall as exc:
        if automatikus and not proba and not kifejezett and not str(exc).startswith("leállítva"):
            automatika.Tar(cfg).kesz(FOGYASZTO, ut, md, hash_=alap_hash)    # ugyanezt a változatot nem próbáljuk újra és újra
            return {"allapot": "nincs_osszefoglalo", "ut": ut, "ok": str(exc)}
        raise
    proba = proba or kifejezett or bool(hivo.jel and hivo.jel.get("proba"))

    # a forrás: `^m-…` horgonyok + a `## Gyakorlás` beágyazó sora, egy szövegben (egy út egy tételben egyszer szerepelhet)
    o = e.osszefoglalo
    uj_md, blokkok = horgony.horgonyoz(md, [a.idezet for a in o.allitasok])
    for i, (a, blokk) in enumerate(zip(o.allitasok, blokkok)):
        if blokk and not (a.horgony.alcel or "").startswith("^"):
            o.allitasok[i] = dataclasses.replace(a, horgony=FM.Horgony(a.horgony.cel, "^" + blokk, a.horgony.felirat))
    vault_utak = vault_md_utak(cfg)
    meglevo = kisero_keres(olvas_mappa(cfg), cel, "jegyzet")
    kisero_ut, nev = _kisero_hely(cfg, b, ut, vault_utak, meglevo)
    try:
        uj_md = szakasz_beszur(uj_md, gyakorlas.FEJEZET, gyakorlas.beagyazo_sor(nev), "vege", True)
    except Exception as exc:  # noqa: BLE001 — pl. két `## Gyakorlás` szakasz: a beágyazás elmarad, az összefoglaló elkészül
        naplo(f"[összefoglaló] a beágyazó sor nem került be ({exc})")
    muveletek = [_kisero_muvelet(gepi, kisero_ut, FM.ir(o), meglevo)]
    if uj_md != md:
        muveletek.append(gepi.csere(ut, uj_md, alap_hash))
    r = _irj(gepi, kor, ut, muveletek, hivo.jel, proba, f"összefoglaló: {cim} ({len(o.allitasok)} állítás)")
    ki = {"allapot": "kesz", "ut": ut, "szint": "jegyzet", "allitasok": len(o.allitasok), "kisero": kisero_ut, "modell": hivo.jel["modell"],
          "proba": r.get("proba"), "sha": r.get("sha"), "kor": r.get("kor"), "statisztika": _statisztika(e, hivo)}
    if not r.get("proba"):
        automatika.Tar(cfg).kesz(FOGYASZTO, ut, uj_md, hash_=(r.get("hash") or {}).get(ut, alap_hash), kimenet=kisero_ut)
    return ki


# ---------------------------------------------------------------------- mappa

def _mappa_jegyzetei(cfg, mappa_ut: str, b: L.Beallitas) -> list[str]:
    """A mappa közvetlen tartalmi `.md` jegyzetei (vault-relatív, NFC, ábécében)."""
    from core import automatika
    vault = Path(cfg.path("vault"))
    p = vault / mappa_ut
    if not p.is_dir() or any(r.startswith(".") for r in mappa_ut.split("/")):
        raise L.Megall(f"Nincs ilyen mappa a vaultban: {mappa_ut}")
    ki = []
    for f in sorted(os.listdir(p)):
        rp = FM.nfc(f"{mappa_ut}/{f}")
        if f.lower().endswith(".md") and not f.startswith(".") and (p / f).is_file() and automatika.tartalmi_ut(rp):
            ki.append(rp)
    return ki


def mappa_terv(cfg, mappa_ut: str, kiegeszit: bool = True) -> dict:
    """A mappa-szintű kérés terve (csak olvas): `{jegyzetek, van, hianyzik, keszul, tetelek}`. Egy kérés legfeljebb `mappa_max_uj`
    hiányzó jegyzet-összefoglalót készít el (a koordinátor kikötése: egy kérésben legfeljebb 5 tétel = `mappa_max_uj` + a mappa-szint, ezért
    az alap `mappa_max_uj` = 4), a `tetelek` a gépi írások (commitok) száma, a mappa-szinttel együtt."""
    b = L.beallitas(cfg)
    mappa_ut = FM.nfc(mappa_ut).strip("/")
    jegyzetek = _mappa_jegyzetei(cfg, mappa_ut, b)[:b.mappa_max_jegyzet]
    el = olvas_mappa(cfg)
    van = [u for u in jegyzetek if kisero_keres(el, u.removesuffix(".md"), "jegyzet")]
    hianyzik = [u for u in jegyzetek if u not in van]
    keszul = hianyzik[:b.mappa_max_uj] if kiegeszit else []
    return {"jegyzetek": jegyzetek, "van": van, "hianyzik": hianyzik, "keszul": keszul, "tetelek": len(keszul) + 1}


def futtat_mappa(cfg, mappa_ut: str, *, gepi, worker, kiegeszit: bool = True, proba: bool = False, modell: str | None = None,
                 allj=lambda: False, naplo=lambda s: None) -> dict:
    """Mappa-szintű összefoglaló a jegyzet-szintűekből (`docs/C26-TERV.md` 3.2). `kiegeszit`: a hiányzó jegyzet-összefoglalókat
    (egy kérésben legfeljebb `mappa_max_uj`, így összesen legfeljebb 5 gépi írás) előbb elkészíti, mindegyiket önálló tételben; a
    haladás (`[manifold-progress]`) a tételek számához igazodik."""
    b = L.beallitas(cfg)
    mappa_ut = FM.nfc(mappa_ut).strip("/")
    terv = mappa_terv(cfg, mappa_ut, kiegeszit)
    jegyzetek = terv["jegyzetek"]
    if not jegyzetek:
        raise L.Megall("A mappában nincs tartalmi jegyzet.")
    cim = os.path.basename(mappa_ut)
    naplo(f"[összefoglaló/mappa] {cim}: {len(terv['van'])} jegyzethez van összefoglaló, {len(terv['keszul'])} készül el most "
          f"({len(terv['hianyzik']) - len(terv['keszul'])} marad ki), utána a mappa-szint — összesen {terv['tetelek']} tétel")
    kesz_tetel = 0

    def haladas() -> None:
        naplo(f"[manifold-progress] {round(100 * kesz_tetel / terv['tetelek'])}%")

    uj, kihagyott = [], [{"ut": u, "ok": "nincs_osszefoglalo"} for u in terv["hianyzik"] if u not in terv["keszul"]]
    for ut in terv["keszul"]:
        if allj():
            raise L.Megall("leállítva (a következő jegyzet előtt)")
        try:
            r = futtat_jegyzet(cfg, ut, gepi=gepi, worker=worker, proba=proba, modell=modell, allj=allj, naplo=naplo)
            uj.append(r["ut"])
        except (L.Megall, getattr(gepi, "GepiHiba", L.Megall)) as exc:
            if str(exc).startswith("leállítva"):
                raise
            kihagyott.append({"ut": ut, "ok": str(exc)[:160]})
        kesz_tetel += 1
        haladas()
    el = olvas_mappa(cfg)       # próbában az új összefoglalók az APFS-klónon vannak: a mappa-szint a vault meglévőiből dolgozik
    anyag, bemenetek = [], []
    for ut in jegyzetek:
        k = kisero_keres(el, ut.removesuffix(".md"), "jegyzet")
        o = el[k].osszefoglalo if k else None
        if not o or not o.allitasok:
            continue
        md = gepi.olvas(ut)["tartalom"]
        t = elemzo.elemez(md)
        bemenetek.append(SZ.jegyzet_bemenet(md, ut.removesuffix(".md"), FM.cim_of(ut), t.fejezetek, t.blokkok,
                                            b.darab_max_karakter, b.szakasz_min_karakter, b.kihagyott_szakaszok))
        anyag.append(o)
    if len(anyag) < 2:
        raise L.Megall(f"A mappa-összefoglalóhoz legalább két jegyzet-összefoglaló kell (most {len(anyag)}"
                       + (f"; nem készült el: {len(kihagyott)}" if kihagyott else "") + ").")
    m, kifejezett = modell_valasztas(worker, modell)
    hivo = Hivo(cfg, worker, m, kifejezett, gepi)
    kor = gepi.uj_kor(KOR_ELOTAG)
    e = L.mappa_osszefoglal(cim, list(zip(anyag, bemenetek)), hivo, m, azon=kor, b=b, p=L.profil(cfg), log=naplo)
    proba = proba or kifejezett or bool(hivo.jel and hivo.jel.get("proba"))
    meglevo = mappa_kisero_keres(el, mappa_ut, cim)
    kisero_ut, _ = _kisero_hely(cfg, b, mappa_ut + ".md", vault_md_utak(cfg), meglevo)
    r = _irj(gepi, kor, mappa_ut, [_kisero_muvelet(gepi, kisero_ut, FM.ir(e.osszefoglalo), meglevo)], hivo.jel, proba,
             f"összefoglaló (mappa): {cim} ({len(e.osszefoglalo.allitasok)} állítás)")
    return {"allapot": "kesz", "ut": mappa_ut, "szint": "mappa", "allitasok": len(e.osszefoglalo.allitasok), "kisero": kisero_ut,
            "modell": hivo.jel["modell"], "proba": r.get("proba"), "sha": r.get("sha"), "kor": r.get("kor"), "uj_jegyzet_osszefoglalo": uj,
            "kihagyott": kihagyott, "statisztika": _statisztika(e, hivo)}


# ---------------------------------------------------------------------- videó és hang

def futtat_video(cfg, ut: str, *, gepi, worker, proba: bool = False, modell: str | None = None,
                 allj=lambda: False, naplo=lambda s: None) -> dict:
    """Összefoglaló egy videó vagy hang átiratából (a core olvasó szabálya szerinti VTT, csak olvasva)."""
    b = L.beallitas(cfg)
    ut = FM.nfc(ut)
    at = gepi.atirat(ut)
    cuek = [(c["k"], c["szoveg"]) for c in at.get("cuek") or []]
    if not cuek:
        raise L.Megall("A médiához nincs olvasható átirat (VTT) a melléklet-mappájában" + (f": {at['figyelmeztetes']}" if at.get("figyelmeztetes") else "") + ".")
    cim = FM.nfc(os.path.splitext(os.path.basename(ut))[0])
    bem = V.video_bemenet(cuek, ut, cim, b.ablak_mp, b.darab_max_karakter)
    if not bem.darabok:
        raise L.Megall("Az átiratból nem képezhető darab.")
    m, kifejezett = modell_valasztas(worker, modell)
    hivo = Hivo(cfg, worker, m, kifejezett, gepi)
    kor = gepi.uj_kor(KOR_ELOTAG)
    e = L.osszefoglal(bem, hivo, m, cim, forrasok=[ut], szint="video", azon=kor, b=b, p=L.profil(cfg), log=naplo, allj=allj)
    proba = proba or kifejezett or bool(hivo.jel and hivo.jel.get("proba"))
    meglevo = kisero_keres(olvas_mappa(cfg), ut, "video")
    kisero_ut, _ = _kisero_hely(cfg, b, os.path.splitext(ut)[0] + ".md", vault_md_utak(cfg), meglevo)
    r = _irj(gepi, kor, ut, [_kisero_muvelet(gepi, kisero_ut, FM.ir(e.osszefoglalo), meglevo)], hivo.jel, proba,
             f"összefoglaló (videó): {cim} ({len(e.osszefoglalo.allitasok)} állítás)")
    return {"allapot": "kesz", "ut": ut, "szint": "video", "allitasok": len(e.osszefoglalo.allitasok), "kisero": kisero_ut,
            "modell": hivo.jel["modell"], "proba": r.get("proba"), "sha": r.get("sha"), "kor": r.get("kor"),
            "gepi_atirat": at.get("gepi"), "statisztika": _statisztika(e, hivo)}


def futtat(cfg, szint: str, ut: str, **kw) -> dict:
    if szint == "jegyzet":
        kw.pop("kiegeszit", None)
        return futtat_jegyzet(cfg, ut, **kw)
    kw.pop("automatikus", None)
    if szint == "mappa":
        return futtat_mappa(cfg, ut, **kw)
    if szint == "video":
        kw.pop("kiegeszit", None)
        return futtat_video(cfg, ut, **kw)
    raise L.Megall(f"ismeretlen szint: {szint!r} ({', '.join(SZINTEK)})")
