"""A betöltő négy szabálya álmodellel (L22–L28): közös zár, keret, szűk cache + darabolt beolvasás, őr."""
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

from core.modell import beallitas as B
from core.modell.betolto import KeretHiba
from core.modell.hatter import BetoltesHiba, gyar
from core.modell.zar import Zar, ZarFoglalt
from tests.helpers import REPO, alg_core, tmpdir
from tests.modell_segedek import AlHatter, al_betolto, beallitas

MINTA = re.compile(r"^pid \d+ · \S+ · \d\d:\d\d:\d\d$")


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)


class ZarTest(Alap):
    def test_a_zar_utja_es_felulirasa(self):
        self.assertEqual(self.b.zar, self.cfg.path("state") / "modell.lock")
        b = B.betolt(self.cfg, {"MANIFOLD_MODELL_ZAR": str(Path(self._t.name) / "masik.lock")})
        self.assertEqual(b.zar, Path(self._t.name) / "masik.lock")

    def test_a_klon_workere_ugyanazt_a_zarat_tartja(self):
        """T010 (L23): a klónos próba (`proba_app`, `_kornyezet.elkulonit`) külön `MOS_STATE`-et kap, de a valódi
        configból számolt zárat adja át `MANIFOLD_MODELL_ZAR`-ként — különben a próba és az éles két modellt tölthetne
        be egyszerre (2026-09-23: két párhuzamos modell 14 GB-ot foglalt a 16-ból)."""
        from core import config
        valodi = self.b.zar
        klon_env = {"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
                    "MOS_STATE": str(Path(self._t.name) / "klon" / "state"), "MANIFOLD_MODELL_ZAR": str(valodi)}
        kcfg = config.load(klon_env)
        self.assertNotEqual(kcfg.path("state"), self.cfg.path("state"))
        self.assertEqual(B.betolt(kcfg, klon_env).zar, valodi)
        # a zár nélküli átadás külön zárat adna: ez a hiba, amit a segéd megelőz
        self.assertNotEqual(B.betolt(kcfg, {}).zar, valodi)
        elso = Zar(valodi)
        elso.megszerez("eles/modell")
        self.addCleanup(elso.elenged)
        with self.assertRaises(ZarFoglalt):
            Zar(B.betolt(kcfg, klon_env).zar).megszerez("klon/modell", varakozas=0.2)

    def test_masik_folyamat_tartja_a_masodik_var(self):
        # T085: a másik folyamat addig tartja a zárat, amíg a stdin-jén jelet nem kap (nem fix `sleep(1.0)`: terhelt
        # gépen a tartás lejárhatott, mielőtt a „foglalt” ellenőrzés lefutott)
        kod = ("import sys; sys.path.insert(0, %r); from core.modell.zar import Zar; "
               "z = Zar(%r); z.megszerez('mas/modell'); print('fog', flush=True); sys.stdin.readline(); z.elenged()"
               % (str(REPO), str(self.b.zar)))
        p = subprocess.Popen([sys.executable, "-B", "-c", kod], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.wait)
        self.addCleanup(lambda: p.stdin.closed or p.stdin.close())
        self.assertEqual(p.stdout.readline().strip(), "fog")
        z = Zar(self.b.zar)
        self.assertRegex(z.tartalom(), r"mas/modell")
        with self.assertRaises(ZarFoglalt):
            z.megszerez("en/modell", varakozas=0.2)

        def elenged():
            p.stdin.write("\n")
            p.stdin.flush()

        import threading
        threading.Timer(0.4, elenged).start()
        t0 = time.monotonic()
        z.megszerez("en/modell")                       # vár, amíg a másik elengedi
        self.assertGreater(time.monotonic() - t0, 0.3)
        self.assertRegex(z.tartalom(), MINTA)
        z.elenged()
        self.assertEqual(z.tartalom(), "")
        p.stdout.close()


class KeretTest(Alap):
    def test_keretbe_nem_fero_nem_indul(self):
        bt = al_betolto(self.b)
        with self.assertRaises(KeretHiba):
            bt.general(self.b.modell("gemma4_12b"), [{"content": "x"}], self.b.keret_gb("munka"))
        self.assertEqual(AlHatter.naplo, [])
        r = bt.general(self.b.modell("gemma4_12b"), [{"content": "x"}], self.b.keret_gb("tavol"))
        self.assertEqual(r["text"], "gemma4_12b: válasz")

    def test_nevesitett_keretek_es_kornyezeti_felulirás(self):
        self.assertEqual((self.b.keret_gb("munka"), self.b.keret_gb("tavol"), self.b.keret_gb(None)), (5.0, 9.0, 5.0))
        b = B.betolt(self.cfg, {"MANIFOLD_MODELL_KERET_GB": "3"})
        self.assertEqual(b.keret_gb("tavol"), 3.0)
        with self.assertRaises(KeretHiba):
            al_betolto(b).betolt(b.modell("qwen3_vl_4b"), b.keret_gb("munka"))

    def test_cache_es_darabolt_beolvasas_a_hattereig_jut(self):
        bt = al_betolto(self.b)
        r = bt.general(self.b.modell("qwen3_vl_4b"), [{"content": "x"}], 5.0)
        self.assertEqual((r["prefill"], r["temp"]), (256, 0.0))
        self.assertIn(("betolt", "qwen3_vl_4b", 0.25), AlHatter.naplo)

    def test_egyszerre_egy_modell_a_zar_koveti(self):
        bt = al_betolto(self.b)
        bt.general(self.b.modell("qwen3_vl_4b"), [{"content": "a"}], 5.0)
        self.assertIn("Qwen3-VL-4B", bt.zar.tartalom())
        bt.general(self.b.modell("qwen35_2b"), [{"content": "b"}], 5.0)
        self.assertIn(("urit", "qwen3_vl_4b"), AlHatter.naplo)
        self.assertIn("Qwen3.5-2B", bt.zar.tartalom())
        bt.urit()
        self.assertEqual(bt.zar.tartalom(), "")
        self.assertFalse(bt.zar.tartja)

    def test_hattertelen_es_konvertalando_modell(self):
        for nev, szoveg in (("whisper_large_v3_hu", "konvertálni"), ("parakeet_v3", "C20"),
                            ("qwen3_reranker_06b", "C25")):
            with self.assertRaisesRegex(BetoltesHiba, szoveg):
                gyar(self.b.modell(nev))


class OrTest(Alap):
    def test_szukos_memorianal_kiurit_es_kivarja_a_helyreallast(self):
        sor = iter([60, 10, 30, 30, 60, 60, 60, 60, 60, 60, 60])
        bt = al_betolto(self.b, mem=lambda: next(sor, 60))
        m = self.b.modell("qwen3_vl_4b")
        bt.general(m, [{"content": "első"}], 5.0)
        bt.general(m, [{"content": "második"}], 5.0)
        self.assertEqual(bt.szunetek, 1)
        esemenyek = [e[0] for e in AlHatter.naplo]
        self.assertEqual(esemenyek, ["betolt", "general", "urit", "betolt", "general"])

    def test_a_visszatoltes_a_modell_sajat_reszevel_szamol(self):
        # 20 + 5 + 100·4,6/16 ≈ 53,8 % (K80, 2026-10-07: a qwen3_vl_4b csúcsa 4,0 → 4,6): az 50 % nem elég, csak az 55
        latott = []
        sor = iter([10, 45, 50, 50, 55, 55, 55])

        def mem():
            v = next(sor, 55)
            latott.append(v)
            return v
        bt = al_betolto(self.b, mem=mem)
        bt.general(self.b.modell("qwen3_vl_4b"), [{"content": "x"}], 5.0)
        self.assertGreaterEqual(latott.count(55), 2)
        self.assertGreaterEqual(latott.count(50), 2)                   # az 50 % már nem volt elég (a régi küszöb)

    def test_gpu_memoriahiba_ujraprobal_majd_felad(self):
        bt = al_betolto(self.b, hibak=2)
        r = bt.general(self.b.modell("qwen3_vl_4b"), [{"content": "x"}], 5.0)
        self.assertIn("válasz", r["text"])
        self.assertEqual(bt.szunetek, 2)
        bt.urit()                                      # a második betöltő ugyanarra a gépszintű zárra várna
        bt = al_betolto(self.b, hibak=5)
        with self.assertRaisesRegex(RuntimeError, "Insufficient Memory"):
            bt.general(self.b.modell("qwen3_vl_4b"), [{"content": "x"}], 5.0)

    def test_offline_betoltes(self):
        # a helyi út a local_files_only-val keres: a nem letöltött modell érthető hibát ad, hálózat nélkül
        from core.modell.hatter import helyi_ut
        with self.assertRaisesRegex(BetoltesHiba, "mos models pull"):
            helyi_ut(self.b.modell("qwen3_vl_4b"), str(self.root / "var" / "models" / "hub"))


if __name__ == "__main__":
    unittest.main()
