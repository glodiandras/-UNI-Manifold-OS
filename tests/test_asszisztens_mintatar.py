"""J1/J3: a mintatár és a javaslat-kártya jelöltjei álvaulton — a jegyzetszerkezet a testvérjegyzetekből (index), az ismétlődő
művelet a felület jelzéseiből (küszöb után), a tartalmi kiegészítés a (befecskendezett) hasonló jegyzetekből; a hangolás néma
fajtája nem jön, az elutasított javaslat egy ideig nem tér vissza; kikapcsolt Asszisztensnél semmi; a vaultba nem ír."""
import json
import os
import unittest

from core.asszisztens.allapot import Allapot
from core.asszisztens.hangolo import Hangolo
from core.asszisztens.mintatar import Mintatar
from core.utvonalak import HttpError
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit

FM = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
ALAP = {
    "M - Matek/01 - Függvények.md": FM + "# Függvények\n\n## Definíció\n\nx\n\n## Példák\n\ny\n",
    "M - Matek/02 - Sorozatok.md": FM + "# Sorozatok\n\n## Definíció\n\nx\n\n## Példák\n\ny\n",
    "M - Matek/03 - Határérték.md": FM + "# Határérték\n\n## Definíció\n\nx\n\n## példák\n\ny\n",
    "M - Matek/04 - Deriválás.md": FM + "# Deriválás\n\n## Definíció\n\nx\n",
    "M - Matek/05 - Új.md": FM + "# Új\n\n## Definíció\n\nszöveg\n",
    "H - Történelem/Reformkor.md": FM + "# Reformkor\n",
    "X01 - Napló & To-Do/2026-10/Napló/2026-10-14.md": FM + "# Napló\n",
}
UJ = "M - Matek/05 - Új.md"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, ALAP)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.be = True
        self.most = 1_800_000_000.0
        self.a = Allapot(self.cfg)
        self.h = Hangolo(self.cfg, self.a, ido=lambda: self.most)
        self.hasonlo = {"allapot": "ok", "talalatok": []}
        self.m = Mintatar(self.cfg, self.ix, self.a, self.h, lambda: self.be, hasonlok=lambda ut, n: self.hasonlo,
                          ido=lambda: self.most)

    def kartya(self, szoveg=None, ut=UJ, alkalom="szunet"):
        if szoveg is None:
            szoveg = (self.v / ut).read_text(encoding="utf-8")
        return self.m.kartya({"ut": ut, "szoveg": szoveg, "alkalom": alkalom})

    def vault_lenyomat(self):
        return sorted((str(p.relative_to(self.v)), p.stat().st_mtime_ns) for p in self.v.rglob("*") if p.is_file())


class SzerkezetTest(Alap):
    def test_hianyzo_szakasz_a_testverekbol(self):
        r = self.kartya()
        j = r["javaslat"]
        self.assertEqual(j["tipus"], "szerkezet")
        self.assertEqual(j["muvelet"], {"fajta": "szakasz", "szoveg": "## Példák"})
        self.assertIn("3-ban", j["indok"])                     # a „példák” kisbetűs alakja is számít (kis-nagybetű-független)
        self.assertEqual(j["helyzet"], "szunet_rovid")
        self.assertGreater(r["varakozas_mp"], 0)

    def test_a_mentetlen_szoveg_szamit(self):
        r = self.kartya(FM + "# Új\n\n## Definíció\n\n## Példák\n")
        self.assertIsNone(r["javaslat"])

    def test_keves_testver_nem_minta(self):
        self.assertIsNone(self.kartya(ut="H - Történelem/Reformkor.md")["javaslat"])

    def test_kizart_mappa_es_kikapcsolt_asszisztens(self):
        self.assertIsNone(self.kartya(ut="X01 - Napló & To-Do/2026-10/Napló/2026-10-14.md")["javaslat"])
        self.be = False
        r = self.kartya()
        self.assertIsNone(r["javaslat"])
        self.assertFalse(r["kapcsolo"])

    def test_elutasitas_nem_ter_vissza_es_a_vault_erintetlen(self):
        elotte = self.vault_lenyomat()
        j = self.kartya()["javaslat"]
        self.assertTrue(self.m.dontes({"azon": j["azon"], "tipus": j["tipus"], "helyzet": j["helyzet"], "dontes": "elutasit",
                                       "cim": j["cim"]})["fogadva"])
        self.assertIsNone(self.kartya()["javaslat"])
        self.assertEqual([e["kulcs"] for e in self.m.lista()["elutasitott"]], [j["azon"]])
        self.most += 31 * 86400
        self.assertEqual(self.kartya()["javaslat"]["azon"], j["azon"])          # a lejárat után visszatérhet
        self.assertEqual(self.vault_lenyomat(), elotte)

    def test_nema_fajta_nem_jon(self):
        for _ in range(5):
            self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")
        self.assertIsNone(self.kartya()["javaslat"])
        self.assertIsNotNone(self.kartya(alkalom="megnyitas")["javaslat"])     # más helyzetben még (óvatosan) igen

    def test_ervenytelen_keres(self):
        for d in ({"ut": "a.pdf", "szoveg": ""}, {"ut": UJ}, {"ut": UJ, "szoveg": "", "alkalom": "mindig"}):
            with self.assertRaises(HttpError):
                self.m.kartya(d)
        with self.assertRaises(HttpError):
            self.m.dontes({"azon": "szerkezet:xyz", "tipus": "szerkezet", "helyzet": "a", "dontes": "elfogad"})


class IsmetlodoTest(Alap):
    def tanul(self, muvelet, ertek, ut="M - Matek/01 - Függvények.md"):
        return self.m.tanul({"muvelet": muvelet, "ut": ut, "ertek": ertek})

    def test_cimke_a_kuszob_utan(self):
        self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")            # a szerkezet ne nyerjen
        for _ in range(5):
            self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")
        self.assertFalse(self.tanul("cimke", "#Analízis")["tanult"])
        self.tanul("cimke", "Analízis", "M - Matek/02 - Sorozatok.md")
        self.assertIsNone(self.kartya()["javaslat"])
        self.assertTrue(self.tanul("cimke", "analízis")["tanult"])         # kis-nagybetűtől független kulcs
        j = self.kartya()["javaslat"]
        self.assertEqual((j["tipus"], j["muvelet"]), ("muvelet", {"fajta": "cimke", "ertek": "Analízis"}))
        self.assertIsNone(self.kartya(FM.replace("Mathematics", "Mathematics\n  - Analízis") + "# Új\n")["javaslat"])
        # más mappában nem
        self.assertIsNone(self.kartya(ut="H - Történelem/Reformkor.md")["javaslat"])
        lista = self.m.lista()["muveletek"]
        self.assertEqual([(x["muvelet"], x["ertek"], x["db"], x["tanult"]) for x in lista], [("cimke", "Analízis", 3, True)])
        self.assertTrue(self.m.torol_muvelet(lista[0]["kulcs"]))
        self.assertEqual(self.m.lista()["muveletek"], [])

    def test_link_es_sablon(self):
        for _ in range(6):
            self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")
        for _ in range(3):
            self.tanul("link", "M - Matek/04 - Deriválás.md")
        j = self.kartya()["javaslat"]
        self.assertEqual(j["muvelet"], {"fajta": "link", "cel": "M - Matek/04 - Deriválás.md"})
        self.assertIsNone(self.kartya(FM + "# Új\n\nLásd [[04 - Deriválás]].\n")["javaslat"])
        for _ in range(6):
            self.h.rogzit("muvelet", "szunet_rovid", "elutasit")
        self.assertIsNone(self.kartya()["javaslat"])

    def test_sablon_csak_rovid_jegyzetben(self):
        for _ in range(6):
            self.h.rogzit("szerkezet", "szunet_hosszu", "elutasit")
            self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")
        for _ in range(3):
            self.tanul("sablon", "_Template/Óra.md")
        self.assertEqual(self.kartya()["javaslat"]["muvelet"], {"fajta": "sablon", "ut": "_Template/Óra.md"})
        self.assertIsNone(self.kartya(FM + "# Új\n\n" + "hosszú szöveg " * 300)["javaslat"])

    def test_kikapcsolva_nem_tanul_es_rossz_bemenet(self):
        self.be = False
        self.assertFalse(self.tanul("cimke", "X")["fogadva"])
        self.assertFalse(self.a.ut.exists())
        self.be = True
        for d in ({"muvelet": "torles", "ut": UJ, "ertek": "x"}, {"muvelet": "cimke", "ut": "a.pdf", "ertek": "x"},
                  {"muvelet": "cimke", "ut": UJ, "ertek": "a\nb"}, {"muvelet": "cimke", "ut": UJ, "ertek": ""}):
            with self.assertRaises(HttpError):
                self.m.tanul(d)


class TartalomTest(Alap):
    def test_kapcsolodo_jegyzet_a_vektortarbol(self):
        for _ in range(6):
            self.h.rogzit("szerkezet", "szunet_rovid", "elutasit")
        self.hasonlo = {"allapot": "ok", "talalatok": [
            {"ut": "M - Matek/02 - Sorozatok.md", "pont": 0.9, "kimeno": True, "bejovo": False},
            {"ut": "ATTCHMNTS - cards/x.md", "pont": 0.95, "kimeno": False, "bejovo": False},
            {"ut": "M - Matek/03 - Határérték.md", "pont": 0.8, "kimeno": False, "bejovo": False},
            {"ut": "M - Matek/04 - Deriválás.md", "pont": 0.5, "kimeno": False, "bejovo": False}]}
        j = self.kartya()["javaslat"]
        self.assertEqual((j["tipus"], j["muvelet"]), ("tartalom", {"fajta": "link", "cel": "M - Matek/03 - Határérték.md"}))
        self.hasonlo = {"allapot": "nincs_tar", "talalatok": []}
        self.assertIsNone(self.kartya()["javaslat"])

    def test_hiba_a_forrasban_nem_tori_a_kartyat(self):
        def hiba(ut, n):
            raise RuntimeError("nincs vektortár")
        self.m.hasonlok = hiba
        self.assertEqual(self.kartya()["javaslat"]["tipus"], "szerkezet")


class AllapotfajlTest(Alap):
    def test_minden_a_state_alatt(self):
        self.m.tanul({"muvelet": "cimke", "ut": UJ, "ertek": "Analízis"})
        j = self.kartya()["javaslat"]
        self.m.dontes({"azon": j["azon"], "tipus": j["tipus"], "helyzet": j["helyzet"], "dontes": "elfogad"})
        self.assertEqual(self.a.ut.parent, self.cfg.path("state"))
        d = json.loads(self.a.ut.read_text(encoding="utf-8"))
        self.assertEqual(set(d) & {"muveletek", "kartya_dontesek", "hangolas"}, {"muveletek", "kartya_dontesek", "hangolas"})
        self.m.torol_mind()
        self.assertEqual(self.m.lista(), {"muveletek": [], "elutasitott": []})


if __name__ == "__main__":
    unittest.main()
