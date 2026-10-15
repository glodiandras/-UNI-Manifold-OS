"""C20b: a hang-háttér (mlx-whisper) útja a workeren át — álháttérrel, és a hang dekódolása a pinelt ffmpeg-gel."""
import os
import shutil
import struct
import subprocess
import threading
import unittest
import wave
from pathlib import Path

from core import config
from core.modell import eval as E
from core.modell import hatter as H
from core.modell import kliens
from core.modell.kalibracio import Tabla
from core.modell.worker import Gazda, Szerver, _handler
from tests.helpers import alg_core, tmpdir
from tests.modell_segedek import AlAktivitas, AlHatter, al_betolto, beallitas


def _wav(ut: Path, mp: float = 1.0, hz: int = 8000) -> Path:
    with wave.open(str(ut), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(b"".join(struct.pack("<h", (i % 40) * 500 - 10000) for i in range(int(mp * hz))))
    return ut


class AtiratWorkerTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.tabla = Tabla(self.b.router_db)
        self.g = Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla, tick_mp=0.02, naplo=lambda s: None)
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.u = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(self._leall)
        self.hang = str(_wav(Path(self._t.name) / "a.wav"))

    def _leall(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.g.utemezo.leall()
        self.tabla.close()

    def test_kalibralt_nelkul_409_proba_megy(self):
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.atir(self.u, self.hang)
        self.assertEqual(cm.exception.kod, 409)                       # D9: nincs kalibrált `atirat`
        r = kliens.atir(self.u, self.hang, modell="whisper_turbo_mlx")
        self.assertTrue(r["proba"])
        self.assertEqual(r["modell"], "whisper_turbo_mlx")
        self.assertEqual([s["text"] for s in r["szegmensek"]], ["Első mondat.", "Második mondat."])
        self.assertIn(("atir", "whisper_turbo_mlx", self.hang, "hu"), AlHatter.naplo)

    def test_kalibralt_feladat(self):
        self.tabla.rogzit("atirat", "whisper_turbo_mlx", 0.8, "v1", kalibralt=True)
        r = kliens.atir(self.u, self.hang)
        self.assertFalse(r["proba"])
        self.assertEqual((r["feladat"], r["modell"], r["hossz_mp"]), ("atirat", "whisper_turbo_mlx", 7.5))

    def test_ervenytelen_keres(self):
        for body in ({"audio": "relativ.wav"}, {"audio": 3}, {"audio": self.hang, "nyelv": "hu; rm"}):
            with self.assertRaises(kliens.KliensHiba) as cm:
                kliens.keres(self.u, "/v1/audio/transcriptions", {**body, "mod": "interaktiv", "model": "whisper_turbo_mlx",
                                                                  "proba": True})
            self.assertEqual(cm.exception.kod, 400, body)

    def test_mero_hivas(self):
        szoveg, extra = E._hiv(self.u, "whisper_turbo_mlx", {"tipus": "atirat", "audio": self.hang, "nyelv": "hu"},
                               None, "interaktiv")
        self.assertEqual(szoveg, "Első mondat. Második mondat.")
        self.assertEqual(extra["szegmens_db"], 2)

    def test_ujjlenyomat_a_hang_tartalmatol_fugg_nem_az_uttol(self):
        m = self.b.modell("whisper_turbo_mlx")
        masik = Path(self._t.name) / "b.wav"
        shutil.copy(self.hang, masik)
        k1 = {"tipus": "atirat", "audio": self.hang, "nyelv": "hu"}
        self.assertEqual(E.ujjlenyomat(m, k1), E.ujjlenyomat(m, {**k1, "audio": str(masik)}))
        _wav(masik, mp=2.0)
        self.assertNotEqual(E.ujjlenyomat(m, k1), E.ujjlenyomat(m, {**k1, "audio": str(masik)}))


class HangDekodolasTest(unittest.TestCase):
    """A valódi pinelt ffmpeg-gel (a `runtime/` alatt); nélküle a teszt kihagyódik (a doctor amúgy is HIBÁT ad)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.ff = config.load().path("ffmpeg")
        if not self.ff.is_file():
            self.skipTest("nincs pinelt ffmpeg a runtime/ alatt")

    def test_16khz_mono_tomb(self):
        t = H.hang_tomb(str(_wav(Path(self._t.name) / "a.wav", mp=1.5)), ffmpeg=str(self.ff))
        self.assertEqual(t.dtype.name, "float32")
        self.assertAlmostEqual(len(t) / H.HANG_MINTAVETEL, 1.5, delta=0.01)
        self.assertLessEqual(float(abs(t).max()), 1.0)

    def test_videobol_a_hangsav(self):
        ki = Path(self._t.name) / "v.mp4"
        subprocess.run([str(self.ff), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-c:v", "libx264",
                        "-c:a", "aac", str(ki)], check=True, capture_output=True)
        t = H.hang_tomb(str(ki), ffmpeg=str(self.ff))
        self.assertAlmostEqual(len(t) / H.HANG_MINTAVETEL, 1.0, delta=0.1)

    def test_hibak(self):
        with self.assertRaises(H.BetoltesHiba):
            H.hang_tomb("relativ.wav", ffmpeg=str(self.ff))
        with self.assertRaises(H.BetoltesHiba):
            H.hang_tomb(os.path.join(self._t.name, "nincs.wav"), ffmpeg=str(self.ff))
        rossz = Path(self._t.name) / "rossz.wav"
        rossz.write_bytes(b"nem hang")
        with self.assertRaises(H.BetoltesHiba):
            H.hang_tomb(str(rossz), ffmpeg=str(self.ff))
        kep = Path(self._t.name) / "csak_kep.mp4"
        subprocess.run([str(self.ff), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
                        "-c:v", "libx264", str(kep)], check=True, capture_output=True)
        with self.assertRaises(H.BetoltesHiba):
            H.hang_tomb(str(kep), ffmpeg=str(self.ff))

    def test_gyar(self):
        b = beallitas(alg_core(self._t.name)[0])
        self.assertIsInstance(H.gyar(b.modell("whisper_turbo_mlx")), H.MlxWhisper)
        with self.assertRaises(H.BetoltesHiba):
            H.gyar(b.modell("parakeet_v3"))


if __name__ == "__main__":
    unittest.main()
