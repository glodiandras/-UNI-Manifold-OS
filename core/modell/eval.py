"""`mos eval` — egy modell egy feladat aranyhalmazán (D5, D9; a legacy `mos eval` általános kerete).

A legacy négy feladata (kötés, N-kötés, téma) a vault `media_itelet`-jére épült, amely a 2.0-ban még
nincs portolva; ezért itt a keret él, a feladatokat a C18 adja. Szerződés:

    {modulok}/eval/<feladat>/feladat.py
        VERZIO: str                           az aranyhalmaz verziója (a kalibrációs táblába kerül)
        ROUTER_FELADAT: str (opcionális)      a router feladatneve (alap: a mappa neve)
        tetelek(cfg) -> Iterable[dict]        {"id": str, "keres": {tipus?, messages|input|query…}, "vart": …}
        pontoz(rekordok) -> dict              {"pontszam": float, …}; a rekord: {id, verzio, vart, valasz, mp, …}
        formatum_ok(valasz, vart) -> bool     (opcionális) a válasz alakja értelmezhető-e (C18.1, csak jelentés)

A közös pontozó-segédek a `{modulok}/eval/kozos/` csomagban élnek (C18).

**Kérés-beállítás (C18.1)**: a tétel kérését a regiszter egészíti ki (`keres_beallitas`): a feladat
`[meres.feladat.<f>]` alapja, a modell szakaszának mérés-kulcsai (`gondolkodas`, `gondolkodas_token`, …),
a modell `meres.<f>` alszakasza, végül a próbához adott `--beallit`. A feladat.py csak a feladat saját
keretét (`max_tokens`) adja; a gondolkodó modell token-kerete, az ismétlés-büntetés a regiszteré.

**Folytatás és értékelés** (C29.8, T046): a sor kulcsa a tétel azonosítója ÉS a feloldott kérés ujjlenyomata
(`beallitas`: a beállítások, a prompt, a képek TARTALOM-hash-e — az út nem —, a modell repója). A rekord `verzio`
mezője az aranyhalmaz generáláskori verziója: **adat, nem kulcs** — a K27 jóváhagyása (a `-vazlat` levétele) vagy egy
javított `vart` nem tesz elavulttá egyetlen generált sort sem. Az értékelés a pontozáskor a tétel AKTUÁLIS `vart`-ját
adja a pontozónak, és rögzíti a használt aranyhalmaz-verziót (`aranyhalmaz_verzio`) és a sorok generálási verzióit
(`sor_verziok`). A megváltozott kérésű (prompt, beállítás, kép) tétel újramérődik; a régi sorok a fájlban maradnak.
Az újrapontozás (K27 után) `--csak-ertekel`-lel megy: worker nélkül, generálás nélkül.

**Memória** (C29.8, T045): a sor a worker mérését hordozza (`memoria`: a kérés mlx-csúcsmemóriája GB-ban, a modell betöltésének
ténye és ideje); az értékelés `futas` mezője a maximumot (`csucs_gb_max`), a betöltések számát és idejét, és a regiszter
`csucs_gb`-ját; a `--rogzit` figyelmeztet, ha a mért csúcs a regiszterbelit `TURES_GB`-nál jobban meghaladja.

**Érvényesség** (`ervenyesseg.py`): az értékelés `ervenyes` mezője hamis, ha a levágott, hurkos, üres,
hibás tételek aránya a küszöb (`[meres] ervenyes_kuszob`) fölött van, vagy tétel hiányzik. Érvénytelen
értékelést a `--rogzit` csak a hozzáfűzős naplóba ír (`ervenyes = 0`), kalibrálható sort nem.

A futás a workeren át megy (próba: kifejezett modell és keret; a vaultba semmi nem ír), folytatható,
és a `{runs}/eval/<modell>/<feladat>.jsonl`-be ír (a `--kimenet` más mappába: előpróba, kézi próba; ilyenkor
nincs `--rogzit`). A `--rogzit` a pontszámot a kalibrációs táblába írja; „kalibrált” jelet csak a
`--kalibralt` ad (a C19 vagy a felhasználó döntése). A `--kalibralt` nélküli `--rogzit` a meglévő jelet nem veszi le
(ugyanarra az aranyhalmaz-verzióra kalibrált sor jele megmarad: az újrapontozás biztonságos); a kifejezett levétel
`--kalibralt-le`. Alapból `auto` módban fut: ha közben dolgozol a
gépen, szünetel.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

from .. import config
from . import beallitas as B
from . import ervenyesseg, kliens, revizio
from . import kalibracio
from .kalibracio import vazlat

BEALLITAS_MEZOK = ("max_tokens", "temperature", "gondolkodas", "repetition_penalty", "repetition_context_size")
TURES_GB = 0.2                 # a mért csúcs és a regiszterbeli `csucs_gb` közti tűrés (a legacy mérése más keretben készült)


def feladat_modul(cfg: config.Config, feladat: str):
    ut = cfg.path("modulok") / "eval" / feladat / "feladat.py"
    if not ut.is_file():
        raise FileNotFoundError(f"nincs ilyen aranyhalmaz-feladat: {ut} (a feladat mappája: modulok/eval/<feladat>/)")
    spec = importlib.util.spec_from_file_location(f"mos_eval_{feladat}", ut)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for kell in ("VERZIO", "tetelek", "pontoz"):
        if not hasattr(mod, kell):
            raise AttributeError(f"{ut}: hiányzik a(z) {kell}")
    return mod


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]


def keres_beallitas(b: B.Beallitas, modell: B.Modell, feladat: str, keres: dict,
                    felulir: dict | None = None) -> dict:
    """A tétel kérése a regiszter mérés-beállításával (a sorrend a modul leírásában); csak a chat-kérést érinti."""
    beall = {**dict(((b.meres.get("feladat") or {}).get(feladat)) or {}), **modell.meres_beallitas(feladat),
             **(felulir or {})}
    rossz = sorted(set(beall) - set(B.MERES_KULCSOK))
    if rossz:
        raise ValueError(f"ismeretlen mérés-kulcs ({feladat}): {', '.join(rossz)}")
    k = dict(keres)
    if k.get("tipus", "chat") != "chat":
        return k
    mt = int(k.get("max_tokens", 256))
    if beall.get("max_tokens_szorzo"):
        mt = round(mt * float(beall["max_tokens_szorzo"]))
    mt += int(beall.get("gondolkodas_token") or 0)
    k["max_tokens"] = mt
    k["temperature"] = float(beall.get("temperature", k.get("temperature", 0.0)))       # L27: determinisztikus
    for kulcs in ("gondolkodas", "repetition_penalty", "repetition_context_size"):
        if beall.get(kulcs) is not None:
            k[kulcs] = beall[kulcs]
    return k


_KEP_HASH: dict = {}           # (út, mtime_ns, méret) → tartalom-hash: a futtatás és az értékelés ne hash-eljen kétszer


def _kep_hash(ut) -> str:
    try:
        p = Path(ut)
        st = p.stat()
        kulcs = (str(p), st.st_mtime_ns, st.st_size)
        if kulcs not in _KEP_HASH:
            _KEP_HASH[kulcs] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        return _KEP_HASH[kulcs]
    except OSError as e:
        raise FileNotFoundError(f"hiányzik vagy nem olvasható a kép: {ut}") from e


def ujjlenyomat(modell: B.Modell, keres: dict) -> str:
    """A feloldott kérés ujjlenyomata: beállítások + prompt + a képek tartalom-hash-e (az út NEM számít, a sorrend igen; C29.8,
    T046) + a modell repója. Kép nélküli (szöveges) kérésnél az alak a régi: a meglévő sorok kulcsa érvényes marad."""
    adat = {"repo": modell.repo, "keres": {k: v for k, v in keres.items() if k not in ("images", "audio")}}
    if keres.get("images"):
        adat["kepek"] = [_kep_hash(u) for u in keres["images"]]
    if keres.get("audio"):                       # C20b: a hang is tartalom szerint (az út nem számít)
        adat["hang"] = _kep_hash(keres["audio"])
    return hashlib.sha256(json.dumps(adat, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _beallitas_kivonat(keres: dict) -> dict:
    return {"tipus": keres.get("tipus", "chat"), **{k: keres[k] for k in BEALLITAS_MEZOK if k in keres}}


def _valaszt(mod_, cfg: config.Config, limit: int | None, tetel_idk: list[str] | None) -> tuple[list[dict], int]:
    """A kiválasztott tételek és a halmaz teljes tételszáma (a `--limit`/`--tetel` nélküli)."""
    arany = getattr(mod_, "ARANY", None)
    if isinstance(arany, dict) and (arany.get("hianyzik") or arany.get("allapot") == "hianyzik"):
        raise ValueError(f"ehhez a feladathoz nincs aranyhalmaz ({arany.get('fajl', 'arany.json')}): a mérés nem indítható")
    tetelek = list(mod_.tetelek(cfg))
    osszes = len(tetelek)
    if tetel_idk:
        ismert = {t["id"] for t in tetelek}
        ismeretlen = [i for i in tetel_idk if i not in ismert]
        if ismeretlen:
            raise ValueError(f"ismeretlen tétel: {', '.join(ismeretlen)}")
        tetelek = [t for t in tetelek if t["id"] in set(tetel_idk)]
    return (tetelek[:limit] if limit else tetelek), osszes


def _kimenet(cfg: config.Config, modell: str, kimenet: Path | None) -> Path:
    return (Path(kimenet) if kimenet else cfg.path("runs") / "eval") / modell


def _hiv(u: str, modell: str, keres: dict, keret: str | None, mod: str) -> tuple[object, dict]:
    tipus = keres.get("tipus", "chat")
    body = {k: v for k, v in keres.items() if k != "tipus"}
    body.update(model=modell, proba=True, mod=mod)
    if keret:
        body["keret"] = keret
    if tipus == "chat":
        r = kliens.chat_keres(u, body)      # időkorláttal és egy óvatos újrapróbával (egy elveszett válasz nem akaszt meg)
        return r["choices"][0]["message"]["content"], {"usage": r.get("usage"), "memoria": r.get("memoria")}
    if tipus == "embed":
        r = kliens.keres(u, "/v1/embeddings", body)
        return [d["embedding"] for d in r["data"]], {"memoria": r.get("memoria")}
    if tipus == "rerank":
        r = kliens.keres(u, "/v1/rerank", body)
        return [x["relevance_score"] for x in r["results"]], {"memoria": r.get("memoria")}
    if tipus == "atirat":
        r = kliens.keres(u, "/v1/audio/transcriptions", body)
        return r["text"], {"memoria": r.get("memoria"), "hossz_mp": r.get("hossz_mp"), "szegmens_db": len(r.get("szegmensek") or [])}
    raise ValueError(f"ismeretlen kérésfajta: {tipus}")


def _feloldott(cfg: config.Config, modell: str, feladat: str, mod_, limit, tetel_idk, felulir):
    b = B.betolt(cfg)
    m = b.modell(modell)
    tetelek = []
    valasztott, osszes = _valaszt(mod_, cfg, limit, tetel_idk)
    for t in valasztott:
        k = keres_beallitas(b, m, feladat, t["keres"], felulir)
        tetelek.append({**t, "keres": k, "beallitas": ujjlenyomat(m, k)})
    return b, tetelek, osszes


def futtat(cfg: config.Config, modell: str, feladat: str, u: str, keret: str | None = None, limit: int | None = None,
           mod: str = "auto", log=print, felulir: dict | None = None, kimenet: Path | None = None,
           tetel_idk: list[str] | None = None) -> Path:
    mod_ = feladat_modul(cfg, feladat)
    ki = _kimenet(cfg, modell, kimenet) / f"{feladat}.jsonl"
    ki.parent.mkdir(parents=True, exist_ok=True)
    _, tetelek, _ = _feloldott(cfg, modell, feladat, mod_, limit, tetel_idk, felulir)
    lenyomat = {t["id"]: t["beallitas"] for t in tetelek}
    kesz = {r["id"] for r in _jsonl(ki) if r.get("beallitas") == lenyomat.get(r["id"])}        # T046: id + ujjlenyomat (a verzió adat)
    beall = sorted({json.dumps(_beallitas_kivonat(t["keres"]), ensure_ascii=False, sort_keys=True) for t in tetelek})
    log(f"[eval] {modell} · {feladat} (aranyhalmaz {mod_.VERZIO}): {len(tetelek)} tétel, ebből kész "
        f"{sum(1 for t in tetelek if t['id'] in kesz)}; kérés: {'; '.join(beall)}")
    for i, t in enumerate(tetelek, 1):
        if t["id"] in kesz:
            continue
        t0 = time.time()
        # a `vart` nem kerül a sorba (T046): az értékelés a pontozáskor az aktuális aranyból veszi; a `verzio` a generáláskor érvényes
        alap = {"id": t["id"], "verzio": mod_.VERZIO, "beallitas": t["beallitas"],
                "keres_beallitas": _beallitas_kivonat(t["keres"])}
        try:
            valasz, extra = _hiv(u, modell, t["keres"], keret, mod)
            rec = {**alap, "valasz": valasz, "mp": round(time.time() - t0, 2), **extra}
        except kliens.KliensHiba as exc:
            if exc.kod == 503:
                raise                                  # leállás / keret: a futás megáll, a kész sorok megmaradnak
            rec = {**alap, "valasz": None, "hiba": str(exc), "mp": round(time.time() - t0, 2)}
        with open(ki, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[manifold-progress] {100.0 * i / len(tetelek):.1f}%", flush=True)
    return ki


def ertekel(cfg: config.Config, modell: str, feladat: str, limit: int | None = None, felulir: dict | None = None,
            kimenet: Path | None = None, tetel_idk: list[str] | None = None) -> dict:
    mod_ = feladat_modul(cfg, feladat)
    d = _kimenet(cfg, modell, kimenet)
    b, tetelek, osszes = _feloldott(cfg, modell, feladat, mod_, limit, tetel_idk, felulir)
    lenyomat = {t["id"]: t["beallitas"] for t in tetelek}
    utolso = {r["id"]: r for r in _jsonl(d / f"{feladat}.jsonl") if r.get("beallitas") == lenyomat.get(r["id"])}
    # az aktuális tételek és ujjlenyomatuk sorai; a pontozó a tétel AKTUÁLIS `vart`-ját kapja (T046: a K27 után nem kell újragenerálni)
    rekordok = [{**utolso[t["id"]], "vart": t.get("vart")} for t in tetelek if t["id"] in utolso]
    erv = ervenyesseg.vizsgal(rekordok, float(b.meres["ervenyes_kuszob"]), getattr(mod_, "formatum_ok", None))
    erv["hianyzo"] = len(tetelek) - len(rekordok)
    erv["ervenyes"] = erv["ervenyes"] and erv["hianyzo"] == 0
    tok = [int((r.get("usage") or {}).get("completion_tokens") or 0) for r in rekordok]
    mem = [r.get("memoria") or {} for r in rekordok]
    csucsok = [m["csucs_gb"] for m in mem if m.get("csucs_gb") is not None]
    betoltes_mp = [m.get("betoltes_mp") or 0.0 for m in mem]
    sor_verziok: dict = {}
    for r in rekordok:
        sor_verziok[r.get("verzio")] = sor_verziok.get(r.get("verzio"), 0) + 1
    ert = {"modell": modell, "feladat": feladat, "router_feladat": getattr(mod_, "ROUTER_FELADAT", feladat),
           "aranyhalmaz_verzio": mod_.VERZIO, "sor_verziok": sor_verziok, "n": len(rekordok), **mod_.pontoz(rekordok),
           "ervenyes": erv["ervenyes"], "ervenyesseg": erv,
           # C19 (T050): csak a teljes, `--limit`/`--tetel` nélküli halmaz értékelése rögzíthető
           "tetelszam": osszes, "teljes": len(tetelek) == osszes and not limit and not tetel_idk,
           "keres_beallitas": [json.loads(x) for x in sorted({json.dumps(_beallitas_kivonat(t["keres"]),
                                                                        ensure_ascii=False, sort_keys=True)
                                                             for t in tetelek})],
           "futas": {"mp_atlag": round(sum(r.get("mp") or 0 for r in rekordok) / len(rekordok), 2) if rekordok else 0,
                     "mp_atlag_betoltes_nelkul": round(sum((r.get("mp") or 0) - bm for r, bm in zip(rekordok, betoltes_mp))
                                                       / len(rekordok), 2) if rekordok else 0,
                     "completion_tokens_max": max(tok, default=0),
                     # T045 (a K28 előfeltétele): a kérés mlx-csúcsmemóriája, a betöltések, és a regiszter értéke az összevetéshez
                     "csucs_gb_max": max(csucsok) if csucsok else None,
                     "betoltesek": sum(1 for m in mem if m.get("betoltve")),
                     "betoltes_mp_ossz": round(sum(betoltes_mp), 2),
                     "regiszter_csucs_gb": b.modell(modell).csucs_gb},
           # C19 (T141): a mért modell pillanatképe (a rögzített revízió, ha helyben megvan; különben a refs/main)
           "snapshot": revizio.mert_pillanatkep(cfg.path("models"), b.modell(modell).repo, b.modell(modell).revizio)}
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{feladat}-ertekeles.json").write_text(json.dumps(ert, ensure_ascii=False, indent=1), encoding="utf-8")
    return ert


def csucs_figyelmeztetes(cfg: config.Config, ert: dict) -> str | None:
    """Figyelmeztetés, ha a mért csúcsmemória a regiszterbeli `csucs_gb`-t `TURES_GB`-nál jobban meghaladja (T045): a keret-döntés
    és a router alapja a regiszter értéke, ezért a mérés után javítandó. `None`: nincs mérés, vagy a mért érték a tűrésen belül."""
    futas = ert.get("futas") or {}
    mert, regiszter = futas.get("csucs_gb_max"), futas.get("regiszter_csucs_gb")
    if mert is None or regiszter is None or mert <= regiszter + TURES_GB:
        return None
    return (f"a mért csúcsmemória ({mert:g} GB) meghaladja a regiszterbelit ({regiszter:g} GB, tűrés {TURES_GB:g} GB): a "
            f"`[modellek.{ert.get('modell')}] csucs_gb` a keret-döntés alapja — javítandó, mielőtt a router használná")


def rogzit(cfg: config.Config, ert: dict, kalibralt: bool | None, megjegyzes: str = "") -> dict:
    """Érvényes értékelés: kalibrációs sor. Érvénytelen (vagy kapu nélküli): csak naplósor, `ervenyes = 0`.

    `kalibralt`: `True` felveszi, `False` kifejezetten leveszi, `None` nem változtat a jelen (`Tabla.rogzit`)."""
    ervenyes = bool(ert.get("ervenyes"))
    if not ert.get("teljes"):
        raise ValueError(f"csak a teljes halmaz értékelése rögzíthető: {ert.get('n')}/"
                         f"{ert.get('tetelszam', '?')} tétel — `--limit` és `--tetel` nélkül értékeld")
    if kalibralt and vazlat(str(ert.get("aranyhalmaz_verzio") or "")):
        raise ValueError(f"vázlat-aranyhalmazon ({ert.get('aranyhalmaz_verzio')}) nem adható kalibrált jel")
    if kalibralt and not ervenyes:
        raise ValueError("érvénytelen értékelés nem kaphat kalibrált jelet: "
                         + (ervenyesseg.osszegzes(ert["ervenyesseg"]) if ert.get("ervenyesseg") else "nincs kapu"))
    alap = megjegyzes or f"mos eval, n={ert['n']}"
    fig = csucs_figyelmeztetes(cfg, ert)
    if fig:
        alap += f"; FIGYELEM: {fig}"
    if not ervenyes:
        alap = "érvénytelen: " + (ervenyesseg.osszegzes(ert["ervenyesseg"]) if ert.get("ervenyesseg")
                                          else "nincs érvényességi kapu") + f"; {alap}"
    t = kalibracio.megnyit(cfg)
    try:
        return t.rogzit(ert["router_feladat"], ert["modell"], float(ert["pontszam"]), ert["aranyhalmaz_verzio"],
                        kalibralt, alap, ervenyes=ervenyes, snapshot=ert.get("snapshot") or "")
    finally:
        t.close()


def _beallit(par: list[str]) -> dict:
    ki = {}
    for p in par or []:
        kulcs, sep, ertek = p.partition("=")
        if not sep or kulcs not in B.MERES_KULCSOK:
            raise ValueError(f"--beallit KULCS=ÉRTÉK, a kulcs: {', '.join(B.MERES_KULCSOK)} (kapott: {p})")
        try:
            ki[kulcs] = json.loads(ertek)
        except ValueError:
            ki[kulcs] = ertek
    return ki


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mos eval", description="Egy modell egy feladat aranyhalmazán (a workeren át).")
    ap.add_argument("modell")
    ap.add_argument("feladatok", nargs="+")
    ap.add_argument("--keret", help="munka | tavol | GB (a távol-kerethez hagyd magára a gépet)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--mod", choices=("auto", "interaktiv"), default="auto",
                    help="auto (alap): aktív használatkor szünetel; interaktiv: nem vár")
    ap.add_argument("--rogzit", action="store_true", help="a pontszám a kalibrációs táblába (var/router.sqlite)")
    jel = ap.add_mutually_exclusive_group()
    jel.add_argument("--kalibralt", action="store_true", help="a rögzített sor „kalibrált” jelet kap")
    jel.add_argument("--kalibralt-le", action="store_true",
                     help="a rögzített sor kalibrált jelét kifejezetten leveszi; e nélkül (és --kalibralt nélkül) a jel "
                          "változatlan marad, ha a sor ugyanarra az aranyhalmaz-verzióra már kalibrált")
    ap.add_argument("--megjegyzes", default="")
    ap.add_argument("--kimenet", help="más kimeneti mappa (pl. \"{tmp}/eval-proba\"): előpróba, kézi próba; --rogzit nélkül")
    ap.add_argument("--beallit", action="append", metavar="KULCS=ÉRTÉK",
                    help="próbához a kérés-beállítás felülírása (pl. repetition_penalty=1.1); --rogzit nélkül")
    ap.add_argument("--tetel", action="append", metavar="ID", help="csak ezek a tételek (ismételhető)")
    ap.add_argument("--csak-ertekel", action="store_true",
                    help="nem indít workert és nem generál: a meglévő sorokat értékeli (újrapontozás; a hiányzó tétel érvénytelen)")
    a = ap.parse_args(argv)
    if (a.kalibralt or a.kalibralt_le) and not a.rogzit:
        ap.error("a --kalibralt és a --kalibralt-le csak a --rogzit mellett értelmes")
    if a.rogzit and (a.kimenet or a.beallit or a.tetel or a.limit):
        ap.error("a --rogzit csak az éles kimenettel, a teljes halmazon (--limit, --tetel és --beallit nélkül) megy")
    cfg = config.load()
    kimenet = Path(cfg.expand(a.kimenet)) if a.kimenet else None
    try:
        felulir = _beallit(a.beallit)
        b = B.betolt(cfg)
        b.modell(a.modell)
        # M3 (C19): a kérés `keret`-je a workerben csak szűkíthet; a kifejezett keretű (pl. távol-keretes) mérés ezért saját
        # workert indít a `MANIFOLD_MODELL_KERET_GB`-felülírással (L24) — a futó idegen workert nem használja
        felulir_env = {"MANIFOLD_MODELL_KERET_GB": f"{b.keret_gb(a.keret):g}"} if a.keret else None
    except (B.RegiszterHiba, ValueError) as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 2
    folyamat = None if a.csak_ertekel else kliens.Folyamat(cfg, env=felulir_env, sajat=bool(a.keret))
    kod = 0
    try:
        u = folyamat.biztosit() if folyamat else None
        for f in a.feladatok:
            if not a.csak_ertekel:
                futtat(cfg, a.modell, f, u, a.keret, a.limit, a.mod, felulir=felulir, kimenet=kimenet, tetel_idk=a.tetel)
            ert = ertekel(cfg, a.modell, f, a.limit, felulir=felulir, kimenet=kimenet, tetel_idk=a.tetel)
            print(json.dumps(ert, ensure_ascii=False, indent=1))
            print(f"[eval] {a.modell} · {f}: {ervenyesseg.osszegzes(ert['ervenyesseg'])}")
            if not ert["ervenyes"]:
                kod = 1
            fig = csucs_figyelmeztetes(cfg, ert)
            if fig:
                print(f"[eval] FIGYELEM: {fig}")
            if a.rogzit:
                sor = rogzit(cfg, ert, True if a.kalibralt else False if a.kalibralt_le else None, a.megjegyzes)
                print("[eval] rögzítve" + ("" if sor.get("ervenyes") else " (csak a naplóba, érvénytelen)") + ":",
                      json.dumps(sor, ensure_ascii=False))
    except (FileNotFoundError, AttributeError, ValueError, kliens.KliensHiba) as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 2
    finally:
        if folyamat:
            folyamat.leallit()
    return kod


if __name__ == "__main__":
    sys.exit(main())
