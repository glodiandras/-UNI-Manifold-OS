"""A média-kiszolgálás (`/media/<token>/<út>`) és a C10 HTTP-végpontjai, a core-ral együtt, álvaulton.

Amit ezek a tesztek őriznek:
  - a token az egyetlen hitelesítés (a böngésző-elemek nem küldhetnek X-Manifold fejlécet), a `Host`-ellenőrzés marad;
  - csak a vaulton belüli, rejtett szegmens nélküli, engedélylistás fájl jön; a Content-Type a listából;
  - a Range (206/416) és a HEAD, az ETag (304) működik — a WebKit videója enélkül nem játszik;
  - az SVG sandbox-CSP-t kap; a végpontok (feloldás, linkcél, beágyazás, aliasok, átnevezés) elérhetők.
"""
import http.client
import io
import json
import os
import threading
import unittest
import urllib.parse
from unittest import mock

from core import kepek, server, snapshot
from tests.helpers import API_TITOK, tmpdir
from tests.index_segedek import ALAP, alvault, var_ra
from tests.test_core_api import _Kimenet


class _MediaAlap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        fajlok = dict(ALAP)
        fajlok["media/video.mp4"] = bytes(range(256)) * 40
        fajlok["media/kep.svg"] = b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"
        fajlok["media/rejtett/.titok.png"] = b"x"
        fajlok[".rejtett/kep.png"] = b"x"
        fajlok["media/szoveg.md"] = "# nem média\n"
        fajlok["Beagyazo.md"] = "# Beágyazó\n[[Cél]] ![[kep.png]]\n"
        self.cfg, self.v = alvault(self._t.name, fajlok)
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        os.symlink(self.v.parent / "kint.txt", self.v / "media" / "kint.png")
        (self.v.parent / "kint.txt").write_bytes(b"titok")
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.api("GET", "/api/vault/index")[1].get("kesz"), 30))
        self.token = self.api("GET", "/api/allapot")[1]["media_token"]

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def keres(self, method, path, fejlec=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, headers={"Host": host or f"127.0.0.1:{self.port}", **(fejlec or {})})
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()

    def api(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def media(self, rel, **kw):
        return self.keres(kw.pop("method", "GET"), f"/media/{self.token}/" + urllib.parse.quote(rel), **kw)



class MediaApiTest(_MediaAlap):
    # ------------------------------------------------------------ média

    def test_token_az_egyetlen_hitelesites(self):
        kod, fej, b = self.media("kep.png")
        self.assertEqual((kod, fej["Content-Type"], b), (200, "image/png", b"\x89PNG\r\n"))   # X-Manifold nélkül
        self.assertEqual(self.keres("GET", "/media/rossz-token/kep.png")[0], 403)
        self.assertEqual(self.keres("GET", "/media//kep.png")[0], 403)
        self.assertEqual(self.keres("GET", f"/media/{self.token}/kep.png", host="evil.example")[0], 403)

    def test_utvedelem_es_engedelylista(self):
        for rel, kod in (("media/szoveg.md", 400), ("Cél.md", 400), (".rejtett/kep.png", 400),
                         ("media/rejtett/.titok.png", 400), ("media/kint.png", 400), ("../kint.txt", 400),
                         ("media/../../kint.txt", 400), ("nincs.png", 404), ("", 400)):
            self.assertEqual(self.media(rel)[0], kod, rel)

    def test_range(self):
        teljes = bytes(range(256)) * 40
        kod, fej, b = self.media("media/video.mp4")
        self.assertEqual((kod, fej["Accept-Ranges"], fej["Content-Type"], len(b)), (200, "bytes", "video/mp4", len(teljes)))
        kod, fej, b = self.media("media/video.mp4", fejlec={"Range": "bytes=10-19"})
        self.assertEqual((kod, b, fej["Content-Range"]), (206, teljes[10:20], f"bytes 10-19/{len(teljes)}"))
        kod, fej, b = self.media("media/video.mp4", fejlec={"Range": "bytes=10230-"})
        self.assertEqual((kod, b), (206, teljes[10230:]))
        kod, fej, b = self.media("media/video.mp4", fejlec={"Range": "bytes=-5"})
        self.assertEqual((kod, b), (206, teljes[-5:]))
        kod, fej, b = self.media("media/video.mp4", fejlec={"Range": "bytes=999999-"})
        self.assertEqual((kod, fej["Content-Range"]), (416, f"bytes */{len(teljes)}"))
        self.assertEqual(self.media("media/video.mp4", fejlec={"Range": "bytes=x"})[0], 416)

    def test_keretezes_elleni_fejlecek(self):
        """T103: a core válaszai idegen oldalba keretezhetők voltak (a CSP csak `<meta>`-ban élt, ahol a `frame-ancestors`
        nem hat; `X-Frame-Options` nem volt). Saját originű keretezés (a PDF/média-beágyazás `<iframe>`-je) marad."""
        for kod, fej in (self.media("kep.png")[:2], self.media("kep.png", method="HEAD")[:2], self.media("nincs.png")[:2],
                         self.media("media/video.mp4", fejlec={"Range": "bytes=10-19"})[:2],
                         self.media("media/video.mp4", fejlec={"Range": "bytes=999999-"})[:2]):
            self.assertEqual(fej["X-Frame-Options"], "SAMEORIGIN", kod)
            self.assertIn("frame-ancestors 'self'", fej["Content-Security-Policy"], kod)
        _, fej, _ = self.media("kep.png")
        self.assertEqual(self.media("kep.png", fejlec={"If-None-Match": fej["ETag"]})[1]["X-Frame-Options"], "SAMEORIGIN")   # 304
        _, fej, _ = self.media("media/kep.svg")                                  # az SVG sandbox-CSP-je megmarad, kiegészül
        self.assertIn("sandbox", fej["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'self'", fej["Content-Security-Policy"])
        self.assertEqual(fej["Content-Security-Policy"].count("frame-ancestors"), 1)
        self.assertEqual(self.keres("GET", f"/media/rossz-token/kep.png")[1]["X-Frame-Options"], "SAMEORIGIN")     # 403

    def test_head_etag_svg(self):
        kod, fej, b = self.media("media/video.mp4", method="HEAD")
        self.assertEqual((kod, b, fej["Content-Length"]), (200, b"", "10240"))
        kod, fej, _ = self.media("kep.png")
        self.assertEqual(self.media("kep.png", fejlec={"If-None-Match": fej["ETag"]})[0], 304)
        kod, fej, _ = self.media("media/kep.svg")
        self.assertIn("sandbox", fej["Content-Security-Policy"])
        self.assertEqual(fej["X-Content-Type-Options"], "nosniff")

    # ------------------------------------------------------------ végpontok

    def test_feloldas_linkcel_beagyazas_aliasok(self):
        kod, d = self.api("POST", "/api/vault/feloldas", {"forras": "A/Forrás.md", "celok": ["Jegyzet", "nincs"]})
        self.assertEqual((kod, [e["ut"] for e in d["eredmenyek"]]), (200, ["A/Jegyzet.md", None]))
        self.assertEqual(self.api("POST", "/api/vault/feloldas", {"forras": "x.md", "celok": "rossz"})[0], 400)
        kod, d = self.api("GET", "/api/vault/linkcel?" + urllib.parse.urlencode({"ut": "B/Jegyzet.md", "forras": "C/x.md"}))
        self.assertEqual((kod, d["cel"]), (200, "B/Jegyzet"))
        kod, d = self.api("GET", "/api/vault/beagyazas?" + urllib.parse.urlencode({"forras": "x.md", "cel": "Cél", "alcel": "Fejezet"}))
        self.assertEqual((kod, d["tipus"], d["szoveg"]), (200, "jegyzet", "# Fejezet\nSzöveg ^blokk\n"))
        self.assertEqual(self.api("GET", "/api/vault/aliasok")[1]["aliasok"]["Cél.md"], ["Célpont"])

    def test_atnevezes_http_en_at(self):
        kod, t = self.api("POST", "/api/vault/atnevezes/terv", {"ut": "Beagyazo.md", "uj": "Beágyazó új.md"})
        self.assertEqual(kod, 200)
        self.assertTrue(t["ok"])
        kod, r = self.api("POST", "/api/vault/atnevezes", {"ut": "Beagyazo.md", "uj": "Beágyazó új.md", "terv_hash": t["terv_hash"]})
        self.assertEqual((kod, r["ok"]), (200, True))
        self.assertTrue((self.v / "Beágyazó új.md").exists())
        self.assertFalse((self.v / "Beagyazo.md").exists())
        kod, d = self.api("GET", "/api/vault/jegyzet?ut=" + urllib.parse.quote("Beágyazó új.md"))
        self.assertEqual(kod, 200)
        # a visszavonás a meglévő végponton megy
        kod, u = self.api("POST", "/api/pillanat/vault/visszavonas", {"sha": r["pillanat"]})
        self.assertEqual(kod, 200)
        self.assertTrue((self.v / "Beagyazo.md").exists())
        # hibák
        self.assertEqual(self.api("POST", "/api/vault/atnevezes", {"ut": "Cél.md", "uj": "Új.md", "terv_hash": "x"})[0], 409)
        self.assertEqual(self.api("POST", "/api/vault/atnevezes", {"ut": "nincs.md", "uj": "Új.md", "terv_hash": "x"})[0], 404)
        self.assertEqual(self.api("POST", "/api/vault/atnevezes/terv", {"ut": "kep.png", "uj": "k.png"})[1]["ok"], True)


if __name__ == "__main__":
    unittest.main()


class KepekTest(_MediaAlap):
    """A `?w=` kicsinyítés (C11a, audit M9): vödör, gyorsítótár, tájolás, alfa, hibatűrés; a vaultba nem ír."""

    def setUp(self):
        super().setUp()
        from PIL import Image
        d = self.v / "fotok"
        d.mkdir()
        Image.new("RGB", (2400, 1600), (200, 30, 30)).save(d / "nagy.jpg", quality=90)
        exif = Image.Exif()
        exif[0x0112] = 6                                  # 90°-os forgatás: a megjelenített méret 1600 × 2400
        Image.new("RGB", (2400, 1600), (30, 200, 30)).save(d / "allo.jpg", exif=exif)
        Image.new("RGBA", (2000, 1000), (0, 0, 255, 128)).save(d / "alfas.png")
        Image.new("RGB", (300, 200), (9, 9, 9)).save(d / "kicsi.jpg")
        elso = Image.new("RGB", (2400, 1600), (10, 20, 30))                  # a telefonok MPO-JPEG-je: több képkocka, nem animáció
        elso.save(d / "telefon.jpg", format="MPO", save_all=True, append_images=[Image.new("RGB", (300, 200))])
        (d / "serult.jpg").write_bytes(b"\xff\xd8\xff nem kep")
        self.keszitesek = 0
        eredeti = kepek._keszit

        def szamol(*a, **k):
            self.keszitesek += 1
            return eredeti(*a, **k)
        p = mock.patch.object(kepek, "_keszit", szamol)
        p.start()
        self.addCleanup(p.stop)

    def kep(self, rel, w, **kw):
        return self.keres(kw.pop("method", "GET"), f"/media/{self.token}/" + urllib.parse.quote(rel)
                          + (f"?w={w}" if w is not None else ""), **kw)

    @staticmethod
    def meret(b):
        from PIL import Image
        with Image.open(io.BytesIO(b)) as im:
            return im.size, im.format, im.mode

    def vault_lista(self):
        return sorted(str(p.relative_to(self.v)) for p in self.v.rglob("*") if p.is_file())

    def test_voder_kerekites(self):
        for w, szeles in ((100, 400), (400, 400), (500, 800), (801, 1600), (1600, 1600), (1700, 1600), (4096, 1600)):
            kod, fej, b = self.kep("fotok/nagy.jpg", w)
            self.assertEqual((kod, fej["Content-Type"]), (200, "image/jpeg"), w)
            self.assertEqual(self.meret(b)[0], (szeles, round(szeles * 2 / 3)), w)
        eredeti = (self.v / "fotok" / "nagy.jpg").read_bytes()
        self.assertEqual(self.kep("fotok/nagy.jpg", None)[2], eredeti)                 # a `w` nélküli kérés (nagyítás): az eredeti

    def test_a_kisebb_kep_az_eredeti_es_nem_keszul_masolat(self):
        kod, fej, b = self.kep("fotok/kicsi.jpg", 800)
        self.assertEqual((kod, b), (200, (self.v / "fotok" / "kicsi.jpg").read_bytes()))
        self.assertFalse(self.cfg.path("vault_kepek").exists() and any(self.cfg.path("vault_kepek").rglob("*.jpg")))

    def test_gyorsitotar_es_a_vaulthoz_nem_nyul(self):
        elotte = self.vault_lista()
        bajtok = (self.v / "fotok" / "nagy.jpg").read_bytes()
        b1 = self.kep("fotok/nagy.jpg", 800)[2]
        b2 = self.kep("fotok/nagy.jpg", 800)[2]
        self.assertEqual((b1, self.keszitesek), (b2, 1))                         # a második a gyorsítótárból
        # a kép és (C33, T177) a kísérője (`<kulcs>.forras`: az árva bejegyzés felismeréséhez)
        fajlok = sorted(p for p in self.cfg.path("vault_kepek").rglob("*") if p.is_file())
        self.assertEqual([p.suffix for p in fajlok], [".forras", ".jpg"])
        self.assertEqual(fajlok[0].stem, fajlok[1].stem)
        self.assertEqual(self.vault_lista(), elotte)                              # a vaultban semmi nem változott
        self.assertEqual((self.v / "fotok" / "nagy.jpg").read_bytes(), bajtok)
        os.utime(self.v / "fotok" / "nagy.jpg", (2_000_000_000, 2_000_000_000))   # módosult kép: új kulcs
        self.kep("fotok/nagy.jpg", 800)
        self.assertEqual(self.keszitesek, 2)
        kod, fej, _ = self.kep("fotok/nagy.jpg", 800)
        self.assertEqual(self.kep("fotok/nagy.jpg", 800, fejlec={"If-None-Match": fej["ETag"]})[0], 304)

    def test_mpo_telefonfoto_is_kicsinyul(self):
        kod, fej, b = self.kep("fotok/telefon.jpg", 800)
        self.assertEqual((kod, self.meret(b)[0]), (200, (800, 533)))

    def test_exif_tajolas(self):
        self.assertEqual(self.meret(self.kep("fotok/allo.jpg", 800)[2])[0], (800, 1200))

    def test_alfas_png_marad_alfas(self):
        kod, fej, b = self.kep("fotok/alfas.png", 800)
        self.assertEqual((kod, fej["Content-Type"]), (200, "image/png"))
        self.assertEqual(self.meret(b), ((800, 400), "PNG", "RGBA"))

    def test_hibas_w(self):
        for w in ("x", "10", "5000", "-1", "1.5"):
            self.assertEqual(self.kep("fotok/nagy.jpg", w)[0], 400, w)

    def test_nem_kicsinyitheto_tipus_valtozatlan(self):
        for rel in ("media/kep.svg", "media/video.mp4"):
            self.assertEqual(self.kep(rel, 400)[2], self.media(rel)[2], rel)

    def test_serult_kep_az_eredeti(self):
        kod, fej, b = self.kep("fotok/serult.jpg", 400)
        self.assertEqual((kod, b), (200, b"\xff\xd8\xff nem kep"))

    def test_parhuzamos_kerest_egyszer_keszit(self):
        eredmenyek = []
        szalak = [threading.Thread(target=lambda: eredmenyek.append(self.kep("fotok/nagy.jpg", 400)[2])) for _ in range(6)]
        for t in szalak:
            t.start()
        for t in szalak:
            t.join(30)
        self.assertEqual((len(eredmenyek), len(set(eredmenyek)), self.keszitesek), (6, 1, 1))


class PoszterTest(_MediaAlap):
    """A `?poster=1` videó-előnézet (E14): pinelt (itt hamis) ffmpeg, gyorsítótár, hibatűrés, útvédelem; a vaultba nem ír."""

    def setUp(self):
        super().setUp()
        from PIL import Image
        from tests.video_segedek import pin_es_ffmpeg
        kep = os.path.join(self._t.name, "poszter.jpg")
        Image.new("RGB", (800, 450), (10, 120, 200)).save(kep, quality=90)
        self.naplo = os.path.join(self._t.name, "ffmpeg-hivasok.txt")
        self.root = self.cfg.root
        self.ff = pin_es_ffmpeg(
            self.cfg, self.root,
            f'#!/bin/sh\nfor a; do u=$a; done\necho "$@" >> "{self.naplo}"\ncp "{kep}" "$u"\n')

    def hivasok(self):
        try:
            with open(self.naplo) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def poszter(self, rel, q="poster=1"):
        return self.keres("GET", f"/media/{self.token}/" + urllib.parse.quote(rel) + "?" + q)

    def test_jpeg_es_gyorsitotar(self):
        kod, fej, b = self.poszter("media/video.mp4")
        self.assertEqual((kod, fej["Content-Type"]), (200, "image/jpeg"))
        self.assertTrue(b.startswith(b"\xff\xd8"))
        self.assertEqual(self.poszter("media/video.mp4")[2], b)
        self.assertEqual(len(self.hivasok()), 1)                      # a második kérés a gyorsítótárból jött
        self.assertIn("-ss 1.000", self.hivasok()[0])
        self.poszter("media/video.mp4", "poster=1&t=12.5")
        self.assertEqual(len(self.hivasok()), 2)
        self.assertIn("-ss 12.500", self.hivasok()[1])

    def test_utvedelem(self):
        self.assertEqual(self.poszter("media/kint.png")[0], 400)          # nem videó
        self.assertIn(self.poszter("../kint.mp4")[0], (400, 403, 404))
        self.assertIn(self.poszter(".rejtett/video.mp4")[0], (400, 403, 404))
        self.assertEqual(self.poszter("media/nincs.mp4")[0], 404)
        self.assertEqual(self.hivasok(), [])
        r = self.keres("GET", f"/media/rossz-token/media/video.mp4?poster=1")
        self.assertEqual(r[0], 403)

    def test_hibas_t(self):
        for t in ("x", "nan", "inf"):
            self.assertEqual(self.poszter("media/video.mp4", f"poster=1&t={t}")[0], 400, t)

    def test_ffmpeg_hibaja_404(self):
        from tests.video_segedek import pin_es_ffmpeg
        pin_es_ffmpeg(self.cfg, self.root, "#!/bin/sh\nexit 1\n")
        self.assertEqual(self.poszter("media/video.mp4")[0], 404)
        self.assertEqual(self.media("media/video.mp4")[0], 200)           # maga a videó továbbra is kiszolgálódik

    def test_pin_nelkul_zarva_hibazik(self):
        os.unlink(self.root / "config" / "runtime-pins.env")
        self.assertEqual(self.poszter("media/video.mp4")[0], 404)
        self.assertEqual(self.hivasok(), [])

    def test_a_vaultba_nem_ir(self):
        elotte = sorted(p.name for p in (self.v / "media").iterdir())
        self.poszter("media/video.mp4")
        self.assertEqual(sorted(p.name for p in (self.v / "media").iterdir()), elotte)
