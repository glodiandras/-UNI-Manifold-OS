"""Az összefoglaló végpontjai (C26b; `docs/C26-TERV.md` 7. fejezet; CLAUDE.md 49. döntés): a kontextus-csomag a külső AI-nak, a
visszamásolt válasz feldolgozása, és az összefoglaló-jegyzet elemzése a beágyazott megjelenítéshez. **Mindhárom csak olvas**: a
vaultba nem írnak, modellt nem hívnak. Az összefoglaló *készítése* a `osszefoglalas` / `osszefoglalas_automatikus` feladat
(`core/osszefoglalas_feladat.py`, `POST /api/feladatok`), amely a gépi-írás szolgáltatáson át ír.

- `POST /api/osszefoglalas/kontextus {utak, kerdes?, max_karakter?}` → `{szoveg, azonositok, benne, csonkolt, kihagyott, karakter}`:
  a kijelölt jegyzetek tisztított szövege azonosítókkal (`J1`, `J2`, …), **útvonal nélkül** (49(d)); az azonosító → út leképezés a
  válaszban van, a felület helyben tartja;
- `POST /api/osszefoglalas/valasz {utak, valasz, cim?}` → `{allitasok, elvetett, torzs, jegyzet, statisztika}`: a visszamásolt külső AI
  válasza a közös forráshűség-kapun át (az `utak` sorrendje ugyanaz, mint a csomagnál: a `J<n>` a sorszám). A `torzs` az `## Állítások`
  blokk — **a felhasználó kézzel illeszti a szerkesztőbe** (49(c): a külső AI kalibrálatlan, gép nem ír belőle a vaultba);
- `GET /api/osszefoglalas/jegyzet?ut=` → az összefoglaló-jegyzet elemzése: állítások, hibák és a **sodródás** (a forrásjegyzet azóta
  megváltozott: `sodrodott`), a horgony és a forrás hiánya. Csak az `[osszefoglalas] mappa` alatti `.md`-re.

- `GET /api/osszefoglalas/mappa-terv?ut=&kiegeszit=` → `{jegyzetek, van, hianyzik, keszul, tetelek}`: a mappa-szintű kérés terve — hány
  hiányzó jegyzet-összefoglaló készülne el előbb (egy kérésben legfeljebb `mappa_max_uj`, összesen legfeljebb 5 gépi írás); a felület ezt
  mutatja indítás előtt.

A `modulok` csomag importja lusta: egy hibás modul a core indulását nem viheti el.
"""
from __future__ import annotations

from types import SimpleNamespace

from .utvonalak import HttpError
from .vaultio import Invalid, NotFound, nfc, norm_path

MAX_UT = 30
MAX_VALASZ = 200_000
MAX_KERDES = 2000
_modulok: SimpleNamespace | None = None


def _m() -> SimpleNamespace:
    global _modulok
    if _modulok is None:
        from modulok.osszefoglalas import ellenorzes, formatum, futtat, kontextus, lanc
        _modulok = SimpleNamespace(ellenorzes=ellenorzes, formatum=formatum, futtat=futtat, kontextus=kontextus, lanc=lanc)
    return _modulok


def mappa(cfg) -> str:
    return nfc(cfg.section("osszefoglalas").get("mappa", "ATTCHMNTS - summaries")).strip("/")


class OsszefoglalasApi:
    def __init__(self, app):
        self.app = app

    @property
    def cfg(self):
        return self.app.cfg

    def _jegyzetek(self, utak) -> list:
        if not isinstance(utak, list) or not 1 <= len(utak) <= MAX_UT or not all(isinstance(u, str) for u in utak):
            raise Invalid(f"Az `utak` 1–{MAX_UT} jegyzet vault-relatív útja legyen.")
        K = _m().kontextus
        ki, latott = [], set()
        for u in utak:
            rp = norm_path(u)
            if not rp.lower().endswith(".md"):
                raise Invalid(f"nem jegyzet: {rp}")
            if rp.casefold() in latott:
                raise Invalid(f"a jegyzet kétszer szerepel: {rp}")
            latott.add(rp.casefold())
            f = self.app.vault.read(rp)
            ki.append(K.Jegyzet(f["ut"], f["tartalom"]))
        return ki

    # -------------------------------------------------- végpontok

    def kontextus(self, d: dict) -> dict:
        m = _m()
        jegyzetek = self._jegyzetek(d.get("utak"))
        kerdes = d.get("kerdes", "")
        if not isinstance(kerdes, str) or len(kerdes) > MAX_KERDES:
            raise Invalid(f"A `kerdes` legfeljebb {MAX_KERDES} karakteres szöveg legyen.")
        b = m.lanc.beallitas(self.cfg)
        maxk = d.get("max_karakter", b.kontextus_max_karakter)
        if isinstance(maxk, bool) or not isinstance(maxk, int) or not 1000 <= maxk <= 400_000:
            raise Invalid("A `max_karakter` 1000 és 400000 közötti egész legyen.")
        try:
            cs = m.kontextus.csomag(jegyzetek, maxk, kerdes)
        except m.lanc.Megall as exc:
            raise HttpError(422, str(exc)) from None
        return {"ok": True, "szoveg": cs.szoveg, "azonositok": cs.azonositok, "benne": cs.benne, "csonkolt": cs.csonkolt,
                "kihagyott": cs.kihagyott, "karakter": cs.karakter}

    def valasz(self, d: dict) -> dict:
        m = _m()
        jegyzetek = self._jegyzetek(d.get("utak"))
        valasz = d.get("valasz")
        if not isinstance(valasz, str) or not valasz.strip() or len(valasz) > MAX_VALASZ:
            raise Invalid(f"A `valasz` a külső AI visszamásolt válasza legyen (legfeljebb {MAX_VALASZ} karakter).")
        cim = d.get("cim", "Kontextus")
        if not isinstance(cim, str) or not cim.strip() or "\n" in cim or len(cim) > 200:
            raise Invalid("A `cim` egysoros, legfeljebb 200 karakteres szöveg legyen.")
        b = m.lanc.beallitas(self.cfg)
        e = m.kontextus.valasz_feldolgoz(valasz, jegyzetek, cim=cim.strip(), b=b, p=m.lanc.profil(self.cfg))
        o = e.osszefoglalo
        ki = {"ok": True, "allitasok": len(o.allitasok), "elvetett": e.elvetett, "statisztika": e.statisztika, "torzs": "", "jegyzet": ""}
        if o.allitasok:
            ki["torzs"], ki["jegyzet"] = m.formatum.torzs(o), m.formatum.ir(o)
        return ki

    def jegyzet(self, q: dict) -> dict:
        m = _m()
        ut = q.get("ut")
        if not isinstance(ut, str) or not ut.strip():
            raise Invalid("hiányzik az `ut`")
        rp = norm_path(ut)
        if not rp.lower().endswith(".md"):
            raise Invalid(f"nem jegyzet: {rp}")
        if not nfc(rp).startswith(mappa(self.cfg) + "/"):
            raise Invalid(f"Összefoglaló-jegyzet csak a „{mappa(self.cfg)}” mappából olvasható: {rp}")
        f = self.app.vault.read(rp)

        def olvas(r: str):
            try:
                return self.app.vault.read(r)["tartalom"]
            except (NotFound, Invalid):
                return None

        def letezik(r: str) -> bool:
            try:
                return self.app.vault.lemezen(norm_path(r)).is_file()
            except (NotFound, Invalid):
                return False

        ki, _ = m.ellenorzes.vizsgal(f["tartalom"], olvas, letezik, m.lanc.beallitas(self.cfg))
        reszletek = ki.pop("reszletek", [])
        forrasok = ki.get("forrasok") or []
        szint = ki.get("szint")
        return {"ok": True, "ut": f["ut"], "szint": szint, "cim": ki.get("cim"), "azon": ki.get("azon"), "modell": ki.get("modell"),
                "keszult": ki.get("keszult"), "forrasok": forrasok,
                "forras_ut": (forrasok[0] + ".md") if szint == "jegyzet" and forrasok else None,
                "allitasok": reszletek, "hibak": ki["hibak"], "sodrodott": ki.get("sodrodott", []),
                "horgony_hianyzik": ki.get("horgony_hianyzik", []), "forras_hianyzik": ki.get("forras_hianyzik", [])}


    def mappa_terv(self, q: dict) -> dict:
        m = _m()
        ut = q.get("ut")
        if not isinstance(ut, str) or not ut.strip() or ut.lower().endswith(".md"):
            raise Invalid("Az `ut` a vault egy mappájának relatív útja legyen.")
        rp = norm_path(ut.strip().rstrip("/"))
        from .automatika import kisero_elotag                     # lusta import: az automatika nem függ az API-tól
        if nfc(rp).startswith(nfc(kisero_elotag(self.cfg))):
            raise Invalid("Gépi kísérőjegyzet-mappából nem készül mappa-összefoglaló.")
        try:
            terv = m.futtat.mappa_terv(self.cfg, rp, q.get("kiegeszit", "1") not in ("0", "false", "nem"))
        except m.lanc.Megall as exc:
            raise NotFound(str(exc)) from None
        return {"ok": True, **terv}


def utvonalak(r) -> None:
    def api(k) -> OsszefoglalasApi:
        if getattr(k.app, "osszefoglalas_api", None) is None:
            k.app.osszefoglalas_api = OsszefoglalasApi(k.app)
        return k.app.osszefoglalas_api

    r.post("/api/osszefoglalas/kontextus", lambda k: api(k).kontextus(k.torzs()))
    r.post("/api/osszefoglalas/valasz", lambda k: api(k).valasz(k.torzs()))
    r.get("/api/osszefoglalas/jegyzet", lambda k: api(k).jegyzet(k.q))
    r.get("/api/osszefoglalas/mappa-terv", lambda k: api(k).mappa_terv(k.q))
