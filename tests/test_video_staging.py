"""C20a: a videólánc modell nélküli építőkövei — útnormalizálás (264 `state.json`, a mért alakok), staging-olvasás a valódi pipeline kimenetén,
a staging APFS-klónja, az `ffmpeg -i` elemzése és a valódi konvertálás szintetikus MKV/WebM/AV1 fájlokon. Ideiglenes könyvtárakban."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from modulok.ytdlp import klon, konvertalas, staging, utnorm
from tests.helpers import tmpdir
from tests.video_segedek import FFMPEG, ffmpeg_elerheto, forras, szintetikus_video

JOBS = Path("/J/jobs")
STAG = Path("/S/staging")
ELOK = "[indokolt] nincs runtime/ffmpeg (bin/mos runtime fetch ffmpeg)"


class UtnormTeszt(unittest.TestCase):
    def n(self, ut):
        return utnorm.normalizal(ut, jobs=JOBS, staging=STAG)

    def test_a_ket_merve_alak(self):
        """2026-10-04-én a 264 state.json-ban két abszolút alak állt: az app-support/iCloud és a régi SSD-gyökér."""
        self.assertEqual(self.n("/Users/u/Library/Application Support/Manifold-media/jobs/youtube-abc"), JOBS / "youtube-abc")
        self.assertEqual(self.n("/Users/u/Library/Mobile Documents/iCloud~md~obsidian/Documents/ytdlp/staging/Zanza/Irodalom/Cím"),
                         STAG / "Zanza" / "Irodalom" / "Cím")
        self.assertEqual(self.n("/Volumes/Work/Manifold-OS/var/state/Manifold-media/jobs/youtube-abc"), JOBS / "youtube-abc")
        self.assertEqual(self.n("/Volumes/Work/Manifold-OS/modulok/ytdlp/staging/Zanza/Történelem/A"), STAG / "Zanza" / "Történelem" / "A")

    def test_a_tobbi_alak_is_feloldodik(self):
        self.assertEqual(self.n("/Volumes/Work/Obsidian/ytdlp/staging/YouTube/Irodalom/X"), STAG / "YouTube" / "Irodalom" / "X")
        self.assertEqual(self.n("/Volumes/Work/Manifold-OS legacy/Legacy/modulok/ytdlp/staging/Zanza/I/A"), STAG / "Zanza" / "I" / "A")
        self.assertEqual(self.n("/Volumes/Work/Manifold-OS v2/var/state/Manifold-media/jobs/youtube-q/"), JOBS / "youtube-q")
        self.assertEqual(self.n("staging/Zanza/I/A"), STAG / "Zanza" / "I" / "A")
        self.assertEqual(self.n("jobs/youtube-r"), JOBS / "youtube-r")
        self.assertEqual(self.n("Zanza/Irodalom/A cím"), STAG / "Zanza" / "Irodalom" / "A cím")
        with mock.patch.dict(os.environ, {"HOME": "/Users/teszt"}):
            self.assertEqual(self.n("~/ytdlp/staging/Zanza/I/A"), STAG / "Zanza" / "I" / "A")

    def test_nfd_nev_nfc_re_alakul(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", "/Users/u/Documents/ytdlp/staging/Zanza/Irodalom/Bánk bán")
        self.assertEqual(self.n(nfd), STAG / "Zanza" / "Irodalom" / "Bánk bán")

    def test_ismeretlen_alak_none(self):
        for ut in ("/tmp/valami/mas", "/Users/u/Desktop/x", "", None, 5, "..", "../kifele"):
            self.assertIsNone(self.n(ut), ut)

    def test_alak_nevek(self):
        self.assertEqual([utnorm.alak(u) for u in (
            "/Users/u/Library/Application Support/Manifold-media/jobs/x", "/Users/u/Library/Mobile Documents/iCloud~md~obsidian/D",
            "/Volumes/Work/Manifold-OS/var/x", "/Volumes/Work/Manifold-OS legacy/Legacy/x", "/Volumes/Work/Manifold-OS v2/x",
            "/Volumes/Work/Obsidian/ytdlp/x", "~/x", "rel/x", "/ismeretlen")],
            ["app_support", "icloud", "regi_gyoker", "legacy", "v2", "kozbenso", "tilde", "relativ", "ismeretlen"])

    def test_felmeres_egy_ujgyokeru_allomanyon(self):
        with tmpdir() as t:
            jobs, stag = Path(t) / "jobs", Path(t) / "staging"
            (stag / "Zanza" / "Irodalom" / "Cím").mkdir(parents=True)
            for kulcs, mm, st in (
                    ("youtube-a", "/Users/u/Library/Application Support/Manifold-media/jobs/youtube-a",
                     "/Users/u/Library/Mobile Documents/iCloud~md~obsidian/Documents/ytdlp/staging/Zanza/Irodalom/Cím"),
                    ("youtube-b", "/Volumes/Work/Manifold-OS/var/state/Manifold-media/jobs/youtube-b",
                     "/Volumes/Work/Manifold-OS/modulok/ytdlp/staging/Zanza/Irodalom/Cím")):
                (jobs / kulcs).mkdir(parents=True)
                (jobs / kulcs / "state.json").write_text(json.dumps({
                    "munkamappa": mm, "staging": st, "lepesek": {"visszajelzes": {"mappa": st}}}), encoding="utf-8")
            (jobs / "youtube-c").mkdir()
            (jobs / "youtube-c" / "state.json").write_text("nem json", encoding="utf-8")
            r = utnorm.felmeres(jobs, stag)
            self.assertEqual(r["state_json"], 2)
            self.assertEqual(r["alakok"], {"app_support": 1, "icloud": 2, "regi_gyoker": 3})
            self.assertEqual(r["kulcsok"]["staging"], {"osszes": 2, "letezik": 2, "nem_oldhato": 0})
            self.assertEqual(r["kulcsok"]["munkamappa"]["letezik"], 2)
            self.assertEqual(len(r["olvasasi_hibak"]), 1)

    def test_a_tarolt_ut_nem_irodik_ujra(self):
        with tmpdir() as t:
            jobs = Path(t) / "jobs" / "youtube-a"
            jobs.mkdir(parents=True)
            szoveg = json.dumps({"munkamappa": "/Users/u/x/Manifold-media/jobs/youtube-a"})
            (jobs / "state.json").write_text(szoveg, encoding="utf-8")
            utnorm.felmeres(Path(t) / "jobs", Path(t))
            self.assertEqual((jobs / "state.json").read_text(encoding="utf-8"), szoveg)


class StagingTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.mappa = forras(self.d)

    def test_olvas_a_valodi_pipeline_kimenetet(self):
        s = staging.olvas(self.mappa)
        self.assertEqual((s["video_id"], s["cim"], s["targy"]), ("abc123", "Az ókori Athén", "Történelem"))
        self.assertEqual(Path(s["media"]).name, "video.mp4")
        self.assertFalse(s["atirat_kesz"], "az átirat a C20b: pending")
        self.assertEqual(staging.meta_min(s)["id"], "abc123")

    def test_a_forras_mappa_szerkezete(self):
        self.assertEqual(sorted(p.name for p in self.mappa.iterdir()),
                         ["integration.json", "metadata.json", "source.md", "transcript.md", "video.mp4"])
        self.assertEqual(json.loads((self.mappa / "integration.json").read_text(encoding="utf-8"))["integration_status"], "pending")

    def test_leltar_es_forrasmappak(self):
        masik = forras(self.d, "https://zanza.tv/tortenelem/masik", video_id="x2", cim="Másik")
        self.assertEqual(staging.forrasmappak(self.d / "staging"), sorted([str(self.mappa), str(masik)]))
        l = staging.leltar(self.d / "staging", {"abc123": "ATTCHMNTS - Videos/Az ókori Athén.mp4"})
        self.assertEqual({x["cim"]: (x["integration_status"], x["vaultban"]) for x in l},
                         {"Az ókori Athén": ("pending", "ATTCHMNTS - Videos/Az ókori Athén.mp4"), "Másik": ("pending", None)})
        self.assertEqual([x["hiba"] for x in l], [None, None])

    def test_hianyos_mappa_jelentett_nem_potolt(self):
        (self.mappa / "metadata.json").unlink()
        with self.assertRaises(staging.StagingHiba):
            staging.olvas(self.mappa)
        self.assertIn("metadata.json", staging.leltar(self.d / "staging")[0]["hiba"])

    def test_ures_media_hiba(self):
        (self.mappa / "video.mp4").write_bytes(b"")
        with self.assertRaises(staging.StagingHiba):
            staging.olvas(self.mappa)

    def test_visszajelez_egy_mezot_ir_atomi(self):
        elotte = json.loads((self.mappa / "integration.json").read_text(encoding="utf-8"))
        self.assertEqual((staging.visszajelez(self.mappa), staging.visszajelez(self.mappa)), ("irva", "mar_ez"))
        utana = json.loads((self.mappa / "integration.json").read_text(encoding="utf-8"))
        self.assertEqual({k for k in elotte if elotte[k] != utana.get(k)}, {"integration_status"})
        self.assertEqual(utana["integration_status"], "integrated")
        self.assertFalse(list(self.mappa.glob("*.manifold-tmp")))
        with self.assertRaises(ValueError):
            staging.visszajelez(self.mappa, "kitalalt")

    def test_keres_azonosito(self):
        self.assertEqual(staging.keres_azonosito("abc123", self.d / "staging"), str(self.mappa))
        self.assertIsNone(staging.keres_azonosito("nincs", self.d / "staging"))
        self.assertIsNone(staging.keres_azonosito(None, self.d / "staging"))
        self.assertIsNone(staging.keres_azonosito("abc123", self.d / "nincs"))


class KlonTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.f = self.d / "forras"
        for rel, b in (("Zanza/Irodalom/A/video.mp4", b"v" * 4096), ("Zanza/Irodalom/A/source.md", b"# a\n"), ("YouTube/B/video.mp4", b"w" * 100),
                       ("x/.DS_Store", b"")):
            (self.f / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.f / rel).write_bytes(b)
        (self.d / "arch").mkdir()
        (self.d / "arch" / "downloaded.txt").write_text("youtube abc\n", encoding="utf-8")

    def test_meretlista(self):
        m = klon.meretlista(self.f)
        self.assertEqual((m["fajl"], m["bajt"]), (4, 4096 + 4 + 100))
        self.assertEqual(m["agak"]["Zanza/Irodalom"], {"fajl": 2, "bajt": 4100})
        self.assertIn(".mp4", m["kiterjesztesek"])
        szoveg = klon.lista_szoveg(m, 10 * 1024 ** 3)
        self.assertIn("Zanza/Irodalom", szoveg)
        self.assertIn("szabad hely", szoveg)

    def test_igen_nelkul_csak_lista(self):
        r = klon.klonoz(self.f, self.d / "cel", igen=False, log=lambda s: None)
        self.assertFalse(r["klonozva"])
        self.assertFalse((self.d / "cel").exists())

    @unittest.skipUnless(sys.platform == "darwin", "[indokolt] APFS-klón (cp -c) csak macOS-en; K-tétel: tests/kezi/video_proba.py")
    def test_klon_apfs_en_bajtra_azonos_es_nem_foglal(self):
        cel = self.d / "uj" / "staging"
        r = klon.klonoz(self.f, cel, igen=True, archivum_forras=self.d / "arch", archivum_cel=self.d / "uj" / "archive", log=lambda s: None)
        self.assertTrue(r["klonozva"])
        self.assertEqual(klon.meretlista(cel)["bajt"], klon.meretlista(self.f)["bajt"])
        self.assertEqual((cel / "Zanza/Irodalom/A/video.mp4").read_bytes(), b"v" * 4096)
        self.assertEqual((self.d / "uj" / "archive" / "downloaded.txt").read_text(encoding="utf-8"), "youtube abc\n")
        (cel / "Zanza/Irodalom/A/video.mp4").write_bytes(b"modositva")        # a klón írása nem érinti a forrást
        self.assertEqual((self.f / "Zanza/Irodalom/A/video.mp4").read_bytes(), b"v" * 4096)

    def test_meglevo_celt_nem_ir_felul(self):
        (self.d / "cel").mkdir()
        (self.d / "cel" / "x").write_text("x", encoding="utf-8")
        with self.assertRaises(klon.KlonHiba):
            klon.klonoz(self.f, self.d / "cel", igen=True, log=lambda s: None)
        self.assertEqual((self.d / "cel" / "x").read_text(encoding="utf-8"), "x")

    def test_nem_letezo_forras(self):
        with self.assertRaises(klon.KlonHiba):
            klon.meretlista(self.d / "nincs")

    def test_valodi_masolat_gyanuja_hiba(self):
        """Ha a szabad hely a küszöbnél jobban fogy, a klón valódi másolatnak tűnik (más kötet, nem APFS)."""
        eredeti = klon.shutil.disk_usage
        hivasok = []

        def hamis(p):
            hivasok.append(p)
            u = eredeti(p)
            return type(u)(u.total, u.used, u.free - (0 if len(hivasok) == 1 else 500 * 1024 ** 2))
        with mock.patch.object(klon.shutil, "disk_usage", hamis), self.assertRaises(klon.KlonHiba):
            klon.klonoz(self.f, self.d / "cel2", igen=True, df_kuszob_bajt=100 * 1024 ** 2, log=lambda s: None)


FIX_MKV = """Input #0, matroska,webm, from 'x.mkv':
  Duration: 00:05:22.37, start: 0.000000, bitrate: 1543 kb/s
  Stream #0:0(eng): Video: h264 (High), yuv420p(tv, bt709, progressive), 1920x1080 [SAR 1:1 DAR 16:9], 30 fps (default)
  Stream #0:1(eng): Audio: aac (LC), 48000 Hz, stereo, fltp (default)
  Stream #0:2(eng): Subtitle: subrip (default)
"""
FIX_WEBM = """Input #0, matroska,webm, from 'x.webm':
  Duration: 00:01:00.00, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0(eng): Video: vp9 (Profile 0), yuv420p(tv, bt709), 1280x720, 30 fps (default)
  Stream #0:1(eng): Audio: opus, 48000 Hz, stereo, fltp (default)
"""
FIX_MP4_AV1 = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'video.mp4':
  Duration: 00:10:12.04, start: 0.000000, bitrate: 800 kb/s
  Stream #0:0[0x1](und): Video: av1 (Main) (av01 / 0x31307661), yuv420p(tv, bt709), 1280x720, 25 fps (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s (default)
"""
FIX_MP4_NATIV = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'video.mp4':
  Duration: 00:05:22.00, start: 0.000000, bitrate: 1543 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 1280x720 [SAR 1:1 DAR 16:9], 25 fps (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s (default)
  Stream #0:2: Video: mjpeg (Baseline), yuvj420p, 320x180, 90k tbr (attached pic)
"""
FIX_HEVC_MOV = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'a.mov':
  Duration: 00:00:30.00, start: 0.000000, bitrate: 5000 kb/s
  Stream #0:0(und): Video: hevc (Main) (hvc1 / 0x31637668), yuv420p(tv, bt709), 1920x1080, 30 fps (default)
  Stream #0:1(und): Audio: alac (alac / 0x63616C61), 44100 Hz, stereo, s16p (default)
"""
FIX_HANG = """Input #0, mp3, from 'a.mp3':
  Duration: 00:03:00.00, start: 0.025057, bitrate: 128 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 128 kb/s
"""


class FelmeresSzovegTeszt(unittest.TestCase):
    def test_mkv_h264_remux(self):
        f = konvertalas.felmeres_szoveg(FIX_MKV)
        self.assertEqual((f.konteneres, f.video, f.hang, f.hossz_s, f.szelesseg, f.magassag), ("matroska,webm", "h264", "aac", 322.37, 1920, 1080))
        self.assertFalse(konvertalas.nativ_e(f, ".mkv")[0])
        t = konvertalas.terv(f, ".mkv")
        self.assertEqual((t["mod"], t["video"], t["hang"]), ("remux", "copy", "copy"))

    def test_webm_vp9_opus_atkodol(self):
        f = konvertalas.felmeres_szoveg(FIX_WEBM)
        t = konvertalas.terv(f, ".webm")
        self.assertEqual((f.video, f.hang, t["mod"], t["video"], t["hang"]), ("vp9", "opus", "atkodol", "libx264", "aac"))

    def test_av1_mp4_nem_nativ_videokodek(self):
        f = konvertalas.felmeres_szoveg(FIX_MP4_AV1)
        ok, miert = konvertalas.nativ_e(f, ".mp4")
        self.assertFalse(ok)
        self.assertIn("av1", miert)
        t = konvertalas.terv(f, ".mp4")
        self.assertEqual((t["mod"], t["video"], t["hang"]), ("atkodol", "libx264", "copy"), "a natív AAC másolódik")

    def test_natív_mp4_a_borito_kep_nem_videofolyam(self):
        f = konvertalas.felmeres_szoveg(FIX_MP4_NATIV)
        self.assertEqual((f.video, f.hang), ("h264", "aac"), "az (attached pic) mjpeg nem számít")
        self.assertEqual(konvertalas.nativ_e(f, ".mp4"), (True, ""))
        self.assertEqual(konvertalas.terv(f, ".mp4")["mod"], "nativ")

    def test_hevc_mov_natív(self):
        f = konvertalas.felmeres_szoveg(FIX_HEVC_MOV)
        self.assertEqual(konvertalas.nativ_e(f, ".mov"), (True, ""))

    def test_nem_mp4_kiterjesztes_nem_nativ_meg_ha_a_tartalom_az(self):
        f = konvertalas.felmeres_szoveg(FIX_MP4_NATIV)
        self.assertFalse(konvertalas.nativ_e(f, ".mkv")[0])

    def test_hang_only(self):
        f = konvertalas.felmeres_szoveg(FIX_HANG)
        self.assertEqual((f.video, f.hang, f.hossz_s), (None, "mp3", 180.0))
        self.assertEqual(konvertalas.nativ_e(f, ".mp3")[1], "nem natív konténer (.mp3: mp3)")

    def test_ures_kimenet(self):
        self.assertEqual(konvertalas.felmeres_szoveg(""), konvertalas.Felmeres())

    def test_parancssor_nem_kodol_ujra_ha_nem_kell(self):
        f = konvertalas.felmeres_szoveg(FIX_MKV)
        cmd = konvertalas.parancs("ffmpeg", Path("a.mkv"), Path("a.mp4.part"), konvertalas.terv(f, ".mkv"), f, crf=19, szal=3)
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "copy")
        self.assertIn("+faststart", cmd)
        self.assertEqual(cmd[cmd.index("-threads") + 1], "3")
        self.assertIn("-sn", cmd)
        f2 = konvertalas.felmeres_szoveg(FIX_WEBM)
        cmd2 = konvertalas.parancs("ffmpeg", Path("a.webm"), Path("a.mp4.part"), konvertalas.terv(f2, ".webm"), f2, crf=19)
        self.assertEqual(cmd2[cmd2.index("-c:v") + 1], "libx264")
        self.assertEqual(cmd2[cmd2.index("-crf") + 1], "19")
        self.assertEqual(cmd2[cmd2.index("-c:a") + 1], "aac")

    def test_hevc_copy_hvc1_cimkevel(self):
        f = konvertalas.felmeres_szoveg(FIX_HEVC_MOV)
        cmd = konvertalas.parancs("ffmpeg", Path("a.mov"), Path("o"), {"video": "copy", "hang": "copy"}, f)
        self.assertIn("hvc1", cmd)

    def test_ellenorzes(self):
        a = konvertalas.Felmeres("m", "h264", "aac", 100.0)
        konvertalas._ellenoriz(a, konvertalas.Felmeres("m", "h264", "aac", 100.5))
        for rossz in (konvertalas.Felmeres("m", None, "aac", 100.0), konvertalas.Felmeres("m", "h264", None, 100.0),
                      konvertalas.Felmeres("m", "h264", "aac", 90.0), konvertalas.Felmeres("m", "h264", "aac", None)):
            with self.assertRaises(konvertalas.KonvertalasHiba):
                konvertalas._ellenoriz(a, rossz)


@unittest.skipUnless(ffmpeg_elerheto(), ELOK)
class ValodiKonvertalasTeszt(unittest.TestCase):
    """A pinelt ffmpeg-gel, szintetikus 2 s-os fájlokon (lavfi): MKV remux, WebM és AV1-mp4 újrakódolás, natív érintetlen."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.ff = str(FFMPEG)
        self.arch = self.d / "arch"

    def konv(self, fajl: Path, **kw):
        return konvertalas.konvertal(self.ff, fajl, eredeti_gyoker=self.arch, relativ="Zanza/A", log=lambda s: None, **kw)

    def kimenet_nativ(self, ut) -> konvertalas.Felmeres:
        f = konvertalas.felmeres(self.ff, ut)
        self.assertEqual(konvertalas.nativ_e(f, Path(ut).suffix), (True, ""), f)
        return f

    def test_mkv_h264_aac_remux(self):
        mkv = szintetikus_video(self.d / "s" / "video.mkv", "libx264", "mkv", "aac")
        r = self.konv(mkv)
        self.assertEqual((r["mod"], Path(r["ut"]).name), ("remux", "video.mp4"))
        f = self.kimenet_nativ(r["ut"])
        self.assertAlmostEqual(f.hossz_s, 2.0, delta=0.2)
        self.assertFalse(mkv.exists())
        self.assertTrue((self.arch / "Zanza" / "A" / "video.mkv").exists(), "az eredeti az archive alá került")
        self.assertTrue((self.arch / "INDOK.md").exists())

    def test_webm_vp9_opus_atkodolas(self):
        w = szintetikus_video(self.d / "s" / "video.webm", "libvpx-vp9", "webm", "libopus")
        r = self.konv(w)
        self.assertEqual(r["mod"], "atkodol")
        f = self.kimenet_nativ(r["ut"])
        self.assertEqual((f.video, f.hang), ("h264", "aac"))
        self.assertTrue((self.arch / "Zanza" / "A" / "video.webm").exists())

    def test_av1_mp4_a_helyere_kerul_az_eredeti_archivalva(self):
        a = szintetikus_video(self.d / "s" / "video.mp4", "libsvtav1", "mp4", "aac")
        eredeti = a.read_bytes()
        r = self.konv(a)
        self.assertEqual((r["mod"], r["ut"]), ("atkodol", str(a)))
        self.kimenet_nativ(a)
        self.assertEqual((self.arch / "Zanza" / "A" / "video.mp4").read_bytes(), eredeti, "az AV1 eredeti változatlanul archivált")
        self.assertNotEqual(a.read_bytes(), eredeti)

    def test_natív_fajlhoz_nem_nyul(self):
        n = szintetikus_video(self.d / "s" / "video.mp4", "libx264", "mp4", "aac")
        bajtok = n.read_bytes()
        r = self.konv(n)
        self.assertEqual((r["mod"], r["eredeti"]), ("nativ", None))
        self.assertEqual(n.read_bytes(), bajtok)
        self.assertFalse(self.arch.exists())

    def test_eredeti_nev_marad_ha_nincs_archivum_gyoker(self):
        mkv = szintetikus_video(self.d / "s" / "video.mkv", "libx264", "mkv", "aac")
        r = konvertalas.konvertal(self.ff, mkv, eredeti_gyoker=None, log=lambda s: None)
        self.assertEqual(Path(r["eredeti"]).name, "video.mkv.eredeti")
        self.assertTrue(Path(r["eredeti"]).exists())

    def test_nem_video_fajl_kihagyva_erintetlenul(self):
        rossz = self.d / "s" / "video.mkv"
        rossz.parent.mkdir(parents=True)
        rossz.write_bytes(b"ez nem video")
        self.assertEqual(self.konv(rossz)["mod"], "kihagy")
        self.assertEqual(rossz.read_bytes(), b"ez nem video")
        self.assertEqual([p.name for p in rossz.parent.iterdir()], ["video.mkv"])

    def test_audio_only_kihagyva(self):
        h = self.d / "s" / "a.m4a"
        h.parent.mkdir(parents=True)
        import subprocess
        subprocess.run([self.ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", str(h)], check=True)
        self.assertEqual(self.konv(h)["mod"], "kihagy")

    def test_a_felmeres_a_valodi_ffmpeg_kimenetet_olvassa(self):
        mkv = szintetikus_video(self.d / "v.mkv", "libx264", "mkv", "aac")
        f = konvertalas.felmeres(self.ff, mkv)
        self.assertEqual((f.video, f.hang, f.szelesseg, f.magassag), ("h264", "aac", 320, 240))
        self.assertIn("matroska", f.konteneres)


FAKE_FFMPEG = """#!/bin/sh
# hamis ffmpeg: a próba (-i, kimenet nélkül) rögzített kimenetet ad; a konvertálás (-progress) a MOD szerint hibázik vagy hamis eredményt ír
case "$*" in
  *-progress*)
    if [ "$MOD" = "hiba" ]; then echo "Error: boom" >&2; exit 3; fi
    for utolso; do :; done
    printf 'x' > "$utolso"; exit 0 ;;
  *.part*)
    cat >&2 <<'VEGE'
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.part':
  Duration: 00:00:02.00, start: 0.000000, bitrate: 100 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 1280x720, 30 fps
  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp
VEGE
    exit 1 ;;
  *)
    cat >&2 <<'VEGE'
Input #0, matroska,webm, from 'video.webm':
  Duration: 00:00:10.00, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0: Video: vp9 (Profile 0), yuv420p, 1280x720, 30 fps
  Stream #0:1: Audio: opus, 48000 Hz, stereo, fltp
VEGE
    exit 1 ;;
esac
"""


class HibaagakTeszt(unittest.TestCase):
    """A konvertálás hibaágai hamis ffmpeg-gel (a bináris nélkül is fut): az eredeti érintetlen, nincs maradék `.part`."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.ff = self.d / "ffmpeg"
        self.ff.write_text(FAKE_FFMPEG, encoding="utf-8")
        self.ff.chmod(0o755)
        self.video = self.d / "s" / "video.webm"
        self.video.parent.mkdir()
        self.video.write_bytes(b"eredeti")

    def _futtat(self, mod: str):
        with mock.patch.dict(os.environ, {"MOD": mod}):
            return konvertalas.konvertal(str(self.ff), self.video, eredeti_gyoker=self.d / "arch", log=lambda s: None)

    def test_az_ffmpeg_hibaja(self):
        with self.assertRaises(konvertalas.KonvertalasHiba) as cm:
            self._futtat("hiba")
        self.assertIn("boom", str(cm.exception))
        self.assertEqual([p.name for p in self.video.parent.iterdir()], ["video.webm"])
        self.assertEqual(self.video.read_bytes(), b"eredeti")
        self.assertFalse((self.d / "arch").exists())

    def test_hamis_hosszu_eredmeny_elutasitva(self):
        """Az ffmpeg 0-val tér vissza, de a kimenet hossza (2 s) a forrásétól (10 s) eltér: nem kerül a helyére."""
        with self.assertRaises(konvertalas.KonvertalasHiba) as cm:
            self._futtat("sikeres")
        self.assertIn("hossz", str(cm.exception))
        self.assertEqual([p.name for p in self.video.parent.iterdir()], ["video.webm"])
        self.assertEqual(self.video.read_bytes(), b"eredeti")


if __name__ == "__main__":
    unittest.main()
