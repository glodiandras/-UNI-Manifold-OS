"""Összeomlás-forgatókönyvek (C29.6, 2. audit T193): a vault-író művelet megölése minden lépéshatáron, utána
`App.indulas()` — a vault az „előtte” vagy a „teljesen utána” állapotban áll, nincs napló, nincs ideiglenes fájl, a
pillanatkép-tároló tiszta és ép. Az állvány: `tests/osszeomlas.py`; a horgok: `core/osszeomlas.py`."""
import unittest

from core import mentes
from tests import osszeomlas as o
from tests.helpers import tmpdir

# a referencia („teljesen utána”) állapot műveletenként, egyszer számolva
_UTANA: dict[str, dict] = {}


def utana(muvelet: str) -> dict:
    if muvelet not in _UTANA:
        with tmpdir() as t:
            a = o.Allvany(t)
            p = a.futtat(muvelet)
            assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-2000:]
            _UTANA[muvelet] = o.lenyomat(a.v)
    return _UTANA[muvelet]


class AllvanyTest(unittest.TestCase):
    def test_a_horog_nelkul_a_muvelet_vegigfut(self):
        for muvelet in (m for m in o.PONTOK if m not in ("mentes", "visszavonas")):   # a mentés a vaultot nem változtatja; a visszavonás visszaáll
            with self.subTest(muvelet=muvelet), tmpdir() as t:
                a = o.Allvany(t)
                self.assertNotEqual(utana(muvelet), a.elotte, "a referencia-futás semmit nem változtatott")

    def test_a_pont_valoban_megoli_a_folyamatot(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            p = a.futtat("gepi", "gepi.naplo_kesz")
            self.assertEqual(p.returncode, 137, p.stderr.decode("utf-8", "replace")[-1500:])
            self.assertTrue((a.cfg.path("run") / "gepi-iras" / "terv.json").is_file())     # a napló az első írás előtt kész


class PontonkentTest(unittest.TestCase):
    """Minden művelet minden pontján: kill → indulás → invariánsok."""

    def _kill(self, muvelet: str, pont: str):
        with tmpdir() as t:
            a = o.Allvany(t)
            p = a.futtat(muvelet, pont)
            self.assertEqual(p.returncode, 137, f"a(z) {pont} pont nem teljesült: {p.stderr.decode('utf-8', 'replace')[-1500:]}")
            a.indulas()
            vart = utana(muvelet) if pont in o.UTANA_PONTOK else a.elotte
            a.invariansok(self, vart, kor_commit=pont in o.UTANA_PONTOK if muvelet == "gepi" else None)
            self.assertEqual(a.indulas(), [], "a második indulásnak már nincs mit javítania")

    def test_gepi_tetel(self):
        for pont in o.PONTOK["gepi"]:
            with self.subTest(pont=pont):
                self._kill("gepi", pont)

    def test_atnevezes(self):
        for pont in o.PONTOK["atnevezes"]:
            with self.subTest(pont=pont):
                self._kill("atnevezes", pont)

    def test_atomi_csere_tmp_maradeka_az_indulasnal_eltunik(self):
        """T101: a `csere_elott` kill a kész tmp fájlt hagyja a vaultban (a fájl érintetlen); az indulás takarít. A
        `csere_utan` kill a már lecserélt fájlt hagyja: nincs napló, a tartalom a teljes új."""
        with tmpdir() as t:
            a = o.Allvany(t)
            p = a.futtat("atomi", "atomi.csere_elott")
            self.assertEqual(p.returncode, 137, p.stderr.decode("utf-8", "replace")[-1500:])
            self.assertEqual(len(a.tmp_maradek()), 1, "a kill után a tmp fájl ott marad")
            self.assertEqual({k: v for k, v in o.lenyomat(a.v).items() if not k.endswith(".manifold-tmp")}, a.elotte)
            uzenetek = a.indulas()
            self.assertTrue(any("ideiglenes fájl" in u for u in uzenetek), uzenetek)
            a.invariansok(self, a.elotte)
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("atomi", "atomi.csere_utan").returncode, 137)
            a.indulas()
            vart = dict(a.elotte)
            vart["T01/a.md"] = b"uj tartalom\n"
            a.invariansok(self, vart, tiszta_tar=False)       # a kész csere még nincs commitban: a gazda munkája

    def test_visszavonas(self):
        """T020: a visszavonás az alkalmazás és a commit között meghal → az indulás visszagörgeti (a gépi commit utáni
        állapot); a commit után meghal → csak a napló törlődik (a visszavont állapot marad)."""
        for pont in o.PONTOK["visszavonas"]:
            with self.subTest(pont=pont), tmpdir() as t:
                a = o.Allvany(t)
                p = a.futtat("visszavonas", pont)
                self.assertEqual(p.returncode, 137, f"a(z) {pont} pont nem teljesült: {p.stderr.decode('utf-8', 'replace')[-1500:]}")
                a.indulas()
                vart = dict(a.elotte)
                if pont == "visszavonas.apply_utan":
                    vart["T01/a.md"] = a.elotte["T01/a.md"] + o.GEPI_SOR          # a visszavonás nem történt meg
                a.invariansok(self, vart)
                self.assertEqual(a.indulas(), [])

    def test_visszaallitas_egy_verziora(self):
        for pont in o.PONTOK["visszaallit"]:
            with self.subTest(pont=pont), tmpdir() as t:
                a = o.Allvany(t)
                p = a.futtat("visszaallit", pont)
                self.assertEqual(p.returncode, 137, f"a(z) {pont} pont nem teljesült: {p.stderr.decode('utf-8', 'replace')[-1500:]}")
                a.indulas()
                vart = dict(a.elotte)
                alap = a.elotte["T01/a.md"]
                vart["T01/a.md"] = alap + o.GEPI_SOR + (o.V2_SOR if pont == "visszavonas.apply_utan" else b"")
                a.invariansok(self, vart)

    def test_mappa_atnevezes(self):
        for pont in o.PONTOK["mappa"]:
            with self.subTest(pont=pont):
                self._kill("mappa", pont)


class MentesKillTest(unittest.TestCase):
    """A belső lemezes mentés megölése: soha nem marad csonka `.bundle` vagy félkész állapotmappa; a következő mentés
    befejezi és takarít (C29.6, T023/K44)."""

    def test_bundle_tmp_pontnal_nincs_csonka_bundle_a_kovetkezo_mentes_bepotolja(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("mentes", "mentes.bundle_tmp").returncode, 137)
            backup = a.cfg.path("backup")
            self.assertEqual(sorted(backup.glob("vault-*.bundle")), [], "csonka .bundle maradt")
            self.assertEqual(len(list(backup.glob("vault-*.bundle.tmp"))), 1)
            self.assertFalse(mentes.friss(a.repo, backup), "a megszakadt mentés után a bundle nem lehet „friss”")
            a.indulas()                                                     # az indulás nem érinti a mentéseket
            self.assertEqual(len(a.tmp_maradek()), 0)
            ki = mentes.ment(a.cfg, csak_ha_valtozott=True)
            self.assertEqual(len(list(backup.glob("vault-*.bundle"))), 1)
            self.assertEqual(list(backup.glob("*.tmp")), [])
            self.assertTrue(mentes.friss(a.repo, backup))
            self.assertTrue(any(p.name.startswith("mos-allapot-") for p in ki))

    def test_allapot_fele_pontnal_nincs_felkesz_allapotmappa(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("mentes", "mentes.allapot_fele").returncode, 137)
            backup = a.cfg.path("backup")
            self.assertEqual(len(list(backup.glob("vault-*.bundle"))), 1)    # a vault bundle-je már kész volt
            self.assertEqual([p.name for p in backup.glob("mos-allapot-*") if not p.name.endswith(".tmp")], [])
            self.assertEqual(len(list(backup.glob("mos-allapot-*.tmp"))), 1)
            self.assertFalse(mentes.allapot_friss(a.cfg, backup))
            mentes.ment(a.cfg, csak_ha_valtozott=True)
            self.assertEqual(list(backup.glob("*.tmp")), [])
            self.assertTrue(mentes.allapot_friss(a.cfg, backup))
            mappa = mentes.utolso_allapot(backup)
            self.assertTrue((mappa / "router.sqlite").is_file() and (mappa / "state/felulet.json").is_file())


if __name__ == "__main__":
    unittest.main()
