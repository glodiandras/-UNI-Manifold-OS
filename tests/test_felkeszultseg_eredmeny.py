"""Az eredmény-kinyerő tesztjei (C28b; `core/felkeszultseg/eredmeny.py`): a vault valódi „Dolgozat kiértékelő” / „Dolgozat Napló”
jegyzeteinek 13 szeptemberi és 6 októberi szakasza **kézzel címkézve** (a szakaszok számot hordozó és a kinyerőt próbára tevő mondatai,
szó szerint; a napló személyes részei nélkül) — a legacy `eredmeny()` három hibájának regressziója is itt él."""
import unittest

from core.felkeszultseg import eredmeny as E

# (szakasz-azonosító, szöveg, várt eredmény) — a várt: (pont, max) | ("szazalek", érték) | None | "ellentmondas"
SZAKASZOK = [
    ("sz-08-tortenelem", "[[2026-09-08 - Történelem]]\n\nMegtanultam rendesen az esszé anyagát, a dolgozatot is jónak éreztem.\n"
     "Megkaptam az eredményt: 16/23 lett, ami négyes. Összességében nincs bajom ezzel az eredménnyel viszont észrevételeim a következő dolgok:\n"
     "- **Forráselemzés:** Túl röviden használtad a forrásokat.\n", (16, 23)),
    ("sz-14-matek", "[[2026-09-14 - Matematika]]\n\nJónak éreztem a dolgozatot. Kis figyelmetlenségi hiba és másodfokú egyenlet nem végigszámolása "
     "miatt vesztettem 10 pontot. Szerintem a tanárnő nagyon szigorúan osztályoz, ezt figyelembe kell venni készüléskor. "
     "14/24-es lett az eredményem.\n", (14, 24)),
    # 1. hiba nem ez, hanem a jövő idejű mondat: a „lesz” a számot nem érinti (külön mondat)
    ("sz-15-nemet", "[[2026-09-15 - Német]]\n\nÖsszességében jónak éreztem, mentek a kötelező szavak, én realisztikusan azt mondanám rá, hogy a "
     "hármas szintjén lesz. Teljesen elfogadhatónak tartom ezt az eredményt.\n\n6.5 pont lett végül a 10-ből.\n", (6.5, 10)),
    # 3. hiba: 68% lett (18/31) — 18/31 = 58,1%: a két érték ellentmond
    ("sz-17-fizika", "[[2026-09-17 - Fizika]]\n\nIgaz a keleténél kevesebbet tanultam rá, de még így is egész jó lett: 68% lett (18/31), ami hármas, "
     "és teljesen elégedett vagyok az eredményemmel mert tudom hogy nem tanultam rá annyit amennyit kellett volna\n", "ellentmondas"),
    ("sz-17-tortenelem", "[[2026-09-17 - Történelem]]\n\nBejelentett egy dolgozatot, amit nem mindenki írt meg, ezt el is mondta. Én nem írtam meg, "
     "ennek ellenére készültem rá és készen álltam volna arra, hogy megírjam.\n", None),
    ("sz-18-matek", "[[2026-09-18 - Matematika]]\n\nErre már jelentősen többet készültem, mint az előzőre (09.14) nagyon jó is lett. 16 megoldandó "
     "egyenlet volt, amelyből kettőt elfelejtettem megoldani, mert túlságosan ráfókuszáltam az ellenőrzésre, emellett reggel nyolc volt. "
     "Az eredményem: 13.5/16 lett ami szerintem kiemelkedő.\n", (13.5, 16)),
    # 1. hiba: a „szerintem” nem zárja ki a múlt idejű eredményt; a „kb 30 percet” nem a szám közelítése
    ("sz-22-nemet", "[[2026-09-22 - Német]]\n\nErre kb 30 percet szántam és 7.5 pontot értem el végül a 10-ből ami szerintem fair. Jelenleg a német "
     "nem annyira a prioritásom, hogy ennél jobban ráfókuszáljak és többet foglalkozzak vele\n", (7.5, 10)),
    ("sz-22-irodalom", "[[2026-09-22 - Irodalom]]\n\nEz egy kis röpdolgozat volt, amire egész sokat készültem, viszont olyan nehéz feladatot adott "
     "elsőnek, hogy még a mellettem ülő aki puskázott, ő is csak tippelni tudott. A többi feladat megoldásomat solidnak éreztem, még nincs eredmény\n"
     "13/20-as eredmény lett, ami hármas. Nem vagyok elégedetlen a teljesítményemmel a 14 pont az már 4-es lett volna. Mostantól óráról órára "
     "kell tanulni az irodalmat.\n", (13, 20)),
    ("sz-28-nyelvtan", "[[2026-09-28 - Nyelvtan]]\n\nNem lett rossz a dolgozat, elégedett vagyok vele. Magyarnál úgy tekintek a dolgozatokra, "
     "jegyekre, hogy 3-as felett már nem egy rossz eredmény, de mindenképp javítandó a 3-as a 4-es kevésbé. Jelenleg úgy látom, hogy lesz egy "
     "négyes a dolgozat, rossz esetben 3-as.\n", None),
    # 2. hiba: a pluszpont (26/26, 2/2) nem a dolgozat eredménye; az eredmény a 13/16
    ("sz-28-matek", "[[2026-09-28 - Matematika]]\n\nNem lett rossz a dolgozat, egy hibám lett ahogy érzem, és az azért lett mert túlbonyolítottam.\n\n"
     "Emellett több plusz pontra menő munkát visszakaptunk, amelyeken 26/26 pontot szereztem. (itt van egy maximális pont, amelyet egy hibátlan "
     "feladatra ad a tanárnő, de ha kettő pontot adna a dolgozaton az ötből akkor egy plusz pontoson 2/2 pontot kapunk - ezeket dolgozatba "
     "számítja be.)\n\nVisszakaptuk a dolgozat eredményét: 13/16 pontos lett\n", (13, 16)),
    # a havi jegy (18/30) összesített, nem ez a dolgozat; az eredmény a 4,5/10
    ("sz-29-nemet", "[[2026-09-29 - Német]]\n\nNem tanultam nagyon rá a végén, mert nem prioritásom a német és rámfért egy kis pihenés. 4,5/10 "
     "eredménnyel zártam. Összeségében az ehavi dolgozatokból lesz, jön 1 db jegy, ami kettes (18/30). Szerintem nagyon szigorúan osztályoznak, "
     "és ez elkeserít.\n", (4.5, 10)),
    # jövő idejű önbecslés: „30–40 pont között leszek az 50-ből”
    ("sz-30-nemet-temazaro", "Nem lett rossz, a szerintem 30-40 pont között leszek az 50-ből. Nem mondanám magam elégedettnek, kifejtettem miért, fentebb\n", None),
    ("sz-30-matek", "Itt nem egy dolgozatról számolok, be. 4 dolgozat eredményét összesítették, és a plusz pontokat belerakták. Ez mind nekem egy "
     "5-ös eredményt hozott amire nagyon büszke vagyok.\n", None),
    # ---- októberi szakaszok
    # 2. hiba: önbecslés, feltételes mondat, százalék-tartomány
    ("sz-okt-01-tortenelem", "[[2026-10-01 - Történelem]]\n\nNem írattak velem, viszont az anyag 80-85%-át el tudtam volna mondani, le tudtam volna írni.\n", None),
    ("sz-okt-02-matek", "[[2026-10-02 - Matematika]]\n\nAz exponenciális egyenletrendszerekből írtunk\n10/10 pontos lett, sőt plusz feladatot is csináltam, "
     "amelyre 4/4 pontot kaptam pluszban\n", (10, 10)),
    ("sz-okt-05-irodalom", "[[2026-10-05 - Irodalom]]\n\nAlapvetően szerintem jó lett, jobb mint az előző irodalom dolgozat, hisz ebben csak a himnuszt "
     "kellett megtanulni. Én azt mondanám rá most, hogy 5-ös, de ki tudja még mi lesz\n", None),
    ("sz-okt-05-matek", "[[2026-10-05 - Matematika]]\n\nEz egy meglepetés matekdolgozat volt a logaritmus függvényekből és az egyenletekből. Azt "
     "ellenőrizte a tanár nő, hogy mindenki írt e házit, ettől függetlenül a pontok számítanak majd\n", None),
    ("sz-okt-06-fizika", "Alapvetően nem tanultam rá sokat, de úgy éreztem, hogy ment. Amúgy nehéznek éreztem, nem is tudtam mindent befejezni, "
     "volt 8 feladat 45 percre, ami szerintem szürreális, még úgy is hogy emelt fizikán vagyok.\n", None),
    ("sz-okt-06-digkult", "Amúgy egész jól ment, mint utólag kiderült 14 feladat volt, én csak 12 feladatot csináltam meg. Összességében nem tartom "
     "rossznak ezt az eredményt, hisz 45 perc volt 14 feladatra.\n", None),
]


def _elvart(kinyeres: E.Kinyeres, varhato):
    return kinyeres.eredmeny, kinyeres.ellentmondas


class CimkezettSzakaszok(unittest.TestCase):
    def test_a_19_szakasz_a_kezi_cimke_szerint(self):
        for azon, szoveg, var in SZAKASZOK:
            with self.subTest(azon):
                k = E.kinyer(szoveg)
                if var is None:
                    self.assertIsNone(k.eredmeny, f"{azon}: nincs eredmény, de: {k.eredmeny}")
                    self.assertIsNone(k.ellentmondas)
                elif var == "ellentmondas":
                    self.assertIsNone(k.eredmeny)
                    self.assertIsNotNone(k.ellentmondas)
                    szazalekok = sorted(j["szazalek"] for j in k.ellentmondas["jeloltek"])
                    self.assertEqual(szazalekok, [58.1, 68.0])
                else:
                    self.assertIsNotNone(k.eredmeny, f"{azon}: van eredmény, de nem találta")
                    self.assertEqual((k.eredmeny["pont"], k.eredmeny["max"]), (float(var[0]), float(var[1])))
                    self.assertAlmostEqual(k.eredmeny["szazalek"], round(100 * var[0] / var[1], 1))
                    self.assertIsNone(k.ellentmondas)

    def test_a_cimkek_osszesitese(self):
        """A 19 szakaszból 9 egyértelmű eredmény (8 szeptemberi, 1 októberi), 1 ellentmondó (Fizika), 9 eredmény nélküli."""
        egyertelmu = sum(1 for _, sz, _ in SZAKASZOK if E.kinyer(sz).eredmeny)
        ellentmondo = sum(1 for _, sz, _ in SZAKASZOK if E.kinyer(sz).ellentmondas)
        self.assertEqual((egyertelmu, ellentmondo, len(SZAKASZOK) - egyertelmu - ellentmondo), (9, 1, 9))

    def test_a_legacy_alak_kompatibilis(self):
        e = E.eredmeny("Megkaptam az eredményt: 16/23 lett, ami négyes.")
        self.assertEqual(set(e) >= {"pont", "max", "szazalek", "forras"}, True)
        self.assertEqual((e["pont"], e["max"], e["szazalek"], e["forras"]), (16.0, 23.0, 69.6, "16/23"))
        self.assertIsNone(E.eredmeny("A dolgozat jól sikerült."))


class HibakJavitasa(unittest.TestCase):
    """A legacy `eredmeny()` három hibája külön-külön."""

    def test_szerintem_nem_zar_ki_multidejű_eredmenyt(self):
        e = E.eredmeny("7.5 pontot értem el végül a 10-ből ami szerintem fair.")
        self.assertEqual((e["pont"], e["max"]), (7.5, 10.0))
        self.assertIsNone(E.eredmeny("Szerintem 13/16 körül lesz."))
        self.assertIsNone(E.eredmeny("Szerintem 13/16 pont."), "eredményjelző nélküli vélemény")

    def test_pluszpont_nem_eredmeny(self):
        self.assertIsNone(E.eredmeny("A plusz munkákon 26/26 pontot szereztem."))
        e = E.eredmeny("10/10 pontos lett, sőt plusz feladatot is csináltam, amelyre 4/4 pontot kaptam pluszban")
        self.assertEqual((e["pont"], e["max"]), (10.0, 10.0))

    def test_onbecsles_es_feltetel_nem_eredmeny(self):
        self.assertIsNone(E.eredmeny("Az anyag 80-85%-át el tudtam volna mondani."))
        self.assertIsNone(E.eredmeny("A 14 pont az már 4-es lett volna, ha 14/20 volt volna."))
        self.assertIsNone(E.eredmeny("Várhatóan 70%-os lesz."))
        self.assertIsNone(E.eredmeny("Kb 12/20 körül lehet."))

    def test_jovore_vagy_szandekra_utalo_mondat_nem_eredmeny(self):
        """K390 (F8, 2026-10-14): a jelen idejű, de jövőre/szándékra utaló alak nem eredmény (77(a)); a múlt idejű igen."""
        k = E.kinyer("# Október 13: Német\n\n8 pontot elérek a 10-ből.\n")       # a Kézi kör 2b mondata
        self.assertIsNone(k.eredmeny)
        self.assertIn("szándékra", [t for t in k.talalatok if not t.elfogadva][0].ok)
        for mondat in ("Remélem, elérem a 8/10 pontot.", "Szeretnék 80%-ot elérni.", "Talán 15/20 pont lett.",
                       "16/20 pontot kellene elérnem.", "Holnap megkapom a 18/20 pontot.", "8 pontot kapok a 10-ből.",
                       "A célom 45 pont az 50-ből."):
            with self.subTest(mondat=mondat):
                self.assertIsNone(E.eredmeny(mondat))
        for mondat, varhato in (("8 pontot értem el a 10-ből.", (8.0, 10.0)), ("8 pontot elértem a 10-ből.", (8.0, 10.0)),
                                ("Megkaptam: 16/23 lett.", (16.0, 23.0)), ("18/20 pontot kaptam.", (18.0, 20.0))):
            with self.subTest(mondat=mondat):
                e = E.eredmeny(mondat)
                self.assertEqual((e["pont"], e["max"]), varhato)

    def test_ellentmondas_nem_valaszt_csendben(self):
        k = E.kinyer("68% lett (18/31), ami hármas.")
        self.assertIsNone(k.eredmeny)
        self.assertEqual({j["forras"] for j in k.ellentmondas["jeloltek"]}, {"68%", "18/31"})

    def test_az_egyezo_pont_es_szazalek_egy_eredmeny(self):
        k = E.kinyer("69,6% lett (16/23), ami négyes.")
        self.assertIsNone(k.ellentmondas)
        self.assertEqual((k.eredmeny["pont"], k.eredmeny["max"]), (16.0, 23.0))
        self.assertEqual(E.kinyer("85% lett az eredményem.").eredmeny["szazalek"], 85.0)
        self.assertIsNone(E.eredmeny("A tanulás 85%-a megvolt."), "nincs eredményjelző / rag")

    def test_ket_kulonbozo_eredmeny_ellentmondas(self):
        k = E.kinyer("Az első 14/20 lett. A javított 18/20 lett.")
        self.assertIsNone(k.eredmeny)
        self.assertIsNotNone(k.ellentmondas)

    def test_a_hataresetek(self):
        self.assertIsNone(E.eredmeny("A 10/6 dátum"), "pont > max")
        self.assertIsNone(E.eredmeny("Fél óra, 1/2 óra"), "eredményjelző nélküli tört")
        self.assertIsNone(E.eredmeny("25/0 pont lett"), "max = 0")
        self.assertIsNone(E.eredmeny(""))
        e = E.eredmeny("A 20-ből 17 pontot kaptam.")
        self.assertEqual((e["pont"], e["max"]), (17.0, 20.0))
        e = E.eredmeny("**13,5/16** lett")
        self.assertEqual((e["pont"], e["max"]), (13.5, 16.0))
        e = E.eredmeny("Összesen 46 pontot kaptam az 50-ből.")
        self.assertEqual((e["pont"], e["max"]), (46.0, 50.0))

    def test_a_talalatok_indokot_adnak(self):
        k = E.kinyer("Plusz munkán 26/26 pontot szereztem. Aztán 13/16 pontos lett.")
        kizart = [t for t in k.talalatok if not t.elfogadva]
        self.assertEqual(len(kizart), 1)
        self.assertIn("pluszpont", kizart[0].ok)


class Szakaszolas(unittest.TestCase):
    JEGYZET = ("---\nTags:\n  - Dolgozat-kiértékelés\nSource:\nStatus:\n---\n\n# Szeptember 08: Történelem esszé\n\n[[2026-09-08 - Történelem]]\n\n"
               "16/23 lett.\n\n```\n# nem címsor\n```\n\n# Szeptember 14: Matek\n[[2026-09-14 - Matematika|Matek]] és [[más]]\n14/24-es lett.\n\n"
               "## Alcím\nszöveg\n\n# Szeptemberi összegzés\nSemmi link.\n")

    def test_a_szakaszok_cime_linkje_es_sora(self):
        sz = E.szakaszok(self.JEGYZET)
        self.assertEqual([x.cim for x in sz], ["Szeptember 08: Történelem esszé", "Szeptember 14: Matek", "Szeptemberi összegzés"])
        self.assertEqual([x.link for x in sz], ["2026-09-08 - Történelem", "2026-09-14 - Matematika", None])
        self.assertEqual(sz[0].sor, 8)
        self.assertIn("# nem címsor", sz[0].torzs)
        self.assertIn("Alcím", sz[1].torzs)

    def test_frontmatter_nelkul_es_ures(self):
        self.assertEqual(E.szakaszok(""), [])
        self.assertEqual(E.szakaszok("nincs címsor\n[[x]]"), [])
        self.assertEqual(len(E.szakaszok("# A\n[[x]]")), 1)

    def test_jegyzetenkent_osszegez(self):
        se = {x.szakasz.cim: x for x in E.szakasz_eredmenyek(self.JEGYZET)}
        ki = E.jegyzetenkent([("A.md", se["Szeptember 08: Történelem esszé"]), ("B.md", se["Szeptember 14: Matek"]),
                              ("C.md", se["Szeptemberi összegzés"])])
        self.assertEqual(ki["A.md"]["eredmeny"]["max"], 23.0)
        self.assertEqual(ki["B.md"]["eredmeny"]["pont"], 14.0)
        self.assertIsNone(ki["C.md"]["eredmeny"])

    def test_ugyanahhoz_a_jegyzethez_ket_kulonbozo_szakasz_ellentmondas(self):
        a = E.szakasz_eredmenyek("# A\n[[x]]\n14/20 lett.\n# B\n[[x]]\n18/20 lett.\n")
        ki = E.jegyzetenkent([("X.md", s) for s in a])
        self.assertIsNone(ki["X.md"]["eredmeny"])
        self.assertIsNotNone(ki["X.md"]["ellentmondas"])
        egyezo = E.szakasz_eredmenyek("# A\n[[x]]\n14/20 lett.\n# B\n[[x]]\n14/20 pontos lett.\n")
        ki = E.jegyzetenkent([("X.md", s) for s in egyezo])
        self.assertEqual(ki["X.md"]["eredmeny"]["pont"], 14.0)


class SzabottMezo(unittest.TestCase):
    """C28c (K348): a szakasz `Eredmény::` inline mezője elsőbbséget kap a szabad szöveg előtt."""

    def test_pont_per_max(self):
        k = E.kinyer("[[x]]\nEredmény:: 16/23\n")
        self.assertEqual(k.eredet, "mezo")
        self.assertEqual((k.eredmeny["pont"], k.eredmeny["max"], k.eredmeny["szazalek"]), (16.0, 23.0, 69.6))
        self.assertEqual((k.eredmeny["eredet"], k.eredmeny["fajta"], k.eredmeny["forras"]), ("mezo", "pont", "Eredmény:: 16/23"))

    def test_szazalek(self):
        k = E.kinyer("Eredmény:: 68%")
        self.assertEqual((k.eredmeny["pont"], k.eredmeny["szazalek"], k.eredmeny["fajta"]), (None, 68.0, "szazalek"))
        self.assertEqual(E.kinyer("Eredmény:: 72,5 %").eredmeny["szazalek"], 72.5)

    def test_pont_es_egyezo_szazalek(self):
        for ertek in ("16/23 (70%)", "16/23 (69,6%)", "16 / 23 pont (70 %)", "13.5/16 (84%)"):
            with self.subTest(ertek=ertek):
                k = E.kinyer(f"Eredmény:: {ertek}")
                self.assertIsNotNone(k.eredmeny, ertek)
                self.assertIsNone(k.ellentmondas)
                self.assertIsNotNone(k.eredmeny["pont"])

    def test_ellentmondo_mezo_jelzett_hiany(self):
        k = E.kinyer("[[x]]\nEredmény:: 18/31 (68%)\n16/23 lett.\n")
        self.assertEqual(k.eredet, "mezo")
        self.assertIsNone(k.eredmeny)                       # a szövegre sem esik vissza
        self.assertIn("ellentmond", k.ellentmondas["ok"])
        self.assertEqual(k.ellentmondas["jeloltek"][0]["forras"], "Eredmény:: 18/31 (68%)")

    def test_olvashatatlan_es_lehetetlen_ertek_jelzett_hiany(self):
        for ertek in ("négyes", "25/23", "16/0", "120%", "16/23 70%", "kb. 16/23"):
            with self.subTest(ertek=ertek):
                k = E.kinyer(f"Eredmény:: {ertek}\n16/23 lett.")
                self.assertIsNone(k.eredmeny)
                self.assertEqual(k.eredet, "mezo")
                self.assertIsNotNone(k.ellentmondas)

    def test_ket_ellentmondo_mezo_es_ket_egyezo(self):
        k = E.kinyer("Eredmény:: 14/20\nEredmény:: 18/20\n")
        self.assertIsNone(k.eredmeny)
        self.assertEqual(len(k.ellentmondas["jeloltek"]), 2)
        k = E.kinyer("Eredmény:: 14/20\nEredmény:: 70%\n")
        self.assertEqual((k.eredmeny["pont"], k.eredmeny["max"]), (14.0, 20.0))   # a pont/max az elsődleges alak

    def test_a_mezo_elsobbsege_a_szoveg_elott(self):
        # a szöveg önmagában ellentmondó („68% lett (18/31)”): a mező feloldja
        szoveg = SZAKASZOK[3][1] + "\nEredmény:: 18/31\n"
        self.assertIsNotNone(E.kinyer(SZAKASZOK[3][1]).ellentmondas)
        k = E.kinyer(szoveg)
        self.assertEqual((k.eredet, k.eredmeny["pont"], k.eredmeny["max"]), ("mezo", 18.0, 31.0))
        # a szöveg mást mond, a mező nyer
        k = E.kinyer("[[x]]\nMegkaptam: 16/23 lett.\nEredmény:: 17/23\n")
        self.assertEqual(k.eredmeny["pont"], 17.0)

    def test_mezo_nelkul_a_szoveg_dont(self):
        k = E.kinyer("[[x]]\nMegkaptam az eredményt: 16/23 lett.\n")
        self.assertEqual((k.eredet, k.eredmeny["eredet"]), ("szoveg", "szoveg"))
        self.assertIsNone(E.kinyer("A dolgozat jól sikerült.").eredet)
        # az üres mező (sablonból) nem mező
        k = E.kinyer("Eredmény::\nMegkaptam az eredményt: 16/23 lett.\n")
        self.assertEqual((k.eredet, k.eredmeny["pont"]), ("szoveg", 16.0))

    def test_a_mezo_alakvaltozatai(self):
        for sor in ("eredmény:: 16/23", "Eredmeny:: 16/23", "EREDMÉNY :: 16/23", "- Eredmény:: 16/23", "> Eredmény:: 16/23",
                    "**Eredmény**:: 16/23", "  * Eredmény::16/23", "Eredme\u0301ny:: 16/23"):
            with self.subTest(sor=sor):
                k = E.kinyer(f"[[x]]\n{sor}\n")
                self.assertEqual(k.eredet, "mezo", sor)
                self.assertEqual(k.eredmeny["pont"], 16.0)

    def test_nem_mezo(self):
        # kódblokkban, sor közepén, szimpla kettősponttal, más kulccsal: nem a szabott mező (a szöveg dönt vagy nincs eredmény)
        for szoveg in ("```\nEredmény:: 16/23\n```\n", "Azt írtam: Eredmény:: 16/23", "Eredmény: 16/23", "Pont:: 16/23",
                       "`Eredmény:: 16/23`"):
            with self.subTest(szoveg=szoveg):
                self.assertNotEqual(E.kinyer(szoveg).eredet, "mezo")

    def test_mezo_ertek_elemzo(self):
        self.assertEqual(E.mezo_ertek("16/23")[0]["fajta"], "pont")
        e, ok = E.mezo_ertek("16/23 (50%)")
        self.assertIsNone(e)
        self.assertIn("69,6%", ok)
        self.assertEqual(E.mezo_ertek("0/10")[0]["szazalek"], 0.0)
        self.assertEqual(E.mezo_ertek("100%")[0]["szazalek"], 100.0)

    def test_jegyzeten_belul_a_mezos_szakasz_nyer(self):
        a = E.szakasz_eredmenyek("# A\n[[x]]\n14/20 lett.\n# B\n[[x]]\nEredmény:: 18/20\n")
        ki = E.jegyzetenkent([("X.md", s) for s in a])
        self.assertEqual((ki["X.md"]["eredmeny"]["pont"], ki["X.md"]["eredet"], ki["X.md"]["szakasz_cim"]), (18.0, "mezo", "B"))
        a = E.szakasz_eredmenyek("# A\n[[x]]\n14/20 lett.\n# B\n[[x]]\nEredmény:: 18/20 (50%)\n")
        ki = E.jegyzetenkent([("X.md", s) for s in a])
        self.assertIsNone(ki["X.md"]["eredmeny"])         # a hibás mező nem esik vissza a másik szakasz szövegére
        self.assertEqual(ki["X.md"]["eredet"], "mezo")
        a = E.szakasz_eredmenyek("# A\n[[x]]\n14/20 lett.\n")
        self.assertEqual(E.jegyzetenkent([("X.md", s) for s in a])["X.md"]["eredet"], "szoveg")


if __name__ == "__main__":
    unittest.main()
