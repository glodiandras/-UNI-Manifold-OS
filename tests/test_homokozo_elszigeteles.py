"""Javító 1 (Audit 3: A3-02, A3-15, A3-16): a CAS-homokozó feladatonkénti elszigetelése és a protokoll szigorú olvasása.

Ezek a tesztek a **protokollt és a szülő-oldali őrzést** mérik, nem a `sandbox-exec` profilt: egy ál-`sandbox-exec`
(a `-f`/`-D` kapcsolókat elhagyja, a maradékot exec-eli) alatt futnak, így Linuxon és macOS-en is. A profil-próbák a
`test_homokozo.py`-ban maradnak (csak macOS). A támadások a SymPy `sympify`-án át mennek (a fehérlista nem határ):
- a gyermek `vegrehajt` függvényének felülírása (a köteg későbbi tételeinek hamisítása);
- előre gyártott eredmény-sorok írása a protokoll-leíróra."""
import os
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import tmpdir

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "modulok"))
from homokozo import Homokozo, memoria, proba  # noqa: E402

AL_SANDBOX = """#!/bin/sh
# ál-sandbox-exec (csak teszt): a -f PROFIL és a -D K=V kapcsolókat elhagyja, a maradékot exec-eli
while [ $# -gt 0 ]; do
  case "$1" in
    -f|-D) shift 2 ;;
    *) break ;;
  esac
done
exec "$@"
"""

HAMIS = proba.HAMIS
BECSULETES, HIVAS = proba.BECSULETES, proba.HIVAS
vegrehajt_csere, elore_gyartott_sorok = proba.vegrehajt_csere, proba.elore_gyartott_sorok


def al_sandbox(mappa: Path) -> str:
    p = Path(mappa) / "sandbox-exec"
    p.write_text(AL_SANDBOX)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return str(p)


class _Alap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.sb = al_sandbox(Path(cls._t.name))
        cls.hk = Homokozo(None, sandbox_exec=cls.sb, idokorlat_s=20.0)

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()


class ElszigetelesTest(_Alap):
    """A3-02: a `kod` után a gyermek leáll; a `hivas` soha nem fut olyan gyermekben, amelyben `kod` futott."""

    def test_a_kontroll_a_tamadas_nelkul_helyes(self):
        e = self.hk.futtat([BECSULETES, HIVAS])
        self.assertEqual([x["allapot"] for x in e], ["ok", "ok"], e)
        self.assertEqual(e[0]["ertek"], {"tipus": "halmaz", "elemek": ["-2", "2"]})
        self.assertEqual(e[1]["ertek"], "ok")

    def test_a_vegrehajt_csereje_utan_a_kovetkezo_feladat_erintetlen(self):
        e = self.hk.futtat([vegrehajt_csere(), BECSULETES, HIVAS, BECSULETES])
        self.assertEqual(e[1]["allapot"], "ok", e)
        self.assertEqual(e[1]["ertek"], {"tipus": "halmaz", "elemek": ["-2", "2"]})
        self.assertEqual(e[2]["ertek"], "ok")
        self.assertEqual(e[3]["ertek"], {"tipus": "halmaz", "elemek": ["-2", "2"]})

    def test_elore_gyartott_sor_nem_fogadhato_el(self):
        e = self.hk.futtat([elore_gyartott_sorok(), BECSULETES, HIVAS])
        self.assertEqual(e[0]["allapot"], "homokozo_hiba", e[0])       # a hamis (nonce nélküli) sor a saját tételét buktatja
        self.assertEqual(e[1]["ertek"], {"tipus": "halmaz", "elemek": ["-2", "2"]}, e[1])
        self.assertEqual(e[2]["ertek"], "ok")

    def test_a_kod_utan_uj_gyermek_a_hivasok_egy_gyermekben(self):
        pidek: list[int] = []
        eredeti = Homokozo._indit

        def figyelt(self_, mem):
            gy, ok = eredeti(self_, mem)
            if gy is not None:
                pidek.append(gy.proc.pid)
            return gy, ok

        with mock.patch.object(Homokozo, "_indit", figyelt):
            e = self.hk.futtat([HIVAS, HIVAS, BECSULETES, HIVAS, BECSULETES, BECSULETES])
        self.assertTrue(all(x["allapot"] == "ok" for x in e), e)
        # [H, H, K] egy gyermek (a K a végén leállítja) · [H, K] · [K]
        self.assertEqual(len(pidek), 3, pidek)

    def test_a_proba_keszlet_elszigetelesi_probai_rendben(self):
        for r in proba.elszigetelesi_probak_futtat(self.hk):
            self.assertTrue(r["rendben"], r)


class ProtokollTest(_Alap):
    """A3-15: a gyermek sora szigorúan: szótár, csak ismert kulcsok és típusok, az elvárt azonosítóval."""

    def _sor(self, sor: bytes) -> dict:
        """A gyermek a saját feladata közben minden nyitott leíróra (a protokoll-leíróra is) `sor`-t ír."""
        return self.hk.egy(proba.leirora_ir(sor))

    def test_nem_szotar_sor_homokozo_hiba(self):
        e = self._sor(b"[1]\n")
        self.assertEqual(e["allapot"], "homokozo_hiba", e)

    def test_ismeretlen_kulcs_homokozo_hiba(self):
        e = self.hk.egy(proba.sajat_azonositoval(dict(HAMIS, csucs_mb=0.0)))
        self.assertEqual(e["allapot"], "homokozo_hiba", e)
        self.assertIn("ismeretlen kulcs", e["uzenet"])

    def test_a_szulo_allapotai_a_gyermektol_nem_fogadhatok_el(self):
        e = self.hk.egy(proba.sajat_azonositoval(dict(HAMIS, allapot="kimenet_tullepes")))
        self.assertEqual(e["allapot"], "homokozo_hiba", e)

    def test_a_sajat_azonositoval_a_sajat_tetelet_hamisithatja_mast_nem(self):
        """A dokumentált határ: a `kod` a saját eredményét meghamisíthatja (mint az EREDMENY-t), a következőét nem."""
        e = self.hk.futtat([proba.sajat_azonositoval(HAMIS), BECSULETES])
        self.assertEqual(e[0]["ertek"], HAMIS["ertek"], e[0])
        self.assertEqual(e[1]["ertek"], proba.BECSULETES_ERTEK, e[1])

    def test_ismeretlen_allapot_homokozo_hiba(self):
        from homokozo import _ertelmez
        self.assertEqual(_ertelmez({"azonosito": "a", "allapot": "csoda"}, "a")[0], "homokozo_hiba")

    def test_az_ertelmezo_szabalyai(self):
        from homokozo import _ertelmez
        jo = {"azonosito": "n1", "allapot": "ok", "ertek": {"tipus": "logikai", "ertek": True}, "uzenet": "",
              "mp": 0.1, "kimenet": "x"}
        self.assertEqual(_ertelmez(jo, "n1")[0], "ok")
        for rossz in ([1], "ok", None, 5, dict(jo, azonosito="n2"), {k: v for k, v in jo.items() if k != "azonosito"},
                      dict(jo, allapot="homokozo_hiba"), dict(jo, allapot="kimenet_tullepes"), dict(jo, uzenet=5),
                      dict(jo, mp="1"), dict(jo, mp=True), dict(jo, mp=-1), dict(jo, kimenet=[1]), dict(jo, extra=1),
                      {k: v for k, v in jo.items() if k != "allapot"}):
            self.assertEqual(_ertelmez(rossz, "n1")[0], "homokozo_hiba", rossz)


class MatekCasTest(unittest.TestCase):
    """A3-02 a pontozón: a `matek_cas` a változott szerződéssel becsületes bemenetre a régi pontszámot adja, és egy
    támadó modellválasz a többi válasz pontszámát nem változtatja meg."""

    JO = ("Terv: szorzattá alakítás.\n```python\nimport sympy as sp\nx = sp.Symbol('x', real=True)\n"
          "EREDMENY = sp.solveset(2*x**3 - 5*x**2 - 3*x, x, sp.S.Reals)\n```")
    HAMIS = "```python\nimport sympy as sp\nx = sp.Symbol('x', real=True)\nEREDMENY = sp.FiniteSet(6, 26)\n```"
    TILTOTT = "```python\nimport os\nEREDMENY = os.listdir('/')\n```"

    def setUp(self):
        from tests.eval_segedek import eval_cfg, feladat
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = eval_cfg(self._t.name)
        self.m = feladat(self.cfg, "matek_cas")
        self.t = {x["id"]: x for x in self.m.tetelek(self.cfg)}
        self.hk = Homokozo(self.cfg, sandbox_exec=al_sandbox(Path(self._t.name)))

    def test_becsuletes_bemenetre_a_regi_pontszam(self):
        from tests.eval_segedek import rekord
        p = self.m.pontoz([rekord(self.t["m01"], self.JO), rekord(self.t["m02"], self.HAMIS),
                           rekord(self.t["m02"], self.TILTOTT)], homokozo=self.hk)
        self.assertEqual(p["helyes"], 1)                         # ugyanaz, mint a macOS-es `test_pontozo_a_valodi_homokozoban`
        self.assertEqual(p["allapotok"], {"ok": 2, "tiltott": 1})

    def test_a_tamado_valasz_a_tobbi_pontszamat_nem_valtoztatja(self):
        from tests.eval_segedek import rekord
        tamado = "```python\n" + vegrehajt_csere()["kod"] + "\n```"
        gyart = "```python\n" + elore_gyartott_sorok()["kod"] + "\n```"
        rek = [rekord(self.t["m02"], tamado), rekord(self.t["m01"], self.JO), rekord(self.t["m02"], gyart),
               rekord(self.t["m02"], self.HAMIS), rekord(self.t["m01"], self.JO)]
        p = self.m.pontoz(rek, homokozo=self.hk)
        self.assertEqual(p["helyes"], 2, p)
        rossz = {r["id"] for r in p["rossz"]}
        self.assertEqual(rossz, {"m02"})
        self.assertEqual(p["allapotok"].get("homokozo_hiba"), 1, p)       # az előre gyártott sor


class MemoriaorTest(_Alap):
    """A3-16: ha az élő gyermek memóriája nem olvasható, zárva hibázik (nem fut tovább őr nélkül)."""

    def test_a_linuxos_meres_mukodik(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("[indokolt] a /proc-os mérés Linux-specifikus; macOS-en a proc_pid_rusage (K141)")
        self.assertGreater(memoria.mb(os.getpid()) or 0, 1)
        self.assertGreaterEqual(memoria.csoport_mb(os.getpgrp()) or 0, memoria.mb(os.getpid()) * 0.9)

    def test_olvashatatlan_memoria_homokozo_hiba(self):
        hk = Homokozo(None, sandbox_exec=self.sb, idokorlat_s=20.0)
        with mock.patch.object(memoria, "mb", return_value=None):
            e = hk.egy(BECSULETES)
        self.assertEqual(e["allapot"], "homokozo_hiba", e)
        self.assertIn("memória", e["uzenet"])


if __name__ == "__main__":
    unittest.main()
