"""F6: Model Manager háttere — manifeszt, telepítettség a lemezről, mockolt HF-letöltés (haladás, hash, megszakítás, folytatás,
host-kapu), törlés a kalibráció visszavonásával, a kódba költözött küszöb, „Test this model” álworkerrel, aranyhalmaz-csomag és
saját-halmaz varázsló, a `/api/modellek/*` kezelői, a füzetlánc 409-e és az AI-hibaszerződés. Hálózat és valódi modell nincs."""
import contextlib
import hashlib
import io
import json
import os
import threading
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from core import letoltes
from core.modell import aranycsomag as A
from core.modell import api, halmaz, hibaszerzodes, kalibracio, kuszob, manifeszt, revizio
from core.modell import eval as ev
from core.modell import teszt as T
from core.modell.kalibracio import Tabla
from core.modell.worker import Gazda, Szerver, _handler
from core.utvonalak import HttpError, Regiszter
from tests.helpers import REPO, alg_core, tmpdir
from tests.modell_segedek import AlAktivitas, al_betolto, beallitas

MAN = manifeszt.betolt(fajl=REPO / "config" / "models.toml")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class AlForras:
    """A HF álja: a fájlokat a HF-gyorsítótár szerkezetében írja (blob = sha256, snapshot-link), hálózat nélkül."""

    def __init__(self, fajlok: dict[str, bytes], rossz: set | None = None, nevek: list | None = None):
        self.adat, self.rossz, self.hivasok = fajlok, rossz or set(), []
        self.nevek = nevek

    def fajlok(self, repo, rev, minta):
        return [{"nev": n, "meret": len(b), "sha256": _sha(b), "blob_id": None} for n, b in self.adat.items()] \
            if self.nevek is None else self.nevek

    def letolt(self, repo, rev, nev, cache_dir):
        self.hivasok.append(nev)
        b = self.adat[nev] + (b"x" if nev in self.rossz else b"")
        repo_d = Path(cache_dir) / f"models--{repo.replace('/', '--')}"
        blob = repo_d / "blobs" / _sha(b)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b)
        link = repo_d / "snapshots" / rev / nev
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(os.path.relpath(blob, link.parent))
        return link


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = alg_core(self._t.name)
        self.models = self.cfg.path("models")
        self.man = manifeszt.betolt(self.cfg)


# ====================================================================== manifeszt

class ManifesztTest(unittest.TestCase):
    def test_a_manifeszt_es_a_regiszter_egyezik(self):
        with open(REPO / "config" / "os.toml", "rb") as f:
            os_toml = tomllib.load(f)
        reg = os_toml["modellek"]
        self.assertEqual(list(MAN["modell"]), list(reg))
        for n, m in MAN["modell"].items():
            r = reg[n]
            with self.subTest(modell=n):
                self.assertEqual((m["repo"], m["revizio"], m.get("minta"), m["csucs_gb"], m["futtato"], bool(m.get("konvertalas")),
                                  m["feladat"]),
                                 (r["repo"], r["revizio"], r.get("minta"), r["csucs_gb"], r["futtato"], bool(r.get("konvertalas")),
                                  r["feladat"]))
                self.assertIn(m["szerep"], r["kepessegek"])
                self.assertNotIn("megvan", m)                           # a telepítettség a lemezről, nem kézi jelző
                self.assertIsInstance(m["ajanlott"], bool)
        self.assertEqual(MAN["modell"]["whisper_large_v3_hu"]["nyelvek"], ["hu"])

    def test_feladatok_funkciok_es_kuszobok(self):
        with open(REPO / "config" / "os.toml", "rb") as f:
            router = set(tomllib.load(f)["router"]["feladatok"])
        self.assertEqual(set(MAN["feladat"]), router)
        self.assertEqual(set(kuszob.ALAP), router)                          # minden router-feladatnak van kód-küszöbe (vagy None)
        for f, v in MAN["feladat"].items():
            self.assertTrue(v["cim"] and v["leiras"], f)
        for fn, v in MAN["funkcio"].items():
            self.assertTrue(set(v["feladatok"]) <= router, fn)
        for f, k in MAN["kalibracio"].items():                              # a konfig a kóddal egyezik (szigoríthat, lazítani nem)
            with self.subTest(feladat=f):
                self.assertEqual((k["kuszob"], k["min_tetel"]), (kuszob.ALAP[f].kuszob, kuszob.ALAP[f].min_tetel))

    def test_host_kapu(self):
        ok = manifeszt.host_engedelyezett
        self.assertTrue(ok(MAN, "https://huggingface.co/api/models/x"))
        self.assertTrue(ok(MAN, "https://cdn-lfs.huggingface.co/a"))
        self.assertTrue(ok(MAN, "https://cas-bridge.xethub.hf.co/a"))
        for rossz in ("http://huggingface.co/a", "https://evil.com/a", "https://huggingface.co.evil.com/",
                      "https://user:pw@huggingface.co/", "https://huggingface.co:8443/", "file:///etc/passwd", "https://hf.co.evil/"):
            self.assertFalse(ok(MAN, rossz), rossz)
        self.assertEqual(manifeszt.vegpont(MAN), "https://huggingface.co")
        with self.assertRaises(manifeszt.ManifesztHiba) as e:
            manifeszt.vegpont({**MAN, "forras": {**MAN["forras"], "vegpont": "https://mirror.example/"}})
        self.assertEqual(e.exception.kod, "modell.host_tiltott")

    def test_a_hf_kliens_kerese_host_kapun_megy_at(self):
        import httpx
        gyar = {}
        with mock.patch("huggingface_hub.set_client_factory", side_effect=lambda f: gyar.setdefault("f", f)):
            letoltes.HfForras(MAN)
        kliens = gyar["f"]()
        try:
            kapu = kliens.event_hooks["request"][0]
            kapu(httpx.Request("GET", "https://huggingface.co/api/models"))
            with self.assertRaises(letoltes.LetoltesHiba) as e:
                kapu(httpx.Request("GET", "https://evil.example/x"))
            self.assertEqual(e.exception.kod, "modell.host_tiltott")
        finally:
            kliens.close()

    def test_hibas_manifeszt(self):
        with self.assertRaises(manifeszt.ManifesztHiba):
            manifeszt.modell(MAN, "../x")
        with self.assertRaises(manifeszt.ManifesztHiba) as e:
            manifeszt.modell(MAN, "nincs_ilyen")
        self.assertEqual(e.exception.kod, "modell.ismeretlen")


# ====================================================================== letöltés és telepítettség

class LetoltesTest(Alap):
    NEV = "qwen35_08b"

    def m(self):
        return self.man["modell"][self.NEV]

    def allapot(self):
        return manifeszt.telepitettseg(self.models, self.NEV, self.m())["allapot"]

    def test_letoltes_halad_ellenoriz_es_nyugtat_ir(self):
        self.assertEqual(self.allapot(), "nincs")
        f = AlForras({"config.json": b"{}", "model.safetensors": b"w" * 5000})
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            e = letoltes.modell_letolt(self.cfg, self.NEV, forras=f, log=lambda s: None)
        self.assertEqual((e["allapot"], e["fajlok"]), ("kesz", 2))
        self.assertIn("[manifold-progress] 100.0%", ki.getvalue())
        self.assertEqual(self.allapot(), "kesz")
        t = manifeszt.telepitettseg(self.models, self.NEV, self.m())
        self.assertGreaterEqual(t["lemez_bajt"], 5002)
        self.assertTrue(t["ellenorizve"])
        f2 = AlForras(f.adat)                                       # újra: minden megvan és ellenőrzött, semmi nem töltődik
        with contextlib.redirect_stdout(io.StringIO()):
            letoltes.modell_letolt(self.cfg, self.NEV, forras=f2, log=lambda s: None)
        self.assertEqual(f2.hivasok, [])

    def test_hash_elteres_torli_a_fajlt(self):
        f = AlForras({"a.json": b"{}", "b.bin": b"abc"}, rossz={"b.bin"})
        with self.assertRaises(letoltes.LetoltesHiba) as e, contextlib.redirect_stdout(io.StringIO()):
            letoltes.modell_letolt(self.cfg, self.NEV, forras=f, log=lambda s: None)
        self.assertEqual((e.exception.kod, e.exception.param["fajl"]), ("modell.hash_elter", "b.bin"))
        snap = revizio.repo_mappa(self.models, self.m()["repo"]) / "snapshots" / self.m()["revizio"]
        self.assertFalse((snap / "b.bin").exists())
        self.assertEqual(self.allapot(), "reszleges")

    def test_megszakitas_utan_folytatja(self):
        f = AlForras({"a.json": b"{}", "b.bin": b"abc", "c.bin": b"def"})
        hivas = {"n": 0}

        def stop():
            hivas["n"] += 1
            return hivas["n"] == 2                                   # az első fájl után megáll
        with contextlib.redirect_stdout(io.StringIO()):
            e = letoltes.modell_letolt(self.cfg, self.NEV, forras=f, stop=stop, log=lambda s: None)
        self.assertEqual((e["allapot"], f.hivasok), ("megszakitva", ["a.json"]))
        self.assertEqual(self.allapot(), "reszleges")
        f2 = AlForras(f.adat)
        with contextlib.redirect_stdout(io.StringIO()):
            letoltes.modell_letolt(self.cfg, self.NEV, forras=f2, log=lambda s: None)
        self.assertEqual(f2.hivasok, ["b.bin", "c.bin"])              # a kész fájl nem töltődik újra
        self.assertEqual(self.allapot(), "kesz")

    def test_hely_fajlnev_es_ures_forras(self):
        f = AlForras({"a.bin": b"x" * 100})
        with self.assertRaises(letoltes.LetoltesHiba) as e:
            letoltes.modell_letolt(self.cfg, self.NEV, forras=f, szabad=lambda d: 10)
        self.assertEqual(e.exception.kod, "modell.nincs_hely")
        rossz = AlForras({}, nevek=[{"nev": "../../kiszokik", "meret": 1, "sha256": None}])
        with self.assertRaises(letoltes.LetoltesHiba) as e:
            letoltes.modell_letolt(self.cfg, self.NEV, forras=rossz)
        self.assertEqual(e.exception.kod, "modell.tiltott_fajlnev")
        with self.assertRaises(letoltes.LetoltesHiba) as e:
            letoltes.modell_letolt(self.cfg, self.NEV, forras=AlForras({}, nevek=[]))
        self.assertEqual(e.exception.kod, "modell.nincs_fajl")

    def test_allapotok_a_lemezrol(self):
        repo_d = revizio.repo_mappa(self.models, self.m()["repo"])
        (repo_d / "snapshots" / ("b" * 40)).mkdir(parents=True)
        self.assertEqual(self.allapot(), "elter_revizio")
        (repo_d / "snapshots" / self.m()["revizio"]).mkdir(parents=True)
        self.assertEqual(self.allapot(), "ellenorizetlen")           # régi CLI-letöltés / v2-import: használható, nem ellenőrzött
        (repo_d / "blobs").mkdir()
        (repo_d / "blobs" / "abc.incomplete").write_bytes(b"x")
        self.assertEqual(self.allapot(), "reszleges")
        hu = self.man["modell"]["whisper_large_v3_hu"]
        snap = revizio.repo_mappa(self.models, hu["repo"]) / "snapshots" / hu["revizio"]
        snap.mkdir(parents=True)
        self.assertEqual(manifeszt.telepitettseg(self.models, "whisper_large_v3_hu", hu)["allapot"], "konvertalasra_var")

    def test_torles_csak_a_modelltarban(self):
        with contextlib.redirect_stdout(io.StringIO()):
            letoltes.modell_letolt(self.cfg, self.NEV, forras=AlForras({"a.bin": b"abc"}), log=lambda s: None)
        e = manifeszt.torol(self.models, self.NEV, self.m())
        self.assertGreater(e["felszabadult_bajt"], 0)
        self.assertEqual(self.allapot(), "nincs")
        self.assertIsNone(manifeszt.nyugta(self.models, self.NEV))
        kint = Path(self._t.name) / "kint"
        kint.mkdir()
        repo_d = revizio.repo_mappa(self.models, self.m()["repo"])
        repo_d.symlink_to(kint)                                    # a repó-mappa egy idegen helyre mutató link: nem törlünk
        with self.assertRaises(manifeszt.ManifesztHiba):
            manifeszt.torol(self.models, self.NEV, self.m())
        self.assertTrue(kint.is_dir())

    def test_a_feladat_lepes_riportot_ir(self):
        stop = Path(self._t.name) / "stop"
        with mock.patch.object(letoltes.config, "load", return_value=self.cfg), \
                mock.patch.dict(os.environ, {"MANIFOLD_STOP_FAJL": str(stop)}), \
                mock.patch.object(letoltes, "modell_letolt", return_value={"allapot": "kesz", "fajlok": 1, "bajt": 3}) as ml, \
                contextlib.redirect_stdout(io.StringIO()) as ki:
            self.assertEqual(letoltes.main(["--feladat", self.NEV]), 0)
            self.assertEqual(os.environ["HF_HUB_DISABLE_XET"], "1")
        self.assertIn("Riport:", ki.getvalue())
        self.assertFalse(ml.call_args.kwargs["stop"]())
        r = json.loads((self.cfg.path("runs") / "modell-letoltes" / f"{self.NEV}-riport.json").read_text())
        self.assertEqual(r["allapot"], "kesz")
        with mock.patch.object(letoltes.config, "load", return_value=self.cfg), \
                mock.patch.object(letoltes, "modell_letolt",
                                  side_effect=letoltes.LetoltesHiba("x", "modell.nincs_hely", szukseges_gb=3.0)), \
                contextlib.redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(letoltes.main(["--feladat", self.NEV]), 2)
        r = json.loads((self.cfg.path("runs") / "modell-letoltes" / f"{self.NEV}-riport.json").read_text())
        self.assertEqual((r["kod"], r["param"]), ("modell.nincs_hely", {"szukseges_gb": 3.0}))


# ====================================================================== küszöb

class KuszobTest(Alap):
    def test_dont(self):
        ert = {"pontszam": 0.72, "n": 60, "tetelszam": 60, "modok": {"hiba": 0.6}}
        self.assertTrue(kuszob.dont("kod", ert)["kalibralhato"])
        self.assertEqual([o["kod"] for o in kuszob.dont("kod", {**ert, "modok": {"hiba": 0.4}})["okok"]], ["modell.reszpont_alatt"])
        self.assertEqual([o["kod"] for o in kuszob.dont("kod", {**ert, "pontszam": 0.5})["okok"]], ["modell.kuszob_alatt"])
        self.assertEqual([o["kod"] for o in kuszob.dont("szoveg", {"pontszam": 0.9, "n": 5, "tetelszam": 5})["okok"]],
                         ["modell.keves_tetel"])
        self.assertEqual(kuszob.dont("tema", {"pontszam": 1.0, "n": 300, "tetelszam": 300})["okok"][0]["kod"], "modell.kuszob_nincs")
        self.assertFalse(kuszob.dont("ismeretlen", {"pontszam": 1.0, "n": 99})["kalibralhato"])

    def test_a_konfig_csak_szigorithat(self):
        self.assertEqual(kuszob.hatalyos("szoveg", {"szoveg": {"kuszob": 0.1, "min_tetel": 2}}).kuszob, 0.40)
        self.assertEqual(kuszob.hatalyos("szoveg", {"szoveg": {"kuszob": 0.1, "min_tetel": 2}}).min_tetel, 20)
        k = kuszob.hatalyos("szoveg", {"szoveg": {"kuszob": 0.55, "min_tetel": 30}})
        self.assertEqual((k.kuszob, k.min_tetel), (0.55, 30))
        self.assertIsNone(kuszob.hatalyos("tema", {"tema": {"kuszob": 0.5}}).kuszob)       # konfigból sem lesz küszöb

    def test_eval_rogzit_kikenyszeriti(self):
        ert = {"router_feladat": "szoveg", "modell": "qwen35_2b", "pontszam": 0.3, "aranyhalmaz_verzio": "szoveg-v1", "n": 40,
               "tetelszam": 40, "teljes": True, "ervenyes": True, "ervenyesseg": {}}
        with self.assertRaisesRegex(ValueError, "kuszob_alatt"):
            ev.rogzit(self.cfg, ert, True)
        self.assertEqual(ev.rogzit(self.cfg, ert, None)["kalibralt"], 0)            # jel nélkül rögzíthető
        self.assertEqual(ev.rogzit(self.cfg, {**ert, "pontszam": 0.45}, True)["kalibralt"], 1)
        with self.assertRaisesRegex(ValueError, "keves_tetel"):
            ev.rogzit(self.cfg, {**ert, "pontszam": 0.9, "n": 8, "tetelszam": 8}, True)

    def test_jel_levetel_modellenkent(self):
        t = Tabla(self.cfg.path("router_db"))
        self.addCleanup(t.close)
        t.rogzit("szoveg", "qwen35_4b", 0.6, "v1", kalibralt=True)
        t.rogzit("kviz", "qwen35_4b", 0.5, "v1", kalibralt=True)
        t.rogzit("szoveg", "qwen35_9b", 0.7, "v1", kalibralt=True)
        self.assertEqual(sorted(t.modell_jel_levesz("qwen35_4b", "törölve")), ["kviz", "szoveg"])
        self.assertEqual([s["modell"] for s in t.kalibralt_sorrend("szoveg")], ["qwen35_9b"])
        sor = t.tabla("kviz")[0]
        self.assertEqual((sor["kalibralt"], sor["pontszam"]), (0, 0.5))
        self.assertTrue(sor["megjegyzes"].startswith("törölve"))


# ====================================================================== Test this model (álworker)

def _feladat_py(n: int, router: str = "szoveg") -> str:
    return f'''
VERZIO = "{router}-teszt-v1"
ROUTER_FELADAT = "{router}"

def tetelek(cfg):
    for i in range({n}):
        yield {{"id": f"t{{i:02d}}", "keres": {{"messages": [{{"role": "user", "content": f"kérdés {{i}}"}}], "max_tokens": 100}},
               "vart": "qwen35_2b: válasz" if i % 2 == 0 else "más"}}

def pontoz(rekordok):
    jo = sum(1 for r in rekordok if r["valasz"] == r["vart"])
    return {{"pontszam": jo / len(rekordok) if rekordok else 0.0, "helyes": jo}}
'''


class TesztFolyamTest(Alap):
    def setUp(self):
        super().setUp()
        d = self.cfg.path("modulok") / "eval" / "szoveg"
        d.mkdir(parents=True)
        (d / "feladat.py").write_text(_feladat_py(20), encoding="utf-8")
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.tabla = Tabla(self.b.router_db)
        self.addCleanup(self.tabla.close)
        self.g = Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla, tick_mp=0.02, naplo=lambda s: None)
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.u = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close(), self.g.utemezo.leall()))
        m = self.man["modell"]["qwen35_2b"]
        (revizio.repo_mappa(self.models, m["repo"]) / "snapshots" / m["revizio"]).mkdir(parents=True)   # „ellenőrizetlen”

    def futtat(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return T.futtat(self.cfg, "qwen35_2b", "szoveg", self.u, log=lambda s: None, mod="interaktiv", **kw)

    def test_elopróba_meres_es_kalibralt_jel(self):
        e = self.futtat()
        self.assertEqual((e["allapot"], e["jel"], e["okok"]), ("kesz", "kalibralt", []))
        self.assertEqual((e["ertekeles"]["pontszam"], e["ertekeles"]["n"], e["kuszob"]), (0.5, 20, 0.40))
        self.assertEqual(self.tabla.kalibralt_sorrend("szoveg")[0]["modell"], "qwen35_2b")
        self.assertTrue((self.cfg.path("tmp") / "eval-proba" / "szallitott" / "qwen35_2b" / "szoveg.jsonl").is_file())
        r = json.loads(T.riport_ut(self.cfg, "qwen35_2b", "szoveg").read_text())
        self.assertEqual(r["jel"], "kalibralt")

    def test_kuszob_alatt_proba_es_a_regi_jel_lekerul(self):
        self.futtat()
        with mock.patch.dict(kuszob.ALAP, {"szoveg": kuszob.Kuszob(0.6, 20)}):
            e = self.futtat()
        self.assertEqual((e["jel"], [o["kod"] for o in e["okok"]]), ("proba", ["modell.kuszob_alatt"]))
        self.assertEqual(self.tabla.kalibralt_sorrend("szoveg"), [])
        self.assertEqual(self.tabla.tabla("szoveg")[0]["pontszam"], 0.5)

    def test_elofeltetel_es_eloproba(self):
        m = self.man["modell"]["qwen35_2b"]
        import shutil
        shutil.rmtree(revizio.repo_mappa(self.models, m["repo"]))
        e = self.futtat()
        self.assertEqual((e["allapot"], e["okok"][0]["kod"]), ("elofeltetel", "modell.nincs_telepitve"))
        (revizio.repo_mappa(self.models, m["repo"]) / "snapshots" / m["revizio"]).mkdir(parents=True)
        self.assertEqual(T.elofeltetel(self.cfg, "qwen35_2b", "ismeretlen_f")[0]["kod"], "modell.feladat_ismeretlen")
        self.assertEqual(T.elofeltetel(self.cfg, "qwen35_2b", "kviz")[0]["kod"], "modell.halmaz_nincs")
        valodi = ev.ertekel
        def rossz(*a, **k):
            r = valodi(*a, **k)
            return {**r, "ervenyes": False, "ervenyesseg": {**r["ervenyesseg"], "ervenyes": False, "levagott": 3}}
        with mock.patch.object(ev, "ertekel", side_effect=rossz):
            e = self.futtat()
        self.assertEqual((e["allapot"], e["jel"], e["okok"][0]["kod"]), ("eloproba_bukott", "proba", "modell.eloproba_ervenytelen"))
        self.assertFalse((self.cfg.path("runs") / "eval" / "qwen35_2b" / "szoveg.jsonl").exists())    # az éles mérés el sem indult

    def test_megallitas(self):
        e = self.futtat(stop=lambda: True)
        self.assertEqual((e["allapot"], e["jel"]), ("megallitva", "proba"))
        self.assertEqual(self.tabla.tabla("szoveg"), [])


# ====================================================================== aranyhalmazok

class AranycsomagTest(Alap):
    def setUp(self):
        super().setUp()
        (self.root / "modulok").symlink_to(REPO / "modulok")          # a szállított eval-mappák (csak olvasva)

    def test_szallitott_csomag_vault_nelkul_merheto(self):
        sorok = {s["feladat"]: s for s in A.lista(self.cfg)}
        self.assertEqual(set(sorok), {"kod", "kiegeszites", "matek", "matek_cas", "matek_ellenorzo"})
        for f, s in sorok.items():
            with self.subTest(feladat=f):
                self.assertNotIn(s["allapot"], ("hibas", "hianyzik"), s.get("hiba"))
                self.assertTrue(s["nyelv"] and s["licenc"] and s["forras"])
                self.assertGreaterEqual(s["tetelszam"], s["min_tetel"] if s["allapot"] == "jovahagyott" else 1)
        self.assertEqual((sorok["kod"]["allapot"], sorok["kod"]["tetelszam"], sorok["kod"]["kalibralhato"]), ("jovahagyott", 60, True))
        self.assertEqual(sorok["kiegeszites"]["allapot"], "vazlat")
        self.assertEqual(list(self.vault.iterdir()), [self.vault / ".obsidian"])     # a vaulthoz nem nyúlt

    def _kieg(self, n=12):
        return [{"elotte": f"Előzmény {i}: ", "utana": "", "elfogadhato": [f"válasz {i}"]} for i in range(n)]

    def test_sajat_halmaz_varazslo_es_router_verzio(self):
        o = A.letrehoz(self.cfg, "kiegeszites", self._kieg())
        self.assertEqual((o["allapot"], o["tetelszam"], o["valasztva"]), ("vazlat", 12, False))
        with self.assertRaises(A.HalmazHiba) as e:
            A.valaszt(self.cfg, "kiegeszites", "sajat")
        self.assertEqual(e.exception.kod, "modell.halmaz_vazlat")
        with self.assertRaises(A.HalmazHiba) as e:
            A.jovahagy(self.cfg, "kiegeszites", [f"s{i:03d}" for i in range(1, 11)])
        self.assertEqual(e.exception.kod, "modell.keves_tetel")
        o = A.jovahagy(self.cfg, "kiegeszites", [f"s{i:03d}" for i in range(1, 13)])
        self.assertEqual(o["allapot"], "jovahagyott")
        verziok = halmaz.Verziok(self.cfg.path("modulok"), A.sajat_gyoker(self.cfg))
        szall = verziok("kiegeszites")
        self.assertNotIn("-sajat-", szall)
        A.valaszt(self.cfg, "kiegeszites", "sajat")
        sajat_v = verziok("kiegeszites")
        self.assertRegex(sajat_v, r"^kiegeszites-sajat-[0-9a-f]{10}$")
        mod = ev.feladat_modul(self.cfg, "kiegeszites", "sajat")
        self.assertEqual((mod.VERZIO, mod.MERO), (sajat_v, "sajat"))
        tetelek = list(mod.tetelek(self.cfg))
        self.assertEqual(len(tetelek), 12)
        self.assertIn("Előzmény 0", json.dumps(tetelek[0]["keres"], ensure_ascii=False))
        A.torol(self.cfg, "kiegeszites")
        self.assertEqual(verziok("kiegeszites"), szall)                       # a választás visszaállt a szállítottra
        self.assertTrue(any((A.sajat_gyoker(self.cfg) / ".torolt").iterdir()))

    def test_kijeloles_a_vaultbol_fagyaszt_csak_olvasva(self):
        jegyzet = self.vault / "Bio" / "Sejt.md"
        jegyzet.parent.mkdir()
        jegyzet.write_text("# Sejt\n\nA mitokondrium a sejt energiaüzeme, ATP-t termel.\n", encoding="utf-8")
        elotte = jegyzet.stat().st_mtime_ns
        t = {"ut": "Bio/Sejt.md", "kezd": "A mitokondrium", "veg": "termel.", "kulcs": [["ATP"]], "tema": [["energia"]]}
        A.letrehoz(self.cfg, "kifejtes", [t])
        d = A.sajat(self.cfg, "kifejtes")
        self.assertEqual(d["tetel"][0]["kijeloles"], "A mitokondrium a sejt energiaüzeme, ATP-t termel.")
        self.assertEqual(jegyzet.stat().st_mtime_ns, elotte)
        for rossz in ({**t, "ut": "../kint.md"}, {**t, "ut": "/etc/passwd.md"}, {**t, "kezd": "nincs ilyen"}, {**t, "ut": "Bio/Nincs.md"}):
            with self.subTest(t=rossz), self.assertRaises(A.HalmazHiba):
                A.letrehoz(self.cfg, "kifejtes", [rossz])
        with self.assertRaises(A.HalmazHiba) as e:
            A.letrehoz(self.cfg, "szoveg", [t])
        self.assertEqual(e.exception.kod, "modell.sajat_nem_tamogatott")


# ====================================================================== API-kezelők

class AlSor:
    def __init__(self):
        self.feladatok, self.leallitva = [], []

    def submit(self, tipus, params=None, priority=0):
        d = {"id": f"F{len(self.feladatok)}", "tipus": tipus, "parameterek": dict(params or {}), "allapot": "sorban", "szazalek": 0}
        self.feladatok.append(d)
        return d

    def list(self, limit=40):
        return list(self.feladatok)

    def stop(self, fid, immediate=False):
        self.leallitva.append((fid, immediate))
        return {"id": fid, "allapot": "megallitva"}


class AlApp:
    def __init__(self, cfg):
        self.cfg, self.queue, self.worker = cfg, AlSor(), None


class AlKeres:
    def __init__(self, app, m=None, torzs=None):
        self.app, self.m, self._t = app, m, torzs or {}

    def torzs(self):
        return self._t


class ApiTest(Alap):
    def setUp(self):
        super().setUp()
        self.r = Regiszter()
        api.utvonalak(self.r)
        self.app = AlApp(self.cfg)

    def hiv(self, metodus, ut, torzs=None):
        kezelo, m = self.r.keres(metodus, ut)
        return kezelo(AlKeres(self.app, m, torzs))

    def test_lista_es_reszlet(self):
        d = self.hiv("GET", "/api/modellek")
        m = {x["id"]: x for x in d["modellek"]}
        self.assertEqual(m["glm_ocr"]["allapot"], "nincs")
        self.assertTrue(m["glm_ocr"]["ajanlott"])
        self.assertEqual(d["feladatok"]["ocr_keplet"]["kuszob"], 0.90)
        self.assertIn("keplet_ocr", d["feladatok"]["ocr_keplet"]["funkciok"])
        self.assertEqual(d["keretek"], {"munka": 5.0, "tavol": 9.0})
        self.assertEqual(self.hiv("GET", "/api/modellek/glm_ocr")["repo"], "mlx-community/GLM-OCR-4bit")
        with self.assertRaises(HttpError) as e:
            self.hiv("GET", "/api/modellek/nincs_ilyen")
        self.assertEqual((e.exception.code, e.exception.kod), (404, "modell.ismeretlen"))

    def test_letoltes_feladatkent_utkozes_es_megszakitas(self):
        v = self.hiv("POST", "/api/modellek/glm_ocr/letoltes")
        self.assertEqual((v.kod, v.obj["feladat"]["tipus"], v.obj["feladat"]["parameterek"]), (202, api.LETOLTES, {"modell": "glm_ocr"}))
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/glm_ocr/letoltes")
        self.assertEqual((e.exception.code, e.exception.kod), (409, "modell.letoltes_fut"))
        self.assertEqual(self.hiv("GET", "/api/modellek/glm_ocr")["letoltes"]["feladat_id"], "F0")
        self.hiv("POST", "/api/modellek/glm_ocr/letoltes/megszakitas")
        self.assertEqual(self.app.queue.leallitva, [("F0", True)])

    def test_a_feladat_terve_halozati_lepes_token_nelkul(self):
        from core import lepes_kapu, tasks
        lepesek, osszegzes, _ = tasks.REGISTRY[api.LETOLTES].plan(self.cfg, {"modell": "glm_ocr"}, "/x/stop")
        self.assertEqual(lepesek[0].argv[-3:], ["core.letoltes", "--feladat", "glm_ocr"])
        self.assertEqual(lepesek[0].jogok, lepes_kapu.JOGOK_NINCS)
        self.assertIn("GLM-OCR", osszegzes)
        with self.assertRaises(tasks.Invalid):
            tasks.REGISTRY[api.LETOLTES].plan(self.cfg, {"modell": "nincs"}, "/x/stop")
        lepesek, _, _ = tasks.REGISTRY[api.TESZT].plan(self.cfg, {"modell": "glm_ocr", "feladat": "ocr_keplet"}, "/x/stop")
        self.assertEqual(lepesek[0].argv[-5:], ["core.modell.teszt", "glm_ocr", "ocr_keplet", "--halmaz", "szallitott"])
        self.assertEqual(tasks.REGISTRY[api.TESZT].resources, frozenset({"modell"}))

    def test_torles_megerositessel_es_a_kalibracio_levetelevel(self):
        m = self.man["modell"]["glm_ocr"]
        snap = revizio.repo_mappa(self.models, m["repo"]) / "snapshots" / m["revizio"]
        snap.mkdir(parents=True)
        (snap / "w.bin").write_bytes(b"123")
        t = kalibracio.megnyit(self.cfg)
        t.rogzit("ocr_keplet", "glm_ocr", 0.95, "v1", kalibralt=True)
        t.close()
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/glm_ocr/torles", {})
        self.assertEqual((e.exception.code, e.exception.kod), (409, "modell.megerosites_kell"))
        d = self.hiv("POST", "/api/modellek/glm_ocr/torles", {"megerosit": True})
        self.assertEqual((d["kalibracio_levett"], d["felszabadult_bajt"]), (["ocr_keplet"], 3))
        self.assertEqual(self.hiv("GET", "/api/modellek/glm_ocr")["allapot"], "nincs")
        self.assertFalse(self.hiv("GET", "/api/modellek/glm_ocr")["kalibracio"][0]["kalibralt"])
        self.hiv("POST", "/api/modellek/glm_ocr/letoltes")
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/glm_ocr/torles", {"megerosit": True})
        self.assertEqual(e.exception.kod, "modell.foglalt")

    def test_teszt_inditasa_elofeltetellel(self):
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/glm_ocr/teszt", {"feladat": "ocr_keplet"})
        self.assertEqual((e.exception.code, e.exception.kod), (400, "modell.nincs_telepitve"))
        self.assertEqual(e.exception.data["okok"][0]["param"]["modell"], "glm_ocr")
        with mock.patch.object(T, "elofeltetel", return_value=[]):
            v = self.hiv("POST", "/api/modellek/glm_ocr/teszt", {"feladat": "ocr_keplet"})
            self.assertEqual((v.kod, v.obj["feladat"]["tipus"]), (202, api.TESZT))
            with self.assertRaises(HttpError) as e:
                self.hiv("POST", "/api/modellek/qwen35_4b/teszt", {"feladat": "szoveg"})
            self.assertEqual(e.exception.kod, "modell.teszt_fut")          # egyszerre egy mérés
        with self.assertRaises(HttpError) as e:
            self.hiv("GET", "/api/modellek/glm_ocr/teszt/ocr_keplet")
        self.assertEqual(e.exception.code, 404)
        ut = T.riport_ut(self.cfg, "glm_ocr", "ocr_keplet")
        ut.parent.mkdir(parents=True)
        ut.write_text(json.dumps({"jel": "proba"}))
        self.assertEqual(self.hiv("GET", "/api/modellek/glm_ocr/teszt/ocr_keplet"), {"jel": "proba"})

    def test_halmaz_vegpontok(self):
        d = self.hiv("GET", "/api/modellek/halmazok")
        self.assertEqual(d["tamogatott"], ["kiegeszites", "kifejtes", "osszefoglal_kijeloles"])
        o = self.hiv("POST", "/api/modellek/halmazok/kiegeszites",
                     {"tetelek": [{"elotte": "a", "utana": "", "elfogadhato": ["b"]}] * 12})
        self.assertEqual((o["allapot"], o["tetelszam"]), ("vazlat", 12))
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/halmazok/kiegeszites/valasztas", {"halmaz": "sajat"})
        self.assertEqual(e.exception.kod, "modell.halmaz_vazlat")
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/modellek/halmazok/kiegeszites", {"tetelek": [{"elotte": "a"}]})
        self.assertEqual((e.exception.code, e.exception.kod, e.exception.param), (400, "modell.sajat_hibas_tetel",
                                                                                 {"sor": 1, "mezo": "utana"}))


# ====================================================================== füzetlánc 409 és hibaszerződés

class FuzetEsHibaszerzodesTest(unittest.TestCase):
    def test_a_router_409_nincs_modell_egyszer(self):
        import sys
        sys.path.insert(0, str(REPO / "modulok"))
        self.addCleanup(sys.path.remove, str(REPO / "modulok"))
        from fuzet import modell as FM
        from core.modell import kliens
        mm = FM.Modellek(cfg=None, u="http://127.0.0.1:9")
        with mock.patch.object(kliens, "keres", side_effect=kliens.KliensHiba(
                409, "a(z) fuzet_fejezet feladatra nincs kalibrált modell", {"nincs_kalibralt": True})):
            with self.assertRaises(FM.NincsModell) as e:
                mm.modell_nev("fuzet_fejezet")
        self.assertEqual((e.exception.hiba_kod, e.exception.hiba_param), ("nincs_kalibralt", {"feladat": "fuzet_fejezet"}))
        with mock.patch.object(kliens, "keres", side_effect=kliens.KliensHiba(
                409, "most csak tartós tétlenségben fut", {"nincs_kalibralt": True})):
            with self.assertRaises(FM.NincsModell) as e:
                FM.Modellek(cfg=None, u="http://127.0.0.1:9").modell_nev("ocr_kezi")
        self.assertEqual(e.exception.hiba_kod, "csak_tavol")
        with mock.patch.object(kliens, "keres", side_effect=kliens.KliensHiba(409, "megszakítva", {"megszakitva": True})):
            with self.assertRaises(kliens.KliensHiba):                      # a megszakítás nem „nincs modell”
                FM.Modellek(cfg=None, u="http://127.0.0.1:9").modell_nev("ocr_kezi")

    def test_ai_hibaszerzodes(self):
        from core.modell import kliens
        from core.modell.router import RoutingHiba
        o = hibaszerzodes.osztalyoz
        self.assertEqual(o(kliens.KliensHiba(409, "x", {"nincs_kalibralt": True})), "nincs_kalibralt")
        self.assertEqual(o(RoutingHiba("most csak tartós tétlenségben")), "csak_tavol")
        self.assertEqual(o(kliens.KliensHiba(503, "a modell-worker nem indult el: x")), "nincs_ai_runtime")
        self.assertEqual(o(kliens.KliensHiba(503, "y", {"kapcsolat": True})), "nincs_ai_runtime")
        self.assertEqual(o(kliens.KliensHiba(500, "z")), "worker_hiba")
        self.assertEqual(hibaszerzodes.ai_mezo("szoveg", None, "kerdezz"),
                         {"kod": "nincs_kalibralt", "feladat": "szoveg", "funkcio": "kerdezz", "param": {}})
        e = HttpError(503, "x", kod="kereses_api.modell_nincs_kotve", ai=hibaszerzodes.ai_mezo("szoveg", None, "kerdezz"))
        self.assertEqual(e.torzs()["ai"]["kod"], "nincs_kalibralt")
        from core.hibauzenetek import ANGOL
        for k in hibaszerzodes.KODOK:
            self.assertIn(k, ANGOL)

    def test_minden_modell_hibakod_angol_tartalekkal(self):
        import re
        from core.hibauzenetek import ANGOL
        kodok = set()
        for p in [REPO / "core" / "letoltes.py", *(REPO / "core" / "modell").glob("*.py")]:
            kodok |= set(re.findall(r'"(modell\.[a-z_]+)"', p.read_text(encoding="utf-8")))
        self.assertTrue(kodok)
        self.assertEqual(sorted(k for k in kodok if k not in ANGOL), [])


if __name__ == "__main__":
    unittest.main()
