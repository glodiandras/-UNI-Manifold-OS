"""C26a: az összefoglaló lánc modell nélküli része (`modulok/osszefoglalas/lanc.py`) álhívóval.

A hívható forgatókönyvezett válaszokat ad; a vaultba a lánc nem ír. A kapu a közös `modulok/kapuk` (új kapu nincs)."""
import json
import unittest

from core.index import elemzo
from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import lanc as L
from modulok.osszefoglalas import szakaszolas as SZ

RP = "T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar.md"
CEL = RP.removesuffix(".md")
JEGYZET = """---
Tags:
  - History
Source:
  - "[[10 - Történelem.pdf#page=93]]"
Status:
NN:
---

# A polgárháborúk kora és Caesar

## Az első triumvirátus

Caesar karrierjének fontos állomását jelentette, hogy kibékítette egymással a birodalom két legbefolyásosabb hadvezérét, Crassust és Pompeiust, majd szövetséget kötött velük a senatus ellen (Kr. e. 60). ^m-3f2a

## A Rubicon átlépése

Mikor Caesart a senatus Rómába rendelte (Kr. e. 49), hogy elszakítsák hadseregétől, döntő elhatározásra jutott: katonáival átlépte az Itália határát jelentő Rubicont.

## A polgárháború kimenetele

Caesar sorra legyőzte Pompeius légióit, majd a görögországi Pharszalosznál (Kr. e. 48) döntő vereséget mért vetélytársára.

## Füzet

![[IMG_0001.JPG]]
"""

Q1 = "kibékítette egymással a birodalom két legbefolyásosabb hadvezérét, Crassust és Pompeiust, majd szövetséget kötött velük a senatus ellen (Kr. e. 60)"
Q2 = "Mikor Caesart a senatus Rómába rendelte (Kr. e. 49), hogy elszakítsák hadseregétől, döntő elhatározásra jutott: katonáival átlépte az Itália határát jelentő Rubicont."
Q3 = "Caesar sorra legyőzte Pompeius légióit, majd a görögországi Pharszalosznál (Kr. e. 48) döntő vereséget mért vetélytársára."

A1 = {"allitas": "Caesar kibékítette Crassust és Pompeiust, és szövetséget kötött velük a senatus ellen.", "idezet": Q1}
A2 = {"allitas": "Caesar katonáival átlépte a Rubicont, amikor a senatus Rómába rendelte (Kr. e. 49).", "idezet": Q2}
A3 = {"allitas": "Caesar a görögországi Pharszalosznál győzte le Pompeius légióit (Kr. e. 48).", "idezet": Q3}


def valasz(*elemek) -> str:
    return json.dumps(list(elemek), ensure_ascii=False)


def bemenet(md=JEGYZET, cel=CEL):
    j = elemzo.elemez(md)
    return SZ.jegyzet_bemenet(md, cel, FM.cim_of(cel), j.fejezetek, j.blokkok)


def fut(valaszok, **kw):
    hivasok = []
    sor = list(valaszok)

    def hivo(prompt, max_token):
        hivasok.append((prompt, max_token))
        return sor.pop(0) if len(sor) > 1 else sor[0]
    kw.setdefault("b", L.Beallitas(karakter_per_allitas=100))
    e = L.osszefoglal(bemenet(), hivo, "almodell", FM.cim_of(CEL), **kw)
    return e, hivasok


class Alap(unittest.TestCase):
    def test_jo_allitasok_atmennek_a_jegyzet_sorrendjeben(self):
        e, hivasok = fut([valasz(A3, A1, A2)])
        o = e.osszefoglalo
        self.assertEqual([a.szoveg for a in o.allitasok], [A1["allitas"], A2["allitas"], A3["allitas"]])
        self.assertEqual(e.statisztika["elfogadott"], 3)
        self.assertEqual(e.statisztika["lefedett_szakasz"], 3)
        self.assertEqual(o.forrasok, [CEL])
        self.assertEqual(len(hivasok), 1)
        self.assertIn("A polgárháborúk kora és Caesar", hivasok[0][0])          # a jegyzet címe a promptban
        self.assertNotIn("IMG_0001", hivasok[0][0])                              # a Füzet szakasz kiesik

    def test_az_idezet_a_jegyzet_mondata_nem_a_modelle(self):
        kisbetus = dict(A1, idezet=Q1.lower())
        e, _ = fut([valasz(kisbetus, A2, A3)])
        a = e.osszefoglalo.allitasok[0]
        self.assertTrue(a.idezet.startswith("Caesar karrierjének fontos állomását"))      # a teljes jegyzet-mondat
        self.assertTrue(a.idezet.endswith("(Kr. e. 60)."))

    def test_horgony_blokk_majd_fejezet(self):
        e, _ = fut([valasz(A1, A2, A3)])
        h = [a.horgony.link() for a in e.osszefoglalo.allitasok]
        self.assertEqual(h[0], f"[[{CEL}#^m-3f2a|forrás]]")                       # a blokkazonosítós bekezdés
        self.assertEqual(h[1], f"[[{CEL}#A Rubicon átlépése|forrás]]")            # blokk nélkül a fejezet
        self.assertEqual(len(e.uj_horgonyok), 2)                                   # a C26b ezekre tenne ^m- horgonyt
        self.assertEqual({x["szakasz"] for x in e.uj_horgonyok}, {"A Rubicon átlépése", "A polgárháború kimenetele"})

    def test_forras_nelkuli_mondat_kiesik(self):
        e, _ = fut([valasz(A1, A2, A3, {"allitas": "Caesar a római történelem legnagyobb alakja volt.", "idezet": ""},
                           {"allitas": "Caesar uralkodott.", "idezet": 5})])
        self.assertEqual(e.statisztika["elvetve"], {"forras_nelkul": 2})
        self.assertEqual(len(e.osszefoglalo.allitasok), 3)

    def test_nem_a_jegyzetben_allo_idezet_kiesik_a_kapun(self):
        kitalalt = {"allitas": "Caesar Britanniában is hadjáratot vezetett a kelták ellen.",
                    "idezet": "Caesar Britanniában két hadjáratot vezetett a kelták ellen és sikeresen partra szállt"}
        e, _ = fut([valasz(A1, A2, A3, kitalalt)])
        self.assertEqual(e.statisztika["elvetve"], {"idezet": 1})
        self.assertEqual(e.elvetett[0]["ok"], "idezet")

    def test_szamcsere_es_tagadas_a_kozos_kapun_bukik(self):
        szam = dict(A1, allitas="Caesar kibékítette Crassust és Pompeiust, és szövetséget kötött velük a senatus ellen (Kr. e. 52).")
        tagadas = dict(A2, allitas="Caesar nem lépte át a Rubicont, amikor a senatus Rómába rendelte (Kr. e. 49).")
        e, _ = fut([valasz(szam, tagadas, A1, A2, A3)])
        self.assertEqual(e.statisztika["elvetve"], {"kenyes": 1, "tagadas": 1})

    def test_ismetles_es_ugyanaz_a_hely(self):
        ismetlo = dict(A1, allitas="Caesar kibékítette Crassust és Pompeiust, és szövetséget kötött velük a senatus ellen is.")
        masik_szavak = {"allitas": "Crassus és Pompeius békéjét Caesar teremtette meg, a senatus ellen fordulva.", "idezet": Q1}
        e, _ = fut([valasz(A1, ismetlo, masik_szavak, A2, A3)])
        self.assertEqual(e.statisztika["elvetve"].get("duplikatum"), 1)
        self.assertEqual(len(e.osszefoglalo.allitasok), 3)
        self.assertEqual(sum(e.statisztika["elvetve"].values()), 2)

    def test_mechanikus_kapu(self):
        j = lambda a, i=Q1: L.Jelolt(a, i)      # noqa: E731
        b = L.Beallitas()
        self.assertEqual(L.mechanikus(j(""), b)[0], "ures_allitas")
        self.assertEqual(L.mechanikus(j("Rövid állítás"), b)[0], "allitas_hossz")
        self.assertEqual(L.mechanikus(j("Caesar a [[Rubicon]] átlépésével háborút kezdett."), b)[0], "tiltott_jeloles")
        self.assertEqual(L.mechanikus(j("Caesar a ==Rubicon== átlépésével háborút kezdett."), b)[0], "tiltott_jeloles")
        self.assertEqual(L.mechanikus(j("Caesar átlépte a Rubicont és háborút kezdett.", ""), b)[0], "forras_nelkul")
        self.assertIsNone(L.mechanikus(j("Caesar átlépte a Rubicont és háborút kezdett."), b))

    def test_kevesebb_mint_a_minimum_megall(self):
        with self.assertRaises(L.Megall) as cm:
            fut([valasz(A1, A2)])
        self.assertIn("az összefoglaló nem készült el", str(cm.exception))

    def test_ertelmezhetetlen_valasz(self):
        with self.assertRaises(L.Megall):
            fut(["Sajnos nem tudok segíteni."])
        e, _ = fut([valasz(A1, A2, A3)], max_allitas=3)
        self.assertEqual(e.statisztika.get("ertelmezhetetlen_valasz", 0), 0)

    def test_kerit_es_burok_tures(self):
        szoveg = "Íme az összefoglaló:\n```json\n" + json.dumps({"allitasok": [A1, A2, A3]}, ensure_ascii=False) + "\n```"
        e, _ = fut([szoveg])
        self.assertEqual(len(e.osszefoglalo.allitasok), 3)

    def test_max_allitas_a_szakaszokat_koriben_valasztja(self):
        e, _ = fut([valasz(A1, A2, A3)], max_allitas=3)
        self.assertEqual(len(e.osszefoglalo.allitasok), 3)
        e2 = L.valaszt([{"hely": (i, i), "si": si} for i, si in enumerate([0, 0, 0, 1, 2])], 3)
        self.assertEqual([q["si"] for q in e2], [0, 1, 2])                       # szakaszonként körbe, nem az elejéről

    def test_az_iras_visszaolvashato_es_hibatlan(self):
        e, _ = fut([valasz(A1, A2, A3)])
        szoveg = FM.ir(e.osszefoglalo)
        el = FM.elemez(szoveg)
        self.assertEqual(el.hibak, [])
        self.assertEqual([a.szoveg for a in el.osszefoglalo.allitasok], [a.szoveg for a in e.osszefoglalo.allitasok])
        self.assertEqual(el.osszefoglalo.allitasok[0].idezet, e.osszefoglalo.allitasok[0].idezet)

    def test_modell_es_szint_ellenorzes(self):
        with self.assertRaises(L.Megall):
            L.osszefoglal(bemenet(), lambda p, m: "", "", "cím")
        with self.assertRaises(L.Megall):
            L.osszefoglal(bemenet(), lambda p, m: "", "m", "cím", szint="ismeretlen")


class MappaTest(unittest.TestCase):
    def jegyzetek(self):
        e, _ = fut([valasz(A1, A2, A3)])
        return [(e.osszefoglalo, bemenet())]

    def test_uj_allitas_csak_ellenorzott_allitasbol(self):
        jo = {"allitas": "Caesar a senatus ellen szövetkezett két hadvezérrel.", "forras": "J1.1"}
        hamis = {"allitas": "Caesar Britanniában győzött a kelták ellen.", "forras": "J1.2"}
        hivatkozas_nelkul = {"allitas": "Caesar a történelem legnagyobb hadvezére volt.", "forras": ""}
        jo2 = {"allitas": "Caesar átlépte a Rubicont a senatus parancsa után.", "forras": "J1.2"}
        jo3 = {"allitas": "Pharszalosznál Caesar legyőzte Pompeius légióit.", "forras": "J1.3"}
        e = L.mappa_osszefoglal("Elmélet", self.jegyzetek(), lambda p, m: valasz(jo, hamis, hivatkozas_nelkul, jo2, jo3),
                                "almodell", b=L.Beallitas(mappa_max_per_jegyzet=5))
        self.assertEqual(e.osszefoglalo.szint, "mappa")
        self.assertEqual([a.szoveg for a in e.osszefoglalo.allitasok], [jo["allitas"], jo2["allitas"], jo3["allitas"]])
        self.assertEqual(e.statisztika["elvetve"], {"tamogatas": 1, "forras_nelkul": 1})
        # a link a jegyzet eredeti horgonyára mutat, az idézet a jegyzet mondata
        self.assertEqual(e.osszefoglalo.allitasok[0].horgony.alcel, "^m-3f2a")
        self.assertTrue(e.osszefoglalo.allitasok[1].idezet.startswith("Mikor Caesart"))
        self.assertEqual(FM.elemez(FM.ir(e.osszefoglalo)).hibak, [])

    def test_ervenytelen_hivatkozas_kiesik(self):
        rossz = {"allitas": "Caesar szövetséget kötött velük a senatus ellen.", "forras": "J9.9"}
        jo = [{"allitas": t, "forras": f"J1.{i}"} for i, t in enumerate([
            "Caesar a senatus ellen szövetkezett két hadvezérrel.", "Caesar átlépte a Rubicont a senatus parancsa után.",
            "Pharszalosznál Caesar legyőzte Pompeius légióit."], 1)]
        e = L.mappa_osszefoglal("Elmélet", self.jegyzetek(), lambda p, m: valasz(rossz, *jo), "almodell",
                                b=L.Beallitas(mappa_max_per_jegyzet=5))
        self.assertEqual(e.statisztika["elvetve"], {"forras_nelkul": 1})

    def test_jegyzetenkenti_plafon(self):
        valaszok = [{"allitas": t, "forras": f"J1.{i}"} for i, t in enumerate([
            "Caesar a senatus ellen szövetkezett két hadvezérrel.", "Caesar átlépte a Rubicont a senatus parancsa után.",
            "Pharszalosznál Caesar legyőzte Pompeius légióit."], 1)]
        with self.assertRaises(L.Megall):
            L.mappa_osszefoglal("Elmélet", self.jegyzetek(), lambda p, m: valasz(*valaszok), "almodell",
                                b=L.Beallitas(mappa_max_per_jegyzet=1))


if __name__ == "__main__":
    unittest.main()
