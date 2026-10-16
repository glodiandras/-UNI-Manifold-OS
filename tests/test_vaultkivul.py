"""A3-27: a „nem a vaultba” őr fájlrendszer-azonosság alapján, kis-nagybetű-érzéketlen fájlrendszeren is."""
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import tmpdir


def _apfs_samefile(a, b):
    """Kis-nagybetű-érzéketlen fájlrendszer: ugyanaz a mappa, ha a két út kisbetűsítve egyezik."""
    return str(a).casefold() == str(b).casefold()


class VaultkivulTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.gyoker = Path(self._t.name)
        self.vault = self.gyoker / "Manifold"
        (self.vault / "A").mkdir(parents=True)
        (self.gyoker / "kint").mkdir()

    def test_szoveg_szerinti_belso_es_kulso(self):
        from core.vaultkivul import vaultban_van
        self.assertTrue(vaultban_van(self.vault / "A" / "uj" / "r.md", self.vault))
        self.assertTrue(vaultban_van(self.vault, self.vault))
        self.assertFalse(vaultban_van(self.gyoker / "kint" / "r.md", self.vault))
        self.assertFalse(vaultban_van(self.gyoker / "Manifold-mas" / "r.md", self.vault))

    def test_kis_nagybetu_erzekeny_apfs_szimulacio(self):
        """APFS: `…/manifold/…` ugyanaz a mappa; a szimulált `samefile` kis-nagybetűt nem különböztet meg."""
        from core import vaultkivul

        cel = self.gyoker / "manifold" / "A" / "riport.md"
        self.assertFalse(cel.is_relative_to(self.vault.resolve()))             # a szöveges őr átengedné
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile):
            self.assertTrue(vaultkivul.vaultban_van(cel, self.vault))
            self.assertFalse(vaultkivul.vaultban_van(self.gyoker / "kint" / "r.md", self.vault))

    def test_symlinkelt_ut(self):
        from core.vaultkivul import vaultban_van
        (self.gyoker / "alias").symlink_to(self.vault)
        self.assertTrue(vaultban_van(self.gyoker / "alias" / "r.md", self.vault))

    def test_nem_letezo_vault_ut_zarva_hibazik(self):
        """K179: ha a vault-út nem oldható fel, az őr tilt (igaz), nem enged át."""
        from core.vaultkivul import vaultban_van
        self.assertTrue(vaultban_van(self.gyoker / "kint" / "r.md", self.gyoker / "nincs-ilyen-vault"))

    def test_eltavolitott_vault_konyvtar_zarva_hibazik(self):
        """K179 (a megfigyelt eset): a vault könyvtárát a futás közben eltávolították; a kisbetűs úttal a cél ma sem juthat át."""
        import shutil
        from core.vaultkivul import vaultban_van
        shutil.rmtree(self.vault)
        self.assertTrue(vaultban_van(self.gyoker / "manifold" / "A" / "r.md", self.vault))
        self.assertTrue(vaultban_van(self.gyoker / "kint" / "r.md", self.vault))

    def test_a_vault_eltunese_az_osszevetes_kozben_zarva_hibazik(self):
        """K179: a vault létezik a vizsgálat elején, de a `samefile` `OSError`-t ad egy létező őssel: tiltás."""
        from core import vaultkivul
        with mock.patch.object(vaultkivul.os.path, "samefile", side_effect=FileNotFoundError("a vault eltűnt")):
            self.assertTrue(vaultkivul.vaultban_van(self.gyoker / "kint" / "r.md", self.vault))

    def test_nem_letezo_osoknel_tovabb_lep_es_kivul_marad(self):
        """A csak a CÉL ősei nem léteznek (új mappa a vaulton kívül): ez nem hiba, a cél kívül van."""
        from core.vaultkivul import vaultban_van
        self.assertFalse(vaultban_van(self.gyoker / "kint" / "uj" / "meg-ujabb" / "r.md", self.vault))

    def test_kisbetus_ut_letezo_vaulttal_apfs_szimulacio_es_nem_letezo_vaulttal(self):
        from core import vaultkivul
        cel = self.gyoker / "manifold" / "A" / "r.md"
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile):
            self.assertTrue(vaultkivul.vaultban_van(cel, self.vault))
        import shutil
        shutil.rmtree(self.vault)
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile):
            self.assertTrue(vaultkivul.vaultban_van(cel, self.vault))

    def test_symlinkelt_vault_es_symlinkelt_cel(self):
        from core.vaultkivul import vaultban_van
        (self.gyoker / "alias").symlink_to(self.vault)
        self.assertTrue(vaultban_van(self.vault / "A" / "r.md", self.gyoker / "alias"))         # a vault maga a symlink
        (self.gyoker / "kint" / "be").symlink_to(self.vault)
        self.assertTrue(vaultban_van(self.gyoker / "kint" / "be" / "uj" / "r.md", self.vault))  # a cél symlinkjén át a vaultba
        self.assertFalse(vaultban_van(self.gyoker / "kint" / "ki.md", self.gyoker / "alias"))

    def test_hibas_bemenet_zarva_hibazik(self):
        from core.vaultkivul import vaultban_van
        self.assertTrue(vaultban_van(self.gyoker / "kint" / "r.md", "\0nem-ut"))
        self.assertTrue(vaultban_van(self.gyoker / "kint" / "r.md", None))


class KapuCliTest(unittest.TestCase):
    def test_kiir_vaultba_tilos_kis_nagybetuvel_is(self):
        from core import vaultkivul
        from modulok.kapuk import __main__ as m
        t = tmpdir()
        self.addCleanup(t.cleanup)
        vault = Path(t.name) / "Manifold"
        vault.mkdir()
        cfg = mock.Mock()
        cfg.path.return_value = vault
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile):
            with self.assertRaises(SystemExit):
                m._kiir("x", str(Path(t.name) / "manifold" / "riport.md"), cfg)
        self.assertFalse((vault / "riport.md").exists())

    def test_kartya_export_vaultba_tilos_kis_nagybetuvel_is(self):
        from core import vaultkivul
        from modulok.kartya import __main__ as m
        t = tmpdir()
        self.addCleanup(t.cleanup)
        vault = Path(t.name) / "Manifold"
        vault.mkdir()
        cfg = mock.Mock()
        cfg.path.return_value = vault
        a = mock.Mock(cel=str(Path(t.name) / "manifold" / "k.apkg"))
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile), \
                mock.patch.object(m.apkg, "gyujt", return_value=[]), mock.patch.object(m.apkg, "export") as ex:
            self.assertEqual(m.exportal(cfg, a), 2)
        ex.assert_not_called()



class ManifoldAllapotTest(unittest.TestCase):
    """F3 (§3.6): a munkatér állapota (`<vault>/.manifold/var`, a termék `{var}`-ja) nem vault-tartalom — a kártya-export
    alapcélja (`{szemelyes}/export`) írható; minden más (a `.manifold` többi része, symlinkelt állapot, eltűnt vault) tiltott."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.vault = self.t / "Vault"
        (self.vault / ".manifold" / "var" / "szemelyes").mkdir(parents=True)
        (self.vault / "Jegyzetek").mkdir()

    def test_az_allapot_alatt_kivul_mashol_belul(self):
        from core.vaultkivul import vaultban_van
        allapot = self.vault / ".manifold" / "var"
        self.assertFalse(vaultban_van(allapot / "szemelyes" / "export" / "k.apkg", self.vault))   # még nem létező mappák
        self.assertFalse(vaultban_van(allapot, self.vault))
        self.assertTrue(vaultban_van(self.vault / ".manifold" / "workspace.toml", self.vault))
        self.assertTrue(vaultban_van(self.vault / ".manifold" / "varx" / "k.apkg", self.vault))
        self.assertTrue(vaultban_van(allapot / ".." / "workspace.toml", self.vault))
        self.assertTrue(vaultban_van(self.vault / "Jegyzetek" / "k.apkg", self.vault))
        self.assertTrue(vaultban_van(allapot / "k.apkg", self.t / "nincs"))                    # zárva hibázik
        (self.vault / ".manifold" / "var" / "szemelyes").rmdir()
        (self.vault / ".manifold" / "var").rmdir()                         # munkatér-állapot nélkül (hordozható): nincs kivétel
        self.assertTrue(vaultban_van(allapot / "szemelyes" / "export" / "k.apkg", self.vault))

    def test_kis_nagybetus_iras_az_allapotra_is_kivul(self):
        from core import vaultkivul
        with mock.patch.object(vaultkivul.os.path, "samefile", _apfs_samefile):
            self.assertFalse(vaultkivul.vaultban_van(self.vault / ".MANIFOLD" / "VAR" / "szemelyes" / "k.apkg", self.vault))
            self.assertTrue(vaultkivul.vaultban_van(self.vault / ".MANIFOLD" / "k.apkg", self.vault))

    def test_symlinkelt_allapot_nem_kivetel(self):
        from core.vaultkivul import vaultban_van
        v = self.t / "Idegen"
        (v / "Jegyzetek").mkdir(parents=True)
        (v / ".manifold").mkdir()
        (v / ".manifold" / "var").symlink_to(v / "Jegyzetek")             # egy letöltött vault a jegyzetei közé irányítana
        self.assertTrue(vaultban_van(v / ".manifold" / "var" / "k.apkg", v))
        (v / ".manifold" / "var").unlink()
        kint = self.t / "kint"
        kint.mkdir()
        (v / ".manifold" / "var").symlink_to(kint)
        self.assertFalse(vaultban_van(v / ".manifold" / "var" / "k.apkg", v))   # a feloldott cél a vaulton kívül van

    def test_termekben_a_kartya_export_alapcelja_engedett(self):
        from core import workspace
        from modulok.kartya import __main__ as m
        from tests.fresh_install import termek_alap, termek_cfg
        root, home, alap = termek_alap(str(self.t / "t"))
        v = self.t / "Munkater"
        (v / ".obsidian").mkdir(parents=True)
        workspace.letrehoz(v, alap)
        cfg = termek_cfg(root, home, v)
        self.assertTrue(str(cfg.path("szemelyes")).startswith(str(v / ".manifold" / "var")))
        with mock.patch.object(m.apkg, "gyujt", return_value=[]), \
                mock.patch.object(m.apkg, "export", return_value={"kartya": 0}) as ex, \
                mock.patch.object(m, "_kiir"):
            self.assertEqual(m.exportal(cfg, mock.Mock(cel=None)), 0)
        cel = ex.call_args.args[0]
        self.assertEqual(cel.parent, cfg.path("szemelyes") / "export")
        # a teljes mentés célja a `.manifold` alatt továbbra is tiltott (a saját gyökér-ellenőrzése)
        from core import teljes_mentes
        cel = v / ".manifold" / "var" / "mentes"
        cel.mkdir()
        with self.assertRaisesRegex(teljes_mentes.MentesHiba, "nem lehet"):     # a cél-szabály, nem a kötet-szabály
            teljes_mentes.ment(cfg, cel, log=lambda *a, **k: None)


if __name__ == "__main__":
    unittest.main()
