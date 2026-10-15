"""A kártya-generálás feladattípusai (C23b; `docs/C23-TERV.md` 5–6. fejezet; CLAUDE.md 28., 45., 56. döntés, D8, D9).

- `kartya_general`: kézzel indított („Kártyák ebből” a jegyzet helyi menüjéből vagy a ⌘P-ből), egy jegyzet, a teljes
  mennyiség (a sűrűségből, legfeljebb `[kartya.generalas] max_kartya`).
- `kartya_automatikus` (`automatikus=True`): a közös automatika-ütemező küldi be (`core/automatika.py`) az új vagy erősen
  módosult, 10 perce nem változott jegyzetekre; a `Kapu.admit` alatt indul (D8, aktív használat, memóriaőr), az
  Asszisztens-kapcsoló alatt; jegyzetenként legfeljebb `auto_max_kartya`.

Mindkettő modellt használ és a vaultba ír (`modell`, `vault` erőforrás). A lépés a `python -m modulok.kartya general`
alfolyamata: a jegyzetet a core-tól olvassa, a modellt a workeren át hívja (a `szoveg` router-feladat kalibrált modellje),
és jegyzetenként egy tételt ír a gépi-írás szolgáltatáson át (`Mos-Forras: mos-kartya`).

Paraméterek: `ut` (kézi; `kijeloles`: a kijelölt szöveg, csak abból kérdez) / `utak` (automatikus), `proba` (D9: az írás az APFS-klónra), `modell` (kifejezett modell: csak próba).
"""
from __future__ import annotations

import sys

from . import tasks
from .config import Config

TIPUS = "kartya_general"
AUTO_TIPUS = "kartya_automatikus"
MAX_UT = 20
MAX_KIJELOLES = 20000


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
    if "szoveg" not in m.feladat:
        raise tasks.Invalid(f"A(z) {m.nev} nem `szoveg`-modell (a regiszter `feladat` listája).")
    return m.nev


def _argv(cfg: Config, utak: list[str], p: dict, stop: str, automatikus: bool) -> tuple[list[str], list[str]]:
    if not isinstance(p.get("proba", False), bool):
        raise tasks.Invalid("A `proba` igaz vagy hamis lehet.")
    argv = [sys.executable, "-B", "-m", "modulok.kartya", "general", "--stop-fajl", stop]
    for u in utak:
        argv += ["--ut", u]
    if automatikus:
        argv.append("--automatikus")
    figy = []
    proba = bool(p.get("proba"))
    if p.get("modell") is not None:
        argv += ["--modell", _modellnev(cfg, p["modell"])]
        proba = True
    if proba:
        argv.append("--proba")
        figy.append("Próbamód (D9): a kártyák a vault APFS-klónjára kerülnek, a vaultba nem.")
    return argv, figy


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    if not _ut_ok(p.get("ut")):
        raise tasks.Invalid("Az `ut` a vault egy Markdown-jegyzetének relatív útja legyen.")
    if not kezi_szuro(cfg)(p["ut"]):
        raise tasks.Invalid("Kártya csak tartalmi jegyzetből készül (kísérőjegyzetből és rejtett mappából nem).")
    argv, figy = _argv(cfg, [p["ut"]], p, stop, automatikus=False)
    k = p.get("kijeloles")
    if k is not None:
        if not isinstance(k, str) or len(k) > MAX_KIJELOLES:
            raise tasks.Invalid(f"A `kijeloles` a jegyzet kijelölt szövege legyen (legfeljebb {MAX_KIJELOLES} jel).")
        if k.strip():
            argv += ["--kijeloles", k]
    return ([tasks.Step("Kártyák a jegyzetből (modell + kapuk)", argv, str(cfg.root))],
            "A modell kártyákat javasol a jegyzetből; a kapukon átment kártyák a kísérőjegyzetbe kerülnek, a forrásba "
            "blokkazonosító és beágyazó sor (gépi írás, visszavonható).", figy)


def _auto_terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    utak = p.get("utak")
    if not isinstance(utak, list) or not 1 <= len(utak) <= MAX_UT or not all(_ut_ok(u) for u in utak):
        raise tasks.Invalid(f"Az `utak` 1–{MAX_UT} jegyzet relatív útja legyen.")
    argv, figy = _argv(cfg, utak, p, stop, automatikus=True)
    return ([tasks.Step("Kártyák az új vagy erősen módosult jegyzetekből", argv, str(cfg.root))],
            f"{len(utak)} jegyzet kap kártyákat (jegyzetenként legfeljebb néhányat; gépi írás, visszavonható).", figy)


def kezi_szuro(cfg: Config):
    """A kézi „Kártyák ebből” szűrője: tartalmi `.md` (nem kísérőjegyzet, nem rejtett mappa)."""
    from .automatika import tartalmi_ut
    return tartalmi_ut


def automatikus_szuro(cfg: Config):
    """Az automatikus kártya-fogyasztó szűrője: tartalmi `.md` egy **tantárgyi** mappában — a legfelső mappa első betűje a
    `[pdf.tags]` térképben áll (a tracker tantárgy-szabálya, 30(f); a workflow-, napló-, projekt- és sablonmappák jegyzetei a
    tanulásnak nem forrásai, ezekből az automatika nem készít kártyát — kézzel igen)."""
    from .automatika import tartalmi_ut
    betuk = frozenset(k for k in cfg.section("pdf", "tags"))

    def szuro(ut: str) -> bool:
        felso = ut.replace("\\", "/").split("/", 1)
        return tartalmi_ut(ut) and len(felso) == 2 and felso[0][:1] in betuk
    return szuro


def regisztral() -> None:
    """A két feladattípus felvétele (idempotens; a `vezerlo.utvonalak` hívja)."""
    tasks.register(tasks.TaskType(TIPUS, "Kártyák ebből", _terv, resources=frozenset({"modell", "vault"}), graceful_stop=True))
    tasks.register(tasks.TaskType(AUTO_TIPUS, "Kártyák (automatikus)", _auto_terv, resources=frozenset({"modell", "vault"}),
                                  graceful_stop=True, automatikus=True))
