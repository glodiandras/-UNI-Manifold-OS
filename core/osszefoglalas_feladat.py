"""Az összefoglalás feladattípusai (C26b; `docs/C26-TERV.md` 7., 9. fejezet; CLAUDE.md 28., 49., 56. döntés, D8, D9).

- `osszefoglalas`: kézzel indított („Összefoglalás” a jegyzet helyi menüjéből vagy a ⌘P-ből; mappa és videó/hang szintre is), egy út,
  nem függ az automatikus feltételektől.
- `osszefoglalas_automatikus` (`automatikus=True`): a közös automatika-ütemező küldi be (`core/automatika.py`) az új vagy erősen
  módosult, 10 perce nem változott tantárgyi jegyzetekre; a `Kapu.admit` alatt indul (D8, aktív használat, memóriaőr), az
  Asszisztens-kapcsoló alatt. Csak jegyzet-szint.

Mindkettő modellt használ és a vaultba ír (`modell`, `vault` erőforrás). A lépés a `python -m modulok.osszefoglalas general`
alfolyamata: a jegyzetet a core-tól olvassa, a modellt a workeren át hívja (a `szoveg` router-feladat kalibrált modellje), és
összefoglalónként egy tételt ír a gépi-írás szolgáltatáson át (`Mos-Forras: mos-osszefoglalas`).

Paraméterek: `szint` (`jegyzet` | `mappa` | `video`; alap: `jegyzet`), `ut` (a jegyzet / mappa / média vault-relatív útja), `kiegeszit`
(mappa: a hiányzó jegyzet-összefoglalókat előbb elkészíti; alap igaz), `proba` (D9: az írás az APFS-klónra), `modell` (kifejezett
modell: csak próba). Automatikusan: `utak`.
"""
from __future__ import annotations

import sys

from . import mediatipus, tasks
from .config import Config

TIPUS = "osszefoglalas"
AUTO_TIPUS = "osszefoglalas_automatikus"
SZINTEK = ("jegyzet", "mappa", "video")
MAX_UT = 20


def _rel_ok(ut) -> bool:
    return isinstance(ut, str) and bool(ut.strip()) and not ut.startswith("/") and ".." not in ut.split("/") and "\x00" not in ut


def _md_ut(ut) -> bool:
    return _rel_ok(ut) and ut.lower().endswith(".md")


def _modellnev(cfg: Config, nev) -> str:
    from .modell import beallitas as B
    if not isinstance(nev, str) or not nev:
        raise tasks.Invalid("A `modell` egy regisztrált modell neve legyen.")
    try:
        m = B.betolt(cfg).modell(nev)
    except B.RegiszterHiba as exc:
        raise tasks.Invalid(str(exc)) from None
    if "szoveg" not in m.feladat:
        raise tasks.Invalid(f"A(z) {m.nev} nem `szoveg`-modell (a regiszter `feladat` listája).")
    return m.nev


def _argv(cfg: Config, szint: str, utak: list[str], p: dict, stop: str, automatikus: bool) -> tuple[list[str], list[str]]:
    for kulcs in ("proba", "kiegeszit"):
        if not isinstance(p.get(kulcs, False), bool):
            raise tasks.Invalid(f"A `{kulcs}` igaz vagy hamis lehet.")
    argv = [sys.executable, "-B", "-m", "modulok.osszefoglalas", "general", "--szint", szint, "--stop-fajl", stop]
    for u in utak:
        argv += ["--ut", u]
    if automatikus:
        argv.append("--automatikus")
    if szint == "mappa" and p.get("kiegeszit", True):
        argv.append("--kiegeszit")
    figy = []
    proba = bool(p.get("proba"))
    if p.get("modell") is not None:
        argv += ["--modell", _modellnev(cfg, p["modell"])]
        proba = True
    if proba:
        argv.append("--proba")
        figy.append('Trial mode: the summary is written to an APFS clone of the workspace. The workspace is unchanged.')
    return argv, figy


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    szint = p.get("szint", "jegyzet")
    if szint not in SZINTEK:
        raise tasks.Invalid(f"A `szint` {', '.join(SZINTEK)} lehet.")
    ut = p.get("ut")
    if szint == "jegyzet":
        if not _md_ut(ut):
            raise tasks.Invalid("Az `ut` a vault egy Markdown-jegyzetének relatív útja legyen.")
        from .automatika import kisero_elotag, tartalmi_ut
        if not tartalmi_ut(ut, kisero_elotag(cfg)):
            raise tasks.Invalid("Összefoglaló csak tartalmi jegyzetből készül (kísérőjegyzetből és rejtett mappából nem).")
        cim = "Összefoglaló a jegyzetből (modell + kapuk)"
        mit = ('The model suggests claims supported by exact quotations from the note. Claims that pass the gates go to the companion note, with block IDs and embeds added to the source (machine write, undoable).')
    elif szint == "mappa":
        if not _rel_ok(ut) or ut.lower().endswith(".md") or ut.rstrip("/").split("/")[0].startswith("."):
            raise tasks.Invalid("Az `ut` a vault egy mappájának relatív útja legyen.")
        from .automatika import kisero_elotag
        if ut.startswith(kisero_elotag(cfg)):
            raise tasks.Invalid("Gépi kísérőjegyzet-mappából nem készül mappa-összefoglaló.")
        ut = ut.rstrip("/")
        cim = "Összefoglaló a mappából (jegyzet-összefoglalókból)"
        mit = ('The model combines the folder’s note summaries into claims traceable to the original notes. Missing note summaries are created first. The companion note is written to the summaries folder (undoable).')
    else:
        if not _rel_ok(ut) or not ut.lower().endswith(tuple(k for k, t in mediatipus.MEDIA_TIPUS.items() if t.startswith(("video/", "audio/")))):
            raise tasks.Invalid("Az `ut` a vault egy videó- vagy hangfájljának relatív útja legyen.")
        cim = "Összefoglaló a videóból (az átirat alapján)"
        mit = ('The model suggests claims from the media transcript (VTT), with links to timestamps. The companion note is written to the summaries folder (undoable).')
    argv, figy = _argv(cfg, szint, [ut], p, stop, automatikus=False)
    return [tasks.Step(cim, argv, str(cfg.root))], mit, figy


def _auto_terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    utak = p.get("utak")
    if not isinstance(utak, list) or not 1 <= len(utak) <= MAX_UT or not all(_md_ut(u) for u in utak):
        raise tasks.Invalid(f"Az `utak` 1–{MAX_UT} jegyzet relatív útja legyen.")
    argv, figy = _argv(cfg, "jegyzet", utak, p, stop, automatikus=True)
    return ([tasks.Step("Összefoglalók az új vagy erősen módosult jegyzetekből", argv, str(cfg.root))],
            f"Create summaries for {len(utak)} notes (machine write, undoable).", figy)


def automatikus_szuro(cfg: Config):
    """Az automatikus összefoglaló-fogyasztó szűrője: tartalmi `.md` egy **tantárgyi** mappában (mint a kártyáé: a legfelső mappa első
    betűje a `[pdf.tags]` térképben áll, 30(f); a workflow-, napló-, projekt- és sablonmappák jegyzeteiből az automatika nem készít
    összefoglalót — kézzel igen)."""
    from . import kartya_feladat
    return kartya_feladat.automatikus_szuro(cfg)


def regisztral() -> None:
    """A két feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "Összefoglalás", _terv, resources=frozenset({"modell", "vault"}), graceful_stop=True))
    tasks.register(tasks.TaskType(AUTO_TIPUS, "Összefoglaló (automatikus)", _auto_terv, resources=frozenset({"modell", "vault"}),
                                  graceful_stop=True, automatikus=True))
