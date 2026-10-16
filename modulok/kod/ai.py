"""F10: the text core of the five AI modes with a language parameter — the prompt and the answer parsing, in one place (the
live path `ai_futas.py` and a future measurement of a `kod_<language>` gold set use the same functions: D9, the calibration
is for the measured prompt).

C++ keeps the measured C36b prompt and parsers byte for byte (`modulok/cpp/ai.py`, router task `kod`). Every other language
has its own router task (`Profil.kalibracios_kulcs`, e.g. `kod_python`) and the English prompts below, which name the
language (`Profil.ai_nyelv`) and its code fence (`Profil.kerites`). The modes and answer shapes are the C36b ones:

| Mode | Asks the model for | The parsed answer |
|---|---|---|
| `hiba` | where and what the bug is, from the compiler / failing-test evidence | `{sor, fajta, magyarazat}` (last line `ERROR: <line> <kind>`) |
| `tipp` | a three-step hint without code: direction → algorithm → location | `{szintek, sorrend_ok, hely_sor, kod_szintek}` |
| `megoldas` | the fixed full program (only after a separate confirmation) | `{kod, magyarazat}` |
| `teszt` | 3–5 edge inputs + a slow, obviously correct reference | `{bemenetek, referencia}` |
| `stressz` | a random input generator (seed = 1st argument) + a slow reference | `{generator, referencia}` |

The model's output is only text here: nothing runs in this module (the sandbox is `futtato.py`).
"""
from __future__ import annotations

import re

from core import kod_nyelvek as KN
from modulok.cpp import ai as CA

PROMPT_VERZIO = "kod-nyelv-p1"
MODOK = KN.AI_MODOK
MAX_TOKENS = dict(CA.MAX_TOKENS)
FAJTAK = {
    "index": "off-by-one index or bound (< vs <=, wrong first or last index)",
    "tulcsordulas": "integer overflow or precision loss (wrong numeric type, missing modulo)",
    "inicializalas": "wrong initial value (e.g. the maximum starts at 0, a counter is not reset)",
    "alapeset": "wrong base case in recursion or dynamic programming",
    "ido": "correct but too slow algorithm (time limit)",
    "feltetel": "wrong condition or comparison (> vs >=, and vs or)",
    "sorrend": "wrong order: update before use, wrong traversal direction, wrong output order",
    "egyeb": "something else",
}
_FAJTA_LISTA = "\n".join(f"- {k}: {v}" for k, v in FAJTAK.items())
BEMENET_MAX_KAR = CA.BEMENET_MAX_KAR
TESZT_BEMENET_MAX = CA.TESZT_BEMENET_MAX
TESZT_BEMENET_MAX_KAR = CA.TESZT_BEMENET_MAX_KAR

_IO = "It reads standard input and writes standard output."

_HIBA = """A student's {nyelv} solution is wrong. Find the bug.

TASK:
{leiras}

THE STUDENT'S CODE (numbered):
{kod}

WHAT WE SEE:
{bizonyitek}

Explain in 2-4 sentences what the bug is and why it causes the symptom above. Do not write the fixed program and do not write
a code block. The last line of your answer must have exactly this form:
ERROR: <line number> <kind>
where <line number> is the number of the faulty line in the numbering above, and <kind> is one of:
{fajtak}"""

_TIPP = """A student's {nyelv} solution is wrong. Help them find the fix themselves.

TASK:
{leiras}

THE STUDENT'S CODE (numbered):
{kod}

WHAT WE SEE:
{bizonyitek}

Give a three-step hint. Do not write the solution, do not write code or a code block, and do not quote a line of code.
Answer in exactly this form, in three lines:
1. DIRECTION: <one or two sentences: where to look for the bug>
2. ALGORITHM: <one or two sentences: what the correct reasoning is>
3. LOCATION: <one sentence: which line has the problem (with its number, e.g. "line 12"), and what is wrong with it>"""

_MEGOLDAS = """A student's {nyelv} solution is wrong. Fix it.

TASK:
{leiras}

THE STUDENT'S CODE (numbered):
{kod}

WHAT WE SEE:
{bizonyitek}

Fix the program with the smallest possible change. First describe in one or two sentences what you fixed, then give the
complete fixed program in a single ```{kerites} code block. """ + _IO

_TESZT = """We are looking for edge test cases for a {nyelv} task.

TASK:
{leiras}

THE STUDENT'S CODE (numbered):
{kod}

Write 3-5 edge test cases that can expose common bugs (bounds, smallest and largest values, repetition, a single element,
negative numbers, overflow). Put every input in its own ```input code block, exactly in the input format of the task, small
(at most 30 lines). Do NOT write the expected output.
Then write a simple, slow but obviously correct {nyelv} reference solution (brute force) in a single ```{kerites} code block.
""" + _IO + " Do not write an explanation."

_STRESSZ = """We are building a stress test for a {nyelv} task: on random inputs we compare the student's solution with a slow
but surely correct one.

TASK:
{leiras}

THE STUDENT'S CODE (numbered):
{kod}

Write two {nyelv} programs, each in its own ```{kerites} code block, in this order:
1. GENERATOR: the first command-line argument is an integer seed; from it, with a seeded pseudo-random generator, it writes
   ONE small random input that matches the input format of the task exactly to standard output. Keep the sizes small (the
   slow solution must stay fast) and make edge values frequent. It must not use files or the network.
2. REFERENCE: a simple, slow but obviously correct solution (brute force). """ + _IO + """
Do not write an explanation."""

_SABLON = {"hiba": _HIBA, "tipp": _TIPP, "megoldas": _MEGOLDAS, "teszt": _TESZT, "stressz": _STRESSZ}


def _rovid(s: str | None, n: int = BEMENET_MAX_KAR) -> str:
    s = (s or "").rstrip("\n")
    return s if len(s) <= n else s[:n] + f"\n… (cut, {len(s)} characters in total)"


def bizonyitek_szoveg(b: dict | None) -> str:
    """The evidence (`fajta`: `fordito` | `teszt` | `futas` | `ido` | `nincs`) as prompt text (English)."""
    if not b:
        return "No further information."
    f = b.get("fajta")
    if f == "fordito":
        sorok = [f"- line {d.get('sor') or '?'}: {d.get('uzenet', '')}" for d in (b.get("diagnosztika") or [])[:6]]
        return "The program does not compile. The compiler's errors:\n" + ("\n".join(sorok) or "- (no details)")
    if f in ("teszt", "szanitizer"):
        r = [f"On a test the program gives a wrong result ({b.get('allapot_szoveg') or b.get('allapot') or 'wrong output'})."]
        r.append("Input:\n" + _rovid(b.get("bemenet")))
        if b.get("vart") is not None:
            r.append("Expected output:\n" + _rovid(b.get("vart")))
        if b.get("kapott") is not None:
            r.append("The program's output:\n" + (_rovid(b.get("kapott")) or "(empty)"))
        if b.get("jelentes"):
            j = b["jelentes"]
            r.append(f"The runtime error: {j.get('leiras', '')}" + (f" (at line {j['sor']})" if j.get("sor") else ""))
        return "\n".join(r)
    return b.get("leiras") or "No further information."


def prompt(p: KN.Profil, mod: str, leiras: str, kod: str, bizonyitek: dict | None = None) -> str:
    if mod not in _SABLON:
        raise ValueError(f"unknown mode: {mod!r} ({', '.join(MODOK)})")
    if p.azonosito == "cpp":
        return CA.prompt(mod, leiras, kod, bizonyitek)            # the measured C36b prompt, unchanged
    return _SABLON[mod].format(nyelv=p.ai_nyelv or p.nev, kerites=p.kerites[0] if p.kerites else "", leiras=leiras.strip(),
                               kod=CA.szamozott(kod), bizonyitek=bizonyitek_szoveg(bizonyitek), fajtak=_FAJTA_LISTA)


def keres(p: KN.Profil, mod: str, leiras: str, kod: str, bizonyitek: dict | None = None) -> dict:
    """The worker chat request (without the task, mode and budget: the caller adds them). Deterministic (L27)."""
    if p.azonosito == "cpp":
        return CA.keres(mod, leiras, kod, bizonyitek)
    return {"messages": [{"role": "user", "content": prompt(p, mod, leiras, kod, bizonyitek)}], "max_tokens": MAX_TOKENS[mod]}


# --------------------------------------------------------------------------- the answer

_HIBA_SOR = re.compile(r"(?:ERROR|HIBA)\s*:\s*(?:line\s+)?(\d{1,5})\.?\s*[\s,;:-]*([A-Za-z_]+)?", re.I)
_SZINT = re.compile(r"(?mi)^\s*(?:\*\*)?\s*([1-3])\s*[.)]\s*(?:\*\*)?\s*(DIRECTION|ALGORITHM|LOCATION|IRÁNY|IRANY|ALGORITMUS|HELY)"
                    r"\s*(?:\*\*)?\s*:\s*(?:\*\*)?")
_NEM_KOD = ("bemenet", "input", "text", "txt", "plaintext", "output", "kimenet")


def nyelv_blokkok(p: KN.Profil, szoveg: str) -> list[tuple[str, str]]:
    """The code blocks of the profile's language (by fence tag; an untagged block counts unless it looks like an input)."""
    ki = []
    for info, tart in CA.kodblokkok(szoveg):
        nyelv = info.split()[0] if info else ""
        if nyelv in p.kerites or (not nyelv and len(tart.strip().splitlines()) > 1 and re.search(r"[(){};=]", tart)):
            ki.append((info, tart))
    return ki


def hiba_valasz(p: KN.Profil, valasz) -> dict:
    if p.azonosito == "cpp":
        return CA.hiba_valasz(valasz)
    s = CA.tisztit(valasz)
    talalat = list(_HIBA_SOR.finditer(s))
    if not talalat:
        return {"sor": None, "fajta": None, "magyarazat": s}
    m = talalat[-1]
    fajta = (m.group(2) or "").lower().strip("_") or None
    if fajta is not None and fajta not in FAJTAK:
        fajta = "egyeb"
    return {"sor": int(m.group(1)), "fajta": fajta, "magyarazat": (s[:m.start()] + s[m.end():]).strip()}


def tipp_valasz(p: KN.Profil, valasz) -> dict:
    if p.azonosito == "cpp":
        return CA.tipp_valasz(valasz)
    s = CA.tisztit(valasz)
    jelek = list(_SZINT.finditer(s))
    szintek: list[str | None] = [None, None, None]
    sorrend = []
    for i, m in enumerate(jelek):
        veg = jelek[i + 1].start() if i + 1 < len(jelek) else len(s)
        n = int(m.group(1)) - 1
        if szintek[n] is None:
            szintek[n] = s[m.end():veg].strip()
            sorrend.append(n)
    hiv = CA.sor_hivatkozasok(szintek[2] or "")
    return {"szintek": szintek, "sorrend_ok": sorrend == [0, 1, 2], "hely_sor": hiv[0] if hiv else None,
            "kod_szintek": [i for i, t in enumerate(szintek) if t and ("```" in t or "~~~" in t)]}


def megoldas_valasz(p: KN.Profil, valasz) -> dict:
    if p.azonosito == "cpp":
        return CA.megoldas_valasz(valasz)
    s = CA.tisztit(valasz)
    b = nyelv_blokkok(p, s)
    return {"kod": b[-1][1] if b else None, "magyarazat": CA.kodon_kivul(s).strip()}


def teszt_valasz(p: KN.Profil, valasz) -> dict:
    if p.azonosito == "cpp":
        return CA.teszt_valasz(valasz)
    s = CA.tisztit(valasz)
    kodok = nyelv_blokkok(p, s)
    bemenetek = []
    for info, tart in CA.kodblokkok(s):
        nyelv = info.split()[0] if info else ""
        if nyelv in _NEM_KOD or (not nyelv and not any(t == tart for _, t in kodok)):
            t = tart if tart.endswith("\n") else tart + "\n"
            if t.strip() and len(t) <= TESZT_BEMENET_MAX_KAR:
                bemenetek.append(t)
    return {"bemenetek": bemenetek[:TESZT_BEMENET_MAX], "referencia": kodok[-1][1] if kodok else None}


def stressz_valasz(p: KN.Profil, valasz) -> dict:
    if p.azonosito == "cpp":
        return CA.stressz_valasz(valasz)
    s = CA.tisztit(valasz)
    b = nyelv_blokkok(p, s)
    gen = next((t for i, t in b if "gener" in i), None)
    ref = next((t for i, t in b if "refer" in i), None)
    maradek = [t for i, t in b if t is not gen and t is not ref]
    if gen is None and maradek:
        gen = maradek.pop(0)
    if ref is None and maradek:
        ref = maradek.pop(0)
    return {"generator": gen, "referencia": ref}
