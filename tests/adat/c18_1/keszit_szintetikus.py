"""A `glm_ocr-ocr_keplet.jsonl.gz` és a `phi4_mini_reasoning-matek_ellenorzo.jsonl.gz` teszt-fixture szintetikus generátora.

Az érvényességi kapu (`tests/test_eval_ervenyesseg.py`) két futás **alakját** várja: egy levágás-mentes képlet-OCR futást (164 rövid,
egysoros LaTeX-válasz) és egy gondolkodásban levágott futást (20 válasz, mind a `<think>` blokkban szakad meg a 1200-as kereten).
A tartalom kitalált, általános képletekből és mondatokból áll (valódi füzetből, fotóból vagy jegyzetből, valódi modell-futásból semmi
nincs benne). A kimenet determinisztikus (rögzített mag, gzip-időbélyeg nélkül), így a teszt összeveti a lemezen állóval.

    python3 tests/adat/c18_1/keszit_szintetikus.py              # (újra)írja a két .jsonl.gz-t
    python3 tests/adat/c18_1/keszit_szintetikus.py --ellenoriz  # csak összeveti a lemezen állókkal (0 = egyezik)
"""
from __future__ import annotations

import gzip
import io
import json
import random
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
KEPLET_FAJL = ITT / "glm_ocr-ocr_keplet.jsonl.gz"
GONDOLKODO_FAJL = ITT / "phi4_mini_reasoning-matek_ellenorzo.jsonl.gz"

MAG = 20261004
KEPLET_VERZIO = "ocr_keplet-szintetikus-v1"
GONDOLKODO_VERZIO = "matek_ellenorzo-szintetikus-v1"
KEPLET_DB = 164
GONDOLKODO_DB = 20
GONDOLKODO_KERET = 1200                # a mérés kerete: a levágott sor `completion_tokens`-e ennyi

_GOROG = ("\\alpha", "\\beta", "\\gamma", "\\theta", "\\varphi", "\\omega")
_SABLON = (
    "$${a}^2 + {b}^2 = {c}^2$$",
    "$$\\frac{{{a}}}{{{b}}} + \\frac{{{c}}}{{{d}}} = \\frac{{{a} \\cdot {d} + {c} \\cdot {b}}}{{{b} \\cdot {d}}}$$",
    "$$\\sin {g} \\cdot \\sin {g} = \\sin^2 {g}$$",
    "$$\\sqrt{{{a}}} \\cdot \\sqrt{{{b}}} = \\sqrt{{{a} \\cdot {b}}}$$",
    "$$x_{{1,2}} = \\frac{{-{a} \\pm \\sqrt{{{a}^2 - 4 \\cdot {b} \\cdot {c}}}}}{{2 \\cdot {b}}}$$",
    "$$\\log_{{{b}}} {a} + \\log_{{{b}}} {c} = \\log_{{{b}}} ({a} \\cdot {c})$$",
    "$$\\sum_{{k=1}}^{{{a}}} k = \\frac{{{a} ({a} + 1)}}{{2}}$$",
    "$$\\cos {g}^2 = \\cos ({g} \\cdot {g})$$",
    "$$v = \\frac{{s}}{{t}} = \\frac{{{a}}}{{{b}}}$$",
    "$$F = m \\cdot a = {a} \\cdot {b}$$",
    "$$\\int_{{0}}^{{{a}}} {b} x \\, dx = \\frac{{{b} \\cdot {a}^2}}{{2}}$$",
    "$$({a} + {b})^2 = {a}^2 + 2 \\cdot {a} \\cdot {b} + {b}^2$$",
)
_ELEJE = ("Let me work through this step by step.", "First I want to restate the problem in my own words.",
          "Okay, so the task is to check a short derivation line by line.", "I will start by reading the given steps carefully.")
_LEPES = ("Next, I substitute {a} for the first quantity and {b} for the second one.",
          "That gives {c} on the left side, and I compare it with {d} on the right side.",
          "Wait, I should double-check the sign in the third step before moving on.",
          "If I expand the bracket, the middle term becomes {a} times {b}, which is {e}.",
          "Hmm, the second line does not follow from the first one unless {c} equals {d}.",
          "Let me try the other order: first simplify the fraction, then collect the terms.",
          "Then I check the units: both sides are plain numbers, so nothing is lost there.",
          "So far the derivation looks consistent, but I have not verified the last step yet.",
          "I can also test the claim with a small example, say {a} and {b}, and see what happens.",
          "Now the factor {c} appears twice, so I should be careful not to count it as a new term.")


def _kepletek(rng: random.Random) -> list[dict]:
    ki = []
    for i in range(1, KEPLET_DB + 1):
        k = {"a": rng.randint(2, 19), "b": rng.randint(2, 19), "c": rng.randint(2, 19), "d": rng.randint(2, 19), "g": rng.choice(_GOROG)}
        valasz = rng.choice(_SABLON).format(**k)
        tokenek = max(8, round(len(valasz) / rng.uniform(2.2, 2.8)))
        tps = round(rng.uniform(170.0, 190.0), 2)
        ki.append({"id": f"formula-{i:03d}.png", "verzio": KEPLET_VERZIO, "valasz": valasz,
                   "usage": {"prompt_tokens": rng.randint(340, 370), "completion_tokens": tokenek, "generation_tps": tps},
                   "mp": round(rng.uniform(0.8, 1.4), 2)})
    return ki


def _gondolkodasok(rng: random.Random) -> list[dict]:
    ki = []
    for i in range(1, GONDOLKODO_DB + 1):
        reszek = ["<think>\n" + rng.choice(_ELEJE)]
        hossz = 0
        while hossz < 3600:                         # a keretnek megfelelő hossz; a vége mondat közepén megszakad, `</think>` nincs
            k = {x: rng.randint(2, 99) for x in "abcde"}
            s = rng.choice(_LEPES).format(**k)
            reszek.append(s)
            hossz += len(s) + 1
        szoveg = "\n\n".join(reszek[:1]) + "\n\n" + " ".join(reszek[1:])
        szoveg = szoveg[:len(szoveg) - rng.randint(4, 30)]
        tps = round(rng.uniform(95.0, 110.0), 2)
        ki.append({"id": f"{'jo' if i % 2 else 'hibas'}-{i:02d}", "verzio": GONDOLKODO_VERZIO, "valasz": szoveg,
                   "usage": {"prompt_tokens": rng.randint(380, 520), "completion_tokens": GONDOLKODO_KERET, "generation_tps": tps},
                   "mp": round(rng.uniform(1.0, 3.0) + GONDOLKODO_KERET / tps, 2)})
    return ki


def rekordok() -> tuple[list[dict], list[dict]]:
    """(képlet-OCR futás, gondolkodásban levágott futás)."""
    rng = random.Random(MAG)
    return _kepletek(rng), _gondolkodasok(rng)


def tartalom(rek: list[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rek).encode("utf-8")


def gzip_bajtok(rek: list[dict]) -> bytes:
    puffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=puffer, mtime=0, compresslevel=9) as f:
        f.write(tartalom(rek))
    return puffer.getvalue()


def main(argv: list[str]) -> int:
    kepletek, gondolkodasok = rekordok()
    parok = ((KEPLET_FAJL, kepletek), (GONDOLKODO_FAJL, gondolkodasok))
    if "--ellenoriz" in argv:
        rossz = 0
        for fajl, rek in parok:
            if not fajl.is_file():
                print(f"hiányzik: {fajl}", file=sys.stderr)
                rossz += 1
                continue
            with gzip.open(fajl, "rb") as f:
                if f.read() != tartalom(rek):
                    print(f"ELTÉR a generátor kimenetétől: {fajl.name}", file=sys.stderr)
                    rossz += 1
        return 1 if rossz else 0
    for fajl, rek in parok:
        fajl.write_bytes(gzip_bajtok(rek))
        print(f"{fajl.name}: {len(rek)} sor", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
