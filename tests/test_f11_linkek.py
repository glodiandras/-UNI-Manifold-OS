"""F11 (02-links): link-formátum beállítások (rövid / relatív / teljes út; wikilink vagy md), a vault-szintű fejezetkeresés,
a használt de nem létező link-szövegek, a kimenő linkeletlen említések, a stílusőrző átnevezés (relatív, teljes út,
`%` a fájlnévben) és az md-cél értelmezésének közös vektorai (a felület `markdownCel`-jével).

Álvaulton dolgozik; a valódi vaulthoz nem nyúl."""
import json
import unittest
from pathlib import Path

from core import atnevezes, snapshot, termek_beallitasok as b, vaultio
from core.asszisztens.emlites import Emlitesek
from core.index import feloldas, linkek
from core.index.feloldas import Feloldo
from core.utvonalak import HttpError
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import ALAP, alvault, index_indit

REPO = Path(__file__).resolve().parent.parent


class FormaTest(unittest.TestCase):
    def setUp(self):
        self.f = Feloldo(["A/Jegyzet.md", "B/Jegyzet.md", "Cél.md", "Mélység/Be/Cél X.md", "kep.png", "A/Mellék/Ábra.png"])

    def test_abszolut_cel_teljes_ut_es_visszaoldodik(self):
        for forras in ("x.md", "A/y.md", "B/Z/y.md"):
            for ut in sorted(self.f.fileset):
                cel = linkek.abszolut_cel(self.f, ut, forras)
                self.assertEqual(self.f.resolve(cel, forras)[0], ut, (forras, cel))
        self.assertEqual(linkek.abszolut_cel(self.f, "B/Jegyzet.md", "A/y.md"), "B/Jegyzet")
        self.assertEqual(linkek.abszolut_cel(self.f, "kep.png", "A/y.md"), "kep.png")
        self.assertEqual(linkek.abszolut_cel(self.f, "Mélység/Be/Cél X.md", "A/y.md"), "Mélység/Be/Cél X")

    def test_cel_forma_valaszt_es_ismeretlenre_rovid(self):
        self.assertEqual(linkek.cel_forma(self.f, "B/Jegyzet.md", "A/y.md", "rovid"), "B/Jegyzet")
        self.assertEqual(linkek.cel_forma(self.f, "B/Jegyzet.md", "A/y.md", "relativ"), "../B/Jegyzet")
        self.assertEqual(linkek.cel_forma(self.f, "B/Jegyzet.md", "A/y.md", "abszolut"), "B/Jegyzet")
        self.assertEqual(linkek.cel_forma(self.f, "Mélység/Be/Cél X.md", "A/y.md", "rovid"), "Cél X")
        self.assertEqual(linkek.cel_forma(self.f, "Mélység/Be/Cél X.md", "A/y.md", "abszolut"), "Mélység/Be/Cél X")
        self.assertEqual(linkek.cel_forma(self.f, "Mélység/Be/Cél X.md", "A/y.md", "ismeretlen"), "Cél X")
        self.assertEqual(linkek.cel_forma(self.f, "Mélység/Be/Cél X.md", "A/y.md", None), "Cél X")

    def test_md_cel_kodolasa_visszafejtheto_es_feloldhato(self):
        esetek = [("Cél X", "Cél X.md", None), ("Mélység/Be/Cél X", "Mélység/Be/Cél X.md", "Első rész"),
                  ("kep.png", "kep.png", None), ("a%b (1)", "a%b (1).md", "^abc"), ("a;b,c&d=e+f", "a;b,c&d=e+f.md", None),
                  ("[x] <y>", "[x] <y>.md", "Rész (2) [a]")]
        for cel, ut, alcel in esetek:
            md = linkek.md_cel_irasra(cel, ut, alcel)
            self.assertNotRegex(md, r"[ ()<>\[\]\\]")
            vissza = feloldas.md_reszek(md)
            self.assertIsNotNone(vissza, md)
            self.assertEqual(vissza[0], cel + (".md" if ut.endswith(".md") else ""), md)
            self.assertEqual(vissza[1], alcel or "", md)

    def test_md_cel_nem_ketszerezi_a_kiterjesztest(self):
        self.assertEqual(linkek.md_cel_irasra("Cél.md", "Cél.md"), "Cél.md")
        self.assertEqual(linkek.md_cel_irasra("Cél", "Cél.md"), "Cél.md")


class VektorTest(unittest.TestCase):
    def test_md_cel_vektorok_a_kozos_fajlbol(self):
        v = json.loads((REPO / "app" / "tests" / "fixtures" / "md-cel-vektorok.json").read_text(encoding="utf-8"))["vektorok"]
        self.assertGreater(len(v), 10)
        for nyers, cel, alcel in v:
            r = feloldas.md_reszek(nyers)
            if cel is None:
                self.assertIsNone(r, nyers)
            else:
                self.assertEqual(r, (cel, alcel or ""), nyers)


class IndexAlap(unittest.TestCase):
    FAJLOK = {
        **ALAP,
        "Hosszú.md": "# Cím\n## Első rész\nszöveg\n## Második\n### Árvíztűrő fejezet\n",
        "Másik.md": "# Másik cím\n## Első lépések\n",
        "Hianyzo.md": "[[Még nincs]] [[Még nincs]] ![[kép nélkül.png]] [[Cél]] [[Másik hiányzó#H]]\n[[Még nincs|alias]]\n",
        "Emlito.md": "Ma a Cél X jegyzetről és a célpont aliasról szólok. Linkelt: [[Cél]].\nA Másik is szóba kerül.\n",
    }

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _ = alvault(self._t.name, self.FAJLOK)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)

    def beallit(self, **kv):
        self.ix.cfg.data["beallitasok"]["fajlok"].update(kv)


class LinkCelApiTest(IndexAlap):
    def test_alapertelmezes_rovid_wiki(self):
        d = self.ix.link_cel("B/Jegyzet.md", "C/x.md")
        self.assertEqual((d["cel"], d["alak"]), ("B/Jegyzet", "wiki"))
        self.assertEqual(d["md"], "B/Jegyzet.md")

    def test_abszolut_formatum(self):
        self.beallit(link_formatum="abszolut")
        self.assertEqual(self.ix.link_cel("B/Jegyzet.md", "A/Forrás.md")["cel"], "B/Jegyzet")
        self.assertEqual(self.ix.link_cel("Cél X.md", "A/Forrás.md")["cel"], "Cél X")
        self.assertEqual(self.ix.link_cel("A/Jegyzet.md", "A/Forrás.md")["cel"], "A/Jegyzet")
        self.assertEqual(self.ix.feloldas("A/Forrás.md", ["A/Jegyzet"])[0]["ut"], "A/Jegyzet.md")

    def test_markdown_link_alak_a_beallitasbol(self):
        self.beallit(wikilinkek=False)
        d = self.ix.link_cel("Cél X.md", "A/Forrás.md", "Első rész")
        self.assertEqual(d["alak"], "md")
        self.assertEqual(d["md"], "Cél%20X.md#Első%20rész")
        self.assertEqual(feloldas.md_reszek(d["md"]), ("Cél X.md", "Első rész"))
        self.assertEqual(self.ix.feloldas("A/Forrás.md", ["Cél X.md"])[0]["ut"], "Cél X.md")

    def test_markdown_link_relativ_formatummal(self):
        self.beallit(wikilinkek=False, link_formatum="relativ")
        d = self.ix.link_cel("B/Jegyzet.md", "A/Forrás.md")
        self.assertEqual(d["md"], "../B/Jegyzet.md")
        self.assertEqual(self.ix.feloldas("A/Forrás.md", [feloldas.md_reszek(d["md"])[0]])[0]["ut"], "B/Jegyzet.md")

    def test_meg_nem_letezo_cel(self):
        d = self.ix.link_cel(None, "A/Forrás.md", hianyzo="Új jegyzet")
        self.assertEqual((d["ut"], d["cel"], d["alak"], d["md"]), (None, "Új jegyzet", "wiki", "Új%20jegyzet.md"))
        self.beallit(wikilinkek=False)
        d = self.ix.link_cel(None, "A/Forrás.md", "Fej", hianyzo="Új jegyzet")
        self.assertEqual((d["alak"], d["md"]), ("md", "Új%20jegyzet.md#Fej"))
        self.assertEqual(feloldas.md_reszek(d["md"]), ("Új jegyzet.md", "Fej"))
        self.assertEqual(self.ix.link_cel(None, "A/Forrás.md", hianyzo="kép.png")["md"], "kép.png")   # a melléklet kiterjesztése marad
        with self.assertRaises(vaultio.Invalid):
            self.ix.link_cel(None, "A/Forrás.md")

    def test_hibas_alcel(self):
        with self.assertRaises(vaultio.Invalid):
            self.ix.link_cel("Cél X.md", "A/Forrás.md", 5)


class FejezetekMindTest(IndexAlap):
    def test_ures_lekerdezes_a_fejezeteket_listazza(self):
        d = self.ix.fejezetek_mind("")["fejezetek"]
        szovegek = {(x["ut"], x["szoveg"]) for x in d}
        self.assertIn(("Hosszú.md", "Első rész"), szovegek)
        self.assertIn(("Másik.md", "Első lépések"), szovegek)
        self.assertTrue(all(x["sor"] >= 1 and 1 <= x["szint"] <= 6 for x in d))

    def test_ekezet_es_kisbetu_fuggetlen_szuro(self):
        d = self.ix.fejezetek_mind("arvizturo")["fejezetek"]
        self.assertEqual([(x["ut"], x["szoveg"]) for x in d], [("Hosszú.md", "Árvíztűrő fejezet")])
        d = self.ix.fejezetek_mind("ELSŐ")["fejezetek"]
        self.assertEqual({x["szoveg"] for x in d}, {"Első rész", "Első lépések"})

    def test_tobb_szo_es_ut_is_szamit(self):
        d = self.ix.fejezetek_mind("masik elso")["fejezetek"]
        self.assertEqual([(x["ut"], x["szoveg"]) for x in d], [("Másik.md", "Első lépések")])

    def test_fejezet_kezdetu_talalat_elol_es_limit(self):
        d = self.ix.fejezetek_mind("rész", 1)["fejezetek"]
        self.assertEqual(len(d), 1)
        d = self.ix.fejezetek_mind("lépések")["fejezetek"]
        self.assertEqual(d[0]["szoveg"], "Első lépések")


class FeloldatlanTest(IndexAlap):
    def test_gyakoriság_szerint_beagyazas_nelkul(self):
        d = self.ix.feloldatlan_szovegek()["szovegek"]
        celok = {x["cel"]: x["db"] for x in d}
        self.assertEqual(celok["Még nincs"], 3)
        self.assertEqual(celok["Másik hiányzó"], 1)
        self.assertNotIn("kép nélkül.png", celok)
        self.assertNotIn("Cél", celok)
        self.assertEqual(d[0]["cel"], "Még nincs")

    def test_limit(self):
        self.assertEqual(len(self.ix.feloldatlan_szovegek(1)["szovegek"]), 1)


class KimenoEmlitesTest(IndexAlap):
    def test_a_szovegben_emlitett_jegyzetek_csoportositva(self):
        motor = Emlitesek(self.cfg, self.ix)
        d = self.ix.kimeno_emlitesek("Emlito.md", motor)
        celok = {f["ut"]: f["talalatok"] for f in d["forrasok"]}
        self.assertIn("Cél X.md", celok)
        t = celok["Cél X.md"][0]
        self.assertEqual((t["sor"], t["emlitett"]), (1, "Cél X"))
        sor = "Ma a Cél X jegyzetről és a célpont aliasról szólok. Linkelt: [[Cél]]."
        self.assertEqual(t["szoveg"], sor)
        self.assertEqual(sor[t["oszlop"]:t["oszlop"] + t["hossz"]], "Cél X")
        self.assertNotIn("Cél.md", celok)             # a már belinkelt cél kimarad
        self.assertNotIn("Emlito.md", celok)          # a jegyzet saját magát nem javasolja

    def test_nem_jegyzetre_ures(self):
        motor = Emlitesek(self.cfg, self.ix)
        self.assertEqual(self.ix.kimeno_emlitesek("kep.png", motor)["forrasok"], [])


class BeallitasTest(unittest.TestCase):
    def test_uj_ertekek_ervenyesek(self):
        b.ellenoriz({"fajlok": {"link_formatum": "abszolut"}})
        b.ellenoriz({"fajlok": {"wikilinkek": False}})
        b.ellenoriz({"fajlok": {"wikilinkek": True, "link_formatum": "relativ"}})

    def test_hibas_ertekek_elutasitva(self):
        for rossz in ({"link_formatum": "teljes"}, {"wikilinkek": "nem"}, {"wikilinkek": 1}):
            with self.subTest(rossz=rossz), self.assertRaises(HttpError):
                b.ellenoriz({"fajlok": rossz})

    def test_alapertelmezett(self):
        self.assertIs(b.ALAP["fajlok"]["wikilinkek"], True)
        self.assertEqual(b.ALAP["fajlok"]["link_formatum"], "rovid")


class AtnevezesAlap(unittest.TestCase):
    FAJLOK: dict = {}

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        for rp, t in self.FAJLOK.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.A = atnevezes.Atnevezes(self.cfg, vaultio.Vault(self.cfg), self.ix, busy=lambda: False, publish=lambda e, **k: None)

    def olvas(self, rp):
        return (self.v / rp).read_bytes().decode("utf-8")

    def nevez(self, ut, uj):
        t = self.A.terv(ut, uj)
        self.assertTrue(t["ok"], t["blokkolok"])
        return self.A.vegrehajt(ut, uj, t["terv_hash"])


class RelativAtnevezesTest(AtnevezesAlap):
    FAJLOK = {
        "Mappa/Régi.md": "# Régi\n",
        "Mappa/Forrás.md": "[[./Régi]] [[../Mappa/Régi]] [r](./Régi.md) [s](../Mappa/Régi%20.md) [[Régi]]\n",
        "Gyökér.md": "[[Mappa/Régi]] [[Régi|alias]] [[Régi#Fej]]\n",
        "Más/Hivo.md": "[[../Mappa/Régi]] [[../Mappa/Régi#Fej|x]]\n",
        "Mélyebb/Alsó/Elem.md": "# Elem\n",
    }

    def test_csak_a_nev_valtozik_a_relativ_ut_megmarad(self):
        self.nevez("Mappa/Régi.md", "Mappa/Új név.md")
        self.assertEqual(self.olvas("Mappa/Forrás.md"),
                         "[[./Új név]] [[../Mappa/Új név]] [r](./Új%20név.md) [s](../Mappa/Régi%20.md) [[Új név]]\n")
        self.assertEqual(self.olvas("Más/Hivo.md"), "[[../Mappa/Új név]] [[../Mappa/Új név#Fej|x]]\n")
        self.assertEqual(self.olvas("Gyökér.md"), "[[Mappa/Új név]] [[Új név|alias]] [[Új név#Fej]]\n")

    def test_athelyezes_relativ_marad_relativ(self):
        self.nevez("Mappa/Régi.md", "Más/Régi.md")
        self.assertEqual(self.olvas("Mappa/Forrás.md").split(" [r]")[0], "[[../Más/Régi]] [[../Más/Régi]]")
        self.assertEqual(self.olvas("Más/Hivo.md"), "[[./Régi]] [[./Régi#Fej|x]]\n")
        self.assertIn("[r](../Más/Régi.md)", self.olvas("Mappa/Forrás.md"))

    def test_a_forras_athelyezese_relativ_linket_ujraszamol(self):
        self.nevez("Mappa/Forrás.md", "Mélyebb/Alsó/Forrás.md")
        szoveg = self.olvas("Mélyebb/Alsó/Forrás.md")
        self.assertTrue(szoveg.startswith("[[../../Mappa/Régi]] [[../../Mappa/Régi]] [r](../../Mappa/Régi.md)"), szoveg)
        for cel in feloldas.jegyzet_celok(szoveg)[:2]:
            self.assertEqual(Feloldo(["Mappa/Régi.md", "Mélyebb/Alsó/Forrás.md"]).resolve(cel, "Mélyebb/Alsó/Forrás.md")[0], "Mappa/Régi.md")


class TeljesUtAtnevezesTest(AtnevezesAlap):
    FAJLOK = {
        "A/B/Cél.md": "# Cél\n",
        "Cél.md": "# Másik\n",
        "Hivo.md": "[[A/B/Cél]] [[A/B/Cél.md]] [[/A/B/Cél]] [[B/Cél]]\n",
        "X/Y/Z/Elem.md": "# Elem\n",
        "C/Elem.md": "# Elem\n",
    }

    def test_teljes_ut_teljes_ut_marad_mélyebb_mappaba_is(self):
        self.nevez("A/B/Cél.md", "X/Y/Z/Cél.md")
        self.assertEqual(self.olvas("Hivo.md"), "[[X/Y/Z/Cél]] [[X/Y/Z/Cél.md]] [[/X/Y/Z/Cél]] [[Z/Cél]]\n")


class PercentAtnevezesTest(AtnevezesAlap):
    FAJLOK = {
        "100%25 kész.md": "# a\n",
        "Hivo.md": "[a](100%2525%20k%C3%A9sz.md) [[100%25 kész]]\n",
    }

    def test_a_fajlnevben_allo_szazalekjel_kodolt_marad(self):
        self.assertEqual(feloldas.md_cel("100%2525%20k%C3%A9sz.md"), "100%25 kész.md")
        self.nevez("100%25 kész.md", "50%25 kész.md")
        szoveg = self.olvas("Hivo.md")
        self.assertEqual(szoveg, "[a](50%2525%20kész.md) [[50%25 kész]]\n")
        self.assertEqual(feloldas.jegyzet_celok(szoveg), ["50%25 kész", "50%25 kész.md"])
        self.assertEqual(feloldas.md_cel("50%2525%20kész.md"), "50%25 kész.md")


if __name__ == "__main__":
    unittest.main()
