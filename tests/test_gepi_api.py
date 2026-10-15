"""A gépi írás a futó core-on (C16.5): a végpont és a kliens, álfeladat a valódi feladatsoron át, a felület
mentetlen-jelzése a WebSocketen, visszavonás tételre és körre futó vault-író feladat mellett, indulási helyreállítás."""
import hashlib
import json
import os
import sys
import time
import unittest
from unittest import mock

from core import gepi_iras, gepi_kliens, snapshot, tasks
from tests.helpers import REPO
from tests.test_core_api import _Szerver, ws_connect, ws_csatlakozik

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
ALAP = FM + "# A\n\n## Gyakorlás\nelső\n"

LEPES = """
import sys, time
from core import gepi_kliens as gepi
kor = gepi.uj_kor("KARTYA")
for i in (1, 2):
    a = gepi.olvas("T01/a.md")
    r = gepi.ir(kor, tetel=f"t{i}", forras="mos-kartya", uzenet=f"kártyák {i}", modell=None, muveletek=[
        gepi.uj(f"T01/a — kártyák {i}.md", sys.argv[1] + f"# a — kártyák {i}\\n", osztaly="normal"),
        gepi.beszuras("T01/a.md", "Gyakorlás", f"![[a — kártyák {i}]]", alap=a["hash"])])
    print("TETEL", r["kor"], r["sha"], flush=True)
    time.sleep(float(sys.argv[2]))
"""


LEPES_KAPU = """
import json, os, sys, urllib.error, urllib.request
u, tok = os.environ["MOS_CORE_URL"], os.environ["MOS_LEPES_TOKEN"]
def hiv(met, ut, torzs=None, token=tok):
    h = {"X-Manifold": token, "Content-Type": "application/json"}      # a lépés hitelesítője a lépés-token (35. döntés + T137)
    r = urllib.request.Request(u + ut, data=json.dumps(torzs).encode() if torzs is not None else None, method=met, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status
    except urllib.error.HTTPError as e:
        e.close()
        return e.code
print("PUT_FAJL", hiv("PUT", "/api/vault/fajl", {"ut": "T01/a.md", "tartalom": "valami\\n", "alap": "0" * 40}), flush=True)
print("UJ", hiv("POST", "/api/vault/uj", {"mappa": "T01", "nev": "Lepes uj"}), flush=True)
print("FELADAT", hiv("POST", "/api/feladatok", {"tipus": "mentes"}), flush=True)
print("GET", hiv("GET", "/api/vault/fajl?ut=T01/a.md"), flush=True)
print("TUKROZOTT", hiv("POST", "/api/vault/tulajdonsagok/elemez", {"ut": "T01/a.md", "fm": None}), flush=True)
print("HAMIS_GET", hiv("GET", "/api/vault/fajl?ut=T01/a.md", token="hamis"), flush=True)
print("HAMIS_PUT", hiv("PUT", "/api/vault/fajl", {"ut": "T01/a.md", "tartalom": "x", "alap": "0" * 40}, token="hamis"), flush=True)
print("TITOK_ENV", "NINCS" if "MOS_API_TITOK" not in os.environ else "VAN", flush=True)
"""


class GepiApiTest(_Szerver):
    def elokeszit(self):
        vissza = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(REPO)
        self.addCleanup(lambda: os.environ.pop("PYTHONPATH", None) if vissza is None
                        else os.environ.__setitem__("PYTHONPATH", vissza))
        (self.v / "T01").mkdir()
        (self.v / "T01" / "a.md").write_text(ALAP, encoding="utf-8")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.url = None

    def ir(self, *muveletek, kor="KARTYA-20261003-101500", tetel="t1", **tobbi):
        return self.k("POST", "/api/gepi-iras", {"kor": kor, "tetel": tetel, "forras": "mos-kartya", "modell": None,
                                                 "muveletek": list(muveletek), **tobbi})

    def a(self) -> str:
        return (self.v / "T01" / "a.md").read_text(encoding="utf-8")

    def test_vegpont_es_hibakodok(self):
        besz = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "gépi"}
        kod, r = self.ir(besz)
        self.assertEqual(kod, 200, r)
        self.assertEqual(self.a(), ALAP + "gépi\n")
        self.assertEqual(self.repo.log(1)[0].sha, r["sha"])
        self.assertEqual(self.ir(besz)[1]["ismetles"], True)
        self.assertEqual(self.ir(dict(besz, szakasz="Nincs"), tetel="t2")[0], 404)
        kod, r = self.ir({"tipus": "csere", "ut": "T01/a.md", "tartalom": "x", "alap": "0" * 40}, tetel="t3")
        self.assertEqual((kod, r["utkozes"], r["ut"]), (409, True, "T01/a.md"))
        kod, r = self.ir({"tipus": "uj", "ut": "T01/uj.md", "tartalom": "# nincs séma\n", "osztaly": "normal"}, tetel="t4")
        self.assertEqual((kod, r["sema"]), (400, True))
        self.assertEqual(self.ir(besz, kor="rossz")[0], 400)
        self.assertEqual(self.k("POST", "/api/gepi-iras", {"kor": "X"}, {"X-Manifold": "0"})[0], 403)
        # a kör a visszavonás végpontján érvényes azonosító (új előtag), a próba-kör nem
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "KARTYA-20261003-101500"})[0], 200)
        self.assertEqual(self.a(), ALAP)
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "KARTYA-20261003-101500-proba"})[0], 400)

    def test_kliens(self):
        u = f"http://127.0.0.1:{self.port}"
        h = gepi_kliens.olvas("T01/a.md", url=u)["hash"]
        self.assertEqual(h, hashlib.sha1(ALAP.encode()).hexdigest())
        r = gepi_kliens.ir("KARTYA-20261003-101500", "t1", "mos-kartya",
                           [gepi_kliens.csere("T01/a.md", ALAP + "kliens\n", h)], modell=None, url=u, varakozas_mp=0)
        self.assertTrue(r["valtozas"])
        with self.assertRaises(gepi_kliens.GepiHiba) as cm:
            gepi_kliens.ir("KARTYA-20261003-101500", "t2", "mos-kartya",
                           [gepi_kliens.csere("T01/a.md", "x", h)], modell=None, url=u, varakozas_mp=0)
        self.assertEqual((cm.exception.kod, cm.exception.adat["utkozes"]), (409, True))

    def test_modell_kotelezo_a_vegponton_es_a_kliensben(self):
        """T043 (C29.8): `modell` nélküli kérés 400 (ma ír); a kliensben a `modell` kötelező kulcsszó (a `None` = determinisztikus)."""
        u = f"http://127.0.0.1:{self.port}"
        besz = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "gépi"}
        kod, r = self.k("POST", "/api/gepi-iras", {"kor": "KARTYA-20261003-101500", "tetel": "t1", "forras": "mos-kartya",
                                                   "muveletek": [besz]})
        self.assertEqual(kod, 400, r)
        self.assertEqual(self.a(), ALAP)
        with self.assertRaises(TypeError):                              # a láncnak ki kell mondania: modell vagy None
            gepi_kliens.ir("KARTYA-20261003-101500", "t1", "mos-kartya", [besz], url=u, varakozas_mp=0)
        kod, r = self.ir(besz, modell={"feladat": "nincs_ilyen_feladat", "modell": "x"})
        self.assertEqual(kod, 400, r)

    def test_lepes_token_a_szerkesztoi_irasi_vegpontokat_nem_eri_el(self):
        """T137 (C29.8, 28(a)): a lépés-folyamat tokenes kérése nem hívhatja a szerkesztői író végpontokat (403), a gépi írás és a
        tiszta számolók mennek; a hamis token minden kérésre 403."""
        tasks.register(tasks.TaskType("t_lepes", "lépés-kapu", lambda c, p, s: (
            [tasks.Step("kapu", [sys.executable, "-B", "-c", LEPES_KAPU], str(REPO))], "", []), frozenset()))
        fid = self.k("POST", "/api/feladatok", {"tipus": "t_lepes"})[1]["id"]
        d = self.var(fid)
        self.assertEqual(d["allapot"], "kesz", d)
        eredmeny = dict(s.split() for s in self.k("GET", f"/api/feladatok/{fid}")[1]["sorok"]
                        if s.split()[:1] and s.split()[0] in ("PUT_FAJL", "UJ", "FELADAT", "GET", "TUKROZOTT", "HAMIS_GET", "HAMIS_PUT", "TITOK_ENV"))
        self.assertEqual(eredmeny, {"PUT_FAJL": "403", "UJ": "403", "FELADAT": "403", "GET": "200", "TUKROZOTT": "200",
                                    "HAMIS_GET": "403", "HAMIS_PUT": "403",               # ma: PUT_FAJL 409 (az ütköző alap), UJ 201
                                    "TITOK_ENV": "NINCS"})                                # a lépés a felületi API-titkot nem kapja
        self.assertEqual(self.a(), ALAP)
        self.assertFalse((self.v / "T01" / "Lepes uj.md").exists())
        # a feladat vége után a token lejár: a (kiszivárgott) token már nem érvényes
        self.assertEqual(self.k("GET", "/api/allapot", fejlec={"X-Manifold": "bármi-lejárt-token"})[0], 403)
        self.assertEqual(self.k("GET", "/api/allapot")[0], 200)                         # a felületi titok (a `k` alapja) a teljes jogú

    def test_modell_jel_a_worker_valaszabol(self):
        valasz = {"object": "chat.completion", "model": "repo/x", "modell": "qwen35_9b", "feladat": "szoveg", "proba": False,
                  "keret_gb": 5.0, "choices": []}
        self.assertEqual(gepi_kliens.modell_jel(valasz), {"feladat": "szoveg", "modell": "qwen35_9b", "proba": False})
        self.assertEqual(gepi_kliens.modell_jel({**valasz, "proba": True})["proba"], True)
        with self.assertRaises(ValueError):
            gepi_kliens.modell_jel({"choices": []})                    # nem worker-válasz

    def test_kliens_a_titkot_a_kornyezetbol_kuldi(self):
        """35. döntés (T071): a lépés-folyamat a `MOS_API_TITOK`-ot kapja (a feladatsor adja); nélküle a core 403-at ad."""
        u = f"http://127.0.0.1:{self.port}"
        with mock.patch.dict(os.environ):
            os.environ.pop("MOS_API_TITOK", None)
            with self.assertRaises(gepi_kliens.GepiHiba) as cm:
                gepi_kliens.olvas("T01/a.md", url=u)
            self.assertEqual(cm.exception.kod, 403)
            os.environ["MOS_API_TITOK"] = "rossz-titok-0123456789"
            with self.assertRaises(gepi_kliens.GepiHiba) as cm:
                gepi_kliens.olvas("T01/a.md", url=u)
            self.assertEqual(cm.exception.kod, 403)
        self.assertTrue(gepi_kliens.olvas("T01/a.md", url=u)["hash"])         # a tesztkörnyezet titkával megy

    def test_kliens_a_lepes_tokent_kuldi_ha_van_es_az_elsobbseget_elvez(self):
        """T137 + 35. döntés: a lépés-folyamat `MOS_LEPES_TOKEN`-je az `X-Manifold` értéke; ha van, az előbbre való a felületi titoknál
        (egy érvénytelen token 403, a titok jelenléte nem menti meg); token nélkül (kézi próba, teszt) a `MOS_API_TITOK` megy."""
        u = f"http://127.0.0.1:{self.port}"
        with mock.patch.dict(os.environ, {"MOS_LEPES_TOKEN": "nem-letezo-lepes-token"}):
            self.assertTrue(os.environ["MOS_API_TITOK"])
            with self.assertRaises(gepi_kliens.GepiHiba) as cm:
                gepi_kliens.olvas("T01/a.md", url=u)
            self.assertEqual(cm.exception.kod, 403)

    @unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
    def test_mentetlen_jelzes_a_ws_en_es_esemeny(self):
        besz = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "gépi"}
        with ws_csatlakozik(self.port) as ws:
            self.assertEqual(json.loads(ws.recv(timeout=5))["tipus"], "hello")
            ws.send(json.dumps({"tipus": "mentetlen", "utak": ["T01/a.md"]}))
            ws.send("nem json")                                         # a hibás üzenet némán kimarad
            ws.ping().wait(5)                                           # a core feldolgozta az előzőket
            kod, r = self.ir(besz)
            self.assertEqual((kod, r["nyitott"], r["utak"]), (409, True, ["T01/a.md"]))
            self.assertEqual(self.a(), ALAP)
            ws.send(json.dumps({"tipus": "mentetlen", "utak": []}))
            ws.ping().wait(5)
            kod, r = self.ir(besz)
            self.assertEqual(kod, 200, r)
            tipusok = {}
            while "gepi_iras" not in tipusok:
                e = json.loads(ws.recv(timeout=10))
                tipusok[e["tipus"]] = e
            self.assertEqual((tipusok["gepi_iras"]["sha"], tipusok["gepi_iras"]["utak"]), (r["sha"], ["T01/a.md"]))
            self.assertEqual(tipusok["vault_iras"]["pillanat"], r["sha"])
            ws.send(json.dumps({"tipus": "mentetlen", "utak": ["T01/a.md"]}))
            ws.ping().wait(5)
        # T107 (C29.7b): a kapcsolat zárása után a halmaz türelmi ideig megmarad (a visszacsatlakozó felület szövege él) …
        kod, r = self.ir(dict(besz, szoveg="zárás után"), tetel="t2")
        self.assertEqual((kod, r["nyitott"]), (409, True), "a bontás pillanatában a gép még nem írhat a mentetlen mellé")
        # … és az új kapcsolat teljes (itt üres) halmaza felszabadítja: a jelzés nem ragad be
        with ws_csatlakozik(self.port) as ws:
            self.assertEqual(json.loads(ws.recv(timeout=5))["tipus"], "hello")
            ws.send(json.dumps({"tipus": "mentetlen", "utak": []}))
            ws.ping().wait(5)
            kod, r = self.ir(dict(besz, szoveg="zárás után"), tetel="t2")
            self.assertEqual(kod, 200, r)

    def test_alfeladat_a_feladatsoron_at_es_visszavonas_futas_kozben(self):
        """Egy vault-író álfeladat lépése a klienssel ír (két tétel egy körben); az első tétel a feladat futása
        közben visszavonható (28. döntés), a végén a kör egésze is."""
        tasks.register(tasks.TaskType("t_gepi", "álfeladat", lambda c, p, s: (
            [tasks.Step("ír", [sys.executable, "-B", "-c", LEPES, FM, "1.5"], str(REPO))], "", []),
            frozenset({"vault"})))
        fid = self.k("POST", "/api/feladatok", {"tipus": "t_gepi"})[1]["id"]
        t0, sorok = time.time(), []
        while time.time() - t0 < 15 and not sorok:
            sorok = [s for s in self.k("GET", f"/api/feladatok/{fid}")[1]["sorok"] if s.startswith("TETEL")]
            time.sleep(0.05)
        self.assertTrue(sorok, self.k("GET", f"/api/feladatok/{fid}")[1])
        _, kor, sha1 = sorok[0].split()
        self.assertEqual(self.k("GET", f"/api/feladatok/{fid}")[1]["allapot"], "fut")
        c = self.repo.log(1)[0]
        self.assertEqual((c.sha, c.trailers["Mos-Feladat"], c.trailers["Mos-Tetel"]), (sha1, fid, "t1"))
        kod, v = self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": sha1})       # a feladat még fut
        self.assertEqual(kod, 200, v)
        self.assertEqual(self.a(), ALAP)
        self.assertFalse((self.v / "T01" / "a — kártyák 1.md").exists())
        self.assertEqual(self.var(fid)["allapot"], "kesz")
        self.assertEqual(self.a(), ALAP + "![[a — kártyák 2]]\n")
        kod, d = self.k("GET", f"/api/feladatok/{fid}/valtozasok")
        self.assertEqual([len(k["commitok"]) for k in d["korok"]], [2])                  # a vezérlő a kört látja
        # a kör visszavonása: az első tétel már vissza van vonva, így ütközik — a második tétel sha-ra megy
        sha2 = d["korok"][0]["commitok"][1]["sha"]
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": sha2})[0], 200)
        self.assertEqual(self.a(), ALAP)
        self.assertEqual(sorted(p.name for p in (self.v / "T01").iterdir()), ["a.md"])
        # az index a visszavonás után azonnal friss (nem a figyelőre vár): az új fájlok eltűntek belőle
        t0, fa = time.time(), None
        while time.time() - t0 < 5:
            fa = sorted(f["ut"] for f in self.k("GET", "/api/vault/fa")[1].get("fajlok", []))
            if fa == ["T01/a.md"]:
                break
            time.sleep(0.05)
        self.assertEqual(fa, ["T01/a.md"])


class GepiIndulasTest(_Szerver):
    """Megszakadt gépi írás naplója az indulás előtt: a core visszaállít, és az első WS-kapcsolat hírt kap róla."""

    def elokeszit(self):
        (self.v / "A.md").write_text("# A\n", encoding="utf-8")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        naplo = self.cfg.path("run") / gepi_iras.NAPLO
        (naplo / "eredeti").mkdir(parents=True)
        (naplo / "eredeti" / "0.bin").write_bytes(b"# A\n")
        (self.v / "A.md").write_bytes(b"# A\nfelbe\n")
        (self.v / "Uj").mkdir()
        (self.v / "Uj" / "uj.md").write_bytes(b"uj\n")
        (naplo / "terv.json").write_text(json.dumps({
            "verzio": 1, "kor": "KARTYA-20261003-101500", "tetel": "t1", "feladat": None, "fajlok": [
                {"ut": "A.md", "lemez": "A.md", "eredeti": "0.bin", "uj_fajl": False,
                 "uj_sha1": hashlib.sha1(b"# A\nfelbe\n").hexdigest(), "mappak": []},
                {"ut": "Uj/uj.md", "lemez": "Uj/uj.md", "eredeti": "1.bin", "uj_fajl": True,
                 "uj_sha1": hashlib.sha1(b"uj\nteljes\n").hexdigest(), "mappak": ["Uj"]}]}))
        (naplo / "eredeti" / "1.bin").write_bytes(b"uj\nteljes\n")          # az új fájl félig íródott meg

    @unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
    def test_indulas_visszaallit_es_szol(self):
        self.assertEqual((self.v / "A.md").read_bytes(), b"# A\n")
        self.assertFalse((self.v / "Uj").exists())
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())
        with ws_csatlakozik(self.port) as ws:
            hello = json.loads(ws.recv(timeout=5))
        self.assertTrue(any("gépi írás megszakadt" in u for u in hello["figyelmeztetesek"]), hello)


if __name__ == "__main__":
    unittest.main()
