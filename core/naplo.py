"""A napi jegyzet (C15): megnyitás vagy létrehozás a `[naplo]` konfiguráció szerint.

Az útvonal egyetlen formátum-kulcsból jön (`[naplo] ut`, a sablonmotor formázójával; alap: `[Daily]/YYYY-MM-DD`, vagyis
`Daily/ÉÉÉÉ-HH-NN.md`), így kódban nincs beégetett vault-mappanév. A hónap- és napnevek nyelve a tartalmi nyelvé
(`sablon.tartalmi_nyelv`: kifejezett `[sablon] nyelv`, a munkatér nyelve, angol).

A váz (12-templates-08/09): a `[naplo] sablon` jegyzet — vault-relatív út (`Templates/Daily.md`, a `.md` elhagyható) vagy a
sablonmappa jegyzetének neve —, ha be van állítva és létezik; ha be van állítva, de nem oldódik fel, a semleges vázból készül a
jegyzet és a válasz `sablon_hiany` mezője jelzi, melyik sablont nem találta (a felület értesít); ha nincs beállítva sablon, a
beépített semleges váz (`# {{title}}` és a kurzor) jön. A régi v2-váz (`Tags`/`Source`/`Status`/`NN`/`Canvas`) csak a `v2-kompat`
presettel él (`[naplo] vaz = "v2"`); a `Status` mezőt ott is a felhasználó tölti (L33), és a `Canvas` csak létező havi canvasra mutat.
Mindegyik a `sablon.kiertekel` motoron megy át. Meglévő jegyzetet nem ír felül: ilyenkor csak az útját adja. A létrehozás a
`Vault.create` útján megy (kör-zár, atomi írás, egy gépi commit, WS-esemény).

Előző / következő nap (12-templates-04): a hivatkozási napot a megnyitott jegyzet útjából a formátum visszafejtése adja
(`nap_az_utbol`), különben a mai nap; a cél az adott irányban legközelebbi LÉTEZŐ napi jegyzet (legfeljebb `SZOMSZED_ABLAK` napon belül),
ennek híján a szomszédos naptári nap (létrehozva, mint a mai nap megnyitásakor).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from . import sablon
from .utvonalak import HttpError
from .vaultio import Invalid, NotFound, norm_path

ALAP_UT = "[Daily]/YYYY-MM-DD"          # semleges alap (a `[Daily]` szó szerinti: a `D` és az `a` formátum-jel); a vault saját konvencióját az os.toml `[naplo] ut` kulcsa adja
ALAP_CANVAS = "YYYY-MM"
ALAP_SABLON = ""                         # semleges alap: nincs sablon, a beépített váz jön
ALAP_VAZ = "semleges"
SZOMSZED_ABLAK = 400                     # ennyi napon belül keresi az előző / következő LÉTEZŐ napi jegyzetet
SEMLEGES_VAZ = "# {{title}}\n\n{{cursor}}\n"
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def beallitasok(cfg) -> dict:
    s = cfg.section("naplo")
    return {"ut": s.get("ut", ALAP_UT), "sablon": s.get("sablon", ALAP_SABLON), "canvas": s.get("canvas", ALAP_CANVAS),
            "vaz": s.get("vaz", ALAP_VAZ),
            "dolgozat_mappa": s.get("dolgozat_mappa", "Dolgozatok"), "naptar_regi_ora": float(s.get("naptar_regi_ora", 36))}


def datum_ertek(szoveg) -> date:
    """`ÉÉÉÉ-HH-NN` → date; hiányzó érték: a mai nap. Hibás: 400."""
    if szoveg is None or szoveg == "":
        return date.today()
    if not isinstance(szoveg, str) or not _DATUM.match(szoveg):
        raise HttpError(400, "a `datum` ÉÉÉÉ-HH-NN alakú", kod="naplo.datum_alak")
    try:
        return date.fromisoformat(szoveg)
    except ValueError:
        raise HttpError(400, "érvénytelen `datum`", kod="naplo.datum_ervenytelen") from None


def napi_ut(cfg, nap: date) -> str:
    """A napi jegyzet vault-relatív útja `.md`-vel."""
    dt = datetime(nap.year, nap.month, nap.day, 12, 0)
    return norm_path(sablon.datum_formatum(dt, beallitasok(cfg)["ut"], sablon.beallitasok(cfg)["nyelv"]) + ".md")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def havi_canvas(cfg, index, nap: date) -> str | None:
    """A havi canvas fájlneve (pl. `2026-10.canvas`), ha az indexben van; különben None."""
    dt = datetime(nap.year, nap.month, nap.day, 12, 0)
    nev = _nfc(sablon.datum_formatum(dt, beallitasok(cfg)["canvas"], sablon.beallitasok(cfg)["nyelv"])) + ".canvas"
    try:
        halmaz = index.fajl_halmaz()
    except Exception:       # az index még épül: a váz Canvas nélkül készül, a jegyzet attól még létrejön
        return None
    kis = nev.lower()
    return nev if any(u.rsplit("/", 1)[-1].lower() == kis for u in halmaz) else None


def v2_vaz(canvas: str | None) -> str:
    """A régi v2-váz (csak a `v2-kompat` presettel, `[naplo] vaz = "v2"`); `canvas`: a havi canvas fájlneve vagy None."""
    cv = f'Canvas: "[[{canvas}]]"' if canvas else "Canvas:"
    return f"---\nTags:\n  - Napló\nSource:\nStatus:\nNN:\n{cv}\n---\n\n# Napló\n\n{{{{cursor}}}}\n"


def alapvaz(cfg, index, nap: date) -> str:
    """A beépített váz a `[naplo] vaz` szerint: `semleges` (alap) vagy `v2`."""
    if beallitasok(cfg)["vaz"] == "v2":
        return v2_vaz(havi_canvas(cfg, index, nap))
    return SEMLEGES_VAZ


def sablon_ut(cfg) -> str | None:
    """A beállított napi sablon vault-relatív útja `.md`-vel, vagy None, ha nincs beállítva. A `/`-t vagy `.md`-t tartalmazó érték
    vault-relatív út; a puszta név a sablonmappa jegyzete (régi rövidítés). Érvénytelen út (`..`, rejtett mappa): Invalid."""
    nev = str(beallitasok(cfg)["sablon"] or "").strip()
    if not nev:
        return None
    nev = nev.replace("\\", "/")
    if "/" in nev or nev.lower().endswith(".md"):
        rp = nev if nev.lower().endswith(".md") else nev + ".md"
    else:
        rp = f"{sablon.beallitasok(cfg)['mappa']}/{nev}.md"
    return norm_path(rp)


def _vaz(vault, index, nap: date) -> tuple[str, str | None]:
    """→ (a váz szövege, a nem található sablon útja | None). A beállított sablon bármely vaulton belüli `.md` lehet (a
    `norm_path` védi a rejtett és a vaulton kívüli utat)."""
    try:
        rp = sablon_ut(vault.cfg)
    except Invalid:
        return alapvaz(vault.cfg, index, nap), str(beallitasok(vault.cfg)["sablon"]).strip()
    if rp is None:
        return alapvaz(vault.cfg, index, nap), None
    try:
        return vault.read(rp)["tartalom"], None
    except (NotFound, Invalid):
        return alapvaz(vault.cfg, index, nap), rp


def nap_az_utbol(cfg, ut) -> date | None:
    """A napi jegyzet napja az útjából (a `napi_ut` fordítottja); None, ha az út nem egy napi jegyzeté. Az évszámot az útból
    veszi (négyjegyű számok), ennek híján ±30 évet próbál; a hónap- és napnevek a tartalmi nyelvvel képződnek."""
    try:
        cel = norm_path(ut)
    except Invalid:
        return None
    evek = {int(x) for x in re.findall(r"(?<!\d)(\d{4})(?!\d)", cel) if 1900 <= int(x) <= 2200}
    evek |= {e + k for e in set(evek) for k in (-1, 1)}                      # a hét-év (`gggg`) és a határnapok
    if not evek:
        ma = date.today().year
        evek = set(range(ma - 30, ma + 6))
    for ev in sorted(evek):
        nap = date(ev, 1, 1)
        while nap.year == ev:
            if napi_ut(cfg, nap) == cel:
                return nap
            nap += timedelta(days=1)
    return None


def megnyit_vagy_letrehoz(app, szoveg_datum=None) -> dict:
    """A `POST /api/naplo/ma` törzse: `{ut, letrejott, kurzor, figyelmeztetes, sablon_hiany}`. A `kurzor` csak létrehozáskor van;
    a `sablon_hiany` a beállított, de nem található sablon útja (a jegyzet ilyenkor a semleges vázból készült)."""
    vault = app.vault
    nap = datum_ertek(szoveg_datum)
    rp = napi_ut(vault.cfg, nap)
    if vault._abs(rp).is_file():
        return {"ut": rp, "letrejott": False, "kurzor": None, "figyelmeztetes": None, "sablon_hiany": None}
    mappa, _, nev = rp.rpartition("/")
    nev = nev[:-3]
    sb = sablon.beallitasok(vault.cfg)
    most = datetime.now().astimezone().replace(year=nap.year, month=nap.month, day=nap.day)
    vaz, hiany = _vaz(vault, app.index, nap)
    e = sablon.kiertekel(vaz, nev, most, nyelv=sb["nyelv"], datum=sb["datum"], ido=sb["ido"])
    try:
        d = vault.create({"mappa": mappa, "nev": nev, "tartalom": e.szoveg, "mappa_keszit": True})
    except (Invalid, FileExistsError):
        if vault._abs(rp).is_file():                         # a versenyhelyzet vesztese: a másik létrehozta
            return {"ut": rp, "letrejott": False, "kurzor": None, "figyelmeztetes": None, "sablon_hiany": None}
        raise
    return {"ut": d["ut"], "letrejott": True, "kurzor": e.kurzor, "figyelmeztetes": d.get("figyelmeztetes"),
            "sablon_hiany": hiany}


def szomszed(app, ut=None, datum=None, irany="elozo") -> dict:
    """A `POST /api/naplo/szomszed` törzse: az előző (`elozo`) vagy következő (`kovetkezo`) napi jegyzet megnyitása, mint a
    `megnyit_vagy_letrehoz`; a válasz kiegészül a `datum` mezővel. A hivatkozási nap: a kifejezett `datum`, különben az `ut`
    napi jegyzetének napja, különben a mai nap."""
    if irany not in ("elozo", "kovetkezo"):
        raise HttpError(400, "az `irany` elozo vagy kovetkezo lehet", kod="naplo.irany")
    lepes = -1 if irany == "elozo" else 1
    if datum not in (None, ""):
        ref = datum_ertek(datum)
    else:
        ref = (nap_az_utbol(app.vault.cfg, ut) if isinstance(ut, str) and ut.strip() else None) or date.today()
    cel = ref + timedelta(days=lepes)
    for i in range(1, SZOMSZED_ABLAK + 1):
        try:
            nap = ref + timedelta(days=lepes * i)
        except OverflowError:
            break
        if app.vault._abs(napi_ut(app.vault.cfg, nap)).is_file():
            cel = nap
            break
    r = megnyit_vagy_letrehoz(app, cel.isoformat())
    return {**r, "datum": cel.isoformat()}


def utvonalak(r) -> None:
    r.post("/api/naplo/ma", lambda k: megnyit_vagy_letrehoz(k.app, k.torzs().get("datum")))
    r.post("/api/naplo/szomszed", lambda k: szomszed(k.app, k.torzs().get("ut"), k.torzs().get("datum"), k.torzs().get("irany")))
