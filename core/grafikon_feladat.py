"""A ```plot beírásának feladattípusai (C35b-mag; CLAUDE.md 2., 3., 5., 28. és 80(a) döntés, D8).

80(a), AI csak gombra: a **`grafikon_beiras` kézi** (`automatikus=False`): a „Grafikonok beírása ebbe a jegyzetbe” parancs (⌘P) és a
vezérlő indítja kifejezett kérésre, a D8-kapu aktív használat-szünete nélkül (a memóriaőr a `modell` erőforrás miatt marad). A
**`grafikon_automatikus`** (`automatikus=True`) a közös ütemező feladata, de az ütemező csak a `[grafikon.automatika] be = true`
kulccsal köti rá (alapból nem): ekkor a `Kapu.admit` alatt fut (D8 indulási szünet, aktív használat alatt nem, kevés szabad
memóriánál nem). Mindkettő ugyanaz a lépés. A lépés a `modulok/grafikon/__main__.py automatikus`
alfolyamata: a vault jegyzeteit **csak olvassa**, az írás a gépi-írás szolgáltatáson át megy (egy jegyzet = egy tétel = egy gépi
commit, `Mos-Forras: mos-plot`). A determinisztikus ág modellt nem tölt; a **modell-ág** (a `bizonytalan` képletekre, C35b) a
`grafikon` router-feladat kalibrált modelljét hívja a workeren át — éles írása csak a `[grafikon.automatika] modell_ag = true`
kapcsolóval (alapból hamis: az éles blokk-író prompt mérése és a 0 téves blokk igazolása előtt a modell-ág nem ír élesben).

Paraméterek: `utak` (a közös ütemező adja: a feldolgozandó jegyzetek relatív útjai; nélküle a lépés a vaultot maga járja be a közös
döntéssel), `proba` (igaz: az írás a vault APFS-klónjára megy, D9; az állapottárhoz nem nyúl), `modell_ag` (csak `proba`
mellett: a modell-ág is fut, a kimenete próba), `max` (legfeljebb ennyi jegyzet; alap a `[grafikon.automatika] max_jegyzet`).
A feladat vault-író és modell-igényes (`vault`, `modell` erőforrás): a többi modell-feladat mellett nem fut egyszerre.
"""
from __future__ import annotations

import sys

from . import tasks
from .config import Config

TIPUS = "grafikon_beiras"
AUTOMATIKUS = "grafikon_automatikus"
MAX_JEGYZET = 50
MAX_UT = 20


def _rel_md(ut) -> bool:
    return (isinstance(ut, str) and bool(ut.strip()) and ut.lower().endswith(".md") and not ut.startswith("/")
            and ".." not in ut.split("/") and "\x00" not in ut)


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    for kulcs in ("proba", "modell_ag"):
        if not isinstance(p.get(kulcs, False), bool):
            raise tasks.Invalid(f"A `{kulcs}` igaz vagy hamis lehet.")
    if p.get("modell_ag") and not p.get("proba"):
        raise tasks.Invalid("A `modell_ag` kézzel csak `proba` mellett kérhető (az éles modell-ág a beállítás kapcsolója).")
    utak = p.get("utak")
    if utak is not None:
        from .automatika import kisero_elotag, tartalmi_ut
        elotag = kisero_elotag(cfg)
        if (not isinstance(utak, list) or not 1 <= len(utak) <= MAX_UT
                or not all(_rel_md(u) and tartalmi_ut(u, elotag) for u in utak)):
            raise tasks.Invalid(f"Az `utak` 1–{MAX_UT} tartalmi jegyzet relatív útja legyen.")
    argv = [sys.executable, "-B", str(cfg.path("modulok") / "grafikon" / "__main__.py"), "automatikus", "--eles",
            "--stop-fajl", stop]
    for u in utak or ():
        argv += ["--ut", u]
    if p.get("proba"):
        argv.append("--proba")
    if p.get("modell_ag"):
        argv.append("--modell-ag")
    if "max" in p:
        m = p["max"]
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= MAX_JEGYZET:
            raise tasks.Invalid(f"A `max` 1–{MAX_JEGYZET} egész szám legyen.")
        argv += ["--max", str(m)]
    figyelmeztetes = ["Próbamód: a blokkok a vault APFS-klónjára kerülnek, a vaultba nem."] if p.get("proba") else []
    return ([tasks.Step("Grafikonok a képletek alá", argv, str(cfg.root))],
            "A frissen szerkesztett jegyzetek biztosan felismert képletei alá ```plot blokk kerül (gépi írás, visszavonható).",
            figyelmeztetes)


def regisztral() -> None:
    """A feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "Grafikonok a képletek alá", _terv, resources=frozenset({"modell", "vault"}),
                                  graceful_stop=True))
    tasks.register(tasks.TaskType(AUTOMATIKUS, "Grafikonok a képletek alá (automatikus)", _terv,
                                  resources=frozenset({"modell", "vault"}), graceful_stop=True, automatikus=True))
