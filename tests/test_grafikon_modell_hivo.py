"""C35b: a ```plot modell-ágának worker-kötése (`modulok/grafikon/modell_hivo.py`) álworkerrel — modellt nem tölt. Lusta kapcsolat;
D9: a `grafikon` router-feladat kalibrált modellje (éles) vagy a kifejezett modell (próba); a nem elérhető modell
`ModellNemElerheto`, a jegyzet később újra sorra kerül; a gépi írás jele a worker válaszából jön."""
import unittest
from unittest import mock

from core.modell import kliens as valodi_kliens
from tests.grafikon_segedek import F, HamisHomokozo, felismero
from tests.helpers import alg_core, tmpdir
from tests import test_grafikon_modell_ag as MAT

from grafikon import beiras as B  # noqa: E402
from grafikon import modell_ag as MA  # noqa: E402
from grafikon import modell_hivo as MH  # noqa: E402

BLOKK = "```plot\nx in [-4, 4]\ny in [-6, 6]\ny = 1/x\n```"


class AlKliens:
    """A `core.modell.kliens` álarca: a worker címe, a router-döntés és a chat-válasz."""
    KliensHiba = valodi_kliens.KliensHiba

    def __init__(self, router=None, valasz=BLOKK, nincs_worker=False, chat_hiba=None, modell="qwen35_4b"):
        self.router = router if router is not None else {"modell": modell, "var_tavolra": False}
        self.valasz, self.nincs_worker, self.chat_hiba, self.modell = valasz, nincs_worker, chat_hiba, modell
        self.hivasok: list = []

    def url(self, cfg=None):
        if self.nincs_worker:
            raise self.KliensHiba(503, "nem fut modell-worker")
        return "http://worker"

    def keres(self, u, ut, body=None, timeout=None):
        self.hivasok.append(("keres", ut, body))
        if isinstance(self.router, Exception):
            raise self.router
        return self.router

    def chat(self, u, messages, feladat=None, modell=None, mod=None, **kw):
        self.hivasok.append(("chat", feladat, modell, mod, dict(kw), messages))
        if self.chat_hiba:
            raise self.chat_hiba
        return {"choices": [{"message": {"content": self.valasz}}], "feladat": feladat, "modell": modell or self.modell,
                "proba": modell is not None}


class Hivo(unittest.TestCase):
    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)

    def hivo(self, kl, **kw):
        return MH.Hivo(self.cfg, mod="auto", kliens=kl, **kw)

    def test_lusta_epites_nem_nyul_a_workerhez(self):
        kl = AlKliens()
        self.hivo(kl)
        self.assertEqual(kl.hivasok, [])

    def test_kalibralt_modell_eles_jellel(self):
        kl = AlKliens()
        h = self.hivo(kl)
        self.assertEqual(h("prompt", 400), BLOKK)
        self.assertEqual(kl.hivasok[0][:3], ("keres", "/router/valaszt", {"feladat": "grafikon"}))
        _, feladat, modell, mod, kw, uzenetek = kl.hivasok[1]
        self.assertEqual((feladat, modell, mod), ("grafikon", None, "auto"))             # a worker routere választ, nem a hívó
        self.assertGreaterEqual(kw["max_tokens"], 400)
        self.assertEqual(uzenetek, [{"role": "user", "content": "prompt"}])
        self.assertTrue(h.kalibralt)
        self.assertEqual(h.jel, {"feladat": "grafikon", "modell": "qwen35_4b", "proba": False})
        h("masodik", 400)
        self.assertEqual([x[0] for x in kl.hivasok], ["keres", "chat", "chat"])           # a router-döntés egyszer

    def test_gondolkodo_modell_kerete_a_regiszterbol(self):
        """A mért kérés beállítása az éles: a gondolkodó modell token-kerete a kéréshez adódik."""
        kl = AlKliens(router={"modell": "ministral3_8b_reasoning"}, modell="ministral3_8b_reasoning")
        self.hivo(kl)("p", 400)
        h = self.hivo(AlKliens(router={"modell": "ministral3_8b_reasoning"}, modell="ministral3_8b_reasoning"))
        h("p", 400)
        self.assertGreater(h._kliens.hivasok[1][4]["max_tokens"], 400)

    def test_kifejezett_modell_proba(self):
        kl = AlKliens()
        h = self.hivo(kl, modell="qwen35_9b")
        h("p", 400)
        self.assertEqual([x[0] for x in kl.hivasok], ["chat"])                            # router-döntés nincs
        self.assertEqual(kl.hivasok[0][2], "qwen35_9b")
        self.assertFalse(h.kalibralt)
        self.assertEqual(h.jel["proba"], True)

    def test_ismeretlen_modell_nem_elerheto(self):
        with self.assertRaises(MA.ModellNemElerheto):
            self.hivo(AlKliens(), modell="nincs-ilyen")("p", 400)

    def test_nem_elerheto_esetek(self):
        for kl in (AlKliens(nincs_worker=True),
                   AlKliens(router=valodi_kliens.KliensHiba(409, "nincs kalibrált modell")),
                   AlKliens(router=valodi_kliens.KliensHiba(500, "router hiba")),
                   AlKliens(router={"modell": None, "var_tavolra": True, "indok": "a távol-keretbe fér"}),
                   AlKliens(chat_hiba=valodi_kliens.KliensHiba(503, "keret")),
                   AlKliens(chat_hiba=valodi_kliens.KliensHiba(409, "nincs_kalibralt"))):
            with self.assertRaises(MA.ModellNemElerheto):
                self.hivo(kl)("p", 400)
        with self.assertRaises(valodi_kliens.KliensHiba):                                  # a kérés hibája (400) nem „nem elérhető”
            self.hivo(AlKliens(chat_hiba=valodi_kliens.KliensHiba(400, "rossz kérés")))("p", 400)

    def test_javasol_modell_var_allapot(self):
        j = {"bizonyossag": "bizonytalan", "forras_keplet": r"y = \frac{1}{x}", "ok": "pólus"}
        e = MA.javasol(j, self.hivo(AlKliens(nincs_worker=True)), homokozo=HamisHomokozo())
        self.assertEqual(e["allapot"], "modell_var")


class BeiroHivoval(MAT.Beirasa):
    """A lusta hívó a `Beiro`-ban: a kalibráltságot és a gépi-írás jelet a hívás UTÁN olvassa."""

    def beiro_hivoval(self, kl):
        h = MH.Hivo(self.cfg, mod="auto", kliens=kl)
        return B.Beiro(self.kliens, felismero, self.tilt, self.napl, modell=h, homokozo=HamisHomokozo(), varakozas_mp=0.1), h

    def test_kalibralt_hivo_eles_blokk_a_worker_jelevel(self):
        from core import gepi_iras
        from core.modell import kalibracio
        kl = AlKliens()
        b, h = self.beiro_hivoval(kl)
        kuldott = []
        eredeti = self.kliens.ir

        def ir_(*a, **k):
            kuldott.append((k.get("proba"), k.get("modell")))
            return eredeti(*a, **k)
        self.kliens.ir = ir_
        with mock.patch.object(gepi_iras.GepiIras, "_modell_feladat", lambda self, k: None), \
                mock.patch.object(kalibracio.Tabla, "kalibralt_sorrend",
                                  lambda self, feladat, verziok=None: [{"modell": "qwen35_4b"}] if feladat == "grafikon" else []):
            r = b.jegyzet(MAT.UT)
        self.assertEqual(r["allapot"], "kesz", r)
        self.assertEqual(r["fuggoben"], 0)
        self.assertEqual(sorted(x.abra.elemek[0].kifejezes for x in F.blokkok(self.olvas())), ["1/x", "x^2"])
        self.assertEqual(kuldott, [(False, {"feladat": "grafikon", "modell": "qwen35_4b", "proba": False})])
        self.assertEqual(r["tartalom"], self.JEGY)                                         # a feldolgozott (írás előtti) változat

    def test_kifejezett_modell_csak_proba(self):
        kl = AlKliens()
        h = MH.Hivo(self.cfg, modell="qwen35_9b", mod="auto", kliens=kl)
        b = B.Beiro(self.kliens, felismero, self.tilt, self.napl, modell=h, homokozo=HamisHomokozo(), varakozas_mp=0.1, proba=True)
        proba_hivasok = []
        eredeti = self.kliens.ir

        def ir_(*a, **k):
            proba_hivasok.append(k.get("proba"))
            return {"ok": True, "valtozas": True, "sha": "y" * 40, "proba": True} if k.get("proba") else eredeti(*a, **k)
        self.kliens.ir = ir_
        r = b.jegyzet(MAT.UT)
        self.assertEqual([m["mod"] for m in r["modell"]], ["proba"])
        self.assertEqual(F.blokkok(self.olvas()), [])                                      # próbamód: a vaultba semmi nem került
        self.assertEqual(set(proba_hivasok), {True})

    def test_nem_elerheto_modell_fuggoben(self):
        b, _ = self.beiro_hivoval(AlKliens(nincs_worker=True))
        r = b.jegyzet(MAT.UT)
        self.assertEqual((r["allapot"], r["fuggoben"]), ("kesz", 1))                      # a determinisztikus blokk megíródott
        self.assertEqual(r["modell"][0]["allapot"], "modell_var")
        self.assertEqual([x.abra.elemek[0].kifejezes for x in F.blokkok(self.olvas())], ["x^2"])


if __name__ == "__main__":
    unittest.main()
