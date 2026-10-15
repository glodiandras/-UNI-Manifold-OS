"""C22a: a közös forráshűség-kapu szabályai (`modulok/kapuk/huseg.py`, `tokenek.py`; `docs/C22-TERV.md` 1. fejezet).

A szabályokat explicit `Profil`-lal teszteljük (nem az `os.toml` mért küszöbeivel): a teszt a *viselkedést* védi, a küszöb
mért értékét a `test_kapuk_meres` őrzi."""
import unittest

from modulok.kapuk import forras as F
from modulok.kapuk import huseg as H
from modulok.kapuk import tokenek as T

JEGYZET = """# Róma

## Az első triumvirátus

Caesar kibékítette Crassust és Pompeiust, majd szövetséget kötött velük a senatus ellen (Kr. e. 60). A szövetséget később „három férfiú szövetsége” néven emlegették, mert titokban jött létre.

## Polgárháború

A senatus nem bízott Pompeiusban, ezért 49-ben Caesar átkelt a Rubiconon. Ez volt a polgárháború kezdete.
"""
FORRAS = F.ForrasSzoveg.jegyzetbol(JEGYZET)
IDEZET = "majd szövetséget kötött velük a senatus ellen (Kr. e. 60)"

P = H.Profil(idezet_min_szo=3, idezet_max_szo=45, idezet_kuszob=0.85, tamogatas_kuszob=0.6, bizonyitek="mondat",
             kenyes=True, tagadas="bevezetett")


class TokenekTest(unittest.TestCase):
    def test_tovek_ragtol_es_ekezettol_fuggetlen(self):
        self.assertEqual(T.tovek("Crassust és Pompeiusszal"), {"crass", "pompe"})
        self.assertEqual(T.tovek("Crassus"), T.tovek("Crassusszal"))

    def test_fuggvenyszavak_es_kerdoszavak_kiesnek(self):
        self.assertEqual(T.tovek("Melyik hadvezérrel kötött szövetséget, hogy nem volt"), {"hadve", "kotot", "szove"})
        self.assertIn("hogy", T.tovek("hogy", stop=False))

    def test_szamok(self):
        self.assertEqual(T.szamok("Kr. e. 60-ban, 1 000 fő és 3,5"), {"60", "1", "000", "3", "5"})

    def test_nagybetus_szavak_es_a_mondatkezdet(self):
        s = "Caesar átkelt. Rubiconon, mint „Crassus” mondta: Pompeius (Magnus) is"
        szavak = dict(T.nagybetus(s))
        self.assertTrue(szavak["Caesar"])             # mondatkezdő
        self.assertTrue(szavak["Rubiconon"])          # pont után
        self.assertFalse(szavak["Crassus"])           # idézőjel mögött, de nem mondatkezdő
        self.assertTrue(szavak["Pompeius"])           # kettőspont után
        self.assertFalse(szavak["Magnus"])

    def test_tagadas(self):
        self.assertTrue(T.tagado("A senatus nem bízott"))
        self.assertTrue(T.tagado("pénz nélkül"))
        self.assertFalse(T.tagado("A senatus bízott"))

    def test_a_forras_nevtovei(self):
        nevek = FORRAS.nevtovek()
        self.assertIn("pompe", nevek)                 # „Pompeiust”, mondaton belül nagybetűvel
        self.assertIn("crass", nevek)
        self.assertNotIn("a", nevek)


class SzabalyokTest(unittest.TestCase):
    def ell(self, allitas, idezet=IDEZET, profil=P):
        return H.ellenoriz(FORRAS, allitas, idezet, profil)

    def test_elfogadja_a_tamogatott_allitast(self):
        v = self.ell("Caesar szövetséget kötött Crassusszal és Pompeiusszal a senatus ellen.")
        self.assertTrue(v.ok, v.okok)
        self.assertEqual(v.okok, [])
        self.assertEqual(FORRAS.szakaszok[v.szakasz].cim, "Az első triumvirátus")
        self.assertEqual(v.hasonlosag, 1.0)
        self.assertGreaterEqual(v.lefedettseg, 0.9)

    def test_kitalalt_idezet_csak_a_kotottseget_buktatja(self):
        v = self.ell("Caesar legyőzte Pompeiust.", "Caesar legyőzte Pompeiust a pharsalosi csatában")
        self.assertFalse(v.ok)
        self.assertEqual(v.okok, ["kotott"])
        self.assertIsNone(v.hely)

    def test_hossz(self):
        v = self.ell("Caesar szövetséget kötött.", "szövetséget kötött")
        self.assertIn("hossz", v.okok)
        hosszu = " ".join(["senatus"] * 50)
        self.assertIn("hossz", self.ell("x", hosszu).okok)
        self.assertEqual(self.ell("Caesar szövetséget kötött a senatus ellen.", IDEZET,
                                  H.Profil(**{**P.__dict__, "idezet_min_szo": 3, "idezet_max_szo": None})).okok, [])

    def test_szamcsere(self):
        v = self.ell("Caesar szövetséget kötött Crassusszal és Pompeiusszal a senatus ellen Kr. e. 61-ben.")
        self.assertEqual(v.okok, ["kenyes"])
        self.assertIn("61", v.hianyzo)
        ki = H.Profil(**{**P.__dict__, "kenyes": False})
        self.assertTrue(self.ell("Caesar szövetséget kötött Crassusszal és Pompeiusszal a senatus ellen Kr. e. 61-ben.",
                                 profil=ki).ok)                    # a kapcsoló kikapcsolható (a mérés ezt hasonlítja)

    def test_nevcsere_amely_nincs_a_jegyzetben(self):
        v = self.ell("Caesar szövetséget kötött Antoniusszal és Pompeiusszal a senatus ellen.")
        self.assertEqual(v.okok, ["kenyes"])
        self.assertIn("anton", v.hianyzo)

    def test_nevcsere_amely_a_jegyzet_mas_helyen_all_nem_a_mondatban(self):
        # a „Rubicon” a jegyzet másik szakaszában áll: a mondatban nincs, tehát a bizonyíték nem fedi
        v = self.ell("Caesar szövetséget kötött a Rubiconnal a senatus ellen.")
        self.assertIn("kenyes", v.okok)

    def test_tagadas_bevezetese(self):
        v = self.ell("Caesar nem kötött szövetséget Crassusszal és Pompeiusszal a senatus ellen.")
        self.assertEqual(v.okok, ["tagadas"])

    def test_tagadas_modok(self):
        nem = "A senatus nem bízott Pompeiusban."
        quote = "A senatus nem bízott Pompeiusban, ezért 49-ben Caesar átkelt a Rubiconon"
        pozitiv = "A senatus bízott Pompeiusban."
        bevezetett = H.Profil(**{**P.__dict__, "tagadas": "bevezetett", "idezet_min_szo": 3})
        paritas = H.Profil(**{**P.__dict__, "tagadas": "paritas", "idezet_min_szo": 3})
        self.assertTrue(H.ellenoriz(FORRAS, nem, quote, bevezetett).ok)
        self.assertTrue(H.ellenoriz(FORRAS, pozitiv, quote, bevezetett).ok)         # a törölt tagadást ez a mód nem fogja
        self.assertEqual(H.ellenoriz(FORRAS, pozitiv, quote, paritas).okok, ["tagadas"])
        ki = H.Profil(**{**P.__dict__, "tagadas": "ki", "idezet_min_szo": 3})
        self.assertTrue(H.ellenoriz(FORRAS, "A senatus nem bízott Pompeiusban és nem is félt.", quote, ki).ok)

    def test_gyenge_tamogatas(self):
        v = self.ell("A Rubicon átkelése a polgárháború kezdete volt.")
        self.assertIn("tamogatas", v.okok)
        self.assertLess(v.lefedettseg, 0.6)

    def test_ures_allitas_nem_tamogatott(self):
        self.assertIn("tamogatas", self.ell("?").okok)
        self.assertIn("tamogatas", self.ell("").okok)

    def test_a_bizonyitek_kiterjesztese(self):
        allitas = "Az első triumvirátus Kr. e. 60-ban jött létre a senatus ellen."
        idezet_csak = H.Profil(**{**P.__dict__, "bizonyitek": "idezet"})
        mondat = H.Profil(**{**P.__dict__, "bizonyitek": "mondat"})
        cimmel = H.Profil(**{**P.__dict__, "bizonyitek": "mondat+cim"})
        self.assertIn("tamogatas", self.ell(allitas, profil=idezet_csak).okok)
        self.assertIn("tamogatas", self.ell(allitas, profil=mondat).okok)          # a „triumvirát” csak a fejezet címében áll
        self.assertTrue(self.ell(allitas, profil=cimmel).ok)

    def test_a_verdikt_szotarrá_alakitva(self):
        d = self.ell("Caesar nem kötött szövetséget.").to_dict()
        self.assertEqual(set(d) >= {"ok", "okok", "hely", "szakasz", "hasonlosag", "lefedettseg", "hianyzo"}, True)
        self.assertEqual(d["ok"], False)


class KontextusEsKepletTest(unittest.TestCase):
    """Kvíz/kártya: az állítás a válasz, a kérdés a kontextus (csak a számai és nevei számítanak)."""

    def test_a_kerdes_szavai_nem_szamitanak_a_lefedettsegbe(self):
        v = H.ellenoriz(FORRAS, "szövetséget kötött velük", IDEZET, P,
                        kontextus="Melyik hadvezérrel kötött szövetséget Caesar a senatus ellen? Miért?")
        self.assertTrue(v.ok, v.okok)
        self.assertEqual(v.lefedettseg, 1.0)

    def test_a_kerdes_neve_es_szama_a_bizonyitekban_all(self):
        rossz_nev = H.ellenoriz(FORRAS, "szövetséget kötött velük", IDEZET, P, kontextus="Kivel kötött szövetséget Antonius?")
        self.assertEqual(rossz_nev.okok, ["kenyes"])
        rossz_szam = H.ellenoriz(FORRAS, "szövetséget kötött velük", IDEZET, P, kontextus="Mikor, Kr. e. 61-ben?")
        self.assertEqual(rossz_szam.okok, ["kenyes"])
        jo_szam = H.ellenoriz(FORRAS, "szövetséget kötött velük", IDEZET, P, kontextus="Mikor, Kr. e. 60-ban?")
        self.assertTrue(jo_szam.ok)

    def test_a_kerdes_kepletei_kiesnek(self):
        """A „(a+b)^2” kitevője nem a mondatból való: a képleten kívüli számok és nevek számítanak."""
        v = H.ellenoriz(FORRAS, "szövetséget kötött velük", IDEZET, P, kontextus="Mi a $(x+y)^7$ kifejtése Caesar szerint?")
        self.assertTrue(v.ok, v.okok)

    def test_kepletes_allitas_a_jelekkel(self):
        forras = F.ForrasSzoveg.jegyzetbol("# C\n\n## S\n\nAz $a^2 - b^2$ kifejezés szorzattá alakítva $(a+b)(a-b)$, ezt két négyzet különbségének hívjuk.\n")
        idezet = "Az $a^2 - b^2$ kifejezés szorzattá alakítva $(a+b)(a-b)$"
        self.assertTrue(H.ellenoriz(forras, "$(a+b)(a-b)$", idezet, P).ok)                # nincs 3 betűs szó: a jelek fedik
        v = H.ellenoriz(forras, "$p + q$", idezet, P)
        self.assertIn("tamogatas", v.okok)
        self.assertLess(v.lefedettseg, 0.5)

    def test_szam_es_ures_allitas(self):
        self.assertTrue(H.ellenoriz(FORRAS, "60", IDEZET, P).ok)
        self.assertIn("kenyes", H.ellenoriz(FORRAS, "61", IDEZET, P).okok)


class ProfilTest(unittest.TestCase):
    class Cfg:
        def __init__(self, adat):
            self.adat = adat

        def section(self, *kulcsok):
            n = self.adat
            for k in kulcsok:
                n = n.get(k, {})
            return n

    def test_alap_es_fogyaszto_felulirasa(self):
        cfg = self.Cfg({"kapuk": {"idezet_kuszob": 0.8, "tamogatas_kuszob": 0.55, "bizonyitek": "mondat+cim",
                                  "kviz": {"idezet_min_szo": 5, "tamogatas_kuszob": 0.5}}})
        p = H.profil(cfg)
        self.assertEqual((p.idezet_kuszob, p.tamogatas_kuszob, p.bizonyitek), (0.8, 0.55, "mondat+cim"))
        k = H.profil(cfg, "kviz")
        self.assertEqual((k.nev, k.idezet_min_szo, k.tamogatas_kuszob, k.idezet_kuszob), ("kviz", 5, 0.5, 0.8))

    def test_ismeretlen_kulcs_es_ertek_hiba(self):
        with self.assertRaises(ValueError):
            H.profil(self.Cfg({"kapuk": {"nincs_ilyen": 1}}))
        with self.assertRaises(ValueError):
            H.profil(self.Cfg({"kapuk": {"tagadas": "talan"}}))
        with self.assertRaises(ValueError):
            H.profil(self.Cfg({"kapuk": {"idezet_kuszob": 1.5}}))

    def test_az_os_toml_profilja_ervenyes(self):
        from core import config
        cfg = config.load()
        for nev in (None, "osszefoglalo", "kartya", "kviz", "valasz"):
            H.profil(cfg, nev)


if __name__ == "__main__":
    unittest.main()
