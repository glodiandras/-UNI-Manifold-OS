"""Az önkalibráció tesztjei (C28b; `core/felkeszultseg/kalibracio.py`): a ridge-illesztés és a leave-one-out hiba **szintetikus adaton**
(az adatfeltétel — mért tudás a lezárt dolgozatok előtt — a valós vaulton ma nem teljesül), a pontgyűjtés a rekonstrukcióval, a
`n < kalibracio_min` védelem és az `os.toml` írása."""
import json
import random
import tomllib
import unittest
from datetime import date, datetime, timedelta, timezone

from core import naptar
from core.felkeszultseg import adat, keplet
from core.felkeszultseg import kalibracio as K
from core.felkeszultseg.forrasok import KvizEredmeny
from core.naptar_seged import Seged
from tests.felkeszultseg_segedek import Alap
from tests.helpers import alg_core, ir, tmpdir
from tests.naptar_segedek import esemeny as ev

B0 = keplet.Beallitas()


def jel(kartya=(), kviz=(), nap=3.0, perc=30.0) -> keplet.TemaJel:
    return keplet.TemaJel(kartya=tuple(kartya), kviz=tuple(kviz), utolso_tanulas_nap=nap, tanult_perc=perc)


def pont(i: int, jelek, y: float) -> K.Pont:
    return K.Pont(f"d{i}", f"Dolgozat {i}", f"2026-09-{i + 1:02d}", y, f"{round(y * 20)}/20", "kiertekelo.md", "2026-09-01T23:59:59+02:00",
                  tuple(jelek))


def kevert_pontok(n: int, y_fuggveny, mag: int = 7) -> list[K.Pont]:
    """`n` dolgozat, mindegyik két témával (5 kártya, 10 kvízkérdés: teljes bizalom); az `y` a téma-értékekből."""
    r = random.Random(mag)
    ki = []
    for i in range(n):
        jelek, ertekek = [], []
        for _ in range(2):
            k, q = r.uniform(0.25, 0.95), r.uniform(0.25, 1.0)
            jelek.append(jel(kartya=[k] * 5, kviz=[(1.0, round(q * 10), 10)], nap=2.0, perc=40.0))
            ertekek.append((k, round(q * 10) / 10))
        ki.append(pont(i, jelek, y_fuggveny(ertekek)))
    return ki


class IlleszTest(unittest.TestCase):
    def test_nulla_pont_nem_teljesitheto_es_nem_dob(self):
        ki = K.illeszt([], B0, 0.1, 8)
        self.assertEqual((ki["allapot"], ki["pontok"], ki["kell"]), ("nem_teljesitheto", 0, 8))
        self.assertIsNone(ki["alap"]["rmse"])
        self.assertEqual(ki["pontok_reszlet"], [])

    def test_kevesebb_mint_nyolc_pont_a_sulyok_nem_valtoznak_a_hiba_meg_mert(self):
        pontok = kevert_pontok(5, lambda e: sum(q for _, q in e) / len(e))
        ki = K.illeszt(pontok, B0, 0.1, 8)
        self.assertEqual((ki["allapot"], ki["pontok"], ki["kis_minta"]), ("nem_teljesitheto", 5, True))
        self.assertIsNotNone(ki["alap"]["rmse"])                         # az induló súlyok hibája tájékoztatásul mérhető
        self.assertEqual(ki["alap"]["suly"], {"suly_kartya": 0.4, "suly_kviz": 0.35, "suly_frissesseg": 0.1, "suly_ido": 0.15})
        self.assertEqual(len(ki["pontok_reszlet"]), 5)
        self.assertNotIn("illesztett", ki, "kevés pontra illesztett súlyt nem adunk ki")
        with self.assertRaises(ValueError):
            K.config_ir(_cfg_ures(self), ki)                             # nem alkalmazható

    def test_a_kvizre_epulo_valosag_a_kvizsulyt_emeli_a_kartyasulyt_csokkenti(self):
        pontok = kevert_pontok(14, lambda e: sum(q for _, q in e) / len(e))
        ki = K.illeszt(pontok, B0, 0.1, 8)
        self.assertEqual(ki["allapot"], "javasolt", ki["loo"])
        s = ki["illesztett"]["suly"]
        self.assertGreater(s["suly_kviz"], B0.suly_kviz)
        self.assertLess(s["suly_kartya"], B0.suly_kartya)
        self.assertAlmostEqual(sum(s.values()), 1.0, places=3)                              # az összeg az induló összeg
        self.assertLessEqual(s["suly_frissesseg"] + s["suly_ido"], s["suly_kartya"] + s["suly_kviz"] + 1e-9)   # a proxik ≤ a mért
        self.assertAlmostEqual(s["suly_frissesseg"] / (s["suly_frissesseg"] + s["suly_ido"]), 0.4, places=3)  # az induló arány
        self.assertGreater(ki["javulas"], K.JAVULAS_MIN)
        self.assertLess(ki["loo"]["rmse"], ki["alap"]["rmse"])

    def test_a_loo_hiba_nem_kisebb_a_mintan_belulinel(self):
        pontok = kevert_pontok(12, lambda e: sum(q for _, q in e) / len(e) + random.Random(len(e)).uniform(-0.05, 0.05))
        ki = K.illeszt(pontok, B0, 0.1, 8)
        self.assertGreaterEqual(ki["loo"]["rmse"], ki["illesztett"]["rmse"] - 1e-9)

    def test_ha_az_indulo_sulyok_helyesek_nincs_javulas_es_a_sulyok_nem_valtoznak(self):
        pontok = []
        for p in kevert_pontok(12, lambda e: 0.0):
            y = K.becsles(p.jelek, B0)
            pontok.append(K.Pont(p.azon, p.cim, p.nap, y, p.eredmeny_forras, p.jegyzet, p.becsles_ideje, p.jelek))
        ki = K.illeszt(pontok, B0, 0.1, 8)
        self.assertEqual(ki["allapot"], "nincs_javulas")
        self.assertAlmostEqual(ki["alap"]["rmse"], 0.0, places=6)
        self.assertEqual(ki["illesztett"]["suly"], {"suly_kartya": 0.4, "suly_kviz": 0.35, "suly_frissesseg": 0.1, "suly_ido": 0.15})

    def test_nagy_ridge_az_indulo_sulyok_kozeleben_tart(self):
        pontok = kevert_pontok(14, lambda e: sum(q for _, q in e) / len(e))
        gyenge = K.illeszt(pontok, B0, 0.0, 8)["illesztett"]["suly"]
        erosen = K.illeszt(pontok, B0, 50.0, 8)["illesztett"]["suly"]
        tav = lambda s: sum((s[k] - getattr(B0, k)) ** 2 for k in K.SULY_KULCSOK)
        self.assertLess(tav(erosen), tav(gyenge))
        self.assertLess(tav(erosen), 0.01)

    def test_determinisztikus(self):
        pontok = kevert_pontok(10, lambda e: e[0][1])
        self.assertEqual(K.illeszt(pontok, B0, 0.1, 8), K.illeszt(pontok, B0, 0.1, 8))

    def test_az_egyetlen_pont_nem_dob(self):
        ki = K.illeszt([pont(0, [jel(kartya=[0.5] * 5)], 0.6)], B0, 0.1, 8)
        self.assertEqual((ki["allapot"], ki["pontok"]), ("nem_teljesitheto", 1))
        self.assertEqual(ki["loo"]["n"], 1)

    def test_mert_tudas_nelkuli_jel_nem_dob_es_bunteti(self):
        ki = K.illeszt([pont(i, [jel()], 0.5) for i in range(9)], B0, 0.1, 8)         # semmi nem mért: a szám mindenhol None
        self.assertEqual(ki["pontok"], 9)
        self.assertEqual(ki["allapot"], "nincs_javulas")

    def test_a_racs_tartalmazza_az_indulo_sulyokat_es_betartja_a_korlatot(self):
        racs = K._racs(B0)
        self.assertTrue(any(all(abs(a - b) < 1e-9 for a, b in zip(g, (0.4, 0.35, 0.25))) for g in racs))
        self.assertTrue(all(abs(sum(g) - 1.0) < 1e-9 and g[2] <= g[0] + g[1] + 1e-9 and min(g) >= 0.049 for g in racs))
        egyedi = keplet.Beallitas(suly_kartya=0.3, suly_kviz=0.3, suly_frissesseg=0.12, suly_ido=0.18)          # 0,3 / 0,3 / 0,3 — nem a rács pontja? igen
        self.assertTrue(any(all(abs(a - b) < 1e-9 for a, b in zip(g, (0.3, 0.3, 0.3))) for g in K._racs(egyedi)))

    def test_az_osszeg_az_indulo_osszeg(self):
        b = keplet.Beallitas(suly_kartya=0.8, suly_kviz=0.7, suly_frissesseg=0.2, suly_ido=0.3)       # összeg 2,0
        ki = K.illeszt(kevert_pontok(12, lambda e: e[0][1]), b, 0.1, 8)
        self.assertAlmostEqual(sum(ki["illesztett"]["suly"].values()), 2.0, places=3)


# ------------------------------------------------------------------ az os.toml írása

CONFIG = """# fejléc
[masik]
suly_kartya = 9            # nem érintjük

[felkeszultseg]
suly_kartya = 0.40                   # a kártya súlya
suly_kviz = 0.35
suly_frissesseg = 0.10
suly_ido = 0.15
kalibralt = false                    # a C28b írja át

# --- következő szakasz
[kartya]
suly_kartya = 5
"""


def _cfg_ures(teszt):
    t = tmpdir()
    teszt.addCleanup(t.cleanup)
    cfg, _, _ = alg_core(t.name)
    return cfg


class TomlIrasTest(unittest.TestCase):
    def test_a_meglevo_kulcs_erteke_cserelodik_a_megjegyzes_es_a_tobbi_szakasz_marad(self):
        uj = K.toml_felulir(CONFIG, "felkeszultseg", {"suly_kartya": 0.25, "kalibralt": True})
        d = tomllib.loads(uj)
        self.assertEqual((d["felkeszultseg"]["suly_kartya"], d["felkeszultseg"]["kalibralt"]), (0.25, True))
        self.assertEqual(d["masik"]["suly_kartya"], 9)
        self.assertEqual(d["kartya"]["suly_kartya"], 5)
        self.assertIn("suly_kartya = 0.25                   # a kártya súlya", uj)
        self.assertIn("kalibralt = true", uj)
        self.assertIn("# a C28b írja át", uj)
        self.assertIn("# --- következő szakasz", uj)

    def test_a_hianyzo_kulcs_a_szakasz_vegere_kerul(self):
        uj = K.toml_felulir(CONFIG, "felkeszultseg", {"kalibracio_n": 11})
        d = tomllib.loads(uj)
        self.assertEqual(d["felkeszultseg"]["kalibracio_n"], 11)
        self.assertNotIn("kalibracio_n", d["kartya"])
        sorok = uj.split("\n")
        self.assertLess(sorok.index("kalibracio_n = 11"), sorok.index("[kartya]"))

    def test_hianyzo_szakasz_hiba(self):
        with self.assertRaises(ValueError):
            K.toml_felulir(CONFIG, "nincs", {"a": 1})

    def test_tobbszori_ismetles_ugyanazt_adja(self):
        egyszer = K.toml_felulir(CONFIG, "felkeszultseg", {"suly_kartya": 0.25, "kalibracio_n": 9})
        ketszer = K.toml_felulir(egyszer, "felkeszultseg", {"suly_kartya": 0.25, "kalibracio_n": 9})
        self.assertEqual(egyszer, ketszer)


class ConfigIrTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)

    def jelentes(self, allapot="javasolt"):
        suly = {"suly_kartya": 0.25, "suly_kviz": 0.5, "suly_frissesseg": 0.1, "suly_ido": 0.15}
        return {"allapot": allapot, "ok": "x", "pontok": 11, "illesztett": {"suly": suly}, "alap": {"suly": {}, "rmse": 0.2},
                "loo": {"rmse": 0.1}, "javulas": 0.1}

    def test_a_javasolt_sulyok_az_os_tomlba_kerulnek_es_naplozodnak(self):
        eredmeny = K.config_ir(self.cfg, self.jelentes(), mikor=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
        d = tomllib.loads(self.cfg.source.read_text(encoding="utf-8"))["felkeszultseg"]
        self.assertEqual((d["suly_kartya"], d["suly_kviz"], d["kalibralt"], d["kalibracio_n"]), (0.25, 0.5, True, 11))
        with open(eredmeny["naplo"], encoding="utf-8") as f:
            sor = json.loads(f.read().strip())
        self.assertEqual((sor["pontok"], sor["uj"]["suly_kviz"], sor["loo_rmse"]), (11, 0.5, 0.1))
        from core import config
        ujra = config.load({"MOS_ROOT": str(self.root), "HOME": str(self._t.name) + "/home"})
        b = keplet.Beallitas.cfg_bol(ujra)
        self.assertEqual((b.suly_kartya, b.suly_kviz, b.kalibralt), (0.25, 0.5, True))

    def test_nem_javasolt_allapotra_nem_ir(self):
        elotte = self.cfg.source.read_text(encoding="utf-8")
        for allapot in ("nem_teljesitheto", "nincs_javulas"):
            with self.assertRaises(ValueError):
                K.config_ir(self.cfg, self.jelentes(allapot))
        self.assertEqual(self.cfg.source.read_text(encoding="utf-8"), elotte)


# ------------------------------------------------------------------ pontgyűjtés a rekonstrukcióval (integráció)

DOLGOZATOK = [date(2026, 9, 1) + timedelta(days=3 * i) for i in range(9)]          # 09-01 … 09-25
MOST2 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone(timedelta(hours=2)))
KIERT = "X01 - Napló & To-Do/2026-09/Napló/2026-09 - Dolgozat kiértékelő.md"


def felk_ut(d: date) -> str:
    return f"X01 - Napló & To-Do/2026-09/Dolgozatok/{d.isoformat()} - Matematika.md"


def tema_ut(i: int) -> str:
    return f"M06 - Exponenciális/Elmélet/Téma {i}.md"


class PontGyujtes(Alap):
    """Kilenc lezárt dolgozat, mindegyikhez egy téma, a D−5. napon egy kvíz; a kiértékelőben a pontszám."""
    NAPTARAK = list(Alap.NAPTARAK)
    ESEMENYEK = [ev(f"d{i}", "HAT", f"{d.isoformat()}T10:00:00+02:00", f"{d.isoformat()}T10:45:00+02:00", "Matek témazáró")
                 for i, d in enumerate(DOLGOZATOK)]
    FAJLOK = {}
    for _i, _d in enumerate(DOLGOZATOK):
        FAJLOK[felk_ut(_d)] = (f"---\nTags:\n  - Active-recall\nSource:\nStatus:\nNN:\n  - \"[[Téma {_i}]]\"\nCanvas:\n---\n# Készülés\n")
        FAJLOK[tema_ut(_i)] = f"# Téma {_i}\nszöveg\n"

    def setUp(self):
        super().setUp()
        self.helyes = [3, 5, 6, 7, 8, 4, 9, 10, 6]
        self.kviz(*[KvizEredmeny(tema_ut(i), datetime.combine(d - timedelta(days=5), datetime.min.time().replace(hour=12), tzinfo=MOST2.tzinfo),
                                 self.helyes[i], 10) for i, d in enumerate(DOLGOZATOK)])
        self.kiertekelo([f"{round(100 * (0.4 + 0.05 * i))}/100" for i in range(len(DOLGOZATOK))])

    def kiertekelo(self, pontok: list[str | None]) -> None:
        sz = []
        for i, p in enumerate(pontok):
            if p is not None:
                sz.append(f"# {DOLGOZATOK[i].isoformat()}\n\n[[{DOLGOZATOK[i].isoformat()} - Matematika]]\n\n{p} lett.\n")
        ir(self.v, KIERT, "---\nTags:\n  - Dolgozat-kiértékelés\nSource:\nStatus:\nNN:\nCanvas:\n---\n\n" + "\n".join(sz))
        self.ix.frissit([KIERT])

    def most(self, **kw):
        def olvas(rp):
            return (self.v / rp).read_text(encoding="utf-8")
        return adat.Adatok(self.cfg, self.ix, MOST2, olvas=olvas, visszamenoleg_nap=400, **kw)

    def test_kilenc_pont_a_rekonstrualt_kvizzel(self):
        pontok, kihagyott = K.pontok_gyujt(self.most())
        self.assertEqual((len(pontok), kihagyott), (9, []))
        self.assertEqual([p.nap for p in pontok], [d.isoformat() for d in DOLGOZATOK])
        p0 = pontok[0]
        self.assertAlmostEqual(p0.y, 0.40)
        self.assertEqual(len(p0.jelek), 1)
        self.assertEqual(p0.jelek[0].kviz[0][1:], (3, 10))
        self.assertTrue(p0.becsles_ideje.startswith("2026-08-29T23:59:59"))                          # D−3 napjának vége
        self.assertEqual(len(p0.jelek[0].kartya), 0)

    def test_a_kvizeredmeny_a_rekonstrukcio_utan_nem_latszik(self):
        # a D−5-ös kvíz mellé egy D−1-es: a D−3. nap végi becslés nem láthatja
        self.kviz(*[KvizEredmeny(tema_ut(i), datetime.combine(d - timedelta(days=5), datetime.min.time().replace(hour=12), tzinfo=MOST2.tzinfo),
                                 self.helyes[i], 10) for i, d in enumerate(DOLGOZATOK)],
                  KvizEredmeny(tema_ut(0), datetime.combine(DOLGOZATOK[0] - timedelta(days=1), datetime.min.time().replace(hour=9),
                                                            tzinfo=MOST2.tzinfo), 10, 10))
        pontok, _ = K.pontok_gyujt(self.most())
        self.assertEqual(len(pontok[0].jelek[0].kviz), 1)

    def test_jelentes_kilenc_ponttal_alkalmazhato_vagy_nincs_javulas(self):
        j = K.jelentes(self.most())
        self.assertEqual((j["pontok"], j["lezart"], j["eredmennyel"], j["kell"]), (9, 9, 9, 8))
        self.assertIn(j["allapot"], ("javasolt", "nincs_javulas"))
        self.assertEqual(len(j["pontok_reszlet"]), 9)
        self.assertIsNotNone(j["loo"]["rmse"])

    def test_a_becsles_az_indulo_sulyokkal_a_kozolt_alakban(self):
        j = K.jelentes(self.most())
        p = j["pontok_reszlet"][0]
        self.assertEqual((p["eredmeny"], p["forras"]), (0.4, "40/100"))
        # a becslés (kilátás): kvíz 3/10, a kor 4,9 nap → időben csökkentett 7,8 kérdés (c = 0,78); frissesség 0,5^(5/10)
        cq = min(1.0, 10 * 0.5 ** (4.9 / 14) / 10)
        self.assertAlmostEqual(p["becsles"], (0.35 * cq * 0.3 + 0.10 * 0.5 ** (5 / 10)) / (0.35 * cq + 0.10), delta=0.002)

    def test_nyolcnal_kevesebb_pont_nem_teljesitheto_es_kimondja_miert(self):
        self.kiertekelo([f"{round(100 * (0.4 + 0.05 * i))}/100" if i < 5 else None for i in range(9)])
        j = K.jelentes(self.most())
        self.assertEqual((j["allapot"], j["pontok"], j["eredmennyel"]), ("nem_teljesitheto", 5, 5))
        self.assertIn("5 / 8", j["ok"])
        self.assertEqual(len(j["kihagyott"]), 4)
        self.assertTrue(all(k["ok"] == "nincs eredmény a kiértékelő jegyzetekben" for k in j["kihagyott"]))
        self.assertFalse(j["kalibralt"])

    def test_mert_tudas_nelkuli_dolgozat_kimarad_okkal(self):
        self.kviz(*[KvizEredmeny(tema_ut(i), datetime.combine(d - timedelta(days=5), datetime.min.time().replace(hour=12),
                                                              tzinfo=MOST2.tzinfo), self.helyes[i], 10)
                    for i, d in enumerate(DOLGOZATOK) if i != 2])
        j = K.jelentes(self.most())
        self.assertEqual(j["pontok"], 8)
        self.assertEqual([k["ok"].split(" (")[0] for k in j["kihagyott"]], ["nincs mért tudás"])
        self.assertEqual(j["eredmennyel"], 9)
        self.assertEqual(j["allapot"] in ("javasolt", "nincs_javulas"), True, "8 pont még elég")

    def test_a_nyitott_dolgozat_nem_pont(self):
        a = adat.Adatok(self.cfg, self.ix, datetime(2026, 9, 10, 12, 0, tzinfo=MOST2.tzinfo), olvas=lambda rp: (self.v / rp).read_text(encoding="utf-8"),
                        visszamenoleg_nap=400)
        pontok, _ = K.pontok_gyujt(a)
        self.assertEqual(len(pontok), 3)                       # 09-01, 09-04, 09-07 zárult le 09-10-ig

    def test_ellentmondo_eredmeny_kimarad_okkal(self):
        self.kiertekelo(["68% lett (18/31)"] + [f"{round(100 * (0.4 + 0.05 * i))}/100" for i in range(1, 9)])
        j = K.jelentes(self.most())
        self.assertEqual(j["pontok"], 8)
        self.assertEqual(j["kihagyott"][0]["ok"], "ellentmondó eredmény a kiértékelőben")

    def test_a_szabott_mezo_feloldja_az_ellentmondo_szoveget(self):
        # C28c (K348): az „Eredmény::” mező a szöveg előtt áll — az ellentmondó szöveg mellé írt mező pontot ad
        self.kiertekelo(["Eredmény:: 18/31\n\n68% lett (18/31)"] + [f"{round(100 * (0.4 + 0.05 * i))}/100" for i in range(1, 9)])
        pontok, kihagyott = K.pontok_gyujt(self.most())
        self.assertEqual((len(pontok), kihagyott), (9, []))
        self.assertAlmostEqual(pontok[0].y, 18 / 31, places=3)
        self.assertEqual(pontok[0].eredmeny_forras, "Eredmény:: 18/31")

    def test_a_dolgozat_oldal_megmondja_az_eredmeny_eredetet(self):
        from core.felkeszultseg import osszesit
        self.kiertekelo(["Eredmény:: 40/100\n\n40/100"] + [f"{round(100 * (0.4 + 0.05 * i))}/100" for i in range(1, 8)] + ["68% lett (18/31)"])
        a = self.most()
        dk = sorted(a.dolgozatok(), key=lambda d: d["nap"])
        e0, _ = osszesit._eredmeny(a, dk[0])
        e1, _ = osszesit._eredmeny(a, dk[1])
        self.assertEqual((e0["eredet"], e0["forras"], e1["eredet"]), ("mezo", "Eredmény:: 40/100", "szoveg"))
        e8, ellent = osszesit._eredmeny(a, dk[8])
        self.assertIsNone(e8)
        self.assertEqual(ellent["eredet"], "szoveg")

    def test_a_hibas_szabott_mezo_kimarad_okkal(self):
        self.kiertekelo(["Eredmény:: 40/100 (70%)\n\n40/100"] + [f"{round(100 * (0.4 + 0.05 * i))}/100" for i in range(1, 9)])
        j = K.jelentes(self.most())
        self.assertEqual(j["pontok"], 8)
        self.assertTrue(j["kihagyott"][0]["ok"].startswith("hibás „Eredmény::” mező a kiértékelőben: a mezőben a pont és a százalék"))

    def test_a_valodi_kovetelmeny_nincs_tanulas_sqlite_nincs_pos_nincs_kviz_nem_dob(self):
        forrasok_tiszta = self.most()
        from core.felkeszultseg import forrasok
        forrasok._FORRASOK.clear()
        j = K.jelentes(forrasok_tiszta)
        self.assertEqual((j["allapot"], j["pontok"]), ("nem_teljesitheto", 0))
        self.assertEqual(j["eredmennyel"], 9)
        self.assertIn("0 / 8", j["ok"])
        self.assertIn("nem pótolható", j["ok"])

    def test_nincs_naptar_hiba_a_jelentesben_nem_kivetel(self):
        class NincsNaptar(PontGyujtes):
            naptar_van = False
        t = NincsNaptar()
        t.setUp()
        self.addCleanup(t.doCleanups)
        j = K.jelentes(t.most())
        self.assertEqual(j["allapot"], "nem_teljesitheto")
        self.assertIn("naptár", j["ok"])


if __name__ == "__main__":
    unittest.main()
