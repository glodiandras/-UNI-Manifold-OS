"""A videó és a tananyag-jegyzetek automatikus, tartalmi kötése (C20b).

A jelöltállítás a TELJES jegyzetkorpuszon fut (témahatár nélkül); az igazolás egy kalibrált, mért pontosságú **verifikátor** (10 jegy
logisztikus kombinációja, `kotes_modell.json`, videónként csoportosított keresztvalidációval mérve). A verifikátor determinisztikus (nem
nyelvi modell): a kimenete nem „modell-kimenet”, a gépi írás `modell: null`-lal viheti. A modell egy magyar nyelvű jegyzetmintán illeszkedett;
más gyűjteménynél a pontosságát újra kell mérni.

    Korpusz(idx)                     az invertált index (szótő → jegyzetek), a félkövér terminusok, a bekezdések
    ablakok(f, korp)                 a `windows` ablakai + nyers szöveg, évszámok, cue-k
    jeloltek(f, korp)                (jegyzet, ablak) jelöltek az előszűrő után, a jegyekkel
    pontszam(jegyek, modell)         p = σ(b0 + Σ w·(x−μ)/σ)
    vegso_t(n, w, korp)              a horgony másodperce az ablakon belül (a jegyzet legjobb bekezdésével legtöbb ritka szótő)
    kotes(f, korp, tema=…)           {"auto": […], "javaslat": […]}: auto = saját téma, kalibrált tárgy, p ≥ küszöb
    elvetettek(ut)                   az olvasott elvetések (append-only JSONL): ezt a párt a gép nem ajánlja újra
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import statistics
from pathlib import Path

from . import egyezes as X
from .szovegreteg import K, longwords, mask_code, nfc, stem_list

FEATURES = ("B", "C", "rang_log", "res", "ritka", "cim", "felkov", "ev_plusz", "ev_minusz", "passz")
MODELL_UT = Path(__file__).resolve().parent / "kotes_modell.json"
_BOLD = re.compile(r"\*\*([^*\n]{2,80})\*\*")

# a kötés alapértékei (egy magyar nyelvű jegyzetmintán mérve)
ALAP = {"kuszob": 0.90, "javaslat_kuszob": 0.75, "max_horgony": 2, "min_tavolsag_s": 60, "elo_B": 0.12, "jelolt_per_jegyzet": 3,
        "df_max_arany": 0.25, "ritka_df": 5, "kalibralt_targyak": ["T", "I", "N"], "kuszob_targy": {"N": 0.97}}


def beallitas(felulir: dict | None = None) -> dict:
    return {**ALAP, **(felulir or {})}


def modell() -> dict:
    return json.loads(MODELL_UT.read_text(encoding="utf-8"))["modell"]


class Korpusz:
    """Az ÖSSZES `Elmélet/` jegyzet invertált indexe (a kötésnek a teljes korpusz kell)."""

    def __init__(self, idx: X.NoteIndex):
        self.idx = idx
        self.ids = sorted(idx.notes)
        self.post: dict[str, list[int]] = collections.defaultdict(list)
        for i, rp in enumerate(self.ids):
            n = idx.notes[rp]
            for s in n["stems"]:
                self.post[s].append(i)
            body = mask_code(n["body"])
            n["bold"] = {b.strip() for b in _BOLD.findall(body) if len(b.strip()) >= 3}
            n["bold_stems"] = [x for x in ({w[:K] for w in longwords(b)} for b in n["bold"]) if x]
            n["yearset"] = set(n.get("years") or [])
            paras = []
            for blk in re.split(r"\n\s*\n", body):
                b = blk.strip()
                if b and not b.startswith("#") and len(b) > 40:
                    st = set(stem_list(b))
                    if st:
                        paras.append(st)
            n["paras"] = paras
        self.nd = len(self.ids)

    def idf(self, s):
        return self.idx.idf_note(s)


def ablakok(f: X.Forras, korp: Korpusz) -> list[dict]:
    wins = X.windows(f, korp.idx)
    cues = f.cuek
    for w in wins:
        t = w["t"]
        txt = " ".join(c[2] for c in cues if c[1] >= t - 20 and c[0] <= t + 40)
        w["text"] = txt
        w["years"] = set(X.evszamok(txt))
        w["cues"] = [(c[0], c[2]) for c in cues if t - 20 <= c[0] <= t + 40]
    return wins


def pontok_ablakra(w: dict, korp: Korpusz, df_max: int) -> dict[int, float]:
    acc: dict[int, float] = collections.defaultdict(float)
    for x in w["src"]:
        p = korp.post.get(x[:K])
        if not p or len(p) > df_max:
            continue
        wt = w["wi"][x]
        for i in p:
            acc[i] += wt
    den = w["den"] or 1.0
    return {i: v / den for i, v in acc.items()}


def jegyek(n: dict, w: dict, B: float, med: float, rang: int, legjobb_masik: float, korp: Korpusz, ritka_df: int) -> dict:
    common = n["stems"] & w["sw"]
    ritka = sum(1 for s in common if korp.idx.df_note.get(s, 0) <= ritka_df)
    cim = (len(n["title"] & w["sw"]) / len(n["title"])) if n["title"] else 0.0
    if n["bold_stems"]:
        felkov = sum(1 for b in n["bold_stems"] if b <= w["sw"] or len(b & w["sw"]) >= max(1, len(b) // 2 + 1)) / len(n["bold_stems"])
    else:
        felkov = 0.0
    ev_plusz = len(w["years"] & n["yearset"])
    ev_minusz = len(w["years"] - n["yearset"]) if n["yearset"] else 0
    passz = 0.0
    for st in n["paras"]:
        tot = sum(korp.idf(s) for s in st) or 1.0
        sh = sum(korp.idf(s) for s in st & w["sw"])
        passz = max(passz, sh / tot)
    return {"B": B, "C": B - med, "rang_log": math.log(rang), "res": B - legjobb_masik, "ritka": ritka, "cim": cim,
            "felkov": felkov, "ev_plusz": ev_plusz, "ev_minusz": ev_minusz, "passz": passz}


def jeloltek(f: X.Forras, korp: Korpusz, wins=None, b: dict | None = None) -> list[dict]:
    b = beallitas(b)
    sep, max_per = b["min_tavolsag_s"], b["jelolt_per_jegyzet"]
    df_max = int(b["df_max_arany"] * korp.nd)
    wins = ablakok(f, korp) if wins is None else wins
    if not wins:
        return []
    per_w = [pontok_ablakra(w, korp, df_max) for w in wins]
    per_note: dict[int, list] = collections.defaultdict(list)
    for wi, sc in enumerate(per_w):
        for i, v in sc.items():
            per_note[i].append((v, wi))
    nw = len(wins)
    out = []
    for i, lst in per_note.items():
        med = statistics.median([v for v, _ in lst] + [0.0] * (nw - len(lst)))
        lst.sort(key=lambda x: -x[0])
        chosen: list = []
        for v, wi in lst:
            if len(chosen) >= max_per:
                break
            if all(abs(wins[wi]["t"] - wins[cj]["t"]) >= sep for _, cj in chosen):
                chosen.append((v, wi))
        for v, wi in chosen:
            sc = per_w[wi]
            rang = 1 + sum(1 for x in sc.values() if x > v)
            if v < b["elo_B"] and rang > 3:
                continue
            masik = max((x for j, x in sc.items() if j != i), default=0.0)
            n = korp.idx.notes[korp.ids[i]]
            out.append({"jegyzet": korp.ids[i], "t": wins[wi]["t"], "wi": wi, "rang": rang,
                        "jegyek": jegyek(n, wins[wi], v, med, rang, masik, korp, b["ritka_df"])})
    return out


def pontszam(f: dict, m: dict) -> float:
    z = m["b0"]
    for k in FEATURES:
        z += m["w"][k] * (f[k] - m["mu"][k]) / (m["sd"][k] or 1.0)
    return 1.0 / (1.0 + math.exp(-z))


def vegso_t(n: dict, w: dict, korp: Korpusz) -> int:
    best_para, bs = set(), -1.0
    for st in n["paras"]:
        sc = sum(korp.idf(s) for s in st & w["sw"])
        if sc > bs:
            best_para, bs = st, sc
    target = best_para or n["stems"]
    best_t, best_sc = w["t"], -1.0
    for t0, txt in w["cues"]:
        st = {x[:K] for x in longwords(txt)}
        sc = sum(korp.idf(s) for s in st & target)
        if sc > best_sc + 1e-9:
            best_t, best_sc = int(round(t0)), sc
    return best_t


def elvetettek(ut: str | Path | None) -> dict:
    """{(jegyzet, média): [t, …]} — az olvasott elvetések (a legacy `kotes/elvetett.jsonl`; hiányzó fájl: üres)."""
    out: dict = collections.defaultdict(list)
    if ut and os.path.isfile(ut):
        for sor in Path(ut).read_text(encoding="utf-8").splitlines():
            if sor.strip():
                try:
                    r = json.loads(sor)
                    out[(nfc(r["jegyzet"]), nfc(r["media"]))].append(int(r["t"]))
                except (ValueError, KeyError, TypeError):
                    continue
    return out


def sajat_tema(rp: str, tema: str) -> bool:
    return nfc(rp).split("/")[0] == nfc(tema)


def targy_kalibralt(tema: str, b: dict | None = None) -> bool:
    return X.targy(nfc(tema or "")) in set(beallitas(b)["kalibralt_targyak"])


def kotes(f: X.Forras, korp: Korpusz, tema: str, *, m: dict | None = None, elvet: dict | None = None, b: dict | None = None,
          kalibralt: bool | None = None, wins=None) -> dict:
    """A videó kötései: `auto` (saját téma, mért tárgy, p ≥ a tárgy küszöbe) és `javaslat` (minden más p ≥ 0,75-ös, a más téma csak
    p ≥ küszöb felett). Jegyzetenként legfeljebb 2 időpont ugyanabból a videóból (a meglévőkkel együtt), ≥ 60 s távolságra; a már
    meglévő (±20 s) és az olvasott elvetés (±30 s) kimarad."""
    b = beallitas(b)
    m = m or modell()
    kal = targy_kalibralt(tema, b) if kalibralt is None else kalibralt
    kus = b["kuszob_targy"].get(X.targy(nfc(tema or "")), b["kuszob"])
    jkus, maxh, sep = b["javaslat_kuszob"], b["max_horgony"], b["min_tavolsag_s"]
    elvet = elvet or {}
    wins = ablakok(f, korp) if wins is None else wins
    mname = nfc(f.nev)
    cands = jeloltek(f, korp, wins, b)
    for x in cands:
        x["p"] = pontszam(x["jegyek"], m)
    cands.sort(key=lambda x: -x["p"])
    out: dict = {"auto": [], "javaslat": []}
    foglalt: dict[str, list[int]] = {}
    for x in cands:
        if x["p"] < jkus:
            break
        rp = x["jegyzet"]
        n = korp.idx.notes[rp]
        if rp not in foglalt:
            foglalt[rp] = [tt for fn, tt in n["media"] if nfc(fn) == mname and tt > 0]
        sajat = sajat_tema(rp, tema)
        if x["p"] < kus and not sajat:
            continue
        w = wins[x["wi"]]
        vt = vegso_t(n, w, korp)
        if any(abs(tt - vt) <= 20 or abs(tt - x["t"]) <= 20 for tt in foglalt[rp]):
            continue
        if any(abs(tt - x["t"]) <= 30 for tt in elvet.get((nfc(rp), mname), [])):
            continue
        if len(foglalt[rp]) >= maxh or any(abs(vt - tt) < sep for tt in foglalt[rp]):
            continue
        common = sorted(n["stems"] & w["sw"], key=lambda s: -korp.idf(s))
        rec = {"jegyzet": rp, "media": mname, "t": x["t"], "vegso_t": vt, "p": round(x["p"], 4), "sajat_tema": sajat,
               "rang": x["rang"], "jegyek": {k: round(v, 4) for k, v in x["jegyek"].items()},
               "bizonyitek": {"ritka_kozos": common[:8], "evszam_kozos": sorted(w["years"] & n["yearset"])[:6]}}
        if sajat and kal and x["p"] >= kus:
            out["auto"].append(rec)
            foglalt[rp].append(vt)
        else:
            out["javaslat"].append(rec)
    return out


def indok(rec: dict) -> str:
    bz = rec.get("bizonyitek", {})
    ev = ", ".join(str(y) for y in bz.get("evszam_kozos", []))
    return (f"media_link verifikátor p={rec['p']:.3f} ≥ küszöb (saját téma); közös ritka szótövek: "
            + ", ".join(bz.get("ritka_kozos", [])[:6]) + (f"; közös évszám: {ev}" if ev else ""))
