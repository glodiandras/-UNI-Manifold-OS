"""C20a / T142: a média-kiterjesztések egyetlen forrása — a pillanatkép kizárólistája és a média-engedélylista nem térhet el.

Álgyökérben, valódi `git`-tel: a valódi vaulthoz és var/-hoz a teszt nem nyúl."""
import subprocess
import unittest
from pathlib import Path

from core import atirat, doctor, mediatipus, snapshot, vaultio
from core.index import indexelo
from tests.helpers import alg_core, tmpdir


class EgyForrasTeszt(unittest.TestCase):
    def test_a_vaultio_es_az_atirat_a_kozos_listabol_jon(self):
        self.assertIs(vaultio.MEDIA_TIPUS, mediatipus.MEDIA_TIPUS)
        video_hang = tuple(k for k, t in mediatipus.MEDIA_TIPUS.items() if t.startswith(("video/", "audio/")))
        self.assertEqual(atirat.MEDIA_KIT, video_hang)

    def test_minden_media_kiterjesztes_kizart_kis_es_nagybetuvel(self):
        mintak = set(mediatipus.kizar_mintak())
        for kit in mediatipus.MEDIA_TIPUS:
            self.assertIn(f"*{kit}", mintak)
            self.assertIn(f"*{kit.upper()}", mintak)
        for kit in mediatipus.EGYEB_BINARIS:
            self.assertIn(f"*{kit}", mintak)

    def test_a_korabban_hianyzo_kiterjesztesek_most_kizartak(self):
        """A 2. audit felsorolása (T142): avif, bmp, heif, tif, m4v, ogv, flac, ogg, opus, aac, 3gp, svg."""
        mintak = set(mediatipus.kizar_mintak())
        for kit in ("avif", "bmp", "heif", "tif", "m4v", "ogv", "flac", "ogg", "opus", "aac", "3gp", "svg"):
            self.assertIn(f"*.{kit}", mintak, kit)

    def test_nincs_ismetlodes_es_rendezett(self):
        mintak = mediatipus.kizar_mintak()
        self.assertEqual(len(mintak), len(set(mintak)))
        self.assertEqual(mediatipus.BINARIS_KITERJESZTESEK, tuple(sorted(mediatipus.BINARIS_KITERJESZTESEK)))

    def test_tipus_es_binaris_e(self):
        self.assertEqual(mediatipus.tipus("A/b.MP4"), "video/mp4")
        self.assertIsNone(mediatipus.tipus("a.md"))
        self.assertTrue(mediatipus.binaris_e("x/y.AVI"))
        self.assertTrue(mediatipus.binaris_e("x.docx"))
        self.assertFalse(mediatipus.binaris_e("x.md"))
        self.assertFalse(mediatipus.binaris_e("x.vtt"))
        self.assertTrue(mediatipus.media_e("kep.heif"))

    def test_az_os_toml_nem_sorol_fel_median_mintat(self):
        """A médiamintákat a `mediatipus` adja; ha az `os.toml`-ban is megjelenne, kettő lenne az igazság."""
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
            for nev, sec in cfg.section("pillanat").items():
                for minta in sec.get("kizar", []):
                    self.assertFalse(minta.startswith("*.") and "." + minta[2:].lower() in mediatipus.BINARIS_KITERJESZTESEK,
                                     f"[pillanat.{nev}] kizar: {minta} — a core/mediatipus.py adja")

    def test_az_index_tipusai_egyeznek_a_media_listaval(self):
        """Az index (`indexelo._KIT_TIPUS`) külön táblát tart; a C29.8 területe, ezért itt csak őrzöm az egyezést. Ismert
        eltérés: a `.heif` az indexben nincs képként (NAPLO: Maradt)."""
        ISMERT_ELTERES = {".heif"}
        kat = {"image/": "kep", "video/": "video", "audio/": "hang", "application/pdf": "pdf"}
        for kit, ct in mediatipus.MEDIA_TIPUS.items():
            if kit in ISMERT_ELTERES:
                continue
            varhato = next(v for k, v in kat.items() if ct.startswith(k))
            self.assertEqual(indexelo._KIT_TIPUS.get(kit[1:]), varhato, kit)


class GitKizarasTeszt(unittest.TestCase):
    """A generált `info/exclude` a valódi gittel: a kizárt fájl `check-ignore`-ral kizárt, mindkét `core.ignorecase` mellett."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = alg_core(self._t.name)
        self.repo = snapshot.repos(self.cfg)["vault"]

    def _listazott(self) -> set[str]:
        """Amit a git a munkafában nem kizártként lát (a `check-ignore` a `GIT_LITERAL_PATHSPECS` miatt nem használható)."""
        ki = self.repo.git("status", "--porcelain", "--untracked-files=all").stdout
        return {sor[3:] for sor in ki.splitlines() if sor.strip()}

    def test_a_kizarasok_ignorecase_mellett_es_nelkul_is_hatnak(self):
        self.repo.init()
        for ic in ("true", "false"):
            self.repo.git("config", "core.ignorecase", ic)
            kizartak = []
            for kit in ("mp4", "avif", "m4v", "flac", "opus", "heif", "svg", "3gp", "pdf", "docx"):
                for rp in (f"k_{ic}_{kit}.{kit}", f"U_{ic}_{kit}.{kit.upper()}", f"mappa/m_{ic}_{kit}.{kit}"):
                    f = self.vault / rp
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(b"x")
                    kizartak.append(rp)
            (self.vault / f"jegyzet_{ic}.md").write_text("# x\n", encoding="utf-8")
            (self.vault / f"felirat_{ic}.vtt").write_text("WEBVTT\n", encoding="utf-8")
            lista = self._listazott()
            for rp in kizartak:
                self.assertFalse(any(l == rp or l.startswith(rp.split("/")[0] + "/") and rp.startswith(l.rstrip("/"))
                                     for l in lista), f"{rp} nem kizárt (core.ignorecase={ic}): {sorted(lista)}")
            self.assertIn(f"jegyzet_{ic}.md", lista)
            self.assertIn(f"felirat_{ic}.vtt", lista)

    def test_a_regi_tarolo_info_exclude_ja_frissul_a_kornyezet_biztositasakor(self):
        """T142: az élő (régi) tárolón az `info/exclude` sosem frissült, mert a `write_exclude` csak az `init()`-ből futott."""
        self.repo.init()
        kizaras = self.repo.git_dir / "info" / "exclude"
        kizaras.write_text("# régi\n*.mp4\n", encoding="utf-8")
        self.assertTrue(self.repo.write_exclude() is True)
        kizaras.write_text("# régi\n*.mp4\n", encoding="utf-8")
        self.repo.biztosit_kornyezet()
        self.assertEqual(kizaras.read_text(encoding="utf-8"), self.repo.exclude_szoveg())
        self.assertIn("*.avif", kizaras.read_text(encoding="utf-8"))
        self.assertFalse(self.repo.write_exclude(), "idempotens: változatlan tartalomnál nem ír")

    def test_az_ytdlp_tar_is_ugyanazt_a_listat_kapja(self):
        self.assertIn("*.opus", snapshot.repos(self.cfg)["ytdlp"].exclude)
        self.assertIn("*.part", snapshot.repos(self.cfg)["ytdlp"].exclude)


class DoctorBinarisTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = alg_core(self._t.name)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()

    def _sorok(self) -> dict:
        ki = {}
        doctor._tarolt_binaris(self.cfg, lambda a, n, m: ki.update({n: (a, m)}))
        return ki

    def _commit(self, *utak):
        for u in utak:
            f = self.vault / u
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
        self.repo.git("add", "-f", "--", *utak)
        self.repo.git("commit", "-q", "-m", "teszt")

    def test_tiszta_tar_rendben(self):
        self._commit("a.md")
        a, m = self._sorok()["pillanatkép bináris"]
        self.assertEqual(a, doctor.OK, m)

    def test_a_tarban_allo_binaris_media_figyelmeztet(self):
        self._commit("a.md", "ATTCHMNTS - Videos/film.M4V", "hang.opus")
        a, m = self._sorok()["pillanatkép bináris"]
        self.assertEqual(a, doctor.FIGYELEM)
        self.assertIn("2 bináris fájl", m)
        self.assertIn("film.M4V", m)

    def test_ures_tarnal_nincs_sor(self):
        self.assertEqual(self._sorok(), {})


if __name__ == "__main__":
    unittest.main()
