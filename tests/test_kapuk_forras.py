"""C22a: a közös forráshűség-kapu forrás-előkészítése (`modulok/kapuk/forras.py`; `docs/C22-TERV.md` 1. fejezet).

Tiszta függvények: szöveg be, szerkezet ki. A jegyzet a vaultból jönne, de a teszt csak ideiglenes szöveget használ."""
import unicodedata
import unittest

from modulok.kapuk import forras as F

JEGYZET = """---
Tags: Történelem
Source: []
---
# A polgárháborúk kora

Bevezető mondat **vastaggal** és [[Másik jegyzet|szép névvel]] meg [[Útvonal/Cél]] linkkel. ^m-1a2b

%% rejtett megjegyzés, amely nem tartalom %%
<!-- HTML-megjegyzés -->
![[kep.png]]

## Az első triumvirátus

- Caesar kibékítette Crassust és Pompeiust (Kr. e. 60).
- [ ] Feladat-jelű sor szövege.

> [!note] Callout címe
> Idézett sor a calloutban.

Egy [md-link](https://pelda.hu/x) is van benne.

### Alfejezet $x$ szerepe

Az alfejezet szövege itt áll.

## Füzet

A füzetfotók szövege nem forrás.

### Füzet alfejezete

Ez is kimarad.

## Következmények

A senatus félt. Ezért szövetséget kötöttek.

```python
# ez nem fejezet
print("kód marad")
```

## Gyakorlás

![[Valami — kártyák]]
"""


class ElokeszitTest(unittest.TestCase):
    def setUp(self):
        self.sz = F.elokeszit(JEGYZET)

    def szoveg(self):
        return "\n".join(s.szoveg for s in self.sz)

    def test_a_tartalom_tisztitva(self):
        t = self.szoveg()
        self.assertNotIn("Tags", t)                                  # frontmatter
        self.assertNotIn("rejtett megjegyzés", t)                    # %%…%%
        self.assertNotIn("HTML-megjegyzés", t)
        self.assertNotIn("kep.png", t)                               # beágyazás
        self.assertNotIn("^m-1a2b", t)                               # blokkazonosító
        self.assertIn("szép névvel", t)                              # wikilink: a látható szöveg
        self.assertIn("Cél linkkel", t)                              # útvonal nélkül: az alapnév
        self.assertNotIn("Másik jegyzet", t)
        self.assertIn("Caesar kibékítette Crassust és Pompeiust (Kr. e. 60).", t)     # listajel nélkül
        self.assertNotIn("- Caesar", t)
        self.assertIn("Feladat-jelű sor szövege.", t)                # feladatjel nélkül
        self.assertNotIn("[ ]", t)
        self.assertIn("Idézett sor a calloutban.", t)                # idézetjel nélkül
        self.assertNotIn("[!note]", t)
        self.assertIn("Egy md-link is van benne.", t)                # md-link: a szöveg

    def test_fuzet_es_gyakorlas_szakasz_kiesik_az_alfejezetevel(self):
        t = self.szoveg()
        self.assertNotIn("füzetfotók", t)
        self.assertNotIn("Ez is kimarad", t)
        self.assertNotIn("Valami", t)
        self.assertIn("A senatus félt.", t)                          # a következő azonos szintű fejezet visszatér

    def test_a_kodblokk_szoveg_marad_es_nem_fejezet(self):
        self.assertIn('print("kód marad")', self.szoveg())
        self.assertNotIn("ez nem fejezet", [s.cim for s in self.sz if s.cim])

    def test_szakaszok_szerkezete(self):
        cimek = [(s.cim, s.ut) for s in self.sz]
        self.assertEqual(cimek[0], (None, ()))                       # a H1 alatti bevezető
        self.assertIn(("Az első triumvirátus", ("Az első triumvirátus",)), cimek)
        self.assertIn(("Alfejezet $x$ szerepe", ("Az első triumvirátus", "Alfejezet $x$ szerepe")), cimek)
        horgonyok = {s.cim: s.horgony for s in self.sz}
        self.assertEqual(horgonyok["Az első triumvirátus"], "Az első triumvirátus")
        self.assertIsNone(horgonyok["Alfejezet $x$ szerepe"])        # a `$` töri a horgonyt (Obsidian-link)

    def test_rovid_szakasz_a_min_karakterrel_kiesik(self):
        rovid = "# C\n\n## A\n\nhat\n\n## B\n\nEz egy elég hosszú mondat a szakaszban.\n"
        self.assertEqual([s.cim for s in F.elokeszit(rovid)], ["A", "B"])
        self.assertEqual([s.cim for s in F.elokeszit(rovid, min_karakter=20)], ["B"])

    def test_vegleges_sorvegek_es_nfc(self):
        nfd = unicodedata.normalize("NFD", "# C\n\n## Á\r\n\r\nÉgő házak füstje.\r\n")
        sz = F.elokeszit(nfd)
        self.assertEqual(sz[0].cim, "Á")
        self.assertEqual(sz[0].szoveg, "Égő házak füstje.")


class ForrasSzovegTest(unittest.TestCase):
    def setUp(self):
        self.f = F.ForrasSzoveg(F.elokeszit(JEGYZET))

    def test_pontos_idezet_a_szakasszal(self):
        t = self.f.keres("kibékítette Crassust és Pompeiust")
        self.assertIsNotNone(t)
        self.assertEqual(t.hasonlosag, 1.0)
        self.assertEqual(self.f.szakaszok[t.szakasz].cim, "Az első triumvirátus")
        self.assertEqual(self.f.szoveg[t.hely[0]:t.hely[1]], "kibékítette Crassust és Pompeiust")

    def test_jelolestol_es_kis_nagybetutol_fuggetlen(self):
        t = self.f.keres("a SENATUS félt ezért szövetséget kötöttek")
        self.assertIsNotNone(t)
        self.assertEqual(self.f.szakaszok[t.szakasz].cim, "Következmények")

    def test_egy_elutes_meg_idezet(self):
        self.assertIsNotNone(self.f.keres("A senatus félt. Ezért szövetsget kötöttek.", kuszob=0.85))

    def test_nincs_ilyen_idezet(self):
        self.assertIsNone(self.f.keres("Nero tűzbe borította az egész birodalmat éjszaka"))
        self.assertIsNone(self.f.keres(""))

    def test_a_fuzet_szakasz_szovege_nem_talalhato(self):
        self.assertIsNone(self.f.keres("A füzetfotók szövege nem forrás"))

    def test_nfc_es_a_helyek_az_nfc_szovegre_mutatnak(self):
        f = F.ForrasSzoveg(F.elokeszit(unicodedata.normalize("NFD", JEGYZET)))
        t = f.keres("A senatus félt")
        self.assertEqual(f.szoveg[t.hely[0]:t.hely[1]], "A senatus félt")


class MuveletiJelTest(unittest.TestCase):
    """A képlet előjele mérendő különbség: az idézet a jó mondatra illeszkedik (a legacy füstpróbája, 2026-09-27)."""
    FORRAS = F.ForrasSzoveg.jegyzetbol(
        "# C\n\n## Négyzetek\n\nA összeg négyzete: $(a+b)^2 = a^2 + 2ab + b^2$.\n\n"
        "A különbség négyzete: $(a-b)^2 = a^2 - 2ab + b^2$, vagyis a középső tag negatív.\n")

    def test_az_elojel_dont_a_mondatrol(self):
        t = self.FORRAS.keres("(a-b)^2 = a^2 - 2ab + b^2")
        self.assertIn("különbség négyzete", self.FORRAS.mondat(*t.hely))
        t = self.FORRAS.keres("(a+b)^2 = a^2 + 2ab + b^2")
        self.assertIn("összeg négyzete", self.FORRAS.mondat(*t.hely))

    def test_az_elojelet_felcserelo_idezet_nem_szo_szerinti(self):
        """Két előjel eltér a 15 tokenből: a betűszintű tűrés még közelítő találatnak veszi, de nem szó szerintinek
        (szigorú fogyasztó `idezet_kuszob = 1.0`-val kizárhatja)."""
        t = self.FORRAS.keres("(a-b)^2 = a^2 + 2ab - b^2", kuszob=0.85)
        self.assertLess(t.hasonlosag, 1.0)
        self.assertIsNone(self.FORRAS.keres("(a-b)^2 = a^2 + 2ab - b^2", kuszob=1.0))


class MondatTest(unittest.TestCase):
    def forras(self, szoveg):
        return F.ForrasSzoveg(F.elokeszit("# C\n\n## S\n\n" + szoveg + "\n"))

    def test_a_mondat_hataraira_bovit(self):
        f = self.forras("Az első mondat. A **második** mondat itt hosszabb, vesszővel is. A harmadik.")
        t = f.keres("második mondat itt hosszabb")
        self.assertEqual(f.mondat(*t.hely), "A második mondat itt hosszabb, vesszővel is.")

    def test_kepleten_belul_nem_vag(self):
        f = self.forras("Ha $a. b$ igaz, akkor a tétel érvényes. Következő.")
        t = f.keres("akkor a tétel érvényes")
        self.assertEqual(f.mondat(*t.hely), "Ha $a. b$ igaz, akkor a tétel érvényes.")

    def test_tul_hosszu_mondatnal_marad_a_talalt_resz(self):
        f = self.forras("Kezdet " + "szó " * 30 + "A KERESETT RÉSZ itt van " + "vég " * 30 + "Utolsó.")
        t = f.keres("A KERESETT RÉSZ itt van")
        self.assertEqual(f.mondat(*t.hely, max_k=60), "A KERESETT RÉSZ itt van")

    def test_paratlan_dollar_a_talalt_reszre_esik_vissza(self):
        f = self.forras("Egy ár $5 volt, és ez a mondat itt végződik. Következő mondat.")
        t = f.keres("ez a mondat itt végződik")
        self.assertEqual(f.mondat(*t.hely), "ez a mondat itt végződik")        # a kibővített mondatban páratlan a `$`


if __name__ == "__main__":
    unittest.main()
