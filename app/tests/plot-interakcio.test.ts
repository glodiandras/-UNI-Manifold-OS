// A grafikon interakciója (C35a), könyvtár nélkül: az egér alatti érték (a legközelebbi görbén), a nagyítás és a
// mozgatás számítása, a billentyűzet, a határok. A rajzoló (JSXGraph) ezeket hívja, és a kapott ablakot adja a táblának.

import { describe, expect, it } from 'vitest';
import { elemez } from '../src/szerkeszto/renderelok/plot/forras';
import {
  MAX_SPAN,
  MIN_SPAN,
  billentyu,
  kozeppont,
  legkozelebbi,
  nagyit,
} from '../src/szerkeszto/renderelok/plot/interakcio';
import { terv } from '../src/szerkeszto/renderelok/plot/terv';

const MERET = { szelesseg: 400, magassag: 300 };
const NEZET = { x: [-5, 5] as [number, number], y: [-5, 5] as [number, number] };

describe('legkozelebbi (az egér alatti érték)', () => {
  const p = terv(elemez('y = x^2\ny = x'));

  it('a kurzor x-éhez tartozó függvényérték a legközelebbi görbén', () => {
    const t = legkozelebbi(p, NEZET, MERET, 2, 3.9);
    expect(t).toMatchObject({ gorbe: 0, x: 2 });
    expect(t!.y).toBe(4);
  });

  it('két görbe közül a pixelben közelebbi', () => {
    const t = legkozelebbi(p, NEZET, MERET, 1.5, 1.4);
    expect(t!.gorbe).toBe(1); // y = x → 1,5; az x² → 2,25
    expect(t!.y).toBe(1.5);
  });

  it('küszöbön túl nincs találat', () => {
    expect(legkozelebbi(p, NEZET, MERET, 2, -4)).toBeNull();
  });

  it('a tartományon kívüli (NaN) pontnál nincs találat', () => {
    const q = terv(elemez('y = sqrt(x)'));
    expect(legkozelebbi(q, NEZET, MERET, -2, 0)).toBeNull();
  });

  it('a paraméteres görbén a legközelebbi mintapont', () => {
    const q = terv(elemez('x = 3*cos(t), y = 3*sin(t), t in [0, 2*pi]'));
    const t = legkozelebbi(q, NEZET, MERET, 3.05, 0.1);
    expect(t).not.toBeNull();
    expect(Math.hypot(t!.x - 3, t!.y)).toBeLessThan(0.3);
  });

  it('ha nincs görbe (csak pont, egyenlőtlenség) nincs találat', () => {
    expect(legkozelebbi(terv(elemez('pont (1, 1)')), NEZET, MERET, 1, 1)).toBeNull();
  });
});

describe('nagyítás', () => {
  it('a nagyítás a megadott pont körül skáláz, a pont a helyén marad', () => {
    const n = nagyit(NEZET, 2, 1, 0.5);
    expect(n.x[1] - n.x[0]).toBeCloseTo(5, 12);
    expect(n.y[1] - n.y[0]).toBeCloseTo(5, 12);
    // a (2, 1) pont aránya az ablakban nem változott
    expect((2 - n.x[0]) / (n.x[1] - n.x[0])).toBeCloseTo((2 + 5) / 10, 12);
    expect((1 - n.y[0]) / (n.y[1] - n.y[0])).toBeCloseTo((1 + 5) / 10, 12);
  });

  it('a kicsinyítés és a nagyítás egymás inverze', () => {
    const n = nagyit(nagyit(NEZET, 1, 1, 0.8), 1, 1, 1 / 0.8);
    expect(n.x[0]).toBeCloseTo(-5, 10);
    expect(n.y[1]).toBeCloseTo(5, 10);
  });

  it('a szélesség a határok közé szorul', () => {
    const kicsi = nagyit(NEZET, 0, 0, 1e-12);
    expect(kicsi.x[1] - kicsi.x[0]).toBeGreaterThanOrEqual(MIN_SPAN * 0.999);
    const nagy = nagyit(NEZET, 0, 0, 1e12);
    expect(nagy.x[1] - nagy.x[0]).toBeLessThanOrEqual(MAX_SPAN * 1.001);
    expect(nagy.y[1] - nagy.y[0]).toBeLessThanOrEqual(MAX_SPAN * 1.001);
  });

  it('a közepe', () => {
    expect(kozeppont(NEZET)).toEqual([0, 0]);
  });
});

describe('billentyűzet', () => {
  const alap = { x: [-3, 3] as [number, number], y: [-2, 2] as [number, number] };

  it('a nyilak az ablak tizedét mozgatják', () => {
    expect(billentyu(NEZET, 'ArrowRight', alap)!.x).toEqual([-4, 6]);
    expect(billentyu(NEZET, 'ArrowLeft', alap)!.x).toEqual([-6, 4]);
    expect(billentyu(NEZET, 'ArrowUp', alap)!.y).toEqual([-4, 6]);
    expect(billentyu(NEZET, 'ArrowDown', alap)!.y).toEqual([-6, 4]);
  });

  it('a + és a - nagyít és kicsinyít a közép körül', () => {
    const be = billentyu(NEZET, '+', alap)!;
    expect(be.x[1] - be.x[0]).toBeCloseTo(8, 12);
    const ki = billentyu(NEZET, '-', alap)!;
    expect(ki.x[1] - ki.x[0]).toBeCloseTo(12.5, 12);
    expect(billentyu(NEZET, '=', alap)!.x[1] - billentyu(NEZET, '=', alap)!.x[0]).toBeCloseTo(8, 12);
  });

  it('a 0 az alaphelyzet', () => {
    expect(billentyu(NEZET, '0', alap)).toEqual(alap);
  });

  it('más billentyű: nincs művelet (a böngésző kezeli)', () => {
    expect(billentyu(NEZET, 'a', alap)).toBeNull();
    expect(billentyu(NEZET, 'Tab', alap)).toBeNull();
  });
});
