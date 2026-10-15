// A ```plot a kódblokk-regiszterben és a szerkesztőben (C35a): egyszeri regisztráció, az interaktív widget a Live
// Previewban („</>” gomb: a forrásba lép) és az Olvasóban (nincs forrás-gomb). A JSXGraph hamis (vi.mock).

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { MAGASSAG_PX } from '../src/szerkeszto/renderelok/plot/rajzolo';
import { plotRenderelo, plotTelepit } from '../src/szerkeszto/renderelok/plot/index';
import { kodRenderelok } from '../src/szerkeszto/renderelok/regiszter';
import { hamisKonyvtar } from './plot-hamis';

vi.mock('jsxgraph', () => ({ default: hamisKonyvtar().konyvtar }));

const JEGYZET = '# Cím\n\nElőtte.\n\n```plot\ny = x^2\n```\n\nUtána.';

let nezetek: EditorView[];
beforeEach(() => {
  nezetek = [];
  // a CAS-kérés ne menjen hálózatra a tesztben
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: true, fuggvenyek: [{ kif: 'x^2', allapot: 'ok', zerushelyek: [], szelsoertekek: [], aszimptotak: [], ferde_aszimptotak: [], numerikus: false, figyelmeztetesek: [] }] }), { status: 200 })));
});
afterEach(() => {
  nezetek.forEach((v) => v.destroy());
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

function szerkeszto(doc: string, kurzor = 0): EditorView {
  const state = EditorState.create({
    doc,
    selection: { anchor: kurzor },
    extensions: bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'Jegyzet.md', cimke: 'próba' }),
  });
  ensureSyntaxTree(state, state.doc.length, 5000);
  const v = new EditorView({ state, parent: document.body });
  nezetek.push(v);
  return v;
}

describe('regisztráció', () => {
  it('a plot egyszer regisztrálható, interaktív, a becsült magassága a rajzé; a leiratkozás működik', () => {
    const le = plotTelepit();
    try {
      const r = kodRenderelok.keres('plot');
      expect(r).toBe(plotRenderelo);
      expect(r!.interaktiv).toBe(true);
      expect(r!.becsultMagassag!('y = x')).toBe(MAGASSAG_PX);
      expect(kodRenderelok.keres('PLOT y')).toBe(plotRenderelo); // az info-sor első szava, kisbetűvel
      expect(() => plotTelepit()).toThrow(/már regisztrált/);
    } finally {
      le();
    }
    expect(kodRenderelok.keres('plot')).toBeUndefined();
  });
});

describe('Live Preview', () => {
  it('a kurzoron kívüli plot-blokk widgetként rajzolódik; a forrás gomb a blokkba lép', async () => {
    const le = plotTelepit();
    try {
      const v = szerkeszto(JEGYZET, 0);
      // terhelés alatt a fix alvás kevés volt (NAPLO): a feltételre várunk
      await vi.waitFor(() => expect(v.dom.querySelector('.cm-renderelt-blokk .plot-tabla')).not.toBeNull(), { timeout: 5000 });
      const blokk = v.dom.querySelector('.cm-renderelt-blokk .plot-blokk');
      expect(blokk).not.toBeNull();
      expect(v.dom.querySelector('.cm-renderelt-blokk .plot-tabla')!.getAttribute('aria-label')).toContain('y = x^2');
      const gomb = [...v.dom.querySelectorAll<HTMLButtonElement>('.plot-eszkoztar button')].find((b) => b.getAttribute('aria-label') === 'A blokk forrása')!;
      expect(gomb).toBeDefined();
      gomb.click();
      const kezdet = JEGYZET.indexOf('```plot');
      const fej = v.state.selection.main.head;
      expect(fej).toBeGreaterThanOrEqual(kezdet);
      expect(fej).toBeLessThanOrEqual(JEGYZET.indexOf('```\n\nUtána'));
    } finally {
      le();
    }
  });

  it('a hibás blokk a blokkban hibát mutat (a regiszter)', async () => {
    const le = plotTelepit();
    try {
      const v = szerkeszto('Előtte.\n\n```plot\ny = sin x\n```\n\nUtána.', 0);
      await vi.waitFor(() => expect(v.dom.querySelector('.cm-renderelt-blokk .renderelo-hiba')?.textContent).toContain('zárójel'), { timeout: 5000 });
    } finally {
      le();
    }
  });
});

describe('Olvasó', () => {
  it('a plot rajzolódik, forrás-gomb nélkül (nincs blokk-kapcsolat)', async () => {
    const le = plotTelepit();
    try {
      const lusta = LustaRajzolo.azonnali();
      const d = document.createElement('article');
      document.body.append(d);
      d.appendChild(dokumentumRenderel(obsidianElemzo.parse(JEGYZET), { olvas: (a, b) => JEGYZET.slice(a, b), ut: 'proba.md', lusta, elotag: 'p' }));
      await vi.waitFor(() => expect(d.querySelectorAll('.plot-eszkoztar button').length).toBe(3), { timeout: 5000 });
      expect(d.querySelector('.plot-blokk')).not.toBeNull();
      expect([...d.querySelectorAll('.plot-eszkoztar button')].map((b) => b.getAttribute('aria-label'))).toEqual(['Nagyítás (+)', 'Kicsinyítés (−)', 'Alaphelyzet (0)']);
    } finally {
      le();
    }
  });
});

