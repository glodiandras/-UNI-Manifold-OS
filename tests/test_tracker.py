"""A tracker (C27): a pos.sqlite 2-es migrációja, a fogadás és az aggregáció, a kapcsoló, a statisztika és a
használat, az export és a törlés — ideiglenes álgyökéren, a valódi `var/`-hoz soha nem nyúl."""
import json
import random
import sqlite3
import unittest
from datetime import datetime, timedelta

from core import ma, szemelyes_db, tracker, vezerlo
from core.utvonalak import HttpError
from tests.helpers import alg_core, tmpdir
from tests.test_ma import DDL, ESEMENYEK, NAPTARAK
from tests.test_szemelyes_db import szemelyes_cfg

NAP = "2026-10-03"
MIKOR = datetime(2026, 10, 3, 10, 0)
MATEK = "M01 - Matek/Függvények.md"
FIZIKA = "F01 - Fizika/Mozgás.md"
NAPLO = "X01 - Napló & To-Do/2026-10/Napló/2026-10-03.md"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ido = MIKOR
        self.tr = tracker.Tracker(self.cfg, mikor=lambda: self.ido)

    def pos(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.tr.ut())
        c.row_factory = sqlite3.Row
        self.addCleanup(c.close)
        return c

    def fogad(self, **d):
        return self.tr.fogad(d)

    def _klon_v1(self) -> None:
        """A klónozott legacy-adatbázis: 1-es migráció, naptáradattal, `user_version = 1`."""
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        c.executescript(DDL)
        c.executemany("INSERT INTO naptar (azon, nev, szin, kategoria, kategoria_forras, eltunt) VALUES (?,?,?,?,'auto',?)",
                      [(a, n, s, k, e) for a, n, s, k, e in NAPTARAK])
        c.executemany("INSERT INTO forras_rekord VALUES (?,?,?,?,?,?,?,?,?,?)", ESEMENYEK)
        c.execute("CREATE INDEX forras_rekord_kezd ON forras_rekord (forras, kezd)")
        c.execute("PRAGMA user_version = 1")
        c.commit()
        c.close()


class DbHibaTest(Alap):
    """F3 (2026-10-14): a DB-írás hibája a felület kötegének 503 (a kliens újraküldi), a core saját gyűjtőinek nem kivétel."""

    def setUp(self):
        super().setUp()
        szemelyes = self.cfg.path("szemelyes")
        szemelyes.parent.mkdir(parents=True, exist_ok=True)
        szemelyes.write_text("nem mappa", encoding="utf-8")         # az adatbázis nem hozható létre

    def test_kliens_koteg_503(self):
        with self.assertRaises(HttpError) as cm:
            self.tr.fogad({"aktiv": [{"ut": MATEK, "mp": 5}]}, kliens=True)
        self.assertEqual((cm.exception.code, cm.exception.data.get("db_hiba"), cm.exception.data.get("fogadva")), (503, True, False))

    def test_core_gyujto_nem_kap_kivetelt(self):
        self.assertEqual(self.tr.esemeny("integralt_video", MATEK, {"video_s": 60, "jegyzet_db": 1, "kotes": "nincs"}),
                         {"fogadva": False, "hiba": "a tracker adatbázisa nem írható"})
        self.assertEqual(self.tr.fogad({"aktiv": [{"ut": MATEK, "mp": 5}]}),
                         {"fogadva": False, "hiba": "a tracker adatbázisa nem írható"})


class MigracioTest(Alap):
    def test_olvasas_nem_hoz_letre_fajlt(self):
        self.assertFalse(self.tr.ut().exists())
        self.assertEqual(self.tr.statisztika()["osszes"]["aktiv_mp"], 0)
        self.assertEqual(self.tr.hasznalat()["parancsok"], [])
        self.assertEqual(self.tr.torles("minden"), {"torolt": 0})
        self.assertFalse(self.tr.ut().exists())

    def test_kikapcsolva_nem_ir_es_nem_hoz_letre_fajlt(self):
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertEqual(self.fogad(aktiv=[{"ut": MATEK, "mp": 5}]), {"fogadva": False})
        self.tr.gepi_iras("mos-kartya")
        self.tr.visszavonas(["mos-kartya"])
        self.tr.szunet_minta("memoria", 0, 0)
        self.tr.szunet_minta("memoria", 2, 30)
        self.assertFalse(self.tr.ut().exists())

    def test_friss_fajl_2_es_verzio_es_az_1_es_tablak_is_megvannak(self):
        self.assertTrue(self.fogad(aktiv=[{"ut": MATEK, "mp": 5}])["fogadva"])
        c = self.pos()
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        tablak = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"forras_rekord", "naptar", "tr_aktiv", "has_parancs", "has_kesleltetes"} <= tablak)

    def test_migracio_az_1_esbol_megorzi_a_sorokat_es_a_ma_oldal_olvas(self):
        self._klon_v1()
        elotte = self.pos().execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0]
        self.assertGreater(elotte, 0)
        self.assertTrue(self.fogad(aktiv=[{"ut": MATEK, "mp": 5}])["fogadva"])
        c = self.pos()
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0], elotte)
        # a `mode=ro` olvasó (Ma oldal) a WAL-os fájlt is olvassa
        from contextlib import closing
        with closing(ma._pos(self.cfg)) as r:
            self.assertEqual(r.execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0], elotte)

    def test_ures_koteg_az_1_es_klont_nem_migralja(self):
        """T112: az üres köteg a klónozott legacy-adatbázist sem lépteti 2-es sémára (a fájl bájtjai változatlanok)."""
        self._klon_v1()
        elotte = self.tr.ut().read_bytes()
        for d in ({}, {"aktiv": []}, {"parancsok": [], "esemenyek": []}):
            self.assertEqual(self.tr.fogad(d), {"fogadva": True})
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(self.tr.ut().read_bytes(), elotte)

    def test_olvasas_nem_ir_nem_migral_es_csak_kisero_fajlt_hagy(self):
        """T112/30(a) pontosítása: az olvasás (`mode=ro`) tartalmat nem ír, nem migrál, fájlt nem hoz létre; a WAL-mód
        `-shm`/`-wal` kísérőfájlját az SQLite az olvasáskor is létrehozhatja — a fő fájl bájtjai ettől nem változnak."""
        for van_2es in (False, True):
            with self.subTest(van_2es=van_2es), tmpdir() as t:
                cfg, _, _ = alg_core(t)
                tr = tracker.Tracker(cfg, mikor=lambda: MIKOR)
                if van_2es:
                    tr.fogad({"aktiv": [{"ut": MATEK, "mp": 5}]})
                else:
                    self.tr = tr
                    self._klon_v1()
                fo = tr.ut()
                elotte, verzio = fo.read_bytes(), sqlite3.connect(fo).execute("PRAGMA user_version").fetchone()[0]
                tr.statisztika(NAP, NAP)
                tr.hasznalat()
                from contextlib import closing
                with closing(ma._pos(cfg)) as r:
                    r.execute("SELECT COUNT(*) FROM forras_rekord").fetchone()
                self.assertEqual(fo.read_bytes(), elotte)
                self.assertEqual(sqlite3.connect(fo).execute("PRAGMA user_version").fetchone()[0], verzio)
                self.assertEqual({p.name for p in fo.parent.iterdir()} - {"pos.sqlite-shm", "pos.sqlite-wal"}, {"pos.sqlite"})

    def test_ujabb_semat_nem_bantja(self):
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        c.execute("PRAGMA user_version = 9")
        c.commit()
        c.close()
        r = self.fogad(aktiv=[{"ut": MATEK, "mp": 5}])
        self.assertFalse(r["fogadva"])
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 9)

    def test_ujabb_semaban_a_sajat_tablakkal_ir(self):
        """T007: egy újabb `user_version` (a séma csak bővül) nem dobatja el az eseményeket, ha a tracker táblái megvannak."""
        self.assertTrue(self.fogad(aktiv=[{"ut": MATEK, "mp": 5}])["fogadva"])
        c = self.pos()
        c.execute("PRAGMA user_version = 9")
        c.commit()
        r = self.fogad(aktiv=[{"ut": MATEK, "mp": 7}], parancsok=[{"id": "manifold.most", "forras": "paletta"}])
        self.assertTrue(r["fogadva"], r)
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 9)
        self.assertEqual(self.pos().execute("SELECT sum(mp) FROM tr_aktiv").fetchone()[0], 12)

    def test_a_torles_olvasojanak_hibaja_503_nem_kezeletlen_kivetel(self):
        """T108: a törlés olvasója is a `try` alatt áll — a nem olvasható `pos.sqlite` 503, nem 500-as kivétel."""
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        self.tr.ut().write_bytes(b"ez nem sqlite adatbazis " * 100)
        with self.assertRaises(HttpError) as cm:
            self.tr.torles("minden")
        self.assertEqual(cm.exception.code, 503)

    def test_az_1_es_tablak_torleskor_ervintetlenek(self):
        self._klon_v1()
        self.fogad(aktiv=[{"ut": MATEK, "mp": 5}], parancsok=[{"id": "manifold.most", "forras": "paletta"}])
        elotte = self.pos().execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0]
        self.assertGreater(self.tr.torles("minden")["torolt"], 0)
        c = self.pos()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM forras_rekord").fetchone()[0], elotte)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM tr_aktiv").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM has_parancs").fetchone()[0], 0)


class KodoltUtTest(unittest.TestCase):
    def test_olvasas_es_torles_specialis_karakteres_uton_is_a_valodi_adatbazison_megy(self):
        """T108 (2. audit): `#`, `?`, `%` a `{szemelyes}` útjában — az olvasó a valódi fájlt látja, a törlés tényleg töröl
        (ma csendben `{torolt: 0}`), és a szülőmappában nem keletkezik kóbor fájl."""
        for nev in ("a#b", "a?b", "a%20b", "100%"):
            with self.subTest(nev=nev), tmpdir() as tmp:
                cfg, mappa = szemelyes_cfg(tmp, nev)
                tr = tracker.Tracker(cfg, mikor=lambda: MIKOR)
                self.assertTrue(tr.fogad({"aktiv": [{"ut": MATEK, "mp": 5}]})["fogadva"])
                self.assertEqual(tr.statisztika(NAP, NAP)["osszes"]["aktiv_mp"], 5)
                self.assertEqual(tr.torles("tevekenyseg"), {"torolt": 2, "tisztitva": True})        # tr_aktiv + tr_aktiv_ora (C30b)
                self.assertEqual(tr.statisztika(NAP, NAP)["osszes"]["aktiv_mp"], 0)
                self.assertEqual([p.name for p in mappa.parent.iterdir()], [nev])


class NapszakTest(Alap):
    """C30b (K205 (a)): az aktív idő napszak-bontása (`tr_aktiv_ora`: nap × óra × tantárgy) — útvonal és szöveg nélkül, a
    Tracker-kapcsoló alatt, a törlés és az export hatókörében."""

    def ora_sorok(self):
        return [tuple(r) for r in self.pos().execute("SELECT nap, ora, tantargy, mp FROM tr_aktiv_ora ORDER BY nap, ora, tantargy")]

    def test_a_kotegek_a_mostani_orara_esnek_tantargyanként(self):
        self.ido = datetime(2026, 10, 3, 19, 5)
        self.fogad(aktiv=[{"ut": MATEK, "mp": 30}, {"ut": FIZIKA, "mp": 20}])
        self.ido = datetime(2026, 10, 3, 20, 10)
        self.fogad(aktiv=[{"ut": MATEK, "mp": 15}])
        self.ido = datetime(2026, 10, 3, 20, 40)
        self.fogad(aktiv=[{"ut": MATEK, "mp": 10}])
        self.assertEqual(self.ora_sorok(), [(NAP, 19, "Mathematics", 30), (NAP, 19, "Physics", 20), (NAP, 20, "Mathematics", 25)])

    def test_az_ejfelen_atnyulo_kotegek_a_nap_utolso_orajara_esnek(self):
        self.ido = datetime(2026, 10, 3, 0, 0, 20)
        self.fogad(aktiv=[{"nap": "2026-10-02", "ut": MATEK, "mp": 10}, {"ut": MATEK, "mp": 5}])
        self.assertEqual(self.ora_sorok(), [("2026-10-02", 23, "Mathematics", 10), (NAP, 0, "Mathematics", 5)])

    def test_nincs_ut_es_szoveg_oszlop_es_az_osszeg_egyezik_a_tr_aktiv_ral(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 30}, {"ut": FIZIKA, "mp": 20}, {"ut": "Z/Szabad.md", "mp": 7}])
        self.assertEqual([r[1] for r in self.pos().execute("PRAGMA table_info(tr_aktiv_ora)")], ["nap", "ora", "tantargy", "mp"])
        self.assertEqual(sum(r[3] for r in self.ora_sorok()), self.pos().execute("SELECT SUM(mp) FROM tr_aktiv").fetchone()[0])
        self.assertNotIn("Szabad", json.dumps(self.ora_sorok()))
        self.assertNotIn("Függvények", json.dumps(self.ora_sorok()))

    def test_a_napi_plafon_a_napszak_bontasra_is_igaz(self):
        for _ in range(30):
            self.fogad(aktiv=[{"ut": MATEK, "mp": tracker.KOTEG_AKTIV_MAX_MP}])
        osszeg = sum(r[3] for r in self.ora_sorok())
        self.assertEqual(osszeg, tracker.NAP_MAX_MP)
        self.assertEqual(osszeg, self.pos().execute("SELECT SUM(mp) FROM tr_aktiv").fetchone()[0])

    def test_kikapcsolva_nem_ir_es_nem_hoz_letre_fajlt(self):
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.fogad(aktiv=[{"ut": MATEK, "mp": 30}])
        self.assertFalse(self.tr.ut().exists())
        self.assertEqual(self.tr.napszakok(), [])
        self.assertFalse(self.tr.ut().exists())

    def test_az_export_es_a_torles_hatokore(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 30}], parancsok=[{"id": "manifold.most"}])
        self.assertEqual(self.tr.napszakok(NAP, NAP), [{"nap": NAP, "ora": 10, "tantargy": "Mathematics", "mp": 30}])
        self.assertEqual(self.tr.napszakok("2026-10-01", "2026-10-02"), [])
        self.assertNotIn("napszakok", self.tr.export()["tartalom"])                  # alapból csak a használati adat
        self.assertIn("napszakok", self.tr.export(tevekenyseg=True)["tartalom"])
        self.tr.torles("hasznalat")
        self.assertEqual(len(self.ora_sorok()), 1)                                    # a használat törlése a tevékenységhez nem nyúl
        self.tr.torles("tevekenyseg")
        self.assertEqual(self.ora_sorok(), [])

    def test_4_es_fajlbol_migral_es_az_adat_megmarad_az_olvasas_nem_migral(self):
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        for sql in szemelyes_db.MIGRACIOK[:4]:
            c.executescript(sql)
        c.execute("PRAGMA user_version = 4")
        c.execute("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES ('2026-10-01', 'a.md', 'Mathematics', 60)")
        c.commit()
        c.close()
        self.assertEqual(self.tr.napszakok(), [])                                     # még nincs 5-ös séma: üres, és nem migrál
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 4)
        self.fogad(aktiv=[{"ut": MATEK, "mp": 5}])
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        self.assertEqual(self.pos().execute("SELECT mp FROM tr_aktiv WHERE nap = '2026-10-01'").fetchone()[0], 60)
        self.assertEqual(len(self.ora_sorok()), 1)


class FogadasTest(Alap):
    def test_aktiv_ido_osszeadodik_tantargyra_es_jegyzetre(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 30}, {"ut": FIZIKA, "mp": 20}])
        self.fogad(aktiv=[{"ut": MATEK, "mp": 15}])
        s = self.tr.statisztika(NAP, NAP)
        self.assertEqual(s["osszes"]["aktiv_mp"], 65)
        t = {x["tantargy"]: x["aktiv_mp"] for x in s["tantargyak"]}
        self.assertEqual(t, {"Mathematics": 45, "Physics": 20})
        self.assertEqual(s["jegyzetek"][0], {"ut": MATEK, "tantargy": "Mathematics", "aktiv_mp": 45})

    def test_ismeretlen_betu_egyeb_tantargy(self):
        self.fogad(aktiv=[{"ut": NAPLO, "mp": 10}, {"ut": "gyoker.md", "mp": 4}])
        t = {x["tantargy"] for x in self.tr.statisztika(NAP, NAP)["tantargyak"]}
        self.assertEqual(t, {tracker.EGYEB})

    def test_nem_jegyzet_fulek_aktiv_ideje_is_beiratik(self):
        """38. döntés (T074): a PDF, a videó, a canvas, a base és a gráf (álkulcs: `(gráf)`) ideje is számít; a tantárgy a
        legfelső mappa betűje, ismeretlen: „Egyéb”."""
        r = self.fogad(aktiv=[{"ut": "Tx/11 - Történelem.pdf", "mp": 40}, {"ut": "ATTCHMNTS/Videos/A Nyugat.mp4", "mp": 90},
                              {"ut": "M03/térkép.canvas", "mp": 12}, {"ut": "(gráf)", "mp": 25}])
        self.assertEqual(r.get("elvetve", 0), 0, r)
        s = self.tr.statisztika(NAP, NAP)
        self.assertEqual(s["osszes"]["aktiv_mp"], 167)
        ut = {j["ut"]: j["tantargy"] for j in s["jegyzetek"]}
        self.assertEqual(ut["(gráf)"], tracker.EGYEB)
        self.assertEqual(ut["Tx/11 - Történelem.pdf"], "History")

    def test_napi_plafon_nem_tobb_a_napnal(self):
        for _ in range(30):
            self.fogad(aktiv=[{"ut": MATEK, "mp": 3600}])
        self.assertEqual(self.tr.statisztika(NAP, NAP)["osszes"]["aktiv_mp"], tracker.NAP_MAX_MP)

    def test_karakter_es_az_elozo_nap_jelolese(self):
        self.fogad(karakter=[{"ut": MATEK, "beszurt": 120, "torolt": 7},
                             {"nap": "2026-10-02", "ut": MATEK, "beszurt": 10, "torolt": 0},
                             {"nap": "2020-01-01", "ut": MATEK, "beszurt": 1, "torolt": 0}])     # a régi nap „mára” esik
        s = self.tr.statisztika("2026-10-02", NAP)
        self.assertEqual([(n["nap"], n["beszurt"], n["torolt"]) for n in s["napok"]],
                         [("2026-10-02", 10, 0), (NAP, 121, 7)])

    def test_nem_objektum_torzs_400_es_semmi_nem_irodik(self):
        for d in ([], "x", None, 5):
            with self.subTest(d=d), self.assertRaises(HttpError) as cm:
                self.tr.fogad(d)
            self.assertEqual(cm.exception.code, 400)
        self.assertFalse(self.tr.ut().exists())

    def _jo_elemek(self) -> dict:
        return {"aktiv": [{"ut": FIZIKA, "mp": 11}], "karakter": [{"ut": FIZIKA, "beszurt": 5, "torolt": 2}],
                "parancsok": [{"id": "jo.parancs", "forras": "paletta", "db": 3}],
                "kesleltetes": {"gepeles": {"3": [4, 9.0]}},
                "esemenyek": [{"tipus": "kartya_valasz", "ut": FIZIKA, "adat": {"jegy": 3}}]}

    def _jo_ellenorzes(self, extra_aktiv: int = 0) -> None:
        c = self.pos()
        self.assertEqual(c.execute("SELECT COALESCE(SUM(mp), 0) FROM tr_aktiv").fetchone()[0], 11 + extra_aktiv)
        self.assertEqual(tuple(c.execute("SELECT beszurt, torolt FROM tr_karakter").fetchone()), (5, 2))
        self.assertEqual(c.execute("SELECT db FROM has_parancs WHERE parancs = 'jo.parancs'").fetchone()[0], 3)
        self.assertEqual(c.execute("SELECT db FROM has_kesleltetes WHERE vedro = 3").fetchone()[0], 4)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM tr_esemeny WHERE tipus = 'kartya_valasz'").fetchone()[0], 1)

    def test_az_ervenytelen_elem_kimarad_a_tobbi_beirodik(self):
        """T029 (2. audit): egyetlen rossz (túlméretes, hibás) elem nem viheti el a köteg többi részét — a kliens a 400-as
        köteget örökké újraküldte, és a munkamenet tracker-adata elveszett. Elemenként: az érvénytelen kimarad."""
        rossz = [
            ("aktiv", {"ut": MATEK, "mp": -1}), ("aktiv", {"ut": "", "mp": 1}), ("aktiv", {"ut": "x" * 5000, "mp": 1}),
            ("aktiv", {"ut": MATEK, "mp": True}), ("aktiv", {"ut": MATEK, "mp": "a"}), ("aktiv", "x"), ("aktiv", {"ut": MATEK}),
            ("aktiv", {"ut": "a\x00b.md", "mp": 1}),
            ("karakter", {"ut": MATEK, "beszurt": "a", "torolt": 0}), ("karakter", {"ut": MATEK, "beszurt": -1, "torolt": 0}),
            ("parancsok", {"id": "nincspont"}), ("parancsok", {"id": "A.b"}), ("parancsok", {"id": "a.b", "forras": "ismeretlen"}),
            ("parancsok", {"id": "a.b", "db": 0}), ("parancsok", {"id": 5}),
            ("esemenyek", {"tipus": "ismeretlen"}), ("esemenyek", {"tipus": "kviz_eredmeny", "adat": "x"}),
            ("esemenyek", {"tipus": "kviz_eredmeny", "adat": {"x": "a" * 5000}}), ("esemenyek", {"tipus": "kviz_eredmeny", "ut": ""}),
        ]
        for szakasz, elem in rossz:
            with self.subTest(elem=str(elem)[:50]), tmpdir() as t:
                cfg, _, _ = alg_core(t)
                tr = tracker.Tracker(cfg, mikor=lambda: MIKOR)
                d = self._jo_elemek()
                d[szakasz] = [elem] + d[szakasz]
                v = tr.fogad(d)
                self.assertTrue(v["fogadva"], v)
                self.assertEqual(v["elvetve"], 1, v)
                self.assertEqual(len(v["okok"]), 1)
                self.tr, self.cfg = tr, cfg
                self._jo_ellenorzes()

    def test_ervenytelen_kesleltetes_resz_kimarad_a_tobbi_beirodik(self):
        jo = {"3": [4, 9.0]}
        rossz = [{"ismeretlen": {"1": [1, 1.0]}, "gepeles": jo}, {"gepeles": {"99": [1, 1.0], **jo}},
                 {"gepeles": {"x": [1, 1.0], **jo}}, {"gepeles": {"1": [1, -5], **jo}}, {"gepeles": {"1": "x", **jo}},
                 {"gepeles": {"1": [1], **jo}}, {"gepeles": {"1": [1, "a"], **jo}}, {"mentes": "x", "gepeles": jo}]
        for k in rossz:
            with self.subTest(k=str(k)[:60]), tmpdir() as t:
                cfg, _, _ = alg_core(t)
                tr = tracker.Tracker(cfg, mikor=lambda: MIKOR)
                d = self._jo_elemek()
                d["kesleltetes"] = k
                v = tr.fogad(d)
                self.assertTrue(v["fogadva"], v)
                self.assertEqual(v["elvetve"], 1, v)
                self.tr, self.cfg = tr, cfg
                self._jo_ellenorzes()
        v = self.tr.fogad({**self._jo_elemek(), "kesleltetes": "x"})                 # nem objektum: csak az maradt ki
        self.assertEqual((v["fogadva"], v["elvetve"]), (True, 1))

    def test_tulcsordulo_szam_vagva_a_plafonra(self):
        v = self.fogad(aktiv=[{"ut": MATEK, "mp": 99999}], karakter=[{"ut": MATEK, "beszurt": 10 ** 9, "torolt": 0}],
                       parancsok=[{"id": "a.b", "db": 10 ** 9}])
        self.assertEqual(v, {"fogadva": True})                  # vágás, nem kihagyás: nincs `elvetve`
        c = self.pos()
        self.assertEqual(c.execute("SELECT mp FROM tr_aktiv").fetchone()[0], tracker.KOTEG_AKTIV_MAX_MP)
        self.assertEqual(c.execute("SELECT beszurt FROM tr_karakter").fetchone()[0], tracker.KOTEG_KARAKTER_MAX)
        self.assertEqual(c.execute("SELECT db FROM has_parancs").fetchone()[0], tracker.SZAM_MAX)

    def test_a_tul_hosszu_lista_elso_eleme_beirodik_a_tobbi_kimarad(self):
        v = self.fogad(aktiv=[{"ut": MATEK, "mp": 1}] * 3000)
        self.assertEqual((v["fogadva"], v["elvetve"]), (True, 1000))
        self.assertEqual(self.pos().execute("SELECT mp FROM tr_aktiv").fetchone()[0], tracker.KOTEG_ELEM_MAX)

    def test_nem_lista_szakasz_kimarad_a_tobbi_beirodik(self):
        d = {**self._jo_elemek(), "aktiv": "x"}
        v = self.tr.fogad(d)
        self.assertEqual((v["fogadva"], v["elvetve"]), (True, 1))
        c = self.pos()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM tr_aktiv").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM has_parancs").fetchone()[0], 1)

    def test_az_okok_kulonbozoek_legfeljebb_otig_es_a_tiszta_koteg_valasza_valtozatlan(self):
        v = self.fogad(aktiv=[{"ut": MATEK, "mp": -i} for i in range(1, 9)] + [{"ut": MATEK, "mp": 4}])
        self.assertEqual((v["elvetve"], len(v["okok"])), (8, 1))                   # ugyanaz az ok egyszer
        v = self.fogad(aktiv=[{"ut": "", "mp": 1}, {"ut": MATEK, "mp": "a"}], karakter=[{"ut": MATEK, "beszurt": "a", "torolt": 0}],
                       parancsok=[{"id": "x"}, {"id": "a.b", "forras": "z"}, {"id": "a.b", "db": 0}], esemenyek=[{"tipus": "z"}])
        self.assertEqual((v["fogadva"], v["elvetve"], len(v["okok"])), (True, 7, 5))
        self.assertEqual(self.fogad(aktiv=[{"ut": MATEK, "mp": 4}]), {"fogadva": True})
        self.assertNotIn("elvetve", self.fogad(aktiv=[{"ut": MATEK, "mp": 4}]))

    def test_ures_koteg_nem_ir_nem_hoz_letre_fajlt_es_nem_migral(self):
        """T112 (2. audit): az üres köteg ne nyissa az adatbázist (fájlt hozna létre, és a 1-es sémát migrálná)."""
        for d in ({}, {"aktiv": []}, {"kesleltetes": {}}, {"aktiv": [], "karakter": [], "parancsok": [], "esemenyek": []},
                  {"aktiv": [{"ut": MATEK, "mp": 0}]}, {"kesleltetes": {"gepeles": {"3": [0, 1.0]}}}):
            with self.subTest(d=str(d)[:50]):
                self.assertEqual(self.tr.fogad(d), {"fogadva": True})
                self.assertFalse(self.tr.ut().exists())

    def test_parancsok_forrasonkent(self):
        self.fogad(parancsok=[{"id": "manifold.most", "forras": "paletta", "db": 2}, {"id": "manifold.most", "forras": "billentyu"},
                              {"id": "szerkeszto.mentes", "forras": "billentyu", "db": 5}])
        self.fogad(parancsok=[{"id": "manifold.most", "forras": "paletta"}])
        p = self.tr.hasznalat()["parancsok"]
        self.assertEqual([(x["parancs"], x["db"]) for x in p], [("szerkeszto.mentes", 5), ("manifold.most", 4)])
        self.assertEqual(p[1]["forrasok"], {"paletta": 3, "billentyu": 1})

    def test_esemenyek_a_gyujtok_szamara(self):
        self.fogad(esemenyek=[{"tipus": "kartya_valasz", "ut": MATEK, "adat": {"jegy": 3}},
                              {"tipus": "kviz_eredmeny", "adat": {"jo": 7, "ossz": 10}},
                              {"tipus": "integralt_video"}, {"tipus": "integralt_fuzet", "ut": FIZIKA}])
        s = self.tr.statisztika(NAP, NAP)
        n = s["napok"][0]
        self.assertEqual((n["kartya"], n["kviz"], n["integralt"]), (1, 1, 2))
        self.assertEqual(s["elerheto"], {"kartya": True, "kviz": True, "integralt": True, "terv": s["elerheto"]["terv"]})

    def test_nincs_gyujto_jelzes(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 1}])
        e = self.tr.statisztika(NAP, NAP)["elerheto"]
        self.assertEqual((e["kartya"], e["kviz"], e["integralt"]), (False, False, False))


class CppEsemenyTest(Alap):
    """C36a: a C++ feladat eseményei (`cpp_proba`, `cpp_tipp`) — nincs migráció (a `tr_esemeny` általános), de az `adat`
    fehérlistás: a használat-mérés itt sem tárol kódot vagy szöveget (TERV 5.14), az útvonal a tevékenységnaplóé."""
    FELADAT = "D08 - Algoritmizálás és programozás/Összeg.md"

    def proba(self, **adat):
        d = {"atment": True, "tesztek": 3, "atment_db": 3, "fordit_ok": True, "mod": "gyors", "ms": 1500}
        d.update(adat)
        return {"tipus": "cpp_proba", "ut": self.FELADAT, "adat": d}

    def test_a_proba_beirodik_a_tantargyaval_migracio_nelkul(self):
        v0 = len(tracker.MIGRACIOK)
        self.fogad(esemenyek=[self.proba()])
        r = self.pos().execute("SELECT tipus, tantargy, ut, adat FROM tr_esemeny").fetchone()
        self.assertEqual((r["tipus"], r["tantargy"], r["ut"]), ("cpp_proba", "Informatics", self.FELADAT))
        self.assertEqual(json.loads(r["adat"])["atment_db"], 3)
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], v0)

    def test_a_tipp_esemeny_a_c36b_helye(self):
        self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": 2}}])
        self.assertEqual(self.pos().execute("SELECT COUNT(*) FROM tr_esemeny WHERE tipus = 'cpp_tipp'").fetchone()[0], 1)

    def test_kod_vagy_szoveg_nem_irhato_az_adatba(self):
        for adat in ({"kod": "int main() {}"}, {"atment": True, "forras": "x"}, {"atment": "igen"}, {"tesztek": "3"},
                     {"mod": "valami"}, {"ms": -1}, {"tesztek": True}, {"atment_db": 1.5}, {"fordit_ok": 1}):
            with self.subTest(adat=adat):
                r = self.fogad(esemenyek=[{"tipus": "cpp_proba", "ut": self.FELADAT, "adat": adat}])
                self.assertEqual(r["elvetve"], 1)
        self.assertFalse(self.tr.ut().exists())                  # csak érvénytelen elem: fájl sem jön létre
        r = self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": 1, "szoveg": "irány"}}])
        self.assertEqual(r["elvetve"], 1)
        self.assertFalse(self.tr.ut().exists())

    def test_az_atment_db_nem_lehet_tobb_a_teszteknel(self):
        """A3-24: a konzisztencia-ellenőrzés — nem létező teszt nem mehet át."""
        r = self.fogad(esemenyek=[self.proba(tesztek=3, atment_db=4)])
        self.assertEqual(r["elvetve"], 1)
        self.assertFalse(self.tr.ut().exists())
        self.assertNotIn("elvetve", self.fogad(esemenyek=[self.proba(tesztek=3, atment_db=3)]))
        self.assertNotIn("elvetve", self.fogad(esemenyek=[self.proba(tesztek=0, atment_db=0, atment=False, fordit_ok=False)]))

    def test_a_tipp_szintje_reális_plafonu(self):
        self.assertNotIn("elvetve", self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": tracker.CPP_TIPP_SZINT_MAX}}]))
        r = self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": tracker.CPP_TIPP_SZINT_MAX + 1}}])
        self.assertEqual(r["elvetve"], 1)
        self.assertEqual(self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": 10_000_000}}])["elvetve"], 1)

    def test_a_kliens_nem_kuldhet_cpp_probat(self):
        """A3-24: a `cpp_proba` csak core-forrásból (a `cpp_utvonal` hívja közvetlenül); a kliens-útról (`kliens=True`) kimarad."""
        r = self.tr.fogad({"esemenyek": [self.proba(), {"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": 1}}]}, kliens=True)
        self.assertEqual(r["elvetve"], 1)
        self.assertIn("core", r["okok"][0])
        self.assertEqual([x[0] for x in self.tarolt_tipusok()], ["cpp_tipp"])

    def tarolt_tipusok(self):
        return [(r["tipus"],) for r in self.pos().execute("SELECT tipus FROM tr_esemeny ORDER BY id")]

    def test_a_proba_adat_nelkul_is_ervenytelen_a_tipp_szint_nelkul_is(self):
        self.assertEqual(self.fogad(esemenyek=[{"tipus": "cpp_proba", "ut": self.FELADAT}])["elvetve"], 1)
        self.assertEqual(self.fogad(esemenyek=[{"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {}}])["elvetve"], 1)

    def test_a_statisztika_szamolja_a_probakat_es_az_atmenteket(self):
        self.fogad(esemenyek=[self.proba(), self.proba(atment=False, atment_db=1),
                              {"tipus": "cpp_tipp", "ut": self.FELADAT, "adat": {"szint": 1}}])
        s = self.tr.statisztika(NAP, NAP)
        n = s["napok"][0]
        self.assertEqual((n["cpp_proba"], n["cpp_atment"], n["cpp_tipp"]), (2, 1, 1))
        self.assertEqual((s["osszes"]["cpp_proba"], s["osszes"]["cpp_atment"], s["osszes"]["cpp_tipp"]), (2, 1, 1))

    def test_a_heti_bontas_is_osszegzi(self):
        self.fogad(esemenyek=[self.proba()])
        s = self.tr.statisztika(NAP, NAP, bontas="het")
        self.assertEqual(s["napok"][0]["cpp_proba"], 1)

    def test_ismeretlen_esemenytipus_a_db_ben_nem_dobja_el_a_statisztikat(self):
        """Egy újabb app írhat ismeretlen típust (L56: a séma csak bővül): a statisztika nem dőlhet el `KeyError`-ral."""
        self.fogad(aktiv=[{"ut": MATEK, "mp": 7}])
        c = sqlite3.connect(self.tr.ut())
        c.execute("INSERT INTO tr_esemeny (mikor, nap, tipus, tantargy, ut, adat) VALUES (?,?,?,?,?,?)",
                  (MIKOR.isoformat(), NAP, "valami_uj", "Egyéb", None, None))
        c.commit()
        c.close()
        s = self.tr.statisztika(NAP, NAP)
        self.assertEqual(s["osszes"]["aktiv_mp"], 7)

    def test_a_cpp_esemeny_nem_hatja_a_tobbi_gyujto_jelzeset(self):
        self.fogad(esemenyek=[self.proba()])
        e = self.tr.statisztika(NAP, NAP)["elerheto"]
        self.assertEqual((e["kartya"], e["kviz"], e["integralt"]), (False, False, False))

    def test_kikapcsolt_trackerben_nem_irodik(self):
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertEqual(self.tr.fogad({"esemenyek": [self.proba()]}), {"fogadva": False})
        self.assertFalse(self.tr.ut().exists())

    def test_az_export_nem_viszi_a_feladat_utjat_sem_a_kodot(self):
        self.fogad(esemenyek=[self.proba()])
        for tevekenyseg in (False, True):
            szoveg = json.dumps(self.tr.export(NAP, NAP, tevekenyseg=tevekenyseg), ensure_ascii=False)
            self.assertNotIn("Összeg", szoveg)
            self.assertNotIn("int main", szoveg)
        self.assertEqual(self.tr.export(NAP, NAP, tevekenyseg=True)["tartalom"]["tevekenyseg"]["osszes"]["cpp_proba"], 1)



class TorlesTest(Alap):
    """T110 (2. audit): a törlés után a törölt utak nem maradhatnak a pos.sqlite szabad lapjain és a WAL-ban."""
    JELOLO = "TITKOS-JEGYZET-UT"

    def nyers(self) -> bytes:
        ki = b""
        for kiterjesztes in ("", "-wal"):
            f = self.tr.ut().with_name(self.tr.ut().name + kiterjesztes)
            if f.exists():
                ki += f.read_bytes()
        return ki

    def toltes(self) -> str:
        ut = f"M01 - Matek/{self.JELOLO}.md"
        self.fogad(aktiv=[{"ut": ut, "mp": 30}], karakter=[{"ut": ut, "beszurt": 5, "torolt": 1}],
                   esemenyek=[{"tipus": "kviz_eredmeny", "ut": ut}], parancsok=[{"id": "manifold.most", "forras": "paletta"}])
        self.assertTrue(self.JELOLO.encode() in self.nyers(), "a jelölő előtte a fájlban van")
        return ut

    def test_a_torolt_utak_nem_maradnak_a_fajlban(self):
        self.toltes()
        r = self.tr.torles("tevekenyseg")
        self.assertFalse(self.JELOLO.encode() in self.nyers(), "a törölt út a fájlban maradt")
        self.assertEqual((r["torolt"], r["tisztitva"]), (4, True))        # tr_aktiv, tr_aktiv_ora, tr_karakter, tr_esemeny
        c = self.pos()
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(c.execute("SELECT COUNT(*) FROM has_parancs").fetchone()[0], 1)          # a másik rész érintetlen

    def test_a_korabbi_nem_biztonsagos_torles_maradeka_is_eltunik(self):
        """A VACUUM a korábban, `secure_delete` nélkül felszabadított lapokat is újraírja."""
        self.toltes()
        c = self.pos()
        c.execute("DELETE FROM tr_aktiv")
        c.execute("DELETE FROM tr_karakter")
        c.execute("DELETE FROM tr_esemeny")
        c.commit()
        c.close()
        self.assertTrue(self.JELOLO.encode() in self.nyers(), "a sima DELETE a szabad lapokon hagyja")
        r = self.tr.torles("hasznalat")
        self.assertFalse(self.JELOLO.encode() in self.nyers(), "a törölt út a fájlban maradt")
        self.assertEqual(r["tisztitva"], True)

    def test_az_1_es_tablak_sorai_a_tisztitas_utan_valtozatlanok(self):
        self._klon_v1()
        sorok = lambda: [tuple(r) for r in self.pos().execute("SELECT * FROM forras_rekord ORDER BY forras, forras_id")]
        elotte = sorok()
        naptar = [tuple(r) for r in self.pos().execute("SELECT * FROM naptar ORDER BY azon")]
        self.assertGreater(len(elotte), 0)
        self.toltes()
        self.tr.torles("minden")
        self.assertEqual(sorok(), elotte)
        self.assertEqual([tuple(r) for r in self.pos().execute("SELECT * FROM naptar ORDER BY azon")], naptar)

    def test_a_tisztitas_hibaja_nem_hiusitja_meg_a_torlest(self):
        from unittest import mock
        self.toltes()
        with mock.patch.object(szemelyes_db, "tisztit", side_effect=sqlite3.OperationalError("database is locked")):
            r = self.tr.torles("tevekenyseg")
        self.assertEqual((r["torolt"], r["tisztitva"]), (4, False))
        self.assertEqual(self.pos().execute("SELECT COUNT(*) FROM tr_aktiv").fetchone()[0], 0)


class KesleltetesTest(Alap):
    def test_vedor_index_hatarai(self):
        self.assertEqual(tracker.vedor_index(0.5), 0)
        self.assertEqual(tracker.vedor_index(1), 0)
        self.assertEqual(tracker.vedor_index(1.01), 1)
        self.assertEqual(tracker.vedor_index(5000), len(tracker.VEDROK_MS) - 1)
        self.assertEqual(tracker.vedor_index(5001), len(tracker.VEDROK_MS))

    def test_p50_p95_max_napok_kozott_osszevonva(self):
        i = tracker.vedor_index
        # 100 mintából 90 ≤ 8 ms, 8 ≤ 50 ms, 2 ≤ 300 ms
        self.fogad(kesleltetes={"gepeles": {str(i(8)): [90, 7.5], str(i(50)): [8, 44.0], str(i(300)): [2, 260.0]}})
        self.ido += timedelta(days=1)
        self.fogad(kesleltetes={"gepeles": {str(i(8)): [10, 6.0]}})
        k = self.tr.hasznalat("2026-10-03", "2026-10-04")["kesleltetes"]["gepeles"]
        self.assertEqual(k["db"], 110)
        self.assertEqual((k["p50_ms"], k["max_ms"]), (8.0, 260.0))
        self.assertEqual(k["p95_ms"], 50.0)                     # a 105. minta (95%) már az 50 ms-os vödörben van: 100 ≤ 8 ms
        self.assertGreaterEqual(k["p95_ms"], k["p50_ms"])
        self.assertEqual(sum(k["vedrok"]), 110)
        self.assertIsNone(self.tr.hasznalat()["kesleltetes"]["mentes"]["p95_ms"])

    def test_tulcsordulo_vodor_a_megfigyelt_maximumot_adja(self):
        self.fogad(kesleltetes={"mentes": {str(len(tracker.VEDROK_MS)): [5, 9100.0]}})
        k = self.tr.hasznalat()["kesleltetes"]["mentes"]
        self.assertEqual((k["p95_ms"], k["max_ms"]), (9100.0, 9100.0))

    def test_szazalek_ures(self):
        self.assertIsNone(tracker.szazalek({}, 0.95))


class GepiEsSzunetTest(Alap):
    def test_gepi_iras_es_visszavonas_funkciónként_proba_es_kezi_nelkul(self):
        for _ in range(4):
            self.tr.gepi_iras("mos-kartya")
        self.tr.gepi_iras("mos-kviz")
        for f in ("kezi", "pult-szerkeszto", None, "", "pult", "kezi-x", "pult-x", "kartya"):        # T135: csak a `mos-…` gépi funkció
            self.tr.gepi_iras(f)
        self.tr.visszavonas(["mos-kartya", "kezi", "pult-elozmeny", None, "pult", "kezi-x"])
        g = {x["funkcio"]: x for x in self.tr.hasznalat()["gepi"]}
        self.assertEqual(set(g), {"mos-kartya", "mos-kviz"})
        self.assertEqual((g["mos-kartya"]["iras"], g["mos-kartya"]["visszavonas"], g["mos-kartya"]["elfogadas"]), (4, 1, 0.75))
        self.assertEqual(g["mos-kviz"]["elfogadas"], 1.0)

    def test_elfogadas_nem_lehet_negativ(self):
        self.tr.visszavonas(["mos-x1"])
        self.tr.visszavonas(["mos-x1"])
        self.tr.gepi_iras("mos-x1")
        g = self.tr.hasznalat()["gepi"][0]
        self.assertEqual(g["elfogadas"], 0.0)

    def test_szunet_novekmeny_es_worker_ujrainditas(self):
        self.tr.szunet_minta("memoria", 0, 0)           # alapvonal
        self.tr.szunet_minta("memoria", 0, 0)
        self.tr.szunet_minta("memoria", 2, 45)
        self.tr.szunet_minta("memoria", 3, 50)
        self.tr.szunet_minta("memoria", 0, 0)           # a worker újraindult: új alapvonal, nincs negatív
        self.tr.szunet_minta("memoria", 1, 12)
        self.tr.szunet_minta("hutes", 4, None)          # első minta: alapvonal
        self.tr.szunet_minta("hutes", 5, None)
        self.tr.szunet_minta("ismeretlen", 1, 1)
        self.tr.szunet_minta("memoria", None, None)
        sz = self.tr.hasznalat()["szunetek"]
        self.assertEqual(sz["memoria"], {"db": 4, "mp": 62})
        self.assertEqual(sz["hutes"], {"db": 1, "mp": 0})


class StatisztikaTest(Alap):
    def test_hetek_hetfotol_es_tartomany_hibak(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 60}])                     # 2026-10-03 szombat
        self.ido += timedelta(days=2)                                   # 2026-10-05 hétfő
        self.fogad(aktiv=[{"ut": MATEK, "mp": 100}])
        s = self.tr.statisztika("2026-09-28", "2026-10-11", "het")
        self.assertEqual([(n["nap"], n["aktiv_mp"]) for n in s["napok"]], [("2026-09-28", 60), ("2026-10-05", 100)])
        for tol, ig, b in (("x", None, "nap"), ("2026-10-05", "2026-10-01", "nap"), ("2020-01-01", NAP, "nap"),
                           (None, None, "ev")):
            with self.assertRaises(HttpError):
                self.tr.statisztika(tol, ig, b)

    def test_naptar_terv_a_legacy_importbol(self):
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        c.executescript(DDL)
        c.executemany("INSERT INTO naptar (azon, nev, szin, kategoria, kategoria_forras, eltunt) VALUES (?,?,?,?,'auto',?)",
                      [(a, n, s, k, e) for a, n, s, k, e in NAPTARAK])
        c.executemany("INSERT INTO forras_rekord VALUES (?,?,?,?,?,?,?,?,?,?)", ESEMENYEK)
        c.execute("PRAGMA user_version = 1")
        c.commit()
        c.close()
        s = self.tr.statisztika("2026-10-01", "2026-10-06")
        terv = {n["nap"]: n["terv_mp"] for n in s["napok"]}
        # csak a „tanulás” kategória: 10-02 a 25 perces séta (TAN); a testnevelés (órarend), a határidő (HAT),
        # az egész napos és a kizárt kihagyva
        self.assertEqual(terv["2026-10-02"], 25 * 60)
        self.assertEqual(terv["2026-10-05"], 0)
        self.assertEqual(terv["2026-10-01"], 0)
        self.assertTrue(s["elerheto"]["terv"])

    def test_a_tr_naptar_blokk_elonyt_elvez_es_torles_utan_a_legacy_lekerdezes_marad(self):
        """C29: a naptár-szinkron által töltött `tr_naptar_blokk` a tervezett idő forrása; üresen a régi út."""
        self.test_naptar_terv_a_legacy_importbol()
        self.fogad(aktiv=[{"ut": MATEK, "mp": 1}])                     # 2-es (és 3-as) migráció
        c = sqlite3.connect(self.tr.ut())
        c.execute("INSERT INTO tr_naptar_blokk (azon, nap, kezd, veg, kategoria, tantargy, forras) VALUES "
                  "('b1','2026-10-03','2026-10-03T17:00:00+02:00','2026-10-03T18:30:00+02:00','tanulas','Matematika','naptar')")
        c.commit()
        c.close()
        terv = {n["nap"]: n["terv_mp"] for n in self.tr.statisztika("2026-10-01", "2026-10-06")["napok"]}
        self.assertEqual((terv["2026-10-03"], terv["2026-10-02"]), (90 * 60, 0))     # a tábla nyer, a régi forrás nem számít
        self.tr.torles("tevekenyseg")
        terv = {n["nap"]: n["terv_mp"] for n in self.tr.statisztika("2026-10-01", "2026-10-06")["napok"]}
        self.assertEqual((terv["2026-10-03"], terv["2026-10-02"]), (0, 25 * 60))     # üres tábla: a legacy lekérdezés

    def test_naptar_nelkul_a_terv_nem_elerheto(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 1}])             # a pos.sqlite-ban van 1-es séma, de nincs naptáradat
        s = self.tr.statisztika(NAP, NAP)
        self.assertEqual(s["napok"][0]["terv_mp"], 0)

    def test_az_export_alapbol_csak_a_hasznalati_adat_utvonal_nelkul(self):
        """T111 (2. audit): az alap export a használati adat; a jegyzetutas tevékenységnapló csak kérésre kerül bele —
        sem a visszaadott tartalomba, sem a fájlba (egyetlen jegyzetút sem)."""
        self.fogad(aktiv=[{"ut": MATEK, "mp": 60}], karakter=[{"ut": MATEK, "beszurt": 4, "torolt": 0}],
                   esemenyek=[{"tipus": "kviz_eredmeny", "ut": MATEK}], parancsok=[{"id": "manifold.most"}])
        for e in (self.tr.export(), self.tr.export(tevekenyseg=False)):
            self.assertTrue(e["ut"].endswith("export/hasznalat-2026-10-03.json"), e["ut"])
            self.assertNotIn("tevekenyseg", e["tartalom"])
            with open(e["ut"], encoding="utf-8") as f:
                szoveg = f.read()
            self.assertNotIn("Matek", szoveg)
            self.assertNotIn(".md", szoveg)
            self.assertNotIn("tevekenyseg", json.loads(szoveg))
            self.assertEqual(json.loads(szoveg)["hasznalat"]["parancsok"][0]["parancs"], "manifold.most")

    def test_a_tevekenysegnaplos_export_masik_fajlba_ir_es_nem_keveredik_az_utvonalmentessel(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 60}], parancsok=[{"id": "manifold.most"}])
        alap = self.tr.export()
        teljes = self.tr.export(tevekenyseg=True)
        self.assertNotEqual(alap["ut"], teljes["ut"])
        self.assertTrue(teljes["ut"].endswith("export/hasznalat-tevekenyseggel-2026-10-03.json"), teljes["ut"])
        with open(alap["ut"], encoding="utf-8") as f:
            self.assertNotIn("Matek", f.read())                         # a későbbi teljes export nem írta felül
        with open(teljes["ut"], encoding="utf-8") as f:
            self.assertIn(MATEK, f.read())

    def test_export_es_torles(self):
        self.fogad(aktiv=[{"ut": MATEK, "mp": 60}], parancsok=[{"id": "manifold.most"}])
        e = self.tr.export(tevekenyseg=True)
        self.assertTrue(e["ut"].endswith("export/hasznalat-tevekenyseggel-2026-10-03.json"))
        with open(e["ut"], encoding="utf-8") as f:
            fajl = json.load(f)
        self.assertEqual(fajl["hasznalat"]["parancsok"][0]["parancs"], "manifold.most")
        self.assertEqual(fajl["tevekenyseg"]["osszes"]["aktiv_mp"], 60)
        self.assertEqual(fajl["napszakok"], [{"nap": NAP, "ora": MIKOR.hour, "tantargy": "Mathematics", "mp": 60}])      # C30b
        self.assertNotIn(MATEK, json.dumps(fajl["napszakok"]))          # a napszak-bontás sem tartalmaz útvonalat
        self.assertNotIn(MATEK, json.dumps(fajl["hasznalat"]))          # a használati mérés nem tartalmaz útvonalat
        self.assertEqual(self.tr.torles("hasznalat")["torolt"], 1)
        self.assertEqual(self.tr.hasznalat()["parancsok"], [])
        self.assertEqual(self.tr.statisztika(NAP, NAP)["osszes"]["aktiv_mp"], 60)
        self.assertEqual(self.tr.torles("tevekenyseg")["torolt"], 2)         # tr_aktiv + tr_aktiv_ora (C30b)
        with self.assertRaises(HttpError):
            self.tr.torles("semmi")

    def test_egy_nap_valos_hasznalat_hihetoen_aggregalodik(self):
        """Egy 8 órás munkanap szintetikus, de valószerű menete az API-n át: 30 s-os kötegek, szünetekkel, három
        tantárgy, parancsok, mentések, gépi írások visszavonással. Invariánsok: nem több aktív idő az eltelt időnél,
        a tantárgyak összege a napi összeg, p95 ≥ p50, az elfogadás [0, 1]."""
        rnd = random.Random(27)
        jegyzetek = [MATEK, FIZIKA, "I01 - Irodalom/Bánk bán.md"]
        percek, aktiv_mp, karakter = 8 * 60, 0, 0
        for kotes in range(percek * 2):                                  # 30 s-os kötegek
            if 180 <= kotes < 210 or 600 <= kotes < 660:                 # kávészünet, ebéd: nincs bevitel
                continue
            mp = rnd.choice([0, 0, 5, 12, 20, 30])
            j = jegyzetek[(kotes // 90) % 3]
            self.fogad(aktiv=[{"ut": j, "mp": mp}] if mp else [], karakter=[{"ut": j, "beszurt": mp * 3, "torolt": mp // 4}]
                       if mp else [], parancsok=[{"id": rnd.choice(["manifold.most", "szerkeszto.mentes", "fajl.megnyit"]),
                                                  "forras": rnd.choice(["billentyu", "paletta"])}] if mp > 10 else [],
                       kesleltetes={"gepeles": {str(tracker.vedor_index(rnd.choice([3, 6, 12, 25]))): [mp, 25.0]},
                                    "mentes": {str(tracker.vedor_index(rnd.choice([20, 40, 90]))): [1, 90.0]}} if mp else {})
            aktiv_mp += mp
            karakter += mp * 3
        for i in range(40):
            self.tr.gepi_iras("mos-kartya" if i % 2 else "mos-osszefoglalo")
        self.tr.visszavonas(["mos-kartya"] * 3)
        self.tr.szunet_minta("memoria", 0, 0)
        self.tr.szunet_minta("memoria", 3, 95)
        s, h = self.tr.statisztika(NAP, NAP), self.tr.hasznalat(NAP, NAP)
        self.assertEqual(s["osszes"]["aktiv_mp"], aktiv_mp)
        self.assertLessEqual(s["osszes"]["aktiv_mp"], percek * 60)
        self.assertLessEqual(s["osszes"]["aktiv_mp"], tracker.NAP_MAX_MP)
        self.assertEqual(sum(t["aktiv_mp"] for t in s["tantargyak"]), s["osszes"]["aktiv_mp"])
        self.assertEqual(s["osszes"]["beszurt"], karakter)
        self.assertEqual({t["tantargy"] for t in s["tantargyak"]}, {"Mathematics", "Physics", "Literature"})
        for fajta in ("gepeles", "mentes"):
            k = h["kesleltetes"][fajta]
            self.assertGreater(k["db"], 0)
            self.assertGreaterEqual(k["p95_ms"], k["p50_ms"])
            self.assertGreaterEqual(k["max_ms"], 0)
        for g in h["gepi"]:
            self.assertTrue(0 <= g["elfogadas"] <= 1)
        self.assertEqual(h["szunetek"]["memoria"], {"db": 3, "mp": 95})
        self.assertGreater(len(h["parancsok"]), 0)


class AdatSemaTest(Alap):
    """T143 (C20a): a `tr_esemeny.adat` eseménytípusonkénti fehérlistás sémája — a jegyzettartalom és a szabad szöveg nem
    kerülhet az adatbázisba; az ismeretlen kulcs kiesik, a rossz érték az elemet dobja el."""

    def tarolt(self) -> list[tuple]:
        return [(r["tipus"], r["adat"]) for r in self.pos().execute("SELECT tipus, adat FROM tr_esemeny ORDER BY id")]

    def test_a_fehereslista_kulcsai_megmaradnak(self):
        v = self.fogad(esemenyek=[
            {"tipus": "kartya_valasz", "ut": MATEK, "adat": {"jegy": 3, "ms": 4200, "kartya_id": "c-7f3a9e21"}},
            {"tipus": "kviz_eredmeny", "adat": {"jo": 7, "ossz": 10, "ms": 90_000}},
            {"tipus": "integralt_video", "ut": MATEK, "adat": {"video_s": 322, "jegyzet_db": 2, "kotes": "valoszinu"}},
            {"tipus": "integralt_fuzet", "adat": {"oldal_db": 12, "kep_db": 12}}])
        self.assertEqual(v, {"fogadva": True})
        self.assertEqual([(t, json.loads(a)) for t, a in self.tarolt()], [
            ("kartya_valasz", {"jegy": 3, "ms": 4200, "kartya_id": "c-7f3a9e21"}),
            ("kviz_eredmeny", {"jo": 7, "ossz": 10, "ms": 90_000}),
            ("integralt_video", {"video_s": 322, "jegyzet_db": 2, "kotes": "valoszinu"}),
            ("integralt_fuzet", {"oldal_db": 12, "kep_db": 12})])

    def test_az_ismeretlen_kulcs_kiesik_az_esemeny_megmarad(self):
        """A jegyzet címe, szövege, útja a kulcsok között nem juthat az adatbázisba."""
        v = self.fogad(esemenyek=[{"tipus": "kartya_valasz", "ut": MATEK, "adat": {
            "jegy": 2, "cim": "Titkos jegyzet", "szoveg": "a kártya kérdése", "ut": MATEK, "ertekeles": 3}}])
        self.assertEqual(v, {"fogadva": True})
        [(_, adat)] = self.tarolt()
        self.assertEqual(json.loads(adat), {"jegy": 2})
        self.assertNotIn("Titkos", adat)

    def test_csak_ismeretlen_kulcs_eseten_nincs_adat_de_van_esemeny(self):
        self.assertEqual(self.fogad(esemenyek=[{"tipus": "integralt_video", "adat": {"cim": "x"}}]), {"fogadva": True})
        self.assertEqual(self.tarolt(), [("integralt_video", None)])

    def test_a_rossz_ertek_az_elemet_dobja_el(self):
        rossz = [
            ("kartya_valasz", {"jegy": 0}), ("kartya_valasz", {"jegy": 5}), ("kartya_valasz", {"jegy": "3"}),
            ("kartya_valasz", {"jegy": 2.5}), ("kartya_valasz", {"jegy": True}), ("kartya_valasz", {"ms": -1}),
            ("kartya_valasz", {"kartya_id": "Kérdés szövege"}), ("kartya_valasz", {"kartya_id": "c-" + "a" * 40}),
            ("kartya_valasz", {"kartya_id": 5}), ("kviz_eredmeny", {"jo": 11, "ossz": 10}),
            ("integralt_video", {"kotes": "talan"}), ("integralt_video", {"video_s": -5}),
            ("integralt_video", {"jegyzet_db": {"a": 1}}), ("integralt_fuzet", {"oldal_db": None}),
        ]
        for tipus, adat in rossz:
            with self.subTest(tipus=tipus, adat=adat):
                v = self.fogad(esemenyek=[{"tipus": tipus, "adat": adat}, {"tipus": "kviz_eredmeny", "adat": {"jo": 1}}])
                self.assertEqual(v["elvetve"], 1, v)
        self.assertEqual(len(self.tarolt()), len(rossz), "csak a jó kísérőelem íródott")

    def test_a_felso_hatar_es_egesz_float(self):
        self.assertEqual(self.fogad(esemenyek=[{"tipus": "kartya_valasz", "adat": {"jegy": 4.0, "ms": 3_600_000}}]), {"fogadva": True})
        self.assertEqual(json.loads(self.tarolt()[0][1]), {"jegy": 4, "ms": 3_600_000})

    def test_minden_esemenytipusnak_van_semaja(self):
        # a cpp-események (C36a) szigorúbb, kötelező kulcsos sémája a CPP_ADAT-ban él; a két tábla diszjunkt és együtt teljes
        self.assertEqual(set(tracker.ADAT_SEMA) | set(tracker.CPP_ADAT), set(tracker.ESEMENY_TIPUSOK))
        self.assertFalse(set(tracker.ADAT_SEMA) & set(tracker.CPP_ADAT))

    def test_a_core_oldali_gyujto_ugyanazt_az_utat_hasznalja(self):
        """Az `integralt_video` kibocsátója (a hívási pontja a C20b): kapcsoló, séma, elvetés ugyanaz."""
        self.assertEqual(self.tr.integralt_video(MATEK, 322, 2, "biztos"), {"fogadva": True})
        self.assertEqual(json.loads(self.tarolt()[0][1]), {"video_s": 322, "jegyzet_db": 2, "kotes": "biztos"})
        self.assertEqual(self.tr.integralt_video(MATEK, 5, 1, "kitalalt")["elvetve"], 1)
        n = self.tr.statisztika(NAP, NAP)["napok"][0]
        self.assertEqual(n["integralt"], 1)



class VodrokEgyezesTest(unittest.TestCase):
    """C33 (T181, 30(e)): a késleltetés-vödrök a core-ban és a kliensben egyeznek — a p50/p95 a vödör felső határa, a két
    oldal eltérése csendben hamis számot adna. A kliens `kesleltetes.ts`-éből olvasva."""

    def test_a_kliens_vodrei_azonosak_a_core_eval(self):
        import re
        from pathlib import Path
        ts = (Path(__file__).resolve().parents[1] / "app" / "src" / "lib" / "tracker" / "kesleltetes.ts").read_text(encoding="utf-8")
        m = re.search(r"export const VEDROK_MS\s*=\s*\[([^\]]*)\]", ts)
        self.assertIsNotNone(m, "a kesleltetes.ts-ben nincs VEDROK_MS")
        kliens = [int(x) for x in re.findall(r"\d+", m.group(1))]
        self.assertEqual(kliens, tracker.VEDROK_MS)
        self.assertEqual(len(kliens) + 1, tracker.VEDOR_DB)


class ParancsAzonositoTest(unittest.TestCase):
    """C33 (NAPLO „Ötletek”, C29.7t): a felület parancs-regiszterének minden azonosítója a core `PARANCS_MINTA`-jának alakja —
    különben a használati mérés (`has_parancs`) a parancsot csendben elveti (T029). A forrásból olvasva: a literális
    `id: '…'` és a sablonos `` id: `…${x}…` `` azonosítók (a változó helyén egy betű)."""

    def test_a_felulet_parancsazonositoi_a_core_mintajara_illenek(self):
        import re
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "app" / "src"
        talalt, rossz = 0, []
        for f in list(src.rglob("*.ts")) + list(src.rglob("*.svelte")):
            t = f.read_text(encoding="utf-8")
            for m in re.finditer(r"\bid: (?:'([^'\n]*\.[^'\n]*)'|`([^`\n]*\.[^`\n]*)`)", t):
                azon = m.group(1) if m.group(1) is not None else re.sub(r"\$\{[^}]*\}", "x", m.group(2))
                if "." not in azon:                 # a sablon pontja a `${…}` kifejezésben állt: nem parancsazonosító
                    continue
                talalt += 1
                if not tracker.PARANCS_MINTA.match(azon):
                    rossz.append(f"{f.relative_to(src)}: {azon}")
        self.assertGreater(talalt, 50)
        self.assertEqual(rossz, [])


if __name__ == "__main__":
    unittest.main()
