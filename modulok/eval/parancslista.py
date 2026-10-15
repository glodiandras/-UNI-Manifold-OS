"""A mérés parancslistái a regiszterből (modellenként egy `bin/mos eval` sor):

    docs/MERES-ELOPROBA.md    előpróba (C18.1): `--limit 3`, külön kimenet (`{tmp}/eval-proba`), `--rogzit` nélkül,
                              a végén az összesítő (`osszesito.py`), amelynek zöld kapuja után indulhat az éles lista
    docs/MERES-PARANCSOK.md   az éles mérés a vázlat-aranyon (K28, nem rögzít), majd a K27 utáni újrapontozás
                              (`--csak-ertekel --rogzit`: worker és újragenerálás nélkül)

    bin/mos exec var/venv/bin/python -B modulok/eval/parancslista.py

A feladat-hozzárendelés a `[modellek.*].feladat` mezőből jön; a keret a mért/becsült csúcsból (≤ 5 GB: munka,
különben távol). A futásidő becslés: tételszám × modellméret szerinti tételidő, a gondolkodó modelleknél
tételenként + `gondolkodas_token` × 0,5 / token/s (az alapja a lista végén áll).
"""
from __future__ import annotations

import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT))
sys.path.insert(0, str(ITT / "kereses"))
from kozos import arany as A  # noqa: E402

FUTTATHATO = ("mlx-vlm", "mlx-lm", "sentence-transformers", "mlx-whisper")       # a worker mai hátterei (C05; C20b: mlx-whisper)
HANG_FUTTATO = ("mlx-whisper",)   # az `atirat` hang-kérését csak ez a háttér fogadja (C20b); a gemma `atirat` feladata nem mérhető
SORREND = ("ocr_kezi", "fuzet_fejezet", "fuzet_valaszto", "ocr_keplet", "szoveg", "kviz", "matek", "matek_cas", "matek_ellenorzo", "grafikon", "beagyazas", "rerank", "kod", "atirat", "tema", "kotes",
           "kiegeszites", "kifejtes", "osszefoglal_kijeloles")
UTASITHATO_VLM = ("qwen35_9b", "gemma4_12b", "qwen3_vl_4b", "qwen35_4b")   # a zárt fejezetlistát is megkapják
# a füzetlánc 2. lépésének (zárt listás jegyzetválasztás, C19) jelöltjei: a legacy választója (gemma4_12b), olvasója (qwen35_9b)
# és két munka-keretes szöveges modell
VALASZTO_JELOLT = ("gemma4_12b", "qwen35_9b", "qwen35_4b", "gemma4_e4b")
# a videólánc médiatársításának két ítélete (C20b: `tema`, `kotes`): a legacy két modellje (gemma-4-12B, Qwen3-VL-4B) és a két
# Qwen3.5 szöveges modell
TARSITAS_JELOLT = ("gemma4_12b", "qwen3_vl_4b", "qwen35_9b", "qwen35_4b")
# másodperc tételenként, modellméret szerint: (≤ 2,3 GB, ≤ 5 GB, fölötte)
TETELIDO = {"ocr_kezi": (10, 25, 60), "fuzet_fejezet": (12, 20, 45), "fuzet_valaszto": (3, 6, 14), "ocr_keplet": (2, 4, 8), "szoveg": (15, 30, 65), "kviz": (12, 25, 55),
            "matek": (10, 20, 45), "matek_cas": (13, 24, 50), "matek_ellenorzo": (8, 14, 28), "grafikon": (4, 8, 15), "beagyazas": (1.5, 1.5, 1.5),
            "rerank": (3, 3, 3), "kod": (20, 35, 70),
            "atirat": (60, 120, 150),   # C20b: ~5 perces videónként (becslés; a K29 méri)
            "tema": (4, 8, 16), "kotes": (2, 3, 6),   # C20b: ~3500 karakteres átirat + témalista, 24 token; ~2300 karakter, 8 token
            # J4/CX-011 (asszisztens): rövid kimenet (180 / 400 / 300 token), a kérés kicsi; a tényleges idő a K430-ban mérendő
            "kiegeszites": (2, 3, 6), "kifejtes": (5, 8, 16), "osszefoglal_kijeloles": (4, 6, 12)}
BETOLTES_PERC = 1                  # a 2026-10-03-i futásban az első tétel a betöltéssel együtt 25–45 s
TPS = (80, 40, 20)                 # token/s a méretosztály szerint (a Qwen3-VL-4B mért 41,8-ából arányosítva)
GONDOLKODAS_KITOLTES = 0.5         # a gondolkodási keret várhatóan ennyiedét használja el tételenként
ELOPROBA_LIMIT = 3
ELOPROBA_MAPPA = "{tmp}/eval-proba"
SORREND_SZOVEG = (
    "**Sorrend (C29.8)**: (1) **előpróba** (`docs/MERES-ELOPROBA.md`, `--limit 3`, külön mappa; K32/K59, az összesítő "
    "kapuja zöld) → (2) **az éles mérés a vázlat-aranyon** (K28, a `docs/MERES-PARANCSOK.md` első listája; "
    "a `var/router.sqlite`-ba nem rögzít) → (3) **a K27 jóváhagyás** (az `arany.json`-ok `jovahagyott` állapota) → "
    "(4) **újrapontozás** (a `docs/MERES-PARANCSOK.md` második listája: `--csak-ertekel --rogzit`, worker és "
    "újragenerálás nélkül; a pontozó a jóváhagyott `vart`-ot kapja, és az érvényes értékelés kerül a kalibrációs "
    "táblába) → (5) C19. A jóváhagyás így nem kényszerít újramérésre: a generált sor kulcsa a tétel azonosítója és a "
    "kérés ujjlenyomata, az aranyhalmaz verziója csak adat; újra csak az a tétel mér, amelynek a kérése (prompt, kép, "
    "beállítás) a K27-ben megváltozott. Az előpróba sorai nem kerülnek a `var/runs/eval` alá, és az élesből nem "
    "zárnak ki tételt.")


def tetelszamok(cfg) -> dict[str, int]:
    import korpusz as K
    matek = A.betolt(ITT / "matek")
    pk = K.parok()
    parok = pk["parok"]
    try:
        darab = sum(len(d) for d in K.korpusz(K.forras(cfg, pk), parok).values())
    except FileNotFoundError:
        darab = 1500
    return {"ocr_kezi": 97, "fuzet_fejezet": 97, "fuzet_valaszto": 97, "ocr_keplet": len(A.betolt(ITT / "ocr_keplet")["kepletek"]),
            "szoveg": 2 * len(A.betolt(ITT / "szoveg")["jegyzetek"]),
            "kviz": len(A.betolt(ITT / "kviz")["jegyzetek"]), "matek": len(matek["feladatok"]),
            "matek_cas": len(matek["feladatok"]),
            "matek_ellenorzo": len(matek["levezetesek"]) + sum(1 for f in matek["feladatok"] if f.get("lepesek")),
            "grafikon": len(A.betolt(ITT / "grafikon")["kepletek"]), "beagyazas": -(-darab // 16) + len(parok),
            "rerank": len(parok), "atirat": len(A.betolt(ITT / "atirat")["videok"]),
            "kod": 5 * len(A.betolt(ITT / "kod")["feladatok"]),
            "tema": sum(2 if v.get("cim") else 1 for v in A.betolt(ITT / "tema")["videok"]),
            "kotes": len(A.betolt(ITT / "kotes")["parok"]),
            "kiegeszites": len(A.betolt(ITT / "kiegeszites")["tetel"]), "kifejtes": len(A.betolt(ITT / "kifejtes")["tetel"]),
            "osszefoglal_kijeloles": len(A.betolt(ITT / "osszefoglal_kijeloles")["tetel"])}


def feladatai(m) -> list[str]:
    f = [x for x in m.feladat if x in SORREND and (x != "atirat" or m.futtato in HANG_FUTTATO)]
    if "ocr_kezi" in f and m.nev in UTASITHATO_VLM:
        f.append("fuzet_fejezet")
    if m.nev in VALASZTO_JELOLT:
        f.append("fuzet_valaszto")
    if m.nev in TARSITAS_JELOLT:
        f += ["tema", "kotes"]
    if "matek" in f:
        f.append("grafikon")
    kihagy = dict(m.meres_kihagy_feladat)                    # feladatonkénti kihagyás (K32), a származtatottak után
    return sorted((x for x in f if x not in kihagy), key=SORREND.index)


def kihagyott_feladatok(cfg) -> list[dict]:
    """A modelleken belül feladatonként kihagyott sorok (a regiszter `meres_kihagy` táblája) az indoklással."""
    from core.modell import beallitas as B
    return [{"modell": m.nev, "feladat": f, "ok": i}
            for m in B.betolt(cfg).modellek.values() for f, i in m.meres_kihagy_feladat]


def _kihagy_tabla(cfg) -> list[str]:
    ki = kihagyott_feladatok(cfg)
    if not ki:
        return []
    return ["## Kihagyott feladatok", "",
            "A modell a többi feladatán marad; a kihagyás a regiszter `[modellek.<m>.meres_kihagy]` táblája, a "
            "bejegyzés törlése visszahozza.", "", "| Modell | Feladat | Ok |", "|---|---|---|",
            *[f"| `{s['modell']}` | {s['feladat']} | {s['ok']} |" for s in ki], ""]


def tetelido(m, f: str) -> float:
    """Egy tétel becsült ideje másodpercben: a feladat tételideje + a gondolkodó modell többlete."""
    osztaly = 0 if m.csucs_gb <= 2.3 else 1 if m.csucs_gb <= 5.0 else 2
    gt = int(m.meres_beallitas(f).get("gondolkodas_token") or 0)
    return TETELIDO[f][osztaly] + gt * GONDOLKODAS_KITOLTES / TPS[osztaly]


def perc(m, feladatok: list[str], n: dict[str, int], limit: int | None = None) -> int:
    return round(BETOLTES_PERC + sum(min(n[f], limit or n[f]) * tetelido(m, f) for f in feladatok) / 60)


def sorok(cfg, eloproba: bool = False) -> tuple[list[dict], list[dict]]:
    from core.modell import beallitas as B
    n = tetelszamok(cfg)
    fut, nem = [], []
    for m in B.betolt(cfg).modellek.values():
        f = feladatai(m)
        ok = []
        if m.meres_kihagy:
            ok.append(f"kihagyva a mérésből: {m.meres_kihagy}")
        if m.konvertalas:
            ok.append("MLX-re konvertálni kell")
        if m.futtato not in FUTTATHATO:
            ok.append(f"nincs `{m.futtato}` háttér a workerben")
        if "atirat" in m.feladat and m.futtato in FUTTATHATO and m.futtato not in HANG_FUTTATO and not f:
            ok.append("az `atirat` hang-kérését csak az mlx-whisper háttér fogadja (C20b)")
        if ok or not f:
            nem.append({"modell": m.nev, "feladatok": list(m.feladat), "ok": "; ".join(ok) or "nincs C18-as feladata"})
            continue
        keret = "munka" if m.csucs_gb <= 5.0 else "tavol"
        vege = f' --limit {ELOPROBA_LIMIT} --kimenet "{ELOPROBA_MAPPA}"' if eloproba else ""
        fut.append({"modell": m.nev, "keret": keret, "feladatok": f, "csucs": m.csucs_gb, "gondolkodo": m.gondolkodo,
                    "perc": perc(m, f, n, ELOPROBA_LIMIT if eloproba else None),
                    "parancs": f"bin/mos eval {m.nev} {' '.join(f)} --keret {keret}{vege}",
                    "ujrapontozas": f"bin/mos eval {m.nev} {' '.join(f)} --csak-ertekel --rogzit"})
    fut.sort(key=lambda s: (s["keret"] != "munka", s["csucs"], s["modell"]))
    return fut, nem


def _sorlista(fut: list[dict]) -> list[str]:
    ki = ["## Munka-keret (5 GB): nappal is futhat", ""]
    for keret, cim in (("munka", None), ("tavol", "## Távol-keret (9 GB): hagyd magára a gépet")):
        if cim:
            ki += [cim, ""]
        for s in (x for x in fut if x["keret"] == keret):
            g = ", gondolkodó" if s["gondolkodo"] else ""
            ki += [f"`{s['modell']}` — becsült idő: **~{s['perc']} perc** ({s['csucs']} GB{g})", "", "```bash",
                   s["parancs"], "```", ""]
    ossz = sum(s["perc"] for s in fut)
    return ki + [f"Összesen kb. **{ossz // 60} óra {ossz % 60} perc** ({len(fut)} modell).", ""]


def _ujrapontozas(fut: list[dict]) -> list[str]:
    ki = ["## Újrapontozás a K27 jóváhagyása után (C29.8)", "",
          "Worker, modell és generálás nélkül (percek, nem órák): a meglévő sorokat értékeli újra a jóváhagyott `vart`-tal, "
          "és az érvényes értékelést a `var/router.sqlite`-ba rögzíti (a sor `aranyhalmaz_verzio` mezője a jóváhagyott "
          "verzió). Ha a K27-ben egy tétel **kérése** (prompt, kép) változott, annak a sora hiányzik: az értékelés "
          "`ervenyes: false`, a `--rogzit` csak a naplóba ír, a kilépési kód 1 — ilyenkor az első lista ugyanazon "
          "sora (folytatás: csak a hiányzó tételt generálja) után ez ismétlendő. „Kalibrált” jelet ez sem ad (C19).", "",
          "**Figyelem — a kalibrált jel megmaradása**: a `--kalibralt` nélküli `--rogzit` a (feladat, modell) sor már meglévő "
          "„kalibrált” jelét **megtartja**, ha a sor ugyanarra az aranyhalmaz-verzióra kalibrált (csak a pontszám frissül; a "
          "rögzítés megjegyzése jelzi). A jel levétele csak a kifejezett `--kalibralt-le`. Ha a K27 jóváhagyás **új** "
          "aranyverziót ad, a régi sor felülíródik és az új jelet nem kap: a router a feladatot addig nem routolja, amíg a "
          "`--kalibralt` nem kerül a rögzítésre (C19, a felhasználó döntése) — ellenőrizd a `bin/mos models list` kimenetét "
          "az újrapontozás előtt és után.", "",
          "```bash"]
    ki += [s["ujrapontozas"] for s in fut]
    return ki + ["```", ""]


def markdown_eloproba(cfg) -> str:
    fut, _ = sorok(cfg, eloproba=True)
    ki = ["# Előpróba a mérés előtt (C18.1)", "",
          f"Modellenként és feladatonként az első {ELOPROBA_LIMIT} tétel, külön mappában (`{ELOPROBA_MAPPA}`), "
          "`--rogzit` nélkül: a `var/runs/eval` éles sorai és a `var/router.sqlite` érintetlen. Terminálban, Claude "
          "nélkül futtatandó; a `mos eval` itt is `auto` módban fut (aktív használatkor szünetel). Cél: a levágás, a "
          "hurok, az üres válasz és a hiba **még az éles futás előtt** kiderüljön (a 2026-10-03-i mérés nagy része "
          "ezeken bukott el).", "", SORREND_SZOVEG, "",
          "Ezt a fájlt a `modulok/eval/parancslista.py` állítja elő a regiszterből (`config/os.toml`).", ""]
    ki += _sorlista(fut)
    ki += _kihagy_tabla(cfg)
    ki += ["## A kapu", "", "```bash", f'bin/mos exec var/venv/bin/python -B modulok/eval/osszesito.py "{ELOPROBA_MAPPA}"',
           "```", "",
           "Modell × feladat: levágott / hurok / üres / hiba / formátumhiba, érvényesség, pontszám, átlagos mp/tétel, "
           "és a legnagyobb `completion_tokens` a kerethez mérve. **Zöld** (kilépési kód 0): minden sor érvényes — "
           "jöhet az éles mérés a vázlat-aranyon (K28, `docs/MERES-PARANCSOK.md`; a K27 jóváhagyás az után). **Piros**: a hibás sor okát a "
           "regiszterben kell javítani (gondolkodó modellnél a `gondolkodas_token`, hurkos OCR-nél a "
           "`[meres.feladat.ocr_kezi] repetition_penalty`, sok worker-hibánál a modell kivétele a listából), és az "
           "előpróbát megismételni: a beállítás változása új ujjlenyomat, így a sor újramér, a régi a fájlban marad.",
           "", "3 tételen egyetlen rossz válasz is 33%: a kapu itt szándékosan szigorú.", ""]
    return "\n".join(ki)


def markdown(cfg) -> str:
    fut, nem = sorok(cfg)
    n = tetelszamok(cfg)
    ki = ["# A mérés parancslistája (C18 → C19)", "",
          "A C19 előtt, terminálban, Claude nélkül futtatandó. Egy sor egy modell minden feladatát méri; a `mos eval` "
          "folytatható (megszakítás után ugyanazzal a sorral folytatja), és `auto` módban fut: ha közben dolgozol a "
          "gépen, szünetel. Az első lista a generálás (és a vázlat-aranyon kapott pontszám kiírása), **nem rögzít**; "
          "a pontszámot a `var/router.sqlite`-ba a második lista `--rogzit`-je írja, a K27 után; „kalibrált” jelet a "
          "C19 ad.",
          "", SORREND_SZOVEG, "",
          "**Érvényesség (C18.1)**: minden értékelés kap egy `ervenyes` mezőt; ha a levágott, hurkos, üres vagy hibás "
          "tételek aránya 10% fölött van (`[meres] ervenyes_kuszob`), vagy tétel hiányzik, a `--rogzit` csak a "
          "naplóba ír (`ervenyes = 0`), kalibrálható sort nem, és a parancs 1-es kóddal lép ki. A folytatás a tétel "
          "azonosítója **és** a kérés ujjlenyomata (beállítás, prompt, a képek tartalom-hash-e, a modell repója) szerint "
          "megy: a beállítás változása után a sor újramér, az aranyhalmaz verziójának változása nem (C29.8). A "
          "2026-10-03-i (C18.1 előtti) sorok ezért mind újramérődnek, a ministral3_3b `szoveg` is (15% levágott "
          "kártyalista).",
          "", "Ezt a fájlt a `modulok/eval/parancslista.py` állítja elő a regiszterből (`config/os.toml` `[modellek.*]`).",
          "", "## Előtte egyszer", "", "```bash", "bin/mos exec var/venv/bin/python -B modulok/eval/ocr_kezi/feladat.py", "```",
          "", "A 97 fotó megléte és hash-e (üres `hash_elter` lista kell), és a bíró plafonja.", "",
          "A `--keret`-es sor (C19, M3) saját modell-workert indít a keret-felülírással: ha a Manifold app (a core workere) fut, "
          "a mérés hibával áll meg — előtte zárd be az appot. A `--rogzit` csak a teljes halmazon (`--limit` és `--tetel` nélkül) "
          "megy, a `--kalibralt` vázlat-aranyon hiba.", ""]
    ki += _sorlista(fut)
    ki += _ujrapontozas(fut)
    ki += ["## Ma nem futtatható", "", "| Modell | Feladat | Ok |", "|---|---|---|"]
    ki += [f"| `{s['modell']}` | {', '.join(s['feladatok'])} | {s['ok']} |" for s in nem]
    ki += [""] + _kihagy_tabla(cfg)
    ki += ["Az `atirat` (K29) a C20b óta mérhető: a hang-kérést (`/v1/audio/transcriptions`) csak az `mlx-whisper` háttér "
           "fogadja, ezért a gemma-modellek `atirat` feladata kimarad a soraikból; a `parakeet_v3` (`mlx-audio`) "
           "háttere csak mért igény mellett készül.", "",
           "## Az ocr_kezi és a legacy", "",
           "A 2.0 `ocr_kezi` mérése a nyers fotókon, egy lépésben mér; a legacy 87/97-e a papírra kivágott, "
           "elforgatott képeken és a kétlépéses „erős módszerrel” született. A kettő **nem összevethető**; a kivágás "
           "és a forgatás portja a C21 dolga (NAPLO, Ötletek).", "",
           "## A becslés alapja", "",
           f"Tételszám × tételidő + modellenként {BETOLTES_PERC} perc betöltés. A gondolkodó modelleknél (regiszter: "
           "`gondolkodo`, `gondolkodas_token`) tételenként + `gondolkodas_token` × "
           f"{GONDOLKODAS_KITOLTES} / token/s, a token/s méretosztályonként {TPS[0]} / {TPS[1]} / {TPS[2]}. Mért adat "
           "kevés van: a Qwen3-VL-4B 41,8 token/s (C05 bench), a legacy lánc 95 s/fotó (9B + 12B, két hívás); a többi "
           "ebből arányosított becslés, a valós idő ±50%-kal eltérhet. Az előpróba összesítője tételenkénti mért "
           "időt ad: ezzel pontosítható.", "",
           "| Feladat | Tétel | ≤ 2,3 GB | ≤ 5 GB | > 5 GB |", "|---|---|---|---|---|"]
    ki += [f"| `{f}` | {n[f]} | {TETELIDO[f][0]} s | {TETELIDO[f][1]} s | {TETELIDO[f][2]} s |" for f in SORREND]
    ki += ["", "A `fuzet_fejezet` (a legacy 1. lépése) csak az utasítható képmodellek sorában áll; a `grafikon` a "
           "matek-modellekében. Mindkettő router-feladat (63(e), 72. döntés), a `kiegeszites`, `kifejtes` és "
           "`osszefoglal_kijeloles` (J4, 85. döntés) is: ezek aranyhalmaza vázlat (`-vazlat` verzió), kalibrált jelet a "
           "K27/K430 jóváhagyás előtt nem kaphatnak.", ""]
    return "\n".join(ki)


if __name__ == "__main__":
    from core import config
    cfg = config.load()
    docs = Path(cfg.expand("{os}")) / "docs"
    for nev, fn in (("MERES-PARANCSOK.md", markdown), ("MERES-ELOPROBA.md", markdown_eloproba)):
        (docs / nev).write_text(fn(cfg), encoding="utf-8")
        print(docs / nev)
