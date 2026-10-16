"""A füzetlánc feladattípusai (C21; CLAUDE.md 2., 3., 28. döntés, D8, D9).

- `fuzet_lanc` (kézi): a figyelt mappák új fotói, vagy egy feltöltött csoport (`csoport`: a `{fuzet_bejovo}/<csoport>/` mappa);
  `cel`: „Beszúrás az aktív jegyzetbe” (a választó nem fut, a fotók ebbe a jegyzetbe kerülnek); `proba`: a vault APFS-klónjára.
- `fuzet_automatikus` (`automatikus=True`; 80(a): a figyelő alapból nem indul, `[fuzet] figyelo_be`): a figyelő (`core/fuzet_figyelo.py`) küldi be, ha a figyelt mappában új fotó áll; a
  `Kapu.admit` alatt indul (D8 indulási szünet, aktív használat alatt nem, memóriaőr), az Asszisztens kikapcsolásakor a sorban vár
  (27(c), 9. pont), a worker `auto` módban futtatja a kéréseit (a nagy modell csak tétlenségben).
- `fuzet_ellenoriz` (kézi): a bekötött fotók újradöntése, eltérésnél átkötés (`mos-fuzet-ellenor`).

Mindegyik `resources={"modell", "vault"}` és `graceful_stop` (a folyamatban lévő fotó végigfut, L54). A lépés a
`modulok/fuzet/__main__.py` alfolyamata: a vaultot csak olvassa, az írás a gépi-írás szolgáltatáson át megy (28(a)).
"""
from __future__ import annotations

import re
import sys

from . import kiserok, tasks
from .config import Config

LANC, AUTOMATIKUS, ELLENORIZ = "fuzet_lanc", "fuzet_automatikus", "fuzet_ellenoriz"
CSOPORT = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_FOTO = 200


def _alap(cfg: Config, p: dict, stop: str, parancs: str) -> list[str]:
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    if not isinstance(p.get("proba", False), bool):
        raise tasks.Invalid("A `proba` igaz vagy hamis lehet.")
    argv = [sys.executable, "-B", str(cfg.path("modulok") / "fuzet" / "__main__.py"), parancs, "--stop-fajl", stop]
    if p.get("proba"):
        argv.append("--proba")
    return argv


def _max(p: dict, argv: list[str], kapcsolo: str) -> None:
    if "max" in p:
        m = p["max"]
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= MAX_FOTO:
            raise tasks.Invalid(f"A `max` 1–{MAX_FOTO} egész szám legyen.")
        argv += [kapcsolo, str(m)]


def _lanc_terv(cfg: Config, p: dict, stop: str, automatikus: bool = False):
    argv = _alap(cfg, p, stop, "lanc")
    _max(p, argv, "--max")
    cel = p.get("cel")
    if cel is not None:
        if automatikus or not isinstance(cel, str) or not cel.endswith(".md") or ".." in cel.split("/") or cel.startswith("/"):
            raise tasks.Invalid("A `cel` a vault egy jegyzete (`.md`, vault-relatív út) lehet.")
        if not (cfg.path("vault") / cel).is_file():
            raise tasks.Invalid(f"Nincs ilyen jegyzet: {cel}")
        argv += ["--cel", cel]
    csoport = p.get("csoport")
    if csoport is not None:
        if automatikus or not isinstance(csoport, str) or not CSOPORT.fullmatch(csoport):
            raise tasks.Invalid("A `csoport` a feltöltött fotók csoport-azonosítója.")
        argv.append(str(cfg.path("fuzet_bejovo") / csoport))
    figyelm = ["Próbamód: az írás a vault APFS-klónjára megy, a fotók a helyükön maradnak."] if p.get("proba") else []
    cim = "Füzetfotók az aktív jegyzetbe" if cel else "Füzetfotók bekötése"
    fz = cfg.section("fuzet")
    szakasz, cel_mappa = fz.get("szakasz") or "Füzet", kiserok.kisero_mappa(cfg, "fuzet")
    osszeg = (f"A fotók a megadott jegyzet „## {szakasz}” szakaszába kerülnek, alattuk a képletek (gépi írás, visszavonható)."
              if cel else
              f"Az új füzetfotók a választott jegyzet „## {szakasz}” szakaszába kerülnek, alattuk a képletek; a fotó a "
              f"„{cel_mappa}” alá költözik (gépi írás, fotónként visszavonható).")
    return [tasks.Step(cim, argv, str(cfg.root))], osszeg, figyelm


def _ellenoriz_terv(cfg: Config, p: dict, stop: str):
    argv = _alap(cfg, p, stop, "ellenoriz")
    _max(p, argv, "--limit")
    return ([tasks.Step("Füzet-bekötések ellenőrzése", argv, str(cfg.root))],
            "A bekötött füzetfotók újradöntése; eltérésnél a beágyazás a jobb jegyzetbe költözik (gépi írás, visszavonható).",
            ["Próbamód: csak javaslat, a vault nem változik."] if p.get("proba") else [])


def regisztral() -> None:
    """A feladattípusok felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    eroforras = frozenset({"modell", "vault"})
    tasks.register(tasks.TaskType(LANC, "Füzetfotók bekötése", _lanc_terv, resources=eroforras, graceful_stop=True))
    tasks.register(tasks.TaskType(AUTOMATIKUS, "Füzetfotók (automatikus)",
                                  lambda cfg, p, stop: _lanc_terv(cfg, p, stop, automatikus=True),
                                  resources=eroforras, graceful_stop=True, automatikus=True))
    tasks.register(tasks.TaskType(ELLENORIZ, "Füzet-bekötések ellenőrzése", _ellenoriz_terv, resources=eroforras,
                                  graceful_stop=True))
