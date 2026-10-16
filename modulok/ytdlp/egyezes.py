"""A médiaforrás és a tananyag-jegyzetek lexikai párosítása (C20b).

A bemenet egy `Forras` (a médiafájl NEVE, a szövegréteg cue-i és a mért hossza); a még el nem helyezett forrással is dolgozik. A vaultot
a `NoteIndex` egyszer olvassa végig, csak olvasva.

    temak(vault)                 a témamappák (alap: `^[A-Z]{1,3}\\d{2} - `, a `*00 - ` és a kizárt mappák nélkül; `[video] tema_minta`, `kizart_mappak`)
    NoteIndex(vault)             az `<Téma>/Elmélet/` jegyzetek szótő-indexe (jegyzetenkénti és témánkénti gyakoriság, évszámok)
    windows(f, idx)              a jelöltállás 60 s-os ablakai 10 s lépéssel (a 25 hosszú szónál szegényebb ablak kimarad)
    rank_text / rank_topics      a lift (a véletlen feletti többlet) témánként
    cim_tema(cim, temak)         a cím megnevez-e egy témát
    classify(f, idx, csak_targy) a lexikai besorolás és a négy jel (margó, erős jelölt, kronológia, cím)
    candidates(f, temak, idx)    jegyzet × időpont jelöltek egy témakészleten (sávok: a távoli kontroll p99/p95)

A küszöbök egy magyar nyelvű jegyzetgyűjteményen mért értékek (`tema_besorolas`, `jeloltallitas`); más gyűjteménynél újra kell mérni őket.
"""
from __future__ import annotations

import collections
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .szovegreteg import (K, longwords, mask_code, media_anchors, nfc, parse_fm, split_note, stem_list, ablak_szoveg)

# tema_besorolas
KUSZOB_MARGO = 0.091
KRON = {"h_ev": 12, "eps": 0.0002, "top_k": 3, "min_evszam": 3}
# jeloltallitas
LEPES_S, MIN_NEVEZO = 10, 25
EROS_B, KOZEPES_B = 0.193, 0.150
MASODIK_ABLAK_S, MAX_HORGONY_JEGYZETENKENT = 60, 2

# A téma-mappa felismerése és a kizárt mappák: a `[video] tema_minta` / `kizart_mappak` (os.toml) adja; ezek az alapértékek, ha a kulcs hiányzik.
# A minta alapja egyezik az os.toml-éval (és a `core/videolanc.TEMA_MINTA_ALAP`-éval); a kizárt mappák alapja semleges: csak a sablonmappa.
TEMA_MINTA = re.compile(r"^[A-Z]{1,3}\d{2} - \S.*$")
KIZART_MAPPAK = ("_Template",)
ELMELET_MAPPA = "Elmélet"                   # `[fuzet] elmelet_mappa`: a téma-mappa tananyag-jegyzeteinek almappája
SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


def index_beallitas(cfg) -> dict:
    """A `NoteIndex` és a `temak` konfigurációból jövő kulcsszavai (`tema_minta`, `kizart_mappak`, `elmelet_mappa`); hiányzó kulcs: az alap."""
    v = cfg.section("video")
    minta = v.get("tema_minta")
    kizart = v.get("kizart_mappak")
    try:
        minta_re = re.compile(str(minta)) if minta else TEMA_MINTA
    except re.error as e:                       # hibás `[video] tema_minta`: az alapminta (a Bevitel `videolanc.tema_minta` úgyis jelzi a hibát)
        print(f"[egyezés] FIGYELEM: a [video] tema_minta nem érvényes reguláris kifejezés ({e}); az alapminta marad", file=sys.stderr, flush=True)
        minta_re = TEMA_MINTA
    return {"tema_minta": minta_re,
            "kizart_mappak": tuple(str(k) for k in kizart) if isinstance(kizart, (list, tuple)) else KIZART_MAPPAK,
            "elmelet_mappa": str(cfg.section("fuzet").get("elmelet_mappa") or ELMELET_MAPPA)}


@dataclass
class Forras:
    """A párosítás bemenete: a médiafájl NEVE (a horgony erre mutat), a szövegréteg cue-i és a mért hossz (≤ 0: nem mért)."""
    nev: str
    cuek: tuple = ()
    hossz: float = -1.0
    _szoveg: str | None = field(default=None, repr=False)

    @property
    def torzs(self) -> str:
        return os.path.splitext(self.nev)[0]

    def szoveg(self, t: float | None = None) -> str:
        if t is None:
            if self._szoveg is None:
                self._szoveg = ablak_szoveg(self.cuek)
            return self._szoveg
        return ablak_szoveg(self.cuek, t)


def temak(vault: str | Path, tema_minta=None, kizart_mappak=None) -> list[str]:
    tema_minta = tema_minta or TEMA_MINTA
    kizart_mappak = tuple(KIZART_MAPPAK if kizart_mappak is None else kizart_mappak)
    out = []
    for d in sorted(os.listdir(vault)):
        if not os.path.isdir(os.path.join(vault, d)) or d.startswith("."):
            continue
        n = nfc(d)
        if not tema_minta.match(n) or re.match(r"^[A-Z]{1,3}00 - ", n) or n.startswith(kizart_mappak):
            continue
        out.append(n)
    return out


def _walk_md(root: str | Path) -> list[str]:
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if not f.startswith(".") and f.endswith(".md"):
                out.append(os.path.join(dp, f))
    return sorted(out)


# ------------------------------------------------ kronológia

_ROMAI = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_KRE = r"(?:Kr\.\s*e\.|i\.\s*e\.)"
_KRU = r"(?:Kr\.\s*u\.|i\.\s*sz\.)"
_RAG = r"(?:-(?:ban|ben|ig|tól|től|es|as|os|ös|ra|re|i|ik|ban|ben|beli|ban|at|et|ot|öt|hoz|hez|höz|nak|nek|ból|ből)\b)"
_RE_KRE1 = re.compile(_KRE + r"\s*(\d{1,4})\b")
_RE_KRE2 = re.compile(r"\b(\d{1,4})\s*" + _KRE)
_RE_EV3 = re.compile(r"(?:" + _KRU + r"\s*(\d{2,4})\b)|\b(\d{3})" + _RAG)
_RE_EV4 = re.compile(r"(?<![\d.,])(1\d{3}|20[0-2]\d)(?![\d.,]\d)")
_RE_SZAZ_A = re.compile(r"\b(\d{1,2})\.\s*(?:–\s*\d{1,2}\.\s*)?század")
_RE_SZAZ_R = re.compile(r"\b([IVXL]{1,6})\.\s*(?:–\s*[IVXL]{1,6}\.\s*)?század")


def _romai(s: str) -> int:
    tot, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAI[ch]
        tot += -v if v < prev else v
        prev = max(prev, v)
    return tot


def evszamok(text: str) -> list[int]:
    """A szöveg évszám-ELŐFORDULÁSAI: négyjegyű (1000–2029), Kr. e. negatívként, ragozott háromjegyű, évszázad a közepével."""
    t = mask_code(text)
    out, spans = [], []
    for rx in (_RE_KRE1, _RE_KRE2):
        for m in rx.finditer(t):
            y = int(m.group(1))
            if 1 <= y <= 4000:
                out.append(-y)
                spans.append(m.span())

    def taken(sp):
        return any(a <= sp[0] < b for a, b in spans)

    for m in _RE_EV4.finditer(t):
        if not taken(m.span()):
            out.append(int(m.group(1)))
    for m in _RE_EV3.finditer(t):
        if taken(m.span()):
            continue
        y = int(m.group(1) or m.group(2))
        if 100 <= y <= 999:
            out.append(y)
    for rx, conv in ((_RE_SZAZ_A, int), (_RE_SZAZ_R, _romai)):
        for m in rx.finditer(t):
            c = conv(m.group(1))
            if 1 <= c <= 21:
                kr_e = re.search(_KRE + r"\s*$", t[max(0, m.start() - 12):m.start()])
                out.append(-(c - 1) * 100 - 50 if kr_e else (c - 1) * 100 + 50)
    return out


def kron_pont(ys, ys_tema):
    if not ys or not ys_tema:
        return None
    h, eps = KRON["h_ev"], KRON["eps"]
    norm = len(ys_tema) * h * math.sqrt(2 * math.pi)
    tot = 0.0
    for y in ys:
        s = sum(math.exp(-0.5 * ((y - u) / h) ** 2) for u in ys_tema)
        tot += math.log(s / norm + eps)
    return tot / len(ys)


def rank_kron(ys, topics, topic_years):
    sc = {t: kron_pont(ys, topic_years.get(t, [])) for t in topics}
    return sorted(((t, s) for t, s in sc.items() if s is not None), key=lambda x: -x[1])


def targy(tema: str | None) -> str | None:
    """'T15 - A reformkor' → 'T'."""
    m = re.match(r"^([A-Z]+)\d", tema or "")
    return m.group(1) if m else None


def kron_jel(ys, lift_rangsor, topics, topic_years) -> dict:
    k, nmin = KRON["top_k"], KRON["min_evszam"]
    l1 = lift_rangsor[0][0] if lift_rangsor else None
    sz = targy(l1)
    jel = {"evszam": len(ys), "merheto": False, "egyezik": False, "top3": [], "kombinalt": None}
    if not l1 or len(ys) < nmin:
        return jel
    kr = rank_kron(ys, [t for t in topics if targy(t) == sz], topic_years)
    top = [t for t, _ in kr[:k]]
    jel["top3"] = [{"tema": t, "pont": round(s, 3)} for t, s in kr[:3]]
    if l1 not in dict(kr):
        return jel
    jel["merheto"] = True
    jel["egyezik"] = l1 in top
    jel["kombinalt"] = next((t for t, _ in lift_rangsor if t in top), None)
    return jel


# ------------------------------------------------ az index

class NoteIndex:
    """Az `<Téma>/Elmélet/` jegyzetek szótő-indexe (egyszer épül, a futás idejére; a vaultot csak olvassa)."""

    def __init__(self, vault: str | Path, jegyzetek: dict[str, str] | None = None, *, tema_minta=None, kizart_mappak=None,
                 elmelet_mappa: str = ELMELET_MAPPA):
        """`jegyzetek`: `{vault-relatív út: szöveg}` a lemez helyett (tesztek). `tema_minta`, `kizart_mappak`, `elmelet_mappa`:
        a konfigurációból (`index_beallitas`); hiányzó érték: az alap."""
        self.vault = Path(vault)
        tset = set(temak(vault, tema_minta, kizart_mappak)) if jegyzetek is None else {nfc(r).split("/")[0] for r in jegyzetek}
        self.notes: dict[str, dict] = {}
        self.by_topic: dict[str, list[str]] = collections.defaultdict(list)
        self.topic_tf: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        if jegyzetek is None:
            forras = ((nfc(os.path.relpath(p, vault)), p) for p in _walk_md(vault))
        else:
            forras = ((nfc(r), None) for r in sorted(jegyzetek))
        for rp, p in forras:
            parts = rp.split("/")
            if len(parts) < 3 or parts[1] != elmelet_mappa or parts[0] not in tset:
                continue
            try:
                txt = Path(p).read_text(encoding="utf-8") if p else jegyzetek[rp]
            except (OSError, UnicodeDecodeError):
                continue
            fm, body = split_note(txt)
            d, _ = parse_fm(fm)
            h1 = re.search(r"^# (.+)$", body, re.M)
            cim = (h1.group(1) if h1 else os.path.splitext(parts[-1])[0]).strip()
            sl = stem_list(body)
            self.notes[rp] = {"tema": parts[0], "path": p, "cim": cim, "body": body, "stems": set(sl),
                              "title": {w[:K] for w in longwords(cim)}, "media": media_anchors(d.get("Source", ""))}
            self.by_topic[parts[0]].append(rp)
            self.topic_tf[parts[0]].update(sl)
        self.topics = sorted(self.topic_tf)
        self.nd = len(self.notes)
        self.df_note = collections.Counter(s for x in self.notes.values() for s in x["stems"])
        self.df_topic = collections.Counter(s for t in self.topics for s in self.topic_tf[t])
        self.tvocab = {t: set(self.topic_tf[t]) for t in self.topics}
        self.vocab_total = sum(len(v) for v in self.tvocab.values()) or 1
        self.topic_years: dict[str, list[int]] = collections.defaultdict(list)
        for rp, n in self.notes.items():
            n["years"] = evszamok(n["body"])
            self.topic_years[n["tema"]] += n["years"]

    def veletlen_esely(self, s, tema):
        w = len(self.tvocab[tema]) / self.vocab_total
        return 1.0 - (1.0 - w) ** self.df_topic[s]

    def idf_note(self, s):
        return math.log((self.nd + 1) / (self.df_note.get(s, 0) + 1))


# ------------------------------------------------ ablakok és jelöltek

def windows(f: Forras, idx: NoteIndex) -> list[dict]:
    """[{t, src, sw, wi, den}] — a jelöltállás időablakai a szövegrétegen."""
    cues = f.cuek
    if not cues:
        return []
    dur = f.hossz
    if not dur or dur <= 0:
        dur = max(c[1] for c in cues)
    out = []
    for t in range(0, int(dur) + 1, LEPES_S):
        src = longwords(" ".join(c[2] for c in cues if c[1] >= t - 20 and c[0] <= t + 40))
        if len(src) < MIN_NEVEZO:
            continue
        wi = {x: idx.idf_note(x[:K]) for x in src}
        out.append({"t": t, "src": src, "sw": {x[:K] for x in src}, "wi": wi, "den": sum(wi.values())})
    return out


def best_passage(body: str, sw: set, idx: NoteIndex, limit: int = 600) -> str:
    """A jegyzet azon bekezdése, amely az ablakkal a legtöbb ritka szótövet osztja (az olvasó EGYMÁS MELLETT lássa a kettőt)."""
    best, score = "", 0.0
    for blk in re.split(r"\n\s*\n", mask_code(body)):
        b = blk.strip()
        if not b or b.startswith("#"):
            continue
        sc = sum(idx.idf_note(s) for s in set(stem_list(b)) & sw)
        if sc > score:
            best, score = b, sc
    return best[:limit]


def candidates(f: Forras, topics, idx: NoteIndex, wins=None, with_text: bool = True) -> list[dict]:
    wins = windows(f, idx) if wins is None else wins
    mname = nfc(f.nev)
    out = []
    for tp in topics:
        for rp in idx.by_topic.get(tp, []):
            n = idx.notes[rp]
            vals = []
            for w in wins:
                mt = [x for x in w["src"] if x[:K] in n["stems"]]
                vals.append((sum(w["wi"][x] for x in mt) / w["den"] if w["den"] else 0.0, len(mt) / len(w["src"]), w["t"],
                             (len(n["title"] & w["sw"]) / len(n["title"])) if n["title"] else None, w))
            if not vals:
                continue
            med = statistics.median(v[0] for v in vals)
            vals.sort(key=lambda v: (-v[0], -v[1]))
            chosen = []
            for v in vals:
                if len(chosen) >= MAX_HORGONY_JEGYZETENKENT:
                    break
                if all(abs(v[2] - c[2]) >= MASODIK_ABLAK_S for c in chosen):
                    chosen.append(v)
            for B, s1, t, s2, w in chosen:
                band = "eros" if B >= EROS_B else ("kozepes" if B >= KOZEPES_B else None)
                if not band:
                    continue
                c = {"jegyzet": rp, "cim": n["cim"], "tema": tp, "media": mname, "t": t, "horgony": f'"[[{mname}#t={t}]]"',
                     "sav": band, "B": round(B, 3), "s1": round(s1, 3), "C": round(B - med, 3),
                     "s2": None if s2 is None else round(s2, 3),
                     "mar_horgonyzott": any(fn == mname and abs(tt - t) <= 20 for fn, tt in n["media"])}
                if with_text:
                    c["ablak_szoveg"] = f.szoveg(t)
                    c["jegyzet_reszlet"] = best_passage(n["body"], w["sw"], idx)
                out.append(c)
    out.sort(key=lambda c: (c["sav"] != "eros", -c["B"]))
    return out


# ------------------------------------------------ a téma

def rank_text(text: str, idx: NoteIndex, nyers: bool = False, tvocab=None) -> list[tuple[str, float]]:
    tv = tvocab or idx.tvocab
    qs = [s for s in set(stem_list(text)) if s in idx.df_topic]
    idf = {s: math.log(len(idx.topics) / idx.df_topic[s]) for s in qs}
    den = sum(idf.values()) or 1.0
    sc = {}
    for t in idx.topics:
        raw = sum(idf[s] for s in qs if s in tv[t]) / den
        if nyers:
            sc[t] = raw
            continue
        w = len(tv[t]) / idx.vocab_total
        exp = sum(idf[s] * (1.0 - (1.0 - w) ** idx.df_topic[s]) for s in qs) / den
        sc[t] = raw - exp
    return sorted(sc.items(), key=lambda x: -x[1])


def rank_topics(f: Forras, idx: NoteIndex, nyers: bool = False):
    """A teljes átirat + a fájlnév törzse témánként (lift; `nyers`: a korrigálatlan lefedettség)."""
    return rank_text(f.szoveg() + " " + f.torzs, idx, nyers=nyers)


def _nrm(s: str) -> str:
    return re.sub(r"\s+", " ", nfc(s or "").lower()).strip()


def cim_tema(cim: str, topics, csak_targy: str | None = None) -> str | None:
    c = _nrm(cim)
    hits = []
    for t in topics:
        if " - " not in t or (csak_targy and targy(t) != csak_targy):
            continue
        nev = _nrm(t.split(" - ", 1)[1])
        if nev and re.search(r"(?<!\w)" + re.escape(nev) + r"(?!\w)", c):
            hits.append((len(nev), nev, t))
    if not hits:
        return None
    hits.sort(reverse=True)
    return None if any(n not in hits[0][1] for _, n, _ in hits[1:]) else hits[0][2]


def classify(f: Forras, idx: NoteIndex, nyelv: str | None, wins=None, csak_targy: str | None = None) -> dict:
    """A lexikai téma-javaslat és az automatikus döntés (a legacy négy jele). `nyelv`: a szövegréteg nyelve (csak `hu` mérhető)."""
    wins = windows(f, idx) if wins is None else wins
    rang = rank_topics(f, idx)
    if csak_targy:
        rang = [x for x in rang if targy(x[0]) == csak_targy]
    top3 = [x for x in rang[:3] if x[1] > 0]
    kus = KUSZOB_MARGO
    if not top3:
        return {"tema": None, "auto": False, "arany": None, "kuszob": kus, "nyelv": nyelv,
                "okok": ["nincs összevethető szöveg vagy jegyzet — nem mért"], "top3": [], "targy_szukites": csak_targy,
                "rang": rang}
    margo = top3[0][1] - top3[1][1] if len(top3) > 1 else float("inf")
    ny = dict(rank_topics(f, idx, nyers=True))
    n1, n2 = ny.get(top3[0][0], 0.0), (ny.get(top3[1][0], 0.0) if len(top3) > 1 else 0.0)
    arany = n1 / n2 if n2 > 0 else float("inf")
    eros = {t: sum(1 for c in candidates(f, [t], idx, wins, with_text=False) if c["sav"] == "eros") for t, _ in top3}
    jel1 = margo >= kus
    jel2 = eros[top3[0][0]] > 0 and eros[top3[0][0]] == max(eros.values())
    ys = evszamok(f.szoveg() + " " + f.torzs)
    kj = kron_jel(ys, rang, idx.topics, idx.topic_years)
    jel3 = kj["egyezik"]
    okok = []
    if nyelv != "hu":
        okok.append(f"az átirat nyelve {nyelv or '—'}: lexikailag nem mérhető a jegyzetekkel")
    if not jel1:
        okok.append(f"a top1−top2 margó {margo:.3f} < {kus}")
    if not jel2:
        okok.append("az erős jelöltek nem a top1 témában a legtöbbek")
    if not kj["merheto"]:
        okok.append(f"a kronológia nem mérhető ({kj['evszam']} évszám) — második jel nélkül nincs automatikus döntés")
    elif not jel3:
        okok.append("a top1 nincs a kronológiai top-3-ban (" + ", ".join(x["tema"][:3] for x in kj["top3"]) + ")")
    cj = cim_tema(f.torzs, idx.topics, targy(top3[0][0]))
    jel4 = cj is not None and cj == top3[0][0]
    if cj and not jel4:
        okok.append(f"a cím más témát nevez meg: {cj}")
    harom = jel1 and jel2 and jel3
    auto = nyelv == "hu" and (harom or jel4)
    return {"tema": top3[0][0] if auto else None, "auto": auto,
            "auto_jel": ("három jel" if harom else "a cím és a lift egyezik") if auto else None, "cim_tema": cj,
            "margo": round(margo, 4) if margo != float("inf") else None, "arany": round(arany, 3) if arany != float("inf") else None,
            "kuszob": kus, "nyelv": nyelv, "okok": okok, "kronologia": kj, "targy_szukites": csak_targy,
            "top3": [{"tema": t, "pont": round(s, 4), "eros_jelolt": eros[t]} for t, s in top3], "rang": rang}
