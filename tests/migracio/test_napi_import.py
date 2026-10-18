"""12-templates-01 / 05 / 08: the Obsidian `daily-notes.json` import keeps every real-world variant (empty, format only, folder only,
template, everything) instead of silently dropping the root-folder case and the template. Synthetic vaults in temp dirs only."""
from __future__ import annotations

import json
import unicodedata
import unittest
from datetime import date
from pathlib import Path

from core import importalas as imp
from core import naplo, workspace
from tests.fresh_install import termek_alap
from tests.helpers import tmpdir

NAP = date(2026, 10, 2)


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)

    def vault(self, napi=None, *, mag=None, nyers=None):
        """A synthetic Obsidian vault with the given `daily-notes.json` (a dict, `nyers` text, or no file) and `core-plugins.json`."""
        v = self.t / "Vault"
        (v / ".obsidian").mkdir(parents=True, exist_ok=True)
        if nyers is not None:
            (v / ".obsidian" / "daily-notes.json").write_text(nyers, encoding="utf-8")
        elif napi is not None:
            (v / ".obsidian" / "daily-notes.json").write_text(json.dumps(napi), encoding="utf-8")
        if mag is not None:
            (v / ".obsidian" / "core-plugins.json").write_text(json.dumps(mag), encoding="utf-8")
        return v

    def w(self, v):
        return workspace._w_mag(workspace._obsidian_beallitasok(v), self.alap, workspace._napi_engedelyezve(v))

    def ut(self, w, nap=NAP):
        """The daily note path Manifold would use with this workspace layer."""
        self.alap.data.setdefault("naplo", {}).update(w.get("naplo", {}))
        return naplo.napi_ut(self.alap, nap)


class NapiVariansokTest(_Alap):
    def test_ures_fajl_nem_talal_ki_utat(self):
        self.assertEqual(self.w(self.vault({})), {})
        self.assertEqual(self.w(self.vault(nyers="")), {})                       # an unreadable / empty file
        self.assertEqual(self.w(self.vault(nyers="{ not json")), {})

    def test_ures_fajl_de_bekapcsolt_plugin_az_obsidian_alapja_a_gyoker(self):
        w = self.w(self.vault({}, mag=["daily-notes", "file-explorer"]))
        self.assertEqual(w, {"naplo": {"ut": "YYYY-MM-DD"}})
        self.assertEqual(self.ut(w), "2026-10-02.md")
        self.assertEqual(self.w(self.vault({}, mag={"daily-notes": True})), {"naplo": {"ut": "YYYY-MM-DD"}})

    def test_ures_fajl_kikapcsolt_plugin_nem_ir_semmit(self):
        self.assertEqual(self.w(self.vault({}, mag=["file-explorer"])), {})
        self.assertEqual(self.w(self.vault({}, mag={"daily-notes": False})), {})

    def test_csak_formatum_a_gyokerben(self):
        w = self.w(self.vault({"format": "YYYY/MM/YYYY-MM-DD"}))
        self.assertEqual(w, {"naplo": {"ut": "YYYY/MM/YYYY-MM-DD"}})
        self.assertEqual(self.ut(w), "2026/10/2026-10-02.md")

    def test_csak_mappa_alap_formatummal(self):
        w = self.w(self.vault({"folder": "Journal"}))
        self.assertEqual(w, {"naplo": {"ut": "[Journal]/YYYY-MM-DD"}})
        self.assertEqual(self.ut(w), "Journal/2026-10-02.md")

    def test_gyoker_mappa_es_formatum_es_beagyazott_sablon(self):
        """The case the audit measured: folder "", a format and a template outside any template folder."""
        w = self.w(self.vault({"folder": "", "format": "YYYY-MM-DD", "template": "Templates/Daily"}))
        self.assertEqual(w, {"naplo": {"ut": "YYYY-MM-DD", "sablon": "Templates/Daily.md"}})
        self.assertEqual(self.ut(w), "2026-10-02.md")

    def test_mindent_megad_beagyazott_mappa_es_sablon(self):
        w = self.w(self.vault({"folder": "Notes/Daily/", "format": "YYYY-MM-DD ddd", "template": "Meta/Tpl/Day note.md",
                               "autorun": True}))
        self.assertEqual(w["naplo"], {"ut": "[Notes]/[Daily]/YYYY-MM-DD ddd", "sablon": "Meta/Tpl/Day note.md"})
        self.assertEqual(self.ut(w), "Notes/Daily/2026-10-02 Fri.md")

    def test_sablon_a_gyokerben_es_kiterjesztessel(self):
        self.assertEqual(self.w(self.vault({"template": "Daily"}))["naplo"]["sablon"], "Daily.md")
        self.assertEqual(self.w(self.vault({"template": "Daily.md"}))["naplo"]["sablon"], "Daily.md")
        self.assertEqual(self.w(self.vault({"template": "  "}))["naplo"].get("sablon"), None)

    def test_szogletes_zarojel_a_mappaban_szo_szerint_megmarad(self):
        for mappa in ("Journal [2026]", "[draft] Notes", "a]b", "x[", "Ünnep (2026) [A]/Napló"):
            w = self.w(self.vault({"folder": mappa, "format": "YYYY-MM-DD"}))
            self.assertIn("naplo", w, mappa)
            self.assertEqual(self.ut(w), f"{mappa}/2026-10-02.md", mappa)

    def test_nem_szoveges_ertek_marad_ki(self):
        w = self.w(self.vault({"folder": None, "format": 5, "template": ["x"]}))
        self.assertEqual(w, {})

    def test_nfd_mappa_nfc_lesz(self):
        w = self.w(self.vault({"folder": unicodedata.normalize("NFD", "Napló")}))
        self.assertEqual(w["naplo"]["ut"], "[Napló]/YYYY-MM-DD")

    def test_a_rosszul_formazott_ut_nem_kerul_a_retegbe(self):
        for mappa in ("../Kint", ".hidden/Napló", "Napló/{x}"):
            self.assertEqual(self.w(self.vault({"folder": mappa, "format": "YYYY-MM-DD"})), {}, mappa)

    def test_a_sablon_ut_ellenorzott(self):
        w = self.w(self.vault({"folder": "J", "template": "../Kint/Tpl"}))
        self.assertEqual(w["naplo"], {"ut": "[J]/YYYY-MM-DD"})                   # the bad template is dropped, the rest stays

    def test_a_templates_json_tovabbra_is_bejon(self):
        v = self.vault({"format": "YYYY-MM-DD"})
        (v / ".obsidian" / "templates.json").write_text(json.dumps({"folder": "Sablonok"}), encoding="utf-8")
        self.assertEqual(self.w(v), {"sablon": {"mappa": "Sablonok"}, "naplo": {"ut": "YYYY-MM-DD"}})


class MunkaterIrasTest(_Alap):
    """The workspace creation (`workspace.letrehoz`) writes the variants into `workspace.toml`."""

    def letrehoz(self, v):
        import tomllib
        workspace.letrehoz(v, self.alap, nev="T", nyelv="en")
        return tomllib.loads((v / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))

    def test_gyoker_mappa_es_beagyazott_sablon_a_workspace_tomlban(self):
        w = self.letrehoz(self.vault({"folder": "", "format": "YYYY-MM-DD", "template": "Templates/Daily"}))
        self.assertEqual((w["naplo"]["ut"], w["naplo"]["sablon"]), ("YYYY-MM-DD", "Templates/Daily.md"))

    def test_csak_formatum_a_workspace_tomlban(self):
        w = self.letrehoz(self.vault({"format": "YYYY/MM/YYYY-MM-DD"}))
        self.assertEqual(w["naplo"]["ut"], "YYYY/MM/YYYY-MM-DD")
        self.assertNotIn("sablon", w["naplo"])


class ImportJelentesTest(_Alap):
    """The import preview reports what it takes over and what it rejects."""

    def lekepez(self, v):
        return imp._obsidian_lekepezes(v, self.alap, {"obsidian_mappa": True})

    def test_a_gyoker_mappas_beallitas_a_jelentesben(self):
        v = self.vault({"folder": "", "format": "YYYY-MM-DD", "template": "Templates/Daily"}, mag={"daily-notes": True})
        jelentes, w = self.lekepez(v)
        b = {x["kulcs"]: x for x in jelentes["beallitasok"]}
        self.assertEqual(b["naplo.ut"]["ertek"], "YYYY-MM-DD")
        self.assertEqual(b["naplo.sablon"]["ertek"], "Templates/Daily.md")
        self.assertEqual(jelentes["nem_atvett"], [])

    def test_az_elutasitott_ertek_nem_tunik_el_nema(self):
        jelentes, _ = self.lekepez(self.vault({"folder": "../Kint", "format": "YYYY-MM-DD", "template": "../Tpl/Daily"}))
        nem = {(x["forras"], x["ok"]) for x in jelentes["nem_atvett"]}
        for kulcs in ("folder", "format", "template"):
            self.assertIn((f".obsidian/daily-notes.json#{kulcs}", "ervenytelen"), nem)


if __name__ == "__main__":
    unittest.main()
