// 01-rendering-13: a tördelt lista-, feladat- és idézetsorok függő behúzása (a látható előtag mért szélessége).
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { elotagVege } from '../src/szerkeszto/elo/fuggoBehuzas';

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; vi.restoreAllMocks(); });

const ext = (mod: 'elo' | 'forras' = 'forras') => bovitmenyek({ mod, ut: 'Host.md', cimke: 'Note', csakOlvashato: false });
function allapot(doc: string) {
  const s = EditorState.create({ doc, extensions: ext() });
  ensureSyntaxTree(s, doc.length, 5000);
  return s;
}
const elotag = (doc: string, n: number) => {
  const s = allapot(doc);
  const v = elotagVege(s, s.doc.line(n).from);
  return v === null ? null : s.sliceDoc(s.doc.line(n).from, v);
};

describe('a látható előtag', () => {
  it('listajel, számozott jel, feladat, behúzott elem és idézet', () => {
    expect(elotag('- Elem szöveg', 1)).toBe('- ');
    expect(elotag('12. Számozott', 1)).toBe('12. ');
    expect(elotag('- [x] Kész feladat', 1)).toBe('- [x] ');
    expect(elotag('- a\n\t- Beágyazott', 2)).toBe('\t- ');
    expect(elotag('> Idézet szöveg', 1)).toBe('> ');
    expect(elotag('> - [ ] Idézett feladat', 1)).toBe('> - [ ] ');
    expect(elotag('- a\n\n  Folytató bekezdés', 3)).toBe('  ');
  });

  it('nincs előtag: sima bekezdés, üres elem, kód, frontmatter, táblázat', () => {
    expect(elotag('Sima bekezdés', 1)).toBeNull();
    expect(elotag('- ', 1)).toBeNull();
    expect(elotag('```\n  - nem lista\n```', 2)).toBeNull();
    expect(elotag('    behúzott kód', 1)).toBeNull();
    expect(elotag('---\n  a: 1\n---', 2)).toBeNull();
    expect(elotag('| a |\n|---|\n| - b |', 3)).toBeNull();
  });
});

describe('a függő behúzás díszítése', () => {
  it.each(['elo', 'forras'] as const)('%s: a mért szélesség a sor `--fuggo-behuzas` értéke; a mérés nem ismétlődik változatlan értékre', async (mod) => {
    const doc = '- Egy hosszú listaelem, amely tördelődik\nSima sor\n> - [ ] Idézett feladat';
    const parent = document.createElement('div'); document.body.append(parent);
    const v = new EditorView({ parent, state: EditorState.create({ doc, extensions: ext(mod) }) });
    nezetek.push(v);
    ensureSyntaxTree(v.state, doc.length, 5000);
    // jsdom nem rajzol: a koordinátákat a forrás-oszlop szerint adjuk (1 karakter = 8 px)
    vi.spyOn(v, 'coordsAtPos').mockImplementation((pos: number) => {
      const s = v.state.doc.lineAt(pos);
      const x = (pos - s.from) * 8;
      return { left: x, right: x, top: s.number * 20, bottom: s.number * 20 + 16 };
    });
    const kuld = vi.spyOn(v, 'dispatch');
    v.requestMeasure(); (v as unknown as { measure(): void }).measure();
    await Promise.resolve();
    const sorok = [...v.contentDOM.querySelectorAll<HTMLElement>('.cm-line')];
    expect(sorok[0].classList.contains('cm-fuggo')).toBe(true);
    expect(sorok[0].style.getPropertyValue('--fuggo-behuzas')).toBe('16px');
    expect(sorok[1].classList.contains('cm-fuggo')).toBe(false);
    expect(sorok[2].style.getPropertyValue('--fuggo-behuzas')).toBe('64px');
    const hivas = kuld.mock.calls.length;
    v.requestMeasure(); (v as unknown as { measure(): void }).measure();
    await Promise.resolve();
    expect(kuld.mock.calls.length).toBe(hivas);
    expect(v.state.doc.toString()).toBe(doc);
  });
});
