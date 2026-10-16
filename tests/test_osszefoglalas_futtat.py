"""C26b: az összefoglaló éles lánca (`modulok/osszefoglalas/futtat.py`) álcore-ral és álworkerrel — egy tétel, a forrás egyetlen
`csere`-je (horgonyok + beágyazó sor), D9, a gyorsítótár, az automatikus mód, mappa- és videó-szint, a feladattípusok, a mérés.
A vaultba és a valódi var/-ba nem ír."""
from __future__ import annotations

import hashlib
import json
import re
import unittest

from core import automatika
from core.tulajdonsagok import Tulajdonsagok
from modulok.osszefoglalas import ellenorzes as EL
from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import futtat as F
from modulok.osszefoglalas import lanc as L
from tests.eval_segedek import aranyt_igenyel
from tests.helpers import alg_core, ir, tmpdir
from tests.test_osszefoglalas_lanc import A1, A2, A3, CEL, JEGYZET, Q2, RP, valasz

MAPPA = "T03 - Az ókori Róma/Elmélet"
RP2 = MAPPA + "/09 - A második jegyzet.md"
KISERO = "ATTCHMNTS - summaries/08 - A polgárháborúk kora és Caesar — összefoglaló.md"


class Hiba409(RuntimeError):
    kod = 409


class AlGepi:
    """A `core.gepi_kliens` álarca: fájlok a memóriában, az írások rögzítve."""

    def __init__(self, fajlok, cuek=None, hiba_elso=False):
        self.fajlok, self.irasok, self.cuek, self.hiba_elso = dict(fajlok), [], cuek or [], hiba_elso

    class GepiHiba(RuntimeError):
        def __init__(self, kod=409, uzenet="nyitott"):
            super().__init__(uzenet)
            self.kod = kod

    def olvas(self, ut):
        t = self.fajlok[ut]
        return {"ut": ut, "tartalom": t, "hash": hashlib.sha1(t.encode()).hexdigest()}

    def atirat(self, ut):
        return {"ut": ut, "cuek": self.cuek, "gepi": True, "figyelmeztetes": None}

    @staticmethod
    def modell_jel(v):
        return {"feladat": v["feladat"], "modell": v["modell"], "proba": bool(v.get("proba"))}

    n = 0

    def uj_kor(self, elotag):
        AlGepi.n += 1
        return f"{elotag}-20261008-1200{AlGepi.n:02d}-{AlGepi.n:06x}"

    @staticmethod
    def uj(ut, tartalom, osztaly=None):
        return {"tipus": "uj", "ut": ut, "tartalom": tartalom, "osztaly": osztaly}

    @staticmethod
    def csere(ut, tartalom, alap):
        return {"tipus": "csere", "ut": ut, "tartalom": tartalom, "alap": alap}

    def ir(self, kor, tetel, forras, muveletek, uzenet=None, proba=None, *, modell):
        if self.hiba_elso:
            self.hiba_elso = False
            raise AlGepi.GepiHiba(409, "a jegyzet nyitva van, mentetlen")
        self.irasok.append({"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "proba": proba, "modell": modell,
                            "uzenet": uzenet})
        for m in muveletek:
            self.fajlok[m["ut"]] = m["tartalom"]
        return {"ok": True, "sha": "abc", "kor": kor, "proba": bool(proba),
                "hash": {m["ut"]: hashlib.sha1(m["tartalom"].encode()).hexdigest() for m in muveletek}}


class AlWorker:
    """A worker: a `szoveg` router-feladat kalibrált modellje; a darab-promptra (`JEGYZET (`) a megadott választ adja."""

    def __init__(self, kalibralt=True, darab=None, mappa=None):
        self.kalibralt, self.utolso = kalibralt, None
        self.darab = valasz(A1, A2, A3) if darab is None else darab
        self.mappa = mappa
        self.hivasok = []

    def valaszt(self):
        if not self.kalibralt:
            raise Hiba409("nincs kalibrált modell")
        return {"modell": "qwen35_4b"}

    def hivo(self, modell, kifejezett):
        def hiv(prompt, max_tokens):
            self.hivasok.append((modell, kifejezett, prompt))
            szoveg = self.mappa if "ÁLLÍTÁSOK:" in prompt else self.darab
            self.utolso = {"feladat": "szoveg", "modell": modell, "proba": kifejezett, "choices": [{"message": {"content": szoveg}}]}
            return szoveg
        return hiv


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, RP, JEGYZET)
        self.gepi = AlGepi({RP: JEGYZET})

    def jegyzet(self, **kw):
        return F.futtat_jegyzet(self.cfg, RP, gepi=self.gepi, worker=kw.pop("worker", AlWorker()), **kw)


class JegyzetTest(Alap):
    def test_egy_tetel_kisero_es_forras(self):
        r = self.jegyzet()
        self.assertEqual((r["allapot"], r["szint"], r["allitasok"]), ("kesz", "jegyzet", 3))
        self.assertEqual(len(self.gepi.irasok), 1)
        w = self.gepi.irasok[0]
        self.assertEqual((w["forras"], w["tetel"], w["modell"]), ("mos-osszefoglalas", RP, {"feladat": "szoveg", "modell": "qwen35_4b", "proba": False}))
        self.assertTrue(w["kor"].startswith("OSSZ-"))
        kisero, forras = w["muveletek"]
        self.assertEqual((kisero["tipus"], kisero["osztaly"], kisero["ut"]), ("uj", "osszefoglalo", KISERO))
        self.assertEqual((forras["tipus"], forras["ut"]), ("csere", RP))
        # a forrás: a `## Gyakorlás` beágyazó sora, a meglévő `^m-3f2a` azonosító újrahasznosul, a másik kettő új `^m-…`
        self.assertIn("## Gyakorlás\n![[08 - A polgárháborúk kora és Caesar — összefoglaló]]\n", forras["tartalom"])
        self.assertEqual(len(re.findall(r" \^m-[0-9a-f]{4}\n", forras["tartalom"])), 3)
        self.assertIn("(Kr. e. 60). ^m-3f2a\n", forras["tartalom"])
        # az összefoglaló: az `Osszefoglalas` a kör azonosítója, a linkek az éles blokkazonosítóra mutatnak (nem a fejezetre)
        e = FM.elemez(kisero["tartalom"])
        self.assertEqual(e.hibak, [])
        o = e.osszefoglalo
        self.assertEqual((o.azon, o.szint, o.modell, o.forrasok), (w["kor"], "jegyzet", "qwen35_4b", [CEL]))
        self.assertTrue(FM.AZON_RE.match(o.azon))
        self.assertTrue(all((a.horgony.alcel or "").startswith("^m-") for a in o.allitasok), [a.horgony for a in o.allitasok])
        self.assertEqual(o.allitasok[0].horgony.alcel, "^m-3f2a")
        # a `osszefoglalo` sémaosztály szerint ép (a gépi írás ugyanezt ellenőrzi); a H1 nincs ellenőrizve
        t = Tulajdonsagok(self.cfg, None)
        fm = re.match(r"---\n(.*?)\n---\n", kisero["tartalom"], re.S).group(0)
        el = t.elemez(kisero["ut"], fm)
        self.assertEqual((el["osztaly"], el["problemak"]), ("osszefoglalo", []))
        self.assertEqual(t.h1_problemak(kisero["ut"], kisero["tartalom"]), [])
        # az automatika visszacsatolása: a forrás új változata feldolgozott, a kimenet a kísérőjegyzet
        s = automatika.Tar(self.cfg).sor("osszefoglalo", RP)
        self.assertEqual(s["kimenet"], KISERO)
        self.assertEqual(s["hash"], hashlib.sha1(forras["tartalom"].encode()).hexdigest())

    def test_az_uj_vault_allapot_a_vizsgalon_at_nem_sodrodott(self):
        """Az író és a vizsgáló ugyanazt mondja: a frissen írt összefoglaló nem sodródott, a horgonyok léteznek."""
        self.jegyzet()
        ir(self.v, RP, self.gepi.fajlok[RP])
        olvas = lambda rp: (self.v / rp).read_text(encoding="utf-8") if (self.v / rp).is_file() else None       # noqa: E731
        ki, rc = EL.vizsgal(self.gepi.irasok[0]["muveletek"][0]["tartalom"], olvas, lambda rp: (self.v / rp).is_file(), L.beallitas(self.cfg))
        self.assertEqual((ki["hibak"], ki["sodrodott"], ki["horgony_hianyzik"], rc), ([], [], [], 0), ki)
        # a forrás azóta megváltozott: az idézet nem áll szó szerint → sodródás
        valtozott = self.gepi.fajlok[RP].replace("Mikor Caesart", "Amikor Caesart")
        ir(self.v, RP, valtozott)
        ki, rc = EL.vizsgal(self.gepi.irasok[0]["muveletek"][0]["tartalom"], olvas, lambda rp: (self.v / rp).is_file(), L.beallitas(self.cfg))
        self.assertEqual((ki["sodrodott"], rc), (["a2"], 1))
        self.assertTrue(next(x for x in ki["reszletek"] if x["id"] == "a2")["sodrodott"])

    def test_masodik_futas_csere_uj_azonositoval_es_egy_beagyazassal(self):
        self.jegyzet()
        ir(self.v, KISERO, self.gepi.fajlok[KISERO])
        elso = FM.elemez(self.gepi.fajlok[KISERO]).osszefoglalo.azon
        self.jegyzet()
        kisero = self.gepi.irasok[1]["muveletek"][0]
        self.assertEqual((kisero["tipus"], kisero["ut"]), ("csere", KISERO))
        self.assertNotEqual(FM.elemez(kisero["tartalom"]).osszefoglalo.azon, elso)       # új tartalom = új kör = új azonosító
        self.assertEqual(self.gepi.fajlok[RP].count("![[08 - A polgárháborúk kora és Caesar — összefoglaló]]"), 1)
        self.assertEqual(len(self.gepi.irasok[1]["muveletek"]), 1)                       # a forrás változatlan: nincs második csere

    def test_d9_kalibralt_nelkul_megall(self):
        with self.assertRaises(L.Megall) as cm:
            self.jegyzet(worker=AlWorker(kalibralt=False))
        self.assertIn("kalibrált", str(cm.exception))
        self.assertEqual(self.gepi.irasok, [])

    def test_kifejezett_modell_proba_es_nem_ir_allapotot(self):
        r = self.jegyzet(modell="gemma4_12b")
        self.assertTrue(self.gepi.irasok[0]["proba"])
        self.assertTrue(r["proba"])
        self.assertTrue(self.gepi.irasok[0]["modell"]["proba"])
        self.assertIsNone(automatika.Tar(self.cfg).sor("osszefoglalo", RP))

    def test_gyorsitotar_az_elakadt_iras_ujraprobaja_nem_hiv_ujra(self):
        w = AlWorker()
        self.gepi.hiba_elso = True                      # a jegyzet nyitva van, mentetlen: a gépi kliens 409-et ad
        with self.assertRaises(AlGepi.GepiHiba):
            self.jegyzet(worker=w)
        hivas = len(w.hivasok)
        self.assertGreaterEqual(hivas, 1)
        self.jegyzet(worker=w)
        self.assertEqual(len(w.hivasok), hivas)           # a modell-válasz a gyorsítótárból jött
        self.assertEqual(len(self.gepi.irasok), 1)
        self.assertEqual(self.gepi.irasok[0]["modell"]["modell"], "qwen35_4b")      # a jel a gyorsítótárból is megvan

    def test_gyorsitotar_nem_keveri_a_kifejezett_modellt(self):
        w = AlWorker()
        self.jegyzet(worker=w)
        n = len(w.hivasok)
        self.jegyzet(worker=w, modell="gemma4_12b")
        self.assertGreater(len(w.hivasok), n)           # másik modell: új hívás
        self.assertTrue(self.gepi.irasok[1]["proba"])

    def test_kevés_hiteles_allitas_kezi_modban_hiba_automatikusban_feldolgozott(self):
        w = AlWorker(darab=valasz(A1))
        with self.assertRaises(L.Megall):
            self.jegyzet(worker=w)
        r = self.jegyzet(worker=AlWorker(darab=valasz(A1)), automatikus=True)
        self.assertEqual(r["allapot"], "nincs_osszefoglalo")
        self.assertEqual(self.gepi.irasok, [])
        self.assertIsNotNone(automatika.Tar(self.cfg).sor("osszefoglalo", RP))           # ugyanezt a változatot nem próbáljuk újra

    def test_leallitas(self):
        with self.assertRaises(L.Megall) as cm:
            self.jegyzet(allj=lambda: True)
        self.assertTrue(str(cm.exception).startswith("leállítva"))
        self.assertEqual(self.gepi.irasok, [])


class MappaTest(Alap):
    def setUp(self):
        super().setUp()
        ir(self.v, RP2, JEGYZET)
        self.gepi.fajlok[RP2] = JEGYZET
        self.mappa_valasz = valasz({"allitas": "Caesar a senatus ellen szövetkezett két hadvezérrel.", "forras": "J1.1"},
                                   {"allitas": "Caesar átlépte a Rubicont a senatus parancsa után.", "forras": "J1.2"},
                                   {"allitas": "Pharszalosznál Caesar legyőzte Pompeius légióit.", "forras": "J2.3"})

    def test_hianyzo_jegyzet_osszefoglalokat_elobb_elkesziti_majd_mappa_szint(self):
        w = AlWorker(mappa=self.mappa_valasz)
        # minden írás után a vault is kövesse az álgépi írást (a mappa-szint a vaultból olvassa a meglévő összefoglalókat)
        eredeti = self.gepi.ir

        def ir_es_lemez(kor, tetel, forras, muveletek, **kw):
            r = eredeti(kor, tetel, forras, muveletek, **kw)
            for m in muveletek:
                ir(self.v, m["ut"], m["tartalom"])
            return r
        self.gepi.ir = ir_es_lemez
        r = F.futtat_mappa(self.cfg, MAPPA, gepi=self.gepi, worker=w)
        self.assertEqual((r["allapot"], r["szint"], r["allitasok"]), ("kesz", "mappa", 3))
        self.assertEqual(sorted(r["uj_jegyzet_osszefoglalo"]), sorted([RP, RP2]))
        self.assertEqual(len(self.gepi.irasok), 3)                                           # 2 jegyzet + 1 mappa, mind önálló tétel
        self.assertEqual(len({i["kor"] for i in self.gepi.irasok}), 3)
        mappa_irasa = self.gepi.irasok[-1]
        self.assertEqual((mappa_irasa["tetel"], mappa_irasa["forras"]), (MAPPA, "mos-osszefoglalas"))
        self.assertEqual(len(mappa_irasa["muveletek"]), 1)                                   # a mappának nincs forrásjegyzete
        m = mappa_irasa["muveletek"][0]
        self.assertEqual((m["tipus"], m["osztaly"], m["ut"]), ("uj", "osszefoglalo", "ATTCHMNTS - summaries/Elmélet — összefoglaló.md"))
        o = FM.elemez(m["tartalom"]).osszefoglalo
        self.assertEqual((o.szint, o.cim), ("mappa", "Elmélet"))
        self.assertEqual(sorted(o.forrasok), sorted([RP.removesuffix(".md"), RP2.removesuffix(".md")]))
        # a link a jegyzet eredeti horgonyára mutat
        self.assertTrue(all(a.horgony.cel in o.forrasok for a in o.allitasok))
        # a második futás a meglévő mappa-összefoglalót cseréli (nem készít újat)
        self.gepi.irasok.clear()
        F.futtat_mappa(self.cfg, MAPPA, gepi=self.gepi, worker=w)
        self.assertEqual(len(self.gepi.irasok), 1)
        self.assertEqual(self.gepi.irasok[0]["muveletek"][0]["tipus"], "csere")

    def test_terv_egy_kerelemben_legfeljebb_otodik_tetel(self):
        for i in range(3, 9):                                                              # 8 jegyzet, mind összefoglaló nélkül
            ir(self.v, f"{MAPPA}/{i:02d} - Jegyzet.md", JEGYZET)
        t = F.mappa_terv(self.cfg, MAPPA)
        self.assertEqual((len(t["jegyzetek"]), len(t["van"]), len(t["hianyzik"])), (8, 0, 8))
        self.assertEqual((len(t["keszul"]), t["tetelek"]), (4, 5))                         # ≤ 4 jegyzet-szintű + 1 mappa-szintű írás
        self.assertEqual(F.mappa_terv(self.cfg, MAPPA, kiegeszit=False)["tetelek"], 1)

    def test_haladas_a_tetelek_szamahoz_igazodik(self):
        naplo = []
        eredeti = self.gepi.ir

        def ir_es_lemez(kor, tetel, forras, muveletek, **kw):
            r = eredeti(kor, tetel, forras, muveletek, **kw)
            for m in muveletek:
                ir(self.v, m["ut"], m["tartalom"])
            return r
        self.gepi.ir = ir_es_lemez
        F.futtat_mappa(self.cfg, MAPPA, gepi=self.gepi, worker=AlWorker(mappa=self.mappa_valasz), naplo=naplo.append)
        self.assertIn("[manifold-progress] 33%", naplo)
        self.assertIn("[manifold-progress] 67%", naplo)
        self.assertTrue(any("2 készül el most" in x and "összesen 3 tétel" in x for x in naplo), naplo)

    def test_nelkul_a_kiegeszites_ket_osszefoglalo_kell(self):
        with self.assertRaises(L.Megall) as cm:
            F.futtat_mappa(self.cfg, MAPPA, gepi=self.gepi, worker=AlWorker(mappa=self.mappa_valasz), kiegeszit=False)
        self.assertIn("legalább két", str(cm.exception))
        self.assertEqual(self.gepi.irasok, [])

    def test_rejtett_vagy_hianyzo_mappa(self):
        for rossz in ("nincs/ilyen", ".obsidian"):
            with self.assertRaises(L.Megall):
                F.futtat_mappa(self.cfg, rossz, gepi=self.gepi, worker=AlWorker())


class VideoTest(Alap):
    VIDEO = "T03 - Az ókori Róma/Média/Előadás.mp4"
    CUEK = [{"k": 0.0, "v": 4.0, "szoveg": "Caesar kibékítette Crassust és Pompeiust, és szövetséget kötött velük a senatus ellen."},
            {"k": 61.0, "v": 66.0, "szoveg": "Mikor Caesart a senatus Rómába rendelte, döntő elhatározásra jutott: átlépte a Rubicont."},
            {"k": 125.0, "v": 130.0, "szoveg": "Caesar sorra legyőzte Pompeius légióit, majd Pharszalosznál döntő vereséget mért rá."}]

    def test_atirat_idokod_linkekkel(self):
        gepi = AlGepi({}, cuek=self.CUEK)
        v = valasz(
            {"allitas": "Caesar szövetséget kötött Crassusszal és Pompeiusszal a senatus ellen.",
             "idezet": "Caesar kibékítette Crassust és Pompeiust, és szövetséget kötött velük a senatus ellen."},
            {"allitas": "Caesar átlépte a Rubicont, miután a senatus Rómába rendelte.",
             "idezet": "Mikor Caesart a senatus Rómába rendelte, döntő elhatározásra jutott: átlépte a Rubicont."},
            {"allitas": "Pharszalosznál Caesar döntő vereséget mért Pompeiusra.",
             "idezet": "Caesar sorra legyőzte Pompeius légióit, majd Pharszalosznál döntő vereséget mért rá."})
        r = F.futtat_video(self.cfg, self.VIDEO, gepi=gepi, worker=AlWorker(darab=v))
        self.assertEqual((r["allapot"], r["szint"], r["allitasok"]), ("kesz", "video", 3))
        w = gepi.irasok[0]
        self.assertEqual(len(w["muveletek"]), 1)                                              # videóhoz nincs beágyazó sor
        m = w["muveletek"][0]
        self.assertEqual((m["tipus"], m["osztaly"], m["ut"]), ("uj", "osszefoglalo", "ATTCHMNTS - summaries/Előadás — összefoglaló.md"))
        o = FM.elemez(m["tartalom"]).osszefoglalo
        self.assertEqual((o.szint, o.forrasok), ("video", [self.VIDEO]))
        self.assertEqual([a.horgony.alcel for a in o.allitasok], ["t=0", "t=61", "t=125"])
        self.assertEqual([a.horgony.felirat for a in o.allitasok], ["0:00", "1:01", "2:05"])

    def test_atirat_nelkul_hiba(self):
        with self.assertRaises(L.Megall) as cm:
            F.futtat_video(self.cfg, self.VIDEO, gepi=AlGepi({}, cuek=[]), worker=AlWorker())
        self.assertIn("átirat", str(cm.exception))


class FeladatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        from core import osszefoglalas_feladat, tasks
        self.OF, self.tasks = osszefoglalas_feladat, tasks

    def test_kezi_terv_szintenkent(self):
        lep, _, figy = self.OF._terv(self.cfg, {"ut": "M/A.md"}, "/tmp/stop")
        argv = lep[0].argv
        self.assertEqual(argv[2:5], ["-m", "modulok.osszefoglalas", "general"])
        self.assertEqual(argv[argv.index("--szint") + 1], "jegyzet")
        self.assertEqual(figy, [])
        lep, _, _ = self.OF._terv(self.cfg, {"szint": "mappa", "ut": "M/Elmélet/"}, "/tmp/stop")
        self.assertEqual(lep[0].argv[lep[0].argv.index("--ut") + 1], "M/Elmélet")
        self.assertIn("--kiegeszit", lep[0].argv)
        lep, _, _ = self.OF._terv(self.cfg, {"szint": "mappa", "ut": "M/E", "kiegeszit": False}, "/tmp/stop")
        self.assertNotIn("--kiegeszit", lep[0].argv)
        lep, _, _ = self.OF._terv(self.cfg, {"szint": "video", "ut": "ATTCHMNTS - Videos/x.mp4"}, "/tmp/stop")
        self.assertEqual(lep[0].argv[lep[0].argv.index("--szint") + 1], "video")
        _, _, figy = self.OF._terv(self.cfg, {"ut": "M/A.md", "modell": "gemma4_12b"}, "/tmp/stop")
        self.assertTrue(figy)                                                   # kifejezett modell: próba (D9)

    def test_hibas_parameterek(self):
        for rossz in ({"ut": "ATTCHMNTS - summaries/x.md"}, {"ut": "/abs.md"}, {"ut": "x.txt"}, {"ut": "M/A.md", "proba": 1},
                      {"ut": "M/A.md", "modell": "bge_m3"}, {"ut": "M/A.md", "szint": "kurzus"}, {"szint": "mappa", "ut": "M/A.md"},
                      {"szint": "mappa", "ut": ".obsidian"}, {"szint": "mappa", "ut": "ATTCHMNTS - cards"}, {"szint": "video", "ut": "M/A.md"},
                      {"szint": "video", "ut": "../x.mp4"}):
            with self.assertRaises(self.tasks.Invalid, msg=str(rossz)):
                self.OF._terv(self.cfg, rossz, "/tmp/stop")

    def test_automatikus_terv_es_regisztracio(self):
        lep, _, _ = self.OF._auto_terv(self.cfg, {"utak": ["M/A.md", "F/B.md"]}, "/tmp/stop")
        self.assertIn("--automatikus", lep[0].argv)
        self.assertEqual(lep[0].argv.count("--ut"), 2)
        with self.assertRaises(self.tasks.Invalid):
            self.OF._auto_terv(self.cfg, {"utak": []}, "/tmp/stop")
        self.OF.regisztral()
        self.assertTrue(self.tasks.REGISTRY[self.OF.AUTO_TIPUS].automatikus)
        self.assertFalse(self.tasks.REGISTRY[self.OF.TIPUS].automatikus)
        self.assertEqual(self.tasks.REGISTRY[self.OF.TIPUS].resources, frozenset({"modell", "vault"}))

    def test_az_ütemezo_fogyasztoja(self):
        automatika.alap_fogyasztok(self.cfg)
        self.assertNotIn("osszefoglalo", automatika.REGISZTER)                      # 80(a): alapból nem automatikus
        self.cfg.data.setdefault("osszefoglalas", {}).setdefault("automatika", {})["be"] = True
        self.addCleanup(lambda: automatika.REGISZTER.pop("osszefoglalo", None))
        automatika.alap_fogyasztok(self.cfg)
        self.assertNotIn("osszefoglalo", automatika.REGISZTER)  # CX-011: régi flag sem indít AI-t.



@aranyt_igenyel("szoveg")
class MeresTest(unittest.TestCase):
    def test_mer_jegyzet_alakja(self):
        """A mérés az éles láncot futtatja a fagyasztott arany-jegyzeten: az álmodell jelöltjei (idézetük nincs a jegyzetben) a kapuk
        előtt pontozódnak, utánuk nem marad állítás — a jegyzet `nem_keszult`, 0 ponttal az átlagban."""
        from modulok.osszefoglalas import meres
        s = meres.mer_jegyzet("j01", lambda p, m: valasz(A1, A2, A3), L.Beallitas(), L.profil())
        self.assertNotIn("nem_keszult", s)                  # az arany j01 az A1–A3 forrása: az első darab 3 állítása átmegy
        self.assertEqual((s["elott"]["allitasok"], s["utan"]["allitasok"]), (12, 3))
        self.assertTrue(all(not a["idezet"].startswith(("*", "„")) for a in s["allitasok"]))      # a kiemelés-jel nem része az idézetnek
        s = meres.mer_jegyzet("j01", lambda p, m: valasz(A1), L.Beallitas(), L.profil())
        self.assertIn("nem_keszult", s)
        self.assertEqual(s["utan"]["allitasok"], 0)
        self.assertEqual(s["elott"]["allitasok"], 4)
        o = meres.osszegez([s])
        self.assertEqual((o["jegyzet"], o["nem_keszult"], o["elfogadott"], o["pont_kapuk_utan"]), (1, 1, 0, 0.0))
        self.assertEqual(meres.minta([s]), [])

    def test_mer_jegyzet_jo_valasszal(self):
        from modulok.eval.szoveg import feladat as SZ
        from modulok.osszefoglalas import meres
        md = SZ.forras_szoveg("j01")
        mondatok = [m.strip() for m in re.split(r"(?<=[.!?])\s+", re.sub(r"[#>*_`\[\]]", "", md.split("---", 2)[-1])) if len(m.split()) >= 8][:12]
        v = valasz(*[{"allitas": " ".join(m.split()[:14]) + ".", "idezet": m} for m in mondatok])
        s = meres.mer_jegyzet("j01", lambda p, m: v, L.Beallitas(), L.profil())
        self.assertGreater(s["elott"]["pont"], 0)
        if not s.get("nem_keszult"):
            self.assertGreater(s["utan"]["pont"], 0)
            self.assertTrue(meres.minta([s]))


if __name__ == "__main__":
    unittest.main()
