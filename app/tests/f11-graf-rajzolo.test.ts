// F11 / 11-graph-04, 11-graph-05, 11-graph-02/03 (rajzoló): a csúszkák (csúcsméret, vonalvastagság, szöveg-halványítás) valóban
// hatnak a rajzra; a címke és a feloldatlan cél saját alakot és színt kap (nem csak színt: a szaggatott gyűrű és a hatszög alak is
// jelez); a jobb gomb / Shift+F10 / ContextMenu a csúcs menüjét kéri (a natív menü sosem jön elő); az Enter és a kattintás a
// csúcs vásznon lévő helyét is átadja (a feloldatlan cél felajánlott műveletének menüjéhez).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GrafAdat, lathatosag, type GrafMeta, type GrafValasz } from '../src/lib/graf/modell';
import { GrafRajzolo, type Bemenet, type Esemenyek } from '../src/lib/graf/rajzolo';
import { felvevoKontextus, SZINEK, type FelvevoKontextus } from './graf-vaszon-segedek';

let rec: FelvevoKontextus;
let canvas: HTMLCanvasElement;
const r_: GrafRajzolo[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => setTimeout(() => f(performance.now()), 16) as unknown as number);
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  rec = felvevoKontextus();
  canvas = document.createElement('canvas');
  vi.spyOn(canvas, 'getContext').mockImplementation(() => rec.ctx as never);
  canvas.getBoundingClientRect = () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, x: 0, y: 0, toJSON() {} });
  canvas.setPointerCapture = vi.fn();
  canvas.releasePointerCapture = vi.fn();
  canvas.hasPointerCapture = () => false;
  canvas.focus = vi.fn();
  document.body.append(canvas);
});

afterEach(() => {
  r_.splice(0).forEach((r) => r.leallit());
  canvas.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const VALASZ: GrafValasz = { csucsok: ['A.md', 'B.md'], elek: [['A.md', 'B.md']] };
const META: GrafMeta = {
  cimkek: { 'A.md': ['x'] },
  tulajdonsagok: {},
  cimke_csucsok: { x: { nev: 'x', db: 1 } },
  feloldatlan_elek: [['B.md', 'Hiány']],
};
// világ-koordináták (k = 1, tx = ty = 0 → a vászon pontjai): A, B, #x, Hiány
const POZ = Float32Array.from([100, 100, 200, 100, 100, 200, 200, 200]);

function keszit(adat: GrafAdat, extra: Partial<Bemenet> = {}, esemenyek: Partial<Esemenyek> = {}, poz = POZ) {
  const e: Esemenyek = { megnyit: vi.fn(), fizika: vi.fn(), ...esemenyek };
  const r = new GrafRajzolo(canvas, e);
  r_.push(r);
  r.meretValtozas();
  r.szinBeallit(SZINEK, '11px sans-serif');
  const lathato = lathatosag(adat, { lekerdezes: '', mellekletek: true, arvak: true, cimkek: true, letezoCsak: false }).lathato;
  r.bemenet({ adat, lathato, csoport: new Int16Array(adat.n).fill(-1), csoportSzinek: [], nyil: false, meretSzorzo: 1, vonalSzorzo: 1, ...extra });
  r.pozBe(poz.slice(0, 2 * adat.n), false);
  vi.advanceTimersByTime(80);
  return { r, e };
}

const adat = () => new GrafAdat(VALASZ, () => 'md', META);

describe('11-graph-02/03: a virtuális csúcsok alakja és színe', () => {
  it('a feloldatlan cél szaggatott gyűrű a saját színével; a címke kitöltött hatszög a címke színével', () => {
    keszit(adat());
    const stroke = rec.nev('stroke').filter((h) => h.strokeStyle === SZINEK.feloldatlan);
    expect(stroke.length).toBe(1);
    expect(stroke[0].dash).toEqual([2.5, 2.5]); // alakkal is jelez, nem csak színnel
    // a szaggatás a rajz végére visszaáll (a többi gyűrű és vonal folytonos)
    expect(rec.nev('setLineDash').at(-1)!.args[0]).toEqual([]);
    const fill = rec.nev('fill').filter((h) => h.fillStyle === SZINEK.cimke);
    expect(fill.length).toBe(1);
    // hatszög: 6 csúcs → moveTo + 5 lineTo egyetlen útvonalban a címke-vödörben
    const i = rec.hivasok.indexOf(fill[0]);
    const elotte = rec.hivasok.slice(0, i);
    const utolsoKezdet = elotte.map((h) => h.fn).lastIndexOf('beginPath');
    const ut = elotte.slice(utolsoKezdet).map((h) => h.fn);
    expect(ut.filter((f) => f === 'lineTo').length).toBe(5);
    expect(ut.filter((f) => f === 'arc').length).toBe(0);
  });

  it('a fájl-csúcsok színe és alakja változatlan (a jegyzet kitöltött kör a jegyzet színével)', () => {
    keszit(adat());
    const fill = rec.nev('fill').filter((h) => h.fillStyle === SZINEK.jegyzet);
    expect(fill.length).toBe(1);
    expect(rec.nev('arc').length).toBeGreaterThanOrEqual(2);
  });
});

describe('11-graph-04: csúcsméret és vonalvastagság', () => {
  const sugarak = () => rec.nev('arc').map((h) => h.args[2] as number);
  const csucsSugar = () => {
    // a jegyzet-vödör körei: az első `fill` jegyzet-színnel; a hozzá tartozó `arc`-ok az útvonalban
    const f = rec.nev('fill').find((h) => h.fillStyle === SZINEK.jegyzet)!;
    const i = rec.hivasok.indexOf(f);
    const ut = rec.hivasok.slice(0, i);
    const k = ut.map((h) => h.fn).lastIndexOf('beginPath');
    return ut.slice(k).filter((h) => h.fn === 'arc').map((h) => h.args[2] as number);
  };

  it('a csúcsméret-szorzó a rajzolt sugarat változtatja (a tartományon belül, a tartományra szorítva)', () => {
    keszit(adat(), { meretSzorzo: 1 });
    const alap = csucsSugar()[0];
    rec.torol();
    r_.pop()!.leallit();
    keszit(adat(), { meretSzorzo: 2 });
    const nagy = csucsSugar()[0];
    rec.torol();
    r_.pop()!.leallit();
    keszit(adat(), { meretSzorzo: 0.5 });
    const kicsi = csucsSugar()[0];
    rec.torol();
    r_.pop()!.leallit();
    keszit(adat(), { meretSzorzo: 99 });
    const szelso = csucsSugar()[0];
    expect(nagy).toBeGreaterThan(alap);
    expect(kicsi).toBeLessThanOrEqual(alap);
    expect(szelso).toBe(nagy); // a tartományon kívüli érték a maximumra szorul
    expect(sugarak().length).toBeGreaterThan(0);
  });

  it('a vonalvastagság-szorzó az élek vonalát változtatja', () => {
    const elVonal = () => {
      const s = rec.nev('stroke').filter((h) => h.strokeStyle === SZINEK.el);
      return s[0].lineWidth as number;
    };
    keszit(adat(), { vonalSzorzo: 1 });
    const alap = elVonal();
    rec.torol();
    r_.pop()!.leallit();
    keszit(adat(), { vonalSzorzo: 2 });
    expect(elVonal()).toBeCloseTo(alap * 2, 5);
    rec.torol();
    r_.pop()!.leallit();
    keszit(adat(), { vonalSzorzo: 0.3 });
    expect(elVonal()).toBeCloseTo(alap * 0.3, 5);
  });
});

describe('11-graph-04: szöveg-halványítás (a graph.json textFadeMultiplier-e is ide kötődik)', () => {
  // csillag: a középpont 25 szomszéddal (nagy csúcs), a levelek 1 fokúak (kicsik)
  const CS = ['Közép.md', ...Array.from({ length: 25 }, (_, i) => `L${i}.md`)];
  const csillag = () => new GrafAdat({ csucsok: CS, elek: CS.slice(1).map((u): [string, string] => ['Közép.md', u]) }, () => 'md', null);
  const pozCsillag = () => {
    const p = new Float32Array(2 * CS.length);
    CS.forEach((_, i) => {
      p[2 * i] = 400 + (i ? 220 * Math.cos(i) : 0);
      p[2 * i + 1] = 300 + (i ? 220 * Math.sin(i) : 0);
    });
    return p;
  };
  const feliratok = () => rec.nev('fillText').map((h) => h.args[0] as string);

  function rajzol(szovegHalvany?: number) {
    rec.torol();
    const a = csillag();
    const e: Esemenyek = { megnyit: vi.fn(), fizika: vi.fn() };
    const r = new GrafRajzolo(canvas, e);
    r_.push(r);
    r.meretValtozas();
    r.szinBeallit(SZINEK, '11px sans-serif');
    r.bemenet({ adat: a, lathato: new Uint8Array(a.n).fill(1), csoport: new Int16Array(a.n).fill(-1), csoportSzinek: [], nyil: false, meretSzorzo: 1, vonalSzorzo: 1, szovegHalvany });
    r.pozBe(pozCsillag(), false);
    vi.advanceTimersByTime(80);
    return feliratok();
  }

  it('alapérték (0): csak a nagy csúcs kap feliratot', () => {
    expect(rajzol(0)).toEqual(['Közép']);
    expect(rajzol(undefined)).toEqual(['Közép']); // a hiányzó érték = 0 (a régi viselkedés)
  });

  it('negatív érték: a kis csúcsok is kapnak feliratot; pozitív: a nagy csúcs sem', () => {
    const sok = rajzol(-3);
    expect(sok.length).toBeGreaterThan(10);
    expect(sok).toContain('Közép');
    expect(rajzol(3)).toEqual([]);
    expect(rajzol(-1).length).toBeGreaterThanOrEqual(rajzol(0).length);
  });

  it('a tartományon kívüli érték a tartományra szorul', () => {
    expect(rajzol(-50)).toEqual(rajzol(-3));
    expect(rajzol(50)).toEqual(rajzol(3));
  });
});

describe('11-graph-05: a csúcs menüje és a vászon eseményei', () => {
  const esemeny = (tipus: string, init: MouseEventInit & Record<string, unknown> = {}) => {
    const e = new MouseEvent(tipus, { bubbles: true, cancelable: true, ...init });
    canvas.dispatchEvent(e);
    return e;
  };

  it('jobb gomb egy csúcson: a menü kérése a csúcs indexével és vászon-helyével, a natív menü nélkül', () => {
    const menu = vi.fn();
    const kijeloles = vi.fn();
    keszit(adat(), {}, { menu, kijeloles });
    const e = esemeny('contextmenu', { clientX: 200, clientY: 100, button: 2 }); // B.md
    expect(e.defaultPrevented).toBe(true);
    expect(menu).toHaveBeenCalledWith(1, 200, 100);
    expect(kijeloles).toHaveBeenCalledWith(1); // a menü a kijelölt csúcsra vonatkozik
  });

  it('a feloldatlan és a címke-csúcs menüje is kérhető; az üres helyen nincs menü, de a natív sem jön elő', () => {
    const menu = vi.fn();
    keszit(adat(), {}, { menu });
    esemeny('contextmenu', { clientX: 200, clientY: 200 });
    esemeny('contextmenu', { clientX: 100, clientY: 200 });
    expect(menu.mock.calls.map((c) => c[0])).toEqual([3, 2]);
    menu.mockClear();
    const ures = esemeny('contextmenu', { clientX: 600, clientY: 500 });
    expect(menu).not.toHaveBeenCalled();
    expect(ures.defaultPrevented).toBe(true);
  });

  it('billentyűzetről: ContextMenu és Shift+F10 a kijelölt csúcs menüjét kéri a csúcs helyén; kijelölés nélkül semmit', () => {
    const menu = vi.fn();
    const { r } = keszit(adat(), {}, { menu });
    canvas.dispatchEvent(new KeyboardEvent('keydown', { key: 'ContextMenu', bubbles: true, cancelable: true }));
    expect(menu).not.toHaveBeenCalled();
    r.kijeloles(0);
    vi.advanceTimersByTime(40);
    const k1 = new KeyboardEvent('keydown', { key: 'ContextMenu', bubbles: true, cancelable: true });
    canvas.dispatchEvent(k1);
    expect(k1.defaultPrevented).toBe(true);
    canvas.dispatchEvent(new KeyboardEvent('keydown', { key: 'F10', shiftKey: true, bubbles: true, cancelable: true }));
    expect(menu.mock.calls).toEqual([[0, 100, 100], [0, 100, 100]]);
  });

  it('az Enter és a kattintás a csúcs helyét is átadja (a feloldatlan cél felajánlott műveletének menüjéhez)', () => {
    const megnyit = vi.fn();
    const { r } = keszit(adat(), {}, { megnyit });
    r.kijeloles(3);
    vi.advanceTimersByTime(40);
    canvas.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    expect(megnyit).toHaveBeenLastCalledWith(3, 'aktiv', 200, 200);
    canvas.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true }));
    expect(megnyit).toHaveBeenLastCalledWith(3, 'ujful', 200, 200);
    for (const t of ['pointerdown', 'pointerup'] as const) esemeny(t, { clientX: 100, clientY: 200, button: 0 });
    expect(megnyit).toHaveBeenLastCalledWith(2, 'aktiv', 100, 200);
  });

  it('a bal gombon kívüli gomb nem indít húzást (a jobb gomb a menüé)', () => {
    const fizika = vi.fn();
    keszit(adat(), {}, { fizika });
    esemeny('pointerdown', { clientX: 100, clientY: 100, button: 2 });
    esemeny('pointermove', { clientX: 150, clientY: 150 });
    esemeny('pointerup', { clientX: 150, clientY: 150, button: 2 });
    expect(fizika).not.toHaveBeenCalled();
  });
});
