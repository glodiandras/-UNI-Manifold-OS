import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import type { Tree } from '@lezer/common';
import { afterEach, describe, expect, it } from 'vitest';
import { bovitmenyek, markdownNyelv } from '../src/szerkeszto/beallitas';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { blokkok } from '../src/szerkeszto/notion/blokkmodell';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

// F11 01-rendering-01: a bekezdés közepén nyíló, üres sorokon átnyúló és a lezáratlan `%%` megjegyzés.

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; });
function nezet(doc: string, kurzor = doc.length, mod: 'elo' | 'forras' = 'elo'): EditorView {
  const parent = document.createElement('div'); document.body.append(parent);
  const view = new EditorView({ parent, state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({ mod, ut: 'Host.md', cimke: 'Note', csakOlvashato: false }) }) });
  ensureSyntaxTree(view.state, doc.length, 5000); nezetek.push(view); return view;
}

type Csomopont = { nev: string; from: number; to: number };
function csomopontok(fa: Tree): Csomopont[] {
  const ki: Csomopont[] = []; fa.iterate({ enter(n) { ki.push({ nev: n.name, from: n.from, to: n.to }); } }); return ki;
}
const elemez = (doc: string) => csomopontok(obsidianElemzo.parse(doc));
const nevek = (doc: string) => elemez(doc).map(n => n.nev);
const megjegyzesek = (doc: string) => elemez(doc).filter(n => n.nev === 'ObsidianComment').map(n => doc.slice(n.from, n.to));
const felso = (doc: string) => { const ki: string[] = []; for (let c = obsidianElemzo.parse(doc).topNode.firstChild; c; c = c.nextSibling) ki.push(c.name); return ki; };
function olvaso(doc: string): DocumentFragment {
  return dokumentumRenderel(obsidianElemzo.parse(doc), { ut: 'Host.md', olvas: (a, b) => doc.slice(a, b), lusta: LustaRajzolo.azonnali() });
}
const bekezdesek = (doc: string) => [...olvaso(doc).querySelectorAll('p')].map(p => p.textContent!.replace(/\s+/g, ' ').trim());

describe('F11 %% megjegyzés: bekezdés közepén nyíló, üres sorokon átnyúló', () => {
  it('a bekezdés közepén nyíló megjegyzés az üres soron át a záró %%-ig tart, egy bekezdésben', () => {
    const doc = 'Before %%hidden\n\nstill hidden%% after\n\nVisible';
    expect(megjegyzesek(doc)).toEqual(['%%hidden\n\nstill hidden%%']);
    expect(felso(doc)).toEqual(['Paragraph', 'Paragraph']);
    const elso = obsidianElemzo.parse(doc).topNode.firstChild!;
    expect(doc.slice(elso.from, elso.to)).toBe('Before %%hidden\n\nstill hidden%% after');
  });

  it('több üres bekezdésen át is egy megjegyzés; az olvasó nem hagy üres <p>-t', () => {
    const doc = 'A %%one\n\ntwo\n\n\n\nthree%% B\n\nC';
    expect(megjegyzesek(doc)).toEqual(['%%one\n\ntwo\n\n\n\nthree%%']);
    expect(bekezdesek(doc)).toEqual(['A B', 'C']);
    const html = olvaso(doc);
    expect(html.textContent).not.toMatch(/one|two|three/);
    expect([...html.querySelectorAll('p')].filter(p => !p.textContent!.trim())).toHaveLength(0);
  });

  it('a sor elején nyíló, de szöveggel folytatódó záró sor is bekezdés (nem blokk), az eleje rejtett', () => {
    const doc = '%%x\n\ny%% tail\n\nNext';
    expect(megjegyzesek(doc)).toEqual(['%%x\n\ny%%']);
    expect(nevek(doc)).not.toContain('ObsidianCommentBlock');
    expect(bekezdesek(doc)).toEqual(['tail', 'Next']);
  });

  it('csak megjegyzésből álló bekezdés nem lesz üres <p> az olvasóban', () => {
    const doc = 'Lead\n\n%%a%% %%b\n\nc%%  \n\nEnd';
    expect(megjegyzesek(doc)).toEqual(['%%a%%', '%%b\n\nc%%']);
    expect(bekezdesek(doc)).toEqual(['Lead', 'End']);
    expect(olvaso(doc).querySelectorAll('p')).toHaveLength(2);
  });

  it('a lezáratlan %% a dokumentum végéig tart, az olvasóban minden utána rejtett', () => {
    const doc = 'Visible %%rest\n\n# Heading\n\n- [ ] task [[Link]] #tag\n\nTail';
    expect(megjegyzesek(doc)).toEqual([doc.slice(doc.indexOf('%%'))]);
    expect(felso(doc)).toEqual(['Paragraph']);
    expect(nevek(doc)).not.toContain('ATXHeading1');
    expect(bekezdesek(doc)).toEqual(['Visible']);
    expect(olvaso(doc).querySelector('h1')).toBeNull();
    // a korábbi `%%open` is megjegyzés lett (Obsidian: a lezáratlan %% a szöveg végéig rejt)
    expect(megjegyzesek('%%open')).toEqual(['%%open']);
    expect(olvaso('%%open').querySelectorAll('p')).toHaveLength(0);
  });

  it('több megjegyzés egy dokumentumban: soron belüli, átnyúló és lezáratlan vegyesen', () => {
    const doc = 'a %%1%% b %%2\n\n3%% c %%4\n\n5%% d\n\nE %%6%% F\n\nG %%7';
    expect(megjegyzesek(doc)).toEqual(['%%1%%', '%%2\n\n3%%', '%%4\n\n5%%', '%%6%%', '%%7']);
    expect(felso(doc)).toEqual(['Paragraph', 'Paragraph', 'Paragraph']);
    expect(bekezdesek(doc)).toEqual(['a b c d', 'E F', 'G']);
  });

  it('a megjegyzés belseje opaque: a benne álló fejezet, kerítés, idézet, lista nem blokk', () => {
    const doc = 'A %%x\n# H\n```\ncode\n```\n> quote\n- item\n\ny%% B\n\nEnd';
    const n = nevek(doc);
    for (const tiltott of ['ATXHeading1', 'FencedCode', 'Blockquote', 'BulletList']) expect(n).not.toContain(tiltott);
    expect(felso(doc)).toEqual(['Paragraph', 'Paragraph']);
    expect(bekezdesek(doc)).toEqual(['A B', 'End']);
  });

  it('kommenten belüli #tag, [[link]], embed és - [ ] feladat nem keletkezik a szerkesztő oldali elemzésben', () => {
    const doc = 'Text %%#tag [[Link]]\n\n- [ ] hidden task\n\n![[Embed]] [md](Note.md)%% end #visible\n\n- [ ] real task';
    const n = elemez(doc);
    expect(n.filter(x => x.nev === 'Hashtag').map(x => doc.slice(x.from, x.to))).toEqual(['#visible']);
    expect(n.filter(x => ['Wikilink', 'Embed', 'Link'].includes(x.nev))).toEqual([]);
    expect(n.filter(x => x.nev === 'Task').map(x => doc.slice(x.from, x.to))).toEqual(['[ ] real task']);
    expect(n.filter(x => x.nev === 'BulletList')).toHaveLength(1);
  });

  it('feladat szövegében nyíló megjegyzés is átnyúlik az üres soron, a feladat egy marad', () => {
    const doc = '- [ ] do %%x\n\n  y%% done\n- [x] next';
    const n = elemez(doc);
    expect(n.filter(x => x.nev === 'Task').map(x => doc.slice(x.from, x.to))).toEqual(['[ ] do %%x\n\n  y%% done', '[x] next']);
    expect(megjegyzesek(doc)).toEqual(['%%x\n\n  y%%']);
    expect(olvaso(doc).textContent).not.toMatch(/\bx\b|\by\b/);
  });

  it('idézetben az üres `>` soron át tart, a jelölők a megjegyzés gyerekei', () => {
    const doc = '> a %%x\n>\n> y%% b\n\nAfter';
    expect(megjegyzesek(doc)).toEqual(['%%x\n>\n> y%%']);
    expect(felso(doc)).toEqual(['Blockquote', 'Paragraph']);
    expect(olvaso(doc).querySelector('blockquote')!.textContent!.replace(/\s+/g, ' ').trim()).toBe('a b');
  });
});

describe('F11 %% megjegyzés: védett kontextusban a %% nem nyit', () => {
  it.each([
    ['kerítéses kód', '```md\n%%fence\n```\n\nafter'],
    ['YAML frontmatter', '---\nk: "%%yaml"\n---\n\nafter'],
    ['soron belüli kód', '`a %% b` c\n\nafter'],
    ['soron belüli kód több backtickkel', '``a %% ` b`` c\n\nafter'],
    ['soron belüli matek', '$a %% b$ c\n\nafter'],
    ['display matek soron belül', '$$a %% b$$ c\n\nafter'],
    ['matek blokk', '$$\n%%\n$$\n\nafter'],
    ['HTML blokk', '<div>\n%%\n</div>\n\nafter'],
    ['soron belüli HTML', '<span title="%%">x</span> c\n\nafter'],
    ['Markdown link-cél', '[label](a%%b.md) c\n\nafter'],
    ['Markdown link-cél csúcsos zárójelben', '[label](<a %% b.md>) c\n\nafter'],
    ['wikilink-cél', '[[A%%B]] ![[C%%D]] c\n\nafter'],
    ['escape-elt jelölők', '\\%%a\\%% c\n\nafter'],
  ])('%s', (_cim, doc) => {
    expect(nevek(doc).filter(n => n.startsWith('ObsidianComment'))).toEqual([]);
    expect(olvaso(doc).textContent).toContain('after');
  });

  it('a védett kontextus után nyíló megjegyzés továbbra is átnyúlik', () => {
    const doc = '`%%` [l](a%%b) %%open\n\nhidden%% shown';
    expect(megjegyzesek(doc)).toEqual(['%%open\n\nhidden%%']);
    expect(nevek(doc)).toContain('InlineCode'); expect(nevek(doc)).toContain('Link');
    expect(olvaso(doc).textContent).not.toContain('hidden');
    expect(olvaso(doc).textContent).toContain('shown');
  });
});

describe('F11 %% megjegyzés: Live Preview és Source', () => {
  it('LP halvány forrásként mutatja az átnyúló megjegyzést, a sorok szövege megmarad', () => {
    const doc = 'A %%x\n\ny%% B\n\nEnd';
    const v = nezet(doc);
    expect([...v.dom.querySelectorAll('.cm-line')].map(l => l.textContent)).toEqual(['A %%x', '', 'y%% B', '', 'End']);
    expect([...v.dom.querySelectorAll('.cm-jelolo')].map(e => e.textContent)).toEqual(['%%x', 'y%%']);
    expect(nezet(doc, doc.length, 'forras').dom.textContent).toContain('y%% B');
  });

  it('inkrementális elemzés: a záró %% beírása és törlése után a fa a friss elemzéssel egyezik', () => {
    const doc = 'A %%x\n\nB\n\n# C\n\nD';
    let s = EditorState.create({ doc, extensions: [markdownNyelv()] });
    const fa = (st: EditorState) => csomopontok(ensureSyntaxTree(st, st.doc.length, 5000)!);
    const friss = (szoveg: string) => elemez(szoveg);
    expect(fa(s)).toEqual(friss(doc));
    for (const [from, to, insert] of [[doc.indexOf('B') + 1, undefined, '%%'], [doc.indexOf('B') + 1, doc.indexOf('B') + 3, ''], [2, 4, ''], [2, undefined, '%%']] as const) {
      s = s.update({ changes: { from, to, insert } }).state;
      expect(fa(s), s.doc.toString()).toEqual(friss(s.doc.toString()));
    }
  });
});

describe('F11 %% megjegyzés: blokkmodell és PDF-kiemelés regresszió', () => {
  const KIEMELES = '%%manifold-kiemeles k-aaaaaa 0.1,0.2,0.3,0.02%%\n> Idézet\n> — [[X.pdf#page=1]] ^k-aaaaaa';

  it('az átnyúló megjegyzéses bekezdés egy mozgatható blokk, a kiemelés jelölője az idézeté marad', () => {
    const doc = `Jegyzet %%nyit\n\nmég%% vége\n\n${KIEMELES}\n\nUtána\n`;
    const s = EditorState.create({ doc, extensions: [markdownNyelv()] }); ensureSyntaxTree(s, doc.length, 5000);
    const bl = blokkok(s);
    expect(bl.map(b => [b.tipus, b.elsoSor, b.utolsoSor, b.jelolo, b.mozgathato])).toEqual([
      ['bekezdes', 1, 3, null, true],
      ['idezet', 6, 7, 5, true],
      ['bekezdes', 9, 9, null, true],
    ]);
    expect(bl[1].id).toBe('k-aaaaaa');
  });

  it('a lezáratlan megjegyzés után álló kiemelés is a megjegyzésé (nem mozgatható egység)', () => {
    const doc = `Jegyzet %%nyit\n\n${KIEMELES}\n`;
    const s = EditorState.create({ doc, extensions: [markdownNyelv()] }); ensureSyntaxTree(s, doc.length, 5000);
    const bl = blokkok(s);
    expect(bl).toHaveLength(1);
    expect(bl[0].mozgathato).toBe(false);
    expect(bl[0].jelolo).toBeNull();
  });

  it('a kiemelés jelölősora önálló megjegyzésblokk marad, az olvasó elrejti, az idézet látszik', () => {
    const doc = `Előtte %%a%% szöveg\n\n${KIEMELES}`;
    expect(felso(doc)).toEqual(['Paragraph', 'ObsidianCommentBlock', 'Blockquote']);
    const html = olvaso(doc);
    expect(html.textContent).not.toContain('manifold-kiemeles');
    expect(html.querySelector('blockquote')?.textContent).toContain('Idézet');
    expect(bekezdesek(doc)[0]).toBe('Előtte szöveg');
  });
});
