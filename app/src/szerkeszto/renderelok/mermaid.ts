// Mermaid a ```` ```mermaid ```` blokkra, a kódblokk-regiszteren át. A Mermaid külön chunkban, csak az első
// diagramnál töltődik be. `securityLevel: 'strict'`: a feliratok DOMPurify-jal tisztítva, kattintás- és
// szkript-kezelő nincs. A színek a design-tokenekből jönnek; témaváltáskor minden látható diagram újrarajzol.
// A `mermaid.render` nem újrahívható biztonsággal: a renderelések egy sorban futnak.

import { lustaImportHiba } from '../../lib/vezerlo/epites.svelte';
import type { KodRenderelo, RenderKornyezet } from './regiszter';
import { sotetTema, temaFigyelo, tokenSzin } from './tema';

type MermaidApi = typeof import('mermaid').default;

let betoltes: Promise<MermaidApi> | null = null;
let lanc: Promise<unknown> = Promise.resolve();
let sorszam = 0;
const elo = new Set<{ forras: string; cel: HTMLElement; k: RenderKornyezet }>();
let figyeloLe: (() => void) | null = null;

function mermaid(): Promise<MermaidApi> {
  // a bukott import nem gyorsítótárazódik (a következő diagram újrapróbál); ha a dist közben újrafordult, újratöltés kell
  return (betoltes ??= import('mermaid').then(
    (m) => m.default,
    (e) => {
      betoltes = null;
      lustaImportHiba();
      throw e;
    },
  ));
}

function temaValtozok(): Record<string, string> {
  return {
    background: tokenSzin('--hatter'),
    primaryColor: tokenSzin('--hatter-hover'),
    primaryTextColor: tokenSzin('--szoveg'),
    primaryBorderColor: tokenSzin('--keret-eros'),
    secondaryColor: tokenSzin('--hatter-oldalsav'),
    tertiaryColor: tokenSzin('--hatter-aktiv'),
    lineColor: tokenSzin('--szoveg-masodlagos'),
    textColor: tokenSzin('--szoveg'),
    noteBkgColor: tokenSzin('--figyelmeztetes-hatter'),
    noteTextColor: tokenSzin('--szoveg'),
    fontFamily: getComputedStyle(document.documentElement).getPropertyValue('--betu-rendszer') || 'system-ui',
    fontSize: '14px',
  };
}

async function rajzol(forras: string, cel: HTMLElement, k: RenderKornyezet): Promise<void> {
  const m = await mermaid();
  const feladat = lanc.then(async () => {
    if (k.jel.aborted) return;
    m.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      darkMode: sotetTema(),
      themeVariables: temaValtozok(),
    });
    const { svg } = await m.render(`mermaid-${++sorszam}`, forras);
    if (k.jel.aborted) return;
    cel.innerHTML = svg;
  });
  lanc = feladat.catch(() => undefined);
  await feladat;
}

export const mermaidRenderelo: KodRenderelo = {
  nyelv: 'mermaid',
  becsultMagassag: (forras) => Math.min(600, 80 + 36 * forras.split('\n').length),
  async render(forras, cel, k) {
    cel.classList.add('mermaid-diagram');
    await rajzol(forras, cel, k);
    const rec = { forras, cel, k };
    elo.add(rec);
    figyeloLe ??= temaFigyelo(() => {
      for (const r of elo) void rajzol(r.forras, r.cel, r.k).catch(() => undefined);
    });
    return () => {
      elo.delete(rec);
      if (!elo.size && figyeloLe) {
        figyeloLe();
        figyeloLe = null;
      }
    };
  },
};
