"""A K42 próbavault-generátor (`tests/kezi/k42_proba.py`): a generált fa pontosan az Obsidian-összevetés anyaga."""
import contextlib
import io
import unittest
from pathlib import Path

from tests.helpers import tmpdir
from tests.kezi import k42_proba

ELVART = {"AB/J.md", "B/J.md", "A/x.md", "C/x.md"}


def _fa(cel: Path) -> set[str]:
    return {p.relative_to(cel).as_posix() for p in cel.rglob("*") if p.is_file()}


class K42ProbaTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cel = Path(self._t.name) / "k42"

    def _main(self, cel) -> tuple[int, str]:
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            kod = k42_proba.main(["k42_proba.py", str(cel)])
        return kod, ki.getvalue()

    def test_a_fa_pontosan_a_negy_jegyzet(self):
        self.cel.mkdir()
        k42_proba.general(self.cel)
        self.assertEqual(_fa(self.cel), ELVART)
        self.assertEqual({p.relative_to(self.cel).as_posix() for p in self.cel.rglob("*") if p.is_dir()}, {"AB", "B", "A", "C"})

    def test_a_forrasok_a_J_linket_tartalmazzak_a_ket_J_kulonbozik(self):
        self.cel.mkdir()
        k42_proba.general(self.cel)
        for forras in ("A/x.md", "C/x.md"):
            self.assertEqual((self.cel / forras).read_text(encoding="utf-8").strip(), "[[J]]")
        self.assertNotEqual((self.cel / "AB/J.md").read_bytes(), (self.cel / "B/J.md").read_bytes())

    def test_a_2_0_mai_feloldasa_a_T139_szerint(self):
        """A rögzített mai viselkedés: A/x → AB/J (szöveg-előtag), a kontroll C/x → a legrövidebb út (B/J)."""
        self.assertEqual(k42_proba.ma_a_2_0(self.cel), {"A/x.md": "AB/J.md", "C/x.md": "B/J.md"})

    def test_main_ir_listat_es_csak_a_celba_ir(self):
        kod, ki = self._main(self.cel)
        self.assertEqual(kod, 0)
        self.assertEqual(_fa(self.cel), ELVART)
        self.assertEqual(_fa(self.cel.parent), {f"k42/{u}" for u in ELVART})
        for u in ELVART:
            self.assertIn(u, ki)
        self.assertIn("A/x.md → AB/J.md", ki)

    def test_nem_ures_celt_visszautasit(self):
        self.cel.mkdir()
        (self.cel / "mar-van.md").write_text("x", encoding="utf-8")
        kod, ki = self._main(self.cel)
        self.assertEqual(kod, 2)
        self.assertEqual(_fa(self.cel), {"mar-van.md"})
        self.assertIn("nem üres", ki)

    def test_argumentum_nelkul_hasznalatot_ir(self):
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            self.assertEqual(k42_proba.main(["k42_proba.py"]), 2)
        self.assertIn("k42_proba.py", ki.getvalue())


if __name__ == "__main__":
    unittest.main()
