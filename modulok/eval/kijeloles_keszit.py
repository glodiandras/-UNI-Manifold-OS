"""A `kifejtes` és az `osszefoglal_kijeloles` aranyhalmazának fagyasztója (J4).

    bin/mos exec var/venv/bin/python -B modulok/eval/kijeloles_keszit.py              # a kijelölések fagyasztása (újraírás)
    bin/mos exec var/venv/bin/python -B modulok/eval/kijeloles_keszit.py --ellenoriz  # csak összeveti a vault mai szövegével

A tételek kézzel választott kijelölések a felhasználó saját jegyzeteiből (`ut`, a jegyzet vault-relatív útja): a kijelölés a
`kezd` szöveg első előfordulásától a `veg` szöveg első, utána álló előfordulásának végéig tart (a jegyzet nyers szövegében,
Markdownnal együtt — ahogy a szerkesztő kijelöli). A fagyasztó kitölti a `kijeloles`, az `elotte` (a kijelölés előtti nyers szöveg
utolsó 1500 karaktere: az éles kérés is ennyit lát), a `jegyzet_sha256` és — a kifejtésnél — a `szamok` (a jegyzet összes
száma: az ellentmondás-kapu ezeket engedi) mezőt.

A vaultot **csak olvassa** (`MOS_VAULT`); a `var/`-hoz és a vaulthoz nem ír, modellt nem hív. Fagyasztás után a halmaz a
jegyzet későbbi változásától független (a mérés nem csúszhat el csendben); az `--ellenoriz` jelzi, ha a jegyzet azóta változott.
Az `allapot` (`vazlat` → `jovahagyott`) kézi lépés a felhasználó jóváhagyása után (K430); a fagyasztó tartalmi változásnál
`vazlat`-ra állítja.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parent.parent
for _p in (str(REPO), str(ITT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kozos import kijeloles as K  # noqa: E402
from modulok.kapuk import tokenek as KT  # noqa: E402

FELADATOK = ("kifejtes", "osszefoglal_kijeloles")
FAGYASZTOTT = ("kijeloles", "elotte", "jegyzet_sha256", "szamok")


def kivag(szoveg: str, kezd: str, veg: str) -> tuple[str, str]:
    """(kijelölés, előtte): a `kezd` első előfordulásától a `veg` utána álló első előfordulásának végéig."""
    i = szoveg.find(kezd)
    if i < 0:
        raise ValueError(f"nincs a jegyzetben: {kezd[:60]!r}")
    j = szoveg.find(veg, i)
    if j < 0:
        raise ValueError(f"nincs a kezdet után: {veg[:60]!r}")
    return szoveg[i:j + len(veg)], szoveg[:i][-K.ELOTTE_MAX:]


def fagyaszt_tetel(vault: Path, t: dict, kifejtes: bool) -> dict:
    nyers = (vault / t["ut"]).read_bytes()
    szoveg = nyers.decode("utf-8")
    kij, elotte = kivag(szoveg, t["kezd"], t["veg"])
    ki = {**t, "kijeloles": kij, "elotte": elotte, "jegyzet_sha256": hashlib.sha256(nyers).hexdigest()}
    if kifejtes:
        ki["szamok"] = sorted(KT.szamok(szoveg), key=lambda x: (len(x), x))
    else:
        ki.pop("szamok", None)
    return ki


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ellenoriz", action="store_true", help="csak összeveti; nem ír")
    a = ap.parse_args(argv)
    from core import config
    vault = config.load().path("vault")
    hiba = 0
    for f in FELADATOK:
        ut = ITT / f / "arany.json"
        arany = K.betolt(ut.parent)
        uj = [fagyaszt_tetel(vault, t, f == "kifejtes") for t in arany["tetel"]]
        valtozott = [t["id"] for t, r in zip(uj, arany["tetel"]) if any(t.get(k) != r.get(k) for k in FAGYASZTOTT)]
        if a.ellenoriz:
            for i in valtozott:
                print(f"{f}/{i}: a jegyzet vagy a kijelölés a fagyasztás óta változott")
            hiba += len(valtozott)
            continue
        if valtozott:
            arany = {**arany, "allapot": "vazlat", "jovahagyva": None, "tetel": uj}
            ut.write_text(K.json_ki(arany), encoding="utf-8")
        print(f"{f}: {len(uj)} tétel, ebből újrafagyasztva {len(valtozott)}")
    return 1 if hiba else 0


if __name__ == "__main__":
    sys.exit(main())
