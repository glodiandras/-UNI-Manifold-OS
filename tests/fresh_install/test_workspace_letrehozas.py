"""F3 kapu (PLAN F3, F3-DESIGN §3.3): munkatér létrehozása friss telepítésben.

Üres mappából `.obsidian` + `.manifold` + élő pillanatkép-tároló + az első `kezi` commit; egy meglévő Obsidian-vault a
`.obsidian`/`.manifold`-on kívül bájtra azonos marad; minden lépés utáni összeomlás után a létrehozás folytatható (ugyanazzal az
azonosítóval, egyetlen kezdő commit); a `.manifold` törlése bájtra visszaadja az eredeti vaultot (I7); a beágyazott, a telepítés
alatti, a hálózati és a hordozható elrendezésű létrehozás tiltott."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from core import config, snapshot, workspace
from tests import csak_darwin
from tests.fresh_install import lenyomat, obsidian_vault, termek_alap, termek_cfg
from tests.helpers import REPO, alg_gyoker, env, tmpdir


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.install = self.home / "Library" / "Application Support" / "Manifold"

    def cfg(self, v: Path):
        return termek_cfg(self.root, self.home, v)

    def kuka(self):
        """Ál-Kuka: a Kukába tett elem egy külön mappába kerül (mint a héj `--kuka`-ja: semmi nem törlődik)."""
        kuka = self.t / "Kuka"
        kuka.mkdir(exist_ok=True)
        tett = []

        def tesz(p: Path):
            cel = kuka / f"{len(tett)}-{Path(p).name}"
            shutil.move(str(p), str(cel))
            tett.append(cel)
        return tesz, tett


class UresMappabolTest(_Alap):
    def test_uj_mappabol_obsidian_manifold_elo_tarolo_es_kezi_commit(self):
        v = self.t / "Új jegyzetek"
        lepesek = []
        r = workspace.letrehoz(v, self.alap, uj_mappa=True, haladas=lambda d: lepesek.append(d["lepes"]))
        self.assertTrue(r["uj"])
        self.assertEqual(lepesek, ["felmeres", "mappak", "tarolo", "pillanatkep", "beallitasok", "regiszter", "kesz"])
        self.assertTrue((v / ".obsidian").is_dir())
        self.assertEqual(os.listdir(v / ".obsidian"), [])                 # üres, mint az Obsidianban; nem írunk bele
        ws = v / ".manifold"
        self.assertEqual((ws / ".gitignore").read_text(), "var/\n")
        self.assertIn("Delete it to remove Manifold", (ws / "README.txt").read_text())
        for d in ("state", "tmp", "run", "runs", "cache", "index"):
            self.assertTrue((ws / "var" / d).is_dir(), d)
        self.assertTrue((ws / "var" / ".metadata_never_index").is_file())
        w = tomllib.loads((ws / "workspace.toml").read_text(encoding="utf-8"))["workspace"]
        self.assertEqual(w, {"id": r["id"], "formatum": 1, "olvaso_min": 1, "nev": "Új jegyzetek", "nyelv": "en",
                             "presetek": [], "obsidian_letrehozva": True})
        self.assertRegex(r["id"], r"^[0-9a-f]{32}$")
        # a core konfigurációja a workspace.toml-ból (a W réteg), az állapot a vaultban
        cfg = self.cfg(v)
        self.assertEqual((cfg.workspace_id, cfg.path("var")), (r["id"], ws / "var"))
        repo = snapshot.repos(cfg)["vault"]
        self.assertTrue(repo.live())
        self.assertIn(".manifold/", (repo.git_dir / "info" / "exclude").read_text())
        self.assertEqual(repo.git("config", "--get", "core.worktree").stdout.strip(), str(v))
        # üres mappa: nincs mit rögzíteni → nincs commit, de a tároló él, és a munkatér nem piszkos
        self.assertEqual((r["commit"], repo.dirty()), (None, []))
        # regiszter
        reg = workspace.Regiszter(self.install).olvas()
        e = reg["munkaterek"][r["id"]]
        self.assertEqual(reg["utolso"], r["id"])
        self.assertEqual((e["vault"], e["allapot"], e["nev"], e["demo"]), (str(v), "vault", "Új jegyzetek", False))
        self.assertEqual(e["kanonikus"], os.path.realpath(v))
        self.assertEqual(e["inode"], os.stat(ws).st_ino)
        for k in ("kotet_uuid", "letrehozva", "megnyitva"):
            self.assertIn(k, e)

    def test_preset_es_hibas_beallitas(self):
        v = self.t / "P"
        v.mkdir()
        with self.assertRaises(config.ConfigError) as e:
            workspace.letrehoz(v, self.alap, presetek=["nincs-ilyen"])
        self.assertEqual(e.exception.kod, "workspace_beallitas_hibas")
        self.assertEqual(os.listdir(v), [])                                # semmi nem jött létre
        r = workspace.letrehoz(v, self.alap, presetek=["v2-kompat"], nyelv="hu")
        cfg = self.cfg(v)
        self.assertEqual((cfg.section("workspace")["presetek"], cfg.section("workspace")["nyelv"]), (["v2-kompat"], "hu"))
        self.assertEqual(cfg.workspace_id, r["id"])

    @csak_darwin("Time Machine-kizárás (xattr)")
    def test_time_machine_kizaras_csak_az_ujraepitheto_mappakon(self):
        v = self.t / "TM"
        workspace.letrehoz(v, self.alap, uj_mappa=True)
        var = v / ".manifold" / "var"
        jel = lambda d: subprocess.run(["xattr", "-p", "com.apple.metadata:com_apple_backup_excludeItem", str(d)],  # noqa: E731
                                       capture_output=True).returncode == 0
        self.assertEqual({d: jel(var / d) for d in ("tmp", "cache", "index", "state", "run", "runs")},
                         {"tmp": True, "cache": True, "index": True, "state": False, "run": False, "runs": False})

    def test_a_mappa_szuloje_hianyzik_vagy_nem_letezik(self):
        f = workspace.felmer(self.t / "nincs" / "Jegyzetek", self.alap, uj=True)
        self.assertEqual((f.eredmeny, f.akadaly), ("tilos", ["szulo_hianyzik"]))
        f = workspace.felmer(self.t / "Jegyzetek", self.alap)
        self.assertEqual((f.eredmeny, f.akadaly), ("tilos", ["nem_letezik"]))
        with self.assertRaises(config.ConfigError) as e:
            workspace.letrehoz(self.t / "nincs" / "Jegyzetek", self.alap, uj_mappa=True)
        self.assertEqual(e.exception.kod, "szulo_hianyzik")
        self.assertFalse((self.t / "nincs").exists())                     # leválasztott kötet alá soha nem hoz létre

    def test_a_ures_mappa_teljes_eltavolitasa_ures_mappat_hagy(self):
        v = self.t / "Üres"
        v.mkdir()
        r = workspace.letrehoz(v, self.alap)
        kuka, tett = self.kuka()
        e = workspace.eltavolit(v, self.alap, kuka)
        self.assertEqual((e["id"], e["obsidian_torolve"]), (r["id"], True))
        self.assertEqual(os.listdir(v), [])
        self.assertEqual([p.name for p in tett], ["0-.manifold"])           # a .manifold a Kukába, nem törlődik
        self.assertNotIn(r["id"], workspace.Regiszter(self.install).olvas()["munkaterek"])


class ObsidianVaultTest(_Alap):
    def setUp(self):
        super().setUp()
        self.v = obsidian_vault(self.t / "Vault")
        self.elotte = lenyomat(self.v, kihagy=())

    def test_meglevo_vault_bajtra_azonos_es_az_elso_commit_kezi(self):
        f = workspace.felmer(self.v, self.alap)
        self.assertEqual((f.akadaly, f.meglevo_id, f.reszleges, f.md_db), ([], None, False, 5))
        self.assertEqual(f.obsidian["templates"], {"folder": "Sablonok"})
        self.assertNotIn("obsidian", f.letrehozando)
        r = workspace.letrehoz(self.v, self.alap, nev="Fizika")
        self.assertEqual(lenyomat(self.v), self.elotte)                   # a .manifold-on kívül (a .obsidian is) érintetlen
        cfg = self.cfg(self.v)
        repo = snapshot.repos(cfg)["vault"]
        (c,) = repo.log(5)
        self.assertEqual((c.sha, c.trailers), (r["commit"], {"Mos-Forras": "kezi"}))
        fajlok = set(repo.git("ls-files", "-z").stdout.split("\0")) - {""}
        self.assertIn("Kezdőlap.md", fajlok)
        self.assertIn(".obsidian/app.json", fajlok)
        self.assertFalse([f for f in fajlok if f.startswith(".manifold")])
        self.assertEqual(repo.dirty(), [])
        # a W réteg magja az Obsidian beállításaiból (csak olvasva)
        w = tomllib.loads((self.v / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
        self.assertEqual(w["workspace"]["nev"], "Fizika")
        self.assertFalse(w["workspace"]["obsidian_letrehozva"])
        self.assertEqual(w["sablon"], {"mappa": "Sablonok"})
        self.assertEqual(w["naplo"], {"ut": "[Napló]/YYYY-MM-DD", "sablon": "Sablonok/Napi.md"})
        self.assertTrue((self.v / w["naplo"]["sablon"]).is_file(), "a napi sablon a vault-relatív útján feloldható")
        self.assertEqual((cfg.section("naplo")["ut"], cfg.forras("naplo", "ut")), ("[Napló]/YYYY-MM-DD", "munkater"))

    def test_a_manifold_torlese_bajtra_visszaadja_a_vaultot_I7(self):
        workspace.letrehoz(self.v, self.alap)
        shutil.rmtree(self.v / ".manifold")
        self.assertEqual(lenyomat(self.v, kihagy=()), self.elotte)

    def test_eltavolitas_a_meglevo_obsidian_mappat_megtartja(self):
        r = workspace.letrehoz(self.v, self.alap)
        kuka, tett = self.kuka()
        e = workspace.eltavolit(self.v, self.alap, kuka)
        self.assertEqual((e["obsidian_torolve"], len(tett)), (False, 1))
        self.assertEqual(lenyomat(self.v, kihagy=()), self.elotte)
        self.assertNotIn(r["id"], workspace.Regiszter(self.install).olvas()["munkaterek"])

    def test_eltavolitas_futo_core_mellett_tilos(self):
        import fcntl
        workspace.letrehoz(self.v, self.alap)
        zar = self.v / ".manifold" / "var" / "run" / "core.lock"
        with open(zar, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(config.ConfigError) as e:
                workspace.eltavolit(self.v, self.alap, lambda p: self.fail("nem tehet a Kukába"))
        self.assertEqual(e.exception.kod, "munkater_hasznalatban")
        self.assertTrue((self.v / ".manifold" / "workspace.toml").is_file())

    def test_ismetelt_letrehozas_idempotens(self):
        r1 = workspace.letrehoz(self.v, self.alap)
        r2 = workspace.letrehoz(self.v, self.alap)
        self.assertEqual((r2["id"], r2["uj"]), (r1["id"], False))
        repo = snapshot.repos(self.cfg(self.v))["vault"]
        self.assertEqual(len(repo.log(5)), 1)

    def test_osszeomlas_minden_lepes_utan_folytathato(self):
        class Halal(BaseException):
            pass

        for lepes in ("mappak", "tarolo", "pillanatkep", "beallitasok", "regiszter", "kesz"):
            with self.subTest(lepes=lepes):
                t = tmpdir()
                self.addCleanup(t.cleanup)
                root, home, alap = termek_alap(t.name)
                v = obsidian_vault(Path(t.name) / "Vault")
                elotte = lenyomat(v, kihagy=())

                def hal(d, lepes=lepes):
                    if d["lepes"] == lepes:
                        raise Halal()
                with self.assertRaises(Halal):
                    workspace.letrehoz(v, alap, haladas=hal)
                f = workspace.felmer(v, alap)
                vegleges = lepes in ("regiszter", "kesz")                 # a workspace.toml (véglegesítési pont) már megvan
                self.assertEqual(f.reszleges, lepes in ("tarolo", "pillanatkep", "beallitasok"))
                self.assertEqual(f.meglevo_id is not None, vegleges)
                jel = v / ".manifold" / "var" / "letrehozas.json"
                elso_id = json.loads(jel.read_text())["id"] if jel.is_file() else None
                r = workspace.letrehoz(v, alap)
                if elso_id:
                    self.assertEqual(r["id"], elso_id)                    # a folytatás ugyanazt az azonosítót használja
                self.assertEqual(r["uj"], not vegleges)
                cfg = termek_cfg(root, home, v)
                self.assertEqual(cfg.workspace_id, r["id"])
                repo = snapshot.repos(cfg)["vault"]
                self.assertEqual(len(repo.log(5)), 1)                     # egyetlen kezdő kézi commit
                self.assertEqual(repo.dirty(), [])
                install = home / "Library" / "Application Support" / "Manifold"
                self.assertIn(r["id"], workspace.Regiszter(install).olvas()["munkaterek"])
                self.assertEqual(lenyomat(v), elotte)


class TiltasTest(_Alap):
    def test_beagyazott_munkater_tilos_mindket_iranyban(self):
        kulso = self.t / "Kulso"
        kulso.mkdir()
        workspace.letrehoz(kulso, self.alap)
        (kulso / "Belso").mkdir()
        f = workspace.felmer(kulso / "Belso", self.alap)
        self.assertIn("munkateren_belul", f.akadaly)
        szulo = self.t
        f = workspace.felmer(szulo, self.alap)
        self.assertIn("munkateret_tartalmaz", f.akadaly)
        with self.assertRaises(config.ConfigError) as e:
            workspace.letrehoz(kulso / "Belso", self.alap)
        self.assertEqual(e.exception.kod, "munkateren_belul")
        self.assertFalse((kulso / "Belso" / ".manifold").exists())

    def test_a_telepites_es_a_kodfa_alatt_tilos(self):
        (self.install / "x").mkdir(parents=True)
        self.assertIn("telepitesben", workspace.felmer(self.install / "x", self.alap).akadaly)
        (self.root / "jegyzet").mkdir()
        self.assertIn("kodfaban", workspace.felmer(self.root / "jegyzet", self.alap).akadaly)
        self.assertIn("telepitest_tartalmaz", workspace.felmer(self.home, self.alap).akadaly)
        # a bemutató munkatér a {install}/demo alatt engedett
        r = workspace.letrehoz(self.install / "demo" / "Manifold Demo", self.alap, demo=True)
        self.assertTrue(workspace.Regiszter(self.install).olvas()["munkaterek"][r["id"]]["demo"])

    def test_halozati_kotet_tilos_nem_apfs_figyelmeztet(self):
        v = self.t / "V"
        v.mkdir()
        with mock.patch.object(workspace, "_statfs", return_value=("smbfs", False, "/Volumes/halo")):
            f = workspace.felmer(v, self.alap)
        self.assertEqual(f.eredmeny, "tilos")
        self.assertIn("halozati_kotet", f.akadaly)
        self.assertEqual((f.fajlrendszer, f.helyi), ("smbfs", False))
        with mock.patch.object(workspace, "_statfs", return_value=("exfat", True, "/Volumes/usb")):
            f = workspace.felmer(v, self.alap)
        self.assertEqual(f.akadaly, [])
        self.assertIn("nem_apfs", f.figyelmeztetes)
        self.assertEqual(f.eredmeny, "figyelmeztet")

    def test_hordozhato_elrendezesben_nem_hoz_letre(self):
        root = alg_gyoker(str(self.t / "h"))
        alap = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        v = root.parent / "Manifold"
        (v / ".obsidian").mkdir()
        f = workspace.felmer(v, alap)
        self.assertIn("hordozhato_elrendezes", f.akadaly)
        with self.assertRaises(config.ConfigError):
            workspace.letrehoz(v, alap)
        self.assertFalse((v / ".manifold").exists())

    def test_ujabb_formatum_es_hibas_toml_tilos(self):
        v = self.t / "V"
        (v / ".manifold").mkdir(parents=True)
        (v / ".manifold" / "workspace.toml").write_text(
            f'[workspace]\nid = "{"a" * 32}"\nformatum = 3\nolvaso_min = 2\n', encoding="utf-8")
        f = workspace.felmer(v, self.alap)
        self.assertEqual((f.meglevo_id, f.formatum), ("a" * 32, 3))
        self.assertIn("workspace_ujabb", f.akadaly)
        (v / ".manifold" / "workspace.toml").write_text("[workspace\n", encoding="utf-8")
        self.assertIn("workspace_toml_hibas", workspace.felmer(v, self.alap).akadaly)

    def test_masik_telepites_fut_a_vaulton(self):
        import fcntl
        v = self.t / "Manifold"
        v.mkdir()
        zar = self.t / "Manifold-OS v2" / "var" / "run" / "core.lock"
        zar.parent.mkdir(parents=True)
        zar.write_text(f"pid 1 · {v}")
        self.assertNotIn("masik_telepites_fut", workspace.felmer(v, self.alap).akadaly)     # a zár szabad
        with open(zar, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn("masik_telepites_fut", workspace.felmer(v, self.alap).akadaly)
            (self.t / "Masik").mkdir()
            self.assertNotIn("masik_telepites_fut", workspace.felmer(self.t / "Masik", self.alap).akadaly)
        self.assertEqual(zar.read_text(), f"pid 1 · {v}")                 # csak olvasva vizsgálta


class SzinkronMappaTest(_Alap):
    def test_szinkron_mappaban_az_allapot_a_telepites_alatt(self):
        v = self.home / "Library" / "CloudStorage" / "Felho" / "Jegyzetek"
        (v / ".obsidian").mkdir(parents=True)
        (v / "a.md").write_text("a")
        f = workspace.felmer(v, self.alap)
        self.assertEqual((f.szinkron, f.figyelmeztetes[:1]), ("cloudstorage", ["szinkron_mappa"]))
        self.assertIn("allapot_telepitesben", f.letrehozando)
        r = workspace.letrehoz(v, self.alap)
        var = self.install / "workspaces" / r["id"] / "var"
        self.assertEqual((r["allapot"], r["var"]), ("telepites", str(var)))
        self.assertEqual(sorted(os.listdir(v / ".manifold")), [".gitignore", "README.txt", "workspace.toml"])
        cfg = self.cfg(v)                                                   # a regiszter dönt (a vault soha)
        self.assertEqual((cfg.path("var"), cfg.forras("utak", "var")), (var, "regiszter"))
        self.assertEqual(len(snapshot.repos(cfg)["vault"].log(5)), 1)

    def test_allapot_mas_koteten_figyelmeztet(self):
        """§3.7: a `{var}` a vault kötetén kell legyen (klón, atomi csere); különben csökkentett mód, figyelmeztetéssel."""
        v = self.home / "Library" / "CloudStorage" / "Felho" / "V"
        (v / ".obsidian").mkdir(parents=True)
        self.assertNotIn("allapot_mas_koteten", workspace.felmer(v, self.alap).figyelmeztetes)
        install = self.install

        def eszkoz(p):
            return 2 if Path(p) == install / "workspaces" else 1
        with mock.patch.object(workspace, "_eszkoz", eszkoz):
            f = workspace.felmer(v, self.alap)
        self.assertIn("allapot_mas_koteten", f.figyelmeztetes)
        self.assertEqual(f.eredmeny, "figyelmeztet")
        sima = self.t / "Sima"
        (sima / ".obsidian").mkdir(parents=True)
        with mock.patch.object(workspace, "_eszkoz", eszkoz):                # nem szinkronizált: a `.manifold` a vault kötetén
            self.assertNotIn("allapot_mas_koteten", workspace.felmer(sima, self.alap).figyelmeztetes)

    def test_icloud_es_dropbox_felismerese(self):
        icloud = self.home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "V"
        dropbox = self.t / "Dropbox" / "V"
        for p in (icloud, dropbox):
            p.mkdir(parents=True)
        self.assertEqual(workspace.felmer(icloud, self.alap).szinkron, "icloud")
        self.assertEqual(workspace.felmer(dropbox, self.alap).szinkron, "dropbox")
        self.assertIsNone(workspace.felmer(self.t, self.alap).szinkron)


class ParancssorTest(_Alap):
    def futtat(self, *args):
        e = env(MOS_ROOT=str(self.root), HOME=str(self.home))
        p = subprocess.run([sys.executable, "-B", "-m", "core.workspace", *args], cwd=REPO, env=e,
                           capture_output=True, text=True, timeout=120)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout)

    def test_felmer_letrehoz_lista_eltavolit(self):
        v = self.t / "Cli vault"
        (v / ".obsidian").mkdir(parents=True)
        kod, f = self.futtat(str(v), "--json")                            # alapértelmezés: felmer
        self.assertEqual((kod, f["akadaly"], f["meglevo_id"]), (0, [], None))
        kod, r = self.futtat("letrehoz", str(v), "--json", "--igen", "--nev", "Cli")
        self.assertEqual((kod, r["uj"]), (0, True))
        kod, lista = self.futtat("lista", "--json")
        self.assertEqual(lista["munkaterek"][r["id"]]["nev"], "Cli")
        kod, h = self.futtat("eltavolit", str(v), "--json")               # megerősítés nélkül nem tesz semmit
        self.assertEqual((kod, h["hiba"]), (1, "megerosites_kell"))
        self.assertTrue((v / ".manifold" / "workspace.toml").is_file())
        kod, h = self.futtat("felmer", str(self.root), "--json")
        self.assertEqual(kod, 1)
        self.assertIn("kodfaban", h["akadaly"])
        kod, h = self.futtat("elfelejt", r["id"], "--json")
        self.assertEqual((kod, h["ok"]), (0, True))
        self.assertTrue((v / ".manifold").is_dir())                       # az elfelejtés fájlt nem töröl


@csak_darwin("APFS: a munkatér kötete")
class KotetTest(_Alap):
    def test_felmeres_kotet_adatai(self):
        f = workspace.felmer(self.t, self.alap)
        self.assertTrue(f.helyi)
        self.assertTrue(f.fajlrendszer)
        self.assertGreater(f.szabad_bajt, 0)
        self.assertIsInstance(f.kis_nagy_erzekeny, bool)
        if not f.kis_nagy_erzekeny:                                          # a lemezen álló alak, bármilyen írásmódból
            self.assertEqual(workspace.kanonikus(Path(str(self.t).swapcase())), os.path.realpath(self.t))


if __name__ == "__main__":
    unittest.main()
