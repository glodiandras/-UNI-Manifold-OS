"""A linkeletlen említés felismerése core API-ként (C30a; CHATKALAUZ C30 1. pont — a szerkesztő aláhúzása és a Tab/Esc a
C30b-é): a *kapott* (akár mentetlen) szövegben a többi jegyzet nevét és aliasát keresi szóhatáron, kis-nagybetűtől függetlenül,
ékezetre érzékenyen; kód, képlet, link és frontmatter nélkül; hasonlóság és modell nélkül. Álvaulton."""
import os
import unittest

from core.asszisztens.emlites import Emlitesek
from tests.helpers import ir, tmpdir
from tests.index_segedek import alvault, index_indit

KERET = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"


def jo(szoveg: str = "") -> str:
    return KERET + szoveg


ALAP = {
    "Függvények.md": jo("# Függvények\n"),
    "Sorozatok.md": jo("# Sorozatok\n"),
    "Mérték.md": jo("m\n"),
    "Fém.md": jo("rövid név\n"),
    "2026.md": jo("csak szám\n"),
    "Függvény ábrázolása.md": jo("hosszú\n"),
    "Függvény.md": jo("rövidebb\n"),
    "Célállomás.md": "---\naliases: [Célpont, Cél alias]\n---\nszöveg\n",
    "A/Közös.md": jo("a\n"),
    "B/Közös.md": jo("b\n"),
    "ATTCHMNTS - cards/Függvények — kártyák.md": jo("k\n"),
    "Jegyzet.md": jo("üres\n"),
}


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def indit(self, fajlok=None, beall=None, **kw):
        self._n = getattr(self, "_n", 0) + 1            # egy teszt több álvaultot is indíthat: mindegyik saját mappában
        mappa = os.path.join(self._t.name, f"v{self._n}")
        os.makedirs(mappa)
        cfg, self.v = alvault(mappa, ALAP if fajlok is None else fajlok)
        if beall:
            cfg.data.setdefault("asszisztens", {}).update(beall)
        self.cfg = cfg
        self.ix, _ = index_indit(cfg)
        self.addCleanup(self.ix.leallit)
        self.e = Emlitesek(cfg, self.ix, **kw)
        return self.e

    def keres(self, szoveg, ut="Jegyzet.md", **kw):
        return self.e.keres(ut, szoveg, **kw)["emlitesek"]

    @staticmethod
    def szovegek(lista) -> list[str]:
        return [x["szoveg"] for x in lista]


class HosszTartoKisbetuTest(Alap):
    """A3-26: a kisbetűsítés hossztartó (`'İ'.lower()` két kódpont): a pozíciók nem tolódnak el, a sor/oszlop jó."""

    def test_nagy_i_ponttal_nem_tolja_el_a_poziciokat(self):
        self.indit()
        szoveg = "İİ rendben\nİ és függvények, majd İİİ sorozatok.\n"
        lista = self.keres(szoveg)
        self.assertEqual(self.szovegek(lista), ["függvények", "sorozatok"])
        for x in lista:
            self.assertEqual(szoveg[x["kezd"]:x["veg"]], x["szoveg"])
        f, s_ = lista
        self.assertEqual((f["sor"], f["oszlop"]), (2, 5))
        self.assertEqual((s_["sor"], s_["oszlop"]), (2, szoveg.split("\n")[1].index("sorozatok")))

    def test_a_nagy_i_ponttal_a_nevben_is_illeszkedik(self):
        self.indit({**ALAP, "İstanbul.md": jo("város\n")})
        szoveg = "az istanbul és az İSTANBUL\n"
        self.assertEqual(self.szovegek(self.keres(szoveg)), ["istanbul", "İSTANBUL"])

    def test_sok_sor_sok_talalat_sorszama(self):
        self.indit()
        szoveg = "".join(f"İ {i} sor függvények\n" for i in range(300))
        lista = self.keres(szoveg, limit=500)
        self.assertEqual([x["sor"] for x in lista], list(range(1, 301)))
        self.assertTrue(all(szoveg[x["kezd"]:x["veg"]] == "függvények" for x in lista))


class AlapTest(Alap):
    def setUp(self):
        super().setUp()
        self.indit()

    def test_szohatar_kisbetu_es_pozicio(self):
        szoveg = "Ma a függvények és a Sorozatok. Mérték nem mértékegység.\nMásik sor: sorozatok!"
        t = self.keres(szoveg)
        self.assertEqual(self.szovegek(t), ["függvények", "Sorozatok", "Mérték", "sorozatok"])
        for x in t:
            self.assertEqual(szoveg[x["kezd"]:x["veg"]], x["szoveg"])
        self.assertEqual((t[0]["sor"], t[0]["oszlop"]), (1, 5))
        self.assertEqual((t[3]["sor"], t[3]["oszlop"]), (2, 11))
        self.assertEqual([x["cel"] for x in t], ["Függvények.md", "Sorozatok.md", "Mérték.md", "Sorozatok.md"])
        self.assertTrue(all(x["forras"] == "nev" and not x["tobbertelmu"] for x in t))

    def test_ekezetre_erzekeny(self):
        self.assertEqual(self.szovegek(self.keres("fuggvenyek es sorozatok")), ["sorozatok"])

    def test_szon_beluli_resz_nem_talalat(self):
        self.assertEqual(self.keres("mértékegység, függvényekből, asorozatok"), [])

    def test_leghosszabb_talalat_nyer(self):
        t = self.keres("a függvény ábrázolása és egy függvény")
        self.assertEqual(self.szovegek(t), ["függvény ábrázolása", "függvény"])
        self.assertEqual([x["cel"] for x in t], ["Függvény ábrázolása.md", "Függvény.md"])

    def test_alias(self):
        t = self.keres("a célpont és a cél alias, meg a célállomás")
        self.assertEqual(self.szovegek(t), ["célpont", "cél alias", "célállomás"])
        self.assertEqual([x["forras"] for x in t], ["alias", "alias", "nev"])
        self.assertTrue(all(x["cel"] == "Célállomás.md" for x in t))

    def test_tobbertelmu_nev(self):
        t = self.keres("a közös jegyzet")
        self.assertEqual(len(t), 1)
        self.assertTrue(t[0]["tobbertelmu"])
        self.assertIsNone(t[0]["cel"])
        self.assertEqual(sorted(t[0]["jeloltek"]), ["A/Közös.md", "B/Közös.md"])

    def test_rovid_es_szam_nev_kimarad_a_beallitas_szerint(self):
        self.assertEqual(self.keres("fém és 2026"), [])
        self.indit(beall={"emlites_min_hossz": 3})
        self.assertEqual(self.szovegek(self.keres("fém és 2026")), ["fém"])

    def test_kizart_mappa_nem_cel_es_a_sajat_jegyzet_sem(self):
        t = self.keres("Függvények — kártyák")
        self.assertEqual([x["cel"] for x in t], ["Függvények.md"])            # a gépi kísérőjegyzet (ATTCHMNTS - ) nem cél
        self.assertEqual(self.szovegek(self.keres("jegyzet és függvények", ut="Függvények.md")), ["jegyzet"])   # a saját név kimarad

    def test_a_mar_belinkelt_cel_kimarad(self):
        self.indit({**ALAP, "Jegyzet.md": jo("[[Sorozatok]] már linkelve\n")})
        self.assertEqual(self.szovegek(self.keres("sorozatok és függvények", ut="Jegyzet.md")), ["függvények"])

    def test_limit(self):
        self.assertEqual(len(self.keres("sorozatok " * 20)), 20)
        self.assertEqual(len(self.keres("sorozatok " * 20, limit=3)), 3)

    def test_ismeretlen_ut_is_mukodik_mentetlen_uj_jegyzet(self):
        self.assertEqual(self.szovegek(self.keres("függvények", ut="Új, még nem mentett.md")), ["függvények"])

    def test_nem_szoveg_400(self):
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError) as e:
            self.e.keres("Jegyzet.md", None)
        self.assertEqual(e.exception.code, 400)


class MaszkTest(Alap):
    def setUp(self):
        super().setUp()
        self.indit()

    def test_kod_kepelt_link_frontmatter_nem_talalat(self):
        szoveg = ("---\nTags: függvények\n---\n"
                  "`függvények` és $sorozatok$ és $$\nfüggvények\n$$ és "
                  "[[Függvények]] és [[Sorozatok|sorozatok]] és ![[Mérték]] és [a függvények](x.md) és "
                  "https://példa.hu/függvények\n"
                  "```\nsorozatok\n```\n")
        self.assertEqual(self.keres(szoveg), [])

    def test_kep_kod_utan_a_szoveg_talalat_es_a_pozicio_nem_csuszik(self):
        szoveg = "`kód` és $x$ és függvények\n```\nx\n```\nsorozatok"
        t = self.keres(szoveg)
        self.assertEqual(self.szovegek(t), ["függvények", "sorozatok"])
        for x in t:
            self.assertEqual(szoveg[x["kezd"]:x["veg"]], x["szoveg"])
        self.assertEqual(t[1]["sor"], 5)

    def test_nem_bmp_karakter_utan_a_kodpont_oszlop(self):
        szoveg = "😀 függvények"
        t = self.keres(szoveg)
        self.assertEqual((t[0]["kezd"], t[0]["oszlop"]), (2, 2))


class CimreszTest(unittest.TestCase):
    """K177: a fájlnév címrésze (az `NN - ` előtag és a ` — Feladattár`-féle utótag nélkül) és a névelő nélküli szószám."""

    def test_cimresz(self):
        from core.asszisztens.emlites import cimresz
        self.assertEqual(cimresz("05 - Ciklusok"), ("Ciklusok", False))
        self.assertEqual(cimresz("06F - Nyelvtípusok — Feladattár"), ("Nyelvtípusok", True))
        self.assertEqual(cimresz("13 - Függvények — elemzés, leolvasás és transzformációk"),
                         ("Függvények", True))
        self.assertEqual(cimresz("Függvények"), ("Függvények", False))                    # nincs előtag és utótag: maga a név
        self.assertEqual(cimresz("Áram- és feszültségmérés. Az áram vegyi hatása — Feladattár")[0],
                         "Áram- és feszültségmérés. Az áram vegyi hatása")
        self.assertEqual(cimresz("2026")[0], "2026")                                       # a puszta szám nem előtag
        self.assertEqual(cimresz("Algebra - Alapok"), ("Algebra - Alapok", False))         # kötőjel szám nélkül nem előtag

    def test_nevelo_nelkul(self):
        from core.asszisztens.emlites import nevelo_nelkul
        self.assertEqual(nevelo_nelkul("A vita"), "vita")
        self.assertEqual(nevelo_nelkul("Az atomerőművek"), "atomerőművek")
        self.assertEqual(nevelo_nelkul("A New Deal"), "New Deal")
        self.assertEqual(nevelo_nelkul("Egy a kettő"), "kettő")
        self.assertEqual(nevelo_nelkul("A"), "A")                                          # nem marad szó nélkül
        self.assertEqual(nevelo_nelkul("Azonos"), "Azonos")                                # szóelemet nem vág

    def test_tartalmas_szavak_a_kezdo_nevelo_nelkul(self):
        from core.asszisztens.emlites import tartalmas_szavak
        self.assertEqual(tartalmas_szavak("a vita"), ["vita"])
        self.assertEqual(tartalmas_szavak("az atomerőművek"), ["atomerőművek"])
        self.assertEqual(tartalmas_szavak("a thalész-tétel"), ["thalész-tétel"])
        self.assertEqual(tartalmas_szavak("nyelvi identitás"), ["nyelvi", "identitás"])
        self.assertEqual(tartalmas_szavak("a"), ["a"])


TARTALOM = jo("Lényeg.\n")
CIM_FAJLOK = {
    "M01 - Halmazok/05 - Ciklusok.md": TARTALOM,
    "M01 - Halmazok/05F - Ciklusok — Feladattár.md": jo("# Ciklusok — Feladattár\nfeladatok\n"),
    "M01 - Halmazok/Forras.md": jo("Itt a ciklusok használata.\n"),
    "D01 - Mas/Mas.md": jo("A ciklusok mások.\n"),
    "N01 - Nyelv/03 - Nyelvi identitás.md": TARTALOM,
    "N01 - Nyelv/04 - A vita.md": TARTALOM,
    "N01 - Nyelv/Y.md": jo("y\n"),
    "T01 - Tört/02 - Nyelvi identitás.md": TARTALOM,
    "T01 - Tört/X.md": jo("x\n"),
    "I01 - Irod/Z.md": jo("z\n"),
    "N02 - Csak feladattár/01F - Zárt kör — Feladattár.md": TARTALOM,
}


class CimAlakTest(Alap):
    """K177: a szótár a címrészt is tartalmazza (`NN - ` előtag és ` — Feladattár` nélkül), a zajt a szűrés védi."""

    def setUp(self):
        super().setUp()
        self.indit(CIM_FAJLOK)

    def cel(self, szoveg, ut):
        return [(x["szoveg"], x["cel"], x["tobbertelmu"]) for x in self.keres(szoveg, ut=ut)]

    def test_a_prozai_emlites_a_cimre_egyezik_a_teljes_fajlnev_helyett(self):
        self.assertEqual(self.cel("a nyelvi identitás kérdése", "N01 - Nyelv/Y.md"),
                         [("nyelvi identitás", "N01 - Nyelv/03 - Nyelvi identitás.md", False)])

    def test_az_alak_kikapcsolhato_a_regi_viselkedes_marad(self):
        self.indit(CIM_FAJLOK, beall={"emlites_cim_alak": False})
        self.assertEqual(self.keres("a nyelvi identitás kérdése, a ciklusok", ut="N01 - Nyelv/Y.md"), [])
        self.assertEqual(self.szovegek(self.keres("03 - Nyelvi identitás", ut="N01 - Nyelv/Y.md")), ["03 - Nyelvi identitás"])

    def test_tobbszavas_cim_mas_tantargybol_is_javaslat(self):
        self.assertEqual(self.cel("a nyelvi identitás", "I01 - Irod/Z.md")[0][0], "nyelvi identitás")

    def test_egyszavas_cim_csak_ugyanabban_a_tantargyban(self):
        self.assertEqual(self.cel("a ciklusok", "M01 - Halmazok/Forras.md"),
                         [("ciklusok", "M01 - Halmazok/05 - Ciklusok.md", False)])
        self.assertEqual(self.cel("a ciklusok", "D01 - Mas/Mas.md"), [])               # más tantárgy: nincs
        self.assertEqual(self.cel("a ciklusok", "Gyoker.md"), [])                      # a gyökérben nincs tantárgy

    def test_az_egyszavas_cim_csak_ha_ritka_a_vaultban(self):
        self.indit(CIM_FAJLOK, beall={"emlites_cim_egyszavas_max_db": 1})              # a „ciklusok” 3 jegyzetben szerepel
        self.assertEqual(self.cel("a ciklusok", "M01 - Halmazok/Forras.md"), [])
        self.indit(CIM_FAJLOK, beall={"emlites_cim_egyszavas_max_db": 3})
        self.assertEqual(len(self.cel("a ciklusok", "M01 - Halmazok/Forras.md")), 1)

    def test_a_kezdo_nevelo_nem_szam_szonak_es_nem_resze_a_linknek(self):
        """„A vita” egyszavas: más tantárgyból nem javasolt, az azonosból igen (ritka szó); a névelő a link előtt marad."""
        self.assertEqual(self.cel("a vita", "T01 - Tört/X.md"), [])
        t = self.keres("itt a vita lényege", ut="N01 - Nyelv/Y.md")
        self.assertEqual([(x["szoveg"], x["cel"], x["kezd"]) for x in t], [("vita", "N01 - Nyelv/04 - A vita.md", 6)])

    def test_az_utotagos_jegyzet_csak_tartalek_az_elsodleges_elonyt_elvez(self):
        t = self.keres("a ciklusok", ut="M01 - Halmazok/Forras.md")
        self.assertEqual((t[0]["cel"], t[0]["forras"]), ("M01 - Halmazok/05 - Ciklusok.md", "cim"))
        self.assertEqual(self.cel("a zárt kör", "I01 - Irod/Z.md"),                    # nincs elsődleges: a Feladattár marad
                         [("zárt kör", "N02 - Csak feladattár/01F - Zárt kör — Feladattár.md", False)])

    def test_azonos_cim_tobb_tantargyban_az_azonos_tantargy_elony_kulonben_tobbertelmu(self):
        self.assertEqual(self.cel("a nyelvi identitás", "T01 - Tört/X.md"),
                         [("nyelvi identitás", "T01 - Tört/02 - Nyelvi identitás.md", False)])
        t = self.keres("a nyelvi identitás", ut="I01 - Irod/Z.md")
        self.assertEqual((t[0]["tobbertelmu"], t[0]["cel"]), (True, None))             # a felület nem húzza alá
        self.assertEqual(sorted(t[0]["jeloltek"]), ["N01 - Nyelv/03 - Nyelvi identitás.md", "T01 - Tört/02 - Nyelvi identitás.md"])

    def test_cimsorba_nem_javasol_csak_a_torzsbe(self):
        t = self.keres("# Nyelvi identitás\n\nA nyelvi identitás itt a törzsben.\n", ut="T01 - Tört/X.md")
        self.assertEqual([(x["sor"], x["szoveg"]) for x in t], [(3, "nyelvi identitás")])

    def test_a_teljes_nev_szurese_valtozatlan_a_cimsor_es_az_idegen_tantargy_sem_tiltja(self):
        self.indit()                                                                    # az `ALAP` fájlok: előtag és utótag nélküli nevek
        t = self.keres("# Függvények\n\nfüggvények", ut="I01 - Irod/Z.md")
        self.assertEqual([(x["sor"], x["szoveg"]) for x in t], [(1, "Függvények"), (3, "függvények")])

    def test_az_FTS_hiba_zarva_hibazik_az_egyszavas_cim_elmarad(self):
        eredeti = self.ix.olvaso

        def hibas():
            raise OSError("nem olvasható")
        self.e.szotar()                                                                 # a szótár már áll
        self.ix.olvaso = hibas
        try:
            sz = self.e.szotar()
            self.assertEqual(self.e._df(sz, "nincs-ilyen-szo"), 10 ** 9)
        finally:
            self.ix.olvaso = eredeti


class SzotarTest(Alap):
    def test_a_szotar_generacio_szerint_frissul_de_nem_minden_hivasra(self):
        e = self.indit(beall={"emlites_szotar_frissites_mp": 0})
        self.assertEqual(self.keres("új fogalom"), [])
        ir(self.v, "Új fogalom.md", jo("x\n"))
        self.assertTrue(self.ix.frissit(["Új fogalom.md"]))
        self.assertEqual(self.szovegek(self.keres("új fogalom")), ["új fogalom"])

    def test_gyors_egymas_utani_hivasnal_a_szotar_nem_epul_ujra(self):
        e = self.indit(beall={"emlites_szotar_frissites_mp": 3600})
        hivasok = []
        eredeti = self.ix.olvaso

        def szamol():
            hivasok.append(1)
            return eredeti()
        self.ix.olvaso = szamol
        self.keres("függvények")
        elso = len(hivasok)
        self.keres("sorozatok")
        self.keres("mérték")
        self.assertLessEqual(len(hivasok) - elso, 2)                  # csak a belinkelt-célok lekérdezése hívásonként 1
        self.assertGreaterEqual(elso, 2)


if __name__ == "__main__":
    unittest.main()
