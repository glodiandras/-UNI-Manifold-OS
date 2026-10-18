"""13-palette-01 / 13-palette-02: Obsidian `.obsidian/hotkeys.json` -> Manifold hotkey settings, and the reserved-chord table the
validator and the importer share (`config/billentyuk.json`, generated from the shell menu).

The importer never writes the source: every end-to-end test here ends with the source's byte AND metadata fingerprint unchanged
(`ujjlenyomat`, like `test_obsidian_import.py`). Synthetic vaults in temp dirs only."""
from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from core import billentyu_forras, config
from core import importalas as imp
from core import importalas_billentyuk as hk
from core import termek_beallitasok, workspace
from core.utvonalak import HttpError
from tests.fresh_install import termek_alap
from tests.helpers import tmpdir
from tests.migracio import Kuka, obsidian_vault, ujjlenyomat


def kotes(*moduloknak_es_kulcs):
    """`kotes(["Mod"], "B")` -> an Obsidian binding."""
    m, k = moduloknak_es_kulcs
    return {"modifiers": m, "key": k}


ALAP = {"szerkeszto.felkover": "Mod+b", "szerkeszto.dolt": "Mod+i", "szerkeszto.link": "Mod+k", "kereses.panel": "Mod+Shift+f",
        "ful.uj": "Mod+t", "beallitasok.megnyit": "Mod+,"}


def sorok(r, ok):
    return {x["forras"].split("#", 1)[1]: x for x in r["nem_atvett"] if x["ok"] == ok}


class LekepezesTest(unittest.TestCase):
    def test_leosztott_kotesek_alkalmazva_vagy_okkal_kihagyva(self):
        adat = {
            "editor:toggle-strikethrough": [kotes(["Mod", "Shift"], "X")],                 # free chord: applied
            "global-search:open": [kotes(["Mod", "Shift"], "F")],                          # same as the default: nothing to write
            "editor:toggle-code": [kotes(["Mod"], "C")],                                   # ⌘C belongs to the native menu
            "editor:open-search": [kotes([], "F")],                                        # a bare key is not a command chord
            "workspace:new-tab": [],                                                       # default removed in Obsidian
            "some-plugin:do-it": [kotes(["Mod"], "J")],                                    # no Manifold command
            "editor:insert-link": [kotes(["Mod", "Shift"], "L"), kotes(["Mod", "Alt"], "K")],    # two chords: the first is kept
            "app:open-settings": [kotes(["Mod"], "P")],                                    # the settings chord is fixed
        }
        r = hk.lekepez(adat, ALAP)
        self.assertEqual(r["billentyuk"], {"szerkeszto.athuzott": "Mod+Shift+x", "szerkeszto.link": "Mod+Shift+l"})
        b = {x["kulcs"]: x for x in r["beallitasok"]}
        self.assertEqual(b["beallitasok.billentyuk.szerkeszto.athuzott"]["mod"], "ir")
        self.assertEqual(b["beallitasok.billentyuk.kereses.panel"]["mod"], "azonos")
        self.assertEqual(b["beallitasok.billentyuk.szerkeszto.athuzott"]["forras"], ".obsidian/hotkeys.json#editor:toggle-strikethrough")
        self.assertEqual(set(sorok(r, "hotkey_foglalt")), {"editor:toggle-code", "app:open-settings"})
        self.assertEqual(sorok(r, "hotkey_foglalt")["editor:toggle-code"]["akkord"], "Mod+c")
        self.assertEqual(sorok(r, "hotkey_ervenytelen")["editor:open-search"]["kulcs"], "szerkeszto.kereses")
        self.assertEqual(set(sorok(r, "hotkey_ures")), {"workspace:new-tab"})
        self.assertEqual(set(sorok(r, "hotkey_nincs_parancs")), {"some-plugin:do-it"})
        self.assertEqual(set(sorok(r, "hotkey_tobb")), {"editor:insert-link"})

    def test_utkozes_a_megmarado_alapertelmezessel_es_ket_import_kozott(self):
        adat = {
            "editor:toggle-highlight": [kotes(["Mod"], "K")],        # ⌘K stays with the link command (not imported)
            "editor:toggle-code": [kotes(["Mod", "Alt"], "Q")],
            "editor:toggle-strikethrough": [kotes(["Mod", "Alt"], "Q")],     # same chord as the previous one: first (sorted) wins
        }
        r = hk.lekepez(adat, ALAP)
        self.assertEqual(set(sorok(r, "hotkey_utkozes")), {"editor:toggle-highlight", "editor:toggle-strikethrough"})
        self.assertEqual(r["billentyuk"], {"szerkeszto.kod": "Mod+Alt+q"})    # Obsidian-id order: `toggle-code` < `toggle-strikethrough`
        self.assertEqual(sorok(r, "hotkey_utkozes")["editor:toggle-highlight"]["masik"], "szerkeszto.link")

    def test_ket_akkord_cserelje_elfogadott(self):
        adat = {"editor:toggle-bold": [kotes(["Mod"], "I")], "editor:toggle-italics": [kotes(["Mod"], "B")]}
        r = hk.lekepez(adat, ALAP)
        self.assertEqual(r["billentyuk"], {"szerkeszto.felkover": "Mod+i", "szerkeszto.dolt": "Mod+b"})
        self.assertEqual(r["nem_atvett"], [])

    def test_egy_rossz_bejegyzes_nem_blokkolja_a_tobbit(self):
        adat = {"editor:toggle-bold": "not a list", "editor:toggle-italics": [{"modifiers": ["Hyper"], "key": "I"}],
                "editor:toggle-code": [None], "editor:toggle-strikethrough": [kotes(["Mod", "Shift"], "X")]}
        r = hk.lekepez(adat, ALAP)
        self.assertEqual(r["billentyuk"], {"szerkeszto.athuzott": "Mod+Shift+x"})
        self.assertEqual({x["ok"] for x in r["nem_atvett"]}, {"ervenytelen", "hotkey_ervenytelen"})
        self.assertEqual(len(r["nem_atvett"]), 3)

    def test_nem_objektum_fajl_jelentett(self):
        self.assertEqual(hk.lekepez(["x"], ALAP)["nem_atvett"], [{"forras": ".obsidian/hotkeys.json", "ok": "ervenytelen"}])

    def test_modositok_es_kulcsnevek(self):
        adat = {"editor:toggle-bold": [kotes(["Meta", "Alt"], "ArrowLeft")], "editor:toggle-italics": [kotes(["Ctrl"], " ")],
                "editor:toggle-code": [kotes(["Mod", "Shift"], "+")], "editor:toggle-strikethrough": [kotes(["Mod"], "F5")]}   # `+` key: unsupported
        r = hk.lekepez(adat, {})
        self.assertEqual(r["billentyuk"], {"szerkeszto.felkover": "Mod+Alt+ArrowLeft", "szerkeszto.dolt": "Ctrl+Space",
                                           "szerkeszto.athuzott": "Mod+F5"})
        self.assertEqual(set(sorok(r, "hotkey_ervenytelen")), {"editor:toggle-code"})

    def test_a_tabla_cel_azonositoi_leteznek_a_felulet_forrasaban(self):
        """Every target id of the reviewed table is a real registry command (found in `app/src`)."""
        forras = ""
        for p in sorted((config.os_root() / "app" / "src").rglob("*")):
            if p.suffix in (".ts", ".svelte") and not p.name.endswith((".test.ts", ".d.ts")):
                forras += p.read_text(encoding="utf-8") + "\n"
        van = set(re.findall(r"""\bid:\s*['"]([a-z0-9]+(?:[.\-][a-z0-9\-]+)+)['"]""", forras))
        van |= {f"szerkeszto.{x}" for x in re.findall(r"\b(?:notion|formaz)\(\s*'([a-z0-9\-]+)'", forras)}
        van |= {f"szerkeszto.fejezet-{n}" for n in range(7)} | {f"ful.n{n}" for n in range(1, 10)}    # generated in a loop
        hianyzik = sorted(m for m in set(hk.OBSIDIAN_PARANCS.values()) if m not in van)
        self.assertEqual(hianyzik, [], "the Obsidian hotkey table points at a command the registry does not define")
        self.assertGreaterEqual(len(hk.OBSIDIAN_PARANCS), 40)


class FenntartottTablaTest(unittest.TestCase):
    def test_a_natav_tabla_a_shell_menujebol_szarmazik_es_naprakesz(self):
        self.assertTrue(billentyu_forras.naprakesz(), "run: python -m core.billentyu_forras --iras")
        f = billentyu_forras.fenntartott()
        for akkord in ("Mod+c", "Mod+v", "Mod+x", "Mod+z", "Mod+Shift+z", "Mod+a", "Mod+h", "Mod+Alt+h", "Mod+m", "Mod+q",
                       "Mod+Ctrl+f", "Mod+Shift+o", "Mod+,"):
            self.assertIn(akkord, f)
        self.assertEqual(f["Mod+,"], "beallitasok.megnyit")

    def test_kinyeres_swift_szovegbol(self):
        swift = '''
        let a = appMenu.addItem(withTitle: L("Egy"), action: nil, keyEquivalent: "h")
        a.keyEquivalentModifierMask = [.command, .option]
        let b = NSMenuItem(title: L("Beállítások…"), action: nil, keyEquivalent: ",")
        b.representedObject = "beallitasok.megnyit"; b.target = self
        edit.addItem(withTitle: L("Másolás"), action: nil, keyEquivalent: "c")
        // edit.addItem(withTitle: L("Komment"), action: nil, keyEquivalent: "j")
        x.addItem(withTitle: L("Nincs"), action: nil, keyEquivalent: "")
        let t = x.addItem(withTitle: L("Teljes képernyő"), action: nil, keyEquivalent: "f")
        t.keyEquivalentModifierMask = [.command, .control, .shift]
        '''
        ki = {e["akkord"]: e for e in billentyu_forras.natav_menu(swift)}
        self.assertEqual(set(ki), {"Mod+Alt+h", "Mod+,", "Mod+c", "Mod+Ctrl+Shift+f"})
        self.assertEqual(ki["Mod+,"]["tulajdonos"], "beallitasok.megnyit")

    def test_a_beallitas_iro_elutasitja_a_natav_akkordot(self):
        for akkord in ("Mod+c", "Mod+Shift+z", "Mod+Ctrl+f", "Mod+Shift+o", "cmd+V"):
            with self.assertRaises(HttpError, msg=akkord):
                termek_beallitasok.ellenoriz({"billentyuk": {"szerkeszto.kod": akkord}})
        termek_beallitasok.ellenoriz({"billentyuk": {"szerkeszto.kod": "Mod+Alt+q"}})
        termek_beallitasok.ellenoriz({"billentyuk": {"beallitasok.megnyit": "Mod+,"}})
        with self.assertRaises(HttpError):
            termek_beallitasok.ellenoriz({"billentyuk": {"szerkeszto.kod": "Mod+,"}})

    def test_az_alapertelmezesek_nem_fenntartottak_es_nem_utkoznek(self):
        alap = billentyu_forras.tabla()["alap"]
        f = billentyu_forras.fenntartott()
        for mid, akkord in alap.items():
            self.assertFalse(akkord in f and f[akkord] != mid, f"{mid} default {akkord} is a native menu chord")
        self.assertEqual(len(set(alap.values())), len(alap), "two registry defaults share a chord")


class _Alap(unittest.TestCase):
    HOTKEYS = {
        "editor:toggle-bold": [kotes(["Mod"], "I")],
        "editor:toggle-italics": [kotes(["Mod"], "B")],
        "editor:toggle-strikethrough": [kotes(["Mod", "Shift"], "X")],
        "editor:toggle-code": [kotes(["Mod"], "C")],
        "editor:toggle-highlight": [kotes(["Mod"], "K")],
        "editor:open-search": [kotes([], "F")],
        "global-search:open": [kotes(["Mod", "Shift"], "F")],
        "workspace:new-tab": [],
        "unknown-plugin:command": [kotes(["Mod"], "J")],
    }

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.forras = obsidian_vault(self.t / "My Vault")
        (self.forras / ".obsidian" / "hotkeys.json").write_text(json.dumps(self.HOTKEYS), encoding="utf-8")
        self.cel = self.t / "Imported"
        self.lenyomat = ujjlenyomat(self.forras)

    def tearDown(self):
        self.assertEqual(ujjlenyomat(self.forras), self.lenyomat, "the import changed the source")


class ImportTest(_Alap):
    def test_elonezet_jelenti_az_atvettet_es_a_kihagyottat(self):
        r = imp.obsidian_elonezet(self.forras, self.cel, self.alap)
        b = {x["kulcs"]: x for x in r["obsidian"]["beallitasok"] if x["kulcs"].startswith("beallitasok.billentyuk.")}
        self.assertEqual({k: (v["ertek"], v["mod"]) for k, v in b.items()}, {
            "beallitasok.billentyuk.szerkeszto.felkover": ("Mod+i", "ir"),
            "beallitasok.billentyuk.szerkeszto.dolt": ("Mod+b", "ir"),
            "beallitasok.billentyuk.szerkeszto.athuzott": ("Mod+Shift+x", "ir"),
            "beallitasok.billentyuk.kereses.panel": ("Mod+Shift+f", "azonos"),
        })
        nem = {x["forras"].split("#", 1)[1]: x["ok"] for x in r["obsidian"]["nem_atvett"] if "hotkeys.json#" in x["forras"]}
        self.assertEqual(nem, {
            "editor:toggle-code": "hotkey_foglalt", "editor:toggle-highlight": "hotkey_utkozes",
            "editor:open-search": "hotkey_ervenytelen", "workspace:new-tab": "hotkey_ures",
            "unknown-plugin:command": "hotkey_nincs_parancs",
        })
        self.assertNotIn(".obsidian/hotkeys.json", {x["forras"] for x in r["obsidian"]["nem_atvett"]}, "no longer 'not supported' as a whole")
        self.assertFalse(self.cel.exists(), "the preview writes nothing")

    def test_import_az_uj_munkater_beallitasaiba_ir_egy_visszavonhato_futasban(self):
        t = imp.obsidian_elonezet(self.forras, self.cel, self.alap)
        r = imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"])
        self.assertEqual(r["allapot"], "kesz")
        w = tomllib.loads((self.cel / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
        self.assertEqual(w["beallitasok"]["billentyuk"], {"szerkeszto.felkover": "Mod+i", "szerkeszto.dolt": "Mod+b",
                                                          "szerkeszto.athuzott": "Mod+Shift+x"})
        from tests.fresh_install import termek_cfg
        ertek = termek_beallitasok.olvas(termek_cfg(self.root, self.home, self.cel))["ertek"]
        self.assertEqual(ertek["billentyuk"]["szerkeszto.dolt"], "Mod+b")
        # the hotkeys file itself was copied byte for byte, like every other .obsidian file
        self.assertEqual((self.cel / ".obsidian" / "hotkeys.json").read_bytes(), (self.forras / ".obsidian" / "hotkeys.json").read_bytes())
        # one undoable run: the same undo as for every import
        kuka = Kuka(self.t / "Trash")
        v = imp.visszafordit(r["id"], self.alap, kuka=kuka)
        self.assertEqual(v["allapot"], "visszaforditva")
        self.assertFalse(self.cel.exists())

    def test_nincs_hotkeys_fajl_nincs_jelentes(self):
        (self.forras / ".obsidian" / "hotkeys.json").unlink()
        self.lenyomat = ujjlenyomat(self.forras)
        r = imp.obsidian_elonezet(self.forras, self.cel, self.alap)
        self.assertFalse([x for x in r["obsidian"]["beallitasok"] if "billentyuk" in x["kulcs"]])
        self.assertFalse([x for x in r["obsidian"]["nem_atvett"] if "hotkeys" in x["forras"]])

    def test_hibas_hotkeys_fajl_jelentett(self):
        (self.forras / ".obsidian" / "hotkeys.json").write_text("{not json", encoding="utf-8")
        self.lenyomat = ujjlenyomat(self.forras)
        r = imp.obsidian_elonezet(self.forras, self.cel, self.alap)
        self.assertIn({"forras": ".obsidian/hotkeys.json", "ok": "hibas_json"}, r["obsidian"]["nem_atvett"])


if __name__ == "__main__":
    unittest.main()
