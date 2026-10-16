"""F10: the language profile schema (`core/kod_nyelvek.py`) and the toolchain discovery's rules (`modulok/kod/felderites.py`):
every v1 language has a profile, its own calibration key, a run plan; the `.cpp` embedding agrees with C36a; a tool counts
only when its version probe passes in the sandbox, a too broad root is refused, an explicit setting is not second-guessed,
and the xcrun shim is resolved. No download anywhere (D3)."""
import os
import sys
import unittest
from pathlib import Path

from core import config, cpp_teszt
from core import kod_nyelvek as KN
from modulok.kod.felderites import Felderites
from tests.helpers import tmpdir
from tests.kod_segedek import KodCfg, _szkript

MACOS = sys.platform == "darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK)
V1 = ("cpp", "c", "python", "javascript", "typescript", "java", "go", "rust", "swift")


class ProfilTest(unittest.TestCase):
    def test_minden_v1_nyelv_megvan(self):
        self.assertEqual(KN.azonositok(), list(V1))

    def test_egyedi_kiterjesztes_es_kalibracios_kulcs(self):
        kit = KN.kiterjesztesek()
        self.assertEqual(len(kit), len(set(kit)))
        kulcsok = [p.kalibracios_kulcs for p in KN.PROFILOK]
        self.assertEqual(len(kulcsok), len(set(kulcsok)))
        self.assertEqual(KN.profil("cpp").kalibracios_kulcs, "kod")         # C++ keeps the measured C36b task
        self.assertTrue(all(k.startswith("kod_") for k in kulcsok if k != "kod"))

    def test_profil_teljes(self):
        for p in KN.PROFILOK:
            with self.subTest(nyelv=p.azonosito):
                self.assertTrue(p.nev and p.kiterjesztesek and p.forras_nev and p.ai_nyelv and p.kerites)
                self.assertIn(p.motor, ("cpp", "nyelv"))
                self.assertIn(p.eszkozlanc, ("beagyazott", "rendszer"))
                if p.motor == "nyelv":
                    self.assertTrue(p.eszkozok)
                    self.assertTrue(p.fordit)
                    self.assertTrue(p.nativ or p.futtat)
                    nevek = {e.nev for e in p.eszkozok}
                    for tok in (*p.fordit, *p.futtat):
                        if tok.startswith("{eszkoz:"):
                            self.assertIn(tok[8:-1], nevek)
                if p.eszkozlanc == "rendszer":
                    self.assertTrue(p.telepites_tipp)
                pub = p.publikus()
                self.assertEqual(pub["ai_modok"], list(KN.AI_MODOK))

    def test_beagyazas_egyezik_a_c36a_val_cpp_re(self):
        szoveg = "# F\n![[a.cpp]]\n![[b.py|x]]\n![[Sub/c.ts#h]]\n![[d.md]]\n![[e.CPP]]\n"
        self.assertEqual(KN.beagyazott_forrasok(szoveg), ["a.cpp", "b.py", "Sub/c.ts", "e.CPP"])
        cpp = [n for n in KN.beagyazott_forrasok(szoveg) if n.lower().endswith(".cpp")]
        self.assertEqual(cpp, cpp_teszt.beagyazott_cpp(szoveg))

    def test_nyelv_ut(self):
        self.assertEqual(KN.nyelv_ut("Mappa/Feladat.PY").azonosito, "python")
        self.assertIsNone(KN.nyelv_ut("x.mts"))   # AVCHD-videókonténer (a pillanatkép bináris-ként zárja ki): nem TypeScript-forrás
        self.assertEqual(KN.nyelv_ut("x.cts").azonosito, "typescript")
        self.assertIsNone(KN.nyelv_ut("x.md"))

    def test_beallitasok_alap_es_felulirt(self):
        b = KN.beallitasok(None)
        self.assertEqual(b["proba_modell"], "")
        self.assertEqual(KN.nyelv_beallitas({**b, "extra_exec": ["/a"], "nyelv": {"go": {"extra_exec": ["/b"]}}}, "go")["extra_exec"],
                         ["/a", "/b"])
        self.assertIn("kod", config.load().data)                             # the shipped [kod] section


@unittest.skipUnless(MACOS, "[indokolt] nincs sandbox-exec (csak macOS)")
class FelderitesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.alap = config.load()

    def fd(self, kod: dict, **kw) -> Felderites:
        return Felderites(KodCfg(self.alap, kod), **kw)

    def test_a_probat_elbukó_csonk_nem_eszkoz(self):
        """Like the macOS `/usr/bin/java` without a JDK: present and executable, but the probe fails."""
        csonk = _szkript(self.t / "jdk" / "bin" / "java", 'echo "Unable to locate a Java Runtime." >&2; exit 1\n')
        _szkript(self.t / "jdk" / "bin" / "javac", 'echo "Unable to locate a Java Runtime." >&2; exit 1\n')
        st = self.fd({"eszkozok": {"java": str(csonk), "javac": str(self.t / "jdk" / "bin" / "javac")},
                      "extra_exec": ["/bin"]}).nyelv(KN.profil("java"))
        self.assertFalse(st["elerheto"])
        self.assertEqual(st["hiba"]["kod"], "kod.nincs_eszkozlanc")
        self.assertEqual(st["hiba"]["param"]["hianyzo"], "javac, java")
        self.assertTrue(st["eszkozok"][0]["probak"])

    def test_tul_tag_gyoker_elutasitva(self):
        e = KN.Eszkoz("go", ("go",), gyoker_szint=2)
        d = self.fd({"eszkozok": {"go": "/bin/sh"}}).eszkoz(e)     # root would be "/"
        self.assertFalse(d["ok"])
        self.assertIn("too broad", d["probak"][0]["hiba"])

    def test_explicit_beallitas_nem_esik_vissza_path_ra(self):
        d = self.fd({"eszkozok": {"node": str(self.t / "nincs")}}, which=lambda n: "/usr/local/bin/node").eszkoz(
            KN.profil("javascript").eszkozok[0])
        self.assertFalse(d["ok"])
        self.assertEqual([p["forras"] for p in d["probak"]], ["konfig"])

    def test_xcrun_shim_feloldasa(self):
        valodi = _szkript(self.t / "CLT" / "usr" / "bin" / "swiftc", 'echo "Swift version 9.9 (mock)"\n')
        hivasok = []

        def futtato(argv, timeout):
            hivasok.append(argv)
            if argv[1:] == ["--find", "swiftc"]:
                return 0, str(valodi) + "\n"
            return 1, ""
        # the PATH entry is a shim under /usr/bin (any existing file there: `true`)
        fd = self.fd({"extra_exec": ["/bin"]}, which={"swiftc": "/usr/bin/true", "xcrun": "xcrun"}.get, futtato=futtato)
        d = fd.eszkoz(KN.profil("swift").eszkozok[0])
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["valos"], str(valodi))
        self.assertEqual(d["gyoker"], str(self.t / "CLT"))
        self.assertIn(["xcrun", "--find", "swiftc"], hivasok)

    def test_cpp_profil_a_c36a_eszkoztarat_jelenti(self):
        st = Felderites(self.alap).nyelv(KN.profil("cpp"))
        self.assertEqual(st["eszkozok"][0]["nev"], "clang++")
        self.assertIn("elerheto", st)


if __name__ == "__main__":
    unittest.main()
