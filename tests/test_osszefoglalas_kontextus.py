"""C26a: a kontextus-csomag és a visszamásolt külső AI-válasz feldolgozása (`modulok/osszefoglalas/kontextus.py`)."""
import json
import unittest

from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import kontextus as KX
from modulok.osszefoglalas import lanc as L
from tests.test_osszefoglalas_lanc import A1, A2, JEGYZET, Q1, RP, valasz

MASIK_RP = "M03 - Algebra/Elmélet/04 - Nevezetes szorzatok.md"
MASIK = """---
Source:
  - "[[10 - Matematika.pdf#page=93]]"
  - "[[Egyéb/Könyv.pdf]]"
---

# Nevezetes szorzatok

## Elméleti alapok

Két tag összegének négyzete: $(a+b)^2 = a^2 + 2ab + b^2$. Ezt teljes négyzetnek nevezzük.

Két tag különbségének négyzete: $(a-b)^2 = a^2 - 2ab + b^2$, vagyis a középső tag előjele negatív.
"""
JEGYZETEK = [KX.Jegyzet(RP, JEGYZET), KX.Jegyzet(MASIK_RP, MASIK)]


SZIVARGO = """---
Source:
  - "[[Mappa/Könyv.pdf#page=3]]"
---

# Szivárgó

## Alap

Szöveges link: [[T03 - Az ókori Róma/Rómaiak|a rómaiak]] és [[M01 - Matek/Függvények]] és ![[M01 - Matek/kep.png]].

Md-link: [a jegyzet](M01%20-%20Matek/F%C3%BCggv%C3%A9nyek.md) és file:///Volumes/Lemez/Vault/titok.md URL.

```text
[[M03 - Algebra/Elmélet/04 - Nevezetes szorzatok]]
/Volumes/Lemez/Vault/T03 - Az ókori Róma/Titok.md
```

Abszolút út: /Users/minta/Library/Mobile Documents/Vault/x.md és a ~/Documents/naplo.txt, valamint C:\\Users\\a\\b.txt.
Az osztás 1/2/3 és az "és/vagy" marad. A hányados a/b is.
"""


class SzivargasTest(unittest.TestCase):
    """A3-28: a csomagba mappa-út, abszolút út és `file:///` URL nem kerül (kódblokkban sem)."""

    def csomag(self) -> str:
        return KX.csomag([KX.Jegyzet("X01 - Titkos mappa/Szivárgó.md", SZIVARGO)]).szoveg

    def test_nincs_mappa_ut_a_linkekben_es_a_kodblokkban(self):
        sz = self.csomag()
        for tilos in ("T03 - Az ókori Róma", "M01 - Matek", "M03 - Algebra", "Elmélet/", "Mappa/", "X01 - Titkos"):
            self.assertNotIn(tilos, sz)

    def test_nincs_abszolut_ut_es_file_url(self):
        sz = self.csomag()
        for tilos in ("/Volumes", "/Users", "file://", "~/Documents", "C:\\Users", "Titok.md", "titok.md", "Mobile Documents"):
            self.assertNotIn(tilos, sz)

    def test_a_szoveg_tobbi_resze_megmarad(self):
        sz = self.csomag()
        for marad in ("a rómaiak", "Függvények", "1/2/3", "és/vagy", "a/b", "a jegyzet"):
            self.assertIn(marad, sz)


class CsomagTest(unittest.TestCase):
    def test_azonositok_utvonal_nelkul(self):
        c = KX.csomag(JEGYZETEK, kerdes="Mi történt Rómában?")
        self.assertEqual(c.benne, ["J1", "J2"])
        self.assertEqual(c.azonositok, {"J1": RP, "J2": MASIK_RP})
        for resz in ("T03 - Az ókori Róma", "M03 - Algebra", "Elmélet/", ".md"):
            self.assertNotIn(resz, c.szoveg)                                  # az útvonal helyben marad
        self.assertIn("=== J1 · A polgárháborúk kora és Caesar", c.szoveg)
        self.assertIn("=== J2 · Nevezetes szorzatok (forrás: 10 - Matematika.pdf, 93. oldal; Könyv.pdf) ===", c.szoveg)
        self.assertIn("(Mi történt Rómában?)", c.szoveg)
        self.assertIn('"forras": "J1"', c.szoveg)                              # a külső AI szabályai a csomagban
        self.assertIn("SZÓ SZERINTI", c.szoveg)

    def test_a_tisztitott_szoveg_kerul_bele(self):
        c = KX.csomag(JEGYZETEK)
        self.assertNotIn("Tags", c.szoveg)                                     # frontmatter nélkül
        self.assertNotIn("IMG_0001", c.szoveg)                                 # gép írta szakasz nélkül
        self.assertNotIn("^m-3f2a", c.szoveg)
        self.assertIn("## Az első triumvirátus", c.szoveg)
        self.assertEqual(c.csonkolt, [])
        self.assertEqual(c.karakter, len(c.szoveg))

    def test_meretkorlat_bekezdeshataron_csonkit(self):
        nagy = KX.Jegyzet(RP, "# N\n\n## A\n\n" + "\n\n".join(f"A(z) {i}. bekezdés szövege elég hosszú, hogy a keret elfogyjon." for i in range(60)))
        c = KX.csomag([nagy, JEGYZETEK[1]], max_karakter=2500)
        self.assertLessEqual(c.karakter, 2500)
        self.assertEqual(c.csonkolt, ["J1"])
        self.assertIn(KX.CSONKOLAS_JEL, c.szoveg)
        self.assertEqual(c.benne, ["J1", "J2"])                                # a kicsi jegyzet teljes
        for sor in c.szoveg.splitlines():
            if sor.startswith("A(z)"):
                self.assertTrue(sor.endswith("elfogyjon."))                    # félmondatot nem vág
        self.assertEqual(c.csonkolt.count("J2"), 0)

    def test_nem_fero_es_ures_jegyzet(self):
        c = KX.csomag([KX.Jegyzet("U.md", "---\nTags: []\n---\n"), JEGYZETEK[1]])
        self.assertEqual(c.benne, ["J2"])
        self.assertEqual(c.kihagyott, [{"azon": "J1", "ut": "U.md", "ok": "ures"}])
        with self.assertRaises(L.Megall):
            KX.csomag(JEGYZETEK, max_karakter=300)
        with self.assertRaises(L.Megall):
            KX.csomag([])

    def test_determinisztikus(self):
        self.assertEqual(KX.csomag(JEGYZETEK).szoveg, KX.csomag(JEGYZETEK).szoveg)

    def test_forras_feliratok(self):
        self.assertEqual(KX.forras_feliratok(MASIK), ["10 - Matematika.pdf, 93. oldal", "Könyv.pdf"])
        self.assertEqual(KX.forras_feliratok("# Nincs frontmatter"), [])
        self.assertEqual(KX.forras_feliratok("---\n: : [\n---\n"), [])


def kulso(forras, allitas, idezet):
    return {"allitas": allitas, "forras": forras, "idezet": idezet}


class ValaszTest(unittest.TestCase):
    def test_a_kapun_atment_allitasok_osszefoglalova_allnak(self):
        r = valasz(
            kulso("J1", A2["allitas"], A2["idezet"]),
            kulso("J1", A1["allitas"], A1["idezet"]),
            kulso("J2", "A két tag összegének négyzete az $a^2 + 2ab + b^2$ kifejezés.", "Két tag összegének négyzete: $(a+b)^2 = a^2 + 2ab + b^2$."),
            kulso("J1", "Caesar Britanniában győzött.", "Caesar Britanniában két hadjáratot vezetett és győzött a kelták felett"),     # nincs a jegyzetben
            kulso("J1", "Caesar legyőzte a gallokat.", ""),                                                                      # forrás nélkül
            kulso("J7", "Valami egészen más állítás.", "Valami egészen más idézet a semmiből"),                                  # ismeretlen jegyzet
            kulso("", "Azonosító nélküli állítás szöveg.", Q1))
        e = KX.valasz_feldolgoz(r, JEGYZETEK, cim="Róma és algebra")
        o = e.osszefoglalo
        self.assertEqual(o.szint, "kontextus")
        self.assertEqual(o.modell, "külső AI")
        self.assertEqual([a.id for a in o.allitasok], ["a1", "a2", "a3"])
        # jegyzetek sorrendje, jegyzeten belül a forráshely szerint
        self.assertEqual([a.szoveg[:12] for a in o.allitasok], ["Caesar kibék", "Caesar katon", "A két tag ös"])
        self.assertEqual(o.forrasok, [RP.removesuffix(".md"), MASIK_RP.removesuffix(".md")])
        self.assertEqual(e.statisztika["elvetve"], {"idezet": 1, "forras_nelkul": 1, "ismeretlen_forras": 2})
        self.assertEqual(o.allitasok[2].horgony.link(), f"[[{MASIK_RP.removesuffix('.md')}#Elméleti alapok|forrás]]")
        self.assertEqual(FM.elemez(FM.ir(o)).hibak, [])

    def test_torzs_a_kezi_beillesztesre(self):
        e = KX.valasz_feldolgoz(valasz(kulso("J1", A1["allitas"], A1["idezet"])), JEGYZETEK)
        torzs = FM.torzs(e.osszefoglalo)
        self.assertTrue(torzs.startswith("## Állítások\n\n1. "))
        self.assertNotIn("Szint:", torzs)                                     # frontmatter nélkül

    def test_azonosito_alakok(self):
        for forras in ("J1", "j1", "[J1]", " J 1 "):
            e = KX.valasz_feldolgoz(valasz(kulso(forras, A1["allitas"], A1["idezet"])), JEGYZETEK)
            self.assertEqual(len(e.osszefoglalo.allitasok), 1, forras)
        e = KX.valasz_feldolgoz(valasz(kulso("J0", A1["allitas"], A1["idezet"])), JEGYZETEK)
        self.assertEqual(len(e.osszefoglalo.allitasok), 0)

    def test_ertelmezhetetlen_valasz_nem_kivetel(self):
        e = KX.valasz_feldolgoz("Sajnos ehhez nincs elég információm.", JEGYZETEK)
        self.assertEqual(e.osszefoglalo.allitasok, [])
        self.assertEqual(e.statisztika["nem_ertelmezheto"], 1)

    def test_a_kerit_es_a_burok_tures(self):
        szoveg = "Íme:\n```json\n" + json.dumps({"allitasok": [kulso("J1", A1["allitas"], A1["idezet"])]}, ensure_ascii=False) + "\n```"
        self.assertEqual(len(KX.valasz_feldolgoz(szoveg, JEGYZETEK).osszefoglalo.allitasok), 1)


if __name__ == "__main__":
    unittest.main()
