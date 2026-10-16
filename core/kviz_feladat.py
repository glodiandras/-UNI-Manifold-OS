"""A kvíz-generálás feladattípusa (C22b; `docs/C22-TERV.md` 10. fejezet; CLAUDE.md 28., 48., 56., 63. döntés, D9).

- `kviz_general`: kézzel indított („Kvíz ebből” a jegyzet helyi menüjéből vagy a ⌘P-ből), egy jegyzet. Automatikus mód nincs:
  a 3. döntés az automatikusan futó munkák közt a kvízt nem sorolja (a kvíz kérésre készül).

Modellt használ és a vaultba ír (`modell`, `vault` erőforrás). A lépés a `python -m modulok.kviz general` alfolyamata: a
jegyzetet a core-tól olvassa, a modellt a workeren át hívja (a `kviz` router-feladat kalibrált modellje; ha az csak a
távol-keretbe fér, a kérés tétlenségre vár), és egy tételt ír a gépi-írás szolgáltatáson át (`Mos-Forras: mos-kviz`).

Paraméterek: `ut`, `n` (a kérdések száma, a `[kviz] kerdes_min..kerdes_max` között), `proba` (D9: az írás az APFS-klónra),
`modell` (kifejezett modell: csak próba).
"""
from __future__ import annotations

import sys

from . import tasks
from .config import Config

TIPUS = "kviz_general"


def _ut_ok(ut) -> bool:
    return isinstance(ut, str) and ut.lower().endswith(".md") and not ut.startswith("/") and ".." not in ut.split("/")


def _modellnev(cfg: Config, nev) -> str:
    from .modell import beallitas as B
    if not isinstance(nev, str) or not nev:
        raise tasks.Invalid("A `modell` egy regisztrált modell neve legyen.")
    try:
        m = B.betolt(cfg).modell(nev)
    except B.RegiszterHiba as exc:
        raise tasks.Invalid(str(exc)) from None
    if "kviz" not in m.feladat:
        raise tasks.Invalid(f"A(z) {m.nev} nem `kviz`-modell (a regiszter `feladat` listája).")
    return m.nev


def _terv(cfg: Config, p: dict, stop: str):
    from .automatika import kisero_elotag, tartalmi_ut
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    if not _ut_ok(p.get("ut")):
        raise tasks.Invalid("Az `ut` a vault egy Markdown-jegyzetének relatív útja legyen.")
    if not tartalmi_ut(p["ut"], kisero_elotag(cfg)):
        raise tasks.Invalid("Kvíz csak tartalmi jegyzetből készül (kísérőjegyzetből és rejtett mappából nem).")
    if not isinstance(p.get("proba", False), bool):
        raise tasks.Invalid("A `proba` igaz vagy hamis lehet.")
    argv = [sys.executable, "-B", "-m", "modulok.kviz", "general", "--stop-fajl", stop, "--ut", p["ut"]]
    n = p.get("n")
    if n is not None:
        k = cfg.section("kviz")
        lo, hi = int(k.get("kerdes_min", 3)), int(k.get("kerdes_max", 30))
        if isinstance(n, bool) or not isinstance(n, int) or not lo <= n <= hi:
            raise tasks.Invalid(f"Az `n` (a kérdések száma) {lo} és {hi} közötti egész legyen.")
        argv += ["--n", str(n)]
    figy = []
    proba = bool(p.get("proba"))
    if p.get("modell") is not None:
        argv += ["--modell", _modellnev(cfg, p["modell"])]
        proba = True
    if proba:
        argv.append("--proba")
        figy.append("Próbamód: a kvíz a vault APFS-klónjára kerül, a vaultba nem.")
    return ([tasks.Step("Kvíz a jegyzetből (modell + kapuk)", argv, str(cfg.root))],
            "A modell kérdéseket javasol a jegyzetből; a kapukon átment kérdések a kvízjegyzetbe kerülnek, a forrás "
            "`## Gyakorlás` szakaszába a beágyazó sor (gépi írás, visszavonható). Ha a kvíz modellje csak a távol-keretbe fér, "
            "a feladat tétlenségben készül el.", figy)


def regisztral() -> None:
    """A feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "Kvíz ebből", _terv, resources=frozenset({"modell", "vault"}), graceful_stop=True))
