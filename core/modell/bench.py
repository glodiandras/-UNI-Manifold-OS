"""`mos bench` — sebesség és memóriaterhelés a jelölt modelleken (D5: a mérés dönt).

Minden modell KÜLÖN gyermekfolyamatban fut (`python -m core.modell.bench --gyermek <név>`), a betöltőn
át (zár, keret, őr: a mérés sem kerülheti meg, CLAUDE.md 4.), így a mérések nem szennyezik egymást. A
szülő közben félmásodpercenként mintavételezi a rendszert (szabad memória %, swap). Futás előtt a futó
workert kiüríti (`/unload`), különben a közös zárra várna.

Feladatok: (1) kötés-ítélet egy minta-páron (`--minta <json>` első párja, címke: `--cimkek <json>`; nélküle a
beépített semleges pár); (2) ötmondatos összefoglaló (generálási sebesség); (3) egy fotó átirata (`--foto <kép vagy
mappa>`; nélküle kimarad) — CSAK olvasva, a `{tmp}` alá kicsinyítve, a mérés után törölve. A `csucs_gb` mérési
feltételei: `--cache-limit-gb 1`, 1400 px, a könyvtár alapértelmezett beolvasási lépése (`--prefill-lepes 0`).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from .. import config
from . import beallitas as B
from . import kliens, memoria

KOTES_PROMPT = (
    "Egy oktatóvideó részletét és egy tankönyvi jegyzet részletét látod. "
    "Magyarázza-e a videórészlet a jegyzet tartalmát (nem csak megemlíti)? "
    "Válaszolj egyetlen szóval: igen vagy nem.\n\n"
    "VIDEÓRÉSZLET:\n{ablak}\n\nJEGYZET ({cim}):\n{reszlet}\n\nVálasz:"
)
# A beépített minta-pár (`--minta` nélkül): semleges tankönyvi szöveg, a várt ítélet „igen”.
ALAP_PAR = {
    "ablak_szoveg": "A fotoszintézis során a növények a fény energiáját hasznosítják: a levelekben lévő klorofill "
                    "elnyeli a fényt, és a szén-dioxidból meg a vízből szőlőcukor és oxigén keletkezik.",
    "jegyzet_cim": "Fotoszintézis",
    "jegyzet_reszlet": "A fotoszintézis a zöld növények anyagcsere-folyamata: fényenergia segítségével szén-dioxidból "
                       "és vízből szerves anyag (glükóz) és oxigén képződik. A folyamat a zöld színtestekben zajlik.",
    "y": 1,
}
KEP_KITERJESZTES = {".jpg", ".jpeg", ".png"}
KEP_PROMPT = ("Írd át pontosan a képen látható kézírásos magyar szöveget. "
              "Ahol nem olvasható, írd: [?]. Csak az átiratot add vissza.")


class Mintavevo(threading.Thread):
    def __init__(self, every: float = 0.5):
        super().__init__(daemon=True)
        self.every, self.samples, self._allj = every, [], threading.Event()

    def run(self):
        while not self._allj.is_set():
            self.samples.append((time.time(), memoria.szabad_szazalek(), memoria.swap_mb()))
            self._allj.wait(self.every)

    def stop(self) -> dict:
        self._allj.set()
        self.join(timeout=5)
        lv = [s[1] for s in self.samples if s[1] >= 0]
        sw = [s[2] for s in self.samples if s[2] >= 0]
        return {"szabad_memoria_min_szazalek": min(lv) if lv else None,
                "szabad_memoria_median_szazalek": sorted(lv)[len(lv) // 2] if lv else None,
                "swap_novekedes_mb": round(max(sw) - sw[0], 1) if sw else None, "mintak": len(self.samples)}


def _uzenet(s: str) -> list[dict]:
    return [{"role": "user", "content": s}]


# ------------------------------------------------------------------ gyermekfolyamat

def gyermek(nev: str, par: dict, kep: str | None, max_tokens: int, keret: str | None, cache_gb: float | None,
            prefill: int | None, betolto=None, csucs=None) -> dict:
    """Egy modell mérése a betöltőn át. `betolto`/`csucs`: a tesztek álháttere."""
    from . import hatter as H
    from .betolto import Betolto
    cfg = config.load()
    b = B.betolt(cfg)
    m = b.modell(nev)
    keret_gb = b.keret_gb(keret)
    if betolto is None:
        betolto = Betolto(b, cache_gb=cache_gb, prefill_lepes=prefill)
    if csucs is None:
        csucs = (H.mlx_csucs_nullaz, H.mlx_csucs_gb, H.mlx_aktiv_gb)
    nullaz, csucs_gb, aktiv_gb = csucs
    out: dict = {"nev": nev, "repo": m.repo, "keret_gb": keret_gb, "cache_limit_gb": betolto.cache_gb,
                 "prefill_lepes": betolto.prefill_lepes or "alap"}
    nullaz()
    t0 = time.time()
    betolto.betolt(m, keret_gb)
    out["betoltes_s"] = round(time.time() - t0, 1)
    out["memoria_betoltes_utan_gb"] = round(aktiv_gb(), 2)
    t0 = time.time()
    r = betolto.general(m, _uzenet(KOTES_PROMPT.format(ablak=par["ablak_szoveg"], cim=par["jegyzet_cim"],
                                                       reszlet=par["jegyzet_reszlet"])), keret_gb, max_tokens=12)
    out["szoveg"] = {"mp": round(time.time() - t0, 1), "prompt_token": r.get("prompt_tokens"),
                     "prompt_tps": round(float(r.get("prompt_tps") or 0), 1), "valasz": r["text"].strip()[:80],
                     "vart": "igen" if par.get("y") == 1 else ("nem" if par.get("y") == 0 else "?")}
    out["csucs_szoveg_gb"] = round(csucs_gb(), 2)
    t0 = time.time()
    r2 = betolto.general(m, _uzenet("Foglald össze öt mondatban magyarul: " + par["jegyzet_reszlet"]), keret_gb,
                         max_tokens=max_tokens)
    out["generalas"] = {"mp": round(time.time() - t0, 1), "token": r2.get("generation_tokens"),
                        "gen_tps": round(float(r2.get("generation_tps") or 0), 1), "minta": r2["text"].strip()[:200]}
    if kep and "kep" in m.kepessegek:
        t0 = time.time()
        r3 = betolto.general(m, _uzenet(KEP_PROMPT), keret_gb, kepek=[kep], max_tokens=400)
        out["kep"] = {"mp": round(time.time() - t0, 1), "prompt_token": r3.get("prompt_tokens"),
                      "token": r3.get("generation_tokens"), "minta": r3["text"].strip()[:300]}
    out["csucs_memoria_gb"] = round(csucs_gb(), 2)
    betolto.urit()
    return out


# ------------------------------------------------------------------ szülő

def kep_elokeszit(cfg: config.Config, px: int = 1400, foto: Path | str | None = None) -> str | None:
    """A `foto` (egy kép, vagy egy mappa középső képe) a füzetlánc méretére kicsinyítve a `{tmp}` alá (a forrásban
    semmi nem változik). `foto` nélkül, vagy ha nincs benne kép: `None` (a képes lépés kimarad)."""
    if not foto:
        return None
    foto = Path(foto)
    fotok = sorted(p for p in foto.iterdir() if p.suffix.lower() in KEP_KITERJESZTES) if foto.is_dir() else (
        [foto] if foto.is_file() else [])
    if not fotok:
        return None
    from PIL import Image, ImageOps
    src = fotok[len(fotok) // 2]
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((px, px))
    tmp = cfg.path("tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    dst = tmp / f"bench-{src.stem}.jpg"
    im.save(dst, quality=90)
    return str(dst)


def minta_par(cfg: config.Config, i: int = 0, minta: Path | str | None = None,
              cimkek: Path | str | None = None) -> dict:
    """A kötés-ítélet minta-párja: a `minta` JSON-lista `i`-edik eleme (`ablak_szoveg`, `jegyzet_cim`,
    `jegyzet_reszlet`, opcionális `y`), a várt címke a `cimkek` JSON `{"cimkek": [...]}` listájából; `minta` nélkül
    a beépített `ALAP_PAR`."""
    if not minta:
        return dict(ALAP_PAR)
    par = dict(json.loads(Path(minta).read_text(encoding="utf-8"))[i])
    if cimkek:
        try:
            par["y"] = json.loads(Path(cimkek).read_text(encoding="utf-8"))["cimkek"][i]
        except (OSError, KeyError, IndexError, ValueError):
            pass
    return par


def render(r: dict) -> str:
    if "hiba" in r:
        return f"  {r['nev']}: HIBA — {r['hiba'][-300:]}"
    sz, g, k, s = r.get("szoveg", {}), r.get("generalas", {}), r.get("kep", {}), r["rendszer"]
    sorok = [f"  {r['nev']}: betöltés {r['betoltes_s']} s · csúcsmemória {r['csucs_memoria_gb']} GB "
             f"(szövegnél {r.get('csucs_szoveg_gb')} GB; cache-korlát {r.get('cache_limit_gb')}, "
             f"beolvasási lépés {r.get('prefill_lepes')}, kép {r.get('kep_px')} px)",
             f"    szöveg-ítélet: {sz.get('mp')} s ({sz.get('prompt_token')} token, {sz.get('prompt_tps')} tok/s) "
             f"→ „{sz.get('valasz')}” (várt: {sz.get('vart')})",
             f"    generálás: {g.get('gen_tps')} tok/s ({g.get('token')} token, {g.get('mp')} s)"]
    if k:
        sorok.append(f"    füzetfotó-átirat: {k.get('mp')} s ({k.get('token')} token) → „{k.get('minta', '')[:90]}…”")
    sorok.append(f"    rendszer: szabad memória min {s['szabad_memoria_min_szazalek']} % "
                 f"(medián {s['szabad_memoria_median_szazalek']} %), swap +{s['swap_novekedes_mb']} MB")
    return "\n".join(sorok)


def futtat(cfg: config.Config, nevek: list[str], max_tokens: int = 200, keret: str | None = None,
           cache_gb: float | None = None, prefill: int | None = None, px: int = 1400, log=print,
           minta: Path | str | None = None, cimkek: Path | str | None = None, foto: Path | str | None = None) -> Path:
    b = B.betolt(cfg)
    for n in nevek:
        b.modell(n)
    if kliens.unload_ha_fut(cfg):
        log("[bench] a futó modell-worker kiürítve (közös zár)")
    kep = kep_elokeszit(cfg, px, foto)
    par = minta_par(cfg, minta=minta, cimkek=cimkek)
    eredmenyek = []
    try:
        for n in nevek:
            log(f"[bench] {n}: {b.modellek[n].repo} …")
            elotte = {"szabad_memoria_szazalek": memoria.szabad_szazalek(), "swap_mb": memoria.swap_mb()}
            argv = [sys.executable, "-B", "-m", "core.modell.bench", "--gyermek", n, "--max-tokens", str(max_tokens)]
            argv += ["--kep", kep] if kep else []
            argv += ["--keret", keret] if keret else []
            argv += ["--cache-limit-gb", str(cache_gb)] if cache_gb is not None else []
            argv += ["--prefill-lepes", str(prefill)] if prefill is not None else []
            s = Mintavevo()
            s.start()
            t0 = time.time()
            p = subprocess.run(argv, input=json.dumps(par, ensure_ascii=False), capture_output=True, text=True,
                               env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                                    "HF_HOME": str(cfg.path("models")), "MOS_ROOT": str(cfg.root)})
            rec = {"nev": n, "ido_osszes_s": round(time.time() - t0, 1), "elotte": elotte, "rendszer": s.stop(),
                   "kep_px": px if kep else None}
            if p.returncode == 0:
                rec.update(json.loads(p.stdout.strip().splitlines()[-1]))
            else:
                rec["hiba"] = (p.stderr or p.stdout).strip()[-800:]
            eredmenyek.append(rec)
            log(render(rec))
    finally:
        if kep:
            Path(kep).unlink(missing_ok=True)          # a saját var/tmp fájlunk
    runs = cfg.path("runs")
    runs.mkdir(parents=True, exist_ok=True)
    out = runs / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(eredmenyek, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mos bench", description="Sebesség és csúcsmemória a jelölt modelleken.")
    ap.add_argument("nevek", nargs="*", help="modellnevek a config/os.toml [modellek] alól")
    ap.add_argument("--keret", help="munka | tavol | GB (alap: munka)")
    ap.add_argument("--cache-limit-gb", type=float, help="MLX-cache-korlát (alap: [modellgazda].cache_gb)")
    ap.add_argument("--prefill-lepes", type=int, help="beolvasási lépés; 0 = a könyvtár alapja")
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("--px", type=int, default=1400)
    ap.add_argument("--minta", help="a kötés-ítélet minta-párjai (JSON-lista; alap: a beépített semleges pár)")
    ap.add_argument("--cimkek", help="a minta-párok várt címkéi (JSON: {\"cimkek\": [0|1, …]})")
    ap.add_argument("--foto", help="kép vagy képmappa az átirat-méréshez (nélküle a képes lépés kimarad)")
    ap.add_argument("--gyermek", help=argparse.SUPPRESS)
    ap.add_argument("--kep", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.gyermek:
        res = gyermek(a.gyermek, json.loads(sys.stdin.read()), a.kep, a.max_tokens, a.keret, a.cache_limit_gb,
                      a.prefill_lepes)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if not a.nevek:
        ap.error("adj meg legalább egy modellt")
    try:
        out = futtat(config.load(), a.nevek, a.max_tokens, a.keret, a.cache_limit_gb, a.prefill_lepes, a.px,
                     minta=a.minta, cimkek=a.cimkek, foto=a.foto)
    except (B.RegiszterHiba, config.ConfigError, OSError, ValueError, IndexError, KeyError) as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 2
    print(f"Eredmény: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
