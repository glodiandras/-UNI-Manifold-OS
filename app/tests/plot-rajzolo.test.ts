// A ```plot rajzolója (C35a): a JSXGraph-burok hamis könyvtárral — a tábla felépítése a rajztervből, a színek csak
// tokenből, a görbék adata az aktuális ablakra, a CAS-jelölők, a billentyűk, a ⌘+görgő, a hover-érték, a témaváltás
// újraépítése, a takarítás. A valódi könyvtár működését a K104 (valódi felület, mindkét téma) és a Browser-pane-es
// próba igazolja (docs/C35-TERV.md 5. fejezet).

import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RenderKornyezet } from '../src/szerkeszto/renderelok/regiszter';
import { JellemzoKliens, type Jellemzok } from '../src/szerkeszto/renderelok/plot/jellemzok';
import { rajzol } from '../src/szerkeszto/renderelok/plot/rajzolo';
import { hamisKonyvtar } from './plot-hamis';
import { forras as forrasok } from './plot-segedek';

// minden szín a `tokenSzin`-en át jön: a hamis feloldás a token nevét adja vissza, így a teszt látja a forrást
vi.mock('../src/szerkeszto/renderelok/tema', async (eredeti) => ({
  ...(await eredeti<typeof import('../src/szerkeszto/renderelok/tema')>()),
  tokenSzin: (token: string) => `<${token}>`,
}));

/* eslint-disable @typescript-eslint/no-explicit-any */
function kornyezet(jel = new AbortController().signal): RenderKornyezet {
  return { ut: 'x.md', sotet: false, jel };
}

function jellemzokKliens(valasz: Partial<Jellemzok>[] | null): JellemzoKliens {
  return new JellemzoKliens(async (_ut, o) => {
    if (valasz === null) throw new Error('503');
    const f = (o!.torzs as { fuggvenyek: string[] }).fuggvenyek;
    return {
      ok: true,
      fuggvenyek: f.map((kif, i) => ({
        kif,
        allapot: 'ok',
        zerushelyek: [],
        szelsoertekek: [],
        aszimptotak: [],
        ferde_aszimptotak: [],
        numerikus: false,
        figyelmeztetesek: [],
        ...valasz[i],
      })),
    };
  });
}

const varj = (ms = 30) => new Promise((f) => setTimeout(f, ms));

afterEach(() => {
  document.body.replaceChildren();
  delete document.documentElement.dataset.tema;
});

async function indit(forras: string, kliens = jellemzokKliens([{}, {}, {}])) {
  const k = hamisKonyvtar();
  const cel = document.createElement('div');
  document.body.append(cel);
  const takarito = await rajzol(forras, cel, kornyezet(), k.konyvtar, { kliens });
  await varj();
  return { ...k, cel, takarito };
}

describe('felépítés', () => {
  it('a tábla az ablakból, tengellyel, rácsal, a navigáció és a szerzői jog nélkül', async () => {
    const { naplo } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x^2');
    expect(naplo.init).toHaveLength(1);
    const a = naplo.init[0].attr;
    expect(a.boundingbox).toEqual([-4, 10, 4, -2]);
    expect(a.axis).toBe(true);
    expect(a.showNavigation).toBe(false);
    expect(a.showCopyright).toBe(false);
    expect(a.zoom.wheel).toBe(false); // a nagyítás a sajátunk (⌘+görgő), a sima görgetés a jegyzetet lapozza
    expect(a.pan).toMatchObject({ enabled: true, needShift: false });
    expect(a.keyboard.enabled).toBe(false);
    expect(a.renderer).toBe('svg');
  });

  it('a görbék, a kitöltés és a határgörbe, a pontok létrejönnek', async () => {
    const { naplo } = await indit('y = x\ny > x^2\npont (1, 2) "P"');
    const tipusok = naplo.hivasok.map((h) => h.tipus);
    expect(tipusok.filter((t) => t === 'curve')).toHaveLength(1 + 2); // egy függvény + (kitöltés, határ)
    expect(naplo.hivasok.some((h) => h.tipus === 'point' && h.attr.name === 'P')).toBe(true);
  });

  it('a görbe adata az aktuális ablakból számolódik (updateDataArray)', async () => {
    const { naplo, tablak } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x^2');
    const g = naplo.hivasok.find((h) => h.tipus === 'curve')!.elem;
    g.updateDataArray();
    const veges = g.dataX.filter((x: number) => !Number.isNaN(x));
    expect(Math.min(...veges)).toBeGreaterThanOrEqual(-4);
    expect(Math.max(...veges)).toBeLessThanOrEqual(4);
    tablak[0].setBoundingBox([0, 10, 2, -2]); // közelítés
    g.updateDataArray();
    expect(Math.min(...g.dataX.filter((x: number) => !Number.isNaN(x)))).toBeGreaterThanOrEqual(0);
    expect(Math.max(...g.dataX.filter((x: number) => !Number.isNaN(x)))).toBeLessThanOrEqual(2);
  });

  it('a színek csak design-tokenekből jönnek (tokenSzin); a forrásban nincs szín-literál', async () => {
    const { naplo } = await indit('y = x\ny > 1\npont (1, 2)');
    let db = 0;
    const szinek = (o: any): string[] => {
      const ki: string[] = [];
      for (const [k, v] of Object.entries(o ?? {})) {
        if (/^(strokeColor|fillColor)$/.test(k) && typeof v === 'string') ki.push(v);
        else if (v && typeof v === 'object' && !Array.isArray(v)) ki.push(...szinek(v));
      }
      return ki;
    };
    for (const h of naplo.hivasok) for (const sz of szinek(h.attr)) { expect(sz, `${h.tipus}`).toMatch(/^<--[a-z0-9-]+>$/); db++; }
    for (const i of naplo.init) for (const sz of szinek(i.attr)) { expect(sz).toMatch(/^<--[a-z0-9-]+>$/); db++; }
    expect(db).toBeGreaterThan(8);
    const kod = forrasok.rajzolo.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(kod).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(kod).not.toMatch(/\brgba?\(/);
    expect(forrasok.css.replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it('a tábla elérhető: role="img", leírás, fókuszálható', async () => {
    const { cel } = await indit('y = x^2');
    const d = cel.querySelector<HTMLElement>('.plot-tabla')!;
    expect(d.getAttribute('role')).toBe('img');
    expect(d.getAttribute('aria-label')).toContain('y = x^2');
    expect(d.tabIndex).toBe(0);
  });
});

describe('hibák', () => {
  it('a teljesen hibás és az üres blokk hibát dob (a regiszter a blokkban mutatja)', async () => {
    const { konyvtar } = hamisKonyvtar();
    const cel = document.createElement('div');
    await expect(rajzol('y = sin x', cel, kornyezet(), konyvtar)).rejects.toThrow(/zárójel/);
    await expect(rajzol('', cel, kornyezet(), konyvtar)).rejects.toThrow(/üres/);
    await expect(rajzol('valami', cel, kornyezet(), konyvtar)).rejects.toThrow(/ismeretlen/);
  });

  it('a részben hibás blokk él, halk figyelmeztetéssel', async () => {
    const { cel, naplo } = await indit('y = x^2\nvalami ismeretlen');
    expect(naplo.init).toHaveLength(1);
    const f = cel.querySelector<HTMLElement>('.plot-figyelmeztetes')!;
    expect(f.textContent).toBe('1 sor kihagyva');
    expect(f.title).toContain('ismeretlen vagy hibás sor');
  });

  it('a megszakított jel után nem rajzol', async () => {
    const { konyvtar, naplo } = (() => hamisKonyvtar())();
    const v = new AbortController();
    v.abort();
    const t = await rajzol('y = x', document.createElement('div'), kornyezet(v.signal), konyvtar);
    t();
    expect(naplo.init).toHaveLength(0);
  });
});

describe('CAS-jelölők', () => {
  const jellemzok: Partial<Jellemzok>[] = [
    {
      zerushelyek: [{ x: '-2', ertek: -2 }, { x: '2', ertek: 2 }],
      szelsoertekek: [{ x: '0', y: '-4', x_ertek: 0, y_ertek: -4, tipus: 'minimum' }],
      aszimptotak: [{ egyenlet: 'y=1', tipus: 'vizszintes', ertek: 1 }],
    },
  ];

  it('a zérushely, a szélsőérték és az aszimptota a CAS megérkezése után rajzolódik', async () => {
    const { naplo, cel } = await indit('y = x^2 - 4', jellemzokKliens(jellemzok));
    await varj();
    const pontok = naplo.hivasok.filter((h) => h.tipus === 'point');
    expect(pontok.map((h) => h.attr.name)).toEqual(['−2', '2', 'min (0; −4)']);
    expect(pontok[0].attr.fillColor).not.toBe(pontok[2].attr.fillColor); // a zérushely üres (háttérszín), a szélsőérték teli
    const egyenes = naplo.hivasok.find((h) => h.tipus === 'line')!;
    expect(egyenes.attr).toMatchObject({ straightFirst: true, straightLast: true, dash: 2, name: 'y=1' });
    expect(cel.querySelector('.plot-tabla')!.getAttribute('aria-label')).toContain('zérushely x = −2');
  });

  it('a CAS hibája esetén a rajz jelölések nélkül él', async () => {
    const { naplo } = await indit('y = x^2 - 4', jellemzokKliens(null));
    await varj();
    expect(naplo.init).toHaveLength(1);
    expect(naplo.hivasok.filter((h) => h.tipus === 'point')).toHaveLength(0);
  });

  it('a nézet kilépése az elemzett ablakból új kérést indít (és a régi jelölők törlődnek)', async () => {
    vi.useFakeTimers();
    try {
      const kerdez = vi.fn(async (_ut: string, o?: { torzs?: unknown }) => ({
        ok: true,
        fuggvenyek: (o!.torzs as { fuggvenyek: string[] }).fuggvenyek.map((kif) => ({
          kif, allapot: 'ok', zerushelyek: [{ x: '1', ertek: 1 }], szelsoertekek: [], aszimptotak: [], ferde_aszimptotak: [], numerikus: false, figyelmeztetesek: [],
        })),
      }));
      const k = hamisKonyvtar();
      const cel = document.createElement('div');
      document.body.append(cel);
      await rajzol('x in [-4, 4]\ny in [-2, 10]\ny = x', cel, kornyezet(), k.konyvtar, { kliens: new JellemzoKliens(kerdez as any) });
      await vi.advanceTimersByTimeAsync(10);
      expect(kerdez).toHaveBeenCalledTimes(1);
      k.tablak[0].setBoundingBox([100, 10, 108, -2]);
      k.naplo.esemenyek['boundingbox']();
      await vi.advanceTimersByTimeAsync(500);
      expect(kerdez).toHaveBeenCalledTimes(2);
      expect(k.naplo.torolt.length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('interakció', () => {
  it('a + nagyít, a 0 az alaphelyzet; a nyilak mozgatnak', async () => {
    const { cel, naplo, tablak } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x');
    const d = cel.querySelector<HTMLElement>('.plot-tabla')!;
    d.dispatchEvent(new KeyboardEvent('keydown', { key: '+', bubbles: true, cancelable: true }));
    const nagyitott = tablak[0].getBoundingBox();
    expect(nagyitott[2] - nagyitott[0]).toBeCloseTo(8 * 0.8, 9);
    d.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    expect(tablak[0].getBoundingBox()[0]).toBeGreaterThan(nagyitott[0]);
    d.dispatchEvent(new KeyboardEvent('keydown', { key: '0', bubbles: true, cancelable: true }));
    expect(tablak[0].getBoundingBox()).toEqual([-4, 10, 4, -2]);
    expect(naplo.bbox.length).toBe(3);
  });

  it('a más billentyű és a módosítós billentyű nem érinti a tábla ablakát', async () => {
    const { cel, naplo } = await indit('y = x');
    const d = cel.querySelector<HTMLElement>('.plot-tabla')!;
    d.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    d.dispatchEvent(new KeyboardEvent('keydown', { key: '+', metaKey: true, bubbles: true }));
    expect(naplo.bbox).toHaveLength(0);
  });

  it('a sima görgetés a jegyzeté, a ⌘/Ctrl+görgő nagyít és megakadályozza a lapozást', async () => {
    const { cel, tablak } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x');
    const d = cel.querySelector<HTMLElement>('.plot-tabla')!;
    const sima = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true });
    d.dispatchEvent(sima);
    expect(sima.defaultPrevented).toBe(false);
    expect(tablak[0].getBoundingBox()).toEqual([-4, 10, 4, -2]);
    const nagyit = new WheelEvent('wheel', { deltaY: -200, ctrlKey: true, bubbles: true, cancelable: true });
    d.dispatchEvent(nagyit);
    expect(nagyit.defaultPrevented).toBe(true);
    const bb = tablak[0].getBoundingBox();
    expect(bb[2] - bb[0]).toBeLessThan(8);
  });

  it('a hover az egér alatti értéket mutatja a legközelebbi görbén, kilépéskor eltűnik', async () => {
    const { cel } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x^2 "f"');
    const d = cel.querySelector<HTMLElement>('.plot-tabla')!;
    const tip = cel.querySelector<HTMLElement>('.plot-hover-ertek')!;
    expect(tip.hidden).toBe(true);
    const e = new Event('pointermove', { bubbles: true }) as any;
    e.__ux = 2;
    e.__uy = 4;
    e.buttons = 0;
    d.dispatchEvent(e);
    expect(tip.hidden).toBe(false);
    expect(tip.textContent).toBe('f: x = 2; y = 4');
    d.dispatchEvent(new Event('pointerleave'));
    expect(tip.hidden).toBe(true);
  });

  it('a gombok: +, −, alaphelyzet; a „</>” csak a Live Preview-ban (blokk-kapcsolattal)', async () => {
    const { cel } = await indit('y = x');
    const gombok = [...cel.querySelectorAll('.plot-eszkoztar button')].map((b) => b.getAttribute('aria-label'));
    expect(gombok).toEqual(['Nagyítás (+)', 'Kicsinyítés (−)', 'Alaphelyzet (0)']);
    const k = hamisKonyvtar();
    const cel2 = document.createElement('div');
    const forrasba = vi.fn();
    await rajzol('y = x', cel2, { ...kornyezet(), blokk: { csakOlvashato: false, csere: () => true, forrasba } }, k.konyvtar, { kliens: jellemzokKliens([{}]) });
    const gomb = [...cel2.querySelectorAll<HTMLButtonElement>('.plot-eszkoztar button')].find((b) => b.getAttribute('aria-label') === 'A blokk forrása')!;
    gomb.click();
    expect(forrasba).toHaveBeenCalledTimes(1);
  });
});

describe('téma és takarítás', () => {
  it('témaváltáskor a tábla az aktuális ablakkal újraépül', async () => {
    const { naplo, tablak } = await indit('x in [-4, 4]\ny in [-2, 10]\ny = x');
    tablak[0].setBoundingBox([-1, 5, 3, 0]);
    document.documentElement.dataset.tema = 'sotet';
    await varj(20);
    expect(naplo.szabad).toBe(1);
    expect(naplo.init).toHaveLength(2);
    expect(naplo.init[1].attr.boundingbox).toEqual([-1, 5, 3, 0]);
  });

  it('a takarító felszabadítja a táblát, kiveszi a DOM-ot, és leállítja a téma-figyelőt', async () => {
    const { naplo, cel, takarito } = await indit('y = x');
    takarito();
    expect(naplo.szabad).toBe(1);
    expect(cel.querySelector('.plot-blokk')).toBeNull();
    document.documentElement.dataset.tema = 'sotet';
    await varj(20);
    expect(naplo.init).toHaveLength(1); // nem épül újra
    takarito(); // idempotens
  });
});
