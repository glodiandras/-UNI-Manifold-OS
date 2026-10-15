"""A pillanatkép-keret (`core/frame.py`): kör-zár, kézi commit előtte, gépi commit utána — álvaulton."""
import fcntl
import unittest

from core import frame, snapshot
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir


class FrameTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "T01/a.md", "# A\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})

    def test_keret_kezi_elotte_gepi_utana(self):
        ir(self.v, "X01/nap.md", "a gazda írta\n")
        with frame.snapshot_frame(self.cfg, "lépés", "T01/a.md", "mos-lepes") as e:
            ir(self.v, "T01/a.md", "# A\ngépi\n")
            e["utak"] = ["T01/a.md"]
        log = self.repo.log(3)
        self.assertEqual(log[1].subject, "kézi változások a lépés előtt")
        self.assertEqual(log[1].trailers["Mos-Forras"], "kezi")
        self.assertEqual(log[0].sha, e["sha"])
        self.assertEqual(log[0].trailers["Mos-Forras"], "mos-lepes")
        self.assertTrue(e["kor"].startswith("LEPES-"))
        self.assertEqual(self.repo.changed_files(e["sha"]), ["T01/a.md"])
        self.repo.undo_run(e["kor"])
        self.assertEqual((self.v / "T01/a.md").read_text(encoding="utf-8"), "# A\n")
        self.assertEqual((self.v / "X01/nap.md").read_text(encoding="utf-8"), "a gazda írta\n")

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_keret_kulonleges_nevekkel(self):
        """M1 (audit): a lépés által írt különleges nevű fájlok mind a gépi commitba kerülnek, kivétel nélkül —
        a `git status` emberi kimenetének vágása a `" -> "`-t átnevezésnek, az idézőjelet a név részének vette."""
        import unicodedata
        nevek = ["T01/a -> b.md", "T01/tab\tnév.md", 'T01/idéz"őjel.md', "T01/Mi?.md",
                 "T01/" + unicodedata.normalize("NFD", "Öröklés.md")]
        with frame.snapshot_frame(self.cfg, "lépés", "T01", "mos-lepes") as e:
            for n in nevek:
                ir(self.v, n, "gépi\n")
            e["utak"] = self.repo.dirty_paths()
        self.assertEqual(sorted(self.repo.changed_files(e["sha"])),
                         sorted(unicodedata.normalize("NFC", n) for n in nevek))
        self.assertEqual(self.repo.dirty_paths(), [])
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "mos-lepes")

    def test_kor_azonosito_egyedi_utotagot_kap(self):
        """T095: két azonos másodpercben indult kör azonosítója nem eshet egybe (eddig `<ELŐTAG>-ÉÉÉÉHHNN-ÓÓPPMM`)."""
        idk = [frame.new_id("SZERK") for _ in range(300)]
        self.assertEqual(len(set(idk)), 300)
        for i in idk:
            self.assertRegex(i, r"^SZERK-\d{8}-\d{6}-[0-9a-f]{6}$")
            self.assertTrue(frame.KOR_MINTA.fullmatch(i))
        self.assertTrue(frame.KOR_MINTA.fullmatch("KARTYA-20261004-101500"))              # a régi alak is érvényes
        self.assertTrue(frame.KOR_MINTA.fullmatch("KARTYA-20261004-101500-ab3f-proba"))

    def test_foglalt_zar_varakozas_nelkul(self):
        lock = frame.lock_path(self.cfg)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            with self.assertRaises(frame.Busy):
                with frame.snapshot_frame(self.cfg, "x", "y", wait=False):
                    pass
            with frame.try_run_lock(self.cfg) as szabad:
                self.assertFalse(szabad)
        with frame.try_run_lock(self.cfg) as szabad:
            self.assertTrue(szabad)

    def _tart(self, mp: float):
        """A kör-zár egy másik leíróval `mp` másodpercig (mint a kör végi bundle a háttérszálon); → a szál és a „megfogva” jel."""
        import threading
        megfogva = threading.Event()

        def fut():
            with open(frame.lock_path(self.cfg), "a+") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                megfogva.set()
                threading.Event().wait(mp)
                fcntl.flock(fh, fcntl.LOCK_UN)
        frame.lock_path(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        sz = threading.Thread(target=fut, daemon=True)
        sz.start()
        self.assertTrue(megfogva.wait(5))
        self.addCleanup(sz.join, 5)
        return sz

    def test_turelem_kivarja_a_rovid_zar_tartast(self):
        """Mac-integráció (2026-10-07): a felhasználói művelet a rövid (bundle-) zár-tartást kivárja, nem 409."""
        sz = self._tart(0.3)
        with frame.run_lock(self.cfg, wait=False, turelem_mp=3.0):
            self.assertFalse(sz.is_alive())                       # a zárat csak a tartó elengedése után kaptuk meg

    def test_turelem_utan_busy(self):
        self._tart(1.0)
        with self.assertRaises(frame.Busy):
            with frame.run_lock(self.cfg, wait=False, turelem_mp=0.2):
                pass
        with self.assertRaises(frame.Busy):                       # türelem nélkül azonnal (a korábbi viselkedés)
            with frame.run_lock(self.cfg, wait=False):
                pass

    def test_felhasznaloi_turelem_a_configbol(self):
        self.assertEqual(frame.felhasznaloi_turelem(self.cfg), 3.0)

    def test_zar_tartalma_a_legacy_alakja(self):
        with frame.run_lock(self.cfg):
            self.assertRegex(frame.lock_path(self.cfg).read_text(), r"^pid \d+ · \d\d:\d\d:\d\d$")
        self.assertEqual(frame.lock_path(self.cfg).read_text(), "")

    def test_nem_elo_tarolo_kimarad(self):
        # a ytdlp munkafája (a C20-ig) nem létezik: a keret nem bukik el rajta
        self.assertEqual(list(frame.live_repos(self.cfg)), ["vault"])
        with frame.snapshot_frame(self.cfg, "x", "y") as e:
            ir(self.v, "T01/b.md", "# B\n")
            e["utak"] = ["T01/b.md"]
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Tetel"], "y")

    def test_feladat_trailer_az_env_szerint(self):
        """C17: a feladatsor lépése (MOS_FELADAT) a gépi commitba beírja a feladat azonosítóját; env nélkül nincs."""
        import os
        with frame.snapshot_frame(self.cfg, "kézi hívás", "x") as e:
            ir(self.v, "T01/b.md", "# B\n")
            e["utak"] = ["T01/b.md"]
        self.assertNotIn("Mos-Feladat", self.repo.log(1)[0].trailers)
        os.environ["MOS_FELADAT"] = "F-20261002-120000-1"
        self.addCleanup(os.environ.pop, "MOS_FELADAT", None)
        with frame.snapshot_frame(self.cfg, "feladat lépése", "y") as e:
            ir(self.v, "T01/c.md", "# C\n")
            e["utak"] = ["T01/c.md"]
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Feladat"], "F-20261002-120000-1")
        self.assertEqual(self.repo.log(1)[0].sha, e["sha"])

    def test_commit_fajlok_allapot_es_sorszam(self):
        (self.v / "T01" / "t.md").write_text("1\n2\n3\n", encoding="utf-8")
        self.repo.commit("t", {"Mos-Forras": "kezi"}, ["T01/t.md"])
        with frame.snapshot_frame(self.cfg, "vegyes", "z") as e:
            ir(self.v, "T01/a.md", "# A\nújabb sor\n")                  # módosítva: +1
            (self.v / "T01" / "t.md").unlink()                           # törölve: −3
            ir(self.v, "T01/uj.md", "x\ny\n")                           # új: +2
            e["utak"] = ["T01/a.md", "T01/t.md", "T01/uj.md"]
        f = {x["ut"]: x for x in self.repo.commit_fajlok(e["sha"])}
        self.assertEqual((f["T01/a.md"]["allapot"], f["T01/a.md"]["plusz"], f["T01/a.md"]["minusz"]), ("M", 1, 0))
        self.assertEqual((f["T01/t.md"]["allapot"], f["T01/t.md"]["plusz"], f["T01/t.md"]["minusz"]), ("D", 0, 3))
        self.assertEqual((f["T01/uj.md"]["allapot"], f["T01/uj.md"]["plusz"]), ("A", 2))
        self.assertEqual(len(f), 3)

    def test_utak_nelkul_nincs_gepi_commit(self):
        """T136 (C29.8): a keret nem tesz „minden piszkos utat” gépi commitba (L13 látens veszélye): a törzsnek meg kell nevezni
        az `utak` listát; hiányában hiba, gépi commit nincs, a fájl a felhasználó nem rögzített változása marad."""
        fej = self.repo.log(1)[0].sha
        with self.assertRaises(ValueError):
            with frame.snapshot_frame(self.cfg, "x", "y"):
                ir(self.v, "T01/b.md", "# B\n")                                  # útlista nélkül
        self.assertEqual(self.repo.log(1)[0].sha, fej)
        self.assertEqual(self.repo.dirty_paths(), ["T01/b.md"])

    def test_ures_utak_lista_nincs_commit_es_nem_hiba(self):
        with frame.snapshot_frame(self.cfg, "x", "y") as e:
            e["utak"] = []                                                          # „nincs mit commitolni” (ismétlés, változás nélküli tétel)
            ir(self.v, "T01/b.md", "# B\n")
        self.assertIsNone(e["sha"])
        self.assertEqual(self.repo.dirty_paths(), ["T01/b.md"])

    def test_csak_a_megnevezett_utak_kerulnek_a_gepi_commitba(self):
        with frame.snapshot_frame(self.cfg, "x", "y") as e:
            ir(self.v, "T01/b.md", "# B\n")
            ir(self.v, "T01/c.md", "# C\n")
            e["utak"] = ["T01/b.md"]
        self.assertEqual(self.repo.changed_files(e["sha"]), ["T01/b.md"])
        log = self.repo.log(2)                                                      # a másik fájl külön, „kézi” commitba kerül (L14)
        self.assertEqual((log[0].sha, log[1].trailers["Mos-Forras"]), (e["sha"], "kezi"))
        self.assertEqual(self.repo.changed_files(log[1].sha), ["T01/c.md"])

    def test_azonositok(self):
        self.assertRegex(frame.new_id("SZERK"), r"^SZERK-\d{8}-\d{6}-[0-9a-f]{6}$")
        a, b = frame.new_id("F"), frame.new_id("F")
        self.assertRegex(a, r"^F-\d{8}-\d{6}-\d+$")
        self.assertNotEqual(a, b)

    @csak_darwin("APFS-klón (`cp -c`)")
    def test_a_probaklon_jelet_kap_a_valodi_tarolo_nem(self):
        """A2-iras-7: a klón git-configjában `mos.klon = 1`; a valódi tárolóéban nincs (a mentés ebből tudja)."""
        import subprocess
        klon = self.root.parent / "klon"
        vault, git = frame.trial_clone(self.cfg, klon)
        jel = lambda g: subprocess.run(["git", "--git-dir", str(g), "config", "--get", "mos.klon"],  # noqa: E731
                                        capture_output=True, text=True).stdout.strip()
        self.assertEqual(jel(git), "1")
        self.assertEqual(jel(self.repo.git_dir), "")

    def test_vault_letezik_csak_obsidian_mappaval(self):
        """T002 (2. audit): az indulási helyreállítás csak valódi vaulton futhat. A vault attól vault, hogy van
        `.obsidian` mappája; a nem létező (munkafában az `{os}/../Manifold`) vagy a puszta üres mappa nem az."""
        self.assertTrue(frame.vault_letezik(self.cfg))
        (self.v / ".obsidian").rmdir()
        self.assertFalse(frame.vault_letezik(self.cfg), "üres mappa, .obsidian nélkül")
        elmozgatva = self.v.with_name("Manifold-elmozgatva")
        self.v.rename(elmozgatva)
        self.assertFalse(frame.vault_letezik(self.cfg), "nem létező vault")


class FeladatnaploTakaritasTest(unittest.TestCase):
    """Lelet 13: a `{runs}/feladatok` naplói kor-/darabszám-alapon takarulnak; az `eval` riportjai és minden más fájl marad."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.mappa = self.cfg.path("runs") / "feladatok"
        self.mappa.mkdir(parents=True)
        self.most = 1_800_000_000.0

    def fajl(self, nev, kor_nap, mappa=None, most=None):
        import os
        p = (mappa or self.mappa) / nev
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        t = (self.most if most is None else most) - kor_nap * 86400
        os.utime(p, (t, t))
        return p

    def nevek(self):
        return sorted(p.name for p in self.mappa.iterdir())

    def test_a_regi_naplo_torlodik_a_friss_marad_az_eval_erintetlen(self):
        regi, friss = self.fajl("F-regi.log", 61), self.fajl("F-friss.log", 59)
        eval_riport = self.fajl("riport.json", 400, self.cfg.path("runs") / "eval" / "qwen35_9b")
        masik = self.fajl("jegyzet.txt", 400)                           # nem .log/.stop: nem érintjük
        self.assertEqual(frame.feladatnaplo_takaritas(self.cfg, self.most), 1)
        self.assertFalse(regi.exists())
        self.assertTrue(friss.exists() and eval_riport.exists() and masik.exists())

    def test_a_darabszam_fole_a_legregebbiek_torlodnek_de_az_egy_napnal_frissebb_nem(self):
        for i in range(8):
            self.fajl(f"F-{i}.log", 2 + i)                              # 2..9 napos
        self.fajl("F-uj1.log", 0.2)
        self.fajl("F-uj2.log", 0.5)
        torolt = frame.feladatnaplo_takaritas(self.cfg, self.most, max_db=4)
        self.assertEqual(torolt, 6)                                     # 10 napló − 4 megtartott
        self.assertEqual(self.nevek(), ["F-0.log", "F-1.log", "F-uj1.log", "F-uj2.log"])
        for i in range(6):                                              # a plafon fölött is marad, ami egy napnál frissebb
            self.fajl(f"G-{i}.log", 0.1)
        self.assertEqual(frame.feladatnaplo_takaritas(self.cfg, self.most, max_db=4), 2)     # csak a két egy napnál régebbi esik ki
        self.assertEqual(self.nevek(), sorted(["F-uj1.log", "F-uj2.log"] + [f"G-{i}.log" for i in range(6)]))

    def test_a_konfig_kulcsai_az_os_tomlban_vannak(self):
        sec = self.cfg.section("feladatsor")
        self.assertEqual((sec["naplo_max_nap"], sec["naplo_max_db"]), (frame.FELADATNAPLO_MAX_NAP, frame.FELADATNAPLO_MAX_DB))

    def test_a_lemaradt_stop_jelzo_egy_nap_utan_torlodik_a_symlink_es_az_almappa_nem(self):
        import os
        regi_stop, uj_stop = self.fajl("F-a.stop", 2), self.fajl("F-b.stop", 0.1)
        cel = self.fajl("cel.log", 400, self.cfg.path("runs") / "mas")
        os.symlink(cel, self.mappa / "link.log")
        (self.mappa / "alm.log").mkdir()
        self.assertEqual(frame.feladatnaplo_takaritas(self.cfg, self.most), 1)
        self.assertFalse(regi_stop.exists())
        self.assertTrue(uj_stop.exists() and cel.exists() and (self.mappa / "link.log").is_symlink() and (self.mappa / "alm.log").is_dir())

    def test_hianyzo_mappa_nem_hiba(self):
        import shutil
        shutil.rmtree(self.mappa)
        self.assertEqual(frame.feladatnaplo_takaritas(self.cfg), 0)

    def test_a_feladatsor_indulasakor_takarit(self):
        import time
        from core import tasks
        most = time.time()
        regi, friss = self.fajl("F-regi.log", 90, most=most), self.fajl("F-friss.log", 1, most=most)
        q = tasks.Queue(self.cfg, publish=lambda e, **k: None)
        self.addCleanup(q.close)
        self.assertFalse(regi.exists())
        self.assertTrue(friss.exists())


if __name__ == "__main__":
    unittest.main()
