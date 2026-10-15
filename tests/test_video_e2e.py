"""C20a: a lánc a VALÓDI yt-dlp-vel, a valódi `msp`-pipeline-nal és a pinelt ffmpeg-gel — külső hálózat nélkül: egy 127.0.0.1-en futó teszt-szerver
szolgál egy szintetikus videót, a yt-dlp általános (generic) kinyerője tölti le. A feladat `plan()`-ja a helyi címet elutasítja (a core ne tudjon a
saját helyi címén letöltetni), ezért itt a lépést közvetlenül hívjuk (`lanc.letoltes`, és alfolyamatban a `python -m modulok.ytdlp lepes letoltes`)."""
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from modulok.ytdlp import konvertalas, lanc
from tests.helpers import REPO, alg_core, env, tmpdir
from tests.video_segedek import FFMPEG, ffmpeg_elerheto, pin_es_ffmpeg, szintetikus_video

ELOK = "[indokolt] nincs runtime/ffmpeg (bin/mos runtime fetch ffmpeg)"


class _Csendes(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipUnless(ffmpeg_elerheto(), ELOK)
class ValodiLancTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.cfg, self.root, self.v = alg_core(self.d.as_posix())
        (self.root / "modulok" / "ytdlp" / "config").mkdir(parents=True)
        (self.root / "modulok" / "ytdlp" / "config" / "config.yaml").write_text(
            (REPO / "modulok" / "ytdlp" / "config" / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        self.szerv = self.d / "szerv"
        self.szerv.mkdir()
        h = functools.partial(_Csendes, directory=str(self.szerv))
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.port = self.srv.server_address[1]
        pin_es_ffmpeg(self.cfg, self.root, valodi=FFMPEG)         # A3-17: a pinelt, hash-ellenőrzött `[utak] ffmpeg`, nem a környezet
        self.proba = self.d / "proba"

    def url(self, nev: str) -> str:
        return f"http://127.0.0.1:{self.port}/{nev}"

    def futtat(self, urlek, **kw):
        sorok: list[str] = []
        rc = lanc.letoltes(self.cfg, urlek, proba_gyoker=self.proba, log=sorok.append, **kw)
        return rc, "\n".join(sorok)

    def forrasmappak(self):
        return [p.parent for p in (self.proba / "staging").rglob("integration.json")]

    def test_mkv_remux_a_stagingbe(self):
        szintetikus_video(self.szerv / "proba.mkv", "libx264", "mkv", "aac", mp=3)
        rc, ki = self.futtat([self.url("proba.mkv")])
        self.assertEqual(rc, 0, ki)
        self.assertIn("konvertálva (remux", ki)
        (mappa,) = self.forrasmappak()
        self.assertEqual(sorted(p.name for p in mappa.iterdir()), ["integration.json", "metadata.json", "source.md", "transcript.md", "video.mp4"])
        self.assertEqual(json.loads((mappa / "integration.json").read_text(encoding="utf-8"))["media"], "video.mp4")
        f = konvertalas.felmeres(str(FFMPEG), mappa / "video.mp4")
        self.assertEqual(konvertalas.nativ_e(f, ".mp4"), (True, ""))
        self.assertAlmostEqual(f.hossz_s, 3.0, delta=0.3)
        self.assertEqual(len(list((self.proba / "eredeti").rglob("video.mkv"))), 1, "az eredeti archivált, nem törölt")
        self.assertEqual(json.loads((mappa / "integration.json").read_text(encoding="utf-8"))["integration_status"], "pending")

    def test_webm_vp9_atkodolva(self):
        szintetikus_video(self.szerv / "w.webm", "libvpx-vp9", "webm", "libopus", mp=2)
        rc, ki = self.futtat([self.url("w.webm")])
        self.assertEqual(rc, 0, ki)
        self.assertIn("konvertálva (atkodol", ki)
        (mappa,) = self.forrasmappak()
        f = konvertalas.felmeres(str(FFMPEG), mappa / "video.mp4")
        self.assertEqual((f.video, f.hang), ("h264", "aac"))

    def test_natív_mp4_valtozatlan_es_a_masodik_futas_mar_megvan(self):
        szintetikus_video(self.szerv / "n.mp4", "libx264", "mp4", "aac", mp=2)
        rc, ki = self.futtat([self.url("n.mp4")])
        self.assertEqual(rc, 0, ki)
        self.assertNotIn("konvertálva", ki)
        self.assertFalse((self.proba / "eredeti").exists())
        (mappa,) = self.forrasmappak()
        self.assertEqual((mappa / "video.mp4").read_bytes(), (self.szerv / "n.mp4").read_bytes(), "a natív fájl bájtra azonos")
        rc2, ki2 = self.futtat([self.url("n.mp4")])
        self.assertEqual(rc2, 0)
        self.assertIn("Már megvan", ki2)
        self.assertEqual(len(self.forrasmappak()), 1)

    def test_hibas_link_nem_viszi_el_a_tobbit(self):
        szintetikus_video(self.szerv / "j.mp4", "libx264", "mp4", "aac", mp=2)
        rc, ki = self.futtat([self.url("nincs-ilyen.mp4"), self.url("j.mp4")])
        self.assertEqual(rc, 1, ki)
        self.assertIn("Hiba:", ki)
        self.assertIn("1 letöltve", ki)
        self.assertEqual(len(self.forrasmappak()), 1)

    def test_a_lepes_alfolyamatban_a_cli_bekoteseivel(self):
        """A feladatsor ezt a parancssort futtatja (`core/videolanc.py`): `python -m modulok.ytdlp lepes letoltes --url … --proba-gyoker …`."""
        szintetikus_video(self.szerv / "c.mkv", "libx264", "mkv", "aac", mp=2)
        e = env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO), MANIFOLD_STOP_FAJL=str(self.d / "nincs-stop"),
                MOS_VIDEO_HELYI_ENGEDELY="1")        # csak a teszt: a loopback szerverhez (a hálózat-őr egyébként tiltja, A3-13)
        p = subprocess.run([sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "letoltes", "--url", self.url("c.mkv"),
                            "--proba-gyoker", str(self.proba)], cwd=REPO, env=e, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout[-1500:] + p.stderr[-1500:])
        self.assertIn("[manifold-progress] 100%", p.stdout)
        self.assertIn("Összegzés: 1 letöltve", p.stdout)
        self.assertEqual(len(list((self.proba / "staging").rglob("video.mp4"))), 1)


if __name__ == "__main__":
    unittest.main()
