"""A folyamat gyökerei (F3-DESIGN §2.1, §2.6): az elrendezés felismerése, az I1 (termékben semmi írható nem mutat a
kódfába), a `rogzit` (a gyermekek ugyanazt oldják fel), a `shell` kimenete szóközös utakkal (K13: `Application Support`),
a `portable init`, a `core start` rögzítése, és a `rejtett` kihagyási lista."""
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from core import config, gyokerek, rejtett
from tests.helpers import REPO, alg_bundle, alg_gyoker, env, tmpdir

ID = "0123456789abcdef0123456789abcdef"


def lista(gyoker: Path) -> list[tuple[str, int]]:
    return sorted((str(p.relative_to(gyoker)), p.stat().st_mtime_ns) for p in gyoker.rglob("*"))


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.home = self.t / "home"

    def termek(self, munkater: bool = True) -> tuple[Path, Path]:
        root = alg_bundle(self._t.name)
        vault = self.t / "Jegyzetek"
        vault.mkdir()
        if munkater:
            (vault / ".manifold").mkdir()
            (vault / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{ID}"\n', encoding="utf-8")
        return root, vault


class ElrendezesTeszt(Alap):
    def test_felismeres(self):
        self.assertEqual(config.elrendezes(alg_gyoker(self._t.name), {}), "hordozhato")
        b = alg_bundle(self._t.name)
        self.assertEqual(config.elrendezes(b, {}), "termek")
        self.assertEqual(config.elrendezes(Path("/x/Y.app/Contents/Resources/mas"), {}), "hordozhato")
        self.assertEqual(config.elrendezes(Path("/x/Contents/Resources/manifold"), {}), "hordozhato")
        self.assertEqual(config.elrendezes(Path("/x"), {"MOS_ELRENDEZES": "termek"}), "termek")
        with self.assertRaises(config.ConfigError) as e:
            config.elrendezes(Path("/x"), {"MOS_ELRENDEZES": "valami"})
        self.assertEqual(e.exception.kod, "elrendezes_ismeretlen")

    def test_hordozhato_csomagban_csak_developer_modban(self):
        b = alg_bundle(self._t.name)
        with self.assertRaises(config.ConfigError) as e:
            config.elrendezes(b, {"MOS_ELRENDEZES": "hordozhato"})
        self.assertEqual(e.exception.kod, "hordozhato_bundleben")
        self.assertEqual(config.elrendezes(b, {"MOS_ELRENDEZES": "hordozhato", "MOS_FEJLESZTO": "1"}), "hordozhato")


class I1Teszt(Alap):
    def test_termekben_minden_irhato_ut_a_kodfan_kivul(self):
        root, vault = self.termek()
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault)})
        self.assertEqual(cfg.elrendezes, "termek")
        for k, p in cfg.utak.items():
            bent = p == root or root in p.parents
            if not bent:
                continue
            self.assertIn(k, config.CSAK_OLVASOTT - {"naptar_seged", "hej_cli", "sandbox_exec"}, f"{k}: {p}")
        self.assertEqual(cfg.path("naptar_seged"), self.t / "X.app" / "Contents" / "MacOS" / "Manifold")
        self.assertEqual(cfg.path("venv"), root / "runtime" / "venv")
        self.assertEqual(cfg.path("ytdlp"), vault / ".manifold" / "var" / "ytdlp")
        self.assertEqual(cfg.expand(cfg.section("modellgazda")["zar"]),
                         str(self.home / "Library" / "Application Support" / "Manifold" / "state" / "modell.lock"))

    def test_kodfaba_mutato_irhato_ut_hiba(self):
        root, vault = self.termek()
        for kulcs in ("MOS_TMP", "MOS_INSTALL"):
            with self.subTest(kulcs=kulcs), self.assertRaises(config.ConfigError) as e:
                config.load({"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault), kulcs: str(root / "var")})
            self.assertEqual(e.exception.kod, "iras_a_kodba")
        with self.assertRaises(config.ConfigError) as e:      # a vault sem lehet a csomagban
            config.load({"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(root / "v"),
                         "MOS_WORKSPACE_ID": ID})
        self.assertEqual(e.exception.kod, "iras_a_kodba")


class RogzitTeszt(Alap):
    def test_minden_feloldott_kulcs_abszolut_es_a_gyermek_ugyanazt_latja(self):
        root = alg_gyoker(self._t.name)
        e = {"MOS_ROOT": str(root), "HOME": str(self.home)}
        cfg = config.load(e)
        gyerek = dict(e)
        gyokerek.rogzit(cfg, gyerek)
        for k, p in cfg.utak.items():
            self.assertEqual(gyerek[f"MOS_{k.upper()}"], str(p))
            self.assertTrue(os.path.isabs(gyerek[f"MOS_{k.upper()}"]), k)
        self.assertEqual(gyerek["MOS_ELRENDEZES"], "hordozhato")
        self.assertNotIn("MOS_WORKSPACE_ID", gyerek)
        # a réteg közben megváltozik (más vault): a rögzített gyermek a régi utakat látja (K4: az út a következő megnyitáskor hat)
        (root / "var" / "settings.toml").write_text('[utak]\nvault = "/mas/vault"\n', encoding="utf-8")
        self.assertEqual(config.load(gyerek).utak, cfg.utak)
        self.assertEqual(config.load(e).path("vault"), Path("/mas/vault"))

    def test_feloldatlan_kulcs_kimarad_a_munkater_azonosito_bekerul(self):
        root = alg_gyoker(self._t.name, vault=False, preset=None)
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        e: dict[str, str] = {}
        gyokerek.rogzit(cfg, e)
        self.assertNotIn("MOS_VAULT", e)
        self.assertNotIn("MOS_WORKSPACE", e)
        root, vault = self.termek()
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault)})
        gyokerek.rogzit(cfg, e)
        self.assertEqual((e["MOS_WORKSPACE_ID"], e["MOS_ELRENDEZES"]), (ID, "termek"))

    def test_folyamat_env(self):
        root = alg_gyoker(self._t.name)
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        f = gyokerek.folyamat_env(cfg, {"HF_HUB_OFFLINE": "0"})
        self.assertEqual(f["HF_HOME"], str(cfg.path("models")))
        self.assertEqual((f["HF_HUB_OFFLINE"], f["TRANSFORMERS_OFFLINE"]), ("0", "1"))   # a kifejezett érték marad
        self.assertEqual((f["XDG_CACHE_HOME"], f["UV_CACHE_DIR"], f["PIP_CACHE_DIR"]),
                         (str(cfg.path("cache")), str(cfg.path("cache") / "uv"), str(cfg.path("cache") / "pip")))
        self.assertEqual((f["TMPDIR"], f["PYTHONDONTWRITEBYTECODE"]), (str(cfg.path("tmp")), "1"))


class ShellTeszt(Alap):
    def futtat(self, gyoker: Path, *args: str, **extra) -> subprocess.CompletedProcess:
        e = env(MOS_ROOT=str(gyoker), HOME=str(self.home), PYTHONPATH=str(REPO), **extra)
        return subprocess.run([sys.executable, "-B", "-m", "core.gyokerek", *args], capture_output=True, text=True, env=e,
                              cwd=str(self.t), timeout=60)

    def kiertekel(self, gyoker: Path, *valtozok: str, **extra) -> list[str]:
        """A `shell` kimenete bash `eval`-lal (ahogy a `bin/mos`), majd a változók értéke soronként."""
        e = env(MOS_ROOT=str(gyoker), HOME=str(self.home), PYTHONPATH=str(REPO), **extra)
        kod = f'eval "$("{sys.executable}" -B -m core.gyokerek shell --rogzit)" && printf "%s\\n" ' + \
              " ".join(f'"${v}"' for v in valtozok)
        p = subprocess.run(["bash", "-c", kod], capture_output=True, text=True, env=e, cwd=str(self.t), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.split("\n")[:len(valtozok)]

    def test_szokozos_utak_hordozhato(self):
        (self.t / "a b").mkdir()
        root = alg_gyoker(str(self.t / "a b"))
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        ki = self.kiertekel(root, "TMPDIR", "MOS_VAULT", "XDG_CACHE_HOME", "HF_HOME", "MOS_ELRENDEZES")
        self.assertEqual(ki, [str(cfg.path("tmp")), str(cfg.path("vault")), str(cfg.path("cache")), str(cfg.path("models")),
                              "hordozhato"])
        self.assertIn(" ", ki[0])
        self.assertTrue((root / "var" / ".metadata_never_index").is_file())

    def test_termek_application_support_es_a_csomag_erintetlen(self):
        root, vault = self.termek()
        elotte = lista(self.t / "X.app")
        install = self.home / "Library" / "Application Support" / "Manifold"
        ki = self.kiertekel(root, "TMPDIR", "MOS_VAR", "MOS_INSTALL", "HF_HOME", MOS_VAULT=str(vault))
        self.assertEqual(ki, [str(vault / ".manifold" / "var" / "tmp"), str(vault / ".manifold" / "var"), str(install),
                              str(install / "models")])
        self.assertTrue((install / ".metadata_never_index").is_file())
        self.assertTrue((vault / ".manifold" / "var" / ".metadata_never_index").is_file())
        self.assertTrue((install / "run").is_dir() and (install / "logs").is_dir())
        # munkatér nélkül (a vault nincs megadva) a TMPDIR az {install}/tmp
        self.assertEqual(self.kiertekel(root, "TMPDIR"), [str(install / "tmp")])
        self.assertEqual(lista(self.t / "X.app"), elotte)

    def test_betoltesi_hiba_nem_allitja_meg_a_parancsot(self):
        root = alg_gyoker(self._t.name)
        (root / "var" / "settings.toml").write_text("[hibas\n", encoding="utf-8")
        p = self.futtat(root, "shell")
        self.assertEqual(p.returncode, 0)
        self.assertIn("settings_toml_hibas", p.stderr)
        self.assertIn("export PYTHONDONTWRITEBYTECODE=1", p.stdout)
        self.assertNotIn("TMPDIR", p.stdout)

    def test_json(self):
        root = alg_gyoker(self._t.name)
        p = self.futtat(root, "json")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual((d["elrendezes"], d["utak"]["vault"], d["feloldatlan"]),
                         ("hordozhato", str(root.parent / "Manifold"), {}))
        self.assertEqual(d["retegek"]["utak.vault"], "telepites")

    def test_ismeretlen_parancs(self):
        self.assertEqual(self.futtat(alg_gyoker(self._t.name), "nincs").returncode, 2)


class PortableInitTeszt(Alap):
    def setUp(self):
        super().setUp()
        self.root = alg_gyoker(self._t.name, preset=None, vault=False)
        self.vault = self.t / "SSD vault"
        self.vault.mkdir()

    def init(self, **kw) -> Path:
        return gyokerek.portable_init(self.root, environ={"HOME": str(self.home)}, **{"vault": self.vault, **kw})

    def test_iras_es_betoltes(self):
        idegen = self.t / "v2" / "var" / "run" / "core.lock"
        cel = self.init(presetek=["v2-kompat"], backup="{home}/Manifold-backup/ssd", idegen_zarak=[str(idegen)])
        self.assertEqual(cel, self.root / "var" / "settings.toml")
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home)})
        self.assertEqual(cfg.elutasitott, [])
        self.assertEqual(cfg.path("vault"), self.vault)
        self.assertEqual(cfg.path("backup"), self.home / "Manifold-backup" / "ssd")
        self.assertEqual(cfg.section("hordozhato")["idegen_zarak"], [str(idegen)])
        self.assertEqual(cfg.forras("fuzet", "mappak"), "preset:v2-kompat")
        self.assertFalse((self.vault / ".manifold").exists())               # egy v2 által kezelt vaultba nem ír
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_meglevo_csak_igen_mellett_es_az_elozo_megmarad(self):
        self.init()
        with self.assertRaises(config.ConfigError) as e:
            self.init(presetek=["v2-kompat"])
        self.assertEqual(e.exception.kod, "settings_letezik")
        regi = (self.root / "var" / "settings.toml").read_text(encoding="utf-8")
        self.init(presetek=["v2-kompat"], igen=True)
        self.assertEqual((self.root / "var" / "settings.toml.elozo").read_text(encoding="utf-8"), regi)
        self.assertIn("v2-kompat", (self.root / "var" / "settings.toml").read_text(encoding="utf-8"))

    def test_elutasitasok(self):
        for kw, kod in (({"vault": self.t / "nincs"}, "vault_nem_letezik"),
                        ({"vault": self.root / "var"}, "vault_a_kodban"),
                        ({"presetek": ["nincs-ilyen"]}, "settings_ervenytelen")):
            with self.subTest(kod=kod), self.assertRaises(config.ConfigError) as e:
                self.init(**kw)
            self.assertEqual(e.exception.kod, kod)
        b = alg_bundle(str(self.t / "b"))
        with self.assertRaises(config.ConfigError) as e:
            gyokerek.portable_init(b, vault=self.vault, environ={"HOME": str(self.home)})
        self.assertEqual(e.exception.kod, "portable_termekben")
        self.assertFalse((self.root / "var" / "settings.toml").exists())

    def test_cli(self):
        e = env(MOS_ROOT=str(self.root), HOME=str(self.home), PYTHONPATH=str(REPO))
        p = subprocess.run([sys.executable, "-B", "-m", "core.gyokerek", "portable-init", "--vault", str(self.vault),
                            "--preset", "v2-kompat", "--idegen-zar", "/a b/core.lock"], capture_output=True, text=True,
                           env=e, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home)})
        self.assertEqual((cfg.path("vault"), cfg.section("hordozhato")["idegen_zarak"]), (self.vault, ["/a b/core.lock"]))
        p = subprocess.run([sys.executable, "-B", "-m", "core.gyokerek", "portable-init", "--vault", str(self.vault)],
                           capture_output=True, text=True, env=e, timeout=60)
        self.assertEqual(p.returncode, 78)
        self.assertIn("settings_letezik", p.stderr)


class CoreStartTeszt(Alap):
    def test_a_start_rogzit_es_a_cfg_t_adja_at(self):
        from core import __main__ as fo
        from core import server
        root = alg_gyoker(self._t.name)
        kapott = {}

        def start(**k):
            kapott.update(k, var=os.environ.get("MOS_VAR"), tmp=os.environ.get("TMPDIR"), elr=os.environ.get("MOS_ELRENDEZES"))
            return 0

        with mock.patch.dict(os.environ, {"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_SETTINGS": ""}), \
                mock.patch.object(server, "start", start):
            self.assertEqual(fo.main(["start"]), 0)
        cfg = kapott["cfg"]
        self.assertEqual((kapott["var"], kapott["tmp"], kapott["elr"]), (str(root / "var"), str(root / "var" / "tmp"), "hordozhato"))
        self.assertEqual(cfg.path("vault"), root.parent / "Manifold")

    def test_konfig_hiba_78_es_hiba_sor(self):
        from core import __main__ as fo
        from core import server
        root, vault = self.termek(munkater=False)
        ki, hiba = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault)}), \
                mock.patch.object(server, "start", side_effect=AssertionError("nem indulhat")), \
                redirect_stdout(ki), redirect_stderr(hiba):
            self.assertEqual(fo.main(["start"]), fo.KONFIG_HIBA_KILEPES)
        sor = json.loads(ki.getvalue().splitlines()[0])
        self.assertEqual((sor["hiba"], sor["param"]["vault"]), ("nem_workspace", str(vault)))
        self.assertEqual(fo.KONFIG_HIBA_KILEPES, 78)


class RejtettTeszt(unittest.TestCase):
    def test_metsz(self):
        self.assertIn(".manifold", rejtett.KIHAGYOTT_MAPPAK)
        m = ["A", ".manifold", ".obsidian", ".trash", ".git", "node_modules", ".rejtett-mappa", "B"]
        self.assertIs(rejtett.metsz(m), m)
        self.assertEqual(m, ["A", ".rejtett-mappa", "B"])
        self.assertTrue(rejtett.kihagyott(".manifold") and not rejtett.kihagyott("A"))


if __name__ == "__main__":
    unittest.main()
