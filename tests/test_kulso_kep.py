"""04-embeds-02 / 01-rendering-04: külső kép letöltése kifejezett kattintásra — mockolt hálózattal (valódi kérés nincs), álvaulton."""
import json
import socket
import unittest
from types import SimpleNamespace
from unittest import mock

from core import csatolmany, kulso_kep
from core.utvonalak import HttpError
from tests.test_atnevezes import Alap

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x01" * 40
SVG = b'<?xml version="1.0"?>\n<!-- x -->\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'
NYILVANOS = "93.184.216.34"


class Valasz:
    def __init__(self, status=200, fejlec=None, torzs=b"", hiba=None):
        self.status = status
        self.fejlec = {k.lower(): v for k, v in (fejlec or {}).items()}
        self.torzs = torzs
        self.hiba = hiba
        self.olvasva = 0

    def getheader(self, nev, alap=None):
        return self.fejlec.get(nev.lower(), alap)

    def read(self, n):
        if self.hiba:
            raise self.hiba
        d = self.torzs[self.olvasva:self.olvasva + n]
        self.olvasva += len(d)
        return d


class Halozat:
    """Az ál-hálózat: (gazda, út) → válasz; minden kapcsolat naplózva (gazda, IP, út, fejlécek)."""

    def __init__(self, valaszok, cimek=None):
        self.valaszok = valaszok
        self.cimek = cimek or {}
        self.naplo = []

    def felold(self, host):
        if host not in self.cimek:
            raise socket.gaierror("nincs")
        return self.cimek[host]

    def kapcsolat(self, host, ip, timeout):
        h = self

        class K:
            def request(self, metodus, ut, headers):
                h.naplo.append((host, ip, ut, headers))
                self.ut = ut

            def getresponse(self):
                v = h.valaszok[(host, self.ut)]
                if isinstance(v, Exception):
                    raise v
                return v

            def close(self):
                pass
        return K()


def kep(torzs=PNG, tipus="image/png", **fejlec):
    return Valasz(200, {"Content-Type": tipus, "Content-Length": str(len(torzs)), **fejlec}, torzs)


class KulsoKepTest(Alap):
    def setUp(self):
        super().setUp()
        # Védőháló: ha bármi valódi hálózatot próbálna, a teszt bukik.
        for nev in ("getaddrinfo", "create_connection"):
            p = mock.patch.object(socket, nev, side_effect=AssertionError("valódi hálózati kérés"))
            p.start()
            self.addCleanup(p.stop)
        self.h = Halozat({}, {"img.example": [NYILVANOS]})
        for nev, fn in (("_felold", self.h.felold), ("_kapcsolat", self.h.kapcsolat)):
            p = mock.patch.object(kulso_kep, nev, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

    def app(self):
        return SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A)

    def letolt(self, url="https://img.example/a/Diagram%20one.png?x=1", forras="A/Cél.md"):
        return csatolmany.feltolt(self.app(), {"url": url, "forras": forras})

    def test_sikeres_letoltes_a_csatolmany_mappaba_pillanatkeppel(self):
        (self.v / ".obsidian/app.json").write_text(json.dumps({"attachmentFolderPath": "./Média"}))
        self.h.valaszok[("img.example", "/a/Diagram%20one.png?x=1")] = kep()
        r = self.letolt()
        self.assertEqual(r["ut"], "A/Média/Diagram one.png")
        self.assertFalse(r["meglevo"])
        self.assertEqual((self.v / r["ut"]).read_bytes(), PNG)
        host, ip, _, fejlec = self.h.naplo[0]
        self.assertEqual((host, ip), ("img.example", NYILVANOS))       # az ellenőrzött IP-re kapcsolódik
        self.assertNotIn("Cookie", fejlec)
        self.assertNotIn("Referer", fejlec)
        # a kép bináris: a szöveges pillanatkép kizárja (14. döntés), az import előtti kézi állapot viszont rögzül (mint a beillesztésnél)
        self.assertIn("kézi változások import előtt", self.repo.git("log", "-1").stdout)
        self.assertNotIn("Diagram one.png", self.repo.git("ls-files").stdout)
        self.assertEqual([p for p in (self.v / "A/Média").iterdir() if p.name.startswith(".")], [])

    def test_ismetelt_letoltes_nem_duplikal_mas_tartalom_uj_nevet_kap(self):
        self.h.valaszok[("img.example", "/a/Diagram%20one.png?x=1")] = kep()
        elso = self.letolt()
        self.h.valaszok[("img.example", "/a/Diagram%20one.png?x=1")] = kep()
        masodik = self.letolt()
        self.assertEqual((masodik["ut"], masodik["meglevo"]), (elso["ut"], True))
        self.h.valaszok[("img.example", "/a/Diagram%20one.png?x=1")] = kep(PNG + b"!")
        self.assertEqual(self.letolt()["ut"], "Diagram one 1.png")

    def test_a_kiterjesztes_a_magicbol_jon_es_a_nev_tisztitott(self):
        self.h.valaszok[("img.example", "/a%2F..%2Fx%23y.png")] = kep(JPG, "image/png")
        self.assertEqual(self.letolt("https://img.example/a%2F..%2Fx%23y.png")["ut"], "a-..-x-y.jpg")
        self.h.valaszok[("img.example", "/")] = kep(SVG, "image/svg+xml")
        self.assertEqual(self.letolt("https://img.example/")["ut"], "image.svg")

    def test_ssrf_es_semak_halozat_elott_elutasitva(self):
        self.h.cimek.update({"vegyes.example": [NYILVANOS, "10.0.0.5"], "belso.example": ["192.168.1.2"]})
        for url, statusz in [
            ("http://img.example/a.png", 400), ("file:///etc/passwd", 400), ("data:image/png;base64,AAAA", 400),
            ("javascript:alert(1)", 400), ("https://user:pw@img.example/a.png", 400), ("https://img.example:8443/a.png", 400),
            ("https://localhost/a.png", 403), ("https://127.0.0.1/a.png", 403), ("https://127.1/a.png", 403),
            ("https://0x7f000001/a.png", 403), ("https://2130706433/a.png", 403), ("https://[::1]/a.png", 403),
            ("https://[::ffff:127.0.0.1]/a.png", 403), ("https://10.0.0.1/a.png", 403), ("https://169.254.169.254/x", 403),
            ("https://100.64.0.1/a.png", 403), ("https://printer.local/a.png", 403), ("https://vegyes.example/a.png", 403),
            ("https://belso.example/a.png", 403), ("https://nincs.example/a.png", 502), ("https://img.example/a b.png", 400),
        ]:
            with self.subTest(url=url), self.assertRaises(HttpError) as e:
                self.letolt(url)
            self.assertEqual(e.exception.code, statusz, url)
        self.assertEqual(self.h.naplo, [])

    def test_atiranyitas_ellenorzott_privat_celra_nem_lep(self):
        self.h.cimek["cdn.example"] = ["8.8.4.4"]
        self.h.valaszok[("img.example", "/r")] = Valasz(302, {"Location": "https://cdn.example/k.png"})
        self.h.valaszok[("cdn.example", "/k.png")] = kep()
        self.assertEqual(self.letolt("https://img.example/r")["ut"], "k.png")
        for hova, statusz in (("https://127.0.0.1/x.png", 403), ("http://cdn.example/k.png", 400), ("file:///x", 400)):
            self.h.valaszok[("img.example", "/r")] = Valasz(301, {"Location": hova})
            with self.subTest(hova=hova), self.assertRaises(HttpError) as e:
                self.letolt("https://img.example/r")
            self.assertEqual(e.exception.code, statusz)
        self.h.valaszok[("img.example", "/hurok")] = Valasz(307, {"Location": "/hurok"})
        with self.assertRaises(HttpError) as e:
            self.letolt("https://img.example/hurok")
        self.assertEqual(e.exception.kod, "kulso_kep.atiranyitas")

    def test_meret_tipus_es_allapot_korlatok(self):
        nagy = kulso_kep.MAX_BAJT + 1
        esetek = [
            (Valasz(200, {"Content-Type": "image/png", "Content-Length": str(nagy)}, PNG), "kulso_kep.tul_nagy", 413),
            (Valasz(200, {"Content-Type": "image/png"}, PNG + b"\0" * nagy), "kulso_kep.tul_nagy", 413),
            (kep(b"<html>nope</html>", "text/html"), "kulso_kep.nem_kep", 415),
            (kep(b"<html>nope</html>", "image/png"), "kulso_kep.nem_kep", 415),
            (kep(PNG, "image/png", **{"Content-Encoding": "gzip"}), "kulso_kep.nem_kep", 415),
            (Valasz(404, {"Content-Type": "text/html"}), "kulso_kep.http_hiba", 502),
            (Valasz(200, {"Content-Type": "image/png"}, hiba=socket.timeout()), "kulso_kep.idotullepes", 504),
            (Valasz(200, {"Content-Type": "image/png"}, hiba=ConnectionResetError()), "kulso_kep.megszakadt", 502),
            (ConnectionRefusedError(), "kulso_kep.nem_elerheto", 502),
        ]
        for valasz, kod, statusz in esetek:
            self.h.valaszok[("img.example", "/x.png")] = valasz
            with self.subTest(kod=kod, statusz=statusz), self.assertRaises(HttpError) as e:
                self.letolt("https://img.example/x.png")
            self.assertEqual((e.exception.kod, e.exception.code), (kod, statusz))
        self.assertEqual(list(self.v.rglob("x.*")), [])

    def test_az_idokorlat_a_teljes_letoltesre_vonatkozik(self):
        self.h.valaszok[("img.example", "/x.png")] = kep()
        with self.assertRaises(HttpError) as e:
            kulso_kep.letolt_bajtok("https://img.example/x.png", idokorlat=0)
        self.assertEqual(e.exception.code, 504)

    def test_hianyzo_vagy_nem_letezo_forras_halozat_nelkul_bukik(self):
        for forras in (None, "", "Nincs.md"):
            with self.subTest(forras=forras), self.assertRaises(Exception):
                self.letolt("https://img.example/x.png", forras=forras)
        self.assertEqual(self.h.naplo, [])

    def test_magic_felismeres(self):
        self.assertEqual(kulso_kep.kep_tipus(b"GIF89a" + b"\0" * 10), "gif")
        self.assertEqual(kulso_kep.kep_tipus(b"RIFF\0\0\0\0WEBPVP8 "), "webp")
        self.assertEqual(kulso_kep.kep_tipus(b"\0\0\0\x1cftypavif\0\0"), "avif")
        self.assertIsNone(kulso_kep.kep_tipus(b"<svgx>"))
        self.assertIsNone(kulso_kep.kep_tipus(b"%PDF-1.7"))


if __name__ == "__main__":
    unittest.main()
