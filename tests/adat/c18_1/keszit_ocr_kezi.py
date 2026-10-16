"""A `qwen3_vl_4b-ocr_kezi.jsonl.gz` teszt-fixture szintetikus generátora (id, verzio, valasz, usage, mp).

A fixture egy **kézírásos OCR-futás alakját** adja az érvényességi kapunak (`tests/test_eval_ervenyesseg.py`): sok levágott
(`completion_tokens` = a 1500-as keret), köztük sor-hurkos és farok-ismétlődéses válasz, és néhány rendes, rövid. A szöveg
semleges, kitalált mondatokból áll; valódi füzetből, fotóból vagy jegyzetből semmi nincs benne. A kimenet determinisztikus
(rögzített mag, gzip-időbélyeg nélkül), így a teszt összeveti a lemezen álló fájllal.

    python3 tests/adat/c18_1/keszit_ocr_kezi.py              # (újra)írja a .jsonl.gz-t
    python3 tests/adat/c18_1/keszit_ocr_kezi.py --ellenoriz  # csak összeveti a lemezen állóval (0 = egyezik)
"""
from __future__ import annotations

import gzip
import io
import json
import random
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
KIMENET = ITT / "qwen3_vl_4b-ocr_kezi.jsonl.gz"

MAG = 20261003
VERZIO = "ocr_kezi-szintetikus-v1"
MAX_TOKENS = 1500                      # a mérés kerete: a levágott sor `completion_tokens`-e ennyi

# a halmaz összetétele (a teszt ezekre a számokra épít)
OSSZES = 97
SOR_HUROK = 32                         # egyetlen sor ismétlődik: több mint 20 sor, a leggyakoribb > 40%
FAROK_HUROK = 6                        # egy mondat ismétlődik a válasz végén (nincs sortörés)
HOSSZU = 40                            # levágott, de nem hurkos
RENDES = OSSZES - SOR_HUROK - FAROK_HUROK - HOSSZU
LEVAGOTT = SOR_HUROK + FAROK_HUROK + HOSSZU

_ALANY = ("The water in the lake", "A small group of students", "The old bridge", "Every sample in the first tray",
          "The morning train", "A careful reader", "The garden behind the library", "The second experiment",
          "Each page of the notebook", "The new schedule", "A thin layer of frost", "The workshop on Tuesday",
          "Our neighbour's radio", "The smaller of the two boxes", "A short list of rules", "The map on the wall")
_IGE = ("stays calm until noon", "arrives a few minutes late", "is repaired every spring", "shows a clear pattern",
        "is copied by hand twice", "needs a little more time", "keeps the room warm", "is easy to forget",
        "changes slowly over the week", "is measured again after lunch", "holds more than expected",
        "is compared with the earlier result", "depends on the weather", "ends with a short summary")
_VEG = ("in the first half of the month.", "when nobody is watching.", "before the lesson begins.",
        "unless the instructions say otherwise.", "after the third attempt.", "near the end of the row.",
        "for reasons that are written below.", "and the result is noted in the margin.", "while the others wait.",
        "as shown in the small table.", "during the quiet part of the day.", "without any special equipment.")
_ISMETLODO = ("Remember to check the total again.", "The value in the last row is not final.",
              "See the note above for the exact figure.", "This line is the same as the previous one.")


def _mondat(rng: random.Random) -> str:
    return f"{rng.choice(_ALANY)} {rng.choice(_IGE)} {rng.choice(_VEG)}"


def _sorok(rng: random.Random, n: int) -> list[str]:
    """`n` különböző, számozott sor (a számozás miatt egy sor sem ismétlődik)."""
    return [f"{i}. {_mondat(rng)}" for i in range(1, n + 1)]


def _rendes(rng: random.Random) -> tuple[str, int]:
    """Befejezett, rövid válasz: néhány sor, a keretnél jóval kevesebb tokennel."""
    szoveg = "\n".join(_mondat(rng) for _ in range(rng.randint(1, 8)))
    return szoveg, max(20, round(len(szoveg) / rng.uniform(2.3, 2.9)))


def _hosszu(rng: random.Random) -> str:
    """Levágott, de ismétlődés nélküli válasz: különböző sorok, a vége mondat közepén megszakad."""
    sorok, hossz = [], 0
    while hossz < 3600:
        s = f"{len(sorok) + 1}. {_mondat(rng)}"
        sorok.append(s)
        hossz += len(s) + 1
    szoveg = "\n".join(sorok)
    return szoveg[:len(szoveg) - rng.randint(5, 40)]


def _sorhurok(rng: random.Random) -> str:
    """Néhány rendes sor, majd ugyanaz a sor újra és újra a keret végéig."""
    sorok = _sorok(rng, rng.randint(8, 14))
    ismetlodo = rng.choice(_ISMETLODO)
    while sum(len(s) + 1 for s in sorok) < 3600:
        sorok.append(ismetlodo)
    szoveg = "\n".join(sorok)
    return szoveg[:len(szoveg) - rng.randint(0, 8)]


def _farokhurok(rng: random.Random) -> str:
    """Rendes bevezető bekezdés, majd egyetlen mondat ismétlődik sortörés nélkül (a sor-szabály ezt nem látja)."""
    bevezeto = " ".join(_mondat(rng) for _ in range(rng.randint(4, 8)))
    mondat = rng.choice(_ISMETLODO) + " "
    szoveg = bevezeto + " "
    while len(szoveg) < 3600:
        szoveg += mondat
    return szoveg[:len(szoveg) - rng.randint(1, len(mondat) - 1)]


def rekordok() -> list[dict]:
    rng = random.Random(MAG)
    fajtak = (["sorhurok"] * SOR_HUROK + ["farokhurok"] * FAROK_HUROK + ["hosszu"] * HOSSZU + ["rendes"] * RENDES)
    rng.shuffle(fajtak)
    ki = []
    for i, fajta in enumerate(fajtak, 1):
        if fajta == "rendes":
            valasz, tokenek = _rendes(rng)
        else:
            valasz = {"sorhurok": _sorhurok, "farokhurok": _farokhurok, "hosszu": _hosszu}[fajta](rng)
            tokenek = MAX_TOKENS
        tps = round(rng.uniform(24.0, 27.5), 2)
        ki.append({"id": f"scan-{i:03d}.jpg", "verzio": VERZIO, "valasz": valasz,
                   "usage": {"prompt_tokens": rng.randint(2700, 2900), "completion_tokens": tokenek, "generation_tps": tps},
                   "mp": round(rng.uniform(4.0, 18.0) + tokenek / tps, 2)})
    return ki


def tartalom() -> bytes:
    """A .jsonl.gz tömörítetlen tartalma (UTF-8, soronként egy rekord)."""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rekordok()).encode("utf-8")


def gzip_bajtok() -> bytes:
    puffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=puffer, mtime=0, compresslevel=9) as f:
        f.write(tartalom())
    return puffer.getvalue()


def main(argv: list[str]) -> int:
    if "--ellenoriz" in argv:
        if not KIMENET.is_file():
            print(f"hiányzik: {KIMENET}", file=sys.stderr)
            return 1
        with gzip.open(KIMENET, "rb") as f:
            egyezik = f.read() == tartalom()
        print("egyezik" if egyezik else "ELTÉR a generátor kimenetétől", file=sys.stderr)
        return 0 if egyezik else 1
    KIMENET.write_bytes(gzip_bajtok())
    print(f"{KIMENET.name}: {OSSZES} sor ({LEVAGOTT} levágott, ebből {SOR_HUROK} sor-hurok és {FAROK_HUROK} farok-hurok)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
