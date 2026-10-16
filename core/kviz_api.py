"""A kvíz végpontjai (C22a; `docs/C22-TERV.md` 5. fejezet): a beágyazott kvíz kitöltése a szerkesztőben.

A kvíz a vaultban él (`[kviz] mappa`, alapból `<kisero_elotag>Quizzes`; a legacy kvíz formátuma); a végpontok **csak olvassák**, és a
kitöltés eredményét a `{tanulas_db}`-be (2-es migráció) írják — a vaultba nem. Az értékelést a core végzi (egyetlen
elemző a Pythonban, a felület csak mutat); az **API a kulcsot, az idézetet és a magyarázatot a válasz előtt nem adja ki** (48(b),
A3-03): a `GET /api/kviz/kviz` **kitöltés-tokent** ad; a `megoldas` a kérdésre adott választ **rögzíti** (az első válasz
végleges: újrakérdezéssel a kulcs nem szondázható), és csak utána felel; a `kitoltes` a rögzített válaszokból pontoz (a kliens
által küldött `valaszok` nem számít), a `jelol` csak a kitöltés megválaszolt kérdésére áll. A vaultbeli kísérőjegyzet
`> [!success]- Megoldás` szövege nem része ennek a védelemnek (K144).
A kitöltés a Tracker-kapcsolótól független (tanulási állapot, nem telemetria); a válasz kész `tracker` objektumot hordoz
(`{ut, adat}`), a felület ezt továbbítja a `kviz_eredmeny` eseményként.

**A `## Kitöltések` szakasz** (C22b): a kitöltés és a „hibás” jelölés után a core a kvízjegyzet szakaszát a DB-ből újraírja —
nem a végpont ír, hanem a gépi-írás szolgáltatás (in-process, `Mos-Forras: mos-kviz-kitoltes`, `modell: null`, `csere`
alap-hash-sel), `KITOLTES_KESLELTETES_S` késleltetéssel: az addig érkező kitöltések egy commitba vonódnak össze. Nyitott,
mentetlen kvízjegyzetbe nem ír (28(c)); a következő kitöltés pótolja (a szakasz a DB tiszta függvénye).

A logika a `modulok/kviz/`-ban él (tiszta függvények); ez a modul a vault-olvasást, az út ellenőrzését és a HTTP-alakot adja.
A `modulok` csomag importja lusta: egy hibás modul a core indulását nem viheti el.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import sqlite3
import threading
import time
from types import SimpleNamespace

from . import frame
from . import kiserok
from .utvonalak import HttpError
from .vaultio import Conflict, Invalid, NotFound, nfc, norm_path

MAPPA_ALAP = kiserok.alap_mappa("kviz")             # a szállított alap; a mappát a `kiserok.kisero_mappa` adja
KULCS_MINTA = re.compile(r"[A-Za-z0-9_-]{8,80}")
MODOK = ("teljes", "hibasak")
TOKEN_MAX = 64                                  # egyszerre nyitott kitöltések száma (a legrégebben használt esik ki)
TOKEN_ELET_S = 12 * 3600                        # a nyitott kitöltés élettartama az utolsó használattól (újraindításkor elvész)
MS_MAX = 3_600_000
KITOLTES_KESLELTETES_S = 60.0                   # a `## Kitöltések` írása ennyivel a kitöltés után (az addigiak összevonva)
KITOLTES_FORRAS = "mos-kviz-kitoltes"           # determinisztikus gépi írás (`modell: null`), nem AI-funkció
_modulok: SimpleNamespace | None = None


def _m() -> SimpleNamespace:
    """A kvíz-modulok (lusta import)."""
    global _modulok
    if _modulok is None:
        from modulok.kapuk import forras
        from modulok.kviz import ertekeles, esemeny, formatum, tar
        _modulok = SimpleNamespace(forras=forras, ertekeles=ertekeles, esemeny=esemeny, formatum=formatum, tar=tar)
    return _modulok


def mappa(cfg) -> str:
    return kiserok.kisero_mappa(cfg, "kviz")


class Kitoltes:
    """Egy nyitott kitöltés a core memóriájában: a rögzített válaszok (az első válasz végleges)."""

    def __init__(self, ut: str, azon: str, hash_: str):
        self.ut, self.azon, self.hash = ut, azon, hash_
        self.mikor = time.monotonic()
        self.valaszok: dict[str, dict] = {}


class KvizApi:
    def __init__(self, app, kesleltetes_s: float | None = None):
        self.app = app
        self._kitoltesek: dict[str, Kitoltes] = {}
        self._zar = threading.Lock()
        self.kesleltetes_s = KITOLTES_KESLELTETES_S if kesleltetes_s is None else kesleltetes_s
        self._fuggo_irasok: dict[str, threading.Timer] = {}
        self.utolso_iras: dict[str, str] = {}          # kvízjegyzet → az utolsó szakasz-írás eredménye (napló, tesztek)

    # -------------------------------------------------- a `## Kitöltések` szakasz (C22b)

    def kitoltes_utemez(self, rp: str) -> None:
        """A kvízjegyzet `## Kitöltések` szakaszának frissítése `kesleltetes_s` múlva: az addig érkező kitöltések és jelölések
        egy gépi commitba vonódnak össze (a vault.git ne teljen meg zajjal). A szakasz a DB tiszta függvénye, ezért a
        késleltetett írás mindig a legfrissebb állapotot írja."""
        with self._zar:
            if rp in self._fuggo_irasok:
                return
            t = threading.Timer(self.kesleltetes_s, self._utemezett_iras, args=(rp,))
            t.daemon = True
            self._fuggo_irasok[rp] = t
        t.start()

    def _utemezett_iras(self, rp: str) -> None:
        with self._zar:
            self._fuggo_irasok.pop(rp, None)
        try:
            self.utolso_iras[rp] = self.kitoltes_szakasz_ir(rp)
        except Exception as e:                                    # noqa: BLE001 — háttérszál: a hiba a naplóba, a kitöltés megmarad
            self.utolso_iras[rp] = f"hiba: {e}"
            logging.getLogger("manifold.kviz").warning("a Kitöltések szakasz nem íródott (%s): %s", rp, e)

    def kitoltes_szakasz_ir(self, rp: str) -> str:
        """A szakasz írása most (gépi írás, `csere` alap-hash-sel, `modell: null`). → `ok` | `valtozatlan` | `kesobb` (a
        kvízjegyzet nyitott és mentetlen, vagy a kör-zár foglalt: a következő kitöltés pótolja) | `nincs` (a kvízjegyzet eltűnt)."""
        m = _m()
        for _ in range(2):
            try:
                f = self.app.vault.read(rp)
            except (NotFound, Invalid):
                return "nincs"
            tartalek = "KVIZ-00000000-000000-" + hashlib.sha1(nfc(f["ut"]).encode("utf-8")).hexdigest()[:8]
            e = m.formatum.elemez(f["tartalom"], azon_tartalek=tartalek)
            if e.kviz is None:
                return "nincs"
            k = e.kviz
            szakasz = m.formatum.kitoltes_szakasz(k, m.tar.kitoltesek(self.cfg, k.azon), m.tar.jelolesek(self.cfg, k.azon))
            uj = m.formatum.kitoltes_csere(f["tartalom"], szakasz)
            if uj == f["tartalom"]:
                return "valtozatlan"
            try:
                self.app.gepi.ir({"kor": frame.new_id("KVIZ"), "tetel": f["ut"], "forras": KITOLTES_FORRAS, "modell": None,
                                  "uzenet": f"kvíz-kitöltések: {k.cim}"[:200],
                                  "muveletek": [{"tipus": "csere", "ut": f["ut"], "tartalom": uj, "alap": f["hash"]}]})
                return "ok"
            except HttpError as ex:
                if ex.code == 409 and (ex.data.get("nyitott") or ex.data.get("foglalt")):
                    return "kesobb"
                if ex.code != 409:
                    raise
            except Conflict:
                pass                                   # közben változott: újraolvasás
        return "kesobb"

    def leallit(self, irjon: bool = True) -> None:
        """A függő írások azonnal (a core rendezett leállásakor): a késleltetés nem veszítheti el az utolsó kitöltést (a DB-ben
        akkor is megvan; a szakasz a következő kitöltéskor pótlódik). `irjon=False` (kényszer): csak az időzítők állnak le."""
        with self._zar:
            fuggo = list(self._fuggo_irasok.items())
            self._fuggo_irasok.clear()
        for rp, t in fuggo:
            t.cancel()
            if not irjon:
                continue
            try:
                self.utolso_iras[rp] = self.kitoltes_szakasz_ir(rp)
            except Exception as e:                                # noqa: BLE001
                logging.getLogger("manifold.kviz").warning("a Kitöltések szakasz nem íródott (%s): %s", rp, e)

    def _nyit(self, ut: str, k) -> str:
        """Új kitöltés-token a kvízhez (a legrégebbi nyitott esik ki a `TOKEN_MAX` felett)."""
        token = secrets.token_urlsafe(24)
        with self._zar:
            ma = time.monotonic()
            for t in [t for t, x in self._kitoltesek.items() if ma - x.mikor > TOKEN_ELET_S]:
                del self._kitoltesek[t]
            while len(self._kitoltesek) >= TOKEN_MAX:
                del self._kitoltesek[next(iter(self._kitoltesek))]
            self._kitoltesek[token] = Kitoltes(ut, k.azon, _m().formatum.tartalom_hash(k))
        return token

    def _tokenes(self, d: dict, ut: str, k) -> Kitoltes:
        """A kérés tokenéhez tartozó nyitott kitöltés; ismeretlen/lejárt token 410, másik kvíz tokenje vagy a közben
        megváltozott kvíz 409."""
        token = d.get("token")
        if not isinstance(token, str) or not token:
            raise Invalid("hiányzik a `token` (a `GET /api/kviz/kviz` adja)")
        with self._zar:
            x = self._kitoltesek.pop(token, None)
            if x is not None and time.monotonic() - x.mikor <= TOKEN_ELET_S:
                x.mikor = time.monotonic()
                self._kitoltesek[token] = x                            # a legutóbb használt a sor végére kerül
            else:
                x = None
        if x is None:
            raise HttpError(410, "a kitöltés lejárt vagy ismeretlen: nyisd meg újra a kvízt")
        if x.ut != ut or x.azon != k.azon:
            raise HttpError(409, "ez a kitöltés egy másik kvízé")
        if x.hash != _m().formatum.tartalom_hash(k):
            raise HttpError(409, "a kvíz közben megváltozott: nyisd meg újra")
        return x

    @property
    def cfg(self):
        return self.app.cfg

    # -------------------------------------------------- a kvízjegyzet

    def _betolt(self, ut):
        """(kvíz, hibák, a kvízjegyzet kanonikus útja). Csak a kvízmappa alatti `.md`."""
        m = _m()
        if not isinstance(ut, str) or not ut.strip():
            raise Invalid("hiányzik az `ut`")
        rp = norm_path(ut)
        if not rp.lower().endswith(".md"):
            raise Invalid(f"nem jegyzet: {rp}")
        if not nfc(rp).startswith(mappa(self.cfg) + "/"):
            raise Invalid(f"kvízjegyzet csak a „{mappa(self.cfg)}” mappából tölthető: {rp}")
        f = self.app.vault.read(rp)
        rp = f["ut"]
        tartalek = "KVIZ-00000000-000000-" + hashlib.sha1(nfc(rp).encode("utf-8")).hexdigest()[:8]
        e = m.formatum.elemez(f["tartalom"], azon_tartalek=tartalek)
        if e.kviz is None or not e.kviz.kerdesek:
            raise Invalid("nem kitölthető kvízjegyzet: " + ("; ".join(h["szoveg"] for h in e.hibak) or "nincs benne érvényes kérdés"))
        return e.kviz, e.hibak, rp

    def _forras_szakaszok(self, k) -> list[str] | None:
        """A forrásjegyzet szakaszainak címei (a kvíz által nem érintettek jelzéséhez); olvashatatlan forrásnál `None`."""
        try:
            f = self.app.vault.read(k.forras + ".md")
            return [s.cim for s in _m().forras.elokeszit(f["tartalom"]) if s.cim]
        except Exception:                                   # noqa: BLE001 — a forrás hiánya nem akadályozza a kitöltést
            return None

    # -------------------------------------------------- végpontok

    def kviz(self, q: dict) -> dict:
        m = _m()
        k, hibak, rp = self._betolt(q.get("ut"))
        jelolesek = m.tar.jelolesek(self.cfg, k.azon)
        elozo = m.tar.kitoltesek(self.cfg, k.azon)
        ujra = []
        megvaltozott = False
        if elozo:
            megvaltozott = elozo[-1]["szoveg_hash"] != m.formatum.tartalom_hash(k)
            ervenyes = {x.id for x in k.kerdesek}
            ujra = [e["kerdes"] for e in elozo[-1]["eredmenyek"]
                    if e["kategoria"] != "tudja" and not e["jelolt"] and e["kerdes"] in ervenyes]
        return {"ok": True, "ut": rp, "forras_ut": k.forras + ".md", "token": self._nyit(rp, k),
                "kviz": m.ertekeles.kitoltesre(k, set(jelolesek)),
                "hibak": hibak, "ujra": ujra, "megvaltozott": megvaltozott,
                "elozmenyek": [{"mikor": x["mikor"], "mod": x["mod"], **{a: x["osszegzes"][a] for a in ("pont", "osszes", "szazalek")}}
                               for x in elozo[-5:]]}

    def megoldas(self, d: dict) -> dict:
        """A kérdésre adott válasz rögzítése, majd a megoldás. A `valasz` kulcs kötelező (az egész sorszám vagy `null` =
        „nem tudom”); a rögzítés végleges, így a megoldás megnézése egyúttal a kérdés feladása is (hiány)."""
        m = _m()
        k, _, rp = self._betolt(d.get("ut"))
        x = self._tokenes(d, rp, k)
        if "valasz" not in d:
            raise Invalid("hiányzik a `valasz` (a válasz sorszáma, vagy null a „nem tudom”-hoz): válasz nélkül nincs megoldás")
        valasz = d["valasz"]
        if valasz is not None and (isinstance(valasz, bool) or not isinstance(valasz, int)):
            raise Invalid("a `valasz` a válasz sorszáma (egész) vagy null")
        kid = d.get("kerdes")
        if not isinstance(kid, str):
            raise Invalid("hiányzik a `kerdes`")
        if kid not in {q.id for q in k.kerdesek}:
            raise Invalid(f"nincs ilyen kérdés: {kid}")
        ms = d.get("ms")
        with self._zar:
            if kid not in x.valaszok:                                   # az első válasz végleges
                x.valaszok[kid] = {
                    "kerdes": kid, "valasz": valasz if valasz is not None and 0 <= valasz < len(next(q for q in k.kerdesek if q.id == kid).valaszok) else None,
                    "tipp": bool(d.get("tipp")) or valasz is None,
                    "ms": min(ms, MS_MAX) if isinstance(ms, int) and not isinstance(ms, bool) and ms >= 0 else None}
            rogzitett = x.valaszok[kid]["valasz"]
        try:
            return {"ok": True, **m.ertekeles.megoldas(k, kid, rogzitett), "forras_ut": k.forras + ".md"}
        except m.ertekeles.Hiba as e:
            raise Invalid(str(e)) from e

    def kitoltes(self, d: dict) -> dict:
        """A kitöltés értékelése és mentése a token rögzített válaszaiból (a kérés `valaszok` mezője nem számít)."""
        m = _m()
        k, _, rp = self._betolt(d.get("ut"))
        kulcs, mod = d.get("kulcs"), d.get("mod", "teljes")
        if not isinstance(kulcs, str) or not KULCS_MINTA.fullmatch(kulcs):
            raise Invalid("a `kulcs` 8–80 karakteres azonosító legyen (betű, szám, `_`, `-`)")
        if mod not in MODOK:
            raise Invalid("a `mod` teljes vagy hibasak lehet")
        ido_ms = d.get("ido_ms")
        if ido_ms is not None and (isinstance(ido_ms, bool) or not isinstance(ido_ms, int) or not 0 <= ido_ms <= 86_400_000):
            raise Invalid("az `ido_ms` nem negatív egész (ms) legyen")
        try:
            kesz = m.tar.kitoltes_kulccsal(self.cfg, kulcs, k.azon)
            uj = kesz is None
            if uj:
                x = self._tokenes(d, rp, k)
                with self._zar:
                    valaszok = list(x.valaszok.values())
                if not valaszok:
                    raise Invalid("nincs értékelhető válasz: egy érvényes kérdésre sem érkezett válasz")
                kesz = m.ertekeles.kitoltes_ertekel(
                    k, valaszok, mod, m.tar.kitoltesek(self.cfg, k.azon), set(m.tar.jelolesek(self.cfg, k.azon)), ido_ms,
                    self._forras_szakaszok(k), teljes_halmaz=True)
                kesz, uj = m.tar.kitoltes_ment(self.cfg, kulcs, k, rp, kesz)
                with self._zar:
                    self._kitoltesek.pop(d["token"], None)              # a mentett kitöltés tokenje lezárul
                if uj:
                    self.kitoltes_utemez(rp)
        except m.tar.KulcsFoglalt as e:
            raise HttpError(409, str(e)) from e
        except (sqlite3.Error, OSError) as e:
            raise HttpError(503, f"a tanulási adatbázis nem érhető el: {e}") from e
        return {"ok": True, "uj": uj, "ertekeles": kesz, "token": self._nyit(rp, k),         # a következő körhöz
                "tracker": {"ut": k.forras + ".md", "adat": m.esemeny.adat(kesz, k.azon)}}

    def jelol(self, d: dict) -> dict:
        """A „hibás kérdés” jelölés: csak a nyitott kitöltés már megválaszolt kérdésére."""
        m = _m()
        k, _, rp = self._betolt(d.get("ut"))
        x = self._tokenes(d, rp, k)
        kid, hibas = d.get("kerdes"), d.get("hibas")
        if not isinstance(hibas, bool):
            raise Invalid("a `hibas` igaz vagy hamis legyen")
        if kid not in {q.id for q in k.kerdesek}:
            raise Invalid(f"nincs ilyen kérdés: {kid}")
        with self._zar:
            megvalaszolt = kid in x.valaszok
        if not megvalaszolt:
            raise Invalid("a kérdést előbb meg kell válaszolni a kitöltésben, utána jelölhető hibásnak")
        megj = d.get("megjegyzes", "")
        if not isinstance(megj, str):
            raise Invalid("a `megjegyzes` szöveg legyen")
        try:
            m.tar.jelol(self.cfg, k.azon, kid, hibas, megj)
            self.kitoltes_utemez(rp)
            return {"ok": True, "jelolesek": sorted(m.tar.jelolesek(self.cfg, k.azon), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)}
        except (sqlite3.Error, OSError) as e:
            raise HttpError(503, f"a tanulási adatbázis nem érhető el: {e}") from e


def utvonalak(r) -> None:
    def api(k) -> KvizApi:
        if getattr(k.app, "kviz_api", None) is None:
            k.app.kviz_api = KvizApi(k.app)
        return k.app.kviz_api

    r.get("/api/kviz/kviz", lambda k: api(k).kviz(k.q))
    r.post("/api/kviz/megoldas", lambda k: api(k).megoldas(k.torzs()))
    r.post("/api/kviz/kitoltes", lambda k: api(k).kitoltes(k.torzs()))
    r.post("/api/kviz/jelol", lambda k: api(k).jelol(k.torzs()))
