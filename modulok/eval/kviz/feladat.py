"""Aranyhalmaz: feleletválasztós kvíz (router-feladat: `kviz`) — 20 jegyzet, jegyzetenként egy 5 kérdéses darab (C22m).

A források a `szoveg/forrasok/jNN.md` fagyasztott másolatok. A tétel a kvízlánc generáló kérése (`modulok/kviz/promptok`,
`PROMPT_VERZIO`) a jegyzet egy darabjára (`keszit.py` választja és fagyasztja), 5 kérdéssel; a token-keret 5 × 230 + 150.

**Pontozás** (modell nélkül; a lánc kapuival, a vak ellenőrzés nélkül). Kérdésenként, a lánc sorrendjében — az első bukott kapu
dönt, a részletek megnevezik:
  - mechanikus (`modulok/kviz/mechanikus`): szerkezet, jelölés, tiltott válasz, kiszivárgás;
  - közös forráshűség-kapu (`modulok/kapuk`, `kviz` profil): az idézet kötött, a **helyes válasz támogatott** (a kérdés a kontextus);
  - **a három rossz válasz nem támogatott** (`tobb_helyes`: ugyanazon az idézeten a rossz válasz is átmegy a támogatottsági,
    kényes-token és tagadás-vizsgálaton, ÉS a forrásmondat nem különbözteti meg a helyestől — képlet, saját szó, tagadás,
    megfordított sorrend: `generalas.megkulonbozteti`, C22b; a szabály a láncé, a mérés ugyanazt méri) és **hihető** (`hihetetlen`: a rossz válaszok közül legfeljebb `HIHETETLEN_MAX` marad jegyzeten kívül — a
    tartalmi tövei nem érik el a `HIHETO_KUSZOB` arányt a jegyzet, a kérdés és a helyes válasz tövei között) — a „pontosan egy helyes” és a „tipikus tévedés” lexikai közelítése;
  - duplikátum: a kérdés Jaccard-hasonlósága egy korábbi, átment kérdéshez ≥ `[kviz] duplikat_jaccard`.
Pontszám = 0,6 × az átmenő kérdések aránya (nevező: `max(értékelt, kerdes_cel)`) + 0,4 × az arany tények lefedettsége.

Mit nem lát: hogy a kérdés jól van-e feltéve, és hogy a kulcs valóban az egyetlen helyes; a szókészletet nem változtató hamis
válasz; a jegyzettől idegen, de hihető tévedés (a `hihetetlen` szabály ezt is bünteti — a kalibrálatlan induló küszöb, K134).
Ezt a C19 rétegzett mintáján a felhasználó bírálja, élesben a „hibás a kérdés” jelölések mérik (`tar.modell_statisztika`).

A kapuk profilja és a duplikátum-küszöb az `os.toml`-ból jön (`[kapuk.kviz]`, `[kviz]`): a `pontoz(rekordok)` nem kap `cfg`-t, ezért a
`tetelek(cfg)` eltárolja őket (a hívási sorrend az `eval.ertekel`-ben: tételek, majd pontozás); `tetelek` nélkül az alapértékek állnak.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
for _p in (str(REPO), str(ITT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kozos import arany as A  # noqa: E402
from kozos import kimenet  # noqa: E402
from modulok.kapuk import forras as KF  # noqa: E402
from modulok.kapuk import huseg as KH  # noqa: E402
from modulok.kviz import generalas as G  # noqa: E402
from modulok.kviz import mechanikus as MK  # noqa: E402
from modulok.kviz.promptok import GENERALO_PROMPT, PROMPT_VERZIO  # noqa: E402



def _keszit():
    """A generátor (`keszit.py`): a darab- és forrás-képzés egyetlen helye; útról töltve (az eval-keret is útról tölti a feladatot)."""
    spec = importlib.util.spec_from_file_location("mos_eval_kviz_keszit", ITT / "keszit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("mos_eval_kviz_keszit", mod)
    spec.loader.exec_module(mod)
    return sys.modules["mos_eval_kviz_keszit"]


keszit = _keszit()

ARANY = A.betolt(ITT)
VERZIO = "kviz-" + A.verzio(ARANY)
ROUTER_FELADAT = "kviz"

SULY = {"kerdesek": 0.6, "lefedettseg": 0.4}
HIHETO_KUSZOB = G.HIHETO_KUSZOB        # a lánc szabálya (C22b: a rossz válaszok kapuja a láncé, a mérés azt méri)
HIHETETLEN_MAX = G.HIHETETLEN_MAX
JELOLT_TUL = 2              # a lánc `szetszed(...)[:k + 2]` szabálya: ennyivel több jelölt számít a kértnél
ATFEDES_ARANY = 0.5         # az idézet és a tény forrásmondata: az egyik legalább fele a másikban áll (mint a `szoveg` pontozóban)

KAPU_KODOK = ("szerkezet", "valaszok", "tiltott_valasz", "jeloles", "kiszivargas", "idezet", "tamogatas", "kenyes", "tagadas",
              "tobb_helyes", "hihetetlen", "duplikatum")

_beall: dict = {"profil": KH.Profil(nev="kviz", idezet_min_szo=4, idezet_max_szo=60), "kviz": G.Beallitas()}
_forrasok: dict[str, tuple[str, KF.ForrasSzoveg]] = {}


def jegyzet(jid: str) -> dict:
    return next(j for j in ARANY["jegyzetek"] if j["id"] == jid)


def forras(jid: str) -> tuple[str, KF.ForrasSzoveg]:
    """(a jegyzet Markdownja, a teljes jegyzet `ForrasSzoveg`-e): a lánc `general`-jával azonos felépítés."""
    if jid not in _forrasok:
        md = keszit.forras_ut(jid).read_text(encoding="utf-8")
        _forrasok[jid] = (md, KF.ForrasSzoveg.jegyzetbol(md, cim=jegyzet(jid)["cim"]))
    return _forrasok[jid]


def max_tokens() -> int:
    return int(ARANY["kerdes_cel"]) * int(ARANY["token_per_kerdes"]) + int(ARANY["token_alap"])


def darab(jid: str) -> dict:
    """A jegyzet fagyasztott darabja; ha a darabolás elcsúszott (a hash nem egyezik), hiba — a mérés nem csúszhat el csendben."""
    j = jegyzet(jid)
    md, _ = forras(jid)
    d = keszit.darab_szoveg(md, j["ut"], j["darab"]["index"], int(ARANY["darab_max_karakter"]), int(ARANY["szakasz_min_karakter"]))
    if A.szoveg_sha256(d["szoveg"]) != j["darab"]["sha256"]:
        raise ValueError(f"{jid}: a darab elcsúszott (a kapuk/forrás-előkészítés vagy a darabolás változott): "
                         "futtasd a `modulok/eval/kviz/keszit.py --ellenoriz`-t, és hagyd jóvá az új halmazt")
    return d


def prompt(jid: str) -> str:
    j = jegyzet(jid)
    return GENERALO_PROMPT.format(k=int(ARANY["kerdes_cel"]), cim=j["cim"], szoveg=darab(jid)["szoveg"], kerulendo="")


def tetelek(cfg):
    _beall["profil"] = KH.profil(cfg, "kviz")
    _beall["kviz"] = G.beallitas(cfg)
    for j in ARANY["jegyzetek"]:
        yield {"id": f"kviz-{j['id']}",
               "keres": {"messages": [{"role": "user", "content": prompt(j["id"])}], "max_tokens": max_tokens()},
               "vart": {"fajta": "kviz", "jegyzet": j["id"], "prompt_verzio": PROMPT_VERZIO}}


# ---------------------------------------------------------------------- a kérdés kapui

def kerdes_kapu(fs: KF.ForrasSzoveg, j: MK.Jelolt, elfogadott: list[MK.Jelolt]) -> tuple[str | None, str | None, KH.Verdikt | None]:
    """Egy jelölt a lánc kapuin: `(kód, részlet, verdikt)`; `kód = None`: átment. Az első három kapu a lánc `general` kapuja
    (`G._forras_kapu`: ugyanaz a kód), a negyedik (rossz válaszok) a mérés saját, modell nélküli közelítése, az ötödik a duplikátum."""
    b = _beall["kviz"]
    ok = MK.kapu(j, b.engedett_jelek)
    if ok:
        return ok[0], ok[1], None
    kod, reszlet, v = G._forras_kapu(fs, j, _beall["profil"], b)
    if kod:
        return kod, reszlet, v
    hiba = G.rossz_valasz_hiba(fs, j, _beall["profil"], v)
    if hiba:
        return hiba[0], hiba[1], v
    if any(G.jaccard(j.kerdes, x.kerdes) >= b.duplikat_jaccard for x in elfogadott):
        return "duplikatum", "egy korábbi, átment kérdés ismétlése", v
    return None, None, v


def _atfed(a: tuple[int, int], b: tuple[int, int]) -> bool:
    kozos = min(a[1], b[1]) - max(a[0], b[0])
    return kozos >= ATFEDES_ARANY * min(a[1] - a[0], b[1] - b[0]) > 0


def pontoz_jegyzet(jid: str, valasz) -> dict:
    _, fs = forras(jid)
    jeloltek = G.szetszed(kimenet.tisztit(valasz))[:int(ARANY["kerdes_cel"]) + JELOLT_TUL]
    elfogadott: list[MK.Jelolt] = []
    helyek: list[tuple[int, int]] = []
    hibak, bukas = [], dict.fromkeys(KAPU_KODOK, 0)
    for i, j in enumerate(jeloltek, 1):
        kod, reszlet, v = kerdes_kapu(fs, j, elfogadott)
        if kod is None:
            elfogadott.append(j)
            helyek.append(v.hely)
        else:
            bukas[kod] = bukas.get(kod, 0) + 1
            hibak.append({"kerdes": i, "kapu": kod, "reszlet": reszlet})
    n = len(jeloltek)
    tenyek = []
    for t in jegyzet(jid)["tenyek"]:
        h = fs.keres(t["forras"])
        tenyek.append(h is not None and any(_atfed(e, h.hely) for e in helyek))
    resz = {"kerdesek": len(elfogadott) / max(n, int(ARANY["kerdes_cel"])),
            "lefedettseg": A.atlag(tenyek)}
    return {"pont": sum(SULY[k] * v for k, v in resz.items()), **resz, "jeloltek": n, "atment": len(elfogadott),
            "bukas": {k: v for k, v in bukas.items() if v}, "hibak": hibak}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): kinyerhető-e a válaszból legalább egy teljes jelölt (négy válasz és helyes betű)."""
    return any(len(j.valaszok) == 4 and j.helyes for j in G.szetszed(kimenet.tisztit(valasz)))


def pontoz(rekordok) -> dict:
    reszek, reszletek = [], []
    for r in rekordok:
        e = pontoz_jegyzet(r["vart"]["jegyzet"], r.get("valasz"))
        reszek.append(e)
        reszletek.append({"id": r["id"], **{k: (round(x, 3) if isinstance(x, float) else x) for k, x in e.items()}})
    if not reszek:
        return {"pontszam": 0.0, "kviz": None, "reszletek": []}
    k = {x: round(A.atlag(e[x] for e in reszek), 4) for x in ("pont", "kerdesek", "lefedettseg")}
    bukas: dict[str, int] = {}
    for e in reszek:
        for kod, db in e["bukas"].items():
            bukas[kod] = bukas.get(kod, 0) + db
    k["jeloltek"] = sum(e["jeloltek"] for e in reszek)
    k["bukas"] = bukas
    return {"pontszam": k["pont"], "kviz": k, "reszletek": reszletek}


def epseg() -> list[str]:
    """Az arany hibái (üres lista = rendben): a forrás sha256-ja, a darab hash-e, a tények megtalálhatósága, a verziók."""
    hibak = []
    if ARANY.get("prompt_verzio") != PROMPT_VERZIO:
        hibak.append(f"a prompt verziója elcsúszott: {ARANY.get('prompt_verzio')} ≠ {PROMPT_VERZIO} (a halmazt újra kell jóváhagyni)")
    for j in ARANY["jegyzetek"]:
        ut = keszit.forras_ut(j["id"])
        if not ut.is_file():
            hibak.append(f"{j['id']}: nincs forrás ({ut.name})")
            continue
        if A.sha256(ut) != j["forras_sha256"]:
            hibak.append(f"{j['id']}: a forrás sha256-ja nem egyezik")
            continue
        try:
            darab(j["id"])
        except ValueError as e:
            hibak.append(str(e))
        _, fs = forras(j["id"])
        for i, t in enumerate(j["tenyek"], 1):
            if fs.keres(t["forras"], 0.9) is None:
                hibak.append(f"{j['id']} tények {i}: nincs a forrásban")
        if len(j["tenyek"]) < 3:
            hibak.append(f"{j['id']}: a darabban kevesebb mint 3 tény van (a lefedettség nem mérhető)")
    return hibak


if __name__ == "__main__":
    h = epseg()
    print(f"{VERZIO}: {len(ARANY['jegyzetek'])} jegyzet, {sum(len(j['tenyek']) for j in ARANY['jegyzetek'])} tény; "
          + ("rendben" if not h else f"{len(h)} hiba"))
    for x in h:
        print(" -", x)
    raise SystemExit(1 if h else 0)
