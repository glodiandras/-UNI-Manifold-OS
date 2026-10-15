"""Javító 3 (Audit 3: A3-08…A3-22): a videólánc (C20a) keményítése — leletenként a repró, hálózat nélkül (a yt-dlp és az ffmpeg álhívóval).

Ideiglenes álgyökérben és álvaultban fut, a valódi vaulthoz és var/-hoz nem nyúl. A teszt platformfüggetlen (a `rename_excl` Linuxon a
létezés-ellenőrzéses tartalékkal fut). Az A3-12 (a lépés a teljes API-titkot kapja) a Mac-main T137 lépés-tokenjétől függ: ott csak váz van."""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from core import binaris_naplo as bn
from core import frame, mediatipus, snapshot, videolanc
from modulok.ytdlp import konvertalas, lanc, staging
from tests.helpers import alg_core, tmpdir
from tests.test_video_staging import FAKE_FFMPEG
from tests.video_segedek import hamis_letolto, msp, pin_es_ffmpeg

URL = "https://zanza.tv/tortenelem/az-okori-athen"


def lepes(cfg, urlek, **kw):
    import io
    ki = io.StringIO()
    with redirect_stdout(ki):
        rc = lanc.letoltes(cfg, list(urlek), log=lambda s: print(s), **kw)
    return rc, ki.getvalue()


# ------------------------------------------------------------------ A3-08, A3-09

class PillanatUtanTeszt(unittest.TestCase):
    """A3-08: a lánc gépi commitja csak a saját útjait (célmappák, archívum) viszi; a kód és a konfig soha."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ytdlp = self.cfg.path("ytdlp")
        (self.ytdlp / "src").mkdir(parents=True)
        (self.ytdlp / "config").mkdir()
        (self.ytdlp / "src" / "kod.py").write_text("# régi\n", encoding="utf-8")
        (self.ytdlp / "config" / "config.yaml").write_text("a: 1\n", encoding="utf-8")
        self.repo = snapshot.repos(self.cfg)["ytdlp"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        pin_es_ffmpeg(self.cfg, self.root)

    def futtat(self, letolto, urlek=(URL,)):
        _, modul, _ = msp()
        with mock.patch.object(modul, "create_downloader", return_value=letolto):
            return lepes(self.cfg, urlek)

    def test_a_letoltes_kozben_szerkesztett_kod_es_konfig_nem_kerul_a_gepi_commitba(self):
        l = hamis_letolto()
        eredeti = l.download

        def download(kerelem):
            (self.ytdlp / "src" / "kod.py").write_text("# a felhasználó közben szerkeszti\n", encoding="utf-8")
            (self.ytdlp / "config" / "config.yaml").write_text("a: 2\n", encoding="utf-8")
            (self.ytdlp / "src" / "uj.py").write_text("x = 1\n", encoding="utf-8")
            return eredeti(kerelem)
        l.download = download
        rc, ki = self.futtat(l)
        self.assertEqual(rc, 0, ki)
        gepi = [c for c in self.repo.log(10) if c.trailers.get("Mos-Forras") == "mos-video"]
        self.assertEqual(len(gepi), 1)
        fajlok = {f["ut"] for f in self.repo.commit_fajlok(gepi[0].sha)}
        self.assertTrue(any(f.endswith("metadata.json") for f in fajlok), fajlok)
        self.assertEqual({f for f in fajlok if not (f.startswith("staging/") or f.startswith("archive/"))}, set(), fajlok)
        # a felhasználó közbeni változása a `commit_machine` előtti külön `kezi` commitba került (L14), a gépi commitba nem
        self.assertEqual(self.repo.dirty(), [])
        kezi = [c for c in self.repo.log(10) if c.trailers.get("Mos-Forras") == "kezi" and c.subject != "alap"]
        self.assertEqual({f["ut"] for c in kezi for f in self.repo.commit_fajlok(c.sha)}, {"src/kod.py", "config/config.yaml", "src/uj.py"})

    def test_celok_nelkul_nincs_gepi_commit(self):
        (self.ytdlp / "src" / "kod.py").write_text("# módosított\n", encoding="utf-8")
        self.assertIsNone(lanc.pillanat_utan(self.cfg, 0, log=lambda s: None, celok=[]))
        self.assertEqual([c.trailers.get("Mos-Forras") for c in self.repo.log(5)], ["kezi"])

    def test_a_celon_kivuli_ut_kimarad_a_celon_beluli_bekerul(self):
        mappa = self.cfg.path("staging") / "Zanza" / "Tortenelem" / "Cim"
        mappa.mkdir(parents=True)
        (mappa / "metadata.json").write_text("{}\n", encoding="utf-8")
        (self.ytdlp / "src" / "kod.py").write_text("# módosított\n", encoding="utf-8")
        sha = lanc.pillanat_utan(self.cfg, 1, log=lambda s: None, celok=[mappa])
        self.assertTrue(sha)
        self.assertEqual({f["ut"] for f in self.repo.commit_fajlok(sha)}, {"staging/Zanza/Tortenelem/Cim/metadata.json"})

    def test_a_staging_melletti_testvermappa_nem_celon_belul(self):
        """Az előtag-egyezés útszegmensre áll: a `Cim` célmappa nem viszi a `Cim-masik`-et."""
        a, b = (self.cfg.path("staging") / n for n in ("Cim", "Cim-masik"))
        for m in (a, b):
            m.mkdir(parents=True)
            (m / "metadata.json").write_text("{}\n", encoding="utf-8")
        sha = lanc.pillanat_utan(self.cfg, 1, log=lambda s: None, celok=[a])
        self.assertEqual({f["ut"] for f in self.repo.commit_fajlok(sha)}, {"staging/Cim/metadata.json"})


class BinarisFajlokNemKerulnekATarbaTeszt(unittest.TestCase):
    """A3-09: az `.eredeti`, `.part`, `.ytdl`, `.temp` és a hiányzó médiabővítmények kizártak (egy forrás: `core/mediatipus.py`)."""
    UJ = (".eredeti", ".part", ".ytdl", ".temp", ".mts", ".mpg", ".wmv", ".aiff")

    def test_a_kizarolista_tartalmazza_kis_es_nagybetuvel(self):
        mintak = set(mediatipus.kizar_mintak())
        for kit in self.UJ:
            self.assertIn(f"*{kit}", mintak, kit)
            self.assertIn(f"*{kit.upper()}", mintak, kit)
            self.assertTrue(mediatipus.binaris_e(f"x/video.mkv{kit}"), kit)

    def test_az_ytdlp_tar_nem_latja_ezeket_a_fajlokat(self):
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
            (cfg.path("ytdlp") / "staging" / "a").mkdir(parents=True)
            repo = snapshot.repos(cfg)["ytdlp"]
            repo.init()
            for nev in ("video.mkv.eredeti", "video.mp4.part", "video.f137.mp4.ytdl", "x.temp", "k.mts", "k.mpg", "k.wmv", "k.aiff"):
                (cfg.path("ytdlp") / "staging" / "a" / nev).write_bytes(b"\0\1\2")
            (cfg.path("ytdlp") / "staging" / "a" / "metadata.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual([ln[3:] for ln in repo.dirty()], ["staging/a/metadata.json"])

    def test_a_media_url_es_az_index_listaja_nem_bovult(self):
        """A `.mts`, `.mpg`, `.wmv`, `.aiff` nem kiszolgált média (a WKWebView nem játssza): csak a kizárás bővült."""
        for kit in (".mts", ".mpg", ".wmv", ".aiff", ".eredeti"):
            self.assertNotIn(kit, mediatipus.MEDIA_TIPUS)


class SzovegesSzuroTeszt(unittest.TestCase):
    """A3-09: a gépi commit útlistája tartalom (NUL-bájt) és méret szerint is szűrt."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)

    def ir(self, rel: str, b: bytes) -> str:
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
        return rel

    def test_nul_bajtos_es_nagy_fajl_kimarad(self):
        jo = self.ir("staging/a/metadata.json", b'{"a": 1}\n')
        szoveg = self.ir("staging/a/source.md", "# Cím — ékezetes\n".encode("utf-8"))
        nul = self.ir("staging/a/video.dat", b"abc\0def")
        nagy = self.ir("staging/a/nagy.txt", b"a" * 5000)
        ures = self.ir("staging/a/ures.json", b"")
        self.assertEqual(lanc.szoveges_utak(self.d, [jo, szoveg, nul, nagy, ures], max_bajt=1000), [jo, szoveg, ures])

    def test_a_binaris_kiterjesztes_es_a_hianyzo_fajl_kimarad(self):
        mp4 = self.ir("staging/a/video.mp4", b"szoveg")
        eredeti = self.ir("staging/a/video.mkv.eredeti", b"szoveg")
        self.assertEqual(lanc.szoveges_utak(self.d, [mp4, eredeti], max_bajt=1000), [])
        self.assertEqual(lanc.szoveges_utak(self.d, ["torolt/regi.md"], max_bajt=1000), ["torolt/regi.md"], "a törlés is változás: átmegy")

    def test_symlink_nem_szoveges_ut(self):
        kint = self.d.parent / "kint-titok.txt"
        kint.write_text("titok", encoding="utf-8")
        self.addCleanup(kint.unlink)
        (self.d / "staging").mkdir()
        (self.d / "staging" / "link.md").symlink_to(kint)
        self.assertEqual(lanc.szoveges_utak(self.d, ["staging/link.md"], max_bajt=1000), [])


# ------------------------------------------------------------------ A3-10, A3-11, A3-20

class BinarisVisszaallitasTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.vault, self.jobs, self.kint = self.d / "Vault", self.d / "jobs", self.d / "kint"
        (self.vault / "V").mkdir(parents=True)
        self.jobs.mkdir()
        self.kint.mkdir()
        self.naplo = self.d / "binaris-naplo.jsonl"

    def video(self, rel: str = "V/a.mp4", b: bytes = b"video") -> Path:
        p = self.vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
        return p

    def cel(self, kulcs: str) -> Path:
        return Path(kulcs) if os.path.isabs(kulcs) else self.jobs / kulcs

    def vissza(self, shak, **kw):
        return bn.visszaallit(self.naplo, self.vault, shak, self.cel, gyokerek=[self.jobs], log=lambda s: None, **kw)

    # -- A3-10: a commit mező és a cél

    def test_rovid_commit_mezo_nem_illeszkedik_semmire(self):
        v = self.video()
        for c in ("a", "abc", "abcdef", "zzzzzzzz", "ABCDEFG!"):
            bn.ir(self.naplo, {"commit": c, "kulcs": "k", "fajlok": ["V/a.mp4"]})
        self.assertEqual(self.vissza(["abcdef0123456789"])["mozgatva"], [])
        self.assertTrue(v.exists())

    def test_het_hex_jegyu_commit_illeszkedik(self):
        v = self.video()
        bn.ir(self.naplo, {"commit": "abcdef0", "kulcs": "k", "fajlok": ["V/a.mp4"]})
        self.assertEqual(len(self.vissza(["abcdef0123456789"])["mozgatva"]), 1)
        self.assertFalse(v.exists())

    def test_abszolut_kulcs_a_jobs_en_kivul_marad(self):
        v = self.video()
        bn.ir(self.naplo, {"commit": "abcdef01", "kulcs": str(self.kint), "fajlok": ["V/a.mp4"]})
        r = self.vissza(["abcdef01"])
        self.assertEqual(r["mozgatva"], [])
        self.assertEqual([m[0] for m in r["marad"]], ["V/a.mp4"])
        self.assertTrue(v.exists())
        self.assertEqual(list(self.kint.iterdir()), [])

    def test_nem_letezo_abszolut_mappat_nem_hozunk_letre(self):
        v = self.video()
        regi = self.d / "regi-icloud" / "Fuzetek"
        bn.ir(self.naplo, {"commit": "abcdef01", "kulcs": str(regi), "fajlok": ["V/a.mp4"]})
        r = bn.visszaallit(self.naplo, self.vault, ["abcdef01"], self.cel, gyokerek=[self.jobs, self.d], log=lambda s: None)
        self.assertEqual(r["mozgatva"], [])
        self.assertEqual(len(r["marad"]), 1)
        self.assertFalse(regi.parent.exists(), "a régi út nem támad fel")
        self.assertTrue(v.exists())

    def test_relativ_kulcs_felfele_nem_lephet_ki(self):
        v = self.video()
        bn.ir(self.naplo, {"commit": "abcdef01", "kulcs": "../kint", "fajlok": ["V/a.mp4"]})
        r = self.vissza(["abcdef01"])
        self.assertEqual((r["mozgatva"], len(r["marad"])), ([], 1))
        self.assertTrue(v.exists())
        self.assertEqual(list(self.kint.iterdir()), [])

    def test_a_jobs_alatti_symlink_cel_kivulre_nem_visz(self):
        v = self.video()
        (self.jobs / "k").symlink_to(self.kint, target_is_directory=True)
        bn.ir(self.naplo, {"commit": "abcdef01", "kulcs": "k", "fajlok": ["V/a.mp4"]})
        r = self.vissza(["abcdef01"])
        self.assertEqual((r["mozgatva"], len(r["marad"])), ([], 1))
        self.assertTrue(v.exists())
        self.assertEqual(list(self.kint.iterdir()), [])

    def test_a_vaultba_tett_mappa_symlink_forrasa_nem_mozog(self):
        """`vault/link -> /kint` mellett a `link/x.mp4` forrás a vaulton kívülre mutat (a `belul` csak az utolsó elemet nézte)."""
        (self.kint / "x.mp4").write_bytes(b"titok")
        (self.vault / "link").symlink_to(self.kint, target_is_directory=True)
        bn.ir(self.naplo, {"commit": "abcdef01", "kulcs": "k", "fajlok": ["link/x.mp4"]})
        r = self.vissza(["abcdef01"])
        self.assertEqual(r["mozgatva"], [])
        self.assertTrue((self.kint / "x.mp4").exists())
        self.assertFalse((self.jobs / "k" / "x.mp4").exists())

    def test_atnevezes_cel_symlinkje_nem_visz_ki(self):
        self.video("V/uj.mp4")
        (self.vault / "kilep").symlink_to(self.kint, target_is_directory=True)
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "atnevezes", [], tipus="atnevezes", regi="kilep/regi.mp4", uj="V/uj.mp4"))
        self.assertEqual(self.vissza(["abcdef01"])["mozgatva"], [])
        self.assertEqual(list(self.kint.iterdir()), [])

    def test_a_jobs_alatti_kulcs_tovabbra_is_letrejon(self):
        self.video()
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "youtube-uj", ["V/a.mp4"], tipus="media"))
        r = self.vissza(["abcdef01"])
        self.assertEqual(len(r["mozgatva"]), 1)
        self.assertTrue((self.jobs / "youtube-uj" / "a.mp4").is_file())

    # -- A3-11: azonosság

    def test_masik_tartalmu_fajlt_nem_visz_el(self):
        """A rekord a régi videó sha256-ját tartja; ha az útra azóta más fájl került, a fájl a helyén marad."""
        v = self.video(b=b"ujabb, mas video")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k", ["V/a.mp4"], tipus="media",
                                    sha256={"V/a.mp4": hashlib.sha256(b"regi video").hexdigest()}))
        r = self.vissza(["abcdef01"])
        self.assertEqual(r["mozgatva"], [])
        self.assertIn("nem azonos", r["marad"][0][1])
        self.assertEqual(v.read_bytes(), b"ujabb, mas video")

    def test_egyezo_sha256_mozog_dict_es_szoveg_alakban_is(self):
        self.video("V/a.mp4", b"video-a")
        self.video("V/b.mp4", b"video-b")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k1", ["V/a.mp4"], tipus="media", sha256=hashlib.sha256(b"video-a").hexdigest()))
        bn.ir(self.naplo, bn.rekord("abcdef02", "K", "k2", ["V/b.mp4"], tipus="media", sha256={"V/b.mp4": hashlib.sha256(b"video-b").hexdigest()}))
        self.assertEqual(len(self.vissza(["abcdef01", "abcdef02"])["mozgatva"]), 2)

    def test_meret_alapu_azonossag(self):
        v = self.video(b=b"12345")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k", ["V/a.mp4"], tipus="media", meret={"V/a.mp4": 99}))
        self.assertEqual(self.vissza(["abcdef01"])["mozgatva"], [])
        self.assertTrue(v.exists())
        bn.ir(self.naplo, bn.rekord("abcdef02", "K", "k2", ["V/a.mp4"], tipus="media", meret={"V/a.mp4": 5}))
        self.assertEqual(len(self.vissza(["abcdef02"])["mozgatva"]), 1)

    def test_atnevezes_sor_azonossaga(self):
        v = self.video("V/uj.mp4", b"masik")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "atnevezes", [], tipus="atnevezes", regi="V/regi.mp4", uj="V/uj.mp4",
                                    sha256=hashlib.sha256(b"eredeti").hexdigest()))
        r = self.vissza(["abcdef01"])
        self.assertEqual(r["mozgatva"], [])
        self.assertTrue(v.exists())

    def test_kivonat_seged(self):
        p = self.video(b=b"abc")
        self.assertEqual(bn.kivonat(p), hashlib.sha256(b"abc").hexdigest())

    # -- A3-20: fájlonkénti hibakezelés

    def test_a_masodik_fajl_hibaja_utan_az_elso_a_valaszban_marad(self):
        self.video("V/a.mp4", b"a")
        self.video("V/b.mp4", b"b")
        self.video("V/c.mp4", b"c")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k", ["V/a.mp4", "V/b.mp4", "V/c.mp4"], tipus="media"))
        eredeti = bn._mozgat

        def mozgat(src, dst, *a, **kw):
            if src.name == "b.mp4":
                raise OSError(5, "I/O hiba")
            return eredeti(src, dst, *a, **kw)
        with mock.patch.object(bn, "_mozgat", mozgat):
            r = self.vissza(["abcdef01"])
        self.assertEqual([m[0] for m in r["mozgatva"]], ["V/a.mp4", "V/c.mp4"])
        self.assertEqual([m[0] for m in r["marad"]], ["V/b.mp4"])
        self.assertIn("I/O", r["marad"][0][1])
        self.assertEqual(bn.olvas(self.naplo)[-1]["visszaallitva"], ["V/a.mp4", "V/c.mp4"], "a jelzősor a ténylegesen mozgatottakról szól")

    def test_a_jelzosor_irasanak_hibaja_nem_viszi_el_a_valaszt(self):
        self.video()
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k", ["V/a.mp4"], tipus="media"))
        eredeti = bn.ir

        def ir(naplo, rec):
            if "visszaallitva" in rec:
                raise OSError(28, "nincs hely")
            return eredeti(naplo, rec)
        with mock.patch.object(bn, "ir", ir):
            r = self.vissza(["abcdef01"])
        self.assertEqual(len(r["mozgatva"]), 1)
        self.assertTrue((self.jobs / "k" / "a.mp4").is_file())

    def test_nem_oserror_kivetel_is_fajlonkenti(self):
        self.video("V/a.mp4", b"a")
        self.video("V/b.mp4", b"b")
        bn.ir(self.naplo, bn.rekord("abcdef01", "K", "k", ["V/a.mp4", "V/b.mp4"], tipus="media"))
        eredeti = bn._mozgat

        def mozgat(src, dst, *a, **kw):
            if src.name == "a.mp4":
                raise RuntimeError("váratlan")
            return eredeti(src, dst, *a, **kw)
        with mock.patch.object(bn, "_mozgat", mozgat):
            r = self.vissza(["abcdef01"])
        self.assertEqual([m[0] for m in r["mozgatva"]], ["V/b.mp4"])
        self.assertEqual([m[0] for m in r["marad"]], ["V/a.mp4"])


# ------------------------------------------------------------------ A3-13

class SsrfTeszt(unittest.TestCase):
    HELYI = ("127.1", "0", "2130706433", "0x7f000001", "127.0.0.1.", "0177.0.0.1", "127.0.1", "017700000001", "0.0.0.0", "10.1", "192.168.1",
             "169.254.169.254", "[::1]", "::ffff:127.0.0.1", "[::ffff:7f00:1]", "１２７.0.0.1", "127。0。0。1", "100.64.0.1", "localhost.", "LOCALHOST",
             "x.localhost", "fd00::1")

    def tesztelt(self, host: str) -> bool:
        with mock.patch.object(videolanc, "_felold", side_effect=AssertionError("számformához nem kell DNS")):
            return videolanc._helyi_cim(host)

    def test_a_szamforma_kerulok_mind_helyiek(self):
        for host in self.HELYI:
            with self.subTest(host=host):
                try:
                    self.assertTrue(self.tesztelt(host))
                except AssertionError as e:
                    if "számformához" in str(e):      # névnek látszik: a felold-ágon kell elbuknia (DNS-mock nélkül tiltott)
                        self.fail(f"{host!r}: névként kezelve, nem IP-ként")
                    raise

    def test_a_nyilvanos_cim_nem_helyi(self):
        for host in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"):
            with self.subTest(host=host):
                self.assertFalse(self.tesztelt(host))

    def test_dns_nev_helyi_cimre_oldodik(self):
        for cimek in (["127.0.0.1"], ["93.184.216.34", "10.0.0.5"], ["::1"], ["::ffff:127.0.0.1"], ["169.254.169.254"]):
            with self.subTest(cimek=cimek), mock.patch.object(videolanc, "_felold", return_value=cimek):
                self.assertTrue(videolanc._helyi_cim("localtest.me"))

    def test_dns_nev_nyilvanos_cimre_oldodik(self):
        with mock.patch.object(videolanc, "_felold", return_value=["93.184.216.34", "2606:2800:220:1::1"]):
            self.assertFalse(videolanc._helyi_cim("zanza.tv"))

    def test_nem_feloldhato_nev_zarva_hibazik(self):
        with mock.patch.object(videolanc, "_felold", side_effect=socket.gaierror("nincs")):
            self.assertTrue(videolanc._helyi_cim("nincs-ilyen-nev.example"))

    def test_az_urlek_ellenoriz_a_megkerulo_formakat_400_al_utasitja_el(self):
        from core import tasks
        for u in ("http://127.1/", "http://0/", "http://2130706433/", "http://0x7f000001/", "http://127.0.0.1./", "http://[::ffff:127.0.0.1]/"):
            with self.subTest(url=u), self.assertRaises(tasks.Invalid):
                videolanc.urlek_ellenoriz([u], 20)
        with mock.patch.object(videolanc, "_felold", return_value=["127.0.0.1"]), self.assertRaises(tasks.Invalid):
            videolanc.urlek_ellenoriz(["http://localtest.me/"], 20)
        with mock.patch.object(videolanc, "_felold", return_value=["93.184.216.34"]):
            self.assertEqual(videolanc.urlek_ellenoriz([URL], 20), [URL])


class HalozatOrzoTeszt(unittest.TestCase):
    """A3-13 (átirányítás, DNS-újrakötés): a lépés folyamatában minden kapcsolat célja ellenőrzött — a yt-dlp saját átirányítása is."""

    def setUp(self):
        from modulok.ytdlp import halozat_orzo
        self.orzo = halozat_orzo
        self.addCleanup(self.orzo.leszed)
        self.szerver = socket.socket()
        self.szerver.bind(("127.0.0.1", 0))
        self.szerver.listen(1)
        self.addCleanup(self.szerver.close)

    def test_a_helyi_kapcsolat_tiltott(self):
        self.orzo.telepit()
        k = socket.socket()
        self.addCleanup(k.close)
        with self.assertRaises(PermissionError):
            k.connect(self.szerver.getsockname())
        with self.assertRaises(PermissionError):
            socket.create_connection(self.szerver.getsockname(), timeout=2)

    def test_leszedve_a_kapcsolat_megy(self):
        self.orzo.telepit()
        self.orzo.leszed()
        k = socket.create_connection(self.szerver.getsockname(), timeout=2)
        k.close()

    def test_idempotens_telepites(self):
        self.orzo.telepit()
        self.orzo.telepit()
        self.orzo.leszed()
        k = socket.create_connection(self.szerver.getsockname(), timeout=2)
        k.close()

    def test_a_lepes_belepesi_pontja_telepiti(self):
        """A `python -m modulok.ytdlp lepes` a lánc előtt telepíti az őrt (a core folyamata nem kapja)."""
        forras = (Path(__file__).resolve().parent.parent / "modulok" / "ytdlp" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("halozat_orzo", forras)


class LepesHalozatOrzoTeszt(unittest.TestCase):
    """A3-13 végpontig: a `python -m modulok.ytdlp lepes letoltes` folyamatában a VALÓDI yt-dlp nem ér el loopback szervert (ez fogja meg az
    átirányítást és a DNS-újrakötést is); a kontroll (a teszt-kapcsolóval) bizonyítja, hogy a szerver egyébként elérhető volt."""

    def setUp(self):
        import functools
        import http.server
        import threading
        from tests.helpers import REPO
        self.REPO = REPO
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.cfg, self.root, _ = alg_core(self.d.as_posix())
        (self.root / "modulok" / "ytdlp" / "config").mkdir(parents=True)
        (self.root / "modulok" / "ytdlp" / "config" / "config.yaml").write_text(
            (REPO / "modulok" / "ytdlp" / "config" / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        pin_es_ffmpeg(self.cfg, self.root)
        self.talalatok: list[str] = []
        talalatok = self.talalatok

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                talalatok.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>nincs itt video</body></html>")

            do_HEAD = do_GET

            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def lepes(self, **env_extra):
        from tests.helpers import env
        e = {k: v for k, v in env(MOS_ROOT=str(self.root), PYTHONPATH=str(self.REPO), **env_extra).items() if "proxy" not in k.lower()}
        e["NO_PROXY"] = "127.0.0.1"
        url = f"http://127.0.0.1:{self.srv.server_address[1]}/oldal"
        return subprocess.run([sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "letoltes", "--url", url, "--proba-gyoker", str(self.d / "proba")],
                              cwd=self.REPO, env=e, capture_output=True, text=True, timeout=300)

    def test_a_loopback_szerver_nem_erheto_el_a_lepesbol(self):
        p = self.lepes()
        self.assertEqual(self.talalatok, [], p.stdout[-1500:] + p.stderr[-1500:])
        self.assertEqual(p.returncode, 1, p.stdout[-1500:] + p.stderr[-1500:])

    def test_kontroll_a_teszt_kapcsoloval_a_szerver_elerheto(self):
        p = self.lepes(MOS_VIDEO_HELYI_ENGEDELY="1")
        self.assertTrue(self.talalatok, "a kontroll szerver nem kapott kérést: a fenti teszt nem bizonyít semmit\n" + p.stdout[-1500:] + p.stderr[-1500:])


# ------------------------------------------------------------------ A3-17, A3-18

class EszkozTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.cfg.path("ytdlp").mkdir(parents=True)
        self.ff = pin_es_ffmpeg(self.cfg, self.root)
        self.kint = Path(self._t.name) / "kint"
        self.kint.mkdir()
        self.hamis_ff = self.kint / "ffmpeg"
        self.hamis_ff.write_text("#!/bin/sh\necho kint\n")
        self.hamis_ff.chmod(0o755)

    def futtat(self, letolto=None, urlek=(URL,)):
        _, modul, _ = msp()
        with mock.patch.object(modul, "create_downloader", return_value=letolto or hamis_letolto()) as m:
            rc, ki = lepes(self.cfg, urlek)
        return rc, ki, m

    # -- A3-17

    def test_az_ffmpeg_a_utak_ffmpegbol_megy_nem_a_kornyezetbol(self):
        with mock.patch.dict(os.environ, {"MOS_FFMPEG": str(self.hamis_ff)}):
            rc, ki, m = self.futtat()
        self.assertEqual(rc, 0, ki)
        mcfg = m.call_args.args[0]
        self.assertEqual(mcfg.ytdlp.ffmpeg_location, str(self.ff))

    def test_eltero_sha256_nem_indul(self):
        self.ff.write_text("#!/bin/sh\necho csereltek\n")
        rc, ki, m = self.futtat()
        self.assertEqual(rc, 2)
        self.assertIn("sha256", ki)
        m.assert_not_called()

    def test_pin_nelkul_zarva_hibazik(self):
        (self.root / "config" / "runtime-pins.env").unlink()
        rc, ki, m = self.futtat()
        self.assertEqual(rc, 2)
        self.assertIn("FFMPEG_BIN_SHA256", ki)
        m.assert_not_called()

    def test_a_kornyezeti_ffmpeg_es_a_konfig_ffmpeg_location_nem_er_semmit(self):
        konfig, letolto, _ = msp()[0], msp()[1], None
        mcfg = lanc.msp_konfig(self.cfg)
        self.assertEqual(mcfg.ytdlp.ffmpeg_location, str(self.ff))
        with mock.patch.dict(os.environ, {"MOS_FFMPEG": str(self.hamis_ff)}):
            self.assertEqual(letolto.resolve_ffmpeg(mcfg), str(self.ff))
            auto = konfig.Config.load(project_root=self.cfg.path("ytdlp"))
            self.assertIsNone(letolto.resolve_ffmpeg(auto), "nincs MOS_FFMPEG, nincs runtime-keresés: csak a kapott útvonal")

    # -- A3-18

    def test_nincs_path_beli_ytdlp_node_es_deno(self):
        _, letolto, _ = msp()
        for nev in ("yt-dlp", "node", "deno"):
            b = self.kint / nev
            b.write_text("#!/bin/sh\nexit 0\n")
            b.chmod(0o755)
        mcfg = lanc.msp_konfig(self.cfg)
        with mock.patch.dict(os.environ, {"PATH": f"{self.kint}{os.pathsep}{os.environ['PATH']}", "MOS_NODE": ""}):
            self.assertIsNone(letolto.find_ytdlp_binary(mcfg))
            self.assertIsNone(letolto._js_runtime_path("node", mcfg))
            self.assertIsNone(letolto.resolve_js_runtime(mcfg))

    def test_a_ytdlp_js_runtimes_ures_ha_nincs_pinelt_node(self):
        _, letolto, _ = msp()
        mcfg = lanc.msp_konfig(self.cfg)
        d = letolto.YtDlpPythonDownloader(mcfg, progress=False)
        self.assertEqual(d._base_options()["js_runtimes"], {}, "az üres szótár kikapcsolja a yt-dlp deno-alapértelmezését is")

    def test_a_pinelt_node_az_utak_nodebol_jon(self):
        _, letolto, _ = msp()
        node = self.cfg.path("node")
        node.parent.mkdir(parents=True)
        node.write_text("#!/bin/sh\nexit 0\n")
        node.chmod(0o755)
        mcfg = lanc.msp_konfig(self.cfg)
        self.assertEqual(letolto._js_runtime_path("node", mcfg), str(node))
        self.assertEqual(letolto.resolve_js_runtime(mcfg), "node")
        d = letolto.YtDlpPythonDownloader(mcfg, progress=False)
        self.assertEqual(d._base_options()["js_runtimes"], {"node": {"path": str(node)}})

    def test_a_forraskod_nem_keres_a_path_ban(self):
        """Szerkezeti őr: a port két érintett fájljában nincs `which(` hívás és nincs `"nice"` szöveg-konstans."""
        import ast
        gyoker = Path(__file__).resolve().parent.parent / "modulok" / "ytdlp"
        for rel in ("src/msp/downloader.py", "konvertalas.py"):
            fa = ast.parse((gyoker / rel).read_text(encoding="utf-8"))
            hivasok = {n.func.attr for n in ast.walk(fa) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            self.assertNotIn("which", hivasok, rel)
            konstansok = {n.value for n in ast.walk(fa) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertNotIn("nice", konstansok, rel)

    def test_a_konvertalas_nem_hasznal_path_beli_nice_t(self):
        felvett = {}
        valodi = subprocess.Popen

        def P(cmd, *a, **kw):
            if "-progress" not in cmd:          # a próba (`ffmpeg -i`) valódi hamis ffmpeg-et indít
                return valodi(cmd, *a, **kw)
            felvett["cmd"], felvett["kw"] = cmd, kw
            raise RuntimeError("megállj")
        forras = Path(self._t.name) / "s" / "video.webm"
        forras.parent.mkdir()
        forras.write_bytes(b"x")
        ff = self.kint / "ffmpeg"
        ff.write_text(FAKE_FFMPEG)
        with mock.patch.object(konvertalas.subprocess, "Popen", P), self.assertRaises(RuntimeError):
            konvertalas.konvertal(str(ff), forras, log=lambda s: None)
        self.assertEqual(felvett["cmd"][0], str(ff), "az ffmpeg közvetlenül indul, nem a PATH-os `nice` alatt")
        self.assertTrue(callable(felvett["kw"].get("preexec_fn")), "az alacsony prioritást a gyermek `os.nice`-szal veszi fel")


# ------------------------------------------------------------------ A3-19, A3-09 (archiválás-hiba)

FAKE_SIKERES = """#!/bin/sh
# hamis ffmpeg: a próbák 10 s-os (webm, illetve a `.part` mp4) kimenetet adnak, a konvertálás (-progress) a kimenetet létrehozza
case "$*" in
  *-progress*)
    for utolso; do :; done
    printf 'x' > "$utolso"; exit 0 ;;
  *.part*)
    cat >&2 <<'VEGE'
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.part':
  Duration: 00:00:10.00, start: 0.000000, bitrate: 100 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 1280x720, 30 fps
  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp
VEGE
    exit 1 ;;
  *)
    cat >&2 <<'VEGE'
Input #0, matroska,webm, from 'video.webm':
  Duration: 00:00:10.00, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 1280x720, 30 fps
  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp
VEGE
    exit 1 ;;
esac
"""


class KonvertalasCsereTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.ff = self.d / "ffmpeg"
        self.ff.write_text(FAKE_SIKERES, encoding="utf-8")
        self.ff.chmod(0o755)
        self.s = self.d / "s"
        self.s.mkdir()

    def konvertal(self, forras: Path, **kw):
        return konvertalas.konvertal(str(self.ff), forras, log=lambda s: None, **kw)

    def maradek(self):
        return sorted(p.name for p in self.s.iterdir())

    def test_a_sikeres_csere_nem_irja_felul_semmit(self):
        forras = self.s / "video.webm"
        forras.write_bytes(b"webm")
        r = self.konvertal(forras)
        self.assertEqual(self.maradek(), ["video.mp4", "video.webm.eredeti"])
        self.assertEqual((self.s / "video.webm.eredeti").read_bytes(), b"webm")
        self.assertEqual(r["ut"], str(self.s / "video.mp4"))

    def test_meglevo_mp4_nem_irodik_felul(self):
        forras = self.s / "video.webm"
        forras.write_bytes(b"webm")
        (self.s / "video.mp4").write_bytes(b"MEGLEVO")
        with self.assertRaises(konvertalas.KonvertalasHiba) as cm:
            self.konvertal(forras)
        self.assertIn("video.mp4", str(cm.exception))
        self.assertEqual((self.s / "video.mp4").read_bytes(), b"MEGLEVO")
        self.assertEqual(forras.read_bytes(), b"webm")
        self.assertEqual(self.maradek(), ["video.mp4", "video.webm"], "nincs `.part` maradék")

    def test_meglevo_eredeti_nem_irodik_felul(self):
        forras = self.s / "video.webm"
        forras.write_bytes(b"webm")
        (self.s / "video.webm.eredeti").write_bytes(b"REGI EREDETI")
        with self.assertRaises(konvertalas.KonvertalasHiba):
            self.konvertal(forras)
        self.assertEqual((self.s / "video.webm.eredeti").read_bytes(), b"REGI EREDETI")
        self.assertEqual(forras.read_bytes(), b"webm")
        self.assertEqual(self.maradek(), ["video.webm", "video.webm.eredeti"])

    def test_mp4_forras_helyben_lecserelve_az_eredeti_marad(self):
        """A forrás maga az `.mp4` (nem natív kodek): a `.eredeti` előfeltétel, a végleges ugyanarra a névre kerül."""
        forras = self.s / "video.mp4"
        forras.write_bytes(b"vp9-mp4")
        self.konvertal(forras)
        self.assertEqual(self.maradek(), ["video.mp4", "video.mp4.eredeti"])
        self.assertEqual((self.s / "video.mp4.eredeti").read_bytes(), b"vp9-mp4")

    def test_a_masodik_lepes_hibaja_visszaallitja_az_eredetit(self):
        """Ha a végleges név a csere közben foglalt lesz, az eredeti visszakerül a helyére: nincs lejátszható fájl nélküli állapot."""
        forras = self.s / "video.mp4"
        forras.write_bytes(b"vp9-mp4")
        from core import tartos
        eredeti = tartos.rename_excl
        hivas = []

        def rename(src, dst):
            hivas.append((Path(src).name, Path(dst).name))
            if Path(dst).name == "video.mp4" and Path(src).name.endswith(".part"):
                raise FileExistsError(17, "foglalt", str(dst))
            return eredeti(src, dst)
        with mock.patch.object(tartos, "rename_excl", rename), self.assertRaises(konvertalas.KonvertalasHiba):
            self.konvertal(forras)
        self.assertEqual(forras.read_bytes(), b"vp9-mp4", "az eredeti a helyén")
        self.assertEqual(self.maradek(), ["video.mp4"], "a `.part` is eltakarítva")

    def test_az_archivalas_hibaja_nem_veszit_el_semmit(self):
        """A3-09 útja: a `shutil.move` hibája után az eredeti `.eredeti` néven marad, a konvertálás sikeres, nincs kivétel."""
        forras = self.s / "video.webm"
        forras.write_bytes(b"webm")
        with mock.patch.object(konvertalas.shutil, "move", side_effect=OSError(28, "nincs hely")):
            r = self.konvertal(forras, eredeti_gyoker=self.d / "arch", relativ="a/b")
        self.assertEqual(self.maradek(), ["video.mp4", "video.webm.eredeti"])
        self.assertEqual(r["eredeti"], str(self.s / "video.webm.eredeti"))
        self.assertIn("nincs hely", r.get("archivalas_hiba", ""))


# ------------------------------------------------------------------ A3-21

class StagingTmpNevTeszt(unittest.TestCase):
    def test_a_visszajelez_ideiglenes_neve_a_paragrafus_4_szerinti(self):
        with tmpdir() as t:
            mappa = Path(t) / "s"
            mappa.mkdir()
            (mappa / "integration.json").write_text('{"integration_status": "pending"}\n', encoding="utf-8")
            felvett = []
            eredeti = os.replace

            def csere(src, dst, *a, **kw):
                felvett.append(Path(src).name)
                return eredeti(src, dst, *a, **kw)
            with mock.patch("os.replace", csere):
                self.assertEqual(staging.visszajelez(mappa), "irva")
            (nev,) = felvett
            self.assertRegex(nev, frame.TMP_MINTA.pattern)
            self.assertNotEqual(nev, "integration.json.manifold-tmp")
            self.assertEqual([p.name for p in mappa.iterdir()], ["integration.json"])

    def test_a_hibas_iras_nem_hagy_ideiglenes_fajlt(self):
        with tmpdir() as t:
            mappa = Path(t) / "s"
            mappa.mkdir()
            (mappa / "integration.json").write_text('{"integration_status": "pending"}\n', encoding="utf-8")
            with mock.patch("os.replace", side_effect=OSError(5, "hiba")), self.assertRaises(OSError):
                staging.visszajelez(mappa)
            self.assertEqual([p.name for p in mappa.iterdir()], ["integration.json"])


# ------------------------------------------------------------------ A3-22

class AsrModellTiltasTeszt(unittest.TestCase):
    """§4: modellt kizárólag a betöltő (modellgazda) tölthet be; a port ASR-motorjai kódból tiltottak."""

    def setUp(self):
        msp()
        from msp.errors import TranscriptionError
        self.hiba = TranscriptionError

    def cfg(self):
        konfig, _, _ = msp()
        return konfig.Config.load(project_root=Path(__file__).resolve().parent.parent / "modulok" / "ytdlp")

    def test_a_modellt_tolto_motorok_transcribe_ja_tiltott(self):
        from msp.transcription.faster_whisper import FasterWhisperBackend
        from msp.transcription.mlx_whisper import MlxWhisperBackend
        from msp.transcription.whisper_cpp import WhisperCppBackend
        with tmpdir() as t:
            media = Path(t) / "video.mp4"
            media.write_bytes(b"x")
            for osztaly in (FasterWhisperBackend, MlxWhisperBackend, WhisperCppBackend):
                with self.subTest(motor=osztaly.__name__), self.assertRaises(self.hiba) as cm:
                    osztaly(self.cfg()).transcribe(media, language="hu", folder=Path(t))
                self.assertIn("modellgazda", str(cm.exception))

    def test_a_felirat_alapu_motor_modell_nelkul_nem_tiltott(self):
        from msp.transcription.subtitles import SubtitlesBackend
        self.assertTrue(hasattr(SubtitlesBackend, "transcribe"))
        from msp.transcription import base
        self.assertNotIn("subtitles", getattr(base, "MODELLT_TOLTO", ()))

    def test_a_tiltas_nem_toltott_be_modellt(self):
        from msp.transcription.faster_whisper import FasterWhisperBackend
        with tmpdir() as t:
            media = Path(t) / "video.mp4"
            media.write_bytes(b"x")
            with mock.patch.dict(sys.modules, {"faster_whisper": None}), self.assertRaises(self.hiba) as cm:
                FasterWhisperBackend(self.cfg()).transcribe(media, language="hu", folder=Path(t))
            self.assertNotIn("not installed", str(cm.exception).lower())


# ------------------------------------------------------------------ A3-12 (váz, a C29.8-fésüléskor)

class LepesTokenVaz(unittest.TestCase):
    """A3-12 (K149): a `video_letoltes` lépés (yt-dlp: távoli tartalom, JS-futtató node) a környezetében sem a felületi API-titkot, sem
    lépés-tokent, sem a core címét nem kapja (jogkészlet: `"nincs"`, `core/lepes_kapu.py`); a környezet a fehérlistából épül, így a
    yt-dlp által indított node-gyermek sem örököl titkot. A hálózati lépés semmilyen írási jogot nem kap (47(c))."""

    def test_a_video_letoltes_lepes_nem_kap_api_titkot_es_irasi_jogot(self):
        from core import lepes_kapu, tasks
        videolanc.regisztral()
        with tmpdir() as t:
            cfg, root, _ = alg_core(t)
            pin_es_ffmpeg(cfg, root)
            with mock.patch.object(videolanc, "_felold", return_value=["93.184.216.34"]):
                (l, *_), _, _ = videolanc._terv(cfg, {"urlek": [URL]}, "/stop")
            self.assertEqual(l.jogok, lepes_kapu.JOGOK_NINCS)
            self.assertFalse(lepes_kapu.token_jar(l.jogok))
            q = tasks.Queue(cfg, start_delay=3600)
            try:
                extra = {"MOS_CORE_URL": "http://127.0.0.1:1"}         # amit a `server.feladat_env` minden feladatnak ad
                with mock.patch.dict(os.environ, {"MOS_API_TITOK": "felulet-titka-0123456789", "MOS_CORE_PORT": "1",
                                                  "MOS_LEPES_TOKEN": "orokolt-token-0123456789"}):
                    env = q._env("F-20261007-0001", Path("/stop"), extra, "lepes-token-0123456789", l.jogok)
            finally:
                q.close()
            self.assertNotIn("MOS_API_TITOK", env, "a hálózati lépés a teljes titkot nem kaphatja")
            self.assertNotIn("MOS_LEPES_TOKEN", env, "a hálózati lépés lépés-tokent sem kap: nincs gépi-írás joga")
            self.assertNotIn("MOS_CORE_URL", env, "a hálózati lépés a core címét sem kapja")
            self.assertNotIn("MOS_CORE_PORT", env)


if __name__ == "__main__":
    unittest.main()
