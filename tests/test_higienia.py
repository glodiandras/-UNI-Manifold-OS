"""A jegyzethigiénia-riport (C30a): tételfajtánként álvaulton, modell és vault-írás nélkül."""
import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from core import higienia
from core.tulajdonsagok import Tulajdonsagok
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit

KERET = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"      # séma-konform frontmatter


def jo(szoveg: str = "") -> str:
    return KERET + szoveg


def vaultbajtok(gyoker) -> dict:
    ki = {}
    for ut, _, fajlok in os.walk(gyoker):
        for f in fajlok:
            p = os.path.join(ut, f)
            with open(p, "rb") as fh:
                ki[p] = hashlib.sha1(fh.read()).hexdigest()
    return ki


class HigieniaAlap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def riport(self, fajlok: dict, ut: str | None = None, beall: dict | None = None) -> dict:
        self._n = getattr(self, "_n", 0) + 1            # egy teszt több álvaultot is kérhet: mindegyik saját mappában
        mappa = os.path.join(self._t.name, f"v{self._n}")
        os.makedirs(mappa)
        cfg, self.v = alvault(mappa, fajlok)
        if beall:
            cfg.data.setdefault("asszisztens", {}).update(beall)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        self.ix = ix
        self.h = higienia.Higienia(cfg, ix, Tulajdonsagok(cfg, ix))
        return self.h.riport(ut)

    @staticmethod
    def fajta(r: dict, fajta: str, ut: str | None = None) -> list[dict]:
        return [t for t in r["tetelek"] if t["fajta"] == fajta and (ut is None or t["ut"] == ut)]


class FajtaTest(HigieniaAlap):
    def test_torott_link(self):
        r = self.riport({"A.md": jo("[[Nincs ilyen]] és [[B]]\n"), "B.md": jo("[[A]]\n")})
        t = self.fajta(r, "torott_link")
        self.assertEqual([(x["ut"], x["sor"]) for x in t], [("A.md", 9)])
        self.assertIn("Nincs ilyen", t[0]["uzenet"])
        self.assertEqual(self.fajta(r, "tobbertelmu_link"), [])

    def test_kodban_allo_link_nem_tetel(self):
        """Az Obsidian viselkedése (13. döntés): a kódban álló `[[…]]` nem link."""
        r = self.riport({"A.md": jo("`[[Nincs]]`\n```\n[[Nincs2]]\n```\n[[B]]\n"), "B.md": jo("[[A]]\n")})
        self.assertEqual(self.fajta(r, "torott_link"), [])

    def test_tobbertelmu_link(self):
        r = self.riport({"A/Jegyzet.md": jo("a\n"), "B/Jegyzet.md": jo("b\n"), "C.md": jo("[[Jegyzet]] [[A/Jegyzet]]\n")})
        t = self.fajta(r, "tobbertelmu_link")
        self.assertEqual([x["ut"] for x in t], ["C.md"])
        self.assertEqual(t[0]["reszlet"]["cel_nyers"], "Jegyzet")
        self.assertIn(t[0]["reszlet"]["jelolt"], ("A/Jegyzet.md", "B/Jegyzet.md"))

    def test_arva_jegyzet(self):
        r = self.riport({"Arva.md": jo("semmi\n"), "A.md": jo("[[B]]\n"), "B.md": jo("x\n"),
                         "Kimeno.md": jo("[[A]]\n"), "Csak kimeno törött.md": jo("[[Nincs]]\n")})
        arvak = sorted(x["ut"] for x in self.fajta(r, "arva_jegyzet"))
        # Az árva: nincs bejövő és nincs kimenő feloldott link (az Obsidian fogalma). A kimenő link nem teszi árvává a
        # bejövő nélküli jegyzetet, ha feloldott; a csak törött kimenő linkes jegyzet árva marad.
        self.assertEqual(arvak, ["Arva.md", "Csak kimeno törött.md"])

    def test_arva_a_canvas_linkjevel_nem_arva_ha_a_beallitas_igy_kerti(self):
        r = self.riport({"Arva.md": jo("x\n"), "V.canvas": '{"nodes":[{"id":"1","type":"file","file":"Arva.md"}],"edges":[]}'},
                        beall={"higienia_arva_canvas": True})
        self.assertEqual(self.fajta(r, "arva_jegyzet"), [])

    def test_hibas_keplet(self):
        r = self.riport({"A.md": jo("jó $x^2$ és rossz $\\frac{a}{b$ és $\\left( x$ és $$\\begin{aligned} a$$ és $\\{x\\}$\n"
                                    "[[A]]\n")})
        t = self.fajta(r, "hibas_keplet")
        self.assertEqual(len(t), 3)
        self.assertTrue(all(x["ut"] == "A.md" for x in t))

    def test_keplet_proba_egysegek(self):
        p = higienia.kepletproba
        self.assertIsNone(p("x^2 + \\frac{a}{b}"))
        self.assertIsNone(p("\\{ a \\} \\\\ b"))
        self.assertIsNone(p("\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}"))
        self.assertIsNone(p("\\left( x \\right)"))
        self.assertIsNotNone(p("\\frac{a}{b"))
        self.assertIsNotNone(p("a}"))
        self.assertIsNotNone(p("\\left( x"))
        self.assertIsNotNone(p("\\begin{a} x \\end{b}"))
        self.assertIsNotNone(p("\\begin{a} x"))
        self.assertIsNotNone(p("   "))

    def test_hibas_frontmatter(self):
        r = self.riport({"A.md": "---\nTags: [a\nStatus: x: y\n---\nszöveg [[A]]\n"})
        t = self.fajta(r, "hibas_frontmatter", "A.md")
        self.assertEqual(len(t), 1)
        self.assertTrue(t[0]["reszlet"]["hiba"])

    def test_sema_sertes(self):
        r = self.riport({"A.md": "---\nTags:\n  - Ismeretlen\nIsmeretlenKulcs: 1\nStatus: Kész\n---\n[[A]]\n"})
        kodok = {x["reszlet"]["kod"] for x in self.fajta(r, "sema_sertes", "A.md")}
        self.assertTrue({"ismeretlen_kulcs", "mezosorrend"} <= kodok)
        self.assertIn("ertekkeszlet", kodok)     # CX-002: a jegyzet saját értéke önmagát nem legitimálja
        r = self.riport({"A.md": "---\nTags:\n  - Ismeretlen\nIsmeretlenKulcs: 1\nStatus: Kész\n---\n[[A]] [[B]]\n",
                         "B.md": "---\nTags:\n  - Ismeretlen\nStatus: Kész\n---\n[[A]]\n"})
        self.assertNotIn("ertekkeszlet", {x["reszlet"]["kod"] for x in self.fajta(r, "sema_sertes", "A.md")})  # másik jegyzet használja
        self.assertEqual(self.fajta(r, "sema_sertes", "A.md")[0]["reszlet"].keys() >= {"kod", "szint"}, True)

    def test_sema_nelkuli_jegyzet_es_duplikalt_kulcs(self):
        r = self.riport({"Keret nélkül.md": "szöveg [[Keret nélkül]]\n",
                         "Dup.md": "---\nTags:\n  - Mathematics\nTags:\n  - Physics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"})
        self.assertIn("mezosorrend", {x["reszlet"]["kod"] for x in self.fajta(r, "sema_sertes", "Keret nélkül.md")})
        self.assertIn("duplikalt_kulcs", {x["reszlet"]["kod"] for x in self.fajta(r, "sema_sertes", "Dup.md")})

    def test_hianyzo_forrashorgony(self):
        r = self.riport({
            "Tan.pdf": b"%PDF-1.4\n",
            "Nincs.md": KERET.replace("Source:", 'Source: "[[Hiányzik.pdf#page=3]]"') + "[[Nincs]]\n",
            "Rossz oldal.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=0]]"') + "[[Nincs]]\n",
            "Jo.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=3]]"') + "[[Nincs]]\n",
        })
        t = self.fajta(r, "hianyzo_forrashorgony")
        self.assertEqual(sorted(x["ut"] for x in t), ["Nincs.md", "Rossz oldal.md"])
        # nem számít törött linknek is
        self.assertEqual([x["ut"] for x in self.fajta(r, "torott_link") if "Hiányzik" in x["uzenet"]], [])

    def pdf_gyorsitotar(self, ut: str, lapok, **kw):
        """A kinyerő gyorsítótárába írja egy álvault-PDF lapjait (a valódi kulccsal: méret + mtime)."""
        from core.index import pdfszoveg
        st = os.stat(os.path.join(str(self.v), ut))
        g = pdfszoveg.Gyorsitotar(self.ix.db_ut.parent / "pdf-szoveg.sqlite")
        try:
            g.ir(ut, st.st_size, st.st_mtime_ns, lapok=lapok, **kw)
        finally:
            g.close()

    def test_forrashorgony_oldalszam_a_pdf_lapszamabol(self):
        """C30b (K205 (c)): `oldal ≤ oldalszám` — az oldalszám a kinyerő gyorsítótárából jön; ismeretlen oldalszámnál nem ítél."""
        f = {"Tan.pdf": b"%PDF-1.4\n", "Ismeretlen.pdf": b"%PDF-1.4\n", "Csonka.pdf": b"%PDF-1.4\n",
             "Jo.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=3]]"') + "[[Jo]] [[Tan.pdf#page=1]]\n",
             "Tul.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=4]]"') + "[[Tul]] [[Tan.pdf#page=999|szó]]\n",
             "Ismeretlen.md": KERET + "[[Ismeretlen.pdf#page=77]] [[Csonka.pdf#page=77]] [[Ismeretlen]]\n"}
        r = self.riport(f)
        self.assertEqual(self.fajta(r, "hianyzo_forrashorgony"), [])          # nincs gyorsítótár: nincs ítélet
        self.pdf_gyorsitotar("Tan.pdf", ["egy", "kettő", ""])                  # 3 oldal (az utolsó szöveg nélküli: szkennelt)
        self.pdf_gyorsitotar("Csonka.pdf", ["egy"], csonka=True)
        r = self.h.riport()
        t = self.fajta(r, "hianyzo_forrashorgony")
        self.assertEqual(sorted((x["ut"], x["reszlet"]["alcel"]) for x in t),
                         [("Tul.md", "page=4"), ("Tul.md", "page=999")])
        self.assertIn("3 pages", t[0]["uzenet"])
        self.assertIn("Tan.pdf#page=", t[0]["uzenet"])
        # a Source-tulajdonság hibája is jelzi a tulajdonságot; az oldalszámon belüli horgony nem tétel
        self.assertEqual([x["reszlet"].get("tulajdonsag") for x in t if x["reszlet"]["alcel"] == "page=4"], ["Source"])
        # egy jegyzet riportja ugyanazt adja
        self.assertEqual(len(self.fajta(self.h.riport("Tul.md"), "hianyzo_forrashorgony")), 2)
        self.assertEqual(self.fajta(self.h.riport("Jo.md"), "hianyzo_forrashorgony"), [])

    def test_oldalszam_valtozott_pdf_nem_itelet(self):
        """A gyorsítótár kulcsa (méret + mtime): a kinyerés óta változott PDF oldalszáma nem használható."""
        f = {"Tan.pdf": b"%PDF-1.4\n", "A.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=9]]"') + "[[A]]\n"}
        self.riport(f)
        from core.index import pdfszoveg
        st = os.stat(os.path.join(str(self.v), "Tan.pdf"))
        g = pdfszoveg.Gyorsitotar(self.ix.db_ut.parent / "pdf-szoveg.sqlite")
        g.ir("Tan.pdf", st.st_size + 1, st.st_mtime_ns, lapok=["egy"])        # egy korábbi változat kulcsa
        g.close()
        self.assertEqual(self.fajta(self.h.riport(), "hianyzo_forrashorgony"), [])
        self.pdf_gyorsitotar("Tan.pdf", ["egy", "ketto"])                      # a mostani kulcs
        self.assertEqual(len(self.fajta(self.h.riport(), "hianyzo_forrashorgony")), 1)

    def test_oldalszam_hibas_pdf_es_hianyzo_gyorsitotar_nem_itelet(self):
        f = {"Tan.pdf": b"%PDF-1.4\n", "A.md": KERET.replace("Source:", 'Source: "[[Tan.pdf#page=9]]"') + "[[A]]\n"}
        self.riport(f)
        self.pdf_gyorsitotar("Tan.pdf", None, hiba="jelszóval védett PDF")
        self.assertEqual(self.fajta(self.h.riport(), "hianyzo_forrashorgony"), [])
        (self.ix.db_ut.parent / "pdf-szoveg.sqlite").unlink()                  # a gyorsítótár eltűnt: a riport nem hibázik
        for kiegeszites in ("-wal", "-shm"):
            (self.ix.db_ut.parent / f"pdf-szoveg.sqlite{kiegeszites}").unlink(missing_ok=True)
        self.assertEqual(self.fajta(self.h.riport(), "hianyzo_forrashorgony"), [])

    def test_hianyzo_media(self):
        r = self.riport({"kep.png": b"\x89PNG\r\n",
                         "A.md": jo("![[kep.png]] ![[nincs.png]] ![[nincs.mp4|300]] ![[Nincs jegyzet]] [[kep.png]]\n")})
        t = self.fajta(r, "hianyzo_media")
        self.assertEqual(sorted(x["reszlet"]["cel_nyers"] for x in t), ["nincs.mp4", "nincs.png"])
        # a hiányzó jegyzet-beágyazás törött link, nem média
        self.assertEqual(len(self.fajta(r, "torott_link")), 1)

    def test_hibatlan_jegyzet_nulla_tetel(self):
        r = self.riport({"A.md": jo("[[B]] $x$\n"), "B.md": jo("[[A]]\n")})
        self.assertEqual(r["tetelek"], [])
        self.assertEqual(r["osszesites"]["ossz"], 0)


class RiportAlakTest(HigieniaAlap):
    FAJLOK = {"A.md": jo("[[Nincs]]\n"), "B.md": jo("[[Nincs2]]\n[[Nincs3]]\n"), "C.md": jo("[[A]] [[B]]\n")}

    def test_osszesites_es_jegyzetenkent(self):
        r = self.riport(self.FAJLOK)
        self.assertTrue(r["kesz"])
        self.assertEqual(r["osszesites"]["torott_link"], 3)
        self.assertEqual(r["osszesites"]["ossz"], len(r["tetelek"]))
        self.assertEqual(r["osszesites"]["erintett_jegyzet"], 2)
        self.assertEqual(r["jegyzetenkent"], {"A.md": 1, "B.md": 2})
        self.assertEqual(set(higienia.FAJTAK), {
            "torott_link", "tobbertelmu_link", "arva_jegyzet", "hibas_keplet", "hibas_frontmatter", "sema_sertes",
            "hianyzo_forrashorgony", "hianyzo_media"})
        for t in r["tetelek"]:
            self.assertEqual(set(t), {"azonosito", "fajta", "szint", "ut", "sor", "uzenet", "reszlet"})
            self.assertTrue(t["azonosito"].startswith(t["fajta"] + ":"))

    def test_ut_szures(self):
        r = self.riport(self.FAJLOK, "B.md")
        self.assertEqual({t["ut"] for t in r["tetelek"]}, {"B.md"})
        self.assertEqual(r["osszesites"]["torott_link"], 2)
        self.assertEqual(r["osszesites"]["ossz"], 2)

    def test_ismeretlen_ut(self):
        self.riport(self.FAJLOK)
        from core.vaultio import NotFound
        with self.assertRaises(NotFound):
            self.h.riport("nincs.md")

    def test_azonosito_stabil(self):
        a = self.riport(self.FAJLOK)
        id1 = sorted(t["azonosito"] for t in a["tetelek"])
        self.assertEqual(len(set(id1)), len(id1))
        # ugyanaz a riport újra: ugyanazok az azonosítók
        self.assertEqual(sorted(t["azonosito"] for t in self.h.riport()["tetelek"]), id1)

    def test_azonosito_a_sor_eltolodasara_nem_valtozik(self):
        a = self.riport(self.FAJLOK)
        elotte = {t["azonosito"] for t in a["tetelek"] if t["ut"] == "A.md"}
        # a link elé sorok kerülnek, tartalma nem változik
        from tests.helpers import ir
        ir(self.v, "A.md", jo("új sor\nmég egy\n[[Nincs]]\n"))
        self.assertTrue(self.ix.frissit(["A.md"]))
        b = self.h.riport()
        utana = {t["azonosito"] for t in b["tetelek"] if t["ut"] == "A.md"}
        self.assertEqual(elotte, utana)
        sor = [t["sor"] for t in b["tetelek"] if t["ut"] == "A.md"]
        self.assertEqual(sor, [11])

    def test_azonosito_tartalomvaltozasra_valtozik(self):
        a = self.riport(self.FAJLOK)
        elotte = {t["azonosito"] for t in a["tetelek"] if t["ut"] == "A.md"}
        from tests.helpers import ir
        ir(self.v, "A.md", jo("[[Másik nincs]]\n"))
        self.assertTrue(self.ix.frissit(["A.md"]))
        utana = {t["azonosito"] for t in self.h.riport()["tetelek"] if t["ut"] == "A.md"}
        self.assertTrue(elotte.isdisjoint(utana) and utana)

    def test_azonos_link_ketszer_kulon_azonosito(self):
        r = self.riport({"A.md": jo("[[Nincs]] [[Nincs]]\n"), "B.md": jo("[[A]]\n")})
        ids = [t["azonosito"] for t in self.fajta(r, "torott_link")]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_csak_olvas(self):
        cfg, v = alvault(self._t.name, self.FAJLOK)
        elotte = vaultbajtok(self._t.name)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        higienia.Higienia(cfg, ix, Tulajdonsagok(cfg, ix)).riport()
        ix.leallit()
        valtozott = {p for p, h in vaultbajtok(self._t.name).items()
                     if p in elotte and elotte[p] != h and "/Manifold/" in p and "/.obsidian/" not in p}
        self.assertEqual(valtozott, set())


CANVAS = '{"nodes":[{"id":"1","type":"file","file":"Arva.md"}],"edges":[]}'


class ArvaDefinicioTest(HigieniaAlap):
    """C30a: az árva a jegyzet↔jegyzet kapcsolatokra épül; a vault szerkezeti linkjei (`Canvas`, `Source`, a havi
    canvas bejövő linkje) nem számítanak, különben egyetlen jegyzet sem árva."""

    def arvak(self, fajlok, **beall) -> list[str]:
        return sorted(x["ut"] for x in self.fajta(self.riport(fajlok, beall=beall or None), "arva_jegyzet"))

    def test_canvas_es_source_tulajdonsag_alapbol_nem_szamit(self):
        """A `Canvas` és a `Source` frontmatter-link szerkezeti: önmagában nem tesz jegyzetet kapcsolttá (a canvas azon a
        jegyzeten nem szerepel, ezért a canvas-bejövő sem segít)."""
        fm = KERET.replace("Canvas:", 'Canvas: "[[Havi.canvas]]"').replace("Source:", 'Source: "[[Tan.pdf#page=1]]"')
        self.assertEqual(self.arvak({"Arva.md": fm + "szöveg\n", "Havi.canvas": '{"nodes":[],"edges":[]}',
                                     "Tan.pdf": b"%PDF-1.4\n"}), ["Arva.md"])

    def test_canvas_bejovo_alapbol_szamit(self):
        """K176: a canvas-ból érkező link bejövő linknek számít (a valódi vaulton 577 árvából 552 egy tantárgyi canvason
        szerepelt); a beállítás hamisra állításával a régi, szigorú definíció visszaáll."""
        fajlok = {"Arva.md": jo("x\n"), "Havi.canvas": CANVAS}
        self.assertEqual(self.arvak(fajlok), [])
        self.assertEqual(self.arvak(fajlok, higienia_arva_canvas=False), ["Arva.md"])

    def test_az_alapertek_a_configban_es_a_kodban_is_igaz(self):
        import tomllib
        from core.asszisztens import beallitasok
        self.assertIs(beallitasok.ALAP["higienia_arva_canvas"], True)
        with open(Path(__file__).resolve().parent.parent / "config" / "os.toml", "rb") as f:
            self.assertIs(tomllib.load(f)["asszisztens"]["higienia_arva_canvas"], True)

    def test_a_canvasra_sem_mutato_jegyzet_marad_arva(self):
        fajlok = {"Arva.md": jo("x\n"), "Masik.md": jo("y\n"), "Havi.canvas": CANVAS}
        self.assertEqual(self.arvak(fajlok), ["Masik.md"])

    def test_csak_nem_jegyzet_celra_mutato_link_arva(self):
        self.assertEqual(self.arvak({"Kep.md": jo("![[kep.png]] [[Tan.pdf]]\n"), "kep.png": b"\x89PNG\r\n",
                                     "Tan.pdf": b"%PDF-1.4\n"}), ["Kep.md"])

    def test_nn_relacio_szamit_linknek(self):
        a = KERET.replace("NN:", 'NN:\n  - "[[B]]"') + "szöveg\n"
        self.assertEqual(self.arvak({"A.md": a, "B.md": jo("x\n")}), [])

    def test_kizart_utak_nem_arvak(self):
        fajlok = {"X01 - Napló & To-Do/2026-10/Napló/2026-10-04.md": jo("nap\n"), "AI02 - Log/Log.md": jo("l\n"),
                  "_Template/Sablon.md": jo("s\n"), "ATTCHMNTS - cards/Valami — kártyák.md": jo("k\n"),
                  "Matek/Média/Jegyzet.md": jo("m\n"), "Valódi árva.md": jo("v\n")}
        self.assertEqual(self.arvak(fajlok), ["Valódi árva.md"])

    def test_kizart_mappabol_kapott_link_bejovonek_szamit(self):
        fajlok = {"X01 - Napló & To-Do/2026-10/Napló/2026-10-04.md": jo("[[Cél]]\n"), "Cél.md": jo("c\n")}
        self.assertEqual(self.arvak(fajlok), [])

    def test_a_kizart_utak_a_configbol_jonnek(self):
        self.assertEqual(self.arvak({"Egyedi/A.md": jo("a\n"), "B.md": jo("b\n")},
                                    higienia_arva_kizart=["Egyedi/"]), ["B.md"])

    def test_ut_szuro_ugyanazt_adja(self):
        r = self.riport({"A.md": jo("a\n"), "B.md": jo("[[C]]\n"), "C.md": jo("c\n")}, "A.md")
        self.assertEqual([x["ut"] for x in self.fajta(r, "arva_jegyzet")], ["A.md"])


class HorgonyTest(HigieniaAlap):
    """C30a: `#^blokk` és `#Fejezet` horgony a `blokk`/`fejezet` táblák szerint; `page=`/`t=` szintaxis minden linkre."""

    def horgonyok(self, fajlok, ut=None) -> list[tuple[str, str]]:
        return sorted((x["ut"], x["reszlet"]["alcel"]) for x in self.fajta(self.riport(fajlok, ut), "hianyzo_forrashorgony"))

    def test_blokk_horgony(self):
        self.assertEqual(self.horgonyok({"B.md": jo("Mondat. ^m-3f2a\n\nMás sor\n"),
                                         "A.md": jo("[[B#^m-3f2a]] jó, [[B#^m-nincs]] rossz\n[[A]]\n")}),
                         [("A.md", "^m-nincs")])

    def test_fejezet_horgony(self):
        self.assertEqual(self.horgonyok({"B.md": jo("# Fejezet\n## Alfejezet\nszöveg\n"),
                                         "A.md": jo("[[B#Fejezet]] [[B#Nincs fejezet]] [[B#Fejezet#Alfejezet]]\n[[A]]\n")}),
                         [("A.md", "Nincs fejezet")])

    def test_azonos_jegyzet_horgony(self):
        self.assertEqual(self.horgonyok({"A.md": jo("# Cím\n[[#Cím]] [[#Nincs]] ^kod\n[[#^kod]] [[#^hiany]]\n")}),
                         [("A.md", "Nincs"), ("A.md", "^hiany")])

    def test_beagyazott_horgony_is(self):
        self.assertEqual(self.horgonyok({"B.md": jo("# Fejezet\n"), "A.md": jo("![[B#Nincs]] ![[B#Fejezet]]\n")}),
                         [("A.md", "Nincs")])

    def test_oldal_es_ido_szintaxis_minden_linkre(self):
        r = self.horgonyok({
            "Tan.pdf": b"%PDF-1.4\n", "v.mp4": b"\x00",
            "A.md": jo("[[Tan.pdf#page=0]] [[Tan.pdf#page=2]] [[v.mp4#t=abc]] [[v.mp4#t=90]] [[v.mp4#t=1.5]]\n[[A]]\n")})
        self.assertEqual(r, [("A.md", "page=0"), ("A.md", "t=abc")])

    def test_nem_jegyzet_celnal_a_fejezet_nem_ellenorizheto(self):
        self.assertEqual(self.horgonyok({"Tan.pdf": b"%PDF-1.4\n", "A.md": jo("[[Tan.pdf#Valami]]\n[[A]]\n")}), [])

    def test_torott_cel_nem_horgony_hiba(self):
        r = self.riport({"A.md": jo("[[Nincs#^x]]\n")})
        self.assertEqual(self.fajta(r, "hianyzo_forrashorgony"), [])
        self.assertEqual(len(self.fajta(r, "torott_link")), 1)

    def test_ut_szuro_es_azonosito(self):
        fajlok = {"B.md": jo("# F\n"), "A.md": jo("[[B#Nincs]]\n"), "C.md": jo("[[B#Rossz]]\n")}
        r = self.riport(fajlok, "A.md")
        t = self.fajta(r, "hianyzo_forrashorgony")
        self.assertEqual([x["ut"] for x in t], ["A.md"])
        self.assertTrue(t[0]["azonosito"].startswith("hianyzo_forrashorgony:"))


class SzunetPontTest(HigieniaAlap):
    """C30a: a háttérszámítás szünet-pontja: a `kozbe()` a fázisok között és 512 soronként hívódik, kivétele megszakít."""

    FAJLOK = {"A.md": jo(" ".join(f"$x_{i}$" for i in range(1300)) + "\n[[A]]\n")}

    def test_kozbe_fazisonkent_es_soronkent(self):
        self.riport(self.FAJLOK)
        hivasok = []
        self.h.riport(kozbe=lambda: hivasok.append(1))
        self.assertGreaterEqual(len(hivasok), 4 + 2)          # 4 fázis, a 1300 képlet: 512-nél és 1024-nél is

    def test_kozbe_kivetele_megszakitja(self):
        class Megall(Exception):
            pass

        def kozbe():
            raise Megall()
        self.riport(self.FAJLOK)
        with self.assertRaises(Megall):
            self.h.riport(kozbe=kozbe)

    def test_kozbe_nelkul_ugyanaz_a_riport(self):
        a = self.riport(self.FAJLOK)
        self.assertEqual(self.h.riport(kozbe=lambda: None), a)

    def test_kozbe_alatt_nincs_lefoglalt_olvaso_kapcsolat(self):
        """A szünet alatt egyetlen olvasó kapcsolat sincs lefoglalva (a fázisok `fetchall`-lal olvasnak): az indexelő és a
        WAL-ellenőrzőpont nem akad el egy órákig szüneteltetett számításon."""
        import queue
        self.riport(self.FAJLOK)
        while True:                               # üres készlet: ami a `kozbe` alatt visszakerült, azt a riport adta vissza
            try:
                self.ix._pool.get_nowait()[1].close()
            except queue.Empty:
                break
        meretek = []
        self.h.riport(kozbe=lambda: meretek.append(self.ix._pool.qsize()))
        self.assertTrue(meretek and min(meretek) >= 1, meretek)


class CliTest(HigieniaAlap):
    def _fut(self, cfg, *argv):
        import contextlib
        import io
        from unittest import mock
        ki, hiba = io.StringIO(), io.StringIO()
        with mock.patch("core.config.load", return_value=cfg), contextlib.redirect_stdout(ki), \
                contextlib.redirect_stderr(hiba):
            rc = higienia.main(list(argv))
        return rc, ki.getvalue(), hiba.getvalue()

    def test_cli_json_es_szoveg(self):
        import json
        cfg, _ = alvault(self._t.name, {"A.md": jo("[[Nincs]]\n"), "B.md": jo("[[A]]\n")})
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        rc, ki, _ = self._fut(cfg, "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(ki)["osszesites"]["torott_link"], 1)
        rc, ki, _ = self._fut(cfg, "--ut", "A.md")
        self.assertEqual(rc, 0)
        self.assertIn("[torott_link]", ki)
        rc, _, hiba = self._fut(cfg, "--ut", "nincs.md")
        self.assertEqual(rc, 1)
        self.assertIn("nincs ilyen jegyzet", hiba)

    def test_cli_index_nelkul(self):
        cfg, _ = alvault(self._t.name, {"A.md": jo("x\n")})
        rc, _, hiba = self._fut(cfg)
        self.assertEqual(rc, 1)
        self.assertIn("index", hiba)


class AngolTetelTest(HigieniaAlap):
    def test_a_higieniai_uzenetek_angolok_a_fajlok_es_azonositok_valtozatlanok(self):
        r = self.riport({
            "Magyar cím.md": jo("[[Missing target]] és $\\frac{a}{b$\n"),
            "Orphan.md": jo("user content\n"),
            "Frontmatter.md": "---\n- invalid\n---\n# Frontmatter\n",
        })
        elvart = {"torott_link": "Broken link:", "arva_jegyzet": "Orphan note:",
                  "hibas_keplet": "Invalid formula:", "hibas_frontmatter": "Invalid frontmatter syntax:"}
        for fajta, kezdet in elvart.items():
            tetelek = self.fajta(r, fajta)
            self.assertTrue(tetelek, fajta)
            self.assertTrue(all(t["uzenet"].startswith(kezdet) for t in tetelek), tetelek)
        link = self.fajta(r, "torott_link")[0]
        self.assertEqual(link["reszlet"]["cel_nyers"], "Missing target")
        self.assertEqual(link["ut"], "Magyar cím.md")
        keplet = self.fajta(r, "hibas_keplet")[0]
        self.assertIn("Unclosed opening braces", keplet["uzenet"])
        self.assertIn("1", keplet["uzenet"])
        eredeti = vaultbajtok(self.v)
        self.assertEqual([t["azonosito"] for t in self.h.riport()["tetelek"]], [t["azonosito"] for t in r["tetelek"]])
        regi_problemak = self.h.tulajdonsagok.problemak

        def mas_szoveg(*args, **kwargs):
            return [{**p, "uzenet": "Más felületi szöveg"} for p in regi_problemak(*args, **kwargs)]

        with mock.patch.object(higienia, "keplethiba_angol", return_value="Más képletszöveg"), \
                mock.patch.object(higienia, "frontmatter_hiba_angol", return_value="Más YAML-szöveg"), \
                mock.patch.object(self.h.tulajdonsagok, "problemak", side_effect=mas_szoveg):
            mas_nyelv = self.h.riport()
        self.assertEqual([t["azonosito"] for t in mas_nyelv["tetelek"]], [t["azonosito"] for t in r["tetelek"]])
        self.assertEqual(vaultbajtok(self.v), eredeti)

    def test_a_legacy_kepletproba_szovege_megmarad_a_reszlet_angol(self):
        forrasok = ["", "a}", "{a", r"\left( x", r"\end{matrix}", r"\begin{a}\end{b}", r"\begin{aligned}"]
        for forras in forrasok:
            with self.subTest(forras=forras):
                hiba = higienia.kepletproba(forras)
                self.assertIsNotNone(hiba)
                angol = higienia.keplethiba_angol(hiba)
                self.assertNotEqual(angol, hiba)
                self.assertNotEqual(angol, "The formula structure is invalid.")
        self.assertEqual(higienia.kepletproba(""), "üres képlet")
        self.assertIn("aligned", higienia.keplethiba_angol(higienia.kepletproba(r"\begin{aligned}")))


if __name__ == "__main__":
    unittest.main()
