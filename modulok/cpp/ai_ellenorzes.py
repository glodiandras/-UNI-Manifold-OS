"""A modell kódjának ellenőrzése — **kizárólag a program-homokozóban** (C36b; 53(b)).

A modell által írt minden kód (javított megoldás, lassú referencia, véletlenbemenet-generátor) a fordító-profil alatt fordul
és a futtató profil alatt fut (`modulok/homokozo/program.py`: hálózat, idegen fájl, fork tiltva; idő-, memória-, kimenet- és
lemezkorlát). A modell bemenet-javaslata adat: csak a stdin-re kerül. Az élő út (`ai_futas.py`) és a mérés
(`modulok/eval/kod/feladat.py`) ugyanezeket a függvényeket hívja.

`Futtato`: egy ideiglenes futás-mappa (`{tmp}/cpp/ai-*`, a végén törlődik), benne `fordit(forras) → Program` és
`futtat(program, bemenet, argv)`. A „referencia” csak akkor ad várt kimenetet, ha a feladat minden tesztjén átmegy (az
ellenőrzött referencia); különben a javaslat „nem ellenőrzött”.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from modulok.homokozo.program import Programhomokozo

from . import diagnosztika, osszevet
from .eszkoztar import Eszkoztar, fordit_kornyezet, futtat_kornyezet

FORRAS_MAX_BAJT = 256 * 1024
STRESSZ_MENET = 150                 # ennyi véletlen bemenet a stressz-tesztben (vagy az időkeretig)
STRESSZ_IDOKERET_S = 25.0
GENERATOR_IDOKORLAT_S = 2.0
REFERENCIA_IDOKORLAT_S = 3.0
GENERALT_MAX_KAR = 20000            # a generátor kimenete (egy bemenet) legfeljebb ennyi karakter


@dataclass
class Program:
    ok: bool
    bin: Path | None
    allapot: str
    diagnosztika: list = field(default_factory=list)
    hiba_db: int = 0
    uzenet: str = ""
    ms: float = 0.0

    def osszegzes(self) -> dict:
        return {"ok": self.ok, "allapot": self.allapot, "hiba_db": self.hiba_db, "uzenet": self.uzenet,
                "diagnosztika": self.diagnosztika[:8], "ms": self.ms}


class Futtato:
    """Fordítás és futtatás egy saját ideiglenes mappában. Környezetkezelő: a mappa a végén törlődik."""

    def __init__(self, cfg, *, eszkoztar: Eszkoztar | None = None, homokozo: Programhomokozo | None = None, megszakit=None):
        self.cfg = cfg
        self.e = eszkoztar or Eszkoztar(cfg)
        self.b = self.e.b
        self.ph = homokozo or Programhomokozo(cfg)
        self.megszakit = megszakit or (lambda: False)
        self.mappa: Path | None = None
        self._n = 0

    def __enter__(self) -> "Futtato":
        alap = self.cfg.path("tmp") / "cpp"
        alap.mkdir(parents=True, exist_ok=True)
        self.mappa = Path(tempfile.mkdtemp(prefix="ai-", dir=alap)).resolve()
        return self

    def __exit__(self, *_):
        if self.mappa is not None:
            shutil.rmtree(self.mappa, ignore_errors=True)
            self.mappa = None

    def hiany(self) -> str | None:
        """Az eszköztár vagy a homokozó hiánya (akkor semmi nem fordul és nem fut: zárva hibázik)."""
        h = self.e.hianyzo()
        if h:
            return f"nincs C++ eszköztár (hiányzik: {', '.join(h)}): bin/mos cpp telepit --igen"
        ok, uzenet = self.ph.elerheto()
        return None if ok else f"a homokozó nem elérhető: {uzenet}"

    def fordit(self, forras: str, nev: str = "prog", mod: str = "gyors") -> Program:
        """A `forras` fordítása a fordító-profil alatt (a forrás a saját `munka/` mappájába másolódik)."""
        if self.mappa is None:
            raise RuntimeError("a Futtato környezetkezelőként használandó")
        if not isinstance(forras, str) or not forras.strip():
            return Program(False, None, "nincs_forras", uzenet="nincs forráskód")
        if len(forras.encode("utf-8")) > FORRAS_MAX_BAJT:
            return Program(False, None, "tul_nagy", uzenet="a forrás túl nagy")
        self._n += 1
        munka = self.mappa / f"{nev}-{self._n}"
        munka.mkdir()
        (munka / "megoldas.cpp").write_text(forras, encoding="utf-8")
        c = self.ph.fordit(self.e.parancs(str(munka / "megoldas.cpp"), str(munka / "prog"), mod), munka=munka, llvm=self.e.llvm,
                           sdk=self.e.sdk, pot=self.e.pot, kornyezet=fordit_kornyezet(munka, self.e.sdk),
                           idokorlat_s=float(self.b["fordit_idokorlat_s"]), memoria_mb=float(self.b["fordit_memoria_mb"]),
                           kimenet_max_kb=int(self.b["kimenet_max_kb"]), megszakit=self.megszakit,
                           munka_max_mb=float(self.b["fordit_munka_max_mb"]),
                           munka_max_fajl=int(self.b["fordit_munka_max_fajl"]))
        d = diagnosztika.fordito(c["stderr"] + ("\n" + c["stdout"] if c["stdout"].strip() else ""), "megoldas.cpp")
        ok = c["allapot"] == "ok" and (munka / "prog").is_file()
        if not ok:
            return Program(False, None, c["allapot"], d["diagnosztika"], d["hiba_db"], c["uzenet"] or "a fordítás nem sikerült",
                           c["ido_ms"])
        binmappa = munka / "bin"
        binmappa.mkdir()
        shutil.copy2(munka / "prog", binmappa / "prog")
        os.chmod(binmappa / "prog", 0o755)
        return Program(True, binmappa / "prog", "ok", d["diagnosztika"], 0, "", c["ido_ms"])

    def futtat(self, p: Program, bemenet: str = "", *, argv: tuple = (), idokorlat_s: float | None = None,
               memoria_mb: float | None = None) -> dict:
        """Egy futás a futtató profil alatt. → `{allapot, stdout, stderr, ido_ms, uzenet}`; az állapot a homokozóé
        (`ok`, `idotullepes`, `memoria`, `kimenet_tullepes`, `iras_korlat`, `jel`, `kilepesi_hiba`, `homokozo_hiba`)."""
        if not p.ok or p.bin is None:
            return {"allapot": "nincs_program", "stdout": "", "stderr": "", "ido_ms": 0.0, "uzenet": "a program nem fordult le"}
        self._n += 1
        munka = self.mappa / f"futas-{self._n}"
        munka.mkdir()
        try:
            r = self.ph.futtat(p.bin, argv=[str(a) for a in argv], bemenet=bemenet.encode("utf-8"), munka=munka,
                               idokorlat_s=float(idokorlat_s or self.b["teszt_idokorlat_s"]),
                               memoria_mb=float(memoria_mb or self.b["memoria_mb"]),
                               kimenet_max_kb=int(self.b["kimenet_max_kb"]), stderr_max_kb=int(self.b["stderr_max_kb"]),
                               munka_max_mb=float(self.b["munka_max_mb"]), munka_max_fajl=int(self.b["munka_max_fajl"]),
                               kornyezet=futtat_kornyezet(self.b, "gyors"), mintavetel_ms=float(self.b["mintavetel_ms"]),
                               megszakit=self.megszakit)
        finally:
            shutil.rmtree(munka, ignore_errors=True)
        return {"allapot": r["allapot"], "stdout": r["stdout"].decode("utf-8", "replace"),
                "stderr": r["stderr"].decode("utf-8", "replace"), "ido_ms": r["ido_ms"], "uzenet": r["uzenet"]}


# --------------------------------------------------------------------------- tesztek

def teszt_futas(f: Futtato, p: Program, tesztek: list) -> dict:
    """A program a feladat (`core.cpp_teszt.Teszt`) tesztjein. → `{atment_db, ossz, elbukott: [sorszám], eredmenyek}`; a hibás
    blokk nem számít (nem futtatható)."""
    ered = []
    for t in tesztek:
        if getattr(t, "hiba", None):
            continue
        r = f.futtat(p, t.bemenet, idokorlat_s=t.idokorlat_s or None)
        jo = r["allapot"] == "ok" and osszevet.egyezik(t.kimenet, r["stdout"], t.osszevetes,
                                                       t.eps if t.eps is not None else float(f.b["lebego_eps"]))
        ered.append({"sorszam": t.sorszam, "atment": jo, "allapot": r["allapot"] if r["allapot"] != "ok" or jo else "hibas_kimenet",
                     "kapott": r["stdout"]})
    return {"atment_db": sum(e["atment"] for e in ered), "ossz": len(ered),
            "elbukott": [e["sorszam"] for e in ered if not e["atment"]], "eredmenyek": ered}


def referencia(f: Futtato, kod: str | None, tesztek: list) -> dict:
    """A modell lassú referenciája: lefordul-e, és a feladat tesztjein átmegy-e. Ellenőrzött = lefordult, volt teszt, és mindegyiken
    átment. → `{ellenorzott, fordit, atment_db, ossz, program}`."""
    if not kod:
        return {"ellenorzott": False, "fordit": None, "atment_db": 0, "ossz": 0, "program": None, "uzenet": "nincs referencia"}
    p = f.fordit(kod, "referencia")
    if not p.ok:
        return {"ellenorzott": False, "fordit": p.osszegzes(), "atment_db": 0, "ossz": 0, "program": None,
                "uzenet": "a referencia nem fordul le"}
    t = teszt_futas(f, p, tesztek)
    ell = t["ossz"] > 0 and t["atment_db"] == t["ossz"]
    return {"ellenorzott": ell, "fordit": p.osszegzes(), "atment_db": t["atment_db"], "ossz": t["ossz"], "program": p,
            "uzenet": "" if ell else (f"a referencia {t['atment_db']}/{t['ossz']} teszten ment át" if t["ossz"]
                                      else "nincs teszt, amin a referencia ellenőrizhető")}


def kimenet(f: Futtato, p: Program | None, bemenet: str, idokorlat_s: float | None = None) -> dict:
    if p is None:
        return {"allapot": "nincs_program", "stdout": "", "stderr": "", "ido_ms": 0.0, "uzenet": ""}
    return f.futtat(p, bemenet, idokorlat_s=idokorlat_s)


def egyezik(a: str, b: str) -> bool:
    return osszevet.egyezik(a, b, "alap", None)


def szelso_tesztek(f: Futtato, bemenetek: list[str], ref: dict, sajat: Program | None, idokorlat_s: float | None = None) -> list[dict]:
    """A modell bemenetei: a várt kimenet az ELLENŐRZÖTT referenciáé (különben `None`), a kapott a diák programjáé.
    → tesztenként `{bemenet, vart, kapott, allapot, ellenorzott}`; az állapot `elteres` | `egyezik` | `sajat_hiba` |
    `referencia_hiba` | `nem_ellenorzott`."""
    ki = []
    for bem in bemenetek:
        vart = None
        allapot = "nem_ellenorzott"
        if ref.get("ellenorzott"):
            rv = kimenet(f, ref["program"], bem, REFERENCIA_IDOKORLAT_S)
            if rv["allapot"] == "ok":
                vart = rv["stdout"]
            else:
                allapot = "referencia_hiba"
        sv = kimenet(f, sajat, bem, idokorlat_s) if sajat is not None else None
        kapott = sv["stdout"] if sv is not None else None
        if vart is not None and sv is not None:
            if sv["allapot"] != "ok":
                allapot = "sajat_hiba"
            else:
                allapot = "egyezik" if egyezik(vart, kapott) else "elteres"
        ki.append({"bemenet": bem, "vart": vart, "kapott": kapott,
                   "sajat_allapot": sv["allapot"] if sv is not None else None, "allapot": allapot,
                   "ellenorzott": vart is not None})
    return ki


def generalt_bemenet(f: Futtato, gen: Program, mag: int) -> tuple[str | None, str]:
    """A generátor egy futása a `mag`-gal (1. argumentum). → (bemenet, hiba)."""
    r = f.futtat(gen, "", argv=(mag,), idokorlat_s=GENERATOR_IDOKORLAT_S)
    if r["allapot"] != "ok":
        return None, f"a generátor nem futott le ({r['allapot']}: {r['uzenet']})"
    if not r["stdout"].strip():
        return None, "a generátor üres bemenetet adott"
    if len(r["stdout"]) > GENERALT_MAX_KAR:
        return None, "a generátor túl nagy bemenetet adott"
    return r["stdout"], ""


def stressz(f: Futtato, gen: Program, vart_prog: Program, kapott_prog: Program, *, menet: int = STRESSZ_MENET,
            idokeret_s: float = STRESSZ_IDOKERET_S, ervenyes=None, idokorlat_s: float | None = None) -> dict:
    """Stressz-teszt: `menet` véletlen bemenet (mag = 1, 2, …) a generátorból; a `vart_prog` (referencia) és a `kapott_prog`
    kimenete összevetve. Az első eltérés az ellenpélda. Az `ervenyes(bemenet) -> bool` (ha van) a generált bemenetet szűri.
    → `{menet, ellenpelda: {mag, bemenet, vart, kapott, allapot} | None, hiba, ervenytelen}`."""
    kezd = time.monotonic()
    n = ervenytelen = 0
    for mag in range(1, menet + 1):
        if f.megszakit() or time.monotonic() - kezd > idokeret_s:
            break
        bem, hiba = generalt_bemenet(f, gen, mag)
        if bem is None:
            return {"menet": n, "ellenpelda": None, "hiba": hiba, "ervenytelen": ervenytelen}
        if ervenyes is not None and not ervenyes(bem):
            ervenytelen += 1
            continue
        n += 1
        rv = kimenet(f, vart_prog, bem, REFERENCIA_IDOKORLAT_S)
        if rv["allapot"] != "ok":
            return {"menet": n, "ellenpelda": None, "hiba": f"a referencia nem futott le ({rv['allapot']})",
                    "ervenytelen": ervenytelen}
        kv = kimenet(f, kapott_prog, bem, idokorlat_s)
        if kv["allapot"] != "ok" or not egyezik(rv["stdout"], kv["stdout"]):
            return {"menet": n, "ellenpelda": {"mag": mag, "bemenet": bem, "vart": rv["stdout"], "kapott": kv["stdout"],
                                               "allapot": "elteres" if kv["allapot"] == "ok" else kv["allapot"]},
                    "hiba": "", "ervenytelen": ervenytelen}
    return {"menet": n, "ellenpelda": None, "hiba": "", "ervenytelen": ervenytelen}
