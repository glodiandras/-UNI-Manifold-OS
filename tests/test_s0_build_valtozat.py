"""S0: a tényleges App.swift belépési pont kiadási selftest-kapuja, UI/core/vault indítása nélkül.

A próba mindkét fordítási feltétellel fordítja az eredeti App.swift-et; az NSApplication és a segédek szintetikusak.
Az alkalmazás létrehozásának jelzése bizonyítja, hogy a kiadási --selftest elutasítása már előtte megtörténik.
"""
import json
import subprocess
import unittest
from pathlib import Path

from tests import csak_darwin
from tests.helpers import REPO, env, tmpdir


PROBA = r'''
import Foundation

@MainActor final class NSApplication {
    enum Policy: String { case accessory, regular }
    static var shared: NSApplication {
        print("APPLICATION_CREATED")
        return NSApplication()
    }
    var delegate: AnyObject?
    func setActivationPolicy(_ policy: Policy) { print("POLICY:\(policy.rawValue)") }
    func run() { print("APPLICATION_RUN") }
}

@MainActor final class AppController {
#if MOS_DEVELOPER
    init(selftest: Bool, forgatokonyv: String?) { print("SELFTEST:\(selftest):\(forgatokonyv ?? "")") }
#else
    init() { print("RELEASE_CONTROLLER") }
#endif
}

enum Kuka {
    static func futtat() -> Int32 { print("TRASH_HELPER"); return 7 }
}
enum Naptar {
    static func futtat(_ args: [String]) -> Int32 {
        print(String(decoding: try! JSONSerialization.data(withJSONObject: args), as: UTF8.self))
        return 8
    }
}
'''


@csak_darwin("az App.swift fordítási kapuja AppKit-ot használ")
class HejBuildValtozatTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ideiglenes = tmpdir()
        cls.addClassCleanup(cls.ideiglenes.cleanup)
        cls.gyoker = Path(cls.ideiglenes.name)
        proba = cls.gyoker / "Proba.swift"
        proba.write_text(PROBA, encoding="utf-8")
        cls.futtathatok = {}
        for fejlesztoi in (False, True):
            valtozat = "fejlesztoi" if fejlesztoi else "kiadasi"
            exe = cls.gyoker / valtozat
            parancs = ["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-module-cache-path",
                       str(cls.gyoker / "cache"), "-o", str(exe)]
            if fejlesztoi:
                parancs.append("-DMOS_DEVELOPER")
            parancs += [str(REPO / "shell/Sources/App.swift"), str(proba)]
            p = subprocess.run(parancs, capture_output=True, text=True, timeout=120,
                               env=env(HOME=str(cls.gyoker / "home"), TMPDIR=str(cls.gyoker),
                                       CLANG_MODULE_CACHE_PATH=str(cls.gyoker / "cache")))
            if p.returncode:
                raise AssertionError(f"{valtozat} App.swift failed to compile:\n{p.stderr}")
            cls.futtathatok[fejlesztoi] = exe

    def futtat(self, *args, fejlesztoi=False):
        return subprocess.run([str(self.futtathatok[fejlesztoi]), *args], capture_output=True, text=True, timeout=5,
                              env=env(HOME=str(self.gyoker / "home")))

    def test_a_kiadas_minden_selftest_alakot_az_alkalmazas_letrehozasa_elott_utasit_el(self):
        for args in (("--selftest",), ("--selftest=kilepes",), ("--selftest=",), ("--other", "--selftest=szerkesztes")):
            with self.subTest(args=args):
                p = self.futtat(*args)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertEqual(p.stdout, "")
                self.assertIn("Self-tests require a developer build.", p.stderr)
                self.assertIn("MOS_DEVELOPER_BUILD=1 bash shell/build.sh", p.stderr)

    def test_a_normal_kiadasi_inditas_es_a_mas_kezdetu_argumentum_megmarad(self):
        for args in ((), ("--selftesting",)):
            with self.subTest(args=args):
                p = self.futtat(*args)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stderr, "")
                self.assertEqual(p.stdout.splitlines(), ["APPLICATION_CREATED", "RELEASE_CONTROLLER", "POLICY:regular", "APPLICATION_RUN"])

    def test_a_fejlesztoi_selftest_valtozatlanul_atadja_a_forgatokonyvet(self):
        for args, jel in ((("--selftest",), "SELFTEST:true:"), (("--selftest=kilepes",), "SELFTEST:true:kilepes"),
                          ((), "SELFTEST:false:")):
            with self.subTest(args=args):
                p = self.futtat(*args, fejlesztoi=True)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn(jel, p.stdout.splitlines())
                self.assertIn("POLICY:accessory" if args else "POLICY:regular", p.stdout.splitlines())

    def test_a_kuka_es_naptar_seged_prioritasa_es_argumentumai_megmaradnak(self):
        for fejlesztoi in (False, True):
            with self.subTest(fejlesztoi=fejlesztoi):
                kuka = self.futtat("--kuka", "--selftest", fejlesztoi=fejlesztoi)
                self.assertEqual((kuka.returncode, kuka.stdout, kuka.stderr), (7, "TRASH_HELPER\n", ""))
                naptar = self.futtat("--naptar", "events", "--selftest=kilepes", fejlesztoi=fejlesztoi)
                self.assertEqual(naptar.returncode, 8, naptar.stderr)
                self.assertEqual(json.loads(naptar.stdout), ["events", "--selftest=kilepes"])
                self.assertEqual(naptar.stderr, "")
