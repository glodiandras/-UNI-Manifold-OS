"""C26a: `bin/mos osszefoglalas` (`modulok/osszefoglalas/__main__.py`) — csak olvas, a vaultba nem ír, modellt nem hív."""
import argparse
import contextlib
import hashlib
import io
import json
import unittest

from modulok.osszefoglalas import __main__ as cli
from modulok.osszefoglalas import formatum as FM
from tests.helpers import alg_core, ir, tmpdir
from tests.test_osszefoglalas_lanc import A1, A2, A3, CEL, JEGYZET, RP, valasz


def vault_hash(v):
    return {str(p.relative_to(v)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(v.rglob("*")) if p.is_file()}


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, RP, JEGYZET)
        self.elotte = vault_hash(self.v)

    def tearDown(self):
        if not getattr(self, "_irt", False):                      # a parancsok a vaultba nem írnak (a teszt maga igen)
            self.assertEqual(vault_hash(self.v), self.elotte)

    def fut(self, fv, **kw):
        ki, hiba = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(ki), contextlib.redirect_stderr(hiba):
            rc = fv(self.cfg, argparse.Namespace(**kw))
        return rc, ki.getvalue(), hiba.getvalue()

    def forgatokonyv(self, **tartalom):
        p = self.root / "forgatokonyv.json"
        p.write_text(json.dumps(tartalom), encoding="utf-8")
        return str(p)


class ProbaTest(Alap):
    def test_a_lanc_almodellel_a_kimenetre_ir(self):
        rc, ki, hiba = self.fut(cli.proba, forras=RP, forgatokonyv=self.forgatokonyv(hivo=valasz(A1, A2, A3)), max_allitas=None)
        self.assertEqual(rc, 0, hiba)
        e = FM.elemez(ki)
        self.assertEqual(e.hibak, [])
        self.assertEqual(len(e.osszefoglalo.allitasok), 3)
        self.assertEqual(e.osszefoglalo.modell, "almodell")
        self.assertEqual(e.osszefoglalo.allitasok[0].horgony.alcel, "^m-3f2a")          # az index-táblák a core elemzőjéből
        self.assertIn('"uj_horgonyok"', hiba)
        self.assertEqual(sorted(p.name for p in self.v.rglob("*.md")), [RP.rsplit("/", 1)[1]])    # semmi nem íródott

    def test_valaszok_hivasonkent(self):
        rc, ki, _ = self.fut(cli.proba, forras=RP, forgatokonyv=self.forgatokonyv(valaszok=[valasz(A1, A2, A3)]), max_allitas=3)
        self.assertEqual(rc, 0)
        self.assertEqual(len(FM.elemez(ki).osszefoglalo.allitasok), 3)

    def test_kevés_allitas_hibakod(self):
        rc, ki, hiba = self.fut(cli.proba, forras=RP, forgatokonyv=self.forgatokonyv(hivo=valasz(A1)), max_allitas=None)
        self.assertEqual(rc, 1)
        self.assertIn("az összefoglaló nem készült el", hiba)

    def test_hianyzo_forras(self):
        with self.assertRaises(SystemExit):
            self.fut(cli.proba, forras="nincs.md", forgatokonyv=self.forgatokonyv(hivo="[]"), max_allitas=None)


class EllenorizTest(Alap):
    def osszefoglalo(self, forras_md=None):
        rc, ki, _ = self.fut(cli.proba, forras=RP, forgatokonyv=self.forgatokonyv(hivo=valasz(A1, A2, A3)), max_allitas=None)
        self.assertEqual(rc, 0)
        self._irt = True
        ir(self.v, "ATTCHMNTS - summaries/X — összefoglaló.md", ki)
        return "ATTCHMNTS - summaries/X — összefoglaló.md"

    def test_rendben(self):
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet=self.osszefoglalo())
        j = json.loads(ki)
        self.assertEqual((rc, j["hibak"], j["sodrodott"], j["horgony_hianyzik"], j["allitas"]), (0, [], [], [], 3))

    def test_sodrodas_es_horgony(self):
        ut = self.osszefoglalo()
        ir(self.v, RP, JEGYZET.replace("Crassust és Pompeiust", "Crassust és Brutust").replace("^m-3f2a", "^m-ffff").replace("## A Rubicon átlépése", "## A Rubicon"))
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet=ut)
        j = json.loads(ki)
        self.assertEqual(rc, 1)
        self.assertEqual(j["sodrodott"], ["a1"])
        self.assertEqual(j["horgony_hianyzik"], ["a1", "a2"])

    def test_hianyzo_forras_es_hibas_jegyzet(self):
        ut = self.osszefoglalo()
        (self.v / RP).unlink()
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet=ut)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(ki)["forras_hianyzik"], [CEL])
        ir(self.v, "rossz.md", "---\nSource: []\n---\n")
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet="rossz.md")
        self.assertEqual(rc, 1)
        self.assertIn("forras_hiany", ki)


class KontextusTest(Alap):
    def test_csomag_a_kimenetre_azonositokkal(self):
        rc, ki, hiba = self.fut(cli.kontextus, jegyzetek=[RP], max_karakter=None, kerdes="Miről szól?", valasz=None)
        self.assertEqual(rc, 0)
        self.assertIn("=== J1 · A polgárháborúk kora és Caesar", ki)
        self.assertNotIn("T03 - Az ókori Róma", ki)
        self.assertEqual(json.loads(hiba)["azonositok"], {"J1": RP})

    def test_valasz_feldolgozasa(self):
        p = self.root / "valasz.json"
        p.write_text(valasz({"allitas": A1["allitas"], "forras": "J1", "idezet": A1["idezet"]},
                            {"allitas": "Kitalált állítás a jegyzeten kívülről.", "forras": "J1", "idezet": "Kitalált idézet a jegyzeten kívülről, nincs benne"}),
                     encoding="utf-8")
        rc, ki, hiba = self.fut(cli.kontextus, jegyzetek=[RP], max_karakter=None, kerdes=None, valasz=str(p))
        self.assertEqual(rc, 0, hiba)
        self.assertTrue(ki.startswith("## Állítások"))
        self.assertIn(f"[[{CEL}#^m-3f2a|forrás]]", ki)
        self.assertEqual(json.loads(hiba)["elvetett"][0]["ok"], "idezet")

    def test_semmi_nem_megy_at(self):
        p = self.root / "valasz.json"
        p.write_text("Nem tudok segíteni.", encoding="utf-8")
        rc, ki, hiba = self.fut(cli.kontextus, jegyzetek=[RP], max_karakter=None, kerdes=None, valasz=str(p))
        self.assertEqual((rc, ki), (1, ""))
        self.assertIn("egyetlen állítás sem ment át", hiba)

    def test_nem_fero_keret(self):
        rc, ki, hiba = self.fut(cli.kontextus, jegyzetek=[RP], max_karakter=200, kerdes=None, valasz=None)
        self.assertEqual(rc, 1)
        self.assertIn("HIBA", hiba)


if __name__ == "__main__":
    unittest.main()
