"""Javító 5: az `.apkg` import adversariális átnézése (`modulok/kartya/apkg.py`, `html.py`) — a csomag külső forrásból jön.

Zip-bomba, zstd-bomba, média-nevek (traversal, NUL, nem szöveg), a gyűjtemény SQLite-ja (típustalan oszlopok, rossz JSON,
NaN, túl nagy kártyaszám/mező, érvénytelen UTF-8), a HTML-tisztítás (kép-cél, négyzetes futásidő), a protobuf-dekóder."""
import json
import sqlite3
import time
import unittest
import zipfile
from compression import zstd
from pathlib import Path
from unittest import mock

from modulok.kartya import apkg, html
from tests.helpers import tmpdir
from tests.test_kartya_apkg import _idegen_gyujtemeny, _pb, _pb_varint


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def csomag(self, *, gy: bytes | None = None, media=None, meta: bytes | None = b"\x08\x02", extra=None, nev="a.apkg") -> Path:
        if gy is None:
            p = self.tmp / f"gy{len(list(self.tmp.iterdir()))}.sqlite"
            _idegen_gyujtemeny(p)
            gy = p.read_bytes()
        ut = self.tmp / nev
        with zipfile.ZipFile(ut, "w", zipfile.ZIP_DEFLATED) as z:
            if meta is not None:
                z.writestr("meta", meta)
            z.writestr("collection.anki21", gy)
            if media is not None:
                z.writestr("media", media if isinstance(media, bytes) else json.dumps(media))
            for k, v in (extra or {}).items():
                z.writestr(k, v)
        return ut


class ZipBombaTest(Alap):
    def test_tul_nagy_gyujtemeny(self):
        cs = self.csomag(gy=b"\0" * (3 << 20))
        with mock.patch.object(apkg, "GY_MAX", 1 << 20):
            with self.assertRaises(apkg.ApkgHiba) as e:
                apkg.beolvas(cs)
        self.assertIn("túl nagy", str(e.exception))

    def test_tul_nagy_media_jegyzek(self):
        cs = self.csomag(media=b"{" + b" " * (3 << 20) + b"}")
        with mock.patch.object(apkg, "MEDIA_JEGYZEK_MAX", 1 << 20):
            with self.assertRaises(apkg.ApkgHiba):
                apkg.beolvas(cs)

    def test_tul_nagy_meta(self):
        cs = self.csomag(meta=b"\x08\x02" + b"\0" * 200_000)
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(cs)

    def test_zstd_bomba_nem_tolti_be_a_kimenetet(self):
        gy = zstd.compress(b"\0" * (8 << 20))
        ut = self.tmp / "z.apkg"
        with zipfile.ZipFile(ut, "w") as z:
            z.writestr("meta", b"\x08\x03")
            z.writestr("collection.anki21b", gy)
        with mock.patch.object(apkg, "GY_MAX", 1 << 20):
            with self.assertRaises(apkg.ApkgHiba) as e:
                apkg.beolvas(ut)
        self.assertIn("túl nagy", str(e.exception))

    def test_zstd_media_jegyzek_bomba(self):
        gy = self.tmp / "g.sqlite"
        _idegen_gyujtemeny(gy, v18=True)
        ut = self.tmp / "z2.apkg"
        with zipfile.ZipFile(ut, "w") as z:
            z.writestr("meta", b"\x08\x03")
            z.writestr("collection.anki21b", zstd.compress(gy.read_bytes()))
            z.writestr("media", zstd.compress(b"\0" * (8 << 20)))
        with mock.patch.object(apkg, "MEDIA_JEGYZEK_MAX", 1 << 20):
            with self.assertRaises(apkg.ApkgHiba):
                apkg.beolvas(ut)

    def test_nem_zip_es_hianyzo_gyujtemeny_es_csonka_zstd(self):
        rossz = self.tmp / "rossz.apkg"
        rossz.write_bytes(b"ez nem zip")
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(rossz)
        ut = self.tmp / "ures.apkg"
        with zipfile.ZipFile(ut, "w") as z:
            z.writestr("meta", b"\x08\x03")
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(ut)
        csonka = self.tmp / "csonka.apkg"
        with zipfile.ZipFile(csonka, "w") as z:
            z.writestr("meta", b"\x08\x03")
            z.writestr("collection.anki21b", zstd.compress(b"x" * 5000)[:-9])
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(csonka)

    def test_nem_sqlite_gyujtemeny(self):
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(self.csomag(gy=b"nem adatbazis" * 100))


class MediaNevTest(Alap):
    def test_veszelyes_nevek_kiesnek_a_jegyzekbol(self):
        media = {"0": "ok.png", "1": "../kint.png", "2": "/abs/ut.png", "3": "a\0b.png", "4": "mappa/kep.png", "5": "..",
                 "6": "", "7": 5, "8": ["x"], "9": "\\win\\ut.png", "10": "x" * 300, "11": "szó \ud800.png", "12": ".",
                 "13": "CON\x07.png", "14": "szép ékezetes.jpg"}
        pakli = apkg.beolvas(self.csomag(media=media))
        self.assertEqual(pakli["media"], ["ok.png", "szép ékezetes.jpg"])
        self.assertEqual(pakli["kihagyva"].get("media_nev"), 13)

    def test_media_jegyzek_nem_objektum_vagy_hibas_json(self):
        for rossz in (b"[]", b'"szoveg"', b"{", b"\xff\xfe"):
            with self.subTest(rossz=rossz), self.assertRaises(apkg.ApkgHiba):
                apkg.beolvas(self.csomag(media=rossz))

    def test_latest_ervenytelen_utf8_nev(self):
        gy = self.tmp / "g.sqlite"
        _idegen_gyujtemeny(gy, v18=True)
        media = _pb(1, _pb(1, b"\xff\xfe.png")) + _pb(1, _pb(1, "jo.png")) + _pb(1, _pb(1, "../x.png"))
        ut = self.tmp / "u.apkg"
        with zipfile.ZipFile(ut, "w") as z:
            z.writestr("meta", b"\x08\x03")
            z.writestr("collection.anki21b", zstd.compress(gy.read_bytes()))
            z.writestr("media", zstd.compress(media))
        pakli = apkg.beolvas(ut)
        self.assertEqual(pakli["media"], ["jo.png"])
        self.assertEqual(pakli["kihagyva"].get("media_nev"), 2)

    def test_biztonsagos_nev_fuggveny(self):
        self.assertEqual(apkg.media_nev("kep.png"), "kep.png")
        for rossz in ("../a", "a/b", "a\\b", "", ".", "..", "a\0", "\x1fa", "x" * 256, 5, None):
            self.assertIsNone(apkg.media_nev(rossz), rossz)


class ProtobufTest(Alap):
    def test_vegtelen_varint(self):
        with self.assertRaises(apkg.ApkgHiba):
            apkg.protobuf(b"\x08" + b"\xff" * 5000 + b"\x01")

    def test_csonka_hossz(self):
        with self.assertRaises(apkg.ApkgHiba):
            apkg.protobuf(_pb_varint(1 << 3 | 2) + _pb_varint(1000) + b"abc")


class GyujtemenyTest(Alap):
    def gy(self, modosit) -> bytes:
        p = self.tmp / "m.sqlite"
        _idegen_gyujtemeny(p)
        c = sqlite3.connect(p)
        modosit(c)
        c.commit()
        c.close()
        return p.read_bytes()

    def test_tipustalan_oszlopok_es_rossz_json_nem_dobnak(self):
        def m(c):
            c.execute("UPDATE col SET models = ?, decks = ?", (json.dumps({"x": 5, "10": "nem objektum", "11": {"flds": [{}]}}), "[1,2]"))
            c.execute("UPDATE cards SET ord = 'x' WHERE id = 21")
            c.execute("UPDATE cards SET due = 'sok', \"left\" = 'x' WHERE id = 11")
            c.execute("UPDATE cards SET data = ? WHERE id = 41", (json.dumps({"s": float("nan"), "d": 5, "lrt": 1e30}),))
            c.execute("UPDATE revlog SET ease = 'x', time = 'z' WHERE cid = 41")
            c.execute("UPDATE notes SET flds = x'0001ff' WHERE id = 4")
        pakli = apkg.beolvas(self.csomag(gy=self.gy(m)))
        self.assertIsInstance(pakli["kartyak"], list)
        self.assertGreaterEqual(pakli["kihagyva"].get("hibas_sor", 0), 1)

    def test_nan_es_nagy_szam_nem_kerul_allapotba(self):
        def m(c):
            c.execute("UPDATE cards SET data = ? WHERE id = 11", (json.dumps({"s": 1e999, "d": 5, "lrt": 99}),))
            c.execute("UPDATE cards SET data = ? WHERE id = 41", (json.dumps({"s": 5.0, "d": float("nan")}),))
        for k in apkg.beolvas(self.csomag(gy=self.gy(m)))["kartyak"]:
            a = k["allapot"]
            for mezo in ("stabilitas", "nehezseg"):
                self.assertTrue(a[mezo] is None or 0 < a[mezo] < 1e6, (k["guid"], a))

    def test_tul_sok_kartya(self):
        with mock.patch.object(apkg, "KARTYA_MAX", 2):
            with self.assertRaises(apkg.ApkgHiba) as e:
                apkg.beolvas(self.csomag())
        self.assertIn("kártyá", str(e.exception))

    def test_tul_sok_naplo(self):
        with mock.patch.object(apkg, "NAPLO_MAX", 1):
            with self.assertRaises(apkg.ApkgHiba):
                apkg.beolvas(self.csomag())

    def test_tul_nagy_mezo_kimarad(self):
        def m(c):
            c.execute("UPDATE notes SET flds = ? WHERE id = 1", ("k" + "x" * 5000 + "\x1fv",))
        with mock.patch.object(apkg, "MEZO_MAX", 1000):
            pakli = apkg.beolvas(self.csomag(gy=self.gy(m)))
        self.assertEqual(pakli["kihagyva"].get("tul_nagy_mezo"), 1)
        self.assertNotIn("Gx#1", {k["guid"] for k in pakli["kartyak"]})

    def test_erteklen_guid_kimarad(self):
        def m(c):
            c.execute("UPDATE notes SET guid = ? WHERE id = 1", ("g" * 1000,))
        pakli = apkg.beolvas(self.csomag(gy=self.gy(m)))
        self.assertNotIn("g" * 1000, {k["guid"] for k in pakli["kartyak"]})
        self.assertGreaterEqual(pakli["kihagyva"].get("hibas_sor", 0), 1)

    def test_erytelen_utf8_nem_dob(self):
        def m(c):
            c.execute("UPDATE notes SET flds = CAST(x'4b6572ff6465735a1f56e1' AS TEXT) WHERE id = 1")
        pakli = apkg.beolvas(self.csomag(gy=self.gy(m)))
        k = next(x for x in pakli["kartyak"] if x["guid"] == "Gx#1")
        self.assertIn("�", k["kerdes"])

    def test_hianyzo_col_sor(self):
        def m(c):
            c.execute("DELETE FROM col")
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(self.csomag(gy=self.gy(m)))

    def test_wal_modu_gyujtemeny_olvashato(self):
        """A valódi Anki-gyűjtemények gyakran WAL-fejlécűek: az `immutable=1` nyitás -wal/-shm fájl nélkül is működik."""
        ut = self.tmp / "wal.sqlite"
        _idegen_gyujtemeny(ut)
        c = sqlite3.connect(ut)
        self.assertEqual(c.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        c.close()
        self.assertEqual(ut.read_bytes()[18:20], b"\x02\x02")
        pakli = apkg.beolvas(self.csomag(gy=ut.read_bytes()))
        self.assertEqual(len(pakli["kartyak"]), 4)

    def test_a_gyujtemeny_csak_olvasva_nyilik_es_nem_iras(self):
        """A rosszindulatú gyűjtemény triggere/nézete nem futhat írásra: a kapcsolat csak olvasó, az engedélyező csak SELECT-et enged."""
        def m(c):
            c.execute("CREATE TABLE naplo_t (x)")
            c.execute("CREATE TRIGGER t AFTER INSERT ON cards BEGIN INSERT INTO naplo_t VALUES (1); END")
        cs = self.csomag(gy=self.gy(m))
        nyitott = []
        eredeti = sqlite3.connect

        def figyel(*a, **k):
            c = eredeti(*a, **k)
            nyitott.append((a, k, c))
            return c
        with mock.patch.object(apkg.sqlite3, "connect", figyel):
            apkg.beolvas(cs)
        self.assertTrue(nyitott)
        a, k, c = nyitott[-1]
        self.assertIn("mode=ro", a[0])
        self.assertTrue(k.get("uri"))


class FormatumBefecskendezesTest(Alap):
    """Az idegen kártya szövege a kísérőjegyzet saját nyelvtanát nem forgathatja ki (C23b: a `formatum.ir` ezt írja a vaultba):
    a válasz végi `^c-…` egy másik kártya azonosítóját, a `— [[…]]` sor egy idegen forrás-horgonyt, a `[!card]` sor új
    kártyát jelenthetne."""

    def importal(self, k: str, v: str) -> dict:
        def m(c):
            c.execute("UPDATE notes SET flds = ? WHERE id = 1", (f"{k}\x1f{v}",))
        p = self.tmp / "inj.sqlite"
        _idegen_gyujtemeny(p)
        c = sqlite3.connect(p)
        m(c)
        c.commit()
        c.close()
        pakli = apkg.beolvas(self.csomag(gy=p.read_bytes()))
        return next(x for x in pakli["kartyak"] if x["guid"] == "Gx#1")

    def kor(self, kartya: dict):
        from modulok.kartya import formatum as f
        szoveg = f.ir([f.Kartya(kartya["kerdes"].replace("\n", " "), kartya["valasz"], "c-00000001")])
        return f.elemez(szoveg)

    def test_valasz_vegi_azonosito_nem_veheti_at_a_kartyat(self):
        e = self.kor(self.importal("Kérdés", "válasz <b>vége</b> ^c-99999999"))
        self.assertEqual([k.azon for k in e.kartyak], ["c-00000001"])

    def test_sorkezdo_azonosito_is_el_van_zarva(self):
        e = self.kor(self.importal("Kérdés", "válasz<br>^c-99999999"))
        self.assertEqual([k.azon for k in e.kartyak], ["c-00000001"])

    def test_forrassor_nem_hamisithato(self):
        e = self.kor(self.importal("Kérdés", "szöveg<br>— [[Titok#^m-1]]"))
        self.assertEqual(len(e.kartyak), 1)
        self.assertIsNone(e.kartyak[0].forras)

    def test_hamis_callout_nem_uj_kartya_es_nem_valtoztatja_a_kerdest(self):
        e = self.kor(self.importal("Kérdés", "a<br>[!card]- hamis<br>b"))
        self.assertEqual([k.kerdes for k in e.kartyak], ["Kérdés"])
        self.assertEqual(len(e.kartyak), 1)

    def test_a_szoveg_tartalma_megmarad_olvashatoan(self):
        k = self.importal("Kérdés ^c-99999999", "válasz ^c-99999999")
        self.assertIn("válasz", k["valasz"])
        self.assertIn("c-99999999", k["valasz"])
        self.assertNotRegex(k["valasz"] + "\n" + k["kerdes"], r"(?m)(^|[ \t])\^c-")

    def test_sima_szoveg_valtozatlan(self):
        k = self.importal("Mikor volt $x^2$?", "1526, **augusztus** 29. [a](b)")
        self.assertEqual((k["kerdes"], k["valasz"]), ("Mikor volt $x^2$?", "1526, **augusztus** 29. [a](b)"))


class HtmlBiztonsagTest(unittest.TestCase):
    def test_kep_cel_csak_fajlnev(self):
        for src, vart in (("../../etc/passwd", "passwd"), ("https://x.example/a/b.png", None),
                          ("a]] [[b", "a b"), ("data:image/png;base64,AAAA", None), ("k|ep#x.png", "kepx.png"),
                          ("mappa\\kep.png", "kep.png"), ("", None), ("ok.png", "ok.png")):
            md = html.html_md(f'<img src="{src}">')
            with self.subTest(src=src):
                self.assertNotIn("/", md)
                self.assertNotIn("]]]", md)
                self.assertEqual(md.count("[["), md.count("]]"))
                if vart is None:
                    self.assertEqual(md, "")
                else:
                    self.assertEqual(md, f"![[{vart}]]")

    def test_negyzetes_futasido_nincs(self):
        for rossz in ("<" * 200_000, "<div " * 40_000, "\\[" * 100_000, "\\(" * 100_000, "<img src=" * 30_000, "<b" * 100_000):
            t0 = time.monotonic()
            html.html_md(rossz)
            html.csupasz(rossz)
            self.assertLess(time.monotonic() - t0, 2.0, rossz[:12])

    def test_a_reszhalmaz_kor_utja_valtozatlan(self):
        for md in ("Mi a $q$?", "**b** és *i* `k`", "$$x^2$$", "![[abra.png]]", "sor1\nsor2"):
            self.assertEqual(html.html_md(html.md_html(md)), md)


if __name__ == "__main__":
    unittest.main()
