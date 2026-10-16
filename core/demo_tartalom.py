"""Demo workspace content, part 1: the synthetic notes (English, neutral, no personal data).

Everything here is invented for the demo: topics are generic school-level maths and science, programming exercises, study
habits, fictional books and projects. Pure functions: `jegyzetek(seed)` returns `{vault-relative path: text}`; nothing is
read from or written to the disk. The seed only varies the sampled parts (daily notes), so one seed always gives the same bytes.

The sentences that cards and quizzes quote are defined once here (`MONDATOK`) and used by the note text, so a quote is
always a verbatim sentence of its source note.
"""
from __future__ import annotations

import datetime as dt
import random

# ------------------------------------------------------------------ sentences quoted by cards and quizzes

MONDATOK = {
    "geo_hanyados": "The ratio $q$ is the number every term is multiplied by to get the next term.",
    "geo_tag": "The $n$-th term of a geometric sequence is $a_n = a_1 q^{n-1}$.",
    "geo_osszeg": "For $q \\neq 1$ the sum of the first $n$ terms is $S_n = a_1 \\frac{q^n - 1}{q - 1}$.",
    "geo_vegtelen": "An infinite geometric series converges only when $|q| < 1$.",
    "ari_kulonbseg": "The common difference $d$ is the constant amount added to each term to get the next term.",
    "ari_tag": "The $n$-th term of an arithmetic sequence is $a_n = a_1 + (n-1)d$.",
    "ari_osszeg": "The sum of the first $n$ terms is $S_n = \\frac{n(a_1 + a_n)}{2}$.",
    "newton_1": "A body stays at rest or moves with constant velocity unless a net force acts on it.",
    "newton_2": "The net force on a body equals its mass times its acceleration, $F = ma$.",
    "newton_3": "When one body pushes on another, the second pushes back on the first with an equal force in the opposite direction.",
    "tav_ismetles": "Spaced repetition reviews a fact at growing intervals, just before it would be forgotten.",
    "tav_felidezes": "Each successful recall makes the next gap between reviews longer.",
    "viz_parolgas": "Evaporation turns liquid water into vapour when the sun warms oceans, lakes and soil.",
    "viz_lecsapodas": "Condensation turns rising vapour into tiny droplets that form clouds.",
    "bin_felez": "Binary search halves the range of candidates at every step.",
}

KOZZETETEL = "2026-10-01"


def _fm(**kv) -> str:
    """Front matter with simple scalar / list / link values, in insertion order."""
    sorok = ["---"]
    for k, v in kv.items():
        if v is None:
            continue
        if isinstance(v, list):
            sorok.append(f"{k}:" + ("" if v else " []"))
            sorok += [f"  - {x}" for x in v]
        elif isinstance(v, bool):
            sorok.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, str) and (v.startswith("[[") or ": " in v or v.startswith(("#", "!", "&", "*"))):
            sorok.append(f'{k}: "{v}"')
        else:
            sorok.append(f"{k}: {v}")
    sorok.append("---")
    return "\n".join(sorok) + "\n\n"


def _jegyzet(cim: str, torzs: str, **fm) -> str:
    return (_fm(**fm) if fm else "") + f"# {cim}\n\n" + torzs.strip("\n") + "\n"


# ------------------------------------------------------------------ hub notes

def _hub() -> dict[str, str]:
    m = {}
    m["Welcome.md"] = _jegyzet("Welcome to Manifold", """
Your notes are Markdown files on your Mac. Start writing here, or open [[Connected ideas]].

Use **Cmd+O** to find notes, **Cmd+P** for commands and **Cmd+,** for Settings.

AI is optional. Editing, search and local history work without a model.

## This demo workspace

This is a small library of invented notes. Everything in it is sample data, and it is safe to edit: the demo can be reset to its
original state at any time from Settings. The [[Tour of Manifold]] walks through seven things to try.

- Maths: [[Geometric series]], [[Quadratic equations]], [[Solving linear equations]]
- Science: [[Newton's laws]], [[Orbits and gravity]], [[Water cycle]]
- Code: [[Sum of numbers (Python)]], [[FizzBuzz (JavaScript)]], [[Reverse a string (C++)]]
- Study: [[Spaced repetition]], [[Active recall]], [[Weekly review]]
- Reading and projects: [[Reading overview]], [[Garden planner]]

The built-in user guide is in the **Manifold Guide** folder: start with [[Getting started]].
""", tags=["demo", "start"])
    m["Connected ideas.md"] = _jegyzet("Connected ideas", """
Link notes with `[[Welcome]]`. Add headings, lists and tasks as you write.

- [ ] Try editing this note
- [ ] Follow the link back to [[Welcome]]

See [[Writing in two languages]] for automatic language recognition.

Linked notes show up in the Backlinks panel, in the graph and in the outline. Try opening [[Spaced repetition]] and look at its
backlinks: several notes point to it. A link to a note that does not exist yet, such as [[Fractals]], stays visible as an
unresolved link until you create the note.
""", tags=["demo", "start"])
    m["Writing in two languages.md"] = _jegyzet("Writing in two languages", """
Write naturally. Manifold recognises the language of your notes locally, independently of its English interface.

Ez egy magyar nyelvű mintabekezdés. A jegyzeteid a saját mappádban maradnak, és szabadon szerkesztheted őket.

This paragraph is English again. Nothing leaves your Mac to detect the language.
""", tags=["demo", "start"])
    m["Tour of Manifold.md"] = _jegyzet("Tour of Manifold", """
Seven short flows to try in this workspace. None of them needs a network connection or an AI model.

1. **Open and search.** Press Cmd+O and type `geo` to open [[Geometric series]]. Search for `ratio`, or use `tag:#math/algebra`.
2. **Links and backlinks.** Open [[Spaced repetition]] and read its Backlinks panel. Open the graph and find the study cluster. The
   canvas [[Learning map.canvas]] shows the same ideas as a map.
3. **Properties and Bases.** [[Property types]] lists every property type. [[Reading overview]] embeds a Base that turns the
   properties of the book notes into a table.
4. **Cards and quiz.** The cards for [[Geometric series]] live in a companion note; review them from the Cards page. The quiz
   for the same note can be taken from its file in the quizzes folder.
5. **Maths.** [[Solving linear equations]] is a step-by-step derivation. Select the lines and run the derivation check; the
   note [[Common algebra mistakes]] contains a wrong step on purpose.
6. **Code.** [[Sum of numbers (Python)]], [[FizzBuzz (JavaScript)]] and [[Reverse a string (C++)]] embed a solution file and
   `teszt` blocks that run in the sandbox.
7. **PDF.** Open [[Orbits primer.pdf]], select a sentence and highlight it. Highlights are saved as text in a note next to the
   PDF.

## About AI in this demo

No model is installed and nothing is downloaded. AI features show as **Trial** until a model has been measured on your Mac, and
trial results are never written into your notes without asking.

## Calendar and reminders

The demo ships a few sample events and tasks with dates, so the Today page and the study planner have something to show. See
[[Calendar and reminders]].
""", tags=["demo", "start"])
    return m


# ------------------------------------------------------------------ mathematics

def _matek() -> dict[str, str]:
    M = MONDATOK
    m = {}
    m["Mathematics/Geometric series.md"] = _jegyzet("Geometric series", f"""
A geometric sequence multiplies each term by the same number. {M['geo_hanyados']} ^g-ratio

{M['geo_tag']} ^g-term

For example, with $a_1 = 3$ and $q = 2$ the sequence is 3, 6, 12, 24, 48.

## Sum of terms

{M['geo_osszeg']} ^g-sum

With $a_1 = 3$, $q = 2$ and $n = 5$ this gives $S_5 = 3 \\cdot \\frac{{2^5 - 1}}{{2 - 1}} = 93$.

## Infinite series

{M['geo_vegtelen']} ^g-infinite

Then the sum is $S = \\frac{{a_1}}{{1 - q}}$. For $a_1 = 1$ and $q = \\frac{{1}}{{2}}$ the sum is 2.

Compare with the [[Arithmetic series]]. A picture book version of the same idea is a possible future note: [[Fractals]].

#math/algebra
""", aliases=["Geometric sequence"], tags=["math/algebra", "series"], level=2, done=False)
    m["Mathematics/Arithmetic series.md"] = _jegyzet("Arithmetic series", f"""
{M['ari_kulonbseg']} ^a-diff

{M['ari_tag']} ^a-term

{M['ari_osszeg']} ^a-sum

Example: 2, 5, 8, 11, 14 has $a_1 = 2$ and $d = 3$, so $S_5 = \\frac{{5(2 + 14)}}{{2}} = 40$.

Related: [[Geometric series]], [[Solving linear equations]].

#math/algebra
""", tags=["math/algebra", "series"], level=1, done=True)
    m["Mathematics/Solving linear equations.md"] = _jegyzet("Solving linear equations", """
To solve a linear equation, do the same thing to both sides until $x$ stands alone.

A worked derivation. Select the lines below and run **Check derivation**: every step should be equivalent to the one before.

$$
\\begin{aligned}
2x + 6 &= 14 \\\\
2x &= 8 \\\\
x &= 4
\\end{aligned}
$$

A second example with brackets:

$$
\\begin{aligned}
3(x - 2) &= x + 4 \\\\
3x - 6 &= x + 4 \\\\
2x &= 10 \\\\
x &= 5
\\end{aligned}
$$

See [[Common algebra mistakes]] for steps that look right and are not, and [[Quadratic equations]] for the next level.

#math/algebra
""", tags=["math/algebra", "derivation"], level=1)
    m["Mathematics/Common algebra mistakes.md"] = _jegyzet("Common algebra mistakes", """
These derivations contain a wrong step on purpose. Run **Check derivation** on each block: the checker marks the first line that
is not equivalent to the line before.

Expanding a square (the cross term is missing):

$$
\\begin{aligned}
(a + b)^2 &= (a + b)^2 \\\\
&= a^2 + b^2
\\end{aligned}
$$

The correct version:

$$
\\begin{aligned}
(a + b)^2 &= (a + b)^2 \\\\
&= a^2 + 2ab + b^2
\\end{aligned}
$$

A slip while moving a term:

$$
\\begin{aligned}
2x + 6 &= 14 \\\\
2x &= 9 \\\\
x &= 4
\\end{aligned}
$$

Back to [[Solving linear equations]] and [[Algebra identities]].

#math/algebra
""", tags=["math/algebra", "derivation"], level=1)
    m["Mathematics/Quadratic equations.md"] = _jegyzet("Quadratic equations", """
A quadratic equation has the form $ax^2 + bx + c = 0$ with $a \\neq 0$.

The solutions are $x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$. The sign of the discriminant $D = b^2 - 4ac$ tells how many real
solutions there are: two if $D > 0$, one if $D = 0$, none if $D < 0$.

![[parabola.png|360]]

The graph of $x^2 - 2x - 3$ crosses the axis at the two solutions:

```plot
x in [-4, 5]
y in [-5, 10]
y = x^2 - 2*x - 3  "f"
pont (3, 0) "root"
pont (-1, 0) "root"
```

Factoring gives the same answer: $x^2 - 2x - 3 = (x - 3)(x + 1)$. See [[Algebra identities]] for the identities used and
[[Solving linear equations]] for the warm-up.

#math/algebra
""", tags=["math/algebra", "equations"], level=2)
    m["Mathematics/Algebra identities.md"] = _jegyzet("Algebra identities", """
Three identities worth knowing by heart:

- $(a + b)^2 = a^2 + 2ab + b^2$
- $(a - b)^2 = a^2 - 2ab + b^2$
- $a^2 - b^2 = (a - b)(a + b)$

They turn a product into a sum and back, which is how most factoring works. Used in [[Quadratic equations]]; the usual slips
are collected in [[Common algebra mistakes]].

#math/algebra
""", tags=["math/algebra"], level=1)
    m["Mathematics/Derivative rules.md"] = _jegyzet("Derivative rules", """
The derivative $f'(x)$ is the slope of the tangent line of $f$ at $x$.

| Rule | Formula |
|---|---|
| Power | $(x^n)' = n x^{n-1}$ |
| Sum | $(f + g)' = f' + g'$ |
| Product | $(fg)' = f'g + fg'$ |
| Chain | $(f(g(x)))' = f'(g(x)) \\cdot g'(x)$ |

Example: $(3x^4 - 2x)' = 12x^3 - 2$.

Next: [[Integral basics]]. The idea of a limit comes first: [[Limits and continuity]].

#math/calculus
""", tags=["math/calculus"], level=3)
    m["Mathematics/Integral basics.md"] = _jegyzet("Integral basics", """
An integral adds up infinitely many infinitely thin slices. The fundamental theorem links it to the derivative:

$$\\int_a^b f'(x)\\,dx = f(b) - f(a)$$

Common antiderivatives: $\\int x^n\\,dx = \\frac{x^{n+1}}{n+1} + C$ for $n \\neq -1$, and $\\int \\frac{1}{x}\\,dx = \\ln|x| + C$.

See [[Derivative rules]] and [[Logarithms]].

#math/calculus
""", tags=["math/calculus"], level=3)
    m["Mathematics/Limits and continuity.md"] = _jegyzet("Limits and continuity", """
The limit $\\lim_{x \\to a} f(x) = L$ says $f(x)$ gets as close to $L$ as we like when $x$ is close enough to $a$.

A function is continuous at $a$ when the limit exists and equals $f(a)$. A classic example:

$$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$$

Limits are the basis of the [[Derivative rules]].

#math/calculus
""", tags=["math/calculus"], level=3)
    m["Mathematics/Logarithms.md"] = _jegyzet("Logarithms", """
The logarithm answers the question "which power gives this number?": $\\log_b y = x$ means $b^x = y$.

- $\\log_b(xy) = \\log_b x + \\log_b y$
- $\\log_b\\frac{x}{y} = \\log_b x - \\log_b y$
- $\\log_b x^k = k \\log_b x$

Logarithms undo exponentials, which is why they appear in the [[Geometric series]] when solving for $n$, and in
[[Integral basics]].

#math/algebra
""", tags=["math/algebra"], level=2)
    m["Mathematics/Right triangles.md"] = _jegyzet("Right triangles", """
In a right triangle the square of the hypotenuse equals the sum of the squares of the legs: $a^2 + b^2 = c^2$.

![[right-triangle.png|360]]

For a 3-4-5 triangle: $3^2 + 4^2 = 9 + 16 = 25 = 5^2$. The ratios of the sides define sine, cosine and tangent; see
[[Trigonometric identities]].

#math/geometry
""", tags=["math/geometry"], level=1)
    m["Mathematics/Trigonometric identities.md"] = _jegyzet("Trigonometric identities", """
The most important identity follows from the Pythagorean theorem in [[Right triangles]]:

$$\\sin^2 x + \\cos^2 x = 1$$

Others: $\\tan x = \\frac{\\sin x}{\\cos x}$, $\\sin 2x = 2 \\sin x \\cos x$ and $\\cos 2x = \\cos^2 x - \\sin^2 x$.

#math/geometry
""", tags=["math/geometry"], level=2)
    m["Mathematics/Matrix basics.md"] = _jegyzet("Matrix basics", """
A matrix is a rectangular table of numbers. Two matrices of the same size are added entry by entry; a product $AB$ needs as many
columns in $A$ as rows in $B$.

$$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}\\begin{pmatrix} 0 & 1 \\\\ 1 & 0 \\end{pmatrix} = \\begin{pmatrix} 2 & 1 \\\\ 4 & 3 \\end{pmatrix}$$

Matrix multiplication is not commutative: in general $AB \\neq BA$.

#math/algebra
""", tags=["math/algebra"], level=3)
    return m


# ------------------------------------------------------------------ science

def _termeszettudomany() -> dict[str, str]:
    M = MONDATOK
    m = {}
    m["Science/Newton's laws.md"] = _jegyzet("Newton's laws", f"""
## First law

{M['newton_1']} ^n-first

## Second law

{M['newton_2']} ^n-second

A 2 kg cart pushed with a net force of 6 N accelerates at $a = F/m = 3\\ \\mathrm{{m/s^2}}$.

## Third law

{M['newton_3']} ^n-third

The laws describe motion in [[Kinematics]] and lead to [[Energy and work]]. For planets see [[Orbits and gravity]].

#science/physics
""", aliases=["Laws of motion"], tags=["science/physics"], level=2)
    m["Science/Kinematics.md"] = _jegyzet("Kinematics", """
Kinematics describes motion without asking what causes it. For constant acceleration $a$:

- $v = v_0 + at$
- $s = v_0 t + \\frac{1}{2} a t^2$
- $v^2 = v_0^2 + 2as$

A car starting from rest with $a = 2\\ \\mathrm{m/s^2}$ covers $s = \\frac{1}{2} \\cdot 2 \\cdot 5^2 = 25\\ \\mathrm{m}$ in 5 seconds.
The causes are in [[Newton's laws]].

#science/physics
""", tags=["science/physics"], level=1)
    m["Science/Energy and work.md"] = _jegyzet("Energy and work", """
Work is force along the displacement, $W = F s \\cos\\theta$. Kinetic energy is $E_k = \\frac{1}{2} m v^2$ and potential energy
near the ground is $E_p = m g h$.

> [!note] Conservation
> Without friction, $E_k + E_p$ stays constant while a body falls or swings.

Builds on [[Newton's laws]] and [[Kinematics]].

#science/physics
""", tags=["science/physics"], level=2)
    m["Science/Orbits and gravity.md"] = _jegyzet("Orbits and gravity", """
Two masses attract each other with the force $F = G \\frac{m_1 m_2}{r^2}$. A planet stays on its orbit because gravity keeps
bending its straight-line motion, as [[Newton's laws]] predict.

![[orbit.png|360]]

The orbit is an ellipse with the star in one focus, and the planet moves faster when it is closer. The reading list has a
fictional book about this: [[An Introduction to Orbits]]. The PDF [[Orbits primer.pdf]] summarises it in three pages.

#science/physics
""", source="[[An Introduction to Orbits]]", tags=["science/physics", "astronomy"], level=2)
    m["Science/Waves.md"] = _jegyzet("Waves", """
A wave carries energy without carrying matter. Frequency $f$, wavelength $\\lambda$ and speed $v$ are linked by $v = f\\lambda$.

Sound is a longitudinal wave, light a transverse one. Two waves of the same frequency can add up (constructive interference) or
cancel (destructive interference). A good companion book in the list: [[Waves and Rhythms]].

#science/physics
""", source="[[Waves and Rhythms]]", tags=["science/physics"], level=2)
    m["Science/Cell structure.md"] = _jegyzet("Cell structure", """
Cells are the smallest units of life. Most cells have a membrane, cytoplasm and genetic material.

![[cell.png|360]]

Plant cells also have a cell wall and chloroplasts, where [[Photosynthesis]] happens. The book [[A Field Guide to Cells]] gives
more detail.

#science/biology
""", source="[[A Field Guide to Cells]]", tags=["science/biology"], level=1)
    m["Science/Photosynthesis.md"] = _jegyzet("Photosynthesis", """
Plants turn light, water and carbon dioxide into sugar and oxygen:

$$6\\,\\mathrm{CO_2} + 6\\,\\mathrm{H_2O} \\xrightarrow{\\text{light}} \\mathrm{C_6H_{12}O_6} + 6\\,\\mathrm{O_2}$$

It takes place in the chloroplasts of the [[Cell structure|cell]]. The sun's energy also drives the [[Water cycle]].
In the [[Garden planner]] it explains why the tomatoes get the sunniest bed.

#science/biology
""", tags=["science/biology"], level=2)
    m["Science/Water cycle.md"] = _jegyzet("Water cycle", f"""
![[water-cycle.png|360]]

{M['viz_parolgas']} ^w-evap

{M['viz_lecsapodas']} ^w-cond

Rain, snow and hail bring the water back to the ground (precipitation), and rivers carry it to the sea again (runoff).

Related: [[Photosynthesis]], [[Garden planner]].

#science/earth
""", tags=["science/earth"], level=1)
    return m


# ------------------------------------------------------------------ programming (task notes live in demo_tanulas)

def _programozas() -> dict[str, str]:
    M = MONDATOK
    m = {}
    m["Programming/Big-O notation.md"] = _jegyzet("Big-O notation", f"""
Big-O describes how the running time of an algorithm grows with the input size $n$.

| Class | Name | Example |
|---|---|---|
| $O(1)$ | constant | reading one array element |
| $O(\\log n)$ | logarithmic | [[Binary search (Python)]] |
| $O(n)$ | linear | [[Sum of numbers (Python)]] |
| $O(n^2)$ | quadratic | comparing every pair |

{M['bin_felez']} That is why it needs only about $\\log_2 n$ steps; see [[Logarithms]].

#code/theory
""", tags=["code/theory"])
    m["Programming/Programming glossary.md"] = _jegyzet("Programming glossary", """
- **Algorithm**: a finite list of steps that solves a problem.
- **Variable**: a named place that holds a value.
- **Function**: a reusable block of code with inputs and an output.
- **Test**: a small program or check that confirms code does what you expect.
- **Complexity**: how cost grows with input size, see [[Big-O notation]].
- **Sandbox**: a restricted environment where code runs without touching your files; used by the task notes such as
  [[Reverse a string (C++)]].

#code/theory
""", tags=["code/theory"])
    return m


# ------------------------------------------------------------------ study skills

def _tanulas() -> dict[str, str]:
    M = MONDATOK
    m = {}
    m["Study skills/Spaced repetition.md"] = _jegyzet("Spaced repetition", f"""
{M['tav_ismetles']} ^s-def

{M['tav_felidezes']} ^s-gap

Manifold schedules cards with the FSRS algorithm. Try it with the cards for [[Geometric series]] or [[Newton's laws]].
It works best together with [[Active recall]].

#study
""", aliases=["SRS"], tags=["study", "memory"])
    m["Study skills/Active recall.md"] = _jegyzet("Active recall", """
Active recall means trying to produce the answer from memory instead of rereading it. Closing the book and writing down what you
remember is a form of recall; so is a quiz.

- Turn each heading of a note into a question.
- Answer before you look.
- Mark what you missed and review it with [[Spaced repetition]].

Try the quiz for [[Geometric series]]. Planned in the [[Weekly review]].

#study
""", tags=["study", "memory"])
    m["Study skills/Note-taking methods.md"] = _jegyzet("Note-taking methods", """
Three common ways to take notes:

1. **Linear notes**: write in order, good for lectures.
2. **Outline method**: nested bullets for structure.
3. **Linked notes**: small notes that point to each other, see [[Atomic notes]].

No method is best; the one you actually review is. Compare [[Active recall]].

#study
""", tags=["study", "notes"])
    m["Study skills/Atomic notes.md"] = _jegyzet("Atomic notes", """
An atomic note holds one idea, so it can be linked from many places. Write the title as a statement, link to related notes, and
let the [[Connected ideas]] panel show you what else points there.

The book [[Notes on Notes]] argues for this style. See also [[Note-taking methods]].

#study
""", source="[[Notes on Notes]]", tags=["study", "notes"])
    m["Study skills/Weekly review.md"] = _jegyzet("Weekly review", """
Once a week, spend twenty minutes on this list:

- [ ] Clear the [[Ideas inbox]]
- [ ] Review the cards that are due ([[Spaced repetition]])
- [ ] Take one quiz ([[Active recall]])
- [ ] Look at the open tasks in [[Study plan October]]
- [x] Write down what went well

The daily notes help: start from [[2026-10-14]] and look backwards.

#study
""", tags=["study", "routine"])
    m["Study skills/Focus and breaks.md"] = _jegyzet("Focus and breaks", """
Short focused blocks followed by real breaks work better than long, tiring sessions. A common rhythm is 25 minutes of work and
5 minutes of rest; after four rounds take a longer break.

Plan the blocks in the [[Study plan October]]; the book [[Calculus in Pictures]] is a good candidate for a focused block.

#study
""", tags=["study", "routine"])
    m["Study skills/Learning goals.md"] = _jegyzet("Learning goals", """
Good goals are specific and small. Instead of "learn maths", write "solve five quadratic equations by Friday" and link the
notes you need: [[Quadratic equations]], [[Algebra identities]].

Review goals in the [[Weekly review]].

#study
""", tags=["study", "planning"])
    return m


# ------------------------------------------------------------------ reading list (fictional books)

KONYVEK = [
    # path stem, title, author, year, pages, status, rating, finished, topic link, summary
    ("An Introduction to Orbits", "Mira Solen", 2018, 240, "finished", 5, "2026-09-14", "Orbits and gravity",
     "A gentle book about gravity and planetary motion."),
    ("The Practice of Recall", "Tobias Rane", 2020, 180, "finished", 4, "2026-09-02", "Active recall",
     "Short chapters on remembering what you read."),
    ("Small Steps in Algebra", "Ada Wren", 2015, 320, "reading", None, None, "Algebra identities",
     "Algebra from the first equation to quadratics."),
    ("Code by Example", "Jonas Pell", 2021, 400, "reading", None, None, "Sum of numbers (Python)",
     "Programming through small worked tasks."),
    ("Notes on Notes", "Lena Corvo", 2019, 150, "finished", 4, "2026-08-21", "Atomic notes",
     "Why small linked notes beat long documents."),
    ("A Field Guide to Cells", "Idris Vale", 2017, 210, "planned", None, None, "Cell structure",
     "An illustrated tour of plant and animal cells."),
    ("Waves and Rhythms", "Nora Finch", 2016, 190, "planned", None, None, "Waves",
     "Sound, light and everything that oscillates."),
    ("Calculus in Pictures", "Owen Marsh", 2022, 260, "finished", 5, "2026-10-05", "Derivative rules",
     "Derivatives and integrals explained with drawings."),
]


def _olvasas() -> dict[str, str]:
    m = {}
    for cim, szerzo, ev, oldal, allapot, ertek, kesz, tema, osszegzes in KONYVEK:
        sorok = [f"{osszegzes} Fictional book, invented for this demo.", "", f"Topic note: [[{tema}]]."]
        if allapot == "finished":
            sorok += ["", "## Takeaways", "", "- The main idea fits in one sentence; write it down.",
                      "- Link what you learned to your own notes."]
        elif allapot == "reading":
            sorok += ["", "## Progress", "", "- [ ] Finish the next chapter", "- [ ] Write a summary note"]
        else:
            sorok += ["", "Not started yet."]
        m[f"Reading/{cim}.md"] = _jegyzet(cim, "\n".join(sorok), type="book", author=szerzo, year=ev, pages=oldal,
                                          status=allapot, rating=ertek, finished=kesz, tags=["book"])
    m["Reading/Reading overview.md"] = _jegyzet("Reading overview", """
The table below is a **Base**: it reads the properties (author, year, status, rating) of every note tagged `book`. Edit a
property in a book note and the table updates. Open the file [[Reading list.base]] to change the view itself.

![[Reading list.base]]

Currently reading: [[Small Steps in Algebra]], [[Code by Example]]. Reading takes time; plan it in the [[Weekly review]].
""", tags=["reading"])
    return m


# ------------------------------------------------------------------ projects, meetings, reference

def _projektek() -> dict[str, str]:
    m = {}
    m["Projects/Garden planner.md"] = _jegyzet("Garden planner", """
A small project: plan a vegetable garden for the spring. Tomatoes need sun (see [[Photosynthesis]]); beans need support.

## Beds

| Bed | Crop | Sun |
|---|---|---|
| North | beans | partial |
| South | tomatoes | full |
| East | herbs | partial |

## Tasks

- [x] Measure the garden
- [ ] Order seeds 📅 2026-10-20
- [ ] Build two raised beds 📅 2026-11-02
- [ ] Draw the final plan 📅 2026-10-27

Notes from the kickoff: [[Meeting - Project review]].
""", status="active", priority=2, start="2026-10-01", due="2026-11-15", tags=["project", "garden"])
    m["Projects/Bike repair log.md"] = _jegyzet("Bike repair log", """
A running log of small repairs, newest first.

- 2026-10-09: replaced the rear brake pads.
- 2026-09-25: oiled the chain, pumped the tyres to 4 bar.
- 2026-09-10: fixed a flat front tyre.

## Next

- [ ] Check the gear cable 📅 2026-10-22
- [ ] Buy a new bell 📅 2026-10-30

Repairs are physics in practice: levers, friction and [[Energy and work]].
""", status="active", priority=3, start="2026-09-10", tags=["project", "bike"])
    m["Projects/Study plan October.md"] = _jegyzet("Study plan October", """
The plan for the month. Each week has one topic from each area.

## Week 1 - 5 October
- [x] [[Geometric series]] with cards and quiz
- [x] [[Newton's laws]]

## Week 2 - 12 October
- [x] [[Quadratic equations]]
- [ ] [[Derivative rules]] 📅 2026-10-17

## Week 3 - 19 October
- [ ] [[Binary search (Python)]] 📅 2026-10-21
- [ ] [[Orbits and gravity]] and the [[Orbits primer.pdf]] 📅 2026-10-23

## Week 4 - 26 October
- [ ] Review everything in the [[Weekly review]] 📅 2026-10-30

Time blocks for these appear in the calendar as study sessions, see [[Calendar and reminders]].
""", status="active", priority=1, start="2026-10-01", due="2026-10-31", tags=["project", "study"])
    m["Projects/Ideas inbox.md"] = _jegyzet("Ideas inbox", """
Capture first, sort later. Clear this list in the [[Weekly review]].

- A note about fractals, linked from the [[Geometric series]]
- Draw a map of all physics notes ([[Learning map.canvas]] is a start)
- Try a longer coding task with tests
- Write a summary of [[Calculus in Pictures]]
""", tags=["inbox"])
    m["Projects/Project dashboard.md"] = _jegyzet("Project dashboard", """
All projects in one table, read from their properties.

![[Projects.base]]

Open projects: [[Garden planner]], [[Bike repair log]], [[Study plan October]].
""", tags=["dashboard"])
    m["Meetings/Meeting - Study group kickoff.md"] = _jegyzet("Meeting - Study group kickoff", """
Date: 2026-10-02. Attendees: four invented people (A, B, C, D).

## Decisions

- Meet every Thursday for 45 minutes.
- Each person presents one topic; start with [[Spaced repetition]].

## Actions

- [ ] A: prepare cards for [[Geometric series]] 📅 2026-10-08
- [ ] B: find a quiz format for [[Active recall]]
""", date="2026-10-02", tags=["meeting"])
    m["Meetings/Meeting - Project review.md"] = _jegyzet("Meeting - Project review", """
Date: 2026-10-12. Reviewing the [[Garden planner]] and the [[Bike repair log]].

## Notes

- The garden plan needs the seed list before ordering.
- The bike only needs small repairs; keep the log short.

## Actions

- [ ] Send the seed list 📅 2026-10-18
""", date="2026-10-12", tags=["meeting"])
    return m


def _referencia() -> dict[str, str]:
    m = {}
    m["Reference/Property types.md"] = _jegyzet("Property types", """
The properties at the top of this note show every type. Click a property icon to see or change its type. A type is a setting of
the whole workspace, so `score` is a number in every note that has it.

| Property | Type | Example |
|---|---|---|
| summary | text | one line |
| topics | list | several values |
| score | number | 7.5 |
| done | checkbox | true / false |
| due | date | 2026-11-01 |
| reviewed | date and time | with a clock time |
| related | link | `[[Welcome]]` |
| tags, aliases | built in | |

The Base [[Reading list.base]] sorts and filters on these types.
""", summary="A note that shows every property type.", topics=["types", "demo", "reference"], score=7.5, done=True,
        due="2026-11-01", reviewed="2026-10-15T09:30:00", related="[[Welcome]]", aliases=["Properties demo"],
        tags=["reference", "demo"])
    m["Reference/Tags overview.md"] = _jegyzet("Tags overview", """
Tags group notes without folders. Nested tags use a slash: `#math/algebra` is inside `#math`.

Try the tag pane or search `tag:#math`. Main tags in this workspace: #math, #science, #code, #study, #project, #book, #daily.

A note can carry several tags in its properties or inline in the text, for example #demo.
""", tags=["reference", "demo"])
    m["Reference/Markdown cheatsheet.md"] = _jegyzet("Markdown cheatsheet", """
## Text

**bold**, *italic*, ~~strikethrough~~, ==highlight== and `inline code`.

## Links and embeds

- Link: [[Welcome]], with an alias: [[Welcome|the start page]], to a heading: [[Geometric series#Sum of terms]]
- Block link: [[Geometric series#^g-ratio]]
- External: [Example](https://example.com)
- Embed a note section: ![[Geometric series#Sum of terms]]

## Callouts

> [!tip] A tip
> Callouts group related text. Use `-` after the type to make one collapsible.

> [!warning]- Collapsed warning
> Hidden until you open it.

## Lists, tasks and tables

1. First
2. Second
   - nested bullet

- [ ] open task
- [x] done task

| Left | Right |
|---|---|
| a | b |

## Code, maths and comments

```python
print("hello")
```

Inline math $e^{i\\pi} + 1 = 0$ and a block:

$$\\sum_{k=1}^{n} k = \\frac{n(n+1)}{2}$$

%% This comment is not shown in Reading view. %%

A footnote[^1].

[^1]: Footnotes appear at the bottom.
""", tags=["reference"])
    m["Reference/Calendar and reminders.md"] = _jegyzet("Calendar and reminders", """
Manifold can show your calendar next to your notes. In this demo a few **sample events** are included instead of reading your
real calendar: study sessions, an exam and a deadline, placed around today.

- Tasks with a date such as `📅 2026-10-27` can become reminders when you allow it in Settings.
- Study blocks are suggestions: you approve each one before anything is written.
- Without calendar access nothing is read and nothing is sent anywhere.

Open tasks with dates: [[Garden planner]], [[Study plan October]], [[Bike repair log]].
""", tags=["reference", "calendar"])
    return m


# ------------------------------------------------------------------ daily notes

NAPI_FELADATOK = [
    ("Review the cards that are due", None), ("Take a short quiz", "Active recall"),
    ("Read a chapter", "Reading overview"), ("Solve three equations", "Quadratic equations"),
    ("Write a summary note", "Atomic notes"), ("Practise one coding task", "Programming glossary"),
    ("Tidy the ideas inbox", "Ideas inbox"), ("Plan tomorrow", "Weekly review"),
    ("Watch the garden beds", "Garden planner"), ("Repair something small", "Bike repair log"),
]
NAPI_TEMAK = ["Geometric series", "Arithmetic series", "Newton's laws", "Kinematics", "Quadratic equations", "Derivative rules",
              "Water cycle", "Binary search (Python)", "Spaced repetition", "Orbits and gravity", "Photosynthesis", "Waves"]
NAPI_MEGJEGYZESEK = ["A calm session.", "Harder than expected, but it clicked at the end.", "Short day, kept the streak.",
                     "Good focus after the break.", "Distracted early, better in the afternoon.", "Finished what I planned."]
NAPOK = 14


def _napi(seed: int) -> dict[str, str]:
    rnd = random.Random(f"daily-{seed}")
    elso = dt.date(2026, 10, 1)
    napok = [elso + dt.timedelta(days=i) for i in range(NAPOK)]
    m = {}
    for i, nap in enumerate(napok):
        cim = nap.isoformat()
        elozo = f"[[{napok[i - 1].isoformat()}]]" if i else "-"
        kovetkezo = f"[[{napok[i + 1].isoformat()}]]" if i + 1 < NAPOK else "-"
        feladatok = rnd.sample(NAPI_FELADATOK, 3)
        temak = rnd.sample(NAPI_TEMAK, 2)
        kesz = nap < napok[-1] and nap.weekday() < 5
        sorok = [f"{elozo} | {kovetkezo}", "", "## Plan", ""]
        for j, (szoveg, link) in enumerate(feladatok):
            doboz = "x" if (kesz and j < 2) or (nap < napok[-3] and j == 2) else " "
            sorok.append(f"- [{doboz}] {szoveg}" + (f" ([[{link}]])" if link else ""))
        sorok += ["", "## Log", "", f"Studied [[{temak[0]}]] and [[{temak[1]}]]. {rnd.choice(NAPI_MEGJEGYZESEK)}"]
        if nap.weekday() == 3:
            sorok += ["", "Study group met today, see [[Meeting - Study group kickoff]]."]
        if nap == napok[-1]:
            sorok += ["", "Tomorrow: finish the [[Study plan October]] week 2 items."]
        m[f"Daily/{cim}.md"] = _jegyzet(cim, "\n".join(sorok), date=cim, focus=rnd.randint(3, 5), mood=rnd.choice(["calm", "tired", "good", "focused"]),
                                        tags=["daily"])
    return m


# ------------------------------------------------------------------ templates

def _sablonok() -> dict[str, str]:
    return {
        "_Template/Meeting.md": "---\ndate: {{date}}\ntags:\n  - meeting\n---\n\n# {{title}}\n\nAttendees:\n\n## Decisions\n\n## Actions\n\n- [ ] \n",
        "_Template/Book.md": "---\ntype: book\nauthor:\nyear:\npages:\nstatus: planned\nrating:\ntags:\n  - book\n---\n\n# {{title}}\n\n",
    }


def jegyzetek(seed: int) -> dict[str, str]:
    """Every plain note of the demo library (without the task notes, cards, quizzes and PDF highlights, which
    `demo_tanulas` builds because they embed files)."""
    m: dict[str, str] = {}
    for resz in (_hub(), _matek(), _termeszettudomany(), _programozas(), _tanulas(), _olvasas(), _projektek(), _referencia(),
                 _napi(seed), _sablonok()):
        m.update(resz)
    return m
