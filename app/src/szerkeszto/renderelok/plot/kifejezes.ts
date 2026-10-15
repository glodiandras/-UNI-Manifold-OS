// A ```plot blokk kifejezés-nyelve (C35a): tokenizáló, rekurzív leszállású elemző és kiértékelő. Saját, mert a rajz a
// nagyításkor és a mozgatáskor másodpercenként sokszor értékel, hálózat nélkül, és a CSP-ben nincs `unsafe-eval`
// (a JSXGraph szöveges kifejezés-elemzője nem használható: JS-függvényt kap, nem szöveget).
//
// A nyelv a Python-oldal `kozos.matek.elemez` jelölése (közös vektorok: `modulok/grafikon/vektorok/kifejezes.json`), de a
// felület **szigorúbb** (D-4): függvényhívás csak zárójellel (`sin(x)`), nincs `|x|`, nincs `x!`, egyetlen változó. Amit
// az `elemez` elutasít (hatványtorony, óriási szám, ismeretlen név), azt ez is. A páratlan nevezőjű tört kitevő a
// negatív oldalon is valós (D-5: `root(x,3)`, `x^(1/3)`), de csak ha az alap változót tartalmaz — állandó alapon a főág
// marad, mint a CAS-ban. Ami nincs a valós értelmezési tartományban, az `NaN` (nem hiba): a rajz itt szakít.

export class KifejezesHiba extends Error {
  constructor(
    uzenet: string,
    readonly poz: number | null = null,
  ) {
    super(poz === null ? uzenet : `${uzenet} (${poz + 1}. jel)`);
    this.name = 'KifejezesHiba';
  }
}

/** Egy lefordított kifejezés: a változó értékéből a kifejezés értéke (`NaN`, ha nem valós vagy nem véges). */
export type Ertek = (v: number) => number;

const MAX_HOSSZ = 300; // a `kozos.matek.elemez` plafonja
const MEGENGEDETT = /^[0-9A-Za-z+\-*/^().,! ]*$/;
const SZAM = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/;
const NEV = /^[A-Za-z]+/;

// Az `elemez` szövegszintű védelmei (óriási szám, hatványtorony, faktoriális-robbanás), szó szerint ugyanazok.
const TUL_NAGY: RegExp[] = [
  /\d{13,}/,
  /(?:\^|\*\*)\s*\(?\s*\d{4,}/,
  /(?:\^|\*\*)\s*\(?\s*[\d.]+\s*\)?\s*(?:\^|\*\*)/,
  /!!/,
  /\d{3,}\s*!|factorial\s*\(\s*\d{3,}/,
];

const FUGGVENYEK = new Set([
  'sqrt', 'root', 'log', 'ln', 'lg', 'exp', 'sin', 'cos', 'tan', 'tg', 'cot', 'ctg', 'asin', 'acos', 'atan', 'abs', 'Abs',
]);
const NEM_RAJZOLHATO = new Set(['factorial', 'binomial']);
// `Map`: a sima objektum prototípus-kulcsai (`constructor`, `toString`, `valueOf`…) nem lehetnek állandók (A3-29)
const ALLANDOK: ReadonlyMap<string, number> = new Map([
  ['pi', Math.PI],
  ['e', Math.E],
]);

// ------------------------------------------------------------------ tokenek

type Token =
  | { t: 'szam'; v: number; poz: number }
  | { t: 'nev'; v: string; poz: number }
  | { t: 'jel'; v: string; poz: number }
  | { t: 'vege'; poz: number };

function tokenek(s: string): Token[] {
  const ki: Token[] = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === ' ') {
      i++;
      continue;
    }
    const rest = s.slice(i);
    const sz = SZAM.exec(rest);
    if (sz) {
      ki.push({ t: 'szam', v: Number(sz[0]), poz: i });
      i += sz[0].length;
      continue;
    }
    const n = NEV.exec(rest);
    if (n) {
      ki.push({ t: 'nev', v: n[0], poz: i });
      i += n[0].length;
      continue;
    }
    if (c === '*' && s[i + 1] === '*') {
      ki.push({ t: 'jel', v: '^', poz: i });
      i += 2;
      continue;
    }
    if ('+-*/^(),'.includes(c)) {
      ki.push({ t: 'jel', v: c, poz: i });
      i++;
      continue;
    }
    if (c === '!') throw new KifejezesHiba('a faktoriális (!) nem rajzolható', i);
    throw new KifejezesHiba(`nem megengedett jel: ${c}`, i);
  }
  ki.push({ t: 'vege', poz: s.length });
  return ki;
}

// ------------------------------------------------------------------ szintaxisfa

type Csucs =
  | { t: 'szam'; v: number }
  | { t: 'valt' }
  | { t: 'neg'; a: Csucs }
  | { t: 'bin'; op: '+' | '-' | '*' | '/' | '^'; a: Csucs; b: Csucs; poz: number }
  | { t: 'fv'; nev: string; args: Csucs[] };

function allando(c: Csucs): boolean {
  switch (c.t) {
    case 'szam':
      return true;
    case 'valt':
      return false;
    case 'neg':
      return allando(c.a);
    case 'bin':
      return allando(c.a) && allando(c.b);
    case 'fv':
      return c.args.every(allando);
  }
}

class Elemzo {
  private i = 0;
  constructor(
    private readonly tk: Token[],
    private readonly valtozo: string | null,
  ) {}

  private get most(): Token {
    return this.tk[this.i];
  }

  private jel(v: string): boolean {
    const t = this.most;
    return t.t === 'jel' && t.v === v;
  }

  elemez(): Csucs {
    const c = this.osszeg();
    const t = this.most;
    if (t.t !== 'vege') {
      if (t.t === 'jel' && t.v === ')') throw new KifejezesHiba('páratlan zárójel: felesleges `)`', t.poz);
      throw new KifejezesHiba('váratlan jel', t.poz);
    }
    return c;
  }

  private osszeg(): Csucs {
    let a = this.szorzat();
    for (;;) {
      const t = this.most;
      if (t.t === 'jel' && (t.v === '+' || t.v === '-')) {
        this.i++;
        a = { t: 'bin', op: t.v, a, b: this.szorzat(), poz: t.poz };
      } else return a;
    }
  }

  private szorzat(): Csucs {
    let a = this.tenyezo();
    for (;;) {
      const t = this.most;
      if (t.t === 'jel' && (t.v === '*' || t.v === '/')) {
        this.i++;
        a = { t: 'bin', op: t.v, a, b: this.tenyezo(), poz: t.poz };
      } else if (t.t === 'szam') {
        throw new KifejezesHiba('hiányzó művelet a szám előtt (`2 3`, `x2`)', t.poz);
      } else if (t.t === 'nev' || (t.t === 'jel' && t.v === '(')) {
        a = { t: 'bin', op: '*', a, b: this.tenyezo(), poz: t.poz }; // implicit szorzás: beszúrt `*`
      } else return a;
    }
  }

  private tenyezo(): Csucs {
    const t = this.most;
    if (t.t === 'jel' && (t.v === '-' || t.v === '+')) {
      this.i++;
      const a = this.tenyezo();
      return t.v === '-' ? { t: 'neg', a } : a;
    }
    return this.hatvany();
  }

  private hatvany(): Csucs {
    const alap = this.elsodleges();
    const t = this.most;
    if (t.t === 'jel' && t.v === '^') {
      this.i++;
      return { t: 'bin', op: '^', a: alap, b: this.tenyezo(), poz: t.poz };
    }
    return alap;
  }

  private elsodleges(): Csucs {
    const t = this.most;
    if (t.t === 'vege') throw new KifejezesHiba('csonka kifejezés: hiányzik a művelet jobb oldala', t.poz);
    if (t.t === 'szam') {
      this.i++;
      return { t: 'szam', v: t.v };
    }
    if (t.t === 'jel') {
      if (t.v === '(') {
        this.i++;
        const c = this.osszeg();
        this.zarojelZar(t.poz);
        return c;
      }
      throw new KifejezesHiba(`váratlan jel: ${t.v}`, t.poz);
    }
    return this.nev(t);
  }

  private zarojelZar(nyitoPoz: number): void {
    const z = this.most;
    if (z.t === 'jel' && z.v === ')') {
      this.i++;
      return;
    }
    throw new KifejezesHiba('páratlan zárójel: hiányzik a záró `)`', nyitoPoz);
  }

  private nev(t: Token & { t: 'nev' }): Csucs {
    this.i++;
    if (FUGGVENYEK.has(t.v)) {
      const nyito = this.most;
      if (!(nyito.t === 'jel' && nyito.v === '(')) {
        throw new KifejezesHiba(`a függvény neve után zárójel kell, pl. ${t.v}(x)`, t.poz);
      }
      this.i++;
      const args: Csucs[] = [];
      if (this.jel(')')) throw new KifejezesHiba(`a ${t.v} argumentuma hiányzik`, nyito.poz);
      for (;;) {
        args.push(this.osszeg());
        if (this.jel(',')) {
          this.i++;
          continue;
        }
        break;
      }
      this.zarojelZar(nyito.poz);
      return this.fuggveny(t, args);
    }
    if (NEM_RAJZOLHATO.has(t.v)) throw new KifejezesHiba(`a ${t.v} nem rajzolható (nem folytonos függvény)`, t.poz);
    const allando = ALLANDOK.get(t.v);
    if (allando !== undefined) return { t: 'szam', v: allando };
    if (this.valtozo !== null && t.v === this.valtozo) return { t: 'valt' };
    throw new KifejezesHiba(`ismeretlen név: ${t.v}`, t.poz);
  }

  private fuggveny(t: Token & { t: 'nev' }, args: Csucs[]): Csucs {
    const v = t.v;
    const kell = v === 'root' ? [2] : v === 'log' ? [1, 2] : [1];
    if (!kell.includes(args.length)) {
      throw new KifejezesHiba(
        v === 'root'
          ? 'a root két argumentumot kér: root(x, n)'
          : v === 'log'
            ? 'a log egy vagy két argumentumot kér: log(x) vagy log(x, alap)'
            : `a ${v} egy argumentumot kér`,
        t.poz,
      );
    }
    if (v === 'root') {
      if (!allando(args[1])) throw new KifejezesHiba('a gyökkitevő állandó legyen: root(x, 3)', t.poz);
      // root(a, n) ≡ a^(1/n): ugyanaz a hatvány-szemantika (páratlan gyök a negatív oldalon is valós)
      return { t: 'bin', op: '^', a: args[0], b: { t: 'bin', op: '/', a: { t: 'szam', v: 1 }, b: args[1], poz: t.poz }, poz: t.poz };
    }
    return { t: 'fv', nev: v === 'Abs' ? 'abs' : v === 'tg' ? 'tan' : v === 'ctg' ? 'cot' : v === 'ln' ? 'log' : v, args };
  }
}

// ------------------------------------------------------------------ kiértékelés

const veges = (r: number): number => (Number.isFinite(r) ? r : NaN);

/** Egy állandó kitevő tört alakja (p/q, a nevező ≤ 10000), `null`, ha nem racionális. */
export function racionalis(v: number): [number, number] | null {
  if (!Number.isFinite(v)) return null;
  let h0 = 0, h1 = 1, k0 = 1, k1 = 0, b = v;
  for (let i = 0; i < 24; i++) {
    const a = Math.floor(b);
    const h = a * h1 + h0;
    const k = a * k1 + k0;
    h0 = h1; h1 = h; k0 = k1; k1 = k;
    if (k > 10000) return null;
    if (Math.abs(v - h / k) <= 1e-12 * Math.max(1, Math.abs(v))) return [h, k];
    b = 1 / (b - a);
    if (!Number.isFinite(b)) return null;
  }
  return null;
}

function hatvany(alap: number, kit: number, tort: [number, number] | null, alapValtozo: boolean): number {
  if (Number.isNaN(alap) || Number.isNaN(kit)) return NaN;
  if (Number.isInteger(kit) || alap >= 0) return veges(Math.pow(alap, kit));
  // negatív alap, nem egész kitevő: csak a változós alap páratlan nevezőjű kitevője valós (D-5)
  if (alapValtozo && tort && Math.abs(tort[1]) % 2 === 1) {
    const [p, q] = tort;
    const abs = Math.pow(-alap, p / q);
    return veges(Math.abs(p) % 2 === 0 ? abs : -abs);
  }
  return NaN;
}

const FV1: Record<string, (a: number) => number> = {
  sqrt: Math.sqrt,
  exp: Math.exp,
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  cot: (a) => 1 / Math.tan(a),
  asin: Math.asin,
  acos: Math.acos,
  atan: Math.atan,
  log: Math.log,
  lg: Math.log10,
  abs: Math.abs,
};

function forditCsucs(c: Csucs): Ertek {
  switch (c.t) {
    case 'szam': {
      const v = c.v;
      return () => v;
    }
    case 'valt':
      return (x) => x;
    case 'neg': {
      const a = forditCsucs(c.a);
      return (x) => -a(x);
    }
    case 'fv': {
      if (c.nev === 'log' && c.args.length === 2) {
        const a = forditCsucs(c.args[0]);
        const b = forditCsucs(c.args[1]);
        return (x) => {
          const n = Math.log(b(x));
          return n === 0 ? NaN : veges(Math.log(a(x)) / n);
        };
      }
      const f = FV1[c.nev];
      const a = forditCsucs(c.args[0]);
      return (x) => veges(f(a(x)));
    }
    case 'bin': {
      const a = forditCsucs(c.a);
      const b = forditCsucs(c.b);
      switch (c.op) {
        case '+':
          return (x) => veges(a(x) + b(x));
        case '-':
          return (x) => veges(a(x) - b(x));
        case '*':
          return (x) => veges(a(x) * b(x));
        case '/':
          return (x) => {
            const n = b(x);
            return n === 0 ? NaN : veges(a(x) / n);
          };
        case '^': {
          const alapValtozo = !allando(c.a);
          const kitAllando = allando(c.b);
          const tort = kitAllando ? racionalis(b(0)) : null;
          return (x) => hatvany(a(x), b(x), tort, alapValtozo);
        }
      }
    }
  }
}

function elofeldolgoz(forras: string): string {
  if (typeof forras !== 'string' || !forras.trim()) throw new KifejezesHiba('üres kifejezés');
  if (forras.length > MAX_HOSSZ) throw new KifejezesHiba(`a kifejezés túl hosszú (legfeljebb ${MAX_HOSSZ} jel)`);
  const hely = [...forras].findIndex((ch) => !MEGENGEDETT.test(ch));
  if (hely >= 0) throw new KifejezesHiba(`nem megengedett jel: ${[...forras][hely]}`, hely);
  if (TUL_NAGY.some((r) => r.test(forras))) throw new KifejezesHiba('túl nagy szám vagy hatványtorony');
  return forras;
}

/** A kifejezés lefordítása; `valtozo`: a megengedett változó neve (`x` a függvényeknél, a paraméter a görbéknél),
 *  `null`: állandó kifejezés. Hibás vagy túl engedékeny szövegre `KifejezesHiba`. */
export function fordit(forras: string, valtozo: string | null = 'x'): Ertek {
  const fa = new Elemzo(tokenek(elofeldolgoz(forras)), valtozo).elemez();
  return forditCsucs(fa);
}

/** Egy állandó kifejezés (tartományhatár, pont koordinátája) értéke; nem véges érték hiba. */
export function konstans(forras: string): number {
  const v = fordit(forras, null)(0);
  if (!Number.isFinite(v)) throw new KifejezesHiba('az állandó kifejezés értéke nem véges szám');
  return v;
}
