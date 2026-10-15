"""Egy AI-kérés élő útja (C36b): a core gyermekfolyamatként hívja (`python -m modulok.cpp ai …`), mint a ⌘R-t.

    indul        {mod}
    ellenorzes   {fordit_ok, atment_db, ossz, bizonyitek}       (hiba / tipp / megoldas: a modell bemenete)
    modell       {modell, indok}                                 a router döntése (D9: csak kalibrált modell)
    generalas    {tokenek}                                       folyamatjelzés (másodpercenként legfeljebb egy)
    eredmeny     {mod, …}                                        az elemzett és homokozóban ellenőrzött javaslat
    kesz         {ok, mod, modell, ms, uzenet}
    hiba         {kod, uzenet}                                   nincs_kalibralt | csak_tavol | nincs_eszkoztar | megerosites_kell | …
    megszakitva  {}

A modell a workeren át fut (`MOS_WORKER_URL`; a feladat `kod`, a mód `interaktiv`, a keret `munka`), a kérés-beállítás a
regiszteré (`core.modell.eval.keres_beallitas`: ugyanaz, mint a mérésben). A modell kódja csak a program-homokozóban fordul és fut
(`ai_ellenorzes.py`, 53(b)); a motor semmit nem ír a vaultba és a `.cpp`-be (53(d)): a javaslatot a felület mutatja, elfogadni a
felhasználó tudja, egy szerkesztő-tranzakcióval.
"""
from __future__ import annotations

import time
from pathlib import Path

from core import cpp_teszt

from . import ai, ai_ellenorzes as AE
from . import ellenorzes as E
from .eszkoztar import beallitas

ALLAPOT_SZOVEG = {"hibas_kimenet": "hibás kimenet", "futasi_hiba": "futási hiba", "szanitizer": "a futásidejű ellenőrző hibát talált",
                  "idotullepes": "időtúllépés", "memoria": "memóriakorlát túllépve", "kimenet_tullepes": "túl sok kimenet",
                  "iras_korlat": "túl sok írás"}
TIPP_CIMEK = ("Irány", "Algoritmus", "Hely")
FELADAT = "kod"
KERET = "munka"
GENERALAS_JEL_S = 1.0


class Hiba(Exception):
    def __init__(self, kod: str, uzenet: str):
        super().__init__(uzenet)
        self.kod, self.uzenet = kod, uzenet


def _leiras(jegyzet_szoveg: str) -> str:
    """A feladat-jegyzet szövege a frontmatter és a megoldás-beágyazás nélkül (a modellnek a feladat kell, nem a vault-adat)."""
    s = jegyzet_szoveg.replace("\r\n", "\n")
    if s.startswith("---\n"):
        veg = s.find("\n---", 4)
        if veg != -1:
            s = s[veg + 4:].lstrip("\n")
    return "\n".join(sor for sor in s.split("\n") if not cpp_teszt.beagyazott_cpp(sor)).strip()


def bizonyitek_esemenyekbol(fordit: dict | None, tesztek_ki: list[dict], tesztek: list) -> dict | None:
    """Az ellenőrzés eseményeiből a modell bemenete: a fordító hibái, különben az első elbukó teszt (a sanitizer jelentésével).
    Minden átment → None."""
    if fordit is not None and not fordit.get("ok"):
        diag = [{"sor": d.get("sor"), "uzenet": d.get("uzenet", "")} for d in fordit.get("diagnosztika") or []
                if d.get("szint") in ("error", "fatal error")]
        if not diag:
            diag = [{"sor": None, "uzenet": fordit.get("uzenet") or fordit.get("kivonat") or "a fordítás nem sikerült"}]
        return {"fajta": "fordito", "diagnosztika": diag}
    szerint = {t.sorszam: t for t in tesztek}
    for e in tesztek_ki:
        if e.get("allapot") in ("atment", "hibas_teszt", "homokozo_hiba"):
            continue
        t = szerint.get(e.get("sorszam"))
        j = e.get("jelentes") or None
        return {"fajta": "szanitizer" if e["allapot"] == "szanitizer" else "teszt", "allapot": e["allapot"],
                "allapot_szoveg": ALLAPOT_SZOVEG.get(e["allapot"], e["allapot"]), "teszt": e.get("sorszam"),
                "bemenet": t.bemenet if t else None, "vart": t.kimenet if t else None,
                "kapott": e.get("stdout_kivonat") if e["allapot"] != "idotullepes" else None,
                "jelentes": {"leiras": j.get("leiras"), "sor": j.get("sor")} if j else None}
    return None


def bizonyitek_sorai(b: dict | None) -> set[int]:
    """A bizonyítékban megnevezett forrássorok (a fordító hibái, a sanitizer jelentése): ezzel „ellenőrzött” a hiba helye."""
    if not b:
        return set()
    ki = {d["sor"] for d in b.get("diagnosztika") or [] if d.get("sor")}
    if (b.get("jelentes") or {}).get("sor"):
        ki.add(int(b["jelentes"]["sor"]))
    return ki


class AIFutas:
    def __init__(self, cfg, *, esemeny=None, megszakit=None, worker_url: str | None = None, modell_hivo=None):
        """`modell_hivo(keres: dict, jelzes) -> (szöveg, modell_nev)`: a tesztek álmodellje; alapból a worker."""
        self.cfg = cfg
        self._esemeny = esemeny or (lambda _d: None)
        self.megszakit = megszakit or (lambda: False)
        self.worker_url = worker_url
        self.modell_hivo = modell_hivo or self._worker_hiv
        self.modell_nev: str | None = None

    def ki(self, szakasz: str, **adat) -> dict:
        d = {"szakasz": szakasz, **adat}
        self._esemeny(d)
        return d

    # ------------------------------------------------------------------ a modell

    def _worker_hiv(self, keres: dict, jelzes) -> tuple[str, str | None]:
        from core.kereses_modell import chat_folyam
        from core.modell import beallitas as B, kliens
        from core.modell.eval import keres_beallitas
        u = self.worker_url or kliens.url(self.cfg)
        try:
            d = kliens.keres(u, "/router/valaszt", {"feladat": FELADAT, "keret": KERET}, timeout=15)
        except kliens.KliensHiba as exc:
            if exc.adat.get("nincs_kalibralt"):
                raise Hiba("nincs_kalibralt", f"a C++ AI-hoz nincs kalibrált modell: {exc}") from None
            raise Hiba("worker_hiba", f"a modell-worker nem válaszol: {exc}") from None
        if d.get("var_tavolra") or not d.get("modell"):
            raise Hiba("csak_tavol", "a kalibrált kódmodell csak a távol-keretbe fér: akkor fut, ha nem dolgozol a gépen")
        nev = d["modell"]
        b = B.betolt(self.cfg)
        try:
            k = keres_beallitas(b, b.modell(nev), FELADAT, keres)
        except B.RegiszterHiba as exc:
            raise Hiba("nincs_kalibralt", f"a router modellje nincs a regiszterben: {exc}") from None
        body = {**k, "feladat": FELADAT, "mod": "interaktiv", "keret": KERET}
        reszek: list[str] = []
        folyam = chat_folyam(u, body, timeout=900)
        try:
            for e in folyam:
                if self.megszakit():
                    raise Hiba("megszakitva", "megszakítva")
                if e.get("tipus") == "token":
                    reszek.append(e.get("szoveg", ""))
                    jelzes(len(reszek))
                elif e.get("tipus") == "vege":
                    nev = e.get("modell") or nev
                    if e.get("proba"):
                        raise Hiba("nincs_kalibralt", "a worker próbaként futtatta a modellt: élesben csak kalibrált modell (D9)")
                elif e.get("tipus") == "hiba":
                    raise Hiba("modell_hiba", str(e.get("hiba") or "a generálás hibával állt meg"))
        except kliens.KliensHiba as exc:
            raise Hiba("nincs_kalibralt" if exc.adat.get("nincs_kalibralt") else "worker_hiba", str(exc)) from None
        finally:
            folyam.close()
        return "".join(reszek), nev

    def _modell(self, keres: dict) -> str:
        utolso = [0.0]

        def jelzes(n: int) -> None:
            most = time.monotonic()
            if most - utolso[0] >= GENERALAS_JEL_S:
                utolso[0] = most
                self.ki("generalas", tokenek=n)
        szoveg, nev = self.modell_hivo(keres, jelzes)
        self.modell_nev = nev
        self.ki("modell", modell=nev)
        return szoveg

    # ------------------------------------------------------------------ a futás

    def fut(self, mod: str, cpp: Path, jegyzet: Path | None = None, *, megerosit: bool = False) -> dict:
        kezd = time.monotonic()
        self.ki("indul", mod=mod)
        try:
            eredmeny = self._fut(mod, Path(cpp), Path(jegyzet) if jegyzet else None, megerosit)
        except Hiba as exc:
            if exc.kod == "megszakitva":
                self.ki("megszakitva")
            else:
                self.ki("hiba", kod=exc.kod, uzenet=exc.uzenet)
            return {"ok": False, "kod": exc.kod, "uzenet": exc.uzenet}
        self.ki("eredmeny", **eredmeny)
        d = {"ok": True, "mod": mod, "modell": self.modell_nev, "ms": round((time.monotonic() - kezd) * 1000), "uzenet": ""}
        self.ki("kesz", **d)
        return d

    def _fut(self, mod: str, cpp: Path, jegyzet: Path | None, megerosit: bool) -> dict:
        if mod not in ai.MODOK:
            raise Hiba("ismeretlen_mod", f"ismeretlen mód: {mod}")
        if mod == "megoldas" and not megerosit:
            raise Hiba("megerosites_kell", "a teljes megoldás csak külön megerősítéssel kérhető")
        try:
            kod = cpp.read_text(encoding="utf-8")
            jegyzet_szoveg = jegyzet.read_text(encoding="utf-8") if jegyzet else ""
        except OSError as exc:
            raise Hiba("nincs_forras", f"a fájl nem olvasható: {exc}") from None
        b = beallitas(self.cfg)
        tesztek = cpp_teszt.tesztek(jegyzet_szoveg, float(b["teszt_idokorlat_max_s"]),
                                    float(b["teszt_memoria_max_mb"])) if jegyzet_szoveg else []
        leiras = _leiras(jegyzet_szoveg) if jegyzet_szoveg else "(nincs feladat-jegyzet: csak a kód ismert)"
        with AE.Futtato(self.cfg, megszakit=self.megszakit) as f:
            h = f.hiany()
            if h:
                raise Hiba("nincs_eszkoztar", h)
            if mod in ("hiba", "tipp", "megoldas"):
                return self._javito(mod, f, kod, cpp, leiras, tesztek)
            if mod == "teszt":
                return self._teszt(f, kod, leiras, tesztek)
            return self._stressz(f, kod, leiras, tesztek)

    def _ellenoriz(self, cpp: Path, tesztek: list, mod: str) -> dict | None:
        fordit: dict = {}
        ki: list[dict] = []

        def gyujt(d: dict) -> None:
            if d["szakasz"] == "fordit_kesz":
                fordit.update(d["fordit"])
            elif d["szakasz"] == "teszt":
                ki.append(d["teszt"])
        r = E.Ellenorzes(self.cfg, esemeny=gyujt, megszakit=self.megszakit).fut(cpp, tesztek, mod)
        if self.megszakit():
            raise Hiba("megszakitva", "megszakítva")
        biz = bizonyitek_esemenyekbol(fordit or None, ki, tesztek)
        self.ki("ellenorzes", fordit_ok=bool(r.get("fordit_ok")), atment_db=r.get("atment_db", 0), ossz=r.get("tesztek_db", 0),
                bizonyitek=biz)
        return biz

    def _javito(self, mod: str, f, kod: str, cpp: Path, leiras: str, tesztek: list) -> dict:
        biz = self._ellenoriz(cpp, tesztek, "hibakereso" if mod == "hiba" else "gyors")
        if biz is None:
            return {"mod": mod, "nincs_hiba": True,
                    "uzenet": "A program lefordul, és minden teszten átmegy: nincs mit magyarázni." if tesztek else
                    "A program lefordul, de nincs teszt, amin hibát láthatnánk: írj `teszt` blokkot a jegyzetbe."}
        valasz = self._modell(ai.keres(mod, leiras, kod, biz))
        sorok = bizonyitek_sorai(biz)
        sor_db = len(kod.splitlines())
        if mod == "hiba":
            v = ai.hiba_valasz(valasz)
            ervenyes_sor = v["sor"] is not None and 1 <= v["sor"] <= sor_db
            return {"mod": mod, "sor": v["sor"] if ervenyes_sor else None, "fajta": v["fajta"],
                    "fajta_szoveg": ai.FAJTAK.get(v["fajta"] or "", None), "magyarazat": v["magyarazat"],
                    "ellenorzott": bool(ervenyes_sor and v["sor"] in sorok),
                    "magyar": ai.magyar_arany(v["magyarazat"]) >= 0.3}
        if mod == "tipp":
            v = ai.tipp_valasz(valasz)
            szintek = []
            for i, szoveg in enumerate(v["szintek"]):
                kiszurve = i in v["kod_szintek"]
                szintek.append({"szint": i + 1, "cim": TIPP_CIMEK[i], "szoveg": None if kiszurve else szoveg,
                                "kiszurve": kiszurve, "hianyzik": szoveg is None})
            hely = v["hely_sor"] if v["hely_sor"] and 1 <= v["hely_sor"] <= sor_db else None
            return {"mod": mod, "szintek": szintek, "hely_sor": hely, "ellenorzott": bool(hely and hely in sorok)}
        v = ai.megoldas_valasz(valasz)
        if not v["kod"]:
            return {"mod": mod, "kod": None, "magyarazat": v["magyarazat"], "ellenorzott": False,
                    "uzenet": "a válaszban nincs C++ kódblokk"}
        p = f.fordit(v["kod"], "megoldas")
        t = AE.teszt_futas(f, p, tesztek) if p.ok else {"atment_db": 0, "ossz": len(tesztek)}
        return {"mod": mod, "kod": v["kod"], "magyarazat": v["magyarazat"], "fordit": p.osszegzes(),
                "atment_db": t["atment_db"], "ossz": t["ossz"], "ellenorzott": bool(p.ok and t["ossz"] and t["atment_db"] == t["ossz"])}

    def _sajat(self, f, kod: str):
        p = f.fordit(kod, "sajat")
        return p if p.ok else None

    def _teszt(self, f, kod: str, leiras: str, tesztek: list) -> dict:
        valasz = self._modell(ai.keres("teszt", leiras, kod))
        v = ai.teszt_valasz(valasz)
        ref = AE.referencia(f, v["referencia"], tesztek)
        sajat = self._sajat(f, kod)
        esetek = AE.szelso_tesztek(f, v["bemenetek"], ref, sajat)
        for i, e in enumerate(esetek, 1):
            e["blokk"] = None
            if e["vart"] is not None:
                try:
                    e["blokk"] = cpp_teszt.teszt_blokk(f"Szélső eset {i} (AI)", e["bemenet"], e["vart"])
                except ValueError:
                    pass
        return {"mod": "teszt", "esetek": esetek, "referencia": _ref_ki(ref), "sajat_fordul": sajat is not None,
                "ellenorzott": bool(ref["ellenorzott"])}

    def _stressz(self, f, kod: str, leiras: str, tesztek: list) -> dict:
        valasz = self._modell(ai.keres("stressz", leiras, kod))
        v = ai.stressz_valasz(valasz)
        ref = AE.referencia(f, v["referencia"], tesztek)
        ki = {"mod": "stressz", "referencia": _ref_ki(ref), "ellenpelda": None, "menet": 0, "ellenorzott": bool(ref["ellenorzott"])}
        gen = f.fordit(v["generator"], "generator") if v["generator"] else None
        sajat = self._sajat(f, kod)
        if gen is None or not gen.ok:
            return {**ki, "uzenet": "a generátor hiányzik vagy nem fordul le", "generator": gen.osszegzes() if gen else None}
        if ref["program"] is None:
            return {**ki, "uzenet": ref["uzenet"]}
        if sajat is None:
            return {**ki, "uzenet": "a saját megoldásod nem fordul le: előbb javítsd a fordítási hibát (⌘R)"}
        s = AE.stressz(f, gen, ref["program"], sajat)
        e = s["ellenpelda"]
        if e is not None:
            try:
                e["blokk"] = cpp_teszt.teszt_blokk("Stressz-ellenpélda (AI)", e["bemenet"], e["vart"]) if ref["ellenorzott"] else None
            except ValueError:
                e["blokk"] = None
        return {**ki, "ellenpelda": e, "menet": s["menet"], "uzenet": s["hiba"]}


def _ref_ki(ref: dict) -> dict:
    return {"ellenorzott": ref["ellenorzott"], "atment_db": ref["atment_db"], "ossz": ref["ossz"], "uzenet": ref.get("uzenet", ""),
            "fordul": bool(ref.get("program"))}
