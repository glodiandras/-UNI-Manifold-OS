"""C22a: a kvíz végpontjai a valódi core-on, álvaulton (`core/kviz_api.py`): a kvíz kulcs nélkül, a megoldás a válasz után, a
kitöltés értékelése a core-ban és mentése a `tanulas.sqlite`-ba (idempotens), a „hibás kérdés” jelölés. A végpontok a vaultba nem
írnak; a `## Kitöltések` szakaszt (C22b) késleltetve a gépi-írás szolgáltatás írja (`KitoltesSzakaszTest`)."""
import http.client
import json
import os
import threading
import time
import unittest
import urllib.parse

from core import kviz_api, server, snapshot, tanulas_db
from modulok.kviz import esemeny as ES
from modulok.kviz import formatum as FM
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.test_core_api import _Kimenet
from tests.test_kviz_generalas import JEGYZET as FORRAS_SZOVEG
from tests.test_kviz_ertekeles import kviz, rossz

FORRAS = "M03 - Algebra/Elmélet/04 - Nevezetes szorzatok.md"
KVIZ = "ATTCHMNTS - quizes/Nevezetes szorzatok — Kvíz 2026-10-04 2030.md"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.q = kviz()
        ir(self.v, FORRAS, FORRAS_SZOVEG)
        ir(self.v, KVIZ, FM.ir(self.q))
        ir(self.v, "ATTCHMNTS - quizes/Üres jegyzet.md", "# Üres\n\nSemmi kérdés.\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.fejek = len(self.repo.log(10))
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

    def k(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def lekerdez(self, ut=KVIZ):
        return self.k("GET", "/api/kviz/kviz?" + urllib.parse.urlencode({"ut": ut}))

    def token(self, ut=KVIZ):
        return self.lekerdez(ut)[1]["token"]

    def valaszol(self, token, valaszok, ut=KVIZ):
        """A válaszok rögzítése a kitöltésben (a `megoldas` végponton át, mint a felület)."""
        for v in valaszok:
            kod, d = self.k("POST", "/api/kviz/megoldas", {"ut": ut, "token": token, "kerdes": v["kerdes"], "valasz": v["valasz"],
                                                           "tipp": v.get("tipp", False), "ms": v.get("ms")})
            self.assertEqual(kod, 200, d)

    def kitolt(self, kulcs="u-0001-abcd", mod="teljes", valaszok=None, ut=KVIZ, token=None):
        q = self.q
        valaszok = valaszok if valaszok is not None else [
            {"kerdes": "k1", "valasz": q.kerdesek[0].helyes, "tipp": False, "ms": 900},
            {"kerdes": "k2", "valasz": rossz(q, 1), "tipp": False},
            {"kerdes": "k3", "valasz": q.kerdesek[2].helyes, "tipp": True}]
        token = token or self.token(ut)
        self.valaszol(token, valaszok, ut)
        return self.k("POST", "/api/kviz/kitoltes", {"ut": ut, "token": token, "kulcs": kulcs, "mod": mod, "ido_ms": 61000})


class KvizLekerdezesTest(Alap):
    def test_a_kviz_kulcs_nelkul(self):
        kod, d = self.lekerdez()
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["ut"], KVIZ)
        self.assertEqual(d["forras_ut"], FORRAS)
        self.assertEqual(d["hibak"], [])
        self.assertEqual([x["id"] for x in d["kviz"]["kerdesek"]], ["k1", "k2", "k3"])
        self.assertTrue(d["token"])
        szoveg = json.dumps({k: v for k, v in d.items() if k != "token"}, ensure_ascii=False)
        self.assertNotIn("helyes", szoveg)
        self.assertNotIn("Két tag összegének", szoveg)              # az idézet a válasz után jön
        self.assertEqual((d["elozmenyek"], d["ujra"], d["megvaltozott"]), ([], [], False))

    def test_hibas_utak(self):
        for rossz_ut, kod in ((FORRAS, 400), ("../kint.md", 400), ("ATTCHMNTS - quizes/kep.png", 400),
                              ("ATTCHMNTS - quizes/Nincs.md", 404), ("ATTCHMNTS - quizes/Üres jegyzet.md", 400)):
            self.assertEqual(self.lekerdez(rossz_ut)[0], kod, rossz_ut)
        self.assertEqual(self.k("GET", "/api/kviz/kviz")[0], 400)

    def test_kezzel_irt_kviz_azonosito_tartalekkal(self):
        szoveg = FM.ir(self.q).replace("Kviz: KVIZ-20261004-203015-3fa91c\n", "")
        ir(self.v, "ATTCHMNTS - quizes/Kézi.md", szoveg)
        self.assertTrue(var_ra(lambda: self.lekerdez("ATTCHMNTS - quizes/Kézi.md")[0] == 200, 5))
        kod, d = self.lekerdez("ATTCHMNTS - quizes/Kézi.md")
        self.assertTrue(FM.AZON_RE.match(d["kviz"]["azon"]), d["kviz"]["azon"])

    def test_hibas_kerdes_a_hibak_kozt_marad_a_tobbi_kitoltheto(self):
        szoveg = FM.ir(self.q)
        a = szoveg.index("> [!success]- Megoldás")
        b = szoveg.index("> [!question] 3. kérdés")
        ir(self.v, "ATTCHMNTS - quizes/Csonka.md", szoveg[:a] + szoveg[b:])
        self.assertTrue(var_ra(lambda: self.lekerdez("ATTCHMNTS - quizes/Csonka.md")[0] == 200, 5))
        kod, d = self.lekerdez("ATTCHMNTS - quizes/Csonka.md")
        self.assertEqual([h["fajta"] for h in d["hibak"]], ["megoldas_nelkul"])
        self.assertEqual([x["id"] for x in d["kviz"]["kerdesek"]], ["k3"])


class MegoldasTest(Alap):
    def megold(self, token=None, **kw):
        return self.k("POST", "/api/kviz/megoldas", {"ut": KVIZ, "token": token or self.t, **kw})

    def setUp(self):
        super().setUp()
        self.t = self.token()

    def test_helyes_es_rossz_valasz(self):
        kod, d = self.megold(kerdes="k1", valasz=self.q.kerdesek[0].helyes)
        self.assertEqual((kod, d["helyes"]), (200, True))
        kod, d = self.megold(kerdes="k2", valasz=0)
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["helyes"], d["helyes_index"], d["helyes_valasz"], d["szakasz"], d["jegyzet"]),
                         (False, 2, "$(a+b)(a-b)$", "Szorzattá alakítás", FORRAS[:-3]))
        self.assertIn("kifejezés szorzattá alakítva", d["idezet"])
        kod, d = self.megold(kerdes="k3", valasz=None)                               # „nem tudom”: rögzítés, utána kulcs
        self.assertEqual((kod, d["helyes"]), (200, False))

    def test_valasz_nelkul_nincs_kulcs(self):
        """A3-03: a válasz rögzítése nélküli kérés (hiányzó `valasz`, token nélkül, ismeretlen token) nem kap kulcsot."""
        for torzs in ({"ut": KVIZ, "token": self.t, "kerdes": "k1"},                  # nincs `valasz`
                      {"ut": KVIZ, "kerdes": "k1", "valasz": None},                   # nincs token
                      {"ut": KVIZ, "token": "x" * 32, "kerdes": "k1", "valasz": 0}):   # ismeretlen token
            kod, d = self.k("POST", "/api/kviz/megoldas", torzs)
            self.assertIn(kod, (400, 410), torzs)
            for kulcs in ("helyes_index", "helyes_valasz", "magyarazat", "idezet", "horgony", "helyes"):
                self.assertNotIn(kulcs, d, torzs)

    def test_az_elso_valasz_vegleges(self):
        """A3-03: a kulcs nem szondázható — a rögzített válasz után a másik válasz nem módosítja az eredményt."""
        kod, elso = self.megold(kerdes="k1", valasz=0)                               # rossz
        kod, masodik = self.megold(kerdes="k1", valasz=elso["helyes_index"])         # a most megismert kulccsal próbál
        self.assertEqual((elso["helyes"], masodik["helyes"]), (False, False))
        kod, d = self.k("POST", "/api/kviz/kitoltes", {"ut": KVIZ, "token": self.t, "kulcs": "u-0001-abcd", "mod": "teljes"})
        self.assertEqual(d["ertekeles"]["eredmenyek"][0]["valasz"], 0)
        self.assertEqual(d["ertekeles"]["osszegzes"]["pont"], 0)

    def test_masik_kitoltes_tokenje_nem_oroklodik(self):
        self.megold(kerdes="k1", valasz=0)
        masik = self.token()
        self.assertEqual(self.megold(token=masik, kerdes="k1", valasz=self.q.kerdesek[0].helyes)[1]["helyes"], True)

    def test_token_masik_kvizhez_409(self):
        ir(self.v, "ATTCHMNTS - quizes/Másik.md", FM.ir(self.q).replace("Kviz: KVIZ-20261004-203015-3fa91c", "Kviz: KVIZ-20261004-203015-aaaaaa"))
        self.assertTrue(var_ra(lambda: self.lekerdez("ATTCHMNTS - quizes/Másik.md")[0] == 200, 5))
        kod, d = self.k("POST", "/api/kviz/megoldas", {"ut": "ATTCHMNTS - quizes/Másik.md", "token": self.t, "kerdes": "k1", "valasz": 0})
        self.assertEqual(kod, 409, d)

    def test_a_megvaltozott_kviz_tokenje_409(self):
        ir(self.v, KVIZ, FM.ir(self.q).replace("$(a+b)(a-b)$", "$(a-b)(a+b)$", 1))
        self.assertTrue(var_ra(lambda: self.megold(kerdes="k1", valasz=0)[0] == 409, 5))

    def test_hibak(self):
        self.assertEqual(self.megold(kerdes="k9", valasz=0)[0], 400)
        self.assertEqual(self.megold(valasz=0)[0], 400)
        self.assertEqual(self.megold(kerdes="k1", valasz="A")[0], 400)
        self.assertEqual(self.megold(kerdes="k1", valasz=True)[0], 400)

    def test_nem_ir_semmit(self):
        self.megold(kerdes="k1", valasz=1)
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertIsNone(c)


class KitoltesTest(Alap):
    def test_ertekeles_mentes_es_tracker_adat(self):
        kod, d = self.kitolt()
        self.assertEqual(kod, 200, d)
        self.assertTrue(d["uj"])
        o = d["ertekeles"]["osszegzes"]
        self.assertEqual((o["pont"], o["osszes"], o["szazalek"]), (2, 3, 67))
        self.assertEqual(d["ertekeles"]["javaslatok"][0]["szakasz"], "Szorzattá alakítás")
        self.assertEqual(d["tracker"]["ut"], FORRAS)                                # a tantárgyhoz a forrásjegyzet
        self.assertEqual(ES.hibak(d["tracker"]["adat"]), [])
        self.assertEqual((d["tracker"]["adat"]["pont"], d["tracker"]["adat"]["kviz"]), (2, self.q.azon))
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_kitoltes").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_valasz").fetchone()[0], 3)

    def test_az_ujrakuldes_nem_duplikal(self):
        kod, elso = self.kitolt("u-0001-abcd")
        kod, masodik = self.k("POST", "/api/kviz/kitoltes", {"ut": KVIZ, "token": elso["token"], "kulcs": "u-0001-abcd", "mod": "teljes"})
        self.assertEqual((kod, masodik["uj"]), (200, False))
        self.assertEqual(masodik["ertekeles"], elso["ertekeles"])
        self.assertEqual(masodik["tracker"], elso["tracker"])
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_kitoltes").fetchone()[0], 1)

    def test_elozmeny_trend_es_ujra(self):
        self.kitolt("u-0001-abcd")
        kod, d = self.lekerdez()
        self.assertEqual([x["szazalek"] for x in d["elozmenyek"]], [67])
        self.assertEqual(d["ujra"], ["k2", "k3"])                                   # a hibás és a tippelt
        kod, masodik = self.kitolt("u-0002-abcd", mod="hibasak", valaszok=[{"kerdes": "k2", "valasz": 2, "tipp": False}])
        self.assertEqual(masodik["ertekeles"]["osszegzes"]["osszes"], 1)
        self.assertEqual(masodik["ertekeles"]["trend"]["javult"], 1)

    def test_a_megvaltozott_kviz_jelezve(self):
        self.kitolt()
        szoveg = FM.ir(self.q).replace("$(a+b)(a-b)$", "$(a-b)(a+b)$", 1)           # a helyes válasz szövege változott
        ir(self.v, KVIZ, szoveg)
        self.assertTrue(var_ra(lambda: self.lekerdez()[1]["megvaltozott"], 5))

    def test_fedetlen_szakaszok_a_forrasbol(self):
        """A forrásjegyzet egy újabb szakasza, amelyből a kvíz nem kérdez, az elemzésben jelezve."""
        ir(self.v, FORRAS, FORRAS_SZOVEG + "\n## Harmadik szakasz\n\nEz egy újabb szakasz, amelyből a kvíz nem kérdez.\n")
        kod, d = self.kitolt(valaszok=[{"kerdes": "k1", "valasz": 1, "tipp": False}])
        self.assertEqual(d["ertekeles"]["fedetlen_szakaszok"], ["Harmadik szakasz"])

    def test_hibas_kerdesek(self):
        t = self.token()
        self.valaszol(t, [{"kerdes": "k1", "valasz": 0}])
        alap = {"ut": KVIZ, "token": t, "kulcs": "u-1234567", "mod": "teljes"}
        for rossz_torzs in ({"kulcs": ""}, {"kulcs": "x y"}, {"mod": "furcsa"}, {"ido_ms": "x"}, {"ido_ms": -1},
                            {"token": None}, {"token": "x" * 32}):
            self.assertIn(self.k("POST", "/api/kviz/kitoltes", {**alap, **rossz_torzs})[0], (400, 410), rossz_torzs)
        # válasz nélküli kitöltés nem értékelhető
        self.assertEqual(self.k("POST", "/api/kviz/kitoltes", {**alap, "token": self.token()})[0], 400)
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertIsNone(c)                                                    # semmi nem mentődött

    def test_a_kliens_valaszai_nem_szamitanak(self):
        """A3-03/04: a kérés `valaszok` mezője figyelmen kívül marad — csak a rögzített válaszok pontoznak."""
        t = self.token()
        self.valaszol(t, [{"kerdes": "k1", "valasz": 0}])                            # rossz
        csalas = [{"kerdes": k, "valasz": self.q.kerdesek[i].helyes, "tipp": False} for i, k in enumerate(("k1", "k2", "k3"))]
        kod, d = self.k("POST", "/api/kviz/kitoltes", {"ut": KVIZ, "token": t, "kulcs": "u-1234567", "mod": "teljes", "valaszok": csalas})
        o = d["ertekeles"]["osszegzes"]
        self.assertEqual((kod, o["pont"], o["osszes"]), (200, 0, 3))

    def test_teljes_modban_a_nevezo_az_osszes_kerdes(self):
        """A3-04: egy helyes válasz a háromból 1/3, nem 1/1."""
        kod, d = self.kitolt(valaszok=[{"kerdes": "k1", "valasz": self.q.kerdesek[0].helyes, "tipp": False}])
        o = d["ertekeles"]["osszegzes"]
        self.assertEqual((kod, o["pont"], o["osszes"], o["szazalek"]), (200, 1, 3, 33))
        self.assertEqual(o["matrix"]["hiany"], 2)
        self.assertEqual(len(d["ertekeles"]["eredmenyek"]), 3)

    def test_hibasak_modban_a_nevezo_a_megvalaszoltak(self):
        self.kitolt("u-0001-abcd")
        kod, d = self.kitolt("u-0002-abcd", mod="hibasak", valaszok=[{"kerdes": "k2", "valasz": 2, "tipp": False}])
        self.assertEqual(d["ertekeles"]["osszegzes"]["osszes"], 1)

    def test_a_masik_kviz_kulcsa_nem_ad_ki_ertekelest(self):
        """A3-04: a kulcs a kvíz azonosítójával együtt egyedi — egy másik kvíz kulcsával nem kapható vissza az értékelés."""
        kod, elso = self.kitolt("u-0001-abcd")
        self.assertEqual(kod, 200, elso)
        ir(self.v, "ATTCHMNTS - quizes/Másik.md", FM.ir(self.q).replace("Kviz: KVIZ-20261004-203015-3fa91c", "Kviz: KVIZ-20261004-203015-aaaaaa"))
        self.assertTrue(var_ra(lambda: self.lekerdez("ATTCHMNTS - quizes/Másik.md")[0] == 200, 5))
        kod, d = self.kitolt("u-0001-abcd", ut="ATTCHMNTS - quizes/Másik.md", valaszok=[{"kerdes": "k1", "valasz": 0}])
        self.assertEqual(kod, 409, d)
        self.assertNotIn("ertekeles", d)
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_kitoltes").fetchone()[0], 1)

    def test_a_kitoltes_utan_uj_token_jar(self):
        t = self.token()
        kod, d = self.kitolt("u-0001-abcd", token=t)
        self.assertTrue(d["token"] and d["token"] != t)
        kod, vissza = self.k("POST", "/api/kviz/megoldas", {"ut": KVIZ, "token": t, "kerdes": "k1", "valasz": 0})
        self.assertEqual(kod, 410, vissza)                                          # a mentett kitöltés tokenje lezárult
        kod, d2 = self.k("POST", "/api/kviz/megoldas", {"ut": KVIZ, "token": d["token"], "kerdes": "k1", "valasz": 0})
        self.assertEqual(kod, 200, d2)

    def test_a_vegpont_nem_ir_a_vaultba(self):
        """A végpont maga nem ír; a `## Kitöltések` írása késleltetett (alapból 60 s), és a gépi-írás szolgáltatásé."""
        elotte = {p: (self.v / p).read_bytes() for p in (FORRAS, KVIZ)}
        self.kitolt()
        self.k("POST", "/api/kviz/jelol", {"ut": KVIZ, "kerdes": "k1", "hibas": True})
        for p, b in elotte.items():
            self.assertEqual((self.v / p).read_bytes(), b, p)
        self.assertEqual(len(self.repo.log(10)), self.fejek)                         # nincs új pillanatkép


class KitoltesSzakaszTest(Alap):
    """C22b: a kitöltés után a `## Kitöltések` szakasz a DB-ből íródik, késleltetve; az addigi kitöltések egy gépi commitba
    vonódnak össze (`Mos-Forras: mos-kviz-kitoltes`, determinisztikus írás); a nyitott, mentetlen kvízjegyzetbe nem ír."""

    def setUp(self):
        regi = kviz_api.KITOLTES_KESLELTETES_S
        kviz_api.KITOLTES_KESLELTETES_S = 1.0
        self.addCleanup(setattr, kviz_api, "KITOLTES_KESLELTETES_S", regi)
        super().setUp()

    def api(self):
        return self.szerver_app().kviz_api

    def szerver_app(self):
        import gc
        return next(o for o in gc.get_objects() if type(o).__name__ == "App" and getattr(o, "cfg", None) is self.cfg)

    def commitok(self):
        return [c for c in self.repo.log(20) if "mos-kviz-kitoltes" in c.trailers.values()]

    def test_ket_kitoltes_egy_commit(self):
        self.kitolt("u-0001-abcd")
        self.kitolt("u-0002-abcd")
        self.assertTrue(var_ra(lambda: (self.v / KVIZ).read_text(encoding="utf-8").count("\n- 20") == 2, 15))
        szoveg = (self.v / KVIZ).read_text(encoding="utf-8")
        self.assertNotIn("Még nincs kitöltés.", szoveg)
        self.assertIn("## Kérdések", szoveg)                                       # a jegyzet többi része érintetlen
        self.assertTrue(var_ra(lambda: len(self.commitok()) == 1, 10))
        self.assertEqual(len(self.repo.log(20)), self.fejek + 1)                    # egy gépi commit a két kitöltésre
        self.assertEqual(self.api().utolso_iras.get(KVIZ), "ok")

    def test_a_jeloles_is_bekerul(self):
        t = self.token()
        self.valaszol(t, [{"kerdes": "k2", "valasz": 0}])
        self.k("POST", "/api/kviz/jelol", {"ut": KVIZ, "token": t, "kerdes": "k2", "hibas": True})
        self.assertTrue(var_ra(lambda: "Hibásnak jelölt kérdés: 2." in (self.v / KVIZ).read_text(encoding="utf-8"), 15))

    def test_nyitott_mentetlen_kvizjegyzetbe_nem_ir(self):
        app = self.szerver_app()
        app.gepi.mentetlen = lambda: {KVIZ}            # a felület WS-jelzése helyett: a kvízjegyzet nyitott és mentetlen
        elotte = (self.v / KVIZ).read_bytes()
        self.kitolt()
        self.assertTrue(var_ra(lambda: KVIZ in app.kviz_api.utolso_iras, 30))
        self.assertEqual(app.kviz_api.utolso_iras[KVIZ], "kesobb")
        self.assertEqual((self.v / KVIZ).read_bytes(), elotte)


class JelolesTest(Alap):
    def setUp(self):
        super().setUp()
        self.t = self.token()

    def jelol(self, **kw):
        return self.k("POST", "/api/kviz/jelol", {"ut": KVIZ, "token": self.t, **kw})

    def test_jeloles_be_ki(self):
        self.valaszol(self.t, [{"kerdes": "k3", "valasz": 0}])
        kod, d = self.jelol(kerdes="k3", hibas=True, megjegyzes="félreérthető")
        self.assertEqual((kod, d["jelolesek"]), (200, ["k3"]))
        self.assertTrue([x for x in self.lekerdez()[1]["kviz"]["kerdesek"] if x["id"] == "k3"][0]["jelolt"])
        kod, k = self.kitolt(token=self.t)
        self.assertEqual(k["ertekeles"]["osszegzes"]["osszes"], 2)                   # a jelölt kérdés nem számít
        self.assertEqual(self.jelol(kerdes="k3", hibas=False)[0], 410)               # a lezárt kitöltésben már nem
        self.assertEqual(self.k("POST", "/api/kviz/jelol", {"ut": KVIZ, "token": k["token"], "kerdes": "k3", "hibas": False})[0], 400)

    def test_csak_megvalaszolt_kerdes_jelolheto(self):
        """A3-04: megválaszolatlan kérdés nem jelölhető (a megoldás utáni kiesés csak a rögzített válasz után, és csak
        az adott kitöltés kérdésére áll)."""
        kod, d = self.jelol(kerdes="k1", hibas=True)
        self.assertEqual(kod, 400, d)
        self.assertEqual(self.k("POST", "/api/kviz/jelol", {"ut": KVIZ, "kerdes": "k1", "hibas": True})[0], 400)    # token nélkül
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertIsNone(c)

    def test_hibak(self):
        self.valaszol(self.t, [{"kerdes": "k1", "valasz": 0}])
        self.assertEqual(self.jelol(kerdes="k9", hibas=True)[0], 400)
        self.assertEqual(self.jelol(kerdes="k1", hibas="igen")[0], 400)
        self.assertEqual(self.jelol(hibas=True)[0], 400)


if __name__ == "__main__":
    unittest.main()
