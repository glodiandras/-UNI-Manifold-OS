"""84. döntés (javasolt): egy oldal összes videója — a bejárás (felfedezés) és a jóváhagyott letöltés, HÁLÓZAT NÉLKÜL.

A CS50x szerkezetét utánozza (a valódi oldal 2026-10-14-i alakja): a `/x/weeks/` lista a `0/` … `10/` és `ai/` hetekre linkel, a heti oldal
a CS50 saját lejátszóját ágyazza be (`<iframe src="https://video.cs50.io/<YouTube-azonosító>">`), mellette `youtu.be` és
`youtube.com/watch` *linkek* (szinkronok, rövidek), és a fejléc a YouTube-lejátszási listára mutat. A felfedezés hamis letöltővel
(szótár-válaszoló) és egy valódi, helyi (127.0.0.1) HTTP-szerverrel is fut; a letöltés helyett a `lanc.letoltes` mock."""
import dataclasses
import http.server
import io
import json
import os
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import tasks, video_api, videolanc
from core.utvonalak import HttpError
from modulok.ytdlp import __main__ as cli
from modulok.ytdlp import bejaras, lanc
from tests.helpers import REPO, alg_core, tmpdir
from tests.test_videolanc import dns_hamis, ffmpeg_a_gyokerben
from tests.video_segedek import msp

START = "https://cs50.harvard.edu/x/weeks/"
HETEK = [str(i) for i in range(11)] + ["ai"]
# hét → a CS50-lejátszó YouTube-azonosítója (11 karakter; a 0. hét a valódi oldalé)
AZON = {h: ("UuIEbpQms8o" if h == "0" else f"lecture{h:0>4}"[:11].ljust(11, "x")) for h in HETEK}


def fejlec() -> str:
    return ('<header><a href="https://www.youtube.com/playlist?list=PLhQjrBD2T380hlTqAU8HfvVepCcjCqTg6">YouTube</a>'
            '<a href="../syllabus/">Syllabus</a><a href="https://cs50.harvard.edu/python">CS50P</a><a href="..">CS50x</a></header>')


def lista() -> str:
    linkek = "".join(f'<li><a href="{h}/">Week {h}</a></li>' for h in HETEK)
    return f"<html><head><title>Weeks - CS50x 2026</title></head><body>{fejlec()}<ul>{linkek}</ul></body></html>"


def het(h: str) -> str:
    a = AZON[h]
    return (f"<html><head><title>Week {h} - CS50x 2026</title></head><body>{fejlec()}<h1>Week {h}</h1>"
            f'<iframe allow="autoplay" allowfullscreen class="border" data-video src="https://video.cs50.io/{a}"></iframe>'
            f'<ul><li><a href="https://video.cs50.io/{a}">CS50 Video Player</a></li><li><a href="https://youtu.be/{a}">YouTube</a></li>'
            f'<li><a href="https://youtu.be/GHZzYAy4NKA">YouTube (Portuguese)</a></li>'
            f'<li><a href="https://www.youtube.com/watch?v=zkPUmtxeji8">This is CS50</a></li>'
            f'<li><a href="notes/">Notes</a></li><li><a href="slides.pdf">Slides</a></li></ul></body></html>')


def cs50_oldalak() -> dict[str, str]:
    o = {"https://cs50.harvard.edu/x/weeks": lista()}
    for h in HETEK:
        o[f"https://cs50.harvard.edu/x/weeks/{h}"] = het(h)
    return o


class Valaszolo:
    """Szótár-alapú `msp.crawl.Fetcher`: a robots.txt 404 (mint a valódi oldalon), minden kérés rögzítve."""

    def __init__(self, oldalak, robots_txt: str | None = None):
        self.oldalak, self.robots, self.kerest = oldalak, robots_txt, []

    def __call__(self, url):
        from msp.crawl import Page, normalize_url
        self.kerest.append(url)
        if url.endswith("/robots.txt"):
            return Page(url, 200, "text/plain", self.robots) if self.robots is not None else Page(url, 404, "text/html", "nincs")
        t = self.oldalak.get(normalize_url(url))
        return Page(url, 200, "text/html; charset=utf-8", t) if t is not None else Page(url, 404)


def video_url(h: str) -> str:
    return f"https://www.youtube.com/watch?v={AZON[h]}"


class BeagyazasTeszt(unittest.TestCase):
    def test_a_lejatszok_a_videora_fordulnak(self):
        esetek = {
            '<iframe src="https://www.youtube.com/embed/abcdefghijk?rel=0"></iframe>': "https://www.youtube.com/watch?v=abcdefghijk",
            '<iframe src="https://www.youtube-nocookie.com/embed/abcdefghijk"></iframe>': "https://www.youtube.com/watch?v=abcdefghijk",
            "<iframe src='https://youtu.be/abcdefghijk'></iframe>": "https://www.youtube.com/watch?v=abcdefghijk",
            '<iframe src="https://video.cs50.io/UuIEbpQms8o"></iframe>': "https://www.youtube.com/watch?v=UuIEbpQms8o",
            '<iframe src="https://player.vimeo.com/video/123456?h=1"></iframe>': "https://vimeo.com/123456",
            '<video controls src="/media/eloadas.mp4"></video>': "https://pelda.hu/media/eloadas.mp4",
            '<video><source src="e.mp4" type="video/mp4"></video>': "https://pelda.hu/kurzus/e.mp4",
        }
        for html, vart in esetek.items():
            with self.subTest(html=html):
                self.assertEqual(bejaras.beagyazott_videok(html, "https://pelda.hu/kurzus/"), [vart])

    def test_lejatszasi_lista_nem_video_es_a_tobb_lejatszo_sorrendben(self):
        self.assertEqual(bejaras.beagyazott_videok('<iframe src="https://www.youtube.com/embed/videoseries?list=PLx"></iframe>', "https://a.hu/"), [])
        html = ('<iframe src="https://video.cs50.io/AAAAAAAAAAA"></iframe><iframe src="https://www.youtube.com/embed/BBBBBBBBBBB"></iframe>'
                '<iframe src="https://video.cs50.io/AAAAAAAAAAA"></iframe><iframe src="https://maps.example/x"></iframe>')
        self.assertEqual(bejaras.beagyazott_videok(html, "https://a.hu/"),
                         ["https://www.youtube.com/watch?v=AAAAAAAAAAA", "https://www.youtube.com/watch?v=BBBBBBBBBBB"])

    def test_a_cs50_heti_oldal_fo_videoja_a_beagyazott_eloadas(self):
        self.assertEqual(bejaras.beagyazott_videok(het("0"), "https://cs50.harvard.edu/x/weeks/0/"), [video_url("0")])

    def test_cim(self):
        self.assertEqual(bejaras.oldal_cime(het("3")), "Week 3 - CS50x 2026")
        self.assertEqual(bejaras.oldal_cime("<h1>  Első  &amp; második </h1>"), "Első & második")
        self.assertEqual(bejaras.oldal_cime("<p>semmi</p>"), "")


class MintaEsHatokorTeszt(unittest.TestCase):
    """A valódi `modulok/ytdlp/config/config.yaml` mintái: a heti oldal videóoldal, a lista (csak `youtu.be`-linkkel) nem."""

    @classmethod
    def setUpClass(cls):
        konfig, _, _ = msp()
        cls.mcfg = konfig.Config.load(project_root=REPO / "modulok" / "ytdlp")

    def videooldal(self, html):
        from msp.crawl import Page, video_page_classifier
        return video_page_classifier(self.mcfg)("https://x/", Page("https://x/", 200, "text/html", html)).collect

    def test_beagyazasok_illeszkednek(self):
        for html in ('<iframe src="https://www.youtube.com/embed/abcdefghijk"></iframe>',
                     '<iframe width="560" src="https://youtu.be/abcdefghijk"></iframe>',
                     '<iframe src="https://video.cs50.io/UuIEbpQms8o"></iframe>', het("7")):
            with self.subTest(html=html[:60]):
                self.assertTrue(self.videooldal(html))

    def test_a_youtube_link_nem_teszi_videooldalla_a_listat(self):
        self.assertFalse(self.videooldal(lista()))
        self.assertFalse(self.videooldal('<a href="https://youtu.be/abcdefghijk">YouTube</a>'
                                         '<a href="https://www.youtube.com/watch?v=abcdefghijk">x</a>'))

    def test_a_hetek_a_kezdo_ut_alatt_vannak(self):
        from msp.crawl import Scope, normalize_url
        s = Scope.of(normalize_url(START))
        for h in HETEK:
            self.assertTrue(s.contains(f"https://cs50.harvard.edu/x/weeks/{h}"), h)
        for kivul in ("https://cs50.harvard.edu/x/syllabus", "https://cs50.harvard.edu/x", "https://cs50.harvard.edu/python",
                      "https://cs50.harvard.edu/x/weeks-archive", "https://video.cs50.io/UuIEbpQms8o"):
            self.assertFalse(s.contains(kivul), kivul)


class _Gyoker(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.cfg.path("ytdlp").mkdir(parents=True, exist_ok=True)
        cfgdir = self.cfg.path("ytdlp") / "config"
        cfgdir.mkdir(exist_ok=True)
        (cfgdir / "config.yaml").write_bytes((REPO / "modulok" / "ytdlp" / "config" / "config.yaml").read_bytes())
        self.mcfg = lanc.msp_konfig(self.cfg)
        self.mcfg = dataclasses.replace(self.mcfg, crawl=dataclasses.replace(self.mcfg.crawl, delay_seconds=0))


class FelfedezesTeszt(_Gyoker):
    def felfedez(self, valaszolo, **kw):
        alvasok = []
        naplo = []
        r = bejaras.felfedez(self.cfg, START, fetch=valaszolo, sleep=alvasok.append, log=naplo.append, mcfg=self.mcfg, **kw)
        return r, alvasok, naplo

    def test_a_cs50_szerkezet_minden_heti_eloadasa_letoltes_nelkul(self):
        v = Valaszolo(cs50_oldalak())
        r, alvasok, naplo = self.felfedez(v)
        self.assertEqual([t["video"] for t in r["tetelek"]], [video_url(h) for h in HETEK])
        self.assertEqual([t["cim"] for t in r["tetelek"]], [f"Week {h} - CS50x 2026" for h in HETEK])
        self.assertEqual(r["tetelek"][0]["oldal"], "https://cs50.harvard.edu/x/weeks/0")
        self.assertFalse(any(t["megvan"] for t in r["tetelek"]))
        self.assertEqual(r["oldalak"], 13)
        self.assertEqual(r["max_db"], 50)
        self.assertEqual(v.kerest[0], "https://cs50.harvard.edu/robots.txt", "a robots.txt az első kérés")
        self.assertFalse([u for u in v.kerest if "youtu" in u or "video.cs50.io" in u or "syllabus" in u or u.endswith(".pdf")],
                         "a kezdő úton kívülre és a videószolgáltatóhoz a felfedezés nem megy")
        self.assertFalse([u for u in v.kerest if "/notes" in u], "a videóoldal levél: a linkjei nem követődnek")
        self.assertEqual(len(alvasok), 13)
        self.assertFalse(self.cfg.path("staging").exists(), "a felfedezés semmit nem tölt le")

    def test_robots_txt_tiltas_es_crawl_delay(self):
        v = Valaszolo(cs50_oldalak(), "User-agent: *\nDisallow: /x/weeks/5\nCrawl-delay: 3\n")
        r, alvasok, _ = self.felfedez(v)
        self.assertNotIn(video_url("5"), [t["video"] for t in r["tetelek"]])
        self.assertEqual(r["robots_tiltott"], 1)
        self.assertEqual(r["kesleltetes_s"], 3.0)
        self.assertTrue(alvasok and set(alvasok) == {3.0})
        self.assertNotIn("https://cs50.harvard.edu/x/weeks/5", v.kerest)

    def test_a_teljes_tiltas_hiba(self):
        from msp.errors import CrawlError
        with self.assertRaises(CrawlError):
            self.felfedez(Valaszolo(cs50_oldalak(), "User-agent: *\nDisallow: /\n"))

    def test_leallitas_kerve_megall(self):
        stop = Path(self._t.name) / "stop"
        stop.write_text("")
        r, _, _ = self.felfedez(Valaszolo(cs50_oldalak()), stop_fajl=str(stop))
        self.assertTrue(r["megszakitva"])
        self.assertEqual(r["tetelek"], [])

    def test_ugyanaz_a_video_ket_oldalon_egyszer(self):
        o = cs50_oldalak()
        o["https://cs50.harvard.edu/x/weeks/ai"] = het("0")
        r, _, _ = self.felfedez(Valaszolo(o))
        self.assertEqual(len(r["tetelek"]), 11)

    def test_mentes_betoltes_es_a_letoltendo(self):
        r, _, _ = self.felfedez(Valaszolo(cs50_oldalak()))
        p = bejaras.ment(self.cfg, r)
        self.assertEqual(p, videolanc.bejaras_fajl(self.cfg, START))
        self.assertTrue(str(p).startswith(str(self.cfg.path("state"))))
        self.assertEqual(bejaras.betolt(self.cfg, START.rstrip("/")), r)
        self.assertIsNone(bejaras.betolt(self.cfg, START, max_kor_s=-1))
        urlek, meglevo = bejaras.letoltendo(r, lambda u: u in (video_url("0"), video_url("1")))
        self.assertEqual(meglevo, 2)
        self.assertEqual(urlek, [video_url(h) for h in HETEK[2:]])
        urlek, _ = bejaras.letoltendo(r, lambda u: False, csak=["https://cs50.harvard.edu/x/weeks/3", video_url("4")])
        self.assertEqual(urlek, [video_url("3"), video_url("4")])

    def test_a_meglevo_jel_az_archivumbol(self):
        _, _, folyamat = msp()
        from tests.video_segedek import hamis_letolto, info
        l = hamis_letolto(info(video_id="UuIEbpQms8o", url=video_url("0"), cim="CS50x 2026 - Lecture 0 - Scratch"))
        _, _, _, archivum = lanc.msp()
        arch = archivum.Archive(self.mcfg.archive_dir, enabled=True)
        out = folyamat.ingest_url(video_url("0"), config=self.mcfg, downloader=l, archive=arch)
        self.assertEqual(out.status, folyamat.STATUS_DOWNLOADED, out.message)
        megvan = bejaras.megvan_fuggveny(self.mcfg)
        self.assertTrue(megvan(video_url("0")))
        self.assertTrue(megvan("https://www.youtube.com/watch?v=UuIEbpQms8o&t=5"), "a YouTube-azonosító szerint is")
        self.assertFalse(megvan(video_url("1")))


class _Kezelo(http.server.BaseHTTPRequestHandler):
    oldalak: dict = {}

    def do_GET(self):  # noqa: N802
        ut = self.path.split("?")[0].rstrip("/") or "/"
        t = self.oldalak.get(ut)
        if t is None:
            self.send_response(404)
            self.end_headers()
            return
        b = t.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


class HelyiSzerverTeszt(_Gyoker):
    """Valódi HTTP (urllib, `HttpFetcher`) a 127.0.0.1-en: a fejléc, a robots.txt 404, a relatív linkek, a beágyazás — hálózat nélkül."""

    def test_valodi_http_a_helyi_szerveren(self):
        oldalak = {}
        for teljes, html in cs50_oldalak().items():
            oldalak[teljes.replace("https://cs50.harvard.edu", "")] = html
        _Kezelo.oldalak = oldalak
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Kezelo)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        start = f"http://127.0.0.1:{srv.server_address[1]}/x/weeks/"
        r = bejaras.felfedez(self.cfg, start, sleep=lambda s: None, log=lambda s: None, mcfg=self.mcfg)
        self.assertEqual([t["video"] for t in r["tetelek"]], [video_url(h) for h in HETEK])
        self.assertEqual(r["oldalak"], 13)


def _args(**kw):
    alap = dict(url=[], bejaras=START, igen=False, ujra=False, max=None, json=False, proba=False)
    alap.update(kw)
    return SimpleNamespace(**alap)


class ParancssorTeszt(_Gyoker):
    def setUp(self):
        super().setUp()
        dns_hamis(self)
        self.r = {"verzio": 1, "start": START, "kezdo": START.rstrip("/"), "ido": "2026-10-14T10:00:00+02:00", "kesleltetes_s": 10.0,
                  "oldalak": 13, "robots_tiltott": 0, "olvashatatlan": 0, "megszakitva": False, "max_db": 50,
                  "tetelek": [{"oldal": f"{START}{h}", "cim": f"Week {h}", "video": video_url(h), "tovabbi": [], "megvan": False}
                              for h in HETEK]}

    def futtat(self, args, megvan=lambda u: False, felfedez=None):
        ki, hiba = io.StringIO(), io.StringIO()
        with mock.patch.object(bejaras, "felfedez", side_effect=felfedez or (lambda *a, **k: json.loads(json.dumps(self.r)))) as ff, \
                mock.patch.object(bejaras, "megvan_fuggveny", return_value=megvan), \
                mock.patch.object(lanc, "letoltes", return_value=0) as le, redirect_stdout(ki), redirect_stderr(hiba):
            rc = cli.cmd_letoltes(self.cfg, args)
        return rc, ki.getvalue() + hiba.getvalue(), ff, le

    def test_igen_nelkul_csak_a_lista(self):
        rc, ki, ff, le = self.futtat(_args())
        self.assertEqual(rc, 0, ki)
        ff.assert_called_once()
        le.assert_not_called()
        self.assertIn("12 videó letölthető, 0 már megvan. Semmi nem töltődött le", ki)
        self.assertIn("Week ai", ki)
        self.assertTrue(videolanc.bejaras_fajl(self.cfg, START).is_file())

    def test_igen_a_mentett_listat_tolti_le_a_meglevok_nelkul(self):
        self.futtat(_args())
        rc, ki, ff, le = self.futtat(_args(igen=True), megvan=lambda u: u == video_url("0"))
        self.assertEqual(rc, 0, ki)
        ff.assert_not_called()     # a 24 órán belüli lista újrahasznosul
        (hivas,) = le.call_args_list
        self.assertEqual(hivas.args[1], [video_url(h) for h in HETEK[1:]])
        self.assertIn("1 már megvan, kimarad", ki)

    def test_ujra_bejar(self):
        self.futtat(_args())
        _, _, ff, _ = self.futtat(_args(igen=True, ujra=True))
        ff.assert_called_once()

    def test_minden_megvan(self):
        rc, ki, _, le = self.futtat(_args(igen=True), megvan=lambda u: True)
        self.assertEqual(rc, 0)
        le.assert_not_called()
        self.assertIn("Nincs letöltendő videó (12 már megvan)", ki)

    def test_a_korlat_folott_megerosites_kell(self):
        self.r["tetelek"] = [dict(self.r["tetelek"][0], video=f"https://www.youtube.com/watch?v=v{i:010d}") for i in range(60)]
        rc, ki, _, le = self.futtat(_args(igen=True))
        self.assertEqual(rc, 64)
        self.assertIn("--max 60", ki)
        le.assert_not_called()
        rc, ki, _, le = self.futtat(_args(igen=True, max=60))
        self.assertEqual(rc, 0, ki)
        self.assertEqual(len(le.call_args.args[1]), 60)
        rc, _, _, le = self.futtat(_args(igen=True, max=5))
        self.assertEqual(len(le.call_args.args[1]), 5)

    def test_bejaras_es_link_egyutt_hiba_es_link_nelkul_hiba(self):
        self.assertEqual(self.futtat(_args(url=["https://youtu.be/x"]))[0], 64)
        rc, ki, _, _ = self.futtat(_args(bejaras=None))
        self.assertEqual(rc, 64)
        self.assertIn("--bejaras", ki)
        self.assertEqual(self.futtat(_args(bejaras="http://127.0.0.1/x"))[0], 64)

    def test_a_bejaro_hibaja_magyar_uzenettel(self):
        from msp.errors import CrawlError

        def hiba(*a, **k):
            raise CrawlError("robots.txt of x does not allow", hint="a tipp")
        rc, ki, _, le = self.futtat(_args(), felfedez=hiba)
        self.assertEqual(rc, 1)
        self.assertIn("a tipp", ki)
        le.assert_not_called()

    def test_a_lepes_a_ki_fajlba_ir(self):
        ki_fajl = Path(self._t.name) / "ki" / "e.json"
        with mock.patch.object(bejaras, "felfedez", return_value=self.r), mock.patch.dict(os.environ, {"MOS_FEJLESZTO": "1", "MOS_VIDEO_HELYI_ENGEDELY": "1"}), \
                redirect_stdout(io.StringIO()) as ki:
            rc = cli.lepes_bejaras(self.cfg, SimpleNamespace(url=[START], ki=str(ki_fajl)))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(ki_fajl.read_text(encoding="utf-8"))["tetelek"][3]["video"], video_url("3"))
        self.assertIn("[manifold-progress] 100%", ki.getvalue())
        self.assertIn("12 videó", ki.getvalue())


class CoreTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        dns_hamis(self)
        ffmpeg_a_gyokerben(self.root)

    def test_a_bejaras_terve(self):
        (l,), osszeg, _ = videolanc._bejaras_terv(self.cfg, {"url": START}, "/stop")
        self.assertEqual(l.argv[3:7], ["modulok.ytdlp", "lepes", "bejaras", "--url"])
        self.assertEqual(l.argv[-1], str(videolanc.bejaras_fajl(self.cfg, START)))
        self.assertEqual(l.jogok, "nincs")
        self.assertIn("letöltés nélkül", osszeg)
        for p in ({}, {"url": 5}, {"url": "ftp://x/y"}, {"url": "http://localhost/x"}, "x"):
            with self.subTest(p=p), self.assertRaises(tasks.Invalid):
                videolanc._bejaras_terv(self.cfg, p, "/stop")
        videolanc.regisztral()
        t = tasks.REGISTRY[videolanc.BEJARAS]
        self.assertFalse(t.automatikus)
        self.assertEqual(t.resources, frozenset())

    def test_a_letoltes_korlatja_bejarasbol(self):
        sok = [f"https://www.youtube.com/watch?v=v{i:010d}" for i in range(60)]
        with self.assertRaises(tasks.Invalid):
            videolanc._terv(self.cfg, {"urlek": sok[:21]}, "/stop")            # egyedi linkek: 20
        (l,), _, _ = videolanc._terv(self.cfg, {"urlek": sok[:50], "bejaras": True}, "/stop")
        self.assertEqual(l.argv.count("--url"), 50)
        with self.assertRaises(tasks.Invalid) as e:
            videolanc._terv(self.cfg, {"urlek": sok, "bejaras": True}, "/stop")
        self.assertIn("meg kell erősíteni", str(e.exception))
        (l,), _, _ = videolanc._terv(self.cfg, {"urlek": sok, "bejaras": True, "megerosit": True}, "/stop")
        self.assertEqual(l.argv.count("--url"), 60)
        with self.assertRaises(tasks.Invalid):
            videolanc._terv(self.cfg, {"urlek": sok[:3], "bejaras": "igen"}, "/stop")

    def test_a_vegpont(self):
        app = SimpleNamespace(cfg=self.cfg)
        self.assertEqual(video_api.bejaras(app, START), {"kesz": False})
        with self.assertRaises(HttpError):
            video_api.bejaras(app, None)
        p = videolanc.bejaras_fajl(self.cfg, START)
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"start": START, "ido": "x", "oldalak": 13, "max_db": 50,
                                 "tetelek": [{"oldal": "o", "cim": "c", "video": "v", "megvan": True, "tovabbi": ["t"]}]}), encoding="utf-8")
        d = video_api.bejaras(app, START + "  ")
        self.assertTrue(d["kesz"])
        self.assertEqual(d["tetelek"], [{"oldal": "o", "cim": "c", "video": "v", "megvan": True}])
        self.assertEqual(d["max_db"], 50)


if __name__ == "__main__":
    unittest.main()
