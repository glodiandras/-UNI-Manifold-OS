"""H2 (audit): mentés a belső lemezre kilépéskor, ha a HEAD változott az utolsó bundle óta; a doctor jelzi, ha a
legutóbbi bundle régebbi a HEAD-nél. Álvaulton, az ál-`{home}/Manifold-backup` alá (a valódi mentéshez nem nyúl).
Csak git bundle: a média nem kerül mentésbe (1. / 14. döntés)."""
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from core import config, doctor, frame, mentes, server, snapshot
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir
from tests.test_core_api import _Szerver


class MentesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "A.md", "# A\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.backup = self.cfg.path("backup")

    def bundlek(self):
        return sorted(self.backup.glob("vault-*.bundle")) if self.backup.is_dir() else []

    @csak_darwin("APFS-klón (`cp -c`)")
    def test_a_probaklon_tarolojat_a_mentes_kihagyja(self):
        """A2-iras-7 (2. audit): a klónos próba core-ja `MOS_VAULT_GIT`-tel a klón tárolójára mutat; a kilépési mentése a
        valódi `{backup}` rotációját nem érheti (a `vault-*.bundle` rotáció származástól függetlenül törölne)."""
        for i in range(3):
            (self.backup).mkdir(parents=True, exist_ok=True)
            (self.backup / f"vault-2026010{i}-000000.bundle").write_bytes(b"valodi")
        klon = Path(self._t.name) / "klon"
        vault, git = frame.trial_clone(self.cfg, klon)
        kcfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"), "MOS_VAULT": str(vault),
                            "MOS_VAULT_GIT": str(git), "MOS_BACKUP": str(self.backup)})
        self.assertEqual(mentes.ment(kcfg), [])
        self.assertEqual(sorted(p.name for p in self.backup.glob("vault-*.bundle")),
                         [f"vault-2026010{i}-000000.bundle" for i in range(3)])
        self.assertEqual(mentes.kilepeskor(kcfg), [])
        # a valódi tároló mentése változatlanul megy
        self.assertEqual(len(mentes.ment(self.cfg)), 1)

    def test_csak_ha_a_head_valtozott(self):
        self.assertFalse(mentes.friss(self.repo, self.backup))
        self.assertEqual(len(mentes.ment(self.cfg, csak_ha_valtozott=True)), 1)
        self.assertEqual(len(self.bundlek()), 1)
        self.assertTrue(mentes.friss(self.repo, self.backup))
        self.assertEqual(mentes.ment(self.cfg, csak_ha_valtozott=True), [])
        self.assertEqual(len(self.bundlek()), 1)
        ir(self.v, "A.md", "# A\nújabb\n")
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        self.assertFalse(mentes.friss(self.repo, self.backup))
        import time
        time.sleep(1.1)                     # a bundle neve másodpercre pontos
        self.assertEqual(len(mentes.ment(self.cfg, csak_ha_valtozott=True)), 1)
        self.assertEqual(len(self.bundlek()), 2)
        self.assertTrue(mentes.friss(self.repo, self.backup))

    def test_media_nem_kerul_mentesbe(self):
        (self.v / "kep.jpg").write_bytes(b"\xff\xd8" * 100)
        mentes.ment(self.cfg, csak_ha_valtozott=False)
        self.assertEqual([p.suffix for p in self.backup.iterdir() if p.name != mentes.JEL_NEV], [".bundle"])      # az üres mappa tulajdonosjelet kap
        # C31 (2. audit T065, A2-visszaallitas1-8): a bundle kiklónozva — a `.jpg` hiányzik, a `.md` bájtra egyezik
        klon = Path(self._t.name) / "klon"
        p = subprocess.run(["git", "clone", "-q", str(next(self.backup.glob("vault-*.bundle"))), str(klon)],
                           capture_output=True, text=True, env=snapshot.hermetikus_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((klon / "kep.jpg").exists())
        self.assertEqual((klon / "A.md").read_bytes(), (self.v / "A.md").read_bytes())

    def test_doctor_jelzi_a_regi_mentest(self):
        home = Path(self._t.name) / "home"
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(home)})
        sor = lambda: {r.nev: r for r in doctor.ellenoriz(cfg, {"HF_HUB_OFFLINE": "1"}, home)}["mentés"]  # noqa: E731
        self.assertEqual(sor().allapot, doctor.FIGYELEM)                     # nincs bundle
        mentes.ment(self.cfg, csak_ha_valtozott=False)
        self.assertEqual(sor().allapot, doctor.OK)
        ir(self.v, "A.md", "# A\nmás\n")
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        self.assertEqual(sor().allapot, doctor.FIGYELEM)
        self.assertIn("régebbi", sor().uzenet)


class KilepesMentesTest(_Szerver):
    """A core rendezett leállása (a stdin lezárul) bundle-t ír; a SIGTERM-es kényszerleállás nem (a tesztben a
    szál-szerver csak a stdin útját járja)."""

    def elokeszit(self):
        ir(self.v, "A.md", "# A\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})

    def test_kilepeskor_bundle(self):
        self._leall()
        self.assertFalse(self.szal.is_alive())
        b = sorted(self.cfg.path("backup").glob("vault-*.bundle"))
        self.assertEqual(len(b), 1)
        self.assertTrue(mentes.friss(self.repo, self.cfg.path("backup")))


def git_init(gyoker: Path) -> None:
    """Egy git-tár a (kódtárnak szánt) álgyökérben, egy üres committal."""
    for a in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "alap"]):
        subprocess.run(["git", "-C", str(gyoker), *a], check=True, capture_output=True)


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "A.md", "# A\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.backup = self.cfg.path("backup")

    def nevek(self, minta):
        return sorted(p.name for p in self.backup.glob(minta)) if self.backup.is_dir() else []


class KodtarEsAllapotTest(Alap):
    """33. döntés (T001): a belső lemezes mentés a vault szövege mellett a 2.0 kódtárát (git bundle) és a kis állapotfájlokat
    (SQLite `VACUUM INTO`, `state/*.json`) is viszi; a média és az újraépíthető adat nem kerül bele."""

    def test_kodtar_bundle_es_rotacio(self):
        git_init(self.root)
        mentes._jel_ir(self.cfg, self.backup)                               # a mappa a miénk (tulajdonosjel): a rotáció a régi módon megy
        for i in range(3):                                                  # régi bundle-ök: a rotáció a `keep` fölöttieket törli
            (self.backup / f"mos-kodtar-2026010{i}-000000.bundle").write_bytes(b"regi")
        cfg = self._cfg(megtartott_bundle=2)
        ki = mentes.ment(cfg)
        self.assertEqual(len(self.nevek("mos-kodtar-*.bundle")), 2)         # 3 régi + 1 új → a legrégebbi 2 törölve
        self.assertIn("mos-kodtar-20260102-000000.bundle", self.nevek("mos-kodtar-*.bundle"))
        uj = [p for p in ki if p.name.startswith("mos-kodtar-")]
        self.assertEqual(len(uj), 1)
        p = subprocess.run(["git", "bundle", "verify", str(uj[0])], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(mentes.kodtar_friss(cfg, self.backup))
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "uj"], check=True, capture_output=True)
        self.assertFalse(mentes.kodtar_friss(cfg, self.backup))             # egy új commit után a bundle elavult

    def _cfg(self, **mentes_kulcsok):
        toml = self.root / "config" / "os.toml"
        szoveg = toml.read_text(encoding="utf-8")
        for k, v in mentes_kulcsok.items():
            import re
            szoveg = re.sub(rf"^{k} = .*$", f"{k} = {v}", szoveg, count=1, flags=re.M)
        toml.write_text(szoveg, encoding="utf-8")
        return config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home")})

    def test_nincs_kodtar_ha_nincs_git(self):
        self.assertIsNone(mentes.kodtar_munkafa(self.cfg))
        ki = mentes.ment(self.cfg)
        self.assertEqual([p.name.split("-")[0] for p in ki], ["vault"])

    def _sqlite(self, ut: Path, sor: str, wal: bool = False):
        ut.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(ut)
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE IF NOT EXISTS t (x TEXT)")
        con.execute("INSERT INTO t VALUES (?)", (sor,))
        con.commit()
        return con                                                          # nyitva marad: élő kapcsolat mellett is menteni kell

    def test_allapot_masolat_sqlite_es_json(self):
        elo = [self._sqlite(self.cfg.path("router_db"), "router", wal=True),
               self._sqlite(self.cfg.path("feladatok_db"), "feladat"),
               self._sqlite(self.cfg.path("szemelyes") / "pos.sqlite", "pos", wal=True)]
        st = self.cfg.path("state")
        st.mkdir(parents=True, exist_ok=True)
        (st / "felulet.json").write_text('{"tema": "sotet"}', encoding="utf-8")
        (st / "kapcsolok.json").write_text('{"tracker": true}', encoding="utf-8")
        (st / "modell.lock").write_text("pid 1", encoding="utf-8")         # nem json: nem kerül bele
        (self.v / "kep.jpg").write_bytes(b"\xff\xd8" * 100)                   # média: soha
        mappa = mentes.allapot_masolat(self.cfg)
        self.assertTrue(mentes.allapot_friss(self.cfg, self.backup))       # (a WAL-os kapcsolatok zárása checkpointol: az már újabb)
        for c in elo:
            c.close()
        self.assertTrue(mappa.is_dir() and mappa.name.startswith("mos-allapot-"))
        for rel, vart in (("router.sqlite", "router"), ("feladatok.sqlite", "feladat"), ("szemelyes/pos.sqlite", "pos")):
            con = sqlite3.connect(f"file:{mappa / rel}?mode=ro", uri=True)
            self.assertEqual(con.execute("SELECT x FROM t").fetchall(), [(vart,)], rel)
            con.close()
        self.assertEqual(json.loads((mappa / "state/felulet.json").read_text(encoding="utf-8")), {"tema": "sotet"})
        self.assertFalse((mappa / "state/modell.lock").exists())
        self.assertEqual(sorted(p.name for p in mappa.rglob("*") if p.is_file() and p.name.endswith(("-wal", "-shm", ".jpg"))), [])

    def test_allapot_masolat_tanulas_sqlite(self):
        """C23a (33. döntés): a kártyák FSRS-története (`tanulas.sqlite`) a belső mentés `VACUUM INTO`-listájában."""
        from core import tanulas_db
        with tanulas_db.iro(self.cfg) as c:
            c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0001', '2026-10-04T10:00:00+00:00')")
        self.assertIn(("tanulas.sqlite", self.cfg.path("tanulas_db")), mentes.allapot_forrasok(self.cfg))
        mappa = mentes.allapot_masolat(self.cfg)
        con = sqlite3.connect(f"file:{mappa / 'tanulas.sqlite'}?mode=ro", uri=True)
        try:
            self.assertEqual(con.execute("SELECT azon FROM kartya").fetchall(), [("c-0001",)])
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(tanulas_db.MIGRACIOK))
        finally:
            con.close()

    def test_allapot_csak_ha_valtozott_es_rotacio(self):
        self._sqlite(self.cfg.path("router_db"), "egy").close()
        cfg = self._cfg(allapot_megtartott=2)
        mentes._jel_ir(self.cfg, self.backup)                               # ugyanezért: a mappa a miénk
        for i in range(3):
            (self.backup / f"mos-allapot-2026010{i}-000000").mkdir()
        elso = mentes.allapot_masolat(cfg)
        self.assertIsNotNone(elso)
        self.assertEqual(len(self.nevek("mos-allapot-*")), 2)               # a rotáció a keep fölöttieket törli (a napi ablakon kívül)
        self.assertIsNone(mentes.allapot_masolat(cfg, csak_ha_valtozott=True))   # nem változott: kimarad
        time.sleep(0.05)
        self._sqlite(self.cfg.path("router_db"), "ketto").close()
        self.assertFalse(mentes.allapot_friss(cfg, self.backup))
        self.assertIsNotNone(mentes.allapot_masolat(cfg, csak_ha_valtozott=True))

    def test_nincs_mit_masolni(self):
        self.assertIsNone(mentes.allapot_masolat(self.cfg))
        self.assertIsNone(mentes.allapot_friss(self.cfg, self.backup))

    def test_egy_hibas_sqlite_nem_viszi_el_a_tobbit(self):
        self._sqlite(self.cfg.path("feladatok_db"), "feladat").close()
        self.cfg.path("router_db").write_bytes(b"ez nem sqlite" * 50)
        with self.assertRaises(OSError) as cm:
            mentes.allapot_masolat(self.cfg)
        self.assertIn("router.sqlite", str(cm.exception))
        mappa = mentes.utolso_allapot(self.backup)
        self.assertTrue((mappa / "feladatok.sqlite").is_file())

    @csak_darwin("APFS-klón (`cp -c`)")
    def test_a_probaklon_a_kodtarat_es_az_allapotot_sem_menti(self):
        git_init(self.root)
        self._sqlite(self.cfg.path("router_db"), "x").close()
        klon = Path(self._t.name) / "klon"
        vault, git = frame.trial_clone(self.cfg, klon)
        kcfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"), "MOS_VAULT": str(vault),
                            "MOS_VAULT_GIT": str(git), "MOS_BACKUP": str(self.backup)})
        self.assertEqual(mentes.ment(kcfg), [])
        self.assertEqual(self.nevek("*"), [])


class HibaKezelesTest(Alap):
    """T023: egy tároló mentési hibája nem viszi el a többit, és nem marad néma (`mentes-hiba.json`)."""

    def setUp(self):
        super().setUp()
        (self.cfg.path("modulok") / "ytdlp").mkdir(parents=True)
        self.yt = snapshot.repos(self.cfg)["ytdlp"]
        self.yt.init()
        ir(self.cfg.path("modulok") / "ytdlp", "x.py", "print(1)\n")
        self.yt.commit("alap", {"Mos-Forras": "kezi"})
        self.assertEqual(sorted(frame.live_repos(self.cfg)), ["vault", "ytdlp"])

    def _elso_bukik(self):
        eredeti = snapshot.Repo.bundle

        def bundle(repo, dest, keep=10):
            if repo.name == "vault":
                raise snapshot.SnapshotError("[vault] a belső lemez tele van")
            return eredeti(repo, dest, keep)

        snapshot.Repo.bundle = bundle
        self.addCleanup(setattr, snapshot.Repo, "bundle", eredeti)

    def test_az_elso_tarolo_hibaja_nem_viszi_el_a_masodikat(self):
        self._elso_bukik()
        hibak = {}
        ki = mentes.ment(self.cfg, hibak=hibak)
        self.assertEqual(list(hibak), ["vault"])
        self.assertEqual([p.name.split("-")[0] for p in ki], ["ytdlp"])
        with self.assertRaises(snapshot.SnapshotError):                     # hibák-gyűjtő nélkül az első hiba kivétel (a kézi `backup`)
            mentes.ment(self.cfg)

    def test_kilepeskor_hibaja_a_fajlba_kerul_es_a_siker_torli(self):
        self._elso_bukik()
        ki = mentes.kilepeskor(self.cfg)
        self.assertEqual([p.name.split("-")[0] for p in ki], ["ytdlp"])
        d = mentes.hiba_olvas(self.cfg)
        self.assertIn("vault", d["hibak"])
        self.assertIn("tele van", mentes.hiba_szoveg(d))
        snapshot.Repo.bundle = snapshot.Repo.__dict__["bundle"]             # (a cleanup áll vissza; itt marad a hibás)
        # a hiba megszűnése: a következő sikeres mentés törli a nyomot
        self.addCleanup(lambda: None)
        mentes.hiba_ir(self.cfg, {})
        self.assertIsNone(mentes.hiba_olvas(self.cfg))

    def test_zart_stderr_mellett_is_vegigmegy(self):
        """A héj összeomlása után a core stderr-je törött cső: a naplózás `BrokenPipeError`-ja nem szakíthatja meg a
        második tároló mentését."""
        class Toro:
            def write(self, *_a):
                raise BrokenPipeError(32, "Broken pipe")

            def flush(self):
                raise BrokenPipeError(32, "Broken pipe")

        eredeti, sys.stderr = sys.stderr, Toro()
        try:
            ki = mentes.kilepeskor(self.cfg)
        finally:
            sys.stderr = eredeti
        self.assertEqual(sorted(p.name.split("-")[0] for p in ki), ["vault", "ytdlp"])
        self.assertIsNone(mentes.hiba_olvas(self.cfg))

    def test_a_kovetkezo_indulas_uzenetet_ad(self):
        mentes.hiba_ir(self.cfg, {"vault": "a belső lemez tele van"})
        app = server.App(self.cfg, start_delay=0)
        self.addCleanup(app.queue.close, 0)
        self.addCleanup(app.index.leallit)
        app.indulas()
        uz = [u for u in app.indulasi_uzenetek if "belső lemezes mentés nem sikerült" in u]
        self.assertEqual(len(uz), 1, app.indulasi_uzenetek)
        self.assertIn("tele van", uz[0])

    def test_a_doctor_kulon_sorban_jelzi_a_hibas_mentest(self):
        home = Path(self._t.name) / "home"
        sorok = lambda: {r.nev: r for r in doctor.ellenoriz(self.cfg, {"HF_HUB_OFFLINE": "1"}, home)}  # noqa: E731
        self.assertNotIn("mentés hiba", sorok())
        mentes.hiba_ir(self.cfg, {"vault": "tele van"})
        r = sorok()["mentés hiba"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("HIBÁS", r.uzenet)
        self.assertIn("tele van", r.uzenet)

    def test_a_vezerlo_kulon_mezoben_adja_a_hibat(self):
        from core import vezerlo
        self.assertIsNone(vezerlo._mentes(self.cfg)["hiba"])
        mentes.hiba_ir(self.cfg, {"vault": "tele van"})
        h = vezerlo._mentes(self.cfg)["hiba"]
        self.assertEqual(h["hibak"], {"vault": "tele van"})


class KilepesiRogzitesTest(Alap):
    """T022: a 2.0-n kívül (Obsidian, Finder) szerkesztett, még nem rögzített szöveg a bundle-be kerül, a `friss` nem hazudik."""

    def test_friss_a_nem_rogzitett_valtozasra_hamis(self):
        mentes.ment(self.cfg)
        self.assertTrue(mentes.friss(self.repo, self.backup))
        (self.v / "A.md").write_text("# A\nObsidianban szerkesztve\n", encoding="utf-8")        # nincs commit
        self.assertFalse(mentes.friss(self.repo, self.backup))                                        # eddig: igaz
        self.assertTrue(mentes.friss(self.repo, self.backup, dirty=False))                            # a HEAD benne van
        self.assertEqual(mentes.nem_rogzitett(self.repo), ["A.md"])

    def test_kilepeskor_rogziti_es_a_bundle_viszi(self):
        mentes.ment(self.cfg)
        (self.v / "A.md").write_text("# A\nObsidianban szerkesztve\n", encoding="utf-8")
        (self.v / "Uj.md").write_text("# Új\n", encoding="utf-8")
        ki = mentes.kilepeskor(self.cfg)
        self.assertEqual([p.name.split("-")[0] for p in ki], ["vault"])
        self.assertEqual(self.repo.dirty_paths(), [])
        c = self.repo.log(1)[0]
        self.assertEqual(c.trailers["Mos-Forras"], "kezi")
        self.assertEqual(sorted(self.repo.changed_files(c.sha)), ["A.md", "Uj.md"])
        self.assertTrue(mentes.friss(self.repo, self.backup))
        # a bundle valóban tartalmazza a szerkesztett szöveget
        klon = Path(self._t.name) / "visszaallitott"
        subprocess.run(["git", "clone", "-q", str(ki[0]), str(klon)], check=True, capture_output=True)
        self.assertIn("Obsidianban szerkesztve", (klon / "A.md").read_text(encoding="utf-8"))

    def test_kilepeskor_idempotens(self):
        mentes.kilepeskor(self.cfg)
        n = len(self.repo.log(50))
        mentes.kilepeskor(self.cfg)
        self.assertEqual(len(self.repo.log(50)), n)                                                    # nincs üres commit
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)

    def test_a_doctor_figyelmeztet_a_nem_rogzitett_valtozasra(self):
        home = Path(self._t.name) / "home"
        sor = lambda: {r.nev: r for r in doctor.ellenoriz(self.cfg, {"HF_HUB_OFFLINE": "1"}, home)}["mentés"]  # noqa: E731
        mentes.ment(self.cfg)
        self.assertEqual(sor().allapot, doctor.OK)
        (self.v / "A.md").write_text("# A\nkívülről\n", encoding="utf-8")
        r = sor()
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("nem rögzített", r.uzenet)
        self.assertIn("A.md", r.uzenet)


class KenyszerIdokeretTest(Alap):
    """K44: a második ⌘Q ágán a bundle-próba legfeljebb az időkeretig fut; a félkész bundle nem marad `.bundle`-ként."""

    def test_lassu_bundle_az_idokeretnel_visszater_es_nem_hagy_csonka_bundle_t(self):
        eredeti = snapshot.Repo.git
        kesz = []

        def lassu(repo, *args, **k):
            if args[:2] == ("bundle", "create"):
                time.sleep(3)
                kesz.append(1)
            return eredeti(repo, *args, **k)

        snapshot.Repo.git = lassu
        self.addCleanup(setattr, snapshot.Repo, "git", eredeti)
        t0 = time.monotonic()
        self.assertEqual(mentes.kilepeskor(self.cfg, idokeret=0.4), [])
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(self.nevek("vault-*.bundle"), [], "időkeret után nem lehet kész bundle")
        import threading
        for szal in threading.enumerate():                                  # a háttérszál ne éljen túl a tmp-mappa törlésén
            if szal.name == "kilepesi-mentes":
                szal.join(20)
        self.assertTrue(kesz)

    def test_a_megmaradt_bundle_tmp_a_kovetkezo_mentesnel_eltunik(self):
        self.backup.mkdir(parents=True, exist_ok=True)
        (self.backup / "vault-20260101-000000.bundle.tmp").write_bytes(b"felkesz")
        (self.backup / "mos-allapot-20260101-000000.tmp").mkdir()
        self.v.joinpath("B.md").write_text("# B\n", encoding="utf-8")
        self.repo.commit("b", {"Mos-Forras": "kezi"})
        mentes.ment(self.cfg)
        self.assertEqual(self.nevek("*.tmp"), [])
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)


class UtemezoTest(Alap):
    """34. döntés: bundle gépi kör végén és tétlenségben N percenként, ha a HEAD változott — a `tick()` hamis órával."""

    class Ora:
        def __init__(self):
            self.t = 1000.0

        def __call__(self):
            return self.t

    class Aktivitas:
        def __init__(self):
            self.mod = "tetlen"

        def allapot(self):
            return self.mod

    def setUp(self):
        super().setUp()
        self.ora, self.akt = self.Ora(), self.Aktivitas()
        self.u = mentes.Utemezo(self.cfg, aktivitas=self.akt, ido_perc=30, ora=self.ora, log=lambda s: None)

    def uj_commit(self, n: str):
        (self.v / f"{n}.md").write_text(f"# {n}\n", encoding="utf-8")
        self.repo.commit(n, {"Mos-Forras": "kezi"})

    def test_30_perc_elott_nem_fut_utana_egy_bundle_ha_a_head_valtozott(self):
        self.assertFalse(self.u.tick())
        self.ora.t += 29 * 60
        self.assertFalse(self.u.tick())
        self.ora.t += 2 * 60                                                # 31 perc
        self.assertTrue(self.u.tick())
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)
        self.ora.t += 31 * 60                                               # újabb 30 perc, de a HEAD nem változott
        self.assertTrue(self.u.tick())
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)              # nincs új bundle
        self.uj_commit("B")
        self.ora.t += 31 * 60
        time.sleep(1.1)                                                     # a bundle neve másodpercre pontos
        self.assertTrue(self.u.tick())
        self.assertEqual(len(self.nevek("vault-*.bundle")), 2)

    def test_aktiv_hasznalat_kozben_nem_fut_a_jel_megmarad(self):
        self.akt.mod = "aktiv"
        self.u.kor_vege()
        self.assertFalse(self.u.tick())
        self.assertEqual(self.nevek("vault-*.bundle"), [])
        self.akt.mod = "tetlen"
        self.assertTrue(self.u.tick())                                      # tétlenségben a kör vége miatt azonnal
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)
        self.assertFalse(self.u.tick())                                     # a jel elfogyott, az idő még nem jött el

    def test_foglalt_kor_zar_eseten_30_mp_mulva_ujra(self):
        import fcntl
        self.u.kor_vege()
        zar = frame.lock_path(self.cfg)
        zar.parent.mkdir(parents=True, exist_ok=True)
        with open(zar, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            self.assertFalse(self.u.tick())
            fcntl.flock(fh, fcntl.LOCK_UN)
        self.assertEqual(self.nevek("vault-*.bundle"), [])
        self.assertTrue(self.u.tick())                                      # a jel megmaradt: a zár szabadulásakor fut
        self.assertEqual(len(self.nevek("vault-*.bundle")), 1)

    def test_a_vault_iro_feladat_vege_jelzi_az_utemezonek(self):
        a = server.App(self.cfg, start_delay=0)
        self.addCleanup(a.queue.close, 0)
        self.addCleanup(a.index.leallit)
        a._feladat_publish({"tipus": "feladat", "feladat": {"vault_ir": False, "allapot": "kesz"}})
        self.assertFalse(a.mentes_utemezo._kor_jel.is_set())                # nem vault-író: nem kör
        a._feladat_publish({"tipus": "feladat", "feladat": {"vault_ir": True, "allapot": "fut"}})
        self.assertFalse(a.mentes_utemezo._kor_jel.is_set())                # még fut
        a._feladat_publish({"tipus": "feladat", "feladat": {"vault_ir": True, "allapot": "kesz"}})
        self.assertTrue(a.mentes_utemezo._kor_jel.is_set())                 # vége: mentésre jelzett

    def test_allapotmasolat_legfeljebb_allapot_ido_percenkent(self):
        """B-javító 4: a gépi kör végén és a 30 perces lépésben csak bundle; az állapotmásolat legfeljebb
        `allapot_ido_perc`-enként (itt 60) — eddig minden kör végén másolt, és a 10-es közös rotáció egy nap alatt kifutott."""
        st = self.cfg.path("state")
        st.mkdir(parents=True, exist_ok=True)
        (st / "felulet.json").write_text("{}", encoding="utf-8")
        self.u.kor_vege()
        self.assertTrue(self.u.tick())
        self.assertEqual(len(self.nevek("mos-allapot-*")), 1)               # az első lépés másol
        for perc in (1, 31):
            time.sleep(1.1)                                                 # a név másodpercre pontos
            (st / "felulet.json").write_text(f'{{"perc": {perc}}}', encoding="utf-8")
            self.uj_commit(f"K{perc}")
            self.ora.t += perc * 60
            self.u.kor_vege()
            self.assertTrue(self.u.tick())
            self.assertEqual(len(self.nevek("mos-allapot-*")), 1, perc)     # csak bundle
        time.sleep(1.1)
        self.ora.t += 30 * 60                                               # 62 perc az első másolat óta
        self.u.kor_vege()
        self.assertTrue(self.u.tick())
        self.assertEqual(len(self.nevek("mos-allapot-*")), 2)


class AllapotMasolatTest(Alap):
    """B-javító 4–5: az állapotmásolat tartalma (JSONL, füzet-, videóállapot), a hard linkes inkrementum, a saját megtartás."""

    def setUp(self):
        super().setUp()
        self.st = self.cfg.path("state")
        ir(self.st, "felulet.json", "{}")
        ir(self.st, "binaris-naplo.jsonl", '{"muvelet": "mozgat"}\n')
        ir(self.st, "modell.lock", "pid 1")
        fz = self.cfg.path("fuzet")
        ir(fz, "allapot.json", '{"kotesek": 522}')
        ir(fz, "eros/abc.json", "{}")
        ir(fz, "naplo.jsonl", "{}\n")
        ir(fz, "tmp/felkesz.json", "{}")
        (fz / "elonezet").mkdir(parents=True)
        (fz / "elonezet" / "abc_720.jpg").write_bytes(b"\xff\xd8" * 10)
        ir(self.cfg.path("video_jobs"), "k1/state.json", '{"allapot": "kesz"}')
        ir(self.st, "video-bejaras/kulcs.json", "[]")
        ir(self.st, "Manifold-media/itelet/n_kotes_minta.json", "{}")
        ir(self.st, "Manifold-work/nagy/meres.json", "{}")                 # nincs a listán: nem kerül bele

    def test_a_masolat_viszi_a_jsonl_t_es_az_allapotmappakat(self):
        nevek = {n for n, _ in mentes.allapot_forrasok(self.cfg)}
        for vart in ("state/felulet.json", "state/binaris-naplo.jsonl", "state/Manifold-fuzet/allapot.json",
                     "state/Manifold-fuzet/eros/abc.json", "state/Manifold-fuzet/naplo.jsonl",
                     "state/Manifold-media/jobs/k1/state.json", "state/video-bejaras/kulcs.json",
                     "state/Manifold-media/itelet/n_kotes_minta.json"):
            self.assertIn(vart, nevek)
        for nincs in ("state/modell.lock", "state/Manifold-fuzet/tmp/felkesz.json",
                      "state/Manifold-fuzet/elonezet/abc_720.jpg", "state/Manifold-work/nagy/meres.json"):
            self.assertNotIn(nincs, nevek)
        mappa = mentes.allapot_masolat(self.cfg)
        self.assertEqual((mappa / "state/binaris-naplo.jsonl").read_text(encoding="utf-8"), '{"muvelet": "mozgat"}\n')
        self.assertEqual((mappa / "state/Manifold-fuzet/allapot.json").read_text(encoding="utf-8"), '{"kotesek": 522}')

    def test_valtozatlan_fajl_hard_link_a_valtozott_uj_masolat(self):
        elso = mentes.allapot_masolat(self.cfg)
        time.sleep(1.1)
        (self.cfg.path("fuzet") / "allapot.json").write_text('{"kotesek": 523}', encoding="utf-8")
        masodik = mentes.allapot_masolat(self.cfg)
        self.assertNotEqual(elso, masodik)
        a, b = elso / "state/Manifold-fuzet/eros/abc.json", masodik / "state/Manifold-fuzet/eros/abc.json"
        self.assertEqual(a.stat().st_ino, b.stat().st_ino)                  # változatlan: link, nem új hely
        a, b = elso / "state/Manifold-fuzet/allapot.json", masodik / "state/Manifold-fuzet/allapot.json"
        self.assertNotEqual(a.stat().st_ino, b.stat().st_ino)
        self.assertEqual(a.read_text(encoding="utf-8"), '{"kotesek": 522}')   # a régi másolat érintetlen
        self.assertEqual(b.read_text(encoding="utf-8"), '{"kotesek": 523}')

    def test_megtartas_legujabbak_es_napi_egy(self):
        self.backup.mkdir(parents=True, exist_ok=True)
        ma = datetime.date(2026, 10, 14)
        nevek = ["20261001-100000", "20261005-080000", "20261005-200000", "20261013-090000", "20261013-210000",
                 "20261014-100000", "20261014-110000", "20261014-120000", "20261014-130000"]
        for n in nevek:
            (self.backup / f"mos-allapot-{n}").mkdir()
        torolt = mentes.allapot_ritkit(self.backup, megtartott=3, napi=3, ma=ma)
        marad = [n.removeprefix("mos-allapot-") for n in self.nevek("mos-allapot-*")]
        # a legújabb 3 + az utolsó 3 nap (10-12 … 10-14) mindegyikéből a nap utolsója (10-13 21:00; 10-14 13:00 már benne)
        self.assertEqual(marad, ["20261013-210000", "20261014-110000", "20261014-120000", "20261014-130000"])
        self.assertEqual(len(torolt), len(nevek) - len(marad))

    def test_hibanal_nem_marad_felkesz_tmp(self):
        eredeti = mentes.os.replace

        def bukik(a, b):
            if str(a).endswith(".tmp"):
                raise OSError(28, "No space left on device")
            return eredeti(a, b)
        with mock.patch.object(mentes.os, "replace", bukik):
            with self.assertRaises(OSError):
                mentes.allapot_masolat(self.cfg)
        self.assertEqual(self.nevek("mos-allapot-*"), [])

    def test_allapot_rendben_az_idoablakon_belul(self):
        mappa = mentes.allapot_masolat(self.cfg)
        time.sleep(0.05)
        (self.st / "felulet.json").write_text('{"uj": 1}', encoding="utf-8")
        self.assertFalse(mentes.allapot_friss(self.cfg, self.backup))
        self.assertTrue(mentes.allapot_rendben(self.cfg, self.backup))              # 2 × 60 percen belül: rendben
        regi = mappa.stat().st_mtime - 3 * 3600
        os.utime(mappa, (regi, regi))
        self.assertFalse(mentes.allapot_rendben(self.cfg, self.backup))


class KilepesTurelemEsGitIdokorlatTest(Alap):
    """B-javító 6–7: a kilépési mentés kivárja a rövid zár-tartást; a git-hívás időkorlátja magyar `MentesHiba`."""

    def test_a_kilepesi_mentes_kivarja_a_rovid_zarat(self):
        zart, engedd = threading.Event(), threading.Event()

        def tart():
            with frame.run_lock(self.cfg):
                zart.set()
                engedd.wait(5)
        t = threading.Thread(target=tart)
        t.start()
        zart.wait(5)
        threading.Timer(0.5, engedd.set).start()
        ki = mentes.kilepeskor(self.cfg)
        t.join(5)
        self.assertEqual([p.name.split("-")[0] for p in ki], ["vault"])
        self.assertIsNone(mentes.hiba_olvas(self.cfg))

    def test_turelem_utan_a_hiba_megnevezi(self):
        self.cfg.data.setdefault("mentes", {})["kilepes_turelem_mp"] = 0.2
        zart, engedd = threading.Event(), threading.Event()

        def tart():
            with frame.run_lock(self.cfg):
                zart.set()
                engedd.wait(5)
        t = threading.Thread(target=tart)
        t.start()
        zart.wait(5)
        try:
            self.assertEqual(mentes.kilepeskor(self.cfg), [])
        finally:
            engedd.set()
            t.join(5)
        self.assertIn("0.2 s várakozás után", mentes.hiba_olvas(self.cfg)["hibak"]["mentes"])

    def test_git_idokorlat_magyar_mentes_hiba(self):
        def lassu(*a, **k):
            raise subprocess.TimeoutExpired(a[0], k.get("timeout"))
        with mock.patch.object(mentes.subprocess, "run", lassu):
            with self.assertRaises(mentes.MentesHiba) as cm:
                mentes.friss(self.repo, self.backup)
            self.assertIn("nem válaszolt", str(cm.exception))
            hibak = {}
            self.assertEqual(mentes.ment(self.cfg, csak_ha_valtozott=True, hibak=hibak, allapot=False), [])
            self.assertIn("vault", hibak)

    def test_kodtar_bundle_idokorlatnal_nem_marad_tmp(self):
        git_init(self.root)
        eredeti = mentes.subprocess.run

        def run(parancs, *a, **k):
            if "bundle" in parancs and "create" in parancs:
                Path(parancs[parancs.index("-q") + 1]).write_bytes(b"felkesz")
                raise subprocess.TimeoutExpired(parancs, k.get("timeout"))
            return eredeti(parancs, *a, **k)
        with mock.patch.object(mentes.subprocess, "run", run):
            hibak = {}
            mentes.ment(self.cfg, hibak=hibak, allapot=False)
        self.assertIn("kodtar", hibak)
        self.assertIn("nem válaszolt", hibak["kodtar"])
        self.assertEqual(self.nevek("mos-kodtar-*"), [])


if __name__ == "__main__":
    unittest.main()
