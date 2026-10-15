"""A kvízlánc vak ellenőrzésének mérése a `kviz` arany mért kimenetén (C22b; `docs/C22-TERV.md` 10.6: a kapuk utáni pontosság az
éles láncon).

    python -m modulok.kviz.meres --modell qwen35_9b [--keret tavol] --ki <jelentés.json>

A `mos eval <modell> kviz` rögzített válaszain (`{runs}/eval/<modell>/kviz.jsonl`; újragenerálás nincs) a pontozó kapui
(`modulok/eval/kviz/feladat.kerdes_kapu`: mechanikus, közös forráshűség-kapu, rossz válaszok, duplikátum) után a lánc **vak
ellenőrzése** fut a workeren át (ugyanaz a modell, a kulcs nélkül, más sorrendben, a darab szövegéből; `generalas._vak_ellenorzes`),
`auto` módban: a jelentés kérdésenként a pontozó és a vak ellenőrzés döntését adja, és összegzi, hányat ejt ki a vak
ellenőrzés a pontozón átment kérdésekből (élesben ezek nem kerülnek kvízbe). A kézi mintával (`docs/MERES-2026-10-07.md` 6.)
összevetve mutatja, a vak ellenőrzés a rossz kulcsot és a második helyes választ mennyire fogja. A vaultba nem ír.
Folytatható: a már mért tételek a jelentésből jönnek.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import time
from pathlib import Path

from core import config

from . import generalas as G


def _rekordok(cfg, modell: str):
    from core.modell import eval as E
    mod_ = E.feladat_modul(cfg, "kviz")
    _, tetelek, _ = E._feloldott(cfg, modell, "kviz", mod_, None, None, None)
    lny = {t["id"]: t for t in tetelek}
    rek = {}
    for sor in (cfg.path("runs") / "eval" / modell / "kviz.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(sor)
        if r["id"] in lny and r.get("beallitas") == lny[r["id"]]["beallitas"]:
            rek[r["id"]] = {**r, "vart": lny[r["id"]]["vart"]}
    return mod_, dict(sorted(rek.items()))


def mer_tetel(mod_, r: dict, ellenorzo) -> list[dict]:
    """Egy tétel jelöltjei: a pontozó döntése, és az átmentekre a vak ellenőrzésé."""
    jid = r["vart"]["jegyzet"]
    _, fs = mod_.forras(jid)
    d = mod_.darab(jid)
    jeloltek = G.szetszed(mod_.kimenet.tisztit(r.get("valasz") or ""))[:int(mod_.ARANY["kerdes_cel"]) + mod_.JELOLT_TUL]
    elfogadott, ki = [], []
    for i, j in enumerate(jeloltek, 1):
        kod, reszlet, _ = mod_.kerdes_kapu(fs, j, elfogadott)
        s = {"jegyzet": jid, "kerdes": i, "szoveg": j.kerdes, "pontozo": kod or "at"}
        if kod is None:
            elfogadott.append(j)
            vak = G._vak_ellenorzes(j, d, ellenorzo, collections.Counter())
            s["vak"] = vak[0] if vak else "at"
            if vak:
                s["vak_reszlet"] = vak[1]
        ki.append(s)
    return ki


def osszegez(sorok: list[dict]) -> dict:
    at = [s for s in sorok if s["pontozo"] == "at"]
    vak_at = [s for s in at if s.get("vak") == "at"]
    return {"jelolt": len(sorok), "pontozo_at": len(at), "vak_utan_at": len(vak_at),
            "vak_kiejtette": [f"{s['jegyzet']} Q{s['kerdes']}" for s in at if s.get("vak") != "at"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kviz-meres")
    ap.add_argument("--modell", required=True)
    ap.add_argument("--keret", default=None, help="munka | tavol (saját worker a keret-felülírással)")
    ap.add_argument("--ki", required=True)
    a = ap.parse_args(argv)
    cfg = config.load()
    from core.modell import beallitas as B
    from core.modell import eval as E
    from core.modell import kliens
    b = B.betolt(cfg)
    m = b.modell(a.modell)
    ki = Path(a.ki)
    adat = json.loads(ki.read_text(encoding="utf-8")) if ki.exists() else {}
    sorok = adat.get(a.modell, {}).get("sorok", [])
    kesz = {s["jegyzet"] for s in sorok}
    mod_, rek = _rekordok(cfg, a.modell)
    env = {"MANIFOLD_MODELL_KERET_GB": f"{b.keret_gb(a.keret):g}"} if a.keret else None
    folyamat = kliens.Folyamat(cfg, env=env, sajat=bool(a.keret))
    try:
        u = folyamat.biztosit(timeout=600)

        def ellenorzo(prompt: str, max_tokens: int) -> str:
            k = E.keres_beallitas(b, m, "kviz", {"tipus": "chat", "messages": [{"role": "user", "content": prompt}],
                                                 "max_tokens": max_tokens})
            uzenetek = k.pop("messages")
            k.pop("tipus", None)
            r = kliens.chat(u, uzenetek, feladat="kviz", modell=a.modell, mod="auto", **k)
            return r["choices"][0]["message"]["content"]

        for r in rek.values():
            if r["vart"]["jegyzet"] in kesz:
                continue
            t0 = time.time()
            uj = mer_tetel(mod_, r, ellenorzo)
            sorok += uj
            adat[a.modell] = {"sorok": sorok, "osszegzes": osszegez(sorok), "prompt_verzio": G.PROMPT_VERZIO}
            tmp = ki.with_name(ki.name + ".tmp")
            tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, ki)
            print(f"[kvíz-mérés] {a.modell} {r['vart']['jegyzet']}: {sum(s.get('vak') == 'at' for s in uj)}/"
                  f"{sum(s['pontozo'] == 'at' for s in uj)} a vak ellenőrzés után · {time.time() - t0:.0f} s", flush=True)
    finally:
        folyamat.leallit()
    print(json.dumps(adat.get(a.modell, {}).get("osszegzes"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
