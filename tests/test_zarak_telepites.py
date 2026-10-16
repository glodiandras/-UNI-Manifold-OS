"""F3 zárak (F3-DESIGN §4): két munkatér egy telepítésen (egy modellzár, egy `worker.pid`, munkaterenkénti `core.lock`), a
vault-őr (kis-nagybetűs útváltozat és más `{run}` is ugyanarra a vaultra fut össze → 75), az idegen telepítés `core.lock`-ja
(csak olvasva; foglalt → megtagad), és a `visszaallitas` a vault-őrön is látja a futó core-t."""
import fcntl
import io
import json
import os
import unittest

from core import config, server, visszaallitas
from core.modell import beallitas, kliens
from tests.helpers import alg_core, alg_gyoker, tmpdir
from tests.multi_user import install, munkater, termek_cfg, termek_telepites


def _sor(out: io.StringIO) -> dict:
    return json.loads(out.getvalue().splitlines()[0])


class KetMunkaterEgyTelepitesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root, self.home = termek_telepites(self._t.name)
        self.va, self.ida = munkater(self._t.name, "Jegyzet A")
        self.vb, self.idb = munkater(self._t.name, "Jegyzet B")
        self.cfga = termek_cfg(self.root, self.home, self.va)
        self.cfgb = termek_cfg(self.root, self.home, self.vb)

    def test_egy_modellzar_egy_worker_pid_munkaterenkent_core_lock(self):
        i = install(self.home)
        self.assertEqual((self.cfga.elrendezes, self.cfga.workspace_id), ("termek", self.ida))
        self.assertEqual(kliens.pidfajl(self.cfga), kliens.pidfajl(self.cfgb))
        self.assertEqual(kliens.pidfajl(self.cfga), i / "run" / "worker.pid")
        ba, bb = beallitas.betolt(self.cfga, environ={}), beallitas.betolt(self.cfgb, environ={})
        self.assertEqual(ba.zar, bb.zar)
        self.assertEqual(ba.zar, i / "state" / "modell.lock")
        self.assertEqual((ba.run, bb.run), (i / "run", i / "run"), "az aktivitásjel és a worker zárja gépszintű")
        self.assertEqual(self.cfga.path("install_logs"), i / "logs", "a worker.log helye")
        self.assertEqual(self.cfga.path("run"), self.va / ".manifold" / "var" / "run")
        self.assertEqual(self.cfgb.path("run"), self.vb / ".manifold" / "var" / "run")
        self.assertNotEqual(server.vault_or_ut(self.cfga), server.vault_or_ut(self.cfgb))
        self.assertEqual(server.vault_or_ut(self.cfga).parent, i / "run" / "vaults")

    def test_ket_munkater_zarjai_fuggetlenek_es_a_tartalom(self):
        za, fa = server._zarak(self.cfga)
        self.addCleanup(server._elenged, za)
        zb, fb = server._zarak(self.cfgb)
        self.addCleanup(server._elenged, zb)
        self.assertIsNone(fa)
        self.assertIsNone(fb)
        tart = (self.va / ".manifold" / "var" / "run" / "core.lock").read_text(encoding="utf-8")
        self.assertEqual(tart, f"pid {os.getpid()} · {self.ida} · {self.va}")
        self.assertEqual(server.zar_foglalt(server.vault_or_ut(self.cfga)),
                         {"foglalt": True, "pid": os.getpid(), "vault": str(self.va)})
        server._elenged(za)
        self.assertIsNone(server.zar_foglalt(self.cfga.path("run") / "core.lock"))
        self.assertIsNone(server.zar_foglalt(server.vault_or_ut(self.cfga)))

    def test_kis_nagy_betus_utvaltozat_75(self):
        valtozat = self.va.parent / self.va.name.upper()
        if not valtozat.is_dir():
            self.skipTest("[indokolt] kis-nagybetű-érzékeny kötet: az útváltozat másik mappa")
        cfgv = termek_cfg(self.root, self.home, valtozat)
        self.assertEqual(server.vault_or_ut(cfgv), server.vault_or_ut(self.cfga), "egy vault: egy kulcs")
        za, fa = server._zarak(self.cfga)
        self.addCleanup(server._elenged, za)
        self.assertIsNone(fa)
        out = io.StringIO()
        self.assertEqual(server.start(cfgv, out=out), server.CORE_ZAR_KILEPES)
        self.assertEqual(_sor(out), {"foglalt": True, "pid": os.getpid(), "vault": str(self.va)})

    def test_mas_run_ugyanaz_a_vault_a_vault_or_fog(self):
        """A szinkronizált mappás munkatér `{var}`-ja a telepítés alatt van: a `core.lock` más, a vault-őr ugyanaz."""
        cfgm = termek_cfg(self.root, self.home, self.va, MOS_VAR=str(self.home / "masik-var"))
        self.assertNotEqual(cfgm.path("run"), self.cfga.path("run"))
        za, _ = server._zarak(self.cfga)
        self.addCleanup(server._elenged, za)
        out = io.StringIO()
        self.assertEqual(server.start(cfgm, out=out), server.CORE_ZAR_KILEPES)
        self.assertEqual(_sor(out)["pid"], os.getpid())
        self.assertIsNone(server.zar_foglalt(cfgm.path("run") / "core.lock"), "a már fogott core.lock elengedve")

    def test_a_zar_tartalma_v2_alakban_is_olvashato(self):
        self.assertEqual(server._zar_tulajdonos("pid 12 · /V/Manifold"), {"foglalt": True, "pid": 12, "vault": "/V/Manifold"})
        self.assertEqual(server._zar_tulajdonos("pid 12 · - · /V/a · b"), {"foglalt": True, "pid": 12, "vault": "/V/a · b"})
        self.assertEqual(server._zar_tulajdonos(f"pid 7 · {self.ida} · /V"), {"foglalt": True, "pid": 7, "vault": "/V"})
        self.assertEqual(server._zar_tulajdonos(""), {"foglalt": True, "pid": None, "vault": None})


class IdegenZarTest(unittest.TestCase):
    """`[hordozhato] idegen_zarak`: más telepítések `core.lock`-jai, csak olvasva (pl. a v2-checkouté)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name)
        (self.root.parent / "Manifold" / ".obsidian").mkdir()
        self.idegen = self.root.parent.parent / "v2" / "var" / "run" / "core.lock"
        self.idegen.parent.mkdir(parents=True)
        self.idegen.write_text("pid 4242 · /X/Manifold", encoding="utf-8")
        sajat = self.root / "var" / "run" / "core.lock"         # a lista véletlenül a sajátot is megnevezi: nem akadály
        settings = self.root / "var" / "settings.toml"
        settings.write_text(settings.read_text(encoding="utf-8")
                            + f"\n[hordozhato]\nidegen_zarak = [{json.dumps(str(self.idegen))}, {json.dumps(str(sajat))}]\n",
                            encoding="utf-8")
        self.cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.root.parent.parent / "home")})
        self.assertEqual(self.cfg.section("hordozhato")["idegen_zarak"], [str(self.idegen), str(sajat)])

    def test_foglalt_idegen_zar_megtagad_es_elenged(self):
        fd = os.open(self.idegen, os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        out = io.StringIO()
        self.assertEqual(server.start(self.cfg, out=out), server.CORE_ZAR_KILEPES)
        self.assertEqual(_sor(out), {"foglalt": True, "pid": 4242, "vault": "/X/Manifold"})
        self.assertIsNone(server.zar_foglalt(self.cfg.path("run") / "core.lock"))
        self.assertIsNone(server.zar_foglalt(server.vault_or_ut(self.cfg)))
        self.assertEqual(self.idegen.read_text(encoding="utf-8"), "pid 4242 · /X/Manifold", "csak olvasva")

    def test_szabad_idegen_zar_es_a_sajat_nem_akadaly(self):
        zarak, foglalt = server._zarak(self.cfg)
        self.addCleanup(server._elenged, zarak)
        self.assertIsNone(foglalt)
        self.assertEqual(len(zarak), 2)

    def test_hianyzo_idegen_zarat_nem_hozza_letre(self):
        self.idegen.unlink()
        zarak, foglalt = server._zarak(self.cfg)
        self.addCleanup(server._elenged, zarak)
        self.assertIsNone(foglalt)
        self.assertFalse(self.idegen.exists())


class VisszaallitasVaultOrTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)

    def test_a_core_a_vault_oron_is_latszik(self):
        self.assertFalse(visszaallitas._core_fut(self.cfg))
        self.assertFalse((self.cfg.path("install_run") / "vaults").exists(), "a vizsgálat semmit nem hoz létre")
        fh, _ = server._vault_or(self.cfg)
        try:
            self.assertTrue(visszaallitas._core_fut(self.cfg))
            bundle = self.root.parent / "x.bundle"
            bundle.write_bytes(b"")
            with self.assertRaises(visszaallitas.VisszaallitasHiba) as cm:
                visszaallitas.visszaallit(self.cfg, bundle)
            self.assertIn("core fut", str(cm.exception))
        finally:
            fh.close()
        self.assertFalse(visszaallitas._core_fut(self.cfg))
        fh, _ = server._core_zar(self.cfg)
        try:
            self.assertTrue(visszaallitas._core_fut(self.cfg))
        finally:
            fh.close()


if __name__ == "__main__":
    unittest.main()
