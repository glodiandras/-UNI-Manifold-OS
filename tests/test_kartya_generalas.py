"""C23b: a kártya-lánc — mennyiség, kapuk (közös forráshűség, atomi, egyértelmű, vak önellenőrzés, duplikáció), a forrás horgonyai
és a `## Gyakorlás` sor, a lánc I/O-ja álcore-ral és álworkerrel (a vaultba és a valódi var/-ba nem ír)."""
from __future__ import annotations

import hashlib
import json
import re
import unittest

from core import automatika, tanulas_db
from core.tulajdonsagok import Tulajdonsagok
from modulok.eval.kozos import kimenet
from tests.eval_segedek import aranyt_igenyel
from modulok.kartya import formatum as F
from modulok.kartya import generalas as G
from modulok.kartya import horgony as H
from modulok.kartya import lanc as L
from modulok.kartya import szinkron
from tests.helpers import alg_core, ir, tmpdir

JEGYZET = """---
Tags: Mathematics
Source: []
Status:
NN:
Canvas:
---
# Mértani sorozat

A mértani sorozat olyan sorozat, amelyben a szomszédos tagok hányadosa állandó.

A hányadost q betűvel jelöljük, értéke a 2, 6, 18 sorozatban 3.

Carl Friedrich Gauss 1801-ben foglalta össze a módszert.

$$
a_n = a_1 q^{n-1}
$$
"""

M1 = "A mértani sorozat olyan sorozat, amelyben a szomszédos tagok hányadosa állandó."
M2 = "A hányadost q betűvel jelöljük, értéke a 2, 6, 18 sorozatban 3."
M3 = "Carl Friedrich Gauss 1801-ben foglalta össze a módszert."

JELOLTEK = [
    {"kerdes": "Mi állandó a mértani sorozatban?", "valasz": "a szomszédos tagok hányadosa", "forrasz": M1},   # elcsúszott kulcs
    {"kerdes": "Mennyi a 2, 6, 18 sorozat hányadosa?", "valasz": "3", "forras": M2},
    {"kerdes": "Mennyi a 2, 6, 18 sorozat hányadosa?", "valasz": "3", "forras": M2},                            # duplikátum
    {"kerdes": "Mit állít a jegyzet a sorozatról?", "valasz": "a hányados állandó", "forras": M1},              # kontextusfüggő
    {"kerdes": "Ki foglalta össze a módszert 1801-ben?", "valasz": "Carl Friedrich Gauss", "forras": M3},
    {"kerdes": "Melyik évben született Gauss?", "valasz": "1777-ben", "forras": "Gauss 1777-ben született Braunschweigben."},
    {"kerdes": "Mivel jelöljük a hányadost?", "valasz": "q betűvel", "forras": M2},
]


def generalo(jeloltek=JELOLTEK):
    """Az első hívás a jelölteket adja, a többi üres listát (a lánc darabonként többször is kérhet)."""
    volt = []

    def hiv(prompt, max_tokens):
        lista = [] if volt else jeloltek
        volt.append(1)
        return "```json\n" + json.dumps(lista, ensure_ascii=False) + "\n```"
    return hiv


def ellenorzo(rossz=()):
    """A vak válasz: a kérdéshez illő válasz, a `rossz` kérdésekre „NEM TUDOM”."""
    tud = {"Mi állandó a mértani sorozatban?": "A szomszédos tagok hányadosa.",
           "Mennyi a 2, 6, 18 sorozat hányadosa?": "3",
           "Ki foglalta össze a módszert 1801-ben?": "Carl Friedrich Gauss",
           "Mivel jelöljük a hányadost?": "q betűvel"}

    def hiv(prompt, max_tokens):
        k = re.search(r"KÉRDÉS: (.*)\n", prompt).group(1)
        return "NEM TUDOM" if k in rossz else tud.get(k, "NEM TUDOM")
    return hiv


class MennyisegTest(unittest.TestCase):
    def test_tenyes_mondatok(self):
        self.assertTrue(G.tenyes("A hányados értéke 3."))
        self.assertTrue(G.tenyes("A mértani sorozat olyan sorozat, amelyben a tagok hányadosa állandó."))
        self.assertTrue(G.tenyes("Ezt a tételt Gauss írta le."))
        self.assertFalse(G.tenyes("ez egy egyszerű mondat."))

    def test_suruseg_es_plafon(self):
        b = G.Beallitas()
        self.assertEqual(G.mennyiseg(JEGYZET, b), 2)                     # 3–4 tényes mondat × 0,5
        hosszu = JEGYZET + "\n".join(f"A {i}. tag értéke {3 ** i}." for i in range(80))
        self.assertEqual(G.mennyiseg(hosszu, b), 30)
        self.assertEqual(G.mennyiseg(hosszu, b, automatikus=True), 10)   # a koordinátor döntése: körönként ≤ 10
        self.assertEqual(G.mennyiseg(JEGYZET, b, csak=set()), 0)         # módosult jegyzet: csak az új mondatok


class KapuTest(unittest.TestCase):
    def test_kulcs_turo_kozos_hely(self):
        from modulok.eval.szoveg import feladat as SZ
        # egy forrás (az eval `kozos` csomagja két néven is betöltődhet, a kód helye ugyanaz)
        self.assertEqual(SZ.kulcs_turo.__code__.co_filename, kimenet.kulcs_turo.__code__.co_filename)
        j = G.szetszed(json.dumps([{"kerdes": "K?", "valaszzi": "V", "forrasza": "F"}]))
        self.assertEqual((j[0].valasz, j[0].forras), ("V", "F"))

    def test_lanc_kapui(self):
        e = G.general(JEGYZET, "Mértani sorozat", generalo(), ellenorzo(rossz={"Mivel jelöljük a hányadost?"}), n=10)
        kerdesek = [k.kerdes for k in e.kartyak]
        self.assertEqual(kerdesek, ["Mi állandó a mértani sorozatban?", "Mennyi a 2, 6, 18 sorozat hányadosa?",
                                    "Ki foglalta össze a módszert 1801-ben?"])
        ok = e.statisztika["elvetve"]
        self.assertEqual(ok.get("duplikat"), 1)
        self.assertEqual(ok.get("kontextusfuggo"), 1)
        self.assertEqual(ok.get("vak"), 1)
        self.assertEqual(ok.get("huseg_kotott"), 1)                      # a forrásmondat nincs a jegyzetben
        self.assertEqual(e.kartyak[0].forras_mondat, M1)                 # a JEGYZET mondata
        self.assertTrue(all(k.idezet for k in e.kartyak))

    def test_meglevo_es_sirko_ellen_szur(self):
        e = G.general(JEGYZET, "Mértani sorozat", generalo(), ellenorzo(), n=10,
                      meglevo=("Mennyi a 2, 6, 18 sorozat hányadosa?",),
                      sirkovek=frozenset({F.ujjlenyomat("Mi állandó a mértani sorozatban?", "Mértani sorozat")}),
                      forras_link="Mértani sorozat")
        kerdesek = {k.kerdes for k in e.kartyak}
        self.assertNotIn("Mennyi a 2, 6, 18 sorozat hányadosa?", kerdesek)
        self.assertNotIn("Mi állandó a mértani sorozatban?", kerdesek)
        self.assertEqual(e.statisztika["elvetve"]["duplikat_meglevo"], 3)

    def test_atomi_es_egyertelmu(self):
        b = G.Beallitas()
        self.assertEqual(G.atomi(G.Jelolt("Mi ez?", "egy kettő három négy öt hat hét nyolc kilenc tíz tizenegy tizenkettő tizenhárom", "f"), b),
                         "hosszu_valasz")
        self.assertEqual(G.atomi(G.Jelolt("Mi ez? És az?", "x", "f"), b), "nem_egy_kerdes")
        self.assertEqual(G.atomi(G.Jelolt("Mik ezek?", "a; b", "f"), b), "felsorolas")
        self.assertEqual(G.egyertelmu(G.Jelolt("Mi a mértani sorozat hányadosa?", "mértani sorozat hányadosa", "f")), "elarulja")
        self.assertIsNone(G.egyertelmu(G.Jelolt("Mi állandó a mértani sorozatban?", "a tagok hányadosa", "f")))

    def test_vak_egyezes(self):
        self.assertEqual(G.vak_egyezes("NEM TUDOM", "3"), 0.0)
        self.assertEqual(G.vak_egyezes("4", "3"), 0.0)
        self.assertEqual(G.vak_egyezes("A válasz 3.", "3"), 1.0)
        self.assertGreaterEqual(G.vak_egyezes("Carl Friedrich Gauss volt", "Carl Friedrich Gauss"), 0.99)


class HorgonyTest(unittest.TestCase):
    def test_horgony_a_bekezdes_vegere(self):
        uj, b = H.horgonyoz(JEGYZET, [M1, M2, M1, "a_n = a_1 q^{n-1}", "nincs ilyen mondat sehol a szövegben"])
        self.assertEqual(b[0], b[2])                                      # ugyanaz a bekezdés, ugyanaz az azonosító
        self.assertTrue(b[0].startswith("m-") and b[1].startswith("m-") and b[0] != b[1])
        self.assertIsNone(b[3])                                           # a $$ képletblokk nem kap azonosítót
        self.assertIsNone(b[4])
        self.assertIn(f"állandó. ^{b[0]}\n", uj)
        self.assertIn("a_n = a_1 q^{n-1}\n$$", uj)
        self.assertEqual(uj.replace(f" ^{b[0]}", "").replace(f" ^{b[1]}", ""), JEGYZET)

    def test_meglevo_azonosito_ujra(self):
        md = JEGYZET.replace("állandó.\n", "állandó. ^sajat\n")
        uj, b = H.horgonyoz(md, [M1])
        self.assertEqual((uj, b), (md, ["sajat"]))

    def test_crlf_marad(self):
        md = JEGYZET.replace("\n", "\r\n")
        uj, b = H.horgonyoz(md, [M3])
        self.assertNotIn("\n", uj.replace("\r\n", ""))
        self.assertIn(f"módszert. ^{b[0]}\r\n", uj)

    def test_link(self):
        self.assertEqual(H.link("M", "m-1a2b", "Fej"), "M#^m-1a2b")
        self.assertEqual(H.link("M", None, "Fej"), "M#Fej")
        self.assertEqual(H.link("M", None, None), "M")


class AlGepi:
    def __init__(self, fajlok):
        self.fajlok, self.irasok = dict(fajlok), []

    class GepiHiba(RuntimeError):
        pass

    def olvas(self, ut):
        t = self.fajlok[ut]
        return {"ut": ut, "tartalom": t, "hash": hashlib.sha1(t.encode()).hexdigest()}

    @staticmethod
    def modell_jel(v):
        return {"feladat": v["feladat"], "modell": v["modell"], "proba": bool(v.get("proba"))}

    @staticmethod
    def uj_kor(elotag):
        return elotag + "-20261008-120000"

    @staticmethod
    def uj(ut, tartalom, osztaly=None):
        return {"tipus": "uj", "ut": ut, "tartalom": tartalom, "osztaly": osztaly}

    @staticmethod
    def csere(ut, tartalom, alap):
        return {"tipus": "csere", "ut": ut, "tartalom": tartalom, "alap": alap}

    def ir(self, kor, tetel, forras, muveletek, uzenet=None, proba=None, *, modell):
        self.irasok.append({"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "proba": proba,
                            "modell": modell})
        for m in muveletek:
            self.fajlok[m["ut"]] = m["tartalom"]
        return {"ok": True, "sha": "abc", "kor": kor, "proba": bool(proba),
                "hash": {m["ut"]: hashlib.sha1(m["tartalom"].encode()).hexdigest() for m in muveletek}}


class Hiba409(RuntimeError):
    kod = 409


class AlWorker:
    def __init__(self, kalibralt=True, rossz=()):
        self.kalibralt, self.utolso = kalibralt, None
        self.gen, self.ell = generalo(), ellenorzo(rossz)
        self.hivasok = []

    def valaszt(self):
        if not self.kalibralt:
            raise Hiba409("nincs kalibrált modell")
        return {"modell": "qwen35_4b"}

    def hivo(self, modell, kifejezett):
        def hiv(prompt, max_tokens):
            self.hivasok.append((modell, kifejezett))
            szoveg = self.ell(prompt, max_tokens) if "KÉRDÉS:" in prompt else self.gen(prompt, max_tokens)
            self.utolso = {"feladat": "szoveg", "modell": modell, "proba": kifejezett,
                           "choices": [{"message": {"content": szoveg}}]}
            return szoveg
        return hiv


class LancTest(unittest.TestCase):
    UT = "M10 - Sorozatok/Mértani sorozat.md"

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, self.UT, JEGYZET)
        self.gepi = AlGepi({self.UT: JEGYZET})

    def futtat(self, **kw):
        return L.futtat(self.cfg, self.UT, gepi=self.gepi, worker=kw.pop("worker", AlWorker()), **kw)

    def test_egy_tetel_kisero_es_forras(self):
        r = self.futtat()
        self.assertEqual((r["allapot"], r["kartyak"]), ("kesz", 2))
        self.assertEqual(len(self.gepi.irasok), 1)
        w = self.gepi.irasok[0]
        self.assertEqual((w["forras"], w["tetel"], w["modell"]["feladat"]), ("mos-kartya", self.UT, "szoveg"))
        self.assertTrue(w["kor"].startswith("KARTYA-"))
        kisero, forras = w["muveletek"]
        self.assertEqual((kisero["tipus"], kisero["osztaly"], kisero["ut"]),
                         ("uj", "kartya", "ATTCHMNTS - cards/Mértani sorozat — kártyák.md"))
        self.assertEqual((forras["tipus"], forras["ut"]), ("csere", self.UT))
        self.assertIn("## Gyakorlás\n![[Mértani sorozat — kártyák]]\n", forras["tartalom"])
        self.assertEqual(len(re.findall(r" \^m-[0-9a-f]{4}\n", forras["tartalom"])), 2)
        e = F.elemez(kisero["tartalom"])
        self.assertEqual(e.source, ["Mértani sorozat"])
        self.assertEqual(e.modell, "qwen35_4b")
        self.assertTrue(all(k.azon and re.fullmatch(r"Mértani sorozat#\^m-[0-9a-f]{4}", k.forras) for k in e.kartyak))
        # a kísérőjegyzet a `kartya` sémaosztály szerint ép (a gépi írás ugyanezt ellenőrzi)
        t = Tulajdonsagok(self.cfg, None)
        fm = re.match(r"---\n(.*?)\n---\n", kisero["tartalom"], re.S).group(0)
        el = t.elemez(kisero["ut"], fm)
        self.assertEqual((el["osztaly"], el["problemak"]), ("kartya", []))
        self.assertEqual(t.h1_problemak(kisero["ut"], kisero["tartalom"]), [])
        # szinkron (eredet: gép) és az automatika visszacsatolása
        with tanulas_db.olvaso(self.cfg) as c:
            sorok = [dict(x) for x in c.execute("SELECT azon, eredet, jegyzet FROM kartya")]
        self.assertEqual({x["eredet"] for x in sorok}, {"gep"})
        self.assertEqual(len(sorok), 2)
        s = automatika.Tar(self.cfg).sor("kartya", self.UT)
        self.assertEqual(s["kimenet"], kisero["ut"])
        self.assertEqual(s["hash"], hashlib.sha1(forras["tartalom"].encode()).hexdigest())

    def test_masodik_futas_a_vegere_fuz_es_nem_ismetel(self):
        self.futtat()
        kisero_ut = "ATTCHMNTS - cards/Mértani sorozat — kártyák.md"
        ir(self.v, kisero_ut, self.gepi.fajlok[kisero_ut])
        r = self.futtat()
        # az első kör 2 kártyát kért (a sűrűség), a harmadik átment jelölt most kerül be: a meglévő kísérőjegyzet végére
        self.assertEqual((r["allapot"], r["kartyak"]), ("kesz", 1))
        kisero = self.gepi.irasok[1]["muveletek"][0]
        self.assertEqual((kisero["tipus"], kisero["ut"]), ("csere", kisero_ut))
        self.assertEqual([k.kerdes for k in F.elemez(kisero["tartalom"]).kartyak][-1], "Ki foglalta össze a módszert 1801-ben?")
        self.assertEqual(self.gepi.fajlok[self.UT].count("![[Mértani sorozat — kártyák]]"), 1)
        ir(self.v, kisero_ut, self.gepi.fajlok[kisero_ut])
        r = self.futtat()
        self.assertEqual(r["allapot"], "nincs_kartya")                  # minden jelölt a meglévők ismétlése
        self.assertEqual(len(self.gepi.irasok), 2)

    def test_d9_kalibralt_nelkul_megall(self):
        with self.assertRaises(L.Megall):
            self.futtat(worker=AlWorker(kalibralt=False))
        self.assertEqual(self.gepi.irasok, [])

    def test_kifejezett_modell_proba_es_nem_ir_allapotot(self):
        r = self.futtat(modell="gemma4_12b")
        self.assertTrue(self.gepi.irasok[0]["proba"])
        self.assertTrue(r["proba"])
        self.assertFalse(tanulas_db.ut(self.cfg).exists())
        self.assertIsNone(automatika.Tar(self.cfg).sor("kartya", self.UT))

    def test_automatikus_modosult_jegyzet_csak_az_uj_mondatokbol(self):
        automatika.Tar(self.cfg).kesz("kartya", self.UT, JEGYZET)          # minden mondat már feldolgozva
        r = self.futtat(automatikus=True)
        self.assertEqual(r["allapot"], "nincs_teendo")
        self.assertEqual(self.gepi.irasok, [])

    def test_kijeloles_csak_abbol_es_nem_jeloli_feldolgozottnak(self):
        w = AlWorker()
        w.gen = generalo([JELOLTEK[4], JELOLTEK[0]])                          # a kijelölésen kívüli forrás kiesik (kötött)
        r = self.futtat(kijeloles=M3, worker=w)
        self.assertEqual((r["allapot"], r["kartyak"]), ("kesz", 1))
        kisero = F.elemez(self.gepi.irasok[0]["muveletek"][0]["tartalom"])
        self.assertEqual([k.kerdes for k in kisero.kartyak], ["Ki foglalta össze a módszert 1801-ben?"])
        self.assertIsNone(automatika.Tar(self.cfg).sor("kartya", self.UT))


class FeladatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        from core import kartya_feladat, tasks
        self.KF, self.tasks = kartya_feladat, tasks

    def test_kezi_terv(self):
        lep, _, figy = self.KF._terv(self.cfg, {"ut": "M/A.md", "kijeloles": "Egy mondat."}, "/tmp/stop")
        argv = lep[0].argv
        self.assertEqual(argv[2:5], ["-m", "modulok.kartya", "general"])
        self.assertIn("--kijeloles", argv)
        self.assertEqual(figy, [])
        _, _, figy = self.KF._terv(self.cfg, {"ut": "M/A.md", "modell": "gemma4_12b"}, "/tmp/stop")
        self.assertTrue(figy)                                                   # kifejezett modell: próba (D9)
        for rossz in ({"ut": "ATTCHMNTS - cards/x.md"}, {"ut": "/abs.md"}, {"ut": "x.txt"}, {"ut": "M/A.md", "proba": 1},
                      {"ut": "M/A.md", "modell": "bge_m3"}):
            with self.assertRaises(self.tasks.Invalid):
                self.KF._terv(self.cfg, rossz, "/tmp/stop")

    def test_automatikus_terv(self):
        lep, _, _ = self.KF._auto_terv(self.cfg, {"utak": ["M/A.md", "F/B.md"]}, "/tmp/stop")
        self.assertIn("--automatikus", lep[0].argv)
        self.assertEqual(lep[0].argv.count("--ut"), 2)
        with self.assertRaises(self.tasks.Invalid):
            self.KF._auto_terv(self.cfg, {"utak": []}, "/tmp/stop")
        self.KF.regisztral()
        self.assertTrue(self.tasks.REGISTRY[self.KF.AUTO_TIPUS].automatikus)
        self.assertFalse(self.tasks.REGISTRY[self.KF.TIPUS].automatikus)
        self.assertEqual(self.tasks.REGISTRY[self.KF.TIPUS].resources, frozenset({"modell", "vault"}))


@aranyt_igenyel("szoveg")
class MeresTest(unittest.TestCase):
    def test_mer_jegyzet_alakja(self):
        """A mérés (`modulok/kartya/meres.py`) az éles láncot futtatja a fagyasztott arany-jegyzeten; az álmodell jelöltjei
        (a forrásuk nincs a jegyzetben) a kapuk előtt pontozódnak, utánuk nem marad kártya."""
        from modulok.kartya import meres
        s = meres.mer_jegyzet("j01", generalo(), G.Beallitas())
        self.assertEqual(s["utan"]["n"], 0)
        self.assertEqual(s["elott"]["n"], len(JELOLTEK))
        o = meres.osszegez([s])
        self.assertEqual((o["jelolt"], o["elfogadott"], o["pontossag_kapuk_utan"]), (len(JELOLTEK), 0, None))


class SzinkronEredetTest(unittest.TestCase):
    def test_gepi_kisero_kartyaja_gep(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, v = alg_core(t.name)
        ir(v, "ATTCHMNTS - cards/A — kártyák.md", F.ir([F.Kartya("K?", "V", "c-11111111")], ["A"], modell="qwen35_4b"))
        ir(v, "ATTCHMNTS - cards/B — kártyák.md", F.ir([F.Kartya("L?", "W", "c-22222222")], ["B"]))
        szinkron.szinkron(cfg)
        with tanulas_db.olvaso(cfg) as c:
            self.assertEqual(dict(c.execute("SELECT azon, eredet FROM kartya").fetchall()),
                             {"c-11111111": "gep", "c-22222222": "kezi"})


if __name__ == "__main__":
    unittest.main()
