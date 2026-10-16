"""Átnevezés és áthelyezés teljes link-átírással (C10, a legacy I30 szabálya) — álvaulton, ál-`var/`-on.

Amit ezek a tesztek őriznek:
  - minden linkalak helyesen íródik át (alias, `#fejezet`, `#^blokk`, `!`, szóközök, táblázatbeli `\\|`,
    frontmatter, md-link, canvas), a kódban álló link és minden más bájt érintetlen;
  - az *elrabolt* link (áthelyezés után egy azonos alapnevű másik fájl kerülne közelebb) is átíródik;
  - a CRLF, az érvénytelen UTF-8 és az NFD fájlnév bájtra megmarad;
  - egy gépi commit a régi és az új úttal; a visszavonás után minden bájtra az eredeti;
  - hash-eltérés, közben futó írás, hibás lépés vagy bukó referencia-próba: semmi sem változik;
  - a médiát és a hibás kéréseket a terv blokkolja.
"""
import os
import threading
import time
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from core import atnevezes, snapshot, tartos, vaultio
from core.index import feloldas
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

NFD = unicodedata.normalize("NFD", "Ütőér")

ALAP = {
    "Cél.md": "# Cél\n\n## Fejezet\nSzöveg ^b\n",
    "Hivo.md": ("---\nSource: \"[[Cél]]\"\n---\n"
                "A [[Cél]] B [[Cél|alias]] C [[Cél#Fejezet]] D ![[Cél]] E ![[Cél#^b]] F [[ Cél ]] "
                "G `[[Cél]]` H [md](Cél.md)\n"
                "| [[Cél\\|x]] | [[Cél\\#Fejezet\\|y]] |\n"
                "```\n[[Cél]]\n```\n[[Cél]]"),
    "A/Cél.md": "# A-s Cél\n",
    "B/Útvonalas.md": "[[A/Cél]] [[A/Cél.md]] [[/A/Cél]] [[Cél]]\n",
    "Önmaga.md": "# Önmaga\n[[Önmaga]] [[Önmaga#Cím]]\n",
    "Vaszon.canvas": ('{\n\t"nodes": [\n\t\t{"id": "1", "type": "file", "file": "Cél.md", "subpath": "#Fejezet", "x": 0},\n'
                      '\t\t{"id": "2", "type": "text", "text": "[[Cél]] és [[Cél|név]]\\n`[[Cél]]`", "x": 1},\n'
                      '\t\t{"id": "3", "type": "file", "file": "A/Cél.md"}\n\t],\n\t"edges": []\n}\n'),
    "kep.png": b"\x89PNG\r\n",
    "Kep.md": "![[kep.png]]\n",
}


def lenyomat(gyoker):
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = [m for m in mappak if m != ".obsidian"]
        for f in fajlok:
            p = os.path.join(d, f)
            ki[unicodedata.normalize("NFC", os.path.relpath(p, gyoker))] = Path(p).read_bytes()
    return ki


class Alap(unittest.TestCase):
    FAJLOK = ALAP

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
        self.esemenyek = []
        self.busy = False
        self.V = vaultio.Vault(self.cfg)
        self.A = atnevezes.Atnevezes(self.cfg, self.V, self.ix, busy=lambda: self.busy,
                                     publish=lambda e, **k: self.esemenyek.append(e))

    def olvas(self, rp):
        return (self.v / rp).read_bytes().decode("utf-8")

    def nevez(self, ut, uj):
        t = self.A.terv(ut, uj)
        self.assertTrue(t["ok"], t["blokkolok"])
        return self.A.vegrehajt(ut, uj, t["terv_hash"])


class MdKodolasTest(Alap):
    """C31 (36. döntés): a kódolt md-link feloldódik és kódolt alakban íródik át; a `<…>` burok burokban, kódolás nélkül;
    a nyers szóközös régi alak stílusőrzően nyers marad."""
    FAJLOK = {
        "Régi cél.md": "# Régi\n",
        "Hivo.md": "[a](R%C3%A9gi%20c%C3%A9l.md) [b](<Régi cél.md>) [c](Régi%20cél.md#Fej) [d](Régi cél.md)\n",
    }

    def test_kodolt_burkos_es_nyers(self):
        t = self.A.terv("Régi cél.md", "Mappa nélkül új.md")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.A.vegrehajt("Régi cél.md", "Mappa nélkül új.md", t["terv_hash"])
        self.assertEqual(self.olvas("Hivo.md"),
                         "[a](Mappa%20nélkül%20új.md) [b](<Mappa nélkül új.md>) [c](Mappa%20nélkül%20új.md#Fej) "
                         "[d](Mappa nélkül új.md)\n")
        celok = feloldas.jegyzet_celok(self.olvas("Hivo.md"))
        self.assertEqual(celok, ["Mappa nélkül új.md"] * 4)


class LinkAlakokTest(Alap):
    def test_minden_alak(self):
        r = self.nevez("Cél.md", "Új név.md")
        self.assertEqual(self.olvas("Hivo.md"), (
            "---\nSource: \"[[Új név]]\"\n---\n"
            "A [[Új név]] B [[Új név|alias]] C [[Új név#Fejezet]] D ![[Új név]] E ![[Új név#^b]] F [[ Új név ]] "
            "G `[[Cél]]` H [md](Új%20név.md)\n"
            "| [[Új név\\|x]] | [[Új név\\#Fejezet\\|y]] |\n"
            "```\n[[Cél]]\n```\n[[Új név]]"))
        # az A/Cél.md-re mutató linkek (útvonallal) érintetlenek; a `[[Cél]]` a B/-ből az A/Cél.md-t találta
        # a legközelebbi (azonos alapnevű) jelöltként? Nem: a gyökér Cél.md rövidebb útú, ezért az volt a cél.
        self.assertEqual(self.olvas("B/Útvonalas.md"), "[[A/Cél]] [[A/Cél.md]] [[/A/Cél]] [[Új név]]\n")
        self.assertEqual(self.olvas("Önmaga.md"), self.FAJLOK["Önmaga.md"])
        self.assertFalse((self.v / "Cél.md").exists())
        self.assertEqual(self.olvas("Új név.md"), self.FAJLOK["Cél.md"])
        self.assertEqual(r["modositott"], ["B/Útvonalas.md", "Hivo.md", "Vaszon.canvas"])

    def test_canvas_bajtra_csak_a_valtozo_literal(self):
        self.nevez("Cél.md", "Új név.md")
        c = self.olvas("Vaszon.canvas")
        self.assertEqual(c, self.FAJLOK["Vaszon.canvas"].replace('"file": "Cél.md"', '"file": "Új név.md"').replace(
            "[[Cél]] és [[Cél|név]]\\n`[[Cél]]`", "[[Új név]] és [[Új név|név]]\\n`[[Cél]]`"))

    def test_athelyezes_utvonalas_link_megtartja_a_stilust(self):
        self.nevez("A/Cél.md", "B/Cél.md")
        self.assertEqual(self.olvas("B/Útvonalas.md"), "[[B/Cél]] [[B/Cél.md]] [[/B/Cél]] [[Cél]]\n")
        self.assertIn('"file": "B/Cél.md"', self.olvas("Vaszon.canvas"))

    def test_onmaga_linkje(self):
        self.nevez("Önmaga.md", "Máshogy.md")
        self.assertEqual(self.olvas("Máshogy.md"), "# Önmaga\n[[Máshogy]] [[Máshogy#Cím]]\n")


class CanvasNevTest(Alap):
    FAJLOK = {**ALAP, "Ref.md": "![[Vaszon.canvas]] és [[Vaszon.canvas|a vászon]] és [[Vaszon]]\n"}

    def test_canvas_atnevezese_a_hivatkozok_atirodnak_a_canvas_sajat_linkjei_nem(self):
        elotte = self.olvas("Vaszon.canvas")
        r = self.nevez("Vaszon.canvas", "Új vászon.canvas")
        self.assertEqual(self.olvas("Ref.md"), "![[Új vászon.canvas]] és [[Új vászon.canvas|a vászon]] és [[Vaszon]]\n")   # a kiterjesztés nélküli [[Vaszon]] eleve feloldatlan
        self.assertEqual(self.olvas("Új vászon.canvas"), elotte)       # a vászon saját linkjei a régi fájlokra mutatnak: nem változnak
        self.assertEqual(r["modositott"], ["Ref.md"])


class ElrabolasTest(Alap):
    FAJLOK = {"A/X.md": "# A-X\n", "B/X.md": "# B-X\n", "A/Forrás.md": "[[X]] [[B/X]]\n",
              "C/Hivo.md": "[[X]]\n", "D/Hivo2.md": "[[X]]\n"}

    def setUp(self):
        super().setUp()
        os.makedirs(self.v / "Z")

    def test_elrabolt_link_is_atiródik(self):
        # A/Forrás `[[X]]` az A/X.md-t találta (azonos mappa), C/Hivo és D/Hivo2 az „első” közelit (A/X.md)
        r = self.nevez("A/X.md", "Z/X.md")
        self.assertEqual(self.olvas("A/Forrás.md"), "[[Z/X]] [[B/X]]\n")
        self.assertEqual(self.olvas("C/Hivo.md"), "[[Z/X]]\n")
        self.assertEqual(self.olvas("D/Hivo2.md"), "[[Z/X]]\n")
        self.assertEqual(len(r["modositott"]), 3)

    def test_nem_erintett_link_marad(self):
        # a B/X.md-t áthelyezve az A/X.md-re mutató `[[X]]`-ek közül egyik sem a B/X.md-é
        self.nevez("B/X.md", "Z/Y.md")
        self.assertEqual(self.olvas("C/Hivo.md"), "[[X]]\n")
        self.assertEqual(self.olvas("A/Forrás.md"), "[[X]] [[Z/Y]]\n")


class BajtHuseg(Alap):
    FAJLOK = {"Cél.md": "# Cél\n",
              "Crlf.md": b"Els\xc5\x91 [[C\xc3\xa9l]]\r\nm\xc3\xa1sodik [[C\xc3\xa9l|x]]\r\n",
              "Vegyes.md": b"[[C\xc3\xa9l]]\n\xff\xfe `[[C\xc3\xa9l]]` [[C\xc3\xa9l#a]]\r\n",
              NFD + ".md": "# Ütőér\n[[Cél]]\n"}

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_crlf_es_ervenytelen_utf8(self):
        self.nevez("Cél.md", "Másik.md")
        self.assertEqual((self.v / "Crlf.md").read_bytes(), "Első [[Másik]]\r\nmásodik [[Másik|x]]\r\n".encode())
        self.assertEqual((self.v / "Vegyes.md").read_bytes(), b"[[M\xc3\xa1sik]]\n\xff\xfe `[[C\xc3\xa9l]]` [[M\xc3\xa1sik#a]]\r\n".replace(
            b"M\xc3\xa1sik", "Másik".encode()))

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_nev_athelyezeskor_megmarad(self):
        os.makedirs(self.v / "Mappa")
        self.nevez(unicodedata.normalize("NFC", NFD) + ".md", "Mappa/" + unicodedata.normalize("NFC", NFD) + ".md")
        nevek = os.listdir(self.v / "Mappa")
        self.assertEqual(nevek, [NFD + ".md"])                  # a lemezen álló NFD név megmaradt

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_nev_visszavonas_utan_nfd(self):
        elotte = lenyomat(self.v)
        raw = sorted(os.listdir(self.v))
        r = self.nevez(unicodedata.normalize("NFC", NFD) + ".md", "Új ütőér.md")
        self.assertIn("Mos-Lemezen", self.repo.log(1)[0].trailers)
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(sorted(os.listdir(self.v)), raw)       # bájtra ÉS a lemezen álló névre az eredeti
        self.assertEqual(lenyomat(self.v), elotte)


class VisszavonasTest(Alap):
    def test_egy_commit_es_visszavonas(self):
        elotte = lenyomat(self.v)
        r = self.nevez("Cél.md", "Új név.md")
        log = self.repo.log(5)
        self.assertEqual(len(log), 2)                            # alap + 1 gépi (a kézi nem kellett)
        c = log[0]
        self.assertEqual(c.trailers["Mos-Forras"], "pult-szerkeszto")
        self.assertTrue(c.run.startswith("ATNEV-"))
        self.assertEqual(c.trailers["Mos-Tetel"], "Új név.md")
        self.assertIn("Cél.md", self.repo.changed_files(c.sha))
        self.assertIn("Új név.md", self.repo.changed_files(c.sha))
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_kezi_valtozas_elobb_kulon_commitba_kerul(self):
        (self.v / "Cél.md").write_text("# Cél\n\n## Fejezet\nSzöveg ^b\nkézzel\n", encoding="utf-8")
        self.ix.frissit(["Cél.md"])
        self.nevez("Cél.md", "Új.md")
        log = self.repo.log(5)
        self.assertEqual([c.trailers.get("Mos-Forras") for c in log[:2]], ["pult-szerkeszto", "kezi"])


class BlokkoloTest(Alap):
    def blokk(self, ut, uj):
        t = self.A.terv(ut, uj)
        self.assertFalse(t["ok"])
        return " ".join(t["blokkolok"])

    def test_blokkolok(self):
        self.assertTrue(self.A.terv("kep.png", "uj.png")["ok"])
        self.assertIn("kiterjesztés", self.blokk("Cél.md", "Cél.canvas"))
        self.assertIn("Érvénytelen név", self.blokk("Cél.md", "Cé#l.md"))
        with self.assertRaises(vaultio.Invalid):
            self.A.terv("Cél.md", ".rejtett.md")
        self.assertIn("Nincs ilyen mappa", self.blokk("Cél.md", "Nincs/Cél.md"))
        self.assertIn("Már van ilyen", self.blokk("Cél.md", "Önmaga.md"))
        self.assertIn("Már van ilyen", self.blokk("Cél.md", "önmaga.md"))
        self.assertIn("nem változott", self.blokk("Cél.md", "Cél.md"))
        with self.assertRaises(vaultio.Invalid):
            self.A.terv("Cél.md", ".obsidian/x.md")
        with self.assertRaises(vaultio.Invalid):
            self.A.terv("../x.md", "y.md")
        with self.assertRaises(vaultio.NotFound):
            self.A.terv("nincs.md", "y.md")

    def test_terv_csak_olvas(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        self.assertTrue(t["ok"])
        self.assertEqual({f["ut"] for f in t["fajlok"]}, {"Hivo.md", "B/Útvonalas.md", "Vaszon.canvas"})
        self.assertEqual(lenyomat(self.v), elotte)
        h = next(f for f in t["fajlok"] if f["ut"] == "Hivo.md")
        self.assertEqual(h["linkek"][0]["sor"], 2)               # a frontmatter Source-sora
        self.assertEqual(h["linkek"][0]["uj"], 'Source: "[[Új név]]"')

    def test_foglalt_es_pillanatkep_nelkul(self):
        t = self.A.terv("Cél.md", "Új név.md")
        self.busy = True
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.busy = False
        import shutil
        shutil.rmtree(self.repo.git_dir)
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertIn("pillanatkép", str(e.exception))


class BiztonsagTest(Alap):
    def test_hash_eltérés_semmi_nem_valtozik(self):
        t = self.A.terv("Cél.md", "Új név.md")
        (self.v / "Hivo.md").write_text("[[Cél]] közben átírva\n", encoding="utf-8")
        elotte = lenyomat(self.v)
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)

    def test_rossz_terv_hash(self):
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", "nem-jo")
        self.assertTrue(e.exception.adat.get("valtozott"))

    def test_felbeszakadt_iras_visszaall(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        eredeti, db = self.A._ir, [0]

        def torott(p, b, **k):
            db[0] += 1
            if db[0] == 2:
                raise OSError("lemez megtelt")
            return eredeti(p, b, **k)

        self.A._ir = torott
        with self.assertRaises(atnevezes.Hiba):
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)
        self.assertEqual([e["allapot"] for e in self.esemenyek if e["tipus"] == "vault_atnevezes"], ["kezd", "vissza"])

    def test_bukó_proba_visszaall(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        self.A._proba = staticmethod(lambda *a, **k: ["kitalált hiba"])
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual(e.exception.adat["proba_hibak"], ["kitalált hiba"])
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)

    def test_a_proba_valodi_hibat_fog(self):
        """A próba nem „mindent elfogadó”: egy rosszul átírt link hibát ad."""
        elotte = feloldas.hivatkozasok(self.v)
        terv = self.A._terv("Cél.md", "Új név.md")
        # átnevezés elvégzése átírás nélkül: a linkek eltörnek
        os.rename(self.v / "Cél.md", self.v / "Új név.md")
        utana = feloldas.hivatkozasok(self.v)
        hibak = atnevezes.Atnevezes._proba(elotte, utana, terv, {})
        self.assertTrue(hibak)
        self.assertTrue(any("Hivo.md" in h for h in hibak))

    def test_esemenyek_sorrendje(self):
        r = self.nevez("Cél.md", "Új név.md")
        e = [x for x in self.esemenyek if x["tipus"] == "vault_atnevezes"]
        self.assertEqual([x["allapot"] for x in e], ["kezd", "kesz"])
        self.assertEqual(e[1]["pillanat"], r["pillanat"])


class KisNagybetuTest(Alap):
    def test_hivatkozas_nelkuli_case_atnevezes_gepi_pillanat(self):
        ir(self.v, 'Magányos.md', '# Tartalom')
        self.repo.commit('kézi jegyzet'); self.ix.frissit(['Magányos.md'])
        r = self.nevez('Magányos.md', 'magányos.md')
        self.assertIsNotNone(r['pillanat'])
        self.assertEqual(self.repo.log(1)[0].trailers['Mos-Forras'], 'pult-szerkeszto')
        utak = self.repo.git('ls-tree', '-r', '--name-only', 'HEAD').stdout.splitlines()
        self.assertIn('magányos.md', utak); self.assertNotIn('Magányos.md', utak)

    def test_csak_kis_nagybetu_atnevezheto(self):
        r = self.nevez("Cél.md", "CÉL.md")
        self.assertIn("CÉL.md", [p.name for p in self.v.iterdir()])
        self.assertNotIn("Cél.md", [p.name for p in self.v.iterdir()])
        self.assertIn("CÉL.md", self.repo.git("ls-files").stdout.splitlines())
        self.assertFalse(r["visszavonhato"])
        t = self.A.terv("Cél.md", "B/cél.md")           # másik mappába: valódi áthelyezés, a név kis-nagybetűje mellékes
        self.assertTrue(t["ok"])


class ObsidianSzabalyTest(Alap):
    """C10.6 (13. döntés): az átnevezés az új feloldással és maszkkal — a más betűzésű link is a jegyzeté, a
    `~~~` blokkban, a több-backtickes kódban és a képletben álló `[[…]]` nem link, bájtra marad."""

    FAJLOK = {
        "Cél.md": "# Cél\n",
        "Mappa/Másik.md": "# Másik\n",
        "Hivo.md": ("[[cél]] [[CÉL|alias]] [[Cél]] [[cél.md]] [md](cél.md)\n"
                    "~~~\n[[Cél]]\n~~~\n``[[Cél]] ` `` $[[Cél]]$\n$$\n[[Cél]]\n$$\n"
                    "[[mappa/másik]] [[x/Cél]]\n"),
        "Vaszon.canvas": '{"nodes":[{"id":"1","type":"text","text":"[[cél]] ``[[Cél]]`` $[[Cél]]$"}],"edges":[]}',
    }

    def test_a_mas_betuzesu_link_atirodik_a_maszkolt_marad(self):
        r = self.nevez("Cél.md", "Új név.md")
        self.assertEqual(self.olvas("Hivo.md"), (
            "[[Új név]] [[Új név|alias]] [[Új név]] [[Új név.md]] [md](Új%20név.md)\n"
            "~~~\n[[Cél]]\n~~~\n``[[Cél]] ` `` $[[Cél]]$\n$$\n[[Cél]]\n$$\n"
            "[[mappa/másik]] [[x/Cél]]\n"))
        self.assertEqual(self.olvas("Vaszon.canvas"),
                         '{"nodes":[{"id":"1","type":"text","text":"[[Új név]] ``[[Cél]]`` $[[Cél]]$"}],"edges":[]}')
        self.assertEqual(r["modositott"], ["Hivo.md", "Vaszon.canvas"])

    def test_athelyezes_a_mas_betuzesu_utvonalas_link_stilust_tart(self):
        os.makedirs(self.v / "Z")
        self.nevez("Mappa/Másik.md", "Z/Másik.md")
        self.assertIn("[[Z/Másik]] [[x/Cél]]", self.olvas("Hivo.md"))

    def test_visszavonas_utan_bajtra_az_eredeti(self):
        elotte = lenyomat(self.v)
        r = self.nevez("Cél.md", "Új név.md")
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)


class EgyidejuSzerkesztesTest(Alap):
    """C29.6 (2. audit T015, T092, T106): az átnevezés fogja az érintett utak zárát (a beékelt mentés vár, majd 409), a mentetlen
    forrásba nem nyúl, a közben létrejött célra nem ír rá, a próba nem olvassa újra a terven kívüli fájlokat, és a saját
    bájtjait állítja csak vissza."""

    def _rename_utan(self, tennivalo):
        """A `tartos.rename_excl` becsomagolása: a valódi átnevezés után lefut a `tennivalo()` (az „utána” próba előtt)."""
        eredeti = tartos.rename_excl

        def csomag(src, dst):
            eredeti(src, dst)
            tennivalo()
        return mock.patch.object(atnevezes.tartos, "rename_excl", csomag)

    def test_a_terven_kivuli_kulso_fajl_az_ablakban_nem_buktatja_a_probat(self):
        """C33 (a soak lelete): egy külső író (Obsidian-szinkron, Finder) az átnevezés ablakában a terven kívül fájlt hoz létre —
        a referencia-próba a fájlhalmaz eltérése miatt 500-zal visszaállt (30 perces soakban 181/183 átnevezés). A terven kívüli
        fájl nem az átnevezés hibája: a próba csak a terv útjait nézi; ha a link-próba mégis eltér, az 409 (közben változott)."""
        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_utan(lambda: ir(self.v, "Kulso/Szinkron közben.md", "# más\n")):
            r = self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertTrue(r["ok"])
        self.assertIn("[[Új név]]", self.olvas("Hivo.md"))
        self.assertTrue((self.v / "Kulso" / "Szinkron közben.md").exists())

    def test_a_kulso_valtozasra_bukott_proba_409(self):
        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_utan(lambda: ir(self.v, "Kulso/Más.md", "# más\n")), \
                mock.patch.object(atnevezes.Atnevezes, "_proba", staticmethod(lambda *a: ["kitalált link-eltérés"])), \
                self.assertRaises(atnevezes.Hiba) as cm:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(cm.exception.kod, 409)
        self.assertEqual(cm.exception.adat["kulso"], ["Kulso/Más.md"])
        self.assertTrue((self.v / "Cél.md").exists())

    def test_beekelt_mentes_varakozik_majd_utkozest_kap_es_nem_vesz_el_szoveg(self):
        """T015: a mentés a link-átírás/próba ablakában eddig átjutott (nem volt útvonal-zár), a próba „a terven kívül változott”
        miatt 500-zal visszaállt, és a visszaállítás vakon felülírta a mentett szöveget (`ok: true`, mégis elveszett)."""
        alap = vaultio.sha1((self.v / "Hivo.md").read_bytes())
        eredmeny = {}

        def ment():
            try:
                self.V.write({"ut": "Hivo.md", "tartalom": "# a szerkesztő szövege\n", "alap": alap})
                eredmeny["r"] = "ok"
            except vaultio.Conflict:
                eredmeny["r"] = "utkozes"
            except Exception as e:  # noqa: BLE001
                eredmeny["r"] = repr(e)

        def beekel():
            eredmeny["szal"] = threading.Thread(target=ment)
            eredmeny["szal"].start()
            time.sleep(0.3)                                     # a mentésnek a zárra kell várnia

        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_utan(beekel):
            r = self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        eredmeny["szal"].join(15)
        self.assertTrue(r["ok"])
        self.assertEqual(eredmeny["r"], "utkozes", "a mentés a zár alatt nem írhat: az átírt alap miatt 409")
        self.assertIn("[[Új név]]", self.olvas("Hivo.md"))        # az átnevezés tartalma áll, a szerkesztő szövege nem „csúszott be” és nem tűnt el némán
        self.assertEqual(self.repo.dirty_paths(), [])

    def test_mentetlen_forras_409(self):
        masik = atnevezes.Atnevezes(self.cfg, self.V, self.ix, mentetlen=lambda: {"cél.md"})        # kis-nagybetűtől független
        t = masik.terv("Cél.md", "Új név.md")
        with self.assertRaises(atnevezes.Hiba) as e:
            masik.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertTrue(e.exception.adat["nyitott"])
        self.assertEqual(e.exception.adat["utak"], ["Cél.md"])
        self.assertTrue((self.v / "Cél.md").exists())
        # egy nem érintett, mentetlen dokumentum nem akadály
        negyedik = atnevezes.Atnevezes(self.cfg, self.V, self.ix, mentetlen=lambda: {"Önmaga.md"})
        negyedik.vegrehajt("Cél.md", "Új név.md", negyedik.terv("Cél.md", "Új név.md")["terv_hash"])
        self.assertTrue((self.v / "Új név.md").exists())

    def test_kozben_letrejott_cel_nincs_felulirva_es_visszaall(self):
        """T092 (L12): az `os.rename` felülírta a közben létrejött célfájlt (az ellenőrzés és az átnevezés közti ablak a
        link-átírásokkal és a próbával megnőtt)."""
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        n, eredeti, db = len(self.A._terv("Cél.md", "Új név.md").fajlok), self.A._ir, [0]

        def ir_es_cel(p, b, **k):
            eredeti(p, b, **k)
            db[0] += 1
            if db[0] == n:
                (self.v / "Új név.md").write_text("a felhasználó közben létrehozta\n", encoding="utf-8")

        self.A._ir = ir_es_cel
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.A._ir = eredeti
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual((self.v / "Új név.md").read_text(encoding="utf-8"), "a felhasználó közben létrehozta\n")
        (self.v / "Új név.md").unlink()
        self.assertEqual(lenyomat(self.v), elotte, "a link-átírások visszaálltak, a cél bájtjai érintetlenek maradtak")
        self.assertFalse((self.cfg.path("run") / atnevezes.NAPLO).exists())

    def test_terven_kivuli_fajl_kozbeni_modositasa_nem_okoz_visszaallitast(self):
        """T106: az „utána” próba a terven kívüli fájlok bájtjait is összevetette — bármely közbeni külső mentés 500-as
        visszaállítást okozott. Most a közben módosult (mtime/méret) terven kívüli fájl kimarad a próbából."""
        def kulso_mentes():
            (self.v / "Önmaga.md").write_text("# Önmaga\n[[Önmaga]] [[Önmaga#Cím]]\nkülső szerkesztés\n", encoding="utf-8")

        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_utan(kulso_mentes):
            r = self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertTrue(r["ok"])
        self.assertIn("külső szerkesztés", self.olvas("Önmaga.md"))
        self.assertTrue((self.v / "Új név.md").exists())

    def test_a_proba_csak_a_tervezett_fajlokat_olvassa_ujra(self):
        eredeti = atnevezes.Atnevezes._fajl_linkjei
        hivasok = []

        def szamol(rp, b, fo):
            hivasok.append(rp)
            return eredeti(rp, b, fo)

        t = self.A._terv("Cél.md", "Új név.md")
        tervezett = set(t.fajlok) | set(t.lek)
        with mock.patch.object(atnevezes.Atnevezes, "_fajl_linkjei", staticmethod(szamol)), \
                mock.patch.object(feloldas, "hivatkozasok", side_effect=AssertionError("a teljes fa újraolvasása")):
            self.A.vegrehajt("Cél.md", "Új név.md", self.A.terv("Cél.md", "Új név.md")["terv_hash"])
        osszes = [rp for rp in lenyomat(self.v) if rp.endswith((".md", ".canvas", ".base"))]
        bazis = {f["ut"] for f in self.ix.bazis_forrasok()}
        self.assertEqual(len(hivasok), 2 * len(tervezett | bazis), hivasok)        # egyszer „előtte”, egyszer „utána”
        self.assertLess(len(hivasok), 2 * len(osszes))

    def test_a_visszaallitas_csak_a_sajat_bajtjait_irja_vissza(self):
        """T015: a hiba utáni visszaállítás a memóriában tartott régi bájtokat vakon visszaírta — a közben más által átírt fájl
        elvesztette a módosítást. Most a közben megváltozott fájl érintetlen marad, a napló megmarad."""
        t = self.A.terv("Cél.md", "Új név.md")
        idegen = "# valaki mást írt ide\n"

        def bukó_proba(elotte, utana, terv, vart):
            (self.v / "Hivo.md").write_text(idegen, encoding="utf-8")
            return ["kitalált hiba"]

        self.A._proba = staticmethod(bukó_proba)
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual(self.olvas("Hivo.md"), idegen, "az idegen módosítást a visszaállítás nem tapossa el")
        self.assertTrue((self.v / "Cél.md").exists() and not (self.v / "Új név.md").exists(), "a név visszaállt")
        self.assertTrue((self.cfg.path("run") / atnevezes.NAPLO / "terv.json").is_file(), "a nem teljes visszaállítás naplót hagy")


class KozbenEltuntTest(Alap):
    """C33 (T175): ha egy érintett fájl az átnevezés ablakában eltűnik (külső törlés), az átnevezés visszaáll és 409-et ad (nem
    500-at abszolút úttal); a többi lemezhiba a `lemez_hiba` szerinti 503/507, magyarul, út nélkül."""

    def _rename_hibaval(self, hiba):
        def csomag(src, dst):
            raise hiba
        return mock.patch.object(atnevezes.tartos, "rename_excl", csomag)

    def test_a_kozben_eltunt_fajl_409_es_visszaall(self):
        eredeti = self.olvas("Hivo.md")
        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_hibaval(FileNotFoundError(2, "No such file or directory", str(self.v / "Cél.md"))), \
                self.assertRaises(atnevezes.Hiba) as cm:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(cm.exception.kod, 409)
        self.assertTrue(cm.exception.adat.get("valtozott"))
        self.assertNotIn(str(self.v), str(cm.exception))
        self.assertEqual(self.olvas("Hivo.md"), eredeti)          # a link-átírás visszaállt

    def test_a_lemezhiba_503_magyarul_ut_nelkul(self):
        import errno
        t = self.A.terv("Cél.md", "Új név.md")
        with self._rename_hibaval(PermissionError(errno.EACCES, "Permission denied", str(self.v / "Cél.md"))), \
                self.assertRaises(atnevezes.Hiba) as cm:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(cm.exception.kod, 503)
        self.assertTrue(cm.exception.adat.get("lemez_hiba"))
        self.assertEqual(cm.exception.adat["kod"], "lemez.eacces")
        self.assertEqual((cm.exception.hiba_kod, cm.exception.hiba_param), ("lemez.eacces", {"errno": "EACCES"}))
        self.assertNotIn(str(self.v), str(cm.exception))
        self.assertTrue((self.v / "Cél.md").exists())


class SzandeknaploTest(Alap):
    """H3 (audit): a megszakadt átnevezés (a core meghal az írások és az `os.rename` között, vagy a próba alatt)
    után a vault nem maradhat félig átírva. A terv és az eredeti bájtok az első írás előtt a `{run}/atnevezes/`
    naplóba kerülnek (fsync); induláskor a napló alapján visszaáll minden, és üzenet megy a felületnek.
    A folyamat halálát a folyamaton belüli visszaállítás kikapcsolása és egy BaseException szimulálja."""

    class Halal(BaseException):
        pass

    def setUp(self):
        super().setUp()
        self.A._visszaallit = lambda lepesek: None          # a halott folyamat nem állít vissza semmit
        self.naplo = self.cfg.path("run") / "atnevezes"

    def _meghal_az_irasok_utan(self):
        t = self.A.terv("Cél.md", "Új név.md")
        n, eredeti, db = len(self.A._terv("Cél.md", "Új név.md").fajlok), self.A._ir, [0]

        def ir_es_hal(p, b, **k):
            eredeti(p, b, **k)
            db[0] += 1
            if db[0] == n:
                raise self.Halal()

        self.A._ir = ir_es_hal
        with self.assertRaises(self.Halal):
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])

    def test_halal_az_atnevezes_elott_induláskor_visszaall(self):
        elotte = lenyomat(self.v)
        self._meghal_az_irasok_utan()
        self.assertNotEqual(lenyomat(self.v), elotte)                 # félig átírt vault
        self.assertTrue((self.naplo / "terv.json").is_file())
        uzenetek = atnevezes.helyreallit(self.cfg)
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertFalse(self.naplo.exists())
        self.assertTrue(uzenetek and "Cél.md" in uzenetek[0])
        self.assertEqual(atnevezes.helyreallit(self.cfg), [])

    def test_halal_az_atnevezes_utan_visszaall(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")

        def proba_es_hal(*a, **k):
            raise self.Halal()

        self.A._proba = staticmethod(proba_es_hal)
        with self.assertRaises(self.Halal):
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertTrue((self.v / "Új név.md").exists())
        atnevezes.helyreallit(self.cfg)
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)

    def test_a_commit_utan_csak_a_naplo_torlodik(self):
        regi = atnevezes._naplo_torol
        atnevezes._naplo_torol = lambda cfg: None
        try:
            self.nevez("Cél.md", "Új név.md")
        finally:
            atnevezes._naplo_torol = regi
        utana = lenyomat(self.v)
        self.assertTrue((self.naplo / "terv.json").is_file())
        self.assertEqual(atnevezes.helyreallit(self.cfg), [])
        self.assertEqual(lenyomat(self.v), utana)
        self.assertFalse(self.naplo.exists())

    def test_kozben_kezzel_irt_fajlt_nem_ir_felul(self):
        self._meghal_az_irasok_utan()
        (self.v / "Hivo.md").write_text("# a gazda közben átírta\n", encoding="utf-8")
        uzenetek = atnevezes.helyreallit(self.cfg)
        self.assertEqual(self.olvas("Hivo.md"), "# a gazda közben átírta\n")
        self.assertIn("Hivo.md", " ".join(uzenetek))

    def test_sikeres_es_visszaallt_atnevezes_utan_nincs_naplo(self):
        self.nevez("Cél.md", "Új név.md")
        self.assertFalse(self.naplo.exists())

    def test_nem_letezo_vaulton_a_naplo_erintetlen(self):
        """T002 (2. audit): a symlinkelt `var/`-ú munkafa core-ja a valódi `{run}`-t kapja, a vault útja viszont nem
        létezik. A helyreállítás ilyenkor nem nyúl a naplóhoz: a valódi app indulása még megtalálja és visszaállítja."""
        elotte = lenyomat(self.v)
        self._meghal_az_irasok_utan()
        felig = lenyomat(self.v)
        elmozgatva = self.v.with_name("Manifold-elmozgatva")
        self.v.rename(elmozgatva)
        self.assertEqual(atnevezes.helyreallit(self.cfg), [])
        self.assertTrue((self.naplo / "terv.json").is_file())
        elmozgatva.rename(self.v)
        self.assertEqual(lenyomat(self.v), felig)
        uzenetek = atnevezes.helyreallit(self.cfg)                       # a valódi vaulton már visszaáll
        self.assertTrue(uzenetek and "was restored" in uzenetek[0])
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertFalse(self.naplo.exists())

    def test_az_uzenet_nem_allit_visszaallast_ha_semmi_nem_allt_vissza(self):
        """T002: a core az első írás előtt halt meg (a napló kész, a vault érintetlen): nincs mit visszaállítani,
        és az üzenet ezt mondja, nem hamis „visszaállt”-at."""
        t = self.A.terv("Cél.md", "Új név.md")

        def nem_ir(p, b, **k):
            raise self.Halal()

        self.A._ir = nem_ir
        with self.assertRaises(self.Halal):
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertTrue((self.naplo / "terv.json").is_file())
        elotte = lenyomat(self.v)
        (uzenet,) = atnevezes.helyreallit(self.cfg)
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertNotIn("was restored", uzenet)
        self.assertIn("no restoration was needed", uzenet)
        self.assertFalse(self.naplo.exists())


class SzandeknaploVisszaallasTest(Alap):
    def test_folyamaton_beluli_visszaallitas_utan_nincs_naplo(self):
        t = self.A.terv("Cél.md", "Új név.md")
        self.A._proba = staticmethod(lambda *a, **k: ["kitalált hiba"])
        with self.assertRaises(atnevezes.Hiba):
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertFalse((self.cfg.path("run") / "atnevezes").exists())


def lenyomat_mappakkal(gyoker):
    """A fájlok bájtjai ÉS a mappák (az üresek is) NFC úton — a mappa-mozgatás visszavonásának mércéje."""
    ki = lenyomat(gyoker)
    mappak = set()
    for d, ms, _ in os.walk(gyoker):
        ms[:] = [m for m in ms if m != ".obsidian"]
        for m in ms:
            mappak.add(unicodedata.normalize("NFC", os.path.relpath(os.path.join(d, m), gyoker)))
    return ki, mappak


def lemezen_nevek(gyoker, rel):
    """A lemezen álló (nyers) nevek a `rel` mappában."""
    return sorted(os.listdir(os.path.join(gyoker, rel)))


MAPPA_FAJLOK = {
    ".obsidian/app.json": "{}",
    "Tan/Elmélet/A.md": "# A\n[[B]] [[Tan/Elmélet/Alma/C]] [[Kint]]\n",
    "Tan/Elmélet/B.md": "# B\n[[A]] [[Elmélet/Alma/C|alias]]\n",
    "Tan/Elmélet/Alma/C.md": "# C\n[[A]] [[Gyujto]]\n",
    "Tan/Elmélet/Vaszon.canvas": ('{"nodes":[{"id":"1","type":"file","file":"Tan/Elmélet/A.md"},'
                                  '{"id":"2","type":"text","text":"[[Tan/Elmélet/B]]"}],"edges":[]}'),
    "Kint.md": "# Kint\n[[Tan/Elmélet/A]] [[B]] [[Elmélet/Alma/C]] ![[kep.png]]\n",
    "Mas/Gyujto.md": "# Gyűjtő\n[[Elmélet/A]] [[Tan/Elmélet/B.md]]\n",
    "Mas/B.md": "# Másik B\n",
    "Cel/Hely.md": "# Hely\n",
    "Tan/Kep/kep.png": b"\x89PNG\r\n",
    "Tan/Kep/Jegyzet.md": "# Képes\n![[kep.png]]\n",
    "Ures/Alfa/.gitkeep.md": "",
    "kep.png": b"\x89PNG\r\n",
}


class MappaTest(Alap):
    """C11a (21. döntés): mappa átnevezése/áthelyezése leképezésként — a link-átírás, a próba, az egy commit és a
    visszavonás bájtra ÉS mappaszerkezetre; a médiát tartalmazó mappa blokkolt."""
    FAJLOK = MAPPA_FAJLOK

    def blokk(self, ut, uj):
        t = self.A.terv(ut, uj)
        self.assertFalse(t["ok"], (ut, uj))
        return " ".join(t["blokkolok"])

    def test_atnevezes_linkek_commit_es_visszavonas(self):
        elotte = lenyomat_mappakkal(self.v)
        t = self.A.terv("Tan/Elmélet", "Tan/Tananyag")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual((t["mappa"], t["mozgo_fajlok"]), (True, 4))
        r = self.nevez("Tan/Elmélet", "Tan/Tananyag")
        self.assertEqual((r["ok"], r["mappa"], r["mozgo_fajlok"]), (True, True, 4))
        self.assertFalse((self.v / "Tan/Elmélet").exists())
        self.assertTrue((self.v / "Tan/Tananyag/Alma/C.md").is_file())
        self.assertIn("[[Tan/Tananyag/A]]", self.olvas("Kint.md"))
        self.assertIn("[[Tan/Tananyag/Alma/C]]", self.olvas("Tan/Tananyag/A.md"))
        self.assertIn('"file":"Tan/Tananyag/A.md"', self.olvas("Tan/Tananyag/Vaszon.canvas"))
        self.assertIn("[[Tananyag/A]]", self.olvas("Mas/Gyujto.md"))
        log = self.repo.log(5)
        self.assertEqual(len(log), 2)                                     # alap + EGY gépi commit
        self.assertTrue(log[0].run.startswith("ATNEV-"))
        self.assertEqual(log[0].trailers["Mos-Tetel"], "Tan/Tananyag")
        fajlok = self.repo.changed_files(log[0].sha)
        self.assertIn("Tan/Elmélet/A.md", fajlok)
        self.assertIn("Tan/Tananyag/A.md", fajlok)
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)              # bájtra és mappaszerkezetre (nincs üres célmappa)

    def test_athelyezes_masik_mappaba_es_visszavonas(self):
        elotte = lenyomat_mappakkal(self.v)
        r = self.nevez("Tan/Elmélet", "Cel/Elmélet")
        self.assertTrue((self.v / "Cel/Elmélet/A.md").is_file())
        self.assertIn("[[Cel/Elmélet/A]]", self.olvas("Kint.md"))
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)

    def test_minden_link_ugyanarra_a_fajlra_old_a_mozgatas_utan(self):
        """A lemezről számolt referencia-próba (az átnevezés saját próbájától függetlenül, itt is): minden korábban
        feloldott link a (mozgatott) ugyanazon fájlra old, a linkek száma és sorrendje ugyanaz."""
        def uj(ut):
            return "Cel/Elmélet/" + ut[len("Tan/Elmélet/"):] if ut and ut.startswith("Tan/Elmélet/") else ut
        elotte = feloldas.hivatkozasok(self.v)
        self.nevez("Tan/Elmélet", "Cel/Elmélet")
        utana = feloldas.hivatkozasok(self.v)
        self.assertEqual(sorted(utana["files"]), sorted(uj(x) for x in elotte["files"]))
        self.assertEqual(sum(len(v) for v in utana["linkek"].values()), sum(len(v) for v in elotte["linkek"].values()))
        for forras, lista in elotte["linkek"].items():
            masik = utana["linkek"][uj(forras)]
            self.assertEqual([uj(h) for _, h in lista], [h for _, h in masik], forras)

    def test_blokkolok(self):
        self.assertTrue(self.A.terv("Tan", "Tan2")["ok"])
        self.assertTrue(self.A.terv("Tan", "Cel/Tan")["ok"])
        self.assertIn("nem változott", self.blokk("Tan/Elmélet", "Tan/Elmélet"))
        self.assertTrue(self.A.terv("Tan/Elmélet", "Tan/elmélet")["ok"])
        self.assertIn("önmagába", self.blokk("Tan/Elmélet", "Tan/Elmélet/Alma/Mély"))
        self.assertIn("Már van ilyen", self.blokk("Tan/Elmélet", "Mas"))
        self.assertIn("Nincs ilyen mappa", self.blokk("Tan/Elmélet", "Nincs/Ilyen/Elmélet"))
        self.assertIn("Érvénytelen mappanév", self.blokk("Tan/Elmélet", "Tan/Rossz#név"))

    def test_ures_mappa_atnevezheto(self):
        (self.v / "Valodi Ures" / "Alsó").mkdir(parents=True)
        self.ix.frissit(["Valodi Ures"])
        self.nevez("Valodi Ures", "Valodi Ures 2")
        self.assertTrue((self.v / "Valodi Ures 2" / "Alsó").is_dir())
        self.assertFalse((self.v / "Valodi Ures").exists())

    def test_nincs_ilyen_mappa_es_fajl(self):
        with self.assertRaises(vaultio.NotFound):
            self.A.terv("Nincs/Ilyen.md", "Uj.md")
        with self.assertRaises(vaultio.Invalid):
            self.A.terv("../Kint", "Uj")

    def test_hash_eltérés_semmi_nem_valtozik(self):
        t = self.A.terv("Tan/Elmélet", "Tan/Tananyag")
        (self.v / "Tan/Elmélet/B.md").write_text("# B\n[[A]] közben átírva\n", encoding="utf-8")
        elotte = lenyomat_mappakkal(self.v)
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Tan/Elmélet", "Tan/Tananyag", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)

    def test_bukó_proba_teljes_visszaallas(self):
        elotte = lenyomat_mappakkal(self.v)
        t = self.A.terv("Tan/Elmélet", "Tan/Tananyag")
        self.A._proba = staticmethod(lambda *a, **k: ["kitalált hiba"])
        with self.assertRaises(atnevezes.Hiba):
            self.A.vegrehajt("Tan/Elmélet", "Tan/Tananyag", t["terv_hash"])
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)
        self.assertFalse((self.cfg.path("run") / "atnevezes").exists())

    def test_esemenyek_jelzik_a_mappat(self):
        self.nevez("Tan/Elmélet", "Tan/Tananyag")
        self.assertEqual([(e["allapot"], e["mappa"]) for e in self.esemenyek if e["tipus"] == "vault_atnevezes"],
                         [("kezd", True), ("kesz", True)])

    def test_az_index_kovetja_a_mappat(self):
        self.nevez("Tan/Elmélet", "Tan/Tananyag")
        fa = self.ix.fa()
        self.assertIn("Tan/Tananyag", fa["mappak"])
        self.assertIn("Tan/Tananyag/Alma", fa["mappak"])
        self.assertNotIn("Tan/Elmélet", fa["mappak"])
        utak = {f["ut"] for f in fa["fajlok"]}
        self.assertIn("Tan/Tananyag/Alma/C.md", utak)
        self.assertNotIn("Tan/Elmélet/A.md", utak)


class MappaSzandeknaploTest(Alap):
    """A megszakadt mappa-átnevezés (a core meghal az írások után / az átnevezés után, a commit előtt): induláskor
    a napló alapján a mappa visszanevezi magát, és minden fájl az eredeti bájtjait kapja (H3)."""
    FAJLOK = MAPPA_FAJLOK

    class Halal(BaseException):
        pass

    def setUp(self):
        super().setUp()
        self.A._visszaallit = lambda lepesek: None
        self.naplo = self.cfg.path("run") / "atnevezes"

    def test_halal_a_commit_elott_visszaall(self):
        elotte = lenyomat_mappakkal(self.v)
        t = self.A.terv("Tan/Elmélet", "Cel/Elmélet")

        def hal(*a, **k):
            raise self.Halal()
        self.A._proba = staticmethod(hal)
        with self.assertRaises(self.Halal):
            self.A.vegrehajt("Tan/Elmélet", "Cel/Elmélet", t["terv_hash"])
        self.assertTrue((self.v / "Cel/Elmélet").is_dir())                 # az átnevezés megtörtént, a commit nem
        uzenetek = atnevezes.helyreallit(self.cfg)
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)
        self.assertFalse(self.naplo.exists())
        self.assertTrue(uzenetek and "Tan/Elmélet" in uzenetek[0])

    def test_halal_az_irasok_utan_az_atnevezes_elott(self):
        elotte = lenyomat_mappakkal(self.v)
        t = self.A.terv("Tan/Elmélet", "Cel/Elmélet")
        eredeti = self.A._ir

        db = [0]
        n = len(t["fajlok"])

        def ir_es_hal(p, b, **k):
            eredeti(p, b, **k)
            db[0] += 1
            if db[0] == n:
                raise self.Halal()
        self.A._ir = ir_es_hal
        with self.assertRaises(self.Halal):
            self.A.vegrehajt("Tan/Elmélet", "Cel/Elmélet", t["terv_hash"])
        self.assertNotEqual(lenyomat_mappakkal(self.v), elotte)
        atnevezes.helyreallit(self.cfg)
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)


class MappaNfdTest(unittest.TestCase):
    """Lemezen NFD nevű mappa és fájl: a mozgatás a lemezen álló nevet megtartja, a visszavonás visszaadja."""

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_mappa_es_fajl_visszavonas_nevre_is(self):
        from tests.index_segedek import NFD
        with tmpdir() as t:
            cfg, root, v = alg_core(t)
            ir(v, "Cel/Hely.md", "# Hely\n")
            (v / NFD).mkdir()
            ir(v, NFD + "/" + NFD + ".md", "# Ütőér\n[[Hely]]\n")
            ir(v, NFD + "/Másik.md", "# Másik\n[[" + NFD + "]]\n")
            repo = snapshot.repos(cfg)["vault"]
            repo.init()
            repo.commit("alap", {"Mos-Forras": "kezi"})
            ix, _ = index_indit(cfg)
            try:
                A = atnevezes.Atnevezes(cfg, vaultio.Vault(cfg), ix)
                elotte = (lemezen_nevek(v, ""), lemezen_nevek(v, NFD))
                uj = unicodedata.normalize("NFC", NFD)
                tv = A.terv(uj, "Cel/" + uj)
                self.assertTrue(tv["ok"], tv["blokkolok"])
                r = A.vegrehajt(uj, "Cel/" + uj, tv["terv_hash"])
                self.assertEqual(lemezen_nevek(v, "Cel"), sorted(["Hely.md", NFD]))      # a mappa lemezen álló neve NFD maradt
                self.assertEqual(lemezen_nevek(v, "Cel/" + NFD), sorted([NFD + ".md", "Másik.md"]))
                repo.undo_commit(r["pillanat"])
                self.assertEqual((lemezen_nevek(v, ""), lemezen_nevek(v, NFD)), elotte)
            finally:
                ix.leallit()


BAZIS_FAJLOK = {
    "Cél.md": "# Cél\n",
    "A/Cél.md": "# A-s Cél\n",
    "B/Segéd.md": "# Segéd\n",
    "Hivo.md": "A [[Cél]] link.\n",
    "Könyvek.base": ("# megjegyzés\n"
                     "filters:\n"
                     "  and:\n"
                     "    - file.hasLink(link(\"Cél\"))   # a Cél-re mutatók\n"
                     "    - file.path == \"Cél.md\"\n"
                     "    - file.name == \"Cél.md\"\n"
                     "formulas:\n"
                     "  x: 'link(\"A/Cél\")'\n"
                     "views:\n"
                     "  - type: table\n"
                     "    name: Táblázat\n"
                     "    order:\n"
                     "      - file.name\n"),
    "Jegyzet.md": "# J\n\n[[Cél]]\n\n```base\nfilters: file.hasLink(link(\"Cél\"))\n```\n",
    "Csak blokk.md": "```base\nformulas:\n  a: link(\"Cél\")\n```\n",
    "Beágyazó.md": "![[Könyvek.base]] ![[Könyvek.base#Táblázat]]\n",
}


class LinkTobbertelmuAtnevezesTest(Alap):
    """T126 (C29.8): két azonos nevű jegyzet és egy `link("Dup")`-os `.base` — az átnevezés-terv figyelmeztet (nem blokkol),
    hogy a Bases soronként a sor mappájából old fel; a terv `figyelmeztetesek` mezője a felületig jut."""
    FAJLOK = {"A/Dup.md": "# A\n", "B/Dup.md": "# B\n", "Dup.base": 'filters: file.hasLink(link("Dup"))\n'}

    def test_a_terv_figyelmeztet_es_az_atnevezes_megy(self):
        t = self.A.terv("A/Dup.md", "A/Dup2.md")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual([(f["ut"], f["hely"]) for f in t["figyelmeztetesek"]], [("Dup.base", "filters")])
        self.assertIn("többértelmű", t["figyelmeztetesek"][0]["uzenet"])
        self.nevez("A/Dup.md", "A/Dup2.md")                                      # a figyelmeztetés nem blokkol
        self.assertTrue((self.v / "A/Dup2.md").is_file())

    def test_egyertelmu_nev_nem_figyelmeztet(self):
        t = self.A.terv("B/Dup.md", "B/Dup.md".replace("Dup", "Egyedi"))
        self.assertEqual([f["ut"] for f in t["figyelmeztetesek"]], ["Dup.base"])        # a másik Dup megmarad: többértelmű volt
        (self.v / "B/Dup.md").unlink()
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        t = self.A.terv("A/Dup.md", "A/Masik.md")                                  # már csak egy Dup van
        self.assertEqual(t["figyelmeztetesek"], [])


class BazisAtnevezesTest(Alap):
    """C12b, a terv 11. lépése: a `.base` fájlok és a ```base blokkok hivatkozásai az átnevezéssel együtt íródnak
    át (egy terv, egy commit); a névre szűrők csak figyelmeztetnek; a visszavonás bájtra visszaad."""
    FAJLOK = BAZIS_FAJLOK

    def test_link_tipusu_hely_ut_literal_es_figyelmeztetes(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual(sorted(f["ut"] for f in t["fajlok"]),
                         ["Csak blokk.md", "Hivo.md", "Jegyzet.md", "Könyvek.base"])
        self.assertEqual(t["modositott_linkek"], 6)                  # jegyzetlink 2 + base-literál 2 + 1 + 1 (blokkok)
        self.assertEqual(len(t["figyelmeztetesek"]), 1)              # a `file.name == "Cél.md"`
        f = t["figyelmeztetesek"][0]
        self.assertEqual((f["ut"], f["hely"]), ("Könyvek.base", "filters.and[2]"))
        self.assertIn("Cél.md", f["uzenet"])
        r = self.nevez("Cél.md", "Új név.md")
        self.assertEqual(self.olvas("Könyvek.base"), elotte["Könyvek.base"].decode().replace(
            'link("Cél")', 'link("Új név")').replace('file.path == "Cél.md"', 'file.path == "Új név.md"'))
        self.assertEqual(self.olvas("Jegyzet.md"), elotte["Jegyzet.md"].decode().replace("[[Cél]]", "[[Új név]]").replace(
            'link("Cél")', 'link("Új név")'))
        self.assertEqual(self.olvas("Csak blokk.md"), elotte["Csak blokk.md"].decode().replace(
            'link("Cél")', 'link("Új név")'))
        self.assertEqual(self.olvas("Hivo.md"), "A [[Új név]] link.\n")
        self.assertIn('file.name == "Cél.md"', self.olvas("Könyvek.base"))      # a névre szűrőt nem írja át
        self.assertIn('link("A/Cél")', self.olvas("Könyvek.base"))              # a másik fájlra mutató nem érintett
        log = self.repo.log(5)
        self.assertEqual(len(log), 2)                                           # alap + EGY gépi commit
        self.assertIn("Könyvek.base", self.repo.changed_files(log[0].sha))
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)                              # bájtra az eredeti

    def test_elrablas_a_base_ben_es_a_blokkban_is(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "B/Cél.md")                    # az `A/Cél.md` közelebb kerülne a gyökérből
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual(t["figyelmeztetesek"], [])              # a fájl neve nem változik
        r = self.nevez("Cél.md", "B/Cél.md")
        b = self.olvas("Könyvek.base")
        self.assertIn('file.hasLink(link("B/Cél"))', b)
        self.assertIn('file.path == "B/Cél.md"', b)
        self.assertIn('link("A/Cél")', b)
        self.assertIn('link("B/Cél")', self.olvas("Jegyzet.md"))
        self.assertIn('link("B/Cél")', self.olvas("Csak blokk.md"))
        self.assertEqual(self.olvas("Hivo.md"), "A [[B/Cél]] link.\n")
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_masik_fajl_atnevezese_a_base_linkjeit_nem_erinti(self):
        t = self.A.terv("B/Segéd.md", "B/Új segéd.md")
        self.assertTrue(t["ok"])
        self.assertEqual((t["fajlok"], t["figyelmeztetesek"]), ([], []))

    def test_az_a_cel_atnevezese_csak_az_utvonalas_literalt_irja(self):
        elotte = lenyomat(self.v)
        r = self.nevez("A/Cél.md", "A/Új.md")
        self.assertEqual(self.olvas("Könyvek.base"), elotte["Könyvek.base"].decode().replace('link("A/Cél")', 'link("A/Új")'))
        self.assertEqual(self.olvas("Hivo.md"), "A [[Cél]] link.\n")
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_kis_nagybetutol_fuggetlen_literal_is_atirodik(self):
        ir(self.v, "Kicsi.base", 'filters: file.hasLink(link("cél"))\n')
        self.ix.frissit(["Kicsi.base"])
        self.nevez("Cél.md", "Új név.md")
        self.assertEqual(self.olvas("Kicsi.base"), 'filters: file.hasLink(link("Új név"))\n')

    def test_a_base_fajl_atnevezese_a_beagyazasokat_irja(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Könyvek.base", "Olvasmányok.base")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual([f["ut"] for f in t["fajlok"]], ["Beágyazó.md"])
        r = self.nevez("Könyvek.base", "Olvasmányok.base")
        self.assertEqual(self.olvas("Beágyazó.md"), "![[Olvasmányok.base]] ![[Olvasmányok.base#Táblázat]]\n")
        self.assertTrue((self.v / "Olvasmányok.base").is_file())
        self.assertFalse((self.v / "Könyvek.base").exists())
        self.assertEqual((self.v / "Olvasmányok.base").read_bytes(), elotte["Könyvek.base"])
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_a_base_athelyezese_sajat_literaljait_is_javitja(self):
        """Az áthelyezett `.base` forrás-mappája változik: ami előtte a saját mappája közelsége miatt az `X/Közös.md`-re
        oldódott, az az új mappából az `A/Közös.md`-re (rövidebb út) oldódna — az átírás ezt is fogja."""
        ir(self.v, "X/Közös.md", "# X-es\n")
        ir(self.v, "A/Közös.md", "# A-s\n")
        ir(self.v, "Z/z.md", "# Z\n")
        ir(self.v, "X/Más.base", 'formulas:\n  k: link("Közös")\n')
        self.ix.frissit(["X/Közös.md", "A/Közös.md", "Z/z.md", "X/Más.base"])
        elotte = lenyomat(self.v)
        r = self.nevez("X/Más.base", "Z/Más.base")
        self.assertEqual(self.olvas("Z/Más.base"), 'formulas:\n  k: link("X/Közös")\n')
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_a_proba_a_base_hivatkozasokat_is_vizsgalja(self):
        from core.bazis import hivatkozas
        elotte = feloldas.hivatkozasok(self.v, tovabbi=hivatkozas.celok)
        self.assertIn("Könyvek.base", elotte["linkek"])
        self.assertIn("Könyvek.base", elotte["hash"])
        self.assertEqual([c for c, _ in elotte["linkek"]["Könyvek.base"]], ["Cél", "A/Cél"])
        self.assertEqual([c for c, _ in elotte["linkek"]["Jegyzet.md"]], ["Cél", "Cél"])      # jegyzetlink + blokk
        terv = self.A._terv("Cél.md", "Új név.md")
        os.rename(self.v / "Cél.md", self.v / "Új név.md")                      # átírás nélkül: a linkek eltörnek
        utana = feloldas.hivatkozasok(self.v, tovabbi=hivatkozas.celok)
        hibak = atnevezes.Atnevezes._proba(elotte, utana, terv, {})
        self.assertTrue(any("Könyvek.base" in h for h in hibak))

    def test_hibas_base_irasnal_a_proba_visszaallit(self):
        elotte = lenyomat(self.v)
        t = self.A.terv("Cél.md", "Új név.md")
        eredeti = self.A._ir
        self.A._ir = lambda p, b, **k: None if p.name == "Könyvek.base" else eredeti(p, b, **k)     # a base nem íródik át
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertTrue(any("Könyvek.base" in h for h in e.exception.adat["proba_hibak"]))
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(5)), 1)

    def test_a_terv_hash_a_base_valtozasat_is_fogja(self):
        t = self.A.terv("Cél.md", "Új név.md")
        (self.v / "Könyvek.base").write_text('filters: file.hasLink(link("Cél"))\n', encoding="utf-8")
        self.ix.frissit(["Könyvek.base"])
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertTrue(e.exception.adat.get("valtozott"))

    def test_terv_csak_olvas(self):
        elotte = lenyomat(self.v)
        self.A.terv("Cél.md", "Új név.md")
        self.assertEqual(lenyomat(self.v), elotte)


class BazisBlokkoloTest(Alap):
    FAJLOK = dict(BAZIS_FAJLOK, **{
        "Blokkos.base": 'filters: |\n  file.hasLink(link("Cél"))\n',
        "Hajtogatott.md": "```base\nformulas:\n  x: >-\n    link(\"Cél\")\n```\n",
    })

    def test_blokk_skalarban_allo_erintett_hivatkozas_blokkol(self):
        t = self.A.terv("Cél.md", "Új név.md")
        self.assertFalse(t["ok"])
        szoveg = " ".join(t["blokkolok"])
        self.assertIn("Blokkos.base", szoveg)
        self.assertIn("Hajtogatott.md", szoveg)
        self.assertIn("blokk-skalár", szoveg)
        elotte = lenyomat(self.v)
        with self.assertRaises(atnevezes.Hiba) as e:
            self.A.vegrehajt("Cél.md", "Új név.md", t["terv_hash"])
        self.assertEqual(e.exception.kod, 409)
        self.assertEqual(lenyomat(self.v), elotte)

    def test_a_nem_erintett_blokk_skalar_nem_blokkol(self):
        t = self.A.terv("B/Segéd.md", "B/Új segéd.md")
        self.assertTrue(t["ok"], t["blokkolok"])
        t = self.A.terv("A/Cél.md", "A/Új.md")                   # a `link("Cél")` a gyökér `Cél.md`-re old: nem érintett
        self.assertTrue(t["ok"], t["blokkolok"])


BAZIS_MAPPA_FAJLOK = {
    "Tan/a.md": "# A\n",
    "Tan/b.md": "# B\n",
    "Tan/Nézet.base": 'filters: file.inFolder("Tan")\nformulas:\n  x: \'link("a")\'\n',
    "Tanár/c.md": "# C\n",
    "Kívül.base": ("filters:\n"
                   "  or:\n"
                   "    - file.inFolder(\"Tan\")\n"
                   "    - file.folder == \"Tan\"\n"
                   "    - file.path == \"Tan/a.md\"\n"
                   "    - file.inFolder(\"Tanár\")\n"
                   "    - file.path.startsWith(\"Tan/\")\n"
                   "views:\n"
                   "  - type: cards\n"
                   "    name: Kártyák\n"),
    "Hivo.md": "![[Nézet.base]] [[a]] [[b]]\n",
}


class BazisMappaTest(Alap):
    """A `.base`-t tartalmazó mappa is mozog (23. döntés); a mappa-literálok a mappa átnevezésével íródnak át."""
    FAJLOK = BAZIS_MAPPA_FAJLOK

    def test_a_base_es_a_mappaliteralok_a_mappa_atnevezesekor(self):
        elotte = lenyomat_mappakkal(self.v)
        t = self.A.terv("Tan", "Tananyag")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual((t["mappa"], t["mozgo_fajlok"]), (True, 3))
        self.assertEqual(len(t["figyelmeztetesek"]), 1)                          # `file.path.startsWith("Tan/")`
        self.assertEqual(t["figyelmeztetesek"][0]["hely"], "filters.or[4]")
        r = self.nevez("Tan", "Tananyag")
        self.assertEqual(self.olvas("Kívül.base"), (
            "filters:\n  or:\n    - file.inFolder(\"Tananyag\")\n    - file.folder == \"Tananyag\"\n"
            "    - file.path == \"Tananyag/a.md\"\n    - file.inFolder(\"Tanár\")\n"
            "    - file.path.startsWith(\"Tan/\")\nviews:\n  - type: cards\n    name: Kártyák\n"))
        self.assertEqual(self.olvas("Tananyag/Nézet.base"), 'filters: file.inFolder("Tananyag")\nformulas:\n  x: \'link("a")\'\n')
        self.assertEqual(len(self.repo.log(5)), 2)
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)

    def test_a_mappa_athelyezese(self):
        elotte = lenyomat_mappakkal(self.v)
        ir(self.v, "Cel/Hely.md", "# Hely\n")
        self.ix.frissit(["Cel/Hely.md"])
        elotte = lenyomat_mappakkal(self.v)
        r = self.nevez("Tan", "Cel/Tan")
        self.assertIn('file.inFolder("Cel/Tan")', self.olvas("Kívül.base"))
        self.assertIn('file.path == "Cel/Tan/a.md"', self.olvas("Kívül.base"))
        self.assertIn('file.inFolder("Tanár")', self.olvas("Kívül.base"))
        self.assertTrue((self.v / "Cel/Tan/Nézet.base").is_file())
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat_mappakkal(self.v), elotte)

    def test_a_tanar_mappa_nem_erintett(self):
        t = self.A.terv("Tanár", "Tanárok")
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual([f["ut"] for f in t["fajlok"]], ["Kívül.base"])         # a `inFolder("Tanár")`
        self.nevez("Tanár", "Tanárok")
        self.assertIn('file.inFolder("Tanárok")', self.olvas("Kívül.base"))
        self.assertIn('file.inFolder("Tan")', self.olvas("Kívül.base"))

    def test_a_kepet_tartalmazo_mappa_atnevezheto(self):
        ir(self.v, "Tan/kep.png", b"\x89PNG\r\n", "wb")
        self.ix.frissit(["Tan/kep.png"])
        t = self.A.terv("Tan", "Tananyag")
        self.assertTrue(t["ok"], t)
        self.nevez("Tan", "Tananyag")
        self.assertEqual((self.v / "Tananyag/kep.png").read_bytes(), b"\x89PNG\r\n")


if __name__ == "__main__":
    unittest.main()


class MediaAtnevezes(Alap):
    def test_media_linkek_es_bajtok(self):
        elotte = (self.v / "kep.png").read_bytes()
        r = self.nevez("kep.png", "uj.png")
        self.assertEqual((self.v / "uj.png").read_bytes(), elotte)
        self.assertIn("![[uj.png]]", self.olvas("Kep.md"))
        self.assertFalse(r["visszavonhato"])
        self.assertNotIn("uj.png", self.repo.git("ls-files").stdout)
        with self.assertRaises(snapshot.SnapshotError):
            self.repo.undo_commit(r["pillanat"])
        self.nevez("uj.png", "kep.png")
        self.assertEqual((self.v / "kep.png").read_bytes(), elotte)
        self.assertIn("![[kep.png]]", self.olvas("Kep.md"))

    def test_media_hibanal_visszaall(self):
        with mock.patch.object(self.A, "_proba", return_value=["hiba"]):
            with self.assertRaises(atnevezes.Hiba):
                self.nevez("kep.png", "uj.png")
        self.assertTrue((self.v / "kep.png").exists())
        self.assertFalse((self.v / "uj.png").exists())
        self.assertIn("![[kep.png]]", self.olvas("Kep.md"))


class KisNagybetuMediasMappaTest(Alap):
    """CX-003: a médiát tartalmazó mappa csak kis-nagybetűs átnevezése nem bukhat a gitignore-olt média `git add`-ján."""

    def test_medias_mappa_kis_nagybetus_atnevezese(self):
        ir(self.v, "Tan/kep.png", b"\x89PNG\r\n", "wb")
        ir(self.v, "Tan/Jegyzet.md", "# Jegyzet\n![[kep.png]]\n")
        self.repo.commit("kézi mappa", {"Mos-Forras": "kezi"})
        self.ix.frissit(["Tan/kep.png", "Tan/Jegyzet.md"])
        vizsgalat = self.repo.git("--no-literal-pathspecs", "check-ignore", "-q", "--no-index", "Tan/kep.png", check=False)
        self.assertEqual(vizsgalat.returncode, 0,
                        "a próba feltétele: a média gitignore-olt")
        r = self.nevez("Tan", "TAN")
        self.assertIn("TAN", [p.name for p in self.v.iterdir()])
        self.assertEqual((self.v / "TAN/kep.png").read_bytes(), b"\x89PNG\r\n")
        utak = self.repo.git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
        self.assertIn("TAN/Jegyzet.md", utak)
        self.assertNotIn("Tan/Jegyzet.md", utak)
        self.assertFalse(any(u.endswith(".png") for u in utak))
        self.assertIsNotNone(r["pillanat"])
