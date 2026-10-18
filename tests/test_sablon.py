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

    def test_ismeretlen_nyelv_angolra_esik_nem_magyarra(self):
        """12-templates-02: az ismeretlen vagy üres nyelv angol, a magyar csak kifejezett kérésre jön."""
        self.assertEqual(self.f("MMMM", nyelv="xx"), "October")
        self.assertEqual(self.f("MMMM", nyelv=""), "October")
        self.assertEqual(self.f("dddd"), "péntek")                  # az `f` segéd alapból hu-t kér: kifejezett kérés
        self.assertEqual(sablon.datum_formatum(NAP, "dddd"), "Friday")   # a függvény alapja angol

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
        self.assertEqual(self.k("{{date:dddd, MMMM Do}}|{{time:HH.mm}}", nyelv="hu").szoveg, "péntek, október 2.|07.05")
        self.assertEqual(self.k("{{date:dddd, MMMM Do}}|{{time:HH.mm}}").szoveg, "Friday, October 2nd|07.05")   # alap: angol

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
        self.assertEqual((b["mappa"], b["datum"], b["ido"]), ("_Template", "YYYY-MM-DD", "HH:mm"))
        self.assertEqual(b["nyelv"], "hu")                           # a `v2-kompat` preset `[sablon] nyelv = "hu"` (a tesztgyökér presetje)


class MomentTokenTest(unittest.TestCase):
    """12-templates-07: a moment.js token-lefedettség (2.30) és a nem támogatott tokenek jelentése."""

    def f(self, fmt, dt=NAP, nyelv="en"):
        return sablon.datum_formatum(dt, fmt, nyelv)

    def test_negyedev_es_sorszamos_tokenek(self):
        self.assertEqual(self.f("Q Qo"), "4 4th")
        self.assertEqual(self.f("Q", datetime(2026, 2, 1)), "1")
        self.assertEqual(self.f("Mo DDDo do", datetime(2026, 3, 1)), "3rd 60th 0th")        # vasárnap: do = 0
        self.assertEqual(self.f("Mo DDDo", datetime(2026, 3, 1), "hu"), "3. 60.")

    def test_hetek_a_nyelv_szabalya_szerint(self):
        # hu = ISO (hétfő, január 4.); en = vasárnap, január 1. a hét 1-ben (moment `en`)
        dec31 = datetime(2026, 12, 31)                                   # csütörtök
        self.assertEqual(self.f("w ww gggg", dec31, "hu"), "53 53 2026")
        self.assertEqual(self.f("w ww gggg", dec31, "en"), "1 01 2027")
        self.assertEqual(self.f("W WW GGGG", dec31, "en"), "53 53 2026")     # ISO mindkét nyelven ugyanaz
        jan3 = datetime(2026, 1, 3)                                      # szombat
        self.assertEqual(self.f("w gggg GG gg", jan3, "hu"), "1 2026 26 26")
        self.assertEqual(self.f("w gggg", jan3, "en"), "1 2026")
        self.assertEqual(self.f("wo Wo", datetime(2026, 1, 20), "en"), "4th 4th")

    def test_periodikus_jegyzet_hetnev(self):
        """A Periodic Notes-stílusú `gggg-[W]ww` nem veszti el a `W` literált és a hetet."""
        self.assertEqual(self.f("gggg-[W]ww"), "2026-W40")

    def test_het_napja_a_nyelv_szerint(self):
        vasarnap = datetime(2026, 10, 4)
        self.assertEqual(self.f("e E", vasarnap, "en"), "0 7")
        self.assertEqual(self.f("e E", vasarnap, "hu"), "6 7")
        self.assertEqual(self.f("e", datetime(2026, 10, 5), "hu"), "0")  # hétfő

    def test_ev_tokenek(self):
        self.assertEqual(self.f("Y YYYYY YYYYYY"), "2026 02026 +002026")

    def test_kk_es_tortmasodperc(self):
        self.assertEqual(self.f("kk k", datetime(2026, 1, 1, 0, 5)), "24 24")
        self.assertEqual(self.f("k", datetime(2026, 1, 1, 7, 5)), "7")
        mikro = datetime(2026, 1, 1, 7, 5, 9, 123456)
        self.assertEqual(self.f("S SS SSS SSSSSS SSSSSSSSS", mikro), "1 12 123 123456 123456000")

    def test_idozona_es_unix(self):
        from datetime import timedelta, timezone
        dt = datetime(2026, 10, 2, 7, 5, 9, tzinfo=timezone(timedelta(hours=-3, minutes=-30)))
        self.assertEqual(self.f("Z ZZ", dt), "-03:30 -0330")
        self.assertEqual(self.f("X x", dt), f"{int(dt.timestamp())} {int(dt.timestamp() * 1000)}")
        self.assertEqual(self.f("Z", datetime(2026, 10, 2, tzinfo=timezone.utc)), "+00:00")

    def test_lokalizalt_formatumok(self):
        dt = datetime(2026, 10, 2, 17, 5)
        self.assertEqual(self.f("LT|LTS|L|LL", dt), "5:05 PM|5:05:00 PM|10/02/2026|October 2, 2026")
        self.assertEqual(self.f("LLL", dt), "October 2, 2026 5:05 PM")
        self.assertEqual(self.f("LLLL", dt), "Friday, October 2, 2026 5:05 PM")
        self.assertEqual(self.f("l|ll", dt), "10/2/2026|Oct 2, 2026")
        self.assertEqual(self.f("LT|L|LL", dt, "hu"), "17:05|2026.10.02.|2026. október 2.")
        self.assertEqual(self.f("LLLL", dt, "hu"), "2026. október 2., péntek 17:05")

    def test_escape_a_lokalizalt_tokenre_is(self):
        self.assertEqual(self.f("[LT] LT", datetime(2026, 1, 1, 9, 0)), "LT 9:00 AM")
        self.assertEqual(self.f("\\Y\\Q YYYY"), "YQ 2026")

    def test_nem_tamogatott_tokenek_jelentese(self):
        self.assertEqual(sablon.ismeretlen_tokenek("YYYY-MM-DD"), [])
        self.assertEqual(sablon.ismeretlen_tokenek("YYYY z zz [z] N yo"), ["z", "zz", "N", "yo"])
        self.assertEqual(sablon.ismeretlen_tokenek("[Napló] gggg-[W]ww"), [])
        self.assertEqual(self.f("z N"), "z N")                          # szó szerint megy át (a Beállítások előnézete jelzi)


class TartalmiNyelvTest(unittest.TestCase):
    """12-templates-02: a hónap-/napnevek nyelve a tartalmi nyelvből jön, alapból angol (nem magyar)."""

    def setUp(self):
        from tests.vaultgyar import alg_semleges
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)      # preset nélkül: a szállított semleges alapok

    def nyelvek(self, sablon_nyelv=None, munkater_nyelv=None):
        if sablon_nyelv is not None:
            self.cfg.data.setdefault("sablon", {})["nyelv"] = sablon_nyelv
        if munkater_nyelv is not None:
            self.cfg.data.setdefault("workspace", {})["nyelv"] = munkater_nyelv
        return sablon.beallitasok(self.cfg)["nyelv"]

    def test_a_szallitott_alap_angol(self):
        self.assertEqual(self.cfg.section("sablon").get("nyelv"), "")           # a szállított os.toml nem ír magyart
        self.assertEqual(sablon.beallitasok(self.cfg)["nyelv"], "en")

    def test_a_munkater_nyelve_szerint(self):
        self.assertEqual(self.nyelvek(munkater_nyelv="hu"), "hu")
        self.assertEqual(self.nyelvek(munkater_nyelv="en"), "en")

    def test_a_kifejezett_sablon_nyelv_nyer(self):
        self.assertEqual(self.nyelvek(sablon_nyelv="hu", munkater_nyelv="en"), "hu")
        self.assertEqual(self.nyelvek(sablon_nyelv="en", munkater_nyelv="hu"), "en")

    def test_az_auto_ures_ertek_nem_esik_magyarra(self):
        """A Beállítások „Automatic” nyelve `""`-t ír a `[sablon] nyelv` és a `[workspace] nyelv` kulcsba."""
        self.assertEqual(self.nyelvek(sablon_nyelv="", munkater_nyelv=""), "en")

    def test_ismeretlen_nyelv_angol(self):
        self.assertEqual(self.nyelvek(sablon_nyelv="de", munkater_nyelv="fr"), "en")

    def test_a_napi_jegyzet_utja_es_a_beszuras_az_angol_neveket_adja(self):
        from datetime import date
        from core import naplo
        self.cfg.data.setdefault("naplo", {})["ut"] = "YYYY/MMMM/YYYY-MMM-DD"
        self.assertEqual(naplo.napi_ut(self.cfg, date(2026, 10, 17)), "2026/October/2026-Oct-17.md")
        b = sablon.beallitasok(self.cfg)
        e = sablon.kiertekel("{{date:dddd, MMMM Do}}", "x", datetime(2026, 10, 17, 9, 0), nyelv=b["nyelv"])
        self.assertEqual(e.szoveg, "Saturday, October 17th")

    def test_magyar_munkater_magyar_neveket_ad(self):
        from datetime import date
        from core import naplo
        self.nyelvek(munkater_nyelv="hu")
        self.cfg.data.setdefault("naplo", {})["ut"] = "YYYY/MMMM/YYYY-MMM-DD"
        self.assertEqual(naplo.napi_ut(self.cfg, date(2026, 10, 17)), "2026/október/2026-okt.-17.md")


class MostSzovegTest(unittest.TestCase):
    """12-templates-03 / 06: a mostani dátum / idő a beállított formátummal (az „Insert current date / time” parancsok és az előnézet)."""

    def setUp(self):
        from tests.vaultgyar import alg_semleges
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)
        self.V = vaultio.Vault(self.cfg)

    def test_alap_formatumok(self):
        self.assertEqual(sablon.most_szoveg(self.V, "date", most=NAP), {"szoveg": "2026-10-02", "formatum": "YYYY-MM-DD", "ismeretlen": []})
        self.assertEqual(sablon.most_szoveg(self.V, "time", most=NAP)["szoveg"], "07:05")

    def test_a_beallitott_formatum_es_nyelv(self):
        self.cfg.data["sablon"]["datum"] = "dddd, D MMMM YYYY"
        self.cfg.data["sablon"]["ido"] = "h:mm A"
        self.assertEqual(sablon.most_szoveg(self.V, "date", most=NAP)["szoveg"], "Friday, 2 October 2026")
        self.assertEqual(sablon.most_szoveg(self.V, "time", most=ESTE)["szoveg"], "5:45 PM")
        self.cfg.data["sablon"]["nyelv"] = "hu"
        self.assertEqual(sablon.most_szoveg(self.V, "date", most=NAP)["szoveg"], "péntek, 2 október 2026")

    def test_kifejezett_formatum_az_elonezethez_es_a_nem_tamogatott_jelentese(self):
        r = sablon.most_szoveg(self.V, "date", "YYYY/[Q]Q z", NAP)
        self.assertEqual((r["szoveg"], r["formatum"], r["ismeretlen"]), ("2026/Q4 z", "YYYY/[Q]Q z", ["z"]))
        self.assertEqual(sablon.most_szoveg(self.V, "date", "   ", NAP)["formatum"], "YYYY-MM-DD")      # üres: a beállított

    def test_hibas_kerdes_400(self):
        for fajta, fmt in (("nap", None), (None, None), ("date", 5), ("date", "x" * 201)):
            with self.assertRaises(sablon.SablonHiba, msg=str((fajta, fmt))) as e:
                sablon.most_szoveg(self.V, fajta, fmt, NAP)
            self.assertEqual(e.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
