"""A portolt média-selftest (C20a): a legacy `modulok/eszkozok/tests/media_selftest.py` azon esetei, amelyek a **portolt kódra** vonatkoznak — modell,
hálózat és vault-író nélkül, ideiglenes álvaulttal. Az esetszámok a legacyéi (a névben: `t08_…`), hogy a megfelelés követhető legyen.

**Portolva**: 8–10 elhelyezés (ütközés, idegen jegyzet, fájllista), 22 az állapot a vaulton kívül, 24 staging (`olvas`, `visszajelez`,
`forrasmappak`, hiányos mappa), 30 videómappa és melléklet-réteg (a `place_video` szabálya tervként), 32 staging-mappa azonosítóból.
**Nem portolt (C20b, vagy a kód nem került át)**: 1–3 felirat-választás, 4 `norm_lang`, 4b–4e téma- és kötés-besorolás, 5 nyelvi döntés,
6 `download_args` (a `media.py fetch` helyett az `msp` letöltő dolgozik; a tesztjei az `msp` készletében vannak), 7 duplikátum (az `msp`
archívuma, `test_archive_manifest`/`test_pipeline`), 11–12 megálló lánc és elárvult zár (`media_auto`), 14–21 horgony, igazolás, verifikáció,
napló (`mfd.py`), 25 próbafutás, 31 helyi modell ítélete."""
import json
import os
import unittest
from pathlib import Path

from core import config
from modulok.ytdlp import elhelyezes, staging
from tests.helpers import REPO, alg_core, tmpdir
from tests.video_segedek import forras

TEMA = "T99 - Teszttéma"
VIDEOK = "ATTCHMNTS - Videos"
RETEG = "Média"
SENTINEL = "<!-- manifold-media -->"


def ir(p: Path, szoveg: str | bytes = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(szoveg if isinstance(szoveg, bytes) else szoveg.encode("utf-8"))
    return p


class ElhelyezesTeszt(unittest.TestCase):
    """8–10 és 30: az elhelyezés terve — a legacy `_s_elhelyezes` / `place_video` szabályai."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.vault = Path(self._t.name) / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.dest = self.vault / TEMA / RETEG
        self.fajlok = ["Tiszta.mp4", "Tiszta.hu.vtt", "Tiszta.info.json", "Tiszta.jpg"]

    def terv(self, fajlok=None, **kw):
        return elhelyezes.terv(self.vault, TEMA, fajlok or self.fajlok, video_mappa=VIDEOK, reteg=RETEG, **kw)

    def test_t08_utkozes_a_celmappaban_megall_semmi_nem_mozdul(self):
        ir(self.dest / "Tiszta.hu.vtt", "régi")
        t = self.terv()
        self.assertEqual(t["utkozesek"], ["Tiszta.hu.vtt"], "az ütközés megnevezett")
        self.assertEqual((self.dest / "Tiszta.hu.vtt").read_text(encoding="utf-8"), "régi", "a terv nem ír")
        self.assertFalse((self.vault / VIDEOK).exists(), "a terv nem hoz létre mappát")

    def test_t09_idegen_jegyzet_megallit(self):
        ir(self.dest / "Tiszta.md", "# Kézzel írt jegyzet\n")
        t = self.terv(torzs="Tiszta", sentinel=SENTINEL)
        self.assertEqual(t["utkozesek"], ["Tiszta.md (nem a media.py írta)"])
        self.assertTrue(t["forrasjegyzet_letezik"])

    def test_t09_a_lanc_sajat_jegyzete_nem_utkozes(self):
        ir(self.dest / "Tiszta.md", f"# T\n{SENTINEL}\n")
        self.assertEqual(self.terv(torzs="Tiszta", sentinel=SENTINEL)["utkozesek"], [])

    def test_t10_fajllista_es_cel(self):
        t = self.terv()
        self.assertEqual(t["utkozesek"], [])
        self.assertEqual(sorted(x["nev"] for x in t["fajlok"]), sorted(self.fajlok))
        self.assertEqual((t["cel"], t["video_cel"]), (f"{TEMA}/{RETEG}", VIDEOK))

    def test_t30_a_video_a_videomappaba_a_mellekletek_a_retegbe(self):
        t = self.terv()
        cel = {x["nev"]: x["cel_ut"] for x in t["fajlok"]}
        self.assertEqual(cel["Tiszta.mp4"], f"{VIDEOK}/Tiszta.mp4")
        for melleklet in ("Tiszta.hu.vtt", "Tiszta.info.json", "Tiszta.jpg"):
            self.assertEqual(cel[melleklet], f"{TEMA}/{RETEG}/{melleklet}")
        self.assertEqual([x["video"] for x in t["fajlok"] if x["nev"] == "Tiszta.mp4"], [True])
        self.assertEqual(sum(1 for x in t["fajlok"] if x["video"]), 1, "a videómappába csak videó kerül")

    def test_t30_a_hang_a_retegben_marad(self):
        t = self.terv(["Hangos.m4a", "Hangos.info.json"])
        self.assertEqual({x["nev"]: x["cel_ut"] for x in t["fajlok"]},
                         {"Hangos.m4a": f"{TEMA}/{RETEG}/Hangos.m4a", "Hangos.info.json": f"{TEMA}/{RETEG}/Hangos.info.json"})

    def test_t30_regi_elrendezes_minden_a_retegben(self):
        t = elhelyezes.terv(self.vault, TEMA, ["Régi.mp4", "Régi.hu.vtt"], video_mappa=None, reteg=RETEG)
        self.assertIsNone(t["video_cel"])
        self.assertEqual({x["cel_ut"] for x in t["fajlok"]}, {f"{TEMA}/{RETEG}/Régi.mp4", f"{TEMA}/{RETEG}/Régi.hu.vtt"})

    def test_t30_utkozes_a_videomappaban(self):
        ir(self.vault / VIDEOK / "Ütköző2.mp4", "régi")
        t = self.terv(["Ütköző2.mp4", "Ütköző2.hu.vtt"])
        self.assertEqual(t["utkozesek"], ["Ütköző2.mp4"])
        self.assertEqual((self.vault / VIDEOK / "Ütköző2.mp4").read_text(encoding="utf-8"), "régi", "a meglévő videó érintetlen")
        self.assertFalse((self.dest / "Ütköző2.hu.vtt").exists(), "nem mozdult semmi")

    def test_t30_utkozes_vault_szinten_masutt_allo_azonos_nevu_video(self):
        ir(self.vault / "Valami más mappa" / "Máshol.mp4", "másik")
        t = self.terv(["Máshol.mp4"])
        self.assertEqual(len(t["utkozesek"]), 1)
        self.assertIn("már létezik", t["utkozesek"][0])
        self.assertIn("Valami más mappa/Máshol.mp4", t["utkozesek"][0])

    def test_t30_nfd_nev_is_utkozik(self):
        import unicodedata
        ir(self.vault / "x" / unicodedata.normalize("NFD", "Bánk bán.mp4"), "m")
        self.assertEqual(len(self.terv(["Bánk bán.mp4"])["utkozesek"]), 1)

    def test_t30_fajlnev_torzs(self):
        """A fájlnév és a cím ugyanabból a sztringből (I32); a vaultban nem ábrázolható jelek `-`-re cserélődnek."""
        self.assertEqual(elhelyezes.fajlnev_torzs("Dante: Az isteni színjáték"), "Dante- Az isteni színjáték")
        self.assertEqual(elhelyezes.fajlnev_torzs("A magyar nyelv: jövevényszavak, nyelvújítás"), "A magyar nyelv- jövevényszavak, nyelvújítás")
        self.assertEqual(elhelyezes.fajlnev_torzs("  ...  "), "media")
        self.assertEqual(len(elhelyezes.fajlnev_torzs("a" * 300)), 120)
        self.assertEqual(elhelyezes.fajlnev_torzs('x/y\\z"w'), "x-y-z-w")

    def test_t30_media_index_kihagyja_a_rejtett_mappakat(self):
        ir(self.vault / ".obsidian" / "x.mp4")
        ir(self.vault / ".trash" / "y.mp4")
        ir(self.vault / "z" / "w.mp3")
        self.assertEqual(sorted(elhelyezes.media_index(self.vault)), ["w.mp3"])


class AllapotVaultonKivulTeszt(unittest.TestCase):
    def test_t22_a_lanc_allapota_nincs_a_vaultban(self):
        """A legacy 2026-09-13-i e2e hibája: a vaultba írt `media-log.jsonl` izolált csomópontot hozott létre. Itt: a lánc minden
        útja (jobs, staging, archívum, napló, eredeti, bináris napló) a vaulton kívül van."""
        with tmpdir() as t:
            cfg, _, vault = alg_core(t)
            for kulcs in ("video_jobs", "staging", "ytdlp_archivum", "video_eredeti", "binaris_naplo", "ffmpeg", "node"):
                ut = os.path.abspath(cfg.path(kulcs))
                self.assertFalse(ut.startswith(os.path.abspath(vault) + os.sep), f"{kulcs}: {ut} a vaultban van")

    def test_t22_az_alapertelmezett_utak_a_valodi_configban(self):
        cfg = config.load({"MOS_ROOT": str(REPO)})
        vault = os.path.abspath(cfg.path("vault"))
        for kulcs in ("video_jobs", "staging", "ytdlp_archivum", "video_eredeti", "binaris_naplo"):
            self.assertFalse(os.path.abspath(cfg.path(kulcs)).startswith(vault + os.sep), kulcs)
        self.assertEqual(Path(cfg.path("ffmpeg")), REPO / "runtime" / "ffmpeg" / "ffmpeg")
        self.assertEqual(Path(cfg.path("staging")), REPO / "modulok" / "ytdlp" / "staging")


class StagingEsetekTeszt(unittest.TestCase):
    """24 és 32: a staging forrásmappa — a valódi msp-pipeline kimenetén."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.sd = forras(self.d, video_id="abc123", cim="Teszt forrás")

    def test_t24_staging_olvas(self):
        s = staging.olvas(self.sd)
        self.assertEqual((s["video_id"], s["targy"], s["atirat_kesz"]), ("abc123", "Történelem", False))

    def test_t24_a_staging_erintetlen_olvasas_utan(self):
        elotte = {p.name: p.read_bytes() for p in self.sd.iterdir()}
        staging.olvas(self.sd)
        staging.leltar(self.d / "staging")
        self.assertEqual({p.name: p.read_bytes() for p in self.sd.iterdir()}, elotte)

    def test_t24_visszajelez_ketszer_irva_majd_mar_ez(self):
        self.assertEqual((staging.visszajelez(self.sd), staging.visszajelez(self.sd)), ("irva", "mar_ez"))

    def test_t24_visszajelez_egy_mezo(self):
        elotte = json.loads((self.sd / "integration.json").read_text(encoding="utf-8"))
        staging.visszajelez(self.sd)
        utana = json.loads((self.sd / "integration.json").read_text(encoding="utf-8"))
        self.assertEqual({k for k in elotte if elotte[k] != utana.get(k)}, {"integration_status"})

    def test_t24_forrasmappak(self):
        self.assertEqual(staging.forrasmappak(self.d / "staging"), [str(self.sd)])
        self.assertEqual(staging.forrasmappak(self.sd), [str(self.sd)], "maga a forrásmappa is az")

    def test_t24_hianyos_mappa_nem_atmegy(self):
        (self.sd / "metadata.json").unlink()
        with self.assertRaises(staging.StagingHiba):
            staging.olvas(self.sd)

    def test_t32_megtalalja_nincs_talalat_ures_nem_letezo_gyoker(self):
        gy = self.d / "staging"
        self.assertEqual(staging.keres_azonosito("abc123", gy), str(self.sd))
        self.assertIsNone(staging.keres_azonosito("nincs-ilyen", gy))
        self.assertIsNone(staging.keres_azonosito(None, gy))
        self.assertIsNone(staging.keres_azonosito("abc123", self.d / "nincs"))

    def test_t32_az_utvonal_elavulasa_nem_szamit(self):
        """A lánc állapotában tárolt mappa-út elavulhat (a repó költözött); az azonosító nem."""
        athelyezve = self.d / "uj-gyoker"
        self.sd.parent.parent.rename(athelyezve)
        self.assertFalse(self.sd.exists())
        talalt = staging.keres_azonosito("abc123", athelyezve)
        self.assertIsNotNone(talalt)
        self.assertTrue(talalt.startswith(str(athelyezve)))


if __name__ == "__main__":
    unittest.main()
