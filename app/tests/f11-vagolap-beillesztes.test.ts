import { history, undo } from '@codemirror/commands';
import { EditorSelection, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ kerdez: vi.fn(async (_ut: string, _opciok?: unknown) => ({ azon: 'a'.repeat(32), ut: 'Assets/image.png', kesz: true })) }));
vi.mock('../src/lib/core/api', () => ({ kerdez: api.kerdez, ApiHiba: class extends Error {} }));
vi.mock('../src/lib/vault/linkek.svelte', () => ({ linkek: { linkCel: async () => 'image.png' } }));
vi.mock('../src/lib/ertesites/ertesites.svelte', () => ({ ertesitesek: { ertesit: vi.fn() } }));

import { csatolmanyBovitmeny } from '../src/szerkeszto/csatolmany';

const nezetek: EditorView[] = [];
function nezet(doc = '', csakOlvashato = false): EditorView {
  const v = new EditorView({ state: EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [csatolmanyBovitmeny('Note.md'), history(), EditorState.allowMultipleSelections.of(true), EditorState.readOnly.of(csakOlvashato)] }), parent: document.body });
  v.focus();
  nezetek.push(v);
  return v;
}
afterEach(() => { nezetek.splice(0).forEach((v) => v.destroy()); document.body.textContent = ''; api.kerdez.mockClear(); });

function beilleszt(v: EditorView, html: string, sima: string, fajlok: File[] = []): Event {
  const e = new Event('paste', { bubbles: true, cancelable: true });
  Object.defineProperty(e, 'clipboardData', { value: { files: fajlok, types: ['text/html', 'text/plain'], getData: (tipus: string) => tipus === 'text/html' ? html : ['text/plain', 'text', 'Text'].includes(tipus) ? sima : '' } });
  v.contentDOM.dispatchEvent(e);
  return e;
}

describe('F11: valódi CodeMirror paste esemény', () => {
  it('HTML → Markdown, egy undo, hálózati/API-hívás nélkül', () => {
    const v = nezet('Before ');
    const e = beilleszt(v, '<p><strong>Bold</strong> and <em>italic</em></p>', 'Bold and italic');
    expect(e.defaultPrevented).toBe(true);
    expect(v.state.doc.toString()).toBe('Before **Bold** and *italic*');
    expect(api.kerdez).not.toHaveBeenCalled();
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('Before ');
  });

  it('Shift+Mod+V a text/plain tartalmat illeszti be formázás nélkül', () => {
    const v = nezet();
    v.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key: 'v', code: 'KeyV', metaKey: true, shiftKey: true, bubbles: true, cancelable: true }));
    beilleszt(v, '<p><strong>Bold</strong></p>', 'Bold');
    expect(v.state.doc.toString()).toBe('Bold');
    expect(api.kerdez).not.toHaveBeenCalled();
    v.contentDOM.dispatchEvent(new KeyboardEvent('keyup', { key: 'v', bubbles: true }));
    beilleszt(v, '<p><strong>Next</strong></p>', 'Next');
    expect(v.state.doc.toString()).toBe('Bold**Next**');
  });

  it('fájlt és HTML-t együtt tartalmazó vágólapon a fájl-import nyer', async () => {
    const v = nezet();
    const f = new File([new Uint8Array([1, 2, 3])], 'image.png', { type: 'image/png' });
    beilleszt(v, '<img src="https://example.com/image.png" alt="HTML image">', 'HTML image', [f]);
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('![[image.png]]'));
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    expect(api.kerdez.mock.calls[0][0]).toBe('/api/vault/import');
    expect(v.state.doc.toString()).not.toContain('example.com');
  });

  it('HTML beillesztése minden kijelölést lecserél, a főkijelölés megmarad', () => {
    const v = nezet('alpha + beta');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(0, 5), EditorSelection.range(8, 12)], 1) });
    beilleszt(v, '<strong>new</strong>', 'new');
    expect(v.state.doc.toString()).toBe('**new** + **new**');
    expect(v.state.selection.mainIndex).toBe(1);
    expect(v.state.selection.ranges.length).toBe(2);
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('alpha + beta');
  });

  it('readOnly nem ír szöveget és nem importál fájlt', async () => {
    const v = nezet('Locked', true);
    beilleszt(v, '<strong>new</strong>', 'new');
    beilleszt(v, '<p>image</p>', 'image', [new File(['x'], 'image.png', { type: 'image/png' })]);
    expect(v.state.doc.toString()).toBe('Locked');
    expect(api.kerdez).not.toHaveBeenCalled();
  });

  it('nem használható HTML a text/plain fallbackot használja; URL kijelölésre beillesztése megmarad', () => {
    const v = nezet();
    beilleszt(v, '<script>unsafe()</script>', 'Fallback');
    expect(v.state.doc.toString()).toBe('Fallback');
    v.dispatch({ selection: { anchor: 0, head: 8 } });
    beilleszt(v, '<a href="https://example.com">https://example.com</a>', 'https://example.com');
    expect(v.state.doc.toString()).toBe('[Fallback](<https://example.com>)');
  });
});
