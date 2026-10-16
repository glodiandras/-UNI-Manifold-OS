"""C20b: a gépi írás `mozgat` műveletének videó-profilja (68(b) kiterjesztése) — a staging videója APFS-klónként a vaultba, a bináris
napló `media` + `klon` rekordja, és a visszavonás, amely nem töröl (archívum, vagy vissza a staging helyére).

A valódi vaulthoz, stagingbe és `var/`-hoz egyik teszt sem nyúl (álgyökér, ál-staging)."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from core import binaris_naplo, gepi_iras, snapshot, tartos, vaultio
from core.tulajdonsagok import Tulajdonsagok
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
J1 = "T01 - Történelem/Média/Az I. triumvirátus.md"
VM = "ATTCHMNTS - Videos"


@csak_darwin("APFS-klón (clonefile)")
class VideoMozgatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.staging = Path(self._t.name) / "staging"
        self.cfg, self.root, self.v = alg_core(self._t.name, MOS_STAGING=str(self.staging))
        ir(self.v, J1, FM + "# Az I. triumvirátus\n\nszöveg\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.V = vaultio.Vault(self.cfg)
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None), varakozas_mp=0.3)

    def video(self, nev="video.mp4", tartalom=b"\x00\x00\x00\x18ftypmp42" + os.urandom(4096)) -> Path:
        p = self.staging / "youtube" / "tortenelem" / "Az I. triumvirátus" / nev
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(tartalom)
        return p

    def keres(self, *muveletek, tetel="t1", proba=False, kor="VIDEO-20261008-120000"):
        return {"kor": kor, "tetel": tetel, "forras": "mos-video", "modell": None, "proba": proba, "muveletek": list(muveletek)}

    def mozgat(self, p: Path, nev="Az I. triumvirátus.mp4"):
        return {"tipus": "mozgat", "forras": str(p), "ut": f"{VM}/{nev}", "sha256": binaris_naplo.kivonat(p)}

    def csere(self, nev="Az I. triumvirátus.mp4"):
        r = self.V.read(J1)
        return {"tipus": "csere", "ut": J1, "tartalom": r["tartalom"] + f"\n![[{nev}]]\n", "alap": r["hash"]}

    def cel(self, nev="Az I. triumvirátus.mp4") -> Path:
        return self.v / VM / nev

    def test_klon_a_staging_erintetlen_rekord_es_visszavonas_archivumba(self):
        p = self.video()
        eredeti = p.read_bytes()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere()))
        self.assertEqual(r["mozgatva"], [f"{VM}/Az I. triumvirátus.mp4"])
        self.assertEqual(self.cel().read_bytes(), eredeti)
        self.assertEqual(p.read_bytes(), eredeti)                                    # a staging példánya marad (klón)
        self.assertNotEqual(os.stat(p).st_ino, os.stat(self.cel()).st_ino)
        self.assertEqual(self.repo.changed_files(r["sha"]), [J1])                    # a videó a pillanatképben nincs (14.)
        rec = binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg))[-1]
        self.assertEqual((rec["commit"], rec["tipus"], rec["klon"], rec["forras_ut"], rec["sha256"], rec["meret"]),
                         (r["sha"], "media", True, os.path.realpath(p), binaris_naplo.kivonat(p), len(eredeti)))
        self.assertEqual(list(self.cfg.path("tmp").glob("*.manifold-tmp")), [])
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(len(v["mozgatva"]), 1, v)
        self.assertFalse(self.cel().exists())
        self.assertEqual(p.read_bytes(), eredeti)                                    # semmi nem törlődött:
        archiv = Path(v["mozgatva"][0][1])
        self.assertEqual(archiv.read_bytes(), eredeti)                               # a klón az archívumban
        self.assertTrue(archiv.is_relative_to(self.cfg.path("video_visszavont")))
        self.assertTrue((self.cfg.path("video_visszavont") / "INDOK.md").is_file())
        v2 = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(v2["mozgatva"], [])                                         # idempotens

    def test_hianyzo_eredetinel_a_klon_a_staging_helyere_ter_vissza(self):
        p = self.video()
        eredeti = p.read_bytes()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere()))
        os.rename(p, p.with_name("elkoltozott.mp4"))
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(v["mozgatva"], [(f"{VM}/Az I. triumvirátus.mp4", os.path.realpath(p))])
        self.assertEqual(p.read_bytes(), eredeti)
        self.assertFalse(self.cel().exists())

    def test_mas_tartalmu_eredeti_vagy_vaultbeli_valtozas_marad(self):
        p = self.video()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere()))
        p.write_bytes(b"atirt staging")
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(v["mozgatva"], [])
        self.assertTrue(self.cel().is_file() and "más tartalmú" in v["marad"][0][1])
        self.cel().write_bytes(b"a vaultban atirva")                                 # a vaultbeli fájl sem azonos: marad
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertTrue(self.cel().is_file() and "nem azonos" in v["marad"][0][1])

    def test_tiltott_forrasok_es_celok(self):
        p = self.video()
        kint = Path(self._t.name) / "mashol" / "video.mp4"
        kint.parent.mkdir()
        kint.write_bytes(b"x")
        vaultbeli = self.v / VM / "regi.mp4"
        vaultbeli.parent.mkdir()
        vaultbeli.write_bytes(b"y")
        link = self.staging / "link.mp4"
        link.symlink_to(kint)
        for m, hiba in ((self.mozgat(kint), vaultio.Invalid),                                   # nem a staging alól
                        ({**self.mozgat(p), "ut": "T01 - Történelem/Média/a.mp4"}, vaultio.Invalid),  # nem a videómappába
                        ({**self.mozgat(p), "sha256": "0" * 64}, vaultio.Conflict),
                        ({**self.mozgat(p), "ut": f"{VM}/a.mkv.part"}, vaultio.Invalid),
                        ({**self.mozgat(vaultbeli, "uj.mp4")}, vaultio.Invalid),                 # a vaultbeli média nem mozog
                        ({**self.mozgat(kint), "forras": str(link)}, vaultio.NotFound),         # symlink nem forrás
                        ({**self.mozgat(p), "ut": f"{VM}/regi.mp4"}, vaultio.Conflict),         # felülírás nincs
                        ({**self.mozgat(p), "ut": f"{VM}/REGI.mp4"}, vaultio.Conflict)):        # kis-nagybetűtől függetlenül
            with self.subTest(m=m["ut"]), self.assertRaises(hiba):
                self.G.ir(self.keres(m, self.csere()))
        with self.assertRaises(vaultio.Invalid):                                                # egyedül nem mozog (I40)
            self.G.ir(self.keres(self.mozgat(p)))
        self.assertEqual(vaultbeli.read_bytes(), b"y")
        self.assertEqual(sorted(x.name for x in (self.v / VM).iterdir()), ["regi.mp4"])

    def test_irasi_hiba_utan_a_klon_eltunik_a_staging_marad(self):
        p = self.video()
        with mock.patch.object(gepi_iras.GepiIras, "_fajl_ir", side_effect=OSError("lemez")):
            with self.assertRaises(OSError):
                self.G.ir(self.keres(self.mozgat(p), self.csere()))
        self.assertTrue(p.is_file())
        self.assertFalse(self.cel().exists())
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())
        self.assertEqual(list(self.cfg.path("tmp").glob("*.manifold-tmp")), [])

    def test_megszakadt_klon_helyreall(self):
        p = self.video()
        sha = binaris_naplo.kivonat(p)
        self.cel().parent.mkdir()
        tartos.klon_excl(p, self.cel())
        d = self.cfg.path("run") / gepi_iras.NAPLO
        (d / "eredeti").mkdir(parents=True)
        mz = {"ut": f"{VM}/Az I. triumvirátus.mp4", "lemez": f"{VM}/Az I. triumvirátus.mp4", "forras": str(p), "sha256": sha,
              "masolat": False, "klon": True}
        (d / "terv.json").write_text(json.dumps({"kor": "VIDEO-20261008-120000", "tetel": "t9", "feladat": None, "fajlok": [],
                                                 "mozgasok": [mz]}), encoding="utf-8")
        uz = gepi_iras.helyreallit(self.cfg)
        self.assertIn("was restored", uz[0])
        self.assertTrue(p.is_file() and not self.cel().exists())

    def test_proba_a_klonba_klonoz(self):
        p = self.video()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere(), proba=True))
        self.assertTrue(r["proba"] and p.is_file())
        self.assertTrue((Path(r["proba_mappa"]) / self.v.name / VM / "Az I. triumvirátus.mp4").is_file())
        self.assertFalse(self.cel().exists())
        self.assertFalse(binaris_naplo.naplo_ut(self.cfg).exists())                  # próbában nincs napló-sor

    def test_klon_excl_nem_ir_felul(self):
        p = self.video()
        cel = Path(self._t.name) / "cel.mp4"
        cel.write_bytes(b"meglevo")
        with self.assertRaises(FileExistsError):
            tartos.klon_excl(p, cel)
        self.assertEqual(cel.read_bytes(), b"meglevo")


if __name__ == "__main__":
    unittest.main()
