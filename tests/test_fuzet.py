"""C21: a füzetlánc — papírkivágás és forgatás (modell nélkül), a `## Füzet` formátum, az átirat tisztítása, a gépi írás `mozgat`
művelete a bináris naplóval és a visszavonással (L19, L20), a lánc álworkerrel és a gépi-írás szolgáltatással, a figyelő, a
feltöltés és a képlet-OCR végpontja, az Asszisztens kikapcsolásának hatása az automatikus feladatra (9. pont).
A valódi vaulthoz, `var/`-hoz és workerhez egyik teszt sem nyúl."""
import base64
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from core import binaris_naplo, fuzet, fuzet_api, fuzet_feladat, fuzet_figyelo, gepi_iras, snapshot, tasks, vaultio, vezerlo
from core.tulajdonsagok import Tulajdonsagok
from core.utvonalak import HttpError
from tests import csak_darwin
from tests.helpers import REPO, alg_core, ir, tmpdir

sys.path.insert(0, str(REPO / "modulok"))
from fuzet import formatum, kep, lanc as L, modszer  # noqa: E402
from fuzet.katalogus import Katalogus  # noqa: E402

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
J1 = "M10 - Geometria (szintetikus)/Elmélet/01 - A háromszögek alapismeretei.md"
J2 = "M10 - Geometria (szintetikus)/Elmélet/02 - Pitagorasz-tétel.md"
KAT = {"fejezetek": [{"kod": "M10", "nev": "Geometria (szintetikus)", "targy": "Matematika"}],
       "jegyzetek": [{"ut": J1, "cim": "A háromszögek alapismeretei", "cimsorok": ["Háromszög", "Szögek"],
                      "szavak": {"haroms": 9, "szogei": 4, "kulso": 3}},
                     {"ut": J2, "cim": "Pitagorasz-tétel", "cimsorok": ["Pitagorasz"], "szavak": {"pitago": 9, "befogo": 4}}]}


def papir_kep(ut: Path, allo: bool = False, szelen: bool = False):
    """Szintetikus füzetfotó: sötét asztal, világos papír (a képszélt nem érinti), a spirál sötét sávja középen."""
    from PIL import Image, ImageDraw
    sz, m = (900, 1200) if allo else (1200, 800)
    im = Image.new("RGB", (sz, m), (40, 40, 40))
    d = ImageDraw.Draw(im)
    if szelen:                                   # a füzet a kép szélét is érinti, a belső folt apró: hihetetlen kivágás (IMG_1764)
        d.rectangle((0, 0, 800, m - 1), fill=(230, 230, 230))
        d.rectangle((1000, 300, 1100, 400), fill=(240, 240, 240))
    elif allo:
        d.rectangle((150, 100, 750, 1100), fill=(235, 235, 235))
        d.rectangle((150, 590, 750, 610), fill=(60, 60, 60))
    else:
        d.rectangle((120, 100, 1080, 700), fill=(235, 235, 235))
        d.rectangle((590, 100, 610, 700), fill=(60, 60, 60))
    ut.parent.mkdir(parents=True, exist_ok=True)
    im.save(ut, quality=92)
    return ut


class KepTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)

    def test_fekvo_papir_ket_oldal_a_spiralnal(self):
        e = kep.elokeszit(kep.betolt(papir_kep(self.d / "a.jpg")))
        self.assertEqual((e.kivagas, e.fekvo, [n for n, _ in e.lapok]), ("papir", True, ["bal", "jobb"]))
        bal, jobb = e.lapok[0][1], e.lapok[1][1]
        self.assertLess(abs(bal.width - jobb.width), 0.1 * bal.width)        # a vágás a spirálnál, középen
        self.assertGreater(bal.height, 0.6 * 600)                             # a papír magassága (az asztal nélkül)

    def test_allo_papir_felso_also_forgatassal(self):
        e = kep.elokeszit(kep.betolt(papir_kep(self.d / "b.jpg", allo=True)))
        self.assertEqual((e.kivagas, e.fekvo, [n for n, _ in e.lapok]), ("papir", False, ["felso", "also"]))
        meta, utak = kep.oldalkepek(self.d / "b.jpg", self.d / "ki", forgatas=-90)
        self.assertFalse(meta["fekvo"])
        self.assertTrue(all(u.name.endswith("-r-90.jpg") and u.is_file() for u in utak))
        from PIL import Image
        alap = Image.open(kep.oldalkepek(self.d / "b.jpg", self.d / "ki")[1][0])
        with Image.open(utak[0]) as f:
            self.assertEqual(f.size, (alap.height, alap.width))

    def test_hihetetlen_kivagas_teljes(self):
        e = kep.elokeszit(kep.betolt(papir_kep(self.d / "c.jpg", szelen=True)))
        self.assertEqual((e.kivagas, e.fekvo, len(e.lapok)), ("teljes", True, 2))

    def test_gyorsitotar_es_kep_e(self):
        p = papir_kep(self.d / "a.jpg")
        m1, u1 = kep.oldalkepek(p, self.d / "ki")
        t = u1[0].stat().st_mtime_ns
        m2, u2 = kep.oldalkepek(p, self.d / "ki")
        self.assertEqual((m1, u1, u2[0].stat().st_mtime_ns), (m2, u2, t))
        self.assertTrue(kep.kep_e("IMG_1.JPG") and kep.kep_e("x.heic"))
        self.assertFalse(kep.kep_e(".IMG.jpg") or kep.kep_e("a.mp4"))

    def test_forgatas_dontes_a_szokincs_szerint(self):
        szk = set(kep.tovek("háromszög szögei külső szög pitagorasz befogó"))
        fok, pont = kep.forgatas_dontes({-90: "xqzw vbnm", 90: "A háromszög szögei és a külső szög", 0: "lkjh"}, szk)
        self.assertEqual(fok, 90)
        self.assertGreater(pont[90], pont[-90])
        self.assertEqual(kep.forgatas_dontes({}, szk)[0], -90)                # döntetlen: a legacy alapja
        self.assertEqual(kep.FORGATASOK, (-90, 90, 0))


class FormatumTest(unittest.TestCase):
    def test_uj_szakasz_a_vegere_es_a_visszaut(self):
        t = FM + "# Cím\n\nszöveg\n"
        u = formatum.beagyaz(t, "IMG_2.jpg", ["a^2+b^2=c^2"])
        self.assertTrue(u.endswith("## Füzet\n\n![[IMG_2.jpg]]\n> [!info]- Képletek a fotóról\n> $$a^2+b^2=c^2$$\n"))
        self.assertEqual(formatum.beagyaz(u, "IMG_2.jpg", ["más"]), u)                       # idempotens
        self.assertEqual(formatum.levalaszt(u, "IMG_2.jpg"), t)

    def test_rendezes_es_ures_sor_a_callout_utan(self):
        t = "# C\n\n## Füzet\n\n![[IMG_1.jpg]]\n![[IMG_3.jpg]]\n\n## Más\n"
        u = formatum.beagyaz(t, "IMG_2.jpg", ["x=1"])
        self.assertIn("![[IMG_1.jpg]]\n![[IMG_2.jpg]]\n> [!info]- Képletek a fotóról\n> $$x=1$$\n\n![[IMG_3.jpg]]", u)
        v = formatum.beagyaz(u, "IMG_4.jpg")
        self.assertIn("![[IMG_3.jpg]]\n![[IMG_4.jpg]]\n\n## Más", v)
        w = formatum.beagyaz(u, "IMG_25.jpg")                 # a callout után üres sor, mielőtt a következő beágyazás jön
        self.assertIn("> $$x=1$$\n\n![[IMG_25.jpg]]\n![[IMG_3.jpg]]", w)
        self.assertEqual(formatum.levalaszt(u, "IMG_2.jpg"), t)
        sorok = formatum.blokk_kivesz(u, "IMG_2.jpg")
        self.assertEqual(formatum.callout_kepletei(sorok), ["x=1"])
        self.assertIsNone(formatum.blokk_kivesz(u, "IMG_9.jpg"))

    def test_kepletek_az_atiratbol(self):
        a = ("Pitagorasz: $a^2+b^2=c^2$, és újra $a^2 + b^2 = c^2$.\n$$\n\\frac{1}{2} x\n$$\nDe: $x$, $12$, $AB$, "
             "költség $5 és $6 között")
        self.assertEqual(formatum.kepletek(a), ["a^2+b^2=c^2", "\\frac{1}{2} x"])
        self.assertEqual(len(formatum.kepletek(" ".join(f"$x={i}$" for i in range(40)), 20)), 20)


class AtiratTest(unittest.TestCase):
    def test_bevezeto_es_kerites(self):
        self.assertEqual(fuzet.atirat_tisztit("Természetesen, itt van a képeken látható szöveg pontos átirata:\n\n**1. oldal**\nx"),
                         "**1. oldal**\nx")
        self.assertEqual(fuzet.atirat_tisztit("```markdown\n# Cím\nszöveg\n```"), "# Cím\nszöveg")
        self.assertEqual(fuzet.atirat_tisztit("Természetes mértékegység: kg\nx"), "Természetes mértékegység: kg\nx")
        self.assertEqual(fuzet.atirat_tisztit("A 1. képen:\nszöveg"), "A 1. képen:\nszöveg")
        self.assertEqual(fuzet.atirat_tisztit(None), "")


class _Core(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.bejovo = Path(self._t.name) / "bejovo"
        self.cfg, self.root, self.v = alg_core(self._t.name, MOS_FUZET_BEJOVO=str(self.bejovo))
        for j in (J1, J2):
            ir(self.v, j, FM + f"# {Path(j).stem[5:]}\n\nszöveg\n")
        (self.v / "ATTCHMNTS - photos").mkdir()
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.V = vaultio.Vault(self.cfg)
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None), varakozas_mp=0.3)

    def foto(self, nev="IMG_1.jpg", csoport="cs1", **kw) -> Path:
        return papir_kep(self.bejovo / csoport / nev, **kw)

    def keres(self, *muveletek, tetel="t1", proba=False):
        return {"kor": "FUZET-20261007-230000", "tetel": tetel, "forras": "mos-fuzet", "modell": None, "proba": proba,
                "muveletek": list(muveletek)}

    def mozgat(self, p: Path, nev=None):
        return {"tipus": "mozgat", "forras": str(p), "ut": f"ATTCHMNTS - photos/{nev or p.name}", "sha256": fuzet.sha256(p)}

    def csere(self, rp, link="IMG_1.jpg"):
        r = self.V.read(rp)
        return {"tipus": "csere", "ut": rp, "tartalom": formatum.beagyaz(r["tartalom"], link, ["x=1"]), "alap": r["hash"]}


class MozgatTest(_Core):
    def test_mozgat_naplo_es_visszavonas_a_forrasba(self):
        p = self.foto()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere(J1)))
        cel = self.v / "ATTCHMNTS - photos" / "IMG_1.jpg"
        self.assertTrue(cel.is_file() and not p.exists())
        self.assertEqual(r["mozgatva"], ["ATTCHMNTS - photos/IMG_1.jpg"])
        self.assertEqual(self.repo.changed_files(r["sha"]), [J1])                          # a fotó a pillanatképben nincs (14.)
        rec = binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg))[-1]
        self.assertEqual((rec["commit"], rec["tipus"], rec["kulcs"], rec["fajlok"]),
                         (r["sha"], "fuzet", str(Path(os.path.realpath(p)).parent), ["ATTCHMNTS - photos/IMG_1.jpg"]))
        self.assertEqual(rec["forras_nevek"], {"ATTCHMNTS - photos/IMG_1.jpg": "IMG_1.jpg"})
        self.assertEqual(rec["sha256"]["ATTCHMNTS - photos/IMG_1.jpg"], fuzet.sha256(cel))
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(len(v["mozgatva"]), 1)
        self.assertTrue(p.is_file() and not cel.exists())                                   # vissza a forrásmappába

    def test_utkozo_nev_uj_nevvel_es_a_visszaut_az_eredeti_nevre(self):
        (self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").write_bytes(b"masik")
        p = self.foto()
        with self.assertRaises(vaultio.Conflict):
            self.G.ir(self.keres(self.mozgat(p), self.csere(J1)))
        self.assertTrue(p.is_file())
        r = self.G.ir(self.keres(self.mozgat(p, "IMG_1 (2).jpg"), self.csere(J1, "IMG_1 (2).jpg"), tetel="t2"))
        self.repo.undo_commit(r["sha"])
        binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertTrue(p.is_file())                                                        # a forrásbeli nevén
        self.assertEqual((self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").read_bytes(), b"masik")

    def test_tiltott_forrasok_es_celok(self):
        kint = papir_kep(Path(self._t.name) / "mashol" / "IMG_1.jpg")
        for m, hiba in ((self.mozgat(kint), vaultio.Invalid),                             # nem figyelt mappából
                        ({**self.mozgat(self.foto()), "ut": "T01/IMG_1.jpg"}, vaultio.Invalid),   # nem a cél-mappába
                        ({**self.mozgat(self.foto()), "sha256": "0" * 64}, vaultio.Conflict),
                        ({**self.mozgat(self.foto()), "ut": "ATTCHMNTS - photos/a.md"}, vaultio.Invalid)):
            with self.subTest(m=m["ut"]), self.assertRaises(hiba):
                self.G.ir(self.keres(m, self.csere(J1)))
        with self.assertRaises(vaultio.Invalid):                                            # egyedül nem mozog (I40)
            self.G.ir(self.keres(self.mozgat(self.foto())))
        vaultbeli = self.v / "ATTCHMNTS - photos" / "IMG_9.jpg"
        vaultbeli.write_bytes(b"x")
        with self.assertRaises(vaultio.Invalid):                                            # a vaultbeli média nem mozog (47(e))
            self.G.ir(self.keres({"tipus": "mozgat", "forras": str(vaultbeli), "ut": "ATTCHMNTS - photos/IMG_8.jpg",
                                  "sha256": fuzet.sha256(vaultbeli)}, self.csere(J1)))

    def test_irasi_hiba_utan_a_foto_visszakoltozik(self):
        p = self.foto()
        with mock.patch.object(gepi_iras.GepiIras, "_fajl_ir", side_effect=OSError("lemez")):
            with self.assertRaises(OSError):
                self.G.ir(self.keres(self.mozgat(p), self.csere(J1)))
        self.assertTrue(p.is_file())
        self.assertFalse((self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").exists())
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())

    def test_megszakadt_mozgas_helyreall(self):
        p = self.foto()
        cel = self.v / "ATTCHMNTS - photos" / "IMG_1.jpg"
        sha = fuzet.sha256(p)
        os.rename(p, cel)
        d = self.cfg.path("run") / gepi_iras.NAPLO
        (d / "eredeti").mkdir(parents=True)
        (d / "terv.json").write_text(json.dumps({"kor": "FUZET-20261007-230000", "tetel": "t9", "feladat": None, "fajlok": [],
                                                 "mozgasok": [{"ut": "ATTCHMNTS - photos/IMG_1.jpg",
                                                               "lemez": "ATTCHMNTS - photos/IMG_1.jpg", "forras": str(p),
                                                               "sha256": sha, "masolat": False}]}), encoding="utf-8")
        uz = gepi_iras.helyreallit(self.cfg)
        self.assertIn("was restored", uz[0])
        self.assertTrue(p.is_file() and not cel.exists())

    @csak_darwin
    def test_proba_masol_a_forras_erintetlen(self):
        p = self.foto()
        r = self.G.ir(self.keres(self.mozgat(p), self.csere(J1), proba=True))
        self.assertTrue(r["proba"] and p.is_file())
        self.assertTrue((Path(r["proba_mappa"]) / self.v.name / "ATTCHMNTS - photos" / "IMG_1.jpg").is_file())
        self.assertFalse((self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").exists())


class AllapotTest(_Core):
    def test_l20_bekotes_visszavonva_atkotes_regi_kotes(self):
        fuzet.allapot_frissit(self.cfg, "a" * 64, kep="IMG_1.jpg", allapot="bekotve", bekotve=[J1], commit="1234567abc", kor="FUZET-1")
        fuzet.allapot_frissit(self.cfg, "b" * 64, kep="IMG_2.jpg", allapot="bekotve", bekotve=[J2], commit="7654321abc",
                              ellenorzes=[{"commit": "abcdef0123", "kor": "FUZETELL-1", "regi": [J1], "uj": [J2]}])
        self.assertEqual(fuzet.visszavonas_utan(self.cfg, ["1234567abc"]), 1)
        self.assertEqual(fuzet.visszavonas_utan(self.cfg, ["abcdef0"]), 1)
        st = fuzet.allapot_betolt(self.cfg)
        self.assertEqual(st["a" * 64]["allapot"], "visszavonva")
        self.assertEqual((st["b" * 64]["bekotve"], st["b" * 64]["allapot"]), ([J1], "bekotve"))
        self.assertTrue(st["b" * 64]["ellenorzes"][0]["visszavonva"])
        self.assertEqual(fuzet.visszavonas_utan(self.cfg, ["abcdef0"]), 0)                  # idempotens
        self.assertEqual(fuzet.visszavonas_utan(self.cfg, ["12"]), 0)                       # rövid sha semmire nem illik

    def test_ocr_szoveg_az_indexnek(self):
        fuzet.ocr_ir(self.cfg, "IMG_1.jpg", "c" * 64, 123, "Természetesen, itt az átirat:\nPitagorasz-tétel")
        self.assertEqual(fuzet.ocr_szoveg(self.cfg, "img_1.JPG", 123), "Pitagorasz-tétel")
        self.assertEqual(fuzet.ocr_szoveg(self.cfg, "IMG_1.jpg", 124), "")
        self.assertEqual(fuzet.ocr_szoveg(self.cfg, "IMG_2.jpg", 123), "")

    def test_a_foto_atirata_kereshető_az_indexben(self):
        from tests.index_segedek import index_indit
        p = papir_kep(self.v / "ATTCHMNTS - photos" / "IMG_7.jpg")
        fuzet.ocr_ir(self.cfg, "IMG_7.jpg", fuzet.sha256(p), p.stat().st_size, "Pitagorasz zebrakockatétel")
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        utak = [t["ut"] for t in ix.kereses("zebrakockatétel")["talalatok"]]
        self.assertEqual(utak, ["ATTCHMNTS - photos/IMG_7.jpg"])
        self.assertNotIn("zebrakockatétel", (self.v / J1).read_text(encoding="utf-8"))   # a vaultba nem kerül

    def test_figyelt_mappak_a_vaulton_kivul(self):
        cfg, _, v = alg_core(self._t.name + "/b", MOS_FUZET_BEJOVO=str(self.bejovo))
        cfg.data.setdefault("fuzet", {})["mappak"] = [str(v / "belul"), str(Path(self._t.name) / "kulso"), "relativ"]
        self.assertEqual(fuzet.figyelt_mappak(cfg), [Path(os.path.realpath(self.bejovo)),
                                                      Path(os.path.realpath(Path(self._t.name) / "kulso"))])


class HamisModellek:
    """A `fuzet.modell.Modellek` helyett: feladatonként előre megadott válaszok; a hívások naplózva."""

    def __init__(self, valaszok: dict, proba: bool = False):
        self.valaszok, self.proba = valaszok, proba
        self.hivasok: list[tuple] = []
        self.kifejezett = {}

    utotag = ""

    def modell_nev(self, feladat):
        return "hamis-" + feladat + self.utotag

    def kerdez(self, feladat, prompt, kepek=None, max_tokens=256, beallitas_feladat=None):
        self.hivasok.append((feladat, prompt[:40], len(kepek or [])))
        v = self.valaszok[feladat]
        return (v(prompt) if callable(v) else v), {"feladat": feladat, "modell": "hamis-" + feladat, "proba": self.proba}


class LancTest(_Core):
    def setUp(self):
        super().setUp()
        from tests.grafikon_segedek import SzolgaltatasKliens
        self.kliens = SzolgaltatasKliens(self.G, self.V)
        p = mock.patch.object(L, "gepi_kliens", self.kliens)
        p.start()
        self.addCleanup(p.stop)
        self.d9 = gepi_iras.GepiIras._d9
        d = mock.patch.object(gepi_iras.GepiIras, "_d9", lambda s, k: None)     # a hamis modell „kalibrált” (a D9 külön teszt)
        d.start()
        self.addCleanup(d.stop)
        self.M = HamisModellek({"fuzet_fejezet": "TANTÁRGY: Matematika\nCÍMEK: Pitagorasz\nTARTALOM: befogó\nFEJEZET: M10",
                                "ocr_kezi": "Természetesen, itt az átirat:\n$a^2+b^2=c^2$ befogók",
                                "fuzet_valaszto": "2"})

    def lanc(self, **kw):
        return L.Lanc(self.cfg, modellek=self.M, katalogus=Katalogus(KAT), log=lambda s: None, **kw)

    def test_kor_beir_mozgat_allapot_index_es_nem_ismetel(self):
        p = self.foto()
        r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"bekotve": 1}, r)
        t = (self.v / J2).read_text(encoding="utf-8")
        self.assertIn("## Füzet\n\n![[IMG_1.jpg]]\n> [!info]- Képletek a fotóról\n> $$a^2+b^2=c^2$$\n", t)
        self.assertTrue((self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").is_file() and not p.exists())
        sha = r["fotok"][0]["sha256"]
        st = fuzet.allapot_betolt(self.cfg)[sha]
        self.assertEqual((st["allapot"], st["bekotve"], st["kep"]), ("bekotve", [J2], "IMG_1.jpg"))
        self.assertEqual(fuzet.ocr_szoveg(self.cfg, "IMG_1.jpg", (self.v / "ATTCHMNTS - photos/IMG_1.jpg").stat().st_size),
                         "$a^2+b^2=c^2$ befogók")
        self.assertEqual([h[0] for h in self.M.hivasok], ["fuzet_fejezet", "ocr_kezi", "fuzet_valaszto"])
        self.assertTrue(Path(self.cfg.path("runs") / "fuzet" / f"{r['kor']}.json").is_file())
        n = len(self.M.hivasok)                    # a második kör: nincs új fotó (a fotó a vaultban van)
        self.assertEqual(self.lanc().futtat()["eredmeny"], {})
        self.assertEqual(len(self.M.hivasok), n)
        # L19/L20: a tétel visszavonása — a fotó vissza a forrásba, az állapot „visszavonva”, a lánc nem veszi újra
        self.repo.undo_commit(st["commit"])
        binaris_naplo.visszavonas_utan(self.cfg, self.repo, st["commit"], None, log=lambda s: None)
        fuzet.visszavonas_utan(self.cfg, [st["commit"]])
        self.assertTrue(p.is_file())
        self.assertEqual(fuzet.allapot_betolt(self.cfg)[sha]["allapot"], "visszavonva")
        self.assertEqual(self.lanc().futtat()["eredmeny"], {})

    def test_gyorsitotarbol_folytat(self):
        self.foto()
        with mock.patch.object(L.Lanc, "ir", side_effect=RuntimeError("megállt")):
            self.lanc().futtat()
        n = len(self.M.hivasok)
        self.assertEqual(self.lanc().futtat()["eredmeny"], {"bekotve": 1})
        self.assertEqual(len(self.M.hivasok), n)                                            # nem kérdezett újra

    def test_aktiv_jegyzet_mod_valaszto_nelkul(self):
        self.foto()
        r = self.lanc(cel=J1).futtat()
        self.assertEqual(r["eredmeny"], {"bekotve": 1})
        self.assertIn("![[IMG_1.jpg]]", (self.v / J1).read_text(encoding="utf-8"))
        self.assertEqual([h[0] for h in self.M.hivasok], ["ocr_kezi"])

    def test_allo_foto_forgatas_probaval(self):
        self.foto(allo=True)
        self.M.valaszok["fuzet_fejezet"] = lambda prompt: (
            "háromszög pitagorasz befogó" if prompt == modszer.FORGATAS_PROMPT and self._n() == 2 else
            "xyzw" if prompt == modszer.FORGATAS_PROMPT else
            "TANTÁRGY: Matematika\nCÍMEK: Pitagorasz\nTARTALOM: befogó\nFEJEZET: M10")
        r = self.lanc().futtat()
        self.assertEqual(r["fotok"][0]["forgatas"], 90)                                     # a második próba (+90°) olvasható
        self.assertEqual(sum(1 for h in self.M.hivasok if h[1] == modszer.FORGATAS_PROMPT[:40]), 3)

    def _n(self):
        return sum(1 for h in self.M.hivasok if h[1] == modszer.FORGATAS_PROMPT[:40])

    def test_utkozo_nev_a_celmappaban(self):
        (self.v / "ATTCHMNTS - photos" / "IMG_1.jpg").write_bytes(b"masik")
        self.foto()
        r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"bekotve": 1})
        self.assertTrue((self.v / "ATTCHMNTS - photos" / "IMG_1 (2).jpg").is_file())
        self.assertIn("![[IMG_1 (2).jpg]]", (self.v / J2).read_text(encoding="utf-8"))

    def test_proba_modell_elesben_nem_ir(self):
        self.foto()
        self.M.proba = True
        with mock.patch.object(gepi_iras.GepiIras, "_d9", self.d9):
            r = self.lanc().futtat()
        self.assertEqual(r["eredmeny"], {"hiba": 1})
        self.assertIn("próba", r["fotok"][0]["uzenet"])

    def test_ellenorzo_kor_atkot_a_callouttal(self):
        self.foto()
        self.lanc().futtat()
        self.M.valaszok["fuzet_valaszto"] = "1"
        self.M.utotag = "-eros"                     # az ellenőrzés más (erősebb) modellel: a gyorsítótár kulcsa más
        r = self.lanc().ellenoriz()
        self.assertEqual(r["eredmeny"], {"atkotve": 1})
        self.assertNotIn("IMG_1.jpg", (self.v / J2).read_text(encoding="utf-8"))
        self.assertIn("![[IMG_1.jpg]]\n> [!info]- Képletek a fotóról\n> $$a^2+b^2=c^2$$", (self.v / J1).read_text(encoding="utf-8"))
        sha, st = next(iter(fuzet.allapot_betolt(self.cfg).items()))
        self.assertEqual(st["bekotve"], [J1])
        commit = st["ellenorzes"][-1]["commit"]
        self.repo.undo_commit(commit)
        fuzet.visszavonas_utan(self.cfg, [commit])                                          # L20: a régi kötés áll vissza
        self.assertEqual(fuzet.allapot_betolt(self.cfg)[sha]["bekotve"], [J2])
        self.assertEqual(self.lanc().ellenoriz()["eredmeny"], {"atkotve": 1})


class FigyeloTest(_Core):
    class Sor:
        def __init__(self):
            self.sorok: list[dict] = []

        def list(self, limit=40):
            return self.sorok

        def submit(self, tipus, p):
            self.sorok.append({"id": f"F-{len(self.sorok)}", "tipus": tipus, "allapot": "sorban"})
            return self.sorok[-1]

    def test_a_figyelo_alapbol_nem_indul(self):
        """80(a), 80(h): `[fuzet] figyelo_be` alapból hamis — nincs szál, és a beragadt fotót sem próbálja újra."""
        self.assertIs(self.cfg.section("fuzet").get("figyelo_be"), False)
        q = self.Sor()
        f = fuzet_figyelo.Figyelo(self.cfg, q, indulasi_kesleltetes_mp=0, ora=lambda: time.time() + 3600)
        self.foto()
        f.indit()
        self.assertIsNone(f._szal)
        self.assertIn("ki van kapcsolva", f.egy_kor()["ok"])
        self.assertEqual(q.sorok, [])

    def test_uj_foto_bekuldes_kapcsolo_es_nyugalom(self):
        q = self.Sor()
        most = [time.time()]
        self.cfg.data.setdefault("fuzet", {})["figyelo_be"] = True
        f = fuzet_figyelo.Figyelo(self.cfg, q, ora=lambda: most[0])
        self.foto()
        most[0] += 3600
        for be in (False, True):
            vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": be})
            self.assertIn("ki van kapcsolva", f.egy_kor()["ok"])
            f.indit()
            self.assertIsNone(f._szal)
            self.assertEqual(q.sorok, [])  # régi figyelo_be mellett sem indít tartalomgenerálást

    def test_feladattipusok(self):
        fuzet_feladat.regisztral()
        t = tasks.REGISTRY["fuzet_automatikus"]
        self.assertTrue(t.automatikus and t.graceful_stop and t.resources == {"modell", "vault"})
        lepes, _, _ = tasks.REGISTRY["fuzet_lanc"].plan(self.cfg, {"cel": J1, "proba": True, "csoport": "cs1"}, "/s")
        self.assertEqual(lepes[0].argv[3:], ["lanc", "--stop-fajl", "/s", "--proba", "--cel", J1, str(self.bejovo / "cs1")])
        for rossz in ({"cel": "../x.md"}, {"cel": "nincs.md"}, {"csoport": "../a"}, {"max": 0}, {"proba": "igen"}):
            with self.subTest(rossz), self.assertRaises(tasks.Invalid):
                tasks.REGISTRY["fuzet_lanc"].plan(self.cfg, rossz, "/s")
        with self.assertRaises(tasks.Invalid):
            t.plan(self.cfg, {"cel": J1}, "/s")


class ApiTest(_Core):
    class App:
        def __init__(self, cfg):
            self.cfg = cfg

            class W:
                @staticmethod
                def biztosit():
                    return "http://worker"
            self.worker = W()

    def test_bejovo_feltoltes(self):
        app = self.App(self.cfg)
        b = base64.b64encode(b"\xff\xd8kep").decode()
        r1 = fuzet_api.bejovo(app, {"nev": "../IMG 1.JPG", "adat": b, "csoport": "cs"})
        r2 = fuzet_api.bejovo(app, {"nev": "IMG 1.JPG", "adat": b, "csoport": "cs"})
        self.assertEqual((r1["nev"], r2["nev"]), ("IMG 1.JPG", "IMG 1 (2).JPG"))
        self.assertTrue((self.bejovo / "cs" / "IMG 1.JPG").is_file())
        for rossz in ({"nev": "a.txt", "adat": b}, {"nev": "a.jpg", "adat": "!!"}, {"nev": "a.jpg", "adat": b, "csoport": "../x"}):
            with self.subTest(rossz), self.assertRaises(HttpError):
                fuzet_api.bejovo(app, rossz)
        self.assertEqual(fuzet_api.allapot(app)["figyelt_mappak"][0]["ut"], str(Path(os.path.realpath(self.bejovo))))

    def test_keplet_ocr(self):
        app = self.App(self.cfg)

        class Mod:
            PROMPT = "képlet"
            ARANY = {"max_token": 200}
            jelolt = staticmethod(lambda s: s.strip("`"))
        hivas = []

        def chat(u, messages, **kw):
            hivas.append(kw)
            return {"choices": [{"message": {"content": "$$\\frac{a}{b}$$"}}], "modell": "glm_ocr", "proba": False}
        with mock.patch.object(fuzet_api, "_keplet_modul", lambda cfg: Mod):
            def vagolap(cel):
                cel.parent.mkdir(parents=True, exist_ok=True)
                cel.write_bytes(b"png")
                return True
            r = fuzet_api.keplet_ocr(app, {}, vagolap=vagolap, chat=chat)
            self.assertEqual((r["latex"], r["modell"]), ("\\frac{a}{b}", "glm_ocr"))
            self.assertEqual((hivas[0]["feladat"], hivas[0]["mod"]), ("ocr_keplet", "interaktiv"))
            self.assertEqual(list((self.cfg.path("tmp") / "keplet-ocr").iterdir()), [])        # a kép nem marad
            with self.assertRaises(HttpError) as cm:
                fuzet_api.keplet_ocr(app, {}, vagolap=lambda cel: False, chat=chat)
            self.assertEqual(cm.exception.code, 404)

    def test_keplet_prompt_az_evale(self):
        m = fuzet_api._keplet_modul(type("C", (), {"path": lambda self, k: REPO / "modulok"})())
        self.assertIn("LaTeX", m.PROMPT)


class FelfuggesztesTest(unittest.TestCase):
    """9. pont: az Asszisztens kikapcsolása a futó automatikus feladatot a tétel végén megállítja és a sorba teszi vissza; a
    sorban álló felfüggesztve vár; visszakapcsoláskor folytatódik."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])

    def test_felfuggesztes_es_folytatas(self):
        enged = Path(self._t.name) / "enged"
        kod = ("import os, time\nprint('indul', flush=True)\n"
               f"while not os.path.exists('STOP') and not os.path.exists({str(enged)!r}): time.sleep(0.02)\n")

        def plan(cfg, p, stop):
            return [tasks.Step("l", [sys.executable, "-c", kod.replace("STOP", stop)], "/")], "", []
        tasks.register(tasks.TaskType("t_auto", "t_auto", plan, frozenset({"vault"}), True, automatikus=True))
        be = {"v": True}
        q = tasks.Queue(self.cfg, start_delay=0, admit=lambda t: not t.automatikus or be["v"])
        self.addCleanup(q.close)

        def var(fid, allapot, mp=20):
            t0 = time.time()
            while q.get(fid)["allapot"] != allapot and time.time() - t0 < mp:
                time.sleep(0.05)
            return q.get(fid)["allapot"]
        fid = q.submit("t_auto", {})["id"]
        self.assertEqual(var(fid, "fut"), "fut")
        be["v"] = False
        self.assertEqual(q.automatikus_felfuggeszt(), [fid])
        self.assertEqual(var(fid, "sorban"), "sorban")
        time.sleep(0.5)
        self.assertEqual(q.get(fid)["allapot"], "sorban")                                   # felfüggesztve, nem indul
        be["v"] = True
        self.assertEqual(var(fid, "fut"), "fut")
        enged.touch()
        self.assertEqual(var(fid, "kesz"), "kesz")


if __name__ == "__main__":
    unittest.main()
