"""F3 egyenértékűségi kapu (F3-DESIGN §9 WP1, §7.1): a rétegzett konfiguráció a hordozható álgyökéren
(`alg_gyoker(preset="v2-kompat")`) ugyanazt adja, mint az F2-fa.

A `tests/adat/konfig/f2-hordozhato.json` az F3 első szerkesztése ELŐTT készült az F2-fából: egy `alg_gyoker()` álgyökér
feloldott `[utak]`-ja és minden más szakasza (a helyőrzős szövegek feloldva, `{"$kifejtve": …}`; `<TMP>` = a teszt mappája).
Eltérés csak a lenti, kifejezett listákban lehet: az F3 új kulcsai, egy tervezett változás (`.manifold/` a pillanatkép
kizárásában), és a `v2-kompat` preset két F3 előtti (v2) értéke, amelyet a preset maga hoz (F2 NAPLO: a fejlesztő saját,
a termék által már nem szállított értékei).
"""
import json
import os
import tomllib
import unittest
from pathlib import Path

from core import config
from tests.helpers import REPO, alg_gyoker, tmpdir

ARANY = REPO / "tests" / "adat" / "konfig" / "f2-hordozhato.json"

# Az F3 új `[utak]` kulcsai (hordozható módban mind egy F2-útra esik)
UJ_UTAK = {"install", "install_run", "install_state", "install_logs", "workspace", "backup_gyoker"}
# Az F3 új szakaszai / levelei
UJ_ELOTAGOK = ("_meta.", "elrendezes.", "telepites.", "pdf.nevek.")
UJ_LEVELEK = {"sema.alap", "sema.mod"}
# Tervezett változás (F3-DESIGN §2.4): a `.manifold/` a vault pillanatkép-tárolójának kizárásában
MANIFOLD_KIZARAS = ("pillanat.vault.kizar", ".manifold/")
# A `v2-kompat` preset F3 előtti értékei (a presetből jönnek, és csak a preset értékével egyezhetnek)
PRESET_ERTEKEK = {"fuzet.mappak", "naptar.szotar.dolgozat"}


def _h(s: str, tmp: str) -> str:
    return s.replace(os.path.realpath(tmp), "<TMP>").replace(tmp, "<TMP>")


def _bejar(cfg, tmp: str, x):
    """Az aranyfájl alakja: a helyőrzős szöveg feloldva (`{"$kifejtve": …}`), a teszt mappája `<TMP>`."""
    if isinstance(x, dict):
        return {k: _bejar(cfg, tmp, v) for k, v in x.items()}
    if isinstance(x, list):
        return [_bejar(cfg, tmp, v) for v in x]
    if isinstance(x, str) and config._HELYORZO.search(x):
        try:
            return {"$kifejtve": _h(cfg.expand(x), tmp)}
        except config.ConfigError:
            return x
    return x


def _pillanatkep(cfg, tmp: str) -> dict:
    """Ugyanaz a szerkezet, amelyből az aranyfájl készült: feloldott `[utak]` + a többi szakasz (helyőrzős szöveg feloldva)."""
    return {"utak": {k: _h(str(p), tmp) for k, p in sorted(cfg.utak.items())},
            "szakaszok": {k: _bejar(cfg, tmp, v) for k, v in cfg.data.items() if k != "utak"}}


def _levelek(d: dict, elotag: str = "") -> dict:
    ki = {}
    for k, v in d.items():
        if isinstance(v, dict) and "$kifejtve" not in v:
            ki.update(_levelek(v, f"{elotag}{k}."))
        else:
            ki[f"{elotag}{k}"] = v
    return ki


class KonfigEgyenertekTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arany = json.loads(ARANY.read_text(encoding="utf-8"))
        cls._t = tmpdir()
        t = cls._t.name
        cls.root = alg_gyoker(t, preset="v2-kompat")
        cls.cfg = config.load({"MOS_ROOT": str(cls.root), "HOME": str(Path(t) / "home")})
        cls.most = _pillanatkep(cls.cfg, t)
        cls.preset = tomllib.loads((cls.root / "config" / "presets" / "v2-kompat.toml").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_az_arany_fajl_az_f2_fabol_valo(self):
        self.assertIn("vault", self.arany["utak"])
        self.assertEqual(self.arany["utak"]["vault"], "<TMP>/work/Manifold")
        self.assertGreater(len(self.arany["szakaszok"]), 30)

    def test_utak_egyeznek_csak_az_uj_kulcsok_tobbek(self):
        arany, most = self.arany["utak"], self.most["utak"]
        for k, v in arany.items():
            self.assertEqual(most.get(k), v, k)
        self.assertEqual(set(most) - set(arany), UJ_UTAK)

    def test_az_uj_utak_hordozhato_modban_f2_utra_esnek(self):
        p = self.cfg.path
        self.assertEqual(p("install"), p("var"))
        self.assertEqual(p("install_run"), p("run"))
        self.assertEqual(p("install_state"), p("state"))
        self.assertEqual(p("install_logs"), p("runs"))
        self.assertEqual(p("backup_gyoker"), p("var") / "backups")
        self.assertEqual(p("workspace"), p("vault") / ".manifold")
        self.assertEqual(self.cfg.elrendezes, "hordozhato")
        self.assertEqual((self.cfg.feloldatlan, self.cfg.elutasitott), ({}, []))

    def test_szakaszok_egyeznek_csak_a_kifejezett_elteresekkel(self):
        arany, most = _levelek(self.arany["szakaszok"]), _levelek(self.most["szakaszok"])
        for k, v in arany.items():
            self.assertIn(k, most, f"eltűnt kulcs: {k}")
            if most[k] == v:
                continue
            if k == MANIFOLD_KIZARAS[0]:
                self.assertEqual([x for x in most[k] if x != MANIFOLD_KIZARAS[1]], v)
                self.assertIn(MANIFOLD_KIZARAS[1], most[k])
                continue
            self.assertIn(k, PRESET_ERTEKEK, f"eltér az F2-től: {k}: {v!r} → {most[k]!r}")
            nyers = config._keres(self.preset, k)
            self.assertIsNot(nyers, config._NINCS, f"{k}: nem a preset hozza")
            self.assertEqual(most[k], _bejar(self.cfg, self._t.name, nyers), k)
            self.assertEqual(self.cfg.forras(*k.split(".")), "preset:v2-kompat", k)
        uj = set(most) - set(arany)
        self.assertEqual({k for k in uj if not k.startswith(UJ_ELOTAGOK) and k not in UJ_LEVELEK}, set(), "új kulcs a listán kívül")
        self.assertTrue(UJ_LEVELEK <= uj)

    def test_a_vaultot_es_a_presetet_a_telepitesi_reteg_adja(self):
        self.assertEqual(self.cfg.forras("utak", "vault"), "telepites")
        self.assertEqual(self.cfg.section("telepites")["presetek"], ["v2-kompat"])
        # a semleges `[naplo] ut` után a fejlesztő értéke a `v2-kompat` presetből jön (F3-DESIGN §7.2)
        self.assertEqual(self.cfg.forras("naplo", "ut"), "preset:v2-kompat")


if __name__ == "__main__":
    unittest.main()
