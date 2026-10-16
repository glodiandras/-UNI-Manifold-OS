"""F7 Privacy Center: a valós állapot (hálózat, modellek, tárolt adat, AI-memória, tracker, integrációk, engedélyek)."""
import json
import os
import shutil
import sqlite3
import unittest
from types import SimpleNamespace
from unittest import mock

from core import adatvedelem, vezerlo
from tests.helpers import REPO, tmpdir
from tests.test_doctor_termek import termek_epit

TITOK = "SENTINEL-JEGYZET-SZOVEG"


def _epit(t):
    k = termek_epit(t)
    shutil.copy(REPO / "config" / "models.toml", k.root / "config" / "models.toml")
    return k


class AdatvedelemTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)
        self.cfg = self.k.cfg
        (self.k.vault / "note.md").write_text(f"# t\n{TITOK}\n", encoding="utf-8")

    def test_az_allapot_szerkezete_es_hogy_jegyzet_tartalom_nem_kerul_bele(self):
        a = adatvedelem.allapot(self.cfg)
        self.assertEqual(set(a), {"verzio", "mikor", "halozat", "modellek", "adat", "memoria", "tracker", "integraciok", "engedelyek"})
        json.dumps(a, allow_nan=False)
        self.assertNotIn(TITOK, json.dumps(a))

    def test_halozat_offline_a_valos_kornyezetbol_es_tiltott_lista(self):
        self.assertTrue(adatvedelem.halozat(self.cfg, env={"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})["offline"])
        self.assertFalse(adatvedelem.halozat(self.cfg, env={})["offline"])
        h = adatvedelem.halozat(self.cfg, env={})
        self.assertEqual(h["engedett"] and [e["kod"] for e in h["engedett"]], ["models", "runtime_tools", "video_links"])
        self.assertIn("telemetry", h["tiltott"])
        self.assertTrue(set(h["tiltott"]).isdisjoint(e["kod"] for e in h["engedett"]))

    def test_kikapcsolt_video_modul_a_video_letoltest_nem_elerhetonek_mutatja(self):
        self.cfg.data.setdefault("modulok", {})["video"] = False
        h = adatvedelem.halozat(self.cfg, env={})
        self.assertEqual({e["kod"]: e["elerheto"] for e in h["engedett"]}["video_links"], False)

    def test_utolso_letoltesek_a_naplokbol_csak_gazdagepnevvel(self):
        runs = self.cfg.path("runs")
        runs.mkdir(parents=True, exist_ok=True)
        naplo = runs / "letoltes-20260101-000000.json"
        naplo.write_text(json.dumps({"qwen": {"repo": "o/q", "meret_gb": 1, "eredmeny": "ok"}}), encoding="utf-8")
        os.utime(naplo, (1_700_000_000, 1_700_000_000))
        db = self.cfg.path("feladatok_db")
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE feladat (sor INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, tipus TEXT, parameterek TEXT, allapot TEXT, vegzett TEXT)")
        c.execute("INSERT INTO feladat (id, tipus, parameterek, allapot, vegzett) VALUES ('1', 'video_letoltes', ?, 'kesz', '2026-02-02T10:00:00')",
                  (json.dumps({"urlek": ["https://www.example.org/watch?v=SECRETQUERY&t=1"]}),))
        c.execute("INSERT INTO feladat (id, tipus, parameterek, allapot, vegzett) VALUES ('2', 'kartya', '{}', 'kesz', '2026-03-03T10:00:00')")
        c.commit()
        c.close()
        ki = adatvedelem.utolso_letoltesek(self.cfg)
        self.assertEqual([(x["fajta"], x["nev"]) for x in ki], [("video_links", "www.example.org"), ("models", "qwen")])
        self.assertNotIn("SECRETQUERY", json.dumps(ki))
        self.assertEqual(ki[1]["eredmeny"], "ok")

    def test_letoltes_lista_korlatos(self):
        runs = self.cfg.path("runs")
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "letoltes-x.json").write_text(json.dumps({f"m{i}": {"eredmeny": "ok"} for i in range(30)}), encoding="utf-8")
        self.assertEqual(len(adatvedelem.utolso_letoltesek(self.cfg)), adatvedelem.MAX_LETOLTES)

    def test_modellek_a_lemezen_levo_allapotbol(self):
        from core.modell import manifeszt
        nev = next(iter(manifeszt.betolt(self.cfg)["modell"]))

        def tel(models, n, m):
            return {"allapot": "kesz" if n == nev else "nincs", "lemez_bajt": 1234 if n == nev else 0, "ellenorizve": None, "revizio": m["revizio"]}
        with mock.patch.object(manifeszt, "telepitettseg", tel):
            m = adatvedelem.modellek(self.cfg)
        self.assertEqual([x["nev"] for x in m["telepitve"]], [nev])
        self.assertEqual((m["bajt"], m["telepitve"][0]["bajt"], m["hiba"]), (1234, 1234, None))

    def test_hianyzo_manifeszt_nem_dob(self):
        (self.k.root / "config" / "models.toml").unlink()
        self.assertEqual(adatvedelem.modellek(self.cfg)["hiba"], "modell.manifeszt_hianyzik")

    def test_adat_helyek_a_konfiguralt_utakbol_valos_meretekkel(self):
        index = self.cfg.path("index")
        index.mkdir(parents=True, exist_ok=True)
        (index / "vault.sqlite").write_bytes(b"x" * 5000)
        helyek = {h["kod"]: h for h in adatvedelem.adat_helyek(self.cfg)}
        self.assertEqual(set(helyek), {"workspace", "snapshots", "index", "personal", "models", "backup", "caches", "logs"})
        self.assertEqual((helyek["index"]["bajt"], helyek["index"]["van"], helyek["index"]["torolheto"]), (5000, True, True))
        self.assertGreater(helyek["workspace"]["bajt"], 0)
        self.assertFalse(helyek["models"]["torolheto"])
        self.assertEqual(helyek["workspace"]["ut"], str(self.k.vault))

    def test_ai_memoria_darabszamok_es_kapcsolo(self):
        ap = SimpleNamespace(asszisztens=SimpleNamespace(tanult=lambda: {"mintak": [1, 2, 3], "muveletek": [1], "elutasitott": [], "hangolas": {"a": 1}}))
        m = adatvedelem.memoria(self.cfg, ap)
        self.assertEqual((m["tetelek"], m["osszes"]), ({"mintak": 3, "muveletek": 1, "elutasitott": 0, "hangolas": 1}, 5))
        self.assertTrue(m["kapcsolo"])
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        self.assertFalse(adatvedelem.memoria(self.cfg, ap)["kapcsolo"])
        self.assertEqual(adatvedelem.memoria(self.cfg)["osszes"], 0)           # app nélkül sincs hiba

    def test_ai_memoria_hibaja_nem_dobja_el_az_oldalt(self):
        def rossz():
            raise RuntimeError("x")
        self.assertEqual(adatvedelem.memoria(self.cfg, SimpleNamespace(asszisztens=SimpleNamespace(tanult=rossz)))["osszes"], 0)

    def test_tracker_allapot_mit_tarol_mit_nem(self):
        tr = adatvedelem.tracker(self.cfg)
        self.assertIn("note_text", tr["nem_tarol"])
        self.assertNotIn("note_text", tr["tarol"])
        self.assertEqual((tr["van"], tr["bajt"]), (False, 0))
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertFalse(adatvedelem.tracker(self.cfg)["be"])

    def test_integraciok_es_engedelyek_a_beallitasokbol_es_a_naptar_segedtol(self):
        from core import termek_beallitasok as b
        b.ir(self.cfg, b.olvas(self.cfg)["rev"], {"adatvedelem": {"naptar": True, "ertesitesek": False}})
        ap = SimpleNamespace(naptar=SimpleNamespace(d={"seged": True, "esemeny_engedely": "engedelyezve", "emlekezteto_engedely": "elutasitva", "utolso": "2026-01-01"}))
        i = {x["kod"]: x for x in adatvedelem.integraciok(self.cfg, ap)}
        self.assertEqual((i["calendar"]["be"], i["notifications"]["be"], i["calendar"]["utolso"]), (True, False, "2026-01-01"))
        e = adatvedelem.engedelyek(self.cfg, ap)
        self.assertEqual(e["naptar"], {"kapcsolo": True, "esemeny": "engedelyezve", "emlekezteto": "elutasitva"})
        self.assertEqual(e["ertesitesek"], {"kapcsolo": False})

    def test_csak_olvas_nem_hoz_letre_fajlt(self):
        elotte = sorted(str(p) for p in self.k.install.rglob("*")) + sorted(str(p) for p in self.k.vault.rglob("*"))
        adatvedelem.allapot(self.cfg)
        self.assertEqual(sorted(str(p) for p in self.k.install.rglob("*")) + sorted(str(p) for p in self.k.vault.rglob("*")), elotte)


if __name__ == "__main__":
    unittest.main()
