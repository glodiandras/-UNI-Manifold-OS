"""F5 options reach their real consumers without changing imported Obsidian files."""
import json
import unittest

from core import config, csatolmany, gyokerek, naptar, termek_beallitasok as b, vaultio
from core.index import feloldas, linkek
from core.utvonalak import HttpError
from tests.helpers import tmpdir
from tests.multi_user import munkater, termek_cfg, termek_telepites


class BeallitasFogyasztoTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, self.id = munkater(self.t.name, "Notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)

    def ment(self, d):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], d)

    def test_fajl_opciok_elve_valtoznak_es_az_obsidian_bajtok_megmaradnak(self):
        p = self.v / ".obsidian/app.json"
        p.write_text(json.dumps({"newFileLocation": "current", "attachmentFolderPath": "./Old"}))
        eredeti = p.read_bytes()
        v = vaultio.Vault(self.cfg)
        self.assertEqual(v.uj_fajl_beallitas()[0], "current")
        self.assertEqual(csatolmany.mappa(self.v, "A/Note.md", self.cfg), "A/Old")
        self.ment({"fajlok": {"uj_mappa": "Drafts/Missing", "csatolmany_mappa": "./Assets"}})
        self.assertEqual(v.link_jegyzet_helye("New", "A/Note.md"),
                         {"mappa": "Drafts/Missing", "nev": "New", "mappa_keszit": True})
        self.assertEqual(csatolmany.mappa(self.v, "A/Note.md", self.cfg), "A/Assets")
        (self.v / "A").mkdir()
        self.ment({"fajlok": {"uj_mappa": ".", "csatolmany_mappa": ""}})
        self.assertEqual(v.link_jegyzet_helye("New", "A/Note.md"), {"mappa": "A", "nev": "New"})
        self.assertEqual(csatolmany.mappa(self.v, "A/Note.md", self.cfg), "")
        self.ment({"fajlok": {"uj_mappa": ""}})
        self.assertEqual(v.link_jegyzet_helye("New", "A/Note.md"), {"mappa": "", "nev": "New"})
        self.assertEqual(p.read_bytes(), eredeti)

    def test_naptar_kulon_engedely_utan_es_modultiltasra_megall(self):
        self.assertFalse(naptar.beallitasok(self.cfg)["automatikus"])
        self.ment({"adatvedelem": {"naptar": True}})
        self.assertTrue(naptar.beallitasok(self.cfg)["automatikus"])
        self.ment({"modulok": {"naptar": False}})
        self.assertFalse(naptar.beallitasok(self.cfg)["automatikus"])

    def test_hianyzo_relativ_jegyzet_helye_es_kilepes_tiltasa(self):
        v = vaultio.Vault(self.cfg)
        self.assertEqual(v.link_jegyzet_helye("./New", "Dir/Source.md"),
                         {"mappa": "Dir", "nev": "New", "mappa_keszit": True})
        self.assertEqual(v.link_jegyzet_helye("../Other/New", "Dir/Source.md"),
                         {"mappa": "Other", "nev": "New", "mappa_keszit": True})
        self.ment({"fajlok": {"uj_mappa": "Drafts"}})
        self.assertEqual(v.link_jegyzet_helye("../New.md", "Dir/Source.md"), {"mappa": "", "nev": "New"})
        for cel in ("../../Outside/New", "../.manifold/Hidden", "./.obsidian/Hidden"):
            with self.subTest(cel=cel), self.assertRaises(vaultio.Invalid):
                v.link_jegyzet_helye(cel, "Dir/Source.md")

    def test_valaszto_uj_munkaterhez_nem_orokol_regi_folyamat_utakat(self):
        masik, masik_id = munkater(self.t.name, "Other")
        e = {"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_SETTINGS": ""}
        gyokerek.rogzit(self.cfg, e)
        e.update(MOS_VAULT=str(masik), MOS_MUNKATER_VALTAS="1")
        uj = config.load(e)
        self.assertEqual(uj.workspace_id, masik_id)
        for k in ("var", "state", "run", "index", "backup"):
            self.assertNotEqual(uj.path(k), self.cfg.path(k), k)
        self.assertEqual(uj.path("models"), self.cfg.path("models"))
        self.assertEqual(uj.path("install_run"), self.cfg.path("install_run"))

    def test_hibas_vagy_foglalt_billentyu_nem_mentheto(self):
        for akkord in ("Mod+wat", "Strange+x", "x", "Shift+x", "Mod+", "Cmd+,", "Mod+Shift+O"):
            with self.subTest(akkord=akkord), self.assertRaises(HttpError):
                b.ellenoriz({"billentyuk": {"szerkeszto.proba": akkord}})
        for akkord in ("Mod+Alt+S", "F6", "Ctrl+Enter", ""):
            b.ellenoriz({"billentyuk": {"szerkeszto.proba": akkord}})


class RelativLinkTest(unittest.TestCase):
    def test_relativ_kereses_nem_jarja_be_a_teljes_fajllistat(self):
        f = feloldas.Feloldo([f"Dir/Note{i}.md" for i in range(1000)])
        class BejarhatatlanHalmaz(set):
            def __iter__(self):
                raise AssertionError("relative lookup scanned every file")
        f.fileset = BejarhatatlanHalmaz(f.fileset)
        self.assertEqual(f.resolve("./Note999", "Dir/Source.md")[0], "Dir/Note999.md")
        self.assertEqual(f.resolve("./note999", "Dir/Source.md")[0], "Dir/Note999.md")

    def test_relativ_cel_visszaoldodik_azonos_neveknel_is(self):
        f = feloldas.Feloldo(["A/Note.md", "B/Note.md", "A/Deep/Source.md", "Image.png"])
        for forras in ("Source.md", "A/Deep/Source.md", "B/Source.md"):
            for ut in f.fileset:
                cel = linkek.relativ_cel(f, ut, forras)
                self.assertTrue(cel.startswith(("./", "../")))
                self.assertEqual(f.resolve(cel, forras)[0], ut, (forras, cel))
        self.assertIsNone(f.resolve("../../B/Note", "A/Source.md")[0])
        self.assertIsNone(f.resolve("../Missing/Note", "A/Source.md")[0])
        self.assertEqual(f.resolve("../B/note", "A/Source.md")[0], "B/Note.md")


if __name__ == "__main__":
    unittest.main()
