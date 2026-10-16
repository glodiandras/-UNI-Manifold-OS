"""A napi jegyzet (C15): megnyitás vagy létrehozás a vault konvenciója szerint.

A konvenció: a napi jegyzet a `[naplo] ut` formátum-kulcs szerinti útra kerül (alap, ha a kulcs hiányzik: `Daily/ÉÉÉÉ-HH-NN.md`),
frontmatter `Tags: [Napló]`, üres `Source`, `Status`, `NN`, a `Canvas` a havi canvasra mutat, H1 = `# Napló`.
Az útvonal egyetlen formátum-kulcsból jön (a sablonmotor formázójával), így kódban nincs beégetett vault-mappanév.

A `Status` mezőt a felhasználó tölti (L33): az alapváz üresen hagyja, a core soha nem tölti ki. A `Canvas` mező
csak akkor mutat a havi canvasra, ha az az indexben létezik (nincs törött link).

A váz: a sablonmappa `[naplo] sablon` nevű jegyzete, ha van (a felhasználó így szabja testre; a vaultba a kód
sablont nem ír), különben a beépített. Mindkettő a `sablon.kiertekel` motoron megy át. Meglévő jegyzetet nem ír
felül: ilyenkor csak az útját adja. A létrehozás a `Vault.create` útján megy (kör-zár, atomi írás, egy gépi
commit, WS-esemény).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from . import sablon
from .utvonalak import HttpError
from .vaultio import Invalid, NotFound, norm_path

ALAP_UT = "Daily/YYYY-MM-DD"            # semleges alap; a vault saját konvencióját az os.toml `[naplo] ut` kulcsa adja
ALAP_CANVAS = "YYYY-MM"
ALAP_SABLON = "Napi jegyzet"
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def beallitasok(cfg) -> dict:
    s = cfg.section("naplo")
    return {"ut": s.get("ut", ALAP_UT), "sablon": s.get("sablon", ALAP_SABLON), "canvas": s.get("canvas", ALAP_CANVAS),
            "dolgozat_mappa": s.get("dolgozat_mappa", "Dolgozatok"), "naptar_regi_ora": float(s.get("naptar_regi_ora", 36))}


def datum_ertek(szoveg) -> date:
    """`ÉÉÉÉ-HH-NN` → date; hiányzó érték: a mai nap. Hibás: 400."""
    if szoveg is None or szoveg == "":
        return date.today()
    if not isinstance(szoveg, str) or not _DATUM.match(szoveg):
        raise HttpError(400, "a `datum` ÉÉÉÉ-HH-NN alakú")
    try:
        return date.fromisoformat(szoveg)
    except ValueError:
        raise HttpError(400, "érvénytelen `datum`") from None


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


def alapvaz(canvas: str | None) -> str:
    """A beépített váz (a `sablon.kiertekel` kapja); `canvas`: a havi canvas fájlneve vagy None."""
    cv = f'Canvas: "[[{canvas}]]"' if canvas else "Canvas:"
    return f"---\nTags:\n  - Napló\nSource:\nStatus:\nNN:\n{cv}\n---\n\n# Napló\n\n{{{{cursor}}}}\n"


def _vaz(vault, index, nap: date) -> str:
    b = beallitasok(vault.cfg)
    mappa = sablon.beallitasok(vault.cfg)["mappa"]
    nev = b["sablon"]
    if nev:
        try:
            return sablon.olvas(vault, f"{mappa}/{nev}.md")
        except (NotFound, Invalid):
            pass
    return alapvaz(havi_canvas(vault.cfg, index, nap))


def megnyit_vagy_letrehoz(app, szoveg_datum=None) -> dict:
    """A `POST /api/naplo/ma` törzse: `{ut, letrejott, kurzor, figyelmeztetes}`. A `kurzor` csak létrehozáskor van."""
    vault = app.vault
    nap = datum_ertek(szoveg_datum)
    rp = napi_ut(vault.cfg, nap)
    if vault._abs(rp).is_file():
        return {"ut": rp, "letrejott": False, "kurzor": None, "figyelmeztetes": None}
    mappa, _, nev = rp.rpartition("/")
    nev = nev[:-3]
    sb = sablon.beallitasok(vault.cfg)
    most = datetime.now().astimezone().replace(year=nap.year, month=nap.month, day=nap.day)
    e = sablon.kiertekel(_vaz(vault, app.index, nap), nev, most, nyelv=sb["nyelv"], datum=sb["datum"], ido=sb["ido"])
    try:
        d = vault.create({"mappa": mappa, "nev": nev, "tartalom": e.szoveg, "mappa_keszit": True})
    except (Invalid, FileExistsError):
        if vault._abs(rp).is_file():                         # a versenyhelyzet vesztese: a másik létrehozta
            return {"ut": rp, "letrejott": False, "kurzor": None, "figyelmeztetes": None}
        raise
    return {"ut": d["ut"], "letrejott": True, "kurzor": e.kurzor, "figyelmeztetes": d.get("figyelmeztetes")}


def utvonalak(r) -> None:
    r.post("/api/naplo/ma", lambda k: megnyit_vagy_letrehoz(k.app, k.torzs().get("datum")))
