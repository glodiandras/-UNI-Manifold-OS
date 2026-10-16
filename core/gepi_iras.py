"""A gépi írás egyetlen útja (C16.5, audit M11): minden gép — lánc, AI-funkció, automatika — ezen át ír a vaultba.

Egy kérés = egy **tétel**: fájlműveletek listája (`uj`: új fájl; `csere`: teljes csere alap-hash-sel; `beszuras`:
szöveg egy megnevezett szakasz alá; `mozgat`: egy füzetfotó a figyelt mappából a vaultba, C21), a forrás (`Mos-Forras`), a kör és a
tétel azonosítója.

**`mozgat` (C21)**: `{"tipus": "mozgat", "forras": <abszolút út>, "ut": "<[fuzet] cel_mappa>/<név>", "sha256": …}`. A forrás csak a
figyelt mappák (`core/fuzet.py`: a `{fuzet_bejovo}` és a `[fuzet] mappak`) alól jöhet, vaulton kívülről, kép kiterjesztéssel; a
cél csak a `[fuzet] cel_mappa` alatt állhat, és nem létezhet (nem írunk felül: ütközésnél a hívó új nevet ad); a bájtok sha256-ja
egyezik. A fotó a szöveges írások ELŐTT mozog (azonos köteten atomi `rename_excl`), a szándéknaplóba kerül, hiba esetén visszaköltözik;
a commit után a bináris napló (L19) `fuzet` rekordot kap a commit sha-jával, a forrásbeli névvel és az azonossággal — a visszavonás
így a fotót a forrásmappájába viszi vissza. A vaultban már álló média nem mozog (47(e)); próbában a fotó a klónba MÁSOLÓDIK. A lépés-folyamat
közvetlenül soha nem ír a vaultba: a `core/gepi_kliens.py`-n át ezt a szolgáltatást hívja (`POST /api/gepi-iras`).

**`mozgat`, videó-profil (C20b)**: ugyanez a művelet videó-kiterjesztésű céllal (`MEDIA_TIPUS` `video/*`): a forrás csak a videólánc
stagingje (`[utak] staging`) alól jöhet (engedélylistás gyökér, feloldott úton, vaulton kívül), a cél csak a `[video] vault_mappa` alatt.
A videó **APFS-klónként** kerül a vaultba (`tartos.klon_excl`: azonnali, 0 többlethely; mérve 2 GiB-on 7 ms, 0 MiB), a staging példánya
(a letöltő igazsága) érintetlen marad. Előbb a `{tmp}` alá klónozunk, onnan `rename_excl` a vaultba: a félbeszakadt klón soha nem a vaultban
áll. A tétel hibájánál a még nem rögzített saját klón a `{tmp}`-be kerül vissza, és ott törlődik (a staging eredetije megvan). A bináris napló
`media` rekordja `klon: true` és a staging-beli út (`forras_ut`) mellett; a **visszavonás nem töröl**: ha a staging eredetije bájtra azonos
és megvan, a vaultbeli klón a `[utak] video_visszavont` alá kerül indokkal, különben (az eredeti hiányzik) a staging helyére költözik vissza.

**`behoz` (az `.apkg` médiája; 55(b), 83. döntés javaslata)**: `{"tipus": "behoz", "forras": <abszolút út>, "ut": "<csatolmány-mappa>/<név>",
"sha256": …}` — egy ÚJ bináris az importáló saját kicsomagoló mappájából (`behoz_gyoker`: `{tmp}/apkg-media`, vaulton kívül) a vaultba.
Szűkebb a `mozgat`-nál, és nem tágítja azt (a `mozgat` a figyelt fotómappák és a videó-staging útja marad, 68(b)): csak a `mos-kartya`
forrás kérheti; a kiterjesztés a `mediatipus.APKG_MEDIA` fehérlistáján áll; a cél mappája a tétel valamelyik jegyzetének
csatolmány-mappája (`core/csatolmany.py`, az `.obsidian/app.json` `attachmentFolderPath`-ja, 80(c)); a fájlt a tétel egy szöveges írása
`![[név]]`-ként beágyazza (bekötetlen média nem kerül a vaultba, I40); a bájtok sha256-ja egyezik; a cél nem létezhet (kis-nagybetűtől és
normalizálástól függetlenül), **felülírás nincs** (`rename_excl`). Élesben a fájl a kicsomagoló mappából a vaultba KÖLTÖZIK (a saját
`{tmp}` fájlunk), próbában a klónba MÁSOLÓDIK. A commit után a bináris napló tételenként egy `apkg` rekordot kap (az utak, a sha256 és a méret);
a visszavonás a fájlokat nem törli, hanem az `[utak] apkg_visszavont` alá költözteti (`<kör>/`, `INDOK.md`), és csak a bájtra azonosat.

A csővezeték: alaki ellenőrzés → útvonalankénti zárak (a szerkesztő mentése ugyanarra a fájlra a tétel végéig vár) →
kör-zár (korlátos várakozással) → kézi commit (L14) → a lemez olvasása és minden ellenőrzés (út, séma, Status-tilalom,
alap-hash, nyitott mentetlen dokumentum) → szándéknapló (`{run}/gepi-iras/`) → atomi írások, a saját írás
bejelentésével az indexnek → a tétel EGY gépi commitja útlistával (L13) → WS `vault_iras` fájlonként és egy
`gepi_iras {kor, tetel, utak, sha, forras, …}`.

**Pillanatkép nélkül gép nem ír** (a szerkesztő mentésével ellentétben, 18. döntés): ha nincs élő tároló vagy a git
hibázik, semmi nem íródik — a gépi írás csak így vonható vissza egy kattintással (D1). Bármi hiba az írások közben:
visszaállítás a memóriában tartott eredeti bájtokból, commit nincs. Ha a folyamat az írások és a commit között hal
meg, a napló alapján a következő induláskor `helyreallit` állít vissza.

Próbamód (`proba: true`; D9, L12, L21): ugyanez a kód egy APFS-klónon (`{tmp}/proba/<kör>-proba/`), a kör `-proba`
utótagot kap; az éles vault, az éles tároló és az index érintetlen. Kalibrálatlan modell kimenete csak így írható.
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import binaris_naplo, config, csatolmany, frame, fuzet, mediatipus, osszeomlas, snapshot, tartos, vaultio
from .tartos import fsync_ir as _fsync_ir, fsync_mappa as _fsync_mappa
from .index import elemzo
from .index.feloldas import canvas_bajtbol
from .index.maszk import FM_RE, mask_code
from .modell import kalibracio
from .modell.halmaz import Verziok
from .tulajdonsagok import Tulajdonsagok
from . import utkapu
from .utvonalak import HttpError
from .vaultio import Conflict, Invalid, NotFound, nfc, sha1

NAPLO = "gepi-iras"                      # a szándéknapló mappája a {run} alatt
MAX_MUVELET = 50
MAX_BEHOZ = 2000                         # a `behoz` műveletek egy tételben (az `.apkg` egy paklijának médiája): a szöveges írások mellett
BEHOZ_FORRASOK = ("mos-kartya",)         # a `behoz` csak az `.apkg`-import forrásával kérhető
ZAR_VARAKOZAS_MP = 10.0                  # ennyit vár a kör-zárra, utána 409 `foglalt`
# a `mozgat` célmappái, ha a config nem adja meg (`[video] vault_mappa`, `[fuzet] cel_mappa`; os.toml ugyanezeket írja)
VIDEO_MAPPA_ALAP = "ATTCHMNTS - Videos"
FUZET_MAPPA_ALAP = "ATTCHMNTS - photos"
# a gépi írás forrása (`Mos-Forras`, L09) mindig `mos-<lánc>` (C29.8, T135): így a `kezi`, `pult`, `pult-…` (a felhasználó munkájának
# forrásai) és minden idegen alak kizárt, és a tracker a „gépi funkciót” egyértelműen felismeri
_FORRAS = re.compile(r"mos-[a-z0-9-]{1,36}")
_GAZDAI_ELOTAG = {"SZERK", "ATNEV", "VISSZA"}        # a szerkesztő, az átnevezés és a visszaállítás kör-előtagjai
_FELADAT = re.compile(r"F-[0-9]{8}-[0-9]{6}-[0-9]+")
_SZAKASZ = re.compile(r"(#{1,6})[ \t]+(.*)")


def behoz_gyoker(cfg) -> Path:
    """A `behoz` művelet egyetlen megengedett forrás-gyökere: az importáló saját kicsomagoló mappája a `{tmp}` alatt."""
    return cfg.path("tmp") / "apkg-media"


def _video_e(ut: str) -> bool:
    """C20b: a `mozgat` videó-profilja (a `MEDIA_TIPUS` `video/*` kiterjesztései)."""
    return (mediatipus.tipus(ut) or "").startswith("video/")


# ---------------------------------------------------------------- beszúrás megnevezett szakasz alá

def _fejezetek(lf: str) -> list[tuple[int, int, int, str]]:
    """(sor eleje, sor vége, szint, szöveg) a törzs fejezeteire — a core kódmaszkjával (kódblokkban álló `## X`
    nem fejezet), a frontmatter nélkül; a szöveg az eredetiből (a soron belüli kód a címben megmarad)."""
    maszk = mask_code(lf)
    fm = FM_RE.match(lf)
    ki = []
    for m in elemzo._FEJEZET.finditer(maszk, fm.end() if fm else 0):
        e = elemzo._FEJEZET.match(lf[m.start():m.end()])
        szoveg = re.sub(r"[ \t]+#+$", "", e.group(2)).strip() if e else ""
        if szoveg:
            ki.append((m.start(), m.end(), len(m.group(1)), szoveg))
    return ki


def szakasz_beszur(txt: str, szakasz: str, szoveg: str, hova: str = "vege", letrehoz: bool = False) -> str:
    """A `szoveg` beszúrása a `szakasz` nevű fejezet alá; → az új szöveg (változatlan, ha a `szoveg` már ott áll).

    A `szakasz` a fejezet szövege, opcionálisan `#`-ekkel a szint is (`## Gyakorlás`). A szakasz a következő azonos
    vagy magasabb szintű fejezetig tart. `vege`: a szakasz utolsó nem üres sora után, új sorban; `eleje`: a címsor
    alá. Több azonos nevű szakasz: 409; hiányzó: `letrehoz` esetén a fájl végére kerül a `## szakasz` (vagy a megadott
    szint) és alá a szöveg, különben 404. A sorvég a fájlé marad (CRLF-es fájl CRLF)."""
    if hova not in ("vege", "eleje"):
        raise Invalid("a `hova` vege vagy eleje lehet")
    crlf = "\r\n" in txt
    if crlf and "\n" in txt.replace("\r\n", ""):
        raise Invalid("a fájlban vegyes sorvégek állnak: gépi beszúrás nem írható bele bájthűen")
    lf = txt.replace("\r\n", "\n") if crlf else txt
    uj = szoveg.replace("\r\n", "\n").strip("\n")
    if not uj.strip():
        raise Invalid("üres a beszúrandó szöveg")
    cel, szint = szakasz.strip(), None
    m = _SZAKASZ.fullmatch(cel)
    if m:
        szint, cel = len(m.group(1)), re.sub(r"[ \t]+#+$", "", m.group(2)).strip()
    if not cel or "\n" in cel:
        raise Invalid("a `szakasz` egy fejezet szövege legyen")
    fejek = _fejezetek(lf)
    talalat = [i for i, f in enumerate(fejek) if nfc(f[3]) == nfc(cel) and (szint is None or f[2] == szint)]
    if len(talalat) > 1:
        raise HttpError(409, f"több „{cel}” nevű szakasz van, a beszúrás helye nem egyértelmű", tobbertelmu=True)
    if not talalat:
        if not letrehoz:
            raise NotFound(f"nincs „{cel}” nevű szakasz")
        alap = lf.rstrip("\n")
        ki = alap + ("\n\n" if alap else "") + f"{'#' * (szint or 2)} {cel}\n{uj}\n"
    else:
        i = talalat[0]
        _, sor_vege, sz, _ = fejek[i]
        vege = next((f[0] for f in fejek[i + 1:] if f[2] <= sz), len(lf))
        torzs = lf[sor_vege:vege]
        if f"\n{uj}\n" in f"{torzs}\n":
            return txt
        if hova == "eleje":
            uj_torzs = "\n" + uj + (torzs if torzs else "\n")
        else:
            tart = torzs.rstrip()
            farok = torzs[len(tart):]
            uj_torzs = tart + "\n" + uj + (farok if farok else "\n")
        ki = lf[:sor_vege] + uj_torzs + lf[vege:]
    return ki.replace("\n", "\r\n") if crlf else ki


# ---------------------------------------------------------------- a kérés

@dataclass
class _Keres:
    kor: str
    tetel: str
    forras: str
    uzenet: str
    proba: bool
    muveletek: list[dict]
    dontes: str | None = None
    feladat: str | None = None
    modell: dict | None = None
    hash: str = ""                  # a kérés tartalmának ujjlenyomata (`Mos-Keres` trailer): az ismétlés felismerésére
    esemeny: dict | None = None     # C20b: a sikeres, nem próba írás után a core tracker-eseménye (`ESEMENYEK` fehérlista)


# C20b: a lépés-folyamat a trackert nem éri el (a pos.sqlite egyetlen írója a core, a lépés-kapu default-deny), ezért a lánc
# záró eseményét a tételével együtt küldi: a core a commit UTÁN, csak élesben (nem próbában, nem ismétlésnél) rögzíti.
# Forrás → az engedett esemény és az adatának kulcsai (a tracker `ADAT_SEMA`-ja a végső szűrő).
ESEMENYEK = {"mos-video": {"integralt_video": ("video_s", "jegyzet_db", "kotes")}}


def _esemeny(d: dict, forras: str) -> dict | None:
    e = d.get("esemeny")
    if e is None:
        return None
    engedett = ESEMENYEK.get(forras, {})
    if not isinstance(e, dict) or e.get("tipus") not in engedett:
        raise Invalid(f"a `{forras}` forrás tételéhez ilyen tracker-esemény nem küldhető")
    ut = e.get("ut")
    adat = e.get("adat")
    if not isinstance(ut, str) or not ut or len(ut) > 1024 or not isinstance(adat, dict) or set(adat) - set(engedett[e["tipus"]]):
        raise Invalid("az `esemeny` alakja: {tipus, ut, adat} a forrás engedett kulcsaival")
    return {"tipus": e["tipus"], "ut": vaultio.norm_path(ut), "adat": dict(adat)}


@dataclass
class _Fajl:
    ut: str                         # vault-relatív, NFC
    p: Path                         # a lemezen álló út
    regi: bytes | None              # None: új fájl
    uj: bytes
    mappak: list[Path] = field(default_factory=list)     # az új fájlhoz létrehozandó mappák, kívülről befelé


@dataclass
class _Mozgas:
    ut: str                         # vault-relatív cél, NFC
    p: Path                         # a cél a lemezen
    forras: Path                    # a figyelt mappában álló forrás (feloldott út)
    sha256: str
    mappak: list[Path] = field(default_factory=list)
    klon: bool = False              # C20b: a videó-profil APFS-klónt tesz a vaultba (a staging példánya marad)
    behoz: bool = False             # 83: az `.apkg` médiája a kicsomagoló mappából (élesben költözik, próbában másolódik)


def _egysoros(d: dict, kulcs: str, max_hossz: int, kotelezo: bool = True) -> str | None:
    v = d.get(kulcs)
    if v is None and not kotelezo:
        return None
    if not isinstance(v, str) or not v.strip() or len(v) > max_hossz or re.search(r"[\r\n\x00]", v):
        raise Invalid(f"a `{kulcs}` egysoros, legfeljebb {max_hossz} karakteres szöveg legyen")
    return v.strip()


def _keres(d: dict) -> _Keres:
    """A kérés alaki ellenőrzése (400): itt még semmi nem olvas a lemezről."""
    kor = _egysoros(d, "kor", 80)
    if not frame.KOR_MINTA.fullmatch(kor) or kor.split("-", 1)[0] in _GAZDAI_ELOTAG:
        raise Invalid(f"érvénytelen kör-azonosító: {kor} (alak: ELŐTAG-ÉÉÉÉHHNN-ÓÓPPMM)")
    forras = _egysoros(d, "forras", 40)
    if not _FORRAS.fullmatch(forras):
        raise Invalid(f"érvénytelen forrás (Mos-Forras): {forras} (alak: mos-<lánc>, kisbetű, szám, kötőjel, legfeljebb 40 karakter)")
    tetel = _egysoros(d, "tetel", 500)
    proba = d.get("proba", False)
    if not isinstance(proba, bool):
        raise Invalid("a `proba` igaz vagy hamis lehet")
    feladat = _egysoros(d, "feladat", 40, kotelezo=False)
    if feladat is not None and not _FELADAT.fullmatch(feladat):
        raise Invalid(f"érvénytelen feladat-azonosító: {feladat}")
    # D9 (C29.8, T043; a 28(g) pontosítása): a `modell` kulcs KÖTELEZŐ — AI-funkció kimenetére `{feladat, modell[, proba]}`, determinisztikus
    # írásra kifejezetten `null`. A kapu így nem a kérés önkéntes mezőjén múlik: aki nem mond semmit, az nem ír.
    if "modell" not in d:
        raise Invalid("a `modell` kulcs kötelező: AI-funkció kimenetére {feladat, modell}, determinisztikus írásra kifejezetten null")
    modell = d["modell"]
    if modell is not None and not (isinstance(modell, dict) and all(
            isinstance(modell.get(k), str) and modell[k].strip() for k in ("feladat", "modell"))
            and isinstance(modell.get("proba", False), bool)):
        raise Invalid("a `modell` alakja: {feladat, modell[, proba]} vagy null")
    muveletek = d.get("muveletek")
    if not isinstance(muveletek, list) or not 1 <= len(muveletek) <= MAX_MUVELET + MAX_BEHOZ or \
            not all(isinstance(m, dict) for m in muveletek):
        raise Invalid(f"a `muveletek` 1–{MAX_MUVELET} elemű lista legyen (plusz legfeljebb {MAX_BEHOZ} `behoz`)")
    muveletek, utak = [dict(m) for m in muveletek], set()
    behoz_db = sum(1 for m in muveletek if m.get("tipus") == "behoz")
    if behoz_db > MAX_BEHOZ or len(muveletek) - behoz_db > MAX_MUVELET:
        raise Invalid(f"a `muveletek` legfeljebb {MAX_MUVELET} szöveges/mozgató és {MAX_BEHOZ} `behoz` műveletet tartalmazhat")
    if behoz_db and forras not in BEHOZ_FORRASOK:
        raise Invalid(f"a `behoz` csak az `.apkg`-import forrásával ({', '.join(BEHOZ_FORRASOK)}) kérhető, nem: {forras}")
    for m in muveletek:
        if m.get("tipus") not in ("uj", "csere", "beszuras", "mozgat", "behoz"):
            raise Invalid("a művelet `tipus`-a uj, csere, beszuras, mozgat vagy behoz lehet")
        m["ut"] = vaultio.norm_path(m.get("ut"))
        if m["tipus"] == "behoz":
            if mediatipus.kiterjesztes(m["ut"]) not in mediatipus.APKG_MEDIA:
                raise Invalid(f"a `behoz` csak a fehérlistás médiát viszi a vaultba ({' '.join(mediatipus.APKG_MEDIA)}): {m['ut']}")
            f = m.get("forras")
            if not isinstance(f, str) or not os.path.isabs(f) or "\x00" in f or len(f) > 1024:
                raise Invalid("a `behoz` forrása abszolút út legyen")
            if not isinstance(m.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", m["sha256"]):
                raise Invalid("a `behoz` kéri a forrás sha256-ját (64 hex jegy)")
        elif m["tipus"] == "mozgat":
            if not m["ut"].lower().endswith(fuzet.KEP_KITERJESZTESEK) and not _video_e(m["ut"]):
                raise Invalid(f"a `mozgat` csak füzetfotót (kép) vagy a videólánc videóját viszi a vaultba: {m['ut']}")
            f = m.get("forras")
            if not isinstance(f, str) or not os.path.isabs(f) or "\x00" in f or len(f) > 1024:
                raise Invalid("a `mozgat` forrása abszolút út legyen")
            if not isinstance(m.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", m["sha256"]):
                raise Invalid("a `mozgat` kéri a forrás sha256-ját (64 hex jegy)")
        elif not m["ut"].lower().endswith(vaultio.SZOVEGES):
            raise Invalid(f"gép csak a pillanatképben követett szöveges fájlt írhat: {m['ut']}")
        kulcs = m["ut"].lower()
        if kulcs in utak:
            raise Invalid(f"egy út egy tételben egyszer szerepelhet: {m['ut']}")
        utak.add(kulcs)
    uzenet = _egysoros(d, "uzenet", 200, kotelezo=False) or f"gépi írás: {tetel}"[:200]
    dontes = _egysoros(d, "dontes", 200, kotelezo=False)
    ujjlenyomat = hashlib.sha1(json.dumps({"muveletek": muveletek, "forras": forras, "uzenet": uzenet, "dontes": dontes},
                                          sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return _Keres(kor, tetel, forras, uzenet, proba, muveletek, dontes, feladat, modell, ujjlenyomat, _esemeny(d, forras))


# ---------------------------------------------------------------- szándéknapló és helyreállítás

def _naplo_mappa(cfg) -> Path:
    return cfg.path("run") / NAPLO


def _naplo_torol(cfg) -> None:
    shutil.rmtree(_naplo_mappa(cfg), ignore_errors=True)


def _commit_obj(repo: snapshot.Repo, kor: str, tetel: str, feladat: str | None) -> snapshot.Commit | None:
    """A (kör, tétel, feladat) gépi commitja, ha van (az ismétlés és a helyreállítás kérdése). A feladat azért része
    a kulcsnak, mert a régi kör-azonosító másodperc-felbontású volt: két feladat azonos másodpercben induló köre egybeesne."""
    for c in repo.kor_commitok(kor):        # a teljes történetben, a trailer pontos összevetésével (T094)
        if c.trailers.get(snapshot.TRAILER_ITEM) == tetel and c.trailers.get(snapshot.TRAILER_TASK) == feladat:
            return c
    return None


def _commit(repo: snapshot.Repo, kor: str, tetel: str, feladat: str | None) -> str | None:
    c = _commit_obj(repo, kor, tetel, feladat)
    return c.sha if c else None


def _mappak_torol(mappak: list[Path]) -> int:
    """Az üresen maradt új mappák törlése belülről kifelé; ami nem üres, az marad. → a törölt mappák száma."""
    db = 0
    for d in reversed(mappak):
        try:
            os.rmdir(d)
            db += 1
        except OSError:
            pass
    return db


def _klon_vissza_tmp(p: Path, tmp_mappa: Path) -> None:
    """C20b: a vaultba tett, még nem rögzített saját videó-klón kivétele: `rename_excl` a `{tmp}` alá, és ott törlés (a saját `var/tmp`
    fájl; a staging eredetije érintetlen). A vaultban semmi nem törlődik."""
    tmp_mappa.mkdir(parents=True, exist_ok=True)
    tmp = tartos.tmp_ut(tmp_mappa / p.name)
    tartos.rename_excl(p, tmp)
    os.remove(tmp)


def helyreallit(cfg) -> list[str]:
    """Induláskor (a kör-zár alatt, az index előtt): ha egy gépi írás naplója megmaradt, a folyamat az írások és a
    commit között halt meg. Ha a tétel commitja megvan, csak a napló törlődik; különben minden fájl az eredeti
    bájtjait kapja vissza (az új fájl és az üresen maradt új mappája eltűnik) — de csak ott, ahol a lemezen a terv
    szerinti új változat áll: amit közben más írt át, azt nem bántja, és a napló `gepi-iras-megtartva-<idő>` néven
    megmarad. → a felhasználónak szóló üzenetek."""
    d = _naplo_mappa(cfg)
    if not d.exists():
        return []
    if not frame.vault_letezik(cfg):        # T002: nem létező vaulton nincs mit visszaállítani; a napló a valódi vaultra vár
        return []
    tj = d / "terv.json"
    if not tj.is_file():                    # a napló az első írás előtt készül: terv nélkül a vault érintetlen
        _naplo_torol(cfg)
        return []
    n = json.loads(tj.read_text(encoding="utf-8"))
    repo = snapshot.repos(cfg).get("vault")
    if repo is not None and repo.live() and _commit(repo, n["kor"], n["tetel"], n.get("feladat")):
        _naplo_torol(cfg)
        return []
    root = cfg.path("vault")
    visszaallt = 0                          # amit ténylegesen visszaírtunk/töröltünk: az üzenet csak erről állíthat valamit
    utkozo = []
    for f in n["fajlok"]:
        p = root / f["lemez"]
        try:
            most = p.read_bytes()
        except FileNotFoundError:
            most = None
        eredeti = (d / "eredeti" / f["eredeti"]).read_bytes()
        if f["uj_fajl"]:                    # a naplóban a tervezett tartalom áll
            if most is not None and eredeti.startswith(most):
                os.remove(p)                # a saját, be nem fejezett (akár félig megírt) írásunk
                visszaallt += 1
            elif most is not None:
                utkozo.append(f["ut"])
            visszaallt += _mappak_torol([root / m for m in f["mappak"]])
            continue
        if most == eredeti:
            continue
        if most is not None and sha1(most) == f["uj_sha1"]:
            vaultio.atomi_csere(p, eredeti)
            visszaallt += 1
        else:
            utkozo.append(f["ut"])
    for mz in n.get("mozgasok", []):        # C21: a vaultba vitt fotó vissza a forrásmappájába (csak a mi bájtazonos fájlunk)
        p, src = root / mz["lemez"], Path(mz["forras"])
        if not os.path.lexists(p):
            continue
        if mz.get("behoz") and not mz.get("masolat") and binaris_naplo.kivonat(p) == mz["sha256"]:
            # 83: a saját `.apkg`-médiánk: vissza a kicsomagoló mappába, ha az megvan; különben az archívumba (nem töröl)
            if not os.path.lexists(src) and src.parent.is_dir():
                binaris_naplo._mozgat(p, src, letrehoz=False)
            else:
                binaris_naplo.archival(p, cfg.path("apkg_visszavont"), n["kor"], binaris_naplo.APKG_INDOK)
            visszaallt += 1
        elif mz.get("klon") and binaris_naplo.kivonat(p) == mz["sha256"]:      # C20b: a saját klónunk
            if os.path.isfile(src) and binaris_naplo.kivonat(src) == mz["sha256"]:
                _klon_vissza_tmp(p, cfg.path("tmp"))
            elif not os.path.lexists(src):
                binaris_naplo._mozgat(p, src, letrehoz=False)      # az eredeti közben eltűnt: a klón tér vissza a helyére
            else:
                utkozo.append(mz["ut"])
                continue
            visszaallt += 1
        elif not mz.get("masolat") and not mz.get("klon") and not os.path.lexists(src) and \
                binaris_naplo.kivonat(p) == mz["sha256"]:
            binaris_naplo._mozgat(p, src, letrehoz=False)
            visszaallt += 1
        else:
            utkozo.append(mz["ut"])
    if repo is not None and repo.live():
        repo.index_frissit()                # a visszaírt fájlok stat-adata ne zajoljon a git-indexben (T101)
    elso = f"Egy gépi írás megszakadt ({n['kor']} · {n['tetel']}; a core az írások közben leállt). "
    if visszaallt:
        uzenet = elso + "A vault visszaállt az írás előtti állapotra; a tétel újra futtatható."
    elif utkozo:
        uzenet = elso + "Semmit nem tudtam visszaállítani."
    else:
        uzenet = elso + "A vault még érintetlen volt: nem kellett visszaállítani semmit; a tétel újra futtatható."
    if utkozo:
        megtartva = d.with_name(f"{NAPLO}-megtartva-{time.strftime('%Y%m%d-%H%M%S')}")
        os.rename(d, megtartva)
        uzenet += (f" Ezeket a fájlokat közben más is átírta, ezért nem írtam vissza: {', '.join(utkozo[:10])}. "
                   f"Az eredeti bájtjaik itt vannak: {megtartva}.")
    else:
        _naplo_torol(cfg)
    return [uzenet]


# ---------------------------------------------------------------- a szolgáltatás

KLON_SZOLGALTATAS_MAX = 16      # ennyi próbakör klón-szolgáltatása marad a memóriában (a régebbi a következő tételnél újraépül)


class _Korlatos(collections.OrderedDict):
    """Legfeljebb `maximum` elemű szótár, a legrégebben használt esik ki (F7, 2026-10-14). A próbakör klón-szolgáltatása olcsón
    újraépül (a klón a lemezen marad, a `_klon` újrahasznosítja), ezért a kiesett befejezett kör csak memóriát szabadít fel."""

    def __init__(self, maximum: int):
        super().__init__()
        self.maximum = maximum

    def __getitem__(self, kulcs):
        ertek = super().__getitem__(kulcs)
        self.move_to_end(kulcs)
        return ertek

    def __setitem__(self, kulcs, ertek):
        super().__setitem__(kulcs, ertek)
        self.move_to_end(kulcs)
        while len(self) > self.maximum:
            self.popitem(last=False)


class GepiIras:
    """`vault`: a `vaultio.Vault` (út-ellenőrzés, lemeznevek, tároló); `tul`: a séma (`Tulajdonsagok`);
    `publish`: esemény a WS-nek — a `vault_iras`-ra az `App` az indexet is frissíti; `sajat(ut, hash)`: a saját írás
    bejelentése az indexnek a csere ELŐTT; `mentetlen()`: a felület által jelentett mentetlen utak (NFC)."""

    def __init__(self, cfg, vault: vaultio.Vault, tul: Tulajdonsagok, publish=lambda e, **k: None,
                 sajat=lambda rp, h: None, mentetlen=lambda: set(), varakozas_mp: float = ZAR_VARAKOZAS_MP,
                 proba: bool = False, jelzo=lambda forras: None, esemeny_jelzo=lambda e: None):
        self.cfg, self.v, self.tul = cfg, vault, tul
        self.publish, self.sajat, self.mentetlen = publish, sajat, mentetlen
        self.jelzo = jelzo                  # C27: a tracker számlálja a funkciónkénti gépi írást (nem próbát)
        self.esemeny_jelzo = esemeny_jelzo  # C20b: a tétel tracker-eseménye (`ESEMENYEK`), a commit után, élesben
        self.varakozas_mp = varakozas_mp
        self.proba = proba
        self._klonok: dict[str, GepiIras] = _Korlatos(KLON_SZOLGALTATAS_MAX)    # F7: a próbakörök szolgáltatásai nem gyűlnek
        self._klon_zar = threading.Lock()

    # -------------------------------------------------- belépés

    def ir(self, d: dict) -> dict:
        k = _keres(d)
        self._modell_feladat(k)
        for m in k.muveletek:       # T018: a lemezen álló (kanonikus) út — a git pathspec, a zárak és a mentetlen-halmaz is ezt látja
            m["ut"] = self.v.kanonikus(m["ut"])
        if k.proba:
            if not k.kor.endswith("-proba"):
                k.kor += "-proba"
            return self._klon(k.kor)._vegrehajt(k)
        if "proba" in k.kor:
            raise Invalid(f"a `-proba` kör élesben nem írhat: {k.kor}")
        self._d9(k)
        return self._vegrehajt(k)

    def _modell_feladat(self, k: _Keres) -> None:
        """A `modell.feladat` a router feladatainak (`[router] feladatok`) eleme legyen, mindkét ágon (éles és próba): a kalibráció
        feladatonként él, egy ismeretlen feladatnévre sosem lehet kalibrált modell (T043)."""
        if k.modell is None:
            return
        feladatok = list(self.cfg.section("router").get("feladatok", []))
        if k.modell["feladat"] not in feladatok:
            raise Invalid(f"a(z) „{k.modell['feladat']}” nem router-feladat ({', '.join(feladatok)}): a `modell.feladat` a "
                          "`[router] feladatok` eleme lehet")

    def _d9(self, k: _Keres) -> None:
        """D9: kalibrálatlan modell kimenete élesben nem írható, csak próbában. A worker `proba: true` jelzésű válasza (a modell
        kifejezett kérésre futott, nem a router választotta) szintén csak próbában írható, akkor is, ha a pár kalibrált."""
        if k.modell is None:
            return
        if k.modell.get("proba"):
            raise HttpError(400, f"a(z) {k.modell['modell']} modell próbaként futott (kifejezett kérésre, nem a router választotta): "
                                 "a kimenete csak próbában (`proba: true`, a klónon) írható", kalibralatlan=True)
        t = kalibracio.megnyit(self.cfg)
        try:
            # csak az aranyhalmaz aktuális verzióján kalibrált sor (mint a routernél): az elavult verziójú nem írhat élesben
            kalibralt = {s["modell"] for s in t.kalibralt_sorrend(k.modell["feladat"], Verziok(self.cfg.path("modulok")))}
        finally:
            t.close()
        if k.modell["modell"] not in kalibralt:
            raise HttpError(400, f"a(z) {k.modell['modell']} modell a(z) „{k.modell['feladat']}” feladatra nincs "
                                 "kalibrálva: a kimenete csak próbában (`proba: true`, a klónon) írható",
                            kalibralatlan=True)

    def _klon(self, kor: str) -> "GepiIras":
        """A próbakör klónja és a rá mutató szolgáltatás (a kör első tételénél készül, utána ugyanaz)."""
        with self._klon_zar:
            if kor not in self._klonok:
                d = self.cfg.path("tmp") / "proba" / kor
                vault, git = d / self.cfg.path("vault").name, d / "vault.git"
                if not (vault.is_dir() and (git / "HEAD").is_file()):
                    if snapshot.repos(self.cfg)["vault"].live() is False:
                        raise HttpError(503, "Nincs élő pillanatkép-tároló: próbaklón sem készíthető.", pillanat_hiba=True)
                    # a régi (`[vault] proba_klon_max_nap`) gépi próbaklónok előbb: egy-egy a vault teljes APFS-klónja
                    frame.proba_klon_takaritas(self.cfg, kiveve=[self.cfg.path("tmp") / "proba" / k for k in self._klonok])
                    try:
                        frame.trial_clone(self.cfg, d)
                        frame.proba_jelol(d, kor)        # a doctor látja, a takarítás csak jelölt klónt töröl
                    except (RuntimeError, OSError) as e:
                        raise HttpError(503, f"A próbaklón nem készült el: {e}") from e
                utak = self.cfg.data.get("utak", {})
                env = {"HOME": self.cfg.table["home"],
                       **{f"MOS_{n.upper()}": v for n, v in self.cfg.table.items() if n in utak},
                       "MOS_VAULT": str(vault), "MOS_VAULT_GIT": str(git), "MOS_RUN": str(d / "run"),
                       "MOS_YTDLP_GIT": str(d / "ytdlp.git")}       # a klónban más tároló nem él
                kcfg = config.Config(self.cfg.root, self.cfg.data, env, self.cfg.source)
                self._klonok[kor] = GepiIras(kcfg, vaultio.Vault(kcfg), self.tul, publish=self.publish,
                                             varakozas_mp=self.varakozas_mp, proba=True)
            return self._klonok[kor]

    # -------------------------------------------------- végrehajtás

    def _vegrehajt(self, k: _Keres) -> dict:
        repo = self.v.repo()
        if repo is None:
            raise HttpError(503, "Nincs élő pillanatkép-tároló: pillanatkép nélkül gép nem ír a vaultba.",
                            pillanat_hiba=True)
        hatarido = time.monotonic() + self.varakozas_mp
        zarak = [vaultio._ut_zar(m["ut"]) for m in sorted(k.muveletek, key=lambda m: nfc(m["ut"]).lower())]
        while True:
            try:
                with contextlib.ExitStack() as verem:
                    for z in zarak:         # a szerkesztő mentése ugyanarra a fájlra a tétel végéig vár
                        verem.enter_context(z)
                    return self._zarban(repo, k)
            except frame.Busy as e:
                if time.monotonic() >= hatarido:
                    raise HttpError(409, str(e), foglalt=True) from e
            time.sleep(0.05)

    def _regi_naplo(self) -> None:
        """T016: egy megmaradt szándéknapló (az előző gépi írás megszakadt, vagy a visszaállítása nem sikerült) a kör-zár
        alatt előbb helyreáll vagy `-megtartva-<idő>` néven félrekerül — soha nem törlődik némán (a félkész gépi tartalom
        különben a következő kézi commitba kerülne, L13). Ha a napló nem oldható fel, az új írás 409-et kap."""
        d = _naplo_mappa(self.cfg)
        if not d.exists():
            return
        try:
            for u in helyreallit(self.cfg):
                print(f"[gépi írás] {u}", file=sys.stderr, flush=True)
        except (OSError, ValueError, KeyError, snapshot.SnapshotError) as e:
            raise HttpError(409, f"Egy megszakadt gépi írás naplója áll ({d}), és nem sikerült feldolgozni: {e}. "
                                 "Addig új gépi írás nem indulhat.", naplo=True) from e
        if d.exists():
            raise HttpError(409, f"Egy megszakadt gépi írás naplója áll ({d}); addig új gépi írás nem indulhat.", naplo=True)

    def _zarban(self, repo: snapshot.Repo, k: _Keres) -> dict:
        with frame.run_lock(self.cfg, wait=False):      # a kör-zár alatt (Busy → a hívó újrapróbál / 409)
            self._regi_naplo()
        lepesek: list[tuple] = []
        naplo = False
        fajlok: list[_Fajl] = []
        mozgasok: list[_Mozgas] = []
        trailerek = {}
        if k.dontes:
            trailerek["Mos-Dontes"] = k.dontes
        if k.feladat:
            trailerek[snapshot.TRAILER_TASK] = k.feladat
        trailerek["Mos-Keres"] = k.hash          # T095: a más tartalmú ismétlést a következő hívás felismeri
        try:
            with frame.snapshot_frame(self.cfg, k.uzenet, k.tetel, k.forras, wait=False, kor=k.kor,
                                      trailerek=trailerek) as e:
                e["utak"] = []
                mar = _commit_obj(repo, k.kor, k.tetel, k.feladat)
                if mar:                     # az elveszett válasz utáni újraküldés nem ír kétszer
                    regi_hash = mar.trailers.get("Mos-Keres")       # (a régi commitoknak nincs: azok egyezőnek számítanak)
                    if regi_hash and regi_hash != k.hash:
                        raise HttpError(409, f"a(z) {k.kor} · {k.tetel} tétel már lefutott, de MÁS tartalommal: ugyanezen a "
                                             "kör- és tétel-azonosítón más írás nem ismételhető (új tétel-azonosító kell)",
                                        utkozes=True, ismetles_eltero=True)
                    return self._valasz(k, mar.sha, repo.changed_files(mar.sha), {}, ismetles=True)
                terv = self._terv(k)
                fajlok = [f for f in terv if isinstance(f, _Fajl)]
                mozgasok = [f for f in terv if isinstance(f, _Mozgas)]
                if not fajlok:              # a fotó egyedül nem mozog: a beágyazás nélküli kép bekötetlen volna (I40)
                    if mozgasok:
                        raise Invalid("a `mozgat` csak szöveges írással (a beágyazással) együtt kérhető")
                    return self._valasz(k, None, [], {})
                self._naplo_ir(k, fajlok, mozgasok)
                naplo = True
                osszeomlas.pont("gepi.naplo_kesz")
                for mz in mozgasok:
                    self._mozgat(mz, lepesek)
                    osszeomlas.pont("gepi.mozgatva")
                for f in fajlok:
                    self._fajl_ir(f, lepesek)
                    osszeomlas.pont("gepi.egy_fajl_irva")
                e["utak"] = [f.ut for f in fajlok]
                osszeomlas.pont("gepi.commit_elott")
            if not e["sha"]:
                raise snapshot.SnapshotError("a gépi commit üres maradt (a fájl nincs a pillanatképben?)")
        except BaseException as exc:
            if lepesek or naplo:
                if self._visszaallit(lepesek):
                    _naplo_torol(self.cfg)  # különben a napló marad: a következő induláskor ismét próbálkozik
            if isinstance(exc, snapshot.SnapshotError):
                raise HttpError(503, f"A pillanatkép-tároló (git) hibát jelzett, a gépi írás nem történt meg: {exc}",
                                pillanat_hiba=True) from exc
            raise
        osszeomlas.pont("gepi.commit_utan")
        sha = e["sha"]
        if mozgasok and not self.proba:
            self._binaris_rekord(k, sha, mozgasok)
        _naplo_torol(self.cfg)
        hashek = {f.ut: sha1(f.uj) for f in fajlok}
        if not self.proba:
            for ut, h in hashek.items():
                self.publish({"tipus": "vault_iras", "ut": ut, "hash": h, "pillanat": sha})
        self.publish({"tipus": "gepi_iras", "kor": k.kor, "tetel": k.tetel, "utak": list(hashek), "sha": sha,
                      "forras": k.forras, "uzenet": k.uzenet, "feladat": k.feladat, "proba": self.proba})
        if not self.proba:
            self.jelzo(k.forras)
            if k.esemeny is not None:
                try:
                    self.esemeny_jelzo(k.esemeny)
                except Exception as exc:  # noqa: BLE001 — a tracker hibája a rögzített tételt nem viszi el
                    print(f"[gépi írás] FIGYELEM: a tracker-esemény nem íródott ({k.esemeny['tipus']}): {exc}", file=sys.stderr,
                          flush=True)
        return self._valasz(k, sha, list(hashek), hashek)

    def _valasz(self, k: _Keres, sha, utak, hashek, ismetles: bool = False) -> dict:
        ki = {"ok": True, "kor": k.kor, "tetel": k.tetel, "sha": sha, "utak": utak, "hash": hashek,
              "mozgatva": [m["ut"] for m in k.muveletek if m["tipus"] == "mozgat"] if sha else [],
              "behozva": [m["ut"] for m in k.muveletek if m["tipus"] == "behoz"] if sha else [],
              "valtozas": bool(sha) and not ismetles, "ismetles": ismetles, "proba": self.proba}
        if self.proba:
            ki["proba_mappa"] = str(self.cfg.path("vault").parent)
        return ki

    # -------------------------------------------------- a terv: olvasás és ellenőrzés (még semmi nem íródik)

    def _terv(self, k: _Keres) -> list:
        fajlok, nyitott = [], []
        mentetlen = {nfc(u).casefold() for u in self.mentetlen()}       # T018: kis-nagybetűtől független összevetés
        kor_mappak: set[Path] = set()
        for m in k.muveletek:
            f = getattr(self, "_m_" + m["tipus"])(m)
            if f is None:
                continue
            if isinstance(f, _Mozgas):
                f.mappak = [d for d in f.mappak if d not in kor_mappak]
                kor_mappak.update(f.mappak)
                fajlok.append(f)
                continue
            if f.regi is not None and nfc(f.ut).casefold() in mentetlen:
                nyitott.append(f.ut)
            # T019: a tétel KÖZÖS, még nem létező ős-mappáját az első művelet birtokolja (egyszer jön létre, egyszer kerül
            # a naplóba és a visszaállításba) — különben a második `mkdir` `FileExistsError`-ral (500) elhasalt
            f.mappak = [d for d in f.mappak if d not in kor_mappak]
            kor_mappak.update(f.mappak)
            fajlok.append(f)
        if nyitott:
            raise HttpError(409, "a dokumentum nyitva van, mentetlen változással — a gép nem ír bele: "
                                 + ", ".join(nyitott), nyitott=True, utak=nyitott)
        self._behoz_kotes(fajlok)
        return fajlok

    def _behoz_kotes(self, terv: list) -> None:
        """83: a `behoz` célja a tétel egy jegyzetének csatolmány-mappája (80(c)), és a fájlt a tétel egy szöveges írása beágyazza
        (`![[név]]` vagy `![[név|…]]`): bekötetlen média nem kerül a vaultba (I40)."""
        behozok = [f for f in terv if isinstance(f, _Mozgas) and f.behoz]
        if not behozok:
            return
        jegyzetek = [f for f in terv if isinstance(f, _Fajl) and f.ut.lower().endswith(".md")]
        engedett = set()
        for f in jegyzetek:
            try:
                engedett.add(nfc(csatolmany.mappa(self.v.root, f.ut)).casefold())
            except Invalid as e:
                raise Invalid(f"a csatolmány-mappa nem használható: {e}") from None
        szovegek = [f.uj.decode("utf-8", errors="replace") for f in jegyzetek]
        for b in behozok:
            mappa_, nev = b.ut.rpartition("/")[0], b.ut.rpartition("/")[2]
            if nfc(mappa_).casefold() not in engedett:
                raise Invalid(f"a `behoz` célja a tétel jegyzetének csatolmány-mappája (attachmentFolderPath) lehet, nem: {b.ut}")
            if not any(f"![[{nev}]]" in s or f"![[{nev}|" in s for s in szovegek):
                raise Invalid(f"a `behoz` fájlját a tétel egy jegyzete `![[{nev}]]`-ként be kell ágyazza (bekötetlen média nem kerül a vaultba)")

    def _szoveg(self, m: dict, kulcs: str) -> str:
        v = m.get(kulcs)
        if not isinstance(v, str):
            raise Invalid(f"hiányzik a művelet `{kulcs}` mezője ({m['ut']})")
        return v

    def _bajt(self, rp: str, szoveg: str) -> bytes:
        b = szoveg.encode("utf-8")
        if len(b) > vaultio.MAX_SZOVEG:
            raise Invalid(f"túl nagy fájl: {rp}")
        if rp.lower().endswith(".canvas"):
            _, hiba = canvas_bajtbol(b)
            if hiba:
                raise Invalid(f"a canvas nem érvényes JSON Canvas ({rp}): {hiba}")
        return b

    def _meglevo(self, m: dict) -> tuple[str, Path, bytes]:
        rp = m["ut"]
        p = self.v._abs(rp)
        if not p.is_file():
            raise NotFound(f"nincs ilyen fájl: {rp}")
        p = self.v.lemezen(rp)
        regi = p.read_bytes()
        alap = m.get("alap")
        if alap is not None and (not isinstance(alap, str) or sha1(regi) != alap):
            raise Conflict(f"a fájl a gép olvasása óta megváltozott: {rp}", ut=rp, hash=sha1(regi))
        return rp, p, regi

    def _fm(self, rp: str, szoveg: str) -> dict:
        m = FM_RE.match(szoveg)
        return self.tul.elemez(rp, m.group(0) if m else None)

    @staticmethod
    def _status(e: dict):
        """A jegyzet Status-mezői (a kulcs kis-nagybetűjétől függetlenül: a `status` kijátszás lett volna, T127), `(kulcs, érték)`
        párokban; `None`, ha nincs nem üres Status. A változás (törlés, átnevezés, érték) mind eltér."""
        vk = tuple((t["kulcs"], t["ertek"]) for t in e["tulajdonsagok"]
                   if t["kulcs"].casefold() == "status" and t["ertek"] not in ("", [], None))
        return vk or None

    def _sema_tiltas(self, rp: str) -> None:
        if rp.lower().endswith(".md") and self.tul.sema.osztaly(rp)["sema_nelkul"]:
            raise Invalid(f"séma nélküli (ügynök-hordozó) fájlba gép nem ír: {rp}")

    def _m_uj(self, m: dict) -> _Fajl:
        rp = m["ut"]
        self._sema_tiltas(rp)
        szoveg = self._szoveg(m, "tartalom")
        p = self.v._abs(rp)
        reszek = rp.split("/")
        mappak, d = [], self.v.root
        for i, r in enumerate(reszek[:-1]):
            d = d / r
            if not d.is_dir():
                if d.exists() or vaultio._TILTOTT_NEV.search(r):
                    raise Invalid(f"érvénytelen mappa az új fájl útjában: {'/'.join(reszek[:i + 1])}")
                mappak.append(d)
        torzs = reszek[-1].rsplit(".", 1)[0]
        if not torzs.strip() or vaultio._TILTOTT_NEV.search(reszek[-1]) or len(reszek[-1].encode("utf-8")) > 240:
            raise Invalid(f'érvénytelen fájlnév: {reszek[-1]} — tilos benne: \\ / : * ? " < > | # ^ [ ]')
        if not mappak and (os.path.lexists(p) or any(nfc(n).lower() == nfc(reszek[-1]).lower()
                                                     for n in os.listdir(p.parent))):
            raise Conflict(f"már van ilyen nevű fájl: {rp}", ut=rp, letezik=True)
        if rp.lower().endswith(".md"):
            osztaly = m.get("osztaly")
            e = self._fm(rp, szoveg)
            if osztaly != e["osztaly"]:
                raise HttpError(400, f"az új jegyzet sémaosztálya az útja szerint „{e['osztaly']}”, a kérésben "
                                     f"„{osztaly}” áll: új gépi jegyzetfajta csak bejegyzett sémaosztállyal "
                                     "írható (a vault-séma kivételosztályai)", sema=True)
            problemak = [*e["problemak"], *self.tul.h1_problemak(rp, szoveg)]        # a H1-szabály is (L33/L34, T044)
            if problemak:
                raise HttpError(400, f"az új jegyzet sérti a vault sémáját ({rp}): "
                                     + " ".join(x["uzenet"] for x in problemak), sema=True, problemak=problemak)
            if self.tul.sema.status_gazdai and self._status(e) is not None:
                raise HttpError(400, "A Status mezőt csak a felhasználó tölti, gép nem.", sema=True)
        return _Fajl(rp, p, None, self._bajt(rp, szoveg), mappak)

    def _m_csere(self, m: dict) -> _Fajl | None:
        self._sema_tiltas(m["ut"])
        szoveg = self._szoveg(m, "tartalom")
        if not isinstance(m.get("alap"), str) or not m["alap"]:
            raise Invalid("hiányzik az alapváltozat (alap) — vakon nem írunk felül")
        rp, p, regi = self._meglevo(m)
        if b"\r\n" in regi and "\r\n" not in szoveg:
            szoveg = szoveg.replace("\n", "\r\n")
        b = self._bajt(rp, szoveg)
        if b == regi:
            return None
        if rp.lower().endswith(".md"):
            regi_szoveg = regi.decode("utf-8", errors="replace")
            elotte, utana = self._fm(rp, regi_szoveg), self._fm(rp, szoveg)
            # csak az ÚJ sértés akadály: a frontmatteré (a hiányzó kulcsok halmazával, T133) és a H1-szabályé (T044)
            uj_p = self.tul.uj_sertesek([*elotte["problemak"], *self.tul.h1_problemak(rp, regi_szoveg)],
                                        [*utana["problemak"], *self.tul.h1_problemak(rp, szoveg)])
            if uj_p:
                raise HttpError(400, f"a csere sérti a vault sémáját ({rp}): " + " ".join(x["uzenet"] for x in uj_p),
                                sema=True, problemak=uj_p)
            if self.tul.sema.status_gazdai and self._status(elotte) != self._status(utana):
                raise HttpError(400, "A Status mezőt csak a felhasználó tölti és változtatja, gép nem.", sema=True)
        return _Fajl(rp, p, regi, b)

    def _m_mozgat(self, m: dict) -> _Mozgas:
        """C21: egy füzetfotó a figyelt mappából a `[fuzet] cel_mappa` alá; C20b: a videólánc videója a stagingből a `[video] vault_mappa`
        alá, klónként (még semmi nem mozog, csak ellenőrzünk)."""
        rp = m["ut"]
        video = _video_e(rp)
        if video:
            cel_mappa = vaultio.norm_path(str(self.cfg.section("video").get("vault_mappa") or VIDEO_MAPPA_ALAP))
            hiba_hely = f"a videó helye a `{cel_mappa}` mappa, nem: {rp}"
        else:
            cel_mappa = vaultio.norm_path(str(self.cfg.section("fuzet").get("cel_mappa") or FUZET_MAPPA_ALAP))
            hiba_hely = f"a füzetfotó helye a `{cel_mappa}` mappa, nem: {rp}"
        reszek = rp.split("/")
        if "/".join(reszek[:-1]) != cel_mappa:
            raise Invalid(hiba_hely)
        src = Path(m["forras"])
        if os.path.islink(src) or not src.is_file():
            raise NotFound(f"nincs ilyen {'videó a stagingben' if video else 'fotó a figyelt mappában'}: {src}")
        src = Path(os.path.realpath(src))
        if video:
            if not utkapu.alatta(self.cfg.path("staging"), src) or utkapu.alatta(self.v.root, src):
                raise Invalid(f"a `mozgat` videót csak a videólánc stagingje (a vaulton kívül) alól visz a vaultba: {src}")
        elif fuzet.figyelt_alatt(self.cfg, src) is None or utkapu.alatta(self.v.root, src):
            raise Invalid(f"a `mozgat` csak a figyelt mappák (a vaulton kívül) új fotóját viszi a vaultba: {src}")
        if binaris_naplo.kivonat(src) != m["sha256"]:
            raise Conflict(f"a {'videó' if video else 'fotó'} a gép olvasása óta megváltozott: {src.name}", ut=rp)
        if vaultio._TILTOTT_NEV.search(reszek[-1]) or len(reszek[-1].encode("utf-8")) > 240:
            raise Invalid(f"érvénytelen fájlnév: {reszek[-1]}")
        p = self.v._abs(rp)
        mappak = [] if p.parent.is_dir() else [p.parent]
        if p.parent.exists() and not p.parent.is_dir():
            raise Invalid(f"érvénytelen célmappa: {cel_mappa}")
        if os.path.lexists(p) or (p.parent.is_dir() and any(nfc(n).casefold() == nfc(reszek[-1]).casefold()
                                                          for n in os.listdir(p.parent))):
            raise Conflict(f"már van ilyen nevű fájl (nem írunk felül; új név kell): {rp}", ut=rp, letezik=True)
        return _Mozgas(rp, p, src, m["sha256"], mappak, klon=video)

    def _m_behoz(self, m: dict) -> _Mozgas:
        """83: egy új bináris (az `.apkg` médiája) az importáló kicsomagoló mappájából (`behoz_gyoker`) a vaultba — még semmi nem mozog,
        csak ellenőrzünk; a cél-mappa és a beágyazás kötését a `_behoz_kotes` nézi a tétel egészén."""
        rp = m["ut"]
        reszek = rp.split("/")
        if vaultio._TILTOTT_NEV.search(reszek[-1]) or len(reszek[-1].encode("utf-8")) > 240 or \
                not os.path.splitext(reszek[-1])[0].strip():
            raise Invalid(f"érvénytelen fájlnév: {reszek[-1]}")
        if any(vaultio._TILTOTT_NEV.search(r) for r in reszek[:-1]):
            raise Invalid(f"érvénytelen célmappa: {'/'.join(reszek[:-1])}")
        src = Path(m["forras"])
        if os.path.islink(src) or not src.is_file():
            raise NotFound(f"nincs ilyen kicsomagolt fájl: {src}")
        src = Path(os.path.realpath(src))
        if not utkapu.alatta(behoz_gyoker(self.cfg), src) or utkapu.alatta(self.v.root, src):
            raise Invalid(f"a `behoz` csak az importáló saját kicsomagoló mappájából (a `{{tmp}}` alól) visz a vaultba: {src}")
        if binaris_naplo.kivonat(src) != m["sha256"]:
            raise Conflict(f"a kicsomagolt fájl az ellenőrzés óta megváltozott: {src.name}", ut=rp)
        p = self.v._abs(rp)
        mappak, d = [], p.parent
        while d != self.v.root and not d.is_dir():
            if os.path.lexists(d):
                raise Invalid(f"érvénytelen célmappa: {os.path.relpath(d, self.v.root)}")
            mappak.insert(0, d)
            d = d.parent
        if os.path.lexists(p) or (p.parent.is_dir() and any(nfc(n).casefold() == nfc(reszek[-1]).casefold()
                                                          for n in os.listdir(p.parent))):
            raise Conflict(f"már van ilyen nevű fájl (nem írunk felül; új név kell): {rp}", ut=rp, letezik=True)
        return _Mozgas(rp, p, src, m["sha256"], mappak, behoz=True)

    def _mozgat(self, mz: _Mozgas, lepesek: list[tuple]) -> None:
        for d in mz.mappak:
            if not d.is_dir():
                os.mkdir(d)
                lepesek.append(("mappa", d))
        if mz.behoz:                        # 83: a csatolmány-mappa a tétel jegyzetéé is lehet (annak a `mappak`-ja a naplóban él): a fájl
            hianyzo, d = [], mz.p.parent    # a szöveg ELŐTT költözik, ezért a hiányzó őseit itt hozzuk létre (a visszagörgetés listájába)
            while d != self.v.root and not d.is_dir():
                hianyzo.insert(0, d)
                d = d.parent
            for d in hianyzo:
                os.mkdir(d)
                lepesek.append(("mappa", d))
        if mz.klon:                         # C20b: APFS-klón a {tmp}-be, onnan felülírás nélkül a vaultba (élesben és próbában is)
            tmp_mappa = self.cfg.path("tmp")
            tmp_mappa.mkdir(parents=True, exist_ok=True)
            tmp = tartos.tmp_ut(tmp_mappa / mz.p.name)
            tartos.klon_excl(mz.forras, tmp)
            try:
                tartos.rename_excl(tmp, mz.p)
            except FileExistsError:
                tmp.unlink(missing_ok=True)
                raise Conflict(f"a fájl közben létrejött: {mz.ut}", ut=mz.ut, letezik=True) from None
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
            tartos.fsync_mappa(mz.p.parent)
            lepesek.append(("klonozva", mz.p, tmp_mappa))
            return
        if self.proba:                      # a klónba másolat: a figyelt mappa érintetlen (D9)
            tmp = tartos.tmp_ut(mz.p)
            shutil.copy2(mz.forras, tmp)
            try:
                tartos.rename_excl(tmp, mz.p)
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
            lepesek.append(("masolat", mz.p))
            return
        try:
            binaris_naplo._mozgat(mz.forras, mz.p, letrehoz=False)
        except FileExistsError:
            raise Conflict(f"a fájl közben létrejött: {mz.ut}", ut=mz.ut, letezik=True) from None
        lepesek.append(("mozgatva", mz.forras, mz.p))

    def _binaris_rekord(self, k: _Keres, sha: str, mozgasok: list[_Mozgas]) -> None:
        """A bináris napló (L19) rekordja fotónként: a commit, a forrásmappa (a visszavonás célja), a forrásbeli név és az azonosság.
        A napló hibája a már rögzített tételt nem viszi el: a fotó a vaultban marad, az üzenet a core naplójába megy."""
        behozok = [mz for mz in mozgasok if mz.behoz]
        if behozok:                         # 83: az `.apkg` médiája tételenként egy rekord; a visszavonás az archívumba visz (nem töröl)
            try:
                utak = [mz.ut for mz in behozok]
                rec = binaris_naplo.rekord(sha, k.kor, k.kor, utak, tipus="apkg", **binaris_naplo.azonossag_mezok(self.v.root, utak))
                binaris_naplo.ir(binaris_naplo.naplo_ut(self.cfg), rec)
            except Exception as e:  # noqa: BLE001
                print(f"[gépi írás] FIGYELEM: a bináris napló sora nem íródott ({len(behozok)} `.apkg`-médiafájl): {e}", file=sys.stderr,
                      flush=True)
        for mz in mozgasok:
            if mz.behoz:
                continue
            try:
                if mz.klon:                 # C20b: a videó klónja; a visszavonás a staging eredetijéhez méri (nem töröl)
                    rec = binaris_naplo.rekord(sha, k.kor, str(mz.forras.parent), [mz.ut], tipus="media", forras=str(mz.forras.parent),
                                               klon=True, forras_ut=str(mz.forras), forras_nevek={nfc(mz.ut): mz.forras.name},
                                               sha256=mz.sha256, meret=mz.p.stat().st_size)
                else:
                    rec = binaris_naplo.rekord(sha, k.kor, str(mz.forras.parent), [mz.ut], tipus="fuzet", forras=str(mz.forras.parent),
                                               forras_nevek={nfc(mz.ut): mz.forras.name},
                                               **binaris_naplo.azonossag_mezok(self.v.root, [mz.ut]))
                binaris_naplo.ir(binaris_naplo.naplo_ut(self.cfg), rec)
            except Exception as e:  # noqa: BLE001
                print(f"[gépi írás] FIGYELEM: a bináris napló sora nem íródott ({mz.ut}): {e}", file=sys.stderr, flush=True)

    def _m_beszuras(self, m: dict) -> _Fajl | None:
        if not m["ut"].lower().endswith(".md"):
            raise Invalid("szakasz alá beszúrni csak jegyzetbe (.md) lehet")
        self._sema_tiltas(m["ut"])
        szoveg, szakasz = self._szoveg(m, "szoveg"), self._szoveg(m, "szakasz")
        rp, p, regi = self._meglevo(m)
        try:
            txt = regi.decode("utf-8")
        except UnicodeDecodeError:
            raise Invalid(f"a fájl nem érvényes UTF-8, gép nem ír bele: {rp}") from None
        b = self._bajt(rp, szakasz_beszur(txt, szakasz, szoveg, m.get("hova") or "vege", bool(m.get("letrehoz"))))
        if b == regi:
            return None
        uj_h1 = self.tul.uj_sertesek(self.tul.h1_problemak(rp, txt), self.tul.h1_problemak(rp, b.decode("utf-8")))
        if uj_h1:                       # a beszúrt szöveg (pl. egy `# …` sor) a H1-szabályt nem sértheti új módon (T044)
            raise HttpError(400, f"a beszúrás sérti a vault H1-szabályát ({rp}): " + " ".join(x["uzenet"] for x in uj_h1),
                            sema=True, problemak=uj_h1)
        return _Fajl(rp, p, regi, b)

    # -------------------------------------------------- írás, napló, visszaállítás

    def _naplo_ir(self, k: _Keres, fajlok: list[_Fajl], mozgasok: list[_Mozgas] = ()) -> None:
        """A szándéknapló az első írás előtt: az eredeti bájtok és a terv, fsync-elve; a `terv.json` kerül utoljára
        a helyére (atomi csere), a napló csak vele érvényes."""
        root, d = self.v.root, _naplo_mappa(self.cfg)
        if d.exists():          # a `_regi_naplo` már feldolgozta; ide csak egy versenyhelyzet juthat — némán nem törlünk (T016)
            raise HttpError(409, f"Egy szándéknapló áll ({d}); addig új gépi írás nem indulhat.", naplo=True)
        (d / "eredeti").mkdir(parents=True)
        lista = []
        for i, f in enumerate(fajlok):
            # az új fájlnak a tervezett tartalma megy a naplóba: a félig megírt fájl ebből ismerhető fel
            _fsync_ir(d / "eredeti" / f"{i}.bin", f.uj if f.regi is None else f.regi)
            lista.append({"ut": f.ut, "lemez": os.path.relpath(f.p, root),
                          "eredeti": f"{i}.bin", "uj_fajl": f.regi is None, "uj_sha1": sha1(f.uj),
                          "mappak": [os.path.relpath(m, root) for m in f.mappak]})
        _fsync_mappa(d / "eredeti")
        terv = {"verzio": 1, "kor": k.kor, "tetel": k.tetel, "forras": k.forras, "feladat": k.feladat, "fajlok": lista,
                "ido": time.strftime("%Y-%m-%d %H:%M:%S")}
        if mozgasok:
            terv["mozgasok"] = [{"ut": mz.ut, "lemez": os.path.relpath(mz.p, root), "forras": str(mz.forras), "sha256": mz.sha256,
                                 "masolat": self.proba and not mz.klon, "klon": mz.klon, "behoz": mz.behoz} for mz in mozgasok]
        _fsync_ir(d / "terv.json.tmp", json.dumps(terv, ensure_ascii=False, indent=1).encode("utf-8"))
        os.replace(d / "terv.json.tmp", d / "terv.json")
        _fsync_mappa(d)
        _fsync_mappa(d.parent)

    def _fajl_ir(self, f: _Fajl, lepesek: list[tuple]) -> None:
        h = sha1(f.uj)
        if f.regi is None:
            for d in f.mappak:
                if d.is_dir():              # T019: csak a ténylegesen általunk létrehozott mappa kerül a visszagörgetésbe
                    continue
                os.mkdir(d)
                lepesek.append(("mappa", d))
            self.sajat(f.ut, h)
            # "x": meglévő fájlt nem ír felül. (Nem tmp + `os.link`: a hard linkkel létrehozott fájl későbbi törlésének
            # eseményét az FSEvents EGYÁLTALÁN nem jelenti — nem az „első néven”, ahogy a C16.5 hitte, T100 —, és az index
            # nem venné észre a visszavonást; a `tests/test_forraskod.py` tiltja az `os.link`-et.) A félbeszakadt írást a
            # napló tervezett tartalma azonosítja a helyreállításkor.
            try:
                fh = open(f.p, "xb")
            except FileExistsError:
                raise Conflict(f"a fájl közben létrejött: {f.ut}", ut=f.ut, letezik=True) from None
            lepesek.append(("uj", f.p, f.uj))
            with fh:
                fh.write(f.uj)
                fh.flush()
                tartos.fsync_teljes(fh.fileno())
            return

        def ellenoriz():
            most = f.p.read_bytes()
            if most != f.regi:              # az írás közben is változhatott (Obsidian, szinkron)
                raise Conflict(f"a fájl írás közben megváltozott: {f.ut}", ut=f.ut, hash=sha1(most))
            self.sajat(f.ut, h)
        vaultio.atomi_csere(f.p, f.uj, ellenoriz)
        lepesek.append(("irva", f.p, f.regi))

    def _visszaallit(self, lepesek: list[tuple]) -> bool:
        """A végrehajtott lépések visszacsinálása fordított sorrendben, a memóriában tartott eredetiből."""
        ok = True
        for l in reversed(lepesek):
            try:
                if l[0] == "mappa":
                    os.rmdir(l[1])
                elif l[0] == "mozgatva":    # C21: a fotó vissza a figyelt mappába (felülírás nélkül)
                    binaris_naplo._mozgat(l[2], l[1], letrehoz=False)
                elif l[0] == "masolat":
                    os.remove(l[1])
                elif l[0] == "klonozva":    # C20b: a saját, még nem rögzített klónunk vissza a {tmp}-be, ott törlődik (a staging eredetije áll)
                    _klon_vissza_tmp(l[1], l[2])
                elif l[0] == "uj":
                    if l[2].startswith(l[1].read_bytes()):
                        os.remove(l[1])     # a most létrehozott (akár félig megírt), még nem rögzített fájlunk
                    else:
                        ok = False
                else:
                    vaultio.atomi_csere(l[1], l[2])
            except OSError:
                ok = False
        return ok


def utvonalak(r) -> None:
    """A gépi írás végpontja az útvonal-regiszterben."""
    def ir(k):
        d = k.torzs()
        m = d.get("muveletek") if isinstance(d, dict) else None
        if isinstance(m, list) and any(isinstance(x, dict) and x.get("tipus") == "behoz" for x in m):
            # 83: a `behoz` csak a core saját `.apkg`-importjából (in-process) jöhet, a HTTP-n (lépés-folyamat, felület) nem
            raise Invalid("a `behoz` műveletet csak a core `.apkg`-importja kérheti, a gépi-írás végponton át nem")
        return k.app.gepi.ir(d)
    r.post("/api/gepi-iras", ir)
