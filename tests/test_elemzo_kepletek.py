"""T146 (C21): az elemző egymenetes blokk-képlet-kitakarása és a `_bekezdes_vege` bekezdésenkénti gyorsítótára a korábbi (négyzetes)
algoritmussal azonos eredményt ad. A falióra-kapu a perf-készletben: `tests/perf_elemzo.py`."""
import random
import unittest

from core.index import elemzo, maszk
from core.index.elemzo import _KEPLET_BLOKK, _KEPLET_SOR


def regi_kepletek(txt: str) -> list[dict]:
    """A C21 előtti algoritmus (képletenkénti szelet-összefűzés) — referenciának."""
    j = elemzo.Jegyzet(tartalom=txt)
    poz = elemzo._Sorok(txt)
    mk, _ = maszk.maszkok(txt)
    fm = elemzo.FM_RE.match(txt)
    fm_veg = fm.end() if fm else 0
    import re
    torzs = re.sub(r"[^\n]", " ", mk[:fm_veg]) + mk[fm_veg:]
    kepletes = torzs
    for m in _KEPLET_BLOKK.finditer(torzs):
        j.kepletek.append({"sor": poz(m.start())[0], "sor_veg": poz(m.end())[0], "kezd": m.start(), "veg": m.end(), "blokk": True,
                           "forras": m.group(1).strip()})
        kepletes = kepletes[:m.start()] + " " * (m.end() - m.start()) + kepletes[m.end():]
    for m in _KEPLET_SOR.finditer(kepletes):
        s = poz(m.start())[0]
        j.kepletek.append({"sor": s, "sor_veg": s, "kezd": m.start(), "veg": m.end(), "blokk": False,
                           "forras": m.group(1) or m.group(2)})
    j.kepletek.sort(key=lambda k: k["kezd"])
    return j.kepletek


class KepletKitakarasTest(unittest.TestCase):
    def test_azonos_a_regi_algoritmussal(self):
        rnd = random.Random(21)
        darabok = ["$$a=b$$", "$x$", "$$\n\\frac{1}{2}\n$$", "szöveg ", "`kód $x$`", "\n\n", "$ 5 és $6", "$$ $y$ $$", "\\$",
                   "```\n$$z$$\n```\n", "- $a$ lista\n", "$a$$b$", "$$", "$"]
        for _ in range(300):
            t = "".join(rnd.choice(darabok) for _ in range(rnd.randint(1, 30)))
            if rnd.random() < 0.3:
                t = "---\nTags: $x$\n---\n" + t
            with self.subTest(t=t):
                self.assertEqual(elemzo.elemez(t).kepletek, regi_kepletek(t))

    def test_kodfutam_tobb_bekezdesben(self):
        t = "a `x` b `y`\nfolytatás `z`\n\nmásik `w\n\n` nem zár\n- lista `q`\n`r`"
        km, _ = maszk.maszkok(t, frontmatter=False)
        self.assertEqual(len(km), len(t))
        for kod in ("`x`", "`y`", "`z`", "`q`", "`r`"):
            self.assertNotIn(kod, km)
        self.assertIn("`w", km)                                    # a bekezdéshatáron át nem zár


if __name__ == "__main__":
    unittest.main()
