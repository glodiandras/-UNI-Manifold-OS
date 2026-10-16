"""A vault-index: bejárás, elemzés, SQLite, inkrementális frissítés, külső szerkesztés felismerése.

Életciklus: az `indit()` egy író szálat indít. Az író először a figyelőt indítja (az események sorba
állnak), azután stat-bejárással összeveti a vaultot az indexszel: csak a méret vagy az mtime szerint
változott fájl olvasódik be, és ha a hash-e nem változott, nincs újraelemzés. Üres indexnél ez a teljes
építés, egy tranzakcióban. Azután az események ~20 ms-os kötegekben, egy-egy tranzakcióban futnak.

Feloldás: a `feloldas.Feloldo` az egész fájlhalmazon él. Új vagy eltűnt fájlnál csak azok a linkek oldódnak
fel újra, amelyeknek a `kulcs`-a a fájl **kisbetűs** alapneve vagy annak `.md` nélküli alakja: a feloldás (a
pontos és a kis-nagybetűtől független menet is) csak az ilyen alapnevű jelöltektől függ (`feloldas.celkulcs`).

Külső szerkesztés: a core saját írásait (`sajat_iras(ut, hash)`) az index nyilvántartja; ha egy
változás után a lemezen más hash áll, mint amit a core írt, a változás `kulso` (Obsidian, git, Finder,
lánc). WS-esemény: `vault_valtozas {utak, torolt, kulso[, mappak]}`; az építés végén `index {…allapot}`.

C33: az olvasó rész az `IndexOlvaso`-ban él (`olvaso.py`, T172); ez a modul az író. A nagy köteg (szinkron, tömeges
FSEvents) `SZELET` fájlos szeletekben, szeletenként egy tranzakcióban fut, és a szeletek között a core **saját írásai**
(a szerkesztő mentése, a gépi írás) elsőbbséget kapnak (T176): a mentés így legfeljebb egy szelet idejét várja, nem a
teljes kötegét; a mentés utáni API-konzisztencia (a válasz után az index a mentett tartalmat adja) megmarad. A csak
mappát érintő változás is generációt és eseményt ad (T173). A sérült `vault.sqlite` félrekerül és újraépül (T171).
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

from .. import atirat, fuzet, utkapu
from ..config import Config
from ..vaultio import Invalid, NotFound  # noqa: F401 — a régi importálók (`indexelo.Invalid`) kedvéért
from . import elemzo, feloldas, figyelo, kereses, pdfszoveg, tar
from .feloldas import SKIP_DIRS, nfc
from .olvaso import IndexOlvaso, NemKesz  # noqa: F401 — a `NemKesz` a szerver hibatérképének is innen jön

KOTEG_MP = 0.005                # ennyi ideig gyűjti az író a további eseményeket (az FSEvents maga is gyűjt)
TOMEGES = 500                   # ennyi új/eltűnt fájl fölött minden link újra feloldódik
SAJAT_MAX = 2000
_KIT_TIPUS = {"md": "md", "canvas": "canvas", "base": "base", "pdf": "pdf", "vtt": "felirat", "srt": "felirat"}
for _k in ("jpg", "jpeg", "png", "gif", "webp", "heic", "svg", "bmp", "avif", "tif", "tiff"):
    _KIT_TIPUS[_k] = "kep"
for _k in ("mp4", "mov", "mkv", "webm", "m4v", "avi", "ogv"):
    _KIT_TIPUS[_k] = "video"
for _k in ("mp3", "m4a", "wav", "flac", "ogg", "opus", "aac", "3gp"):
    _KIT_TIPUS[_k] = "hang"
HASHELT = ("md", "canvas", "base", "felirat")     # C25c: a felirat (VTT) szövege is kereshető, a változását a hash dönti
PDF_KOTEG_MP = 0.2              # C25c: a kinyert PDF-szövegek FTS-be írása kötegenként legfeljebb ennyi ideig (a többi újra sorba áll)
SZELET = 200                    # C33 (T176): a nagy köteg ennyi fájlos tranzakciókban; köztük a saját írások elsőbbséget kapnak
ELERHETOSEG_MP = 10.0           # C33 (T175): tétlenségben ennyi másodpercenként egy `stat`: eltűnt-e a vault (esemény nélkül is)


def tipus(nev: str) -> tuple[str, str]:
    kit = nev.rsplit(".", 1)[-1].lower() if "." in nev else ""
    return kit, _KIT_TIPUS.get(kit, "egyeb")


def _ervenyes(rel: str) -> bool:
    """A legacy bejárás szabálya egy útra: a `SKIP_DIRS` mappák alatt és a pontos fájl nem tartozik bele."""
    reszek = rel.split("/")
    return bool(rel) and not any(r in SKIP_DIRS for r in reszek[:-1]) and not reszek[-1].startswith(".") \
        and reszek[-1] not in SKIP_DIRS


class Index(IndexOlvaso):
    """A vault-index (az író; az olvasó fele az `IndexOlvaso`). `publish`: esemény a WS-nek (`events.Bus.publish`)."""

    def __init__(self, cfg: Config, publish=None, pdf_kapu=None, elerheto=None):
        """`pdf_kapu`: `() → bool`, a PDF-szöveg kinyerésének kapuja (a core-ban a feladatsor `Kapu.admit`-ja egy automatikus
        munkára, C25c); nélküle (tesztek, CLI) a PDF-ek szövegét a kinyerő nem állítja elő, csak a gyorsítótárból olvas.
        `elerheto`: `(bool) → None`, a vault elérhetőségének váltása (a core-ban a `Vault` `vault_elerheto` eseménye, T175)."""
        self._olvaso_init()
        self.cfg = cfg
        self.root = Path(cfg.path("vault"))
        self.db_ut = Path(cfg.path("index")) / "vault.sqlite"
        b = cfg.section("index")
        self.figyelo_fajta = b.get("figyelo", "fsevents")
        self.latencia = float(b.get("latencia_mp", 0.03))
        self.lekerdezes_mp = float(b.get("lekerdezes_mp", 2))
        self.max_talalat = int(b.get("max_talalat", 200))
        self.regex_idokorlat = float(b.get("regex_idokorlat_mp", kereses.REGEX_IDOKORLAT_MP))
        self.publish = publish or (lambda e, **k: None)
        self._elerheto_jel = elerheto or (lambda ok: None)
        self._q: queue.Queue = queue.Queue()
        self._elso: collections.deque = collections.deque()   # T176: a saját írások elsőbbségi sora [(utak, kesz)]
        self._elso_fut = False
        self._szal: threading.Thread | None = None
        self._figyelo = None
        self._sajat: collections.OrderedDict[str, str] = collections.OrderedDict()
        self._sajat_lock = threading.Lock()
        self._kesz = threading.Event()
        self.feloldo = feloldas.Feloldo()
        self._fl_lock = threading.Lock()        # a feloldót az író szál módosítja, az API-szálak olvassák
        self.tipusok: dict = {}
        self._c = None
        self._elemzesi_hibak: dict[str, str] = {}      # T037: a csonka sorral felvett fájlok (ut → hiba), csak az író szál írja
        self._gyujto: dict | None = None    # T176: a szeletelt köteg eseményeinek gyűjtője (a köteg végén egy esemény)
        self._koteg_hiba = False        # az `allapot_d["hiba"]` egy köteg átmeneti hibájából jön: a következő sikeres köteg törli
        self.allapot_d = {"kesz": False, "elerheto": None, "fajlok": 0, "jegyzetek": 0, "epites_ms": None,
                          "figyelo": None, "utolso_frissites": None, "hiba": None, "elemzesi_hibak": [],
                          "pdf_szoveg": {"osszes": 0, "kesz": 0}, "felretett": None}
        # C25c: a PDF-ek kereshető szövege — gyorsítótár és (kapuval) a kinyerő háttérszál (`pdfszoveg`)
        self._pdf_tar: pdfszoveg.Gyorsitotar | None = None
        self.pdf_kinyero: pdfszoveg.Kinyero | None = None
        self._pdf_kapu = pdf_kapu

    # ================================================================ életciklus

    def indit(self) -> None:
        if self._szal is None:
            self._szal = threading.Thread(target=self._fut, name="index-iro", daemon=True)
            self._szal.start()

    def leallit(self, timeout: float = 10) -> None:
        if self.pdf_kinyero is not None:
            self.pdf_kinyero.leallit()
            self.pdf_kinyero = None
        if self._figyelo:
            self._figyelo.leallit()
            self._figyelo = None
        if self._szal:
            self._q.put(None)
            self._szal.join(timeout)
            self._szal = None
        self._pool_urit()

    def var(self, timeout: float = 60) -> bool:
        """Megvárja az első szinkront (tesztek, mérés)."""
        return self._kesz.wait(timeout)

    def jelez(self, utak, teljes: bool = False) -> None:
        """A figyelő jele: megváltozott nyers relatív utak; `teljes`: az alfát újra be kell járni."""
        self._q.put(("teljes" if teljes else "utak", list(utak), None))

    def _iro_el(self) -> bool:
        """Él-e az író szál. Ha kilépett (pl. a `tar.nyit` hibája), a várakozók nem várnak rá hiába (A-javító, 2026-10-14)."""
        szal = self._szal
        return szal is not None and szal.is_alive()

    def frissit(self, utak, var: float = 5.0) -> bool:
        """Az utak (nyers relatív) azonnali újravizsgálata; megvárja, hogy a változás az API-ban látsszon. Ha az író szál
        nem él, nem vár (hamis)."""
        if not self._iro_el():
            return False
        kesz = threading.Event()
        self._q.put(("utak", list(utak), kesz))
        return kesz.wait(var)

    def vart_iras(self, rp: str, h: str) -> None:
        """A core saját írása előre bejelentve (`vaultio`, a csere előtt): ha a lemezen ez a hash áll,
        a változás nem külső."""
        rp = nfc(rp)
        with self._sajat_lock:
            self._sajat[rp] = h
            self._sajat.move_to_end(rp)
            while len(self._sajat) > SAJAT_MAX:
                self._sajat.popitem(last=False)

    def sajat_iras(self, rp: str, h: str, var: float = 2.0) -> None:
        """A core saját írása megtörtént: a fájl azonnal újraindexelődik (nem vár a figyelőre).
        Megvárja (legfeljebb `var` s), hogy a változás az API-ban látsszon.

        C33 (T176): az elsőbbségi sorba kerül — az író egy nagy köteg két szelete között (≤ `SZELET` fájl) feldolgozza, nem
        a köteg végén. A szerződés: a válasz után az index a mentett tartalmat adja; ha az író `var` s alatt nem ér oda (pl.
        egyetlen nagy fájl elemzése), a `vault_valtozas` esemény hozza."""
        rp = nfc(rp)
        self.vart_iras(rp, h)
        if not self._iro_el():          # nincs (vagy már nem él) író szál: a mentés ne várja hiába a teljes `var`-t
            return
        kesz = threading.Event()
        self._elso.append(([self._lemez_ut(rp)], kesz))
        self._q.put(("ebreszt", [], None))          # a tétlen író felébred; a köteg közepén járó a szelethatáron veszi
        kesz.wait(var)

    def lemez_ut(self, rp: str) -> str:
        """Az NFC út lemezen álló (nyers) relatív alakja az indexből."""
        return self._lemez_ut(nfc(rp))

    def _lemez_ut(self, rp: str) -> str:
        try:
            with self.olvaso(tranzakcio=False) as c:
                r = c.execute("SELECT lemez_ut FROM fajl WHERE ut = ?", (rp,)).fetchone()
            return r[0] if r else rp
        except Exception:  # noqa: BLE001 — az index még nem épült fel
            return rp

    # ================================================================ író szál

    def _fut(self) -> None:
        felretett: list = []
        try:
            self._c = tar.nyit(self.db_ut, iro=True, felretett=felretett)
        except Exception as e:  # noqa: BLE001
            self.allapot_d["hiba"] = f"{type(e).__name__}: {e}"
            self._kesz.set()
            return
        if felretett:                       # T171: a sérült index félrekerült, az első szinkron újraépíti
            self.allapot_d["felretett"] = felretett[-1].name
        try:
            self._pdf_tar = pdfszoveg.Gyorsitotar(self.db_ut.parent / "pdf-szoveg.sqlite")
        except Exception as e:  # noqa: BLE001 — gyorsítótár nélkül a PDF-ek csak név szerint kereshetők
            print(f"[index] a PDF-szöveg gyorsítótára nem nyílik meg: {e}", file=sys.stderr, flush=True)
        if self._pdf_tar is not None and self._pdf_kapu is not None:
            b = self.cfg.section("index")
            self.pdf_kinyero = pdfszoveg.Kinyero(self.cfg, self._pdf_tar, self._pdf_kapu, self._pdf_kesz, self.root,
                                                 idokorlat=float(b.get("pdf_idokorlat_mp", pdfszoveg.ALAP_IDOKORLAT_MP)))
            self.pdf_kinyero.indit()
        try:
            self._betolt_feloldo()
            try:
                self._figyelo = figyelo.keszit(self.root, self.jelez, self.figyelo_fajta, self.latencia,
                                               self.lekerdezes_mp)
                self.allapot_d["figyelo"] = self._figyelo.fajta
            except Exception as e:  # noqa: BLE001 — figyelő nélkül is indexel (indításkori szinkron)
                self.allapot_d["hiba"] = f"figyelő: {e}"
            t0 = time.perf_counter()
            try:
                self._szinkron("", elso=True)
            except Exception as e:  # noqa: BLE001
                if not tar.serult_hiba(e):
                    raise
                self._serult_ujraepit(e, publikal=False)        # T171: menet közben derült ki (a próbaolvasás nem látta)
            self._szamlal()             # változás nélküli indulásnál a _szinkron nem számol
            self.allapot_d["epites_ms"] = round((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            self.allapot_d["hiba"] = f"{type(e).__name__}: {e}"
        self.allapot_d["kesz"] = True
        self._kesz.set()
        self.publish({"tipus": "index", **self.allapot()})
        with contextlib.suppress(Exception):            # C25c: a szöveg nélküli PDF-ek a gyorsítótárból / a kinyerőhöz (sorban)
            self._pdf_hianyzok()
        while True:
            self._elsobbseg()
            try:
                elem = self._q.get(timeout=ELERHETOSEG_MP)
            except queue.Empty:
                self._elerhetoseg_proba()       # T175: tétlenségben is észrevesszük, ha a vault eltűnt (esemény nélkül)
                continue
            if elem is None:
                break
            koteg = [elem]
            hatar = time.monotonic() + KOTEG_MP
            leall = False
            while True:
                marad = hatar - time.monotonic()
                if marad <= 0:
                    break
                try:
                    e = self._q.get(timeout=marad)
                except queue.Empty:
                    break
                if e is None:
                    leall = True
                    break
                koteg.append(e)
            try:
                self._koteg(koteg)
                self._koteg_hiba_torol()
            except Exception as e:  # noqa: BLE001 — az író szál nem halhat meg egy fájltól
                self._koteg_hiba_jelez(e)
                with contextlib.suppress(Exception):
                    self._c.execute("ROLLBACK")
                if tar.serult_hiba(e):
                    with contextlib.suppress(Exception):
                        self._serult_ujraepit(e)
            finally:
                for _, _, kesz in koteg:
                    if kesz is not None:
                        kesz.set()
            if leall:
                break
        self._elsobbseg()                   # a leállás előtt bejelentett saját írás se várjon hiába
        self._c.close()
        if self._pdf_tar is not None:
            self._pdf_tar.close()

    # ---------------------------------------------------------------- elsőbbség, elérhetőség, sérülés (C33)

    def _elsobbseg(self) -> None:
        """A saját írások elsőbbségi sora (T176): a köteg két szelete között és minden kör elején. Nem rekurzív: egy saját
        írás feldolgozása közben (amely maga is szeletelhetne) nem fut újra."""
        if self._elso_fut or not self._elso:
            return
        self._elso_fut = True
        try:
            while self._elso:
                utak, kesz = self._elso.popleft()
                gyujto, self._gyujto = self._gyujto, None       # a saját írás eseménye azonnal megy, nem a köteg végén
                try:
                    self._koteg([("utak", utak, None)])
                    self._koteg_hiba_torol()
                except Exception as e:  # noqa: BLE001
                    self._koteg_hiba_jelez(e)
                    with contextlib.suppress(Exception):
                        self._c.execute("ROLLBACK")
                finally:
                    self._gyujto = gyujto
                    kesz.set()
        finally:
            self._elso_fut = False

    def _koteg_hiba_jelez(self, e: Exception) -> None:
        self.allapot_d["hiba"] = f"{type(e).__name__}: {e}"
        self._koteg_hiba = True

    def _koteg_hiba_torol(self) -> None:
        """Egy köteg átmeneti hibája (pl. egy olvasás közben eltűnt fájl, foglalt adatbázis) a következő SIKERES kötegnél
        lekerül: nem látszik tartós index-hibaként. Az induláskori (építési) és a figyelő-hiba marad."""
        if self._koteg_hiba:
            self._koteg_hiba = False
            self.allapot_d["hiba"] = None
            with contextlib.suppress(Exception):
                self.publish({"tipus": "index", **self.allapot()})

    def _elerhetoseg(self, ok: bool) -> None:
        """A vault elérhetőségének rögzítése; a VÁLTÁS `index` WS-esemény és az `elerheto` horog (a `Vault` egyetlen
        `vault_elerheto` eseménye, T175). Az első észlelés nem esemény (az indulás végén úgyis megy egy `index`)."""
        elozo = self.allapot_d["elerheto"]
        self.allapot_d["elerheto"] = ok
        if elozo is None or elozo == ok:
            return
        with contextlib.suppress(Exception):
            self._elerheto_jel(ok)
        self.publish({"tipus": "index", **self.allapot()})

    def _elerhetoseg_proba(self) -> None:
        """Tétlenségben egy `stat` (T175): a kihúzott vagy átnevezett vault esemény nélkül is észlelhető. Ha visszajött, a
        teljes szinkron igazít (a kiesés alatti változások)."""
        if not self.allapot_d["kesz"]:
            return
        if self.root.is_dir():
            if self.allapot_d["elerheto"] is False:
                with contextlib.suppress(Exception):
                    self._koteg([("teljes", [""], None)])
        else:
            self._elerhetoseg(False)

    def _serult_ujraepit(self, hiba: BaseException, publikal: bool = True) -> None:
        """A menet közben sérültnek bizonyult index (T171): a kapcsolatok zárva, a fájl félre (`serult-<idő>.sqlite`), új,
        üres index és teljes szinkron. A félretett fájl a doctorban látszik."""
        print(f"[index] az index sérült ({hiba}); félreteszem és újraépítem", file=sys.stderr, flush=True)
        with contextlib.suppress(Exception):
            self._c.close()
        self._pool_urit()
        cel = tar.felretesz(self.db_ut)
        self._c = tar.nyit(self.db_ut, iro=True)
        self._pool_urit()               # F5: új készlet-generáció — a közben nyitott olvasó a félretett fájlra mutatna
        self.allapot_d["felretett"] = cel.name if cel else None
        self.allapot_d["hiba"] = None
        self._elemzesi_hibak.clear()
        self._betolt_feloldo()
        self._szinkron("", elso=True)
        self._szamlal()
        self._uj_generacio(None, True)
        if publikal:
            self.publish({"tipus": "index", **self.allapot()})

    def _betolt_feloldo(self) -> None:
        self.tipusok = elemzo.tipusok_olvas(self.root)
        uj = feloldas.Feloldo(r[0] for r in self._c.execute(
            "SELECT ut FROM fajl WHERE torolve IS NULL ORDER BY lemez_ut"))
        with self._fl_lock:
            self.feloldo = uj

    def _koteg(self, koteg: list) -> None:
        if not self.root.is_dir():
            self._elerhetoseg(False)
            return
        teljes, utak, pdfek = set(), [], []
        for fajta, lista, _ in koteg:
            if fajta == "teljes":
                teljes.update(lista)
            elif fajta == "pdf":
                pdfek.extend(lista)
            else:
                utak.extend(lista)
        if pdfek:
            self._pdf_koteg(pdfek)
        if not teljes and not utak:
            return
        if "" in teljes or self.allapot_d["elerheto"] is False:
            return self._szinkron("")
        for alfa in sorted(teljes):
            self._szinkron(alfa)
        jeloltek, torolt, alfak, tipusvalt = {}, set(), [], False
        mappalista: dict = {}               # a köteg idejére: mappa → {NFC név: a lemezen álló név} (T038)
        for rel in dict.fromkeys(utak):
            rel = rel.strip("/")
            if rel == ".obsidian/types.json":
                tipusvalt = True
                continue
            if not _ervenyes(rel):
                continue
            # T038: az APFS kis-nagybetűre és normalizálásra érzéketlen, ezért `root/rel` létezése nem bizonyít: a jelölt a
            # lemezen álló PONTOS névvel él (szülőmappa-lista, NFC-összevetés); a régi (kis-nagybetűben vagy normalizálásban
            # eltérő) név eltűnt. A normalizálás csak az index kulcsánál (`nfc`) történik, a `lemez_ut` a lemezen álló név.
            lemez = self._lemezen(rel, mappalista)
            full = self.root / lemez if lemez is not None else None
            if full is not None and full.is_dir():
                alfak.append(lemez)
            elif full is not None and full.is_file():
                jeloltek[nfc(lemez)] = lemez
            else:
                torolt.add(nfc(rel))
                torolt.update(self._alatta(nfc(rel)))
        if tipusvalt:
            self._tipusok_ujra()
        mappak = set()
        for r in jeloltek.values():
            d = os.path.dirname(r)
            while d:
                mappak.add(nfc(d))
                d = os.path.dirname(d)
        self._alkalmaz_szeletelve(list(jeloltek.items()), sorted(torolt - set(jeloltek)), mappak_uj=mappak,
                                  mappak_torolt={t for t in torolt if self._lemezen(t, mappalista) is None})
        for alfa in alfak:
            self._szinkron(alfa)

    def _lemezen(self, rel: str, mappalista: dict | None = None) -> str | None:
        """A vault-relatív `rel` a lemezen ténylegesen álló, PONTOS névvel (szegmensenként a szülőmappa listájából, NFC-
        összevetéssel, kis-nagybetű-érzékenyen); `None`, ha nincs ilyen. Az APFS-en a `root / rel` kis-nagybetűtől és
        normalizálástól függetlenül „létezik”, ezért az index figyelője ezt használja az `is_file()` helyett (T038).
        `mappalista`: a köteg idejére szóló gyorsítótár. (Nem a `Vault.kanonikus`: az NFC nevet ad és kis-nagybetűt egyesít.)"""
        mappalista = {} if mappalista is None else mappalista
        d, ki = self.root, []
        for szegmens in (r for r in rel.split("/") if r):
            nevek = mappalista.get(d)
            if nevek is None:
                try:
                    nevek = {nfc(n): n for n in os.listdir(d)}
                except OSError:
                    nevek = {}
                mappalista[d] = nevek
            nev = nevek.get(nfc(szegmens))
            if nev is None:
                return None
            ki.append(nev)
            d = d / nev
        return "/".join(ki)

    def _alatta(self, rp: str) -> list[str]:
        """Az indexben a `rp` mappa alatt álló élő fájlok (egy törölt mappa eseményére)."""
        minta = rp.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
        return [r[0] for r in self._c.execute(
            "SELECT ut FROM fajl WHERE torolve IS NULL AND ut LIKE ? ESCAPE '\\'", (minta,))]

    def _bejar(self, alfa: str) -> tuple[list[tuple[str, str]], set[str]]:
        """A legacy bejárás egy alfára: [(NFC út, nyers út)], és a mappák (NFC)."""
        base = str(self.root)
        start = os.path.join(base, alfa) if alfa else base
        if alfa and not _ervenyes(alfa + "/x"):
            return [], set()
        fajlok, mappak = [], set()
        for dp, dn, fn in os.walk(start):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            rel_dp = os.path.relpath(dp, base)
            if rel_dp != ".":
                mappak.add(nfc(rel_dp))
            for f in fn:
                if not f.startswith(".") and utkapu.belul(base, os.path.join(dp, f)):      # T098: vaulton kívüli symlink nem fájl
                    fajlok.append(os.path.join(dp, f))
        fajlok.sort()
        return [(nfc(os.path.relpath(p, base)), os.path.relpath(p, base)) for p in fajlok], mappak

    def _szinkron(self, alfa: str, elso: bool = False) -> None:
        """A vault (vagy egy alfája) összevetése az indexszel stat alapján."""
        if not self.root.is_dir():
            self._elerhetoseg(False)
            return
        self._elerhetoseg(True)
        if elso and json.dumps(self.tipusok, sort_keys=True) != (tar.meta(self._c, "tipusok") or "{}"):
            self._tipusok_ujra()
        lista, mappak = self._bejar(alfa)
        alfa_nfc = nfc(alfa)
        if alfa_nfc:
            regi = {alfa_nfc, *self._alatta(alfa_nfc)}
            regi_mappak = {r[0] for r in self._c.execute("SELECT ut FROM mappa WHERE torolve IS NULL")
                           if r[0] == alfa_nfc or r[0].startswith(alfa_nfc + "/")}
        else:
            regi = {r[0] for r in self._c.execute("SELECT ut FROM fajl WHERE torolve IS NULL")}
            regi_mappak = {r[0] for r in self._c.execute("SELECT ut FROM mappa WHERE torolve IS NULL")}
        most = {rp for rp, _ in lista}
        self._alkalmaz_szeletelve(lista, sorted(regi - most), mappak_uj=mappak - regi_mappak,
                                  mappak_torolt=regi_mappak - mappak, csendes=elso)

    def _tipusok_ujra(self) -> None:
        """A `.obsidian/types.json` változott: a tulajdonságok típusa újraszámolódik a tárolt értékből."""
        self.tipusok = elemzo.tipusok_olvas(self.root)
        c = self._c
        c.execute("BEGIN")
        for rid, k, e in c.execute("SELECT rowid, kulcs, ertek FROM tulajdonsag").fetchall():
            v = json.loads(e)
            t = self.tipusok.get(k)
            t = t if t in elemzo.TIPUSOK else elemzo.tipus_ertekbol(k, v)
            c.execute("UPDATE tulajdonsag SET tipus = ?, ervenyes = ? WHERE rowid = ?", (t, int(elemzo._illik(t, v)), rid))
        tar.meta(c, "tipusok", json.dumps(self.tipusok, sort_keys=True))
        c.execute("COMMIT")
        self._uj_generacio(None, True)
        self.publish({"tipus": "tulajdonsag_tipusok"})      # változatlan FM-et mutató panelek / kulcs-cache is frissül

    # ---------------------------------------------------------------- alkalmazás

    def _alkalmaz_szeletelve(self, jeloltek, torolt, mappak_uj=(), mappak_torolt=(), csendes=False) -> None:
        """Az `_alkalmaz` `SZELET` fájlos tranzakciókban (T176); a szeletek között a saját írások elsőbbséget kapnak. Az
        események a köteg végén egyetlen `vault_valtozas`-ba olvadnak (a felület egy rohamot kap, nem szeletenként egyet).
        Az eltűnt fájlok és a mappák az utolsó szeletben."""
        jeloltek = list(jeloltek)
        if len(jeloltek) <= SZELET or self._gyujto is not None:
            return self._alkalmaz(jeloltek, torolt, mappak_uj, mappak_torolt, csendes)
        self._gyujto = {"valtozott": [], "kulso": [], "eltunt": [], "mappak": []}
        try:
            for i in range(0, len(jeloltek), SZELET):
                utolso = i + SZELET >= len(jeloltek)
                self._alkalmaz(jeloltek[i:i + SZELET], torolt if utolso else [], mappak_uj if utolso else (),
                               mappak_torolt if utolso else (), csendes)
                if not utolso:
                    self._elsobbseg()
        finally:
            g, self._gyujto = self._gyujto, None
        if not csendes:
            self._esemeny(g["valtozott"], g["kulso"], g["eltunt"], g["mappak"])

    def _esemeny(self, valtozott: list, kulso: list, eltunt: list, mappak: list) -> None:
        """Egy `vault_valtozas` (vagy a szeletelt köteg alatt a gyűjtőbe); `mappak`: a csak mappát érintő változás (T173)."""
        if not (valtozott or eltunt or mappak):
            return
        if self._gyujto is not None:
            for k, v in (("valtozott", valtozott), ("kulso", kulso), ("eltunt", eltunt), ("mappak", mappak)):
                self._gyujto[k].extend(v)
            return
        ev = {"tipus": "vault_valtozas", "torolt": eltunt}
        if len(valtozott) + len(eltunt) > TOMEGES:
            ev.update(tomeges=True, darab=len(valtozott) + len(eltunt), utak=[], kulso=[])
        else:
            ev.update(utak=valtozott, kulso=kulso)
        if mappak:
            ev["mappak"] = mappak[:TOMEGES]
        self.publish(ev)

    def _szerkezet(self, fid: int) -> str:
        """Egy fájl gráf- és graf-meta-szempontú lenyomata (T070): a linkjei (a feloldott céllal), a címkéi, a tulajdonságai,
        a canvas-hibája. Ha egy mentés után ez nem változik, a `szerkezet_generacio` sem: a gráf gyorsítótára érvényes marad."""
        c = self._c
        h = hashlib.sha1()
        for sql in ("SELECT fajta, cel_nyers, alcel, beagyazas, cel, alap, tobbertelmu FROM link WHERE forras_id = ? "
                    "ORDER BY sorrend",
                    "SELECT cimke FROM cimke WHERE fajl_id = ? ORDER BY rowid",
                    "SELECT kulcs, ertek FROM tulajdonsag WHERE fajl_id = ? ORDER BY sorrend",
                    "SELECT canvas_hiba, aliasok FROM fajl WHERE id = ?"):
            h.update(repr([tuple(r) for r in c.execute(sql, (fid,))]).encode("utf-8"))
        return h.hexdigest()

    def _alkalmaz(self, jeloltek, torolt, mappak_uj=(), mappak_torolt=(), csendes=False) -> None:
        c = self._c
        most = time.time()
        valtozott, kulso, uj, eltunt, ujraelemzett, pdfek = [], [], [], [], [], []
        erintett: list[str] = []        # minden út, amelynek a sora változott (a stat-változás is): a Bases inkrementális frissítése
        regi_szerkezet: dict[int, str] = {}
        szerkezeti = False              # a gráf / graf-meta változhatott (T070)
        mappa_valt: list[str] = []      # T173: a ténylegesen megjelent / eltűnt mappák
        irt = False                     # volt-e bármilyen írás: a `generacio` ezen múlik (a stat-változás is: `file.mtime`)
        c.execute("BEGIN")
        try:
            for rp, lemez in jeloltek:
                full = self.root / lemez
                try:
                    st = full.stat()
                except OSError:
                    torolt = [*torolt, rp]
                    continue
                if not utkapu.belul(self.root, full):          # T098: az FSEvents-ből jövő út sem olvasható a vaulton kívülre
                    torolt = [*torolt, rp]
                    continue
                r = c.execute("SELECT id, meret, mtime_ns, hash, torolve, lemez_ut FROM fajl WHERE ut = ?",
                              (rp,)).fetchone()
                el = r is not None and r["torolve"] is None
                if el and r["meret"] == st.st_size and r["mtime_ns"] == st.st_mtime_ns and r["lemez_ut"] == lemez:
                    continue
                kit, tip = tipus(rp.rsplit("/", 1)[-1])
                b = h = None
                if tip in HASHELT:
                    try:
                        b = full.read_bytes()
                    except OSError:
                        torolt = [*torolt, rp]
                        continue
                    h = hashlib.sha1(b).hexdigest()
                if el and tip != "pdf" and (h is None or h == r["hash"]):
                    c.execute("UPDATE fajl SET meret = ?, mtime_ns = ?, lemez_ut = ? WHERE id = ?",
                              (st.st_size, st.st_mtime_ns, lemez, r["id"]))
                    irt = True
                    erintett.append(rp)
                    if r["lemez_ut"] != lemez:          # a gráf a `lemez_ut` szerint rendez
                        szerkezeti = True
                    if h is None:
                        valtozott.append(rp)
                        kulso.append(rp)
                    continue
                if el:
                    regi_szerkezet[r["id"]] = self._szerkezet(r["id"])
                try:
                    c.execute("SAVEPOINT fajl_ir")
                    fid = self._fajl_ir(rp, lemez, kit, tip, st, h, b, full, r["id"] if r else None, most)
                    c.execute("RELEASE fajl_ir")
                    self._elemzesi_hibak.pop(rp, None)
                except Exception as e:  # noqa: BLE001 — T037: egy rossz fájl nem viheti el a köteget és a hidegépítést
                    c.execute("ROLLBACK TO fajl_ir")
                    c.execute("RELEASE fajl_ir")
                    fid = self._fajl_csonka(rp, lemez, kit, tip, st, h, r["id"] if r else None, most, e)
                irt = True
                ujraelemzett.append(fid)
                valtozott.append(rp)
                erintett.append(rp)
                if tip == "pdf":
                    pdfek.append(rp)
                with self._sajat_lock:
                    if self._sajat.get(rp) != h or (el and h is None):     # (a PDF: a core nem írja, a változása külső)
                        kulso.append(rp)
                if not el:
                    uj.append(rp)
            for rp in dict.fromkeys(torolt):
                r = c.execute("SELECT id FROM fajl WHERE ut = ? AND torolve IS NULL", (rp,)).fetchone()
                if r:
                    self._szarmaztatott_torol(r["id"])
                    c.execute("UPDATE fajl SET torolve = ? WHERE id = ?", (most, r["id"]))
                    if self.pdf_kinyero is not None:
                        self.pdf_kinyero.elvet(rp)
                    self._elemzesi_hibak.pop(rp, None)
                    eltunt.append(rp)
                    irt = True
            for m in mappak_uj:
                # T173: csak a valóban megjelent (új vagy visszatért) mappa számít változásnak — a szinkron minden mappát átad
                if c.execute("INSERT INTO mappa(ut, torolve) VALUES (?, NULL) ON CONFLICT(ut) DO UPDATE SET torolve = NULL "
                             "WHERE torolve IS NOT NULL", (m,)).rowcount:
                    mappa_valt.append(m)
            for m in mappak_torolt:
                minta = m.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
                if c.execute("UPDATE mappa SET torolve = ? WHERE torolve IS NULL AND (ut = ? OR ut LIKE ? ESCAPE '\\')",
                             (most, m, minta)).rowcount:
                    mappa_valt.append(m)
            with self._fl_lock:
                for rp in uj:
                    self.feloldo.hozzaad(rp)
                for rp in eltunt:
                    self.feloldo.elvesz(rp)
            self._felold(ujraelemzett, uj + eltunt)
            if uj or eltunt:
                szerkezeti = True
            elif not szerkezeti:
                szerkezeti = any(self._szerkezet(fid) != h for fid, h in regi_szerkezet.items())
            if valtozott or eltunt or mappa_valt:
                tar.meta(c, "frissitve", str(most))
            c.execute("COMMIT")
            self._elemzesi_hibak_kozzetesz()
        except BaseException:
            c.execute("ROLLBACK")
            if uj or eltunt:                 # a memóriabeli feloldót a DB-hez igazítjuk
                self._betolt_feloldo()
            raise
        if irt or mappa_valt:
            # az új/eltűnt fájl a többi fájl link-célját is átírhatja (`_felold`): akkor a Bases teljes újraolvasása kell
            self._uj_generacio(None if (uj or eltunt) else erintett, szerkezeti and bool(irt))
        if pdfek and not csendes:           # az első szinkron után a `_pdf_hianyzok` gyűjti őket
            self._q.put(("pdf", pdfek, None))
        if valtozott or eltunt or mappa_valt:
            self.allapot_d["utolso_frissites"] = most
            self._szamlal()
            if any(u.lower().endswith(".pdf") for u in (*valtozott, *eltunt)):
                self._pdf_szamlal()
            if not csendes:
                self._esemeny(valtozott, kulso, eltunt, mappa_valt)

    def _fajl_csonka(self, rp, lemez, kit, tip, st, h, fid, most, hiba: BaseException) -> int:
        """A fájl **csonka sora** (T037), ha az elemzése vagy az indexelése kivételt dobott: a `fajl` sor megvan (hash, méret és
        mtime-mal, így a változatlan fájlt nem elemzi újra minden szinkron), a fában és a név szerinti keresésben látszik, a
        származtatott sorai (link, címke, fejezet, …) nincsenek; a hiba a `fm_hiba`/`canvas_hiba` mezőben és az állapot
        `elemzesi_hibak` listájában áll. Az ép fájlok indexelését és a köteget ez nem érinti."""
        c = self._c
        szoveg = f"indexelési hiba: {type(hiba).__name__}: {' '.join(str(hiba).split())}"[:300]
        self._elemzesi_hibak[rp] = szoveg
        print(f"[index] {rp}: {szoveg}", file=sys.stderr, flush=True)
        mappa, _, nev = rp.rpartition("/")
        adat = (rp, lemez, nev, kit, mappa, tip, st.st_size, st.st_mtime_ns, h, None,
                szoveg if tip == "md" else None, szoveg if tip == "canvas" else None, "[]", most)
        if fid is None:
            fid = c.execute("INSERT INTO fajl(ut, lemez_ut, nev, kit, mappa, tipus, meret, mtime_ns, hash, fm_nyers, "
                            "fm_hiba, canvas_hiba, aliasok, indexelve, torolve) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)", adat).lastrowid
        else:
            self._szarmaztatott_torol(fid)
            c.execute("UPDATE fajl SET ut=?, lemez_ut=?, nev=?, kit=?, mappa=?, tipus=?, meret=?, mtime_ns=?, hash=?, "
                      "fm_nyers=?, fm_hiba=?, canvas_hiba=?, aliasok=?, indexelve=?, torolve=NULL WHERE id=?", (*adat, fid))
        torzs = nev.rsplit(".", 1)[0] if tip in ("md", "canvas", "base") else nev
        c.execute("INSERT INTO fts(rowid, ut, nev, tartalom) VALUES (?, ?, ?, '')", (fid, rp, torzs))
        return fid

    def _elemzesi_hibak_kozzetesz(self) -> None:
        self.allapot_d["elemzesi_hibak"] = [{"ut": u, "hiba": e} for u, e in list(self._elemzesi_hibak.items())[:50]]

    def _szamlal(self) -> None:
        r = self._c.execute("SELECT count(*), sum(tipus = 'md') FROM fajl WHERE torolve IS NULL").fetchone()
        self.allapot_d["fajlok"], self.allapot_d["jegyzetek"] = r[0], r[1] or 0

    def _szarmaztatott_torol(self, fid: int) -> None:
        c = self._c
        for t in tar.SZARMAZTATOTT:
            c.execute(f"DELETE FROM {t} WHERE fajl_id = ?", (fid,))
        c.execute("DELETE FROM link WHERE forras_id = ?", (fid,))
        c.execute("DELETE FROM fts WHERE rowid = ?", (fid,))
        self._szakaszok_torol(fid)

    def _szakaszok_torol(self, fid: int) -> None:
        """C25c: a fájl `fts_szakasz` sorai (a `szakasz` indexén át: a jegyzetnél üres, nem jár teljes FTS-bejárással)."""
        c = self._c
        c.execute("DELETE FROM fts_szakasz WHERE rowid IN (SELECT id FROM szakasz WHERE fajl_id = ?)", (fid,))
        c.execute("DELETE FROM szakasz WHERE fajl_id = ?", (fid,))

    def _szakaszok_ir(self, fid: int, fajta: str, szakaszok) -> None:
        """C25c: a PDF lapjai / a felirat ablakai az `fts_szakasz`-ba (a régieket előbb törli), és a `media_szoveg` jel."""
        c = self._c
        self._szakaszok_torol(fid)
        for szoveg, ertek, sor_kezd, idok in szakaszok:
            sid = c.execute("INSERT INTO szakasz(fajl_id, ertek, sor_kezd, idok) VALUES (?, ?, ?, ?)",
                            (fid, ertek, sor_kezd, json.dumps(idok) if idok is not None else None)).lastrowid
            c.execute("INSERT INTO fts_szakasz(rowid, tartalom) VALUES (?, ?)", (sid, szoveg))
        c.execute("INSERT OR REPLACE INTO media_szoveg(fajl_id, fajta, szakaszok) VALUES (?, ?, ?)", (fid, fajta, len(szakaszok)))

    def _fajl_ir(self, rp, lemez, kit, tip, st, h, b, full, fid, most) -> int:
        c = self._c
        mappa, _, nev = rp.rpartition("/")
        j = None
        if tip == "md":
            j = elemzo.elemez(feloldas.szoveg(b), self.tipusok)
        elif tip == "canvas":
            j = elemzo.elemez_canvas(*feloldas.canvas_olvas(full))
        adat = (rp, lemez, nev, kit, mappa, tip, st.st_size, st.st_mtime_ns, h,
                j.fm_nyers if j else None, j.fm_hiba if j else None, j.canvas_hiba if j else None,
                json.dumps(j.aliasok, ensure_ascii=False) if j else "[]", most)
        if fid is None:
            fid = c.execute("INSERT INTO fajl(ut, lemez_ut, nev, kit, mappa, tipus, meret, mtime_ns, hash, fm_nyers, "
                            "fm_hiba, canvas_hiba, aliasok, indexelve, torolve) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)", adat).lastrowid
        else:
            self._szarmaztatott_torol(fid)
            c.execute("UPDATE fajl SET ut=?, lemez_ut=?, nev=?, kit=?, mappa=?, tipus=?, meret=?, mtime_ns=?, hash=?, "
                      "fm_nyers=?, fm_hiba=?, canvas_hiba=?, aliasok=?, indexelve=?, torolve=NULL WHERE id=?",
                      (*adat, fid))
        torzs = nev.rsplit(".", 1)[0] if tip in ("md", "canvas", "base") else nev
        tartalom = j.tartalom if j else ""
        if tip == "kep":                # C21 (7. pont): a füzetfotó átirata kereshető, a vaultba nem kerül (`{fuzet}/ocr.json`)
            tartalom = fuzet.ocr_szoveg(self.cfg, nev, st.st_size)
        c.execute("INSERT INTO fts(rowid, ut, nev, tartalom) VALUES (?, ?, ?, ?)", (fid, rp, torzs, tartalom))
        if tip == "felirat" and kit == "vtt":
            # C25c: a VTT mondatai időkóddal a külön `fts_szakasz`-ba (az elemző a `core/atirat.py`-é; a jegyzetek `fts`-e és a
            # bm25-statisztikája érintetlen). A PDF szövegét az író szál külön, rövid tranzakciókban tölti (`_pdf_koteg`): a
            # hidegépítés és a mentések indexelése nem vár a 22 M karakteres FTS-írásra
            self._szakaszok_ir(fid, "felirat", atirat.kereso_szakaszok(b))
        if j is None:
            return fid
        c.executemany("INSERT INTO tulajdonsag VALUES (?,?,?,?,?,?)",
                      [(fid, i, t.kulcs, t.tipus, json.dumps(t.ertek, ensure_ascii=False), int(t.ervenyes))
                       for i, t in enumerate(j.tulajdonsagok)])
        c.executemany("INSERT INTO cimke VALUES (?,?,?,?,?)",
                      [(fid, x["cimke"], x["cimke"].lower(), x["forras"], x["sor"]) for x in j.cimkek])
        c.executemany("INSERT INTO fejezet VALUES (?,?,?,?)",
                      [(fid, x["szint"], x["szoveg"], x["sor"]) for x in j.fejezetek])
        c.executemany("INSERT INTO blokk VALUES (?,?,?,?)",
                      [(fid, x["azon"], x["sor"], x["kezdo_sor"]) for x in j.blokkok])
        c.executemany("INSERT INTO feladat VALUES (?,?,?,?,?,?,?)",
                      [(fid, x["sor"], x["allapot"], x["szoveg"], x["behuzas"], x["datumok"].get("hatarido"),
                        json.dumps(x["datumok"], ensure_ascii=False)) for x in j.feladatok])
        c.executemany("INSERT INTO keplet VALUES (?,?,?,?,?,?,?)",
                      [(fid, x["sor"], x["sor_veg"], x["kezd"], x["veg"], int(x["blokk"]), x["forras"])
                       for x in j.kepletek])
        c.executemany("INSERT INTO kodblokk VALUES (?,?,?,?)",
                      [(fid, x["nyelv"], x["sor_kezd"], x["sor_veg"]) for x in j.kodblokkok])
        c.executemany("INSERT INTO link(forras_id, sorrend, fajta, cel_nyers, alcel, alias, beagyazas, tulajdonsag, "
                      "csomopont, sor, oszlop, hossz, kulcs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(fid, i, L.fajta, L.cel if isinstance(L.cel, str) else str(L.cel), L.alcel, L.alias,
                        int(L.beagyazas), L.tulajdonsag, L.csomopont, L.sor, L.oszlop, L.hossz,
                        feloldas.celkulcs(L.cel if isinstance(L.cel, str) else str(L.cel)))
                       for i, L in enumerate(j.linkek)])
        return fid

    # ---------------------------------------------------------------- PDF-szöveg (C25c)

    def _pdf_gyorsitotar(self, rp: str, lemez: str, meret: int, mtime_ns: int) -> list[str] | None:
        """A PDF lapjainak szövege a gyorsítótárból (`[]`: hibás vagy szöveg nélküli PDF — feldolgozottnak számít, nem kérjük újra);
        `None`: még nincs kinyerve — ilyenkor a kinyerő sorába kerül (ha van kinyerő)."""
        if self._pdf_tar is None:
            return None
        g = self._pdf_tar.olvas(rp, meret, mtime_ns)
        if g is not None:
            return g["lapok"] if g["allapot"] == "kesz" else []
        if self.pdf_kinyero is not None:
            self.pdf_kinyero.ker(rp, lemez, meret, mtime_ns)
        return None

    def _pdf_kesz(self, rp: str) -> None:
        """A kinyerő jele (a saját szálán): a gyorsítótárban új eredmény áll — az író szál a sorából veszi."""
        self._q.put(("pdf", [rp], None))

    def _pdf_hianyzok(self) -> None:
        """Induláskor: a még fel nem dolgozott (`media_szoveg` nélküli) élő PDF-ek — a gyorsítótárból az író szál során át az FTS-be, ami ott sincs,
        a kinyerőhöz. Így a megszakadt kinyerés és az újraépített `vault.sqlite` is pótlódik."""
        if self._pdf_tar is None:
            return
        utak = [r[0] for r in self._c.execute(
            "SELECT f.ut FROM fajl f LEFT JOIN media_szoveg m ON m.fajl_id = f.id WHERE f.tipus = 'pdf' AND f.torolve IS NULL "
            "AND m.fajl_id IS NULL ORDER BY f.ut")]
        if utak:
            self._q.put(("pdf", utak, None))
        self._pdf_szamlal()

    def _pdf_koteg(self, utak: list[str]) -> None:
        """A kinyert szövegek az FTS-be, PDF-enként egy tranzakcióban, legfeljebb `PDF_KOTEG_MP` ideig (a többi a sor végére
        kerül: a jegyzetek mentésének indexelése nem vár egy 130 PDF-es feltöltésre)."""
        hatar = time.monotonic() + PDF_KOTEG_MP
        utak = list(dict.fromkeys(utak))
        irt = 0
        for i, rp in enumerate(utak):
            if time.monotonic() > hatar:
                self._q.put(("pdf", utak[i:], None))
                break
            irt += self._pdf_alkalmaz(rp)
        if not irt:
            return
        self._pdf_szamlal()
        # a keresőpanel a „PDF-szöveg: n/N” állapotot ebből látja (nem `index` esemény: arra a fa, a gráf, a Ma is újratölt)
        self.publish({"tipus": "pdf_szoveg", **self.allapot()["pdf_szoveg"]})

    def _pdf_alkalmaz(self, rp: str) -> bool:
        c = self._c
        r = c.execute("SELECT id, nev, lemez_ut, meret, mtime_ns FROM fajl WHERE ut = ? AND torolve IS NULL AND tipus = 'pdf'",
                      (rp,)).fetchone()
        if r is None or r["meret"] is None or r["mtime_ns"] is None:
            return False
        lapok = self._pdf_gyorsitotar(rp, r["lemez_ut"], r["meret"], r["mtime_ns"])
        if lapok is None:
            return False
        c.execute("BEGIN")
        try:
            self._szakaszok_ir(r["id"], "pdf", pdfszoveg.szakaszok(lapok))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        self._uj_generacio((), False)       # a PDF szövege a Bases sorait és a gráfot nem érinti
        return True

    def _pdf_szamlal(self) -> None:
        r = self._c.execute("SELECT count(*), count(m.fajl_id) FROM fajl f LEFT JOIN media_szoveg m ON m.fajl_id = f.id "
                            "WHERE f.tipus = 'pdf' AND f.torolve IS NULL").fetchone()
        self.allapot_d["pdf_szoveg"] = {"osszes": r[0], "kesz": r[1]}

    def _felold(self, ujraelemzett: list[int], valtozo_fajlok: list[str]) -> None:
        """Az újraelemzett fájlok linkjei, és azok, amelyeknek a feloldása a változó fájlhalmaztól függ."""
        c = self._c
        if len(valtozo_fajlok) > TOMEGES:
            sorok = c.execute("SELECT l.id, l.cel_nyers, f.ut FROM link l JOIN fajl f ON f.id = l.forras_id").fetchall()
        else:
            kulcsok = set()
            for rp in valtozo_fajlok:
                b = feloldas.kis(rp.rsplit("/", 1)[-1])
                kulcsok.add(b)
                if b.endswith(".md"):
                    kulcsok.add(b[:-3])
            sorok = {}
            for i in range(0, len(ujraelemzett), 500):
                resz = ujraelemzett[i:i + 500]
                for r in c.execute("SELECT l.id, l.cel_nyers, f.ut FROM link l JOIN fajl f ON f.id = l.forras_id "
                                   f"WHERE l.forras_id IN ({','.join('?' * len(resz))})", resz):
                    sorok[r[0]] = r
            kl = list(kulcsok)
            for i in range(0, len(kl), 500):
                resz = kl[i:i + 500]
                for r in c.execute("SELECT l.id, l.cel_nyers, f.ut FROM link l JOIN fajl f ON f.id = l.forras_id "
                                   f"WHERE l.kulcs IN ({','.join('?' * len(resz))})", resz):
                    sorok[r[0]] = r
            sorok = list(sorok.values())
        upd = []
        with self._fl_lock:
            for lid, cel, forras in sorok:
                hit, alap, tobb = self.feloldo.resolve(cel, forras)
                upd.append((hit, alap, int(tobb), lid))
        c.executemany("UPDATE link SET cel = ?, alap = ?, tobbertelmu = ? WHERE id = ?", upd)
