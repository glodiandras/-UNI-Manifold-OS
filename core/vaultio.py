"""Vault-fájl olvasása és írása a szerkesztőnek — a legacy pult írási szerződésével (L45–L46).

Írás csak `.md`-re, `.base`-re (C12, adatbázis-nézet) és `.canvas`-ra (C14; csak érvényes JSON Canvas), csak a
vaulton belül, rejtett út nélkül. Soha nem vakon: a kérés a betöltött változat hash-ét hozza (`alap`); ha a
lemezen már más áll, `Conflict` (→ 409), és a fájl érintetlen.
A csere atomi és tartós (`core/tartos.py`): egyedi `.<név>.<véletlen>.manifold-tmp` + `F_FULLFSYNC` + újraellenőrzés +
`os.replace` + a szülőmappa fsync-je, a fájl születési idejét megőrizve; ugyanarra a fájlra egyszerre egy mentés fut
(útvonalankénti zár; M4). A lemezen álló (NFD) név megmarad, a CRLF-es fájl CRLF marad.

Pillanatkép a keret mintájára: egy szerkesztés első mentése (`elso`) előtt a még nem rögzített kézi
változások külön commitba kerülnek, a lezáráskor (`pillanat`) a jegyzet saját gépi commitot kap
(`Mos-Forras: pult-szerkeszto`, visszavonható). Ha egy kör fogja a kör-zárat, vagy vault-író feladat
fut, git-művelet nincs: a mentés az Obsidianhoz hasonlóan pillanatkép nélkül ír, és a változás a
következő gépi commit előtt kézi commitba kerül (`commit_machine`). Ugyanez az ág fut, ha a git hibázik
(elakadt `index.lock`, sérült tároló, hiányzó git; K1): a mentés a git egészségén nem múlhat. A lezáró
mentésnél a fájlírás sikere a válasz, a commit hibája csak figyelmeztetés (`pillanat_hiba` WS-esemény).
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import threading
import time
import unicodedata
import weakref
from pathlib import Path

from . import cpp_teszt, frame, kod_nyelvek, mediatipus, snapshot, tartos, utkapu
from .config import Config
from .hibakod import angol_uzenet
from .index.feloldas import canvas_bajtbol
from .utvonalak import HttpError, kodos, Valasz

MAX_SZOVEG = 8 * 1024 * 1024            # ennél nagyobb szöveget nem töltünk be és nem írunk
TMP_UTOTAG = tartos.TMP_UTOTAG          # az ideiglenes fájl utótagja (a pillanatkép kizárja)
FORRAS = "pult-szerkeszto"              # a szerkesztő commitjainak Mos-Forras trailere (L09)
SZOVEGES = (".md", ".canvas", ".base", ".txt", ".vtt", ".srt", ".json", ".csv", ".yml", ".yaml")   # a gépi írás kapuja is (gepi_iras)
# F10: a kód-munkafelület forrásfájljai — az engedélyezett kiterjesztések EGYETLEN forrása a nyelvprofil-tábla
# (`core/kod_nyelvek.py`: .cpp/.cc/.cxx, .c, .py, .js/.mjs/.cjs, .ts/.mts/.cts, .java, .go, .rs, .swift). A C36a-ban csak a `.cpp` volt
# szerkeszthető; a lista bővítése nem nyit új írási utat: a forrás ugyanazon a mentési úton megy (atomikus csere, alap-hash/CAS,
# pillanatkép, soremelés-megőrzés, rejtett szegmens tiltása), a gépi írás kapuja (`SZOVEGES`) pedig NEM bővül: gép forrást nem ír.
# Kivétel: ami a pillanatképből bináris-ként kizárt (`mediatipus.BINARIS_KITERJESZTESEK`: így a TypeScript `.mts` aliasa, mert az
# egyben AVCHD-videókonténer), az nem szerkeszthető forrás — pillanatkép és visszavonás nélküli írás az adatbiztonságot sértené.
NEM_SZERKESZTHETO_FORRAS = tuple(k for k in kod_nyelvek.kiterjesztesek() if k in mediatipus.BINARIS_KITERJESZTESEK)
FORRAS_KITERJESZTESEK = tuple(k for k in kod_nyelvek.kiterjesztesek() if k not in NEM_SZERKESZTHETO_FORRAS)
OLVASHATO = SZOVEGES + FORRAS_KITERJESZTESEK   # C36a, F10: a forrás a szerkesztőnek olvasható
IRHATO = (".md", ".base", ".canvas") + FORRAS_KITERJESZTESEK   # a többi szöveges fájl csak olvasható (C12, C14, C36a, F10)
UJ_BASE = "views:\n  - type: table\n    name: Táblázat\n"   # az új `.base` tartalma (= `bazis.modell.UJ_SZOVEG`)
UJ_CANVAS = "{}"                        # az új `.canvas` tartalma (az Obsidian új canvasának alakja, C14)

_FELIRAT = {"md": "jegyzet", "base": "adatbázis-nézet", "canvas": "canvas", "cpp": "C++ forrás"}   # a commit-üzenet a fájltípus szerint


def _felirat(rp: str) -> str:
    """A commit-üzenet fájltípus-felirata: a jegyzet-típusoké, a forrásfájlé a nyelvprofil neve (`Python forrás`)."""
    kit = _tipus(rp)
    if kit in _FELIRAT:
        return _FELIRAT[kit]
    p = kod_nyelvek.nyelv_ut(rp)
    return f"{p.nev} forrás" if p else "forrás"


def _tipus(rp: str) -> str:
    return rp.rsplit(".", 1)[-1].lower()


# A média-URL-en kiszolgálható fájlok (kiterjesztés → Content-Type): a lista egyetlen helye a `mediatipus` (C20a, T142).
MEDIA_TIPUS = mediatipus.MEDIA_TIPUS

# Az Obsidian a fájlnévben ezeket nem engedi, vagy a linket törik (`#`, `^`, `[`, `]`, `|`).
_TILTOTT_NEV = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
# A vezérlőkarakteres út a commit-metaadatot hamisítaná (L13, T017): minden vezérlőkarakter tilos a `norm_path`-ban, a
# TABULÁTOR kivételével (nem sortörő sehol, és az M1 „különleges nevek” esete: a tabulátoros fájlnév írható marad).
_UT_VEZERLO = re.compile("[\x00-\x08\x0a-\x1f\x7f\x85\u2028\u2029]")
_H1_ELOTAG = re.compile(r"^\d+[A-Z]? - ")               # H1 = a név a sorszám-előtag nélkül (L46)


class Invalid(ValueError):
    """Érvénytelen kérés (400)."""


class NotFound(Invalid):
    """Nincs ilyen fájl (404)."""


class NemElerheto(Invalid):
    """A vault nem érhető el (503, `lemez_hiba`): a kötet leválasztva, kihúzva, vagy a mappa átnevezve (C33, T175). `kod`:
    `vault_nem_elerheto`, vagy `workspace_csere` (F3: a vault helyén egy másik munkatér áll — azonos nevű, cserélt lemez)."""

    def __init__(self, uzenet: str = "", *, kod: str = "vault_nem_elerheto"):
        super().__init__(uzenet)
        self.kod = kod


# C33 (T175): az I/O-hiba (errno) → HTTP-kód és magyar üzenet. Az adat ilyenkor biztonságban van (a tmp + csere nem ír félig),
# a válasz nem visz abszolút utat (a kivétel `filename`-je kimarad): a felület az „A mentés nem sikerült” értesítésbe teszi.
_LEMEZ_HIBAK = {
    "ENOSPC": (507, "A lemez megtelt: a fájl nem íródott ki (a régi változat érintetlen). Szabadíts fel helyet, a mentés újrapróbálja."),
    "EDQUOT": (507, "A lemezkvóta elfogyott: a fájl nem íródott ki (a régi változat érintetlen)."),
    "EFBIG": (507, "A fájl túl nagy ehhez a lemezhez vagy korláthoz: nem íródott ki (a régi változat érintetlen)."),
    "EACCES": (503, "A lemez vagy a mappa nem írható (hozzáférés megtagadva): a fájl nem íródott ki."),
    "EPERM": (503, "A művelet nem engedélyezett ezen a fájlon vagy mappán: a fájl nem íródott ki."),
    "EROFS": (503, "A kötet csak olvasható: a fájl nem íródott ki."),
    "EIO": (503, "Lemezhiba (I/O): a művelet nem sikerült. Ellenőrizd a kötetet."),
    "ENXIO": (503, "A lemez nem érhető el (leválasztva?): a művelet nem sikerült."),
    "ENODEV": (503, "A lemez nem érhető el (leválasztva?): a művelet nem sikerült."),
}


def lemez_hiba(e: OSError, vault: Path | None = None) -> tuple[int, dict]:
    """An English disk error with a stable code, status and no absolute paths."""
    import errno as _errno
    nev = _errno.errorcode.get(e.errno or 0, "")
    if vault is not None and not vault.is_dir():
        kod, param = "lemez.nem_elerheto", {"vault": vault.name}
        return 503, {"hiba": angol_uzenet(kod, param), "kod": kod, "param": param,
                     "lemez_hiba": True, "errno": nev or None, "vault_elerheto": False}
    statusz = _LEMEZ_HIBAK.get(nev, (503, ""))[0]
    kod = f"lemez.{nev.lower()}" if nev in _LEMEZ_HIBAK else "lemez.hiba"
    param = {"errno": nev or type(e).__name__}
    return statusz, {"hiba": angol_uzenet(kod, param), "kod": kod, "param": param,
                    "lemez_hiba": True, "errno": nev or None}


class Conflict(RuntimeError):
    """A fájl a betöltés óta megváltozott (409) — a felhasználó dönt: újratölt, vagy a sajátját menti."""

    def __init__(self, message: str, **data):
        super().__init__(message)
        self.data = data


class _KorZarFoglalt(Exception):
    """Belső jel: a kör-zár foglalt, és a hívónak (`felulir`) pillanatkép nélkül nem szabad írnia — a `write` újrapróbál."""


# Gyenge értékű szótár (F7, 2026-10-14): a zár csak addig él, amíg valaki tartja (a `with` vagy a hívó listája); a korábbi
# sima szótár minden valaha írt útra megtartotta a zárat. A kizárás változatlan: amíg egy hívó a zárat tartja (vagy várja),
# ugyanazt az objektumot kapja mindenki, a senki által nem hivatkozott zárat pedig senki nem tarthatja.
_UT_ZARAK: "weakref.WeakValueDictionary[str, threading.Lock]" = weakref.WeakValueDictionary()
_UT_ZARAK_ZAR = threading.Lock()


def _ut_zar(rp: str) -> threading.Lock:
    """Útvonalankénti zár a folyamatban (M4): ugyanarra a fájlra egyszerre egy írás fut (kulcs: NFC + kisbetű,
    mert az APFS kis-nagybetűre és normalizálásra nem érzékeny). A hívó a visszakapott zárat a használat végéig tartsa
    hivatkozásban (a `with _ut_zar(…)` ezt teszi)."""
    with _UT_ZARAK_ZAR:
        return _UT_ZARAK.setdefault(nfc(rp).lower(), threading.Lock())


def tmp_ut(p: Path) -> Path:
    """Az ideiglenes fájl: rejtett, egyedi, és a neve 255 bájt alatt marad (L9) — a `*.manifold-tmp` kizárás illik rá."""
    return tartos.tmp_ut(p)


def atomi_csere(p: Path, b: bytes, ellenoriz=None) -> None:
    """Atomi, tartós csere (L45, T026): egyedi tmp-fájl + `F_FULLFSYNC`, az `ellenoriz()` a csere előtt (kivételére a
    tmp törlődik, a fájl érintetlen), utána `os.replace`, a mappa fsync-je, a születési idő megőrzésével (T025)."""
    tartos.atomi_ir(p, b, ellenoriz)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def mark(st: os.stat_result) -> str:
    """A fájl változásjele (módosítás ns + méret) — a felület ezzel figyeli a nyitott jegyzetet."""
    return f"{st.st_mtime_ns}-{st.st_size}"


def norm_path(rp) -> str:
    """A felületről jött vault-relatív út: NFC, `/` elválasztó. Tilos az üres, a `.`/`..` és a rejtett
    (ponttal kezdődő) szegmens — így a `.obsidian`, a `.trash` és az ideiglenes fájlok sem érhetők el."""
    if not isinstance(rp, str) or not rp.strip():
        raise kodos(Invalid("hiányzó út"), "vault.ut_hianyzik")
    rp = nfc(rp).replace("\\", "/").strip().strip("/")
    reszek = rp.split("/")
    if _UT_VEZERLO.search(rp) or any(r in ("", ".", "..") or r.startswith(".") for r in reszek):
        raise kodos(Invalid(f"érvénytelen út: {rp!r}"), "vault.ut_ervenytelen", ut=rp)      # a vezérlőkarakteres (újsoros, U+2028, …) út a commit-metaadatot hamisítaná (L13)
    return rp


# Abszolút (vagy felhasználó-könyvtáras, meghajtó-betűs) mappamegadás: nem vault-relatív
_ABSZOLUT_MAPPA = re.compile(r"[/\\~]|[A-Za-z]:")


class Vault:
    """A vault fájl-API-ja. `busy`: igaz, ha vault-író feladat fut (akkor git-művelet nincs);
    `publish`: eseményküldő (`events.Bus.publish`); `sajat(ut, hash)`: a csere ELŐTT jelzi a saját írást
    (az index így a figyelő eseményét nem nézi külső szerkesztésnek, C06)."""

    KOR_ZAR_VARAKOZAS_MP = 2.0       # az ütközés-felülírás (`felulir`) ennyit vár a kör-zárra, utána 423 (C29.7b, T116)

    def __init__(self, cfg: Config, busy=lambda: False, publish=lambda e, **k: None, sajat=lambda rp, h: None):
        self.cfg = cfg
        self.kor_zar_varakozas_mp = float(cfg.section("vault").get("kor_zar_varakozas_mp", self.KOR_ZAR_VARAKOZAS_MP))
        self.busy = busy
        self.publish = publish
        self.sajat = sajat
        self._elerheto: bool | None = None
        self._elerheto_zar = threading.Lock()

    @property
    def root(self) -> Path:
        v = self.cfg.path("vault")
        if not (v / ".obsidian").is_dir():
            self._elerheto_jelez(False)
            raise NemElerheto(f"a vault nem érhető el ({v.name}): a kötet le van választva, vagy a mappa átnevezve")
        if self._elerheto is not True and not self._munkater_azonos():
            self._elerheto_jelez(False)
            raise NemElerheto(f"a vault helyén egy másik munkatér áll ({v.name}): a megnyitott munkatér nem érhető el",
                              kod="workspace_csere")
        self._elerheto_jelez(True)
        return v

    def _munkater_azonos(self) -> bool:
        """Termékben (F3, §3.4) a nem elérhető → elérhető váltáskor (és az első használatkor): a `workspace.toml` azonosítója
        a megnyitotté-e. Egy azonos nevű, cserélt lemez így „nem elérhető” marad. Hordozható elrendezésben mindig igaz."""
        if self.cfg.elrendezes != "termek" or not self.cfg.workspace_id or "workspace" not in self.cfg.utak:
            return True
        from .workspace import WS_TOML, toml_azonosito
        return toml_azonosito(self.cfg.path("workspace") / WS_TOML) == self.cfg.workspace_id

    def _elerheto_jelez(self, ok: bool) -> None:
        """A vault elérhetőségének VÁLTÁSA egyetlen `vault_elerheto {elerheto}` WS-esemény (M5, C29.6): polling nélkül, a
        `Vault` használata észleli (a felület ebből tudja, hogy az SSD eltűnt vagy visszajött). Az első észlelés
        „elérhető” esetén nem esemény."""
        with self._elerheto_zar:
            elozo, self._elerheto = self._elerheto, ok
        if elozo != ok and not (elozo is None and ok):
            self.publish({"tipus": "vault_elerheto", "elerheto": ok})

    def _abs(self, rp: str) -> Path:
        """A vault-relatív út abszolút párja; a szimbolikus link sem vezethet a vaulton kívülre."""
        root = self.root
        p = root / rp
        if not utkapu.alatta(root, p):
            raise kodos(Invalid(f"a vaulton kívüli út: {rp}"), "vault.vaulton_kivul", ut=rp)
        return p

    def kanonikus(self, rp: str, utolso: bool = True) -> str:
        """Kanonikus út (T018): a `norm_path` utáni vault-relatív út SZEGMENSENKÉNT a lemezen álló névvel (NFC; az összevetés
        NFC + `casefold`, pontos egyezés előnyben). Az APFS kis-nagybetűre és normalizálásra érzéketlen, a git pathspec, a
        mentetlen-halmaz és az index viszont nem: `jegyzetek/a.md` ugyanazt a fájlt írta, mint `Jegyzetek/A.md`, de a gép szövege
        „kézi” commitba került. Ami nincs meg a lemezen (új fájl/mappa), az megadott alakban marad; `utolso=False`: az utolsó
        szegmens (egy leendő név) is."""
        reszek = rp.split("/")
        d, ki, megvan = self.root, [], True
        for i, szegmens in enumerate(reszek):
            if megvan and (utolso or i < len(reszek) - 1):
                try:
                    nevek = os.listdir(d)
                except OSError:
                    nevek = []
                egyezo = next((n for n in nevek if nfc(n) == szegmens), None) or \
                    next((n for n in nevek if nfc(n).casefold() == szegmens.casefold()), None)
                if egyezo is not None:
                    ki.append(nfc(egyezo))
                    d = d / egyezo
                    continue
                megvan = False
            ki.append(szegmens)
        return "/".join(ki)

    @staticmethod
    def _on_disk(p: Path) -> Path:
        """A fájl a lemezen álló nevével. Az APFS a név normalizálására nem érzékeny, de megőrzi: a vault
        sok neve NFD. Íráskor a régi nevet tartjuk meg, hogy a csere ne nevezze át a fájlt NFC-re."""
        try:
            for n in os.listdir(p.parent):
                if nfc(n) == nfc(p.name):
                    return p.parent / n
        except OSError:
            pass
        return p

    def _repo(self) -> snapshot.Repo | None:
        repo = snapshot.repos(self.cfg).get("vault")
        return repo if repo and repo.live() else None

    def repo(self) -> snapshot.Repo | None:
        """A vault élő pillanatkép-tárolója (az átnevezésnek, C10), vagy None."""
        return self._repo()

    def lemezen(self, rp: str) -> Path:
        """A vault-relatív (NFC) útnak a lemezen álló (gyakran NFD) alakja; hiányzó fájlnál az út maga."""
        return self._on_disk(self._abs(rp))

    # ------------------------------------------------------------ olvasás

    def media_path(self, rp) -> tuple[Path, str]:
        """Egy médiafájl a kiszolgálásra: (a lemezen álló út, Content-Type). Csak engedélylistás kiterjesztés,
        a vaulton belül, rejtett szegmens nélkül (`norm_path`); más: `Invalid`/`NotFound`."""
        rp = norm_path(rp)
        tipus = MEDIA_TIPUS.get(os.path.splitext(rp)[1].lower())
        if not tipus:
            raise kodos(Invalid(f"nem kiszolgálható fájltípus: {rp}"), "vault.fajltipus", ut=rp)
        p = self._abs(rp)
        if not p.is_file():
            raise kodos(NotFound(f"nincs ilyen fájl: {rp}"), "vault.nincs_fajl", ut=rp)
        return self._on_disk(p), tipus

    def read(self, rp) -> dict:
        """Egy szöveges fájl a szerkesztőnek: tartalom, hash (az írás alapja), változásjel. A `kodolas_hiba`
        igaz, ha a fájl nem érvényes UTF-8 (a tartalomban cserekarakter áll): a szerkesztő ilyenkor csak
        olvasásra nyitja, mert a mentés a hibás bájtokat felülírná (C08, bájthűség)."""
        rp = self.kanonikus(norm_path(rp))
        if not rp.lower().endswith(OLVASHATO):
            raise kodos(Invalid(f"nem szöveges fájl: {rp}"), "vault.nem_szoveges", ut=rp)
        p = self._abs(rp)
        if not p.is_file():
            raise kodos(NotFound(f"nincs ilyen fájl: {rp}"), "vault.nincs_fajl", ut=rp)
        p = self._on_disk(p)
        st = p.stat()
        if st.st_size > MAX_SZOVEG:
            raise kodos(Invalid("túl nagy fájl"), "vault.tul_nagy_fajl")
        b = p.read_bytes()
        try:
            tartalom, hiba = b.decode("utf-8"), False
        except UnicodeDecodeError:
            tartalom, hiba = b.decode("utf-8", errors="replace"), True
        return {"ut": rp, "tartalom": tartalom, "hash": sha1(b), "jel": mark(st), "mtime": st.st_mtime,
                "kodolas_hiba": hiba}

    # ------------------------------------------------------------ írás

    def write(self, d: dict) -> dict:
        """Egy jegyzet mentése. `alap`: a betöltött (vagy utoljára mentett) változat hash-e. `elso`: a
        szerkesztés első mentése (előtte kézi commit). `pillanat`: a szerkesztés lezárása (saját commit).
        A tartalom soremelését a fájléhoz igazítja (CRLF-es fájl CRLF marad)."""
        rp = self.kanonikus(norm_path(d.get("ut")))
        if not rp.lower().endswith(IRHATO):
            raise kodos(Invalid("csak jegyzet (.md), adatbázis-nézet (.base), canvas (.canvas) vagy ismert nyelvű forráskód (pl. .cpp, .py) menthető"), "vault.menthetetlen_tipus")
        tartalom, alap = d.get("tartalom"), d.get("alap")
        if not isinstance(tartalom, str):
            raise kodos(Invalid("hiányzik a tartalom"), "vault.tartalom_hianyzik")
        if not isinstance(alap, str) or not alap:
            raise kodos(Invalid("hiányzik az alapváltozat (alap) — vakon nem írunk felül"), "vault.alap_hianyzik")
        p = self._abs(rp)
        if not p.is_file():
            raise kodos(NotFound(f"a fájl közben eltűnt (áthelyezték vagy törölték?): {rp}"), "vault.fajl_eltunt", ut=rp)
        p = self._on_disk(p)
        felulir = d.get("felulir") is True
        hatarido = time.monotonic() + self.kor_zar_varakozas_mp
        while True:
            with _ut_zar(rp):
                try:
                    return self._write(d, rp, p, tartalom, alap, felulir)
                except _KorZarFoglalt:
                    pass                                 # az útvonal-zár a várakozás közben szabad (gépi írás nem éhezik)
            if time.monotonic() >= hatarido:
                raise HttpError(423, "a core éppen a vaultot írja (a kör-zár foglalt): a lemezen lévő változat még nem "
                                     "került pillanatképbe, ezért a felülírás várakozik", foglalt=True, kod="vault.kor_zar_foglalt")
            time.sleep(0.05)

    def _write(self, d: dict, rp: str, p: Path, tartalom: str, alap: str, felulir: bool = False) -> dict:
        uzenet, pillanat, elotte, git_hiba = "mentve", None, None, None
        with frame.try_run_lock(self.cfg) as szabad:
            if felulir and not szabad:
                raise _KorZarFoglalt()                   # T116: a lemezen álló (külső) változatot előbb pillanatképbe kell tenni
            git = szabad and not self.busy()
            repo = self._repo() if git else None
            tarolo_hiany = git and repo is None and bool(d.get("elso") or d.get("pillanat"))     # T024
            regi = p.read_bytes()
            if b"\r\n" in regi and "\r\n" not in tartalom:
                tartalom = tartalom.replace("\n", "\r\n")
            b = tartalom.encode("utf-8")
            if len(b) > MAX_SZOVEG:
                raise kodos(Invalid("túl nagy jegyzet"), "vault.tul_nagy_jegyzet")
            if rp.lower().endswith(".canvas"):
                _, canvas_hiba = canvas_bajtbol(b)       # C14: hibás JSON nem kerül a lemezre
                if canvas_hiba:
                    raise kodos(Invalid(f"a canvas nem érvényes JSON Canvas, nem mentődött: {canvas_hiba}"), "vault.canvas_ervenytelen", hiba=canvas_hiba)
            if sha1(regi) != alap and b != regi:         # azonos tartalom elavult alappal: az elveszett válasz utáni újraküldés (no-op)
                raise kodos(Conflict("a jegyzet a betöltés óta megváltozott (Obsidian, szinkron vagy egy lánc írta)",
                               hash=sha1(regi), jel=mark(p.stat())), "vault.jegyzet_valtozott")
            if repo and d.get("elso"):
                try:
                    elotte = repo.commit("kézi változások a szerkesztés előtt", {"Mos-Forras": "kezi"})
                except snapshot.SnapshotError as e:      # K1: a mentés pillanatkép nélkül megy tovább
                    repo, git, git_hiba = None, False, str(e)
            if b != regi:
                def ellenoriz():
                    if p.read_bytes() != regi:           # az írás közben is változhatott
                        raise kodos(Conflict("a jegyzet mentés közben megváltozott", hash=sha1(p.read_bytes()),
                                       jel=mark(p.stat())), "vault.jegyzet_mentes_kozben")
                    self.sajat(rp, sha1(b))
                atomi_csere(p, b, ellenoriz)
            else:
                uzenet = "nem változott"
            if repo and d.get("pillanat"):
                try:
                    pillanat = repo.commit_machine(f"{_felirat(rp)} szerkesztve a pultban: {rp}",
                                                   {snapshot.TRAILER_RUN: frame.new_id("SZERK"),
                                                    snapshot.TRAILER_ITEM: rp, "Mos-Forras": FORRAS}, [rp])
                except snapshot.SnapshotError as e:      # K1: a fájl már a helyén — a válasz a fájlírásé
                    git, git_hiba = False, str(e)
        figyelmeztetes = None
        if tarolo_hiany:
            git = False
        if git_hiba:
            figyelmeztetes = self._git_hiba(rp, git_hiba)
            uzenet += " — pillanatkép nélkül: " + figyelmeztetes
        elif tarolo_hiany:
            figyelmeztetes = self._tarolo_hiany(rp)
            uzenet += " — pillanatkép nélkül: " + figyelmeztetes
        elif not git and (d.get("elso") or d.get("pillanat")):
            uzenet += " — pillanatkép nélkül: egy kör vagy feladat éppen a vaultot írja (a változás a " \
                      "következő pillanatkép előtt kézi commitba kerül)"
        h = sha1(b)
        self.publish({"tipus": "vault_iras", "ut": rp, "hash": h, "pillanat": pillanat})
        return {"ok": True, "ut": rp, "hash": h, "jel": mark(p.stat()), "uzenet": uzenet,
                "pillanat": pillanat, "elotte": elotte, "git": git, "figyelmeztetes": figyelmeztetes}

    def _git_hiba(self, rp: str, hiba: str) -> str:
        """A git-hiba szövege a felhasználónak, és a `pillanat_hiba` WS-esemény (K1)."""
        szoveg = ("a pillanatkép-tároló (git) hibát jelzett, a jegyzet pillanatkép nélkül mentődött (a változás "
                  "a következő sikeres pillanatkép előtt kézi commitba kerül). A doctor megmutatja az okát. "
                  f"Részlet: {hiba[:300]}")
        self.publish({"tipus": "pillanat_hiba", "tar": "vault", "ut": rp, "uzenet": szoveg})
        return szoveg

    def _tarolo_hiany(self, rp: str) -> str:
        """T024: a vault elérhető, de a pillanatkép-tároló nem él — a mentés néma `git: true`-ja helyett figyelmeztetés és
        `pillanat_hiba` WS-esemény (nincs visszavonás, előzmény és belső lemezes mentés)."""
        tar = snapshot.repos(self.cfg).get("vault")
        szoveg = (f"nincs élő pillanatkép-tároló ({tar.git_dir if tar else 'vault'}): a jegyzet pillanatkép nélkül mentődött — "
                  "visszavonás, előzmény és belső lemezes mentés nincs. A doctor megmutatja az okát.")
        self.publish({"tipus": "pillanat_hiba", "tar": "vault", "ut": rp, "uzenet": szoveg})
        return szoveg

    # A nem jegyzet célok (kép, PDF, média, canvas, base …): feloldatlan linkjükhöz nem készül jegyzet (C10, C31).
    NEM_JEGYZET_CEL = re.compile(r"\.(png|jpe?g|gif|webp|avif|svg|heic|bmp|tiff?|mp4|m4v|mov|webm|mkv|ogv|mp3|m4a|wav|flac"
                                 r"|ogg|opus|aac|pdf|canvas|base|txt|csv|json)$", re.I)

    def uj_fajl_beallitas(self) -> tuple[str, str]:
        """Az Obsidian új-jegyzet helye a vault `.obsidian/app.json`-jából (csak olvasva; C31, a koordinátor döntése a K214
        helyett): (`newFileLocation`, `newFileFolderPath`). Kulcs vagy olvasható fájl nélkül az Obsidian alapja: `root`."""
        if self.cfg.forras("beallitasok", "fajlok", "uj_mappa") != "os":
            mappa = self.cfg.section("beallitasok").get("fajlok", {}).get("uj_mappa", "")
            return ("current", "/") if mappa == "." else (("folder", mappa) if mappa else ("root", "/"))
        try:
            adat = json.loads((self.root / ".obsidian" / "app.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            adat = {}
        hely = adat.get("newFileLocation") if isinstance(adat, dict) else None
        mappa = adat.get("newFileFolderPath") if isinstance(adat, dict) else None
        return (hely if hely in ("root", "current", "folder") else "root",
                mappa if isinstance(mappa, str) else "/")

    def minden_kiterjesztes(self) -> bool:
        """Az Obsidian `showUnsupportedFiles` kapcsolója az `.obsidian/app.json`-ból (csak olvasva; 07-explorer-12). Kulcs vagy olvasható
        fájl nélkül az Obsidian alapja: hamis (a nem támogatott kiterjesztésű fájl a fán rejtve marad)."""
        try:
            adat = json.loads((self.root / ".obsidian" / "app.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(adat, dict) and adat.get("showUnsupportedFiles") is True

    def link_jegyzet_helye(self, cel, forras, tipus: str = "md") -> dict:
        """A feloldatlan link (`[[cel]]` a `forras` jegyzetből) új jegyzetének helye — az Obsidian 1.14.4
        `createNewMarkdownFileFromLinktext`-je szerint (statikus olvasás; C31, T158): az útvonalas cél a **vault gyökeréhez**
        képest áll, a mappa kis-nagybetűtől és normalizálástól függetlenül egyezik (`kanonikus`, az Obsidian
        `getAbstractFileByPathInsensitive`-je), a hiányzó mappa létrejön (`getOrCreateFolder`); az út nélküli cél helye a
        `newFileLocation` (`root`: a gyökér, `current`: a forrás mappája, `folder`: a `newFileFolderPath`, ha az létezik,
        különben a gyökér). → a `create` kérése (`mappa`, `nev`, `mappa_keszit`)."""
        if not isinstance(cel, str) or not cel.strip():
            raise kodos(Invalid("hiányzik a link célja"), "vault.link_cel_hianyzik")
        tiszta = nfc(cel).strip().replace("\\", "/").lstrip("/")
        relativ = tiszta.startswith(("./", "../"))
        if relativ:
            if not isinstance(forras, str) or not forras:
                raise kodos(Invalid("hiányzik a link forrása"), "vault.link_cel_hianyzik")
            # A norm_path ezután ellenőrzi a normalizált, vaulton belüli célt;
            # a túl sok ../, rejtett mappa és tiltott név továbbra is elutasított.
            tiszta = norm_path(posixpath.normpath(posixpath.join(posixpath.dirname(norm_path(forras)), tiszta)))
        if self.NEM_JEGYZET_CEL.search(tiszta):
            raise kodos(Invalid(f"a cél nem jegyzet (a fájl nem található): {cel}"), "vault.link_cel_nincs", cel=cel)
        kit = ".cpp" if tipus == "cpp" else ".md"          # C36a-UI: a hiányzó `x.cpp` célja C++ forrás
        if tiszta.lower().endswith(kit):
            tiszta = tiszta[:-len(kit)]
        mappa, _, nev = tiszta.rpartition("/")
        if mappa:
            return {"mappa": self.kanonikus(norm_path(mappa)), "nev": nev, "mappa_keszit": True}
        if relativ:
            return {"mappa": "", "nev": nev}
        hely, fix = self.uj_fajl_beallitas()
        if hely == "current" and isinstance(forras, str) and "/" in forras:
            elotag = norm_path(forras).rpartition("/")[0]
            return {"mappa": elotag if self._abs(elotag).is_dir() else "", "nev": nev}
        if hely == "folder":
            f = (fix or "").strip()
            f = "" if _ABSZOLUT_MAPPA.match(f) else f.strip("/")     # a beállított mappa vault-relatív; az abszolút nem érvényes
            if f:
                try:
                    f = self.kanonikus(norm_path(f))
                except Invalid:
                    f = ""
                if self.cfg.forras("beallitasok", "fajlok", "uj_mappa") != "os" and f:
                    return {"mappa": f, "nev": nev, "mappa_keszit": True}
                return {"mappa": f if f and self._abs(f).is_dir() else "", "nev": nev}
        return {"mappa": "", "nev": nev}

    def create(self, d: dict) -> dict:
        """Új jegyzet (vagy `tipus: "base"`: új adatbázis-nézet, C12; `tipus: "canvas"`: üres canvas, `{}`, C14; `tipus: "cpp"`:
        C++ forrás `main`-nel, C36a) egy meglévő mappában. A jegyzet H1-e a név a sorszám-előtag nélkül (L46); meglévő fájlt — kis-nagybetűtől és
        normalizálástól függetlenül — nem ír felül. Sablon a C15 hatóköre."""
        if isinstance(d.get("link"), dict):            # C31 (T158): a feloldatlan link új jegyzete — a helyet a core dönti
            if d.get("mappa") or d.get("tipus") not in (None, "md", "cpp"):
                raise kodos(Invalid("a `link` mellett nem adható meg `mappa`, és a `tipus` csak `md` vagy `cpp`"), "vault.link_mappa")
            d = {**{k: v for k, v in d.items() if k != "link"},
                 **self.link_jegyzet_helye(d["link"].get("cel"), d["link"].get("forras"), d.get("tipus") or "md")}
        tipus = d.get("tipus") or "md"
        if tipus == "forras":                            # F10: új forrásfájl a kód-munkafelület bármely nyelvén (`nyelv`: profil-azonosító)
            profil = kod_nyelvek.profil(d["nyelv"]) if isinstance(d.get("nyelv"), str) else None
            if profil is None:
                raise kodos(Invalid("ismeretlen nyelv"), "vault.nyelv_ismeretlen")
            kitok, kit, felirat = profil.kiterjesztesek, profil.kiterjesztesek[0], f"{profil.nev} forrás"
        elif tipus not in _FELIRAT:
            raise kodos(Invalid("a tipus `md`, `base`, `canvas` vagy `cpp`"), "vault.tipus_hibas")
        else:
            kit = "." + tipus
            kitok, felirat, profil = (kit,), _FELIRAT[tipus], None
        if d.get("mappa") and (not isinstance(d["mappa"], str) or _ABSZOLUT_MAPPA.match(d["mappa"].strip())):
            # a `norm_path` a vezető `/`-t levágná, így egy abszolút mappa csendben vault-relatívvá válna (és `mappa_keszit`
            # mellett új mappa jönne létre a vaulton belül): a mappa vault-relatív út, abszolút nem fogadható el
            raise kodos(Invalid("a `mappa` vault-relatív út kell legyen"), "vault.mappa_nem_relativ")
        mappa = self.kanonikus(norm_path(d.get("mappa"))) if d.get("mappa") else ""
        nev = nfc(str(d.get("nev") or "")).strip()
        for k in kitok:
            if nev.lower().endswith(k):
                nev = nev[:-len(k)].rstrip()
                break
        if not nev or nev.startswith(".") or _TILTOTT_NEV.search(nev) or len(nev.encode("utf-8")) > 200:
            raise kodos(Invalid('érvénytelen név — tilos benne: \\ / : * ? " < > | # ^ [ ], és nem kezdődhet ponttal'), "vault.nev_ervenytelen")
        rp = f"{mappa}/{nev}{kit}" if mappa else f"{nev}{kit}"
        cel_mappa = self._abs(mappa) if mappa else self.root
        mappat_keszit = False
        if not cel_mappa.is_dir():
            # C15: a napi jegyzet hónapmappája hiányozhat; csak kifejezett kérésre jön létre, és csak tiszta nevekkel
            if not (d.get("mappa_keszit") and not cel_mappa.exists()) or any(_TILTOTT_NEV.search(r) for r in mappa.split("/")):
                raise kodos(NotFound(f"nincs ilyen mappa: {mappa}"), "vault.nincs_mappa", mappa=mappa)
            mappat_keszit = True
        p = self._abs(rp)
        if not mappat_keszit and (p.exists() or any(nfc(n).lower() == nfc(nev + kit).lower() for n in os.listdir(cel_mappa))):
            raise kodos(Invalid(f"már van ilyen nevű fájl: {rp}"), "vault.van_ilyen_fajl", ut=rp)
        tartalom = {"base": UJ_BASE, "canvas": UJ_CANVAS, "cpp": cpp_teszt.cpp_vaz(),
                    "forras": profil and kod_nyelvek.forras_vaz(profil.azonosito)}.get(tipus) \
            or f"# {_H1_ELOTAG.sub('', nev)}\n"
        if d.get("tartalom") is not None:                # C15: sablonból kiértékelt váz a H1-váz helyett (C36a: a `.cpp` váza is)
            if tipus not in ("md", "cpp", "forras") or not isinstance(d["tartalom"], str) \
                    or len(d["tartalom"].encode("utf-8")) > MAX_SZOVEG:
                raise kodos(Invalid("a `tartalom` csak egy (nem túl nagy) szöveg lehet, és csak jegyzethez vagy C++ forráshoz"), "vault.tartalom_alak")
            tartalom = d["tartalom"]
        with frame.try_run_lock(self.cfg) as szabad:
            repo = self._repo() if szabad and not self.busy() else None
            tarolo_hiany = szabad and not self.busy() and repo is None             # T024
            self.sajat(rp, sha1(tartalom.encode("utf-8")))
            if mappat_keszit:
                os.makedirs(cel_mappa, exist_ok=True)
                tartos.fsync_mappa(cel_mappa.parent)
            try:                                              # tmp + F_FULLFSYNC + RENAME_EXCL: ha közben létrejött, nem írjuk felül
                tartos.kizaro_ir(p, tartalom.encode("utf-8"))
            except FileExistsError:
                raise kodos(Invalid(f"már van ilyen nevű fájl: {rp}"), "vault.van_ilyen_fajl", ut=rp) from None
            pillanat, figyelmeztetes = None, None
            if repo:
                try:
                    pillanat = repo.commit_machine(f"új {felirat} a pultban: {rp}",
                                                   {snapshot.TRAILER_RUN: frame.new_id("SZERK"),
                                                    snapshot.TRAILER_ITEM: rp, "Mos-Forras": FORRAS}, [rp])
                except snapshot.SnapshotError as e:      # K1: a fájl létrejött, a commit hibája figyelmeztetés
                    repo, figyelmeztetes = None, self._git_hiba(rp, str(e))
            elif tarolo_hiany:
                figyelmeztetes = self._tarolo_hiany(rp)
        b = tartalom.encode("utf-8")
        self.publish({"tipus": "vault_iras", "ut": rp, "hash": sha1(b), "pillanat": pillanat})
        return {"ok": True, "ut": rp, "hash": sha1(b), "pillanat": pillanat, "git": repo is not None,
                "figyelmeztetes": figyelmeztetes}


def utvonalak(r) -> None:
    """A vault-fájl végpontjai az útvonal-regiszterben (C11a)."""
    r.get("/api/vault/fajl", lambda k: k.app.vault.read(k.q.get("ut")))
    r.put("/api/vault/fajl", lambda k: k.app.vault.write(k.torzs()))
    r.post("/api/vault/uj", lambda k: Valasz(201, k.app.vault.create(k.torzs())))
