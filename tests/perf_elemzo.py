"""Perf-készlet (T146, M6; C21): az elemző képletsűrű nagy jegyzeten — falióra-kapu. NEM része az alap készletnek (nem `test*.py`):
`bin/mos perf`, tétlen gépen. A viselkedés (a régi, négyzetes kitakarással azonos eredmény) a `tests/test_elemzo_kepletek.py`-ban."""
import time
import unittest

from core.index import elemzo, maszk


def kepletsuru(n: int) -> str:
    sorok = ["---\nTags:\n---\n# Képletek\n"]
    for i in range(n):
        sorok.append(f"A(z) {i}. képlet `kód {i}` és `másik`:\n$$\nx_{{{i}}} = \\frac{{a}}{{b}} + {i}\n$$\nés soron belül $y={i}$.\n")
    return "\n".join(sorok)


class ElemzoPerf(unittest.TestCase):
    def test_10000_blokk_keplet_2_mp_alatt(self):
        t = kepletsuru(10_000)
        t0 = time.perf_counter()
        j = elemzo.elemez(t)
        mp = time.perf_counter() - t0
        self.assertEqual(sum(1 for k in j.kepletek if k["blokk"]), 10_000)
        self.assertEqual(sum(1 for k in j.kepletek if not k["blokk"]), 10_000)
        self.assertLess(mp, 2.0, f"{mp:.2f} s")

    def test_maszk_sok_kodfutam_egy_bekezdesben(self):
        t = " ".join(f"`k{i}`" for i in range(20_000))          # egyetlen bekezdés, 20 000 soron belüli kód
        t0 = time.perf_counter()
        maszk.maszkok(t, frontmatter=False)
        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_hosszu_bekezdes_sorok_linearisan(self):
        """C33: a setext-címsor mintája (`([^\\n]*\\S[^\\n]*)`) soronként négyzetes volt — egy 2421 karakteres jegyzet elemzése
        2,2 ms-ból 90% (a 10 000 jegyzetes hideg építés fele). 200 db 2000 karakteres bekezdés-sor ma ~1 ms nagyságrend."""
        t = "\n\n".join(" ".join(["szó"] * 500) for _ in range(200))
        t0 = time.perf_counter()
        elemzo.elemez(t)
        mp = time.perf_counter() - t0
        self.assertLess(mp, 0.2, f"{mp * 1000:.0f} ms")


if __name__ == "__main__":
    unittest.main()
