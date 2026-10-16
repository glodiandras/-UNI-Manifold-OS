// 01-rendering-10: soron belüli lábjegyzet `^[szöveg]` — elemző, Olvasó (közös számozás, lap alji törzs) és Live Preview.
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; });

function csomopontok(doc: string, nev: string): string[] {
  const ki: string[] = [];
  obsidianElemzo.parse(doc).iterate({ enter: (n) => { if (n.name === nev) ki.push(doc.slice(n.from, n.to)); } });
  return ki;
}
function olvaso(doc: string) {
  const d = document.createElement('div');
  d.append(dokumentumRenderel(obsidianElemzo.parse(doc), { olvas: (a, b) => doc.slice(a, b), ut: 'Host.md', lusta: LustaRajzolo.azonnali(), elotag: 'x' }));
  return d;
}
function nezet(doc: string, kurzor = doc.length, mod: 'elo' | 'forras' = 'elo') {
  const parent = document.createElement('div'); document.body.append(parent);
  const v = new EditorView({ parent, state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({ mod, ut: 'Host.md', cimke: 'Note', csakOlvashato: false }) }) });
  ensureSyntaxTree(v.state, doc.length, 5000); nezetek.push(v); return v;
}

describe('elemzés', () => {
  it('a törzs Markdown, a belső link és wikilink nem zárja le; lezáratlan, kódban álló és escape-elt alak szöveg', () => {
    expect(csomopontok('A^[egy **vastag** [link](x.md) és [[Cél]]] vége', 'FootnoteInline')).toEqual(['^[egy **vastag** [link](x.md) és [[Cél]]]']);
    expect(csomopontok('A^[egy **vastag**] vége', 'StrongEmphasis')).toEqual(['**vastag**']);
    expect(csomopontok('Lezáratlan ^[szöveg', 'FootnoteInline')).toEqual([]);
    expect(csomopontok('`^[kód]`', 'FootnoteInline')).toEqual([]);
    expect(csomopontok('\\^[nem]', 'FootnoteInline')).toEqual([]);
    expect(csomopontok('[^ref] és ^[soron]', 'FootnoteReference')).toEqual(['[^ref]']);
    expect(csomopontok('Két ^[első] és ^[második `]` kód]', 'FootnoteInline')).toEqual(['^[első]', '^[második `]` kód]']);
  });
});

describe('Olvasó', () => {
  it('közös számozás a hivatkozásokkal, a törzs formázva a lap alján, oda-vissza ugrás adatai', () => {
    const d = olvaso('Első[^a] majd ^[soron *dőlt*] és[^a] végül ^[másik]\n\n[^a]: Definíció');
    const hiv = [...d.querySelectorAll<HTMLElement>('sup.labjegyzet-hiv a')];
    expect(hiv.map((a) => a.textContent)).toEqual(['1', '2', '1', '3']);
    const tetelek = [...d.querySelectorAll('section.labjegyzetek li')];
    expect(tetelek.map((li) => li.textContent?.replace('↩', ''))).toEqual(['Definíció', 'soron dőlt', 'másik']);
    expect(tetelek[1].querySelector('em')?.textContent).toBe('dőlt');
    expect(tetelek[1].id).toBe(`x-def-${hiv[1].dataset.labjegyzet}`);
    expect(d.querySelector('p')!.textContent).not.toContain('^[');
  });
});

describe('Live Preview', () => {
  it('nem aktív sorban sorszám, a törzs a súgóban; aktív sorban a forrás; Forrás módban jelölés', () => {
    const doc = 'Szöveg[^a] és ^[belső *dőlt*] itt\n\nMásik sor\n\n[^a]: x';
    const v = nezet(doc, doc.indexOf('Másik'));
    const w = v.dom.querySelector<HTMLElement>('.cm-labjegyzet-soron');
    expect(w?.textContent).toBe('2');
    expect(w?.title).toBe('belső *dőlt*');
    expect(v.dom.querySelector('.cm-line')!.textContent).not.toContain('^[');
    v.dispatch({ selection: { anchor: 2 } });
    expect(v.dom.querySelector('.cm-line')!.textContent).toContain('^[belső *dőlt*]');
    const f = nezet(doc, 0, 'forras');
    expect(f.dom.querySelector('.cm-labjegyzet-soron')?.textContent).toBe('^[belső *dőlt*]');
    expect(v.state.doc.toString()).toBe(doc);
  });
});
