// C21 (5. pont): a képlet-OCR beszúrása a kurzorhoz — egy tranzakció, a kijelölést lecseréli; a hiányzó kép figyelmeztetés.
import { describe, expect, it } from 'vitest';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { history, undo } from '@codemirror/commands';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { kepletOcr, kepletSzoveg } from '../src/szerkeszto/kepletOcr';

function nezet(doc: string, from: number, to = from): EditorView {
  return new EditorView({ state: EditorState.create({ doc, selection: { anchor: from, head: to }, extensions: [history()] }) });
}

describe('képlet-OCR (C21)', () => {
  it('soron belüli és blokk-képlet', () => {
    expect(kepletSzoveg(' x^2 ')).toBe('$x^2$');
    expect(kepletSzoveg('\\begin{cases} a \\\\ b \\end{cases}')).toMatch(/^\$\$\n\\begin/);
  });

  it('a kurzorhoz szúr, a kijelölést lecseréli, a ⌘Z egy lépés', async () => {
    const v = nezet('a XX b', 2, 4);
    const ok = await kepletOcr(v, (async () => ({ latex: '\\frac{1}{2}', modell: 'glm_ocr' })) as never);
    expect(ok).toBe(true);
    expect(v.state.doc.toString()).toBe('a $\\frac{1}{2}$ b');
    expect(v.state.selection.main.head).toBe(2 + '$\\frac{1}{2}$'.length);
    undo(v);
    expect(v.state.doc.toString()).toBe('a XX b');
    v.destroy();
  });

  it('nincs kép a vágólapon: figyelmeztetés, a dokumentum nem változik', async () => {
    const v = nezet('ab', 1);
    const ok = await kepletOcr(v, (async () => {
      throw new ApiHiba(404, 'a vágólapon nincs kép');
    }) as never);
    expect(ok).toBe(false);
    expect(v.state.doc.toString()).toBe('ab');
    expect(ertesitesek.lista.some((e) => e.cim === 'A vágólapon nincs kép')).toBe(true);
    v.destroy();
  });
});
