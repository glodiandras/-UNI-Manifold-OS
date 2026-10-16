"""F8: cancelling a running Obsidian import (`POST /api/import/megszakit`, `core/importalas.py`).

The gate of every test (inherited from `_Alap`): the SOURCE is byte- and metadata-identical afterwards. Besides that: the copy stops
at the next file boundary, the journal stays consistent, and the cancelled import can be resumed or undone. Synthetic vaults only."""
from __future__ import annotations

import json
import threading
import types
import unittest
from unittest import mock

from core import importalas as imp
from core import utvonalak, workspace
from core.utvonalak import HttpError
from tests.migracio import tartalom, ujjlenyomat
from tests.migracio.test_obsidian_import import _Alap, _Busz, _vart_masolat

MASOLT_UTAN = 3            # the cancel arrives while the 3rd file is being copied


class _Allj(Exception):
    pass


def _naplo_sorok(naplo: imp.Naplo) -> list[dict]:
    return naplo.sorok()


class MegszakitasTest(_Alap):
    """The core function (`obsidian_importal(..., megszakit=Event)`) without HTTP."""

    def _jelzes_a_fajlnal(self, hova: int):
        """Run an import whose cancel flag is set while file number `hova` is being copied. → (event, copies)"""
        jel = threading.Event()
        eredeti = imp._fajl_masol
        db = {"n": 0}

        def figyelo(*a, **k):
            db["n"] += 1
            if db["n"] == hova:
                jel.set()
            return eredeti(*a, **k)

        return jel, figyelo, db

    def test_megszakitas_a_kovetkezo_fajlhatarnal_all_meg_es_a_naplo_konzisztens(self):
        jel, figyelo, db = self._jelzes_a_fajlnal(MASOLT_UTAN)
        t = self.elonezet()
        with mock.patch.object(imp, "_fajl_masol", figyelo), self.assertRaises(imp.Megszakitva) as e:
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"], megszakit=jel)
        self.assertEqual(db["n"], MASOLT_UTAN, "no file is started after the cancel was requested")
        self.assertEqual((e.exception.kesz_db, e.exception.osszes_db), (MASOLT_UTAN, t["osszesites"]["fajl_db"]))
        a = imp.allapot(t["id"], self.alap)
        self.assertEqual(a["allapot"], "megszakitva")
        self.assertIsNone(a["hiba"])
        self.assertFalse(a["fut"], "the lock is released")
        # nothing half-done: no temporary file, the finished files are complete and journaled with their hashes
        self.assertFalse(list(self.cel.rglob("*.manifold-tmp")))
        naplo = imp._obsidian_naplo(self.alap, t["id"])
        sorok = _naplo_sorok(naplo)
        self.assertEqual(sorok[-1]["m"], "megszakitva")
        fajlok = [s for s in sorok if s["m"] == "fajl"]
        self.assertEqual(len(fajlok), MASOLT_UTAN)
        for s in fajlok:
            self.assertEqual((self.cel / s["ut"]).read_bytes(), (self.forras / s["ut"]).read_bytes())
        # the workspace was not created yet
        self.assertIsNone(workspace.azonosit(self.cel))
        # the preview of the cancelled import shows the state and no obstacle: this is a resume
        p = self.elonezet()
        self.assertEqual((p["allapot"], p["akadaly"]), ("megszakitva", []))
        self.assertEqual(p["osszesites"]["megvan_db"], MASOLT_UTAN)

    def test_megszakitott_import_folytathato_es_bajtra_azonos(self):
        jel, figyelo, _ = self._jelzes_a_fajlnal(MASOLT_UTAN)
        t = self.elonezet()
        with mock.patch.object(imp, "_fajl_masol", figyelo), self.assertRaises(imp.Megszakitva):
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"], megszakit=jel)
        p = self.elonezet()
        r = imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=p["terv_hash"])
        self.assertEqual((r["allapot"], r["megvolt_db"]), ("kesz", MASOLT_UTAN))
        self.assertEqual(r["masolt_db"], t["osszesites"]["masolando_db"] - MASOLT_UTAN)
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))
        self.assertTrue(workspace.azonosit(self.cel))
        self.assertEqual(imp.allapot(t["id"], self.alap)["allapot"], "kesz")
        # the journal tells the whole story: cancelled, then resumed (`folytatas`), then finished
        sorok = _naplo_sorok(imp._obsidian_naplo(self.alap, t["id"]))
        self.assertEqual([s["m"] for s in sorok if s["m"] in ("megszakitva", "kesz")], ["megszakitva", "kesz"])
        self.assertEqual([s["folytatas"] for s in sorok if s["m"] == "kezd"], [False, True])

    def test_megszakitott_import_visszafordithato(self):
        jel, figyelo, _ = self._jelzes_a_fajlnal(MASOLT_UTAN)
        t = self.elonezet()
        with mock.patch.object(imp, "_fajl_masol", figyelo), self.assertRaises(imp.Megszakitva):
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"], megszakit=jel)
        v = imp.visszafordit(t["id"], self.alap, kuka=self.kuka)
        self.assertEqual(v["allapot"], "visszaforditva")
        self.assertFalse(self.cel.exists(), "the folder this import created goes to the Trash as a whole")
        self.assertEqual(self.kuka.utak, [self.cel])
        self.assertEqual(imp.allapot(t["id"], self.alap)["allapot"], "visszaforditva")

    def test_megszakitas_az_utolso_fajl_utan_a_munkater_elott_is_folytathato(self):
        db = {"n": 0}
        jel = threading.Event()
        eredeti = imp._fajl_masol
        t = self.elonezet()

        def figyelo(*a, **k):
            db["n"] += 1
            if db["n"] == t["osszesites"]["fajl_db"]:
                jel.set()                       # during the very last file
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", figyelo), self.assertRaises(imp.Megszakitva) as e:
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"], megszakit=jel)
        self.assertEqual(e.exception.kesz_db, e.exception.osszes_db)
        self.assertIsNone(workspace.azonosit(self.cel), "the workspace step does not start after a cancel")
        r = imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=self.elonezet()["terv_hash"])
        self.assertEqual(r["allapot"], "kesz")
        self.assertTrue(workspace.azonosit(self.cel))
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))

    def test_a_jelzes_nelkuli_futas_valtozatlan(self):
        r = imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=self.elonezet()["terv_hash"],
                                  megszakit=threading.Event())
        self.assertEqual(r["allapot"], "kesz")


class MegszakitasHttpTest(_Alap):
    def setUp(self):
        super().setUp()
        self.r = utvonalak.Regiszter()
        imp.utvonalak(self.r)
        self.app = types.SimpleNamespace(cfg=self.alap, bus=_Busz())
        self.addCleanup(self._takarit)

    def _takarit(self):
        with imp._FUTO_ZAR:
            szalak = list(imp._FUTO.values())
        for sz in szalak:
            sz.join(20)

    def hiv(self, metodus, ut, torzs=None, q=None):
        kezelo, m = self.r.keres(metodus, ut)
        return kezelo(utvonalak.Kerees(self.app, None, ut, q or {}, m, torzs=torzs))

    def _indit_es_megall(self, hova: int):
        """Start the import in the background thread; the HTTP cancel arrives while file `hova` is copied.
        → (preview, response of the cancel)"""
        eredeti = imp._fajl_masol
        db = {"n": 0}
        elerte = threading.Event()
        t = self.hiv("POST", "/api/import/obsidian/elonezet", {"forras": str(self.forras), "cel": str(self.cel)})

        def figyelo(*a, **k):
            db["n"] += 1
            if db["n"] == hova:
                elerte.set()
                # hold the thread inside the copy until the cancel flag is up (no sleeps, no timing guesses)
                with imp._FUTO_ZAR:
                    jel = imp._MEGSZAKIT[t["id"]]
                jel.wait(20)
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", figyelo):
            v = self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel),
                                                         "terv_hash": t["terv_hash"]})
            self.assertEqual((v.kod, v.obj["allapot"]), (202, "fut"))
            self.assertTrue(elerte.wait(20), "the import never reached the file")
            valasz = self.hiv("POST", "/api/import/megszakit", {"id": t["id"]})
        return t, valasz, db

    def test_http_megszakit_leallitja_a_szalat_allapot_megszakitva_forras_erintetlen(self):
        t, valasz, db = self._indit_es_megall(MASOLT_UTAN)
        self.assertEqual(valasz, {"id": t["id"], "allapot": "megszakitva", "megszakitva": True})
        self.assertEqual(db["n"], MASOLT_UTAN)
        with imp._FUTO_ZAR:
            self.assertNotIn(t["id"], imp._FUTO)
            self.assertNotIn(t["id"], imp._MEGSZAKIT)
        vege = [e for e in self.app.bus.esemenyek if e.get("allapot")]
        self.assertEqual([e["allapot"] for e in vege], ["megszakitva"], vege)
        self.assertEqual((vege[0]["kesz_db"], vege[0]["osszes_db"]), (MASOLT_UTAN, t["osszesites"]["fajl_db"]))
        a = self.hiv("GET", "/api/import/allapot", q={"id": t["id"]})
        self.assertEqual((a["allapot"], a["fut"]), ("megszakitva", False))
        self.assertEqual([x["allapot"] for x in self.hiv("GET", "/api/import")["importok"]], ["megszakitva"])
        self.assertFalse(list(self.cel.rglob("*.manifold-tmp")))
        # the journal file on disk is valid JSON lines and ends with the cancel record
        naplo = imp._obsidian_naplo(self.alap, t["id"])
        nyers = (naplo.mappa / imp.NAPLO).read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(nyers[-1])["m"], "megszakitva")
        self.assertTrue(all(json.loads(s) for s in nyers))

    def test_http_megszakitas_utan_folytatas_es_visszafordit(self):
        t, valasz, _ = self._indit_es_megall(MASOLT_UTAN)
        self.assertTrue(valasz["megszakitva"])
        # resume through the same HTTP route
        p = self.hiv("POST", "/api/import/obsidian/elonezet", {"forras": str(self.forras), "cel": str(self.cel)})
        self.assertEqual((p["allapot"], p["akadaly"]), ("megszakitva", []))
        v = self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel), "terv_hash": p["terv_hash"]})
        self.assertEqual(v.kod, 202)
        with imp._FUTO_ZAR:
            szal = imp._FUTO.get(t["id"])
        if szal:
            szal.join(60)
        self.assertEqual(self.hiv("GET", "/api/import/allapot", q={"id": t["id"]})["allapot"], "kesz")
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))
        # ... and the finished import is undone as usual
        with mock.patch.object(imp, "_kuka_gyar", return_value=self.kuka):
            vf = self.hiv("POST", "/api/import/visszafordit", {"id": t["id"]})
        self.assertEqual(vf["allapot"], "visszaforditva")

    def test_http_megszakitott_import_kozvetlenul_visszafordithato(self):
        t, valasz, _ = self._indit_es_megall(MASOLT_UTAN)
        self.assertTrue(valasz["megszakitva"])
        with mock.patch.object(imp, "_kuka_gyar", return_value=self.kuka):
            vf = self.hiv("POST", "/api/import/visszafordit", {"id": t["id"]})
        self.assertEqual(vf["allapot"], "visszaforditva")
        self.assertFalse(self.cel.exists())

    def test_http_nem_futo_import_megszakitasa_409_es_ervenytelen_kerest_elutasit(self):
        for torzs, kod, ok in (({"id": "obs-" + "0" * 16}, 409, "import.nem_fut"),
                               ({"id": "v2-" + "0" * 16}, 409, "import.nem_fut"),
                               ({"id": "../../etc"}, 400, "import.ervenytelen_keres"),
                               ({}, 400, "import.ervenytelen_keres"),
                               ({"id": "obs-" + "0" * 16, "extra": 1}, 400, "import.ervenytelen_keres")):
            with self.assertRaises(HttpError) as e:
                self.hiv("POST", "/api/import/megszakit", torzs)
            self.assertEqual((e.exception.code, e.exception.kod), (kod, ok), torzs)

    def test_http_mar_kesz_import_megszakitasa_nem_rontja_el(self):
        """The cancel arrives after the import finished: nothing is cancelled, the answer says so."""
        t = self.hiv("POST", "/api/import/obsidian/elonezet", {"forras": str(self.forras), "cel": str(self.cel)})
        self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel), "terv_hash": t["terv_hash"]})
        with imp._FUTO_ZAR:
            szal = imp._FUTO.get(t["id"])
            jel = imp._MEGSZAKIT.get(t["id"])
        if szal is not None and jel is not None:
            szal.join(60)
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/import/megszakit", {"id": t["id"]})
        self.assertEqual(e.exception.kod, "import.nem_fut")
        self.assertEqual(self.hiv("GET", "/api/import/allapot", q={"id": t["id"]})["allapot"], "kesz")
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))

    def test_http_lassu_fajl_202_majd_a_szal_megall(self):
        """If the thread needs longer than the wait, the answer is 202 and the WS event follows."""
        eredeti = imp._fajl_masol
        elerte, mehet = threading.Event(), threading.Event()
        t = self.hiv("POST", "/api/import/obsidian/elonezet", {"forras": str(self.forras), "cel": str(self.cel)})
        db = {"n": 0}

        def lassu(*a, **k):
            db["n"] += 1
            if db["n"] == 2:
                elerte.set()
                mehet.wait(20)
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", lassu), mock.patch.object(imp, "_MEGSZAKIT_VARAKOZAS_MP", 0.05):
            self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel), "terv_hash": t["terv_hash"]})
            self.assertTrue(elerte.wait(20))
            valasz = self.hiv("POST", "/api/import/megszakit", {"id": t["id"]})
            self.assertEqual((valasz.kod, valasz.obj), (202, {"id": t["id"], "allapot": "megszakitas"}))
            mehet.set()
            with imp._FUTO_ZAR:
                szal = imp._FUTO.get(t["id"])
            if szal:
                szal.join(30)
        self.assertEqual(imp.allapot(t["id"], self.alap)["allapot"], "megszakitva")
        self.assertEqual(self.app.bus.esemenyek[-1]["allapot"], "megszakitva")
        self.assertEqual(db["n"], 2)

    def test_megszakitas_vegen_a_forras_bajtra_azonos(self):
        t, _, _ = self._indit_es_megall(2)
        self.assertEqual(ujjlenyomat(self.forras), self.lenyomat)


if __name__ == "__main__":
    unittest.main()
