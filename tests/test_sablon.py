"""A sablonmotor (C15): változók, formátum-tokenek, `{{cursor}}`, a sablonlista és a végpontok. Álvaulton."""
import unittest
from datetime import datetime

from core import sablon, vaultio
from tests.helpers import alg_core, ir, tmpdir

NAP = datetime(2026, 10, 2, 7, 5, 9)          # péntek, 40. hét
ESTE = datetime(2026, 1, 3, 17, 45, 0)        # szombat


class FormatumTest(unittest.TestCase):
    def f(self, fmt, dt=NAP, nyelv="hu"):
        return sablon.datum_formatum(dt, fmt, nyelv)

    def test_alap_tokenek(self):
        self.assertEqual(self.f("YYYY-MM-DD"), "2026-10-02")
        self.assertEqual(self.f("YY.M.D."), "26.10.2.")
        self.assertEqual(self.f("HH:mm:ss"), "07:05:09")
        self.assertEqual(self.f("H:m:s"), "7:5:9")

    def test_12_oras(self):
        self.assertEqual(self.f("hh:mm A"), "07:05 DE")
        self.assertEqual(self.f("h:mm a", ESTE), "5:45 du")
        self.assertEqual(self.f("h", datetime(2026, 1, 1, 0, 0)), "12")

    def test_magyar_nevek(self):
        self.assertEqual(self.f("YYYY. MMMM D., dddd"), "2026. október 2., péntek")
        self.assertEqual(self.f("MMM ddd dd"), "okt. pén p")
        # T156 (C31): a moment `hu` locale rövid hónapnevei, pont a végükön (az Obsidian 1.14.4 momentje)
        self.assertEqual([self.f("MMM", datetime(2026, h, 1)) for h in range(1, 13)],
                         ["jan.", "feb.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.", "okt.", "nov.", "dec."])
        self.assertEqual(self.f("Do"), "2.")
        self.assertEqual(self.f("dddd", ESTE), "szombat")
        self.assertEqual(self.f("MMMM", ESTE), "január")

    def test_angol_nevek(self):
        self.assertEqual(self.f("dddd, MMMM Do", nyelv="en"), "Friday, October 2nd")
        self.assertEqual(self.f("Do", datetime(2026, 1, 11), "en"), "11th")
        self.assertEqual(self.f("Do", datetime(2026, 1, 23), "en"), "23rd")
        self.assertEqual(self.f("A", nyelv="en"), "AM")

    def test_ismeretlen_nyelv_a_magyarra_esik(self):
        self.assertEqual(self.f("MMMM", nyelv="xx"), "október")

    def test_het_nap_sorszam(self):
        self.assertEqual(self.f("WW"), "40")
        self.assertEqual(self.f("W", datetime(2026, 1, 5)), "2")
        self.assertEqual(self.f("E d"), "5 5")                      # ISO péntek 5; a moment `d`: vasárnap 0
        self.assertEqual(self.f("d", datetime(2026, 10, 4)), "0")   # vasárnap
        self.assertEqual(self.f("DDDD DDD", datetime(2026, 2, 1)), "032 32")

    def test_escape_es_szoveg(self):
        self.assertEqual(self.f("[Napló]/YYYY"), "Napló/2026")      # az `a` és az `l` nem token az escape-ben
        self.assertEqual(self.f("[X01 - Napló & To-Do]/YYYY-MM"), "X01 - Napló & To-Do/2026-10")
        self.assertEqual(self.f("[]"), "")
        self.assertEqual(self.f(""), "")
        self.assertEqual(self.f("ÉÉÉÉ"), "ÉÉÉÉ")                   # ismeretlen betű szó szerint

    def test_a_napi_jegyzet_alap_utja(self):
        self.assertEqual(self.f("[X01 - Napló & To-Do]/YYYY-MM/[Napló]/YYYY-MM-DD"),
                         "X01 - Napló & To-Do/2026-10/Napló/2026-10-02")


class KiertekelTest(unittest.TestCase):
    def k(self, szoveg, cim="Jegyzet", **kw):
        return sablon.kiertekel(szoveg, cim, NAP, **kw)

    def test_alapvaltozok(self):
        e = self.k("{{title}} · {{date}} {{time}}", "2026-10-02")
        self.assertEqual(e.szoveg, "2026-10-02 · 2026-10-02 07:05")
        self.assertIsNone(e.kurzor)

    def test_formatumos_valtozok(self):
        self.assertEqual(self.k("{{date:dddd, MMMM Do}}|{{time:HH.mm}}").szoveg, "péntek, október 2.|07.05")

    def test_szokozok_a_kapcsos_zarojelben(self):
        self.assertEqual(self.k("{{ date : YYYY }}|{{ title }}").szoveg, "2026|Jegyzet")

    def test_valtozonev_kis_nagybetutol_fuggetlen(self):
        """T156 (C31): az Obsidian Templates magja `gi` zászlóval cserél."""
        self.assertEqual(self.k("{{DATE}}|{{Time}}|{{Title}}|{{date:YYYY}}|{{DATE:MM}}").szoveg,
                         "2026-10-02|07:05|Jegyzet|2026|10")
        e = self.k("a{{CURSOR}}b")
        self.assertEqual((e.szoveg, e.kurzor), ("ab", 1))

    def test_ures_formatum_az_alapformatum(self):
        """T156 (C31): `{{date:}}` → az alapformátum (az Obsidian `i ? format(i) : alap`)."""
        self.assertEqual(self.k("{{date:}}|{{time:}}").szoveg, "2026-10-02|07:05")
        self.assertEqual(self.k("{{date:}}", datum="YYYY.MM.DD.").szoveg, "2026.10.02.")

    def test_alap_formatumok_felulirhatok(self):
        self.assertEqual(self.k("{{date}} {{time}}", datum="YYYY.MM.DD.", ido="H:mm").szoveg, "2026.10.02. 7:05")

    def test_ismeretlen_valtozo_marad(self):
        self.assertEqual(self.k("{{valami}} {{title:x}} {{cursor:x}}").szoveg, "{{valami}} {{title:x}} {{cursor:x}}")

    def test_egy_menet_nincs_ujraertekeles(self):
        e = self.k("a {{title}} b", "{{cursor}}{{date}}")
        self.assertEqual(e.szoveg, "a {{cursor}}{{date}} b")
        self.assertIsNone(e.kurzor)

    def test_kurzor_helye(self):
        e = self.k("# Napló\n\n{{cursor}}\n")
        self.assertEqual(e.szoveg, "# Napló\n\n\n")
        self.assertEqual(e.kurzor, len("# Napló\n\n"))

    def test_kurzor_az_elso_es_a_tobbi_kikerul(self):
        e = self.k("a{{cursor}}b{{cursor}}c")
        self.assertEqual((e.szoveg, e.kurzor), ("abc", 1))

    def test_kurzor_utf16_egysegben(self):
        # az ékezetes betű 1, az emoji (😀) 2 UTF-16 egység; a behelyettesített szöveg is számít
        e = self.k("Árvíztűrő 😀 {{title}} {{cursor}}x", "ő😀")
        self.assertEqual(e.szoveg, "Árvíztűrő 😀 ő😀 x")
        self.assertEqual(e.kurzor, len("Árvíztűrő ") + 2 + 1 + len("ő") + 2 + 1)

    def test_kurzor_a_frontmatter_utan(self):
        e = self.k("---\nTags:\n---\n{{cursor}}")
        self.assertEqual(e.kurzor, len("---\nTags:\n---\n"))

    def test_crlf_megmarad(self):
        self.assertEqual(self.k("a\r\n{{title}}\r\n").szoveg, "a\r\nJegyzet\r\n")

    def test_frontmatter_es_torzs(self):
        self.assertTrue(sablon.frontmatter_van("---\nTags:\n---\nszöveg"))
        self.assertFalse(sablon.frontmatter_van("szöveg\n---\nTags:\n---\n"))
        self.assertEqual(sablon.torzs("---\nTags:\n---\nszöveg\n"), "szöveg\n")
        self.assertEqual(sablon.torzs("szöveg"), "szöveg")


class VaultTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "_Template/Zeta.md", "{{title}}")
        ir(self.v, "_Template/Alfa.md", "---\nTags:\n---\n{{date:YYYY}} {{cursor}}")
        ir(self.v, "_Template/Alma/Béta.md", "x")
        ir(self.v, "_Template/.rejtett.md", "rejtett")
        ir(self.v, "_Template/kep.png", b"\x89PNG", "wb")
        ir(self.v, "Más/Nem sablon.md", "nem")
        self.V = vaultio.Vault(self.cfg)

    def test_lista(self):
        l = sablon.lista(self.V)
        self.assertEqual(l["mappa"], "_Template")
        self.assertEqual([s["nev"] for s in l["sablonok"]], ["Alfa", "Béta", "Zeta"])
        self.assertEqual(l["sablonok"][1]["ut"], "_Template/Alma/Béta.md")

    def test_lista_hianyzo_mappa(self):
        self.assertEqual(sablon.lista(vaultio.Vault(self._cfg_mappa("Nincs")))["sablonok"], [])

    def _cfg_mappa(self, mappa):
        from core import config
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.v.parent / "home")})
        cfg.data.setdefault("sablon", {})["mappa"] = mappa
        return cfg

    def test_csak_a_sablonmappabol_olvas(self):
        with self.assertRaises(vaultio.Invalid):
            sablon.olvas(self.V, "Más/Nem sablon.md")
        with self.assertRaises(vaultio.Invalid):
            sablon.olvas(self.V, "_Template/../Más/Nem sablon.md")
        with self.assertRaises(vaultio.Invalid):
            sablon.olvas(self.V, "_Template/kep.png")
        with self.assertRaises(vaultio.NotFound):
            sablon.olvas(self.V, "_Template/Nincs.md")

    def test_kiertekel_vault(self):
        r = sablon.kiertekel_vault(self.V, "_Template/Alfa.md", "Cím", NAP)
        self.assertEqual(r, {"szoveg": "---\nTags:\n---\n2026 ", "kurzor": len("---\nTags:\n---\n2026 "), "frontmatter": True})
        self.assertEqual(sablon.kiertekel_vault(self.V, "_Template/Zeta.md", "Cím", NAP)["szoveg"], "Cím")
        with self.assertRaises(sablon.SablonHiba):
            sablon.kiertekel_vault(self.V, "_Template/Zeta.md", None, NAP)

    def test_beallitasok_alapertekei(self):
        b = sablon.beallitasok(self.cfg)
        self.assertEqual((b["mappa"], b["datum"], b["ido"], b["nyelv"]), ("_Template", "YYYY-MM-DD", "HH:mm", "hu"))


if __name__ == "__main__":
    unittest.main()
