"""A WS-kiesés védelmei a core oldalán (C29.7b, 2. audit T107, 1. audit L7, 28(c)):

  - a lassú kliens túlcsordult sora `kimaradt` jelzést kap (nem veszít némán eseményt);
  - a bontott kapcsolat mentetlen-halmaza türelmi ideig megmarad, hogy a gép a visszacsatlakozó felület szövege mellé ne
    írjon (28(c)); az új kapcsolat teljes halmaza (amely a `hello` után azonnal jön) vagy a lejárat felszabadítja;
  - a háttér-újrapróba késői indulási üzenete WS-eseményként megy, ha van kapcsolat.
"""
import fcntl
import json
import unittest

from core import events, frame, server
from tests import osszeomlas as o
from tests.helpers import alg_core, tmpdir


class KimaradtTest(unittest.TestCase):
    def test_tul_lassu_kliens_kimaradt_jelzest_kap(self):
        bus = events.Bus()
        s = bus.subscribe()
        for i in range(events.MAX_SOR + 5):
            bus.publish({"tipus": "x", "i": i})
        els = s.get(timeout=0.1)
        self.assertEqual(els, {"tipus": "kimaradt", "db": 5})
        self.assertEqual(s.get(timeout=0.1)["i"], 5, "a megtartott események a jelzés után jönnek, sorrendben")
        sorban = [s.get(timeout=0.1) for _ in range(events.MAX_SOR - 1)]
        self.assertEqual([e["i"] for e in sorban], list(range(6, events.MAX_SOR + 5)))
        self.assertIsNone(s.get(timeout=0.05))
        self.assertEqual(events.Bus().subscribe().get(timeout=0.01), None)

    def test_kimaradt_nullazodik_es_ujra_jelez(self):
        bus = events.Bus()
        s = bus.subscribe()
        for i in range(events.MAX_SOR + 1):
            bus.publish({"tipus": "x", "i": i})
        self.assertEqual(s.get(timeout=0.1)["db"], 1)
        while s.get(timeout=0.01) is not None:
            pass
        for i in range(events.MAX_SOR + 3):
            bus.publish({"tipus": "y", "i": i})
        self.assertEqual(s.get(timeout=0.1), {"tipus": "kimaradt", "db": 3})

    def test_nincs_tulcsordulas_nincs_jelzes(self):
        bus = events.Bus()
        s = bus.subscribe()
        bus.publish({"tipus": "x"})
        self.assertEqual(s.get(timeout=0.1), {"tipus": "x"})


class _Kapcsolat:
    """A `websocket.Connection` helyett: az `App` csak tárolja (és leálláskor lezárja)."""

    def close(self, kod=1000):
        pass


class TurelemTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.app = server.App(self.cfg, start_delay=0)
        self.addCleanup(self.app.queue.close, 0)
        self.addCleanup(self.app.index.leallit)
        self.ido = [1000.0]
        self.app._ora = lambda: self.ido[0]

    def _ws(self, utak=None):
        c = _Kapcsolat()
        self.assertTrue(self.app.add_ws(c))
        if utak is not None:
            self.app.ws_uzenet(c, '{"tipus": "mentetlen", "utak": %s}' % json.dumps(utak))
        return c

    def test_bontas_utan_a_halmaz_a_turelmi_idoig_marad(self):
        c = self._ws(["T01/a.md"])
        self.assertEqual(self.app.mentetlen_utak(), {"T01/a.md"})
        self.app.drop_ws(c)
        self.assertEqual(self.app.mentetlen_utak(), {"T01/a.md"}, "a bontás pillanatában a gép még nem írhat bele")
        self.ido[0] += self.app.mentetlen_turelem_mp - 0.5
        self.assertEqual(self.app.mentetlen_utak(), {"T01/a.md"})
        self.ido[0] += 1
        self.assertEqual(self.app.mentetlen_utak(), set(), "a türelmi idő lejárt")

    def test_az_uj_kapcsolat_teljes_halmaza_felszabadit(self):
        c = self._ws(["T01/a.md", "T01/b.md"])
        self.app.drop_ws(c)
        uj = self._ws()                                                  # a visszacsatlakozó felület még nem jelentett
        self.assertEqual(self.app.mentetlen_utak(), {"T01/a.md", "T01/b.md"})
        self.app.ws_uzenet(uj, '{"tipus": "mentetlen", "utak": ["T01/b.md"]}')    # a `hello` után a teljes, hiteles halmaz
        self.assertEqual(self.app.mentetlen_utak(), {"T01/b.md"})

    def test_ures_halmaz_nem_ker_turelmet_es_leallaskor_sincs(self):
        self.app.drop_ws(self._ws([]))
        self.assertEqual(self.app.mentetlen_utak(), set())
        c = self._ws(["T01/a.md"])
        self.app.close_ws()                                              # leállás: nincs kire várni
        self.app.drop_ws(c)
        self.assertEqual(self.app.mentetlen_utak(), set())

    def test_a_turelmi_ido_a_konfigbol_jon(self):
        self.assertEqual(self.app.mentetlen_turelem_mp, 15.0)


class KesoiIndulasiUzenetTest(unittest.TestCase):
    """T093 maradéka (C29.7b): a háttér-újrapróba üzenete csak a következő `hello`-ba került — ha nincs újracsatlakozás,
    sosem látta senki. Van kapcsolat: WS-esemény (`indulasi_uzenet`); nincs: marad a `hello`-nak."""

    def _fut(self, van_ws: bool):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("atnevezes", "atnevezes.fajl_irva").returncode, 137)
            app = server.App(a.cfg, start_delay=0)
            app.helyreallitas_ujra_mp = 0.1
            self.addCleanup(app.queue.close, 0)
            self.addCleanup(app.index.leallit)
            if van_ws:
                self.assertTrue(app.add_ws(_Kapcsolat()))
            elofizetes = app.bus.subscribe()
            zar = frame.lock_path(a.cfg)
            zar.parent.mkdir(parents=True, exist_ok=True)
            with open(zar, "a+") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                app.indulas()
                kezdeti = list(app.indulasi_uzenetek)
                fcntl.flock(fh, fcntl.LOCK_UN)
            app.helyreallitas_szal.join(20)
            esemenyek = []
            while (e := elofizetes.get(timeout=0.05)) is not None:
                esemenyek.append(e)
            return kezdeti, app.indulasi_uzenetek, [e for e in esemenyek if e["tipus"] == "indulasi_uzenet"]

    def test_van_kapcsolat_esemeny_megy(self):
        kezdeti, hello_nak, esemenyek = self._fut(van_ws=True)
        self.assertTrue(any("kimaradt" in u for u in kezdeti))
        self.assertEqual(len(esemenyek), 1, esemenyek)
        self.assertTrue(any("visszaállt" in u for u in esemenyek[0]["uzenetek"]), esemenyek)
        self.assertFalse(any("visszaállt" in u for u in hello_nak), "nem kerülhet a következő hello-ba is (dupla üzenet)")

    def test_nincs_kapcsolat_a_hello_nak_marad(self):
        kezdeti, hello_nak, esemenyek = self._fut(van_ws=False)
        self.assertEqual(esemenyek, [])
        self.assertTrue(any("visszaállt" in u for u in hello_nak), hello_nak)


if __name__ == "__main__":
    unittest.main()
