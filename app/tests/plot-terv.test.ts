// Az ábrából rajzterv (C35a): ablak-választás hiányzó tartománynál („szép” határok, percentilis-vágás), a hibás elem
// halk kihagyása, a sorozatszín-tokenek sorrendje. A rajzoló (JSXGraph) ebből dolgozik; itt nincs könyvtár.

import { describe, expect, it } from 'vitest';
import { elemez } from '../src/szerkeszto/renderelok/plot/forras';
import { SOROZAT_SZIN, szepHatarok, terv } from '../src/szerkeszto/renderelok/plot/terv';

const t = (szoveg: string) => terv(elemez(szoveg));

describe('szepHatarok', () => {
  it('1/2/5·10^k lépcsőre kerekít', () => {
    expect(szepHatarok(-1.16, 1.16)).toEqual([-2, 2]);
    expect(szepHatarok(-2, 27)).toEqual([-10, 30]);
    expect(szepHatarok(0.12, 0.88)).toEqual([0, 1]);
    expect(szepHatarok(-0.3, 0.1)).toEqual([-0.3, 0.1]);
  });
  it('nem hagy lebegőpontos farkat', () => {
    const [a, b] = szepHatarok(0.1, 0.7);
    expect(String(a)).not.toMatch(/\d{8,}/);
    expect(String(b)).not.toMatch(/\d{8,}/);
  });
});

describe('ablak', () => {
  it('a megadott tartomány az ablak (konstans-kifejezéssel is)', () => {
    const p = t('x in [-2*pi, 2*pi]\ny in [-3, 3]\ny = sin(x)');
    expect(p.ablak.x[0]).toBeCloseTo(-2 * Math.PI, 12);
    expect(p.ablak.x[1]).toBeCloseTo(2 * Math.PI, 12);
    expect(p.ablak.y).toEqual([-3, 3]);
  });

  it('hiányzó x: [-5, 5], trigonometrikusnál [-2π, 2π]', () => {
    expect(t('y = x^2').ablak.x).toEqual([-5, 5]);
    const s = t('y = sin(x)');
    expect(s.ablak.x[0]).toBeCloseTo(-2 * Math.PI, 12);
    expect(s.ablak.x[1]).toBeCloseTo(2 * Math.PI, 12);
  });

  it('hiányzó y: a mintákból, margóval, szép határokra', () => {
    const p = t('y = x^2');
    expect(p.ablak.y[0]).toBeLessThanOrEqual(0);
    expect(p.ablak.y[1]).toBeGreaterThanOrEqual(25);
    expect(p.ablak.y[1]).toBeLessThanOrEqual(40);
    const s = t('y = sin(x)');
    expect(s.ablak.y[0]).toBeLessThanOrEqual(-1);
    expect(s.ablak.y[1]).toBeGreaterThanOrEqual(1);
    expect(s.ablak.y[1]).toBeLessThanOrEqual(2);
  });

  it('a pólus nem nyújtja a tartományt (percentilis-vágás)', () => {
    const p = t('y = 1/x');
    expect(p.ablak.y[1] - p.ablak.y[0]).toBeLessThan(60);
  });

  it('az értelmezetlen szél nem számít (gyök, logaritmus)', () => {
    const p = t('y = sqrt(x)');
    expect(p.ablak.y[0]).toBeLessThanOrEqual(0);
    expect(p.ablak.y[1]).toBeLessThanOrEqual(5);
    const l = t('y = ln(x)');
    expect(l.ablak.y[1] - l.ablak.y[0]).toBeLessThan(60);
  });

  it('paraméteres görbénél a görbe befoglaló téglalapja', () => {
    const p = t('x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]');
    expect(p.ablak.x[0]).toBeLessThanOrEqual(-3);
    expect(p.ablak.x[1]).toBeGreaterThanOrEqual(3);
    expect(p.ablak.y[0]).toBeLessThanOrEqual(-2);
    expect(p.ablak.y[1]).toBeGreaterThanOrEqual(2);
    expect(p.ablak.x[1]).toBeLessThan(8);
  });

  it('csak pontok: körülöttük', () => {
    const p = t('pont (2, 1)\npont (4, 5)');
    expect(p.ablak.x[0]).toBeLessThan(2);
    expect(p.ablak.x[1]).toBeGreaterThan(4);
    expect(p.ablak.y[0]).toBeLessThan(1);
    expect(p.ablak.y[1]).toBeGreaterThan(5);
  });

  it('az egyenlőtlenség határgörbéje is beleszámít', () => {
    const p = t('y >= x^2');
    expect(p.ablak.y[1]).toBeGreaterThanOrEqual(25);
  });

  it('az ablak soha nem üres és nem fordított', () => {
    for (const s of ['y = 3', 'y = x^2 + 1000000', 'x in [2, 1]\ny = x', 'pont (1, 1)', 'y in [5, 5]\ny = x']) {
      const p = t(s);
      expect(p.ablak.x[0], s).toBeLessThan(p.ablak.x[1]);
      expect(p.ablak.y[0], s).toBeLessThan(p.ablak.y[1]);
    }
  });
});

describe('elemek', () => {
  it('függvény, egyenlőtlenség, pont, paraméteres külön listában; a sorozatszín sorrendben', () => {
    const p = t('y = x\ny = x^2 "f"\ny > 1\npont (1, 2) "P"\nx = t, y = t^2, t in [0, 1]');
    expect(p.gorbek.map((g) => g.fajta)).toEqual(['fuggveny', 'fuggveny', 'parameteres']);
    expect(p.tartomanyok).toHaveLength(1);
    expect(p.pontok).toEqual([{ x: 1, y: 2, cimke: 'P' }]);
    expect(p.gorbek.map((g) => g.cimke)).toEqual([null, 'f', null]);
    expect(p.gorbek[0].szin).toBe(SOROZAT_SZIN[0]);
    expect(p.gorbek[1].szin).toBe(SOROZAT_SZIN[1]);
    expect(p.tartomanyok[0].szin).toBe(SOROZAT_SZIN[2]);
    expect(p.gorbek[2].szin).toBe(SOROZAT_SZIN[3]);
  });

  it('a sorozatszínek csak meglévő tokenek; elfogyva újrakezdi', () => {
    expect(SOROZAT_SZIN).toEqual(['--akcent', ...[1, 2, 3, 4, 5, 6].map((n) => `--canvas-szin-${n}`)]);
    const p = t(Array.from({ length: 9 }, (_, i) => `y = x + ${i}`).join('\n'));
    expect(p.gorbek[7].szin).toBe(SOROZAT_SZIN[0]);
  });

  it('a függvény értéke kiértékelhető, a kifejezés szövege megmarad (a jellemzőkhöz)', () => {
    const p = t('y = x^2 + 1');
    expect(p.gorbek[0].ertek(3)).toBe(10);
    expect(p.gorbek[0].kifejezes).toBe('x^2 + 1');
  });

  it('a paraméteres görbe a paraméter betűjével értékel', () => {
    const g = t('x = cos(s), y = sin(s), s in [0, pi]').gorbek[0];
    expect(g.param!.x(0)).toBe(1);
    expect(g.param!.y(Math.PI / 2)).toBeCloseTo(1, 12);
    expect([g.param!.lo, g.param!.hi]).toEqual([0, Math.PI]);
  });
});

describe('hibák: halk figyelmeztetés, nem dobás', () => {
  it('az ismeretlen sor és a hibás kifejezés kimarad, a többi él', () => {
    const p = t('y = x\nvalami\ny = sin x\ny = foo(x)\npont (a, 1)');
    expect(p.gorbek).toHaveLength(1);
    expect(p.pontok).toEqual([]);
    expect(p.figyelmeztetesek.length).toBe(4);
    expect(p.figyelmeztetesek.join('\n')).toMatch(/ismeretlen vagy hibás sor/);
    expect(p.figyelmeztetesek.join('\n')).toMatch(/zárójel/);
    expect(p.figyelmeztetesek.join('\n')).toMatch(/foo/);
    expect(p.hasznalhato).toBe(true);
  });

  it('ha semmi nem rajzolható, a használhatóság hamis és az ok az első hiba', () => {
    const p = t('valami\ny = sin x');
    expect(p.hasznalhato).toBe(false);
    expect(p.figyelmeztetesek.length).toBe(2);
  });

  it('az üres blokk nem használható', () => {
    expect(t('').hasznalhato).toBe(false);
    expect(t('# csak megjegyzés').hasznalhato).toBe(false);
  });

  it('a hibás tartomány-kifejezés figyelmeztet, és az ablak automatikus lesz', () => {
    const p = t('x in [a, b]\ny = x^2');
    expect(p.ablak.x).toEqual([-5, 5]);
    expect(p.figyelmeztetesek.join('\n')).toMatch(/x tartomány/);
    const q = t('x in [3, 1]\ny = x^2');
    expect(q.ablak.x).toEqual([-5, 5]);
    expect(q.figyelmeztetesek.join('\n')).toMatch(/x tartomány/);
  });

  it('az e nevű paraméter az Euler-számmal ütközik', () => {
    const p = t('x = e, y = e^2, e in [0, 1]\ny = x');
    expect(p.gorbek).toHaveLength(1);
    expect(p.figyelmeztetesek.join('\n')).toMatch(/paraméter/);
  });
});

it('CX-010: színek és tengelyfeliratok biztonságos megjegyzésekből', () => {
  const p = t('# szin 1 #b85470\n# x-felirat "Idő (s)"\n# y-felirat "Magasság"\ny = x^2\ny = x');
  expect(p.gorbek[0].szin).toBe('#b85470');
  expect(p.gorbek[1].szin).toBe(SOROZAT_SZIN[1]);
  expect(p.tengelyFelirat).toEqual({ x: 'Idő (s)', y: 'Magasság' });
  const rossz = t('# szin 1 url(javascript:alert(1))\n# x-felirat "<img src=x>"\ny=x');
  expect(rossz.figyelmeztetesek).toHaveLength(2);
  expect(rossz.gorbek[0].szin).toBe(SOROZAT_SZIN[0]);
});
