"""C20b: a médiatársítás tiszta függvényei — a legacy `media_selftest` nem portolt esetei (1–5, 4b–4e, 14–16, 24, 31) a 2.0 moduljain.

    szovegreteg   (vaultlib): cue-k a görgő-dedupplal, ablak, horgonyok, lapos frontmatter
    egyezes       (media_match): évszámok (4c), kronológia, méret-torzítás (4b), cím-téma (4e)
    kotes         (media_link, 4d): saját téma, a verifikátor sorrendje, az elvetés ±30 s, a meglévő horgony ±20 s, a tárgy-kapu
    itelet        (media.py nyelv 1–5; media_itelet 31a–e): felirat, nyelvkód, nyelvi döntés, sorszám, igen/nem, útvonal, tömörítés,
                  téma-sáv, kötés-sáv; és a D1 végső témadöntése (a legacy `dontesre_var` helyett)
    horgony       (add_media_anchors, 14–16): beírás a Source végére, idempotens, inline és szokatlan mező visszautasítva
    vaultoldal    (media_staging 24): a staging-átirat VTT-je (a +1 s szabály), info.json, a forrásleíró jegyzet

Nem portolt, indokolt: 6 (`download_args`: a letöltés a C20a `msp`-je), 7–10, 30 (a duplikátum és az elhelyezés a C20a
`elhelyezes.terv`-e + a lánc tesztje), 11, 17–19, 25 (a „kérdezz rá” és az olvasási mandátum a D1-gyel megszűnt: `test_video_integralas`),
12 (a futás-zár: a feladatsor egy vault-író feladatot futtat egyszerre, 27(b)), 20, 21, 23 (az `mfd.py` G4-verifikáció és az AI02-napló a
2.0-ban a gépi írás kapuja és a riport), 22 (az alkalmazásmappa a `[utak]`-ból), 31f–i (a helyi modell sávjait a router kalibrációja
váltja), 32 (`staging.keres_azonosito`: a C20a tesztje)."""
import json
import unittest
from unittest import mock

from modulok.ytdlp import egyezes as X
from modulok.ytdlp import horgony, itelet, kotes as KT, vaultoldal as VO
from modulok.ytdlp import szovegreteg as SZ


def _vtt(*cuek) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{i}\n00:00:{a:06.3f} --> 00:00:{b:06.3f}\n{t}\n" for i, (a, b, t) in enumerate(cuek, 1))


class SzovegretegTest(unittest.TestCase):
    def test_cuek_tag_es_gorgo_dedup(self):
        nyers = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<c>első</c> sor\n\n2\n00:00:03.000 --> 00:00:05.000\nelső sor\nmásodik sor\n\n"
                 "3\n00:00:05,000 --> 00:00:07,500\n12\nharmadik\n")
        self.assertEqual(SZ.cuek(nyers), ((1.0, 3.0, "első sor"), (3.0, 5.0, "második sor"), (5.0, 7.5, "harmadik")))

    def test_ablak_szoveg(self):
        c = ((0.0, 10.0, "a"), (30.0, 40.0, "b"), (70.0, 80.0, "c"), (120.0, 130.0, "d"))
        self.assertEqual(SZ.ablak_szoveg(c), "a b c d")
        self.assertEqual(SZ.ablak_szoveg(c, 50), "b c")          # [30, 90]: a vég ≥ 30 és a kezdet ≤ 90

    def test_horgonyok_es_frontmatter(self):
        fm, torzs = SZ.split_note('---\nTags:\n  - History\nSource:\n  - "[[A.pdf#page=3]]"\n  - "[[Videó.mp4#t=125]]"\n---\n# X\n')
        d, sorrend = SZ.parse_fm(fm)
        self.assertEqual(sorrend, ["Tags", "Source"])
        self.assertEqual(SZ.media_anchors(d["Source"]), [("Videó.mp4", 125)])
        self.assertEqual(torzs, "# X\n")

    def test_szavak_es_szotovek(self):
        self.assertEqual(SZ.longwords("A reformkori országgyűlés, 1848-ban!"), {"reformkori", "országgyűlés"})
        self.assertEqual(SZ.stem_list("országgyűlés reformkori ló"), ["országg", "reformk"])
        self.assertEqual(SZ.mask_code("a `kód` b"), "a " + " " * 5 + " b")


class EgyezesTest(unittest.TestCase):
    def test_4c_evszamok(self):
        self.assertEqual(sorted(X.evszamok("1848-ban kitört; Kr. e. 490-ben Marathón; a XIX. század eleje; a 18. század; ezerkilencszáz")),
                         sorted([1848, -490, 1850, 1750]))

    def test_4c_kronologia(self):
        tv = {"T15 - Reformkor": [1830, 1840, 1848] * 3, "T13 - Felvilágosodás": [1760, 1770, 1780] * 3}
        rang = [("T13 - Felvilágosodás", 0.3), ("T15 - Reformkor", 0.2)]
        kj = X.kron_jel([1840, 1848, 1847], rang, list(tv), tv)
        self.assertEqual((kj["merheto"], kj["egyezik"]), (True, True))           # a top-3-ban mindkettő (k = 3)
        self.assertEqual(kj["kombinalt"], "T13 - Felvilágosodás")
        self.assertEqual(X.kron_jel([1848], rang, list(tv), tv)["merheto"], False)   # < 3 évszám: nem mérhető

    def test_4e_cim_tema(self):
        temak = ["I24 - Ady Endre", "I09 - Felvilágosodás a magyar irodalomban", "I08 - Felvilágosodás", "T05 - Ady Endre"]
        self.assertEqual(X.cim_tema("Ady Endre szerelmi költészete", temak, "I"), "I24 - Ady Endre")
        self.assertEqual(X.cim_tema("Felvilágosodás a magyar irodalomban", temak), "I09 - Felvilágosodás a magyar irodalomban")
        self.assertIsNone(X.cim_tema("Adyendre", temak))
        self.assertIsNone(X.cim_tema("Ady Endre és a felvilágosodás", temak))             # két független találat
        self.assertEqual(X.cim_tema("Ady Endre", ["T05 - Ady Endre", "I24 - Ady Endre"], "T"), "T05 - Ady Endre")

    def test_4b_meret_torzitas_a_lift_javitja(self):
        """A nagy témának több szava van: a nyers lefedettség őt választja, a lift a ténylegesen illeszkedő kicsit."""
        kozos = "általános szövegrész " * 3

        def szo(i):                                     # 400 különböző 7 betűs szótő
            return "".join("abcdefghijklmnopqrstuvwxyz"[(i // 26 ** k) % 26] for k in range(3)) + "szóalakok"

        jegyzetek = {"T01 - Nagy/Elmélet/a.md": "# a\n" + kozos + " ".join(szo(i) for i in range(400)),
                     "T02 - Kicsi/Elmélet/b.md": "# b\n" + kozos + "különleges kifejezés ritkaszavak sajátossága"}
        for i in range(8):
            jegyzetek[f"T{10 + i:02d} - Csali{i}/Elmélet/c.md"] = "# c\n" + kozos + f" csalitéma{i}szöveg"
        idx = X.NoteIndex("/nincs", jegyzetek=jegyzetek)
        szoveg = "különleges kifejezés ritkaszavak sajátossága " + " ".join(szo(i) for i in range(6))
        nyers = X.rank_text(szoveg, idx, nyers=True)
        lift = X.rank_text(szoveg, idx)
        self.assertEqual(nyers[0][0], "T01 - Nagy")
        self.assertEqual(lift[0][0], "T02 - Kicsi")
        self.assertGreater(lift[0][1] - lift[1][1], 0)

    def test_nyelv_es_ures_szoveg(self):
        idx = X.NoteIndex("/nincs", jegyzetek={"T01 - A/Elmélet/a.md": "# a\nreformkori országgyűlés jobbágyfelszabadítás"})
        cls = X.classify(X.Forras("x.mp4"), idx, "hu")
        self.assertFalse(cls["auto"])
        self.assertIn("nem mért", cls["okok"][0])


class KotesTest(unittest.TestCase):
    def korpusz(self, media=()):
        jegyzetek = {"T05 - A/Elmélet/a.md": "---\nSource:\n" + "".join(f'  - "[[{f}#t={t}]]"\n' for f, t in media) + "---\n# a\nszöveg",
                     "T05 - A/Elmélet/c.md": "# c\nszöveg", "T05 - A/Elmélet/d.md": "# d\nszöveg", "T06 - B/Elmélet/b.md": "# b\nszöveg"}
        return KT.Korpusz(X.NoteIndex("/nincs", jegyzetek=jegyzetek))

    def futtat(self, jeloltek, korp, **kw):
        wins = [{"t": t, "sw": set(), "years": set(), "cues": []} for t in range(0, 400, 10)]
        with mock.patch.object(KT, "jeloltek", lambda f, k, w, b: jeloltek), \
                mock.patch.object(KT, "pontszam", lambda f, m: f["p"]), mock.patch.object(KT, "vegso_t", lambda n, w, k: w["t"]):
            return KT.kotes(X.Forras("V.mp4"), korp, kw.pop("tema", "T05 - A"), m={}, wins=wins, **kw)

    def jelolt(self, rp, t, p):
        return {"jegyzet": rp, "t": t, "wi": t // 10, "rang": 1, "jegyek": {"p": p}}

    def test_4d_sav_sajat_tema_elvetes_meglevo(self):
        korp = self.korpusz(media=[("V.mp4", 300)])
        j = [self.jelolt("T05 - A/Elmélet/a.md", 100, 0.97), self.jelolt("T06 - B/Elmélet/b.md", 100, 0.95),
             self.jelolt("T05 - A/Elmélet/c.md", 200, 0.96), self.jelolt("T05 - A/Elmélet/a.md", 310, 0.95),
             self.jelolt("T05 - A/Elmélet/d.md", 50, 0.80), self.jelolt("T05 - A/Elmélet/d.md", 150, 0.70)]
        r = self.futtat(j, korp, elvet={("T05 - A/Elmélet/c.md", "V.mp4"): [180]})
        self.assertEqual([(x["jegyzet"], x["t"]) for x in r["auto"]], [("T05 - A/Elmélet/a.md", 100)])
        self.assertEqual({(x["jegyzet"], x["t"]) for x in r["javaslat"]},
                         {("T06 - B/Elmélet/b.md", 100), ("T05 - A/Elmélet/d.md", 50)})   # más téma; saját téma a sáv alatt
        self.assertTrue(KT.indok({**r["auto"][0], "bizonyitek": {"ritka_kozos": ["x"], "evszam_kozos": [1848]}})
                        .startswith("media_link verifikátor p="))

    def test_4d_targy_kapu_es_kuszob(self):
        korp = self.korpusz()
        j = [self.jelolt("T05 - A/Elmélet/a.md", 100, 0.95)]
        self.assertEqual(len(self.futtat(j, korp, kalibralt=False)["auto"]), 0)
        self.assertTrue(KT.targy_kalibralt("N01 - X") and KT.targy_kalibralt("T05 - A") and not KT.targy_kalibralt("M01 - X"))
        r = self.futtat([self.jelolt("T05 - A/Elmélet/a.md", 100, 0.95)], korp, tema="T05 - A")
        self.assertEqual(len(r["auto"]), 1)

    def test_pontszam_sorrend_a_valodi_modellel(self):
        m = KT.modell()
        jo = {"B": 0.35, "C": 0.25, "rang_log": 0.0, "res": 0.2, "ritka": 5, "cim": 0.8, "felkov": 0.3, "ev_plusz": 2, "ev_minusz": 0,
              "passz": 0.6}
        rossz = {"B": 0.15, "C": 0.0, "rang_log": 3.0, "res": -0.2, "ritka": 0, "cim": 0.0, "felkov": 0.0, "ev_plusz": 0, "ev_minusz": 4,
                 "passz": 0.1}
        kozep = {k: (jo[k] + rossz[k]) / 2 for k in jo}
        self.assertGreater(KT.pontszam(jo, m), KT.pontszam(kozep, m))
        self.assertGreater(KT.pontszam(kozep, m), KT.pontszam(rossz, m))
        self.assertEqual(set(m["w"]), set(KT.FEATURES))

    def test_vegso_t_a_legtobb_ritka_szotonel(self):
        korp = KT.Korpusz(X.NoteIndex("/nincs", jegyzetek={
            "T05 - A/Elmélet/a.md": "# a\n\nSzéchenyi István Hitel munkája megjelent reformkori programként, a Lánchíd építése",
            "T06 - B/Elmélet/b.md": "# b\n\nmás tartalom, más szavakkal: általános bevezetés"}))
        w = {"t": 100, "sw": {"széchen", "lánchíd"}, "cues": [(90.0, "általános bevezetés semmiről"),
                                                             (104.0, "Széchenyi István Lánchíd építése"), (120.0, "Széchenyi")]}
        self.assertEqual(KT.vegso_t(korp.idx.notes["T05 - A/Elmélet/a.md"], w, korp), 104)

    def test_elvetettek_jsonl(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"jegyzet": "T/a.md", "media": "V.mp4", "t": 30}) + "\nrossz sor\n")
        self.assertEqual(dict(KT.elvetettek(f.name)), {("T/a.md", "V.mp4"): [30]})
        self.assertEqual(dict(KT.elvetettek(None)), {})


class ItelerTest(unittest.TestCase):
    META = {"language": "en", "subtitles": {k: [] for k in ("en", "en-GB", "fr", "hu", "live_chat")}}

    def test_1_3_felirat_valasztas(self):
        self.assertEqual(itelet.felirat_valasztas(self.META)[0], "en")
        self.assertIsNone(itelet.felirat_valasztas({"language": "en", "subtitles": {}})[0])        # a gépi sáv soha
        self.assertEqual(itelet.felirat_valasztas(self.META, "hu")[0], "hu")                        # a hang dönt
        self.assertIsNone(itelet.felirat_valasztas({"subtitles": {"en": []}})[0])                   # ismeretlen nyelv
        self.assertEqual(itelet.felirat_valasztas({"language": "en", "subtitles": {"en-GB": [], "fr": []}})[0], "en-GB")

    def test_4_norm_lang(self):
        self.assertEqual([itelet.norm_lang(x) for x in ("en-GB", "hu-orig", "iw", "pt_BR", "", None)], ["en", "hu", "he", "pt", None, None])

    def test_5_nyelv_dontes(self):
        d = {"nyelv": "en", "egyhangu": True, "p_min": 0.99}
        r = itelet.nyelv_dontes("en", d)
        self.assertEqual((r["nyelv"], r["blokkol"], r["jelzes"], r["kod"]), ("en", False, False, "metaadat+hang"))
        self.assertEqual(itelet.nyelv_dontes(None, d)["kod"], "hang")
        self.assertTrue(itelet.nyelv_dontes("hu", d)["jelzes"])
        self.assertTrue(itelet.nyelv_dontes("en", {**d, "egyhangu": False})["blokkol"])
        self.assertTrue(itelet.nyelv_dontes("en", {**d, "p_min": 0.4})["blokkol"])
        self.assertTrue(itelet.nyelv_dontes("en", None)["blokkol"])

    def test_31a_31b_31c(self):
        self.assertEqual((itelet.sorszam("3", 5), itelet.sorszam("A válasz: 12.", 5), itelet.sorszam("egyik sem", 5),
                          itelet.sorszam("2. Antikvitás", 5)), (3, None, None, 2))
        self.assertEqual((itelet.igen_nem("Igen, mert"), itelet.igen_nem("- nem"), itelet.igen_nem("talán")), (True, False, None))
        self.assertEqual(itelet.utvonal("https://zanza.tv/irodalom/romantika/e-t-hoffmann"), "irodalom / romantika / e-t-hoffmann")
        self.assertEqual(itelet.utvonal("https://www.youtube.com/watch?v=x"), "")
        self.assertEqual(itelet.tomorit("Antikvitás", ["Az antikvitás irodalma", "Vergilius", "Vergilius"]), "irodalma; Vergilius")
        self.assertEqual(itelet.rovid("egy kettő három négy", 10), "egy kettő …")

    def test_31d_tema_dontes(self):
        rang = [(f"I{i:02d} - T{i}", 1.0 / i) for i in range(1, 15)]
        ok = itelet.tema_dontes({"tartalom": "I03 - T3", "metaadat": "I03 - T3"}, rang)
        self.assertTrue(ok["auto"])
        el = itelet.tema_dontes({"tartalom": "I03 - T3", "metaadat": "I04 - T4"}, rang)
        self.assertFalse(el["auto"])
        self.assertEqual(el["javaslat"][:2], ["I03 - T3", "I04 - T4"])
        lex = itelet.tema_dontes({"tartalom": "I12 - T12", "metaadat": "I12 - T12"}, rang)
        self.assertFalse(lex["auto"])                                                                # a lexikai kapu (top-10)
        self.assertTrue(itelet.tema_dontes({"tartalom": "I12 - T12", "metaadat": "I12 - T12"}, rang, "I12 - T12")["auto"])
        self.assertFalse(itelet.tema_dontes({"tartalom": None, "metaadat": "I03 - T3"}, rang)["auto"])

    def test_31e_kotes_dontes(self):
        self.assertTrue(itelet.kotes_dontes(0.80, True, "T", True))
        for args in ((0.80, True, "T", False), (0.80, True, "T", None), (0.70, True, "T", True), (0.80, False, "T", True),
                     (0.80, True, "N", True), (0.95, True, "M", True)):
            self.assertFalse(itelet.kotes_dontes(*args), args)
        self.assertTrue(itelet.kotes_dontes(0.92, True, "N", True))

    def test_d1_tema_vegso(self):
        """D1: a legacy „döntésre vár” helyett minden ág végső döntést ad (vagy `None`, ha jelölt sincs)."""
        cls = {"auto": True, "tema": "T05 - A", "auto_jel": "három jel"}
        self.assertEqual(itelet.tema_vegso(cls, None, "T")["biztossag"], "biztos")
        d = {"auto": True, "tema": "I03 - X", "A": "I03 - X", "B": "I03 - X", "jel": "j", "okok": []}
        self.assertEqual(itelet.tema_vegso({"auto": False}, d, "I")["forras"], "modell")
        self.assertEqual(itelet.tema_vegso({"auto": False}, d, "T")["biztossag"], "valoszinu")        # T: a sáv nincs mérve
        self.assertEqual(itelet.tema_vegso({"auto": False, "cim_tema": "I24 - Ady"}, None, "I")["tema"], "I24 - Ady")
        r = itelet.tema_vegso({"auto": False, "kronologia": {"kombinalt": "T15 - R"}, "top3": [{"tema": "T13 - F"}]}, None, "T")
        self.assertEqual((r["tema"], r["biztossag"]), ("T15 - R", "bizonytalan"))
        self.assertEqual(itelet.tema_vegso({"auto": False, "top3": [{"tema": "T13 - F"}]}, None, "T")["tema"], "T13 - F")
        self.assertIsNone(itelet.tema_vegso({"auto": False, "top3": []}, None, "T")["tema"])

    def test_promptok_a_legacy_szovegei(self):
        pa, pb = itelet.tema_promptok("átirat", "Cím", "https://zanza.tv/a/b", "1. X: y")
        self.assertTrue(pa.startswith("Egy magyar oktatóvideó gépi átirata következik") and "ÁTIRAT:\nátirat" in pa)
        self.assertIn("A KIADÓ BESOROLÁSA (a weblap útvonala): a / b\n", pb)
        self.assertIsNone(itelet.tema_promptok("", "Cím", None, "1. X")[0])
        self.assertIn("JEGYZET: —\n", itelet.kotes_prompt("ablak", None, "részlet"))


SRC_FM = '---\nTags:\n  - History\nSource:\n  - "[[Könyv.pdf#page=12]]"\nStatus:\nNN:\nCanvas:\n---\n# Cím\n\ntörzs\n'


class HorgonyTest(unittest.TestCase):
    def test_14_beiras_a_source_vegere_es_idempotens(self):
        uj, r = horgony.beir(SRC_FM, [("Videó.mp4", 125)])
        self.assertEqual(uj, SRC_FM.replace('page=12]]"\n', 'page=12]]"\n  - "[[Videó.mp4#t=125]]"\n'))
        self.assertEqual(r, [("Videó.mp4", 125, "irva")])
        uj2, r2 = horgony.beir(uj, [("Videó.mp4", 125)])
        self.assertEqual((uj2, r2[0][2]), (uj, "mar_megvolt"))

    def test_15_16_visszautasit(self):
        for szoveg in ('---\nSource: "[[a.pdf]]"\n---\n', "nincs frontmatter", '---\nSource:\n  - [[a.pdf]]\n---\n',
                       '---\nSource:\n  - "[[a.pdf]]"\nszabad sor\n---\n', '---\nSource:\nSource:\n---\n'):
            with self.subTest(s=szoveg[:30]), self.assertRaises(horgony.HorgonyHiba):
                horgony.beir(szoveg, [("V.mp4", 1)])

    def test_ures_source_lista(self):
        uj, _ = horgony.beir("---\nTags:\nSource:\nStatus:\n---\nx\n", [("V.mp4", 3), ("V.mp4", 70)])
        self.assertEqual(uj, '---\nTags:\nSource:\n  - "[[V.mp4#t=3]]"\n  - "[[V.mp4#t=70]]"\nStatus:\n---\nx\n')


def staging_src(atirat_torzs="[00:00:01]\nelső mondat\n\n[00:00:30]\nmásodik\n\n[00:00:30]\nharmadik\n\n[00:01:10]\nnegyedik\n",
                hossz=100) -> dict:
    return {"mappa": "/s/Zanza/Irodalom/A cím", "video_id": "vid24", "cim": "A cím", "lap": "https://zanza.tv/irodalom/x/a-cim",
            "meta": {"id": "vid24", "title": "A cím", "duration": hossz, "resolution": "1440x1080", "uploader": "zanza tv",
                     "upload_date": "20200423", "webpage_url": "https://www.youtube.com/watch?v=vid24", "extractor": "Youtube",
                     "vcodec": "avc1.640028", "acodec": "mp4a.40.2",
                     "pipeline": {"downloaded_at": "2026-09-18T23:32:16+00:00", "format_selector": "best", "ffmpeg_used": True}},
            "source": {"source_id": "zanza-vid24"}, "integration": {"source_id": "zanza-vid24"},
            "atirat": {"transcript_engine": "faster-whisper:large-v3-turbo", "transcript_model": "large-v3-turbo",
                       "transcript_generated_at": "2026-09-18T23:34:00+00:00", "language": "hu", "transcript_status": "completed"},
            "atirat_torzs": atirat_torzs, "atirat_kesz": True}


class VaultoldalTest(unittest.TestCase):
    def test_24_staging_vtt_konvencio(self):
        vtt = VO.vtt_stagingbol(staging_src(), "hu")
        self.assertIn("NOTE manifold-asr\nmotor: faster-whisper\nmodell: large-v3-turbo\nnyelv: hu\n", vtt)
        sorok = [s for s in vtt.splitlines() if "-->" in s]
        self.assertEqual(sorok, ["00:00:01.000 --> 00:00:30.000", "00:00:30.000 --> 00:00:31.000",    # azonos kezdet: +1 s
                                 "00:00:30.000 --> 00:01:10.000", "00:01:10.000 --> 00:01:40.000"])  # az utolsó: a forrás hossza
        self.assertEqual(VO.felirat_sor("A cím.hu.vtt", vtt), ("hu", "A cím.hu.vtt", 4, "gépi"))
        with self.assertRaises(VO.VaultoldalHiba):
            VO.vtt_stagingbol(staging_src(atirat_torzs="nincs időbélyeg"), "hu")

    def test_24_info_json(self):
        i = VO.info_json(staging_src())
        self.assertEqual((i["id"], i["width"], i["height"], i["epoch"], i["_staging"]["zanza_lap"]),
                         ("vid24", 1440, 1080, 1789774336, "https://zanza.tv/irodalom/x/a-cim"))
        self.assertFalse(VO.info_json_szoveg(staging_src()).endswith("\n"))

    def test_forrasjegyzet_szovegreteg_nelkul_es_sentinel(self):
        j = VO.forrasjegyzet("A cím.mp4", cimke="Literature", info=VO.info_json(staging_src()), hossz=95.4, meret=62097724,
                             feliratok=[], info_nev="A cím.info.json")
        self.assertTrue(j.startswith('---\nTags:\n  - Literature\nSource:\n  - "[[A cím.mp4#t=0]]"\nStatus:\nNN:\nCanvas:\n---\n\n# A cím\n'))
        self.assertIn("| Hossz | 1:35 |", j)
        self.assertIn("| Fájl | [[A cím.mp4]] · 59,2 MB |", j)
        self.assertIn("**Nincs szövegréteg.**", j)
        self.assertFalse(VO.idegen_jegyzet(j))
        self.assertTrue(VO.idegen_jegyzet("# kézzel írt"))

    def test_forrasjegyzet_kozvetlen_fajl(self):
        # 84(e): a közvetlen kiadói fájl forrása az oldal; a hiányzó kodek nem „None” szöveg
        info = {"url": "https://cs50.harvard.edu/x/weeks/1", "webpage_url": "https://cdn.cs50.net/x/lecture1-1080p.mp4",
                "vcodec": None, "acodec": None}
        j = VO.forrasjegyzet("W1.mp4", cimke="Informatics", info=info, hossz=60.0, meret=1, feliratok=[], info_nev=None)
        self.assertIn("| Forrás | https://cs50.harvard.edu/x/weeks/1 |", j)
        self.assertIn("| Felbontás | — |", j)
        yt = VO.forrasjegyzet("Y.mp4", cimke=None, info={"url": "x", "webpage_url": "https://www.youtube.com/watch?v=a"},
                              hossz=1.0, meret=1, feliratok=[], info_nev=None)
        self.assertIn("| Forrás | https://www.youtube.com/watch?v=a |", yt)
        src = staging_src()
        src["meta"] = dict(src["meta"], url="https://cs50.harvard.edu/x/weeks/1",
                           webpage_url="https://cdn.cs50.net/x/lecture1-1080p.mp4")
        info2 = VO.info_json(src)
        self.assertEqual(info2["url"], "https://cs50.harvard.edu/x/weeks/1")
        self.assertNotIn("url", VO.info_json(staging_src()))
        j2 = VO.forrasjegyzet("W1.mp4", cimke=None, info=info2, hossz=1.0, meret=1, feliratok=[], info_nev=None)
        self.assertIn("| Forrás | https://cs50.harvard.edu/x/weeks/1 |", j2)

    def test_atirat_vtt_es_minoseg(self):
        a = {"szegmensek": [{"start": 0.0, "end": 4.5, "text": " Szia "}, {"start": 4.5, "end": 9.0, "text": "Hogy vagy"},
                            {"start": 9.0, "end": 10.0, "text": ""}]}
        vtt = VO.vtt_atiratbol(a, "hu", modell="mlx-community/whisper-large-v3-turbo", nyelv_forras="hang", keszult="2026-10-08")
        self.assertIn("motor: mlx-whisper\nmodell: mlx-community/whisper-large-v3-turbo\nnyelv: hu\nnyelv_forras: hang\nkeszult: 2026-10-08", vtt)
        self.assertEqual(len(SZ.cuek(vtt)), 2)
        hurok = [{"start": 0.0, "end": 4.5, "text": "Szia"}, {"start": 4.5, "end": 9.0, "text": "Szia"}, {"start": 9.0, "end": 10.0, "text": "x"}]
        self.assertEqual(VO.minoseg(hurok, 20.0), (0.275, 0.667))     # a hurok második „Szia”-ja nem fed: (4,5 + 1) s / 20 s
        self.assertEqual(VO.fedettseg(_vtt((0, 5, "a"), (4, 10, "b")), 20.0), 0.5)


class EvalTest(unittest.TestCase):
    """C20b: a `tema` és a `kotes` aranyhalmaz (a legacy olvasott címkéi) — a mérés az éles lánc promptját küldi."""

    def setUp(self):
        from tests.eval_segedek import eval_cfg, feladat
        from tests.helpers import tmpdir
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = eval_cfg(self._t.name)
        self.tema, self.kotes = feladat(self.cfg, "tema"), feladat(self.cfg, "kotes")

    def test_halmazok(self):
        self.assertEqual(len(self.tema.ARANY["videok"]), 118)
        self.assertEqual(sum(v["tema"] is None for v in self.tema.ARANY["videok"]), 3)                # 3 témátlan (bibliai)
        self.assertEqual(itelet.lista_hash(self.tema.ARANY["temak"]["I"]), "0623a5ee67")              # a legacy mérés listája
        self.assertEqual((len(self.kotes.ARANY["parok"]), sum(p["y"] for p in self.kotes.ARANY["parok"])), (141, 118))

    def test_kotes_tetelek_es_pontozo(self):
        from tests.eval_segedek import rekord
        t = list(self.kotes.tetelek(self.cfg))
        p0 = self.kotes.ARANY["parok"][0]
        self.assertEqual(t[0]["keres"]["messages"][0]["content"], itelet.kotes_prompt(p0["ablak_szoveg"], p0["jegyzet_cim"], p0["jegyzet_reszlet"]))
        jo = [rekord(x, "igen" if x["vart"]["y"] else "nem") for x in t]
        e = self.kotes.pontoz(jo)
        self.assertEqual(e["pontszam"], 1.0)
        self.assertEqual(e["lanc"]["pontossag"], 1.0)
        self.assertLess(self.kotes.pontoz([rekord(x, "igen") for x in t])["pontszam"], 0.9)
        self.assertFalse(self.kotes.formatum_ok("talán", {}))

    def test_tema_pontozo(self):
        temak = ["I01 - A", "I02 - B", "I03 - C"]
        v = {"temak": temak, "tema": "I02 - B", "elfogadhato": ["I02 - B", "I03 - C"], "video": "v1", "lex_rang_top10": temak,
             "cim_tema": None}
        rek = [{"id": "v1#tartalom", "vart": {**v, "fajta": "tartalom"}, "valasz": "2"},
               {"id": "v1#metaadat", "vart": {**v, "fajta": "metaadat"}, "valasz": "2."},
               {"id": "v2#tartalom", "vart": {**v, "video": "v2", "fajta": "tartalom"}, "valasz": "3"},
               {"id": "v2#metaadat", "vart": {**v, "video": "v2", "fajta": "metaadat"}, "valasz": "egyik sem"}]
        e = self.tema.pontoz(rek)
        self.assertEqual((e["szigoru"], e["megengedo"]), (0.5, 0.75))
        self.assertEqual((e["lanc"]["auto"], e["lanc"]["auto_szigoru"]), (1, 1.0))
        biblia = {**v, "tema": None, "elfogadhato": [], "fajta": "tartalom"}
        self.assertEqual(self.tema.pontoz([{"id": "b#tartalom", "vart": biblia, "valasz": "egyik sem"}])["szigoru"], 1.0)


if __name__ == "__main__":
    unittest.main()
