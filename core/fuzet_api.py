"""A füzetlánc és a képlet-OCR végpontjai (C21).

- `GET /api/fuzet/allapot` — a lánc összesítője: a fotók állapota, a legutóbbi tételek, a figyelt mappák, a figyelő utolsó köre.
- `POST /api/fuzet/bejovo` `{nev, adat (base64), csoport?}` — egy behúzott/kiválasztott fotó a `{fuzet_bejovo}/<csoport>/` alá (a vaulton
  kívül; felülírás nélkül). A feldolgozást a `fuzet_lanc` feladat indítja (`POST /api/feladatok`, `{csoport, cel?}`).
- `POST /api/keplet-ocr` — 5. pont: a vágólap képe (a `osascript` `«class PNGf»` alakján, a `{tmp}` alá) → a worker `ocr_keplet`
  feladata (kalibrált: `glm_ocr`; interaktív mód) → `{latex}`. A prompt és a kinyerés az eval-feladaté (`modulok/eval/ocr_keplet`):
  a kalibráció arra a kérésre szól. A vaultba nem ír; a felület a kurzorhoz szúrja a szerkesztő egyetlen írási útján.

A lépés-kapu (`core/lepes_kapu.py`) döntéstáblájában mindhárom író végpont a lépés-folyamat számára tiltott (felületi művelet).
"""
from __future__ import annotations

import base64
import binascii
import importlib.util
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

from . import fuzet
from .modell import kliens
from .utvonalak import HttpError

MAX_FOTO_BAJT = 11 * 1024 * 1024               # a JSON-törzs 16 MiB-os korlátja alatt, base64-gyel
MAX_VAGOLAP_BAJT = 20 * 1024 * 1024
VAGOLAP_IDO_MP = 10
_NEV = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
_VAGOLAP_SZKRIPT = """on run argv
  try
    set d to the clipboard as «class PNGf»
  on error
    return "NINCS"
  end try
  set f to open for access (POSIX file (item 1 of argv)) with write permission
  set eof f to 0
  write d to f
  close access f
  return "OK"
end run
"""
_ocr_keplet = None


def _keplet_modul(cfg):
    global _ocr_keplet
    if _ocr_keplet is None:
        ut = cfg.path("modulok") / "eval" / "ocr_keplet" / "feladat.py"
        spec = importlib.util.spec_from_file_location("mos_core_ocr_keplet", ut)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ocr_keplet = mod
    return _ocr_keplet


# ---------------------------------------------------------------- állapot

def allapot(app) -> dict:
    st = fuzet.allapot_betolt(app.cfg)
    db: dict[str, int] = {}
    for r in st.values():
        db[r.get("allapot") or "?"] = db.get(r.get("allapot") or "?", 0) + 1
    legutobbi = sorted(({"sha256": sha[:12], **{k: r.get(k) for k in ("kep", "allapot", "bekotve", "uzenet", "ido", "kor")}}
                        for sha, r in st.items()), key=lambda r: r.get("ido") or "", reverse=True)[:30]
    mappak = []
    for m in fuzet.figyelt_mappak(app.cfg):
        mappak.append({"ut": str(m), "letezik": m.is_dir()})
    fig = getattr(app, "fuzet_figyelo", None)
    return {"foto": len(st), "allapot": db, "legutobbi": legutobbi, "figyelt_mappak": mappak,
            "figyelo": getattr(fig, "utolso", {}) if fig else {}}


# ---------------------------------------------------------------- bevitel

def biztonsagos_nev(nev: str) -> str:
    nev = fuzet.nfc(os.path.basename(str(nev or "")).strip())
    nev = _NEV.sub("_", nev).lstrip(".")
    if not nev or not nev.lower().endswith(fuzet.KEP_KITERJESZTESEK) or len(nev.encode("utf-8")) > 200:
        raise HttpError(400, "csak .jpg, .jpeg, .png vagy .heic füzetfotó tölthető fel (legfeljebb 200 bájtos névvel)", kod="fuzet_api.csak_kepformatum")
    return nev


def bejovo(app, body: dict) -> dict:
    nev = biztonsagos_nev(body.get("nev"))
    csoport = body.get("csoport") or time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    if not isinstance(csoport, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", csoport):
        raise HttpError(400, "érvénytelen csoport-azonosító", kod="fuzet_api.ervenytelen_csoport_azonosito")
    adat = body.get("adat")
    if not isinstance(adat, str) or len(adat) > MAX_FOTO_BAJT * 4 // 3 + 8:
        raise HttpError(413 if isinstance(adat, str) else 400, "a fotó base64-kódolt `adat` mezőben jön, legfeljebb 11 MiB", kod="fuzet_api.foto_base64_mezo")
    try:
        b = base64.b64decode(adat, validate=True)
    except (binascii.Error, ValueError):
        raise HttpError(400, "az `adat` nem érvényes base64", kod="fuzet_api.adat_nem_base64") from None
    if not b or len(b) > MAX_FOTO_BAJT:
        raise HttpError(413, "üres vagy túl nagy fotó", kod="fuzet_api.ures_tul_nagy_foto")
    d = app.cfg.path("fuzet_bejovo") / csoport
    d.mkdir(parents=True, exist_ok=True)
    torzs, kit = os.path.splitext(nev)
    for i in range(1, 1000):                        # felülírás nélkül: ütközésnél `(2)`, `(3)` …
        cel = d / (nev if i == 1 else f"{torzs} ({i}){kit}")
        try:
            with open(cel, "xb") as fh:
                fh.write(b)
            break
        except FileExistsError:
            continue
    else:
        raise HttpError(409, "nincs szabad név a beérkező mappában", kod="fuzet_api.nincs_szabad_nev")
    return {"ok": True, "csoport": csoport, "nev": cel.name, "meret": len(b), "sha256": fuzet.sha256(cel)}


# ---------------------------------------------------------------- képlet-OCR (5. pont)

def vagolap_kep(cel: Path, futtat=subprocess.run) -> bool:
    """A vágólap képe PNG-ként a `cel` fájlba (`osascript`; a képernyőkép TIFF/PNG-jét a rendszer alakítja át). → volt-e kép."""
    cel.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = futtat(["/usr/bin/osascript", "-", str(cel)], input=_VAGOLAP_SZKRIPT, capture_output=True, text=True,
                   timeout=VAGOLAP_IDO_MP)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HttpError(503, f"a vágólap nem olvasható: {e}", kod="fuzet_api.vagolap_nem_olvashato", param={"e": e}) from None
    if (r.stdout or "").strip() != "OK" or not cel.is_file() or cel.stat().st_size == 0:
        return False
    if cel.stat().st_size > MAX_VAGOLAP_BAJT:
        cel.unlink(missing_ok=True)
        raise HttpError(413, "a vágólap képe túl nagy", kod="fuzet_api.vagolap_kepe_tul_nagy")
    return True


def keplet_ocr(app, body: dict, vagolap=vagolap_kep, chat=kliens.chat) -> dict:
    if not isinstance(body, dict) or body:
        raise HttpError(400, "a kérés törzse üres objektum: a képet a core a vágólapról olvassa", kod="fuzet_api.torzs_ures_objektum")
    cel =app.cfg.path("tmp") / "keplet-ocr" / f"vagolap-{secrets.token_hex(4)}.png"
    try:
        if not vagolap(cel):
            raise HttpError(404, "a vágólapon nincs kép — készíts képernyőképet a képletről (⌃⇧⌘4), aztán próbáld újra", kod="fuzet_api.vagolapon_nincs_kep",
                            nincs_kep=True)
        mod = _keplet_modul(app.cfg)
        u = app.worker.biztosit()
        try:
            r = chat(u, [{"role": "user", "content": mod.PROMPT}], feladat="ocr_keplet", mod="interaktiv",
                     images=[str(cel)], max_tokens=int(mod.ARANY["max_token"]), temperature=0.0)
        except kliens.KliensHiba as e:
            raise HttpError(503 if e.kod >= 500 else 400, f"a képlet-olvasó modell nem válaszolt: {e}", kod="fuzet_api.keplet_modell_nem_valaszolt", param={"e": e},
                            modell_hiba=True) from None
        szoveg = r["choices"][0]["message"]["content"]
        latex = mod.jelolt(szoveg).strip().strip("$").strip()
        if not latex:
            raise HttpError(422, "a modell nem adott képletet", kod="fuzet_api.nincs_keplet", nyers=szoveg[:500])
        return {"ok": True, "latex": latex, "modell": r.get("modell"), "proba": bool(r.get("proba")), "mp": r.get("mp")}
    finally:
        cel.unlink(missing_ok=True)


def utvonalak(r) -> None:
    r.get("/api/fuzet/allapot", lambda k: allapot(k.app))
    r.post("/api/fuzet/bejovo", lambda k: bejovo(k.app, k.torzs()))
    r.post("/api/keplet-ocr", lambda k: keplet_ocr(k.app, k.torzs()))
