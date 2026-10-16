"""A „Megoldás” feladattípusa (C24b; docs/C24-TERV.md 5.1–5.3; CLAUDE.md 28., 46., 56. döntés, D9).

`TaskType("matek_megoldas")`: kézzel indított (a szerkesztő „Megoldás” parancsa), nem automatikus; modellt használ és a vaultba ír
(`modell`, `vault` erőforrás). A lépés a `modulok/matek/__main__.py megoldas` alfolyamat: a jegyzetet a core-tól olvassa, a modellt a
workeren át hívja (`matek_cas` router-feladat, második vélemény `kizart_csalad`-dal), a kódot a CAS-homokozóban futtatja, és a
`> [!solution]-` calloutot a feladat sorai UTÁN a gépi-írás szolgáltatáson át írja (egy tétel = egy gépi commit, `Mos-Forras: mos-matek`).

Paraméterek: `ut` (a jegyzet, `.md`), `tol`, `ig` (a feladat sorai, 1-től, zárt), `feladat` (a sorok szövege, változatlanul: a lépés ezzel
ellenőrzi, hogy a jegyzet közben nem változott), `proba` (D9: az írás az APFS-klónra), `modell` / `masodik_modell` (kifejezett modell:
csak próba), `masodik` (alap: igaz).
"""
from __future__ import annotations

import sys

from . import tasks
from .config import Config

TIPUS = "matek_megoldas"
MAX_FELADAT = 4000
MAX_SOR = 80


def _modellnev(cfg: Config, nev, mezo: str) -> str:
    from .modell import beallitas as B
    if not isinstance(nev, str) or not nev:
        raise tasks.Invalid(f"A `{mezo}` egy regisztrált modell neve legyen.")
    try:
        m = B.betolt(cfg).modell(nev)
    except B.RegiszterHiba as exc:
        raise tasks.Invalid(str(exc)) from None
    if "matek_cas" not in m.feladat:
        raise tasks.Invalid(f"A(z) {m.nev} nem `matek_cas`-modell (a regiszter `feladat` listája).")
    return m.nev


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    ut = p.get("ut")
    if not isinstance(ut, str) or not ut.lower().endswith(".md") or ut.startswith("/") or ".." in ut.split("/"):
        raise tasks.Invalid("Az `ut` a vault egy Markdown-jegyzetének relatív útja legyen.")
    tol, ig = p.get("tol"), p.get("ig")
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (tol, ig)) or not 1 <= tol <= ig or ig - tol >= MAX_SOR:
        raise tasks.Invalid(f"A `tol` és az `ig` a feladat sorai (1-től, tol ≤ ig, legfeljebb {MAX_SOR} sor).")
    feladat = p.get("feladat")
    if not isinstance(feladat, str) or not feladat.strip() or len(feladat) > MAX_FELADAT:
        raise tasks.Invalid(f"A `feladat` a kijelölt sorok szövege legyen (legfeljebb {MAX_FELADAT} jel).")
    if feladat.count("\n") != ig - tol:
        raise tasks.Invalid("A `feladat` sorainak száma nem egyezik a `tol`–`ig` tartománnyal.")
    for k in ("proba", "masodik"):
        if not isinstance(p.get(k, k == "masodik"), bool):
            raise tasks.Invalid(f"A `{k}` igaz vagy hamis lehet.")
    argv = [sys.executable, "-B", str(cfg.path("modulok") / "matek" / "__main__.py"), "megoldas", "--ut=" + ut,
            f"--tol={tol}", f"--ig={ig}", "--feladat=" + feladat]
    figy = []
    proba = bool(p.get("proba"))
    if p.get("modell") is not None:
        argv.append("--modell=" + _modellnev(cfg, p["modell"], "modell"))
        proba = True
    if p.get("masodik_modell") is not None:
        argv.append("--masodik-modell=" + _modellnev(cfg, p["masodik_modell"], "masodik_modell"))
        proba = True
    if not p.get("masodik", True):
        argv.append("--nincs-masodik")
    if proba:
        argv.append("--proba")
        figy.append('Trial mode: the solution is written to an APFS clone of the workspace. The note is unchanged.')
    return ([tasks.Step("Megoldás modellel és CAS-ellenőrzéssel", argv, str(cfg.root))],
            'The model solves the selected problem and runs its code in the CAS sandbox. The solution is placed below the problem in a `[!solution]` callout (machine write, undoable).', figy)


def regisztral() -> None:
    """A feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "Megoldás (matek)", _terv, resources=frozenset({"modell", "vault"}),
                                  graceful_stop=True))
