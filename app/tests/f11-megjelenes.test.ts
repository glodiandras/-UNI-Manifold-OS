// F11 Appearance / Editor settings (14-appearance-01, -02, -04, -05): font families, table-cell spellcheck, auto-pair switches.
// Synthetic content only; no core, no vault, no network.
import { readFileSync } from 'node:fs';
import { undoDepth } from '@codemirror/commands';
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorSelection, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { alapBeallitasok, type Beallitasok } from '../src/lib/beallitasok/tipusok';
import { BETU_NEV_MAX, MONO_TARTALEK, SZOVEG_TARTALEK, betuAlkalmaz, betuCss, betuNevJo, betuTelepitve, cssSztring, telepitettJavaslat } from '../src/lib/elrendezes/betutipus';
import { bovitmenyek, opciokKapcsolo, szerkesztoOpciok } from '../src/szerkeszto/beallitas';

const olvas = (ut: string) => readFileSync(decodeURIComponent(new URL(ut, import.meta.url).pathname), 'utf8');

describe('14-appearance-01/02: font family names, CSS and runtime tokens', () => {
  it('accepts plain installed-family names and the empty default', () => {
    for (const jo of ['', 'Helvetica Neue', 'SF Pro Text', 'Source Serif 4', 'Noto Sans CJK JP', 'Menlo', 'Író-Gép_2.0', 'A+B', 'x'.repeat(BETU_NEV_MAX)])
      expect(betuNevJo(jo), jo).toBe(true);
  });

  it('rejects quotes, CSS punctuation, URLs, control characters, odd spacing and overlong names', () => {
    for (const rossz of ['"x"', 'x;y', 'a{b}', 'url(http://x.invalid/f.woff)', 'x, serif', 'a\\b', 'a:b', 'a/b', ' pad', 'pad ', 'a  b', 'x'.repeat(BETU_NEV_MAX + 1), 'a\nb', '@import', "a'b", 'a<b', 3, null, ['a']])
      expect(betuNevJo(rossz), JSON.stringify(rossz)).toBe(false);
  });

  it('always quotes the name and adds the token fallback; invalid or empty names give only the fallback', () => {
    expect(betuCss('Helvetica Neue', SZOVEG_TARTALEK)).toBe('"Helvetica Neue", var(--betu-rendszer)');
    expect(betuCss('Menlo', MONO_TARTALEK)).toBe('"Menlo", var(--betu-mono-alap)');
    expect(betuCss('', SZOVEG_TARTALEK)).toBe(SZOVEG_TARTALEK);
    expect(betuCss('x";}body{display:none', SZOVEG_TARTALEK)).toBe(SZOVEG_TARTALEK);
    expect(betuCss('url(https://example.invalid/a.woff)', MONO_TARTALEK)).toBe(MONO_TARTALEK);
  });

  it('escapes quotes, backslashes and control characters even if called directly', () => {
    expect(cssSztring('a"b\\c\u0000d\n')).toBe('a\\"b\\\\cd');
  });

  it('sets and clears only the two font tokens on the root; no @font-face, no URL anywhere', () => {
    const gyoker = document.createElement('div');
    betuAlkalmaz({ betu_szoveg: 'Georgia', betu_mono: 'Menlo' }, gyoker);
    expect(gyoker.style.getPropertyValue('--betu-jegyzet')).toBe('"Georgia", var(--betu-rendszer)');
    expect(gyoker.style.getPropertyValue('--betu-mono')).toBe('"Menlo", var(--betu-mono-alap)');
    betuAlkalmaz({ betu_szoveg: '', betu_mono: 'bad;name' }, gyoker);
    expect(gyoker.style.getPropertyValue('--betu-jegyzet')).toBe('');
    expect(gyoker.style.getPropertyValue('--betu-mono')).toBe('');
    betuAlkalmaz({}, gyoker);
    expect(gyoker.getAttribute('style') ?? '').not.toMatch(/url\(|@font-face/);
    const forras = olvas('../src/lib/elrendezes/betutipus.ts').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');       // code only, not comments
    expect(forras).not.toMatch(/@font-face|FontFace\(|queryLocalFonts|fonts\.googleapis|https?:\/\//);
  });

  it('the tokens exist, note text and Source mode use them, and defaults stay the system fonts', () => {
    const tokens = olvas('../src/styles/tokens.css');
    expect(tokens).toMatch(/--betu-jegyzet:\s*var\(--betu-rendszer\)/);
    expect(tokens).toMatch(/--betu-mono:\s*var\(--betu-mono-alap\)/);
    expect(tokens).toMatch(/--betu-mono-alap:\s*ui-monospace/);
    const szerkeszto = olvas('../src/szerkeszto/szerkeszto.css');
    expect(szerkeszto).toMatch(/\.szerkeszto \.cm-editor \{[^}]*font-family: var\(--betu-jegyzet\)/);
    expect(szerkeszto).toMatch(/\.cm-editor\.cm-forrasmod \{[^}]*font-family: var\(--betu-mono\)/);
    expect(olvas('../src/szerkeszto/Olvaso.svelte')).toMatch(/\.olvaso \{[^}]*font-family: var\(--betu-jegyzet\)/);
    expect(olvas('../src/styles/alap.css')).toMatch(/\.tipo code \{[^}]*font-family: var\(--betu-mono\)/);
  });

  it('detects installed families by width probe and says nothing when probing is impossible', () => {
    const telepitett = new Set(['Georgia', 'Menlo']);
    const mero = (font: string, szoveg: string) => {
      const m = /^72px (?:"([^"]+)", )?(monospace|serif|sans-serif)$/.exec(font);
      const alap = m?.[2] === 'monospace' ? 10 : m?.[2] === 'serif' ? 11 : 12;
      return szoveg.length * (m?.[1] && telepitett.has(m[1]) ? alap + 3 : alap);
    };
    expect(betuTelepitve('Georgia', mero)).toBe(true);
    expect(betuTelepitve('No Such Font', mero)).toBe(false);
    expect(betuTelepitve('', mero)).toBe(true);
    expect(betuTelepitve('bad;name', mero)).toBe(false);
    expect(betuTelepitve('Georgia', null)).toBeNull();
    expect(telepitettJavaslat(['Georgia', 'Nope', 'Menlo'], mero)).toEqual(['Georgia', 'Menlo']);
    expect(telepitettJavaslat(['Nope', 'Nada'], mero)).toEqual(['Nope', 'Nada']);        // nothing detected: keep the list, never empty
  });

  it('defaults carry empty font names', () => {
    const b = alapBeallitasok();
    expect([b.megjelenes.betu_szoveg, b.megjelenes.betu_mono]).toEqual(['', '']);
  });
});

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; });

function nezet(doc: string, b: Beallitasok = alapBeallitasok(), kurzor = doc.length): EditorView {
  const hely = document.createElement('div'); document.body.append(hely);
  const state = EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({
    mod: 'elo', csakOlvashato: false, ut: 'Synthetic.md', cimke: 'Synthetic editor', beallitas: b,
    kiegeszites: { fajlok: () => [], legutobbi: () => [] },
  }) });
  ensureSyntaxTree(state, state.doc.length, 5000);
  const v = new EditorView({ state, parent: hely }); nezetek.push(v); return v;
}
function gepel(v: EditorView, szoveg: string): void {
  for (const c of szoveg) {
    const r = v.state.selection.main;
    const kezelt = v.state.facet(EditorView.inputHandler).some((h) => h(v, r.from, r.to, c, () => v.state.update({ changes: { from: r.from, to: r.to, insert: c } })));
    if (!kezelt) v.dispatch({ changes: { from: r.from, to: r.to, insert: c }, selection: { anchor: r.from + 1 }, userEvent: 'input.type' });
  }
}
const szoveg = (v: EditorView) => v.state.doc.toString();
function valtoztat(v: EditorView, f: (b: Beallitasok) => void): void {
  const b = alapBeallitasok(); f(b);
  v.dispatch({ effects: opciokKapcsolo.reconfigure(szerkesztoOpciok(b)) });
}

describe('14-appearance-05: auto-pair switches (brackets, quotes, Markdown syntax)', () => {
  it('defaults: everything pairs, as before the switches existed', () => {
    const a = nezet(''); gepel(a, '('); expect(szoveg(a)).toBe('()');
    const b = nezet(''); gepel(b, '"'); expect(szoveg(b)).toBe('""');
    const c = nezet(''); gepel(c, '*'); expect(szoveg(c)).toBe('**');
    const d = nezet(''); gepel(d, '[['); expect(szoveg(d)).toBe('[[]]');
  });

  it('brackets off: ( and { and the closing ]] of [[ stay single; quotes and Markdown marks still pair', () => {
    const b = alapBeallitasok(); b.szerkeszto.auto_par_zarojel = false;
    const v = nezet('', b);
    gepel(v, '('); gepel(v, '{'); expect(szoveg(v)).toBe('({');
    gepel(v, '"'); expect(szoveg(v)).toBe('({""');
    const m = nezet('', b); gepel(m, '*'); expect(szoveg(m)).toBe('**');
    const w = nezet('', b); gepel(w, '[['); expect(szoveg(w)).toBe('[[');            // the link menu may open, but no ]] is added
  });

  it('quotes off: " \' ` stay single; brackets still pair', () => {
    const b = alapBeallitasok(); b.szerkeszto.auto_par_idezojel = false;
    for (const q of ['"', "'", '`']) { const v = nezet('', b); gepel(v, q); expect(szoveg(v), q).toBe(q); }
    const v = nezet('', b); gepel(v, '('); expect(szoveg(v)).toBe('()');
  });

  it.each(['*', '_', '=', '$'])('Markdown syntax off: %s stays single; brackets and quotes still pair', (jel) => {
    const b = alapBeallitasok(); b.szerkeszto.auto_par_jeloles = false;
    const v = nezet('Text ', b); gepel(v, jel); expect(szoveg(v)).toBe('Text ' + jel);
    const k = nezet('', b); gepel(k, '('); expect(szoveg(k)).toBe('()');
    const q = nezet('', b); gepel(q, '"'); expect(szoveg(q)).toBe('""');
  });

  it('toggling live reconfigures without touching the document, the selection or the undo history', () => {
    const v = nezet('Alpha beta');
    v.dispatch({ selection: EditorSelection.create([EditorSelection.range(0, 5)]) });
    gepel(v, '*');
    const doc = v.state.doc, kijeloles = v.state.selection, lepesek = undoDepth(v.state);
    valtoztat(v, (b) => { b.szerkeszto.auto_par_zarojel = false; b.szerkeszto.auto_par_idezojel = false; b.szerkeszto.auto_par_jeloles = false; });
    expect(v.state.doc).toBe(doc); expect(v.state.selection.eq(kijeloles)).toBe(true); expect(undoDepth(v.state)).toBe(lepesek);
    const u = nezet(''); valtoztat(u, (b) => { b.szerkeszto.auto_par_zarojel = false; });
    gepel(u, '('); expect(szoveg(u)).toBe('(');
    valtoztat(u, () => {});
    gepel(u, '('); expect(szoveg(u)).toBe('(()');
  });

  it('with every switch off nothing is generated and Backspace deletes a single character', () => {
    const b = alapBeallitasok(); b.szerkeszto.auto_par_zarojel = b.szerkeszto.auto_par_idezojel = b.szerkeszto.auto_par_jeloles = false;
    const v = nezet('', b);
    gepel(v, '({"\'`*_=$'); expect(szoveg(v)).toBe('({"\'`*_=$');
  });
});

describe('14-appearance-04: the spellcheck setting also governs table-cell inputs', () => {
  const TABLA = '| a | b |\n|---|---|\n| 1 | 2 |\n';
  function cellaMezo(v: EditorView): HTMLInputElement {
    v.dom.querySelector<HTMLElement>('.nt-tabla [data-sor="1"][data-oszlop="0"]')!.click();
    return v.dom.querySelector<HTMLInputElement>('input.nt-cella-mezo')!;
  }

  it('spellcheck off: the cell input is not spell-checked, and the editor content says the same', () => {
    const b = alapBeallitasok(); b.szerkeszto.helyesiras = false;
    const v = nezet(TABLA, b, 0);
    expect(v.contentDOM.getAttribute('spellcheck')).toBe('false');
    expect(cellaMezo(v).spellcheck).toBe(false);
  });

  it('spellcheck on: the cell input is spell-checked; switching live changes the next opened cell', () => {
    const v = nezet(TABLA, alapBeallitasok(), 0);
    const be = cellaMezo(v);
    expect(be.spellcheck).toBe(true);
    be.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    valtoztat(v, (b) => { b.szerkeszto.helyesiras = false; });
    expect(cellaMezo(v).spellcheck).toBe(false);
  });

  it('no editor source forces spellcheck on: only the setting and explicit false remain', () => {
    const talalatok: string[] = [];
    const fajlok = import.meta.glob(['../src/szerkeszto/**/*.ts', '../src/szerkeszto/**/*.svelte'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    for (const [ut, s] of Object.entries(fajlok)) {
      for (const m of s.matchAll(/spellcheck\s*=\s*(?:\{?\s*)?(?:"true"|'true'|true)\b|\.spellcheck\s*=\s*true/g)) talalatok.push(`${ut}: ${m[0]}`);
    }
    expect(talalatok).toEqual([]);
    expect(olvas('../src/szerkeszto/notion/tablazat/szerkeszto.ts')).toMatch(/input\.spellcheck = this\.view\.contentDOM\.getAttribute\('spellcheck'\) !== 'false'/);
  });
});
