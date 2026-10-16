"""Demo workspace content, part 2: code tasks, cards, quizzes, PDF + highlights, canvas, Bases, calendar and assistant memory.

Pure builders over invented data (see `demo_tartalom`). Cards and quizzes are written with the product's own format modules
(`modulok/kartya/formatum.py`, `modulok/kviz/formatum.py`), so the demo files are exactly what the card and quiz features write.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from . import demo_fajlok, pdfkiemeles
from .demo_tartalom import MONDATOK as M

# ------------------------------------------------------------------ code task notes (C++, Python, JavaScript)

# (note title, folder file name, language tag, intro, source text, [(test title, input, output)])
KOD_FELADATOK = [
    ("Sum of numbers (Python)", "sum_numbers.py", "python",
     "Read `n` and then `n` integers on the next line. Print their sum.",
     'n = int(input())\nnumbers = list(map(int, input().split()))\nprint(sum(numbers[:n]))\n',
     [("Basic", "5\n1 2 3 4 5", "15"), ("A single value", "1\n42", "42"), ("Negative numbers", "3\n-4 10 -2", "4")]),
    ("FizzBuzz (JavaScript)", "fizzbuzz.js", "javascript",
     "Read `n`. For every number from 1 to `n` print `Fizz` for multiples of 3, `Buzz` for multiples of 5, `FizzBuzz` for both and "
     "the number otherwise.",
     "const input = require('fs').readFileSync(0, 'utf8').split('\\n');\nconst n = parseInt(input[0], 10);\nfor (let i = 1; i <= n; i++) {\n"
     "  let out = '';\n  if (i % 3 === 0) out += 'Fizz';\n  if (i % 5 === 0) out += 'Buzz';\n  console.log(out || String(i));\n}\n",
     [("Up to five", "5", "1\n2\nFizz\n4\nBuzz"), ("Up to fifteen", "15", "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz")]),
    ("Reverse a string (C++)", "reverse_string.cpp", "cpp",
     "Read one line and print it reversed.",
     '#include <algorithm>\n#include <iostream>\n#include <string>\n\nint main() {\n    std::string line;\n    std::getline(std::cin, line);\n'
     '    std::reverse(line.begin(), line.end());\n    std::cout << line << "\\n";\n    return 0;\n}\n',
     [("Word", "manifold", "dlofinam"), ("With spaces", "a b c", "c b a")]),
    ("Binary search (Python)", "binary_search.py", "python",
     f"{M['bin_felez']} Read `n`, then a sorted list of `n` integers, then a target. Print the index of the target, or -1.",
     'n = int(input())\nvalues = list(map(int, input().split()))\ntarget = int(input())\nlow, high = 0, n - 1\nanswer = -1\n'
     'while low <= high:\n    mid = (low + high) // 2\n    if values[mid] == target:\n        answer = mid\n        break\n'
     '    if values[mid] < target:\n        low = mid + 1\n    else:\n        high = mid - 1\nprint(answer)\n',
     [("Found", "5\n1 3 5 7 9\n7", "3"), ("Missing", "5\n1 3 5 7 9\n4", "-1"), ("First element", "3\n2 4 6\n2", "0")]),
    ("Word count (JavaScript)", "word_count.js", "javascript",
     "Read a text and print how many words it has. Words are separated by spaces or line breaks.",
     "const text = require('fs').readFileSync(0, 'utf8');\nconst words = text.split(/\\s+/).filter(Boolean);\nconsole.log(words.length);\n",
     [("One line", "the quick brown fox", "4"), ("Two lines", "one two\nthree", "3")]),
    ("Fibonacci (C++)", "fibonacci.cpp", "cpp",
     "Read `n` and print the n-th Fibonacci number, counting from F(0) = 0 and F(1) = 1.",
     '#include <iostream>\n\nint main() {\n    int n;\n    std::cin >> n;\n    long long a = 0, b = 1;\n    for (int i = 0; i < n; i++) {\n'
     '        long long next = a + b;\n        a = b;\n        b = next;\n    }\n    std::cout << a << "\\n";\n    return 0;\n}\n',
     [("F(10)", "10", "55"), ("F(0)", "0", "0"), ("F(20)", "20", "6765")]),
]
KOD_MAPPA = "Programming"
KOD_FORRAS_MAPPA = "Programming/code"


def kod(seed: int) -> dict[str, str]:
    """Task notes and their solution files."""
    ki = {}
    for cim, fajl, nyelv, bevezeto, forras, tesztek in KOD_FELADATOK:
        sorok = [bevezeto, "", f"![[{fajl}]]", "", "## Tests", "",
                 "Each `teszt` block gives an input and the expected output; the checks run in the sandbox and never touch your files.", ""]
        for t_cim, bemenet, kimenet in tesztek:
            sorok += [f"```teszt {t_cim}", "--- bemenet", bemenet, "--- kimenet", kimenet, "```", ""]
        sorok += ["Related: [[Big-O notation]], [[Programming glossary]].", "", f"#code/{nyelv}"]
        ki[f"{KOD_MAPPA}/{cim}.md"] = f"---\ntags:\n  - code/{nyelv}\n  - task\nlanguage: {nyelv}\n---\n\n# {cim}\n\n" + "\n".join(sorok) + "\n"
        ki[f"{KOD_FORRAS_MAPPA}/{fajl}"] = forras
    return ki


# ------------------------------------------------------------------ cards

# source note path (without .md), companion cards: (question, answer, source anchor)
KARTYA_CSOMAGOK = [
    ("Mathematics/Geometric series", [
        ("What is the ratio of a geometric sequence?", "The number every term is multiplied by to get the next term.", "g-ratio"),
        ("What is the n-th term of a geometric sequence?", "$a_n = a_1 q^{n-1}$", "g-term"),
        ("What is the sum of the first n terms when $q \\neq 1$?", "$S_n = a_1 \\frac{q^n - 1}{q - 1}$", "g-sum"),
        ("When does an infinite geometric series converge?", "Only when $|q| < 1$.", "g-infinite"),
        ("What is $1 + \\frac{1}{2} + \\frac{1}{4} + \\dots$?", "2", "g-infinite"),
    ]),
    ("Mathematics/Arithmetic series", [
        ("What is the common difference of an arithmetic sequence?", "The constant amount added to each term to get the next.", "a-diff"),
        ("What is the n-th term of an arithmetic sequence?", "$a_n = a_1 + (n-1)d$", "a-term"),
        ("How do you sum the first n terms of an arithmetic sequence?", "$S_n = \\frac{n(a_1 + a_n)}{2}$", "a-sum"),
        ("What is the sum of 2, 5, 8, 11, 14?", "40", "a-sum"),
    ]),
    ("Science/Newton's laws", [
        ("What does Newton's first law say?", "A body stays at rest or moves with constant velocity unless a net force acts on it.", "n-first"),
        ("What does Newton's second law say?", "The net force equals mass times acceleration, $F = ma$.", "n-second"),
        ("What does Newton's third law say?", "Every force has an equal and opposite reaction force.", "n-third"),
        ("A 2 kg cart gets a net force of 6 N. What is its acceleration?", "$3\\ \\mathrm{m/s^2}$", "n-second"),
    ]),
    ("Study skills/Spaced repetition", [
        ("What is spaced repetition?", "Reviewing a fact at growing intervals, just before it would be forgotten.", "s-def"),
        ("What happens to the gap after each successful recall?", "It gets longer.", "s-gap"),
        ("Which algorithm does Manifold use to schedule cards?", "FSRS.", "s-def"),
    ]),
    ("Science/Water cycle", [
        ("What turns liquid water into vapour in the water cycle?", "Evaporation, driven by the sun's warmth.", "w-evap"),
        ("What forms clouds from rising vapour?", "Condensation into tiny droplets.", "w-cond"),
        ("Name two forms of precipitation.", "Rain and snow (also hail).", "w-cond"),
    ]),
]
KARTYA_DATUM = "2026-10-01"


def _kartya_azon(seed: int, forras: str, kerdes: str) -> str:
    return "c-" + hashlib.sha1(f"{seed}|{forras}|{kerdes}".encode("utf-8")).hexdigest()[:8]


def kartyak(seed: int, cfg_mappa: str, md_utak: list[str]) -> dict[str, str]:
    """Companion card notes in the cards folder `cfg_mappa`. `md_utak`: every `.md` path of the library (name collisions)."""
    from modulok.kartya import formatum as F
    ki = {}
    for forras, lista in KARTYA_CSOMAGOK:
        lapok = [F.Kartya(k, v, _kartya_azon(seed, forras, k), f"{forras}#^{h}") for k, v, h in lista]
        nev = F.kiseronev(forras + ".md", md_utak)
        ki[f"{cfg_mappa}/{nev}.md"] = F.ir(lapok, [forras], modell="", keszult=KARTYA_DATUM)
    return ki


# ------------------------------------------------------------------ quizzes

KVIZ_DATUM = "2026-10-01 1200"


def _kerdes(sorszam, kerdes, jo, rosszak, magyarazat, idezet, szakasz=None, horgony=None):
    from modulok.kviz import formatum as FM
    valaszok = [jo, *rosszak]
    return FM.Kerdes(id=f"k{sorszam}", kerdes=kerdes, valaszok=valaszok, helyes=0, magyarazat=magyarazat, idezet=idezet,
                     szakasz=szakasz, horgony=horgony)


def _forgat(kerdesek, seed: int):
    """Moves the correct answer (initially first) to a seeded position, so the key is not always A."""
    ki = []
    for q in kerdesek:
        h = int(hashlib.sha1(f"{seed}|{q.id}".encode()).hexdigest(), 16) % 4
        v = q.valaszok[1:]
        v.insert(h, q.valaszok[0])
        q.valaszok, q.helyes = v, h
        ki.append(q)
    return ki


def kvizek(seed: int, cfg_mappa: str) -> dict[str, str]:
    from modulok.kviz import formatum as FM
    csomagok = [
        ("Mathematics/Geometric series", "Geometric series", [
            _kerdes(1, "What is the ratio $q$ of the sequence 3, 6, 12, 24?", "2", ["3", "6", "1/2"],
                    "Each term is the previous one multiplied by 2.", M["geo_hanyados"], "Geometric series", None),
            _kerdes(2, "Which formula gives the n-th term of a geometric sequence?", "$a_n = a_1 q^{n-1}$",
                    ["$a_n = a_1 + (n-1)q$", "$a_n = a_1 q^n$", "$a_n = q a_1^{n-1}$"],
                    "The exponent is $n-1$ because the first term has not been multiplied yet.", M["geo_tag"], "Geometric series", None),
            _kerdes(3, "What is $S_5$ for $a_1 = 3$ and $q = 2$?", "93", ["48", "96", "45"],
                    "$S_5 = 3 \\cdot (2^5 - 1)/(2 - 1) = 93$.", M["geo_osszeg"], "Sum of terms", "Sum of terms"),
            _kerdes(4, "When does an infinite geometric series converge?", "Only when $|q| < 1$.",
                    ["Always", "Only when $q > 1$", "Only when $q = 0$"],
                    "If $|q| \\geq 1$ the terms do not shrink, so the sum grows without bound.", M["geo_vegtelen"], "Infinite series",
                    "Infinite series"),
        ]),
        ("Science/Newton's laws", "Newton's laws", [
            _kerdes(1, "What happens to a body with no net force acting on it?", "It stays at rest or keeps a constant velocity.",
                    ["It slows down and stops", "It speeds up", "It moves in a circle"],
                    "This is Newton's first law.", M["newton_1"], "First law", "First law"),
            _kerdes(2, "A net force of 10 N acts on a 5 kg body. What is its acceleration?", "$2\\ \\mathrm{m/s^2}$",
                    ["$50\\ \\mathrm{m/s^2}$", "$0.5\\ \\mathrm{m/s^2}$", "$15\\ \\mathrm{m/s^2}$"],
                    "$a = F/m = 10/5 = 2$.", M["newton_2"], "Second law", "Second law"),
            _kerdes(3, "A book rests on a table. Which force is the reaction to the table pushing up on the book?",
                    "The book pushing down on the table.", ["Gravity on the book", "Friction", "Nothing"],
                    "The two forces of a pair act on different bodies.", M["newton_3"], "Third law", "Third law"),
        ]),
    ]
    ki = {}
    for forras, cim, kerdesek in csomagok:
        h = hashlib.sha1(f"{seed}|{forras}".encode()).hexdigest()[:6]
        k = FM.Kviz(azon=f"KVIZ-20261001-120000-{h}", forras=forras, cim=cim, modell="", keszult=KVIZ_DATUM,
                    kerdesek=_forgat(kerdesek, seed))
        ki[f"{cfg_mappa}/{FM.fajlnev(k)}.md"] = _kviz_szoveg(k)
    return ki


def _kviz_szoveg(k) -> str:
    """The quiz note in the product format (front matter, one `question` + `solution` callout pair per question) with an English
    introduction and no results section (the app adds `## Kitöltések` after the first attempt)."""
    from modulok.kviz import formatum as FM
    nev = FM.fajlnev(k)
    fej = ["---", "Source:", f'  - "[[{k.forras}]]"', f"Kviz: {k.azon}", "Modell:", f"Keszult: {k.keszult}", "---", ""]
    bevezeto = [f"# {nev}", "",
                f"A short quiz on [[{k.forras}|{k.cim}]], written for the demo ({len(k.kerdesek)} questions). Every question quotes a "
                "sentence of the note, so you can see where the answer comes from. Take it from the quiz page; the answer key "
                "stays hidden until you have answered.", "", "## Questions", ""]
    return "\n".join(fej + bevezeto) + "\n" + "\n\n".join(FM.ir_kerdes(k, q) for q in k.kerdesek) + "\n"


# ------------------------------------------------------------------ PDF and its highlights

PDF_UT = "Attachments/Orbits primer.pdf"
PDF_LAPOK = [
    {"cim": "Orbits primer", "felirat": "Invented sample document for the Manifold demo - page 1 of 3",
     "bekezdesek": [
         "This short primer is a made-up document that ships with the Manifold demo workspace. It exists so that you can try the PDF "
         "reader, select text, highlight a sentence and search inside a PDF.",
         "A planet moves around its star on an ellipse. The star sits in one focus of the ellipse, not in the centre.",
         "A line from the star to the planet sweeps out equal areas in equal times. Near the star the planet moves faster; far away "
         "it moves slower."]},
    {"cim": "Gravity and period", "felirat": "Invented sample document for the Manifold demo - page 2 of 3",
     "bekezdesek": [
         "Gravity pulls two masses together with a force that falls with the square of the distance between them.",
         "The orbital period grows with the size of the orbit: planets farther from the star take longer to go around.",
         "The diagram below shows an ellipse with the star in one focus."],
     "alakzatok": [(306, 380, 150, 80, "ellipszis"), (360, 380, 10, 0, "kor"), (156, 380, 300, 0, "vonal")]},
    {"cim": "Summary", "felirat": "Invented sample document for the Manifold demo - page 3 of 3",
     "bekezdesek": [
         "To summarise: orbits are ellipses, speed changes along the orbit, and the period depends on the size of the orbit.",
         "Try this: highlight the first sentence of this page, then open the highlights note next to the PDF to see it saved as text."]},
]
KIEMELESEK = [(1, "A planet moves around its star on an ellipse."),
              (2, "Gravity pulls two masses together with a force that falls with the square of the distance between them."),
              (3, "To summarise: orbits are ellipses, speed changes along the orbit, and the period depends on the size of the orbit.")]


def pdf_bajtok() -> bytes:
    return demo_fajlok.pdf(PDF_LAPOK, "Orbits primer (demo)")


def kiemeles_jegyzet(seed: int) -> dict[str, str]:
    """The highlights note next to the PDF, in the exact format the PDF reader writes."""
    ut = pdfkiemeles.fajl_ut(PDF_UT)
    cel = "Orbits primer.pdf"
    szoveg = pdfkiemeles.vaz(PDF_UT, "reading")
    for oldal, mondat in KIEMELESEK:
        tl = demo_fajlok.kiemeles_teglalapok(PDF_LAPOK[oldal - 1], mondat)
        kid = "k-" + hashlib.sha1(f"{seed}|{oldal}|{mondat}".encode()).hexdigest()[:6]
        szoveg = pdfkiemeles.beszur(szoveg, kid, oldal, mondat, tl, cel)
    oldalak = sorted(o for o, _ in KIEMELESEK)
    forrasok = "Source:\n" + "".join(f'  - "[[{cel}#page={o}]]"\n' for o in oldalak)
    szoveg = szoveg.replace("Source:\n", forrasok, 1)
    return {ut: szoveg}


# ------------------------------------------------------------------ canvas, Bases, property types

def _azon(seed: int, kulcs: str) -> str:
    return hashlib.sha1(f"{seed}|canvas|{kulcs}".encode()).hexdigest()[:16]


def canvas(seed: int) -> dict[str, str]:
    csucsok = [
        ("math", "file", "Mathematics/Geometric series.md", 0, 0),
        ("arith", "file", "Mathematics/Arithmetic series.md", 0, 240),
        ("quad", "file", "Mathematics/Quadratic equations.md", 0, 480),
        ("newton", "file", "Science/Newton's laws.md", 460, 0),
        ("orbit", "file", "Science/Orbits and gravity.md", 460, 240),
        ("srs", "file", "Study skills/Spaced repetition.md", 920, 0),
        ("recall", "file", "Study skills/Active recall.md", 920, 240),
        ("weekly", "file", "Study skills/Weekly review.md", 920, 480),
    ]
    nodes = [{"id": _azon(seed, k), "type": t, t: v, "x": x, "y": y, "width": 360, "height": 200} for k, t, v, x, y in csucsok]
    nodes.append({"id": _azon(seed, "text"), "type": "text", "text": "## Learning map\n\nHow the demo notes connect. Drag nodes, add cards, "
                  "draw arrows.", "x": 460, "y": 520, "width": 360, "height": 160, "color": "6"})
    elek = [("math", "arith", "compare"), ("math", "srs", "practice with"), ("arith", "srs", "practice with"), ("newton", "orbit", "explains"),
            ("srs", "recall", "pairs with"), ("recall", "weekly", "planned in"), ("quad", "math", "builds on")]
    edges = [{"id": _azon(seed, f"{a}-{b}"), "fromNode": _azon(seed, a), "fromSide": "right", "toNode": _azon(seed, b), "toSide": "left",
              "label": c} for a, b, c in elek]
    return {"Maps/Learning map.canvas": json.dumps({"nodes": nodes, "edges": edges}, indent="\t") + "\n"}


def bazisok() -> dict[str, str]:
    olvasas = """filters:
  and:
    - file.inFolder("Reading")
    - file.hasTag("book")
properties:
  author:
    displayName: Author
  year:
    displayName: Year
  status:
    displayName: Status
  rating:
    displayName: Rating
views:
  - type: table
    name: All books
    order:
      - file.name
      - author
      - year
      - status
      - rating
    sort:
      - property: year
        direction: DESC
  - type: table
    name: By status
    order:
      - file.name
      - author
      - rating
    groupBy:
      property: status
      direction: ASC
  - type: cards
    name: Finished
    filters:
      and:
        - status == "finished"
    order:
      - file.name
      - author
      - rating
"""
    projektek = """filters:
  and:
    - file.inFolder("Projects")
    - file.hasTag("project")
properties:
  status:
    displayName: Status
  priority:
    displayName: Priority
  start:
    displayName: Start
  due:
    displayName: Due
views:
  - type: table
    name: Projects
    order:
      - file.name
      - status
      - priority
      - start
      - due
    sort:
      - property: priority
        direction: ASC
"""
    return {"Bases/Reading list.base": olvasas, "Bases/Projects.base": projektek}


TIPUSOK = {"summary": "text", "topics": "multitext", "score": "number", "done": "checkbox", "due": "date", "start": "date",
           "reviewed": "datetime", "rating": "number", "pages": "number", "year": "number", "finished": "date", "focus": "number",
           "priority": "number", "date": "date"}


def tipusok() -> dict[str, str]:
    return {".obsidian/types.json": json.dumps({"types": dict(sorted(TIPUSOK.items()))}, indent=2) + "\n"}


# ------------------------------------------------------------------ pictures

def kepek() -> dict[str, bytes]:
    return {"Attachments/parabola.png": demo_fajlok.kep_parabola(), "Attachments/orbit.png": demo_fajlok.kep_palya(),
            "Attachments/right-triangle.png": demo_fajlok.kep_haromszog(), "Attachments/water-cycle.png": demo_fajlok.kep_vizkoerforgas(),
            "Attachments/cell.png": demo_fajlok.kep_sejt()}


# ------------------------------------------------------------------ calendar sample events (no EventKit, no permission)

NAPTAROK = [
    {"azon": "demo-study", "nev": "Study", "szin": "#a08cf6"},
    {"azon": "demo-deadlines", "nev": "Deadlines", "szin": "#ec7c61"},
    {"azon": "demo-timetable", "nev": "Timetable", "szin": "#78a6e6"},
    {"azon": "demo-personal", "nev": "Personal", "szin": "#e68aa8"},
]
# (calendar, title, day offset, start hour, minutes)
ESEMENYEK = [
    ("demo-study", "Study session: Geometric series", 1, 16, 60), ("demo-study", "Study session: Newton's laws", 3, 16, 60),
    ("demo-study", "Study session: Quadratic equations", 5, 17, 45), ("demo-study", "Study session: Binary search", 8, 16, 60),
    ("demo-study", "Review cards and quiz", -2, 18, 30),
    ("demo-deadlines", "Exam: Algebra basics", 6, 9, 60), ("demo-deadlines", "Deadline: Garden plan", 12, 17, 30),
    ("demo-deadlines", "Quiz: Physics motion", 9, 10, 40),
    ("demo-timetable", "Lesson: Mathematics", 2, 8, 45), ("demo-timetable", "Lesson: Computer science", 4, 10, 45),
    ("demo-personal", "Bike ride with a friend", 6, 15, 90), ("demo-personal", "Cook dinner", 2, 19, 60),
]


def naptar_adat(most: dt.datetime) -> dict:
    """The answer of a calendar helper (shape of `core/naptar_seged.py` `olvas`) with fixed sample events around `most`
    (an aware datetime). Same `most` gives the same data."""
    nap0 = most.replace(hour=0, minute=0, second=0, microsecond=0)
    naptarak = [{"azon": n["azon"], "nev": n["nev"], "tipus": "local", "forras": "Demo", "forras_tipus": "local",
                 "forras_azon": "demo", "irhato": False, "feliratkozas": False, "szin": n["szin"]} for n in NAPTAROK]
    esemenyek = []
    for n, (nap_azon, cim, eltolas, ora, perc) in enumerate(ESEMENYEK):
        kezd = nap0 + dt.timedelta(days=eltolas, hours=ora)
        veg = kezd + dt.timedelta(minutes=perc)
        esemenyek.append({"azon": f"demo-{n:02d}|{kezd.isoformat(timespec='seconds')}", "naptar": nap_azon, "cim": cim,
                          "kezd": kezd.isoformat(timespec="seconds"), "veg": veg.isoformat(timespec="seconds"),
                          "nap": kezd.date().isoformat(), "egesznap": False, "ismetlodo": False, "leszakitott": False, "allapot": 1})
    return {"ok": True, "allapot": "engedelyezve", "naptarak": naptarak, "esemenyek": esemenyek}


class DemoNaptarSeged:
    """A calendar 'helper' that returns the sample data: the demo never asks the system calendar for permission."""

    def __init__(self, most: dt.datetime):
        self.most = most

    def olvas(self, tol: str, ig: str) -> dict:
        return naptar_adat(self.most)


# ------------------------------------------------------------------ AI memory examples (Settings > AI > Memory)

TANULT_MINTAK = [
    {"elotte": "The ratio of a geometric sequence is", "szoveg": " the number each term is multiplied by."},
    {"elotte": "Remember to review the cards that are", "szoveg": " due today."},
    {"elotte": "In the weekly review I will first", "szoveg": " clear the ideas inbox."},
]
TANULT_MUVELETEK = [("cimke", "Mathematics", "math/algebra", 4), ("link", "Study skills", "Spaced repetition", 5),
                    ("sablon", "Meetings", "Meeting", 3)]


def asszisztens_memoria() -> dict:
    """Sample learned items for `{state}/asszisztens.json`: text patterns and repeated actions (all invented, no notes)."""
    from .asszisztens.mintatar import _h
    muveletek = {}
    for muvelet, mappa, ertek, db in TANULT_MUVELETEK:
        muveletek[_h(muvelet, mappa, ertek.casefold())] = {"muvelet": muvelet, "mappa": mappa, "ertek": ertek, "db": db, "utolso": 1_790_000_000.0}
    return {"kiegeszites_mintak": [dict(m) for m in TANULT_MINTAK], "muveletek": muveletek}
