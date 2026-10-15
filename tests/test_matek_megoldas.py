"""C24b: a „Megoldás” (modell + CAS-homokozó → `[!solution]` callout gépi írással), a második vélemény, a levezetés-ellenőrzés
végpontja (margójel) és a `matek_megoldas` feladattípus. A modell, a core és a homokozó álpéldány; a valódi homokozós út csak
macOS-en. A valódi vaulthoz és `var/`-hoz egyik teszt sem nyúl."""
import hashlib
import json
import subprocess
import sys
import unittest

from tests.helpers import REPO, alg_core, tmpdir

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from matek import eredmeny as ER  # noqa: E402
from matek import lanc as LANC  # noqa: E402
from matek import megoldas as M  # noqa: E402

MACOS = sys.platform == "darwin"

JO_VALASZ = ("Megoldás.\n1. Az egyenlet: $x^2-5x+6=0$\n2. Szorzattá alakítva: $(x-2)(x-3)=0$\n3. A gyökök: $x=2 \\vee x=3$\n"
             "```python\nimport sympy as sp\nx = sp.Symbol('x', real=True)\n"
             "EREDMENY = sp.solveset(x**2 - 5*x + 6, x, sp.S.Reals)\n```")


class AlHomokozo:
    """Forgatókönyves homokozó: a `kod` és a `hivas` műveletre előre megadott eredményt ad, és naplóz."""

    def __init__(self, kod=None, levezetes=None, eredmeny=None):
        self.beall = {"lepes_idokorlat_s": 3.0, "idokorlat_s": 10.0}
        self.kod, self.levezetes, self.eredmeny = list(kod or []), levezetes, eredmeny
        self.feladatok = []

    def futtat(self, feladatok):
        ki = []
        for f in feladatok:
            self.feladatok.append(f)
            if f["muvelet"] == "kod":
                ki.append(self.kod.pop(0))
            else:
                ki.append({"allapot": "ok", "ertek": self.levezetes, "uzenet": ""})
        return ki

    def egy(self, f):
        self.feladatok.append(f)
        return {"allapot": "ok", "ertek": self.eredmeny(f["args"]) if callable(self.eredmeny) else self.eredmeny, "uzenet": ""}


def kod_ok(*elemek):
    return {"allapot": "ok", "ertek": {"tipus": "halmaz", "elemek": list(elemek)}, "uzenet": ""}


LV_RENDBEN = {"allapot": "rendben", "elso_hiba": None,
              "atmenetek": [{"honnan": 1, "hova": 2, "itelet": "ekvivalens"}, {"honnan": 2, "hova": 3, "itelet": "ekvivalens"}]}


class TisztaTest(unittest.TestCase):
    def test_kodblokk_lepesek_es_gondolkodas(self):
        v = {"choices": [{"message": {"content": "<think>```python\nEREDMENY = 9\n```</think>" + JO_VALASZ}}]}
        self.assertIn("solveset", M.kodblokk(v))
        lp = M.lepesek(v)
        self.assertEqual([l["keplet"] for l in lp], ["x^2-5x+6=0", "(x-2)(x-3)=0", "x=2 \\vee x=3"])
        self.assertEqual(M.lepesek("**1.** Rendezés $a==b$\n2) Kész"),
                         [{"szoveg": "Rendezés $a=b$", "keplet": "a=b"}, {"szoveg": "Kész", "keplet": None}])
        self.assertIsNone(M.kodblokk("nincs kód"))

    def test_a_keres_egy_helyen_es_a_meres_ugyanazt_keri(self):
        k = M.keres("Oldd meg: $x^2=4$")
        self.assertEqual(k["max_tokens"], M.MAX_TOKENS)
        self.assertIn("EREDMENY", k["messages"][0]["content"])
        self.assertIn("{x: 4, y: 1}", k["messages"][0]["content"])           # a format() kapcsos zárójelei épek
        from tests.eval_segedek import eval_cfg, feladat
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = eval_cfg(t.name)
        tetel = next(feladat(cfg, "matek_cas").tetelek(cfg))
        self.assertEqual(tetel["keres"]["messages"][0]["content"].split("FELADAT:")[0],
                         k["messages"][0]["content"].split("FELADAT:")[0])

    def test_beszur_es_csere(self):
        szoveg = "# Cím\n\nOldd meg: $x^2-5x+6=0$\n\nKövetkező bekezdés"
        blokk = "> [!solution]- Megoldás · CAS-ellenőrzött\n> 1. x"
        egy = M.beszur(szoveg, 3, blokk)
        self.assertEqual(egy, "# Cím\n\nOldd meg: $x^2-5x+6=0$\n\n" + blokk + "\n\nKövetkező bekezdés")
        ketto = M.beszur(egy, 3, blokk.replace("1. x", "1. y"))
        self.assertEqual(ketto, egy.replace("1. x", "1. y"))                  # az újrafuttatás cserél, nem halmoz
        self.assertEqual(M.beszur("feladat", 1, blokk), "feladat\n\n" + blokk + "\n")
        self.assertEqual(M.feladat_sorai("a\nb\nc", 2, 3), "b\nc")

    def test_callout_cimkek_es_masodik_velemeny(self):
        e = {"ellenorzott": True, "ok": None, "lepesek": [{"szoveg": "Egyenlet $x=1$", "jel": "ok"}]}
        rossz = {"ellenorzott": False, "ok": "a kód nem futott le", "lepesek": []}
        c = M.callout(e, None, {"latex_a": "\\{1\\}"}, modell="qwen35_9b", masodik_ok="nincs kalibrált második család")
        self.assertTrue(c.startswith("> [!solution]- Megoldás · CAS-ellenőrzött\n> 1. Egyenlet $x=1$ ✓"))
        self.assertIn("**Eredmény:** $\\{1\\}$", c)
        self.assertIn("*Második vélemény:* nincs (nincs kalibrált második család).", c)
        self.assertTrue(all(s.startswith(">") for s in c.split("\n")))
        c = M.callout(e, e, {"latex_a": "1", "latex_b": "1", "egyezik": True}, modell="a", masodik_modell="b")
        self.assertIn("*Második vélemény* (b, CAS-ellenőrzött): egyezik.", c)
        c = M.callout(e, rossz, {"latex_a": "1", "latex_b": "2", "egyezik": False}, modell="a", masodik_modell="b", proba=True)
        self.assertIn("**Eredmény (a):** $1$", c)
        self.assertIn("**Eredmény (b, második vélemény · nem ellenőrizhető):** $2$", c)
        self.assertIn("**A két megoldás eltér**", c)
        self.assertIn("· próba*", c)
        c = M.callout(rossz, None, {}, modell="a")
        self.assertIn("Megoldás · nem ellenőrizhető", c)
        self.assertIn("*Nem ellenőrizhető:* a kód nem futott le.", c)
        self.assertNotIn("==", M.callout({"ellenorzott": True, "lepesek": [{"szoveg": "a == b", "jel": None}]}, None, {},
                                         modell="a"))


class EllenorzesTest(unittest.TestCase):
    def test_cas_ellenorzott(self):
        hk = AlHomokozo(kod=[kod_ok("2", "3")], levezetes=LV_RENDBEN)
        e = M.ellenoriz(JO_VALASZ, hk)
        self.assertTrue(e["ellenorzott"])
        self.assertEqual([l["jel"] for l in e["lepesek"]], [None, "ok", "ok"])
        self.assertEqual([f["muvelet"] for f in hk.feladatok], ["kod", "hivas"])
        self.assertEqual(hk.feladatok[1]["args"]["sorok"], ["x^2-5x+6=0", "(x-2)(x-3)=0", "x=2 \\vee x=3"])

    def test_hibas_lepes_tiltott_kod_es_egyeb_eredmeny(self):
        lv = {"allapot": "hiba", "elso_hiba": {"sor": 3, "fajta": "eltero_halmaz"},
              "atmenetek": [{"honnan": 1, "hova": 2, "itelet": "ekvivalens"}, {"honnan": 2, "hova": 3, "itelet": "hiba"}]}
        e = M.ellenoriz(JO_VALASZ, AlHomokozo(kod=[kod_ok("2", "3")], levezetes=lv))
        self.assertFalse(e["ellenorzott"])
        self.assertEqual(e["lepesek"][2]["jel"], "hiba")
        self.assertIn("hibát talált", e["ok"])
        e = M.ellenoriz(JO_VALASZ, AlHomokozo(kod=[{"allapot": "tiltott", "ertek": None, "uzenet": "tiltott import: os"}],
                                              levezetes=LV_RENDBEN))
        self.assertFalse(e["ellenorzott"])
        self.assertIn("tiltott", e["ok"])
        e = M.ellenoriz(JO_VALASZ, AlHomokozo(kod=[{"allapot": "ok", "ertek": {"tipus": "egyeb", "ertek": "ImageSet"},
                                                    "uzenet": ""}], levezetes=LV_RENDBEN))
        self.assertEqual(e["ok"], M.UZENET_EGYEB)
        e = M.ellenoriz("1. Csak szöveg", AlHomokozo())
        self.assertEqual((e["kod"]["allapot"], e["ellenorzott"]), ("nincs_kod", False))


class EredmenyTest(unittest.TestCase):
    """A `matek.eredmeny` művelet logikája (a homokozóban fut; itt a megbízható tesztbemenettel folyamaton belül)."""

    def test_latex_es_egyezes(self):
        h = {"tipus": "halmaz", "elemek": ["2", "3"]}
        r = ER.osszevet(h, {"tipus": "halmaz", "elemek": ["3", "2"]})
        self.assertEqual((r["latex_a"], r["egyezik"]), (r"\{2;\ 3\}", True))
        self.assertFalse(ER.osszevet(h, {"tipus": "halmaz", "elemek": ["2"]})["egyezik"])
        self.assertTrue(ER.osszevet({"tipus": "kifejezes", "ertek": "1/2"}, {"tipus": "halmaz", "elemek": ["0.5"]})["egyezik"])
        self.assertTrue(ER.osszevet({"tipus": "kifejezes", "ertek": "sqrt(2)/2"}, {"tipus": "kifejezes", "ertek": "1/sqrt(2)"})["egyezik"])
        iv = {"tipus": "intervallum", "darabok": [{"a": "5", "b": "6", "bal_nyitott": False, "jobb_nyitott": True}]}
        self.assertEqual(ER.osszevet(iv)["latex_a"], r"[5;\ 6)")
        self.assertTrue(ER.osszevet(iv, iv)["egyezik"])
        self.assertIsNone(ER.osszevet({"tipus": "egyeb", "ertek": "?"}, h)["egyezik"])
        self.assertEqual(ER.osszevet({"tipus": "halmaz", "elemek": []})["latex_a"], r"\emptyset")
        p = {"tipus": "par", "ertekek": {"x": "4", "y": "1"}}
        self.assertTrue(ER.osszevet(p, {"tipus": "par", "ertekek": {"y": "1", "x": "4"}})["egyezik"])
        self.assertIsNone(ER.osszevet({"tipus": "kifejezes", "ertek": "(("})["latex_a"])


class AlGepi:
    """A `core.gepi_kliens` álpéldánya: egy jegyzet, a csere-írás naplóval."""

    class GepiHiba(RuntimeError):
        pass

    def __init__(self, tartalom):
        self.tartalom, self.irasok = tartalom, []

    def olvas(self, ut):
        return {"ut": ut, "tartalom": self.tartalom, "hash": hashlib.sha1(self.tartalom.encode()).hexdigest()}

    @staticmethod
    def modell_jel(v):
        return {"feladat": v["feladat"], "modell": v["modell"], "proba": bool(v.get("proba"))}

    @staticmethod
    def uj_kor(elotag):
        return elotag + "-20261007-120000"

    @staticmethod
    def csere(ut, tartalom, alap):
        return {"tipus": "csere", "ut": ut, "tartalom": tartalom, "alap": alap}

    def ir(self, kor, tetel, forras, muveletek, uzenet=None, proba=None, *, modell):
        self.irasok.append({"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "proba": proba,
                            "modell": modell})
        return {"ok": True, "sha": "abc"}


class KliensHiba(RuntimeError):
    def __init__(self, kod, uzenet):
        super().__init__(uzenet)
        self.kod = kod


class AlWorker:
    CSALAD = {"qwen35_9b": "qwen", "qwen35_4b": "qwen", "ministral3_8b_reasoning": "mistral"}

    def __init__(self, kalibralt=("qwen35_9b",), valaszok=None):
        self.kalibralt, self.kerdesek = list(kalibralt), []
        self.valaszok = valaszok or {}

    def csalad(self, nev):
        return self.CSALAD[nev]

    def valaszt(self, kizart_csalad=None):
        jo = [m for m in self.kalibralt if self.CSALAD[m] != kizart_csalad]
        if not jo:
            raise KliensHiba(409, "nincs")
        return {"modell": jo[0], "var_tavolra": False}

    def kerdez(self, feladat, modell, *, kifejezett, kizart_csalad=None):
        self.kerdesek.append((modell, kifejezett, kizart_csalad))
        return {"modell": modell, "feladat": "matek_cas", "proba": kifejezett,
                "choices": [{"message": {"content": self.valaszok.get(modell, JO_VALASZ)}}]}


SZOVEG = "---\nTags: M\n---\n# Feladat\n\nOldd meg: $x^2-5x+6=0$\n\nVége"


def futtat(gepi=None, worker=None, hk=None, **kw):
    gepi = gepi or AlGepi(SZOVEG)
    hk = hk or AlHomokozo(kod=[kod_ok("2", "3"), kod_ok("2", "3")], levezetes=LV_RENDBEN,
                          eredmeny=lambda a: {"latex_a": r"\{2;\ 3\}", "latex_b": a["b"] and r"\{2;\ 3\}",
                                              "egyezik": True if a["b"] else None})
    r = LANC.futtat(ut="M/F.md", tol=6, ig=6, feladat="Oldd meg: $x^2-5x+6=0$", gepi=gepi, worker=worker or AlWorker(),
                    homokozo=hk, **kw)
    return r, gepi


class LancTest(unittest.TestCase):
    def test_kalibralt_elso_nincs_masodik_csalad(self):
        r, g = futtat()
        self.assertEqual(len(g.irasok), 1)
        i = g.irasok[0]
        self.assertEqual((i["forras"], i["tetel"], i["proba"]), ("mos-matek", "M/F.md", False))
        self.assertEqual(i["modell"], {"feladat": "matek_cas", "modell": "qwen35_9b", "proba": False})
        uj = i["muveletek"][0]["tartalom"]
        self.assertEqual(i["muveletek"][0]["alap"], hashlib.sha1(SZOVEG.encode()).hexdigest())
        self.assertTrue(uj.startswith("---\nTags: M\n---\n# Feladat\n\nOldd meg: $x^2-5x+6=0$\n\n> [!solution]- Megoldás · "
                                      "CAS-ellenőrzött\n"))
        self.assertIn("*Második vélemény:* nincs (nincs kalibrált második család (a qwen családon kívül)).", uj)
        self.assertTrue(uj.endswith("\n\nVége"))
        self.assertEqual(r["masodik"], {"nincs": "nincs kalibrált második család (a qwen családon kívül)"})

    def test_masodik_velemeny_masik_csaladbol_egyezik(self):
        w = AlWorker(kalibralt=("qwen35_9b", "ministral3_8b_reasoning"))
        r, g = futtat(worker=w)
        self.assertEqual(w.kerdesek, [("qwen35_9b", False, None), ("ministral3_8b_reasoning", False, "qwen")])
        self.assertIn("*Második vélemény* (ministral3_8b_reasoning, CAS-ellenőrzött): egyezik.",
                      g.irasok[0]["muveletek"][0]["tartalom"])
        self.assertFalse(g.irasok[0]["proba"])
        self.assertTrue(r["masodik"]["egyezik"])

    def test_proba_modell_probava_teszi_az_irast(self):
        _, g = futtat(modell="qwen35_4b")
        self.assertTrue(g.irasok[0]["proba"])
        self.assertTrue(g.irasok[0]["modell"]["proba"])
        _, g = futtat(masodik_modell="ministral3_8b_reasoning")         # a második vélemény próba-modellje is próbává tesz
        self.assertTrue(g.irasok[0]["proba"])
        self.assertFalse(g.irasok[0]["modell"]["proba"])
        with self.assertRaisesRegex(LANC.Megall, "ugyanabból a családból"):
            futtat(masodik_modell="qwen35_4b")

    def test_nincs_kalibralt_megall_valtozott_sorok_megall(self):
        with self.assertRaisesRegex(LANC.Megall, "nincs kalibrált modell"):
            futtat(worker=AlWorker(kalibralt=()))
        with self.assertRaisesRegex(LANC.Megall, "megváltoztak"):
            LANC.futtat(ut="M/F.md", tol=6, ig=6, feladat="más", gepi=AlGepi(SZOVEG), worker=AlWorker(), homokozo=AlHomokozo())

    def test_a_masodik_modell_hibaja_nem_viszi_el_az_elsot(self):
        class HibasWorker(AlWorker):
            def kerdez(self, feladat, modell, **kw):
                if modell == "ministral3_8b_reasoning":
                    raise KliensHiba(503, "a worker leállt")
                return super().kerdez(feladat, modell, **kw)
        _, g = futtat(worker=HibasWorker(kalibralt=("qwen35_9b", "ministral3_8b_reasoning")))
        self.assertIn("a második modell hibája: a worker leállt", g.irasok[0]["muveletek"][0]["tartalom"])


class VegpontTest(unittest.TestCase):
    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)

    def test_ervenyesites(self):
        from core import matek_api
        from core.utvonalak import HttpError
        e = matek_api.Ellenorzo(self.cfg, futtato=lambda k: {"allapot": "rendben"})
        for torzs in (None, [], {}, {"sorok": []}, {"sorok": [{"sor": 0, "szoveg": "x"}]},
                      {"sorok": [{"sor": True, "szoveg": "x"}]}, {"sorok": [{"sor": 1, "szoveg": "x" * 501}]},
                      {"sorok": [{"sor": 1, "szoveg": "x"}] * 61}, {"sorok": [{"sor": 1, "szoveg": "x"}], "vegeredmeny": "igen"},
                      {"sorok": [{"sor": 1, "szoveg": "x"}], "kikotesek": [1]}):
            with self.assertRaises(HttpError) as c:
                e.levezetes(torzs)
            self.assertEqual(c.exception.code, 400, torzs)
        self.assertEqual(e.levezetes({"sorok": [{"sor": 3, "szoveg": "$x=1$"}]}), {"ok": True, "allapot": "rendben"})
        e = matek_api.Ellenorzo(self.cfg, futtato=lambda k: {"allapot": "nem_ellenorizheto", "ok": "legalább két sor kell"})
        self.assertEqual(e.levezetes({"sorok": [{"sor": 3, "szoveg": "x"}]}),
                         {"ok": True, "allapot": "nem_ellenorizheto", "indok": "legalább két sor kell"})

    def test_homokozo_hiba_503_es_regisztralt_ut(self):
        from core import matek_api, server
        from core.utvonalak import HttpError
        e = matek_api.Ellenorzo(self.cfg, futtato=lambda k: {"allapot": "nem_ellenorizheto",
                                                             "ok": "homokozó: homokozo_hiba — nincs sandbox-exec"})
        with self.assertRaises(HttpError) as c:
            e.levezetes({"sorok": [{"sor": 1, "szoveg": "x=1"}]})
        self.assertEqual(c.exception.code, 503)
        self.assertIn(("POST", "/api/matek/levezetes"), {(m, u) for m, u, _ in server.regiszter_epit().vegpontok()})

    def test_a_cli_hibas_kerest_64_gyel_utasit_el(self):
        from core import matek_api
        p = subprocess.run([sys.executable, "-B", str(MODULOK / "matek" / "__main__.py"), "levezetes-json"],
                           input=json.dumps({"sorok": "x"}), capture_output=True, text=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO)})
        self.assertEqual(p.returncode, matek_api.KERES_HIBA, p.stderr)


    def test_a_megoldas_lepes_importjai_es_hibakodja(self):
        """A lépés valódi alfolyamatként indul (a feladatsor argv-je): worker nélkül érthető hibával (5) lép ki (az ál-`var/`
        miatt a gépen esetleg futó valódi worker pidfájlját sem látja)."""
        t = tmpdir()
        self.addCleanup(t.cleanup)
        p = subprocess.run([sys.executable, "-B", str(MODULOK / "matek" / "__main__.py"), "megoldas", "--ut=M/F.md", "--tol=1",
                            "--ig=1", "--feladat=-x"], capture_output=True, text=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "MOS_WORKER_URL": "", "MOS_VAR": t.name})
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn("modell-worker", p.stderr)


class FeladatTest(unittest.TestCase):
    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)
        from core import matek_feladat, tasks
        matek_feladat.regisztral()
        self.terv, self.tasks = tasks.REGISTRY["matek_megoldas"].plan, tasks
        self.tipus = tasks.REGISTRY["matek_megoldas"]

    def test_terv_es_argv(self):
        self.assertEqual(self.tipus.resources, frozenset({"modell", "vault"}))
        self.assertFalse(self.tipus.automatikus)
        lepesek, _, figy = self.terv(self.cfg, {"ut": "M/F.md", "tol": 6, "ig": 7, "feladat": "-a\nb"}, "/x")
        argv = lepesek[0].argv
        self.assertIn("--feladat=-a\nb", argv)                                  # a `-`-szal kezdődő szöveg sem kapcsoló
        self.assertNotIn("--proba", argv)
        self.assertEqual(figy, [])
        lepesek, _, figy = self.terv(self.cfg, {"ut": "M/F.md", "tol": 6, "ig": 6, "feladat": "x", "modell": "qwen35_4b",
                                                "masodik": False}, "/x")
        self.assertIn("--modell=qwen35_4b", lepesek[0].argv)
        self.assertIn("--proba", lepesek[0].argv)
        self.assertIn("--nincs-masodik", lepesek[0].argv)
        self.assertTrue(figy)

    def test_ervenytelen_parameterek(self):
        alap = {"ut": "M/F.md", "tol": 1, "ig": 1, "feladat": "x"}
        for rossz in ({**alap, "ut": "/abs.md"}, {**alap, "ut": "../k.md"}, {**alap, "ut": "a.pdf"}, {**alap, "tol": 0},
                      {**alap, "ig": 0}, {**alap, "tol": True}, {**alap, "feladat": ""}, {**alap, "feladat": "a\nb"},
                      {**alap, "feladat": "x" * 4001}, {**alap, "proba": "igen"}, {**alap, "modell": "nincs_ilyen"},
                      {**alap, "modell": "bge_m3"}, {**alap, "tol": 1, "ig": 200, "feladat": "\n" * 199}):
            with self.assertRaises(self.tasks.Invalid, msg=rossz):
                self.terv(self.cfg, rossz, "/x")


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class ValodiHomokozoTest(unittest.TestCase):
    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)

    def test_ellenorzes_es_osszevetes_a_homokozoban(self):
        from homokozo import Homokozo
        hk = Homokozo(self.cfg)
        e = M.ellenoriz(JO_VALASZ, hk)
        self.assertTrue(e["ellenorzott"], e)
        masik = JO_VALASZ.replace("sp.solveset(x**2 - 5*x + 6, x, sp.S.Reals)", "[sp.Rational(6, 2), 2]")
        e2 = M.ellenoriz(masik, hk)
        cmp = M.osszevet(e, e2, hk)
        self.assertEqual((cmp["latex_a"], cmp["egyezik"]), (r"\{2;\ 3\}", True))
        rossz = M.ellenoriz(JO_VALASZ.replace("import sympy as sp", "import os\nimport sympy as sp"), hk)
        self.assertFalse(rossz["ellenorzott"])

    def test_a_vegpont_alfolyamata_a_jegyzet_soraira_kepez(self):
        from core import config, matek_api
        e = matek_api.Ellenorzo(config.load())                # a munkafa saját, csak olvasott konfigurációja (a modulok útja)
        r = e.levezetes({"sorok": [{"sor": 10, "szoveg": "$$"}, {"sor": 11, "szoveg": "2x+3=7"}, {"sor": 12, "szoveg": ""},
                                   {"sor": 13, "szoveg": "2x=10"}, {"sor": 14, "szoveg": "- $x=5$"}]})
        self.assertEqual(r["allapot"], "hiba")
        self.assertEqual(r["elso_hiba"]["jegyzet_sor"], 13)
        self.assertEqual([a["jegyzet_hova"] for a in r["atmenetek"]], [13, 14])


if __name__ == "__main__":
    unittest.main()
