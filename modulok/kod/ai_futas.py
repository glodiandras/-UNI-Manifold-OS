"""F10: one AI request of the code workbench, for any language profile (the core runs it as a child process:
`python -m modulok.kod ai <mode> <source> …`). The events (JSON lines):

    indul        {mod, nyelv}
    ellenorzes   {fordit_ok, atment_db, ossz, bizonyitek}       (hiba / tipp / megoldas: the model's input)
    modell       {modell, proba, kalibracios_kulcs, indok}      the D9 decision (see below)
    generalas    {tokenek}                                       progress (at most once a second)
    eredmeny     {mod, proba, …}                                 the parsed answer, its code checked in the sandbox
    kesz         {ok, mod, modell, proba, ms, uzenet}
    hiba         {kod, param, uzenet}                            kod.nincs_kalibralt | kod.csak_tavol | kod.nincs_eszkozlanc | …
    megszakitva  {}

**D9 — measured AI.** The router task is the profile's own calibration key (`kod` for C++, `kod_python`, `kod_java`, …).
A calibrated model of that key runs for real (`proba: false`). Without one, the request may only run as a **trial**
(`proba: true`): the `[kod] proba_modell` registry model if set, else the calibrated C++ (`kod`) model on the other
language; a trial is labelled, its result is a suggestion only (the engine never writes; the UI shows it, only the user
can accept it). No calibrated row and no trial candidate → `kod.nincs_kalibralt`. The gate is not weakened: a "real"
request that the worker reports as a trial is refused.

The model's code runs only in the sandbox (`futtato.py`); nothing is written to the vault or the source.
"""
from __future__ import annotations

import time
from pathlib import Path

from core import cpp_teszt
from core import kod_nyelvek as KN
from modulok.cpp import ai_ellenorzes as AE
from modulok.cpp.ai_futas import bizonyitek_esemenyekbol, bizonyitek_sorai

from . import ai
from .ellenorzes import Ellenorzes
from .futtato import Futtato

KERET = "munka"
GENERALAS_JEL_S = 1.0
TIPP_CIMEK = ("Direction", "Algorithm", "Location")
ALLAPOT_SZOVEG = {"hibas_kimenet": "wrong output", "futasi_hiba": "runtime error", "szanitizer": "the runtime checker found an error",
                  "idotullepes": "time limit exceeded", "memoria": "memory limit exceeded", "kimenet_tullepes": "too much output",
                  "iras_korlat": "too much writing"}


def _leiras(jegyzet_szoveg: str) -> str:
    """The task note without its frontmatter and the embedded solution (the model needs the task, not vault data)."""
    s = jegyzet_szoveg.replace("\r\n", "\n")
    if s.startswith("---\n"):
        veg = s.find("\n---", 4)
        if veg != -1:
            s = s[veg + 4:].lstrip("\n")
    return "\n".join(sor for sor in s.split("\n") if not KN.beagyazott_forrasok(sor)).strip()


class Hiba(Exception):
    def __init__(self, kod: str, uzenet: str, **param):
        super().__init__(uzenet)
        self.kod, self.uzenet, self.param = kod, uzenet, param


class AIFutas:
    def __init__(self, cfg, profil: KN.Profil, *, esemeny=None, megszakit=None, worker_url: str | None = None,
                 modell_hivo=None, dontes=None, felderites=None, homokozo=None):
        """`dontes() -> {modell, proba, feladat, indok}` and `modell_hivo(keres, dontes, jelzes) -> (text, model)`: the
        tests' fakes; by default the worker."""
        self.cfg = cfg
        self.p = profil
        self._esemeny = esemeny or (lambda _d: None)
        self.megszakit = megszakit or (lambda: False)
        self.worker_url = worker_url
        self.modell_hivo = modell_hivo or self._worker_hiv
        self.dontes_fv = dontes or self._dontes
        self.felderites, self.homokozo = felderites, homokozo
        self.modell_nev: str | None = None
        self.proba = False

    def ki(self, szakasz: str, **adat) -> dict:
        d = {"szakasz": szakasz, "nyelv": self.p.azonosito, **adat}
        self._esemeny(d)
        return d

    # ------------------------------------------------------------------ D9: which model, real or trial

    def _url(self) -> str:
        from core.modell import kliens
        return self.worker_url or kliens.url(self.cfg)

    def _valaszt(self, feladat: str) -> dict | None:
        """The router's decision for a task; no calibrated row → None."""
        from core.modell import kliens
        try:
            d = kliens.keres(self._url(), "/router/valaszt", {"feladat": feladat, "keret": KERET}, timeout=15)
        except kliens.KliensHiba as exc:
            if exc.adat.get("nincs_kalibralt"):
                return None
            raise Hiba("kod.worker_hiba", f"The model worker does not answer: {exc}", hiba=str(exc)) from None
        if d.get("var_tavolra") or not d.get("modell"):
            raise Hiba("kod.csak_tavol", "The calibrated code model only fits the away budget: it runs when you are not "
                       "working on the machine.", feladat=feladat)
        return d

    def _dontes(self) -> dict:
        kulcs = self.p.kalibracios_kulcs
        d = self._valaszt(kulcs)
        if d is not None:
            return {"modell": d["modell"], "proba": False, "feladat": kulcs, "indok": d.get("indok") or "calibrated"}
        nev = str(KN.beallitasok(self.cfg).get("proba_modell") or "")
        if nev:
            return {"modell": nev, "proba": True, "feladat": kulcs,
                    "indok": f"no calibrated model for {kulcs}: the trial model of [kod] proba_modell"}
        if kulcs != "kod":
            d = self._valaszt("kod")
            if d is not None:
                return {"modell": d["modell"], "proba": True, "feladat": kulcs,
                        "indok": f"no calibrated model for {kulcs}: the calibrated C++ model as a trial"}
        raise Hiba("kod.nincs_kalibralt", f"There is no calibrated model for {self.p.nev} ({kulcs}) and no trial model. "
                   "Settings › AI › Calibration.", nyelv=self.p.nev, kulcs=kulcs)

    def _worker_hiv(self, keres: dict, dontes: dict, jelzes) -> tuple[str, str | None]:
        from core.kereses_modell import chat_folyam
        from core.modell import beallitas as B, kliens
        from core.modell.eval import keres_beallitas
        nev = dontes["modell"]
        b = B.betolt(self.cfg)
        try:
            m = b.modell(nev)
        except B.RegiszterHiba as exc:
            raise Hiba("kod.nincs_kalibralt", f"The model is not in the registry: {exc}", modell=nev) from None
        k = keres_beallitas(b, m, dontes["feladat"], keres)
        body = {**k, "mod": "interaktiv", "keret": KERET}
        if dontes["proba"]:
            body.update(model=nev, proba=True)
        else:
            body["feladat"] = dontes["feladat"]
        reszek: list[str] = []
        folyam = chat_folyam(self._url(), body, timeout=900)
        try:
            for e in folyam:
                if self.megszakit():
                    raise Hiba("kod.megszakitva", "interrupted")
                if e.get("tipus") == "token":
                    reszek.append(e.get("szoveg", ""))
                    jelzes(len(reszek))
                elif e.get("tipus") == "vege":
                    nev = e.get("modell") or nev
                    if e.get("proba") and not dontes["proba"]:
                        raise Hiba("kod.nincs_kalibralt", "The worker ran the model as a trial: a real request needs a "
                                   "calibrated model.", modell=nev)
                elif e.get("tipus") == "hiba":
                    raise Hiba("kod.modell_hiba", str(e.get("hiba") or "the generation stopped with an error"))
        except kliens.KliensHiba as exc:
            raise Hiba("kod.nincs_kalibralt" if exc.adat.get("nincs_kalibralt") else "kod.worker_hiba", str(exc)) from None
        finally:
            folyam.close()
        return "".join(reszek), nev

    def _modell(self, keres: dict) -> str:
        dontes = self.dontes_fv()
        self.proba = bool(dontes["proba"])
        self.ki("modell", modell=dontes["modell"], proba=self.proba, kalibracios_kulcs=self.p.kalibracios_kulcs,
                indok=dontes.get("indok", ""))
        utolso = [0.0]

        def jelzes(n: int) -> None:
            most = time.monotonic()
            if most - utolso[0] >= GENERALAS_JEL_S:
                utolso[0] = most
                self.ki("generalas", tokenek=n)
        szoveg, nev = self.modell_hivo(keres, dontes, jelzes)
        self.modell_nev = nev
        return szoveg

    # ------------------------------------------------------------------ the run

    def fut(self, mod: str, forras: Path, jegyzet: Path | None = None, *, megerosit: bool = False) -> dict:
        kezd = time.monotonic()
        self.ki("indul", mod=mod)
        try:
            eredmeny = self._fut(mod, Path(forras), Path(jegyzet) if jegyzet else None, megerosit)
        except Hiba as exc:
            if exc.kod == "kod.nincs_kalibralt":
                exc.param.setdefault("nyelv", self.p.nev)
                exc.param.setdefault("kulcs", self.p.kalibracios_kulcs)
            if exc.kod == "kod.megszakitva":
                self.ki("megszakitva")
            else:
                self.ki("hiba", kod=exc.kod, param=exc.param, uzenet=exc.uzenet)
            return {"ok": False, "kod": exc.kod, "uzenet": exc.uzenet}
        self.ki("eredmeny", proba=self.proba, **eredmeny)
        d = {"ok": True, "mod": mod, "modell": self.modell_nev, "proba": self.proba,
             "ms": round((time.monotonic() - kezd) * 1000), "uzenet": ""}
        self.ki("kesz", **d)
        return d

    def _fut(self, mod: str, forras: Path, jegyzet: Path | None, megerosit: bool) -> dict:
        if mod not in ai.MODOK:
            raise Hiba("kod.ismeretlen_mod", f"Unknown mode: {mod}", mod=mod)
        if mod == "megoldas" and not megerosit:
            raise Hiba("kod.megerosites_kell", "The full solution can only be requested with a separate confirmation.")
        try:
            kod = forras.read_text(encoding="utf-8")
            jegyzet_szoveg = jegyzet.read_text(encoding="utf-8") if jegyzet else ""
        except OSError as exc:
            raise Hiba("kod.nincs_forras", f"The file is not readable: {exc}") from None
        b = KN.beallitasok(self.cfg)
        tesztek = cpp_teszt.tesztek(jegyzet_szoveg, float(b["teszt_idokorlat_max_s"]),
                                    float(b["teszt_memoria_max_mb"])) if jegyzet_szoveg else []
        leiras = _leiras(jegyzet_szoveg) if jegyzet_szoveg else "(no task note: only the code is known)"
        with Futtato(self.cfg, self.p, felderites=self.felderites, homokozo=self.homokozo, megszakit=self.megszakit) as f:
            h = f.hiany()
            if h:
                raise Hiba(h["kod"], h["uzenet"], **h["param"])
            if mod in ("hiba", "tipp", "megoldas"):
                return self._javito(mod, f, kod, forras, leiras, tesztek)
            if mod == "teszt":
                return self._teszt(f, kod, leiras, tesztek)
            return self._stressz(f, kod, leiras, tesztek)

    def _ellenoriz(self, forras: Path, tesztek: list, mod: str) -> dict | None:
        fordit: dict = {}
        ki: list[dict] = []

        def gyujt(d: dict) -> None:
            if d["szakasz"] == "fordit_kesz":
                fordit.update(d["fordit"])
            elif d["szakasz"] == "teszt":
                ki.append(d["teszt"])
        r = Ellenorzes(self.cfg, self.p, esemeny=gyujt, megszakit=self.megszakit, felderites=self.felderites,
                       homokozo=self.homokozo).fut(forras, tesztek, mod)
        if self.megszakit():
            raise Hiba("kod.megszakitva", "interrupted")
        biz = bizonyitek_esemenyekbol(fordit or None, ki, tesztek)
        if biz and biz.get("allapot"):
            biz["allapot_szoveg"] = ALLAPOT_SZOVEG.get(biz["allapot"], biz["allapot"])
        self.ki("ellenorzes", fordit_ok=bool(r.get("fordit_ok")), atment_db=r.get("atment_db", 0), ossz=r.get("tesztek_db", 0),
                bizonyitek=biz)
        return biz

    def _javito(self, mod: str, f: Futtato, kod: str, forras: Path, leiras: str, tesztek: list) -> dict:
        ell_mod = "hibakereso" if mod == "hiba" and self.p.motor == "cpp" else "gyors"
        biz = self._ellenoriz(forras, tesztek, ell_mod)
        if biz is None:
            return {"mod": mod, "nincs_hiba": True, "kod_uzenet": "kod.nincs_hiba" if tesztek else "kod.nincs_teszt",
                    "uzenet": "The program compiles and passes every test: there is nothing to explain." if tesztek else
                    "The program compiles, but there is no test that could show a bug: add a `teszt` block to the note."}
        valasz = self._modell(ai.keres(self.p, mod, leiras, kod, biz))
        sorok = bizonyitek_sorai(biz)
        sor_db = len(kod.splitlines())
        if mod == "hiba":
            v = ai.hiba_valasz(self.p, valasz)
            jo_sor = v["sor"] is not None and 1 <= v["sor"] <= sor_db
            return {"mod": mod, "sor": v["sor"] if jo_sor else None, "fajta": v["fajta"],
                    "fajta_szoveg": ai.FAJTAK.get(v["fajta"] or "", None), "magyarazat": v["magyarazat"],
                    "ellenorzott": bool(jo_sor and v["sor"] in sorok)}
        if mod == "tipp":
            v = ai.tipp_valasz(self.p, valasz)
            szintek = []
            for i, szoveg in enumerate(v["szintek"]):
                kiszurve = i in v["kod_szintek"]
                szintek.append({"szint": i + 1, "cim": TIPP_CIMEK[i], "szoveg": None if kiszurve else szoveg,
                                "kiszurve": kiszurve, "hianyzik": szoveg is None})
            hely = v["hely_sor"] if v["hely_sor"] and 1 <= v["hely_sor"] <= sor_db else None
            return {"mod": mod, "szintek": szintek, "hely_sor": hely, "ellenorzott": bool(hely and hely in sorok)}
        v = ai.megoldas_valasz(self.p, valasz)
        if not v["kod"]:
            return {"mod": mod, "kod": None, "magyarazat": v["magyarazat"], "ellenorzott": False,
                    "kod_uzenet": "kod.nincs_kodblokk", "uzenet": f"The answer has no {self.p.nev} code block."}
        p = f.fordit(v["kod"], "megoldas")
        t = AE.teszt_futas(f, p, tesztek) if p.ok else {"atment_db": 0, "ossz": len(tesztek)}
        return {"mod": mod, "kod": v["kod"], "magyarazat": v["magyarazat"], "fordit": p.osszegzes(),
                "atment_db": t["atment_db"], "ossz": t["ossz"],
                "ellenorzott": bool(p.ok and t["ossz"] and t["atment_db"] == t["ossz"])}

    def _sajat(self, f: Futtato, kod: str):
        p = f.fordit(kod, "sajat")
        return p if p.ok else None

    def _teszt(self, f: Futtato, kod: str, leiras: str, tesztek: list) -> dict:
        v = ai.teszt_valasz(self.p, self._modell(ai.keres(self.p, "teszt", leiras, kod)))
        ref = AE.referencia(f, v["referencia"], tesztek)
        sajat = self._sajat(f, kod)
        esetek = AE.szelso_tesztek(f, v["bemenetek"], ref, sajat)
        for i, e in enumerate(esetek, 1):
            e["blokk"] = None
            if e["vart"] is not None:
                try:
                    e["blokk"] = cpp_teszt.teszt_blokk(f"Edge case {i} (AI)", e["bemenet"], e["vart"])
                except ValueError:
                    pass
        return {"mod": "teszt", "esetek": esetek, "referencia": _ref_ki(ref), "sajat_fordul": sajat is not None,
                "ellenorzott": bool(ref["ellenorzott"])}

    def _stressz(self, f: Futtato, kod: str, leiras: str, tesztek: list) -> dict:
        v = ai.stressz_valasz(self.p, self._modell(ai.keres(self.p, "stressz", leiras, kod)))
        ref = AE.referencia(f, v["referencia"], tesztek)
        ki = {"mod": "stressz", "referencia": _ref_ki(ref), "ellenpelda": None, "menet": 0, "ellenorzott": bool(ref["ellenorzott"])}
        gen = f.fordit(v["generator"], "generator") if v["generator"] else None
        sajat = self._sajat(f, kod)
        if gen is None or not gen.ok:
            return {**ki, "kod_uzenet": "kod.generator_hiba", "uzenet": "The generator is missing or does not compile.",
                    "generator": gen.osszegzes() if gen else None}
        if ref["program"] is None:
            return {**ki, "kod_uzenet": "kod.referencia_hiba", "uzenet": "The reference is missing or does not compile."}
        if sajat is None:
            return {**ki, "kod_uzenet": "kod.sajat_nem_fordul",
                    "uzenet": "Your own solution does not compile: fix the compile error first (⌘R)."}
        s = AE.stressz(f, gen, ref["program"], sajat)
        e = s["ellenpelda"]
        if e is not None:
            try:
                e["blokk"] = cpp_teszt.teszt_blokk("Stress counterexample (AI)", e["bemenet"], e["vart"]) if ref["ellenorzott"] else None
            except ValueError:
                e["blokk"] = None
        return {**ki, "ellenpelda": e, "menet": s["menet"], "uzenet": s["hiba"]}


def _ref_ki(ref: dict) -> dict:
    return {"ellenorzott": ref["ellenorzott"], "atment_db": ref["atment_db"], "ossz": ref["ossz"], "uzenet": ref.get("uzenet", ""),
            "fordul": bool(ref.get("program"))}
