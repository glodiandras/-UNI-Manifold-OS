"""A megbízhatatlan munkatér (a vault utazik, szinkronizálódik, letölthető) elleni védelmek — az F3 végső javítókör (K3, K5, I7):

- a `.manifold` / `var` / `workspace.toml` szimbolikus link nem követhető (`munkater_symlink`): se olvasás, se írás, se állapot;
- a `workspace.toml` azonosítója a vaulttal utazik: önmagában nem ad regisztrált állapotot, nem vesz át regiszter-bejegyzést és
  mentési mappát, és nem tüntet el idegen állapotmappát;
- az `ID_MINTA` az újsoros értéket nem engedi át;
- a megbízhatatlan TOML mérete, mélysége, a nevek, a vezérlőkarakterek és a reguláris kifejezések korlátozottak;
- a visszavonási kivételek és a `schema.json` érvényesítése, a hibás fájl helyett a lánc következő jelöltje él."""
import json
import os
import re
import unittest
from pathlib import Path

from core import config, doctor, kiserok, regex_biztonsag, snapshot, workspace
from core.tulajdonsagok import Sema
from tests.fresh_install import termek_alap, termek_cfg
from tests.helpers import tmpdir

ID = "0123456789abcdef0123456789abcdef"


def tiszta_vault(v: Path) -> Path:
    (v / ".obsidian").mkdir(parents=True)
    (v / "a.md").write_text("# a\n", encoding="utf-8")
    return v


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.install = self.alap.path("install")

    def munkater(self, nev: str) -> tuple[Path, str]:
        v = tiszta_vault(self.t / nev)
        return v, workspace.letrehoz(v, self.alap)["id"]

    def reg(self) -> dict:
        return workspace.Regiszter(self.install).olvas()


class SzimbolikusLinkTest(Alap):
    def setUp(self):
        super().setUp()
        self.a, self.id_a = self.munkater("A")                                  # az áldozat
        self.d = tiszta_vault(self.t / "D")                                     # a másik vault, amelynek `.manifold`-ja link
        os.symlink(self.a / ".manifold", self.d / ".manifold")
        self.elotte = {p.relative_to(self.a / ".manifold").as_posix(): p.read_bytes()
                       for p in (self.a / ".manifold").rglob("*") if p.is_file() and ".git" not in p.parts}

    def megsem_valtozott_az_aldozat(self):
        most = {p.relative_to(self.a / ".manifold").as_posix(): p.read_bytes()
                for p in (self.a / ".manifold").rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(most, self.elotte)
        self.assertEqual(workspace.azonosit(self.a), self.id_a)

    def test_a_config_load_nem_olvassa_a_linken_at(self):
        with self.assertRaises(config.ConfigError) as e:
            termek_cfg(self.root, self.home, self.d)
        self.assertEqual(e.exception.kod, "munkater_symlink")
        with self.assertRaises(config.ConfigError) as e:                         # munkatér nélküli betöltés (worker, CLI) sem
            config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(self.d)}, munkater=False)
        self.assertEqual(e.exception.kod, "munkater_symlink")

    def test_a_felmeres_tilos_a_letrehozas_nem_ir_a_nyitas_nem_nyit(self):
        f = workspace.felmer(self.d, self.alap)
        self.assertEqual((f.eredmeny, f.akadaly[0]), ("tilos", "munkater_symlink"))
        self.assertIsNone(f.meglevo_id)                                          # a link mögül nem olvasunk azonosítót
        with self.assertRaises(config.ConfigError) as e:
            workspace.letrehoz(self.d, self.alap)
        self.assertEqual(e.exception.kod, "munkater_symlink")
        cfg = termek_cfg(self.root, self.home, self.a)                           # a nyit-hoz érvényes cfg, a vault-útja a link
        cfg.utak["vault"] = self.d
        cfg.utak["workspace"] = self.d / ".manifold"
        with self.assertRaises(config.ConfigError) as e:
            workspace.nyit(cfg)
        self.assertEqual(e.exception.kod, "munkater_symlink")
        self.megsem_valtozott_az_aldozat()

    def test_az_azonosito_atirasa_nem_irja_at_a_link_mogotti_fajlt(self):
        toml = self.d / ".manifold" / "workspace.toml"
        with self.assertRaises(config.ConfigError) as e:
            workspace._uj_id_irasa(toml, self.id_a, "f" * 32)
        self.assertEqual(e.exception.kod, "munkater_symlink")
        with self.assertRaises(config.ConfigError):
            workspace._atomi_ir_nofollow(self.d / ".manifold", "workspace.toml", b"x")
        self.megsem_valtozott_az_aldozat()

    def test_az_eltavolitas_a_linket_viszi_a_kukaba_nem_a_celt_es_a_futo_aldozat_nem_akadalyozza(self):
        import fcntl
        zar = self.a / ".manifold" / "var" / "run" / "core.lock"
        zar.parent.mkdir(parents=True, exist_ok=True)
        with open(zar, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)                                      # az A munkatéren fut egy core
            kukaba = []
            e = workspace.eltavolit(self.d, self.alap, kukaba.append)
        self.assertEqual(kukaba, [self.d / ".manifold"])
        self.assertNotEqual(e["id"], self.id_a)                                  # a link mögötti azonosító nem a D-é
        self.assertIn(self.id_a, self.reg()["munkaterek"])                      # az A bejegyzése megmaradt
        self.assertTrue((self.a / ".manifold" / "workspace.toml").is_file())
        self.assertIsNone(workspace.azonosit(self.d))

    def test_var_es_workspace_toml_link_is_tilos(self):
        b, _ = self.munkater("B")
        celpont = self.t / "kulso-var"
        celpont.mkdir()
        os.rename(b / ".manifold" / "var", self.t / "regi-var")
        os.symlink(celpont, b / ".manifold" / "var")
        with self.assertRaises(config.ConfigError) as e:
            config.munkater_mappa_ellenoriz(b)
        self.assertEqual((e.exception.kod, e.exception.param["ok"]), ("munkater_symlink", "szimbolikus link"))
        os.unlink(b / ".manifold" / "var")
        os.rename(self.t / "regi-var", b / ".manifold" / "var")
        config.munkater_mappa_ellenoriz(b)                                       # rendben
        toml = b / ".manifold" / "workspace.toml"
        tartalom = toml.read_bytes()
        os.rename(toml, self.t / "ws.toml")
        os.symlink(self.t / "ws.toml", toml)
        with self.assertRaises(config.ConfigError):
            config.munkater_mappa_ellenoriz(b)
        os.unlink(toml)
        toml.write_bytes(tartalom)
        for nev in (".gitignore", "README.txt"):
            os.symlink(self.t / "x", b / ".manifold" / f"{nev}.link")
        config.munkater_mappa_ellenoriz(b)                                       # más nevű link nem számít

    def test_a_vault_maga_lehet_link(self):
        link = self.t / "VaultLink"
        os.symlink(self.a, link)
        config.munkater_mappa_ellenoriz(link)                                    # a felhasználó saját elrendezése
        self.assertEqual(workspace.felmer(link, self.alap).akadaly.count("munkater_symlink"), 0)

    def test_a_doctor_jelzi(self):
        cfg = termek_cfg(self.root, self.home, self.a)
        cfg.utak["vault"] = self.d
        cfg.utak["workspace"] = self.d / ".manifold"
        sorok = []
        doctor._munkater_sorok(cfg, True, lambda allapot, nev, uzenet, **kw: sorok.append((allapot, nev, kw.get("kod"))))
        self.assertEqual(sorok, [(doctor.HIBA, "munkatér", "munkater_symlink")])


class AzonositoKotesTest(Alap):
    def test_idegen_vault_nem_kapja_meg_a_regisztralt_szinkron_allapotot(self):
        v = self.home / "Library" / "CloudStorage" / "Felho" / "Jegyzetek"
        tiszta_vault(v)
        id_ = workspace.letrehoz(v, self.alap)["id"]
        self.assertEqual(self.reg()["munkaterek"][id_]["allapot"], "telepites")
        hamis = tiszta_vault(self.t / "Letoltott")
        os.makedirs(hamis / ".manifold")
        (hamis / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{id_}"\n', encoding="utf-8")
        cfg = termek_cfg(self.root, self.home, hamis)
        self.assertEqual(cfg.workspace_id, id_)
        self.assertEqual(cfg.path("var"), hamis / ".manifold" / "var")           # nem az áldozat `{install}/workspaces/<id>/var`-ja
        self.assertEqual(termek_cfg(self.root, self.home, v).path("var"), self.install / "workspaces" / id_ / "var")

    def test_a_regisztralt_hely_eltuntevel_idegen_vault_nem_veszi_at_a_bejegyzest(self):
        a, id_a = self.munkater("A")
        regi_bejegyzes = dict(self.reg()["munkaterek"][id_a])
        a_helye = self.t / "A-athelyezve"
        os.rename(a, a_helye)                                                    # az A pillanatnyilag nincs a régi helyén
        hamis = tiszta_vault(self.t / "Hamis")
        os.makedirs(hamis / ".manifold")
        (hamis / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{id_a}"\nnev = "hamis"\n', encoding="utf-8")
        uzenetek = workspace.nyit(termek_cfg(self.root, self.home, hamis))
        uj = workspace.azonosit(hamis)
        self.assertNotEqual(uj, id_a)                                            # új azonosítót kapott: nem az A áthelyezése
        self.assertIn("nem bizonyítható", uzenetek[0])
        r = self.reg()["munkaterek"]
        self.assertEqual(r[id_a], regi_bejegyzes)                                # az A bejegyzése (és mentési mappája) érintetlen
        self.assertEqual(r[uj]["vault"], str(hamis))
        # az igazi áthelyezett A (azonos `.manifold` inode, azonos kötet) felismerhető
        self.assertEqual(len(workspace.nyit(termek_cfg(self.root, self.home, a_helye))), 1)
        self.assertEqual(self.reg()["munkaterek"][id_a]["vault"], str(a_helye))
        self.assertEqual(workspace.azonosit(a_helye), id_a)

    def test_nem_bizonyitott_athelyezesnel_az_idegen_vault_nem_kapja_meg_a_regisztralt_tortenetet(self):
        felho = self.home / "Library" / "CloudStorage" / "Felho"
        a = tiszta_vault(felho / "A")
        id_a = workspace.letrehoz(a, self.alap)["id"]
        a_var = self.install / "workspaces" / id_a / "var"
        self.assertTrue((a_var / "vault.git").exists())
        os.rename(a, felho / "A-mashol")                                         # a regisztrált hely eltűnt
        hamis = tiszta_vault(felho / "Hamis")
        os.makedirs(hamis / ".manifold")
        (hamis / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{id_a}"\n', encoding="utf-8")
        cfg = termek_cfg(self.root, self.home, hamis)
        self.assertEqual(cfg.path("var"), hamis / ".manifold" / "var")           # a regiszter az A útjához kötött
        workspace.nyit(cfg)
        uj = workspace.azonosit(hamis)
        self.assertNotEqual(uj, id_a)
        self.assertFalse((self.install / "workspaces" / uj / "var" / "vault.git").exists())     # az A története nem klónozódott át
        self.assertTrue((a_var / "vault.git").exists())                                          # és az A állapota érintetlen

    def test_az_eltavolitas_nem_nyul_idegen_allapothoz_es_bejegyzeshez(self):
        a, id_a = self.munkater("A")
        telepes = self.install / "workspaces" / id_a
        telepes.mkdir(parents=True)
        (telepes / "var").mkdir()
        b, id_b = self.munkater("B")
        # B toml-ja az A azonosítóját hordozza (megbízhatatlan fájl)
        toml = b / ".manifold" / "workspace.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace(id_b, id_a), encoding="utf-8")
        kukaba = []
        e = workspace.eltavolit(b, self.alap, kukaba.append)
        self.assertEqual(e["id"], id_b)                                          # a regiszter a vaulthoz kötött azonosítót mondja
        self.assertEqual(kukaba, [b / ".manifold"])                              # az A telepítés alatti mappája nem
        self.assertTrue(telepes.exists())
        self.assertIn(id_a, self.reg()["munkaterek"])
        self.assertNotIn(id_b, self.reg()["munkaterek"])

    def test_id_minta_nem_engedi_at_a_zaro_ujsort(self):
        for rossz in (ID + "\n", ID + " ", "\n" + ID, ID.upper(), ID[:-1]):
            self.assertIsNone(config.ID_MINTA.match(rossz), repr(rossz))
        self.assertTrue(config.ID_MINTA.match(ID))
        self.assertIsNone(config.PRESET_NEV.match("v2-kompat\n"))
        v = tiszta_vault(self.t / "V")
        os.makedirs(v / ".manifold")
        (v / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{ID}\\n"\n', encoding="utf-8")
        cfg = termek_cfg(self.root, self.home, v, MOS_WORKSPACE_ID=ID)
        self.assertEqual(cfg.workspace_id, ID)
        self.assertEqual({k: kod for r, k, kod in cfg.elutasitott if r == "munkater"}, {"workspace.id": "vezerlo_karakter"})
        self.assertIsNone(workspace.azonosit(v))
        (v / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{ID} "\n', encoding="utf-8")
        self.assertEqual({k: kod for r, k, kod in termek_cfg(self.root, self.home, v, MOS_WORKSPACE_ID=ID).elutasitott
                          if r == "munkater"}, {"workspace.id": "id"})
        with self.assertRaises(config.ConfigError) as e:
            termek_cfg(self.root, self.home, v, MOS_WORKSPACE_ID=ID + "\n")
        self.assertEqual(e.exception.kod, "workspace_id_hibas")


class ReteguzenetTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root, self.home, self.alap = termek_alap(self._t.name)

    def hiba(self, **tabla) -> dict[str, str]:
        return dict(config.reteg_ellenoriz("munkater", tabla, self.alap.data, self.root))

    def test_nevek_nem_utak(self):
        for rossz in ("../../", "a/b", "a\\b", ".rejtett", "..", "x{os}", "~", "A" * 65, "Ké"):
            h = self.hiba(vault={"kisero_elotag": rossz})
            self.assertIn("vault.kisero_elotag", h, repr(rossz))
        self.assertEqual(self.hiba(vault={"kisero_elotag": "Gen - "}, kartya={"utotag": " — kártyák"},
                                   osszefoglalas={"utotag": " — összefoglaló"}), {})
        self.assertEqual(self.hiba(kartya={"utotag": "../x"}), {"kartya.utotag": "nev_ervenytelen"})
        self.assertEqual(self.hiba(osszefoglalas={"utotag": ".md"}), {"osszefoglalas.utotag": "ut_pontos_szakasz"})

    def test_vezerlokarakter_minden_szovegben_es_kulcsban(self):
        self.assertEqual(self.hiba(pdf={"tags": {"X": "a\nStatus: done"}}), {"pdf.tags.X": "vezerlo_karakter"})
        self.assertEqual(self.hiba(pdf={"tags": {"X": "a b"}}), {"pdf.tags.X": "vezerlo_karakter"})
        self.assertEqual(self.hiba(pdf={"tags": {"X": "tab\tmehet"}}), {})
        self.assertEqual(self.hiba(video={"kizart_mappak": ["ok", "rossz\r"]}), {"video.kizart_mappak": "vezerlo_karakter"})
        kulcs = list(self.hiba(pdf={"tags": {"A\nB": "x"}}))
        self.assertEqual(len(kulcs), 1)
        self.assertNotIn("\n", kulcs[0])                                         # a jelentésbe sem kerül nyers újsor
        self.assertEqual(self.hiba(workspace={"nev": "két\nsor"}), {"workspace.nev": "vezerlo_karakter"})

    def test_regex_veszelyes_beagyazott_ismetles(self):
        for rossz in ("(a+)+$", "(a*)*", "([A-Z]{1,3})+x", "(.*a){12}", "(?:a|b+)+c"):
            self.assertEqual(self.hiba(video={"tema_minta": rossz}), {"video.tema_minta": "regex_beagyazott_ismetles"}, rossz)
        self.assertEqual(self.hiba(video={"tema_minta": "("}), {"video.tema_minta": "regex"})
        for jo in (r"^([A-Z]{1,3})(\d{2}) - \S.*$", r"^\d{2} - ", r"(foo|bar)+", r"(\d{2}){1,3}"):
            self.assertEqual(self.hiba(video={"tema_minta": jo}), {}, jo)

    def test_a_kalibracios_kapuk_nem_allithatok_a_munkater_retegbol(self):
        for kulcs in ("kalibralt", "kalibracio_min", "kalibracio_elotte_nap", "kalibracio_vissza_nap", "kalibracio_ridge"):
            self.assertEqual(self.hiba(felkeszultseg={kulcs: 0 if kulcs != "kalibralt" else True}),
                             {f"felkeszultseg.{kulcs}": "reteg_tiltott"}, kulcs)
        self.assertEqual(self.hiba(felkeszultseg={"jo": 0.5}), {})               # a súlyok engedettek

    def test_minden_tiltomintanak_van_kulcsa(self):
        """Egy tiltó (`!`) minta, amely semmire sem illik, halott szabály: a kulcsok átnevezése csendben kinyitná a kaput."""
        kulcsok = set()

        def jar(d, elotag=""):
            for k, v in d.items():
                if isinstance(v, dict):
                    jar(v, f"{elotag}{k}.")
                else:
                    kulcsok.add(f"{elotag}{k}")
        jar({k: v for k, v in self.alap.data.items() if k != "_meta"})
        kulcsok |= set(config.META_TIPUS)
        import fnmatch
        for reteg, mintak in config.RETEG_JOG.items():
            for m in (m[1:] for m in mintak if m.startswith("!")):
                with self.subTest(reteg=reteg, minta=m):
                    self.assertTrue(any(fnmatch.fnmatchcase(k, m) for k in kulcsok), "halott tiltó minta")


class MegbizhatatlanTomlTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.v = tiszta_vault(self.t / "V")
        self.toml = self.v / ".manifold" / "workspace.toml"
        self.toml.parent.mkdir()

    def betolt(self):
        return termek_cfg(self.root, self.home, self.v)

    def test_tul_nagy_fajl(self):
        self.toml.write_text(f'[workspace]\nid = "{ID}"\nnev = "' + "x" * (config.MAX_TOML_BAJT + 10) + '"\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError) as e:
            self.betolt()
        self.assertEqual(e.exception.kod, "workspace_toml_hibas")
        self.assertIsNone(workspace.azonosit(self.v))
        f = workspace.felmer(self.v, self.alap)
        self.assertIn("workspace_toml_hibas", f.akadaly)

    def test_melyen_beagyazott_tabla_nem_traceback(self):
        melyseg = 1500
        self.toml.write_text(f'[workspace]\nid = "{ID}"\n[' + ".".join(["a"] * melyseg) + "]\nx = 1\n", encoding="utf-8")
        with self.assertRaises(config.ConfigError) as e:
            self.betolt()
        self.assertEqual(e.exception.kod, "workspace_toml_hibas")
        self.toml.write_text(f'[workspace]\nid = "{ID}"\nx = ' + "[" * melyseg + "]" * melyseg + "\n", encoding="utf-8")
        with self.assertRaises(config.ConfigError) as e:
            self.betolt()
        self.assertEqual(e.exception.kod, "workspace_toml_hibas")

    def test_az_ertelmes_melyseg_atmegy(self):
        self.toml.write_text(f'[workspace]\nid = "{ID}"\n[pdf.tags]\nM = "Mathematics"\n[naptar.szotar.kategoriak]\nx = ["y"]\n',
                             encoding="utf-8")
        cfg = self.betolt()
        self.assertEqual((cfg.workspace_id, cfg.section("pdf", "tags")["M"]), (ID, "Mathematics"))

    def test_olvashatatlan_vagy_kodolasi_hiba_sem_traceback(self):
        self.toml.write_bytes(b'[workspace]\nid = "\xff\xfe"\n')
        with self.assertRaises(config.ConfigError) as e:
            self.betolt()
        self.assertEqual(e.exception.kod, "workspace_toml_hibas")
        self.toml.unlink()
        self.toml.mkdir()                                                        # mappa a fájl helyén
        self.assertIsNone(workspace.azonosit(self.v))

    def test_a_telepitesi_reteg_is_korlatozott(self):
        settings = self.t / "settings.toml"
        settings.write_text("[naplo]\nut = " + '"' + "x" * (config.MAX_TOML_BAJT + 1) + '"\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError) as e:
            config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_SETTINGS": str(settings)}, munkater=False)
        self.assertEqual(e.exception.kod, "settings_toml_hibas")

    def test_a_doctor_nagy_fajlnal_hibat_jelez_nem_dob(self):
        self.toml.write_text(f'[workspace]\nid = "{ID}"\n', encoding="utf-8")
        cfg = self.betolt()
        self.toml.write_text(f'[workspace]\nid = "{ID}"\n[' + ".".join(["a"] * 1500) + "]\n", encoding="utf-8")   # a betöltés UTÁN romlott el
        sorok = []
        doctor._munkater_sorok(cfg, True, lambda allapot, nev, uzenet, **kw: sorok.append((allapot, kw.get("kod"))))
        self.assertEqual(sorok, [(doctor.HIBA, "workspace_toml")])


class RegexBiztonsagTest(unittest.TestCase):
    def test_veszelyes(self):
        self.assertIsNone(regex_biztonsag.veszelyes(r"^(?!Manifold - )[^._].*$"))
        self.assertEqual(regex_biztonsag.veszelyes("a" * 201), "regex_hossz")
        self.assertEqual(regex_biztonsag.veszelyes("(a+)+$"), "regex_beagyazott_ismetles")
        self.assertEqual(regex_biztonsag.veszelyes("(((("), "regex")


class SemaEsKivetelTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.v = tiszta_vault(self.t / "V")
        self.id = workspace.letrehoz(self.v, self.alap)["id"]
        self.cfg = termek_cfg(self.root, self.home, self.v)
        self.ws = self.cfg.path("workspace")

    # ---- schema.json
    def test_a_hibas_munkater_sema_helyett_az_alap_el_es_nem_dob(self):
        sema = self.ws / "schema.json"
        for rossz in ("{nem json", "[]", json.dumps({"mezosorrend": "nem lista"}),
                      json.dumps({"mezosorrend": [], "status_gazdai": "igen"}),
                      json.dumps({"mezosorrend": [1, 2]}),
                      json.dumps({"mezosorrend": [], "kivetel_osztalyok": [{"nev": "x", "mezosorrend": [], "h1_minta": "(a+)+$"}]}),
                      json.dumps({"mezosorrend": [], "h1": {"kivetel_osztalyok": [{"fajlnev_minta": "("}]}}),
                      json.dumps({"mezosorrend": [], "kivetel_osztalyok": [7]}),
                      json.dumps({"mezosorrend": ["a\nStatus"]}),
                      '{"mezosorrend": [], "x": "' + "y" * (kiserok.SEMA_MAX_BAJT + 1) + '"}'):
            sema.write_text(rossz, encoding="utf-8")
            s = Sema.betolt(self.cfg)
            self.assertEqual((s.mezosorrend, s.mod), ([], "ki"), rossz[:60])     # a szállított semleges alap
            self.assertEqual(kiserok.sema_fajlok(self.cfg)[0], sema)
            with self.assertRaises(kiserok.SemaHiba):
                kiserok.sema_olvas(sema)
        sema.write_text(json.dumps({"mezosorrend": ["Tags"], "status_gazdai": False}), encoding="utf-8")
        s = Sema.betolt(self.cfg)
        self.assertEqual(s.mezosorrend, ["Tags"])                                 # az érvényes munkatér-séma nyer

    def test_ha_minden_jelolt_hibas_ertheto_hiba(self):
        (self.ws / "schema.json").write_text("{", encoding="utf-8")
        alap = self.root / "config" / "schema-default.json"
        alap.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError) as e:
            Sema.betolt(self.cfg)
        self.assertIn("schema.json", str(e.exception))

    # ---- pillanat-kivetelek.json
    def test_kivetelek_ervenyes_es_ervenytelen_bejegyzesek(self):
        sha = "a" * 40
        ut = self.ws / "pillanat-kivetelek.json"
        ut.write_text(json.dumps({
            "_leiras": "megjegyzés",
            sha: {"utak": ["Naplo/*", "A/b.md"], "indok": "x"},
            "b" * 40: {"utak": ["*"]},                          # csupa helyettesítő jel az első szakaszban
            "c" * 40: {"utak": ["../x"]},
            "d" * 40: {"utak": ["/abs"]},
            "e" * 7: {"utak": ["A/b.md"]},                      # nem teljes azonosító
            "f" * 40: {"utak": "nem lista"},
            "1" * 40: {"utak": ["x\ny"]},
            "2" * 40: {"utak": [".manifold/var/*"]},
            "3" * 40: {"utak": ["ok"] * 300},
            "4" * 40: "nem objektum",
        }), encoding="utf-8")
        ki = snapshot.exclusions(self.cfg, "vault")
        self.assertEqual(ki, {sha: ["Naplo/*", "A/b.md"]})
        hibak = snapshot.kivetelek_hibak(self.cfg, "vault")
        self.assertEqual(len(hibak), 9)
        self.assertTrue(all(isinstance(h, str) for h in hibak))
        sorok = []
        doctor._kivetelek_sor(self.cfg, lambda allapot, nev, uzenet, **kw: sorok.append((allapot, kw.get("kod"))))
        self.assertEqual(sorok, [(doctor.FIGYELEM, "kivetelek_hibas")])

    def test_kivetelek_olvashatatlan_fajl_nem_dob(self):
        ut = self.ws / "pillanat-kivetelek.json"
        for rossz in ("{nem json", "[]", "\xff".encode("latin-1").decode("latin-1")):
            ut.write_text(rossz, encoding="utf-8")
            self.assertEqual(snapshot.exclusions(self.cfg, "vault"), {})
            self.assertTrue(snapshot.kivetelek_hibak(self.cfg, "vault"))
        ut.unlink()
        self.assertEqual((snapshot.exclusions(self.cfg, "vault"), snapshot.kivetelek_hibak(self.cfg, "vault")), ({}, []))

    def test_a_szallitott_v2_alak_atmegy(self):
        ut = self.ws / "pillanat-kivetelek.json"
        ut.write_text(json.dumps({"4b72aca838fbac0b206094ca8a9c601e52f46017": {
            "utak": ["X01 - Napló & To-Do/*", "AI01 - Workflow System/2.0/01 - Master/00 - MASTER.md"], "indok": "x"}}),
            encoding="utf-8")
        self.assertEqual(len(snapshot.exclusions(self.cfg, "vault")), 1)
        self.assertEqual(snapshot.kivetelek_hibak(self.cfg, "vault"), [])


class CimkeTest(unittest.TestCase):
    def test_yaml_cimke(self):
        from core import cpp_teszt, pdfkiemeles
        import yaml
        for tag, nyers in (("Mathematics", True), ("Física", True), ("Computer Science", True), ("a\nStatus: done", False),
                           ("x: y", False), ("#c", False), ("true", False), ("2024", False), (" pad", False), ("a b", False)):
            ki = kiserok.yaml_cimke(tag)
            self.assertEqual(ki == tag, nyers, tag)
            for vaz in (pdfkiemeles.vaz("T/x.pdf", tag), cpp_teszt.feladat_vaz("Nev", tag)):
                fm = re.match(r"---\n(.*?)\n---\n", vaz, re.S).group(1)
                d = yaml.safe_load(fm)
                self.assertEqual(d["Tags"], [tag], tag)                             # egyetlen címke
                self.assertIsNone(d["Status"])                                      # nincs hamisított kulcs-érték
                self.assertEqual(sorted(d), ["Canvas", "NN", "Source", "Status", "Tags"])


if __name__ == "__main__":
    unittest.main()
