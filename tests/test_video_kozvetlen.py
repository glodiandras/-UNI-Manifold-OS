"""84. döntés (javasolt kiegészítés): a bejárt videóoldal közvetlen videófájlja a beágyazott lejátszó helyett — HÁLÓZAT NÉLKÜL.

A fixtúra a CS50x heti oldalának 2026-10-14-i szerkezetét utánozza: `<html lang="en-us">`, a CS50-lejátszó iframe-je, és a „Lecture” lista
`<a href>`-jei a `cdn.cs50.net`-re: a diák (`lecture1.pdf`), a forráskód PDF-je (`src1.pdf`), a feliratok (`lang/en/lecture1.srt`,
`lang/pt/aula1.srt`, `lang/es/clase1.srt`), és a videó HDR/SDR × 360p/720p/1080p/4K változatai, angolul és két szinkronnal (`pt/aula1-…`,
`es/clase1-…`). A letöltés hamis letöltővel és hamis felirat-kérővel fut; a staging a valódi `ingest_url` kimenete."""
import dataclasses
import io
import json
import os
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import atirat, video_api, videolanc
from modulok.ytdlp import bejaras, kozvetlen, lanc, staging
from tests.helpers import REPO, alg_core, tmpdir
from tests.test_video_bejaras import START, Valaszolo, cs50_oldalak, fejlec, lista
from tests.video_segedek import FFMPEG, ffmpeg_elerheto, info, msp, pin_es_ffmpeg

CDN = "https://cdn.cs50.net/2025/fall/lectures"
HETEK = [str(i) for i in range(11)] + ["ai"]
YT = {h: f"yt{h:0>9}"[:11] for h in HETEK}


def _mp4_lista(alap: str, mappa: str) -> str:
    sorok = []
    for dinamika, utotag in (("HDR", "-hdr"), ("SDR", "")):
        sorok.append(f'<li data-marker="+">{dinamika}<ul>')
        for q in ("360p", "720p", "1080p", "4k"):
            sorok.append(f'<li data-marker="*"><a href="{mappa}{alap}-{q}{utotag}.mp4">{q.upper() if q == "4k" else q}</a></li>')
        sorok.append("</ul></li>")
    return "".join(sorok)


def cs50_het(h: str, *, minosegek=None, cim: str | None = None, lang: str | None = "en-us") -> str:
    """A heti oldal közvetlen fájlokkal (a valódi szerkezet szerint). `minosegek`: csak ezek a (minőség, utótag) változatok."""
    n = h if h != "ai" else "ai"
    d = f"{CDN}/{n}/"
    mp4 = _mp4_lista(f"lecture{n}", d) + _mp4_lista(f"aula{n}", d + "pt/") + _mp4_lista(f"clase{n}", d + "es/")
    if minosegek is not None:
        mp4 = "".join(f'<li><a href="{d}lecture{n}-{q}{u}.mp4">{q}</a></li>' for q, u in minosegek) + _mp4_lista(f"clase{n}", d + "es/")
    html_lang = f' lang="{lang}"' if lang else ""
    return (f"<!DOCTYPE html><html{html_lang}><head><title>{cim or f'Week {h} - CS50x 2026'}</title></head><body>{fejlec()}"
            f'<h1>Week {h}</h1><iframe allow="autoplay" allowfullscreen class="border" data-video src="https://video.cs50.io/{YT[h]}"></iframe>'
            f'<pre><code>wget {d}src{n}.zip</code></pre>'
            f'<ul><li data-marker="-">Lecture<ul>'
            f'<li><a href="{d}lecture{n}.mp3">Audio</a></li><li><a href="../../notes/{n}/">Notes</a></li>'
            f'<li data-marker="-">Slides<ul><li><a href="https://docs.google.com/presentation/d/x/edit">Google Slides</a></li>'
            f'<li><a href="{d}lecture{n}.pdf">PDF</a></li></ul></li>'
            f'<li data-marker="-">Source Code<ul><li><a href="{d}src{n}/">Index</a></li><li><a href="{d}src{n}.pdf">PDF</a></li>'
            f'<li><a href="{d}src{n}.zip">Zip</a></li></ul></li>'
            f'<li data-marker="+">Subtitles<ul><li><a href="{d}lang/en/lecture{n}.srt">English</a></li>'
            f'<li><a href="{d}lang/pt/aula{n}.srt">Portuguese</a></li><li><a href="{d}lang/es/clase{n}.srt">Spanish</a></li></ul></li>'
            f'<li data-marker="-">Video<ul><li data-marker="+">English<ul>'
            f'<li><a href="https://video.cs50.io/{YT[h]}">CS50 Video Player</a></li><li data-marker="+">MP4<ul>{mp4}</ul></li>'
            f'<li><a href="https://youtu.be/{YT[h]}">YouTube</a></li></ul></li></ul></li></ul></li></ul></body></html>')


def kozvetlen_oldalak() -> dict[str, str]:
    o = {"https://cs50.harvard.edu/x/weeks": lista()}
    for h in HETEK:
        o[f"https://cs50.harvard.edu/x/weeks/{h}"] = cs50_het(h)
    return o


SRT = ("1\n00:00:00,000 --> 00:00:03,500\n[MUSIC PLAYING]\n\n2\n00:00:17,850 --> 00:00:20,190\nDAVID J. MALAN: All right.\n"
       "This is CS50.\n\n3\n00:01:02,5 --> 00:01:04,000\n<i>Week one.</i>\n")


class ValasztasTeszt(unittest.TestCase):
    def setUp(self):
        self.b = dict(kozvetlen.ALAP)

    def test_a_cs50_heti_oldal_1080p_sdr_angol_felirattal_es_diakkal(self):
        k = kozvetlen.valaszt(cs50_het("1"), "https://cs50.harvard.edu/x/weeks/1/", self.b)
        self.assertEqual(k, {"video": f"{CDN}/1/lecture1-1080p.mp4", "minoseg": "1080p", "nyelv": "en", "alapnev": "lecture1",
                             "felirat": f"{CDN}/1/lang/en/lecture1.srt", "diak": f"{CDN}/1/lecture1.pdf"})

    def test_csak_hdr_1080p_mellett_a_720p_jon(self):
        k = kozvetlen.valaszt(cs50_het("2", minosegek=[("1080p", "-hdr"), ("720p", ""), ("4k", "")]), "https://x/", self.b)
        self.assertEqual(k["video"], f"{CDN}/2/lecture2-720p.mp4")
        self.assertEqual(k["minoseg"], "720p")

    def test_nincs_elfogadhato_valtozat_a_lejatszo_marad(self):
        self.assertIsNone(kozvetlen.valaszt(cs50_het("3", minosegek=[("360p", ""), ("1080p", "-hdr")]), "https://x/", self.b))
        self.assertIsNone(kozvetlen.valaszt('<a href="https://cdn/x.mp3">a</a><iframe src="https://video.cs50.io/abcdefghijk">',
                                            "https://x/", self.b))

    def test_a_szinkron_utak_kimaradnak_akkor_is_ha_csak_azok_vannak(self):
        html = cs50_het("4", minosegek=[])          # csak az `es/` szinkron marad
        self.assertIsNone(kozvetlen.valaszt(html, "https://x/", self.b))

    def test_csak_iso_nyelvkod_jelol_szinkront(self):
        html = '<html lang="en"><a href="https://cdn/l/ai/lectureai-1080p.mp4">v</a><a href="https://cdn/l/ai/lang/en/lectureai.srt">s</a></html>'
        k = kozvetlen.valaszt(html, "https://x/", self.b)
        self.assertEqual((k["video"], k["felirat"]), ("https://cdn/l/ai/lectureai-1080p.mp4", "https://cdn/l/ai/lang/en/lectureai.srt"))
        html = '<html lang="en"><a href="https://cdn/l/de/v-1080p.mp4">v</a></html>'
        self.assertIsNone(kozvetlen.valaszt(html, "https://x/", self.b))

    def test_a_beallitas_kikapcsolja_es_atallithato(self):
        self.assertIsNone(kozvetlen.valaszt(cs50_het("1"), "https://x/", dict(self.b, be=False)))
        k = kozvetlen.valaszt(cs50_het("1"), "https://x/", dict(self.b, minoseg=["720p"]))
        self.assertEqual(k["video"], f"{CDN}/1/lecture1-720p.mp4")
        k = kozvetlen.valaszt(cs50_het("1"), "https://x/", dict(self.b, kizar=[], minoseg=["4k"]))
        self.assertEqual(k["video"], f"{CDN}/1/lecture1-4k-hdr.mp4", "a HDR csak a kizárás miatt marad ki; oldalsorrendben az első")

    def test_lang_nelkuli_oldal_az_alap_nyelv_es_a_nyelvjelolt_felirat(self):
        k = kozvetlen.valaszt(cs50_het("5", lang=None), "https://x/", dict(self.b, alap_nyelv="en"))
        self.assertEqual((k["nyelv"], k["felirat"]), ("en", f"{CDN}/5/lang/en/lecture5.srt"))
        html = ('<html lang="hu"><a href="v/eloadas-1080p.mp4">v</a><a href="v/eloadas.hu.vtt">f</a><a href="v/eloadas.en.vtt">e</a>'
                '<a href="v/eloadas-720p.mp4">v2</a></html>')
        k = kozvetlen.valaszt(html, "https://pelda.hu/kurzus/1/", self.b)
        self.assertEqual(k["video"], "https://pelda.hu/kurzus/1/v/eloadas-1080p.mp4")
        self.assertEqual(k["felirat"], "https://pelda.hu/kurzus/1/v/eloadas.hu.vtt")
        self.assertIsNone(k["diak"])

    def test_a_beallitas_az_os_tomlbol(self):
        cfg = SimpleNamespace(section=lambda n: {"kozvetlen": {"minoseg": ["720P"], "kizar": []}})
        b = kozvetlen.beallitas(cfg)
        self.assertEqual((b["minoseg"], b["kizar"], b["kiterjesztes"]), (["720p"], [], [".mp4", ".mov", ".m4v"]))
        import tomllib
        valodi = tomllib.loads((REPO / "config" / "os.toml").read_text(encoding="utf-8"))["video"]["kozvetlen"]
        self.assertEqual(set(valodi), set(kozvetlen.ALAP), "az os.toml és az alapértékek kulcsai egyeznek")
        self.assertEqual(kozvetlen.beallitas(SimpleNamespace(section=lambda n: valodi and {"kozvetlen": valodi})), kozvetlen.ALAP)


class SrtVttTeszt(unittest.TestCase):
    def test_srt_vtt_a_lejatszo_elemzojevel(self):
        vtt = kozvetlen.srt_vtt(SRT, forras=f"{CDN}/1/lang/en/lecture1.srt")
        self.assertTrue(vtt.startswith("WEBVTT\n\nNOTE kiadói felirat: "))
        self.assertIn("00:00:17.850 --> 00:00:20.190", vtt)
        self.assertIn("00:01:02.500 --> 00:01:04.000", vtt)
        self.assertNotIn(atirat.GEPI_JEL, vtt[:600], "kiadói felirat (L44)")
        cuek = atirat.elemez(vtt)
        self.assertEqual([c["szoveg"] for c in cuek], ["[MUSIC PLAYING]", "DAVID J. MALAN: All right. This is CS50.", "Week one."])
        self.assertEqual(cuek[1]["k"], 17.85)

    def test_a_vtt_bemenet_megmarad(self):
        vtt = kozvetlen.srt_vtt("﻿WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nszia\n")
        self.assertEqual(atirat.elemez(vtt)[0]["szoveg"], "szia")


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
    def test_a_hetek_kozvetlen_fajlra_fordulnak_letoltes_nelkul(self):
        v = Valaszolo(kozvetlen_oldalak())
        naplo = []
        r = bejaras.felfedez(self.cfg, START, fetch=v, sleep=lambda s: None, log=naplo.append, mcfg=self.mcfg)
        tt = r["tetelek"]
        self.assertEqual(len(tt), 12)
        self.assertEqual([t["video"] for t in tt], [f"{CDN}/{h}/lecture{h}-1080p.mp4" for h in HETEK])
        self.assertTrue(all(t["forras"] == "kozvetlen" for t in tt))
        self.assertEqual(tt[1]["beagyazott"], f"https://www.youtube.com/watch?v={YT['1']}")
        self.assertEqual((tt[1]["felirat"], tt[1]["diak"], tt[1]["minoseg"], tt[1]["nyelv"]),
                         (f"{CDN}/1/lang/en/lecture1.srt", f"{CDN}/1/lecture1.pdf", "1080p", "en"))
        self.assertFalse([u for u in v.kerest if "cdn.cs50.net" in u], "a felfedezés a fájlokhoz nem nyúl (a diákhoz sem)")
        self.assertFalse(self.cfg.path("staging").exists())
        self.assertIn("közvetlen fájl (1080p, en; felirat)", "\n".join(naplo))
        ki = []
        bejaras.kiir(r, ki.append)
        self.assertIn("forrás: közvetlen fájl (1080p, en; felirat)", ki[1])
        self.assertIn(f"diák: {CDN}/1/lecture1.pdf (csak metaadat, nem töltődik le)", ki[2])

    def test_a_regi_beagyazott_oldal_valtozatlan(self):
        r = bejaras.felfedez(self.cfg, START, fetch=Valaszolo(cs50_oldalak()), sleep=lambda s: None, log=lambda s: None, mcfg=self.mcfg)
        self.assertTrue(all(t["forras"] == "beagyazott" and t["video"] == t["beagyazott"] for t in r["tetelek"]))
        self.assertNotIn("felirat", r["tetelek"][0])
        ki = []
        bejaras.kiir(r, ki.append)
        self.assertIn("forrás: beágyazott lejátszó", ki[1])

    def test_a_lejatszon_at_mar_letoltott_eloadas_megvan(self):
        r = bejaras.felfedez(self.cfg, START, fetch=Valaszolo(kozvetlen_oldalak()), sleep=lambda s: None, log=lambda s: None, mcfg=self.mcfg)
        yt0 = f"https://www.youtube.com/watch?v={YT['0']}"
        urlek, meglevo = bejaras.letoltendo(r, lambda u: u == yt0)
        self.assertEqual(meglevo, 1)
        self.assertEqual(urlek, [f"{CDN}/{h}/lecture{h}-1080p.mp4" for h in HETEK[1:]])
        urlek, meglevo = bejaras.letoltendo(r, lambda u: u == "https://cs50.harvard.edu/x/weeks/2")
        self.assertEqual(meglevo, 1, "az oldal (a közvetlen fájl forrás-linkje) szerint is")

    def test_a_vegpont_a_forrast_is_adja_es_a_mentett_lista_a_letoltesnek(self):
        r = bejaras.felfedez(self.cfg, START, fetch=Valaszolo(kozvetlen_oldalak()), sleep=lambda s: None, log=lambda s: None, mcfg=self.mcfg)
        bejaras.ment(self.cfg, r)
        d = video_api.bejaras(SimpleNamespace(cfg=self.cfg), START)
        self.assertEqual(d["tetelek"][1]["forras"], "kozvetlen")
        self.assertEqual(d["tetelek"][1]["diak"], f"{CDN}/1/lecture1.pdf")
        self.assertNotIn("tovabbi", d["tetelek"][1])
        kt = bejaras.kozvetlen_tetelek(self.cfg)
        self.assertEqual(set(kt), {f"{CDN}/{h}/lecture{h}-1080p.mp4" for h in HETEK})
        self.assertEqual(kt[f"{CDN}/3/lecture3-1080p.mp4"]["oldal"], "https://cs50.harvard.edu/x/weeks/3")
        self.assertTrue(str(videolanc.bejaras_fajl(self.cfg, START)).startswith(str(self.cfg.path("state"))))


class LetoltesTeszt(_Gyoker):
    """A jóváhagyott letöltés: a közvetlen fájl a szokásos `ingest_url` úton, az oldal forrás-linkjével és címével, őszinte User-Agenttel;
    utána a kiadói felirat `video.en.vtt`-ként a forrásmappába, belőle a kész `transcript.md` (modell nélkül)."""

    def setUp(self):
        super().setUp()
        pin_es_ffmpeg(self.cfg, self.root, valodi=FFMPEG if ffmpeg_elerheto() else None)
        p = mock.patch.dict(os.environ, {"MOS_FFMPEG": "/nincs/ilyen/ffmpeg"})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("MANIFOLD_STOP_FAJL", None)
        self.url = f"{CDN}/1/lecture1-1080p.mp4"
        self.tetel = {"oldal": "https://cs50.harvard.edu/x/weeks/1", "cim": "Week 1 C - CS50x 2026", "video": self.url,
                      "forras": "kozvetlen", "beagyazott": f"https://www.youtube.com/watch?v={YT['1']}", "minoseg": "1080p",
                      "nyelv": "en", "felirat": f"{CDN}/1/lang/en/lecture1.srt", "diak": f"{CDN}/1/lecture1.pdf"}
        self.kerest: list[str] = []

    def letolto(self):
        _, letolto, _ = msp()
        teszt = self
        inf = dict(info(video_id="lecture1-1080p", cim="lecture1-1080p", url=self.url), language=None, duration=None, uploader=None)

        class Hamis(letolto.Downloader):
            name = "hamis"
            uak: list = []

            @property
            def version(self):
                return "hamis-1.0"

            def probe(self, url, *, allow_playlist=False, flat=False, user_agent=None):
                self.uak.append(("probe", user_agent))
                teszt.assertEqual(url, teszt.url)
                return dict(inf)

            def download(self, request):
                self.uak.append(("download", request.user_agent))
                cel = Path(request.target_dir)
                cel.mkdir(parents=True, exist_ok=True)
                m = cel / f"{request.stem}.mp4"
                m.write_bytes(b"FAKEMEDIA")
                return letolto.DownloadResult(media_path=m, info=dict(inf, requested_downloads=[{"filepath": str(m)}]), subtitle_files=[])
        return Hamis()

    def fetch(self, url):
        from msp.crawl import Page
        self.kerest.append(url)
        return Page(url, 200, "application/x-subrip", SRT)

    def futtat(self, l, **kw):
        _, modul, _ = msp()
        ki = io.StringIO()
        with mock.patch.object(modul, "create_downloader", return_value=l), redirect_stdout(ki):
            rc = lanc.letoltes(self.cfg, [self.url], log=print, felirat_fetch=self.fetch, **kw)
        return rc, ki.getvalue()

    def test_kozvetlen_fajl_a_stagingbe_felirattal_es_atirattal(self):
        l = self.letolto()
        rc, ki = self.futtat(l, kozvetlen_tetelek={self.url: self.tetel})
        self.assertEqual(rc, 0, ki)
        self.assertEqual(l.uak, [("probe", self.mcfg.crawl.user_agent), ("download", self.mcfg.crawl.user_agent)])
        self.assertEqual(self.kerest, [self.tetel["felirat"]], "csak a felirat; a diák nem töltődik le")
        (integ,) = list(self.cfg.path("staging").rglob("integration.json"))
        mappa = integ.parent
        self.assertEqual(mappa.name, "Week 1 C - CS50x 2026")
        self.assertEqual(mappa.parent.parent.name, "CS50", "a szolgáltató az oldal gazdagépe (config.yaml provider_names)")
        src = staging.olvas(mappa)
        self.assertEqual(src["source"]["url"], "https://cs50.harvard.edu/x/weeks/1")
        self.assertEqual(src["source"]["title"], "Week 1 C - CS50x 2026")
        self.assertEqual(src["source"]["media_url"], self.url)
        self.assertEqual(src["source"]["language"], "en")
        self.assertTrue(src["video_id"].startswith("u"), "a fájlnév nem azonosító: az URL hash-e")
        self.assertEqual(src["meta"]["url"], "https://cs50.harvard.edu/x/weeks/1")
        self.assertTrue((mappa / "video.en.vtt").is_file())
        self.assertTrue(src["atirat_kesz"])
        self.assertEqual(src["atirat"]["transcript_engine"], "subtitles:video.en.vtt")
        self.assertEqual(src["felirat"], str(mappa / "video.en.vtt"))
        self.assertIn("This is CS50.", src["atirat_torzs"])
        self.assertEqual(json.loads(integ.read_text(encoding="utf-8"))["transcript_status"], "completed")
        megvan = bejaras.megvan_fuggveny(lanc.msp_konfig(self.cfg))
        self.assertTrue(bejaras.tetel_megvan(self.tetel, megvan), "a következő bejárás megvannak látja (az oldal szerint)")
        self.assertFalse(megvan(self.url))

        # újrafuttatva: már megvan, nem tölt le, a feliratot nem kéri újra
        l2 = self.letolto()
        rc, ki = self.futtat(l2, kozvetlen_tetelek={self.url: self.tetel})
        self.assertEqual(rc, 0, ki)
        self.assertIn("Már megvan", ki)
        self.assertEqual([x for x in l2.uak if x[0] == "download"], [])
        self.assertEqual(len(self.kerest), 1)

    def test_a_felirat_hibaja_nem_hibaztatja_a_letoltest_es_kesobb_potolhato(self):
        from msp.crawl import Page

        def rossz(url):
            return Page(url, 404)
        _, modul, _ = msp()
        ki = io.StringIO()
        with mock.patch.object(modul, "create_downloader", return_value=self.letolto()), redirect_stdout(ki):
            rc = lanc.letoltes(self.cfg, [self.url], log=print, kozvetlen_tetelek={self.url: self.tetel}, felirat_fetch=rossz)
        self.assertEqual(rc, 0, ki.getvalue())
        self.assertIn("a felirat nem tölthető le", ki.getvalue())
        (integ,) = list(self.cfg.path("staging").rglob("integration.json"))
        self.assertFalse(staging.olvas(integ.parent)["atirat_kesz"])
        rc, _ = self.futtat(self.letolto(), kozvetlen_tetelek={self.url: self.tetel})
        self.assertEqual(rc, 0)
        self.assertTrue(staging.olvas(integ.parent)["atirat_kesz"], "a már meglévő videóhoz a felirat pótlódik")

    def test_a_mentett_bejarasbol_veszi_a_kontextust(self):
        bejaras.ment(self.cfg, {"start": START, "tetelek": [self.tetel]})
        rc, ki = self.futtat(self.letolto())
        self.assertEqual(rc, 0, ki)
        self.assertIn("közvetlen fájl: Week 1 C - CS50x 2026", ki)
        (integ,) = list(self.cfg.path("staging").rglob("integration.json"))
        self.assertEqual(integ.parent.name, "Week 1 C - CS50x 2026")

    def test_ket_kurzus_azonos_fajlneve_nem_utkozik(self):
        self.futtat(self.letolto(), kozvetlen_tetelek={self.url: self.tetel})
        masik_url = "https://cdn.cs50.net/python/2022/spring/lectures/1/lecture1-1080p.mp4"
        masik = dict(self.tetel, oldal="https://cs50.harvard.edu/python/weeks/1", cim="Lecture 1 - CS50P", video=masik_url)
        self.url = masik_url
        rc, ki = self.futtat(self.letolto(), kozvetlen_tetelek={masik_url: masik})
        self.assertEqual(rc, 0, ki)
        self.assertNotIn("Már megvan", ki)
        self.assertEqual(len(list(self.cfg.path("staging").rglob("integration.json"))), 2)


class IntegralasFeliratTeszt(unittest.TestCase):
    """A vault oldala: a kiadói felirat szó szerint, „kiadói” jelöléssel kerül a `<törzs>.<nyelv>.vtt`-be (nem a kerekített átirat)."""

    def test_a_szovegreteg_a_kiadoi_feliratot_veszi(self):
        from modulok.ytdlp import integralas
        t = tmpdir()
        self.addCleanup(t.cleanup)
        vtt_ut = Path(t.name) / "video.en.vtt"
        vtt_ut.write_text(kozvetlen.srt_vtt(SRT), encoding="utf-8")
        tetel = integralas.Tetel(mappa=t.name)
        src = {"atirat": {"language": "en", "transcript_engine": "subtitles:video.en.vtt"}, "atirat_kesz": True, "felirat": str(vtt_ut)}
        vtt, nyelv, info_ = integralas.Integralas._szovegreteg(SimpleNamespace(), tetel, src, "Week 1.mp4", 7000.0)
        self.assertEqual((vtt, nyelv, info_), (vtt_ut.read_text(encoding="utf-8"), "en", None))
        self.assertEqual(tetel.lepesek["szovegreteg"]["osztaly"], "kiadói")


if __name__ == "__main__":
    unittest.main()
