"""RootLocator (F9): hol van a Manifold kódfája (`{os}`), és milyen módban fut — EGYETLEN forrás a Pythonban.

Három mód, a felfedezés sorrendjében:
  env       a `MOS_ROOT` környezeti változó (fejlesztés, tesztek, a héj által indított core);
  csomag    a termék: `<X>.app/Contents/Resources/manifold` (a gyökér útjának alakja dönti el, nem mentett beállítás);
  checkout  a fejlesztői (hordozható) checkout: a `Manifold.app` a gyökérben él, a kód a `bin/mos` szülőmappájában.

A héj (`shell/Sources/RootLocator.swift`) ugyanezt a sorrendet követi; a két megvalósítást a `tests/adat/gyoker_esetek.json`
közös esettáblája köti össze (a Python-teszt és a Swift-harness ugyanazt a táblát futtatja). Beégetett út, kötet-átnézés,
mentett beállítás nincs (CLAUDE.md). Érvényes gyökér: van futtatható `bin/mos` és `config/os.toml`.

A `kod_gyoker(env)` a core saját feloldása (`config.os_root`): a `MOS_ROOT`-ot érvényesítés nélkül veszi át (a tesztek
álgyökereinek nincs `bin/mos`-a), különben a kódot hordozó fa. A `keres()` a szigorú változat (a héj és a csomagoló ezt
használja): az első ÉRVÉNYES jelölt.

`python -m core.gyoker_kereso [--app <X.app>] [--json]` → a talált gyökér, a mód, az elrendezés és az `{install}` gyökér.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

MODOK = ("env", "csomag", "checkout")

# A kódot hordozó fa (ennek a fájlnak a nagyszülője): checkoutban a repo, termékben a `Contents/Resources/manifold`.
KOD_HELY = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Talalat:
    gyoker: Path
    mod: str            # env | csomag | checkout
    termek: bool        # a gyökér csomag-alakú (`*.app/Contents/Resources/manifold`)

    def szotar(self) -> dict:
        return {"gyoker": str(self.gyoker), "mod": self.mod, "termek": self.termek}


def termek_gyoker(ut: Path | str) -> bool:
    """`<X>.app/Contents/Resources/manifold` alakú-e az út (tiszta függvény; a záró `/` nem számít)."""
    p = Path(os.path.normpath(str(ut))).parts
    return len(p) >= 4 and p[-1] == "manifold" and p[-2] == "Resources" and p[-3] == "Contents" and p[-4].endswith(".app")


def ervenyes(ut: Path) -> bool:
    """Érvényes gyökér: futtatható `bin/mos` és `config/os.toml`."""
    mos = Path(ut) / "bin" / "mos"
    return mos.is_file() and os.access(mos, os.X_OK) and (Path(ut) / "config" / "os.toml").is_file()


def jeloltek(env: Mapping[str, str], *, app: Path | None = None, kod_hely: Path | None = None) -> list[tuple[str, Path]]:
    """A jelöltek a felfedezés sorrendjében (tiszta függvény). `app`: a héj csomagja (`Bundle.main.bundleURL`) — ekkor a jelöltek
    a Swift `RootLocator.jeloltek`-kel azonosak: `MOS_ROOT`, `<app>/Contents/Resources/manifold`, az app szülőmappája.
    `app` nélkül (a Python-folyamat maga) a kódot hordozó fa: csomag-alakú útnál `csomag`, különben `checkout`."""
    ki: list[tuple[str, Path]] = []
    e = env.get("MOS_ROOT") or ""
    if e:
        ki.append(("env", Path(e)))
    if app is not None:
        ki.append(("csomag", Path(app) / "Contents" / "Resources" / "manifold"))
        ki.append(("checkout", Path(os.path.normpath(str(app))).parent))
    else:
        hely = Path(kod_hely) if kod_hely is not None else KOD_HELY
        ki.append(("csomag" if termek_gyoker(hely) else "checkout", hely))
    return ki


def keres(env: Mapping[str, str] | None = None, *, app: Path | None = None, kod_hely: Path | None = None) -> Talalat | None:
    """Az első érvényes jelölt (a symlinkek feloldva), vagy None. A mód a jelölt forrása; a `termek` az út alakja."""
    env = os.environ if env is None else env
    for mod, jelolt in jeloltek(env, app=app, kod_hely=kod_hely):
        gyoker = Path(os.path.realpath(jelolt))
        if ervenyes(gyoker):
            return Talalat(gyoker, mod, termek_gyoker(gyoker))
    return None


def kod_gyoker(env: Mapping[str, str] | None = None) -> Path:
    """A core gyökere (`config.os_root`): a `MOS_ROOT` (érvényesítés nélkül, feloldva), különben a kódot hordozó fa."""
    env = os.environ if env is None else env
    e = env.get("MOS_ROOT") or ""
    return Path(e).resolve() if e else KOD_HELY


def _main(argv: list[str]) -> int:
    app = None
    if "--app" in argv:
        i = argv.index("--app")
        app = Path(argv[i + 1]) if i + 1 < len(argv) else None
    t = keres(app=app)
    if t is None:
        print("HIBA: nem található érvényes Manifold-gyökér (bin/mos + config/os.toml)", file=sys.stderr)
        return 1
    ki = t.szotar()
    try:
        from . import config
        cfg = config.load({**os.environ, "MOS_ROOT": str(t.gyoker)}, munkater=False)
        ki["elrendezes"] = cfg.elrendezes
        ki["install"] = str(cfg.utak["install"]) if "install" in cfg.utak else None
    except Exception as exc:                 # a gyökér megvan; a konfiguráció hibája külön mező (nem rejti el a találatot)
        ki["konfig_hiba"] = getattr(exc, "kod", type(exc).__name__)
    print(json.dumps(ki, ensure_ascii=False) if "--json" in argv else "\n".join(f"{k}: {v}" for k, v in ki.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
