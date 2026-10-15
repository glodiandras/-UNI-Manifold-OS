"""A videó vault-oldali mellékletei (C20b) — a legacy `media_staging.py` (`cues`, `vtt`, `info_json`) és `media.py` (`write_note`,
`transcribe` VTT-kimenete, `_segs_minoseg`, `asr_coverage`) **tiszta függvényként**: bemenet a beolvasott staging-mappa (`staging.olvas`)
vagy a worker átirata, kimenet a fájl szövege. Nem ír, nem olvas a vaultból: a vaultba a lánc a gépi-írás szolgáltatáson át ír
(`uj` a szöveges mellékletekre, `mozgat` a videóra; 28., 68(b) döntés).

A kimenet a legacy formátuma **bájtra** (a vaultban 236 forrásjegyzet áll a sentinel-lel, a `.hu.vtt`-k a `NOTE manifold-asr`
fejléccel): a próbakör a legacyvel azonos vault-változást vár (C20b „Kész, ha”). Ahol a 2.0 eltér, a függvény leírása kimondja.

    vtt_stagingbol(src, nyelv, hossz)   a msp `transcript.md`-jéből (újra-ASR nélkül, K2 konvenció)
    vtt_atiratbol(atirat, …)            a worker `atirat` válaszából (mlx-whisper szegmensek)
    info_json(src)                      a vault `.info.json`-alakja a msp `metadata.json`-jából + `_staging`
    forrasjegyzet(…)                    a forrásleíró jegyzet (a PDF-tankönyv analogonja) a `SENTINEL`-lel
    minoseg(szegmensek, hossz)          (hangfedettség, ismétlés-arány): a felismerő degenerációjának két jele
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re

from core import atirat as A

SENTINEL = "<!-- manifold-media-source-note -->"     # a legacy `media.SENTINEL`: e nélkül a lánc nem ír felül létező jegyzetet
ASR_JEL = A.GEPI_JEL                                  # „NOTE manifold-asr”: a gépi átirat jele (`vaultlib.ASR_JEL`)
_TS = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*$", re.M)
_INDOK = ("A forras a multimedia-source-pipeline (msp) staging repojabol jott, nem a media.py fetch-bol. "
          "Ez a kulcs a staging teljes provenienciajat megorzi, hogy semmi ne vesszen el az atalakitasban (I3, I12).")


class VaultoldalHiba(ValueError):
    """A melléklet nem állítható elő (az ok a bemeneté; a lánc nem javítja, jelenti)."""


def hhmmss(sec) -> str:
    """`m:ss` vagy `h:mm:ss` (a legacy `vaultlib.hhmmss`)."""
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def vtt_ts(sec) -> str:
    """`HH:MM:SS.mmm` (a legacy `media._vtt_ts`)."""
    h, r = divmod(float(sec), 3600.0)
    m, s = divmod(r, 60.0)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def meret_szoveg(n: float) -> str:
    """Fájlméret magyar tizedesvesszővel (a legacy `media._fmt_size`)."""
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}".replace(".", ",")
        n /= 1024
    return ""


# ------------------------------------------------------------------ a staging átirata → VTT

def cues(tbody: str) -> list[tuple[int, str]]:
    """`[(kezdet_mp, szöveg)]` — a `transcript.md` `[HH:MM:SS]` jelölései, a szöveg SZÓ SZERINT (a msp a motor kimenetét javítás
    nélkül írja; `transcript_postprocessed: false`)."""
    ms = list(_TS.finditer(tbody))
    out = []
    for i, m in enumerate(ms):
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        end = ms[i + 1].start() if i + 1 < len(ms) else len(tbody)
        txt = " ".join(sor.strip() for sor in tbody[m.end():end].splitlines() if sor.strip())
        if txt:
            out.append((t, txt))
    return out


def staging_hossz(src: dict) -> int | None:
    """A forrás hossza a msp metaadatából (`metadata.json` `duration`, különben a `source.md` `duration_seconds`)."""
    for v in (src["meta"].get("duration"), src["source"].get("duration_seconds")):
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def vtt_stagingbol(src: dict, nyelv: str, hossz: float | None = None) -> str:
    """A `.vtt` szöveg a 2026-09-18-i K2 konvencióval: a cue kezdete MÉRT (egész másodperc), a vége a következő cue kezdete, az utolsóé a
    forrás hossza — ez KONVENCIÓ, és a fejléc kimondja. Két azonos kezdetű szakasznál a vég legalább +1 s. A `hossz` a lemezen álló fájl
    mért hossza (a hívó adja, `konvertalas.felmeres`), ha a metaadat nem közli."""
    a = src["atirat"]
    cs = cues(src["atirat_torzs"])
    if not cs:
        raise VaultoldalHiba("a transcript.md-ben nincs időbélyeges szakasz")
    dur = staging_hossz(src)
    if dur is None:
        if hossz is None:
            raise VaultoldalHiba("a forrás hossza nem ismert (metaadat és mérés nélkül)")
        dur = int(round(hossz))
    sorok = ["WEBVTT", "", ASR_JEL,
             f"motor: {str(a.get('transcript_engine') or 'ismeretlen').split(':')[0]}",
             f"modell: {a.get('transcript_model') or 'ismeretlen'}",
             f"nyelv: {nyelv}",
             "nyelv_forras: pipeline-beallitas (msp config transcript.language)",
             f"keszult: {str(a.get('transcript_generated_at') or '')[:10]}",
             "futas: multimedia-source-pipeline (msp), staging",
             "figyelem: GEPI atirat, nem a kiado felirata. Az idobelyeg szakasz-szintu.",
             "cue_vege: a KOVETKEZO cue kezdete, az utolsoe a forras hossza — KONVENCIO, nem meres.",
             "cue_kezdet: MERT ertek, de egesz masodpercre kerekitve (a staging transcript.md granularitasa).",
             ""]
    for i, (t, txt) in enumerate(cs):
        vege = max(cs[i + 1][0] if i + 1 < len(cs) else dur, t + 1)
        sorok += [str(i + 1), f"{vtt_ts(t)} --> {vtt_ts(vege)}", txt, ""]
    return "\n".join(sorok)


def staging_atirat_atveheto(src: dict, nyelv: str) -> bool:
    """A staging kész átirata átvehető-e (a legacy `szovegreteg_helyett` feltétele): kész, utómunka nélküli, és a nyelve (a msp a
    konfigurációjából veszi, nem méri) nem tér el a lánc nyelvétől — eltérésnél a lánc maga ír át (I13)."""
    if not src.get("atirat_kesz"):
        return False
    alang = str(src["atirat"].get("language") or "").strip().lower().split("-")[0]
    return not alang or alang == nyelv


# ------------------------------------------------------------------ a worker átirata → VTT

def minoseg(szegmensek: list[dict], hossz: float | None) -> tuple[float | None, float]:
    """(hangfedettség, ismétlés-arány) — a felismerő degenerációjának két jele (a legacy `media._segs_minoseg`). Az ismétlés a
    leggyakoribb szakasz-szöveg aránya; a fedettség a DUPLIKÁCIÓ KISZŰRÉSE UTÁN mért (a hurok „lefedi” a hangot, csak szeméttel)."""
    if not szegmensek:
        return (0.0 if hossz and hossz > 0 else None), 1.0
    txts = [(x.get("text") or "").strip() for x in szegmensek]
    ism = round(max(collections.Counter(txts).values()) / len(txts), 3)
    egyedi, elozo = [], None
    for x in sorted(szegmensek, key=lambda y: y["start"]):
        t = (x.get("text") or "").strip()
        if t and t != elozo:
            egyedi.append(x)
        elozo = t
    osszevont: list[tuple[float, float]] = []
    for x in egyedi:
        a_, b_ = float(x["start"]), float(x["end"])
        if osszevont and a_ <= osszevont[-1][1]:
            osszevont[-1] = (osszevont[-1][0], max(osszevont[-1][1], b_))
        else:
            osszevont.append((a_, b_))
    cov = round(sum(b_ - a_ for a_, b_ in osszevont) / hossz, 3) if hossz and hossz > 0 else None
    return cov, ism


def vtt_atiratbol(atirat: dict, nyelv: str, *, modell: str, nyelv_forras: str, keszult: str, futas: str = "alap") -> str:
    """A worker `atirat` válaszából (`{szegmensek: [{start, end, text}]}`) a `<törzs>.<nyelv>.vtt` a legacy `media.transcribe`
    fejlécével (`NOTE manifold-asr`, motor, modell, nyelv és forrása, a készítés napja, a futás módja). A `keszult` a hívóé
    (ÉÉÉÉ-HH-NN): a függvény determinisztikus. Eltérés a legacytől: a motor `mlx-whisper` (a legacyé ugyanez volt) és a `modell` a
    regiszter repója a modellnév helyett."""
    szegm = [s for s in atirat.get("szegmensek") or [] if str(s.get("text") or "").strip()]
    if not szegm:
        raise VaultoldalHiba("az átiratban nincs szöveges szakasz")
    sorok = ["WEBVTT", "", ASR_JEL, "motor: mlx-whisper", f"modell: {modell}", f"nyelv: {nyelv}",
             f"nyelv_forras: {nyelv_forras or 'megadott'}", f"keszult: {keszult}", f"futas: {futas}",
             "figyelem: GEPI atirat, nem a kiado felirata. Az idobelyeg szakasz-szintu.", ""]
    for i, s in enumerate(szegm, 1):
        sorok += [str(i), f"{vtt_ts(s['start'])} --> {vtt_ts(s['end'])}", str(s["text"]).strip(), ""]
    return "\n".join(sorok)


def fedettseg(vtt: str, hossz: float | None) -> float | None:
    """A hossz hány százalékát fedik le a cue-k (a legacy `media.asr_coverage`, a VTT szövegéből)."""
    if not hossz or hossz <= 0:
        return None
    cs = A.elemez(vtt)
    if not cs:
        return None
    osszevont: list[tuple[float, float]] = []
    for c in cs:
        if osszevont and c["k"] <= osszevont[-1][1]:
            osszevont[-1] = (osszevont[-1][0], max(osszevont[-1][1], c["v"]))
        else:
            osszevont.append((c["k"], c["v"]))
    return round(sum(b_ - a_ for a_, b_ in osszevont) / hossz, 3)


# ------------------------------------------------------------------ info.json

def info_json(src: dict) -> dict:
    """A vault info.json-alakja: a msp `metadata.json` mezői + a yt-dlp-nevű származtatott mezők (`fulltitle`, `channel`,
    `width`/`height`, `epoch`) + `_staging`. Az `epoch` a letöltés ideje, nem az átvételé — a forrásjegyzet „Letöltve” sora így
    idempotens (I26)."""
    m, pl, a = src["meta"], src["meta"].get("pipeline") or {}, src["atirat"]
    w = h = None
    rm = re.match(r"^(\d+)x(\d+)$", str(m.get("resolution") or ""))
    if rm:
        w, h = int(rm.group(1)), int(rm.group(2))
    le = pl.get("downloaded_at") or src["source"].get("downloaded_at")
    epoch = int(dt.datetime.fromisoformat(str(le).replace("Z", "+00:00")).timestamp()) if le else None
    out = {"id": src["video_id"], "title": src["cim"], "fulltitle": m.get("title") or src["cim"],
           "uploader": m.get("uploader"), "channel": m.get("uploader"), "upload_date": m.get("upload_date"),
           "duration": m.get("duration"), "webpage_url": m.get("webpage_url"), "extractor": m.get("extractor"),
           "width": w, "height": h}
    for k in ("fps", "vcodec", "acodec", "ext", "format_id", "format_note", "filesize"):
        out[k] = m.get(k)
    out["epoch"] = epoch
    out["description"] = m.get("description")
    if m.get("url") and m.get("url") != m.get("webpage_url"):
        out["url"] = m["url"]                  # 84(e): a bejárt oldal, ha a `webpage_url` a közvetlen kiadói fájl
    out["_staging"] = {
        "indok": _INDOK, "staging_mappa": os.path.basename(src["mappa"]),
        "source_id": src["integration"].get("source_id") or src["source"].get("source_id"),
        "zanza_lap": src["lap"], "letoltve": le,
        "format_selector": pl.get("format_selector"), "ffmpeg_used": pl.get("ffmpeg_used"),
        "yt_dlp_version": pl.get("yt_dlp_version"),
        "subtitles_available": m.get("subtitles_available"),
        "automatic_captions_available": m.get("automatic_captions_available"),
        "atirat": {k: a.get(k) for k in ("transcript_engine", "transcript_model", "transcript_confidence",
                                         "transcript_generated_at", "transcript_postprocessed", "language")},
        "cim_javitva": None}
    return out


def info_json_szoveg(src: dict) -> str:
    """Az `.info.json` fájl szövege a legacy írásmódjával (`json.dump(…, ensure_ascii=False, indent=1)`, záró újsor nélkül)."""
    return json.dumps(info_json(src), ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ a forrásleíró jegyzet

def forrasjegyzet(video_nev: str, *, cimke: str | None, info: dict | None, hossz: float | None, meret: int,
                  feliratok: list[tuple[str, str, int, str]], info_nev: str | None,
                  egyezes: float | None = None, fedettseg_: float | None = None) -> str:
    """A forrásleíró jegyzet (a legacy `media.write_note`) szövege. IDEMPOTENS (I26): minden adata a bemenetből jön, semmi nem a futás
    idejéből — a „Letöltve” dátum is az info.json `epoch` mezője (a legacy itt a fájl mtime-jára esett vissza; ez a hívó dolga: ha nincs
    `epoch`, a sor `—`).

    `feliratok`: `[(nyelv, fájlnév, cue-szám, eredet: "gépi" | "kiadói")]`; `egyezes`/`fedettseg_`: a gépi átirat két minőségjele (a
    kiadó átiratával mért tartalmi egyezés és a hangfedettség), `None` → `—`. A H1 a fájlnév törzse (a H1-szabály, L34)."""
    meta = info or {}
    torzs = os.path.splitext(video_nev)[0]
    L = ["---", "Tags:"]
    if cimke:
        L.append(f"  - {cimke}")
    L += ["Source:", f'  - "[[{video_nev}#t=0]]"', "Status:", "NN:", "Canvas:", "---", "",
          f"# {torzs}", "", f"![[{video_nev}]]", "", "## Forrásadatok", ""]
    ep = meta.get("epoch")
    letoltve = dt.datetime.fromtimestamp(ep).strftime("%Y-%m-%d") if ep else "—"
    up = meta.get("upload_date") or ""
    up = f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else "—"
    res = f"{meta['width']}×{meta['height']}" if meta.get("width") else "—"
    kod = " + ".join(x for x in (str(meta.get("vcodec") or "").split(".")[0], str(meta.get("acodec") or "").split(".")[0])
                     if x and x.lower() not in ("none", "null"))
    # 84(e): közvetlen kiadói fájlnál a `webpage_url` maga a fájl; a forrás az oldal (`url`), ahonnan a bejárás vette
    forras = meta.get("webpage_url") or ""
    if meta.get("url") and os.path.splitext(forras.split("?")[0])[1].lower() in (".mp4", ".mov", ".m4v", ".webm", ".mkv"):
        forras = meta["url"]
    L += ["| Mező | Érték |", "|---|---|",
          f"| Csatorna | {meta.get('uploader') or meta.get('channel') or '—'} |",
          f"| Közzététel | {up} |",
          f"| Hossz | {hhmmss(hossz) if hossz and hossz > 0 else 'NEM MÉRT'} |"]
    try:
        sdur = float(meta.get("duration") or -1)
    except (TypeError, ValueError):
        sdur = -1.0
    if sdur > 0 and hossz and hossz > 0 and abs(sdur - hossz) > 2:
        L.append(f"| Forrás teljes hossza | {hhmmss(sdur)} — **szakasz letöltve**, a `#t=` a LETÖLTÖTT fájl idejére vonatkozik |")
    L += [f"| Felbontás | {res}{f' ({kod})' if kod else ''} |",
          f"| Forrás | {forras or '—'} |",
          f"| Letöltve | {letoltve} |",
          f"| Fájl | [[{video_nev}]] · {meret_szoveg(meret)} |"]
    if info_nev:
        L.append(f"| Proveniencia-fájl | [[{info_nev}]] |")
    L += ["", "## Fejezetek", "",
          "Az időbélyeg a médiaforrás **oldalszáma**: a `#t=` horgony erre a másodpercre mutat, és a jegyzet állítása ezen a ponton "
          "kereshető vissza.", ""]
    ch = [c for c in (meta.get("chapters") or []) if c.get("title")]
    if ch:
        L += ["| Idő | Fejezet | Horgony |", "|---|---|---|"]
        for c in ch:
            t = int(c.get("start_time") or 0)
            L.append(f"| {hhmmss(t)} | {c['title'].strip()} | `[[{video_nev}#t={t}]]` |")
    else:
        L.append("A forrás nem közöl fejezetbeosztást. A horgonyt a felirat időbélyege adja; a `#t=` bármelyik másodpercre állítható.")
    L += ["", "## Szövegréteg", ""]
    if feliratok:
        L += ["| Nyelv | Fájl | Feliratsáv | Eredet |", "|---|---|---|---|"]
        gepi = False
        for nyelv, fajl, n, eredet in feliratok:
            gepi = gepi or eredet == "gépi"
            L.append(f"| {nyelv} | [[{fajl}]] | {n} cue | {eredet} |")
        L += ["", "A felirat a médiaforrás szövegrétege — ezen fut a horgony visszakeresése, ahogy a tankönyvi PDF-en az oldal szövege."]
        if gepi:
            L += ["", "**A szövegréteg gépi átirat**, nem a kiadó felirata: mérés eredménye, amely tévedhet. Két, egymástól független "
                      "minőségjel — tartalmi egyezés a kiadó átiratával: "
                      f"**{egyezes if egyezes is not None else '—'}**, hangfedettség: "
                      f"**{fedettseg_ if fedettseg_ is not None else '—'}**."]
    else:
        L.append("**Nincs szövegréteg.** A forrásból nem volt letölthető felirat, ezért a `#t=` horgony gépileg NEM verifikálható "
                 "(`I20`, `I21`) — a `mfd.py media` ezt találatként jelzi, és ez a jelzés helyes.")
    L += ["", SENTINEL, ""]
    return "\n".join(L)


def felirat_sor(fajlnev: str, vtt: str) -> tuple[str, str, int, str]:
    """`(nyelv, fájlnév, cue-szám, eredet)` egy `<törzs>.<nyelv>.vtt` feliratfájlhoz, a forrásjegyzet táblájához."""
    reszek = fajlnev.rsplit(".", 2)
    nyelv = reszek[-2] if len(reszek) == 3 else "?"
    return nyelv, fajlnev, len(A.elemez(vtt)), "gépi" if ASR_JEL in vtt[:600] else "kiadói"


def idegen_jegyzet(szoveg: str) -> bool:
    """Igaz, ha a létező jegyzetet nem a lánc írta (nincs benne a `SENTINEL`): azt nem írjuk felül (I13, I33)."""
    return SENTINEL not in szoveg
