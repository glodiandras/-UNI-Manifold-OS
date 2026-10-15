"""A higiénia-háttérszámítás hatása a szerkesztő mentési útjára (C30a; `bin/mos perf`, tétlen gépen — NEM része az alap készletnek).

A mérés a szerkesztő automatikus mentésének kiszolgáló útját veszi: `Vault.write` (a `PUT /api/vault/fajl` törzse: kör-zár,
atomi csere, pillanatkép) + az index frissítése (`Index.frissit`), egy 3000 jegyzetes szintetikus vaulton, **két helyzetben**:
tétlenül és úgy, hogy közben a háttérszolgáltatás a teljes riportot számolja (szünet-pont nélkül, aktív használat nélkül — a
legrosszabb eset: a számítás végig fut, miközben mentünk). A kapu: a számítás közbeni p95 nem nő a tétlenhez képest a `KAPU`
szorosánál (a két mérés zaja miatt laza), és a mentés sosem várakozik a riportra. A valódi appos gépelési késleltetés a C30b kapuja.
A szolgáltatás szünet-pontjai (aktív használat alatt nem számol) a `tests/test_asszisztens_szolgalat.py`-ban vannak bizonyítva."""
import statistics
import threading
import time
import unittest

from core import snapshot, vaultio
from core.asszisztens.allapot import Allapot
from core.asszisztens.szolgalat import HigieniaSzolgalat
from core.higienia import Higienia
from core.tulajdonsagok import Tulajdonsagok
from tests.bazis_teljesitmeny_segedek import szintetikus
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

DB = 3000
MENTES = 40
KAPU = 3.0                 # a számítás közbeni p95 legfeljebb ennyiszerese a tétlennek (a GIL-verseny enyhe, a mentés nem vár a riportra)
ABSZOLUT_KORLAT_MS = 250   # …és semmi esetre sem több ennél


def p95(lista: list[float]) -> float:
    return sorted(lista)[max(0, int(len(lista) * 0.95) - 1)]


class MentesiUtPerf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, _, v = alg_core(cls._t.name)
        cls.v = v
        szintetikus(v, DB)
        for i in range(0, DB, 10):
            ir(v, f"Hibas/H{i}.md", f"---\nTags:\n  - Ismeretlen\n---\n[[Nincs {i}]] $\\frac{{a}}{{b$ ![[nincs{i}.png]]\n")
        ir(v, "Szerkesztett.md", "# Szerkesztett\nszöveg\n")
        cls.repo = snapshot.repos(cls.cfg)["vault"]
        cls.repo.init()
        cls.repo.commit("alap", {"Mos-Forras": "kezi"})
        cls.ix, _ = index_indit(cls.cfg)
        cls.vault = vaultio.Vault(cls.cfg, publish=lambda *a, **k: None, sajat=cls.ix.vart_iras)
        h = Higienia(cls.cfg, cls.ix, Tulajdonsagok(cls.cfg, cls.ix))
        cls.sz = HigieniaSzolgalat(cls.cfg, cls.ix, h, Allapot(cls.cfg), aktiv=lambda: False, szunet_mp=0.05)

    @classmethod
    def tearDownClass(cls):
        cls.sz.leallit()
        cls.ix.leallit()
        cls._t.cleanup()

    def mentesek(self, db: int) -> list[float]:
        idok = []
        hash_ = self.vault.read("Szerkesztett.md")["hash"]
        for i in range(db):
            t0 = time.perf_counter()
            r = self.vault.write({"ut": "Szerkesztett.md", "tartalom": f"# Szerkesztett\nszöveg {i}\n", "alap": hash_})
            self.assertTrue(self.ix.frissit(["Szerkesztett.md"]))
            idok.append((time.perf_counter() - t0) * 1000)
            hash_ = r["hash"]
        return idok

    def test_a_mentes_nem_var_a_riportra(self):
        self.mentesek(5)                                     # bemelegítés
        tetlen = self.mentesek(MENTES)
        szamolt, kesz = [], threading.Event()

        def hatter():
            self.sz.szamol()
            kesz.set()
        szal = threading.Thread(target=hatter, daemon=True)
        t0 = time.perf_counter()
        szal.start()
        while not kesz.is_set() and len(szamolt) < MENTES * 5:        # amíg a riport fut, folyamatosan mentünk
            szamolt += self.mentesek(1)
        szal.join(60)
        riport_ms = (time.perf_counter() - t0) * 1000
        self.assertTrue(self.sz.osszegzes()["kesz"])
        print(f"\nmentési út ({DB} jegyzet): tétlen p50 {statistics.median(tetlen):.1f} ms, p95 {p95(tetlen):.1f} ms; "
              f"riport közben {len(szamolt)} mentés, p50 {statistics.median(szamolt):.1f} ms, p95 {p95(szamolt):.1f} ms, "
              f"max {max(szamolt):.1f} ms; a riport {riport_ms:.0f} ms alatt kész ({self.sz.osszegzes()['ossz']} tétel)")
        self.assertLess(p95(szamolt), max(p95(tetlen) * KAPU, 25.0))
        self.assertLess(max(szamolt), ABSZOLUT_KORLAT_MS)


if __name__ == "__main__":
    unittest.main()
