import { acceptCompletion, CompletionContext, completionStatus, setSelectedCompletion, startCompletion } from '@codemirror/autocomplete';
import { history, undo } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { cimkeForras, cimkeHely } from '../src/szerkeszto/tulajdonsagok/cimkeKiegeszites';
import { fmKiegeszites } from '../src/szerkeszto/tulajdonsagok/fmKiegeszites';

const lista = [
  { cimke: 'Fizika', kis: 'fizika', db: 2, ossz: 10 },
  { cimke: 'Fizika/Mechanika', kis: 'fizika/mechanika', db: 4, ossz: 5 },
  { cimke: 'Mértan', kis: 'mértan', db: 3, ossz: 3 },
  { cimke: 'Bad tag', kis: 'bad tag', db: 20, ossz: 20 },
  { cimke: '123', kis: '123', db: 20, ossz: 20 },
];
const tar = () => ({ lista, kerjen: vi.fn(async () => {}) });
function context(doc: string, explicit = false): CompletionContext {
  const pos = doc.indexOf('|');
  return new CompletionContext(EditorState.create({ doc: doc.replace('|', ''), extensions: markdownNyelv() }), pos, explicit);
}
const nezetek: EditorView[] = [];
afterEach(() => { nezetek.splice(0).forEach((v) => v.destroy()); document.body.textContent = ''; });

describe('F11: törzs címke-kiegészítés', () => {
  it('csak whitespace/start # után indul; részleges Unicode és beágyazott címke', () => {
    expect(cimkeHely(context('#|'))).toEqual({ from: 1, to: 1, q: '' });
    expect(cimkeHely(context('Text #Fizika/Me|chanika!'))).toEqual({ from: 6, to: 22, q: 'Fizika/Me' });
    expect(cimkeHely(context('Text\u0085#é|'))).toEqual({ from: 6, to: 7, q: 'é' });
    for (const doc of ['word#fi|', '(#fi|', '##fi|', '\\#fi|', 'Text #e\u0301|', '\ufeff#fi|']) expect(cimkeHely(context(doc)), doc).toBeNull();
  });

  it('fuzzy, ékezetfüggetlen, beágyazott javaslatok és darabszám; hibás tagek kizárva', async () => {
    const t = tar();
    const forras = cimkeForras({ tar: t });
    const r = await forras(context('Text #mert|'));
    expect(r?.options.map((o) => o.label)).toEqual(['Mértan']);
    expect(r?.options[0].detail).toBe('3 jegyzetben');
    const beagyazott = await forras(context('#Fizika/Me|'));
    expect(beagyazott?.options[0].apply).toBe('Fizika/Mechanika');
    const ures = await forras(context('#|'));
    expect(ures?.options.map((o) => o.label)).toEqual(['Fizika', 'Fizika/Mechanika', 'Mértan']);
    expect(t.kerjen).toHaveBeenCalledTimes(3);
  });

  it.each([
    '---\ntitle: #fi|\n---',
    '```md\n#fi|\n```',
    '    #fi|',
    '` #fi|`',
    '$x #fi|$',
    '$$x #fi|$$',
    '$$\n#fi|\n$$',
    '%% #fi| %%',
    '%%\n#fi|\n%%',
    '[[Note #fi|]]',
    '![[Note #fi|]]',
    '[label #fi|](url)',
    '[label](<https://example.com/ #fi|>)',
    '<span title=" #fi|">text</span>',
  ])('védett helyen nem kér adatot: %s', async (doc) => {
    const t = tar();
    expect(await cimkeForras({ tar: t })(context(doc))).toBeNull();
    expect(t.kerjen).not.toHaveBeenCalled();
  });

  it('kikapcsolt modul és readonly nem kér adatot; futó kérés után is ellenőrzi a modult', async () => {
    const t = tar();
    const forras = cimkeForras({ tar: t, engedelyezett: () => false });
    expect(await forras(context('#fi|'))).toBeNull();
    const s = EditorState.create({ doc: '#fi', extensions: [markdownNyelv(), EditorState.readOnly.of(true)] });
    expect(await cimkeForras({ tar: t })(new CompletionContext(s, 3, true))).toBeNull();
    expect(t.kerjen).not.toHaveBeenCalled();
    let be = true;
    const valtas = { lista, kerjen: vi.fn(async () => { be = false; }) };
    expect(await cimkeForras({ tar: valtas, engedelyezett: () => be })(context('#fi|'))).toBeNull();
  });

  it('a frontmatter egyetlen override-jába kerül; valódi CM elfogadás és egy undo, szóköz nélkül', async () => {
    const v = new EditorView({ state: EditorState.create({ doc: 'Text #Fiz', selection: { anchor: 9 }, extensions: [markdownNyelv(), history(), fmKiegeszites({ cimkek: { tar: tar() } })] }), parent: document.body });
    nezetek.push(v);
    v.focus();
    startCompletion(v);
    await vi.waitFor(() => expect(completionStatus(v.state)).toBe('active'));
    v.dispatch({ effects: setSelectedCompletion(0) });
    await vi.waitFor(() => expect(acceptCompletion(v)).toBe(true));
    expect(v.state.doc.toString()).toBe('Text #Fizika');
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('Text #Fiz');
  });
});
