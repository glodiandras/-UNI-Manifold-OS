# A ```plot blokk formátuma (C35a)

A jegyzetbe a képlet alá kerülő, olvasható és kézzel szerkeszthető kódblokk (CLAUDE.md 5. döntés). Obsidianban sima kódblokk, a Manifold interaktív grafikont rajzol belőle (C35b, JSXGraph). A formátum **csak adat**: a kifejezést nem értékeli ki, nincs benne kód és nincs YAML-fejléc. A kód: `core/plot/formatum.py` (elemző, szerializáló, a jegyzetből kivágó), `core/plot/felismeres.py` (felismerés), `core/plot/meres.py` (mérés).

## Példa

````
```plot
x in [-4, 4]
y in [-2, 10]
y = x^2 + 2  "f"
y = sin(2*x)
x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]
y >= x^2 - 1
pont (2, 1) "minimum"
# megjegyzés
```
````

## Sorok

| Sor | Jelentés |
|---|---|
| `x in [a, b]`, `y in [a, b]` | a látható tartomány; elhagyható (a renderelő automatikusan választ). Mindkettő legfeljebb egyszer. |
| `y = kifejezés` `["címke"]` | függvény, `y` az `x` függvénye |
| `x = kif(t), y = kif(t), t in [a, b]` `["címke"]` | paraméteres görbe; a paraméter egy betű (a kanonikus alak `t`) |
| `y < kif`, `y <= kif`, `y > kif`, `y >= kif` `["címke"]` | egyenlőtlenség-tartomány az `y = kif` görbe fölött/alatt |
| `pont (x, y)` `["címke"]` | kiemelt pont |
| `# szöveg` | megjegyzés (egész sor) |

- **A kifejezés jelölése** az `modulok/eval/kozos/matek.elemez` jelölése: `+ - * / ^`, `sqrt()`, `abs()`, `exp()`, `ln()`, `log(x, 2)`, `sin() cos() tan()…`, `pi`, `e`; az implicit szorzás (`2x`) megengedett. Ugyanez a nyelv az aranyhalmaz `kifejezes` mezője, így a renderelő (C35b) és a mérés egyet használ.
- A **címke** idézőjeles; belül `\"` és `\\` a feloldójel. A karakterosztály (`CIMKE`: `\s+"((?:[^"\\]|\\.)*)"\s*$`) a Python- és a TypeScript-oldalon azonos, és **bármit** elfogad, a HTML-jelet is (`<`, `>`, `&`): a címke **szöveg**, sosem jelölés. Ezt a közös `forras.json` vektorok őrzik (A3-14).
- Az **állandók** zárt listája: `pi` és `e`. Más név (köztük a `constructor`, `toString`, `valueOf` és társai) ismeretlen név, hibát ad mindkét oldalon; a felület az állandókat `Map`-ben keresi, nem sima objektumban (A3-29; közös vektor: `hibas_mindketto`).
- A tartomány-határ szám vagy konstans-kifejezés (`-2*pi`).
- **Ismeretlen vagy hibás sor** hibát nem okoz: az elemző megőrzi (`Ismeretlen`), a renderelő kihagyja, a `hibak` jelzi a sor számát. Ezért marad a kézi szerkesztés biztonságos.
- **Plafonok** (a renderelőnek ne jusson óriási bemenet): legfeljebb 64 rajzelem, 2000 jel soronként, 100 000 jel blokkonként; ami túllóg, `Ismeretlen`.
- A **sorvégi `# …` megjegyzés** elemzéskor eltűnik a kanonikus alakból (a teljes soros megjegyzés megmarad). A gép a kézzel írt blokkot nem írja át: csak új blokkot szúr be (C35b).

## A feliratok megjelenítése (A3-14, 2026-10-05)

A feliratok — a felhasználó `"…"` címkéje és a CAS-szövegű jelölők (zérushely, szélsőérték, aszimptota, érintő) — a rajzban
**szövegként** jelennek meg, sosem HTML-ként. A JSXGraph szövegének alapja `display: 'html'` (`innerHTML`) és `parse: true`
(a szöveg értelmezése, `<value>`-címkék, JessieCode); a rajzoló (`plot/rajzolo.ts`) ezért (1) a lusta import után, a táblák
előtt zárja a globális alapot (`JXG.Options.text.parse = false`, `text.display = 'internal'`, `jc.enabled = false`:
`biztonsagosit`), és (2) minden pont-, vonal- és tengelycímkének megadja a `display: 'internal'`, `parse: false` párt
(`FELIRAT_ATTR`). A CSP változatlan (`script-src 'self'` a szkriptet fogja meg, a `style-src 'unsafe-inline'` miatt a DOM-befecskendezés —
átfedés, hamis párbeszédablak — ellen ez a védelem kell, főként azért, mert a C35b a blokkot modellkimenetből is írja).
Őr: `app/tests/plot-xss.test.ts` (valódi JSXGraph jsdom alatt: a `<img …>` és `<a …>` felirat sehol nem hoz létre elemet).

## API (`core/plot/formatum.py`)

- `elemez(szöveg) -> Abra` (`x_tartomany`, `y_tartomany`, `elemek`, `hibak`); az elemek: `Fuggveny`, `Parameteres`, `Egyenlotlenseg`, `Pont`, `Megjegyzes`, `Ismeretlen`.
- `szerializal(abra) -> str`: kanonikus alak (előbb `x`, `y` tartomány, aztán az elemek a megadott sorrendben, záró újsor nélkül); `blokk(abra) -> str`: kerítéssel és záró újsorral.
- `blokkok(jegyzet) -> list[BlokkHely]`: a jegyzet plot-blokkjai karakter- és sorhellyel, lezártság-jelzéssel. **Kódmaszk**: a más kódblokkban (akár hosszabb kerítésben) álló példa és a frontmatter nem számít (13. döntés).
- **Körút**: `szerializal(elemez(s))` fixpont, és `elemez(szerializal(a)) == a` (tesztelve véletlen ábrákra).

## Felismerés (`core/plot/felismeres.py`)

`felismer(képlet) -> Javaslat` és `felismer_jegyzet(szöveg) -> list[Javaslat]` (jegyzetbeli sorral, `blokk_kovetkezik` jelzéssel). A `Javaslat`: `fajta`, `bizonyossag`, `ok` (mindig kitöltött, magyarul), `abra`, `blokk`, `kulcs`.

| Forma | Fajta | Megjegyzés |
|---|---|---|
| `y = …`, `f(x) = …`, `g(t) = …` | `fuggveny` | a deklarált változó `x`-re nevezve; több függvény egy képletben (`f(x)=…, g(x)=…`) |
| `x = …, y = …, t ∈ [a, b]`, `x(t)=…, y(t)=…`, `a ≤ t ≤ b` | `parameteres` | tartomány nélkül bizonytalan |
| `y ≥ …`, `y < …`, `x² ≤ y` | `egyenlotlenseg` | y-ra rendezett, egyoldali; a fordított alak megfordul |
| `\addplot[domain=a:b]{…}`, `\addplot … ({…},{…})`, `\draw plot (\x,{…})` | `tikz` | a pgfplots `domain`, `xmin/xmax/ymin/ymax`, `variable`, `\addlegendentry` |

**Bizonyosság.** `biztos`: a rajzolandó kifejezés egyértelmű, hibátlanul elemezhető, és az ablakon belül nincs szakadás. `bizonytalan`: kimondja az okot, és a döntés a modell-ágra (C35b) marad. `nincs`: nem grafikon-alapanyag (szám-egyenlet, azonosság, `f(2)=5`, `f'(x)=…`, `x = 3`, kifejezés egyenlőség nélkül). Elv: **a bizonytalan jobb, mint a téves**; a kapu: biztosan rossz javaslat 0.

**Bizonytalan okok:** szakadás vagy aszimptota az ablakon (a CAS-os ellenőrzés C35b), konstans jobb oldal (`y = 3` egyenlet megoldása is lehet), egyenlőség-lánc, paraméter a kifejezésben (`y = ax + b`: csúszka nincs), implicit görbe (`x² + y² = 1`), szakaszonkénti definíció (`cases`), ismeretlen függvény vagy változó, nem értelmezett kiegészítés a képlet mellett, hiányzó paraméter-tartomány, a pgfplots fokban számolt trigonometriája (`sin(x)` `deg()` nélkül), adatpontokból álló görbe (nincs javaslat).

**Ablak-heurisztika** (determinisztikus, a képletből és mintavételből, 401 pont):
1. Ha a képlet megadja (`x ∈ [a, b]`, `a ≤ x ≤ b`, `x > a`: `[a, a+10]`, `x < b`: `[b-10, b]`; pgfplotsban `domain`, `xmin/xmax`), az az x-ablak.
2. Különben alap `[-5, 5]`, trigonometrikus függvénynél `[-2π, 2π]`; ha a függvény az ablak szélén nem értelmezett (`sqrt`, `log`), az értelmezési tartomány széléig szűkül (felezéssel keresve, 6 tizedesig).
3. Az y-ablak a mintavételezett értékek terjedelme + 8% margó, „szép” (1/2/5·10ᵏ) lépcsőre kerekítve; ha egy-két szélsőséges érték (a tartomány széle) tízszeresére nyújtaná, az 1.–99. percentilis.
4. Belső lyuk (nem értelmezett pont az ablak közepén) vagy pólus-gyanú (szomszédos, ellentétes előjelű, a mediánnál 20×-osan nagyobb értékek) → bizonytalan.
5. Paraméteres görbénél a hiányzó tartomány `[0, 2*pi]` (és bizonytalan); a pgfplots hiányzó `domain`-je `[-5, 5]` (a pgfplots alapja).

A felismerő **zérushelyet, szélsőértéket, aszimptotát nem számol** (a C24 CAS-homokozójából jön, C35b), kiemelt pontot nem ír, a vaultba nem ír, modellt nem tölt, hálózatot nem hív.

## Mérés (C35a, 2026-10-04)

`var/venv/bin/python -m core.plot.meres`. A C18 `grafikon` aranyhalmaza (15 képlet): **15/15 biztos és helyes** (a kifejezés a `kozos.matek.kifejezes_egyezik` szerint egyezik, a blokk körútja azonos, a javasolt x-ablak tartalmazza a várt zérushelyeket és szélsőérték-helyeket), 0 biztosan rossz, 0 bizonytalan. Az aranyhalmaz csak `y=`/`f(x)=` alakú függvényeket tartalmaz, ezért egy 36 tételes szintetikus kiegészítő halmaz (`core/plot/meres.py`: paraméteres, egyenlőtlenség, TikZ/pgfplots, szándékosan bizonytalan és nem grafikon-alapanyag tételek): 20 biztos és helyes, 9 helyesen bizonytalan, 7 helyesen „nincs”, **0 téves**. A kiegészítő halmaz a felismerő írója által készült, nem jóváhagyott aranyhalmaz (K27 nem érinti): a 0 téves állítás ennek a halmaznak szól, nem valós jegyzetek gyakoriságának; a valós vault-mintán a mérés a C35b/C31 dolga.

## A tiltólista helye (5. döntés: a törölt blokk képlete nem kap újat)

Építés: **C35b-mag** (2026-10-05; `core/plot_allapot.py`, `modulok/grafikon/tiltolista.py`); a hely és a kulcs itt rögzített, a működés a lenti „Automatikus beírás” szakaszban.

- **Hely**: `{state}/plot-tiltolista.json` (a core állapotfájlja; a `state/*.json` a 33. döntés szerint a belső mentésben van). A **vaultba semmi nem kerül**, hogy az Obsidian-tisztaság megmaradjon.
- **Kulcs**: `Javaslat.kulcs` = `sha1(latex.normalizal(képlet))[:16]`, **jegyzet-úttól független**, így az átnevezés vagy az áthelyezés nem támasztja fel a tiltott képletet; a rekord tartalmazza az utat is (megjelenítéshez), a kulcs nem. Az írásmód-különbség (`\dfrac`/`\frac`, szóköz) nem számít (`normalizal`).
- **Mikor kerül fel**: ha a gép által beírt blokk (a `Mos-Forras: mos-plot` gépi commit szerint, nem a szöveg alapján) a képlet alól eltűnik a jegyzetből, és a változás nem visszavonás (a visszavonás nem tiltólistáz). A törlés felismerése: a gép minden beírását egy napló (`{state}/plot-beirasok.json`) jegyzi (jegyzet-út, képlet-kulcs, a blokk kanonikus törzse, a gépi commit sha-ja); a felismerés a **napló és a jegyzet mostani szövege** különbségéből megy, a visszavonást a pillanatkép-napló `Mos-Visszavon` trailere jelzi. A felhasználó által kézzel beírt blokk a gépet nem érinti.
- **Visszaút**: a tiltólistáról a vezérlő API-ján át vehető le (`GET /api/grafikon/tiltolista`, `POST /api/grafikon/tiltolista/levesz {kulcs}`; a felület a C35b modell-felével épül); a `felismer_jegyzet` a kulcsot adja, a szűrést a `beiras.terv` végzi.
- **Beszúrás horgonya**: a blokk a képlet **utáni** sor(ok)ba kerül; a `Javaslat.sor`/`veg_sor` és a `blokk_kovetkezik` ehhez adja az adatot (ha a képlet alatt 3 soron belül már van plot blokk, a gép nem szúr be másikat). A C16.5 `csere` + alap-hash útja vagy egy új `beszuras`-horgony művelet a C35b döntése (T151).

## Automatikus beírás (C35b-mag, 2026-10-05)

A kód: `modulok/grafikon/beiras.py` (terv, beszúrás, beíró, törlés-felismerés), `tiltolista.py` (döntések), `automatika.py` (mikor és melyik
jegyzet), `modell_ag.py` (hívható mögötti modell-ág), `core/plot_allapot.py` (az állapotfájlok), `core/grafikon_feladat.py` (a feladattípus).

- **Írás**: egyedül a gépi-írás szolgáltatáson át (`core/gepi_kliens.py`, 28. döntés): jegyzetenként **egy `csere` művelet alap-hash-sel = egy tétel =
  egy gépi commit** (`Mos-Forras: mos-plot`, kör `PLOT-…`), a jegyzet összes új blokkja együtt. Nyitott, mentetlen dokumentumba nem ír (a kliens
  újrapróbál, utána `elhalasztva`); a közben megváltozott fájl `utkozes`; a `Status`-t és a frontmattert nem érinti.
- **Hely**: a blokk a képletet tartalmazó jelölés (`$…$`, `$$…$$`, `\(…\)`, `\[…\]`, ```` ```math ````) **után** áll, üres sorral elválasztva
  (`jegyzet.tarolo_veg_sor`: a `jeloltek` a képlet belsejét adja, ezért a többsoros `$$ … $$` záró jele utáni sor kell). Táblázat-, idézet-, lista-
  és behúzott sor alá, kódblokkba és frontmatterbe nem ír; sortörés-hű (CRLF).
- **Mit ír**: csak `biztos` felismerést, amelynek blokkja kanonikus, rajzol valamit, és egyezik a felismerő ábrájával; képletenként egyszer
  (azonos kulcsú ismétlődő képlet alá az elsőhöz), jegyzetenként legfeljebb 8-at; ha 3 soron belül már van plot blokk (kézi vagy gépi), nem ír másikat; a
  tiltólistás kulcs alá nem ír.
- **Tiltólista (5. döntés)**: a gép beírt blokkjának eltűnése (a képlet marad, alatta és máshol sincs ugyanilyen ábra) = törlés → a képlet kulcsa a
  tiltólistára. **Nem** törlés: a visszavonás, a kézi szerkesztés (más blokk áll ott), az áthelyezés, a képlet eltűnése, az átnevezés (a rekord marad).
  A sérült állapotfájl zárva hibázik (nem üres lista).
- **Automatikus mód**: `TaskType("grafikon_beiras", automatikus=True)` a `Kapu.admit` alatt (D8 indulási szünet, aktív használat, memória), az
  Asszisztens-kapcsoló alatt. **A döntés a C23b közös ütemezőjéé** (`core/automatika.py`, C35b/K309; a `modulok/grafikon/automatika.py` csak a `grafikon`
  fogyasztót adja): tartalmi jegyzet → **van képlet** (`tartalom_szuro`) → elég hosszú → **10 perce nem változott** → **új / erősen módosult / új képlet**
  (`kiegeszito`: az utoljára feldolgozott változat képletkulcsai a közös tár `adat` mezőjében) → nem készült még el (`mar_kesz`). A jelölt útjai a feladat
  `utak` paramétere (egy köteg legfeljebb `max_jegyzet`), a lépés tételhatáron áll meg. Feldolgozottnak (`Tar.kesz`) csak az számít, amit nem kell
  újrapróbálni (nem a nyitott dokumentum miatt elhalasztott, nem az ütközött, nem a modellre váró); a próbamód a tárhoz nem nyúl.
- **Modell-ág** (`bizonytalan` felismerésre; csak `hivo(prompt, max_tokens) → szöveg` mögött): a kimenet négy kapun megy át — kinyerés, formátum,
  CAS-homokozó (értelmezhető-e az ablakán), egyeztetés a felismerő kifejezésével (`grafikon.egyezes`). **Élesben csak kalibrált modell és `referencia`
  egyeztetés mellett írható; különben `proba: true` (D9)**; paraméteres görbét a modell-ág nem ír. **Worker-kötés (C35b)**: `modell_hivo.Hivo` — a `grafikon`
  router-feladat kalibrált modellje (a keretet a worker az aktivitásból dönti), a mérés kérés-beállításával; a kifejezett modell próba. **Az éles írás a
  `[grafikon.automatika] modell_ag` kapcsolón múlik, amely alapból hamis**: a mért C18 `grafikon` kérés (JSON-adatok kiolvasása) nem azonos az éles blokk-író
  kéréssel, ezért az éles kérést a `bin/mos grafikon modell-meres` méri (a C18 15 képlete kényszerítetten bizonytalannak véve + a természetesen bizonytalan
  szintetikus függvények; kapu: **0 téves blokk**, a blokk x-ablaka lefedi a várt pontokat); a kapcsolót a számok alapján kapcsolják be.
- **CLI** (`bin/mos grafikon`): `terv`, `beiras` (alapból csak terv; `--proba` klónra ír), `automatikus` (alapból szárazon; `--proba`; az éles `--eles` csak
  `MOS_FELADAT` mellett, azaz a feladatsor lépéseként), `tiltolista`, `modell-ellenorzes`.


## CX-010: színek és tengelyfeliratok

A régebbi olvasók által is elfogadott megjegyzéssorok adják a megjelenítést. A görbék sorszáma 1-től indul;
a szín három- vagy hatjegyű hexadecimális érték, a felirat egyszerű szöveg (HTML nélkül, legfeljebb 80 karakter).
Érvénytelen értéknél a renderelő jelzi a hibát és az alapmegjelenítést tartja.

```plot
# szin 1 #b85470
# x-felirat "Idő (s)"
# y-felirat "Magasság"
y=x^2
y=x "y=x"
```

A `/` beszúrás-menüben „Függvénygrafikon” és „Függvény összevetése y=x-szel” minták érhetők el.
