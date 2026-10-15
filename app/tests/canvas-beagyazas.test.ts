// A `![[x.canvas]]` beágyazás (C14): a canvas kicsinyített, csak olvasható képe, és a renderelő a regiszterben.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { canvasBeagyazasRenderelo, canvasKep } from '../src/canvas/beagyazas';

const CANVAS = JSON.stringify({
  nodes: [
    { id: 'g', type: 'group', x: -20, y: -60, width: 700, height: 300, label: 'Ókor', color: '4' },
    { id: 'a', type: 'file', file: 'T01/Görög.md', x: 0, y: 0, width: 300, height: 200 },
    { id: 'b', type: 'text', text: '# Cím\nmásodik sor', x: 360, y: 0, width: 300, height: 200, color: '#ff0000' },
  ],
  edges: [
    { id: 'e1', fromNode: 'a', toNode: 'b', fromSide: 'right', toSide: 'left' },
    { id: 'e2', fromNode: 'b', toNode: 'a', fromEnd: 'arrow', toEnd: 'none' },
    { id: 'e3', fromNode: 'a', toNode: 'nincs' },
  ],
});

afterEach(() => vi.unstubAllGlobals());

describe('canvas-beágyazás', () => {
  it('a kép: node-onként keret és felirat, élenként út és nyíl, a viewBox a befoglaló doboz', () => {
    const kep = canvasKep(CANVAS);
    if (typeof kep === 'string') throw new Error(kep);
    expect(kep.querySelectorAll('rect.kep-node').length).toBe(3);
    expect([...kep.querySelectorAll('text')].map((t) => t.textContent)).toEqual(['Ókor', 'Görög', 'Cím']);
    expect(kep.querySelectorAll('path.kep-el').length).toBe(2); // a lógó él nem rajzolódik
    expect(kep.querySelectorAll('polygon.kep-nyil').length).toBe(2);
    expect(kep.getAttribute('viewBox')).toBe('-60 -100 780 380');
    expect((kep.querySelector('rect.kep-text') as SVGElement).style.getPropertyValue('--szin')).toBe('#ff0000');
  });

  it('hibás canvas: magyar üzenet; üres canvas: üres kép', () => {
    expect(canvasKep('{"nodes":')).toMatch(/nem érvényes JSON/);
    const ures = canvasKep('{}');
    expect(typeof ures).not.toBe('string');
  });

  it('a renderelő a fájlt a core-ból tölti, és kattintásra nyílik', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      expect(u.pathname).toBe('/api/vault/fajl');
      return new Response(JSON.stringify({ ut: u.searchParams.get('ut'), tartalom: CANVAS, hash: 'h', jel: '', mtime: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    const kont = document.createElement('span');
    await canvasBeagyazasRenderelo.render(
      { tipus: 'canvas', ut: 'Térképek/Ókor.canvas', alcel: null } as never,
      { cel: 'Ókor.canvas', alcel: null, alias: null, beagyazas: true, from: 0, to: 0 },
      kont,
      { forras: 'Jegyzet.md' },
    );
    expect(kont.className).toBe('beagyazas beagyazas-canvas');
    expect(kont.querySelector('.beagyazas-cim')?.textContent).toBe('Ókor.canvas');
    expect(kont.querySelector('svg.canvas-kep')?.getAttribute('aria-label')).toBe('Canvas: Ókor.canvas');
  });
});
