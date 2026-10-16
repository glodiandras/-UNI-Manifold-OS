"""Jegyzet átnevezése és áthelyezése teljes link-átírással (C10; a legacy I30 szabálya: átnevezés előtt
lista a módosuló fájlokról, egy pillanatkép, utána teljes referencia-próba).

Hatókör: azonos kiterjesztésű fájl vagy mappa, üres és médiás mappák is (CX-003).
A média nem kerül gitbe: a csak szöveges pillanatkép-visszavonás helyett az ilyen mozgást kézzel lehet visszamozgatni.
A megszakadt műveletet a szándéknapló állítja helyre. A `.base` hivatkozásokat a `core/bazis/hivatkozas.py` kezeli. A terv **leképezéssel** (`lek`: régi → új út minden mozgó szöveges fájlra) dolgozik;
a mappa egyetlen atomi `os.rename`-mel mozog, egy gépi commit rögzíti. A feloldás szabálya a `core/index/feloldas.py`-é (L42), itt nincs saját szabály:
a terv minden linket **előtte** és **utána** (a régi szöveggel) feloldja, és átír mindent, ami nem a
várt célra oldódna — a régi fájlra mutatókat és az *elrabolt* linkeket is (áthelyezés után egy azonos
alapnevű másik fájl kerülhet közelebb a forráshoz).

Végrehajtás (a kör-zár alatt): kézi commit → hash-ellenőrzés → előtte-próba a lemezről → **szándéknapló** →
atomi írások és az átnevezés → utána-próba (az indextől független, `feloldas.hivatkozasok`) → egy gépi commit →
a napló törlése. Bármi hiba vagy a próba bukása: a memóriában tartott eredeti bájtokból teljes visszaállítás,
commit nincs. Ha a folyamat közben meghal (SIGKILL, áramszünet), a napló (`{run}/atnevezes/`: a terv és az
eredeti bájtok, az első írás előtt fsync-elve) alapján a következő induláskor `helyreallit` állít vissza (H3). Az átírt
fájlokat nem jelentjük be `sajat`-ként: a nyitott szerkesztők külső változásként, csendben újratöltenek.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import frame, osszeomlas, snapshot, tartos, vaultio
from .bazis import hivatkozas as bazis_hivatkozas
from .index import feloldas, linkek
from .index.feloldas import SKIP_DIRS, Feloldo, nfc
from .hibakod import kodol

SZOVEGES = (".md", ".canvas")
MOZGATHATO = SZOVEGES + (".base",)        # a `.base` szöveges fájl, a pillanatkép-tárolóban van (23. döntés)
FORRAS = vaultio.FORRAS                   # a felhasználó kézi munkája (L09), nincs új érték
ELOTAG = "ATNEV"                          # új kör-előtag (L12)
MAX_RESZLET = 200                         # a tervben fájlonként ennyi link-sor részletezve


NAPLO = "atnevezes"                       # a szándéknapló mappája a {run} alatt (H3)
ZAR_VARAKOZAS_MP = 10.0                   # ennyit vár egy érintett út zárára (egy másik írás), utána 409


def _naplo_mappa(cfg) -> Path:
    return cfg.path("run") / NAPLO


# a szándéknapló darabjai `F_FULLFSYNC`-kel (core/tartos.py); a régi nevek a gépi írásnak és a teszteknek maradnak
_fsync_ir = tartos.fsync_ir
_fsync_mappa = tartos.fsync_mappa


def _atomi_ir(p: Path, b: bytes) -> None:
    vaultio.atomi_csere(p, b)


def _naplo_torol(cfg) -> None:
    """A szándéknapló törlése (a commit után, vagy a sikeres visszaállítás után)."""
    shutil.rmtree(_naplo_mappa(cfg), ignore_errors=True)


def _pontos(p: Path) -> bool:
    try:
        return any(nfc(n) == nfc(p.name) for n in os.listdir(p.parent))
    except FileNotFoundError:
        return False


def _mozgat(regi: Path, uj: Path) -> None:
    """Kizáró átnevezés; azonos inode-on a kis-nagybetű cseréje is atomi."""
    if str(regi).casefold() == str(uj).casefold() and uj.exists() and os.path.samefile(regi, uj):
        os.rename(regi, uj)
        _fsync_mappa(uj.parent)
    else:
        tartos.rename_excl(regi, uj)


def helyreallit(cfg) -> list[str]:
    """Induláskor (a kör-zár alatt, az index előtt): ha egy átnevezés naplója megmaradt, a folyamat az írások és a
    commit között halt meg (H3). Ha a commit megtörtént (a `Mos-Kor` a naplóé), csak a napló törlődik; különben az
    átnevezés visszafordul, és minden fájl az eredeti bájtjait kapja vissza — de csak ott, ahol a lemezen a terv
    szerinti új (vagy már az eredeti) változat áll: a közben kézzel átírt fájlt nem írja felül, és ilyenkor a napló
    `atnevezes-megtartva-<idő>` néven megmarad. → a felhasználónak szóló üzenetek."""
    d = _naplo_mappa(cfg)
    if not d.exists():
        return []
    if not frame.vault_letezik(cfg):    # T002: nem létező vaulton nincs mit visszaállítani; a napló a valódi vaultra vár
        return []
    tj = d / "terv.json"
    if not tj.is_file():            # a napló az első írás előtt készül: terv nélkül a vault még érintetlen
        _naplo_torol(cfg)
        return []
    n = json.loads(tj.read_text(encoding="utf-8"))
    if n.get("kesz"):
        _naplo_torol(cfg)
        return []
    repo = snapshot.repos(cfg).get("vault")
    if repo is not None and repo.live() and repo.has_head() and repo.kor_commitok(n["kor"]):     # a teljes történetben (T094)
        _naplo_torol(cfg)
        return []
    root = cfg.path("vault")
    p_regi, p_uj = root / n["regi_lemez"], root / n["uj_lemez"]
    visszaallt = []                 # amit ténylegesen visszaírtunk: az üzenet csak erről állíthat valamit
    if _pontos(p_uj) and not _pontos(p_regi):
        _mozgat(p_uj, p_regi)        # T092: közben létrejött régi útra nem ír rá
        visszaallt.append(n["uj"])
    utkozo = []
    for f in n["fajlok"]:
        p = root / f["lemez"]
        eredeti = (d / "eredeti" / f["eredeti"]).read_bytes()
        try:
            most = p.read_bytes()
        except FileNotFoundError:
            most = None
        if most == eredeti:
            continue
        if most is not None and _sha1(most) == f["uj_sha1"]:
            _atomi_ir(p, eredeti)
            visszaallt.append(f["ut"])
        else:
            utkozo.append(f["ut"])
    if repo is not None and repo.live():
        repo.index_frissit()                # a visszaírt fájlok stat-adata ne zajoljon a git-indexben (T101)
    elso = f"A rename was interrupted ({n['regi']} → {n['uj']}) when the core stopped during writing. "
    if visszaallt:
        uzenet = elso + "The vault was restored to its state before the rename. You can try renaming again."
    elif utkozo:
        uzenet = elso + "No files could be restored."
    else:
        uzenet = elso + "The vault had not changed, so no restoration was needed. You can try renaming again."
    if utkozo:
        megtartva = d.with_name(f"{NAPLO}-megtartva-{time.strftime('%Y%m%d-%H%M%S')}")
        os.rename(d, megtartva)
        uzenet += (f" These files were changed by another writer and were left untouched: {', '.join(utkozo[:10])}. "
                   f"Their original bytes are preserved at: {megtartva}.")
    else:
        _naplo_torol(cfg)
    return [uzenet]


class Hiba(Exception):
    """Az átnevezés kérés- vagy állapothibája; `kod`: HTTP-kód."""

    def __init__(self, statusz: int, uzenet: str, **adat):
        super().__init__(uzenet)
        self.kod, self.adat = statusz, adat
        # The numeric HTTP status and the string translation code are independent.
        if isinstance(adat.get("kod"), str):
            kodol(self, adat["kod"], adat.get("param"))


@dataclass
class _Fajl:
    ut: str
    alap: str                                   # a terv idején a lemezen álló bájtok sha1-je
    regi: bytes
    uj: bytes
    szerk: list[dict] = field(default_factory=list)     # a módosuló sorok (soronként egyszer, előtte → utána)
    darab: int = 0                                      # a módosuló linkek száma (egy sorban több is lehet)


@dataclass
class _Terv:
    regi: str                                   # a fájl vagy a mappa régi útja
    uj: str
    blokkolok: list[str]
    fajlok: dict[str, _Fajl]
    linkek: int = 0
    uj_feloldott: int = 0
    hash: str = ""
    lek: dict[str, str] = field(default_factory=dict)       # régi → új út minden mozgó szöveges fájlra (C11a)
    mappa: bool = False                                     # mappa-leképezés
    figyelmeztetesek: list[dict] = field(default_factory=list)      # amit az átírás nem érint, de másként viselkedhet


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _sor_info(szoveg: str, kezd: int) -> tuple[int, str]:
    a = max(szoveg.rfind("\n", 0, kezd), szoveg.rfind("\r", 0, kezd)) + 1
    veg = [x for x in (szoveg.find("\n", kezd), szoveg.find("\r", kezd)) if x >= 0]
    b = min(veg) if veg else len(szoveg)
    return len(re.findall(r"\r\n|\r|\n", szoveg[:kezd])) + 1, szoveg[a:b][:300]


def _alkalmaz(szoveg: str, szerk: list[tuple[int, int, str]]) -> tuple[str, list[int]]:
    """A cserék alkalmazása; → az új szöveg és a cserék új kezdőhelyei (az eredeti sorrendben)."""
    ki, poz, eltolas, ujak = [], 0, 0, []
    for kezd, veg, ujszoveg in sorted(szerk):
        ki.append(szoveg[poz:kezd])
        ki.append(ujszoveg)
        ujak.append(kezd + eltolas)
        eltolas += len(ujszoveg) - (veg - kezd)
        poz = veg
    ki.append(szoveg[poz:])
    return "".join(ki), ujak


class Atnevezes:
    """Az átnevezés szolgáltatás: `terv` (csak olvas) és `vegrehajt`. `busy`: igaz, ha vault-író feladat fut."""

    def __init__(self, cfg, vault: vaultio.Vault, index, busy=lambda: False, publish=lambda e, **k: None,
                 mentetlen=lambda: set()):
        self.cfg, self.v, self.ix, self.busy, self.publish = cfg, vault, index, busy, publish
        self.mentetlen = mentetlen          # a felület által jelentett mentetlen utak (WS `mentetlen`, C16.5): ezekbe nem nyúlunk

    # ================================================================ terv

    def _ellenoriz(self, ut, uj) -> tuple[str, str, list[str]]:
        regi, uj = self.v.kanonikus(vaultio.norm_path(ut)), self.v.kanonikus(vaultio.norm_path(uj), utolso=False)
        blok: list[str] = []
        er, eu = os.path.splitext(regi)[1].lower(), os.path.splitext(uj)[1].lower()
        if eu != er:
            blok.append(f"A kiterjesztés nem változhat ({er}).")
        nev = os.path.splitext(os.path.basename(uj))[0]
        if not nev.strip() or nev.startswith(".") or vaultio._TILTOTT_NEV.search(nev) or len(nev.encode("utf-8")) > 200:
            blok.append('Érvénytelen név — tilos benne: \\ / : * ? " < > | # ^ [ ], és nem kezdődhet ponttal.')
        mappa = os.path.dirname(uj)
        if any(r in SKIP_DIRS for r in mappa.split("/")):
            blok.append("Ide nem helyezhető át (a mappa a vault-index hatókörén kívül esik).")
        elif mappa and not self.v._abs(mappa).is_dir():
            blok.append(f"Nincs ilyen mappa: {mappa}")
        if regi == uj:
            blok.append("A név és a hely nem változott.")
        elif not blok:
            p_regi = self.v.lemezen(regi)
            cel_mappa = self.v._abs(mappa) if mappa else self.v.root
            for n in os.listdir(cel_mappa):
                if nfc(n).lower() == nfc(os.path.basename(uj)).lower():
                    if not p_regi.exists() or not os.path.samefile(cel_mappa / n, p_regi):
                        blok.append(f"Már van ilyen nevű fájl: {uj}")
        return regi, uj, blok

    def _uj_cel(self, fo_u: Feloldo, cel: str, vart: str, forras: str, fajta: str) -> str | None:
        """Új cél-szöveg egy linkhez: stílusőrző, majd a rövid egyértelmű; mindig a feloldóval ellenőrizve."""
        jeloltek = [vart] if fajta == "canvas_fajl" else linkek.uj_cel_szoveg(cel, vart)
        jeloltek.append(linkek.rovid_cel(fo_u, vart, forras))
        tiltott = r"[)\n]" if fajta == "md" else r"[\]|#\n]"
        for j in dict.fromkeys(jeloltek):
            if fajta != "canvas_fajl" and re.search(tiltott, j):
                continue
            if fo_u.resolve(j, forras)[0] == vart:
                return j
        return None

    def _mappa_e(self, regi: str) -> bool:
        return self.v._abs(regi).is_dir()

    def _ellenoriz_mappa(self, regi: str, uj: str) -> tuple[list[str], dict[str, str]]:
        """A mappa-mozgatás szabályai (21. döntés): → (blokkolók, leképezés). Csak a kizárólag `.md`/`.canvas`
        fájlt tartalmazó részfa mozoghat (a média nincs a pillanatkép-tárolóban, a visszavonás nem hozná vissza)."""
        blok: list[str] = []
        if any(r in SKIP_DIRS or r.startswith(".") for r in regi.split("/")):
            blok.append("Rejtett vagy a vault-index hatókörén kívüli mappa nem mozgatható.")
        nev = os.path.basename(uj)
        if not nev.strip() or nev.startswith(".") or vaultio._TILTOTT_NEV.search(nev) or len(nev.encode("utf-8")) > 200:
            blok.append('Érvénytelen mappanév — tilos benne: \\ / : * ? " < > | # ^ [ ], és nem kezdődhet ponttal.')
        mappa = os.path.dirname(uj)
        if any(r in SKIP_DIRS for r in mappa.split("/")):
            blok.append("Ide nem helyezhető át (a mappa a vault-index hatókörén kívül esik).")
        elif mappa and not self.v._abs(mappa).is_dir():
            blok.append(f"Nincs ilyen mappa: {mappa}")
        if regi == uj:
            blok.append("A név és a hely nem változott.")
        elif nfc(uj).lower().startswith(nfc(regi).lower() + "/"):
            blok.append("Egy mappa nem helyezhető önmagába.")
        elif not blok:
            cel_mappa = self.v._abs(mappa) if mappa else self.v.root
            for n in os.listdir(cel_mappa):
                if nfc(n).lower() == nfc(nev).lower():
                    if not os.path.samefile(cel_mappa / n, self.v._abs(regi)):
                        blok.append(f"Már van ilyen nevű mappa vagy fájl: {uj}")
        root, p_regi = self.v.root, self.v._abs(regi)
        nem_szoveges: list[str] = []
        szoveges: dict[str, str] = {}
        for dp, dn, fn in os.walk(p_regi):
            dn.sort()
            for d in list(dn):
                if d.startswith(".") or d in SKIP_DIRS or os.path.islink(os.path.join(dp, d)):
                    nem_szoveges.append(nfc(os.path.relpath(os.path.join(dp, d), root)) + "/")
                    dn.remove(d)
            for f in sorted(fn):
                if f == ".DS_Store":
                    continue
                rel = os.path.relpath(os.path.join(dp, f), root)
                if f.startswith(".") or os.path.islink(os.path.join(dp, f)):
                    nem_szoveges.append(nfc(rel))
                else:
                    szoveges[nfc(rel)] = rel
        if nem_szoveges:
            pl = ", ".join(nem_szoveges[:5]) + (f" … (összesen {len(nem_szoveges)})" if len(nem_szoveges) > 5 else "")
            blok.append(f"Rejtett fájl vagy szimbolikus link van a mappában: {pl}.")
        lek: dict[str, str] = {}
        for ut_nfc in szoveges:
            if not ut_nfc.startswith(regi + "/"):
                blok.append("A mappa neve a lemezen más betűzéssel áll (kis-nagybetű): add meg pontosan.")
                return blok, {}
            lek[ut_nfc] = uj + ut_nfc[len(regi):]
        return blok, lek

    def _terv(self, ut, uj) -> _Terv:
        regi = self.v.kanonikus(vaultio.norm_path(ut))         # T018: a lemezen álló (kanonikus) alak — a leképezés kulcsai ezek
        if self._mappa_e(regi):
            uj = self.v.kanonikus(vaultio.norm_path(uj), utolso=False)
            blok, lek = self._ellenoriz_mappa(regi, uj)
            terv = _Terv(regi, uj, blok, {}, lek=lek, mappa=True)
            if blok:
                return terv
            fajlok = [rp for rp, _ in feloldas.bejaras(self.v.root)]
            halmaz = set(fajlok)
            for r in lek:
                if r not in halmaz:
                    terv.blokkolok.append(f"{r}: még nincs az indexben — próbáld újra")
            for u in lek.values():
                if u in halmaz:
                    terv.blokkolok.append(f"Már van ilyen nevű fájl: {u}")
            return terv if terv.blokkolok else self._terv_kozos(terv, fajlok)
        regi, uj, blok = self._ellenoriz(ut, uj)
        terv = _Terv(regi, uj, blok, {}, lek={regi: uj})
        if blok:
            return terv
        fajlok = [rp for rp, _ in feloldas.bejaras(self.v.root)]
        if regi not in fajlok:
            raise kodol(vaultio.NotFound(f"nincs ilyen fájl az indexben: {regi}"), "atnevezes.nincs_ilyen_fajl_indexben_regi", {"regi": regi})
        if uj in fajlok:
            terv.blokkolok.append(f"Már van ilyen nevű fájl: {uj}")
            return terv
        return self._terv_kozos(terv, fajlok)

    def _terv_kozos(self, terv: _Terv, fajlok: list[str]) -> _Terv:
        """A link-átírás terve a leképezésre (egy fájl: egyelemű leképezés): minden link előtte és utána feloldva.
        A link-ciklus után a Bases-források (`.base` fájlok, ```` ```base ```` blokkos jegyzetek) kifejezéseiben
        álló hivatkozások is sorra kerülnek; a cserék a jegyzetlinkek cseréivel egy tervben, egy commitban."""
        lek = terv.lek
        fo_e = Feloldo(fajlok)
        fo_u = Feloldo([x for x in fajlok if x not in lek] + list(lek.values()))
        forrasok: dict[str, list[dict]] = {}
        for r in self.ix.link_sorok():
            forrasok.setdefault(r["forras"], []).append(r)
        bazisok = {f["ut"]: f for f in self.ix.bazis_forrasok()}
        for forras, sorok in forrasok.items():
            s2 = lek.get(forras, forras)
            szukseges = []
            for i, r in enumerate(sorok):
                cel = r["cel_nyers"] or ""
                t = fo_e.resolve(cel, forras)[0]
                utana = fo_u.resolve(cel, s2)[0]
                terv.linkek += 1
                if t is None:
                    terv.uj_feloldott += utana is not None
                    continue
                vart = lek.get(t, t)
                if utana != vart:
                    szukseges.append((i, cel, vart, r["fajta"]))
            if szukseges or forras in bazisok:
                self._fajl_terv(terv, forras, s2, sorok, szukseges, fo_e, fo_u, (bazisok.get(forras) or sorok[0])["hash"],
                                forras in bazisok)
        for forras, f in bazisok.items():           # `.base` fájl, vagy base-blokkos jegyzet link nélkül
            if forras not in forrasok:
                self._fajl_terv(terv, forras, lek.get(forras, forras), [], [], fo_e, fo_u, f["hash"], True)
        terv.hash = _sha1(json.dumps(
            {"regi": terv.regi, "uj": terv.uj, "lek": sorted(lek.items()),
             "fajlok": [[f.ut, f.alap, f.szerk, f.darab] for _, f in sorted(terv.fajlok.items())]},
            sort_keys=True).encode("ascii"))
        return terv

    def _fajl_terv(self, terv: _Terv, forras: str, s2: str, sorok: list[dict], szukseges: list, fo_e: Feloldo,
                   fo_u: Feloldo, hash_: str, bazis: bool) -> None:
        """Egy forrásfájl cseréi: a link-cserék (`szukseges`) és, ha a fájl Bases-forrás (`bazis`), a kifejezéseiben
        álló hivatkozások cseréi. `hash_`: az index szerinti tartalom-hash (a `sorok` üres lehet: csak base-blokkos
        jegyzet, `.base` fájl)."""
        p = self.v.lemezen(forras)
        try:
            b = p.read_bytes()
        except OSError as e:
            terv.blokkolok.append(f"{forras}: nem olvasható ({e.strerror})")
            return
        if _sha1(b) != hash_:
            terv.blokkolok.append(f"{forras}: közben megváltozott, az index még nem érte utol — próbáld újra")
            return
        szoveg = linkek.dekodol(b)
        low = forras.lower()
        szerk_ki: list[dict] = []
        extra = 0                                       # a base-cserék literálonkénti többlete a csere-darabhoz képest
        if low.endswith(".md"):
            refs = linkek.jegyzet_talalatok(szoveg)
            if [t.cel for t in refs] != [r["cel_nyers"] or "" for r in sorok]:
                terv.blokkolok.append(f"{forras}: a link-lista nem egyezik az indexszel — próbáld újra")
                return
            cserek = []
            for i, cel, vart, fajta in szukseges:
                t = refs[i]
                j = self._uj_cel(fo_u, cel, vart, s2, fajta)
                if j is None:
                    terv.blokkolok.append(f"{forras}: a(z) „{cel.strip()}” link nem írható át egyértelműen")
                    continue
                pre, _, post = linkek.cel_resz(szoveg[t.kezd:t.veg])
                if fajta == "md" and not t.burok and " " not in szoveg[t.kezd:t.veg].strip():
                    # C31 (36. döntés): az md-link célja kódolt alakban (az Obsidian `hd()`-je); a nyers szóközös régi
                    # alak (a CommonMark szerint nem link, a gráf mégis annak veszi) stílusőrzően nyers marad
                    j = feloldas.md_kodol(j)
                cserek.append((t.kezd, t.veg, pre + j + post))
            if bazis:
                cserek, extra = self._bazis_cserek(terv, szoveg, "md", forras, s2, fo_e, fo_u, cserek)
            uj_szoveg, ujhelyek = _alkalmaz(szoveg, cserek)
            for (kezd, _, _), uh in zip(sorted(cserek), ujhelyek):
                sor, regi_sor = _sor_info(szoveg, kezd)
                szerk_ki.append({"sor": sor, "regi": regi_sor, "uj": _sor_info(uj_szoveg, uh)[1]})
        elif low.endswith(".canvas"):
            uj_szoveg, szerk_ki = self._canvas_terv(terv, forras, s2, sorok, szukseges, fo_u, szoveg)
            if uj_szoveg is None:
                return
        else:                                           # `.base`: nincs jegyzetlink, csak kifejezésekben álló hivatkozás
            cserek, extra = self._bazis_cserek(terv, szoveg, "base", forras, s2, fo_e, fo_u, [])
            uj_szoveg, ujhelyek = _alkalmaz(szoveg, cserek)
            for (kezd, _, _), uh in zip(sorted(cserek), ujhelyek):
                sor, regi_sor = _sor_info(szoveg, kezd)
                szerk_ki.append({"sor": sor, "regi": regi_sor, "uj": _sor_info(uj_szoveg, uh)[1]})
        if uj_szoveg != szoveg:
            egyedi = list({(x["sor"], x["regi"], x["uj"]): x for x in szerk_ki}.values())     # soronként egyszer
            terv.fajlok[forras] = _Fajl(forras, _sha1(b), b, linkek.kodol(uj_szoveg), egyedi[:MAX_RESZLET],
                                        len(szerk_ki) + extra)

    def _bazis_cserek(self, terv: _Terv, szoveg: str, fajta: str, forras: str, s2: str, fo_e: Feloldo, fo_u: Feloldo,
                      cserek: list) -> tuple[list, int]:
        """A Bases-kifejezésekben álló hivatkozások cseréi (`hivatkozas.cserek_keszit`) a már meglévő cserékhez
        fésülve; a blokkolók és a figyelmeztetések a tervbe kerülnek. → (az összes csere, a többlet-darabszám)."""
        er = bazis_hivatkozas.cserek_keszit(
            szoveg, fajta, forras, s2, terv.lek, fo_e, fo_u,
            lambda cel, vart: self._uj_cel(fo_u, cel, vart, s2, "wiki"),
            (terv.regi, terv.uj) if terv.mappa else None)
        terv.blokkolok += er.blokkolok
        terv.figyelmeztetesek += er.figyelmeztetesek
        return list(cserek) + er.cserek, er.db - len(er.cserek)

    def _canvas_terv(self, terv, forras, s2, sorok, szukseges, fo_u, szoveg):
        refs = []        # (literál-index, kezd a dekódolt szövegben | None, veg, cel, fajta)
        lit = linkek.canvas_stringek(szoveg)
        for li, (kezd, veg, ertek, kulcs, _) in enumerate(lit):
            if kulcs == "file" and ertek:
                refs.append((li, None, None, ertek, "canvas_fajl"))
            elif kulcs == "text" and isinstance(ertek, str) and "[[" in ertek:
                for m in feloldas.canvas_wiki(ertek):
                    refs.append((li, m.start(1), m.end(1), m.group(1), "canvas_szoveg"))
        if [r[3] for r in refs] != [r["cel_nyers"] or "" for r in sorok]:
            terv.blokkolok.append(f"{forras}: a canvas link-listája nem egyezik az indexszel — próbáld újra")
            return None, []
        literal_cserek: dict[int, list[tuple[int, int, str]]] = {}
        szerk_ki = []
        for i, cel, vart, fajta in szukseges:
            li, a, b_, _, _ = refs[i]
            j = self._uj_cel(fo_u, cel, vart, s2, fajta)
            if j is None:
                terv.blokkolok.append(f"{forras}: a(z) „{cel.strip()}” link nem írható át egyértelműen")
                continue
            sor = szoveg.count("\n", 0, lit[li][0]) + 1
            szerk_ki.append({"sor": sor, "regi": cel.strip(), "uj": j})
            if a is None:
                literal_cserek[li] = [(0, 0, j)]
            else:
                ertek = lit[li][2]
                pre, _, post = linkek.cel_resz(ertek[a:b_])
                literal_cserek.setdefault(li, []).append((a, b_, pre + j + post))
        cserek = []
        for li, lista in literal_cserek.items():
            kezd, veg, ertek = lit[li][0], lit[li][1], lit[li][2]
            ujertek = lista[0][2] if lit[li][3] == "file" else _alkalmaz(ertek, lista)[0]
            cserek.append((kezd, veg, linkek.json_literal(ujertek)))
        return _alkalmaz(szoveg, cserek)[0], szerk_ki

    def terv(self, ut, uj) -> dict:
        """A terv a felhasználónak: mi módosul, mi blokkol. Csak olvas."""
        t = self._terv(ut, uj)
        return {"ok": not t.blokkolok, "regi": t.regi, "uj": t.uj, "mappa": t.mappa, "blokkolok": t.blokkolok,
                "mozgo_fajlok": len(t.lek), "atnevezesek": [{"regi": r, "uj": u} for r, u in sorted(t.lek.items())[:500]],
                "fajlok": [{"ut": f.ut, "alap": f.alap, "darab": f.darab, "linkek": f.szerk}
                           for _, f in sorted(t.fajlok.items())],
                "modositott_linkek": sum(f.darab for f in t.fajlok.values()),
                "osszes_link": t.linkek, "uj_feloldott": t.uj_feloldott, "figyelmeztetesek": t.figyelmeztetesek,
                "terv_hash": t.hash}

    # ================================================================ referencia-próba

    @staticmethod
    def _proba(elotte: dict, utana: dict, t: _Terv, vart_hash: dict[str, str]) -> list[str]:
        """A teljes referencia-próba (I30): minden korábban feloldott link a várt célra old, a fájlhalmaz a
        várt, és a terven kívüli szöveges fájlok bájtra azonosak. → a hibák listája (üres: rendben)."""
        hibak: list[str] = []
        lek = t.lek
        vart_fajlok = {lek.get(x, x) for x in elotte["files"]}
        # C33: a terven KÍVÜLI fájl megjelenése/eltűnése (egy külső író: Obsidian-szinkron, Finder) nem az átnevezés hibája —
        # azt az `_kulso_fajlvaltozas` jelzi a hívónak (409); itt csak a terv útjainak eltérése számít
        terv_utak = set(lek) | set(lek.values())
        belso = sorted(x for x in set(utana["files"]) ^ vart_fajlok if x in terv_utak)
        if belso:
            hibak.append(f"a fájlhalmaz eltér a vártól: {belso[:5]}")
        for forras, lista in elotte["linkek"].items():
            s2 = lek.get(forras, forras)
            masik = utana["linkek"].get(s2)
            if masik is None:
                hibak.append(f"{s2}: nincs meg a próbában")
                continue
            if len(masik) != len(lista):
                hibak.append(f"{s2}: a linkek száma {len(lista)} → {len(masik)}")
                continue
            for i, ((c0, h0), (c1, h1)) in enumerate(zip(lista, masik)):
                if h0 is None:
                    continue
                vart = lek.get(h0, h0)
                if h1 != vart:
                    hibak.append(f"{s2}: a(z) {i + 1}. link („{c1.strip()}”) {h1!r} helyett {vart!r}-re kellene oldódnia")
            if len(hibak) >= 20:
                break
        for rp, h in elotte["hash"].items():
            s2 = lek.get(rp, rp)
            vart = vart_hash.get(rp, h)
            if utana["hash"].get(s2) != vart:
                hibak.append(f"{s2}: a tartalma nem a várt ({'tervezett csere' if rp in vart_hash else 'a terven kívül változott'})")
            if len(hibak) >= 20:
                break
        return hibak[:20]

    @staticmethod
    def _kulso_fajlvaltozas(elotte: dict, utana: dict, t: _Terv) -> list[str]:
        """A terven kívüli fájlok, amelyek az átnevezés ablakában megjelentek vagy eltűntek (külső író) — C33."""
        lek = t.lek
        vart_fajlok = {lek.get(x, x) for x in elotte["files"]}
        terv_utak = set(lek) | set(lek.values())
        return sorted(x for x in set(utana["files"]) ^ vart_fajlok if x not in terv_utak)

    # ================================================================ végrehajtás

    def _ir(self, p: Path, b: bytes, regi: bytes | None = None) -> None:
        """Atomi írás; `regi` megadásakor a csere előtt újra ellenőrzi, hogy a fájl még az, amit a terv olvasott."""
        if regi is None:
            _atomi_ir(p, b)
            return

        def ellenoriz():
            if p.read_bytes() != regi:
                raise Hiba(409, f"{p.name} közben megváltozott — nézd át újra a tervet.", valtozott=True)
        vaultio.atomi_csere(p, b, ellenoriz)

    def _naplo_ir(self, t: _Terv, kor: str, p_regi: Path, p_uj: Path) -> None:
        """A szándéknapló (H3) az első írás előtt: az eredeti bájtok és a terv, fsync-elve. A `terv.json` kerül
        utoljára a helyére (atomi csere): a napló csak vele érvényes."""
        root, d = self.v.root, _naplo_mappa(self.cfg)
        if d.exists():          # a `_regi_naplo` már feldolgozta; ide csak egy versenyhelyzet juthat — némán nem törlünk (T016)
            raise Hiba(409, f"Egy szándéknapló áll ({d}); addig új átnevezés nem indulhat.", naplo=True)
        (d / "eredeti").mkdir(parents=True)
        fajlok = []
        for i, (rp, f) in enumerate(t.fajlok.items()):
            _fsync_ir(d / "eredeti" / f"{i}.bin", f.regi)
            fajlok.append({"ut": rp, "lemez": os.path.relpath(self.v.lemezen(rp), root), "eredeti": f"{i}.bin",
                           "regi_sha1": _sha1(f.regi), "uj_sha1": _sha1(f.uj)})
        _fsync_mappa(d / "eredeti")
        terv = {"verzio": 1, "kor": kor, "regi": t.regi, "uj": t.uj, "mappa": t.mappa,
                "regi_lemez": os.path.relpath(p_regi, root),
                "uj_lemez": os.path.relpath(p_uj, root), "fajlok": fajlok, "ido": time.strftime("%Y-%m-%d %H:%M:%S")}
        _fsync_ir(d / "terv.json.tmp", json.dumps(terv, ensure_ascii=False, indent=1).encode("utf-8"))
        os.replace(d / "terv.json.tmp", d / "terv.json")
        _fsync_mappa(d)
        _fsync_mappa(d.parent)

    def vegrehajt(self, ut, uj, terv_hash) -> dict:
        repo = self.v.repo()
        if repo is None:
            raise kodol(Hiba(409, "Nincs élő pillanatkép-tároló: pillanatkép nélkül nem nevezek át."), "atnevezes.nincs_pillanatkep")
        if self.busy():
            raise Hiba(409, "Egy vault-író feladat fut — az átnevezés a vége után indítható.", foglalt=True)
        t = self._terv(ut, uj)
        if t.blokkolok:
            raise Hiba(409, "Az átnevezés nem hajtható végre: " + " ".join(t.blokkolok), blokkolok=t.blokkolok)
        if not isinstance(terv_hash, str) or terv_hash != t.hash:
            raise Hiba(409, "A vault közben megváltozott — nézd át újra a tervet.", valtozott=True)
        self._mentetlen_ellenor(t)
        t0 = time.perf_counter()
        try:
            with frame.run_lock(self.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(self.cfg)):
                return self._vegrehajt_zarban(repo, t, t0)
        except frame.Busy as e:
            raise Hiba(409, str(e), foglalt=True) from e

    def _mentetlen_ellenor(self, t: _Terv) -> None:
        """T015: ha a forrás (mappánál a részfa) a felület jelentése szerint mentetlen, 409 — az átnevezés a szerkesztő szövegét
        nem dobhatja el és nem írhatja át. (A felület az átnevezés előtt lezárja a dokumentumokat; ez a védelem a közben
        elkezdett gépelésre való.) Az összevetés kis-nagybetűtől és normalizálástól független."""
        mozgo = {nfc(u).casefold(): u for u in t.lek}
        nyitott = sorted(mozgo[k] for k in {nfc(u).casefold() for u in self.mentetlen()} if k in mozgo)
        if nyitott:
            raise Hiba(409, "A jegyzet nyitva van mentetlen változással — az átnevezés addig nem indulhat (mentsd el vagy zárd be): "
                            + ", ".join(nyitott[:5]) + (f" … (összesen {len(nyitott)})" if len(nyitott) > 5 else ""),
                       nyitott=True, utak=nyitott)

    def _regi_naplo(self) -> None:
        """T016: egy megmaradt szándéknapló a kör-zár alatt, a kézi commit ELŐTT előbb helyreáll vagy félrekerül — soha
        nem törlődik némán. Ha nem oldható fel, az új átnevezés 409-et kap."""
        d = _naplo_mappa(self.cfg)
        if not d.exists():
            return
        try:
            for u in helyreallit(self.cfg):
                print(f"[átnevezés] {u}", file=sys.stderr, flush=True)
        except (OSError, ValueError, KeyError, snapshot.SnapshotError) as e:
            raise Hiba(409, f"Egy megszakadt átnevezés naplója áll ({d}), és nem sikerült feldolgozni: {e}. "
                            "Addig új átnevezés nem indulhat.", naplo=True) from e
        if d.exists():
            raise Hiba(409, f"Egy megszakadt átnevezés naplója áll ({d}); addig új átnevezés nem indulhat.", naplo=True)

    @contextlib.contextmanager
    def _utak_zarolva(self, t: _Terv):
        """T015: minden átírt és mozgó út `vaultio` útvonal-zára, rendezett sorrendben (mint a gépi írásé; a kör-zárat már
        tartjuk, a gépi írás és a mentés a kör-zárat csak megpróbálja, így holtpont nincs). Amíg tartjuk, a szerkesztő mentése
        ezekre az utakra vár (utána a megváltozott alap miatt 409-et kap) — nem csúszhat be az átírás és a próba közé."""
        zarak: dict[int, object] = {}
        for u in sorted({*t.fajlok, *t.lek, *t.lek.values()}, key=lambda x: nfc(x).casefold()):
            z = vaultio._ut_zar(u)
            zarak.setdefault(id(z), z)
        with contextlib.ExitStack() as verem:
            for z in zarak.values():
                if not z.acquire(timeout=ZAR_VARAKOZAS_MP):
                    raise Hiba(409, "Egy másik írás (mentés vagy gépi írás) éppen tart az érintett jegyzetek valamelyikén — "
                                    "próbáld újra.", foglalt=True)
                verem.callback(z.release)
            yield

    def _vegrehajt_zarban(self, repo: snapshot.Repo, t: _Terv, t0: float) -> dict:
        self._regi_naplo()
        with self._utak_zarolva(t):
            self._mentetlen_ellenor(t)
            return self._vegrehajt_zarolva(repo, t, t0)

    # ---------------------------------------------------------------- a referencia-próba állapotai (T106)

    @staticmethod
    def _fajl_linkjei(rp: str, b: bytes, fo: Feloldo) -> list[tuple[str, str | None]]:
        """Egy szöveges fájl (`.md`, `.canvas`, `.base`) linkjei [(nyers cél, feloldott út | None)] a bájtjaiból — a
        `feloldas.hivatkozasok` szabályával (jegyzetlinkek, canvas, a Bases-kifejezések hivatkozásai)."""
        low = rp.lower()
        if low.endswith(".md"):
            celok = feloldas.jegyzet_celok(feloldas.szoveg(b)) + bazis_hivatkozas.celok(rp, b)
        elif low.endswith(".canvas"):
            j, _ = feloldas.canvas_bajtbol(b)
            celok = feloldas.canvas_celok(j) if j is not None else []
        elif low.endswith(".base"):
            celok = bazis_hivatkozas.celok(rp, b)
        else:
            return []
        return [(c, fo.resolve(c, rp)[0]) for c in celok]

    def _elotte(self, root: Path, t: _Terv) -> tuple[dict, dict]:
        """A próba „előtte” állapota (T106), a fájlok újraolvasása nélkül a terven kívül: a fájlhalmaz csak NEVEKBŐL (bejárás
        tartalom-olvasás nélkül); a tervezett (módosuló, mozgó) és a Bases-forrás fájlok linkjei a lemezről (a zárak alatt,
        stabilak); a terven kívüli forrásoké az indexből (nyers cél, a feloldás az új fájlhalmazon). → (elotte, kontextus)."""
        fajlok = [rp for rp, _ in feloldas.bejaras(root)]
        fo = Feloldo(fajlok)
        bazis = {f["ut"] for f in self.ix.bazis_forrasok()}
        tervezett = set(t.fajlok) | {u for u in t.lek if u.lower().endswith(MOZGATHATO)} | bazis
        linkek: dict[str, list] = {}
        hash_: dict[str, str] = {}
        for rp in sorted(tervezett):
            try:
                b = self.v.lemezen(rp).read_bytes()
            except FileNotFoundError:           # C33: a terv óta eltűnt (külső törlés) — változás, nem lemezhiba
                raise Hiba(409, f"{rp} közben eltűnt — nézd át újra a tervet.", valtozott=True) from None
            hash_[rp] = _sha1(b)
            linkek[rp] = self._fajl_linkjei(rp, b, fo)
        allapot = self.ix.fajl_allapot()
        idx: dict[str, list[str]] = {}
        for r in self.ix.link_sorok():
            if r["forras"] not in tervezett and r["forras"] in allapot:
                idx.setdefault(r["forras"], []).append(r["cel_nyers"] or "")
        for forras, celok in idx.items():
            linkek[forras] = [(c, fo.resolve(c, forras)[0]) for c in celok]
            hash_[forras] = allapot[forras][0]
        return {"files": fajlok, "linkek": linkek, "hash": hash_}, {"tervezett": tervezett, "allapot": allapot, "idx": idx}

    def _utana(self, root: Path, t: _Terv, elotte: dict, ctx: dict) -> dict:
        """A próba „utána” állapota (T106): a fájlhalmaz újra csak nevekből; a tervezett és Bases-forrás fájlokat az új helyükön
        újraolvassa; a terven kívüli forrást NEM (a link-listája az indexből, az új fájlhalmazon feloldva) — és ha közben
        módosult (mtime/méret eltér), kimarad a próbából (az „előtte”-ből is): egy egyidejű külső mentés nem okozhat
        500-as visszaállítást."""
        fajlok = [rp for rp, _ in feloldas.bejaras(root)]
        fo = Feloldo(fajlok)
        linkek: dict[str, list] = {}
        hash_: dict[str, str] = {}
        for rp in sorted(ctx["tervezett"]):
            s2 = t.lek.get(rp, rp)
            b = self.v.lemezen(s2).read_bytes()
            hash_[s2] = _sha1(b)
            linkek[s2] = self._fajl_linkjei(s2, b, fo)
        for forras, celok in ctx["idx"].items():
            h, mtime_ns, meret, lemez = ctx["allapot"][forras]
            try:
                st = os.stat(root / lemez)
            except OSError:
                st = None
            if st is None or st.st_mtime_ns != mtime_ns or st.st_size != meret:
                elotte["linkek"].pop(forras, None)
                elotte["hash"].pop(forras, None)
                continue
            linkek[forras] = [(c, fo.resolve(c, forras)[0]) for c in celok]
            hash_[forras] = h
        return {"files": fajlok, "linkek": linkek, "hash": hash_}

    def _vegrehajt_zarolva(self, repo: snapshot.Repo, t: _Terv, t0: float) -> dict:
        root = self.v.root
        repo.commit("kézi változások az átnevezés előtt", {"Mos-Forras": "kezi"})
        for f in t.fajlok.values():             # a terv óta senki nem írta át őket
            try:
                b = self.v.lemezen(f.ut).read_bytes()
            except FileNotFoundError:           # C33 (T175): a közben eltűnt fájl változás, nem lemezhiba
                raise Hiba(409, f"{f.ut} közben eltűnt — nézd át újra a tervet.", valtozott=True) from None
            if _sha1(b) != f.alap:
                raise Hiba(409, f"{f.ut} közben megváltozott — nézd át újra a tervet.", valtozott=True)
        p_regi = self.v.lemezen(t.regi)
        elotte, ctx = self._elotte(root, t)
        lemez_regi = {rp: os.path.relpath(self.v.lemezen(rp), root) for rp in t.lek}   # a mozgó fájlok lemezútja
        vart_hash = {rp: _sha1(f.uj) for rp, f in t.fajlok.items()}
        cel_mappa = self.v._abs(os.path.dirname(t.uj)) if os.path.dirname(t.uj) else root
        # ha csak a mappa változik, a lemezen álló (gyakran NFD) név marad
        nev = p_regi.name if nfc(p_regi.name) == os.path.basename(t.uj) else os.path.basename(t.uj)
        p_uj = cel_mappa / nev
        if p_uj.exists() and not os.path.samefile(p_regi, p_uj):
            raise Hiba(409, f"Már van ilyen nevű fájl vagy mappa: {t.uj}", valtozott=True)
        lepesek: list[tuple] = []
        kor = frame.new_id(ELOTAG)
        self._naplo_ir(t, kor, p_regi, p_uj)
        osszeomlas.pont("atnevezes.naplo_kesz")
        self.publish({"tipus": "vault_atnevezes", "allapot": "kezd", "regi": t.regi, "uj": t.uj, "mappa": t.mappa})
        try:
            for rp, f in t.fajlok.items():
                p = self.v.lemezen(rp)
                self._ir(p, f.uj, regi=f.regi)      # a csere előtti újraellenőrzéssel (külső író, pl. Obsidian ellen)
                lepesek.append(("irva", p, f.regi, f.uj))
                osszeomlas.pont("atnevezes.fajl_irva")
            try:
                _mozgat(p_regi, p_uj)    # T092 (L12): fájl vagy egy egész mappa, egyetlen atomi, KIZÁRÓ lemezlépés
            except FileExistsError:
                raise Hiba(409, f"Közben létrejött a cél: {t.uj} — az átnevezés visszaállt, nézd át újra a tervet.",
                           valtozott=True) from None
            lepesek.append(("atnevezve", p_regi, p_uj))
            osszeomlas.pont("atnevezes.atnevezve")
            utana = self._utana(root, t, elotte, ctx)
            hibak = self._proba(elotte, utana, t, vart_hash)
            if hibak:
                kulso = self._kulso_fajlvaltozas(elotte, utana, t)
                if kulso:   # C33: a próba közben külső író változtatta a fájlhalmazt — ütközés, nem programhiba
                    raise Hiba(409, "A vault közben változott (egy másik program fájlt hozott létre vagy törölt) — az átnevezés "
                                    "visszaállt, próbáld újra.", valtozott=True, proba_hibak=hibak, kulso=kulso[:10])
                raise Hiba(500, "A referencia-próba hibát talált, az átnevezés visszaállt.", proba_hibak=hibak)
            utak = sorted({*t.fajlok, *t.lek, *t.lek.values()})
            trailerek = {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: t.uj, "Mos-Forras": FORRAS}
            regi_lemezen = os.path.relpath(p_regi, root)
            # a lemezen NFD-n álló régi nevek (a git NFC-t őriz): a visszavonás ezekkel adja vissza a neveket
            lemezen = [regi_lemezen] if regi_lemezen != t.regi else []
            if t.mappa:
                lemezen += [r for rp, r in sorted(lemez_regi.items()) if r != rp]
            if lemezen:
                trailerek[snapshot.TRAILER_DISK] = json.dumps(lemezen, ensure_ascii=False, separators=(",", ":"))
            uzenet = (f"mappa átnevezve: {t.regi} → {t.uj} ({len(t.lek)} jegyzet)" if t.mappa
                      else f"jegyzet átnevezve: {t.regi} → {t.uj}")
            osszeomlas.pont("atnevezes.commit_elott")
            # CX-003: média nem kerülhet gitbe; üres mappának nincs git-útja.
            ignoralt = set()
            if utak:
                vizsgalat = repo.git("--no-literal-pathspecs", "check-ignore", "--no-index", "-z", "--stdin",
                                     input="\0".join(utak) + "\0", check=False)
                if vizsgalat.returncode not in (0, 1):
                    raise RuntimeError("A média kizárásának ellenőrzése nem sikerült: " + vizsgalat.stderr[-300:])
                ignoralt = set(filter(None, vizsgalat.stdout.split("\0")))
            kovetett = [u for u in utak if u not in ignoralt]
            visszavonhato = bool(t.lek) and not ignoralt and t.regi.casefold() != t.uj.casefold()
            if not visszavonhato:
                trailerek["Mos-Mozgatas"] = "kezzel-visszamozgathato"
            # a gitignore-olt (média) leképezés nem kerülhet a pontos cserébe: a git add bukna rajta (CX-003)
            pontos = ({r: u for r, u in t.lek.items() if r not in ignoralt and u not in ignoralt}
                      if t.regi.casefold() == t.uj.casefold() else None)
            sha = repo.commit_machine(uzenet, trailerek, kovetett, pontos_atnevezesek=pontos) if kovetett else None
            # A git nélküli művelet is tartósan befejezett legyen a napló eltávolítása előtt.
            naplo_ut = _naplo_mappa(self.cfg) / "terv.json"
            befejezett = json.loads(naplo_ut.read_text())
            befejezett["kesz"] = True
            _atomi_ir(naplo_ut, json.dumps(befejezett, ensure_ascii=False).encode())
            osszeomlas.pont("atnevezes.commit_utan")
            _naplo_torol(self.cfg)
        except BaseException as e:
            if self._visszaallit(lepesek):
                _naplo_torol(self.cfg)      # különben a napló marad: a következő induláskor ismét próbálkozik
            self.publish({"tipus": "vault_atnevezes", "allapot": "vissza", "regi": t.regi, "uj": t.uj, "mappa": t.mappa})
            if isinstance(e, Hiba):
                raise
            if isinstance(e, FileNotFoundError):    # C33 (T175): egy érintett fájl közben eltűnt (külső törlés) — változás, 409
                raise Hiba(409, "Egy érintett fájl közben eltűnt — az átnevezés visszaállt, nézd át újra a tervet.",
                           valtozott=True) from e
            if isinstance(e, OSError):               # C33 (T175): lemezhiba magyarul, abszolút út nélkül
                kod, adat = vaultio.lemez_hiba(e, self.cfg.path("vault"))
                raise Hiba(kod, "Az átnevezés megszakadt, visszaállt. " + adat.pop("hiba"), **adat) from e
            if isinstance(e, Exception):
                raise Hiba(500, f"Az átnevezés megszakadt, visszaállt: {type(e).__name__}: {e}") from e
            raise
        modositott = sorted(t.fajlok)
        uj_nevek = [t.lek.get(m, m) for m in modositott]
        self.publish({"tipus": "vault_atnevezes", "allapot": "kesz", "regi": t.regi, "uj": t.uj, "mappa": t.mappa,
                      "modositott": uj_nevek, "pillanat": sha})
        raw = [self.ix.lemez_ut(m) for m in modositott if m not in t.lek]
        if t.mappa:
            regi_ut, uj_ut = os.path.relpath(p_regi, root), os.path.relpath(p_uj, root)
            raw += [regi_ut, uj_ut]
            for r in lemez_regi.values():
                raw += [r, uj_ut + r[len(regi_ut):]]
        else:
            raw += [os.path.relpath(p_regi, root), os.path.relpath(p_uj, root)]
        self.ix.frissit(raw)
        return {"ok": True, "regi": t.regi, "uj": t.uj, "mappa": t.mappa, "modositott": uj_nevek, "mozgo_fajlok": len(t.lek),
                "pillanat": sha, "visszavonhato": visszavonhato, "proba": {"fajlok": len(utana["files"]), "linkek": sum(len(v) for v in utana["linkek"].values()),
                                           "feloldott_uj": t.uj_feloldott},
                "ms": round((time.perf_counter() - t0) * 1000)}

    def _visszaallit(self, lepesek: list[tuple]) -> bool:
        """A végrehajtott lépések visszacsinálása fordított sorrendben, a memóriában tartott eredeti bájtokból — de CSAK a
        saját bájtjainkat (T015): ha egy fájl tartalma már nem az általunk írt (közben más módosította), nem tapossuk
        rá; az átnevezés visszafordítása kizáró (nem ír rá egy közben létrejött régi útra). → True, ha minden lépés
        visszaállt; különben a szándéknapló marad (a következő induláskor `helyreallit` próbálkozik)."""
        ok = True
        for l in reversed(lepesek):
            try:
                if l[0] == "atnevezve":
                    _mozgat(l[2], l[1])
                else:
                    p, regi, uj = l[1], l[2], (l[3] if len(l) > 3 else None)
                    most = p.read_bytes()
                    if most == regi:
                        continue
                    if uj is not None and most != uj:
                        ok = False          # közben más írta át: a bájtjait nem írjuk felül
                        continue
                    self._ir(p, regi)
            except OSError:
                ok = False
        return ok


def utvonalak(r) -> None:
    """Az átnevezés végpontjai az útvonal-regiszterben (C11a)."""
    r.post("/api/vault/atnevezes/terv", lambda k: k.app.atnevezes.terv(k.torzs().get("ut"), k.torzs().get("uj")))
    r.post("/api/vault/atnevezes", lambda k: k.app.atnevezes.vegrehajt(
        k.torzs().get("ut"), k.torzs().get("uj"), k.torzs().get("terv_hash")))
