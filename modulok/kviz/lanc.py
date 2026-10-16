"""A kvízlánc I/O-ja (C22b; `docs/C22-TERV.md` 10. fejezet; CLAUDE.md 28., 48., 56. döntés, D1, D9): a jegyzet olvasása a
core-tól, a modell a workeren át (gyorsítótárral), az írás a gépi-írás szolgáltatáson át. A kapuk a `generalas.py`-ban.

    futtat(cfg, ut, gepi=gepi_kliens, worker=Worker(cfg), proba=False, modell=None) → összegzés

**Egy kvíz = egy tétel = egy gépi commit** (`Mos-Forras: mos-kviz`, kör `KVIZ-…`, amely a kvízjegyzet `Kviz:` mezője is): a
kvízjegyzet (`uj` a `kviz` sémaosztállyal, `formatum.ir`; foglalt névnél sorszámmal) és a forrás `## Gyakorlás` szakaszába a
beágyazó sor (`gyakorlas.beszuras_muvelet`). A nyitott, mentetlen dokumentum 409-et ad; a gépi kliens a határidőig újrapróbál.

**D9** (63. döntés): a modell a `kviz` router-feladat kalibrált modellje — a worker routere választ. Ha a kalibrált modell csak a
távol-keretbe fér (2026-10-08: a `qwen35_9b`), a kérés `auto` módban sorba áll, és tétlenségben fut (a worker ütemezője). A
kifejezett modell (próba) és a `proba` az írást az APFS-klónra viszi (`proba: true`). A token-keret a mérés szabálya
(`core.modell.eval.keres_beallitas`: a Qwen3.5-család `max_tokens_szorzo`-ja): az éles kérés ugyanaz, mint a mért.

**Gyorsítótár**: a modell nyers válaszai a `{tmp}/kviz-gyorsitotar/<forrás-kulcs>/` alatt (kérésenként egy JSON, a kulcs a modell,
a kérés-beállítás, a prompt és a `PROMPT_VERZIO`): a leállított vagy elbukott futás onnan folytatódik, a sikeres írás után a
forrás mappája törlődik (a saját `var/tmp` fájl, §4), a 7 napnál régebbi mappák induláskor.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime

from core import kiserok

from . import formatum as FM
from . import generalas as G
from .promptok import PROMPT_VERZIO

FELADAT = "kviz"
FORRAS = "mos-kviz"
KOR_ELOTAG = "KVIZ"
OSZTALY = "kviz"
GYORSITOTAR = "kviz-gyorsitotar"
GYORSITOTAR_NAP = 7


class Megall(Exception):
    """A kvíz nem készülhet el — az üzenet a felhasználónak szól (a feladatsor hibaként mutatja)."""


def _kulcs(*reszek) -> str:
    return hashlib.sha256("\x1f".join(str(r) for r in reszek).encode("utf-8")).hexdigest()[:24]


class Gyorsitotar:
    """A nyers modell-válaszok egy forrásjegyzethez (a teljes worker-válasz, hogy a modell-jel is visszaálljon)."""

    def __init__(self, cfg, ut: str):
        self.gyoker = cfg.path("tmp") / GYORSITOTAR
        self.mappa = self.gyoker / _kulcs(FM.nfc(ut))
        self.talalat = 0

    def takarit(self) -> None:
        if not self.gyoker.is_dir():
            return
        hatar = time.time() - GYORSITOTAR_NAP * 86400
        for d in self.gyoker.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < hatar:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue

    def kap(self, kulcs: str) -> dict | None:
        p = self.mappa / f"{kulcs}.json"
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self.talalat += 1
        return r

    def tesz(self, kulcs: str, valasz: dict) -> None:
        self.mappa.mkdir(parents=True, exist_ok=True)
        p = self.mappa / f"{kulcs}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(valasz, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def torol(self) -> None:
        shutil.rmtree(self.mappa, ignore_errors=True)


class Worker:
    """A worker a `core.modell.kliens`-en át; a kérés-beállítás (gondolkodás, token-keret) a regiszterből, a mérés szabályával."""

    def __init__(self, cfg):
        from core.modell import beallitas as B
        from core.modell import kliens
        self.kliens, self.b = kliens, B.betolt(cfg)
        self.u = kliens.url(cfg)
        self.utolso: dict | None = None

    def valaszt(self, keret: str | None = None) -> dict:
        body = {"feladat": FELADAT}
        if keret:
            body["keret"] = keret
        return self.kliens.keres(self.u, "/router/valaszt", body)

    def hivo(self, modell: str, kifejezett: bool, mod: str | None = None, tar: Gyorsitotar | None = None):
        from core.modell import eval as E

        def hiv(prompt: str, max_tokens: int) -> str:
            k = E.keres_beallitas(self.b, self.b.modell(modell), FELADAT,
                                  {"tipus": "chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens})
            kulcs = _kulcs(modell, kifejezett, PROMPT_VERZIO, json.dumps(k, ensure_ascii=False, sort_keys=True))
            r = tar.kap(kulcs) if tar else None
            if r is None:
                uzenetek = k.pop("messages")
                k.pop("tipus", None)
                r = self.kliens.chat(self.u, uzenetek, feladat=FELADAT, modell=modell if kifejezett else None, mod=mod, **k)
                if tar:
                    tar.tesz(kulcs, r)
            self.utolso = r
            return r["choices"][0]["message"]["content"]
        return hiv


def modell_dontes(worker, modell: str | None) -> tuple[str, bool, str | None, str]:
    """→ (modellnév, kifejezett, mód, megjegyzés). A router a munka-keretben választ; ha a kalibrált modell csak a távol-keretbe
    fér, a távol-keret döntésének modellje `auto` módban (vár a tétlenségre). Nincs kalibrált modell: `Megall` (D9)."""
    if modell is not None:
        return modell, True, None, "kifejezett modell (próba)"
    try:
        dont = worker.valaszt()
        if dont.get("modell"):
            return dont["modell"], False, None, dont.get("indok") or ""
        if dont.get("var_tavolra"):
            tavol = worker.valaszt("tavol")
            if tavol.get("modell"):
                return tavol["modell"], False, "auto", (f"a(z) {tavol['modell']} csak a távol-keretbe fér: a kvíz sorba áll, és "
                                                        "tétlenségben készül el")
    except Exception as exc:  # noqa: BLE001 — a worker hibája üzenetként
        if getattr(exc, "kod", None) == 409:
            raise Megall(f"A `{FELADAT}` feladatra nincs kalibrált modell: élesen nem készül kvíz. Próbához adj meg "
                         f"modellt (a kimenet a vault klónjára kerül). ({exc})") from None
        raise
    raise Megall(f"A kvíz modellje most nem futhat: {dont.get('indok') or 'nincs választható modell'}.")


def _celja(link: str) -> str:
    return FM.nfc(link.split("#", 1)[0].split("|", 1)[0].strip()).casefold()


def korabbi_kvizek(cfg, ut: str) -> tuple[list[str], set[str]]:
    """A kvízmappa (csak olvasva): a forrás korábbi kvízeinek kérdései (az új nem ismétli őket) és a foglalt fájlnevek."""
    vault = cfg.path("vault")
    mappa = vault / mappa_nev(cfg)
    jel = {FM.nfc(ut[:-3]).casefold(), FM.nfc(os.path.splitext(os.path.basename(ut))[0]).casefold()}
    kerdesek: list[str] = []
    nevek: set[str] = set()
    if not mappa.is_dir():
        return kerdesek, nevek
    for f in sorted(mappa.iterdir()):
        if not f.name.lower().endswith(".md"):
            continue
        nevek.add(FM.nfc(f.name[:-3]).casefold())
        try:
            e = FM.elemez(f.read_text(encoding="utf-8"), azon_tartalek="KVIZ-00000000-000000-kezi")
        except (OSError, UnicodeDecodeError):
            continue
        if e.kviz and _celja(e.kviz.forras) in jel:
            kerdesek += [q.kerdes for q in e.kviz.kerdesek]
    return kerdesek, nevek


def mappa_nev(cfg) -> str:
    return kiserok.kisero_mappa(cfg, "kviz")


def futtat(cfg, ut: str, *, gepi, worker, proba: bool = False, modell: str | None = None, n: int | None = None,
           kor: str | None = None, allj=lambda: False, naplo=lambda s: None, halad=lambda arany: None) -> dict:
    """Kvíz egy jegyzetből: → `{allapot: "kesz", ut, kviz, kerdesek, modell, proba, sha, kor, statisztika, elvetett}`. Hiba:
    `Megall` (érthető üzenet), a lánc `G.Megall`-ja (kevés kérdés, leállítás) `Megall`-ként, vagy a gépi kliens `GepiHiba`-ja."""
    from core import gyakorlas

    b = G.beallitas(cfg)
    d = gepi.olvas(ut)
    ut, md = d["ut"], d["tartalom"]
    nev_m, kifejezett, mod, megj = modell_dontes(worker, modell)
    if kifejezett:
        proba = True
    if megj:
        naplo(f"[kvíz] modell: {nev_m} — {megj}")
    tar = Gyorsitotar(cfg, ut)
    tar.takarit()
    hivo = worker.hivo(nev_m, kifejezett, mod=mod, tar=tar)
    korabbi, foglalt = korabbi_kvizek(cfg, ut)
    kor = kor or gepi.uj_kor(KOR_ELOTAG)
    azon = kor.removesuffix("-proba")
    mikor = datetime.now()
    try:
        from modulok.kapuk import huseg as KH
        e = G.general(md, ut, hivo, hivo, n=n, modell=nev_m, azon=azon, korabbi=korabbi, b=b, profil=KH.profil(cfg, "kviz"),
                      mikor=mikor, log=naplo, halad=halad, allj=allj)
    except G.Megall as exc:
        raise Megall(str(exc)) from None
    if tar.talalat:
        naplo(f"[kvíz] {tar.talalat} modellválasz a gyorsítótárból (a korábbi, megszakadt futásé)")
    jel = gepi.modell_jel(worker.utolso)
    proba = proba or jel["proba"]
    e.kviz.modell = jel["modell"]

    nev = FM.fajlnev(e.kviz)
    i = 1
    while nev.casefold() in foglalt:
        i += 1
        nev = FM.fajlnev(e.kviz, i)
    kviz_ut = f"{mappa_nev(cfg)}/{nev}.md"
    muveletek = [gepi.uj(kviz_ut, FM.ir(e.kviz), osztaly=OSZTALY), gyakorlas.beszuras_muvelet(ut, nev)]
    r = gepi.ir(kor, tetel=ut, forras=FORRAS, muveletek=muveletek, modell=jel, proba=proba,
                uzenet=f"kvíz: {e.kviz.cim} ({len(e.kviz.kerdesek)} kérdés)"[:200])
    tar.torol()
    return {"allapot": "kesz", "ut": ut, "kviz": kviz_ut, "kerdesek": len(e.kviz.kerdesek), "modell": jel["modell"],
            "proba": r.get("proba"), "sha": r.get("sha"), "kor": r.get("kor"), "statisztika": e.statisztika,
            "elvetett": e.elvetett[:30]}
