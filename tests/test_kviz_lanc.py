"""C22b: a kvízlánc modellfele — a rossz válaszok kapuja (`generalas.megkulonbozteti`, a C19 K135-mintájának esetei), a lánc
I/O-ja (`modulok/kviz/lanc.py`: egy gépi tétel, D9, a távol-keretre várás, a gyorsítótár, a Qwen-keret) és a feladattípus.
Álmodellel és álcore-ral; a valódi vaulthoz és var/-hoz nem nyúl."""
from __future__ import annotations

import hashlib
import re
import unittest

from core.tulajdonsagok import Tulajdonsagok
from modulok.kviz import formatum as FM
from modulok.kviz import generalas as G
from modulok.kviz import lanc as L
from tests.helpers import alg_core, ir, tmpdir
from tests.test_kviz_generalas import GEN, JEGYZET, RP, TUDAS, Almodell


class MegkulonboztetTest(unittest.TestCase):
    """A rossz válasz akkor „helyes is”, ha a forrásmondat nem különbözteti meg a helyestől (a C19 rétegzett mintájának esetei)."""

    def dont(self, rossz, helyes, mondat):
        return G.megkulonbozteti(rossz, helyes, mondat)

    def test_keplet(self):
        m = "Energiamegmaradás (I. főtétel): $W = Q_1 - Q_2$"
        self.assertIn("képlet", self.dont("$W = Q_1 + Q_2$", "$W = Q_1 - Q_2$", m))
        m = "$\\cos(\\alpha-\\beta) = \\cos\\alpha\\cos\\beta + \\sin\\alpha\\sin\\beta$."
        self.assertIn("képlet", self.dont("$\\cos(\\alpha-\\beta) = \\cos\\alpha\\cos\\beta$",
                                          "$\\cos(\\alpha-\\beta) = \\cos\\alpha\\cos\\beta + \\sin\\alpha\\sin\\beta$", m))
        m = "$P(A\\mid B)=P(A)$, ami a szimmetrikus $P(AB)=P(A)P(B)$ szorzatalakkal egyenértékű."
        self.assertIsNone(self.dont("$P(AB) = P(A)P(B)$", "$P(A\\mid B) = P(A)$", m))      # valóban két helyes

    def test_sajat_szo_csak_a_mondatbol(self):
        m = "Hangerősség (hangintenzitás): az amplitúdóval (és így az energiával) arányos."
        self.assertIn("saját szava", self.dont("A hangszín a hangforrás frekvenciájától függ, míg a hangmagasság az amplitúdótól.",
                                               "A hangerősség (hangintenzitás) az amplitúdóval és az energiával arányos.", m))
        m = "Az alárendelő összetett mondat tagmondatai nem egyenrangúak: a főmondat egyik mondatrészét fejti ki a mellékmondat."
        self.assertIn("saját szava", self.dont("Mellérendelő összetett mondat", "Alárendelő összetett mondat", m))
        m = "HTTP (HyperText Transfer Protocol): az a protokoll, amely szerint a világhálón a kommunikáció zajlik."
        self.assertIn("saját szava", self.dont("HTTPS", "HTTP", m))                       # a betűszó pontosan
        m = "A hang keletkezéséhez hangforrás és azt körülvevő rugalmas közeg szükséges."
        self.assertIn("saját szava", self.dont("A hangforrás és a hanghullám", "A hangforrás és a rugalmas közeg", m))

    def test_tagadas_es_foszto(self):
        m = "Szervetlen: tagmondatai között van tagolatlan mondat; szerves: a tagmondatok mindegyike tagolt mondat"
        self.assertIn("tagadás", self.dont("A tagmondatai mindegyike tagolt mondat",
                                           "A tagmondatai között van tagolatlan mondat", m))
        self.assertIn("tagadás", self.dont("A tagmondatai között nincs tagolatlan mondat",
                                           "A tagmondatai között van tagolatlan mondat", m))

    def test_kizaro_szo(self):
        m = ("A neológusok a szókészlet bővítését szóalkotással, szóképzéssel, idegen szavak fordításával és nyelvjárási elemek "
             "elterjesztésével végezték.")
        self.assertIn("szűkít", self.dont("Csak nyelvjárási elemeket elterjesztettek.",
                                          "Szóalkotással, szóképzéssel és idegen szavak fordításával dolgoztak.", m))

    def test_megforditas_es_hiany(self):
        m = "Szabadeséskor a nehézségi erő mg, a súlyerő pedig nulla: G = 0."
        self.assertIn("sorrend", self.dont("A nehézségi erő nulla, a súlyerő pedig $mg$.",
                                           "A nehézségi erő $mg$, a súlyerő pedig nulla.", m))
        m = "Két ország választójoga lehet formailag „általános”, és mégis gyökeresen eltérő a gyakorlatban."
        self.assertIn("elhagyja", self.dont("Mert a két országban a választójog formailag eltérő volt, és a gyakorlatban is eltérő volt.",
                                            "Mert a két ország választójoga formailag általános, és mégis gyökeresen eltérő volt a gyakorlatban.",
                                            m))

    def test_azonos_valasz_tobb_helyes(self):
        m = "A rugóerő iránya mindig ellentétes a deformáció irányával."
        self.assertIsNone(self.dont("A rugóerő iránya mindig ellentétes a deformáció irányával",
                                    "A rugóerő iránya mindig ellentétes a deformáció irányával.", m))

    def test_a_meres_ugyanazt_a_szabalyt_hivja(self):
        from modulok.eval.kviz import feladat as F
        self.assertIs(F.G.rossz_valasz_hiba, G.rossz_valasz_hiba)
        self.assertEqual((F.HIHETO_KUSZOB, F.HIHETETLEN_MAX), (G.HIHETO_KUSZOB, G.HIHETETLEN_MAX))


# ---------------------------------------------------------------------- a lánc I/O-ja

class AlGepi:
    def __init__(self, fajlok, hiba=None):
        self.fajlok, self.irasok, self.hiba = dict(fajlok), [], hiba

    def olvas(self, ut):
        t = self.fajlok[ut]
        return {"ut": ut, "tartalom": t, "hash": hashlib.sha1(t.encode()).hexdigest()}

    @staticmethod
    def modell_jel(v):
        return {"feladat": v["feladat"], "modell": v["modell"], "proba": bool(v.get("proba"))}

    @staticmethod
    def uj_kor(elotag):
        return elotag + "-20261008-120000-abc123"

    @staticmethod
    def uj(ut, tartalom, osztaly=None):
        return {"tipus": "uj", "ut": ut, "tartalom": tartalom, "osztaly": osztaly}

    def ir(self, kor, tetel, forras, muveletek, uzenet=None, proba=None, *, modell):
        if self.hiba:
            raise self.hiba
        self.irasok.append({"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "proba": proba, "modell": modell})
        return {"ok": True, "sha": "abc", "kor": kor + ("-proba" if proba else ""), "proba": bool(proba)}


class Hiba409(RuntimeError):
    kod = 409


class AlKliens:
    """A `core.modell.kliens` helyett: a `chat` az álmodellt hívja, és rögzíti a kérést (modell, mód, max_tokens)."""

    def __init__(self, router):
        self.router, self.hivasok = router, []
        self.m = Almodell(gen=GEN, tudas=TUDAS)

    def keres(self, u, ut, body):
        return self.router(body.get("keret"))

    def chat(self, u, uzenetek, feladat, modell, mod=None, **k):
        self.hivasok.append({"modell": modell, "mod": mod, "max_tokens": k.get("max_tokens")})
        p = uzenetek[0]["content"]
        szoveg = self.m.ellenorzo(p, 12) if "KÉRDÉS:" in p and "HELYES" not in p else self.m.generalo(p, 1300)
        return {"feladat": feladat, "modell": modell or "qwen35_9b", "proba": modell is not None,
                "choices": [{"message": {"content": szoveg}}]}


def router(mod="kalibralt"):
    def r(keret):
        if mod == "nincs":
            raise Hiba409("nincs kalibrált modell")
        if mod == "tavol" and keret != "tavol":
            return {"modell": None, "var_tavolra": True, "indok": "csak a távol-keretbe fér"}
        return {"modell": "qwen35_9b", "var_tavolra": False, "indok": "a legjobb kalibrált"}
    return r


class LancTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, RP, JEGYZET)
        self.gepi = AlGepi({RP: JEGYZET})
        self.cfg.data.setdefault("kviz", {})["karakter_per_kerdes"] = 50       # a rövid próbajegyzetből több jelölt kell

    def worker(self, mod="kalibralt"):
        w = L.Worker.__new__(L.Worker)
        from core.modell import beallitas as B
        w.b, w.u, w.utolso = B.betolt(self.cfg), "http://al", None
        w.kliens = AlKliens(router(mod))
        return w

    def futtat(self, w=None, **kw):
        w = w or self.worker()
        return L.futtat(self.cfg, RP, gepi=kw.pop("gepi", self.gepi), worker=w, n=3, **kw), w

    def test_egy_tetel_kvizjegyzet_es_gyakorlas(self):
        r, w = self.futtat()
        self.assertEqual((r["allapot"], r["kerdesek"]), ("kesz", 3))
        self.assertEqual(len(self.gepi.irasok), 1)
        t = self.gepi.irasok[0]
        self.assertEqual((t["forras"], t["tetel"], t["kor"], t["modell"]["feladat"], t["proba"]),
                         ("mos-kviz", RP, "KVIZ-20261008-120000-abc123", "kviz", False))
        kviz, gyak = t["muveletek"]
        self.assertEqual((kviz["tipus"], kviz["osztaly"]), ("uj", "kviz"))
        self.assertTrue(kviz["ut"].startswith("ATTCHMNTS - quizes/Nevezetes szorzatok — Kvíz "), kviz["ut"])
        nev = kviz["ut"].split("/", 1)[1][:-3]
        self.assertEqual((gyak["tipus"], gyak["ut"], gyak["szakasz"], gyak["szoveg"]), ("beszuras", RP, "## Gyakorlás", f"![[{nev}]]"))
        e = FM.elemez(kviz["tartalom"])
        self.assertEqual((e.kviz.azon, e.kviz.modell, e.kviz.forras), ("KVIZ-20261008-120000-abc123", "qwen35_9b", RP[:-3]))
        self.assertEqual(e.hibak, [])
        t_ = Tulajdonsagok(self.cfg, None)                                    # a `kviz` sémaosztály szerint ép
        fm = re.match(r"---\n(.*?)\n---\n", kviz["tartalom"], re.S).group(0)
        el = t_.elemez(kviz["ut"], fm)
        self.assertEqual((el["osztaly"], el["problemak"]), ("kviz", []))
        self.assertEqual(t_.h1_problemak(kviz["ut"], kviz["tartalom"]), [])
        self.assertEqual({h["mod"] for h in w.kliens.hivasok}, {None})       # interaktív: a router modellje a munka-keretben
        self.assertIn("elvetve", r["statisztika"])

    def test_d9_kalibralt_nelkul_megall(self):
        with self.assertRaises(L.Megall):
            self.futtat(self.worker("nincs"))
        self.assertEqual(self.gepi.irasok, [])

    def test_tavol_keretre_var_auto_modban(self):
        naplo = []
        r, w = self.futtat(self.worker("tavol"), naplo=naplo.append)
        self.assertEqual(r["allapot"], "kesz")
        self.assertEqual({h["mod"] for h in w.kliens.hivasok}, {"auto"})     # sorba áll, tétlenségben fut
        self.assertEqual({h["modell"] for h in w.kliens.hivasok}, {None})     # a router választ (élesen írható)
        self.assertTrue(any("tétlenségben" in s for s in naplo))
        self.assertFalse(self.gepi.irasok[0]["proba"])

    def test_kifejezett_modell_proba(self):
        r, w = self.futtat(modell="gemma4_e4b")
        self.assertTrue(self.gepi.irasok[0]["proba"])
        self.assertTrue(r["proba"])
        self.assertEqual({h["modell"] for h in w.kliens.hivasok}, {"gemma4_e4b"})

    def test_a_qwen_kerete_a_meres_szerint(self):
        _, w9 = self.futtat()
        _, w4 = self.futtat(modell="gemma4_e4b")
        g9 = [h["max_tokens"] for h in w9.kliens.hivasok if h["max_tokens"] > 100]
        g4 = [h["max_tokens"] for h in w4.kliens.hivasok if h["max_tokens"] > 100]
        self.assertEqual(round(g4[0] * 1.6), g9[0])                          # [modellek.qwen35_9b.meres.kviz] max_tokens_szorzo

    def test_gyorsitotar_a_megszakadt_futas_folytatasa(self):
        hibas = AlGepi({RP: JEGYZET}, hiba=OSError("a core nem érhető el"))
        with self.assertRaises(OSError):
            self.futtat(gepi=hibas)
        naplo = []
        r, w = self.futtat(naplo=naplo.append)
        self.assertEqual(r["allapot"], "kesz")
        self.assertEqual(w.kliens.hivasok, [])                                # minden válasz a gyorsítótárból
        self.assertTrue(any("gyorsítótár" in s for s in naplo))
        self.assertFalse((self.cfg.path("tmp") / L.GYORSITOTAR / L._kulcs(RP)).exists())    # siker után törölve

    def test_leallitas(self):
        with self.assertRaises(L.Megall):
            self.futtat(allj=lambda: True)
        self.assertEqual(self.gepi.irasok, [])

    def test_foglalt_nev_sorszamot_kap_es_a_korabbi_kerdes_kimarad(self):
        r, _ = self.futtat()
        k = self.gepi.irasok[0]["muveletek"][0]
        ir(self.v, k["ut"], k["tartalom"])                                    # az első kvíz a vaultban
        korabbi, foglalt = L.korabbi_kvizek(self.cfg, RP)
        self.assertEqual(len(korabbi), 3)
        self.assertIn(k["ut"].split("/", 1)[1][:-3].casefold(), foglalt)
        # a második futás minden jelöltje a korábbi kvíz ismétlése: kevés kérdés, nem készül kvíz
        with self.assertRaises(L.Megall):
            self.futtat()


class VakMeresTest(unittest.TestCase):
    """`modulok.kviz.meres.mer_tetel`: a pontozón átment kérdésekre a vak ellenőrzés fut, a többire nem."""

    def test_mer_tetel(self):
        from modulok.kviz import meres
        from tests.eval_segedek import eval_cfg, feladat
        from tests.test_eval_kviz import JO, kimenet
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = eval_cfg(t.name)
        m = feladat(cfg, "kviz")
        list(m.tetelek(cfg))
        hivasok = []

        def ellenorzo(prompt, max_tokens):                   # a „Brutus és Cassius” kérdésre mást mond: kiesik
            hivasok.append(prompt)
            k = re.search(r"KÉRDÉS: (.*)\n((?:[ABCD]\) .*\n?)+)", prompt)
            for betu, opcio in re.findall(r"([ABCD])\) (.*)", k.group(2)):
                if (opcio == "Crassus és Pompeius") if "összeesküvés" in k.group(1) else (opcio in [x[1][0] for x in JO]):
                    return betu
            return "?"
        sorok = meres.mer_tetel(m, {"vart": {"jegyzet": "j01"}, "valasz": kimenet(JO)}, ellenorzo)
        o = meres.osszegez(sorok)
        self.assertEqual((o["jelolt"], o["pontozo_at"], o["vak_utan_at"]), (5, 5, 4))
        self.assertEqual(o["vak_kiejtette"], ["j01 Q5"])
        self.assertEqual(len(hivasok), 5)


class FeladatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        from core import kviz_feladat, tasks
        self.KF, self.tasks = kviz_feladat, tasks

    def test_terv(self):
        lep, _, figy = self.KF._terv(self.cfg, {"ut": "M/A.md", "n": 5}, "/tmp/stop")
        argv = lep[0].argv
        self.assertEqual(argv[2:5], ["-m", "modulok.kviz", "general"])
        self.assertEqual(argv[argv.index("--n") + 1], "5")
        self.assertEqual(figy, [])
        lep, _, figy = self.KF._terv(self.cfg, {"ut": "M/A.md", "modell": "gemma4_e4b"}, "/tmp/stop")
        self.assertIn("--proba", lep[0].argv)
        self.assertTrue(figy)
        for rossz in ({"ut": "ATTCHMNTS - quizes/x.md"}, {"ut": "/abs.md"}, {"ut": "x.txt"}, {"ut": "M/A.md", "proba": 1},
                      {"ut": "M/A.md", "modell": "bge_m3"}, {"ut": "M/A.md", "n": 99}, {"ut": "M/A.md", "n": True}):
            with self.assertRaises(self.tasks.Invalid):
                self.KF._terv(self.cfg, rossz, "/tmp/stop")

    def test_regisztracio(self):
        self.KF.regisztral()
        t = self.tasks.REGISTRY[self.KF.TIPUS]
        self.assertFalse(t.automatikus)
        self.assertEqual(t.resources, frozenset({"modell", "vault"}))


if __name__ == "__main__":
    unittest.main()
