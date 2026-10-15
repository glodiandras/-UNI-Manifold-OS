"""A közös kód- és képletmaszk (`core/index/maszk.py`, C10.6; CLAUDE.md 1. / 13. döntés).

Amit ezek a tesztek őriznek: a `~~~` kerítés, a több-backtickes soron belüli kód és a képlet belsejében álló
`[[…]]` nem link; a maszk a hosszt és a sortöréseket megtartja; a frontmatterben nincs maszk; a zárt `[[…]]`
belsejében nem indul kód vagy képlet; és hogy minden fogyasztó (gráf, index, átnevezés, említések) ugyanazt a
link-halmazt látja. A behúzott kód és a HTML-megjegyzés kapcsolója mindkét állásában.
"""
import unittest
from unittest import mock

from core.index import elemzo, feloldas, kereses, linkek, maszk
from core.index.maszk import keritesek, link_maszk, mask_code, maszkok


def celok(t: str) -> list[str]:
    return feloldas.jegyzet_celok(t)


class AlakTest(unittest.TestCase):
    SZOVEGEK = [
        "",
        "sima [[A]] szöveg",
        "---\nK: \"[[P]]\"\n---\n`[[K]]` $[[1,2]]$ [[A]]\n~~~\n[[T]]\n~~~\n",
        "```\nlezáratlan [[X]]\n\n$$\n",
        "a `` b ` c `` d $$\nx\n$$ e\n> ```\n> [[Q]]\n> ```\n",
        "\\` [[A]] \\$ `x` $y$",
    ]

    def test_a_hossz_es_a_sortoresek_megmaradnak(self):
        for t in self.SZOVEGEK:
            for m in maszkok(t):
                self.assertEqual(len(m), len(t), t)
                self.assertEqual([i for i, c in enumerate(m) if c == "\n"], [i for i, c in enumerate(t) if c == "\n"], t)
                self.assertTrue(all(a == b or a == " " for a, b in zip(m, t)), t)

    def test_a_ket_maszk_egy_menetbol_jon(self):
        for t in self.SZOVEGEK:
            kod, link = maszkok(t)
            self.assertEqual((mask_code(t), link_maszk(t)), (kod, link))
            self.assertTrue(all(b == a or b == " " for a, b in zip(kod, link)), t)     # a link-maszk szigorúbb


class KeritesTest(unittest.TestCase):
    def test_backtick_es_tilde(self):
        self.assertEqual(celok("```\n[[A]]\n```\n[[B]]\n~~~\n[[C]]\n~~~\n[[D]]"), ["B", "D"])
        self.assertEqual(celok("~~~python title\n[[A]]\n~~~\n[[B]]"), ["B"])

    def test_a_zaro_legalabb_olyan_hosszu_es_ugyanaz_a_jel(self):
        self.assertEqual(celok("````\n[[A]]\n```\n[[B]]\n````\n[[C]]"), ["C"])
        self.assertEqual(celok("```\n[[A]]\n~~~\n[[B]]\n```\n[[C]]"), ["C"])
        self.assertEqual(celok("~~~\n[[A]]\n~~~~~\n[[B]]"), ["B"])
        self.assertEqual(celok("```\n[[A]]\n``` nem záró\n[[B]]\n```\n[[C]]"), ["C"])

    def test_lezaratlan_kerites_a_szoveg_vegeig(self):
        self.assertEqual(celok("[[A]]\n```\n[[B]]\n\n[[C]]"), ["A"])

    def test_idezetben_es_listaban(self):
        self.assertEqual(celok("> [!note]\n> ```\n> [[A]]\n> ```\n> [[B]]"), ["B"])
        self.assertEqual(celok("> ```\n> [[A]]\n[[B]]"), ["B"])                    # az idézet vége lezárja
        self.assertEqual(celok("- elem\n  ```\n  [[A]]\n  ```\n  [[B]]"), ["B"])
        self.assertEqual(celok("- ```\n  [[A]]\n  ```\n- [[B]]"), ["B"])

    def test_backtickes_info_nem_kerites(self):
        self.assertEqual(celok("```a``` [[A]]\n[[B]]\n```\n[[C]]\n```"), ["A", "B"])
        self.assertEqual(celok("~~~a~~~ b\n[[A]]\n~~~\n[[B]]"), ["B"])            # a tilde infójában lehet tilde

    def test_keritesek_helye_es_infoja(self):
        t = "a\n```py\nx\n```\nb\n~~~ plot extra\ny\n"
        self.assertEqual(keritesek(t), [(2, 13, "py"), (16, len(t), "plot extra")])
        self.assertEqual(t[2:13], "```py\nx\n```")

    def test_a_soron_beluli_harmas_nem_nyit_blokkot(self):
        self.assertEqual(celok("a ``` b\n\n[[A]]\n\n```\n[[B]]\n```\n"), ["A"])


class SoronBeluliKodTest(unittest.TestCase):
    def test_futamok(self):
        self.assertEqual(celok("`[[A]]` [[B]]"), ["B"])
        self.assertEqual(celok("``[[A]]`` [[B]]"), ["B"])
        self.assertEqual(celok("``[[A]] ` `` [[B]]"), ["B"])                      # az egyes backtick nem zár
        self.assertEqual(celok("`` ` `` [[A]] `` ` ``"), ["A"])
        self.assertEqual(celok("```[[A]]``` [[B]] szöveg"), ["B"])
        self.assertEqual(celok("`a``b` [[A]] ``c`d``"), ["A"])

    def test_paratlan_backtick_nem_takar(self):
        self.assertEqual(celok("a ` b [[A]]"), ["A"])
        self.assertEqual(celok("a `` b ` [[A]]"), ["A"])

    def test_tobb_soron_at_a_bekezdesen_belul(self):
        self.assertEqual(celok("`kód\n[[A]] vége` [[B]]"), ["B"])
        self.assertEqual(celok("`kód\n\n[[A]] vége`"), ["A"])                     # üres soron nem megy át
        self.assertEqual(celok("- egy `\n- [[A]] ` kettő"), ["A"])                # új listaelemen sem
        self.assertEqual(celok("szöveg `\n# [[A]] `"), ["A"])                     # fejezeten sem
        self.assertEqual(celok("| a ` |\n| [[A]] ` |"), ["A"])                    # táblázatsoron sem

    def test_escape(self):
        self.assertEqual(celok("\\`[[A]]\\` [[B]]"), ["A", "B"])
        self.assertEqual(celok("`a\\` [[A]] `b`"), ["A"])                         # a kódon belül a `\\` betű szerinti


class KepletTest(unittest.TestCase):
    def test_soron_beluli_es_blokk(self):
        self.assertEqual(celok("$[[1,2],[3,4]]$ [[A]]"), ["A"])
        self.assertEqual(celok("$$\n[[1,2]]\n$$\n[[A]]"), ["A"])
        self.assertEqual(celok("szöveg $$[[x]]$$ [[A]]"), ["A"])
        self.assertEqual(celok("$a$ [[A]] $b$"), ["A"])

    def test_ami_nem_keplet(self):
        self.assertEqual(celok("5$ [[A]] és 6$"), ["A"])                          # a nyitó után szóköz
        self.assertEqual(celok("$a [[A]] $5"), ["A"])                             # a záró után számjegy
        self.assertEqual(celok("\\$ [[A]] \\$"), ["A"])
        self.assertEqual(celok("$x\n[[A]]$"), ["A"])                              # a `$…$` egysoros

    def test_ami_elobb_nyit_az_nyer(self):
        self.assertEqual(celok("`$` [[A]] `$`"), ["A"])                           # a kódban álló `$` nem képlet
        self.assertEqual(celok("$a`b$ [[A]] `c`"), ["A"])                         # a képletben álló backtick nem kód
        self.assertEqual(celok("```\n$\n```\n[[A]] $x$"), ["A"])

    def test_a_kodmaszk_a_kepletet_nem_takarja(self):
        t = "$[[1,2]]$ és `kód`"
        self.assertEqual(mask_code(t), "$[[1,2]]$ és      ")
        self.assertEqual(link_maszk(t), "          és      ")
        j = elemzo.elemez(t)
        self.assertEqual([k["forras"] for k in j.kepletek], ["[[1,2]]"])          # a képlet-tábla változatlan
        self.assertEqual(j.linkek, [])


class WikilinkVedelemTest(unittest.TestCase):
    def test_a_zart_wikilinkben_nem_indul_keplet_vagy_kod(self):
        self.assertEqual(celok("[[Ár $-ban]] és [[Másik $ jegyzet]]"), ["Ár $-ban", "Másik $ jegyzet"])
        self.assertEqual(celok("[[a `b` c]]"), ["a `b` c"])
        self.assertEqual(celok("[[jegyzet $x$]] $[[y]]$"), ["jegyzet $x$"])
        self.assertEqual(celok("![[kep $1$.png|300]] `[[K]]`"), ["kep $1$.png"])

    def test_az_ures_es_a_lezaratlan_link_nem_ved(self):
        self.assertEqual(celok("[[]] `[[K]]` [[A]]"), ["", "A"])
        self.assertEqual(celok("[[nyitott `[[K` szöveg"), ["nyitott       szöveg"])   # a kódban álló `[[K` nem link
        # az első `]]`-ig tart a link (a szerkesztő elemzője is így látja): a belsejében álló backtick nem kód
        self.assertEqual(celok("[[nyitott `[[K]]` szöveg"), ["nyitott `[[K"])


class FrontmatterTest(unittest.TestCase):
    def test_a_frontmatterben_nincs_maszk(self):
        t = "---\nSource: \"[[doc.pdf#page=3]]\"\nK: \"`[[A]]` $[[B]]$\"\n---\n`[[C]]` [[D]]\n"
        self.assertEqual(celok(t), ["doc.pdf", "A", "B", "D"])
        self.assertTrue(link_maszk(t).startswith(t[:t.index("`[[C")]))

    def test_a_kerites_a_torzsben_indul(self):
        self.assertEqual(celok("---\nK: \"```\"\n---\n[[A]]\n```\n[[B]]\n```\n"), ["A"])

    def test_canvas_szovegben_nincs_frontmatter(self):
        t = "---\n`[[A]]`\n---\n[[B]]"
        self.assertEqual([m.group(1) for m in feloldas.canvas_wiki(t)], ["B"])
        self.assertEqual(feloldas.canvas_celok({"nodes": [{"text": "$[[1,2]]$ ~~~ [[C]]"}]}), ["C"])


class EgyMaszkMindenholTest(unittest.TestCase):
    """A 3. pont: az index, a gráf, az átnevezés és az említések ugyanazt a maszkot használják."""

    T = ("---\nNN: \"[[P]]\"\n---\n[[A]] `[[K1]]` ``[[K2]] ` `` $[[1,2],[3,4]]$ [[B|x]] [md](C.md)\n"
         "~~~\n[[K3]] [md](K4.md)\n~~~\n$$\n[[K5]]\n$$\n```\n[[K6]]\n```\n![[D.png]] #cimke `#nem` ~~~\n")

    def test_graf_index_es_atnevezes_ugyanazt_latja(self):
        vart = ["P", "A", "B", "D.png", "C.md"]
        self.assertEqual(celok(self.T), vart)
        self.assertEqual([L.cel for L in elemzo.elemez(self.T).linkek], vart)
        self.assertEqual([x.cel for x in linkek.jegyzet_talalatok(self.T)], vart)
        crlf = self.T.replace("\n", "\r\n")
        self.assertEqual([x.cel for x in linkek.jegyzet_talalatok(crlf)], vart)

    def test_canvas_index_es_graf(self):
        adat = {"nodes": [{"id": "1", "text": "[[A]] ``[[K]]`` $[[1,2]]$\n~~~\n[[K2]]\n~~~"}]}
        self.assertEqual(feloldas.canvas_celok(adat), ["A"])
        self.assertEqual([L.cel for L in elemzo.elemez_canvas(adat, None).linkek], ["A"])

    def test_emlitesek(self):
        import re
        t = "Cél itt. `Cél` ``Cél ` `` $Cél$ [[Cél]]\n~~~\nCél\n~~~\n$$\nCél\n$$\nés Cél újra"
        talalat = kereses.emlites_talalatok(t, [re.compile(r"(?<!\w)Cél(?!\w)", re.I)])
        self.assertEqual([(x["sor"], x["oszlop"]) for x in talalat], [(1, 0), (8, 3)])

    def test_cimke_fejezet_feladat_a_tilde_blokkban_nem_szamit(self):
        j = elemzo.elemez("# Cím\n~~~\n# Nem cím\n- [ ] nem feladat #nemcimke\n~~~\n- [ ] feladat #igen ``#nem``\n")
        self.assertEqual([f["szoveg"] for f in j.fejezetek], ["Cím"])
        self.assertEqual([f["sor"] for f in j.feladatok], [6])
        self.assertEqual([c["cimke"] for c in j.cimkek], ["igen"])
        self.assertEqual(j.kodblokkok, [{"nyelv": "", "sor_kezd": 2, "sor_veg": 5}])


class KapcsoloTest(unittest.TestCase):
    """A két nyitott kérdés (a felhasználó Obsidian-próbája dönt): mindkét állás működik."""

    BEHUZOTT = "szöveg\n\n    [[A]]\n\tmég kód [[B]]\n\nbekezdés\n    [[C]] folytatás\n\n- elem\n\n    [[D]] a listaelem része\n\nvége\n\n\t[[E]]\n"
    HTML = "a <!-- [[A]] --> b [[B]]\n<!--\n[[C]]\n-->\n[[D]] <!-- lezáratlan [[E]]\n"

    def test_alapbol_mindketto_link(self):
        self.assertFalse(maszk.BEHUZOTT_KOD)
        self.assertFalse(maszk.HTML_MEGJEGYZES)
        self.assertEqual(celok(self.BEHUZOTT), ["A", "B", "C", "D", "E"])
        self.assertEqual(celok(self.HTML), ["A", "B", "C", "D", "E"])

    def test_behuzott_kod_bekapcsolva(self):
        with mock.patch.object(maszk, "BEHUZOTT_KOD", True):
            self.assertEqual(celok(self.BEHUZOTT), ["C", "D"])                    # a bekezdés és a lista folytatása nem kód
            self.assertEqual(len(mask_code(self.BEHUZOTT)), len(self.BEHUZOTT))

    def test_html_megjegyzes_bekapcsolva(self):
        with mock.patch.object(maszk, "HTML_MEGJEGYZES", True):
            self.assertEqual(celok(self.HTML), ["B", "D", "E"])


if __name__ == "__main__":
    unittest.main()
