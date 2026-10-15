// Az elemző (C08): a képletszabály az index szabályát tükrözi (core/index/elemzo.py), a frontmatter az L39-ét;
// feladat bármely állapottal, `==`, lábjegyzet, wikilink (csak szerkezet), callout-felismerés, a táblázatban
// a képletben álló `|`. A CodeMirror-nyelv és a tiszta elemző fája azonos.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import type { SyntaxNode, Tree } from '@lezer/common';
import { describe, expect, it } from 'vitest';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { calloutAdat } from '../src/szerkeszto/markdown/callout';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { kepletek } from '../src/szerkeszto/markdown/fa';
import { feladatAllapot } from '../src/szerkeszto/markdown/feladat';

function fa(s: string): Tree {
  return obsidianElemzo.parse(s);
}

function kep(s: string) {
  return kepletek(fa(s), (a, b) => s.slice(a, b)).map((k) => ({ tex: k.tex, display: k.display, blokk: k.blokk }));
}

function nevek(t: Tree, s: string, nev: string): string[] {
  const ki: string[] = [];
  t.iterate({ enter: (n) => void (n.name === nev && ki.push(s.slice(n.from, n.to))) });
  return ki;
}

function elso(t: Tree, nev: string): SyntaxNode | null {
  let ki: SyntaxNode | null = null;
  t.iterate({
    enter: (n) => {
      if (ki) return false;
      if (n.name === nev) ki = n.node;
    },
  });
  return ki;
}

/** Az index soron belüli szabálya JavaScriptben (a `_KEPLET_SOR` és `_KEPLET_BLOKK` sorrendjében). */
function indexSzabaly(s: string): string[] {
  const ki: string[] = [];
  let maszk = s;
  for (const m of s.matchAll(/\$\$([\s\S]+?)\$\$/g)) {
    ki.push(m[1].trim());
    maszk = maszk.slice(0, m.index) + ' '.repeat(m[0].length) + maszk.slice(m.index! + m[0].length);
  }
  for (const m of maszk.matchAll(/\$(?<![\\$]\$)(?:(?=[^\s$])([^$\n]*?[^\s\\$])|([^\s$\\]))\$(?!\d)/g)) ki.push(m[1] ?? m[2]);
  return ki;
}

describe('képletek (az index szabálya)', () => {
  it.each([
    ['$x$', ['x']],
    ['a $x+1$ b', ['x+1']],
    ['$ x$', []],
    ['$x $', []],
    ['$x$5', []],
    ['a$b$c', ['b']],
    ['$5 és $6', []],
    ['$\\alpha$', ['\\alpha']],
    ['$a\\$', []],
    ['\\$x$', []],
    ['ár: 5$', []],
    ['$a$ és $b$', ['a', 'b']],
    ['$$x^2$$ közben', ['x^2']],
    ['előtte $$\\frac12$$ utána', ['\\frac12']],
    ['$\\text{gáz \\to rakéta}$', ['\\text{gáz \\to rakéta}']],
  ])('%s', (forras, varhato) => {
    expect(kep(forras).map((k) => k.tex.trim())).toEqual(varhato);
    expect(indexSzabaly(forras)).toEqual(varhato);
  });

  it('a sor eleji `$$` blokk több sorra; a lezáró nélküli nem képlet', () => {
    expect(kep('a\n\n$$\nx = 1\ny = 2\n$$\n\nb')).toEqual([{ tex: 'x = 1\ny = 2', display: true, blokk: true }]);
    expect(kep('$$x$$')).toEqual([{ tex: 'x', display: true, blokk: true }]);
    expect(kep('a\n$$\nx\n$$')).toEqual([{ tex: 'x', display: true, blokk: true }]); // a bekezdést megszakítja
    expect(kep('$$\nx\n\nnincs lezáró')).toEqual([]);
  });

  it('a soron belül nyitott `$$` lezáró sora nem szakítja meg a bekezdést', () => {
    expect(kep('Szöveg: $$\na = b\n$$ vége')).toEqual([{ tex: '\na = b\n', display: true, blokk: false }]);
  });

  it('az idézetben álló többsoros képlet a `>` jelek nélkül', () => {
    expect(kep('> $$\n> x = 1\n> $$')).toEqual([{ tex: 'x = 1', display: true, blokk: true }]);
  });

  it('kódban nincs képlet', () => {
    expect(kep('`$x$` és\n\n```\n$y$\n```')).toEqual([]);
  });

  it('a táblázatban a képletben álló `|` nem cellahatár (a vault 64 képlete)', () => {
    const s = '| Egyenlet | Megoldás |\n|---|---|\n| $|A| = 0$ | $A = 0$ |\n';
    const t = fa(s);
    expect(nevek(t, s, 'TableCell')).toEqual(['Egyenlet', 'Megoldás', '$|A| = 0$', '$A = 0$']);
    expect(kep(s).map((k) => k.tex)).toEqual(['|A| = 0', 'A = 0']);
  });

  it('a szöveges táblázat cellái a GFM szerint', () => {
    const s = '| a | b \\| c |\n|:-|-:|\n| 1 | 2 |';
    expect(nevek(fa(s), s, 'TableCell')).toEqual(['a', 'b \\| c', '1', '2']);
  });
});

describe('frontmatter (L39)', () => {
  it.each([
    ['---\nTags:\n  - a\n---\n# Cím', true, 'Tags:\n  - a'],
    ['---\n\n---\ntörzs', true, ''],
    ['---\nkulcs: 1\n---', true, 'kulcs: 1'],
    ['---\n---\nx', true, ''],                                          // C29.8 (T130): az üres blokk is frontmatter
    ['\ufeff---\na: 1\n---\nx', true, 'a: 1'],                        // a BOM-os blokk is
    ['--- \na: 1\n---\nx', false, null],                                // a szóközös nyitó nem (K79)
    ['---\nkulcs: 1\nlezáró nélkül', false, null],
    ['szöveg\n---\na: 1\n---', false, null],
  ])('%j → %s', (s, van, tartalom) => {
    const t = fa(s);
    const fm = elso(t, 'Frontmatter');
    expect(!!fm).toBe(van);
    if (fm) {
      const c = elso(t, 'FrontmatterContent');
      expect(c ? s.slice(c.from, c.to) : '').toBe(tartalom);
    }
  });
});

describe('feladatok, kiemelés, lábjegyzet, wikilink', () => {
  it('feladat bármely egykarakteres állapottal; lista nélkül nem feladat', () => {
    const s = '- [ ] a\n- [x] b\n- [/] c\n- [😀] d\n\n[ ] e';
    const jelek = nevek(fa(s), s, 'TaskMarker');
    expect(jelek).toEqual(['[ ]', '[x]', '[/]', '[😀]']);
    expect(jelek.map(feladatAllapot)).toEqual([' ', 'x', '/', '😀']);
  });

  it('`==kiemelés==`', () => {
    expect(nevek(fa('a ==kiemelt== b'), 'a ==kiemelt== b', 'Highlight')).toEqual(['==kiemelt==']);
    expect(nevek(fa('a == nem == b'), 'a == nem == b', 'Highlight')).toEqual([]);
  });

  it('lábjegyzet: hivatkozás és definíció a folytatósorral', () => {
    const s = 'Szöveg[^1] és[^jegyzet].\n\n[^1]: Az első.\n    Folytatás.\n\n[^jegyzet]: A második.';
    const t = fa(s);
    expect(nevek(t, s, 'FootnoteReference')).toEqual(['[^1]', '[^jegyzet]']);
    expect(nevek(t, s, 'FootnoteDefinition').map((x) => x.split('\n')[0])).toEqual(['[^1]: Az első.', '[^jegyzet]: A második.']);
    expect(nevek(t, s, 'FootnoteDefinition')[0]).toContain('Folytatás.');
    expect(nevek(fa('[^a b]'), '[^a b]', 'FootnoteReference')).toEqual([]);
  });

  it('wikilink és beágyazás: cél, fejezet, alias; a táblázat `\\|`-e elválasztó', () => {
    const s = '[[Mértani sorozat#Képlet|a képlet]] és ![[ábra.png]] és [[]] és [[nyitott';
    const t = fa(s);
    expect(nevek(t, s, 'Wikilink')).toEqual(['[[Mértani sorozat#Képlet|a képlet]]']);
    expect(nevek(t, s, 'Embed')).toEqual(['![[ábra.png]]']);
    expect(nevek(t, s, 'WikilinkTarget')).toEqual(['Mértani sorozat', 'ábra.png']);
    expect(nevek(t, s, 'WikilinkSubpath')).toEqual(['#Képlet']);
    expect(nevek(t, s, 'WikilinkAlias')).toEqual(['a képlet']);
    const tb = '| [[Cél\\|alias]] | b |\n|---|---|\n| 1 | 2 |';
    const t2 = fa(tb);
    expect(nevek(t2, tb, 'WikilinkTarget')).toEqual(['Cél']);
    expect(nevek(t2, tb, 'WikilinkAlias')).toEqual(['alias']);
  });

  it('a wikilinkben nem indul képlet', () => {
    expect(kep('[[jegyzet $x$]]')).toEqual([]);
  });
});

describe('callout', () => {
  const olvaso = (s: string) => (a: number, b: number) => s.slice(a, b);

  it('típus, hajtás, cím és a fejléc vége', () => {
    const s = '> [!warning]- Vigyázz\n> törzs\n> még';
    const a = calloutAdat(elso(fa(s), 'Blockquote')!, olvaso(s))!;
    expect(a.tipus).toBe('warning');
    expect(a.hajtas).toBe('-');
    expect(s.slice(a.cimFrom, a.cimTo)).toBe('Vigyázz');
    expect(s.slice(a.jelFrom, a.jelTo)).toBe('[!warning]-');
    expect(a.fejVeg).toBe(s.indexOf('\n'));
  });

  it('cím nélkül; sima idézet nem callout; egymásba ágyazva is', () => {
    const s = '> [!tip]\n> törzs';
    const a = calloutAdat(elso(fa(s), 'Blockquote')!, olvaso(s))!;
    expect(a.cimFrom).toBe(a.cimTo);
    const sima = '> csak idézet';
    expect(calloutAdat(elso(fa(sima), 'Blockquote')!, olvaso(sima))).toBeNull();
    const be = '> [!note] Külső\n> > [!bug] Belső\n> > törzs';
    const kulso = elso(fa(be), 'Blockquote')!;
    let belso: SyntaxNode | null = null;
    for (let c = kulso.firstChild; c; c = c.nextSibling) if (c.name === 'Blockquote') belso = c;
    expect(calloutAdat(belso!, olvaso(be))!.tipus).toBe('bug');
  });
});

describe('a CodeMirror-nyelv és a tiszta elemző azonos fát ad', () => {
  it('a felső szintű blokkok és a képletek egyeznek', () => {
    const s = [
      '---',
      'Tags: a',
      '---',
      '# Cím $x$',
      '',
      '> [!note] Cím',
      '> $$a$$',
      '',
      '| a | $|b|$ |',
      '|---|---|',
      '| 1 | 2 |',
      '',
      '```python',
      'print("$x$")',
      '```',
      '',
      '- [x] kész ==jó==[^1]',
      '',
      '[^1]: lj',
    ].join('\n');
    const state = EditorState.create({ doc: s, extensions: markdownNyelv() });
    const cm = ensureSyntaxTree(state, s.length, 5000)!;
    const tiszta = fa(s);
    const lista = (t: Tree) => {
      const ki: string[] = [];
      for (let c = t.topNode.firstChild; c; c = c.nextSibling) ki.push(`${c.name}:${c.from}-${c.to}`);
      return ki;
    };
    expect(lista(cm)).toEqual(lista(tiszta));
    expect(kepletek(cm, (a, b) => s.slice(a, b))).toEqual(kepletek(tiszta, (a, b) => s.slice(a, b)));
  });
});
