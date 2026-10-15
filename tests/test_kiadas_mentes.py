"""C34: a `tests/kezi/kiadas_mentes.py` (a belső lemezes mentés visszaállítási próbája) szakaszai álgyökéren — a valódi
`~/Manifold-backup`-hoz, vaulthoz és `var/`-hoz nem nyúlnak; a kézi kapu a valódi mentésen a NAPLO C34-bejegyzésében fut."""
import contextlib
import io
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from core import mentes, snapshot
from tests.helpers import REPO, alg_core, env as tiszta_env, ir, tmpdir

sys.path.insert(0, str(REPO / "tests" / "kezi"))
import kiadas_mentes as KM  # noqa: E402
from _kornyezet import probamappa  # noqa: E402


def _git(munkafa: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(munkafa), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env=snapshot.hermetikus_env())


class KiadasMentesTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        ki = contextlib.redirect_stdout(io.StringIO())              # a kézi kapu szakaszai kiírják az eredményüket
        ki.__enter__()
        self.addCleanup(ki.__exit__, None, None, None)
        # a `_kornyezet.cfg_elkulonitve` a folyamat környezetébe írja az API-titkot (a kézi szkriptek saját folyamatában ez a cél);
        # a tesztfolyamatban ez a későbbi API-teszteket (`test_kviz_api`, `test_ma_api`, …) 403-ra vinné — minden teszt után visszaáll
        kornyezet = mock.patch.dict(os.environ)
        kornyezet.start()
        self.addCleanup(kornyezet.stop)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "A.md", "# A\nszöveg\n")
        ir(self.v, "Mappa/B.md", "# B\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.backup = self.cfg.path("backup")
        self.d = probamappa(self.cfg, "teszt-kiadas", szkript="test_kiadas_mentes.py")
        self.riport: dict = {}
        self.alap = tiszta_env(MOS_ROOT=str(self.root), HOME=str(Path(self._t.name) / "home"))

    # --- A. vault
    def test_a_vault_visszaallitasa_rendben(self):
        mentes.ment(self.cfg)
        self.assertEqual(KM.a_vault(self.cfg, self.backup, self.d, self.riport, self.alap), [])
        self.assertEqual(self.riport["vault"]["kiirt"], 2)
        self.assertEqual(self.riport["vault"]["azonos"], 2)

    def test_a_bundle_ota_modositott_fajl_megmagyarazott_elteres(self):
        mentes.ment(self.cfg)
        ir(self.v, "A.md", "# A\nmódosítva a mentés után\n")                 # nem rögzített változás
        self.assertEqual(KM.a_vault(self.cfg, self.backup, self.d, self.riport, self.alap), [])
        self.assertEqual(self.riport["vault"]["elter"], 1)
        self.assertEqual(self.riport["vault"]["megmagyarazatlan"], 0)

    def test_nincs_vault_bundle_hiba(self):
        self.assertIn("nincs vault-*.bundle", KM.a_vault(self.cfg, self.backup, self.d, self.riport, self.alap)[0])

    # --- B. kódtár
    def _kodtar(self, kihagy: str | None = None) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, env=snapshot.hermetikus_env())
        for k in KM.KULCSFAJLOK:
            if k == kihagy:
                continue
            f = self.root / k
            f.parent.mkdir(parents=True, exist_ok=True)
            if not f.exists():
                f.write_text("x\n", encoding="utf-8")
        _git(self.root, "add", "--force", *[k for k in KM.KULCSFAJLOK if k != kihagy])
        _git(self.root, "commit", "-qm", "kodtar")
        self.assertIsNotNone(mentes._kodtar_bundle(self.cfg, self.backup, 10))

    def test_a_kodtar_bundle_klonozhato_es_a_kulcsfajlok_megvannak(self):
        self._kodtar()
        self.assertEqual(KM.a_kodtar(self.cfg, self.backup, self.d, self.riport), [])
        self.assertEqual(self.riport["kodtar"]["relacio"], "őse a valódi HEAD-nek (vagy azonos)")

    def test_hianyzo_kulcsfajl_a_kodtarban_hiba(self):
        self._kodtar(kihagy="core/doctor.py")
        hibak = KM.a_kodtar(self.cfg, self.backup, self.d, self.riport)
        self.assertEqual(len(hibak), 1)
        self.assertIn("core/doctor.py", hibak[0])

    def test_nincs_kodtar_bundle_hiba(self):
        self.backup.mkdir(parents=True, exist_ok=True)
        self.assertIn("nincs mos-kodtar-*.bundle", KM.a_kodtar(self.cfg, self.backup, self.d, self.riport)[0])

    # --- C. állapot
    def _allapot(self) -> Path:
        con = sqlite3.connect(self.cfg.path("router_db"))
        con.execute("CREATE TABLE t (x)")
        con.execute("PRAGMA user_version = 3")
        con.commit()
        con.close()
        (self.cfg.path("state") / "felulet.json").write_text('{"tema": "sotet"}', encoding="utf-8")
        return mentes.allapot_masolat(self.cfg)

    def test_az_allapotmasolat_rendben(self):
        self._allapot()
        self.assertEqual(KM.az_allapot(self.cfg, self.backup, self.riport), [])
        self.assertEqual(sorted(self.riport["allapot"]["ellenorizve"]), ["router.sqlite v3", "state/felulet.json"])

    def test_serult_sqlite_es_json_es_hianyzo_masolat_hiba(self):
        mappa = self._allapot()
        (mappa / "router.sqlite").write_bytes(b"nem sqlite" * 100)
        (mappa / "state" / "felulet.json").write_text("{nem json", encoding="utf-8")
        hibak = KM.az_allapot(self.cfg, self.backup, self.riport)
        self.assertEqual(len(hibak), 2, hibak)
        self.assertTrue(any("router.sqlite" in h for h in hibak))
        self.assertTrue(any("nem JSON" in h for h in hibak))
        (mappa / "state" / "felulet.json").unlink()
        self.assertTrue(any("nincs másolata" in h and "felulet.json" in h for h in KM.az_allapot(self.cfg, self.backup, self.riport)))

    def test_user_version_eltereset_jelzi(self):
        self._allapot()
        con = sqlite3.connect(self.cfg.path("router_db"))
        con.execute("PRAGMA user_version = 4")                                # az élő forrás azóta migrált
        con.commit()
        con.close()
        hibak = KM.az_allapot(self.cfg, self.backup, self.riport)
        self.assertTrue(any("user_version 3 (másolat) ≠ 4 (forrás)" in h for h in hibak), hibak)

    # --- D. ritmus
    def test_a_ritmus_friss_bundle_rendben_regi_es_hianyos_hiba(self):
        mentes.ment(self.cfg)
        self.assertEqual(KM.a_ritmus(self.cfg, self.backup, self.riport), [])
        ir(self.v, "A.md", "# A\nújabb\n")
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        self.assertEqual(KM.a_ritmus(self.cfg, self.backup, self.riport), [], "friss (fél órán belüli) bundle: a lemaradás normális")
        import os
        regi = mentes.legujabb(self.repo, self.backup)
        os.utime(regi, (1_700_000_000, 1_700_000_000))
        self.assertTrue(KM.a_ritmus(self.cfg, self.backup, self.riport))


if __name__ == "__main__":
    unittest.main()
