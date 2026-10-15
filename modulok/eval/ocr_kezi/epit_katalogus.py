"""A füzet-bíró fagyasztott cél-katalógusa: `katalogus.json` a vault elméleti jegyzeteiből (csak olvasva).

    bin/mos exec <python> -B modulok/eval/ocr_kezi/epit_katalogus.py

Cél csak a tárgyi fejezetmappák `Elmélet/` alatti, számozott jegyzete (`NN - Cím.md`; L48, a legacy
`jegyzet_szabaly`). A jegyzet `## Füzet` szakasza kimarad: a régi kötések nem befolyásolhatják a bírót.
A katalógus az aranyhalmaz része: ha újraépül, az `ocr_kezi` és a `fuzet_fejezet` verziója is lép.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kozos import tavolsag  # noqa: E402

TANTARGYAK = {"M": "Matematika", "F": "Fizika", "T": "Történelem", "I": "Irodalom", "N": "Magyar nyelvtan",
              "D": "Digitális kultúra", "E": "Angol nyelv"}
_MAPPA = re.compile(r"^([A-Z])(\d{2}) - (.+)$")
_NEV = re.compile(r"^(\d+) - (.+)\.md$")
SZAVAK_MAX = 160
TO_HOSSZ = 6


def tokenek(szoveg: str) -> list[str]:
    """A bíró szavai: hajtott, legfeljebb 6 betűs szóelők (a ragozott alakok összevonva), 3 betűtől."""
    return [w[:TO_HOSSZ] for w in (tavolsag.hajt(x) for x in tavolsag.szavak(szoveg)) if len(w) >= 3 and not w.isdigit()]


def _torzs(szoveg: str) -> str:
    """A jegyzet törzse frontmatter és `## Füzet` szakasz nélkül, a beágyazások és linkcélok nélkül."""
    if szoveg.startswith("---"):
        vege = szoveg.find("\n---", 3)
        szoveg = szoveg[vege + 4:] if vege > 0 else szoveg
    szoveg = re.split(r"\n## Füzet\s*\n", szoveg)[0]
    szoveg = re.sub(r"!\[\[[^\]]*\]\]", " ", szoveg)
    szoveg = re.sub(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), szoveg)
    return szoveg


def epit(vault: Path) -> dict:
    fejezetek, jegyzetek = [], []
    for top in sorted(p for p in vault.iterdir() if p.is_dir()):
        nev = unicodedata.normalize("NFC", top.name)
        m = _MAPPA.match(nev)
        if not m or m.group(2) == "00" or m.group(1) not in TANTARGYAK:
            continue
        elmelet = top / "Elmélet"
        if not elmelet.is_dir():
            elmelet = next((d for d in top.iterdir() if unicodedata.normalize("NFC", d.name) == "Elmélet"), None)
            if elmelet is None:
                continue
        sajat = []
        for f in elmelet.iterdir():
            fn = unicodedata.normalize("NFC", f.name)
            n = _NEV.match(fn)
            if not n or not f.is_file():
                continue
            torzs = _torzs(f.read_text(encoding="utf-8"))
            cimsorok = list(dict.fromkeys(x.strip() for x in re.findall(r"^#{1,3}\s+(.+)$", torzs, re.M)))
            szavak = Counter(tokenek(torzs))
            sajat.append((int(n.group(1)), {
                "ut": f"{nev}/Elmélet/{fn}", "cim": n.group(2), "cimsorok": cimsorok[:24],
                "szavak": dict(szavak.most_common(SZAVAK_MAX))}))
        if sajat:
            fejezetek.append({"kod": nev[:3], "nev": m.group(3), "targy": TANTARGYAK[m.group(1)]})
            jegyzetek += [j for _, j in sorted(sajat, key=lambda t: (t[0], t[1]["ut"]))]
    return {"fejezetek": fejezetek, "jegyzetek": jegyzetek}


def main() -> int:
    from core import config
    cfg = config.load()
    kat = epit(cfg.path("vault"))
    ki = Path(__file__).resolve().parent / "katalogus.json"
    ki.write_text(json.dumps(kat, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(kat['fejezetek'])} fejezet, {len(kat['jegyzetek'])} jegyzet → {ki.name} ({ki.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
