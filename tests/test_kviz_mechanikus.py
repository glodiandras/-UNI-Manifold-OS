"""C22a: a jelölt kérdés mechanikus kapuja (`modulok/kviz/mechanikus.py`) — a legacy kvízlánc tesztjeinek portja."""
import unittest

from modulok.kviz import mechanikus as m
from modulok.kviz.mechanikus import Jelolt


def jo(**kw) -> Jelolt:
    alap = dict(kerdes="Mi a kifejtés?", valaszok={"A": "$a^2+2ab+b^2$", "B": "$a^2-2ab+b^2$", "C": "$a^2+b^2$", "D": "$2ab$"},
                helyes="A", idezet="x", magyarazat="mert")
    alap.update(kw)
    return Jelolt(**alap)


class KapuTest(unittest.TestCase):
    def test_jo_jelolt_atmegy_az_elojel_kulonbseg_negy_valasz(self):
        self.assertIsNone(m.kapu(jo()))                       # „a²+2ab+b²” és „a²−2ab+b²” két külön válasz

    def test_hibak_kod_szerint(self):
        v = jo().valaszok
        rossz = [({"helyes": "E"}, "szerkezet"), ({"helyes": None}, "szerkezet"), ({"helyes": "AB"}, "szerkezet"), ({"kerdes": "Rövid?"}, "szerkezet"),
                 ({"valaszok": {**v, "D": ""}}, "szerkezet"), ({"valaszok": {"A": "x", "B": "y", "C": "z"}}, "szerkezet"),
                 ({"valaszok": {**v, "D": "$a^2 + b^2$"}}, "valaszok"),                    # a C-vel azonos (szóközök nélkül)
                 ({"valaszok": {**v, "D": "egyik sem"}}, "tiltott_valasz"), ({"valaszok": {**v, "D": "A és B"}}, "tiltott_valasz"),
                 ({"valaszok": {**v, "D": "Mindegyik"}}, "tiltott_valasz"),
                 ({"magyarazat": "páratlan $a"}, "jeloles"), ({"kerdes": "Mi a ==kiemelt== kifejtés?"}, "jeloles"),
                 ({"magyarazat": "pipa ✅"}, "jeloles"), ({"magyarazat": "link [[x]]"}, "jeloles"),
                 ({"magyarazat": "<b>vastag</b>"}, "jeloles"), ({"magyarazat": "két\nsor"}, "jeloles"),
                 ({"kerdes": "Igaz-e, hogy $a^2+2ab+b^2$ a kifejtés?"}, "kiszivargas")]
        for valtozas, kod in rossz:
            self.assertEqual(m.kapu(jo(**valtozas))[0], kod, valtozas)

    def test_az_engedett_jelek(self):
        self.assertIsNone(m.kapu(jo(magyarazat="✓ jó, ✗ rossz, ▸ tovább")))

    def test_jelhiba(self):
        self.assertIsNone(m.jelhiba("Szép $x^2$ képlet és **vastag** szöveg"))
        self.assertEqual(m.jelhiba("$$ páratlan"), "páratlan $")
        self.assertEqual(m.jelhiba("kód %% megjegyzés"), "link, megjegyzés vagy sortörés")
        self.assertEqual(m.jelhiba("c <div> d"), "HTML-jelölés")
        self.assertIn("tiltott jel", m.jelhiba("hurrá 🎉"))

    def test_a_valaszok_osszevetese_a_muveleti_jelet_megtartja_a_zaro_irasjelet_nem(self):
        self.assertNotEqual(m._norm("$a+b$"), m._norm("$a-b$"))
        self.assertEqual(m._norm(" Teljes négyzet. "), m._norm("teljes négyzet"))


if __name__ == "__main__":
    unittest.main()
