// F5: settings reconfigure the actual CodeMirror view without replacing the
// document, selections or undo history. Synthetic content only; no core/vault.
import { redo, undo, undoDepth } from '@codemirror/commands';
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorSelection, EditorState, type Extension } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { alapBeallitasok, type Beallitasok } from '../src/lib/beallitasok/tipusok';
import { bovitmenyek, opciokKapcsolo, szerkesztoOpciok } from '../src/szerkeszto/beallitas';
import { perjelNyit, perjelNyitva } from '../src/szerkeszto/notion/perjel';
import { eloTulajdonsagForras, torzsEleje } from '../src/szerkeszto/tulajdonsagok/elo.svelte';

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) { const hely = v.dom.parentElement; v.destroy(); hely?.remove(); } });

function allapot(doc: string, b: Beallitasok, tovabbi: Extension[] = []) {
  const state = EditorState.create({ doc, selection: { anchor: doc.length }, extensions: bovitmenyek({
    mod: 'elo', csakOlvashato: false, ut: 'Synthetic.md', cimke: 'Synthetic editor', beallitas: b, tovabbi,
  }) });
  ensureSyntaxTree(state, state.doc.length, 1000);
  return state;
}

function nezet(state: EditorState) {
  const hely = document.createElement('div'); document.body.append(hely);
  const v = new EditorView({ state, parent: hely }); nezetek.push(v); return v;
}

function valt(v: EditorView, b: Beallitasok) { v.dispatch({ effects: opciokKapcsolo.reconfigure(szerkesztoOpciok(b)) }); }
function gepel(v: EditorView, szoveg: string) {
  const r = v.state.selection.main;
  v.dispatch({ changes: { from: r.from, to: r.to, insert: szoveg }, selection: { anchor: r.from + szoveg.length }, userEvent: 'input.type' });
}

describe('live editor settings', () => {
  it('uses initial settings passed to bovitmenyek instead of hardcoded editor defaults', () => {
    const b = alapBeallitasok();
    b.szerkeszto.helyesiras = false; b.szerkeszto.tab_meret = 8; b.szerkeszto.olvashato_szelesseg = false;
    const v = nezet(allapot('A synthetic note.\n', b));
    expect(v.contentDOM.getAttribute('spellcheck')).toBe('false');
    expect(v.state.tabSize).toBe(8);
    expect(v.dom.getAttribute('data-olvashato-szelesseg')).toBe('false');
    expect(v.contentDOM.getAttribute('aria-label')).toBe('Synthetic editor');
  });

  it('changes spellcheck, tab width and readable width live while preserving document, selections and undo/redo', () => {
    const alap = alapBeallitasok();
    const eredeti = 'First paragraph.\n\nSecond paragraph.\n';
    const v = nezet(allapot(eredeti, alap));
    expect(v.contentDOM.getAttribute('spellcheck')).toBe('true');
    expect(v.dom.getAttribute('data-olvashato-szelesseg')).toBe('true');
    gepel(v, 'A new sentence.');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(1, 5), EditorSelection.cursor(20)], 1) });
    const doc = v.state.doc; const kijeloles = v.state.selection; const lepesek = undoDepth(v.state);
    expect(lepesek).toBeGreaterThan(0);
    const b = structuredClone(alap);
    b.szerkeszto.helyesiras = false; b.szerkeszto.tab_meret = 4; b.szerkeszto.olvashato_szelesseg = false;
    valt(v, b);
    expect(v.contentDOM.getAttribute('spellcheck')).toBe('false');
    expect(v.state.tabSize).toBe(4);
    expect(v.dom.getAttribute('data-olvashato-szelesseg')).toBe('false');
    expect(v.state.doc).toBe(doc); expect(v.state.selection.eq(kijeloles)).toBe(true);
    expect(undoDepth(v.state)).toBe(lepesek);
    valt(v, alap);
    expect(v.contentDOM.getAttribute('spellcheck')).toBe('true');
    expect(v.state.tabSize).toBe(2);
    expect(v.dom.getAttribute('data-olvashato-szelesseg')).toBe('true');
    expect(v.state.selection.eq(kijeloles)).toBe(true); expect(undoDepth(v.state)).toBe(lepesek);
    expect(undo(v)).toBe(true); expect(v.state.doc.toString()).toBe(eredeti);
    expect(redo(v)).toBe(true); expect(v.state.doc.toString()).toBe(eredeti + 'A new sentence.');
  });

  it.each(['editor', 'module'] as const)('closes an open slash menu and prevents typing/command reopening when disabled by %s', (hol) => {
    const alap = alapBeallitasok(); const v = nezet(allapot('Paragraph.\n\n', alap));
    gepel(v, '/'); expect(perjelNyitva(v.state)).toBe(true);
    expect(v.dom.querySelector('.nt-perjel')).not.toBeNull();
    const doc = v.state.doc; const kijeloles = v.state.selection; const lepesek = undoDepth(v.state);
    const b = structuredClone(alap);
    if (hol === 'editor') b.szerkeszto.perjel = false; else b.modulok.perjel = false;
    valt(v, b);
    expect(perjelNyitva(v.state)).toBe(false); expect(v.dom.querySelector('.nt-perjel')).toBeNull();
    expect(v.contentDOM.getAttribute('aria-expanded')).toBeNull();
    expect(v.state.doc).toBe(doc); expect(v.state.selection.eq(kijeloles)).toBe(true); expect(undoDepth(v.state)).toBe(lepesek);
    v.dispatch({ selection: { anchor: 0 } });
    const eredeti = v.state.doc.toString(); expect(perjelNyit(v)).toBe(false); expect(v.state.doc.toString()).toBe(eredeti);
    gepel(v, '/'); expect(perjelNyitva(v.state)).toBe(false); expect(v.state.doc.toString()).toBe('/' + eredeti);
    valt(v, alap);
    v.dispatch({ selection: { anchor: v.state.doc.length }, changes: { from: v.state.doc.length, insert: '\n\n' } });
    v.dispatch({ selection: { anchor: v.state.doc.length } });
    expect(perjelNyit(v)).toBe(true); expect(perjelNyitva(v.state)).toBe(true);
  });

  it('shows raw YAML and removes its invisible-widget cursor guard when the properties module is disabled', () => {
    const doc = '---\nStatus: Draft\nTags: [synthetic]\n---\n\nBody.\n';
    const alap = alapBeallitasok();
    const forras = eloTulajdonsagForras.of({ ut: 'Synthetic.md', nyitottsag: { nyitva: false } });
    let s = allapot(doc, alap, [forras]);
    const torzs = torzsEleje(s); expect(torzs).not.toBeNull();
    // Enabled properties guard the hidden YAML from an invisible text caret.
    s = s.update({ selection: { anchor: 0 } }).state;
    expect(s.selection.main.head).toBe(torzs);
    const b = structuredClone(alap); b.modulok.tulajdonsagok = false;
    s = s.update({ effects: opciokKapcsolo.reconfigure(szerkesztoOpciok(b)) }).state;
    expect(torzsEleje(s)).toBeNull(); expect(s.doc.toString()).toBe(doc);
    const v = nezet(s);
    expect(v.dom.querySelector('.cm-tulajdonsagok')).toBeNull();
    const sorok = [...v.contentDOM.querySelectorAll('.cm-line')].map(l => l.textContent);
    expect(sorok).toContain('Status: Draft'); expect(sorok).toContain('Tags: [synthetic]');
    v.dispatch({ selection: { anchor: 0 } }); expect(v.state.selection.main.head).toBe(0);
    const yamlPozicio = doc.indexOf('Draft');
    v.dispatch({ selection: { anchor: yamlPozicio } }); expect(v.state.selection.main.head).toBe(yamlPozicio);
    gepel(v, 'New '); expect(v.state.doc.toString()).toContain('Status: New Draft');
    expect(undo(v)).toBe(true); expect(v.state.doc.toString()).toBe(doc);
  });
});
