"""F9 RootLocator: a `core/gyoker_kereso.py` a három módban (env / csomag / checkout), a közös esettábla
(`tests/adat/gyoker_esetek.json`) a Pythonban ÉS a Swift héj `RootLocator.swift`-jében ugyanazt adja (egyetlen forrás),
a `config` a gyökér-feloldást innen veszi, és a `MOS_INSTALL` a telepítési gyökeret állítja (a csomagba nem mutathat)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from core import config, gyoker_kereso
from tests.helpers import REPO, alg_bundle, tmpdir

ESETEK = json.loads((REPO / "tests" / "adat" / "gyoker_esetek.json").read_text(encoding="utf-8"))


def _gyoker_letrehoz(ut: Path) -> None:
    (ut / "bin").mkdir(parents=True, exist_ok=True)
    (ut / "config").mkdir(parents=True, exist_ok=True)
    mos = ut / "bin" / "mos"
    mos.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    mos.chmod(mos.stat().st_mode | stat.S_IXUSR)
    (ut / "config" / "os.toml").write_text("", encoding="utf-8")


def _helyettesit(x, t: str):
    if isinstance(x, str):
        return x.replace("{t}", t)
    if isinstance(x, dict):
        return {k: _helyettesit(v, t) for k, v in x.items()}
    if isinstance(x, list):
        return [_helyettesit(v, t) for v in x]
    return x


class GyokerKeresoTablaTest(unittest.TestCase):
    def test_az_ut_alakja_dont_a_termek_gyokerrol(self):
        for ut, vart in ESETEK["alakok"]:
            with self.subTest(ut):
                self.assertEqual(gyoker_kereso.termek_gyoker(ut), vart)
                self.assertEqual(config._bundle_gyoker(Path(ut)), vart)       # a config ugyanazt a forrást használja

    def test_jeloltek_sorrendje_a_hejeval_azonos(self):
        for e in ESETEK["jeloltek"]:
            with self.subTest(e):
                j = [str(p) for _, p in gyoker_kereso.jeloltek(e["env"], app=Path(e["app"]))]
                self.assertEqual(j, e["vart"])

    def test_harom_mod_es_a_tartalek_a_kozos_tablaval(self):
        for e in ESETEK["elrendezesek"]:
            with self.subTest(e["nev"]), tmpdir() as d:
                t = os.path.realpath(d)
                for g in e["gyokerek"]:
                    _gyoker_letrehoz(Path(t) / g)
                e = _helyettesit(e, t)
                talalat = gyoker_kereso.keres(e["env"], app=Path(e["app"]))
                if e["vart"] is None:
                    self.assertIsNone(talalat)
                else:
                    self.assertEqual(talalat.szotar(), e["vart"])

    def test_python_folyamat_a_sajat_kodfajabol(self):
        with tmpdir() as d:
            t = Path(os.path.realpath(d))
            csomag = t / "M.app" / "Contents" / "Resources" / "manifold"
            checkout = t / "checkout"
            for g in (csomag, checkout):
                _gyoker_letrehoz(g)
            self.assertEqual(gyoker_kereso.keres({}, kod_hely=csomag).szotar(), {"gyoker": str(csomag), "mod": "csomag", "termek": True})
            self.assertEqual(gyoker_kereso.keres({}, kod_hely=checkout).szotar(), {"gyoker": str(checkout), "mod": "checkout", "termek": False})
            self.assertEqual(gyoker_kereso.keres({"MOS_ROOT": str(checkout)}, kod_hely=csomag).mod, "env")

    def test_a_config_gyokere_innen_jon(self):
        self.assertEqual(gyoker_kereso.kod_gyoker({}), REPO.resolve())
        self.assertEqual(gyoker_kereso.kod_gyoker({"MOS_ROOT": "/x/../y"}), Path("/y"))
        self.assertEqual(gyoker_kereso.KOD_HELY, REPO.resolve())
        self.assertEqual(gyoker_kereso.keres({}).mod, "checkout")          # ez a checkout maga
        self.assertEqual(config.os_root(), gyoker_kereso.kod_gyoker(os.environ))


class GyokerCliTest(unittest.TestCase):
    """`python -m core.gyoker_kereso --json`: a talált gyökér, az elrendezés és az `{install}`."""

    def _fut(self, env: dict) -> dict:
        e = {k: v for k, v in os.environ.items() if not k.startswith("MOS_")}
        e.update(env)
        p = subprocess.run([sys.executable, "-B", "-m", "core.gyoker_kereso", "--json"], cwd=REPO, env=e,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_env_mod_csomag_alaku_gyokerrel_es_a_mos_install(self):
        with tmpdir() as d:
            root = alg_bundle(d)
            _gyoker_letrehoz(root)
            shutil.copy(REPO / "config" / "os.toml", root / "config" / "os.toml")
            home = Path(d) / "home"
            ki = self._fut({"MOS_ROOT": str(root), "HOME": str(home)})
            self.assertEqual((ki["mod"], ki["termek"], ki["elrendezes"]), ("env", True, "termek"))
            self.assertEqual(ki["install"], str(home / "Library" / "Application Support" / "Manifold"))
            sajat = Path(d) / "sajat-install"
            self.assertEqual(self._fut({"MOS_ROOT": str(root), "HOME": str(home), "MOS_INSTALL": str(sajat)})["install"],
                             str(sajat))
            # I1: a telepítési gyökér nem mutathat a csak olvasható csomagba
            ki = self._fut({"MOS_ROOT": str(root), "HOME": str(home), "MOS_INSTALL": str(root / "install")})
            self.assertEqual(ki["konfig_hiba"], "iras_a_kodba")

    def test_checkout_mod(self):
        with tmpdir() as d:
            ki = self._fut({"HOME": d, "MOS_SETTINGS": ""})
        self.assertEqual((ki["mod"], ki["termek"], ki["elrendezes"]), ("checkout", False, "hordozhato"))
        self.assertEqual(ki["gyoker"], str(REPO.resolve()))


SWIFTC = shutil.which("xcrun") and subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True).returncode == 0

HARNESS = r"""
import Foundation
@main struct Harness { static func main() {
  let d = try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
  let esetek = try! JSONSerialization.jsonObject(with: d) as! [[String: Any]]
  var ki: [[String: Any]] = []
  for e in esetek {
    let env = e["env"] as? [String: String] ?? [:]
    let app = URL(fileURLWithPath: e["app"] as! String)
    var sor: [String: Any] = ["jeloltek": RootLocator.jeloltek(environment: env, bundle: app).map(\.path),
                              "alak": (e["alakok"] as? [String] ?? []).map { RootLocator.termekGyoker(URL(fileURLWithPath: $0)) }]
    if let t = RootLocator.locate(environment: env, bundle: app) { sor["gyoker"] = t.root.path; sor["termek"] = t.termek }
    else { sor["gyoker"] = NSNull() }
    ki.append(sor)
  }
  print(String(data: try! JSONSerialization.data(withJSONObject: ki), encoding: .utf8)!)
}}
"""


@unittest.skipUnless(SWIFTC, "nincs swiftc (Command Line Tools)")
class SwiftParitasTest(unittest.TestCase):
    """A héj `RootLocator.swift`-je ugyanazon az esettáblán ugyanazt adja, mint a Python (egyetlen forrás: a tábla)."""

    def test_a_swift_rootlocator_a_kozos_tablaval(self):
        with tmpdir() as d:
            t = os.path.realpath(d)
            (Path(t) / "main.swift").write_text(HARNESS, encoding="utf-8")
            cache = REPO / "var" / "cache" / "clang"
            cache.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-module-cache-path", str(cache), "-o",
                                str(Path(t) / "harness"), str(Path(t) / "main.swift"),
                                str(REPO / "shell" / "Sources" / "RootLocator.swift")],
                               capture_output=True, text=True, timeout=600,
                               env={**os.environ, "TMPDIR": t, "CLANG_MODULE_CACHE_PATH": str(cache)})
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            esetek = []
            for e in ESETEK["elrendezesek"]:
                alap = Path(t) / e["nev"]
                for g in e["gyokerek"]:
                    _gyoker_letrehoz(alap / g)
                esetek.append(_helyettesit(e, str(alap)))
            jel = [dict(e, alakok=[]) for e in ESETEK["jeloltek"]]
            alak = [{"env": {}, "app": "/A/Manifold.app", "alakok": [u for u, _ in ESETEK["alakok"]]}]
            (Path(t) / "esetek.json").write_text(json.dumps(esetek + jel + alak), encoding="utf-8")
            r = subprocess.run([str(Path(t) / "harness"), str(Path(t) / "esetek.json")], capture_output=True, text=True,
                               timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            ki = json.loads(r.stdout)
            for e, s in zip(esetek, ki[:len(esetek)]):
                with self.subTest(e["nev"]):
                    py = gyoker_kereso.keres(e["env"], app=Path(e["app"]))
                    sw = None if s["gyoker"] is None else {"gyoker": os.path.realpath(s["gyoker"]), "termek": s["termek"]}
                    self.assertEqual(sw, None if py is None else {"gyoker": str(py.gyoker), "termek": py.termek})
                    self.assertEqual(s["jeloltek"], [str(p) for _, p in gyoker_kereso.jeloltek(e["env"], app=Path(e["app"]))])
            for e, s in zip(jel, ki[len(esetek):len(esetek) + len(jel)]):
                self.assertEqual(s["jeloltek"], e["vart"])
            self.assertEqual(ki[-1]["alak"], [v for _, v in ESETEK["alakok"]])


if __name__ == "__main__":
    unittest.main()
