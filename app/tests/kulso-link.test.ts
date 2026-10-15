// Külső link (C11a, audit M8): a megnyitható cím szűrése (csak http, https, mailto), a héj üzenete
// (`{tipus: 'megnyit', url}`), az Olvasó kattintása és a Live Preview kattintása/szintaxis-felismerése.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { kulsoCim, kulsoLink } from '../src/szerkeszto/linkek/kulso';
import { kulsoLinkAt } from '../src/szerkeszto/linkek/szerkeszto';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const uzenetek: unknown[] = [];

beforeEach(() => {
  uzenetek.length = 0;
  Object.defineProperty(window, 'webkit', {
    value: { messageHandlers: { manifold: { postMessage: (u: unknown) => uzenetek.push(u) } } },
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  delete (window as unknown as { webkit?: unknown }).webkit;
  vi.restoreAllMocks();
});

describe('kulsoCim: csak http, https és mailto', () => {
  it('megnyitható címek', () => {
    expect(kulsoCim('https://pelda.hu/a?b=1#c')).toBe('https://pelda.hu/a?b=1#c');
    expect(kulsoCim('http://pelda.hu')).toBe('http://pelda.hu/');
    expect(kulsoCim('mailto:valaki@pelda.hu')).toBe('mailto:valaki@pelda.hu');
    expect(kulsoCim('<https://pelda.hu>')).toBe('https://pelda.hu/');
    expect(kulsoCim('www.pelda.hu')).toBe('https://www.pelda.hu/');
  });

  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'file:///etc/passwd',
    'data:text/html,<script>1</script>',
    'tel:+36123',
    'ftp://pelda.hu',
    'Jegyzet.md',
    '../Jegyzet.md',
    '#fejezet',
    'http://',
    '',
    '   ',
  ])('tiltott vagy nem külső: %s', (url) => {
    expect(kulsoCim(url)).toBeNull();
  });
});

describe('kulsoLink: a héjon át megy', () => {
  it('megnyitható cím → egy `megnyit` üzenet a héjnak', () => {
    expect(kulsoLink('https://pelda.hu')).toBe(true);
    expect(uzenetek).toEqual([{ tipus: 'megnyit', url: 'https://pelda.hu/' }]);
  });

  it('tiltott séma → semmi nem megy el', () => {
    expect(kulsoLink('javascript:alert(1)')).toBe(false);
    expect(kulsoLink('file:///etc/passwd')).toBe(false);
    expect(uzenetek).toEqual([]);
  });

  it('héj nélkül (fejlesztői böngésző) új ablakban nyit, noopener-rel', () => {
    delete (window as unknown as { webkit?: unknown }).webkit;
    const nyit = vi.spyOn(window, 'open').mockReturnValue(null);
    expect(kulsoLink('https://pelda.hu')).toBe(true);
    expect(nyit).toHaveBeenCalledWith('https://pelda.hu/', '_blank', 'noopener,noreferrer');
  });
});

function renderel(s: string): HTMLElement {
  const d = document.createElement('article');
  d.appendChild(
    dokumentumRenderel(obsidianElemzo.parse(s), { olvas: (a, b) => s.slice(a, b), ut: 'proba.md', lusta: LustaRajzolo.azonnali(), elotag: 'p' }),
  );
  return d;
}

describe('az Olvasó DOM-ja', () => {
  it('a Markdown-link, az autolink és a csupasz URL kattintható, `href` nélkül', () => {
    const d = renderel('[szöveg](https://pelda.hu/x) és <https://masik.hu> és https://csupasz.hu/y és [levél](mailto:a@b.hu)');
    const linkek = [...d.querySelectorAll<HTMLElement>('a.link')];
    expect(linkek.map((a) => a.dataset.url)).toEqual(['https://pelda.hu/x', 'https://masik.hu/', 'https://csupasz.hu/y', 'mailto:a@b.hu']);
    for (const a of linkek) {
      expect(a.getAttribute('href')).toBeNull();
      expect(a.getAttribute('role')).toBe('link');
      expect(a.tabIndex).toBe(0);
    }
  });

  it('a relatív és a tiltott sémájú link csak szöveg marad (nincs `data-url`)', () => {
    const d = renderel('[belső](Jegyzet.md) [rossz](javascript:alert(1)) [fájl](file:///etc/passwd) [horgony](#fej)');
    expect(d.querySelectorAll('a.link').length).toBe(4);
    expect(d.querySelectorAll('a.link[data-url]').length).toBe(0);
  });
});

function nezet(doc: string, kurzor = doc.length): EditorView {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const v = new EditorView({
    state: EditorState.create({
      doc,
      selection: { anchor: kurzor },
      extensions: bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'proba.md', cimke: 'próba' }),
    }),
    parent: hely,
  });
  ensureSyntaxTree(v.state, v.state.doc.length, 5000);
  return v;
}

describe('az Olvasó kattintása', () => {
  it('a külső linkre kattintás a héjnak szól, és nem navigál', async () => {
    const v = nezet('[szöveg](https://pelda.hu/x) és https://csupasz.hu');
    const r = render(Olvaso, { props: { view: v, dok: { csakOlvashato: false } as never, ut: 'proba.md', valtozat: 0 } });
    const linkek = r.container.querySelectorAll<HTMLElement>('a.link[data-url]');
    expect(linkek.length).toBe(2);
    const ok = await fireEvent.click(linkek[0]);
    expect(ok).toBe(false); // preventDefault
    await fireEvent.click(linkek[1]);
    expect(uzenetek).toEqual([
      { tipus: 'megnyit', url: 'https://pelda.hu/x' },
      { tipus: 'megnyit', url: 'https://csupasz.hu/' },
    ]);
    v.destroy();
  });

  it('Enterre is nyit (billentyűzetről)', async () => {
    const v = nezet('[szöveg](https://pelda.hu/x)');
    const r = render(Olvaso, { props: { view: v, dok: { csakOlvashato: false } as never, ut: 'proba.md', valtozat: 0 } });
    await fireEvent.keyDown(r.container.querySelector('a.link[data-url]')!, { key: 'Enter' });
    expect(uzenetek).toEqual([{ tipus: 'megnyit', url: 'https://pelda.hu/x' }]);
    v.destroy();
  });
});

describe('a Live Preview külső linkjei (szintaxis)', () => {
  it('kulsoLinkAt: Markdown-link, autolink és csupasz URL — a kép, a relatív és a tiltott séma nem', () => {
    const doc = '[szöveg](https://a.hu/x) <https://b.hu> https://c.hu/y ![kép](https://d.hu/k.png) [rel](Jegyzet.md) [js](javascript:x)';
    const v = nezet(doc, 0);
    const at = (s: string, bent = 2) => kulsoLinkAt(v.state, doc.indexOf(s) + bent);
    expect(at('[szöveg]')?.url).toBe('https://a.hu/x');
    expect(at('https://a.hu/x', 4)?.url).toBe('https://a.hu/x'); // az URL-részen állva is a link
    expect(at('<https://b.hu>', 3)?.url).toBe('https://b.hu/');
    expect(at('https://c.hu/y', 3)?.url).toBe('https://c.hu/y');
    expect(at('![kép]', 3)).toBeNull();
    expect(at('https://d.hu/k.png', 3)).toBeNull();
    expect(at('[rel]')).toBeNull();
    expect(at('[js]')).toBeNull();
    expect(at('és', 0)).toBeNull();
    v.destroy();
  });
});
