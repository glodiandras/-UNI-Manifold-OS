"""A C++ munkafelület a core-ban (C36a; `docs/C36a-TERV.md`, TERV 5.14): végpontok, a futás-kezelő, a WS-események, a tracker-esemény.

A motor (`modulok/cpp`) **gyermekfolyamat**: a core nem importál `modulok`-ot. Egy ⌘R egy `python -m modulok.cpp ellenoriz …
--json-sorok` folyamat; a stdout JSON-sorait a core WS-eseménnyé (`cpp_futas`) alakítja, a végén a tracker-eseményt írja
(`cpp_proba`: számok és jelzők, kód és szöveg nélkül). A megszakítás SIGTERM a motornak, az leállítja a saját (homokozóban futó)
gyermekeit; a core leállásakor is ez történik, így nem marad árva `clang++` vagy teszt-folyamat.

Egyszerre egy futás. A hosszú művelet nem a feladatsor (`core/tasks.py`: az nem visz strukturált eredményt, és a szinkron
végpontnak 30 s-os korlátja van), hanem egy háttérszál a gyermekfolyamat kimenetén.

| Végpont | Mit ad |
|---|---|
| `GET /api/cpp/allapot` | az eszköztár állapota (`bin/mos cpp allapot --json`) + az aktív futás |
| `GET /api/cpp/feladat?ut=` | a jegyzet ↔ `.cpp` párosítás és a `teszt` blokkok |
| `POST /api/cpp/feladat {mappa, nev, nyelv?}` | új feladat: a forrás (alap: `.cpp`; `nyelv`: bármely kód-profil) és a jegyzet (két gépi commit) |
| `POST /api/cpp/ellenoriz {ut, jegyzet?, mod?}` | 202 `{futas, …}`; az eredmény WS-en jön |
| `GET /api/cpp/futas/{id}` | a futás összesítője (késői csatlakozóknak) |
| `POST /api/cpp/megszakit {futas}` | a futás leállítása |
| `POST /api/cpp/formaz {szoveg}` | clang-format |
| `/api/cpp/ai…` | az AI-réteg (C36b): `core/cpp_ai.py` |
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import cpp_ai, cpp_teszt, kod_nyelvek, pdfkiemeles, sablon, tulajdonsagok
from .utvonalak import HttpError, Valasz
from .vaultio import Invalid, NotFound, nfc, norm_path
from .hibakod import kodol

REPO = Path(__file__).resolve().parent.parent
MODOK = ("gyors", "hibakereso")
FORMAZ_MAX_BAJT = 2 * 1024 * 1024
FORMAZ_IDOKORLAT_S = 30
MEGSZAKIT_VARAKOZAS_S = 5.0
ELOZMENY_MAX = 8                    # a lezárt futások száma a memóriában (a `GET /api/cpp/futas/{id}` ennyit ismer)
LOG_VEGE = 12                       # a motor nem JSON kimenetének utolsó sorai (váratlan leállásnál az üzenetbe)
KIVONAT_MAX = 160
FUTAS_ID = re.compile(r"^futas-[0-9a-f]{12}$")


def beallitasok(cfg) -> dict:
    s = cfg.section("cpp")
    return {"teszt_idokorlat_max_s": float(s.get("teszt_idokorlat_max_s", 10.0)),
            "teszt_memoria_max_mb": float(s.get("teszt_memoria_max_mb", 1024)), "sablon": s.get("sablon", "C++ feladat")}


def gyerek_env(cfg) -> dict[str, str]:
    """A motor-folyamat környezete: a core `os.environ`-ja, de a core saját konfigurációjával — minden `[utak]` kulcs a core
    feloldott értékével, a gyökér és a konfigfájl, így a motor pontosan azt látja, amit a core (álgyökerű teszt is)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOS_")}
    env.update({f"MOS_{k.upper()}": str(v) for k, v in cfg.utak.items()})
    env["MOS_ROOT"] = str(cfg.root)
    if cfg.source:
        env["MOS_CONFIG"] = str(cfg.source)
    env["HOME"] = cfg.table.get("home", env.get("HOME", ""))
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _kivonat(s: str | None) -> str | None:
    return None if s is None else (s if len(s) <= KIVONAT_MAX else s[:KIVONAT_MAX] + "…")


class Futas:
    def __init__(self, fid: str, ut: str, jegyzet: str | None, mod: str, tesztek_db: int, proc: subprocess.Popen):
        self.id, self.ut, self.jegyzet, self.mod, self.tesztek_db, self.proc = fid, ut, jegyzet, mod, tesztek_db, proc
        self.allapot = "fut"                        # fut | kesz | hiba | megszakitva
        self.indult = time.time()
        self.fordit: dict | None = None
        self.tesztek: list[dict] = []
        self.kesz: dict | None = None
        self.hiba: dict | None = None
        self.megszakit_kerve = False
        self.log: list[str] = []

    def adat(self) -> dict:
        return {"futas": self.id, "ut": self.ut, "jegyzet": self.jegyzet, "mod": self.mod, "allapot": self.allapot,
                "tesztek_db": self.tesztek_db, "fordit": self.fordit, "tesztek": self.tesztek, "kesz": self.kesz,
                "hiba": self.hiba, "indult": self.indult}


class Szolgalat:
    def __init__(self, cfg, vault, index, publish, tracker, mentetlen=None):
        self.cfg, self.vault, self.index, self.publish, self.tracker = cfg, vault, index, publish, tracker
        self.mentetlen = mentetlen or (lambda: set())
        self.b = beallitasok(cfg)
        self._zar = threading.Lock()
        self._aktiv: Futas | None = None
        self._futasok: dict[str, Futas] = {}
        self._szalak: list[threading.Thread] = []
        self._leallt = False
        # C36b: az AI-réteg (csak kattintásra; a motor ugyanaz a gyermekfolyamat, mint a ⌘R-é)
        self.ai = cpp_ai.Szolgalat(cfg, vault, publish, tracker, feladat=self.feladat, motor=self._motor,
                                   env=lambda: gyerek_env(cfg), mentetlen=self.mentetlen,
                                   eszkoztar_hianya=self._eszkoztar_hianya)
        # F10: the multi-language workbench (`/api/kod/*`, core/kod_utvonal.py) — reached as `app.cpp.kod`
        from . import kod_utvonal
        self.kod = kod_utvonal.Szolgalat(cfg, vault, index, publish, env=lambda: gyerek_env(cfg), mentetlen=self.mentetlen)

    # ------------------------------------------------------------------ segédek

    def _motor(self, *argv: str) -> list[str]:
        return [sys.executable, "-B", "-m", "modulok.cpp", *argv]

    def _eszkoztar_hianya(self) -> str | None:
        llvm, sdk = self.cfg.path("llvm"), self.cfg.path("sdk")
        hi = [n for n in ("clang++", "clang-format") if not os.access(llvm / "bin" / n, os.X_OK)]
        if not (sdk / "SDKSettings.json").is_file():
            hi.append("sdk")
        return (f"nincs C++ eszköztár (hiányzik: {', '.join(hi)}): bin/mos cpp telepit --igen" if hi else None)

    def _fajl_szoveg(self, rp: str) -> str:
        return self.vault.read(rp)["tartalom"]

    def _rp(self, ut, *kiterjesztesek: str) -> str:
        if not isinstance(ut, str) or not ut.strip():
            raise kodol(Invalid("hiányzik az út (`ut`)"), "cpp_utvonal.hianyzik_ut_ut")
        rp = self.vault.kanonikus(norm_path(ut))
        if not rp.lower().endswith(kiterjesztesek):
            raise kodol(Invalid(f"a fájl {' vagy '.join(kiterjesztesek)} kiterjesztésű legyen: {rp}"), "cpp_utvonal.fajl_join_kiterjesztesu_legyen_rp", {"join": ' vagy '.join(kiterjesztesek), "rp": rp})
        return rp

    def _tesztek(self, rp: str) -> list[dict]:
        return [t.szotar() for t in cpp_teszt.tesztek(self._fajl_szoveg(rp), self.b["teszt_idokorlat_max_s"],
                                                      self.b["teszt_memoria_max_mb"])]

    # ------------------------------------------------------------------ a jegyzet ↔ .cpp párosítás

    def _beagyazott_cpp(self, jegyzet: str, szoveg: str) -> tuple[str | None, str | None]:
        """A jegyzet első beágyazott `.cpp`-je → (vault-relatív út, hiba). Az index feloldásával (`link.cel`); ha az index még nem
        látja (új jegyzet), a név a jegyzet mappájából vagy a vault gyökeréből."""
        celok = cpp_teszt.beagyazott_cpp(szoveg)
        if not celok:
            return None, "nincs beágyazott .cpp a jegyzetben (![[név.cpp]])"
        feloldott = []
        try:
            feloldott = [l["cel"] for l in self.index.jegyzet(jegyzet)["linkek"]
                         if l["beagyazas"] and l["cel"] and l["cel"].lower().endswith(".cpp")]
        except Exception:                                   # noqa: BLE001 — az index még épül vagy nem látja: a név-tartalék
            feloldott = []
        if feloldott:
            return feloldott[0], None
        mappa = jegyzet.rpartition("/")[0]
        for jelolt in ((f"{mappa}/{celok[0]}" if mappa else celok[0]), celok[0]):
            try:
                rp = self.vault.kanonikus(norm_path(jelolt))
                if self.vault._abs(rp).is_file():
                    return rp, None
            except (Invalid, NotFound):
                continue
        return None, f"a beágyazott fájl nem található: {celok[0]}"

    def _jegyzetek(self, cpp: str) -> list[str]:
        """A `.cpp`-t beágyazó, `teszt` blokkos jegyzetek (a visszahivatkozásokból)."""
        try:
            forrasok = self.index.visszahivatkozasok(cpp)["forrasok"]
        except Exception:                                   # noqa: BLE001 — az index még épül vagy nem látja
            return []
        ki = []
        for f in forrasok:
            if f["ut"].lower().endswith(".md") and any(l["beagyazas"] for l in f["linkek"]):
                try:
                    if cpp_teszt.tesztek(self._fajl_szoveg(f["ut"])):
                        ki.append(f["ut"])
                except (Invalid, NotFound):
                    continue
        return sorted(ki)

    def feladat(self, ut) -> dict:
        rp = self._rp(ut, ".md", ".cpp")
        jegyzet = cpp = hiba = None
        jegyzetek: list[str] = []
        if rp.lower().endswith(".md"):
            szoveg = self._fajl_szoveg(rp)
            jegyzet = rp
            jegyzetek = [rp]
            cpp, hiba = self._beagyazott_cpp(rp, szoveg)
        else:
            self.vault.read(rp)                              # létezik és olvasható
            cpp = rp
            jegyzetek = self._jegyzetek(rp)
            jegyzet = jegyzetek[0] if len(jegyzetek) == 1 else None
        return {"jegyzet": jegyzet, "cpp": cpp, "jegyzetek": jegyzetek, "hiba": hiba,
                "tesztek": self._tesztek(jegyzet) if jegyzet else []}

    # ------------------------------------------------------------------ új feladat

    def _van_ilyen(self, mappa: str, nev: str) -> bool:
        d = self.vault._abs(mappa) if mappa else self.vault.root
        if not d.is_dir():
            return False
        kulcs = nfc(nev).lower()
        return any(nfc(n).lower() == kulcs for n in os.listdir(d))

    def uj_feladat(self, d: dict) -> dict:
        """New task: the companion source and the task note. `nyelv` (a `core/kod_nyelvek.py` profile id; default `cpp`) selects the
        language of the code workbench; the note skeleton is the same neutral English one for every language."""
        nyelv = d.get("nyelv") or "cpp"
        profil = kod_nyelvek.profil(nyelv) if isinstance(nyelv, str) else None
        if profil is None:
            raise kodol(Invalid("ismeretlen nyelv"), "kod.ismeretlen_nyelv", {"nyelv": str(nyelv)})
        kitok = (".md", *profil.kiterjesztesek)
        nev = nfc(str(d.get("nev") or "")).strip()
        for kit in kitok:
            if nev.lower().endswith(kit):
                nev = nev[:-len(kit)].rstrip()
                break
        mappa = self.vault.kanonikus(norm_path(d.get("mappa"))) if d.get("mappa") else ""
        if not nev:
            raise kodol(Invalid('érvénytelen név — tilos benne: \\ / : * ? " < > | # ^ [ ], és nem kezdődhet ponttal'), "cpp_utvonal.ervenytelen_nev_tilos_benne_kezdodhet")
        if mappa and not self.vault._abs(mappa).is_dir():
            raise kodol(NotFound(f"nincs ilyen mappa: {mappa}"), "cpp_utvonal.nincs_ilyen_mappa_mappa", {"mappa": mappa})
        for kit in (".md", *profil.kiterjesztesek):
            if self._van_ilyen(mappa, nev + kit):
                raise Invalid(f"már van ilyen nevű fájl: {mappa + '/' if mappa else ''}{nev}{kit}")
        if nyelv == "cpp":                                                               # C36a: the unchanged request shape
            forras_valasz = self.vault.create({"mappa": mappa, "nev": nev, "tipus": "cpp"})   # first: the note never points to a missing file
        else:
            forras_valasz = self.vault.create({"mappa": mappa, "nev": nev, "tipus": "forras", "nyelv": nyelv})
        tag = pdfkiemeles.cimke(self.cfg, f"{mappa}/{nev}")
        szoveg = self._vaz(nev, tag, nyelv, f"{mappa}/{nev}.md" if mappa else f"{nev}.md")
        md_valasz = self.vault.create({"mappa": mappa, "nev": nev, "tartalom": szoveg})
        return {"jegyzet": md_valasz["ut"], "cpp": forras_valasz["ut"], "forras": forras_valasz["ut"], "nyelv": nyelv,
                "figyelmeztetes": md_valasz.get("figyelmeztetes") or forras_valasz.get("figyelmeztetes")}

    def _sema_mezok(self, jegyzet: str) -> list[str]:
        """The frontmatter keys of the workspace schema for a new note at this path (empty: the neutral schema, or none readable)."""
        try:
            return list(tulajdonsagok.Sema.betolt(self.cfg).osztaly(jegyzet)["mezosorrend"])
        except (OSError, ValueError, KeyError):
            return []

    def _vaz(self, nev: str, tag: str | None, nyelv: str = "cpp", jegyzet: str | None = None) -> str:
        """The `C++ feladat` template note of the template folder for C++ (its `{{title}}` is the task name), otherwise the built-in
        neutral skeleton (`cpp_teszt.feladat_vaz`) with the workspace schema's keys."""
        sablon_nev = self.cfg.section("cpp").get("sablon", "C++ feladat") if nyelv == "cpp" else None
        if sablon_nev:
            try:
                alap = sablon.olvas(self.vault, f"{sablon.beallitasok(self.cfg)['mappa']}/{sablon_nev}.md")
                sb = sablon.beallitasok(self.cfg)
                most = datetime.now().astimezone()
                return sablon.kiertekel(alap, nev, most, nyelv=sb["nyelv"], datum=sb["datum"], ido=sb["ido"]).szoveg
            except (NotFound, Invalid):
                pass
        return cpp_teszt.feladat_vaz(nev, tag, nyelv, self._sema_mezok(jegyzet or f"{nev}.md"))

    # ------------------------------------------------------------------ állapot, formázás

    def allapot(self) -> dict:
        try:
            ki = subprocess.run(self._motor("allapot", "--json"), capture_output=True, text=True, timeout=60, cwd=str(REPO),
                                env=gyerek_env(self.cfg))
            d = json.loads(ki.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise HttpError(503, f"a C++ motor nem válaszol: {exc}", kod="cpp_utvonal.motor_nem_valaszol", param={"exc": exc}) from exc
        with self._zar:
            d["futas"] = self._aktiv.id if self._aktiv and self._aktiv.allapot == "fut" else None
        return d

    def formaz(self, d: dict) -> dict:
        szoveg = d.get("szoveg")
        if not isinstance(szoveg, str):
            raise kodol(Invalid("hiányzik a `szoveg`"), "cpp_utvonal.hianyzik_szoveg")
        if len(szoveg.encode("utf-8")) > FORMAZ_MAX_BAJT:
            raise kodol(Invalid("túl nagy szöveg a formázáshoz"), "cpp_utvonal.tul_nagy_szoveg_formazashoz")
        if not os.access(self.cfg.path("llvm") / "bin" / "clang-format", os.X_OK):
            raise HttpError(503, "nincs clang-format (bin/mos cpp telepit --igen)", kod="cpp_utvonal.nincs_clang_format")
        try:
            ki = subprocess.run(self._motor("formaz", "-"), input=szoveg, capture_output=True, text=True,
                                timeout=FORMAZ_IDOKORLAT_S, cwd=str(REPO), env=gyerek_env(self.cfg))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HttpError(503, f"a formázás nem sikerült: {exc}", kod="cpp_utvonal.formazas_sikertelen", param={"exc": exc}) from exc
        if ki.returncode != 0:
            raise Invalid(ki.stderr.strip().removeprefix("HIBA: ") or "a formázás nem sikerült")
        return {"szoveg": ki.stdout, "valtozott": ki.stdout != szoveg}

    # ------------------------------------------------------------------ ellenőrzés

    def ellenoriz(self, d: dict) -> Valasz:
        mod = d.get("mod") or "gyors"
        if mod not in MODOK:
            raise kodol(Invalid("a `mod` gyors vagy hibakereso lehet"), "cpp_utvonal.mod_gyors_hibakereso_lehet")
        f = self.feladat(d.get("ut"))
        jegyzet = f["jegyzet"]
        if d.get("jegyzet") is not None:
            jegyzet = self._rp(d["jegyzet"], ".md")
        if f["cpp"] is None:
            raise HttpError(400, f["hiba"] or "nincs .cpp megoldás", kod="nincs_cpp")
        if jegyzet is None and len(f["jegyzetek"]) > 1:
            raise HttpError(409, "több feladat-jegyzet ágyazza be ezt a .cpp-t: válassz", kod="tobbertelmu",
                            jegyzetek=f["jegyzetek"])
        hianyzik = self._eszkoztar_hianya()
        if hianyzik:
            raise HttpError(503, hianyzik, kod="nincs_eszkoztar")
        ment = self.mentetlen()
        mentetlen = [u for u in (f["cpp"], jegyzet) if u and u in ment]
        if mentetlen:
            raise HttpError(409, "mentetlen változás van a fájlban: mentsd előbb", kod="mentetlen", utak=mentetlen)
        tesztek = self._tesztek(jegyzet) if jegyzet else []
        cpp_abs = self.vault._abs(f["cpp"])
        argv = ["ellenoriz", str(self.vault._abs(jegyzet) if jegyzet else cpp_abs), "--json-sorok"]
        if jegyzet:
            argv += ["--cpp", str(cpp_abs)]
        if mod == "hibakereso":
            argv.append("--hibakereso")
        with self._zar:
            if self._leallt:
                raise HttpError(503, "a core leáll", kod="cpp_utvonal.core_leall")
            if self._aktiv is not None and self._aktiv.allapot == "fut":
                raise HttpError(409, "már fut egy ellenőrzés", kod="foglalt", futas=self._aktiv.id)
            fid = f"futas-{os.urandom(6).hex()}"
            try:
                proc = subprocess.Popen(self._motor(*argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        cwd=str(REPO), env=gyerek_env(self.cfg), start_new_session=True)
            except OSError as exc:
                raise HttpError(503, f"a C++ motor nem indul: {exc}", kod="cpp_utvonal.motor_nem_indul", param={"exc": exc}) from exc
            futas = Futas(fid, f["cpp"], jegyzet, mod, len(tesztek), proc)
            self._aktiv = futas
            self._futasok[fid] = futas
            while len(self._futasok) > ELOZMENY_MAX:
                regi = next((k for k, v in self._futasok.items() if v.allapot != "fut"), None)
                if regi is None:
                    break
                del self._futasok[regi]
            szal = threading.Thread(target=self._olvas, args=(futas,), daemon=True, name=f"cpp-{fid}")
            self._szalak.append(szal)
            szal.start()
        return Valasz(202, {"futas": fid, "jegyzet": jegyzet, "cpp": f["cpp"], "mod": mod, "tesztek_db": len(tesztek)})

    def _esemeny(self, futas: Futas, d: dict) -> None:
        sz = d.get("szakasz")
        if sz == "fordit_kesz":
            futas.fordit = d["fordit"]
        elif sz == "teszt":
            futas.tesztek.append(d["teszt"])
        elif sz == "kesz":
            futas.kesz = {k: v for k, v in d.items() if k != "szakasz"}
            futas.allapot = "kesz"
        elif sz == "hiba":
            futas.hiba = {"kod": d.get("kod"), "uzenet": d.get("uzenet")}
            futas.allapot = "hiba"
        elif sz == "megszakitva":
            futas.allapot = "megszakitva"
        if sz == "kesz":
            self._tracker(futas)                             # előbb a napló: mire a felület a `kesz`-t hallja, az esemény megvan
        self.publish({**d, "tipus": "cpp_futas", "futas": futas.id, "ut": futas.ut, "jegyzet": futas.jegyzet, "mod": futas.mod})

    def _tracker(self, futas: Futas) -> None:
        """Egy ⌘R a trackerbe: számok és jelzők, kód és szöveg nélkül; csak feladat-jegyzettel és teszttel (a csak-fordítás
        nem próbálkozás). A gyűjtő hibatűrő: soha nem akaszt."""
        k = futas.kesz or {}
        if not futas.jegyzet or not k.get("tesztek_db"):
            return
        try:
            self.tracker.fogad({"esemenyek": [{"tipus": "cpp_proba", "ut": futas.jegyzet, "adat": {
                "atment": bool(k["atment"]), "tesztek": int(k["tesztek_db"]), "atment_db": int(k["atment_db"]),
                "fordit_ok": bool(k["fordit_ok"]), "mod": futas.mod, "ms": max(0, int(k.get("ms") or 0))}}]})
        except Exception:                                    # noqa: BLE001
            pass

    def _olvas(self, futas: Futas) -> None:
        """A motor stdout-ját olvassa: JSON-sor = esemény, minden más a napló vége (váratlan leállásnál az üzenetbe)."""
        try:
            for sor in futas.proc.stdout:
                sor = sor.rstrip("\n")
                try:
                    d = json.loads(sor)
                    if isinstance(d, dict) and "szakasz" in d:
                        self._esemeny(futas, d)
                        continue
                except ValueError:
                    pass
                futas.log = (futas.log + [sor])[-LOG_VEGE:]
        finally:
            try:
                futas.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                futas.proc.kill()
            try:
                futas.proc.stdout.close()
            except OSError:
                pass
            if futas.allapot == "fut":                       # a motor végeredmény nélkül állt le
                uzenet = "a C++ motor váratlanul leállt" + (": " + " | ".join(futas.log[-3:]) if futas.log else "")
                self._esemeny(futas, {"szakasz": "hiba", "kod": "motor_hiba", "uzenet": uzenet})
            with self._zar:
                if self._aktiv is futas:
                    self._aktiv = None

    def futas(self, fid: str) -> dict:
        f = self._futasok.get(fid) if FUTAS_ID.match(fid or "") else None
        if f is None:
            raise kodol(NotFound(f"nincs ilyen futás: {fid}"), "cpp_utvonal.nincs_ilyen_futas_fid", {"fid": fid})
        return f.adat()

    def megszakit(self, d: dict) -> dict:
        fid = d.get("futas")
        if not isinstance(fid, str) or not fid:
            raise kodol(Invalid("hiányzik a `futas`"), "cpp_utvonal.hianyzik_futas")
        f = self._futasok.get(fid) if FUTAS_ID.match(fid) else None
        if f is None:
            raise kodol(NotFound(f"nincs ilyen futás: {fid}"), "cpp_utvonal.nincs_ilyen_futas_fid", {"fid": fid})
        if f.allapot != "fut":
            return {"megszakitva": False, "allapot": f.allapot}
        self._leallit(f)
        return {"megszakitva": True, "allapot": f.allapot}

    def _leallit(self, f: Futas) -> None:
        """SIGTERM a motornak (az a futó gyermekeit maga állítja le); `MEGSZAKIT_VARAKOZAS_S` után SIGKILL a folyamatcsoportra."""
        f.megszakit_kerve = True
        try:
            f.proc.send_signal(signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return

        def kenyszer():
            try:
                f.proc.wait(timeout=MEGSZAKIT_VARAKOZAS_S)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(f.proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        threading.Thread(target=kenyszer, daemon=True).start()

    def leallit(self) -> None:
        """A core leállása: a futó ellenőrzés és AI-kérés megszakad, nem marad árva `clang++` vagy teszt-folyamat."""
        self.ai.leallit()
        self.kod.leallit()
        with self._zar:
            self._leallt = True
            aktiv = self._aktiv
        if aktiv is not None and aktiv.allapot == "fut":
            self._leallit(aktiv)
            try:
                aktiv.proc.wait(timeout=MEGSZAKIT_VARAKOZAS_S + 3)
            except subprocess.TimeoutExpired:
                pass


def utvonalak(r) -> None:
    r.get("/api/cpp/allapot", lambda k: k.app.cpp.allapot())
    r.get("/api/cpp/feladat", lambda k: k.app.cpp.feladat(k.q.get("ut")))
    r.post("/api/cpp/feladat", lambda k: Valasz(201, k.app.cpp.uj_feladat(k.torzs())))
    r.post("/api/cpp/ellenoriz", lambda k: k.app.cpp.ellenoriz(k.torzs()))
    r.get(re.compile(r"/api/cpp/futas/([^/]+)"), lambda k: k.app.cpp.futas(k.m.group(1)))
    r.post("/api/cpp/megszakit", lambda k: k.app.cpp.megszakit(k.torzs()))
    r.post("/api/cpp/formaz", lambda k: k.app.cpp.formaz(k.torzs()))
    cpp_ai.utvonalak(r)
    from . import kod_utvonal
    kod_utvonal.utvonalak(r)                 # F10: /api/kod/*
