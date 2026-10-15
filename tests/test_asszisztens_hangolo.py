"""J1: az önhangoló gyakoriság — kezdetben bátrabb, az elutasított fajta ritkul, végül elnémul; a helyzet a fajtához húz; a döntések
súlya kopik; minden a `{state}/asszisztens.json`-ban, útvonal és szöveg nélkül; soronként törölhető."""
import json
import unittest

from core.asszisztens.allapot import Allapot
from core.asszisztens.hangolo import Hangolo
from core.utvonalak import HttpError
from tests.helpers import alg_core, tmpdir

NAP = 86400.0


class HangoloTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.cfg, _, self.v = alg_core(self.t.name)
        self.most = 1_800_000_000.0
        self.a = Allapot(self.cfg)
        self.h = Hangolo(self.cfg, self.a, ido=lambda: self.most)

    def test_kezdetben_batrabb(self):
        a = self.h.allas("szerkezet", "szunet_rovid")
        self.assertEqual(a["szint"], "batrabb")
        self.assertLess(a["szorzo"], 1.0)
        self.assertFalse(self.a.ut.exists(), "olvasás nem hoz létre állapotfájlt")

    def test_elutasitas_ritkit_majd_nemit(self):
        szintek = []
        for _ in range(5):
            szintek.append(self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")["szint"])
        self.assertIn("ritkabb", szintek)
        self.assertEqual(szintek[-1], "nema")
        self.assertIsNone(self.h.allas("szerkezet", "szunet_rovid")["szorzo"])
        # a fajta többi helyzete is óvatosabb lesz (a fajta becslése húzza), de még nem néma
        masik = self.h.allas("szerkezet", "megnyitas_rovid")
        self.assertIn(masik["szint"], ("ritkabb", "alap"))

    def test_elfogadas_gyakorit(self):
        for _ in range(4):
            self.h.rogzit("muvelet", "szunet_kozepes", "elfogad")
        a = self.h.allas("muvelet", "szunet_kozepes")
        self.assertEqual(a["szint"], "batrabb")
        self.assertLess(a["szorzo"], self.h.allas("tartalom", "szunet_kozepes")["szorzo"] + 1e-9)

    def test_fajta_egesze_nemul(self):
        for helyzet in ("szunet_rovid", "szunet_kozepes", "megnyitas_rovid", "megnyitas_hosszu", "szunet_hosszu"):
            for _ in range(2):
                self.h.rogzit("tartalom", helyzet, "elutasit")
        self.assertEqual(self.h.allas("tartalom", "megnyitas_kozepes")["szint"], "nema")

    def test_figyelmen_kivul_kis_sullyal(self):
        for _ in range(5):
            self.h.rogzit("kiegeszites", "folytat", "figyelmen_kivul")
        self.assertNotEqual(self.h.allas("kiegeszites", "folytat")["szint"], "nema")

    def test_kopas_visszahozza_az_elnemultat(self):
        for _ in range(6):
            self.h.rogzit("link", "szoveg", "elutasit")
        self.assertEqual(self.h.allas("link", "szoveg")["szint"], "nema")
        self.most += 120 * NAP
        self.assertNotEqual(self.h.allas("link", "szoveg")["szint"], "nema")

    def test_tarolas_utvonal_nelkul_es_torles(self):
        self.h.rogzit("link", "szoveg", "elfogad")
        d = json.loads(self.a.ut.read_text(encoding="utf-8"))
        self.assertEqual(list(d["hangolas"]), ["link|szoveg"])
        self.assertEqual(set(d["hangolas"]["link|szoveg"]), {"e", "u", "t"})
        self.assertEqual([x["kulcs"] for x in self.h.lista()], ["link|szoveg"])
        self.assertTrue(self.h.torol("link|szoveg"))
        self.assertFalse(self.h.torol("link|szoveg"))
        self.assertEqual(self.h.lista(), [])
        self.assertEqual(list(self.v.rglob("*.md")), [])

    def test_ervenytelen_bemenet(self):
        for tipus, helyzet, dontes in (("x", "a", "elfogad"), ("link", "A/B", "elfogad"), ("link", "szoveg", "talan")):
            with self.assertRaises(HttpError):
                self.h.rogzit(tipus, helyzet, dontes)

    def test_serult_allapot_nem_dont(self):
        self.a.ut.parent.mkdir(parents=True, exist_ok=True)
        self.a.ut.write_text(json.dumps({"hangolas": {"link|szoveg": {"e": "x"}, "rossz": 5}}), encoding="utf-8")
        self.assertEqual(self.h.allas("link", "szoveg")["szint"], "batrabb")
        self.h.rogzit("link", "szoveg", "elfogad")
        self.assertEqual(self.h.lista()[0]["elfogad"], 1.0)


if __name__ == "__main__":
    unittest.main()
