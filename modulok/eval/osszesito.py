"""Az eval-értékelések összesítője (C18.1): modell × feladat érvényessége egy kimeneti mappában.

    bin/mos exec var/venv/bin/python -B modulok/eval/osszesito.py "{tmp}/eval-proba"

A `<mappa>/<modell>/<feladat>-ertekeles.json` fájlokat olvassa (a `mos eval` írja), és soronként kiírja a
levágott / hurkos / üres / hibás / formátumhibás tételek arányát, az érvényességet, a pontszámot, az átlagos
mp/tételt, a legnagyobb `completion_tokens`-t a kerethez mérve, és (C29.8, T045) a mért csúcsmemóriát a regiszterbelihez
(`3.5/2.7 !`: a mért érték a regiszterbelit 0,2 GB-nál jobban meghaladja). A C18.1 előtti (kapu nélküli) értékelés
„régi”. A regiszter szerint a mérésből kihagyott sor (a modell `meres_kihagy`-a, a feladat `meres_kihagy` bejegyzése,
vagy a feladat már nincs a modell mért feladatai között; 2026-10-07, a K28 piros sorai) „kihagyva” állapotú: látszik,
de a kapuba nem számít — a regiszterben nem szereplő modell sora nem kihagyott. Kilépési kód: 0, ha van értékelés, és
minden nem kihagyott sor érvényes (zöld kapu); különben 1. Csak olvas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent


def ertekelesek(mappa: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(mappa).glob("*/*-ertekeles.json"))]


def kihagyottak(cfg) -> dict[tuple[str, str], str]:
    """(modell, feladat) → ok a regiszter minden modelljére és ismert feladatára, amelyet a mérési lista nem mér
    (a `parancslista.feladatai` és a modell `meres_kihagy`-a szerint). A regiszteren kívüli modell nincs benne."""
    import importlib.util
    from core.modell import beallitas as B
    spec = importlib.util.spec_from_file_location("mos_parancslista", ITT / "parancslista.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    ki: dict[tuple[str, str], str] = {}
    for m in B.betolt(cfg).modellek.values():
        mert = set(p.feladatai(m))
        kihagy = dict(m.meres_kihagy_feladat)
        for f in p.SORREND:
            if m.meres_kihagy:
                ki[(m.nev, f)] = f"a modell kihagyva a mérésből: {m.meres_kihagy}"
            elif f in kihagy:
                ki[(m.nev, f)] = f"a feladat kihagyva a mérésből: {kihagy[f]}"
            elif f not in mert:
                ki[(m.nev, f)] = "a feladat nincs a modell mért feladatai között (regiszter)"
    return ki


def kihagyott_sor(ert: dict, ok: str) -> dict:
    return {"modell": ert["modell"], "feladat": ert["feladat"], "allapot": "kihagyva", "ervenyes": None,
            "kihagyva": ok, "pontszam": ert.get("pontszam"), "n": ert.get("n")}


def _arany(e: dict, k: str) -> str:
    if e.get(k) is None:
        return "–"
    return f"{e[k]}/{e['n']}"


def _csucs(futas: dict) -> str:
    mert, reg = futas.get("csucs_gb_max"), futas.get("regiszter_csucs_gb")
    if mert is None:
        return "–"
    if reg is None:
        return f"{mert:g}"
    return f"{mert:g}/{reg:g}" + (" !" if mert > reg + 0.2 else "")


def sor(ert: dict) -> dict:
    e = ert.get("ervenyesseg")
    if not e:
        return {"modell": ert["modell"], "feladat": ert["feladat"], "allapot": "régi (kapu nélkül)", "ervenyes": False,
                "pontszam": ert.get("pontszam"), "n": ert.get("n")}
    keret = max((b.get("max_tokens") or 0 for b in ert.get("keres_beallitas") or []), default=0)
    futas = ert.get("futas") or {}
    return {"modell": ert["modell"], "feladat": ert["feladat"], "ervenyes": bool(ert.get("ervenyes")),
            "allapot": "érvényes" if ert.get("ervenyes") else "ÉRVÉNYTELEN", "pontszam": ert.get("pontszam"),
            "n": e["n"], "hianyzo": e.get("hianyzo", 0), "levagott": _arany(e, "levagott"), "hurok": _arany(e, "hurok"),
            "ures": _arany(e, "ures"), "hiba": _arany(e, "hiba"), "formatum_hiba": _arany(e, "formatum_hiba"),
            "rossz": f"{e['rossz_arany']:.0%}", "mp": futas.get("mp_atlag"),
            "tokenek": f"{futas.get('completion_tokens_max', 0)}/{keret}" if keret else "–", "csucs": _csucs(futas)}


def tabla(sorok: list[dict]) -> str:
    fej = ("modell", "feladat", "allapot", "n", "levagott", "hurok", "ures", "hiba", "formatum_hiba", "rossz",
           "pontszam", "mp", "tokenek", "csucs")
    ki = ["| " + " | ".join(fej) + " |", "|" + "---|" * len(fej)]
    for s in sorok:
        ki.append("| " + " | ".join("" if s.get(k) is None else str(s.get(k)) for k in fej) + " |")
    return "\n".join(ki)


def main(argv: list[str] | None = None, cfg=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("használat: osszesito.py <mappa>   (pl. \"{tmp}/eval-proba\")", file=sys.stderr)
        return 2
    if cfg is None:
        from core import config
        cfg = config.load()
    mappa = cfg.expand(argv[0]) if "{" in argv[0] else argv[0]
    kihagy = kihagyottak(cfg)
    sorok = [kihagyott_sor(e, kihagy[(e["modell"], e["feladat"])]) if (e["modell"], e["feladat"]) in kihagy else sor(e)
             for e in ertekelesek(Path(mappa))]
    mert = [s for s in sorok if s["allapot"] != "kihagyva"]
    if not mert:
        print(f"nincs értékelés: {mappa}")
        return 1
    print(tabla(sorok))
    rossz = [s for s in mert if not s["ervenyes"]]
    ki = [s for s in sorok if s["allapot"] == "kihagyva"]
    if ki:
        print("\nKihagyva (a regiszter szerint nem mért; a kapuba nem számít):")
        for s in ki:
            print(f"- {s['modell']} · {s['feladat']}: {s['kihagyva'][:160]}")
    print(f"\n{len(mert) - len(rossz)}/{len(mert)} érvényes"
          + (f" ({len(ki)} kihagyott sor nélkül)" if ki else "") + ". "
          + ("A kapu zöld: indulhat a következő lépés." if not rossz else
             "A kapu PIROS: " + ", ".join(f"{s['modell']} · {s['feladat']}" for s in rossz)))
    return 0 if not rossz else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main())
