"""A füzetlánc köre (C21; a legacy `fuzet.lanc` + `fuzet_eros` + `src/mos/fuzetkor.py` portja).

Egy kör a figyelt mappák (vagy a megadott fájlok/mappák) új fotóit dolgozza fel, név szerinti sorrendben, fázisokban (a legacy
sorrendje: a modellcsere ne fotónként történjen; egy megállított kör a gyorsítótárból folytatódik, a vault addig nem változik):

1. **olvasás** (`fuzet_fejezet`): papírkivágás, álló papírnál forgatás-próba (`kep.FORGATASOK`), a fejezetlista;
2. **átirat** (`ocr_kezi`): a képletek (callout) és az index szövege;
3. **választás** (`fuzet_valaszto`): a jelöltlistából egy jegyzet — „Beszúrás az aktív jegyzetbe” módban (`cel`) nem fut;
4. **írás**: fotónként EGY gépi tétel (`FUZET-…` kör, `Mos-Forras: mos-fuzet`): `mozgat` (a fotó a `[fuzet] cel_mappa` alá) +
   `csere` (a cél jegyzet `## Füzet` blokkja); a visszavonás a fotót a forrásmappájába viszi vissza (L19), az állapot „visszavonva” (L20).

Az **ellenőrző kör** (`ellenoriz`, a legacy `--ellenoriz`): a már bekötött fotók újradöntése; eltérésnél átkötés (a fotó a helyén
marad, a blokk — beágyazás és callout — költözik), fotónként egy `Mos-Forras: mos-fuzet-ellenor` tétel.

Leállítás a tétel végén (a stop-fájl, L54); a haladás `[manifold-progress] N%`, a riport `Riport: <út>` sora.
"""
from __future__ import annotations

import json
import os
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from core import fuzet as F
from core import gepi_kliens

from . import formatum, kep, modszer
from .katalogus import Katalogus
from .modell import Gyorsitotar, Modellek, NincsModell

FORRAS = "mos-fuzet"
FORRAS_ELLENOR = "mos-fuzet-ellenor"
KOR_ELOTAG = "FUZET"
KOR_ELOTAG_ELLENOR = "FUZETELL"
LEZART = ("bekotve", "visszavonva", "kihagyva")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


class Stop:
    def __init__(self, ut: str | None):
        self.ut = ut

    def __call__(self) -> bool:
        return bool(self.ut) and os.path.exists(self.ut)


@dataclass
class Foto:
    forras: Path
    sha: str
    nev: str
    olvasat: dict = field(default_factory=dict)          # tantárgy, címek, tartalom, fejezetek + kivágás, forgatás
    atirat: str = ""
    kepletek: list = field(default_factory=list)
    jegyzet: str | None = None
    jelek: dict = field(default_factory=dict)             # lépés → a modell jele (D9)
    allapot: str = "uj"
    uzenet: str | None = None
    jeloltek: list = field(default_factory=list)
    tartalek: bool = False


def kepek(mappak: list[Path]) -> list[Path]:
    """A mappák képei (a közvetlen tartalom és egy szint almappa — a felületről feltöltött fotók `<azonosító>/` alá kerülnek),
    a rejtett és az ideiglenes fájlok nélkül, név szerint rendezve."""
    ki: list[Path] = []
    for m in mappak:
        if not m.is_dir():
            continue
        for p in sorted(m.iterdir()):
            if p.name.startswith("."):
                continue
            if p.is_dir() and not p.is_symlink():
                ki += [q for q in sorted(p.iterdir()) if q.is_file() and not q.is_symlink() and kep.kep_e(q.name)]
            elif p.is_file() and not p.is_symlink() and kep.kep_e(p.name):
                ki.append(p)
    return sorted(ki, key=lambda p: (nfc(p.name), str(p)))


class Lanc:
    def __init__(self, cfg, *, proba: bool = False, kifejezett: dict | None = None, cel: str | None = None,
                 stop=None, log=print, modellek: Modellek | None = None, katalogus: Katalogus | None = None,
                 max_foto: int | None = None):
        self.cfg, self.proba, self.cel, self.log = cfg, proba, cel, log
        self.stop = stop or (lambda: False)
        self.modellek = modellek or Modellek(cfg, kifejezett)
        self._kat = katalogus
        self.tar = Gyorsitotar(cfg)
        fz = cfg.section("fuzet")
        self.cel_mappa = str(fz.get("cel_mappa") or "ATTCHMNTS - photos")
        self.szakasz = "## " + str(fz.get("szakasz") or "Füzet")
        self.kepletek_max = int(fz.get("kepletek_max", 20))
        self.max_foto = int(max_foto or fz.get("max_foto", 40))
        self.tmp = cfg.path("tmp") / "fuzet"
        self.kor: str | None = None
        self._nevek: set[str] | None = None
        self._klon: Path | None = None

    # -------------------------------------------------- segédek

    def kat(self) -> Katalogus:
        if self._kat is None:
            self._kat = Katalogus.vaultbol(self.cfg.path("vault"))
        return self._kat

    def _haladas(self, szazalek: float) -> None:
        self.log(f"[manifold-progress] {max(0.0, min(100.0, szazalek)):.1f}%")

    def _kerdez(self, foto: Foto, fajta: str, feladat: str, prompt: str, kepek_: list[Path] | None, max_tokens: int,
                beallitas_feladat: str | None = None, extra: tuple = ()) -> tuple[str, dict]:
        """Egy modellhívás a gyorsítótáron át (a kulcs: a fotó, a fajta, a modell, a próba-jel és a prompt ujjlenyomata)."""
        nev = self.modellek.modell_nev(feladat)
        ly = Gyorsitotar.lenyomat(fajta, nev, feladat in self.modellek.kifejezett, prompt, max_tokens, kep.VERZIO, *extra)
        r = self.tar.olvas(fajta, foto.sha, ly)
        if r is None:
            t0 = time.time()
            szoveg, jel = self.modellek.kerdez(feladat, prompt, [str(k) for k in kepek_ or []], max_tokens, beallitas_feladat)
            r = self.tar.ir(fajta, foto.sha, ly, {"kep": foto.nev, "valasz": szoveg, "jel": jel, "mp": round(time.time() - t0, 1),
                                                  "ido": F.most()})
        return r["valasz"], r["jel"]

    def _oldalak(self, foto: Foto, forgatas: int | None = None) -> tuple[dict, list[Path]]:
        return kep.oldalkepek(foto.forras, self.tmp / foto.sha[:16], forgatas=forgatas)

    # -------------------------------------------------- 1. olvasás

    def olvas(self, foto: Foto) -> None:
        meta, utak = self._oldalak(foto)
        forgatas, pontok = None, {}
        if not meta["fekvo"]:
            olv = {}
            # a próbaolvasás a fejezet-olvasó modellje; aktív jegyzet módban (nincs fejezet-olvasás) az átiraté (a kalibrált `ocr_kezi`)
            olvaso = "ocr_kezi" if self.cel else "fuzet_fejezet"
            for fok in kep.FORGATASOK:
                _, fu = self._oldalak(foto, fok)
                olv[fok], _ = self._kerdez(foto, f"forgatas{fok}", olvaso, modszer.FORGATAS_PROMPT, [fu[0]],
                                           modszer.MAX_TOKEN_FORGATAS, beallitas_feladat="fuzet_forgatas")
            forgatas, pontok = kep.forgatas_dontes({k: modszer.kimenet.tisztit(v) for k, v in olv.items()}, self.kat().szokincs())
            if forgatas:
                _, utak = self._oldalak(foto, forgatas)
        foto.olvasat = {"kivagas": meta["kivagas"], "fekvo": meta["fekvo"], "forgatas": forgatas,
                        "forgatas_pontok": pontok, "oldalak": [str(u) for u in utak]}
        if self.cel:                    # „Beszúrás az aktív jegyzetbe”: a fejezet-olvasás nem kell
            return
        prompt = modszer.fejezet_prompt(len(utak), self.kat())
        valasz, jel = self._kerdez(foto, "fejezet", "fuzet_fejezet", prompt, utak, modszer.MAX_TOKEN_FEJEZET)
        foto.olvasat.update(modszer.olvasat(valasz, self.kat()))
        foto.jelek["fuzet_fejezet"] = jel
        self.log(f"[füzet] {foto.nev}: {foto.olvasat.get('tantargy') or '?'} · fejezet "
                 f"{', '.join(foto.olvasat.get('fejezetek') or []) or '—'}" + (f" · forgatás {forgatas}°" if forgatas else ""))

    # -------------------------------------------------- 2. átirat

    def atir(self, foto: Foto) -> None:
        utak = [Path(u) for u in foto.olvasat["oldalak"]]
        valasz, jel = self._kerdez(foto, "atirat", "ocr_kezi", modszer.atirat_prompt(len(utak)), utak, modszer.atirat_max_token())
        foto.atirat = F.atirat_tisztit(valasz)
        foto.kepletek = formatum.kepletek(foto.atirat, self.kepletek_max)
        foto.jelek["ocr_kezi"] = jel

    # -------------------------------------------------- 3. választás

    def valaszt(self, foto: Foto) -> None:
        if self.cel:
            foto.jegyzet = self.cel
            return
        kat = self.kat()
        if not modszer.ismert_targy(foto.olvasat):       # 80(h): „sehová nem illik” — nem köt be, nincs újrapróba
            foto.allapot = "kihagyva"
            foto.uzenet = f"nem illik sehová: a tantárgy ismeretlen ({foto.olvasat.get('tantargy') or '?'})"
            return
        jl = modszer.jeloltek(foto.olvasat, kat)
        foto.jeloltek = jl
        if not jl:
            foto.allapot, foto.uzenet = "hiba", "nincs jelölt jegyzet (a tantárgy ismeretlen)"
            return
        if len(jl) == 1:
            foto.jegyzet = jl[0]
            return
        valasz, jel = self._kerdez(foto, "valaszto", "fuzet_valaszto", modszer.valaszto_prompt(foto.olvasat, jl, kat), None,
                                   modszer.MAX_TOKEN_VALASZTO)
        foto.jegyzet, foto.tartalek = modszer.dontes(valasz, foto.olvasat, jl, kat)
        foto.jelek["fuzet_valaszto"] = jel
        if foto.jegyzet is None:                          # 80(h): a választás nem biztos (a tartalék-ág nem köt be)
            foto.allapot = "kihagyva"
            foto.uzenet = "nem illik sehová: a választás nem biztos (nincs értelmezhető válasz a jelöltekre)"

    # -------------------------------------------------- 4. írás

    def _vault_nevek(self) -> set[str]:
        """A vault fájlneveinek halmaza (NFC, kisbetű) — a cél-mappán KÍVÜL: a puszta név csak akkor link, ha egyértelmű (I29)."""
        if self._nevek is None:
            root, cel, nevek = self.cfg.path("vault"), nfc(self.cel_mappa), set()
            for dp, dn, fn in os.walk(root):
                dn[:] = [d for d in dn if not d.startswith(".")]
                rel = nfc(os.path.relpath(dp, root))
                if rel == cel:
                    continue
                nevek.update(nfc(f).casefold() for f in fn)
            self._nevek = nevek
        return self._nevek

    def celnev(self, foto: Foto) -> tuple[str, bool]:
        """A fotó neve a cél-mappában → (név, már bent áll-e bájtazonosan). Ütközésnél (más tartalom) `<törzs> (2)<kit>`, `(3)`, …"""
        d = self.cfg.path("vault") / self.cel_mappa
        meglevo = {nfc(n).casefold(): n for n in os.listdir(d)} if d.is_dir() else {}
        torzs, kit = os.path.splitext(foto.nev)
        for i in range(1, 1000):
            nev = foto.nev if i == 1 else f"{torzs} ({i}){kit}"
            van = meglevo.get(nfc(nev).casefold())
            if van is None:
                return nev, False
            if kep.sha256(d / van) == foto.sha:
                return van, True
        raise RuntimeError(f"nincs szabad név a cél-mappában: {foto.nev}")

    def _olvas(self, ut: str) -> dict:
        """A cél jegyzet szövege és hash-e: élesben a core-ból; próbában a kör klónjából, ha az már létezik (a kör korábbi tételei
        oda írtak — a csere alapja a klón változata)."""
        if self.proba and self._klon is not None and (self._klon / ut).is_file():
            import hashlib
            b = (self._klon / ut).read_bytes()
            return {"tartalom": b.decode("utf-8"), "hash": hashlib.sha1(b).hexdigest()}
        return gepi_kliens.olvas(ut)

    def link(self, nev: str) -> str:
        return nev if nfc(nev).casefold() not in self._vault_nevek() else f"{self.cel_mappa}/{nev}"

    def _modell_jel(self, foto: Foto) -> dict | None:
        """A gépi írás modell-jele (D9): ha bármelyik lépés próba-modellel futott, az (a szolgáltatás csak klónra engedi); különben a
        döntést hozó lépésé (a választó, aktív jegyzet módban az átirat)."""
        for j in foto.jelek.values():
            if j.get("proba"):
                return j
        return foto.jelek.get("fuzet_valaszto") or foto.jelek.get("ocr_kezi") or foto.jelek.get("fuzet_fejezet")

    def ir(self, foto: Foto) -> None:
        nev, bent = self.celnev(foto)
        link = self.link(nev)
        rp = f"{self.cel_mappa}/{nev}"
        if not self.proba:
            F.ocr_ir(self.cfg, nev, foto.sha, foto.forras.stat().st_size, foto.atirat)
        o = self._olvas(foto.jegyzet)
        uj = formatum.beagyaz(o["tartalom"], link, foto.kepletek, self.szakasz)
        muveletek = []
        if not bent:
            muveletek.append({"tipus": "mozgat", "forras": str(foto.forras), "ut": rp, "sha256": foto.sha})
        if uj != o["tartalom"]:
            muveletek.append(gepi_kliens.csere(foto.jegyzet, uj, o["hash"]))
        if not any(m["tipus"] == "csere" for m in muveletek):
            foto.allapot, foto.uzenet = "bekotve", "már be volt kötve"
            return
        r = gepi_kliens.ir(self.kor, f"foto-{foto.sha[:12]}", FORRAS, muveletek, uzenet=f"füzetfotó: {nev} → {Path(foto.jegyzet).stem}"[:200],
                           proba=self.proba, modell=self._modell_jel(foto),
                           dontes=f"{', '.join(foto.olvasat.get('fejezetek') or []) or 'aktív jegyzet'} → {Path(foto.jegyzet).stem}"[:200])
        foto.allapot = "bekotve"
        if r.get("proba_mappa"):
            self._klon = Path(r["proba_mappa"]) / self.cfg.path("vault").name
        if not self.proba:
            F.allapot_frissit(self.cfg, foto.sha, kep=nev, forras=str(foto.forras), allapot="bekotve", bekotve=[foto.jegyzet],
                              link=link, kor=self.kor, commit=r.get("sha"), ki="gep" if not self.cel else "gep-aktiv",
                              modellek={k: v.get("modell") for k, v in foto.jelek.items()}, kepletek=len(foto.kepletek),
                              uzenet=None)
            F.naplo(self.cfg, "bekotve", sha256=foto.sha, kep=nev, jegyzet=foto.jegyzet, kor=self.kor, commit=r.get("sha"))

    # -------------------------------------------------- a kör

    def jeloltek(self, forrasok: list[Path] | None = None) -> list[Foto]:
        """A feldolgozandó fotók: a figyelt mappák (vagy a megadott mappák/fájlok) képei, a lezártak (bekötve, visszavonva, kihagyva)
        nélkül; legfeljebb `max_foto`."""
        if forrasok:
            mappak = [p for p in forrasok if p.is_dir()]
            utak = kepek(mappak) + [p for p in forrasok if p.is_file() and kep.kep_e(p.name)]
        else:
            utak = kepek(F.figyelt_mappak(self.cfg))
        st = {} if self.proba else F.allapot_betolt(self.cfg)
        ki, latott = [], set()
        for p in utak:
            if F.figyelt_alatt(self.cfg, p) is None and not self.proba:
                self.log(f"[füzet] kihagyva (nem figyelt mappából jön): {p}")
                continue
            sha = kep.sha256(p)
            allapot = (st.get(sha) or {}).get("allapot")
            if sha in latott or (allapot in LEZART and not (self.cel and allapot == "kihagyva")):
                continue                                  # a kifejezett „aktív jegyzet” kérés a kihagyott fotót újra elővehetné
            latott.add(sha)
            ki.append(Foto(p, sha, nfc(p.name)))
            if len(ki) >= self.max_foto:
                break
        return ki

    def futtat(self, forrasok: list[Path] | None = None) -> dict:
        fotok = self.jeloltek(forrasok)
        self.kor = gepi_kliens.uj_kor(KOR_ELOTAG)
        self.log(f"[füzet] {self.kor}: {len(fotok)} új fotó" + (" · PRÓBA (a vault APFS-klónján)" if self.proba else "")
                 + (f" · cél: {self.cel}" if self.cel else ""))
        n = max(len(fotok), 1)
        fazisok = (("olvasás", self.olvas), ("átirat", self.atir), ("választás", self.valaszt), ("írás", self.ir))
        megallt = False
        for fi, (nev, fv) in enumerate(fazisok):
            for i, foto in enumerate(fotok):
                if self.stop():
                    megallt = True
                    break
                if foto.allapot != "uj":
                    continue
                self._haladas(100.0 * (fi * n + i) / (len(fazisok) * n))
                try:
                    fv(foto)
                except NincsModell:
                    raise
                except gepi_kliens.GepiHiba as e:
                    foto.allapot, foto.uzenet = "hiba", f"gépi írás: {e}"
                except Exception as e:  # noqa: BLE001 — a tétel végállapotot kap, a kör megy tovább (D1)
                    foto.allapot, foto.uzenet = "hiba", f"{nev}: {type(e).__name__}: {e}"
                if foto.allapot == "kihagyva":
                    self.log(f"[füzet] {foto.nev}: KIHAGYVA — {foto.uzenet}")
                    if not self.proba:                   # lezárt állapot: sem a figyelő, sem a következő kör nem próbálja újra
                        F.allapot_frissit(self.cfg, foto.sha, kep=foto.nev, forras=str(foto.forras), allapot="kihagyva",
                                          uzenet=foto.uzenet, kor=self.kor)
                        F.naplo(self.cfg, "kihagyva", sha256=foto.sha, kep=foto.nev, ok=foto.uzenet, kor=self.kor)
                if foto.allapot == "hiba":
                    self.log(f"[füzet] {foto.nev}: HIBA — {foto.uzenet}")
                    if not self.proba:
                        F.allapot_frissit(self.cfg, foto.sha, kep=foto.nev, forras=str(foto.forras), allapot="hiba",
                                          uzenet=foto.uzenet)
            if megallt:
                self.log("[füzet] megállítva a tétel végén" + (" (a vault nem változott)" if fi < 3 else ""))
                break
        self._haladas(100.0)
        return self._riport(fotok, megallt)

    def _riport(self, fotok: list[Foto], megallt: bool) -> dict:
        r = {"kor": self.kor, "fajta": "fuzet", "proba": self.proba, "megallitva": megallt, "cel": self.cel,
             "eredmeny": {}, "fotok": []}
        for f in fotok:
            r["eredmeny"][f.allapot] = r["eredmeny"].get(f.allapot, 0) + 1
            r["fotok"].append({"kep": f.nev, "sha256": f.sha, "allapot": f.allapot, "jegyzet": f.jegyzet, "uzenet": f.uzenet,
                               "fejezetek": f.olvasat.get("fejezetek"), "forgatas": f.olvasat.get("forgatas"),
                               "kepletek": len(f.kepletek), "tartalek": f.tartalek,
                               "modellek": {k: v.get("modell") for k, v in f.jelek.items()}})
        d = self.cfg.path("runs") / "fuzet"
        d.mkdir(parents=True, exist_ok=True)
        ut = d / f"{self.kor}.json"
        ut.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log(f"[füzet] vége: {r['eredmeny']}")
        self.log(f"Riport: {ut}")
        return r

    # -------------------------------------------------- az ellenőrző kör (6. pont)

    def ellenoriz(self, limit: int | None = None) -> dict:
        """A bekötött fotók újradöntése (a cél-mappában álló képből); eltérésnél átkötés: a blokk a régi jegyzetből az újba költözik,
        a fotó a helyén marad. Próbában csak a javaslat (`valtozna`), a vault és az állapot nem változik."""
        st = F.allapot_betolt(self.cfg)
        tetelek = sorted(((sha, r) for sha, r in st.items() if r.get("allapot") == "bekotve" and r.get("bekotve")),
                         key=lambda x: x[1].get("kep") or "")[:limit or None]
        self.kor = gepi_kliens.uj_kor(KOR_ELOTAG_ELLENOR)
        self.log(f"[füzet-ellenőrzés] {self.kor}: {len(tetelek)} bekötött fotó" + (" · PRÓBA" if self.proba else ""))
        fotok: list[tuple[Foto, dict]] = []
        for sha, r in tetelek:
            p = self.cfg.path("vault") / self.cel_mappa / r["kep"]
            if p.is_file():
                fotok.append((Foto(p, sha, r["kep"]), r))
        eredmeny: dict[str, int] = {}
        n = max(len(fotok), 1)
        for fi, fv in enumerate((self.olvas, self.valaszt)):
            for i, (foto, _) in enumerate(fotok):
                if self.stop():
                    return self._ell_riport(eredmeny, True)
                self._haladas(70.0 * (fi * n + i) / (2 * n))
                if foto.allapot == "uj":
                    try:
                        fv(foto)
                    except NincsModell:
                        raise
                    except Exception as e:  # noqa: BLE001
                        foto.allapot, foto.uzenet = "hiba", f"{type(e).__name__}: {e}"
        for i, (foto, r) in enumerate(fotok):
            if self.stop():
                return self._ell_riport(eredmeny, True)
            self._haladas(70.0 + 30.0 * i / n)
            if foto.allapot == "kihagyva":
                kimenet = "bizonytalan"                       # 80(h): az ellenőrző kör nem köt át, ha a besorolás nem biztos
            elif foto.allapot == "hiba" or not foto.jegyzet:
                kimenet = "hiba"
            elif foto.jegyzet in (r.get("bekotve") or []):
                kimenet = "megerositve"
            elif self.proba:
                kimenet = "valtozna"
                self.log(f"[füzet-ellenőrzés] {foto.nev}: {', '.join(r['bekotve'])} → {foto.jegyzet} (próba)")
            else:
                try:
                    self._atkot(foto, r)
                    kimenet = "atkotve"
                except Exception as e:  # noqa: BLE001
                    kimenet, foto.uzenet = "hiba", str(e)
            if kimenet == "hiba":
                self.log(f"[füzet-ellenőrzés] {foto.nev}: HIBA — {foto.uzenet}")
            eredmeny[kimenet] = eredmeny.get(kimenet, 0) + 1
        self._haladas(100.0)
        return self._ell_riport(eredmeny, False)

    def _atkot(self, foto: Foto, r: dict) -> None:
        link = r.get("link") or foto.nev
        muveletek, kepletek_ = [], None
        for regi in r.get("bekotve") or []:
            if regi == foto.jegyzet:
                continue
            o = gepi_kliens.olvas(regi)
            sorok = formatum.blokk_kivesz(o["tartalom"], link, self.szakasz)
            if sorok is not None and kepletek_ is None:
                kepletek_ = formatum.callout_kepletei(sorok)
            uj = formatum.levalaszt(o["tartalom"], link, self.szakasz)
            if uj != o["tartalom"]:
                muveletek.append(gepi_kliens.csere(regi, uj, o["hash"]))
        o = gepi_kliens.olvas(foto.jegyzet)
        uj = formatum.beagyaz(o["tartalom"], link, kepletek_ or [], self.szakasz)
        if uj != o["tartalom"]:
            muveletek.append(gepi_kliens.csere(foto.jegyzet, uj, o["hash"]))
        if not muveletek:
            return
        v = gepi_kliens.ir(self.kor, f"foto-{foto.sha[:12]}", FORRAS_ELLENOR, muveletek, modell=self._modell_jel(foto),
                           uzenet=f"füzetfotó átkötése: {foto.nev} → {Path(foto.jegyzet).stem}"[:200],
                           dontes=f"{', '.join(r.get('bekotve') or [])} → {foto.jegyzet}"[:200])
        el = list(r.get("ellenorzes") or []) + [{"ido": F.most(), "kor": self.kor, "commit": v.get("sha"), "regi": r.get("bekotve"),
                                                "uj": [foto.jegyzet], "modellek": {k: j.get("modell") for k, j in foto.jelek.items()}}]
        F.allapot_frissit(self.cfg, foto.sha, bekotve=[foto.jegyzet], ellenorzes=el, allapot="bekotve")
        F.naplo(self.cfg, "atkotve", sha256=foto.sha, kep=foto.nev, regi=r.get("bekotve"), uj=foto.jegyzet, kor=self.kor)
        self.log(f"[átkötve] {foto.nev}: {', '.join(r.get('bekotve') or [])} → {foto.jegyzet}")

    def _ell_riport(self, eredmeny: dict, megallt: bool) -> dict:
        r = {"kor": self.kor, "fajta": "fuzet-ellenoriz", "proba": self.proba, "megallitva": megallt, "eredmeny": eredmeny}
        d = self.cfg.path("runs") / "fuzet"
        d.mkdir(parents=True, exist_ok=True)
        ut = d / f"{self.kor}.json"
        ut.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log(f"[füzet-ellenőrzés] vége: {eredmeny}")
        self.log(f"Riport: {ut}")
        return r
