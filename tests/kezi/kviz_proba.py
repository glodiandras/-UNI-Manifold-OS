"""C22a kézi próbakörnyezet: a beágyazott kvíz egy MINI-vaulton, elkülönített állapottal (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/kviz_proba.py core      # a core; a címét kiírja (böngésző / Browser pane)
    bin/mos exec var/venv/bin/python -B tests/kezi/kviz_proba.py app       # a valódi Manifold.app (WKWebView) a mini-vaulton
    … --megtart                                                           # a próbamappa nem törlődik a végén

A valódi vaulthoz és var/-hoz nem nyúl: a próbamappában (`{tmp}/c22-kviz-proba-<idő>/`) egy mini-vault áll, benne a forrásjegyzet
(`M03 - Algebra/Elmélet/04 - Nevezetes szorzatok.md`, a `## Gyakorlás` alatt a kvíz beágyazásával) és a kvízjegyzet
(`ATTCHMNTS - quizes/…`), amelyet a kvízlánc állított elő álmodellel (a fixture a `tests/test_kviz_generalas.py`-ból). A kitöltések
a próbamappa `tanulas.sqlite`-jába mennek. Megnyitás: ⌘O → „Nevezetes szorzatok”.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, snapshot  # noqa: E402
from modulok.kviz import formatum, generalas  # noqa: E402
from proba_app import _var  # noqa: E402
from tests.test_kviz_generalas import GEN, JEGYZET, RP, TUDAS, Almodell  # noqa: E402
from _kornyezet import elkulonit, probamappa  # noqa: E402


def mini_vault(vault: Path) -> Path:
    """A forrásjegyzet és a kvízjegyzet a mini-vaultban; → a kvízjegyzet útja."""
    (vault / ".obsidian").mkdir(parents=True)
    modell = Almodell(gen=GEN, tudas=TUDAS)
    e = generalas.general(JEGYZET, RP, modell.generalo, modell.ellenorzo, n=3, modell="almodell",
                          b=generalas.Beallitas(karakter_per_kerdes=50))
    nev = formatum.fajlnev(e.kviz)
    ut = f"ATTCHMNTS - quizes/{nev}.md"
    forras = vault / RP
    forras.parent.mkdir(parents=True)
    forras.write_text(JEGYZET.rstrip("\n") + f"\n\n## Gyakorlás\n![[{nev}]]\n", encoding="utf-8")
    (vault / ut).parent.mkdir(parents=True)
    (vault / ut).write_text(formatum.ir(e.kviz), encoding="utf-8")
    return Path(ut)


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("core", "app"):
        print(__doc__)
        return 2
    mod, megtart = sys.argv[1], "--megtart" in sys.argv
    cfg = config.load()
    d = probamappa(cfg, "c22-kviz-proba", megtart=megtart, szkript="kviz_proba.py")
    vault, git = d / "Manifold", d / "vault.git"
    kviz_ut = mini_vault(vault)
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=(mod == "core"))
    repo = snapshot.repos(config.load(env))["vault"]
    repo.init()
    repo.commit("alap", {"Mos-Forras": "kezi"})
    print(f"[próba] mini-vault: {vault}  ·  kvíz: {kviz_ut}", flush=True)
    try:
        if mod == "core":
            p = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, env=env)
            port = json.loads(p.stdout.readline())["port"]
            print(f"[próba] core: http://127.0.0.1:{port}/", flush=True)
            (d / "port").write_text(str(port))
            _var(p, lezar=lambda: p.stdin.close())
        else:
            app = REPO / "Manifold.app" / "Contents" / "MacOS" / "Manifold"
            p = subprocess.Popen([str(app)], env=env)
            print(f"[próba] app: pid {p.pid} — kilépés: ⌘Q", flush=True)
            _var(p, lezar=p.terminate)
    finally:
        if not megtart:
            shutil.rmtree(d, ignore_errors=True)
            print("[próba] a próbamappa törölve", flush=True)
        else:
            print(f"[próba] a próbamappa megmaradt (--megtart): {d} — törlése csak a felhasználó igenjével", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
