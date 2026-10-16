"""A hibrid keresés végpontjai (C25b-mag) a valódi core-on, álvaulton: kötött modell nélkül a keresés lexikai (és ezt
kimondja), a vektortár hiánya nem hiba, a „Kérdezz” forrás nélkül `nincs_valasz`, forrással és modell nélkül 503; a
kérés semmit nem ír. A kötés horga (`kereses_api.kotes`) a folyamaton belül, álbeágyazóval."""
import hashlib
import json
import os
import threading
import unittest
import urllib.parse
from pathlib import Path

from core import kereses_api, server
from core.index.hibrid import frissites, vektortar
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.hibrid_segedek import FAJLOK, AlBeagyazo
from tests.index_segedek import alvault, index_indit, var_ra
from tests.test_core_api import _Kimenet

class AlApp:
    """Az `App` helyett (a szolgálat app-onként, gyenge hivatkozással él)."""

    def __init__(self, cfg, index):
        self.cfg, self.index = cfg, index


SPARTA = "T02 - Hellász/Elmélet/07 - Spárta.md"


class ApiTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        for rp, t in FAJLOK.items():
            ir(self.v, rp, t)
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/index")[1].get("kesz"), 30))

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None, titok=API_TITOK):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        fej = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if titok:
            fej["X-Manifold"] = titok
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=fej)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def lenyomat(self):
        ki = {}
        for d, mappak, fajlok in os.walk(self.v):
            mappak[:] = [m for m in mappak if m != ".obsidian"]
            for f in fajlok:
                p = Path(d) / f
                ki[os.path.relpath(p, self.v)] = hashlib.sha1(p.read_bytes()).hexdigest()
        return ki

    def test_vegpontok_kotes_nelkul(self):
        elotte = self.lenyomat()
        s, r = self.k("GET", "/api/kereses/hibrid?q=" + urllib.parse.quote("spártai nevelés"))
        self.assertEqual(s, 200)
        self.assertEqual((r["mod"], r["ok"]), ("lexikai", "nincs_beagyazo"))
        self.assertEqual(r["talalatok"][0]["ut"], SPARTA)
        self.assertIn("legalabb", r)
        s, r = self.k("GET", "/api/kereses/vektor-allapot")
        self.assertEqual((s, r["van"], r["kotve"]["beagyazo"], r["kotve"]["modell"]), (200, False, None, False))
        self.assertFalse((Path(self.cfg.path("index")) / "vektor.sqlite").exists())       # a végpont nem épít tárat
        s, r = self.k("POST", "/api/kereses/kerdezz", {"kerdes": "kvantumgravitáció húrelmélet szuperszimmetria"})
        self.assertEqual((s, r["allapot"], r["ok"]), (200, "nincs_valasz", "nincs_eleg_forras"))
        s, r = self.k("POST", "/api/kereses/kerdezz", {"kerdes": "Hány évesen vették el a spártai fiúkat a családtól?"})
        self.assertEqual(s, 503)
        self.assertIn("not set up", r["error"] if "error" in r else json.dumps(r, ensure_ascii=False))
        self.assertEqual(self.lenyomat(), elotte)

    def test_hibas_kerések_es_titok(self):
        self.assertEqual(self.k("GET", "/api/kereses/hibrid?q=")[0], 400)
        self.assertEqual(self.k("GET", "/api/kereses/hibrid?q=x&mod=szemantikus")[0], 400)
        self.assertEqual(self.k("GET", "/api/kereses/hibrid?q=x&limit=0")[0], 400)
        self.assertEqual(self.k("POST", "/api/kereses/kerdezz", {"kerdes": ""})[0], 400)
        self.assertEqual(self.k("POST", "/api/kereses/kerdezz", {"kerdes": "x" * 2001})[0], 400)
        self.assertEqual(self.k("GET", "/api/kereses/hibrid?q=x", titok=None)[0], 403)
        self.assertEqual(self.k("POST", "/api/kereses/kerdezz", {"kerdes": "x"}, titok="rossz-titok-1234567890")[0], 403)


    def test_a_lepes_token_a_kerdezzt_folyamkent_sem_hivhatja(self):
        """C25b: a „Kérdezz” (a folyamos változat is) a lépés-tokennel 403 (default-deny), a keresés olvasható."""
        from unittest import mock
        from core import tasks
        token = "lepes-token-0123456789abcdef"
        with mock.patch.object(tasks.Queue, "lepes_feladat", lambda self, t: "F-1" if t == token else None):
            s, _ = self.k("POST", "/api/kereses/kerdezz", {"kerdes": "Spárta", "folyam": True}, titok=token)
            self.assertEqual(s, 403)
            s, _ = self.k("POST", "/api/kereses/kerdezz", {"kerdes": "Spárta"}, titok=token)
            self.assertEqual(s, 403)
            s, _ = self.k("GET", "/api/kereses/hibrid?q=" + urllib.parse.quote("Spárta"), titok=token)
            self.assertEqual(s, 200)                    # a token érvényes: a tiltás a végpontnak szól

    def test_folyam_ndjson_modell_nelkul(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", "/api/kereses/kerdezz",
                  body=json.dumps({"kerdes": "Hány évesen vették el a spártai fiúkat a családtól?", "folyam": True}),
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        self.assertEqual((r.status, r.getheader("Content-Type").split(";")[0]), (200, "application/x-ndjson"))
        esemenyek = [json.loads(s) for s in r.read().decode().splitlines() if s.strip()]
        self.assertEqual([e["tipus"] for e in esemenyek], ["forrasok", "vege"])
        self.assertEqual(esemenyek[-1]["allapot"], "nincs_modell")


class FolyamKuldTest(unittest.TestCase):
    """A core NDJSON-írója: a kliens bontásakor a modell tokenfolyama bezárul, és a `megszakit` horog lefut."""

    class _H:
        def __init__(self, hiba_utan: int):
            self.sorok, self.hiba_utan = [], hiba_utan
            self.wfile = self

        def send_response(self, k):
            self.kod = k

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

        def write(self, b):
            if len(self.sorok) >= self.hiba_utan:
                raise BrokenPipeError
            self.sorok.append(json.loads(b))

        def flush(self):
            pass

    def test_bontaskor_a_modell_folyama_bezarul(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _ = alvault(t.name, FAJLOK)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        app = AlApp(cfg, ix)
        lezart, megszakitva = [], []

        def modell(prompt, max_tokens):
            def gen():
                try:
                    sor = json.dumps({"mondat": "A spártai fiúkat hétévesen elvették a családtól.", "forras": 1,
                                      "idezet": "a fiúkat hétévesen elvették a családtól"}, ensure_ascii=False) + "\n"
                    for _ in range(50):
                        yield sor
                finally:
                    lezart.append(True)
            return gen()
        sz = kereses_api.kotes(app, modell=modell, kalibralt=True, megszakit=lambda: megszakitva.append(True))
        from core.index.hibrid import kerdezz
        h = self._H(hiba_utan=2)
        kereses_api._folyam_kuld(h, kereses_api._hiba_esemenyekkel(
            kerdezz.folyam("Hány évesen vették el a spártai fiúkat a családtól?", sz.kereso(), sz.modell,
                           kalibralt=True, megszakit=sz.megszakit)))
        self.assertEqual([e["tipus"] for e in h.sorok], ["forrasok", "mondat"])
        self.assertEqual((lezart, megszakitva), ([True], [True]))


class BetoltesAlattTest(unittest.TestCase):
    """C25b (58(b)): ha a kereső-modellek nincsenek bent, a hibrid kérés azonnal lexikai választ kap, a háttérben a teljes
    hibrid lánc lefut, és ugyanaz a kérés utána a kész hibrid választ kapja."""

    def test_azonnal_lexikai_utana_hibrid(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _ = alvault(t.name, FAJLOK)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        b = AlBeagyazo()
        tar = vektortar.Vektortar(kereses_api.tar_ut(cfg))
        self.addCleanup(tar.close)
        frissites.frissit(ix._olvaso, tar, b)
        sz = kereses_api.Szolgalat(AlApp(cfg, ix))
        self.addCleanup(lambda: sz.tar() and sz.tar().close())
        sz.beagyazo = b
        bent: set = set()
        sz.betoltve = lambda: bent
        r = sz.hibrid("Mikor vették el a gyerekeket?", 10, "hibrid")
        self.assertEqual((r["mod"], r["ok"]), ("lexikai", "modell_betoltes_alatt"))
        self.assertIn("legalabb", r)
        sz._hatter.join(10)
        r = sz.hibrid("Mikor vették el a gyerekeket?", 10, "hibrid")
        self.assertEqual((r["mod"], r["talalatok"][0]["ut"]), ("hibrid", SPARTA))
        bent.add(b.nev)                              # bent van: azonnal hibrid, háttér nélkül
        r = sz.hibrid("Spárta nevelés", 10, "hibrid")
        self.assertEqual(r["mod"], "hibrid")
        self.assertEqual(sz.hibrid("Spárta", 10, "lexikai")["mod"], "lexikai")


class KotesTest(unittest.TestCase):
    """A modellfél horga a folyamaton belül: a kötött álbeágyazóval és a felépített tárral a keresés hibrid."""

    def test_kotes_hibrid_es_kerdezz(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, v = alvault(t.name, FAJLOK)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        b = AlBeagyazo()
        tar = vektortar.Vektortar(kereses_api.tar_ut(cfg))
        self.addCleanup(tar.close)
        frissites.frissit(ix._olvaso, tar, b)
        app = AlApp(cfg, ix)
        sz = kereses_api.szolgalat(app)
        self.addCleanup(lambda: sz.tar() and sz.tar().close())
        self.assertEqual(sz.kereso().keres("Spárta")["mod"], "lexikai")
        self.assertIs(kereses_api.szolgalat(app), sz)

        def modell(prompt, max_tokens):
            return json.dumps({"mondat": "A spártai fiúkat hétévesen elvették a családtól.", "forras": 1,
                               "idezet": "a fiúkat hétévesen elvették a családtól"}, ensure_ascii=False) + "\n"
        kereses_api.kotes(app, beagyazo=b, modell=modell, kalibralt=True)
        r = sz.kereso().keres("Mikor vették el a gyerekeket?")
        self.assertEqual((r["mod"], r["talalatok"][0]["ut"]), ("hibrid", SPARTA))
        a = kereses_api.vektor_allapot(sz)
        self.assertEqual((a["van"], a["jegyzetek"], a["kotve"]["beagyazo"], a["kotve"]["kalibralt"]),
                         (True, 4, "al-beagyazo", True))
        from core.index.hibrid import kerdezz
        v = kerdezz.valaszol("Hány évesen vették el a spártai fiúkat a családtól?", sz.kereso(), sz.modell,
                             kalibralt=sz.kalibralt)
        self.assertEqual((v["allapot"], v["proba"]), ("kesz", False))


class KalibraltModellVerzioTest(unittest.TestCase):
    """Lelet 7: a „Kérdezz” / keresés kötése csak az aranyhalmaz AKTUÁLIS verzióján kalibrált sort fogadja el (mint a router)."""

    def test_az_elavult_verzion_kalibralt_sor_nem_kot(self):
        from core.modell import kalibracio
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, root, _ = alg_core(t.name)
        for feladat, verzio in (("szoveg", "v2"), ("beagyazas", "v1")):
            mappa = cfg.path("modulok") / "eval" / feladat
            mappa.mkdir(parents=True)
            (mappa / "feladat.py").write_text(f'ROUTER_FELADAT = "{feladat}"\nVERZIO = "{verzio}"\n', encoding="utf-8")
        tabla = kalibracio.Tabla(cfg.path("router_db"))
        tabla.rogzit("szoveg", "regi-modell", 0.9, "v1", kalibralt=True)                 # elavult verzió
        tabla.rogzit("beagyazas", "bge_m3", 0.86, "v1", kalibralt=True)                  # aktuális verzió
        tabla.close()
        sz = kereses_api.Szolgalat(AlApp(cfg, None))
        self.assertIsNone(sz._kalibralt_modell("szoveg"))
        self.assertEqual(sz._kalibralt_modell("beagyazas"), "bge_m3")
        tabla = kalibracio.Tabla(cfg.path("router_db"))
        tabla.rogzit("szoveg", "uj-modell", 0.8, "v2", kalibralt=True)
        tabla.close()
        self.assertEqual(sz._kalibralt_modell("szoveg"), "uj-modell")


if __name__ == "__main__":
    unittest.main()
