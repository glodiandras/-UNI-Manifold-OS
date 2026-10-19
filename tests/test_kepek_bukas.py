"""A kicsinyítés és a videó-poszter bukás-memója (2026-10-14, F1): a bukott kulcs a lejáratig nem próbálkozik újra,
a bukás egyszer kerül a naplóba, és a poszter időtúllépése nem futtatja kétszer az ffmpeg-et. Álkönyvtárban, a vault nélkül."""
import contextlib
import io
import os
import stat
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from core import kepek
from tests.helpers import tmpdir


class _Cfg:
    def __init__(self, gyoker: Path):
        self.gyoker = gyoker

    def path(self, kulcs):
        assert kulcs == "vault_kepek"
        return self.gyoker / "vault-kepek"


class BukasMemoTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.cfg = _Cfg(self.d)
        kepek._bukasok.clear()
        self.addCleanup(kepek._bukasok.clear)
        self.kep = self.d / "nagy.jpg"
        self.kep.write_bytes(b"\xff\xd8\xff nem igazi kep")

    def test_a_bukott_kicsinyites_nem_probalkozik_ujra_es_egyszer_naploz(self):
        hivas = []

        def bukik(*a, **k):
            hivas.append(1)
            raise MemoryError("dekódolás")
        hiba = io.StringIO()
        with mock.patch.object(kepek, "_keszit", bukik), contextlib.redirect_stderr(hiba):
            for _ in range(5):
                self.assertEqual(kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 800), (self.kep, "image/jpeg"))
        self.assertEqual(len(hivas), 1)
        self.assertEqual(hiba.getvalue().count("[kepek]"), 1)
        self.assertIn("nagy.jpg", hiba.getvalue())
        self.assertNotIn(str(self.d), hiba.getvalue())                 # abszolút út nem kerül a naplóba
        # más vödör: más kulcs, újra próbál
        with mock.patch.object(kepek, "_keszit", bukik), contextlib.redirect_stderr(io.StringIO()):
            kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 400)
        self.assertEqual(len(hivas), 2)

    def test_a_memo_lejar_es_a_modosult_kep_uj_kulcs(self):
        hivas = []

        def bukik(*a, **k):
            hivas.append(1)
            raise OSError("x")
        with mock.patch.object(kepek, "_keszit", bukik), contextlib.redirect_stderr(io.StringIO()):
            kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 800)
            os.utime(self.kep, (2_000_000_000, 2_000_000_000))           # módosult kép: új kulcs, új próba
            kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 800)
            self.assertEqual(len(hivas), 2)
            with mock.patch.object(kepek, "BUKAS_LEJARAT_MP", 0):
                kepek._bukasok.clear()
                kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 800)
                kepek.kicsinyitett(self.cfg, self.kep, "image/jpeg", 800)  # azonnal lejárt: újra próbál
            self.assertEqual(len(hivas), 4)

    def test_a_memo_korlatos(self):
        with mock.patch.object(kepek, "BUKAS_MAX", 10), contextlib.redirect_stderr(io.StringIO()):
            for i in range(50):
                kepek._bukas(f"{i:040x}", "próba", self.kep, "x")
        self.assertEqual(len(kepek._bukasok), 10)
        self.assertIn(f"{49:040x}", kepek._bukasok)

    def _ffmpeg(self, szoveg: str) -> Path:
        ff = self.d / "ffmpeg"
        ff.write_text(szoveg)
        ff.chmod(ff.stat().st_mode | stat.S_IXUSR)
        return ff

    def test_a_poszter_idotullepese_egyszer_futtatja_az_ffmpeget(self):
        ff = self._ffmpeg('#!/bin/sh\nexec /bin/sleep 5\n')
        video = self.d / "v.mp4"
        video.write_bytes(b"\0" * 64)
        hiba = io.StringIO()
        eredeti_futtat = subprocess.run
        idotullepesek = []

        def futtat(*a, **k):
            try:
                return eredeti_futtat(*a, **k)
            except subprocess.TimeoutExpired:
                idotullepesek.append(True)
                raise

        with mock.patch.object(kepek, "_ffmpeg", lambda cfg: ff), mock.patch.object(kepek, "POSZTER_IDOKORLAT_MP", 0.3), \
                mock.patch.object(kepek.subprocess, "run", wraps=futtat) as futas, \
                contextlib.redirect_stderr(hiba):
            t0 = time.monotonic()
            self.assertIsNone(kepek.poszter(self.cfg, video))
            self.assertIsNone(kepek.poszter(self.cfg, video))           # a memóból: nem indít ffmpeg-et
            self.assertLess(time.monotonic() - t0, 3)
        # A timeout még a gyermek első mellékhatása előtt is lejárhat terhelt gépen.
        # A tényleges indítási kísérletet mérjük, valódi OS-időtúllépéssel; nincs második kocka vagy memo-retry.
        self.assertEqual(futas.call_count, 1)
        self.assertEqual(idotullepesek, [True])
        self.assertEqual(hiba.getvalue().count("[kepek]"), 1)

    def test_a_poszter_hibaja_a_memoba_kerul(self):
        naplo = self.d / "hivasok.txt"
        ff = self._ffmpeg(f'#!/bin/sh\necho x >> "{naplo}"\nexit 1\n')
        video = self.d / "v.mp4"
        video.write_bytes(b"\0" * 64)
        with mock.patch.object(kepek, "_ffmpeg", lambda cfg: ff), contextlib.redirect_stderr(io.StringIO()):
            for _ in range(3):
                self.assertIsNone(kepek.poszter(self.cfg, video))
        self.assertEqual(naplo.read_text().count("x"), 2)               # az első kérés: a t és a 0. kocka; utána a memó

    def test_az_ffmpeg_ellenorzes_hibaja_is_a_memoba(self):
        video = self.d / "v.mp4"
        video.write_bytes(b"\0" * 64)
        hivas = []

        def rossz(cfg):
            hivas.append(1)
            raise RuntimeError("pin hiányzik")
        with mock.patch.object(kepek, "_ffmpeg", rossz), contextlib.redirect_stderr(io.StringIO()):
            kepek.poszter(self.cfg, video)
            kepek.poszter(self.cfg, video)
        self.assertEqual(len(hivas), 1)


if __name__ == "__main__":
    unittest.main()
