"""A kézi szkriptek közös elkülönítő segédje (`tests/kezi/_kornyezet.py`) és az AST-őr (T011, T010, 2. audit).

Az 1. audit óta minden új kézi szkript maga állított össze egy `MOS_*` környezetet, és mindegyik kihagyott valamit
(`MOS_STATE`, `MOS_SZEMELYES`, `MOS_BACKUP`, a ytdlp, a naptár-segéd, a modellzár): a klónos próba így a valódi
`~/Manifold-backup` bundle-jait forgathatta, a valódi `pos.sqlite`-ot írhatta, és külön modellzárat tartott. Itt:
a segéd futásidejű tulajdonságai, és egy AST-őr, amely bukik, ha egy core-t vagy appot indító szkript a segéd nélkül
állítja össze a környezetét. A szkripteket csak `ast.parse`-olja, nem importálja és nem futtatja."""
import ast
import fcntl
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from core import config, frame, snapshot
from core.modell import beallitas as B
from tests.helpers import REPO, alg_core, alg_gyoker, env as tiszta_env, tmpdir

KEZI = REPO / "tests" / "kezi"
sys.path.insert(0, str(KEZI))
import _kornyezet as K  # noqa: E402

# Minden kézi szkript pontosan egy osztályba tartozik; új szkript besorolás nélkül nem maradhat.
INDITO = {  # core-t (bin/mos core start) vagy a Manifold.app-ot indítja: subprocess.Popen
    "apfs_proba.py", "atnevezes_proba.py", "canvas_proba.py", "szerkeszto_mentes.py", "sema_proba.py",
    "proba_app.py", "memoria_meres.py", "graf_nyugalmi_cpu.py", "kviz_proba.py", "atallas_riport.py",
    "fuzet_proba.py",       # C21: a füzetlánc próbaköre (core a klónon, a lánc kifejezett modellekkel, próbában)
    "soak.py",              # C33 (T206): a soak-készlet (saját core álvaulton, terhelés, leállás-próbák)
}
INPROC = {  # folyamaton belül indít core-t vagy indexet (server.start, indexelo.Index) saját configgal
    "index_meres.py", "bazis_meres.py", "bazis_paritas.py", "graf_nezet_paritas.py", "graf_paritas.py",
    "link_feloldas_paritas.py", "mentes_proba.py", "video_proba.py", "video_integralas_proba.py",
    "nagy_vault_meres.py",  # C33 (1. pont): 10 000 jegyzetes szintetikus vault, folyamaton belüli index
    "kiadas_mentes.py",     # C34: a belső lemezes mentés visszaállítása a próbamappába (csak olvas a valódi mentésből)
}
OLVASO = {"kepletek.py", "link_lezer_paritas.py", "notion_obsidian.py", "obsidian_link_proba.py", "kor2_olvaso.py",
          "link_dekodolas_meres.py", "emlites_meres.py", "hasonlosag_meres.py"}   # csak olvas (C30b: az index és a vektortár ideiglenes másolatán)
GENERATOR = {"bazis_proba.py", "k42_proba.py", "atallas_probavault.py"}      # próbavaultot generál, core-t nem indít
KLIENS = {"gepi_iras_proba.py"}     # kapott URL-re ír, és megtagadja a nem próba-klónt
FUTTATO = {"kapu.py",               # C33 (T069): a klónos próbákat futtatja sorban (azok maguk különítenek el)
           "lefedettseg.py"}        # C33 (T185): a tesztkészletet futtatja (a tesztek maguk különítenek el)


def _szkriptek() -> list[Path]:
    return sorted(p for p in KEZI.glob("*.py") if p.name != "_kornyezet.py")


def _utak_kulcsai() -> set[str]:
    # F3-DESIGN §2.4: a `vault` nincs az `os.toml [utak]`-ban, de a kézi szkript akkor sem írhat kézzel `MOS_VAULT`-ot
    return set(config.utak_kulcsok(config.load({"MOS_ROOT": str(REPO)}).data))


class MunkafaEsLegacy(unittest.TestCase):
    """A fejlesztői kézi kapuk (F2): a munkafa-mód a fő checkout SAJÁT konfigjából veszi a vaultot (nincs beégetett mappanév), és a
    régi telepítés referenciája kizárólag a `MOS_LEGACY`-ból jön (nincs alapértelmezett hely)."""

    def test_munkafa_forras_a_fo_checkout_konfigjabol_veszi_a_vaultot(self):
        with tmpdir() as t:
            fo = alg_gyoker(t)                                           # a „fő checkout”
            munkafa = Path(t) / "munkafa"
            munkafa.mkdir()
            (munkafa / ".git").write_text(f"gitdir: {fo}/.git/worktrees/x\n")
            kimenet = mock.Mock(returncode=0, stdout=f"{fo}/.git\n")
            with mock.patch.object(K, "REPO", munkafa), mock.patch.object(K.subprocess, "run", return_value=kimenet):
                ki = K.munkafa_forras({"A": "b"})
            vault = config.load({"MOS_ROOT": str(fo)}).path("vault")
            self.assertEqual(ki["MOS_VAULT"], str(vault))
            self.assertEqual(ki["MOS_VAULT_GIT"], str(fo / "var" / "vault.git"))
            self.assertEqual(ki["A"], "b")
            self.assertNotIn("MOS_LEGACY", ki)                           # a régi telepítést sosem találgatja
            with mock.patch.object(K, "REPO", munkafa), mock.patch.object(K.subprocess, "run", return_value=kimenet):
                self.assertEqual(K.munkafa_forras({"MOS_VAULT": "/mas"})["MOS_VAULT"], "/mas")   # a hívó kulcsa marad

    def test_a_legacy_referencia_csak_a_mos_legacy_bol_jon(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MOS_LEGACY", None)
            self.assertIsNone(K.legacy_eszkozok())
        with tmpdir() as t:
            esz = Path(t) / "modulok" / "eszkozok"
            esz.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"MOS_LEGACY": t}):
                self.assertIsNone(K.legacy_eszkozok())                   # nincs benne mfd.py
                (esz / "mfd.py").write_text("")
                self.assertEqual(K.legacy_eszkozok(), esz)


class AstOr(unittest.TestCase):
    def test_minden_szkript_besorolt(self):
        mind = INDITO | INPROC | OLVASO | GENERATOR | KLIENS | FUTTATO
        van = {p.name for p in _szkriptek()}
        self.assertEqual(van - mind, set(), "besorolatlan kézi szkript: vegyük fel az osztályok egyikébe, és ha core-t "
                                            "indít, használja a _kornyezet.elkulonit-ot")
        self.assertEqual(mind - van, set(), "a besorolásban szereplő szkript nincs meg")
        self.assertEqual(len(mind), len(INDITO) + len(INPROC) + len(OLVASO) + len(GENERATOR) + len(KLIENS) + len(FUTTATO))

    def _fa(self, nev: str) -> ast.AST:
        return ast.parse((KEZI / nev).read_text(encoding="utf-8"), filename=nev)

    @staticmethod
    def _elkulonit_hivas(n: ast.AST) -> bool:
        """`elkulonit(...)`, `_kornyezet.elkulonit(...)` vagy `cfg_elkulonitve(...)` hívás."""
        if not isinstance(n, ast.Call):
            return False
        f = n.func
        nev = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        return nev in ("elkulonit", "cfg_elkulonitve")

    def _elkulonitett_nevek(self, fa: ast.AST) -> set[str]:
        return {t.id for n in ast.walk(fa) if isinstance(n, ast.Assign) and self._elkulonit_hivas(n.value)
                for t in n.targets if isinstance(t, ast.Name)}

    def test_az_inditok_es_az_inprocok_a_segedet_hasznaljak(self):
        for nev in sorted(INDITO | INPROC):
            with self.subTest(szkript=nev):
                fa = self._fa(nev)
                importal = any(isinstance(n, ast.ImportFrom) and n.module == "_kornyezet"
                               or isinstance(n, ast.Import) and any(a.name == "_kornyezet" for a in n.names)
                               for n in ast.walk(fa))
                self.assertTrue(importal, f"{nev}: nem importálja a _kornyezet-et")
                self.assertTrue(any(self._elkulonit_hivas(n) for n in ast.walk(fa)),
                                f"{nev}: nem hívja az elkulonit/cfg_elkulonitve függvényt")

    def test_a_popen_kornyezete_a_segedbol_jon(self):
        """Egy `subprocess.Popen` (core vagy app indítása) `env=`-je a segéd eredménye (vagy abból épített `dict`)."""
        for nev in sorted(INDITO):
            fa = self._fa(nev)
            jo = self._elkulonitett_nevek(fa)

            def rendben(v: ast.AST) -> bool:
                if self._elkulonit_hivas(v):
                    return True
                if isinstance(v, ast.Name):
                    return v.id in jo
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "dict" and v.args:
                    return rendben(v.args[0])
                if isinstance(v, ast.Dict) and v.keys and v.keys[0] is None:       # {**env, ...}
                    return rendben(v.values[0])
                return False

            hivasok = [n for n in ast.walk(fa) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr == "Popen"]
            self.assertTrue(hivasok, f"{nev}: nincs Popen (a besorolás téves?)")
            for h in hivasok:
                kw = {k.arg: k.value for k in h.keywords}
                with self.subTest(szkript=nev, sor=h.lineno):
                    self.assertIn("env", kw, f"{nev}:{h.lineno}: a Popen env nélkül a hívó környezetét örökli")
                    self.assertTrue(rendben(kw["env"]), f"{nev}:{h.lineno}: a Popen env-je nem a _kornyezet.elkulonit-ból jön")

    def test_nincs_kezzel_irt_ut_kulcs(self):
        """Kézzel írt `MOS_<[utak]-kulcs>` vagy `MANIFOLD_MODELL_ZAR` string-konstans a szkriptekben nem megengedett:
        az elkülönítés kulcslistája az `os.toml`-ból jön, így egy új `[utak]` kulcs nem maradhat ki."""
        kulcsok = {f"MOS_{k.upper()}" for k in _utak_kulcsai()} | {"MANIFOLD_MODELL_ZAR"}
        for p in _szkriptek():
            fa = self._fa(p.name)
            doc = {id(n.body[0].value) for n in ast.walk(fa)
                   if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                   and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            talalt = sorted({n.value for n in ast.walk(fa) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                             and id(n) not in doc for k in kulcsok if re.search(rf"(?<![A-Z_]){k}(?![A-Z_])", n.value)})
            for n in ast.walk(fa):
                if isinstance(n, ast.Call):
                    for kw in n.keywords:                               # dict(os.environ, MOS_VAULT=…)
                        if kw.arg in kulcsok:
                            talalt.append(kw.arg)
            self.assertEqual(talalt, [], f"{p.name}: kézzel írt út-kulcs: {talalt}")


class ElkulonitTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.proba = K.probamappa(self.cfg, "teszt", szkript="test_kezi_kornyezet.py")
        self.alap = tiszta_env(MOS_ROOT=str(self.root), HOME=str(Path(self._t.name) / "home"))

    def env(self, **kw) -> dict:
        return K.elkulonit(self.proba, self.cfg, alap=self.alap, **kw)

    def test_a_probamappa_jelolot_kap(self):
        j = json.loads((self.proba / ".mos-proba.json").read_text(encoding="utf-8"))
        self.assertEqual((j["szkript"], j["pid"], j["megtart"]), ("test_kezi_kornyezet.py", os.getpid(), False))
        self.assertTrue(j["letrehozva"])
        self.assertEqual(self.proba.parent, self.cfg.path("tmp"))

    def test_minden_ut_a_probamappaba_a_klonra_vagy_az_engedelyezettre_megy(self):
        klon, git = self.proba / "Manifold", self.proba / "vault.git"
        e = self.env(vault=klon, vault_git=git)
        kcfg = config.load(e)
        for kulcs in kcfg.data["utak"]:
            ut = kcfg.path(kulcs)
            if kulcs in K.VALODI_MARAD:
                self.assertEqual(ut, self.cfg.path(kulcs), kulcs)
            elif kulcs == "vault":
                self.assertEqual(ut, klon)
            elif kulcs == "vault_git":
                self.assertEqual(ut, git)
            else:
                self.assertIn(self.proba, ut.parents, f"{kulcs} → {ut} nincs a próbamappában")

    def test_a_hivo_shell_ut_kulcsai_nem_szivarognak_at(self):
        self.alap.update(MOS_BACKUP="/valodi/backup", MOS_SZEMELYES="/valodi/szemelyes", MOS_STATE="/valodi/state",
                         MOS_YTDLP_GIT="/valodi/ytdlp.git", MOS_NAPTAR_SEGED="/valodi/seged")
        kcfg = config.load(self.env())
        for kulcs in ("backup", "szemelyes", "state", "ytdlp_git", "naptar_seged"):
            self.assertIn(self.proba, kcfg.path(kulcs).parents, kulcs)

    def test_vault_nelkul_a_valodi_vault_marad_a_git_pedig_nem_el(self):
        """Csak olvasó mérésnél (index) a vault a valódi, de a pillanatkép-tároló nem él: nincs mit véletlenül írni."""
        kcfg = config.load(self.env())
        self.assertEqual(kcfg.path("vault"), self.cfg.path("vault"))
        self.assertFalse(snapshot.repos(kcfg)["vault"].exists())

    def test_a_valodi_ytdlp_tarolo_nem_el_a_klonban(self):
        """A2-tesztek-8: a `{modulok}/ytdlp` nem `{var}`-ból származik; a valódi `ytdlp.git` nem lehet élő a klónban."""
        valodi = snapshot.repos(self.cfg)["ytdlp"]
        valodi.work_tree.mkdir(parents=True, exist_ok=True)
        valodi.git_dir.mkdir(parents=True, exist_ok=True)
        (valodi.git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        self.assertIn("ytdlp", frame.live_repos(self.cfg))
        git = self.proba / "vault.git"
        kcfg = config.load(self.env(vault=self.v, vault_git=git))
        self.assertNotIn("ytdlp", frame.live_repos(kcfg))

    def test_naptar_seged_alapbol_nem_letezo(self):
        e = self.env()
        self.assertIn(self.proba, Path(e["MOS_NAPTAR_SEGED"]).parents)
        self.assertFalse(Path(e["MOS_NAPTAR_SEGED"]).exists())

    def test_modellzar_a_valodi(self):
        """T010 (L23): a klón workere ugyanazt a gépszintű zárat tartja, mint az éles — nem külön `{state}/modell.lock`-ot."""
        e = self.env()
        valodi = B.betolt(self.cfg, self.alap).zar
        self.assertEqual(Path(e["MANIFOLD_MODELL_ZAR"]), valodi)
        self.assertEqual(B.betolt(config.load(e), e).zar, valodi)
        self.assertNotIn(self.proba, B.betolt(config.load(e), e).zar.parents)

    def test_a_hivo_modellzara_megmarad(self):
        self.alap["MANIFOLD_MODELL_ZAR"] = "/valami/mas.lock"
        self.assertEqual(self.env()["MANIFOLD_MODELL_ZAR"], "/valami/mas.lock")

    # --- C34: a próbaindítás figyelmeztetései
    def test_figyelmeztetes_nincs_az_elkulonitett_kornyezetnel(self):
        e = self.env(vault=self.proba / "Manifold", vault_git=self.proba / "vault.git")
        self.assertEqual(K.proba_figyelmeztetesek(e, self.cfg), [])

    def test_figyelmeztet_ha_a_backup_a_valodira_mutat(self):
        e = self.env(vault=self.proba / "Manifold", vault_git=self.proba / "vault.git")
        e["MOS_BACKUP"] = str(self.cfg.path("backup"))
        figy = K.proba_figyelmeztetesek(e, self.cfg)
        self.assertEqual(len(figy), 1, figy)
        self.assertIn("backup", figy[0])
        self.assertIn("VALÓDI", figy[0])

    def test_figyelmeztet_ha_a_home_beli_valodi_mentesre_mutat(self):
        otthon = Path(self._t.name) / "otthon"
        (otthon / "Manifold-backup").mkdir(parents=True)
        e = self.env(vault=self.proba / "Manifold", vault_git=self.proba / "vault.git")
        e["MOS_BACKUP"] = str(otthon / "Manifold-backup")
        with mock.patch.dict(os.environ, {"HOME": str(otthon)}):
            figy = K.proba_figyelmeztetesek(e, self.cfg)
        self.assertTrue(any("backup" in f and "VALÓDI" in f for f in figy), figy)

    def test_figyelmeztet_ha_a_vault_a_valodi(self):
        e = self.env()                                              # vault nélkül: a valódi vault, csak olvasásra
        e["MOS_VAULT"] = str(self.cfg.path("vault"))
        figy = K.proba_figyelmeztetesek(e, self.cfg)
        self.assertTrue(any("vault" in f for f in figy), figy)

    def test_figyelmeztet_ha_mar_fut_a_valodi_peldany(self):
        zar = self.cfg.path("run") / "core.lock"
        zar.parent.mkdir(parents=True, exist_ok=True)
        zar.write_text("pid")
        e = self.env(vault=self.proba / "Manifold", vault_git=self.proba / "vault.git")
        self.assertFalse(K.valodi_core_fut(self.cfg))
        with open(zar) as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)                           # a „futó core” tartja
            figy = K.proba_figyelmeztetesek(e, self.cfg)
            self.assertTrue(K.valodi_core_fut(self.cfg))
            fcntl.flock(fh, fcntl.LOCK_UN)
        self.assertEqual(len(figy), 1, figy)
        self.assertIn("már fut", figy[0])

    def test_a_proba_ablak_cimsora_a_hej_forrasaban_es_a_proba_app_ban_ugyanaz_a_valtozo(self):
        """A kétnyelvű szerződés: a `proba_app.py` ezt a változót állítja, a héj ezt olvassa, és a címsor „PRÓBA”."""
        swift = (REPO / "shell" / "Sources" / "AppController.swift").read_text(encoding="utf-8")
        proba_app = (KEZI / "proba_app.py").read_text(encoding="utf-8")
        self.assertIn(f'environment["{K.PROBA_JELZES}"]', swift)
        self.assertIn("PRÓBA — Manifold", swift)
        self.assertIn("w.title = AppController.ablakCim", swift)
        self.assertIn("env[PROBA_JELZES]", proba_app)
        self.assertIn("proba_figyelmeztetesek(env, cfg)", proba_app)

    def test_home_csak_kerve_csere(self):
        valodi_home = self.alap["HOME"]
        self.assertEqual(self.env()["HOME"], valodi_home)
        e = self.env(home=True)
        self.assertEqual(e["HOME"], str(self.proba / "home"))
        self.assertTrue((self.proba / "home").is_dir())

    def test_masolat_a_valodi_fajlbol_indul(self):
        self.cfg.path("router_db").parent.mkdir(parents=True, exist_ok=True)
        self.cfg.path("router_db").write_bytes(b"kalibracio")
        kcfg = config.load(self.env(masolat=("router_db",)))
        self.assertEqual(kcfg.path("router_db").read_bytes(), b"kalibracio")
        self.assertIn(self.proba, kcfg.path("router_db").parents)
        self.assertEqual(self.cfg.path("router_db").read_bytes(), b"kalibracio")

    def test_ellenorzes_elkap_egy_kimaradt_utat(self):
        e = self.env()
        e["MOS_STATE"] = "/valodi/state"                # egy kimaradt (visszaállított) kulcs
        with self.assertRaisesRegex(AssertionError, "state"):
            K.ellenoriz(e, self.proba, self.cfg)

    def test_uj_ut_kulcs_alapbol_elkulonul(self):
        """Ha az `os.toml`-ba új `[utak]` kulcs kerül (C27 `szemelyes`, C29 `naptar_seged`), az elkülönítés nem marad ki."""
        os_toml = Path(self._t.name) / "os-uj.toml"
        szoveg = (self.root / "config" / "os.toml").read_text(encoding="utf-8")
        os_toml.write_text(szoveg.replace("[utak]\n", '[utak]\ntanulas = "{var}/tanulas"\n', 1), encoding="utf-8")
        alap = tiszta_env(MOS_ROOT=str(self.root), HOME=str(Path(self._t.name) / "home"), MOS_CONFIG=str(os_toml))
        cfg = config.load(alap)
        self.assertIn("tanulas", cfg.data["utak"])
        e = K.elkulonit(self.proba, cfg, alap=alap)
        self.assertIn(self.proba, Path(e["MOS_TANULAS"]).parents)
        self.assertTrue(Path(e["MOS_TANULAS"]).is_dir())

    def test_csak_olvasott_eszkoztar_valodi_marad_a_klonban(self):
        """A klón-app CAS-a, C++-a és Kukája a valódi (csak olvasott) eszköztárat használja; az írható `var/` nem szivárog."""
        e = self.env(vault=self.proba / "Manifold", vault_git=self.proba / "vault.git")
        kcfg = config.load(e)
        for kulcs in ("sandbox_exec", "llvm", "sdk", "hej_cli"):
            self.assertEqual(kcfg.path(kulcs), self.cfg.path(kulcs), kulcs)
        valodi_var = self.cfg.path("var")
        for kulcs in K.VALODI_MARAD - {"work", "var", "venv", "models", "modulok", "runtime", "app_dist", "ffmpeg", "node"}:
            ut = kcfg.path(kulcs)
            self.assertNotIn(valodi_var, (ut, *ut.parents), f"{kulcs} a valódi var/ alatt: írható szivárgás")

    def test_megvar_kilepest_a_gyermek_kilepeseig_var(self):
        """A mérések a core kilépése UTÁN törölnek (különben a lezáró mentés újraírja a törölt próbamappát)."""
        import subprocess
        import time
        szulo = subprocess.Popen([sys.executable, "-B", "-c",
                                  "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(1.2)']).wait();time.sleep(30)"])
        self.addCleanup(lambda: (szulo.kill(), szulo.wait()))
        gy = []
        for _ in range(40):
            gy = K.gyermek_pidek(szulo.pid)
            if gy:
                break
            time.sleep(0.1)
        self.assertEqual(len(gy), 1)
        self.assertFalse(K.megvar_kilepest(gy, mp=0.2))         # még fut: nem lép ki időben
        self.assertTrue(K.megvar_kilepest(gy, mp=10))
        self.assertTrue(K.megvar_kilepest([], mp=1))

    def test_valodi_naptar_csak_kifejezett_kapcsolora(self):
        e = self.env(valodi_naptar=True)
        self.assertEqual(Path(e["MOS_NAPTAR_SEGED"]), self.cfg.path("naptar_seged"))


class SemaProbaTest(unittest.TestCase):
    """T080 (2. audit): a `sema_proba.py` menet-útlistája csak a `Mos-Forras: pult-*` commitokat nézi — a valódi vault
    nem rögzített változását az első mentés `kezi` commitba teszi, és az nem a menet írása."""

    def test_a_kezi_commit_utjai_nem_szamitanak(self):
        import sema_proba
        naplo = ("\x01" + "a" * 40 + "\tkezi\nX01/obsidianban-szerkesztett.md\nT01/masik.md\n\n"
                 "\x01" + "b" * 40 + "\tpult-szerkeszto\nM01/jegyzet.md\n\n"
                 "\x01" + "c" * 40 + "\tpult-szerkeszto\nM01/jegyzet.md\nM01/Ékezetes név.md\n")
        self.assertEqual(sema_proba.menet_utak_a_naplobol(naplo), {"M01/jegyzet.md", "M01/Ékezetes név.md"})
        self.assertEqual(sema_proba.menet_utak_a_naplobol(""), set())
        self.assertEqual(sema_proba.menet_utak_a_naplobol("\x01" + "d" * 40 + "\t\nX/y.md\n"), set())      # forrás nélkül sem

    def test_a_naplo_formatuma_valodi_git_naplon_is_igaz(self):
        import subprocess
        import sema_proba
        from core import snapshot
        with tmpdir() as t:
            cfg, root, v = alg_core(t)
            (v / "A.md").write_text("# A\n", encoding="utf-8")
            (v / "B.md").write_text("# B\n", encoding="utf-8")
            repo = snapshot.repos(cfg)["vault"]
            repo.init()
            repo.commit("alap", {"Mos-Forras": "kezi"})
            fej = repo.git("rev-parse", "HEAD").stdout.strip()
            (v / "B.md").write_text("# B Obsidianban\n", encoding="utf-8")
            repo.commit("kezi változás", {"Mos-Forras": "kezi"})
            (v / "A.md").write_text("# A szerkesztve\n", encoding="utf-8")
            repo.commit("szerkesztő", {"Mos-Forras": "pult-szerkeszto"})
            ki = subprocess.run(["git", "-c", "core.quotepath=false", "--git-dir", str(repo.git_dir), "log", "--name-only",
                                 "--format=" + sema_proba.MENET_FORMATUM, f"{fej}..HEAD"], capture_output=True, text=True).stdout
            self.assertEqual(sema_proba.menet_utak_a_naplobol(ki), {"A.md"})


class ProbaAppLeallitasTest(unittest.TestCase):
    """T081 (2. audit): a `proba_app` SIGTERM-re, SIGINT-re és SIGHUP-ra is rendezetten leállítja a gyermekét, nyitott stdin
    (`tail -f /dev/null |`) nélkül; háttérből indítva az örökölten ignorált SIGINT sem akaszthatja meg."""

    def setUp(self):
        import signal
        self.regi = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        self.addCleanup(lambda: [signal.signal(s, h) for s, h in self.regi.items()])

    def _gyermek(self, kod: str, stdin=None):
        import subprocess
        p = subprocess.Popen([sys.executable, "-B", "-c", kod], stdin=stdin)
        self.addCleanup(lambda: (p.kill(), p.wait()) if p.poll() is None else None)
        return p

    def _jelre_leall(self, jel):
        import signal
        import threading
        import time
        import proba_app
        p = self._gyermek("import time; time.sleep(120)")
        threading.Timer(0.4, os.kill, (os.getpid(), getattr(signal, jel))).start()
        t0 = time.monotonic()
        proba_app._var(p, lezar=p.terminate)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertIsNotNone(p.poll())

    def test_sigterm(self):
        self._jelre_leall("SIGTERM")

    def test_sigint_ignoralt_orokles_mellett_is(self):
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)          # háttérből indítva a SIGINT örökölten ignorált
        self._jelre_leall("SIGINT")

    def test_sighup(self):
        self._jelre_leall("SIGHUP")

    def test_a_core_stdin_lezarasra_rendezetten_kilep(self):
        import subprocess
        import proba_app
        p = self._gyermek("import sys; sys.stdin.read()", stdin=subprocess.PIPE)
        import threading
        threading.Timer(0.4, lambda: os.kill(os.getpid(), 15)).start()
        proba_app._var(p, lezar=lambda: p.stdin.close())
        self.assertEqual(p.poll(), 0)

    def test_ha_nem_all_le_rendezetten_terminate_majd_kill(self):
        import signal
        import threading
        import proba_app
        p = self._gyermek("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)")
        threading.Timer(0.4, os.kill, (os.getpid(), signal.SIGTERM)).start()
        proba_app._var(p, lezar=lambda: None, rendezett_mp=0.5, terminate_mp=0.5)
        self.assertIsNotNone(p.poll())


class HelpersEnvTest(unittest.TestCase):
    """A `tests.helpers.env()` hermetikus gyermek-környezetet ad: ál-HOME (a `{home}` — belső lemezes mentés, ~/.cache —
    a valódi HOME-hoz nem érhet), és a hívó MOS_*/MANIFOLD_* változói nem szivárognak át (T011)."""

    def setUp(self):
        valodi = {k: os.environ.get(k) for k in ("MOS_TESZT_X", "MANIFOLD_MODELL_ZAR")}
        os.environ["MOS_TESZT_X"], os.environ["MANIFOLD_MODELL_ZAR"] = "1", "/valodi.lock"

        def vissza():
            for k, v in valodi.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.addCleanup(vissza)

    def test_hermetikus_es_al_home(self):
        e = tiszta_env()
        self.assertNotIn("MOS_TESZT_X", e)
        self.assertNotIn("MANIFOLD_MODELL_ZAR", e)
        self.assertNotEqual(e["HOME"], os.environ["HOME"])
        self.assertTrue(Path(e["HOME"]).is_dir())

    def test_al_home_az_algyoker_testvere(self):
        with tmpdir() as t:
            root = Path(t) / "work" / "os"
            self.assertEqual(Path(tiszta_env(MOS_ROOT=str(root))["HOME"]), Path(t) / "home")

    def test_kifejezett_home_nyer_es_a_valodi_home_kerheto(self):
        self.assertEqual(tiszta_env(HOME="/x/home")["HOME"], "/x/home")
        self.assertEqual(tiszta_env(home=False)["HOME"], os.environ["HOME"])

    def test_valodi_home_mellett_is_algyoker_lokalis_a_belso_lemezes_mentes(self):
        """C29.6: egy `--selftest`-ben (valódi HOME) indított core leállásakor az állapotmásolat a valódi `~/Manifold-backup`-ba
        került volna (és a rotációját is érhette)."""
        with tmpdir() as t:
            root = Path(t) / "work" / "os"
            e = tiszta_env(MOS_ROOT=str(root), home=False)
            self.assertEqual(e["HOME"], os.environ["HOME"])
            self.assertEqual(Path(e["MOS_BACKUP"]), Path(t) / "home" / "Manifold-backup")
            self.assertEqual(tiszta_env(MOS_ROOT=str(root), home=False, MOS_BACKUP="/x/b")["MOS_BACKUP"], "/x/b")
            self.assertNotIn("MOS_BACKUP", tiszta_env(home=False))


class MasolatIndexFeluletTest(unittest.TestCase):
    """Az `emlites_meres.py` / `hasonlosag_meres.py` `_MasolatIndex`-e azt a felületet adja, amelyet a core `Emlitesek`-e hív
    (C33 óta `olvaso()`, `generacio`): a szkriptek korábban `AttributeError`-ral buktak a valódi vaulton."""

    def test_a_felulet_es_a_valodi_index_masolatan_az_emlitesek_dolgozik(self):
        import shutil
        import emlites_meres as E
        from core.asszisztens.emlites import Emlitesek
        from tests.index_segedek import alvault, index_indit
        self.assertTrue(callable(getattr(E._MasolatIndex, "generacio", None)) or isinstance(E._MasolatIndex.generacio, int))
        with tmpdir() as t:
            cfg, v = alvault(t, {"T01/Spárta törvényei.md": "# Spárta\nA spártai állam.\n",
                                      "T01/Athén.md": "# Athén\nLásd a Spárta törvényei jegyzetet.\n"})
            ix, _ = index_indit(cfg)
            ix.leallit()                                      # a WAL kiürül: a másolat teljes
            masolat = Path(t) / "masolat.sqlite"
            shutil.copy(cfg.path("index") / "vault.sqlite", masolat)
            mi = E._MasolatIndex(masolat)
            for nev in ("olvaso", "_olvaso"):
                with getattr(mi, nev)() as c:
                    self.assertGreaterEqual(c.execute("SELECT COUNT(*) FROM fajl").fetchone()[0], 2)
            self.assertEqual(len(E._mintat_valaszt(mi, cfg, 5, 1)), 2)
            em = Emlitesek(cfg, mi)
            em.szotar()                                       # a szótár építése az `index.olvaso()`-t hívja
            self.assertIsInstance(em.keres("T01/Athén.md", "Mesélek a Spárta törvényei című jegyzetről."), dict)


if __name__ == "__main__":
    unittest.main()
