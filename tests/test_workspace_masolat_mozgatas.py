"""F3-DESIGN §3.4: megnyitáskor (`workspace.nyit`) az azonosság a regiszterrel.

Áthelyezett munkatér: a regiszter frissül, a `core.worktree` az új helyre mutat, és egy függő átnevezés-napló (vault-relatív) az
új helyen áll vissza. Másolat: új azonosító (a `workspace.toml` többi tartalma marad), új regiszter-bejegyzés, a régi érintetlen,
a másolat a saját (másolt) történetével indul; az `ujratolt` az új azonosítóval tölti újra a konfigurációt. Az azonos nevű,
cserélt lemez a `Vault` szemében „nem elérhető” marad (`workspace_csere`)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

from core import atnevezes, config, snapshot, vaultio, workspace
from tests import csak_darwin
from tests.fresh_install import lenyomat, termek_alap, termek_cfg
from tests.helpers import tmpdir
from tests.index_segedek import index_indit


def _worktree(cfg) -> str:
    repo = snapshot.repos(cfg)["vault"]
    return repo.git("config", "--get", "core.worktree").stdout.strip()


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.install = self.alap.path("install")
        self.v = self.t / "Eredeti"
        (self.v / ".obsidian").mkdir(parents=True)
        (self.v / "Cél.md").write_text("# Cél\n", encoding="utf-8")
        (self.v / "Hivo.md").write_text("A [[Cél]] link.\n", encoding="utf-8")
        self.id = workspace.letrehoz(self.v, self.alap)["id"]

    def cfg(self, v: Path, **extra):
        return termek_cfg(self.root, self.home, v, **extra)

    def reg(self) -> dict:
        return workspace.Regiszter(self.install).olvas()


class NyitTest(_Alap):
    def test_ugyanott_rendben_es_hordozhatoban_semmit_nem_tesz(self):
        self.assertEqual(workspace.nyit(self.cfg(self.v)), [])
        self.assertEqual(list(self.reg()["munkaterek"]), [self.id])
        self.assertIsNone(workspace.ujratolt(self.cfg(self.v), {}))

    def test_ismeretlen_azonosito_uj_bejegyzes(self):
        (self.install / "workspaces.json").unlink()                        # a regiszter elveszett: csak a lista vész el
        self.assertEqual(workspace.nyit(self.cfg(self.v)), [])
        e = self.reg()["munkaterek"][self.id]
        self.assertEqual((e["vault"], e["allapot"]), (str(self.v), "vault"))

    def test_elveszett_allapot_uj_tarolo_szinkron_kezi_elso_commit(self):
        cfg = self.cfg(self.v)
        shutil.rmtree(snapshot.repos(cfg)["vault"].git_dir)                  # a `.manifold/var` állapota elveszett
        self.assertEqual(workspace.nyit(cfg), [])
        repo = snapshot.repos(cfg)["vault"]
        self.assertTrue(repo.live())
        naplo = repo.log(5)
        self.assertEqual([(c.subject, c.trailers.get("Mos-Forras")) for c in naplo], [("munkatér megnyitva", "kezi")])
        self.assertEqual(repo.dirty(), [])
        self.assertEqual(_worktree(cfg), str(self.v))
        self.assertEqual(workspace.nyit(cfg), [])
        self.assertEqual(len(repo.log(5)), 1)                               # másodszor nincs új commit

    def test_ujabb_formatum_megtagadva(self):
        toml = self.v / ".manifold" / "workspace.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace("olvaso_min = 1", "olvaso_min = 9"), encoding="utf-8")
        with self.assertRaises(config.ConfigError) as e:
            workspace.nyit(self.cfg(self.v))
        self.assertEqual(e.exception.kod, "workspace_ujabb")

    def test_athelyezett_munkater_a_regiszter_es_a_worktree_kovet(self):
        uj = self.t / "Mashol" / "Athelyezett"
        uj.parent.mkdir()
        os.rename(self.v, uj)
        cfg = self.cfg(uj)
        self.assertEqual(_worktree(cfg), str(self.v))                      # elavult (csak a külső eszközöket vezetné félre)
        uzenetek = workspace.nyit(cfg)
        self.assertEqual(len(uzenetek), 1)
        self.assertIn("új helyen", uzenetek[0])
        e = self.reg()["munkaterek"][self.id]
        self.assertEqual((e["vault"], e["kanonikus"], list(self.reg()["munkaterek"])),
                         (str(uj), workspace.kanonikus(uj), [self.id]))
        self.assertEqual(_worktree(cfg), str(uj))
        self.assertEqual(snapshot.repos(cfg)["vault"].dirty(), [])
        self.assertEqual(workspace.nyit(cfg), [])                          # másodszor már rendben

    def test_athelyezett_munkater_fuggo_atnevezes_naploja_az_uj_helyen_all_vissza(self):
        cfg = self.cfg(self.v)
        elotte = lenyomat(self.v)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        a = atnevezes.Atnevezes(cfg, vaultio.Vault(cfg), ix)
        a._visszaallit = lambda lepesek: None                              # a halott folyamat nem állít vissza semmit

        class Halal(BaseException):
            pass
        t = a.terv("Cél.md", "Új cél.md")
        eredeti = a._ir

        def ir_es_hal(p, b, **k):
            eredeti(p, b, **k)
            raise Halal()
        a._ir = ir_es_hal
        with self.assertRaises(Halal):
            a.vegrehajt("Cél.md", "Új cél.md", t["terv_hash"])
        ix.leallit()
        self.assertNotEqual(lenyomat(self.v), elotte)
        self.assertTrue((cfg.path("run") / "atnevezes" / "terv.json").is_file())
        uj = self.t / "Athelyezett"
        os.rename(self.v, uj)                                              # a napló (`.manifold/var/run`) a mappával utazik
        ucfg = self.cfg(uj)
        workspace.nyit(ucfg)
        uzenetek = atnevezes.helyreallit(ucfg)
        self.assertTrue(uzenetek)
        self.assertEqual(lenyomat(uj), elotte)
        self.assertFalse((ucfg.path("run") / "atnevezes").exists())

    def test_masolat_uj_azonositot_kap_a_regi_erintetlen(self):
        (self.v / ".manifold" / "workspace.toml").write_text(
            (self.v / ".manifold" / "workspace.toml").read_text(encoding="utf-8") + "\n# saját megjegyzés\n[naplo]\nut = \"N/YYYY\"\n",
            encoding="utf-8")
        masolat = self.t / "Masolat"
        subprocess.run(["cp", "-R", str(self.v), str(masolat)], check=True)
        eredeti_toml = (self.v / ".manifold" / "workspace.toml").read_bytes()
        ccfg = self.cfg(masolat)
        self.assertEqual(ccfg.workspace_id, self.id)
        uzenetek = workspace.nyit(ccfg)
        self.assertEqual(len(uzenetek), 1)
        self.assertIn("másolata", uzenetek[0])
        uj_id = workspace.azonosit(masolat)
        self.assertRegex(uj_id, r"^[0-9a-f]{32}$")
        self.assertNotEqual(uj_id, self.id)
        szoveg = (masolat / ".manifold" / "workspace.toml").read_text(encoding="utf-8")
        self.assertEqual(szoveg, eredeti_toml.decode("utf-8").replace(self.id, uj_id))   # csak az azonosító változott
        self.assertEqual((self.v / ".manifold" / "workspace.toml").read_bytes(), eredeti_toml)
        r = self.reg()
        self.assertEqual(sorted(r["munkaterek"]), sorted([self.id, uj_id]))
        self.assertEqual((r["munkaterek"][self.id]["vault"], r["munkaterek"][uj_id]["vault"]), (str(self.v), str(masolat)))
        self.assertEqual(r["utolso"], uj_id)
        # a régi cfg elavult: a `Vault` nem enged dolgozni vele; az `ujratolt` az új azonosítóval tölt újra
        with self.assertRaises(vaultio.NemElerheto) as e:
            vaultio.Vault(ccfg).root
        self.assertEqual(e.exception.kod, "workspace_csere")
        env = {"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(masolat),
               "MOS_WORKSPACE_ID": self.id, "MOS_BACKUP": str(ccfg.path("backup")), "MOS_VAR": str(ccfg.path("var")),
               "MOS_INSTALL": str(self.install)}
        ucfg = workspace.ujratolt(ccfg, env)
        self.assertEqual((env["MOS_WORKSPACE_ID"], "MOS_BACKUP" in env, env["MOS_INSTALL"]), (uj_id, False, str(self.install)))
        self.assertEqual((ucfg.workspace_id, ucfg.path("backup")), (uj_id, self.install / "backups" / uj_id))
        self.assertEqual(vaultio.Vault(ucfg).root, masolat)
        # a másolat a saját, másolt történetével él; a worktree a másolatra mutat
        self.assertEqual(_worktree(ucfg), str(masolat))
        self.assertEqual(len(snapshot.repos(ucfg)["vault"].log(5)), 1)
        self.assertEqual(_worktree(self.cfg(self.v)), str(self.v))
        self.assertEqual(workspace.nyit(self.cfg(self.v)), [])             # az eredeti megnyitása rendben
        self.assertEqual(workspace.nyit(ucfg), [])


@csak_darwin("APFS-klón (`cp -c`): a szinkronizált munkatér állapota a telepítés kötetén")
class SzinkronMasolatTest(unittest.TestCase):
    def test_szinkron_mappa_masolata_klonozott_allapottal_indul_az_eredetit_nem_erinti(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        root, home, alap = termek_alap(t.name)
        felho = home / "Library" / "CloudStorage" / "Felho"
        v = felho / "Jegyzetek"
        (v / ".obsidian").mkdir(parents=True)
        (v / "a.md").write_text("a", encoding="utf-8")
        id = workspace.letrehoz(v, alap)["id"]
        install = alap.path("install")
        masolat = felho / "Masolat"
        subprocess.run(["cp", "-R", str(v), str(masolat)], check=True)
        ccfg = termek_cfg(root, home, masolat)
        # a másolat nem kapja meg az eredeti regisztrált állapotát (az azonosító a vaulttal utazik, a bejegyzés az eredeti útjához kötött)
        self.assertEqual(ccfg.path("var"), masolat / ".manifold" / "var")
        self.assertEqual(len(workspace.nyit(ccfg)), 1)
        uj = workspace.azonosit(masolat)
        self.assertNotEqual(uj, id)
        self.assertEqual(_worktree(termek_cfg(root, home, v)), str(v))     # az eredeti tárolója érintetlen
        env = {"MOS_ROOT": str(root), "HOME": str(home), "MOS_VAULT": str(masolat), "MOS_VAR": str(ccfg.path("var"))}
        ucfg = workspace.ujratolt(ccfg, env)
        self.assertEqual(ucfg.path("var"), install / "workspaces" / uj / "var")
        self.assertEqual(_worktree(ucfg), str(masolat))
        self.assertEqual(len(snapshot.repos(ucfg)["vault"].log(5)), 1)    # a klónozott történet
        self.assertEqual(workspace.nyit(ucfg), [])


class SzinkronMasikGepTest(unittest.TestCase):
    def test_masik_macen_az_allapot_a_telepites_alatt_jon_letre_soha_nem_a_felhoben(self):
        """§3.7: a szinkronizált munkatér `workspace.toml`-ja átjön egy másik Macre, a regiszter és az állapot nem. A megnyitás
        a telepítés alá teszi az állapotot, és ott szinkron, kézi első commit készül."""
        t = tmpdir()
        self.addCleanup(t.cleanup)
        root, home, alap = termek_alap(t.name)
        v = home / "Library" / "CloudStorage" / "Felho" / "Jegyzetek"
        (v / ".obsidian").mkdir(parents=True)
        (v / "a.md").write_text("a", encoding="utf-8")
        id = workspace.letrehoz(v, alap)["id"]
        install = alap.path("install")
        (install / "workspaces.json").unlink()                               # a „másik Mac”: nincs regiszter-bejegyzés…
        shutil.rmtree(install / "workspaces" / id)                           # …és nincs állapot
        cfg = termek_cfg(root, home, v)
        self.assertEqual(cfg.path("var"), v / ".manifold" / "var")          # a regiszter nélkül a `cfg` még a vaultra mutat
        self.assertEqual(workspace.nyit(cfg), [])
        self.assertEqual(workspace.Regiszter(install).olvas()["munkaterek"][id]["allapot"], "telepites")
        self.assertFalse((v / ".manifold" / "var").exists())                # a felhőben nem jött létre tároló
        env = {"MOS_ROOT": str(root), "HOME": str(home), "MOS_VAULT": str(v), "MOS_VAR": str(cfg.path("var"))}
        ucfg = workspace.ujratolt(cfg, env)
        var = install / "workspaces" / id / "var"
        self.assertEqual((ucfg.workspace_id, ucfg.path("var"), "MOS_VAR" in env), (id, var, False))
        repo = snapshot.repos(ucfg)["vault"]
        self.assertTrue(repo.live())
        self.assertEqual([(c.subject, c.trailers.get("Mos-Forras")) for c in repo.log(5)], [("munkatér megnyitva", "kezi")])
        self.assertEqual(_worktree(ucfg), str(v))
        self.assertFalse((v / ".manifold" / "var").exists())
        self.assertEqual(workspace.nyit(ucfg), [])
        self.assertIsNone(workspace.ujratolt(ucfg, dict(env)))


class VaultAzonossagTest(_Alap):
    def test_cserelt_lemez_nem_elerheto_marad(self):
        cfg = self.cfg(self.v)
        esemenyek = []
        V = vaultio.Vault(cfg, publish=lambda e, **k: esemenyek.append(e))
        self.assertEqual(V.root, self.v)
        tarolt = self.t / "lemez"
        os.rename(self.v, tarolt)                                          # a kötet eltűnt
        with self.assertRaises(vaultio.NemElerheto) as e:
            V.root
        self.assertEqual(e.exception.kod, "vault_nem_elerheto")
        # azonos nevű, másik lemez: ugyanott egy másik munkatér
        (self.v / ".obsidian").mkdir(parents=True)
        (self.v / ".manifold").mkdir()
        (self.v / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{"e" * 32}"\n', encoding="utf-8")
        for _ in range(2):
            with self.assertRaises(vaultio.NemElerheto) as e:
                V.root
            self.assertEqual(e.exception.kod, "workspace_csere")
        shutil.rmtree(self.v)
        os.rename(tarolt, self.v)                                          # az eredeti visszajött
        self.assertEqual(V.root, self.v)
        self.assertEqual([x["elerheto"] for x in esemenyek], [False, True])


if __name__ == "__main__":
    unittest.main()
