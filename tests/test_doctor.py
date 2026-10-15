import json
import os
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from core import config, doctor, snapshot
from tests.helpers import REPO, alg_gyoker, tmpdir


def futtat(root: Path, home: Path, env: dict | None = None, python: Path | None = None) -> dict:
    cfg = config.load({"MOS_ROOT": str(root), "HOME": str(home)})
    e = {"HF_HUB_OFFLINE": "1"} | (env or {})
    return {r.nev: r for r in doctor.ellenoriz(cfg, e, home, python or root / "runtime" / "python" / "bin" / "python3")}


class DoctorTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name)
        self.home = Path(self._t.name) / "home"
        (self.home / "Applications").mkdir(parents=True)
        rt = self.root / "runtime"
        (rt / "python" / "bin").mkdir(parents=True)
        (rt / "python" / "bin" / "python3").write_text("")
        venv = self.root / "var" / "venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text(f"home = {rt}/python/bin\nexecutable = {rt}/python/bin/python3.14\n")

    def test_zold_python_es_tiszta_kornyezet(self):
        r = futtat(self.root, self.home)
        self.assertEqual(r["python"].allapot, doctor.OK, r["python"].uzenet)
        self.assertEqual(r["~/Applications, ~/.cache"].allapot, doctor.OK)
        self.assertEqual(r["legacy var/"].allapot, doctor.OK)
        self.assertEqual(r["offline"].allapot, doctor.OK)

    def test_rendszer_python_piros(self):
        r = futtat(self.root, self.home, python=Path("/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"))
        self.assertEqual(r["python"].allapot, doctor.HIBA)

    def test_venv_rendszer_pythonra_mutat(self):
        (self.root / "var" / "venv" / "pyvenv.cfg").write_text(
            "home = /Library/Frameworks/Python.framework/Versions/3.14/bin\n")
        self.assertEqual(futtat(self.root, self.home)["python"].allapot, doctor.HIBA)

    def test_cache_az_envben_piros(self):
        r = futtat(self.root, self.home, env={"UV_CACHE_DIR": str(self.home / ".cache" / "uv")})
        self.assertEqual(r["~/Applications, ~/.cache"].allapot, doctor.HIBA)

    def test_sajat_fajl_home_applicationsre_hivatkozik(self):
        (self.root / "config" / "x.toml").write_text('cel = "~/Applications/Manifold.app"\n')
        self.assertEqual(futtat(self.root, self.home)["~/Applications, ~/.cache"].allapot, doctor.HIBA)

    def test_megjegyzes_nem_szamit(self):
        (self.root / "config" / "x.toml").write_text('# soha nem ~/.cache\nk = 1  # sem ~/Applications\n')
        self.assertEqual(futtat(self.root, self.home)["~/Applications, ~/.cache"].allapot, doctor.OK)

    def test_rejtett_mappa_es_a_claude_munkafak_kimaradnak(self):
        """A gyökér alatti rejtett mappa (`.claude/worktrees/…`) nem saját forrás: a doctor nem járja be, és a bennük álló
        legacy-utas fájl nem ad hamis „legacy var/” hibát."""
        for rejtett in (".claude/worktrees/x/config", ".rejtett"):
            mappa = self.root / rejtett
            mappa.mkdir(parents=True)
            (mappa / "y.toml").write_text('ut = "/Volumes/Work/Manifold-OS legacy/Legacy/var"\n~/Applications\n')
        r = futtat(self.root, self.home)
        self.assertEqual(r["legacy var/"].allapot, doctor.OK, r["legacy var/"].uzenet)
        self.assertEqual(r["~/Applications, ~/.cache"].allapot, doctor.OK)
        self.assertEqual([p for p in doctor._sajat_fajlok(self.root) if {".claude", ".rejtett"} & set(p.relative_to(self.root).parts)], [])
        (self.root / "config" / "z.toml").write_text('ut = "/Volumes/Work/Manifold-OS legacy/Legacy/var"\n')
        self.assertEqual(futtat(self.root, self.home)["legacy var/"].allapot, doctor.HIBA)

    def test_legacy_git_config_piros(self):
        g = self.root / "var" / "ytdlp.git"
        g.mkdir()
        (g / "config").write_text("[core]\n\tworktree = /Volumes/Work/Manifold-OS legacy/Legacy/modulok/ytdlp\n")
        self.assertEqual(futtat(self.root, self.home)["legacy var/"].allapot, doctor.HIBA)

    def test_regi_worktree_piros(self):
        g = self.root / "var" / "allapot.git"
        g.mkdir()
        (g / "config").write_text("[core]\n\tworktree = /Volumes/Work/Manifold-OS/var/state\n")
        self.assertEqual(futtat(self.root, self.home)["legacy var/"].allapot, doctor.HIBA)

    def test_legacy_symlink_piros(self):
        os.symlink("/Volumes/Work/Manifold-OS legacy/Legacy/var/models", self.root / "var" / "models")
        self.assertEqual(futtat(self.root, self.home)["legacy var/"].allapot, doctor.HIBA)

    def test_legacy_env_piros(self):
        r = futtat(self.root, self.home, env={"MOS_VAR": "/Volumes/Work/Manifold-OS legacy/Legacy/var"})
        self.assertEqual(r["legacy var/"].allapot, doctor.HIBA)

    def test_vault_sema_zold_a_sajat_masolattal(self):
        """T162 (2. audit, C11b): a `[sema] vault` a 2.0 saját `config/vault-sema.json`-jára mutat, és betölthető."""
        r = futtat(self.root, self.home)["vault-séma"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)

    def test_vault_sema_a_legacyre_mutat_piros(self):
        """T162: a legacy kalibrációjára mutató `[sema] vault` HIBA (a 2.0 nem olvashat a legacyből)."""
        toml = self.root / "config" / "os.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace(
            'vault = "{os}/config/vault-sema.json"',
            'vault = "/Volumes/Work/Manifold-OS legacy/Legacy/config/vault-sema.json"'), encoding="utf-8")
        r = futtat(self.root, self.home)["vault-séma"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("legacy", r.uzenet)

    def test_vault_sema_hianyzo_vagy_hibas_fajl_piros(self):
        sema = self.root / "config" / "vault-sema.json"
        sema.write_text("{nem json", encoding="utf-8")
        self.assertEqual(futtat(self.root, self.home)["vault-séma"].allapot, doctor.HIBA)
        sema.write_text('{"tags_ertekkeszlet": []}', encoding="utf-8")
        self.assertEqual(futtat(self.root, self.home)["vault-séma"].allapot, doctor.HIBA)
        sema.unlink()
        self.assertEqual(futtat(self.root, self.home)["vault-séma"].allapot, doctor.HIBA)

    def test_var_symlink_az_oson_kivulre_piros(self):
        """T002 (2. audit): a symlinkelt `var/`-ú munkafa core-ja a valódi állapotot használná."""
        self.assertEqual(futtat(self.root, self.home)["var symlink"].allapot, doctor.OK)
        kulso = Path(self._t.name) / "valodi-var"
        shutil.move(self.root / "var", kulso)
        os.symlink(kulso, self.root / "var")
        r = futtat(self.root, self.home)["var symlink"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn(str(kulso), r.uzenet)

    def test_var_symlink_a_gyokeren_belul_rendben(self):
        belso = self.root / "var-valodi"
        shutil.move(self.root / "var", belso)
        os.symlink(belso, self.root / "var")
        self.assertEqual(futtat(self.root, self.home)["var symlink"].allapot, doctor.OK)

    def test_munkafa_modban_a_hianyzo_venv_info(self):
        """T002: a munkafának nincs saját venv-je (az eszköztár a fő checkoutból jön): nem hamis HIBA, hanem INFO;
        munkafa-mód nélkül a hiányzó venv továbbra is HIBA."""
        shutil.rmtree(self.root / "var" / "venv")
        self.assertEqual(futtat(self.root, self.home)["python"].allapot, doctor.HIBA)
        self.assertEqual(futtat(self.root, self.home)["runtime"].allapot, doctor.HIBA)
        r = futtat(self.root, self.home, env={"MOS_MUNKAFA": "1"})
        self.assertEqual(r["python"].allapot, doctor.INFO)
        self.assertEqual(r["runtime"].allapot, doctor.INFO)             # a munkafában nincs runtime: a fő checkoutból jön
        self.assertEqual(r["lock"].allapot, doctor.INFO)
        self.assertEqual(r["var symlink"].allapot, doctor.OK)

    def test_munkafa_modban_a_sajat_rossz_venv_tovabbra_is_hiba(self):
        (self.root / "var" / "venv" / "pyvenv.cfg").write_text(
            "home = /Library/Frameworks/Python.framework/Versions/3.14/bin\n")
        (self.root / "var" / "venv" / "bin" / "python").write_text("")
        self.assertEqual(futtat(self.root, self.home, env={"MOS_MUNKAFA": "1"})["python"].allapot, doctor.HIBA)

    def _klon(self, nev: str, pid: int, kor_ora: float, megtart: bool = False) -> Path:
        d = self.root / "var" / "tmp" / nev
        d.mkdir(parents=True)
        (d / ".mos-proba.json").write_text(json.dumps({
            "szkript": "proba_app.py", "pid": pid, "megtart": megtart,
            "letrehozva": (datetime.now() - timedelta(hours=kor_ora)).strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
        return d

    def _halott_pid(self) -> int:
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def test_proba_klonok_nincs_megmaradt(self):
        self.assertEqual(futtat(self.root, self.home)["próbaklónok"].allapot, doctor.OK)
        self._klon("c08-proba-elo", os.getpid(), 0.1)                      # fut a szkriptje, nem megtartott: rendben
        self.assertEqual(futtat(self.root, self.home)["próbaklónok"].allapot, doctor.OK)

    def test_proba_klonok_arva_es_megtartott_figyelmeztet_a_doctor_nem_torol(self):
        """T081 (2. audit): a félbehagyott vagy `--megtart` próbaklónok (egy-egy APFS-klón a vaultról) gazdátlanul
        hevertek; a doctor jelzi a nevüket és a korukat, és NEM töröl (a törlést csak a felhasználó igenjére)."""
        arva = self._klon("c14-canvas-20261001-100000", self._halott_pid(), 30)
        megtartott = self._klon("c08-proba-20261002-090000", os.getpid(), 5, megtart=True)
        r = futtat(self.root, self.home)["próbaklónok"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("c14-canvas-20261001-100000", r.uzenet)
        self.assertIn("árva", r.uzenet)
        self.assertIn("c08-proba-20261002-090000", r.uzenet)
        self.assertIn("megtartott", r.uzenet)
        self.assertRegex(r.uzenet, r"1 napos|30 órás|1 d")
        self.assertIn("a törlésről a felhasználó dönt", r.uzenet)
        self.assertTrue(arva.is_dir() and megtartott.is_dir(), "a doctor nem töröl")

    def test_proba_klonok_a_jelolo_elotti_regi_klon_is_latszik(self):
        d = self.root / "var" / "tmp" / "c08-proba-20261002-143000"
        (d / "vault.git").mkdir(parents=True)
        r = futtat(self.root, self.home)["próbaklónok"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("c08-proba-20261002-143000", r.uzenet)
        self.assertIn("jelölő nélküli régi klón", r.uzenet)
        self.assertTrue(d.is_dir())

    def test_proba_klonok_jelolo_nelkuli_mappa_nem_szamit(self):
        (self.root / "var" / "tmp" / "valami-mas").mkdir(parents=True)
        self.assertEqual(futtat(self.root, self.home)["próbaklónok"].allapot, doctor.OK)

    def test_gepi_proba_klonok_latszanak_meretukkel(self):
        """B-javító 8: a gépi írás D9-próbaklónjai (`{tmp}/proba/<kör>/`) eddig láthatatlanok voltak; a jelölt (élő core-é
        is) INFO-sorban, névvel, korral és mérettel, a jelölő nélküli régi gépi klón a figyelmeztetésben."""
        from core import frame
        d = self.root / "var" / "tmp" / "proba" / "KARTYA-20261001-100000-abc123-proba"
        (d / "vault.git").mkdir(parents=True)
        (d / "Manifold").mkdir()
        (d / "Manifold" / "nagy.bin").write_bytes(b"\0" * 3_000_000)
        frame.proba_jelol(d, "KARTYA-20261001-100000-abc123-proba")
        r = futtat(self.root, self.home)
        self.assertEqual(r["próbaklónok"].allapot, doctor.OK)
        g = r["próbaklónok (gépi)"]
        self.assertEqual(g.allapot, doctor.INFO)
        self.assertIn("KARTYA-20261001-100000-abc123-proba", g.uzenet)
        self.assertIn("3 MB", g.uzenet)
        self.assertIn("proba_klon_max_nap", g.uzenet)
        regi = self.root / "var" / "tmp" / "proba" / "OSSZ-20260901-100000-proba"
        (regi / "vault.git").mkdir(parents=True)
        r = futtat(self.root, self.home)["próbaklónok"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("proba/OSSZ-20260901-100000-proba", r.uzenet)
        self.assertIn("jelölő nélküli gépi próbaklón", r.uzenet)
        self.assertTrue(d.is_dir() and regi.is_dir(), "a doctor nem töröl")

    def test_index_utvonal_kulonleges_karakterrel(self):
        """B-javító 9 (T108 mintája): a `#`/`?` az index útjában nem törheti a csak olvasó URI-t."""
        import sqlite3
        idx = Path(self._t.name) / "index #1?x"
        idx.mkdir()
        c = sqlite3.connect(idx / "vault.sqlite")
        c.execute("PRAGMA user_version = 1")
        c.execute("CREATE TABLE fajl (ut TEXT, torolve TEXT)")
        c.commit()
        c.close()
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_INDEX": str(idx)})
        r = {x.nev: x for x in doctor.ellenoriz(cfg, {"HF_HUB_OFFLINE": "1"}, self.home,
                                                 self.root / "runtime" / "python" / "bin" / "python3")}["index"]
        self.assertNotIn("nem olvasható", r.uzenet)

    def test_regi_app_csak_figyelmeztet(self):
        (self.home / "Applications" / "Manifold.app").mkdir()
        r = futtat(self.root, self.home)
        self.assertEqual(r["régi appok"].allapot, doctor.FIGYELEM)
        self.assertEqual(r["~/Applications, ~/.cache"].allapot, doctor.OK)

    def test_git_hianya_piros(self):
        """K1/M10: a rendszer gitje rejtett függőség — a doctor jelzi, ha nincs."""
        self.assertEqual(futtat(self.root, self.home)["git"].allapot, doctor.OK)
        self.assertEqual(futtat(self.root, self.home, env={"PATH": "/nincs-ilyen"})["git"].allapot, doctor.HIBA)

    # ---------------------------------------------------------------- vault és pillanatkép-tároló (C29.6, T105, T024)

    def _cfg(self):
        return config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home)})

    def _vault(self, obsidian: bool = True) -> Path:
        v = self.root.parent / "Manifold"
        if obsidian:
            (v / ".obsidian").mkdir(exist_ok=True)
        return v

    def test_nincs_vault_hiba(self):
        """T105: a doctor eddig semmit nem jelzett, ha a beállított vault nem létezik (az SSD nincs csatlakoztatva)."""
        shutil.rmtree(self.root.parent / "Manifold")
        r = futtat(self.root, self.home)["vault"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("nincs vault", r.uzenet)
        self.assertIn(str(self.root.parent / "Manifold"), r.uzenet)
        self.assertIn("csatlakoztatva az SSD", r.uzenet)

    def test_nincs_vault_munkafa_modban_info(self):
        shutil.rmtree(self.root.parent / "Manifold")
        r = futtat(self.root, self.home, env={"MOS_MUNKAFA": "1"})["vault"]
        self.assertEqual(r.allapot, doctor.INFO)
        self.assertIn("munkafa", r.uzenet)

    def test_vault_rendben_az_utat_es_a_jegyzetszamot_adja(self):
        v = self._vault()
        (v / "A").mkdir()
        (v / "A" / "egy.md").write_text("# 1\n", encoding="utf-8")
        (v / "ketto.md").write_text("# 2\n", encoding="utf-8")
        (v / ".trash").mkdir()
        (v / ".trash" / "kidobott.md").write_text("# x\n", encoding="utf-8")
        (v / "kep.png").write_bytes(b"x")
        r = futtat(self.root, self.home)["vault"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)
        self.assertIn(str(v), r.uzenet)
        self.assertIn("2 jegyzet", r.uzenet)

    def test_vault_obsidian_nelkul_figyelem(self):
        r = futtat(self.root, self.home)["vault"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn(".obsidian", r.uzenet)

    def _tar(self):
        self._vault()
        repo = snapshot.repos(self._cfg())["vault"]
        repo.init()
        return repo

    def test_elo_vault_mellett_hianyzo_pillanatkep_tarolo_hiba(self):
        """T024: ha a vault elérhető, de a `vault.git` elveszett, nincs visszavonás, előzmény és bundle — erről semmi nem szólt."""
        self._vault()
        r = futtat(self.root, self.home)["pillanatkép (vault)"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("vault.git", r.uzenet)
        self.assertIn("visszavonás", r.uzenet)

    def test_ep_pillanatkep_tarolo_rendben(self):
        self._tar()
        self.assertEqual(futtat(self.root, self.home)["pillanatkép (vault)"].allapot, doctor.OK)

    def test_eltero_core_worktree_hiba(self):
        repo = self._tar()
        repo.git("config", "core.worktree", "/Volumes/Mas/Manifold")
        r = futtat(self.root, self.home)["pillanatkép (vault)"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("core.worktree", r.uzenet)

    def test_eltero_info_exclude_hiba(self):
        """A `kizar` lista az `info/exclude`-ba generálódik; ha eltér, a kizárt (média, tmp) fájlok bekerülhetnek a
        pillanatképbe."""
        repo = self._tar()
        (repo.git_dir / "info" / "exclude").write_text("# kézzel szerkesztve\n", encoding="utf-8")
        r = futtat(self.root, self.home)["pillanatkép (vault)"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("info/exclude", r.uzenet)

    def test_eltero_info_attributes_es_hooks_hiba(self):
        """T099: a zárt git-környezet (info/attributes, core.hooksPath) hiánya HIBA; a core indulása beírja."""
        repo = self._tar()
        self.assertEqual(futtat(self.root, self.home)["pillanatkép (vault)"].allapot, doctor.OK)
        (repo.git_dir / "info" / "attributes").unlink()
        r = futtat(self.root, self.home)["pillanatkép (vault)"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("info/attributes", r.uzenet)
        repo.biztosit_kornyezet()
        repo.git("config", "--unset", "core.hooksPath")
        r = futtat(self.root, self.home)["pillanatkép (vault)"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("hooksPath", r.uzenet)

    def test_vault_gitattributes_figyelmeztet(self):
        v = self._vault()
        self.assertNotIn("vault .gitattributes", futtat(self.root, self.home))
        (v / ".gitattributes").write_text("*.md filter=lfs\n", encoding="utf-8")
        r = futtat(self.root, self.home)["vault .gitattributes"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)

    def test_nem_vault_tarolo_munkafa_nelkul_nem_hiba(self):
        """A ytdlp munkafája a C20-ig hiányzik: tároló híján sem hiba."""
        self._tar()
        r = futtat(self.root, self.home)
        self.assertNotIn("pillanatkép (ytdlp)", r)

    def test_osszeomlas_horog_eles_kornyezetben_hiba(self):
        self.assertNotIn("összeomlás-horog", futtat(self.root, self.home))
        r = futtat(self.root, self.home, env={"MOS_OSSZEOMLAS": "gepi.naplo_kesz"})["összeomlás-horog"]
        self.assertEqual(r.allapot, doctor.HIBA)

    def test_futo_core_info(self):
        """T027: a doctor megmutatja, ha a `core.lock` foglalt (a core fut) — a zárat nem veszi el, fájlt nem hoz létre."""
        import fcntl
        self.assertNotIn("core", futtat(self.root, self.home))
        zar = self.root / "var" / "run" / "core.lock"
        zar.parent.mkdir(parents=True)
        with open(zar, "a+") as fh:
            fh.write("pid 4242 · /x/Manifold")
            fh.flush()
            fcntl.flock(fh, fcntl.LOCK_EX)
            r = futtat(self.root, self.home)["core"]
            self.assertEqual(r.allapot, doctor.INFO)
            self.assertIn("4242", r.uzenet)
        self.assertNotIn("core", futtat(self.root, self.home))            # szabad zár: nincs futó core

    def test_offline_hiany(self):
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home)})
        r = {x.nev: x for x in doctor.ellenoriz(cfg, {}, self.home, self.root / "runtime" / "python" / "bin" / "python3")}
        self.assertEqual(r["offline"].allapot, doctor.HIBA)


def _hamis_cpp(root: Path, *, formaz=True, lld=True, sdk_verzio="27.0") -> None:
    bin_ = root / "runtime" / "llvm" / "bin"
    bin_.mkdir(parents=True, exist_ok=True)
    for nev, kell in (("clang++", True), ("clang-format", formaz), ("clangd", True), ("ld64.lld", lld)):
        if kell:
            (bin_ / nev).write_text("#!/bin/sh\nexit 0\n")
            (bin_ / nev).chmod(0o755)
    sdk = root / "runtime" / "sdk"
    (sdk / "usr" / "include").mkdir(parents=True, exist_ok=True)
    (sdk / "SDKSettings.json").write_text(json.dumps({"Version": sdk_verzio}))


class CppDoctorTeszt(unittest.TestCase):
    """C36a: a C++ eszköztár sorai (`C++ eszköztár`, `C++ SDK`, `C++ linker`)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()
        self.home = Path(self._t.name) / "home"
        (self.home / "Applications").mkdir(parents=True)
        rt = self.root / "runtime"
        (rt / "python" / "bin").mkdir(parents=True)
        (rt / "python" / "bin" / "python3").write_text("")
        venv = self.root / "var" / "venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text(f"home = {rt}/python/bin\nexecutable = {rt}/python/bin/python3.14\n")

    def futtat(self, macos="27.0", env=None):
        with mock.patch.object(doctor, "macos_verzio", return_value=macos):
            return futtat(self.root, self.home, env=env)

    def test_nincs_eszkoztar_figyelem_a_telepito_parancsot_mondja(self):
        r = self.futtat()["C++ eszköztár"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("bin/mos cpp telepit", r.uzenet)

    def test_munkafa_modban_az_eszkoztar_hianya_info(self):
        shutil.rmtree(self.root / "var" / "venv")
        r = self.futtat(env={"MOS_MUNKAFA": "1"})["C++ eszköztár"]
        self.assertEqual(r.allapot, doctor.INFO)
        self.assertIn("fő checkout", r.uzenet)

    def test_teljes_eszkoztar_rendben(self):
        _hamis_cpp(self.root)
        r = self.futtat()
        self.assertEqual(r["C++ eszköztár"].allapot, doctor.OK, r["C++ eszköztár"].uzenet)
        self.assertEqual(r["C++ SDK"].allapot, doctor.OK, r["C++ SDK"].uzenet)
        self.assertEqual(r["C++ linker"].allapot, doctor.OK, r["C++ linker"].uzenet)

    def test_regebbi_sdk_figyelem_mindket_verziot_megnevezi(self):
        _hamis_cpp(self.root, sdk_verzio="26.5")
        r = self.futtat(macos="27.0")["C++ SDK"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("26.5", r.uzenet)
        self.assertIn("27.0", r.uzenet)
        self.assertIn("--sdk", r.uzenet)

    def test_az_azonos_vagy_ujabb_sdk_rendben(self):
        _hamis_cpp(self.root, sdk_verzio="27.1")
        self.assertEqual(self.futtat(macos="27.0")["C++ SDK"].allapot, doctor.OK)

    def test_hianyzo_sdk_figyelem(self):
        _hamis_cpp(self.root)
        shutil.rmtree(self.root / "runtime" / "sdk")
        r = self.futtat()["C++ SDK"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("--sdk", r.uzenet)

    def test_hianyzo_clang_format_figyelem_a_hianyzot_nevezi(self):
        _hamis_cpp(self.root, formaz=False)
        r = self.futtat()["C++ eszköztár"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("clang-format", r.uzenet)

    def test_lld_hianya_figyelem_tartalek_linker_nincs(self):
        """K168: a rendszer linkere a fordító-profil alatt nem futhat, az `ld64.lld` hiánya ezért nem INFO a tartalékra esve."""
        _hamis_cpp(self.root, lld=False)
        r = self.futtat()["C++ linker"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("nem tud linkelni", r.uzenet)
        self.assertIn("cpp telepit", r.uzenet)

    def test_a_regi_rendszer_linker_beallitas_figyelmeztet(self):
        _hamis_cpp(self.root)
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home)})
        cfg.data.setdefault("cpp", {})["linker"] = "rendszer"
        with mock.patch.object(doctor, "macos_verzio", return_value="27.0"):
            r = {x.nev: x for x in doctor.ellenoriz(cfg, {"HF_HUB_OFFLINE": "1"}, self.home,
                                                    self.root / "runtime" / "python" / "bin" / "python3")}
        self.assertEqual(r["C++ linker"].allapot, doctor.FIGYELEM)
        self.assertIn("rendszer", r["C++ linker"].uzenet)
        self.assertIn("K168", r["C++ linker"].uzenet)

    def test_a_doctor_nem_hasznalja_a_rendszer_fordítóját(self):
        """A doctor a `runtime/llvm`-et nézi, a PATH-on talált fordítót nem (és programot csak az LLVM-ből futtat)."""
        _hamis_cpp(self.root)
        with mock.patch("shutil.which", side_effect=lambda n, *a, **k: "/usr/bin/" + n if n.startswith("clang") else None):
            self.assertEqual(self.futtat()["C++ eszköztár"].allapot, doctor.OK)

    def test_a_macos_verzio_lekerdezes_hibaja_nem_riaszt(self):
        _hamis_cpp(self.root, sdk_verzio="26.5")
        self.assertEqual(self.futtat(macos=None)["C++ SDK"].allapot, doctor.OK)


def _hamis_eszkoz(ut: Path, kimenet: str) -> None:
    ut.parent.mkdir(parents=True, exist_ok=True)
    ut.write_text(f"#!/bin/sh\necho '{kimenet}'\n", encoding="utf-8")
    ut.chmod(0o755)


PINEK = ("UV_VERSION=0.12.21\nPY_VERSION=3.14.7\nNODE_VERSION=24.21.0\n"
         "FFMPEG_BIN_SHA256=" + "0" * 64 + "\n")


class KiadasDoctorTeszt(unittest.TestCase):
    """C34 (2. audit T187–T190 + a hordozhatósági tételek): a doctor új tételei."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name)
        self.home = Path(self._t.name) / "home"
        (self.home / "Applications").mkdir(parents=True)
        (self.root / "config" / "runtime-pins.env").write_text(PINEK, encoding="utf-8")

    def r(self, **kw) -> dict:
        return futtat(self.root, self.home, **kw)

    # --- T187: @napi-rs/canvas
    def test_napi_canvas_nincs_node_modules_info(self):
        self.assertEqual(self.r()["@napi-rs/canvas"].allapot, doctor.INFO)

    def test_napi_canvas_hianya_rendben(self):
        (self.root / "app" / "node_modules" / "@napi-rs").mkdir(parents=True)
        (self.root / "app" / "node_modules" / "@napi-rs" / "wasm-runtime").mkdir()      # más @napi-rs csomag: nem érintett
        self.assertEqual(self.r()["@napi-rs/canvas"].allapot, doctor.OK)

    def test_napi_canvas_megleve_hiba(self):
        for n in ("canvas", "canvas-darwin-arm64"):
            (self.root / "app" / "node_modules" / "@napi-rs" / n).mkdir(parents=True)
        r = self.r()["@napi-rs/canvas"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("@napi-rs/canvas-darwin-arm64", r.uzenet)
        self.assertIn("29", r.uzenet)

    # --- T188: a runtime verziói a pinhez
    def _runtime(self, uv="uv 0.12.21 (abc 2026-09-29 aarch64-apple-darwin)", py="Python 3.14.7", node="v24.21.0"):
        rt = self.root / "runtime"
        _hamis_eszkoz(rt / "uv", uv)
        _hamis_eszkoz(rt / "python" / "bin" / "python3", py)
        _hamis_eszkoz(rt / "node" / "bin" / "node", node)

    def test_runtime_verzio_egyezik(self):
        self._runtime()
        r = self.r()["runtime verzió"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)
        self.assertIn("Python 3.14.7", r.uzenet)

    def test_runtime_verzio_eltero_hiba_megnevezi_az_eszkozt_es_a_parancsot(self):
        self._runtime(py="Python 3.14.6", node="v24.20.0")
        r = self.r()["runtime verzió"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("Python 3.14.6 ≠ pin 3.14.7", r.uzenet)
        self.assertIn("Node 24.20.0 ≠ pin 24.21.0", r.uzenet)
        self.assertNotIn("uv 0", r.uzenet.split("—")[0])
        self.assertIn("runtime fetch", r.uzenet)

    def test_runtime_verzio_a_pontos_szamcsoportot_hasonlitja(self):
        self._runtime(py="Python 3.14.70")
        self.assertEqual(self.r()["runtime verzió"].allapot, doctor.HIBA)

    def test_runtime_verzio_nem_olvashato_hiba(self):
        self._runtime(node="semmi verziószám")
        r = self.r()["runtime verzió"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("nem olvasható", r.uzenet)

    # --- T188: requirements.in a config/ alatt
    def test_requirements_in_hianya_hiba(self):
        r = self.r()["requirements.in"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("config/requirements.in", r.uzenet)

    def test_requirements_in_a_lockhoz_kepest(self):
        (self.root / "config" / "requirements.lock").write_text(
            "numpy==2.5.3 \\\n    --hash=sha256:aa\nPyYAML==6.0.3 \\\n    --hash=sha256:bb\nyt-dlp==1\n", encoding="utf-8")
        ki = self.root / "config" / "requirements.in"
        ki.write_text("# megjegyzés\nnumpy==2.5.3\npyyaml==6.0.3   # kisbetű is jó\nyt_dlp==1\n\n", encoding="utf-8")
        r = self.r()["requirements.in"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)
        ki.write_text(ki.read_text(encoding="utf-8") + "fsrs==6.3.2\n", encoding="utf-8")
        r = self.r()["requirements.in"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("fsrs", r.uzenet)

    def test_a_repo_requirements_in_a_lockkal_konzisztens(self):
        """A valódi `config/requirements.in` minden csomagja a valódi lockban áll."""
        cfg = config.load({"MOS_ROOT": str(REPO)})
        out = []
        doctor._kovetelmenyek(cfg, lambda a, n, u: out.append((a, u)))
        self.assertEqual(out[0][0], doctor.OK, out)

    # --- T190: Spotlight-kizárás
    def test_never_index_hianya_figyelem_megleve_rendben(self):
        (self.root / "var" / ".metadata_never_index").unlink(missing_ok=True)
        self.assertEqual(self.r()["Spotlight"].allapot, doctor.FIGYELEM)
        (self.root / "var" / ".metadata_never_index").write_text("")
        self.assertEqual(self.r()["Spotlight"].allapot, doctor.OK)

    # --- T189: a home alá írt Preferences plist megengedett kivétel
    def test_preferences_plist_megengedett_kivetel_info(self):
        pref = self.home / "Library" / "Preferences"
        pref.mkdir(parents=True)
        (pref / "local.manifold-os.app.plist").write_bytes(b"bplist00")
        r = self.r()["home írások"]
        self.assertEqual(r.allapot, doctor.INFO)
        self.assertIn("megengedett kivétel", r.uzenet)
        self.assertIn("Preferences", r.uzenet)

    def test_nem_engedett_home_iras_figyelmeztet(self):
        mentett = self.home / "Library" / "Saved Application State" / "local.manifold-os.app.savedState"
        mentett.mkdir(parents=True)
        web = self.home / "Library" / "WebKit" / "local.manifold-os.app"
        web.mkdir(parents=True)
        (self.home / "Library" / "Caches" / "mas.app").mkdir(parents=True)             # idegen app: nem a miénk
        r = self.r()["home írások"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("Saved Application State/local.manifold-os.app.savedState", r.uzenet)
        self.assertIn("WebKit/local.manifold-os.app", r.uzenet)
        self.assertNotIn("mas.app", r.uzenet)

    def test_tiszta_home_nincs_tetel(self):
        self.assertNotIn("home írások", self.r())

    # --- az aláírás fajtája
    def test_alairas_tipus(self):
        adhoc = "Executable=/x/Manifold\nIdentifier=local.manifold-os.app\nSignature=adhoc\nTeamIdentifier=not set\n"
        stabil = "Executable=/x/Manifold\nAuthority=Manifold Helyi Alairas\nSignature size=1520\nTeamIdentifier=not set\n"
        self.assertEqual(doctor.alairas_tipus(adhoc), ("adhoc", ""))
        self.assertEqual(doctor.alairas_tipus(stabil), ("identitas", "Manifold Helyi Alairas"))
        self.assertEqual(doctor.alairas_tipus("code object is not signed at all"), ("ismeretlen", ""))

    # --- a rendszer-gittől való függés kimondva
    def test_fuggoseg_a_rendszer_gitjetol_info(self):
        r = self.r()["git függőség"]
        self.assertEqual(r.allapot, doctor.INFO)
        self.assertIn("rendszer-git", r.uzenet)
        self.assertIn("docs/KIADAS.md", r.uzenet)

    def test_fuggoseg_hordozhato_git_rendben(self):
        van = shutil.which("git")
        if not van:
            self.skipTest("nincs git")
        hordozhato = self.root / "runtime" / "git" / "bin" / "git"
        hordozhato.parent.mkdir(parents=True)
        hordozhato.write_text(f"#!/bin/sh\nexec '{van}' \"$@\"\n", encoding="utf-8")
        hordozhato.chmod(0o755)
        r = self.r(env={"PATH": str(hordozhato.parent) + os.pathsep + "/usr/bin" + os.pathsep + "/bin"})["git függőség"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)


if __name__ == "__main__":
    unittest.main()
