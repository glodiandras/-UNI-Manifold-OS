// A ```plot blokk kifejezés-nyelve (C35a): saját, `eval` nélküli elemző és kiértékelő. A Python-oldallal (`kozos.matek.elemez`)
// közös vektorok őrzik a paritást (`modulok/grafikon/vektorok/kifejezes.json`, `bin/mos grafikon vektorok`); a felület
// sosem fogad el többet, mint az `elemez` (D-4), és a páratlan nevezőjű tört kitevő a negatív oldalon is valós (D-5).

import { describe, expect, it } from 'vitest';
import { KifejezesHiba, fordit, konstans } from '../src/szerkeszto/renderelok/plot/kifejezes';
import { forras as forrasok, vektor } from './plot-segedek';

interface Tetel {
  kifejezes: string;
  x: number;
  ertek: number | null;
  forras?: string;
}
interface Vektor {
  tetelek: Tetel[];
  hibas_mindketto: string[];
  hibas_csak_ts: string[];
}
const V = vektor<Vektor>('kifejezes');

function kozel(kapott: number, vart: number | null): boolean {
  if (vart === null) return Number.isNaN(kapott);
  if (!Number.isFinite(kapott)) return false;
  return Math.abs(kapott - vart) <= 1e-9 * Math.max(1, Math.abs(vart));
}

describe('paritás a Python-oldallal (közös vektorok)', () => {
  const kulonbozo = [...new Set(V.tetelek.map((t) => t.kifejezes))];
  it('a vektor elegendő és sokféle kifejezést tartalmaz', () => {
    expect(kulonbozo.length).toBeGreaterThanOrEqual(80);
    expect(V.tetelek.length).toBeGreaterThan(1000);
  });

  it('minden kifejezés minden pontján azonos az érték (vagy mindkettő nem valós)', () => {
    const rosszak: string[] = [];
    for (const kif of kulonbozo) {
      const f = fordit(kif);
      for (const t of V.tetelek.filter((e) => e.kifejezes === kif)) {
        const k = f(t.x);
        if (!kozel(k, t.ertek)) rosszak.push(`${kif} @ ${t.x}: ${k} ≠ ${t.ertek}`);
      }
    }
    expect(rosszak).toEqual([]);
  });

  it('az elutasítandó kifejezések hibát adnak (mindkét lista)', () => {
    for (const kif of [...V.hibas_mindketto, ...V.hibas_csak_ts]) {
      expect(() => fordit(kif), kif).toThrow(KifejezesHiba);
    }
  });
});

describe('szintaxis', () => {
  const ertek = (kif: string, x: number) => fordit(kif)(x);

  it('precedencia: a hatvány erősebb az előjelnél és a szorzásnál', () => {
    expect(ertek('-x^2', 3)).toBe(-9);
    expect(ertek('-2^2', 0)).toBe(-4);
    expect(ertek('2^-x', 3)).toBeCloseTo(0.125, 12);
    expect(ertek('2x^2', 3)).toBe(18);
    expect(ertek('(-x)^2', 3)).toBe(9);
    expect(ertek('1/2x', 4)).toBe(2); // az implicit szorzás beszúrt `*`: (1/2)*x, mint a Python-oldalon
    expect(ertek('8/2*2', 0)).toBe(8);
    expect(ertek('2 - 3 - 4', 0)).toBe(-5);
  });

  it('implicit szorzás: szám/zárójel/név után név, függvény vagy zárójel', () => {
    expect(ertek('2x', 3)).toBe(6);
    expect(ertek('2(x+1)', 3)).toBe(8);
    expect(ertek('(x+1)(x-1)', 3)).toBe(8);
    expect(ertek('x(x+1)', 3)).toBe(12);
    expect(ertek('3sin(x)cos(x)', 0.5)).toBeCloseTo(3 * Math.sin(0.5) * Math.cos(0.5), 12);
    expect(ertek('x sin(x)', 2)).toBeCloseTo(2 * Math.sin(2), 12);
    expect(ertek('2pi', 0)).toBeCloseTo(2 * Math.PI, 12);
    expect(ertek('x/pi', Math.PI)).toBeCloseTo(1, 12);
  });

  it('számok: tizedes, `.5`, tudományos; `2e` a 2·e, nem szám', () => {
    expect(ertek('0.5x', 4)).toBe(2);
    expect(ertek('.5x', 4)).toBe(2);
    expect(ertek('2e3', 0)).toBe(2000);
    expect(ertek('2e', 0)).toBeCloseTo(2 * Math.E, 12);
    expect(ertek('2e^x', 1)).toBeCloseTo(2 * Math.E, 12);
  });

  it('a `**` hatványjel, mint a Python-oldalon', () => {
    expect(ertek('x**2', 3)).toBe(9);
    expect(ertek('2**x', 3)).toBe(8);
  });

  it('függvények: nevek, aliasok és a `log` két alakja', () => {
    expect(ertek('abs(x)', -2)).toBe(2);
    expect(ertek('Abs(x)', -2)).toBe(2);
    expect(ertek('ln(x)', Math.E)).toBeCloseTo(1, 12);
    expect(ertek('log(x)', Math.E)).toBeCloseTo(1, 12); // a SymPy-ban `log(x)` természetes
    expect(ertek('lg(x)', 1000)).toBeCloseTo(3, 12);
    expect(ertek('log(x, 2)', 8)).toBeCloseTo(3, 12);
    expect(ertek('log(x,10)', 1000)).toBeCloseTo(3, 12);
    expect(ertek('tg(x)', 1)).toBeCloseTo(Math.tan(1), 12);
    expect(ertek('ctg(x)', 1)).toBeCloseTo(1 / Math.tan(1), 12);
    expect(ertek('root(x,3)', 27)).toBeCloseTo(3, 12);
    expect(ertek('exp(x)', 1)).toBeCloseTo(Math.E, 12);
  });

  it('a változó neve a hívó dönti; más betű ismeretlen', () => {
    expect(fordit('t^2 + 1', 't')(3)).toBe(10);
    expect(() => fordit('t^2 + 1', 'x')).toThrow(/ismeretlen név/);
    expect(() => fordit('x + 1', 't')).toThrow(/ismeretlen név/);
  });

  it('a konstans-kifejezés (tartományhatár, pont): nincs változó', () => {
    expect(konstans('-2*pi')).toBeCloseTo(-2 * Math.PI, 12);
    expect(konstans('4')).toBe(4);
    expect(konstans('pi/2')).toBeCloseTo(Math.PI / 2, 12);
    expect(konstans('sqrt(2)')).toBeCloseTo(Math.SQRT2, 12);
    expect(() => konstans('x')).toThrow(/ismeretlen név/);
    expect(() => konstans('1/0')).toThrow(KifejezesHiba);
    expect(() => konstans('ln(0)')).toThrow(KifejezesHiba);
  });
});

describe('értelmezési tartomány és a páratlan gyök (D-5)', () => {
  const ertek = (kif: string, x: number) => fordit(kif)(x);

  it('a tartományon kívül NaN, nem hiba és nem végtelen', () => {
    expect(ertek('sqrt(x)', -1)).toBeNaN();
    expect(ertek('ln(x)', 0)).toBeNaN();
    expect(ertek('ln(x)', -2)).toBeNaN();
    expect(ertek('1/x', 0)).toBeNaN();
    expect(ertek('asin(x)', 2)).toBeNaN();
    expect(ertek('(x^2-1)/(x-1)', 1)).toBeNaN();
    expect(ertek('1/(1/x)', 0)).toBeNaN(); // a köztes végtelen nem enged véges eredményt (a CAS: komplex végtelen)
    expect(ertek('x^(-1/3)', 0)).toBeNaN();
  });

  it('a páratlan nevezőjű tört kitevő a negatív oldalon is valós', () => {
    expect(ertek('root(x,3)', -8)).toBeCloseTo(-2, 12);
    expect(ertek('x^(1/3)', -8)).toBeCloseTo(-2, 12);
    expect(ertek('x^(2/3)', -8)).toBeCloseTo(4, 12);
    expect(ertek('x^(-1/3)', -8)).toBeCloseTo(-0.5, 12);
    expect(ertek('root(x,3)^2', -8)).toBeCloseTo(4, 12);
    expect(ertek('root(x,5)', -32)).toBeCloseTo(-2, 12);
  });

  it('páros nevező, tizedes kitevő és változó kitevő a negatív alapon nem valós', () => {
    expect(ertek('x^(1/2)', -4)).toBeNaN();
    expect(ertek('x^0.5', -4)).toBeNaN();
    expect(ertek('root(x,4)', -16)).toBeNaN();
    expect(ertek('x^0.333', -8)).toBeNaN(); // 333/1000: páros nevező
    expect(ertek('x^x', -0.5)).toBeNaN();
    expect(ertek('x^x', -2)).toBeCloseTo(0.25, 12);
  });

  it('állandó alapon a főág marad (nem a páratlan gyök): (-8)^(1/3) nem valós', () => {
    expect(ertek('(-8)^(1/3)', 0)).toBeNaN();
  });
});

describe('hibák: magyar üzenet, pozícióval', () => {
  const uzenet = (kif: string, valtozo: string | null = 'x'): string => {
    try {
      fordit(kif, valtozo);
    } catch (e) {
      return (e as Error).message;
    }
    throw new Error('nem dobott: ' + kif);
  };

  it('zárójel nélküli függvény: a javítás a példa', () => {
    expect(uzenet('sin x')).toMatch(/zárójel/);
    expect(uzenet('sin x')).toMatch(/sin\(x\)/);
    expect(uzenet('sqrt x')).toMatch(/zárójel/);
  });

  it('nem megengedett jel és idegen név', () => {
    expect(uzenet('x @ 2')).toMatch(/nem megengedett jel/);
    expect(uzenet('foo(x)')).toMatch(/ismeretlen név/);
    expect(uzenet('x_1')).toMatch(/nem megengedett jel/);
    expect(uzenet('|x|')).toMatch(/nem megengedett jel/);
  });

  it('hiányzó művelet, páratlan zárójel, csonka kifejezés, üres', () => {
    expect(uzenet('2 3')).toMatch(/művelet/);
    expect(uzenet('(x+1')).toMatch(/zárójel/);
    expect(uzenet('x+1)')).toMatch(/zárójel/);
    expect(uzenet('x +')).toMatch(/hiányzik|csonka/);
    expect(uzenet('')).toMatch(/üres/);
    expect(uzenet('   ')).toMatch(/üres/);
    expect(uzenet('x^')).toMatch(/hiányzik|csonka/);
  });

  it('nem rajzolható és túl nagy', () => {
    expect(uzenet('x!')).toMatch(/faktoriális/);
    expect(uzenet('factorial(x)')).toMatch(/nem rajzolható/);
    expect(uzenet('x^2^3')).toMatch(/hatványtorony/);
    expect(uzenet('x^10000')).toMatch(/túl nagy/);
    expect(uzenet('1'.repeat(300) + '+x')).toMatch(/túl hosszú/);
    expect(uzenet('1234567890123456')).toMatch(/túl nagy/);
  });

  it('a függvény argumentum-száma', () => {
    expect(uzenet('sin(x, 2)')).toMatch(/argumentum/);
    expect(uzenet('sin()')).toMatch(/argumentum|hiányzik/);
    expect(uzenet('root(x)')).toMatch(/argumentum/);
    expect(uzenet('root(x, x)')).toMatch(/állandó/);
    expect(uzenet('log(x, 2, 3)')).toMatch(/argumentum/);
  });

  it('a pozíció a hibás jelre mutat', () => {
    try {
      fordit('2x + @');
    } catch (e) {
      expect(e).toBeInstanceOf(KifejezesHiba);
      expect((e as KifejezesHiba).poz).toBe(5);
    }
  });
});

describe('a modul `eval`-mentes', () => {
  it('a forrás nem hivatkozik `eval`-ra, `Function`-re, dinamikus kódra', () => {
    const kod = forrasok.kifejezes.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(kod).not.toMatch(/\beval\b/);
    expect(kod).not.toMatch(/\bnew\s+Function\b/);
    expect(kod).not.toMatch(/\bFunction\s*\(/);
    expect(kod).not.toMatch(/setTimeout\s*\(\s*['"`]/);
  });
});
