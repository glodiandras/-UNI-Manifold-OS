"""A tracker a futó core-on (C27): végpontok és hibakódok, a kapcsoló, a gépi írás és a visszavonás horga funkciónként,
és hogy a tracker hibája nem akasztja meg a gépi írást."""
import json
import sqlite3
import unittest

from core import snapshot, szemelyes_db
from tests import csak_darwin
from tests.test_core_api import _Szerver

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
ALAP = FM + "# A\n\n## Gyakorlás\nelső\n"
BESZ = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "gépi"}


class TrackerApiTest(_Szerver):
    def elokeszit(self):
        (self.v / "T01").mkdir()
        (self.v / "T01" / "a.md").write_text(ALAP, encoding="utf-8")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})

    def ir(self, kor="KARTYA-20261003-101500", tetel="t1", forras="mos-kartya", **tobbi):
        return self.k("POST", "/api/gepi-iras", {"kor": kor, "tetel": tetel, "forras": forras, "modell": None, "muveletek": [BESZ], **tobbi})

    def gepi(self) -> dict:
        return {g["funkcio"]: g for g in self.k("GET", "/api/tracker/hasznalat")[1]["gepi"]}

    def test_koteg_statisztika_hasznalat(self):
        kod, r = self.k("POST", "/api/tracker/esemenyek", {
            "aktiv": [{"ut": "M01 - Matek/a.md", "mp": 42}], "karakter": [{"ut": "M01 - Matek/a.md", "beszurt": 9, "torolt": 1}],
            "parancsok": [{"id": "manifold.most", "forras": "paletta"}],
            "kesleltetes": {"gepeles": {"4": [3, 14.0]}}})
        self.assertEqual((kod, r), (200, {"fogadva": True}))
        s = self.k("GET", "/api/tracker/statisztika")[1]
        self.assertEqual((s["osszes"]["aktiv_mp"], s["osszes"]["beszurt"], s["kapcsolo"]), (42, 9, True))
        self.assertEqual(s["tantargyak"][0]["tantargy"], "Mathematics")
        self.assertEqual(len(s["napok"]), 7)
        h = self.k("GET", "/api/tracker/hasznalat")[1]
        self.assertEqual(h["parancsok"][0]["parancs"], "manifold.most")
        self.assertEqual(h["kesleltetes"]["gepeles"]["p95_ms"], 16.0)
        het = self.k("GET", "/api/tracker/statisztika?bontas=het&tol=2026-01-05&ig=2026-01-18")[1]
        self.assertEqual(len(het["napok"]), 2)

    def test_a_http_kliens_nem_hamisithat_cpp_probat(self):
        """A3-24: a `POST /api/tracker/esemenyek` a `cpp_proba`-t elveti (a core maga írja), a `cpp_tipp`-et fogadja."""
        kod, r = self.k("POST", "/api/tracker/esemenyek", {"esemenyek": [
            {"tipus": "cpp_proba", "ut": "D08/a.md", "adat": {"atment": True, "tesztek": 3, "atment_db": 3, "fordit_ok": True}},
            {"tipus": "cpp_tipp", "ut": "D08/a.md", "adat": {"szint": 2}}]})
        self.assertEqual((kod, r["fogadva"], r["elvetve"]), (200, True, 1))
        c = sqlite3.connect(f"file:{szemelyes_db.ut(self.cfg)}?mode=ro", uri=True)
        try:
            self.assertEqual([x[0] for x in c.execute("SELECT tipus FROM tr_esemeny")], ["cpp_tipp"])
        finally:
            c.close()

    def test_hibak_es_fejlec(self):
        self.assertEqual(self.k("POST", "/api/tracker/esemenyek", {}, {"X-Manifold": "0"})[0], 403)
        self.assertEqual(self.k("POST", "/api/tracker/esemenyek", [1])[0], 400)       # csak a nem-objektum törzs 400
        self.assertEqual(self.k("GET", "/api/tracker/statisztika?tol=ma")[0], 400)
        self.assertEqual(self.k("GET", "/api/tracker/statisztika?bontas=ev")[0], 400)
        self.assertEqual(self.k("POST", "/api/tracker/torles", {"mit": "semmi"})[0], 400)

    def test_a_rossz_elem_nem_viszi_el_a_koteget(self):
        """T029: a túlméretes/hibás elem 200-at kap `elvetve` jelzéssel; a jó elemek beíródnak (a kliens nem kap 400-at,
        amit örökké újraküldene)."""
        kod, r = self.k("POST", "/api/tracker/esemenyek", {
            "aktiv": [{"ut": "x" * 5000, "mp": 9}, {"ut": "M01 - Matek/a.md", "mp": 42}],
            "parancsok": [{"id": "rossz"}, {"id": "manifold.most", "forras": "paletta"}],
            "esemenyek": [{"tipus": "kviz_eredmeny", "adat": {"x": "a" * 5000}}]})
        self.assertEqual(kod, 200)
        self.assertEqual((r["fogadva"], r["elvetve"], len(r["okok"])), (True, 3, 3))
        self.assertEqual(self.k("GET", "/api/tracker/statisztika")[1]["osszes"]["aktiv_mp"], 42)
        self.assertEqual(self.k("GET", "/api/tracker/hasznalat")[1]["parancsok"][0]["parancs"], "manifold.most")

    def test_kapcsolo_ki_nem_gyujt(self):
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"tracker": False})[0], 200)
        self.assertEqual(self.k("POST", "/api/tracker/esemenyek", {"aktiv": [{"ut": "M/a.md", "mp": 5}]})[1], {"fogadva": False})
        self.assertEqual(self.ir()[0], 200)
        self.assertFalse((self.cfg.path("szemelyes") / "pos.sqlite").exists())
        s = self.k("GET", "/api/tracker/statisztika")[1]
        self.assertEqual((s["kapcsolo"], s["osszes"]["aktiv_mp"]), (False, 0))
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"tracker": True})[0], 200)
        self.assertTrue(self.k("POST", "/api/tracker/esemenyek", {"aktiv": [{"ut": "M/a.md", "mp": 5}]})[1]["fogadva"])

    @csak_darwin("APFS-klón (`cp -c`) próbakör")
    def test_gepi_iras_es_visszavonas_funkciónként(self):
        self.assertEqual(self.ir()[0], 200)
        self.assertEqual(self.ir()[1]["ismetles"], True)                   # az újraküldés nem számolódik kétszer
        g = self.gepi()["mos-kartya"]
        self.assertEqual((g["iras"], g["visszavonas"], g["elfogadas"]), (1, 0, 1.0))
        self.assertEqual(self.ir(kor="KARTYA-20261003-101501-proba", proba=True)[0], 200)
        self.assertEqual(self.gepi()["mos-kartya"]["iras"], 1)             # a próba nem számít
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "KARTYA-20261003-101500"})[0], 200)
        g = self.gepi()["mos-kartya"]
        self.assertEqual((g["iras"], g["visszavonas"], g["elfogadas"]), (1, 1, 0.0))

    def test_visszavonas_sha_alapjan_es_kezi_commit_nem_szamit(self):
        kod, r = self.ir(kor="KVIZ-20261003-101500", forras="mos-kviz")
        self.assertEqual(kod, 200)
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": r["sha"]})[0], 200)
        self.assertEqual(self.gepi()["mos-kviz"]["visszavonas"], 1)
        sha_kezi = self.repo.log(5)[-1].sha                                # az „alap” kézi commit
        self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": sha_kezi})
        self.assertEqual(set(self.gepi()), {"mos-kviz"})

    def test_a_tracker_hibaja_nem_akasztja_a_gepi_irast(self):
        szemelyes = self.cfg.path("szemelyes")
        szemelyes.parent.mkdir(parents=True, exist_ok=True)
        szemelyes.write_text("nem mappa", encoding="utf-8")               # a tracker nem tud mappát létrehozni
        kod, r = self.ir()
        self.assertEqual(kod, 200, r)
        self.assertEqual((self.v / "T01" / "a.md").read_text(encoding="utf-8"), ALAP + "gépi\n")
        kod, r = self.k("POST", "/api/tracker/esemenyek", {"aktiv": [{"ut": "M/a.md", "mp": 5}]})
        # F3 (2026-10-14): a DB-hiba 503 (a kliens újraküldi a köteget), nem 200 `fogadva: false` (az elveszne)
        self.assertEqual((kod, r["fogadva"], r.get("db_hiba")), (503, False, True))
        self.assertNotIn(str(self.cfg.path("szemelyes")), r["hiba"])

    def test_export_es_torles(self):
        self.k("POST", "/api/tracker/esemenyek", {"parancsok": [{"id": "manifold.most"}]})
        kod, r = self.k("POST", "/api/tracker/export", {})
        self.assertEqual(kod, 200)
        self.assertEqual(r["tartalom"]["hasznalat"]["parancsok"][0]["parancs"], "manifold.most")
        self.assertNotIn("tevekenyseg", r["tartalom"])                      # T111: alapból csak a használati adat
        kod, t = self.k("POST", "/api/tracker/torles", {"mit": "minden"})
        self.assertEqual((kod, t), (200, {"torolt": 1, "tisztitva": True}))
        self.assertEqual(self.k("GET", "/api/tracker/hasznalat")[1]["parancsok"], [])
        c = sqlite3.connect(self.cfg.path("szemelyes") / "pos.sqlite")
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        finally:
            c.close()
        json.dumps(r)


if __name__ == "__main__":
    unittest.main()
