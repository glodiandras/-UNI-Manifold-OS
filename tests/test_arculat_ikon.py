"""Az app-ikon (C37): a verziókövetett AppIcon.icns, a forrás SVG-k, és a build-lánc összekötése. Hálózat és fordítás
nélkül: a szkript-ellenőrzés a fájlokra és a hivatkozásokra megy; a bájtos reprodukálhatóságot a kézi
`bash shell/ikon/keszit.sh --ellenoriz` bizonyítja (az OS SVG-motorjától függ)."""
import plistlib
import re
import unittest

from tests.helpers import REPO

IKON = REPO / "shell" / "ikon"


class AppIkon(unittest.TestCase):
    def test_icns_verziokovetett_es_ervenyes(self):
        b = (IKON / "AppIcon.icns").read_bytes()
        self.assertEqual(b[:4], b"icns")
        self.assertEqual(int.from_bytes(b[4:8], "big"), len(b))
        # az iconutil mind a tíz iconset-tagot beírja (16–1024 px, a retina párokkal): a TOC-ban a tagok típusai
        tipusok, i = set(), 8
        while i < len(b):
            tipusok.add(b[i : i + 4].decode("ascii"))
            i += int.from_bytes(b[i + 4 : i + 8], "big")
        self.assertEqual(i, len(b))
        for tipus in ("ic04", "ic05", "ic07", "ic08", "ic09", "ic10", "ic11", "ic12", "ic13", "ic14"):
            self.assertIn(tipus, tipusok, tipus)

    def test_forras_svg_a_design_system_szinei(self):
        for nev, szinek in (
            ("manifold-ikon.svg", ("#3d1119", "#f3ece3", "#c23a52")),
            ("manifold-ikon-kicsi.svg", ("#3d1119", "#f3ece3", "#c23a52")),
            ("manifold-ikon-teli.svg", ("#3d1119", "#f3ece3", "#c23a52")),
        ):
            s = (IKON / nev).read_text()
            for sz in szinek:
                self.assertIn(sz, s, f"{nev}: {sz}")
        self.assertIn('stroke="#000000"', (IKON / "manifold-sablon.svg").read_text())

    def test_info_plist_es_build_osszekotve(self):
        info = plistlib.loads((REPO / "shell" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIconFile"], "AppIcon")
        build = (REPO / "shell" / "build.sh").read_text()
        # a build csak másol: a raszterezés (swiftc, iconutil) nem része a build-láncnak
        self.assertIn("ikon/AppIcon.icns", build)
        self.assertNotIn("qlmanage", build)
        self.assertNotIn("iconutil", build)

    def test_generalo_nem_hasznal_qlmanage_vegrehajtast(self):
        """A qlmanage fehér háttérre renderel (a lekerekített sarkok fehérek lennének): a generáló AppKitet használ."""
        s = (IKON / "keszit.sh").read_text()
        futtatott = [sor for sor in s.splitlines() if not sor.lstrip().startswith("#")]
        self.assertFalse(any(re.search(r"\bqlmanage\b", sor) for sor in futtatott))
        self.assertIn("rasztero", s)


if __name__ == "__main__":
    unittest.main()
