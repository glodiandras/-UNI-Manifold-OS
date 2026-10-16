"""F11 explorer, core half: `Make a copy` (07-explorer-06), `Reveal in Finder` (07-explorer-07) and the
`showUnsupportedFiles` switch of the file tree (07-explorer-12). Synthetic vaults only; the Finder call is injected."""
import json
import unicodedata
import unittest
from types import SimpleNamespace

from core import csatolmany
from core.utvonalak import HttpError
from tests.test_atnevezes import Alap

NFD = lambda s: unicodedata.normalize("NFD", s)  # noqa: E731


class MasolatTest(Alap):
    FAJLOK = {
        "Jegyzet.md": "---\ntitle: x\n---\n# Jegyzet\r\nbájt\n",
        "Mappa/Jegyzet.md": "# másik\n",
        "Mappa/Jegyzet 1.md": "# foglalt\n",
        "kep.png": b"\x89PNG\r\n\x00\xff",
        "Nincskit": "szöveg",
        "Ütőér.md": "# Ütőér\n",
    }

    def app(self):
        return SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A)

    def test_szoveges_masolat_bajtra_azonos_es_gepi_commitot_kap(self):
        r = csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})
        self.assertEqual(r["ut"], "Jegyzet 1.md")
        self.assertEqual((self.v / "Jegyzet 1.md").read_bytes(), (self.v / "Jegyzet.md").read_bytes())
        self.assertTrue(r["pillanat"])
        self.assertIn("Jegyzet 1.md", self.repo.git("ls-files").stdout)

    def test_szamozas_kihagyja_a_foglalt_nevet(self):
        r = csatolmany.masolat(self.app(), {"ut": "Mappa/Jegyzet.md"})
        self.assertEqual(r["ut"], "Mappa/Jegyzet 2.md")
        self.assertEqual((self.v / "Mappa/Jegyzet 1.md").read_text(encoding="utf-8"), "# foglalt\n")

    def test_ismetelt_masolas_nem_ir_felul(self):
        a = csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})["ut"]
        b = csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})["ut"]
        self.assertEqual((a, b), ("Jegyzet 1.md", "Jegyzet 2.md"))

    def test_nagybetu_es_normalizalas_fuggetlen_utkozes(self):
        (self.v / "jegyzet 1.MD").write_text("kis-nagybetű", encoding="utf-8")
        self.assertEqual(csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})["ut"], "Jegyzet 2.md")
        (self.v / NFD("Ütőér 1.md")).write_text("nfd", encoding="utf-8")
        self.assertEqual(csatolmany.masolat(self.app(), {"ut": "Ütőér.md"})["ut"], "Ütőér 2.md")

    def test_binaris_masolat_commit_nelkul_es_kiterjesztes_nelkuli_fajl(self):
        r = csatolmany.masolat(self.app(), {"ut": "kep.png"})
        self.assertEqual(r["ut"], "kep 1.png")
        self.assertEqual((self.v / "kep 1.png").read_bytes(), b"\x89PNG\r\n\x00\xff")
        self.assertIsNone(r["pillanat"])
        self.assertEqual(csatolmany.masolat(self.app(), {"ut": "Nincskit"})["ut"], "Nincskit 1")

    def test_mappa_rejtett_ut_es_hiany_elutasitva(self):
        (self.v / "Mappa/Alma").mkdir()
        for ut in ("Mappa", ".obsidian/app.json", "../x.md", "nincs.md", ""):
            with self.subTest(ut=ut), self.assertRaises((HttpError, ValueError, KeyError, Exception)):
                csatolmany.masolat(self.app(), {"ut": ut})
        self.assertFalse((self.v / "Mappa 1").exists())

    def test_mentetlen_dokumentum_409_es_semmi_nem_keletkezik(self):
        self.A.mentetlen = lambda: {"Jegyzet.md"}
        with self.assertRaises(HttpError) as cm:
            csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})
        self.assertEqual(cm.exception.code, 409)
        self.assertFalse((self.v / "Jegyzet 1.md").exists())

    def test_szimbolikus_link_nem_masolhato(self):
        (self.v / "link.md").symlink_to(self.v / "Jegyzet.md")
        with self.assertRaises(HttpError):
            csatolmany.masolat(self.app(), {"ut": "link.md"})

    def test_a_masolat_visszavonhato_a_pillanatkep_utjan(self):
        r = csatolmany.masolat(self.app(), {"ut": "Jegyzet.md"})
        self.assertTrue((self.v / "Jegyzet 1.md").exists())
        self.repo.git("revert", "--no-edit", r["pillanat"])
        self.assertFalse((self.v / "Jegyzet 1.md").exists())


class FinderTest(Alap):
    FAJLOK = {"A/Jegyzet.md": "# x\n", "Kep.png": b"\x89PNG"}

    def app(self):
        return SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A)

    def test_fajl_es_mappa_a_vaulton_beluli_abszolut_uttal_nyilik(self):
        hivasok = []
        csatolmany.finder(self.app(), {"ut": "A/Jegyzet.md"}, hivasok.append)
        csatolmany.finder(self.app(), {"ut": "A"}, hivasok.append)
        self.assertEqual([p.resolve() for p in hivasok], [(self.v / "A/Jegyzet.md").resolve(), (self.v / "A").resolve()])

    def test_kifele_vezeto_rejtett_es_hianyzo_ut_tiltott(self):
        (self.v / "kifele").symlink_to(self.root)
        for ut in ("../x", "/etc/passwd", ".obsidian", ".git/config", "nincs.md", "kifele/x", ""):
            hivasok = []
            with self.subTest(ut=ut), self.assertRaises(Exception):
                csatolmany.finder(self.app(), {"ut": ut}, hivasok.append)
            self.assertEqual(hivasok, [])

    def test_a_finder_nem_ir_a_vaultba(self):
        elotte = {p: p.stat().st_mtime_ns for p in self.v.rglob("*") if p.is_file() and ".git" not in p.parts}
        csatolmany.finder(self.app(), {"ut": "Kep.png"}, lambda p: None)
        utana = {p: p.stat().st_mtime_ns for p in self.v.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(elotte, utana)

    def test_nem_macos_501(self):
        from unittest import mock
        with mock.patch.object(csatolmany.sys, "platform", "linux"), self.assertRaises(HttpError) as cm:
            csatolmany.finder(self.app(), {"ut": "Kep.png"})
        self.assertEqual(cm.exception.code, 501)


class NemTamogatottFajlokTest(Alap):
    FAJLOK = {"A.md": "# a\n", "x.zip": b"PK"}

    def test_alap_hamis_es_az_obsidian_kulcsa_kapcsolja(self):
        self.assertFalse(self.V.minden_kiterjesztes())
        (self.v / ".obsidian/app.json").write_text(json.dumps({"showUnsupportedFiles": True}))
        self.assertTrue(self.V.minden_kiterjesztes())
        (self.v / ".obsidian/app.json").write_text(json.dumps({"showUnsupportedFiles": "igen"}))
        self.assertFalse(self.V.minden_kiterjesztes())
        (self.v / ".obsidian/app.json").write_text("nem json")
        self.assertFalse(self.V.minden_kiterjesztes())

    def test_a_fa_valasza_tovabbra_is_minden_fajlt_hoz_a_szures_a_feluleten_van(self):
        self.assertIn("x.zip", {f["ut"] for f in self.ix.fa()["fajlok"]})


if __name__ == "__main__":
    unittest.main()
