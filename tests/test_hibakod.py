"""English error fallbacks at real core boundaries, using synthetic temp workspaces."""
import ast
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import unittest

from core import config, server, tasks, tulajdonsagok, vaultio
from core.hibakod import angol_uzenet, json_param, kodol
from core.hibauzenetek import ANGOL
from core.utvonalak import HttpError, hiba_torzs
from tests.helpers import alg_core, tmpdir, vault_sema

REPO = Path(__file__).resolve().parent.parent
HELYORZO = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class AngolHibakodTest(unittest.TestCase):
    def test_a_kivetel_szovege_megmarad_de_a_publikus_hiba_angol(self):
        e = vaultio.Invalid("hiányzó út")
        self.assertIs(kodol(e, "index.olvaso.hianyzo_ut"), e)
        self.assertEqual(str(e), "hiányzó út")
        self.assertEqual(hiba_torzs(e), {"hiba": "The path is missing.", "kod": "index.olvaso.hianyzo_ut", "param": {}})

    def test_a_param_egyszer_helyettesul_es_a_hianyzo_param_nem_latszik(self):
        sz = angol_uzenet("vault.nincs_fajl", {"ut": "{titok}.md"})
        self.assertEqual(sz, "There is no such file: {titok}.md")
        self.assertEqual(angol_uzenet("vault.nincs_fajl"), "The operation could not be completed. Try again.")
        self.assertEqual(angol_uzenet("uj.kod", tartalek="This extension failed."), "This extension failed.")

    def test_a_param_szigoru_json_es_nem_osztott_szotar(self):
        p = {"ut": Path("a/b.md"), "hiba": ValueError("x"), "n": math.nan, "inf": math.inf, "ok": True}
        e = HttpError(400, "régi", kod="proba.kod", param=p)
        p["ok"] = False
        self.assertEqual(e.param, {"ut": "a/b.md", "hiba": "x", "n": "nan", "inf": "inf", "ok": True})
        json.dumps(e.torzs(), allow_nan=False)
        self.assertEqual(json_param({1: None}), {"1": None})

    def test_minden_literal_core_hibakodnak_van_tartaleka_es_paramja(self):
        """Catch missing messages and mismatched parameters before an affected branch executes."""
        for p in (REPO / "core").rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text())):
                if not isinstance(n, ast.Call) or not isinstance(n.func, (ast.Name, ast.Attribute)):
                    continue
                nev = n.func.id if isinstance(n.func, ast.Name) else n.func.attr
                if nev in ("HttpError", "ConfigError"):
                    kod = next((k.value for k in n.keywords if k.arg == "kod"), None)
                    param = next((k.value for k in n.keywords if k.arg == "param"), None)
                    kulcsok = {k.value for k in param.keys if isinstance(k, ast.Constant)} if isinstance(param, ast.Dict) else set()
                elif nev in ("kodol", "kodos") and len(n.args) > 1:
                    kod = n.args[1]
                    param = n.args[2] if len(n.args) > 2 else None
                    kulcsok = {k.value for k in param.keys if isinstance(k, ast.Constant)} if isinstance(param, ast.Dict) else {k.arg for k in n.keywords}
                else:
                    continue
                if not isinstance(kod, ast.Constant) or not isinstance(kod.value, str):
                    continue
                with self.subTest(ut=str(p.relative_to(REPO)), sor=n.lineno, kod=kod.value):
                    self.assertIn(kod.value, ANGOL)
                    # ConfigError sometimes supplies parameters by a computed mapping.
                    if nev != "ConfigError":
                        self.assertFalse(set(HELYORZO.findall(ANGOL[kod.value])) - kulcsok)

    def test_az_app_es_core_kozos_angol_uzenetei_azonosak(self):
        for p in (REPO / "app/src/lib/i18n/en").glob("*.json"):
            for kulcs, szoveg in json.loads(p.read_text()).items():
                if kulcs.startswith("hiba."):
                    with self.subTest(kulcs=kulcs):
                        self.assertEqual(ANGOL.get(kulcs[5:]), szoveg)

    def test_a_lemezhiba_nem_szivarogtat_abszolut_utat(self):
        import errno
        e = PermissionError(errno.EACCES, "hozzáférés megtagadva", "/private/example/note.md")
        statusz, adat = vaultio.lemez_hiba(e)
        self.assertEqual(statusz, 503)
        self.assertEqual(adat["kod"], "lemez.eacces")
        self.assertIn("not writable", adat["hiba"])
        self.assertNotIn("/private", json.dumps(adat))
        self.assertEqual(adat["errno"], "EACCES")

    def test_a_konfiguracios_kezfogas_angol_de_a_regi_kod_megmarad(self):
        ki = io.StringIO()
        e = config.ConfigError("hibás konfiguráció", kod="workspace_csere", param={"ut": Path("note.md")})
        self.assertEqual(server._hiba_kezfogas(ki, e), 78)
        adat = json.loads(ki.getvalue())
        self.assertEqual(adat["hiba"], "workspace_csere")
        self.assertIn("different workspace", adat["uzenet"])
        self.assertEqual(adat["param"], {"ut": "note.md"})

    def test_a_tartalmi_nyelv_fuggetlen_a_felulettol(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        cfg.data["workspace"] = {"nyelv": "hu"}
        cfg.data["sablon"]["nyelv"] = "en"
        cfg.data.setdefault("felulet", {})["nyelv"] = "en"
        sema = tulajdonsagok.Sema(vault_sema(), cfg)
        self.assertEqual(sema.leiras()["nyelv"], "hu")
        cfg.data["workspace"] = {}
        self.assertEqual(tulajdonsagok.Sema(vault_sema(), cfg).leiras()["nyelv"], "en")


class FeladatHibakodTest(unittest.TestCase):
    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)
        self.esemenyek = []
        self.sorok = []
        self.addCleanup(lambda: [q.close() for q in self.sorok if not q._db_zarva])
        self.addCleanup(lambda: tasks.REGISTRY.pop("t_hibakod", None))
        tasks.register(tasks.TaskType("t_hibakod", "Trial task", lambda cfg, p, stop: (
            [tasks.Step("Run", [sys.executable, "-c", "pass"], str(cfg.root))], "Source {literal}.md", ["Trial warning."])))

    def sor(self):
        q = tasks.Queue(self.cfg, gate=lambda: False, start_delay=3600,
                        publish=lambda e, **kw: self.esemenyek.append(e))
        self.sorok.append(q)
        return q

    def test_v2_migracio_adatvesztes_nelkul_es_ismetelt_megnyitas(self):
        db_ut = self.cfg.path("feladatok_db")
        db_ut.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_ut) as db:
            db.executescript(tasks._SEMA + "ALTER TABLE feladat ADD COLUMN lepes_pid INTEGER; "
                            "ALTER TABLE feladat ADD COLUMN lepes_inditva TEXT; "
                            "ALTER TABLE feladat ADD COLUMN lepes_argv0 TEXT; PRAGMA user_version=2;")
            db.execute("INSERT INTO feladat(id,tipus,cim,allapot,letrehozva,osszegzes,parameterek,hiba) "
                       "VALUES (?,?,?,?,?,?,?,?)", ("F-old", "t_hibakod", "Old title", "hiba", "2026-10-16", "Keep summary", '{"x": 2}', "régi hiba"))
        q = self.sor()
        d = q.get("F-old")
        self.assertEqual((d["cim"], d["osszegzes"], d["parameterek"]), ("Old title", "Keep summary", {"x": 2}))
        self.assertEqual(d["kod"], "feladat.futtatas_hibas")
        self.assertIn("could not be completed", d["hiba"])
        self.assertEqual(q._db.execute("SELECT hiba FROM feladat WHERE id='F-old'").fetchone()[0], "régi hiba")
        self.assertEqual(q._db.execute("PRAGMA user_version").fetchone()[0], 3)
        q.close()
        q2 = self.sor()
        self.assertEqual(q2.get("F-old"), d)
        self.assertEqual(q2._db.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_hiba_metaadat_a_reszletben_tortenetben_es_ws_esemenyben(self):
        q = self.sor()
        alap = q.submit("t_hibakod", {"ut": "Forrás.md"})
        fid = alap["id"]
        with q._lock:
            d = q._update(fid, allapot="hiba", kilepes=7,
                          **tasks._hiba_adat("feladat.lepes_hibas", lepes=1, kilepes=7))
        q._event(d)
        vart = {"hiba": "Step 1 failed with exit code 7.", "kod": "feladat.lepes_hibas", "param": {"lepes": 1, "kilepes": 7}}
        for adat in (q.get(fid), q.detail(fid), q.list()[0], self.esemenyek[-1]["feladat"]):
            self.assertEqual({k: adat[k] for k in vart}, vart)
            for kulcs in ("cim", "osszegzes", "parameterek", "figyelmeztetes", "lepesek", "eroforras"):
                self.assertEqual(adat[kulcs], alap[kulcs])
            self.assertNotIn("hiba_kod", adat)
            self.assertNotIn("hiba_param", adat)
        q.close()
        self.assertEqual({k: self.sor().get(fid)[k] for k in vart}, vart)


if __name__ == "__main__":
    unittest.main()
