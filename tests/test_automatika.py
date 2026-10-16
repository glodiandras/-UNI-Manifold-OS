"""C23b: a közös automatika-ütemező (`core/automatika.py`, T149) — a mérték, a döntés, a tároló és az ütem álindexszel,
álfeladatsorral és álórával (modellt nem tölt, a vaultba nem ír, a valódi var/-hoz nem nyúl)."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import unittest
from unittest import mock

from core import automatika as A
from core import mentes
from tests.helpers import alg_core, ir, tmpdir

_SZAMOK = ("első", "második", "harmadik", "negyedik", "ötödik", "hatodik", "hetedik", "nyolcadik")
SZOVEG = ("# Cím\n\nA mértani sorozat olyan sorozat, amelyben a szomszédos tagok hányadosa állandó. "
          "A hányadost q betűvel jelöljük, és a 2, 6, 18 sorozatban értéke 3. ") + "\n\n" + \
         "\n\n".join(f"A {s} bekezdés egy hosszabb mondata a sorozatok tulajdonságairól szól, példákkal és magyarázattal." for s in _SZAMOK)


def h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


class MertekTest(unittest.TestCase):
    def test_elgepeles_nem_uj(self):
        m = A.mondatok(SZOVEG)
        v = A.valtozas(m, SZOVEG.replace("tulajdonságairól", "tulajdonsagairól", 1))
        self.assertEqual(v.uj_karakter, 0)
        self.assertLess(v.tavolsag, 0.01)

    def test_uj_szakasz_eros(self):
        m = A.mondatok(SZOVEG)
        uj = SZOVEG + "\n\n## Új\n\n" + "\n\n".join(f"Új tartalom {i}: a mértani sor összege véges, ha |q| < 1, ekkor a határérték {i}." for i in range(6))
        ok, v = A.erosen_modosult(m, A.mondatok(uj), 0.2, 600, 400)
        self.assertEqual(ok, "erosen_modosult")
        ok, _ = A.erosen_modosult(m, A.mondatok(SZOVEG + "\n\nEgy új mondat."), 0.2, 600, 400)
        self.assertIsNone(ok)

    def test_uj_jegyzet_hossza(self):
        self.assertEqual(A.erosen_modosult(None, A.mondatok(SZOVEG), 0.2, 600, 400)[0], "uj")
        self.assertIsNone(A.erosen_modosult(None, A.mondatok("Rövid mondat."), 0.2, 600, 400)[0])

    def test_c26_es_c35_a_kozos_peldanyt_hivja(self):
        from modulok.grafikon import automatika as GA
        from modulok.osszefoglalas import automatika as OA
        self.assertIs(OA.mondatok, A.mondatok)
        self.assertIs(OA.valtozas, A.valtozas)
        self.assertIs(GA._kozos(), A)


class DontesTest(unittest.TestCase):
    F = A.Fogyaszto("teszt", "t", kuszob=0.2, csend_perc=10, min_hossz=100)

    def dont(self, sor=None, mtime=0.0, most=10_000.0, md=SZOVEG, f=None):
        return A.dont(f or self.F, "M/a.md", h(md), mtime, most, sor, lambda u: md)

    def test_kuszob_nulla_olvasas_nelkul(self):
        f = A.Fogyaszto("v", "v", kuszob=0, csend_perc=1)
        st, j = A.dont(f, "M/a.md", "h", 0, 1e6, {"hash": "regi"}, lambda u: self.fail("nem olvashat"))
        self.assertEqual((st, j.ok), ("jelolt", "valtozott"))

    def test_bekuldott_de_be_nem_fejezett_ujraproba(self):
        sor = {"hash": h(SZOVEG), "bekuldve": "2026-10-01T10:00:00", "feldolgozva": None}
        self.assertEqual(self.dont(sor, most=1e10)[0], "jelolt")                  # rég beküldve, kész jel nincs
        self.assertEqual(self.dont({**sor, "feldolgozva": "2026-10-01T10:05:00"}, most=1e10)[0], "elbiralt")


class KampoTest(unittest.TestCase):
    """C35b (K309): a fogyasztó két kampója — `tartalom_szuro` (a nem kellő tartalom elbírált) és `kiegeszito` (saját ok a közös mérték után)."""

    def dont(self, f, sor=None, md=SZOVEG):
        return A.dont(f, "M/a.md", h(md), 0.0, 1e6, sor, lambda u: md)

    def test_tartalom_szuro_nem_kell(self):
        f = A.Fogyaszto("v", "v", kuszob=0.2, csend_perc=1, min_hossz=100, tartalom_szuro=lambda md: "xyz" in md)
        self.assertEqual(self.dont(f)[0], "nem_kell")
        self.assertEqual(self.dont(f, md=SZOVEG + " xyz")[0], "jelolt")

    def test_kiegeszito_csak_alappal_es_a_kozos_merteke_utan(self):
        import json
        hivasok = []

        def kieg(md, sor):
            hivasok.append(sor)
            return "sajat"
        f = A.Fogyaszto("v", "v", kuszob=0.2, csend_perc=1, min_hossz=100, kiegeszito=kieg)
        self.assertEqual(self.dont(f)[1].ok, "uj")                                      # nincs alap: a közös „új”
        self.assertEqual(hivasok, [])
        sor = {"alap": json.dumps(sorted(A.mondatok(SZOVEG))), "ujjlenyomat": "x"}
        st, j = self.dont(f, sor, SZOVEG + "\n\nEgy új mondat itt.")
        self.assertEqual((st, j.ok), ("jelolt", "sajat"))
        self.assertEqual(self.dont(A.Fogyaszto("v", "v", kuszob=0.2, csend_perc=1, min_hossz=100, kiegeszito=lambda m, s: None),
                                   sor, SZOVEG + "\n\nEgy új mondat itt.")[0], "nem_eleg")


class AlIndex:
    def __init__(self):
        self.allapot = {}

    def fajl_allapot(self):
        return dict(self.allapot)


class AlSor:
    def __init__(self):
        self.bekuldott, self.fut = [], set()

    def fuggo(self, tipus):
        return tipus in self.fut

    def submit(self, tipus, params):
        self.bekuldott.append((tipus, params))
        return {"id": f"F-{len(self.bekuldott)}"}


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.index, self.sor = AlIndex(), AlSor()
        self.ido = [1_000_000.0]
        self.kapcsolo = [True]
        self._reg = dict(A.REGISZTER)
        A.REGISZTER.clear()
        self.addCleanup(lambda: (A.REGISZTER.clear(), A.REGISZTER.update(self._reg)))
        self.u = A.Utemezo(self.cfg, self.index, self.sor, kapcsolo=lambda: self.kapcsolo[0], indulasi_kesleltetes_mp=180,
                           ora=lambda: self.ido[0])

    def jegyzet(self, ut, md, mtime):
        ir(self.v, ut, md)
        os.utime(self.v / ut, (mtime, mtime))
        self.index.allapot[ut] = (h(md), int(mtime * 1e9), len(md), ut)


class UtemTest(Alap):
    def test_d8_szunet_es_kapcsolo(self):
        A.regisztral(A.Fogyaszto("k", "kt", kuszob=0.2, min_hossz=100))
        self.jegyzet("M/a.md", SZOVEG, 0)
        self.assertEqual(self.u.utem(), {"szunet": True})
        self.ido[0] += 200
        self.kapcsolo[0] = False
        self.assertEqual(self.u.utem(), {"kapcsolo_ki": True})
        self.assertEqual(self.sor.bekuldott, [])
        self.assertFalse(A.ut(self.cfg).exists())                               # semmit nem hozott létre

    def test_bekuldes_kotegelve_es_egy_fuggo(self):
        A.regisztral(A.Fogyaszto("k", "kt", kuszob=0.2, min_hossz=100, koteg=2))
        self.ido[0] += 200
        for i in range(3):
            self.jegyzet(f"M/{i}.md", SZOVEG + f"\n\nKülön mondat {i}.", 1000 + i)
        self.jegyzet("M/friss.md", SZOVEG, self.ido[0] - 60)                   # még változik (csend)
        self.jegyzet("ATTCHMNTS - cards/x.md", SZOVEG, 0)                       # nem tartalmi
        r = self.u.utem()
        self.assertEqual(self.sor.bekuldott, [("kt", {"utak": ["M/0.md", "M/1.md"]})])
        self.assertEqual(r["fogyasztok"]["k"]["allapotok"].get("csend"), 1)
        self.sor.fut.add("kt")
        self.u.utem()
        self.assertEqual(len(self.sor.bekuldott), 1)                            # fut a feladat: nincs második
        self.sor.fut.clear()
        self.u.utem()
        self.assertEqual(self.sor.bekuldott[-1], ("kt", {"utak": ["M/2.md"]}))  # a maradék a következő ütemben
        self.u.utem()
        self.assertEqual(len(self.sor.bekuldott), 2)                            # a beküldött nem megy újra

    def test_kesz_utan_csak_eros_valtozasra(self):
        A.regisztral(A.Fogyaszto("k", "kt", kuszob=0.2, min_hossz=100))
        self.ido[0] += 200
        self.jegyzet("M/a.md", SZOVEG, 1000)
        A.Tar(self.cfg).kesz("k", "M/a.md", SZOVEG, hash_=h(SZOVEG))
        self.assertEqual(self.u.utem()["fogyasztok"]["k"]["bekuldve"], [])
        self.jegyzet("M/a.md", SZOVEG + "\n\nEgy apró kiegészítés.", 2000)
        self.u.esemeny({"tipus": "vault_valtozas", "utak": ["M/a.md"], "torolt": []})
        r = self.u.utem()
        self.assertEqual(r["fogyasztok"]["k"]["allapotok"], {"nem_eleg": 1})
        self.assertEqual(self.sor.bekuldott, [])

    def test_onallo_fogyaszto_es_engedely(self):
        A.regisztral(A.Fogyaszto("v", "vektorindex", kuszob=0, csend_perc=2, onallo=True))
        A.regisztral(A.Fogyaszto("ki", "kikapcsolt", kuszob=0, engedelyezett=lambda cfg: False))
        self.ido[0] += 200
        self.jegyzet("M/a.md", SZOVEG, 1000)
        self.jegyzet("M/b.md", SZOVEG + "x", 1000)
        self.u.utem()
        self.assertEqual(self.sor.bekuldott, [("vektorindex", {})])
        self.u.utem()
        self.assertEqual(len(self.sor.bekuldott), 1)                            # az önálló lépés mindet feldolgozza

    def test_a_fogyaszto_konfig_hibaja_naplozva_es_az_allapotban(self):
        """F6 (2026-10-14): a hibás beállítású fogyasztó kimarad, de az ütem összesítésében (`hiba`) és egyszer a naplóban látszik."""
        import contextlib
        import io

        def rossz(cfg):
            raise ValueError("a [kereses.hibrid] vektor nem logikai")
        A.regisztral(A.Fogyaszto("v", "vektorindex", kuszob=0, csend_perc=2, onallo=True, engedelyezett=rossz))
        self.ido[0] += 200
        self.jegyzet("M/a.md", SZOVEG, 1000)
        naplo = io.StringIO()
        with contextlib.redirect_stderr(naplo):
            r = self.u.utem()
            self.u.utem()
        self.assertIn("nem logikai", r["fogyasztok"]["v"]["hiba"])
        self.assertEqual(self.u.utolso["fogyasztok"]["v"], r["fogyasztok"]["v"])
        self.assertEqual(naplo.getvalue().count("[automatika] v:"), 1)
        self.assertEqual(self.sor.bekuldott, [])

    def test_kimenet_torlese_tilt(self):
        A.regisztral(A.Fogyaszto("k", "kt", kuszob=0.2, min_hossz=100))
        tar = A.Tar(self.cfg)
        tar.kesz("k", "M/a.md", SZOVEG, kimenet="ATTCHMNTS - cards/a — kártyák.md")
        self.u.esemeny({"tipus": "vault_valtozas", "utak": [], "torolt": ["ATTCHMNTS - cards/a — kártyák.md"]})
        self.assertTrue(tar.sor("k", "M/a.md")["tiltva"])
        self.assertEqual(tar.tiltottak()[0]["ut"], "M/a.md")
        self.ido[0] += 200
        self.jegyzet("M/a.md", SZOVEG + "\n\n" + SZOVEG.replace("sorozat", "sor"), 1000)
        self.u.utem()
        self.assertEqual(self.sor.bekuldott, [])                                # a tiltott forrás nem jön újra
        self.assertTrue(tar.felold("k", "M/a.md"))

    def test_teljes_egyeztetes_potolja_a_lemaradt_torlest(self):
        A.regisztral(A.Fogyaszto("k", "kt", kuszob=0.2, min_hossz=100))
        A.Tar(self.cfg).kesz("k", "M/a.md", SZOVEG, kimenet="ATTCHMNTS - cards/a — kártyák.md")
        self.ido[0] += 200
        self.u.utem()                                                            # az indulás teljes egyeztetés: a kimenet nincs az indexben
        self.assertTrue(A.Tar(self.cfg).sor("k", "M/a.md")["tiltva"])


class TaroloTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

    def test_belso_mentes_listajan(self):
        A.Tar(self.cfg).tilt("k", "M/a.md", "teszt")
        self.assertIn("automatika.sqlite", [n for n, _ in mentes.allapot_forrasok(self.cfg)])

    def test_migracio_elott_masolat_es_hibaja_megallit(self):
        A.Tar(self.cfg).tilt("k", "elso", "y")                                # a használt, 1-es sémájú adatbázis
        with mock.patch.object(A, "MIGRACIOK", A.MIGRACIOK + ["CREATE TABLE uj (x);"]):
            with mock.patch("core.mentes.migracio_elott", side_effect=OSError("tele a lemez")):
                with self.assertRaises(sqlite3.DatabaseError):
                    A.Tar(self.cfg).tilt("k", "x", "y")
            with mock.patch("core.mentes.migracio_elott") as ment:
                A.Tar(self.cfg).tilt("k", "x", "y")
                ment.assert_called_once()

    def test_adat_mezo_es_a_regi_1_es_sema_migralasa(self):
        """A 2-es migráció (`adat`): a `kesz` az `adat`-ot tárolja; a régi 1-es sémájú adatbázis sorai megmaradnak."""
        import json
        c = sqlite3.connect(A.ut(self.cfg))
        c.executescript("BEGIN;" + A.MIGRACIOK[0] + "PRAGMA user_version=1; COMMIT;")
        c.execute("INSERT INTO allapot (fogyaszto, ut, hash) VALUES ('k', 'regi.md', 'hh')")
        c.commit()
        c.close()
        with mock.patch("core.mentes.migracio_elott") as ment:
            t = A.Tar(self.cfg)
            t.kesz("k", "uj.md", SZOVEG, hash_="h2", adat={"kepletek": ["a" * 16]})
            ment.assert_called_once()                                                    # a használt adatbázis migrációja előtt másolat
        self.assertEqual(t.sor("k", "regi.md")["hash"], "hh")
        self.assertIsNone(t.sor("k", "regi.md")["adat"])
        self.assertEqual(json.loads(t.sor("k", "uj.md")["adat"]), {"kepletek": ["a" * 16]})
        t.kesz("k", "uj.md", SZOVEG)                                                     # adat nélküli hívás nem törli
        self.assertIsNotNone(t.sor("k", "uj.md")["adat"])

    def test_atvesz_nem_ir_felul_feldolgozott_sort(self):
        t = A.Tar(self.cfg)
        t.atvesz("k", "a.md", ["mondat"], "uj1", {"kepletek": []})
        self.assertEqual(t.sor("k", "a.md")["ujjlenyomat"], "uj1")
        t.atvesz("k", "a.md", ["más"], "uj2")
        self.assertEqual(t.sor("k", "a.md")["ujjlenyomat"], "uj1")

    def test_ujabb_sema_nem_bantja(self):
        A.Tar(self.cfg).tilt("k", "x", "y")
        c = sqlite3.connect(A.ut(self.cfg))
        c.execute("PRAGMA user_version=9")
        c.close()
        A.Tar(self.cfg).tilt("k", "z", "y")
        self.assertEqual(len(A.Tar(self.cfg).tiltottak()), 2)


class AlapFogyasztokTest(unittest.TestCase):
    def test_regisztracio(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        regi = dict(A.REGISZTER)
        self.addCleanup(lambda: (A.REGISZTER.clear(), A.REGISZTER.update(regi)))
        A.REGISZTER.clear()
        A.alap_fogyasztok(cfg)
        # 80(a): AI csak gombra — alapból csak a vektorindex fogyasztó regisztrálódik
        self.assertEqual({n: f.feladattipus for n, f in A.REGISZTER.items()}, {"vektorindex": "vektorindex"})
        self.assertTrue(A.REGISZTER["vektorindex"].onallo)
        for szakasz in ("kartya", "osszefoglalas", "grafikon"):
            self.assertIs(cfg.section(szakasz, "automatika").get("be"), False, szakasz)       # az os.toml dokumentált kulcsa
        for szakasz in ("kartya", "osszefoglalas", "grafikon"):
            cfg.data.setdefault(szakasz, {}).setdefault("automatika", {})["be"] = True
        A.alap_fogyasztok(cfg)
        # CX-011: régi beállítás sem kapcsolhatja vissza az önálló generálást.
        self.assertEqual({n: f.feladattipus for n, f in A.REGISZTER.items()}, {"vektorindex": "vektorindex"})
        self.assertTrue(A.REGISZTER["vektorindex"].onallo)



if __name__ == "__main__":
    unittest.main()
