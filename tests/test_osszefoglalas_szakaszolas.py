"""C26a: szakaszolás, horgony-keresés és a videó-szint (`modulok/osszefoglalas/szakaszolas.py`, `video.py`)."""
import unittest

from core.index import elemzo
from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import lanc as L
from modulok.osszefoglalas import szakaszolas as SZ
from modulok.osszefoglalas import video as V
from tests.test_osszefoglalas_lanc import CEL, JEGYZET, Q1, valasz

HOSSZU = "# Hosszú\n\n## Egy\n\n" + "\n\n".join(f"Ez a {i}. bekezdés, amelyben a mértani sorozat hányadosa állandó, a tagok szorzata pedig a közbülső tagok szorzata." for i in range(30)) + "\n\n## Kettő\n\nRövid szakasz, de van benne elég szöveg a kapu számára.\n"


class Darabolas(unittest.TestCase):
    def test_fejezethatar_es_kihagyott_szakasz(self):
        j = elemzo.elemez(JEGYZET)
        b = SZ.jegyzet_bemenet(JEGYZET, CEL, "Caesar", j.fejezetek, j.blokkok)
        self.assertEqual(len(b.darabok), 1)                                   # a rövid szakaszok egy darabba fűződnek
        sz = b.darabok[0].szoveg
        self.assertIn("[Az első triumvirátus]", sz)
        self.assertIn("[A Rubicon átlépése]", sz)
        self.assertNotIn("IMG_0001", sz)                                       # Füzet: kiesik
        self.assertNotIn("^m-3f2a", sz)                                        # a blokkazonosító nem tartalom
        self.assertEqual(len(b.bekezdesek()), 3)

    def test_hosszu_szakasz_bekezdeshataron_osztva(self):
        b = SZ.jegyzet_bemenet(HOSSZU, "H", "Hosszú", max_karakter=900)
        self.assertGreater(len(b.darabok), 3)
        for d in b.darabok:
            self.assertLessEqual(len(d.szoveg), 900 + 80)
            self.assertTrue(d.szoveg.startswith("["))                          # minden darab fejezet-útvonallal indul
        osszes = [x.szoveg for x in b.bekezdesek()]
        self.assertEqual(len(osszes), 31)                                      # semmi nem vész el, semmi nem duplázódik

    def test_index_tabla_nelkul_is_megy(self):
        b = SZ.jegyzet_bemenet(JEGYZET, CEL, "Caesar")
        h, _ = SZ.horgony_keres(b, 1, "Mikor Caesart a senatus Rómába rendelte (Kr. e. 49)")
        self.assertEqual(h.link(), f"[[{CEL}#A Rubicon átlépése|forrás]]")
        h, _ = SZ.horgony_keres(b, 0, Q1)
        self.assertIsNone(h.alcel if h.alcel and h.alcel.startswith("^") else None)      # blokk-tábla nélkül nincs ^blokk

    def test_az_index_nem_ismert_fejezet_nem_horgony(self):
        j = elemzo.elemez(JEGYZET)
        b = SZ.jegyzet_bemenet(JEGYZET, CEL, "Caesar", [f for f in j.fejezetek if f["szoveg"] != "A Rubicon átlépése"], j.blokkok)
        h, _ = SZ.horgony_keres(b, 1, "Mikor Caesart a senatus Rómába rendelte")
        self.assertEqual(h.link(), f"[[{CEL}|forrás]]")                          # a jegyzetre mutat

    def test_listaelem_blokkazonosito(self):
        md = "# L\n\n## Lista\n\n- Az első tétel hosszabb szöveggel, amely a kapu számára is elég. ^t-aaa1\n- A második tétel szintén hosszabb szöveggel és adatokkal. ^t-bbb2\n"
        j = elemzo.elemez(md)
        b = SZ.jegyzet_bemenet(md, "L", "L", j.fejezetek, j.blokkok)
        h, _ = SZ.horgony_keres(b, 0, "A második tétel szintén hosszabb szöveggel és adatokkal.")
        self.assertEqual(h.alcel, "^t-bbb2")
        h, _ = SZ.horgony_keres(b, 0, "Az első tétel hosszabb szöveggel, amely a kapu számára is elég.")
        self.assertEqual(h.alcel, "^t-aaa1")

    def test_ket_bekezdesen_atnyulo_talalat_az_elsore_horgonyoz(self):
        b = SZ.jegyzet_bemenet(JEGYZET, CEL, "Caesar", elemzo.elemez(JEGYZET).fejezetek, elemzo.elemez(JEGYZET).blokkok)
        h, bek = SZ.horgony_keres(b, 0, "Caesar karrierjének fontos állomását jelentette, hogy kibékítette egymással")
        self.assertEqual(h.alcel, "^m-3f2a")

    def test_ures_bemenet(self):
        b = SZ.jegyzet_bemenet("---\nTags: []\n---\n", "X", "X")
        self.assertEqual(b.darabok, [])
        with self.assertRaises(L.Megall):
            L.osszefoglal(b, lambda p, m: "", "m", "X")


CUES = [(0, "Üdvözlöm a hallgatókat az előadáson."), (12, "A mai téma a mértani sorozat és a hányados."),
        (45, "A hányados két egymást követő tag aránya, ez állandó."), (70, ""), (75, "A következő rész a végtelen mértani sor összege."),
        (130, "Az összeg akkor létezik, ha a hányados abszolút értéke kisebb, mint egy.")]


class VideoSzint(unittest.TestCase):
    def test_ablakok(self):
        a = V.ablakok(CUES, 60)
        self.assertEqual([m for m, _ in a], [0, 75])                            # az üres cue kiesik; a 130. mp még a 75-ös ablak (55 s)
        self.assertIn("mértani sorozat és a hányados", a[0][1])

    def test_video_lanc_idokod_horgonnyal(self):
        cel = "T03/Média/Előadás.mp4"
        bem = V.video_bemenet(CUES, cel, "Előadás", ablak_mp=60)
        q = "A hányados két egymást követő tag aránya, ez állandó."
        r = valasz({"allitas": "A hányados két egymást követő tag aránya, és állandó.", "idezet": q},
                   {"allitas": "A végtelen mértani sor összege akkor létezik, ha a hányados abszolút értéke kisebb egynél.",
                    "idezet": "Az összeg akkor létezik, ha a hányados abszolút értéke kisebb, mint egy."},
                   {"allitas": "A mai téma a mértani sorozat és a hányados volt az előadáson.",
                    "idezet": "A mai téma a mértani sorozat és a hányados."})
        e = L.osszefoglal(bem, lambda p, m: r, "almodell", "Előadás", szint="video", b=L.Beallitas(allitas_min=3))
        self.assertEqual(e.osszefoglalo.szint, "video")
        self.assertEqual([a.horgony.link() for a in e.osszefoglalo.allitasok],
                         [f"[[{cel}#t=0|0:00]]", f"[[{cel}#t=0|0:00]]", f"[[{cel}#t=75|1:15]]"])
        self.assertEqual(FM.elemez(FM.ir(e.osszefoglalo)).hibak, [])


if __name__ == "__main__":
    unittest.main()
