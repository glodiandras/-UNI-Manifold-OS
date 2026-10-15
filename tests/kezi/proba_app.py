"""C08 kézi próbakörnyezet: a felület a vault APFS-klónján, elkülönített állapottal (a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/proba_app.py core       # a core a klónon; a címét kiírja (böngésző)
    var/venv/bin/python -B tests/kezi/proba_app.py app        # a valódi Manifold.app a klónon (WKWebView)
    … --megtart                                               # a próbamappa nem törlődik a végén

Figyelmeztetések (C34): ha a gyermek környezetének bármely útja a VALÓDIRA mutatna (vault, `{backup}`, …), vagy a valódi
vaulton már fut egy Manifold-példány, a szkript `[próba] FIGYELEM:` sort ír ki; az `app` mód ablakának címsora
„PRÓBA — Manifold (klón)” (a héj a `MOS_PROBA_JELZES` változót olvassa), így a klónos és a valódi példány nem keverhető össze.

A szerkesztő automatikusan ment, ezért a felületet a valódi vaulton nem próbáljuk ki: minden írás a
`{tmp}/c08-proba-<idő>/` alatti klónba megy. Elkülönítve (`_kornyezet.elkulonit`): a vault és a `vault.git` (klón), és az `os.toml` MINDEN
más `[utak]` kulcsa a klón mappájába (index, állapot, zárak, futásnaplók, feladatsor, személyes adat, mentés, ytdlp,
naptár-segéd); a modellzár a valódi (L23). A klónba két próbajegyzet kerül
(`Manifold-proba/`):
  - „5000 sor — képletek.md”: a vault legtöbb képletet tartalmazó jegyzetei összefűzve, legalább 5000 sorig
    (a gépelési késleltetés kapuja);
  - „Bemutató.md”: minden elem, amit a szerkesztő kirajzol (callout, Mermaid, lábjegyzet, táblázat, kód …);
  - „Link-próba.md” + „Link-próba cél.md” + a két körkörös jegyzet (C10): minden link- és beágyazás-alak;
  - „Külső-link-próba.md” (C11a): Markdown-link, autolink, csupasz URL, mailto, tiltott séma, nagy fotó;
  - „Tulajdonság-próba.md”, „Címke-próba A.md”, „Címke-próba B.md” és „borito-proba.png” (C11b): minden mezőtípus,
    séma-sértés (`icon`, `cover`, értékkészleten kívüli címke), egymásba ágyazott címkék, és egy borítókép;
  - „Canvas-próba.canvas” (C14): mind a négy node-típus (szöveg, jegyzet, kép, link), csoport címkével, élek
    címkével, iránnyal és színnel (preset és hex) — a vault canvasaiban szöveg- és link-kártya nincs —, és
    „Canvas-beágyazás-próba.md” (a `![[…canvas]]` kép);
  - „Grafikon-próba.md” (C35a): a ```plot blokk minden elemfajtája, aszimptoták, értelmezési tartomány széle,
    paraméteres görbe, egyenlőtlenség, hibás és üres blokk — a K104 lista pontjaihoz;
  - „Notion-próba.md” (C09): listák, számozott lista, táblázat, callout, kód — a / menü, a blokkfogó, az
    eszköztár és a táblázatszerkesztő próbájához.
A futás a core vagy az app kilépéséig tart (SIGTERM/SIGINT/SIGHUP vagy a core/app kilépése; nyitott stdin nem
kell); utána a próbamappa törlődik (saját `var/tmp`), `--megtart` esetén marad, és a doctor jelzi.
"""
import json
import shutil
import signal
import sqlite3
import subprocess
import time
import os
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame  # noqa: E402
from _kornyezet import PROBA_JELZES, TITOK, elkulonit, proba_figyelmeztetesek, probamappa  # noqa: E402

PROBA_MAPPA = "Manifold-proba"

TULAJDONSAG = """---
Tags:
  - Mathematics
  - Physics
Source:
  - "[[Link-próba cél]]"
Status: In progress
NN:
  - "[[Link-próba]]"
Canvas:
Pont: 3
Határidő: 2026-10-30
Időpont: 2026-10-30T09:30
Kész: false
Megjegyzés: "Idézőjeles: érték"
icon: 📘
cover: "[[borito-proba.png]]"
---

# Tulajdonság-próba

A jegyzet frontmatterét a panel szerkeszti: szöveg, szám, dátum, jelölő, lista, link; a séma szerinti Status; a séma
sérülése (új kulcs, értékkészleten kívüli címke) figyelmeztetést ad, és csak „Mégis beírom” után kerül be.

Címkék a törzsben: #Fizika/Mechanika #Matek/Algebra
"""

CIMKE_A = """---
Tags:
  - Fizika/Mechanika/Newton
  - Fizika/Mechanika
---

# Címke-próba A

Törzs-címke: #Fizika/Optika
"""

CIMKE_B = """---
Tags: Fizika/Mechanika
---

# Címke-próba B

#Matek
"""

BEMUTATO = r"""---
Tags:
  - proba
Source: C08
Status:
---
# Bemutató — a szerkesztő elemei

Ez a jegyzet a **C08** próbája: *dőlt*, **félkövér**, ~~áthúzott~~, ==kiemelés==, `kód`, és egy lábjegyzet[^1].
Képlet a sorban: $f(x) = \tg x + 3{,}14$, és egy megjelenítési képlet:

$$
\int_0^1 x^2 \, dx = \frac{1}{3} \qquad K_\max = 840\ \mathrm{N}
$$

## Listák és feladatok

- első elem
- második elem, benne $a_n = a_1 \cdot q^{n-1}$
	- behúzott elem
1. számozott
2. lista

- [ ] nyitott feladat
- [x] kész feladat
- [/] folyamatban (Tasks-állapot)

## Idézet és callout

> Sima idézet, két sorban,
> a második sor.

> [!note] Megjegyzés címmel
> A callout törzse **formázással** és képlettel: $\sqrt{2}$.

> [!warning]- Összecsukott figyelmeztetés
> Ez a törzs alapból rejtve van.

> [!tip]+
> Nyitott, összecsukható, cím nélkül (az alapcím látszik).

## Kód

```python
def mertani(a1: float, q: float, n: int) -> float:
    # a mértani sorozat n-edik tagja
    return a1 * q ** (n - 1)
```

```bash
bin/mos app build
```

## Mermaid

```mermaid
flowchart LR
    A[Jegyzet] --> B{Live Preview?}
    B -- igen --> C[Kirajzolt elemek]
    B -- nem --> D[Forrás]
```

## Táblázat

| Egyenlet | Megoldás | Jegyzet |
|:---|:---:|---:|
| $|A| = 0$ | $A = 0$ | egy eset |
| $|A| = c > 0$ | $A = \pm c$ | két eset |

---

H<sub>2</sub>O és x<sup>2</sup>; a `<script>` szövegként marad.

[^1]: A lábjegyzet szövege, a lap alján.
"""


GRAFIKON = r"""# Grafikon-próba (C35a)

Minden elemfajta; a K104 lista pontjai ezen mennek végig. Alatta egy hibás, egy részben hibás és egy üres blokk.

Másodfokú, zérushely, csúcs (CAS-jelölők), címkével:

```plot
x in [-4, 4]
y in [-6, 12]
y = x^2 - 4 "f(x) = x² − 4"
y = 2x + 1 "g(x) = 2x + 1"
pont (1, -3) "P"
```

Aszimptoták: törtfüggvény és tangens (2π tartomány):

```plot
y = (x^2 - 1)/(x - 2) "racionális"
```

```plot
x in [-2*pi, 2*pi]
y in [-4, 4]
y = tan(x)
y = sin(x) "sin"
```

Logaritmus és gyök (az értelmezési tartomány széle):

```plot
y = log(x, 2) "log₂ x"
y = sqrt(x) "√x"
y = root(x,3) "∛x"
```

Paraméteres görbe és egyenlőtlenség-tartomány:

```plot
x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi] "ellipszis"
```

```plot
x in [-4, 4]
y in [-2, 8]
y > x^2 - 1 "fölötte"
y <= 2x + 3
```

Részben hibás (a második sor kimarad, halk figyelmeztetés):

```plot
y = x^2
valami ismeretlen
y = sin x
```

Teljesen hibás:

```plot
y = sin x
y = foo(x)
```

Üres:

```plot
```
"""

NOTION = r"""# Notion-réteg próbája

Első bekezdés, amelyet mozgatni lehet.
Második sora ugyanannak a bekezdésnek.

## Lista

- első elem
	- gyerek A
	- gyerek B
- második elem
- harmadik elem ^treti

1. alma
2. körte
3. szilva

- [ ] nyitott feladat
- [x] kész feladat

## Táblázat

| Név | Érték | Jegyzet |
|:---|---:|:---:|
| alma | 5 | piros |
| $|A|$ | 3 | képlet |
| körte | | üres cella |

> [!tip] Tipp
> A callout törzse.

> [!note]- Összecsukható
> Rejtett törzs.

Zárószöveg, itt lehet kipróbálni a lebegő eszköztárat: jelölj ki szavakat.

```python
print("kód")
```

Utolsó bekezdés.
"""


LINK_PROBA = r"""# Link-próba

Wikilink: [[Link-próba cél]], alias: [[Link-próba cél|a cél jegyzet]], fejezet: [[Link-próba cél#Cél fejezet]], blokk: [[Link-próba cél#^celblokk]], hiányzó: [[Ez még nincs meg]].
Gépelj ide `[[` -t: fájl-, `#`-fejezet-, `#^`-blokk-, `|`-alias-kiegészítés. ⌘ + rámutatás: előnézet.

## Első rész
Egy bekezdés, amelyre blokklink mutathat. ^elso

## Beágyazások

Kép (méretezve):

![[Az antikvitás korszakai.jpg|400]]

PDF, a 3. oldal:

![[emelt matematika témakörök.pdf#page=3]]

Videó, az 1:30-tól:

![[Arany János életműve, epikus költészete.mp4#t=90]]

Jegyzet, fejezet és blokk:

![[Link-próba cél]]

![[Link-próba cél#Cél fejezet]]

![[Link-próba cél#^celblokk]]

Körkörös beágyazás (A → B → A) és hiányzó cél:

![[Link-próba körkörös A]]

![[Nincs ilyen jegyzet]]

## Említések

A Link-próba cél szó itt link nélkül áll, és a Cél-alias is.
"""

LINK_CEL = r"""---
aliases:
  - Cél-alias
---
# Link-próba cél

Bevezető szöveg.

## Cél fejezet
Ez a fejezet szövege, benne egy képlet: $x^2 + y^2 = r^2$.

- Ez egy blokk ^celblokk
  - gyerek elem
"""

LINK_A = "# Körkörös A\n\nA tartalma.\n\n![[Link-próba körkörös B]]\n"
LINK_B = "# Körkörös B\n\nB tartalma.\n\n![[Link-próba körkörös A]]\n"

KULSO = """# Külső link próba

Markdown-link: [Példa oldal](https://example.com/pelda?x=1#y) és egy csupasz cím: https://example.org/csupasz.

Autolink: <https://example.net/auto> és levél: [írj nekünk](mailto:pelda@example.com).

Tiltott vagy belső (nem nyílhat meg): [rossz](javascript:alert(1)), [fájl](file:///etc/passwd), [belső](Link-próba cél.md).

Kép a vaultból (kicsinyített, kattintásra az eredeti): ![[IMG_1336.JPG]]
"""


def otezer_sor(vault: Path, index_db: Path, cel: Path) -> int:
    """Az index szerint legtöbb képletet tartalmazó jegyzetek (M és F tárgyak) összefűzve, ≥ 5000 sorig."""
    c = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        sorok = c.execute(
            "select f.lemez_ut, count(*) n from keplet k join fajl f on f.id = k.fajl_id "
            "where f.torolve is null and (f.ut like 'M%' or f.ut like 'F%') group by f.id order by n desc").fetchall()
    finally:
        c.close()
    reszek, n = [], 0
    for lemez_ut, _ in sorok:
        p = vault / lemez_ut
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        if t.startswith("---\n"):                     # a frontmatter csak az elején lehet
            veg = t.find("\n---", 4)
            t = t[veg + 4:].lstrip("\n") if veg > 0 else t
        reszek.append(f"\n\n<!-- {lemez_ut} -->\n\n{t.strip()}\n")
        n += t.count("\n") + 4
        if n >= 5000:
            break
    szoveg = "# 5000 sor — képletek\n" + "".join(reszek)
    cel.write_text(szoveg, encoding="utf-8")
    return szoveg.count("\n") + 1


CANVAS_PROBA = {
    "nodes": [
        {"id": "c14csoport000001", "type": "group", "x": -60, "y": -80, "width": 1040, "height": 560, "color": "4",
         "label": "Próbacsoport"},
        {"id": "c14szoveg0000001", "type": "text", "text": "# Szövegkártya\n\nA **canvas** kártyája: $a^2 + b^2 = c^2$, "
         "link: [[Link-próba cél]], és egy lista:\n- első\n- második", "x": 0, "y": 0, "width": 400, "height": 260},
        {"id": "c14jegyzet000001", "type": "file", "file": "Manifold-proba/Link-próba cél.md", "x": 520, "y": 0,
         "width": 400, "height": 400, "color": "1"},
        {"id": "c14kep0000000001", "type": "file", "file": "Manifold-proba/borito-proba.png", "x": 0, "y": 600,
         "width": 480, "height": 120},
        {"id": "c14link000000001", "type": "link", "url": "https://jsoncanvas.org/spec/1.0/", "x": 600, "y": 600,
         "width": 400, "height": 120, "color": "#5a56d6"},
        {"id": "c14szoveg0000002", "type": "text", "text": "Sárga kártya, **félkövér**.", "x": 0, "y": 300,
         "width": 400, "height": 100, "color": "3"},
    ],
    "edges": [
        {"id": "c14el00000000001", "fromNode": "c14szoveg0000001", "fromSide": "right", "toNode": "c14jegyzet000001",
         "toSide": "left", "label": "hivatkozik"},
        {"id": "c14el00000000002", "fromNode": "c14szoveg0000002", "fromSide": "bottom", "toNode": "c14kep0000000001",
         "toSide": "top", "color": "2", "toEnd": "none"},
        {"id": "c14el00000000003", "fromNode": "c14jegyzet000001", "fromSide": "bottom", "toNode": "c14link000000001",
         "toSide": "top", "fromEnd": "arrow", "color": "5", "label": "mindkét irányba"},
    ],
}


def obsidian_canvas(v: dict) -> str:
    """A canvas az Obsidian írásmódjában (tabbal behúzott gyökér, egysoros elemek, záró sorvég nélkül)."""
    tomb = lambda a: "[\n" + ",\n".join("\t\t" + json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in a) \
        + "\n\t]" if a else "[]"  # noqa: E731
    return '{\n\t"nodes":' + tomb(v["nodes"]) + ',\n\t"edges":' + tomb(v["edges"]) + "\n}"


def borito(cel: Path) -> None:
    """A C11b borítókép-próbája: egy 1200×300-as színátmenet (Pillow, a venvben van)."""
    from PIL import Image
    kep = Image.new("RGB", (1200, 300))
    for x in range(1200):
        for y in range(0, 300, 1):
            kep.putpixel((x, y), (90 + x // 12, 86 + y // 5, 214 - x // 10))
    kep.save(cel)


def _var(p: subprocess.Popen, lezar, rendezett_mp: float = 60, terminate_mp: float = 15) -> None:
    """A gyermek kilépéséig vár. SIGTERM, SIGINT és SIGHUP: rendezett leállítás (core: a stdin lezárása, a kilépési mentés
    a klón mappájába megy; app: `terminate`), `rendezett_mp` után `terminate`, majd `kill`. Nyitott stdin (`tail -f
    /dev/null |`) nem kell, és a háttérből indítva örökölten ignorált SIGINT is működik, mert mindhármat kifejezetten
    telepítjük (T081)."""
    jel = threading.Event()
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, lambda *_: jel.set())
    while p.poll() is None and not jel.is_set():
        try:
            p.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
    if p.poll() is None:
        lezar()
        try:
            p.wait(timeout=rendezett_mp)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(timeout=terminate_mp)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


def _klon_folyamatok_vege(d: Path, max_mp: float = 90) -> None:
    """Megvárja, hogy a klón mappájára (`MOS_VAR=…`) állított gyermekfolyamatok (az app alatt indult core és a workere)
    kilépjenek, legfeljebb `max_mp`-ig: a héj kilépése után a core kilépési mentése még a klón `backup/`-jába ír, és a
    törlés után maradékot hagyna (Kézi kör 3). A környezetet a `ps -E` adja (saját felhasználó); ha nem elérhető, nem vár."""
    minta = f"={d}"
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_mp:
        try:
            ki = subprocess.run(["ps", "-axE", "-o", "pid=,command="], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return
        sorok = [so for so in ki.splitlines() if minta in so and " ps " not in so and not so.strip().startswith(str(os.getpid()))]
        if not sorok:
            return
        time.sleep(0.5)
    print(f"[próba] FIGYELEM: a klón folyamatai {max_mp:.0f} s után is futnak; a próbamappa törlése maradékot hagyhat", flush=True)


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("core", "app") or any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)                                     # Kézi kör 3: a `--help` sem indít appot
        return 2
    mod, megtart = sys.argv[1], "--megtart" in sys.argv
    cfg = config.load()
    d = probamappa(cfg, "c08-proba", megtart=megtart, szkript="proba_app.py")
    vault, git = frame.trial_clone(cfg, d)
    (vault / PROBA_MAPPA).mkdir()
    sorok = otezer_sor(vault, cfg.path("index") / "vault.sqlite", vault / PROBA_MAPPA / "5000 sor — képletek.md")
    (vault / PROBA_MAPPA / "Bemutató.md").write_text(BEMUTATO.lstrip("\n"), encoding="utf-8")
    (vault / PROBA_MAPPA / "Notion-próba.md").write_text(NOTION.lstrip("\n"), encoding="utf-8")
    (vault / PROBA_MAPPA / "Grafikon-próba.md").write_text(GRAFIKON.lstrip("\n"), encoding="utf-8")        # C35a
    (vault / PROBA_MAPPA / "Külső-link-próba.md").write_text(KULSO, encoding="utf-8")                # C11a
    for nev, tartalom in (("Link-próba.md", LINK_PROBA), ("Link-próba cél.md", LINK_CEL),
                          ("Link-próba körkörös A.md", LINK_A), ("Link-próba körkörös B.md", LINK_B)):
        (vault / PROBA_MAPPA / nev).write_text(tartalom.lstrip("\n"), encoding="utf-8")   # C10
    for nev, tartalom in (("Tulajdonság-próba.md", TULAJDONSAG), ("Címke-próba A.md", CIMKE_A),
                          ("Címke-próba B.md", CIMKE_B)):
        (vault / PROBA_MAPPA / nev).write_text(tartalom.lstrip("\n"), encoding="utf-8")                # C11b
    borito(vault / PROBA_MAPPA / "borito-proba.png")
    (vault / PROBA_MAPPA / "Canvas-próba.canvas").write_text(obsidian_canvas(CANVAS_PROBA), encoding="utf-8")  # C14
    (vault / PROBA_MAPPA / "Canvas-beágyazás-próba.md").write_text(
        "# Canvas-beágyazás\n\nA próba-canvas kicsinyített képe:\n\n![[Canvas-próba.canvas]]\n", encoding="utf-8")
    # minden [utak] kulcs a klón mappájába (a kilépési mentés is, a tracker és a kapcsolók is), a modellzár a valódi
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=(mod == "core"))
    for figy in proba_figyelmeztetesek(env, cfg):            # C34: valódi {backup}/vault vagy már futó valódi példány
        print(f"[próba] FIGYELEM: {figy}", flush=True)
    if mod == "app":
        env[PROBA_JELZES] = "klón"                          # a héj ablakának címsora: „PRÓBA — Manifold (klón)”
    print(f"[próba] klón: {d}  ·  5000 soros jegyzet: {sorok} sor", flush=True)
    try:
        if mod == "core":
            p = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, env=env)
            port = json.loads(p.stdout.readline())["port"]
            print(f"[próba] core: http://127.0.0.1:{port}/#titok={TITOK}  (a töredéket a felület egyszer olvassa és törli; a Browser panebe így nyisd)", flush=True)
            (d / "port").write_text(str(port))
            _var(p, lezar=lambda: p.stdin.close())
        else:
            app = REPO / "Manifold.app" / "Contents" / "MacOS" / "Manifold"
            p = subprocess.Popen([str(app)], env=env)
            print(f"[próba] app: pid {p.pid} — az ablak címsora „PRÓBA — Manifold (klón)” · kilépés: ⌘Q", flush=True)
            _var(p, lezar=p.terminate)
    finally:
        if not megtart:
            _klon_folyamatok_vege(d)                       # Kézi kör 3: az app kilépése után a core kilépési mentése még ír
            shutil.rmtree(d, ignore_errors=True)
            print("[próba] a próbamappa törölve", flush=True)
        else:
            print(f"[próba] a próbamappa megmaradt (--megtart): {d} — törlése csak a felhasználó igenjével "
                  "(a doctor jelzi a megtartott klónokat)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
