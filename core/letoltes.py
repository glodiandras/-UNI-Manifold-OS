"""Modell-letöltő: a config/letoltes.toml jelöltjeit tölti le a {models} alá (HF_HOME).

A D3 szerint a letöltés egyszeri, jóváhagyott hálózati lépés: indulás előtt a név- és mérettel
ellátott lista megjelenik, és csak kifejezett igen után indul. Modellt nem tölt be és nem
konvertál: az a modellgazda (C05) dolga. Megszakítás után újraindítható; a kész fájlokat a
huggingface_hub nem tölti le újra.

Használat (a bin/mos-on át):
    mos letoltes                 # az első kör
    mos letoltes opcionalis      # az opcionális kör
    mos letoltes mind            # mindkettő
    mos letoltes glm_ocr parakeet_v3   # név szerint
    mos letoltes --lista         # csak a lista, letöltés nélkül
    mos letoltes --igen          # kérdés nélkül (a lista ekkor is kiíródik)
    mos letoltes mind --token    # bekéri a HF-tokent (nem látszik, nem kerül fájlba és előzménybe)

Gyorsítás: a Xet nagy teljesítményű módja (HF_XET_HIGH_PERFORMANCE=1) és 16 párhuzamos fájl alapból
bekapcsolva; a token a HF sebességkorlátját emeli. A token csak a folyamat memóriájában él.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import time
import tomllib
from pathlib import Path

from core import config
from core.modell import revizio

CSOPORTOK = ("elso", "opcionalis", "mind")
PARHUZAMOS_FAJL = 16


class LetoltesHiba(RuntimeError):
    pass


def jeloltek_betoltese(ut: Path) -> dict[str, dict]:
    try:
        with open(ut, "rb") as f:
            return tomllib.load(f).get("modell", {})
    except FileNotFoundError as exc:
        raise LetoltesHiba(f"a letöltési lista nem található: {ut}") from exc


def valasztas(modellek: dict[str, dict], kerdes: list[str]) -> list[str]:
    """A kért csoport(ok) vagy nevek → letöltendő nevek, sorrendtartóan; a meglévők kimaradnak."""
    kerdes = kerdes or ["elso"]
    nevek: list[str] = []
    for k in kerdes:
        if k in CSOPORTOK:
            korok = {"elso", "opcionalis"} if k == "mind" else {k}
            talalat = [n for n, m in modellek.items() if m.get("kor") in korok]
        elif k in modellek:
            talalat = [k]
        else:
            raise LetoltesHiba(f"ismeretlen modell vagy csoport: {k}")
        nevek += [n for n in talalat if n not in nevek]
    return [n for n in nevek if not modellek[n].get("megvan")]


def lista_szoveg(modellek: dict[str, dict], nevek: list[str]) -> str:
    sorok = [f"{'név':<26} {'repó':<58} {'GB':>6}"]
    for n in nevek:
        m = modellek[n]
        jel = "  (konvertálás kell)" if m.get("konvertalas") else ""
        sorok.append(f"{n:<26} {m['repo']:<58} {m['meret_gb']:>6.2f}{jel}")
    osszes = sum(modellek[n]["meret_gb"] for n in nevek)
    sorok.append(f"{'összesen':<85} {osszes:>6.2f} GB  ({len(nevek)} modell)")
    return "\n".join(sorok)


def letolt(modellek: dict[str, dict], nevek: list[str], cache_dir: Path, naplo: Path,
           letolto=None, token: str | None = None) -> dict[str, str]:
    """Modellenként letölt; egy hiba nem állítja meg a többit. Eredmény: név → 'kész' | hibaüzenet."""
    if letolto is None:
        from huggingface_hub import snapshot_download as letolto
    eredmeny: dict[str, str] = {}
    for i, n in enumerate(nevek, 1):
        m = modellek[n]
        print(f"\n[{i}/{len(nevek)}] {n} — {m['repo']} ({m['meret_gb']:.2f} GB)", flush=True)
        rev = m.get("revizio") or None
        try:
            # C19 (T141): a rögzített commit (`revizio`) töltődik, nem a pillanatnyi főág
            ut = letolto(repo_id=m["repo"], allow_patterns=m.get("minta"), cache_dir=str(cache_dir),
                         max_workers=PARHUZAMOS_FAJL, token=token, revision=rev)
            if rev and Path(str(ut)).name != rev:
                raise LetoltesHiba(f"a letöltött pillanatkép ({Path(str(ut)).name}) nem a rögzített revízió ({rev})")
            main = revizio.helyi_main(cache_dir.parent if cache_dir.name == "hub" else cache_dir, m["repo"])
            if rev and main and main != rev:
                print(f"  FIGYELEM: a helyi refs/main ({main[:12]}) eltér a rögzített revíziótól ({rev[:12]}); a betöltő a "
                      "rögzítettet tölti (doctor: main_elter)", flush=True)
            eredmeny[n] = "kész"
        except KeyboardInterrupt:
            eredmeny[n] = "megszakítva"
            _naplo_iras(naplo, modellek, eredmeny)
            raise
        except Exception as exc:  # hálózati, jogosultsági vagy tárhelyhiba: jelentjük, megyünk tovább
            eredmeny[n] = f"hiba: {exc}"
            print(f"  HIBA: {exc}", file=sys.stderr, flush=True)
        _naplo_iras(naplo, modellek, eredmeny)
    return eredmeny


def _naplo_iras(naplo: Path, modellek: dict[str, dict], eredmeny: dict[str, str]) -> None:
    naplo.parent.mkdir(parents=True, exist_ok=True)
    adat = {n: {"repo": modellek[n]["repo"], "meret_gb": modellek[n]["meret_gb"], "eredmeny": e}
            for n, e in eredmeny.items()}
    tmp = naplo.with_name(f".{naplo.name}.manifold-tmp")
    tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, naplo)


def main(argv: list[str] | None = None, bemenet=input, jelszokero=getpass.getpass) -> int:
    p = argparse.ArgumentParser(prog="mos letoltes", description="Modellek letöltése a config/letoltes.toml szerint.")
    p.add_argument("mit", nargs="*", help="elso | opcionalis | mind | modellnév … (alap: elso)")
    p.add_argument("--lista", action="store_true", help="csak kiírja a listát, nem tölt le")
    p.add_argument("--igen", action="store_true", help="nem kérdez rá (a lista ekkor is kiíródik)")
    p.add_argument("--token", action="store_true", help="bekéri a Hugging Face read-tokent (rejtett bevitel)")
    a = p.parse_args(argv)

    try:
        cfg = config.load()
        modellek = jeloltek_betoltese(Path(os.environ.get("MOS_LETOLTES") or cfg.root / "config" / "letoltes.toml"))
        nevek = valasztas(modellek, a.mit)
    except (config.ConfigError, LetoltesHiba) as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 2

    if not nevek:
        print("Nincs letöltendő modell (a kért tételek már megvannak).")
        return 0
    print(lista_szoveg(modellek, nevek))
    if a.lista:
        return 0

    models = cfg.path("models")
    cache_dir = models / "hub"
    cache_dir.mkdir(parents=True, exist_ok=True)
    szukseges = sum(modellek[n]["meret_gb"] for n in nevek) * 1e9
    szabad = shutil.disk_usage(cache_dir).free
    print(f"\nCél: {cache_dir}  (szabad: {szabad / 1e9:.1f} GB)")
    if szabad < szukseges * 1.05:
        print(f"HIBA: nincs elég hely ({szukseges / 1e9:.1f} GB kell).", file=sys.stderr)
        return 2

    if not a.igen:
        valasz = bemenet("Letöltöd? [i/N] ").strip().lower()
        if valasz not in ("i", "igen", "y", "yes"):
            print("Megszakítva, semmi nem töltődött le.")
            return 1

    token = None
    if a.token:
        token = jelszokero("HF-token (nem látszik; Enter = token nélkül): ").strip() or None
        if token and not token.startswith("hf_"):
            print("HIBA: ez nem HF-token (hf_ kezdetű kell).", file=sys.stderr)
            return 2
    # a Xet a modul betöltésekor olvassa a beállítást, ezért az import (a letolt-ben) előtt kell
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

    naplo = cfg.path("runs") / f"letoltes-{time.strftime('%Y%m%d-%H%M%S')}.json"
    try:
        eredmeny = letolt(modellek, nevek, cache_dir, naplo, token=token)
    except KeyboardInterrupt:
        print(f"\nMegszakítva. Újraindítva onnan folytatja, ahol abbahagyta. Napló: {naplo}")
        return 130
    hibak = {n: e for n, e in eredmeny.items() if e != "kész"}
    print(f"\nKész: {len(eredmeny) - len(hibak)}/{len(eredmeny)}. Napló: {naplo}")
    for n, e in hibak.items():
        print(f"  {n}: {e}", file=sys.stderr)
    konv = [n for n in nevek if modellek[n].get("konvertalas") and eredmeny.get(n) == "kész"]
    if konv:
        print("MLX-konvertálásra vár (a modellgazda végzi): " + ", ".join(konv))
    return 1 if hibak else 0


if __name__ == "__main__":
    sys.exit(main())
