"""A kártyák végpontjai és a kártyamappa szinkronja (C23b; `docs/C23-TERV.md` 4.2, 7., 8. fejezet).

A kártya **szövege mindig a vault aktuális fájljából** jön (a kísérőjegyzet elemezve), az **állapota** a `{tanulas_db}`-ből. A
végpontok a vaultba nem írnak; az értékelés és a visszavonás a tanulási adatbázist írja (a Tracker-kapcsolótól független:
tanulási állapot, nem telemetria). A sikeres válasz kész `tracker` objektumot ad (`{ut, adat}`: a `kartya_valasz` esemény, a
T143 fehérlistája szerint), a felület ezt továbbítja (30(b): a felület csak eseményt küld).

- `GET  /api/kartya/allapot`               a „Ma” oldal és a vezérlő összesítője: `{allapot, esedekes, uj, holnap, osszes}`;
- `GET  /api/kartya/esedekes?limit=`        a „Mai ismétlés”: az esedékes kártyák, utánuk az újak a napi limitig;
- `GET  /api/kartya/jegyzet?ut=`            egy kísérőjegyzet kártyái és állapota (a beágyazott pakli);
- `POST /api/kartya/valasz {azon, jegy, ms}` értékelés (1–4) → az új állapot és a tracker-esemény;
- `POST /api/kartya/visszavon {azon}`       az utolsó értékelés visszavonása (⌘Z);
- `POST /api/kartya/export {utak?, cel?}`   `.apkg` a `{szemelyes}/export/` alá (a vaultba nem kerülhet);
- `POST /api/kartya/import {fajl, proba}`   `.apkg` import: próbában jelentés; élesben előbb a kísérőjegyzetek a gépi írással
  (`Mos-Forras: mos-kartya`, determinisztikus írás: `modell: null`), **utána** az állapot (`apkg.importal`), hogy a szinkron ne
  lássa töröltnek a kártyákat. A kártyák által hivatkozott médiája ugyanabban a tételben, a gépi írás `behoz` műveletével kerül a
  csatolmány-mappába (K308; 55(b), 83. döntés javaslata); a jelentés `media_jelentes` mezője nevenként mondja meg, mi került be,
  mi kapott új nevet és mi maradt ki, miért.

**Szinkron** (`KartyaSzinkron`): a busz `vault_valtozas` eseményére a kártyamappa érintett fájljai → `tanulas.sqlite`
(`modulok/kartya/szinkron.py`); eseményvesztésnél (`kimaradt`) és tömeges változásnál teljes szinkron. A `modulok` importja lusta.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from . import kiserok, rejtett
from .utvonalak import HttpError
from .vaultio import Invalid, nfc, norm_path

MS_MAX = 3_600_000
LIMIT_MAX = 500
_modulok: SimpleNamespace | None = None


def _m() -> SimpleNamespace:
    global _modulok
    if _modulok is None:
        from modulok.kartya import apkg, formatum, html, szinkron, utemezo
        _modulok = SimpleNamespace(apkg=apkg, formatum=formatum, html=html, szinkron=szinkron, utemezo=utemezo)
    return _modulok


def mappa(cfg) -> str:
    return kiserok.kisero_mappa(cfg, "kartya")


# ------------------------------------------------------------------ összesítő (Ma oldal, vezérlő)

def osszegzes(cfg, most: datetime | None = None) -> dict:
    """`{allapot: "kesz", esedekes, uj, holnap, osszes}`: a most esedékes (nem új) kártyák, a ma még elkezdhető újak (a napi
    limitig), a holnap (a következő tanulási napon) esedékessé válók, az élő kártyák száma. Adatbázis nélkül nullák."""
    m = _m()
    t = m.szinkron.most_utc(most)
    esed = m.utemezo.esedekesek(cfg, t)
    esedekes = sum(1 for k in esed if k["allapot"] != 0)
    uj = len(esed) - esedekes
    from . import tanulas_db
    holnap = osszes = 0
    kezd = m.utemezo.nap_kezdete(cfg, t)
    hatar = m.szinkron.iso(kezd + timedelta(days=2))
    with tanulas_db.olvaso(cfg) as c:
        if c is not None:
            holnap = c.execute("SELECT COUNT(*) FROM kartya WHERE torolve IS NULL AND felfuggesztve = 0 AND allapot != 0 "
                               "AND esedekes > ? AND esedekes <= ?", (m.szinkron.iso(t), hatar)).fetchone()[0]
            osszes = c.execute("SELECT COUNT(*) FROM kartya WHERE torolve IS NULL").fetchone()[0]
    return {"allapot": "kesz", "esedekes": esedekes, "uj": uj, "holnap": holnap, "osszes": osszes}


# ------------------------------------------------------------------ a szinkron szolgáltatás

class KartyaSzinkron:
    """A kártyamappa → `tanulas.sqlite` a vault változásaira (háttérszál; a vaultot csak olvassa)."""

    def __init__(self, cfg, bus=None, kesleltetes_mp: float = 1.5, indulasi_kesleltetes_mp: float = 20.0):
        self.cfg, self.bus = cfg, bus
        self.kesleltetes_mp, self.indulasi = kesleltetes_mp, indulasi_kesleltetes_mp
        self._utak: set[str] = set()
        self._teljes = True
        self._zar = threading.Lock()
        self._futas = threading.Lock()
        self._jel = threading.Event()
        self._stop = threading.Event()
        self.utolso: dict | None = None
        self._szal: threading.Thread | None = None

    def indit(self) -> None:
        if self._szal is not None:
            return
        if self.bus is not None:
            sub = self.bus.subscribe()
            threading.Thread(target=self._figyel, args=(sub,), name="kartya-szinkron-esemeny", daemon=True).start()
        self._szal = threading.Thread(target=self._fut, name="kartya-szinkron", daemon=True)
        self._szal.start()

    def leallit(self) -> None:
        self._stop.set()
        self._jel.set()

    def _figyel(self, sub) -> None:
        try:
            while not self._stop.is_set():
                e = sub.get(timeout=1.0)
                if e:
                    self.esemeny(e)
        finally:
            sub.close()

    def esemeny(self, e: dict) -> None:
        if e.get("tipus") == "kimaradt" or (e.get("tipus") == "vault_valtozas" and e.get("tomeges")):
            with self._zar:
                self._teljes = True
            self._jel.set()
        elif e.get("tipus") == "vault_valtozas":
            elo = mappa(self.cfg) + "/"
            utak = {nfc(u) for u in [*(e.get("utak") or ()), *(e.get("torolt") or ())] if nfc(u).startswith(elo)}
            if utak:
                with self._zar:
                    self._utak |= utak
                self._jel.set()

    def _fut(self) -> None:
        if self._stop.wait(self.indulasi):
            return
        while not self._stop.is_set():
            try:
                self.egyszer()
            except Exception as exc:  # noqa: BLE001 — a szinkron hibája nem viheti el a core-t
                print(f"[kártya] szinkron-hiba: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self._jel.wait()
            self._jel.clear()
            if self._stop.wait(self.kesleltetes_mp):          # a gyors egymásutáni mentések egy szinkronba
                return

    def egyszer(self) -> dict | None:
        """A függő szinkron most (a végpontok is hívják az olvasás előtt). → a jelentés, vagy `None`, ha nem volt teendő. Egyszerre
        egy fut: a végpont megvárja a háttérszál folyó szinkronját (különben a még üres adatbázist olvasná)."""
        with self._futas:
            return self._egyszer()

    def _egyszer(self) -> dict | None:
        with self._zar:
            teljes, utak = self._teljes, self._utak
            self._teljes, self._utak = False, set()
        if not teljes and not utak:
            return None
        from . import tanulas_db
        if not (Path(self.cfg.path("vault")) / mappa(self.cfg)).is_dir() and not tanulas_db.ut(self.cfg).exists():
            return None                                         # nincs kártya és adatbázis sem: fájlt sem hozunk létre
        m = _m()
        if teljes:
            jel = m.szinkron.szinkron(self.cfg)
        else:
            vault = Path(self.cfg.path("vault"))
            el = {}
            for u in sorted(utak):
                p = vault / u
                el[u] = m.formatum.elemez(p.read_bytes().decode("utf-8", "replace")) if p.is_file() else m.formatum.Elemzes()
            jel = m.szinkron.szinkron(self.cfg, el, teljes=False)
        self.utolso = {"ido": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: v for k, v in jel.items() if k != "hibak"},
                       "hibak": len(jel.get("hibak") or [])}
        return jel


# ------------------------------------------------------------------ végpontok

class KartyaApi:
    def __init__(self, app):
        self.app = app

    @property
    def cfg(self):
        return self.app.cfg

    def _szinkron_most(self) -> None:
        sz = getattr(self.app, "kartya_szinkron", None)
        if sz is not None:
            try:
                sz.egyszer()
            except (OSError, sqlite3.Error) as exc:
                print(f"[kártya] szinkron-hiba: {exc}", file=sys.stderr, flush=True)

    def _elemzes(self, ut: str, gyorsitotar: dict):
        if ut not in gyorsitotar:
            try:
                f = self.app.vault.read(ut)
                gyorsitotar[ut] = _m().formatum.elemez(f["tartalom"])
            except Exception:  # noqa: BLE001 — a hiányzó/olvashatatlan fájl kártyái nem jönnek
                gyorsitotar[ut] = None
        return gyorsitotar[ut]

    def _kartya_ki(self, r: dict, k, elore: bool, most) -> dict:
        m = _m()
        ki = {"azon": r["azon"], "jegyzet": r["jegyzet"], "kerdes": k.kerdes, "valasz": k.valasz, "forras": k.forras,
              "allapot": r["allapot"], "uj": r["allapot"] == 0, "esedekes": r["esedekes"], "sor": k.sor}
        if elore:
            try:
                ki["elorejelzes"] = {str(j): s for j, s in m.utemezo.elorejelzes(self.cfg, r["azon"], most).items()}
            except ValueError:
                ki["elorejelzes"] = None
        return ki

    def allapot(self, q: dict) -> dict:
        self._szinkron_most()
        return osszegzes(self.cfg)

    def esedekes(self, q: dict) -> dict:
        """A „Mai ismétlés” sora: az esedékesek, utánuk az újak a napi limitig — a szöveg a vaultból (a fájlból eltűnt kártya kimarad)."""
        m = _m()
        self._szinkron_most()
        try:
            limit = int(q.get("limit", 200))
        except (TypeError, ValueError):
            raise Invalid("a `limit` egész szám") from None
        limit = max(1, min(LIMIT_MAX, limit))
        most = m.szinkron.most_utc()
        gy: dict = {}
        ki = []
        for r in m.utemezo.esedekesek(self.cfg, most):
            e = self._elemzes(r["jegyzet"], gy) if r.get("jegyzet") else None
            k = next((x for x in m.formatum.ervenyes(e) if x.azon == r["azon"]), None) if e else None
            if k is None:
                continue
            ki.append(self._kartya_ki(r, k, len(ki) < 50, most))
            if len(ki) >= limit:
                break
        return {"ok": True, "kartyak": ki, **osszegzes(self.cfg, most)}

    def jegyzet(self, q: dict) -> dict:
        """Egy kísérőjegyzet kártyái a fájl sorrendjében, állapottal; `esedekes`: most ismétlendő (az új a napi limitig)."""
        m = _m()
        ut = q.get("ut")
        if not isinstance(ut, str) or not ut.strip():
            raise Invalid("hiányzik az `ut`")
        rp = norm_path(ut)
        if not rp.lower().endswith(".md"):
            rp += ".md"
        if not nfc(rp).startswith(mappa(self.cfg) + "/"):
            raise Invalid(f"kártyapakli csak a „{mappa(self.cfg)}” mappából tölthető: {rp}")
        f = self.app.vault.read(rp)
        rp = f["ut"]
        e = m.formatum.elemez(f["tartalom"])
        kartyak = m.formatum.ervenyes(e)
        sz = getattr(self.app, "kartya_szinkron", None)
        if sz is not None:
            with sz._zar:
                sz._utak.add(nfc(rp))
        self._szinkron_most()
        most = m.szinkron.most_utc()
        esed = {r["azon"] for r in m.utemezo.esedekesek(self.cfg, most)}
        from . import tanulas_db
        sorok = {}
        with tanulas_db.olvaso(self.cfg) as c:
            if c is not None:
                for r in c.execute("SELECT * FROM kartya WHERE jegyzet = ?", (nfc(rp),)):
                    sorok[r["azon"]] = dict(r)
        ki = []
        for k in kartyak:
            r = sorok.get(k.azon)
            if r is None:
                continue
            d = self._kartya_ki(r, k, k.azon in esed, most)
            d["esedekes_most"] = k.azon in esed
            ki.append(d)
        return {"ok": True, "ut": rp, "kartyak": ki, "hibak": e.hibak,
                "esedekes": sum(1 for x in ki if x["esedekes_most"] and not x["uj"]),
                "uj": sum(1 for x in ki if x["esedekes_most"] and x["uj"]), "osszes": len(ki)}

    def _forras_jegyzet(self, r) -> str | None:
        """A kártya forrásjegyzete (a tracker tantárgyához, 30(f)): a forrássor célja a core feloldójával (L42), különben a
        kísérőjegyzet."""
        cel = (r["forras"] or "").split("#", 1)[0].strip()
        if cel:
            try:
                u = self.app.index.felold_egy(cel, r["jegyzet"] or "")
                if u:
                    return u
            except Exception:  # noqa: BLE001
                pass
        return r["jegyzet"]

    def valasz(self, d: dict) -> dict:
        m = _m()
        azon, jegy, ms = d.get("azon"), d.get("jegy"), d.get("ms")
        if not isinstance(azon, str) or not m.formatum.AZON_RE.fullmatch(azon):
            raise Invalid("az `azon` egy kártya-azonosító (c-…)")
        if isinstance(jegy, bool) or not isinstance(jegy, int) or not 1 <= jegy <= 4:
            raise Invalid("a `jegy` 1–4 (Again, Hard, Good, Easy)")
        if ms is not None and (isinstance(ms, bool) or not isinstance(ms, int) or ms < 0):
            raise Invalid("az `ms` nem negatív egész")
        ms = None if ms is None else min(ms, MS_MAX)
        try:
            uj = m.utemezo.valaszol(self.cfg, azon, jegy, ms)
        except ValueError as e:
            raise Invalid(str(e)) from e
        except (sqlite3.Error, OSError) as e:
            raise HttpError(503, f"a tanulási adatbázis nem érhető el: {e}") from e
        from . import tanulas_db
        with tanulas_db.olvaso(self.cfg) as c:
            r = c.execute("SELECT jegyzet, forras FROM kartya WHERE azon = ?", (azon,)).fetchone() if c is not None else None
        adat = {"jegy": jegy, "kartya_id": azon, **({"ms": ms} if ms is not None else {})}
        return {"ok": True, "allapot": uj, "tracker": {"ut": self._forras_jegyzet(r) if r else None, "adat": adat}}

    def visszavon(self, d: dict) -> dict:
        m = _m()
        azon = d.get("azon")
        if not isinstance(azon, str) or not m.formatum.AZON_RE.fullmatch(azon):
            raise Invalid("az `azon` egy kártya-azonosító (c-…)")
        try:
            a = m.utemezo.visszavon(self.cfg, azon)
        except (sqlite3.Error, OSError) as e:
            raise HttpError(503, f"a tanulási adatbázis nem érhető el: {e}") from e
        return {"ok": True, "visszavonva": a is not None, "allapot": a}

    def export(self, d: dict) -> dict:
        m = _m()
        from .vaultkivul import vaultban_van
        self._szinkron_most()
        utak = d.get("utak")
        if utak is not None and (not isinstance(utak, list) or not all(isinstance(u, str) for u in utak)):
            raise Invalid("az `utak` kísérőjegyzet-utak listája")
        el = None
        if utak:
            el = {}
            for u in utak:
                f = self.app.vault.read(norm_path(u))
                el[nfc(f["ut"])] = m.formatum.elemez(f["tartalom"])
        kartyak = m.apkg.gyujt(self.cfg, el)
        cel = d.get("cel")
        szem = self.cfg.path("szemelyes") / "export"
        if cel is None:
            cel = szem / f"manifold-kartyak-{datetime.now().strftime('%Y%m%d-%H%M%S')}.apkg"
        elif not isinstance(cel, str) or not cel.endswith(".apkg") or not os.path.isabs(cel):
            raise Invalid("a `cel` egy abszolút `.apkg` út")
        cel = Path(cel)
        if vaultban_van(cel, self.cfg.path("vault")):
            raise Invalid("a csomag nem kerülhet a vaultba")
        from modulok.kartya import __main__ as cli
        media, hiany = cli._media(self.cfg, kartyak)
        b = m.szinkron.beallitas(self.cfg)
        jel = m.apkg.export(cel, kartyak, megtartas=float(b.get("megtartas", 0.9)), lepesszam=cli._lepesszam(self.cfg),
                            media=media)
        return {"ok": True, **jel, "feloldatlan_kepek": hiany}

    def importal(self, d: dict) -> dict:
        m = _m()
        fajl, proba = d.get("fajl"), d.get("proba", True)
        if not isinstance(fajl, str) or not os.path.isabs(fajl) or not fajl.lower().endswith((".apkg", ".colpkg")):
            raise Invalid("a `fajl` egy abszolút `.apkg` út")
        if not isinstance(proba, bool):
            raise Invalid("a `proba` igaz vagy hamis")
        from modulok.kartya import __main__ as cli
        try:
            p = m.apkg.beolvas(Path(fajl), cli._lepesszam(self.cfg))
        except (m.apkg.ApkgHiba, OSError) as e:
            raise Invalid(f"a csomag nem olvasható: {e}") from e
        jel = importal_eles(self.app, p, proba, Path(fajl))
        return {"ok": True, "proba": proba, **jel}


def _pakli_nev(nev: str) -> str:
    """Az Anki-pakli neve a kísérőjegyzet alapjához: az utolsó `::` utáni rész, a tiltott fájlnév-jelek nélkül."""
    import re
    n = (nev or "").split("::")[-1].strip()
    n = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", n)
    return re.sub(r"\s+", " ", n).strip()[:120] or "Anki"


MEDIA_LISTA_MAX = 200          # a jelentés okonkénti listáinak hossza (a darabszám mindig teljes)


def _vault_nevek(root: Path) -> dict[str, list[str]]:
    """A vault fájljainak neve → vault-relatív útjai (NFC + casefold kulcs; a rejtett mappák és fájlok nélkül): a beágyazás
    `![[név]]` a név szerint old fel (L42), ezért az ütközést a vault egészén nézzük, nem csak a célmappában."""
    ki: dict[str, list[str]] = {}
    for d, almappak, fajlok in os.walk(root):
        rejtett.metsz_munkater(almappak)         # a `.manifold` kimarad; a többi pontos mappát a következő sor, a `node_modules`-t semmi (v2)
        almappak[:] = [a for a in almappak if not a.startswith(".")]
        for f in fajlok:
            if not f.startswith("."):
                ki.setdefault(nfc(f).casefold(), []).append(nfc(os.path.relpath(os.path.join(d, f), root)))
    return ki


def _media_terv(app, p: dict, dontesek: list[dict], fajl: Path | None, tmp: Path) -> dict:
    """K308 (55(b), 83. döntés javaslata): a kártyák által hivatkozott csomag-média kicsomagolása a `tmp` alá, a vault-nevek kiosztása
    (a csatolmány-mappában, ütközésnél Obsidian-módra ` 1`, ` 2` utótaggal; a vaultban már álló, bájtra azonos fájl újrahasznosul), és
    a kártyák `![[…]]` hivatkozásainak átírása. A `dontesek` paklinként: {nev, ut (a kísérőjegyzet), kartyak}; ide kerül a pakli
    `behoz` műveleteinek listája. → a jelentés (`hozzaadva`, `atnevezve`, `mar_megvan`, `kihagyva`, `osszesites`)."""
    from . import binaris_naplo, csatolmany, gepi_iras
    m = _m()
    root = app.cfg.path("vault")
    jel = {"csomagban": len(p.get("media") or []), "hozzaadva": [], "atnevezve": [], "mar_megvan": [], "kihagyva": []}
    for d in dontesek:
        d["behoz"] = []
    nevek = list(p.get("media") or [])
    kulcs_nev: dict[str, str] = {}
    for n in nevek:
        kulcs_nev.setdefault(m.apkg.hivatkozas_kulcs(n), n)
    gazda: dict[str, int] = {}                       # csomagnév → az első hivatkozó pakli indexe
    for i, d in enumerate(dontesek):
        for k in d["kartyak"]:
            for ref in m.apkg.hivatkozasok(k["kerdes"] + "\n" + k["valasz"]):
                n = kulcs_nev.get(nfc(ref)) or kulcs_nev.get(nfc(urllib.parse.unquote(ref)))
                if n is not None:
                    gazda.setdefault(n, i)
    for n in nevek:
        if n not in gazda:
            jel["kihagyva"].append({"nev": n, "ok": "nem_hivatkozott"})
    if gazda and fajl is not None:
        ki = m.apkg.media_kicsomagol(fajl, tmp, set(gazda))
        jel["kihagyva"].extend(ki["kihagyva"])
        vault_nevek = _vault_nevek(root)
        terkep: dict[str, str] = {}
        for f in sorted(ki["fajlok"], key=lambda x: (gazda[x["nev"]], x["nev"])):
            d = dontesek[gazda[f["nev"]]]
            alap = m.apkg.vault_nev(f["nev"])
            if alap is None:
                jel["kihagyva"].append({"nev": f["nev"], "ok": "ervenytelen_nev"})
                continue
            try:
                cel_mappa = csatolmany.mappa(root, d["ut"])
            except Invalid:
                jel["kihagyva"].append({"nev": f["nev"], "ok": "csatolmany_mappa_ervenytelen"})
                continue
            if len(d["behoz"]) >= gepi_iras.MAX_BEHOZ:
                jel["kihagyva"].append({"nev": f["nev"], "ok": "tul_sok_media"})
                continue
            torzs, kit = os.path.splitext(alap)
            valasztott, ujrahasznal = None, None
            for j in range(1000):
                jelolt = alap if j == 0 else f"{torzs} {j}{kit}"
                talalat = vault_nevek.get(nfc(jelolt).casefold())
                if not talalat:
                    valasztott = jelolt
                    break
                meglevo = root / talalat[0]
                if len(talalat) == 1 and not meglevo.is_symlink() and meglevo.is_file():
                    try:
                        if binaris_naplo.kivonat(meglevo) == f["sha256"]:
                            valasztott, ujrahasznal = jelolt, talalat[0]
                            break
                    except OSError:
                        pass
            if valasztott is None:
                jel["kihagyva"].append({"nev": f["nev"], "ok": "nincs_szabad_nev"})
                continue
            terkep[m.apkg.hivatkozas_kulcs(f["nev"])] = valasztott
            if ujrahasznal is not None:
                jel["mar_megvan"].append({"nev": f["nev"], "ut": ujrahasznal})
                continue
            ut = f"{cel_mappa}/{valasztott}" if cel_mappa else valasztott
            vault_nevek[nfc(valasztott).casefold()] = [ut]
            d["behoz"].append({"tipus": "behoz", "forras": str(f["fajl"]), "ut": ut, "sha256": f["sha256"]})
            if valasztott == f["nev"]:
                jel["hozzaadva"].append({"nev": f["nev"], "ut": ut})
            else:
                jel["atnevezve"].append({"nev": f["nev"], "ut": ut,
                                         "ok": "utkozes" if valasztott != alap else "nev_tisztitva"})
        if terkep:
            for d in dontesek:
                for k in d["kartyak"]:
                    k["kerdes"] = m.apkg.hivatkozas_csere(k["kerdes"], terkep)
                    k["valasz"] = m.apkg.hivatkozas_csere(k["valasz"], terkep)
    osszesites: dict[str, int] = {}
    for x in jel["kihagyva"]:
        osszesites[x["ok"]] = osszesites.get(x["ok"], 0) + 1
    jel["osszesites"] = osszesites
    for kulcs in ("hozzaadva", "atnevezve", "mar_megvan", "kihagyva"):
        jel[f"{kulcs}_db"] = len(jel[kulcs])
        jel[kulcs] = jel[kulcs][:MEDIA_LISTA_MAX]
    return jel


def importal_eles(app, p: dict, proba: bool, fajl: Path | None = None) -> dict:
    """Az import (C23b, 4.2; K308): a csomag kártyái paklinként egy kísérőjegyzetbe (a már a vaultban élő saját kártyák kimaradnak),
    a kártyák által hivatkozott médiával együtt (`behoz`, a csatolmány-mappába), **egy gépi körben** (paklinként egy tétel: a
    kísérőjegyzet és a médiája együtt, így a visszavonás tételenként és körönként is mindkettőt viszi); utána az állapot és a napló.
    Próbában csak a terv: a médiát kicsomagolja és ellenőrzi (a jelentés kedvéért), de a vaulthoz és a DB-hez nem nyúl. A kicsomagoló
    mappa (a saját `{tmp}` fájljaink) a végén mindig törlődik."""
    import shutil
    import uuid

    from . import frame, gepi_iras, tanulas_db
    m = _m()
    cfg = app.cfg
    for k in p["kartyak"]:
        k["kerdes"] = " ".join(x.strip() for x in k["kerdes"].splitlines() if x.strip()) or "(üres kérdés)"
    el = m.szinkron.olvas_mappa(cfg)
    vaultban = {k.azon for e in el.values() for k in e.kartyak if k.azon}
    with tanulas_db.olvaso(cfg) as c:                  # a korábban importált idegen kártya ismert azonosítója (csak olvasva)
        if c is not None:
            for k in p["kartyak"]:
                if not k.get("azon"):
                    r = c.execute("SELECT kartya FROM apkg_kulcs WHERE guid = ? AND ord = ?", (k["guid"], k["ord"])).fetchone()
                    if r is not None:
                        k["azon"] = r[0]
    paklik: dict[str, list[dict]] = {}
    for k in p["kartyak"]:
        if k.get("azon") and k["azon"] in vaultban:
            continue
        paklik.setdefault(_pakli_nev(k.get("pakli", "")), []).append(k)
    mp = mappa(cfg)
    vault_utak = app.index.fajl_halmaz()
    dontesek = []
    for nev, ks in sorted(paklik.items()):
        meglevo = f"{mp}/{nev}{m.formatum.UTOTAG}.md"
        if any(nfc(u) == nfc(meglevo) for u in vault_utak):
            dontesek.append({"nev": nev, "ut": meglevo, "meglevo": True, "kartyak": ks})
        else:
            alap = m.formatum.kiseronev(f"{nev}.md", [u for u in vault_utak if u.lower().endswith(".md")])
            dontesek.append({"nev": nev, "ut": f"{mp}/{alap}.md", "meglevo": False, "kartyak": ks})
    tmp = gepi_iras.behoz_gyoker(cfg) / uuid.uuid4().hex
    try:
        media = _media_terv(app, p, dontesek, fajl, tmp)
        jel = {"kartyak": len(p["kartyak"]), "kihagyva": p.get("kihagyva", {}), "media": len(p.get("media") or []),
               "media_nem_importalt": media["kihagyva_db"], "media_jelentes": media,
               "kisero": [{"pakli": n, "kartyak": len(ks)} for n, ks in sorted(paklik.items())]}
        if proba:
            return jel
        m.apkg.azonositok_kioszt(cfg, p)
        kor = frame.new_id("KARTYA")                   # egy import = egy gépi kör (a visszavonás körre is szólhat)
        irasok = []
        for d in dontesek:
            kartyak = [m.formatum.Kartya(kerdes=k["kerdes"], valasz=k["valasz"], azon=k["azon"], forras=k.get("forras"))
                       for k in d["kartyak"]]
            if d["meglevo"]:
                f = app.vault.read(d["ut"])
                tartalom = f["tartalom"].rstrip("\n") + "\n\n" + "\n\n".join(m.formatum.ir_kartya(k) for k in kartyak) + "\n"
                muv = {"tipus": "csere", "ut": d["ut"], "tartalom": tartalom, "alap": f["hash"]}
            else:
                tartalom = m.formatum.ir(kartyak, source=[], modell="", keszult=date.today().isoformat())
                muv = {"tipus": "uj", "ut": d["ut"], "tartalom": tartalom, "osztaly": "kartya"}
            media_db = f", {len(d['behoz'])} médiafájl" if d["behoz"] else ""
            r = app.gepi.ir({"kor": kor, "tetel": d["ut"], "forras": "mos-kartya", "modell": None,
                             "uzenet": f"kártyák importja: {d['nev']} ({len(kartyak)}{media_db})"[:200],
                             "muveletek": [muv, *d["behoz"]]})
            irasok.append({"ut": d["ut"], "kartyak": len(kartyak), "sha": r.get("sha"), "kor": r.get("kor"),
                           "media": r.get("behozva", [])})
            m.szinkron.szinkron(cfg, {nfc(d["ut"]): m.formatum.elemez(tartalom)}, teljes=False, eredet="apkg")
        jel["irasok"] = irasok
        jel["allapot"] = m.apkg.importal(cfg, p)
        return jel
    finally:
        shutil.rmtree(tmp, ignore_errors=True)         # a saját `{tmp}` kicsomagoló mappánk (CLAUDE.md §4: a var/tmp saját fájljai)


def utvonalak(r) -> None:
    def api(k) -> KartyaApi:
        if getattr(k.app, "kartya_api", None) is None:
            k.app.kartya_api = KartyaApi(k.app)
        return k.app.kartya_api

    r.get("/api/kartya/allapot", lambda k: api(k).allapot(k.q))
    r.get("/api/kartya/esedekes", lambda k: api(k).esedekes(k.q))
    r.get("/api/kartya/jegyzet", lambda k: api(k).jegyzet(k.q))
    r.post("/api/kartya/valasz", lambda k: api(k).valasz(k.torzs()))
    r.post("/api/kartya/visszavon", lambda k: api(k).visszavon(k.torzs()))
    r.post("/api/kartya/export", lambda k: api(k).export(k.torzs()))
    r.post("/api/kartya/import", lambda k: api(k).importal(k.torzs()))
