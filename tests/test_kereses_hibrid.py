"""A hibrid keresés és a „Kérdezz a vaulttól” modell nélküli magja (C25b-mag): normalizálás, darabolás, vektortár,
inkrementális frissítés, rangfúzió, kereső, vault-válasz, mérő. Álvaulton, álbeágyazóval és álmodellel; platformfüggetlen."""
import os
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.index import kereses
from core.index.hibrid import darabolas, frissites, kereso as KR, kerdezz, normal, rangsor, vektortar
from core.vaultio import Invalid
from tests.helpers import ir, tmpdir
from tests.hibrid_segedek import FAJLOK, AlBeagyazo, AlReranker
from tests.index_segedek import alvault, index_indit

SPARTA = "T02 - Hellász/Elmélet/07 - Spárta.md"
ATHEN = "T02 - Hellász/Elmélet/08 - Athén.md"
PANNONIA = "T03 - Róma/Elmélet/14 - Pannónia.md"


# ====================================================================== tiszta részek

class NormalTest(unittest.TestCase):
    def test_ekezetfuggetlen_tovek(self):
        self.assertEqual(normal.tovek("Spártai NEVELÉS"), normal.tovek("spartai neveles"))
        self.assertEqual(normal.tovek("a fiúkat és 1848"), ["fiukat", "1848"])         # töltelékszó ki, a szám marad

    def test_fts_kerdes_vagy(self):
        self.assertEqual(normal.fts_kerdes("Miért harcoltak a hopliták? hopliták"), '"harcol"* OR "hoplit"*')
        self.assertIsNone(normal.fts_kerdes("mi az a"))

    def test_operatoros(self):
        for q in ("path:T02 sparta", "-athen", "tag:#x", "line:(a b)", "/re/", '"pontos kifejezés"', "a OR b"):
            self.assertTrue(normal.operatoros(q), q)
        for q in ("Miért tiltották a céhek az újítást?", "spártai nevelés", "1-2 közötti szám"):
            self.assertFalse(normal.operatoros(q), q)


class DarabolasTest(unittest.TestCase):
    def test_fejezet_blokk_frontmatter_kihagyott_szakasz(self):
        t = ("---\nTags: x\n---\n# Cím\nElső bekezdés ^a1\n\nMásodik\nsor\n## Al\n```\nkód\n\nkód2\n```\n"
             "## Gyakorlás\n![[x]]\n### Mély\nez is kimarad\n# Vége\nutolsó\n")
        fej = [(1, "Cím", 4), (2, "Al", 9), (2, "Gyakorlás", 15), (3, "Mély", 17), (1, "Vége", 19)]
        d = darabolas.darabol("M/Jegy.md", t, fej, [("a1", 5, 5)])
        self.assertEqual([(x.sor_kezd, x.sor_veg, x.fejezet, x.blokkok) for x in d],
                         [(5, 8, ("Cím",), ("a1",)), (10, 14, ("Cím", "Al"), ()), (20, 20, ("Vége",), ())])
        self.assertIn("kód\n\nkód2", d[1].szoveg)                                     # a kódblokkon belül nem vág
        self.assertEqual(d[0].beagyazando.split("\n\n")[0], "Jegy › Cím")
        self.assertEqual(d[0].cim, "Jegy")

    def test_hossz_szerinti_csoportositas_es_vagas(self):
        bek = "\n\n".join(f"Bekezdés {i} " + "szó " * 40 for i in range(6))           # ~210 karakteres bekezdések
        d = darabolas.darabol("a.md", bek, darab_max=500)
        self.assertGreater(len(d), 1)
        self.assertTrue(all(len(x.szoveg) <= 500 for x in d))
        hosszu = "\n".join("sor " * 30 for _ in range(20))                            # egy ~2400 karakteres bekezdés
        v = darabolas.darabol("b.md", hosszu + " ^vg\n", blokkok=[("vg", 20, 1)], darab_max=500)
        self.assertGreater(len(v), 3)
        self.assertEqual([x.blokkok for x in v][-1], ("vg",))                          # a blokkazonosító az utolsó részé
        self.assertEqual(v[0].sor_kezd, 1)
        self.assertEqual(v[-1].sor_veg, 20)
        self.assertEqual([b.sor_kezd for b in v[1:]], [a.sor_veg + 1 for a in v[:-1]])  # hézag és átfedés nélkül

    def test_hash_stabil_es_tartalomfuggo(self):
        a = darabolas.darabol("a.md", "# A\nszöveg\n", [(1, "A", 1)])[0]
        b = darabolas.darabol("a.md", "\n\n# A\nszöveg\n", [(1, "A", 3)])[0]
        self.assertEqual(a.hash, b.hash)                                               # a sor eltolódása nem változás
        c = darabolas.darabol("a.md", "# A\nmás szöveg\n", [(1, "A", 1)])[0]
        self.assertNotEqual(a.hash, c.hash)


class RangsorTest(unittest.TestCase):
    def test_rrf(self):
        r = rangsor.rrf({"lex": ["a", "b", "c"], "vek": ["b", "d", "b"]}, k=60)
        self.assertEqual([x[0] for x in r], ["b", "a", "d", "c"])
        self.assertAlmostEqual(r[0][1], 1 / 62 + 1 / 61, places=7)
        self.assertEqual(r[0][2], {"lex": 2, "vek": 1})                                # az ismétlés az első helyén számít
        s = rangsor.rrf({"lex": ["a", "b"], "vek": ["b", "a"]}, k=60, sulyok={"lex": 1.0, "vek": 0.0})
        self.assertEqual([x[0] for x in s], ["a", "b"])
        holt = rangsor.rrf({"x": ["b"], "y": ["a"]})
        self.assertEqual([x[0] for x in holt], ["a", "b"])                             # holtverseny: az azonosító dönt

    def test_jegyzetre_bm25_fedes(self):
        self.assertEqual(rangsor.jegyzetre([("a", 1, 0.2), ("b", 2, 0.5), ("a", 3, 0.9)]), [("a", 3, 0.9), ("b", 2, 0.5)])
        p = rangsor.bm25(["hoplit", "falanx"], {1: ["hoplit", "falanx"], 2: ["hoplit"], 3: ["mas"]})
        self.assertGreater(p[1], p[2])
        self.assertNotIn(3, p)
        self.assertEqual(rangsor.fedes(["a", "b", "a"], ["b", "c"]), 0.5)

    def test_rerankel(self):
        rr = rangsor.rerankel("q", [("x", "nincs"), ("y", "kedv kedv"), ("z", "kedv"), ("w", "kedv kedv kedv")],
                              AlReranker("kedv"), n=3)
        self.assertEqual(rr, [("y", 2.0), ("z", 1.0), ("x", 0.0), ("w", None)])         # a 4. nem rerankelt, a végén
        for rossz in ([1.0], [1, "x", 2], [float("nan")] * 3, None):
            with self.assertRaises(ValueError):
                rangsor.rerankel("q", [("x", "a"), ("y", "b"), ("z", "c")], lambda q, d, r=rossz: r, n=3)


# ====================================================================== vektortár

class VektortarTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def tar(self, motor=None, nev="v.sqlite"):
        t = vektortar.Vektortar(Path(self._t.name) / nev, motor=motor)
        self.addCleanup(t.close)
        return t

    @staticmethod
    def darab(ut, i, szoveg):
        return darabolas.Darab(ut, i, i + 1, i + 1, ("F",), szoveg, (darabolas.Bekezdes(i + 1, i + 1, szoveg, None),))

    def tolt(self, t):
        t.modell_allit({"nev": "m", "dim": 3, "elotag": "e", "darabolas": "d"})
        t.jegyzet_ir("a.md", "h1", [self.darab("a.md", 0, "x"), self.darab("a.md", 1, "y")], [[1, 0, 0], [0, 1, 0]])
        t.jegyzet_ir("b.md", "h2", [self.darab("b.md", 0, "z")], [[0.9, 0.1, 0]])

    def test_motorok_egyeznek(self):
        motorok = ["python", "numpy"] if vektortar._numpy() is not None else ["python"]
        eredmenyek = []
        for m in motorok:
            t = self.tar(m, f"{m}.sqlite")
            self.tolt(t)
            self.assertEqual(t.motor, m)
            eredmenyek.append(t.keres([1, 0, 0], k=2))
        for e in eredmenyek:
            self.assertEqual([i for i, _ in e], [eredmenyek[0][0][0], eredmenyek[0][1][0]])
            self.assertAlmostEqual(e[0][1], 1.0, places=5)

    def test_kereses_szurt_utakon_es_darabok(self):
        t = self.tar("python")
        self.tolt(t)
        e = t.keres([1, 0, 0], k=5, utak={"b.md"})
        self.assertEqual(len(e), 1)
        d = t.darabok([e[0][0]])[0]
        self.assertEqual((d.ut, d.szoveg, d.fejezet, d.cim), ("b.md", "z", ("F",), "b"))
        self.assertEqual([x.szoveg for x in t.darabok(ut="a.md")], ["x", "y"])
        self.assertEqual(t.jegyzet_hashek(), {"a.md": "h1", "b.md": "h2"})

    def test_modellvaltas_kiurit_es_dimenzio(self):
        t = self.tar("python")
        self.tolt(t)
        self.assertFalse(t.modell_allit({"nev": "m", "dim": 3, "elotag": "e", "darabolas": "d"}))     # azonos: marad
        self.assertEqual(t.allapot()["darabok"], 3)
        self.assertTrue(t.modell_allit({"nev": "m", "dim": 3, "elotag": "MÁS", "darabolas": "d"}))   # más előtag
        self.assertEqual((t.allapot()["darabok"], t.allapot()["jegyzetek"]), (0, 0))
        with self.assertRaises(ValueError):
            t.jegyzet_ir("a.md", "h", [self.darab("a.md", 0, "x")], [[1, 0, 0, 0]])

    def test_ujrahasznositas_torles_atomi(self):
        t = self.tar("python")
        self.tolt(t)
        h = self.darab("a.md", 0, "x").hash
        self.assertIn(h, t.vektorok_hash_szerint([h, "nincs"]))
        t.jegyzet_torol("a.md")
        self.assertEqual(set(t.jegyzet_hashek()), {"b.md"})
        with self.assertRaises(ValueError):                                         # darab/vektor-eltérés: semmi nem íródik
            t.jegyzet_ir("b.md", "h3", [self.darab("b.md", 0, "q")], [])
        self.assertEqual(t.jegyzet_hashek(), {"b.md": "h2"})

    def test_masik_kapcsolat_irasa_latszik(self):
        """Az API csak olvasó tára és az építő két külön kapcsolat: az építő írása után az olvasó gyorsítótára friss."""
        t = self.tar("python")
        self.tolt(t)
        o = vektortar.Vektortar(t.ut, csak_olvas=True, motor=t.motor)
        self.addCleanup(o.close)
        self.assertEqual(len(o.keres([1, 0, 0], k=10)), 3)
        t.jegyzet_ir("c.md", "h3", [self.darab("c.md", 0, "w")], [[0, 0, 1]])
        self.assertEqual(o.darabok([o.keres([0, 0, 1], k=1)[0][0]])[0].ut, "c.md")
        t.jegyzet_torol("a.md")
        self.assertEqual(len(o.keres([1, 0, 0], k=10)), 2)

    def test_csak_olvaso_es_motorvalasztas(self):
        with self.assertRaises(vektortar.NincsTar):
            vektortar.Vektortar(Path(self._t.name) / "nincs.sqlite", csak_olvas=True)
        self.assertFalse((Path(self._t.name) / "nincs.sqlite").exists())
        t = self.tar("python")
        self.tolt(t)
        o = vektortar.Vektortar(t.ut, csak_olvas=True, motor="python")
        self.addCleanup(o.close)
        self.assertEqual(len(o.keres([0, 1, 0], k=1)), 1)
        with self.assertRaises(sqlite3.OperationalError):
            o._c.execute("DELETE FROM darab")
        # a legjobb motor: a sqlite-vec, ha betölthető (ma nincs a lockban, D3), különben numpy/python
        vart = "sqlite-vec" if vektortar._sqlite_vec() is not None else ("numpy" if vektortar._numpy() else "python")
        self.assertEqual(vektortar.elerheto_motor(), vart)
        a = self.tar(None, "auto.sqlite")
        self.tolt(a)
        self.assertEqual(a.keres([1, 0, 0], k=1)[0][1], 1.0)
        with self.assertRaises(ValueError):
            vektortar.Vektortar(Path(self._t.name) / "x.sqlite", motor="faiss")


# ====================================================================== álvaultos részek

class AlvaultAlap(unittest.TestCase):
    fajlok = FAJLOK

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, self.fajlok)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.tar = vektortar.Vektortar(Path(self.cfg.path("index")) / "vektor.sqlite", motor="python")
        self.addCleanup(self.tar.close)
        self.b = AlBeagyazo()

    def epit(self, **kw):
        return frissites.frissit(self.ix._olvaso, self.tar, self.b, **kw)

    def kereso(self, beagyazo=True, **kw):
        return KR.HibridKereso(self.ix._olvaso, self.tar, self.b if beagyazo else None, kw.pop("reranker", None),
                               KR.Beallitas(**kw))

    def modosit(self, rp, tartalom):
        ir(self.v, rp, tartalom)
        self.assertTrue(self.ix.frissit([rp]))


class FrissitesTest(AlvaultAlap):
    def test_terv_tiszta(self):
        t = frissites.terv({"a": "1", "b": "2", "c": None}, {"b": "x", "c": "", "d": "4"})
        self.assertEqual((t.uj, t.valtozott, t.torolt), (("a",), ("b",), ("d",)))
        self.assertTrue(frissites.terv({}, {}).ures)

    def test_teljes_epites_es_inkrementalis(self):
        e = self.epit()
        self.assertEqual(e.to_dict()["terv"], {"uj": 4, "valtozott": 0, "torolt": 0})
        self.assertEqual((e.beagyazott_jegyzet, e.hibak, e.megszakitva), (4, [], False))
        self.assertEqual(self.tar.allapot()["jegyzetek"], 4)
        self.assertTrue(all(f == "dokumentum" for _, f in self.b.hivasok))
        # a Gyakorlás szakasz (gép írta) nem darab
        self.assertFalse(any("kártyák" in d.szoveg for d in self.tar.darabok(ut=SPARTA)))
        # második futás: semmi dolga
        self.b.hivasok.clear()
        self.assertTrue(self.epit().terv.ures)
        self.assertEqual(self.b.hivasok, [])
        # egy bekezdés változik: csak az a darab ágyazódik újra, a többi vektora újrahasznosul
        regi = FAJLOK[SPARTA]
        self.modosit(SPARTA, regi.replace("pajzsfal védte a sort", "pajzsfal védte a sort, és lándzsát vittek"))
        e = self.epit()
        self.assertEqual((e.terv.valtozott, e.beagyazott_darab, e.ujrahasznalt_darab), ((SPARTA,), 1, 1))
        # törlés
        os.remove(self.v / ATHEN)
        self.assertTrue(self.ix.frissit([ATHEN]))
        e = self.epit()
        self.assertEqual((e.terv.torolt, e.torolt), ((ATHEN,), 1))
        self.assertNotIn(ATHEN, self.tar.jegyzet_hashek())

    def test_megszakithato_es_folytathato(self):
        engedely = iter([True, False])
        e = self.epit(folytathat=lambda: next(engedely, False))
        self.assertTrue(e.megszakitva)
        self.assertEqual(e.beagyazott_jegyzet, 1)
        e = self.epit(max_jegyzet=2)
        self.assertEqual((e.beagyazott_jegyzet, e.megszakitva), (2, True))
        e = self.epit()
        self.assertEqual((e.beagyazott_jegyzet, e.megszakitva, len(e.terv.uj)), (1, False, 1))

    def test_modellvaltas_ujraepit_es_hibas_beagyazo(self):
        self.epit()
        self.b = AlBeagyazo(nev="masik")
        e = self.epit()
        self.assertTrue(e.ujraepites)
        self.assertEqual(e.beagyazott_jegyzet, 4)

        class Rossz(AlBeagyazo):
            def __call__(self, szovegek, fajta):
                return []
        self.b = Rossz(nev="rossz")
        e = self.epit()
        self.assertEqual(len(e.hibak), 4)
        self.assertEqual(self.tar.allapot()["jegyzetek"], 0)

    def test_kapu_dont(self):
        from core.modell.aktivitas import Aktivitas
        from core.modell.kapu import Kapu
        ora = [1000.0]
        akt = Aktivitas(Path(self._t.name) / "aktivitas", rendszer=False, ido=lambda: 0.0)
        kapu = Kapu(akt, 10, 60, mem=lambda: 90, ido=lambda: ora[0])
        f = frissites.kapu_folytathat(kapu)
        self.assertFalse(f())                                    # D8: az indulás után még nem
        ora[0] += 61
        self.assertTrue(f())
        e = self.epit(folytathat=lambda: False)
        self.assertEqual((e.megszakitva, e.beagyazott_jegyzet), (True, 0))


class KeresoTest(AlvaultAlap):
    def setUp(self):
        super().setUp()
        self.epit()

    def test_beagyazo_nelkul_a_lexikai_valasz_valtozatlan(self):
        k = self.kereso(beagyazo=False)
        r = k.keres("spártai", 10)
        with self.ix._olvaso() as c:
            vart = kereses.keres(c, "spártai", 10)
        self.assertEqual({x: r[x] for x in vart}, vart)
        self.assertEqual((r["mod"], r["ok"]), ("lexikai", "nincs_beagyazo"))
        self.assertEqual(self.kereso().keres("spártai", 10, mod="lexikai")["ok"], "kert_lexikai")
        with self.assertRaises(Invalid):
            self.kereso().keres("  ")
        with self.assertRaises(Invalid):
            self.kereso().keres("x", mod="szemantikus")

    def test_legalabb_megmarad(self):
        r = self.kereso(beagyazo=False).keres("a", 1)                       # a lexikai korai leállás jele
        self.assertTrue(r["legalabb"])
        r = self.kereso(jelolt_n=1).keres("Spárta Athén Pannónia", 10)
        self.assertEqual(r["mod"], "hibrid")
        self.assertTrue(r["legalabb"])                                       # a lexikai ág elérte a jelöltkorlátot

    def test_jelentes_szerinti_talalat(self):
        q = "Mikor vették el a gyerekeket?"                                  # a „gyerek” szó nincs a vaultban
        with self.ix._olvaso() as c:
            self.assertEqual(kereses.keres(c, "gyerekeket")["osszes"], 0)
        r = self.kereso().keres(q, 5)
        self.assertEqual(r["mod"], "hibrid")
        self.assertEqual(r["talalatok"][0]["ut"], SPARTA)
        self.assertIn("vektor", r["talalatok"][0]["agak"])
        self.assertEqual(r["talalatok"][0]["darab"]["fejezet"], ["Spárta"])

    def test_ekezetfuggetlen(self):
        a = [t["ut"] for t in self.kereso().keres("spartai neveles", 3)["talalatok"]]
        b = [t["ut"] for t in self.kereso().keres("SPÁRTAI NEVELÉS", 3)["talalatok"]]
        self.assertEqual(a, b)
        self.assertEqual(a[0], SPARTA)

    def test_operatoros_kerdes_szur(self):
        r = self.kereso().keres("path:Róma borostyánút", 10)
        self.assertEqual([t["ut"] for t in r["talalatok"]], [PANNONIA])
        self.assertTrue(r["talalatok"][0]["talalatok"])                        # a sor-kiemelés a lexikai kereséstől
        r = self.kereso().keres("path:Hellász katonák", 10)                     # a szabad szó csak vektorral talál
        self.assertEqual({t["ut"] for t in r["talalatok"]} - {SPARTA, ATHEN}, set())
        r = self.kereso().keres("tag:#History", 10)                            # nincs szabad szó: lexikai
        self.assertEqual((r["mod"], r["ok"]), ("lexikai", "nincs_szabad_szo"))
        self.assertEqual(KR.szabad_szoveg('path:x "a b" -c line:(d e) OR f'), "a b d e f")

    def test_reranker(self):
        k = self.kereso(rerank=True, reranker=AlReranker("borostyán"))
        r = k.keres("Spárta Athén Pannónia", 3)
        self.assertEqual(r["talalatok"][0]["ut"], PANNONIA)
        self.assertIn("rerank", r["talalatok"][0])
        k = self.kereso(rerank=True, reranker=lambda q, d: [1.0])              # hibás válasz: a fúziós sorrend marad
        self.assertEqual(k.keres("Spárta Athén", 3)["mod"], "hibrid")

    def test_mas_modell_vektorai(self):
        k = KR.HibridKereso(self.ix._olvaso, self.tar, AlBeagyazo(nev="uj-modell"))
        self.assertEqual(k.miert_lexikai(), "mas_modell_vektorai")
        self.assertEqual(k.keres("Spárta")["mod"], "lexikai")
        self.assertEqual(KR.HibridKereso(self.ix._olvaso, None, self.b).miert_lexikai(), "nincs_vektortar")

    def test_darab_jeloltek(self):
        j = self.kereso().darab_jeloltek("hogyan harcoltak a hopliták", 3)
        self.assertEqual((j[0].darab.ut, j[0].darab.fejezet), (SPARTA, ("Spárta", "Hadsereg")))
        self.assertGreater(j[0].fedes, 0.5)
        self.assertIsNotNone(j[0].hasonlosag)
        lex = self.kereso(beagyazo=False).darab_jeloltek("hogyan harcoltak a hopliták", 3)
        self.assertEqual(lex[0].darab.fejezet, ("Spárta", "Hadsereg"))
        self.assertIsNone(lex[0].hasonlosag)

    def test_darab_jeloltek_vektortar_nelkul_az_indexbol(self):
        k = KR.HibridKereso(self.ix._olvaso, None, None)
        j = k.darab_jeloltek("borostyánút Itália", 2)
        self.assertEqual(j[0].darab.ut, PANNONIA)
        self.assertEqual(j[0].darab.id, -1)


# ====================================================================== „Kérdezz a vaulttól”

def sorok(*elemek):
    import json
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in elemek)


class KerdezzTest(AlvaultAlap):
    KERDES = "Hány évesen vették el a spártai fiúkat a családtól?"

    def setUp(self):
        super().setUp()
        self.epit()
        self.k = self.kereso()
        self.promptok = []

    def hivo(self, szoveg):
        def h(prompt, max_tokens):
            self.promptok.append(prompt)
            return szoveg
        return h

    def test_elfogadott_mondat_blokklinkkel_es_idezettel(self):
        v = kerdezz.valaszol(self.KERDES, self.k, self.hivo(sorok(
            {"mondat": "A spártai fiúkat hétévesen elvették a családtól.", "forras": 1,
             "idezet": "a fiúkat hétévesen elvették a családtól"})))
        self.assertEqual(v["allapot"], "kesz")
        m = v["mondatok"][0]
        self.assertEqual(m["link"], "[[T02 - Hellász/Elmélet/07 - Spárta#^nev1]]")
        self.assertEqual((m["ut"], m["blokk"], m["sor_kezd"]), (SPARTA, "nev1", 10))
        self.assertTrue(m["idezet"].startswith("A spártai nevelés kemény volt"))     # a jegyzet szó szerinti mondata
        self.assertTrue(v["proba"])                                                     # D9: nem kalibrált
        self.assertIn("[1] 07 - Spárta › Spárta", self.promptok[0])
        self.assertIn(self.KERDES, self.promptok[0])

    def test_forras_nelkuli_es_bukott_mondat_kiesik(self):
        v = kerdezz.valaszol(self.KERDES, self.k, self.hivo(sorok(
            {"mondat": "A spártai fiúkat hétévesen elvették a családtól.", "forras": 1,
             "idezet": "a fiúkat hétévesen elvették a családtól"},
            {"mondat": "Forrás nélküli állítás."},
            {"mondat": "Rossz számú forrás.", "forras": 99, "idezet": "a fiúkat hétévesen elvették a családtól"},
            {"mondat": "A Holdon is így volt.", "forras": 1, "idezet": "a Hold sajtból van ezt mindenki tudja"},
            {"mondat": "A spártai lányokat kilencévesen vitték el.", "forras": 1,
             "idezet": "a fiúkat hétévesen elvették a családtól"}) + "nem json sor\n"), kalibralt=True)
        self.assertEqual(len(v["mondatok"]), 1)
        self.assertEqual(v["elvetve"].get("nincs_forras"), 1)
        self.assertEqual(v["elvetve"].get("ismeretlen_forras"), 1)
        self.assertEqual(v["elvetve"].get("nem_json"), 1)
        self.assertTrue(any(k.startswith("kapu:") and "kotott" in k for k in v["elvetve"]))
        self.assertTrue(any(k.startswith("kapu:") and ("kenyes" in k or "tamogatas" in k) for k in v["elvetve"]))
        self.assertFalse(v["proba"])

    def test_nincs_eleg_forras_a_modell_nem_fut(self):
        v = kerdezz.valaszol("kvantumgravitáció húrelmélet szuperszimmetria", self.k, self.hivo("x"))
        self.assertEqual((v["allapot"], v["ok"]), ("nincs_valasz", "nincs_eleg_forras"))
        self.assertEqual(self.promptok, [])

    def test_nincs_valasz_ha_minden_kiesik_vagy_a_modell_szerint(self):
        v = kerdezz.valaszol(self.KERDES, self.k, self.hivo(sorok({"nincs": True})))
        self.assertEqual((v["allapot"], v["ok"]), ("nincs_valasz", "modell_szerint_nincs"))
        v = kerdezz.valaszol(self.KERDES, self.k, self.hivo(sorok({"mondat": "Kitalált.", "forras": 1,
                                                                  "idezet": "teljesen kitalált idézet a semmiből"})))
        self.assertEqual((v["allapot"], v["ok"], v["mondatok"]), ("nincs_valasz", "minden_mondat_kiesett", []))

    def test_modell_nelkul(self):
        v = kerdezz.valaszol(self.KERDES, self.k, None)
        self.assertEqual(v["allapot"], "nincs_modell")
        self.assertTrue(v["forrasok"])
        with self.assertRaises(Invalid):
            kerdezz.valaszol(" ", self.k, None)

    def test_folyam_megszakitas_a_kovetkezo_tokennel(self):
        huzott, megszakitva = [], []
        mondat = sorok({"mondat": "A spártai fiúkat hétévesen elvették a családtól.", "forras": 1,
                        "idezet": "a fiúkat hétévesen elvették a családtól"})

        def tokenek(prompt, max_tokens):
            for i in range(1000):
                huzott.append(i)
                yield mondat if i % 2 == 0 else ""
        g = kerdezz.folyam(self.KERDES, self.k, tokenek, megszakit=lambda: megszakitva.append(True))
        tipusok = []
        for e in g:
            tipusok.append(e["tipus"])
            if e["tipus"] == "mondat":
                break
        g.close()
        self.assertEqual(tipusok, ["forrasok", "mondat"])
        self.assertLessEqual(len(huzott), 2)                                      # a generátor nem húzott tovább
        self.assertEqual(megszakitva, [True])

    def test_max_mondat_es_cimsor_horgony(self):
        m = {"mondat": "A hopliták falanxban harcoltak.", "forras": 1, "idezet": "A hopliták falanxban harcoltak"}
        b = kerdezz.Beallitas(max_mondat=1)
        v = kerdezz.valaszol("hogyan harcoltak a hopliták falanxban", self.k, self.hivo(sorok(m, m)), b=b)
        self.assertEqual(len(v["mondatok"]), 1)
        self.assertEqual(v["elvetve"], {"tobb_mondat": 1})
        self.assertEqual(v["mondatok"][0]["link"], "[[T02 - Hellász/Elmélet/07 - Spárta#Hadsereg]]")
        self.assertIsNone(v["mondatok"][0]["blokk"])

    def test_sorok_es_json(self):
        self.assertEqual(list(kerdezz.sorok(["ab", "c\nd", "e\n", "f"])), ["abc", "de", "f"])
        self.assertEqual(kerdezz._json_sor('  {"a": 1},'), {"a": 1})
        self.assertIsNone(kerdezz._json_sor("```json"))
        self.assertIsNone(kerdezz._json_sor("[1, 2]"))

    def test_profil_az_os_tomlbol(self):
        p = kerdezz.profil(self.cfg)
        self.assertEqual((p.nev, p.idezet_min_szo, p.idezet_max_szo), ("valasz", 4, 120))
        self.assertEqual(kerdezz.profil().idezet_max_szo, p.idezet_max_szo)
        self.assertEqual(kerdezz.beallitas(self.cfg), kerdezz.Beallitas())
        self.assertEqual(KR.beallitas(self.cfg), KR.Beallitas(vektor=True, rerank=True))     # C25b mérés: M12 szerint be
        self.cfg.data.setdefault("kereses", {}).setdefault("hibrid", {})["ismeretlen"] = 1
        with self.assertRaises(ValueError):
            KR.beallitas(self.cfg)


# ====================================================================== mérő és regresszió-kapu

class MeresTest(AlvaultAlap):
    PAROK = [{"id": "k1", "tipus": "atfogalmazott", "kerdes": "Mikor vették el a gyerekeket?", "cel": SPARTA},
             {"id": "k2", "tipus": "kulcsszavas", "kerdes": "borostyánút Balti-tenger", "cel": PANNONIA},
             {"id": "k3", "tipus": "ekezet_nelkul", "kerdes": "athen nepgyules", "cel": ATHEN}]

    def meres(self):
        from modulok.eval.kereses import hibrid
        return hibrid

    def test_dontes_m12(self):
        d = self.meres().dontes
        self.assertEqual(d({"fts": {"recall5": 0.5}})["javasolt"], "fts")
        r = d({"fts": {"recall5": 0.5}, "fts_rerank": {"recall5": 0.6}, "fts_vektor": {"recall5": 0.61}})
        self.assertEqual((r["rerank"], r["vektor"], r["javasolt"]), (True, False, "fts_rerank"))   # a vektor nem jobb a rerankesnél
        r = d({"fts": {"recall5": 0.5}, "fts_rerank": {"recall5": 0.6}, "fts_vektor": {"recall5": 0.7},
               "fts_vektor_rerank": {"recall5": 0.7}})
        self.assertEqual((r["vektor"], r["javasolt"]), (True, "fts_vektor"))                        # holtverseny: az olcsóbb
        r = d({"fts": {"recall5": 0.5}, "fts_rerank": {"nem_mert": "nincs_reranker"}, "fts_vektor": {"recall5": 0.53}})
        self.assertEqual((r["rerank"], r["vektor"]), (False, True))
        self.assertIsNone(d({})["javasolt"])

    def test_regresszio(self):
        r = self.meres().regresszio
        self.assertEqual(r({"recall5": 0.8, "recall10": 0.9, "mrr": 0.7}, {"recall5": 0.8, "recall10": 0.85, "mrr": 0.6}), [])
        self.assertEqual(len(r({"recall5": 0.7, "recall10": 0.9, "mrr": 0.7}, {"recall5": 0.8}, tures=0.05)), 1)
        self.assertEqual(r({"recall5": 0.76}, {"recall5": 0.8}, tures=0.05), [])

    def test_futtat_es_kapu(self):
        """A regresszió-kapu az álvaulton: a hibrid mód egyik mutatója sem rosszabb a lexikai alapszintnél, és a
        jelentés szerinti kérdést (k1) csak a vektor-ág találja meg."""
        m = self.meres()
        self.epit()
        r = m.futtat(self.kereso(), self.PAROK, halmaz="teszt")
        v = r["valtozatok"]
        self.assertEqual(v["fts_rerank"], {"nem_mert": "nincs_reranker"})
        self.assertEqual(m.regresszio(v["fts_vektor"], v["fts"]), [])
        self.assertGreater(v["fts_vektor"]["recall5"], v["fts"]["recall5"])
        self.assertEqual([x["id"] for x in v["fts"]["rossz"]], ["k1"])
        self.assertTrue(r["dontes"]["vektor"])
        self.assertEqual(r["halmaz"], "teszt")
        lex = m.futtat(self.kereso(beagyazo=False), self.PAROK)["valtozatok"]
        self.assertEqual(lex["fts_vektor"], {"nem_mert": "nincs_beagyazo"})
        r = m.futtat(self.kereso(reranker=AlReranker("borostyán")), self.PAROK)
        self.assertIn("recall5", r["valtozatok"]["fts_vektor_rerank"])

    def test_a_valodi_halmaz_formaja(self):
        """A fagyasztott `parok.json` a mérő bemenete: minden párnak van azonosítója, típusa, kérdése és célja."""
        self.meres()                                         # a mérő a modulok/eval/kereses útját a sys.path-ra teszi
        import korpusz
        p = korpusz.parok()
        self.assertEqual(len(p["parok"]), 50)
        self.assertTrue(all({"id", "tipus", "kerdes", "cel"} <= set(x) for x in p["parok"]))


if __name__ == "__main__":
    unittest.main()
