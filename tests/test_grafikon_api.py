"""C35a: `POST /api/grafikon/elemzes` — a ```plot blokk függvényeinek CAS-jellemzői (core/grafikon_api.py). A core nem
importál `modulok`-ot (D-1): a számítást a `modulok/grafikon/__main__.py elemez-json` alfolyamat végzi a CAS-homokozóban.
A végpont logikáját (érvényesítés, gyorsítótár, egy-átfutás zár, időkorlát, hibák) hamis futtatóval és hamis
alfolyamat-paranccsal teszteljük; egy teljes út a valódi homokozóval csak macOS-en."""
import json
import sys
import threading
import time
import unittest
from types import SimpleNamespace

from core import config, grafikon_api, server, utvonalak
from core.utvonalak import HttpError, Kerees
from tests.helpers import REPO, alg_core, tmpdir

MACOS = sys.platform == "darwin"
ABLAK = [-3, 3]


def ok(kif, **mas):
    return {"allapot": "ok", "kifejezes": kif, "ertelmezes": "Reals", "zerushelyek": [], "szelsoertekek": [],
            "aszimptotak": [], "ferde_aszimptotak": [], "numerikus": False, "figyelmeztetesek": [], **mas}


class Futtato:
    """Hamis alfolyamat: naplózza a hívásokat, a párhuzamosságot, és tud várakozni."""

    def __init__(self, ered=None, kesleltetes=0.0):
        self.hivasok: list[tuple[list[str], list]] = []
        self.ered = ered
        self.kesleltetes = kesleltetes
        self.egyszerre = 0
        self.legtobb = 0
        self._zar = threading.Lock()

    def __call__(self, fuggvenyek, ablak):
        with self._zar:
            self.egyszerre += 1
            self.legtobb = max(self.legtobb, self.egyszerre)
            self.hivasok.append((list(fuggvenyek), list(ablak)))
        try:
            time.sleep(self.kesleltetes)
            return [self.ered(f) if self.ered else ok(f) for f in fuggvenyek]
        finally:
            with self._zar:
                self.egyszerre -= 1


def elemzo(futtato=None, **beall):
    t = tmpdir()
    cfg, _, _ = alg_core(t.name)
    e = grafikon_api.Elemzo(cfg, futtato=futtato, **beall)
    e._t = t
    return e


class ErvenyesitesTest(unittest.TestCase):
    def setUp(self):
        self.e = elemzo(Futtato())
        self.addCleanup(self.e._t.cleanup)

    def rossz(self, torzs):
        with self.assertRaises(HttpError) as c:
            self.e.elemez(torzs)
        self.assertEqual(c.exception.code, 400, torzs)
        self.assertTrue(str(c.exception))

    def test_a_torzs_alakja(self):
        for torzs in (None, [], "x", {}, {"fuggvenyek": ["x"]}, {"ablak": ABLAK},
                      {"fuggvenyek": "x", "ablak": ABLAK}, {"fuggvenyek": [], "ablak": ABLAK},
                      {"fuggvenyek": ["x"] * 9, "ablak": ABLAK}, {"fuggvenyek": [1], "ablak": ABLAK},
                      {"fuggvenyek": [None], "ablak": ABLAK}):
            self.rossz(torzs)

    def test_a_kifejezes_korlatai(self):
        for kif in ("", "   ", "x" * 301, "x; import os", "x\ny", "sin(x)\\", "x = 1", "<script>", "é", "x $ y"):
            self.rossz({"fuggvenyek": [kif], "ablak": ABLAK})

    def test_az_ablak_korlatai(self):
        for ablak in (None, [], [1], [1, 2, 3], "ab", ["a", "b"], [True, 2], [0, float("nan")], [0, float("inf")],
                      [1, 1], [2, 1], [-1e12, 1], [0, 1e7 + 1], [{"a": 1}, 2]):
            self.rossz({"fuggvenyek": ["x"], "ablak": ablak})

    def test_a_jo_bemenet_mehet(self):
        for kif in ("x", "-x^2 + 8", "log(x, 2)", "abs(x) - 3", "(x^2-1)/(x-1)", "e^(-x^2)", "sin(2*x)"):
            self.assertTrue(self.e.elemez({"fuggvenyek": [kif], "ablak": [-5, 5.5]})["ok"], kif)

    def test_a_valasz_alakja(self):
        v = self.e.elemez({"fuggvenyek": ["x^2", "1/x"], "ablak": ABLAK})
        self.assertEqual([f["kif"] for f in v["fuggvenyek"]], ["x^2", "1/x"])
        self.assertEqual(v["fuggvenyek"][0]["allapot"], "ok")
        self.assertIsInstance(v["ido_ms"], int)
        self.assertIs(v["gyorsitotar"], False)
        self.assertEqual(json.loads(json.dumps(v)), v)


class GyorsitotarTest(unittest.TestCase):
    def test_masodik_azonos_keres_nem_inditja_ujra(self):
        f = Futtato()
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        k = {"fuggvenyek": ["x^2", "x^3"], "ablak": ABLAK}
        self.assertIs(e.elemez(k)["gyorsitotar"], False)
        self.assertIs(e.elemez(k)["gyorsitotar"], True)
        self.assertEqual(len(f.hivasok), 1)

    def test_reszleges_talalat_csak_a_hianyzot_szamolja(self):
        f = Futtato()
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        e.elemez({"fuggvenyek": ["x^2"], "ablak": ABLAK})
        v = e.elemez({"fuggvenyek": ["x^2", "x^3", "x^2"], "ablak": ABLAK})
        self.assertEqual(f.hivasok[-1][0], ["x^3"])
        self.assertEqual([x["kif"] for x in v["fuggvenyek"]], ["x^2", "x^3", "x^2"])
        self.assertIs(v["gyorsitotar"], False)

    def test_az_ablak_9_ertekes_jegyre_kerekitve_kozos_kulcs(self):
        f = Futtato()
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        e.elemez({"fuggvenyek": ["x^2"], "ablak": [-3.0000000001, 3.0000000002]})
        e.elemez({"fuggvenyek": ["x^2"], "ablak": [-3.0000000004, 3.0000000001]})
        self.assertEqual(len(f.hivasok), 1)
        e.elemez({"fuggvenyek": ["x^2"], "ablak": [-3.001, 3.0]})
        self.assertEqual(len(f.hivasok), 2)

    def test_az_alfolyamat_a_kerekitett_ablakot_kapja(self):
        f = Futtato()
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        e.elemez({"fuggvenyek": ["x"], "ablak": [-3.0000000001, 3.14159265358979]})
        self.assertEqual(f.hivasok[0][1], [-3.0, 3.14159265])

    def test_a_gyorsitotar_korlatos(self):
        f = Futtato()
        e = elemzo(f, gyorsitotar_db=3)
        self.addCleanup(e._t.cleanup)
        for i in range(5):
            e.elemez({"fuggvenyek": [f"x + {i}"], "ablak": ABLAK})
        e.elemez({"fuggvenyek": ["x + 4"], "ablak": ABLAK})                  # a legfrissebb még bent van
        self.assertEqual(len(f.hivasok), 5)
        e.elemez({"fuggvenyek": ["x + 0"], "ablak": ABLAK})                  # a legrégebbi kiesett
        self.assertEqual(len(f.hivasok), 6)

    def test_homokozo_hiba_nem_kerul_a_gyorsitotarba_es_ha_mind_az_503(self):
        f = Futtato(ered=lambda k: {"allapot": "homokozo_hiba", "uzenet": "homokozó: nincs sandbox-exec"})
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        with self.assertRaises(HttpError) as c:
            e.elemez({"fuggvenyek": ["x"], "ablak": ABLAK})
        self.assertEqual(c.exception.code, 503)
        self.assertIn("sandbox-exec", str(c.exception))
        with self.assertRaises(HttpError):
            e.elemez({"fuggvenyek": ["x"], "ablak": ABLAK})
        self.assertEqual(len(f.hivasok), 2)                                  # nem gyorsítótárazott

    def test_reszleges_homokozo_hiba_200_tetelenkent(self):
        f = Futtato(ered=lambda k: {"allapot": "homokozo_hiba", "uzenet": "x"} if k == "1/x" else ok(k))
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        v = e.elemez({"fuggvenyek": ["x", "1/x"], "ablak": ABLAK})
        self.assertEqual([x["allapot"] for x in v["fuggvenyek"]], ["ok", "homokozo_hiba"])

    def test_a_hiba_allapot_determinisztikus_ezert_gyorsitotarazott(self):
        f = Futtato(ered=lambda k: {"allapot": "hiba", "uzenet": "a kifejezésben csak az x változó állhat"})
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        e.elemez({"fuggvenyek": ["a*x"], "ablak": ABLAK})
        e.elemez({"fuggvenyek": ["a*x"], "ablak": ABLAK})
        self.assertEqual(len(f.hivasok), 1)


class EgyAtfutasTest(unittest.TestCase):
    def test_az_azonos_kerelmek_egyszer_futnak(self):
        f = Futtato(kesleltetes=0.3)
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        k = {"fuggvenyek": ["x^2"], "ablak": ABLAK}
        ki = []
        szalak = [threading.Thread(target=lambda: ki.append(e.elemez(k))) for _ in range(4)]
        for s in szalak:
            s.start()
        for s in szalak:
            s.join(10)
        self.assertEqual(len(ki), 4)
        self.assertEqual(len(f.hivasok), 1)
        self.assertEqual(sorted(x["gyorsitotar"] for x in ki), [False, True, True, True])

    def test_kulonbozo_kerelmek_sorban_egyszerre_egy_homokozo(self):
        f = Futtato(kesleltetes=0.15)
        e = elemzo(f)
        self.addCleanup(e._t.cleanup)
        szalak = [threading.Thread(target=e.elemez, args=({"fuggvenyek": [f"x + {i}"], "ablak": ABLAK},)) for i in range(4)]
        for s in szalak:
            s.start()
        for s in szalak:
            s.join(10)
        self.assertEqual(len(f.hivasok), 4)
        self.assertEqual(f.legtobb, 1)


class VarakozasiKorlatTest(unittest.TestCase):
    """A3-30: a zár a futás idejéig áll; a sorban várakozó kérés korlátos ideig vár, utána 503 „foglalt”."""

    def test_a_foglalt_homokozora_varo_kerelem_503_foglalt(self):
        f = Futtato(kesleltetes=0.8)
        e = elemzo(f, varakozas_s=0.1)
        self.addCleanup(e._t.cleanup)
        elso = threading.Thread(target=e.elemez, args=({"fuggvenyek": ["x + 1"], "ablak": ABLAK},))
        elso.start()
        while not f.hivasok:                                    # az első kérés tartja a zárat
            time.sleep(0.01)
        t0 = time.monotonic()
        with self.assertRaises(HttpError) as c:
            e.elemez({"fuggvenyek": ["x + 2"], "ablak": ABLAK})
        self.assertEqual(c.exception.code, 503)
        self.assertIn("foglalt", str(c.exception))
        self.assertLess(time.monotonic() - t0, 0.6)             # nem várta ki az első futást
        elso.join(10)
        self.assertEqual(len(f.hivasok), 1)                     # a visszautasított kérés nem indított homokozót

    def test_a_gyorsitotar_talalat_nem_var_a_zarra(self):
        f = Futtato(kesleltetes=0.0)
        e = elemzo(f, varakozas_s=0.1)
        self.addCleanup(e._t.cleanup)
        e.elemez({"fuggvenyek": ["x^2"], "ablak": ABLAK})
        lassu = Futtato(kesleltetes=0.6)
        e.futtato = lassu
        szal = threading.Thread(target=e.elemez, args=({"fuggvenyek": ["x^3"], "ablak": ABLAK},))
        szal.start()
        while not lassu.hivasok:
            time.sleep(0.01)
        self.assertTrue(e.elemez({"fuggvenyek": ["x^2"], "ablak": ABLAK})["gyorsitotar"])
        szal.join(10)

    def test_a_varakozas_a_korlaton_belul_sorban_lefut(self):
        f = Futtato(kesleltetes=0.1)
        e = elemzo(f, varakozas_s=5.0)
        self.addCleanup(e._t.cleanup)
        ki = []
        szalak = [threading.Thread(target=lambda i=i: ki.append(e.elemez({"fuggvenyek": [f"x + {i}"], "ablak": ABLAK})))
                  for i in range(3)]
        for s in szalak:
            s.start()
        for s in szalak:
            s.join(10)
        self.assertEqual(len(ki), 3)

    def test_a_korlat_a_configbol_jon(self):
        e = elemzo(Futtato())
        self.addCleanup(e._t.cleanup)
        self.assertGreater(float(e.beall["varakozas_s"]), 0)
        self.assertIn("varakozas_s", (REPO / "config" / "os.toml").read_text(encoding="utf-8"))


class AlfolyamatTest(unittest.TestCase):
    """A valódi `_alfolyamat` hamis paranccsal: JSON a stdin-en, JSON a stdout-on."""

    def elemzo_paranccsal(self, kod: str, idokorlat=5.0):
        e = elemzo(None, elemzes_idokorlat_s=idokorlat)
        e.parancs = [sys.executable, "-c", kod]
        self.addCleanup(e._t.cleanup)
        return e

    def test_jo_valasz(self):
        kod = ("import sys, json; k = json.load(sys.stdin); "
               "print(json.dumps({'fuggvenyek': [{'allapot': 'ok', 'kifejezes': f, 'ablak': k['ablak']} for f in k['fuggvenyek']]}))")
        v = self.elemzo_paranccsal(kod).elemez({"fuggvenyek": ["x^2"], "ablak": [-3, 3]})
        self.assertEqual(v["fuggvenyek"][0]["kifejezes"], "x^2")
        self.assertEqual(v["fuggvenyek"][0]["ablak"], [-3.0, 3.0])

    def test_idotullepes_503_es_a_folyamat_leall(self):
        kod = "import time; time.sleep(30)"
        e = self.elemzo_paranccsal(kod, idokorlat=0.5)
        t = time.monotonic()
        with self.assertRaises(HttpError) as c:
            e.elemez({"fuggvenyek": ["x"], "ablak": ABLAK})
        self.assertEqual(c.exception.code, 503)
        self.assertIn("időkorlát", str(c.exception))
        self.assertLess(time.monotonic() - t, 8)

    def test_hibas_kilepes_es_hibas_json_503(self):
        for kod in ("import sys; sys.exit(3)", "import sys; sys.exit(2)", "print('nem json')", "print('{}')", "print('[1]')",
                    "import json; print(json.dumps({'fuggvenyek': 'x'}))",
                    "import json; print(json.dumps({'fuggvenyek': []}))"):
            with self.assertRaises(HttpError, msg=kod) as c:
                self.elemzo_paranccsal(kod).elemez({"fuggvenyek": ["x"], "ablak": ABLAK})
            self.assertEqual(c.exception.code, 503, kod)

    def test_a_kerelmi_hiba_kilepesi_kod_belso_hiba_500(self):
        kod = "import sys; print('{\"hiba\": \"x\"}'); sys.exit(64)"
        with self.assertRaises(HttpError) as c:
            self.elemzo_paranccsal(kod).elemez({"fuggvenyek": ["x"], "ablak": ABLAK})
        self.assertEqual(c.exception.code, 500)

    def test_az_alapparancs_a_grafikon_cli_a_config_utjaibol(self):
        e = elemzo(Futtato())
        self.addCleanup(e._t.cleanup)
        p = e.parancs
        self.assertEqual(p[0], sys.executable)
        self.assertTrue(p[-1] == "elemez-json" and p[-2].endswith("grafikon/__main__.py"))
        self.assertIn(str(e.cfg.path("modulok")), p[-2])


class ForrasTest(unittest.TestCase):
    def test_a_core_nem_importal_modulokat(self):
        forras = (REPO / "core" / "grafikon_api.py").read_text(encoding="utf-8")
        for tiltott in ("import homokozo", "from homokozo", "import grafikon", "from grafikon", "import sympy",
                        "from modulok", "import modulok", "sys.path"):
            self.assertNotIn(tiltott, forras)

    def test_a_cli_es_a_core_ugyanazt_a_korlatot_tartja(self):
        for ut in (REPO / "modulok" / "eval", REPO / "modulok"):
            if str(ut) not in sys.path:
                sys.path.insert(0, str(ut))
        import grafikon
        self.assertEqual(grafikon_api.MAX_FUGGVENY, grafikon.MAX_FUGGVENY)

    def test_a_vegpont_regisztralva_van(self):
        r = server.regiszter_epit()
        self.assertIn(("POST", "/api/grafikon/elemzes", False), r.vegpontok())

    def test_a_kezelo_az_elemzo_valaszat_adja_es_400_at_a_hibas_torzsre(self):
        r = server.regiszter_epit()
        kezelo, _ = r.keres("POST", "/api/grafikon/elemzes")
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        f = Futtato()
        app = SimpleNamespace(cfg=cfg, _grafikon=grafikon_api.Elemzo(cfg, futtato=f))
        v = kezelo(Kerees(app, None, "/api/grafikon/elemzes", {}, None, {"fuggvenyek": ["x^2"], "ablak": ABLAK}))
        self.assertTrue(v["ok"])
        with self.assertRaises(HttpError) as c:
            kezelo(Kerees(app, None, "/api/grafikon/elemzes", {}, None, {}))
        self.assertEqual(c.exception.code, 400)


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class ValodiTest(unittest.TestCase):
    def test_a_valodi_alfolyamat_es_homokozo(self):
        cfg = config.load()                                   # a worktree saját, csak olvasott konfigurációja
        e = grafikon_api.Elemzo(cfg)
        v = e.elemez({"fuggvenyek": ["x^3 - 3*x", "1/x"], "ablak": [-3, 3]})
        self.assertTrue(v["ok"])
        a, b = v["fuggvenyek"]
        self.assertEqual(a["allapot"], "ok", a)
        self.assertEqual([p["x"] for p in a["zerushelyek"]], ["-sqrt(3)", "0", "sqrt(3)"])
        self.assertEqual([(p["x"], p["tipus"]) for p in a["szelsoertekek"]], [("-1", "maximum"), ("1", "minimum")])
        self.assertEqual([x["egyenlet"] for x in b["aszimptotak"]], ["x=0", "y=0"])
        masodik = e.elemez({"fuggvenyek": ["x^3 - 3*x"], "ablak": [-3, 3]})
        self.assertIs(masodik["gyorsitotar"], True)


if __name__ == "__main__":
    unittest.main()
