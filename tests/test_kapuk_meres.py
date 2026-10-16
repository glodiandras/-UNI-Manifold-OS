"""C22a: a forráshűség-kapu mérése (`modulok/kapuk/meres.py`; `docs/C22-KAPU-MERES.md`): a rontások, a halmaz
determinizmusa, és a konfigurált küszöbök padlója a C18 `szoveg` halmaz első jegyzetein (a teljes mérés: `bin/mos kapu meres`)."""
import random
import unittest

from core import config
from modulok.kapuk import forras as F
from modulok.kapuk import huseg as H
from modulok.kapuk import meres as M
from modulok.kapuk import tokenek as T
from tests.eval_segedek import aranyt_igenyel

JEGYZET = "# Róma\n\n## Triumvirátus\n\nCaesar kibékítette Crassust és Pompeiust, majd szövetséget kötött velük a senatus ellen (Kr. e. 60). A szenátus tagjai Rómában ültek.\n"


class RontasTest(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random("teszt")
        self.fs = F.ForrasSzoveg.jegyzetbol(JEGYZET)

    def test_szamcsere_olyan_szamot_ad_amely_a_bizonyitekban_nincs(self):
        a = M._szam_csere("Kr. e. 60-ban szövetséget kötöttek.", {"60"}, self.rng)
        self.assertNotIn("60", a)
        self.assertRegex(a, r"Kr\. e\. \d+-ban")
        self.assertIsNone(M._szam_csere("Nincs benne szám.", set(), self.rng))

    def test_tagadas_egyszer_kerul_be_es_tagadott_allitasba_nem(self):
        self.assertEqual(M._tagadas_beszur("A senatus félt a hadvezértől."), "A senatus nem félt a hadvezértől.")
        self.assertIsNone(M._tagadas_beszur("A senatus nem félt a hadvezértől."))
        self.assertIsNone(M._tagadas_beszur("Rövid szó."))

    def test_nevcsere_a_jegyzet_masik_nevere(self):
        biz = "Caesar kibékítette Crassust és Pompeiust"
        a = M._nev_csere("Caesar szövetséget kötött Crassusszal.", self.fs, biz, True, self.rng)     # a mondaton belüli nevek
        self.assertIsNotNone(a)
        self.assertNotEqual(a, "Caesar szövetséget kötött Crassusszal.")
        kicsi = F.ForrasSzoveg.jegyzetbol("# R\n\n## T\n\nCaesar kibékítette Crassust és Pompeiust.\n")
        self.assertIsNone(M._nev_csere("Caesar szövetséget kötött Crassusszal.", kicsi, biz, False, self.rng))     # nincs más név
        kivul = M._nev_csere("Caesar szövetséget kötött Crassusszal.", self.fs, biz, False, self.rng)
        self.assertEqual(kivul, "Caesar szövetséget kötött Rómában.")        # a bizonyítékban nem álló név

    def test_idezet_rontasok(self):
        i = "majd szövetséget kötött velük a senatus ellen"
        self.assertEqual(M._kisbetu("A Senatus, ellen!"), "a senatus ellen")
        e = M._elutes(i, self.rng)
        self.assertEqual(len(e), len(i))
        self.assertEqual(sum(1 for x, y in zip(e, i) if x != y), 1)
        self.assertEqual(len(M._kihagy(i, self.rng).split()), len(i.split()) - 1)
        self.assertEqual(len(M._vagott(i, self.rng).split()), len(i.split()) - 1)
        self.assertIsNone(M._kihagy("túl rövid idézet", self.rng))
        k = M._kitalalt(i, self.fs, self.rng).split()
        self.assertGreaterEqual(sum(1 for x, y in zip(k, i.split()) if x != y), 2)


@aranyt_igenyel("szoveg")
class HalmazTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = M.halmaz(jegyzetek=3)
        cls.merdek = M.merj_esetek(cls.h)

    def test_determinisztikus_es_a_mag_valtoztat(self):
        elso = M.halmaz(jegyzetek=2)
        masik = M.halmaz(jegyzetek=2)
        self.assertEqual([(e.osztaly, e.allitas, e.idezet) for e in elso.esetek],
                         [(e.osztaly, e.allitas, e.idezet) for e in masik.esetek])
        mas_mag = M.halmaz(mag=2, jegyzetek=2)
        self.assertNotEqual([e.idezet for e in elso.esetek], [e.idezet for e in mas_mag.esetek])

    def test_minden_osztaly_van_es_a_pozitivok_a_forrasban_allnak(self):
        osztalyok = {e.osztaly for e in self.h.esetek}
        self.assertEqual(osztalyok, set(M.POZITIV + M.NEGATIV + M.LEIRO))
        for e in self.h.esetek:
            if e.osztaly in ("poz_teny", "poz_kulcsresz"):
                self.assertIsNotNone(self.h.forrasok[e.jegyzet].keres(e.idezet, 0.85), e.idezet)

    def test_az_arany_hash_rogzitve(self):
        self.assertEqual(len(self.h.arany_sha256), 64)
        self.assertIn("jegyzetek", self.h.arany)

    def test_a_merj_es_a_dont_megegyezik_az_ellenorizzel(self):
        p = H.Profil(idezet_min_szo=1, idezet_max_szo=None, tamogatas_kuszob=0.5)
        for e, m in self.merdek[:60]:
            self.assertEqual(H.dont(m, p).to_dict(), H.ellenoriz(self.h.forrasok[e.jegyzet], e.allitas, e.idezet, p).to_dict())

    def test_a_konfiguralt_kuszobok_padloja(self):
        """A `config/os.toml` `[kapuk]` küszöbeivel (hossz-határ nélkül): a pozitívok elfogadva, a rontások elutasítva
        (3 jegyzeten, tehát lazább padló, mint a teljes mérésben; a pontos számok a docs/C22-KAPU-MERES.md-ben)."""
        p = H.profil(config.load())
        p = H.Profil(**{**p.__dict__, "idezet_min_szo": 1, "idezet_max_szo": None})
        ered = M.kiertekel(self.merdek, p)
        for o in M.POZITIV:
            self.assertGreaterEqual(ered[o]["arany"], 0.80, o)
        for o in ("neg_szam", "neg_nev_kivul", "neg_idegen_jegyzet", "neg_kitalalt"):
            self.assertGreaterEqual(1 - ered[o]["arany"], 0.95, o)
        for o in ("neg_tagadas", "neg_masik_forras"):
            self.assertGreaterEqual(1 - ered[o]["arany"], 0.85, o)

    def test_a_kenyes_tokenek_es_a_tagadas_nelkul_a_rontasok_atmennek(self):
        """A mérés lényege: a puszta lefedettség a számot, a tagadást és a nevet nem fogja meg."""
        p = H.profil(config.load())
        ki = H.Profil(**{**p.__dict__, "idezet_min_szo": 1, "idezet_max_szo": None, "kenyes": False, "tagadas": "ki"})
        ered = M.kiertekel(self.merdek, ki)
        for o in ("neg_szam", "neg_tagadas", "neg_nev_kivul"):
            self.assertGreater(ered[o]["arany"], 0.5, o)

    def test_valasztas_es_pontszam(self):
        p, mutatok, padlo, cellak = M.valaszt(self.merdek)
        self.assertEqual(len(cellak), len(M.racs()))
        self.assertGreaterEqual(padlo, 0.8)
        self.assertGreaterEqual(mutatok["poz_min"], padlo)
        self.assertGreater(mutatok["neg_makro"], 0.8)

    def test_fragmens_hosszak(self):
        d = M.fragmens_hosszak(self.h.arany)
        self.assertEqual(d["n"], sum(len(j["tenyek"]) for j in self.h.arany["jegyzetek"]))
        self.assertLessEqual(d["min"], d["median"])
        self.assertLessEqual(d["median"], d["max"])

    def test_riport_es_minta_lap(self):
        p, mutatok, padlo, _ = M.valaszt(self.merdek)
        szoveg = M.riport(self.h, self.merdek, p, mutatok, padlo, "bin/mos kapu meres", "2026-10-04")
        for resz in ("# A közös forráshűség-kapu mérése", "```toml", "[kapuk]", "| `poz_teny`", "## Mit ér az egyes szabály",
                     "## Mit nem lát a kapu", "bin/mos kapu meres"):
            self.assertIn(resz, szoveg)
        m = M.minta(self.merdek, p, darab=8)
        for oldal in m.values():
            kulcsok = [(e.jegyzet, e.sorszam) for _, e, _, _ in oldal]
            self.assertEqual(len(kulcsok), len(set(kulcsok)))                   # tényenként egy eset
            self.assertEqual([x[0] for x in oldal], sorted(x[0] for x in oldal))     # a küszöbhöz közeliek elöl
        lap = M.minta_lap(self.merdek, p, self.h, darab=3)
        self.assertEqual(lap.count("**Jó a döntés?**"), 6)
        self.assertIn("Elfogadott párok", lap)
        self.assertIn("Elutasított párok", lap)


class TokenSzabalyTest(unittest.TestCase):
    def test_a_racs_minden_cellaja_ervenyes_profil(self):
        self.assertEqual(len(M.racs()), 5 * 6 * 3 * 2 * 3)


if __name__ == "__main__":
    unittest.main()
