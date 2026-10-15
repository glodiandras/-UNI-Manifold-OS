"""A kézi import és törlés kizárólag álvaulton."""
import base64
import json
import unittest
from types import SimpleNamespace
from core import csatolmany
from core.utvonalak import HttpError
from tests.test_atnevezes import Alap


class CsatolmanyTest(Alap):
    def app(self):
        return SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A)

    def kuld(self, bajtok="kép".encode(), **extra):
        return csatolmany.feltolt(self.app(), {
            "nev": "kep.png", "adat": base64.b64encode(bajtok).decode(), "vege": True, **extra})

    def test_nem_ir_felul_es_nem_indit_feladatot(self):
        r = self.kuld()
        self.assertIsNone(r["figyelmeztetes"])
        self.assertEqual(r["ut"], "kep 1.png")
        self.assertEqual((self.v / r["ut"]).read_bytes(), "kép".encode())
        self.assertEqual((self.v / "kep.png").read_bytes(), b"\x89PNG\r\n")
        self.assertNotIn("kep 1.png", self.repo.git("ls-files").stdout)

    def test_jegyzet_melletti_csatolmany_mappa(self):
        (self.v / ".obsidian/app.json").write_text(json.dumps({"attachmentFolderPath": "./Média"}))
        r = self.kuld(forras="A/Cél.md")
        self.assertEqual(r["ut"], "A/Média/kep.png")

    def test_darabolt_feltoltes_es_ismetelt_lezaras(self):
        r = self.kuld(b"abc", vege=False)
        with self.assertRaises(HttpError):
            self.kuld(b"d", azon=r["azon"], offset=0)
        veg = self.kuld(b"def", azon=r["azon"], offset=3)
        self.assertEqual((self.v / veg["ut"]).read_bytes(), b"abcdef")
        self.assertEqual(self.kuld(b"def", azon=r["azon"], offset=3)["ut"], veg["ut"])

    def test_kilepes_a_vaultbol_tiltott(self):
        for nev in ("../x.png", "/x.png", ".hidden.png", "x\ny.png"):
            with self.subTest(nev=nev), self.assertRaises((HttpError, ValueError)):
                self.kuld(nev=nev)

    def test_mappa_es_kuka_megerosites(self):
        csatolmany.uj_mappa(self.app(), {"nev": "Új"})
        self.assertTrue((self.v / "Új").is_dir())
        with self.assertRaises(HttpError):
            csatolmany.kuka(self.app(), {"ut": "Új"}, lambda p: None)
        cel = self.root / "álkuka"
        csatolmany.kuka(self.app(), {"ut": "Új", "megerosit": True}, lambda p: p.rename(cel))
        self.assertTrue(cel.is_dir())
        self.assertFalse((self.v / "Új").exists())

    def test_kepimport_nem_kuld_be_feladatot(self):
        """80(a): a behúzott/beillesztett kép importja semmilyen feladatot (AI-t) nem indít."""
        from unittest import mock
        from core import tasks
        sor = SimpleNamespace(submit=mock.Mock(side_effect=AssertionError("feladat indult")))
        app = SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A, queue=sor)
        with mock.patch.object(tasks.Queue, "submit", side_effect=AssertionError("feladat indult")) as submit:
            r = csatolmany.feltolt(app, {"nev": "foto.png", "adat": base64.b64encode(b"x").decode(), "vege": True,
                                         "forras": "A/Cél.md"})
        self.assertTrue(r["kesz"])
        sor.submit.assert_not_called()
        submit.assert_not_called()

    def test_zar_feltoltes_utan_es_hibanal_is_torlodik(self):
        r = self.kuld(b"abc", vege=False)
        self.assertEqual(csatolmany._ZARAK, {})
        with self.assertRaises(HttpError):
            self.kuld(b"d", azon=r["azon"], offset=0)
        self.assertEqual(csatolmany._ZARAK, {})
        self.kuld(b"def", azon=r["azon"], offset=3)
        self.assertEqual(csatolmany._ZARAK, {})

    def test_elavult_feltoltesi_mappak_takaritasa(self):
        import os
        import time
        gyoker = self.cfg.path("tmp") / "csatolmany"
        regi, friss = gyoker / ("a" * 32), gyoker / ("b" * 32)
        for m in (regi, friss, gyoker / "idegen"):
            m.mkdir(parents=True)
            (m / "adat.part").write_bytes(b"x")
        (gyoker / ("c" * 32)).symlink_to(self.root)
        tegnapelott = time.time() - 3 * 24 * 3600
        for p in (regi, regi / "adat.part", gyoker / "idegen", gyoker / "idegen" / "adat.part"):
            os.utime(p, (tegnapelott, tegnapelott))
        self.assertEqual(csatolmany.takarit(gyoker), ["a" * 32])
        self.assertFalse(regi.exists())
        self.assertTrue(friss.is_dir() and (gyoker / "idegen").is_dir() and (gyoker / ("c" * 32)).is_symlink())
        self.assertTrue(self.root.is_dir())

    def test_kuka_a_hej_cli_kulcsat_es_a_vault_gyokeret_adja(self):
        from unittest import mock
        csatolmany.uj_mappa(self.app(), {"nev": "Törlendő"})
        valasz = SimpleNamespace(returncode=0, stdout='{"ok": true}')
        with mock.patch.object(csatolmany.subprocess, "run", return_value=valasz) as run:
            csatolmany.kuka(self.app(), {"ut": "Törlendő", "megerosit": True})
        argv, kw = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(argv, [str(self.cfg.path("hej_cli")), "--kuka"])
        self.assertEqual(json.loads(kw["input"]), {"ut": str(self.v / "Törlendő"), "gyoker": str(self.V.root)})
        self.cfg.utak.pop("hej_cli")                               # régi konfiguráció: a naptar_seged a tartalék
        self.assertEqual(csatolmany.hej_cli(self.cfg), self.cfg.path("naptar_seged"))

    # ---- F2 (2026-10-14): foglalt kör-zár, az utolsó darab ismétlése, a másolás a zár előtt, a Kuka-segéd hibaszövege

    def _foglalt(self):
        """A kör-zár egy másik leíróval foglalva (a flock leíró-szintű: ugyanabban a folyamatban is ütközik)."""
        import fcntl
        from core import frame
        lock = frame.lock_path(self.cfg)
        lock.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock, "a+")
        fcntl.flock(fh, fcntl.LOCK_EX)
        self.addCleanup(fh.close)
        return fh

    def test_foglalt_kor_zar_409_es_az_utolso_darab_ismetelheto(self):
        from unittest import mock
        from core import frame
        r = self.kuld(b"abc", vege=False)
        fh = self._foglalt()
        with mock.patch.object(frame, "felhasznaloi_turelem", return_value=0.1), self.assertRaises(HttpError) as cm:
            self.kuld(b"def", azon=r["azon"], offset=3)
        self.assertEqual((cm.exception.code, cm.exception.data.get("foglalt")), (409, True))
        self.assertEqual([p.name for p in self.v.iterdir() if p.name.endswith(".manifold-tmp")], [])   # az átmeneti másolat törlődött
        fh.close()
        veg = self.kuld(b"def", azon=r["azon"], offset=3)           # ugyanaz az utolsó darab újra: nem „sorrend eltér”
        self.assertEqual((self.v / veg["ut"]).read_bytes(), b"abcdef")
        self.assertEqual(self.kuld(b"def", azon=r["azon"], offset=3)["ut"], veg["ut"])

    def test_az_utolso_darab_mas_tartalommal_sorrend_hiba(self):
        from unittest import mock
        from core import frame
        r = self.kuld(b"abc", vege=False)
        fh = self._foglalt()
        with mock.patch.object(frame, "felhasznaloi_turelem", return_value=0.05), self.assertRaises(HttpError):
            self.kuld(b"def", azon=r["azon"], offset=3)
        fh.close()
        with self.assertRaises(HttpError) as cm:
            self.kuld(b"XYZ", azon=r["azon"], offset=3)
        self.assertEqual((cm.exception.code, cm.exception.data.get("offset")), (409, 6))
        with self.assertRaises(HttpError):
            self.kuld(b"def", azon=r["azon"], offset=2)              # nem a vége: hiba marad

    def test_a_masolas_a_kor_zar_elott_fut(self):
        from unittest import mock
        from core import frame
        eredeti = csatolmany.shutil.copyfileobj
        zar_szabad = []

        def masol(*a, **k):
            try:
                with frame.run_lock(self.cfg, wait=False):
                    zar_szabad.append(True)
            except frame.Busy:
                zar_szabad.append(False)
            return eredeti(*a, **k)
        with mock.patch.object(csatolmany.shutil, "copyfileobj", masol):
            r = self.kuld(b"tartalom")
        self.assertEqual(zar_szabad, [True])
        self.assertEqual((self.v / r["ut"]).read_bytes(), b"tartalom")

    def test_uj_mappa_es_kuka_foglalt_zarnal_409(self):
        from unittest import mock
        from core import frame
        csatolmany.uj_mappa(self.app(), {"nev": "Megvan"})
        self._foglalt()
        with mock.patch.object(frame, "felhasznaloi_turelem", return_value=0.05):
            for hivas in (lambda: csatolmany.uj_mappa(self.app(), {"nev": "Új2"}),
                          lambda: csatolmany.kuka(self.app(), {"ut": "Megvan", "megerosit": True}, lambda p: None)):
                with self.assertRaises(HttpError) as cm:
                    hivas()
                self.assertEqual((cm.exception.code, cm.exception.data.get("foglalt")), (409, True))

    def _seged(self, valasz):
        """Csak a `--kuka` hívást cseréli (a pillanatkép git-hívásai a valódi `subprocess.run`-on mennek)."""
        from unittest import mock
        eredeti = csatolmany.subprocess.run
        return mock.patch.object(csatolmany.subprocess, "run",
                                 side_effect=lambda cmd, *a, **k: valasz if "--kuka" in cmd else eredeti(cmd, *a, **k))

    def test_kuka_seged_hibaszovege_a_valaszban(self):
        csatolmany.uj_mappa(self.app(), {"nev": "Törlendő"})
        szoveg = f"A macOS nem tette a Kukába: „{self.v / 'Törlendő'}” nincs jogosultság ({self.V.root})."
        valasz = SimpleNamespace(returncode=1, stdout=json.dumps({"ok": False, "kod": "kuka_hiba", "hiba": szoveg}))
        with self._seged(valasz), self.assertRaises(HttpError) as cm:
            csatolmany.kuka(self.app(), {"ut": "Törlendő", "megerosit": True})
        self.assertEqual(cm.exception.code, 503)
        self.assertEqual(cm.exception.data, {"kod": "kuka_hiba"})
        self.assertIn("Törlendő", str(cm.exception))
        self.assertNotIn(str(self.root), str(cm.exception))         # abszolút út nem megy ki (78(e))
        # régi segéd (csak `ok`) és olvashatatlan válasz: az általános üzenet, `kod` nélkül
        for stdout in ('{"ok": false}', "nem json", ""):
            with self._seged(SimpleNamespace(returncode=1, stdout=stdout)), self.assertRaises(HttpError) as cm:
                csatolmany.kuka(self.app(), {"ut": "Törlendő", "megerosit": True})
            self.assertEqual((cm.exception.code, cm.exception.data), (503, {}), stdout)
            self.assertIn("macOS Kuka", str(cm.exception))


class AutomatikusKapuTest(unittest.TestCase):
    def test_csak_a_vektorindex_automatikus(self):
        from core import server, tasks
        t = lambda i, a: tasks.TaskType(id=i, title=i, plan=lambda *x: ([], "", None), automatikus=a)
        self.assertIsNone(server.automatikus_tiltott(t("vektorindex", True)))
        self.assertIsNone(server.automatikus_tiltott(t("kartya", False)))
        for nev in ("kartya_automatikus", "fuzet_automatikus", "grafikon_automatikus"):
            indok = server.automatikus_tiltott(t(nev, True))
            self.assertIn(nev, indok)
            self.assertIn("80(a)", indok)
