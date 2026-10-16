"""A „Megoldás” lánca (C24b): a feladat-lépés I/O-ja — a jegyzet olvasása a core-tól, a modell a workeren át, a callout a gépi-írás
szolgáltatáson át (28., 56. döntés). A CAS-rész a `megoldas.py`-é (homokozóban), ez a modul csak összeköt.

    futtat(ut=…, tol=…, ig=…, feladat=…, gepi=gepi_kliens, worker=Worker(cfg), homokozo=Homokozo(cfg)) → összegzés

D9 (56(b)): élesen csak a `matek_cas` router-feladat kalibrált modellje fut (a worker routere ezt adja); a kifejezett modell (próba) a worker
`proba` jelét viszi, és akkor az egész írás `proba: true` (APFS-klón). A második vélemény független kérés `kizart_csalad`-dal; ha nincs másik
családú kalibrált modell, a callout ezt kimondja („nincs második vélemény”), és az első megoldás íródik. A második vélemény próba-modellje is
próbává teszi az írást.
"""
from __future__ import annotations

from . import megoldas as M

FELADAT = "matek_cas"
FORRAS = "mos-matek"
KOR_ELOTAG = "MATEK"


class Megall(Exception):
    """A megoldás nem készülhet el — az üzenet a felhasználónak szól (a feladatsor hibaként mutatja)."""


class Worker:
    """A worker a `core.modell.kliens`-en át; a kérés-beállítás (gondolkodás, token-keret) a regiszterből, a mérés szabályával
    (`core.modell.eval.keres_beallitas`): az éles kérés ugyanaz, mint a mért."""

    def __init__(self, cfg):
        from core.modell import beallitas as B
        from core.modell import kliens
        self.kliens = kliens
        self.b = B.betolt(cfg)
        self.u = kliens.url(cfg)

    def csalad(self, nev: str) -> str:
        return self.b.modell(nev).csalad

    def valaszt(self, kizart_csalad: str | None = None) -> dict:
        """A router száraz döntése → `{modell, var_tavolra, indok}`; nincs kalibrált modell: `KliensHiba` (409)."""
        body = {"feladat": FELADAT}
        if kizart_csalad:
            body["kizart_csalad"] = kizart_csalad
        return self.kliens.keres(self.u, "/router/valaszt", body)

    def kerdez(self, feladat_szoveg: str, modell: str, *, kifejezett: bool, kizart_csalad: str | None = None) -> dict:
        from core.modell import eval as E
        k = E.keres_beallitas(self.b, self.b.modell(modell), FELADAT, {"tipus": "chat", **M.keres(feladat_szoveg)})
        uzenetek = k.pop("messages")
        k.pop("tipus", None)
        if kizart_csalad and not kifejezett:
            k["kizart_csalad"] = kizart_csalad
        return self.kliens.chat(self.u, uzenetek, feladat=FELADAT, modell=modell if kifejezett else None, **k)


def _hibakod(exc) -> int | None:
    return getattr(exc, "kod", None)


def futtat(*, ut: str, tol: int, ig: int, feladat: str, gepi, worker, homokozo, proba: bool = False,
           modell: str | None = None, masodik_modell: str | None = None, masodik: bool = True,
           allj=lambda: False, naplo=lambda s: None) -> dict:
    d = gepi.olvas(ut)
    if M.feladat_sorai(d["tartalom"], tol, ig) != feladat:
        raise Megall("A feladat sorai a jegyzetben megváltoztak az indítás óta — jelöld ki újra, és indítsd újra.")

    # 1. az első megoldás (kalibrált modell a routerből, vagy kifejezett próba-modell)
    if modell is None:
        try:
            dont = worker.valaszt()
        except Exception as exc:  # noqa: BLE001 — a worker hibája üzenetként
            if _hibakod(exc) == 409:
                raise Megall(f"A `{FELADAT}` feladatra nincs kalibrált modell: élesen nem írható megoldás. Próbához adj meg "
                             f"modellt (`modell`, a kimenet a vault klónjára kerül). ({exc})") from None
            raise
        if not dont.get("modell"):
            raise Megall(f"A megoldás modellje most nem futhat: {dont.get('indok') or 'a távol-keretre vár'}.")
        m1 = dont["modell"]
    else:
        m1 = modell
    naplo(f"megoldás: {m1}")
    v1 = worker.kerdez(feladat, m1, kifejezett=modell is not None)
    jel1 = gepi.modell_jel(v1)
    if allj():
        raise Megall("Leállítva.")

    # 2. második vélemény: független kérés másik családból
    v2, m2, masodik_ok = None, None, None
    if masodik:
        csalad1 = worker.csalad(v1["modell"])
        if masodik_modell:
            if worker.csalad(masodik_modell) == csalad1:
                raise Megall(f"A második vélemény modellje ({masodik_modell}) ugyanabból a családból ({csalad1}) való.")
            m2, kifejezett2 = masodik_modell, True
        else:
            kifejezett2 = False
            try:
                dont = worker.valaszt(kizart_csalad=csalad1)
                m2 = dont.get("modell")
                if not m2:
                    masodik_ok = dont.get("indok") or "a másik családú modell a távol-keretre vár"
            except Exception as exc:  # noqa: BLE001
                if _hibakod(exc) != 409:
                    raise
                masodik_ok = f"nincs kalibrált második család (a {csalad1} családon kívül)"
        if m2:
            naplo(f"második vélemény: {m2}")
            try:
                v2 = worker.kerdez(feladat, m2, kifejezett=kifejezett2, kizart_csalad=csalad1)
                m2 = v2.get("modell") or m2
            except Exception as exc:  # noqa: BLE001 — a második vélemény hibája nem viszi el az elsőt
                v2, masodik_ok = None, f"a második modell hibája: {str(exc)[:160]}"
    else:
        masodik_ok = "kikapcsolva"
    if allj():
        raise Megall("Leállítva.")

    # 3. CAS-ellenőrzés a homokozóban, összevetés
    e1 = M.ellenoriz(v1, homokozo)
    e2 = M.ellenoriz(v2, homokozo) if v2 is not None else None
    cmp = M.osszevet(e1, e2, homokozo)
    iras_proba = bool(proba or jel1.get("proba") or (v2 is not None and v2.get("proba")))
    blokk = M.callout(e1, e2, cmp, modell=v1["modell"], masodik_modell=m2 if v2 is not None else None,
                      masodik_ok=masodik_ok, proba=iras_proba)
    uj = M.beszur(d["tartalom"], ig, blokk)

    # 4. gépi írás: egy tétel = egy gépi commit
    kor = gepi.uj_kor(KOR_ELOTAG)
    r = gepi.ir(kor, tetel=ut, forras=FORRAS, muveletek=[gepi.csere(ut, uj, d["hash"])],
                uzenet=f"megoldás: {ut}"[:200], proba=iras_proba, modell=jel1)
    return {"ok": True, "ut": ut, "kor": kor, "sha": r.get("sha"), "proba": iras_proba, "modell": v1["modell"],
            "ellenorzott": e1["ellenorzott"], "ok_szoveg": e1.get("ok"),
            "masodik": ({"modell": m2, "ellenorzott": e2["ellenorzott"], "egyezik": cmp.get("egyezik")} if e2 else
                        {"nincs": masodik_ok})}
