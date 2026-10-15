"""A tesztkészlet közös kapuja: a szigorú kihagyás-kezelés (T086, 2. audit).

Egy kihagyott teszt csendben zöldre enged: az `app/dist`, a `Manifold.app`, a Node vagy a `websockets` hiánya esetén a
készlet „0 hiba”-val végez, miközben a kapu nem futott. `MOS_SZIGORU=1` mellett (chatzáró és kapufutás: `MOS_SZIGORU=1
bin/mos test`) a kihagyás bukás, KIVÉVE az `[indokolt]` előtagú okút (a gép adottsága: nincs APFS-klón, nincs
`st_birthtime`; a `skipTest("[indokolt] …")`), és a futás végén a kihagyott tesztek névsora kiíródik — ezt írjuk a
chat NAPLO-bejegyzésébe. A CHATKALAUZ kész-feltétele: „0 kihagyás, vagy indokolt”.

A kapu a `tests` csomag importjakor kapcsol be (a `discover` és a `-m unittest tests.X` is importálja), így minden
futtatási úton egységes; `MOS_SZIGORU` nélkül semmi nem változik.
"""
import atexit
import os
import sys
import time
import unittest

INDOKOLT = "[indokolt]"


def csak_darwin(ok: str):
    """Platformfüggő teszt (APFS, FSEvents, NFD-nevek, F_FULLFSYNC, EventKit, Mach-O héj): csak macOS-en fut. A Macen a feltétel
    hamis, a teszt változatlanul lefut; máshol `[indokolt]` kihagyás (a `MOS_SZIGORU` nem veszi bukásnak)."""
    return unittest.skipUnless(sys.platform == "darwin", f"{INDOKOLT} macOS kell: {ok}")


def budapest_idozona(teszt: unittest.TestCase) -> None:
    """A fixture `+02:00` eltolásokat vár: az időzónát rögzíti `Europe/Budapest`-re, és a teszt végén visszaállítja."""
    regi = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Budapest"
    time.tzset()

    def vissza():
        if regi is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = regi
        time.tzset()
    teszt.addCleanup(vissza)

# A core API-titka (35. döntés, T071): a core induláskor titkot sorsol; a tesztekben rögzített (a `MOS_API_TITOK` felülírja a
# sorsolást), hogy a kérések fejlécét ismerjük. A `helpers.env()` a gyermek-core-oknak is átadja (a `MOS_*` szűrő után).
API_TITOK = "teszt-api-titok-0123456789abcdef"
os.environ.setdefault("MOS_API_TITOK", API_TITOK)

if os.environ.get("MOS_SZIGORU") == "1":
    _kihagyasok: list[tuple[str, str]] = []
    _addSkip, _wasSuccessful = unittest.TestResult.addSkip, unittest.TestResult.wasSuccessful

    def _indokolatlan() -> list[tuple[str, str]]:
        return [k for k in _kihagyasok if not k[1].startswith(INDOKOLT)]

    def _add_skip(self, test, reason):
        _kihagyasok.append((test.id(), reason))
        _addSkip(self, test, reason)

    def _was_successful(self):
        return _wasSuccessful(self) and not _indokolatlan()

    def _jelentes() -> None:
        ossz, rossz = len(_kihagyasok), _indokolatlan()
        print(f"\n[MOS_SZIGORU] {ossz} kihagyás, ebből {len(rossz)} indokolatlan", file=sys.stderr)
        for kulcs, lista in (("indokolatlan", rossz), ("indokolt", [k for k in _kihagyasok if k not in rossz])):
            osztalyok: dict[str, list[str]] = {}
            for azon, ok in lista:
                osztaly, _, nev = azon.rpartition(".")
                osztalyok.setdefault(osztaly, []).append(f"{nev}")
            for osztaly, nevek in sorted(osztalyok.items()):
                okok = sorted({ok for a, ok in lista if a.startswith(osztaly + ".")})
                print(f"  {kulcs}: {osztaly}.{', '.join(nevek)} — {'; '.join(okok)}", file=sys.stderr)

    unittest.TestResult.addSkip = _add_skip
    unittest.TestResult.wasSuccessful = _was_successful
    atexit.register(_jelentes)
