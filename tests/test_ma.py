"""A „Ma” oldal összesítője (C15): a mai naptár, a következő dolgozat felkészülési jegyzettel, a mai és lejárt
feladatok, a napi jegyzet kivonata; az elérhetetlen forrás csak a saját szakaszát viszi el. Álvaulton és
ál-`pos.sqlite`-on (a valódi személyes adathoz a teszt nem nyúl)."""
import json
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from core import ma, naplo, vaultio
from core.index import feladatok
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

NAP = date(2026, 10, 2)
TZ = timezone(timedelta(hours=2))
MOST = datetime(2026, 10, 2, 9, 0, tzinfo=TZ)

DDL = """
CREATE TABLE forras_rekord (forras TEXT NOT NULL, forras_id TEXT NOT NULL, kezd TEXT, veg TEXT, tipus TEXT,
  payload TEXT NOT NULL, hash TEXT NOT NULL, importalva TEXT NOT NULL, import_futas INTEGER, torolve TEXT,
  PRIMARY KEY (forras, forras_id));
CREATE TABLE import_futas (id INTEGER PRIMARY KEY, forras TEXT NOT NULL, kezdes TEXT NOT NULL, vege TEXT, allapot TEXT,
  uj INTEGER DEFAULT 0, valtozott INTEGER DEFAULT 0, torolt INTEGER DEFAULT 0, osszes INTEGER DEFAULT 0, uzenet TEXT);
CREATE TABLE naptar (azon TEXT PRIMARY KEY, nev TEXT NOT NULL, forras TEXT, forras_tipus TEXT, tipus TEXT, szin TEXT,
  kategoria TEXT NOT NULL, kategoria_forras TEXT NOT NULL, elso_latva TEXT, utoljara_latva TEXT, eltunt TEXT, utod TEXT);
"""

NAPTARAK = [("HAT", "Deadlines & Exams", "#ff383c", "hatarido", None), ("ORA", "Órarend", "#8b5cf6", "orarend", None),
            ("UNN", "Ünnepnapok", "#999999", "kizart", None), ("TAN", "Studying", "#ff8d28", "tanulas", None),
            ("ELT", "Régi határidők", "#000000", "hatarido", "2026-09-01T00:00:00+02:00")]


def esemeny(azon, naptar, kezd, veg, cim, egesznap=False, hely="", torolve=None):
    p = {"azon": azon, "cim": cim, "egesznap": egesznap, "kezd": kezd, "veg": veg, "naptar": naptar, "nap": kezd[:10]}
    if hely:
        p["hely"] = hely
    return ("naptar", azon, kezd, veg, "esemeny", json.dumps(p, ensure_ascii=False), "h", "2026-09-27T22:00:00+02:00", 7, torolve)


ESEMENYEK = [
    esemeny("e1", "TAN", "2026-10-02T07:00:00+02:00", "2026-10-02T07:25:00+02:00", "Kutyasétáltatás"),
    esemeny("e2", "ORA", "2026-10-02T08:55:00+02:00", "2026-10-02T09:40:00+02:00", "Testnevelés", hely="T2"),
    esemeny("e3", "UNN", "2026-10-02T00:00:00+02:00", "2026-10-02T23:59:59+02:00", "Ünnep", True),
    esemeny("e4", "HAT", "2026-10-01T00:00:00+02:00", "2026-10-01T23:59:59+02:00", "Katona József: Bánk bán", True),
    esemeny("e5", "HAT", "2026-10-05T10:35:00+02:00", "2026-10-05T11:20:00+02:00", "Himnusz"),
    esemeny("e6", "HAT", "2026-10-06T10:00:00+02:00", "2026-10-06T10:45:00+02:00", "Német - Röpdolgozat"),
    esemeny("e7", "HAT", "2026-10-13T10:00:00+02:00", "2026-10-13T10:45:00+02:00", "Német - Röpdolgozat"),
    esemeny("e8", "HAT", "2026-10-20T10:00:00+02:00", "2026-10-20T10:45:00+02:00", "Német - Röpdolgozat"),
    esemeny("e9", "HAT", "2026-10-03T10:00:00+02:00", "2026-10-03T10:45:00+02:00", "Törölt dolgozat", torolve="2026-09-30"),
    esemeny("e10", "ELT", "2026-10-04T10:00:00+02:00", "2026-10-04T10:45:00+02:00", "Eltűnt naptár eseménye"),
    esemeny("e11", "TAN", "2026-10-01T00:00:00+02:00", "2026-10-04T00:00:00+02:00", "Háromnapos tábor", True),
    esemeny("e12", "TAN", "2026-10-01T00:00:00+02:00", "2026-10-02T00:00:00+02:00", "Tegnapi egész napos", True),
    esemeny("e13", "TAN", "2026-10-02T00:00:00+02:00", "2026-10-03T00:00:00+02:00", "Mai egész napos", True),
]

FAJLOK = {
    "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-05 - Irodalom.md": "# Irodalom\n",
    "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-06 - Német.md": "# Német\n",
    "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-06 - Matematika.md": "# Matematika\n",
    "X01 - Napló & To-Do/2026-10/Napló/2026-10-13 - Német.md": "nem dolgozatmappa\n",
    "Tennivalók.md": ("- [ ] ma esedékes 📅 2026-10-02\n- [x] kész 📅 2026-10-02\n- [ ] lejárt [due:: 2026-09-30]\n"
                      "- [ ] ütemezett ⏳ 2026-10-02\n- [ ] holnap 📅 2026-10-03\n- [ ] dátum nélkül\n"
                      "- [-] megszűnt 📅 2026-10-02\n- [ ] kész dátummal ✅ 2026-10-01 📅 2026-10-02\n"
                      "```\n- [ ] kódban 📅 2026-10-02\n```\n"),
}


class Alap(unittest.TestCase):
    pos = True

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        for rp, t in FAJLOK.items():
            ir(self.v, rp, t)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.app = SimpleNamespace(vault=vaultio.Vault(self.cfg), index=self.ix)
        self.szemelyes = self.cfg.path("szemelyes")
        if self.pos:
            self.pos_keszit()

    def pos_keszit(self):
        self.szemelyes.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.szemelyes / ma.POS_FAJL)
        c.executescript(DDL)
        c.executemany("INSERT INTO naptar VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(a, n, "iCloud", "caldav", "caldav", sz, k, "auto", None, None, e, None) for a, n, sz, k, e in NAPTARAK])
        c.executemany("INSERT INTO forras_rekord VALUES (?,?,?,?,?,?,?,?,?,?)", ESEMENYEK)
        c.execute("INSERT INTO import_futas(forras, kezdes, vege, allapot) VALUES ('naptar', ?, ?, 'engedelyezve')",
                  ("2026-10-02T06:00:00+02:00", "2026-10-02T06:00:02+02:00"))
        c.commit()
        c.close()


class NaptarTest(Alap):
    def test_a_mai_esemenyek_sorrendben(self):
        n = ma.naptar(self.app, NAP, MOST)
        self.assertEqual([e["cim"] for e in n["esemenyek"]],
                         ["Háromnapos tábor", "Mai egész napos", "Kutyasétáltatás", "Testnevelés"])

    def test_kizart_torolt_eltunt_es_a_kizaro_veg(self):
        cimek = {e["cim"] for e in ma.naptar(self.app, NAP, MOST)["esemenyek"]}
        for nincs in ("Ünnep", "Törölt dolgozat", "Eltűnt naptár eseménye", "Tegnapi egész napos", "Katona József: Bánk bán"):
            self.assertNotIn(nincs, cimek)

    def test_a_tobbnapos_esemeny_az_utolso_napjan_is_latszik(self):
        self.assertIn("Háromnapos tábor", [e["cim"] for e in ma.naptar(self.app, date(2026, 10, 3), MOST)["esemenyek"]])
        self.assertNotIn("Háromnapos tábor", [e["cim"] for e in ma.naptar(self.app, date(2026, 10, 4), MOST)["esemenyek"]])

    def test_az_esemeny_mezoi(self):
        e = [x for x in ma.naptar(self.app, NAP, MOST)["esemenyek"] if x["cim"] == "Testnevelés"][0]
        self.assertEqual((e["kezd_ora"], e["veg_ora"], e["hely"], e["egesznap"], e["kategoria"], e["szin"]),
                         ("08:55", "09:40", "T2", False, "orarend", "#8b5cf6"))
        egesz = [x for x in ma.naptar(self.app, NAP, MOST)["esemenyek"] if x["cim"] == "Mai egész napos"][0]
        self.assertEqual((egesz["kezd_ora"], egesz["egesznap"]), ("", True))

    def test_friss_es_regi_adat(self):
        self.assertFalse(ma.naptar(self.app, NAP, MOST)["regi"])
        n = ma.naptar(self.app, NAP, MOST + timedelta(hours=40))
        self.assertTrue(n["regi"])
        self.assertEqual(n["utolso_szinkron"], "2026-10-02T06:00:02+02:00")


class DolgozatTest(Alap):
    def test_az_elso_harom_hatarido(self):
        d = ma.dolgozatok(self.app, NAP, MOST)["lista"]
        self.assertEqual([x["cim"] for x in d], ["Himnusz", "Német - Röpdolgozat", "Német - Röpdolgozat"])
        self.assertEqual([x["nap"] for x in d], ["2026-10-05", "2026-10-06", "2026-10-13"])
        self.assertEqual([x["napok"] for x in d], [3, 4, 11])

    def test_a_mai_hatarido_is_szamit_a_multbeli_nem(self):
        d = ma.dolgozatok(self.app, date(2026, 10, 1), MOST)["lista"]
        self.assertEqual(d[0]["cim"], "Katona József: Bánk bán")
        self.assertEqual((d[0]["napok"], d[0]["egesznap"], d[0]["ora"]), (0, True, ""))
        self.assertNotEqual(ma.dolgozatok(self.app, NAP, MOST)["lista"][0]["cim"], "Katona József: Bánk bán")

    def test_felkeszulesi_jegyzet_kotese(self):
        d = ma.dolgozatok(self.app, NAP, MOST)["lista"]
        base = "X01 - Napló & To-Do/2026-10/Dolgozatok/"
        self.assertEqual((d[0]["jegyzet"], d[0]["kotes"]), (base + "2026-10-05 - Irodalom.md", "valoszinu"))   # aznap egyetlen
        self.assertEqual((d[1]["jegyzet"], d[1]["kotes"]), (base + "2026-10-06 - Német.md", "biztos"))        # a címben a tantárgy
        self.assertEqual((d[2]["jegyzet"], d[2]["kotes"]), (None, None))     # a „Napló” mappa jegyzete nem felkészülési

    def test_a_ma_oldal_a_c28_kozos_kotesevel_koti_az_athelyezett_dolgozatot_is(self):
        """C28b: a Ma oldal és a dolgozat-oldal ugyanazt a kötést használja (`felkeszultseg.kotes`) — így a négy fokozatból az
        „áthelyezve?” is megjelenik (korábban a Ma csak biztos/valószínű kötést ismert)."""
        ir(self.v, "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-11 - Német.md", "# Német\n")
        self.ix.frissit(["X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-11 - Német.md"])
        d = ma.dolgozatok(self.app, NAP, MOST)["lista"]
        self.assertEqual((d[2]["nap"], d[2]["jegyzet"], d[2]["kotes"]),
                         ("2026-10-13", "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-11 - Német.md", "athelyezve"))
        self.assertEqual(d[1]["kotes"], "biztos", "az azonos napi, azonos tantárgyú jegyzet előbb köt")

    def test_a_kotes_hibaja_nem_viszi_el_a_dolgozat_kartyat(self):
        from unittest import mock
        with mock.patch.object(ma, "_kotesek", side_effect=RuntimeError("hiba")):
            d = ma.dolgozatok(self.app, NAP, MOST)["lista"]
        self.assertEqual(len(d), 3)
        self.assertEqual((d[0]["jegyzet"], d[0]["kotes"]), (None, None))

    def test_regi_adat_jelzo(self):
        self.assertTrue(ma.dolgozatok(self.app, NAP, MOST + timedelta(days=3))["regi"])


class FeladatTest(Alap):
    def test_mai_es_lejart(self):
        f = feladatok.esedekes(self.ix, "2026-10-02")
        self.assertEqual([x["szoveg"] for x in f["ma"]], ["ma esedékes", "ütemezett"])
        self.assertEqual([x["szoveg"] for x in f["lejart"]], ["lejárt"])
        self.assertEqual((f["osszes_ma"], f["osszes_lejart"]), (2, 1))

    def test_sor_ut_es_datumok(self):
        t = feladatok.esedekes(self.ix, "2026-10-02")["ma"][0]
        self.assertEqual((t["ut"], t["sor"], t["hatarido"]), ("Tennivalók.md", 1, "2026-10-02"))
        self.assertEqual(feladatok.esedekes(self.ix, "2026-10-02")["ma"][1]["utemezve"], "2026-10-02")

    def test_masik_nap(self):
        f = feladatok.esedekes(self.ix, "2026-10-03")
        self.assertEqual([x["szoveg"] for x in f["ma"]], ["holnap"])
        self.assertEqual({x["szoveg"] for x in f["lejart"]}, {"lejárt", "ma esedékes"})   # a kész és a megszűnt nem lejárt

    def test_a_kodban_allo_feladat_nem_szamit(self):
        szovegek = [x["szoveg"] for k in ("ma", "lejart") for x in feladatok.esedekes(self.ix, "2026-10-02")[k]]
        self.assertNotIn("kódban", szovegek)


class OsszesitTest(Alap):
    def test_teljes_valasz(self):
        r = ma.osszesit(self.app, "2026-10-02")
        self.assertEqual((r["datum"], r["felirat"], r["ma"]), ("2026-10-02", "2026. október 2., péntek", NAP == date.today()))
        self.assertEqual(r["napi"], {"ut": naplo.napi_ut(self.cfg, NAP), "letezik": False, "kivonat": ""})
        self.assertEqual(len(r["naptar"]["esemenyek"]), 4)
        self.assertEqual(len(r["dolgozatok"]["lista"]), 3)
        self.assertEqual(r["feladatok"]["osszes_ma"], 2)
        self.assertEqual(r["kartyak"], {"allapot": "kesz", "esedekes": 0, "uj": 0, "holnap": 0, "osszes": 0})   # C23b: adatbázis nélkül nullák

    def test_ma_jelzo(self):
        self.assertTrue(ma.osszesit(self.app)["ma"])

    def test_hibas_datum(self):
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError):
            ma.osszesit(self.app, "holnap")

    def test_asszisztens_szakasz_nelkul_kikapcsolt(self):
        """C30a: az `asszisztens` szakasz a `getattr`-os app-en át jön; nélküle (régebbi app, teszt) a kapcsoló ki, higiénia nincs."""
        self.assertEqual(ma.osszesit(self.app, "2026-10-02")["asszisztens"], {"kapcsolo": False, "higienia": None})

    def test_asszisztens_szakasz_a_homlokzatbol_es_hibatureo(self):
        class Homlokzat:
            def __init__(self, hiba=None):
                self.hiba = hiba

            def ma_szakasz(self):
                if self.hiba:
                    raise self.hiba
                return {"kapcsolo": True, "higienia": {"kesz": True, "ossz": 7, "uj": 2}}
        self.app.asszisztens = Homlokzat()
        r = ma.osszesit(self.app, "2026-10-02")
        self.assertEqual(r["asszisztens"], {"kapcsolo": True, "higienia": {"kesz": True, "ossz": 7, "uj": 2}})
        self.app.asszisztens = Homlokzat(RuntimeError("elromlott"))
        r = ma.osszesit(self.app, "2026-10-02")
        self.assertEqual(r["asszisztens"], {"hiba": "elromlott"})                    # a hibás szakasz a többit nem viszi el
        self.assertEqual(r["feladatok"]["osszes_ma"], 2)

    def test_a_napi_jegyzet_kivonata(self):
        ir(self.v, naplo.napi_ut(self.cfg, NAP), "---\nTags:\n  - Napló\nStatus:\n---\n\n# Napló\n\nmostanában egyre\njobban fáradok.\n## Alcím\n")
        n = ma.osszesit(self.app, "2026-10-02")["napi"]
        self.assertEqual((n["letezik"], n["kivonat"]), (True, "mostanában egyre jobban fáradok."))

    def test_a_kivonat_levagva(self):
        k = ma._kivonat("# Cím\n\n" + "szó " * 200)
        self.assertLessEqual(len(k), ma.KIVONAT_HOSSZ + 1)
        self.assertTrue(k.endswith("…"))
        self.assertEqual(ma._kivonat("# Csak cím\n"), "")


class HianyzoAdatTest(Alap):
    pos = False

    def test_pos_nelkul_csak_a_naptar_es_a_dolgozat_hibas(self):
        r = ma.osszesit(self.app, "2026-10-02")
        self.assertIn("hiba", r["naptar"])
        self.assertIn("hiba", r["dolgozatok"])
        self.assertIn("még nincs naptáradat", r["naptar"]["hiba"])      # a felületre megy: fájlnév nélkül (C32)
        self.assertNotIn("pos.sqlite", r["naptar"]["hiba"])
        self.assertNotIn("hiba", r["napi"])
        self.assertEqual(r["feladatok"]["osszes_ma"], 2)               # a többi szakasz él
        self.assertEqual(r["kartyak"]["allapot"], "kesz")

    def test_serult_adatbazis(self):
        self.szemelyes.mkdir(parents=True, exist_ok=True)
        (self.szemelyes / ma.POS_FAJL).write_bytes(b"ez nem sqlite")
        r = ma.osszesit(self.app, "2026-10-02")
        self.assertIn("hiba", r["naptar"])
        self.assertEqual(r["feladatok"]["osszes_ma"], 2)

    def test_a_pos_nem_modosul(self):
        self.pos_keszit()
        ut = self.szemelyes / ma.POS_FAJL
        elotte = ut.read_bytes()
        ma.osszesit(self.app, "2026-10-02")
        self.assertEqual(ut.read_bytes(), elotte)


if __name__ == "__main__":
    unittest.main()
