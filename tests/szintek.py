"""Test levels (PLAN §8, F9): named, separately runnable groups of the Python test suite.

    bin/mos test --szint <name> [-v -k …]      (or: python -B -m tests.szintek <name> [-v …])
    bin/mos test --szint lista                 the levels and their modules

A level is a list of test modules / packages (dotted names under `tests`). The whole suite (`bin/mos test`) still runs
everything; a level is a reviewable slice of it, e.g. for a release gate or a CI job. Every listed name must exist and must
load at least one test (`tests/test_szintek.py` guards this), so a renamed test cannot silently drop out of a level.

The `dod` level maps the Definition of Done (PLAN §12) to the automated tests; `DOD` names, per DoD point, the tests that
cover it and the points that stay manual (`KEZI`), so the release checklist and the suite cannot drift apart.
"""
from __future__ import annotations

import sys
import unittest

SZINTEK: dict[str, tuple[str, ...]] = {
    # clean fake HOME → install layer → workspace → Setup → first note → search → quit/restart, data kept
    "fresh-install": (
        "tests.fresh_install",
        "tests.test_workspace_masolat_mozgatas",
        "tests.test_manifold_lathatatlan",
        "tests.test_regiszter",
        "tests.test_f5_beallitas_fogyaszto",
    ),
    # two fake users (separate install and workspace state), install-level locks, state keyed by workspace id
    "multi-user": (
        "tests.multi_user",
        "tests.test_zarak_telepites",
    ),
    # index schema v1–v5 → v6, old settings / workspace files, Obsidian and v2 import → usable workspace
    "migracio": (
        "tests.migracio",
        "tests.test_f5_index_migracio",
        "tests.test_index_c33",
    ),
    # sandbox escape, path traversal / symlink escape, SSRF, machine-write gate, secrets / absolute paths, dependencies
    "biztonsag": (
        "tests.biztonsag",
        "tests.test_homokozo_elszigeteles",
        "tests.test_homokozo",
        "tests.test_homokozo_program",
        "tests.test_kod_ellenorzes",
        "tests.test_vaultkivul",
        "tests.test_munkater_biztonsag",
        "tests.test_rejtett_bejaras",
        "tests.test_kulso_kep",
        "tests.test_lepes_kapu",
        "tests.test_kartya_apkg_biztonsag",
        "tests.test_core_api",
    ),
    # snapshot → change → git revert on every write path, CAS conflicts, the destructive-git guard, recovery
    "mentes": (
        "tests.mentes_visszaallitas",
        "tests.test_snapshot",
        "tests.test_mentes",
        "tests.test_mentes_munkater",
        "tests.test_visszaallitas",
        "tests.test_teljes_mentes",
        "tests.test_teljes_mentes_termek",
        "tests.test_tartos",
        "tests.test_elozmeny",
        "tests.test_tulajdonsag_tipusok",
    ),
}

# Definition of Done (PLAN §12): point → (title, automated tests, what stays manual)
DOD: dict[int, tuple[str, tuple[str, ...], str | None]] = {
    1: ("install (DMG)", ("tests.test_runtime_fetch",),
        "build and open the signed DMG on a clean macOS 26 user account (packaging/; Gatekeeper path for the ad-hoc signature)"),
    2: ("start", ("tests.fresh_install.test_f5_folyamat", "tests.test_indito_core"),
        "launch Manifold.app from /Applications (the Swift launcher window)"),
    3: ("create a workspace", ("tests.fresh_install.test_workspace_letrehozas", "tests.fresh_install.test_alap"), None),
    4: ("understand the main idea (Welcome + docs)", ("tests.test_felhasznaloi_doku", "tests.test_demo_generator"),
        "read the Welcome step and the built-in guide in the app (comprehension is not testable)"),
    5: ("import an Obsidian vault", ("tests.migracio.test_obsidian_import", "tests.migracio.test_f9_migracio"), None),
    6: ("write a note", ("tests.fresh_install.test_f5_folyamat", "tests.fresh_install.test_f9_dod"), None),
    7: ("search", ("tests.fresh_install.test_f5_folyamat", "tests.fresh_install.test_f9_dod"), None),
    8: ("use AI (download a model + test + one feature)", ("tests.test_f6_modellek", "tests.fresh_install.test_f9_dod"),
        "download a real model, run 'Test this model' on idle hardware, use one calibrated feature (the user measures, D9)"),
    9: ("cards / quiz", ("tests.test_kartya_api", "tests.test_kviz_api", "tests.fresh_install.test_f9_dod"), None),
    10: ("PDF", ("tests.test_pdfkiemeles", "tests.test_kereses_media", "tests.fresh_install.test_f9_dod"), None),
    11: ("math check", ("tests.test_matek_levezetes", "tests.test_matek_egyseg", "tests.fresh_install.test_f9_dod"), None),
    12: ("C++ sandbox", ("tests.test_cpp_teszt", "tests.test_homokozo_program", "tests.test_kod_ellenorzes"),
         "on a fresh install: install the C++ toolchain from Setup (8.6 GB download) and run one test block"),
    13: ("backup", ("tests.fresh_install.test_alap", "tests.test_mentes", "tests.mentes_visszaallitas.test_korut"), None),
    14: ("restore", ("tests.fresh_install.test_alap", "tests.test_visszaallitas", "tests.mentes_visszaallitas.test_korut"), None),
    15: ("without developer help", ("tests.test_f7_fejleszto_mod", "tests.fresh_install.test_f9_dod"),
         "an outside tester does points 1–14 from the user guide alone (usability, not testable)"),
}

SZINTEK["dod"] = tuple(dict.fromkeys(m for _, mods, _ in DOD.values() for m in mods))


def betolt_nev(nev: str) -> unittest.TestSuite:
    """A module's tests, or — for a package — the tests of every `test*.py` under it (`loadTestsFromName` alone would load
    only the package's `__init__`)."""
    import importlib
    from pathlib import Path
    modul = importlib.import_module(nev)
    if hasattr(modul, "__path__"):
        gyoker = Path(__file__).resolve().parent.parent
        return unittest.defaultTestLoader.discover(str(Path(modul.__path__[0])), pattern="test*.py", top_level_dir=str(gyoker))
    return unittest.defaultTestLoader.loadTestsFromModule(modul)


def betolt(szint: str) -> unittest.TestSuite:
    """The test suite of a level (`KeyError` for an unknown name)."""
    return unittest.TestSuite(betolt_nev(n) for n in SZINTEK[szint])


def _szamol(s: unittest.TestSuite) -> int:
    return s.countTestCases()


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: bin/mos test --szint <" + "|".join(SZINTEK) + "|lista> [-v] [-q] [-f]", file=sys.stderr)
        return 2
    szint, tobbi = argv[0], argv[1:]
    if szint == "lista":
        for nev, mods in SZINTEK.items():
            print(f"{nev}: {', '.join(mods)}")
        print("\nDoD (PLAN §12): automated → manual")
        for n, (cim, mods, kezi) in DOD.items():
            print(f"  {n:2}. {cim}: {', '.join(mods)}" + (f"\n      manual: {kezi}" if kezi else ""))
        return 0
    if szint not in SZINTEK:
        print(f"unknown level: {szint} (known: {', '.join(SZINTEK)})", file=sys.stderr)
        return 2
    ismeretlen = [a for a in tobbi if a not in ("-v", "-q", "-f", "--verbose", "--quiet", "--failfast")]
    if ismeretlen:
        print(f"unknown option(s): {' '.join(ismeretlen)}", file=sys.stderr)
        return 2
    beszedes = 2 if any(a in ("-v", "--verbose") for a in tobbi) else 0 if any(a in ("-q", "--quiet") for a in tobbi) else 1
    s = betolt(szint)
    print(f"[szint] {szint}: {_szamol(s)} tests in {len(SZINTEK[szint])} modules", file=sys.stderr)
    r = unittest.TextTestRunner(verbosity=beszedes, failfast=any(a in ("-f", "--failfast") for a in tobbi)).run(s)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
