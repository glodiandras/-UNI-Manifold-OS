"""C22a: a kvízlánc modell nélküli része (`modulok/kviz/generalas.py`) — a legacy kvíz-tesztek portja álmodellel.

A modellhívás két hívható mögött áll (`generalo`, `ellenorzo`); a teszt forgatókönyvezett válaszokat ad. A vaultba nem ír."""
import re
import unittest

from modulok.kapuk import forras as KF
from modulok.kviz import formatum as FM
from modulok.kviz import generalas as G

RP = "M03 - Algebra/Elmélet/04 - Nevezetes szorzatok.md"
JEGYZET = """---
Tags:
  - Mathematics
Source:
  - "[[10 - Matematika.pdf#page=93]]"
Status:
NN:
Canvas: "[[M03 - Algebra.canvas]]"
---

# Nevezetes szorzatok

## Elméleti alapok

Két tag összegének négyzete: $(a+b)^2 = a^2 + 2ab + b^2$. Ezt **teljes négyzetnek** nevezzük.

Két tag különbségének négyzete: $(a-b)^2 = a^2 - 2ab + b^2$, vagyis a középső tag előjele negatív.

## Szorzattá alakítás

Az $a^2 - b^2$ kifejezés szorzattá alakítva $(a+b)(a-b)$, ezt két négyzet különbségének hívjuk.

## Füzet

![[IMG_0001.JPG]]
"""

# az álmodell generáló válasza: 3 jó kérdés + 3, amelyet egy-egy kapu ejt ki
GEN = """1. KÉRDÉS: Mi a $(a+b)^2$ kifejtése?
A) $a^2 + b^2$
B) $a^2 + 2ab + b^2$
C) $a^2 - 2ab + b^2$
D) $2a + 2b$
HELYES: B
IDÉZET: „Két tag összegének négyzete: $(a+b)^2 = a^2 + 2ab + b^2$.”
MAGYARÁZAT: A középső tag a kétszeres szorzat; tipikus hiba kihagyni.

**KÉRDÉS:** Milyen előjelű a középső tag két tag különbségének négyzetében?
- A) pozitív
- B) negatív
- C) nulla
- D) mindegyik
HELYES: B
IDÉZET: a középső tag előjele negatív
MAGYARÁZAT: mert $-2ab$.

KÉRDÉS: Mi az $a^2 - b^2$ szorzattá alakított alakja?
A) $(a-b)^2$
B) $(a+b)^2$
C) $(a+b)(a-b)$
D) $a(a-b)$
Helyes válasz: C)
IDÉZET: Az a^2 - b^2 kifejezés szorzattá alakítva (a+b)(a-b), ezt két négyzet különbségének hívjuk.
MAGYARÁZAT: Két négyzet különbsége.

KÉRDÉS: Hogyan nevezzük az $(a+b)^2$ kifejtését?
A) teljes négyzet
B) két négyzet különbsége
C) kétszeres szorzat
D) középső tag
HELYES: A
IDÉZET: Ezt teljes négyzetnek nevezzük.
MAGYARÁZAT: Így hívjuk.

KÉRDÉS: Mit mond a jegyzet a harmadfokú tagokról?
A) mindig pozitívak
B) mindig negatívak
C) nullák
D) nincsenek
HELYES: A
IDÉZET: A harmadfokú tagok mindig pozitívak a jegyzet szerint.
MAGYARÁZAT: kitalált.

KÉRDÉS: Minek hívjuk az $a^2 - b^2$ alakú kifejezést?
A) két négyzet különbségének
B) teljes négyzetnek
C) két tag összegének
D) harmadfokú tagnak
HELYES: A
IDÉZET: ezt két négyzet különbségének hívjuk
MAGYARÁZAT: A név a két négyzetes tagra utal.
"""
# a vak ellenőrzés „tudása": kérdés → a helyesnek tartott válasz (a „teljes négyzet" kérdésnél szándékosan rossz; a rossz
# válaszok a jegyzet szavai, hogy a kérdést ne a `hihetetlen` kapu ejtse ki, hanem a vak ellenőrzés)
TUDAS = {"Mi a $(a+b)^2$ kifejtése?": "$a^2 + 2ab + b^2$",
         "Mi az $a^2 - b^2$ szorzattá alakított alakja?": "$(a+b)(a-b)$",
         "Minek hívjuk az $a^2 - b^2$ alakú kifejezést?": "két négyzet különbségének",
         "Hogyan nevezzük az $(a+b)^2$ kifejtését?": "két négyzet különbsége"}

B = G.Beallitas(karakter_per_kerdes=50)       # a rövid próbajegyzetből több jelölt kell (a valódi jegyzetek hosszabbak)


class Almodell:
    """A generáló és az ellenőrző hívás forgatókönyvvel; a hívásokat rögzíti."""

    def __init__(self, gen=GEN, tudas=TUDAS):
        self.gen, self.tudas = gen, tudas
        self.generalo_promptok: list[str] = []
        self.ellenorzo_promptok: list[str] = []

    def generalo(self, prompt: str, max_tokens: int) -> str:
        self.generalo_promptok.append(prompt)
        return self.gen

    def ellenorzo(self, prompt: str, max_tokens: int) -> str:
        self.ellenorzo_promptok.append(prompt)
        m = re.search(r"KÉRDÉS: (.*)\n((?:[ABCD]\) .*\n?)+)", prompt)
        for betu, opcio in re.findall(r"([ABCD])\) (.*)", m.group(2)):
            if opcio == self.tudas.get(m.group(1)):
                return betu
        return "A helyes válasz nem egyértelmű."


def kviz(n=3, modell=None, **kw):
    modell = modell or Almodell()
    kw.setdefault("b", B)
    return G.general(JEGYZET, RP, modell.generalo, modell.ellenorzo, n=n, modell="org/kis", **kw), modell


class SzetszedTest(unittest.TestCase):
    def test_valasz_olvasasa(self):
        j = G.szetszed(GEN)
        self.assertEqual(len(j), 6)
        self.assertEqual(j[1].valaszok["D"], "mindegyik")             # „- A)” alakú opció is
        self.assertEqual(j[2].helyes, "C")                            # „Helyes válasz: C)”
        self.assertEqual(j[0].idezet[:4], "Két ")                     # az idézőjel lekerül
        self.assertEqual(j[0].kerdes, "Mi a $(a+b)^2$ kifejtése?")

    def test_betu(self):
        self.assertEqual(G.betu("B"), "B")
        self.assertEqual(G.betu("C) mert…"), "C")
        self.assertEqual(G.betu("A\nmert így"), "A")
        self.assertIsNone(G.betu("A helyes válasz nem egyértelmű."))   # a névelő nem betűválasz
        self.assertEqual(G.betu("A helyes válasz: D"), "D")
        self.assertIsNone(G.betu(""))
        self.assertEqual(G.betu("**B**"), "B")


class SzakaszolasTest(unittest.TestCase):
    def test_darabok_es_kiosztas(self):
        szak = KF.elokeszit(JEGYZET, min_karakter=20)
        self.assertEqual([s.cim for s in szak], ["Elméleti alapok", "Szorzattá alakítás"])      # a Füzet kimarad
        d = G.darabok(szak, 2200)
        self.assertEqual(len(d), 1)                                   # kis jegyzet: egy darab
        self.assertIn("[Elméleti alapok]", d[0]["szoveg"])
        kio = G.kiosztas(d, 3, B)
        self.assertEqual(len(kio), 1)
        self.assertGreaterEqual(kio[0], 3)                            # túlgenerálás: több jelölt, mint kérdés
        hosszu = [KF.Szakasz(("A",), "A", "A", ("Hosszú bekezdés " * 40 + "\n\n") * 6)]
        self.assertGreater(len(G.darabok(hosszu, 600)), 1)            # a hosszú szakasz bekezdéshatáron darabolva

    def test_a_kiosztas_a_darab_hosszat_aranyosan_osztja(self):
        d = [{"karakter": 1000, "szoveg": "", "szakaszok": [0]}, {"karakter": 3000, "szoveg": "", "szakaszok": [1]}]
        kio = G.kiosztas(d, 10, G.Beallitas(karakter_per_kerdes=150, tulgeneralas=1.0))
        self.assertEqual(sum(kio), 10)
        self.assertGreater(kio[1], kio[0])

    def test_jaccard(self):
        self.assertGreaterEqual(G.jaccard("Mi a kifejtés négyzete?", "Mi a négyzet kifejtése?"), 0.6)
        self.assertLess(G.jaccard("Mi a kifejtés?", "Ki volt Caesar?"), 0.3)


class GeneralasTest(unittest.TestCase):
    def test_harom_kapu(self):
        e, modell = kviz()
        k = e.kviz
        self.assertEqual([q.kerdes for q in k.kerdesek],
                         ["Mi a $(a+b)^2$ kifejtése?", "Mi az $a^2 - b^2$ szorzattá alakított alakja?",
                          "Minek hívjuk az $a^2 - b^2$ alakú kifejezést?"])
        self.assertEqual(e.statisztika["elvetve"], {"tiltott_valasz": 1, "ellenorzes": 1, "idezet": 1})
        q = k.kerdesek[0]
        self.assertEqual(q.valaszok[q.helyes], "$a^2 + 2ab + b^2$")      # a keverés után is a jó kulcs
        self.assertEqual((q.szakasz, q.horgony), ("Elméleti alapok", "Elméleti alapok"))
        self.assertEqual(k.kerdesek[1].idezet,
                         "Az $a^2 - b^2$ kifejezés szorzattá alakítva $(a+b)(a-b)$, ezt két négyzet különbségének hívjuk.")
        self.assertEqual(k.kerdesek[1].szakasz, "Szorzattá alakítás")
        self.assertEqual(e.statisztika["lefedett_szakasz"], 2)
        self.assertEqual([q.id for q in k.kerdesek], ["k1", "k2", "k3"])
        self.assertEqual((k.cim, k.forras, k.modell), ("Nevezetes szorzatok", RP[:-3], "org/kis"))
        self.assertTrue(FM.AZON_RE.match(k.azon), k.azon)

    def test_az_elvetett_jeloltek_okokkal(self):
        e, _ = kviz()
        self.assertEqual(sorted(x["ok"] for x in e.elvetett), ["ellenorzes", "idezet", "tiltott_valasz"])
        ok = {x["kerdes"]: x["ok"] for x in e.elvetett}
        self.assertEqual(ok["Mit mond a jegyzet a harmadfokú tagokról?"], "idezet")
        self.assertEqual(ok["Hogyan nevezzük az $(a+b)^2$ kifejtését?"], "ellenorzes")

    def test_a_vak_ellenorzes_kevert_sorrendet_kap_kulcs_nelkul(self):
        e, modell = kviz()
        self.assertTrue(modell.ellenorzo_promptok)
        for p in modell.ellenorzo_promptok:
            self.assertNotIn("HELYES", p)
            self.assertNotIn("IDÉZET", p)
        elso = next(p for p in modell.ellenorzo_promptok if "Mi a $(a+b)^2$ kifejtése?" in p)
        self.assertNotIn("A) $a^2 + b^2$\nB) $a^2 + 2ab + b^2$", elso)    # nem az eredeti sorrend
        e2, m2 = kviz()
        self.assertEqual(m2.ellenorzo_promptok, modell.ellenorzo_promptok)     # determinisztikus

    def test_a_kviz_vegig_a_formatumon(self):
        e, _ = kviz()
        szoveg = FM.ir(e.kviz)
        ujra = FM.elemez(szoveg)
        self.assertEqual(ujra.hibak, [])
        self.assertEqual(ujra.kviz, e.kviz)

    def test_korabbi_kerdesek_kerulendo_es_kiesnek(self):
        korabbi = ["Mi a $(a+b)^2$ kifejtése?", "Mi az $a^2 - b^2$ szorzattá alakított alakja?",
                   "Minek hívjuk az $a^2 - b^2$ alakú kifejezést?"]
        modell = Almodell()
        with self.assertRaises(G.Megall):                                # a modell ugyanazt adja: mind korábbi
            kviz(modell=modell, korabbi=korabbi)
        self.assertIn("ne ismételd", modell.generalo_promptok[-1])
        self.assertIn(korabbi[0], modell.generalo_promptok[-1])

    def test_keves_kerdes_megall(self):
        modell = Almodell(tudas={})                                      # a vak ellenőrzés semmire nem felel
        with self.assertRaises(G.Megall) as cm:
            kviz(modell=modell)
        self.assertIn("a kvíz nem készült el", str(cm.exception))

    def test_bemenet(self):
        modell = Almodell()
        with self.assertRaises(G.Megall):
            G.general(JEGYZET, RP, modell.generalo, modell.ellenorzo, n=31, modell="x", b=B)
        with self.assertRaises(G.Megall):
            G.general(JEGYZET, RP, modell.generalo, modell.ellenorzo, n=2, modell="x", b=B)
        with self.assertRaises(G.Megall):
            G.general(JEGYZET, RP, modell.generalo, modell.ellenorzo, n=3, modell="", b=B)
        with self.assertRaises(G.Megall):                                 # nincs kérdezhető szöveg
            G.general("# Üres\n\n## Füzet\n\n![[x.jpg]]\n", "Üres.md", modell.generalo, modell.ellenorzo, n=3, modell="x", b=B)

    def test_a_tamogatatlan_kulcs_a_kozos_kapun_bukik(self):
        """Az idézet a jegyzetben áll, de a helyes válasz nem abból következik: a legacy ezt nem fogta meg."""
        gen = GEN.replace("HELYES: B\nIDÉZET: „Két tag összegének négyzete",
                          "HELYES: D\nIDÉZET: „Két tag összegének négyzete")           # a „2a + 2b” a kulcs: nincs az idézetben
        modell = Almodell(gen=gen, tudas={**TUDAS, "Mi a $(a+b)^2$ kifejtése?": "$2a + 2b$"})
        e, _ = kviz(modell=modell, b=G.Beallitas(karakter_per_kerdes=50, kerdes_min=1))
        self.assertEqual(e.statisztika["elvetve"].get("tamogatas") or e.statisztika["elvetve"].get("kenyes"), 1)
        self.assertNotIn("Mi a $(a+b)^2$ kifejtése?", [q.kerdes for q in e.kviz.kerdesek])

    def test_valaszt_szakaszonkent_koronde(self):
        elfogadott = [{"si": 0, "id": "a"}, {"si": 0, "id": "b"}, {"si": 1, "id": "c"}, {"si": 1, "id": "d"}, {"si": 2, "id": "e"}]
        self.assertEqual([x["id"] for x in G.valaszt(elfogadott, 3)], ["a", "c", "e"])
        self.assertEqual([x["id"] for x in G.valaszt(elfogadott, 10)], ["a", "b", "c", "d", "e"])


class BeallitasTest(unittest.TestCase):
    def test_az_os_toml_szakasza_ervenyes_es_egyezik_az_alapokkal(self):
        from core import config
        b = G.beallitas(config.load())
        self.assertEqual(b, G.Beallitas())                      # az `os.toml` a legacy alapértékeit hordozza
        self.assertEqual(config.load().section("kviz")["mappa"], "ATTCHMNTS - quizes")

    def test_ismeretlen_kulcs_hiba(self):
        class Cfg:
            def section(self, *_):
                return {"kerdes_alap": 5, "nincs_ilyen": 1}
        with self.assertRaises(ValueError):
            G.beallitas(Cfg())


if __name__ == "__main__":
    unittest.main()
