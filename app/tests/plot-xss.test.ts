// A3-14 (Audit 3): a ```plot blokk feliratai (a felhasználó `"…"` címkéje, a CAS-szövegű aszimptota- és szélsőérték-
// feliratok) sosem kerülhetnek HTML-ként a DOM-ba. A valódi JSXGraph-fal (jsdom) futó próba: a JSXGraph szövegének
// alapja `display: 'html'` + `innerHTML`, ezért a rajzoló minden feliratot `display: 'internal'`, `parse: false`
// beállítással ad, és a lusta import után globálisan is kikapcsolja a feldolgozást. A CSP változatlan (a `style-src
// 'unsafe-inline'` miatt a DOM-befecskendezés — átfedés, hamis ablak — CSP nélkül is veszélyes).

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { RenderKornyezet } from '../src/szerkeszto/renderelok/regiszter';
import { JellemzoKliens } from '../src/szerkeszto/renderelok/plot/jellemzok';
import { biztonsagosit, rajzol, type Konyvtar } from '../src/szerkeszto/renderelok/plot/rajzolo';
import { hamisKonyvtar } from './plot-hamis';

const PAYLOAD = '<img src=x onerror=alert(1)><a href=javascript:alert(2) style=position:fixed;inset:0>átfedés</a>';
const kornyezet = (): RenderKornyezet => ({ ut: 'x.md', sotet: false, jel: new AbortController().signal });

// A valódi JSXGraph egyszer, bőséges korláttal töltődik (terhelés alatt az első import lassú, NAPLO); a próbák utána a
// feltételre várnak, nem fix alvásra.
let JXGModul: { default: Konyvtar };
beforeAll(async () => {
  JXGModul = (await import('jsxgraph')) as unknown as { default: Konyvtar };
}, 20_000);

afterEach(() => document.body.replaceChildren());

function kliensCasSzoveggel(): JellemzoKliens {
  return new JellemzoKliens(async (_ut, o) => ({
    ok: true,
    fuggvenyek: (o!.torzs as { fuggvenyek: string[] }).fuggvenyek.map((kif) => ({
      kif,
      allapot: 'ok',
      zerushelyek: [{ x: PAYLOAD, ertek: 1 }],
      szelsoertekek: [{ tipus: 'maximum', x: PAYLOAD, y: PAYLOAD, x_ertek: 0, y_ertek: 1 }],
      aszimptotak: [{ tipus: 'fuggoleges', egyenlet: PAYLOAD, ertek: 2 }],
      ferde_aszimptotak: [{ egyenlet: PAYLOAD, meredekseg: 1, eltolas: 0 }],
      numerikus: false,
      figyelmeztetesek: [],
    })),
  }));
}

describe('A3-14: a feliratok nem HTML-ként kerülnek a DOM-ba (valódi JSXGraph, jsdom)', () => {
  it('a felhasználó pont-címkéje és a CAS-szövegű feliratok szövegként látszanak, elem nem születik', async () => {
    const JXG = JXGModul.default;
    const cel = document.createElement('div');
    document.body.append(cel);
    const forras = `y = x^2\npont (1, 1) "${PAYLOAD}"\npont (2, 2) "ártalmatlan"`;
    const takarito = await rajzol(forras, cel, kornyezet(), JXG, { kliens: kliensCasSzoveggel() });
    // a tábla tényleg rajzolt (a próba nem üres DOM-ot vizsgál), a CAS-feliratok is megjöttek
    await vi.waitFor(
      () => {
        expect(cel.querySelector('svg')).not.toBeNull();
        expect(cel.textContent).toContain('ártalmatlan');
        expect(cel.textContent).toContain('<img src=x onerror=alert(1)>');
      },
      { timeout: 10_000 },
    );
    // sehol egyetlen befecskendezett elem
    expect(cel.querySelector('img')).toBeNull();
    expect(cel.querySelector('a')).toBeNull();
    expect(cel.querySelector('[onerror]')).toBeNull();
    expect(cel.querySelector('[href^="javascript"]')).toBeNull();
    // az `innerHTML`-ben (az attribútum-értékek nélkül: az `aria-label` szövege `<`-t kódolás nélkül hordozhat) nincs jelölés
    const jeloles = cel.innerHTML.replace(/="[^"]*"/g, '=""');
    expect(jeloles).not.toMatch(/<img/i);
    expect(jeloles).not.toMatch(/<a[\s>]/i);
    expect([...cel.querySelectorAll('*')].map((e) => e.tagName.toLowerCase())).not.toContain('img');
    // a felirat szövegként megjelenik (az „<” karakter kódolva: nem elem)
    expect(cel.textContent).toContain('<img src=x onerror=alert(1)>');
    takarito();
  });

  it('a JSXGraph globális beállításai: a szöveg nem értelmeződik, a JessieCode ki van kapcsolva', async () => {
    const JXG = JXGModul as unknown as { default: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
    biztonsagosit(JXG.default);
    expect(JXG.default.Options.text.parse).toBe(false);
    expect(JXG.default.Options.text.display).toBe('internal');
    expect(JXG.default.Options.jc.enabled).toBe(false);
  });
});

describe('A3-14: a rajzoló minden felirat-attribútumot biztonságosan ad át (hamis könyvtár)', () => {
  it('pont, egyenes és tengely: label.display = internal, label.parse = false', async () => {
    const k = hamisKonyvtar();
    const cel = document.createElement('div');
    document.body.append(cel);
    await rajzol(`y = 1/x\npont (1, 1) "${PAYLOAD}"`, cel, kornyezet(), k.konyvtar, { kliens: kliensCasSzoveggel() });
    const cimkezettek = () => k.naplo.hivasok.filter((h) => h.tipus === 'point' || h.tipus === 'line');
    // a CAS-feliratok (szélsőérték, aszimptota) a kliens válasza után kerülnek fel
    await vi.waitFor(() => expect(cimkezettek().some((h) => h.tipus === 'line')).toBe(true), { timeout: 5000 });
    const cimkezett = cimkezettek();
    expect(cimkezett.length).toBeGreaterThan(2);
    for (const h of cimkezett) {
      expect(h.attr.label, h.tipus).toMatchObject({ display: 'internal', parse: false });
    }
    const tengelyek = (k.naplo.init[0].attr as { defaultAxes: Record<string, { label: unknown }> }).defaultAxes;
    for (const t of Object.values(tengelyek)) expect(t.label).toMatchObject({ display: 'internal', parse: false });
  });

  it('a hívás a könyvtár globális beállításait is zárja (a hamis könyvtáron nincs `Options`: nem hibázik)', async () => {
    const k = hamisKonyvtar();
    const cel = document.createElement('div');
    document.body.append(cel);
    await expect(rajzol('y = x', cel, kornyezet(), k.konyvtar, { kliens: kliensCasSzoveggel() })).resolves.toBeTypeOf('function');
  });
});

describe('A3-14: a lusta import a globális beállításokat zárja (index.ts)', () => {
  it('a regisztrált renderelő a JSXGraph betöltése után nem hagy HTML-szöveg alapot', async () => {
    const { plotRenderelo } = await import('../src/szerkeszto/renderelok/plot/index');
    const JXG = (JXGModul as unknown as { default: { Options: { text: Record<string, unknown>; jc: Record<string, unknown> } } }).default;
    JXG.Options.text.parse = true; // a próba előtt szándékosan visszaállítva
    JXG.Options.jc.enabled = true;
    const cel = document.createElement('div');
    document.body.append(cel);
    const takarito = await plotRenderelo.render('y = x', cel, kornyezet());
    expect(JXG.Options.text.parse).toBe(false);
    expect(JXG.Options.text.display).toBe('internal');
    expect(JXG.Options.jc.enabled).toBe(false);
    takarito?.();
  });
});
