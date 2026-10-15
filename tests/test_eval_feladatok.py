"""C18: az aranyhalmaz-feladatok (`modulok/eval/*/feladat.py`) — épség, tételek álvaulton, és a pontozók
jó, illetve kézzel elrontott kimeneten. A valódi vaulthoz és `var/`-hoz egyik teszt sem nyúl."""
import json
import sys
import unittest
from unittest import mock
from pathlib import Path

from tests.eval_segedek import EVAL, eval_cfg, feladat, rekord
from tests.helpers import ir, tmpdir

FELADATOK = ("ocr_kezi", "fuzet_fejezet", "ocr_keplet", "atirat", "szoveg", "kviz", "matek", "matek_ellenorzo", "grafikon",
             "beagyazas", "rerank", "matek_cas", "fuzet_valaszto", "fuzet_forgatas", "tema", "kotes", "kifejtes",
             "osszefoglal_kijeloles")
ROUTER = {"ocr_kezi", "ocr_keplet", "atirat", "szoveg", "kviz", "matek", "matek_ellenorzo", "beagyazas", "rerank",
          "fuzet_fejezet", "fuzet_valaszto", "matek_cas", "grafikon", "tema", "kotes", "kifejtes",
          "osszefoglal_kijeloles"}   # a grafikon a C35b óta, a tema/kotes a C20b óta, a két kijelölés-mód a J4 óta


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = eval_cfg(self._t.name)

    def f(self, nev):
        return feladat(self.cfg, nev)


class SzerzodesTest(_Alap):
    def test_minden_feladat_betoltheto_es_a_kulcsa_egyedi(self):
        kulcsok = {}
        for nev in FELADATOK:
            m = self.f(nev)
            self.assertTrue(m.VERZIO.startswith(nev + "-v"), m.VERZIO)
            kulcsok.setdefault(getattr(m, "ROUTER_FELADAT", nev), []).append(nev)
            self.assertEqual(m.pontoz([])["pontszam"], 0.0, nev)            # üres futás nem dob hibát
        self.assertTrue(all(len(v) == 1 for v in kulcsok.values()), kulcsok)  # a tábla kulcsa (feladat, modell)
        router = set(self.cfg.section("router")["feladatok"])
        self.assertEqual({k for k in kulcsok if k in router}, ROUTER)

    def test_vazlat_utotag_a_jovahagyasig(self):
        from kozos import arany as A
        self.assertEqual(A.verzio({"verzio": "v1", "allapot": "vazlat"}), "v1-vazlat")
        self.assertEqual(A.verzio({"verzio": "v2", "allapot": "jovahagyott"}), "v2")

    def test_az_eval_fajlokban_nincs_legacy_vagy_beegetett_ut(self):
        from core import doctor
        for p in EVAL.rglob("*"):
            if p.suffix in (".py", ".json") and p.is_file():
                s = p.read_text(encoding="utf-8")
                self.assertIsNone(doctor.LEGACY_MINTA.search(s), p)
                self.assertNotIn("/Volumes/", s, p)


class FuzetTest(_Alap):
    def _fotok(self):
        from PIL import Image
        a = json.loads((EVAL / "ocr_kezi" / "arany.json").read_text(encoding="utf-8"))
        mappa = self.vault / a["fotomappa"]
        mappa.mkdir()
        for i, f in enumerate(a["fotok"]):
            Image.new("RGB", (64, 48) if i % 2 else (48, 64), "white").save(mappa / f["foto"])
        return a

    def test_tetelek_alvaulton(self):
        a = self._fotok()
        t = list(self.f("ocr_kezi").tetelek(self.cfg))
        self.assertEqual(len(t), 97)
        self.assertEqual(len(a["fotok"]), 97)
        self.assertEqual({len(x["keres"]["images"]) for x in t}, {1, 2})      # fekvő fotó: két oldalkép
        self.assertTrue(all(Path(p).is_file() and str(self.cfg.path("tmp")) in p for x in t for p in x["keres"]["images"]))
        with self.assertRaisesRegex(FileNotFoundError, "fuzet_forgatas"):       # C21: az álló papír iránya a forgatás-próbából
            list(self.f("fuzet_fejezet").tetelek(self.cfg))
        fg = self.f("fuzet_forgatas")
        forg = list(fg.tetelek(self.cfg))
        self.assertEqual(len(forg), 3 * 49)                                       # a 49 álló fotó × 3 irány
        self.assertEqual({t["keres"]["max_tokens"] for t in forg}, {60})
        ut = self.cfg.path("runs") / "eval" / fg.FORGATO / "fuzet_forgatas.jsonl"
        ut.parent.mkdir(parents=True)
        ut.write_text("\n".join(json.dumps({"id": t["id"], "valasz": "háromszög" if t["id"].endswith("#90") else "xyz"},
                                         ensure_ascii=False) for t in forg), encoding="utf-8")
        fej = list(self.f("fuzet_fejezet").tetelek(self.cfg))
        self.assertEqual(len(fej), 97)
        self.assertIn("M10 – Geometria", fej[0]["keres"]["messages"][0]["content"])
        allo = [t for t in fej if t["vart"]["forgatas"] is not None]
        self.assertEqual({t["vart"]["forgatas"] for t in allo}, {90})
        self.assertTrue(all(p.endswith("-r90.jpg") for t in allo for p in t["keres"]["images"]))
        kep = list(self.f("ocr_keplet").tetelek(self.cfg))
        self.assertGreaterEqual(len(kep), 120)
        self.assertEqual(len({x["id"] for x in kep}), len(kep))

    def test_forgatas_pontozo_a_kezi_iranyokkal(self):
        fg = self.f("fuzet_forgatas")
        rek = [{"vart": {"foto": "IMG_1307.JPG", "fok": f}, "valasz": "A háromszögek szögei" if f == -90 else "qqq"}
               for f in (-90, 90, 0)]
        rek += [{"vart": {"foto": "IMG_1545.JPG", "fok": f}, "valasz": "A háromszögek szögei" if f == 90 else "qqq"}
                for f in (-90, 90, 0)]
        e = fg.pontoz(rek)
        self.assertEqual((e["foto"], e["kezi"], e["kezi_egyezik"], e["pontszam"]), (2, 2, 1, 0.5))
        self.assertEqual(e["dontesek"], {"IMG_1307.JPG": -90, "IMG_1545.JPG": 90})

    def test_hianyzo_foto_hiba(self):
        with self.assertRaises(FileNotFoundError):
            list(self.f("ocr_kezi").tetelek(self.cfg))

    def test_valaszto_a_legacy_2_lepese_az_olvaso_soraibol(self):
        """C19 (T052): a `fuzet_valaszto` az olvasó `fuzet_fejezet` soraiból a legacy zárt listáját és promptját adja; a bíró a
        kötési arany (szigorú: `helyes`); értelmezhetetlen válasznál a szóalapú tartalék dönt."""
        m = self.f("fuzet_valaszto")
        with self.assertRaisesRegex(FileNotFoundError, "1. lépés"):
            list(m.tetelek(self.cfg))
        a = json.loads((EVAL / "ocr_kezi" / "arany.json").read_text(encoding="utf-8"))
        ut = self.cfg.path("runs") / "eval" / m.OLVASO / "fuzet_fejezet.jsonl"
        ut.parent.mkdir(parents=True)
        olv = ("TANTÁRGY: Matematika\nCÍMEK: háromszög szögei, külső szög\nTARTALOM: A háromszög belső és külső szögei, "
               "szögösszeg.\nFEJEZET: M10")
        sorok = [{"id": f["foto"], "valasz": "", "beallitas": "regi"} for f in a["fotok"]]       # az üres sort felülírja a következő
        sorok += [{"id": f["foto"], "valasz": olv, "beallitas": "x"} for f in a["fotok"]]
        ut.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in sorok), encoding="utf-8")
        t = list(m.tetelek(self.cfg))
        self.assertEqual(len(t), 97)
        elso = t[0]
        self.assertEqual(elso["id"], "IMG_1289.JPG")
        jl = elso["vart"]["jeloltek"]
        self.assertTrue(all(u.startswith("M") for u in jl))
        self.assertIn("M10 - Geometria (szintetikus)/Elmélet/01 - A háromszögek alapismeretei.md", jl)
        szoveg = elso["keres"]["messages"][0]["content"]
        self.assertIn("1. Matematika › Geometria (szintetikus) › ", szoveg)
        self.assertTrue(szoveg.endswith("Csak a legjobban illő jegyzet sorszámát írd le, semmi mást."))
        self.assertEqual(elso["keres"]["max_tokens"], 24)
        i = jl.index(elso["vart"]["helyes"][0]) + 1
        e = m.pontoz([{"id": "a", "vart": elso["vart"], "valasz": str(i)},
                      {"id": "b", "vart": elso["vart"], "valasz": "nem tudom"},
                      {"id": "c", "vart": elso["vart"], "valasz": f"{1 if i != 1 else 2}"}])
        self.assertEqual((e["szam"]["szigoru"] >= 1, e["szam"]["tartalek"], e["a_listan"]), (True, 1, 1.0))
        self.assertEqual(m.valasztott("A háromszögek alapismeretei", jl), jl.index(elso["vart"]["helyes"][0]))
        self.assertTrue(m.formatum_ok("3.", elso["vart"]))
        self.assertFalse(m.formatum_ok("semmi", elso["vart"]))

    def test_lexikai_biro_jo_atiraton_talal_felreolvasotton_bukik(self):
        m = self.f("ocr_kezi")
        v = {"foto": "IMG_1392.JPG", "elfogadhato": [],
             "helyes": ["M03 - Algebra/Elmélet/14 - A másodfokú egyenlet megoldóképlete.md"]}
        jo = "A másodfokú egyenlet megoldóképlete. ax²+bx+c=0, a diszkrimináns D = b² − 4ac, két valós gyök."
        rossz = "Petőfi Sándor forradalmi látomásköltészete, A XIX. század költői, az apostol-szerep."
        e = m.pontoz([{"id": "a", "vart": v, "valasz": jo}])
        self.assertEqual((e["pontszam"], e["fejezet1"], e["targy1"]), (1.0, 1.0, 1.0))
        e = m.pontoz([{"id": "a", "vart": v, "valasz": rossz}, {"id": "b", "vart": v, "valasz": None}])
        self.assertEqual((e["pontszam"], e["targy1"], e["ures"]), (0.0, 0.0, 0.5))
        self.assertEqual(len(e["rossz"]), 2)

    def test_biro_plafonja_a_kezi_leirasokon(self):
        e = self.f("ocr_kezi").plafon()
        self.assertGreaterEqual(e["szam"]["jegyzet5"], 90)                    # a bíró a jó leírásból kikeresi a jegyzetet

    def test_keplet_talalat_az_atiratban(self):
        m = self.f("ocr_kezi")
        kepletek = ["x_{1,2}=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}", "D=b^2-4ac"]
        jo = "Megoldóképlet: $x_{1,2} = \\dfrac{-b \\pm \\sqrt{b^{2}-4ac}}{2a}$ ahol $D = b^2 - 4ac$"
        self.assertEqual(m.keplet_talalat(jo, kepletek), 1.0)
        self.assertEqual(m.keplet_talalat("$x = \\frac{b + \\sqrt{b - 4c}}{a}$ és semmi más", kepletek), 0.0)

    def test_fejezet_valasz(self):
        m = self.f("fuzet_fejezet")
        kodok = {f["kod"]: f["nev"] for f in m.fejezetek()}
        v = {"helyes": ["M03 - Algebra/Elmélet/14 - x.md"], "elfogadhato": ["M05 - y/Elmélet/06 - z.md"], "kodok": kodok}
        jo = "TANTÁRGY: Matematika\nCÍMEK: megoldóképlet\nTARTALOM: …\nFEJEZET: M03"
        e = m.pontoz([{"id": "a", "vart": v, "valasz": jo}, {"id": "b", "vart": v, "valasz": jo.replace("M03", "M05, M10")},
                      {"id": "c", "vart": v, "valasz": jo.replace("M03", "F02")}, {"id": "d", "vart": v, "valasz": "nem tudom"}])
        self.assertEqual((e["szam"]["fejezet"], e["szam"]["fejezet_elbiralt"], e["szam"]["targy"], e["szam"]["nincs_kod"]),
                         (1, 2, 2, 1))
        self.assertEqual(m.szetszed("FEJEZET: Algebra", kodok)["fejezetek"], ["M03"])            # név kód helyett

    def test_keplet_pontozo_elirt_kepleten_bukik(self):
        m = self.f("ocr_keplet")
        v = "\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}"
        jo = m.pontoz([{"id": "a", "vart": v, "valasz": "$$\\dfrac{-b \\pm \\sqrt{b^{2}-4ac}}{2a}$$"}])
        self.assertEqual((jo["pontszam"], jo["pontos"]), (1.0, 1.0))
        rossz = m.pontoz([{"id": "a", "vart": v, "valasz": "\\frac{-b+\\sqrt{b^2+4ac}}{2}"},
                          {"id": "b", "vart": v, "valasz": None}])
        self.assertEqual((rossz["pontos"], rossz["jo"]), (0.0, 0.0))
        self.assertLess(rossz["pontszam"], 0.5)
        self.assertEqual(len(rossz["rossz"]), 2)
        # C19 rétegzett minta: a tömbös binomiális együttható a \binom-mal azonos
        tomb = "$$(\\begin{array}{c} 4 \\\\ 2 \\end{array}) \\cdot (\\begin{array}{c} 2 8 \\\\ 4 \\end{array})$$"
        b = m.pontoz([{"id": "a", "vart": "\\binom{4}{2}\\cdot\\binom{28}{4}", "valasz": tomb}])
        self.assertEqual(b["pontos"], 1.0)
        self.assertEqual(m.binom_alak("\\begin{pmatrix} 5 \\\\ 2 \\end{pmatrix}"), "\\binom{5}{2}")


class AtiratTest(_Alap):
    JEGYZET = ("---\nTags:\n  - History\n---\n\n# Cím — Átirat\n\nEz a jegyzet a médiaforrás szövegrétege.\n\n"
               "Az átirat **nem tartalmaz időbélyeget**.\n\nSulla (ejtsd: Szulla) diktátorsága után zavaros idők "
               "következtek. Sok rabszolga is csatalakozott.\n\nKr. e. 71-ben consullá választották.\n")

    def test_arany_szoveg_es_tetelek(self):
        m = self.f("atirat")
        s = m.arany_szoveg(self.JEGYZET, [{"mit": "csatalakozott", "mire": "csatlakozott"}])
        self.assertTrue(s.startswith("Sulla diktátorsága"))
        self.assertNotIn("ejtsd", s)
        self.assertIn("csatlakozott", s)
        with self.assertRaises(ValueError):
            m.arany_szoveg(self.JEGYZET, [{"mit": "nincs ilyen", "mire": "x"}])
        with self.assertRaises(FileNotFoundError):                              # az álvaultban nincs meg a jegyzet
            list(m.tetelek(self.cfg))
        self.assertEqual(len(m.ARANY["videok"]), 2)

    def test_megvaltozott_jegyzet_megallitja_a_merest(self):
        m = self.f("atirat")
        for v in m.ARANY["videok"]:
            ir(self.vault, v["atirat"], self.JEGYZET)
            ir(self.vault, v["media"], b"x", "wb")
        with self.assertRaisesRegex(ValueError, "megváltozott"):
            list(m.tetelek(self.cfg))

    def test_pontozo(self):
        m = self.f("atirat")
        v = "Sulla diktátorsága után zavaros idők következtek. Kr. e. 71-ben consullá választották, és ötszáz hajót kapott."
        jo = m.pontoz([{"id": "v1", "vart": v, "valasz": "Sulla diktátorsága után zavaros idők következtek. "
                        "Krisztus előtt 71-ben consullá választották, és 500 hajót kapott."}])
        self.assertEqual((jo["wer"], jo["pontszam"]), (0.0, 1.0))                                  # írásmód-változat nem hiba
        self.assertEqual(m.pontoz([{"id": "v1", "vart": v, "valasz": v}])["irasjel_f1"], 1.0)
        self.assertLess(m.pontoz([{"id": "v1", "vart": v, "valasz": v.replace(".", "").replace(",", "")}])["irasjel_f1"], 0.01)
        rossz = m.pontoz([{"id": "v1", "vart": v, "valasz": "szulla diktátorsága után idők következtek"}])   # kihagyott mondat
        self.assertGreater(rossz["wer"], 0.5)
        self.assertLess(rossz["pontszam"], 0.5)
        self.assertEqual(m.pontoz([{"id": "v1", "vart": v, "valasz": None}])["pontszam"], 0.0)


class SzovegTest(_Alap):
    def test_arany_epseg(self):
        m = self.f("szoveg")
        self.assertEqual(len(m.ARANY["jegyzetek"]), 20)
        self.assertEqual(m.epseg(), [])                                         # minden kulcsrész és forrásmondat megvan
        for j in m.ARANY["jegyzetek"]:
            self.assertTrue(5 <= len(j["kulcsreszek"]) <= 8, j["id"])
            self.assertTrue(8 <= len(j["tenyek"]) <= 16, j["id"])
        self.assertEqual(len(list(m.tetelek(self.cfg))), 40)

    def _ossz(self, m, jid, csere=None):
        k = m.jegyzet(jid)["kulcsreszek"]
        return json.dumps([{"allitas": x["idezet"] if csere is None else x["megnevezes"],
                            "idezet": x["idezet"] if csere is None else csere(x)} for x in k], ensure_ascii=False)

    def test_osszefoglalas_jo_es_elrontott(self):
        m = self.f("szoveg")
        jo = m.pontoz_ossz("j01", "```json\n" + self._ossz(m, "j01") + "\n```")
        self.assertEqual((jo["huseg"], jo["lefedettseg"]), (1.0, 1.0))
        self.assertGreater(jo["pont"], 0.95)
        kitalalt = m.pontoz_ossz("j01", self._ossz(m, "j01", lambda x: "Ez a mondat sehol sem szerepel a forrásban, kitaláció az egész."))
        self.assertEqual((kitalalt["huseg"], kitalalt["lefedettseg"], kitalalt["pont"]), (0.0, 0.0, 0.0))
        egesz = m.forras_szoveg("j01")                                           # az egész forrást idéző „összefoglaló”
        mind = m.pontoz_ossz("j01", json.dumps([{"allitas": "Minden benne van.", "idezet": egesz}], ensure_ascii=False))
        self.assertEqual(mind["pont"], 0.0)
        self.assertEqual(m.pontoz_ossz("j01", "nem JSON")["pont"], 0.0)
        egy = json.loads(self._ossz(m, "j01"))[:1]                               # egyetlen jó állítás: hű, de nem fed le
        resz = m.pontoz_ossz("j01", json.dumps(egy * 12, ensure_ascii=False))
        self.assertEqual(resz["huseg"], 1.0)
        self.assertLess(resz["lefedettseg"], 0.35)

    def _kartyak(self, m, jid):
        ki = []
        for i, t in enumerate(m.jegyzet(jid)["tenyek"], 1):
            szavak = t["forras"].replace("*", "").split()
            ki.append({"kerdes": f"Melyik megállapítás tartozik a(z) {i}. sorszámú tételhez?",
                       "valasz": " ".join(szavak[1:5]), "forras": t["forras"]})
        return ki

    def test_kartya_jo_es_elrontott(self):
        m = self.f("szoveg")
        k = self._kartyak(m, "j02")
        jo = m.pontoz_kartya("j02", json.dumps(k, ensure_ascii=False))
        self.assertEqual((jo["minoseg"], jo["lefedettseg"]), (1.0, 1.0))
        r = [dict(k[0], valasz="; ".join(["egy hosszú, felsorolásos válasz több ténnyel"] * 3)),      # nem atomi
             dict(k[1], forras="Ez a forrásmondat nincs a jegyzetben, csak kitaláltam az egészet."),   # nem kötött
             dict(k[2], valasz="Napóleon császár waterlooi veresége"),                                 # nem igaz
             dict(k[3], kerdes="Mit állít erről a jegyzet a fenti részben?"),                          # nem egyértelmű
             dict(k[4]), dict(k[4])]                                                                   # ismétlés
        e = m.pontoz_kartya("j02", json.dumps(r, ensure_ascii=False))
        self.assertEqual(e["kartyak"], 6)
        self.assertEqual(e["minoseg"], 1 / 6)
        self.assertEqual((e["bukas"]["atomi"], e["bukas"]["kotott"], e["bukas"]["egyertelmu"]), (1, 1, 2))
        self.assertGreaterEqual(e["bukas"]["igaz"], 2)

    def test_pontszam_a_ket_resz_atlaga(self):
        m = self.f("szoveg")
        t = {x["id"]: x for x in m.tetelek(self.cfg)}
        e = m.pontoz([rekord(t["ossz-j01"], self._ossz(m, "j01")), rekord(t["kartya-j02"], "[]")])
        self.assertGreater(e["osszefoglalas"]["pont"], 0.95)
        self.assertEqual(e["kartya"]["pont"], 0.0)
        self.assertAlmostEqual(e["pontszam"], (e["osszefoglalas"]["pont"] + 0.0) / 2, places=3)


class MatekTest(_Alap):
    def test_arany_epseg(self):
        from kozos import matek as M
        m = self.f("matek")
        f = m.ARANY["feladatok"]
        self.assertEqual(len(f), 40)
        self.assertEqual(len({x["id"] for x in f}), 40)
        for x in f:                                                             # minden várt érték elemezhető
            v = x["vart"]
            if v["tipus"] == "halmaz":
                [M.elemez(e) for e in v["ertekek"]]
            elif v["tipus"] == "szam" or v["tipus"] == "kifejezes":
                M.elemez(v["ertek"])
            elif v["tipus"] == "intervallum":
                M.intervallum(v["ertek"])
            elif v["tipus"] == "par":
                [M.elemez(e) for e in v["ertekek"].values()]
            else:
                self.fail(x["id"])
        self.assertEqual(sum(1 for x in f if x.get("lepesek")), 10)
        self.assertGreaterEqual(len({x["tema"] for x in f}), 7)

    def test_levezetesek_egy_hibaval(self):
        from kozos import matek as M
        m = self.f("matek_ellenorzo")
        lv = m.levezetesek()
        self.assertEqual((sum(1 for x in lv if x["hibas_sor"]), sum(1 for x in lv if not x["hibas_sor"])), (10, 10))
        from collections import Counter
        self.assertEqual(Counter(x["hiba"] for x in lv if x["hiba"]),
                         Counter({"elojel": 3, "atrendezes": 3, "nullaval_osztas": 2, "hamis_gyok": 2}))
        for x in lv:
            if x["hibas_sor"]:
                self.assertTrue(2 <= x["hibas_sor"] <= len(x["sorok"]), x["id"])
                elotte, hibas = x["sorok"][x["hibas_sor"] - 2], x["sorok"][x["hibas_sor"] - 1]
                if elotte.get("gepi") and hibas.get("gepi"):                     # a hibás sor tényleg nem következik
                    self.assertNotEqual(M.megoldashalmaz(elotte["gepi"]), M.megoldashalmaz(hibas["gepi"]), x["id"])
        self.assertEqual(len(list(m.tetelek(self.cfg))), 20)

    def test_matek_pontozo(self):
        m = self.f("matek")
        t = list(m.tetelek(self.cfg))
        self.assertEqual(len(t), 40)
        v = {"tipus": "halmaz", "ertekek": ["6"], "tema": "algebra"}
        jo = "Négyzetre emelünk…\nx = 6 vagy x = 26, ellenőrzés után:\nVÉGEREDMÉNY: x = 6"
        hamis = "Négyzetre emelünk…\nVÉGEREDMÉNY: x = 6; x = 26"                 # a hamis gyököt megtartó megoldás
        nincs = "A megoldás x = 6."                                             # nincs zárósor
        e = m.pontoz([{"id": "a", "vart": v, "valasz": jo}, {"id": "b", "vart": v, "valasz": hamis},
                      {"id": "c", "vart": v, "valasz": nincs}, {"id": "d", "vart": v, "valasz": None}])
        self.assertEqual((e["helyes"], e["nincs_zarosor"], e["temak"]), (1, 2, {"algebra": "1/4"}))
        self.assertEqual([x["id"] for x in e["rossz"]], ["b", "c", "d"])

    def test_ellenorzo_pontozo(self):
        m = self.f("matek_ellenorzo")
        h = {"hibas_sor": 3, "hiba": "elojel"}
        j = {"hibas_sor": None, "hiba": None}
        r = [{"id": "h1", "vart": h, "valasz": "A 3. sorban előjelhiba.\nÍTÉLET: HIBA 3"},
             {"id": "h2", "vart": h, "valasz": "ÍTÉLET: HIBA 4"},                # rossz sorszám
             {"id": "h3", "vart": h, "valasz": "ÍTÉLET: HELYES"},                # nem vette észre
             {"id": "j1", "vart": j, "valasz": "Rendben.\n**Ítélet: helyes**"},
             {"id": "j2", "vart": j, "valasz": "ÍTÉLET: HIBA 2"},                # téves riasztás
             {"id": "j3", "vart": j, "valasz": "nem tudom"}]
        e = m.pontoz(r)
        self.assertEqual((e["helyes_itelet"], e["felismert_hiba"], e["teves_riasztas"], e["nincs_itelet"]),
                         (2, "2/3", "1/3", 1))
        self.assertAlmostEqual(e["pontszam"], 2 / 6, places=3)
        mindig = m.pontoz([{"id": x["id"], "vart": x["vart"], "valasz": "ÍTÉLET: HIBA 2"} for x in r])
        self.assertLessEqual(mindig["pontszam"], 0.5)                           # a mindig „HIBA” nem nyer


class GrafikonTest(_Alap):
    def test_arany_es_pontozo(self):
        from kozos import matek as M
        m = self.f("grafikon")
        t = list(m.tetelek(self.cfg))
        self.assertEqual(len(t), 15)
        for x in t:
            M.elemez(x["vart"]["kifejezes"])
        v = next(x["vart"] for x in t if x["vart"]["kifejezes"] == "x^3-3*x")
        jo = {"valtozo": "x", "kifejezes": "x*(x^2-3)", "zerushelyek": ["-1.7321", "0", "sqrt(3)"],
              "szelsoertekek": [{"x": "1", "y": "-2"}, {"x": "-1", "y": "2"}], "aszimptotak": []}
        self.assertEqual(m.pontoz_egyet(v, "```json\n" + json.dumps(jo) + "\n```")["pont"], 1.0)
        self.assertEqual(m.pontoz_egyet(v, json.dumps(dict(jo, kifejezes="x^3+3*x")))["pont"], 0.0)   # előjelhiba
        fel = m.pontoz_egyet(v, json.dumps(dict(jo, zerushelyek=["0"], szelsoertekek=[])))
        self.assertEqual((fel["kifejezes"], fel["zerushelyek"], fel["szelsoertekek"], fel["pont"]), (True, False, False, 0.6))
        self.assertEqual(m.pontoz_egyet(v, "nincs JSON")["pont"], 0.0)
        unicode = dict(jo, zerushelyek=["-√3", "0", "√3"])                    # C19 rétegzett minta: zárójel nélküli gyökjel
        self.assertEqual(m.pontoz_egyet(v, json.dumps(unicode, ensure_ascii=False))["pont"], 1.0)
        log = next(x["vart"] for x in t if x["vart"]["aszimptotak"] == ["x=0"])
        jo_log = {"kifejezes": "log(x, 2)", "zerushelyek": [1], "szelsoertekek": [], "aszimptotak": ["x = 0"]}
        self.assertEqual(m.pontoz_egyet(log, json.dumps(jo_log))["pont"], 1.0)
        self.assertEqual(m.pontoz_egyet(log, json.dumps(dict(jo_log, aszimptotak=["y=0"])))["aszimptotak"], False)


class KeresesTest(_Alap):
    def _vault(self):
        m = "T03 - Az ókori Róma/Elmélet"
        ir(self.vault, f"{m}/08 - A polgárháborúk kora.md", "---\nTags:\n  - History\n---\n# Caesar\n\nCaesar átlépte a "
           "Rubicont, Pompeius Pharszalosznál vereséget szenvedett.\n\n## Füzet\n\n![[IMG_1.JPG]]\n")
        ir(self.vault, f"{m}/07 - A köztársaság válsága.md", "# Gracchusok\n\nA földreform kudarca és a néptribunusok.\n")
        ir(self.vault, f"{m}/09 - A principatus.md", "# Augustus\n\nAugustus egyeduralma, a principatus rendszere.\n")
        ir(self.vault, f"{m}/07F - Feladattár.md", "# Feladatok\n\nRubicon Rubicon Rubicon.\n")
        return [{"id": "k1", "tipus": "kulcsszavas", "kerdes": "Rubicon átlépése Pharszalosz",
                 "cel": f"{m}/08 - A polgárháborúk kora.md", "idezet": "Pompeius Pharszalosznál vereséget szenvedett"},
                {"id": "k2", "tipus": "atfogalmazott", "kerdes": "ki lett az első császár", "cel": f"{m}/09 - A principatus.md",
                 "idezet": "Augustus egyeduralma, a principatus rendszere"}]

    def test_korpusz_es_tetelek(self):
        parok = self._vault()
        import korpusz as K
        korp = K.korpusz(self.vault, parok)
        self.assertEqual(len(korp), 3)                                           # a feladattár nem kerül a korpuszba
        self.assertNotIn("IMG_1", "".join(d for dk in korp.values() for d in dk))  # a `## Füzet` szakasz kimarad
        b = list(self.f("beagyazas").tetelek_ebbol(self.vault, parok))
        self.assertEqual([x["vart"]["fajta"] for x in b], ["korpusz", "kerdes", "kerdes"])
        r = list(self.f("rerank").tetelek_ebbol(self.vault, parok))
        self.assertEqual(len(r[0]["keres"]["documents"]), 3)
        self.assertIn("Rubicont", r[0]["keres"]["documents"][r[0]["vart"]["cel_index"]])
        with self.assertRaises(FileNotFoundError):
            K.korpusz(self.vault, [dict(parok[0], cel="T03 - Az ókori Róma/Elmélet/99 - Nincs.md")])
        self.assertEqual(len(K.parok()["parok"]), 50)
        with self.assertRaises(FileNotFoundError):                               # a valódi párok az álvaultban nincsenek meg
            list(self.f("beagyazas").tetelek(self.cfg))

    def test_rogzitett_korpusz_a_commit_fajabol(self):
        """C19 (a): a `korpusz_commit` fájából épülő korpusz az élő vault későbbi változásától független (reprodukálható
        mérés), és bájtra azonos azzal, amit akkor az élő mappa adott (a meglévő sorok ujjlenyomata nem változik)."""
        import subprocess
        import korpusz as K
        parok = self._vault()
        env = {**K._git_env(), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        git = lambda *a: subprocess.run(["git", "-C", str(self.vault), *a], env=env, check=True, capture_output=True,
                                        text=True).stdout.strip()
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "álvault")
        commit = git("rev-parse", "HEAD")
        elo = K.korpusz(self.vault, parok)
        rogzitett = K.korpusz(K.GitFa(self.vault / ".git", commit), parok)
        self.assertEqual(rogzitett, elo)
        ir(self.vault, "T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora.md", "# Caesar\n\nÁtírva.\n")
        ir(self.vault, "T03 - Az ókori Róma/Elmélet/10 - Új jegyzet.md", "# Új\n\nÚj szomszéd.\n")
        self.assertNotEqual(K.korpusz(self.vault, parok), elo)
        self.assertEqual(K.korpusz(K.GitFa(self.vault / ".git", commit), parok), elo)     # a commit fája nem változik
        cfg = mock.Mock(path=lambda k: {"vault_git": self.vault / ".git", "vault": self.vault}[k])
        self.assertIsInstance(K.forras(cfg, {"korpusz_commit": commit}), K.GitFa)
        self.assertIsInstance(K.forras(cfg, {}), K.MappaFa)
        with self.assertRaisesRegex(FileNotFoundError, "rögzített korpusz"):
            K.GitFa(self.vault / ".git", "0" * 40)
        self.assertTrue(K.parok().get("korpusz_commit"))                        # a valódi halmaz rögzített

    def test_beagyazas_pontozo_felcserelt_rangsoron_bukik(self):
        m = self.f("beagyazas")
        korp = {"id": "korpusz-000", "vart": {"fajta": "korpusz", "utak": ["a.md", "a.md", "b.md", "c.md"]},
                "valasz": [[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0, 1]]}
        k = lambda i, cel, v: {"id": i, "vart": {"fajta": "kerdes", "cel": cel, "tipus": "kulcsszavas"}, "valasz": [v]}
        jo = m.pontoz([korp, k("k1", "a.md", [1, 0.1, 0]), k("k2", "b.md", [0.1, 1, 0])])
        self.assertEqual((jo["recall1"], jo["mrr"], jo["korpusz_jegyzet"]), (1.0, 1.0, 3))
        rossz = m.pontoz([korp, k("k1", "a.md", [0, 1, 0.5]), k("k2", "b.md", [1, 0, 0.5])])       # felcserélt vektorok
        self.assertEqual(rossz["recall1"], 0.0)
        self.assertLess(rossz["mrr"], 0.5)
        hiba = m.pontoz([korp, {"id": "k1", "vart": {"fajta": "kerdes", "cel": "a.md", "tipus": "x"}, "valasz": None}])
        self.assertEqual((hiba["pontszam"], hiba["hibas_rekord"]), (0.0, 1))

    def test_rerank_pontozo(self):
        m = self.f("rerank")
        v = {"cel_index": 1, "tipus": "atfogalmazott", "n": 4}
        jo = m.pontoz([{"id": "a", "vart": v, "valasz": [0.1, 0.9, 0.2, 0.0]}])
        self.assertEqual((jo["mrr"], jo["recall1"]), (1.0, 1.0))
        rossz = m.pontoz([{"id": "a", "vart": v, "valasz": [0.9, 0.1, 0.8, 0.7]}])                 # a cél az utolsó
        self.assertEqual((rossz["mrr"], rossz["recall3"]), (0.25, 0.0))
        azonos = m.pontoz([{"id": "a", "vart": v, "valasz": [0.5, 0.5, 0.5, 0.5]}])               # holtverseny nem nyer
        self.assertEqual(azonos["mrr"], 0.25)
        self.assertEqual(m.pontoz([{"id": "a", "vart": v, "valasz": [0.1, 0.9]}])["mrr"], 0.0)   # rossz hosszú válasz


class FormatumTest(_Alap):
    """C18.1: a feladatok opcionális `formatum_ok` próbája (csak jelentés, a pontozó nem változik)."""

    def test_formatum_ok(self):
        esetek = {
            "matek": ("Számolás…\nVÉGEREDMÉNY: x = 5", "<think>VÉGEREDMÉNY: 5"),
            "matek_ellenorzo": ("ÍTÉLET: helyes", "<think>sokáig gondolkodom"),
            "grafikon": ('```json\n{"kifejezes": "x^2"}\n```', "nem tudom"),
            "matek_cas": ("Terv: …\n```python\nimport sympy as sp\nEREDMENY = 1\n```", "```python\nx = 1\n```"),
            "fuzet_fejezet": ("TANTÁRGY: Fizika\nFEJEZET: F02", "TANTÁRGY: Fizika"),
        }
        for nev, (jo, rossz) in esetek.items():
            m = feladat(self.cfg, nev)
            self.assertTrue(m.formatum_ok(jo, None), nev)
            self.assertFalse(m.formatum_ok(rossz, None), nev)
        m = feladat(self.cfg, "szoveg")
        self.assertTrue(m.formatum_ok('[{"allitas": "a", "idezet": "b"}]', {"fajta": "ossz"}))
        self.assertTrue(m.formatum_ok('[{"kerdes": "a", "valasz": "b", "forras": "c"}, {"kerdes": "d"', {"fajta": "kartya"}))
        self.assertFalse(m.formatum_ok("Íme az összefoglaló.", {"fajta": "ossz"}))
        self.assertFalse(hasattr(feladat(self.cfg, "ocr_kezi"), "formatum_ok"))


class MatekCasTest(_Alap):
    """C24a: a CAS-út váza (`matek_cas`): a modell kódja a homokozóban fut, az összevetés a megbízható folyamatban."""

    class _AlHomokozo:
        def __init__(self, eredmenyek):
            self.eredmenyek, self.kodok = eredmenyek, []

        def futtat(self, feladatok):
            self.kodok += [f["kod"] for f in feladatok]
            return self.eredmenyek[:len(feladatok)]

    def test_tetelek_es_router_feladat(self):
        """C24b: router-feladat, és a kérése a „Megoldás” éles kérése (egy prompt a mérésre és az éles útra)."""
        m = self.f("matek_cas")
        t = list(m.tetelek(self.cfg))
        self.assertEqual(len(t), 40)
        self.assertIn("```python```", t[0]["keres"]["messages"][0]["content"])
        self.assertEqual(m.ROUTER_FELADAT, "matek_cas")
        self.assertIn("matek_cas", self.cfg.section("router")["feladatok"])
        from parancslista import SORREND
        self.assertIn("matek_cas", SORREND)
        from matek import megoldas
        szoveg = next(f["szoveg"] for f in m.ARANY["feladatok"] if f["id"] == t[0]["id"])
        self.assertEqual(t[0]["keres"], megoldas.keres(szoveg))

    def test_kodblokk_es_valasz_szoveg(self):
        m = self.f("matek_cas")
        self.assertEqual(m.kodblokk("a\n```python\nx = 1\n```\nb\n```py\nEREDMENY = 2\n```"), "EREDMENY = 2")
        self.assertIsNone(m.kodblokk("nincs kód"))
        self.assertEqual(m.valasz_szoveg({"tipus": "halmaz", "elemek": ["-1/2", "0"]}, "halmaz"), "x = -1/2; x = 0")
        self.assertEqual(m.valasz_szoveg({"tipus": "halmaz", "elemek": []}, "halmaz"), "nincs megoldás")
        self.assertEqual(m.valasz_szoveg({"tipus": "kifejezes", "ertek": "E**2"}, "szam"), "e**2")
        self.assertEqual(m.valasz_szoveg({"tipus": "par", "ertekek": {"a_1": "7/2", "d": "11/2"}}, "par"),
                         "a_1 = 7/2; d = 11/2")
        iv = {"tipus": "intervallum", "darabok": [{"a": "5", "b": "6", "bal_nyitott": False, "jobb_nyitott": True}]}
        self.assertEqual(m.valasz_szoveg(iv, "intervallum"), "[5; 6)")
        self.assertIsNone(m.valasz_szoveg({"tipus": "egyeb", "ertek": "ImageSet(...)"}, "halmaz"))

    def test_pontozo_al_homokozoval(self):
        m = self.f("matek_cas")
        t = {x["id"]: x for x in m.tetelek(self.cfg)}
        kod = "```python\nimport sympy as sp\nEREDMENY = 0\n```"
        rek = [rekord(t["m01"], kod), rekord(t["m01"], kod), rekord(t["m22"], kod), rekord(t["m09"], kod),
               rekord(t["m02"], "Nem írok kódot."), rekord(t["m02"], kod)]
        al = self._AlHomokozo([
            {"allapot": "ok", "ertek": {"tipus": "halmaz", "elemek": ["-1/2", "0", "3"]}, "uzenet": ""},
            {"allapot": "ok", "ertek": {"tipus": "halmaz", "elemek": ["0", "3"]}, "uzenet": ""},      # elveszett gyök
            {"allapot": "ok", "ertek": {"tipus": "par", "ertekek": {"a_1": "7/2", "d": "11/2"}}, "uzenet": ""},
            {"allapot": "ok", "ertek": {"tipus": "intervallum", "darabok": [
                {"a": "5", "b": "6", "bal_nyitott": False, "jobb_nyitott": True}]}, "uzenet": ""},
            {"allapot": "tiltott", "ertek": None, "uzenet": "tiltott import: os"}])
        p = m.pontoz(rek, homokozo=al)
        self.assertEqual((p["helyes"], p["pontszam"]), (3, 0.5))
        self.assertEqual(p["allapotok"], {"nincs_kod": 1, "ok": 4, "tiltott": 1})
        self.assertEqual(len(al.kodok), 5)                                      # a kód nélküli nem fut

    @unittest.skipUnless(sys.platform == "darwin", "[indokolt] a homokozó a macOS sandbox-exec-jére épül")
    def test_pontozo_a_valodi_homokozoban(self):
        from homokozo import Homokozo
        m = self.f("matek_cas")
        t = {x["id"]: x for x in m.tetelek(self.cfg)}
        jo = ("Terv: szorzattá alakítás.\n```python\nimport sympy as sp\nx = sp.Symbol('x', real=True)\n"
              "EREDMENY = sp.solveset(2*x**3 - 5*x**2 - 3*x, x, sp.S.Reals)\n```")
        hamis = "```python\nimport sympy as sp\nx = sp.Symbol('x', real=True)\nEREDMENY = sp.FiniteSet(6, 26)\n```"
        tiltott = "```python\nimport os\nEREDMENY = os.listdir('/')\n```"
        p = m.pontoz([rekord(t["m01"], jo), rekord(t["m02"], hamis), rekord(t["m02"], tiltott)],
                     homokozo=Homokozo(self.cfg))
        self.assertEqual(p["helyes"], 1)
        self.assertEqual(p["allapotok"], {"ok": 2, "tiltott": 1})


class ParancslistaTest(_Alap):
    def test_minden_sor_modellje_es_feladata_letezik(self):
        import importlib.util
        from core.modell import beallitas as B
        spec = importlib.util.spec_from_file_location("parancslista", EVAL / "parancslista.py")
        p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(p)
        fut, nem = p.sorok(self.cfg)
        modellek = B.betolt(self.cfg).modellek
        self.assertEqual(len(fut) + len(nem), len(modellek))
        for s in fut:
            m = modellek[s["modell"]]
            self.assertFalse(m.konvertalas)
            self.assertIn(m.futtato, p.FUTTATHATO)
            self.assertEqual(s["keret"], "munka" if m.csucs_gb <= 5.0 else "tavol")
            for f in s["feladatok"]:
                self.assertTrue((EVAL / f / "feladat.py").is_file(), f)
            if "atirat" in s["feladatok"]:                                    # C20b: a hang-kérést csak az mlx-whisper fogadja
                self.assertIn(m.futtato, p.HANG_FUTTATO)
            self.assertNotIn("--kalibralt", s["parancs"])                      # a jelet a C19 adja
            # C29.8: az éles generálás a vázlat-aranyon nem rögzít; a rögzítés a K27 utáni újrapontozásé
            self.assertNotIn("--rogzit", s["parancs"])
            self.assertEqual(s["ujrapontozas"], f"bin/mos eval {s['modell']} {' '.join(s['feladatok'])} --csak-ertekel --rogzit")
        self.assertTrue(all(s["ok"] for s in nem))
        md = p.markdown(self.cfg)
        self.assertEqual(md.count("bin/mos eval "), 2 * len(fut))             # generálás + újrapontozás
        self.assertTrue(any("atirat" in s["feladatok"] for s in fut))           # C20b: a K29 sorai a listában
        self.assertFalse(any("atirat" in s["feladatok"] for s in fut if modellek[s["modell"]].futtato != "mlx-whisper"))
        self.assertIn("## Újrapontozás a K27 jóváhagyása után", md)
        self.assertLess(md.index(fut[0]["parancs"]), md.index("## Újrapontozás"))
        self.assertLess(md.index("## Újrapontozás"), md.index(fut[0]["ujrapontozas"]))
        kesz = (EVAL.parent.parent / "docs" / "MERES-PARANCSOK.md").read_text(encoding="utf-8")
        for s in fut:                                                           # a docs-beli lista a regiszterrel egyezik
            self.assertIn(s["parancs"], kesz)
            self.assertIn(s["ujrapontozas"], kesz)

    def test_az_asszisztens_feladatai_a_parancslistaban_es_a_dokumentumban(self):
        """Lelet 6: a `kiegeszites`, `kifejtes`, `osszefoglal_kijeloles` tételidővel, tételszámmal és a regiszter szerinti
        modelleken szerepel; a dokumentum a figyelmeztetést (a kalibrált jel megmaradása) hordozza, és nem állítja, hogy
        a `fuzet_fejezet`/`grafikon` nem router-feladat."""
        import importlib.util
        from core.modell import beallitas as B
        spec = importlib.util.spec_from_file_location("parancslista", EVAL / "parancslista.py")
        p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(p)
        router = set(self.cfg.section("router")["feladatok"])
        n = p.tetelszamok(self.cfg)
        for f in ("kiegeszites", "kifejtes", "osszefoglal_kijeloles"):
            with self.subTest(feladat=f):
                self.assertIn(f, router)
                self.assertIn(f, p.SORREND)
                self.assertIn(f, p.TETELIDO)
                self.assertEqual(n[f], 12)
        for m in B.betolt(self.cfg).modellek.values():
            for f in ("kiegeszites", "kifejtes", "osszefoglal_kijeloles"):
                if f in m.feladat and m.nev not in dict(m.meres_kihagy_feladat):
                    self.assertIn(f, p.feladatai(m), (m.nev, f))
        md = p.markdown(self.cfg)
        self.assertIn("a kalibrált jel megmaradása", md)
        self.assertIn("--kalibralt-le", md)
        fut, _ = p.sorok(self.cfg)
        self.assertLess(md.index("## Újrapontozás"), md.index("a kalibrált jel megmaradása"))
        self.assertLess(md.index("a kalibrált jel megmaradása"), md.index(fut[0]["ujrapontozas"]))     # a lista fölött
        self.assertNotIn("Egyik sem router-feladat", md)
        kesz = (EVAL.parent.parent / "docs" / "MERES-PARANCSOK.md").read_text(encoding="utf-8")
        # a `beagyazas` tételszáma a környezet keresési korpuszából jön (az álkörnyezetben a tartalék 1500): a sor száma nem számít
        import re
        norm = lambda t: re.sub(r"\| `beagyazas` \| \d+ \|", "| `beagyazas` | N |", t)
        self.assertEqual(norm(kesz), norm(md), "a docs/MERES-PARANCSOK.md elavult: modulok/eval/parancslista.py újragenerálja")

    def test_eloproba_lista_kulon_mappa_rogzites_nelkul_es_osszesito(self):
        """C18.1: az előpróba `--limit 3`, külön kimenet, `--rogzit` nélkül; a végén az összesítő kapuja."""
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location("parancslista", EVAL / "parancslista.py")
        p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(p)
        fut, _ = p.sorok(self.cfg, eloproba=True)
        eles, _ = p.sorok(self.cfg)
        self.assertEqual([s["modell"] for s in fut], [s["modell"] for s in eles])
        for s in fut:
            self.assertTrue(s["parancs"].endswith('--limit 3 --kimenet "{tmp}/eval-proba"'), s["parancs"])
            self.assertNotIn("--rogzit", s["parancs"])
        gondolkodo = {s["modell"]: s for s in eles if s["gondolkodo"]}
        self.assertIn("ministral3_8b_reasoning", gondolkodo)
        _, nem = p.sorok(self.cfg)                                  # K32: a lassú gondolkodók és a qwen35_2b kimaradt
        kihagyott = {s["modell"]: s["ok"] for s in nem if "kihagyva a mérésből" in s["ok"]}
        # K231 (2026-10-14): a lassú gondolkodók és a C36b opcionális köre kikerült a regiszterből
        self.assertEqual(sorted(kihagyott), ["qwen35_2b"])
        self.assertTrue(all("K32 előpróba" in ok for ok in kihagyott.values()))
        self.assertNotIn("phi4_mini_reasoning", gondolkodo)
        # feladatonkénti kihagyás: a modell a többi feladatán marad, a származtatott fuzet_fejezet a kihagyás előtt áll
        from core.modell import beallitas as B
        mod = B.betolt(self.cfg).modellek
        self.assertEqual(p.feladatai(mod["gemma4_12b"]), ["fuzet_fejezet", "fuzet_valaszto", "szoveg", "kviz", "matek_ellenorzo", "kod",
                                                         "tema", "kotes"])         # C20b: a médiatársítás két ítélete
        self.assertNotIn("fuzet_fejezet", p.feladatai(mod["qwen35_4b"]))
        self.assertIn("ocr_kezi", p.feladatai(mod["qwen35_4b"]))
        self.assertNotIn("matek_ellenorzo", p.feladatai(mod["gemma4_e4b"]))
        self.assertIn("szoveg", p.feladatai(mod["gemma4_e4b"]))
        ki = {(s["modell"], s["feladat"]) for s in p.kihagyott_feladatok(self.cfg)}
        self.assertEqual(ki, {("qwen35_4b", "fuzet_fejezet"), ("gemma4_e4b", "matek_ellenorzo"),
                              ("gemma4_12b", "ocr_kezi"),
                              ("chandra_ocr2", "ocr_kezi"), ("dots_mocr", "ocr_kezi"),
                              ("qwen3_vl_4b", "ocr_kezi"), ("nanonets_ocr2", "ocr_kezi"),     # K28 piros sorai (2026-10-07)
                              ("ministral3_3b", "kviz"), ("qwen3_vl_4b", "kviz")})            # K135 (C19)
        self.assertIn("## Kihagyott feladatok", p.markdown_eloproba(self.cfg))
        md = p.markdown_eloproba(self.cfg)
        self.assertIn("modulok/eval/osszesito.py", md)
        self.assertIn("K27", md)
        kesz = (EVAL.parent.parent / "docs" / "MERES-ELOPROBA.md").read_text(encoding="utf-8")
        for s in fut:
            self.assertIn(s["parancs"], kesz)
        spec = importlib.util.spec_from_file_location("osszesito", EVAL / "osszesito.py")
        o = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(o)
        d = Path(self.cfg.path("tmp")) / "eval-proba"
        (d / "m1").mkdir(parents=True)
        erv = {"n": 3, "levagott": 0, "hurok": 0, "ures": 0, "hiba": 0, "formatum_hiba": None, "rossz_arany": 0.0,
               "hianyzo": 0}
        ert = {"modell": "m1", "feladat": "matek", "pontszam": 1.0, "n": 3, "ervenyes": True, "ervenyesseg": erv,
               "keres_beallitas": [{"max_tokens": 7500}], "futas": {"mp_atlag": 2.0, "completion_tokens_max": 3100}}
        (d / "m1" / "matek-ertekeles.json").write_text(json.dumps(ert), encoding="utf-8")
        with mock.patch("sys.stdout"):
            self.assertEqual(o.main([str(d)]), 0)
        self.assertEqual(o.sor(ert)["tokenek"], "3100/7500")
        self.assertEqual(o.sor(ert)["csucs"], "–")                              # a C29.8 előtti értékelésben nincs mérés: nem hiba
        ert["futas"].update(csucs_gb_max=3.5, regiszter_csucs_gb=2.7, betoltesek=1)
        self.assertEqual(o.sor(ert)["csucs"], "3.5/2.7 !")                       # T045: a mért csúcs a regiszterbelit tűrésen túl meghaladja
        ert["futas"]["csucs_gb_max"] = 2.6
        self.assertEqual(o.sor(ert)["csucs"], "2.6/2.7")
        self.assertIn("csucs", o.tabla([o.sor(ert)]).split("\n")[0])
        (d / "m1" / "szoveg-ertekeles.json").write_text(json.dumps({"modell": "m1", "feladat": "szoveg", "n": 40,
                                                                   "pontszam": 0.35}), encoding="utf-8")
        with mock.patch("sys.stdout"):
            self.assertEqual(o.main([str(d)], cfg=self.cfg), 1)                  # a kapu nélküli „régi” piros
        self.assertEqual(o.sor({"modell": "m1", "feladat": "szoveg", "n": 1})["allapot"], "régi (kapu nélkül)")
        # 2026-10-07 (a K28 piros sorai): a regiszter szerint nem mért sor „kihagyva”, a kapuba nem számít
        ki = o.kihagyottak(self.cfg)
        self.assertIn("modell kihagyva", ki[("qwen35_2b", "szoveg")])         # a modell kihagyva
        self.assertIn("feladat kihagyva", ki[("gemma4_12b", "ocr_kezi")])                        # a feladat kihagyva
        self.assertIn("nincs a modell", ki[("paddleocr_vl_16", "ocr_kezi")])                     # kikerült a feladatai közül
        self.assertNotIn(("paddleocr_vl_16", "ocr_keplet"), ki)
        self.assertNotIn(("gemma4_12b", "fuzet_fejezet"), ki)
        self.assertFalse(any(m == "m1" for m, _ in ki))                                         # a regiszteren kívüli nem
        (d / "m1" / "szoveg-ertekeles.json").unlink()
        (d / "qwen35_2b").mkdir()
        (d / "qwen35_2b" / "szoveg-ertekeles.json").write_text(json.dumps(
            {"modell": "qwen35_2b", "feladat": "szoveg", "n": 40, "pontszam": 0.0}), encoding="utf-8")
        with mock.patch("sys.stdout") as ki_:
            self.assertEqual(o.main([str(d)], cfg=self.cfg), 0)                  # a kihagyott régi sor nem pirosít
        kiirt = "".join(str(c.args[0]) for c in ki_.write.call_args_list if c.args)
        self.assertIn("kihagyva", kiirt)
        self.assertIn("1/1 érvényes (1 kihagyott sor nélkül)", kiirt)


if __name__ == "__main__":
    unittest.main()
