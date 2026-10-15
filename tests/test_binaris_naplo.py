"""C20a: a bináris mozgásnapló (L19) portja — a legacy `test_binaris.py` két esete, és ami a 2.0-ban javult: NFC/NFD-tűrő összevetés, soha nem
ír felül, a `commit: null` rekord a körre illeszkedik, az átnevezés-sor visszanevez, az utak a vaulton belül maradnak, és az `App.undo`
a vault-visszavonás után végigviszi a médiát. Ideiglenes álvaultban, a valódi vaulthoz és var/-hoz a teszt nem nyúl."""
import json
import os
import unicodedata
import unittest
from pathlib import Path

from core import binaris_naplo as bn
from core import mediatipus, snapshot
from tests.helpers import tmpdir
from tests.test_core_api import _Szerver

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
LEGACY_SOROK = [        # a valódi napló alakjai (útak rövidítve): commit + kor + kulcs + fajlok
    {"commit": "cf1e507c", "kor": "KOR-20260925-183447", "kulcs": "youtube-bqM4pmBGWfw",
     "fajlok": ["ATTCHMNTS - Videos/Katona József- Bánk bán.mp4"]},
    {"commit": "fca7120c", "kor": "KOR-20260926-002358", "kulcs": "youtube-fSiKCvI41K8",
     "fajlok": ["ATTCHMNTS - Videos/A romantika jellemzői.mp4"]},
]


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.vault, self.jobs = self.d / "Vault", self.d / "jobs"
        (self.vault / "ATTCHMNTS - Videos").mkdir(parents=True)
        self.naplo = self.d / "binaris-naplo.jsonl"

    def cel(self, kulcs: str) -> Path:
        return self.jobs / kulcs

    def vissza(self, shak, **kw):
        return bn.visszaallit(self.naplo, self.vault, shak, self.cel, gyokerek=[self.jobs], log=lambda s: None, **kw)


class LegacyEsetekTeszt(Alap):
    """A legacy `tests/test_binaris.py` két esete, változatlan elvárással."""

    def test_az_uj_binaris_visszakoltozik_nem_torlodik(self):
        (self.vault / "regi.mp4").write_bytes(b"x")
        elotte = bn.leltar(self.vault)
        v = self.vault / "ATTCHMNTS - Videos" / "Új videó.mp4"
        v.write_bytes(b"video")
        (self.vault / "jegyzet.md").write_text("szöveg", encoding="utf-8")
        uj = bn.uj_fajlok(elotte, bn.leltar(self.vault))
        self.assertEqual(uj, ["ATTCHMNTS - Videos/Új videó.mp4"])
        bn.ir(self.naplo, bn.rekord("abc123456", "K1", "youtube-x", uj))
        r = self.vissza(["abc123456"])
        self.assertEqual(len(r["mozgatva"]), 1)
        self.assertFalse(v.exists())
        self.assertEqual((self.jobs / "youtube-x" / "Új videó.mp4").read_bytes(), b"video")
        self.assertTrue((self.vault / "regi.mp4").exists(), "a korábbi nem érintett")

    def test_mas_commit_nem_erintett(self):
        (self.vault / "a.mp4").write_bytes(b"a")
        bn.ir(self.naplo, {"commit": "fffffff0", "kulcs": "k", "fajlok": ["a.mp4"]})
        self.assertEqual(self.vissza(["abcdef12"])["mozgatva"], [])
        self.assertTrue((self.vault / "a.mp4").exists())


class JavitasokTeszt(Alap):
    def mp4(self, rel: str, b: bytes = b"video") -> Path:
        p = self.vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
        return p

    def test_a_legacy_sorok_alakja_olvashato_es_visszaallithato(self):
        for s in LEGACY_SOROK:
            bn.ir(self.naplo, s)
        self.mp4("ATTCHMNTS - Videos/A romantika jellemzői.mp4")
        self.assertEqual([r["commit"] for r in bn.olvas(self.naplo)], ["cf1e507c", "fca7120c"])
        r = self.vissza(["fca7120cdeadbeef"])
        self.assertEqual([m[0] for m in r["mozgatva"]], ["ATTCHMNTS - Videos/A romantika jellemzői.mp4"])
        self.assertTrue((self.jobs / "youtube-fSiKCvI41K8" / "A romantika jellemzői.mp4").exists())

    def test_nfc_nfd_toleranc(self):
        """A rekord NFC-ben íródik, a lemezen NFD név állhat (a legacy ezen elbukott); és fordítva."""
        nfd = unicodedata.normalize("NFD", "Katona József- Bánk bán.mp4")
        self.mp4(f"ATTCHMNTS - Videos/{nfd}")
        bn.ir(self.naplo, bn.rekord("aaaaaaaa1", "K1", "youtube-a", ["ATTCHMNTS - Videos/Katona József- Bánk bán.mp4"]))
        self.assertEqual(bn.olvas(self.naplo)[0]["fajlok"], [unicodedata.normalize("NFC", "ATTCHMNTS - Videos/Katona József- Bánk bán.mp4")])
        r = self.vissza(["aaaaaaaa1"])
        self.assertEqual(len(r["mozgatva"]), 1, r)
        self.assertEqual(len(list((self.jobs / "youtube-a").iterdir())), 1)

    def test_a_celban_levo_fajlt_nem_irja_felul(self):
        v = self.mp4("ATTCHMNTS - Videos/film.mp4", b"vault")
        (self.jobs / "youtube-b").mkdir(parents=True)
        (self.jobs / "youtube-b" / "film.mp4").write_bytes(b"munkamappa")
        bn.ir(self.naplo, bn.rekord("bbbbbbbb1", "K1", "youtube-b", ["ATTCHMNTS - Videos/film.mp4"]))
        r = self.vissza(["bbbbbbbb1"])
        self.assertEqual(r["mozgatva"], [])
        self.assertEqual([m[0] for m in r["marad"]], ["ATTCHMNTS - Videos/film.mp4"])
        self.assertEqual(v.read_bytes(), b"vault")
        self.assertEqual((self.jobs / "youtube-b" / "film.mp4").read_bytes(), b"munkamappa")

    def test_a_commit_nelkuli_rekord_a_korre_illeszkedik(self):
        """A legacy `commit: null` sora (nem volt szöveges változás) a visszavonáskor sosem találta meg a fájlt."""
        self.mp4("ATTCHMNTS - Videos/n.mp4")
        bn.ir(self.naplo, bn.rekord(None, "KOR-20261001-100000", "youtube-n", ["ATTCHMNTS - Videos/n.mp4"]))
        self.assertEqual(self.vissza(["cccccccc1"])["mozgatva"], [], "másik commit/kör: nem érintett")
        r = self.vissza(["cccccccc1"], korok=["KOR-20261001-100000"])
        self.assertEqual(len(r["mozgatva"]), 1)

    def test_idempotens_es_jelzosor(self):
        self.mp4("ATTCHMNTS - Videos/i.mp4")
        bn.ir(self.naplo, bn.rekord("dddddddd1", "K1", "youtube-i", ["ATTCHMNTS - Videos/i.mp4"]))
        self.assertEqual(len(self.vissza(["dddddddd1"])["mozgatva"]), 1)
        jelzo = bn.olvas(self.naplo)[-1]
        self.assertEqual(jelzo["visszaallitva"], ["ATTCHMNTS - Videos/i.mp4"])
        self.assertEqual(jelzo["commitok"], ["dddddddd1"])
        masodik = self.vissza(["dddddddd1"])
        self.assertEqual((masodik["mozgatva"], masodik["hianyzik"]), ([], ["ATTCHMNTS - Videos/i.mp4"]), "nincs mit visszaállítani, nem hiba")
        self.assertEqual(len(bn.olvas(self.naplo)), 2, "nem íródik újabb jelzősor")

    def test_rovid_sha_nem_illeszkedik(self):
        """Legalább 7 jel kell: egy 1–2 jegyű előtag mindent visszaállítana."""
        self.mp4("ATTCHMNTS - Videos/r.mp4")
        bn.ir(self.naplo, bn.rekord("eeeeeeee1", "K1", "youtube-r", ["ATTCHMNTS - Videos/r.mp4"]))
        self.assertEqual(self.vissza(["ee"])["mozgatva"], [])

    def test_atnevezes_sor_visszanevez(self):
        self.mp4("ATTCHMNTS - Videos/uj nev.mp4")
        bn.ir(self.naplo, bn.rekord("ffffffff1", "ATNEV-20261004-100000", "atnevezes", [], tipus="atnevezes",
                                    regi="ATTCHMNTS - Videos/regi nev.mp4", uj="ATTCHMNTS - Videos/uj nev.mp4"))
        r = self.vissza(["ffffffff1"])
        self.assertEqual(r["mozgatva"], [("ATTCHMNTS - Videos/uj nev.mp4", "ATTCHMNTS - Videos/regi nev.mp4")])
        self.assertTrue((self.vault / "ATTCHMNTS - Videos" / "regi nev.mp4").exists())
        self.assertFalse((self.vault / "ATTCHMNTS - Videos" / "uj nev.mp4").exists())

    def test_atnevezes_utkozes_a_regi_neven(self):
        self.mp4("ATTCHMNTS - Videos/uj nev.mp4", b"uj")
        self.mp4("ATTCHMNTS - Videos/regi nev.mp4", b"masik")
        bn.ir(self.naplo, bn.rekord("ffffffff2", "K", "atnevezes", [], tipus="atnevezes",
                                    regi="ATTCHMNTS - Videos/regi nev.mp4", uj="ATTCHMNTS - Videos/uj nev.mp4"))
        r = self.vissza(["ffffffff2"])
        self.assertEqual((r["mozgatva"], len(r["marad"])), ([], 1))
        self.assertEqual((self.vault / "ATTCHMNTS - Videos" / "regi nev.mp4").read_bytes(), b"masik")

    def test_veszelyes_utak_kimaradnak(self):
        kivul = self.d / "kivul.mp4"
        kivul.write_bytes(b"titok")
        (self.vault / "link.mp4").symlink_to(kivul)
        for rel in ("../kivul.mp4", str(kivul), "link.mp4", "a/../../kivul.mp4"):
            bn.ir(self.naplo, {"commit": "99999999", "kulcs": "k", "fajlok": [rel]})
        r = self.vissza(["99999999"])
        self.assertEqual(r["mozgatva"], [])
        self.assertTrue(kivul.exists() and (self.vault / "link.mp4").is_symlink())

    def test_serult_sor_nem_akasztja_a_visszavonast(self):
        self.mp4("ATTCHMNTS - Videos/s.mp4")
        with open(self.naplo, "w", encoding="utf-8") as f:
            f.write('{"commit": "77777777", "kulcs": "k", "fajlok": ["ATTCHMNTS - Videos/s.mp4"]}\n{"commit": "7777')
        self.assertEqual(len(self.vissza(["77777777"])["mozgatva"]), 1)

    def test_rekord_tipus_ellenorzes_es_additiv_kulcsok(self):
        with self.assertRaises(ValueError):
            bn.rekord("a", "K", "k", [], tipus="torles")
        r = bn.rekord("abcdef12", "K", "k", ["x.mp4"], tipus="media", forras="staging:Zanza/I/c/video.mp4", sha256="00")
        self.assertEqual(set(r), {"commit", "kor", "kulcs", "fajlok", "tipus", "forras", "sha256"})
        self.assertEqual(set(bn.rekord("abcdef12", "K", "k", ["x.mp4"])), {"commit", "kor", "kulcs", "fajlok"}, "az L19 alakja változatlan")

    def test_leltar_a_mediatipus_listajabol(self):
        for kit in (".flac", ".avif", ".opus", ".m4v", ".docx"):
            self.mp4(f"x/f{kit}")
        self.mp4("jegyzet.md")
        self.mp4(".obsidian/cache.png")
        l = bn.leltar(self.vault)
        for kit in (".flac", ".avif", ".opus", ".m4v", ".docx"):
            self.assertIn(f"x/f{kit}", l)
        self.assertNotIn("jegyzet.md", l)
        self.assertNotIn(".obsidian/cache.png", l)
        self.assertTrue(all(mediatipus.binaris_e(k) for k in l))


class UndoVegigTeszt(_Szerver):
    """Az `App.undo` a szöveg visszavonása után visszaköltözteti a videót a lánc munkamappájába, a kör-zár alatt."""

    def elokeszit(self):
        (self.v / "ATTCHMNTS - Videos").mkdir()
        (self.v / "T01").mkdir()
        (self.v / "T01" / "a.md").write_text(FM + "# A\n", encoding="utf-8")       # kell egy korábbi commit: a visszavonás revert
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.naplo = bn.naplo_ut(self.cfg)

    def tetel(self, kor: str, nev: str, video: bytes = b"videobajtok"):
        """Egy gépi tétel: a videó a vaultban (a C20b `mozgat`-ját szimulálva) + a forrásleíró jegyzet a gépi-írás szolgáltatáson át."""
        v = self.v / "ATTCHMNTS - Videos" / f"{nev}.mp4"
        v.write_bytes(video)
        kod, r = self.k("POST", "/api/gepi-iras", {
            "kor": kor, "tetel": "t1", "forras": "mos-video", "modell": None,       # determinisztikus írás (D9)
            "muveletek": [{"tipus": "uj", "ut": f"T01/{nev}.md", "tartalom": FM + f"# {nev}\n![[{nev}.mp4]]\n", "osztaly": "normal"}]})
        self.assertEqual(kod, 200, r)
        bn.ir(self.naplo, bn.rekord(r["sha"], kor, f"youtube-{nev}", [f"ATTCHMNTS - Videos/{nev}.mp4"], tipus="media"))
        return v, r["sha"]

    def test_kor_visszavonasa_a_videot_a_munkamappaba_koltozteti(self):
        v, sha = self.tetel("VIDEO-20261004-101500-aaaaaa", "film")
        self.assertTrue(v.exists())
        kod, r = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "VIDEO-20261004-101500-aaaaaa"})
        self.assertEqual(kod, 200, r)
        self.assertEqual(r["media"], {"visszakoltoztetve": 1})
        self.assertFalse((self.v / "T01" / "film.md").exists(), "a jegyzet visszavonva")
        self.assertFalse(v.exists(), "a videó kikerült a vaultból")
        self.assertEqual((self.cfg.path("video_jobs") / "youtube-film" / "film.mp4").read_bytes(), b"videobajtok", "de nem törlődött")
        self.assertEqual(bn.olvas(self.naplo)[-1]["visszaallitva"], ["ATTCHMNTS - Videos/film.mp4"])

    def test_tetel_visszavonasa_sha_alapjan(self):
        v, sha = self.tetel("VIDEO-20261004-101501-bbbbbb", "masik")
        kod, r = self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": sha})
        self.assertEqual((kod, r.get("media")), (200, {"visszakoltoztetve": 1}))
        self.assertFalse(v.exists())

    def test_utkozes_a_munkamappaban_a_szoveg_visszavonasat_nem_hiusitja_meg(self):
        v, _ = self.tetel("VIDEO-20261004-101502-cccccc", "utk", b"vault")
        celmappa = self.cfg.path("video_jobs") / "youtube-utk"
        celmappa.mkdir(parents=True)
        (celmappa / "utk.mp4").write_bytes(b"mar-ott-van")
        kod, r = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "VIDEO-20261004-101502-cccccc"})
        self.assertEqual(kod, 200, r)
        self.assertFalse((self.v / "T01" / "utk.md").exists(), "a szöveg visszavonva")
        self.assertEqual(r["media"], {"marad": [{"ut": "ATTCHMNTS - Videos/utk.mp4", "ok": "a célban már van ilyen nevű fájl"}]})
        self.assertEqual(v.read_bytes(), b"vault", "a fájl a helyén marad")
        self.assertEqual((celmappa / "utk.mp4").read_bytes(), b"mar-ott-van", "és a másikat sem írtuk felül")

    def test_naplo_nelkuli_visszavonas_valasza_valtozatlan(self):
        ir = {"kor": "KARTYA-20261004-101503", "tetel": "t1", "forras": "mos-kartya", "modell": None,
              "muveletek": [{"tipus": "uj", "ut": "T01/x.md", "tartalom": FM + "# x\n", "osztaly": "normal"}]}
        self.assertEqual(self.k("POST", "/api/gepi-iras", ir)[0], 200)
        kod, r = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "KARTYA-20261004-101503"})
        self.assertEqual((kod, set(r)), (200, {"ok", "sha"}))


if __name__ == "__main__":
    unittest.main()
