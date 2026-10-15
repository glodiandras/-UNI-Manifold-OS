"""A staging forrásmappa olvasása, leltára és visszajelzése (C20a) — a legacy `media_staging.py` modell- és vault-író nélküli része.

A staging a letöltő (`msp`) igazsága: `<szolgáltató>/<tárgy>/<cím>/{video.*, source.md, transcript.md, metadata.json,
integration.json}`. Ez a modul **olvas**, és egyetlen mezőt ír vissza (`integration.json` `integration_status`, atomi csere), pontosan
mint a legacy. A vault sidecar-jainak előállítása (`.info.json`, `.vtt` az átiratból) és a forrásleíró jegyzet a C20b `vaultoldal.py`-ja,
a vaultba kerülés az `integralas.py` (a legacy `letoltes_helyett`/`szovegreteg_helyett` munkamappás másolása helyett a gépi írás
`mozgat` + `uj` művelete).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

SEMA = 1        # a msp staging-sémájának verziója (`schema_version`), amelyre ez a modul épül
INTEGRATION_ALLAPOTOK = ("pending", "in_review", "integrated", "rejected")
_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


class StagingHiba(Exception):
    """A mappa nem vehető át — az ok a staging-mappáé, nem a láncé (a lánc nem javítja, jelenti)."""


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def frontmatter(ut: str | Path) -> tuple[dict, str]:
    """(mezők, törzs) — a msp jegyzeteinek frontmattere: `kulcs: érték` sorok, az érték JSON-skalár (idézőjeles szöveg, szám,
    true/false/null); ami nem az, szövegként marad."""
    txt = Path(ut).read_text(encoding="utf-8")
    m = _FM.match(txt)
    if not m:
        raise StagingHiba(f"nincs frontmatter: {ut}")
    ki = {}
    for sor in m.group(1).splitlines():
        if not sor.strip() or sor[0] in " #-" or ":" not in sor:
            continue
        k, v = sor.split(":", 1)
        v = v.strip()
        try:
            ki[k.strip()] = json.loads(v) if v else None
        except ValueError:
            ki[k.strip()] = v
    return ki, txt[m.end():]


def olvas(mappa: str | Path) -> dict:
    """Egy staging forrásmappa ellenőrzött beolvasása. Minden hiány `StagingHiba`, a mappa nevével."""
    mappa = os.path.abspath(mappa)
    p = lambda n: os.path.join(mappa, n)  # noqa: E731
    for n in ("integration.json", "source.md", "metadata.json"):
        if not os.path.isfile(p(n)):
            raise StagingHiba(f"nem staging forrásmappa (hiányzik: {n}): {mappa}")
    integ = json.loads(Path(p("integration.json")).read_text(encoding="utf-8"))
    if integ.get("schema_version") != SEMA:
        raise StagingHiba(f"ismeretlen staging-séma: {integ.get('schema_version')} (ez a modul a {SEMA}-et ismeri)")
    src, _ = frontmatter(p("source.md"))
    meta = json.loads(Path(p("metadata.json")).read_text(encoding="utf-8"))
    if src.get("pipeline_status") != "downloaded":
        raise StagingHiba(f"a msp szerint nincs letöltve (pipeline_status: {src.get('pipeline_status')})")
    media = p(integ.get("media") or src.get("media_file") or "video.mp4")
    if not os.path.isfile(media) or os.path.getsize(media) == 0:
        raise StagingHiba(f"a médiafájl hiányzik vagy üres: {media}")
    vid = meta.get("id") or src.get("provider_video_id")
    if not vid:
        raise StagingHiba("nincs videóazonosító — a duplikátum-szűrés nem futtatható")
    tr = p(integ.get("transcript") or "transcript.md")
    tfm, tbody = frontmatter(tr) if os.path.isfile(tr) else ({}, "")
    # a kiadói felirat (a msp `subtitles` motorja ebből írta az átiratot): a vaultba ez kerül, nem a másodpercre kerekített átirat
    felirat = None
    motor = str(tfm.get("transcript_engine") or "")
    if motor.startswith("subtitles:"):
        nev = motor.split(":", 1)[1]
        if nev.lower().endswith(".vtt") and "/" not in nev and os.path.isfile(p(nev)):
            felirat = p(nev)
    return {"felirat": felirat,"mappa": mappa, "integration": integ, "source": src, "meta": meta, "media": media,
            "video_id": str(vid), "cim": str(meta.get("title") or src.get("title") or vid).strip(),
            "lap": integ.get("url") or src.get("url") or meta.get("url"),
            "targy": integ.get("suggested_subject") or src.get("subject"),
            "targy_forras": integ.get("subject_source"),
            "atirat": tfm, "atirat_torzs": tbody,
            "atirat_kesz": tfm.get("transcript_status") == "completed" and not tfm.get("transcript_postprocessed")}


def meta_min(src: dict) -> dict:
    """A lánc `meta_min`-alakja a staging metaadatából. A `language` a SZOLGÁLTATÓ állítása (zanza.tv-n üres) — nem az átiraté."""
    m = src["meta"]
    return {"id": src["video_id"], "title": src["cim"], "language": src["source"].get("language"),
            "duration": m.get("duration"), "webpage_url": m.get("webpage_url"), "uploader": m.get("uploader"),
            "extractor_key": m.get("extractor") or "media", "subtitles": {}, "orig_auto": []}


def forrasmappak(gyoker: str | Path) -> list[str]:
    """Minden staging forrásmappa a gyökér alatt (az a mappa, amelyben `integration.json` áll)."""
    gyoker = os.path.abspath(gyoker)
    if os.path.isfile(os.path.join(gyoker, "integration.json")):
        return [gyoker]
    ki = []
    for d, almappak, fajlok in os.walk(gyoker):
        almappak[:] = sorted(s for s in almappak if not s.startswith("."))
        if "integration.json" in fajlok:
            ki.append(d)
            almappak[:] = []
    return ki


def keres_azonosito(video_id: str, gyoker: str | Path) -> str | None:
    """A staging forrásmappa a VIDEÓAZONOSÍTÓBÓL (a `metadata.json` `id` mezője). A lánc állapotában tárolt mappa-ÚT elavulhat
    (2026-09-19-én 118 várakozó futás a régi utat hordozta), az azonosító nem. `None`, ha nincs találat — a hívó dönt."""
    if not video_id or not gyoker or not os.path.isdir(gyoker):
        return None
    for d in forrasmappak(gyoker):
        try:
            if str(json.loads(Path(d, "metadata.json").read_text(encoding="utf-8")).get("id")) == str(video_id):
                return d
        except (OSError, ValueError):
            continue
    return None


def visszajelez(mappa: str | Path, allapot: str = "integrated") -> str:
    """Az `integration.json` `integration_status`-a — az EGYETLEN mező, amit a vault oldala a stagingbe visszaír, a msp saját
    értékkészletéből. Atomi csere; minden más mező megmarad. → `"irva"` | `"mar_ez"`."""
    if allapot not in INTEGRATION_ALLAPOTOK:
        raise ValueError(allapot)
    p = os.path.join(mappa, "integration.json")
    nyers = Path(p).read_text(encoding="utf-8")
    j = json.loads(nyers)
    if j.get("integration_status") == allapot:
        return "mar_ez"
    j["integration_status"] = allapot
    from core import tartos
    tmp = tartos.tmp_ut(Path(p))             # A3-21: `.<név>.<8 hex>.manifold-tmp` (L45/§4), nem fix név
    try:
        tmp.write_text(json.dumps(j, ensure_ascii=False, indent=2) + ("\n" if nyers.endswith("\n") else ""), encoding="utf-8")
        if Path(p).read_text(encoding="utf-8") != nyers:
            raise RuntimeError(f"az integration.json az olvasás óta megváltozott: {p}")
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return "irva"


def leltar(gyoker: str | Path, vaultban: dict[str, str] | None = None) -> list[dict]:
    """`[{mappa, cim, targy, integration_status, vaultban, atirat, lap, letoltve, hiba}]` — mi van a stagingben.
    A `vaultban` (`{videóazonosító: vault-út}`, a vault médiaréteg info.json-jaiból) a hívó dolga (C20b); nélküle `None`."""
    bent = vaultban or {}
    ki = []
    for d in forrasmappak(gyoker):
        try:
            s = olvas(d)
            ki.append({"mappa": d, "cim": s["cim"], "targy": s["targy"],
                       "integration_status": s["integration"].get("integration_status"),
                       "vaultban": bent.get(s["video_id"]), "atirat": s["atirat"].get("transcript_status"),
                       "lap": s.get("lap"), "letoltve": s["source"].get("downloaded_at"), "hiba": None})
        except (StagingHiba, ValueError, OSError) as e:
            ki.append({"mappa": d, "cim": os.path.basename(d), "targy": None, "integration_status": None, "vaultban": None,
                       "atirat": None, "lap": None, "letoltve": None, "hiba": str(e)})
    return ki
