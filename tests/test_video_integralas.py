"""C20b: a videó bevitele a vaultba — a 14 lépéses lánc (D1), a gépi írás egy tétele, a visszavonás, a staging visszajelzése, a tracker
eseménye, a próbamód, a behúzott fájl átvétele, a feladattípus és a feltöltés végpontja.

Álvault, ál-staging és ál-`var/` (a valódi vaulthoz, staginghez és var/-hoz egyik teszt sem nyúl); a modell hamis (a worker nem
indul), az ffmpeg-mérés hamis (a valódi ffmpeg-es átvételt a `BevitelTest` csak pinelt ffmpeg mellett futtatja)."""
import base64
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from core import binaris_naplo, gepi_iras, snapshot, tasks, vaultio, video_api, videolanc
from core.tulajdonsagok import Tulajdonsagok
from modulok.ytdlp import integralas as I
from modulok.ytdlp import konvertalas, staging
from tests import csak_darwin
from tests.grafikon_segedek import SzolgaltatasKliens
from tests.helpers import alg_core, ir, tmpdir

T05 = "T05 - A reformkor/Elmélet/01 - Széchenyi István.md"
T05B = "T05 - A reformkor/Elmélet/02 - Kossuth Lajos.md"
T06 = "T06 - Forradalom/Elmélet/01 - Petőfi Sándor.md"
FM = '---\nTags:\n  - History\nSource:\n  - "[[Tankönyv.pdf#page=3]]"\nStatus:\nNN:\nCanvas:\n---\n'
ATIRAT = ("[00:00:01]\nA reformkori országgyűlések idején Széchenyi István megírta a Hitel című munkáját.\n\n"
          "[00:00:20]\nA reformkori átalakulás jobbágyfelszabadítás örökváltság közteherviselés kérdéseit tárgyalta.\n\n"
          "[00:00:45]\nKossuth Lajos Pesti Hírlap szerkesztőjeként népszerűsítette a reformkori programot.\n")


def staging_mappa(gyoker: Path, cim="A reformkor", targy="Történelem", vid="vidREF", atirat=ATIRAT, video=b"\x00\x00\x00\x18ftypmp42" + b"x" * 4096,
                  allapot="pending") -> Path:
    d = gyoker / "Zanza" / targy / cim
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(video)
    (d / "integration.json").write_text(json.dumps({"schema_version": 1, "source_id": f"zanza-{vid}", "media": "video.mp4",
                                                    "url": "https://zanza.tv/tortenelem/reformkor/a-reformkor", "suggested_subject": targy,
                                                    "transcript": "transcript.md", "integration_status": allapot}, indent=2) + "\n")
    (d / "source.md").write_text('---\ntitle: "%s"\nsubject: "%s"\nlanguage: null\nduration_seconds: 75\nmedia_file: "video.mp4"\n'
                                 'downloaded_at: "2026-09-18T23:32:16+00:00"\npipeline_status: "downloaded"\nschema_version: 1\n---\n\n# x\n'
                                 % (cim, targy), encoding="utf-8")
    (d / "metadata.json").write_text(json.dumps({"id": vid, "title": cim, "duration": 75, "extractor": "Youtube", "uploader": "zanza tv",
                                                 "upload_date": "20200423", "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                                                 "resolution": "1440x1080", "vcodec": "avc1.640028", "acodec": "mp4a.40.2",
                                                 "pipeline": {"downloaded_at": "2026-09-18T23:32:16+00:00"}}, ensure_ascii=False))
    if atirat is not None:
        (d / "transcript.md").write_text('---\nlanguage: "hu"\ntranscript_status: "completed"\ntranscript_postprocessed: false\n'
                                         'transcript_engine: "faster-whisper:large-v3-turbo"\ntranscript_model: "large-v3-turbo"\n'
                                         'transcript_generated_at: "2026-09-18T23:34:00+00:00"\n---\n' + atirat, encoding="utf-8")
    return d


class HamisModellek:
    def __init__(self, vannak=(), valaszok=None, proba=False):
        self.vannak, self.valaszok, self.proba = set(vannak), valaszok or {}, proba
        self.hivasok: list[tuple] = []

    def van(self, feladat):
        return feladat in self.vannak

    def kerdez(self, feladat, prompt, max_tokens):
        self.hivasok.append((feladat, prompt[:30]))
        v = self.valaszok[feladat]
        return (v(prompt) if callable(v) else v), {"feladat": feladat, "modell": "hamis-" + feladat, "proba": self.proba}

    def atir(self, hang, nyelv):
        self.hivasok.append(("atirat", hang))
        return ({"szegmensek": [{"start": 0.0, "end": 30.0, "text": "A reformkori országgyűlések Széchenyi István"},
                                {"start": 30.0, "end": 70.0, "text": "jobbágyfelszabadítás örökváltság közteherviselés"}],
                 "nyelv": "hu", "model": "mlx-community/whisper-large-v3-turbo"},
                {"feladat": "atirat", "modell": "whisper_turbo_mlx", "proba": self.proba})


def hamis_felmeres(ff, p):
    return konvertalas.Felmeres("mov,mp4", "h264", "aac", 75.4, 1440, 1080)


@csak_darwin("APFS-klón (clonefile)")
class IntegralasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.staging = Path(self._t.name) / "staging"
        self.cfg, self.root, self.v = alg_core(self._t.name, MOS_STAGING=str(self.staging))
        ir(self.v, T05, FM + "# Széchenyi István\n\nSzéchenyi István a reformkori országgyűlések vezéralakja, a Hitel szerzője; "
                       "a reformkori átalakulás programját fogalmazta meg.\n")
        ir(self.v, T05B, FM + "# Kossuth Lajos\n\nKossuth Lajos a Pesti Hírlap szerkesztője, a jobbágyfelszabadítás és a "
                        "közteherviselés szószólója.\n")
        ir(self.v, T06, FM + "# Petőfi Sándor\n\nPetőfi Sándor forradalmi költészete, márciusi ifjúság, Nemzeti dal.\n")
        (self.v / "ATTCHMNTS - Videos").mkdir()
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.V = vaultio.Vault(self.cfg)
        self.esemenyek: list[dict] = []
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None), varakozas_mp=0.3,
                                    esemeny_jelzo=self.esemenyek.append)
        self.kliens = SzolgaltatasKliens(self.G, self.V)
        d = mock.patch.object(gepi_iras.GepiIras, "_d9", lambda s, k: None)   # a hamis modell „kalibrált” (a D9 a próba-tesztben)
        d.start()
        self.addCleanup(d.stop)
        self.kotes = {"auto": [{"jegyzet": T05, "media": "A reformkor.mp4", "t": 10, "vegso_t": 12, "p": 0.97, "sajat_tema": True,
                                "rang": 1, "jegyek": {}, "bizonyitek": {"ritka_kozos": ["széchen"], "evszam_kozos": []}}],
                      "javaslat": [{"jegyzet": T05B, "media": "A reformkor.mp4", "t": 40, "vegso_t": 45, "p": 0.80, "sajat_tema": True,
                                    "rang": 2, "jegyek": {}, "bizonyitek": {"ritka_kozos": ["kossuth"], "evszam_kozos": []}}]}
        k = mock.patch.object(I.KT, "kotes", lambda *a, **kw: json.loads(json.dumps(self.kotes)))
        k.start()
        self.addCleanup(k.stop)

    def lanc(self, M=None, **kw):
        return I.Integralas(self.cfg, modellek=M or HamisModellek(), gepi=self.kliens, felmeres=hamis_felmeres, log=lambda s: None, **kw)

    def statusz(self, d: Path) -> str:
        return json.loads((d / "integration.json").read_text())["integration_status"]

    def test_teljes_tetel_visszavonas_es_visszajelzes(self):
        d = staging_mappa(self.staging)
        eredeti = (d / "video.mp4").read_bytes()
        M = HamisModellek(vannak={"kotes"}, valaszok={"kotes": "igen"})
        r = self.lanc(M).futtat()
        self.assertEqual(r["eredmeny"], {"integralva": 1}, r)
        t = r["tetelek"][0]
        self.assertEqual((t["tema"]["tema"], t["tema"]["biztossag"]), ("T05 - A reformkor", "biztos"))     # a cím és a lift egyezik
        media = self.v / "T05 - A reformkor" / "Média"
        self.assertEqual((self.v / "ATTCHMNTS - Videos" / "A reformkor.mp4").read_bytes(), eredeti)
        self.assertEqual((d / "video.mp4").read_bytes(), eredeti)                                       # a staging példánya marad
        vtt = (media / "A reformkor.hu.vtt").read_text()
        self.assertIn("NOTE manifold-asr", vtt)
        self.assertEqual(json.loads((media / "A reformkor.info.json").read_text())["id"], "vidREF")
        jegyzet = (media / "A reformkor.md").read_text()
        self.assertTrue(jegyzet.startswith('---\nTags:\n  - History\nSource:\n  - "[[A reformkor.mp4#t=0]]"'))
        self.assertIn("<!-- manifold-media-source-note -->", jegyzet)
        self.assertIn('  - "[[Tankönyv.pdf#page=3]]"\n  - "[[A reformkor.mp4#t=12]]"\nStatus:', (self.v / T05).read_text())
        self.assertIn('"[[A reformkor.mp4#t=45]]"', (self.v / T05B).read_text())       # a javaslat: a modell „igen” → elfogadva
        self.assertEqual(M.hivasok, [("kotes", "Egy magyar oktatóvideó felirat")])
        self.assertEqual(sorted(self.repo.changed_files(t["commit"])),
                         sorted([T05, T05B, "T05 - A reformkor/Média/A reformkor.hu.vtt", "T05 - A reformkor/Média/A reformkor.info.json",
                                 "T05 - A reformkor/Média/A reformkor.md"]))                       # a videó a pillanatképben nincs (14.)
        rec = binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg))[-1]
        self.assertEqual((rec["commit"], rec["tipus"], rec["klon"], rec["fajlok"]), (t["commit"], "media", True,
                                                                                    ["ATTCHMNTS - Videos/A reformkor.mp4"]))
        self.assertEqual(self.esemenyek, [{"tipus": "integralt_video", "ut": "T05 - A reformkor/Média/A reformkor.md",
                                           "adat": {"video_s": 75, "jegyzet_db": 2, "kotes": "valoszinu"}}])
        self.assertEqual(self.statusz(d), "integrated")
        allapot = json.loads((self.cfg.path("video_jobs") / "youtube-vidREF" / "integralas.json").read_text())
        self.assertEqual(list(allapot["lepesek"]), [x for x in I.LEPESEK if x in allapot["lepesek"]])
        self.assertEqual(len(allapot["lepesek"]), 14)
        # a második kör: nincs várakozó forrás (a staging „integrated”); kifejezetten megadva: már a vaultban
        self.assertEqual(self.lanc().futtat()["eredmeny"], {})
        self.assertEqual(self.lanc().futtat([d])["eredmeny"], {"mar_megvan": 1})
        # a visszavonás (a vezérlő „Visszavonás”-a: App.undo → revert + a bináris napló): a klón az archívumba, nem törlődik
        self.repo.undo_commit(t["commit"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, t["commit"], None, log=lambda s: None)
        self.assertEqual(len(v["mozgatva"]), 1)
        self.assertFalse((self.v / "ATTCHMNTS - Videos" / "A reformkor.mp4").exists())
        self.assertFalse(media.exists() and any(media.iterdir()))
        self.assertNotIn("A reformkor.mp4", (self.v / T05).read_text())
        arch = list(self.cfg.path("video_visszavont").rglob("A reformkor.mp4"))
        self.assertEqual([p.read_bytes() for p in arch], [eredeti])
        self.assertEqual((d / "video.mp4").read_bytes(), eredeti)

    def test_kalibralt_kotes_modell_nelkul_a_javaslat_nem_kotott(self):
        staging_mappa(self.staging)
        r = self.lanc().futtat()
        t = r["tetelek"][0]
        self.assertEqual([(k["jegyzet"], k["dontes"]) for k in t["kotesek"]], [(T05, "elfogad")])
        self.assertNotIn("A reformkor.mp4", (self.v / T05B).read_text())
        self.assertEqual(self.esemenyek[0]["adat"], {"video_s": 75, "jegyzet_db": 1, "kotes": "biztos"})
        self.assertEqual(self.kliens.hivasok[-1]["modell"], None)                  # lexikai téma + verifikátor: determinisztikus

    def test_utkozes_vegallapot_in_review(self):
        d = staging_mappa(self.staging)
        (self.v / "ATTCHMNTS - Videos" / "A reformkor.mp4").write_bytes(b"masik")
        r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"utkozes": 1})
        self.assertEqual(self.statusz(d), "in_review")
        self.assertEqual((self.v / "ATTCHMNTS - Videos" / "A reformkor.mp4").read_bytes(), b"masik")

    def test_atirat_kalibralatlan_marad_pending(self):
        d = staging_mappa(self.staging, atirat=None)
        r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"atirat_kalibralatlan": 1})
        self.assertEqual(self.statusz(d), "pending")
        self.assertFalse((self.v / "T05 - A reformkor" / "Média").exists())

    def test_nincs_tema(self):
        d = staging_mappa(self.staging, cim="Másodfokú egyenlet", targy="Matematika", vid="vidM",
                          atirat="[00:00:01]\nA másodfokú egyenlet megoldóképlete diszkrimináns.\n")
        r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"nincs_tema": 1})
        self.assertEqual(self.statusz(d), "in_review")

    def test_bizonytalan_tema_is_beirodik_d1(self):
        staging_mappa(self.staging, cim="Egy előadás", vid="vidB")
        r = self.lanc().futtat()
        t = r["tetelek"][0]
        self.assertEqual(t["allapot"], "integralva")
        self.assertEqual(t["tema"]["biztossag"], "bizonytalan")
        self.cfg.data.setdefault("video", {})["bizonytalan_tema"] = "kihagy"
        staging_mappa(self.staging, cim="Még egy előadás", vid="vidC")
        self.assertEqual(self.lanc().futtat()["eredmeny"], {"nincs_tema": 1})

    def test_proba_a_klonra_ir_a_staging_es_a_vault_erintetlen(self):
        d = staging_mappa(self.staging, atirat=None)
        M = HamisModellek(vannak={"atirat"}, proba=True)
        r = self.lanc(M, proba=True).futtat()
        self.assertEqual(r["eredmeny"], {"integralva": 1}, r)
        self.assertEqual(self.statusz(d), "pending")
        self.assertFalse((self.v / "ATTCHMNTS - Videos" / "A reformkor.mp4").exists())
        self.assertNotIn("A reformkor.mp4", (self.v / T05).read_text())
        self.assertEqual(self.kliens.hivasok[-1]["modell"], {"feladat": "atirat", "modell": "whisper_turbo_mlx", "proba": True})
        self.assertTrue(self.kliens.hivasok[-1]["proba"])
        self.assertEqual(self.esemenyek, [])                                       # próbában nincs tracker-esemény
        self.assertFalse((self.cfg.path("video_jobs") / "youtube-vidREF").exists())

    def test_proba_modell_elesben_nem_ir_d9(self):
        mock.patch.stopall()
        k = mock.patch.object(I.KT, "kotes", lambda *a, **kw: {"auto": [], "javaslat": []})
        k.start()
        self.addCleanup(k.stop)
        d = staging_mappa(self.staging, atirat=None)
        r = self.lanc(HamisModellek(vannak={"atirat"}, proba=True)).futtat()
        self.assertEqual(r["eredmeny"], {"hiba": 1})
        self.assertIn("csak próbában", r["tetelek"][0]["uzenet"])
        self.assertEqual(self.statusz(d), "pending")


    # ---------------------------------------------- 86. döntés (javasolt): a kényszerített célmappa

    CS = "D13 - CS50"
    CS_FM = '---\nTags:\n  - Informatics\nSource:\n  - "[[CS50.pdf#page=1]]"\nStatus:\nNN:\nCanvas:\n---\n'

    def test_celmappa_uj_mappa_determinisztikus_tema_es_visszavonas(self):
        """A staging tárgya (Irodalom, a korábbi téves besorolás) nem számít; a téma- és a kötés-modell nem fut; a mappa ugyanabban a
        tételben jön létre; a jegyzet Tags-e a D betűből (Informatics); a gépi írás modell-jele null; a visszavonás mindent visz."""
        d = staging_mappa(self.staging, cim="CS50x - Lecture 0 - Scratch", targy="Irodalom", vid="vidCS0")
        eredeti = (d / "video.mp4").read_bytes()
        t05 = (self.v / T05).read_text()
        M = HamisModellek(vannak={"tema", "kotes"}, valaszok={"tema": "1", "kotes": "igen"})
        r = self.lanc(M, tema_mappa=self.CS).futtat([d])
        self.assertEqual(r["eredmeny"], {"integralva": 1}, r)
        t = r["tetelek"][0]
        self.assertEqual(t["tema"], {"tema": self.CS, "forras": "célmappa", "biztossag": "biztos",
                                     "jel": "a hívó megadta a célmappát (--tema-mappa): a téma-modell és a lexikai besorolás nem fut"})
        self.assertEqual(M.hivasok, [])                                                  # se téma-, se kötés-modell
        media = self.v / self.CS / "Média"
        nev = "CS50x - Lecture 0 - Scratch"
        self.assertEqual((self.v / "ATTCHMNTS - Videos" / f"{nev}.mp4").read_bytes(), eredeti)
        jegyzet = (media / f"{nev}.md").read_text()
        self.assertTrue(jegyzet.startswith(f'---\nTags:\n  - Informatics\nSource:\n  - "[[{nev}.mp4#t=0]]"'), jegyzet[:200])
        self.assertEqual((self.v / T05).read_text(), t05)                               # a mappán kívüli jegyzethez nem köt
        self.assertEqual(t["kotesek"], [])
        self.assertEqual(self.kliens.hivasok[-1]["modell"], None)
        self.assertEqual(sorted(self.repo.changed_files(t["commit"])),
                         sorted(f"{self.CS}/Média/{nev}{x}" for x in (".hu.vtt", ".info.json", ".md")))
        allapot = json.loads((self.cfg.path("video_jobs") / "youtube-vidCS0" / "integralas.json").read_text())
        self.assertEqual(allapot["lepesek"]["jeloltek"]["kihagyva"], "a célmappa új: nincs benne jegyzet, amelyhez kötni lehetne")
        self.assertEqual(self.statusz(d), "integrated")
        # a második bevitel ugyanabba a (már létező) mappába: a duplikátum-szűrés az új mappát is látja
        self.assertEqual(self.lanc(tema_mappa=self.CS).futtat([d])["eredmeny"], {"mar_megvan": 1})
        self.repo.undo_commit(t["commit"])
        binaris_naplo.visszavonas_utan(self.cfg, self.repo, t["commit"], None, log=lambda s: None)
        self.assertFalse((self.v / "ATTCHMNTS - Videos" / f"{nev}.mp4").exists())
        self.assertFalse(media.exists() and any(media.iterdir()))

    def test_celmappa_letezo_mappa_csak_a_sajat_jegyzetekhez_kot(self):
        sajat = f"{self.CS}/Elmélet/01 - Scratch.md"
        ir(self.v, sajat, self.CS_FM + "# Scratch\n\nA Scratch blokkos programozási nyelv, a reformkori példák nélkül.\n")
        self.repo.commit("cs50", {"Mos-Forras": "kezi"})
        self.kotes["auto"].append({**self.kotes["auto"][0], "jegyzet": sajat, "vegso_t": 30})
        d = staging_mappa(self.staging, cim="CS50x - Lecture 0", targy="Informatika", vid="vidCS1")
        M = HamisModellek(vannak={"kotes"}, valaszok={"kotes": "igen"})
        r = self.lanc(M, tema_mappa=self.CS).futtat([d])
        self.assertEqual(r["eredmeny"], {"integralva": 1}, r)
        t = r["tetelek"][0]
        self.assertEqual([(k["jegyzet"], k["dontes"]) for k in t["kotesek"]], [(sajat, "elfogad")])
        self.assertEqual(M.hivasok, [])                    # a mappán kívüli javaslat (T05B) el sem olvasódik
        self.assertIn('"[[CS50x - Lecture 0.mp4#t=30]]"', (self.v / sajat).read_text())
        self.assertNotIn("CS50x", (self.v / T05).read_text() + (self.v / T05B).read_text())
        self.assertTrue((self.v / self.CS / "Média" / "CS50x - Lecture 0.md").is_file())

    def test_celmappa_atirat_nelkul_pending_marad_d9(self):
        d = staging_mappa(self.staging, cim="CS50x - Lecture 2", targy="Informatika", vid="vidCS2", atirat=None)
        r = self.lanc(tema_mappa=self.CS).futtat([d])
        self.assertEqual(r["eredmeny"], {"atirat_kalibralatlan": 1})
        self.assertEqual(self.statusz(d), "pending")
        self.assertFalse((self.v / self.CS).exists())


class EsemenyKapuTest(unittest.TestCase):
    def test_csak_a_mos_video_es_az_engedett_kulcsok(self):
        alap = {"kor": "VIDEOBE-20261008-120000", "tetel": "t", "forras": "mos-video", "modell": None,
                "muveletek": [{"tipus": "uj", "ut": "a.md", "tartalom": "x"}]}
        k = gepi_iras._keres({**alap, "esemeny": {"tipus": "integralt_video", "ut": "T/a.md", "adat": {"video_s": 3}}})
        self.assertEqual(k.esemeny["tipus"], "integralt_video")
        for rossz in ({**alap, "forras": "mos-kartya", "esemeny": {"tipus": "integralt_video", "ut": "a", "adat": {}}},
                      {**alap, "esemeny": {"tipus": "kartya_valasz", "ut": "a", "adat": {}}},
                      {**alap, "esemeny": {"tipus": "integralt_video", "ut": "a", "adat": {"jelszo": 1}}}):
            with self.assertRaises(vaultio.Invalid):
                gepi_iras._keres(rossz)


class FeladatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.staging = Path(self._t.name) / "staging"
        self.cfg, self.root, _ = alg_core(self._t.name, MOS_STAGING=str(self.staging))
        ff = self.cfg.path("ffmpeg")
        ff.parent.mkdir(parents=True, exist_ok=True)
        ff.write_text("#!/bin/sh\n")
        videolanc.regisztral()

    def test_terv_validalas_es_lepes(self):
        staging_mappa(self.staging)
        lepesek, _, figy = videolanc._integralas_terv(self.cfg, {"mappak": ["Zanza/Történelem/A reformkor"], "proba": True}, "/stop")
        self.assertEqual(lepesek[0].argv[-4:], ["integral", "--mappa", str(self.staging / "Zanza/Történelem/A reformkor"), "--proba"][-4:])
        self.assertEqual(lepesek[0].jogok, "gepi")
        self.assertTrue(figy)
        for p in ({"mappak": ["../ki"]}, {"mappak": ["/abs"]}, {"mappak": ["nincs"]}, {"csoport": "../x"}, {"proba": "igen"}, []):
            with self.subTest(p=p), self.assertRaises(tasks.Invalid):
                videolanc._integralas_terv(self.cfg, p, "/stop")
        self.assertEqual(tasks.REGISTRY[videolanc.INTEGRALAS].resources, frozenset({"modell", "vault"}))

    def test_terv_celmappa(self):
        """86. d. (javasolt): a `tema_mappa` csak kijelölt forrással, a core ellenőrzi (400), és a lépés `--tema-mappa`-t kap."""
        staging_mappa(self.staging)
        lepesek, osszeg, _ = videolanc._integralas_terv(
            self.cfg, {"mappak": ["Zanza/Történelem/A reformkor"], "tema_mappa": "D13 - CS50 "}, "/stop")
        self.assertEqual(lepesek[0].argv[-2:], ["--tema-mappa", "D13 - CS50"])
        self.assertIn("„D13 - CS50/Média”", osszeg)
        for p in ({"tema_mappa": "D13 - CS50"}, {"mappak": ["Zanza/Történelem/A reformkor"], "tema_mappa": "D13 - CS50/x"},
                  {"mappak": ["Zanza/Történelem/A reformkor"], "tema_mappa": "Q13 - Ismeretlen"},
                  {"mappak": ["Zanza/Történelem/A reformkor"], "tema_mappa": 5}):
            with self.subTest(p=p), self.assertRaises(tasks.Invalid):
                videolanc._integralas_terv(self.cfg, p, "/stop")

    def _sor(self):
        cfg = self.cfg
        logdir = Path(self._t.name) / "feladatok"
        logdir.mkdir(exist_ok=True)

        class Sor:
            def __init__(self):
                self.k, self.cfg, self.logdir = [], cfg, logdir

            def submit(self, t, p):
                self.k.append((t, p))
                return {"id": "x"}
        return Sor()

    def _eredmeny(self, s, fid, mappak):
        videolanc.letoltes_eredmeny(s.logdir, fid).write_text(json.dumps({"mappak": mappak}), encoding="utf-8")

    def test_letoltes_utan_egyszer_sorba(self):
        staging_mappa(self.staging)
        s = self._sor()
        sajat = "Zanza/Történelem/A reformkor"
        for fid in ("F-1", "F-2", "F-3", "F-4"):
            self._eredmeny(s, fid, [sajat, "../kint", "/abs", "nincs/ilyen", sajat])
        f = {"id": "F-1", "tipus": videolanc.TIPUS, "allapot": "kesz", "parameterek": {"urlek": ["https://a"], "bevitel": True}}
        videolanc.letoltes_utan(s, f)
        videolanc.letoltes_utan(s, f)
        videolanc.letoltes_utan(s, {**f, "id": "F-2", "parameterek": {"bevitel": True, "proba": True}})
        videolanc.letoltes_utan(s, {**f, "id": "F-3", "parameterek": {}})
        # F4: csak a saját, létező staging-mappák (nem az összes várakozó: `{}`), és hibás letöltés után semmi
        videolanc.letoltes_utan(s, {**f, "id": "F-4", "allapot": "hiba"})
        self.assertEqual(s.k, [(videolanc.INTEGRALAS, {"mappak": [sajat]})])

    def test_letoltes_utan_eredmeny_nelkul_nem_indul(self):
        s = self._sor()
        f = {"id": "F-9", "tipus": videolanc.TIPUS, "allapot": "kesz", "parameterek": {"urlek": ["https://a"], "bevitel": True}}
        videolanc.letoltes_utan(s, f)                                   # nincs eredményfájl
        self._eredmeny(s, "F-10", [])
        videolanc.letoltes_utan(s, {**f, "id": "F-10"})                 # üres lista
        self.assertEqual(s.k, [])

    def test_a_letoltes_lepese_megirja_a_sajat_mappait(self):
        """A `lanc.letoltes` `eredmeny_fajl`-ja: a letöltött és a már meglévő tételek staging-relatív mappái, a hibás nem."""
        from types import SimpleNamespace
        from unittest import mock
        from modulok.ytdlp import eszkoz, lanc
        staging_mappa(self.staging)
        meglevo = self.staging / "Zanza" / "Történelem" / "A reformkor"
        uj = self.staging / "Uj" / "Video"
        uj.mkdir(parents=True)
        folyamat = SimpleNamespace(STATUS_DOWNLOADED="downloaded", STATUS_SKIPPED="skipped")
        valaszok = iter([SimpleNamespace(status="downloaded", path=str(uj)), SimpleNamespace(status="skipped", path=str(meglevo)),
                         SimpleNamespace(status="failed", path=None, message="x", error=None)])
        folyamat.ingest_url = lambda *a, **k: next(valaszok)
        letolto = SimpleNamespace(require_ytdlp=lambda c: None, create_downloader=lambda *a, **k: object())
        archivum = SimpleNamespace(Archive=lambda *a, **k: object())
        mcfg = SimpleNamespace(archive_dir=str(Path(self._t.name) / "archive"), archive=SimpleNamespace(enabled=False))
        ki = Path(self._t.name) / "ki" / "F-1.letoltes.json"
        with mock.patch.object(lanc, "msp", return_value=(None, letolto, folyamat, archivum)), \
                mock.patch.object(lanc, "msp_konfig", return_value=mcfg), \
                mock.patch.object(eszkoz, "ffmpeg_ellenorzott", return_value="ffmpeg"), \
                mock.patch.object(lanc, "KonvertaloLetolto", lambda *a, **k: object()), \
                mock.patch.object(lanc, "_video_beallitas", return_value={}), \
                mock.patch.object(lanc, "pillanat_elo"), mock.patch.object(lanc, "pillanat_utan"):
            kod = lanc.letoltes(self.cfg, ["https://a", "https://b", "https://c"], log=lambda s: None, kozvetlen_tetelek={},
                                eredmeny_fajl=ki)
        self.assertEqual(kod, 1)
        d = json.loads(ki.read_text(encoding="utf-8"))
        self.assertEqual(d["mappak"], ["Uj/Video", "Zanza/Történelem/A reformkor"])
        self.assertEqual((d["letoltve"], d["megvolt"], d["hiba"]), (1, 1, 1))


class FeltoltesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

        class App:
            pass
        self.app = App()
        self.app.cfg = self.cfg

    def test_darabolt_feltoltes_es_vegleges_nev(self):
        from core.utvonalak import HttpError
        b1, b2 = b"a" * 10, b"b" * 5
        r = video_api.bejovo(self.app, {"nev": "Előadás.mp4", "offset": 0, "adat": base64.b64encode(b1).decode()})
        cs = r["csoport"]
        with self.assertRaises(HttpError) as e:
            video_api.bejovo(self.app, {"nev": "Előadás.mp4", "csoport": cs, "offset": 3, "adat": base64.b64encode(b2).decode()})
        self.assertEqual(e.exception.code, 409)
        r = video_api.bejovo(self.app, {"nev": "Előadás.mp4", "csoport": cs, "offset": 10, "adat": base64.b64encode(b2).decode(), "vege": True})
        self.assertEqual((r["nev"], r["meret"]), ("Előadás.mp4", 15))
        self.assertEqual((self.cfg.path("video_bejovo") / cs / "Előadás.mp4").read_bytes(), b1 + b2)
        r2 = video_api.bejovo(self.app, {"nev": "Előadás.mp4", "csoport": cs, "offset": 0, "adat": base64.b64encode(b2).decode(), "vege": True})
        self.assertEqual(r2["nev"], "Előadás (2).mp4")                                    # felülírás nincs
        for rossz in ({"nev": "kep.jpg", "adat": ""}, {"nev": "../x.mp4", "csoport": "../x", "adat": ""},
                      {"nev": "a.mp4", "adat": "!!!"}, {"nev": "a.mp4", "offset": -1, "adat": ""}):
            with self.subTest(r=rossz), self.assertRaises(HttpError):
                video_api.bejovo(self.app, rossz)

    def test_allapot(self):
        staging_mappa(self.cfg.path("staging"))
        staging_mappa(self.cfg.path("staging"), cim="Más", vid="v2", allapot="integrated")
        a = video_api.allapot(self.app)
        self.assertEqual((a["staging"], a["varakozik"]), ({"pending": 1, "integrated": 1}, 1))
        self.assertEqual(a["fuggo"], [{"mappa": "Zanza/Történelem/A reformkor", "cim": "A reformkor"}])
        v = self.cfg.path("vault")
        for m in ("D08 - Algoritmizálás", "D00 - Visual", "ATTCHMNTS - Videos", "D13 - CS50"):
            (v / m).mkdir(parents=True, exist_ok=True)
        self.assertEqual(video_api.allapot(self.app)["temamappak"], ["D08 - Algoritmizálás", "D13 - CS50"])


class BevitelTest(unittest.TestCase):
    """A behúzott fájl → staging-forrásmappa a pinelt ffmpeg-gel (nélküle indokolt kihagyás)."""

    def setUp(self):
        from tests.video_segedek import FFMPEG, ffmpeg_elerheto
        if not ffmpeg_elerheto():
            self.skipTest("[indokolt] nincs runtime/ffmpeg (bin/mos runtime fetch ffmpeg)")
        self.ff = str(FFMPEG)
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

    def test_forrasmappa_es_ismetles(self):
        from modulok.ytdlp import bevitel
        from tests.video_segedek import szintetikus_video
        be = self.cfg.path("video_bejovo") / "cs1"
        f = szintetikus_video(be / "Saját előadás.mp4", kontener="mp4")
        d = bevitel.forrasmappa(self.cfg, f, ffmpeg=self.ff, log=lambda s: None)
        src = staging.olvas(d)
        self.assertEqual((src["cim"], src["integration"]["integration_status"]), ("Saját előadás", "pending"))
        self.assertTrue(src["video_id"].startswith("helyi-") and not f.exists())
        g = szintetikus_video(be / "másolat.mp4", kontener="mp4")
        self.assertEqual(bevitel.forrasmappa(self.cfg, g, ffmpeg=self.ff, log=lambda s: None), d)      # ugyanaz a tartalom
        with self.assertRaises(bevitel.BevitelHiba):
            bevitel.forrasmappa(self.cfg, be / "nincs.txt", ffmpeg=self.ff)


if __name__ == "__main__":
    unittest.main()
