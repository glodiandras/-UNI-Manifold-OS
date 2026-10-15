"""Egy C++ megoldás ellenőrzése (C36a): fordítás a fordító-profil alatt, majd tesztenként futtatás a futtató profil alatt.

Az események (a `esemeny` visszahívás kapja; a CLI JSON-sorként írja, a core WS-eseményként továbbítja):

    indul        {mod, tesztek_db, cpp, jegyzet}
    fordit_kesz  {fordit: {ok, allapot, ms, csucs_mb, diagnosztika, hiba_db, figyelmeztetes_db, levagva, uzenet, kivonat}}
    teszt        {teszt: {sorszam, cim, allapot, ido_ms, cpu_ms, csucs_mb, idokorlat_s, memoria_mb, osszevetes, kilepes, jel, diff, stdout_kivonat,
                          stderr_kivonat, jelentes, uzenet, hiba}, kesz_db, ossz}
    kesz         {atment, tesztek_db, atment_db, fordit_ok, ms, mod, hash, uzenet}
    hiba         {kod, uzenet}            az eszköztár vagy a homokozó hiánya: nincs mit futtatni
    megszakitva  {}

A teszt állapota: `atment`, `hibas_kimenet`, `futasi_hiba` (nem nulla kilépés vagy jel; az `assert` jelentésével), `szanitizer` (az
ASan/UBSan jelentésével, hibakereső módban), `idotullepes`, `memoria`, `kimenet_tullepes`, `iras_korlat`, `hibas_teszt` (a blokk
nem értelmezhető: nem fut), `homokozo_hiba`. A forrás a futás saját mappájába másolódik (`megoldas.cpp`), így a fordító
profiljának a vaultot nem kell olvasnia; a futás mappa a végén törlődik (saját `var/tmp`).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from modulok.homokozo.program import Programhomokozo

from . import diagnosztika, osszevet
from .eszkoztar import Eszkoztar, fordit_kornyezet, futtat_kornyezet

FORRAS_NEV = "megoldas.cpp"                 # a fordításban használt (ASCII) név; a megjelenített név az eredeti fájlnév
FORRAS_MAX_BAJT = 2 * 1024 * 1024
KIVONAT_MAX = 2000
MARADVANY_NAP_S = 86400                     # az ennél régebbi `futas-*` mappák maradványok (megszakadt futás)
_TBD_TIPP = ("az SDK-másolat .tbd fájljai az ld64.lld számára ismeretlen célt tartalmaznak: futtasd a "
             "`bin/mos cpp telepit --tbd-igazit` parancsot")

_ALLAPOT_UZENET = {"idotullepes": "a program túllépte az időkorlátot", "memoria": "a program túllépte a memóriakorlátot",
                   "kimenet_tullepes": "a program túl sok kimenetet írt", "iras_korlat": "a program túl sokat írt a saját mappájába"}


def _kivonat(b: bytes | str, tisztit: list[str] | None = None) -> str:
    s = b if isinstance(b, str) else b.decode("utf-8", "replace")
    for ut in tisztit or []:
        s = s.replace(ut, "<futás>")
    return s if len(s) <= KIVONAT_MAX else s[:KIVONAT_MAX] + "…"


def _nev_csere(obj, regi: str, uj: str):
    """A fordításban használt fájlnév cseréje a megjelenített névre (a `fajl` mezőkben, rekurzívan)."""
    if isinstance(obj, dict):
        return {k: (uj if k == "fajl" and v == regi else _nev_csere(v, regi, uj)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nev_csere(x, regi, uj) for x in obj]
    return obj


class Ellenorzes:
    def __init__(self, cfg, *, esemeny=None, eszkoztar: Eszkoztar | None = None, homokozo: Programhomokozo | None = None,
                 megszakit=None):
        self.cfg = cfg
        self.e = eszkoztar or Eszkoztar(cfg)
        self.b = self.e.b
        self.ph = homokozo or Programhomokozo(cfg)
        self._esemeny = esemeny or (lambda _d: None)
        self._megszakit = megszakit or (lambda: False)

    def ki(self, szakasz: str, **adat) -> dict:
        d = {"szakasz": szakasz, **adat}
        self._esemeny(d)
        return d

    # ------------------------------------------------------------------ előkészítés

    def _futas_mappa(self) -> Path:
        alap = self.cfg.path("tmp") / "cpp"
        alap.mkdir(parents=True, exist_ok=True)
        most = time.time()
        for p in alap.glob("futas-*"):                  # megszakadt futások maradványa (saját ideiglenes mappa)
            try:
                if most - p.stat().st_mtime > MARADVANY_NAP_S:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
        return Path(tempfile.mkdtemp(prefix="futas-", dir=alap)).resolve()

    def _hiba(self, kod: str, uzenet: str, mod: str, ido: float) -> dict:
        self.ki("hiba", kod=kod, uzenet=uzenet)
        return {"atment": False, "tesztek_db": 0, "atment_db": 0, "fordit_ok": False, "ms": round((time.monotonic() - ido) * 1000),
                "mod": mod, "hash": None, "uzenet": uzenet}

    # ------------------------------------------------------------------ a futás

    def fut(self, cpp: Path, tesztek: list, mod: str = "gyors", jegyzet: str | None = None) -> dict:
        """A `cpp` fájl fordítása és a `tesztek` (`core.cpp_teszt.Teszt`) futtatása. → a `kesz` esemény adata."""
        kezdet = time.monotonic()
        cpp = Path(cpp)
        nev = cpp.name
        hiany = self.e.hianyzo()
        if hiany:
            return self._hiba("nincs_eszkoztar", f"nincs C++ eszköztár (hiányzik: {', '.join(hiany)}): bin/mos cpp telepit --igen",
                              mod, kezdet)
        ok, uzenet = self.ph.elerheto()
        if not ok:
            return self._hiba("nincs_homokozo", f"a homokozó nem elérhető: {uzenet}", mod, kezdet)
        try:
            forras = cpp.read_bytes()
        except OSError as exc:
            return self._hiba("nincs_forras", f"a forrás nem olvasható: {exc}", mod, kezdet)
        if len(forras) > FORRAS_MAX_BAJT:
            return self._hiba("tul_nagy_forras", f"a forrás túl nagy (legfeljebb {FORRAS_MAX_BAJT >> 20} MiB)", mod, kezdet)
        sha = hashlib.sha256(forras).hexdigest()
        futas = self._futas_mappa()
        try:
            return self._fut(futas, cpp, nev, forras, sha, tesztek, mod, jegyzet, kezdet)
        finally:
            shutil.rmtree(futas, ignore_errors=True)

    def _megszakitva(self, mod: str, sha: str, ossz: int, atment_db: int, kezdet: float) -> dict:
        self.ki("megszakitva")
        return {"atment": False, "tesztek_db": ossz, "atment_db": atment_db, "fordit_ok": False,
                "ms": round((time.monotonic() - kezdet) * 1000), "mod": mod, "hash": sha, "uzenet": "megszakítva"}

    def _fut(self, futas: Path, cpp: Path, nev: str, forras: bytes, sha: str, tesztek: list, mod: str, jegyzet, kezdet) -> dict:
        b, e, ph = self.b, self.e, self.ph
        munka, bin_mappa = futas / "munka", futas / "bin"
        munka.mkdir()
        bin_mappa.mkdir()
        (munka / FORRAS_NEV).write_bytes(forras)
        self.ki("indul", mod=mod, tesztek_db=len(tesztek), cpp=nev, jegyzet=jegyzet)
        if self._megszakit():
            return self._megszakitva(mod, sha, len(tesztek), 0, kezdet)

        # -- fordítás
        c = ph.fordit(e.parancs(str(munka / FORRAS_NEV), str(munka / "prog"), mod), munka=munka, llvm=e.llvm, sdk=e.sdk, pot=e.pot,
                      kornyezet=fordit_kornyezet(munka, e.sdk), idokorlat_s=float(b["fordit_idokorlat_s"]),
                      memoria_mb=float(b["fordit_memoria_mb"]), kimenet_max_kb=int(b["kimenet_max_kb"]), megszakit=self._megszakit,
                      munka_max_mb=float(b["fordit_munka_max_mb"]), munka_max_fajl=int(b["fordit_munka_max_fajl"]))
        if c["allapot"] == "megszakitva":
            return self._megszakitva(mod, sha, len(tesztek), 0, kezdet)
        szoveg = c["stderr"] + ("\n" + c["stdout"] if c["stdout"].strip() else "")
        d = diagnosztika.fordito(szoveg, FORRAS_NEV)
        fordit_ok = c["allapot"] == "ok" and (munka / "prog").is_file()
        fordit = {"ok": fordit_ok, "allapot": c["allapot"], "ms": c["ido_ms"], "csucs_mb": c["csucs_mb"], "linker": e.linker(),
                  "diagnosztika": d["diagnosztika"], "hiba_db": d["hiba_db"], "figyelmeztetes_db": d["figyelmeztetes_db"],
                  "levagva": d["levagva"], "uzenet": c["uzenet"], "kivonat": ""}
        if e.linker_figyelmeztetes():
            fordit["linker_figyelmeztetes"] = e.linker_figyelmeztetes()      # a régi `rendszer` beállítás (K168) nem marad csendben
        if not fordit_ok:
            fordit["kivonat"] = _kivonat(szoveg, [str(futas)]) if not d["diagnosztika"] or c["allapot"] != "hiba" else ""
            if "unknown target" in szoveg or "could not load TAPI" in szoveg:
                fordit["uzenet"] = _TBD_TIPP
            elif c["allapot"] == "ok":
                fordit["uzenet"] = "a fordítás nem hozott létre futtatható programot"
        self.ki("fordit_kesz", fordit=_nev_csere(fordit, FORRAS_NEV, nev))
        if not fordit_ok:
            return self._kesz(False, len(tesztek), 0, mod, sha, kezdet, "a fordítás nem sikerült")
        shutil.copy2(munka / "prog", bin_mappa / "prog")
        os.chmod(bin_mappa / "prog", 0o755)

        # -- tesztek
        if not tesztek:
            return self._kesz(True, 0, 0, mod, sha, kezdet, "nincs teszt blokk a jegyzetben: csak a fordítás futott")
        atment_db = 0
        for i, t in enumerate(tesztek, 1):
            if self._megszakit():
                return self._megszakitva(mod, sha, len(tesztek), atment_db, kezdet)
            eredmeny = self._teszt(t, futas, munka, bin_mappa / "prog", mod, nev)
            if eredmeny is None:
                return self._megszakitva(mod, sha, len(tesztek), atment_db, kezdet)
            atment_db += eredmeny["allapot"] == "atment"
            self.ki("teszt", teszt=eredmeny, kesz_db=i, ossz=len(tesztek))
        return self._kesz(True, len(tesztek), atment_db, mod, sha, kezdet, "")

    def _kesz(self, fordit_ok: bool, ossz: int, atment_db: int, mod: str, sha: str, kezdet: float, uzenet: str) -> dict:
        d = {"atment": fordit_ok and ossz > 0 and atment_db == ossz, "tesztek_db": ossz, "atment_db": atment_db,
             "fordit_ok": fordit_ok, "ms": round((time.monotonic() - kezdet) * 1000), "mod": mod, "hash": sha, "uzenet": uzenet}
        self.ki("kesz", **d)
        return d

    # ------------------------------------------------------------------ egy teszt

    def _teszt(self, t, futas: Path, fordit_munka: Path, prog: Path, mod: str, nev: str) -> dict | None:
        b = self.b
        alap = {"sorszam": t.sorszam, "cim": t.cim, "allapot": None, "ido_ms": 0.0, "cpu_ms": 0.0, "csucs_mb": 0.0,
                "idokorlat_s": None, "memoria_mb": None, "osszevetes": t.osszevetes, "kilepes": None, "jel": None, "diff": None, "stdout_kivonat": "", "stderr_kivonat": "",
                "jelentes": None, "uzenet": "", "hiba": None}
        if t.hiba:
            return alap | {"allapot": "hibas_teszt", "hiba": t.hiba, "uzenet": t.hiba}
        szorzo = float(b["hibakereso_idoszorzo"]) if mod == "hibakereso" else 1.0
        ido = (t.idokorlat_s if t.idokorlat_s else float(b["teszt_idokorlat_s"])) * szorzo
        if mod == "hibakereso":        # a sanitizer árnyékmemóriája miatt a blokk korlátja nem szűkítheti a hibakereső keretet
            mem = max(float(b["hibakereso_memoria_mb"]), t.memoria_mb or 0)
        else:
            mem = t.memoria_mb or float(b["memoria_mb"])
        munka = futas / f"t{t.sorszam}"
        munka.mkdir()
        try:
            r = self.ph.futtat(prog, bemenet=t.bemenet.encode("utf-8"), munka=munka, idokorlat_s=ido, memoria_mb=mem,
                               kimenet_max_kb=int(b["kimenet_max_kb"]), stderr_max_kb=int(b["stderr_max_kb"]),
                               munka_max_mb=float(b["munka_max_mb"]), munka_max_fajl=int(b["munka_max_fajl"]),
                               kornyezet=futtat_kornyezet(b, mod), san_lib=self.e.san_lib() if mod == "hibakereso" else None,
                               mintavetel_ms=float(b["mintavetel_ms"]), megszakit=self._megszakit)
        finally:
            shutil.rmtree(munka, ignore_errors=True)
        if r["allapot"] == "megszakitva":
            return None
        tisztit = [str(futas)]
        stdout = r["stdout"].decode("utf-8", "replace")
        stderr = r["stderr"].decode("utf-8", "replace")
        e = alap | {"ido_ms": r["ido_ms"], "cpu_ms": r["cpu_ms"], "csucs_mb": r["csucs_mb"], "idokorlat_s": ido, "memoria_mb": mem,
                    "kilepes": r["kilepes"], "jel": r["jel"], "stderr_kivonat": _kivonat(stderr, tisztit), "uzenet": r["uzenet"]}
        allapot = r["allapot"]
        if allapot == "ok":
            eps = t.eps if t.eps is not None else float(b["lebego_eps"])
            if osszevet.egyezik(t.kimenet, stdout, t.osszevetes, eps):
                return e | {"allapot": "atment", "uzenet": ""}
            return e | {"allapot": "hibas_kimenet", "diff": osszevet.diff(t.kimenet, stdout, mod=t.osszevetes, eps=eps),
                        "stdout_kivonat": _kivonat(stdout), "uzenet": "a kimenet eltér a vártól"}
        if allapot in ("kilepesi_hiba", "jel"):
            j = diagnosztika.jelentes(stderr, FORRAS_NEV, bin_nev="prog")
            if j is not None:
                self._szimbolizal(j, fordit_munka)
                j = _nev_csere(j, FORRAS_NEV, nev)
            e["stdout_kivonat"] = _kivonat(stdout)
            szanitizer = j is not None and j["forras"] in ("asan", "ubsan")
            if szanitizer:
                return e | {"allapot": "szanitizer", "jelentes": j, "uzenet": j["leiras"]}
            return e | {"allapot": "futasi_hiba", "jelentes": j}
        if allapot == "homokozo_hiba":
            return e | {"allapot": "homokozo_hiba"}
        return e | {"allapot": allapot, "uzenet": _ALLAPOT_UZENET.get(allapot, r["uzenet"]), "stdout_kivonat": _kivonat(stdout)}

    def _szimbolizal(self, j: dict, munka: Path) -> None:
        """Az ASan nyers kereteinek feloldása az `llvm-symbolizer`-rel — a fordító profilja alatt (olvas: az LLVM és a `munka/`,
        ahol a bináris és a dSYM áll)."""
        cimek = diagnosztika.szimbolizalando_cimek(j)
        if not cimek or not self.e.bin("llvm-symbolizer").is_file():
            return
        arch = next((k["arch"] for k in j["keretek"] if k.get("sajat_modul")), "arm64")
        r = self.ph.fordit([str(self.e.bin("llvm-symbolizer")), f"--obj={munka / 'prog'}", f"--default-arch={arch}",
                            "--functions=short", "--inlines", *cimek],
                           munka=munka, llvm=self.e.llvm, sdk=self.e.sdk, pot=self.e.pot, idokorlat_s=15, memoria_mb=1024,
                           kimenet_max_kb=256)
        if r["allapot"] == "ok":
            diagnosztika.szimbolizal(j, FORRAS_NEV, r["stdout"])
