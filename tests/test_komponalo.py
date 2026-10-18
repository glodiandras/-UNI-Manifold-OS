"""Note composer (12-templates-10 / 12-templates-11): kivonás és összefűzés álvaulton, valódi pillanatkép-tárolóval.

Amit ezek a tesztek őriznek:
  - a kivonás a célt írja (új jegyzet vagy hash-védett hozzáfűzés), a forráshoz soha nem nyúl; névütközés, mentetlen cél, elavult
    hash, hiányzó sablon: semmi nem íródik / a cél érintetlen;
  - az összefűzés terve csak olvas; a linkek (wiki, alias, `#fejezet`, beágyazás, md, canvas) a célra íródnak át; a frontmatter a
    Tulajdonságok szabályai szerint egyesül; a forrás a Kukába kerül (nem törlődik);
  - a végrehajtás minden lépése egy `KOMP-…` körben van, a `kor` visszavonása (git revert) bájtra visszaadja az eredetit;
  - hibás írás, elavult terv, mentetlen dokumentum, hiányzó pillanatkép-tároló: a vault nem változik.
"""
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import atnevezes, csatolmany, komponalo, snapshot, vaultio
from core.tulajdonsagok import Tulajdonsagok
from core.utvonalak import HttpError
from tests.helpers import ir, tmpdir
from tests.index_segedek import index_indit
from tests.vaultgyar import alg_semleges

ALAP = {
    "Welcome.md": "# Welcome\n\nA first note.\n",
    "Projects/Plan.md": "# Plan\n\nSketch.\n",
    "A.md": "---\ntags: [alpha]\nstatus: draft\n---\n# A\nA body\n",
    "B.md": "---\ntags: [beta]\nstatus: done\nextra: 1\n---\n# B\nB body links [[A]] and [[B]].\n\n## Head\ntext ^blk\n",
    "Linker.md": "See [[B]], [[B|alias]], [[B#Head]], [[B#^blk]], ![[B]] and [md](B.md). `[[B]]`\n",
    "Deep/Other.md": "[[B]] and [[A]]\n",
    "Board.canvas": '{"nodes": [{"id": "1", "type": "file", "file": "B.md"}, {"id": "2", "type": "text", "text": "[[B]] here"}], "edges": []}\n',
}


def lenyomat(gyoker: Path) -> dict:
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = [m for m in mappak if m not in (".obsidian", ".manifold")]
        for f in fajlok:
            p = Path(d) / f
            ki[p.relative_to(gyoker).as_posix()] = p.read_bytes()
    return ki


class Alap(unittest.TestCase):
    FAJLOK = ALAP

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)
        for rp, t in self.FAJLOK.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.V = vaultio.Vault(self.cfg)
        self.mentetlen: set[str] = set()
        self.A = atnevezes.Atnevezes(self.cfg, self.V, self.ix, mentetlen=lambda: self.mentetlen)
        self.app = SimpleNamespace(cfg=self.cfg, vault=self.V, index=self.ix, atnevezes=self.A,
                                   tulajdonsagok=Tulajdonsagok(self.cfg, self.ix))
        self.kuka = Path(self._t.name) / "alkuka"
        self.kuka.mkdir()
        self.kukaba = lambda app, ut: csatolmany.kuka(app, {"ut": ut, "megerosit": True}, lambda p: p.rename(self.kuka / p.name))

    def olvas(self, rp):
        return (self.v / rp).read_text(encoding="utf-8")

    def sablon(self, ut, szoveg):
        ir(self.v, ut, szoveg)
        self.cfg.data.setdefault("beallitasok", {}).setdefault("fajlok", {})["kivonas_sablon"] = ut


class KivonasUjTest(Alap):
    def kivon(self, **cel):
        return komponalo.kivon(self.app, {"forras": "Welcome.md", "szoveg": "Extracted words", "cel": {"mod": "uj", **cel}})

    def test_uj_jegyzet_az_alap_helyen_es_a_forras_erintetlen(self):
        elotte = self.olvas("Welcome.md")
        r = self.kivon(nev="Idea")
        self.assertEqual((r["ut"], r["nev"], r["letrejott"]), ("Idea.md", "Idea", True))
        self.assertEqual(self.olvas("Idea.md"), "Extracted words\n")
        self.assertEqual(self.olvas("Welcome.md"), elotte)
        self.assertTrue(r["pillanat"])

    def test_kifejezett_mappa(self):
        r = self.kivon(nev="Idea", mappa="Projects")
        self.assertEqual(r["ut"], "Projects/Idea.md")
        self.assertEqual(self.olvas("Projects/Idea.md"), "Extracted words\n")

    def test_az_uj_jegyzetek_beallitott_helye_a_forras_mappaja(self):
        self.cfg.data.setdefault("beallitasok", {}).setdefault("fajlok", {})["uj_mappa"] = "."
        self.cfg.retegek["beallitasok.fajlok.uj_mappa"] = "munkater"
        r = komponalo.kivon(self.app, {"forras": "Projects/Plan.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "Side"}})
        self.assertEqual(r["ut"], "Projects/Side.md")

    def test_nevutkozes_semmit_nem_ir(self):
        elotte = lenyomat(self.v)
        for nev in ("Welcome", "welcome", "Welcome.md"):
            with self.assertRaises(vaultio.Invalid, msg=nev):
                self.kivon(nev=nev)
        self.assertEqual(lenyomat(self.v), elotte)

    def test_hibas_kerelem(self):
        elotte = lenyomat(self.v)
        for d in ({"forras": "Welcome.md", "szoveg": "   ", "cel": {"mod": "uj", "nev": "X"}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "?"}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "uj", "nev": " "}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "A:B"}},
                  {"forras": "Nincs.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "X"}},
                  {"forras": "kep.png", "szoveg": "x", "cel": {"mod": "uj", "nev": "X"}},
                  {"forras": "../kint.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "X"}},
                  {"forras": "Welcome.md", "szoveg": 5, "cel": {"mod": "uj", "nev": "X"}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "X", "mappa": 3}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "X", "mappa": "../kint"}},
                  {"forras": "Welcome.md", "szoveg": "x", "cel": {"mod": "uj", "nev": "X", "mappa": "/etc"}},
                  [], None):
            with self.assertRaises((HttpError, vaultio.Invalid), msg=str(d)):
                komponalo.kivon(self.app, d)
        self.assertEqual(lenyomat(self.v), elotte)

    def test_visszavonas_a_pillanatkepbol(self):
        elotte = lenyomat(self.v)
        r = self.kivon(nev="Idea")
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)


class KivonasMeglevoTest(Alap):
    def kivon(self, ut="Projects/Plan.md", hely="veg", szoveg="Moved text"):
        return komponalo.kivon(self.app, {"forras": "Welcome.md", "szoveg": szoveg, "cel": {"mod": "meglevo", "ut": ut, "hely": hely}})

    def test_a_vegere(self):
        r = self.kivon()
        self.assertEqual((r["ut"], r["letrejott"]), ("Projects/Plan.md", False))
        self.assertEqual(self.olvas("Projects/Plan.md"), "# Plan\n\nSketch.\n\nMoved text\n")

    def test_az_elejere_a_frontmatter_utan(self):
        self.kivon(ut="A.md", hely="eleje")
        self.assertEqual(self.olvas("A.md"), "---\ntags: [alpha]\nstatus: draft\n---\nMoved text\n\n# A\nA body\n")

    def test_az_elejere_frontmatter_nelkul(self):
        self.kivon(hely="eleje")
        self.assertEqual(self.olvas("Projects/Plan.md"), "Moved text\n\n# Plan\n\nSketch.\n")

    def test_ures_cel(self):
        ir(self.v, "Empty.md", "")
        self.kivon(ut="Empty.md")
        self.assertEqual(self.olvas("Empty.md"), "Moved text\n")

    def test_crlf_cel_crlf_marad(self):
        ir(self.v, "Win.md", b"line one\r\nline two\r\n", "wb")
        self.kivon(ut="Win.md", szoveg="a\nb")
        self.assertEqual((self.v / "Win.md").read_bytes(), b"line one\r\nline two\r\n\r\na\r\nb\r\n")

    def test_azonos_jegyzet_nem_cel(self):
        with self.assertRaises(HttpError) as e:
            self.kivon(ut="welcome.md")
        self.assertEqual((e.exception.code, e.exception.kod), (400, "komponalo.azonos"))

    def test_mentetlen_cel_409_es_semmi_nem_valtozik(self):
        self.mentetlen = {"Projects/Plan.md"}
        elotte = lenyomat(self.v)
        with self.assertRaises(HttpError) as e:
            self.kivon()
        self.assertEqual((e.exception.code, e.exception.kod), (409, "komponalo.mentetlen"))
        self.assertEqual(lenyomat(self.v), elotte)

    def test_elavult_hash_nem_ir_felul(self):
        eredeti = self.V.read

        def read(rp):
            r = eredeti(rp)
            ir(self.v, "Projects/Plan.md", "externally edited\n")          # közben megváltozik
            return r
        self.V.read = read
        with self.assertRaises(vaultio.Conflict):
            self.kivon()
        self.assertEqual(self.olvas("Projects/Plan.md"), "externally edited\n")

    def test_nem_jegyzet_cel_es_hianyzo_cel(self):
        ir(self.v, "kep.png", b"\x89PNG", "wb")
        for ut in ("kep.png", "Nincs.md", "../kint.md"):
            with self.assertRaises((HttpError, vaultio.Invalid), msg=ut):
                self.kivon(ut=ut)

    def test_hibas_hely(self):
        with self.assertRaises(HttpError) as e:
            self.kivon(hely="kozepe")
        self.assertEqual(e.exception.kod, "komponalo.hely")

    def test_a_cel_pillanatkepe_visszavonhato(self):
        elotte = lenyomat(self.v)
        r = self.kivon()
        self.assertTrue(r["pillanat"])
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(lenyomat(self.v), elotte)


class KivonasSablonTest(Alap):
    def kivon(self, **cel):
        return komponalo.kivon(self.app, {"forras": "Projects/Plan.md", "szoveg": "Body {{date}} {{title}}", "cel": {"mod": "uj", **cel}})

    def test_valtozok_egy_menetben(self):
        self.sablon("Templates/Extract.md", "From [[{{fromTitle}}]] to {{newTitle}} ({{date:YYYY}}):\n{{content}}\n{{unknown}}\n")
        self.kivon(nev="Side")
        t = self.olvas("Side.md")
        self.assertRegex(t, r"^From \[\[Plan\]\] to Side \(\d{4}\):\nBody \{\{date\}\} \{\{title\}\}\n\{\{unknown\}\}\n$")

    def test_a_sablon_a_meglevo_celnal_is_alkalmazodik(self):
        self.sablon("Templates/Extract.md", "> {{content}}\n> from {{fromTitle}}")
        komponalo.kivon(self.app, {"forras": "Welcome.md", "szoveg": "quoted", "cel": {"mod": "meglevo", "ut": "A.md", "hely": "veg"}})
        self.assertTrue(self.olvas("A.md").endswith("A body\n\n> quoted\n> from Welcome\n"))

    def test_hianyzo_sablon_404_es_semmi_nem_jon_letre(self):
        self.cfg.data.setdefault("beallitasok", {}).setdefault("fajlok", {})["kivonas_sablon"] = "Templates/Nincs"
        elotte = lenyomat(self.v)
        with self.assertRaises(HttpError) as e:
            self.kivon(nev="Side")
        self.assertEqual((e.exception.code, e.exception.kod), (404, "komponalo.sablon_nincs"))
        self.assertEqual(lenyomat(self.v), elotte)


class OsszefuzesTervTest(Alap):
    def terv(self, forras="B.md", cel="A.md", hely="veg"):
        return komponalo.osszefuz_terv(self.app, forras, cel, hely)

    def test_a_terv_csak_olvas(self):
        elotte = lenyomat(self.v)
        t = self.terv()
        self.assertTrue(t["ok"], t["blokkolok"])
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertEqual(len(self.repo.log(50)), 1)                                   # nem keletkezett commit

    def test_a_terv_tartalma(self):
        t = self.terv()
        self.assertEqual((t["forras"], t["cel"], t["hely"], t["kukaba"]), ("B.md", "A.md", "veg", "B.md"))
        self.assertEqual(sorted(f["ut"] for f in t["fajlok"]), ["Board.canvas", "Deep/Other.md", "Linker.md"])        # a cél és a forrás nem
        # A.md saját `[[B]]` hivatkozása nincs (csak B hivatkozik A-ra); a Linker 6 linkje, a Deep/Other 1, a Board 2
        db = {f["ut"]: f["darab"] for f in t["fajlok"]}
        self.assertEqual((db["Linker.md"], db["Deep/Other.md"], db["Board.canvas"]), (6, 1, 2))
        self.assertEqual(t["modositott_linkek"], sum(db.values()))
        self.assertEqual(t["tulajdonsagok"]["hozzaadva"], ["extra"])
        self.assertEqual(t["tulajdonsagok"]["egyesitve"], ["tags"])
        self.assertEqual(t["tulajdonsagok"]["megmaradt"], ["status"])
        self.assertEqual(t["figyelmeztetesek"][0], {"kod": "beagyazas", "db": 1})
        self.assertIn({"kod": "megmaradt_ertek", "kulcsok": ["status"]}, t["figyelmeztetesek"])

    def test_ugyanaz_a_terv_ugyanazt_a_hasht_adja_es_a_valtozas_megvaltoztatja(self):
        h = self.terv()["terv_hash"]
        self.assertEqual(self.terv()["terv_hash"], h)
        ir(self.v, "Deep/Other.md", "[[B]] and [[A]] edited\n")
        for _ in range(100):                                   # az index még nem érte utol → blokkoló; várjuk meg
            t = self.terv()
            if t["ok"]:
                break
            import time
            time.sleep(0.05)
        self.assertNotEqual(t["terv_hash"], h)

    def test_blokkolok(self):
        self.mentetlen = {"B.md"}
        t = self.terv()
        self.assertFalse(t["ok"])
        self.assertIn("Unsaved changes", t["blokkolok"][0])
        self.mentetlen = {"A.md"}
        self.assertFalse(self.terv()["ok"])

    def test_alaki_hibak(self):
        for forras, cel in (("A.md", "a.md"), ("A.md", "A.md"), ("Nincs.md", "A.md"), ("A.md", "Nincs.md"),
                            ("Board.canvas", "A.md"), ("A.md", "Board.canvas"), ("../x.md", "A.md"), (None, "A.md")):
            with self.assertRaises((HttpError, vaultio.Invalid), msg=f"{forras} {cel}"):
                self.terv(forras, cel)
        with self.assertRaises(HttpError) as e:
            self.terv(hely="kozepe")
        self.assertEqual(e.exception.kod, "komponalo.hely")

    def test_ervenytelen_utf8_blokkol(self):
        ir(self.v, "Bad.md", b"abc \xff\n", "wb")
        t = self.terv("Bad.md", "A.md")
        self.assertFalse(t["ok"])
        self.assertIn("UTF-8", t["blokkolok"][0])

    def test_hibas_cel_frontmatter_blokkol(self):
        ir(self.v, "Broken.md", "---\ntags: [a\nstatus: x: y\n---\nbody\n")
        t = self.terv("B.md", "Broken.md")
        self.assertFalse(t["ok"])
        self.assertIn("invalid frontmatter", " ".join(t["blokkolok"]))


class OsszefuzesVegrehajtasTest(Alap):
    def merge(self, forras="B.md", cel="A.md", hely="veg", **kw):
        t = komponalo.osszefuz_terv(self.app, forras, cel, hely)
        self.assertTrue(t["ok"], t["blokkolok"])
        return komponalo.osszefuz_vegrehajt(self.app, forras, cel, hely, t["terv_hash"], kukaba=kw.get("kukaba", self.kukaba))

    def test_vege_a_celnak_linkek_atirva_forras_a_kukaban(self):
        r = self.merge()
        self.assertTrue(r["ok"] and r["forras_kukaban"] and r["visszavonhato"])
        self.assertEqual(r["modositott"], ["A.md", "Board.canvas", "Deep/Other.md", "Linker.md"])
        self.assertEqual(self.olvas("A.md"), (
            "---\ntags:\n  - alpha\n  - beta\nstatus: draft\nextra: 1\n---\n# A\nA body\n\n"
            "# B\nB body links [[A]] and [[A]].\n\n## Head\ntext ^blk\n"))
        self.assertFalse((self.v / "B.md").exists())
        self.assertTrue((self.kuka / "B.md").is_file())                               # a Kukában: nem végleges törlés
        self.assertEqual(self.olvas("Linker.md"), "See [[A]], [[A|alias]], [[A#Head]], [[A#^blk]], ![[A]] and [md](A.md). `[[B]]`\n")
        self.assertEqual(self.olvas("Deep/Other.md"), "[[A]] and [[A]]\n")
        self.assertIn('"file": "A.md"', self.olvas("Board.canvas"))
        self.assertIn("[[A]] here", self.olvas("Board.canvas"))

    def test_a_forras_onhivatkozasa_a_celra_mutat(self):
        self.merge()
        self.assertNotIn("[[B]]", self.olvas("A.md"))

    def test_eleje(self):
        self.merge(hely="eleje")
        t = self.olvas("A.md")
        self.assertTrue(t.startswith("---\ntags:\n  - alpha\n  - beta\nstatus: draft\nextra: 1\n---\n# B\nB body links"), t)
        self.assertTrue(t.endswith("text ^blk\n\n# A\nA body\n"))

    def test_frontmatter_nelkuli_cel_megkapja_a_forrasetet(self):
        self.merge(forras="B.md", cel="Welcome.md")
        t = self.olvas("Welcome.md")
        self.assertTrue(t.startswith("---\ntags:\n  - beta\nstatus: done\nextra: 1\n---\n# Welcome\n\nA first note.\n\n# B\n"), t)

    def test_forras_frontmatter_nelkul(self):
        self.merge(forras="Welcome.md", cel="A.md")
        self.assertEqual(self.olvas("A.md"), "---\ntags: [alpha]\nstatus: draft\n---\n# A\nA body\n\n# Welcome\n\nA first note.\n")

    def test_crlf_cel(self):
        ir(self.v, "Win.md", b"---\r\ntags: [w]\r\n---\r\nline\r\n", "wb")
        self.merge(forras="Welcome.md", cel="Win.md")
        b = (self.v / "Win.md").read_bytes()
        self.assertTrue(b.endswith(b"line\r\n\r\n# Welcome\r\n\r\nA first note.\r\n"), b)
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"))                              # nincs magányos LF
        self.assertNotIn(b"\r\r", b)

    def test_visszavonas_korre_bajtra_visszaadja_az_eredetit(self):
        elotte = lenyomat(self.v)
        r = self.merge()
        self.assertNotEqual(lenyomat(self.v), elotte)
        commitok = self.repo.kor_commitok(r["kor"])
        self.assertEqual(len(commitok), 2)                                           # az írások + a Kukába tétel commitja
        self.assertEqual(sorted({c.trailers["Mos-Kor"] for c in commitok}), [r["kor"]])
        self.repo.undo_run(r["kor"])
        visszaallitott = lenyomat(self.v)
        self.assertEqual(visszaallitott, elotte)                                     # a B.md is visszajött (a Kukában a másolat is megvan)
        self.assertTrue((self.kuka / "B.md").is_file())

    def test_a_kor_elotagja_komp(self):
        self.assertTrue(self.merge()["kor"].startswith("KOMP-"))

    def test_kuka_hiba_nem_vonja_vissza_az_osszefuzest(self):
        def rossz(app, ut):
            raise HttpError(503, "Trash unavailable", kod="kuka_hiba")
        r = self.merge(kukaba=rossz)
        self.assertEqual((r["ok"], r["forras_kukaban"]), (True, False))
        self.assertIn("Trash unavailable", r["forras_hiba"])
        self.assertTrue((self.v / "B.md").is_file())                                  # a forrás megvan, a cél is összefűzött
        self.assertIn("B body", self.olvas("A.md"))
        self.assertIsNone(r["torles_pillanat"])
        self.repo.undo_run(r["kor"])
        self.assertEqual(self.olvas("A.md"), ALAP["A.md"])

    def test_elavult_terv_409_semmi_nem_valtozik(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        ir(self.v, "A.md", self.olvas("A.md") + "edited meanwhile\n")
        elotte = lenyomat(self.v)
        with self.assertRaises(HttpError) as e:
            komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(e.exception.code, 409)
        self.assertIn(e.exception.kod, ("komponalo.terv_valtozott", "komponalo.blokkolt"))
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertFalse(list(self.kuka.iterdir()))

    def test_hibas_vagy_hianyzo_hash(self):
        for h in (None, "", "0" * 40, 5):
            with self.assertRaises(HttpError, msg=str(h)) as e:
                komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", h, kukaba=self.kukaba)
            self.assertEqual(e.exception.kod, "komponalo.terv_valtozott")
        self.assertTrue((self.v / "B.md").is_file())

    def test_irasi_hiba_visszaallit_es_nem_kukaz(self):
        eredeti = self.A._ir
        hivasok = []

        def ir_(p, b, regi=None):
            hivasok.append(p.name)
            if len(hivasok) == 3:
                raise OSError(5, "disk error")
            return eredeti(p, b, regi=regi)
        elotte = lenyomat(self.v)
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        with mock.patch.object(self.A, "_ir", ir_):
            with self.assertRaises(OSError):
                komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertGreaterEqual(len(hivasok), 3)                                      # a 3. hívás bukott, a visszaállítás is `_ir`-t hív
        self.assertEqual(lenyomat(self.v), elotte)                                    # a már megírt A.md és az első linkelő is visszaállt
        self.assertFalse(list(self.kuka.iterdir()))
        self.assertFalse([c for c in self.repo.log(20) if c.trailers.get("Mos-Kor", "").startswith("KOMP")])

    def test_mentetlen_dokumentum_blokkol_vegrehajtaskor_is(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        self.mentetlen = {"A.md"}
        with self.assertRaises(HttpError) as e:
            komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual((e.exception.code, e.exception.kod), (409, "komponalo.blokkolt"))
        self.assertTrue((self.v / "B.md").is_file())

    def test_pillanatkep_nelkul_nem_fuz_ossze(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        with mock.patch.object(self.V, "repo", return_value=None):
            with self.assertRaises(HttpError) as e:
                komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(e.exception.kod, "komponalo.nincs_pillanatkep")
        self.assertEqual(self.olvas("A.md"), ALAP["A.md"])

    def test_foglalt_vault_iro_feladat(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        self.A.busy = lambda: True
        with self.assertRaises(HttpError) as e:
            komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(e.exception.kod, "komponalo.foglalt")

    def test_az_index_a_vegrehajtas_utan_a_celra_old(self):
        self.merge()
        import time
        for _ in range(100):
            if not any(r["cel_nyers"] == "B" for r in self.ix.link_sorok()):
                break
            time.sleep(0.05)
        self.assertFalse(any(r["cel_nyers"] == "B" and r["forras"] in ("Linker.md", "Deep/Other.md") for r in self.ix.link_sorok()))


class OsszefuzesCelHivatkozikTest(Alap):
    """A cél maga hivatkozik a forrásra (és a forrás a célra): a két átírás egyetlen írássá olvad, a végeredmény önhivatkozás."""
    FAJLOK = {"A.md": "See [[B]] and [[B#Part]].\n", "B.md": "# B\n\n## Part\nbody [[A]]\n", "C.md": "[[B]]\n"}

    def test_a_cel_sajat_linkje_es_a_forras_visszalinkje(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "veg")
        self.assertTrue(t["ok"], t["blokkolok"])
        komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(self.olvas("A.md"), "See [[A]] and [[A#Part]].\n\n# B\n\n## Part\nbody [[A]]\n")
        self.assertEqual(self.olvas("C.md"), "[[A]]\n")
        self.assertFalse((self.v / "B.md").exists())

    def test_nincs_frontmatter_egyik_oldalon_sem(self):
        t = komponalo.osszefuz_terv(self.app, "B.md", "A.md", "eleje")
        self.assertEqual(t["tulajdonsagok"], {})
        komponalo.osszefuz_vegrehajt(self.app, "B.md", "A.md", "eleje", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(self.olvas("A.md"), "# B\n\n## Part\nbody [[A]]\n\nSee [[A]] and [[A#Part]].\n")


class UresForrasTest(Alap):
    FAJLOK = {"A.md": "---\ntags: [a]\n---\nkeep\n", "Empty.md": "---\nextra: 2\n---\n"}

    def test_ures_torzs_csak_a_frontmattert_viszi(self):
        t = komponalo.osszefuz_terv(self.app, "Empty.md", "A.md", "veg")
        self.assertTrue(t["ok"], t["blokkolok"])
        komponalo.osszefuz_vegrehajt(self.app, "Empty.md", "A.md", "veg", t["terv_hash"], kukaba=self.kukaba)
        self.assertEqual(self.olvas("A.md"), "---\ntags: [a]\nextra: 2\n---\nkeep\n")


class UtvonalakTest(unittest.TestCase):
    def test_a_vegpontok_regisztraltak(self):
        class R:
            def __init__(self):
                self.utak = []

            def post(self, ut, kezelo):
                self.utak.append(("POST", ut))
        r = R()
        komponalo.utvonalak(r)
        self.assertEqual(r.utak, [("POST", "/api/komponalo/kivon"), ("POST", "/api/komponalo/osszefuz/terv"),
                                  ("POST", "/api/komponalo/osszefuz")])


if __name__ == "__main__":
    unittest.main()
