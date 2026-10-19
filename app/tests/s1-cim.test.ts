import { history, redo, undo } from '@codemirror/commands';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { cimTartalmaz, osszevontCim } from '../src/szerkeszto/cim';
import { cimElo } from '../src/szerkeszto/cimElo';

const allapot = (doc: string) => EditorState.create({ doc, extensions: [markdownNyelv()] });
const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); });

describe('U01: csak a fájlcímnek megfelelő első tartalmi H1', () => {
  it.each(['# Title\n\nBody', '\n# Title ###\nBody', 'Title\n=====\nBody', '---\nk: keep\n---\n\n# Title\nBody'])('%s', doc => {
    const state = allapot(doc);
    const c = osszevontCim(state, 'Folder/Title.md');
    expect(c).not.toBeNull();
    expect(cimTartalmaz(c, c!.from)).toBe(true);
    expect(cimTartalmaz(c, c!.to)).toBe(true);
    expect(cimTartalmaz(c, c!.to + 1)).toBe(false);
    expect(state.doc.toString()).toBe(doc);
  });
  it.each(['# Different\n# Title', 'Preface\n\n# Title', '## Title', '> # Title', '```\n# Title\n```',
    '# **Title**', '# [[Title]]', '# `Title`', '# title', '# Arviz', 'Title\n---'])('nem tüntet el külön tartalmat: %s', doc => {
    expect(osszevontCim(allapot(doc), doc === '# Arviz' ? 'Árvíz.md' : 'Title.md')).toBeNull();
  });
  it('NFC-eltérés egyezik, de a külön ékezet és kisbetű nem', () => {
    expect(osszevontCim(allapot('# A\u0301rvi\u0301z\n'), 'Árvíz.md')).not.toBeNull();
    expect(osszevontCim(allapot('# árvíz\n'), 'Árvíz.md')).toBeNull();
  });
});

describe('U01: LP atomikus megjelenítés, változatlan Markdown és szerkeszthető törzs', () => {
  function nyit(doc: string) {
    const fokusz = vi.fn();
    const kapcsolo = new Compartment();
    const v = new EditorView({ state: EditorState.create({ doc, extensions: [markdownNyelv(), history(), kapcsolo.of(cimElo('Title.md', fokusz))] }) });
    document.body.appendChild(v.dom); nezetek.push(v);
    return { v, fokusz, kapcsolo };
  }
  it('a címsor nem duplázódik, az elrejtés/kurzorigazítás nem ír és nem hoz létre undo-lépést', () => {
    const doc = '# Title\nBody';
    const { v } = nyit(doc);
    expect(v.contentDOM.textContent).not.toContain('# Title');
    expect(v.contentDOM.textContent).toContain('Body');
    v.dispatch({ selection: { anchor: 2 } });
    expect(v.state.selection.main.head).toBe(8);
    expect(v.state.doc.toString()).toBe(doc);
    expect(undo(v)).toBe(false);
  });
  it('a Backspace/ArrowUp a törzs elején a látható címre visz; nem törli a rejtett H1-et', () => {
    const { v, fokusz } = nyit('# Title\nBody');
    v.dispatch({ selection: { anchor: 8 } });
    for (const key of ['Backspace', 'ArrowUp']) v.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    expect(fokusz).toHaveBeenCalledTimes(2);
    expect(v.state.doc.toString()).toBe('# Title\nBody');
  });
  it('egyetlen, LF nélküli H1: az első törzsgépelés egy undo-lépés; a H1 bájtjai nem módosulnak', () => {
    const { v } = nyit('# Title');
    v.dispatch({ selection: { anchor: 7 } });
    expect(v.state.facet(EditorView.inputHandler).some(handler => handler(v, 7, 7, 'Body', () => v.state.update({ changes: { from: 7, insert: 'Body' } })))).toBe(true);
    expect(v.state.doc.toString()).toBe('# Title\nBody');
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('# Title');
    expect(redo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('# Title\nBody');
  });
  it('Source-ra váltás az eredeti H1-et azonnal visszaadja, visszaállás megint összevon; nincs tartalmi változás', () => {
    const { v, kapcsolo } = nyit('# Title\nBody');
    v.dispatch({ effects: kapcsolo.reconfigure([]) });
    expect(v.contentDOM.textContent).toContain('# Title');
    v.dispatch({ effects: kapcsolo.reconfigure(cimElo('Title.md', () => {})) });
    expect(v.contentDOM.textContent).not.toContain('# Title');
    expect(v.state.doc.toString()).toBe('# Title\nBody');
    expect(undo(v)).toBe(false);
  });
});
