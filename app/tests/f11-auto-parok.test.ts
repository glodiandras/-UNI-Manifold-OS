import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { history, historyKeymap, undo, redo } from '@codemirror/commands';
import { Compartment, EditorSelection, EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { autoParEngedelyezett, autoParokBovitmeny } from '../src/szerkeszto/autoParok';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { szerkezet } from './notion-segedek';

const nezetek: EditorView[] = [];
const kapcsolo = new Compartment();
function nezet(doc = '', kurzor = doc.length, csakOlvashato = false): EditorView {
  const v = new EditorView({ state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: [markdownNyelv(), history(), closeBrackets(), autoParokBovitmeny(), EditorState.allowMultipleSelections.of(true), EditorState.languageData.of(() => [{ closeBrackets: { brackets: ['(', '{', "'", '"', '`'] } }]), keymap.of([...closeBracketsKeymap, ...historyKeymap]), kapcsolo.of(autoParEngedelyezett.of(true)), EditorState.readOnly.of(csakOlvashato)] }), parent: document.body });
  nezetek.push(v);
  return v;
}
afterEach(() => { nezetek.splice(0).forEach((v) => v.destroy()); document.body.textContent = ''; });
function gepel(v: EditorView, szoveg: string): void {
  for (const c of szoveg) {
    const r = v.state.selection.main;
    const kezelt = v.state.facet(EditorView.inputHandler).some((h) => h(v, r.from, r.to, c, () => v.state.update(v.state.replaceSelection(c))));
    if (!kezelt) v.dispatch(v.state.update(v.state.replaceSelection(c), { userEvent: 'input.type' }));
  }
}
const szoveg = (v: EditorView) => v.state.doc.toString();

describe('F11: Markdown automatikus párok', () => {
  it.each(['*', '_', '~', '=', '$'])('%s nyit, szöveg beírható, záró karakter átugrik', (jel) => {
    const elotag = jel === '~' || jel === '$' ? 'Text ' : '';
    const v = nezet(elotag);
    gepel(v, jel);
    expect(szoveg(v)).toBe(elotag + jel + jel);
    expect(v.state.selection.main.head).toBe(elotag.length + 1);
    gepel(v, 'word' + jel);
    expect(szoveg(v)).toBe(elotag + jel + 'word' + jel);
    expect(v.state.selection.main.head).toBe(szoveg(v).length);
  });

  it.each(['*', '_', '~', '='])('%s dupla jelölője természetesen begépelhető és bezárható', (jel) => {
    const elotag = jel === '~' ? 'Text ' : '';
    const v = nezet(elotag);
    gepel(v, jel + jel);
    expect(szoveg(v)).toBe(elotag + jel.repeat(4));
    expect(v.state.selection.main.head).toBe(elotag.length + 2);
    gepel(v, 'word' + jel + jel);
    expect(szoveg(v)).toBe(elotag + jel.repeat(2) + 'word' + jel.repeat(2));
    expect(v.state.selection.main.head).toBe(szoveg(v).length);
  });

  it('kijelölés körbefogása több kurzornál megőrzi az irányt és az elsődleges kijelölést', () => {
    const v = nezet('alpha beta');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(5, 0), EditorSelection.range(6, 10)], 1) });
    gepel(v, '*');
    expect(szoveg(v)).toBe('*alpha* *beta*');
    expect(v.state.selection.mainIndex).toBe(1);
    expect(v.state.selection.ranges.map((r) => [r.anchor, r.head])).toEqual([[6, 1], [9, 13]]);
    expect(undo(v)).toBe(true);
    expect(szoveg(v)).toBe('alpha beta');
    expect(redo(v)).toBe(true);
    expect(szoveg(v)).toBe('*alpha* *beta*');
  });

  it('nem párosít szó belsejében, escape után, meglévő kézi zárón, vagy % PDF-jelölőn', () => {
    const szo = nezet('someword');
    gepel(szo, '_');
    expect(szoveg(szo)).toBe('someword_');
    const esc = nezet('\\');
    gepel(esc, '*');
    expect(szoveg(esc)).toBe('\\*');
    const kezi = nezet('*word*', 5);
    gepel(kezi, '*');
    expect(szoveg(kezi)).toBe('*word**');
    const pdf = nezet('');
    gepel(pdf, '%%');
    expect(szoveg(pdf)).toBe('%%');
  });

  it.each([
    ['```md\ntext\n```', 10],
    ['---\ntitle: Example\n---', 10],
    ['$formula$', 4],
    ['`source`', 4],
    ['$$\nformula\n$$', 6],
    ['[text](https://example.com)', 16],
    ['[[Note|Label]]', 8],
    ['![[Note|Label]]', 9],
    ['%% comment here %%', 7],
    ['%%\ncomment here\n%%', 8],
  ])('védett szövegben közönséges karakter marad: %s', (doc, kurzor) => {
    const v = nezet(doc as string, kurzor as number);
    gepel(v, '*');
    expect(szoveg(v)).toBe((doc as string).slice(0, kurzor as number) + '*' + (doc as string).slice(kurzor as number));
  });

  it('kijelölt kódot nem alakít át, vegyes próza/kód kurzoroknál csak a próza párosul', () => {
    const v = nezet('plain \n\n```\ncode\n```');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.cursor(6), EditorSelection.cursor(14)]) });
    gepel(v, '*');
    expect(szoveg(v)).toBe('plain **\n\n```\nco*de\n```');
    const kod = nezet('`code`');
    kod.dispatch({ selection: { anchor: 1, head: 5 } });
    gepel(kod, '*');
    expect(szoveg(kod)).toBe('`*`');
  });

  it('Backspace eltávolítja az üres dupla párt egy lépésben, undo visszahozza', () => {
    const v = nezet();
    gepel(v, '**');
    const e = new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true });
    v.contentDOM.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    expect(szoveg(v)).toBe('');
    expect(undo(v)).toBe(true);
    expect(szoveg(v)).toBe('****');
  });

  it('élő letiltás megőrzi a dokumentumot és historyt; readOnly kezelő nem ír', () => {
    const v = nezet();
    gepel(v, '*word*');
    const elotte = szoveg(v);
    v.dispatch({ effects: kapcsolo.reconfigure(autoParEngedelyezett.of(false)) });
    expect(szoveg(v)).toBe(elotte);
    gepel(v, ' $');
    expect(szoveg(v)).toBe('*word* $');
    expect(undo(v)).toBe(true);
    const zarolt = nezet('text', 0, true);
    const kezelt = zarolt.state.facet(EditorView.inputHandler).some((h) => h(zarolt, 0, 0, '*', () => zarolt.state.update({ changes: { from: 0, insert: '*' } })));
    expect(kezelt).toBe(false);
    expect(szoveg(zarolt)).toBe('text');
  });

  it('normál zárójelek és backtick a meglévő CM-párosítást használják', () => {
    const v = nezet();
    gepel(v, '(');
    expect(szoveg(v)).toBe('()');
    expect(v.state.selection.main.head).toBe(1);
    const kod = nezet();
    gepel(kod, '`');
    expect(szoveg(kod)).toBe('``');
  });

  it.each(['', '> ', '- '])('üres tárolósorban a ~/$ nem nyel el későbbi szöveget: %s', (elotag) => {
    const hatul = '\n\nText\n\n```md\ncode\n```\n\n$$\nx\n$$';
    for (const jel of ['~', '$']) {
      const v = nezet(elotag + hatul, elotag.length);
      gepel(v, jel);
      expect(szoveg(v)).toBe(elotag + jel + hatul);
      expect(szerkezet(szoveg(v)).db.FencedCode).toBe(1);
      expect(szerkezet(szoveg(v)).db.MathBlock).toBe(1);
    }
  });
});
