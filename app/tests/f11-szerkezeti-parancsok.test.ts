import { history, undo, redo } from '@codemirror/commands';
import { EditorSelection, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { markdownNyelv, forrasMod } from '../src/szerkeszto/beallitas';
import { feladatValt, fejezetBeallit, idezetValt, listaCiklus, listaValt } from '../src/szerkeszto/szerkezetiParancsok';
import { korbefog, formazasTorles } from '../src/szerkeszto/formazas';
import { linkParancs } from '../src/szerkeszto/notion/eszkoztar';
import { sablonElemek } from '../src/szerkeszto/notion/sablonok';
import { szerkezet } from './notion-segedek';

const nezetek: EditorView[] = [];
function nezet(doc: string, csakOlvashato = false): EditorView {
  const v = new EditorView({ state: EditorState.create({ doc, extensions: [markdownNyelv(), forrasMod(), history(), EditorState.allowMultipleSelections.of(true), EditorState.readOnly.of(csakOlvashato)] }), parent: document.body });
  nezetek.push(v);
  return v;
}
afterEach(() => { nezetek.splice(0).forEach((v) => v.destroy()); document.body.textContent = ''; });
const teljes = (v: EditorView) => v.dispatch({ selection: { anchor: 0, head: v.state.doc.length } });
const szoveg = (v: EditorView) => v.state.doc.toString();

describe('F11: feladatállapot és sorparancsok', () => {
  it('sima sor, többféle lista és Unicode feladatállapot; egy undo, majd redo', () => {
    const eredeti = 'plain\n* bullet\n3) ordered\n> - [ ] todo\n\t- [/] custom\n- [✅] unicode';
    const v = nezet(eredeti);
    teljes(v);
    expect(feladatValt(v)).toBe(true);
    expect(szoveg(v)).toBe('- [ ] plain\n* [ ] bullet\n3) [ ] ordered\n> - [x] todo\n\t- [ ] custom\n- [ ] unicode');
    expect(undo(v)).toBe(true);
    expect(szoveg(v)).toBe(eredeti);
    expect(redo(v)).toBe(true);
    expect(szoveg(v)).toContain('> - [x] todo');
  });

  it('több kijelölés, azonos sor egyszer, a következő sor eleje kizárva; irány és főkijelölés megmarad', () => {
    const v = nezet('- [ ] alpha beta\n- [x] gamma\nuntouched');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(8, 6), EditorSelection.cursor(12), EditorSelection.range(16, 28)], 1) });
    expect(feladatValt(v)).toBe(true);
    expect(szoveg(v)).toBe('- [x] alpha beta\n- [ ] gamma\nuntouched');
    expect(v.state.selection.ranges[0].anchor).toBeGreaterThan(v.state.selection.ranges[0].head);
    expect(v.state.selection.mainIndex).toBe(1);
  });

  it('kód, frontmatter, matek, HTML, táblázat és callout fejléc változatlan; próza átáll', () => {
    const vedett = '---\ntitle: Example\n---\n\n```md\n- [ ] code\n```\n\n$$\nx+y\n$$\n\n| a |\n|---|\n| b |\n\n<div>\nhtml\n</div>\n\n> [!note] Callout\n';
    const v = nezet(vedett + '\nbody');
    teljes(v);
    feladatValt(v);
    expect(szoveg(v).slice(0, vedett.length)).toBe(vedett);
    for (const sor of ['title: Example', '- [ ] code', 'x+y', '| a |', '|---|', '| b |', '<div>', 'html', '</div>', '> [!note] Callout']) expect(szoveg(v).split('\n')).toContain(sor);
    expect(szoveg(v)).toContain('- [ ] body');
  });

  it('csak olvasható vagy teljesen védett kijelölés nem módosul', () => {
    const v = nezet('plain', true);
    for (const muvelet of [feladatValt, (v: EditorView) => fejezetBeallit(v, 2), (v: EditorView) => listaValt(v, 'lista'), idezetValt]) expect(muvelet(v)).toBe(false);
    expect(szoveg(v)).toBe('plain');
    const kod = nezet('```\ncode\n```');
    teljes(kod);
    expect(feladatValt(kod)).toBe(false);
    expect(szoveg(kod)).toBe('```\ncode\n```');
  });

  it('heading 1–6 és szöveg, több sor és meglévő tárolók; kiválasztott szöveg azonos', () => {
    for (let szint = 1; szint <= 6; szint++) {
      const v = nezet('## alpha\n> beta\n- gamma');
      teljes(v);
      expect(fejezetBeallit(v, szint)).toBe(true);
      expect(szoveg(v)).toBe(`${'#'.repeat(szint)} alpha\n> ${'#'.repeat(szint)} beta\n- ${'#'.repeat(szint)} gamma`);
      expect(fejezetBeallit(v, 0)).toBe(true);
      expect(szoveg(v)).toBe('alpha\n> beta\n- gamma');
    }
  });

  it('setext cím átalakítása közben az aláhúzás eltűnik, a szomszéd szöveg nem olvad össze', () => {
    const v = nezet('Title\n=====\n\nnext');
    v.dispatch({ selection: { anchor: 2 } });
    expect(fejezetBeallit(v, 3)).toBe(true);
    expect(szoveg(v)).toBe('### Title\n\n\nnext');
    expect(szerkezet(szoveg(v)).setext).toBe(0);
    expect(undo(v)).toBe(true);
    expect(szoveg(v)).toBe('Title\n=====\n\nnext');
  });

  it('lista kapcsolás egységes, számozás és beágyazott behúzás; feladatállapot megmarad', () => {
    const v = nezet('alpha\n  beta\ngamma\n- [x] done');
    teljes(v);
    listaValt(v, 'szamozott');
    expect(szoveg(v)).toBe('1. alpha\n  1. beta\n2. gamma\n3. done');
    listaValt(v, 'szamozott');
    expect(szoveg(v)).toBe('alpha\n  beta\ngamma\ndone');
    listaValt(v, 'feladat');
    expect(szoveg(v)).toBe('- [ ] alpha\n  - [ ] beta\n- [ ] gamma\n- [ ] done');
    feladatValt(v);
    listaValt(v, 'feladat');
    expect(szoveg(v)).toBe('alpha\n  beta\ngamma\ndone');
  });

  it('listaciklus és idézet visszaállítása megtartja a belső jelölőket', () => {
    const v = nezet('alpha\nbeta');
    teljes(v);
    listaCiklus(v);
    expect(szoveg(v)).toBe('- alpha\n- beta');
    listaCiklus(v);
    expect(szoveg(v)).toBe('- [ ] alpha\n- [ ] beta');
    idezetValt(v);
    expect(szoveg(v)).toBe('> - [ ] alpha\n> - [ ] beta');
    idezetValt(v);
    listaCiklus(v);
    expect(szoveg(v)).toBe('alpha\nbeta');
  });

  it('kurzor a betűhöz tapad prefix beszúrása és törlése után', () => {
    const v = nezet('alpha');
    v.dispatch({ selection: { anchor: 3 } });
    fejezetBeallit(v, 4);
    expect(v.state.selection.main.head).toBe(8);
    fejezetBeallit(v, 0);
    expect(v.state.selection.main.head).toBe(3);
  });
});

describe('F11: forrás link és formázás', () => {
  it('⌘K kijelöléssel az URL-hez viszi a kurzort, a zárójelek escape-elve; egy undo', () => {
    const v = nezet('a [label] z');
    v.dispatch({ selection: { anchor: 2, head: 9 } });
    expect(linkParancs(v)).toBe(true);
    expect(szoveg(v)).toBe('a [\\[label\\]]() z');
    expect(v.state.selection.main.head).toBe(szoveg(v).indexOf(')'));
    expect(undo(v)).toBe(true);
    expect(szoveg(v)).toBe('a [label] z');
  });

  it('⌘K üres kijelölés és több kurzor; meglévő link URL-je kijelölődik', () => {
    const v = nezet('a b');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(0, 1), EditorSelection.range(2, 3)]) });
    linkParancs(v);
    expect(szoveg(v)).toBe('[a]() [b]()');
    expect(v.state.selection.ranges.map((r) => r.head)).toEqual([4, 10]);
    const ures = nezet('');
    linkParancs(ures);
    expect(szoveg(ures)).toBe('[]()');
    expect(ures.state.selection.main.head).toBe(1);
    const link = nezet('[label](https://example.com)');
    link.dispatch({ selection: { anchor: 3, head: 5 } });
    linkParancs(link);
    expect(link.state.sliceDoc(link.state.selection.main.from, link.state.selection.main.to)).toBe('https://example.com');
  });

  it('inline math üres soron nem nyel el későbbi szöveget; formázás törlése értelmezett jelölőkön', () => {
    const v = nezet('\n\nnext');
    v.dispatch({ selection: { anchor: 0 } });
    korbefog(v, '$');
    expect(szerkezet(szoveg(v)).db.MathBlock ?? 0).toBe(0);
    expect(szoveg(v)).toContain('next');
    const f = nezet('**bold** and *italic* and `code_*` and plain_*');
    teljes(f);
    expect(formazasTorles(f)).toBe(true);
    expect(szoveg(f)).toBe('bold and italic and code_* and plain_*');
    expect(undo(f)).toBe(true);
    expect(szoveg(f)).toBe('**bold** and *italic* and `code_*` and plain_*');
  });

  it('H4–6 a slash menüben egyszerű Markdown', () => {
    for (let n = 4; n <= 6; n++) expect(sablonElemek().find((e) => e.id === `h${n}`)!.sablon(new Date()).sorok).toEqual(['#'.repeat(n) + ' ']);
  });
});
