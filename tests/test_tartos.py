"""A tartós fájlírás (`core/tartos.py`, C29.6; 2. audit T026, T025; az 1. audit M5 része): `F_FULLFSYNC` a fájlra és a
szülőmappára, kizáró létrehozás (`renamex_np` + `RENAME_EXCL`), a fájl születési idejének megőrzése a cserénél."""
import fcntl
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from core import tartos, vaultio
from tests import csak_darwin
from tests.helpers import alg_core, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name) / "mappa"
        self.d.mkdir()

    def maradek(self):
        return [p.name for p in self.d.iterdir() if p.name.endswith(tartos.TMP_UTOTAG)]


class TartosIrasTest(Alap):
    def _fcntl_figyelve(self):
        hivasok = []
        eredeti = fcntl.fcntl

        def figyel(fd, cmd, *a):
            if cmd == getattr(fcntl, "F_FULLFSYNC", None):
                hivasok.append(os.fstat(fd).st_mode)
            return eredeti(fd, cmd, *a)

        return hivasok, mock.patch("core.tartos.fcntl.fcntl", side_effect=figyel)

    @csak_darwin("F_FULLFSYNC (macOS-specifikus fcntl)")
    def test_a_fajl_es_a_szulomappa_is_full_fsync(self):
        """T026: az `os.fsync` macOS-en nem üríti a lemez gyorsítótárát; a mentés `F_FULLFSYNC`-et kér a tmp fájlra ÉS a
        szülőmappára (a csere bejegyzése is tartós)."""
        import stat
        hivasok, patch = self._fcntl_figyelve()
        with patch:
            tartos.atomi_ir(self.d / "a.md", b"szoveg")
        self.assertEqual((self.d / "a.md").read_bytes(), b"szoveg")
        self.assertTrue(any(stat.S_ISREG(m) for m in hivasok), hivasok)
        self.assertTrue(any(stat.S_ISDIR(m) for m in hivasok), hivasok)
        self.assertEqual(self.maradek(), [])

    def test_full_fsync_hianyaban_tartalek_fsync(self):
        """Ha a kötet nem támogatja (`ENOTSUP`), az `os.fsync` a tartalék: az írás nem hibázik."""
        with mock.patch("core.tartos.fcntl.fcntl", side_effect=OSError(45, "Operation not supported")):
            tartos.atomi_ir(self.d / "a.md", b"x")
        self.assertEqual((self.d / "a.md").read_bytes(), b"x")

    def test_ellenorzes_kivetelere_a_fajl_erintetlen_es_nincs_tmp(self):
        (self.d / "a.md").write_bytes(b"regi")

        def nem():
            raise RuntimeError("megváltozott")

        with self.assertRaises(RuntimeError):
            tartos.atomi_ir(self.d / "a.md", b"uj", nem)
        self.assertEqual((self.d / "a.md").read_bytes(), b"regi")
        self.assertEqual(self.maradek(), [])


class KizaroIrasTest(Alap):
    def test_uj_fajl_teljes_tartalommal_jon_letre(self):
        tartos.kizaro_ir(self.d / "uj.md", b"tartalom")
        self.assertEqual((self.d / "uj.md").read_bytes(), b"tartalom")
        self.assertEqual(self.maradek(), [])

    def test_meglevo_fajlt_nem_ir_felul_es_nem_hagy_tmp_t(self):
        (self.d / "van.md").write_bytes(b"a felhasznalo irta")
        with self.assertRaises(FileExistsError):
            tartos.kizaro_ir(self.d / "van.md", b"gep")
        self.assertEqual((self.d / "van.md").read_bytes(), b"a felhasznalo irta")
        self.assertEqual(self.maradek(), [])

    def test_rename_excl_fajlra_es_mappara(self):
        (self.d / "a.md").write_bytes(b"a")
        (self.d / "b.md").write_bytes(b"b")
        with self.assertRaises(FileExistsError):
            tartos.rename_excl(self.d / "a.md", self.d / "b.md")
        self.assertEqual((self.d / "a.md").read_bytes(), b"a")
        self.assertEqual((self.d / "b.md").read_bytes(), b"b")
        tartos.rename_excl(self.d / "a.md", self.d / "c.md")
        self.assertFalse((self.d / "a.md").exists())
        (self.d / "m1").mkdir()
        (self.d / "m2").mkdir()
        with self.assertRaises(FileExistsError):
            tartos.rename_excl(self.d / "m1", self.d / "m2")
        tartos.rename_excl(self.d / "m1", self.d / "m3")
        self.assertTrue((self.d / "m3").is_dir())

    def test_rename_excl_nem_letezo_forras(self):
        with self.assertRaises(FileNotFoundError):
            tartos.rename_excl(self.d / "nincs", self.d / "x")

    def test_rename_excl_nfd_nev(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", "Öröklés.md")
        (self.d / nfd).write_bytes(b"x")
        tartos.rename_excl(self.d / nfd, self.d / "Új név.md")
        self.assertEqual((self.d / "Új név.md").read_bytes(), b"x")


class SzuletesiIdoTest(Alap):
    """T025: a csere új inode-ot ad; a születési idő (`st_birthtime`, a Bases `file.ctime`-ja, az Obsidian „Created
    time”) ettől nem változhat. A macOS a `utime`-mal a születési időnél korábbi mtime-ra húzza vissza a crtime-ot."""

    def setUp(self):
        super().setUp()
        if not hasattr(os.stat_result, "st_birthtime"):
            self.skipTest("[indokolt] nincs st_birthtime ezen a rendszeren")

    def test_a_csere_megorzi_a_szuletesi_idot(self):
        p = self.d / "a.md"
        p.write_bytes(b"elso")
        elotte = os.stat(p)
        time.sleep(1.1)
        tartos.atomi_ir(p, b"masodik")
        utana = os.stat(p)
        self.assertEqual(p.read_bytes(), b"masodik")
        self.assertAlmostEqual(utana.st_birthtime, elotte.st_birthtime, delta=1e-5)
        self.assertGreater(utana.st_mtime, elotte.st_mtime)               # a tartalom ideje az új
        self.assertGreaterEqual(utana.st_mtime, utana.st_birthtime)

    def test_ketto_csere_utan_is_az_eredeti_szuletesi_ido(self):
        p = self.d / "a.md"
        p.write_bytes(b"1")
        b0 = os.stat(p).st_birthtime
        time.sleep(1.05)
        tartos.atomi_ir(p, b"2")
        time.sleep(1.05)
        tartos.atomi_ir(p, b"3")
        self.assertAlmostEqual(os.stat(p).st_birthtime, b0, delta=1e-5)

    def test_uj_fajlnal_nincs_mit_orizni(self):
        p = self.d / "uj.md"
        tartos.atomi_ir(p, b"x")
        self.assertEqual(p.read_bytes(), b"x")

    def test_a_vaultio_atomi_csere_ugyanezt_adja(self):
        p = self.d / "v.md"
        p.write_bytes(b"1")
        b0 = os.stat(p).st_birthtime
        time.sleep(1.05)
        vaultio.atomi_csere(p, b"2")
        self.assertAlmostEqual(os.stat(p).st_birthtime, b0, delta=1e-5)


class VaultCreateTest(unittest.TestCase):
    """A `Vault.create` kizáró, tartós létrehozása (T026): kivétel után nincs csonka fájl, meglévőt nem ír felül."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.V = vaultio.Vault(self.cfg)

    def test_create_teljes_tartalmat_ad_es_nincs_tmp(self):
        r = self.V.create({"mappa": "", "nev": "Új"})
        self.assertEqual((self.v / "Új.md").read_text(encoding="utf-8"), "# Új\n")
        self.assertEqual(r["ut"], "Új.md")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))

    def test_create_kozben_letrejott_fajlt_nem_ir_felul(self):
        eredeti = tartos.kizaro_ir

        def versenyez(p, b):
            Path(p).write_text("közben jött létre", encoding="utf-8")
            return eredeti(p, b)

        with mock.patch("core.vaultio.tartos.kizaro_ir", side_effect=versenyez):
            with self.assertRaises(vaultio.Invalid):
                self.V.create({"mappa": "", "nev": "Verseny"})
        self.assertEqual((self.v / "Verseny.md").read_text(encoding="utf-8"), "közben jött létre")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))


if __name__ == "__main__":
    unittest.main()
