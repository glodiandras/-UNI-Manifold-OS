"""A doctor termék-módja (F3-DESIGN §6, WP5): minden §6-sor, a `kod`/`osztaly`/`javitas` stabilitása és a `--json` kimenet.

A termék ál-telepítése: `alg_bundle` (a `*.app/Contents/Resources/manifold`-alakú gyökér, ál-HOME-mal), az ál-telepítési mappa
(`~/Library/Application Support/Manifold`), egy `.manifold/workspace.toml`-os vault és a vault valódi (üres) pillanatkép-tárolója.
A hordozható szabályokat a `tests/test_doctor.py` védi; itt csak a közös `kod`/`osztaly` szerződés és a két mód határa."""
import contextlib
import fcntl
import io
import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import config, doctor, epites, mentes, snapshot
from tests.helpers import REPO, alg_bundle, alg_gyoker, tmpdir

ID = "9f1c" + "0" * 28
MAS_ID = "a" * 32
VAN_KOD = re.compile(r"^[a-z][a-z0-9_]*$")

# A §6 táblázat soraiból a zöld ál-termékben mindig jelen levő sorok kódjai (a kód nem változhat, ha a szöveg igen)
TERMEK_ZOLD_KODOK = {
    "bundle_epites", "iras_a_kodba", "kotet", "kotet_fajlrendszer", "workspace_toml", "workspace_formatum", "manifold_kizarva",
    "pillanatkep_vault", "konfig_kulcsok", "telepites_irhato", "szabad_hely", "zar_helye", "regiszter", "vault", "vault_sema",
    "git", "offline", "runtime", "python", "manifold_app", "spotlight", "mentes", "index", "probaklonok"}
# Csak forrás-checkouton értelmes sorok: termékben nem keletkezhetnek
CSAK_HORDOZHATO_KODOK = {"gyoker", "var_symlink", "lock", "runtime_verzio", "requirements_in", "kapu", "napi_canvas", "felulet",
                         "build_felulet", "build_hej", "cpp_linker", "cpp_sdk"}


def halott_pid() -> int:
    for pid in range(99_999, 50_000, -1):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            continue
    raise RuntimeError("nincs halott pid")


def termek_epit(tmp: Path, *, vault: Path | None = None, id: str = ID, regiszter: dict | None = None) -> SimpleNamespace:
    """Ál-termék a `tmp` alatt: bundle-gyökér (épségjegyzékkel), ál-HOME + telepítési mappa, vault munkatérrel. A `regiszter`
    (ha adott) a `config.load` ELŐTT íródik, mert a `telepites` állapot a `{var}` helyét változtatja."""
    tmp = Path(tmp)
    root = alg_bundle(str(tmp)).resolve()
    home = tmp / "home"
    vault = vault or tmp / "vault"
    install = home / "Library" / "Application Support" / "Manifold"
    (root / "app" / "dist").mkdir(parents=True)
    (root / "app" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    for rel in ("runtime/python/bin/python3", "runtime/node/bin/node", "core/x.py", "modulok/m.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("# ál\n", encoding="utf-8")
    for f in ("letoltes.toml", "runtime-pins.env"):
        if (REPO / "config" / f).is_file():
            (root / "config" / f).write_bytes((REPO / "config" / f).read_bytes())
    (root / "config" / "schema-default.json").write_text(json.dumps({"mezosorrend": ["tags"]}), encoding="utf-8")
    manifest = {"verzio": 1, "felulet": "f" * 64, "mag": epites.ujjlenyomat(root, "mag"), "hej": "h" * 64}
    for ut in (root / "app" / "dist" / "epites.json", root.parent / "epites.json"):
        ut.write_text(json.dumps(manifest), encoding="utf-8")
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".manifold").mkdir()
    (vault / ".manifold" / "workspace.toml").write_text(
        f'[workspace]\nid = "{id}"\nformatum = 1\nolvaso_min = 1\nnev = "Teszt"\n', encoding="utf-8")
    (install / "run").mkdir(parents=True)
    (install / ".metadata_never_index").write_text("", encoding="utf-8")
    if regiszter is not None:
        (install / "workspaces.json").write_text(json.dumps(regiszter), encoding="utf-8")
    env = {"MOS_ROOT": str(root), "HOME": str(home), "MOS_VAULT": str(vault)}
    cfg = config.load(env)
    var = cfg.path("var")
    for d in ("state", "tmp", "run", "runs", "cache", "index"):
        (var / d).mkdir(parents=True, exist_ok=True)
    (var / ".metadata_never_index").write_text("", encoding="utf-8")
    return SimpleNamespace(root=root, home=home, vault=vault, install=install, env=env, cfg=cfg, var=var,
                           python=root / "runtime" / "python" / "bin" / "python3")


class TermekAlap(unittest.TestCase):
    """Közös alap: az ál-termék, és a külső világot (codesign, fájlrendszer, szabad hely) rögzítő foltok."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.t = termek_epit(self.tmp)
        for nev, kw in (("_codesign", {"return_value": (0, "")}), ("_alairas", {}), ("_fajlrendszer", {"return_value": ("apfs", True)}),
                        ("_szabad_bajt", {"return_value": 200 << 30})):
            p = mock.patch.object(doctor, nev, **kw)
            p.start()
            self.addCleanup(p.stop)

    def tar(self, cfg=None):
        """A vault valódi pillanatkép-tárolója (üres, HEAD nélkül)."""
        repo = snapshot.repos(cfg or self.t.cfg)["vault"]
        repo.init()
        return repo

    def sorok(self, cfg=None, *, termek=None, env=None, python=None) -> dict[str, doctor.Eredmeny]:
        e = doctor.ellenoriz(cfg or self.t.cfg, {"HF_HUB_OFFLINE": "1", "PATH": os.environ["PATH"], **(env or {})}, self.t.home,
                             python or self.t.python, termek=termek)
        kodok = [x.kod for x in e]
        self.assertEqual(len(kodok), len(set(kodok)), f"ismétlődő kód: {sorted(k for k in set(kodok) if kodok.count(k) > 1)}")
        return {x.kod: x for x in e}

    def ws_toml(self, szoveg: str) -> None:
        (self.t.vault / ".manifold" / "workspace.toml").write_text(szoveg, encoding="utf-8")


class ZoldFutasTeszt(TermekAlap):
    def setUp(self):
        super().setUp()
        self.tar()

    def test_zold_termek_nincs_hiba_es_minden_sor_termek_osztalyu(self):
        r = self.sorok()
        hibak = [(k, x.uzenet) for k, x in r.items() if x.allapot == doctor.HIBA]
        self.assertEqual(hibak, [])
        self.assertEqual({x.osztaly for x in r.values()}, {"termek"})
        self.assertLessEqual(TERMEK_ZOLD_KODOK, set(r), f"hiányzó sor: {sorted(TERMEK_ZOLD_KODOK - set(r))}")

    def test_az_elrendezesbol_valasztja_a_modot(self):
        self.assertEqual(self.t.cfg.elrendezes, "termek")
        self.assertIn("bundle_epites", self.sorok())                            # alapértelmezés: cfg.elrendezes
        self.assertNotIn("gyoker", self.sorok())

    def test_a_forras_checkout_sorai_termekben_nem_keletkeznek(self):
        self.assertEqual(CSAK_HORDOZHATO_KODOK & set(self.sorok()), set())

    def test_kodok_alakja_egyedisege_es_a_javitas_azonositok(self):
        for x in self.sorok().values():
            self.assertRegex(x.kod, VAN_KOD)
            self.assertIn(x.osztaly, ("termek", "fejleszto"))
            self.assertTrue(x.javitas is None or x.javitas in doctor.JAVITASOK, x)
            self.assertIn(x.allapot, (doctor.OK, doctor.HIBA, doctor.INFO, doctor.FIGYELEM))

    def test_a_python_sor_termekben_nem_olvassa_a_venv_et(self):
        venv = self.t.root / "runtime" / "venv"
        venv.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /Library/Frameworks/Python.framework/Versions/3.14/bin\n", encoding="utf-8")
        self.assertEqual(self.sorok()["python"].allapot, doctor.OK)             # hordozhatóban ez HIBA volna
        self.assertEqual(self.sorok(python=Path("/usr/bin/python3"))["python"].allapot, doctor.HIBA)

    def test_runtime_sor_a_csomagolt_pythont_es_nodeot_varja(self):
        self.assertEqual(self.sorok()["runtime"].allapot, doctor.OK)
        (self.t.root / "runtime" / "node" / "bin" / "node").unlink()
        r = self.sorok()["runtime"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("node", r.uzenet)

    def test_cpp_eszkoztar_termekben_opcionalis(self):
        self.assertEqual(self.sorok()["cpp_eszkoztar"].allapot, doctor.INFO)
        llvm, sdk = self.t.cfg.path("llvm"), self.t.cfg.path("sdk")
        for n in ("clang++", "clang-format", "ld64.lld"):
            (llvm / "bin").mkdir(parents=True, exist_ok=True)
            (llvm / "bin" / n).write_text("#!/bin/sh\n", encoding="utf-8")
            (llvm / "bin" / n).chmod(0o755)
        (sdk / "usr" / "include").mkdir(parents=True)
        self.assertEqual(self.sorok()["cpp_eszkoztar"].allapot, doctor.OK)


class CsomagTeszt(TermekAlap):
    """§6 „root → csomag-épség (`epites.json`) és `bundle_athelyezett`”."""

    def test_jegyzek_nelkul_hianyos_csomag_hiba(self):
        (self.t.root / "app" / "dist" / "epites.json").unlink()
        r = self.sorok()["bundle_hianyos"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("epites.json", r.uzenet)

    def test_hianyzo_felulet_hiba(self):
        (self.t.root / "app" / "dist" / "index.html").unlink()
        self.assertIn("index.html", self.sorok()["bundle_hianyos"].uzenet)

    def test_ervenytelen_jegyzek_hiba(self):
        (self.t.root.parent / "epites.json").write_text("{nem json", encoding="utf-8")
        self.assertEqual(self.sorok()["bundle_hianyos"].allapot, doctor.HIBA)
        (self.t.root.parent / "epites.json").write_text(json.dumps({"verzio": 2}), encoding="utf-8")
        self.assertEqual(self.sorok()["bundle_hianyos"].allapot, doctor.HIBA)

    def test_a_build_utan_modositott_kod_hiba(self):
        (self.t.root / "core" / "x.py").write_text("# módosítva\n", encoding="utf-8")
        r = self.sorok()["bundle_modositott"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertNotIn("bundle_epites", self.sorok())

    def test_a_bytecode_es_a_rejtett_fajl_nem_szamit(self):
        (self.t.root / "core" / "__pycache__").mkdir()
        (self.t.root / "core" / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"\0")
        (self.t.root / "core" / ".DS_Store").write_bytes(b"\0")
        self.assertEqual(self.sorok()["bundle_epites"].allapot, doctor.OK)

    def test_app_translocation(self):
        t = termek_epit(self.tmp / "AppTranslocation" / "u" / "d")
        with mock.patch.object(doctor, "_codesign", return_value=(0, "")):
            e = doctor.ellenoriz(t.cfg, {"HF_HUB_OFFLINE": "1"}, t.home, t.python)
        r = {x.kod: x for x in e}["bundle_athelyezett"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("Alkalmazások", r.uzenet)
        self.assertNotIn("bundle_athelyezett", self.sorok())

    def test_az_alairas_ellenorzese_a_csomagra_megy(self):
        with mock.patch.object(doctor, "_codesign", return_value=(1, "a bundle módosult")) as c:
            r = self.sorok()["manifold_app"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("a bundle módosult", r.uzenet)
        self.assertEqual(c.call_args.args[0], self.tmp / "X.app")


class IrasKodbaTeszt(TermekAlap):
    """I1: semmi írható nem oldódik fel a csak olvasható kódfa alá (a `config.load` megtagadja; a doctor újra ellenőrzi)."""

    def test_rendben(self):
        self.assertEqual(self.sorok()["iras_a_kodba"].allapot, doctor.OK)

    def test_kodfaba_mutato_iras_hiba(self):
        cfg = config.Config(self.t.root, self.t.cfg.data, {**self.t.env, "MOS_TMP": str(self.t.root / "core" / "tmp")})
        r = self.sorok(cfg)["iras_a_kodba"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("tmp=", r.uzenet)

    def test_symlinken_at_a_kodfaba_mutato_iras_is_hiba(self):
        os.symlink(self.t.root / "core", self.tmp / "ki")
        cfg = config.Config(self.t.root, self.t.cfg.data, {**self.t.env, "MOS_CACHE": str(self.tmp / "ki" / "cache")})
        self.assertEqual(self.sorok(cfg)["iras_a_kodba"].allapot, doctor.HIBA)

    def test_a_csak_olvasott_kulcsok_a_kodfaban_rendben_vannak(self):
        for k in ("modulok", "runtime", "app_dist", "ffmpeg", "venv"):
            self.assertIn(k, config.CSAK_OLVASOTT)
            self.assertTrue(doctor._alatt(self.t.cfg.path(k), self.t.root), k)      # a csomag része, mégsem I1-sértés
        self.assertEqual(self.sorok()["iras_a_kodba"].allapot, doctor.OK)


class HomeTeszt(TermekAlap):
    """§6: `HOME_NEM_ENGEDETT` mínusz a `Library/Application Support/Manifold` (a telepítési mappa a saját hely)."""

    def test_a_telepitesi_mappa_nem_idegen_iras(self):
        self.assertTrue(self.t.install.is_dir())
        self.assertNotIn("home_irasok", self.sorok())

    def test_a_hej_azonositoju_idegen_fajl_figyelmeztet_a_telepites_nem(self):
        d = self.t.home / "Library" / "Application Support"
        (d / f"{config.BUNDLE_ID}.sqlite").write_text("", encoding="utf-8")
        r = self.sorok()["home_irasok"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn(f"{config.BUNDLE_ID}.sqlite", r.uzenet)
        self.assertNotIn("Application Support/Manifold", r.uzenet)

    def test_a_telepitesi_mappa_a_megengedett_kivetel_szovegeben(self):
        pref = self.t.home / "Library" / "Preferences"
        pref.mkdir(parents=True)
        (pref / f"{config.BUNDLE_ID}.plist").write_text("", encoding="utf-8")
        r = self.sorok()["home_irasok"]
        self.assertEqual(r.allapot, doctor.INFO)
        self.assertIn("Application Support/Manifold", r.uzenet)


class KotetTeszt(TermekAlap):
    """§6 volume rule: `{var}`, `{tmp}`, `{fuzet_bejovo}`, `{video_bejovo}`, `{staging}` a vault kötetén; fájlrendszer-sorok."""

    def test_azonos_kotet_rendben(self):
        self.assertEqual(self.sorok()["kotet"].allapot, doctor.OK)

    def test_kulon_kotet_hiba_megnevezi_a_kulcsot(self):
        for kulcs in ("var", "tmp", "fuzet_bejovo", "video_bejovo", "staging"):
            with self.subTest(kulcs=kulcs):
                ut = self.t.cfg.path(kulcs)
                with mock.patch.object(doctor, "_eszkoz", side_effect=lambda p, ut=ut: 8 if Path(p) == ut else 7):
                    r = self.sorok()["kotet"]
                self.assertEqual(r.allapot, doctor.HIBA)
                self.assertIn(f"{kulcs} (", r.uzenet)

    def test_a_kotet_az_elso_letezo_osre_meri_a_meg_nem_letezo_utat(self):
        self.assertFalse(self.t.cfg.path("video_bejovo").exists())
        self.assertEqual(doctor._eszkoz(self.t.cfg.path("video_bejovo")), os.stat(self.t.var).st_dev)

    def test_helyi_apfs(self):
        r = self.sorok()["kotet_fajlrendszer"]
        self.assertEqual((r.allapot, r.osztaly), (doctor.OK, "termek"))

    def test_nem_apfs_figyelem(self):
        with mock.patch.object(doctor, "_fajlrendszer", return_value=("exfat", True)):
            r = self.sorok()["kotet_nem_apfs"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("exfat", r.uzenet)

    def test_halozati_kotet_hiba(self):
        with mock.patch.object(doctor, "_fajlrendszer", return_value=("smbfs", False)):
            r = self.sorok()["kotet_halozati"]
        self.assertEqual(r.allapot, doctor.HIBA)

    def test_ismeretlen_fajlrendszer_info(self):
        with mock.patch.object(doctor, "_fajlrendszer", return_value=None):
            self.assertEqual(self.sorok()["kotet_fajlrendszer"].allapot, doctor.INFO)


class ValodiStatfsTeszt(unittest.TestCase):
    @unittest.skipUnless(os.uname().sysname == "Darwin", "[indokolt] a statfs-szerkezet macOS-es")
    def test_a_tmp_kotete_helyi_es_van_neve(self):
        with tmpdir() as t:
            fs = doctor._fajlrendszer(Path(t) / "meg-nem-letezo" / "x")
        self.assertIsNotNone(fs)
        self.assertRegex(fs[0], r"^[a-z0-9]+$")
        self.assertTrue(fs[1])


class SzinkronTeszt(TermekAlap):
    def test_szinkron_fajtak_az_utbol(self):
        for ut, fajta in (("/Users/x/Library/Mobile Documents/com~apple~CloudDocs/V", "icloud"),
                          ("/Users/x/Library/CloudStorage/Dropbox/V", "dropbox"),
                          ("/Users/x/Library/CloudStorage/OneDrive-Personal/V", "cloudstorage"),
                          ("/Users/x/Dropbox/V", "dropbox"), ("/Users/x/Dropbox (Personal)/V", "dropbox"),
                          ("/Users/x/Documents/V", None)):
            self.assertEqual(doctor._szinkron_fajta(Path(ut)), fajta, ut)

    def test_a_dropbox_jelolo_is_szamit(self):
        (self.tmp / "szinkron").mkdir()
        (self.tmp / "szinkron" / ".dropbox").write_text("", encoding="utf-8")
        self.assertEqual(doctor._szinkron_fajta(self.tmp / "szinkron" / "v"), "dropbox")

    def test_nem_szinkronizalt_mappanal_nincs_sor(self):
        self.assertNotIn("szinkron_mappa", self.sorok())

    def test_szinkronizalt_vault_belso_allapottal_figyelem(self):
        t = termek_epit(self.tmp / "a", vault=self.tmp / "a" / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "V")
        self.assertTrue(str(t.var).startswith(str(t.vault)))
        e = {x.kod: x for x in doctor.ellenoriz(t.cfg, {"HF_HUB_OFFLINE": "1"}, t.home, t.python)}
        self.assertEqual(e["szinkron_mappa"].allapot, doctor.FIGYELEM)
        self.assertIn("icloud", e["szinkron_mappa"].uzenet)

    def test_szinkronizalt_vault_telepitesi_allapottal_info(self):
        v = self.tmp / "b" / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "V"
        reg = {"formatum": 1, "utolso": ID, "munkaterek": {ID: {"id": ID, "vault": str(v), "kanonikus": str(v),
                                                                   "allapot": "telepites", "nev": "t"}}}
        t = termek_epit(self.tmp / "b", vault=v, regiszter=reg)
        self.assertFalse(str(t.var).startswith(str(t.vault)))
        e = {x.kod: x for x in doctor.ellenoriz(t.cfg, {"HF_HUB_OFFLINE": "1"}, t.home, t.python)}
        self.assertEqual(e["szinkron_mappa"].allapot, doctor.INFO)


class MunkaterTeszt(TermekAlap):
    def test_rendben(self):
        r = self.sorok()
        self.assertEqual(r["workspace_toml"].allapot, doctor.OK)
        self.assertEqual(r["workspace_formatum"].allapot, doctor.OK)

    def test_hibas_toml_hiba(self):
        self.ws_toml("[workspace\nid = ")
        r = self.sorok()["workspace_toml"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertNotIn("workspace_formatum", self.sorok())

    def test_hianyzo_vagy_hibas_id_hiba(self):
        for toml in ('[workspace]\nnev = "x"\n', '[workspace]\nid = "nem-hexa"\n', '[workspace]\nid = "' + ID.upper() + '"\n'):
            self.ws_toml(toml)
            self.assertEqual(self.sorok()["workspace_toml"].allapot, doctor.HIBA, toml)

    def test_a_core_azonositojatol_eltero_id_hiba(self):
        self.ws_toml(f'[workspace]\nid = "{MAS_ID}"\n')
        r = self.sorok()["workspace_toml"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("eltér", r.uzenet)

    def test_nem_egesz_formatum_hiba(self):
        self.ws_toml(f'[workspace]\nid = "{ID}"\nformatum = "egy"\n')
        self.assertEqual(self.sorok()["workspace_toml"].allapot, doctor.HIBA)
        self.ws_toml(f'[workspace]\nid = "{ID}"\nformatum = true\n')
        self.assertEqual(self.sorok()["workspace_toml"].allapot, doctor.HIBA)

    def test_ujabb_formatum_hiba(self):
        fm, fm_max = doctor._formatumok()
        self.ws_toml(f'[workspace]\nid = "{ID}"\nformatum = {fm_max + 1}\nolvaso_min = {fm_max + 1}\n')
        r = self.sorok()["workspace_ujabb"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertNotIn("workspace_formatum", self.sorok())

    def test_regebbi_formatum_migracio_esedekes(self):
        fm, _ = doctor._formatumok()
        self.ws_toml(f'[workspace]\nid = "{ID}"\nformatum = {fm - 1}\nolvaso_min = 1\n')
        r = self.sorok()["workspace_migracio"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)

    def test_a_formatumok_a_workspace_modulbol_jonnek(self):
        from core import workspace
        self.assertEqual(doctor._formatumok(), (workspace.FORMATUM, workspace.FORMATUM_MAX))

    def test_workspace_toml_nelkuli_munkater(self):
        """A `config.load` termékben megtagadja (`nem_workspace`); a doctor (`munkater=False`) nem omlik össze, és jelzi."""
        ures = self.tmp / "ures"
        (ures / ".obsidian").mkdir(parents=True)
        with self.assertRaises(config.ConfigError) as ctx:
            config.load({**self.t.env, "MOS_VAULT": str(ures)})
        self.assertEqual(ctx.exception.kod, "nem_workspace")
        cfg = config.load({**self.t.env, "MOS_VAULT": str(ures)}, munkater=False)
        r = self.sorok(cfg)
        self.assertEqual(r["nincs_workspace"].allapot, doctor.HIBA)
        self.assertNotIn("vault", r)                                            # a vault-sorok a munkatér nélkül kimaradnak
        self.assertIn("bundle_epites", r)                                       # a gépszintű sorok futnak
        self.assertIn("telepites_irhato", r)

    def test_felbeszakadt_letrehozas_jelzese(self):
        (self.t.vault / ".manifold" / "workspace.toml").unlink()
        (self.t.var / "letrehozas.json").write_text(json.dumps({"id": ID}), encoding="utf-8")
        cfg = config.Config(self.t.root, self.t.cfg.data, {**self.t.env, "MOS_WORKSPACE_ID": ID})
        r = self.sorok(cfg)["workspace_toml"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("félbeszakadt", r.uzenet)

    def test_nincs_vault_termekben_info(self):
        env = {k: v for k, v in self.t.env.items() if k != "MOS_VAULT"}
        cfg = config.load(env)
        r = self.sorok(cfg)
        self.assertEqual(r["nincs_vault"].allapot, doctor.INFO)
        self.assertEqual(r["nincs_vault"].osztaly, "termek")
        self.assertIn("bundle_epites", r)
        self.assertNotIn("pillanatkep_vault", r)


class RegiszterTeszt(TermekAlap):
    def reg(self, munkaterek: dict) -> None:
        (self.t.install / "workspaces.json").write_text(json.dumps({"formatum": 1, "utolso": ID, "munkaterek": munkaterek}),
                                                        encoding="utf-8")

    def sajat(self, **kw) -> dict:
        return {"id": ID, "vault": str(self.t.vault), "kanonikus": str(self.t.vault), "allapot": "vault", "nev": "Teszt", **kw}

    def test_nincs_regiszter_info(self):
        r = self.sorok()["regiszter"]
        self.assertEqual(r.allapot, doctor.INFO)

    def test_regisztralt_munkater_rendben(self):
        self.reg({ID: self.sajat()})
        self.assertEqual(self.sorok()["regiszter"].allapot, doctor.OK)
        self.assertNotIn("regiszter_ervenytelen_ut", self.sorok())

    def test_nem_regisztralt_munkater_figyelem(self):
        self.reg({})
        r = self.sorok()["regiszter"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("nincs a regiszterben", r.uzenet)

    def test_mozgatott_vault_figyelem(self):
        elozo = self.tmp / "regi-hely"
        elozo.mkdir()
        self.reg({ID: self.sajat(vault=str(elozo), kanonikus=str(elozo))})
        r = self.sorok()["regiszter"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("mozgatva vagy másolva", r.uzenet)

    def test_olvashatatlan_regiszter_figyelem_nem_hiba(self):
        (self.t.install / "workspaces.json").write_text("{nem json", encoding="utf-8")
        r = self.sorok()["regiszter"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        (self.t.install / "workspaces.json").write_text(json.dumps({"munkaterek": []}), encoding="utf-8")
        self.assertEqual(self.sorok()["regiszter"].allapot, doctor.FIGYELEM)

    def test_ervenytelen_ut_javitassal(self):
        self.reg({ID: self.sajat(), MAS_ID: {"id": MAS_ID, "vault": str(self.tmp / "torolt"), "nev": "Régi"}})
        r = self.sorok()["regiszter_ervenytelen_ut"]
        self.assertEqual((r.allapot, r.javitas), (doctor.FIGYELEM, "regiszter_takarit"))
        self.assertIn("Régi", r.uzenet)
        self.assertIn(r.javitas, doctor.JAVITASOK)

    def test_lecsatolt_kotet_nem_ervenytelen(self):
        self.reg({ID: self.sajat(), MAS_ID: {"id": MAS_ID, "vault": "/Volumes/NincsIlyenKotet-9f1c/v", "nev": "Külső"}})
        self.assertNotIn("regiszter_ervenytelen_ut", self.sorok())

    def test_bejegyzes_ut_nelkul_ervenytelen(self):
        self.reg({ID: self.sajat(), MAS_ID: {"id": MAS_ID, "nev": "Útnélküli"}})
        self.assertIn("Útnélküli", self.sorok()["regiszter_ervenytelen_ut"].uzenet)

    def test_a_doctor_nem_ir_a_regiszterbe(self):
        self.reg({ID: self.sajat(), MAS_ID: {"id": MAS_ID, "vault": str(self.tmp / "torolt")}})
        elotte = (self.t.install / "workspaces.json").read_bytes()
        self.sorok()
        self.assertEqual((self.t.install / "workspaces.json").read_bytes(), elotte)


class PillanatkepTeszt(TermekAlap):
    def test_worktree_es_exclude_rendben(self):
        self.tar()
        r = self.sorok()
        self.assertEqual(r["pillanatkep_vault"].allapot, doctor.OK, r["pillanatkep_vault"].uzenet)
        self.assertEqual(r["manifold_kizarva"].allapot, doctor.OK)

    def test_eltero_core_worktree_hiba(self):
        repo = self.tar()
        repo.git("config", "core.worktree", str(self.tmp / "mas-vault"))
        r = self.sorok()["pillanatkep_vault"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("core.worktree", r.uzenet)

    def test_a_manifold_mappa_kimaradt_az_exclude_bol_hiba(self):
        repo = self.tar()
        ut = repo.git_dir / "info" / "exclude"
        ut.write_text(ut.read_text(encoding="utf-8").replace(".manifold/\n", ""), encoding="utf-8")
        r = self.sorok()["manifold_kizarva"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn(".manifold/", r.uzenet)

    def test_hianyzo_tarolo_hiba(self):
        r = self.sorok()["pillanatkep_vault"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertNotIn("manifold_kizarva", self.sorok())


class ElutasitottTeszt(TermekAlap):
    def test_nincs_elutasitott_kulcs(self):
        self.assertEqual(self.sorok()["konfig_kulcsok"].allapot, doctor.OK)

    def test_a_ellenseges_workspace_toml_kulcsai_latszanak(self):
        self.ws_toml(f'[workspace]\nid = "{ID}"\n[homokozo]\nengedelyez = true\n[utak]\nvar = "/tmp/evil"\n[router]\nx = 1\n')
        cfg = config.load(self.t.env)
        self.assertTrue(cfg.elutasitott)
        r = self.sorok(cfg)["workspace_kulcs_tiltott"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("homokozo", r.uzenet)
        self.assertNotIn("konfig_kulcsok", self.sorok(cfg))
        self.assertEqual(cfg.path("var"), self.t.var)                           # és tényleg nem érvényesültek


class HelyTeszt(TermekAlap):
    def test_szabad_hely_kuszobok(self):
        for szabad, allapot in ((200 << 30, doctor.OK), (doctor.MIN_SZABAD_FIGYELEM - 1, doctor.FIGYELEM),
                                (doctor.MIN_SZABAD_HIBA - 1, doctor.HIBA)):
            with self.subTest(szabad=szabad), mock.patch.object(doctor, "_szabad_bajt", return_value=szabad):
                self.assertEqual(self.sorok()["szabad_hely"].allapot, allapot)

    def test_a_rosszabb_kotet_dont(self):
        with mock.patch.object(doctor, "_szabad_bajt", side_effect=lambda p: 200 << 30 if Path(p) == self.t.vault else 1 << 20):
            r = self.sorok()["szabad_hely"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("telepítés:", r.uzenet)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "[indokolt] root mellett minden írható")
    def test_nem_irhato_telepites_hiba(self):
        os.chmod(self.t.install, 0o500)
        self.addCleanup(os.chmod, self.t.install, 0o700)
        r = self.sorok()["telepites_irhato"]
        self.assertEqual(r.allapot, doctor.HIBA)

    def test_meg_nem_letezo_telepites_a_szulo_irhatosagan_mulik(self):
        t = termek_epit(self.tmp / "m")
        import shutil
        shutil.rmtree(t.install)
        e = {x.kod: x for x in doctor.ellenoriz(config.load(t.env), {"HF_HUB_OFFLINE": "1"}, t.home, t.python)}
        self.assertEqual(e["telepites_irhato"].allapot, doctor.OK)
        self.assertIn("létrehozza", e["telepites_irhato"].uzenet)

    def test_a_zarak_a_telepites_alatt_vannak(self):
        self.assertEqual(self.sorok()["zar_helye"].allapot, doctor.OK)

    def test_a_vault_allapota_alatt_oldodo_zar_hiba(self):
        cfg = config.Config(self.t.root, self.t.cfg.data, {**self.t.env, "MOS_INSTALL_RUN": str(self.t.var / "run")})
        r = self.sorok(cfg)["zar_helye"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("install_run", r.uzenet)

    def test_a_modellzar_a_telepites_alatt_kell_legyen_a_felulbiralt_nem_hiba(self):
        data = {**self.t.cfg.data, "modellgazda": {**self.t.cfg.data["modellgazda"], "zar": str(self.tmp / "kozos" / "modell.lock")}}
        cfg = config.Config(self.t.root, data, self.t.env)
        r = self.sorok(cfg)["zar_helye"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("modellgazda.zar", r.uzenet)
        e = {"MANIFOLD_MODELL_ZAR": str(self.tmp / "kozos" / "modell.lock")}      # a környezeti felülírás szándékos: nem hiba
        self.assertEqual(self.sorok(cfg, env=e)["zar_helye"].allapot, doctor.OK)

    def test_elakadt_worker_pid_javitassal(self):
        run = self.t.install / "run"
        (run / "worker.pid").write_text(f"{halott_pid()} 4321 titok\n", encoding="utf-8")
        r = self.sorok()["zar_elavult"]
        self.assertEqual((r.allapot, r.javitas), (doctor.FIGYELEM, "zar_takarit"))

    def test_foglalt_worker_zar_mellett_nincs_javitas(self):
        run = self.t.install / "run"
        (run / "worker.pid").write_text(f"{halott_pid()} 4321 titok\n", encoding="utf-8")
        with open(run / "worker.lock", "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.sorok()["zar_elavult"]
        self.assertEqual((r.allapot, r.javitas), (doctor.FIGYELEM, None))

    def test_eleo_worker_pid_nem_elavult(self):
        (self.t.install / "run" / "worker.pid").write_text(f"{os.getpid()} 4321 titok\n", encoding="utf-8")
        self.assertNotIn("zar_elavult", self.sorok())

    def test_a_core_zar_maradeka_halott_pidvel_a_rendes_allapot(self):
        run = self.t.var / "run"
        (run / "core.lock").write_text(f"pid {halott_pid()} · {self.t.vault}", encoding="utf-8")
        self.assertNotIn("zar_elavult", self.sorok())
        self.assertNotIn("core", self.sorok())                                  # szabad zár: a `core` sor sem jelez

    def test_foglalt_core_zar_info(self):
        run = self.t.var / "run"
        with open(run / "core.lock", "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fh.write(f"pid {os.getpid()} · {self.t.vault}")
            fh.flush()
            self.assertEqual(self.sorok()["core"].allapot, doctor.INFO)

    def test_pid_szam_a_regi_es_az_uj_zarformatumbol(self):
        self.assertEqual(doctor._pid_szam("pid 123 · /v"), 123)
        self.assertEqual(doctor._pid_szam(f"pid 77 · {ID} · /v"), 77)
        self.assertEqual(doctor._pid_szam("456 7890 titok"), 456)
        self.assertIsNone(doctor._pid_szam("semmi"))


class MentesTeszt(TermekAlap):
    def jelolo(self, munkater_id, vault=None) -> Path:
        b = self.t.cfg.path("backup")
        b.mkdir(parents=True, exist_ok=True)
        (b / ".manifold-mentes.json").write_text(json.dumps(
            {"formatum": 1, "munkater_id": munkater_id, "vault": vault or str(self.t.vault), "letrehozva": "2026-10-16T10:00:00+02:00"}),
            encoding="utf-8")
        return b

    def test_a_mentes_munkaterenkent_kulon_mappa(self):
        self.assertEqual(self.t.cfg.path("backup"), self.t.install / "backups" / ID)

    def test_sajat_jelolo_rendben(self):
        self.jelolo(ID)
        self.assertEqual(self.sorok()["mentes_tulajdonos"].allapot, doctor.OK)

    def test_idegen_jelolo_figyelem(self):
        self.jelolo(MAS_ID, vault=str(self.tmp / "masik"))
        r = self.sorok()["mentes_idegen_mappa"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("másik munkatér", r.uzenet)
        self.assertNotIn("mentes_tulajdonos", self.sorok())

    def test_olvashatatlan_jelolo_idegennek_szamit(self):
        b = self.jelolo(ID)
        (b / ".manifold-mentes.json").write_text("{nem json", encoding="utf-8")
        self.assertIn("mentes_idegen_mappa", self.sorok())

    def test_jelolo_nelkuli_nem_ures_mappa_orokolt(self):
        b = self.t.cfg.path("backup")
        b.mkdir(parents=True)
        (b / "vault-20260101.bundle").write_bytes(b"x")
        r = self.sorok()["mentes_orokolt_mappa"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("külön mappát", r.uzenet)

    def test_ures_mappa_nem_jelez(self):
        self.t.cfg.path("backup").mkdir(parents=True)
        (self.t.cfg.path("backup") / ".DS_Store").write_bytes(b"x")
        r = self.sorok()
        for k in ("mentes_tulajdonos", "mentes_idegen_mappa", "mentes_orokolt_mappa"):
            self.assertNotIn(k, r)

    def test_azonos_lemez_info(self):
        r = self.sorok()["mentes_azonos_lemez"]
        self.assertEqual(r.allapot, doctor.INFO)
        with mock.patch.object(doctor, "_eszkoz", side_effect=lambda p: 8 if "backups" in Path(p).parts else 7):
            self.assertNotIn("mentes_azonos_lemez", self.sorok())

    def test_a_vaultban_allo_mentesi_mappa_hiba(self):
        cfg = config.load({**self.t.env, "MOS_BACKUP": str(self.t.vault / "Mentés")})
        r = self.sorok(cfg)["mentes_a_vaultban"]
        self.assertEqual(r.allapot, doctor.HIBA)

    def test_a_mentes_frissessege(self):
        repo = self.tar()
        (self.t.vault / "jegyzet.md").write_text("# 1\n", encoding="utf-8")
        self.assertIsNotNone(repo.commit("teszt"))
        r = self.sorok()["mentes"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn("még nincs mentés", r.uzenet)
        mentes.ment(self.t.cfg, allapot=False)
        r = self.sorok()["mentes"]
        self.assertEqual(r.allapot, doctor.OK, r.uzenet)
        self.assertEqual(self.sorok()["mentes_tulajdonos"].allapot, doctor.OK)    # az első író beírta a jelölőt
        (self.t.vault / "jegyzet.md").write_text("# 2\n", encoding="utf-8")
        repo.commit("teszt 2")
        self.assertEqual(self.sorok()["mentes"].allapot, doctor.FIGYELEM)


class SemaTeszt(TermekAlap):
    """A séma feloldási lánca termékben: munkatér `schema.json` → preset sémája → szállított alap."""

    def test_az_alap_a_lanc_vege(self):
        r = self.sorok()["vault_sema"]
        self.assertEqual(r.allapot, doctor.OK)
        self.assertIn("schema-default.json", r.uzenet)

    def test_a_munkater_fajlja_nyer_es_ervenytelenen_hiba(self):
        (self.t.vault / ".manifold" / "schema.json").write_text("{nem json", encoding="utf-8")
        r = self.sorok()["vault_sema"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)               # a hibás munkatér-séma kimarad, a szállított alap él
        self.assertIn("schema-default.json", r.uzenet)
        (self.t.vault / ".manifold" / "schema.json").write_text(json.dumps({"mezosorrend": ["a", "b"]}), encoding="utf-8")
        r = self.sorok()["vault_sema"]
        self.assertEqual(r.allapot, doctor.OK)
        self.assertIn("schema.json: 2 mező", r.uzenet)

    def test_a_megnevezett_preset_semaja_az_alap_elott(self):
        (self.t.root / "config" / "presets").mkdir(exist_ok=True)
        (self.t.root / "config" / "presets" / "proba.toml").write_text("", encoding="utf-8")
        (self.t.root / "config" / "presets" / "proba.schema.json").write_text(json.dumps({"mezosorrend": ["x"] * 3}), encoding="utf-8")
        self.ws_toml(f'[workspace]\nid = "{ID}"\npresetek = ["proba"]\n')
        r = self.sorok(config.load(self.t.env))["vault_sema"]
        self.assertIn("proba.schema.json: 3 mező", r.uzenet)

    def test_nincs_sema_csak_bekapcsolt_ellenorzesnel_hiba(self):
        (self.t.root / "config" / "schema-default.json").unlink()
        self.assertEqual(self.sorok()["vault_sema"].allapot, doctor.INFO)          # [sema] mod = ki
        self.ws_toml(f'[workspace]\nid = "{ID}"\n[sema]\nmod = "szigoru"\n')
        cfg = config.load(self.t.env)
        self.assertEqual(cfg.section("sema")["mod"], "szigoru")
        r = self.sorok(cfg)["vault_sema"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("schema-default.json", r.uzenet)


class SpotlightTeszt(TermekAlap):
    def test_a_telepitesi_mappa_is_kizart(self):
        r = self.sorok()["spotlight"]
        self.assertEqual(r.allapot, doctor.OK)
        self.assertIn("telepítési mappa", r.uzenet)
        (self.t.install / ".metadata_never_index").unlink()
        r = self.sorok()["spotlight"]
        self.assertEqual(r.allapot, doctor.FIGYELEM)
        self.assertIn(str(self.t.install), r.uzenet)


class HordozhatoTeszt(unittest.TestCase):
    """A közös szerződés a hordozható módban: kódok, osztályok, és az új „vault nincs megadva” sor."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name)
        self.home = Path(self._t.name) / "home"

    def sorok(self, root=None, **kw) -> dict:
        root = root or self.root
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        e = doctor.ellenoriz(cfg, {"HF_HUB_OFFLINE": "1"}, self.home, root / "runtime" / "python" / "bin" / "python3", **kw)
        kodok = [x.kod for x in e]
        self.assertEqual(len(kodok), len(set(kodok)), sorted(k for k in set(kodok) if kodok.count(k) > 1))
        return {x.kod: x for x in e}

    def test_hordozhato_alapertelmezes_es_kodok(self):
        r = self.sorok()
        self.assertNotIn("bundle_epites", r)
        for k in ("gyoker", "kotet", "var_symlink", "python", "runtime", "git", "offline", "vault_sema"):
            self.assertIn(k, r)
        for x in r.values():
            self.assertRegex(x.kod, VAN_KOD)
            self.assertIn(x.osztaly, ("termek", "fejleszto"))

    def test_osztalyok_a_forras_checkout_sorai_fejlesztoi(self):
        r = self.sorok()
        for k in ("gyoker", "var_symlink", "python", "runtime", "lock"):
            self.assertEqual(r[k].osztaly, "fejleszto", k)
        for k in ("git", "offline", "vault", "spotlight", "vault_sema"):
            self.assertEqual(r[k].osztaly, "termek", k)

    def test_nincs_vault_hiba_a_portable_init_parancsot_nevezi(self):
        root = alg_gyoker(self._t.name + "/b", vault=False)
        r = self.sorok(root)["nincs_vault"]
        self.assertEqual(r.allapot, doctor.HIBA)
        self.assertIn("portable init", r.uzenet)

    def test_vault_nelkul_a_vaultfuggo_sorok_kimaradnak_de_nem_omlik_ossze(self):
        r = self.sorok(alg_gyoker(self._t.name + "/b", vault=False))
        for k in ("pillanatkep_vault", "manifold_kizarva", "workspace_toml", "kotet_fajlrendszer"):
            self.assertNotIn(k, r)
        self.assertIn("git", r)

    def test_a_hordozhato_nem_hoz_letre_workspace_sort(self):
        r = self.sorok()
        self.assertNotIn("workspace_toml", r)                                   # a réteg hordozhatóban csak, ha létezik
        self.assertNotIn("regiszter", r)

    def test_ha_letezik_a_workspace_toml_hordozhatoban_is_ellenorzi(self):
        v = self.root.parent / "Manifold"
        (v / ".manifold").mkdir()
        (v / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{ID}"\n', encoding="utf-8")
        r = self.sorok()
        self.assertEqual(r["workspace_toml"].allapot, doctor.OK)

    def test_explicit_hordozhato_szabaly_termek_cfg_en(self):
        t = termek_epit(Path(self._t.name) / "p")
        with mock.patch.object(doctor, "_codesign", return_value=(0, "")), mock.patch.object(doctor, "_alairas"):
            e = {x.kod: x for x in doctor.ellenoriz(t.cfg, {"HF_HUB_OFFLINE": "1"}, t.home, t.python, termek=False)}
        self.assertEqual(e["gyoker"].allapot, doctor.HIBA)                      # a bundle-ben nincs bin/mos
        self.assertNotIn("bundle_epites", e)
        self.assertEqual(e["gyoker"].osztaly, "fejleszto")


class KodTablaTeszt(unittest.TestCase):
    """A kódok nem változhatnak, ha a sor szövege igen: a rögzített nevek tábláját és a dinamikus nevek képzését lerögzítjük."""

    def test_a_rogzitett_nevek_kodjai(self):
        vart = {
            "gyökér": "gyoker", "kötet": "kotet", "var symlink": "var_symlink", "vault": "vault",
            "vault .gitattributes": "vault_gitattributes", "vault ideiglenes fájlok": "vault_ideiglenes", "python": "python",
            "~/Applications, ~/.cache": "sajat_utak", "vault-séma": "vault_sema", "git": "git", "git függőség": "git_fuggoseg",
            "offline": "offline", "runtime": "runtime", "lock": "lock", "runtime verzió": "runtime_verzio",
            "requirements.in": "requirements_in", "ffmpeg": "ffmpeg", "modell-revízió": "modell_revizio",
            "kalibráció-pillanatkép": "kalibracio_pillanatkep", "Manifold.app": "manifold_app", "aláírás": "alairas",
            "naptár-segéd": "naptar_seged", "naptár-engedély": "naptar_engedely", "home írások": "home_irasok",
            "@napi-rs/canvas": "napi_canvas", "Spotlight": "spotlight", "felület": "felulet", "mentés": "mentes",
            "mentés (kódtár)": "mentes_kodtar", "mentés (állapot)": "mentes_allapot", "mentés hiba": "mentes_hiba", "index": "index",
            "index (félretett)": "index_felretett", "kapu": "kapu", "C++ eszköztár": "cpp_eszkoztar", "C++ linker": "cpp_linker",
            "C++ SDK": "cpp_sdk", "próbaklónok": "probaklonok", "próbaklónok (gépi)": "probaklonok_gepi", "core": "core",
            "összeomlás-horog": "osszeomlas_horog", "pillanatkép bináris": "pillanatkep_binaris",
            "pillanatkép kód (ytdlp)": "pillanatkep_kod_ytdlp"}
        self.assertEqual(doctor._NEV_KOD, vart)
        for nev, kod in vart.items():
            self.assertEqual(doctor._kod_nevbol(nev), kod)

    def test_a_dinamikus_nevek_kodja(self):
        for nev, kod in (("pillanatkép (vault)", "pillanatkep_vault"), ("pillanatkép (ytdlp)", "pillanatkep_ytdlp"),
                         ("pillanatkép bináris (ytdlp)", "pillanatkep_binaris_ytdlp"), ("vault.git", "vault_git"),
                         ("ytdlp.git", "ytdlp_git"), ("mentés (ytdlp)", "mentes_ytdlp"), ("build-felulet", "build_felulet"),
                         ("build-hej", "build_hej"), ("Ékezetes Név!", "ekezetes_nev"), ("???", "sor")):
            self.assertEqual(doctor._kod_nevbol(nev), kod)

    def test_a_javitas_azonositok_rogzitettek(self):
        self.assertEqual(doctor.JAVITASOK, ("regiszter_takarit", "zar_takarit"))

    def test_a_fejlesztoi_kodok_halmaza(self):
        self.assertEqual(doctor.FEJLESZTO_KODOK, {"gyoker", "var_symlink", "python", "sajat_utak", "runtime", "lock", "runtime_verzio",
                                                  "requirements_in", "manifold_app", "alairas", "napi_canvas", "felulet", "kapu",
                                                  "osszeomlas_horog"})


class JsonTeszt(TermekAlap):
    """`python -m core doctor [--json]`: a `main` a kapott környezetből tölt (nem mockolt `config`), a kimenet stabil."""

    def main(self, env: dict, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            rc = doctor.main(list(argv))
        return rc, buf.getvalue()

    def kornyezet(self, **extra) -> dict:
        return {**self.t.env, "HF_HUB_OFFLINE": "1", "PATH": os.environ["PATH"], **extra}

    def fut(self):
        """Az ál-bundle Pythonja: a doctor `python` sora a futó interpreterre néz."""
        return mock.patch.multiple(doctor.sys, executable=str(self.t.python), prefix=str(self.t.root / "runtime" / "python"))

    def test_json_kimenet_alakja(self):
        self.tar()
        with self.fut():
            rc, ki = self.main(self.kornyezet(), "--json")
        j = json.loads(ki)
        self.assertEqual((j["verzio"], j["elrendezes"]), (1, "termek"))
        self.assertEqual(set(j), {"verzio", "elrendezes", "zold", "osszesen", "eredmenyek"})
        self.assertEqual(set(j["osszesen"]), {doctor.OK, doctor.HIBA, doctor.FIGYELEM, doctor.INFO})
        self.assertEqual(sum(j["osszesen"].values()), len(j["eredmenyek"]))
        for e in j["eredmenyek"]:
            self.assertEqual(set(e), {"kod", "allapot", "nev", "uzenet", "osztaly", "javitas"})
            self.assertRegex(e["kod"], VAN_KOD)
        self.assertEqual([e for e in j["eredmenyek"] if e["allapot"] == doctor.HIBA], [])
        self.assertEqual((rc, j["zold"]), (0, True))

    def test_a_kilepesi_kod_a_hibatol_fugg(self):
        self.tar()
        (self.t.root / "core" / "x.py").write_text("# módosítva\n", encoding="utf-8")
        with self.fut():
            rc, ki = self.main(self.kornyezet(), "--json")
        j = json.loads(ki)
        self.assertEqual((rc, j["zold"]), (1, False))
        self.assertIn("bundle_modositott", [e["kod"] for e in j["eredmenyek"] if e["allapot"] == doctor.HIBA])

    def test_a_javitas_azonosito_a_jsonban(self):
        self.tar()
        (self.t.install / "workspaces.json").write_text(json.dumps(
            {"formatum": 1, "utolso": ID, "munkaterek": {MAS_ID: {"id": MAS_ID, "vault": str(self.tmp / "nincs")}}}), encoding="utf-8")
        with self.fut():
            _, ki = self.main(self.kornyezet(), "--json")
        sor = {e["kod"]: e for e in json.loads(ki)["eredmenyek"]}["regiszter_ervenytelen_ut"]
        self.assertEqual(sor["javitas"], "regiszter_takarit")

    def test_szoveges_kimenet_a_javitassal(self):
        self.tar()
        (self.t.install / "workspaces.json").write_text(json.dumps(
            {"formatum": 1, "utolso": ID, "munkaterek": {MAS_ID: {"id": MAS_ID, "vault": str(self.tmp / "nincs")}}}), encoding="utf-8")
        with self.fut():
            rc, ki = self.main(self.kornyezet())
        self.assertIn("[javítás: regiszter_takarit]", ki)
        self.assertIn("✓ ", ki)
        self.assertTrue(ki.rstrip().endswith("A doctor zöld."))
        self.assertEqual(rc, 0)

    def test_hibas_konfiguracio_jsonban_nem_traceback(self):
        rc, ki = self.main(self.kornyezet(MOS_ELRENDEZES="bogus"), "--json")
        j = json.loads(ki)
        self.assertEqual(rc, 1)
        self.assertIsNone(j["elrendezes"])
        self.assertEqual(j["eredmenyek"][0]["kod"], "elrendezes_ismeretlen")
        self.assertEqual(j["eredmenyek"][0]["allapot"], doctor.HIBA)

    def test_munkater_nelkul_a_main_ujraprobal(self):
        ures = self.tmp / "ures"
        (ures / ".obsidian").mkdir(parents=True)
        with self.fut():
            rc, ki = self.main(self.kornyezet(MOS_VAULT=str(ures)), "--json")
        j = json.loads(ki)
        kodok = {e["kod"]: e for e in j["eredmenyek"]}
        self.assertEqual(kodok["nincs_workspace"]["allapot"], doctor.HIBA)
        self.assertIn("bundle_epites", kodok)
        self.assertEqual(rc, 1)

    def test_hordozhato_json(self):
        with tmpdir() as t:
            root = alg_gyoker(t)
            env = {"MOS_ROOT": str(root), "HOME": str(Path(t) / "home"), "HF_HUB_OFFLINE": "1", "PATH": os.environ["PATH"]}
            _, ki = self.main(env, "--json")
        j = json.loads(ki)
        self.assertEqual(j["elrendezes"], "hordozhato")
        kodok = {e["kod"]: e["osztaly"] for e in j["eredmenyek"]}
        self.assertEqual(kodok["gyoker"], "fejleszto")
        self.assertEqual(kodok["git"], "termek")


if __name__ == "__main__":
    unittest.main()
