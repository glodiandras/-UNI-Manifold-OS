"""C20a: a `video_letoltes` feladat és a lánc lépése — a terv (validáció, parancssor), a feladatsoron át érkező kérés, és a lépés maga hamis
letöltővel (hálózat nélkül): letöltés → konvertálás → staging → pillanatkép az ytdlp tárba. Ideiglenes álgyökérben."""
import io
import os
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from core import frame, snapshot, tasks, videolanc
from modulok.ytdlp import lanc
from tests.helpers import REPO, alg_core, tmpdir
from tests.test_core_api import _Szerver
from tests.test_video_staging import FAKE_FFMPEG
from tests.video_segedek import FFMPEG, ffmpeg_elerheto, forras, hamis_letolto, info, msp, pin_es_ffmpeg, szintetikus_video

URL = "https://zanza.tv/tortenelem/az-okori-athen"
ELOK = "[indokolt] nincs runtime/ffmpeg (bin/mos runtime fetch ffmpeg)"


def dns_hamis(teszt, cimek=("93.184.216.34",)):
    """A link-ellenőrzés DNS-feloldása hálózat nélkül (Javító 3, A3-13): a névhez nyilvános címet ad."""
    p = mock.patch.object(videolanc, "_felold", return_value=list(cimek))
    p.start()
    teszt.addCleanup(p.stop)


def ffmpeg_a_gyokerben(root: Path) -> Path:
    ff = root / "runtime" / "ffmpeg" / "ffmpeg"
    ff.parent.mkdir(parents=True, exist_ok=True)
    ff.write_text("#!/bin/sh\nexit 0\n")
    ff.chmod(0o755)
    return ff


class TervTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        dns_hamis(self)

    def terv(self, p):
        return videolanc._terv(self.cfg, p, "/stop")

    def test_ervenytelen_linkek_400(self):
        ffmpeg_a_gyokerben(self.root)
        for urlek in ([], None, "x", [5], [""], ["ftp://x/y"], ["javascript:alert(1)"], ["file:///etc/passwd"], ["http://localhost/x"],
                      ["http://127.0.0.1:8080/api"], ["http://[::1]/x"], ["https://10.1.2.3/v"], ["https://u:p@zanza.tv/x"],
                      ["https://zanza.tv/a b"], ["https://x.hu/" + "a" * 2100], ["https://szerver.local/x"], ["https://169.254.1.1/x"]):
            with self.subTest(urlek=urlek), self.assertRaises(tasks.Invalid):
                self.terv({"urlek": urlek})
        with self.assertRaises(tasks.Invalid):
            self.terv({"urlek": [f"https://zanza.tv/{i}" for i in range(21)]})

    def test_a_dedupe_sorrendtarto_es_a_parancssor(self):
        ff = ffmpeg_a_gyokerben(self.root)
        lepesek, osszegzes, fig = self.terv({"urlek": [URL, "https://youtu.be/x", URL]})
        (l,) = lepesek
        self.assertEqual(l.argv, [sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "letoltes", "--url", URL, "--url", "https://youtu.be/x",
                                  "--ki", str(videolanc.letoltes_eredmeny("/", "stop"))])         # F4: a letöltött mappák listája
        self.assertEqual(l.cwd, str(self.root))
        self.assertIn("2 videólink", osszegzes)
        self.assertEqual(fig, [])
        self.assertTrue(ff.is_file())

    def test_proba_mod_a_tmp_ala_teszi(self):
        ffmpeg_a_gyokerben(self.root)
        (l,), _, fig = self.terv({"urlek": [URL], "proba": True})
        i = l.argv.index("--proba-gyoker")
        self.assertTrue(l.argv[i + 1].startswith(str(self.cfg.path("tmp") / "video-proba")))
        self.assertTrue(fig and "Próbamód" in fig[0])
        self.assertNotIn("--ki", l.argv)                    # próbában nincs bevitel, eredményfájl sem

    def test_hianyzo_ffmpeg_magyar_hiba(self):
        with self.assertRaises(tasks.Invalid) as cm:
            self.terv({"urlek": [URL]})
        self.assertIn("runtime fetch ffmpeg", str(cm.exception))

    def test_a_tipus_nem_automatikus_nem_modell_nem_vault(self):
        videolanc.regisztral()
        t = tasks.REGISTRY["video_letoltes"]
        self.assertEqual((t.automatikus, t.graceful_stop, set(t.resources)), (False, True, set()))

    def test_nem_objektum_parameter(self):
        with self.assertRaises(tasks.Invalid):
            videolanc._terv(self.cfg, "x", "/stop")


class FeladatsorTeszt(_Szerver):
    """A feladat a valódi útvonal-regiszteren át: regisztrálva van, és az érvénytelen kérés 400."""

    def elokeszit(self):
        dns_hamis(self)

    def test_a_tipus_a_regiszteren_at_el_es_a_kerelem_validalt(self):
        kod, d = self.k("POST", "/api/feladatok", {"tipus": "video_letoltes", "parameterek": {"urlek": ["ftp://x/y"]}})
        self.assertEqual(kod, 400, d)
        self.assertIn("http(s)", d["hiba"])
        kod, d = self.k("POST", "/api/feladatok", {"tipus": "video_letoltes", "parameterek": {"urlek": ["http://127.0.0.1:9/x"]}})
        self.assertEqual(kod, 400)
        self.assertIn("video_letoltes", tasks.REGISTRY)

    def test_ffmpeg_nelkul_a_feladat_nem_indul(self):
        kod, d = self.k("POST", "/api/feladatok", {"tipus": "video_letoltes", "parameterek": {"urlek": [URL]}})
        self.assertEqual(kod, 400, d)
        self.assertIn("ffmpeg", d["hiba"])


def lepes(cfg, urlek, **kw):
    ki = io.StringIO()
    with redirect_stdout(ki):
        rc = lanc.letoltes(cfg, urlek, log=lambda s: print(s), **kw)
    return rc, ki.getvalue()


class LancTeszt(unittest.TestCase):
    """A lépés maga: in-process, hamis letöltővel (`msp.downloader.create_downloader` pótlása), hálózat nélkül."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ytdlp = self.cfg.path("ytdlp")
        self.ytdlp.mkdir(parents=True)
        self.ff = str(pin_es_ffmpeg(self.cfg, self.root, valodi=FFMPEG if ffmpeg_elerheto() else None))
        p = mock.patch.dict(os.environ, {"MOS_FFMPEG": "/nincs/ilyen/ffmpeg"})     # A3-17: a környezeti ffmpeg-et a lánc nem használja
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("MANIFOLD_STOP_FAJL", None)
        self.staging = self.cfg.path("staging")

    def futtat(self, letolto, urlek=(URL,), **kw):
        _, modul, _ = msp()
        with mock.patch.object(modul, "create_downloader", return_value=letolto):
            return lepes(self.cfg, list(urlek), **kw)

    def test_hiba_ffmpeg_nelkul(self):
        shutil.rmtree(self.root / "runtime" / "ffmpeg", ignore_errors=True)   # a setUp által tett (hamis vagy symlinkelt) ffmpeg
        rc, ki = lepes(self.cfg, [URL])
        self.assertEqual(rc, 2)
        self.assertIn("runtime/ffmpeg", ki)

    def test_sikeres_letoltes_a_stagingbe_vaultba_nem_ir(self):
        vault_elotte = {p: p.read_bytes() for p in self.v.rglob("*") if p.is_file()}
        rc, ki = self.futtat(hamis_letolto())
        self.assertEqual(rc, 0, ki)
        self.assertIn("Kész:", ki)
        self.assertIn("[manifold-progress] 100%", ki)
        (integracio,) = list(self.staging.rglob("integration.json"))
        mappa = integracio.parent
        self.assertTrue((mappa / "video.mp4").is_file())
        self.assertEqual({p: p.read_bytes() for p in self.v.rglob("*") if p.is_file()}, vault_elotte, "a vaulthoz nem nyúlt")
        self.assertTrue(self.cfg.path("ytdlp_archivum").is_dir(), "az archívum a [utak] ytdlp_archivum helyén")

    def test_masodik_futas_mar_megvan_nem_tolt_le_ujra(self):
        l = hamis_letolto()
        self.assertEqual(self.futtat(l)[0], 0)
        letolto2 = hamis_letolto()
        rc, ki = self.futtat(letolto2)
        self.assertEqual(rc, 0)
        self.assertIn("Már megvan", ki)
        self.assertEqual(len(list(self.staging.rglob("video.mp4"))), 1)

    def test_hiba_nem_viszi_el_a_tobbi_linket(self):
        _, modul, _ = msp()
        from msp.errors import NetworkError
        l = hamis_letolto()
        hibak = {"https://rossz.hu/x": NetworkError("nincs hálózat")}
        eredeti_probe = l.probe

        def probe(url, **kw):
            if url in hibak:
                raise hibak[url]
            return eredeti_probe(url, **kw)
        l.probe = probe
        rc, ki = self.futtat(l, ["https://rossz.hu/x", URL])
        self.assertEqual(rc, 1)
        self.assertIn("Hiba:", ki)
        self.assertIn("1 letöltve, 0 már megvolt, 1 hiba", ki)
        self.assertEqual(len(list(self.staging.rglob("video.mp4"))), 1)

    def test_leallitas_kerve_a_hatralevo_linkek_kimaradnak(self):
        stop = Path(self._t.name) / "stop"
        stop.write_text("")
        rc, ki = self.futtat(hamis_letolto(), [URL, "https://zanza.tv/masik"], stop_fajl=str(stop))
        self.assertEqual(rc, 0)
        self.assertIn("2 link kimarad", ki)
        self.assertFalse(list(self.staging.rglob("video.mp4")))

    def test_proba_mod_a_tmp_alatt_pillanatkep_nelkul(self):
        proba = Path(self._t.name) / "proba"
        rc, ki = self.futtat(hamis_letolto(), proba_gyoker=proba)
        self.assertEqual(rc, 0, ki)
        self.assertTrue(list((proba / "staging").rglob("video.mp4")))
        self.assertFalse(self.staging.exists(), "az éles staging érintetlen")
        self.assertTrue((proba / "archive").is_dir())

    def test_lanc_a_vegen_pillanatkep_az_ytdlp_tarba(self):
        """Előbb a kézi változás külön commitba, a lánc útjai utána egy gépi commitba (`Mos-Forras: mos-video`, `Mos-Feladat`); a média nem."""
        (self.ytdlp / "src").mkdir()
        (self.ytdlp / "src" / "kod.py").write_text("# régi\n", encoding="utf-8")
        repo = snapshot.repos(self.cfg)["ytdlp"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        (self.ytdlp / "src" / "kod.py").write_text("# módosított kézzel\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"MOS_FELADAT": "F-20261004-120000-1"}):
            rc, ki = self.futtat(hamis_letolto())
        self.assertEqual(rc, 0, ki)
        naplo = repo.log(5)
        self.assertEqual([c.trailers.get("Mos-Forras") for c in naplo[:2]], ["mos-video", "kezi"])
        gepi, kezi = naplo[0], naplo[1]
        self.assertEqual(gepi.trailers["Mos-Feladat"], "F-20261004-120000-1")
        self.assertTrue(gepi.run.startswith("VIDEO-"))
        fajlok = {f["ut"] for f in repo.commit_fajlok(gepi.sha)}
        self.assertTrue(any(f.endswith("metadata.json") for f in fajlok), fajlok)
        self.assertFalse(any(f.endswith(".mp4") for f in fajlok), "a média nem kerül a pillanatképbe")
        self.assertEqual({f["ut"] for f in repo.commit_fajlok(kezi.sha)}, {"src/kod.py"}, "a kézi változás külön commit")
        self.assertEqual(repo.dirty(), [])

    def test_nem_el_o_ytdlp_tar_pillanatkep_nelkul_is_lefut(self):
        rc, ki = self.futtat(hamis_letolto())
        self.assertEqual(rc, 0, ki)
        self.assertIn("nem élő", ki)

    def test_pillanat_utan_nincs_mit_menteni(self):
        repo = snapshot.repos(self.cfg)["ytdlp"]
        (self.ytdlp / "a.txt").write_text("x", encoding="utf-8")
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        self.assertIsNone(lanc.pillanat_utan(self.cfg, 0, log=lambda s: None))


@unittest.skipUnless(ffmpeg_elerheto(), ELOK)
class KonvertalasALancbanTeszt(LancTeszt):
    """A nem natív letöltés a staging-írás ELŐTT natívvá lesz, így a `source.md`, a `metadata.json` és az `integration.json` a natív nevet hordozza."""

    def mkv_letolto(self, kodek="libx264", kontener="mkv", hang="aac", **kw):
        def fajl(cel: Path, stem: str) -> Path:
            return szintetikus_video(cel / f"{stem}.{kontener}", kodek, kontener, hang)
        return hamis_letolto(fajl=fajl, **kw)

    def test_mkv_a_stagingben_mp4_az_eredeti_az_archivumban(self):
        rc, ki = self.futtat(self.mkv_letolto())
        self.assertEqual(rc, 0, ki)
        self.assertIn("konvertálva (remux", ki)
        mappa = list(self.staging.rglob("integration.json"))[0].parent
        self.assertEqual(sorted(p.name for p in mappa.iterdir()), ["integration.json", "metadata.json", "source.md", "transcript.md", "video.mp4"])
        import json
        self.assertEqual(json.loads((mappa / "integration.json").read_text(encoding="utf-8"))["media"], "video.mp4")
        self.assertIn("video.mp4", (mappa / "source.md").read_text(encoding="utf-8"))
        eredeti = list(self.cfg.path("video_eredeti").rglob("video.mkv"))
        self.assertEqual(len(eredeti), 1, "az eredeti az archive alá került")
        from modulok.ytdlp import konvertalas
        self.assertTrue(konvertalas.nativ_e(konvertalas.felmeres(self.ff, mappa / "video.mp4"), ".mp4")[0])

    def test_webm_vp9_atkodolva(self):
        rc, ki = self.futtat(self.mkv_letolto("libvpx-vp9", "webm", "libopus"))
        self.assertEqual(rc, 0, ki)
        self.assertIn("konvertálva (atkodol", ki)
        self.assertTrue(list(self.staging.rglob("video.mp4")))
        self.assertFalse(list(self.staging.rglob("video.webm")))

    def test_eredeti_megtartasa_kikapcsolhato_de_nem_torol(self):
        """`[video] eredeti_megtart = false`: az eredeti `.eredeti` néven a staging-ben marad — nem törlünk."""
        with mock.patch.object(lanc, "_video_beallitas", return_value={"crf": 20, "szal": 2, "nativ": ("h264", "hevc"),
                                                                       "hang": ("aac", "mp3", "alac"), "megtart": False}):
            rc, ki = self.futtat(self.mkv_letolto())
        self.assertEqual(rc, 0, ki)
        self.assertTrue(list(self.staging.rglob("video.mkv.eredeti")))
        self.assertFalse(self.cfg.path("video_eredeti").exists())

    def test_konvertalasi_hiba_nem_hibaztatja_a_letoltest(self):
        pin_es_ffmpeg(self.cfg, self.root, FAKE_FFMPEG)         # a hamis ffmpeg a pinelt helyen, a hozzá tartozó pinnel
        with mock.patch.dict(os.environ, {"MOD": "hiba"}):
            _, modul, folyamat = msp()
            fajl = lambda cel, stem: szintetikus_video(cel / f"{stem}.webm", "libvpx-vp9", "webm", "libopus")   # noqa: E731
            with mock.patch.object(modul, "create_downloader", return_value=hamis_letolto(fajl=fajl)):
                rc, ki = lepes(self.cfg, [URL])
        self.assertEqual(rc, 0, ki)
        self.assertIn("FIGYELEM: a konvertálás nem sikerült", ki)
        self.assertTrue(list(self.staging.rglob("video.webm")), "a letöltött fájl marad")


class DoctorFfmpegTeszt(unittest.TestCase):
    """A doctor ffmpeg-sora (T055): a pinelt build kell; a home-beli és a rendszer-ffmpeg tiltott."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.home = Path(self._t.name) / "home"
        (self.root / "config").mkdir(exist_ok=True)

    def sor(self, cfg=None):
        ki = {}
        from core import doctor
        doctor._video_ffmpeg(cfg or self.cfg, self.home, lambda a, n, m: ki.update({n: (a, m)}))
        return ki["ffmpeg"]

    def pin(self, sha: str):
        (self.root / "config" / "runtime-pins.env").write_text(f"FFMPEG_BIN_SHA256={sha}\n", encoding="utf-8")

    def test_hianyzik_figyelem_nem_hiba(self):
        a, m = self.sor()
        self.assertEqual(a, "figyelem")
        self.assertIn("runtime fetch ffmpeg", m)

    def test_pin_nelkul_info(self):
        ffmpeg_a_gyokerben(self.root)
        self.assertEqual(self.sor()[0], "info")

    def test_egyezo_sha_ok_eltero_hiba(self):
        import hashlib
        ff = ffmpeg_a_gyokerben(self.root)
        self.pin(hashlib.sha256(ff.read_bytes()).hexdigest())
        self.assertEqual(self.sor()[0], "ok")
        self.pin("0" * 64)
        a, m = self.sor()
        self.assertEqual(a, "hiba")
        self.assertIn("eltér", m)

    def test_a_home_beli_ffmpeg_tiltott(self):
        from core import config
        tiltott = self.home / ".local" / "bin" / "ffmpeg"
        tiltott.parent.mkdir(parents=True)
        tiltott.write_text("#!/bin/sh\nexit 0\n")
        tiltott.chmod(0o755)
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_FFMPEG": str(tiltott)})
        a, m = self.sor(cfg)
        self.assertEqual(a, "hiba")
        self.assertIn("tiltott", m)


if __name__ == "__main__":
    unittest.main()
